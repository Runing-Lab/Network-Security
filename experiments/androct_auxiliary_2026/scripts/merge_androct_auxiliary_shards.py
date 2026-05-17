#!/usr/bin/env python3
"""Merge sharded pooled AndroCT auxiliary runs into formal K-level outputs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


YEARS = list(range(2010, 2020))
SPLITS = ["emu_to_real", "real_to_emu"]
SEEDS = list(range(10))


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def find_records(shard_dir: Path) -> Path:
    matches = sorted(shard_dir.glob("*_records.jsonl"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one records file in {shard_dir}, found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=Path("/root/experiments/androct_auxiliary"))
    parser.add_argument("--aux-script", type=Path, default=Path("/root/experiments/androct_auxiliary/scripts/run_androct_auxiliary_experiments.py"))
    parser.add_argument("--k-shot", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    aux = load_module(args.aux_script, "androct_aux_merge_base")
    shard_root = args.base_dir / "pooled_shards"
    formal_dir = args.base_dir / "outputs" / f"androct_aux_y2010_2019_k{args.k_shot}"
    year_key = "-".join(str(y) for y in YEARS)
    run_id = f"androct_aux_y{year_key}_k{args.k_shot}"
    records_path = formal_dir / f"{run_id}_records.jsonl"
    summary_csv = formal_dir / f"{run_id}_summary.csv"
    summary_md = formal_dir / f"{run_id}_summary.md"

    expected = []
    for split in SPLITS:
        for seed in SEEDS:
            expected.append(shard_root / f"androct_aux_pool_k{args.k_shot}_{split}_s{seed}")

    missing = []
    for shard in expected:
        if not list(shard.glob("*_summary.csv")):
            missing.append(str(shard))
    if missing:
        raise RuntimeError("missing shard summaries: " + json.dumps(missing[:20], indent=2))

    if formal_dir.exists() and args.force:
        backup = formal_dir.with_name(formal_dir.name + "_premerge_backup_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        shutil.move(str(formal_dir), str(backup))
    formal_dir.mkdir(parents=True, exist_ok=True)

    with records_path.open("w", encoding="utf-8") as out:
        for shard in expected:
            rec_path = find_records(shard)
            with rec_path.open("r", encoding="utf-8") as inp:
                for line in inp:
                    if line.strip():
                        out.write(line)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "k_shot": args.k_shot,
        "years": YEARS,
        "splits": SPLITS,
        "seeds": SEEDS,
        "shards": [str(p) for p in expected],
        "records_path": str(records_path),
        "summary_csv": str(summary_csv),
        "summary_md": str(summary_md),
    }
    (formal_dir / f"{run_id}_merge_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    aux.summarize(records_path, summary_csv, summary_md)
    print(json.dumps({"merged": str(formal_dir), "k_shot": args.k_shot, "records": str(records_path)}, indent=2))


if __name__ == "__main__":
    main()
