#!/usr/bin/env python3
"""Measure joint tree-partition disclosure across three OpenML releases."""

from __future__ import annotations

import argparse
import gzip
import json
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
IMPLEMENTATION_VERSION = 1
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_structural import (  # noqa: E402
    canonical_json,
    capped_indices,
    row_ids,
    sha256_bytes,
    sha256_file,
    signature_histogram,
    write_json,
    write_json_gz,
)


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def load_release(dataset_id: int, seed: int) -> tuple[dict[str, Any], Any, XGBClassifier, dict[str, Any]]:
    run_dir = ROOT / "reproduction" / "openml" / "runs" / "structural" / f"openml-{dataset_id}" / f"seed-{seed}"
    manifest = json.loads((run_dir / "run-manifest.json").read_text())
    for artifact in manifest["artifacts"].values():
        path = ROOT / artifact["path"]
        if sha256_file(path) != artifact["sha256"]:
            raise ValueError(f"artifact hash mismatch: {path}")
    preprocessing = joblib.load(ROOT / manifest["artifacts"]["preprocessor"]["path"])
    model = XGBClassifier()
    model.load_model(ROOT / manifest["artifacts"]["model"]["path"])
    split_manifest = read_json_gz(ROOT / manifest["artifacts"]["splits"]["path"])
    return manifest, preprocessing["preprocessor"], model, split_manifest


def run_one(dataset: dict[str, Any], config: dict[str, Any], seeds: list[int], force: bool) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    run_dir = ROOT / "reproduction" / "openml" / "runs" / "composition" / f"openml-{dataset_id}"
    manifest_path = run_dir / "run-manifest.json"
    config_hash = sha256_bytes(canonical_json({"config": config, "seeds": seeds}))
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
    features = frame.drop(columns=[dataset["target"]])
    label_encoder = LabelEncoder()
    target = label_encoder.fit_transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(target, max(int(config["row_cap"]) * 2, 500), int(config["master_seed"]))
    features = features.iloc[selected].reset_index(drop=True)
    identities = identities[selected]
    id_to_index = {item: index for index, item in enumerate(identities)}

    releases = [load_release(dataset_id, seed) for seed in seeds]
    target_rosters = [set(item[3]["splits"]["target_train"]) for item in releases]
    common_ids = sorted(set.intersection(*target_rosters))
    if not common_ids:
        raise ValueError("release target-training rosters have an empty intersection")
    common_indices = np.asarray([id_to_index[item] for item in common_ids], dtype=int)

    leaf_matrices: list[np.ndarray] = []
    standalone: list[dict[str, Any]] = []
    standalone_histograms: list[list[dict[str, Any]]] = []
    for seed, (_, preprocessor, model, _) in zip(seeds, releases, strict=True):
        transformed = preprocessor.transform(features.iloc[common_indices])
        leaves = np.asarray(model.apply(transformed))
        if leaves.ndim == 1:
            leaves = leaves.reshape(-1, 1)
        leaf_matrices.append(leaves)
        histogram, metrics = signature_histogram(leaves)
        standalone_histograms.append(histogram)
        standalone.append({"seed": seed, **metrics})
    joint_leaves = np.concatenate(leaf_matrices, axis=1)
    joint_histogram, joint = signature_histogram(joint_leaves)
    prior = 1.0 / len(common_ids)
    standalone_incremental = [item["bayes_linkage_success"] - prior for item in standalone]
    joint_incremental = joint["bayes_linkage_success"] - prior

    run_dir.mkdir(parents=True, exist_ok=True)
    joint_path = run_dir / "joint-leaf-signature-histogram.json.gz"
    write_json_gz(joint_path, joint_histogram)
    artifacts: dict[str, dict[str, str]] = {
        "joint_histogram": {
            "path": str(joint_path.relative_to(ROOT)),
            "sha256": sha256_file(joint_path),
        }
    }
    for seed, histogram in zip(seeds, standalone_histograms, strict=True):
        path = run_dir / f"release-{seed}-common-roster-histogram.json.gz"
        write_json_gz(path, histogram)
        artifacts[f"release_{seed}_histogram"] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
        }
    roster_path = run_dir / "common-roster.json.gz"
    write_json_gz(roster_path, common_ids)
    artifacts["common_roster"] = {
        "path": str(roster_path.relative_to(ROOT)),
        "sha256": sha256_file(roster_path),
    }
    manifest = {
        "status": "complete",
        "implementation_version": IMPLEMENTATION_VERSION,
        "experiment": "three_release_joint_tree_partition",
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "protected_unit": "record",
        "release_seeds": seeds,
        "common_roster_records": len(common_ids),
        "no_release_uniform_roster_success": prior,
        "standalone": standalone,
        "joint": joint,
        "standalone_incremental_values": standalone_incremental,
        "joint_incremental_value": joint_incremental,
        "naive_sum_incremental_values": sum(standalone_incremental),
        "composition_amplification_over_best_standalone": (
            joint["bayes_linkage_success"] - max(item["bayes_linkage_success"] for item in standalone)
        ),
        "joint_no_greater_than_naive_sum": joint_incremental <= sum(standalone_incremental) + 1e-12,
        "evidence_class": "screen",
        "recipient_realizability": "not established by OpenML; exact only for an adversary with this roster and all release leaf signals",
        "artifacts": artifacts,
        "config_sha256": config_hash,
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    suite = json.loads(args.suite_manifest.read_text())
    datasets = suite["datasets"]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    if args.limit is not None:
        datasets = datasets[: args.limit]
    seeds = [int(item) for item in config["replicate_seeds"]]
    if len(seeds) < 2:
        raise ValueError("composition requires at least two release seeds")
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for position, dataset in enumerate(datasets, start=1):
        print(f"[{position}/{len(datasets)}] {dataset['name']} OpenML {dataset['dataset_id']}", flush=True)
        try:
            records.append(run_one(dataset, config, seeds, args.force))
        except Exception as exc:
            failures.append(
                {
                    "dataset_id": dataset["dataset_id"],
                    "dataset_name": dataset["name"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            print(f"  failed: {failures[-1]}", flush=True)
    summary = {
        "experiment": "openml_cc18_three_release_composition",
        "suite_manifest_sha256": sha256_file(args.suite_manifest),
        "config_sha256": sha256_file(args.config),
        "expected_runs": len(datasets),
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
    }
    output = ROOT / "output" / "reproduction"
    write_json(output / "openml-composition-summary.json", summary)
    flat = [
        {
            "dataset_id": item["dataset_id"],
            "dataset_name": item["dataset_name"],
            "common_roster_records": item["common_roster_records"],
            "best_standalone_bayes_success": max(
                release["bayes_linkage_success"] for release in item["standalone"]
            ),
            "joint_bayes_success": item["joint"]["bayes_linkage_success"],
            "composition_amplification": item["composition_amplification_over_best_standalone"],
            "best_standalone_minimum_cell_size": min(
                release["minimum_cell_size"] for release in item["standalone"]
            ),
            "joint_minimum_cell_size": item["joint"]["minimum_cell_size"],
            "joint_no_greater_than_naive_sum": item["joint_no_greater_than_naive_sum"],
            "elapsed_seconds": item["elapsed_seconds"],
        }
        for item in records
    ]
    pd.DataFrame(flat).to_csv(output / "openml-composition-summary.csv", index=False)
    print(json.dumps({"expected_runs": len(datasets), "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
