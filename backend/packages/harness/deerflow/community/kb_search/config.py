"""Central configuration for knowledge-base ingestion, retrieval and evaluation."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _repo_root() -> Path:
    configured = os.environ.get("KB_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config.yaml").exists():
            return parent
    return current.parents[6]


@dataclass(frozen=True)
class ChunkingConfig:
    max_section_chars: int = 1500
    child_chunk_chars: int = 400
    child_overlap_chars: int = 60
    min_child_chars: int = 20
    parent_excerpt_chars: int = 1200

    def validate(self) -> None:
        if self.child_overlap_chars >= self.child_chunk_chars:
            raise ValueError("KB_CHILD_OVERLAP_CHARS must be smaller than KB_CHILD_CHUNK_CHARS")


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 8
    fetch_k: int = 20
    rrf_k: int = 60
    context_expansion_hits: int = 3
    adjacent_chunk_window: int = 1
    lexical_threshold: float = 0.36
    dense_threshold: float = 0.35
    bm25_threshold: float = 8.0
    consensus_rank: int = 1
    consensus_dense: float = 0.22
    consensus_bm25: float = 6.0


@dataclass(frozen=True)
class EmbeddingConfig:
    backend: str = "auto"
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "BAAI/bge-m3"
    batch_size: int = 32
    timeout_seconds: float = 30.0
    max_retries: int = 3
    hashing_dim: int = 512


@dataclass(frozen=True)
class RerankerConfig:
    backend: str = "none"
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "BAAI/bge-reranker-v2-m3"
    candidate_count: int = 20
    timeout_seconds: float = 30.0
    max_retries: int = 2
    fail_open: bool = True


@dataclass(frozen=True)
class VisionConfig:
    backend: str = "none"
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_image_bytes: int = 8 * 1024 * 1024
    pdf_dpi: int = 144
    max_tokens: int = 1200


@dataclass(frozen=True)
class EvaluationConfig:
    cutoffs: tuple[int, ...] = (5, 10)
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = ""
    judge_model: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_tokens: int = 1200


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    project_root: Path
    corpus_dir: Path
    index_dir: Path
    max_document_bytes: int
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    embedding: EmbeddingConfig
    reranker: RerankerConfig
    evaluation: EvaluationConfig
    vision: VisionConfig = field(default_factory=VisionConfig)
    management_dir: Path | None = None

    def snapshot(self) -> dict:
        payload = asdict(self)
        payload["project_root"] = str(self.project_root)
        payload["corpus_dir"] = str(self.corpus_dir)
        payload["index_dir"] = str(self.index_dir)
        payload["management_dir"] = str(self.management_dir) if self.management_dir is not None else None
        payload["evaluation"]["cutoffs"] = list(self.evaluation.cutoffs)
        return payload


def load_kb_config() -> KnowledgeBaseConfig:
    """Load a fresh immutable config so tests and CLI overrides remain predictable."""
    root = _repo_root()
    chunking = ChunkingConfig(
        max_section_chars=_env_int("KB_MAX_SECTION_CHARS", 1500),
        child_chunk_chars=_env_int("KB_CHILD_CHUNK_CHARS", 400),
        child_overlap_chars=_env_int("KB_CHILD_OVERLAP_CHARS", 60),
        min_child_chars=_env_int("KB_MIN_CHILD_CHARS", 20),
        parent_excerpt_chars=_env_int("KB_PARENT_EXCERPT_CHARS", 1200),
    )
    chunking.validate()
    retrieval = RetrievalConfig(
        top_k=_env_int("KB_TOP_K", 8),
        fetch_k=_env_int("KB_FETCH_K", 20),
        rrf_k=_env_int("KB_RRF_K", 60),
        context_expansion_hits=_env_int("KB_CONTEXT_EXPANSION_HITS", 3),
        adjacent_chunk_window=_env_int("KB_ADJACENT_CHUNK_WINDOW", 1),
        lexical_threshold=_env_float("KB_LEXICAL_THRESHOLD", 0.36),
        dense_threshold=_env_float("KB_DENSE_THRESHOLD", 0.35),
        bm25_threshold=_env_float("KB_BM25_THRESHOLD", 8.0),
        consensus_rank=_env_int("KB_CONSENSUS_RANK", 1),
        consensus_dense=_env_float("KB_CONSENSUS_DENSE", 0.22),
        consensus_bm25=_env_float("KB_CONSENSUS_BM25", 6.0),
    )
    embedding = EmbeddingConfig(
        backend=os.environ.get("KB_EMBEDDING_BACKEND", "auto").strip().lower(),
        base_url=os.environ.get("KB_EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1"),
        model=os.environ.get("KB_EMBEDDING_MODEL", "BAAI/bge-m3"),
        batch_size=_env_int("KB_EMBEDDING_BATCH_SIZE", 32),
        timeout_seconds=_env_float("KB_EMBEDDING_TIMEOUT_SECONDS", 30.0),
        max_retries=int(os.environ.get("KB_EMBEDDING_MAX_RETRIES", "3")),
        hashing_dim=_env_int("KB_HASHING_DIM", 512),
    )
    if embedding.backend not in {"auto", "hashing", "openai"}:
        raise ValueError("KB_EMBEDDING_BACKEND must be auto, hashing or openai")
    reranker = RerankerConfig(
        backend=os.environ.get("KB_RERANKER_BACKEND", "none").strip().lower(),
        base_url=os.environ.get("KB_RERANKER_BASE_URL", embedding.base_url),
        model=os.environ.get("KB_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
        candidate_count=_env_int("KB_RERANKER_CANDIDATES", 20),
        timeout_seconds=_env_float("KB_RERANKER_TIMEOUT_SECONDS", 30.0),
        max_retries=int(os.environ.get("KB_RERANKER_MAX_RETRIES", "2")),
        fail_open=os.environ.get("KB_RERANKER_FAIL_OPEN", "true").lower() not in {"0", "false", "no"},
    )
    if reranker.backend not in {"none", "http"}:
        raise ValueError("KB_RERANKER_BACKEND must be none or http")
    vision = VisionConfig(
        backend=os.environ.get("KB_VISION_BACKEND", "none").strip().lower(),
        base_url=os.environ.get("KB_VISION_BASE_URL", embedding.base_url),
        model=os.environ.get("KB_VISION_MODEL", "").strip(),
        timeout_seconds=_env_float("KB_VISION_TIMEOUT_SECONDS", 60.0),
        max_retries=int(os.environ.get("KB_VISION_MAX_RETRIES", "2")),
        max_image_bytes=_env_int("KB_VISION_MAX_IMAGE_BYTES", 8 * 1024 * 1024),
        pdf_dpi=_env_int("KB_PDF_RENDER_DPI", 144),
        max_tokens=_env_int("KB_VISION_MAX_TOKENS", 1200),
    )
    if vision.backend not in {"none", "openai"}:
        raise ValueError("KB_VISION_BACKEND must be none or openai")
    if vision.max_retries < 0:
        raise ValueError("KB_VISION_MAX_RETRIES must be zero or greater")
    evaluation = EvaluationConfig(
        base_url=os.environ.get("KB_E2E_BASE_URL", embedding.base_url),
        model=os.environ.get("KB_E2E_MODEL", "").strip(),
        judge_model=os.environ.get("KB_E2E_JUDGE_MODEL", "").strip(),
        timeout_seconds=_env_float("KB_E2E_TIMEOUT_SECONDS", 60.0),
        max_retries=int(os.environ.get("KB_E2E_MAX_RETRIES", "2")),
        max_tokens=_env_int("KB_E2E_MAX_TOKENS", 1200),
    )
    if evaluation.max_retries < 0:
        raise ValueError("KB_E2E_MAX_RETRIES must be zero or greater")
    return KnowledgeBaseConfig(
        project_root=root,
        corpus_dir=Path(os.environ.get("KB_CORPUS_DIR", root / "data" / "knowledge_base")).expanduser().resolve(),
        index_dir=Path(os.environ.get("KB_INDEX_DIR", root / "data" / "kb_index")).expanduser().resolve(),
        max_document_bytes=_env_int("KB_MAX_DOCUMENT_BYTES", 10 * 1024 * 1024),
        chunking=chunking,
        retrieval=retrieval,
        embedding=embedding,
        reranker=reranker,
        evaluation=evaluation,
        vision=vision,
        management_dir=Path(os.environ.get("KB_MANAGEMENT_DIR", root / "data" / "kb_management")).expanduser().resolve(),
    )
