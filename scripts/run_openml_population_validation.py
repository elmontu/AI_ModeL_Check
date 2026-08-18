#!/usr/bin/env python3
"""Validate finite-population cell-count inference against complete snapshots."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import hypergeom
from sklearn.preprocessing import LabelEncoder


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_structural import (  # noqa: E402
    _xgb_classifier,
    canonical_json,
    sha256_bytes,
    sha256_file,
    write_json,
    write_json_gz,
)


def hypergeometric_lower(population: int, sample: int, observed: int, alpha: float) -> int:
    """Invert the exact upper tail to lower-bound the finite success count."""
    if observed == 0:
        return 0
    low, high = observed, population - sample + observed
    while low < high:
        middle = (low + high) // 2
        if hypergeom.sf(observed - 1, population, middle, sample) > alpha:
            high = middle
        else:
            low = middle + 1
    return int(low)


def apply_in_chunks(model: Any, preprocessor: Any, features: pd.DataFrame, chunk: int = 2000) -> np.ndarray:
    pieces = []
    for start in range(0, len(features), chunk):
        transformed = preprocessor.transform(features.iloc[start:start + chunk])
        leaves = np.asarray(model.apply(transformed))
        if leaves.ndim == 1: leaves = leaves.reshape(-1, 1)
        pieces.append(leaves.astype(np.int32))
    return np.vstack(pieces)


def label_tv(labels: np.ndarray, indices: np.ndarray) -> float:
    classes = int(labels.max()) + 1
    population = np.bincount(labels, minlength=classes) / len(labels)
    sample = np.bincount(labels[indices], minlength=classes) / len(indices)
    return float(0.5 * np.abs(population - sample).sum())


def cell_tv(inverse: np.ndarray, indices: np.ndarray, cell_count: int) -> float:
    population = np.bincount(inverse, minlength=cell_count) / len(inverse)
    sample = np.bincount(inverse[indices], minlength=cell_count) / len(indices)
    return float(0.5 * np.abs(population - sample).sum())


def run_one(dataset: dict[str, Any], config: dict[str, Any], force: bool) -> dict[str, Any]:
    dataset_id, seed = int(dataset["dataset_id"]), int(config["model_seed"])
    run_dir = ROOT / "reproduction/openml/runs/population-validation" / f"openml-{dataset_id}" / f"seed-{seed}"
    manifest_path = run_dir / "run-manifest.json"
    config_hash = sha256_bytes(canonical_json(config))
    if manifest_path.is_file() and not force:
        old = json.loads(manifest_path.read_text())
        if old.get("status") == "complete" and old.get("config_sha256") == config_hash: return old
    started = time.monotonic()
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]: raise ValueError("snapshot hash mismatch")
    frame = pd.read_parquet(snapshot); features = frame.drop(columns=[dataset["target"]])
    encoder = LabelEncoder().fit(frame[dataset["target"]].astype("string").fillna("<NA>")); labels = encoder.transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    structural_dir = ROOT / "reproduction/openml/runs/structural" / f"openml-{dataset_id}" / f"seed-{seed}"
    structural_manifest_path = structural_dir / "run-manifest.json"; structural = json.loads(structural_manifest_path.read_text())
    model = _xgb_classifier()(); model.load_model(ROOT / structural["artifacts"]["model"]["path"])
    preprocessor = joblib.load(ROOT / structural["artifacts"]["preprocessor"]["path"])["preprocessor"]
    signatures = apply_in_chunks(model, preprocessor, features)
    unique, inverse, counts = np.unique(signatures, axis=0, return_inverse=True, return_counts=True)
    population = len(features); sample_size = min(int(config["sample_size_cap"]), population)
    queries = min(int(config["query_records"]), population)
    rng = np.random.default_rng(seed + dataset_id)
    probability_sample = np.sort(rng.choice(population, sample_size, replace=False)); query_indices = np.sort(rng.choice(population, queries, replace=False))
    # A deliberately invalid control: select high values of a deterministic known covariate.
    first_column = features.columns[0]; numeric_score = pd.to_numeric(features[first_column], errors="coerce")
    if numeric_score.notna().sum() >= sample_size:
        filled = numeric_score.fillna(float(numeric_score.median())).to_numpy()
        biased_sample = np.sort(np.argsort(filled, kind="stable")[-sample_size:])
        stress_basis = f"highest values of {first_column}"
    else:
        text_score = features[first_column].astype("string").fillna("<NA>")
        codes = pd.factorize(text_score, sort=True)[0]
        biased_sample = np.sort(np.argsort(codes, kind="stable")[-sample_size:])
        stress_basis = f"lexicographically highest categories of {first_column}"
    alpha_per_query = (1.0 - float(config["familywise_confidence_per_dataset"])) / queries
    probability_counts = np.bincount(inverse[probability_sample], minlength=len(counts)); biased_counts = np.bincount(inverse[biased_sample], minlength=len(counts))
    raw_rows = []
    for query in query_indices:
        cell = int(inverse[query]); truth = int(counts[cell]); observed = int(probability_counts[cell]); biased_observed = int(biased_counts[cell])
        lower = hypergeometric_lower(population, sample_size, observed, alpha_per_query); biased_lower = hypergeometric_lower(population, sample_size, biased_observed, alpha_per_query)
        raw_rows.append({"query_row": int(query), "cell_id": cell, "true_population_cell_size": truth, "probability_sample_matches": observed, "probability_point_estimate": observed * population / sample_size, "probability_simultaneous_lower": lower, "probability_covers": lower <= truth, "biased_sample_matches": biased_observed, "biased_point_estimate": biased_observed * population / sample_size, "biased_pseudo_lower": biased_lower, "biased_pseudo_covers": biased_lower <= truth})
    raw = pd.DataFrame(raw_rows)
    histogram = [{"cell_id": int(index), "leaf_signature": unique[index].astype(int).tolist(), "population_count": int(count)} for index, count in enumerate(counts)]
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_path = run_dir / "raw-population-queries.parquet"; raw.to_parquet(raw_path, index=False, compression="zstd")
    histogram_path = run_dir / "full-population-leaf-histogram.json.gz"; write_json_gz(histogram_path, histogram)
    samples_path = run_dir / "sampling-design.npz"; np.savez_compressed(samples_path, probability_sample=probability_sample, biased_sample=biased_sample, query_indices=query_indices)
    manifest = {
        "status": "complete", "implementation_version": int(config["implementation_version"]), "experiment": config["experiment"], "dataset_id": dataset_id, "dataset_name": dataset["name"], "dataset_snapshot_sha256": dataset["snapshot_sha256"], "model_seed": seed,
        "declared_target_population": config["declared_target_population"], "claim_boundary": config["claim_boundary"], "protected_unit": config["protected_unit"],
        "population_rows": population, "population_cells": int(len(counts)), "sample_size": sample_size, "query_records": queries, "alpha_per_query": alpha_per_query,
        "probability_design": config["probability_sample"], "interval": config["interval"], "stress_control_basis": stress_basis,
        "diagnostics": {"probability_label_total_variation": label_tv(labels, probability_sample), "biased_label_total_variation": label_tv(labels, biased_sample), "probability_cell_total_variation": cell_tv(inverse, probability_sample, len(counts)), "biased_cell_total_variation": cell_tv(inverse, biased_sample, len(counts)), "probability_simultaneous_coverage": float(raw.probability_covers.mean()), "biased_pseudo_coverage": float(raw.biased_pseudo_covers.mean()), "probability_median_relative_absolute_error": float(np.median(np.abs(raw.probability_point_estimate - raw.true_population_cell_size) / np.maximum(1, raw.true_population_cell_size))), "biased_median_relative_absolute_error": float(np.median(np.abs(raw.biased_point_estimate - raw.true_population_cell_size) / np.maximum(1, raw.true_population_cell_size))), "probability_positive_lower_bounds": int(raw.probability_simultaneous_lower.gt(0).sum()), "biased_positive_pseudo_lower_bounds": int(raw.biased_pseudo_lower.gt(0).sum())},
        "target_structural_manifest": {"path": str(structural_manifest_path.relative_to(ROOT)), "sha256": sha256_file(structural_manifest_path)},
        "artifacts": {"raw_queries": {"path": str(raw_path.relative_to(ROOT)), "sha256": sha256_file(raw_path)}, "full_population_histogram": {"path": str(histogram_path.relative_to(ROOT)), "sha256": sha256_file(histogram_path)}, "sampling_design": {"path": str(samples_path.relative_to(ROOT)), "sha256": sha256_file(samples_path)}},
        "config_sha256": config_hash, "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest); return manifest


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--population-config", type=Path, required=True); parser.add_argument("--suite-manifest", type=Path, required=True); parser.add_argument("--dataset-id", type=int, action="append"); parser.add_argument("--force", action="store_true")
    args = parser.parse_args(); config = json.loads(args.population_config.read_text()); suite = json.loads(args.suite_manifest.read_text()); datasets = suite["datasets"]
    if args.dataset_id:
        allowed = set(args.dataset_id); datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    records, failures = [], []
    for position, dataset in enumerate(datasets, 1):
        print(f"[{position}/{len(datasets)}] {dataset['name']}", flush=True)
        try: records.append(run_one(dataset, config, args.force))
        except Exception as exc:
            failures.append({"dataset_id": dataset["dataset_id"], "dataset_name": dataset["name"], "error_type": type(exc).__name__, "error": str(exc)}); print(f"  failed: {failures[-1]}", flush=True)
    output = ROOT / "output/reproduction"; summary = {"experiment": config["experiment"], "expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures), "records": records, "failures": failures, "config_sha256": sha256_file(args.population_config), "suite_manifest_sha256": sha256_file(args.suite_manifest)}
    write_json(output / "openml-population-validation-summary.json", summary); pd.json_normalize(records, sep=".").to_csv(output / "openml-population-validation-summary.csv", index=False)
    print(json.dumps({"expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures)}, indent=2)); return 0 if not failures else 2


if __name__ == "__main__": raise SystemExit(main())
