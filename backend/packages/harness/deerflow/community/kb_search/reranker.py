"""Optional cross-encoder reranking through a SiliconFlow-compatible HTTP API."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from .config import RerankerConfig, load_kb_config

logger = logging.getLogger(__name__)


class Reranker:
    name: str = "base"

    def rerank(self, query: str, hits: list[dict], top_n: int) -> list[dict]:
        raise NotImplementedError


class HTTPReranker(Reranker):
    def __init__(
        self,
        config: RerankerConfig,
        api_key: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.name = f"http:{config.model}"
        self.endpoint = config.base_url.rstrip("/") + "/rerank"
        self.client = client or httpx.Client(
            timeout=config.timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def _request(self, query: str, documents: list[str], top_n: int) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.post(
                    self.endpoint,
                    json={
                        "model": self.config.model,
                        "query": query,
                        "documents": documents,
                        "top_n": top_n,
                        "return_documents": False,
                    },
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                time.sleep(min(0.25 * (2**attempt), 2.0))
        raise RuntimeError("Reranker request failed") from last_error

    def rerank(self, query: str, hits: list[dict], top_n: int) -> list[dict]:
        if not hits:
            return []
        payload = self._request(query, [hit["text"] for hit in hits], min(top_n, len(hits)))
        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError("Reranker response does not contain a results list")

        reranked: list[dict] = []
        seen: set[int] = set()
        for rank, item in enumerate(results, start=1):
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or not 0 <= index < len(hits) or index in seen:
                raise RuntimeError("Reranker returned an invalid document index")
            if not isinstance(score, (int, float)):
                raise RuntimeError("Reranker returned an invalid relevance score")
            hit = dict(hits[index])
            hit["rerank_score"] = round(float(score), 6)
            hit["rerank_rank"] = rank
            reranked.append(hit)
            seen.add(index)
        return reranked


def get_reranker(config: RerankerConfig | None = None) -> Reranker | None:
    config = config or load_kb_config().reranker
    if config.backend == "none":
        return None
    api_key = os.environ.get("KB_RERANKER_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("KB_EMBEDDING_API_KEY")
    if not api_key:
        raise RuntimeError("KB_RERANKER_BACKEND=http requires KB_RERANKER_API_KEY")
    return HTTPReranker(config, api_key)
