#!/usr/bin/env python3
"""Build publication-safe artifacts from the registered ceiling experiments.

The source reports intentionally retain substantially more audit material than a
paper needs.  This script validates the complete registered result families and
then emits only an explicit allow-list of aggregate metrics.  It refuses to
summarize failed, incomplete, or differently identified experiments.

The generated artifacts distinguish three claims that must not be conflated:

* experiments do not constitute a universal mathematical proof;
* the known-channel study is controlled evidence with exact ground truth; and
* the v3 public-data study is role-aware evidence conditional on its finite
  populations and source-bound closed hidden-record wrappers; and
* the optional v2 predecessor remains visibly separate and failed.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
from html import escape as xml_escape
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Mapping, Sequence


SUMMARY_SCHEMA = "1.0"
SUMMARY_ID = "mra-ceiling-publication-summary-v2"
KNOWN_EXPERIMENT_ID = "finite-channel-ceiling-ground-truth-v1"
MODEL_EXPERIMENT_ID = "model-backed-finite-channel-public-data-v3"
PREDECESSOR_MODEL_EXPERIMENT_ID = "model-backed-finite-channel-public-data-v2"

KNOWN_SCENARIOS: Mapping[str, tuple[str, str, Fraction]] = {
    "xgboost-safe-margin": ("XGBoost label", "safe", Fraction(11, 20)),
    "cnn-policy-boundary": ("CNN label", "boundary", Fraction(13, 20)),
    "llm-unsafe-margin": ("LLM label", "unsafe", Fraction(4, 5)),
}
KNOWN_EXPECTED_DECISION = {
    "safe": "CLEAR",
    "boundary": "HOLD",
    "unsafe": "BLOCK",
}
KNOWN_CLAIMS = {
    "primary_ceiling_undercoverage_upper_at_most_registered_alpha",
    "primary_unsafe_false_clear_upper_at_most_registered_alpha",
    "primary_safe_clear_power_meets_target",
    "primary_boundary_hold_rate_meets_target",
    "primary_unsafe_block_power_meets_target",
    "calibration_mean_width_tightens",
    "production_analyzer_exact_replay_matches",
    "model_family_label_invariance",
    "tamper_checks_fail_closed",
    "full_assurance_engine_clear_hold_block_chain",
}

MODEL_IDENTITIES: Mapping[str, tuple[str, str, bool]] = {
    "cnn": ("CNN / MNIST", "cnn", False),
    "xgboost": ("XGBoost / Adult", "xgboost", False),
    "compact_transformer_llm_proxy": (
        "Compact Transformer / 20 Newsgroups (LLM proxy)",
        "llm_proxy_compact_transformer",
        True,
    ),
}
MODEL_VARIANTS = {
    "raw_bins": "raw categorical NLL bins",
    "erasure_0p9": "90% state-independent erasure",
}
PREDECESSOR_MODEL_ACCEPTANCE_CRITERIA = {
    "all_six_oracle_risks_covered",
    "all_source_and_engine_replays_complete",
    "all_four_negative_controls_pass",
    "no_raw_scores_retained",
    "erasure_never_increases_exact_oracle_risk",
    "all_six_one_shot_engine_decisions_clear",
    "all_six_simultaneous_clear_rate_lowers_meet_minimum",
    "all_six_simultaneous_undercoverage_bounds_meet_maximum",
    "all_executable_wrapper_conformance_checks_pass",
}
PREDECESSOR_MODEL_NEGATIVE_CONTROLS = {
    "visible_candidate_or_model_must_be_ineligible",
    "tampered_counts_must_fail_source_replay",
    "changed_prior_must_fail_binding",
    "missing_observation_symbol_must_fail_plan_replay",
}
MODEL_ACCEPTANCE_CRITERIA = {
    "all_six_oracle_risks_covered",
    "all_source_engine_and_repeat_replays_complete",
    "all_five_negative_controls_pass",
    "no_raw_scores_retained",
    "exact_erasure_contraction_identity_holds",
    "all_six_simultaneous_undercoverage_bounds_meet_maximum",
    "all_six_simultaneous_wrong_direction_bounds_meet_maximum",
    "all_margin_eligible_correct_decision_lowers_meet_minimum",
    "at_least_three_margin_eligible_families_resolve",
    "all_executable_wrapper_conformance_and_sampling_equivalence_checks_pass",
}
MODEL_NEGATIVE_CONTROLS = {
    "visible_candidate_or_model_must_be_ineligible",
    "tampered_counts_must_fail_source_replay",
    "changed_prior_must_fail_binding",
    "missing_observation_symbol_must_fail_plan_replay",
    "tampered_or_missing_wrapper_execution_evidence_must_fail_source_replay",
}
META_MULTIPLICITY_METHOD = (
    "bonferroni_across_eighteen_one_sided_bounds:"
    "six_undercoverage_uppers_six_wrong_direction_uppers_"
    "six_correct_decision_lowers"
)
WRAPPER_CONFORMANCE_CHECK_IDS = {
    "exactly_one_categorical_symbol",
    "no_transcript_timing_or_metadata",
    "second_query_refused",
    "all_caller_fields_refused_with_constant_error",
    "complete_registered_alphabet_is_totalized",
    "exact_state_independent_erasure_schedule_replayed",
    "no_public_metadata_accessors",
}
HEX64 = re.compile(r"[0-9a-f]{64}")

# These fields may legitimately occur in source audit reports.  They must never
# leak into the publication projection produced here.
FORBIDDEN_PUBLIC_KEYS = {
    "artifact_directory",
    "collector_input_sha256",
    "derived_state_seeds",
    "ephemeral_model_artifact_sha256s",
    "finite_population_sha256",
    "raw_count_records",
    "raw_scores",
    "retained_rows_path",
    "sample_binding_sha256",
    "sample_seeds",
    "sampled_counts",
    "software",
    "state_rows",
}


class PublicationSummaryError(ValueError):
    """Raised when a report cannot safely support a publication summary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationSummaryError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PublicationSummaryError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise PublicationSummaryError(f"non-finite JSON number is forbidden: {value}")


def load_report(path: Path) -> tuple[dict[str, Any], str]:
    """Load one strict JSON object and return it with its byte-level digest."""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PublicationSummaryError(f"cannot read report {path}: {exc}") from exc
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationSummaryError(f"invalid JSON report {path}: {exc}") from exc
    _require(isinstance(value, dict), f"report {path} must be a JSON object")
    return value, hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    _require(isinstance(value, list), f"{label} must be an array")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= minimum,
        f"{label} must be an integer >= {minimum}",
    )
    return value


def _number(value: Any, label: str, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be a finite number",
    )
    result = float(value)
    _require(minimum <= result <= maximum, f"{label} is outside [{minimum}, {maximum}]")
    return result


def _probability(value: Any, label: str) -> float:
    return _number(value, label, minimum=0.0, maximum=1.0)


def _fraction(value: Any, label: str) -> Fraction:
    item = _mapping(value, label)
    _require(set(item) == {"numerator", "denominator"}, f"{label} is not an exact rational")
    numerator = _integer(item["numerator"], f"{label}.numerator")
    denominator = _integer(item["denominator"], f"{label}.denominator", minimum=1)
    result = Fraction(numerator, denominator)
    _require(
        (result.numerator, result.denominator) == (numerator, denominator),
        f"{label} must be serialized in lowest terms",
    )
    _require(Fraction(0) <= result <= Fraction(1), f"{label} is not a probability")
    return result


def _close(observed: float, expected: float) -> bool:
    return math.isclose(observed, expected, rel_tol=1e-10, abs_tol=1e-12)


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _scenario_design(report: Mapping[str, Any]) -> None:
    design = _mapping(report.get("design"), "known.design")
    scenarios = _sequence(design.get("scenarios"), "known.design.scenarios")
    _require(len(scenarios) == len(KNOWN_SCENARIOS), "known scenario roster is incomplete")
    observed: set[str] = set()
    for index, raw in enumerate(scenarios):
        scenario = _mapping(raw, f"known.design.scenarios[{index}]")
        scenario_id = scenario.get("scenario_id")
        _require(scenario_id in KNOWN_SCENARIOS, "known report contains an unregistered scenario")
        _require(scenario_id not in observed, "known report repeats a scenario")
        observed.add(str(scenario_id))
        _, expected_role, expected_risk = KNOWN_SCENARIOS[str(scenario_id)]
        _require(scenario.get("risk_role") == expected_role, "known scenario role changed")
        _require(scenario.get("controlled_ground_truth_only") is True, "known scenario lost controlled-only scope")
        _require(
            _fraction(scenario.get("exact_channel_risk"), "known scenario risk") == expected_risk,
            "known exact channel risk changed",
        )
    _require(observed == set(KNOWN_SCENARIOS), "known scenario roster differs from registration")


def _known_group(raw: Any, index: int) -> tuple[tuple[str, int], dict[str, Any]]:
    group = _mapping(raw, f"known.groups[{index}]")
    scenario_id = group.get("scenario_id")
    _require(scenario_id in KNOWN_SCENARIOS, "known group has an unregistered scenario")
    _, role, expected_risk = KNOWN_SCENARIOS[str(scenario_id)]
    _require(group.get("risk_role") == role, "known group risk role changed")
    expected_decision = KNOWN_EXPECTED_DECISION[role]
    sample_size = _integer(group.get("sample_size_per_state"), "known sample size", minimum=1)
    replicates = _integer(group.get("replicates"), "known replicates", minimum=1)
    tier_role = group.get("tier_role")
    if tier_role == "primary":
        _require(sample_size == 2000 and replicates == 400, "known primary cell is incomplete")
    elif tier_role == "diagnostic_only":
        _require(sample_size in {100, 500} and replicates == 100, "known diagnostic cell changed")
    else:
        raise PublicationSummaryError("known group has an unregistered tier role")
    _require(_fraction(group.get("true_exact_risk"), "known true risk") == expected_risk, "known group true risk changed")
    coverage_rate = _probability(group.get("ceiling_coverage_rate"), "known ceiling coverage rate")
    undercoverage = _mapping(group.get("undercoverage"), "known undercoverage")
    under_count = _integer(undercoverage.get("count"), "known undercoverage count")
    under_rate = _probability(undercoverage.get("rate"), "known undercoverage rate")
    under_upper = _probability(undercoverage.get("exact_binomial_upper"), "known undercoverage upper")
    _require(under_count <= replicates, "known undercoverage count exceeds replicates")
    _require(_close(under_rate, under_count / replicates), "known undercoverage rate/count mismatch")
    _require(_close(coverage_rate, 1.0 - under_rate), "known coverage/undercoverage mismatch")
    _require(under_upper + 1e-12 >= under_rate, "known undercoverage upper is below its estimate")
    decisions = _mapping(group.get("decision_power"), "known decision power")
    _require(decisions.get("expected_decision") == expected_decision, "known expected decision changed")
    decision_count = _integer(decisions.get("count"), "known correct-decision count")
    decision_rate = _probability(decisions.get("rate"), "known correct-decision rate")
    decision_lower = _probability(
        decisions.get("simultaneous_exact_binomial_lower"),
        "known correct-decision simultaneous lower",
    )
    _require(decision_count <= replicates, "known decision count exceeds replicates")
    _require(_close(decision_rate, decision_count / replicates), "known decision rate/count mismatch")
    _require(decision_lower <= decision_rate + 1e-12, "known decision lower exceeds its estimate")
    false_clear = _mapping(group.get("false_clear"), "known false clear")
    false_clear_count = _integer(false_clear.get("count"), "known false-clear count")
    false_clear_rate = _probability(false_clear.get("rate"), "known false-clear rate")
    false_clear_upper = _probability(
        false_clear.get("exact_binomial_upper"), "known false-clear upper"
    )
    _require(false_clear_count <= replicates, "known false-clear count exceeds replicates")
    _require(_close(false_clear_rate, false_clear_count / replicates), "known false-clear rate/count mismatch")
    _require(false_clear_upper + 1e-12 >= false_clear_rate, "known false-clear upper is below its estimate")
    mean_floor = _probability(group.get("mean_floor"), "known mean floor")
    mean_ceiling = _probability(group.get("mean_ceiling"), "known mean ceiling")
    mean_width = _probability(group.get("mean_interval_width"), "known mean interval width")
    _require(mean_floor <= mean_ceiling, "known mean interval is reversed")
    _require(_close(mean_width, mean_ceiling - mean_floor), "known mean interval width is inconsistent")
    production_replays = _integer(group.get("production_replays"), "known production replays")
    replay_mismatches = _integer(group.get("production_replay_mismatches"), "known replay mismatches")
    if tier_role == "primary":
        _require(production_replays == replicates, "known primary analyzer replays are incomplete")
    _require(replay_mismatches == 0, "known production replay mismatch is present")
    public = {
        "scenario_id": scenario_id,
        "model_label": KNOWN_SCENARIOS[str(scenario_id)][0],
        "risk_role": role,
        "sample_size_per_state": sample_size,
        "replicates": replicates,
        "true_risk_exact": _fraction_text(expected_risk),
        "true_risk": float(expected_risk),
        "mean_floor": mean_floor,
        "mean_ceiling": mean_ceiling,
        "mean_interval_width": mean_width,
        "ceiling_coverage_rate": coverage_rate,
        "undercoverage_count": under_count,
        "simultaneous_undercoverage_upper": under_upper,
        "expected_decision": expected_decision,
        "correct_decision_count": decision_count,
        "correct_decision_rate": decision_rate,
        "simultaneous_correct_decision_lower": decision_lower,
        "false_clear_count": false_clear_count,
        "simultaneous_false_clear_upper": false_clear_upper,
        "production_analyzer_replays": production_replays,
    }
    return (str(scenario_id), sample_size), public


