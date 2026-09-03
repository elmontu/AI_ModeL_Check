from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path

from model_release_assurance.analyzers.finite_channel import FiniteChannelCeilingAnalyzer
from model_release_assurance.decision import (
    decision_game_sha256,
    decide_threat,
    population_scope_sha256,
)
from model_release_assurance.decision_theory import exact_guess_problem
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import AnalyzerError, IntegrityError
from model_release_assurance.incomplete_portfolio import (
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    FiniteStatePriorEvidence,
    IncompletePortfolioProblem,
    StatisticalCoverage,
    finite_prior_contract_sha256,
    solve_analytic_portfolio,
)
from model_release_assurance.integrity import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from model_release_assurance.models import (
    AnalyzerRequirement,
    AnalyzerProvenance,
    AssessmentRequest,
    AttackBatteryStatus,
    CeilingAttackBatteryMode,
    EvidenceBindingContext,
    EvidenceClass,
    EvidenceContext,
    FiniteDecisionGame,
    FiniteChannelCeilingInput,
    FiniteGameState,
    PolicyBundle,
    PolicyReference,
    PolicyRule,
    RationalProbability,
    ThreatContract,
    Verdict,
)
from model_release_assurance.portfolio_statistics import (
    AssuranceErrorBudget,
    ErrorBudgetAllocation,
    IncompletePortfolioSpecification,
    MultinomialCountsFile,
    MultinomialEvidenceRequest,
    MultinomialReleaseCounts,
    MultinomialSamplingPlan,
    MultinomialSamplingPlanRelease,
    MultinomialStateCounts,
    SourceFileReference,
    compile_multinomial_portfolio_problem,
    generate_simultaneous_multinomial_evidence,
)
from model_release_assurance.services import (
    AnalyzerServiceRegistry,
    LocalAnalyzerService,
)


ROOT = Path(__file__).resolve().parents[1]


def _reference(evidence_id: str, *supports: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        source_path=f"{evidence_id}.json",
        source_sha256="a" * 64,
        supports=tuple(supports),
    )


