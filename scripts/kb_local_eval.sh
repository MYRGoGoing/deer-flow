#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${KB_LOCAL_MODEL_PORT:-18080}"
BASE_URL="http://127.0.0.1:${PORT}/v1"
OUTPUT_DIR="${1:-${PROJECT_ROOT}/evals/kb_qa/baselines/local-bge-small-zh}"
INDEX_DIR="${KB_LOCAL_INDEX_DIR:-${PROJECT_ROOT}/data/kb_index_local_bge}"
LOG_FILE="${OUTPUT_DIR}/model-server.log"

mkdir -p "${OUTPUT_DIR}"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'Port %s is already in use; set KB_LOCAL_MODEL_PORT to another port.\n' "${PORT}" >&2
  exit 1
fi

cd "${PROJECT_ROOT}"
uv run --script scripts/kb_local_model_server.py \
  --port "${PORT}" \
  --cache-dir "${PROJECT_ROOT}/data/model_cache" \
  --threads "${KB_LOCAL_MODEL_THREADS:-2}" \
  >"${LOG_FILE}" 2>&1 &
MODEL_PID=$!
trap 'kill "${MODEL_PID}" 2>/dev/null || true; wait "${MODEL_PID}" 2>/dev/null || true' EXIT

printf 'Waiting for local ONNX models (first run downloads about 200 MB)...\n'
for _ in $(seq 1 600); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${MODEL_PID}" 2>/dev/null; then
    printf 'Local model server exited. See %s\n' "${LOG_FILE}" >&2
    exit 1
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null

export KB_INDEX_DIR="${INDEX_DIR}"
export KB_EMBEDDING_BACKEND="openai"
export KB_EMBEDDING_BASE_URL="${BASE_URL}"
export KB_EMBEDDING_MODEL="BAAI/bge-small-zh-v1.5"
export KB_EMBEDDING_API_KEY="local-only"
export KB_RERANKER_BACKEND="http"
export KB_RERANKER_BASE_URL="${BASE_URL}"
export KB_RERANKER_MODEL="ms-marco-MultiBERT-L-12"
export KB_RERANKER_API_KEY="local-only"

cd "${PROJECT_ROOT}/backend"
uv run --frozen python -m deerflow.community.kb_search.ingest \
  --all \
  --embedding-backend openai \
  --metadata-output "${OUTPUT_DIR}/index-metadata.json"

cd "${PROJECT_ROOT}"
backend/.venv/bin/python evals/kb_qa/run_eval.py \
  --output "${OUTPUT_DIR}/report.md" \
  --json-output "${OUTPUT_DIR}/report.json" \
  --quiet

printf 'Local BGE + multilingual reranker evaluation written to %s\n' "${OUTPUT_DIR}"
