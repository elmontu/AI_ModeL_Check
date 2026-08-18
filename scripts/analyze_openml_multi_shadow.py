#!/usr/bin/env python3
"""Validate and aggregate the multi-shadow likelihood-ratio tier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.summary.read_text())
    errors, rows = [], []
    for run in source["records"]:
        run_errors = []
        artifact_records = [run["artifacts"]["raw_scores"], run["artifacts"]["shadow_assignment"], run["target_manifest"], run["target_raw_scores"]] + run["artifacts"]["shadow_model_artifacts"]
        for artifact in artifact_records:
            path = args.workspace / artifact["path"]
            if not path.is_file():
                run_errors.append(f"missing {artifact['path']}")
            elif sha256_file(path) != artifact["sha256"]:
                run_errors.append(f"hash mismatch {artifact['path']}")
        assignment_path = args.workspace / run["artifacts"]["shadow_assignment"]["path"]
        if assignment_path.is_file():
            assignment = np.load(assignment_path, allow_pickle=False)["assignment"]
            if assignment.shape[0] != run["shadow_models"]:
                run_errors.append("shadow assignment model count mismatch")
            if not np.all(assignment.sum(axis=0) == run["shadow_memberships_per_record"]):
                run_errors.append("per-record shadow membership count mismatch")
        raw_path = args.workspace / run["artifacts"]["raw_scores"]["path"]
        auc = None
        baseline_auc = None
        if raw_path.is_file():
            raw = pd.read_parquet(raw_path)
            if raw.groupby("group").size().to_dict() != run["group_counts"]:
                run_errors.append("raw group count mismatch")
            if not (raw.shadow_in_count == run["shadow_memberships_per_record"]).all():
                run_errors.append("raw in-shadow count mismatch")
            member = raw.group.eq("member_audit")
            nonmember = raw.group.eq("nonmember_audit")
            threshold = run["attack"]["threshold"]
            tp = int((raw.loc[member, "multi_shadow_lr_score"] >= threshold).sum())
            fp = int((raw.loc[nonmember, "multi_shadow_lr_score"] >= threshold).sum())
            if tp != run["attack"]["true_positives"] or fp != run["attack"]["false_positives"]:
                run_errors.append("raw TP/FP mismatch")
            audit = member | nonmember
            auc = float(roc_auc_score(raw.loc[audit, "is_member"], raw.loc[audit, "multi_shadow_lr_score"]))
            target_raw = pd.read_parquet(args.workspace / run["target_raw_scores"]["path"])
            target_audit = target_raw.group.str.endswith("audit")
            baseline_auc = float(roc_auc_score(target_raw.loc[target_audit, "is_member"], target_raw.loc[target_audit, "membership_score"]))
        if run_errors:
            errors.append({"dataset_id": run["dataset_id"], "errors": run_errors})
        attack = run["attack"]
        rows.append({
            "dataset_id": int(run["dataset_id"]), "dataset_name": run["dataset_name"],
            "audit_auc": auc, "reference_loss_auc": baseline_auc,
            "auc_change": auc - baseline_auc if auc is not None and baseline_auc is not None else None,
            "tp": attack["true_positives"], "fp": attack["false_positives"], "tn": attack["true_negatives"], "fn": attack["false_negatives"],
            "tpr": attack["tpr"], "fpr": attack["fpr"], "fpr_upper": attack["fpr_clopper_pearson_one_sided"][1],
            "tpr_lower": attack["tpr_clopper_pearson_one_sided"][0], "operating_point_attained": attack["operating_point_attained"],
            "certified_attack_floor": attack["certified_attack_floor"], "elapsed_seconds": run["elapsed_seconds"],
        })
    frame = pd.DataFrame(rows)
    positive = frame[frame.certified_attack_floor.fillna(0).gt(0)].sort_values("certified_attack_floor", ascending=False).to_dict(orient="records")
    result = {
        "analysis_status": "predeclared multi-shadow likelihood-ratio extension; not full augmented online LiRA",
        "validation": {"runs_checked": len(frame), "artifact_hashes_assignments_counts_and_scores_valid": not errors, "errors": errors},
        "design": {"datasets": int(frame.dataset_id.nunique()), "runs": len(frame), "shadow_models_per_run": int(source["records"][0]["shadow_models"]) if source["records"] else None, "target_fpr": 0.001, "confidence": 0.95},
        "outcomes": {
            "median_audit_auc": float(frame.audit_auc.median()),
            "median_reference_loss_auc": float(frame.reference_loss_auc.median()),
            "median_auc_change": float(frame.auc_change.median()),
            "runs_improving_auc": int(frame.auc_change.gt(0).sum()),
            "operating_point_attained": int(frame.operating_point_attained.sum()),
            "positive_certified_attack_floors": len(positive),
            "descriptive_tp": int(frame.tp.sum()), "descriptive_fp": int(frame.fp.sum()), "descriptive_tn": int(frame.tn.sum()), "descriptive_fn": int(frame.fn.sum()),
        },
        "positive_certified_floor_details": positive,
        "per_dataset": frame.to_dict(orient="records"),
        "interpretation": [
            "This is a materially stronger multi-shadow likelihood-ratio baseline than the single-reference loss attack.",
            "It is not the full augmented online LiRA protocol and therefore remains a lower-bound adversary.",
            "Only runs whose exact one-sided FPR upper bound is at most 0.1% support a low-FPR floor.",
            "Non-attainment remains inconclusive and cannot clear a model.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = [
        "# OpenML multi-shadow likelihood-ratio membership attack", "", "## Design", "",
        f"The tier attacked {len(frame)} sealed target releases using {result['design']['shadow_models_per_run']} shadow models per target. Every benchmark row appeared in exactly three shadow training sets and twelve shadow holdouts. Per-record Gaussian in/out distributions were fitted to true-class logit confidence, with predeclared variance shrinkage. Threshold calibration and final audit records remained disjoint.", "",
        "This is a LiRA-style multi-shadow likelihood-ratio baseline, not the complete augmented online LiRA protocol.", "", "## Results", "",
        f"- Median audit AUC was {result['outcomes']['median_audit_auc']:.3f}, versus {result['outcomes']['median_reference_loss_auc']:.3f} for the earlier single-reference attack; {result['outcomes']['runs_improving_auc']}/{len(frame)} releases improved.",
        f"- {result['outcomes']['operating_point_attained']}/{len(frame)} runs attained the exact 0.1% FPR point and {result['outcomes']['positive_certified_attack_floors']} produced a positive certified floor.",
        f"- Descriptive raw counts were TP={result['outcomes']['descriptive_tp']}, FP={result['outcomes']['descriptive_fp']}, TN={result['outcomes']['descriptive_tn']}, FN={result['outcomes']['descriptive_fn']}; these heterogeneous counts are not pooled for inference.", "",
    ]
    if positive:
        lines += ["| Dataset | TP | FP | TPR lower | FPR upper |", "|---|---:|---:|---:|---:|"]
        for row in positive:
            lines.append(f"| {row['dataset_name']} | {row['tp']} | {row['fp']} | {row['tpr_lower']:.3%} | {row['fpr_upper']:.3%} |")
        lines.append("")
    lines += ["## Determination", "", "Each positive floor is blocking evidence for the declared release and attacker. No run supplies an upper bound on optimal membership inference; DP accounting or another mechanism-level proof is required for clearance."]
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "outcomes": result["outcomes"]}, indent=2))


if __name__ == "__main__":
    main()
