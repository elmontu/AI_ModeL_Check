#!/usr/bin/env python3
"""Train the broad OpenML structural tier with sealed splits and histograms."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OrdinalEncoder
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]


def _xgb_classifier():
    """Load the experiment-only learner without burdening core verification.

    The pure split, histogram, and statistical helpers in this module are used
    by the standard-library test suite.  XGBoost is needed only when a retained
    OpenML model is trained or loaded, so importing this module must not make
    the optional experiment environment a requirement for the assurance core.
    """
    try:
        from xgboost import XGBClassifier
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "OpenML model execution requires the 'experiments' optional dependencies"
        ) from error
    return XGBClassifier


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def write_json_gz(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as stream:
            stream.write(payload)


def row_ids(dataset_id: int, snapshot_sha256: str, row_count: int) -> np.ndarray:
    # The snapshot digest binds every value and ordering. Combining it with the
    # original row position yields stable pseudonymous IDs without materialising
    # an enormous string copy for wide datasets.
    return np.asarray([
        hashlib.sha256(f"openml:{dataset_id}:{snapshot_sha256}:{index}".encode("utf-8")).hexdigest()
        for index in range(row_count)
    ])


def capped_indices(y: np.ndarray, row_cap: int, seed: int) -> np.ndarray:
    indices = np.arange(len(y))
    if len(indices) <= row_cap:
        return indices
    selected, _ = train_test_split(
        indices,
        train_size=row_cap,
        random_state=seed,
        stratify=y,
    )
    return np.sort(selected)


def make_splits(y: np.ndarray, seed: int, fractions: dict[str, float]) -> dict[str, np.ndarray]:
    names = tuple(fractions)
    if abs(sum(fractions.values()) - 1.0) > 1e-12:
        raise ValueError("split fractions must sum to one")
    remaining = np.arange(len(y))
    splits: dict[str, np.ndarray] = {}
    remaining_mass = 1.0
    for position, name in enumerate(names[:-1]):
        relative = fractions[name] / remaining_mass
        chosen, remaining = train_test_split(
            remaining,
            train_size=relative,
            random_state=seed + position,
            stratify=y[remaining],
        )
        splits[name] = np.sort(chosen)
        remaining_mass -= fractions[name]
    splits[names[-1]] = np.sort(remaining)
    concatenated = np.concatenate(list(splits.values()))
    if len(np.unique(concatenated)) != len(y) or set(concatenated) != set(range(len(y))):
        raise RuntimeError("splits are not a disjoint partition")
    return splits


def build_preprocessor(features: pd.DataFrame) -> tuple[ColumnTransformer, list[str], list[str]]:
    categorical = [
        str(column)
        for column in features.columns
        if not pd.api.types.is_numeric_dtype(features[column].dtype)
        or pd.api.types.is_bool_dtype(features[column].dtype)
    ]
    numeric = [str(column) for column in features.columns if str(column) not in categorical]
    transformers = []
    if numeric:
        transformers.append(("numeric", SimpleImputer(strategy="median"), numeric))
    if categorical:
        transformers.append((
            "categorical",
            Pipeline(steps=[
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
            ]),
            categorical,
        ))
    return ColumnTransformer(transformers=transformers, remainder="drop"), numeric, categorical


def model_parameters(config: dict[str, Any], class_count: int, seed: int) -> dict[str, Any]:
    structural = config["broad_structural_model"]
    parameters: dict[str, Any] = {
        "n_estimators": int(structural["n_estimators"]),
        "max_depth": int(structural["max_depth"]),
        "min_child_weight": float(structural["min_child_weight"]),
        "subsample": float(structural["subsample"]),
        "colsample_bytree": float(structural["colsample_bytree"]),
        "learning_rate": 0.1,
        "tree_method": "hist",
        "random_state": seed,
        "n_jobs": 1,
        "verbosity": 0,
    }
    if class_count == 2:
        parameters.update(objective="binary:logistic", eval_metric="logloss")
    else:
        parameters.update(objective="multi:softprob", eval_metric="mlogloss", num_class=class_count)
    return parameters


def signature_histogram(leaves: np.ndarray) -> tuple[list[dict[str, Any]], dict[str, float | int]]:
    if leaves.ndim == 1:
        leaves = leaves.reshape(-1, 1)
    signatures = Counter(tuple(int(item) for item in row) for row in leaves)
    counts = np.asarray(list(signatures.values()), dtype=np.int64)
    n = int(counts.sum())
    occupied = int(len(counts))
    entropy = float(np.sum((counts / n) * np.log2(counts)))
    metrics: dict[str, float | int] = {
        "records": n,
        "occupied_cells": occupied,
        "minimum_cell_size": int(counts.min()),
        "maximum_cell_size": int(counts.max()),
        "harmonic_mean_cell_size": n / occupied,
        "geometric_mean_cell_size": 2.0 ** entropy,
        "arithmetic_mean_cell_size": float(np.sum(counts * counts) / n),
        "residual_entropy_bits": entropy,
        "disclosed_bits": math.log2(n) - entropy,
        "bayes_linkage_success": occupied / n,
        "worst_observation_success": 1.0 / int(counts.min()),
        "singleton_records": int(counts[counts == 1].sum()),
        "singleton_fraction": float(counts[counts == 1].sum() / n),
    }
    histogram = [
        {"leaf_signature": list(signature), "count": count}
        for signature, count in sorted(signatures.items())
    ]
    return histogram, metrics


def utility_metrics(model: Any, X: np.ndarray, y: np.ndarray) -> dict[str, float | None]:
    prediction = model.predict(X)
    probability = model.predict_proba(X)
    metrics: dict[str, float | None] = {
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "log_loss": float(log_loss(y, probability, labels=np.arange(probability.shape[1]))),
        "roc_auc": None,
    }
    try:
        if probability.shape[1] == 2:
            metrics["roc_auc"] = float(roc_auc_score(y, probability[:, 1]))
        else:
            metrics["roc_auc"] = float(roc_auc_score(y, probability, multi_class="ovr", average="weighted"))
    except ValueError:
        metrics["roc_auc"] = None
    return metrics


def run_one(dataset: dict[str, Any], config: dict[str, Any], seed: int, force: bool) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    run_dir = ROOT / "reproduction" / "openml" / "runs" / "structural" / f"openml-{dataset_id}" / f"seed-{seed}"
    manifest_path = run_dir / "run-manifest.json"
    if manifest_path.is_file() and not force:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("status") == "complete" and previous.get("config_sha256") == sha256_bytes(canonical_json(config)):
            return previous

    started = time.monotonic()
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]:
        raise ValueError(f"snapshot hash mismatch for OpenML dataset {dataset_id}")
    frame = pd.read_parquet(snapshot)
    target_name = dataset["target"]
    features = frame.drop(columns=[target_name])
    target_raw = frame[target_name].astype("string").fillna("<NA>")
    encoder = LabelEncoder()
    target = encoder.fit_transform(target_raw)
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))

    cap_seed = int(config["master_seed"])
    selected = capped_indices(target, max(int(config["row_cap"]) * 2, 500), cap_seed)
    features = features.iloc[selected].reset_index(drop=True)
    target = target[selected]
    identities = identities[selected]
    splits = make_splits(target, seed, config["split_fractions"])

    preprocessor, numeric, categorical = build_preprocessor(features)
    train_indices = splits["target_train"]
    X_train = preprocessor.fit_transform(features.iloc[train_indices])
    y_train = target[train_indices]
    utility_indices = splits["utility_test"]
    X_utility = preprocessor.transform(features.iloc[utility_indices])
    y_utility = target[utility_indices]

    parameters = model_parameters(config, len(encoder.classes_), seed)
    model = _xgb_classifier()(**parameters)
    model.fit(X_train, y_train)
    histogram, structural_metrics = signature_histogram(model.apply(X_train))
    utility = utility_metrics(model, X_utility, y_utility)

    run_dir.mkdir(parents=True, exist_ok=True)
    model_path = run_dir / "model.ubj"
    model.save_model(model_path)
    preprocessor_path = run_dir / "preprocessor.joblib"
    joblib.dump({"preprocessor": preprocessor, "label_encoder": encoder}, preprocessor_path, compress=3)
    split_path = run_dir / "split-manifest.json.gz"
    write_json_gz(split_path, {
        "dataset_id": dataset_id,
        "seed": seed,
        "selected_row_ids": identities.tolist(),
        "splits": {name: identities[indices].tolist() for name, indices in splits.items()},
    })
    histogram_path = run_dir / "leaf-signature-histogram.json.gz"
    write_json_gz(histogram_path, histogram)
    manifest = {
        "status": "complete",
        "experiment": "broad_structural",
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "seed": seed,
        "protected_unit": "record",
        "selected_rows": int(len(selected)),
        "split_counts": {name: int(len(indices)) for name, indices in splits.items()},
        "class_labels": encoder.classes_.tolist(),
        "numeric_features": numeric,
        "categorical_features": categorical,
        "transformed_feature_count": int(X_train.shape[1]),
        "model_parameters": parameters,
        "structural": structural_metrics,
        "utility": utility,
        "artifacts": {
            "model": {"path": str(model_path.relative_to(ROOT)), "sha256": sha256_file(model_path)},
            "preprocessor": {"path": str(preprocessor_path.relative_to(ROOT)), "sha256": sha256_file(preprocessor_path)},
            "splits": {"path": str(split_path.relative_to(ROOT)), "sha256": sha256_file(split_path)},
            "histogram": {"path": str(histogram_path.relative_to(ROOT)), "sha256": sha256_file(histogram_path)},
        },
        "config_sha256": sha256_bytes(canonical_json(config)),
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    suite = json.loads(args.suite_manifest.read_text(encoding="utf-8"))
    datasets = suite["datasets"]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    if args.limit is not None:
        datasets = datasets[: args.limit]
    seeds = args.seed or [int(seed) for seed in config["replicate_seeds"]]

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total = len(datasets) * len(seeds)
    position = 0
    for dataset in datasets:
        for seed in seeds:
            position += 1
            print(f"[{position}/{total}] {dataset['name']} (OpenML {dataset['dataset_id']}), seed {seed}", flush=True)
            try:
                records.append(run_one(dataset, config, seed, args.force))
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
        "experiment": "openml_cc18_broad_structural",
        "suite_manifest_sha256": sha256_file(args.suite_manifest),
        "config_sha256": sha256_file(args.config),
        "expected_runs": total,
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
    }
    write_json(output / "openml-structural-summary.json", summary)
    flat = []
    for record in records:
        flat.append({
            "dataset_id": record["dataset_id"],
            "dataset_name": record["dataset_name"],
            "seed": record["seed"],
            "selected_rows": record["selected_rows"],
            **{f"structural_{key}": value for key, value in record["structural"].items()},
            **{f"utility_{key}": value for key, value in record["utility"].items()},
            "elapsed_seconds": record["elapsed_seconds"],
        })
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(flat).to_csv(output / "openml-structural-summary.csv", index=False)
    print(json.dumps({"expected_runs": total, "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
