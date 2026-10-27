from types import SimpleNamespace

import pytest

from deerflow.community.kb_search.config import RerankerConfig
from deerflow.community.kb_search.reranker import HTTPReranker, get_reranker


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_http_reranker_maps_scores_back_to_hits():
    requests = []

    def post(url, json):
        requests.append((url, json))
        return FakeResponse({"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]})

    reranker = HTTPReranker(
        RerankerConfig(backend="http", model="reranker", max_retries=0),
        "secret",
        client=SimpleNamespace(post=post),
    )
    hits = [{"text": "first"}, {"text": "second"}]

    result = reranker.rerank("query", hits, 2)

    assert [hit["text"] for hit in result] == ["second", "first"]
    assert result[0]["rerank_score"] == 0.9
    assert requests[0][1]["documents"] == ["first", "second"]


def test_http_reranker_rejects_invalid_indices():
    reranker = HTTPReranker(
        RerankerConfig(backend="http", max_retries=0),
        "secret",
        client=SimpleNamespace(post=lambda *_args, **_kwargs: FakeResponse({"results": [{"index": 4, "relevance_score": 0.9}]})),
    )

    with pytest.raises(RuntimeError, match="invalid document index"):
        reranker.rerank("query", [{"text": "only"}], 1)


def test_get_reranker_requires_a_dedicated_key(monkeypatch):
    for name in ("KB_RERANKER_API_KEY", "SILICONFLOW_API_KEY", "KB_EMBEDDING_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="requires KB_RERANKER_API_KEY"):
        get_reranker(RerankerConfig(backend="http"))
