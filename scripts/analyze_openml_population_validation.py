#!/usr/bin/env python3
"""Validate and aggregate finite-population representativeness experiments."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import hypergeom


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_lower(N: int, n: int, x: int, alpha: float) -> int:
    if x == 0: return 0
    low, high = x, N - n + x
    while low < high:
        middle = (low + high) // 2
        if hypergeom.sf(x - 1, N, middle, n) > alpha: high = middle
        else: low = middle + 1
    return int(low)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--summary", type=Path, required=True); parser.add_argument("--workspace", type=Path, default=Path.cwd()); parser.add_argument("--output-json", type=Path, required=True); parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args(); source = json.loads(args.summary.read_text()); errors, rows = [], []
    for run in source["records"]:
        run_errors = []
        for name, artifact in run["artifacts"].items():
            path = args.workspace / artifact["path"]
            if not path.is_file(): run_errors.append(f"missing {name}")
            elif sha256_file(path) != artifact["sha256"]: run_errors.append(f"hash mismatch {name}")
        structural = args.workspace / run["target_structural_manifest"]["path"]
        if not structural.is_file() or sha256_file(structural) != run["target_structural_manifest"]["sha256"]: run_errors.append("structural manifest missing or changed")
        histogram_path = args.workspace / run["artifacts"]["full_population_histogram"]["path"]
        if histogram_path.is_file():
            with gzip.open(histogram_path, "rt") as handle: histogram = json.load(handle)
            if sum(item["population_count"] for item in histogram) != run["population_rows"]: run_errors.append("population histogram count mismatch")
            if len(histogram) != run["population_cells"]: run_errors.append("population histogram cell mismatch")
        raw_path = args.workspace / run["artifacts"]["raw_queries"]["path"]
        if raw_path.is_file():
            raw = pd.read_parquet(raw_path)
            if len(raw) != run["query_records"]: run_errors.append("query row count mismatch")
            replay = [exact_lower(run["population_rows"], run["sample_size"], int(x), run["alpha_per_query"]) for x in raw.probability_sample_matches]
            if not np.array_equal(replay, raw.probability_simultaneous_lower.to_numpy()): run_errors.append("hypergeometric lower-bound replay mismatch")
            if not np.array_equal(raw.probability_simultaneous_lower.le(raw.true_population_cell_size), raw.probability_covers): run_errors.append("coverage flag mismatch")
        if run_errors: errors.append({"dataset_id": run["dataset_id"], "errors": run_errors})
        rows.append({"dataset_id": run["dataset_id"], "dataset_name": run["dataset_name"], "population_rows": run["population_rows"], "population_cells": run["population_cells"], "sample_size": run["sample_size"], "census": run["sample_size"] == run["population_rows"], **run["diagnostics"]})
    frame = pd.DataFrame(rows)
    result = {
        "analysis_unit": "complete frozen OpenML snapshot as a finite benchmark population",
        "validation": {"runs_checked": len(frame), "artifact_hashes_histograms_designs_counts_and_bounds_valid": not errors, "errors": errors},
        "design": {"finite_populations": len(frame), "source_rows": int(frame.population_rows.sum()), "census_populations": int(frame.census.sum()), "sampled_populations": int((~frame.census).sum()), "sample_size_cap": int(frame.sample_size.max()), "queries_per_population_max": 100, "familywise_confidence_per_population": 0.95},
        "probability_sample_outcomes": {"minimum_dataset_query_coverage": float(frame.probability_simultaneous_coverage.min()), "datasets_with_complete_query_coverage": int(frame.probability_simultaneous_coverage.eq(1.0).sum()), "median_label_total_variation": float(frame.probability_label_total_variation.median()), "median_cell_total_variation": float(frame.probability_cell_total_variation.median()), "median_of_dataset_median_relative_absolute_error": float(frame.probability_median_relative_absolute_error.median()), "total_positive_simultaneous_lower_bounds": int(frame.probability_positive_lower_bounds.sum())},
        "biased_stress_outcomes": {"minimum_dataset_pseudo_coverage": float(frame.biased_pseudo_coverage.min()), "datasets_with_pseudo_undercoverage": int(frame.biased_pseudo_coverage.lt(1.0).sum()), "median_label_total_variation": float(frame.biased_label_total_variation.median()), "median_cell_total_variation": float(frame.biased_cell_total_variation.median()), "median_of_dataset_median_relative_absolute_error": float(frame.biased_median_relative_absolute_error.median())},
        "per_population": frame.to_dict(orient="records"),
        "claim_boundary": "The result validates design-based inference to each enumerated OpenML snapshot only. OpenML-CC18 is not a probability sample of Singapore residents, companies, ministries, or government model releases.",
        "interpretation": ["Representativeness is a property of the target-population definition and probability sampling design, not a visual similarity score.", "The exact hypergeometric procedure controls simultaneous query undercoverage only under the declared simple-random-sampling design.", "The biased control demonstrates why applying the same formulas to convenience or covariate-selected data is invalid.", "A real government adaptation requires a dated frame, protected-unit inclusion probabilities, nonresponse/coverage analysis, weights, and external validation."],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True); args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    p, b = result["probability_sample_outcomes"], result["biased_stress_outcomes"]
    args.output_md.write_text("\n".join(["# Finite-population validation", "", "## Scope", "", f"Each complete frozen OpenML snapshot was declared as one finite benchmark population. This covers {len(frame)} populations and {int(frame.population_rows.sum()):,} rows. It does not make OpenML representative of Singapore residents, companies, ministries, or government releases.", "", "## Design", "", f"For each population, the sealed tree observable was evaluated on every row. A simple random sample without replacement of up to {int(frame.sample_size.max()):,} rows estimated the true population size of up to 100 queried leaf-signature cells. Exact hypergeometric lower bounds used Bonferroni control for 95% simultaneous confidence within each population. A deterministic covariate-ordered sample was retained as an invalid-design stress control.", "", "## Results", "", f"- {p['datasets_with_complete_query_coverage']}/{len(frame)} probability-sample runs covered every queried true cell count; the minimum within-dataset coverage was {p['minimum_dataset_query_coverage']:.1%}.", f"- Median label and complete-cell distribution total-variation distances were {p['median_label_total_variation']:.3f} and {p['median_cell_total_variation']:.3f}.", f"- The median of per-dataset median relative cell-count error was {p['median_of_dataset_median_relative_absolute_error']:.3f}; {p['total_positive_simultaneous_lower_bounds']:,} query bounds were nonzero.", f"- The invalid covariate-ordered control undercovered in {b['datasets_with_pseudo_undercoverage']}/{len(frame)} populations and had median label/cell total variation {b['median_label_total_variation']:.3f}/{b['median_cell_total_variation']:.3f}.", "", "## Determination", "", "The framework's population layer works when the target population is enumerated and the inclusion design is known. It must refuse a population clearance for convenience samples or an unspecified frame. A Ministry of Health, company, or whole-of-government adaptation still requires its own current frame, protected-unit definition, inclusion probabilities, coverage/nonresponse assessment, and external validation."]) + "\n")
    print(json.dumps({"validation": result["validation"], "design": result["design"], "probability": p, "biased": b}, indent=2))


if __name__ == "__main__": main()
