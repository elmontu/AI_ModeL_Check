"""Exact strategic stress tests for a model-governance protocol.

This module implements the bounded algebraic claims in Section 5 of the
mathematical appendix.  It deliberately does not estimate human behaviour,
declare a model safe, make a governance decision, authorize a release, or
replace any mandatory MRAP gate.  Every numerical
primitive is an exact rational interval tied to an evidence record.  Synthetic
assumptions can exercise the mathematics but cannot support a deployment claim.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from pydantic import Field, model_validator

from .decision_theory import GarblingVerification
from .incomplete_portfolio import RationalNumber
from .integrity import canonical_json_bytes, sha256_bytes
from .models import StrictModel


class StrategicCertificateStatus(StrEnum):
    """Whether an interval claim is established, refuted, or unresolved."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


class EvidenceKind(StrEnum):
    SYNTHETIC_ASSUMPTION = "synthetic_assumption"
    PROSPECTIVE_MEASUREMENT = "prospective_measurement"
    HISTORICAL_OBSERVATION = "historical_observation"
    CONTRACTUAL = "contractual"
    LEGAL_ANALYSIS = "legal_analysis"
    ACCOUNTING = "accounting"
    CAUSAL_STUDY = "causal_study"


class SignedRational(StrictModel):
    """Canonical exact rational number, including negative values."""

    numerator: int
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def canonical_fraction(self) -> SignedRational:
        if math.gcd(abs(self.numerator), self.denominator) != 1:
            raise ValueError("signed rational numbers must be stored in lowest terms")
        if self.numerator == 0 and self.denominator != 1:
            raise ValueError("zero must be encoded with denominator one")
        return self


class ParameterEvidence(StrictModel):
    """Provenance required before a parameter interval may enter a certificate."""

    evidence_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: EvidenceKind
    source: str = Field(min_length=3, max_length=2048)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    population: str = Field(min_length=3, max_length=2048)
    collected_at: datetime
    method: str = Field(min_length=3, max_length=4096)
    uncertainty_method: str = Field(min_length=3, max_length=4096)
    unit: str = Field(min_length=1, max_length=128)
    supports: tuple[str, ...] = Field(min_length=1)
    positive_control_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    deployment_eligible: bool = False

    @model_validator(mode="after")
    def evidence_record_is_coherent(self) -> ParameterEvidence:
        if self.collected_at.utcoffset() is None:
            raise ValueError("parameter evidence collected_at must include a timezone offset")
        if len(set(self.supports)) != len(self.supports):
            raise ValueError("parameter evidence supports entries must be unique")
        if self.kind is EvidenceKind.SYNTHETIC_ASSUMPTION and self.deployment_eligible:
            raise ValueError("synthetic assumptions cannot be deployment eligible")
        if self.deployment_eligible and self.source_sha256 is None:
            raise ValueError("deployment-eligible parameter evidence requires a source digest")
        return self


class RationalQuantity(StrictModel):
    value: RationalNumber
    unit: str = Field(min_length=1, max_length=128)


class RationalInterval(StrictModel):
    lower: RationalNumber
    upper: RationalNumber
    unit: str = Field(min_length=1, max_length=128)
    provenance_id: str = Field(min_length=3, max_length=128)
    claim_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")

    @model_validator(mode="after")
    def lower_does_not_exceed_upper(self) -> RationalInterval:
        if _fraction(self.lower) > _fraction(self.upper):
            raise ValueError("rational interval lower bound must not exceed upper bound")
        return self


class ProbabilityInterval(StrictModel):
    lower: RationalNumber
    upper: RationalNumber
    provenance_id: str = Field(min_length=3, max_length=128)
    claim_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")

    @model_validator(mode="after")
    def probability_bounds_are_valid(self) -> ProbabilityInterval:
        if _fraction(self.lower) > _fraction(self.upper):
            raise ValueError("probability lower bound must not exceed upper bound")
        if _fraction(self.upper) > 1:
            raise ValueError("probability interval must lie in [0,1]")
        return self


class SubmitterType(StrictModel):
    type_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    description: str = Field(min_length=3, max_length=2048)
    net_violation_gain: RationalInterval


