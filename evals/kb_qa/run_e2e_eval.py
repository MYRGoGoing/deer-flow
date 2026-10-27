"""Generate knowledge-base answers and evaluate the full RAG response path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from statistics import mean

from deerflow.community.kb_search.config import load_kb_config
from deerflow.community.kb_search.evaluation import (
    aggregate_e2e_metrics,
    evaluate_answer,
    generate_answer,
    get_evaluation_chat_backend,
    judge_answer,
)
from deerflow.community.kb_search.retriever import hybrid_search
from deerflow.community.kb_search.stores import VectorStore

EVAL_DIR = Path(__file__).resolve().parent


def load_golden_set() -> list[dict]:
    return json.loads((EVAL_DIR / "golden_set.json").read_text(encoding="utf-8"))


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _load_resume_cases(path: Path, run_signature: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("run_signature") != run_signature:
        raise SystemExit("断点文件与当前语料、索引或模型配置不一致；请使用 --fresh 重跑")
    return {case["id"]: case for case in payload.get("cases", [])}


def _report(payload: dict) -> str:
    metrics = payload["metrics"]

    def percent(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.1%}"

    lines = [
        "# Knowledge Base End-to-End RAG Eval",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Generator: `{payload['generator']}`",
        f"- Judge: `{payload['judge'] or 'disabled'}`",
        f"- Cases: `{metrics['case_count']}` "
        f"(`{metrics['answerable_count']}` answerable, "
        f"`{metrics['unanswerable_count']}` unanswerable)",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Refusal accuracy | {percent(metrics['refusal_accuracy'])} |",
        f"| Keyword recall | {percent(metrics['keyword_recall'])} |",
        f"| Reference-answer token F1 | {percent(metrics['answer_token_f1'])} |",
        f"| Citation validity | {percent(metrics['citation_validity'])} |",
        f"| Expected-source citation rate | {percent(metrics['expected_source_citation_rate'])} |",
        f"| Faithfulness (LLM judge) | {percent(metrics['faithfulness'])} |",
        f"| Answer relevancy (LLM judge) | {percent(metrics['answer_relevancy'])} |",
        "",
        "## Latency",
        "",
        f"- Mean: `{payload['latency_ms']['mean']:.2f} ms`",
        f"- P50: `{payload['latency_ms']['p50']:.2f} ms`",
        f"- P95: `{payload['latency_ms']['p95']:.2f} ms`",
        "",
        "## Failed Cases",
        "",
    ]
    failures = [
        case
        for case in payload["cases"]
        if not case["metrics"]["refusal_correct"]
        or (
            not case["unanswerable"]
            and not case["metrics"]["expected_source_cited"]
        )
    ]
    if not failures:
        lines.append("None.")
    else:
        for case in failures:
            lines.append(f"- `{case['id']}` {case['question']}")
    lines.extend(
        [
            "",
            "> Keyword recall and token F1 are deterministic lexical diagnostics, not semantic accuracy. "
            "Faithfulness and answer relevancy are only present when a judge model is configured.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "e2e-report.md")
    parser.add_argument("--json-output", type=Path, default=EVAL_DIR / "e2e-report.json")
    parser.add_argument("--checkpoint", type=Path, default=EVAL_DIR / "e2e-checkpoint.json")
    parser.add_argument("--limit", type=int, help="run only the first N cases")
    parser.add_argument("--case-id", action="append", help="run one or more selected case ids")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="ignore an existing checkpoint")
    args = parser.parse_args()

    config = load_kb_config()
    try:
        backend = get_evaluation_chat_backend(config.evaluation)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    judge_model = None if args.no_judge else config.evaluation.judge_model or None
    vector_store = VectorStore()
    if not vector_store.load(config.index_dir):
        raise SystemExit("知识库索引不存在；请先运行 ingest --all")

    items = load_golden_set()
    if args.case_id:
        selected = set(args.case_id)
        items = [item for item in items if item["id"] in selected]
        missing = selected - {item["id"] for item in items}
        if missing:
            raise SystemExit(f"未知评测样本: {', '.join(sorted(missing))}")
    if args.limit is not None:
        if args.limit <= 0:
            raise SystemExit("--limit 必须大于 0")
        items = items[: args.limit]

    golden_hash = hashlib.sha256(
        (EVAL_DIR / "golden_set.json").read_bytes()
    ).hexdigest()
    signature_payload = {
        "golden_set_sha256": golden_hash,
        "corpus_manifest_hash": vector_store.index_metadata.get("corpus_manifest_hash"),
        "embedding_backend": vector_store.backend_name,
        "generator": backend.name,
        "judge": judge_model,
        "case_ids": [item["id"] for item in items],
    }
    run_signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cases_by_id = {} if args.fresh else _load_resume_cases(args.checkpoint, run_signature)

    for position, item in enumerate(items, start=1):
        if item["id"] in cases_by_id:
            print(f"[{position}/{len(items)}] {item['id']}: resumed")
            continue
        started = time.perf_counter()
        hits = hybrid_search(item["question"], top_k=config.retrieval.top_k)
        answer = generate_answer(item["question"], hits, backend)
        metrics = evaluate_answer(item, answer, hits)
        judge = (
            judge_answer(
                item["question"],
                answer,
                hits,
                backend,
                model=judge_model,
            )
            if judge_model and not item.get("unanswerable")
            else None
        )
        elapsed = (time.perf_counter() - started) * 1000
        cases_by_id[item["id"]] = {
            "id": item["id"],
            "question": item["question"],
            "unanswerable": bool(item.get("unanswerable")),
            "answer": answer,
            "retrieved_sources": [hit.get("source_file") for hit in hits],
            "metrics": metrics,
            "judge": judge,
            "latency_ms": elapsed,
        }
        checkpoint_payload = {
            **signature_payload,
            "run_signature": run_signature,
            "cases": [cases_by_id[item["id"]] for item in items if item["id"] in cases_by_id],
        }
        _write_json_atomic(args.checkpoint, checkpoint_payload)
        print(f"[{position}/{len(items)}] {item['id']}: {elapsed:.0f} ms")

    cases = [cases_by_id[item["id"]] for item in items]
    latencies = [case["latency_ms"] for case in cases]
    payload = {
        "schema_version": "1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **signature_payload,
        "run_signature": run_signature,
        "metrics": aggregate_e2e_metrics(cases),
        "latency_ms": {
            "mean": mean(latencies) if latencies else 0.0,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "cases": cases,
    }
    _write_json_atomic(args.json_output, payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_report(payload), encoding="utf-8")
    print(f"report -> {args.output}")
    print(f"json report -> {args.json_output}")


if __name__ == "__main__":
    main()
