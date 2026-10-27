from deerflow.community.kb_search.config import load_kb_config


def test_kb_config_reads_paths_and_tuning_from_environment(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    index = tmp_path / "index"
    management = tmp_path / "management"
    monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("KB_CORPUS_DIR", str(corpus))
    monkeypatch.setenv("KB_INDEX_DIR", str(index))
    monkeypatch.setenv("KB_MANAGEMENT_DIR", str(management))
    monkeypatch.setenv("KB_CHILD_CHUNK_CHARS", "320")
    monkeypatch.setenv("KB_CHILD_OVERLAP_CHARS", "40")
    monkeypatch.setenv("KB_FETCH_K", "30")
    monkeypatch.setenv("KB_CONTEXT_EXPANSION_HITS", "4")
    monkeypatch.setenv("KB_ADJACENT_CHUNK_WINDOW", "2")
    monkeypatch.setenv("KB_LEXICAL_THRESHOLD", "0.42")
    monkeypatch.setenv("KB_EMBEDDING_BACKEND", "hashing")
    monkeypatch.setenv("KB_VISION_BACKEND", "openai")
    monkeypatch.setenv("KB_VISION_MODEL", "Qwen-VL")
    monkeypatch.setenv("KB_PDF_RENDER_DPI", "120")
    monkeypatch.setenv("KB_E2E_MODEL", "Qwen-Chat")
    monkeypatch.setenv("KB_E2E_JUDGE_MODEL", "Qwen-Judge")

    config = load_kb_config()

    assert config.project_root == tmp_path
    assert config.corpus_dir == corpus
    assert config.index_dir == index
    assert config.management_dir == management
    assert config.chunking.child_chunk_chars == 320
    assert config.chunking.child_overlap_chars == 40
    assert config.retrieval.fetch_k == 30
    assert config.retrieval.context_expansion_hits == 4
    assert config.retrieval.adjacent_chunk_window == 2
    assert config.retrieval.lexical_threshold == 0.42
    assert config.embedding.backend == "hashing"
    assert config.vision.backend == "openai"
    assert config.vision.model == "Qwen-VL"
    assert config.vision.pdf_dpi == 120
    assert config.evaluation.model == "Qwen-Chat"
    assert config.evaluation.judge_model == "Qwen-Judge"
    assert config.snapshot()["chunking"]["child_chunk_chars"] == 320


def test_kb_config_rejects_invalid_overlap(monkeypatch):
    monkeypatch.setenv("KB_CHILD_CHUNK_CHARS", "100")
    monkeypatch.setenv("KB_CHILD_OVERLAP_CHARS", "100")

    try:
        load_kb_config()
    except ValueError as exc:
        assert "KB_CHILD_OVERLAP_CHARS" in str(exc)
    else:
        raise AssertionError("invalid chunking config was accepted")