class AuditPolicy(StrictModel):
    policy_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    detection_probability: ProbabilityInterval
    consequence: RationalInterval
    strict_margin: RationalQuantity
    commitment_observable: bool
    consequence_enforceable: bool

    @model_validator(mode="after")
    def policy_units_are_coherent(self) -> AuditPolicy:
        if self.consequence.unit != self.strict_margin.unit:
            raise ValueError("audit consequence and strict margin must use the same unit")
        if _fraction(self.strict_margin.value) <= 0:
            raise ValueError("audit strict margin must be positive")
        if not self.consequence_enforceable and _fraction(self.consequence.upper) != 0:
            raise ValueError("unenforceable audit consequences must receive zero deterrence credit")
        return self


class AssessorContract(StrictModel):
    contract_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    low_effort_validation_probability: ProbabilityInterval
    high_effort_validation_probability: ProbabilityInterval
    validation_reward: RationalInterval
    low_effort_cost: RationalInterval
    high_effort_cost: RationalInterval
    strict_margin: RationalQuantity
    scoring_event_observable: bool

    @model_validator(mode="after")
    def contract_units_are_coherent(self) -> AssessorContract:
        units = {
            self.validation_reward.unit,
            self.low_effort_cost.unit,
            self.high_effort_cost.unit,
            self.strict_margin.unit,
        }
        if len(units) != 1:
            raise ValueError("assessor reward, costs, and strict margin must use one unit")
        if _fraction(self.strict_margin.value) <= 0:
            raise ValueError("assessor strict margin must be positive")
        return self


class AttackOption(StrictModel):
    option_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    recipient_type: str = Field(min_length=3, max_length=256)
    jurisdiction: str = Field(min_length=2, max_length=256)
    threat_mapping: str = Field(min_length=3, max_length=2048)
    information_experiment_id: str = Field(min_length=3, max_length=128)
    decision_problem_id: str = Field(min_length=3, max_length=128)
    information_value: ProbabilityInterval
    value_scale: RationalInterval
    attack_cost: RationalInterval
    detection_probability: ProbabilityInterval
    consequence: RationalInterval
    strict_abstention_margin: RationalQuantity
    consequence_enforceable: bool
    risk_neutral_expected_utility: bool = True

    @model_validator(mode="after")
    def attack_units_and_enforcement_are_coherent(self) -> AttackOption:
        units = {
            self.value_scale.unit,
            self.attack_cost.unit,
            self.consequence.unit,
            self.strict_abstention_margin.unit,
        }
        if len(units) != 1:
            raise ValueError("attacker value, cost, consequence, and margin must use one unit")
        if _fraction(self.strict_abstention_margin.value) <= 0:
            raise ValueError("attacker strict abstention margin must be positive")
        if not self.consequence_enforceable and _fraction(self.consequence.upper) != 0:
            raise ValueError("unenforceable attacker consequences must receive zero deterrence credit")
        return self


class GovernanceContext(StrictModel):
    """Institutional context that the supplemental stress test must not replace."""

    accountable_model_owner: str = Field(min_length=3, max_length=256)
    decision_authority: str = Field(min_length=3, max_length=256)
    independent_review_body: str = Field(min_length=3, max_length=256)
    affected_party_groups: tuple[str, ...] = Field(min_length=1)
    governance_objective: str = Field(min_length=3, max_length=4096)
    conflict_of_interest_controls: tuple[str, ...] = Field(min_length=1)
    contestation_process: str = Field(min_length=3, max_length=4096)
    incident_and_retirement_authority: str = Field(min_length=3, max_length=256)

    @model_validator(mode="after")
    def governance_roles_are_coherent(self) -> GovernanceContext:
        if self.independent_review_body in {
            self.accountable_model_owner,
            self.decision_authority,
        }:
            raise ValueError(
                "independent review body must be separate from owner and decision authority"
            )
        if len(set(self.affected_party_groups)) != len(self.affected_party_groups):
            raise ValueError("affected-party groups must be unique")
        if len(set(self.conflict_of_interest_controls)) != len(
            self.conflict_of_interest_controls
        ):
            raise ValueError("conflict-of-interest controls must be unique")
        return self


