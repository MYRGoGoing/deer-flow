import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from _router_auth_helpers import call_unwrapped
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from app.gateway.auth.models import User
from app.gateway.authz import AuthContext, Permissions
from app.gateway.routers import knowledge_base


def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_upload_knowledge_base_document_indexes_incrementally(monkeypatch, tmp_path):
    destination = tmp_path / "uploaded.md"
    captured = {}

    def fake_replace(category, filename, content, *, actor=None):
        captured.update(
            {
                "category": category,
                "filename": filename,
                "content": content,
                "actor": actor,
            }
        )
        return destination

    monkeypatch.setattr(knowledge_base, "replace_and_index_document", fake_replace)

    result = asyncio.run(
        call_unwrapped(
            knowledge_base.upload_knowledge_base_document,
            request=SimpleNamespace(),
            file=_upload("deployment guide.md", b"# Deployment"),
            category="baas",
            config=SimpleNamespace(),
        )
    )

    assert result.success is True
    assert result.document.filename == "deployment guide.md"
    assert result.document.category == "baas"
    assert result.document.path == str(destination)
    assert captured == {
        "category": "baas",
        "filename": "deployment guide.md",
        "content": b"# Deployment",
        "actor": knowledge_base.AuditActor(),
    }


def test_upload_knowledge_base_document_rejects_unsupported_type(monkeypatch):
    from deerflow.community.kb_search.documents import DocumentValidationError

    def fail_replace(_category, _filename, _content, *, actor=None):
        del actor
        raise DocumentValidationError("知识库仅支持以下文档类型: .docx, .md, .pdf, .pptx")

    monkeypatch.setattr(knowledge_base, "replace_and_index_document", fail_replace)

    with pytest.raises(Exception, match="知识库仅支持以下文档类型") as exc_info:
        asyncio.run(
            call_unwrapped(
                knowledge_base.upload_knowledge_base_document,
                request=SimpleNamespace(),
                file=_upload("notes.txt", b"text only"),
                category="platform",
                config=SimpleNamespace(),
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == ("知识库仅支持以下文档类型: .docx, .md, .pdf, .pptx")


def test_status_and_document_routes_use_thread_offload(monkeypatch):
    status = {
        "state": "ready",
        "in_sync": True,
        "document_count": 2,
        "indexed_document_count": 2,
        "chunk_count": 9,
        "embedding_backend": "test",
        "embedding_dim": 4,
        "index_created_at": "2026-09-15T00:00:00+00:00",
        "corpus_manifest_hash": "abc",
        "indexed_manifest_hash": "abc",
    }
    documents = [{"path": "platform/guide.md"}]
    monkeypatch.setattr(knowledge_base, "knowledge_base_status", lambda: status)
    monkeypatch.setattr(knowledge_base, "list_documents", lambda: documents)

    status_result = asyncio.run(
        call_unwrapped(
            knowledge_base.get_knowledge_base_status,
            request=SimpleNamespace(),
        )
    )
    documents_result = asyncio.run(
        call_unwrapped(
            knowledge_base.get_knowledge_base_documents,
            request=SimpleNamespace(),
        )
    )

    assert status_result.state == "ready"
    assert status_result.chunk_count == 9
    assert documents_result == documents


def test_delete_and_restore_routes_forward_actor(monkeypatch):
    calls = []
    monkeypatch.setattr(
        knowledge_base,
        "delete_and_deindex_document",
        lambda category, filename, *, actor: calls.append(("delete", category, filename, actor)),
    )
    monkeypatch.setattr(
        knowledge_base,
        "restore_document_version",
        lambda category, filename, version_id, *, actor: calls.append(("restore", category, filename, version_id, actor)),
    )
    monkeypatch.setattr(
        knowledge_base,
        "get_document",
        lambda path: {"path": path},
    )

    delete_result = asyncio.run(
        call_unwrapped(
            knowledge_base.delete_knowledge_base_document,
            category="platform",
            filename="guide.md",
            request=SimpleNamespace(),
        )
    )
    restore_result = asyncio.run(
        call_unwrapped(
            knowledge_base.restore_knowledge_base_document_version,
            category="platform",
            filename="guide.md",
            version_id="version-1",
            request=SimpleNamespace(),
        )
    )

    assert delete_result.document_path == "platform/guide.md"
    assert restore_result.document_path == "platform/guide.md"
    assert calls == [
        ("delete", "platform", "guide.md", knowledge_base.AuditActor()),
        (
            "restore",
            "platform",
            "guide.md",
            "version-1",
            knowledge_base.AuditActor(),
        ),
    ]


def test_kb_read_permission_does_not_grant_write_routes(monkeypatch):
    app = FastAPI()
    app.include_router(knowledge_base.router)
    user = User(id=uuid4(), email="reader@example.com", password_hash="hash")
    auth = AuthContext(user=user, permissions=[Permissions.KB_READ])
    monkeypatch.setattr(
        knowledge_base,
        "knowledge_base_status",
        lambda: {
            "state": "missing",
            "in_sync": False,
            "document_count": 0,
            "indexed_document_count": 0,
            "chunk_count": 0,
        },
    )

    with patch("app.gateway.authz._authenticate", new=AsyncMock(return_value=auth)):
        with TestClient(app) as client:
            assert client.get("/api/kb/status").status_code == 200
            response = client.delete("/api/kb/documents/platform/guide.md")

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied: kb:write"


def test_search_returns_passages_and_forwards_category(monkeypatch):
    calls = []

    def search(query, *, top_k, category):
        calls.append((query, top_k, category))
        return [{"chunk_id": "chunk-1", "doc_title": "RBFT", "text": "共识说明", "source_file": "platform/rbft.md", "weak_evidence": False, "_store_index": 1}]

    monkeypatch.setattr(knowledge_base, "hybrid_search", search)
    app = FastAPI()
    app.include_router(knowledge_base.router)
    auth = AuthContext(user=User(id=uuid4(), email="reader@example.com", password_hash="hash"), permissions=[Permissions.KB_READ])
    with patch("app.gateway.authz._authenticate", new=AsyncMock(return_value=auth)):
        with TestClient(app) as client:
            response = client.get("/api/kb/search", params={"q": " RBFT ", "category": "platform", "top_k": 5})
            assert client.get("/api/kb/search", params={"q": "   "}).status_code == 422
            assert client.get("/api/kb/search", params={"q": "test", "top_k": 100}).status_code == 422
    assert response.status_code == 200
    assert calls == [("RBFT", 5, "platform")]
    payload = response.json()
    assert payload["query"] == "RBFT"
    assert payload["elapsed_ms"] >= 0
    assert payload["hits"][0]["doc_title"] == "RBFT"
    assert "_store_index" not in payload["hits"][0]


def test_search_missing_index_is_actionable_and_requires_permission(monkeypatch):
    def search(*_args, **_kwargs):
        raise knowledge_base.KnowledgeBaseNotReady("index missing")

    monkeypatch.setattr(knowledge_base, "hybrid_search", search)
    app = FastAPI()
    app.include_router(knowledge_base.router)
    reader = AuthContext(user=User(id=uuid4(), email="reader@example.com", password_hash="hash"), permissions=[Permissions.KB_READ])
    with patch("app.gateway.authz._authenticate", new=AsyncMock(return_value=reader)):
        with TestClient(app) as client:
            assert client.get("/api/kb/search?q=RBFT").status_code == 503
    with patch("app.gateway.authz._authenticate", new=AsyncMock(return_value=AuthContext())):
        with TestClient(app) as client:
            assert client.get("/api/kb/search?q=RBFT").status_code == 401
    with patch("app.gateway.authz._authenticate", new=AsyncMock(return_value=AuthContext(user=reader.user))):
        with TestClient(app) as client:
            assert client.get("/api/kb/search?q=RBFT").status_code == 403
