from __future__ import annotations

from typing import Protocol

from ..models import AnalyzerInput, EvidenceContext, EvidenceRecord, ReleaseContract, ThreatContract


def evidence_context_fields(context: EvidenceContext) -> dict[str, object]:
    """Copy source-observed bindings into every analyzer result without restamping them."""
    return context.model_dump(mode="python")


class Analyzer(Protocol):
    name: str

    def supports(self, value: AnalyzerInput) -> bool: ...

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]: ...