def _fixture(
    lower: tuple[tuple[float, float], tuple[float, float]],
    upper: tuple[tuple[float, float], tuple[float, float]],
    *,
    model_family: str = "xgboost",
    tolerance: float = 0.6,
    flags: dict[str, bool] | None = None,
    prior: tuple[float, float] = (0.5, 0.5),
    coverage: StatisticalCoverage = StatisticalCoverage.SIMULTANEOUS,
) -> tuple[object, ThreatContract, object, FiniteChannelCeilingInput]:
    prior_fractions = tuple(Fraction(str(value)) for value in prior)
    prior_total = sum(prior_fractions, Fraction(0))
    rational_prior = tuple(
        RationalProbability(
            numerator=(value / prior_total).numerator,
            denominator=(value / prior_total).denominator,
        )
        for value in prior_fractions
    )
    request = AssessmentRequest.model_validate_json(
        (ROOT / "examples" / "request.json").read_text(encoding="utf-8")
    )
    release = request.release.model_copy(update={"model_family": model_family})
    raw_threat = next(
        value
        for value in request.threats
        if value.decision_metric == "equal_prior_membership_success"
    ).model_dump(mode="python")
    raw_threat["tolerance"] = tolerance
    raw_threat["finite_game"] = FiniteDecisionGame(
        game_id="equal-prior-membership",
        states=(
            FiniteGameState(
                state_id="out",
                secret_value_definition="the audited record was not in training",
            ),
            FiniteGameState(
                state_id="in",
                secret_value_definition="the audited record was in training",
            ),
        ),
        prior=(
            RationalProbability(numerator=1, denominator=2),
            RationalProbability(numerator=1, denominator=2),
        ),
        prior_basis="policy-frozen randomized IN/OUT audit game",
        authority="unit-test policy authority",
    ).model_dump(mode="python")
    threat = ThreatContract.model_validate(raw_threat)
    scope = next(
        value
        for value in request.population_scopes
        if value.scope_id == threat.population_scope_id
    )
    interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))
    context = EvidenceContext(
        release_id=release.release_id,
        release_contract_sha256=sha256_bytes(canonical_json_bytes(release)),
        policy_sha256="b" * 64,
        artifact_sha256=release.artifact_sha256,
        interface_sha256=interface_sha256,
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        decision_game_sha256=decision_game_sha256(threat, scope),
        observed_at=datetime.now(timezone.utc),
    )
    mechanism_supports = (
        f"coupling:{CouplingModel.CONDITIONAL_INDEPENDENCE.value}",
        f"artifact:{release.artifact_sha256}",
        f"interface:{interface_sha256}",
        f"complete-transcript:{release.release_id}",
    )
    problem = IncompletePortfolioProblem(
        portfolio_id="finite-channel-test",
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        threat_id=threat.threat_id,
        decision_game_sha256=decision_game_sha256(threat, scope),
        state_ids=("out", "in"),
        prior=prior,
        rational_prior=rational_prior,
        releases=(ConditionalMarginalBounds(
            release_id=release.release_id,
            observation_ids=("response-0", "response-1"),
            lower=lower,
            upper=upper,
            evidence=_reference(
                "finite-marginal",
                f"marginal:{release.release_id}",
                f"coverage:{coverage.value}",
                *(("error-budget:test-budget:test-allocation",)
                  if coverage is StatisticalCoverage.SIMULTANEOUS else ()),
                *(("confidence-endpoints:outward-validated",)
                  if coverage is StatisticalCoverage.SIMULTANEOUS else ()),
            ),
        ),),
        decision_problem=exact_guess_problem(
            ("out", "in"),
            problem_id="equal-prior-membership",
        ),
        coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
        coverage=coverage,
        coverage_confidence=(
            0.95 if coverage is StatisticalCoverage.SIMULTANEOUS else 1.0
        ),
        selection_scope="all registered states, observations, models, and decisions",
        prior_evidence=_reference(
            "finite-prior",
            "prior",
            f"decision-game:{decision_game_sha256(threat, scope)}",
            "finite-prior:"
            f"{finite_prior_contract_sha256(('out', 'in'), rational_prior)}",
        ),
        mechanism_assumptions=("one complete bounded recipient transcript",),
        mechanism_evidence=(
            _reference("finite-mechanism", *mechanism_supports),
        ),
    )
    entry = solve_analytic_portfolio(problem, method="envelope")
    eligibility = {
        "release_enforced_finite_alphabet": True,
        "complete_interface_coverage": True,
        "recipient_realizable": True,
        "bounded_transcript_complete": True,
    }
    eligibility.update(flags or {})
    value = FiniteChannelCeilingInput(
        threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,
        analytic_evidence=entry,
        observed_interface_sha256=interface_sha256,
        observed_artifact_sha256=release.artifact_sha256,
        interface_observation_definition=(
            "complete response, error, timing, and bounded-query transcript"
        ),
        state_trials=(
            (2_000, 2_000)
            if coverage is StatisticalCoverage.SIMULTANEOUS
            else None
        ),
        evidence_context=context,
        provenance=AnalyzerProvenance(
            tool="finite-channel-test-worker",
            tool_version="1.0",
            producer={
                "service_id": "mra.analyzer.finite_channel_ceiling",
                "service_version": "1.0.0",
                "implementation_sha256": "c" * 64,
                "configuration_sha256": "d" * 64,
            },
            configuration_path="finite-config.json",
            source_path="finite-input.json",
            source_sha256="e" * 64,
            bound_fields=("analyzer",),
        ),
        **eligibility,
    )
    return release, threat, scope, value


