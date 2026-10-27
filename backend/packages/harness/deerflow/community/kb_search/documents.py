"""Safe document-management operations for the knowledge-base corpus."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from deerflow.community.kb_search.config import load_kb_config
from deerflow.community.kb_search.ingest import remove_doc, upsert_doc
from deerflow.community.kb_search.management import (
    AuditActor,
    get_document_version,
    knowledge_base_write_lock,
    record_audit_event,
    record_document_version,
)
from deerflow.community.kb_search.parsers import SUPPORTED_EXTENSIONS
from deerflow.community.kb_search.paths import corpus_dir

logger = logging.getLogger(__name__)

KB_CATEGORIES = frozenset({"platform", "contract-dev", "baas", "crosschain", "api-reference"})


class DocumentValidationError(ValueError):
    """Raised when an uploaded knowledge-base document is invalid."""


def max_document_bytes() -> int:
    return load_kb_config().max_document_bytes


def resolve_document_path(category: str, filename: str) -> Path:
    """Resolve and validate a corpus destination without following symlinks out."""
    if category not in KB_CATEGORIES:
        raise DocumentValidationError(f"不支持的知识库分类: {category}")

    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."} or "\\" in safe_name:
        raise DocumentValidationError("文件名不安全")
    if Path(safe_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentValidationError(f"知识库仅支持以下文档类型: {supported}")
    if len(safe_name.encode("utf-8")) > 255:
        raise DocumentValidationError("文件名过长")

    root = corpus_dir()
    category_dir = (root / category).resolve()
    if category_dir.parent != root.resolve():
        raise DocumentValidationError("知识库分类路径不安全")

    destination = (category_dir / safe_name).resolve()
    if destination.parent != category_dir:
        raise DocumentValidationError("文件路径越界")
    return destination


def replace_and_index_document(
    category: str,
    filename: str,
    content: bytes,
    *,
    actor: AuditActor | None = None,
) -> Path:
    """Atomically replace a corpus document, then refresh its derived index.

    If indexing fails, restore the previous file and index state so callers never
    observe a new source that cannot yet be retrieved.
    """
    with knowledge_base_write_lock():
        return _replace_and_index_document_unlocked(
            category,
            filename,
            content,
            actor=actor,
            action="upload",
        )


def _replace_and_index_document_unlocked(
    category: str,
    filename: str,
    content: bytes,
    *,
    actor: AuditActor | None,
    action: str,
    restored_from: str | None = None,
) -> Path:
    if Path(filename).suffix.lower() == ".md":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentValidationError("Markdown 文档必须是 UTF-8 编码") from exc
    size_limit = max_document_bytes()
    if len(content) > size_limit:
        raise DocumentValidationError(f"文档超过 {size_limit // (1024 * 1024)} MB 上限")

    destination = resolve_document_path(category, filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = destination.read_bytes() if destination.is_file() else None

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".kb-upload-", suffix=".part", delete=False) as handle:
            temp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    document_path = destination.relative_to(corpus_dir()).as_posix()
    try:
        upsert_doc(destination)
        version = record_document_version(
            document_path,
            content,
            action=action,
            actor=actor,
            restored_from=restored_from,
        )
    except Exception as exc:
        _rollback(destination, previous)
        _record_audit_safely(
            action,
            document_path,
            actor=actor,
            outcome="failure",
            detail=type(exc).__name__,
        )
        raise
    _record_audit_safely(
        action,
        document_path,
        actor=actor,
        version_id=version.version_id,
        content_sha256=version.content_sha256,
    )
    return destination


def delete_and_deindex_document(
    category: str,
    filename: str,
    *,
    actor: AuditActor | None = None,
) -> Path:
    """Delete a corpus document while preserving a restorable version snapshot."""
    with knowledge_base_write_lock():
        destination = resolve_document_path(category, filename)
        if not destination.is_file():
            raise FileNotFoundError(destination)
        content = destination.read_bytes()
        document_path = destination.relative_to(corpus_dir()).as_posix()
        try:
            destination.unlink()
            remove_doc(destination)
            version = record_document_version(
                document_path,
                content,
                action="delete",
                actor=actor,
            )
        except Exception as exc:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            try:
                upsert_doc(destination)
            except Exception:
                logger.exception("Failed to roll back deleted knowledge-base document %s", document_path)
            _record_audit_safely(
                "delete",
                document_path,
                actor=actor,
                outcome="failure",
                detail=type(exc).__name__,
            )
            raise
        _record_audit_safely(
            "delete",
            document_path,
            actor=actor,
            version_id=version.version_id,
            content_sha256=version.content_sha256,
        )
        return destination


def restore_document_version(
    category: str,
    filename: str,
    version_id: str,
    *,
    actor: AuditActor | None = None,
) -> Path:
    """Restore one immutable snapshot and index it as a new current version."""
    with knowledge_base_write_lock():
        destination = resolve_document_path(category, filename)
        document_path = destination.relative_to(corpus_dir()).as_posix()
        _record, content = get_document_version(document_path, version_id)
        return _replace_and_index_document_unlocked(
            category,
            filename,
            content,
            actor=actor,
            action="restore",
            restored_from=version_id,
        )


def _record_audit_safely(
    action: str,
    document_path: str,
    *,
    actor: AuditActor | None,
    outcome: str = "success",
    version_id: str | None = None,
    content_sha256: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        record_audit_event(
            action,
            document_path,
            actor=actor,
            outcome=outcome,
            version_id=version_id,
            content_sha256=content_sha256,
            detail=detail,
        )
    except Exception:
        logger.exception("Failed to append knowledge-base audit event for %s", document_path)


def _rollback(destination: Path, previous: bytes | None) -> None:
    try:
        if previous is None:
            destination.unlink(missing_ok=True)
            remove_doc(destination)
            return
        destination.write_bytes(previous)
        upsert_doc(destination)
    except Exception:
        # The caller still receives the original indexing failure; rollback is
        # best-effort because its own failure should not mask that cause.
        pass
