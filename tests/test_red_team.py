from __future__ import annotations

import unittest

from model_release_assurance.empirical_workflow import empirical_dependencies_available
from model_release_assurance.red_team import (
    RedTeamConfig,
    RedTeamTarget,
    RedTeamToolRegistry,
    SACRO_ML_REFERENCE,
    StructuralDisclosureTool,
    WorstCaseMembershipTool,
    default_red_team_tool_registry,
)


@unittest.skipUnless(empirical_dependencies_available(), "empirical dependencies unavailable")
class SacroInspiredRedTeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from sklearn.datasets import make_classification
        from sklearn.model_selection import train_test_split
        from sklearn.neural_network import MLPClassifier
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        features, target = make_classification(
            n_samples=600,
            n_features=12,
            n_informative=7,
            n_redundant=2,
            random_state=17,
        )
        train_x, test_x, train_y, test_y = train_test_split(
            features, target, test_size=0.3, stratify=target, random_state=18
        )
        model = make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(12,), solver="lbfgs", max_iter=400, random_state=19
            ),
        ).fit(train_x, train_y)
        cls.report = default_red_team_tool_registry().run(
            RedTeamTarget("test-mlp", "mlp", model, train_x, train_y, test_x, test_y),
            RedTeamConfig(seed=20, membership_repetitions=2),
        )

    def test_suite_is_attributed_versioned_and_non_clearing(self) -> None:
        self.assertEqual(self.report["schema_version"], "1.0")
        self.assertEqual(self.report["reference"]["project"], "SACRO-ML")
        self.assertEqual(
            self.report["reference"]["reviewed_commit"],
            SACRO_ML_REFERENCE["reviewed_commit"],
        )
        self.assertEqual(self.report["decision"], "no_release_authorization")
        self.assertFalse(self.report["can_clear"])

    def test_structural_tool_reports_aggregate_indicators_only(self) -> None:
        structural = next(
            item for item in self.report["tools"] if item["tool"] == "structural_disclosure"
        )
        self.assertGreater(structural["metrics"]["learned_parameter_count"], 0)
        self.assertIn("degrees_of_freedom_risk", structural["flags"])
        self.assertIn("rounding-dependent", structural["method_notes"][
            "equivalence_class_limitation"
        ])
        self.assertIn("small_group_screen", structural["flags"])
        self.assertIn("zero_probability_equivalence_classes", structural["metrics"])
        self.assertFalse(structural["record_level_output_retained"])
        self.assertFalse(structural["can_clear"])

    def test_worst_case_attack_has_repetitions_dummy_baseline_and_bounds(self) -> None:
        attack = next(
            item for item in self.report["tools"] if item["tool"] == "worst_case_membership"
        )
        self.assertEqual(len(attack["repetitions"]), 2)
        self.assertTrue(all("dummy_auc" in item for item in attack["repetitions"]))
        self.assertTrue(all(
            item["simultaneous_tpr_lower"] <= item["tpr"]
            and item["simultaneous_fpr_upper"] >= item["fpr"]
            for item in attack["repetitions"]
        ))
        self.assertFalse(attack["record_level_output_retained"])
        self.assertFalse(attack["can_clear"])

    def test_duplicate_tools_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique names"):
            RedTeamToolRegistry((StructuralDisclosureTool(), StructuralDisclosureTool()))

    def test_default_registry_exposes_mcp_ready_tools(self) -> None:
        tools = default_red_team_tool_registry().tools
        self.assertEqual({tool.name for tool in tools}, {
            "structural_disclosure", "worst_case_membership",
        })
        self.assertTrue(all(tool.mcp_tool.startswith("red_team_") for tool in tools))


if __name__ == "__main__":
    unittest.main()
