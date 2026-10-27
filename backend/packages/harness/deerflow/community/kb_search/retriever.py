"""Hybrid retrieval: dense vectors + BM25 fused with Reciprocal Rank Fusion."""

from __future__ import annotations

import logging

from .config import RetrievalConfig, load_kb_config
from .embedding import EmbeddingBackend, get_embedding_backend
from .reranker import Reranker, get_reranker
from .stores import BM25Store, VectorStore

logger = logging.getLogger(__name__)

_vector_store: VectorStore | None = None
_bm25_store: BM25Store | None = None
_backend: EmbeddingBackend | None = None
_reranker: Reranker | None = None


class KnowledgeBaseNotReady(RuntimeError):
    """Raised when the index is missing or incompatible with the embedding backend."""


def _load_stores() -> tuple[VectorStore, BM25Store]:
    global _vector_store, _bm25_store
    if _vector_store is None:
        vs, bm = VectorStore(), BM25Store()
        if not vs.load():
            raise KnowledgeBaseNotReady("知识库索引尚未构建。请先在 backend 目录运行: uv run python -m deerflow.community.kb_search.ingest --all")
        bm.load()
        _vector_store, _bm25_store = vs, bm
    return _vector_store, _bm25_store


def _is_weak_evidence(hit: dict, config: RetrievalConfig | None = None) -> bool:
    """Combine lexical support with the calibrated sparse-retrieval score.

    RRF is useful for ranking but intentionally discards score magnitude, so it
    cannot distinguish "the best of a bad candidate pool" from real support.
    Dense similarities are also model-dependent and can remain high for
    semantically related but unsupported questions. The gate therefore requires
    either direct IDF-weighted vocabulary coverage or a calibrated BM25 score.
    Dense scores and ranks remain available as diagnostics and ranking signals.
    """
    config = config or load_kb_config().retrieval
    lexical_score = hit.get("lexical_score", 0.0)
    bm25_score = hit["bm25_score"]
    if lexical_score >= config.lexical_threshold:
        return False
    if bm25_score >= config.bm25_threshold:
        return False
    return True


def reset_cache() -> None:
    """Drop in-process caches so a rebuilt index is picked up immediately."""
    global _vector_store, _bm25_store, _backend, _reranker
    _vector_store = None
    _bm25_store = None
    _backend = None
    _reranker = None


def _attach_context(
    results: list[dict],
    vector_store: VectorStore,
    config: RetrievalConfig,
) -> None:
    """Add bounded same-document context around the strongest matched chunks."""
    for rank, result in enumerate(results):
        base_text = result.get("parent_excerpt") or result["text"]
        context_parts = [base_text]
        context_sections = [result.get("section_path")]
        store_index = result.pop("_store_index")
        if rank < config.context_expansion_hits and not result.get("weak_evidence"):
            start = max(0, store_index - config.adjacent_chunk_window)
            end = min(
                len(vector_store.metadatas),
                store_index + config.adjacent_chunk_window + 1,
            )
            for neighbor_index in range(start, end):
                if neighbor_index == store_index:
                    continue
                neighbor = vector_store.metadatas[neighbor_index]
                if neighbor.get("doc_id") != result.get("doc_id"):
                    continue
                neighbor_text = neighbor.get("parent_excerpt") or neighbor.get("text", "")
                if not neighbor_text or neighbor_text in context_parts:
                    continue
                location = neighbor.get("section_path") or neighbor.get("doc_title") or "相邻内容"
                context_parts.append(f"[相邻章节：{location}]\n{neighbor_text}")
                context_sections.append(neighbor.get("section_path"))
        result["context_text"] = "\n\n".join(context_parts)
        result["context_sections"] = [section for section in context_sections if section]


