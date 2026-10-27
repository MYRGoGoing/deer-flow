"""DeerFlow tool exposing hybrid knowledge-base retrieval to agents."""

from __future__ import annotations

import json
import logging

from langchain.tools import tool

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 8


@tool("kb_search", parse_docstring=True)
def kb_search_tool(query: str, category: str | None = None, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Search the local enterprise knowledge base (Hyperchain product docs).

    ALWAYS call this tool FIRST for questions about Hyperchain, 趣链科技,
    BaaS deployment, smart contracts (HVM/EVM), RBFT consensus, BitXHub
    cross-chain or any internal documentation topic, before answering from
    memory.

    Args:
        query: Search keywords or a natural-language question.
        category: Optional filter by corpus directory: platform, contract-dev, baas, crosschain, api-reference.
        max_results: Maximum number of passages to return.
    """
    config = get_app_config().get_tool_config("kb_search")
    if config is not None:
        max_results = config.model_extra.get("max_results", max_results)  # type: ignore[union-attr]

    from .retriever import KnowledgeBaseNotReady, format_results, hybrid_search

    try:
        hits = hybrid_search(query=query, top_k=max_results, category=category)
    except KnowledgeBaseNotReady as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    except Exception:
        logger.exception("kb_search failed for query %r", query)
        return json.dumps({"error": "知识库检索失败，请查看服务端日志。"}, ensure_ascii=False)

    output = {
        "query": query,
        "total_results": len(hits),
        "formatted": format_results(hits),
        "results": [
            {
                "index": i,
                "doc_title": h["doc_title"],
                "category": h["category"],
                "section_path": h["section_path"],
                "source": h["source"],
                "source_file": h.get("source_file"),
                "file_type": h.get("file_type"),
                "page_number": h.get("page_number"),
                "slide_number": h.get("slide_number"),
                "content_type": h.get("content_type"),
                "version": h.get("version"),
                "text": h.get("context_text") or h["text"],
                "matched_text": h["text"],
                "context_sections": h.get("context_sections", []),
                "score": h["score"],
                "lexical_score": h["lexical_score"],
                "dense_score": h["dense_score"],
                "bm25_score": h["bm25_score"],
                "dense_rank": h["dense_rank"],
                "bm25_rank": h["bm25_rank"],
                "weak_evidence": h["weak_evidence"],
            }
            for i, h in enumerate(hits, start=1)
        ],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)
