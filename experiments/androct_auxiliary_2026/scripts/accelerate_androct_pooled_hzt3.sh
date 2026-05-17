#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/root/experiments/androct_auxiliary}"
STAMP="$(date +%Y%m%dT%H%M%SZ)"
ARCH="$BASE/pooled_monolith_partial_$STAMP"
mkdir -p "$ARCH" "$BASE/logs" "$BASE/state"

{
  echo
  echo "## $(date -Is)"
  echo
  echo "Accelerating pooled auxiliary tail. Stopping monolithic pooled tasks, archiving partial outputs to $ARCH, and starting K x split x seed shards."
} >> "$BASE/EXPERIMENT_PROCESS.md"

for s in androct_aux_y2010_2019_k1 androct_aux_y2010_2019_k2 androct_aux_y2010_2019_k3 androct_aux_y2010_2019_k5 androct_aux_y2010_2019_k10; do
  tmux kill-session -t "$s" 2>/dev/null || true
done

sleep 3

for d in "$BASE"/outputs/androct_aux_y2010_2019_k*; do
  [ -d "$d" ] || continue
  # Only archive incomplete formal pooled directories. Completed directories are left in place.
  if ! find "$d" -maxdepth 1 -type f -name '*_summary.csv' 2>/dev/null | grep -q .; then
    mv "$d" "$ARCH/"
  fi
done

if [ -f "$BASE/state/pooled_shard_launcher.pid" ]; then
  old="$(cat "$BASE/state/pooled_shard_launcher.pid" 2>/dev/null || true)"
  [ -n "$old" ] && kill "$old" 2>/dev/null || true
fi

nohup env BASE="$BASE" MAIN_BASE=/root/experiments/androct_second_main MAX_PARALLEL="${MAX_PARALLEL:-6}" bash "$BASE/scripts/launch_androct_auxiliary_pooled_shards_hzt3.sh" \
  > "$BASE/logs/pooled_shard_launcher_stdout.log" \
  2> "$BASE/logs/pooled_shard_launcher_stderr.log" &
echo $! > "$BASE/state/pooled_shard_launcher.pid"

echo "pooled_shard_launcher_pid=$(cat "$BASE/state/pooled_shard_launcher.pid")"
echo "archived_partial=$ARCH"
