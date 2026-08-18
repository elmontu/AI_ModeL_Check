#!/usr/bin/env python3
"""Run seeded stochastic ground-truth experiments for incomplete-portfolio assurance."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from model_release_assurance.decision_theory import exact_guess_problem  # noqa: E402
from model_release_assurance.incomplete_portfolio import (  # noqa: E402
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    IncompletePortfolioProblem,
    JointEventBound,
    StatisticalCoverage,
    build_envelope_certificate,
    solve_exact_portfolio,
    verify_envelope_certificate,
    verify_exact_certificate,
)
from model_release_assurance.portfolio_statistics import (  # noqa: E402
    exact_two_sided_binomial_interval,
)
from run_openml_structural import canonical_json, sha256_bytes, sha256_file, write_json  # noqa: E402


IMPLEMENTATION_VERSION = 1
STATE_IDS = ("state-0", "state-1")
OBSERVATION_IDS = ("0", "1")
TRANSCRIPTS = (("0", "0"), ("0", "1"), ("1", "0"), ("1", "1"))


def write_json_gz(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as stream:
            stream.write(payload)


def marginal_probabilities(channel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    first = np.asarray([
        [channel[state, 0] + channel[state, 1], channel[state, 2] + channel[state, 3]]
        for state in range(2)
    ])
    second = np.asarray([
        [channel[state, 0] + channel[state, 2], channel[state, 1] + channel[state, 3]]
        for state in range(2)
    ])
    return first, second


def bayes_value(channel: np.ndarray) -> float:
    return float(sum(max(0.5 * channel[0, cell], 0.5 * channel[1, cell]) for cell in range(4)))


def _row_vertices(
    first_interval: tuple[float, float],
    second_interval: tuple[float, float],
    diagonal_mass: float,
) -> tuple[tuple[float, float], ...]:
    """Vertices of feasible binary marginals given an exact diagonal mass."""
    l1, u1 = first_interval
    l2, u2 = second_interval
    # a,b,c,d >= 0 after substituting the two marginals and diagonal mass.
    lines = (
        (1.0, 0.0, l1), (1.0, 0.0, u1),
        (0.0, 1.0, l2), (0.0, 1.0, u2),
        (1.0, 1.0, 1.0 - diagonal_mass),
        (1.0, 1.0, 1.0 + diagonal_mass),
        (1.0, -1.0, diagonal_mass - 1.0),
        (-1.0, 1.0, diagonal_mass - 1.0),
    )

    def feasible(first: float, second: float) -> bool:
        tolerance = 1e-10
        return (
            l1 - tolerance <= first <= u1 + tolerance
            and l2 - tolerance <= second <= u2 + tolerance
            and first + second >= 1.0 - diagonal_mass - tolerance
            and first + second <= 1.0 + diagonal_mass + tolerance
            and first - second >= diagonal_mass - 1.0 - tolerance
            and second - first >= diagonal_mass - 1.0 - tolerance
        )

    candidates: set[tuple[float, float]] = set()
    for left_index, left in enumerate(lines):
        for right in lines[left_index + 1:]:
            determinant = left[0] * right[1] - left[1] * right[0]
            if abs(determinant) < 1e-15:
                continue
            first = (left[2] * right[1] - left[1] * right[2]) / determinant
            second = (left[0] * right[2] - left[2] * right[0]) / determinant
            if feasible(first, second):
                candidates.add((round(first, 15), round(second, 15)))
    return tuple(sorted(candidates))


def linear_diagonal_exact_value(
    lower: np.ndarray,
    upper: np.ndarray,
    diagonal_masses: tuple[float, float],
) -> float | None:
    """Sharp exact-guess value for the benchmark's binary diagonal-mass model."""
    row_channels: list[list[np.ndarray]] = []
    for state_index, diagonal in enumerate(diagonal_masses):
        first_interval = (
            max(lower[0, state_index, 0], 1.0 - upper[0, state_index, 1]),
            min(upper[0, state_index, 0], 1.0 - lower[0, state_index, 1]),
        )
        second_interval = (
            max(lower[1, state_index, 0], 1.0 - upper[1, state_index, 1]),
            min(upper[1, state_index, 0], 1.0 - lower[1, state_index, 1]),
        )
        vertices = _row_vertices(first_interval, second_interval, diagonal)
        if not vertices:
            return None
        rows = []
        for first, second in vertices:
            rows.append(np.asarray([
                (first + second + diagonal - 1.0) / 2.0,
                (first - second + 1.0 - diagonal) / 2.0,
                (-first + second + 1.0 - diagonal) / 2.0,
                (diagonal - first - second + 1.0) / 2.0,
            ]))
        row_channels.append(rows)
    return max(
        0.5 + 0.25 * float(np.abs(left - right).sum())
        for left in row_channels[0]
        for right in row_channels[1]
    )


