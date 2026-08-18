#!/usr/bin/env python3
"""Independently replay and aggregate the sealed DP-SGD ledgers."""

from __future__ import annotations

import argparse
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


def replay_rdp(order: int, q: float, sigma: float) -> float:
    values = []
    for j in range(order + 1):
        if q == 1.0 and j != order:
            continue
        log_binomial = math.lgamma(order + 1) - math.lgamma(j + 1) - math.lgamma(order - j + 1)
        log_weight = (j * math.log(q) if j else 0.0)
        if order - j:
            log_weight += (order - j) * math.log1p(-q)
        values.append(log_binomial + log_weight + j * (j - 1) / (2.0 * sigma * sigma))
    accumulator = values[0]
    for item in values[1:]:
        accumulator = float(np.logaddexp(accumulator, item))
    return accumulator / (order - 1)


def replay_ledger(ledger: dict) -> tuple[float, int, dict[str, float]]:
    results = {}
    for order in ledger["orders"]:
        rdp = ledger["steps"] * replay_rdp(int(order), ledger["sample_rate"], ledger["noise_multiplier"])
        results[str(order)] = rdp + math.log(1.0 / ledger["delta"]) / (int(order) - 1)
    best_order = min(results, key=results.get)
    return float(results[best_order]), int(best_order), results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--non-private-summary", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.summary.read_text())
    non_private_source = json.loads(args.non_private_summary.read_text())
    non_private = {
        (int(item["dataset_id"]), int(item["seed"])): item["utility"]
        for item in non_private_source["records"]
    }
    errors, rows = [], []
    for run in source["records"]:
        run_errors = []
        for artifact_name, artifact in run["artifacts"].items():
            path = args.workspace / artifact["path"]
            if not path.is_file():
                run_errors.append(f"missing {artifact_name}")
            elif sha256_file(path) != artifact["sha256"]:
                run_errors.append(f"hash mismatch {artifact_name}")
        for side in ("target", "reference"):
            ledger = run[f"{side}_accountant"]
            epsilon, order, by_order = replay_ledger(ledger)
            if abs(epsilon - ledger["epsilon_computed"]) > 1e-9:
                run_errors.append(f"{side} epsilon replay mismatch")
            if order != ledger["optimal_integer_order"]:
                run_errors.append(f"{side} optimal order replay mismatch")
            if epsilon > ledger["epsilon_target"] + 1e-9:
                run_errors.append(f"{side} epsilon exceeds target")
            if any(abs(by_order[key] - ledger["epsilon_by_integer_order"][key]) > 1e-9 for key in by_order):
                run_errors.append(f"{side} per-order replay mismatch")
        raw_path = args.workspace / run["artifacts"]["raw_scores"]["path"]
        if raw_path.is_file():
            raw = pd.read_parquet(raw_path)
            expected_groups = run["group_counts"]
            if raw.groupby("group").size().to_dict() != expected_groups:
                run_errors.append("raw score group mismatch")
            score = raw.membership_score.to_numpy()
            audit_member = raw.group.eq("member_audit").to_numpy()
            audit_nonmember = raw.group.eq("nonmember_audit").to_numpy()
            threshold = run["attack"]["threshold"]
            if int(np.sum(score[audit_member] >= threshold)) != run["attack"]["true_positives"]:
                run_errors.append("raw TP mismatch")
            if int(np.sum(score[audit_nonmember] >= threshold)) != run["attack"]["false_positives"]:
                run_errors.append("raw FP mismatch")
        if run_errors:
            errors.append({"dataset_id": run["dataset_id"], "seed": run["seed"], "epsilon_target": run["epsilon_target"], "errors": run_errors})
        baseline = run["matched_non_private_utility"]
        epsilon_replayed, _, _ = replay_ledger(run["target_accountant"])
        target_fpr = float(run["attack"]["target_fpr"])
        delta = float(run["target_accountant"]["delta"])
        replayed_roc_ceiling = min(
            1.0,
            math.exp(epsilon_replayed) * target_fpr + delta,
            1.0 - math.exp(-epsilon_replayed) * (1.0 - target_fpr - delta),
        )
        if abs(replayed_roc_ceiling - run["dp_membership_roc_ceiling_at_target_fpr"]) > 1e-9:
            run_errors.append("DP membership ROC ceiling replay mismatch")
        rows.append({
            "dataset_id": int(run["dataset_id"]),
            "dataset_name": run["dataset_name"],
            "seed": int(run["seed"]),
            "epsilon_target": float(run["epsilon_target"]),
            "epsilon_replayed": float(run["target_accountant"]["epsilon_computed"]),
            "delta": float(run["target_accountant"]["delta"]),
            "noise_multiplier": float(run["target_accountant"]["noise_multiplier"]),
            "optimal_order": int(run["target_accountant"]["optimal_integer_order"]),
            "balanced_accuracy": float(run["utility"]["balanced_accuracy"]),
            "non_private_balanced_accuracy": baseline.get("balanced_accuracy"),
            "balanced_accuracy_change": float(run["utility"]["balanced_accuracy"]) - float(baseline["balanced_accuracy"]),
            "roc_ceiling": replayed_roc_ceiling,
            "tp": int(run["attack"]["true_positives"]),
            "fp": int(run["attack"]["false_positives"]),
            "tn": int(run["attack"]["true_negatives"]),
            "fn": int(run["attack"]["false_negatives"]),
            "tpr": float(run["attack"]["tpr"]),
            "fpr": float(run["attack"]["fpr"]),
            "operating_point_attained": bool(run["attack"]["operating_point_attained"]),
            "certified_attack_floor": run["attack"]["certified_attack_floor"],
        })
    frame = pd.DataFrame(rows)
    by_epsilon = []
    for epsilon, group in frame.groupby("epsilon_target"):
        by_epsilon.append({
            "epsilon_target": float(epsilon),
            "runs": len(group),
            "datasets": int(group.dataset_id.nunique()),
            "median_balanced_accuracy": float(group.balanced_accuracy.median()),
            "median_non_private_balanced_accuracy": float(group.non_private_balanced_accuracy.median()),
            "median_balanced_accuracy_change": float(group.balanced_accuracy_change.median()),
            "minimum_noise_multiplier": float(group.noise_multiplier.min()),
            "maximum_noise_multiplier": float(group.noise_multiplier.max()),
            "minimum_delta": float(group.delta.min()),
            "maximum_delta": float(group.delta.max()),
            "maximum_membership_roc_ceiling_at_0p1pct_fpr": float(group.roc_ceiling.max()),
            "operating_point_attained": int(group.operating_point_attained.sum()),
            "positive_attack_floors": int(
                pd.to_numeric(group.certified_attack_floor, errors="coerce").gt(0).sum()
            ),
            "descriptive_tp": int(group.tp.sum()),
            "descriptive_fp": int(group.fp.sum()),
            "descriptive_tn": int(group.tn.sum()),
            "descriptive_fn": int(group.fn.sum()),
        })
    result = {
        "analysis_unit": "dataset-seed-epsilon DP training mechanism",
        "validation": {"runs_checked": len(frame), "artifact_hashes_counts_and_independent_accountant_replay_valid": not errors, "errors": errors},
        "design": {"datasets": int(frame.dataset_id.nunique()), "seeds": sorted(frame.seed.unique().tolist()), "epsilon_targets": sorted(frame.epsilon_target.unique().tolist()), "runs": len(frame), "adjacency": "add/remove one record", "sampling": "independent Poisson"},
        "by_epsilon": by_epsilon,
        "interpretation": [
            "The replayed DP ceiling is mechanism-level upper-bound evidence, unlike an attack result.",
            "The guarantee is conditional on the benchmark's fixed public preprocessing; a data-dependent production preprocessor must itself be private or included in composition.",
            "Exact database summaries newly released from the confidential training data are a separate mechanism and are not covered by this model-only ledger.",
            "OpenML utility changes do not establish utility for a government deployment population.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = [
        "# OpenML DP-SGD and accountant replay",
        "",
        "## Design",
        "",
        f"The tier trained {len(frame)} shallow ReLU MLP target/reference pairs over {frame.dataset_id.nunique()} frozen datasets, {frame.seed.nunique()} seeds, and {frame.epsilon_target.nunique()} privacy budgets. Each update used independent Poisson sampling, per-example L2 clipping, and Gaussian noise. Delta was 1/n^2 for the actual training size. A separate program recomputed every integer-order RDP log moment from each sealed ledger.",
        "",
        "The guarantee conditions on fixed public benchmark preprocessing. It does not cover a newly disclosed non-private training summary or a data-dependent production preprocessor.",
        "",
        "## Results",
        "",
        "| epsilon target | runs | median balanced accuracy | non-private median | median change | noise range | delta range | max DP TPR ceiling at 0.1% FPR |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in by_epsilon:
        lines.append(f"| {row['epsilon_target']:.1f} | {row['runs']} | {row['median_balanced_accuracy']:.3f} | {row['median_non_private_balanced_accuracy']:.3f} | {row['median_balanced_accuracy_change']:+.3f} | {row['minimum_noise_multiplier']:.3f}-{row['maximum_noise_multiplier']:.3f} | {row['minimum_delta']:.2e}-{row['maximum_delta']:.2e} | {row['maximum_membership_roc_ceiling_at_0p1pct_fpr']:.3%} |")
    lines += [
        "",
        "## Determination",
        "",
        "All validated ledgers provide formal record-level membership ROC ceilings for the declared model-training mechanism. An empirical attack can block a release by finding a positive floor, but failure of an attack cannot improve the DP ceiling. A production adopter must replay the accountant, bind the sampling and clipping ledger, and compose preprocessing and metadata releases when those depend on confidential records.",
    ]
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "by_epsilon": by_epsilon}, indent=2))


if __name__ == "__main__":
    main()
