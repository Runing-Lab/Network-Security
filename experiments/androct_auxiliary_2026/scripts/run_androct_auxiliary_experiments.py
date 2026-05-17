#!/usr/bin/env python3
"""AndroCT auxiliary experiments mirroring KronoDroid reviewer checks.

The AndroCT main experiment works on text-like logcat call traces, while the
original KronoDroid auxiliary scripts work on tabular malware features. This
script therefore reuses the AndroCT parser/split protocol and copies the
experimental questions, not the KronoDroid feature matrix implementation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.naive_bayes import ComplementNB
from sklearn.neighbors import KNeighborsClassifier, NearestCentroid
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def metric_dict(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    labels = sorted(set(np.asarray(y_true, dtype=int).tolist()))
    pred_classes, pred_counts = np.unique(y_pred, return_counts=True)
    zero_recall = 0
    for label in labels:
        mask = y_true == label
        if np.any(mask) and float(np.mean(y_pred[mask] == label)) == 0.0:
            zero_recall += 1
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "n_test": int(len(y_true)),
        "n_classes_test": int(len(labels)),
        "n_predicted_classes": int(len(pred_classes)),
        "n_zero_recall_classes": int(zero_recall),
        "predicted_class_hist": {str(int(c)): int(n) for c, n in zip(pred_classes, pred_counts)},
    }


def append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def texts_labels(records: list[dict], group: str) -> tuple[list[str], np.ndarray]:
    return [r["texts"].get(group, "__empty__") for r in records], np.array([r["label"] for r in records], dtype=int)


def make_vectorizer(max_features: int) -> CountVectorizer:
    return CountVectorizer(min_df=2, max_features=max_features, token_pattern=r"(?u)\b\S+\b")


def make_aux_model(name: str, seed: int, n_estimators: int, n_jobs: int):
    if name == "logreg_balanced":
        return LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            max_iter=1200,
            random_state=seed,
        )
    if name == "extratrees_sqrt_balanced":
        return ExtraTreesClassifier(
            n_estimators=n_estimators,
            max_features="sqrt",
            class_weight="balanced",
            random_state=seed,
            n_jobs=n_jobs,
        )
    if name == "rf_sqrt_balanced":
        return RandomForestClassifier(
            n_estimators=n_estimators,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=seed,
            n_jobs=n_jobs,
        )
    if name == "complement_nb":
        return ComplementNB(alpha=1.0)
    raise ValueError(f"unknown model {name}")


def fit_predict_text(
    *,
    train_records: list[dict],
    query_records: list[dict],
    group: str,
    model_name: str,
    seed: int,
    n_estimators: int,
    n_jobs: int,
    max_features: int,
    sample_weight: np.ndarray | None = None,
):
    train_x, train_y = texts_labels(train_records, group)
    query_x, query_y = texts_labels(query_records, group)
    vec = make_vectorizer(max_features)
    x_train = vec.fit_transform(train_x)
    x_query = vec.transform(query_x)
    model = make_aux_model(model_name, seed, n_estimators, n_jobs)
    try:
        model.fit(x_train, train_y, sample_weight=sample_weight)
    except TypeError:
        model.fit(x_train, train_y)
    pred = model.predict(x_query)
    proba = model.predict_proba(x_query) if hasattr(model, "predict_proba") else None
    return {
        "vectorizer": vec,
        "model": model,
        "y_query": query_y,
        "pred": pred,
        "proba": proba,
        "metrics": metric_dict(query_y, pred),
    }


def prepare_split(andmod, records: list[dict], args: argparse.Namespace, split: str, seed: int):
    source_domain, target_domain = ("emu", "real") if split == "emu_to_real" else ("real", "emu")
    source, support, query = andmod.choose_target_split(
        records,
        source_domain,
        target_domain,
        seed,
        args.k_shot,
        args.max_query_per_class,
        args.min_source_per_class,
    )
    return source_domain, target_domain, source, support, query


def run_source_plus_support(
    *,
    records_path: Path,
    andmod,
    records: list[dict],
    args: argparse.Namespace,
    split: str,
    seed: int,
) -> None:
    source_domain, target_domain, source, support, query = prepare_split(andmod, records, args, split, seed)
    train = source + support
    weights = np.ones(len(train), dtype=float)
    weights[len(source) :] = args.support_weight
    for model_name in args.warm_models:
        t0 = time.time()
        rec = {
            "run_id": f"ANDROCT-AUX-warmstart-{split}-k{args.k_shot}-s{seed}-{model_name}",
            "experiment": "source_plus_support_warm_start",
            "status": "STARTED",
            "started_at": utc_now(),
            "dataset": "AndroCT",
            "years": args.years,
            "split": split,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "seed": seed,
            "k_shot": args.k_shot,
            "group": "all_platform",
            "model": model_name,
            "support_weight": args.support_weight,
            "n_source": len(source),
            "n_support": len(support),
            "n_query": len(query),
        }
        try:
            pred = fit_predict_text(
                train_records=train,
                query_records=query,
                group="all_platform",
                model_name=model_name,
                seed=seed,
                n_estimators=args.n_estimators,
                n_jobs=args.model_jobs,
                max_features=args.max_features,
                sample_weight=weights,
            )
            rec.update({"status": "DONE", "metrics": pred["metrics"]})
        except Exception as exc:
            rec.update({"status": "FAILED", "error": repr(exc)})
        rec.update({"ended_at": utc_now(), "duration_sec": round(time.time() - t0, 3)})
        append_jsonl(records_path, rec)


def run_allfeature_selection(
    *,
    records_path: Path,
    andmod,
    records: list[dict],
    args: argparse.Namespace,
    split: str,
    seed: int,
) -> None:
    source_domain, target_domain, source, support, query = prepare_split(andmod, records, args, split, seed)
    candidates = []
    for model_name in args.selection_models:
        t0 = time.time()
        rec = {
            "run_id": f"ANDROCT-AUX-allselect-fixed-{split}-k{args.k_shot}-s{seed}-{model_name}",
            "experiment": "allfeature_support_selection",
            "status": "STARTED",
            "started_at": utc_now(),
            "dataset": "AndroCT",
            "years": args.years,
            "split": split,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "seed": seed,
            "k_shot": args.k_shot,
            "method": "allfeature_candidate",
            "candidate": model_name,
            "group": "all_platform",
            "n_source": len(source),
            "n_support": len(support),
            "n_query": len(query),
        }
        try:
            sup = fit_predict_text(
                train_records=source,
                query_records=support,
                group="all_platform",
                model_name=model_name,
                seed=seed,
                n_estimators=args.n_estimators,
                n_jobs=args.model_jobs,
                max_features=args.max_features,
            )
            qry = fit_predict_text(
                train_records=source,
                query_records=query,
                group="all_platform",
                model_name=model_name,
                seed=seed,
                n_estimators=args.n_estimators,
                n_jobs=args.model_jobs,
                max_features=args.max_features,
            )
            rec.update(
                {
                    "status": "DONE",
                    "support_metrics": sup["metrics"],
                    "query_metrics": qry["metrics"],
                }
            )
            candidates.append(rec)
        except Exception as exc:
            rec.update({"status": "FAILED", "error": repr(exc)})
        rec.update({"ended_at": utc_now(), "duration_sec": round(time.time() - t0, 3)})
        append_jsonl(records_path, rec)

    done = [r for r in candidates if r.get("status") == "DONE"]
    if done:
        selected = max(
            done,
            key=lambda r: (r["support_metrics"]["balanced_accuracy"], r["candidate"]),
        )
        rec = dict(selected)
        rec.update(
            {
                "run_id": f"ANDROCT-AUX-allselect-selected-{split}-k{args.k_shot}-s{seed}",
                "method": "support_selected_allfeature_model",
                "candidate": "",
                "selected_candidate": selected["candidate"],
            }
        )
        append_jsonl(records_path, rec)


def fit_group_models(
    *,
    source: list[dict],
    support: list[dict],
    query: list[dict],
    groups: list[str],
    seed: int,
    max_features: int,
) -> dict[str, dict]:
    group_results = {}
    for group in groups:
        sx, sy = texts_labels(source, group)
        sup_x, sup_y = texts_labels(support, group)
        qry_x, qry_y = texts_labels(query, group)
        vec = make_vectorizer(max_features)
        xs = vec.fit_transform(sx)
        model = LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            max_iter=1200,
            random_state=seed,
        )
        model.fit(xs, sy)
        sup_mat = vec.transform(sup_x)
        qry_mat = vec.transform(qry_x)
        sup_pred = model.predict(sup_mat)
        qry_pred = model.predict(qry_mat)
        group_results[group] = {
            "vectorizer": vec,
            "model": model,
            "support_y": sup_y,
            "query_y": qry_y,
            "support_pred": sup_pred,
            "query_pred": qry_pred,
            "query_proba": model.predict_proba(qry_mat),
            "support_ba": float(balanced_accuracy_score(sup_y, sup_pred)),
            "query_metrics": metric_dict(qry_y, qry_pred),
        }
    return group_results


def weighted_prediction(group_results: dict[str, dict], groups: list[str], weights: np.ndarray) -> np.ndarray:
    proba = None
    for group, weight in zip(groups, weights):
        cur = group_results[group]["query_proba"] * weight
        proba = cur if proba is None else proba + cur
    return np.argmax(proba, axis=1)


def corrupt_labels(labels: np.ndarray, rate: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = labels.copy()
    mask = rng.random(len(out)) < rate
    for idx in np.where(mask)[0]:
        choices = [v for v in np.unique(labels) if v != out[idx]]
        if choices:
            out[idx] = int(rng.choice(choices))
    return out


def run_support_noise(
    *,
    records_path: Path,
    andmod,
    records: list[dict],
    args: argparse.Namespace,
    split: str,
    seed: int,
) -> None:
    source_domain, target_domain, source, support, query = prepare_split(andmod, records, args, split, seed)
    groups = list(andmod.GROUPS)
    group_results = fit_group_models(
        source=source,
        support=support,
        query=query,
        groups=groups,
        seed=seed,
        max_features=args.max_features,
    )
    yq = group_results[groups[0]]["query_y"]
    y_support = group_results[groups[0]]["support_y"]
    for rate in args.noise_rates:
        t0 = time.time()
        noisy_y = corrupt_labels(y_support, rate, seed + int(rate * 10000) + 17)
        support_scores = {
            group: float(balanced_accuracy_score(noisy_y, group_results[group]["support_pred"]))
            for group in groups
        }
        for tau in args.taus:
            weights = softmax(np.array([support_scores[g] for g in groups], dtype=float) / tau)
            pred = weighted_prediction(group_results, groups, weights)
            rec = {
                "run_id": f"ANDROCT-AUX-labelnoise-{split}-k{args.k_shot}-s{seed}-r{rate:g}-tau{tau:g}",
                "experiment": "label_noise_support_signal",
                "status": "DONE",
                "started_at": utc_now(),
                "ended_at": utc_now(),
                "duration_sec": round(time.time() - t0, 3),
                "dataset": "AndroCT",
                "years": args.years,
                "split": split,
                "source_domain": source_domain,
                "target_domain": target_domain,
                "seed": seed,
                "k_shot": args.k_shot,
                "tau": tau,
                "support_label_noise_rate": rate,
                "feature_groups": groups,
                "support_scores": support_scores,
                "weights": {g: float(w) for g, w in zip(groups, weights)},
                "metrics": metric_dict(yq, pred),
                "n_source": len(source),
                "n_support": len(support),
                "n_query": len(query),
            }
            append_jsonl(records_path, rec)


def make_support_only_model(name: str):
    if name == "nearest_centroid":
        return make_pipeline(StandardScaler(with_mean=False), NearestCentroid())
    if name == "knn1":
        return make_pipeline(StandardScaler(with_mean=False), KNeighborsClassifier(n_neighbors=1))
    if name == "complement_nb":
        return ComplementNB(alpha=1.0)
    raise ValueError(f"unknown support-only model {name}")


def run_support_only(
    *,
    records_path: Path,
    andmod,
    records: list[dict],
    args: argparse.Namespace,
    split: str,
    seed: int,
) -> None:
    source_domain, target_domain, source, support, query = prepare_split(andmod, records, args, split, seed)
    sup_x, sup_y = texts_labels(support, "all_platform")
    qry_x, qry_y = texts_labels(query, "all_platform")
    for model_name in args.support_only_models:
        t0 = time.time()
        rec = {
            "run_id": f"ANDROCT-AUX-supportonly-{split}-k{args.k_shot}-s{seed}-{model_name}",
            "experiment": "support_only_target_baseline",
            "status": "STARTED",
            "started_at": utc_now(),
            "dataset": "AndroCT",
            "years": args.years,
            "split": split,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "seed": seed,
            "k_shot": args.k_shot,
            "method": model_name,
            "group": "all_platform",
            "n_support": len(support),
            "n_query": len(query),
        }
        try:
            vec = make_vectorizer(args.max_features)
            x_sup = vec.fit_transform(sup_x)
            x_qry = vec.transform(qry_x)
            model = make_support_only_model(model_name)
            model.fit(x_sup, sup_y)
            pred = model.predict(x_qry)
            rec.update({"status": "DONE", "metrics": metric_dict(qry_y, pred)})
        except Exception as exc:
            rec.update({"status": "FAILED", "error": repr(exc)})
        rec.update({"ended_at": utc_now(), "duration_sec": round(time.time() - t0, 3)})
        append_jsonl(records_path, rec)


def diagonal_coral(x_source: np.ndarray, x_target_ref: np.ndarray, eps: float) -> np.ndarray:
    src_mean = x_source.mean(axis=0, keepdims=True)
    tgt_mean = x_target_ref.mean(axis=0, keepdims=True)
    src_std = x_source.std(axis=0, keepdims=True) + eps
    tgt_std = x_target_ref.std(axis=0, keepdims=True) + eps
    return ((x_source - src_mean) / src_std) * tgt_std + tgt_mean


def run_svd_coral(
    *,
    records_path: Path,
    andmod,
    records: list[dict],
    args: argparse.Namespace,
    split: str,
    seed: int,
) -> None:
    source_domain, target_domain, source, support, query = prepare_split(andmod, records, args, split, seed)
    target_pool = support + query
    source_x, source_y = texts_labels(source, "all_platform")
    support_x, _ = texts_labels(support, "all_platform")
    query_x, query_y = texts_labels(query, "all_platform")
    pool_x, _ = texts_labels(target_pool, "all_platform")
    t0 = time.time()
    rec = {
        "run_id": f"ANDROCT-AUX-svdcoral-{split}-k{args.k_shot}-s{seed}",
        "experiment": "svd_diagonal_coral_da",
        "status": "STARTED",
        "started_at": utc_now(),
        "dataset": "AndroCT",
        "years": args.years,
        "split": split,
        "source_domain": source_domain,
        "target_domain": target_domain,
        "seed": seed,
        "k_shot": args.k_shot,
        "group": "all_platform",
        "n_source": len(source),
        "n_support": len(support),
        "n_query": len(query),
        "n_target_ref": len(target_pool),
        "svd_components_requested": args.svd_components,
    }
    try:
        vec = make_vectorizer(args.max_features)
        x_all = vec.fit_transform(source_x + pool_x)
        x_source_counts = x_all[: len(source_x)]
        x_pool_counts = x_all[len(source_x) :]
        x_query_counts = vec.transform(query_x)
        max_comp = min(args.svd_components, x_source_counts.shape[0] - 1, x_all.shape[1] - 1)
        if max_comp < 2:
            raise RuntimeError(f"not enough rank for SVD-CORAL: components={max_comp}")
        svd = TruncatedSVD(n_components=max_comp, random_state=seed)
        x_source = svd.fit_transform(x_source_counts)
        x_pool = svd.transform(x_pool_counts)
        x_query = svd.transform(x_query_counts)
        x_source_aligned = diagonal_coral(x_source, x_pool, args.coral_eps)
        model = LogisticRegression(max_iter=1500, class_weight="balanced", random_state=seed)
        model.fit(x_source_aligned, source_y)
        pred = model.predict(x_query)
        rec.update(
            {
                "status": "DONE",
                "svd_components_used": int(max_comp),
                "explained_variance_sum": float(np.sum(svd.explained_variance_ratio_)),
                "metrics": metric_dict(query_y, pred),
            }
        )
    except Exception as exc:
        rec.update({"status": "FAILED", "error": repr(exc)})
    rec.update({"ended_at": utc_now(), "duration_sec": round(time.time() - t0, 3)})
    append_jsonl(records_path, rec)


def flatten_metric_record(rec: dict) -> dict:
    metrics = rec.get("metrics") or rec.get("query_metrics") or {}
    support_metrics = rec.get("support_metrics") or {}
    return {
        "experiment": rec.get("experiment"),
        "status": rec.get("status"),
        "split": rec.get("split"),
        "k_shot": rec.get("k_shot"),
        "seed": rec.get("seed"),
        "method": rec.get("method", rec.get("model", "")),
        "candidate": rec.get("candidate", ""),
        "selected_candidate": rec.get("selected_candidate", ""),
        "group": rec.get("group", rec.get("feature_group", "")),
        "tau": rec.get("tau", ""),
        "noise_rate": rec.get("support_label_noise_rate", ""),
        "balanced_accuracy": metrics.get("balanced_accuracy"),
        "accuracy": metrics.get("accuracy"),
        "macro_f1": metrics.get("macro_f1"),
        "support_ba": support_metrics.get("balanced_accuracy"),
        "n_source": rec.get("n_source"),
        "n_support": rec.get("n_support"),
        "n_query": rec.get("n_query"),
        "error": rec.get("error", ""),
        "run_id": rec.get("run_id"),
    }


def summarize(records_path: Path, summary_csv: Path, summary_md: Path) -> None:
    rows = []
    with records_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    flat = pd.DataFrame([flatten_metric_record(r) for r in rows])
    flat.to_csv(summary_csv.with_name(summary_csv.stem + "_raw.csv"), index=False)
    done = flat[flat["status"] == "DONE"].copy()
    if done.empty:
        flat.to_csv(summary_csv, index=False)
        summary_md.write_text("# AndroCT Auxiliary Summary\n\nNo completed rows.\n", encoding="utf-8")
        return
    group_cols = ["experiment", "split", "k_shot", "method", "candidate", "selected_candidate", "group", "tau", "noise_rate"]
    summary = (
        done.groupby(group_cols, dropna=False)
        .agg(
            n=("balanced_accuracy", "count"),
            ba_mean=("balanced_accuracy", "mean"),
            ba_std=("balanced_accuracy", "std"),
            f1_mean=("macro_f1", "mean"),
            acc_mean=("accuracy", "mean"),
            support_ba_mean=("support_ba", "mean"),
        )
        .reset_index()
        .sort_values(["experiment", "split", "ba_mean"], ascending=[True, True, False])
    )
    summary.to_csv(summary_csv, index=False)
    with summary_md.open("w", encoding="utf-8") as out:
        out.write("# AndroCT Auxiliary Summary\n\n")
        out.write(f"- Records: `{records_path}`\n")
        out.write(f"- Completed rows: {len(done)} / {len(flat)}\n")
        out.write(f"- Summary CSV: `{summary_csv.name}`\n")
        out.write(f"- Raw flat CSV: `{summary_csv.stem}_raw.csv`\n\n")
        out.write("```text\n")
        out.write(summary.to_string(index=False))
        out.write("\n```\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--androct-script", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--splits", nargs="+", default=["emu_to_real", "real_to_emu"])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    parser.add_argument("--k-shot", type=int, default=5)
    parser.add_argument(
        "--blocks",
        nargs="+",
        default=["warm_start", "allfeature_select", "support_only", "label_noise", "svd_coral"],
    )
    parser.add_argument("--taus", type=float, nargs="+", default=[0.05, 0.10])
    parser.add_argument("--noise-rates", type=float, nargs="+", default=[0.0, 0.1, 0.3, 0.5])
    parser.add_argument("--warm-models", nargs="+", default=["logreg_balanced", "extratrees_sqrt_balanced"])
    parser.add_argument("--selection-models", nargs="+", default=["logreg_balanced", "extratrees_sqrt_balanced", "complement_nb"])
    parser.add_argument("--support-only-models", nargs="+", default=["nearest_centroid", "knn1", "complement_nb"])
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--model-jobs", type=int, default=1)
    parser.add_argument("--support-weight", type=float, default=5.0)
    parser.add_argument("--max-features", type=int, default=40000)
    parser.add_argument("--svd-components", type=int, default=128)
    parser.add_argument("--coral-eps", type=float, default=1e-6)
    parser.add_argument("--max-query-per-class", type=int, default=600)
    parser.add_argument("--min-source-per-class", type=int, default=20)
    parser.add_argument("--max-lines-per-log", type=int, default=5000)
    parser.add_argument("--max-apps-per-year-class", type=int, default=0)
    parser.add_argument("--sample-seed", type=int, default=20260514)
    parser.add_argument("--rebuild-cache", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    andmod = load_module(args.androct_script, "androct_sgfe_base")

    # The imported base script expects these attributes when building caches.
    base_ns = argparse.Namespace(**vars(args))
    records = andmod.load_records(base_ns)
    run_id = f"androct_aux_y{'-'.join(map(str,args.years))}_k{args.k_shot}"
    records_path = args.out_dir / f"{run_id}_records.jsonl"
    if records_path.exists():
        records_path.unlink()
    manifest = {
        "created_at": utc_now(),
        "run_id": run_id,
        "argv": sys.argv,
        "years": args.years,
        "splits": args.splits,
        "seeds": args.seeds,
        "k_shot": args.k_shot,
        "blocks": args.blocks,
        "base_androct_script": str(args.androct_script),
        "groups": list(andmod.GROUPS),
        "record_count": len(records),
    }
    (args.out_dir / f"{run_id}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for split in args.splits:
        for seed in args.seeds:
            print(f"[run] {run_id} split={split} seed={seed}", flush=True)
            if "warm_start" in args.blocks:
                run_source_plus_support(records_path=records_path, andmod=andmod, records=records, args=args, split=split, seed=seed)
            if "allfeature_select" in args.blocks:
                run_allfeature_selection(records_path=records_path, andmod=andmod, records=records, args=args, split=split, seed=seed)
            if "support_only" in args.blocks:
                run_support_only(records_path=records_path, andmod=andmod, records=records, args=args, split=split, seed=seed)
            if "label_noise" in args.blocks:
                run_support_noise(records_path=records_path, andmod=andmod, records=records, args=args, split=split, seed=seed)
            if "svd_coral" in args.blocks:
                run_svd_coral(records_path=records_path, andmod=andmod, records=records, args=args, split=split, seed=seed)

    summarize(
        records_path,
        args.out_dir / f"{run_id}_summary.csv",
        args.out_dir / f"{run_id}_summary.md",
    )
    print(f"[done] {records_path}", flush=True)


if __name__ == "__main__":
    main()
