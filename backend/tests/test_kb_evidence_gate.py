from deerflow.community.kb_search.config import RetrievalConfig
from deerflow.community.kb_search.retriever import _is_weak_evidence
from deerflow.community.kb_search.stores import BM25Store, informative_query_tokens


def test_informative_query_tokens_removes_question_boilerplate():
    assert informative_query_tokens("Hyperchain 的 Gas 具体怎么计算？") == ["gas", "计算"]


def test_lexical_coverage_weights_direct_evidence():
    store = BM25Store()
    store._tokenized = [
        ["gas", "计费", "模式", "手续费"],
        ["rbft", "共识", "节点"],
        ["私有化", "部署"],
        ["私有化", "部署"],
        ["私有化", "部署"],
        ["私有化", "部署"],
    ]

    supported = store.lexical_coverage("Gas 计费模式如何计算？", "Gas 计费模式包含免费和收费模式")
    unsupported = store.lexical_coverage("企业采购私有化部署能打几折？", "支持私有化部署")

    assert supported > unsupported
    assert supported >= 0.36
    assert unsupported < 0.36


def test_evidence_gate_does_not_trust_dense_similarity_alone():
    config = RetrievalConfig(lexical_threshold=0.36, bm25_threshold=8.0)
    hit = {
        "lexical_score": 0.2,
        "dense_score": 0.92,
        "bm25_score": 3.0,
        "dense_rank": 1,
        "bm25_rank": 1,
    }

    assert _is_weak_evidence(hit, config)


def test_evidence_gate_accepts_lexical_or_sparse_support():
    config = RetrievalConfig(lexical_threshold=0.36, bm25_threshold=8.0)

    assert not _is_weak_evidence({"lexical_score": 0.4, "dense_score": 0.1, "bm25_score": 0.0}, config)
    assert not _is_weak_evidence({"lexical_score": 0.1, "dense_score": 0.1, "bm25_score": 9.0}, config)
