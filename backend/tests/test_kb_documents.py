import pytest

from deerflow.community.kb_search import documents


def test_resolve_document_path_rejects_escape_attempts(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_CORPUS_DIR", str(tmp_path))

    with pytest.raises(documents.DocumentValidationError, match="分类"):
        documents.resolve_document_path("unknown", "doc.md")
    with pytest.raises(documents.DocumentValidationError, match="文档类型"):
        documents.resolve_document_path("platform", "doc.txt")

    for filename in ("guide.md", "manual.pdf", "slides.pptx", "policy.docx"):
        assert documents.resolve_document_path("platform", filename) == (tmp_path / "platform" / filename)

    # Basenames are intentional: ../doc.md becomes doc.md inside the category.
    assert documents.resolve_document_path("platform", "../doc.md") == (tmp_path / "platform" / "doc.md")


def test_resolve_document_path_rejects_symlinked_category(tmp_path, monkeypatch):
    corpus_root = tmp_path / "corpus"
    outside = tmp_path / "outside"
    corpus_root.mkdir()
    outside.mkdir()
    (corpus_root / "platform").symlink_to(outside)
    monkeypatch.setenv("KB_CORPUS_DIR", str(corpus_root))

    with pytest.raises(documents.DocumentValidationError, match="分类路径不安全"):
        documents.resolve_document_path("platform", "doc.md")


def test_replace_and_index_document_writes_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_CORPUS_DIR", str(tmp_path))
    monkeypatch.setenv("KB_MANAGEMENT_DIR", str(tmp_path / ".management"))
    indexed = []
    monkeypatch.setattr(documents, "upsert_doc", lambda path: indexed.append(path))

    destination = documents.replace_and_index_document("platform", "new-guide.md", b"# New guide\n")

    assert destination == tmp_path / "platform" / "new-guide.md"
    assert destination.read_text(encoding="utf-8") == "# New guide\n"
    assert indexed == [destination]
    assert not list((tmp_path / "platform").glob(".kb-upload-*"))


def test_replace_and_index_document_rolls_back_new_file_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_CORPUS_DIR", str(tmp_path))
    monkeypatch.setenv("KB_MANAGEMENT_DIR", str(tmp_path / ".management"))
    removed = []

    def fail_index(path):
        raise RuntimeError("embedding failed")

    def remove(path):
        removed.append(path)

    monkeypatch.setattr(documents, "upsert_doc", fail_index)
    monkeypatch.setattr(documents, "remove_doc", remove)

    with pytest.raises(RuntimeError, match="embedding failed"):
        documents.replace_and_index_document("platform", "bad.md", b"# Bad")

    assert not (tmp_path / "platform" / "bad.md").exists()
    assert removed == [tmp_path / "platform" / "bad.md"]