def summarize_known(report: Mapping[str, Any], report_sha256: str) -> dict[str, Any]:
    """Validate and project the exact-ground-truth controlled experiment."""

    _require(report.get("schema_version") == "1.0", "unsupported known report schema")
    _require(report.get("experiment_id") == KNOWN_EXPERIMENT_ID, "unexpected known experiment id")
    authority = _mapping(_mapping(report.get("design"), "known.design").get("authority"), "known authority")
    _require(authority.get("experimental_only") is True, "known evidence must remain experimental")
    _require(authority.get("assessment_input_emitted") is False, "known experiment emitted an assessment input")
    _require(authority.get("authorization_eligible") is False, "known experiment cannot authorize release")
    _require(authority.get("prior_screens_promoted") is False, "known experiment promoted historical screens")
    _scenario_design(report)

    completion = _mapping(report.get("completion"), "known.completion")
    expected_records = _integer(completion.get("expected_records"), "known expected records", minimum=1)
    completed_records = _integer(completion.get("completed_records"), "known completed records")
    _require(expected_records == 1800, "known registered record count changed")
    _require(completed_records == expected_records, "known experiment is incomplete")
    _require(completion.get("all_predeclared_cells_reported") is True, "known predeclared cells are missing")
    _require(_integer(completion.get("failed_cells"), "known failed cells") == 0, "known experiment has failed cells")

    headline = _mapping(report.get("headline"), "known.headline")
    claims = _mapping(headline.get("registered_claims"), "known registered claims")
    _require(set(claims) == KNOWN_CLAIMS, "known registered claim family changed")
    _require(all(value is True for value in claims.values()), "a known registered claim failed")
    _require(headline.get("all_registered_claims_passed") is True, "known experiment was not accepted")

    groups = _sequence(report.get("groups"), "known.groups")
    _require(len(groups) == 9, "known result group count is incomplete")
    projected: dict[tuple[str, int], dict[str, Any]] = {}
    for index, raw in enumerate(groups):
        key, value = _known_group(raw, index)
        _require(key not in projected, "known result group is duplicated")
        projected[key] = value
    expected_keys = {
        (scenario, sample_size)
        for scenario in KNOWN_SCENARIOS
        for sample_size in (100, 500, 2000)
    }
    _require(set(projected) == expected_keys, "known registered result cells differ")
    primary = [projected[(scenario, 2000)] for scenario in KNOWN_SCENARIOS]
    minimum_coverage = min(value["ceiling_coverage_rate"] for value in primary)
    primary_undercoverage_count = sum(value["undercoverage_count"] for value in primary)
    primary_repeat_count = sum(value["replicates"] for value in primary)
    maximum_undercoverage_upper = max(
        value["simultaneous_undercoverage_upper"] for value in primary
    )
    unsafe = next(value for value in primary if value["risk_role"] == "unsafe")
    maximum_false_clear_upper = unsafe["simultaneous_false_clear_upper"]
    _require(
        _close(
            _probability(headline.get("minimum_primary_ceiling_coverage_rate"), "known headline coverage"),
            minimum_coverage,
        ),
        "known headline coverage does not match primary cells",
    )
    _require(
        _close(
            _probability(headline.get("maximum_primary_undercoverage_exact_upper"), "known headline undercoverage"),
            maximum_undercoverage_upper,
        ),
        "known headline undercoverage does not match primary cells",
    )
    _require(
        _close(
            _probability(headline.get("maximum_primary_false_clear_exact_upper"), "known headline false-clear"),
            maximum_false_clear_upper,
        ),
        "known headline false-clear does not match the unsafe cell",
    )

    width_checks = _sequence(report.get("width_tightening_checks"), "known width checks")
    _require(len(width_checks) == 3, "known width-tightening family is incomplete")
    public_width: list[dict[str, Any]] = []
    observed_width_scenarios: set[str] = set()
    for index, raw in enumerate(width_checks):
        check = _mapping(raw, f"known.width_tightening_checks[{index}]")
        scenario_id = check.get("scenario_id")
        _require(scenario_id in KNOWN_SCENARIOS and scenario_id not in observed_width_scenarios, "known width check roster changed")
        observed_width_scenarios.add(str(scenario_id))
        _require(check.get("passed") is True, "known calibration width did not tighten")
        smallest_n = _integer(check.get("smallest_n"), "known smallest n", minimum=1)
        largest_n = _integer(check.get("largest_n"), "known largest n", minimum=1)
        small_width = _probability(check.get("smallest_n_mean_width"), "known small-n width")
        large_width = _probability(check.get("largest_n_mean_width"), "known large-n width")
        _require((smallest_n, largest_n) == (100, 500), "known width-check sample sizes changed")
        _require(large_width < small_width, "known calibration interval did not tighten")
        _require(
            _close(small_width, projected[(str(scenario_id), smallest_n)]["mean_interval_width"])
            and _close(large_width, projected[(str(scenario_id), largest_n)]["mean_interval_width"]),
            "known width check disagrees with diagnostic group summaries",
        )
        public_width.append({
            "scenario_id": scenario_id,
            "model_label": KNOWN_SCENARIOS[str(scenario_id)][0],
            "smallest_n": smallest_n,
            "smallest_n_mean_width": small_width,
            "largest_n": largest_n,
            "largest_n_mean_width": large_width,
            "relative_width_reduction": 1.0 - large_width / small_width,
        })
    _require(observed_width_scenarios == set(KNOWN_SCENARIOS), "known width checks are incomplete")

    tamper_checks = _sequence(report.get("tamper_checks"), "known tamper checks")
    expected_tamper_checks = {
        "incomplete_interface_cannot_clear",
        "wrong_artifact_binding_cannot_clear",
        "tampered_certificate_cannot_clear",
    }
    observed_tamper_checks = {
        str(_mapping(value, "known tamper check").get("check"))
        for value in tamper_checks
    }
    _require(
        len(tamper_checks) == 3
        and observed_tamper_checks == expected_tamper_checks
        and all(
            _mapping(value, "known tamper check").get("passed") is True
            for value in tamper_checks
        ),
        "known tamper controls did not all pass",
    )
    invariance = _sequence(report.get("model_family_invariance_checks"), "known invariance checks")
    invariance_keys = {
        (
            str(_mapping(value, "known invariance check").get("scenario_id")),
            _mapping(value, "known invariance check").get("sample_size_per_state"),
        )
        for value in invariance
    }
    _require(
        len(invariance) == 9
        and invariance_keys == expected_keys
        and all(
            _mapping(value, "known invariance check").get("exactly_invariant") is True
            for value in invariance
        ),
        "known label-invariance family is incomplete or failed",
    )
    engine = _sequence(report.get("assurance_engine_decision_chain"), "known engine chain")
    _require(
        len(engine) == 3
        and all(
            _mapping(value, "known engine replay").get("passed") is True
            and _mapping(value, "known engine replay").get(
                "experimental_waiver_not_deployment_valid"
            )
            is True
            for value in engine
        ),
        "known Engine decision chain is incomplete or lacks its experimental-waiver scope",
    )
    _require({str(_mapping(value, "known engine replay").get("release_gate")) for value in engine} == {"clear", "hold", "block"}, "known Engine chain did not exercise CLEAR/HOLD/BLOCK")
    replay_scope = _mapping(report.get("replay_scope"), "known replay scope")
    primary_replays = _integer(replay_scope.get("primary_analyzer_replays"), "known primary analyzer replays")
    engine_replays = _integer(replay_scope.get("full_source_backed_engine_replays"), "known full Engine replays")
    _require(primary_replays == 1200 and engine_replays == 3, "known production replay family is incomplete")

    return {
        "experiment_id": KNOWN_EXPERIMENT_ID,
        "source_report_sha256": report_sha256,
        "evidence_tier": "controlled_exact_ground_truth",
        "acceptance": "all_registered_claims_passed",
        "experimental_only": True,
        "release_authorization": "none",
        "completed_records": completed_records,
        "primary_analyzer_replays": primary_replays,
        "full_engine_replays": engine_replays,
        "full_engine_replay_limit": (
            "Integration evidence under an experimental attack-battery waiver; the waiver is not "
            "deployment-valid and the replay grants no authorization."
        ),
        "headline": {
            "minimum_primary_ceiling_coverage_rate": minimum_coverage,
            "primary_undercoverage_count": primary_undercoverage_count,
            "primary_repeat_count": primary_repeat_count,
            "maximum_simultaneous_primary_undercoverage_upper": maximum_undercoverage_upper,
            "maximum_simultaneous_unsafe_false_clear_upper": maximum_false_clear_upper,
        },
        "primary_results": primary,
        "calibration_width_tightening": public_width,
        "scope_limit": (
            "Controlled finite channels with exact ground truth; model-family names are labels, "
            "not outputs collected from those deployed model families."
        ),
    }


def _model_key(value: Mapping[str, Any], label: str) -> tuple[str, str]:
    model = value.get("collector_model")
    variant = value.get("variant_id")
    _require(model in MODEL_IDENTITIES, f"{label} has an unregistered model")
    _require(variant in MODEL_VARIANTS, f"{label} has an unregistered wrapper variant")
    return str(model), str(variant)


