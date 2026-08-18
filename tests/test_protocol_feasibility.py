from __future__ import annotations

import unittest
from fractions import Fraction

from model_release_assurance.protocol_feasibility import (
    AuthorizationMode,
    ProtocolFeasibilityProblem,
    ProtocolWorld,
    assurance_failure_upper_bound,
    maximal_sound_gate,
    protocol_problem_sha256,
    robustly_releasable_configurations,
    solve_protocol_feasibility,
    verify_protocol_feasibility,
)
from model_release_assurance.incomplete_portfolio import RationalNumber


class ProtocolFeasibilityTests(unittest.TestCase):
    @staticmethod
    def rational(numerator: int, denominator: int = 1) -> RationalNumber:
        return RationalNumber(numerator=numerator, denominator=denominator)

    def binary_problem(
        self,
        *,
        q: Fraction,
        alpha: Fraction,
        beta: Fraction,
        mode: AuthorizationMode = AuthorizationMode.RANDOMIZED,
    ) -> ProtocolFeasibilityProblem:
        r = self.rational
        return ProtocolFeasibilityProblem(
            problem_id=f"binary-{mode.value}",
            evidence_ids=("e0", "e1"),
            configuration_ids=("c0", "c1"),
            worlds=(
                ProtocolWorld(
                    world_id="w0",
                    evidence_probabilities=(
                        r((1 - q).numerator, (1 - q).denominator),
                        r(q.numerator, q.denominator),
                    ),
                    acceptable_configuration_ids=("c0",),
                ),
                ProtocolWorld(
                    world_id="w1",
                    evidence_probabilities=(
                        r(q.numerator, q.denominator),
                        r((1 - q).numerator, (1 - q).denominator),
                    ),
                    acceptable_configuration_ids=("c1",),
                ),
            ),
            unsafe_release_budget=r(alpha.numerator, alpha.denominator),
            liveness_failure_budget=r(beta.numerator, beta.denominator),
            authorization_mode=mode,
        )

    def test_randomized_noisy_two_world_frontier_has_exact_replay(self) -> None:
        problem = self.binary_problem(
            q=Fraction(1, 10),
            alpha=Fraction(1, 10),
            beta=Fraction(1, 10),
        )
        certificate = solve_protocol_feasibility(problem)
        verification = verify_protocol_feasibility(certificate)
        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(verification.status, "target_met")
        self.assertEqual(
            Fraction(
                verification.exact_lower_numerator,
                verification.exact_lower_denominator,
            ),
            Fraction(9, 10),
        )
        self.assertEqual(
            Fraction(
                verification.exact_upper_numerator,
                verification.exact_upper_denominator,
            ),
            Fraction(9, 10),
        )

    def test_open_world_indistinguishability_forces_refusal(self) -> None:
        problem = ProtocolFeasibilityProblem(
            problem_id="open-world-impossibility",
            evidence_ids=("same",),
            configuration_ids=("c0", "c1"),
            worlds=(
                ProtocolWorld(
                    world_id="w0",
                    evidence_probabilities=(self.rational(1),),
                    acceptable_configuration_ids=("c0",),
                ),
                ProtocolWorld(
                    world_id="w1",
                    evidence_probabilities=(self.rational(1),),
                    acceptable_configuration_ids=("c1",),
                ),
            ),
            unsafe_release_budget=self.rational(0),
            liveness_failure_budget=self.rational(1, 2),
        )
        verification = verify_protocol_feasibility(solve_protocol_feasibility(problem))
        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(verification.status, "target_impossible")
        self.assertEqual(verification.exact_upper_numerator, 0)

    def test_randomization_strictly_changes_the_frontier(self) -> None:
        randomized = ProtocolFeasibilityProblem(
            problem_id="single-transcript-randomized",
            evidence_ids=("same",),
            configuration_ids=("c0", "c1"),
            worlds=(
                ProtocolWorld(
                    world_id="w0",
                    evidence_probabilities=(self.rational(1),),
                    acceptable_configuration_ids=("c0",),
                ),
                ProtocolWorld(
                    world_id="w1",
                    evidence_probabilities=(self.rational(1),),
                    acceptable_configuration_ids=("c1",),
                ),
            ),
            unsafe_release_budget=self.rational(1, 2),
            liveness_failure_budget=self.rational(1, 2),
        )
        deterministic = randomized.model_copy(
            update={
                "problem_id": "binary-deterministic",
                "authorization_mode": AuthorizationMode.DETERMINISTIC,
            }
        )
        randomized_result = verify_protocol_feasibility(
            solve_protocol_feasibility(randomized)
        )
        deterministic_result = verify_protocol_feasibility(
            solve_protocol_feasibility(deterministic)
        )
        self.assertEqual(randomized_result.status, "target_met")
        self.assertEqual(
            Fraction(
                randomized_result.exact_lower_numerator,
                randomized_result.exact_lower_denominator,
            ),
            Fraction(1, 2),
        )
        self.assertEqual(deterministic_result.status, "target_impossible")
        self.assertEqual(deterministic_result.exact_upper_numerator, 0)

    def test_tampered_protocol_certificate_fails_exact_replay(self) -> None:
        certificate = solve_protocol_feasibility(
            self.binary_problem(
                q=Fraction(1, 10),
                alpha=Fraction(1, 10),
                beta=Fraction(1, 10),
            )
        )
        tampered = certificate.model_copy(
            update={"problem_sha256": "0" * 64}
        )
        verification = verify_protocol_feasibility(tampered)
        self.assertFalse(verification.valid)
        self.assertIn("another protocol problem", " ".join(verification.reasons))

    def test_certificate_must_match_externally_approved_problem(self) -> None:
        problem = self.binary_problem(
            q=Fraction(1, 10),
            alpha=Fraction(1, 10),
            beta=Fraction(1, 10),
        )
        certificate = solve_protocol_feasibility(problem)
        other_problem = problem.model_copy(
            update={"problem_id": "different-approved-problem"}
        )
        verification = verify_protocol_feasibility(
            certificate,
            expected_problem_sha256=protocol_problem_sha256(other_problem),
        )
        self.assertFalse(verification.valid)
        self.assertIn("externally supplied", " ".join(verification.reasons))

    def test_mixed_evidence_cell_cannot_clear_the_unsafe_configuration(self) -> None:
        # The same lower-order portfolio evidence is compatible with an
        # independent safe world and a parity world that discloses the secret.
        releasable = robustly_releasable_configurations(
            ("independent-safe", "parity-disclosing"),
            ("raw-portfolio",),
            {("raw-portfolio", "independent-safe")},
        )
        self.assertEqual(releasable, ())

    def test_additional_evidence_can_make_nontrivial_release_possible(self) -> None:
        gate = maximal_sound_gate(
            {
                "proper-subsets-only": ("independent-safe", "parity-disclosing"),
                "certified-zero-parity-interaction": ("independent-safe",),
            },
            ("raw-portfolio", "controlled-interface"),
            {
                ("raw-portfolio", "independent-safe"),
                ("controlled-interface", "independent-safe"),
                ("controlled-interface", "parity-disclosing"),
            },
        )
        self.assertEqual(gate["proper-subsets-only"], ("controlled-interface",))
        self.assertEqual(
            gate["certified-zero-parity-interaction"],
            ("raw-portfolio", "controlled-interface"),
        )

    def test_failure_budget_is_additive_without_independence(self) -> None:
        self.assertEqual(
            assurance_failure_upper_bound(
                (Fraction(1, 100), Fraction(1, 200)),
                (Fraction(1, 1000),),
            ),
            Fraction(16, 1000),
        )

    def test_out_of_domain_acceptability_entry_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "out-of-domain"):
            robustly_releasable_configurations(
                ("world-a",),
                ("configuration-a",),
                {("configuration-a", "world-b")},
            )


if __name__ == "__main__":
    unittest.main()
