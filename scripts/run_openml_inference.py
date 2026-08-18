#!/usr/bin/env python3
"""Run controlled-baseline attribute inference and numeric feature reconstruction."""

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
from scipy.stats import binomtest
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, mean_absolute_error, mean_squared_error
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier, XGBRegressor


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_membership import member_halves  # noqa: E402
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


def entropy(labels: np.ndarray) -> float:
    counts = np.unique(labels, return_counts=True)[1].astype(float)
    probabilities = counts / counts.sum()
    return float(-np.sum(probabilities * np.log2(probabilities)))


def attribute_encoding(series: pd.Series, max_classes: int) -> tuple[np.ndarray, list[Any], str] | None:
    filled = series.astype("string").fillna("<NA>")
    unique = filled.nunique()
    if 2 <= unique <= max_classes:
        encoder = LabelEncoder().fit(filled)
        labels = encoder.transform(filled)
        representatives = [None if item == "<NA>" else item for item in encoder.classes_.tolist()]
        return labels, representatives, "exact_value"
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 20 or numeric.nunique() < max_classes + 1:
        return None
    try:
        bins = pd.qcut(numeric, q=4, labels=False, duplicates="drop")
    except ValueError:
        return None
    if bins.nunique(dropna=True) < 2:
        return None
    bins = bins.fillna(-1).astype(int)
    encoder = LabelEncoder().fit(bins)
    labels = encoder.transform(bins)
    representatives = []
    for value in encoder.classes_:
        if int(value) == -1:
            representatives.append(None)
        else:
            representatives.append(float(numeric[bins.eq(value)].median()))
    return labels, representatives, "quantile_band"


def choose_attribute(features: pd.DataFrame, train: np.ndarray, audits: list[np.ndarray], max_classes: int) -> tuple[str, np.ndarray, list[Any], str]:
    candidates = []
    for column in features.columns:
        encoded = attribute_encoding(features[column], max_classes)
        if encoded is None:
            continue
        labels, representatives, kind = encoded
        classes = set(np.unique(labels))
        if any(set(np.unique(labels[index])) != classes for index in [train, *audits]):
            continue
        minimum = min(np.bincount(labels[index], minlength=len(classes)).min() for index in [train, *audits])
        if minimum < 2:
            continue
        candidates.append((entropy(labels), str(column), labels, representatives, kind))
    if not candidates:
        raise ValueError("no eligible attribute-inference secret")
    _, column, labels, representatives, kind = max(candidates, key=lambda item: (item[0], item[1]))
    return column, labels, representatives, kind


def choose_numeric_reconstruction(features: pd.DataFrame, reference: np.ndarray, audits: list[np.ndarray]) -> str | None:
    candidates = []
    for column in features.columns:
        numeric = pd.to_numeric(features[column], errors="coerce")
        if numeric.nunique(dropna=True) < 3 or numeric.isna().mean() > 0.25:
            continue
        if any(numeric.iloc[index].notna().sum() < 10 for index in [reference, *audits]):
            continue
        candidates.append((int(numeric.nunique(dropna=True)), float(numeric.std()), str(column)))
    return max(candidates)[2] if candidates else None


def set_candidate(frame: pd.DataFrame, column: str, value: Any) -> pd.DataFrame:
    result = frame.copy()
    if value is None:
        result[column] = np.nan
    else:
        original = frame[column]
        if pd.api.types.is_numeric_dtype(original.dtype):
            result[column] = float(value)
        else:
            result[column] = str(value)
    return result


def response_curve(model: XGBClassifier, preprocessor: Any, features: pd.DataFrame, indices: np.ndarray, column: str, candidates: list[Any]) -> np.ndarray:
    parts = []
    base = features.iloc[indices]
    for value in candidates:
        modified = set_candidate(base, column, value)
        probability = np.asarray(model.predict_proba(preprocessor.transform(modified)), dtype=np.float32)
        if probability.ndim == 1:
            probability = np.column_stack([1.0 - probability, probability])
        parts.append(probability)
    return np.hstack(parts).astype(np.float32)


