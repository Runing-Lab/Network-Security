#!/usr/bin/env python3
"""Deploy AndroCT second-main-dataset experiments to a Matpool SSH server.

Reads the SSH password from MP_PASS. The password is used only for the initial
connection and must not be written to disk, remote scripts, logs, or messages.
"""

from __future__ import annotations

import argparse
import os
import stat
import textwrap
from pathlib import Path

import paramiko


def quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def connect(args: argparse.Namespace) -> paramiko.SSHClient:
    password = os.environ.get("MP_PASS")
    if not password:
        raise RuntimeError("MP_PASS is not set")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        port=args.port,
        username=args.user,
        password=password,
        timeout=60,
        banner_timeout=60,
        auth_timeout=60,
    )
    return client


def run(client: paramiko.SSHClient, cmd: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def put_text(sftp: paramiko.SFTPClient, remote_path: str, content: str, mode: int = 0o644) -> None:
    with sftp.file(remote_path, "w") as fh:
        fh.write(content)
    sftp.chmod(remote_path, mode)


def install_key(client: paramiko.SSHClient, pubkey_path: Path) -> None:
    pubkey = pubkey_path.read_text(encoding="utf-8").strip()
    cmd = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && "
        f"grep -qxF {quote(pubkey)} ~/.ssh/authorized_keys || echo {quote(pubkey)} >> ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys"
    )
    code, out, err = run(client, cmd)
    if code != 0:
        raise RuntimeError(f"failed to install SSH key: {err or out}")


