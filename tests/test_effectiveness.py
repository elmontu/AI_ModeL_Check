from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_framework_effectiveness import run_evaluation  # noqa: E402


class EffectivenessEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_evaluation()

    def test_executable_oracles_match_all_declared_decisions(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(summary["executable_oracle_checks"], 99)
        self.assertEqual(summary["executable_oracle_checks_passed"], 99)
        self.assertEqual(summary["unexpected_decision_failures"], 0)
        self.assertEqual(summary["valid_clearance_misses"], 0)
        self.assertEqual(summary["unsafe_clearances_observed"], 0)
        self.assertTrue(summary["safe_fail_closed_behavior"])
        self.assertTrue(summary["complete_decision_semantics"])

    def test_all_reported_structural_datasets_are_exercised(self) -> None:
        rows = self.result["structural_linkage"]["twelve_datasets"]
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["passed"] for row in rows))

    def test_unattainable_attacks_never_clear(self) -> None:
        attack = self.result["membership_attack_simulation"]
        self.assertEqual(attack["floor_count"], 24)
        self.assertEqual(attack["screen_count"], 42)
        self.assertEqual(attack["clear_count"], 0)

    def test_evaluation_detects_incomplete_end_to_end_coverage(self) -> None:
        self.assertFalse(self.result["summary"]["effective_as_end_to_end_empirical_assurance_service"])
        severities = {gap["severity"] for gap in self.result["capability_gaps"]}
        self.assertIn("critical", severities)
        self.assertIn("high", severities)

    def test_controlled_attribute_and_reconstruction_contracts_are_enforced(self) -> None:
        probes = self.result["attribute_and_reconstruction_probes"]
        self.assertTrue(probes["attribute_inference"]["incremental_gap_contract_supported"])
        self.assertEqual(probes["attribute_inference"]["controlled_evidence_class"], "floor")
        self.assertTrue(
            probes["reconstruction"]["mandatory_ground_truth_and_membership_verification_enforced"]
        )
        self.assertEqual(probes["reconstruction"]["unverified_attack_evidence_class"], "screen")


if __name__ == "__main__":
    unittest.main()
