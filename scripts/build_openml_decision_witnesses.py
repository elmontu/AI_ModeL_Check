#!/usr/bin/env python3
"""Search all retained OpenML composition rosters for non-degenerate decision-theory witnesses."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_composition import load_release, read_json_gz  # noqa: E402
from run_openml_structural import capped_indices, row_ids, sha256_file, write_json, write_json_gz  # noqa: E402


def observation_digest(row: np.ndarray) -> str:
    payload = ",".join(str(int(value)) for value in np.asarray(row).ravel()).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def exact_guess_value(observations: np.ndarray, mask: np.ndarray | None = None) -> float:
    selected = observations if mask is None else observations[mask]
    return len(set(selected.tolist())) / len(selected)


def attribute_value(observations: np.ndarray, labels: np.ndarray) -> float:
    cells: dict[str, Counter[int]] = defaultdict(Counter)
    for observation, label in zip(observations, labels, strict=True):
        cells[str(observation)][int(label)] += 1
    return sum(max(counts.values()) for counts in cells.values()) / len(labels)


def anchor_masks(series: pd.Series, minimum_support: int) -> list[tuple[str, str, np.ndarray, np.ndarray]]:
    masks: list[tuple[str, str, np.ndarray, np.ndarray]] = []
    if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype):
        numeric = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(numeric)
        if finite.sum() >= 2 * minimum_support:
            threshold = float(np.median(numeric[finite]))
            low = finite & (numeric <= threshold)
            high = finite & (numeric > threshold)
            if low.sum() >= minimum_support and high.sum() >= minimum_support:
                masks.append((
                    f"value <= median ({threshold:.12g})",
                    f"value > median ({threshold:.12g})",
                    low,
                    high,
                ))
    else:
        values = series.astype("string").fillna("<NA>").to_numpy(dtype=str)
        counts = Counter(values.tolist())
        if counts:
            category, _ = counts.most_common(1)[0]
            first = values == category
            second = ~first
            if first.sum() >= minimum_support and second.sum() >= minimum_support:
                masks.append((
                    f"value == {category!r}",
                    f"value != {category!r}",
                    first,
                    second,
                ))
    return masks


def load_dataset_observations(
    dataset: dict[str, Any],
    composition: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]:
        raise ValueError(f"snapshot hash mismatch for OpenML {dataset_id}")
    frame = pd.read_parquet(snapshot)
    target_encoder = LabelEncoder()
    target = target_encoder.fit_transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(
        target,
        max(int(config["row_cap"]) * 2, 500),
        int(config["master_seed"]),
    )
    selected_frame = frame.iloc[selected].reset_index(drop=True)
    selected_target = target[selected]
    selected_ids = identities[selected]
    id_to_index = {identifier: index for index, identifier in enumerate(selected_ids)}
    common_path = ROOT / composition["artifacts"]["common_roster"]["path"]
    if sha256_file(common_path) != composition["artifacts"]["common_roster"]["sha256"]:
        raise ValueError(f"common roster hash mismatch for OpenML {dataset_id}")
    common_ids = read_json_gz(common_path)
    common_indices = np.asarray([id_to_index[identifier] for identifier in common_ids], dtype=int)
    features = selected_frame.drop(columns=[dataset["target"]]).iloc[common_indices].reset_index(drop=True)
    labels = selected_target[common_indices]

    releases: dict[int, dict[str, Any]] = {}
    for seed in composition["release_seeds"]:
        manifest, preprocessor, model, _ = load_release(dataset_id, int(seed))
        transformed = preprocessor.transform(features)
        leaves = np.asarray(model.apply(transformed))
        if leaves.ndim == 1:
            leaves = leaves.reshape(-1, 1)
        observations = np.asarray([observation_digest(row) for row in leaves], dtype=object)
        predictions = np.asarray(model.predict(transformed), dtype=int)
        releases[int(seed)] = {
            "observations": observations,
            "predictions": predictions,
            "manifest_path": str(
                ROOT
                / "reproduction/openml/runs/structural"
                / f"openml-{dataset_id}"
                / f"seed-{seed}"
                / "run-manifest.json"
            ),
            "manifest_sha256": sha256_file(
                ROOT
                / "reproduction/openml/runs/structural"
                / f"openml-{dataset_id}"
                / f"seed-{seed}"
                / "run-manifest.json"
            ),
            "model_sha256": manifest["artifacts"]["model"]["sha256"],
        }
    return {
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "target": dataset["target"],
        "state_ids": np.asarray(common_ids, dtype=object),
        "features": features,
        "labels": labels,
        "releases": releases,
    }


def feature_attribute_candidates(
    data: dict[str, Any],
    minimum_support: int,
) -> list[tuple[str, str, np.ndarray, int]]:
    candidates: list[tuple[str, str, np.ndarray, int]] = [(
        str(data["target"]),
        "exact task-target recovery",
        np.asarray(data["labels"], dtype=int),
        int(len(np.unique(data["labels"]))),
    )]
    for feature in data["features"].columns:
        series = data["features"][feature]
        if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype):
            numeric = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
            finite = np.isfinite(numeric)
            if finite.sum() < 2 * minimum_support:
                continue
            threshold = float(np.median(numeric[finite]))
            labels = np.full(len(numeric), 2, dtype=int)
            labels[finite & (numeric <= threshold)] = 0
            labels[finite & (numeric > threshold)] = 1
            counts = Counter(labels.tolist())
            if counts[0] >= minimum_support and counts[1] >= minimum_support:
                candidates.append((
                    str(feature),
                    f"recovery of <=median versus >median band at {threshold:.12g}; missing is a separate class",
                    labels,
                    len(counts),
                ))
        else:
            values = series.astype("string").fillna("<NA>").to_numpy(dtype=str)
            counts = Counter(values.tolist())
            if not counts:
                continue
            category, _ = counts.most_common(1)[0]
            labels = (values != category).astype(int)
            label_counts = Counter(labels.tolist())
            if label_counts[0] >= minimum_support and label_counts[1] >= minimum_support:
                candidates.append((
                    str(feature),
                    f"recovery of most-common category {category!r} versus all other values",
                    labels,
                    2,
                ))
    return candidates


def metric_candidates(
    data: dict[str, Any],
    seed_left: int,
    seed_right: int,
    minimum_support: int,
) -> list[dict[str, Any]]:
    left = data["releases"][seed_left]["observations"]
    right = data["releases"][seed_right]["observations"]
    identity = (exact_guess_value(left), exact_guess_value(right))
    candidates = []
    for attribute_name, definition, labels, classes in feature_attribute_candidates(data, minimum_support):
        attribute = (attribute_value(left, labels), attribute_value(right, labels))
        directions = (identity[0] - identity[1], attribute[0] - attribute[1])
        if directions[0] * directions[1] >= 0.0:
            continue
        candidates.append({
            "kind": "decision_metric_reversal",
            "dataset_id": data["dataset_id"],
            "dataset_name": data["dataset_name"],
            "records": len(labels),
            "left_seed": seed_left,
            "right_seed": seed_right,
            "identity_values": list(identity),
            "attribute_values": list(attribute),
            "identity_gap": abs(directions[0]),
            "attribute_gap": abs(directions[1]),
            "minimum_gap": min(abs(directions[0]), abs(directions[1])),
            "attribute": attribute_name,
            "attribute_definition": definition,
            "attribute_classes": int(classes),
            "attribute_labels": labels,
        })
    return candidates


def anchor_candidates(
    data: dict[str, Any],
    seed_left: int,
    seed_right: int,
    minimum_support: int,
) -> list[dict[str, Any]]:
    left = data["releases"][seed_left]["observations"]
    right = data["releases"][seed_right]["observations"]
    candidates = []
    for feature in data["features"].columns:
        for first_definition, second_definition, first_mask, second_mask in anchor_masks(
            data["features"][feature], minimum_support
        ):
            first_values = (exact_guess_value(left, first_mask), exact_guess_value(right, first_mask))
            second_values = (exact_guess_value(left, second_mask), exact_guess_value(right, second_mask))
            first_direction = first_values[0] - first_values[1]
            second_direction = second_values[0] - second_values[1]
            if first_direction * second_direction >= 0.0:
                continue
            if first_direction > 0.0:
                left_definition, right_definition = first_definition, second_definition
                left_mask, right_mask = first_mask, second_mask
                left_values, right_values = first_values, second_values
            else:
                left_definition, right_definition = second_definition, first_definition
                left_mask, right_mask = second_mask, first_mask
                left_values, right_values = second_values, first_values
            candidates.append({
                "kind": "population_anchor_reversal",
                "dataset_id": data["dataset_id"],
                "dataset_name": data["dataset_name"],
                "records": len(left),
                "left_seed": seed_left,
                "right_seed": seed_right,
                "anchor_feature": str(feature),
                "left_favouring_population": left_definition,
                "right_favouring_population": right_definition,
                "left_anchor_values": list(left_values),
                "right_anchor_values": list(right_values),
                "left_anchor_support": int(left_mask.sum()),
                "right_anchor_support": int(right_mask.sum()),
                "minimum_gap": min(left_values[0] - left_values[1], right_values[1] - right_values[0]),
                "left_mask": left_mask,
                "right_mask": right_mask,
            })
    return candidates


def substitution_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    for seed, release in data["releases"].items():
        observations = release["observations"]
        predictions = release["predictions"]
        prediction_by_observation: dict[str, set[int]] = defaultdict(set)
        for observation, prediction in zip(observations, predictions, strict=True):
            prediction_by_observation[str(observation)].add(int(prediction))
        if any(len(values) != 1 for values in prediction_by_observation.values()):
            continue
        label_value = exact_guess_value(predictions.astype(str))
        leaf_value = exact_guess_value(observations)
        candidates.append({
            "kind": "substitution_separation",
            "dataset_id": data["dataset_id"],
            "dataset_name": data["dataset_name"],
            "records": len(observations),
            "seed": seed,
            "evaluated_surface": "predicted class label",
            "released_surface": "full tree leaf signature",
            "evaluated_exact_identity_value": label_value,
            "released_exact_identity_value": leaf_value,
            "value_gap": leaf_value - label_value,
            "label_is_deterministic_garbling_of_leaf_signature": True,
        })
    return candidates


def serializable_witness(witness: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in witness.items()
        if key not in {"left_mask", "right_mask", "attribute_labels"}
    }


def witness_rows(kind: str, witness: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "substitution":
        seed_left = int(witness["seed"])
        seed_right = None
    else:
        seed_left = int(witness["left_seed"])
        seed_right = int(witness["right_seed"])
    left = data["releases"][seed_left]
    rows = []
    for index, state_id in enumerate(data["state_ids"]):
        row = {
            "state_id": str(state_id),
            "left_observation": str(left["observations"][index]),
            "target_attribute": int(
                witness.get("attribute_labels", data["labels"])[index]
            ),
        }
        if seed_right is not None:
            row["right_observation"] = str(data["releases"][seed_right]["observations"][index])
        if kind == "substitution":
            row["evaluated_label_observation"] = str(int(left["predictions"][index]))
        elif kind == "anchoring":
            if bool(witness["left_mask"][index]):
                row["anchor"] = "left_favouring"
            elif bool(witness["right_mask"][index]):
                row["anchor"] = "right_favouring"
            else:
                row["anchor"] = "outside_anchor_support"
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--composition-summary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--minimum-records", type=int, default=300)
    parser.add_argument("--minimum-anchor-support", type=int, default=100)
    parser.add_argument("--minimum-gap", type=float, default=0.01)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-raw", type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.suite_manifest.read_text())
    composition_summary = json.loads(args.composition_summary.read_text())
    config = json.loads(args.config.read_text())
    datasets = {int(item["dataset_id"]): item for item in suite["datasets"]}
    composition_records = {
        int(item["dataset_id"]): item for item in composition_summary["records"]
    }
    metric_pool: list[dict[str, Any]] = []
    anchor_pool: list[dict[str, Any]] = []
    substitution_pool: list[dict[str, Any]] = []
    data_cache: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    examined_rows = 0
    for position, dataset_id in enumerate(sorted(composition_records), start=1):
        print(f"[{position}/{len(composition_records)}] OpenML {dataset_id}", flush=True)
        try:
            data = load_dataset_observations(
                datasets[dataset_id], composition_records[dataset_id], config
            )
            examined_rows += len(data["state_ids"])
            if len(data["state_ids"]) < args.minimum_records:
                continue
            data_cache[dataset_id] = data
            for seed_left, seed_right in combinations(sorted(data["releases"]), 2):
                for candidate in metric_candidates(
                    data, seed_left, seed_right, args.minimum_anchor_support
                ):
                    if candidate["minimum_gap"] >= args.minimum_gap:
                        metric_pool.append(candidate)
                anchor_pool.extend(
                    candidate
                    for candidate in anchor_candidates(
                        data, seed_left, seed_right, args.minimum_anchor_support
                    )
                    if candidate["minimum_gap"] >= args.minimum_gap
                )
            substitution_pool.extend(
                item
                for item in substitution_candidates(data)
                if item["value_gap"] >= args.minimum_gap
            )
        except Exception as exc:
            errors.append({
                "dataset_id": dataset_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
    if not metric_pool or not anchor_pool or not substitution_pool:
        raise RuntimeError(
            "non-degenerate witness search failed: "
            f"metric={len(metric_pool)}, anchor={len(anchor_pool)}, substitution={len(substitution_pool)}"
        )
    metric = max(metric_pool, key=lambda item: (item["minimum_gap"], item["records"]))
    anchor = max(anchor_pool, key=lambda item: (item["minimum_gap"], min(item["left_anchor_support"], item["right_anchor_support"])))
    substitution = max(substitution_pool, key=lambda item: (item["value_gap"], item["records"]))
    raw = {
        "metric_reversal": {
            "witness": serializable_witness(metric),
            "rows": witness_rows("metric", metric, data_cache[int(metric["dataset_id"])]),
        },
        "anchoring_reversal": {
            "witness": serializable_witness(anchor),
            "rows": witness_rows("anchoring", anchor, data_cache[int(anchor["dataset_id"])]),
        },
        "substitution_separation": {
            "witness": serializable_witness(substitution),
            "rows": witness_rows("substitution", substitution, data_cache[int(substitution["dataset_id"])]),
        },
    }
    args.output_raw.parent.mkdir(parents=True, exist_ok=True)
    write_json_gz(args.output_raw, raw)
    result = {
        "study": "OpenML finite-experiment decision-theory witness search",
        "claim_boundary": (
            "non-degenerate record-level witnesses on retained OpenML benchmark populations; "
            "not METABRIC and not a government-population prevalence estimate"
        ),
        "search": {
            "datasets_considered": len(composition_records),
            "datasets_loaded_at_minimum_size": len(data_cache),
            "common_roster_rows_examined": examined_rows,
            "minimum_records": args.minimum_records,
            "minimum_anchor_support": args.minimum_anchor_support,
            "minimum_value_gap": args.minimum_gap,
            "metric_reversal_candidates": len(metric_pool),
            "anchoring_reversal_candidates": len(anchor_pool),
            "substitution_separation_candidates": len(substitution_pool),
            "errors": errors,
        },
        "selected": {
            "decision_metric_reversal": serializable_witness(metric),
            "population_anchor_reversal": serializable_witness(anchor),
            "substitution_separation": serializable_witness(substitution),
        },
        "raw_witness": {
            "path": str(args.output_raw),
            "sha256": sha256_file(args.output_raw),
        },
        "source_hashes": {
            "suite_manifest": sha256_file(args.suite_manifest),
            "composition_summary": sha256_file(args.composition_summary),
            "config": sha256_file(args.config),
        },
    }
    write_json(args.output_json, result)
    print(json.dumps({"search": result["search"], "selected": result["selected"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
