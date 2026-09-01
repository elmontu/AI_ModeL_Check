from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_strategic_assurance_experiment",
    ROOT / "scripts" / "run_strategic_assurance_experiment.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StrategicAssuranceExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.problem = MODULE.StrategicAssuranceProblem.model_validate_json(
            (ROOT / "reproduction/strategic-assurance/config.json").read_text(
                encoding="utf-8"
            )
        )

    def test_seeded_experiment_replays_all_registered_claims(self) -> None:
        result = MODULE.run_experiment(
            self.problem,
            seed=20260825,
            samples=250,
            grid_denominator=100,
        )
        self.assertTrue(result["valid"])
        self.assertTrue(result["validation"]["certificate_replays_exactly"])
        self.assertTrue(
            result["validation"]["all_endpoint_statuses_agree_with_sampled_tuples"]
        )
        self.assertTrue(
            result["validation"]["monitoring_without_consequence_is_payoff_invariant"]
        )
        self.assertEqual(result["certificate"]["registered_model_status"], "contradicted")
        self.assertEqual(result["certificate"]["deployment_evidence_status"], "inconclusive")
        self.assertEqual(result["governance_decision"], "not_evaluated")
        self.assertFalse(result["certificate"]["all_evidence_deployment_eligible"])
        statuses = {
            row["claim_id"]: row["certified_status"] for row in result["sample_results"]
        }
        self.assertEqual(
            statuses["attacker:registered-membership-inference:unique-abstention"],
            "supported",
        )
        self.assertEqual(
            statuses["attacker:anonymous-external-inference:unique-abstention"],
            "contradicted",
        )

    def test_same_seed_produces_identical_machine_readable_result(self) -> None:
        left = MODULE.run_experiment(
            self.problem, seed=7, samples=50, grid_denominator=20
        )
        right = MODULE.run_experiment(
            self.problem, seed=7, samples=50, grid_denominator=20
        )
        self.assertEqual(left, right)

    def test_submitter_frontier_is_exact(self) -> None:
        result = MODULE.run_experiment(
            self.problem, seed=1, samples=10, grid_denominator=10
        )
        frontier = result["submitter_deterrence_frontier"]
        self.assertEqual(
            frontier[0]["minimum_consequence_for_registered_margin"],
            {"numerator": 130, "denominator": 1},
        )
        self.assertEqual(
            frontier[-1]["minimum_consequence_for_registered_margin"],
            {"numerator": 13, "denominator": 1},
        )

    def test_invalid_experiment_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.run_experiment(self.problem, samples=0)


if __name__ == "__main__":
    unittest.main()
