from __future__ import annotations

import unittest
import math
from fractions import Fraction

from pydantic import ValidationError

from model_release_assurance.decision_theory import decision_value, exact_guess_problem
from model_release_assurance.incomplete_portfolio import (
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    IncompletePortfolioProblem,
    JointEventBound,
    StatisticalCoverage,
    binary_uniform_diagonal_identified_bounds,
    build_envelope_certificate,
    certificate_can_clear,
    independent_product_experiment,
    solve_exact_portfolio,
    solve_analytic_portfolio,
    outward_rounded_fraction,
    parity_interaction_identified_bounds,
    verify_analytic_portfolio,
    verify_envelope_certificate,
    verify_exact_certificate,
)


def evidence(evidence_id: str, *supports: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        source_path="not-replayed-by-the-standalone-solver.json",
        source_sha256="b" * 64,
        supports=tuple(supports),
    )


def uniform_bit_release(
    release_id: str,
    coverage: StatisticalCoverage = StatisticalCoverage.DETERMINISTIC,
) -> ConditionalMarginalBounds:
    return ConditionalMarginalBounds(
        release_id=release_id,
        observation_ids=("0", "1"),
        lower=((0.5, 0.5), (0.5, 0.5)),
        upper=((0.5, 0.5), (0.5, 0.5)),
        evidence=evidence(
            f"{release_id}-evidence",
            f"marginal:{release_id}",
            f"coverage:{coverage.value}",
        ),
    )


def xor_problem(
    coupling_model: CouplingModel,
    *,
    events: tuple[JointEventBound, ...] = (),
    coverage: StatisticalCoverage = StatisticalCoverage.DETERMINISTIC,
) -> IncompletePortfolioProblem:
    return IncompletePortfolioProblem(
        portfolio_id="xor-portfolio",
        population_scope_id="test-population",
        population_scope_sha256="c" * 64,
        threat_id="guess-secret",
        decision_game_sha256="a" * 64,
        state_ids=("0", "1"),
        prior=(0.5, 0.5),
        releases=(
            uniform_bit_release("release-1", coverage),
            uniform_bit_release("release-2", coverage),
        ),
        decision_problem=exact_guess_problem(("0", "1"), "guess-secret"),
        coupling_model=coupling_model,
        joint_event_bounds=events,
        coverage=coverage,
        coverage_confidence=1.0 if coverage is StatisticalCoverage.DETERMINISTIC else 0.95,
        selection_scope="all portfolio cells and the selected release configuration",
        prior_evidence=EvidenceReference(
            evidence_id="prior-fixture",
            source_path="not-replayed-by-the-standalone-solver.json",
            source_sha256="d" * 64,
            supports=("prior", "prior:uniform-secret"),
        ),
        mechanism_assumptions=("the releases share the declared finite secret and population",),
        mechanism_evidence=(
            EvidenceReference(
                evidence_id="mechanism-fixture",
                source_path="not-replayed-by-the-standalone-solver.json",
                source_sha256="b" * 64,
                supports=(
                    f"coupling:{coupling_model.value}",
                    *(event.event_id for event in events),
                ),
            ),
        ),
    )


