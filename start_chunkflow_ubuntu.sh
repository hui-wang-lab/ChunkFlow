#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8900}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export MINERU_API_TOKEN="eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiIxMzMwMDQwNiIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3NzIwNzM1NywiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiNzBmMWVlZGMtMDQyOC00N2FkLTgxYmQtNjllNzlmYTIxOTk1IiwiZW1haWwiOiIiLCJleHAiOjE3ODQ5ODMzNTd9.SmPdON8Sd4Wy6TnFCYkMFVU1ZfOlnOJJcbhumqQdrYYnYnbvalkDxshAr4RClS7ZdAF7M_kGvWxwg6SFZDARKQ"
export CHUNKFLOW_PARSER_PRIORITY="docling,mineru,pypdf"

echo "Stopping existing ChunkFlow service on port ${PORT} ..."
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti tcp:"${PORT}" || true)"
elif command -v fuser >/dev/null 2>&1; then
  pids="$(fuser "${PORT}"/tcp 2>/dev/null || true)"
else
  pids="$(ss -ltnp 2>/dev/null | awk -v port=":${PORT}" '$4 ~ port { print $NF }' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' || true)"
fi

if [[ -n "${pids:-}" ]]; then
  kill ${pids} 2>/dev/null || true
  sleep 1
  kill -9 ${pids} 2>/dev/null || true
  echo "Stopped process(es): ${pids}"
else
  echo "No existing listener found."
fi

cd "${PROJECT_ROOT}"
echo "Starting ChunkFlow on http://127.0.0.1:${PORT} ..."
exec "${PYTHON_BIN}" -m uvicorn chunkflow.app:app --host 0.0.0.0 --port "${PORT}"
