"""Version, audit and index-health management for the knowledge-base corpus."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import KnowledgeBaseConfig, load_kb_config
from .ingest import corpus_manifest, iter_corpus_files
from .stores import VectorStore

VERSIONS_FILE = "versions.jsonl"
AUDIT_FILE = "audit.jsonl"
WRITE_LOCK_FILE = "write.lock"


@dataclass(frozen=True)
class AuditActor:
    user_id: str = "system"
    email: str | None = None


@dataclass(frozen=True)
class DocumentVersion:
    version_id: str
    document_path: str
    content_sha256: str
    size: int
    created_at: str
    action: str
    actor_id: str
    actor_email: str | None
    snapshot_path: str
    restored_from: str | None = None


def management_dir(config: KnowledgeBaseConfig | None = None) -> Path:
    config = config or load_kb_config()
    return config.management_dir or (config.project_root / "data" / "kb_management")


@contextmanager
def knowledge_base_write_lock() -> Iterator[None]:
    """Serialize source and index mutations across Gateway worker processes."""
    root = management_dir()
    root.mkdir(parents=True, exist_ok=True)
    with (root / WRITE_LOCK_FILE).open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL record at {path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid JSONL object at {path}:{line_number}")
        records.append(payload)
    return records


def record_document_version(
    document_path: str,
    content: bytes,
    *,
    action: str,
    actor: AuditActor | None = None,
    restored_from: str | None = None,
) -> DocumentVersion:
    """Persist an immutable content snapshot and append its version metadata."""
    actor = actor or AuditActor()
    root = management_dir()
    version_id = uuid.uuid4().hex
    suffix = Path(document_path).suffix.lower()
    snapshot_relative = Path("snapshots") / document_path / f"{version_id}{suffix}"
    snapshot = root / snapshot_relative
    snapshot.parent.mkdir(parents=True, exist_ok=True)

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=snapshot.parent,
            prefix=".kb-version-",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, snapshot)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)

    version = DocumentVersion(
        version_id=version_id,
        document_path=document_path,
        content_sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at=_utc_now(),
        action=action,
        actor_id=actor.user_id,
        actor_email=actor.email,
        snapshot_path=snapshot_relative.as_posix(),
        restored_from=restored_from,
    )
    try:
        _append_jsonl(root / VERSIONS_FILE, asdict(version))
    except Exception:
        snapshot.unlink(missing_ok=True)
        raise
    return version


def record_audit_event(
    action: str,
    document_path: str,
    *,
    actor: AuditActor | None = None,
    outcome: str = "success",
    version_id: str | None = None,
    content_sha256: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    actor = actor or AuditActor()
    event = {
        "event_id": uuid.uuid4().hex,
        "created_at": _utc_now(),
        "action": action,
        "outcome": outcome,
        "document_path": document_path,
        "version_id": version_id,
        "content_sha256": content_sha256,
        "actor_id": actor.user_id,
        "actor_email": actor.email,
        "detail": detail,
    }
    _append_jsonl(management_dir() / AUDIT_FILE, event)
    return event


def list_document_versions(document_path: str) -> list[dict[str, Any]]:
    records = _read_jsonl(management_dir() / VERSIONS_FILE)
    return [record for record in reversed(records) if record.get("document_path") == document_path]


def get_document_version(document_path: str, version_id: str) -> tuple[dict[str, Any], bytes]:
    for record in list_document_versions(document_path):
        if record.get("version_id") != version_id:
            continue
        snapshot = (management_dir() / str(record["snapshot_path"])).resolve()
        root = management_dir().resolve()
        if root not in snapshot.parents or not snapshot.is_file():
            raise RuntimeError("Knowledge-base version snapshot is missing or unsafe")
        content = snapshot.read_bytes()
        if hashlib.sha256(content).hexdigest() != record.get("content_sha256"):
            raise RuntimeError("Knowledge-base version snapshot checksum mismatch")
        return record, content
    raise KeyError(version_id)


def list_audit_events(limit: int = 100) -> list[dict[str, Any]]:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    return list(reversed(_read_jsonl(management_dir() / AUDIT_FILE)[-limit:]))


def _safe_corpus_files(config: KnowledgeBaseConfig) -> list[Path]:
    if not config.corpus_dir.exists():
        return []
    return iter_corpus_files(config.corpus_dir, allow_empty=True)


def knowledge_base_status() -> dict[str, Any]:
    config = load_kb_config()
    files = _safe_corpus_files(config)
    current_manifest = corpus_manifest(config.corpus_dir, files)
    store = VectorStore()
    index_loaded = store.load(config.index_dir)
    index_metadata = store.index_metadata if index_loaded else {}
    indexed_hash = index_metadata.get("corpus_manifest_hash")
    current_hash = current_manifest["sha256"]
    if not index_loaded:
        state = "missing"
    elif indexed_hash == current_hash:
        state = "ready"
    else:
        state = "stale"
    return {
        "state": state,
        "in_sync": state == "ready",
        "document_count": len(files),
        "indexed_document_count": int(index_metadata.get("document_count", 0)),
        "chunk_count": int(index_metadata.get("chunk_count", 0)),
        "embedding_backend": index_metadata.get("backend_name"),
        "embedding_dim": index_metadata.get("dim"),
        "index_created_at": index_metadata.get("created_at"),
        "corpus_manifest_hash": current_hash,
        "indexed_manifest_hash": indexed_hash,
    }


def list_documents() -> list[dict[str, Any]]:
    config = load_kb_config()
    files = _safe_corpus_files(config)
    store = VectorStore()
    index_loaded = store.load(config.index_dir)
    indexed_documents = {item.get("path"): item.get("sha256") for item in store.index_metadata.get("documents", []) if isinstance(item, dict)}
    chunks_by_source = Counter(metadata.get("source_file") for metadata in store.metadatas if metadata.get("source_file"))
    latest_versions: dict[str, dict[str, Any]] = {}
    for version in _read_jsonl(management_dir(config) / VERSIONS_FILE):
        document_path = version.get("document_path")
        if isinstance(document_path, str):
            latest_versions[document_path] = version

    documents = []
    for path in files:
        relative = path.relative_to(config.corpus_dir).as_posix()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        indexed_hash = indexed_documents.get(relative)
        if not index_loaded or indexed_hash is None:
            index_status = "missing"
        elif indexed_hash == content_hash:
            index_status = "indexed"
        else:
            index_status = "stale"
        stat = path.stat()
        documents.append(
            {
                "path": relative,
                "category": Path(relative).parts[0],
                "filename": path.name,
                "file_type": path.suffix.lower().lstrip("."),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
                "content_sha256": content_hash,
                "index_status": index_status,
                "chunk_count": chunks_by_source.get(relative, 0),
                "latest_version_id": latest_versions.get(relative, {}).get("version_id"),
            }
        )
    return documents


def get_document(document_path: str) -> dict[str, Any]:
    for document in list_documents():
        if document["path"] == document_path:
            return document
    raise KeyError(document_path)
