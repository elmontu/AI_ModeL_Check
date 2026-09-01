from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_design_controls.py"
SPEC = importlib.util.spec_from_file_location("evaluate_design_controls", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DesignControlEvaluationTests(unittest.TestCase):
    def test_every_enumerated_control_or_diagnostic_is_reproduced(self) -> None:
        report = MODULE.evaluate()

        self.assertTrue(report["all_expected_controls_observed"])
        self.assertEqual(report["case_count"], 12)
        self.assertEqual(report["discovered_test_count"], 12)
        self.assertEqual(report["passed_case_count"], 12)
        self.assertTrue(
            report["known_gap_observations"][0]["representation_sensitive"]
        )
        self.assertIn("do not authorize", report["non_claim"])


if __name__ == "__main__":
    unittest.main()
