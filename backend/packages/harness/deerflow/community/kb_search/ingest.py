"""Build and maintain the knowledge-base index from the document corpus.

Usage (from ``backend/``):

    uv run python -m deerflow.community.kb_search.ingest --all
    uv run python -m deerflow.community.kb_search.ingest --doc ../data/knowledge_base/platform/rbft-consensus.md
    uv run python -m deerflow.community.kb_search.ingest --remove ../data/knowledge_base/platform/old.md

``--all`` rebuilds from scratch (safe to re-run); ``--doc`` upserts one file;
``--remove`` drops a document's chunks. Incremental modes keep the rest of the
index untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .chunker import Chunk, chunk_document
from .config import KnowledgeBaseConfig, load_kb_config
from .embedding import get_embedding_backend
from .parsers import SUPPORTED_EXTENSIONS, ParsedSource, parse_source
from .stores import BM25Store, VectorStore
from .vision import get_vision_extractor

logger = logging.getLogger(__name__)
INDEX_SCHEMA_VERSION = "2"


def _doc_id(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]


def iter_corpus_files(root: Path, *, allow_empty: bool = False) -> list[Path]:
    if not root.exists():
        raise SystemExit(f"语料目录不存在: {root}")
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and p.name.upper() != "README.MD")
    if not files and not allow_empty:
        raise SystemExit(f"语料目录中没有可解析文档: {root}")
    return files


def corpus_manifest(root: Path, files: list[Path] | None = None) -> dict:
    files = iter_corpus_files(root) if files is None else files
    documents = []
    digest = hashlib.sha256()
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        documents.append({"path": relative_path, "sha256": content_hash})
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return {"sha256": digest.hexdigest(), "documents": documents}


def _git_revision(project_root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_index_metadata(
    config: KnowledgeBaseConfig,
    files: list[Path],
    *,
    backend_name: str,
    dim: int,
    chunk_count: int,
) -> dict:
    manifest = corpus_manifest(config.corpus_dir, files)
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_revision": _git_revision(config.project_root),
        "corpus_manifest_hash": manifest["sha256"],
        "documents": manifest["documents"],
        "document_count": len(files),
        "chunk_count": chunk_count,
        "backend_name": backend_name,
        "dim": dim,
        "chunk_config": config.snapshot()["chunking"],
        "vision_backend": ("none" if config.vision.backend == "none" else f"{config.vision.backend}:{config.vision.model}"),
        "vision_pdf_dpi": config.vision.pdf_dpi,
    }


def parse_document(path: Path, corpus_root: Path) -> tuple[str, str, str, str, str]:
    """Return ``(doc_id, title, category, source, body)`` for a corpus file."""
    parsed = parse_source(path, corpus_root)
    body = "\n\n".join(f"# {section.heading}\n{section.text}" if section.heading else section.text for section in parsed.sections)
    return _doc_id(path, corpus_root), parsed.title, parsed.category, parsed.source, body


def chunks_for_source(
    doc_id: str,
    parsed: ParsedSource,
    config: KnowledgeBaseConfig,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in parsed.sections:
        body = f"# {section.heading}\n{section.text}" if section.heading else section.text
        chunks.extend(
            chunk_document(
                doc_id,
                parsed.title,
                parsed.category,
                parsed.source,
                body,
                config.chunking,
                source_file=parsed.source_file,
                file_type=parsed.file_type,
                page_number=section.page_number,
                slide_number=section.slide_number,
                content_type=section.content_type,
                version=parsed.version,
            )
        )
    return chunks


def ingest_all(embedding_backend: str | None = None) -> dict:
    config = load_kb_config()
    corpus_root = config.corpus_dir
    files = iter_corpus_files(corpus_root)
    backend = get_embedding_backend(selection=embedding_backend, config=config.embedding)
    vision_extractor = get_vision_extractor(config.vision)

    vs, bm = VectorStore(), BM25Store()
    vs.reset(backend_name=backend.name, dim=getattr(backend, "dim"))
    bm.reset()

    total_chunks = 0
    for i, path in enumerate(files, start=1):
        parsed = parse_source(path, corpus_root, vision_extractor=vision_extractor)
        chunks = chunks_for_source(_doc_id(path, corpus_root), parsed, config)
        if not chunks:
            logger.warning("跳过无有效内容的文档: %s", path)
            continue
        vectors = backend.embed_documents([c.text for c in chunks])
        vs.add(chunks, vectors)
        bm.add(chunks)
        total_chunks += len(chunks)
        print(f"[{i}/{len(files)}] {path.relative_to(corpus_root)}: {len(chunks)} chunks")

    vs.index_metadata = build_index_metadata(
        config,
        files,
        backend_name=backend.name,
        dim=backend.dim,
        chunk_count=total_chunks,
    )
    vs.save(config.index_dir)
    bm.save(config.index_dir)
    print(f"\n入库完成: {len(files)} 篇文档, {total_chunks} 个分块, embedding={backend.name}(dim={getattr(backend, 'dim')}) -> {config.index_dir}")
    return vs.index_metadata


def upsert_doc(path: Path) -> None:
    config = load_kb_config()
    corpus_root = config.corpus_dir
    path = path.resolve()
    backend = get_embedding_backend()
    vision_extractor = get_vision_extractor(config.vision)
    vs, bm = VectorStore(), BM25Store()
    if not vs.load():
        vs.reset(backend_name=backend.name, dim=getattr(backend, "dim"))
    elif vs.backend_name != backend.name or vs.dim != backend.dim:
        raise RuntimeError(f"Embedding backend changed (index={vs.backend_name}/{vs.dim}, current={backend.name}/{backend.dim}); rebuild with ingest --all")
    bm.load()

    doc_id = _doc_id(path, corpus_root)
    parsed = parse_source(path, corpus_root, vision_extractor=vision_extractor)
    vs.remove_doc(doc_id)
    bm.remove_doc(doc_id)
    chunks = chunks_for_source(doc_id, parsed, config)
    vectors = backend.embed_documents([c.text for c in chunks])
    vs.add(chunks, vectors)
    bm.add(chunks)
    files = iter_corpus_files(corpus_root)
    vs.index_metadata = build_index_metadata(
        config,
        files,
        backend_name=backend.name,
        dim=backend.dim,
        chunk_count=len(vs.ids),
    )
    vs.save(config.index_dir)
    bm.save(config.index_dir)
    print(f"已更新文档 {path.name}: {len(chunks)} 个分块")


def remove_doc(path: Path) -> None:
    config = load_kb_config()
    corpus_root = config.corpus_dir
    path = path.resolve()
    doc_id = _doc_id(path, corpus_root)
    vs, bm = VectorStore(), BM25Store()
    loaded_vs, loaded_bm = vs.load(), bm.load()
    removed = 0
    if loaded_vs:
        removed += vs.remove_doc(doc_id)
    if loaded_bm:
        removed += bm.remove_doc(doc_id)
    if loaded_vs:
        files = iter_corpus_files(corpus_root, allow_empty=True)
        vs.index_metadata = build_index_metadata(
            config,
            files,
            backend_name=vs.backend_name,
            dim=vs.dim,
            chunk_count=len(vs.ids),
        )
    vs.save(config.index_dir)
    bm.save(config.index_dir)
    print(f"已从索引移除 {path.name}: {removed} 个分块")


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge-base index builder")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="rebuild the full index from the corpus directory")
    group.add_argument("--doc", type=Path, help="upsert one supported document")
    group.add_argument("--remove", type=Path, help="remove one supported document from the index")
    parser.add_argument(
        "--embedding-backend",
        choices=("auto", "hashing", "openai"),
        help="override KB_EMBEDDING_BACKEND for this build",
    )
    parser.add_argument("--metadata-output", type=Path, help="write the index manifest as JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.all:
        metadata = ingest_all(args.embedding_backend)
        if args.metadata_output:
            args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
            args.metadata_output.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    elif args.doc:
        upsert_doc(args.doc)
    elif args.remove:
        remove_doc(args.remove)


if __name__ == "__main__":
    main()
