#!/usr/bin/env python3
"""AndroCT support-gated feature-group validation.

This script builds a lightweight external validation for the CIKM paper:
source-trained platform-call group models are scored on a small labeled target
support set and evaluated under emulator/real-device runtime shift.

The split is hash-disjoint between source training and target support/query to
avoid the same APK appearing in both source and target evaluation.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import re
import tarfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import train_test_split


CALL_RE = re.compile(r"->\s*<([^:>]+):\s*([^>]+)>")
METHOD_RE = re.compile(r"([A-Za-z_$][\w$<>]*)\s*\(")
TOKEN_CLEAN_RE = re.compile(r"[^A-Za-z0-9_.$<>]+")


GROUPS = ["android_api", "java_api", "intent", "all_platform"]


def clean_token(text: str) -> str:
    text = TOKEN_CLEAN_RE.sub("_", text.strip())
    text = text.strip("_")
    return text[:180]


def method_token(class_name: str, signature_tail: str) -> str:
    m = METHOD_RE.search(signature_tail)
    method = m.group(1) if m else signature_tail.split(":", 1)[0].split()[0]
    return clean_token(f"{class_name}.{method}")


def parse_log_bytes(data: bytes, max_lines: int) -> dict[str, str]:
    groups: dict[str, list[str]] = {g: [] for g in GROUPS}
    for i, raw in enumerate(data.splitlines()):
        if i >= max_lines:
            break
        line = raw.decode("utf-8", "ignore").strip()
        if not line:
            continue
        if "[ Intent sent ]" in line:
            groups["intent"].append("intent_sent")
            groups["all_platform"].append("intent_sent")
            continue
        if line.startswith(("Action=", "PackageName=", "DataString=", "DataURI=", "Scheme=", "Flags=", "Type=", "Extras=", "Component=")):
            key, _, val = line.partition("=")
            key_tok = f"intent_{key.lower()}"
            groups["intent"].append(key_tok)
            groups["all_platform"].append(key_tok)
            if val and val != "null":
                val_tok = clean_token(f"{key.lower()}_{val}")
                if key in {"Action", "Scheme", "Type"}:
                    groups["intent"].append(val_tok)
                    groups["all_platform"].append(val_tok)
            continue
        m = CALL_RE.search(line)
        if not m:
            continue
        cls = m.group(1)
        tok = method_token(cls, m.group(2))
        if cls.startswith("android."):
            groups["android_api"].append(tok)
            groups["all_platform"].append(tok)
        elif cls.startswith(("java.", "javax.", "org.apache.", "org.json.", "dalvik.")):
            groups["java_api"].append(tok)
            groups["all_platform"].append(tok)
    return {g: " ".join(v) if v else "__empty__" for g, v in groups.items()}


def tar_members_by_hash(path: Path) -> dict[str, str]:
    members: dict[str, str] = {}
    with tarfile.open(path, "r:gz") as tf:
        for member in tf:
            if not member.isfile() or not member.name.endswith(".apk.logcat"):
                continue
            name = Path(member.name).name
            sha = name.replace(".apk.logcat", "")
            members[sha] = member.name
    return members


def tar_name(data_dir: Path, domain: str, label_name: str, year: int) -> Path:
    if domain == "emu":
        return data_dir / f"trace-{label_name}-{year}.tar.gz"
    if domain == "real":
        return data_dir / f"real-trace-{label_name}-{year}.tar.gz"
    raise ValueError(domain)


def build_records(args: argparse.Namespace, cache_path: Path) -> list[dict]:
    label_map = {"benign": 0, "malware": 1}
    records: list[dict] = []
    for year in args.years:
        for label_name, label in label_map.items():
            emu_tar = tar_name(args.data_dir, "emu", label_name, year)
            real_tar = tar_name(args.data_dir, "real", label_name, year)
            if not emu_tar.exists() or not real_tar.exists():
                print(f"[skip] missing pair {year} {label_name}", flush=True)
                continue
            emu_members = tar_members_by_hash(emu_tar)
            real_members = tar_members_by_hash(real_tar)
            overlap = sorted(set(emu_members) & set(real_members))
            if args.max_apps_per_year_class:
                rng = random.Random(args.sample_seed + year * 17 + label)
                rng.shuffle(overlap)
                overlap = sorted(overlap[: args.max_apps_per_year_class])
            print(f"[load] {year} {label_name}: overlap={len(overlap)}", flush=True)
            wanted = set(overlap)
            for domain, tar_path, members in [
                ("emu", emu_tar, emu_members),
                ("real", real_tar, real_members),
            ]:
                with tarfile.open(tar_path, "r:gz") as tf:
                    for sha in overlap:
                        member_name = members.get(sha)
                        if not member_name or sha not in wanted:
                            continue
                        f = tf.extractfile(member_name)
                        if f is None:
                            continue
                        texts = parse_log_bytes(f.read(), args.max_lines_per_log)
                        records.append(
                            {
                                "domain": domain,
                                "year": year,
                                "label": label,
                                "label_name": label_name,
                                "sha": sha,
                                "texts": texts,
                            }
                        )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_path, "wt", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec, sort_keys=True) + "\n")
    return records


def load_records(args: argparse.Namespace) -> list[dict]:
    year_key = "-".join(str(y) for y in args.years)
    cache_path = args.cache_dir / f"androct_records_y{year_key}_maxlines{args.max_lines_per_log}_maxapps{args.max_apps_per_year_class or 'all'}.jsonl.gz"
    if cache_path.exists() and not args.rebuild_cache:
        records = []
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    records.append(json.loads(line))
            print(f"[cache] loaded {len(records)} records from {cache_path}", flush=True)
            return records
        except (EOFError, gzip.BadGzipFile, OSError, json.JSONDecodeError) as exc:
            print(f"[cache-warning] rebuilding unreadable cache {cache_path}: {exc!r}", flush=True)
            cache_path.unlink(missing_ok=True)
    return build_records(args, cache_path)


def make_model(seed: int) -> LogisticRegression:
    return LogisticRegression(
        solver="liblinear",
        class_weight="balanced",
        max_iter=1000,
        random_state=seed,
    )


def metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
    }


def choose_target_split(
    records: list[dict],
    source_domain: str,
    target_domain: str,
    seed: int,
    k: int,
    max_query_per_class: int,
    min_source_per_class: int,
):
    rng = random.Random(seed)
    by_target = defaultdict(list)
    for rec in records:
        if rec["domain"] == target_domain:
            by_target[rec["label"]].append(rec)
    support, query = [], []
    for label in [0, 1]:
        items = list(by_target[label])
        rng.shuffle(items)
        if len(items) < k + 10:
            raise RuntimeError(f"not enough target records for label={label}: {len(items)}")
        support.extend(items[:k])
        q = items[k:]
        if min_source_per_class:
            # Keep enough hash-disjoint source examples for low-overlap years
            # such as 2011, 2016, 2017, and 2019.
            q = q[: max(0, len(items) - k - min_source_per_class)]
        if max_query_per_class:
            q = q[:max_query_per_class]
        query.extend(q)
    holdout = {rec["sha"] for rec in support + query}
    source = [rec for rec in records if rec["domain"] == source_domain and rec["sha"] not in holdout]
    source_labels = {rec["label"] for rec in source}
    if source_labels != {0, 1}:
        counts = {label: sum(1 for rec in source if rec["label"] == label) for label in [0, 1]}
        raise RuntimeError(f"source split missing class after holdout: counts={counts}")
    return source, support, query


def texts_labels(recs: list[dict], group: str):
    return [r["texts"].get(group, "__empty__") for r in recs], np.array([r["label"] for r in recs], dtype=int)


def fit_group(group: str, source: list[dict], support: list[dict], query: list[dict], seed: int):
    sx, sy = texts_labels(source, group)
    vx_train, vx_val, y_train, y_val = train_test_split(
        sx, sy, test_size=0.25, random_state=seed, stratify=sy
    )
    vec_cv = CountVectorizer(min_df=2, max_features=20000, token_pattern=r"(?u)\b\S+\b")
    xtr = vec_cv.fit_transform(vx_train)
    xva = vec_cv.transform(vx_val)
    cv_model = make_model(seed)
    cv_model.fit(xtr, y_train)
    source_cv = float(balanced_accuracy_score(y_val, cv_model.predict(xva)))

    vec = CountVectorizer(min_df=2, max_features=20000, token_pattern=r"(?u)\b\S+\b")
    xs = vec.fit_transform(sx)
    model = make_model(seed)
    model.fit(xs, sy)

    sup_x, sup_y = texts_labels(support, group)
    qry_x, qry_y = texts_labels(query, group)
    sup_mat = vec.transform(sup_x)
    qry_mat = vec.transform(qry_x)
    support_pred = model.predict(sup_mat)
    query_pred = model.predict(qry_mat)
    support_ba = float(balanced_accuracy_score(sup_y, support_pred))
    query_metrics = metrics(qry_y, query_pred)
    query_proba = model.predict_proba(qry_mat)
    return {
        "group": group,
        "vectorizer": vec,
        "model": model,
        "source_cv": source_cv,
        "support_ba": support_ba,
        "query_metrics": query_metrics,
        "query_pred": query_pred,
        "query_proba": query_proba,
        "query_y": qry_y,
    }


def proba_to_pred(proba: np.ndarray, classes: np.ndarray | None = None) -> np.ndarray:
    return np.argmax(proba, axis=1)


def weighted_pred(group_results: dict[str, dict], groups: list[str], weights: np.ndarray) -> np.ndarray:
    proba = None
    for w, g in zip(weights, groups):
        gp = group_results[g]["query_proba"]
        proba = gp * w if proba is None else proba + gp * w
    return proba_to_pred(proba)


def run_one(records: list[dict], args: argparse.Namespace, split: str, seed: int) -> list[dict]:
    source_domain, target_domain = ("emu", "real") if split == "emu_to_real" else ("real", "emu")
    source, support, query = choose_target_split(
        records,
        source_domain,
        target_domain,
        seed,
        args.k_shot,
        args.max_query_per_class,
        args.min_source_per_class,
    )
    yq = np.array([r["label"] for r in query], dtype=int)
    out: list[dict] = []
    group_results = {}
    for group in GROUPS:
        gr = fit_group(group, source, support, query, seed)
        group_results[group] = gr
        out.append(
            {
                "dataset": "AndroCT",
                "years": args.years,
                "split": split,
                "seed": seed,
                "k_shot": args.k_shot,
                "method": "fixed_group",
                "feature_group": group,
                "metrics": gr["query_metrics"],
                "source_cv": gr["source_cv"],
                "support_ba": gr["support_ba"],
                "n_source": len(source),
                "n_support": len(support),
                "n_query": len(query),
                "max_lines_per_log": args.max_lines_per_log,
            }
        )

    src_scores = np.array([group_results[g]["source_cv"] for g in GROUPS], dtype=float)
    sup_scores = np.array([group_results[g]["support_ba"] for g in GROUPS], dtype=float)
    for tau in args.taus:
        methods = {
            "support_gated_softmax": softmax(sup_scores / tau),
            "source_cv_softmax": softmax(src_scores / tau),
            "uniform_ensemble": np.ones(len(GROUPS), dtype=float) / len(GROUPS),
        }
        rng = np.random.default_rng(seed + int(tau * 1000))
        perm_labels = np.array([r["label"] for r in support], dtype=int)
        rng.shuffle(perm_labels)
        perm_scores = []
        for g in GROUPS:
            sup_x, _ = texts_labels(support, g)
            mat = group_results[g]["vectorizer"].transform(sup_x)
            pred = group_results[g]["model"].predict(mat)
            perm_scores.append(float(balanced_accuracy_score(perm_labels, pred)))
        methods["permuted_support_softmax"] = softmax(np.array(perm_scores) / tau)
        for method, weights in methods.items():
            pred = weighted_pred(group_results, GROUPS, weights)
            out.append(
                {
                    "dataset": "AndroCT",
                    "years": args.years,
                    "split": split,
                    "seed": seed,
                    "k_shot": args.k_shot,
                    "tau": tau,
                    "method": method,
                    "feature_groups": GROUPS,
                    "weights": {g: float(w) for g, w in zip(GROUPS, weights)},
                    "source_cv_scores": {g: float(s) for g, s in zip(GROUPS, src_scores)},
                    "support_scores": {g: float(s) for g, s in zip(GROUPS, sup_scores)},
                    "metrics": metrics(yq, pred),
                    "n_source": len(source),
                    "n_support": len(support),
                    "n_query": len(query),
                    "max_lines_per_log": args.max_lines_per_log,
                }
            )

    best_src = GROUPS[int(np.argmax(src_scores))]
    best_sup = GROUPS[int(np.argmax(sup_scores))]
    for method, group in [("source_cv_selected_group", best_src), ("top1_support_group", best_sup)]:
        pred = group_results[group]["query_pred"]
        out.append(
            {
                "dataset": "AndroCT",
                "years": args.years,
                "split": split,
                "seed": seed,
                "k_shot": args.k_shot,
                "method": method,
                "feature_group": group,
                "metrics": metrics(yq, pred),
                "source_cv_scores": {g: float(s) for g, s in zip(GROUPS, src_scores)},
                "support_scores": {g: float(s) for g, s in zip(GROUPS, sup_scores)},
                "n_source": len(source),
                "n_support": len(support),
                "n_query": len(query),
                "max_lines_per_log": args.max_lines_per_log,
            }
        )
    return out


def summarize(jsonl_path: Path, summary_csv: Path, summary_md: Path) -> None:
    rows = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            met = rec.get("metrics", {})
            rows.append(
                {
                    "method": rec.get("method"),
                    "split": rec.get("split"),
                    "tau": rec.get("tau", ""),
                    "feature_group": rec.get("feature_group", ""),
                    "k_shot": rec.get("k_shot"),
                    "seed": rec.get("seed"),
                    "balanced_accuracy": met.get("balanced_accuracy"),
                    "accuracy": met.get("accuracy"),
                    "macro_f1": met.get("macro_f1"),
                    "n_source": rec.get("n_source"),
                    "n_query": rec.get("n_query"),
                }
            )
    df = pd.DataFrame(rows)
    group_cols = ["split", "method", "tau", "feature_group"]
    summ = (
        df.groupby(group_cols, dropna=False)
        .agg(
            n=("balanced_accuracy", "count"),
            ba_mean=("balanced_accuracy", "mean"),
            ba_std=("balanced_accuracy", "std"),
            f1_mean=("macro_f1", "mean"),
            acc_mean=("accuracy", "mean"),
            n_source_mean=("n_source", "mean"),
            n_query_mean=("n_query", "mean"),
        )
        .reset_index()
        .sort_values(["split", "ba_mean"], ascending=[True, False])
    )
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    summ.to_csv(summary_csv, index=False)
    with summary_md.open("w", encoding="utf-8") as out:
        out.write("# AndroCT SGFE Summary\n\n")
        out.write(f"Source records: `{jsonl_path}`\n\n")
        out.write("```text\n")
        out.write(summ.to_string(index=False))
        out.write("\n```")
        out.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--cache-dir", type=Path, default=Path("cache"))
    ap.add_argument("--years", type=int, nargs="+", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    ap.add_argument("--splits", nargs="+", default=["emu_to_real", "real_to_emu"])
    ap.add_argument("--k-shot", type=int, default=5)
    ap.add_argument("--taus", type=float, nargs="+", default=[0.05, 0.10])
    ap.add_argument("--max-query-per-class", type=int, default=600)
    ap.add_argument("--min-source-per-class", type=int, default=20)
    ap.add_argument("--max-lines-per-log", type=int, default=5000)
    ap.add_argument("--max-apps-per-year-class", type=int, default=0)
    ap.add_argument("--sample-seed", type=int, default=20260514)
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    records = load_records(args)
    run_id = f"androct_y{'-'.join(map(str,args.years))}_k{args.k_shot}_q{args.max_query_per_class}_lines{args.max_lines_per_log}"
    jsonl_path = args.out_dir / f"{run_id}.jsonl"
    meta = {
        "run_id": run_id,
        "years": args.years,
        "seeds": args.seeds,
        "splits": args.splits,
        "groups": GROUPS,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with (args.out_dir / f"{run_id}_meta.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    with jsonl_path.open("w", encoding="utf-8") as out:
        for split in args.splits:
            for seed in args.seeds:
                print(f"[run] {run_id} split={split} seed={seed}", flush=True)
                try:
                    for rec in run_one(records, args, split, seed):
                        out.write(json.dumps(rec, sort_keys=True) + "\n")
                        out.flush()
                except Exception as e:
                    fail = {
                        "dataset": "AndroCT",
                        "years": args.years,
                        "split": split,
                        "seed": seed,
                        "status": "failed",
                        "error": repr(e),
                    }
                    out.write(json.dumps(fail, sort_keys=True) + "\n")
                    out.flush()
                    print(f"[failed] {split} seed={seed}: {e!r}", flush=True)
    summarize(jsonl_path, args.out_dir / f"{run_id}_summary.csv", args.out_dir / f"{run_id}_summary.md")
    print(f"[done] {jsonl_path}", flush=True)


if __name__ == "__main__":
    main()
