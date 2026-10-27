"""Persistent storage for the knowledge-base index.

``VectorStore`` keeps normalized chunk vectors in an .npz matrix plus a JSON
metadata sidecar; ``BM25Store`` pickles jieba-tokenized corpora for rank_bm25.
Both are plain-file stores sized for thousands of chunks. If the corpus grows
into the hundreds of thousands, swap these classes for Qdrant/pgvector behind
the same add/search interface used by ``retriever.hybrid_search``.
"""

from __future__ import annotations

import json
import math
import pickle
import re
from collections import Counter
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .chunker import Chunk
from .paths import index_dir

VECTOR_FILE = "vectors.npz"
META_FILE = "meta.json"
BM25_FILE = "bm25.pkl"
INDEX_SCHEMA_VERSION = "2"

_QUESTION_STOPWORDS = frozenset(
    "的 了 是 在 和 与 或 什么 哪些 哪个 哪种 怎么 如何 是否 能否 可以 支持 需要 有 "
    "作用 时候 当前 现在 具体 多少 哪里 哪 两种 一个 几个 中 下 里 对 上 为 主要 用于 "
    "处于 包括 应该 发生 负责 解决 问题 使用 工作 进行 通过 全称 定位 平台 "
    "hyperchain".split()
)
_PUNCTUATION_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    import jieba

    return [token for token in jieba.lcut(text.lower()) if token.strip()]


def informative_query_tokens(text: str) -> list[str]:
    """Return stable content words for model-independent evidence gating."""
    result: list[str] = []
    for raw_token in tokenize(text):
        token = raw_token.strip().lower()
        if not token or token in _QUESTION_STOPWORDS or _PUNCTUATION_RE.fullmatch(token) or (len(token) == 1 and not token.isascii()):
            continue
        if token not in result:
            result.append(token)
    return result


class VectorStore:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.metadatas: list[dict] = []
        self.matrix: np.ndarray | None = None
        self.backend_name: str = ""
        self.dim: int = 0
        self.index_metadata: dict = {}

    # -- persistence -------------------------------------------------------

    def load(self, root: Path | None = None) -> bool:
        root = root or index_dir()
        vec_path, meta_path = root / VECTOR_FILE, root / META_FILE
        if not (vec_path.exists() and meta_path.exists()):
            return False
        with open(meta_path, encoding="utf-8") as f:
            payload = json.load(f)
        data = np.load(vec_path)
        self.ids = payload["ids"]
        self.metadatas = payload["metadatas"]
        self.backend_name = payload.get("backend_name", "")
        self.dim = int(payload.get("dim", 0))
        self.index_metadata = payload.get("index_metadata", {})
        self.matrix = data["matrix"].astype(np.float32)
        return True

    def save(self, root: Path | None = None) -> None:
        root = root or index_dir()
        root.mkdir(parents=True, exist_ok=True)
        matrix = self.matrix if self.matrix is not None else np.empty((0, self.dim), np.float32)
        np.savez_compressed(root / VECTOR_FILE, matrix=matrix)
        with open(root / META_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ids": self.ids,
                    "metadatas": self.metadatas,
                    "backend_name": self.backend_name,
                    "dim": self.dim,
                    "schema_version": INDEX_SCHEMA_VERSION,
                    "index_metadata": self.index_metadata,
                },
                f,
                ensure_ascii=False,
            )

    # -- mutation ----------------------------------------------------------

    def reset(self, backend_name: str, dim: int, index_metadata: dict | None = None) -> None:
        self.ids = []
        self.metadatas = []
        self.matrix = np.empty((0, dim), dtype=np.float32)
        self.backend_name = backend_name
        self.dim = dim
        self.index_metadata = dict(index_metadata or {})

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) == 0:
            return
        assert self.matrix is not None and vectors.shape[1] == self.dim
        self.ids.extend(c.chunk_id for c in chunks)
        self.metadatas.extend(
            {
                "doc_id": c.doc_id,
                "doc_title": c.doc_title,
                "category": c.category,
                "source": c.source,
                "source_file": c.source_file,
                "file_type": c.file_type,
                "section_path": c.section_path,
                "page_number": c.page_number,
                "slide_number": c.slide_number,
                "content_type": c.content_type,
                "version": c.version,
                "parent_excerpt": c.parent_excerpt,
                "text": c.text,
            }
            for c in chunks
        )
        self.matrix = np.vstack([self.matrix, vectors.astype(np.float32)])

    def remove_doc(self, doc_id: str) -> int:
        keep = [i for i, m in enumerate(self.metadatas) if m["doc_id"] != doc_id]
        removed = len(self.ids) - len(keep)
        if removed == 0 or self.matrix is None:
            return removed
        self.ids = [self.ids[i] for i in keep]
        self.metadatas = [self.metadatas[i] for i in keep]
        self.matrix = self.matrix[keep]
        return removed

    # -- search ------------------------------------------------------------

    def search(self, query_vec: np.ndarray, top_k: int, category: str | None = None) -> list[tuple[int, float]]:
        if self.matrix is None or self.matrix.shape[0] == 0:
            return []
        norm = np.linalg.norm(query_vec)
        qv = query_vec / norm if norm > 0 else query_vec
        sims = self.matrix @ qv
        candidates = range(len(self.ids))
        if category:
            candidates = [i for i in candidates if self.metadatas[i]["category"] == category]
        ranked = sorted(((i, float(sims[i])) for i in candidates), key=lambda x: -x[1])
        return ranked[:top_k]