def attacker_features(features: pd.DataFrame, target: np.ndarray, indices: np.ndarray, secret: str, preprocessor: Any | None = None) -> tuple[np.ndarray, Any]:
    known = features.drop(columns=[secret]).copy()
    known["__task_label__"] = pd.Series(target, index=known.index).astype("string")
    if preprocessor is None:
        preprocessor, _, _ = build_preprocessor(known)
        matrix = preprocessor.fit_transform(known.iloc[indices])
    else:
        matrix = preprocessor.transform(known.iloc[indices])
    return np.asarray(matrix, dtype=np.float32), preprocessor


def classifier_parameters(config: dict[str, Any], classes: int, seed: int) -> dict[str, Any]:
    values = config["attribute_attacker"]
    result: dict[str, Any] = {"n_estimators": int(values["n_estimators"]), "max_depth": int(values["max_depth"]), "min_child_weight": float(values["min_child_weight"]), "learning_rate": 0.1, "tree_method": "hist", "random_state": seed, "n_jobs": 1, "verbosity": 0}
    if classes == 2:
        result.update(objective="binary:logistic", eval_metric="logloss")
    else:
        result.update(objective="multi:softprob", eval_metric="mlogloss", num_class=classes)
    return result


def regressor_parameters(config: dict[str, Any], seed: int) -> dict[str, Any]:
    values = config["reconstruction_attacker"]
    return {"n_estimators": int(values["n_estimators"]), "max_depth": int(values["max_depth"]), "min_child_weight": float(values["min_child_weight"]), "learning_rate": 0.1, "tree_method": "hist", "random_state": seed, "n_jobs": 1, "verbosity": 0, "objective": "reg:squarederror"}


