"""Public scalar/group preparation and independent SACRO metric checks."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from sklearn.model_selection import train_test_split

from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes, parse_plan
from model_release_assurance.production_evidence import replay
from model_release_assurance.production_registration.profiles import load_profile
from model_release_assurance.production_sacro import protocol


def pairwise_auc(labels, values):
    positive = [score for label, score in zip(labels, values) if label == 1]
    negative = [score for label, score in zip(labels, values) if label == 0]
    return sum(1. if a > b else .5 if a == b else 0. for a in positive for b in negative) / (len(positive) * len(negative))


class SacroProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="sacro-protocol-")
        cls.root = Path(cls.workspace.name)
        cls.bundles = {}
        for profile in ("sklearn-wine", "sklearn-diabetes"):
            data = load_profile(profile, max_rows=128)
            output = cls.root / profile
            receipt = native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"], source_sha256=data["source_sha256"],
                feature_names=data["feature_names"], task=data["task"], output=output)
            if receipt["status"] != "completed":
                raise AssertionError(receipt)
            cls.bundles[profile] = replay.snapshot_native_bundle(output)
        # Deliberately engineered PUBLIC test fixture for duplicate/conflicting
        # labels. The plan's profile label is not an upstream-provenance claim.
        data = load_profile("sklearn-wine", max_rows=128)
        x = np.concatenate((data["x"], data["x"][:12], data["x"][:1]))
        y = np.concatenate((data["y"], (data["y"][:12] + 1) % 3, data["y"][:1]))
        output = cls.root / "duplicate-group-fixture"
        receipt = native.run_native(x, y, dataset_id=data["dataset_id"], source_sha256=data["source_sha256"],
            feature_names=data["feature_names"], task="classification", output=output)
        if receipt["status"] != "completed":
            raise AssertionError(receipt)
        cls.bundles["duplicates"] = replay.snapshot_native_bundle(output)
        cls.prepared = protocol.prepare_input(cls.bundles["sklearn-wine"])

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def repetitions(self, name="target"):
        result = []
        for split in protocol.frozen_splits(self.prepared):
            labels = split["membership_labels"]
            values = ([.95 if label else .05 for label in labels] if name == "positive"
                      else [.5] * len(labels) if name == "null"
                      else [((index * 13) % 101) / 100. for index in split["test_indices"]])
            result.append({**split, "member_probabilities": values, "upstream_auc": round(pairwise_auc(labels, values), 8)})
        return result

    def test_preparation_binds_exact_artifacts_and_preserves_native_metrics(self):
        data = protocol.prepare_input(self.bundles["sklearn-wine"])
        self.assertEqual(data["schema"], "mra-sacro-comparison-input/v1")
        self.assertEqual((data["status"], data["profile_id"], data["task"]), ("prepared", "sklearn-wine", "classification"))
        self.assertEqual(data["artifacts_sha256"], hashlib.sha256(canonical_bytes(replay.artifact_manifest(self.bundles["sklearn-wine"]))).hexdigest())
        for field, filename in (("plan_sha256", "plan.json"), ("candidate_sha256", "candidate.json"), ("data_sha256", "dataset.json")):
            self.assertEqual(data[field], hashlib.sha256(self.bundles["sklearn-wine"][filename]).hexdigest())
        report = json.loads(self.bundles["sklearn-wine"]["report.json"])
        self.assertEqual(data["native_full_run_metrics"], {key:report[key] for key in data["native_full_run_metrics"]})
        self.assertEqual(len(protocol.SUPPORTED_PROFILES), 7)
        self.assertNotIn("sklearn-diabetes", protocol.SUPPORTED_PROFILES)
        for field in ("can_clear", "authorization_eligible", "production_authorized", "model_delivery",
                      "hostile_code_isolated", "network_isolated"):
            self.assertIs(data[field], False)

    def test_preparation_never_refits_target_or_reads_artifact_paths(self):
        from sklearn.naive_bayes import GaussianNB
        with mock.patch.object(native, "run_native", side_effect=AssertionError("new fit")), \
             mock.patch.object(GaussianNB, "fit", side_effect=AssertionError("new estimator fit")), \
             mock.patch.object(native, "_read", side_effect=AssertionError("artifact path read")):
            self.assertEqual(protocol.prepare_input(self.bundles["sklearn-wine"]), self.prepared)

    def test_members_first_fixed_group_order_and_probability_shape(self):
        data = self.prepared
        plan = parse_plan(self.bundles["sklearn-wine"]["plan.json"])
        self.assertEqual(data["group_ids"], plan.train_groups + plan.calibration_groups + plan.audit_groups)
        self.assertEqual(data["membership_labels"], [1] * len(plan.train_groups) + [0] * (len(plan.calibration_groups) + len(plan.audit_groups)))
        for case in data["cases"].values():
            self.assertEqual(len(case["probabilities"]), data["group_count"])
            self.assertEqual(len(case["native_loss_scores"]), data["group_count"])
            for vector in case["probabilities"]:
                self.assertEqual(len(vector), len(data["classes"]))
                self.assertTrue(all(type(value) is float for value in vector))
                self.assertAlmostEqual(math.fsum(vector), 1.)

    def test_duplicate_rows_contribute_once_and_conflicting_loss_is_averaged(self):
        blobs = self.bundles["duplicates"]
        data = protocol.prepare_input(blobs)
        plan = parse_plan(blobs["plan.json"])
        raw = json.loads(blobs["dataset.json"])
        scores = native._row_scores(native.replay_candidate(blobs["candidate.json"], raw["x"]),
                                   np.asarray(raw["y"]), "classification", data["classes"])
        self.assertEqual((data["row_count"], data["group_count"]), (141, 128))
        self.assertGreater(plan.conflicting_label_groups, 0)
        for index, group_id in enumerate(data["group_ids"]):
            values = scores[plan.groups[group_id].rows]
            expected = float(values[0]) if np.all(values == values[0]) else float(np.mean(values))
            self.assertEqual(data["cases"]["target"]["native_loss_scores"][index], expected)
        self.assertEqual(sum(data["membership_labels"]), len(plan.train_groups))

    def test_controls_have_same_group_counts_and_exact_synthetic_class_zero_scores(self):
        data = self.prepared
        classes = len(data["classes"])
        uniform = [1/classes] * classes
        concentrated = [.99] + [(1-.99)/(classes-1)] * (classes-1)
        for index, label in enumerate(data["membership_labels"]):
            self.assertEqual(data["cases"]["positive"]["probabilities"][index], concentrated if label else uniform)
            self.assertEqual(data["cases"]["null"]["probabilities"][index], uniform)
        self.assertEqual(protocol.rank_auc(data["membership_labels"], data["cases"]["positive"]["native_loss_scores"]), 1.)
        self.assertEqual(protocol.rank_auc(data["membership_labels"], data["cases"]["null"]["native_loss_scores"]), .5)
        self.assertEqual(data["cases"]["positive"]["native_score_definition"], "log_synthetic_class_zero_probability")

    def test_preparation_and_validation_deep_own_inputs(self):
        original = dict(self.bundles["sklearn-wine"])
        bundle = dict(original)
        actual_replay = protocol.replay_native_bundle
        def mutate_caller(captured):
            bundle["candidate.json"] = b"changed caller mapping"
            return actual_replay(captured)
        with mock.patch.object(protocol, "replay_native_bundle", side_effect=mutate_caller):
            prepared = protocol.prepare_input(bundle)
        self.assertEqual(prepared, self.prepared)
        prepared["cases"]["target"]["probabilities"][0][0] = -1.
        self.assertNotEqual(prepared, self.prepared)
        copy_result = protocol.validate_input(self.prepared)
        copy_result["native_full_run_metrics"]["membership"]["raw_auc"] = -1.
        self.assertGreaterEqual(self.prepared["native_full_run_metrics"]["membership"]["raw_auc"], 0.)

    def test_regression_rejected_before_comparison_preparation(self):
        with self.assertRaises(protocol.UnsupportedProfile) as raised:
            protocol.prepare_input(self.bundles["sklearn-diabetes"])
        self.assertEqual(raised.exception.code, "regression_not_supported")
        with mock.patch.object(protocol, "replay_native_bundle", side_effect=AssertionError("must replay before classification decision")):
            with self.assertRaises(protocol.ProtocolError):
                protocol.prepare_input(self.bundles["sklearn-diabetes"])

    def test_unknown_profile_is_explicitly_unsupported(self):
        plan = parse_plan(self.bundles["sklearn-wine"]["plan.json"])
        with self.assertRaises(protocol.UnsupportedProfile) as raised:
            protocol._profile(plan.model_copy(update={"dataset_id": "unregistered-fixture"}))
        self.assertEqual(raised.exception.code, "unregistered_profile")
        with self.assertRaises(protocol.UnsupportedProfile):
            protocol._profile(plan.model_copy(update={"source_sha256": "f"*64}))

    def test_changed_artifact_extra_bundle_and_consistently_restamped_metric_rejected(self):
        for value in ({**self.bundles["sklearn-wine"], "extra.json": b"{}"},
                      {**self.bundles["sklearn-wine"], "candidate.json": b"{}"}):
            with self.assertRaises(protocol.ProtocolError):
                protocol.prepare_input(value)
        blobs = dict(self.bundles["sklearn-wine"])
        report = json.loads(blobs["report.json"])
        report["utility"]["accuracy"] = report["utility"]["accuracy"] - .01
        blobs["report.json"] = canonical_bytes(report) + b"\n"
        receipt = json.loads(blobs["result.json"])
        receipt["files"]["report.json"] = hashlib.sha256(blobs["report.json"]).hexdigest()
        receipt["utility"] = report["utility"]
        blobs["result.json"] = canonical_bytes(receipt) + b"\n"
        with self.assertRaises(protocol.ProtocolError):
            protocol.prepare_input(blobs)

    def test_independent_rank_auc_ties_direction_and_strict_probability_cutoff(self):
        labels, scores = [1, 0, 1, 0], [.9, .9, .2, .1]
        with mock.patch("sklearn.metrics.roc_auc_score", side_effect=AssertionError("not independent")):
            self.assertEqual(protocol.rank_auc(labels, scores), .625)
            self.assertEqual(protocol.rank_auc(labels, [-value for value in scores]), .375)
            self.assertEqual(protocol.rank_auc(labels, [.5]*4), .5)
        metric = protocol.membership_metrics([1,1,0,0], [.5,.6,.5,.9])
        self.assertEqual((metric["true_positives"],metric["false_positives"],metric["true_negatives"],metric["false_negatives"]), (1,1,1,1))
        inverted = protocol.membership_metrics([1,1,0,0], [0.,0.,1.,1.])
        self.assertEqual((inverted["raw_auc"], inverted["symmetric_auc"]), (0.,1.))

    def test_scalar_metrics_reject_nonfinite_bool_nested_and_misaligned_values(self):
        for probabilities in ([True, .5], [float("nan"), .5], [float("inf"), .5], [[.2,.8],[.6,.4]], [-.1,.5], [1.1,.5], [.5], [".1",.5]):
            with self.subTest(values=probabilities), self.assertRaises(protocol.ProtocolError):
                protocol.membership_metrics([1,0], probabilities)
        for labels in ([True,0], [1.,0.], [1,1], [0,0], [2,0], [], [1,0,1]):
            with self.subTest(labels=labels), self.assertRaises(protocol.ProtocolError):
                protocol.membership_metrics(labels, [.5,.5])
        with self.assertRaises(protocol.ProtocolError):
            protocol.rank_auc([1,0], [1e13, 0.])

    def test_frozen_splits_exact_upstream_algorithm_disjoint_and_deterministic(self):
        splits = protocol.frozen_splits(self.prepared)
        self.assertEqual(splits, protocol.frozen_splits(copy.deepcopy(self.prepared)))
        self.assertEqual([split["seed"] for split in splits], [20261001,20261002,20261003])
        for split in splits:
            train, test = train_test_split(np.arange(self.prepared["group_count"]), test_size=.5,
                stratify=self.prepared["membership_labels"], random_state=split["seed"], shuffle=True)
            self.assertEqual(split["train_indices"], train.tolist())
            self.assertEqual(split["test_indices"], test.tolist())
            self.assertFalse(set(train) & set(test))
            self.assertEqual(sorted(list(train)+list(test)), list(range(self.prepared["group_count"])))
            self.assertEqual(split["membership_labels"], [self.prepared["membership_labels"][int(index)] for index in test])
        self.assertEqual(len({tuple(split["test_indices"]) for split in splits}), 3)
        splits[0]["test_indices"][0] = -1
        self.assertNotEqual(splits, protocol.frozen_splits(self.prepared))

    def test_comparison_independently_recomputes_paired_same_group_auc(self):
        repetitions = self.repetitions()
        comparison = protocol.compare_repetitions(self.prepared, "target", repetitions)
        self.assertEqual(comparison["status"], "completed")
        self.assertIsNone(comparison["controls_satisfied"])
        for actual, source in zip(comparison["repetitions"], repetitions):
            labels = source["membership_labels"]
            native_scores = [self.prepared["cases"]["target"]["native_loss_scores"][index] for index in source["test_indices"]]
            native_auc = pairwise_auc(labels, native_scores)
            attack_auc = pairwise_auc(labels, source["member_probabilities"])
            self.assertEqual(actual["native_loss"]["raw_auc"], native_auc)
            self.assertEqual(actual["attack"]["raw_auc"], attack_auc)
            self.assertEqual(actual["paired_raw_auc_difference"], attack_auc-native_auc)
            self.assertEqual(actual["attack"]["member_count"], sum(labels))
            self.assertEqual(actual["attack"]["total"], len(labels))
            self.assertEqual(actual["test_indices_sha256"], hashlib.sha256(canonical_bytes(source["test_indices"])).hexdigest())
        self.assertEqual(comparison["native_full_run_metrics"], self.prepared["native_full_run_metrics"])
        self.assertEqual(comparison["summary"]["auc_uncertainty"], "not_estimated")
        self.assertIs(comparison["summary"]["repetitions_are_not_independent_samples"], True)
        self.assertFalse(comparison["authorization_eligible"])
        comparison["repetitions"][0]["attack"]["raw_auc"] = -1.
        self.assertNotEqual(comparison, protocol.compare_repetitions(self.prepared, "target", repetitions))

    def test_upstream_eight_decimal_rounding_keeps_independent_full_precision(self):
        repetitions = self.repetitions()
        raw = [pairwise_auc(row["membership_labels"], row["member_probabilities"]) for row in repetitions]
        self.assertTrue(any(abs(value-round(value,8)) > 1e-12 for value in raw))
        result = protocol.compare_repetitions(self.prepared, "target", repetitions)
        self.assertEqual([row["attack"]["raw_auc"] for row in result["repetitions"]], raw)
        changed = copy.deepcopy(repetitions)
        changed[0]["upstream_auc"] += 1e-8
        with self.assertRaises(protocol.ProtocolError):
            protocol.compare_repetitions(self.prepared, "target", changed)

    def test_positive_null_controls_pass_without_orienting_inverted_attack(self):
        for name in ("positive", "null"):
            result = protocol.compare_repetitions(self.prepared, name, self.repetitions(name))
            self.assertIs(result["controls_satisfied"], True)
            self.assertEqual(result["summary"]["native_loss_raw_auc_mean"], 1. if name == "positive" else .5)
        inverted = self.repetitions("positive")
        for row in inverted:
            row["member_probabilities"] = [1.-value for value in row["member_probabilities"]]
            row["upstream_auc"] = 0.
        result = protocol.compare_repetitions(self.prepared, "positive", inverted)
        self.assertIs(result["controls_satisfied"], False)
        self.assertEqual(result["summary"]["attack_raw_auc_mean"], 0.)
        self.assertEqual(result["repetitions"][0]["attack"]["symmetric_auc"], 1.)

    def test_repetition_seed_indices_labels_reported_metrics_and_shape_bound(self):
        original = self.repetitions()
        edits = [lambda row: row.update(seed=42), lambda row: row["test_indices"].reverse(),
            lambda row: row["train_indices"].reverse(), lambda row: row["membership_labels"].reverse(),
            lambda row: row.update(upstream_auc=(row["upstream_auc"]+.1) % 1.),
            lambda row: row.update(member_probabilities=[[1-value,value] for value in row["member_probabilities"]]),
            lambda row: row.update(extra="forbidden"), lambda row: row.update(seed=float(row["seed"])),
            lambda row: row["membership_labels"].__setitem__(0, bool(row["membership_labels"][0]))]
        for change in edits:
            repetitions = copy.deepcopy(original)
            change(repetitions[0])
            with self.subTest(change=change), self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)
        for repetitions in (original[:2], original+[original[0]], list(reversed(original))):
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)
        with self.assertRaises(protocol.ProtocolError):
            protocol.compare_repetitions(self.prepared, "unknown", original)

    def test_prepared_contract_rejects_weak_flags_unknown_fields_wrong_bounds_and_controls(self):
        edits = [lambda data: data.update(authorization_eligible=True), lambda data: data.update(extra=False),
            lambda data: data.update(group_count=4097), lambda data: data.update(member_group_count=19),
            lambda data: data.update(classes=list(range(33))), lambda data: data.update(classes=[True,1,2]),
            lambda data: data["classes"].reverse(), lambda data: data["group_ids"].__setitem__(0,data["group_ids"][1]),
            lambda data: data["membership_labels"].reverse(), lambda data: data.update(source_sha256="f"*64),
            lambda data: data.update(artifacts_sha256="not-a-digest"), lambda data: data["protocol"].update(test_fraction=.6),
            lambda data: data["cases"]["target"]["probabilities"][0].__setitem__(0,True),
            lambda data: data["cases"]["target"]["probabilities"][0].__setitem__(0,float("nan")),
            lambda data: data["cases"]["target"]["probabilities"].pop(),
            lambda data: data["cases"]["target"]["native_loss_scores"].pop(),
            lambda data: data["cases"]["positive"]["native_loss_scores"].__setitem__(0,-1.),
            lambda data: data["cases"]["null"]["probabilities"][0].__setitem__(0,.9),
            lambda data: data["native_full_run_metrics"].update(controls_passed=False)]
        for change in edits:
            data = copy.deepcopy(self.prepared)
            change(data)
            with self.subTest(change=change), self.assertRaises(protocol.ProtocolError):
                protocol.validate_input(data)

    def test_array_and_tuple_probabilities_never_silently_coerced(self):
        for value in (np.array(self.prepared["cases"]["target"]["probabilities"]),
                      tuple(self.prepared["cases"]["target"]["probabilities"])):
            data = copy.deepcopy(self.prepared)
            data["cases"]["target"]["probabilities"] = value
            with self.assertRaises(protocol.ProtocolError):
                protocol.validate_input(data)

    def test_deep_large_and_non_json_values_rejected_with_generic_error(self):
        nested = "do-not-echo"
        for _ in range(20):
            nested = [nested]
        for value in (nested, [0]*4097, "x"*16385, object(), 2**100):
            with self.assertRaises(protocol.ProtocolError) as raised:
                protocol._owned(value)
            self.assertNotIn("do-not-echo", str(raised.exception))
        for value in (10**1000, -(10**1000)):
            with self.assertRaises(protocol.ProtocolError):
                protocol.membership_metrics([1,0], [value,.5])


if __name__ == "__main__":
    unittest.main()