def evidence(evidence_id: str, *supports: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        source_path="sealed-by-benchmark-manifest.json",
        source_sha256="a" * 64,
        supports=tuple(supports),
    )


def problem_from_intervals(
    scenario: dict[str, Any],
    lower: np.ndarray,
    upper: np.ndarray,
) -> IncompletePortfolioProblem:
    coupling = CouplingModel(scenario["coupling_model"])
    events = tuple(JointEventBound.model_validate(value) for value in scenario["joint_event_bounds"])
    releases = tuple(
        ConditionalMarginalBounds(
            release_id=f"release-{release_index + 1}",
            observation_ids=OBSERVATION_IDS,
            lower=tuple(tuple(float(value) for value in row) for row in lower[release_index]),
            upper=tuple(tuple(float(value) for value in row) for row in upper[release_index]),
            evidence=evidence(
                f"{scenario['scenario_id']}:release-{release_index + 1}",
                f"marginal:release-{release_index + 1}",
                "coverage:simultaneous",
            ),
        )
        for release_index in range(2)
    )
    return IncompletePortfolioProblem(
        portfolio_id=scenario["scenario_id"],
        population_scope_id="stochastic-ground-truth",
        population_scope_sha256="b" * 64,
        threat_id="binary-secret-exact-guess",
        decision_game_sha256="c" * 64,
        state_ids=STATE_IDS,
        prior=(0.5, 0.5),
        releases=releases,
        decision_problem=exact_guess_problem(STATE_IDS, "binary-secret-exact-guess"),
        coupling_model=coupling,
        joint_event_bounds=events,
        coverage=StatisticalCoverage.SIMULTANEOUS,
        coverage_confidence=0.95,
        selection_scope="complete pre-declared stochastic benchmark family",
        prior_evidence=evidence(f"{scenario['scenario_id']}:prior", "prior"),
        mechanism_assumptions=(scenario["description"],),
        mechanism_evidence=(evidence(
            f"{scenario['scenario_id']}:mechanism",
            f"coupling:{coupling.value}",
            *(event.event_id for event in events),
        ),),
    )


