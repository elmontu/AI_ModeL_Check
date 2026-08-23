from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_protocol_mutations.py"
SPEC = importlib.util.spec_from_file_location("evaluate_protocol_mutations", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProtocolMutationEvaluationTests(unittest.TestCase):
    def test_all_unsafe_mutants_are_rejected_without_breaking_controls(self) -> None:
        report = MODULE.evaluate()
        self.assertTrue(report["controls_passed"])
        self.assertEqual(report["unsafe_mutant_count"], 19)
        self.assertEqual(report["unsafe_mutants_rejected"], 19)
        self.assertEqual(report["mutation_score"], 1.0)
        self.assertTrue(report["valid"])

    def test_report_preserves_the_scientific_non_claim(self) -> None:
        report = MODULE.evaluate()
        self.assertIn("does not establish scientific test adequacy", report["non_claim"])


if __name__ == "__main__":
    unittest.main()
