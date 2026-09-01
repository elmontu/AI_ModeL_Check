from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from model_release_assurance.decision_theory import (
    deterministic_experiment,
    deterministic_garbling_certificate,
    verify_garbling,
)
from model_release_assurance.incomplete_portfolio import RationalNumber
from model_release_assurance.strategic_assurance import (
    AssessorContract,
    AttackOption,
    AuditPolicy,
    EvidenceKind,
    GovernanceContext,
    ParameterEvidence,
    ProbabilityInterval,
    RationalInterval,
    RationalQuantity,
    StrategicAssuranceProblem,
    StrategicCertificateStatus,
    SubmitterType,
    blackwell_safe_control_improvement,
    solve_strategic_assurance,
    verify_strategic_assurance,
)


def rn(numerator: int, denominator: int = 1) -> RationalNumber:
    return RationalNumber(numerator=numerator, denominator=denominator)


def ri(
    lower: tuple[int, int],
    upper: tuple[int, int],
    *,
    unit: str,
    evidence_id: str,
    claim_id: str,
) -> RationalInterval:
    return RationalInterval(
        lower=rn(*lower),
        upper=rn(*upper),
        unit=unit,
        provenance_id=evidence_id,
        claim_id=claim_id,
    )


def pi(
    lower: tuple[int, int],
    upper: tuple[int, int],
    *,
    evidence_id: str,
    claim_id: str,
) -> ProbabilityInterval:
    return ProbabilityInterval(
        lower=rn(*lower),
        upper=rn(*upper),
        provenance_id=evidence_id,
        claim_id=claim_id,
    )


def evidence(
    evidence_id: str,
    claim_id: str,
    unit: str,
    *,
    detection: bool = False,
    eligible: bool = True,
    kind: EvidenceKind = EvidenceKind.PROSPECTIVE_MEASUREMENT,
) -> ParameterEvidence:
    return ParameterEvidence(
        evidence_id=evidence_id,
        kind=kind,
        source=f"registered source for {claim_id}",
        source_sha256=("0" * 64 if eligible else None),
        population="registered synthetic-health release participants",
        collected_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        method="preregistered blinded measurement or enforceability review",
        uncertainty_method="simultaneous lower and upper confidence endpoints",
        unit=unit,
        supports=(claim_id,),
        positive_control_id=(f"pc:{evidence_id}" if detection else None),
        deployment_eligible=eligible,
    )