def hybrid_search(
    query: str,
    top_k: int | None = None,
    fetch_k: int | None = None,
    category: str | None = None,
    use_reranker: bool | None = None,
) -> list[dict]:
    """Return the top_k passages for *query*, best first.

    Each result dict carries the chunk text, its parent section excerpt,
    document metadata, the fused RRF score, original dense/BM25 signals, and a
    ``weak_evidence`` flag so callers can refuse to answer instead of
    hallucinating.
    """
    retrieval_config = load_kb_config().retrieval
    top_k = top_k or retrieval_config.top_k
    fetch_k = fetch_k or retrieval_config.fetch_k
    vs, bm = _load_stores()

    global _backend
    if _backend is None:
        _backend = get_embedding_backend()
    backend = _backend
    if backend.name != vs.backend_name or backend.dim != vs.dim:
        raise KnowledgeBaseNotReady(f"Embedding backend changed (index={vs.backend_name}/{vs.dim}, current={backend.name}/{backend.dim})。请重新构建索引: uv run python -m deerflow.community.kb_search.ingest --all")

    query_vector = backend.embed_query(query)
    vec_hits = vs.search(query_vector, fetch_k, category)
    bm_hits = bm.search(query, fetch_k, category)
    if not vec_hits and not bm_hits:
        return []

    fused: dict[int, float] = {}
    for hits in (vec_hits, bm_hits):
        for rank, (idx, _) in enumerate(hits):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (retrieval_config.rrf_k + rank + 1)

    candidate_count = max(top_k, load_kb_config().reranker.candidate_count)
    ranked = sorted(fused.items(), key=lambda x: -x[1])[:candidate_count]
    results: list[dict] = []
    dense_scores = dict(vec_hits)
    bm25_scores = dict(bm_hits)
    dense_ranks = {idx: rank for rank, (idx, _score) in enumerate(vec_hits, start=1)}
    bm25_ranks = {idx: rank for rank, (idx, _score) in enumerate(bm_hits, start=1)}
    for idx, score in ranked:
        meta = dict(vs.metadatas[idx])
        meta["chunk_id"] = vs.ids[idx]
        meta["_store_index"] = idx
        meta["score"] = round(score, 6)
        meta["dense_score"] = round(dense_scores.get(idx, 0.0), 6)
        meta["bm25_score"] = round(bm25_scores.get(idx, 0.0), 6)
        meta["dense_rank"] = dense_ranks.get(idx)
        meta["bm25_rank"] = bm25_ranks.get(idx)
        evidence_text = " ".join(str(meta.get(key, "")) for key in ("text", "parent_excerpt", "doc_title", "section_path"))
        meta["lexical_score"] = round(bm.lexical_coverage(query, evidence_text), 6)
        meta["weak_evidence"] = _is_weak_evidence(meta, retrieval_config)
        results.append(meta)
    reranker_config = load_kb_config().reranker
    reranking_enabled = reranker_config.backend != "none" if use_reranker is None else use_reranker
    if reranking_enabled:
        global _reranker
        try:
            if _reranker is None:
                _reranker = get_reranker(reranker_config)
            if _reranker is not None:
                results = _reranker.rerank(query, results, top_k)
        except Exception:
            if not reranker_config.fail_open:
                raise
            logger.exception("Reranker failed; returning RRF results")
    results = results[:top_k]
    _attach_context(results, vs, retrieval_config)
    logger.debug("kb_search %r -> %d hits (vec=%d bm25=%d)", query, len(results), len(vec_hits), len(bm_hits))
    return results


def format_results(hits: list[dict]) -> str:
    """Render hits as numbered citation blocks referenced by index number."""
    lines: list[str] = []
    for i, hit in enumerate(hits, start=1):
        marker = " [弱证据]" if hit.get("weak_evidence") else ""
        location = hit.get("source_file") or hit.get("source") or "未知"
        if hit.get("page_number") is not None:
            location += f"，第 {hit['page_number']} 页"
        if hit.get("slide_number") is not None:
            location += f"，第 {hit['slide_number']} 张幻灯片"
        content_label = {
            "table": "表格",
            "ocr": "OCR",
            "image": "图片描述",
        }.get(hit.get("content_type"))
        if content_label:
            location += f"，{content_label}"
        lines.append(f"[{i}] {hit['doc_title']} | {hit['section_path']}{marker} | 来源: {location}\n{hit.get('context_text') or hit['text']}")
    return "\n\n".join(lines)
