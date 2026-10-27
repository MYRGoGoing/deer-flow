#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE_DIR="${1:-${PROJECT_ROOT}/evals/kb_qa/baselines/local-hashing}"
export KB_EMBEDDING_BACKEND="hashing"

mkdir -p "${BASELINE_DIR}"
cd "${PROJECT_ROOT}/backend"
uv run python -m deerflow.community.kb_search.ingest \
  --all \
  --embedding-backend hashing \
  --metadata-output "${BASELINE_DIR}/index-metadata.json"

cd "${PROJECT_ROOT}"
backend/.venv/bin/python evals/kb_qa/run_eval.py \
  --output "${BASELINE_DIR}/report.md" \
  --json-output "${BASELINE_DIR}/report.json" \
  --quiet

printf 'Knowledge-base baseline written to %s\n' "${BASELINE_DIR}"
