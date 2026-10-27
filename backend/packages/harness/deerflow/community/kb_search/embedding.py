"""Embedding backends: OpenAI-compatible API with an offline hashing fallback.

The hashing backend keeps the pipeline runnable with zero network access and
zero API keys. Export ``KB_EMBEDDING_API_KEY`` (or ``SILICONFLOW_API_KEY``)
to switch to bge-m3 via any OpenAI-style endpoint. The backend identity is
stored alongside the index so stale embeddings are detected instead of being
silently compared across different vector spaces.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any

import numpy as np

from .config import EmbeddingConfig, load_kb_config

logger = logging.getLogger(__name__)

BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


class EmbeddingBackend:
    name: str = "base"
    dim: int = 0

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        raise NotImplementedError


class HashingEmbedding(EmbeddingBackend):
    """Character n-gram hashing vectors: deterministic and dependency-free."""

    def __init__(self, dim: int = 512) -> None:
        self.name = "hashing-char-ngram-v1"
        self.dim = dim

    def _vectorize(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        cleaned = re.sub(r"\s+", "", text.lower())
        grams = [cleaned[i : i + n] for n in (2, 3) for i in range(max(len(cleaned) - n + 1, 0))]
        if not grams and cleaned:
            grams = [cleaned]
        for gram in grams:
            bucket = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16) % self.dim
            vec[bucket] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        return np.stack([self._vectorize(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._vectorize(text)


class OpenAICompatEmbedding(EmbeddingBackend):
    """Any OpenAI-style ``/embeddings`` endpoint (SiliconFlow, DashScope, ...)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        batch_size: int = 32,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.name = f"openai:{model}"
        self.model = model
        self.batch_size = batch_size
        if client is None:
            from openai import OpenAI  # local import keeps gateway startup light

            client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
        self.client = client
        self._dim: int | None = None

    @property
    def dim(self) -> int:  # type: ignore[override]
        if self._dim is None:
            probe = self.embed_documents(["dim"])
            self._dim = int(probe.shape[1])
        return self._dim

    def _embed_batch(self, batch: list[str]) -> np.ndarray:
        response = self.client.embeddings.create(model=self.model, input=batch)
        vectors = [item.embedding for item in response.data]
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(batch):
            raise RuntimeError(f"Embedding API returned {matrix.shape[0] if matrix.ndim else 0} vectors for a batch of {len(batch)} texts")
        if self._dim is None:
            self._dim = int(matrix.shape[1])
        elif matrix.shape[1] != self._dim:
            raise RuntimeError(f"Embedding dimension changed within one run: {self._dim} -> {matrix.shape[1]}")
        if not np.isfinite(matrix).all():
            raise RuntimeError("Embedding API returned NaN or infinite values")
        return matrix

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        parts = [self._embed_batch(texts[i : i + self.batch_size]) for i in range(0, len(texts), self.batch_size)]
        return np.vstack(parts)

    def embed_query(self, text: str) -> np.ndarray:
        query = BGE_QUERY_PREFIX + text if "bge" in self.model.lower() else text
        return self._embed_batch([query])[0]


def _api_key() -> str | None:
    return os.environ.get("KB_EMBEDDING_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("OPENAI_API_KEY")


def get_embedding_backend(
    selection: str | None = None,
    config: EmbeddingConfig | None = None,
) -> EmbeddingBackend:
    config = config or load_kb_config().embedding
    selection = (selection or config.backend).strip().lower()
    if selection not in {"auto", "hashing", "openai"}:
        raise ValueError(f"Unsupported embedding backend: {selection}")

    api_key = _api_key()
    if selection == "hashing":
        return HashingEmbedding(dim=config.hashing_dim)
    if selection == "openai" and not api_key:
        raise RuntimeError("KB_EMBEDDING_BACKEND=openai requires KB_EMBEDDING_API_KEY (SILICONFLOW_API_KEY and OPENAI_API_KEY are also supported)")
    if not api_key:
        logger.warning("No embedding API key found; falling back to hashing embeddings.")
        return HashingEmbedding(dim=config.hashing_dim)
    logger.info("Using embedding backend %s", f"openai:{config.model}")
    return OpenAICompatEmbedding(
        base_url=config.base_url,
        api_key=api_key,
        model=config.model,
        batch_size=config.batch_size,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
    )
