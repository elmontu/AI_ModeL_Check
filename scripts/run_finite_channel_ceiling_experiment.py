#!/usr/bin/env python3
"""Repeated-sampling validation for the finite-channel MRA ceiling.

The experiment has two deliberately separate purposes:

* a fast diagnostic tier catches gross calibration and convergence defects; and
* a primary tier replays the production ``FiniteChannelCeilingAnalyzer`` for
  every repetition.

The channels have controlled, exactly known probabilities.  This is what makes
coverage and false-CLEAR measurable; it is not a claim about any real model.
The public ``replay_counts_with_production_analyzer`` helper is the seam for a
separate, prospectively registered real-data collection stage.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import statistics
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model_release_assurance.analyzers.attack import (  # noqa: E402
    bonferroni_per_bound_confidence,
    clopper_pearson_lower,
    clopper_pearson_upper,
)
from model_release_assurance.analyzers.finite_channel import (  # noqa: E402
    FiniteChannelCeilingAnalyzer,
)
from model_release_assurance.decision import (  # noqa: E402
    decision_game_sha256,
    population_scope_sha256,
)
from model_release_assurance.decision_theory import exact_guess_problem  # noqa: E402
from model_release_assurance.engine import AssuranceEngine  # noqa: E402
from model_release_assurance.incomplete_portfolio import (  # noqa: E402
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    FiniteStatePriorEvidence,
    IncompletePortfolioProblem,
    StatisticalCoverage,
    finite_prior_contract_sha256,
    solve_analytic_portfolio,
)
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes  # noqa: E402
from model_release_assurance.models import (  # noqa: E402
    AnalyzerRequirement,
    AnalyzerProvenance,
    AssessmentRequest,
    CeilingAttackBatteryMode,
    EvidenceBindingContext,
    EvidenceClass,
    EvidenceContext,
    FiniteChannelCeilingInput,
    FiniteDecisionGame,
    FiniteGameState,
    PolicyBundle,
    PolicyReference,
    PolicyRule,
    RationalProbability,
)
from model_release_assurance.portfolio_statistics import (  # noqa: E402
    AssuranceErrorBudget,
    ErrorBudgetAllocation,
    IncompletePortfolioSpecification,
    MultinomialCountsFile,
    MultinomialEvidenceRequest,
    MultinomialReleaseCounts,
    MultinomialSamplingPlan,
    MultinomialSamplingPlanRelease,
    MultinomialStateCounts,
    SourceFileReference,
    compile_multinomial_portfolio_problem,
    exact_two_sided_binomial_interval,
    generate_simultaneous_multinomial_evidence,
)
from model_release_assurance.services import (  # noqa: E402
    AnalyzerServiceRegistry,
    LocalAnalyzerService,
)


IMPLEMENTATION_VERSION = 1
DEFAULT_CONFIG = ROOT / "reproduction" / "finite-channel-ceiling" / "config.json"
DEFAULT_OUTPUT = ROOT / "output" / "finite-channel-ceiling" / "report.json"
MODEL_FAMILIES = ("xgboost", "cnn", "llm")
ROLES = ("safe", "boundary", "unsafe")
FINITE_BOUND_FIELDS = (
    "analyzer",
    "schema_version",
    "threat_id",
    "population_scope_id",
    "analytic_evidence",
    "observed_interface_sha256",
    "observed_artifact_sha256",
    "interface_observation_definition",
    "release_enforced_finite_alphabet",
    "complete_interface_coverage",
    "recipient_realizable",
    "bounded_transcript_complete",
    "state_trials",
    "evidence_context",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _strict_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unknown = sorted(set(value) - expected)
        raise ValueError(f"{label} keys differ; missing={missing}, unknown={unknown}")


def rational(value: Mapping[str, Any], label: str = "probability") -> Fraction:
    _strict_keys(value, {"numerator", "denominator"}, label)
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or numerator < 0
        or denominator <= 0
    ):
        raise ValueError(f"{label} must contain non-negative integer numerator and positive denominator")
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        raise ValueError(f"{label} must be serialized in lowest terms")
    return result


def rational_payload(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def exact_channel_risk(
    channel: Sequence[Sequence[Fraction]],
    prior: Sequence[Fraction],
) -> Fraction:
    """Return exact Bayes success for a finite exact-guess channel."""

    if len(channel) != len(prior) or len(channel) < 2:
        raise ValueError("channel rows must align with at least two prior states")
    observation_count = len(channel[0])
    if observation_count < 1 or any(len(row) != observation_count for row in channel):
        raise ValueError("finite channel must be non-empty and rectangular")
    if sum(prior, Fraction(0)) != 1 or any(value < 0 for value in prior):
        raise ValueError("prior must be a probability vector")
    if any(sum(row, Fraction(0)) != 1 or any(value < 0 for value in row) for row in channel):
        raise ValueError("every finite-channel row must be a probability vector")
    return sum(
        max(prior[state] * channel[state][observation] for state in range(len(prior)))
        for observation in range(observation_count)
    )


def _channel(scenario: Mapping[str, Any]) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(
        tuple(
            rational(value, f"{scenario['scenario_id']} channel cell")
            for value in row
        )
        for row in scenario["channel"]
    )


def _prior(config: Mapping[str, Any]) -> tuple[Fraction, ...]:
    return tuple(rational(value, "prior probability") for value in config["prior"])


def validate_config(config: Mapping[str, Any]) -> None:
    _strict_keys(config, {
        "schema_version",
        "experiment_id",
        "implementation_version",
        "design_frozen_at",
        "authority",
        "master_seed",
        "familywise_alpha",
        "evaluation_familywise_alpha",
        "tolerance",
        "prior",
        "state_ids",
        "observation_ids",
        "selection_scope",
        "tiers",
        "primary_claim_thresholds",
        "scenarios",
    }, "experiment config")
    if config["schema_version"] != "1.0" or config["implementation_version"] != IMPLEMENTATION_VERSION:
        raise ValueError("unsupported finite-channel experiment version")
    frozen_at = datetime.fromisoformat(str(config["design_frozen_at"]))
    if frozen_at.utcoffset() is None:
        raise ValueError("design_frozen_at must include a timezone offset")
    authority = config["authority"]
    if not isinstance(authority, Mapping):
        raise ValueError("authority must be an object")
    _strict_keys(authority, {
        "experimental_only",
        "assessment_input_emitted",
        "authorization_eligible",
        "prior_screens_promoted",
    }, "authority")
    if authority != {
        "experimental_only": True,
        "assessment_input_emitted": False,
        "authorization_eligible": False,
        "prior_screens_promoted": False,
    }:
        raise ValueError("experiment authority must remain non-authorizing and outcome-new")
    for field in ("familywise_alpha", "evaluation_familywise_alpha"):
        value = config[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < float(value) <= 0.05:
            raise ValueError(f"{field} must lie in (0, 0.05]")
    if isinstance(config["master_seed"], bool) or not isinstance(config["master_seed"], int):
        raise ValueError("master_seed must be an integer")

    state_ids = tuple(config["state_ids"])
    observation_ids = tuple(config["observation_ids"])
    if len(state_ids) < 2 or len(set(state_ids)) != len(state_ids):
        raise ValueError("state_ids must contain at least two unique values")
    if not observation_ids or len(set(observation_ids)) != len(observation_ids):
        raise ValueError("observation_ids must be a non-empty unique family")
    prior = _prior(config)
    if len(prior) != len(state_ids) or sum(prior, Fraction(0)) != 1:
        raise ValueError("prior must align with states and sum exactly to one")
    tolerance = rational(config["tolerance"], "tolerance")
    if not 0 <= tolerance <= 1:
        raise ValueError("tolerance must lie in [0,1]")
    if not isinstance(config["selection_scope"], str) or not config["selection_scope"]:
        raise ValueError("selection_scope must be non-empty")

    tiers = config["tiers"]
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be a non-empty list")
    tier_ids: list[str] = []
    primary_tiers = 0
    for tier in tiers:
        _strict_keys(tier, {
            "tier_id",
            "role",
            "replicates",
            "sample_sizes_per_state",
            "production_replay",
            "production_replay_replicates",
        }, "tier")
        tier_ids.append(tier["tier_id"])
        if tier["role"] not in {"diagnostic_only", "primary"}:
            raise ValueError("tier role must be diagnostic_only or primary")
        primary_tiers += int(tier["role"] == "primary")
        replicates = tier["replicates"]
        if (
            isinstance(replicates, bool)
            or not isinstance(replicates, int)
            or not 1 <= replicates <= 10_000
        ):
            raise ValueError("tier replicates must lie in [1,10000]")
        sizes = tier["sample_sizes_per_state"]
        if (
            not isinstance(sizes, list)
            or not sizes
            or any(isinstance(value, bool) or not isinstance(value, int) or not 20 <= value <= 100_000 for value in sizes)
            or sizes != sorted(set(sizes))
        ):
            raise ValueError("sample sizes must be unique increasing integers in [20,100000]")
        if tier["production_replay"] not in {"all", "first_n_per_group"}:
            raise ValueError("unknown production_replay mode")
        replay_count = tier["production_replay_replicates"]
        if isinstance(replay_count, bool) or not isinstance(replay_count, int) or not 1 <= replay_count <= replicates:
            raise ValueError("production replay count must lie within the tier")
        if tier["production_replay"] == "all" and replay_count != replicates:
            raise ValueError("production_replay=all requires every replicate")
        if tier["role"] == "primary" and tier["production_replay"] != "all":
            raise ValueError("the primary tier must replay the production analyzer for every replicate")
    if len(set(tier_ids)) != len(tier_ids) or primary_tiers != 1:
        raise ValueError("tier ids must be unique and exactly one tier must be primary")

    thresholds = config["primary_claim_thresholds"]
    _strict_keys(thresholds, {
        "maximum_undercoverage_upper_bound",
        "maximum_false_clear_upper_bound",
        "minimum_safe_clear_lower_bound",
        "minimum_boundary_hold_lower_bound",
        "minimum_unsafe_block_lower_bound",
        "require_calibration_width_tightening",
        "require_exact_family_invariance",
        "require_all_tamper_checks_fail_closed",
        "require_full_engine_clear_hold_block_chain",
    }, "primary claim thresholds")
    for field in (
        "maximum_undercoverage_upper_bound",
        "maximum_false_clear_upper_bound",
        "minimum_safe_clear_lower_bound",
        "minimum_boundary_hold_lower_bound",
        "minimum_unsafe_block_lower_bound",
    ):
        value = thresholds[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise ValueError(f"{field} must lie in [0,1]")
    for field in (
        "require_calibration_width_tightening",
        "require_exact_family_invariance",
        "require_all_tamper_checks_fail_closed",
        "require_full_engine_clear_hold_block_chain",
    ):
        if thresholds[field] is not True:
            raise ValueError(f"{field} must remain enabled")

    scenarios = config["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a non-empty list")
    scenario_ids: list[str] = []
    observed_families: set[str] = set()
    observed_roles: set[str] = set()
    for scenario in scenarios:
        _strict_keys(scenario, {
            "scenario_id",
            "model_family",
            "role",
            "controlled_ground_truth_only",
            "real_data_target",
            "channel",
            "expected_exact_risk",
        }, "scenario")
        scenario_ids.append(scenario["scenario_id"])
        observed_families.add(scenario["model_family"])
        observed_roles.add(scenario["role"])
        if scenario["model_family"] not in MODEL_FAMILIES:
            raise ValueError("scenario has an unsupported model-family label")
        if scenario["role"] not in ROLES:
            raise ValueError("scenario role must be safe, boundary, or unsafe")
        if scenario["controlled_ground_truth_only"] is not True:
            raise ValueError("known-channel scenarios must remain controlled ground truth")
        if not isinstance(scenario["real_data_target"], str) or not scenario["real_data_target"]:
            raise ValueError("real_data_target must document the prospective adapter")
        channel = _channel(scenario)
        if len(channel) != len(state_ids) or any(len(row) != len(observation_ids) for row in channel):
            raise ValueError("scenario channel dimensions differ from the registered family")
        true_risk = exact_channel_risk(channel, prior)
        if true_risk != rational(scenario["expected_exact_risk"], "expected exact risk"):
            raise ValueError(f"exact risk does not replay for {scenario['scenario_id']}")
        expected_role = "safe" if true_risk < tolerance else "boundary" if true_risk == tolerance else "unsafe"
        if scenario["role"] != expected_role:
            raise ValueError(f"risk role does not replay for {scenario['scenario_id']}")
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("scenario ids must be unique")
    if observed_families != set(MODEL_FAMILIES) or observed_roles != set(ROLES):
        raise ValueError("the registered design must cover all three model labels and risk roles")


def validate_runtime(config: Mapping[str, Any]) -> None:
    """Avoid an accidentally unbounded no-SciPy production-size replay."""

    endpoints = len(config["scenarios"]) * len(config["state_ids"]) * len(
        config["observation_ids"]
    ) * sum(
        int(tier["replicates"]) * len(tier["sample_sizes_per_state"])
        for tier in config["tiers"]
    )
    if endpoints > 2_000 and importlib.util.find_spec("scipy") is None:
        raise RuntimeError(
            "the registered production-size experiment requires scipy for bounded "
            "Clopper-Pearson quantile generation; install the portfolio/experiment "
            "dependencies or execute in the registered EC2 environment"
        )


def _derived_seed(master_seed: int, *labels: object) -> int:
    payload = ":".join((str(master_seed), *(str(value) for value in labels)))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _sample_nested_counts(
    channel: Sequence[Sequence[Fraction]],
    sample_sizes: Sequence[int],
    *,
    master_seed: int,
    tier_id: str,
    scenario_id: str,
    replicate: int,
) -> dict[int, tuple[tuple[int, ...], ...]]:
    checkpoints = set(sample_sizes)
    result: dict[int, list[tuple[int, ...] | None]] = {
        sample_size: [None] * len(channel) for sample_size in sample_sizes
    }
    for state_index, row in enumerate(channel):
        generator = random.Random(_derived_seed(
            master_seed,
            tier_id,
            scenario_id,
            replicate,
            state_index,
        ))
        common_denominator = math.lcm(*(value.denominator for value in row))
        integer_weights = tuple(
            value.numerator * (common_denominator // value.denominator)
            for value in row
        )
        total_weight = sum(integer_weights)
        if total_weight != common_denominator:
            raise ValueError("each exact rational channel row must sum to one")
        cumulative: list[int] = []
        running = 0
        for weight in integer_weights:
            running += weight
            cumulative.append(running)
        counts = [0] * len(row)
        for trial in range(1, max(sample_sizes) + 1):
            draw = generator.randrange(total_weight)
            observation = next(
                index for index, threshold in enumerate(cumulative) if draw < threshold
            )
            counts[observation] += 1
            if trial in checkpoints:
                result[trial][state_index] = tuple(counts)
    return {
        sample_size: tuple(row for row in rows if row is not None)
        for sample_size, rows in result.items()
    }


def _downward_alpha(value: Fraction) -> float:
    candidate = float(value)
    while Fraction(Decimal(str(candidate))) > value:
        candidate = math.nextafter(candidate, 0.0)
    if candidate <= 0.0:
        raise ValueError("alpha is below the positive binary64 range")
    return candidate


def simultaneous_intervals(
    counts: Sequence[Sequence[int]],
    familywise_alpha: float,
) -> tuple[tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...], float]:
    """Generate the same simultaneous CP cell family used by production."""

    if len(counts) < 2 or not counts[0] or any(len(row) != len(counts[0]) for row in counts):
        raise ValueError("counts must be a rectangular state-by-observation table")
    trials = tuple(sum(row) for row in counts)
    if min(trials) < 1 or len(set(trials)) != 1 or any(value < 0 for row in counts for value in row):
        raise ValueError("all count rows must be non-negative with one shared positive trial count")
    exact_alpha = Fraction(Decimal(str(familywise_alpha)))
    cell_count = len(counts) * len(counts[0])
    per_tail_alpha = _downward_alpha(exact_alpha / (2 * cell_count))
    intervals = tuple(
        tuple(
            exact_two_sided_binomial_interval(successes, trials[state], per_tail_alpha)
            for successes in row
        )
        for state, row in enumerate(counts)
    )
    lower = tuple(tuple(value[0] for value in row) for row in intervals)
    upper = tuple(tuple(value[1] for value in row) for row in intervals)
    return lower, upper, per_tail_alpha


def exact_interval_bounds(
    lower: Sequence[Sequence[float]],
    upper: Sequence[Sequence[float]],
    prior: Sequence[Fraction],
) -> tuple[Fraction, Fraction]:
    """Exact one-release floor and worst-compatible ceiling from serialized endpoints."""

    lower_fraction = tuple(
        tuple(Fraction(Decimal(str(value))) for value in row) for row in lower
    )
    upper_fraction = tuple(
        tuple(Fraction(Decimal(str(value))) for value in row) for row in upper
    )
    observations = len(lower_fraction[0])
    floor = sum(
        max(prior[state] * lower_fraction[state][observation] for state in range(len(prior)))
        for observation in range(observations)
    )
    ceiling = sum(
        max(prior[state] * upper_fraction[state][observation] for state in range(len(prior)))
        for observation in range(observations)
    )
    return max(max(prior), floor), min(Fraction(1), ceiling)


def _base_contracts(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    model_family: str,
) -> tuple[Any, Any, Any, str, str, str]:
    request = AssessmentRequest.model_validate_json(
        (ROOT / "examples" / "request.json").read_text(encoding="utf-8")
    )
    base = request.release
    artifact_sha256 = sha256_bytes(canonical_json_bytes({
        "experiment_id": config["experiment_id"],
        "scenario_id": scenario["scenario_id"],
        "controlled_ground_truth_only": True,
    }))
    channels = base.interface.output_channels.model_copy(update={
        "aggregates": False,
        "labels": True,
        "scores": False,
        "probabilities": False,
        "logits": False,
        "explanations": False,
        "text": False,
        "embeddings": False,
        "gradients": False,
        "parameters": False,
        "downloadable_files": (),
        "shipped_summary_metadata": (),
        "custom_channels": (),
    })
    interface = base.interface.model_copy(update={
        "protocol_type": "predictive",
        "access": "label",
        "outputs": ("finite_response_symbol",),
        "output_channels": channels,
        "precision_bits": None,
        "query_budget": 1,
        "adaptive_queries": False,
        "rate_limited": False,
        "rate_limit": base.interface.rate_limit,
        "timing": base.interface.timing,
        "errors": base.interface.errors,
        "execution": base.interface.execution.model_copy(update={
            "batching": "none",
            "maximum_batch_size": 1,
            "maximum_concurrent_requests": 1,
            "cross_request_state": "none",
            "cross_request_state_ttl_seconds": None,
        }),
        "access_paths": base.interface.access_paths.model_copy(update={
            "side_channels": (),
            "custom_side_channels": (),
            "admin_access": "none",
            "admin_capabilities": (),
            "local_access": "none",
            "local_capabilities": (),
        }),
        "serialization": base.interface.serialization.model_copy(update={
            "formats": ("categorical-json",),
            "media_types": ("application/json",),
            "encodings": ("utf-8",),
            "compression": (),
            "schema_sha256": sha256_bytes(canonical_json_bytes({
                "observation_ids": config["observation_ids"],
            })),
            "endianness": "not_applicable",
        }),
        "llm_protocol": None,
        "notes": "one-query, complete, enforced finite response used only by the controlled benchmark",
    })
    release = base.model_copy(update={
        "release_id": f"ceiling-{scenario['scenario_id']}",
        "owner": "controlled finite-channel experiment",
        "recipient": "benchmark decoder",
        "purpose": "measure repeated-sampling ceiling behavior against known truth",
        "model_family": model_family,
        "artifact_path": f"controlled://{scenario['scenario_id']}",
        "artifact_sha256": artifact_sha256,
        "interface": interface,
        "previous_release_ids": (),
        "expires_at": None,
    })
    raw_threat = next(
        threat for threat in request.threats
        if threat.decision_metric == "equal_prior_membership_success"
    )
    game = FiniteDecisionGame(
        game_id="controlled-equal-prior-membership",
        states=tuple(
            FiniteGameState(
                state_id=state_id,
                secret_value_definition=f"controlled benchmark secret state {state_id}",
            )
            for state_id in config["state_ids"]
        ),
        prior=tuple(
            RationalProbability(**rational_payload(value)) for value in _prior(config)
        ),
        prior_basis="prospectively frozen controlled randomized audit game",
        authority="finite-channel benchmark design",
    )
    threat = raw_threat.model_copy(update={
        "tolerance": float(rational(config["tolerance"], "tolerance")),
        "finite_game": game,
    })
    scope = next(
        value for value in request.population_scopes
        if value.scope_id == threat.population_scope_id
    )
    release_sha256 = sha256_bytes(canonical_json_bytes(release))
    interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))
    game_sha256 = decision_game_sha256(threat, scope)
    return release, threat, scope, release_sha256, interface_sha256, game_sha256


def _build_analyzer_submission(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    counts: Sequence[Sequence[int]],
    *,
    model_family: str,
    intervals: tuple[Sequence[Sequence[float]], Sequence[Sequence[float]], float] | None = None,
) -> tuple[Any, Any, FiniteChannelCeilingInput]:
    lower, upper, _ = intervals or simultaneous_intervals(
        counts,
        float(config["familywise_alpha"]),
    )
    release, threat, scope, release_sha256, interface_sha256, game_sha256 = _base_contracts(
        config,
        scenario,
        model_family,
    )
    prior = _prior(config)
    rational_prior = tuple(
        RationalProbability(**rational_payload(value)) for value in prior
    )
    count_payload = {
        "state_ids": config["state_ids"],
        "observation_ids": config["observation_ids"],
        "counts": [list(row) for row in counts],
    }
    count_sha256 = sha256_bytes(canonical_json_bytes(count_payload))
    config_sha256 = sha256_bytes(canonical_json(config))
    coverage = StatisticalCoverage.SIMULTANEOUS
    marginal = EvidenceReference(
        evidence_id=f"{scenario['scenario_id']}:simultaneous-count-family",
        source_path="embedded-count-row.json",
        source_sha256=count_sha256,
        supports=(
            f"marginal:{release.release_id}",
            f"coverage:{coverage.value}",
            f"error-budget:{config['experiment_id']}:familywise",
            "confidence-endpoints:outward-validated",
        ),
    )
    mechanism_claims = (
        f"coupling:{CouplingModel.CONDITIONAL_INDEPENDENCE.value}",
        f"artifact:{release.artifact_sha256}",
        f"interface:{interface_sha256}",
        f"complete-transcript:{release.release_id}",
    )
    prior_claim = (
        "finite-prior:"
        f"{finite_prior_contract_sha256(tuple(config['state_ids']), rational_prior)}"
    )
    problem = IncompletePortfolioProblem(
        portfolio_id=f"{scenario['scenario_id']}:single-release",
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        threat_id=threat.threat_id,
        decision_game_sha256=game_sha256,
        state_ids=tuple(config["state_ids"]),
        prior=tuple(float(value) for value in prior),
        rational_prior=rational_prior,
        releases=(ConditionalMarginalBounds(
            release_id=release.release_id,
            observation_ids=tuple(config["observation_ids"]),
            lower=tuple(tuple(row) for row in lower),
            upper=tuple(tuple(row) for row in upper),
            evidence=marginal,
        ),),
        decision_problem=exact_guess_problem(
            tuple(config["state_ids"]),
            problem_id="controlled-equal-prior-membership",
        ),
        coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
        coverage=coverage,
        coverage_confidence=1.0 - float(config["familywise_alpha"]),
        selection_scope=str(config["selection_scope"]),
        prior_evidence=EvidenceReference(
            evidence_id=f"{scenario['scenario_id']}:prior",
            source_path="embedded-prospective-design.json",
            source_sha256=config_sha256,
            supports=("prior", f"decision-game:{game_sha256}", prior_claim),
        ),
        mechanism_assumptions=(
            "the released interface emits exactly one of the registered symbols",
            "state-conditioned observations follow one fixed IID multinomial row",
        ),
        mechanism_evidence=(EvidenceReference(
            evidence_id=f"{scenario['scenario_id']}:mechanism",
            source_path="controlled-channel-mechanism.json",
            source_sha256=sha256_bytes(canonical_json_bytes({
                "scenario_id": scenario["scenario_id"],
                "claims": mechanism_claims,
            })),
            supports=mechanism_claims,
        ),),
    )
    analytic = solve_analytic_portfolio(
        problem,
        method="envelope",
        certificate_id=f"{scenario['scenario_id']}:ceiling",
    )
    observed_at = datetime.fromisoformat(str(config["design_frozen_at"])) + timedelta(seconds=1)
    context = EvidenceContext(
        release_id=release.release_id,
        release_contract_sha256=release_sha256,
        policy_sha256=config_sha256,
        artifact_sha256=release.artifact_sha256,
        interface_sha256=interface_sha256,
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        decision_game_sha256=game_sha256,
        observed_at=observed_at,
    )
    value = FiniteChannelCeilingInput(
        threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,
        analytic_evidence=analytic,
        observed_interface_sha256=interface_sha256,
        observed_artifact_sha256=release.artifact_sha256,
        interface_observation_definition=(
            "the complete one-query response symbol; timing is unobservable, errors are absent, "
            "and no model artifact or auxiliary output is released"
        ),
        release_enforced_finite_alphabet=True,
        complete_interface_coverage=True,
        recipient_realizable=True,
        bounded_transcript_complete=True,
        state_trials=tuple(sample_size for _ in config["state_ids"]),
        evidence_context=context,
        provenance=AnalyzerProvenance(
            tool="finite-channel-ceiling-ground-truth-experiment",
            tool_version="1.0",
            producer={
                "service_id": "mra.analyzer.finite_channel_ceiling",
                "service_version": "1.0.0",
                "implementation_sha256": sha256_file(Path(__file__)),
                "configuration_sha256": config_sha256,
            },
            configuration_path="reproduction/finite-channel-ceiling/config.json",
            source_path="embedded-count-row.json",
            source_sha256=count_sha256,
            bound_fields=("analyzer", "threat_id", "population_scope_id", "state_trials"),
        ),
    )
    return release, threat, value


def replay_counts_with_production_analyzer(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    counts: Sequence[Sequence[int]],
    *,
    model_family: str | None = None,
    intervals: tuple[Sequence[Sequence[float]], Sequence[Sequence[float]], float] | None = None,
) -> dict[str, Any]:
    """Replay one complete count table through the production finite analyzer.

    A real-data adapter may call this helper only for a prospectively registered,
    complete finite interface.  Passing a historical attack screen does not make
    it ceiling evidence.
    """

    selected_family = model_family or str(scenario["model_family"])
    release, threat, value = _build_analyzer_submission(
        config,
        scenario,
        sample_size,
        counts,
        model_family=selected_family,
        intervals=intervals,
    )
    records = FiniteChannelCeilingAnalyzer().analyze(release, threat, value)
    floors = [record for record in records if record.evidence_class is EvidenceClass.FLOOR]
    ceilings = [record for record in records if record.evidence_class is EvidenceClass.CEILING]
    if len(floors) != 1 or len(ceilings) != 1:
        raise RuntimeError("eligible production replay did not emit exactly one floor and ceiling")
    floor = floors[0]
    ceiling = ceilings[0]
    assert floor.exact_lower is not None and ceiling.exact_upper is not None
    return {
        "model_family": selected_family,
        "floor": floor.lower,
        "ceiling": ceiling.upper,
        "exact_floor": rational_payload(floor.exact_lower.as_fraction()),
        "exact_ceiling": rational_payload(ceiling.exact_upper.as_fraction()),
        "resolution": ceiling.details["resolution"],
        "floor_can_block": floor.can_block,
        "ceiling_can_clear": ceiling.can_clear,
    }


def replay_counts_with_assurance_engine(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    counts: Sequence[Sequence[int]],
) -> dict[str, Any]:
    """Replay a count table through source verification, policy, and decision.

    The temporary source bundle exercises the same trust boundary as ``mra
    assess``.  It is deterministically regenerable from the retained config and
    count rows; no model data or trained parameters enter the bundle.
    """

    with tempfile.TemporaryDirectory(prefix="mra-ceiling-engine-") as directory:
        base_dir = Path(directory)
        artifact_path = base_dir / "controlled-channel-artifact.json"
        artifact_payload = {
            "experiment_id": config["experiment_id"],
            "scenario_id": scenario["scenario_id"],
            "controlled_ground_truth_only": True,
        }
        artifact_path.write_bytes(canonical_json_bytes(artifact_payload))
        release, threat, scope, _, interface_sha256, game_sha256 = _base_contracts(
            config,
            scenario,
            str(scenario["model_family"]),
        )
        release = release.model_copy(update={
            "artifact_path": artifact_path.name,
            "artifact_sha256": sha256_file(artifact_path),
        })
        release_sha256 = sha256_bytes(canonical_json_bytes(release))
        scope_sha256 = population_scope_sha256(scope)
        service = LocalAnalyzerService(FiniteChannelCeilingAnalyzer())

        analyzer_config_path = base_dir / "finite-channel-config.json"
        analyzer_config_path.write_bytes(canonical_json(config))
        analyzer_config_sha256 = sha256_file(analyzer_config_path)
        frozen_at = datetime.fromisoformat(str(config["design_frozen_at"]))
        if frozen_at >= datetime.now(timezone.utc):
            raise ValueError("design_frozen_at must predate the source-backed replay")
        policy = PolicyBundle(
            policy_id=f"{scenario['scenario_id']}:experimental-policy",
            policy_version="1.0.0",
            effective_from=frozen_at,
            expires_at=None,
            rules=(PolicyRule(
                threat_id=threat.threat_id,
                kind=threat.kind,
                mandatory=True,
                decision_metric=threat.decision_metric,
                metric_parameters=threat.metric_parameters,
                finite_game=threat.finite_game,
                tolerance=threat.tolerance,
                tolerance_basis=threat.tolerance_basis,
                ceiling_attack_battery_mode=CeilingAttackBatteryMode.WAIVED,
                ceiling_attack_battery_waiver_reason=(
                    "controlled coverage experiment; never valid as a deployment waiver"
                ),
            ),),
            analyzer_requirements=(AnalyzerRequirement(
                threat_id=threat.threat_id,
                analyzer="finite_channel_ceiling",
                minimum_service_version=service.descriptor.service_version,
                accepted_implementation_sha256s=(
                    service.descriptor.implementation_sha256,
                ),
                accepted_configuration_sha256s=(analyzer_config_sha256,),
                required=True,
            ),),
            accepted_selection_policy_sha256s=(sha256_bytes(b"controlled-selection"),),
        )
        policy_path = base_dir / "policy.json"
        policy_path.write_text(policy.model_dump_json(indent=2) + "\n", encoding="utf-8")
        policy_sha256 = sha256_file(policy_path)
        binding_context = EvidenceBindingContext(
            release_id=release.release_id,
            release_contract_sha256=release_sha256,
            policy_sha256=policy_sha256,
            artifact_sha256=release.artifact_sha256,
            interface_sha256=interface_sha256,
            population_scope_id=scope.scope_id,
            population_scope_sha256=scope_sha256,
            decision_game_sha256=game_sha256,
        )

        plan_path = base_dir / "sampling-plan.json"
        plan = MultinomialSamplingPlan(
            plan_id=f"{scenario['scenario_id']}:plan",
            family_id=f"{scenario['scenario_id']}:family",
            portfolio_id=f"{scenario['scenario_id']}:single-release",
            population_scope_id=scope.scope_id,
            threat_id=threat.threat_id,
            registered_at=frozen_at,
            state_ids=tuple(config["state_ids"]),
            releases=(MultinomialSamplingPlanRelease(
                release_id=release.release_id,
                observation_ids=tuple(config["observation_ids"]),
            ),),
            minimum_trials_per_state=sample_size,
            selection_scope=str(config["selection_scope"]),
            audit_sample_definition=(
                "fixed-seed IID state-conditioned draws from the prospectively registered "
                "controlled finite channel"
            ),
            binding_context=binding_context,
        )
        plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

        counts_path = base_dir / "counts.json"
        sampling_started_at = datetime.now(timezone.utc)
        sampling_ended_at = max(
            datetime.now(timezone.utc),
            sampling_started_at + timedelta(microseconds=1),
        )
        count_payload = {
            "state_ids": config["state_ids"],
            "observation_ids": config["observation_ids"],
            "counts": [list(row) for row in counts],
        }
        count_file = MultinomialCountsFile(
            count_file_id=f"{scenario['scenario_id']}:counts",
            sampling_plan_id=plan.plan_id,
            sampling_plan_sha256=sha256_file(plan_path),
            portfolio_id=plan.portfolio_id,
            population_scope_id=scope.scope_id,
            threat_id=threat.threat_id,
            family_id=plan.family_id,
            sampling_started_at=sampling_started_at,
            sampling_ended_at=sampling_ended_at,
            audit_sample_sha256=sha256_bytes(canonical_json(count_payload)),
            sampling_protocol=(
                "fixed-horizon IID multinomial sampling using exact rational integer "
                "weights and the registered seed schedule"
            ),
            state_ids=plan.state_ids,
            releases=(MultinomialReleaseCounts(
                release_id=release.release_id,
                observation_ids=tuple(config["observation_ids"]),
                state_rows=tuple(
                    MultinomialStateCounts(state_id=state_id, counts=tuple(row))
                    for state_id, row in zip(config["state_ids"], counts, strict=True)
                ),
            ),),
            binding_context=binding_context,
        )
        counts_path.write_text(
            count_file.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        budget_path = base_dir / "error-budget.json"
        allocation_id = f"{scenario['scenario_id']}:allocation"
        generation_id = f"{scenario['scenario_id']}:generation"
        budget = AssuranceErrorBudget(
            budget_id=f"{scenario['scenario_id']}:budget",
            authority="prospectively frozen controlled experiment",
            committed_at=frozen_at,
            period_start=date(2026, 1, 1),
            period_end=date(2099, 12, 31),
            total_alpha=float(config["familywise_alpha"]),
            allocations=(ErrorBudgetAllocation(
                allocation_id=allocation_id,
                generation_id=generation_id,
                family_id=plan.family_id,
                portfolio_id=plan.portfolio_id,
                population_scope_id=scope.scope_id,
                threat_id=threat.threat_id,
                sampling_plan_sha256=sha256_file(plan_path),
                alpha=float(config["familywise_alpha"]),
                binding_context=binding_context,
            ),),
        )
        budget_path.write_text(budget.model_dump_json(indent=2) + "\n", encoding="utf-8")

        request = MultinomialEvidenceRequest(
            generation_id=generation_id,
            allocation_id=allocation_id,
            sampling_plan_reference=SourceFileReference(
                source_id=f"{scenario['scenario_id']}:plan-source",
                source_path=plan_path.name,
                source_sha256=sha256_file(plan_path),
            ),
            counts_reference=SourceFileReference(
                source_id=f"{scenario['scenario_id']}:count-source",
                source_path=counts_path.name,
                source_sha256=sha256_file(counts_path),
            ),
            budget_reference=SourceFileReference(
                source_id=f"{scenario['scenario_id']}:budget-source",
                source_path=budget_path.name,
                source_sha256=sha256_file(budget_path),
            ),
            family_pre_registered=True,
            all_cells_reported=True,
            selection_process_covered=True,
            assurance_ledger_complete=True,
            selection_scope=plan.selection_scope,
        )
        evidence = generate_simultaneous_multinomial_evidence(request, base_dir)
        evidence_path = base_dir / "simultaneous-evidence.json"
        evidence_path.write_text(
            evidence.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        prior = _prior(config)
        rational_prior = tuple(
            RationalProbability(**rational_payload(value)) for value in prior
        )
        prior_path = base_dir / "prior.json"
        prior_evidence = FiniteStatePriorEvidence(
            threat_id=threat.threat_id,
            population_scope_id=scope.scope_id,
            population_scope_sha256=scope_sha256,
            decision_game_sha256=game_sha256,
            state_ids=tuple(config["state_ids"]),
            prior=rational_prior,
            prior_definition="prospectively frozen equal-prior controlled game",
            authority="finite-channel benchmark design",
        )
        prior_path.write_text(
            prior_evidence.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        mechanism_claims = (
            f"coupling:{CouplingModel.CONDITIONAL_INDEPENDENCE.value}",
            f"artifact:{release.artifact_sha256}",
            f"interface:{interface_sha256}",
            f"complete-transcript:{release.release_id}",
        )
        mechanism_path = base_dir / "mechanism.json"
        mechanism_path.write_text(
            json.dumps({"claims": mechanism_claims}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        specification = IncompletePortfolioSpecification(
            portfolio_id=plan.portfolio_id,
            population_scope_id=scope.scope_id,
            population_scope_sha256=scope_sha256,
            threat_id=threat.threat_id,
            decision_game_sha256=game_sha256,
            prior=tuple(float(value) for value in prior),
            rational_prior=rational_prior,
            decision_problem=exact_guess_problem(
                tuple(config["state_ids"]),
                problem_id="controlled-equal-prior-membership",
            ),
            coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
            prior_evidence=EvidenceReference(
                evidence_id=f"{scenario['scenario_id']}:prior",
                source_path=prior_path.name,
                source_sha256=sha256_file(prior_path),
                supports=(
                    "prior",
                    f"decision-game:{game_sha256}",
                    "finite-prior:"
                    f"{finite_prior_contract_sha256(tuple(config['state_ids']), rational_prior)}",
                ),
            ),
            mechanism_assumptions=("one complete enforced finite response transcript",),
            mechanism_evidence=(EvidenceReference(
                evidence_id=f"{scenario['scenario_id']}:mechanism",
                source_path=mechanism_path.name,
                source_sha256=sha256_file(mechanism_path),
                supports=mechanism_claims,
            ),),
        )
        problem = compile_multinomial_portfolio_problem(
            evidence,
            specification,
            evidence_source_path=evidence_path.name,
            evidence_source_sha256=sha256_file(evidence_path),
        )
        analytic = solve_analytic_portfolio(
            problem,
            method="envelope",
            certificate_id=f"{scenario['scenario_id']}:engine-ceiling",
        )
        observed_at = max(
            datetime.now(timezone.utc),
            sampling_ended_at + timedelta(microseconds=1),
        )
        value = FiniteChannelCeilingInput(
            threat_id=threat.threat_id,
            population_scope_id=scope.scope_id,
            analytic_evidence=analytic,
            observed_interface_sha256=interface_sha256,
            observed_artifact_sha256=release.artifact_sha256,
            interface_observation_definition="complete enforced one-query finite response",
            release_enforced_finite_alphabet=True,
            complete_interface_coverage=True,
            recipient_realizable=True,
            bounded_transcript_complete=True,
            state_trials=tuple(row.trials for row in evidence.rows),
            evidence_context=EvidenceContext(
                release_id=release.release_id,
                release_contract_sha256=release_sha256,
                policy_sha256=policy_sha256,
                artifact_sha256=release.artifact_sha256,
                interface_sha256=interface_sha256,
                population_scope_id=scope.scope_id,
                population_scope_sha256=scope_sha256,
                decision_game_sha256=game_sha256,
                observed_at=observed_at,
            ),
            provenance=AnalyzerProvenance(
                tool="finite-channel-ceiling-ground-truth-engine-replay",
                tool_version=service.descriptor.service_version,
                producer={
                    "service_id": service.descriptor.service_id,
                    "service_version": service.descriptor.service_version,
                    "implementation_sha256": service.descriptor.implementation_sha256,
                    "configuration_sha256": analyzer_config_sha256,
                },
                configuration_path=analyzer_config_path.name,
                source_path="finite-channel-input.json",
                source_sha256="0" * 64,
                bound_fields=FINITE_BOUND_FIELDS,
            ),
        )
        input_path = base_dir / value.provenance.source_path
        input_path.write_text(
            json.dumps(
                value.model_dump(mode="json", exclude={"provenance"}),
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        value = value.model_copy(update={
            "provenance": value.provenance.model_copy(update={
                "source_sha256": sha256_file(input_path),
            }),
        })
        governed_request = AssessmentRequest(
            policy=PolicyReference(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                policy_path=policy_path.name,
                policy_sha256=policy_sha256,
            ),
            release=release,
            population_scopes=(scope,),
            threats=(threat,),
            analyzer_inputs=(value,),
        )
        report = AssuranceEngine(
            service_registry=AnalyzerServiceRegistry((service,))
        ).assess(governed_request, base_dir)
        decision = report.decisions[0]
        return {
            "scenario_id": scenario["scenario_id"],
            "risk_role": scenario["role"],
            "model_family": scenario["model_family"],
            "sample_size_per_state": sample_size,
            "assessment_request_sha256": report.request_sha256,
            "overall_verdict": report.overall_verdict.value,
            "threat_verdict": decision.verdict.value,
            "release_gate": decision.resolution.release_gate,
            "attack_battery_mode": decision.ceiling_attack_battery.mode.value,
            "attack_battery_satisfied": decision.ceiling_attack_battery.satisfied,
            "evidence_classes": [record.evidence_class.value for record in report.evidence],
            "source_verification_reached": True,
            "experimental_waiver_not_deployment_valid": True,
        }


def _decision(floor: Fraction, ceiling: Fraction, tolerance: Fraction) -> str:
    if floor > tolerance:
        return "BLOCK"
    if ceiling <= tolerance:
        return "CLEAR"
    return "HOLD"


def _covered(
    lower: Sequence[Sequence[float]],
    upper: Sequence[Sequence[float]],
    channel: Sequence[Sequence[Fraction]],
) -> bool:
    return all(
        Fraction(Decimal(str(lower[state][observation]))) <= channel[state][observation]
        <= Fraction(Decimal(str(upper[state][observation])))
        for state in range(len(channel))
        for observation in range(len(channel[state]))
    )


def _group_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    evaluation_confidence: float,
) -> dict[str, Any]:
    if not records:
        raise ValueError("cannot summarize an empty benchmark group")
    first = records[0]
    repetitions = len(records)
    statuses = {
        status: sum(record["decision"] == status for record in records)
        for status in ("CLEAR", "HOLD", "BLOCK")
    }
    expected_decision = {
        "safe": "CLEAR",
        "boundary": "HOLD",
        "unsafe": "BLOCK",
    }[str(first["risk_role"])]
    correct_decisions = statuses[expected_decision]
    undercoverage = sum(not record["ceiling_covers_true_risk"] for record in records)
    false_clears = sum(record["false_clear"] for record in records)
    false_blocks = sum(record["false_block"] for record in records)
    family_covered = sum(record["simultaneous_family_covered"] for record in records)
    ceiling_values = [float(record["ceiling"]) for record in records]
    floor_values = [float(record["floor"]) for record in records]
    widths = [ceiling - floor for floor, ceiling in zip(floor_values, ceiling_values, strict=True)]
    true_risk = float(Fraction(
        first["true_exact_risk"]["numerator"],
        first["true_exact_risk"]["denominator"],
    ))
    replayed = [record for record in records if record["production_replay"]["performed"]]
    return {
        "tier_id": first["tier_id"],
        "tier_role": first["tier_role"],
        "scenario_id": first["scenario_id"],
        "model_family": first["model_family"],
        "risk_role": first["risk_role"],
        "sample_size_per_state": first["sample_size_per_state"],
        "replicates": repetitions,
        "true_exact_risk": first["true_exact_risk"],
        "simultaneous_family_coverage_rate": family_covered / repetitions,
        "ceiling_coverage_rate": 1.0 - undercoverage / repetitions,
        "undercoverage": {
            "count": undercoverage,
            "rate": undercoverage / repetitions,
            "exact_binomial_upper": clopper_pearson_upper(
                undercoverage,
                repetitions,
                evaluation_confidence,
            ),
        },
        "decision_counts": statuses,
        "decision_rates": {
            status: count / repetitions for status, count in statuses.items()
        },
        "decision_power": {
            "expected_decision": expected_decision,
            "count": correct_decisions,
            "rate": correct_decisions / repetitions,
            "simultaneous_exact_binomial_lower": clopper_pearson_lower(
                correct_decisions,
                repetitions,
                evaluation_confidence,
            ),
        },
        "false_clear": {
            "count": false_clears,
            "rate": false_clears / repetitions,
            "exact_binomial_upper": clopper_pearson_upper(
                false_clears,
                repetitions,
                evaluation_confidence,
            ),
        },
        "false_block": {
            "count": false_blocks,
            "rate": false_blocks / repetitions,
            "exact_binomial_upper": clopper_pearson_upper(
                false_blocks,
                repetitions,
                evaluation_confidence,
            ),
        },
        "coverage_exact_binomial_lower": clopper_pearson_lower(
            repetitions - undercoverage,
            repetitions,
            evaluation_confidence,
        ),
        "mean_floor": statistics.fmean(floor_values),
        "mean_ceiling": statistics.fmean(ceiling_values),
        "median_ceiling": statistics.median(ceiling_values),
        "mean_interval_width": statistics.fmean(widths),
        "mean_ceiling_conservatism": statistics.fmean(
            value - true_risk for value in ceiling_values
        ),
        "production_replays": len(replayed),
        "production_replay_mismatches": sum(
            not record["production_replay"]["exact_match"] for record in replayed
        ),
    }


def _tamper_checks(
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
    sample_size: int,
    counts: Sequence[Sequence[int]],
) -> list[dict[str, Any]]:
    intervals = simultaneous_intervals(counts, float(config["familywise_alpha"]))
    release, threat, value = _build_analyzer_submission(
        config,
        scenario,
        sample_size,
        counts,
        model_family=str(scenario["model_family"]),
        intervals=intervals,
    )
    analyzer = FiniteChannelCeilingAnalyzer()
    checks: list[dict[str, Any]] = []

    incomplete = value.model_copy(update={"complete_interface_coverage": False})
    records = analyzer.analyze(release, threat, incomplete)
    checks.append({
        "check": "incomplete_interface_cannot_clear",
        "passed": (
            len(records) == 1
            and records[0].evidence_class is EvidenceClass.SCREEN
            and not records[0].can_clear
            and records[0].details["release_gate"] == "hold"
        ),
    })

    wrong_digest = "f" * 64 if release.artifact_sha256 != "f" * 64 else "e" * 64
    changed_context = value.evidence_context.model_copy(update={
        "artifact_sha256": wrong_digest,
    })
    wrong_binding = value.model_copy(update={
        "observed_artifact_sha256": wrong_digest,
        "evidence_context": changed_context,
    })
    records = analyzer.analyze(release, threat, wrong_binding)
    checks.append({
        "check": "wrong_artifact_binding_cannot_clear",
        "passed": (
            len(records) == 1
            and records[0].evidence_class is EvidenceClass.SCREEN
            and not records[0].can_clear
            and records[0].details["release_gate"] == "hold"
        ),
    })

    certificate = value.analytic_evidence.envelope_certificate
    assert certificate is not None
    tampered_certificate = certificate.model_copy(update={
        "upper_bound": max(0.0, certificate.upper_bound - 0.05),
    })
    tampered_entry = value.analytic_evidence.model_copy(update={
        "envelope_certificate": tampered_certificate,
    })
    tampered_value = value.model_copy(update={"analytic_evidence": tampered_entry})
    records = analyzer.analyze(release, threat, tampered_value)
    checks.append({
        "check": "tampered_certificate_cannot_clear",
        "passed": (
            len(records) == 1
            and records[0].evidence_class is EvidenceClass.SCREEN
            and not records[0].can_clear
            and records[0].details["release_gate"] == "hold"
        ),
    })
    return checks


def run_experiment(
    config: Mapping[str, Any],
    *,
    enforce_runtime_requirements: bool = True,
) -> dict[str, Any]:
    validate_config(config)
    if enforce_runtime_requirements:
        validate_runtime(config)
    started = time.perf_counter()
    prior = _prior(config)
    tolerance = rational(config["tolerance"], "tolerance")
    scenario_by_id = {value["scenario_id"]: value for value in config["scenarios"]}
    raw_records: list[dict[str, Any]] = []
    family_invariance: list[dict[str, Any]] = []
    tier_runtime: list[dict[str, Any]] = []

    for tier in config["tiers"]:
        tier_started = time.perf_counter()
        for scenario in config["scenarios"]:
            channel = _channel(scenario)
            true_risk = exact_channel_risk(channel, prior)
            for replicate in range(int(tier["replicates"])):
                nested = _sample_nested_counts(
                    channel,
                    tier["sample_sizes_per_state"],
                    master_seed=int(config["master_seed"]),
                    tier_id=str(tier["tier_id"]),
                    scenario_id=str(scenario["scenario_id"]),
                    replicate=replicate,
                )
                for sample_size in tier["sample_sizes_per_state"]:
                    counts = nested[int(sample_size)]
                    intervals = simultaneous_intervals(
                        counts,
                        float(config["familywise_alpha"]),
                    )
                    lower, upper, per_tail_alpha = intervals
                    floor, ceiling = exact_interval_bounds(lower, upper, prior)
                    status = _decision(floor, ceiling, tolerance)
                    should_replay = (
                        tier["production_replay"] == "all"
                        or replicate < int(tier["production_replay_replicates"])
                    )
                    replay: dict[str, Any] = {"performed": False, "exact_match": None}
                    if should_replay:
                        production = replay_counts_with_production_analyzer(
                            config,
                            scenario,
                            int(sample_size),
                            counts,
                            intervals=intervals,
                        )
                        exact_match = (
                            Fraction(
                                production["exact_floor"]["numerator"],
                                production["exact_floor"]["denominator"],
                            ) == floor
                            and Fraction(
                                production["exact_ceiling"]["numerator"],
                                production["exact_ceiling"]["denominator"],
                            ) == ceiling
                        )
                        replay = {
                            "performed": True,
                            "exact_match": exact_match,
                            "resolution": production["resolution"],
                        }
                    record = {
                        "tier_id": tier["tier_id"],
                        "tier_role": tier["role"],
                        "scenario_id": scenario["scenario_id"],
                        "model_family": scenario["model_family"],
                        "risk_role": scenario["role"],
                        "replicate": replicate,
                        "sample_size_per_state": int(sample_size),
                        "state_rows": [
                            {
                                "state_id": state_id,
                                "observation_ids": list(config["observation_ids"]),
                                "counts": list(row),
                                "trials": sum(row),
                            }
                            for state_id, row in zip(config["state_ids"], counts, strict=True)
                        ],
                        "per_tail_alpha": per_tail_alpha,
                        "simultaneous_family_covered": _covered(lower, upper, channel),
                        "true_exact_risk": rational_payload(true_risk),
                        "floor": float(floor),
                        "ceiling": float(ceiling),
                        "exact_floor": rational_payload(floor),
                        "exact_ceiling": rational_payload(ceiling),
                        "ceiling_covers_true_risk": ceiling >= true_risk,
                        "floor_covers_true_risk": floor <= true_risk,
                        "decision": status,
                        "false_clear": status == "CLEAR" and true_risk > tolerance,
                        "false_block": status == "BLOCK" and true_risk <= tolerance,
                        "production_replay": replay,
                    }
                    raw_records.append(record)

                    if replicate == 0:
                        family_outputs = [
                            replay_counts_with_production_analyzer(
                                config,
                                scenario,
                                int(sample_size),
                                counts,
                                model_family=model_family,
                                intervals=intervals,
                            )
                            for model_family in MODEL_FAMILIES
                        ]
                        signatures = {
                            canonical_json({
                                "exact_floor": value["exact_floor"],
                                "exact_ceiling": value["exact_ceiling"],
                                "resolution": value["resolution"],
                            })
                            for value in family_outputs
                        }
                        family_invariance.append({
                            "tier_id": tier["tier_id"],
                            "scenario_id": scenario["scenario_id"],
                            "sample_size_per_state": int(sample_size),
                            "model_families": list(MODEL_FAMILIES),
                            "exactly_invariant": len(signatures) == 1,
                        })
        tier_runtime.append({
            "tier_id": tier["tier_id"],
            "runtime_seconds": round(time.perf_counter() - tier_started, 6),
        })

    group_keys = sorted({
        (
            record["tier_id"],
            record["scenario_id"],
            record["sample_size_per_state"],
        )
        for record in raw_records
    })
    # The meta-evaluation intervals are simultaneous over undercoverage,
    # false-CLEAR, and role-correct decision-power endpoints for every
    # registered group. They measure Monte Carlo uncertainty and are not
    # substituted for the MRA ceiling.
    evaluation_bounds = 3 * len(group_keys)
    evaluation_confidence = bonferroni_per_bound_confidence(
        1.0 - float(config["evaluation_familywise_alpha"]),
        evaluation_bounds,
    )
    groups = [
        _group_summary(
            [
                record for record in raw_records
                if (
                    record["tier_id"],
                    record["scenario_id"],
                    record["sample_size_per_state"],
                ) == key
            ],
            evaluation_confidence=evaluation_confidence,
        )
        for key in group_keys
    ]

    calibration_groups = [value for value in groups if value["tier_role"] == "diagnostic_only"]
    primary_groups = [value for value in groups if value["tier_role"] == "primary"]
    width_tightening_checks: list[dict[str, Any]] = []
    for scenario_id in scenario_by_id:
        candidates = sorted(
            (value for value in calibration_groups if value["scenario_id"] == scenario_id),
            key=lambda value: value["sample_size_per_state"],
        )
        if len(candidates) >= 2:
            width_tightening_checks.append({
                "scenario_id": scenario_id,
                "smallest_n": candidates[0]["sample_size_per_state"],
                "largest_n": candidates[-1]["sample_size_per_state"],
                "smallest_n_mean_width": candidates[0]["mean_interval_width"],
                "largest_n_mean_width": candidates[-1]["mean_interval_width"],
                "passed": candidates[-1]["mean_interval_width"] < candidates[0]["mean_interval_width"],
            })

    first_primary_record = next(
        value for value in raw_records if value["tier_role"] == "primary"
    )
    tamper_scenario = scenario_by_id[first_primary_record["scenario_id"]]
    tamper_counts = tuple(
        tuple(row["counts"]) for row in first_primary_record["state_rows"]
    )
    tamper_checks = _tamper_checks(
        config,
        tamper_scenario,
        int(first_primary_record["sample_size_per_state"]),
        tamper_counts,
    )
    expected_gate_by_role = {
        "safe": "clear",
        "boundary": "hold",
        "unsafe": "block",
    }
    engine_decision_chain: list[dict[str, Any]] = []
    for scenario in config["scenarios"]:
        record = next(
            value
            for value in raw_records
            if value["tier_role"] == "primary"
            and value["scenario_id"] == scenario["scenario_id"]
            and value["replicate"] == 0
        )
        counts = tuple(tuple(row["counts"]) for row in record["state_rows"])
        replay = replay_counts_with_assurance_engine(
            config,
            scenario,
            int(record["sample_size_per_state"]),
            counts,
        )
        replay["expected_release_gate"] = expected_gate_by_role[scenario["role"]]
        replay["passed"] = (
            replay["release_gate"] == replay["expected_release_gate"]
            and replay["source_verification_reached"]
            and replay["evidence_classes"] == ["floor", "ceiling"]
        )
        engine_decision_chain.append(replay)
    thresholds = config["primary_claim_thresholds"]
    soundness_passed = max(
        value["undercoverage"]["exact_binomial_upper"] for value in primary_groups
    ) <= float(thresholds["maximum_undercoverage_upper_bound"])
    unsafe_groups = [value for value in primary_groups if value["risk_role"] == "unsafe"]
    false_clear_passed = max(
        value["false_clear"]["exact_binomial_upper"] for value in unsafe_groups
    ) <= float(thresholds["maximum_false_clear_upper_bound"])
    safe_power_passed = min(
        value["decision_power"]["simultaneous_exact_binomial_lower"]
        for value in primary_groups if value["risk_role"] == "safe"
    ) >= float(thresholds["minimum_safe_clear_lower_bound"])
    boundary_hold_passed = min(
        value["decision_power"]["simultaneous_exact_binomial_lower"]
        for value in primary_groups if value["risk_role"] == "boundary"
    ) >= float(thresholds["minimum_boundary_hold_lower_bound"])
    unsafe_block_passed = min(
        value["decision_power"]["simultaneous_exact_binomial_lower"]
        for value in unsafe_groups
    ) >= float(thresholds["minimum_unsafe_block_lower_bound"])
    production_replay_passed = all(
        value["production_replay_mismatches"] == 0
        and (
            value["tier_role"] != "primary"
            or value["production_replays"] == value["replicates"]
        )
        for value in groups
    )
    claims = {
        "primary_ceiling_undercoverage_upper_at_most_registered_alpha": soundness_passed,
        "primary_unsafe_false_clear_upper_at_most_registered_alpha": false_clear_passed,
        "primary_safe_clear_power_meets_target": safe_power_passed,
        "primary_boundary_hold_rate_meets_target": boundary_hold_passed,
        "primary_unsafe_block_power_meets_target": unsafe_block_passed,
        "calibration_mean_width_tightens": bool(width_tightening_checks) and all(
            value["passed"] for value in width_tightening_checks
        ),
        "production_analyzer_exact_replay_matches": production_replay_passed,
        "model_family_label_invariance": all(
            value["exactly_invariant"] for value in family_invariance
        ),
        "tamper_checks_fail_closed": all(value["passed"] for value in tamper_checks),
        "full_assurance_engine_clear_hold_block_chain": (
            all(value["passed"] for value in engine_decision_chain)
            and {value["release_gate"] for value in engine_decision_chain}
            == {"clear", "hold", "block"}
        ),
    }
    completed_expected_records = sum(
        int(tier["replicates"]) * len(tier["sample_sizes_per_state"])
        for tier in config["tiers"]
    ) * len(config["scenarios"])
    report = {
        "schema_version": "1.0",
        "experiment_id": config["experiment_id"],
        "implementation_version": IMPLEMENTATION_VERSION,
        "design": {
            "config_canonical_sha256": sha256_bytes(canonical_json(config)),
            "runner_sha256": sha256_file(Path(__file__)),
            "design_frozen_at": config["design_frozen_at"],
            "selection_scope": config["selection_scope"],
            "authority": config["authority"],
            "familywise_alpha": config["familywise_alpha"],
            "evaluation_familywise_alpha": config["evaluation_familywise_alpha"],
            "evaluation_per_endpoint_confidence": evaluation_confidence,
            "evaluation_simultaneous_bound_count": evaluation_bounds,
            "tolerance": config["tolerance"],
            "prior": config["prior"],
            "state_ids": config["state_ids"],
            "observation_ids": config["observation_ids"],
            "tiers": config["tiers"],
            "scenarios": [
                {
                    "scenario_id": value["scenario_id"],
                    "model_family": value["model_family"],
                    "risk_role": value["role"],
                    "controlled_ground_truth_only": value["controlled_ground_truth_only"],
                    "real_data_target": value["real_data_target"],
                    "exact_channel_risk": value["expected_exact_risk"],
                }
                for value in config["scenarios"]
            ],
            "primary_claim_thresholds": thresholds,
        },
        "completion": {
            "expected_records": completed_expected_records,
            "completed_records": len(raw_records),
            "all_predeclared_cells_reported": len(raw_records) == completed_expected_records,
            "failed_cells": 0,
        },
        "headline": {
            "all_registered_claims_passed": all(claims.values()),
            "registered_claims": claims,
            "minimum_primary_ceiling_coverage_rate": min(
                value["ceiling_coverage_rate"] for value in primary_groups
            ),
            "maximum_primary_undercoverage_exact_upper": max(
                value["undercoverage"]["exact_binomial_upper"] for value in primary_groups
            ),
            "maximum_primary_false_clear_exact_upper": max(
                value["false_clear"]["exact_binomial_upper"] for value in unsafe_groups
            ),
        },
        "groups": groups,
        "width_tightening_checks": width_tightening_checks,
        "model_family_invariance_checks": family_invariance,
        "tamper_checks": tamper_checks,
        "assurance_engine_decision_chain": engine_decision_chain,
        "replay_scope": {
            "primary_analyzer_replays": sum(
                value["production_replays"]
                for value in primary_groups
            ),
            "full_source_backed_engine_replays": len(engine_decision_chain),
            "full_engine_scope": "one primary replicate per safe/boundary/unsafe scenario",
        },
        "raw_count_records_sha256": sha256_bytes(canonical_json(raw_records)),
        "raw_count_records": raw_records,
        "performance": {
            "runtime_seconds": round(time.perf_counter() - started, 6),
            "tier_runtime": tier_runtime,
            "runtime_is_decision_evidence": False,
        },
        "claim_limits": [
            "The known channels are controlled mathematical ground truth, not "
            "observations from XGBoost, CNN, or LLM deployments.",
            "Model-family labels test interface-level code-path invariance; they "
            "do not substitute for real-data model collection.",
            "A real-data stage must be prospectively registered and enforce the "
            "complete finite recipient interface before collecting outcomes.",
            "Historical screens, unsuccessful attacks, or post-hoc score bins "
            "cannot be promoted into ceiling evidence.",
            "The fixed-horizon IID multinomial statement does not cover "
            "distribution shift, clustered samples, or live-interface nonconformance.",
            "The experiment emits no AssessmentRequest and grants no release authorization.",
        ],
    }
    if not report["completion"]["all_predeclared_cells_reported"]:
        raise RuntimeError("experiment did not report every predeclared cell")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the preregistered finite-channel ceiling validation experiment"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = run_experiment(config)
    report["design"]["config_file_sha256"] = sha256_file(args.config.resolve(strict=True))
    write_json(args.output, report)
    print(json.dumps({
        "experiment_id": report["experiment_id"],
        "completed_records": report["completion"]["completed_records"],
        "all_registered_claims_passed": report["headline"]["all_registered_claims_passed"],
        "minimum_primary_ceiling_coverage_rate": report["headline"]["minimum_primary_ceiling_coverage_rate"],
        "maximum_primary_undercoverage_exact_upper": report["headline"]["maximum_primary_undercoverage_exact_upper"],
        "maximum_primary_false_clear_exact_upper": report["headline"]["maximum_primary_false_clear_exact_upper"],
        "runtime_seconds": report["performance"]["runtime_seconds"],
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if report["headline"]["all_registered_claims_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