class BM25Store:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.metadatas: list[dict] = []
        self._tokenized: list[list[str]] = []
        self._engine: BM25Okapi | None = None
        self._document_frequency: Counter[str] | None = None

    # -- persistence -------------------------------------------------------

    def load(self, root: Path | None = None) -> bool:
        path = (root or index_dir()) / BM25_FILE
        if not path.exists():
            return False
        with open(path, "rb") as f:
            payload = pickle.load(f)
        self.ids = payload["ids"]
        self.metadatas = payload["metadatas"]
        self._tokenized = payload["tokenized"]
        self._engine = None
        self._document_frequency = None
        return True

    def save(self, root: Path | None = None) -> None:
        root = root or index_dir()
        root.mkdir(parents=True, exist_ok=True)
        with open(root / BM25_FILE, "wb") as f:
            pickle.dump(
                {"ids": self.ids, "metadatas": self.metadatas, "tokenized": self._tokenized},
                f,
            )

    # -- mutation ----------------------------------------------------------

    def reset(self) -> None:
        self.ids = []
        self.metadatas = []
        self._tokenized = []
        self._engine = None
        self._document_frequency = None

    def add(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self.ids.append(chunk.chunk_id)
            self._tokenized.append(tokenize(chunk.text))
            self.metadatas.append(
                {
                    "doc_id": chunk.doc_id,
                    "doc_title": chunk.doc_title,
                    "category": chunk.category,
                    "source_file": chunk.source_file,
                    "file_type": chunk.file_type,
                    "section_path": chunk.section_path,
                    "page_number": chunk.page_number,
                    "slide_number": chunk.slide_number,
                    "content_type": chunk.content_type,
                    "version": chunk.version,
                }
            )
        self._engine = None
        self._document_frequency = None

    def remove_doc(self, doc_id: str) -> int:
        keep = [i for i, m in enumerate(self.metadatas) if m["doc_id"] != doc_id]
        removed = len(self.ids) - len(keep)
        if removed == 0:
            return 0
        self.ids = [self.ids[i] for i in keep]
        self.metadatas = [self.metadatas[i] for i in keep]
        self._tokenized = [self._tokenized[i] for i in keep]
        self._engine = None
        self._document_frequency = None
        return removed

    # -- search ------------------------------------------------------------

    @property
    def engine(self) -> BM25Okapi | None:
        if self._engine is None and self._tokenized:
            self._engine = BM25Okapi(self._tokenized)
        return self._engine

    def search(self, query: str, top_k: int, category: str | None = None) -> list[tuple[int, float]]:
        engine = self.engine
        if engine is None:
            return []
        scores = engine.get_scores(tokenize(query))
        candidates = range(len(self.ids))
        if category:
            candidates = [i for i in candidates if self.metadatas[i]["category"] == category]
        ranked = sorted(((i, float(scores[i])) for i in candidates), key=lambda x: -x[1])
        return [(i, s) for i, s in ranked[:top_k] if s > 0]

    def lexical_coverage(self, query: str, evidence: str) -> float:
        """Measure how much of a question's informative vocabulary is evidenced.

        Terms rare in the corpus receive more weight, while query boilerplate is
        ignored. This is deliberately independent of the dense model so a high
        semantic similarity alone cannot turn an out-of-scope question into
        apparently strong evidence.
        """
        query_tokens = informative_query_tokens(query)
        if not query_tokens:
            return 0.0
        if self._document_frequency is None:
            self._document_frequency = Counter(token for document in self._tokenized for token in set(document))
        evidence_tokens = set(tokenize(evidence))
        corpus_size = len(self._tokenized)
        weights = {token: math.log((corpus_size + 1) / (self._document_frequency.get(token, 0) + 1)) + 1 for token in query_tokens}
        total_weight = sum(weights.values())
        if total_weight == 0:
            return 0.0
        covered = sum(weight for token, weight in weights.items() if token in evidence_tokens)
        return covered / total_weight
