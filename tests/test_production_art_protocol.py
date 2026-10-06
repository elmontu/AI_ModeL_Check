"""Independent loss-oracle preparation, group splits and score replay checks."""
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
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes, parse_plan
from model_release_assurance.production_evidence import replay
from model_release_assurance.production_registration.profiles import load_profile, PROFILE_IDS
from model_release_assurance.production_art import protocol


def sklearn_repetitions(prepared, name):
    """Independent sklearn reference; this deliberately does not claim ART ran."""
    result = []
    labels = np.asarray(prepared["membership_labels"])
    losses = np.asarray(protocol.loss_features_float32(prepared["cases"][name]["loss_values"]), dtype=np.float32)
    for split in protocol.frozen_splits(prepared):
        order = ([i for i in split["train_indices"] if labels[i] == 1]
                 + [i for i in split["train_indices"] if labels[i] == 0])
        train = np.column_stack([losses[order], np.zeros(len(order), dtype=np.float32)])
        test = np.column_stack([losses[split["test_indices"]], np.zeros(len(split["test_indices"]), dtype=np.float32)])
        scaler = StandardScaler().fit(train)
        model = LogisticRegression(C=1, solver="lbfgs", max_iter=500, random_state=20261006).fit(scaler.transform(train), labels[order])
        result.append({**split, "member_probabilities": model.predict_proba(scaler.transform(test))[:, 1].tolist(),
            "loss_features_float32": losses.tolist(), "learned": {"classes": [0, 1], "coef": model.coef_[0].tolist(),
                "intercept": float(model.intercept_[0]), "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist(), "n_iter": int(model.n_iter_[0])}})
    return result


class ArtProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="art-protocol-")
        cls.root = Path(cls.workspace.name)
        cls.bundles = {}
        for name in ("sklearn-wine", "sklearn-diabetes"):
            data = load_profile(name, max_rows=128)
            destination = cls.root / name
            native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"], source_sha256=data["source_sha256"],
                feature_names=data["feature_names"], task=data["task"], output=destination)
            cls.bundles[name] = replay.snapshot_native_bundle(destination)
        data = load_profile("sklearn-wine", max_rows=128)
        x = np.concatenate((data["x"], data["x"][:12]))
        y = np.concatenate((data["y"], (data["y"][:12] + 1) % 3))
        destination = cls.root / "conflicting-groups"
        native.run_native(x, y, dataset_id=data["dataset_id"], source_sha256=data["source_sha256"],
            feature_names=data["feature_names"], output=destination)
        cls.bundles["duplicates"] = replay.snapshot_native_bundle(destination)
        cls.prepared = protocol.prepare_input(cls.bundles["sklearn-wine"])
        cls.regression = protocol.prepare_input(cls.bundles["sklearn-diabetes"])
        cls.repetitions = {name: sklearn_repetitions(cls.prepared, name) for name in protocol.CASES}

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def rejected(self, value):
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_input(value)

    def test_eight_profile_catalog_and_regression_are_explicitly_scoped(self):
        self.assertEqual(protocol.SUPPORTED_PROFILES, PROFILE_IDS)
        self.assertEqual(self.regression["task"], "regression")
        self.assertEqual(self.regression["classes"], [])
        self.assertEqual(self.regression["cases"]["target"]["native_score_definition"], "mean_squared_error_per_feature_group")
        self.assertEqual(self.prepared["protocol"]["attack_interface"], "precomputed_group_mean_loss_oracle")
        self.assertEqual(self.prepared["protocol"]["target_label_feature"], "constant_zero_not_target_labels")

    def test_byte_bindings_and_original_native_metrics_retained(self):
        data, blobs = self.prepared, self.bundles["sklearn-wine"]
        for field, filename in (("plan_sha256", "plan.json"), ("candidate_sha256", "candidate.json"), ("data_sha256", "dataset.json")):
            self.assertEqual(data[field], hashlib.sha256(blobs[filename]).hexdigest())
        self.assertEqual(data["artifacts_sha256"], hashlib.sha256(canonical_bytes(replay.artifact_manifest(blobs))).hexdigest())
        original = json.loads(blobs["report.json"])
        self.assertEqual(data["native_full_run_metrics"], {key:original[key] for key in data["native_full_run_metrics"]})

    def test_preparation_never_fits_target_or_loads_models(self):
        from sklearn.naive_bayes import GaussianNB
        with mock.patch.object(native, "run_native", side_effect=AssertionError("fit")), \
             mock.patch.object(GaussianNB, "fit", side_effect=AssertionError("fit")), \
             mock.patch.object(native, "_read", side_effect=AssertionError("file read")):
            self.assertEqual(protocol.prepare_input(self.bundles["sklearn-wine"]), self.prepared)

    def test_conflicting_labels_keep_mean_loss_and_single_group_trial(self):
        blobs = self.bundles["duplicates"]
        data = protocol.prepare_input(blobs)
        plan = parse_plan(blobs["plan.json"])
        raw = json.loads(blobs["dataset.json"])
        scores = native._row_scores(native.replay_candidate(blobs["candidate.json"], raw["x"]), np.asarray(raw["y"]), "classification", data["classes"])
        self.assertGreater(plan.conflicting_label_groups, 0)
        self.assertEqual((data["row_count"], data["group_count"]), (140, 128))
        for index, group in enumerate(data["group_ids"]):
            expected = -float(np.mean(scores[plan.groups[group].rows]))
            self.assertAlmostEqual(data["cases"]["target"]["loss_values"][index], expected)

    def test_synthetic_positive_and_null_losses_are_exact(self):
        labels = self.prepared["membership_labels"]
        self.assertEqual(self.prepared["cases"]["positive"]["loss_values"], [0. if value else 1. for value in labels])
        self.assertEqual(self.prepared["cases"]["null"]["loss_values"], [1.] * len(labels))
        for name, expected in (("positive", 1.), ("null", .5)):
            self.assertEqual(protocol.rank_auc(labels, self.prepared["cases"][name]["native_loss_scores"]), expected)

    def test_prepared_inputs_are_owned(self):
        owned = protocol.validate_input(self.prepared)
        owned["cases"]["target"]["loss_values"][0] = 999.
        self.assertNotEqual(owned, self.prepared)
        caller = dict(self.bundles["sklearn-wine"])
        actual = protocol.replay_native_bundle
        def mutation(captured):
            caller["candidate.json"] = b"changed"
            return actual(captured)
        with mock.patch.object(protocol, "replay_native_bundle", side_effect=mutation):
            self.assertEqual(protocol.prepare_input(caller), self.prepared)

    def test_flags_cannot_grant_authority(self):
        for flag, expected in protocol.FLAGS.items():
            with self.subTest(flag=flag):
                self.assertIs(self.prepared[flag], expected)
                data = copy.deepcopy(self.prepared); data[flag] = not expected; self.rejected(data)

    def test_profile_pins_and_task_cannot_be_restamped(self):
        for key, value in (("source_sha256", "f"*64), ("profile_id", "unknown"), ("task", "regression"), ("schema", "other")):
            data = copy.deepcopy(self.prepared); data[key] = value; self.rejected(data)

    def test_exact_contract_rejects_missing_and_extra_fields(self):
        data = copy.deepcopy(self.prepared); data["extra"] = False; self.rejected(data)
        data = copy.deepcopy(self.prepared); del data["protocol"]; self.rejected(data)
        data = copy.deepcopy(self.prepared); del data["cases"]["null"]; self.rejected(data)

    def test_loss_bounds_and_direction_must_match(self):
        for value in (True, float("nan"), float("inf"), -1., 1e31):
            data = copy.deepcopy(self.prepared); data["cases"]["target"]["loss_values"][0] = value; self.rejected(data)
        data = copy.deepcopy(self.prepared); data["cases"]["target"]["native_loss_scores"][0] -= 1.; self.rejected(data)
        data = copy.deepcopy(self.prepared); data["cases"]["null"]["loss_values"][0] = 0.; self.rejected(data)

    def test_membership_labels_and_unique_group_coverage_required(self):
        for key, value in (("membership_labels", [True] + self.prepared["membership_labels"][1:]),
                           ("group_ids", [0] * self.prepared["group_count"]), ("member_group_count", 19)):
            data = copy.deepcopy(self.prepared); data[key] = value; self.rejected(data)

    def test_corrupted_artifacts_and_unknown_registration_rejected(self):
        with self.assertRaises(protocol.ProtocolError):
            protocol.prepare_input({**self.bundles["sklearn-wine"], "candidate.json": b"{}"})
        with self.assertRaises(protocol.ProtocolError):
            protocol.prepare_input({**self.bundles["sklearn-wine"], "extra.json": b"{}"})
        plan = parse_plan(self.bundles["sklearn-wine"]["plan.json"])
        with self.assertRaises(protocol.UnsupportedProfile):
            protocol._profile(plan.model_copy(update={"dataset_id": "unknown"}))

    def test_fixed_stratified_splits_partition_each_group_without_tuning(self):
        splits = protocol.frozen_splits(self.prepared)
        self.assertEqual([split["seed"] for split in splits], [20261006, 20261007, 20261008])
        for split in splits:
            self.assertFalse(set(split["train_indices"]) & set(split["test_indices"]))
            self.assertEqual(sorted(split["train_indices"] + split["test_indices"]), list(range(self.prepared["group_count"])))
            self.assertEqual(set(split["membership_labels"]), {0, 1})
        self.assertNotEqual(splits[0]["test_indices"], splits[1]["test_indices"])

    def test_float32_features_preserve_declared_art_precision(self):
        values = [0.12345678912345, 1.]
        self.assertEqual(protocol.loss_features_float32(values), np.asarray(values, dtype=np.float32).tolist())
        self.assertNotEqual(protocol.loss_features_float32(values)[0], values[0])
        for bad in ([1e40, 1.], [True, 1.], [1., float("inf")]):
            with self.assertRaises(protocol.ProtocolError):
                protocol.loss_features_float32(bad)

    def test_independent_auc_ties_direction_and_cutoff(self):
        self.assertEqual(protocol.rank_auc([1, 0], [0., 1.]), 0.)
        self.assertEqual(protocol.rank_auc([1, 0], [1e25, 1e25]), .5)
        metric = protocol.membership_metrics([1, 0], [.5, .5])
        self.assertEqual((metric["true_positives"], metric["false_positives"], metric["raw_auc"]), (0, 0, .5))

    def test_retained_target_scores_replayed_from_independent_sklearn_head(self):
        report = protocol.compare_repetitions(self.prepared, "target", self.repetitions["target"])
        self.assertEqual(report["status"], "completed")
        self.assertIsNone(report["controls_satisfied"])
        self.assertEqual(len(report["repetitions"]), 3)
        self.assertEqual(report["summary"]["auc_uncertainty"], "not_estimated")
        self.assertTrue(report["summary"]["repetitions_are_not_independent_samples"])
        self.assertTrue(all(row["scores_replayed"] for row in report["repetitions"]))

    def test_synthetic_controls_train_the_learner_path(self):
        for name, auc in (("positive", 1.), ("null", .5)):
            report = protocol.compare_repetitions(self.prepared, name, self.repetitions[name])
            self.assertTrue(report["controls_satisfied"])
            self.assertEqual(report["summary"]["attack_raw_auc_mean"], auc)

    def test_balanced_null_initial_optimizer_optimum_is_valid(self):
        repetitions = self.repetitions["null"]
        initial = [row for row in repetitions if row["learned"]["n_iter"] == 0]
        self.assertTrue(initial)
        for row in initial:
            self.assertTrue(all(value == .5 for value in row["member_probabilities"]))
        report = protocol.compare_repetitions(self.prepared, "null", repetitions)
        self.assertTrue(report["controls_satisfied"])
        self.assertEqual(report["summary"]["attack_raw_auc_mean"], .5)

    def test_regression_same_loss_interface_and_independent_head_replay(self):
        repetitions = sklearn_repetitions(self.regression, "target")
        report = protocol.compare_repetitions(self.regression, "target", repetitions)
        self.assertEqual(report["task"], "regression")
        self.assertTrue(all(row["scores_replayed"] for row in report["repetitions"]))

    def test_repeat_count_or_selection_cannot_change(self):
        for value in (self.repetitions["target"][:2], self.repetitions["target"] + self.repetitions["target"][:1],
                      list(reversed(self.repetitions["target"]))):
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", value)

    def test_wrong_indices_or_membership_labels_rejected(self):
        for key in ("train_indices", "test_indices", "membership_labels"):
            repetitions = copy.deepcopy(self.repetitions["target"])
            repetitions[0][key][0] = 999
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)

    def test_caller_forged_probabilities_rejected_by_logistic_replay(self):
        for value in (True, float("nan"), 2., .12345):
            repetitions = copy.deepcopy(self.repetitions["target"])
            repetitions[0]["member_probabilities"][0] = value
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)

    def test_scaler_moments_independently_validated(self):
        for key in ("scaler_mean", "scaler_scale"):
            repetitions = copy.deepcopy(self.repetitions["target"])
            repetitions[0]["learned"][key][0] += .1
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)

    def test_zero_label_channel_cannot_contain_signal(self):
        for key, value in (("coef", 1.), ("scaler_mean", 1.), ("scaler_scale", 2.)):
            repetitions = copy.deepcopy(self.repetitions["target"])
            repetitions[0]["learned"][key][1] = value
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)

    def test_learned_class_order_convergence_and_finite_bounds(self):
        for key, value in (("classes", [1, 0]), ("classes", [False, True]), ("n_iter", 500),
                           ("n_iter", True), ("intercept", float("inf")), ("coef", [1e7, 0.])):
            repetitions = copy.deepcopy(self.repetitions["target"])
            repetitions[0]["learned"][key] = value
            with self.assertRaises(protocol.ProtocolError):
                protocol.compare_repetitions(self.prepared, "target", repetitions)

    def test_exact_float32_feature_binding_rejects_nonmember_changes(self):
        repetitions = copy.deepcopy(self.repetitions["target"])
        repetitions[0]["loss_features_float32"][-1] += .01
        with self.assertRaises(protocol.ProtocolError):
            protocol.compare_repetitions(self.prepared, "target", repetitions)

    def test_missing_replay_or_unknown_case_rejected(self):
        repetitions = copy.deepcopy(self.repetitions["target"])
        del repetitions[0]["learned"]
        with self.assertRaises(protocol.ProtocolError):
            protocol.compare_repetitions(self.prepared, "target", repetitions)
        with self.assertRaises(protocol.ProtocolError):
            protocol.compare_repetitions(self.prepared, "extraction", self.repetitions["target"])

    def test_outputs_deep_owned_and_do_not_change_original_scores(self):
        original = copy.deepcopy(self.repetitions["target"])
        result = protocol.compare_repetitions(self.prepared, "target", self.repetitions["target"])
        result["native_full_run_metrics"]["membership"]["raw_auc"] = -1.
        self.assertEqual(self.repetitions["target"], original)
        self.assertGreaterEqual(self.prepared["native_full_run_metrics"]["membership"]["raw_auc"], 0.)

if __name__ == "__main__":
    unittest.main()