def supported_problem(
    *,
    all_evidence_eligible: bool = True,
    commitment_observable: bool = True,
    material_types_complete: bool = True,
    audit_detection: tuple[tuple[int, int], tuple[int, int]] = ((3, 5), (7, 10)),
    audit_consequence: tuple[tuple[int, int], tuple[int, int]] = ((24, 1), (30, 1)),
    submitter_gain: tuple[tuple[int, int], tuple[int, int]] = ((8, 1), (12, 1)),
    risk_neutral: bool = True,
) -> StrategicAssuranceProblem:
    claims: list[tuple[str, str, str, bool]] = []

    def add(evidence_id: str, claim_id: str, unit: str, detection: bool = False) -> None:
        claims.append((evidence_id, claim_id, unit, detection))

    add("ev.audit.q", "audit.q", "probability", True)
    add("ev.audit.f", "audit.f", "SGD")
    add("ev.submitter.g", "submitter.g", "SGD")
    add("ev.assessor.sl", "assessor.sl", "probability", True)
    add("ev.assessor.sh", "assessor.sh", "probability", True)
    add("ev.assessor.reward", "assessor.reward", "SGD")
    add("ev.assessor.kl", "assessor.kl", "SGD")
    add("ev.assessor.kh", "assessor.kh", "SGD")
    add("ev.attack.v", "attack.v", "probability")
    add("ev.attack.lambda", "attack.lambda", "SGD")
    add("ev.attack.cost", "attack.cost", "SGD")
    add("ev.attack.d", "attack.d", "probability", True)
    add("ev.attack.p", "attack.p", "SGD")
    evidence_records = tuple(
        evidence(
            evidence_id,
            claim_id,
            unit,
            detection=detection,
            eligible=all_evidence_eligible,
            kind=(
                EvidenceKind.PROSPECTIVE_MEASUREMENT
                if all_evidence_eligible
                else EvidenceKind.SYNTHETIC_ASSUMPTION
            ),
        )
        for evidence_id, claim_id, unit, detection in claims
    )
    return StrategicAssuranceProblem(
        assessment_id="strategic-health-001",
        assessment_time=datetime(2026, 8, 26, tzinfo=timezone.utc),
        governance_context=GovernanceContext(
            accountable_model_owner="hospital_model_office",
            decision_authority="hospital_release_committee",
            independent_review_body="external_assurance_panel",
            affected_party_groups=("patients", "approved_researchers"),
            governance_objective=(
                "decide whether the registered model use is legitimate and satisfies all "
                "non-compensable governance and assurance requirements"
            ),
            conflict_of_interest_controls=(
                "owner cannot approve its own assessment",
                "adverse findings go directly to the decision authority",
            ),
            contestation_process="recorded objection and new-instance reconsideration",
            incident_and_retirement_authority="hospital_incident_board",
        ),
        players=("release_authority", "submitter", "assessor", "recipient"),
        timing=(
            "authority commits to audit and controls",
            "submitter and assessor choose effort",
            "recipient observes release and chooses attack or abstention",
        ),
        information_structure=(
            "audit policy is public before submitter action",
            "recipient observes the released interface",
        ),
        collusion_scope="submitter-assessor and recipient coalitions are registered separately",
        material_types_complete=material_types_complete,
        omitted_material_types=(() if material_types_complete else ("foreign_cloud_operator",)),
        submitter_types=(
            SubmitterType(
                type_id="schedule-pressured-team",
                description="team may omit an adverse result to accelerate release",
                net_violation_gain=ri(
                    submitter_gain[0],
                    submitter_gain[1],
                    unit="SGD",
                    evidence_id="ev.submitter.g",
                    claim_id="submitter.g",
                ),
            ),
        ),
        audit_policy=AuditPolicy(
            policy_id="health-audit-v1",
            detection_probability=pi(
                audit_detection[0],
                audit_detection[1],
                evidence_id="ev.audit.q",
                claim_id="audit.q",
            ),
            consequence=ri(
                audit_consequence[0],
                audit_consequence[1],
                unit="SGD",
                evidence_id="ev.audit.f",
                claim_id="audit.f",
            ),
            strict_margin=RationalQuantity(value=rn(1), unit="SGD"),
            commitment_observable=commitment_observable,
            consequence_enforceable=True,
        ),
        assessor_contract=AssessorContract(
            contract_id="independent-review-v1",
            low_effort_validation_probability=pi(
                (1, 2), (3, 5), evidence_id="ev.assessor.sl", claim_id="assessor.sl"
            ),
            high_effort_validation_probability=pi(
                (4, 5), (9, 10), evidence_id="ev.assessor.sh", claim_id="assessor.sh"
            ),
            validation_reward=ri(
                (30, 1),
                (35, 1),
                unit="SGD",
                evidence_id="ev.assessor.reward",
                claim_id="assessor.reward",
            ),
            low_effort_cost=ri(
                (2, 1),
                (3, 1),
                unit="SGD",
                evidence_id="ev.assessor.kl",
                claim_id="assessor.kl",
            ),
            high_effort_cost=ri(
                (5, 1),
                (6, 1),
                unit="SGD",
                evidence_id="ev.assessor.kh",
                claim_id="assessor.kh",
            ),
            strict_margin=RationalQuantity(value=rn(1), unit="SGD"),
            scoring_event_observable=True,
        ),
        attack_options=(
            AttackOption(
                option_id="registered-membership-inference",
                recipient_type="approved_researcher",
                jurisdiction="SG",
                threat_mapping="membership inference through the bounded research API",
                information_experiment_id="health-bounded-channel",
                decision_problem_id="membership-success",
                information_value=pi(
                    (1, 5), (1, 4), evidence_id="ev.attack.v", claim_id="attack.v"
                ),
                value_scale=ri(
                    (20, 1),
                    (24, 1),
                    unit="SGD",
                    evidence_id="ev.attack.lambda",
                    claim_id="attack.lambda",
                ),
                attack_cost=ri(
                    (7, 1),
                    (9, 1),
                    unit="SGD",
                    evidence_id="ev.attack.cost",
                    claim_id="attack.cost",
                ),
                detection_probability=pi(
                    (4, 5), (9, 10), evidence_id="ev.attack.d", claim_id="attack.d"
                ),
                consequence=ri(
                    (10, 1),
                    (12, 1),
                    unit="SGD",
                    evidence_id="ev.attack.p",
                    claim_id="attack.p",
                ),
                strict_abstention_margin=RationalQuantity(value=rn(1), unit="SGD"),
                consequence_enforceable=True,
                risk_neutral_expected_utility=risk_neutral,
            ),
        ),
        evidence=evidence_records,
    )


