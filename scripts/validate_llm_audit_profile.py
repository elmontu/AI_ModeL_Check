#!/usr/bin/env python3
"""Validate the fail-closed LLM watermark/canary preregistration profile."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


PROFILE_SCHEMA_VERSION = "1.1"
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)
ZERO_SHA256 = "0" * 64
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "profile_type",
    "protocol_id",
    "protocol_version",
    "study_id",
    "protocol_status",
    "placeholder_policy",
    "preregistered_at",
    "assessor_id",
    "decision_semantics",
    "release_binding",
    "decision_games",
    "partitions",
    "multiplicity",
    "watermark_study",
    "canary_study",
    "naturalistic_extraction_probe",
    "collection_controls",
    "analyzer_provenance",
    "required_evidence_artifacts",
    "mandatory_output_fields",
}
REQUIRED_BOUND_SECTIONS = REQUIRED_TOP_LEVEL - {"placeholder_policy"}
REQUIRED_WATERMARK_ATTACK_TYPES = {
    "blind_edit",
    "blind_paraphrase",
    "informed_paraphrase",
    "translation",
    "truncation",
    "mixed_text",
    "watermark_stealing",
    "distillation",
    "scrubbing",
    "spoofing",
    "multi_key_averaging",
    "detector_oracle_optimization",
}
REQUIRED_QUALITY_METRICS = {
    "semantic_similarity",
    "downstream_task_accuracy",
    "factuality",
    "safety_and_refusal_behavior",
    "human_preference",
}
REQUIRED_EVIDENCE_ARTIFACTS = {
    "preregistration_config_sha256",
    "scheme_config_sha256",
    "null_corpus_manifest_sha256",
    "null_generation_manifest_sha256",
    "encrypted_raw_transcripts_sha256",
    "raw_detector_scores_sha256",
    "raw_logprob_or_unavailable_record_sha256",
    "aggregate_cell_counts_sha256",
    "unique_context_ledger_sha256",
    "window_alignment_search_ledger_sha256",
    "quality_raw_results_sha256",
    "attack_matrix_results_sha256",
    "transformation_implementations_sha256",
    "key_custody_attestation_sha256",
    "endpoint_attestation_log_sha256",
    "multiple_testing_result_sha256",
    "exclusions_and_errors_sha256",
    "query_budget_ledger_sha256",
    "contamination_scan_sha256",
    "retention_and_deletion_attestation_sha256",
}
REQUIRED_OUTPUT_FIELDS = {
    "release_and_complete_interface_bindings",
    "separate_watermark_and_canary_decision_game_bindings",
    "protocol_study_and_analyzer_versions",
    "actual_query_session_concurrency_and_retry_counts",
    "raw_counts_and_simultaneous_confidence_method",
    "total_eligible_and_unique_scored_context_counts",
    "complete_window_key_alignment_and_attack_ledgers",
    "quality_and_power_results",
    "all_deviations_failures_exclusions_and_contamination_results",
    "evidence_direction_realizability_and_coverage_limitations",
    "can_block",
    "can_clear_false",
}
SUPPORTED_FAMILY_PROCEDURES = {
    "holm_one_sided_fixed_family",
    "bonferroni_one_sided_fixed_family",
    "registered_maximum_statistic",
}
OPTIONAL_COLLECTION_NULL_PATHS = {
    "profile.multiplicity.umbrella_family",
    "profile.release_binding.llm_protocol_components.retrieval_corpus_sha256",
    "profile.release_binding.llm_protocol_components.retriever_config_sha256",
    "profile.release_binding.llm_protocol_components.tool_policy_sha256",
    "profile.watermark_study.scheme.green_fraction",
    "profile.watermark_study.scheme.logit_bias",
    "profile.watermark_study.scheme.context_width",
    "profile.canary_study.contamination_scan.retrieval_corpus_sha256",
    "profile.naturalistic_extraction_probe.profile_sha256",
}


class ProfileValidationError(ValueError):
    """Raised when a preregistration profile violates a fail-closed invariant."""


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileValidationError(f"{path} must be a JSON object")
    return value


def _array(value: Any, path: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "a non-empty" if nonempty else "an"
        raise ProfileValidationError(f"{path} must be {qualifier} array")
    return value


def _require_keys(value: dict[str, Any], path: str, required: Iterable[str]) -> None:
    missing = set(required) - set(value)
    if missing:
        raise ProfileValidationError(f"{path} is missing required fields: {sorted(missing)}")


def _strict_keys(value: dict[str, Any], path: str, required: Iterable[str]) -> None:
    required_set = set(required)
    _require_keys(value, path, required_set)
    unknown = set(value) - required_set
    if unknown:
        raise ProfileValidationError(f"{path} contains unknown fields: {sorted(unknown)}")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(f"{path} must be a non-empty string")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ProfileValidationError(f"{path} must be a boolean")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProfileValidationError(f"{path} must be an integer >= {minimum}")
    return value


def _positive_integer(value: Any, path: str, *, allow_none: bool = False) -> int | None:
    return _integer(value, path, minimum=1, allow_none=allow_none)


def _number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    allow_none: bool = False,
) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileValidationError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ProfileValidationError(f"{path} must be a finite number")
    if minimum is not None and result < minimum:
        raise ProfileValidationError(f"{path} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ProfileValidationError(f"{path} must be <= {maximum}")
    return result


def _string_array(value: Any, path: str, *, nonempty: bool = False) -> list[str]:
    result = _array(value, path, nonempty=nonempty)
    for index, item in enumerate(result):
        _text(item, f"{path}[{index}]")
    if len(result) != len(set(result)):
        raise ProfileValidationError(f"{path} must not contain duplicates")
    return result


def _integer_array(
    value: Any,
    path: str,
    *,
    minimum: int = 0,
    nonempty: bool = False,
) -> list[int]:
    result = _array(value, path, nonempty=nonempty)
    parsed = [_integer(item, f"{path}[{index}]", minimum=minimum) for index, item in enumerate(result)]
    assert all(item is not None for item in parsed)
    integers = [int(item) for item in parsed]
    if len(integers) != len(set(integers)):
        raise ProfileValidationError(f"{path} must not contain duplicates")
    return integers


def _sha256(value: Any, path: str, *, allow_none: bool = False, prefixed: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise ProfileValidationError(f"{path} must be a lowercase SHA-256 digest")
    candidate = value[7:] if prefixed and value.startswith("sha256:") else value
    if prefixed and not value.startswith("sha256:"):
        raise ProfileValidationError(f"{path} must use the sha256:<digest> form")
    if SHA256_PATTERN.fullmatch(candidate) is None:
        raise ProfileValidationError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: Any, path: str, *, allow_none: bool = False) -> datetime | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value:
        raise ProfileValidationError(f"{path} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProfileValidationError(f"{path} is not an ISO-8601 timestamp") from error
    if parsed.utcoffset() is None:
        raise ProfileValidationError(f"{path} must include a timezone offset")
    return parsed


def _walk(value: Any, path: str = "profile") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def _validate_digest_syntax(value: Any, path: str = "profile") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key.endswith("_sha256"):
                _sha256(item, item_path, allow_none=True)
            elif key.endswith("_sha256s"):
                digests = _array(item, item_path)
                for index, digest in enumerate(digests):
                    _sha256(digest, f"{item_path}[{index}]")
            elif key == "container_image_digest":
                _sha256(item, item_path, prefixed=True)
            else:
                _validate_digest_syntax(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_digest_syntax(item, f"{path}[{index}]")


def _validate_family(value: Any, path: str, *, allowed_hypotheses: set[str]) -> None:
    family = _mapping(value, path)
    _strict_keys(
        family,
        path,
        {
            "family_id",
            "familywise_error_rate_alpha",
            "procedure",
            "ledger_sha256",
            "registered_tests",
            "family_size",
            "correction_order",
            "exploratory_test_policy",
        },
    )
    _text(family["family_id"], f"{path}.family_id")
    alpha = _number(
        family["familywise_error_rate_alpha"],
        f"{path}.familywise_error_rate_alpha",
        minimum=0.0,
        maximum=0.5,
    )
    assert alpha is not None
    if not 0.0 < alpha < 0.5:
        raise ProfileValidationError(f"{path}.familywise_error_rate_alpha must be in (0, 0.5)")
    if family["procedure"] not in SUPPORTED_FAMILY_PROCEDURES:
        raise ProfileValidationError(f"{path}.procedure is unsupported")
    _sha256(family["ledger_sha256"], f"{path}.ledger_sha256")
    tests = _array(family["registered_tests"], f"{path}.registered_tests", nonempty=True)
    test_ids: list[str] = []
    for index, item in enumerate(tests):
        test_path = f"{path}.registered_tests[{index}]"
        test = _mapping(item, test_path)
        _strict_keys(test, test_path, {"test_id", "hypothesis", "confirmatory"})
        test_ids.append(_text(test["test_id"], f"{test_path}.test_id"))
        hypothesis = _text(test["hypothesis"], f"{test_path}.hypothesis")
        if hypothesis not in allowed_hypotheses:
            raise ProfileValidationError(f"{test_path}.hypothesis does not resolve to a declared endpoint")
        if test["confirmatory"] is not True:
            raise ProfileValidationError(f"{path}.registered_tests may contain confirmatory tests only")
    if len(test_ids) != len(set(test_ids)):
        raise ProfileValidationError(f"{path}.registered_tests has duplicate test IDs")
    family_size = _positive_integer(family["family_size"], f"{path}.family_size")
    if family_size != len(test_ids):
        raise ProfileValidationError(f"{path}.family_size does not match registered_tests")
    order = _string_array(family["correction_order"], f"{path}.correction_order", nonempty=True)
    if len(order) != len(test_ids) or set(order) != set(test_ids):
        raise ProfileValidationError(f"{path}.correction_order must list every test ID exactly once")
    _text(family["exploratory_test_policy"], f"{path}.exploratory_test_policy")


def _validate_release_binding(value: Any) -> dict[str, Any]:
    path = "release_binding"
    release = _mapping(value, path)
    _strict_keys(
        release,
        path,
        {
            "release_id",
            "protocol_type",
            "artifact_sha256",
            "complete_interface_sha256",
            "llm_protocol_sha256",
            "policy_bundle_sha256",
            "portfolio_registry_head_sha256",
            "valid_until",
            "llm_protocol_components",
        },
    )
    _text(release["release_id"], f"{path}.release_id")
    if release["protocol_type"] != "interactive_llm":
        raise ProfileValidationError("release_binding.protocol_type must be interactive_llm")
    for field in (
        "artifact_sha256",
        "complete_interface_sha256",
        "llm_protocol_sha256",
        "policy_bundle_sha256",
        "portfolio_registry_head_sha256",
    ):
        _sha256(release[field], f"{path}.{field}")
    _timestamp(release["valid_until"], f"{path}.valid_until", allow_none=True)

    components = _mapping(release["llm_protocol_components"], f"{path}.llm_protocol_components")
    component_path = f"{path}.llm_protocol_components"
    _strict_keys(
        components,
        component_path,
        {
            "model_provider",
            "model_identifier",
            "model_version",
            "tokenizer_sha256",
            "decoding_parameters_sha256",
            "system_prompt_sha256",
            "adapter_sha256s",
            "retrieval_corpus_sha256",
            "retriever_config_sha256",
            "tool_names",
            "tool_policy_sha256",
            "memory_mode",
            "memory_ttl_seconds",
            "logging_mode",
            "provider_retention_days",
            "maximum_session_tokens",
            "maximum_lifetime_queries",
            "maximum_concurrent_sessions",
            "reset_semantics",
            "filter_bundle_sha256",
            "update_policy",
        },
    )
    for field in ("model_provider", "model_identifier", "model_version", "reset_semantics"):
        _text(components[field], f"{component_path}.{field}")
    for field in (
        "tokenizer_sha256",
        "decoding_parameters_sha256",
        "system_prompt_sha256",
        "filter_bundle_sha256",
    ):
        _sha256(components[field], f"{component_path}.{field}")
    adapters = _array(components["adapter_sha256s"], f"{component_path}.adapter_sha256s")
    for index, digest in enumerate(adapters):
        _sha256(digest, f"{component_path}.adapter_sha256s[{index}]")
    if len(adapters) != len(set(adapters)):
        raise ProfileValidationError(f"{component_path}.adapter_sha256s must be unique")
    retrieval = _sha256(
        components["retrieval_corpus_sha256"],
        f"{component_path}.retrieval_corpus_sha256",
        allow_none=True,
    )
    retriever = _sha256(
        components["retriever_config_sha256"],
        f"{component_path}.retriever_config_sha256",
        allow_none=True,
    )
    if (retrieval is None) != (retriever is None):
        raise ProfileValidationError("retrieval corpus and configuration digests must be supplied together")
    tools = _string_array(components["tool_names"], f"{component_path}.tool_names")
    tool_policy = _sha256(
        components["tool_policy_sha256"],
        f"{component_path}.tool_policy_sha256",
        allow_none=True,
    )
    if tools and tool_policy is None:
        raise ProfileValidationError("tool-enabled profiles require tool_policy_sha256")
    if not tools and tool_policy is not None:
        raise ProfileValidationError("tool_policy_sha256 must be null when no tools are registered")
    if components["memory_mode"] not in {"none", "session", "persistent"}:
        raise ProfileValidationError(f"{component_path}.memory_mode is unsupported")
    ttl = _integer(components["memory_ttl_seconds"], f"{component_path}.memory_ttl_seconds")
    if components["memory_mode"] == "none" and ttl != 0:
        raise ProfileValidationError("stateless LLM protocols must use memory_ttl_seconds=0")
    if components["memory_mode"] != "none" and (ttl is None or ttl <= 0):
        raise ProfileValidationError("stateful LLM protocols require a positive memory TTL")
    if components["logging_mode"] not in {"none", "security_only", "full_transcript"}:
        raise ProfileValidationError(f"{component_path}.logging_mode is unsupported")
    _integer(components["provider_retention_days"], f"{component_path}.provider_retention_days")
    for field in ("maximum_session_tokens", "maximum_lifetime_queries", "maximum_concurrent_sessions"):
        _positive_integer(components[field], f"{component_path}.{field}", allow_none=True)
    if components["update_policy"] not in {"immutable", "versioned_reassessment_required"}:
        raise ProfileValidationError(f"{component_path}.update_policy is unsupported")
    return release


def _validate_decision_games(value: Any) -> dict[str, Any]:
    games = _mapping(value, "decision_games")
    _strict_keys(games, "decision_games", {"watermark", "canary"})
    watermark = _mapping(games["watermark"], "decision_games.watermark")
    watermark_keys = {
        "threat_contract_sha256",
        "policy_rule_sha256",
        "population_snapshot_sha256",
        "claim_scope",
        "null_population_id",
        "positive_population_id",
        "inferential_unit",
        "provenance_subject",
        "recipient_observation",
        "attacker_capabilities",
        "operational_false_positive_target",
        "query_budget",
        "harm_of_false_attribution",
    }
    _strict_keys(watermark, "decision_games.watermark", watermark_keys)
    for field in ("threat_contract_sha256", "policy_rule_sha256", "population_snapshot_sha256"):
        _sha256(watermark[field], f"decision_games.watermark.{field}")
    if watermark["claim_scope"] != "key_associated_signal_only":
        raise ProfileValidationError("watermark claim_scope must be key_associated_signal_only")
    for field in (
        "null_population_id",
        "positive_population_id",
        "inferential_unit",
        "provenance_subject",
        "recipient_observation",
        "harm_of_false_attribution",
    ):
        _text(watermark[field], f"decision_games.watermark.{field}")
    _string_array(watermark["attacker_capabilities"], "decision_games.watermark.attacker_capabilities", nonempty=True)
    operational_fpr = _number(
        watermark["operational_false_positive_target"],
        "decision_games.watermark.operational_false_positive_target",
        minimum=0.0,
        maximum=1.0,
        allow_none=True,
    )
    if operational_fpr is not None and not 0.0 < operational_fpr < 1.0:
        raise ProfileValidationError("watermark operational_false_positive_target must be in (0,1)")
    _positive_integer(watermark["query_budget"], "decision_games.watermark.query_budget", allow_none=True)

    canary = _mapping(games["canary"], "decision_games.canary")
    canary_keys = {
        "threat_contract_sha256",
        "policy_rule_sha256",
        "population_snapshot_sha256",
        "protected_unit",
        "secret",
        "recipient",
        "side_information",
        "observation",
        "success_rule",
        "query_budget",
        "harm_rationale",
    }
    _strict_keys(canary, "decision_games.canary", canary_keys)
    for field in ("threat_contract_sha256", "policy_rule_sha256", "population_snapshot_sha256"):
        _sha256(canary[field], f"decision_games.canary.{field}")
    for field in ("protected_unit", "secret", "recipient", "observation", "success_rule", "harm_rationale"):
        _text(canary[field], f"decision_games.canary.{field}")
    _string_array(canary["side_information"], "decision_games.canary.side_information", nonempty=True)
    _positive_integer(canary["query_budget"], "decision_games.canary.query_budget", allow_none=True)
    return games


def _validate_partitions(value: Any) -> None:
    partitions = _mapping(value, "partitions")
    _strict_keys(
        partitions,
        "partitions",
        {
            "development_prompt_set_sha256",
            "calibration_prompt_set_sha256",
            "audit_prompt_set_sha256",
            "disjointness_check_sha256",
            "selection_uses_audit_data",
        },
    )
    for field in (
        "development_prompt_set_sha256",
        "calibration_prompt_set_sha256",
        "audit_prompt_set_sha256",
        "disjointness_check_sha256",
    ):
        _sha256(partitions[field], f"partitions.{field}")
    if partitions["selection_uses_audit_data"] is not False:
        raise ProfileValidationError("partitions.selection_uses_audit_data must be false")


def _validate_multiplicity(value: Any) -> dict[str, Any]:
    multiplicity = _mapping(value, "multiplicity")
    _strict_keys(multiplicity, "multiplicity", {"watermark_family", "canary_family", "umbrella_family"})
    _validate_family(
        multiplicity["watermark_family"],
        "multiplicity.watermark_family",
        allowed_hypotheses={"null_calibration", "detectability"},
    )
    _validate_family(
        multiplicity["canary_family"],
        "multiplicity.canary_family",
        allowed_hypotheses={"randomized_in_out_exact_extraction"},
    )
    if multiplicity["umbrella_family"] is not None:
        _validate_family(
            multiplicity["umbrella_family"],
            "multiplicity.umbrella_family",
            allowed_hypotheses={
                "null_calibration",
                "detectability",
                "randomized_in_out_exact_extraction",
            },
        )
    return multiplicity


def _validate_scheme(value: Any) -> dict[str, Any]:
    path = "watermark_study.scheme"
    scheme = _mapping(value, path)
    _strict_keys(
        scheme,
        path,
        {
            "family",
            "algorithm",
            "version",
            "source_sha256",
            "scheme_config_sha256",
            "embedding_location",
            "tokenizer_sha256",
            "green_fraction",
            "logit_bias",
            "context_width",
            "context_hash_or_prf",
            "seeding_and_reset_rule",
            "synchronization_rule",
            "eligible_token_rule",
            "key_count",
            "key_selection_policy",
            "key_rotation_and_revocation_policy",
            "maximum_key_or_generation_budget",
        },
    )
    for field in (
        "family",
        "algorithm",
        "version",
        "embedding_location",
        "context_hash_or_prf",
        "seeding_and_reset_rule",
        "synchronization_rule",
        "eligible_token_rule",
        "key_selection_policy",
        "key_rotation_and_revocation_policy",
    ):
        _text(scheme[field], f"{path}.{field}")
    for field in ("source_sha256", "scheme_config_sha256", "tokenizer_sha256"):
        _sha256(scheme[field], f"{path}.{field}")
    green_fraction = _number(scheme["green_fraction"], f"{path}.green_fraction", minimum=0.0, maximum=1.0, allow_none=True)
    if green_fraction is not None and not 0.0 < green_fraction < 1.0:
        raise ProfileValidationError(f"{path}.green_fraction must be in (0,1) when applicable")
    _number(scheme["logit_bias"], f"{path}.logit_bias", allow_none=True)
    _positive_integer(scheme["context_width"], f"{path}.context_width", allow_none=True)
    _positive_integer(scheme["key_count"], f"{path}.key_count", allow_none=True)
    _positive_integer(
        scheme["maximum_key_or_generation_budget"],
        f"{path}.maximum_key_or_generation_budget",
        allow_none=True,
    )
    return scheme


def _validate_formal_claims(value: Any) -> None:
    claims = _array(value, "watermark_study.formal_claims")
    claim_ids: list[str] = []
    for index, item in enumerate(claims):
        path = f"watermark_study.formal_claims[{index}]"
        claim = _mapping(item, path)
        _strict_keys(
            claim,
            path,
            {
                "claim_id",
                "claim_type",
                "claim_definition",
                "quantifier",
                "maximum_generation_budget",
                "minimum_entropy_requirement",
                "security_parameter",
                "computational_assumptions",
                "theorem_or_evidence_sha256",
                "implementation_conformance_artifact_sha256",
            },
        )
        claim_ids.append(_text(claim["claim_id"], f"{path}.claim_id"))
        for field in ("claim_type", "claim_definition", "quantifier", "security_parameter"):
            _text(claim[field], f"{path}.{field}")
        _positive_integer(claim["maximum_generation_budget"], f"{path}.maximum_generation_budget")
        _number(claim["minimum_entropy_requirement"], f"{path}.minimum_entropy_requirement", minimum=0.0)
        _string_array(claim["computational_assumptions"], f"{path}.computational_assumptions", nonempty=True)
        _sha256(claim["theorem_or_evidence_sha256"], f"{path}.theorem_or_evidence_sha256")
        _sha256(
            claim["implementation_conformance_artifact_sha256"],
            f"{path}.implementation_conformance_artifact_sha256",
        )
    if len(claim_ids) != len(set(claim_ids)):
        raise ProfileValidationError("watermark_study.formal_claims has duplicate claim IDs")


def _validate_hypotheses(value: Any) -> None:
    hypotheses = _mapping(value, "watermark_study.hypotheses")
    _strict_keys(hypotheses, "watermark_study.hypotheses", {"null_calibration", "detectability"})
    expected = {
        "null_calibration": {
            "estimand": "false_positive_probability",
            "null_relation": "false_positive_probability_above_operational_target",
            "alternative_relation": "false_positive_probability_at_or_below_operational_target",
            "decision_rule": "one_sided_exact_upper_confidence_bound_lte_target",
            "evidence_scope": "detector_false_positive_rate_ceiling_only_not_release_clearance",
        },
        "detectability": {
            "estimand": "release_minus_matched_control_detection_probability",
            "null_relation": "difference_below_minimum_detectable_effect",
            "alternative_relation": "difference_at_or_above_minimum_detectable_effect",
            "decision_rule": "one_sided_simultaneous_lower_confidence_bound_gte_minimum_effect",
            "evidence_scope": "key_associated_signal_detectability_only",
        },
    }
    for name, required_values in expected.items():
        path = f"watermark_study.hypotheses.{name}"
        hypothesis = _mapping(hypotheses[name], path)
        _strict_keys(hypothesis, path, set(required_values))
        for field, required in required_values.items():
            if hypothesis[field] != required:
                raise ProfileValidationError(f"{path}.{field} must be {required!r}")


def _validate_detector(value: Any) -> dict[str, Any]:
    path = "watermark_study.detector"
    detector = _mapping(value, path)
    _strict_keys(
        detector,
        path,
        {
            "tool",
            "version",
            "source_sha256",
            "embedding_key_id",
            "verification_key_id",
            "key_version",
            "key_commitment_sha256",
            "key_count",
            "custody_roles",
            "provisioning_or_escrow_attestation_sha256",
            "compromise_status",
            "revocation_status",
            "score_input",
            "threshold",
            "minimum_eligible_tokens",
            "context_unit",
            "repeated_context_policy",
            "context_deduplication_spec_sha256",
            "total_token_count_output_required",
            "eligible_token_count_output_required",
            "unique_scored_context_count_output_required",
            "effective_sample_size_method",
            "detector_api_visibility",
            "detector_api_output",
            "detector_api_rate_limit",
            "detector_api_total_query_budget",
            "detector_api_privacy_or_randomization_policy",
        },
    )
    for field in (
        "tool",
        "version",
        "embedding_key_id",
        "verification_key_id",
        "key_version",
        "compromise_status",
        "revocation_status",
        "score_input",
        "context_unit",
        "effective_sample_size_method",
        "detector_api_visibility",
        "detector_api_output",
        "detector_api_privacy_or_randomization_policy",
    ):
        _text(detector[field], f"{path}.{field}")
    for field in (
        "source_sha256",
        "key_commitment_sha256",
        "provisioning_or_escrow_attestation_sha256",
        "context_deduplication_spec_sha256",
    ):
        _sha256(detector[field], f"{path}.{field}")
    _positive_integer(detector["key_count"], f"{path}.key_count", allow_none=True)
    _string_array(detector["custody_roles"], f"{path}.custody_roles")
    _number(detector["threshold"], f"{path}.threshold", allow_none=True)
    _positive_integer(detector["minimum_eligible_tokens"], f"{path}.minimum_eligible_tokens", allow_none=True)
    if detector["repeated_context_policy"] not in {"deduplicate", "model_dependence", "reject"}:
        raise ProfileValidationError("watermark detector repeated_context_policy is unsupported")
    for field in (
        "total_token_count_output_required",
        "eligible_token_count_output_required",
        "unique_scored_context_count_output_required",
    ):
        if detector[field] is not True:
            raise ProfileValidationError(f"{path}.{field} must be true")
    _integer(detector["detector_api_rate_limit"], f"{path}.detector_api_rate_limit", allow_none=True)
    _integer(
        detector["detector_api_total_query_budget"],
        f"{path}.detector_api_total_query_budget",
        allow_none=True,
    )
    return detector


def _validate_null_calibration(value: Any) -> None:
    path = "watermark_study.null_calibration"
    calibration = _mapping(value, path)
    _strict_keys(
        calibration,
        path,
        {
            "negative_corpus_manifest_sha256",
            "source_types",
            "domains",
            "languages",
            "repetitive_or_formatted_text_included",
            "code_included",
            "length_strata",
            "entropy_strata",
            "near_duplicate_policy",
            "null_generation_config_sha256",
            "matching_diagnostics_sha256",
            "tail_confidence_method",
        },
    )
    for field in (
        "negative_corpus_manifest_sha256",
        "null_generation_config_sha256",
        "matching_diagnostics_sha256",
    ):
        _sha256(calibration[field], f"{path}.{field}")
    _string_array(calibration["source_types"], f"{path}.source_types", nonempty=True)
    for field in ("domains", "languages", "length_strata", "entropy_strata"):
        _string_array(calibration[field], f"{path}.{field}")
    _boolean(calibration["repetitive_or_formatted_text_included"], f"{path}.repetitive_or_formatted_text_included")
    _boolean(calibration["code_included"], f"{path}.code_included")
    _text(calibration["near_duplicate_policy"], f"{path}.near_duplicate_policy")
    _text(calibration["tail_confidence_method"], f"{path}.tail_confidence_method")


def _validate_search(value: Any) -> dict[str, Any]:
    path = "watermark_study.search_spec"
    search = _mapping(value, path)
    _strict_keys(
        search,
        path,
        {
            "whole_document_test",
            "window_lengths",
            "window_stride",
            "alignment_offsets",
            "truncation_offsets",
            "key_ids_searched",
            "tokenizers_searched",
            "maximum_statistic_definition",
            "search_calibration_method",
            "post_selection_correction",
        },
    )
    _boolean(search["whole_document_test"], f"{path}.whole_document_test")
    _integer_array(search["window_lengths"], f"{path}.window_lengths", minimum=1)
    _integer(search["window_stride"], f"{path}.window_stride", allow_none=True)
    _integer_array(search["alignment_offsets"], f"{path}.alignment_offsets")
    _integer_array(search["truncation_offsets"], f"{path}.truncation_offsets")
    _string_array(search["key_ids_searched"], f"{path}.key_ids_searched")
    tokenizers = _array(search["tokenizers_searched"], f"{path}.tokenizers_searched")
    for index, digest in enumerate(tokenizers):
        _sha256(digest, f"{path}.tokenizers_searched[{index}]")
    if len(tokenizers) != len(set(tokenizers)):
        raise ProfileValidationError(f"{path}.tokenizers_searched must be unique")
    for field in ("maximum_statistic_definition", "search_calibration_method", "post_selection_correction"):
        _text(search[field], f"{path}.{field}")
    return search


def _validate_sample_plan(value: Any) -> dict[str, Any]:
    path = "watermark_study.sample_size_and_power"
    sample = _mapping(value, path)
    _strict_keys(
        sample,
        path,
        {
            "registered_cell_count",
            "null_outputs_per_cell",
            "release_outputs_per_cell",
            "positive_control_outputs",
            "retry_query_budget",
            "tail_claim_minimum_null_count",
            "minimum_detectable_effect",
            "target_power",
            "operational_fpr_targets",
            "power_analysis_sha256",
            "unsupported_tail_policy",
        },
    )
    for field in (
        "registered_cell_count",
        "null_outputs_per_cell",
        "release_outputs_per_cell",
        "tail_claim_minimum_null_count",
    ):
        _positive_integer(sample[field], f"{path}.{field}", allow_none=True)
    for field in ("positive_control_outputs", "retry_query_budget"):
        _integer(sample[field], f"{path}.{field}", allow_none=True)
    minimum_effect = _number(
        sample["minimum_detectable_effect"],
        f"{path}.minimum_detectable_effect",
        minimum=0.0,
        allow_none=True,
    )
    if minimum_effect is not None and minimum_effect <= 0.0:
        raise ProfileValidationError(f"{path}.minimum_detectable_effect must be positive")
    target_power = _number(
        sample["target_power"],
        f"{path}.target_power",
        minimum=0.0,
        maximum=1.0,
        allow_none=True,
    )
    if target_power is not None and not 0.5 < target_power < 1.0:
        raise ProfileValidationError(f"{path}.target_power must be in (0.5,1)")
    targets = _array(sample["operational_fpr_targets"], f"{path}.operational_fpr_targets")
    for index, target in enumerate(targets):
        parsed = _number(target, f"{path}.operational_fpr_targets[{index}]", minimum=0.0, maximum=1.0)
        if parsed is None or not 0.0 < parsed < 1.0:
            raise ProfileValidationError(f"{path}.operational_fpr_targets[{index}] must be in (0,1)")
    if len(targets) != len(set(targets)):
        raise ProfileValidationError(f"{path}.operational_fpr_targets must be unique")
    _sha256(sample["power_analysis_sha256"], f"{path}.power_analysis_sha256")
    if sample["unsupported_tail_policy"] != "refuse_claim":
        raise ProfileValidationError(f"{path}.unsupported_tail_policy must be refuse_claim")
    return sample


def _validate_quality(value: Any) -> dict[str, Any]:
    path = "watermark_study.quality_study"
    quality = _mapping(value, path)
    _strict_keys(
        quality,
        path,
        {
            "enabled",
            "decision_role",
            "paired_prompt_assignment",
            "paired_prompt_count",
            "quality_prompt_manifest_sha256",
            "metrics",
            "length_and_entropy_stratified",
            "noninferiority_margins_sha256",
            "simultaneous_confidence_method",
            "quality_evidence_sha256",
        },
    )
    if quality["enabled"] is not True or quality["paired_prompt_assignment"] is not True:
        raise ProfileValidationError("watermark quality study must use enabled paired prompt assignment")
    if quality["decision_role"] != "exploratory_non_decision_bearing":
        raise ProfileValidationError("watermark quality endpoints must be explicitly exploratory in profile 1.1")
    _positive_integer(quality["paired_prompt_count"], f"{path}.paired_prompt_count", allow_none=True)
    _sha256(quality["quality_prompt_manifest_sha256"], f"{path}.quality_prompt_manifest_sha256")
    metrics = set(_string_array(quality["metrics"], f"{path}.metrics", nonempty=True))
    if metrics != REQUIRED_QUALITY_METRICS:
        raise ProfileValidationError("watermark quality study must register the complete metric set")
    if quality["length_and_entropy_stratified"] is not True:
        raise ProfileValidationError("watermark quality study must stratify by length and entropy")
    _sha256(quality["noninferiority_margins_sha256"], f"{path}.noninferiority_margins_sha256")
    _text(quality["simultaneous_confidence_method"], f"{path}.simultaneous_confidence_method")
    _sha256(quality["quality_evidence_sha256"], f"{path}.quality_evidence_sha256")
    return quality


def _validate_attacks(required_value: Any, matrix_value: Any) -> list[dict[str, Any]]:
    required = set(_string_array(required_value, "watermark_study.required_attack_types", nonempty=True))
    if required != REQUIRED_WATERMARK_ATTACK_TYPES:
        raise ProfileValidationError("watermark_study.required_attack_types is incomplete")
    matrix = _array(matrix_value, "watermark_study.attack_matrix", nonempty=True)
    attack_ids: list[str] = []
    attack_types: list[str] = []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(matrix):
        path = f"watermark_study.attack_matrix[{index}]"
        attack = _mapping(item, path)
        _strict_keys(
            attack,
            path,
            {
                "attack_id",
                "attack_type",
                "decision_role",
                "source_sha256",
                "model_query_budget",
                "detector_query_budget",
                "observed_watermarked_token_budget",
                "quality_constraint",
                "stopping_rule",
            },
        )
        attack_ids.append(_text(attack["attack_id"], f"{path}.attack_id"))
        attack_types.append(_text(attack["attack_type"], f"{path}.attack_type"))
        if attack["decision_role"] != "exploratory_non_decision_bearing":
            raise ProfileValidationError(f"{path}.decision_role must be exploratory_non_decision_bearing")
        _sha256(attack["source_sha256"], f"{path}.source_sha256")
        for field in ("model_query_budget", "detector_query_budget", "observed_watermarked_token_budget"):
            _integer(attack[field], f"{path}.{field}", allow_none=True)
        _text(attack["quality_constraint"], f"{path}.quality_constraint")
        _text(attack["stopping_rule"], f"{path}.stopping_rule")
        records.append(attack)
    if len(attack_ids) != len(set(attack_ids)):
        raise ProfileValidationError("watermark_study.attack_matrix has duplicate attack IDs")
    if len(attack_types) != len(set(attack_types)):
        raise ProfileValidationError("watermark_study.attack_matrix has duplicate attack types")
    if set(attack_types) != required:
        raise ProfileValidationError("watermark_study.attack_matrix omits required adaptive attacks")
    return records


def _validate_watermark(value: Any) -> dict[str, Any]:
    watermark = _mapping(value, "watermark_study")
    _strict_keys(
        watermark,
        "watermark_study",
        {
            "study_type",
            "scheme",
            "formal_claims",
            "hypotheses",
            "detector",
            "normalization_spec_sha256",
            "null_calibration",
            "search_spec",
            "sample_size_and_power",
            "primary_metrics",
            "secondary_metrics",
            "quality_study",
            "required_attack_types",
            "attack_matrix",
            "interpretation",
        },
    )
    if watermark["study_type"] != "output_watermark_detection":
        raise ProfileValidationError("watermark_study.study_type is unsupported")
    _validate_scheme(watermark["scheme"])
    _validate_formal_claims(watermark["formal_claims"])
    _validate_hypotheses(watermark["hypotheses"])
    _validate_detector(watermark["detector"])
    _sha256(watermark["normalization_spec_sha256"], "watermark_study.normalization_spec_sha256")
    _validate_null_calibration(watermark["null_calibration"])
    _validate_search(watermark["search_spec"])
    _validate_sample_plan(watermark["sample_size_and_power"])
    primary = set(_string_array(watermark["primary_metrics"], "watermark_study.primary_metrics", nonempty=True))
    if primary != {
        "false_positive_rate_with_simultaneous_upper_bound",
        "true_positive_rate_with_simultaneous_lower_bound",
    }:
        raise ProfileValidationError("watermark_study.primary_metrics must contain the two registered bound metrics")
    _string_array(watermark["secondary_metrics"], "watermark_study.secondary_metrics")
    _validate_quality(watermark["quality_study"])
    _validate_attacks(watermark["required_attack_types"], watermark["attack_matrix"])
    _text(watermark["interpretation"], "watermark_study.interpretation")
    return watermark


def _validate_canary(value: Any) -> dict[str, Any]:
    path = "canary_study"
    canary = _mapping(value, path)
    _strict_keys(
        canary,
        path,
        {
            "study_type",
            "mode",
            "primary_hypothesis",
            "canary_generator_spec_sha256",
            "canary_randomness_space_bits",
            "plaintext_storage",
            "public_commitment_type",
            "commitment_key_id",
            "inclusion_randomization",
            "member_canary_count",
            "nonmember_decoy_count",
            "primary_inferential_unit",
            "training_insertions_per_member_canary",
            "insertion_count_assignment",
            "prefix_lengths_tokens",
            "queries_per_canary_total",
            "normalization",
            "primary_metric",
            "primary_confidence_output",
            "secondary_metrics",
            "supplementary_rank_exposure",
            "query_policy_sha256",
            "adaptive_queries",
            "all_retries_count_as_attack_opportunities",
            "controls",
            "contamination_scan",
            "secret_safety",
            "interpretation",
        },
    )
    if canary["study_type"] != "randomized_in_out_canary_audit" or canary["mode"] != "randomized_in_out":
        raise ProfileValidationError("canary_study must use randomized_in_out mode")
    hypothesis = _mapping(canary["primary_hypothesis"], f"{path}.primary_hypothesis")
    _strict_keys(hypothesis, f"{path}.primary_hypothesis", {"null", "alternative"})
    _text(hypothesis["null"], f"{path}.primary_hypothesis.null")
    _text(hypothesis["alternative"], f"{path}.primary_hypothesis.alternative")
    _sha256(canary["canary_generator_spec_sha256"], f"{path}.canary_generator_spec_sha256")
    _positive_integer(canary["canary_randomness_space_bits"], f"{path}.canary_randomness_space_bits")
    for field in (
        "plaintext_storage",
        "public_commitment_type",
        "commitment_key_id",
        "primary_inferential_unit",
        "insertion_count_assignment",
        "normalization",
        "primary_metric",
        "primary_confidence_output",
        "interpretation",
    ):
        _text(canary[field], f"{path}.{field}")

    inclusion_path = f"{path}.inclusion_randomization"
    inclusion = _mapping(canary["inclusion_randomization"], inclusion_path)
    _strict_keys(
        inclusion,
        inclusion_path,
        {
            "assignment_design",
            "inclusion_vector_commitment_sha256",
            "assignment_roster_sha256",
            "independent_inclusion_bits",
            "withheld_from_scoring_until_scores_and_guesses_frozen",
            "score_and_guess_freeze_attestation_sha256",
        },
    )
    if inclusion["assignment_design"] != "complete_randomization_fixed_arm_sizes":
        raise ProfileValidationError("canary fixed arm counts require complete_randomization_fixed_arm_sizes")
    if inclusion["independent_inclusion_bits"] is not False:
        raise ProfileValidationError("fixed member/nonmember counts cannot claim independent inclusion bits")
    if inclusion["withheld_from_scoring_until_scores_and_guesses_frozen"] is not True:
        raise ProfileValidationError("canary inclusion assignment must remain blinded until scoring is frozen")
    for field in (
        "inclusion_vector_commitment_sha256",
        "assignment_roster_sha256",
        "score_and_guess_freeze_attestation_sha256",
    ):
        _sha256(inclusion[field], f"{inclusion_path}.{field}")

    members = _positive_integer(canary["member_canary_count"], f"{path}.member_canary_count")
    _positive_integer(canary["nonmember_decoy_count"], f"{path}.nonmember_decoy_count")
    doses = _integer_array(
        canary["training_insertions_per_member_canary"],
        f"{path}.training_insertions_per_member_canary",
        minimum=1,
        nonempty=True,
    )
    assert members is not None
    if members % len(doses) != 0:
        raise ProfileValidationError("member_canary_count must permit integral equal allocation across insertion doses")
    _integer_array(canary["prefix_lengths_tokens"], f"{path}.prefix_lengths_tokens")
    _positive_integer(canary["queries_per_canary_total"], f"{path}.queries_per_canary_total")
    _string_array(canary["secondary_metrics"], f"{path}.secondary_metrics")
    _sha256(canary["query_policy_sha256"], f"{path}.query_policy_sha256")
    _boolean(canary["adaptive_queries"], f"{path}.adaptive_queries")
    if canary["all_retries_count_as_attack_opportunities"] is not True:
        raise ProfileValidationError("all canary retries must count as attack opportunities")
    _string_array(canary["controls"], f"{path}.controls", nonempty=True)

    rank_path = f"{path}.supplementary_rank_exposure"
    rank = _mapping(canary["supplementary_rank_exposure"], rank_path)
    _strict_keys(
        rank,
        rank_path,
        {
            "enabled",
            "formula",
            "randomness_space_sha256",
            "exact_rank_requirement",
            "estimated_rank_uncertainty_required",
            "when_api_lacks_complete_sequence_scoring",
            "recipient_realizability",
        },
    )
    _boolean(rank["enabled"], f"{rank_path}.enabled")
    for field in ("formula", "exact_rank_requirement", "when_api_lacks_complete_sequence_scoring"):
        _text(rank[field], f"{rank_path}.{field}")
    _sha256(rank["randomness_space_sha256"], f"{rank_path}.randomness_space_sha256")
    if rank["estimated_rank_uncertainty_required"] is not True:
        raise ProfileValidationError("estimated rank exposure must include uncertainty")
    if rank["recipient_realizability"] != "auditor_only_unless_bound_interface_exposes_complete_sequence_scoring":
        raise ProfileValidationError("rank exposure realizability is overstated")

    contamination_path = f"{path}.contamination_scan"
    contamination = _mapping(canary["contamination_scan"], contamination_path)
    _strict_keys(
        contamination,
        contamination_path,
        {
            "training_corpus_sha256",
            "retrieval_corpus_sha256",
            "evaluation_and_prompt_corpora_sha256",
            "scan_result_artifact_sha256",
            "fail_on_excluded_canary_or_interface_contamination",
        },
    )
    _sha256(contamination["training_corpus_sha256"], f"{contamination_path}.training_corpus_sha256")
    _sha256(
        contamination["retrieval_corpus_sha256"],
        f"{contamination_path}.retrieval_corpus_sha256",
        allow_none=True,
    )
    _sha256(
        contamination["evaluation_and_prompt_corpora_sha256"],
        f"{contamination_path}.evaluation_and_prompt_corpora_sha256",
    )
    _sha256(contamination["scan_result_artifact_sha256"], f"{contamination_path}.scan_result_artifact_sha256")
    if contamination["fail_on_excluded_canary_or_interface_contamination"] is not True:
        raise ProfileValidationError("canary contamination scan must fail closed")

    safety_path = f"{path}.secret_safety"
    safety = _mapping(canary["secret_safety"], safety_path)
    _strict_keys(
        safety,
        safety_path,
        {
            "synthetic_only",
            "personal_data_forbidden",
            "credentials_and_production_secrets_forbidden",
            "executable_instructions_urls_and_tool_tokens_forbidden",
            "plaintext_in_repository_or_reports_forbidden",
            "data_owner_approval_required_before_training_insertion",
        },
    )
    if any(item is not True for item in safety.values()):
        raise ProfileValidationError("every canary secret-safety control must be true")
    return canary


def _validate_naturalistic(value: Any) -> dict[str, Any]:
    path = "naturalistic_extraction_probe"
    probe = _mapping(value, path)
    _strict_keys(probe, path, {"enabled", "treated_as_canary", "reason", "profile_sha256", "query_budget"})
    enabled = _boolean(probe["enabled"], f"{path}.enabled")
    if probe["treated_as_canary"] is not False:
        raise ProfileValidationError("naturalistic extraction probes must not be relabelled as canaries")
    _text(probe["reason"], f"{path}.reason")
    digest = _sha256(probe["profile_sha256"], f"{path}.profile_sha256", allow_none=True)
    query_budget = _integer(probe["query_budget"], f"{path}.query_budget")
    if not enabled and (digest is not None or query_budget != 0):
        raise ProfileValidationError("disabled naturalistic probe must have null profile and zero query budget")
    if enabled and (digest is None or query_budget is None or query_budget <= 0):
        raise ProfileValidationError("enabled naturalistic probe requires a bound profile and positive query budget")
    return probe


def _validate_collection_controls(value: Any) -> dict[str, Any]:
    path = "collection_controls"
    controls = _mapping(value, path)
    _strict_keys(
        controls,
        path,
        {
            "endpoint_attestation_required_throughout_collection",
            "abort_on_binding_mismatch_or_expiry",
            "development_and_audit_data_disjoint",
            "record_complete_transcript",
            "record_tools_retrieval_memory_and_resets",
            "record_failures_refusals_retries_and_exclusions",
            "maximum_concurrent_sessions",
            "random_seed_commitment_sha256",
        },
    )
    for field in (
        "endpoint_attestation_required_throughout_collection",
        "abort_on_binding_mismatch_or_expiry",
        "development_and_audit_data_disjoint",
        "record_complete_transcript",
        "record_tools_retrieval_memory_and_resets",
        "record_failures_refusals_retries_and_exclusions",
    ):
        if controls[field] is not True:
            raise ProfileValidationError(f"{path}.{field} must be true")
    _positive_integer(controls["maximum_concurrent_sessions"], f"{path}.maximum_concurrent_sessions", allow_none=True)
    _sha256(controls["random_seed_commitment_sha256"], f"{path}.random_seed_commitment_sha256")
    return controls


def _validate_provenance(value: Any) -> None:
    path = "analyzer_provenance"
    provenance = _mapping(value, path)
    _strict_keys(
        provenance,
        path,
        {
            "tool",
            "tool_version",
            "source_path",
            "source_sha256",
            "required_binding_profile",
            "required_binding_profile_authority",
            "implementation_status",
            "required_bound_sections",
            "source_commit_sha256",
            "container_image_digest",
            "dependency_lock_sha256",
            "runtime_manifest_sha256",
            "hardware_class",
            "approval_manifest_sha256",
        },
    )
    for field in (
        "tool",
        "tool_version",
        "source_path",
        "required_binding_profile",
        "required_binding_profile_authority",
        "hardware_class",
    ):
        _text(provenance[field], f"{path}.{field}")
    for field in (
        "source_sha256",
        "source_commit_sha256",
        "dependency_lock_sha256",
        "runtime_manifest_sha256",
        "approval_manifest_sha256",
    ):
        _sha256(provenance[field], f"{path}.{field}")
    _sha256(provenance["container_image_digest"], f"{path}.container_image_digest", prefixed=True)
    if provenance["implementation_status"] != "profile_linter_only_not_core_enforced":
        raise ProfileValidationError("analyzer provenance must disclose that core enforcement is not implemented")
    sections = set(_string_array(provenance["required_bound_sections"], f"{path}.required_bound_sections", nonempty=True))
    if sections != REQUIRED_BOUND_SECTIONS:
        raise ProfileValidationError("analyzer_provenance.required_bound_sections must cover the complete payload")


def _zero_fp_minimum_trials(target_fpr: float, confidence: float) -> int:
    return int(math.ceil(math.log1p(-confidence) / math.log1p(-target_fpr)))


def _validate_collection_ready(profile: dict[str, Any]) -> None:
    if profile["protocol_status"] != "approved_for_collection":
        raise ProfileValidationError("collection-ready profile must have protocol_status=approved_for_collection")
    for path, value in _walk(profile):
        if path == "profile.placeholder_policy":
            continue
        if value is None and path not in OPTIONAL_COLLECTION_NULL_PATHS:
            raise ProfileValidationError(f"collection-ready profile contains an unresolved null at {path}")
        if isinstance(value, str):
            lowered = value.lower()
            if (
                not value.strip()
                or value in {ZERO_SHA256, f"sha256:{ZERO_SHA256}"}
                or value.startswith("replace-")
                or "placeholder" in lowered
            ):
                raise ProfileValidationError(f"collection-ready profile contains a placeholder at {path}")

    preregistered = _timestamp(profile["preregistered_at"], "preregistered_at")
    valid_until = _timestamp(profile["release_binding"]["valid_until"], "release_binding.valid_until")
    assert preregistered is not None and valid_until is not None
    now = datetime.now(timezone.utc)
    if preregistered > now + CLOCK_SKEW_TOLERANCE:
        raise ProfileValidationError("preregistered_at is in the future beyond the five-minute clock-skew allowance")
    if preregistered >= valid_until:
        raise ProfileValidationError("preregistered_at must precede release_binding.valid_until")
    if valid_until <= now:
        raise ProfileValidationError("collection-ready profile is expired")

    components = profile["release_binding"]["llm_protocol_components"]
    lifetime_budget = _positive_integer(
        components["maximum_lifetime_queries"],
        "release_binding.llm_protocol_components.maximum_lifetime_queries",
    )
    _positive_integer(
        components["maximum_session_tokens"],
        "release_binding.llm_protocol_components.maximum_session_tokens",
    )
    protocol_concurrency = _positive_integer(
        components["maximum_concurrent_sessions"],
        "release_binding.llm_protocol_components.maximum_concurrent_sessions",
    )
    collection_concurrency = _positive_integer(
        profile["collection_controls"]["maximum_concurrent_sessions"],
        "collection_controls.maximum_concurrent_sessions",
    )
    assert protocol_concurrency is not None and collection_concurrency is not None
    if collection_concurrency > protocol_concurrency:
        raise ProfileValidationError("collection concurrency exceeds the bound interface concurrency")

    watermark = profile["watermark_study"]
    scheme = watermark["scheme"]
    detector = watermark["detector"]
    search = watermark["search_spec"]
    sample = watermark["sample_size_and_power"]
    scheme_keys = _positive_integer(scheme["key_count"], "watermark_study.scheme.key_count")
    detector_keys = _positive_integer(detector["key_count"], "watermark_study.detector.key_count")
    if scheme_keys != detector_keys:
        raise ProfileValidationError("watermark scheme and detector key counts must match")
    if detector["compromise_status"] != "uncompromised":
        raise ProfileValidationError("collection-ready detector key must be uncompromised")
    if detector["revocation_status"] != "active":
        raise ProfileValidationError("collection-ready detector key must be active and unrevoked")
    if detector["detector_api_visibility"] not in {"public", "private", "offline"}:
        raise ProfileValidationError("watermark detector API visibility is unsupported")
    if detector["detector_api_output"] not in {"binary", "score", "z_score", "p_value"}:
        raise ProfileValidationError("watermark detector API output is unsupported")
    release_tokenizer = components["tokenizer_sha256"]
    if scheme["tokenizer_sha256"] != release_tokenizer:
        raise ProfileValidationError("watermark scheme tokenizer must match the bound release tokenizer")
    searched_tokenizers = _array(search["tokenizers_searched"], "watermark_study.search_spec.tokenizers_searched", nonempty=True)
    if release_tokenizer not in searched_tokenizers:
        raise ProfileValidationError("watermark search must include the bound release tokenizer")
    searched_keys = _string_array(search["key_ids_searched"], "watermark_study.search_spec.key_ids_searched", nonempty=True)
    if len(searched_keys) != scheme_keys:
        raise ProfileValidationError("watermark searched key count must equal the registered scheme key count")
    for path, values in (
        ("watermark_study.detector.custody_roles", detector["custody_roles"]),
        ("watermark_study.null_calibration.domains", watermark["null_calibration"]["domains"]),
        ("watermark_study.null_calibration.languages", watermark["null_calibration"]["languages"]),
        ("watermark_study.null_calibration.length_strata", watermark["null_calibration"]["length_strata"]),
        ("watermark_study.null_calibration.entropy_strata", watermark["null_calibration"]["entropy_strata"]),
    ):
        _array(values, path, nonempty=True)

    cell_count = _positive_integer(sample["registered_cell_count"], "watermark_study.sample_size_and_power.registered_cell_count")
    null_per_cell = _positive_integer(sample["null_outputs_per_cell"], "watermark_study.sample_size_and_power.null_outputs_per_cell")
    release_per_cell = _positive_integer(sample["release_outputs_per_cell"], "watermark_study.sample_size_and_power.release_outputs_per_cell")
    positive_controls = _integer(sample["positive_control_outputs"], "watermark_study.sample_size_and_power.positive_control_outputs")
    retry_budget = _integer(sample["retry_query_budget"], "watermark_study.sample_size_and_power.retry_query_budget")
    declared_minimum = _positive_integer(
        sample["tail_claim_minimum_null_count"],
        "watermark_study.sample_size_and_power.tail_claim_minimum_null_count",
    )
    minimum_effect = _number(
        sample["minimum_detectable_effect"],
        "watermark_study.sample_size_and_power.minimum_detectable_effect",
    )
    target_power = _number(sample["target_power"], "watermark_study.sample_size_and_power.target_power")
    if minimum_effect is None or minimum_effect <= 0.0:
        raise ProfileValidationError("watermark minimum_detectable_effect must be positive")
    if target_power is None or not 0.5 < target_power < 1.0:
        raise ProfileValidationError("watermark target_power must be in (0.5,1)")
    operational_fpr = _number(
        profile["decision_games"]["watermark"]["operational_false_positive_target"],
        "decision_games.watermark.operational_false_positive_target",
    )
    assert operational_fpr is not None
    targets = [float(value) for value in sample["operational_fpr_targets"]]
    if not any(math.isclose(value, operational_fpr, rel_tol=0.0, abs_tol=1e-15) for value in targets):
        raise ProfileValidationError("operational_fpr_targets must include the decision-game target")
    family = profile["multiplicity"]["watermark_family"]
    family_alpha = float(family["familywise_error_rate_alpha"])
    family_size = int(family["family_size"])
    per_bound_confidence = 1.0 - family_alpha / family_size
    minimum_for_tail = _zero_fp_minimum_trials(operational_fpr, per_bound_confidence)
    assert null_per_cell is not None and declared_minimum is not None
    if declared_minimum < minimum_for_tail or null_per_cell < minimum_for_tail or null_per_cell < declared_minimum:
        raise ProfileValidationError(
            "watermark null sample cannot support the registered operational FPR with a simultaneous upper bound"
        )

    quality = watermark["quality_study"]
    quality_pairs = _positive_integer(quality["paired_prompt_count"], "watermark_study.quality_study.paired_prompt_count")
    attacks = watermark["attack_matrix"]
    if any(int(item["observed_watermarked_token_budget"]) <= 0 for item in attacks):
        raise ProfileValidationError("every adaptive attack requires a positive observed-watermarked-token budget")
    model_attack_queries = sum(int(item["model_query_budget"]) for item in attacks)
    detector_attack_queries = sum(int(item["detector_query_budget"]) for item in attacks)
    detector_budget = _integer(
        detector["detector_api_total_query_budget"],
        "watermark_study.detector.detector_api_total_query_budget",
    )
    if detector_budget is None or detector_attack_queries > detector_budget:
        raise ProfileValidationError("adaptive attacks exceed the registered detector query budget")
    watermark_queries = (
        int(cell_count) * (int(null_per_cell) + int(release_per_cell))
        + int(positive_controls)
        + int(retry_budget)
        + 2 * int(quality_pairs)
        + model_attack_queries
    )
    generation_budget = _positive_integer(
        scheme["maximum_key_or_generation_budget"],
        "watermark_study.scheme.maximum_key_or_generation_budget",
    )
    if generation_budget is None or watermark_queries > generation_budget:
        raise ProfileValidationError("watermark query plan exceeds the registered scheme generation budget")
    if profile["decision_games"]["watermark"]["query_budget"] != watermark_queries:
        raise ProfileValidationError("watermark decision-game query_budget does not match the complete registered plan")

    canary = profile["canary_study"]
    canary_queries = (
        int(canary["member_canary_count"]) + int(canary["nonmember_decoy_count"])
    ) * int(canary["queries_per_canary_total"])
    if profile["decision_games"]["canary"]["query_budget"] != canary_queries:
        raise ProfileValidationError("canary decision-game query_budget does not match the registered canary plan")
    naturalistic_queries = int(profile["naturalistic_extraction_probe"]["query_budget"])
    total_queries = watermark_queries + canary_queries + naturalistic_queries
    assert lifetime_budget is not None
    if total_queries > lifetime_budget:
        raise ProfileValidationError("complete registered query plan exceeds maximum_lifetime_queries")


def validate_profile(value: Any, *, collection_ready: bool = False) -> dict[str, Any]:
    """Validate a template or, with ``collection_ready``, a filled preregistration."""

    profile = _mapping(value, "profile")
    _strict_keys(profile, "profile", REQUIRED_TOP_LEVEL)
    for path, item in _walk(profile):
        if isinstance(item, float) and not math.isfinite(item):
            raise ProfileValidationError(f"{path} must be finite")
    if profile["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ProfileValidationError(f"schema_version must be {PROFILE_SCHEMA_VERSION}")
    if profile["profile_type"] != "llm_watermark_canary_preregistration":
        raise ProfileValidationError("profile_type is unsupported")
    for field in ("protocol_id", "protocol_version", "study_id", "protocol_status", "placeholder_policy", "assessor_id"):
        _text(profile[field], field)
    _timestamp(profile["preregistered_at"], "preregistered_at", allow_none=True)

    semantics = _mapping(profile["decision_semantics"], "decision_semantics")
    _strict_keys(
        semantics,
        "decision_semantics",
        {
            "evidence_classes",
            "can_block",
            "block_scope",
            "watermark_can_block_privacy",
            "canary_validated_floor_can_block",
            "can_clear",
            "null_result",
        },
    )
    if set(_string_array(semantics["evidence_classes"], "decision_semantics.evidence_classes")) != {"floor", "screen"}:
        raise ProfileValidationError("decision_semantics.evidence_classes must be floor and screen")
    if semantics["can_block"] is not True or semantics["canary_validated_floor_can_block"] is not True:
        raise ProfileValidationError("validated canary floors must retain block semantics")
    _text(semantics["block_scope"], "decision_semantics.block_scope")
    if semantics["watermark_can_block_privacy"] is not False:
        raise ProfileValidationError("watermark evidence cannot block privacy")
    if semantics["can_clear"] is not False:
        raise ProfileValidationError("LLM preregistration must set can_clear=false")
    if semantics["null_result"] != "inconclusive_never_clear":
        raise ProfileValidationError("null results must remain inconclusive and never clear")

    _validate_release_binding(profile["release_binding"])
    _validate_decision_games(profile["decision_games"])
    _validate_partitions(profile["partitions"])
    _validate_multiplicity(profile["multiplicity"])
    _validate_watermark(profile["watermark_study"])
    _validate_canary(profile["canary_study"])
    _validate_naturalistic(profile["naturalistic_extraction_probe"])
    _validate_collection_controls(profile["collection_controls"])
    _validate_provenance(profile["analyzer_provenance"])

    evidence = set(
        _string_array(
            profile["required_evidence_artifacts"],
            "required_evidence_artifacts",
            nonempty=True,
        )
    )
    if evidence != REQUIRED_EVIDENCE_ARTIFACTS:
        raise ProfileValidationError(
            "required_evidence_artifacts must enumerate the complete post-collection digest contract"
        )
    outputs = set(_string_array(profile["mandatory_output_fields"], "mandatory_output_fields", nonempty=True))
    if outputs != REQUIRED_OUTPUT_FIELDS:
        raise ProfileValidationError("mandatory_output_fields must contain the complete registered output contract")
    _validate_digest_syntax(profile)

    if collection_ready:
        _validate_collection_ready(profile)
    return profile


def _reject_json_constant(value: str) -> None:
    raise ProfileValidationError(f"profile contains non-finite JSON constant {value}")


def load_profile(path: Path, *, collection_ready: bool = False) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileValidationError(f"profile is not valid strict UTF-8 JSON: {path}") from error
    return validate_profile(value, collection_ready=collection_ready)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument(
        "--collection-ready",
        action="store_true",
        help="reject placeholders, expired bindings, unsupported tail plans, and complete query-budget overflow",
    )
    args = parser.parse_args()
    try:
        profile = load_profile(args.profile, collection_ready=args.collection_ready)
    except (OSError, ProfileValidationError) as error:
        print(f"error: {error}")
        return 2
    print(json.dumps({
        "status": "valid",
        "schema_version": profile["schema_version"],
        "protocol_id": profile["protocol_id"],
        "collection_ready_checked": args.collection_ready,
        "can_clear": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
