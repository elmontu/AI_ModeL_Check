from __future__ import annotations

import importlib.util
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
        self.assertTrue(analysis["validation"]["all_decision_oracles_passed"])
        self.assertFalse(summary["representative_release_yield_identified"])
        for row in raw["monte_carlo_rows"]:
            self.assertEqual(
                row["acceptable_release_count"]
                + row["unsafe_release_count"]
                + row["refusal_count"],
                row["trials"],
            )


if __name__ == "__main__":
    unittest.main()