def paired_bootstrap(values: np.ndarray, seed: int, resamples: int = 10000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for start in range(0, resamples, 250):
        count = min(250, resamples - start)
        indices = rng.integers(0, len(values), size=(count, len(values)))
        means[start:start + count] = values[indices].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def attribute_result(y: np.ndarray, baseline: np.ndarray, combined: np.ndarray, seed: int) -> dict[str, Any]:
    baseline_correct = baseline == y
    combined_correct = combined == y
    paired = combined_correct.astype(float) - baseline_correct.astype(float)
    baseline_only = int(np.sum(baseline_correct & ~combined_correct))
    combined_only = int(np.sum(~baseline_correct & combined_correct))
    discordant = baseline_only + combined_only
    pvalue = float(binomtest(combined_only, discordant, 0.5, alternative="greater").pvalue) if discordant else 1.0
    return {
        "records": len(y),
        "prior_accuracy": float(np.bincount(y).max() / len(y)),
        "baseline_accuracy": float(accuracy_score(y, baseline)),
        "combined_accuracy": float(accuracy_score(y, combined)),
        "baseline_balanced_accuracy": float(balanced_accuracy_score(y, baseline)),
        "combined_balanced_accuracy": float(balanced_accuracy_score(y, combined)),
        "incremental_accuracy": float(paired.mean()),
        "incremental_accuracy_bootstrap_95": list(paired_bootstrap(paired, seed)),
        "combined_only_correct": combined_only,
        "baseline_only_correct": baseline_only,
        "mcnemar_exact_one_sided_p": pvalue,
        "baseline_confusion": confusion_matrix(y, baseline, labels=np.arange(max(y.max(), baseline.max(), combined.max()) + 1)).tolist(),
        "combined_confusion": confusion_matrix(y, combined, labels=np.arange(max(y.max(), baseline.max(), combined.max()) + 1)).tolist(),
    }


def reconstruction_result(y: np.ndarray, baseline: np.ndarray, combined: np.ndarray, scale: float, seed: int) -> dict[str, Any]:
    baseline_error = np.abs(y - baseline)
    combined_error = np.abs(y - combined)
    improvement = baseline_error - combined_error
    tolerance = 0.1 * scale
    return {
        "records": len(y),
        "scale_iqr": scale,
        "baseline_mae": float(mean_absolute_error(y, baseline)),
        "combined_mae": float(mean_absolute_error(y, combined)),
        "baseline_rmse": float(math.sqrt(mean_squared_error(y, baseline))),
        "combined_rmse": float(math.sqrt(mean_squared_error(y, combined))),
        "baseline_normalized_mae": float(baseline_error.mean() / scale),
        "combined_normalized_mae": float(combined_error.mean() / scale),
        "mean_absolute_error_reduction": float(improvement.mean()),
        "normalized_mae_reduction": float(improvement.mean() / scale),
        "mae_reduction_bootstrap_95": list(paired_bootstrap(improvement / scale, seed)),
        "baseline_within_0p1_iqr": float(np.mean(baseline_error <= tolerance)),
        "combined_within_0p1_iqr": float(np.mean(combined_error <= tolerance)),
    }


def categorical_reconstruction_result(y: np.ndarray, baseline: np.ndarray, combined: np.ndarray, seed: int) -> dict[str, Any]:
    baseline_correct = baseline.astype(int) == y.astype(int)
    combined_correct = combined.astype(int) == y.astype(int)
    improvement = combined_correct.astype(float) - baseline_correct.astype(float)
    return {
        "metric": "zero_one_accuracy",
        "records": len(y),
        "baseline_accuracy": float(baseline_correct.mean()),
        "combined_accuracy": float(combined_correct.mean()),
        "incremental_accuracy": float(improvement.mean()),
        "incremental_accuracy_bootstrap_95": list(paired_bootstrap(improvement, seed)),
    }


def run_one(dataset: dict[str, Any], base: dict[str, Any], config: dict[str, Any], force: bool) -> dict[str, Any]:
    dataset_id, seed = int(dataset["dataset_id"]), int(config["seed"])
    run_dir = ROOT / "reproduction/openml/runs/inference" / f"openml-{dataset_id}" / f"seed-{seed}"
    manifest_path = run_dir / "run-manifest.json"
    config_hash = sha256_bytes(canonical_json({"base": base, "inference": config}))
    if manifest_path.is_file() and not force:
        old = json.loads(manifest_path.read_text())
        if old.get("status") == "complete" and old.get("config_sha256") == config_hash:
            return old
    started = time.monotonic()
    snapshot = ROOT / dataset["snapshot_path"]
    frame = pd.read_parquet(snapshot)
    features = frame.drop(columns=[dataset["target"]])
    task_encoder = LabelEncoder().fit(frame[dataset["target"]].astype("string").fillna("<NA>"))
    target_all = task_encoder.transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    identities_all = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(target_all, max(int(base["row_cap"]) * 2, 500), int(base["master_seed"]))
    features = features.iloc[selected].reset_index(drop=True); target = target_all[selected]; identities = identities_all[selected]
    splits = make_splits(target, seed, base["split_fractions"])
    member_calibration, member_audit = member_halves(splits["target_train"], target, seed + 200)
    reference = splits["reference_train"]; nonmember_audit = splits["attack_audit_nonmember"]
    strata = {"member_audit": member_audit, "nonmember_audit": nonmember_audit}

    structural_dir = ROOT / "reproduction/openml/runs/structural" / f"openml-{dataset_id}" / f"seed-{seed}"
    structural_manifest_path = structural_dir / "run-manifest.json"
    structural = json.loads(structural_manifest_path.read_text())
    model = XGBClassifier(); model.load_model(ROOT / structural["artifacts"]["model"]["path"])
    target_preprocessor = joblib.load(ROOT / structural["artifacts"]["preprocessor"]["path"])["preprocessor"]

    attribute_column, attribute_labels, attribute_candidates, attribute_kind = choose_attribute(features, reference, list(strata.values()), int(config["attribute_max_classes"]))
    X_attribute_reference, attribute_preprocessor = attacker_features(features, target, reference, attribute_column)
    attribute_curve_reference = response_curve(model, target_preprocessor, features, reference, attribute_column, attribute_candidates)
    attribute_parameters = classifier_parameters(config, len(attribute_candidates), seed + 40_000)
    baseline_attribute = XGBClassifier(**attribute_parameters).fit(X_attribute_reference, attribute_labels[reference])
    combined_attribute = XGBClassifier(**{**attribute_parameters, "random_state": seed + 40_001}).fit(np.hstack([X_attribute_reference, attribute_curve_reference]), attribute_labels[reference])
    attribute_strata, attribute_raw = {}, []
    for offset, (stratum, indices) in enumerate(strata.items()):
        X_known, _ = attacker_features(features, target, indices, attribute_column, attribute_preprocessor)
        curve = response_curve(model, target_preprocessor, features, indices, attribute_column, attribute_candidates)
        baseline_prediction = baseline_attribute.predict(X_known).astype(int)
        combined_prediction = combined_attribute.predict(np.hstack([X_known, curve])).astype(int)
        attribute_strata[stratum] = attribute_result(attribute_labels[indices], baseline_prediction, combined_prediction, seed + 41_000 + offset)
        attribute_raw.extend({"row_id": identities[index], "stratum": stratum, "true_attribute": int(truth), "baseline_prediction": int(b), "combined_prediction": int(c)} for index, truth, b, c in zip(indices, attribute_labels[indices], baseline_prediction, combined_prediction, strict=True))

    reconstruction_column = choose_numeric_reconstruction(features, reference, list(strata.values()))
    categorical_reconstruction = reconstruction_column is None
    if categorical_reconstruction:
        reconstruction_column, encoded_secret, candidate_values, _ = choose_attribute(
            features, reference, list(strata.values()), int(config["attribute_max_classes"])
        )
        secret_numeric = encoded_secret.astype(float)
        reconstruction_kind = "exact_categorical_feature"
        scale = 1.0
        reference_valid = reference
    else:
        secret_numeric = pd.to_numeric(features[reconstruction_column], errors="coerce").to_numpy(dtype=float)
        training_summary = secret_numeric[splits["target_train"]]
        candidate_values = sorted(set(float(value) for value in np.nanquantile(training_summary, [0.0, 0.25, 0.5, 0.75, 1.0]).tolist()))
        q1, q3 = np.nanquantile(training_summary, [0.25, 0.75]); scale = float(max(q3 - q1, np.nanstd(training_summary), 1e-12))
        reference_valid = reference[np.isfinite(secret_numeric[reference])]
        reconstruction_kind = "one_numeric_feature"
    X_reconstruction_reference, reconstruction_preprocessor = attacker_features(features, target, reference_valid, reconstruction_column)
    reconstruction_curve_reference = response_curve(model, target_preprocessor, features, reference_valid, reconstruction_column, candidate_values)
    if categorical_reconstruction:
        reconstruction_parameters = classifier_parameters(config, len(candidate_values), seed + 50_000)
        baseline_reconstruction = XGBClassifier(**reconstruction_parameters).fit(X_reconstruction_reference, secret_numeric[reference_valid].astype(int))
        combined_reconstruction = XGBClassifier(**{**reconstruction_parameters, "random_state": seed + 50_001}).fit(np.hstack([X_reconstruction_reference, reconstruction_curve_reference]), secret_numeric[reference_valid].astype(int))
    else:
        reconstruction_parameters = regressor_parameters(config, seed + 50_000)
        baseline_reconstruction = XGBRegressor(**reconstruction_parameters).fit(X_reconstruction_reference, secret_numeric[reference_valid])
        combined_reconstruction = XGBRegressor(**{**reconstruction_parameters, "random_state": seed + 50_001}).fit(np.hstack([X_reconstruction_reference, reconstruction_curve_reference]), secret_numeric[reference_valid])
    reconstruction_strata, reconstruction_raw = {}, []
    for offset, (stratum, raw_indices) in enumerate(strata.items()):
        indices = raw_indices[np.isfinite(secret_numeric[raw_indices])]
        X_known, _ = attacker_features(features, target, indices, reconstruction_column, reconstruction_preprocessor)
        curve = response_curve(model, target_preprocessor, features, indices, reconstruction_column, candidate_values)
        baseline_prediction = baseline_reconstruction.predict(X_known).astype(float)
        combined_prediction = combined_reconstruction.predict(np.hstack([X_known, curve])).astype(float)
        if categorical_reconstruction:
            reconstruction_strata[stratum] = categorical_reconstruction_result(secret_numeric[indices], baseline_prediction, combined_prediction, seed + 51_000 + offset)
        else:
            reconstruction_strata[stratum] = reconstruction_result(secret_numeric[indices], baseline_prediction, combined_prediction, scale, seed + 51_000 + offset)
        reconstruction_raw.extend({"row_id": identities[index], "stratum": stratum, "true_value": float(truth), "baseline_prediction": float(b), "combined_prediction": float(c), "baseline_absolute_error": float(abs(truth - b)) if not categorical_reconstruction else float(int(round(b)) != int(round(truth))), "combined_absolute_error": float(abs(truth - c)) if not categorical_reconstruction else float(int(round(c)) != int(round(truth)))} for index, truth, b, c in zip(indices, secret_numeric[indices], baseline_prediction, combined_prediction, strict=True))

    run_dir.mkdir(parents=True, exist_ok=True)
    attribute_raw_path = run_dir / "raw-attribute-inference.parquet"; pd.DataFrame(attribute_raw).to_parquet(attribute_raw_path, index=False, compression="zstd")
    reconstruction_raw_path = run_dir / "raw-reconstruction.parquet"; pd.DataFrame(reconstruction_raw).to_parquet(reconstruction_raw_path, index=False, compression="zstd")
    models_path = run_dir / "attack-models.joblib"; joblib.dump({"attribute_preprocessor": attribute_preprocessor, "baseline_attribute": baseline_attribute, "combined_attribute": combined_attribute, "reconstruction_preprocessor": reconstruction_preprocessor, "baseline_reconstruction": baseline_reconstruction, "combined_reconstruction": combined_reconstruction}, models_path, compress=3)
    manifest = {
        "status": "complete", "implementation_version": int(config["implementation_version"]), "experiment": config["experiment"],
        "dataset_id": dataset_id, "dataset_name": dataset["name"], "dataset_snapshot_sha256": dataset["snapshot_sha256"], "seed": seed, "protected_unit": "record",
        "target_structural_manifest": {"path": str(structural_manifest_path.relative_to(ROOT)), "sha256": sha256_file(structural_manifest_path)},
        "split_counts": {"reference_attack_training": len(reference), "member_audit": len(member_audit), "nonmember_audit": len(nonmember_audit)},
        "attribute_inference": {"secret_feature": attribute_column, "secret_kind": attribute_kind, "secret_classes": len(attribute_candidates), "candidate_representatives": attribute_candidates, "baseline_contract": config["baseline"], "strata": attribute_strata},
        "reconstruction": {"secret_feature": reconstruction_column, "secret_kind": reconstruction_kind, "candidate_grid_from_exact_target_training_summaries": candidate_values, "scale_iqr_or_sd": scale, "baseline_contract": config["baseline"], "strata": reconstruction_strata, "claim_boundary": config["claim_boundary"]},
        "artifacts": {
            "raw_attribute": {"path": str(attribute_raw_path.relative_to(ROOT)), "sha256": sha256_file(attribute_raw_path)},
            "raw_reconstruction": {"path": str(reconstruction_raw_path.relative_to(ROOT)), "sha256": sha256_file(reconstruction_raw_path)},
            "attack_models": {"path": str(models_path.relative_to(ROOT)), "sha256": sha256_file(models_path)},
        },
        "config_sha256": config_hash, "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True); parser.add_argument("--inference-config", type=Path, required=True); parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append"); parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base, config, subset = json.loads(args.config.read_text()), json.loads(args.inference_config.read_text()), json.loads(args.subset_manifest.read_text())
    datasets = subset[config["subset_key"]]
    if args.dataset_id:
        allowed = set(args.dataset_id); datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    records, failures = [], []
    for position, dataset in enumerate(datasets, 1):
        print(f"[{position}/{len(datasets)}] {dataset['name']}", flush=True)
        try: records.append(run_one(dataset, base, config, args.force))
        except Exception as exc:
            failures.append({"dataset_id": dataset["dataset_id"], "dataset_name": dataset["name"], "error_type": type(exc).__name__, "error": str(exc)})
            print(f"  failed: {failures[-1]}", flush=True)
    output = ROOT / "output/reproduction"
    shared = {"experiment": config["experiment"], "expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures), "failures": failures, "config_sha256": sha256_file(args.inference_config)}
    attribute_summary = {**shared, "records": [{key: value for key, value in item.items() if key != "reconstruction"} for item in records]}
    reconstruction_summary = {**shared, "records": [{key: value for key, value in item.items() if key != "attribute_inference"} for item in records]}
    write_json(output / "openml-attribute-summary.json", attribute_summary); write_json(output / "openml-reconstruction-summary.json", reconstruction_summary)
    pd.json_normalize(attribute_summary["records"], sep=".").to_csv(output / "openml-attribute-summary.csv", index=False)
    pd.json_normalize(reconstruction_summary["records"], sep=".").to_csv(output / "openml-reconstruction-summary.csv", index=False)
    print(json.dumps({"expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__": raise SystemExit(main())
