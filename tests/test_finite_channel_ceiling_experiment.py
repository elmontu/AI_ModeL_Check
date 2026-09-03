from __future__ import annotations

import copy
import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_finite_channel_ceiling_experiment import (  # noqa: E402
    MODEL_FAMILIES,
    _channel,
    _prior,
    _tamper_checks,
    exact_channel_risk,
    exact_interval_bounds,
    replay_counts_with_production_analyzer,
    replay_counts_with_assurance_engine,
    run_experiment,
    simultaneous_intervals,
    validate_config,
)


class FiniteChannelCeilingExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(
            (ROOT / "reproduction" / "finite-channel-ceiling" / "config.json").read_text(
                encoding="utf-8"
            )
        )

    def test_frozen_known_channels_replay_exact_risk_roles(self) -> None:
        validate_config(self.config)
        prior = _prior(self.config)
        expected = {
            "xgboost-safe-margin": Fraction(11, 20),
            "cnn-policy-boundary": Fraction(13, 20),
            "llm-unsafe-margin": Fraction(4, 5),
        }
        self.assertEqual(
            {
                scenario["scenario_id"]: exact_channel_risk(_channel(scenario), prior)
                for scenario in self.config["scenarios"]
            },
            expected,
        )
        self.assertTrue(self.config["authority"]["experimental_only"])
        self.assertFalse(self.config["authority"]["prior_screens_promoted"])

    def test_production_replay_is_exact_and_family_neutral(self) -> None:
        scenario = self.config["scenarios"][0]
        counts = (
            (300, 250, 250, 200),
            (200, 250, 250, 300),
        )
        intervals = simultaneous_intervals(
            counts,
            float(self.config["familywise_alpha"]),
        )
        expected_floor, expected_ceiling = exact_interval_bounds(
            intervals[0],
            intervals[1],
            _prior(self.config),
        )
        outputs = [
            replay_counts_with_production_analyzer(
                self.config,
                scenario,
                1000,
                counts,
                model_family=model_family,
                intervals=intervals,
            )
            for model_family in MODEL_FAMILIES
        ]
        signatures = {
            (
                output["exact_floor"]["numerator"],
                output["exact_floor"]["denominator"],
                output["exact_ceiling"]["numerator"],
                output["exact_ceiling"]["denominator"],
                output["resolution"],
            )
            for output in outputs
        }
        self.assertEqual(len(signatures), 1)
        self.assertEqual(
            Fraction(
                outputs[0]["exact_floor"]["numerator"],
                outputs[0]["exact_floor"]["denominator"],
            ),
            expected_floor,
        )
        self.assertEqual(
            Fraction(
                outputs[0]["exact_ceiling"]["numerator"],
                outputs[0]["exact_ceiling"]["denominator"],
            ),
            expected_ceiling,
        )

    def test_incomplete_binding_and_certificate_tampering_fail_closed(self) -> None:
        scenario = self.config["scenarios"][0]
        counts = (
            (30, 25, 25, 20),
            (20, 25, 25, 30),
        )
        checks = _tamper_checks(self.config, scenario, 100, counts)
        self.assertEqual(len(checks), 3)
        self.assertTrue(all(check["passed"] for check in checks), checks)

    def test_source_backed_engine_reaches_clear_hold_and_block(self) -> None:
        count_tables = {
            "xgboost-safe-margin": (
                (600, 500, 500, 400),
                (400, 500, 500, 600),
            ),
            "cnn-policy-boundary": (
                (800, 200, 500, 500),
                (200, 800, 500, 500),
            ),
            "llm-unsafe-margin": (
                (1100, 500, 200, 200),
                (200, 200, 500, 1100),
            ),
        }
        expected = {
            "xgboost-safe-margin": "clear",
            "cnn-policy-boundary": "hold",
            "llm-unsafe-margin": "block",
        }
        results = {
            scenario["scenario_id"]: replay_counts_with_assurance_engine(
                self.config,
                scenario,
                2000,
                count_tables[scenario["scenario_id"]],
            )
            for scenario in self.config["scenarios"]
        }
        self.assertEqual(
            {scenario_id: result["release_gate"] for scenario_id, result in results.items()},
            expected,
        )
        self.assertTrue(all(
            result["source_verification_reached"]
            and result["evidence_classes"] == ["floor", "ceiling"]
            for result in results.values()
        ))

    def test_small_complete_run_retains_every_raw_count_row(self) -> None:
        config = copy.deepcopy(self.config)
        config["tiers"] = [
            {
                "tier_id": "fast-calibration",
                "role": "diagnostic_only",
                "replicates": 1,
                "sample_sizes_per_state": [20, 21],
                "production_replay": "first_n_per_group",
                "production_replay_replicates": 1,
            },
            {
                "tier_id": "representative-full-replay",
                "role": "primary",
                "replicates": 1,
                "sample_sizes_per_state": [22],
                "production_replay": "all",
                "production_replay_replicates": 1,
            },
        ]
        report = run_experiment(config)
        self.assertEqual(report["completion"]["expected_records"], 9)
        self.assertEqual(report["completion"]["completed_records"], 9)
        self.assertTrue(report["completion"]["all_predeclared_cells_reported"])
        self.assertEqual(len(report["raw_count_records"]), 9)
        self.assertTrue(all(
            len(record["state_rows"]) == 2
            and all(
                sum(row["counts"]) == record["sample_size_per_state"]
                and row["trials"] == record["sample_size_per_state"]
                for row in record["state_rows"]
            )
            for record in report["raw_count_records"]
        ))
        self.assertTrue(all(
            group["production_replay_mismatches"] == 0
            for group in report["groups"]
        ))
        self.assertTrue(all(
            check["exactly_invariant"]
            for check in report["model_family_invariance_checks"]
        ))
        self.assertEqual(report["design"]["evaluation_simultaneous_bound_count"], 27)
        self.assertTrue(all(
            group["decision_power"]["expected_decision"] in {"CLEAR", "HOLD", "BLOCK"}
            and 0.0 <= group["decision_power"]["simultaneous_exact_binomial_lower"] <= 1.0
            for group in report["groups"]
        ))
        self.assertEqual(report["replay_scope"]["primary_analyzer_replays"], 3)
        self.assertEqual(report["replay_scope"]["full_source_backed_engine_replays"], 3)

    def test_config_rejects_retroactive_screen_promotion(self) -> None:
        changed = copy.deepcopy(self.config)
        changed["authority"]["prior_screens_promoted"] = True
        with self.assertRaisesRegex(ValueError, "outcome-new"):
            validate_config(changed)


if __name__ == "__main__":
    unittest.main()
