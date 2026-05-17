#!/usr/bin/env python3
"""Parallel SFTP uploader for selected AndroCT archives.

Reads the SSH password from MP_PASS. The password must not be written to disk.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import time
from pathlib import Path

import paramiko


FILES = [
    f"{domain}-{kind}-{year}.tar.gz"
    for year in range(2010, 2020)
    for domain in ("trace", "real-trace")
    for kind in ("benign", "malware")
] + [
    "benign-dynamic.tar.gz",
    "benign-static.tar.gz",
    "malware-dynamic.tar.gz",
    "malware-static.tar.gz",
]


def log(msg: str, log_path: Path) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def connect(host: str, port: int, user: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=port,
        username=user,
        password=password,
        timeout=60,
        banner_timeout=60,
        auth_timeout=60,
    )
    return client


def remote_valid(client: paramiko.SSHClient, remote_path: str, expected_size: int) -> bool:
    cmd = f"[ -s {quote(remote_path)} ] && [ \"$(stat -c%s {quote(remote_path)})\" = {expected_size} ] && tar -tzf {quote(remote_path)} >/dev/null 2>&1"
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.channel.recv_exit_status() == 0


def quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def upload_one(args_tuple: tuple[str, argparse.Namespace]) -> str:
    name, args = args_tuple
    password = os.environ.get("MP_PASS")
    if not password:
        raise RuntimeError("MP_PASS is not set")
    local_path = args.local_dir / name
    if not local_path.exists():
        raise FileNotFoundError(local_path)
    size = local_path.stat().st_size
    remote_path = f"{args.remote_dir}/data/AndroCT/{name}"
    tmp_path = remote_path + ".upload"

    client = connect(args.host, args.port, args.user, password)
    try:
        stdin, stdout, stderr = client.exec_command(f"mkdir -p {quote(args.remote_dir + '/data/AndroCT')}")
        stdout.channel.recv_exit_status()
        if remote_valid(client, remote_path, size):
            return f"skip valid {name} {size / 1024 / 1024:.1f} MiB"

        sftp = client.open_sftp()
        try:
            for p in (tmp_path,):
                try:
                    sftp.remove(p)
                except OSError:
                    pass
            started = time.time()
            sftp.put(str(local_path), tmp_path)
            try:
                sftp.remove(remote_path)
            except OSError:
                pass
            sftp.rename(tmp_path, remote_path)
        finally:
            sftp.close()

        if not remote_valid(client, remote_path, size):
            raise RuntimeError(f"remote validation failed: {name}")
        elapsed = max(time.time() - started, 0.1)
        mb = size / 1024 / 1024
        return f"uploaded {name} {mb:.1f} MiB in {elapsed:.1f}s ({mb / elapsed:.2f} MiB/s)"
    finally:
        client.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--user", default="root")
    ap.add_argument("--local-dir", type=Path, default=Path(r"F:\work\dataset\AndroCT"))
    ap.add_argument("--remote-dir", default="/root/experiments/androct_sgfe")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--log", type=Path, default=Path(r"F:\work\submissions\network_agent_safety\logs\androct_upload.log"))
    args = ap.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)

    log(f"start workers={args.workers}", args.log)
    failures: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(upload_one, (name, args)): name for name in FILES}
        for fut in cf.as_completed(futures):
            name = futures[fut]
            try:
                log(fut.result(), args.log)
            except Exception as exc:
                failures.append(name)
                log(f"FAILED {name}: {exc!r}", args.log)
    if failures:
        raise SystemExit(f"failed uploads: {failures}")
    log("all uploads complete", args.log)


if __name__ == "__main__":
    main()
