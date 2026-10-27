"""Knowledge-base document, version and index-health management API."""

import asyncio
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from app.gateway.authz import get_auth_context, require_permission
from app.gateway.deps import get_config
from deerflow.community.kb_search.documents import (
    DocumentValidationError,
    delete_and_deindex_document,
    max_document_bytes,
    replace_and_index_document,
    restore_document_version,
)
from deerflow.community.kb_search.management import (
    AuditActor,
    get_document,
    knowledge_base_status,
    list_audit_events,
    list_document_versions,
    list_documents,
)
from deerflow.community.kb_search.retriever import KnowledgeBaseNotReady, hybrid_search
from deerflow.config.app_config import AppConfig
from deerflow.uploads.manager import normalize_filename

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class KnowledgeBaseDocument(BaseModel):
    filename: str
    category: str
    path: str
    size: int


class KnowledgeBaseUploadResponse(BaseModel):
    success: bool
    document: KnowledgeBaseDocument
    message: str


class KnowledgeBaseMutationResponse(BaseModel):
    success: bool
    document_path: str
    message: str


class KnowledgeBaseStatusResponse(BaseModel):
    state: str
    in_sync: bool
    document_count: int
    indexed_document_count: int
    chunk_count: int
    embedding_backend: str | None = None
    embedding_dim: int | None = None
    index_created_at: str | None = None
    corpus_manifest_hash: str | None = None
    indexed_manifest_hash: str | None = None


class KnowledgeBaseSearchHit(BaseModel):
    chunk_id: str
    doc_title: str = ""
    source_file: str = ""
    category: str = ""
    text: str = ""
    section_path: str = ""
    context_text: str = ""
    parent_excerpt: str = ""
    page_number: int | None = None
    slide_number: int | None = None
    weak_evidence: bool = False


class KnowledgeBaseSearchResponse(BaseModel):
    query: str
    hits: list[KnowledgeBaseSearchHit]
    elapsed_ms: float


@router.get("/search", response_model=KnowledgeBaseSearchResponse)
@require_permission("kb", "read")
async def search_knowledge_base(
    request: Request,
    q: str = Query(min_length=1, max_length=1000),
    category: str | None = Query(None, max_length=80),
    top_k: int = Query(8, ge=1, le=20),
) -> KnowledgeBaseSearchResponse:
    """Expose the agent's existing hybrid retriever without invoking an LLM."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="请输入检索问题")
    started = perf_counter()
    try:
        hits = await asyncio.to_thread(hybrid_search, query, top_k=top_k, category=category)
    except KnowledgeBaseNotReady as exc:
        raise HTTPException(status_code=503, detail="知识库索引尚未就绪，请检查或重建索引") from exc
    except Exception:
        logger.exception("Knowledge-base search failed")
        raise HTTPException(status_code=503, detail="知识库检索暂不可用，请检查嵌入服务后重试") from None
    return KnowledgeBaseSearchResponse(
        query=query,
        hits=[KnowledgeBaseSearchHit.model_validate(hit) for hit in hits],
        elapsed_ms=round((perf_counter() - started) * 1000, 1),
    )


def _actor_from_request(request: Request) -> AuditActor:
    if not hasattr(request, "state"):
        return AuditActor()
    auth = get_auth_context(request)
    user = auth.user if auth is not None else None
    if user is None:
        return AuditActor()
    return AuditActor(
        user_id=str(user.id),
        email=str(user.email) if getattr(user, "email", None) else None,
    )


def _validated_filename(filename: str) -> str:
    try:
        return normalize_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=KnowledgeBaseStatusResponse)
@require_permission("kb", "read")
async def get_knowledge_base_status(request: Request) -> KnowledgeBaseStatusResponse:
    """Return corpus/index consistency and active embedding metadata."""
    status = await asyncio.to_thread(knowledge_base_status)
    return KnowledgeBaseStatusResponse.model_validate(status)


@router.get("/documents", response_model=list[dict[str, Any]])
@require_permission("kb", "read")
async def get_knowledge_base_documents(request: Request) -> list[dict[str, Any]]:
    """List current corpus documents with per-document indexing state."""
    return await asyncio.to_thread(list_documents)


@router.get("/documents/{category}/{filename}/versions", response_model=list[dict[str, Any]])
@require_permission("kb", "read")
async def get_knowledge_base_document_versions(
    category: str,
    filename: str,
    request: Request,
) -> list[dict[str, Any]]:
    """List immutable snapshots for one current or deleted document."""
    safe_name = _validated_filename(filename)
    return await asyncio.to_thread(list_document_versions, f"{category}/{safe_name}")


@router.get("/audit", response_model=list[dict[str, Any]])
@require_permission("kb", "write")
async def get_knowledge_base_audit_events(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Return recent privileged knowledge-base mutations."""
    return await asyncio.to_thread(list_audit_events, limit)


