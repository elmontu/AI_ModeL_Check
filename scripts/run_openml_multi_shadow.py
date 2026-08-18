#!/usr/bin/env python3
"""Run a multi-shadow likelihood-ratio membership attack on sealed targets."""

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
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_membership import one_sided_clopper_pearson, per_record_loss, threshold_at_fpr  # noqa: E402
from run_openml_structural import (  # noqa: E402
    build_preprocessor,
    canonical_json,
    capped_indices,
    make_splits,
    model_parameters,
    row_ids,
    sha256_bytes,
    sha256_file,
    write_json,
)


def logit_confidence_from_loss(loss: np.ndarray) -> np.ndarray:
    probability = np.clip(np.exp(-np.asarray(loss, dtype=float)), 1e-12, 1.0 - 1e-12)
    return np.log(probability) - np.log1p(-probability)


def gaussian_logpdf(value: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return -np.log(std) - 0.5 * ((value - mean) / std) ** 2 - 0.5 * math.log(2.0 * math.pi)


def regular_shadow_assignment(rows: int, models: int, memberships: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    assignment = np.zeros((models, rows), dtype=bool)
    for row in range(rows):
        assignment[rng.choice(models, size=memberships, replace=False), row] = True
    return assignment


def run_one(dataset: dict[str, Any], base: dict[str, Any], config: dict[str, Any], force: bool) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    seed = int(config["seed"])
    capacity = config["target_capacity"]
    run_dir = ROOT / "reproduction/openml/runs/multi-shadow" / f"openml-{dataset_id}" / f"seed-{seed}"
    manifest_path = run_dir / "run-manifest.json"
    config_hash = sha256_bytes(canonical_json({"base": base, "shadow": config}))
    if manifest_path.is_file() and not force:
        old = json.loads(manifest_path.read_text())
        if old.get("status") == "complete" and old.get("config_sha256") == config_hash:
            return old
    started = time.monotonic()
    target_run_dir = ROOT / "reproduction/openml/runs/membership" / f"openml-{dataset_id}" / f"seed-{seed}" / f"trees-{capacity['n_estimators']}-depth-{capacity['max_depth']}"
    target_manifest_path = target_run_dir / "run-manifest.json"
    target_manifest = json.loads(target_manifest_path.read_text())
    if target_manifest["dataset_snapshot_sha256"] != dataset["snapshot_sha256"]:
        raise ValueError("target model and dataset snapshot differ")
    target_raw_path = ROOT / target_manifest["artifacts"]["raw_scores"]["path"]
    if sha256_file(target_raw_path) != target_manifest["artifacts"]["raw_scores"]["sha256"]:
        raise ValueError("target raw scores hash mismatch")

    snapshot = ROOT / dataset["snapshot_path"]
    frame = pd.read_parquet(snapshot)
    features = frame.drop(columns=[dataset["target"]])
    encoder = LabelEncoder().fit(frame[dataset["target"]].astype("string").fillna("<NA>"))
    target_all = encoder.transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    identities_all = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(target_all, max(int(base["row_cap"]) * 2, 500), int(base["master_seed"]))
    features = features.iloc[selected].reset_index(drop=True)
    target = target_all[selected]
    identities = identities_all[selected]
    row_lookup = {value: index for index, value in enumerate(identities)}
    raw = pd.read_parquet(target_raw_path)
    candidate_indices = np.asarray([row_lookup[value] for value in raw.row_id], dtype=int)
    target_statistic = logit_confidence_from_loss(raw.target_loss.to_numpy())

    shadow_count = int(config["shadow_models"])
    memberships = int(config["shadow_memberships_per_record"])
    assignment = regular_shadow_assignment(len(features), shadow_count, memberships, seed + 31_000)
    shadow_statistics = np.empty((len(raw), shadow_count), dtype=np.float32)
    model_artifacts = []
    shadow_training_sizes = []
    run_dir.mkdir(parents=True, exist_ok=True)
    parameters = model_parameters(base, len(encoder.classes_), seed)
    parameters["n_estimators"] = int(capacity["n_estimators"])
    parameters["max_depth"] = int(capacity["max_depth"])
    for shadow in range(shadow_count):
        training_indices = np.flatnonzero(assignment[shadow])
        shadow_training_sizes.append(int(len(training_indices)))
        preprocessor, _, _ = build_preprocessor(features)
        X_train = preprocessor.fit_transform(features.iloc[training_indices])
        model = XGBClassifier(**{**parameters, "random_state": seed + 1000 + shadow}).fit(X_train, target[training_indices])
        X_candidates = preprocessor.transform(features.iloc[candidate_indices])
        losses = per_record_loss(model, X_candidates, target[candidate_indices])
        shadow_statistics[:, shadow] = logit_confidence_from_loss(losses).astype(np.float32)
        model_path = run_dir / f"shadow-{shadow:02d}.ubj"
        preprocessor_path = run_dir / f"shadow-{shadow:02d}-preprocessor.joblib"
        model.save_model(model_path)
        joblib.dump(preprocessor, preprocessor_path, compress=3)
        model_artifacts.extend([
            {"kind": "model", "shadow": shadow, "path": str(model_path.relative_to(ROOT)), "sha256": sha256_file(model_path)},
            {"kind": "preprocessor", "shadow": shadow, "path": str(preprocessor_path.relative_to(ROOT)), "sha256": sha256_file(preprocessor_path)},
        ])

    candidate_assignment = assignment[:, candidate_indices].T
    in_mean = np.empty(len(raw)); out_mean = np.empty(len(raw)); in_var = np.empty(len(raw)); out_var = np.empty(len(raw))
    for index in range(len(raw)):
        in_values = shadow_statistics[index, candidate_assignment[index]]
        out_values = shadow_statistics[index, ~candidate_assignment[index]]
        in_mean[index], out_mean[index] = in_values.mean(), out_values.mean()
        in_var[index], out_var[index] = in_values.var(ddof=1), out_values.var(ddof=1)
    global_in_var = float(np.median(in_var))
    global_out_var = float(np.median(out_var))
    shrinkage = float(config["variance_shrinkage_to_global"])
    floor = float(config["minimum_standard_deviation"])
    in_std = np.sqrt(np.maximum((1.0 - shrinkage) * in_var + shrinkage * global_in_var, floor * floor))
    out_std = np.sqrt(np.maximum((1.0 - shrinkage) * out_var + shrinkage * global_out_var, floor * floor))
    score = gaussian_logpdf(target_statistic, in_mean, in_std) - gaussian_logpdf(target_statistic, out_mean, out_std)
    raw = raw[["row_id", "group", "is_member", "true_class", "target_loss"]].copy()
    raw["target_logit_confidence"] = target_statistic
    raw["shadow_in_mean"] = in_mean
    raw["shadow_in_std"] = in_std
    raw["shadow_out_mean"] = out_mean
    raw["shadow_out_std"] = out_std
    raw["multi_shadow_lr_score"] = score
    raw["shadow_in_count"] = candidate_assignment.sum(axis=1)
    raw["shadow_out_count"] = (~candidate_assignment).sum(axis=1)
    raw["shadow_statistics"] = [list(map(float, item)) for item in shadow_statistics]
    target_fpr = float(base["target_fpr"])
    calibration_nonmember = raw.group.eq("nonmember_calibration")
    audit_member = raw.group.eq("member_audit")
    audit_nonmember = raw.group.eq("nonmember_audit")
    threshold, calibration_fp = threshold_at_fpr(score[calibration_nonmember], target_fpr)
    tp = int(np.sum(score[audit_member] >= threshold)); fp = int(np.sum(score[audit_nonmember] >= threshold))
    fn = int(audit_member.sum()) - tp; tn = int(audit_nonmember.sum()) - fp
    confidence = float(base["confidence"])
    tpr_ci = one_sided_clopper_pearson(tp, tp + fn, confidence)
    fpr_ci = one_sided_clopper_pearson(fp, fp + tn, confidence)
    attained = fpr_ci[1] <= target_fpr

    raw_path = run_dir / "raw-multi-shadow-scores.parquet"
    raw.to_parquet(raw_path, index=False, compression="zstd")
    assignment_path = run_dir / "shadow-assignment.npz"
    np.savez_compressed(assignment_path, assignment=assignment, selected_row_ids=identities)
    manifest = {
        "status": "complete",
        "implementation_version": int(config["implementation_version"]),
        "experiment": config["experiment"],
        "attack_status": config["status"],
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "seed": seed,
        "target_capacity": capacity,
        "target_manifest": {"path": str(target_manifest_path.relative_to(ROOT)), "sha256": sha256_file(target_manifest_path)},
        "target_raw_scores": {"path": str(target_raw_path.relative_to(ROOT)), "sha256": sha256_file(target_raw_path)},
        "shadow_models": shadow_count,
        "shadow_memberships_per_record": memberships,
        "shadow_training_sizes": shadow_training_sizes,
        "group_counts": raw.groupby("group").size().to_dict(),
        "score_definition": config["score"],
        "variance_shrinkage_to_global": shrinkage,
        "minimum_standard_deviation": floor,
        "global_in_variance": global_in_var,
        "global_out_variance": global_out_var,
        "attack": {
            "target_fpr": target_fpr,
            "threshold": threshold,
            "calibration_false_positives": calibration_fp,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
            "tpr": tp / (tp + fn),
            "fpr": fp / (fp + tn),
            "tpr_clopper_pearson_one_sided": list(tpr_ci),
            "fpr_clopper_pearson_one_sided": list(fpr_ci),
            "confidence": confidence,
            "operating_point_attained": attained,
            "certified_attack_floor": tpr_ci[0] if attained else None,
        },
        "artifacts": {
            "raw_scores": {"path": str(raw_path.relative_to(ROOT)), "sha256": sha256_file(raw_path)},
            "shadow_assignment": {"path": str(assignment_path.relative_to(ROOT)), "sha256": sha256_file(assignment_path)},
            "shadow_model_artifacts": model_artifacts,
        },
        "config_sha256": config_hash,
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--shadow-config", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base, config, subset = json.loads(args.config.read_text()), json.loads(args.shadow_config.read_text()), json.loads(args.subset_manifest.read_text())
    datasets = subset[config["subset_key"]]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    records, failures = [], []
    for position, dataset in enumerate(datasets, 1):
        print(f"[{position}/{len(datasets)}] {dataset['name']}", flush=True)
        try:
            records.append(run_one(dataset, base, config, args.force))
        except Exception as exc:
            failures.append({"dataset_id": dataset["dataset_id"], "error_type": type(exc).__name__, "error": str(exc)})
            print(f"  failed: {failures[-1]}", flush=True)
    output = ROOT / "output/reproduction"
    summary = {"experiment": config["experiment"], "expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures), "records": records, "failures": failures, "config_sha256": sha256_file(args.shadow_config)}
    write_json(output / "openml-multi-shadow-summary.json", summary)
    pd.json_normalize(records, sep=".").to_csv(output / "openml-multi-shadow-summary.csv", index=False)
    print(json.dumps({"expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