class StrategicAssuranceProblem(StrictModel):
    """Supplemental one-shot stress test; never a governance or release decision."""

    schema_version: Literal["1.0"] = "1.0"
    assessment_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    assessment_time: datetime
    governance_role: Literal["supplemental_strategic_stress_test"] = (
        "supplemental_strategic_stress_test"
    )
    governance_context: GovernanceContext
    players: tuple[str, ...] = Field(min_length=2)
    timing: tuple[str, ...] = Field(min_length=3)
    information_structure: tuple[str, ...] = Field(min_length=1)
    collusion_scope: str = Field(min_length=3, max_length=4096)
    response_model: Literal["worst_case_best_response"] = "worst_case_best_response"
    follower_tie_rule: Literal["pessimistic"] = "pessimistic"
    material_types_complete: bool
    omitted_material_types: tuple[str, ...] = ()
    submitter_types: tuple[SubmitterType, ...] = Field(min_length=1)
    audit_policy: AuditPolicy
    assessor_contract: AssessorContract | None = None
    attack_options: tuple[AttackOption, ...] = Field(min_length=1)
    evidence: tuple[ParameterEvidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def registered_game_is_coherent(self) -> StrategicAssuranceProblem:
        if self.assessment_time.utcoffset() is None:
            raise ValueError("strategic assessment_time must include a timezone offset")
        if len(set(self.players)) != len(self.players):
            raise ValueError("strategic players must be unique")
        if len(set(value.type_id for value in self.submitter_types)) != len(self.submitter_types):
            raise ValueError("submitter type identifiers must be unique")
        if len(set(value.option_id for value in self.attack_options)) != len(self.attack_options):
            raise ValueError("attack option identifiers must be unique")
        if self.material_types_complete and self.omitted_material_types:
            raise ValueError("a complete type registration cannot list omitted material types")
        if not self.material_types_complete and not self.omitted_material_types:
            raise ValueError("an incomplete type registration must identify omitted material types")
        if len(set(value.evidence_id for value in self.evidence)) != len(self.evidence):
            raise ValueError("parameter evidence identifiers must be unique")
        future_evidence = tuple(
            value.evidence_id
            for value in self.evidence
            if value.collected_at > self.assessment_time
        )
        if future_evidence:
            raise ValueError(
                "parameter evidence cannot postdate the assessment: "
                + ", ".join(future_evidence)
            )
        for submitter in self.submitter_types:
            if submitter.net_violation_gain.unit != self.audit_policy.consequence.unit:
                raise ValueError("submitter gains and audit consequences must use the same unit")
        self._validate_parameter_provenance()
        return self

    def _validate_parameter_provenance(self) -> None:
        catalog = {value.evidence_id: value for value in self.evidence}
        intervals: list[tuple[str, str, str, bool]] = []

        def add_rational(value: RationalInterval, *, detection: bool = False) -> None:
            intervals.append((value.provenance_id, value.claim_id, value.unit, detection))

        def add_probability(value: ProbabilityInterval, *, detection: bool = False) -> None:
            intervals.append((value.provenance_id, value.claim_id, "probability", detection))

        add_probability(self.audit_policy.detection_probability, detection=True)
        add_rational(self.audit_policy.consequence)
        for submitter in self.submitter_types:
            add_rational(submitter.net_violation_gain)
        if self.assessor_contract is not None:
            contract = self.assessor_contract
            add_probability(contract.low_effort_validation_probability, detection=True)
            add_probability(contract.high_effort_validation_probability, detection=True)
            add_rational(contract.validation_reward)
            add_rational(contract.low_effort_cost)
            add_rational(contract.high_effort_cost)
        for option in self.attack_options:
            add_probability(option.information_value)
            add_rational(option.value_scale)
            add_rational(option.attack_cost)
            add_probability(option.detection_probability, detection=True)
            add_rational(option.consequence)
        for provenance_id, claim_id, unit, detection in intervals:
            evidence = catalog.get(provenance_id)
            if evidence is None:
                raise ValueError(f"parameter claim {claim_id} references unknown evidence {provenance_id}")
            if claim_id not in evidence.supports:
                raise ValueError(f"evidence {provenance_id} does not support parameter claim {claim_id}")
            if evidence.unit != unit:
                raise ValueError(
                    f"evidence {provenance_id} unit {evidence.unit!r} does not match {unit!r}"
                )
            if detection and evidence.positive_control_id is None:
                raise ValueError(f"detection claim {claim_id} requires a positive control")


class IntervalClaimResult(StrictModel):
    claim_id: str
    status: StrategicCertificateStatus
    lower_margin: SignedRational
    upper_margin: SignedRational
    required_margin: RationalNumber
    interpretation: str


class AttackerClaimResult(StrictModel):
    option_id: str
    status: StrategicCertificateStatus
    payoff_lower: SignedRational
    payoff_upper: SignedRational
    abstention_margin_lower: SignedRational
    abstention_margin_upper: SignedRational
    required_margin: RationalNumber
    interpretation: str


class StrategicAssuranceCertificate(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    certificate_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    submitter_results: tuple[IntervalClaimResult, ...]
    assessor_result: IntervalClaimResult | None
    attacker_results: tuple[AttackerClaimResult, ...]
    registered_model_status: StrategicCertificateStatus
    deployment_evidence_status: StrategicCertificateStatus
    all_evidence_deployment_eligible: bool
    governance_decision_effect: Literal["none"] = "none"
    authorization_effect: Literal["none"] = "none"
    hard_gate_effect: Literal["cannot_override_or_remove"] = "cannot_override_or_remove"
    reasons: tuple[str, ...]


class StrategicCertificateVerification(StrictModel):
    valid: bool
    registered_model_status: StrategicCertificateStatus
    deployment_evidence_status: StrategicCertificateStatus
    reasons: tuple[str, ...]


class BlackwellControlResult(StrictModel):
    option_id: str
    status: StrategicCertificateStatus
    information_order_certificate_id: str
    burden_difference_lower: SignedRational
    burden_difference_upper: SignedRational
    interpretation: str


def _fraction(value: RationalNumber) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _signed(value: Fraction) -> SignedRational:
    return SignedRational(numerator=value.numerator, denominator=value.denominator)


def _rational_bounds(value: RationalInterval) -> tuple[Fraction, Fraction]:
    return _fraction(value.lower), _fraction(value.upper)


def _probability_bounds(value: ProbabilityInterval) -> tuple[Fraction, Fraction]:
    return _fraction(value.lower), _fraction(value.upper)


def _interval_add(
    left: tuple[Fraction, Fraction], right: tuple[Fraction, Fraction]
) -> tuple[Fraction, Fraction]:
    return left[0] + right[0], left[1] + right[1]


def _interval_subtract(
    left: tuple[Fraction, Fraction], right: tuple[Fraction, Fraction]
) -> tuple[Fraction, Fraction]:
    return left[0] - right[1], left[1] - right[0]


def _interval_multiply(
    left: tuple[Fraction, Fraction], right: tuple[Fraction, Fraction]
) -> tuple[Fraction, Fraction]:
    products = tuple(a * b for a in left for b in right)
    return min(products), max(products)


def _interval_negate(value: tuple[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
    return -value[1], -value[0]


def _claim_status(
    interval: tuple[Fraction, Fraction], required_margin: Fraction
) -> StrategicCertificateStatus:
    if interval[0] >= required_margin:
        return StrategicCertificateStatus.SUPPORTED
    if interval[1] < required_margin:
        return StrategicCertificateStatus.CONTRADICTED
    return StrategicCertificateStatus.INCONCLUSIVE


def _aggregate_status(
    statuses: tuple[StrategicCertificateStatus, ...],
) -> StrategicCertificateStatus:
    if all(value is StrategicCertificateStatus.SUPPORTED for value in statuses):
        return StrategicCertificateStatus.SUPPORTED
    if any(value is StrategicCertificateStatus.CONTRADICTED for value in statuses):
        return StrategicCertificateStatus.CONTRADICTED
    return StrategicCertificateStatus.INCONCLUSIVE


def strategic_problem_sha256(problem: StrategicAssuranceProblem) -> str:
    return sha256_bytes(canonical_json_bytes(problem))


def _submitter_result(
    submitter: SubmitterType, policy: AuditPolicy
) -> IntervalClaimResult:
    detected_consequence = _interval_multiply(
        _probability_bounds(policy.detection_probability),
        _rational_bounds(policy.consequence),
    )
    deterrence_margin = _interval_subtract(
        detected_consequence, _rational_bounds(submitter.net_violation_gain)
    )
    required = _fraction(policy.strict_margin.value)
    status = _claim_status(deterrence_margin, required)
    return IntervalClaimResult(
        claim_id=f"submitter:{submitter.type_id}:unique-compliance",
        status=status,
        lower_margin=_signed(deterrence_margin[0]),
        upper_margin=_signed(deterrence_margin[1]),
        required_margin=policy.strict_margin.value,
        interpretation=(
            "Expected detected consequence minus net violation gain. Supported means the "
            "registered strict margin holds at every endpoint in the uncertainty box."
        ),
    )


def _assessor_result(contract: AssessorContract) -> IntervalClaimResult:
    validation_difference = _interval_subtract(
        _probability_bounds(contract.high_effort_validation_probability),
        _probability_bounds(contract.low_effort_validation_probability),
    )
    expected_reward_difference = _interval_multiply(
        _rational_bounds(contract.validation_reward), validation_difference
    )
    effort_cost_difference = _interval_subtract(
        _rational_bounds(contract.high_effort_cost),
        _rational_bounds(contract.low_effort_cost),
    )
    high_effort_margin = _interval_subtract(
        expected_reward_difference, effort_cost_difference
    )
    required = _fraction(contract.strict_margin.value)
    status = _claim_status(high_effort_margin, required)
    if not contract.scoring_event_observable:
        status = StrategicCertificateStatus.INCONCLUSIVE
    return IntervalClaimResult(
        claim_id=f"assessor:{contract.contract_id}:unique-high-effort",
        status=status,
        lower_margin=_signed(high_effort_margin[0]),
        upper_margin=_signed(high_effort_margin[1]),
        required_margin=contract.strict_margin.value,
        interpretation=(
            "Expected validation-reward increment minus high-effort cost increment. "
            "An unobservable scoring event makes the contract claim inconclusive."
        ),
    )


def _attacker_result(option: AttackOption) -> AttackerClaimResult:
    attack_value = _interval_multiply(
        _rational_bounds(option.value_scale),
        _probability_bounds(option.information_value),
    )
    detected_consequence = _interval_multiply(
        _probability_bounds(option.detection_probability),
        _rational_bounds(option.consequence),
    )
    payoff = _interval_subtract(
        _interval_subtract(attack_value, _rational_bounds(option.attack_cost)),
        detected_consequence,
    )
    abstention_margin = _interval_negate(payoff)
    required = _fraction(option.strict_abstention_margin.value)
    status = _claim_status(abstention_margin, required)
    if not option.risk_neutral_expected_utility:
        status = StrategicCertificateStatus.INCONCLUSIVE
    return AttackerClaimResult(
        option_id=option.option_id,
        status=status,
        payoff_lower=_signed(payoff[0]),
        payoff_upper=_signed(payoff[1]),
        abstention_margin_lower=_signed(abstention_margin[0]),
        abstention_margin_upper=_signed(abstention_margin[1]),
        required_margin=option.strict_abstention_margin.value,
        interpretation=(
            "Risk-neutral attack payoff lambda*V-cost-detection*consequence. Supported "
            "means abstention beats this option by the strict margin at every endpoint."
        ),
    )


def solve_strategic_assurance(
    problem: StrategicAssuranceProblem, *, certificate_id: str
) -> StrategicAssuranceCertificate:
    """Compute an exact interval certificate using pessimistic tie handling."""

    submitter_results = tuple(
        _submitter_result(submitter, problem.audit_policy)
        for submitter in problem.submitter_types
    )
    assessor_result = (
        _assessor_result(problem.assessor_contract)
        if problem.assessor_contract is not None
        else None
    )
    attacker_results = tuple(_attacker_result(option) for option in problem.attack_options)
    statuses = tuple(value.status for value in submitter_results) + tuple(
        value.status for value in attacker_results
    )
    if assessor_result is not None:
        statuses += (assessor_result.status,)
    registered_model_status = _aggregate_status(statuses)
    deployment_evidence_status = registered_model_status
    reasons: list[str] = []
    if not problem.material_types_complete:
        reasons.append(
            "material actor types are incomplete: " + ", ".join(problem.omitted_material_types)
        )
        if deployment_evidence_status is StrategicCertificateStatus.SUPPORTED:
            deployment_evidence_status = StrategicCertificateStatus.INCONCLUSIVE
    if not problem.audit_policy.commitment_observable:
        reasons.append("the audit policy is not an observable Stackelberg commitment")
        deployment_evidence_status = StrategicCertificateStatus.INCONCLUSIVE
    all_deployment_eligible = all(value.deployment_eligible for value in problem.evidence)
    if not all_deployment_eligible:
        deployment_evidence_status = StrategicCertificateStatus.INCONCLUSIVE
        reasons.append("one or more parameter records are not eligible for deployment claims")
    if registered_model_status is StrategicCertificateStatus.CONTRADICTED:
        reasons.append("at least one registered strategic claim is contradicted over its interval")
    elif deployment_evidence_status is StrategicCertificateStatus.INCONCLUSIVE and not reasons:
        reasons.append("at least one registered interval crosses its required strict margin")
    return StrategicAssuranceCertificate(
        certificate_id=certificate_id,
        problem_sha256=strategic_problem_sha256(problem),
        submitter_results=submitter_results,
        assessor_result=assessor_result,
        attacker_results=attacker_results,
        registered_model_status=registered_model_status,
        deployment_evidence_status=deployment_evidence_status,
        all_evidence_deployment_eligible=all_deployment_eligible,
        reasons=tuple(reasons),
    )


def verify_strategic_assurance(
    problem: StrategicAssuranceProblem,
    certificate: StrategicAssuranceCertificate,
) -> StrategicCertificateVerification:
    """Replay every exact calculation and reject a modified certificate."""

    expected = solve_strategic_assurance(problem, certificate_id=certificate.certificate_id)
    reasons: list[str] = []
    if certificate.problem_sha256 != strategic_problem_sha256(problem):
        reasons.append("strategic problem digest mismatch")
    if certificate != expected:
        reasons.append("strategic certificate does not replay exactly")
    return StrategicCertificateVerification(
        valid=not reasons,
        registered_model_status=expected.registered_model_status,
        deployment_evidence_status=expected.deployment_evidence_status,
        reasons=tuple(reasons),
    )


def _attack_burden(option: AttackOption) -> tuple[Fraction, Fraction]:
    return _interval_add(
        _rational_bounds(option.attack_cost),
        _interval_multiply(
            _probability_bounds(option.detection_probability),
            _rational_bounds(option.consequence),
        ),
    )


def blackwell_safe_control_improvement(
    *,
    less_informative: AttackOption,
    more_informative: AttackOption,
    garbling: GarblingVerification,
) -> BlackwellControlResult:
    """Check the interval-strengthened premises of strategic theorem GT-4."""

    if less_informative.option_id != more_informative.option_id:
        raise ValueError("Blackwell control comparison requires the same attack option")
    if less_informative.recipient_type != more_informative.recipient_type:
        raise ValueError("Blackwell control comparison requires the same recipient type")
    if less_informative.value_scale != more_informative.value_scale:
        raise ValueError("Blackwell control comparison requires the same value scale")
    if less_informative.consequence != more_informative.consequence:
        raise ValueError("Blackwell control comparison requires the same consequence interval")
    if less_informative.information_experiment_id != garbling.dominated_experiment_id:
        raise ValueError("less-informative option does not match the dominated experiment")
    if more_informative.information_experiment_id != garbling.dominant_experiment_id:
        raise ValueError("more-informative option does not match the dominant experiment")
    less_burden = _attack_burden(less_informative)
    more_burden = _attack_burden(more_informative)
    burden_difference = _interval_subtract(less_burden, more_burden)
    if not garbling.valid:
        status = StrategicCertificateStatus.INCONCLUSIVE
    elif burden_difference[0] >= 0:
        status = StrategicCertificateStatus.SUPPORTED
    elif burden_difference[1] < 0:
        status = StrategicCertificateStatus.CONTRADICTED
    else:
        status = StrategicCertificateStatus.INCONCLUSIVE
    return BlackwellControlResult(
        option_id=less_informative.option_id,
        status=status,
        information_order_certificate_id=garbling.certificate_id,
        burden_difference_lower=_signed(burden_difference[0]),
        burden_difference_upper=_signed(burden_difference[1]),
        interpretation=(
            "A verified Blackwell garbling plus a non-smaller non-information attack "
            "burden guarantees that the control does not increase this attack payoff."
        ),
    )
