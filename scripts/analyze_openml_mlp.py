#!/usr/bin/env python3
"""Validate and aggregate the frozen non-private OpenML MLP tier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_run(run: dict, workspace: Path) -> list[str]:
    errors: list[str] = []
    counts = run["group_counts"]
    attack = run["attack"]
    if attack["true_positives"] + attack["false_negatives"] != counts["member_audit"]:
        errors.append("member audit counts do not add up")
    if attack["false_positives"] + attack["true_negatives"] != counts["nonmember_audit"]:
        errors.append("nonmember audit counts do not add up")
    for artifact_name, artifact in run["artifacts"].items():
        path = workspace / artifact["path"]
        if not path.is_file():
            errors.append(f"missing {artifact_name}: {artifact['path']}")
        elif sha256_file(path) != artifact["sha256"]:
            errors.append(f"hash mismatch for {artifact_name}: {artifact['path']}")
    raw_path = workspace / run["artifacts"]["raw_scores"]["path"]
    if raw_path.is_file():
        raw = pd.read_parquet(raw_path)
        expected_groups = {
            "member_calibration": counts["member_calibration"],
            "member_audit": counts["member_audit"],
            "nonmember_calibration": counts["nonmember_calibration"],
            "nonmember_audit": counts["nonmember_audit"],
        }
        observed_groups = raw.groupby("group").size().to_dict()
        if observed_groups != expected_groups:
            errors.append(f"raw score groups {observed_groups} != expected {expected_groups}")
        if "row_id" not in raw or raw.row_id.duplicated().any():
            errors.append("raw score row IDs are missing or non-unique")
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
    validation_errors = []
    for run in records:
        errors = validate_run(run, args.workspace)
        if errors:
            validation_errors.append(
                {"dataset_id": run["dataset_id"], "seed": run["seed"], "errors": errors}
            )
    flat = pd.json_normalize(records, sep=".")
    flat["raw_advantage"] = flat["attack.tpr"] - flat["attack.fpr"]
    flat["chance_balanced_accuracy"] = flat["class_labels"].map(lambda labels: 1.0 / len(labels))
    flat["utility_excess_over_chance"] = (
        flat["utility.balanced_accuracy"] - flat["chance_balanced_accuracy"]
    )
    flat["positive_certified_floor"] = (
        flat["attack.operating_point_attained"]
        & flat["attack.certified_attack_floor"].fillna(0.0).gt(0.0)
    )
    grouped = flat.groupby(["dataset_id", "dataset_name"], as_index=False).agg(
        replicates=("seed", "count"),
        balanced_accuracy_mean=("utility.balanced_accuracy", "mean"),
        balanced_accuracy_min=("utility.balanced_accuracy", "min"),
        balanced_accuracy_max=("utility.balanced_accuracy", "max"),
        roc_auc_mean=("utility.roc_auc", "mean"),
        utility_excess_over_chance_mean=("utility_excess_over_chance", "mean"),
        raw_advantage_mean=("raw_advantage", "mean"),
        raw_advantage_min=("raw_advantage", "min"),
        raw_advantage_max=("raw_advantage", "max"),
        attained_runs=("attack.operating_point_attained", "sum"),
        positive_certified_floor_runs=("positive_certified_floor", "sum"),
        target_converged_runs=("target_training.converged", "sum"),
        reference_converged_runs=("reference_training.converged", "sum"),
    )
    strongest = flat.nlargest(10, "raw_advantage")[[
        "dataset_id",
        "dataset_name",
        "seed",
        "utility.balanced_accuracy",
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
    ]].to_dict(orient="records")
    result = {
        "analysis_unit": "OpenML dataset; seeds are repeated measurements and per-run attack intervals are not pooled",
        "validation": {
            "runs_checked": len(flat),
            "artifact_hashes_and_counts_valid": not validation_errors,
            "errors": validation_errors,
        },
        "design": {
            "datasets": int(flat.dataset_id.nunique()),
            "runs": len(flat),
            "replicate_seeds": sorted(int(item) for item in flat.seed.unique()),
            "model_family": sorted(flat.model_family.unique().tolist()),
            "target_fpr": float(flat["attack.target_fpr"].iloc[0]),
            "confidence": float(flat["attack.confidence"].iloc[0]),
        },
        "outcomes": {
            "target_models_converged": int(flat["target_training.converged"].sum()),
            "reference_models_converged": int(flat["reference_training.converged"].sum()),
            "operating_point_attained_runs": int(flat["attack.operating_point_attained"].sum()),
            "positive_certified_attack_floor_runs": int(flat.positive_certified_floor.sum()),
            "runs_with_nonzero_tp": int((flat["attack.true_positives"] > 0).sum()),
            "maximum_raw_advantage": float(flat.raw_advantage.max()),
            "median_dataset_mean_balanced_accuracy": float(grouped.balanced_accuracy_mean.median()),
            "median_dataset_mean_utility_excess_over_chance": float(
                grouped.utility_excess_over_chance_mean.median()
            ),
            "median_dataset_mean_raw_advantage": float(grouped.raw_advantage_mean.median()),
            "maximum_within_dataset_seed_advantage_range": float(
                (grouped.raw_advantage_max - grouped.raw_advantage_min).max()
            ),
            "descriptive_total_tp": int(flat["attack.true_positives"].sum()),
            "descriptive_total_fp": int(flat["attack.false_positives"].sum()),
            "descriptive_total_tn": int(flat["attack.true_negatives"].sum()),
            "descriptive_total_fn": int(flat["attack.false_negatives"].sum()),
        },
        "by_dataset": grouped.to_dict(orient="records"),
        "strongest_exploratory_raw_advantages": strongest,
        "interpretation": [
            "The generic empirical-attack evidence contract operates on MLPs without tree-specific structure.",
            "A negative or unattained empirical attack cannot clear a non-private MLP release.",
            "Utility and convergence must be read with privacy screens; a model that learned little is not a useful privacy frontier.",
            "No differential-privacy claim is made by this non-private tier.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    best = strongest[0]
    lines = [
        "# OpenML non-private MLP results",
        "",
        "## Design",
        "",
        f"The model-family tier trained independent target/reference MLP pipelines for {flat.dataset_id.nunique()} frozen OpenML datasets and {len(flat.seed.unique())} pre-declared seeds ({len(flat)} paired runs). Each model independently fitted imputation, categorical encoding, standardisation, and a one-hidden-layer MLP. Raw record-level scores and full TP/FP/TN/FN counts were retained with hash-bound artifacts.",
        "",
        "This is a non-private neural tier. It tests model-family independence of the empirical evidence contract; it supplies no differential-privacy ceiling.",
        "",
        "## Results",
        "",
        f"- {int(flat['target_training.converged'].sum())}/{len(flat)} target models and {int(flat['reference_training.converged'].sum())}/{len(flat)} reference models satisfied the configured convergence rule.",
        f"- Median dataset-mean balanced accuracy was {grouped.balanced_accuracy_mean.median():.3f}; median excess over chance balanced accuracy was {grouped.utility_excess_over_chance_mean.median():.3f}.",
        f"- {int(flat['attack.operating_point_attained'].sum())}/{len(flat)} attacks certified the 0.1% FPR operating point, and {int(flat.positive_certified_floor.sum())} produced a strictly positive certified floor.",
        f"- The strongest exploratory screen was {best['dataset_name']} seed {best['seed']}: balanced accuracy {best['utility.balanced_accuracy']:.3f}, TP={best['attack.true_positives']}, FP={best['attack.false_positives']}, raw TPR={best['attack.tpr']:.3%}, raw FPR={best['attack.fpr']:.3%}, and raw advantage={best['raw_advantage']:.3%}.",
        f"- The maximum within-dataset raw-advantage range across seeds was {(grouped.raw_advantage_max-grouped.raw_advantage_min).max():.3%}, so a single neural seed is not adequate.",
        "",
        "| Dataset | Mean balanced accuracy | Excess over chance | Mean raw advantage | Advantage range | FPR attained |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in grouped.sort_values("dataset_id").to_dict(orient="records"):
        lines.append(
            f"| {row['dataset_name']} | {row['balanced_accuracy_mean']:.3f} | {row['utility_excess_over_chance_mean']:.3f} | {row['raw_advantage_mean']:.3%} | {row['raw_advantage_min']:.3%}-{row['raw_advantage_max']:.3%} | {int(row['attained_runs'])}/{int(row['replicates'])} |"
        )
    lines += [
        "",
        "## Determination",
        "",
        "The framework's attack-evidence interface is model-family-independent in execution: the same split, count, confidence, operating-point, and fail-closed semantics work for MLPs. The tree-only exact partition theorem does not transfer to MLPs. A non-private MLP can be blocked by a validated attack floor, but it cannot be cleared by a failed empirical attack; clearance needs an applicable validated ceiling such as a correctly scoped DP accountant or another release-specific theorem.",
    ]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "outcomes": result["outcomes"]}, indent=2))


if __name__ == "__main__":
    main()
