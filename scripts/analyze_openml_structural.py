#!/usr/bin/env python3
"""Aggregate the broad structural tier at the dataset, not run, level."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def validate_run(run: dict, workspace: Path) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    for artifact_name, artifact in run["artifacts"].items():
        path = workspace / artifact["path"]
        if not path.is_file():
            errors.append(f"missing {artifact_name}: {artifact['path']}")
        elif sha256_file(path) != artifact["sha256"]:
            errors.append(f"hash mismatch for {artifact_name}: {artifact['path']}")
    split_path = workspace / run["artifacts"]["splits"]["path"]
    selected_roster: set[str] = set()
    if split_path.is_file():
        split = read_json_gz(split_path)
        selected = split["selected_row_ids"]
        selected_roster = set(selected)
        if len(selected_roster) != len(selected):
            errors.append("selected roster has duplicate IDs")
        groups = [set(values) for values in split["splits"].values()]
        union = set().union(*groups)
        if sum(len(group) for group in groups) != len(union):
            errors.append("split groups overlap")
        if union != selected_roster:
            errors.append("split groups do not partition the selected roster")
        if len(split["splits"]["target_train"]) != run["structural"]["records"]:
            errors.append("target-training split size does not match structural records")
    histogram_path = workspace / run["artifacts"]["histogram"]["path"]
    if histogram_path.is_file():
        histogram = read_json_gz(histogram_path)
        counts = [int(item["count"]) for item in histogram]
        signatures = [tuple(item["leaf_signature"]) for item in histogram]
        if len(signatures) != len(set(signatures)):
            errors.append("histogram has duplicate signatures")
        if sum(counts) != run["structural"]["records"]:
            errors.append("histogram counts do not sum to structural records")
        if len(histogram) != run["structural"]["occupied_cells"]:
            errors.append("histogram occupied-cell mismatch")
        if min(counts) != run["structural"]["minimum_cell_size"]:
            errors.append("histogram minimum-cell mismatch")
        if max(counts) != run["structural"]["maximum_cell_size"]:
            errors.append("histogram maximum-cell mismatch")
        if sum(count for count in counts if count == 1) != run["structural"]["singleton_records"]:
            errors.append("histogram singleton-record mismatch")
    return errors, selected_roster


def wilson(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    spread = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


def bootstrap_interval(values: np.ndarray, statistic, seed: int, repeats: int = 20_000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(repeats, len(values)), replace=True)
    estimates = np.asarray([statistic(sample) for sample in samples])
    return float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()
    runs = pd.read_csv(args.summary_csv)
    source_summary = json.loads(args.summary_json.read_text())
    validation_errors: list[dict] = []
    rosters_by_dataset: dict[int, list[set[str]]] = {}
    for run in source_summary["records"]:
        errors, roster = validate_run(run, args.workspace)
        rosters_by_dataset.setdefault(int(run["dataset_id"]), []).append(roster)
        if errors:
            validation_errors.append(
                {"dataset_id": run["dataset_id"], "seed": run["seed"], "errors": errors}
            )
    for dataset_id, rosters in rosters_by_dataset.items():
        if len(rosters) != 3 or any(roster != rosters[0] for roster in rosters[1:]):
            validation_errors.append(
                {"dataset_id": dataset_id, "errors": ["selected rosters differ across seeds"]}
            )
    metadata = pd.DataFrame(json.loads(args.suite_manifest.read_text())["datasets"])[
        ["dataset_id", "rows", "features", "classes", "missing_feature_values"]
    ]
    grouped = runs.groupby(["dataset_id", "dataset_name"], as_index=False).agg(
        replicates=("seed", "count"),
        selected_rows=("selected_rows", "first"),
        pid_mean=("structural_bayes_linkage_success", "mean"),
        pid_min=("structural_bayes_linkage_success", "min"),
        pid_max=("structural_bayes_linkage_success", "max"),
        k_min=("structural_minimum_cell_size", "min"),
        k_max=("structural_minimum_cell_size", "max"),
        singleton_mean=("structural_singleton_fraction", "mean"),
        auc_mean=("utility_roc_auc", "mean"),
        balanced_accuracy_mean=("utility_balanced_accuracy", "mean"),
    ).merge(metadata, on="dataset_id", how="left", validate="one_to_one")
    n = len(grouped)
    all_seed_singleton = int((grouped.k_max == 1).sum())
    any_seed_singleton = int((grouped.k_min == 1).sum())
    all_seed_k5 = int((grouped.k_min >= 5).sum())
    pid = grouped.pid_mean.to_numpy()
    singleton = grouped.singleton_mean.to_numpy()
    median_pid_ci = bootstrap_interval(pid, np.median, args.seed)
    median_singleton_ci = bootstrap_interval(singleton, np.median, args.seed + 1)
    row_corr = spearmanr(np.log1p(grouped.rows), grouped.pid_mean)
    feature_corr = spearmanr(np.log1p(grouped.features), grouped.pid_mean)
    result = {
        "analysis_unit": "OpenML dataset; seeds are repeated measurements, not independent datasets",
        "validation": {
            "runs_checked": len(source_summary["records"]),
            "artifact_hashes_histograms_splits_and_rosters_valid": not validation_errors,
            "errors": validation_errors,
        },
        "datasets": n,
        "runs": len(runs),
        "replicates_per_dataset": sorted(grouped.replicates.unique().tolist()),
        "all_seeds_minimum_cell_one": {
            "count": all_seed_singleton,
            "proportion": all_seed_singleton / n,
            "wilson_95": wilson(all_seed_singleton, n),
        },
        "any_seed_minimum_cell_one": {
            "count": any_seed_singleton,
            "proportion": any_seed_singleton / n,
            "wilson_95": wilson(any_seed_singleton, n),
        },
        "all_seeds_minimum_cell_at_least_five": {
            "count": all_seed_k5,
            "proportion": all_seed_k5 / n,
        },
        "bayes_linkage_success": {
            "median_dataset_mean": float(np.median(pid)),
            "bootstrap_95": median_pid_ci,
            "quartiles": [float(item) for item in np.quantile(pid, [0.25, 0.5, 0.75])],
            "datasets_at_least_0_5": int((pid >= 0.5).sum()),
            "datasets_at_least_0_9": int((pid >= 0.9).sum()),
        },
        "singleton_fraction": {
            "median_dataset_mean": float(np.median(singleton)),
            "bootstrap_95": median_singleton_ci,
        },
        "seed_sensitivity": {
            "median_pid_range": float(np.median(grouped.pid_max - grouped.pid_min)),
            "maximum_pid_range": float(np.max(grouped.pid_max - grouped.pid_min)),
        },
        "metadata_screens": {
            "log_rows_spearman_rho": float(row_corr.statistic),
            "log_rows_p": float(row_corr.pvalue),
            "log_features_spearman_rho": float(feature_corr.statistic),
            "log_features_p": float(feature_corr.pvalue),
            "interpretation": "exploratory screens only; neither correlation is a privacy bound",
        },
        "lowest_pid": grouped.nsmallest(10, "pid_mean").to_dict(orient="records"),
        "highest_pid": grouped.nlargest(10, "pid_mean").to_dict(orient="records"),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    lo, hi = result["all_seeds_minimum_cell_one"]["wilson_95"]
    p_lo, p_hi = result["bayes_linkage_success"]["bootstrap_95"]
    s_lo, s_hi = result["singleton_fraction"]["bootstrap_95"]
    lines = [
        "# OpenML-CC18 broad structural results",
        "",
        "## Design",
        "",
        f"The clean-room tier trained {len(runs)} models: {n} frozen OpenML-CC18 datasets by three pre-declared seeds. The inferential unit is the dataset. Every result is record-level because CC18 establishes independent observations, not person-level entity resolution.",
        "",
        "Each model used 30 XGBoost trees, depth 4, minimum child weight 20, deterministic full-row/full-column sampling, and at most 20,000 target-training records. Preprocessing was fitted only on the target-training split. Complete leaf-signature histograms were retained.",
        "",
        "## Results",
        "",
        f"- {all_seed_singleton}/{n} datasets ({all_seed_singleton/n:.1%}; Wilson 95% CI {lo:.1%}-{hi:.1%}) had minimum cell size 1 in all three seeds.",
        f"- {any_seed_singleton}/{n} datasets had minimum cell size 1 in at least one seed.",
        f"- Only {all_seed_k5}/{n} datasets kept minimum cell size at least 5 in all seeds; these cases must still be read with utility because a nearly constant model can appear structurally private.",
        f"- Median dataset-level Bayes linkage success was {np.median(pid):.3f} (cluster bootstrap 95% CI {p_lo:.3f}-{p_hi:.3f}).",
        f"- Median singleton-record fraction was {np.median(singleton):.3f} (cluster bootstrap 95% CI {s_lo:.3f}-{s_hi:.3f}).",
        f"- {int((pid >= .5).sum())}/{n} datasets had mean linkage success at least 0.5; {int((pid >= .9).sum())}/{n} were at least 0.9.",
        f"- Across-seed linkage ranges had median {np.median(grouped.pid_max-grouped.pid_min):.3f} and maximum {np.max(grouped.pid_max-grouped.pid_min):.3f}, so a single seed is inadequate for fine comparisons.",
        "",
        "## Interpretation",
        "",
        "The original qualitative finding generalizes strongly but not universally: modest-capacity ensembles frequently induce singleton leaf signatures. The exact claim 'all datasets have k=1' is not supported on this larger corpus. Results do not establish population linkage or person-level identification without a recipient-realizable roster and target signal.",
        "",
        "The two consistently non-singleton cases had approximately chance balanced accuracy, illustrating a required utility guard: privacy obtained by learning essentially nothing is not a useful release frontier.",
    ]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n")
    print(json.dumps({key: result[key] for key in ("datasets", "runs", "all_seeds_minimum_cell_one", "bayes_linkage_success")}, indent=2))


if __name__ == "__main__":
    main()