class FiniteChannelCeilingTests(unittest.TestCase):
    def test_typed_prior_preserves_non_binary_rational_probabilities(self) -> None:
        evidence = FiniteStatePriorEvidence(
            threat_id="three-state-secret",
            population_scope_id="population-scope",
            population_scope_sha256="1" * 64,
            decision_game_sha256="2" * 64,
            state_ids=("a", "b", "c"),
            prior=(
                RationalProbability(numerator=1, denominator=3),
                RationalProbability(numerator=1, denominator=3),
                RationalProbability(numerator=1, denominator=3),
            ),
            prior_definition="policy-frozen uniform three-state game",
            authority="unit-test population steward",
        )

        self.assertEqual(
            tuple(value.as_fraction() for value in evidence.prior),
            (Fraction(1, 3), Fraction(1, 3), Fraction(1, 3)),
        )
        serialized_prior = evidence.model_dump(mode="json")["prior"]
        self.assertEqual(
            serialized_prior,
            [
                {"numerator": 1, "denominator": 3},
                {"numerator": 1, "denominator": 3},
                {"numerator": 1, "denominator": 3},
            ],
        )
        self.assertEqual(
            finite_prior_contract_sha256(evidence.state_ids, evidence.prior),
            sha256_bytes(canonical_json_bytes({
                "domain": "MRA-FINITE-PRIOR-2",
                "state_ids": evidence.state_ids,
                "prior": serialized_prior,
            })),
        )

        rounded = evidence.model_dump(mode="json")
        rounded["prior"] = [1 / 3, 1 / 3, 1 / 3]
        with self.assertRaisesRegex(ValueError, "valid dictionary or instance"):
            FiniteStatePriorEvidence.model_validate(rounded)

    def test_engine_replays_statistical_sources_and_exact_state_trials(self) -> None:
        request = AssessmentRequest.model_validate_json(
            (ROOT / "examples" / "request.json").read_text(encoding="utf-8")
        )
        release = request.release.model_copy(update={
            "model_family": "xgboost",
            "artifact_path": str(
                (ROOT / "examples" / request.release.artifact_path).resolve()
            ),
        })
        threat = next(
            value
            for value in request.threats
            if value.decision_metric == "equal_prior_membership_success"
        )
        threat = threat.model_copy(update={
            "finite_game": FiniteDecisionGame(
                game_id="equal-prior-membership",
                states=(
                    FiniteGameState(
                        state_id="out",
                        secret_value_definition="the audited record was not in training",
                    ),
                    FiniteGameState(
                        state_id="in",
                        secret_value_definition="the audited record was in training",
                    ),
                ),
                prior=(
                    RationalProbability(numerator=1, denominator=2),
                    RationalProbability(numerator=1, denominator=2),
                ),
                prior_basis="policy-frozen randomized IN/OUT audit game",
                authority="unit-test policy authority",
            ),
        })
        scope = next(
            value
            for value in request.population_scopes
            if value.scope_id == threat.population_scope_id
        )
        scope_sha256 = population_scope_sha256(scope)
        game_sha256 = decision_game_sha256(threat, scope)
        interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))

        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            plan_path = base_dir / "plan.json"
            counts_path = base_dir / "counts.json"
            budget_path = base_dir / "budget.json"
            evidence_path = base_dir / "simultaneous-evidence.json"
            prior_path = base_dir / "prior.json"
            mechanism_path = base_dir / "mechanism.json"
            policy_path = base_dir / "policy.json"
            config_path = base_dir / "finite-config.json"
            input_path = base_dir / "finite-input.json"

            config_path.write_text("{}\n", encoding="utf-8")
            service = LocalAnalyzerService(FiniteChannelCeilingAnalyzer())
            policy = PolicyBundle(
                policy_id="finite-channel-test-policy",
                policy_version="1.0.0",
                effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                rules=(PolicyRule(
                    threat_id=threat.threat_id,
                    kind=threat.kind,
                    mandatory=True,
                    decision_metric=threat.decision_metric,
                    metric_parameters=threat.metric_parameters,
                    finite_game=threat.finite_game,
                    tolerance=threat.tolerance,
                    tolerance_basis=threat.tolerance_basis,
                    ceiling_attack_battery_mode=CeilingAttackBatteryMode.WAIVED,
                    ceiling_attack_battery_waiver_reason=(
                        "unit-test policy explicitly waives the empirical attack battery"
                    ),
                ),),
                analyzer_requirements=(AnalyzerRequirement(
                    threat_id=threat.threat_id,
                    analyzer="finite_channel_ceiling",
                    minimum_service_version=service.descriptor.service_version,
                    accepted_implementation_sha256s=(
                        service.descriptor.implementation_sha256,
                    ),
                    accepted_configuration_sha256s=(sha256_file(config_path),),
                    required=True,
                ),),
                accepted_selection_policy_sha256s=("0" * 64,),
            )
            policy_path.write_text(
                policy.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            policy_sha256 = sha256_file(policy_path)

            binding_context = EvidenceBindingContext(
                release_id=release.release_id,
                release_contract_sha256=sha256_bytes(canonical_json_bytes(release)),
                policy_sha256=policy_sha256,
                artifact_sha256=release.artifact_sha256,
                interface_sha256=interface_sha256,
                population_scope_id=scope.scope_id,
                population_scope_sha256=scope_sha256,
                decision_game_sha256=game_sha256,
            )

            plan = MultinomialSamplingPlan(
                plan_id="finite-channel-plan",
                family_id="finite-channel-family",
                portfolio_id="finite-channel-single-release",
                population_scope_id=scope.scope_id,
                threat_id=threat.threat_id,
                registered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                state_ids=("out", "in"),
                releases=(MultinomialSamplingPlanRelease(
                    release_id=release.release_id,
                    observation_ids=("response-0", "response-1"),
                ),),
                minimum_trials_per_state=100,
                selection_scope="all states and observations for the single release",
                audit_sample_definition="pre-registered IID state-conditioned audit draws",
                binding_context=binding_context,
            )
            plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
            counts = MultinomialCountsFile(
                count_file_id="finite-channel-counts",
                sampling_plan_id=plan.plan_id,
                sampling_plan_sha256=sha256_file(plan_path),
                portfolio_id=plan.portfolio_id,
                population_scope_id=scope.scope_id,
                threat_id=threat.threat_id,
                family_id=plan.family_id,
                sampling_started_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                sampling_ended_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
                audit_sample_sha256="1" * 64,
                sampling_protocol="the registered IID state-conditioned protocol",
                state_ids=plan.state_ids,
                releases=(MultinomialReleaseCounts(
                    release_id=release.release_id,
                    observation_ids=("response-0", "response-1"),
                    state_rows=(
                        MultinomialStateCounts(state_id="out", counts=(500, 500)),
                        MultinomialStateCounts(state_id="in", counts=(500, 500)),
                    ),
                ),),
                binding_context=binding_context,
            )
            counts_path.write_text(
                counts.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            budget = AssuranceErrorBudget(
                budget_id="finite-channel-budget",
                authority="independent assurance authority",
                committed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                period_start=date(2026, 1, 1),
                period_end=date(2026, 12, 31),
                total_alpha=0.05,
                allocations=(ErrorBudgetAllocation(
                    allocation_id="finite-channel-allocation",
                    generation_id="finite-channel-generation",
                    family_id=plan.family_id,
                    portfolio_id=plan.portfolio_id,
                    population_scope_id=scope.scope_id,
                    threat_id=threat.threat_id,
                    sampling_plan_sha256=sha256_file(plan_path),
                    alpha=0.05,
                    binding_context=binding_context,
                ),),
            )
            budget_path.write_text(
                budget.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            prior = FiniteStatePriorEvidence(
                threat_id=threat.threat_id,
                population_scope_id=scope.scope_id,
                population_scope_sha256=scope_sha256,
                decision_game_sha256=game_sha256,
                state_ids=plan.state_ids,
                prior=(
                    RationalProbability(numerator=1, denominator=2),
                    RationalProbability(numerator=1, denominator=2),
                ),
                prior_definition="equal-prior randomized IN/OUT audit game",
                authority="independent assurance authority",
            )
            prior_path.write_text(
                prior.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            mechanism_claims = (
                "coupling:conditional_independence",
                f"artifact:{release.artifact_sha256}",
                f"interface:{interface_sha256}",
                f"complete-transcript:{release.release_id}",
            )
            mechanism_path.write_text(
                json.dumps({"claims": mechanism_claims}) + "\n",
                encoding="utf-8",
            )
            evidence_request = MultinomialEvidenceRequest(
                generation_id="finite-channel-generation",
                allocation_id="finite-channel-allocation",
                sampling_plan_reference=SourceFileReference(
                    source_id="finite-channel-plan-source",
                    source_path=plan_path.name,
                    source_sha256=sha256_file(plan_path),
                ),
                counts_reference=SourceFileReference(
                    source_id="finite-channel-counts-source",
                    source_path=counts_path.name,
                    source_sha256=sha256_file(counts_path),
                ),
                budget_reference=SourceFileReference(
                    source_id="finite-channel-budget-source",
                    source_path=budget_path.name,
                    source_sha256=sha256_file(budget_path),
                ),
                family_pre_registered=True,
                all_cells_reported=True,
                selection_process_covered=True,
                assurance_ledger_complete=True,
                selection_scope=plan.selection_scope,
            )
            evidence = generate_simultaneous_multinomial_evidence(
                evidence_request,
                base_dir,
            )
            evidence_path.write_text(
                evidence.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            specification = IncompletePortfolioSpecification(
                portfolio_id=plan.portfolio_id,
                population_scope_id=scope.scope_id,
                population_scope_sha256=scope_sha256,
                threat_id=threat.threat_id,
                decision_game_sha256=game_sha256,
                prior=(0.5, 0.5),
                rational_prior=prior.prior,
                decision_problem=exact_guess_problem(
                    plan.state_ids,
                    problem_id="equal-prior-membership",
                ),
                coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
                prior_evidence=EvidenceReference(
                    evidence_id="finite-channel-prior",
                    source_path=prior_path.name,
                    source_sha256=sha256_file(prior_path),
                    supports=(
                        "prior",
                        f"decision-game:{game_sha256}",
                        "finite-prior:"
                        f"{finite_prior_contract_sha256(plan.state_ids, prior.prior)}",
                    ),
                ),
                mechanism_assumptions=("one complete finite release transcript",),
                mechanism_evidence=(EvidenceReference(
                    evidence_id="finite-channel-mechanism",
                    source_path=mechanism_path.name,
                    source_sha256=sha256_file(mechanism_path),
                    supports=mechanism_claims,
                ),),
            )
            problem = compile_multinomial_portfolio_problem(
                evidence,
                specification,
                evidence_source_path=evidence_path.name,
                evidence_source_sha256=sha256_file(evidence_path),
            )
            entry = solve_analytic_portfolio(problem, method="envelope")
            state_trials = tuple(row.trials for row in evidence.rows)
            value = FiniteChannelCeilingInput(
                threat_id=threat.threat_id,
                population_scope_id=scope.scope_id,
                analytic_evidence=entry,
                observed_interface_sha256=interface_sha256,
                observed_artifact_sha256=release.artifact_sha256,
                interface_observation_definition="complete finite response transcript",
                release_enforced_finite_alphabet=True,
                complete_interface_coverage=True,
                recipient_realizable=True,
                bounded_transcript_complete=True,
                state_trials=state_trials,
                evidence_context=EvidenceContext(
                    release_id=release.release_id,
                    release_contract_sha256=sha256_bytes(canonical_json_bytes(release)),
                    policy_sha256=policy_sha256,
                    artifact_sha256=release.artifact_sha256,
                    interface_sha256=interface_sha256,
                    population_scope_id=scope.scope_id,
                    population_scope_sha256=scope_sha256,
                    decision_game_sha256=game_sha256,
                    observed_at=datetime.now(timezone.utc),
                ),
                provenance=AnalyzerProvenance(
                    tool="finite-channel-test-worker",
                    tool_version=service.descriptor.service_version,
                    producer={
                        "service_id": service.descriptor.service_id,
                        "service_version": service.descriptor.service_version,
                        "implementation_sha256": (
                            service.descriptor.implementation_sha256
                        ),
                        "configuration_sha256": sha256_file(config_path),
                    },
                    configuration_path=config_path.name,
                    source_path=input_path.name,
                    source_sha256="0" * 64,
                    bound_fields=(
                        "analyzer",
                        "schema_version",
                        "threat_id",
                        "population_scope_id",
                        "analytic_evidence",
                        "observed_interface_sha256",
                        "observed_artifact_sha256",
                        "interface_observation_definition",
                        "release_enforced_finite_alphabet",
                        "complete_interface_coverage",
                        "recipient_realizable",
                        "bounded_transcript_complete",
                        "state_trials",
                        "evidence_context",
                    ),
                ),
            )

            input_path.write_text(
                json.dumps(
                    value.model_dump(mode="json", exclude={"provenance"}),
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            value = value.model_copy(update={
                "provenance": value.provenance.model_copy(update={
                    "source_sha256": sha256_file(input_path),
                }),
            })

            self.assertEqual(state_trials, (1_000, 1_000))
            AssuranceEngine._verify_finite_channel_sources(value, base_dir)

            governed_request = AssessmentRequest(
                policy=PolicyReference(
                    policy_id=policy.policy_id,
                    policy_version=policy.policy_version,
                    policy_path=policy_path.name,
                    policy_sha256=policy_sha256,
                ),
                release=release,
                population_scopes=(scope,),
                threats=(threat,),
                analyzer_inputs=(value,),
            )
            report = AssuranceEngine(service_registry=AnalyzerServiceRegistry((service,))).assess(
                governed_request,
                base_dir,
            )
            self.assertEqual(report.overall_verdict, Verdict.CLEAR)
            self.assertEqual(report.decisions[0].verdict, Verdict.CLEAR)
            self.assertEqual(report.decisions[0].resolution.release_gate, "clear")

            wrong_context = value.evidence_context.model_copy(
                update={"policy_sha256": "f" * 64}
            )
            with self.assertRaisesRegex(ValueError, "bound to another release"):
                AssuranceEngine._verify_finite_channel_sources(
                    value.model_copy(update={"evidence_context": wrong_context}),
                    base_dir,
                )

            wrong_trials = value.model_copy(update={"state_trials": (999, 1_000)})
            with self.assertRaisesRegex(ValueError, "state_trials do not replay"):
                AssuranceEngine._verify_finite_channel_sources(wrong_trials, base_dir)

            counts_path.write_text(
                counts_path.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
                AssuranceEngine._verify_finite_channel_sources(value, base_dir)

    def test_complete_channel_emits_directional_floor_and_ceiling(self) -> None:
        release, threat, _, value = _fixture(
            ((0.45, 0.45), (0.45, 0.45)),
            ((0.55, 0.55), (0.55, 0.55)),
        )

        records = FiniteChannelCeilingAnalyzer().analyze(release, threat, value)

        self.assertEqual(
            tuple(record.evidence_class for record in records),
            (EvidenceClass.FLOOR, EvidenceClass.CEILING),
        )
        self.assertAlmostEqual(records[0].lower, 0.45)
        self.assertAlmostEqual(records[1].upper, 0.55)
        self.assertTrue(records[0].can_block)
        self.assertTrue(records[1].can_clear)
        self.assertEqual(records[1].details["resolution"], "ceiling_below_tolerance")
        self.assertEqual(
            records[1].details["reported_ceiling_fraction"],
            {"numerator": 11, "denominator": 20},
        )

    def test_exact_rational_ceiling_equal_to_tolerance_clears(self) -> None:
        release, threat, scope, value = _fixture(
            ((0.4, 0.4), (0.4, 0.4)),
            ((0.6, 0.6), (0.6, 0.6)),
            tolerance=0.6,
        )

        records = FiniteChannelCeilingAnalyzer().analyze(release, threat, value)
        decision = decide_threat(
            threat,
            scope,
            release,
            records,
            value.evidence_context.policy_sha256,
            AttackBatteryStatus(
                mode=CeilingAttackBatteryMode.WAIVED,
                satisfied=True,
                waiver_reason="unit-test policy waiver",
            ),
        )

        self.assertEqual(records[1].exact_upper.as_fraction(), Fraction(3, 5))
        self.assertGreater(records[1].upper, threat.tolerance)
        self.assertEqual(decision.verdict, Verdict.CLEAR)
        self.assertEqual(decision.upper_bound_fraction.as_fraction(), Fraction(3, 5))

    def test_same_analyzer_covers_xgboost_cnn_and_bounded_llm_families(self) -> None:
        for model_family in ("xgboost", "cnn", "llm"):
            with self.subTest(model_family=model_family):
                release, threat, _, value = _fixture(
                    ((0.45, 0.45), (0.45, 0.45)),
                    ((0.55, 0.55), (0.55, 0.55)),
                    model_family=model_family,
                )
                records = FiniteChannelCeilingAnalyzer().analyze(
                    release,
                    threat,
                    value,
                )
                self.assertEqual(len(records), 2)
                self.assertTrue(records[1].details["model_family_neutral"])

    def test_interval_decides_clear_block_or_actionable_hold(self) -> None:
        cases = (
            (
                ((0.45, 0.45), (0.45, 0.45)),
                ((0.55, 0.55), (0.55, 0.55)),
                Verdict.CLEAR,
                "ceiling_below_tolerance",
            ),
            (
                ((0.9, 0.0), (0.0, 0.9)),
                ((1.0, 0.1), (0.1, 1.0)),
                Verdict.BLOCK,
                "floor_above_tolerance",
            ),
            (
                ((0.2, 0.2), (0.2, 0.2)),
                ((0.8, 0.8), (0.8, 0.8)),
                Verdict.INCONCLUSIVE,
                "recollect_more_state_conditioned_samples",
            ),
        )
        for lower, upper, expected_verdict, resolution in cases:
            with self.subTest(verdict=expected_verdict):
                release, threat, scope, value = _fixture(lower, upper)
                records = FiniteChannelCeilingAnalyzer().analyze(
                    release,
                    threat,
                    value,
                )
                decision = decide_threat(
                    threat,
                    scope,
                    release,
                    records,
                    value.evidence_context.policy_sha256,
                    AttackBatteryStatus(
                        mode=CeilingAttackBatteryMode.WAIVED,
                        satisfied=True,
                        waiver_reason="unit-test policy waiver",
                    ),
                )
                self.assertEqual(decision.verdict, expected_verdict)
                self.assertEqual(records[-1].details["resolution"], resolution)
                if expected_verdict is Verdict.INCONCLUSIVE:
                    self.assertEqual(decision.resolution.release_gate, "hold")
                    self.assertEqual(decision.resolution.code, resolution)
                    self.assertTrue(decision.resolution.actions)
                    self.assertFalse(
                        decision.resolution.planning_estimate_is_decision_evidence
                    )
                    self.assertTrue(any(
                        "required next action: recollect_more_state_conditioned_samples"
                        in reason
                        for reason in decision.reasons
                    ))
                    self.assertTrue(any(
                        "planning estimate (not decision evidence)" in reason
                        for reason in decision.reasons
                    ))

    def test_unenforced_or_incomplete_interface_is_redesign_screen(self) -> None:
        for flag in (
            "release_enforced_finite_alphabet",
            "complete_interface_coverage",
            "recipient_realizable",
            "bounded_transcript_complete",
        ):
            with self.subTest(flag=flag):
                release, threat, _, value = _fixture(
                    ((0.45, 0.45), (0.45, 0.45)),
                    ((0.55, 0.55), (0.55, 0.55)),
                    flags={flag: False},
                )
                record = FiniteChannelCeilingAnalyzer().analyze(
                    release,
                    threat,
                    value,
                )[0]
                self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
                self.assertFalse(record.can_clear)
                self.assertFalse(record.can_block)
                self.assertEqual(record.details["resolution"], "redesign_interface")

    def test_wrong_interface_binding_fails_closed_with_repair_action(self) -> None:
        release, threat, _, value = _fixture(
            ((0.45, 0.45), (0.45, 0.45)),
            ((0.55, 0.55), (0.55, 0.55)),
        )
        wrong_context = value.evidence_context.model_copy(
            update={"interface_sha256": "f" * 64}
        )
        changed = value.model_copy(update={
            "observed_interface_sha256": "f" * 64,
            "evidence_context": wrong_context,
        })

        record = FiniteChannelCeilingAnalyzer().analyze(
            release,
            threat,
            changed,
        )[0]

        self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
        self.assertEqual(
            record.details["resolution"],
            "repair_release_bindings_and_replay",
        )

    def test_unvalidated_statistical_endpoints_require_evidence_repair(self) -> None:
        release, threat, _, value = _fixture(
            ((0.45, 0.45), (0.45, 0.45)),
            ((0.55, 0.55), (0.55, 0.55)),
        )
        problem = value.analytic_evidence.problem
        marginal = problem.releases[0]
        changed_reference = marginal.evidence.model_copy(update={
            "supports": tuple(
                claim
                for claim in marginal.evidence.supports
                if claim != "confidence-endpoints:outward-validated"
            ),
        })
        changed_problem = problem.model_copy(update={
            "releases": (
                marginal.model_copy(update={"evidence": changed_reference}),
            ),
        })
        value = value.model_copy(update={
            "analytic_evidence": solve_analytic_portfolio(
                changed_problem,
                method="envelope",
            ),
        })

        record = FiniteChannelCeilingAnalyzer().analyze(
            release,
            threat,
            value,
        )[0]

        self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
        self.assertEqual(
            record.details["resolution"],
            "repair_sampling_evidence_and_replay",
        )

    def test_self_declared_deterministic_channel_cannot_clear(self) -> None:
        release, threat, scope, value = _fixture(
            ((0.5, 0.5), (0.5, 0.5)),
            ((0.5, 0.5), (0.5, 0.5)),
            coverage=StatisticalCoverage.DETERMINISTIC,
        )

        record = FiniteChannelCeilingAnalyzer().analyze(
            release,
            threat,
            value,
        )[0]

        self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(record.can_clear)
        self.assertFalse(record.can_block)
        self.assertEqual(
            record.details["resolution"],
            "collect_simultaneous_channel_evidence",
        )
        decision = decide_threat(
            threat,
            scope,
            release,
            (record,),
            value.evidence_context.policy_sha256,
            AttackBatteryStatus(
                mode=CeilingAttackBatteryMode.WAIVED,
                satisfied=True,
                waiver_reason="unit-test policy waiver",
            ),
        )
        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(
            decision.resolution.code,
            "collect_simultaneous_channel_evidence",
        )
        self.assertEqual(decision.resolution.release_gate, "hold")
        self.assertEqual(
            decision.resolution.actions,
            (
                "collect preregistered state-conditioned counts and compile a "
                "simultaneous confidence family",
            ),
        )

    def test_equal_prior_membership_rejects_nonuniform_prior(self) -> None:
        release, threat, _, value = _fixture(
            ((0.45, 0.45), (0.45, 0.45)),
            ((0.55, 0.55), (0.55, 0.55)),
            prior=(0.75, 0.25),
        )

        with self.assertRaisesRegex(AnalyzerError, "exactly two states"):
            FiniteChannelCeilingAnalyzer().analyze(release, threat, value)

    def test_missing_policy_frozen_game_is_actionable_screen(self) -> None:
        release, threat, _, value = _fixture(
            ((0.45, 0.45), (0.45, 0.45)),
            ((0.55, 0.55), (0.55, 0.55)),
        )

        record = FiniteChannelCeilingAnalyzer().analyze(
            release,
            threat.model_copy(update={"finite_game": None}),
            value,
        )[0]

        self.assertEqual(record.evidence_class, EvidenceClass.SCREEN)
        self.assertEqual(
            record.details["resolution"],
            "register_policy_bound_finite_game",
        )

    def test_engine_rejects_request_game_not_frozen_by_policy(self) -> None:
        request = AssessmentRequest.model_validate_json(
            (ROOT / "examples" / "request.json").read_text(encoding="utf-8")
        )
        policy = PolicyBundle.model_validate_json(
            (ROOT / "examples" / request.policy.policy_path).read_text(encoding="utf-8")
        )
        membership = next(
            threat
            for threat in request.threats
            if threat.decision_metric == "equal_prior_membership_success"
        )
        _, frozen_membership, _, _ = _fixture(
            ((0.45, 0.45), (0.45, 0.45)),
            ((0.55, 0.55), (0.55, 0.55)),
        )
        changed = request.model_copy(update={
            "threats": tuple(
                membership.model_copy(update={"finite_game": frozen_membership.finite_game})
                if threat.threat_id == membership.threat_id
                else threat
                for threat in request.threats
            ),
        })

        with self.assertRaisesRegex(ValueError, "changes policy field finite_game"):
            AssuranceEngine._validate_policy(changed, policy)


if __name__ == "__main__":
    unittest.main()
