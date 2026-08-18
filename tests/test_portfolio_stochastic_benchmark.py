from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_portfolio_stochastic_benchmark import (  # noqa: E402
    bayes_value,
    linear_diagonal_exact_value,
    marginal_probabilities,
    problem_from_intervals,
    run_benchmark,
)
from analyze_portfolio_stochastic_benchmark import analyze  # noqa: E402
from model_release_assurance.incomplete_portfolio import (  # noqa: E402
    solve_exact_portfolio,
    verify_exact_certificate,
)


class PortfolioStochasticBenchmarkTests(unittest.TestCase):
    def test_channel_marginals_and_true_bayes_values(self) -> None:
        xor = np.asarray([[0.5, 0.0, 0.0, 0.5], [0.0, 0.5, 0.5, 0.0]])
        first, second = marginal_probabilities(xor)
        self.assertTrue(np.allclose(first, 0.5))
        self.assertTrue(np.allclose(second, 0.5))
        self.assertAlmostEqual(bayes_value(xor), 1.0)

        partial = np.asarray([[0.3, 0.2, 0.2, 0.3], [0.2, 0.3, 0.3, 0.2]])
        self.assertAlmostEqual(bayes_value(partial), 0.6)

    def test_binary_diagonal_vertex_solver_matches_general_certificate(self) -> None:
        config = json.loads(
            (ROOT / "reproduction/portfolio-stochastic/config.json").read_text()
        )
        scenario = next(
            value for value in config["scenarios"]
            if value["scenario_id"] == "partial-certified"
        )
        lower = np.asarray([
            [[0.44, 0.44], [0.43, 0.43]],
            [[0.45, 0.45], [0.42, 0.42]],
        ])
        upper = np.asarray([
            [[0.56, 0.56], [0.57, 0.57]],
            [[0.55, 0.55], [0.58, 0.58]],
        ])
        special = linear_diagonal_exact_value(lower, upper, (0.6, 0.4))
        self.assertIsNotNone(special)
        problem = problem_from_intervals(scenario, lower, upper)
        certificate = solve_exact_portfolio(problem)
        verification = verify_exact_certificate(problem, certificate)
        self.assertTrue(verification.valid, verification.reasons)
        self.assertAlmostEqual(special, verification.upper_bound, places=8)

    def test_small_seeded_benchmark_has_no_false_clear_or_replay_failure(self) -> None:
        config = json.loads(
            (ROOT / "reproduction/portfolio-stochastic/config.json").read_text()
        )
        config["replicates"] = 10
        config["sample_sizes_per_state"] = [100]
        summary, raw = run_benchmark(config)

        self.assertEqual(summary["completed_groups"], 5)
        self.assertEqual(len(raw), 50)
        self.assertTrue(all(group["certificate_replay_failures"] == 0 for group in summary["groups"]))
        self.assertTrue(all(group["exact_equivalence_failures"] == 0 for group in summary["groups"]))
        self.assertTrue(all(
            decision["false_clear_rate"] == 0.0
            for group in summary["groups"]
            for decision in group["decisions"].values()
        ))
        self.assertTrue(all(
            record["certified_upper_bound"] is None
            or record["certified_upper_bound"] >= record["true_bayes_value"] - 1e-10
            for record in raw
        ))
        analysis = analyze(summary, raw)
        self.assertTrue(analysis["validation"]["valid"], analysis["validation"]["errors"])


if __name__ == "__main__":
    unittest.main()