def env_report(client: paramiko.SSHClient, base: str) -> str:
    cmd = textwrap.dedent(
        f"""
        set -e
        echo '## host'; hostname
        echo '## date'; date -Is
        echo '## pwd'; pwd
        echo '## base'; mkdir -p {quote(base)}; echo {quote(base)}
        echo '## disk'; df -h {quote(base)}
        echo '## memory'; free -h || true
        echo '## cpu'; nproc || true
        echo '## gpu'; nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader || true
        echo '## python'; python3 --version
        echo '## packages'; python3 - <<'PY'
import importlib
for name in ['numpy','pandas','scipy','sklearn']:
    try:
        m = importlib.import_module(name)
        print(name, getattr(m, '__version__', 'ok'))
    except Exception as e:
        print(name, 'MISSING', repr(e))
PY
        echo '## tmux'; tmux -V || true
        """
    )
    code, out, err = run(client, cmd)
    if code != 0:
        raise RuntimeError(f"environment check failed: {err or out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--user", default="root")
    ap.add_argument("--remote-dir", default="/root/experiments/androct_second_main")
    ap.add_argument("--local-script", type=Path, required=True)
    ap.add_argument("--pubkey", type=Path, required=True)
    args = ap.parse_args()

    client = connect(args)
    try:
        install_key(client, args.pubkey)
        report = env_report(client, args.remote_dir)
        print(report)

        code, out, err = run(
            client,
            f"mkdir -p {quote(args.remote_dir)}/scripts {quote(args.remote_dir)}/logs "
            f"{quote(args.remote_dir)}/outputs {quote(args.remote_dir)}/cache {quote(args.remote_dir)}/data/AndroCT",
        )
        if code != 0:
            raise RuntimeError(err or out)

        sftp = client.open_sftp()
        try:
            remote_py = f"{args.remote_dir}/scripts/run_androct_sgfe_experiment.py"
            sftp.put(str(args.local_script), remote_py)
            sftp.chmod(remote_py, 0o755)

            runner = f"""#!/usr/bin/env bash
set -euo pipefail
BASE={quote(args.remote_dir)}
NAME="$1"
shift
OUT="$BASE/outputs/$NAME"
LOGDIR="$BASE/logs"
mkdir -p "$OUT" "$LOGDIR" "$BASE/cache/$NAME"
cd "$BASE"
echo "[start] $NAME $(date -Is)" > "$LOGDIR/$NAME.status"
python3 "$BASE/scripts/run_androct_sgfe_experiment.py" \\
  --data-dir "$BASE/data/AndroCT" \\
  --out-dir "$OUT" \\
  --cache-dir "$BASE/cache/$NAME" \\
  --max-lines-per-log 5000 \\
  --min-source-per-class 20 \\
  "$@"
echo "[done] $NAME $(date -Is)" >> "$LOGDIR/$NAME.status"
"""
            put_text(sftp, f"{args.remote_dir}/scripts/run_one_androct.sh", runner, 0o755)

            launcher = f"""#!/usr/bin/env bash
set -euo pipefail
BASE={quote(args.remote_dir)}
DATA="$BASE/data/AndroCT"
LOGDIR="$BASE/logs"
MAX_PARALLEL="${{MAX_PARALLEL:-8}}"
YEARS="2010 2011 2012 2013 2014 2015 2016 2017 2018 2019"
mkdir -p "$LOGDIR" "$BASE/outputs" "$BASE/cache"

archive_ok() {{
  local f="$1"
  [ -s "$DATA/$f" ] && gzip -t "$DATA/$f" >/dev/null 2>&1
}}

all_data_ok() {{
  local missing=0
  for y in $YEARS; do
    for d in trace real-trace; do
      for k in benign malware; do
        f="${{d}}-${{k}}-${{y}}.tar.gz"
        if ! archive_ok "$f"; then
          echo "[wait] missing_or_bad $f" | tee -a "$LOGDIR/launch_second_main.log"
          missing=$((missing+1))
        fi
      done
    done
  done
  [ "$missing" -eq 0 ]
}}

live_count() {{
  tmux ls 2>/dev/null | grep -c '^androct2_' || true
}}

wait_slot() {{
  while [ "$(live_count)" -ge "$MAX_PARALLEL" ]; do
    sleep 60
  done
}}

job_done() {{
  local name="$1"
  compgen -G "$BASE/outputs/$name/*_summary.csv" >/dev/null || return 1
  if compgen -G "$BASE/outputs/$name/*.jsonl" >/dev/null; then
    ! grep -R '"status": "failed"' "$BASE/outputs/$name"/*.jsonl >/dev/null 2>&1
  fi
}}

year_max_apps() {{
  case "$1" in
    2012|2014) echo 1500 ;;
    *) echo 1200 ;;
  esac
}}

launch_job() {{
  local name="$1"
  shift
  if tmux has-session -t "$name" 2>/dev/null; then
    echo "[skip-live] $name" | tee -a "$LOGDIR/launch_second_main.log"
  elif job_done "$name"; then
    echo "[skip-done] $name" | tee -a "$LOGDIR/launch_second_main.log"
  else
    wait_slot
    tmux new-session -d -s "$name" "bash '$BASE/scripts/run_one_androct.sh' '$name' $* > '$LOGDIR/$name.log' 2>&1"
    echo "[launch] $name $* $(date -Is)" | tee -a "$LOGDIR/launch_second_main.log"
  fi
}}

echo "[launcher] waiting for all archives $(date -Is)" | tee -a "$LOGDIR/launch_second_main.log"
until all_data_ok; do
  sleep 300
done
echo "[launcher] all archives ready $(date -Is)" | tee -a "$LOGDIR/launch_second_main.log"

for k in 1 2 3 5 10; do
  for y in $YEARS; do
    launch_job "androct2_y${{y}}_k${{k}}" --years "$y" --k-shot "$k" --seeds 0 1 2 3 4 5 6 7 8 9 --splits emu_to_real real_to_emu --max-apps-per-year-class "$(year_max_apps "$y")" --max-query-per-class 600 --taus 0.05 0.10
  done
done

for k in 1 2 3 5 10; do
  launch_job "androct2_y2010_2019_k${{k}}" --years 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 --k-shot "$k" --seeds 0 1 2 3 4 5 6 7 8 9 --splits emu_to_real real_to_emu --max-apps-per-year-class 700 --max-query-per-class 600 --taus 0.05 0.10
done

echo "[launcher] launch pass complete $(date -Is)" | tee -a "$LOGDIR/launch_second_main.log"
"""
            put_text(sftp, f"{args.remote_dir}/scripts/launch_androct_second_main.sh", launcher, 0o755)

            monitor = f"""#!/usr/bin/env bash
set -euo pipefail
BASE={quote(args.remote_dir)}
echo "## time $(date -Is)"
echo "## tmux"
tmux ls 2>/dev/null | grep -E '^(androct2_|androct2_launcher)' || true
echo "## process"
pgrep -af 'run_androct_sgfe_experiment.py|launch_androct_second_main' || true
echo "## summaries"
find "$BASE/outputs" -name '*_summary.csv' | wc -l
echo "## jsonl failures"
find "$BASE/outputs" -name '*.jsonl' -print0 2>/dev/null | xargs -0 grep -H '\"status\": \"failed\"' 2>/dev/null | tail -20 || true
echo "## launch log"
tail -40 "$BASE/logs/launch_second_main.log" 2>/dev/null || true
"""
            put_text(sftp, f"{args.remote_dir}/scripts/monitor_androct_second_main.sh", monitor, 0o755)
        finally:
            sftp.close()

        code, out, err = run(
            client,
            f"tmux kill-session -t androct2_launcher 2>/dev/null || true; "
            f"tmux new-session -d -s androct2_launcher 'bash {quote(args.remote_dir + '/scripts/launch_androct_second_main.sh')}'; "
            f"bash {quote(args.remote_dir + '/scripts/monitor_androct_second_main.sh')}",
        )
        print(out)
        if err:
            print(err)
        if code != 0:
            raise RuntimeError(err or out)
    finally:
        client.close()


if __name__ == "__main__":
    main()
