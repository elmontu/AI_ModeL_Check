from __future__ import annotations

import json
import math
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from model_release_assurance.decision_theory import exact_guess_problem
from model_release_assurance.incomplete_portfolio import (
    CouplingModel,
    EvidenceReference,
    StatisticalCoverage,
    verify_portfolio_problem_evidence,
)
from model_release_assurance.integrity import sha256_file
from model_release_assurance.errors import IntegrityError
from model_release_assurance.models import EvidenceBindingContext
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
    SimultaneousMultinomialEvidence,
    SourceFileReference,
    compile_multinomial_portfolio_problem,
    exact_two_sided_binomial_interval,
    generate_simultaneous_multinomial_evidence,
    verify_problem_against_multinomial_evidence,
    verify_simultaneous_multinomial_evidence,
)


class PortfolioStatisticsTests(unittest.TestCase):
    @staticmethod
    def exact_binomial_tail(
        successes: int,
        trials: int,
        probability: float,
        side: str,
    ) -> Fraction:
        value = Fraction(Decimal(str(probability)))
        complement = 1 - value
        indices = (
            range(successes, trials + 1)
            if side == "lower"
            else range(successes + 1)
        )
        return sum(
            (
                Fraction(math.comb(trials, index))
                * value**index
                * complement ** (trials - index)
                for index in indices
            ),
            Fraction(0),
        )

    def test_scipy_exact_interval_matches_reference_implementation(self) -> None:
        from model_release_assurance.analyzers.attack import (
            clopper_pearson_lower,
            clopper_pearson_upper,
        )

        for successes, trials in ((0, 10), (3, 10), (50, 100), (10, 10)):
            lower, upper = exact_two_sided_binomial_interval(successes, trials, 0.01)
            self.assertAlmostEqual(
                lower,
                clopper_pearson_lower(successes, trials, 0.99),
                places=10,
            )
            self.assertAlmostEqual(
                upper,
                clopper_pearson_upper(successes, trials, 0.99),
                places=10,
            )

    def test_generic_clopper_pearson_endpoints_are_outward_and_ulp_tight(self) -> None:
        from model_release_assurance.analyzers.attack import (
            clopper_pearson_lower,
            clopper_pearson_upper,
        )

        alpha = Fraction(1, 20)
        lower = clopper_pearson_lower(2, 3, 0.95)
        upper = clopper_pearson_upper(0, 2, 0.95)

        self.assertLessEqual(
            self.exact_binomial_tail(2, 3, lower, "lower"),
            alpha,
        )
        self.assertGreater(
            self.exact_binomial_tail(
                2, 3, math.nextafter(lower, 1.0), "lower"
            ),
            alpha,
        )
        self.assertLessEqual(
            self.exact_binomial_tail(0, 2, upper, "upper"),
            alpha,
        )
        self.assertGreater(
            self.exact_binomial_tail(
                0, 2, math.nextafter(upper, 0.0), "upper"
            ),
            alpha,
        )

    def test_generic_clopper_pearson_fails_closed_above_work_caps(self) -> None:
        from model_release_assurance.analyzers.attack import clopper_pearson_lower

        with self.assertRaisesRegex(ValueError, "directed-tail work cap"):
            clopper_pearson_lower(25_001, 50_002, 0.95)
        with self.assertRaisesRegex(ValueError, "trials exceed the hard limit"):
            clopper_pearson_lower(1, 10_000_001, 0.95)

    def test_generic_bonferroni_uses_canonical_decimal_alpha(self) -> None:
        from model_release_assurance.analyzers.attack import (
            bonferroni_per_bound_confidence,
        )

        family_confidence = 0.95
        simultaneous_bound_count = 3
        per_bound_confidence = bonferroni_per_bound_confidence(
            family_confidence,
            simultaneous_bound_count,
        )
        family_alpha = Fraction(1) - Fraction(
            Decimal(str(family_confidence))
        )
        used_alpha = Fraction(1) - Fraction(
            Decimal(str(per_bound_confidence))
        )

        self.assertLessEqual(
            simultaneous_bound_count * used_alpha,
            family_alpha,
        )
        inward = math.nextafter(per_bound_confidence, 0.0)
        inward_alpha = Fraction(1) - Fraction(Decimal(str(inward)))
        self.assertGreater(
            simultaneous_bound_count * inward_alpha,
            family_alpha,
        )

    def test_serialized_endpoints_satisfy_exact_tail_and_are_ulp_tight(self) -> None:
        successes = 7
        trials = 25
        alpha = 0.01
        alpha_exact = Fraction(Decimal(str(alpha)))

        lower, upper = exact_two_sided_binomial_interval(successes, trials, alpha)

        self.assertLessEqual(
            self.exact_binomial_tail(successes, trials, lower, "lower"),
            alpha_exact,
        )
        self.assertLessEqual(
            self.exact_binomial_tail(successes, trials, upper, "upper"),
            alpha_exact,
        )
        self.assertGreater(
            self.exact_binomial_tail(
                successes, trials, math.nextafter(lower, 1.0), "lower"
            ),
            alpha_exact,
        )
        self.assertGreater(
            self.exact_binomial_tail(
                successes, trials, math.nextafter(upper, 0.0), "upper"
            ),
            alpha_exact,
        )

    def test_canonical_decimal_counterexamples_move_outward(self) -> None:
        alpha = 0.00625
        alpha_exact = Fraction(Decimal(str(alpha)))
        inward_lower = 0.003129898131155706
        inward_upper = 0.9670001667943254

        self.assertGreater(
            self.exact_binomial_tail(1, 2, inward_lower, "lower"),
            alpha_exact,
        )
        self.assertGreater(
            self.exact_binomial_tail(2, 4, inward_upper, "upper"),
            alpha_exact,
        )

        safe_lower, _ = exact_two_sided_binomial_interval(1, 2, alpha)
        _, safe_upper = exact_two_sided_binomial_interval(2, 4, alpha)
        self.assertLess(safe_lower, inward_lower)
        self.assertGreater(safe_upper, inward_upper)
        self.assertLessEqual(
            self.exact_binomial_tail(1, 2, safe_lower, "lower"),
            alpha_exact,
        )
        self.assertLessEqual(
            self.exact_binomial_tail(2, 4, safe_upper, "upper"),
            alpha_exact,
        )

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_dir.name)
        self.counts_path = self.temp / "counts.json"
        self.plan_path = self.temp / "plan.json"
        self.budget_path = self.temp / "budget.json"
        self.prior_path = self.temp / "prior.json"
        self.mechanism_path = self.temp / "mechanism.json"
        self.plan = MultinomialSamplingPlan(
            plan_id="sampling-plan-one",
            family_id="assurance-family-one",
            portfolio_id="statistical-portfolio",
            population_scope_id="population-one",
            threat_id="guess-secret",
            registered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            state_ids=("0", "1"),
            releases=(
                MultinomialSamplingPlanRelease(
                    release_id="release-one",
                    observation_ids=("left", "right"),
                ),
                MultinomialSamplingPlanRelease(
                    release_id="release-two",
                    observation_ids=("low", "high"),
                ),
            ),
            minimum_trials_per_state=100,
            selection_scope="both releases, states, observations, and selected configuration",
            audit_sample_definition="fixed pre-registered stratified audit sample",
        )
        self.plan_path.write_text(self.plan.model_dump_json(indent=2) + "\n")
        self.counts = MultinomialCountsFile(
            count_file_id="counts-family-one",
            sampling_plan_id=self.plan.plan_id,
            sampling_plan_sha256=sha256_file(self.plan_path),
            portfolio_id="statistical-portfolio",
            population_scope_id="population-one",
            threat_id="guess-secret",
            family_id="assurance-family-one",
            sampling_started_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            sampling_ended_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
            audit_sample_sha256="1" * 64,
            sampling_protocol="pre-registered IID audit queries stratified by protected state",
            state_ids=("0", "1"),
            releases=(
                MultinomialReleaseCounts(
                    release_id="release-one",
                    observation_ids=("left", "right"),
                    state_rows=(
                        MultinomialStateCounts(state_id="0", counts=(80, 20)),
                        MultinomialStateCounts(state_id="1", counts=(30, 70)),
                    ),
                ),
                MultinomialReleaseCounts(
                    release_id="release-two",
                    observation_ids=("low", "high"),
                    state_rows=(
                        MultinomialStateCounts(state_id="0", counts=(60, 40)),
                        MultinomialStateCounts(state_id="1", counts=(45, 55)),
                    ),
                ),
            ),
        )
        self.counts_path.write_text(self.counts.model_dump_json(indent=2) + "\n")
        self.budget = AssuranceErrorBudget(
            budget_id="whole-assurance-2026",
            authority="independent central assurance authority",
            committed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            total_alpha=0.05,
            allocations=(
                ErrorBudgetAllocation(
                    allocation_id="portfolio-allocation",
                    generation_id="generation-one",
                    family_id=self.counts.family_id,
                    portfolio_id=self.counts.portfolio_id,
                    population_scope_id=self.counts.population_scope_id,
                    threat_id=self.counts.threat_id,
                    sampling_plan_sha256=sha256_file(self.plan_path),
                    alpha=0.02,
                ),
                ErrorBudgetAllocation(
                    allocation_id="reserved-allocation",
                    generation_id="generation-two",
                    family_id="assurance-family-two",
                    portfolio_id="another-portfolio",
                    population_scope_id="another-population",
                    threat_id="another-threat",
                    sampling_plan_sha256="2" * 64,
                    alpha=0.03,
                ),
            ),
        )
        self.budget_path.write_text(self.budget.model_dump_json(indent=2) + "\n")
        self.prior_path.write_text(json.dumps({"prior": [0.5, 0.5]}) + "\n")
        self.mechanism_path.write_text(json.dumps({"coupling": "arbitrary"}) + "\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def request(self, **changes) -> MultinomialEvidenceRequest:
        values = dict(
            generation_id="generation-one",
            allocation_id="portfolio-allocation",
            sampling_plan_reference=SourceFileReference(
                source_id="sampling-plan",
                source_path=self.plan_path.name,
                source_sha256=sha256_file(self.plan_path),
            ),
            counts_reference=SourceFileReference(
                source_id="raw-counts",
                source_path=self.counts_path.name,
                source_sha256=sha256_file(self.counts_path),
            ),
            budget_reference=SourceFileReference(
                source_id="assurance-ledger",
                source_path=self.budget_path.name,
                source_sha256=sha256_file(self.budget_path),
            ),
            family_pre_registered=True,
            all_cells_reported=True,
            selection_process_covered=True,
            assurance_ledger_complete=True,
            selection_scope="both releases, states, observations, and selected configuration",
        )
        values.update(changes)
        return MultinomialEvidenceRequest(**values)

    def specification(self) -> IncompletePortfolioSpecification:
        return IncompletePortfolioSpecification(
            portfolio_id=self.counts.portfolio_id,
            population_scope_id=self.counts.population_scope_id,
            population_scope_sha256="3" * 64,
            threat_id=self.counts.threat_id,
            decision_game_sha256="4" * 64,
            prior=(0.5, 0.5),
            decision_problem=exact_guess_problem(self.counts.state_ids, "guess-secret"),
            coupling_model=CouplingModel.ARBITRARY,
            prior_evidence=EvidenceReference(
                evidence_id="prior-evidence",
                source_path=self.prior_path.name,
                source_sha256=sha256_file(self.prior_path),
                supports=("prior",),
            ),
            mechanism_assumptions=("no dependence restriction beyond observed marginals",),
            mechanism_evidence=(EvidenceReference(
                evidence_id="mechanism-evidence",
                source_path=self.mechanism_path.name,
                source_sha256=sha256_file(self.mechanism_path),
                supports=("coupling:arbitrary",),
            ),),
        )

    def test_generates_and_replays_exact_simultaneous_family(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)
        verification = verify_simultaneous_multinomial_evidence(evidence, self.temp)

        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(verification.endpoint_validation, "validated")
        self.assertEqual(verification.endpoints_checked, 16)
        self.assertTrue(evidence.selection_valid)
        self.assertIs(evidence.coverage, StatisticalCoverage.SIMULTANEOUS)
        self.assertEqual(evidence.simultaneous_cell_count, 8)
        self.assertAlmostEqual(evidence.per_tail_alpha, 0.02 / 16.0)
        used_alpha = Fraction(
            evidence.per_tail_alpha_numerator,
            evidence.per_tail_alpha_denominator,
        )
        naive_float_alpha = Fraction(Decimal(str(0.05 / 14.0)))
        self.assertGreater(naive_float_alpha, Fraction("0.05") / 14)
        self.assertEqual(
            used_alpha,
            Fraction(Decimal(str(evidence.per_tail_alpha))),
        )
        self.assertLessEqual(
            2 * evidence.simultaneous_cell_count * used_alpha,
            Fraction(str(evidence.family_alpha)),
        )
        self.assertLessEqual(
            Fraction(Decimal(str(evidence.family_coverage_confidence))),
            1 - Fraction(Decimal(str(evidence.family_alpha))),
        )
        self.assertLessEqual(
            Fraction(Decimal(str(evidence.assurance_wide_confidence))),
            1 - Fraction(Decimal(str(evidence.assurance_wide_alpha))),
        )
        self.assertAlmostEqual(evidence.family_coverage_confidence, 0.98)
        self.assertAlmostEqual(evidence.assurance_wide_confidence, 0.95)
        for row in evidence.rows:
            for count, lower, upper in zip(row.counts, row.lower, row.upper, strict=True):
                estimate = count / row.trials
                self.assertLessEqual(lower, estimate)
                self.assertGreaterEqual(upper, estimate)

    def test_selection_failure_downgrades_to_pointwise(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(
            self.request(selection_process_covered=False),
            self.temp,
        )
        self.assertFalse(evidence.selection_valid)
        self.assertIs(evidence.coverage, StatisticalCoverage.POINTWISE)
        self.assertIn("selection process", " ".join(evidence.limitations))

    def test_budget_must_be_precommitted_complete_and_within_total(self) -> None:
        raw = self.budget.model_dump(mode="json")
        raw["committed_at"] = "2026-03-01T00:00:00Z"
        late = AssuranceErrorBudget.model_validate(raw)
        self.budget_path.write_text(late.model_dump_json(indent=2) + "\n")
        request = self.request()
        with self.assertRaisesRegex(ValueError, "before multinomial sampling"):
            generate_simultaneous_multinomial_evidence(request, self.temp)

        raw = self.budget.model_dump(mode="json")
        raw["allocations"][1]["alpha"] = 0.031
        with self.assertRaisesRegex(ValidationError, "exceeds ledger total"):
            AssuranceErrorBudget.model_validate(raw)

        raw = self.budget.model_dump(mode="json")
        raw["allocations"][0]["alpha"] = 0.0250000000000003
        raw["allocations"][1]["alpha"] = 0.0250000000000003
        with self.assertRaisesRegex(ValidationError, "exceeds ledger total"):
            AssuranceErrorBudget.model_validate(raw)

    def test_post_hoc_family_or_sample_size_change_is_rejected(self) -> None:
        raw = self.counts.model_dump(mode="json")
        raw["releases"][0]["observation_ids"] = ["left", "changed"]
        changed_family = MultinomialCountsFile.model_validate(raw)
        self.counts_path.write_text(changed_family.model_dump_json(indent=2) + "\n")
        request = self.request()
        with self.assertRaisesRegex(ValueError, "registered release/output family"):
            generate_simultaneous_multinomial_evidence(request, self.temp)

        self.counts_path.write_text(self.counts.model_dump_json(indent=2) + "\n")
        raw = self.counts.model_dump(mode="json")
        raw["releases"][0]["state_rows"][0]["counts"] = [40, 40]
        too_small = MultinomialCountsFile.model_validate(raw)
        self.counts_path.write_text(too_small.model_dump_json(indent=2) + "\n")
        request = self.request()
        with self.assertRaisesRegex(ValueError, "sample-size floor"):
            generate_simultaneous_multinomial_evidence(request, self.temp)

    def test_release_binding_context_is_atomic_and_cannot_be_relabelled(self) -> None:
        context = EvidenceBindingContext(
            release_id="release-one",
            release_contract_sha256="4" * 64,
            policy_sha256="5" * 64,
            artifact_sha256="6" * 64,
            interface_sha256="7" * 64,
            population_scope_id=self.plan.population_scope_id,
            population_scope_sha256="8" * 64,
            decision_game_sha256="9" * 64,
        )
        plan = self.plan.model_copy(update={"binding_context": context})
        self.plan_path.write_text(plan.model_dump_json(indent=2) + "\n")
        counts = self.counts.model_copy(update={
            "sampling_plan_sha256": sha256_file(self.plan_path),
            "binding_context": context,
        })
        self.counts_path.write_text(counts.model_dump_json(indent=2) + "\n")
        allocations = list(self.budget.allocations)
        allocations[0] = allocations[0].model_copy(update={
            "sampling_plan_sha256": sha256_file(self.plan_path),
            "binding_context": context,
        })
        budget = self.budget.model_copy(update={"allocations": tuple(allocations)})
        self.budget_path.write_text(budget.model_dump_json(indent=2) + "\n")

        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)
        self.assertEqual(evidence.binding_context, context)

        relabelled = context.model_copy(update={"artifact_sha256": "a" * 64})
        changed_counts = counts.model_copy(update={"binding_context": relabelled})
        self.counts_path.write_text(changed_counts.model_dump_json(indent=2) + "\n")
        with self.assertRaisesRegex(ValueError, "change the release binding context"):
            generate_simultaneous_multinomial_evidence(self.request(), self.temp)

        self.counts_path.write_text(counts.model_dump_json(indent=2) + "\n")
        allocations[0] = allocations[0].model_copy(update={"binding_context": None})
        budget = budget.model_copy(update={"allocations": tuple(allocations)})
        self.budget_path.write_text(budget.model_dump_json(indent=2) + "\n")
        with self.assertRaisesRegex(ValueError, "must be present"):
            generate_simultaneous_multinomial_evidence(self.request(), self.temp)

    def test_tampered_counts_or_interval_fail_replay(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)
        row = evidence.rows[0]
        tampered = evidence.model_copy(update={
            "rows": (
                row.model_copy(update={"upper": (0.1, *row.upper[1:])}),
                *evidence.rows[1:],
            ),
        })
        verification = verify_simultaneous_multinomial_evidence(tampered, self.temp)
        self.assertFalse(verification.valid)
        self.assertIn("does not replay", verification.reasons[0])
        self.assertEqual(verification.endpoint_validation, "invalid")
        self.assertTrue(
            any("endpoint validation failed" in value for value in verification.reasons)
        )

        self.counts_path.write_text(self.counts_path.read_text() + " ")
        with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
            verify_simultaneous_multinomial_evidence(evidence, self.temp)

    def test_one_ulp_inward_endpoint_tamper_fails_mechanical_tail_check(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)
        row = evidence.rows[0]
        inward_lower = math.nextafter(row.lower[0], 1.0)
        tampered = evidence.model_copy(update={
            "rows": (
                row.model_copy(update={"lower": (inward_lower, *row.lower[1:])}),
                *evidence.rows[1:],
            ),
        })

        verification = verify_simultaneous_multinomial_evidence(tampered, self.temp)

        self.assertFalse(verification.valid)
        self.assertIn(verification.endpoint_validation, {"invalid", "unresolved"})
        self.assertTrue(
            any("lower endpoint validation" in value for value in verification.reasons),
            verification.reasons,
        )

    def test_per_tail_alpha_exact_binding_tamper_fails(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)
        tampered = evidence.model_copy(update={
            "per_tail_alpha_numerator": evidence.per_tail_alpha_numerator + 1,
        })

        verification = verify_simultaneous_multinomial_evidence(tampered, self.temp)

        self.assertFalse(verification.valid)
        self.assertEqual(verification.endpoint_validation, "invalid")
        self.assertTrue(
            any("exact numerator/denominator" in value for value in verification.reasons),
            verification.reasons,
        )

    def test_endpoint_proof_limit_fails_closed(self) -> None:
        with patch(
            "model_release_assurance.portfolio_statistics.MAX_DIRECTED_TAIL_TERMS",
            1,
        ):
            with self.assertRaisesRegex(ValueError, "exceeding the proof limit"):
                exact_two_sided_binomial_interval(50, 100, 0.01)

    def test_endpoint_proof_limit_during_replay_returns_unresolved(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)

        with patch(
            "model_release_assurance.portfolio_statistics.MAX_DIRECTED_TAIL_TERMS",
            1,
        ):
            verification = verify_simultaneous_multinomial_evidence(
                evidence,
                self.temp,
            )

        self.assertFalse(verification.valid)
        self.assertFalse(verification.selection_valid)
        self.assertEqual(verification.endpoint_validation, "unresolved")
        self.assertEqual(verification.endpoints_checked, 0)
        self.assertTrue(
            any("exceeding the proof limit" in reason for reason in verification.reasons),
            verification.reasons,
        )

    def test_huge_trial_rows_fail_as_controlled_validation_errors(self) -> None:
        with self.assertRaisesRegex(ValidationError, "hard trial limit"):
            MultinomialStateCounts(
                state_id="oversized-state",
                counts=(1, 10**400),
            )
        with self.assertRaisesRegex(ValueError, "hard limit"):
            exact_two_sided_binomial_interval(1, 10_000_001, 0.01)

    def test_aggregate_endpoint_work_limit_fails_before_generation(self) -> None:
        with patch(
            "model_release_assurance.portfolio_statistics."
            "MAX_SIMULTANEOUS_ENDPOINT_TERMS",
            10,
        ):
            with self.assertRaisesRegex(ValueError, "aggregate limit"):
                generate_simultaneous_multinomial_evidence(
                    self.request(),
                    self.temp,
                )

    def test_compile_binds_generated_intervals_and_full_evidence_chain(self) -> None:
        evidence = generate_simultaneous_multinomial_evidence(self.request(), self.temp)
        evidence_path = self.temp / "simultaneous-evidence.json"
        evidence_path.write_text(evidence.model_dump_json(indent=2) + "\n")
        problem = compile_multinomial_portfolio_problem(
            evidence,
            self.specification(),
            evidence_source_path=evidence_path.name,
            evidence_source_sha256=sha256_file(evidence_path),
        )

        verify_problem_against_multinomial_evidence(problem, evidence, evidence_path)
        verify_portfolio_problem_evidence(problem, self.temp)
        self.assertTrue(problem.selection_valid)
        self.assertAlmostEqual(problem.coverage_confidence, 0.95)
        self.assertEqual({value.release_id for value in problem.releases}, {
            "release-one", "release-two",
        })

        first = problem.releases[0]
        self.assertIn(
            "confidence-endpoints:outward-validated",
            first.evidence.supports,
        )
        altered = first.model_copy(update={
            "upper": ((0.01, first.upper[0][1]), *first.upper[1:]),
        })
        tampered_problem = problem.model_copy(update={
            "releases": (altered, *problem.releases[1:]),
        })
        with self.assertRaisesRegex(ValueError, "changes generated intervals"):
            verify_portfolio_problem_evidence(tampered_problem, self.temp)


if __name__ == "__main__":
    unittest.main()
