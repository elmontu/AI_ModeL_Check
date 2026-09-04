#!/usr/bin/env python3
"""Exercise an exact finite synthetic protocol-feasibility frontier.

This benchmark deliberately consumes no external empirical evidence. A future
empirical bridge must use a separately preregistered, current, sealed evidence
bundle rather than discovering ignored local output.
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


def run_benchmark(
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    trials_per_world: int = DEFAULT_TRIALS_PER_WORLD,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not seeds:
        raise ValueError("at least one seed is required")
    if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds):
        raise ValueError("every seed must be an integer")
    if (
        isinstance(trials_per_world, bool)
        or not isinstance(trials_per_world, int)
        or trials_per_world < 1
    ):
        raise ValueError("trials-per-world must be a positive integer")

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
    claim_boundary = (
        "exact finite synthetic protocol experiments only; no external empirical "
        "evidence, deployment behavior, representative release yield, safety claim, "
        "or release authorization is evaluated"
    )
    validation = {
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
    }
    validation["synthetic_benchmark_passed"] = all(validation.values())
    analysis = {
        "benchmark": "finite_protocol_feasibility",
        "claim_boundary": claim_boundary,
        "exact_frontiers": exact_frontiers,
        "special_cases": special_cases,
        "external_evidence": {
            "status": "not_evaluated",
            "reason": (
                "no current sealed external evidence bundle is an input to this benchmark"
            ),
            "representative_release_yield_identified": False,
            "release_authorization_issued": False,
        },
        "validation": validation,
    }
    summary = {
        "benchmark": analysis["benchmark"],
        "claim_boundary": claim_boundary,
        "q_values": [
            {"numerator": value.numerator, "denominator": value.denominator}
            for value in q_values
        ],
        "exact_frontiers": exact_frontiers,
        "special_cases": special_cases,
        "monte_carlo_rows": len(raw["monte_carlo_rows"]),
        "monte_carlo_trials": sum(row["trials"] for row in raw["monte_carlo_rows"]),
        "synthetic_benchmark_passed": validation["synthetic_benchmark_passed"],
        "external_evidence_status": "not_evaluated",
        "representative_release_yield_identified": False,
        "release_authorization_issued": False,
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
    raw, summary, analysis = run_benchmark(
        seeds=tuple(args.seeds),
        trials_per_world=args.trials_per_world,
    )
    if not analysis["validation"]["synthetic_benchmark_passed"]:
        raise RuntimeError("synthetic protocol-feasibility validation failed")
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
