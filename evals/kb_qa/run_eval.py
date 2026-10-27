"""Run retrieval-only quality checks over the knowledge-base golden set."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from deerflow.community.kb_search.config import load_kb_config
from deerflow.community.kb_search.embedding import get_embedding_backend
from deerflow.community.kb_search.paths import index_dir
from deerflow.community.kb_search.retriever import hybrid_search
from deerflow.community.kb_search.stores import BM25Store, VectorStore

EVAL_DIR = Path(__file__).resolve().parent
CUTOFFS = load_kb_config().evaluation.cutoffs


def load_golden_set() -> list[dict]:
    with open(EVAL_DIR / "golden_set.json", encoding="utf-8") as f:
        items = json.load(f)
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("golden_set.json contains duplicate ids")
    return items


def expected_doc_id(source: str) -> str:
    """Mirror the stable relative-path hash used by the ingest CLI."""
    return hashlib.sha1(source.replace("\\", "/").encode("utf-8")).hexdigest()[:12]


def dense_search(
    vector_store: VectorStore,
    query_vector,
    top_k: int,
) -> list[dict]:
    """Run the vector half of the pipeline without BM25 or RRF fusion."""
    # Do not use the golden set category as a routing label; users normally do
    # not provide it, so retrieval should be measured across the whole corpus.
    hits = vector_store.search(query_vector, top_k, None)
    return [dict(vector_store.metadatas[index]) for index, _score in hits]


def bm25_search(bm25_store: BM25Store, query: str, top_k: int) -> list[dict]:
    hits = bm25_store.search(query, top_k, None)
    return [dict(bm25_store.metadatas[index]) for index, _score in hits]


def is_all_weak(hits: list[dict], cutoff: int) -> bool:
    top = hits[:cutoff]
    return bool(top) and all(hit.get("weak_evidence", False) for hit in top)


def evaluate_item(
    item: dict,
    vector_store: VectorStore,
    bm25_store: BM25Store,
    query_vector,
    config_names: tuple[str, ...],
) -> dict:
    expected = None if item.get("unanswerable") else expected_doc_id(item["source"])
    started = time.perf_counter()
    dense_hits = dense_search(vector_store, query_vector, max(CUTOFFS))
    dense_latency = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    bm25_hits = bm25_search(bm25_store, item["question"], max(CUTOFFS))
    bm25_latency = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    hybrid_rrf_hits = hybrid_search(
        query=item["question"],
        top_k=max(CUTOFFS),
        category=None,
        use_reranker=False,
    )
    hybrid_rrf_latency = (time.perf_counter() - started) * 1000

    hits_by_config = {
        "dense": dense_hits,
        "bm25": bm25_hits,
        "hybrid_rrf": hybrid_rrf_hits,
    }
    latency_by_config = {
        "dense": dense_latency,
        "bm25": bm25_latency,
        "hybrid_rrf": hybrid_rrf_latency,
    }
    if "hybrid_rerank" in config_names:
        started = time.perf_counter()
        hits_by_config["hybrid_rerank"] = hybrid_search(
            query=item["question"],
            top_k=max(CUTOFFS),
            category=None,
            use_reranker=True,
        )
        latency_by_config["hybrid_rerank"] = (time.perf_counter() - started) * 1000

    metrics: dict[str, dict] = {}
    for config in config_names:
        hits = hits_by_config[config]
        ranks = [
            position + 1
            for position, hit in enumerate(hits)
            if expected and hit.get("doc_id") == expected
        ]
        for cutoff in CUTOFFS:
            relevant = sum(hit.get("doc_id") == expected for hit in hits[:cutoff])
            metrics[f"{config}@{cutoff}"] = {
                # Document-level recall: any passage from the source doc counts.
                "recall": int(bool(relevant)),
                "precision": relevant / cutoff,
                "rank": min(ranks) if ranks else None,
            }

    gate_hits = hits_by_config.get("hybrid_rerank", hybrid_rrf_hits)
    refusal_predicted = is_all_weak(gate_hits, max(CUTOFFS))
    refusal_correct = refusal_predicted == bool(item.get("unanswerable"))
    return {
        "metrics": metrics,
        "refusal_predicted": refusal_predicted,
        "refusal_correct": refusal_correct,
        "latency_ms": latency_by_config,
    }


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]


def aggregate_metrics(
    items: list[dict],
    rows: list[dict],
    latencies: dict[str, list[float]],
    config_names: tuple[str, ...],
) -> dict:
    answerable_count = sum(not item.get("unanswerable") for item in items)
    unanswerable_count = len(items) - answerable_count
    totals = defaultdict(float)
    for row in rows:
        for config in config_names:
            for cutoff in CUTOFFS:
                metric = row["metrics"][f"{config}@{cutoff}"]
                totals[f"{config}_recall@{cutoff}"] += metric["recall"]
                totals[f"{config}_precision@{cutoff}"] += metric["precision"]
        if row["item"].get("unanswerable"):
            totals["refusal_correct"] += int(row["refusal_correct"])
        else:
            totals["answer_retained"] += int(not row["refusal_predicted"])

    configs = {}
    for name in config_names:
        configs[name] = {
            **{
                f"recall@{cutoff}": totals[f"{name}_recall@{cutoff}"] / answerable_count
                for cutoff in CUTOFFS
            },
            **{
                f"precision@{cutoff}": totals[f"{name}_precision@{cutoff}"] / answerable_count
                for cutoff in CUTOFFS
            },
            "latency_p50_ms": percentile(latencies[name], 0.50),
            "latency_p95_ms": percentile(latencies[name], 0.95),
        }
    gate_correct = totals["refusal_correct"] + totals["answer_retained"]
    return {
        "question_count": len(items),
        "answerable_count": answerable_count,
        "unanswerable_count": unanswerable_count,
        "configs": configs,
        "evidence_gate": {
            "answerable_retention": totals["answer_retained"] / answerable_count,
            "unanswerable_refusal_accuracy": (
                totals["refusal_correct"] / unanswerable_count if unanswerable_count else 0.0
            ),
            "accuracy": gate_correct / len(items),
        },
    }


def render_report(
    items: list[dict],
    rows: list[dict],
    latencies: dict[str, list[float]],
    config_names: tuple[str, ...],
) -> str:
    answerable_count = sum(not item.get("unanswerable") for item in items)
    unanswerable_count = len(items) - answerable_count
    totals = defaultdict(float)
    by_category: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))

    for row in rows:
        for config in config_names:
            for cutoff in CUTOFFS:
                metric = row["metrics"][f"{config}@{cutoff}"]
                totals[f"{config}_recall@{cutoff}"] += metric["recall"]
                totals[f"{config}_precision@{cutoff}"] += metric["precision"]

                if not row["item"].get("unanswerable"):
                    bucket = row["item"].get("category", "default")
                else:
                    bucket = "unanswerable"
                by_category[bucket][f"{config}_recall@{cutoff}"].append(metric["recall"])
        if row["item"].get("unanswerable"):
            totals["refusal_correct"] += int(row["refusal_correct"])
        else:
            totals["answer_retained"] += int(not row["refusal_predicted"])

    lines = [
        "# Knowledge Base Retrieval Eval",
        "",
        f"- Generated at: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Golden set: `{len(items)}` questions (`{answerable_count}` answerable, "
        f"`{unanswerable_count}` unanswerable)",
        f"- Index directory: `{index_dir()}`",
        "",
        "| Config | Recall@5 | Recall@10 | Precision@5 | Precision@10 | P50 ms | P95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for config in config_names:
        recall_5 = totals[f"{config}_recall@5"] / answerable_count
        recall_10 = totals[f"{config}_recall@10"] / answerable_count
        precision_5 = totals[f"{config}_precision@5"] / answerable_count
        precision_10 = totals[f"{config}_precision@10"] / answerable_count
        lines.append(
            f"| {config} | {totals[f'{config}_recall@5']:.0f}/{answerable_count} "
            f"({recall_5:.1%}) | {totals[f'{config}_recall@10']:.0f}/{answerable_count} "
            f"({recall_10:.1%}) | {precision_5:.1%} | {precision_10:.1%} | "
            f"{percentile(latencies[config], 0.50):.2f} | "
            f"{percentile(latencies[config], 0.95):.2f} |"
        )

    refusal_rate = (
        totals["refusal_correct"] / unanswerable_count if unanswerable_count else 0.0
    )
    answer_retention = (
        totals["answer_retained"] / answerable_count if answerable_count else 0.0
    )
    gate_accuracy = (totals["refusal_correct"] + totals["answer_retained"]) / len(items)
    lines.extend(
        [
            "",
            "## Evidence gate",
            "",
            f"Answerable retention: **{totals['answer_retained']:.0f}/"
            f"{answerable_count} ({answer_retention:.1%})**.",
            f"Refusal correctness: **{totals['refusal_correct']:.0f}/"
            f"{unanswerable_count} ({refusal_rate:.1%})**.",
            f"Overall gate accuracy: **{(totals['refusal_correct'] + totals['answer_retained']):.0f}/"
            f"{len(items)} ({gate_accuracy:.1%})**.",
            "",
            "## Recall by category",
            "",
            "| Category | Count | Dense@5 | RRF@5 | Dense@10 | RRF@10 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for category in sorted(by_category):
        values = by_category[category]
        count = len(values["dense_recall@5"])
        lines.append(
            f"| {category} | {count} | "
            f"{mean(values['dense_recall@5']):.0%} | {mean(values['hybrid_rrf_recall@5']):.0%} | "
            f"{mean(values['dense_recall@10']):.0%} | {mean(values['hybrid_rrf_recall@10']):.0%} |"
        )

    failures = [
        row
        for row in rows
        if row["item"].get("source")
        and any(row["metrics"][f"hybrid_rrf@{cutoff}"]["recall"] == 0 for cutoff in CUTOFFS)
    ]
    false_refusals = [
        row for row in rows if not row["item"].get("unanswerable") and row["refusal_predicted"]
    ]
    lines.extend(["", "## Evidence-gate failures", ""])
    if false_refusals:
        lines.append("False refusals:")
        for row in false_refusals:
            item = row["item"]
            lines.append(f"- `{item['id']}` {item['question']}")
    else:
        lines.append("False refusals: None.")

    lines.extend(["", "## Hybrid RRF misses", ""])
    if failures:
        for row in failures:
            item = row["item"]
            lines.append(f"- `{item['id']}` {item['question']} -> expected `{item['source']}`")
    else:
        lines.append("None.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "report.md")
    parser.add_argument("--json-output", type=Path, default=EVAL_DIR / "report.json")
    parser.add_argument("--quiet", action="store_true", help="print only the report path")
    args = parser.parse_args()

    items = load_golden_set()
    vector_store = VectorStore()
    if not vector_store.load():
        raise SystemExit("知识库索引不存在；请先运行 ingest --all")

    backend = get_embedding_backend()
    if backend.name != vector_store.backend_name or backend.dim != vector_store.dim:
        raise SystemExit(
            f"Embedding 后端不一致：index={vector_store.backend_name}/{vector_store.dim}, "
            f"current={backend.name}/{backend.dim}; 请重新执行 ingest --all"
        )
    bm25_store = BM25Store()
    if not bm25_store.load():
        raise SystemExit("BM25 索引不存在；请先运行 ingest --all")

    config_names = ("dense", "bm25", "hybrid_rrf")
    if load_kb_config().reranker.backend != "none":
        config_names += ("hybrid_rerank",)

    rows: list[dict] = []
    latencies: dict[str, list[float]] = {name: [] for name in config_names}
    for item in items:
        started = time.perf_counter()
        query_vector = backend.embed_query(item["question"])
        embed_elapsed = (time.perf_counter() - started) * 1000
        result = evaluate_item(item, vector_store, bm25_store, query_vector, config_names)

        for name in config_names:
            embedding_cost = embed_elapsed if name != "bm25" else 0.0
            latencies[name].append(embedding_cost + result["latency_ms"][name])
        rows.append({"item": item, **result})
        if not args.quiet:
            status = "PASS" if result["refusal_correct"] else "FAIL"
            print(f"{item['id']}: refusal={status}")

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    golden_bytes = (EVAL_DIR / "golden_set.json").read_bytes()
    result = {
        "schema_version": "1",
        "generated_at": generated_at,
        "golden_set_sha256": hashlib.sha256(golden_bytes).hexdigest(),
        "index_metadata": vector_store.index_metadata,
        "runtime_config": load_kb_config().snapshot(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "metrics": aggregate_metrics(items, rows, latencies, config_names),
        "cases": [
            {
                "id": row["item"]["id"],
                "question": row["item"]["question"],
                "unanswerable": bool(row["item"].get("unanswerable")),
                "metrics": row["metrics"],
                "refusal_predicted": row["refusal_predicted"],
                "refusal_correct": row["refusal_correct"],
                "latency_ms": row["latency_ms"],
            }
            for row in rows
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_report(items, rows, latencies, config_names),
        encoding="utf-8",
    )
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report -> {args.output}")
    print(f"json report -> {args.json_output}")


if __name__ == "__main__":
    main()
