"""Parent-child Markdown chunking.

Leaf sections (heading + body) become "parents" providing full context; each
parent is split into small overlapping "children" used as the retrieval unit.
Small chunks keep matching precise, while the parent gives the LLM enough
surrounding text to answer from.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .config import ChunkingConfig, load_kb_config

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    category: str
    source: str
    source_file: str
    file_type: str
    section_path: str
    page_number: int | None
    slide_number: int | None
    content_type: str
    version: str
    parent_id: str
    parent_excerpt: str
    text: str


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        lines = raw.splitlines()
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            for line in lines[1:end]:
                key, sep, value = line.partition(":")
                if sep:
                    meta[key.strip().lower()] = value.strip().strip("'\"")
            body = "\n".join(lines[end + 1 :])
    return meta, body.strip()


def extract_sections(body: str) -> list[tuple[str, str]]:
    """Return ``(section_path, section_text)`` pairs, one per heading leaf."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []

    def flush(buf: list[str], path_stack: list[tuple[int, str]]) -> None:
        text = "\n".join(buf).strip()
        if not text:
            return
        path = " / ".join(title for _, title in path_stack) or "(前言)"
        sections.append((path, text))

    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush(buffer, stack)
            buffer = [line]
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            buffer.append(line)
    flush(buffer, stack)

    if not sections and body.strip():
        sections.append(("(全文)", body.strip()))
    return sections


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paragraphs or ([text.strip()] if text.strip() else [])


def _window(paragraphs: list[str], config: ChunkingConfig) -> list[str]:
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n{para}" if buf else para
        if len(candidate) <= config.child_chunk_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            tail = buf[-config.child_overlap_chars :]
            buf = f"{tail}\n{para}"
        else:
            step = config.child_chunk_chars - config.child_overlap_chars
            for start in range(0, len(para), step):
                piece = para[start : start + config.child_chunk_chars]
                if len(piece) > config.min_child_chars:
                    chunks.append(piece)
            buf = ""
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if len(c.strip()) >= config.min_child_chars]


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def chunk_document(
    doc_id: str,
    title: str,
    category: str,
    source: str,
    body: str,
    config: ChunkingConfig | None = None,
    *,
    source_file: str = "",
    file_type: str = "markdown",
    page_number: int | None = None,
    slide_number: int | None = None,
    content_type: str = "text",
    version: str = "1",
) -> list[Chunk]:
    config = config or load_kb_config().chunking
    chunks: list[Chunk] = []
    for section_path, section_text in extract_sections(body):
        pieces = [section_text]
        if len(section_text) > config.max_section_chars:
            pieces = []
            current: list[str] = []
            size = 0
            for para in _split_paragraphs(section_text):
                if current and size + len(para) > config.max_section_chars:
                    pieces.append("\n\n".join(current))
                    current, size = [], 0
                current.append(para)
                size += len(para)
            if current:
                pieces.append("\n\n".join(current))

        for piece_index, piece in enumerate(pieces):
            parent_id = _hash(f"{doc_id}|{section_path}|{piece_index}")
            base_key = f"{doc_id}|{section_path}|{piece_index}"
            for child_index, child in enumerate(_window(_split_paragraphs(piece), config)):
                chunk_id = _hash(f"{base_key}|{child_index}")
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        doc_title=title,
                        category=category,
                        source=source,
                        source_file=source_file,
                        file_type=file_type,
                        section_path=section_path,
                        page_number=page_number,
                        slide_number=slide_number,
                        content_type=content_type,
                        version=version,
                        parent_id=parent_id,
                        parent_excerpt=piece[: config.parent_excerpt_chars],
                        text=child,
                    )
                )
    return chunks
