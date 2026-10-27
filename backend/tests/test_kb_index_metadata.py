import json

from deerflow.community.kb_search.config import load_kb_config
from deerflow.community.kb_search.ingest import build_index_metadata, corpus_manifest
from deerflow.community.kb_search.stores import INDEX_SCHEMA_VERSION, VectorStore


def test_corpus_manifest_changes_when_document_content_changes(tmp_path):
    first = tmp_path / "a.md"
    second = tmp_path / "nested" / "b.md"
    second.parent.mkdir()
    first.write_text("alpha", encoding="utf-8")
    second.write_text("beta", encoding="utf-8")

    before = corpus_manifest(tmp_path, [first, second])
    first.write_text("changed", encoding="utf-8")
    after = corpus_manifest(tmp_path, [first, second])

    assert before["sha256"] != after["sha256"]
    assert [item["path"] for item in after["documents"]] == ["a.md", "nested/b.md"]


def test_vector_store_round_trips_index_metadata(tmp_path):
    store = VectorStore()
    store.reset(
        backend_name="hashing-char-ngram-v1",
        dim=4,
        index_metadata={"corpus_manifest_hash": "abc", "chunk_count": 0},
    )
    store.save(tmp_path)

    loaded = VectorStore()
    assert loaded.load(tmp_path)
    assert loaded.index_metadata == {"corpus_manifest_hash": "abc", "chunk_count": 0}
    assert loaded.matrix is not None
    assert loaded.matrix.shape == (0, 4)
    payload = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == INDEX_SCHEMA_VERSION


def test_build_index_metadata_captures_config_and_counts(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    document = corpus / "doc.md"
    document.write_text("# Doc\ncontent", encoding="utf-8")
    monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("KB_CORPUS_DIR", str(corpus))
    monkeypatch.setenv("KB_INDEX_DIR", str(tmp_path / "index"))
    config = load_kb_config()

    metadata = build_index_metadata(
        config,
        [document],
        backend_name="test",
        dim=3,
        chunk_count=2,
    )

    assert metadata["document_count"] == 1
    assert metadata["chunk_count"] == 2
    assert metadata["backend_name"] == "test"
    assert metadata["chunk_config"]["child_chunk_chars"] == 400
    assert metadata["vision_backend"] == "none"
    assert metadata["vision_pdf_dpi"] == 144
    assert len(metadata["corpus_manifest_hash"]) == 64
