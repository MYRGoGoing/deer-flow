# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "fastapi>=0.115,<1",
#   "fastembed==0.7.4",
#   "flashrank==0.2.10",
#   "uvicorn[standard]>=0.34,<1",
# ]
# ///
"""Run lightweight local ONNX embedding and reranking APIs for KB evaluation."""

from __future__ import annotations

import argparse
import importlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_ALIAS = "local/bge-small-zh-v1.5"
EMBEDDING_URL = (
    "https://storage.googleapis.com/qdrant-fastembed/"
    "fast-bge-small-zh-v1.5.tar.gz"
)
RERANKER_MODEL = "ms-marco-MultiBERT-L-12"
RERANKER_MIRROR = "https://hf-mirror.com/prithivida/flashrank/resolve/main/{}.zip"


class EmbeddingRequest(BaseModel):
    model: str = EMBEDDING_MODEL
    input: str | list[str]


class RerankRequestBody(BaseModel):
    model: str = RERANKER_MODEL
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1, max_length=100)
    top_n: int | None = Field(default=None, ge=1)
    return_documents: bool = False


class Runtime:
    def __init__(self, cache_dir: Path, threads: int, enable_reranker: bool) -> None:
        self.cache_dir = cache_dir
        self.threads = threads
        self.enable_reranker = enable_reranker
        self.embedding: Any | None = None
        self.reranker: Any | None = None

    def load(self) -> None:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            TextEmbedding.add_custom_model(
                model=EMBEDDING_ALIAS,
                pooling=PoolingType.CLS,
                normalization=True,
                sources=ModelSource(
                    hf=None,
                    url=EMBEDDING_URL,
                    _deprecated_tar_struct=True,
                ),
                dim=512,
                model_file="model_optimized.onnx",
                description="Local Chinese BGE embedding served through ONNX Runtime",
                license="MIT",
                size_in_gb=0.09,
            )
        except ValueError as exc:
            if "already registered" not in str(exc):
                raise
        self.embedding = TextEmbedding(
            model_name=EMBEDDING_ALIAS,
            cache_dir=str(self.cache_dir),
            threads=self.threads,
        )

        if self.enable_reranker:
            ranker_module = importlib.import_module("flashrank.Ranker")
            ranker_module.model_url = RERANKER_MIRROR
            from flashrank import Ranker

            self.reranker = Ranker(
                model_name=RERANKER_MODEL,
                cache_dir=str(self.cache_dir / "flashrank"),
                max_length=512,
                log_level="WARNING",
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embedding is None:
            raise RuntimeError("embedding model is not loaded")
        vectors = self.embedding.embed(texts, batch_size=min(32, len(texts)))
        return [np.asarray(vector, dtype=np.float32).tolist() for vector in vectors]

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[dict]:
        if self.reranker is None:
            raise RuntimeError("reranker is disabled")
        from flashrank import RerankRequest

        passages = [{"id": index, "text": text} for index, text in enumerate(documents)]
        ranked = self.reranker.rerank(RerankRequest(query=query, passages=passages))
        return [
            {"index": int(item["id"]), "relevance_score": float(item["score"])}
            for item in ranked[:top_n]
        ]


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        runtime.load()
        yield

    app = FastAPI(title="DeerFlow KB Local Model Service", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ready",
            "embedding_model": EMBEDDING_MODEL,
            "reranker_model": RERANKER_MODEL if runtime.reranker is not None else None,
        }

    @app.get("/v1/models")
    def models() -> dict:
        names = [EMBEDDING_MODEL]
        if runtime.reranker is not None:
            names.append(RERANKER_MODEL)
        return {"object": "list", "data": [{"id": name, "object": "model"} for name in names]}

    @app.post("/v1/embeddings")
    def embeddings(request: EmbeddingRequest) -> dict:
        texts = [request.input] if isinstance(request.input, str) else request.input
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise HTTPException(status_code=400, detail="input must contain non-empty strings")
        if len(texts) > 256:
            raise HTTPException(status_code=400, detail="at most 256 inputs are allowed")
        vectors = runtime.embed(texts)
        return {
            "object": "list",
            "model": EMBEDDING_MODEL,
            "data": [
                {"object": "embedding", "index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ],
            "usage": {"prompt_tokens": sum(len(text) for text in texts), "total_tokens": sum(len(text) for text in texts)},
        }

    @app.post("/v1/rerank")
    def rerank(request: RerankRequestBody) -> dict:
        if runtime.reranker is None:
            raise HTTPException(status_code=503, detail="reranker is disabled")
        top_n = min(request.top_n or len(request.documents), len(request.documents))
        results = runtime.rerank(request.query, request.documents, top_n)
        if request.return_documents:
            for result in results:
                result["document"] = {"text": request.documents[result["index"]]}
        return {"id": "local-rerank", "results": results}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(os.environ.get("KB_LOCAL_MODEL_CACHE", "data/model_cache")),
    )
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--no-reranker", action="store_true")
    args = parser.parse_args()
    if args.threads <= 0:
        parser.error("--threads must be greater than zero")

    import uvicorn

    uvicorn.run(
        create_app(Runtime(args.cache_dir.resolve(), args.threads, not args.no_reranker)),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
