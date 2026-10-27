from types import SimpleNamespace

import numpy as np
import pytest

from deerflow.community.kb_search.config import EmbeddingConfig
from deerflow.community.kb_search.embedding import OpenAICompatEmbedding, get_embedding_backend


class FakeEmbeddings:
    def __init__(self, dimensions: list[int] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.dimensions = dimensions or [3]

    def create(self, *, model: str, input: list[str]):
        del model
        self.calls.append(input)
        dim = self.dimensions[min(len(self.calls) - 1, len(self.dimensions) - 1)]
        data = [SimpleNamespace(embedding=[float(i + 1)] * dim) for i, _ in enumerate(input)]
        return SimpleNamespace(data=data)


def test_openai_compatible_embedding_batches_and_prefixes_bge_queries():
    embeddings = FakeEmbeddings()
    backend = OpenAICompatEmbedding(
        base_url="https://example.invalid/v1",
        api_key="secret",
        model="BAAI/bge-m3",
        batch_size=2,
        client=SimpleNamespace(embeddings=embeddings),
    )

    vectors = backend.embed_documents(["a", "b", "c"])
    query = backend.embed_query("共识算法")

    assert vectors.shape == (3, 3)
    assert query.shape == (3,)
    assert embeddings.calls[:2] == [["a", "b"], ["c"]]
    assert embeddings.calls[2][0].endswith("共识算法")
    assert embeddings.calls[2][0] != "共识算法"


def test_openai_compatible_embedding_rejects_dimension_changes():
    embeddings = FakeEmbeddings(dimensions=[3, 4])
    backend = OpenAICompatEmbedding(
        base_url="https://example.invalid/v1",
        api_key="secret",
        model="embedding-model",
        batch_size=1,
        client=SimpleNamespace(embeddings=embeddings),
    )

    with pytest.raises(RuntimeError, match="dimension changed"):
        backend.embed_documents(["a", "b"])


def test_explicit_openai_backend_requires_key(monkeypatch):
    for name in ("KB_EMBEDDING_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="requires KB_EMBEDDING_API_KEY"):
        get_embedding_backend(selection="openai", config=EmbeddingConfig())


def test_explicit_hashing_backend_is_deterministic():
    backend = get_embedding_backend(
        selection="hashing",
        config=EmbeddingConfig(hashing_dim=64),
    )

    first = backend.embed_query("Hyperchain RBFT")
    second = backend.embed_query("Hyperchain RBFT")

    assert first.shape == (64,)
    np.testing.assert_array_equal(first, second)
