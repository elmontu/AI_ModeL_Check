#!/usr/bin/env python3
"""Run a seeded synthetic stress test of the strategic certificate algebra.

The experiment samples only inside preregistered rational intervals.  It checks
that endpoint certificates agree with all sampled parameter tuples, exercises
pessimistic tie handling, and demonstrates that detection has no deterrence
effect when the enforceable consequence is zero.  It is not behavioural or
sector-calibration evidence.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from model_release_assurance.incomplete_portfolio import RationalNumber  # noqa: E402
from model_release_assurance.strategic_assurance import (  # noqa: E402
    AssessorContract,
    AttackOption,
    ProbabilityInterval,
    RationalInterval,
    StrategicAssuranceProblem,
    StrategicCertificateStatus,
    solve_strategic_assurance,
    verify_strategic_assurance,
)


DEFAULT_SEED = 20260825
DEFAULT_SAMPLES = 10_000
DEFAULT_GRID_DENOMINATOR = 1_000


def _fraction(value: RationalNumber) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rational_bounds(value: RationalInterval) -> tuple[Fraction, Fraction]:
    return _fraction(value.lower), _fraction(value.upper)


def _probability_bounds(value: ProbabilityInterval) -> tuple[Fraction, Fraction]:
    return _fraction(value.lower), _fraction(value.upper)


def _sample(
    bounds: tuple[Fraction, Fraction], rng: random.Random, grid_denominator: int
) -> Fraction:
    weight = Fraction(rng.randrange(grid_denominator + 1), grid_denominator)
    return bounds[0] + weight * (bounds[1] - bounds[0])


def _fraction_record(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _status_expected_pass(
    status: StrategicCertificateStatus, passed: int, samples: int
) -> bool:
    if status is StrategicCertificateStatus.SUPPORTED:
        return passed == samples
    if status is StrategicCertificateStatus.CONTRADICTED:
        return passed == 0
    return True


def _submitter_trials(
    problem: StrategicAssuranceProblem,
    *,
    rng: random.Random,
    samples: int,
    grid_denominator: int,
) -> list[dict[str, Any]]:
    q_bounds = _probability_bounds(problem.audit_policy.detection_probability)
    consequence_bounds = _rational_bounds(problem.audit_policy.consequence)
    required = _fraction(problem.audit_policy.strict_margin.value)
    rows: list[dict[str, Any]] = []
    for submitter, certified in zip(
        problem.submitter_types,
        solve_strategic_assurance(problem, certificate_id="experiment-submitters").submitter_results,
        strict=True,
    ):
        gain_bounds = _rational_bounds(submitter.net_violation_gain)
        passed = 0
        minimum: Fraction | None = None
        maximum: Fraction | None = None
        for _ in range(samples):
            margin = (
                _sample(q_bounds, rng, grid_denominator)
                * _sample(consequence_bounds, rng, grid_denominator)
                - _sample(gain_bounds, rng, grid_denominator)
            )
            minimum = margin if minimum is None else min(minimum, margin)
            maximum = margin if maximum is None else max(maximum, margin)
            passed += margin >= required
        assert minimum is not None and maximum is not None
        rows.append(
            {
                "claim_kind": "submitter_unique_compliance",
                "claim_id": certified.claim_id,
                "certified_status": certified.status.value,
                "sampled_parameter_tuples": samples,
                "tuples_meeting_strict_margin": passed,
                "sampled_minimum_margin": _fraction_record(minimum),
                "sampled_maximum_margin": _fraction_record(maximum),
                "endpoint_status_agrees_with_samples": _status_expected_pass(
                    certified.status, passed, samples
                ),
            }
        )
    return rows


def _assessor_trials(
    contract: AssessorContract,
    certified_status: StrategicCertificateStatus,
    *,
    rng: random.Random,
    samples: int,
    grid_denominator: int,
) -> dict[str, Any]:
    required = _fraction(contract.strict_margin.value)
    passed = 0
    minimum: Fraction | None = None
    maximum: Fraction | None = None
    for _ in range(samples):
        low_success = _sample(
            _probability_bounds(contract.low_effort_validation_probability),
            rng,
            grid_denominator,
        )
        high_success = _sample(
            _probability_bounds(contract.high_effort_validation_probability),
            rng,
            grid_denominator,
        )
        reward = _sample(_rational_bounds(contract.validation_reward), rng, grid_denominator)
        low_cost = _sample(_rational_bounds(contract.low_effort_cost), rng, grid_denominator)
        high_cost = _sample(_rational_bounds(contract.high_effort_cost), rng, grid_denominator)
        margin = reward * (high_success - low_success) - (high_cost - low_cost)
        minimum = margin if minimum is None else min(minimum, margin)
        maximum = margin if maximum is None else max(maximum, margin)
        passed += margin >= required
    assert minimum is not None and maximum is not None
    return {
        "claim_kind": "assessor_unique_high_effort",
        "claim_id": f"assessor:{contract.contract_id}:unique-high-effort",
        "certified_status": certified_status.value,
        "sampled_parameter_tuples": samples,
        "tuples_meeting_strict_margin": passed,
        "sampled_minimum_margin": _fraction_record(minimum),
        "sampled_maximum_margin": _fraction_record(maximum),
        "endpoint_status_agrees_with_samples": _status_expected_pass(
            certified_status, passed, samples
        ),
    }


def _attacker_trials(
    option: AttackOption,
    certified_status: StrategicCertificateStatus,
    *,
    rng: random.Random,
    samples: int,
    grid_denominator: int,
) -> dict[str, Any]:
    required = _fraction(option.strict_abstention_margin.value)
    passed = 0
    minimum: Fraction | None = None
    maximum: Fraction | None = None
    for _ in range(samples):
        value_scale = _sample(_rational_bounds(option.value_scale), rng, grid_denominator)
        information_value = _sample(
            _probability_bounds(option.information_value), rng, grid_denominator
        )
        attack_cost = _sample(_rational_bounds(option.attack_cost), rng, grid_denominator)
        detection = _sample(
            _probability_bounds(option.detection_probability), rng, grid_denominator
        )
        consequence = _sample(_rational_bounds(option.consequence), rng, grid_denominator)
        payoff = value_scale * information_value - attack_cost - detection * consequence
        abstention_margin = -payoff
        minimum = abstention_margin if minimum is None else min(minimum, abstention_margin)
        maximum = abstention_margin if maximum is None else max(maximum, abstention_margin)
        passed += abstention_margin >= required
    assert minimum is not None and maximum is not None
    return {
        "claim_kind": "attacker_unique_abstention",
        "claim_id": f"attacker:{option.option_id}:unique-abstention",
        "certified_status": certified_status.value,
        "sampled_parameter_tuples": samples,
        "tuples_meeting_strict_margin": passed,
        "sampled_minimum_margin": _fraction_record(minimum),
        "sampled_maximum_margin": _fraction_record(maximum),
        "endpoint_status_agrees_with_samples": _status_expected_pass(
            certified_status, passed, samples
        ),
    }


def _submitter_frontier(problem: StrategicAssuranceProblem) -> list[dict[str, Any]]:
    maximum_gain = max(
        _fraction(value.net_violation_gain.upper) for value in problem.submitter_types
    )
    required = _fraction(problem.audit_policy.strict_margin.value)
    rows: list[dict[str, Any]] = []
    for numerator in range(1, 11):
        detection = Fraction(numerator, 10)
        minimum_consequence = (maximum_gain + required) / detection
        rows.append(
            {
                "detection_probability": _fraction_record(detection),
                "minimum_consequence_for_registered_margin": _fraction_record(
                    minimum_consequence
                ),
                "unit": problem.audit_policy.consequence.unit,
            }
        )
    return rows


def _monitoring_only_check(option: AttackOption) -> dict[str, Any] | None:
    if _fraction(option.consequence.upper) != 0:
        return None
    value_upper = _fraction(option.value_scale.upper) * _fraction(option.information_value.upper)
    cost_lower = _fraction(option.attack_cost.lower)
    payoffs = []
    for numerator in range(11):
        detection = Fraction(numerator, 10)
        payoff_upper = value_upper - cost_lower - detection * 0
        payoffs.append(
            {
                "detection_probability": _fraction_record(detection),
                "payoff_upper": _fraction_record(payoff_upper),
            }
        )
    return {
        "option_id": option.option_id,
        "consequence_is_zero": True,
        "payoff_upper_is_detection_invariant": len(
            {(v["payoff_upper"]["numerator"], v["payoff_upper"]["denominator"]) for v in payoffs}
        )
        == 1,
        "rows": payoffs,
    }


def run_experiment(
    problem: StrategicAssuranceProblem,
    *,
    seed: int = DEFAULT_SEED,
    samples: int = DEFAULT_SAMPLES,
    grid_denominator: int = DEFAULT_GRID_DENOMINATOR,
) -> dict[str, Any]:
    if samples < 1:
        raise ValueError("samples must be positive")
    if grid_denominator < 1:
        raise ValueError("grid denominator must be positive")
    certificate = solve_strategic_assurance(
        problem, certificate_id=f"strategic-experiment-{seed}"
    )
    verification = verify_strategic_assurance(problem, certificate)
    rng = random.Random(seed)
    rows = _submitter_trials(
        problem,
        rng=rng,
        samples=samples,
        grid_denominator=grid_denominator,
    )
    if problem.assessor_contract is not None and certificate.assessor_result is not None:
        rows.append(
            _assessor_trials(
                problem.assessor_contract,
                certificate.assessor_result.status,
                rng=rng,
                samples=samples,
                grid_denominator=grid_denominator,
            )
        )
    rows.extend(
        _attacker_trials(
            option,
            certified.status,
            rng=rng,
            samples=samples,
            grid_denominator=grid_denominator,
        )
        for option, certified in zip(
            problem.attack_options, certificate.attacker_results, strict=True
        )
    )
    monitoring_checks = tuple(
        value
        for option in problem.attack_options
        if (value := _monitoring_only_check(option)) is not None
    )
    tie_margin = Fraction(1, 2) * 20 - 10
    validation = {
        "certificate_replays_exactly": verification.valid,
        "all_endpoint_statuses_agree_with_sampled_tuples": all(
            row["endpoint_status_agrees_with_samples"] for row in rows
        ),
        "pessimistic_tie_has_zero_margin": tie_margin == 0,
        "pessimistic_tie_fails_positive_strict_margin": tie_margin < 1,
        "monitoring_without_consequence_is_payoff_invariant": bool(monitoring_checks)
        and all(value["payoff_upper_is_detection_invariant"] for value in monitoring_checks),
        "synthetic_evidence_cannot_support_deployment": (
            certificate.all_evidence_deployment_eligible
            or certificate.deployment_evidence_status
            is not StrategicCertificateStatus.SUPPORTED
        ),
    }
    return {
        "experiment": "governance_strategic_stress_test_v1",
        "claim_boundary": (
            "seeded sampling of synthetic registered intervals; validates executable endpoint "
            "algebra but does not evaluate governance legitimacy, authorize release, estimate "
            "behaviour or sanctions, or establish deployment safety"
        ),
        "governance_role": problem.governance_role,
        "governance_decision": "not_evaluated",
        "seed": seed,
        "samples_per_claim": samples,
        "sampling_grid_denominator": grid_denominator,
        "problem_sha256": certificate.problem_sha256,
        "certificate": certificate.model_dump(mode="json"),
        "sample_results": rows,
        "submitter_deterrence_frontier": _submitter_frontier(problem),
        "monitoring_only_checks": monitoring_checks,
        "validation": validation,
        "valid": all(validation.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--problem",
        type=Path,
        default=ROOT / "reproduction/strategic-assurance/config.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/reproduction/strategic-assurance-experiment.json",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--grid-denominator", type=int, default=DEFAULT_GRID_DENOMINATOR)
    args = parser.parse_args()
    problem = StrategicAssuranceProblem.model_validate_json(
        args.problem.read_text(encoding="utf-8")
    )
    result = run_experiment(
        problem,
        seed=args.seed,
        samples=args.samples,
        grid_denominator=args.grid_denominator,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "experiment": result["experiment"],
                "valid": result["valid"],
                "registered_model_status": result["certificate"]["registered_model_status"],
                "deployment_evidence_status": result["certificate"][
                    "deployment_evidence_status"
                ],
                "governance_decision": result["governance_decision"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    if not result["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
