from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_v05_prospective_study import (  # noqa: E402
    choose_greedy_allocation,
    choose_joint_allocation,
    group_privacy,
    utility_pass,
)
from run_v05_prospective_study import _load_datasets  # noqa: E402


class ProspectiveV05StudyTests(unittest.TestCase):
    def test_full_corpus_design_resolves_every_active_cc18_dataset(self) -> None:
        design = json.loads(
            (ROOT / "reproduction/prospective-v05/config.json").read_text(encoding="utf-8")
        )
        dp_config = json.loads(
            (ROOT / "reproduction/openml/dp-sgd-config.json").read_text(encoding="utf-8")
        )
        _, datasets = _load_datasets(design, dp_config)
        self.assertEqual(len(datasets), 72)
        self.assertEqual(len({int(item["dataset_id"]) for item in datasets}), 72)
        self.assertTrue(all(item["status"] == "active" for item in datasets))

    def test_group_privacy_uses_epsilon_and_delta_lift(self) -> None:
        epsilon, delta = group_privacy(1.0, 1e-5, 2)
        self.assertEqual(epsilon, 2.0)
        self.assertAlmostEqual(delta, 1e-5 * (1.0 + math.e), places=15)

    def test_joint_allocation_can_outperform_myopic_greedy(self) -> None:
        arguments = {
            "actions": ("expensive", "moderate"),
            "eligible": {"expensive": True, "moderate": True},
            "values": {"expensive": 0.9, "moderate": 0.6},
            "costs": {"expensive": (8.0, 1e-5), "moderate": (2.0, 1e-5)},
            "weights": (1.0, 0.8, 0.6),
            "epsilon_budget": 8.0,
            "delta_budget": 1e-3,
        }
        joint = choose_joint_allocation(**arguments)
        greedy = choose_greedy_allocation(**arguments)
        self.assertEqual(joint, ("moderate", "moderate", "moderate"))
        self.assertEqual(greedy, ("expensive", "refuse", "refuse"))

    def test_utility_contract_requires_relative_and_absolute_floors(self) -> None:
        design = {
            "utility_max_balanced_accuracy_degradation": 0.1,
            "utility_minimum_margin_above_chance": 0.05,
        }
        passing = {
            "class_count": 2,
            "utility": {"balanced_accuracy": 0.71},
            "matched_non_private_utility": {"balanced_accuracy": 0.8},
        }
        failing = {
            "class_count": 2,
            "utility": {"balanced_accuracy": 0.69},
            "matched_non_private_utility": {"balanced_accuracy": 0.8},
        }
        self.assertTrue(utility_pass(passing, design))
        self.assertFalse(utility_pass(failing, design))


if __name__ == "__main__":
    unittest.main()
