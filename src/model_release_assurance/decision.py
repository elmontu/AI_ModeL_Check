from __future__ import annotations

from collections import defaultdict

from .integrity import canonical_json_bytes, sha256_bytes
from .models import (
    EvidenceCoverage,
    EvidenceRecord,
    OverallVerdict,
    PopulationScope,
    ReleaseContract,
    ThreatContract,
    ThreatDecision,
    Verdict,
)


def population_scope_sha256(scope: PopulationScope) -> str:
    return sha256_bytes(canonical_json_bytes(scope))


def decision_game_sha256(
    threat: ThreatContract,
    population_scope: PopulationScope,
) -> str:
    """Bind a decision problem while allowing its observation experiment to vary."""
    return sha256_bytes(canonical_json_bytes({
        "domain": "MRA-DECISION-GAME-2",
        "threat": threat.model_dump(mode="json", exclude_none=True),
        "population_scope": population_scope.model_dump(mode="json", exclude_none=True),
    }))


def decide_threat(
    threat: ThreatContract,
    population_scope: PopulationScope,
    release: ReleaseContract,
    records: tuple[EvidenceRecord, ...],
    policy_sha256: str,
) -> ThreatDecision:
    scope_hash = population_scope_sha256(population_scope)
    game_hash = decision_game_sha256(threat, population_scope)
    interface_hash = sha256_bytes(canonical_json_bytes(release.interface))
    release_contract_hash = sha256_bytes(canonical_json_bytes(release))
    applicable = [
        record
        for record in records
        if record.threat_id == threat.threat_id
        and record.release_id == release.release_id
        and record.release_contract_sha256 == release_contract_hash
        and record.policy_sha256 == policy_sha256
        and record.metric == threat.decision_metric
        and record.population_scope_id == population_scope.scope_id
        and record.population_scope_sha256 == scope_hash
        and record.decision_game_sha256 == game_hash
        and record.interface_sha256 == interface_hash
        and record.artifact_sha256 == release.artifact_sha256
    ]
    floors = [record.lower for record in applicable if record.can_block and record.lower is not None]
    ceilings = [
        record.upper
        for record in applicable
        if record.can_clear
        and record.coverage is EvidenceCoverage.COMPLETE_INTERFACE
        and record.upper is not None
    ]
    lower = max(floors, default=0.0)
    upper = min(ceilings, default=1.0)
    reasons: list[str] = []

    if lower > upper + 1e-12:
        verdict = Verdict.INCONCLUSIVE
        reasons.append("validated lower and upper bounds conflict; independent review is required")
    elif lower > threat.tolerance:
        verdict = Verdict.BLOCK
        reasons.append(f"validated floor {lower:.6g} exceeds tolerance {threat.tolerance:.6g}")
    elif ceilings and upper <= threat.tolerance:
        verdict = Verdict.CLEAR
        reasons.append(f"validated ceiling {upper:.6g} is within tolerance {threat.tolerance:.6g}")
    else:
        verdict = Verdict.INCONCLUSIVE
        if not ceilings:
            reasons.append("no recipient-realizable exact value or validated non-trivial ceiling can clear this threat")
        else:
            reasons.append(f"best ceiling {upper:.6g} exceeds tolerance {threat.tolerance:.6g}")
        if floors:
            reasons.append(f"best validated attack floor is {lower:.6g}")

    excluded = [record for record in records if record.threat_id == threat.threat_id and record not in applicable]
    if excluded:
        reasons.append(f"{len(excluded)} evidence record(s) did not match decision metric {threat.decision_metric}")

    return ThreatDecision(
        threat_id=threat.threat_id,
        population_scope_id=population_scope.scope_id,
        population_scope_sha256=scope_hash,
        decision_game_sha256=game_hash,
        assessed_interface_sha256=interface_hash,
        assessed_artifact_sha256=release.artifact_sha256,
        assessed_release_contract_sha256=release_contract_hash,
        assessed_policy_sha256=policy_sha256,
        decision_metric=threat.decision_metric,
        kind=threat.kind,
        mandatory=threat.mandatory,
        tolerance=threat.tolerance,
        tolerance_basis=threat.tolerance_basis,
        lower_bound=lower,
        upper_bound=upper,
        verdict=verdict,
        evidence_ids=tuple(record.evidence_id for record in applicable),
        reasons=tuple(reasons),
    )


def decide_overall(decisions: tuple[ThreatDecision, ...]) -> OverallVerdict:
    mandatory = [decision for decision in decisions if decision.mandatory]
    if any(decision.verdict is Verdict.BLOCK for decision in mandatory):
        return OverallVerdict.BLOCK
    if mandatory and all(decision.verdict is Verdict.CLEAR for decision in mandatory):
        return OverallVerdict.CLEAR
    return OverallVerdict.INCONCLUSIVE