def run_benchmark(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    replicates = int(config["replicates"])
    family_alpha = float(config["family_alpha"])
    assurance_alpha = float(config["assurance_wide_alpha"])
    if not 0.0 < family_alpha <= assurance_alpha <= 0.05:
        raise ValueError("benchmark alpha allocation must satisfy 0 < family <= assurance <= 0.05")
    rng = np.random.default_rng(int(config["master_seed"]))
    raw_records: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for scenario in config["scenarios"]:
        channel = np.asarray(scenario["true_joint_channel"], dtype=float)
        if channel.shape != (2, 4) or not np.allclose(channel.sum(axis=1), 1.0):
            raise ValueError(f"invalid joint channel for {scenario['scenario_id']}")
        true_value = bayes_value(channel)
        if abs(true_value - float(scenario["true_bayes_value"])) > 1e-12:
            raise ValueError(f"true Bayes value does not replay for {scenario['scenario_id']}")
        marginals = marginal_probabilities(channel)
        for sample_size in config["sample_sizes_per_state"]:
            sample_size = int(sample_size)
            cells = 8
            per_tail_alpha = family_alpha / (2.0 * cells)
            interval_started = time.perf_counter()
            counts = np.empty((replicates, 2, 2, 2), dtype=np.int64)
            for replicate in range(replicates):
                for release_index in range(2):
                    for state_index in range(2):
                        counts[replicate, release_index, state_index] = rng.multinomial(
                            sample_size,
                            marginals[release_index][state_index],
                        )
            lowers = np.empty_like(counts, dtype=float)
            uppers = np.empty_like(counts, dtype=float)
            for index in np.ndindex(counts.shape):
                lowers[index], uppers[index] = exact_two_sided_binomial_interval(
                    int(counts[index]), sample_size, per_tail_alpha
                )
            interval_elapsed = time.perf_counter() - interval_started
            marginal_array = np.stack(marginals)
            covered = np.logical_and(
                lowers <= marginal_array[np.newaxis, ...] + 1e-15,
                uppers >= marginal_array[np.newaxis, ...] - 1e-15,
            ).all(axis=(1, 2, 3))

            certificate_started = time.perf_counter()
            bounds: list[float | None] = []
            method = {
                "conditional_independence": "conditional_independence_envelope",
                "linear_mechanism": "binary_diagonal_vertex_exact",
                "arbitrary": "xor_witness_or_general_exact",
            }[scenario["coupling_model"]]
            replay_failures = 0
            exact_equivalence_failures = 0
            exact_subset = min(
                int(config["exact_solver_replicates_per_scenario_sample"]),
                replicates,
            )
            for replicate in range(replicates):
                problem = problem_from_intervals(scenario, lowers[replicate], uppers[replicate])
                if scenario["coupling_model"] == "conditional_independence":
                    certificate = build_envelope_certificate(problem)
                    verification = verify_envelope_certificate(problem, certificate)
                    bounds.append(verification.upper_bound)
                    replay_failures += int(not verification.valid)
                elif scenario["coupling_model"] == "linear_mechanism":
                    diagonal = tuple(
                        float(event["lower"]) for event in scenario["joint_event_bounds"]
                    )
                    bound = linear_diagonal_exact_value(
                        lowers[replicate], uppers[replicate], diagonal
                    )
                    bounds.append(bound)
                    if replicate < exact_subset and bound is not None:
                        certificate = solve_exact_portfolio(problem)
                        verification = verify_exact_certificate(problem, certificate)
                        replay_failures += int(not verification.valid)
                        exact_equivalence_failures += int(
                            abs(verification.upper_bound - bound) > 1e-8
                        )
                else:
                    contains_half = bool(np.logical_and(
                        lowers[replicate] <= 0.5,
                        uppers[replicate] >= 0.5,
                    ).all())
                    if contains_half:
                        bound = 1.0
                    else:
                        bound = solve_exact_portfolio(problem).upper_bound
                    bounds.append(bound)
                    if replicate < exact_subset:
                        certificate = solve_exact_portfolio(problem)
                        verification = verify_exact_certificate(problem, certificate)
                        replay_failures += int(not verification.valid)
                        exact_equivalence_failures += int(
                            abs(verification.upper_bound - bound) > 1e-8
                        )
            certificate_elapsed = time.perf_counter() - certificate_started
            feasible = np.asarray([value is not None for value in bounds])
            bounds_array = np.asarray([
                float(value) if value is not None else np.nan for value in bounds
            ])
            record_group = []
            for replicate in range(replicates):
                decision_results = {}
                for threshold in config["thresholds"]:
                    threshold = float(threshold)
                    actual_safe = true_value <= threshold
                    clears = bool(feasible[replicate] and bounds_array[replicate] <= threshold)
                    decision_results[str(threshold)] = {
                        "actual_safe": actual_safe,
                        "clears": clears,
                        "false_clear": clears and not actual_safe,
                        "false_block": (not clears) and actual_safe,
                    }
                raw = {
                    "scenario_id": scenario["scenario_id"],
                    "sample_size_per_state": sample_size,
                    "replicate": replicate,
                    "counts": counts[replicate].tolist(),
                    "lower": lowers[replicate].tolist(),
                    "upper": uppers[replicate].tolist(),
                    "marginal_family_covered": bool(covered[replicate]),
                    "ambiguity_set_feasible": bool(feasible[replicate]),
                    "certified_upper_bound": (
                        float(bounds_array[replicate]) if feasible[replicate] else None
                    ),
                    "true_bayes_value": true_value,
                    "bound_covers_true_value": bool(
                        feasible[replicate] and bounds_array[replicate] + 1e-10 >= true_value
                    ),
                    "decision_results": decision_results,
                }
                raw_records.append(raw)
                record_group.append(raw)
            summaries.append({
                "scenario_id": scenario["scenario_id"],
                "description": scenario["description"],
                "coupling_model": scenario["coupling_model"],
                "sample_size_per_state": sample_size,
                "replicates": replicates,
                "true_bayes_value": true_value,
                "certificate_method": method,
                "family_coverage_rate": float(covered.mean()),
                "ambiguity_set_feasibility_rate": float(feasible.mean()),
                "bound_coverage_rate": float(
                    np.logical_and(feasible, bounds_array + 1e-10 >= true_value).mean()
                ),
                "mean_upper_bound": float(np.nanmean(bounds_array)),
                "median_upper_bound": float(np.nanmedian(bounds_array)),
                "maximum_upper_bound": float(np.nanmax(bounds_array)),
                "mean_conservatism_gap": float(np.nanmean(bounds_array - true_value)),
                "p95_conservatism_gap": float(np.nanquantile(bounds_array - true_value, 0.95)),
                "interval_seconds": interval_elapsed,
                "certificate_seconds": certificate_elapsed,
                "mean_certificate_seconds": certificate_elapsed / replicates,
                "certificate_replay_failures": replay_failures,
                "exact_equivalence_checks": exact_subset,
                "exact_equivalence_failures": exact_equivalence_failures,
                "decisions": {
                    str(threshold): {
                        "actual_safe": bool(true_value <= float(threshold)),
                        "release_yield": sum(
                            item["decision_results"][str(float(threshold))]["clears"]
                            for item in record_group
                        ) / replicates,
                        "false_clear_rate": sum(
                            item["decision_results"][str(float(threshold))]["false_clear"]
                            for item in record_group
                        ) / replicates,
                        "false_block_rate": sum(
                            item["decision_results"][str(float(threshold))]["false_block"]
                            for item in record_group
                        ) / replicates,
                    }
                    for threshold in config["thresholds"]
                },
            })
    result = {
        "experiment": config["experiment"],
        "implementation_version": IMPLEMENTATION_VERSION,
        "config_sha256": sha256_bytes(canonical_json(config)),
        "master_seed": int(config["master_seed"]),
        "family_alpha": family_alpha,
        "assurance_wide_alpha": assurance_alpha,
        "expected_groups": len(config["scenarios"]) * len(config["sample_sizes_per_state"]),
        "completed_groups": len(summaries),
        "failed_groups": 0,
        "raw_records": len(raw_records),
        "groups": summaries,
    }
    return result, raw_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-raw", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    summary, raw = run_benchmark(config)
    write_json_gz(args.output_raw, raw)
    raw_path = args.output_raw.resolve(strict=True)
    config_path = args.config.resolve(strict=True)
    summary["raw_evidence"] = {
        "path": str(raw_path.relative_to(ROOT)),
        "sha256": sha256_file(raw_path),
        "records": len(raw),
    }
    summary["config_file_sha256"] = sha256_file(config_path)
    write_json(args.output_summary, summary)
    print(json.dumps({
        "expected_groups": summary["expected_groups"],
        "completed_groups": summary["completed_groups"],
        "raw_records": summary["raw_records"],
        "raw_sha256": summary["raw_evidence"]["sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
