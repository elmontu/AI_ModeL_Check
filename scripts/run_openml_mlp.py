#!/usr/bin/env python3
"""Train non-private MLP target/reference pipelines and audit membership risk."""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_membership import (  # noqa: E402
    equalized_target,
    member_halves,
    one_sided_clopper_pearson,
    threshold_at_fpr,
)
from run_openml_structural import (  # noqa: E402
    build_preprocessor,
    canonical_json,
    capped_indices,
    make_splits,
    row_ids,
    sha256_bytes,
    sha256_file,
    write_json,
)


def per_record_loss(model: MLPClassifier, X: np.ndarray, y: np.ndarray) -> np.ndarray:
    probability = np.asarray(model.predict_proba(X), dtype=float)
    if probability.ndim == 1:
        probability = np.column_stack([1.0 - probability, probability])
    selected = probability[np.arange(len(y)), y]
    return -np.log(np.clip(selected, 1e-300, 1.0))


def utility(model: MLPClassifier, X: np.ndarray, y: np.ndarray) -> dict[str, float | None]:
    prediction = model.predict(X)
    probability = np.asarray(model.predict_proba(X), dtype=float)
    if probability.ndim == 1:
        probability = np.column_stack([1.0 - probability, probability])
    result: dict[str, float | None] = {
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "log_loss": float(log_loss(y, probability, labels=np.arange(probability.shape[1]))),
        "roc_auc": None,
    }
    try:
        if probability.shape[1] == 2:
            result["roc_auc"] = float(roc_auc_score(y, probability[:, 1]))
        else:
            result["roc_auc"] = float(
                roc_auc_score(y, probability, multi_class="ovr", average="weighted")
            )
    except ValueError:
        pass
    return result


def fit_model(X: np.ndarray, y: np.ndarray, model_config: dict[str, Any], seed: int) -> tuple[MLPClassifier, bool]:
    parameters = {
        "hidden_layer_sizes": tuple(int(item) for item in model_config["hidden_layer_sizes"]),
        "activation": model_config["activation"],
        "solver": model_config["solver"],
        "alpha": float(model_config["alpha"]),
        "batch_size": int(model_config["batch_size"]),
        "learning_rate_init": float(model_config["learning_rate_init"]),
        "max_iter": int(model_config["max_iter"]),
        "n_iter_no_change": int(model_config["n_iter_no_change"]),
        "shuffle": bool(model_config["shuffle"]),
        "early_stopping": bool(model_config["early_stopping"]),
        "tol": float(model_config["tol"]),
        "validation_fraction": float(model_config["validation_fraction"]),
        "random_state": seed,
    }
    model = MLPClassifier(**parameters)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(X, y)
    converged = not any(issubclass(item.category, ConvergenceWarning) for item in captured)
    return model, converged


def transformed(
    preprocessor: Any,
    scaler: StandardScaler,
    features: pd.DataFrame,
    indices: np.ndarray,
) -> np.ndarray:
    return scaler.transform(np.asarray(preprocessor.transform(features.iloc[indices]), dtype=np.float64))


