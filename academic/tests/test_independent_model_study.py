"""Pre-run algebra and artifact checks; no confirmatory model fitting."""
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("independent_model_study", ROOT / "academic/scripts/run_independent_model_study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class IndependentModelStudyTests(unittest.TestCase):
    def setUp(self):
        self.reg = json.loads(study.REGISTRATION.read_text())

    def test_frozen_allocation_counts_every_candidate_and_unique_utility_family(self):
        self.assertEqual(len(self.reg["families"]) * self.reg["models_per_family"], 168)
        self.assertEqual(study.allocated_failure_bound(self.reg), F(8568) / study.taylor_exp_lower(16))
        self.assertLess(study.allocated_failure_bound(self.reg), F(1, 20))
        self.assertLess(F(32) / study.taylor_exp_lower(F(168, 25)), F(1, 20))

    def test_oracle_agrees_with_joint_enumeration_and_negative_controls(self):
        for predictions in (np.zeros(36, dtype=np.uint8), study.BASE_LABELS, 1 - study.BASE_LABELS):
            for q in map(F, self.reg["regimes"].values()):
                for rho in map(F, self.reg["controls"]):
                    rows, risk, utility = study.oracle(predictions, q, rho)
                    joint = [[F(0), F(0)], [F(0), F(0)]]
                    for index, base in enumerate(study.BASE_LABELS):
                        for task in (0, 1):
                            ptask = F(9 if task == base else 1, 10)
                            for secret in (0, 1):
                                psecret = 1 - q if task == secret else q
                                for output in (0, 1):
                                    pout = 1 - rho if output == predictions[index] else rho
                                    joint[secret][output] += ptask * psecret * pout / 36
                    independent_risk = sum(max(joint[0][output], joint[1][output]) for output in (0, 1))
                    self.assertEqual(risk, independent_risk)
                    self.assertEqual(rows, [2 * joint[s][1] for s in (0, 1)])
                    if rho == F(1, 5):
                        self.assertLess(utility, F(3, 4))

    def test_interval_contains_every_compatible_grid_channel_and_includes_prior(self):
        for c0 in range(0, 11, 2):
            for c1 in range(0, 11, 2):
                low, high, _ = study.risk_interval((c0, c1), 10, F(1, 5))
                self.assertGreaterEqual(low, F(1, 2))
                for p0 in map(lambda x: F(x, 10), range(11)):
                    for p1 in map(lambda x: F(x, 10), range(11)):
                        if abs(p0 - F(c0, 10)) <= F(1, 5) and abs(p1 - F(c1, 10)) <= F(1, 5):
                            value = max(1 - p0, 1 - p1) / 2 + max(p0, p1) / 2
                            self.assertLessEqual(low, value)
                            self.assertGreaterEqual(high, value)

    def test_randomized_response_controls_have_exact_blackwell_order(self):
        for left, right in zip(map(F, self.reg["controls"]), map(F, self.reg["controls"][1:])):
            gamma = (right - left) / (1 - 2 * left)
            self.assertTrue(0 <= gamma <= F(1, 2))
            self.assertEqual(left + gamma - 2 * left * gamma, right)

    def test_partial_results_never_claim_confirmatory_intervals(self):
        partial = study.summarize(self.reg, [{"family": "logistic", "model_index": 0, "status": "failed"}])
        self.assertFalse(partial["confirmatory_complete"])
        self.assertEqual(partial["attempted_fits"], 1)
        self.assertIsNone(partial["primary_model_mean_failure_upper"])
        self.assertTrue(all(not group["primary_intervals"] for group in partial["groups"]))

    def test_freeze_is_non_overwriting_and_changed_runner_binding_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            study.freeze(output)
            self.assertFalse((output / "STARTED.json").exists())
            with self.assertRaises(FileExistsError):
                study.freeze(output)
            frozen = json.loads((output / "FROZEN.json").read_text())
            frozen["runner_sha256"] = "0" * 64
            study.write_json(output / "FROZEN.json", frozen)
            with self.assertRaisesRegex(ValueError, "mismatch"):
                study.run(output)
            self.assertFalse((output / "STARTED.json").exists())


if __name__ == "__main__":
    unittest.main()
