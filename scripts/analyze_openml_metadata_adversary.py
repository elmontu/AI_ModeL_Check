#!/usr/bin/env python3
"""Validate and aggregate the summary-informed adversary sensitivity tier."""

from __future__ import annotations

import argparse
import gzip
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


def validate_run(run: dict, workspace: Path) -> tuple[list[str], dict[str, float]]:
    errors: list[str] = []
    for artifact_name, artifact in run["artifacts"].items():
        path = workspace / artifact["path"]
        if not path.is_file():
            errors.append(f"missing {artifact_name}: {artifact['path']}")
        elif sha256_file(path) != artifact["sha256"]:
            errors.append(f"hash mismatch for {artifact_name}: {artifact['path']}")
    required_numeric = {
        "minimum",
        "maximum",
        "range",
        "mean",
        "median",
        "standard_deviation",
        "variance",
        "first_quartile",
        "third_quartile",
        "interquartile_range",
        "median_absolute_deviation",
    }
    for name in ("full_source_metadata", "target_training_metadata"):
        path = workspace / run["artifacts"][name]["path"]
        if not path.is_file():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            metadata = json.load(handle)
        for feature, values in metadata["numeric_features"].items():
            missing = required_numeric - set(values)
            if missing:
                errors.append(f"{name} numeric feature {feature} missing {sorted(missing)}")
        for feature, values in metadata["categorical_features"].items():
            if "category_counts" not in values or "category_frequencies" not in values:
                errors.append(f"{name} categorical feature {feature} lacks full frequencies")
    raw_path = workspace / run["artifacts"]["raw_scores"]["path"]
    aucs: dict[str, float] = {}
    if raw_path.is_file():
        raw = pd.read_parquet(raw_path)
        expected_groups = run["group_counts"]
        observed_groups = raw.groupby("group").size().to_dict()
        if observed_groups != expected_groups:
            errors.append(f"raw score groups {observed_groups} != expected {expected_groups}")
        if raw.row_id.duplicated().any():
            errors.append("raw score row IDs are not unique")
        audit = raw.group.str.endswith("audit")
        y = raw.loc[audit, "is_member"].astype(int)
        for name, column in {
            "metadata_only": "metadata_only_score",
            "combined_model_metadata": "combined_model_metadata_score",
            "model_only": "model_membership_score",
        }.items():
            aucs[name] = float(roc_auc_score(y, raw.loc[audit, column]))
        for attack_name, attack in run["attacks"].items():
            score_column = attack["score_column"]
            audit_member = raw.group.eq("member_audit")
            audit_nonmember = raw.group.eq("nonmember_audit")
            tp = int((raw.loc[audit_member, score_column] >= attack["threshold"]).sum())
            fp = int((raw.loc[audit_nonmember, score_column] >= attack["threshold"]).sum())
            if tp != attack["true_positives"] or fp != attack["false_positives"]:
                errors.append(f"{attack_name} raw scores do not reproduce TP/FP")
    return errors, aucs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.summary.read_text())
    validation_errors = []
    rows = []
    for run in source["records"]:
        errors, aucs = validate_run(run, args.workspace)
        if errors:
            validation_errors.append({
                "dataset_id": run["dataset_id"],
                "capacity": run["capacity"],
                "errors": errors,
            })
        for attack_name, attack in run["attacks"].items():
            rows.append({
                "dataset_id": run["dataset_id"],
                "dataset_name": run["dataset_name"],
                "n_estimators": run["capacity"]["n_estimators"],
                "max_depth": run["capacity"]["max_depth"],
                "attack_name": attack_name,
                "tp": attack["true_positives"],
                "fp": attack["false_positives"],
                "tn": attack["true_negatives"],
                "fn": attack["false_negatives"],
                "tpr": attack["tpr"],
                "fpr": attack["fpr"],
                "raw_advantage": attack["tpr"] - attack["fpr"],
                "member_audit_n": attack["true_positives"] + attack["false_negatives"],
                "nonmember_audit_n": attack["false_positives"] + attack["true_negatives"],
                "calibration_false_positives": attack["calibration_false_positives"],
                "confidence": attack["confidence"],
                "tpr_lower": attack["tpr_clopper_pearson_one_sided"][0],
                "tpr_upper": attack["tpr_clopper_pearson_one_sided"][1],
                "fpr_lower": attack["fpr_clopper_pearson_one_sided"][0],
                "fpr_upper": attack["fpr_clopper_pearson_one_sided"][1],
                "operating_point_attained": attack["operating_point_attained"],
                "certified_attack_floor": attack["certified_attack_floor"],
                "audit_auc": aucs.get(attack_name),
                "model_only_audit_auc": aucs.get("model_only"),
            })
    frame = pd.DataFrame(rows)
    metadata = frame[frame.attack_name.eq("metadata_only")].set_index(
        ["dataset_id", "n_estimators", "max_depth"]
    )
    combined = frame[frame.attack_name.eq("combined_model_metadata")].set_index(
        ["dataset_id", "n_estimators", "max_depth"]
    )
    comparison = combined[["dataset_name", "audit_auc", "model_only_audit_auc", "raw_advantage"]].copy()
    comparison = comparison.rename(columns={
        "audit_auc": "combined_auc",
        "raw_advantage": "combined_raw_advantage",
    })
    comparison["metadata_only_auc"] = metadata.audit_auc
    comparison["metadata_only_raw_advantage"] = metadata.raw_advantage
    comparison["combined_minus_metadata_auc"] = comparison.combined_auc - comparison.metadata_only_auc
    comparison["combined_minus_model_auc"] = comparison.combined_auc - comparison.model_only_audit_auc
    comparison = comparison.reset_index()
    strongest = comparison.nlargest(10, "combined_minus_metadata_auc").to_dict(orient="records")
    positive_floors = (
        frame[frame.certified_attack_floor.fillna(0.0).gt(0)]
        .sort_values(["attack_name", "certified_attack_floor"], ascending=[True, False])
        [[
            "dataset_id",
            "dataset_name",
            "n_estimators",
            "max_depth",
            "attack_name",
            "member_audit_n",
            "nonmember_audit_n",
            "tp",
            "fp",
            "tn",
            "fn",
            "tpr",
            "fpr",
            "confidence",
            "tpr_lower",
            "tpr_upper",
            "fpr_lower",
            "fpr_upper",
            "certified_attack_floor",
            "calibration_false_positives",
        ]]
        .to_dict(orient="records")
    )
    outcomes = {}
    for attack_name, group in frame.groupby("attack_name"):
        outcomes[attack_name] = {
            "runs": len(group),
            "operating_point_attained": int(group.operating_point_attained.sum()),
            "positive_certified_floors": int(
                (group.certified_attack_floor.fillna(0.0) > 0).sum()
            ),
            "runs_with_nonzero_tp": int((group.tp > 0).sum()),
            "maximum_raw_advantage": float(group.raw_advantage.max()),
            "median_audit_auc": float(group.audit_auc.median()),
            "descriptive_total_tp": int(group.tp.sum()),
            "descriptive_total_fp": int(group.fp.sum()),
            "descriptive_total_tn": int(group.tn.sum()),
            "descriptive_total_fn": int(group.fn.sum()),
        }
    result = {
        "analysis_status": "post-hoc adversary sensitivity; not a pre-registered confirmatory tier",
        "analysis_unit": "dataset-capacity release; repeated capacities within a dataset are dependent",
        "adversary_assumption": source["records"][0]["adversary_knowledge"],
        "validation": {
            "runs_checked": len(source["records"]),
            "artifact_hashes_metadata_fields_counts_and_scores_valid": not validation_errors,
            "errors": validation_errors,
        },
        "design": {
            "datasets": int(frame.dataset_id.nunique()),
            "capacities": int(frame[["n_estimators", "max_depth"]].drop_duplicates().shape[0]),
            "release_runs": int(len(source["records"])),
            "attack_evaluations": len(frame),
            "new_attack_family_size": 2,
            "familywise_confidence": 0.95,
            "per_attack_bonferroni_confidence": float(
                source["records"][0]["attacks"]["metadata_only"]["confidence"]
            ),
            "target_fpr": float(source["records"][0]["attacks"]["metadata_only"]["target_fpr"]),
        },
        "outcomes": outcomes,
        "positive_certified_floor_details": positive_floors,
        "comparison": {
            "combined_auc_above_metadata_only_runs": int(
                (comparison.combined_minus_metadata_auc > 0).sum()
            ),
            "combined_auc_above_model_only_runs": int(
                (comparison.combined_minus_model_auc > 0).sum()
            ),
            "median_combined_minus_metadata_auc": float(
                comparison.combined_minus_metadata_auc.median()
            ),
            "median_combined_minus_model_auc": float(comparison.combined_minus_model_auc.median()),
            "maximum_combined_minus_metadata_auc": float(
                comparison.combined_minus_metadata_auc.max()
            ),
        },
        "strongest_combined_over_metadata_auc": strongest,
        "interpretation": [
            "Exact training summaries are auxiliary leakage and are provided to both the metadata-only baseline and combined attacker.",
            "The combined attack is a lower-bound adversary, not an upper bound on an optimal summary-informed adversary.",
            "AUC differences and raw advantages are exploratory; they do not establish a low-FPR security statement.",
            "Summary metadata does not create a candidate roster or target signal for person-level linkage.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    meta_outcome = outcomes["metadata_only"]
    combined_outcome = outcomes["combined_model_metadata"]
    comp = result["comparison"]
    top = strongest[0]
    lines = [
        "# Exact-metadata adversary sensitivity",
        "",
        "## Threat assumption",
        "",
        "The adversary is assumed to know the candidate record and label, the complete feature schema, full-source database summaries, exact target-training database summaries, and the released model surface. Numeric metadata includes minimum, maximum, range, mean, median, standard deviation, variance, quartiles/IQR, median absolute deviation, missingness, and cardinality. Categorical and target metadata includes exact counts and frequencies.",
        "",
        "This is stronger than ordinary public dataset documentation. The metadata-only attacker receives the same summaries and is the no-model baseline. Exact summaries are not treated as an external row roster.",
        "",
        "## Design",
        "",
        f"The post-hoc sensitivity tier evaluated two new attacks for {result['design']['release_runs']} sealed dataset-capacity releases ({result['design']['attack_evaluations']} attack evaluations): a metadata-only logistic attacker and a combined model-plus-metadata attacker. Both were trained on the existing calibration groups and evaluated on the untouched audit groups. Exact one-sided intervals use {result['design']['per_attack_bonferroni_confidence']:.1%} confidence per attack, giving 95% familywise confidence across the two new attacks for one release.",
        "",
        "Because this adversary was added after the baseline results were inspected, all cross-corpus comparisons are explicitly exploratory.",
        "",
        "## Results",
        "",
        f"- Metadata-only: {meta_outcome['operating_point_attained']}/96 attained the 0.1% FPR point; {meta_outcome['positive_certified_floors']} had a positive certified floor; median audit AUC {meta_outcome['median_audit_auc']:.3f}; maximum raw advantage {meta_outcome['maximum_raw_advantage']:.3%}.",
        f"- Combined model plus metadata: {combined_outcome['operating_point_attained']}/96 attained the FPR point; {combined_outcome['positive_certified_floors']} had a positive certified floor; median audit AUC {combined_outcome['median_audit_auc']:.3f}; maximum raw advantage {combined_outcome['maximum_raw_advantage']:.3%}.",
        f"- Combined AUC exceeded metadata-only AUC in {comp['combined_auc_above_metadata_only_runs']}/96 releases and model-only AUC in {comp['combined_auc_above_model_only_runs']}/96. Median changes were {comp['median_combined_minus_metadata_auc']:+.3f} and {comp['median_combined_minus_model_auc']:+.3f}, respectively.",
        f"- The largest combined-over-metadata AUC increase was {top['dataset_name']} at {top['n_estimators']} trees/depth {top['max_depth']}: {top['combined_minus_metadata_auc']:+.3f}.",
        "",
        "### Certified low-FPR floors",
        "",
        "| Dataset/release | Audit counts | Exact one-sided 97.5% bounds | Determination |",
        "|---|---:|---:|---|",
    ]
    for floor in positive_floors:
        lines.append(
            f"| {floor['dataset_name']} ({floor['n_estimators']} trees, depth {floor['max_depth']}) "
            f"| TP={floor['tp']}/{floor['member_audit_n']}; FP={floor['fp']}/{floor['nonmember_audit_n']} "
            f"| TPR lower {floor['tpr_lower']:.3%}; FPR upper {floor['fpr_upper']:.3%} "
            f"| Positive attack floor {floor['certified_attack_floor']:.3%} |"
        )
    lines += [
        "",
        "These are blocking lower-bound findings for the declared post-hoc attacker. They are not upper bounds on the optimal adversary and do not certify any release as safe.",
        "",
        "## Determination",
        "",
        "The framework must bind these summaries into auxiliary knowledge for every threat and give them to the no-release baseline. The combined attacker is stronger empirical evidence when it improves audit performance, but it remains a lower bound. Failure to attain the low-FPR point cannot clear a release. Exact summary knowledge alone does not make the structural OpenML roster recipient-realizable and does not convert record-level results into person, company, or population identification.",
    ]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "outcomes": outcomes, "comparison": comp}, indent=2))


if __name__ == "__main__":
    main()
