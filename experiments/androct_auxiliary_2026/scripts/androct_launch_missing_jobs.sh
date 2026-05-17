#!/usr/bin/env bash
set -euo pipefail

BASE="/root/experiments/androct_second_main"
LOGDIR="$BASE/logs"
MAX_PARALLEL="${MAX_PARALLEL:-8}"
YEARS="2010 2011 2012 2013 2014 2015 2016 2017 2018 2019"
K_VALUES="1 2 3 5 10"

mkdir -p "$LOGDIR"

live_count() {
  { tmux ls 2>/dev/null || true; } | awk '/^androct2_/ && !/^androct2_missing_launcher:/ {c++} END {print c + 0}'
}

wait_slot() {
  while [ "$(live_count)" -ge "$MAX_PARALLEL" ]; do
    sleep 60
  done
}

year_max_apps() {
  case "$1" in
    2012|2014) echo 1500 ;;
    *) echo 1200 ;;
  esac
}

job_done() {
  local name="$1"
  find "$BASE/outputs/$name" -maxdepth 1 -name '*_summary.csv' -size +20c 2>/dev/null | grep -q .
}

job_live() {
  local name="$1"
  tmux has-session -t "$name" >/dev/null 2>&1
}

launch_job() {
  local name="$1"
  shift
  if job_done "$name"; then
    echo "[skip-done] $name" >> "$LOGDIR/launch_missing.log"
    return 0
  fi
  if job_live "$name"; then
    echo "[skip-live] $name" >> "$LOGDIR/launch_missing.log"
    return 0
  fi
  wait_slot
  tmux new-session -d -s "$name" "bash '$BASE/scripts/run_one_androct.sh' '$name' $* > '$LOGDIR/$name.log' 2>&1"
  echo "[launch-missing] $name $* $(date -Is)" | tee -a "$LOGDIR/launch_missing.log"
}

echo "[missing-launcher] start max_parallel=$MAX_PARALLEL $(date -Is)" | tee -a "$LOGDIR/launch_missing.log"

for k in $K_VALUES; do
  for y in $YEARS; do
    launch_job "androct2_y${y}_k${k}" --years "$y" --k-shot "$k" --seeds 0 1 2 3 4 5 6 7 8 9 --splits emu_to_real real_to_emu --max-apps-per-year-class "$(year_max_apps "$y")" --max-query-per-class 600 --taus 0.05 0.10
  done
done

for k in $K_VALUES; do
  launch_job "androct2_y2010_2019_k${k}" --years 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 --k-shot "$k" --seeds 0 1 2 3 4 5 6 7 8 9 --splits emu_to_real real_to_emu --max-apps-per-year-class 700 --max-query-per-class 600 --taus 0.05 0.10
done

echo "[missing-launcher] complete $(date -Is)" | tee -a "$LOGDIR/launch_missing.log"
