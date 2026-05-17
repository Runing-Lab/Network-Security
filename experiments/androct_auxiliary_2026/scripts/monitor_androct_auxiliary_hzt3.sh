#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/root/experiments/androct_auxiliary}"
echo "# AndroCT auxiliary monitor"
echo "- time_utc: $(date -Is)"
echo "- base: $BASE"
echo "- summaries: $(find "$BASE/outputs" -type f -name '*_summary.csv' 2>/dev/null | wc -l)"
echo "- running_aux_tmux: $(tmux ls 2>/dev/null | grep -c '^androct_aux_y' || true)"
echo "- failure_exit_files: $(find "$BASE/logs" -type f -name 'androct_aux_y*.exit' -exec sh -c 'for f; do [ "$(cat "$f" 2>/dev/null)" != "0" ] && echo "$f"; done' sh {} + 2>/dev/null | wc -l)"
echo
echo "## tmux"
tmux ls 2>/dev/null | grep -E 'androct_aux|androct2' || true
echo
echo "## queue status"
cat "$BASE/state/queue_status.env" 2>/dev/null || true
echo
echo "## daemon tail"
tail -40 "$BASE/logs/auxiliary_queue_daemon.log" 2>/dev/null || true
echo
echo "## recent logs"
find "$BASE/logs" -maxdepth 1 -type f -name 'androct_aux_y*.log' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -8 | cut -d' ' -f2- | while read -r f; do
  echo "### $f"
  tail -8 "$f" || true
  echo
done