@router.post("/upload", response_model=KnowledgeBaseUploadResponse)
@require_permission("kb", "write")
async def upload_knowledge_base_document(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("platform"),
    config: AppConfig = Depends(get_config),
) -> KnowledgeBaseUploadResponse:
    """Upload one supported document and rebuild only its index entries."""
    del config
    size_limit = await asyncio.to_thread(max_document_bytes)
    filename = _validated_filename(file.filename or "")

    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(64 * 1024):
        size += len(chunk)
        if size > size_limit:
            raise HTTPException(
                status_code=413,
                detail=f"文档超过 {size_limit // (1024 * 1024)} MB 上限",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    try:
        path = await asyncio.to_thread(
            replace_and_index_document,
            category,
            filename,
            content,
            actor=_actor_from_request(request),
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Failed to ingest knowledge-base document %r", filename)
        raise HTTPException(status_code=500, detail="知识库文档入库失败") from None

    return KnowledgeBaseUploadResponse(
        success=True,
        document=KnowledgeBaseDocument(
            filename=filename,
            category=category,
            path=str(path),
            size=size,
        ),
        message=f"文档已入库：{filename}",
    )


@router.delete("/documents/{category}/{filename}", response_model=KnowledgeBaseMutationResponse)
@require_permission("kb", "write")
async def delete_knowledge_base_document(
    category: str,
    filename: str,
    request: Request,
) -> KnowledgeBaseMutationResponse:
    """Delete one document after taking a restorable immutable snapshot."""
    safe_name = _validated_filename(filename)
    try:
        await asyncio.to_thread(
            delete_and_deindex_document,
            category,
            safe_name,
            actor=_actor_from_request(request),
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="知识库文档不存在") from exc
    except Exception:
        logger.exception("Failed to delete knowledge-base document %r", safe_name)
        raise HTTPException(status_code=500, detail="知识库文档删除失败") from None
    document_path = f"{category}/{safe_name}"
    return KnowledgeBaseMutationResponse(
        success=True,
        document_path=document_path,
        message=f"文档已删除并保留版本：{safe_name}",
    )


@router.post(
    "/documents/{category}/{filename}/versions/{version_id}/restore",
    response_model=KnowledgeBaseMutationResponse,
)
@require_permission("kb", "write")
async def restore_knowledge_base_document_version(
    category: str,
    filename: str,
    version_id: str,
    request: Request,
) -> KnowledgeBaseMutationResponse:
    """Restore an immutable snapshot and create a new current version."""
    safe_name = _validated_filename(filename)
    try:
        await asyncio.to_thread(
            restore_document_version,
            category,
            safe_name,
            version_id,
            actor=_actor_from_request(request),
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="知识库文档版本不存在") from exc
    except Exception:
        logger.exception("Failed to restore knowledge-base version %r", version_id)
        raise HTTPException(status_code=500, detail="知识库文档版本恢复失败") from None
    document_path = f"{category}/{safe_name}"
    document = await asyncio.to_thread(get_document, document_path)
    return KnowledgeBaseMutationResponse(
        success=True,
        document_path=document["path"],
        message=f"文档版本已恢复：{safe_name}",
    )
