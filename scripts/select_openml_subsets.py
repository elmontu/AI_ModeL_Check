#!/usr/bin/env python3
"""Pre-declare expensive OpenML subsets from metadata only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_vector(dataset: dict[str, Any], scales: dict[str, tuple[float, float]]) -> np.ndarray:
    raw = {
        "rows": math.log1p(dataset["rows"]),
        "features": math.log1p(dataset["features"]),
        "classes": math.log1p(dataset["classes"]),
    }
    normalized = [
        (raw[name] - low) / (high - low) if high > low else 0.0
        for name, (low, high) in scales.items()
    ]
    normalized.append(1.0 if dataset["missing_feature_values"] > 0 else 0.0)
    return np.asarray(normalized, dtype=float)


def farthest(items: list[dict[str, Any]], count: int, salt: str) -> list[dict[str, Any]]:
    if count > len(items):
        raise ValueError("subset count exceeds available items")
    raw_values = {
        name: [math.log1p(item[name]) for item in items]
        for name in ("rows", "features", "classes")
    }
    scales = {name: (min(values), max(values)) for name, values in raw_values.items()}
    vectors = {item["dataset_id"]: metadata_vector(item, scales) for item in items}
    tie = lambda item: hashlib.sha256(f"{salt}:{item['dataset_id']}".encode()).hexdigest()
    selected = [min(items, key=tie)]
    remaining = [item for item in items if item not in selected]
    while len(selected) < count:
        def score(item: dict[str, Any]) -> tuple[float, str]:
            distance = min(
                float(np.linalg.norm(vectors[item["dataset_id"]] - vectors[chosen["dataset_id"]]))
                for chosen in selected
            )
            return distance, tie(item)
        chosen = max(remaining, key=score)
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def balanced_subset(datasets: list[dict[str, Any]], count: int, salt: str) -> list[dict[str, Any]]:
    binary = [item for item in datasets if item["classes"] == 2]
    multiclass = [item for item in datasets if item["classes"] > 2]
    binary_count = count // 2
    selected = farthest(binary, binary_count, salt + ":binary")
    selected.extend(farthest(multiclass, count - binary_count, salt + ":multiclass"))
    return sorted(selected, key=lambda item: int(item["dataset_id"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    suite = json.loads(args.suite_manifest.read_text(encoding="utf-8"))
    datasets = suite["datasets"]
    salt = f"mra-openml-subset:{config['master_seed']}"
    expensive = balanced_subset(datasets, int(config["expensive_subset_size"]), salt + ":expensive")
    neural = balanced_subset(expensive, int(config["neural_dp_subset_size"]), salt + ":neural")
    output = {
        "manifest_version": "1.0",
        "selection_frozen_before_expensive_outcomes": True,
        "selection_algorithm": "balanced binary/multiclass deterministic farthest-point sampling over log rows, log features, log classes, and missingness",
        "selection_uses_leakage_or_utility_outcomes": False,
        "master_seed": config["master_seed"],
        "suite_manifest_sha256": sha256_file(args.suite_manifest),
        "config_sha256": sha256_file(args.config),
        "expensive_subset": expensive,
        "neural_dp_subset": neural,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "expensive_subset": [(item["dataset_id"], item["name"]) for item in expensive],
        "neural_dp_subset": [(item["dataset_id"], item["name"]) for item in neural],
    }, indent=2))


if __name__ == "__main__":
    main()
