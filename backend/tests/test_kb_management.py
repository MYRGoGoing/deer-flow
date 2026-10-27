import hashlib
import json

import numpy as np

from deerflow.community.kb_search import documents, management
from deerflow.community.kb_search.chunker import Chunk
from deerflow.community.kb_search.stores import VectorStore


def _configure(monkeypatch, tmp_path):
    corpus = tmp_path / "corpus"
    index = tmp_path / "index"
    managed = tmp_path / "management"
    corpus.mkdir()
    monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("KB_CORPUS_DIR", str(corpus))
    monkeypatch.setenv("KB_INDEX_DIR", str(index))
    monkeypatch.setenv("KB_MANAGEMENT_DIR", str(managed))
    return corpus, index, managed


def _save_index(index, document_path, content_hash):
    store = VectorStore()
    store.reset(
        backend_name="test-embedding",
        dim=2,
        index_metadata={
            "created_at": "2026-09-15T00:00:00+00:00",
            "corpus_manifest_hash": "unused",
            "documents": [{"path": document_path, "sha256": content_hash}],
            "document_count": 1,
            "chunk_count": 1,
            "backend_name": "test-embedding",
            "dim": 2,
        },
    )
    chunk = Chunk(
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_title="Guide",
        category="platform",
        source="internal",
        source_file=document_path,
        file_type="markdown",
        section_path="Guide",
        page_number=None,
        slide_number=None,
        content_type="text",
        version="1",
        parent_id="parent-1",
        parent_excerpt="body",
        text="body",
    )
    store.add([chunk], np.array([[1.0, 0.0]], dtype=np.float32))
    store.save(index)
    return store


def test_status_and_document_list_detect_stale_source(monkeypatch, tmp_path):
    corpus, index, _managed = _configure(monkeypatch, tmp_path)
    document = corpus / "platform" / "guide.md"
    document.parent.mkdir()
    document.write_text("# Guide\noriginal", encoding="utf-8")
    original_hash = hashlib.sha256(document.read_bytes()).hexdigest()
    store = _save_index(index, "platform/guide.md", original_hash)

    manifest = management.corpus_manifest(corpus, [document])
    store.index_metadata["corpus_manifest_hash"] = manifest["sha256"]
    store.save(index)
    assert management.knowledge_base_status()["state"] == "ready"
    assert management.list_documents()[0]["index_status"] == "indexed"

    document.write_text("# Guide\nchanged", encoding="utf-8")
    assert management.knowledge_base_status()["state"] == "stale"
    assert management.list_documents()[0]["index_status"] == "stale"


def test_upload_delete_and_restore_create_versions_and_audit(monkeypatch, tmp_path):
    corpus, _index, managed = _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(documents, "upsert_doc", lambda _path: None)
    monkeypatch.setattr(documents, "remove_doc", lambda _path: None)
    actor = management.AuditActor(user_id="user-1", email="owner@example.com")

    destination = documents.replace_and_index_document(
        "platform",
        "guide.md",
        b"# Guide\nversion one",
        actor=actor,
    )
    first_version = management.list_document_versions("platform/guide.md")[0]
    assert destination == corpus / "platform" / "guide.md"
    assert first_version["action"] == "upload"
    assert first_version["actor_id"] == "user-1"

    documents.replace_and_index_document(
        "platform",
        "guide.md",
        b"# Guide\nversion two",
        actor=actor,
    )
    documents.delete_and_deindex_document("platform", "guide.md", actor=actor)
    assert not destination.exists()

    documents.restore_document_version(
        "platform",
        "guide.md",
        first_version["version_id"],
        actor=actor,
    )
    assert destination.read_bytes() == b"# Guide\nversion one"
    versions = management.list_document_versions("platform/guide.md")
    assert [item["action"] for item in versions] == ["restore", "delete", "upload", "upload"]
    assert versions[0]["restored_from"] == first_version["version_id"]

    audits = management.list_audit_events()
    assert [item["action"] for item in audits] == ["restore", "delete", "upload", "upload"]
    assert all(item["actor_email"] == "owner@example.com" for item in audits)
    assert len(list((managed / "snapshots" / "platform" / "guide.md").glob("*.md"))) == 4
    assert all(json.loads(line)["document_path"] == "platform/guide.md" for line in (managed / "versions.jsonl").read_text(encoding="utf-8").splitlines())


def test_get_document_version_rejects_tampered_snapshot(monkeypatch, tmp_path):
    _corpus, _index, managed = _configure(monkeypatch, tmp_path)
    version = management.record_document_version(
        "platform/guide.md",
        b"trusted",
        action="upload",
    )
    snapshot = managed / version.snapshot_path
    snapshot.write_bytes(b"tampered")

    try:
        management.get_document_version("platform/guide.md", version.version_id)
    except RuntimeError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("tampered version snapshot was accepted")
