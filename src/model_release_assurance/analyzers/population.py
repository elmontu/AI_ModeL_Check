from __future__ import annotations

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    PopulationInput,
    Realizability,
    ReleaseContract,
    ThreatContract,
)
from .base import evidence_context_fields


class PopulationAnalyzer:
    name = "population"

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, PopulationInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, PopulationInput):
            raise AnalyzerError("population analyzer received an incompatible input")
        validated = value.fitted_joint_model and value.heldout_validated and value.multiplicity_adjusted
        passes = value.simultaneous_lower_match_count >= value.required_match_count
        # This is a population uniqueness screen, not a universal probability ceiling.
        return (EvidenceRecord(
            **evidence_context_fields(value.evidence_context),
            evidence_id=f"{threat.threat_id}:population:match-count",
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.SCREEN,
            coverage=EvidenceCoverage.SCREEN_ONLY,
            metric="simultaneous_lower_population_match_count",
            value=min(1.0, value.simultaneous_lower_match_count / value.required_match_count),
            lower=None,
            upper=None,
            baseline=None,
            realizability=Realizability.POPULATION_MODEL,
            can_clear=False,
            can_block=False,
            assumptions=(f"population_scope_id={value.population_scope_id}", f"coverage={value.coverage}"),
            limitations=(
                "match-count evidence is not itself an adversarial success-probability ceiling",
                *(() if validated else ("joint model, held-out validation, or multiplicity adjustment is missing",)),
            ),
            details={
                "simultaneous_lower_match_count": value.simultaneous_lower_match_count,
                "population_scope_id": value.population_scope_id,
                "required_match_count": value.required_match_count,
                "gate_passes": passes,
                "validated": validated,
                "source_sha256": value.provenance.source_sha256,
            },
        ),)