def _model_result(
    raw: Any,
    index: int,
) -> tuple[tuple[str, str], dict[str, Any], Fraction]:
    result = _mapping(raw, f"model.results[{index}]")
    key = _model_key(result, "model result")
    model, variant = key
    display_label, expected_family, llm_proxy = MODEL_IDENTITIES[model]
    _require(result.get("model_family") == expected_family, "model family binding changed")
    _require(result.get("llm_proxy_only") is llm_proxy, "LLM-proxy scope label changed")
    _require(_integer(result.get("trials_per_state"), "model trials per state", minimum=1) == 5000, "model trial count changed")
    risk = _fraction(result.get("oracle_exact_bayes_risk"), "model oracle exact risk")
    risk_decimal = _probability(result.get("oracle_exact_bayes_risk_decimal"), "model oracle risk decimal")
    _require(_close(risk_decimal, float(risk)), "model oracle risk decimal/exact mismatch")
    interval = _mapping(result.get("production_interval"), "model production interval")
    floor_exact = _fraction(interval.get("exact_floor"), "model exact floor")
    ceiling_exact = _fraction(interval.get("exact_ceiling"), "model exact ceiling")
    floor = _probability(interval.get("floor"), "model floor")
    ceiling = _probability(interval.get("ceiling"), "model ceiling")
    width = _probability(interval.get("width"), "model interval width")
    covers_oracle = floor_exact <= risk <= ceiling_exact
    _require(
        interval.get("covers_oracle") is covers_oracle,
        "model exact coverage and reported coverage disagree",
    )
    _require(floor <= ceiling and _close(width, float(ceiling_exact - floor_exact)), "model interval width is inconsistent")
    _require(_close(floor, float(floor_exact)) and _close(ceiling, float(ceiling_exact)), "model decimal/exact interval mismatch")
    _require(result.get("sampling_seed_replayed") is True, "model primary sampling seed was not replayed")
    _require(result.get("engine_chain_completed") is True, "model Engine chain is incomplete")
    verdict = str(result.get("experimental_engine_verdict", "")).upper()
    _require(verdict in {"CLEAR", "INCONCLUSIVE", "BLOCK"}, "model one-shot Engine verdict is invalid")
    _require(result.get("release_authorization") == "none", "model experiment granted release authority")
    public = {
        "collector_model": model,
        "model_label": display_label,
        "model_family": expected_family,
        "llm_proxy_only": llm_proxy,
        "variant_id": variant,
        "variant_label": MODEL_VARIANTS[variant],
        "trials_per_state": 5000,
        "oracle_risk_exact": _fraction_text(risk),
        "oracle_risk": risk_decimal,
        "production_floor_exact": _fraction_text(floor_exact),
        "production_floor": floor,
        "production_ceiling_exact": _fraction_text(ceiling_exact),
        "production_ceiling": ceiling,
        "production_interval_width": width,
        "covers_oracle": covers_oracle,
        "experimental_engine_verdict": verdict,
    }
    return key, public, risk


def _repeat_summary_v2(raw: Any, index: int) -> tuple[tuple[str, str], dict[str, Any], Fraction]:
    summary = _mapping(raw, f"model.repeated_validation.summaries[{index}]")
    key = _model_key(summary, "model repeat summary")
    _, expected_family, _ = MODEL_IDENTITIES[key[0]]
    _require(summary.get("model_family") == expected_family, "repeat summary model family changed")
    replicates = _integer(summary.get("replicates"), "model repeat count", minimum=1)
    trials = _integer(summary.get("trials_per_state"), "model repeat trials", minimum=1)
    _require(replicates == 200 and trials == 5000, "model repeated-validation cell is incomplete")
    risk = _fraction(summary.get("true_exact_oracle_risk"), "repeat true oracle risk")
    under_count = _integer(summary.get("undercoverage_count"), "model undercoverage count")
    under_rate = _probability(summary.get("undercoverage_rate"), "model undercoverage rate")
    under_upper = _probability(
        summary.get("simultaneous_clopper_pearson_undercoverage_upper"),
        "model simultaneous undercoverage upper",
    )
    clear_count = _integer(summary.get("clear_count"), "model clear count")
    clear_rate = _probability(summary.get("clear_rate"), "model clear rate")
    clear_lower = _probability(
        summary.get("simultaneous_clopper_pearson_clear_rate_lower"),
        "model simultaneous clear-rate lower",
    )
    _require(under_count <= replicates and clear_count <= replicates, "model repeat count exceeds replicates")
    _require(_close(under_rate, under_count / replicates), "model undercoverage rate/count mismatch")
    _require(_close(clear_rate, clear_count / replicates), "model CLEAR rate/count mismatch")
    _require(under_upper + 1e-12 >= under_rate, "model undercoverage upper is below its estimate")
    _require(clear_lower <= clear_rate + 1e-12, "model CLEAR lower exceeds its estimate")
    mean_ceiling = _probability(summary.get("mean_ceiling"), "model mean ceiling")
    p95_ceiling = _probability(summary.get("p95_ceiling"), "model p95 ceiling")
    mean_width = _probability(summary.get("mean_interval_width"), "model mean interval width")
    p95_width = _probability(summary.get("p95_interval_width"), "model p95 interval width")
    maximum_width = _probability(summary.get("maximum_interval_width"), "model maximum interval width")
    mean_excess = _number(
        summary.get("mean_ceiling_excess_over_oracle"),
        "model mean ceiling excess",
        minimum=-1.0,
        maximum=1.0,
    )
    p95_excess = _number(
        summary.get("p95_ceiling_excess_over_oracle"),
        "model p95 ceiling excess",
        minimum=-1.0,
        maximum=1.0,
    )
    maximum_excess = _number(
        summary.get("maximum_ceiling_excess_over_oracle"),
        "model maximum ceiling excess",
        minimum=-1.0,
        maximum=1.0,
    )
    _require(mean_width <= maximum_width + 1e-12 and p95_width <= maximum_width + 1e-12, "model repeat width summaries are inconsistent")
    _require(mean_excess <= maximum_excess + 1e-12 and p95_excess <= maximum_excess + 1e-12, "model ceiling-excess summaries are inconsistent")
    _require(mean_ceiling + 1e-12 >= float(risk) + mean_excess, "model mean ceiling/excess is inconsistent")
    _require(_close(mean_ceiling - float(risk), mean_excess), "model mean ceiling does not match mean ceiling excess")
    _require(p95_ceiling + 1e-12 >= mean_ceiling, "model p95 ceiling is below the mean ceiling")
    _require(summary.get("every_production_analyzer_replay_completed") is True, "model repeated analyzer replay is incomplete")
    public = {
        "replicates": replicates,
        "undercoverage_count": under_count,
        "undercoverage_rate": under_rate,
        "simultaneous_undercoverage_upper": under_upper,
        "clear_count": clear_count,
        "clear_rate": clear_rate,
        "simultaneous_clear_rate_lower": clear_lower,
        "undercoverage_target_met": under_upper <= 0.05,
        "clear_rate_target_met": clear_lower >= 0.95,
        "mean_ceiling": mean_ceiling,
        "p95_ceiling": p95_ceiling,
        "mean_interval_width": mean_width,
        "p95_interval_width": p95_width,
        "maximum_interval_width": maximum_width,
        "mean_ceiling_excess_over_oracle": mean_excess,
        "p95_ceiling_excess_over_oracle": p95_excess,
        "maximum_ceiling_excess_over_oracle": maximum_excess,
    }
    return key, public, risk


