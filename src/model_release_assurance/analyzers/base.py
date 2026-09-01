from __future__ import annotations

from typing import Protocol

from ..models import (
    AnalyzerInput,
    AnalyzerProvenance,
    EvidenceContext,
    EvidenceRecord,
    ReleaseContract,
    ThreatContract,
)


def evidence_context_fields(context: EvidenceContext) -> dict[str, object]:
    """Copy source-observed bindings into every analyzer result without restamping them."""
    return context.model_dump(mode="python")


def evidence_producer_fields(provenance: AnalyzerProvenance) -> dict[str, object]:
    """Copy the request-declared producer identity into the analyzer result."""
    return {"producer": provenance.producer}


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
