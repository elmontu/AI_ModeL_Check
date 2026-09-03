from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from fractions import Fraction

from .integrity import canonical_json_bytes, sha256_bytes
from .models import (
    AttackBatteryStatus,
    CeilingAttackBatteryMode,
    DecisionResolution,
    EvidenceClass,
    EvidenceConsistency,
    EvidenceCoverage,
    EvidenceRecord,
    OverallVerdict,
    PopulationScope,
    RationalProbability,
    ReleaseContract,
    ThreatContract,
    ThreatDecision,
    Verdict,
)


def _lower_fraction(record: EvidenceRecord) -> Fraction:
    if record.exact_lower is not None:
        return record.exact_lower.as_fraction()
    assert record.lower is not None
    return Fraction(Decimal(str(record.lower)))


def _upper_fraction(record: EvidenceRecord) -> Fraction:
    if record.exact_upper is not None:
        return record.exact_upper.as_fraction()
    assert record.upper is not None
    return Fraction(Decimal(str(record.upper)))


def _rational_probability(value: Fraction) -> RationalProbability:
    return RationalProbability(numerator=value.numerator, denominator=value.denominator)


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
    ceiling_attack_battery: AttackBatteryStatus,
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
    floor_records = [
        record for record in applicable if record.can_block and record.lower is not None
    ]
    clearing_records = [
        record
        for record in applicable
        if record.can_clear
        and record.coverage is EvidenceCoverage.COMPLETE_INTERFACE
        and record.upper is not None
    ]
    floors = [record.lower for record in floor_records]
    ceilings = [record.upper for record in clearing_records]
    upper = min(ceilings, default=1.0)
    exact_floor_records = [
        record
        for record in floor_records
        if record.evidence_class is EvidenceClass.EXACT
    ]
    statistical_floor_records = [
        record
        for record in floor_records
        if record.evidence_class is not EvidenceClass.EXACT
    ]
    statistical_family_records = [
        record
        for record in applicable
        if record.statistical_family_id is not None
    ]
    exact_floor_fraction = max(
        (_lower_fraction(record) for record in exact_floor_records),
        default=Fraction(0),
    )
    # Every statistical floor carries a policy-bound family digest and at
    # least 95% familywise confidence. The engine verifies that generic input
    # families contain exactly their declared number of comparisons; the
    # attack-battery contract separately dispositions every frozen run. Within
    # a family the strongest already-adjusted member floor can therefore be
    # used. Across families the minimum of those maxima is conservative; if a
    # larger family result would change the release boundary, the gate holds
    # for multiplicity resolution rather than becoming safer when weak
    # evidence is added.
    statistical_groups: dict[str, list[EvidenceRecord]] = defaultdict(list)
    statistical_family_dispositions: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in statistical_family_records:
        assert record.statistical_family_id is not None
        statistical_family_dispositions[record.statistical_family_id].append(record)
    for record in statistical_floor_records:
        # EvidenceRecord validation requires a content-addressed family ID and
        # >=95% familywise confidence for every statistical blocking floor.
        assert record.statistical_family_id is not None
        group_id = record.statistical_family_id
        statistical_groups[group_id].append(record)
    statistical_group_bounds: list[
        tuple[Fraction, float, tuple[EvidenceRecord, ...]]
    ] = []
    for group_id in sorted(statistical_family_dispositions):
        group_records = statistical_groups[group_id]
        group_bound = max(
            (_lower_fraction(record) for record in group_records),
            default=Fraction(0),
        )
        group_support = tuple(
            record
            for record in group_records
            if _lower_fraction(record) == group_bound
        ) or tuple(statistical_family_dispositions[group_id])
        group_display = max(
            (
                record.lower
                for record in group_records
                if record.lower is not None
                and _lower_fraction(record) == group_bound
            ),
            default=0.0,
        )
        statistical_group_bounds.append((group_bound, group_display, group_support))
    statistical_floor_fraction = min(
        (bound for bound, _, _ in statistical_group_bounds),
        default=Fraction(0),
    )
    statistical_candidate_fraction = max(
        (bound for bound, _, _ in statistical_group_bounds),
        default=Fraction(0),
    )
    statistical_aggregate_support_records = tuple(
        record
        for _, _, group_support in statistical_group_bounds
        for record in group_support
    )
    lower_fraction = max(exact_floor_fraction, statistical_floor_fraction)
    exact_floor_display = max(
        (
            record.lower
            for record in exact_floor_records
            if _lower_fraction(record) == exact_floor_fraction
            and record.lower is not None
        ),
        default=0.0,
    )
    statistical_floor_display = min(
        (display for _, display, _ in statistical_group_bounds),
        default=0.0,
    )
    if exact_floor_fraction > statistical_floor_fraction:
        lower = exact_floor_display
        lower_support_records = tuple(
            record
            for record in exact_floor_records
            if _lower_fraction(record) == exact_floor_fraction
        )
    elif statistical_floor_fraction > exact_floor_fraction:
        lower = statistical_floor_display
        lower_support_records = statistical_aggregate_support_records
    else:
        lower = min(exact_floor_display, statistical_floor_display)
        lower_support_records = tuple(
            (*exact_floor_records, *statistical_aggregate_support_records)
        )
    upper_fraction = min(
        (_upper_fraction(record) for record in clearing_records),
        default=Fraction(1),
    )
    tolerance_fraction = Fraction(str(threat.tolerance))
    reasons: list[str] = []
    contradictory = lower_fraction > upper_fraction
    unresolved_statistical_multiplicity = (
        len(statistical_group_bounds) > 1
        and statistical_candidate_fraction > lower_fraction
        and (
            statistical_candidate_fraction > tolerance_fraction
            or statistical_candidate_fraction > upper_fraction
        )
    )

    # A contradictory ceiling must not weaken an independently blocking floor.
    clearance_evidence_class = None
    exact_clear_records = [
        record
        for record in clearing_records
        if record.evidence_class is EvidenceClass.EXACT
        and _upper_fraction(record) <= tolerance_fraction
    ]
    ceiling_clear_records = [
        record
        for record in clearing_records
        if record.evidence_class is EvidenceClass.CEILING
        and _upper_fraction(record) <= tolerance_fraction
    ]

    if lower_fraction > tolerance_fraction:
        verdict = Verdict.BLOCK
        reasons.append(f"validated floor {lower:.6g} exceeds tolerance {threat.tolerance:.6g}")
    elif contradictory:
        verdict = Verdict.INCONCLUSIVE
    elif unresolved_statistical_multiplicity:
        verdict = Verdict.INCONCLUSIVE
        reasons.append(
            "independent statistical floor families disagree at the release boundary; "
            "a shared preregistered error ledger is required"
        )
    elif exact_clear_records:
        verdict = Verdict.CLEAR
        clearance_evidence_class = EvidenceClass.EXACT
        exact_upper = min(record.upper for record in exact_clear_records if record.upper is not None)
        reasons.append(
            f"validated exact value {exact_upper:.6g} is within tolerance "
            f"{threat.tolerance:.6g}"
        )
    elif ceiling_clear_records and (
        ceiling_attack_battery.mode is CeilingAttackBatteryMode.WAIVED
        or (
            ceiling_attack_battery.mode is CeilingAttackBatteryMode.REQUIRED
            and ceiling_attack_battery.satisfied
        )
    ):
        verdict = Verdict.CLEAR
        clearance_evidence_class = EvidenceClass.CEILING
        reasons.append(f"validated ceiling {upper:.6g} is within tolerance {threat.tolerance:.6g}")
        if ceiling_attack_battery.mode is CeilingAttackBatteryMode.WAIVED:
            reasons.append(
                "policy explicitly waived the attack battery: "
                f"{ceiling_attack_battery.waiver_reason}"
            )
        else:
            reasons.append("policy-mandated attack battery and positive controls passed")
    elif ceiling_clear_records:
        verdict = Verdict.INCONCLUSIVE
        if ceiling_attack_battery.mode is CeilingAttackBatteryMode.PROHIBITED:
            reasons.append("policy prohibits clearance from ceiling evidence for this threat")
        else:
            reasons.append(
                "otherwise-clearing ceiling is ineligible because the mandatory attack "
                "battery or its positive controls did not pass"
            )
            reasons.extend(ceiling_attack_battery.failure_reasons)
    else:
        verdict = Verdict.INCONCLUSIVE
        if not ceilings:
            reasons.append("no recipient-realizable exact value or validated non-trivial ceiling can clear this threat")
        else:
            reasons.append(f"best ceiling {upper:.6g} exceeds tolerance {threat.tolerance:.6g}")
        if floors:
            reasons.append(f"decision-valid aggregate floor is {lower:.6g}")

    dispositions: dict[str, dict[str, object]] = {}
    if verdict is Verdict.INCONCLUSIVE:
        # Finite-channel evidence carries a machine-readable remediation path.
        for record in applicable:
            resolution = record.details.get("resolution")
            if isinstance(resolution, str):
                dispositions.setdefault(resolution, record.details)

    conflicting_evidence_ids: tuple[str, ...] = ()
    if contradictory:
        reasons.append("validated lower and upper bounds conflict; independent review is required")
        lower_support_ids = {record.evidence_id for record in lower_support_records}
        conflicting_evidence_ids = tuple(
            record.evidence_id
            for record in applicable
            if (
                record.evidence_id in lower_support_ids
            )
            or (
                record.can_clear
                and record.coverage is EvidenceCoverage.COMPLETE_INTERFACE
                and record.upper is not None
                and _upper_fraction(record) == upper_fraction
            )
        )

    evidence_consistency = (
        EvidenceConsistency.CONTRADICTORY
        if contradictory
        else EvidenceConsistency.INSUFFICIENT
        if verdict is Verdict.INCONCLUSIVE
        else EvidenceConsistency.CONSISTENT
    )

    excluded = [record for record in records if record.threat_id == threat.threat_id and record not in applicable]
    if excluded:
        reasons.append(f"{len(excluded)} evidence record(s) did not match decision metric {threat.decision_metric}")

    if verdict is Verdict.BLOCK:
        resolution = DecisionResolution(
            code="floor_above_tolerance",
            release_gate="block",
            actions=("reject the release or remediate it and run a new assessment",),
            evidence_ids=tuple(record.evidence_id for record in lower_support_records),
        )
    elif verdict is Verdict.CLEAR:
        clearance_records = (
            exact_clear_records
            if clearance_evidence_class is EvidenceClass.EXACT
            else ceiling_clear_records
        )
        resolution = DecisionResolution(
            code="risk_bound_within_tolerance",
            release_gate="clear",
            evidence_ids=tuple(
                record.evidence_id
                for record in clearance_records
                if _upper_fraction(record) <= tolerance_fraction
            ),
        )
    elif contradictory:
        resolution = DecisionResolution(
            code="resolve_evidence_conflict",
            release_gate="hold",
            actions=(
                "independently adjudicate the conflicting evidence producers and replay the assessment",
            ),
            evidence_ids=conflicting_evidence_ids,
        )
    elif unresolved_statistical_multiplicity:
        resolution = DecisionResolution(
            code="resolve_statistical_multiplicity",
            release_gate="hold",
            actions=(
                "register all floor-producing tests in one policy-bound error ledger and replay them as a complete family",
            ),
            evidence_ids=tuple(
                record.evidence_id
                for record in statistical_family_records
            ),
            missing_obligations=(
                "one complete preregistered cross-family multiplicity allocation",
            ),
        )
    elif ceiling_clear_records:
        if ceiling_attack_battery.mode is CeilingAttackBatteryMode.PROHIBITED:
            resolution = DecisionResolution(
                code="submit_exact_evidence_or_change_policy",
                release_gate="hold",
                actions=(
                    "submit recipient-realizable exact evidence or obtain an explicit policy change",
                ),
                evidence_ids=tuple(record.evidence_id for record in ceiling_clear_records),
            )
        else:
            resolution = DecisionResolution(
                code="complete_attack_battery",
                release_gate="hold",
                actions=(
                    "complete the policy-mandated red-team battery and passing positive controls",
                ),
                evidence_ids=tuple(record.evidence_id for record in ceiling_clear_records),
                missing_obligations=ceiling_attack_battery.failure_reasons,
            )
    elif dispositions:
        priority = (
            "register_policy_bound_finite_game",
            "redesign_interface",
            "repair_sampling_evidence_and_replay",
            "repair_release_bindings_and_replay",
            "collect_simultaneous_channel_evidence",
            "recollect_more_state_conditioned_samples",
        )
        code = next((item for item in priority if item in dispositions), next(iter(dispositions)))
        details = dispositions[code]
        configured_actions = details.get("resolution_options")
        if isinstance(configured_actions, list) and all(
            isinstance(item, str) for item in configured_actions
        ):
            actions = tuple(configured_actions)
        else:
            actions = {
                "register_policy_bound_finite_game": (
                    "freeze the ordered state semantics and exact rational prior in the signed policy, then recollect and replay",
                ),
                "redesign_interface": (
                    "enforce a finite complete recipient-visible interface, then recollect evidence",
                ),
                "repair_sampling_evidence_and_replay": (
                    "repair the registered confidence evidence and replay every nested source",
                ),
                "repair_release_bindings_and_replay": (
                    "bind the evidence to the exact release, artifact, interface, scope, and game, then replay",
                ),
                "collect_simultaneous_channel_evidence": (
                    "collect preregistered state-conditioned counts and compile a simultaneous confidence family",
                ),
                "recollect_more_state_conditioned_samples": (
                    "collect more preregistered state-conditioned samples and replay the confidence family",
                ),
            }.get(code, ("satisfy the named evidence obligation and replay the assessment",))
        missing = details.get("missing_obligations")
        missing_obligations = (
            tuple(str(item) for item in missing)
            if isinstance(missing, list)
            else ()
        )
        minimum = details.get("indicative_minimum_trials_per_state")
        additional = details.get("indicative_additional_trials_per_state")
        resolution = DecisionResolution(
            code=code,
            release_gate="hold",
            actions=actions,
            evidence_ids=tuple(
                record.evidence_id
                for record in applicable
                if record.details.get("resolution") == code
            ),
            missing_obligations=missing_obligations,
            indicative_minimum_trials_per_state=(
                minimum if isinstance(minimum, int) and minimum > 0 else None
            ),
            indicative_additional_trials_per_state=(
                additional if isinstance(additional, int) and additional >= 0 else None
            ),
        )
    else:
        resolution = DecisionResolution(
            code="supply_admissible_complete_interface_evidence",
            release_gate="hold",
            actions=(
                "supply a recipient-realizable exact value or validated complete-interface ceiling",
            ),
        )

    if verdict is Verdict.INCONCLUSIVE:
        reasons.append(f"required next action: {resolution.code}")
        if resolution.indicative_minimum_trials_per_state is not None:
            reasons.append(
                "planning estimate (not decision evidence): collect approximately "
                f"{resolution.indicative_additional_trials_per_state or 0} additional "
                "trials per state, targeting at least "
                f"{resolution.indicative_minimum_trials_per_state} total per state, then "
                "replay the registered family"
            )
        if resolution.missing_obligations:
            reasons.append(
                "finite-channel obligations still open: "
                + "; ".join(resolution.missing_obligations)
            )

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
        lower_bound_fraction=_rational_probability(lower_fraction),
        upper_bound_fraction=_rational_probability(upper_fraction),
        verdict=verdict,
        evidence_ids=tuple(record.evidence_id for record in applicable),
        excluded_evidence_ids=tuple(record.evidence_id for record in excluded),
        evidence_consistency=evidence_consistency,
        conflicting_evidence_ids=conflicting_evidence_ids,
        clearance_evidence_class=clearance_evidence_class,
        ceiling_attack_battery=ceiling_attack_battery,
        resolution=resolution,
        reasons=tuple(reasons),
    )


def decide_overall(decisions: tuple[ThreatDecision, ...]) -> OverallVerdict:
    mandatory = [decision for decision in decisions if decision.mandatory]
    if any(decision.verdict is Verdict.BLOCK for decision in mandatory):
        return OverallVerdict.BLOCK
    if mandatory and all(decision.verdict is Verdict.CLEAR for decision in mandatory):
        return OverallVerdict.CLEAR
    return OverallVerdict.INCONCLUSIVE
