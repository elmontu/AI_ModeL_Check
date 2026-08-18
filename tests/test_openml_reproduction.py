from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import hypergeom


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_openml_membership import minimum_zero_failure_sample
from run_openml_membership import one_sided_clopper_pearson, threshold_at_fpr
from run_openml_metadata_adversary import numeric_stats
from run_openml_dp_sgd import compose_epsilon, sampled_gaussian_rdp_integer
from run_openml_population_validation import hypergeometric_lower
from run_openml_structural import make_splits, signature_histogram


class OpenMLReproductionTests(unittest.TestCase):
    def test_split_is_deterministic_disjoint_partition(self) -> None:
        y = np.tile(np.arange(2), 100)
        fractions = {
            "target_train": 0.5,
            "reference_train": 0.2,
            "attack_calibration": 0.1,
            "attack_audit_nonmember": 0.1,
            "utility_test": 0.1,
        }
        first = make_splits(y, 42, fractions)
        second = make_splits(y, 42, fractions)
        self.assertEqual({name: len(value) for name, value in first.items()}, {
            "target_train": 100,
            "reference_train": 40,
            "attack_calibration": 20,
            "attack_audit_nonmember": 20,
            "utility_test": 20,
        })
        self.assertTrue(all(np.array_equal(first[name], second[name]) for name in first))
        combined = np.concatenate(list(first.values()))
        self.assertEqual(len(np.unique(combined)), len(y))

    def test_signature_histogram_exact_metrics(self) -> None:
        leaves = np.asarray([[1, 2], [1, 2], [3, 4], [5, 6]])
        histogram, metrics = signature_histogram(leaves)
        self.assertEqual([item["count"] for item in histogram], [2, 1, 1])
        self.assertEqual(metrics["records"], 4)
        self.assertEqual(metrics["occupied_cells"], 3)
        self.assertEqual(metrics["minimum_cell_size"], 1)
        self.assertEqual(metrics["singleton_records"], 2)
        self.assertEqual(metrics["singleton_fraction"], 0.5)
        self.assertEqual(metrics["bayes_linkage_success"], 0.75)

    def test_low_fpr_zero_failure_sample_size(self) -> None:
        required = minimum_zero_failure_sample(0.001, 0.95)
        self.assertEqual(required, 2995)
        self.assertGreater(one_sided_clopper_pearson(0, required - 1, 0.95)[1], 0.001)
        self.assertLessEqual(one_sided_clopper_pearson(0, required, 0.95)[1], 0.001)

    def test_threshold_does_not_split_score_ties(self) -> None:
        scores = np.asarray([1.0, 1.0, 0.5, 0.25])
        threshold, selected = threshold_at_fpr(scores, 0.25)
        self.assertEqual(selected, 0)
        self.assertGreater(threshold, scores.max())
        threshold, selected = threshold_at_fpr(scores, 0.5)
        self.assertEqual(selected, 2)
        self.assertEqual(threshold, 1.0)

    def test_zero_failure_formula(self) -> None:
        n = minimum_zero_failure_sample(0.01, 0.95)
        self.assertEqual(n, math.ceil(math.log(0.05) / math.log(0.99)))

    def test_exact_numeric_metadata_includes_location_and_spread(self) -> None:
        stats = numeric_stats(pd.Series([1.0, 2.0, 3.0, 4.0, np.nan]))
        self.assertEqual(stats["minimum"], 1.0)
        self.assertEqual(stats["maximum"], 4.0)
        self.assertEqual(stats["range"], 3.0)
        self.assertEqual(stats["mean"], 2.5)
        self.assertEqual(stats["median"], 2.5)
        self.assertEqual(stats["variance"], 1.25)
        self.assertAlmostEqual(stats["standard_deviation"], math.sqrt(1.25))
        self.assertEqual(stats["interquartile_range"], 1.5)
        self.assertEqual(stats["median_absolute_deviation"], 1.0)
        self.assertEqual(stats["missing_count"], 1)

    def test_sampled_gaussian_reduces_to_gaussian_without_subsampling(self) -> None:
        for order in (2, 3, 8, 16):
            self.assertAlmostEqual(
                sampled_gaussian_rdp_integer(order, 1.0, 2.0),
                order / 8.0,
                places=12,
            )
        epsilon, best_order, by_order = compose_epsilon(1.0, 2.0, 3, 1e-5, [2, 3, 8])
        self.assertEqual(epsilon, min(by_order.values()))
        self.assertEqual(epsilon, by_order[str(best_order)])

    def test_hypergeometric_lower_bound_is_conservative_and_monotone(self) -> None:
        lowers = [hypergeometric_lower(100, 20, observed, 0.05) for observed in range(0, 21)]
        self.assertEqual(lowers[0], 0)
        self.assertTrue(all(left <= right for left, right in zip(lowers, lowers[1:])))
        for observed, lower in enumerate(lowers[1:], 1):
            self.assertGreater(hypergeom.sf(observed - 1, 100, lower, 20), 0.05)


if __name__ == "__main__":
    unittest.main()