def summarize_predecessor_model_v2(
    report: Mapping[str, Any],
    report_sha256: str,
) -> dict[str, Any]:
    """Validate and project the completed v2 predecessor without rewriting it."""

    _require(report.get("schema_version") == "1.0", "unsupported model-backed report schema")
    _require(
        report.get("experiment_id") == PREDECESSOR_MODEL_EXPERIMENT_ID,
        "unexpected predecessor model-backed experiment id",
    )
    authority = _mapping(report.get("authority"), "model authority")
    _require(authority.get("experimental_only") is True, "model evidence must remain experimental")
    _require(authority.get("benchmark_population_conditional") is True, "model evidence lost finite-population scope")
    for field in ("authorization_eligible", "authorization_granted", "real_world_privacy_claimed"):
        _require(authority.get(field) is False, f"model authority field {field} must remain false")
    _require(authority.get("decision") == "no_release_authorization", "model authority decision changed")
    _require(report.get("decision") == "no_release_authorization", "model experiment granted release authorization")

    acceptance = _mapping(report.get("acceptance"), "model acceptance")
    criteria = _mapping(acceptance.get("criteria"), "model acceptance criteria")
    _require(
        set(criteria) == PREDECESSOR_MODEL_ACCEPTANCE_CRITERIA,
        "predecessor model acceptance family changed",
    )
    _require(all(type(value) is bool for value in criteria.values()), "model acceptance criteria must be booleans")
    acceptance_passed = all(criteria.values())
    _require(
        acceptance.get("passed") is acceptance_passed,
        "model aggregate acceptance disagrees with its registered criteria",
    )
    # Completed negative experimental outcomes remain publishable.  Integrity,
    # replay completeness, aggregate-only retention, and wrapper enforcement do
    # not become optional merely because a statistical acceptance target fails.
    for required_integrity in (
        "all_source_and_engine_replays_complete",
        "all_four_negative_controls_pass",
        "no_raw_scores_retained",
        "all_executable_wrapper_conformance_checks_pass",
    ):
        _require(criteria[required_integrity] is True, f"model integrity criterion failed: {required_integrity}")

    expected_keys = {(model, variant) for model in MODEL_IDENTITIES for variant in MODEL_VARIANTS}
    results = _sequence(report.get("results"), "model results")
    _require(len(results) == 6, "model primary result family is incomplete")
    public_results: dict[tuple[str, str], dict[str, Any]] = {}
    primary_risks: dict[tuple[str, str], Fraction] = {}
    for index, raw in enumerate(results):
        key, public, risk = _model_result(raw, index)
        _require(key not in public_results, "model primary result is duplicated")
        public_results[key] = public
        primary_risks[key] = risk
    _require(set(public_results) == expected_keys, "model primary result roster changed")

    repeated = _mapping(report.get("repeated_validation"), "model repeated validation")
    _require(_integer(repeated.get("replicates_per_model_variant"), "model registered repeats") == 200, "model registered repeat count changed")
    summaries = _sequence(repeated.get("summaries"), "model repeat summaries")
    _require(len(summaries) == 6, "model repeated-validation family is incomplete")
    public_repeats: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(summaries):
        key, public, risk = _repeat_summary_v2(raw, index)
        _require(key not in public_repeats, "model repeat summary is duplicated")
        _require(risk == primary_risks[key], "model repeat oracle differs from primary oracle")
        public_repeats[key] = public
    _require(set(public_repeats) == expected_keys, "model repeated-validation roster changed")

    checks = _mapping(report.get("checks"), "model checks")
    _require(type(checks.get("all_oracles_covered")) is bool, "model oracle coverage check is not boolean")
    _require(checks.get("all_source_and_engine_replays_complete") is True, "model replay completion check failed")
    full_engine = _mapping(checks.get("full_source_and_engine_replays"), "model full Engine replays")
    analyzer = _mapping(checks.get("production_analyzer_replays"), "model analyzer replays")
    _require(
        _integer(full_engine.get("completed"), "model completed Engine replays")
        == _integer(full_engine.get("expected"), "model expected Engine replays")
        == 6,
        "model full Engine replay family is incomplete",
    )
    _require(
        _integer(analyzer.get("completed"), "model completed analyzer replays")
        == _integer(analyzer.get("expected"), "model expected analyzer replays")
        == 1200,
        "model analyzer replay family is incomplete",
    )
    _require(_integer(checks.get("registered_model_count"), "model registered count") == 3, "model roster count changed")
    _require(_integer(checks.get("registered_family_count"), "model registered family count") == 6, "model family count changed")
    _require(checks.get("raw_scores_retained") is False, "model raw scores were retained")

    wrapper = _mapping(report.get("wrapper_conformance"), "model wrapper conformance")
    wrapper_results = _sequence(wrapper.get("results"), "model wrapper results")
    _require(wrapper.get("all_conformant") is True and len(wrapper_results) == 6, "model wrapper conformance family is incomplete")
    wrapper_keys: set[tuple[str, str]] = set()
    for raw in wrapper_results:
        value = _mapping(raw, "model wrapper result")
        key = _model_key(value, "model wrapper result")
        _require(value.get("conformant") is True and key not in wrapper_keys, "model wrapper conformance failed or duplicated")
        wrapper_keys.add(key)
    _require(wrapper_keys == expected_keys, "model wrapper conformance roster changed")

    controls = _sequence(report.get("negative_controls"), "model negative controls")
    _require(len(controls) == 4, "model negative-control family is incomplete")
    control_ids: set[str] = set()
    for raw in controls:
        control = _mapping(raw, "model negative control")
        control_id = control.get("control_id")
        _require(control_id in PREDECESSOR_MODEL_NEGATIVE_CONTROLS and control_id not in control_ids, "model negative-control roster changed")
        _require(control.get("executed") is True and control.get("passed") is True, "model negative control failed")
        control_ids.add(str(control_id))
    _require(control_ids == PREDECESSOR_MODEL_NEGATIVE_CONTROLS, "model negative controls are incomplete")

    ordered_results: list[dict[str, Any]] = []
    for model in MODEL_IDENTITIES:
        for variant in MODEL_VARIANTS:
            combined = dict(public_results[(model, variant)])
            combined["repeated_validation"] = public_repeats[(model, variant)]
            ordered_results.append(combined)

    observed_one_shot_coverage = sum(value["covers_oracle"] for value in ordered_results)
    one_shot_decision_counts = {
        verdict: sum(value["experimental_engine_verdict"] == verdict for value in ordered_results)
        for verdict in ("CLEAR", "INCONCLUSIVE", "BLOCK")
    }
    undercoverage_target_families = sum(
        value["repeated_validation"]["undercoverage_target_met"]
        for value in ordered_results
    )
    clear_target_families = sum(
        value["repeated_validation"]["clear_rate_target_met"]
        for value in ordered_results
    )
    failed_criteria = sorted(name for name, passed in criteria.items() if not passed)
    total_repeat_count = sum(
        value["repeated_validation"]["replicates"] for value in ordered_results
    )
    total_undercoverage_count = sum(
        value["repeated_validation"]["undercoverage_count"]
        for value in ordered_results
    )
    _require(
        criteria["all_six_oracle_risks_covered"] is (observed_one_shot_coverage == 6)
        and checks["all_oracles_covered"] is (observed_one_shot_coverage == 6),
        "model one-shot coverage aggregate disagrees with family results",
    )
    _require(
        criteria["all_six_one_shot_engine_decisions_clear"]
        is (one_shot_decision_counts["CLEAR"] == 6),
        "model one-shot decision aggregate disagrees with family results",
    )
    _require(
        criteria["all_six_simultaneous_undercoverage_bounds_meet_maximum"]
        is (undercoverage_target_families == 6),
        "model repeat undercoverage acceptance disagrees with family results",
    )
    _require(
        criteria["all_six_simultaneous_clear_rate_lowers_meet_minimum"]
        is (clear_target_families == 6),
        "model repeat CLEAR acceptance disagrees with family results",
    )

    return {
        "experiment_id": PREDECESSOR_MODEL_EXPERIMENT_ID,
        "source_report_sha256": report_sha256,
        "evidence_tier": "failed_historical_predecessor_model_conditional_public_data",
        "acceptance": {
            "passed": acceptance_passed,
            "status": (
                "all_registered_criteria_passed"
                if acceptance_passed
                else "registered_acceptance_not_met"
            ),
            "failed_criteria": failed_criteria,
            "criteria": dict(sorted(criteria.items())),
        },
        "experimental_only": True,
        "benchmark_population_conditional": True,
        "release_authorization": "none",
        "full_engine_replays": 6,
        "production_analyzer_replays": 1200,
        "full_engine_replay_limit": (
            "Integration evidence under an experimental attack-battery waiver; the waiver is not "
            "deployment-valid and the replay grants no authorization."
        ),
        "results": ordered_results,
        "headline": {
            "minimum_simultaneous_clear_rate_lower": min(
                value["repeated_validation"]["simultaneous_clear_rate_lower"]
                for value in ordered_results
            ),
            "maximum_simultaneous_undercoverage_upper": max(
                value["repeated_validation"]["simultaneous_undercoverage_upper"]
                for value in ordered_results
            ),
            "registered_family_count": 6,
            "total_repeat_count": total_repeat_count,
            "total_observed_undercoverage_count": total_undercoverage_count,
            "one_shot_oracle_coverage_families": observed_one_shot_coverage,
            "one_shot_engine_decision_counts": one_shot_decision_counts,
            "undercoverage_target_families": undercoverage_target_families,
            "clear_rate_target_families": clear_target_families,
            "undercoverage_target": 0.05,
            "clear_rate_lower_target": 0.95,
        },
        "scope_limit": (
            "Conditional on one newly trained artifact per registered model family, the frozen "
            "finite target audit pools, and the executable one-query closed wrapper. It is not "
            "evidence about ordinary prediction endpoints or another seed, dataset, or wrapper."
        ),
    }


def _model_result_v3(
    raw: Any,
    index: int,
) -> tuple[tuple[str, str], dict[str, Any], Fraction]:
    """Validate one v3 primary result, including wrapper-source evidence."""

    result = _mapping(raw, f"model-v3.results[{index}]")
    key, public, risk = _model_result(result, index)
    expected_erasure = Fraction(0) if key[1] == "raw_bins" else Fraction(9, 10)
    _require(
        _fraction(result.get("state_independent_erasure"), "v3 result erasure")
        == expected_erasure,
        "v3 result erasure does not match its registered variant",
    )
    equivalence = _mapping(
        result.get("wrapper_sampling_equivalence"),
        "v3 wrapper sampling equivalence",
    )
    _require(
        set(equivalence) == {"reference_schedule", "seed_replay", "all_passed"},
        "v3 wrapper sampling-equivalence schema changed",
    )
    for field in ("reference_schedule", "seed_replay"):
        state_checks = _mapping(
            equivalence.get(field), f"v3 wrapper equivalence {field}"
        )
        _require(
            state_checks == {"out": True, "in": True},
            f"v3 wrapper {field} equivalence failed or is incomplete",
        )
    _require(
        equivalence.get("all_passed") is True,
        "v3 wrapper sampling equivalence did not pass",
    )
    evidence = _mapping(
        result.get("wrapper_execution_evidence"),
        "v3 wrapper execution evidence",
    )
    _require(
        set(evidence) == {"path", "sha256", "engine_source_bound"},
        "v3 wrapper execution-evidence schema changed",
    )
    _require(
        evidence.get("path") == "wrapper-execution-evidence.json"
        and bool(HEX64.fullmatch(str(evidence.get("sha256", ""))))
        and evidence.get("engine_source_bound") is True,
        "v3 wrapper execution evidence is not source-bound",
    )
    public["state_independent_erasure_exact"] = _fraction_text(expected_erasure)
    public["wrapper_sampling_equivalence"] = True
    public["wrapper_execution_engine_source_bound"] = True
    return key, public, risk


