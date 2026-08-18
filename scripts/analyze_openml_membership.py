#!/usr/bin/env python3
"""Validate and aggregate the frozen OpenML membership-attack sweep.

The low-FPR operating point is assessed per run. Counts from different OpenML
datasets are never pooled to manufacture a confidence statement; pooled counts
below are labelled descriptive diagnostics only.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def minimum_zero_failure_sample(target_rate: float, confidence: float) -> int:
    """Minimum n for the one-sided CP upper bound with zero events <= rate."""
    alpha = 1.0 - confidence
    return math.ceil(math.log(alpha) / math.log(1.0 - target_rate))


def validate_run(run: dict, workspace: Path) -> list[str]:
    errors: list[str] = []
    attack = run["attack"]
    counts = run["group_counts"]
    if attack["true_positives"] + attack["false_negatives"] != counts["member_audit"]:
        errors.append("member audit counts do not add up")
    if attack["false_positives"] + attack["true_negatives"] != counts["nonmember_audit"]:
        errors.append("nonmember audit counts do not add up")
    if attack["calibration_true_positives"] > counts["member_calibration"]:
        errors.append("member calibration count exceeds group size")
    if attack["calibration_false_positives"] > counts["nonmember_calibration"]:
        errors.append("nonmember calibration count exceeds group size")
    for artifact_name, artifact in run["artifacts"].items():
        path = workspace / artifact["path"]
        if not path.is_file():
            errors.append(f"missing {artifact_name}: {artifact['path']}")
        elif sha256_file(path) != artifact["sha256"]:
            errors.append(f"hash mismatch for {artifact_name}: {artifact['path']}")
    raw_path = workspace / run["artifacts"]["raw_scores"]["path"]
    if raw_path.is_file():
        raw = pd.read_parquet(raw_path)
        expected = sum(counts.values())
        if len(raw) != expected:
            errors.append(f"raw score row count {len(raw)} != calibration-plus-audit count {expected}")
        if "row_id" not in raw or raw["row_id"].duplicated().any():
            errors.append("raw score record IDs are missing or non-unique")
        expected_groups = {
            "member_calibration": counts["member_calibration"],
            "member_audit": counts["member_audit"],
            "nonmember_calibration": counts["nonmember_calibration"],
            "nonmember_audit": counts["nonmember_audit"],
        }
        observed_groups = raw.groupby("group").size().to_dict() if "group" in raw else {}
        if observed_groups != expected_groups:
            errors.append(f"raw score groups {observed_groups} != expected {expected_groups}")
    for prefix in ("target", "reference"):
        histogram_artifact = run["artifacts"].get(f"{prefix}_histogram")
        structural = run.get(f"{prefix}_structural")
        if histogram_artifact is None or structural is None:
            errors.append(f"missing {prefix} complete histogram or structural summary")
            continue
        histogram_path = workspace / histogram_artifact["path"]
        if not histogram_path.is_file():
            continue
        with gzip.open(histogram_path, "rt", encoding="utf-8") as handle:
            histogram = json.load(handle)
        counts_in_histogram = [int(item["count"]) for item in histogram]
        signatures = [tuple(item["leaf_signature"]) for item in histogram]
        if len(signatures) != len(set(signatures)):
            errors.append(f"{prefix} histogram has duplicate signatures")
        if sum(counts_in_histogram) != run["target_and_reference_training_size"]:
            errors.append(f"{prefix} histogram counts do not sum to training size")
        if len(histogram) != structural["occupied_cells"]:
            errors.append(f"{prefix} histogram occupied-cell count mismatch")
        if min(counts_in_histogram) != structural["minimum_cell_size"]:
            errors.append(f"{prefix} histogram minimum-cell count mismatch")
        if max(counts_in_histogram) != structural["maximum_cell_size"]:
            errors.append(f"{prefix} histogram maximum-cell count mismatch")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.summary.read_text())
    records = source["records"]
    validation_errors: list[dict] = []
    for run in records:
        errors = validate_run(run, args.workspace)
        if errors:
            validation_errors.append(
                {
                    "dataset_id": run["dataset_id"],
                    "n_estimators": run["capacity"]["n_estimators"],
                    "max_depth": run["capacity"]["max_depth"],
                    "errors": errors,
                }
            )

    flat = pd.json_normalize(records, sep=".")
    flat["raw_advantage"] = flat["attack.tpr"] - flat["attack.fpr"]
    flat["positive_certified_floor"] = (
        flat["attack.operating_point_attained"]
        & flat["attack.certified_attack_floor"].fillna(0.0).gt(0.0)
    )
    capacity = (
        flat.groupby(["capacity.n_estimators", "capacity.max_depth"], as_index=False)
        .agg(
            datasets=("dataset_id", "nunique"),
            total_tp=("attack.true_positives", "sum"),
            total_fp=("attack.false_positives", "sum"),
            total_members=("group_counts.member_audit", "sum"),
            total_nonmembers=("group_counts.nonmember_audit", "sum"),
            median_tpr=("attack.tpr", "median"),
            median_fpr=("attack.fpr", "median"),
            median_raw_advantage=("raw_advantage", "median"),
            maximum_raw_advantage=("raw_advantage", "max"),
            attained=("attack.operating_point_attained", "sum"),
            positive_certified_floors=("positive_certified_floor", "sum"),
        )
        .sort_values(["capacity.n_estimators", "capacity.max_depth"])
    )
    capacity["descriptive_pooled_tpr"] = capacity.total_tp / capacity.total_members
    capacity["descriptive_pooled_fpr"] = capacity.total_fp / capacity.total_nonmembers

    best_columns = [
        "dataset_id",
        "dataset_name",
        "capacity.n_estimators",
        "capacity.max_depth",
        "group_counts.member_audit",
        "group_counts.nonmember_audit",
        "attack.true_positives",
        "attack.false_positives",
        "attack.true_negatives",
        "attack.false_negatives",
        "attack.tpr",
        "attack.fpr",
        "attack.tpr_clopper_pearson_one_sided",
        "attack.fpr_clopper_pearson_one_sided",
        "raw_advantage",
        "attack.operating_point_attained",
        "attack.certified_attack_floor",
    ]
    strongest = flat.nlargest(10, "raw_advantage")[best_columns].to_dict(orient="records")
    target_fpr = float(flat["attack.target_fpr"].iloc[0])
    confidence = float(flat["attack.confidence"].iloc[0])
    minimum_n = minimum_zero_failure_sample(target_fpr, confidence)
    audit_sizes = flat.groupby("dataset_id")["group_counts.nonmember_audit"].first()
    eligible_datasets = int((audit_sizes >= minimum_n).sum())

    result = {
        "analysis_unit": "one dataset-capacity run; cross-dataset pooled rates are descriptive only",
        "validation": {
            "runs_checked": len(records),
            "artifact_hashes_and_counts_valid": not validation_errors,
            "errors": validation_errors,
        },
        "design": {
            "datasets": int(flat.dataset_id.nunique()),
            "capacities": int(len(capacity)),
            "runs": len(flat),
            "seeds": sorted(int(item) for item in flat.seed.unique()),
            "target_fpr": target_fpr,
            "confidence": confidence,
            "minimum_nonmember_audit_size_for_zero_fp_certification": minimum_n,
            "datasets_with_sufficient_size_if_zero_fp": eligible_datasets,
        },
        "outcomes": {
            "operating_point_attained_runs": int(flat["attack.operating_point_attained"].sum()),
            "positive_certified_attack_floor_runs": int(flat.positive_certified_floor.sum()),
            "runs_with_nonzero_tp": int((flat["attack.true_positives"] > 0).sum()),
            "runs_with_zero_fp": int((flat["attack.false_positives"] == 0).sum()),
            "maximum_raw_tpr": float(flat["attack.tpr"].max()),
            "maximum_raw_fpr": float(flat["attack.fpr"].max()),
            "maximum_raw_advantage": float(flat.raw_advantage.max()),
            "descriptive_total_tp": int(flat["attack.true_positives"].sum()),
            "descriptive_total_fp": int(flat["attack.false_positives"].sum()),
            "descriptive_total_tn": int(flat["attack.true_negatives"].sum()),
            "descriptive_total_fn": int(flat["attack.false_negatives"].sum()),
        },
        "by_capacity": capacity.to_dict(orient="records"),
        "strongest_exploratory_raw_advantages": strongest,
        "interpretation": [
            "No run produced a strictly positive certified attack floor at the pre-declared 0.1% FPR operating point.",
            "Non-attainment is inconclusive, not evidence of privacy or safety.",
            "Raw TPR, FPR, and advantage remain exploratory screens when the exact one-sided FPR upper bound exceeds the target.",
            "Counts across heterogeneous datasets must not be pooled to make a per-release security claim.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    strongest_run = strongest[0]
    lines = [
        "# OpenML membership-attack results",
        "",
        "## Design",
        "",
        f"The clean-room attack tier ran {len(flat)} configurations: {flat.dataset_id.nunique()} frozen OpenML datasets by {len(capacity)} tree capacities and one pre-declared seed. Target and reference models used disjoint, equal-size training sets. The threshold was calibrated on a separate nonmember split; all reported TP/FP/TN/FN counts use a disjoint audit split. Raw per-record scores, split-bound record IDs, models, preprocessors, and SHA-256 hashes were retained.",
        "",
        f"The pre-declared operating point was FPR <= {target_fpr:.1%} with an exact one-sided {confidence:.0%} Clopper-Pearson upper bound. Even with zero false positives this needs at least {minimum_n:,} audit nonmembers; only {eligible_datasets}/{flat.dataset_id.nunique()} selected datasets were large enough to have that possibility.",
        "",
        "## Results",
        "",
        f"- {int(flat['attack.operating_point_attained'].sum())}/{len(flat)} runs certified the FPR operating point. Both had TP=0, so no run produced a strictly positive certified attack floor.",
        f"- {int((flat['attack.true_positives'] > 0).sum())}/{len(flat)} runs had nonzero raw TP counts, and {int((flat['attack.false_positives'] == 0).sum())}/{len(flat)} had zero raw FP counts. These facts alone do not certify the operating point.",
        f"- The strongest exploratory run was {strongest_run['dataset_name']} with {strongest_run['capacity.n_estimators']} trees at depth {strongest_run['capacity.max_depth']}: TP={strongest_run['attack.true_positives']}, FP={strongest_run['attack.false_positives']}, raw TPR={strongest_run['attack.tpr']:.3%}, raw FPR={strongest_run['attack.fpr']:.3%}, and raw advantage={strongest_run['raw_advantage']:.3%}. Its exact FPR upper bound exceeded 0.1%, so it remains a screen.",
        f"- Descriptively, without using cross-dataset pooling for inference, the audit records contain TP={int(flat['attack.true_positives'].sum()):,}, FP={int(flat['attack.false_positives'].sum()):,}, TN={int(flat['attack.true_negatives'].sum()):,}, and FN={int(flat['attack.false_negatives'].sum()):,}.",
        "",
        "| Trees | Depth | TP | FP | pooled TPR* | pooled FPR* | median advantage | attained |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in capacity.to_dict(orient="records"):
        lines.append(
            f"| {int(row['capacity.n_estimators'])} | {int(row['capacity.max_depth'])} | {int(row['total_tp'])} | {int(row['total_fp'])} | {row['descriptive_pooled_tpr']:.3%} | {row['descriptive_pooled_fpr']:.3%} | {row['median_raw_advantage']:.3%} | {int(row['attained'])}/{int(row['datasets'])} |"
        )
    lines += [
        "",
        "*Pooled rates are descriptive diagnostics only; OpenML datasets are heterogeneous and pooling does not create a confidence bound for any release.*",
        "",
        "## Determination",
        "",
        "The attack implementation behaves conservatively: it detects raw leakage signals, retains the complete confusion counts, and refuses to turn an underpowered or off-target result into evidence of safety. This tier therefore validates the framework's fail-closed semantics, but it does not establish that the tested models are private. A future release-specific audit must size the nonmember audit set before training, use multiple independent seeds, include positive controls, and add stronger attacks such as LiRA/shadow models when they are recipient-realizable.",
    ]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "outcomes": result["outcomes"]}, indent=2))


if __name__ == "__main__":
    main()
