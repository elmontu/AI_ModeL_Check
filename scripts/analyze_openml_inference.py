#!/usr/bin/env python3
"""Validate and aggregate attribute inference and partial reconstruction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bootstrap_interval(values: np.ndarray, confidence: float, seed: int, resamples: int = 20000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for start in range(0, resamples, 200):
        count = min(200, resamples - start)
        indices = rng.integers(0, len(values), size=(count, len(values)))
        means[start:start + count] = values[indices].mean(axis=1)
    alpha = 1.0 - confidence
    return float(np.quantile(means, alpha / 2.0)), float(np.quantile(means, 1.0 - alpha / 2.0))


def holm_rejections(pvalues: list[float], family_alpha: float) -> list[bool]:
    order = np.argsort(pvalues)
    rejected = [False] * len(pvalues)
    for rank, index in enumerate(order):
        if pvalues[index] <= family_alpha / (len(pvalues) - rank):
            rejected[index] = True
        else:
            break
    return rejected


def validate_artifacts(run: dict, workspace: Path) -> list[str]:
    errors = []
    for name, artifact in run["artifacts"].items():
        path = workspace / artifact["path"]
        if not path.is_file(): errors.append(f"missing {name}")
        elif sha256_file(path) != artifact["sha256"]: errors.append(f"hash mismatch {name}")
    structural = workspace / run["target_structural_manifest"]["path"]
    if not structural.is_file(): errors.append("missing target structural manifest")
    elif sha256_file(structural) != run["target_structural_manifest"]["sha256"]: errors.append("target structural manifest hash mismatch")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attribute-summary", type=Path, required=True); parser.add_argument("--reconstruction-summary", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd()); parser.add_argument("--output-attribute-json", type=Path, required=True); parser.add_argument("--output-attribute-md", type=Path, required=True)
    parser.add_argument("--output-reconstruction-json", type=Path, required=True); parser.add_argument("--output-reconstruction-md", type=Path, required=True)
    args = parser.parse_args()
    attribute_source = json.loads(args.attribute_summary.read_text()); reconstruction_source = json.loads(args.reconstruction_summary.read_text())
    attribute_errors, reconstruction_errors, attribute_rows, reconstruction_rows = [], [], [], []
    family_size = len(attribute_source["records"]); simultaneous_confidence = 1.0 - 0.05 / max(1, family_size)
    for position, run in enumerate(attribute_source["records"]):
        errors = validate_artifacts(run, args.workspace)
        raw_path = args.workspace / run["artifacts"]["raw_attribute"]["path"]
        raw = pd.read_parquet(raw_path) if raw_path.is_file() else pd.DataFrame()
        for stratum, reported in run["attribute_inference"]["strata"].items():
            group = raw[raw.stratum.eq(stratum)]
            baseline_correct = group.baseline_prediction.eq(group.true_attribute).to_numpy()
            combined_correct = group.combined_prediction.eq(group.true_attribute).to_numpy()
            if len(group) != reported["records"]: errors.append(f"{stratum} row count mismatch")
            if abs(baseline_correct.mean() - reported["baseline_accuracy"]) > 1e-12 or abs(combined_correct.mean() - reported["combined_accuracy"]) > 1e-12: errors.append(f"{stratum} accuracy mismatch")
            paired = combined_correct.astype(float) - baseline_correct.astype(float)
            combined_only = int(np.sum(~baseline_correct & combined_correct)); baseline_only = int(np.sum(baseline_correct & ~combined_correct)); discordant = combined_only + baseline_only
            pvalue = float(binomtest(combined_only, discordant, 0.5, alternative="greater").pvalue) if discordant else 1.0
            simultaneous_ci = bootstrap_interval(paired, simultaneous_confidence, 20270000 + position * 2 + (stratum == "nonmember_audit"))
            attribute_rows.append({"dataset_id": run["dataset_id"], "dataset_name": run["dataset_name"], "secret_feature": run["attribute_inference"]["secret_feature"], "secret_kind": run["attribute_inference"]["secret_kind"], "secret_classes": run["attribute_inference"]["secret_classes"], "stratum": stratum, "records": len(group), "prior_accuracy": reported["prior_accuracy"], "baseline_accuracy": reported["baseline_accuracy"], "combined_accuracy": reported["combined_accuracy"], "incremental_accuracy": reported["incremental_accuracy"], "simultaneous_bootstrap_interval": list(simultaneous_ci), "mcnemar_p": pvalue, "combined_only_correct": combined_only, "baseline_only_correct": baseline_only})
        if errors: attribute_errors.append({"dataset_id": run["dataset_id"], "errors": errors})
    member_attribute = [row for row in attribute_rows if row["stratum"] == "member_audit"]
    rejected = holm_rejections([row["mcnemar_p"] for row in member_attribute], 0.05)
    for row, decision in zip(member_attribute, rejected, strict=True): row["holm_familywise_rejects_no_improvement"] = decision
    attribute_result = {
        "analysis_unit": "dataset and audit stratum; protected secret is the declared exact or derived feature",
        "validation": {"runs_checked": family_size, "artifact_hashes_raw_counts_and_metrics_valid": not attribute_errors, "errors": attribute_errors},
        "design": {"datasets": family_size, "familywise_alpha": 0.05, "holm_mcnemar_family": family_size, "simultaneous_bootstrap_confidence_per_dataset": simultaneous_confidence},
        "member_outcomes": {"median_prior_accuracy": float(np.median([r["prior_accuracy"] for r in member_attribute])), "median_baseline_accuracy": float(np.median([r["baseline_accuracy"] for r in member_attribute])), "median_combined_accuracy": float(np.median([r["combined_accuracy"] for r in member_attribute])), "median_incremental_accuracy": float(np.median([r["incremental_accuracy"] for r in member_attribute])), "datasets_positive_simultaneous_effect_lower_bound": int(sum(r["simultaneous_bootstrap_interval"][0] > 0 for r in member_attribute)), "datasets_holm_significant": int(sum(rejected))},
        "per_dataset_stratum": attribute_rows,
        "interpretation": ["The no-model baseline receives the same auxiliary records, candidate-known fields, labels, and exact summaries.", "Only the target-model response curve differs between baseline and combined attacks.", "A positive incremental effect is model-enabled attribute leakage for this declared game; a null effect does not prove absence of other attribute attacks.", "Quantile-band secrets are derived attributes and must not be reported as exact raw-value recovery."],
    }

    for position, run in enumerate(reconstruction_source["records"]):
        errors = validate_artifacts(run, args.workspace)
        raw_path = args.workspace / run["artifacts"]["raw_reconstruction"]["path"]
        raw = pd.read_parquet(raw_path) if raw_path.is_file() else pd.DataFrame()
        scale = run["reconstruction"]["scale_iqr_or_sd"]
        categorical = run["reconstruction"]["secret_kind"] == "exact_categorical_feature"
        for stratum, reported in run["reconstruction"]["strata"].items():
            group = raw[raw.stratum.eq(stratum)]
            improvement = (group.baseline_absolute_error - group.combined_absolute_error).to_numpy() / scale
            if len(group) != reported["records"]: errors.append(f"{stratum} row count mismatch")
            if categorical:
                if abs(1.0 - group.baseline_absolute_error.mean() - reported["baseline_accuracy"]) > 1e-8: errors.append(f"{stratum} baseline categorical accuracy mismatch")
            elif abs(group.baseline_absolute_error.mean() / scale - reported["baseline_normalized_mae"]) > 1e-8: errors.append(f"{stratum} baseline error mismatch")
            simultaneous_ci = bootstrap_interval(improvement, simultaneous_confidence, 20280000 + position * 2 + (stratum == "nonmember_audit"))
            reconstruction_rows.append({"dataset_id": run["dataset_id"], "dataset_name": run["dataset_name"], "secret_feature": run["reconstruction"]["secret_feature"], "secret_kind": run["reconstruction"]["secret_kind"], "stratum": stratum, "records": len(group), "metric": "zero_one_accuracy" if categorical else "normalized_absolute_error", "baseline_loss": float(group.baseline_absolute_error.mean() / scale), "combined_loss": float(group.combined_absolute_error.mean() / scale), "loss_reduction": float(improvement.mean()), "simultaneous_bootstrap_interval": list(simultaneous_ci), "baseline_accuracy": reported.get("baseline_accuracy"), "combined_accuracy": reported.get("combined_accuracy"), "baseline_within_0p1_iqr": reported.get("baseline_within_0p1_iqr"), "combined_within_0p1_iqr": reported.get("combined_within_0p1_iqr")})
        if errors: reconstruction_errors.append({"dataset_id": run["dataset_id"], "errors": errors})
    member_reconstruction = [row for row in reconstruction_rows if row["stratum"] == "member_audit"]
    reconstruction_result = {
        "analysis_unit": "dataset and audit stratum; one numeric secret feature reconstructed under normalized absolute error",
        "claim_boundary": "partial one-feature numeric or categorical reconstruction, not full-row or training-set reconstruction",
        "validation": {"runs_checked": len(reconstruction_source["records"]), "artifact_hashes_raw_counts_and_metrics_valid": not reconstruction_errors, "errors": reconstruction_errors},
        "design": {"datasets": len(reconstruction_source["records"]), "familywise_alpha": 0.05, "simultaneous_bootstrap_confidence_per_dataset": simultaneous_confidence},
        "member_outcomes": {"numeric_datasets": int(sum(r["secret_kind"] == "one_numeric_feature" for r in member_reconstruction)), "categorical_datasets": int(sum(r["secret_kind"] == "exact_categorical_feature" for r in member_reconstruction)), "median_baseline_normalized_loss": float(np.median([r["baseline_loss"] for r in member_reconstruction])), "median_combined_normalized_loss": float(np.median([r["combined_loss"] for r in member_reconstruction])), "median_normalized_loss_reduction": float(np.median([r["loss_reduction"] for r in member_reconstruction])), "datasets_positive_simultaneous_improvement_lower_bound": int(sum(r["simultaneous_bootstrap_interval"][0] > 0 for r in member_reconstruction))},
        "per_dataset_stratum": reconstruction_rows,
        "interpretation": ["Ground truth is compared directly with reconstructed values; model consistency alone is not counted as success.", "The baseline uses the same known fields, task label, auxiliary records, and exact target-training summary grid.", "This evaluates one-feature numerical reconstruction and does not establish full-record reconstruction risk.", "A null result is attack-specific and cannot clear reconstruction as a threat."],
    }
    for path, result in [(args.output_attribute_json, attribute_result), (args.output_reconstruction_json, reconstruction_result)]:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    a = attribute_result["member_outcomes"]
    args.output_attribute_md.write_text("\n".join(["# OpenML controlled attribute-inference results", "", "## Design", "", f"The tier evaluated {family_size} sealed tree releases. For each dataset, an exact low-cardinality feature or explicitly labelled four-quantile derived attribute was hidden. A no-model attacker and a model-enhanced attacker used the same disjoint auxiliary records, remaining candidate fields, task label, and exact summaries; only the model response curve was added to the combined attack. Target-training members and nonmembers were audited separately.", "", "## Member-audit results", "", f"- Median prior, no-model baseline, and combined accuracies were {a['median_prior_accuracy']:.3f}, {a['median_baseline_accuracy']:.3f}, and {a['median_combined_accuracy']:.3f}.", f"- Median model-enabled accuracy change was {a['median_incremental_accuracy']:+.3f}.", f"- {a['datasets_positive_simultaneous_effect_lower_bound']}/{family_size} datasets had a positive Bonferroni-simultaneous bootstrap lower bound; {a['datasets_holm_significant']}/{family_size} rejected no improvement by exact one-sided McNemar tests with Holm control.", "", "## Determination", "", "Positive controlled gaps are lower-bound evidence of model-enabled attribute leakage in the declared game. Exact-value and quantile-band secrets are reported separately. Failure of this fixed attacker remains inconclusive."]) + "\n")
    r = reconstruction_result["member_outcomes"]
    args.output_reconstruction_md.write_text("\n".join(["# OpenML partial reconstruction results", "", "## Design", "", f"The tier reconstructed one feature for target-training members in {len(member_reconstruction)} datasets and repeated the evaluation on nonmembers. {r['numeric_datasets']} secrets were numeric and scored by IQR-or-SD normalized absolute error; {r['categorical_datasets']} categorical fallbacks were scored by zero-one error. The no-model and model-enhanced attacks used identical auxiliary knowledge; only the target-model response curve was added. Every prediction was compared with ground truth.", "", "## Member-audit results", "", f"- Median baseline normalized loss was {r['median_baseline_normalized_loss']:.3f}; median combined normalized loss was {r['median_combined_normalized_loss']:.3f}.", f"- Median normalized loss reduction was {r['median_normalized_loss_reduction']:+.3f}.", f"- {r['datasets_positive_simultaneous_improvement_lower_bound']}/{len(member_reconstruction)} datasets had a positive Bonferroni-simultaneous bootstrap lower bound.", "", "## Determination", "", "This is ground-truth-scored one-feature reconstruction, not full-row reconstruction. Numeric and categorical losses are not interpreted as interchangeable effect sizes; the pooled median is descriptive only. Positive controlled improvements block the declared threat; null results do not establish a reconstruction ceiling."]) + "\n")
    print(json.dumps({"attribute_validation": attribute_result["validation"], "attribute_member_outcomes": a, "reconstruction_validation": reconstruction_result["validation"], "reconstruction_member_outcomes": r}, indent=2))


if __name__ == "__main__": main()
