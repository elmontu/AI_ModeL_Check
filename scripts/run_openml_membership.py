#!/usr/bin/env python3
"""Run calibrated target/reference membership attacks with retained raw scores."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import beta
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_VERSION = 3
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_structural import (  # noqa: E402
    build_preprocessor,
    canonical_json,
    capped_indices,
    make_splits,
    model_parameters,
    row_ids,
    sha256_bytes,
    sha256_file,
    signature_histogram,
    write_json,
    write_json_gz,
)


def one_sided_clopper_pearson(successes: int, trials: int, confidence: float) -> tuple[float, float]:
    alpha = 1.0 - confidence
    lower = 0.0 if successes == 0 else float(beta.ppf(alpha, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(beta.ppf(confidence, successes + 1, trials - successes))
    return lower, upper


def per_record_loss(model: Any, X: np.ndarray, y: np.ndarray) -> np.ndarray:
    probability = np.asarray(model.predict_proba(X), dtype=float)
    selected = probability[np.arange(len(y)), y]
    return -np.log(np.clip(selected, 1e-300, 1.0))


def equalized_target(indices: np.ndarray, y: np.ndarray, size: int, seed: int) -> np.ndarray:
    if len(indices) < size:
        raise ValueError("target training split is smaller than reference split")
    if len(indices) == size:
        return np.sort(indices)
    selected, _ = train_test_split(indices, train_size=size, random_state=seed, stratify=y[indices])
    return np.sort(selected)


def member_halves(indices: np.ndarray, y: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    calibration, audit = train_test_split(indices, test_size=0.5, random_state=seed, stratify=y[indices])
    return np.sort(calibration), np.sort(audit)


def threshold_at_fpr(scores: np.ndarray, target_fpr: float) -> tuple[float, int]:
    allowed = int(math.floor(target_fpr * len(scores)))
    values, counts = np.unique(scores, return_counts=True)
    order = np.argsort(values)[::-1]
    cumulative = 0
    chosen: float | None = None
    for index in order:
        next_total = cumulative + int(counts[index])
        if next_total > allowed:
            break
        cumulative = next_total
        chosen = float(values[index])
    if chosen is None:
        return float(np.nextafter(np.max(scores), np.inf)), 0
    return float(chosen), cumulative


def save_scores(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False, compression="zstd")


def run_one(dataset: dict[str, Any], config: dict[str, Any], seed: int, capacity: dict[str, int], force: bool) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    capacity_name = f"trees-{capacity['n_estimators']}-depth-{capacity['max_depth']}"
    run_dir = ROOT / "reproduction" / "openml" / "runs" / "membership" / f"openml-{dataset_id}" / f"seed-{seed}" / capacity_name
    manifest_path = run_dir / "run-manifest.json"
    config_hash = sha256_bytes(canonical_json(config))
    if manifest_path.is_file() and not force:
        previous = json.loads(manifest_path.read_text())
        if (
            previous.get("status") == "complete"
            and previous.get("config_sha256") == config_hash
            and previous.get("implementation_version") == IMPLEMENTATION_VERSION
        ):
            return previous
    started = time.monotonic()
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]:
        raise ValueError("dataset snapshot hash mismatch")
    frame = pd.read_parquet(snapshot)
    target_name = dataset["target"]
    features = frame.drop(columns=[target_name])
    label_encoder = LabelEncoder()
    target = label_encoder.fit_transform(frame[target_name].astype("string").fillna("<NA>"))
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(target, max(int(config["row_cap"]) * 2, 500), int(config["master_seed"]))
    features = features.iloc[selected].reset_index(drop=True)
    target = target[selected]
    identities = identities[selected]
    splits = make_splits(target, seed, config["split_fractions"])

    target_indices = equalized_target(
        splits["target_train"], target, len(splits["reference_train"]), seed + 100,
    )
    reference_indices = splits["reference_train"]
    member_calibration, member_audit = member_halves(target_indices, target, seed + 200)
    nonmember_calibration = splits["attack_calibration"]
    nonmember_audit = splits["attack_audit_nonmember"]

    target_preprocessor, numeric, categorical = build_preprocessor(features)
    reference_preprocessor, reference_numeric, reference_categorical = build_preprocessor(features)
    if numeric != reference_numeric or categorical != reference_categorical:
        raise RuntimeError("target and reference preprocessing schemas differ")
    X_target = target_preprocessor.fit_transform(features.iloc[target_indices])
    X_reference = reference_preprocessor.fit_transform(features.iloc[reference_indices])
    parameters = model_parameters(config, len(label_encoder.classes_), seed)
    parameters["n_estimators"] = int(capacity["n_estimators"])
    parameters["max_depth"] = int(capacity["max_depth"])
    from run_openml_structural import _xgb_classifier

    learner = _xgb_classifier()
    target_model = learner(**parameters).fit(X_target, target[target_indices])
    reference_model = learner(**{**parameters, "random_state": seed + 10_000}).fit(
        X_reference, target[reference_indices]
    )
    target_histogram, target_structural = signature_histogram(target_model.apply(X_target))
    reference_histogram, reference_structural = signature_histogram(
        reference_model.apply(X_reference)
    )

    groups = {
        "member_calibration": member_calibration,
        "member_audit": member_audit,
        "nonmember_calibration": nonmember_calibration,
        "nonmember_audit": nonmember_audit,
    }
    scored: dict[str, np.ndarray] = {}
    raw_rows: list[dict[str, Any]] = []
    for group, indices in groups.items():
        X_target_view = target_preprocessor.transform(features.iloc[indices])
        X_reference_view = reference_preprocessor.transform(features.iloc[indices])
        y = target[indices]
        target_loss = per_record_loss(target_model, X_target_view, y)
        reference_loss = per_record_loss(reference_model, X_reference_view, y)
        score = reference_loss - target_loss
        scored[group] = score
        raw_rows.extend({
            "row_id": identities[index],
            "group": group,
            "is_member": group.startswith("member_"),
            "true_class": int(target[index]),
            "target_loss": float(t_loss),
            "reference_loss": float(r_loss),
            "membership_score": float(item),
        } for index, t_loss, r_loss, item in zip(indices, target_loss, reference_loss, score, strict=True))

    target_fpr = float(config["target_fpr"])
    confidence = float(config["confidence"])
    threshold, calibration_fp = threshold_at_fpr(scored["nonmember_calibration"], target_fpr)
    tp = int(np.sum(scored["member_audit"] >= threshold))
    fn = int(len(scored["member_audit"]) - tp)
    fp = int(np.sum(scored["nonmember_audit"] >= threshold))
    tn = int(len(scored["nonmember_audit"]) - fp)
    calibration_tpr = int(np.sum(scored["member_calibration"] >= threshold))
    tpr_lower, tpr_upper = one_sided_clopper_pearson(tp, tp + fn, confidence)
    fpr_lower, fpr_upper = one_sided_clopper_pearson(fp, fp + tn, confidence)
    operating_point_attained = fpr_upper <= target_fpr

    run_dir.mkdir(parents=True, exist_ok=True)
    scores_path = run_dir / "raw-scores.parquet"
    save_scores(scores_path, raw_rows)
    target_model_path = run_dir / "target-model.ubj"
    reference_model_path = run_dir / "reference-model.ubj"
    target_model.save_model(target_model_path)
    reference_model.save_model(reference_model_path)
    preprocessor_path = run_dir / "preprocessor.joblib"
    joblib.dump(
        {
            "target_preprocessor": target_preprocessor,
            "reference_preprocessor": reference_preprocessor,
            "label_encoder": label_encoder,
        },
        preprocessor_path,
        compress=3,
    )
    target_histogram_path = run_dir / "target-leaf-signature-histogram.json.gz"
    reference_histogram_path = run_dir / "reference-leaf-signature-histogram.json.gz"
    write_json_gz(target_histogram_path, target_histogram)
    write_json_gz(reference_histogram_path, reference_histogram)
    manifest = {
        "status": "complete",
        "implementation_version": IMPLEMENTATION_VERSION,
        "experiment": "calibrated_membership_reference_loss",
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "seed": seed,
        "capacity": capacity,
        "protected_unit": "record",
        "target_and_reference_training_size": len(target_indices),
        "group_counts": {name: len(indices) for name, indices in groups.items()},
        "numeric_features": numeric,
        "categorical_features": categorical,
        "model_parameters": parameters,
        "preprocessing_fit": "independently fitted on each model's own training split",
        "target_structural": target_structural,
        "reference_structural": reference_structural,
        "attack": {
            "score": "reference cross-entropy loss minus target cross-entropy loss",
            "member_rule": "membership_score >= threshold",
            "target_fpr": target_fpr,
            "threshold": threshold,
            "calibration_false_positives": calibration_fp,
            "calibration_nonmembers": len(nonmember_calibration),
            "calibration_true_positives": calibration_tpr,
            "calibration_members": len(member_calibration),
            "true_positives": tp,
            "false_negatives": fn,
            "false_positives": fp,
            "true_negatives": tn,
            "tpr": tp / (tp + fn),
            "fpr": fp / (fp + tn),
            "tpr_clopper_pearson_one_sided": [tpr_lower, tpr_upper],
            "fpr_clopper_pearson_one_sided": [fpr_lower, fpr_upper],
            "confidence": confidence,
            "operating_point_attained": operating_point_attained,
            "certified_attack_floor": tpr_lower if operating_point_attained else None,
            "evidence_class": "floor" if operating_point_attained else "screen",
        },
        "artifacts": {
            "raw_scores": {"path": str(scores_path.relative_to(ROOT)), "sha256": sha256_file(scores_path)},
            "target_model": {"path": str(target_model_path.relative_to(ROOT)), "sha256": sha256_file(target_model_path)},
            "reference_model": {"path": str(reference_model_path.relative_to(ROOT)), "sha256": sha256_file(reference_model_path)},
            "preprocessor": {"path": str(preprocessor_path.relative_to(ROOT)), "sha256": sha256_file(preprocessor_path)},
            "target_histogram": {"path": str(target_histogram_path.relative_to(ROOT)), "sha256": sha256_file(target_histogram_path)},
            "reference_histogram": {"path": str(reference_histogram_path.relative_to(ROOT)), "sha256": sha256_file(reference_histogram_path)},
        },
        "config_sha256": config_hash,
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    subset = json.loads(args.subset_manifest.read_text())
    datasets = subset["expensive_subset"]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    if args.limit is not None:
        datasets = datasets[:args.limit]
    seed = int(args.seed or config["replicate_seeds"][0])
    capacities = config["attack_capacities"]
    records, failures = [], []
    total = len(datasets) * len(capacities)
    position = 0
    for dataset in datasets:
        for capacity in capacities:
            position += 1
            print(f"[{position}/{total}] {dataset['name']} OpenML {dataset['dataset_id']} {capacity}", flush=True)
            try:
                records.append(run_one(dataset, config, seed, capacity, args.force))
            except Exception as exc:
                failure = {
                    "dataset_id": dataset["dataset_id"],
                    "dataset_name": dataset["name"],
                    "capacity": capacity,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(failure)
                print(f"  failed: {failure}", flush=True)
    output = ROOT / "output" / "reproduction"
    summary = {
        "experiment": "openml_cc18_membership",
        "subset_manifest_sha256": sha256_file(args.subset_manifest),
        "config_sha256": sha256_file(args.config),
        "expected_runs": total,
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
    }
    write_json(output / "openml-membership-summary.json", summary)
    flat = [{
        "dataset_id": item["dataset_id"],
        "dataset_name": item["dataset_name"],
        "seed": item["seed"],
        **item["capacity"],
        **{f"target_structural_{key}": value for key, value in item["target_structural"].items()},
        **item["attack"],
        "elapsed_seconds": item["elapsed_seconds"],
    } for item in records]
    pd.DataFrame(flat).to_csv(output / "openml-membership-summary.csv", index=False)
    print(json.dumps({"expected_runs": total, "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