def _repeat_summary_v3(
    raw: Any,
    index: int,
) -> tuple[tuple[str, str], dict[str, Any], Fraction]:
    """Validate count/rate/bound and role semantics for one v3 repeat family."""

    summary = _mapping(raw, f"model-v3.repeated_validation.summaries[{index}]")
    key = _model_key(summary, "v3 repeat summary")
    _, expected_family, _ = MODEL_IDENTITIES[key[0]]
    _require(
        summary.get("model_family") == expected_family,
        "v3 repeat summary model family changed",
    )
    replicates = _integer(summary.get("replicates"), "v3 repeat count", minimum=1)
    trials = _integer(summary.get("trials_per_state"), "v3 repeat trials", minimum=1)
    _require(
        replicates == 200 and trials == 5000,
        "v3 repeated-validation cell is incomplete",
    )
    _require(
        _integer(
            summary.get("meta_simultaneous_bound_count"),
            "v3 meta simultaneous bound count",
        )
        == 18,
        "v3 repeat family does not use all 18 registered meta endpoints",
    )
    _require(
        summary.get("meta_multiplicity_method") == META_MULTIPLICITY_METHOD,
        "v3 meta multiplicity method changed",
    )

    risk = _fraction(summary.get("true_exact_oracle_risk"), "v3 repeat oracle risk")
    tolerance = Fraction(13, 20)
    expected_direction = (
        "CLEAR" if risk < tolerance else "BLOCK" if risk > tolerance else "AT_BOUNDARY"
    )
    _require(
        summary.get("expected_direction") == expected_direction,
        "v3 expected decision direction disagrees with oracle risk",
    )
    margin = abs(risk - tolerance)
    observed_margin = _fraction(
        summary.get("absolute_margin_from_tolerance"),
        "v3 absolute margin",
    )
    observed_margin_decimal = _probability(
        summary.get("absolute_margin_from_tolerance_decimal"),
        "v3 absolute margin decimal",
    )
    _require(
        observed_margin == margin
        and _close(observed_margin_decimal, float(margin)),
        "v3 registered margin does not equal |R* - tolerance|",
    )
    margin_eligible = margin >= Fraction(1, 10)
    _require(
        summary.get("margin_eligible_for_resolution_claim") is margin_eligible,
        "v3 margin eligibility does not apply the inclusive 0.10 threshold",
    )

    decisions = _mapping(summary.get("decision_counts"), "v3 decision counts")
    _require(
        set(decisions) == {"CLEAR", "HOLD", "BLOCK"},
        "v3 decision-count family changed",
    )
    decision_counts = {
        name: _integer(decisions[name], f"v3 {name} count")
        for name in ("CLEAR", "HOLD", "BLOCK")
    }
    _require(
        sum(decision_counts.values()) == replicates,
        "v3 decision counts do not sum to the registered repeats",
    )

    def count_rate(
        count_field: str,
        rate_field: str,
        label: str,
    ) -> tuple[int, float]:
        count = _integer(summary.get(count_field), f"v3 {label} count")
        rate = _probability(summary.get(rate_field), f"v3 {label} rate")
        _require(count <= replicates, f"v3 {label} count exceeds repeats")
        _require(
            _close(rate, count / replicates),
            f"v3 {label} count/rate mismatch",
        )
        return count, rate

    under_count, under_rate = count_rate(
        "undercoverage_count", "undercoverage_rate", "undercoverage"
    )
    wrong_count, wrong_rate = count_rate(
        "wrong_direction_count", "wrong_direction_rate", "wrong-direction"
    )
    correct_count, correct_rate = count_rate(
        "correct_direction_count", "correct_direction_rate", "correct-direction"
    )
    clear_count, clear_rate = count_rate("clear_count", "clear_rate", "CLEAR")
    _require(
        clear_count == decision_counts["CLEAR"],
        "v3 CLEAR count disagrees with decision-count family",
    )
    if expected_direction == "CLEAR":
        _require(
            (correct_count, wrong_count)
            == (decision_counts["CLEAR"], decision_counts["BLOCK"]),
            "v3 below-tolerance correct/wrong direction counts are inconsistent",
        )
    elif expected_direction == "BLOCK":
        _require(
            (correct_count, wrong_count)
            == (decision_counts["BLOCK"], decision_counts["CLEAR"]),
            "v3 above-tolerance correct/wrong direction counts are inconsistent",
        )
    else:
        _require(
            correct_count == wrong_count == 0,
            "v3 boundary family must be non-directional",
        )

    under_upper = _probability(
        summary.get("simultaneous_clopper_pearson_undercoverage_upper"),
        "v3 simultaneous undercoverage upper",
    )
    wrong_upper = _probability(
        summary.get("simultaneous_clopper_pearson_wrong_direction_upper"),
        "v3 simultaneous wrong-direction upper",
    )
    correct_lower = _probability(
        summary.get("simultaneous_clopper_pearson_correct_direction_lower"),
        "v3 simultaneous correct-direction lower",
    )
    _require(
        under_upper + 1e-12 >= under_rate,
        "v3 undercoverage upper is below its count rate",
    )
    _require(
        wrong_upper + 1e-12 >= wrong_rate,
        "v3 wrong-direction upper is below its count rate",
    )
    _require(
        correct_lower <= correct_rate + 1e-12,
        "v3 correct-direction lower exceeds its count rate",
    )

    mean_ceiling = _probability(summary.get("mean_ceiling"), "v3 mean ceiling")
    p95_ceiling = _probability(summary.get("p95_ceiling"), "v3 p95 ceiling")
    mean_width = _probability(
        summary.get("mean_interval_width"), "v3 mean interval width"
    )
    p95_width = _probability(
        summary.get("p95_interval_width"), "v3 p95 interval width"
    )
    maximum_width = _probability(
        summary.get("maximum_interval_width"), "v3 maximum interval width"
    )
    mean_excess = _number(
        summary.get("mean_ceiling_excess_over_oracle"),
        "v3 mean ceiling excess",
        minimum=-1.0,
        maximum=1.0,
    )
    p95_excess = _number(
        summary.get("p95_ceiling_excess_over_oracle"),
        "v3 p95 ceiling excess",
        minimum=-1.0,
        maximum=1.0,
    )
    maximum_excess = _number(
        summary.get("maximum_ceiling_excess_over_oracle"),
        "v3 maximum ceiling excess",
        minimum=-1.0,
        maximum=1.0,
    )
    _require(
        _close(mean_ceiling - float(risk), mean_excess),
        "v3 mean ceiling/excess mismatch",
    )
    _require(
        mean_width <= maximum_width + 1e-12
        and p95_width <= maximum_width + 1e-12
        and p95_ceiling + 1e-12 >= mean_ceiling,
        "v3 interval summary order is inconsistent",
    )
    _require(
        mean_excess <= maximum_excess + 1e-12
        and p95_excess <= maximum_excess + 1e-12,
        "v3 ceiling-excess summary order is inconsistent",
    )
    _require(
        summary.get("every_production_analyzer_replay_completed") is True,
        "v3 analyzer replay family is incomplete",
    )
    _require(
        summary.get("every_wrapper_sampling_equivalence_check_passed") is True,
        "v3 repeat wrapper-sampling equivalence failed",
    )

    correct_target_met = correct_lower >= 0.95
    public = {
        "replicates": replicates,
        "expected_direction": expected_direction,
        "absolute_margin_from_tolerance_exact": _fraction_text(margin),
        "absolute_margin_from_tolerance": float(margin),
        "margin_eligible_for_resolution_claim": margin_eligible,
        "decision_counts": decision_counts,
        "undercoverage_count": under_count,
        "undercoverage_rate": under_rate,
        "simultaneous_undercoverage_upper": under_upper,
        "undercoverage_target_met": under_upper <= 0.05,
        "wrong_direction_count": wrong_count,
        "wrong_direction_rate": wrong_rate,
        "simultaneous_wrong_direction_upper": wrong_upper,
        "wrong_direction_target_met": wrong_upper <= 0.05,
        "correct_direction_count": correct_count,
        "correct_direction_rate": correct_rate,
        "simultaneous_correct_direction_lower": correct_lower,
        "correct_direction_target_applicable": margin_eligible,
        "correct_direction_target_met": (
            correct_target_met if margin_eligible else None
        ),
        "mean_ceiling": mean_ceiling,
        "p95_ceiling": p95_ceiling,
        "mean_interval_width": mean_width,
        "p95_interval_width": p95_width,
        "maximum_interval_width": maximum_width,
        "mean_ceiling_excess_over_oracle": mean_excess,
        "p95_ceiling_excess_over_oracle": p95_excess,
        "maximum_ceiling_excess_over_oracle": maximum_excess,
        "wrapper_sampling_equivalence": True,
    }
    return key, public, risk


