from __future__ import annotations

from typing import Protocol

from ..models import AnalyzerInput, EvidenceRecord, ReleaseContract, ThreatContract


class Analyzer(Protocol):
    name: str

    def supports(self, value: AnalyzerInput) -> bool: ...

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]: ...
