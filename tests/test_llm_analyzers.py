from __future__ import annotations

import json
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from pydantic import ValidationError

from model_release_assurance.analyzers.llm_canary import LlmCanaryAnalyzer
from model_release_assurance.analyzers.llm_watermark import LlmWatermarkAnalyzer
from model_release_assurance.analyzers.attack import (
    bonferroni_per_bound_confidence,
    clopper_pearson_lower,
    clopper_pearson_upper,
)
from model_release_assurance.models import (
    AnalyzerProvenance,
    AssessmentRequest,
    EvidenceClass,
    EvidenceContext,
    InterfaceContract,
    LlmCanaryInput,
    LlmWatermarkInput,
)


ROOT = Path(__file__).resolve().parents[1]


def interactive_release_and_threat():
    raw = json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
    request = AssessmentRequest.model_validate(raw)
    interface_raw = {
        "schema_version": "3.0",
        "protocol_type": "interactive_llm",
        "access": "text",
        "outputs": ["text"],
        "output_channels": {
            "aggregates": False,
            "labels": False,
            "scores": False,
            "probabilities": False,
            "logits": False,
            "explanations": False,
            "text": True,
            "embeddings": False,
            "gradients": False,
            "parameters": False,
            "downloadable_files": [],
            "shipped_summary_metadata": [],
            "custom_channels": [],
        },
        "precision_bits": 16,
        "query_budget": 100,
        "adaptive_queries": True,
        "authenticated": True,
        "rate_limited": True,
        "rate_limit": {
            "enabled": True,
            "scope": "per_identity",
            "requests_per_window": 100,
            "window_seconds": 3600,
            "burst_capacity": 5,
            "retry_after_exposed": True,
            "enforcement": "shared_strong",
            "custom_parameters": {},
        },
        "timing": {
            "recipient_observable": True,
            "measurement_resolution_milliseconds": 1.0,
            "includes_queue_time": True,
            "mitigation": "none",
            "mitigation_parameters": {},
        },
        "errors": {
            "transport_status": "http",
            "documented_status_codes": ["200", "400", "401", "429", "500"],
            "error_content": "opaque",
            "error_schema_sha256": None,
            "retry_metadata": True,
        },
        "execution": {
            "batching": "none",
            "maximum_batch_size": 1,
            "maximum_concurrent_requests": 1,
            "cross_request_state": "none",
            "cross_request_state_ttl_seconds": None,
        },
        "access_paths": {
            "side_channels": ["timing", "status_code", "error_content"],
            "custom_side_channels": [],
            "admin_access": "none",
            "admin_capabilities": [],
            "local_access": "none",
            "local_capabilities": [],
        },
        "serialization": {
            "formats": ["json"],
            "media_types": ["application/json"],
            "encodings": ["utf-8"],
            "compression": [],
            "schema_sha256": None,
            "endianness": "not_applicable",
        },
        "llm_protocol": {
            "schema_version": "1.0",
            "model_provider": "test provider",
            "model_identifier": "test model",
            "model_version": "2026-08-13",
            "tokenizer_sha256": "1" * 64,
            "decoding_parameters": {"temperature": 0.0},
            "system_prompt_sha256": "2" * 64,
            "adapter_sha256s": [],
            "retrieval_corpus_sha256": None,
            "retriever_config_sha256": None,
            "tool_names": [],
            "tool_policy_sha256": None,
            "memory_mode": "none",
            "memory_ttl_seconds": None,
            "filter_bundle_sha256": None,
            "logging_mode": "security_only",
            "provider_retention_days": 0,
            "maximum_session_tokens": 4096,
            "maximum_lifetime_queries": 100,
            "maximum_concurrent_sessions": 1,
            "reset_semantics": "fresh context per authenticated session",
            "update_policy": "versioned_reassessment_required",
            "valid_until": "2099-01-01T00:00:00Z",
        },
    }
    interface = InterfaceContract.model_validate(interface_raw)
    release = request.release.model_copy(update={"interface": interface, "expires_at": interface.llm_protocol.valid_until})
    threat = next(item for item in request.threats if item.decision_metric == "equal_prior_membership_success")
    context = next(item.evidence_context for item in request.analyzer_inputs if item.threat_id == threat.threat_id)
    return release, threat, context


def provenance() -> AnalyzerProvenance:
    return AnalyzerProvenance(
        tool="isolated-llm-worker",
        tool_version="1.0",
        producer={
            "service_id": "mra.analyzer.llm-test",
            "service_version": "1.0.0",
            "implementation_sha256": "b" * 64,
            "configuration_sha256": "c" * 64,
        },
        configuration_path="llm-analyzer-config.json",
        source_path="evidence.json",
        source_sha256="a" * 64,
        bound_fields=("analyzer",),
    )