def summarize_model_v3(
    report: Mapping[str, Any],
    report_sha256: str,
) -> dict[str, Any]:
    """Validate and project the frozen v3 role-aware model experiment."""

    _require(report.get("schema_version") == "1.0", "unsupported v3 model report schema")
    _require(
        report.get("experiment_id") == MODEL_EXPERIMENT_ID,
        "unexpected v3 model-backed experiment id",
    )
    authority = _mapping(report.get("authority"), "v3 model authority")
    _require(
        authority.get("experimental_only") is True
        and authority.get("benchmark_population_conditional") is True,
        "v3 model evidence lost its experimental finite-population scope",
    )
    for field in (
        "authorization_eligible",
        "authorization_granted",
        "real_world_privacy_claimed",
    ):
        _require(authority.get(field) is False, f"v3 authority field {field} must remain false")
    _require(
        authority.get("decision") == "no_release_authorization"
        and report.get("decision") == "no_release_authorization",
        "v3 experiment granted release authority",
    )

    acceptance = _mapping(report.get("acceptance"), "v3 acceptance")
    criteria = _mapping(acceptance.get("criteria"), "v3 acceptance criteria")
    _require(set(criteria) == MODEL_ACCEPTANCE_CRITERIA, "v3 acceptance family changed")
    _require(all(type(value) is bool for value in criteria.values()), "v3 acceptance criteria must be booleans")
    acceptance_passed = all(criteria.values())
    _require(
        acceptance.get("passed") is acceptance_passed,
        "v3 aggregate acceptance disagrees with its registered criteria",
    )
    for required_integrity in (
        "all_source_engine_and_repeat_replays_complete",
        "all_five_negative_controls_pass",
        "no_raw_scores_retained",
        "all_executable_wrapper_conformance_and_sampling_equivalence_checks_pass",
    ):
        _require(
            criteria[required_integrity] is True,
            f"v3 integrity criterion failed: {required_integrity}",
        )

    expected_keys = {
        (model, variant)
        for model in MODEL_IDENTITIES
        for variant in MODEL_VARIANTS
    }
    results = _sequence(report.get("results"), "v3 model results")
    _require(len(results) == 6, "v3 primary result family is incomplete")
    public_results: dict[tuple[str, str], dict[str, Any]] = {}
    primary_risks: dict[tuple[str, str], Fraction] = {}
    for index, raw in enumerate(results):
        key, public, risk = _model_result_v3(raw, index)
        _require(key not in public_results, "v3 primary result is duplicated")
        public_results[key] = public
        primary_risks[key] = risk
    _require(set(public_results) == expected_keys, "v3 primary result roster changed")

    repeated = _mapping(report.get("repeated_validation"), "v3 repeated validation")
    _require(
        _integer(repeated.get("replicates_per_model_variant"), "v3 registered repeats")
        == 200,
        "v3 registered repeat count changed",
    )
    _require(
        _integer(
            repeated.get("meta_simultaneous_bound_count"),
            "v3 report meta simultaneous bound count",
        )
        == 18,
        "v3 report does not declare all 18 meta endpoints",
    )
    summaries = _sequence(repeated.get("summaries"), "v3 repeat summaries")
    _require(len(summaries) == 6, "v3 repeated-validation family is incomplete")
    public_repeats: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(summaries):
        key, public, risk = _repeat_summary_v3(raw, index)
        _require(key not in public_repeats, "v3 repeat summary is duplicated")
        _require(risk == primary_risks[key], "v3 repeat oracle differs from primary oracle")
        public_repeats[key] = public
    _require(set(public_repeats) == expected_keys, "v3 repeat roster changed")

    checks = _mapping(report.get("checks"), "v3 checks")
    _require(
        type(checks.get("all_oracles_covered")) is bool,
        "v3 oracle coverage check is not boolean",
    )
    _require(
        checks.get("all_source_engine_and_repeat_replays_complete") is True,
        "v3 source/Engine/repeat replay family is incomplete",
    )
    full_engine = _mapping(
        checks.get("full_source_and_engine_replays"), "v3 full Engine replays"
    )
    analyzer = _mapping(
        checks.get("production_analyzer_replays"), "v3 analyzer replays"
    )
    _require(
        _integer(full_engine.get("completed"), "v3 completed Engine replays")
        == _integer(full_engine.get("expected"), "v3 expected Engine replays")
        == 6,
        "v3 full Engine replay family is incomplete",
    )
    _require(
        _integer(analyzer.get("completed"), "v3 completed analyzer replays")
        == _integer(analyzer.get("expected"), "v3 expected analyzer replays")
        == 1200,
        "v3 analyzer replay family is incomplete",
    )
    _require(
        _integer(checks.get("registered_model_count"), "v3 model count") == 3
        and _integer(checks.get("registered_family_count"), "v3 family count") == 6,
        "v3 registered model/family count changed",
    )
    _require(checks.get("raw_scores_retained") is False, "v3 raw scores were retained")

    wrapper = _mapping(report.get("wrapper_conformance"), "v3 wrapper conformance")
    wrapper_results = _sequence(wrapper.get("results"), "v3 wrapper results")
    _require(
        wrapper.get("all_conformant") is True and len(wrapper_results) == 6,
        "v3 wrapper conformance family is incomplete",
    )
    wrapper_keys: set[tuple[str, str]] = set()
    for raw in wrapper_results:
        value = _mapping(raw, "v3 wrapper result")
        key = _model_key(value, "v3 wrapper result")
        _require(
            key not in wrapper_keys and value.get("conformant") is True,
            "v3 wrapper conformance failed or duplicated",
        )
        interface = _mapping(value.get("interface"), "v3 wrapper interface")
        expected_erasure = Fraction(0) if key[1] == "raw_bins" else Fraction(9, 10)
        _require(
            _fraction(
                interface.get("state_independent_erasure"),
                "v3 conformance erasure",
            )
            == expected_erasure,
            "v3 conformance result is bound to another erasure variant",
        )
        wrapper_checks = _sequence(value.get("checks"), "v3 wrapper checks")
        observed_check_ids = {
            str(_mapping(item, "v3 wrapper check").get("check_id"))
            for item in wrapper_checks
        }
        _require(
            len(wrapper_checks) == len(WRAPPER_CONFORMANCE_CHECK_IDS)
            and observed_check_ids == WRAPPER_CONFORMANCE_CHECK_IDS
            and all(
                _mapping(item, "v3 wrapper check").get("passed") is True
                for item in wrapper_checks
            ),
            "v3 wrapper conformance checks are incomplete or failed",
        )
        wrapper_keys.add(key)
    _require(wrapper_keys == expected_keys, "v3 wrapper conformance roster changed")

    controls = _sequence(report.get("negative_controls"), "v3 negative controls")
    control_ids: set[str] = set()
    for raw in controls:
        control = _mapping(raw, "v3 negative control")
        control_id = control.get("control_id")
        _require(
            control_id in MODEL_NEGATIVE_CONTROLS
            and control_id not in control_ids
            and control.get("executed") is True
            and control.get("passed") is True,
            "v3 negative control failed, duplicated, or changed",
        )
        control_ids.add(str(control_id))
    _require(
        len(controls) == 5 and control_ids == MODEL_NEGATIVE_CONTROLS,
        "v3 negative-control family is incomplete",
    )

    erasure_rows = _sequence(report.get("erasure_comparisons"), "v3 erasure comparisons")
    _require(len(erasure_rows) == 3, "v3 erasure comparison family is incomplete")
    erasure_models: set[str] = set()
    public_erasure: list[dict[str, Any]] = []
    for raw in erasure_rows:
        row = _mapping(raw, "v3 erasure comparison")
        model = row.get("collector_model")
        _require(
            model in MODEL_IDENTITIES and model not in erasure_models,
            "v3 erasure comparison roster changed",
        )
        raw_risk = _fraction(row.get("raw_oracle_risk"), "v3 raw erasure risk")
        erased_risk = _fraction(
            row.get("erased_oracle_risk"), "v3 erased oracle risk"
        )
        expected_erased = Fraction(1, 2) + (raw_risk - Fraction(1, 2)) / 10
        _require(
            erased_risk == expected_erased
            and _fraction(
                row.get("expected_erased_oracle_risk"),
                "v3 expected erased risk",
            )
            == expected_erased
            and row.get("exact_erasure_contraction_identity") is True
            and row.get("oracle_risk_nonincreasing") is True,
            "v3 exact 0.9 erasure contraction identity failed",
        )
        _require(
            raw_risk == primary_risks[(str(model), "raw_bins")]
            and erased_risk == primary_risks[(str(model), "erasure_0p9")],
            "v3 erasure comparison disagrees with primary oracle risks",
        )
        public_erasure.append({
            "collector_model": model,
            "model_label": MODEL_IDENTITIES[str(model)][0],
            "raw_oracle_risk": float(raw_risk),
            "erased_oracle_risk": float(erased_risk),
            "identity": "R_erased = 0.5 + 0.1 * (R_raw - 0.5)",
            "exact_identity_holds": True,
        })
        erasure_models.add(str(model))
    _require(erasure_models == set(MODEL_IDENTITIES), "v3 erasure models are incomplete")

    ordered_results: list[dict[str, Any]] = []
    for model in MODEL_IDENTITIES:
        for variant in MODEL_VARIANTS:
            combined = dict(public_results[(model, variant)])
            combined["repeated_validation"] = public_repeats[(model, variant)]
            ordered_results.append(combined)

    one_shot_coverage = sum(value["covers_oracle"] for value in ordered_results)
    undercoverage_families = sum(
        value["repeated_validation"]["undercoverage_target_met"]
        for value in ordered_results
    )
    wrong_direction_families = sum(
        value["repeated_validation"]["wrong_direction_target_met"]
        for value in ordered_results
    )
    margin_eligible_rows = [
        value
        for value in ordered_results
        if value["repeated_validation"]["margin_eligible_for_resolution_claim"]
    ]
    resolved_rows = [
        value
        for value in margin_eligible_rows
        if value["repeated_validation"]["correct_direction_target_met"] is True
    ]
    all_eligible_resolved = bool(margin_eligible_rows) and len(resolved_rows) == len(
        margin_eligible_rows
    )

    decision_evaluation = _mapping(
        report.get("decision_evaluation"), "v3 decision evaluation"
    )
    _require(
        _mapping(
            decision_evaluation.get("wrong_direction_definition"),
            "v3 wrong-direction definition",
        )
        == {
            "oracle_below_tolerance": "BLOCK",
            "oracle_above_tolerance": "CLEAR",
            "oracle_equal_tolerance": "none; any result is non-directional",
            "hold": "never a wrong-direction decision",
        },
        "v3 wrong-direction role definition changed",
    )
    _require(
        _fraction(decision_evaluation.get("margin_threshold"), "v3 margin threshold")
        == Fraction(1, 10),
        "v3 decision evaluation margin threshold changed",
    )
    eligible_names = {
        f"{value['collector_model']}/{value['variant_id']}"
        for value in margin_eligible_rows
    }
    resolved_names = {
        f"{value['collector_model']}/{value['variant_id']}"
        for value in resolved_rows
    }
    reported_eligible = _sequence(
        decision_evaluation.get("eligible_families"), "v3 eligible families"
    )
    reported_resolved = _sequence(
        decision_evaluation.get("resolved_families"), "v3 resolved families"
    )
    _require(
        all(isinstance(value, str) for value in (*reported_eligible, *reported_resolved)),
        "v3 decision-evaluation family identifiers must be strings",
    )
    _require(
        _integer(
            decision_evaluation.get("margin_eligible_family_count"),
            "v3 eligible family count",
        )
        == len(margin_eligible_rows)
        and _integer(
            decision_evaluation.get("resolved_margin_family_count"),
            "v3 resolved family count",
        )
        == len(resolved_rows)
        and _integer(
            decision_evaluation.get("minimum_required_resolved_families"),
            "v3 minimum resolved families",
        )
        == 3
        and len(reported_eligible) == len(eligible_names)
        and set(reported_eligible) == eligible_names
        and len(reported_resolved) == len(resolved_names)
        and set(reported_resolved) == resolved_names,
        "v3 decision-evaluation aggregate disagrees with family summaries",
    )

    derived_criteria = {
        "all_six_oracle_risks_covered": one_shot_coverage == 6,
        "all_source_engine_and_repeat_replays_complete": True,
        "all_five_negative_controls_pass": True,
        "no_raw_scores_retained": True,
        "exact_erasure_contraction_identity_holds": len(public_erasure) == 3,
        "all_six_simultaneous_undercoverage_bounds_meet_maximum": undercoverage_families == 6,
        "all_six_simultaneous_wrong_direction_bounds_meet_maximum": wrong_direction_families == 6,
        "all_margin_eligible_correct_decision_lowers_meet_minimum": all_eligible_resolved,
        "at_least_three_margin_eligible_families_resolve": len(resolved_rows) >= 3,
        "all_executable_wrapper_conformance_and_sampling_equivalence_checks_pass": True,
    }
    _require(
        dict(criteria) == derived_criteria,
        "v3 registered acceptance disagrees with recomputed role-aware results",
    )
    _require(
        checks["all_oracles_covered"] is derived_criteria["all_six_oracle_risks_covered"],
        "v3 oracle coverage check disagrees with primary results",
    )

    total_repeats = sum(value["repeated_validation"]["replicates"] for value in ordered_results)
    total_undercoverage = sum(
        value["repeated_validation"]["undercoverage_count"]
        for value in ordered_results
    )
    total_wrong_direction = sum(
        value["repeated_validation"]["wrong_direction_count"]
        for value in ordered_results
    )
    failed_criteria = sorted(name for name, passed in criteria.items() if not passed)
    eligible_lowers = [
        value["repeated_validation"]["simultaneous_correct_direction_lower"]
        for value in margin_eligible_rows
    ]
    below_tolerance = sum(
        value["oracle_risk"] < 0.65 for value in ordered_results
    )
    above_tolerance = sum(
        value["oracle_risk"] > 0.65 for value in ordered_results
    )
    at_tolerance = len(ordered_results) - below_tolerance - above_tolerance
    return {
        "experiment_id": MODEL_EXPERIMENT_ID,
        "source_report_sha256": report_sha256,
        "evidence_tier": "role_aware_model_conditional_public_data",
        "acceptance": {
            "passed": acceptance_passed,
            "status": (
                "all_registered_criteria_passed"
                if acceptance_passed
                else "registered_acceptance_not_met"
            ),
            "failed_criteria": failed_criteria,
            "criteria": dict(sorted(criteria.items())),
        },
        "experimental_only": True,
        "benchmark_population_conditional": True,
        "release_authorization": "none",
        "meta_simultaneous_bound_count": 18,
        "full_engine_replays": 6,
        "production_analyzer_replays": 1200,
        "full_engine_replay_limit": (
            "Integration evidence under an experimental attack-battery waiver; the waiver is not "
            "deployment-valid and the replay grants no authorization."
        ),
        "decision_protocol": {
            "tolerance": 0.65,
            "minimum_absolute_margin_for_resolution": 0.10,
            "minimum_resolved_margin_eligible_families": 3,
            "wrong_direction_upper_target": 0.05,
            "correct_direction_lower_target": 0.95,
            "undercoverage_upper_target": 0.05,
        },
        "results": ordered_results,
        "erasure_comparisons": public_erasure,
        "headline": {
            "registered_family_count": 6,
            "total_repeat_count": total_repeats,
            "total_observed_undercoverage_count": total_undercoverage,
            "total_observed_wrong_direction_count": total_wrong_direction,
            "one_shot_oracle_coverage_families": one_shot_coverage,
            "undercoverage_target_families": undercoverage_families,
            "wrong_direction_target_families": wrong_direction_families,
            "below_tolerance_family_count": below_tolerance,
            "above_tolerance_family_count": above_tolerance,
            "at_tolerance_family_count": at_tolerance,
            "margin_eligible_family_count": len(margin_eligible_rows),
            "resolved_margin_family_count": len(resolved_rows),
            "minimum_eligible_correct_direction_lower": (
                min(eligible_lowers) if eligible_lowers else None
            ),
            "maximum_simultaneous_undercoverage_upper": max(
                value["repeated_validation"]["simultaneous_undercoverage_upper"]
                for value in ordered_results
            ),
            "maximum_simultaneous_wrong_direction_upper": max(
                value["repeated_validation"]["simultaneous_wrong_direction_upper"]
                for value in ordered_results
            ),
        },
        "scope_limit": (
            "Conditional on one newly trained artifact per registered model family, the frozen "
            "finite target audit pools, and the source-bound one-query wrapper. Resolution claims "
            "apply only when |R* - 0.65| >= 0.10. The observed v3 roster contains no risk above "
            "0.65, so model-backed BLOCK power is not established."
        ),
    }


def _assert_publication_safe(value: Any) -> None:
    if isinstance(value, dict):
        overlap = FORBIDDEN_PUBLIC_KEYS.intersection(value)
        _require(not overlap, f"publication projection contains forbidden fields: {sorted(overlap)}")
        for item in value.values():
            _assert_publication_safe(item)
    elif isinstance(value, list):
        for item in value:
            _assert_publication_safe(item)
    elif isinstance(value, float):
        _require(math.isfinite(value), "publication projection contains a non-finite number")


