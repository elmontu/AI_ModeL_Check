from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_protocol_feasibility_benchmark",
    ROOT / "scripts" / "run_protocol_feasibility_benchmark.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProtocolFeasibilityBenchmarkTests(unittest.TestCase):
    def test_exact_and_empirical_benchmark_replays(self) -> None:
        raw, summary, analysis = MODULE.run_benchmark(
            seeds=(20260815,),
            trials_per_world=100,
        )
        self.assertEqual(summary["monte_carlo_rows"], 16)
        self.assertEqual(summary["monte_carlo_trials"], 1600)
        self.assertTrue(analysis["validation"]["all_binary_frontiers_tight"])
        self.assertTrue(analysis["validation"]["open_world_zero_error_is_impossible"])
        self.assertTrue(analysis["validation"]["common_control_enables_exact_release"])
        self.assertTrue(analysis["validation"]["synthetic_benchmark_passed"])
        self.assertEqual(analysis["external_evidence"]["status"], "not_evaluated")
        self.assertFalse(summary["representative_release_yield_identified"])
        self.assertFalse(summary["release_authorization_issued"])
        for row in raw["monte_carlo_rows"]:
            self.assertEqual(
                row["acceptable_release_count"]
                + row["unsafe_release_count"]
                + row["refusal_count"],
                row["trials"],
            )

    def test_default_is_self_contained_and_shapes_exclude_stale_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = MODULE.ROOT
            MODULE.ROOT = Path(directory)
            try:
                raw, summary, analysis = MODULE.run_benchmark(
                    seeds=(20260815,),
                    trials_per_world=1,
                )
            finally:
                MODULE.ROOT = original_root

        self.assertEqual(
            set(raw),
            {
                "benchmark",
                "seeds",
                "trials_per_world_per_seed",
                "monte_carlo_rows",
            },
        )
        self.assertEqual(
            set(analysis),
            {
                "benchmark",
                "claim_boundary",
                "exact_frontiers",
                "special_cases",
                "external_evidence",
                "validation",
            },
        )
        self.assertEqual(
            set(analysis["validation"]),
            {
                "all_binary_frontiers_tight",
                "open_world_zero_error_is_impossible",
                "common_control_enables_exact_release",
                "randomized_single_transcript_target_met",
                "deterministic_single_transcript_target_impossible",
                "synthetic_benchmark_passed",
            },
        )
        self.assertEqual(
            set(summary),
            {
                "benchmark",
                "claim_boundary",
                "q_values",
                "exact_frontiers",
                "special_cases",
                "monte_carlo_rows",
                "monte_carlo_trials",
                "synthetic_benchmark_passed",
                "external_evidence_status",
                "representative_release_yield_identified",
                "release_authorization_issued",
            },
        )
        stale_fields = {
            "retained_evidence_audit",
            "retained_datasets",
            "retained_trained_ml_artifacts",
            "retained_tiers",
            "decision_oracles",
            "decision_oracles_passed",
        }
        self.assertTrue(stale_fields.isdisjoint(analysis))
        self.assertTrue(stale_fields.isdisjoint(summary))
        self.assertEqual(summary["external_evidence_status"], "not_evaluated")
        self.assertTrue(summary["synthetic_benchmark_passed"])

    def test_invalid_seed_and_trial_inputs_fail_before_execution(self) -> None:
        cases = (
            {"seeds": (), "trials_per_world": 1},
            {"seeds": (True,), "trials_per_world": 1},
            {"seeds": ("not-an-integer",), "trials_per_world": 1},
            {"seeds": (1,), "trials_per_world": 0},
            {"seeds": (1,), "trials_per_world": True},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    MODULE.run_benchmark(**kwargs)


if __name__ == "__main__":
    unittest.main()
