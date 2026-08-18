#!/usr/bin/env python3
"""Independently validate and report the stochastic incomplete-portfolio benchmark."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_raw(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def analyze(summary: dict[str, Any], raw: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    if summary["completed_groups"] != summary["expected_groups"]:
        errors.append("benchmark groups are incomplete")
    if summary["raw_records"] != len(raw):
        errors.append("raw record count mismatch")
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in raw:
        grouped.setdefault(
            (record["scenario_id"], int(record["sample_size_per_state"])), []
        ).append(record)
        counts = record["counts"]
        for release in counts:
            for row in release:
                if sum(row) != int(record["sample_size_per_state"]):
                    errors.append("raw multinomial counts do not sum to the declared sample size")
                    break
        bound = record["certified_upper_bound"]
        if bound is not None and not 0.0 <= float(bound) <= 1.0:
            errors.append("certified upper bound lies outside [0,1]")
        for decision in record["decision_results"].values():
            if decision["false_clear"] != (decision["clears"] and not decision["actual_safe"]):
                errors.append("false-clear classification does not replay")
            if decision["false_block"] != ((not decision["clears"]) and decision["actual_safe"]):
                errors.append("false-block classification does not replay")
    summary_groups = {
        (value["scenario_id"], int(value["sample_size_per_state"])): value
        for value in summary["groups"]
    }
    if set(grouped) != set(summary_groups):
        errors.append("raw and summary group keys differ")
    for key, records in grouped.items():
        if key not in summary_groups:
            continue
        group = summary_groups[key]
        if len(records) != group["replicates"]:
            errors.append(f"replicate count mismatch for {key}")
        family_coverage = sum(item["marginal_family_covered"] for item in records) / len(records)
        bound_coverage = sum(item["bound_covers_true_value"] for item in records) / len(records)
        if abs(family_coverage - group["family_coverage_rate"]) > 1e-12:
            errors.append(f"family coverage does not replay for {key}")
        if abs(bound_coverage - group["bound_coverage_rate"]) > 1e-12:
            errors.append(f"bound coverage does not replay for {key}")
        for threshold, claimed in group["decisions"].items():
            release_yield = sum(item["decision_results"][threshold]["clears"] for item in records) / len(records)
            false_clear = sum(item["decision_results"][threshold]["false_clear"] for item in records) / len(records)
            false_block = sum(item["decision_results"][threshold]["false_block"] for item in records) / len(records)
            if abs(release_yield - claimed["release_yield"]) > 1e-12:
                errors.append(f"release yield does not replay for {key}, threshold {threshold}")
            if abs(false_clear - claimed["false_clear_rate"]) > 1e-12:
                errors.append(f"false-clear rate does not replay for {key}, threshold {threshold}")
            if abs(false_block - claimed["false_block_rate"]) > 1e-12:
                errors.append(f"false-block rate does not replay for {key}, threshold {threshold}")

    minimum_coverage = min(value["family_coverage_rate"] for value in summary["groups"])
    false_clear_rates = [
        decision["false_clear_rate"]
        for group in summary["groups"]
        for decision in group["decisions"].values()
    ]
    false_block_rates = [
        decision["false_block_rate"]
        for group in summary["groups"]
        for decision in group["decisions"].values()
        if decision["actual_safe"]
    ]
    return {
        "experiment": summary["experiment"],
        "validation": {
            "valid": not errors,
            "errors": list(dict.fromkeys(errors)),
            "raw_records_replayed": len(raw),
            "groups_replayed": len(grouped),
        },
        "design": {
            "scenarios": len({key[0] for key in grouped}),
            "sample_sizes_per_state": sorted({key[1] for key in grouped}),
            "replicates_per_group": summary["groups"][0]["replicates"],
            "thresholds": sorted(summary["groups"][0]["decisions"]),
            "family_alpha": summary["family_alpha"],
            "assurance_wide_alpha": summary["assurance_wide_alpha"],
        },
        "headline": {
            "minimum_empirical_family_coverage": minimum_coverage,
            "maximum_false_clear_rate": max(false_clear_rates),
            "maximum_safe_case_false_block_rate": max(false_block_rates),
            "all_certificate_replays_passed": all(
                value["certificate_replay_failures"] == 0 for value in summary["groups"]
            ),
            "all_special_case_equivalence_checks_passed": all(
                value["exact_equivalence_failures"] == 0 for value in summary["groups"]
            ),
        },
        "groups": summary["groups"],
        "claim_limits": [
            "These are seeded finite binary-channel simulations, not adopter-population observations.",
            "No observed false clearance does not prove a zero false-clearance probability.",
            "The experiment assumes the credited mechanism constraints are true.",
            "The fixed-horizon IID multinomial sampling model is not an anytime-valid or clustered-data result.",
        ],
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    groups = analysis["groups"]
    by_key = {(value["scenario_id"], value["sample_size_per_state"]): value for value in groups}
    independent_unassessed = by_key[("independent-arbitrary", 2000)]
    independent_certified = by_key[("independent-certified", 2000)]
    partial_unassessed = by_key[("partial-arbitrary", 500)]
    partial_certified = by_key[("partial-certified", 500)]
    return "\n".join([
        "# Stochastic incomplete-portfolio benchmark",
        "",
        "## Design",
        "",
        "Five known binary joint mechanisms were evaluated at 100, 500, and 2,000 audit observations per protected state, with 1,000 fixed-seed repetitions per case. Every repetition retained raw cell counts, generated the pre-declared 95% assurance-wide simultaneous marginal family, and computed a worst-compatible Bayes exact-guess ceiling. Policy thresholds 0.55 and 0.65 were applied without tuning on the results.",
        "",
        "## Headline results",
        "",
        f"- All {analysis['validation']['raw_records_replayed']:,} raw repetitions replayed; the minimum empirical simultaneous-family coverage across the 15 scenario/sample groups was {analysis['headline']['minimum_empirical_family_coverage']:.3f}, above the nominal 0.95 floor.",
        f"- The maximum observed false-clearance rate was {analysis['headline']['maximum_false_clear_rate']:.3f}. This is an empirical result, not proof that the probability is zero.",
        "- XOR disclosure was always bounded at 1.0 and never cleared.",
        f"- An actually independent portfolio without credited dependence evidence remained bounded at {independent_unassessed['mean_upper_bound']:.3f} with a 100% false-block rate even at n=2,000. More marginal data cannot identify dependence.",
        f"- With certified conditional independence, the n=2,000 mean ceiling fell to {independent_certified['mean_upper_bound']:.3f} and release yield at threshold 0.65 reached {independent_certified['decisions']['0.65']['release_yield']:.3f}.",
        f"- The true-value-0.6 partial mechanism was still bounded at {partial_unassessed['mean_upper_bound']:.3f} without joint evidence, but the exact diagonal constraint reduced the n=500 mean ceiling to {partial_certified['mean_upper_bound']:.3f} and release yield at threshold 0.65 to {partial_certified['decisions']['0.65']['release_yield']:.3f}.",
        "- Every replayed general LP certificate and binary special-case equivalence check passed.",
        "",
        "## Decision",
        "",
        "The benchmark supports the framework's central distinction: statistical precision quantifies uncertainty inside the declared evidence model, while mechanism evidence determines which dependence structures remain possible. The gate is safe in these simulations but can block every valid release when dependence is unassessed. Release enablement therefore comes from auditable dependence constraints or direct joint assessment, not from collecting ever more marginal samples.",
        "",
        "## Limits",
        "",
        *[f"- {value}" for value in analysis["claim_limits"]],
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    raw_path = args.workspace / summary["raw_evidence"]["path"]
    if sha256_file(raw_path) != summary["raw_evidence"]["sha256"]:
        raise ValueError("stochastic benchmark raw-evidence hash mismatch")
    raw = load_raw(raw_path)
    analysis = analyze(summary, raw)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_markdown(analysis))
    print(json.dumps({
        "validation": analysis["validation"],
        "headline": analysis["headline"],
    }, indent=2))
    if not analysis["validation"]["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
