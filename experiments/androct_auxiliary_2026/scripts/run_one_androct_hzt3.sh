#!/usr/bin/env bash
set -euo pipefail

BASE="/root/experiments/androct_second_main"
NAME="$1"
shift

PY="/root/experiments/androct_sgfe/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

mkdir -p "$BASE/outputs/$NAME" "$BASE/cache/$NAME" "$BASE/logs"

"$PY" "$BASE/scripts/run_androct_sgfe_experiment.py" \
  --data-dir "$BASE/data/AndroCT" \
  --out-dir "$BASE/outputs/$NAME" \
  --cache-dir "$BASE/cache/$NAME" \
  --max-lines-per-log 5000 \
  --min-source-per-class 20 \
  "$@"
