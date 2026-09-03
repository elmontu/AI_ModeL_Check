from __future__ import annotations

from typing import Protocol

from ..integrity import canonical_json_bytes, sha256_bytes
from ..models import (
    AnalyzerInput,
    AnalyzerProvenance,
    AttackInput,
    ControlledInferenceInput,
    EvidenceContext,
    EvidenceRecord,
    LlmCanaryInput,
    ReleaseContract,
    ThreatContract,
)


def evidence_context_fields(context: EvidenceContext) -> dict[str, object]:
    """Copy source-observed bindings into every analyzer result without restamping them."""
    return context.model_dump(mode="python")


def evidence_producer_fields(provenance: AnalyzerProvenance) -> dict[str, object]:
    """Copy the request-declared producer identity into the analyzer result."""
    return {"producer": provenance.producer}


def statistical_family_sha256(
    *,
    analyzer: str,
    family_definition_sha256: str,
) -> str:
    """Domain-separate a policy-bound family definition from raw file hashes."""

    return sha256_bytes(canonical_json_bytes({
        "domain": "MRA-STATISTICAL-FAMILY-1",
        "analyzer": analyzer,
        "family_definition_sha256": family_definition_sha256,
    }))


_STATISTICAL_DESIGN_FIELDS: dict[str, tuple[str, ...]] = {
    "attack": (
        "analyzer",
        "threat_id",
        "population_scope_id",
        "attack_name",
        "preregistration_sha256",
        "metric",
        "trials",
        "confidence",
        "comparison_family_size",
        "calibration_disjoint",
        "audit_disjoint",
        "raw_counts_retained",
        "threshold_pre_registered",
        "nonmember_trials",
        "target_fpr",
    ),
    "controlled_inference": (
        "analyzer",
        "threat_id",
        "population_scope_id",
        "attack_name",
        "preregistration_sha256",
        "metric",
        "trials",
        "confidence_family",
        "comparison_family_size",
        "attack_training_disjoint",
        "audit_disjoint",
        "raw_paired_counts_retained",
        "comparator_same_side_information",
        "secret_and_metric_pre_registered",
        "ground_truth_verified",
        "training_membership_verified",
        "success_definition",
    ),
    "llm_canary": (
        "analyzer",
        "threat_id",
        "population_scope_id",
        "study_id",
        "preregistration_sha256",
        "sealed_assignment_sha256",
        "metric",
        "member_canaries",
        "nonmember_decoys",
        "confidence",
        "comparison_family_size",
        "target_fpr",
        "assignment_randomized",
        "scoring_frozen_before_unblinding",
        "exact_match_pre_registered",
        "audit_disjoint",
        "raw_counts_retained",
        "complete_protocol_binding",
        "recipient_realizable",
    ),
}


def statistical_floor_design_sha256(
    value: AttackInput | ControlledInferenceInput | LlmCanaryInput | dict[str, object],
) -> str:
    """Hash only preregistered design fields, never observed success counts."""

    payload = (
        value.model_dump(mode="json", exclude_none=False)
        if not isinstance(value, dict)
        else value
    )
    analyzer = payload.get("analyzer")
    if not isinstance(analyzer, str) or analyzer not in _STATISTICAL_DESIGN_FIELDS:
        raise ValueError("unsupported statistical floor design")
    fields = _STATISTICAL_DESIGN_FIELDS[analyzer]
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(
            f"statistical floor design omits required fields: {sorted(missing)}"
        )
    return sha256_bytes(canonical_json_bytes({
        "domain": "MRA-STATISTICAL-FLOOR-DESIGN-1",
        "analyzer": analyzer,
        "design": {field: payload[field] for field in fields},
    }))


class Analyzer(Protocol):
    name: str
    can_clear: bool
    can_block: bool

    def supports(self, value: AnalyzerInput) -> bool: ...

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]: ...
