#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_FALLBACK_BIN:-python3}"
fi

cd "$ROOT_DIR"

"$PYTHON_BIN" -m compileall -q apps/api forma_core evals scripts tests
"$PYTHON_BIN" -m py_compile scripts/models/sample.py scripts/models/sample_async.py evals/performance/benchmark_offline.py evals/performance/benchmark_models.py
"$PYTHON_BIN" -m unittest discover -s tests -t . -v
