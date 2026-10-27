"""Compatibility helpers for knowledge-base filesystem locations."""

from pathlib import Path

from .config import load_kb_config


def repo_root() -> Path:
    return load_kb_config().project_root


def corpus_dir() -> Path:
    return load_kb_config().corpus_dir


def index_dir() -> Path:
    return load_kb_config().index_dir