class IncompletePortfolioTests(unittest.TestCase):
    def test_parity_interaction_theorem_has_sharp_safe_to_unsafe_range(self) -> None:
        self.assertEqual(
            parity_interaction_identified_bounds(
                (Fraction(-1), Fraction(1)),
                (Fraction(-1), Fraction(1)),
            ),
            (Fraction(1, 2), Fraction(1)),
        )
        self.assertEqual(
            parity_interaction_identified_bounds(
                (Fraction(0), Fraction(0)),
                (Fraction(0), Fraction(0)),
            ),
            (Fraction(1, 2), Fraction(1, 2)),
        )

    def test_binary_diagonal_theorem_replays_partial_joint_lp(self) -> None:
        identified = binary_uniform_diagonal_identified_bounds(
            (Fraction(55, 100), Fraction(60, 100)),
            (Fraction(40, 100), Fraction(45, 100)),
        )
        self.assertEqual(identified, (Fraction(55, 100), Fraction(60, 100)))

        diagonal = (("0", "0"), ("1", "1"))
        problem = xor_problem(
            CouplingModel.LINEAR_MECHANISM,
            events=(
                JointEventBound(
                    event_id="diagonal-state-0",
                    state_id="0",
                    transcripts=diagonal,
                    lower=0.55,
                    upper=0.6,
                    justification="sharp-theorem cross-check",
                ),
                JointEventBound(
                    event_id="diagonal-state-1",
                    state_id="1",
                    transcripts=diagonal,
                    lower=0.4,
                    upper=0.45,
                    justification="sharp-theorem cross-check",
                ),
            ),
        )
        verification = verify_analytic_portfolio(solve_analytic_portfolio(problem, method="exact"))
        self.assertEqual(
            Fraction(
                verification.exact_upper_numerator,
                verification.exact_upper_denominator,
            ),
            identified[1],
        )

    def test_parity_interaction_theorem_rejects_non_exact_or_invalid_inputs(self) -> None:
        with self.assertRaises(TypeError):
            parity_interaction_identified_bounds((0.0, 1.0), (Fraction(0), Fraction(1)))
        with self.assertRaises(ValueError):
            parity_interaction_identified_bounds(
                (Fraction(1), Fraction(-1)),
                (Fraction(0), Fraction(0)),
            )
        with self.assertRaises(ValueError):
            binary_uniform_diagonal_identified_bounds(
                (Fraction(-1, 10), Fraction(1, 2)),
                (Fraction(0), Fraction(1)),
            )

    def test_exact_arbitrary_coupling_recovers_xor_disclosure(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        self.assertEqual(problem.schema_version, "1.0")
        certificate = solve_exact_portfolio(problem)
        verification = verify_exact_certificate(problem, certificate)

        self.assertTrue(verification.valid, verification.reasons)
        self.assertAlmostEqual(certificate.lower_bound, 1.0, places=7)
        self.assertAlmostEqual(certificate.upper_bound, 1.0, places=7)
        self.assertEqual(certificate.decoder_count, 16)

    def test_verifier_never_uses_a_tolerance_lowered_summary_for_clearance(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        certificate = solve_exact_portfolio(problem, numerical_tolerance=1e-8)
        tampered = certificate.model_copy(update={"upper_bound": 1.0 - 5e-9})

        verification = verify_exact_certificate(problem, tampered)

        self.assertTrue(verification.valid, verification.reasons)
        self.assertAlmostEqual(verification.upper_bound, 1.0, places=12)

    def test_linear_mechanism_constraints_can_make_ceiling_non_vacuous(self) -> None:
        transcripts = (("0", "0"), ("0", "1"), ("1", "0"), ("1", "1"))
        events = tuple(
            JointEventBound(
                event_id=f"cell-{state}-{left}-{right}",
                state_id=state,
                transcripts=((left, right),),
                lower=0.25,
                upper=0.25,
                justification="audited shared-randomness mechanism fixes this joint cell",
            )
            for state in ("0", "1")
            for left, right in transcripts
        )
        problem = xor_problem(CouplingModel.LINEAR_MECHANISM, events=events)
        certificate = solve_exact_portfolio(problem)
        verification = verify_exact_certificate(problem, certificate)

        self.assertTrue(verification.valid, verification.reasons)
        self.assertAlmostEqual(certificate.lower_bound, 0.5, places=7)
        self.assertAlmostEqual(certificate.upper_bound, 0.5, places=7)
        entry = solve_analytic_portfolio(problem, method="exact")
        self.assertEqual(
            [
                Fraction(cell.numerator, cell.denominator)
                for cell in entry.rational_upper_audit.feasible_joint_channel[0]
            ],
            [Fraction(1, 4)] * 4,
        )
        self.assertTrue(certificate_can_clear(
            verify_analytic_portfolio(entry), threshold=0.5, selection_valid=True
        ))

    def test_partial_joint_event_evidence_yields_sharp_middle_case(self) -> None:
        diagonal = (("0", "0"), ("1", "1"))
        problem = xor_problem(
            CouplingModel.LINEAR_MECHANISM,
            events=(
                JointEventBound(
                    event_id="diagonal-state-0",
                    state_id="0",
                    transcripts=diagonal,
                    lower=0.55,
                    upper=0.6,
                    justification="simultaneously covered partial joint-event interval",
                ),
                JointEventBound(
                    event_id="diagonal-state-1",
                    state_id="1",
                    transcripts=diagonal,
                    lower=0.4,
                    upper=0.45,
                    justification="simultaneously covered partial joint-event interval",
                ),
            ),
        )
        certificate = solve_exact_portfolio(problem)
        verification = verify_exact_certificate(problem, certificate)

        self.assertTrue(verification.valid, verification.reasons)
        self.assertAlmostEqual(certificate.lower_bound, 0.6, places=7)
        self.assertAlmostEqual(certificate.upper_bound, 0.6, places=7)
        entry = solve_analytic_portfolio(problem, method="exact")
        self.assertEqual(
            [
                Fraction(cell.numerator, cell.denominator)
                for cell in entry.rational_upper_audit.feasible_joint_channel[0]
            ],
            [Fraction(3, 10), Fraction(1, 5), Fraction(1, 5), Fraction(3, 10)],
        )
        self.assertTrue(certificate_can_clear(
            verify_analytic_portfolio(entry), threshold=0.6, selection_valid=True
        ))

    def test_exact_independent_product_is_safe_while_arbitrary_coupling_is_not(self) -> None:
        problem = xor_problem(CouplingModel.CONDITIONAL_INDEPENDENCE)
        experiment = independent_product_experiment(problem)

        self.assertAlmostEqual(decision_value(experiment, problem.decision_problem), 0.5)
        envelope = build_envelope_certificate(problem)
        verification = verify_envelope_certificate(problem, envelope)
        self.assertTrue(verification.valid, verification.reasons)
        self.assertAlmostEqual(envelope.upper_bound, 0.5)

    def test_envelope_is_sound_and_detects_tampering(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        envelope = build_envelope_certificate(problem)
        self.assertAlmostEqual(envelope.upper_bound, 1.0)
        self.assertTrue(verify_envelope_certificate(problem, envelope).valid)

        tampered = envelope.model_copy(update={"upper_bound": 0.5})
        verification = verify_envelope_certificate(problem, tampered)
        self.assertFalse(verification.valid)
        self.assertIn("clipped upper bound does not replay", verification.reasons)

        relabelled = envelope.model_copy(update={"derivation": "trusted because submitter said so"})
        label_verification = verify_envelope_certificate(problem, relabelled)
        self.assertFalse(label_verification.valid)
        self.assertIn("envelope derivation label does not replay", label_verification.reasons)

        tampered_witness = envelope.model_copy(update={
            "feasible_joint_channel": ((1.0, 0.0, 0.0, 0.0),) * 2,
        })
        witness_verification = verify_envelope_certificate(problem, tampered_witness)
        self.assertFalse(witness_verification.valid)
        self.assertIn(
            "feasible-channel witness does not satisfy the ambiguity set",
            witness_verification.reasons,
        )

    def test_pointwise_coverage_cannot_clear_even_with_low_bound(self) -> None:
        events = tuple(
            JointEventBound(
                event_id=f"fixed-{state}",
                state_id=state,
                transcripts=(("0", "0"), ("0", "1"), ("1", "0"), ("1", "1")),
                lower=1.0,
                upper=1.0,
                justification="normalization cross-check",
            )
            for state in ("0", "1")
        )
        problem = xor_problem(
            CouplingModel.LINEAR_MECHANISM,
            events=events,
            coverage=StatisticalCoverage.POINTWISE,
        )
        entry = solve_analytic_portfolio(problem, method="envelope")
        certificate = entry.envelope_certificate
        assert certificate is not None
        verification = verify_analytic_portfolio(entry)

        self.assertTrue(verification.valid)
        self.assertFalse(certificate.selection_valid)
        self.assertFalse(
            certificate_can_clear(
                verification,
                threshold=1.0,
                selection_valid=certificate.selection_valid,
            )
        )

    def test_invalid_marginal_intervals_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ConditionalMarginalBounds(
                release_id="bad-release",
                observation_ids=("0", "1"),
                lower=((0.7, 0.7), (0.5, 0.5)),
                upper=((0.8, 0.8), (0.5, 0.5)),
                evidence=evidence(
                    "bad-release-evidence",
                    "marginal:bad-release",
                    "coverage:deterministic",
                ),
            )

    def test_low_confidence_statistical_evidence_is_rejected(self) -> None:
        raw = xor_problem(CouplingModel.ARBITRARY).model_dump(mode="json")
        raw["coverage"] = "simultaneous"
        raw["coverage_confidence"] = 0.9
        for release in raw["releases"]:
            release["evidence"]["supports"] = [
                f"marginal:{release['release_id']}",
                "coverage:simultaneous",
            ]
        with self.assertRaisesRegex(ValidationError, "0.95 clearance-confidence floor"):
            IncompletePortfolioProblem.model_validate(raw)

    def test_exact_solver_refuses_exponential_request_over_limit(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        with self.assertRaisesRegex(ValueError, "use the decoder-free envelope"):
            solve_exact_portfolio(problem, max_decoders=15)

    def test_solver_rejects_invalid_resource_and_tolerance_limits_before_work(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        with self.assertRaisesRegex(ValueError, "max_decoders"):
            solve_analytic_portfolio(problem, max_decoders=0)
        with self.assertRaisesRegex(ValueError, "numerical_tolerance"):
            solve_analytic_portfolio(problem, numerical_tolerance=1e-4)

    def test_auto_solver_selects_exact_and_returns_portable_entry(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        entry = solve_analytic_portfolio(problem, method="auto")

        self.assertEqual(entry.schema_version, "1.1")
        self.assertIsNotNone(entry.exact_certificate)
        verification = verify_analytic_portfolio(entry)
        self.assertTrue(verification.valid, verification.reasons)
        self.assertTrue(verification.rationally_replayed)
        self.assertTrue(verification.outward_rounded)
        self.assertEqual(
            (verification.exact_upper_numerator, verification.exact_upper_denominator),
            (1, 1),
        )
        self.assertAlmostEqual(verification.upper_bound, 1.0)

    def test_auto_solver_falls_back_to_envelope(self) -> None:
        problem = xor_problem(CouplingModel.ARBITRARY)
        entry = solve_analytic_portfolio(problem, method="auto", max_decoders=15)

        self.assertIsNotNone(entry.envelope_certificate)
        verification = verify_analytic_portfolio(entry)
        self.assertTrue(verification.valid, verification.reasons)

    def test_rational_audit_tampering_and_threshold_boundary_fail_closed(self) -> None:
        problem = xor_problem(CouplingModel.LINEAR_MECHANISM, events=tuple(
            JointEventBound(
                event_id=f"fixed-{state}-{left}-{right}",
                state_id=state,
                transcripts=((left, right),),
                lower=0.25,
                upper=0.25,
                justification="exact rational boundary fixture",
            )
            for state in ("0", "1")
            for left, right in (("0", "0"), ("0", "1"), ("1", "0"), ("1", "1"))
        ))
        entry = solve_analytic_portfolio(problem, method="exact")
        verification = verify_analytic_portfolio(entry)
        self.assertEqual(
            Fraction(
                verification.exact_upper_numerator,
                verification.exact_upper_denominator,
            ),
            Fraction(1, 2),
        )
        self.assertTrue(certificate_can_clear(
            verification, threshold=0.5, selection_valid=True
        ))
        self.assertFalse(certificate_can_clear(
            verification,
            threshold=math.nextafter(0.5, 0.0),
            selection_valid=True,
        ))
        tampered_audit = entry.rational_upper_audit.model_copy(update={
            "exact_upper_numerator": 49,
            "exact_upper_denominator": 100,
            "outward_upper_bound": 0.49,
        })
        tampered = entry.model_copy(update={"rational_upper_audit": tampered_audit})
        tampered_verification = verify_analytic_portfolio(tampered)
        self.assertFalse(tampered_verification.valid)
        self.assertIn("rational upper audit does not replay", tampered_verification.reasons)
        self.assertFalse(certificate_can_clear(
            tampered_verification, threshold=0.5, selection_valid=True
        ))

    def test_outward_rounding_never_falls_below_exact_fraction(self) -> None:
        exact = Fraction(3, 10)
        rounded = outward_rounded_fraction(exact)
        self.assertGreaterEqual(Fraction.from_float(rounded), exact)
        self.assertEqual(rounded, math.nextafter(0.3, math.inf))

    def test_decimal_probability_vectors_have_exact_normalized_semantics(self) -> None:
        raw = xor_problem(CouplingModel.ARBITRARY).model_dump(mode="json")
        raw["state_ids"] = ["0", "1", "2"]
        raw["prior"] = [1.0 / 3.0] * 3
        raw["decision_problem"] = exact_guess_problem(
            ("0", "1", "2"), "three-state-exact-guess"
        ).model_dump(mode="json")
        for release in raw["releases"]:
            release["lower"] = [[0.5, 0.5]] * 3
            release["upper"] = [[0.5, 0.5]] * 3
        problem = IncompletePortfolioProblem.model_validate(raw)

        entry = solve_analytic_portfolio(problem, method="exact")
        verification = verify_analytic_portfolio(entry)

        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(
            Fraction(
                verification.exact_upper_numerator,
                verification.exact_upper_denominator,
            ),
            Fraction(2, 3),
        )
        self.assertEqual(
            entry.rational_upper_audit.number_interpretation,
            "exact_decimal_weights_normalized_per_probability_vector",
        )

    def test_interval_marginals_get_an_exact_rational_feasible_witness(self) -> None:
        raw = xor_problem(CouplingModel.ARBITRARY).model_dump(mode="json")
        for release in raw["releases"]:
            release["lower"] = [[0.4, 0.4], [0.4, 0.4]]
            release["upper"] = [[0.6, 0.6], [0.6, 0.6]]
        problem = IncompletePortfolioProblem.model_validate(raw)

        entry = solve_analytic_portfolio(problem, method="envelope")
        verification = verify_analytic_portfolio(entry)

        self.assertTrue(verification.valid, verification.reasons)
        for row in entry.rational_upper_audit.feasible_joint_channel:
            exact_row = sum(
                (Fraction(cell.numerator, cell.denominator) for cell in row),
                Fraction(0),
            )
            self.assertEqual(exact_row, 1)


if __name__ == "__main__":
    unittest.main()
