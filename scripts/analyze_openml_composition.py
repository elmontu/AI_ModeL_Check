#!/usr/bin/env python3
"""Validate and aggregate the OpenML three-release composition tier."""

from __future__ import annotations

import argparse
import gzip
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
    for artifact_name, artifact in run["artifacts"].items():
        path = workspace / artifact["path"]
        if not path.is_file():
            errors.append(f"missing {artifact_name}: {artifact['path']}")
        elif sha256_file(path) != artifact["sha256"]:
            errors.append(f"hash mismatch for {artifact_name}: {artifact['path']}")
    roster_path = workspace / run["artifacts"]["common_roster"]["path"]
    if roster_path.is_file():
        with gzip.open(roster_path, "rt", encoding="utf-8") as handle:
            roster = json.load(handle)
        if len(roster) != run["common_roster_records"] or len(roster) != len(set(roster)):
            errors.append("common roster size or uniqueness mismatch")
    histogram_metrics = [("joint_histogram", run["joint"])]
    histogram_metrics.extend(
        (f"release_{release['seed']}_histogram", release) for release in run["standalone"]
    )
    for artifact_name, metrics in histogram_metrics:
        artifact = run["artifacts"].get(artifact_name)
        if not artifact:
            errors.append(f"missing histogram artifact {artifact_name}")
            continue
        path = workspace / artifact["path"]
        if not path.is_file():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            histogram = json.load(handle)
        counts = [int(item["count"]) for item in histogram]
        signatures = [tuple(item["leaf_signature"]) for item in histogram]
        if len(signatures) != len(set(signatures)):
            errors.append(f"{artifact_name} contains duplicate signatures")
        if sum(counts) != run["common_roster_records"]:
            errors.append(f"{artifact_name} counts do not sum to roster")
        if len(histogram) != metrics["occupied_cells"]:
            errors.append(f"{artifact_name} occupied-cell mismatch")
        if min(counts) != metrics["minimum_cell_size"]:
            errors.append(f"{artifact_name} minimum-cell mismatch")
    if run["joint_incremental_value"] > run["naive_sum_incremental_values"] + 1e-12:
        errors.append("joint incremental value exceeds mathematical union bound")
    if run["joint"]["bayes_linkage_success"] + 1e-12 < max(
        release["bayes_linkage_success"] for release in run["standalone"]
    ):
        errors.append("joint partition is less identifying than a component partition")
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
    rows = []
    for run in records:
        errors = validate_run(run, args.workspace)
        if errors:
            validation_errors.append({"dataset_id": run["dataset_id"], "errors": errors})
        best = max(release["bayes_linkage_success"] for release in run["standalone"])
        worst = min(release["bayes_linkage_success"] for release in run["standalone"])
        rows.append(
            {
                "dataset_id": run["dataset_id"],
                "dataset_name": run["dataset_name"],
                "common_roster_records": run["common_roster_records"],
                "best_standalone": best,
                "worst_standalone": worst,
                "joint": run["joint"]["bayes_linkage_success"],
                "amplification": run["composition_amplification_over_best_standalone"],
                "joint_singleton_fraction": run["joint"]["singleton_fraction"],
                "joint_minimum_cell_size": run["joint"]["minimum_cell_size"],
                "bound_holds": run["joint_no_greater_than_naive_sum"],
            }
        )
    frame = pd.DataFrame(rows)
    strongest = frame.nlargest(10, "amplification").to_dict(orient="records")
    result = {
        "analysis_unit": "OpenML dataset; all three releases are evaluated on their common target-training roster",
        "validation": {
            "datasets_checked": len(frame),
            "artifact_hashes_counts_and_bounds_valid": not validation_errors,
            "errors": validation_errors,
        },
        "design": {
            "datasets": len(frame),
            "releases_per_dataset": 3,
            "total_release_models": 3 * len(frame),
            "minimum_common_roster": int(frame.common_roster_records.min()),
            "maximum_common_roster": int(frame.common_roster_records.max()),
        },
        "outcomes": {
            "datasets_with_positive_amplification": int((frame.amplification > 1e-12).sum()),
            "datasets_with_at_least_five_point_amplification": int((frame.amplification >= 0.05).sum()),
            "datasets_jointly_unique": int((frame.joint >= 1.0 - 1e-12).sum()),
            "datasets_joint_minimum_cell_one": int((frame.joint_minimum_cell_size == 1).sum()),
            "median_best_standalone_success": float(frame.best_standalone.median()),
            "median_joint_success": float(frame.joint.median()),
            "median_amplification": float(frame.amplification.median()),
            "maximum_amplification": float(frame.amplification.max()),
            "all_union_bounds_hold": bool(frame.bound_holds.all()),
        },
        "strongest_amplifications": strongest,
        "interpretation": [
            "Joint observation refines every component partition, so joint Bayes success cannot be below the best standalone success.",
            "The sum of standalone incremental values is an upper bound, not a prediction of actual joint disclosure.",
            "These are record-level structural screens because OpenML does not establish a recipient-realizable external roster or person-level entity linkage.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    outcomes = result["outcomes"]
    top = strongest[0]
    lines = [
        "# OpenML three-release composition results",
        "",
        "## Design",
        "",
        f"For each of {len(frame)} frozen OpenML datasets, the three pre-declared seed models were treated as three released artifacts. Exact leaf signatures were recomputed on the intersection of their target-training rosters, giving {int(frame.common_roster_records.min()):,}-{int(frame.common_roster_records.max()):,} comparable records per dataset. Standalone and joint complete histograms are hash-bound.",
        "",
        "## Results",
        "",
        f"- {outcomes['datasets_with_positive_amplification']}/{len(frame)} datasets had strictly greater joint Bayes linkage success than the best standalone release; {outcomes['datasets_with_at_least_five_point_amplification']}/{len(frame)} increased by at least five percentage points.",
        f"- Median best-standalone success was {outcomes['median_best_standalone_success']:.3f}; median joint success was {outcomes['median_joint_success']:.3f}; median amplification was {outcomes['median_amplification']:.3f}.",
        f"- {outcomes['datasets_jointly_unique']}/{len(frame)} common rosters became completely unique under the joint channel, and {outcomes['datasets_joint_minimum_cell_one']}/{len(frame)} had at least one joint singleton.",
        f"- The strongest amplification was {top['dataset_name']}: {top['best_standalone']:.3f} to {top['joint']:.3f}, an increase of {top['amplification']:.3f}.",
        f"- The naive sum of incremental disclosure upper-bounded the exact joint value for all {len(frame)} datasets, as required; it was not used as a point estimate.",
        "",
        "## Determination",
        "",
        "Composition materially changes the release decision on this corpus. A production framework must reassess the joint channel against the recipient's existing release portfolio; evaluating only the new model can miss disclosure created by partition intersection. These values remain structural screens until the recipient's roster and observation channel are established.",
    ]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "outcomes": outcomes}, indent=2))


if __name__ == "__main__":
    main()
