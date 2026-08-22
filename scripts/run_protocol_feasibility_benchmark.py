#!/usr/bin/env python3
"""Exercise the finite protocol frontier and bridge it to retained MRA evidence.

This benchmark has two deliberately separated parts:

1. exact finite synthetic experiments with known evidence laws, for which the
   soundness-liveness frontier is identified and rationally certified; and
2. an audit of the retained OpenML/effectiveness record showing whether those
   artifacts are sufficient to instantiate such a frontier for real releases.

The second part must not infer evidence laws that the retained experiments did not
estimate.
"""

from __future__ import annotations

import argparse
import json
import random
from fractions import Fraction
from pathlib import Path
from typing import Any

from model_release_assurance.incomplete_portfolio import RationalNumber
from model_release_assurance.protocol_feasibility import (
    AuthorizationMode,
    ProtocolFeasibilityProblem,
    ProtocolWorld,
    solve_protocol_feasibility,
    verify_protocol_feasibility,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (20260815, 20260816, 20260817)
DEFAULT_TRIALS_PER_WORLD = 20_000


def rational(value: Fraction | int) -> RationalNumber:
    value = Fraction(value)
    return RationalNumber(numerator=value.numerator, denominator=value.denominator)


def binary_noisy_problem(q: Fraction) -> ProtocolFeasibilityProblem:
    return ProtocolFeasibilityProblem(
        problem_id=f"binary-noisy-q-{q.numerator}-{q.denominator}",
        evidence_ids=("e0", "e1"),
        configuration_ids=("c0", "c1"),
        worlds=(
            ProtocolWorld(
                world_id="w0",
                evidence_probabilities=(rational(1 - q), rational(q)),
                acceptable_configuration_ids=("c0",),
            ),
            ProtocolWorld(
                world_id="w1",
                evidence_probabilities=(rational(q), rational(1 - q)),
                acceptable_configuration_ids=("c1",),
            ),
        ),
        unsafe_release_budget=rational(q),
        liveness_failure_budget=rational(q),
    )


def single_transcript_problem(mode: AuthorizationMode) -> ProtocolFeasibilityProblem:
    return ProtocolFeasibilityProblem(
        problem_id=f"single-transcript-{mode.value}",
        evidence_ids=("same",),
        configuration_ids=("c0", "c1"),
        worlds=(
            ProtocolWorld(
                world_id="w0",
                evidence_probabilities=(rational(1),),
                acceptable_configuration_ids=("c0",),
            ),
            ProtocolWorld(
                world_id="w1",
                evidence_probabilities=(rational(1),),
                acceptable_configuration_ids=("c1",),
            ),
        ),
        unsafe_release_budget=rational(Fraction(1, 2)),
        liveness_failure_budget=rational(Fraction(1, 2)),
        authorization_mode=mode,
    )


def open_world_problem() -> ProtocolFeasibilityProblem:
    problem = single_transcript_problem(AuthorizationMode.RANDOMIZED)
    return problem.model_copy(
        update={
            "problem_id": "open-world-zero-error",
            "unsafe_release_budget": rational(0),
            "liveness_failure_budget": rational(Fraction(1, 2)),
        }
    )


def common_action_problem() -> ProtocolFeasibilityProblem:
    return ProtocolFeasibilityProblem(
        problem_id="indistinguishable-with-common-controlled-action",
        evidence_ids=("same",),
        configuration_ids=("raw-0", "raw-1", "controlled"),
        worlds=(
            ProtocolWorld(
                world_id="w0",
                evidence_probabilities=(rational(1),),
                acceptable_configuration_ids=("raw-0", "controlled"),
            ),
            ProtocolWorld(
                world_id="w1",
                evidence_probabilities=(rational(1),),
                acceptable_configuration_ids=("raw-1", "controlled"),
            ),
        ),
        unsafe_release_budget=rational(0),
        liveness_failure_budget=rational(0),
    )


def exact_result(problem: ProtocolFeasibilityProblem) -> dict[str, Any]:
    certificate = solve_protocol_feasibility(problem, certificate_id=problem.problem_id)
    verification = verify_protocol_feasibility(certificate)
    if not verification.valid:
        raise RuntimeError("; ".join(verification.reasons))
    return {
        "problem_id": problem.problem_id,
        "authorization_mode": problem.authorization_mode.value,
        "status": verification.status,
        "lower": {
            "numerator": verification.exact_lower_numerator,
            "denominator": verification.exact_lower_denominator,
        },
        "upper": {
            "numerator": verification.exact_upper_numerator,
            "denominator": verification.exact_upper_denominator,
        },
        "problem_sha256": certificate.problem_sha256,
        "solver": certificate.solver,
        "deterministic_protocols_checked": certificate.deterministic_protocols_checked,
    }


def monte_carlo_rows(
    q_values: tuple[Fraction, ...],
    seeds: tuple[int, ...],
    trials_per_world: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for q in q_values:
        for seed in seeds:
            generator = random.Random(seed * 1_000_003 + q.numerator * 101 + q.denominator)
            for world in (0, 1):
                acceptable = 0
                unsafe = 0
                for _ in range(trials_per_world):
                    evidence_is_correct = generator.random() >= float(q)
                    selected = world if evidence_is_correct else 1 - world
                    if selected == world:
                        acceptable += 1
                    else:
                        unsafe += 1
                rows.append(
                    {
                        "q": {"numerator": q.numerator, "denominator": q.denominator},
                        "seed": seed,
                        "world": f"w{world}",
                        "trials": trials_per_world,
                        "acceptable_release_count": acceptable,
                        "unsafe_release_count": unsafe,
                        "refusal_count": 0,
                        "empirical_liveness": acceptable / trials_per_world,
                        "empirical_unsafe_rate": unsafe / trials_per_world,
                    }
                )
    return rows


def retained_evidence_audit() -> dict[str, Any]:
    manifest_path = ROOT / "output/reproduction/openml-study-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    effectiveness_path = ROOT / "output/evaluation/framework-effectiveness.json"
    effectiveness = json.loads(effectiveness_path.read_text())
    tier_roles = {
        "structural": "recipient-realizability-dependent exact screen; OpenML does not establish the roster",
        "membership": "attack lower bound or screen",
        "mlp": "attack lower bound or screen",
        "composition": "direct finite structural screen",
        "metadata-adversary": "attack lower bound or screen under exact summaries",
        "dp-sgd": "mechanism/accountant ceiling plus empirical lower bound",
        "multi-shadow": "attack lower bound or screen",
        "attribute": "controlled attack lower bound or screen",
        "reconstruction": "controlled partial-reconstruction lower bound or screen",
        "population-validation": "design-based population-bound validation, not a deployment population frame",
    }
    tiers = []
    for name, values in manifest["tiers"].items():
        tiers.append(
            {
                "tier": name,
                "expected_runs": values["expected_runs"],
                "completed_runs": values["completed_runs"],
                "failed_runs": values["failed_runs"],
                "validation_passed": values["validation_passed"],
                "protocol_role": tier_roles[name],
            }
        )
    return {
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "datasets": manifest["dataset_corpus"]["datasets"],
        "total_trained_ml_artifacts": manifest["total_trained_ml_artifacts"],
        "tiers": tiers,
        "all_tiers_complete_and_valid": all(
            row["completed_runs"] == row["expected_runs"]
            and row["failed_runs"] == 0
            and row["validation_passed"]
            for row in tiers
        ),
        "decision_oracles": effectiveness["summary"],
        "frontier_instantiable_from_retained_evidence": False,
        "reason_frontier_not_instantiable": (
            "the retained tiers do not define repeated, selection-qualified evidence laws "
            "P_omega(e) and world-specific acceptable-action tables for representative "
            "release requests; attack nulls are not safety ceilings"
        ),
        "representative_release_yield_identified": False,
    }


def run_benchmark(
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    trials_per_world: int = DEFAULT_TRIALS_PER_WORLD,
    retained_evidence: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    q_values = (
        Fraction(0),
        Fraction(1, 100),
        Fraction(1, 20),
        Fraction(1, 10),
        Fraction(1, 5),
        Fraction(3, 10),
        Fraction(2, 5),
        Fraction(1, 2),
    )
    exact_frontiers = [exact_result(binary_noisy_problem(q)) for q in q_values]
    special_cases = [
        exact_result(open_world_problem()),
        exact_result(common_action_problem()),
        exact_result(single_transcript_problem(AuthorizationMode.RANDOMIZED)),
        exact_result(single_transcript_problem(AuthorizationMode.DETERMINISTIC)),
    ]
    raw = {
        "benchmark": "finite_protocol_feasibility",
        "seeds": list(seeds),
        "trials_per_world_per_seed": trials_per_world,
        "monte_carlo_rows": monte_carlo_rows(q_values, seeds, trials_per_world),
    }
    retained = retained_evidence if retained_evidence is not None else retained_evidence_audit()
    analysis = {
        "benchmark": "finite_protocol_feasibility",
        "claim_boundary": (
            "exact synthetic protocol experiments plus an audit of retained MRA evidence; "
            "not an estimate of government release yield or proof of deployment safety"
        ),
        "exact_frontiers": exact_frontiers,
        "special_cases": special_cases,
        "retained_evidence_audit": retained,
        "validation": {
            "all_binary_frontiers_tight": all(
                row["lower"] == row["upper"] for row in exact_frontiers
            ),
            "open_world_zero_error_is_impossible": special_cases[0]["status"]
            == "target_impossible",
            "common_control_enables_exact_release": special_cases[1]["status"]
            == "target_met",
            "randomized_single_transcript_target_met": special_cases[2]["status"]
            == "target_met",
            "deterministic_single_transcript_target_impossible": special_cases[3]["status"]
            == "target_impossible",
            "all_retained_tiers_complete_and_valid": retained[
                "all_tiers_complete_and_valid"
            ],
            "all_decision_oracles_passed": retained["decision_oracles"][
                "unexpected_decision_failures"
            ]
            == 0,
        },
    }
    summary = {
        "benchmark": analysis["benchmark"],
        "claim_boundary": analysis["claim_boundary"],
        "q_values": [
            {"numerator": value.numerator, "denominator": value.denominator}
            for value in q_values
        ],
        "exact_frontiers": exact_frontiers,
        "special_cases": special_cases,
        "monte_carlo_rows": len(raw["monte_carlo_rows"]),
        "monte_carlo_trials": sum(row["trials"] for row in raw["monte_carlo_rows"]),
        "retained_datasets": retained["datasets"],
        "retained_trained_ml_artifacts": retained["total_trained_ml_artifacts"],
        "retained_tiers": len(retained["tiers"]),
        "decision_oracles": retained["decision_oracles"]["executable_oracle_checks"],
        "decision_oracles_passed": retained["decision_oracles"][
            "executable_oracle_checks_passed"
        ],
        "representative_release_yield_identified": False,
    }
    return raw, summary, analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output/reproduction",
    )
    parser.add_argument("--trials-per-world", type=int, default=DEFAULT_TRIALS_PER_WORLD)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    args = parser.parse_args()
    if args.trials_per_world < 1:
        raise ValueError("trials-per-world must be positive")
    raw, summary, analysis = run_benchmark(
        seeds=tuple(args.seeds),
        trials_per_world=args.trials_per_world,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "protocol-feasibility-benchmark-raw.json": raw,
        "protocol-feasibility-benchmark-summary.json": summary,
        "protocol-feasibility-benchmark-analysis.json": analysis,
    }
    for name, value in outputs.items():
        path = args.output_dir / name
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
