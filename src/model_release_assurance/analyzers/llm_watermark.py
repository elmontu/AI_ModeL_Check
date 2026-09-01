from __future__ import annotations

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    LlmWatermarkInput,
    Realizability,
    ReleaseContract,
    ThreatContract,
)
from .attack import clopper_pearson_lower, clopper_pearson_upper
from .base import evidence_context_fields, evidence_producer_fields


class LlmWatermarkAnalyzer:
    name = "llm_watermark"
    can_clear = False
    can_block = False

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, LlmWatermarkInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, LlmWatermarkInput):
            raise AnalyzerError("LLM watermark analyzer received an incompatible input")
        if release.interface.protocol_type != "interactive_llm":
            raise AnalyzerError("LLM watermark evidence requires an interactive_llm release")

        per_comparison_confidence = 1.0 - (
            (1.0 - value.confidence) / (2 * value.comparison_family_size)
        )
        valid = (
            value.threshold_pre_registered
            and value.calibration_disjoint
            and value.audit_disjoint
            and value.raw_counts_retained
            and value.complete_protocol_binding
            and not value.key_compromised
            and not value.key_revoked
        )
        estimate = value.detected_outputs / value.eligible_outputs
        detection_lower = clopper_pearson_lower(
            value.detected_outputs, value.eligible_outputs, per_comparison_confidence
        ) if valid else None
        null_fpr_upper = clopper_pearson_upper(
            value.null_false_positives, value.null_outputs, per_comparison_confidence
        ) if valid else None
        return (EvidenceRecord(
            **evidence_context_fields(value.evidence_context),
            **evidence_producer_fields(value.provenance),
            evidence_id=f"{threat.threat_id}:llm-watermark:{value.study_id}",
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.SCREEN,
            coverage=EvidenceCoverage.SCREEN_ONLY,
            metric="watermark_detection_rate",
            value=estimate,
            lower=None,
            upper=None,
            baseline=None,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=False,
            assumptions=(
                f"simultaneous confidence={value.confidence}",
                f"comparison family size={value.comparison_family_size}",
            ),
            limitations=(
                "watermark detection is provenance triage only and cannot clear or block a privacy threat",
                "a detector miss cannot establish absence, authorship safety, or resistance to transformation",
            ) if valid else (
                "watermark screen is invalid because preregistration, separation, raw counts, protocol binding, or key status failed",
            ),
            details={
                "study_id": value.study_id,
                "preregistration_sha256": value.preregistration_sha256,
                "transcript_manifest_sha256": value.transcript_manifest_sha256,
                "detector_id": value.detector_id,
                "detector_version": value.detector_version,
                "opaque_key_id": value.opaque_key_id,
                "detected_outputs": value.detected_outputs,
                "eligible_outputs": value.eligible_outputs,
                "null_false_positives": value.null_false_positives,
                "null_outputs": value.null_outputs,
                "simultaneous_detection_lower": detection_lower,
                "simultaneous_null_fpr_upper": null_fpr_upper,
                "valid": valid,
                "source_sha256": value.provenance.source_sha256,
            },
        ),)
