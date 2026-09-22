"""Bounded kernel, information-flow and export-schema checks; no model study."""

import copy
from fractions import Fraction
import hashlib
import json
import unittest
from unittest.mock import patch

from model_release_assurance.export_poc import mechanism as m


class ExportPocMechanismTests(unittest.TestCase):
    def first(self):
        with patch.object(m.secrets, "randbelow", return_value=0):
            return m.first_release()

    def test_exact_channel_contract(self):
        checked = m.verify_exact_channels()
        self.assertEqual(checked["retained_answer_accuracy"], "11/15")
        self.assertEqual(checked["retained_history_ratio"], 4)
        self.assertEqual(checked["independent_history_ratio"], 4)

    def test_exact_bernoulli_boundaries_and_invalid_probability(self):
        with patch.object(m.secrets, "randbelow", return_value=3):
            self.assertTrue(m._truth(4, 5))
            self.assertFalse(m._truth(3, 5))
        for args in ((1, 0), (-1, 5), (6, 5), (True, 3), (2.0, 3)):
            with self.assertRaises(ValueError):
                m._truth(*args)

    def test_geometric_has_signed_unbounded_support_without_clipping(self):
        with patch.object(m.secrets, "randbelow", side_effect=[0] * 130 + [1, 1]):
            self.assertEqual(m._two_sided_geometric(), 130)
        with patch.object(m.secrets, "randbelow", side_effect=[1, 0, 0, 1]):
            self.assertEqual(m._two_sided_geometric(), -2)
        for k in range(-10, 11):
            mass = Fraction(1, 3) * Fraction(1, 2) ** abs(k)
            adjacent_mass = Fraction(1, 3) * Fraction(1, 2) ** abs(k - 1)
            self.assertLessEqual(mass / adjacent_mass, 2)
            self.assertLessEqual(adjacent_mass / mass, 2)

    def test_first_fits_from_protected_values_only(self):
        groups, xs, _ = m._fixture()
        values = [0] * len(xs)
        self.assertEqual(m._fit_perturbed(groups, values, Fraction(2, 3)),
                         {g: 0.0 for g in m.PUBLIC_GROUP_IDS})
        values = [1] * len(xs)
        self.assertEqual(m._fit_perturbed(groups, values, Fraction(2, 3)),
                         {g: 1.0 for g in m.PUBLIC_GROUP_IDS})
        state, artifact, certificate = self.first()
        parsed = m.inspect_bundle(artifact)
        self.assertEqual(parsed["guarantee"]["history_ratio"], 2)
        self.assertEqual(state["first_bundle_sha256"], hashlib.sha256(artifact).hexdigest())
        self.assertEqual(certificate["history_ratio"], 2)
        self.assertNotIn("X", parsed)
        self.assertNotIn("A", parsed)
        self.assertEqual(len(state["X"]), 512)

    def test_retained_route_uses_correct_conditional_sampler(self):
        # A is always flipped, so each second truth probability must be 3/5.
        with patch.object(m.secrets, "randbelow", return_value=2):
            state, _, _ = m.first_release()
        self.assertEqual(set(state["E"]), {1})
        with patch.object(m.secrets, "randbelow", return_value=3):
            extended, artifact, certificate = m.next_release(state, "retained-state")
        self.assertEqual(extended["B"], [1 - y for y in state["Y"]])
        self.assertEqual(m.inspect_bundle(artifact)["stage"], 2)
        self.assertEqual(certificate["history_ratio"], 4)
        # Without flips, draw 3 is truthful under the required 4/5 rule.
        state, _, _ = self.first()
        with patch.object(m.secrets, "randbelow", return_value=3):
            extended, _, _ = m.next_release(state, "retained-state")
        self.assertEqual(extended["B"], state["Y"])

    def test_all_routes_keep_parent_and_do_not_mutate_first_state(self):
        state, first, _ = self.first()
        before = copy.deepcopy(state)
        for route in m.ROUTES:
            with patch.object(m.secrets, "randbelow", return_value=1):
                updated, artifact, certificate = m.next_release(state, route)
            parsed = m.inspect_bundle(artifact)
            self.assertEqual(state, before)
            self.assertEqual(parsed["parent_artifact_sha256"], hashlib.sha256(first).hexdigest())
            self.assertEqual(certificate["first_artifact_sha256"], hashlib.sha256(first).hexdigest())
            self.assertEqual(parsed["guarantee"]["history_ratio"], 4)
            self.assertEqual(certificate["route"], route)
            with self.assertRaises(ValueError):
                m.next_release(updated, route)

    def test_central_count_is_strong_sufficient_statistic_baseline(self):
        state, _, _ = self.first()
        with patch.object(m, "_two_sided_geometric", return_value=0):
            _, artifact, _ = m.next_release(state, "central-count")
        parsed = m.inspect_bundle(artifact)
        groups, _, ys = m._fixture()
        for group in m.PUBLIC_GROUP_IDS:
            truth = sum(y for g, y in zip(groups, ys) if g == group) / m.PEOPLE_PER_GROUP
            self.assertEqual(parsed["model"]["probabilities"][group], truth)
        self.assertGreaterEqual(m.public_fixture_evaluation(artifact)["group_count_mae"], 0)
        with patch.object(m, "_two_sided_geometric", return_value=-1000):
            updated, artifact, _ = m.next_release(state, "central-count")
        self.assertLess(max(updated["noisy_counts"].values()), 0)
        self.assertEqual(set(m.inspect_bundle(artifact)["model"]["probabilities"].values()), {0.0})

    def test_reject_external_or_inconsistent_private_state(self):
        state, _, _ = self.first()
        changes = [
            lambda s: s.update(stage=2),
            lambda s: s.update(first_bundle_sha256="0" * 64),
            lambda s: s["X"].__setitem__(0, 1 - s["X"][0]),
            lambda s: s["E"].__setitem__(0, 1 - s["E"][0]),
            lambda s: s["A"].__setitem__(0, True),
            lambda s: s["A"].pop(),
            lambda s: s["groups"].__setitem__(0, "external_group"),
            lambda s: s.update(seed=123),
        ]
        for change in changes:
            bad = copy.deepcopy(state)
            change(bad)
            with self.assertRaises(ValueError):
                m.next_release(bad, "retained-state")
        with self.assertRaises(ValueError):
            m.next_release(state, "unknown")

    def test_export_allowlist_rejects_private_payloads_and_false_metadata(self):
        _, artifact, _ = self.first()
        clean = m.inspect_bundle(artifact)
        changes = [
            lambda v: v.update(raw_records=[1, 0]),
            lambda v: v["model"].update(noise_seed=123),
            lambda v: v["preprocessing"].update(private_vocabulary=["person"]),
            lambda v: v["guarantee"].update(history_ratio=1),
            lambda v: v["guarantee"].update(delta=False),
            lambda v: v.update(stage=True),
            lambda v: v["model"]["probabilities"].update(group_0=float("nan")),
            lambda v: v["model"]["probabilities"].update(group_0=True),
            lambda v: v["model"]["probabilities"].update(group_0=10 ** 1000),
        ]
        for change in changes:
            bad = copy.deepcopy(clean)
            change(bad)
            with self.assertRaises(ValueError):
                m.inspect_bundle(json.dumps(bad).encode())
        with self.assertRaises(ValueError):
            m.inspect_bundle(b'{"schema":"one","schema":"two"}')
        with self.assertRaises(ValueError):
            m.inspect_bundle(b"x" * 16385)

    def test_evaluation_is_explicitly_separate_public_holdout(self):
        _, artifact, _ = self.first()
        result = m.public_fixture_evaluation(artifact)
        self.assertIn("public synthetic", result["scope"])
        self.assertIn("separate", result["scope"])
        self.assertEqual(result["target"], "period1")
        self.assertTrue(0 <= result["brier_score"] <= 1)
        self.assertEqual(result["citizens"], 2048)
        self.assertEqual(result, m.public_fixture_evaluation(artifact))
        reuse = m.public_fixture_evaluation(artifact, target="period2")
        self.assertEqual(reuse["target"], "period2")
        self.assertNotEqual(reuse["brier_score"], result["brier_score"])
        with self.assertRaises(ValueError):
            m.public_fixture_evaluation(artifact, target="external")


if __name__ == "__main__":
    unittest.main()