class LlmAnalyzerTests(unittest.TestCase):
    def test_valid_randomized_canary_is_a_blocking_floor_but_never_clears(self) -> None:
        release, threat, context = interactive_release_and_threat()
        value = LlmCanaryInput(
            threat_id=threat.threat_id,
            population_scope_id=threat.population_scope_id,
            study_id="canary-study-1",
            preregistration_sha256="b" * 64,
            transcript_manifest_sha256="c" * 64,
            sealed_assignment_sha256="d" * 64,
            metric="equal_prior_membership_success",
            member_successes=40,
            member_canaries=50,
            decoy_successes=0,
            nonmember_decoys=500,
            assignment_randomized=True,
            scoring_frozen_before_unblinding=True,
            exact_match_pre_registered=True,
            audit_disjoint=True,
            raw_counts_retained=True,
            contamination_scan_passed=True,
            complete_protocol_binding=True,
            recipient_realizable=True,
            evidence_context=context,
            provenance=provenance(),
        )
        record = LlmCanaryAnalyzer().analyze(release, threat, value)[0]
        self.assertEqual(record.evidence_class, EvidenceClass.FLOOR)
        self.assertTrue(record.can_block)
        self.assertFalse(record.can_clear)
        self.assertIsNotNone(record.lower)

    def test_equal_prior_canary_composition_is_rounded_outward(self) -> None:
        release, threat, context = interactive_release_and_threat()
        value = LlmCanaryInput(
            threat_id=threat.threat_id,
            population_scope_id=threat.population_scope_id,
            study_id="canary-rounding-boundary",
            preregistration_sha256="b" * 64,
            transcript_manifest_sha256="c" * 64,
            sealed_assignment_sha256="d" * 64,
            metric="equal_prior_membership_success",
            member_successes=2,
            member_canaries=3,
            decoy_successes=2,
            nonmember_decoys=3,
            assignment_randomized=True,
            scoring_frozen_before_unblinding=True,
            exact_match_pre_registered=True,
            audit_disjoint=True,
            raw_counts_retained=True,
            contamination_scan_passed=True,
            complete_protocol_binding=True,
            recipient_realizable=True,
            evidence_context=context,
            provenance=provenance(),
        )

        record = LlmCanaryAnalyzer().analyze(release, threat, value)[0]
        confidence = bonferroni_per_bound_confidence(0.95, 2)
        member_lower = clopper_pearson_lower(2, 3, confidence)
        decoy_upper = clopper_pearson_upper(2, 3, confidence)
        exact_composite = (
            Fraction(Decimal(str(member_lower)))
            + Fraction(1)
            - Fraction(Decimal(str(decoy_upper)))
        ) / 2
        unsafe_binary_composite = 0.5 * (member_lower + 1.0 - decoy_upper)

        self.assertGreater(
            Fraction(Decimal(str(unsafe_binary_composite))),
            exact_composite,
        )
        self.assertLessEqual(
            Fraction(Decimal(str(record.lower))),
            exact_composite,
        )
        self.assertLessEqual(record.lower, 0.05135154135492936)

    def test_canary_failure_or_contamination_is_only_a_screen(self) -> None:
        release, threat, context = interactive_release_and_threat()
        value = LlmCanaryInput(
            threat_id=threat.threat_id,
            population_scope_id=threat.population_scope_id,
            study_id="canary-study-2",
            preregistration_sha256="b" * 64,
            transcript_manifest_sha256="c" * 64,
            sealed_assignment_sha256="d" * 64,
            metric="equal_prior_membership_success",
            member_successes=0,
            member_canaries=50,
            decoy_successes=0,
            nonmember_decoys=500,
            assignment_randomized=True,
            scoring_frozen_before_unblinding=True,
            exact_match_pre_registered=True,
            audit_disjoint=True,
            raw_counts_retained=True,
            contamination_scan_passed=False,
            complete_protocol_binding=True,
            recipient_realizable=True,
            evidence_context=context,
            provenance=provenance(),
        )
        record = LlmCanaryAnalyzer().analyze(release, threat, value)[0]
        self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(record.can_block)
        self.assertFalse(record.can_clear)

    def test_watermark_is_always_non_decision_bearing(self) -> None:
        release, threat, context = interactive_release_and_threat()
        value = LlmWatermarkInput(
            threat_id=threat.threat_id,
            population_scope_id=threat.population_scope_id,
            study_id="watermark-study-1",
            preregistration_sha256="b" * 64,
            transcript_manifest_sha256="c" * 64,
            detector_id="registered-detector",
            detector_version="1.0",
            opaque_key_id="key-7",
            detected_outputs=95,
            eligible_outputs=100,
            null_false_positives=0,
            null_outputs=500,
            threshold_pre_registered=True,
            calibration_disjoint=True,
            audit_disjoint=True,
            raw_counts_retained=True,
            complete_protocol_binding=True,
            evidence_context=context,
            provenance=provenance(),
        )
        record = LlmWatermarkAnalyzer().analyze(release, threat, value)[0]
        self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
        self.assertEqual(record.metric, "watermark_detection_rate")
        self.assertFalse(record.can_block)
        self.assertFalse(record.can_clear)
        self.assertIsNotNone(record.details["simultaneous_detection_lower"])

    def test_impossible_counts_fail_closed(self) -> None:
        _, threat, context = interactive_release_and_threat()
        with self.assertRaises(ValidationError):
            LlmWatermarkInput(
                threat_id=threat.threat_id,
                population_scope_id=threat.population_scope_id,
                study_id="bad",
                preregistration_sha256="b" * 64,
                transcript_manifest_sha256="c" * 64,
                detector_id="detector",
                detector_version="1",
                opaque_key_id="key",
                detected_outputs=2,
                eligible_outputs=1,
                null_false_positives=0,
                null_outputs=1,
                threshold_pre_registered=True,
                calibration_disjoint=True,
                audit_disjoint=True,
                raw_counts_retained=True,
                complete_protocol_binding=True,
                evidence_context=context,
                provenance=provenance(),
            )


if __name__ == "__main__":
    unittest.main()