def run_one(
    dataset: dict[str, Any],
    base_config: dict[str, Any],
    mlp_config: dict[str, Any],
    seed: int,
    force: bool,
) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    run_dir = ROOT / "reproduction" / "openml" / "runs" / "mlp" / f"openml-{dataset_id}" / f"seed-{seed}"
    manifest_path = run_dir / "run-manifest.json"
    combined_config = {"base": base_config, "mlp": mlp_config}
    config_hash = sha256_bytes(canonical_json(combined_config))
    implementation_version = int(mlp_config["implementation_version"])
    if manifest_path.is_file() and not force:
        previous = json.loads(manifest_path.read_text())
        if (
            previous.get("status") == "complete"
            and previous.get("config_sha256") == config_hash
            and previous.get("implementation_version") == implementation_version
        ):
            return previous

    started = time.monotonic()
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]:
        raise ValueError("dataset snapshot hash mismatch")
    frame = pd.read_parquet(snapshot)
    features = frame.drop(columns=[dataset["target"]])
    label_encoder = LabelEncoder()
    target = label_encoder.fit_transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(
        target,
        max(int(base_config["row_cap"]) * 2, 500),
        int(base_config["master_seed"]),
    )
    features = features.iloc[selected].reset_index(drop=True)
    target = target[selected]
    identities = identities[selected]
    splits = make_splits(target, seed, base_config["split_fractions"])
    target_indices = equalized_target(
        splits["target_train"], target, len(splits["reference_train"]), seed + 100
    )
    reference_indices = splits["reference_train"]
    member_calibration, member_audit = member_halves(target_indices, target, seed + 200)
    nonmember_calibration = splits["attack_calibration"]
    nonmember_audit = splits["attack_audit_nonmember"]
    utility_indices = splits["utility_test"]

    target_preprocessor, numeric, categorical = build_preprocessor(features)
    reference_preprocessor, reference_numeric, reference_categorical = build_preprocessor(features)
    if numeric != reference_numeric or categorical != reference_categorical:
        raise RuntimeError("target and reference preprocessing schemas differ")
    X_target_unscaled = np.asarray(
        target_preprocessor.fit_transform(features.iloc[target_indices]), dtype=np.float64
    )
    X_reference_unscaled = np.asarray(
        reference_preprocessor.fit_transform(features.iloc[reference_indices]), dtype=np.float64
    )
    target_scaler = StandardScaler().fit(X_target_unscaled)
    reference_scaler = StandardScaler().fit(X_reference_unscaled)
    X_target = target_scaler.transform(X_target_unscaled)
    X_reference = reference_scaler.transform(X_reference_unscaled)
    target_model, target_converged = fit_model(X_target, target[target_indices], mlp_config["model"], seed)
    reference_model, reference_converged = fit_model(
        X_reference, target[reference_indices], mlp_config["model"], seed + 10_000
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
        target_view = transformed(target_preprocessor, target_scaler, features, indices)
        reference_view = transformed(reference_preprocessor, reference_scaler, features, indices)
        y = target[indices]
        target_loss = per_record_loss(target_model, target_view, y)
        reference_loss = per_record_loss(reference_model, reference_view, y)
        score = reference_loss - target_loss
        scored[group] = score
        raw_rows.extend(
            {
                "row_id": identities[index],
                "group": group,
                "is_member": group.startswith("member_"),
                "true_class": int(target[index]),
                "target_loss": float(t_loss),
                "reference_loss": float(r_loss),
                "membership_score": float(item),
            }
            for index, t_loss, r_loss, item in zip(
                indices, target_loss, reference_loss, score, strict=True
            )
        )

    target_fpr = float(base_config["target_fpr"])
    confidence = float(base_config["confidence"])
    threshold, calibration_fp = threshold_at_fpr(scored["nonmember_calibration"], target_fpr)
    tp = int(np.sum(scored["member_audit"] >= threshold))
    fp = int(np.sum(scored["nonmember_audit"] >= threshold))
    fn = len(member_audit) - tp
    tn = len(nonmember_audit) - fp
    calibration_tp = int(np.sum(scored["member_calibration"] >= threshold))
    tpr_interval = one_sided_clopper_pearson(tp, tp + fn, confidence)
    fpr_interval = one_sided_clopper_pearson(fp, fp + tn, confidence)
    attained = fpr_interval[1] <= target_fpr
    utility_view = transformed(target_preprocessor, target_scaler, features, utility_indices)

    run_dir.mkdir(parents=True, exist_ok=True)
    scores_path = run_dir / "raw-scores.parquet"
    pd.DataFrame(raw_rows).to_parquet(scores_path, index=False, compression="zstd")
    target_model_path = run_dir / "target-model.joblib"
    reference_model_path = run_dir / "reference-model.joblib"
    pipeline_path = run_dir / "preprocessing.joblib"
    joblib.dump(target_model, target_model_path, compress=3)
    joblib.dump(reference_model, reference_model_path, compress=3)
    joblib.dump(
        {
            "target_preprocessor": target_preprocessor,
            "reference_preprocessor": reference_preprocessor,
            "target_scaler": target_scaler,
            "reference_scaler": reference_scaler,
            "label_encoder": label_encoder,
        },
        pipeline_path,
        compress=3,
    )
    manifest = {
        "status": "complete",
        "implementation_version": implementation_version,
        "experiment": "non_private_mlp_membership_reference_loss",
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "seed": seed,
        "protected_unit": "record",
        "selected_rows": len(selected),
        "target_and_reference_training_size": len(target_indices),
        "group_counts": {name: len(indices) for name, indices in groups.items()},
        "numeric_features": numeric,
        "categorical_features": categorical,
        "transformed_feature_count": int(X_target.shape[1]),
        "class_labels": label_encoder.classes_.tolist(),
        "model_family": "sklearn.neural_network.MLPClassifier",
        "model_parameters": mlp_config["model"],
        "target_training": {
            "converged": target_converged,
            "iterations": int(target_model.n_iter_),
            "final_loss": float(target_model.loss_),
        },
        "reference_training": {
            "converged": reference_converged,
            "iterations": int(reference_model.n_iter_),
            "final_loss": float(reference_model.loss_),
        },
        "preprocessing_fit": "independently fitted on each model's own training split",
        "utility": utility(target_model, utility_view, target[utility_indices]),
        "attack": {
            "score": "reference cross-entropy loss minus target cross-entropy loss",
            "member_rule": "membership_score >= threshold",
            "target_fpr": target_fpr,
            "threshold": threshold,
            "calibration_false_positives": calibration_fp,
            "calibration_nonmembers": len(nonmember_calibration),
            "calibration_true_positives": calibration_tp,
            "calibration_members": len(member_calibration),
            "true_positives": tp,
            "false_negatives": fn,
            "false_positives": fp,
            "true_negatives": tn,
            "tpr": tp / (tp + fn),
            "fpr": fp / (fp + tn),
            "tpr_clopper_pearson_one_sided": list(tpr_interval),
            "fpr_clopper_pearson_one_sided": list(fpr_interval),
            "confidence": confidence,
            "operating_point_attained": attained,
            "certified_attack_floor": tpr_interval[0] if attained else None,
            "evidence_class": "floor" if attained else "screen",
        },
        "artifacts": {
            "raw_scores": {"path": str(scores_path.relative_to(ROOT)), "sha256": sha256_file(scores_path)},
            "target_model": {"path": str(target_model_path.relative_to(ROOT)), "sha256": sha256_file(target_model_path)},
            "reference_model": {"path": str(reference_model_path.relative_to(ROOT)), "sha256": sha256_file(reference_model_path)},
            "preprocessing": {"path": str(pipeline_path.relative_to(ROOT)), "sha256": sha256_file(pipeline_path)},
        },
        "config_sha256": config_hash,
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mlp-config", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base_config = json.loads(args.config.read_text())
    mlp_config = json.loads(args.mlp_config.read_text())
    subset = json.loads(args.subset_manifest.read_text())
    datasets = subset[mlp_config["subset_key"]]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    if args.limit is not None:
        datasets = datasets[: args.limit]
    seeds = args.seed or [int(item) for item in mlp_config["replicate_seeds"]]
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total = len(datasets) * len(seeds)
    position = 0
    for dataset in datasets:
        for seed in seeds:
            position += 1
            print(f"[{position}/{total}] {dataset['name']} OpenML {dataset['dataset_id']}, seed {seed}", flush=True)
            try:
                records.append(run_one(dataset, base_config, mlp_config, seed, args.force))
            except Exception as exc:
                failure = {
                    "dataset_id": dataset["dataset_id"],
                    "dataset_name": dataset["name"],
                    "seed": seed,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(failure)
                print(f"  failed: {failure}", flush=True)

    output = ROOT / "output" / "reproduction"
    summary = {
        "experiment": "openml_cc18_non_private_mlp",
        "subset_manifest_sha256": sha256_file(args.subset_manifest),
        "base_config_sha256": sha256_file(args.config),
        "mlp_config_sha256": sha256_file(args.mlp_config),
        "expected_runs": total,
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
    }
    write_json(output / "openml-mlp-summary.json", summary)
    flat = [
        {
            "dataset_id": item["dataset_id"],
            "dataset_name": item["dataset_name"],
            "seed": item["seed"],
            "training_size": item["target_and_reference_training_size"],
            **{f"utility_{key}": value for key, value in item["utility"].items()},
            **item["attack"],
            "target_converged": item["target_training"]["converged"],
            "target_iterations": item["target_training"]["iterations"],
            "elapsed_seconds": item["elapsed_seconds"],
        }
        for item in records
    ]
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(flat).to_csv(output / "openml-mlp-summary.csv", index=False)
    print(json.dumps({"expected_runs": total, "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
