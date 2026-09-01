from __future__ import annotations

import json
import unittest
from pathlib import Path

from model_release_assurance.empirical_workflow import (
    EmpiricalWorkflowConfig,
    empirical_dependencies_available,
    run_empirical_xgboost_mlp_workflow,
)


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(empirical_dependencies_available(), "empirical dependencies unavailable")
class EmpiricalWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = json.loads((
            ROOT / "reproduction" / "model-audit-workflow" / "empirical-xgboost-mlp-config.json"
        ).read_text(encoding="utf-8"))
        raw.update({"replicates": 2, "samples_per_replicate": 600})
        raw["xgboost_parameters"]["n_estimators"] = 30
        raw["mlp_parameters"]["max_iter"] = 120
        cls.report = run_empirical_xgboost_mlp_workflow(
            EmpiricalWorkflowConfig.model_validate(raw)
        )

    def test_trains_real_xgboost_and_mlp_on_disjoint_holdouts(self) -> None:
        models = {item["kind"]: item for item in self.report["models"]}
        self.assertEqual(set(models), {"xgboost", "mlp"})
        self.assertTrue(all(len(item["replicates"]) == 2 for item in models.values()))
        self.assertTrue(all(item["mean_accuracy"] > 0.75 for item in models.values()))
        self.assertTrue(all(item["mean_roc_auc"] > 0.8 for item in models.values()))
        partitions = [
            item for item in self.report["stages"] if item["stage"] == "dataset_partition"
        ]
        self.assertTrue(all(item["overlap"] == 0 for item in partitions))

    def test_applies_simultaneous_exact_interval_correction(self) -> None:
        correction = self.report["statistical_correction"]
        self.assertEqual(correction["method"], "bonferroni")
        self.assertEqual(correction["interval_count"], 16)
        self.assertGreater(correction["per_interval_confidence"], 0.99)
        for model in self.report["models"]:
            for replicate in model["replicates"]:
                self.assertLessEqual(replicate["accuracy_lower"], replicate["accuracy"])
                self.assertGreaterEqual(replicate["accuracy_upper"], replicate["accuracy"])
                self.assertFalse(replicate["can_clear"])

    def test_runs_disjoint_membership_and_corruption_red_tests(self) -> None:
        red_stages = [
            item for item in self.report["stages"] if item["stage"] == "red_team_evaluation"
        ]
        self.assertEqual(len(red_stages), 4)
        for model in self.report["models"]:
            for replicate in model["replicates"]:
                membership = replicate["red_team"]["membership_attack"]
                corruption = replicate["red_team"]["feature_corruption"]
                self.assertTrue(membership["calibration_and_target_disjoint"])
                self.assertLessEqual(
                    membership["simultaneous_lower"],
                    membership["equal_prior_membership_success"],
                )
                self.assertFalse(membership["can_clear"])
                self.assertFalse(membership["can_block"])
                self.assertIn("gaussian_accuracy", corruption)
                self.assertIn("worst_single_feature_occlusion_accuracy", corruption)
                self.assertFalse(corruption["can_clear"])
                sacro = replicate["red_team"]["sacro_ml_inspired"]
                self.assertEqual(sacro["suite"], "mra_sacro_ml_inspired_red_team")
                self.assertEqual(
                    {tool["tool"] for tool in sacro["tools"]},
                    {"structural_disclosure", "worst_case_membership"},
                )
                self.assertFalse(sacro["can_clear"])

    def test_empirical_results_never_authorize(self) -> None:
        self.assertEqual(self.report["decision"], "no_release_authorization")
        self.assertTrue(all(not item["can_clear"] for item in self.report["models"]))


if __name__ == "__main__":
    unittest.main()
