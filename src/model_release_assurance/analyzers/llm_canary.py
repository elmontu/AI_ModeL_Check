from __future__ import annotations

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    LlmCanaryInput,
    Realizability,
    ReleaseContract,
    ThreatContract,
)
from .attack import clopper_pearson_lower, clopper_pearson_upper
from .base import evidence_context_fields, evidence_producer_fields


class LlmCanaryAnalyzer:
    name = "llm_canary"
    can_clear = False
    can_block = True

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, LlmCanaryInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, LlmCanaryInput):
            raise AnalyzerError("LLM canary analyzer received an incompatible input")
        if release.interface.protocol_type != "interactive_llm":
            raise AnalyzerError("LLM canary evidence requires an interactive_llm release")
        if value.metric != threat.decision_metric:
            raise AnalyzerError("LLM canary metric does not match the threat decision metric")
        if value.metric == "membership_tpr_at_fpr":
            expected_target = threat.metric_parameters.get("target_fpr")
            if expected_target is None or abs(value.target_fpr - expected_target) > 1e-15:  # type: ignore[operator]
                raise AnalyzerError("LLM canary target_fpr does not match the threat contract")

        bounds_per_comparison = 2 if value.metric in (
            "membership_tpr_at_fpr", "equal_prior_membership_success"
        ) else 1
        per_comparison_confidence = 1.0 - (
            (1.0 - value.confidence) /
            (value.comparison_family_size * bounds_per_comparison)
        )
        decoy_upper = clopper_pearson_upper(
            value.decoy_successes, value.nonmember_decoys, per_comparison_confidence
        )
        operating_point_attained = (
            value.metric != "membership_tpr_at_fpr" or decoy_upper <= value.target_fpr  # type: ignore[operator]
        )
        valid = (
            value.assignment_randomized
            and value.scoring_frozen_before_unblinding
            and value.exact_match_pre_registered
            and value.audit_disjoint
            and value.raw_counts_retained
            and value.contamination_scan_passed
            and value.complete_protocol_binding
            and value.recipient_realizable
            and operating_point_attained
        )
        member_rate = value.member_successes / value.member_canaries
        member_lower = clopper_pearson_lower(
            value.member_successes, value.member_canaries, per_comparison_confidence
        ) if valid else None
        if value.metric == "equal_prior_membership_success":
            estimate = 0.5 * (member_rate + 1.0 - value.decoy_successes / value.nonmember_decoys)
            lower = 0.5 * (member_lower + 1.0 - decoy_upper) if member_lower is not None else None
        else:
            estimate = member_rate
            lower = member_lower
        return (EvidenceRecord(
            **evidence_context_fields(value.evidence_context),
            **evidence_producer_fields(value.provenance),
            evidence_id=f"{threat.threat_id}:llm-canary:{value.study_id}",
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.FLOOR if valid else EvidenceClass.SCREEN,
            coverage=EvidenceCoverage.NAMED_PROJECTION if valid else EvidenceCoverage.SCREEN_ONLY,
            metric=value.metric,
            value=estimate,
            lower=lower,
            upper=None,
            baseline=value.decoy_successes / value.nonmember_decoys,
            realizability=Realizability.RECIPIENT if value.recipient_realizable else Realizability.AUDITOR_ONLY,
            can_clear=False,
            can_block=valid,
            assumptions=(
                f"randomized canary is the inferential unit at simultaneous confidence={value.confidence}",
                f"comparison family size={value.comparison_family_size}",
            ),
            limitations=() if valid else (
                "canary result is screen-only because randomization, blinded scoring, preregistration, separation, contamination, binding, realizability, or operating-point requirements failed",
            ),
            details={
                "study_id": value.study_id,
                "preregistration_sha256": value.preregistration_sha256,
                "transcript_manifest_sha256": value.transcript_manifest_sha256,
                "sealed_assignment_sha256": value.sealed_assignment_sha256,
                "member_successes": value.member_successes,
                "member_canaries": value.member_canaries,
                "decoy_successes": value.decoy_successes,
                "nonmember_decoys": value.nonmember_decoys,
                "simultaneous_decoy_fpr_upper": decoy_upper,
                "operating_point_attained": operating_point_attained,
                "source_sha256": value.provenance.source_sha256,
            },
        ),)
