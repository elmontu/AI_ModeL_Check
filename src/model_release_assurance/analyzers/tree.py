from __future__ import annotations

from collections import Counter, defaultdict

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    ReleaseContract,
    ThreatContract,
    ThreatKind,
    TreeLinkageInput,
)
from ..integrity import canonical_json_bytes, sha256_bytes
from ..model_coverage import resolve_model_family
from .base import evidence_context_fields


class TreeLinkageAnalyzer:
    name = "tree_linkage"

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, TreeLinkageInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, TreeLinkageInput):
            raise AnalyzerError("tree analyzer received an incompatible input")
        if threat.kind is not ThreatKind.LINKAGE:
            raise ValueError("tree_linkage evidence can only target a linkage threat")
        if resolve_model_family(release.model_family).family_id != "tree_ensemble":
            raise AnalyzerError("tree_linkage evidence requires a governed tree-ensemble release family")

        n = len(value.candidate_ids)
        prior = value.prior or tuple(1.0 / n for _ in range(n))
        cells: dict[str, list[int]] = defaultdict(list)
        for index, observation in enumerate(value.observations):
            cells[observation].append(index)
        sizes = Counter(value.observations)
        posterior = sum(max(prior[i] for i in indices) for indices in cells.values())
        baseline = max(prior)
        incremental = max(0.0, posterior - baseline)
        min_cell = min(sizes.values())
        worst_uniform = 1.0 / min_cell if value.prior is None else max(
            max(prior[i] for i in indices) / mass
            for indices in cells.values()
            if (mass := sum(prior[i] for i in indices)) > 0.0
        )
        singleton_fraction = sum(1 for obs in value.observations if sizes[obs] == 1) / n
        realizable = value.recipient_has_candidate_roster and value.recipient_has_target_signal
        if threat.realizability is Realizability.RECIPIENT and not realizable:
            raise ValueError("contract claims recipient realizability but analyzer inputs do not establish it")
        classification = Realizability.RECIPIENT if realizable else Realizability.AUDITOR_ONLY
        interface_matches = value.observed_interface_sha256 == sha256_bytes(
            canonical_json_bytes(release.interface)
        )
        complete = realizable and value.complete_interface_coverage and interface_matches
        evidence_class = EvidenceClass.EXACT if realizable else EvidenceClass.SCREEN

        common = dict(
            **evidence_context_fields(value.evidence_context),
            threat_id=threat.threat_id,
            analyzer=self.name,
            realizability=classification,
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                "fixed candidate set",
                "deterministic declared observation",
                "declared prior",
            ),
            coverage=(
                EvidenceCoverage.COMPLETE_INTERFACE
                if complete
                else EvidenceCoverage.NAMED_PROJECTION
            ),
            limitations=(
                *(() if complete else ("declared observations do not establish complete release-interface coverage",)),
                "does not establish membership privacy",
            ),
            details={
                "candidate_count": n,
                "population_scope_id": value.population_scope_id,
                "occupied_cells": len(cells),
                "minimum_cell_size": min_cell,
                "singleton_fraction": singleton_fraction,
                "source_sha256": value.provenance.source_sha256,
                "tool": value.provenance.tool,
                "tool_version": value.provenance.tool_version,
            },
        )
        return (
            EvidenceRecord(
                evidence_id=f"{threat.threat_id}:tree:absolute",
                evidence_class=evidence_class,
                metric="bayes_linkage_success",
                value=posterior,
                lower=posterior if realizable else None,
                upper=posterior if realizable else None,
                baseline=baseline,
                can_clear=complete,
                can_block=realizable,
                **common,
            ),
            EvidenceRecord(
                evidence_id=f"{threat.threat_id}:tree:incremental",
                evidence_class=evidence_class,
                metric="incremental_bayes_linkage_success",
                value=incremental,
                lower=incremental if realizable else None,
                upper=incremental if realizable else None,
                baseline=baseline,
                can_clear=complete,
                can_block=realizable,
                **common,
            ),
            EvidenceRecord(
                evidence_id=f"{threat.threat_id}:tree:worst-observation",
                evidence_class=evidence_class,
                metric="worst_observation_success",
                value=worst_uniform,
                lower=worst_uniform if realizable else None,
                upper=worst_uniform if realizable else None,
                baseline=baseline,
                can_clear=complete,
                can_block=realizable,
                **common,
            ),
        )
