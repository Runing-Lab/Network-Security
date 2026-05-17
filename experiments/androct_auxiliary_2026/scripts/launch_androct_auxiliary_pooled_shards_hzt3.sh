#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/root/experiments/androct_auxiliary}"
MAIN_BASE="${MAIN_BASE:-/root/experiments/androct_second_main}"
VENV="${VENV:-/root/experiments/androct_sgfe/.venv}"
PYTHON="${PYTHON:-$VENV/bin/python}"
MAX_PARALLEL="${MAX_PARALLEL:-6}"
DATA_DIR="${DATA_DIR:-$MAIN_BASE/data/AndroCT}"
CACHE_DIR="${CACHE_DIR:-$MAIN_BASE/cache}"
SHARD_BASE="$BASE/pooled_shards"
PROCESS_MD="$BASE/EXPERIMENT_PROCESS.md"

mkdir -p "$BASE/scripts" "$BASE/logs" "$BASE/outputs" "$BASE/state" "$SHARD_BASE"

log_step() {
  local msg="$1"
  printf '\n## %s\n\n%s\n' "$(date -Is)" "$msg" >> "$PROCESS_MD"
}

count_running() {
  tmux ls 2>/dev/null | awk -F: '/^androct_aux_pool_/ {n++} END {print n+0}'
}

is_running() {
  tmux has-session -t "$1" 2>/dev/null
}

shard_done() {
  find "$1" -maxdepth 1 -type f -name '*_summary.csv' 2>/dev/null | grep -q .
}

formal_done() {
  local k="$1"
  find "$BASE/outputs/androct_aux_y2010_2019_k${k}" -maxdepth 1 -type f -name '*_summary.csv' 2>/dev/null | grep -q .
}

launch_shard() {
  local k="$1"
  local split="$2"
  local seed="$3"
  local task="androct_aux_pool_k${k}_${split}_s${seed}"
  local outdir="$SHARD_BASE/$task"
  local log="$BASE/logs/${task}.log"

  if shard_done "$outdir" || is_running "$task"; then
    return 0
  fi
  local running
  running="$(count_running)"
  if [ "$running" -ge "$MAX_PARALLEL" ]; then
    return 1
  fi
  mkdir -p "$outdir"
  log_step "Launching pooled shard $task. This replaces the slower monolithic pooled task with K=$k split=$split seed=$seed."
  tmux new-session -d -s "$task" "cd '$BASE' && OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 '$PYTHON' '$BASE/scripts/run_androct_auxiliary_experiments.py' \
    --androct-script '$MAIN_BASE/scripts/run_androct_sgfe_experiment.py' \
    --data-dir '$DATA_DIR' \
    --out-dir '$outdir' \
    --cache-dir '$CACHE_DIR' \
    --years 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 \
    --k-shot '$k' \
    --seeds '$seed' \
    --splits '$split' \
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

shard_count_for_k() {
  local k="$1"
  local n=0
  for split in emu_to_real real_to_emu; do
    for seed in 0 1 2 3 4 5 6 7 8 9; do
      if shard_done "$SHARD_BASE/androct_aux_pool_k${k}_${split}_s${seed}"; then
        n=$((n+1))
      fi
    done
  done
  echo "$n"
}

try_merge_k() {
  local k="$1"
  if formal_done "$k"; then
    return 0
  fi
  local n
  n="$(shard_count_for_k "$k")"
  if [ "$n" -eq 20 ]; then
    log_step "Merging pooled shards for K=$k into formal output directory."
    "$PYTHON" "$BASE/scripts/merge_androct_auxiliary_shards.py" --base-dir "$BASE" --k-shot "$k" --force >> "$BASE/logs/pooled_shard_merge.log" 2>&1
  fi
}

write_status() {
  local done_shards=0
  local formal=0
  local running
  running="$(count_running)"
  : > "$BASE/state/pooled_shard_status.tsv"
  printf 'task\tstatus\n' >> "$BASE/state/pooled_shard_status.tsv"
  for k in 1 2 3 5 10; do
    formal_done "$k" && formal=$((formal+1))
    for split in emu_to_real real_to_emu; do
      for seed in 0 1 2 3 4 5 6 7 8 9; do
        local task="androct_aux_pool_k${k}_${split}_s${seed}"
        local status="pending"
        if shard_done "$SHARD_BASE/$task"; then
          status="done"
          done_shards=$((done_shards+1))
        elif is_running "$task"; then
          status="running"
        fi
        printf '%s\t%s\n' "$task" "$status" >> "$BASE/state/pooled_shard_status.tsv"
      done
    done
  done
  printf 'done_shards=%s\nrunning_shards=%s\nexpected_shards=100\nformal_pooled_done=%s\nupdated_at=%s\n' "$done_shards" "$running" "$formal" "$(date -Is)" > "$BASE/state/pooled_shard_status.env"
}

log_step "Pooled shard accelerator started with MAX_PARALLEL=$MAX_PARALLEL."

while true; do
  for k in 1 2 3 5 10; do
    if formal_done "$k"; then
      continue
    fi
    for split in emu_to_real real_to_emu; do
      for seed in 0 1 2 3 4 5 6 7 8 9; do
        launch_shard "$k" "$split" "$seed" || true
      done
    done
    try_merge_k "$k"
  done
  write_status
  # shellcheck disable=SC1090
  . "$BASE/state/pooled_shard_status.env"
  echo "[pooled-shards] done_shards=$done_shards/100 formal=$formal_pooled_done/5 running=$running_shards $(date -Is)" >> "$BASE/logs/pooled_shard_daemon.log"
  if [ "$formal_pooled_done" -ge 5 ] && [ "$running_shards" -eq 0 ]; then
    log_step "All pooled shard outputs merged into formal K-level summaries."
    break
  fi
  sleep 45
done
