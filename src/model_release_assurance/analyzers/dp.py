from __future__ import annotations

import math

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    DpInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    ReleaseContract,
    ThreatContract,
    ThreatKind,
)
from .base import evidence_context_fields


class DpAnalyzer:
    name = "dp"

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, DpInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, DpInput):
            raise AnalyzerError("DP analyzer received an incompatible input")
        validated = (
            value.accountant_replayed
            and value.complete_pipeline
            and value.protected_unit == release.protected_unit
        )
        limitations = [] if validated else [
            "accountant was not independently replayed, pipeline scope is incomplete, or protected unit mismatches"
        ]
        records: list[EvidenceRecord] = []
        common = dict(
            **evidence_context_fields(value.evidence_context),
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.CEILING if validated else EvidenceClass.SCREEN,
            coverage=(
                EvidenceCoverage.COMPLETE_INTERFACE
                if validated
                else EvidenceCoverage.SCREEN_ONLY
            ),
            realizability=Realizability.NOT_APPLICABLE,
            can_clear=validated,
            can_block=False,
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                f"adjacency={value.adjacency}",
                f"protected_unit={value.protected_unit}",
                f"accountant={value.accountant}",
                f"epsilon={value.epsilon}",
                f"delta={value.delta}",
            ),
            limitations=tuple(limitations),
        )
        if threat.kind is ThreatKind.MEMBERSHIP:
            if value.fpr is not None:
                if threat.decision_metric == "membership_tpr_at_fpr" and abs(
                    value.fpr - threat.metric_parameters["target_fpr"]
                ) > 1e-15:
                    raise ValueError("DP evidence FPR does not match the threat contract target_fpr")
                first = math.exp(value.epsilon) * value.fpr + value.delta
                second = 1.0 - math.exp(-value.epsilon) * (1.0 - value.fpr - value.delta)
                ceiling = min(1.0, max(0.0, min(first, second)))
                records.append(EvidenceRecord(
                    evidence_id=f"{threat.threat_id}:dp:roc",
                    metric="membership_tpr_at_fpr",
                    upper=ceiling if validated else None,
                    value=ceiling,
                    details={"population_scope_id": value.population_scope_id, "fpr": value.fpr, "bound_1": first, "bound_2": second, "source_sha256": value.provenance.source_sha256},
                    **common,
                ))
            equal_prior = min(1.0, (math.exp(value.epsilon) + value.delta) / (math.exp(value.epsilon) + 1.0))
            records.append(EvidenceRecord(
                evidence_id=f"{threat.threat_id}:dp:equal-prior",
                metric="equal_prior_membership_success",
                upper=equal_prior if validated else None,
                value=equal_prior,
                details={"population_scope_id": value.population_scope_id, "source_sha256": value.provenance.source_sha256},
                **common,
            ))
        elif value.secret_cardinality is not None:
            validated = validated and value.pairwise_secret_relation_validated
            finite_limitations = list(limitations)
            if not value.pairwise_secret_relation_validated:
                finite_limitations.append("pairwise DP relation across all finite-secret alternatives was not validated")
            m = value.secret_cardinality
            ceiling = min(1.0, (math.exp(value.epsilon) + (m - 1) * value.delta) / (math.exp(value.epsilon) + m - 1))
            records.append(EvidenceRecord(
                evidence_id=f"{threat.threat_id}:dp:finite-secret",
                metric="finite_secret_exact_guess_success",
                upper=ceiling if validated else None,
                value=ceiling,
                details={"population_scope_id": value.population_scope_id, "secret_cardinality": m, "source_sha256": value.provenance.source_sha256},
                **{
                    **common,
                    "evidence_class": EvidenceClass.CEILING if validated else EvidenceClass.SCREEN,
                    "can_clear": validated,
                    "limitations": tuple(finite_limitations),
                },
            ))
        else:
            records.append(EvidenceRecord(
                evidence_id=f"{threat.threat_id}:dp:scope",
                metric="dp_scope_validated",
                value=1.0 if validated else 0.0,
                details={"population_scope_id": value.population_scope_id, "source_sha256": value.provenance.source_sha256},
                **{**common, "can_clear": False},
            ))
        return tuple(records)