def build_publication_summary(
    known_report: Mapping[str, Any],
    model_report: Mapping[str, Any],
    *,
    known_report_sha256: str,
    model_report_sha256: str,
    predecessor_model_report: Mapping[str, Any] | None = None,
    predecessor_model_report_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate both reports and create the aggregate-only public projection."""

    _require(
        bool(HEX64.fullmatch(known_report_sha256))
        and bool(HEX64.fullmatch(model_report_sha256)),
        "source report digests must be lowercase SHA-256 strings",
    )
    _require(
        (predecessor_model_report is None)
        == (predecessor_model_report_sha256 is None),
        "predecessor report and digest must be supplied together",
    )
    if predecessor_model_report_sha256 is not None:
        _require(
            bool(HEX64.fullmatch(predecessor_model_report_sha256)),
            "predecessor report digest must be lowercase SHA-256",
        )
    known = summarize_known(known_report, known_report_sha256)
    model = summarize_model_v3(model_report, model_report_sha256)
    predecessor = None
    if predecessor_model_report is not None and predecessor_model_report_sha256 is not None:
        predecessor = summarize_predecessor_model_v2(
            predecessor_model_report,
            predecessor_model_report_sha256,
        )
        _require(
            _mapping(predecessor["acceptance"], "predecessor acceptance")["passed"]
            is False,
            "v2 predecessor history must retain its registered failed acceptance",
        )
    model_acceptance = _mapping(model["acceptance"], "model publication acceptance")
    model_passed = model_acceptance["passed"] is True
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "summary_id": SUMMARY_ID,
        "status": (
            "all_registered_acceptance_criteria_passed"
            if model_passed
            else "controlled_passed_model_acceptance_not_met"
        ),
        "interpretation": {
            "proof": {
                "status": "not_established_by_experiments",
                "statement": (
                    "Empirical repetition cannot prove a universal ceiling theorem or deployment-level "
                    "coverage. Formal assumptions and proofs must be audited separately."
                ),
            },
            "controlled_evidence": {
                "status": "accepted",
                "experiment_id": KNOWN_EXPERIMENT_ID,
                "statement": (
                    "The registered estimator covered exact risk and supported CLEAR/HOLD/BLOCK decisions "
                    "on the complete predeclared controlled finite-channel family."
                ),
            },
            "model_conditional_evidence": {
                "status": (
                    "all_registered_criteria_passed"
                    if model_passed
                    else "registered_acceptance_not_met"
                ),
                "experiment_id": MODEL_EXPERIMENT_ID,
                "statement": (
                    "The complete registered model-backed run is reported without promoting a failed "
                    "criterion. Per-family coverage and decision-usefulness metrics determine which "
                    "claims passed, conditional on the frozen artifacts, pools, and wrapper."
                ),
            },
        },
        "metric_semantics": {
            "ceiling_coverage": "frequency with which the reported upper bound U is at least exact risk R*",
            "undercoverage": "failure event U < R*; its simultaneous upper confidence bound measures soundness uncertainty",
            "interval_width": "U - L; smaller is more decision-useful when coverage is preserved",
            "ceiling_excess": "U - R*; smaller nonnegative values are tighter",
            "decision_rule": "CLEAR if U <= tolerance; BLOCK if L > tolerance; otherwise HOLD",
            "wrong_direction": "BLOCK below tolerance or CLEAR above tolerance; HOLD is conservative and never wrong-direction",
            "correct_direction": "CLEAR below tolerance or BLOCK above tolerance; the resolution target applies only at absolute margin >= 0.10",
        },
        "decision_tolerance": 0.65,
        "known_channel": known,
        "model_backed": model,
        "release_authorization": "none",
    }
    if predecessor is not None:
        summary["predecessor_model_backed_v2"] = predecessor
        summary["interpretation"]["historical_predecessor"] = {
            "status": "registered_acceptance_not_met",
            "experiment_id": PREDECESSOR_MODEL_EXPERIMENT_ID,
            "statement": (
                "The v2 result remains an explicitly failed predecessor and is not rewritten "
                "as v3 evidence. V3 uses a prospectively registered role-aware endpoint family."
            ),
        }
    _assert_publication_safe(summary)
    return summary


def _percent(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def _decimal(value: float) -> str:
    return f"{value:.4f}"


def render_markdown(summary: Mapping[str, Any], svg_name: str = "ceiling-validation.svg") -> str:
    """Render the validated v3 projection and optional v2 history."""

    known = _mapping(summary["known_channel"], "summary known channel")
    model = _mapping(summary["model_backed"], "summary model backed")
    known_headline = _mapping(known["headline"], "known headline")
    model_headline = _mapping(model["headline"], "model headline")
    model_acceptance = _mapping(model["acceptance"], "model acceptance")
    failed = ", ".join(str(value) for value in model_acceptance["failed_criteria"])
    if model_acceptance["passed"] is True:
        opening = "The controlled study and the prospectively registered v3 model-backed study passed their scoped acceptance criteria."
        current_status = "All registered criteria passed"
    else:
        opening = (
            "The controlled study passed; the complete v3 model-backed study did not meet "
            f"its registered acceptance ({failed}). The negative result is reported without promotion."
        )
        current_status = "Registered acceptance not met"
    minimum_lower = model_headline["minimum_eligible_correct_direction_lower"]
    minimum_lower_text = "n/a" if minimum_lower is None else _percent(float(minimum_lower))
    lines = [
        "# Ceiling experiment results",
        "",
        f"{opening} These experiments are not a universal proof and grant no release authorization.",
        "",
        f"![Ceiling validation intervals]({svg_name})",
        "",
        "## Claim boundary",
        "",
        "| Evidence level | Result | Valid scope |",
        "| --- | --- | --- |",
        "| Mathematical or universal proof | Not established | Requires a separate formal-assumption and proof audit |",
        "| Controlled exact-ground-truth evidence | Accepted | Complete preregistered synthetic finite-channel family |",
        f"| V3 role-aware model-conditional evidence | {current_status} | Frozen artifacts, target pools, and source-bound one-query wrappers |",
        "",
        "## Headline metrics",
        "",
        "| Experiment | Soundness | Role-aware decision behavior | Execution |",
        "| --- | --- | --- | --- |",
        (
            "| Controlled exact-ground-truth | "
            f"{known_headline['primary_undercoverage_count']}/{known_headline['primary_repeat_count']} observed undercoverage; simultaneous upper "
            f"{_percent(float(known_headline['maximum_simultaneous_primary_undercoverage_upper']))} | "
            "400/400 correct decisions for each safe/boundary/unsafe role | "
            f"{known['primary_analyzer_replays']} analyzer + {known['full_engine_replays']} Engine replays |"
        ),
        (
            "| V3 model-conditional public data | "
            f"{model_headline['total_observed_undercoverage_count']}/{model_headline['total_repeat_count']} observed undercoverage; "
            f"{model_headline['undercoverage_target_families']}/6 families met the simultaneous upper target | "
            f"{model_headline['total_observed_wrong_direction_count']}/{model_headline['total_repeat_count']} wrong-direction decisions; "
            f"{model_headline['wrong_direction_target_families']}/6 met its upper target; "
            f"{model_headline['resolved_margin_family_count']}/{model_headline['margin_eligible_family_count']} margin-eligible families resolved; minimum eligible lower {minimum_lower_text} | "
            f"{model['production_analyzer_replays']} analyzer + {model['full_engine_replays']} Engine replays; 18 simultaneous meta endpoints |"
        ),
        "",
        "> Engine replays are integration evidence under experimental attack-battery waivers. The waivers are not deployment-valid.",
        "",
        "## Controlled exact-ground-truth primary cells",
        "",
        "| Scenario | Role | R* | Mean [L, U] | Width | Coverage | Correct decision lower |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for raw in _sequence(known["primary_results"], "known primary results"):
        value = _mapping(raw, "known primary row")
        lines.append(
            f"| {value['model_label']} | {str(value['risk_role']).upper()} | {_decimal(float(value['true_risk']))} | "
            f"[{_decimal(float(value['mean_floor']))}, {_decimal(float(value['mean_ceiling']))}] | "
            f"{_decimal(float(value['mean_interval_width']))} | {_percent(float(value['ceiling_coverage_rate']))} | "
            f"{_percent(float(value['simultaneous_correct_decision_lower']))} |"
        )
    lines.extend([
        "",
        "## V3 role-aware model-conditional cells",
        "",
        "Resolution is preregistered only for families with `|R* - 0.65| >= 0.10`. HOLD is conservative and is never counted as a wrong-direction decision.",
        "",
        (
            f"All {model_headline['below_tolerance_family_count']} v3 oracle risks were below the 0.65 tolerance; "
            "v3 therefore tests safe-side resolution and conservative HOLD, not model-backed BLOCK power. "
            "Unsafe-side BLOCK behavior is demonstrated only by the controlled R*=0.80 channel."
            if model_headline["above_tolerance_family_count"] == 0
            else (
                f"V3 contains {model_headline['below_tolerance_family_count']} below-tolerance and "
                f"{model_headline['above_tolerance_family_count']} above-tolerance families."
            )
        ),
        "",
        "| Model / wrapper | R* | Margin / role | One-shot [L, U] | Decisions C/H/B | Undercoverage upper | Wrong-direction upper | Correct-direction lower | Registered targets |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for raw in _sequence(model["results"], "v3 model results"):
        value = _mapping(raw, "v3 model result")
        repeated = _mapping(value["repeated_validation"], "v3 repeated result")
        eligible = repeated["margin_eligible_for_resolution_claim"] is True
        resolution = (
            ("PASS" if repeated["correct_direction_target_met"] else "FAIL")
            if eligible
            else "N/A (margin < 0.10)"
        )
        counts = _mapping(repeated["decision_counts"], "v3 decision counts")
        lines.append(
            f"| {value['model_label']} — {value['variant_label']} | {_decimal(float(value['oracle_risk']))} | "
            f"{_decimal(float(repeated['absolute_margin_from_tolerance']))} / {repeated['expected_direction']} | "
            f"[{_decimal(float(value['production_floor']))}, {_decimal(float(value['production_ceiling']))}] | "
            f"{counts['CLEAR']}/{counts['HOLD']}/{counts['BLOCK']} | "
            f"{_percent(float(repeated['simultaneous_undercoverage_upper']))} | "
            f"{_percent(float(repeated['simultaneous_wrong_direction_upper']))} | "
            f"{_percent(float(repeated['simultaneous_correct_direction_lower']))} | "
            f"coverage {'PASS' if repeated['undercoverage_target_met'] else 'FAIL'}; "
            f"direction {'PASS' if repeated['wrong_direction_target_met'] else 'FAIL'}; resolution {resolution} |"
        )
    lines.extend([
        "",
        "### Repeated-sample tightness",
        "",
        "A ceiling of 1 would cover every risk but be useless. These values report how far the repeated upper bound remained above exact risk and how wide the interval remained.",
        "",
        "| Model / wrapper | Mean U | Mean width U-L | Mean excess U-R* | P95 excess U-R* |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for raw in _sequence(model["results"], "v3 model tightness results"):
        value = _mapping(raw, "v3 model tightness result")
        repeated = _mapping(value["repeated_validation"], "v3 repeated tightness")
        lines.append(
            f"| {value['model_label']} — {value['variant_label']} | "
            f"{_decimal(float(repeated['mean_ceiling']))} | "
            f"{_decimal(float(repeated['mean_interval_width']))} | "
            f"{_decimal(float(repeated['mean_ceiling_excess_over_oracle']))} | "
            f"{_decimal(float(repeated['p95_ceiling_excess_over_oracle']))} |"
        )
    lines.extend([
        "",
        "## Exact erasure identity",
        "",
        "The 90% state-independent erasure variant must satisfy `R_erased = 0.5 + 0.1 × (R_raw - 0.5)` exactly.",
        "",
        "| Model | Raw R* | Erased R* | Exact identity |",
        "| --- | ---: | ---: | --- |",
    ])
    for raw in _sequence(model["erasure_comparisons"], "v3 erasure comparisons"):
        value = _mapping(raw, "v3 erasure comparison")
        lines.append(
            f"| {value['model_label']} | {_decimal(float(value['raw_oracle_risk']))} | "
            f"{_decimal(float(value['erased_oracle_risk']))} | PASS |"
        )

    predecessor = summary.get("predecessor_model_backed_v2")
    if predecessor is not None:
        previous = _mapping(predecessor, "v2 predecessor")
        previous_acceptance = _mapping(previous["acceptance"], "v2 acceptance")
        lines.extend([
            "",
            "## Historical v2 predecessor — acceptance failed",
            "",
            f"V2 remains a separate failed result (`{', '.join(previous_acceptance['failed_criteria'])}`). It is not relabelled as v3 evidence and no v2 outcome is reused by v3.",
            "",
            "| Model / wrapper | V2 repeat CLEAR | V2 simultaneous CLEAR lower | V2 target |",
            "| --- | ---: | ---: | --- |",
        ])
        for raw in _sequence(previous["results"], "v2 results"):
            value = _mapping(raw, "v2 result")
            repeated = _mapping(value["repeated_validation"], "v2 repeated result")
            lines.append(
                f"| {value['model_label']} — {value['variant_label']} | {repeated['clear_count']}/{repeated['replicates']} | "
                f"{_percent(float(repeated['simultaneous_clear_rate_lower']))} | "
                f"{'PASS' if repeated['clear_rate_target_met'] else 'FAIL'} |"
            )
    lines.extend([
        "",
        "## How the metrics map to MRA",
        "",
        "- Soundness failure is undercoverage: `U < R*`.",
        "- Wrong direction is BLOCK below tolerance or CLEAR above tolerance; HOLD is conservative.",
        "- Correct-direction resolution is evaluated only at the preregistered absolute margin of at least 0.10.",
        "- Width `U - L` and excess `U - R*` measure tightness; neither replaces coverage.",
        "- Results remain conditional on frozen finite populations and source-bound wrappers. The compact Transformer is an LLM proxy, not a generative endpoint.",
        "",
        "No raw scores, count rows, seeds, model artifacts, local paths, or software-environment details are included.",
        "",
    ])
    return "\n".join(lines)


def render_svg(summary: Mapping[str, Any]) -> str:
    """Render exact-risk points and reported floor/ceiling intervals as SVG."""

    known = _mapping(summary["known_channel"], "summary known channel")
    model = _mapping(summary["model_backed"], "summary model backed")
    rows: list[tuple[str, str, float, float, float, float | None, bool]] = []
    for raw in _sequence(known["primary_results"], "known primary results"):
        value = _mapping(raw, "known primary row")
        rows.append((
            f"Controlled · {value['model_label']} · {str(value['risk_role']).upper()}",
            "controlled",
            float(value["mean_floor"]),
            float(value["mean_ceiling"]),
            float(value["true_risk"]),
            None,
            True,
        ))
    for raw in _sequence(model["results"], "model results"):
        value = _mapping(raw, "model result row")
        repeated = _mapping(value["repeated_validation"], "model repeated result")
        variant = "raw" if value["variant_id"] == "raw_bins" else "90% erasure"
        short_model = {
            "cnn": "CNN",
            "xgboost": "XGBoost",
            "compact_transformer_llm_proxy": "Transformer proxy",
        }[str(value["collector_model"])]
        mean_ceiling = float(repeated["mean_ceiling"])
        mean_floor = mean_ceiling - float(repeated["mean_interval_width"])
        eligible = repeated["margin_eligible_for_resolution_claim"] is True
        role_suffix = repeated["expected_direction"]
        if not eligible:
            role_suffix = f"{role_suffix} · margin<0.10"
        rows.append((
            f"Conditional · {short_model} · {variant} · {role_suffix}",
            "model",
            mean_floor,
            mean_ceiling,
            float(value["oracle_risk"]),
            float(repeated["p95_ceiling"]),
            (
                repeated["correct_direction_target_met"] is True
                if eligible
                else True
            ),
        ))

    width = 1280
    left = 440
    right = 70
    top = 145
    row_height = 48
    bottom = 110
    height = top + row_height * len(rows) + bottom
    plot_width = width - left - right

    def x(value: float) -> float:
        clipped = min(1.0, max(0.5, value))
        return left + (clipped - 0.5) / 0.5 * plot_width

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Finite-channel ceiling validation</title>',
        '<desc id="desc">Exact oracle risk points shown against controlled and model-conditional mean intervals. Triangles mark model-conditional 95th-percentile ceilings. A dashed vertical line marks the MRA tolerance of 0.65.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#172033}.title{font-size:25px;font-weight:700}.subtitle{font-size:14px;fill:#536079}.label{font-size:13px}.label.fail{fill:#b42318;font-weight:700}.tick{font-size:12px;fill:#667085}.section{font-size:12px;font-weight:700;letter-spacing:.08em}.legend{font-size:12px}</style>',
        '<text class="title" x="32" y="40">Ceiling validation against exact oracle risk</text>',
        '<text class="subtitle" x="32" y="66">Line = mean [floor, ceiling]; dot = exact risk R*; triangle = p95 ceiling; dashed line = tolerance 0.65</text>',
        '<line x1="32" y1="91" x2="54" y2="91" stroke="#1769aa" stroke-width="5" stroke-linecap="round"/>',
        '<text class="legend" x="62" y="95">controlled mean interval</text>',
        '<line x1="232" y1="91" x2="254" y2="91" stroke="#7a3db8" stroke-width="5" stroke-linecap="round"/>',
        '<text class="legend" x="262" y="95">model-conditional mean interval</text>',
        '<circle cx="503" cy="91" r="5" fill="#111827"/>',
        '<text class="legend" x="514" y="95">exact oracle risk</text>',
        '<polygon points="654,84 648,96 660,96" fill="#7a3db8"/>',
        '<text class="legend" x="669" y="95">model p95 ceiling</text>',
    ]
    axis_top = top - 20
    axis_bottom = top + row_height * len(rows) - 10
    for tick in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        tick_x = x(tick)
        elements.extend([
            f'<line x1="{tick_x:.2f}" y1="{axis_top}" x2="{tick_x:.2f}" y2="{axis_bottom}" stroke="#e4e7ec" stroke-width="1"/>',
            f'<text class="tick" x="{tick_x:.2f}" y="{axis_bottom + 28}" text-anchor="middle">{tick:.1f}</text>',
        ])
    tolerance_x = x(float(summary["decision_tolerance"]))
    elements.extend([
        f'<line x1="{tolerance_x:.2f}" y1="{axis_top - 8}" x2="{tolerance_x:.2f}" y2="{axis_bottom}" stroke="#d1495b" stroke-width="2" stroke-dasharray="7 5"/>',
        f'<text class="tick" x="{tolerance_x + 7:.2f}" y="{axis_top - 12}" fill="#b42318">tolerance 0.65</text>',
    ])
    for index, (label, tier, floor, ceiling, risk, p95_ceiling, target_met) in enumerate(rows):
        y = top + index * row_height
        if index == 0:
            elements.append(f'<text class="section" x="32" y="{y - 17}" fill="#1769aa">CONTROLLED EXACT GROUND TRUTH</text>')
        if index == 3:
            elements.append(f'<line x1="32" y1="{y - 26}" x2="{width - 32}" y2="{y - 26}" stroke="#cfd5df"/>')
            elements.append(f'<text class="section" x="32" y="{y - 8}" fill="#7a3db8">MODEL-CONDITIONAL PUBLIC DATA</text>')
            y += 12
        color = "#1769aa" if tier == "controlled" else "#7a3db8"
        floor_x = x(floor)
        ceiling_x = x(ceiling)
        risk_x = x(risk)
        label_class = "label" if target_met else "label fail"
        rendered_label = label if target_met else f"{label} · RESOLUTION FAIL"
        elements.extend([
            f'<text class="{label_class}" x="32" y="{y + 5}">{xml_escape(rendered_label)}</text>',
            f'<line x1="{floor_x:.2f}" y1="{y}" x2="{ceiling_x:.2f}" y2="{y}" stroke="{color}" stroke-width="6" stroke-linecap="round"/>',
            f'<line x1="{floor_x:.2f}" y1="{y - 7}" x2="{floor_x:.2f}" y2="{y + 7}" stroke="{color}" stroke-width="2"/>',
            f'<line x1="{ceiling_x:.2f}" y1="{y - 7}" x2="{ceiling_x:.2f}" y2="{y + 7}" stroke="{color}" stroke-width="2"/>',
            f'<circle cx="{risk_x:.2f}" cy="{y}" r="5.5" fill="#111827" stroke="#ffffff" stroke-width="1.5"/>',
        ])
        if p95_ceiling is not None:
            p95_x = x(p95_ceiling)
            elements.append(
                f'<polygon points="{p95_x:.2f},{y - 8} {p95_x - 6:.2f},{y + 5} {p95_x + 6:.2f},{y + 5}" fill="{color}"/>'
            )
    elements.extend([
        f'<text class="subtitle" x="{left + plot_width / 2:.2f}" y="{height - 32}" text-anchor="middle">Equal-prior membership success probability</text>',
        '</svg>',
        '',
    ])
    return "\n".join(elements)


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def generate_artifacts(
    known_report_path: Path,
    model_report_path: Path,
    json_output: Path,
    markdown_output: Path,
    svg_output: Path,
    predecessor_model_report_path: Path | None = None,
) -> dict[str, Any]:
    """Validate both inputs before atomically writing any publication artifact."""

    inputs = {known_report_path.resolve(), model_report_path.resolve()}
    if predecessor_model_report_path is not None:
        inputs.add(predecessor_model_report_path.resolve())
    outputs = {json_output.resolve(), markdown_output.resolve(), svg_output.resolve()}
    _require(len(outputs) == 3, "publication output paths must be distinct")
    _require(not inputs.intersection(outputs), "publication output cannot overwrite a source report")
    known_report, known_sha256 = load_report(known_report_path)
    model_report, model_sha256 = load_report(model_report_path)
    predecessor_report = None
    predecessor_sha256 = None
    if predecessor_model_report_path is not None:
        predecessor_report, predecessor_sha256 = load_report(
            predecessor_model_report_path
        )
    summary = build_publication_summary(
        known_report,
        model_report,
        known_report_sha256=known_sha256,
        model_report_sha256=model_sha256,
        predecessor_model_report=predecessor_report,
        predecessor_model_report_sha256=predecessor_sha256,
    )
    json_payload = json.dumps(summary, allow_nan=False, indent=2, sort_keys=True) + "\n"
    svg_reference = Path(
        os.path.relpath(svg_output.resolve(), markdown_output.resolve().parent)
    ).as_posix()
    markdown_payload = render_markdown(summary, svg_reference)
    svg_payload = render_svg(summary)
    # No output is opened until all validation and rendering has succeeded.
    _atomic_write(json_output, json_payload)
    _atomic_write(markdown_output, markdown_payload)
    _atomic_write(svg_output, svg_payload)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--known-report", type=Path, required=True)
    parser.add_argument("--model-report", type=Path, required=True)
    parser.add_argument(
        "--predecessor-model-report",
        type=Path,
        help="optional completed v2 predecessor report retained as failed history",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--svg-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        generate_artifacts(
            args.known_report,
            args.model_report,
            args.json_output,
            args.markdown_output,
            args.svg_output,
            args.predecessor_model_report,
        )
    except PublicationSummaryError as exc:
        print(f"ceiling summary refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "summary_id": SUMMARY_ID,
        "json_output": str(args.json_output),
        "markdown_output": str(args.markdown_output),
        "svg_output": str(args.svg_output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
