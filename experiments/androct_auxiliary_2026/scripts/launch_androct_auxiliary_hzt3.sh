#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/root/experiments/androct_auxiliary}"
MAIN_BASE="${MAIN_BASE:-/root/experiments/androct_second_main}"
VENV="${VENV:-/root/experiments/androct_sgfe/.venv}"
MAX_PARALLEL="${MAX_PARALLEL:-8}"
PYTHON="${PYTHON:-$VENV/bin/python}"
DATA_DIR="${DATA_DIR:-$MAIN_BASE/data/AndroCT}"
CACHE_DIR="${CACHE_DIR:-$MAIN_BASE/cache}"
PROCESS_MD="$BASE/EXPERIMENT_PROCESS.md"

mkdir -p "$BASE/scripts" "$BASE/logs" "$BASE/outputs" "$BASE/state"

log_step() {
  local msg="$1"
  printf '\n## %s\n\n%s\n' "$(date -Is)" "$msg" >> "$PROCESS_MD"
}

count_running() {
  tmux ls 2>/dev/null | awk -F: '/^androct_aux_y/ {n++} END {print n+0}'
}

is_running() {
  local task="$1"
  tmux has-session -t "$task" 2>/dev/null
}

is_done() {
  local outdir="$1"
  find "$outdir" -maxdepth 1 -type f -name '*_summary.csv' 2>/dev/null | grep -q .
}

launch_one() {
  local yid="$1"
  local years="$2"
  local k="$3"
  local task="androct_aux_y${yid}_k${k}"
  local outdir="$BASE/outputs/$task"
  local log="$BASE/logs/${task}.log"
  mkdir -p "$outdir"

  if is_done "$outdir"; then
    return 0
  fi
  if is_running "$task"; then
    return 0
  fi

  local running
  running="$(count_running)"
  if [ "$running" -ge "$MAX_PARALLEL" ]; then
    return 1
  fi

  log_step "Launching $task with years=[$years], K=$k. Output: $outdir"
  tmux new-session -d -s "$task" "cd '$BASE' && '$PYTHON' '$BASE/scripts/run_androct_auxiliary_experiments.py' \
    --androct-script '$MAIN_BASE/scripts/run_androct_sgfe_experiment.py' \
    --data-dir '$DATA_DIR' \
    --out-dir '$outdir' \
    --cache-dir '$CACHE_DIR' \
    --years $years \
    --k-shot '$k' \
    --seeds 0 1 2 3 4 5 6 7 8 9 \
    --splits emu_to_real real_to_emu \
    --blocks warm_start allfeature_select support_only label_noise svd_coral \
    --taus 0.05 0.10 \
    --noise-rates 0.0 0.1 0.3 0.5 \
    --n-estimators 100 \
    --model-jobs 1 \
    --max-features 40000 \
    --svd-components 128 \
    --max-query-per-class 600 \
    --min-source-per-class 20 \
    --max-lines-per-log 5000 \
    > '$log' 2>&1; rc=\$?; echo \$rc > '$BASE/logs/${task}.exit'; exit \$rc"
  return 0
}

write_status() {
  local done=0
  local running
  running="$(count_running)"
  : > "$BASE/state/queue_status.tsv"
  printf 'task\tstatus\tlog\n' >> "$BASE/state/queue_status.tsv"
  for y in 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019; do
    for k in 1 2 3 5 10; do
      local task="androct_aux_y${y}_k${k}"
      local outdir="$BASE/outputs/$task"
      local status="pending"
      if is_done "$outdir"; then status="done"; done=$((done+1)); elif is_running "$task"; then status="running"; fi
      printf '%s\t%s\t%s\n' "$task" "$status" "$BASE/logs/${task}.log" >> "$BASE/state/queue_status.tsv"
    done
  done
  for k in 1 2 3 5 10; do
    local task="androct_aux_y2010_2019_k${k}"
    local outdir="$BASE/outputs/$task"
    local status="pending"
    if is_done "$outdir"; then status="done"; done=$((done+1)); elif is_running "$task"; then status="running"; fi
    printf '%s\t%s\t%s\n' "$task" "$status" "$BASE/logs/${task}.log" >> "$BASE/state/queue_status.tsv"
  done
  printf 'done=%s\nrunning=%s\nexpected=55\nupdated_at=%s\n' "$done" "$running" "$(date -Is)" > "$BASE/state/queue_status.env"
}

if [ ! -f "$PROCESS_MD" ]; then
  cat > "$PROCESS_MD" <<'EOF'
# AndroCT Auxiliary Experiment Process

This log records the continuous auxiliary experiment phase that mirrors the
KronoDroid reviewer-check suite on AndroCT.

EOF
  log_step "Initialized auxiliary queue. Main result directory is /root/experiments/androct_second_main. Auxiliary outputs will be written under /root/experiments/androct_auxiliary."
fi

log_step "Queue daemon started with MAX_PARALLEL=$MAX_PARALLEL."

while true; do
  progressed=0
  for y in 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019; do
    for k in 1 2 3 5 10; do
      if launch_one "$y" "$y" "$k"; then
        progressed=1
      fi
    done
  done
  for k in 1 2 3 5 10; do
    if launch_one "2010_2019" "2010 2011 2012 2013 2014 2015 2016 2017 2018 2019" "$k"; then
      progressed=1
    fi
  done

  write_status
  # shellcheck disable=SC1090
  . "$BASE/state/queue_status.env"
  echo "[daemon] done=$done/55 running=$running $(date -Is)" >> "$BASE/logs/auxiliary_queue_daemon.log"
  if [ "$done" -ge 55 ] && [ "$running" -eq 0 ]; then
    log_step "All 55 auxiliary task folders have summary CSV files. Queue daemon exiting."
    break
  fi
  sleep 60
done