class StrategicAssuranceTests(unittest.TestCase):
    def test_supported_exact_certificate_replays(self) -> None:
        problem = supported_problem()
        certificate = solve_strategic_assurance(problem, certificate_id="strategic-cert-001")
        self.assertEqual(certificate.registered_model_status, StrategicCertificateStatus.SUPPORTED)
        self.assertEqual(certificate.deployment_evidence_status, StrategicCertificateStatus.SUPPORTED)
        self.assertEqual(certificate.governance_decision_effect, "none")
        self.assertEqual(certificate.authorization_effect, "none")
        self.assertEqual(certificate.hard_gate_effect, "cannot_override_or_remove")
        self.assertEqual(certificate.submitter_results[0].lower_margin.numerator, 12)
        self.assertEqual(certificate.submitter_results[0].lower_margin.denominator, 5)
        self.assertEqual(certificate.assessor_result.lower_margin.numerator, 2)
        self.assertEqual(certificate.attacker_results[0].payoff_upper.numerator, -9)
        self.assertTrue(verify_strategic_assurance(problem, certificate).valid)

    def test_synthetic_inputs_cannot_support_deployment_claim(self) -> None:
        problem = supported_problem(all_evidence_eligible=False)
        certificate = solve_strategic_assurance(problem, certificate_id="strategic-cert-synthetic")
        self.assertEqual(certificate.registered_model_status, StrategicCertificateStatus.SUPPORTED)
        self.assertEqual(certificate.deployment_evidence_status, StrategicCertificateStatus.INCONCLUSIVE)
        self.assertFalse(certificate.all_evidence_deployment_eligible)

    def test_incomplete_types_fail_closed(self) -> None:
        certificate = solve_strategic_assurance(
            supported_problem(material_types_complete=False),
            certificate_id="strategic-cert-incomplete",
        )
        self.assertEqual(certificate.registered_model_status, StrategicCertificateStatus.SUPPORTED)
        self.assertEqual(certificate.deployment_evidence_status, StrategicCertificateStatus.INCONCLUSIVE)
        self.assertIn("foreign_cloud_operator", certificate.reasons[0])

    def test_unobservable_commitment_invalidates_stackelberg_claim(self) -> None:
        certificate = solve_strategic_assurance(
            supported_problem(commitment_observable=False),
            certificate_id="strategic-cert-hidden-policy",
        )
        self.assertEqual(certificate.registered_model_status, StrategicCertificateStatus.SUPPORTED)
        self.assertEqual(certificate.deployment_evidence_status, StrategicCertificateStatus.INCONCLUSIVE)

    def test_equality_does_not_receive_favourable_tie_credit(self) -> None:
        problem = supported_problem(
            audit_detection=((1, 2), (1, 2)),
            audit_consequence=((20, 1), (20, 1)),
            submitter_gain=((10, 1), (10, 1)),
        )
        result = solve_strategic_assurance(
            problem, certificate_id="strategic-cert-tie"
        ).submitter_results[0]
        self.assertEqual(result.status, StrategicCertificateStatus.CONTRADICTED)
        self.assertEqual(result.lower_margin.numerator, 0)

    def test_uncertainty_crossing_required_margin_is_inconclusive(self) -> None:
        problem = supported_problem(
            audit_detection=((1, 2), (7, 10)),
            audit_consequence=((20, 1), (20, 1)),
            submitter_gain=((10, 1), (14, 1)),
        )
        result = solve_strategic_assurance(
            problem, certificate_id="strategic-cert-crossing"
        ).submitter_results[0]
        self.assertEqual(result.status, StrategicCertificateStatus.INCONCLUSIVE)
        self.assertEqual((result.lower_margin.numerator, result.upper_margin.numerator), (-4, 4))

    def test_non_risk_neutral_attacker_claim_is_inconclusive(self) -> None:
        result = solve_strategic_assurance(
            supported_problem(risk_neutral=False),
            certificate_id="strategic-cert-risk-model",
        ).attacker_results[0]
        self.assertEqual(result.status, StrategicCertificateStatus.INCONCLUSIVE)

    def test_unenforceable_consequence_must_be_zero(self) -> None:
        option = supported_problem().attack_options[0]
        with self.assertRaises(ValidationError):
            AttackOption.model_validate(
                {
                    **option.model_dump(mode="json"),
                    "consequence_enforceable": False,
                }
            )

    def test_independent_reviewer_cannot_be_the_model_owner(self) -> None:
        context = supported_problem().governance_context
        with self.assertRaises(ValidationError):
            GovernanceContext.model_validate(
                {
                    **context.model_dump(mode="json"),
                    "independent_review_body": context.accountable_model_owner,
                }
            )

    def test_unknown_parameter_provenance_is_rejected(self) -> None:
        problem = supported_problem()
        changed = problem.audit_policy.model_copy(
            update={
                "detection_probability": problem.audit_policy.detection_probability.model_copy(
                    update={"provenance_id": "ev.missing"}
                )
            }
        )
        with self.assertRaises(ValidationError):
            StrategicAssuranceProblem.model_validate(
                {**problem.model_dump(mode="json"), "audit_policy": changed.model_dump(mode="json")}
            )

    def test_claim_not_supported_by_evidence_is_rejected(self) -> None:
        problem = supported_problem()
        changed = problem.audit_policy.detection_probability.model_copy(
            update={"claim_id": "audit.unrelated"}
        )
        with self.assertRaises(ValidationError):
            StrategicAssuranceProblem.model_validate(
                {
                    **problem.model_dump(mode="json"),
                    "audit_policy": {
                        **problem.audit_policy.model_dump(mode="json"),
                        "detection_probability": changed.model_dump(mode="json"),
                    },
                }
            )

    def test_detection_probability_requires_positive_control(self) -> None:
        problem = supported_problem()
        records = list(problem.evidence)
        index = next(i for i, item in enumerate(records) if item.evidence_id == "ev.audit.q")
        records[index] = records[index].model_copy(update={"positive_control_id": None})
        with self.assertRaises(ValidationError):
            StrategicAssuranceProblem.model_validate(
                {**problem.model_dump(mode="json"), "evidence": [v.model_dump(mode="json") for v in records]}
            )

    def test_parameter_unit_mismatch_is_rejected(self) -> None:
        problem = supported_problem()
        records = list(problem.evidence)
        index = next(i for i, item in enumerate(records) if item.evidence_id == "ev.audit.f")
        records[index] = records[index].model_copy(update={"unit": "USD"})
        with self.assertRaises(ValidationError):
            StrategicAssuranceProblem.model_validate(
                {**problem.model_dump(mode="json"), "evidence": [v.model_dump(mode="json") for v in records]}
            )

    def test_future_dated_parameter_evidence_is_rejected(self) -> None:
        problem = supported_problem()
        records = list(problem.evidence)
        records[0] = records[0].model_copy(
            update={"collected_at": datetime(2026, 8, 27, tzinfo=timezone.utc)}
        )
        with self.assertRaises(ValidationError):
            StrategicAssuranceProblem.model_validate(
                {**problem.model_dump(mode="json"), "evidence": [v.model_dump(mode="json") for v in records]}
            )

    def test_deployment_eligible_evidence_requires_source_digest(self) -> None:
        record = evidence("ev.digest", "claim.digest", "SGD", eligible=True)
        with self.assertRaises(ValidationError):
            ParameterEvidence.model_validate(
                {**record.model_dump(mode="json"), "source_sha256": None}
            )

    def test_anonymous_attacker_gets_no_monitoring_deterrence_credit(self) -> None:
        problem = supported_problem()
        base = problem.attack_options[0]
        anonymous = base.model_copy(
            update={
                "option_id": "anonymous-external-inference",
                "recipient_type": "anonymous_external_attacker",
                "jurisdiction": "unresolved",
                "information_value": base.information_value.model_copy(
                    update={"lower": rn(7, 20), "upper": rn(9, 20)}
                ),
                "attack_cost": base.attack_cost.model_copy(
                    update={"lower": rn(2), "upper": rn(4)}
                ),
                "consequence": base.consequence.model_copy(
                    update={"lower": rn(0), "upper": rn(0)}
                ),
                "consequence_enforceable": False,
            }
        )
        changed = StrategicAssuranceProblem.model_validate(
            {
                **problem.model_dump(mode="json"),
                "attack_options": [anonymous.model_dump(mode="json")],
            }
        )
        result = solve_strategic_assurance(
            changed, certificate_id="strategic-cert-anonymous"
        ).attacker_results[0]
        self.assertEqual(result.status, StrategicCertificateStatus.CONTRADICTED)
        self.assertEqual(result.payoff_lower.numerator, 3)

    def test_modified_certificate_fails_exact_replay(self) -> None:
        problem = supported_problem()
        certificate = solve_strategic_assurance(problem, certificate_id="strategic-cert-tamper")
        modified = certificate.model_copy(
            update={"deployment_evidence_status": StrategicCertificateStatus.INCONCLUSIVE}
        )
        verification = verify_strategic_assurance(problem, modified)
        self.assertFalse(verification.valid)
        self.assertIn("strategic certificate does not replay exactly", verification.reasons)

    def test_blackwell_safe_control_improvement_replays(self) -> None:
        dominant = deterministic_experiment(
            experiment_id="open-channel",
            threat_id="membership",
            population_scope_id="health-population",
            state_ids=("member", "nonmember"),
            observations=("member", "nonmember"),
            interface_description="unbounded exact response",
        )
        dominated = deterministic_experiment(
            experiment_id="constant-channel",
            threat_id="membership",
            population_scope_id="health-population",
            state_ids=("member", "nonmember"),
            observations=("constant", "constant"),
            interface_description="constant response",
        )
        certificate = deterministic_garbling_certificate(
            dominant,
            dominated,
            certificate_id="garbling-open-to-constant",
        )
        garbling = verify_garbling(dominant, dominated, certificate)
        base = supported_problem().attack_options[0]
        more = base.model_copy(update={"information_experiment_id": dominant.experiment_id})
        less = base.model_copy(
            update={
                "information_experiment_id": dominated.experiment_id,
                "attack_cost": base.attack_cost.model_copy(
                    update={"lower": rn(15), "upper": rn(16)}
                ),
            }
        )
        result = blackwell_safe_control_improvement(
            less_informative=less,
            more_informative=more,
            garbling=garbling,
        )
        self.assertEqual(result.status, StrategicCertificateStatus.SUPPORTED)
        self.assertGreaterEqual(result.burden_difference_lower.numerator, 0)

    def test_invalid_information_order_is_inconclusive(self) -> None:
        dominant = deterministic_experiment(
            experiment_id="dominant-channel",
            threat_id="membership",
            population_scope_id="health-population",
            state_ids=("member", "nonmember"),
            observations=("member", "nonmember"),
            interface_description="dominant",
        )
        dominated = deterministic_experiment(
            experiment_id="dominated-channel",
            threat_id="membership",
            population_scope_id="health-population",
            state_ids=("member", "nonmember"),
            observations=("constant", "constant"),
            interface_description="dominated",
        )
        garbling = verify_garbling(
            dominant,
            dominated,
            deterministic_garbling_certificate(
                dominant, dominated, certificate_id="garbling-valid-base"
            ),
        ).model_copy(update={"valid": False, "reasons": ("forced invalid",)})
        base = supported_problem().attack_options[0]
        result = blackwell_safe_control_improvement(
            less_informative=base.model_copy(
                update={"information_experiment_id": dominated.experiment_id}
            ),
            more_informative=base.model_copy(
                update={"information_experiment_id": dominant.experiment_id}
            ),
            garbling=garbling,
        )
        self.assertEqual(result.status, StrategicCertificateStatus.INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
