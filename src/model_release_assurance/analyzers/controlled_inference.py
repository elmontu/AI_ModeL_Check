from __future__ import annotations

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    ControlledInferenceInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    ReleaseContract,
    ThreatContract,
    ThreatKind,
)
from .attack import clopper_pearson_lower, clopper_pearson_upper


class ControlledInferenceAnalyzer:
    name = "controlled_inference"

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, ControlledInferenceInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, ControlledInferenceInput):
            raise AnalyzerError("controlled inference analyzer received an incompatible input")
        if value.metric != threat.decision_metric:
            raise ValueError("controlled inference metric does not match the threat contract")
        if threat.kind not in (ThreatKind.ATTRIBUTE, ThreatKind.RECONSTRUCTION):
            raise ValueError("controlled inference evidence requires an attribute or reconstruction threat")

        reconstruction_valid = (
            threat.kind is not ThreatKind.RECONSTRUCTION
            or (value.ground_truth_verified and value.training_membership_verified)
        )
        valid = (
            value.attack_training_disjoint
            and value.audit_disjoint
            and value.raw_paired_counts_retained
            and value.comparator_same_side_information
            and value.secret_and_metric_pre_registered
            and value.ground_truth_verified
            and reconstruction_valid
        )
        incremental = value.metric.startswith("incremental_")
        if incremental:
            estimate = max(
                0.0,
                (value.combined_successes - value.baseline_successes) / value.trials,
            )
            # Bonferroni across the comparison family and the two marginal
            # binomial bounds. The difference is conservative despite the
            # paired multinomial dependence by the union bound.
            per_side_confidence = 1.0 - (
                (1.0 - value.confidence_family) / (2.0 * value.comparison_family_size)
            )
            combined_only_lower = clopper_pearson_lower(
                value.combined_only_successes, value.trials, per_side_confidence
            )
            baseline_only_upper = clopper_pearson_upper(
                value.baseline_only_successes, value.trials, per_side_confidence
            )
            lower = max(0.0, combined_only_lower - baseline_only_upper) if valid else None
        else:
            estimate = value.combined_successes / value.trials
            per_side_confidence = 1.0 - (
                (1.0 - value.confidence_family) / value.comparison_family_size
            )
            combined_only_lower = None
            baseline_only_upper = None
            lower = (
                clopper_pearson_lower(
                    value.combined_successes, value.trials, per_side_confidence
                )
                if valid
                else None
            )

        limitations = () if valid else (
            "controlled floor invalid because disjoint attack training/audit, paired raw counts, same-side-information comparator, pre-registration, ground truth, or reconstruction membership verification is missing",
        )
        return (EvidenceRecord(
            evidence_id=f"{threat.threat_id}:controlled:{value.attack_name}",
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.FLOOR if valid else EvidenceClass.SCREEN,
            coverage=EvidenceCoverage.NAMED_PROJECTION,
            metric=value.metric,
            value=estimate,
            lower=lower,
            upper=None,
            baseline=value.baseline_successes / value.trials,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=valid,
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                f"familywise confidence={value.confidence_family}",
                f"comparison family size={value.comparison_family_size}",
                f"success definition={value.success_definition}",
            ),
            limitations=limitations,
            details={
                "attack_name": value.attack_name,
                "trials": value.trials,
                "combined_successes": value.combined_successes,
                "baseline_successes": value.baseline_successes,
                "combined_only_successes": value.combined_only_successes,
                "baseline_only_successes": value.baseline_only_successes,
                "per_bound_confidence": per_side_confidence,
                "combined_only_probability_lower": combined_only_lower,
                "baseline_only_probability_upper": baseline_only_upper,
                "ground_truth_verified": value.ground_truth_verified,
                "training_membership_verified": value.training_membership_verified,
                "source_sha256": value.provenance.source_sha256,
            },
        ),)
