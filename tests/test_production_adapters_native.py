"""Operational native adapters: inert replay, frozen splits and adversarial inputs."""
from __future__ import annotations

import copy
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError

from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import (
    NativeReport, canonical_bytes, parse_candidate, parse_plan, strict_json,
)


def examples(task="classification", count=240):
    rng = np.random.default_rng(194)
    x = rng.normal(size=(count, 6))
    y = (np.where(x[:, 0] < -.4, -2, np.where(x[:, 0] > .5, 11, 5))
         if task == "classification" else 3 * x[:, 0] - 2 * x[:, 1] + .01 * rng.normal(size=count))
    return x, y


def invoke(output, x=None, y=None, **kwargs):
    if x is None:
        x, y = examples(kwargs.get("task", "classification"))
    values = dict(dataset_id="synthetic-public-test", source_sha256="a" * 64,
                  feature_names=[f"feature_{index}" for index in range(x.shape[1])], output=output)
    values.update(kwargs)
    return native.run_native(x, y, **values)


def read(path):
    return strict_json(path.read_bytes())


def write(path, value):
    path.write_bytes(canonical_bytes(value) + b"\n")


class NativeAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="native-adapter-test-")
        cls.root = Path(cls.workspace.name)
        cls.classification = cls.root / "classification"
        cls.regression = cls.root / "regression"
        cls.result = invoke(cls.classification)
        cls.regression_result = invoke(cls.regression, task="regression")
        if cls.result["status"] != "completed" or cls.regression_result["status"] != "completed":
            raise AssertionError((cls.result, cls.regression_result))

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root, prefix="case-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"

    def copy_run(self, task="classification"):
        shutil.copytree(self.classification if task == "classification" else self.regression, self.output)
        return self.output

    def update_receipt_hash(self, name):
        receipt = read(self.output / "result.json")
        receipt["files"][name] = hashlib.sha256((self.output / name).read_bytes()).hexdigest()
        write(self.output / "result.json", receipt)

    def test_multiclass_exact_candidate_replay_and_nonclearance(self):
        result = self.result
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["controls"]["passed"])
        self.assertEqual(result["controls"]["positive_auc"], 1.)
        self.assertEqual(result["controls"]["null_auc"], .5)
        self.assertGreater(result["utility"]["accuracy"], .8)
        self.assertLess(result["reload_max_absolute_error"], 1e-10)
        x, _ = examples()
        raw = (self.classification / "candidate.json").read_bytes()
        candidate = parse_candidate(raw)
        self.assertEqual(candidate.model.classes, [-2, 5, 11])
        prediction = native.replay_candidate(raw, x)
        self.assertEqual(prediction.shape, (240, 3))
        np.testing.assert_allclose(prediction.sum(axis=1), 1.)
        self.assertEqual(native.replay_run(self.classification)["status"], "passed")
        for key in ("can_clear", "authorization_eligible", "production_authorized", "model_delivery",
                    "hostile_code_isolated", "network_isolated"):
            self.assertIs(result[key], False)

    def test_regression_exact_replay_utility_and_residual_controls(self):
        result = self.regression_result
        self.assertEqual(result["status"], "completed")
        self.assertLess(result["utility"]["rmse"], .1)
        self.assertGreater(result["utility"]["r2"], .99)
        self.assertEqual(result["controls"]["positive_auc"], 1.)
        self.assertEqual(result["controls"]["null_auc"], .5)
        plan = parse_plan((self.regression / "plan.json").read_bytes())
        self.assertEqual(plan.regression_control_targets, "synthetic-zero-targets-exact-zero-or-unit-residual")
        self.assertEqual(native.replay_run(self.regression)["status"], "passed")

    def test_preprocessing_uses_only_frozen_training_rows(self):
        x, _ = examples()
        plan = parse_plan((self.classification / "plan.json").read_bytes())
        candidate = parse_candidate((self.classification / "candidate.json").read_bytes())
        np.testing.assert_allclose(candidate.preprocessing.mean, x[plan.train_indices].mean(axis=0), rtol=0, atol=1e-15)
        self.assertFalse(np.allclose(candidate.preprocessing.mean, x.mean(axis=0)))
        self.assertFalse(set(plan.train_indices) & set(plan.audit_indices))
        self.assertFalse(set(plan.calibration_indices) & set(plan.audit_indices))

    def test_frozen_plan_precedes_only_fit_and_input_copies_are_owned(self):
        from sklearn.naive_bayes import GaussianNB
        x, y = examples()
        original_x = x.copy()
        fitted = GaussianNB.fit
        calls = []
        def observe(model, train_x, train_y, *args, **kwargs):
            self.assertTrue((self.output / "plan.json").is_file())
            self.assertFalse((self.output / "candidate.json").exists())
            calls.append(1)
            x[:] = 9999
            y[:] = 99
            return fitted(model, train_x, train_y, *args, **kwargs)
        with patch.object(GaussianNB, "fit", observe):
            result = invoke(self.output, x, y)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(calls), 1)
        np.testing.assert_array_equal(read(self.output / "dataset.json")["x"], original_x)

    def test_conflicting_duplicate_features_stay_in_whole_groups(self):
        base, _ = examples(count=100)
        counts = np.array([1 + index % 4 for index in range(len(base))])
        x = np.repeat(base, counts, axis=0)
        y = np.arange(len(x)) % 3
        result = invoke(self.output, x, y)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["duplicate_groups"], 75)
        self.assertEqual(result["conflicting_label_groups"], 75)
        self.assertEqual(result["controls"]["null_auc"], .5)
        plan = parse_plan((self.output / "plan.json").read_bytes())
        row_sets = [set(plan.train_indices), set(plan.calibration_indices), set(plan.audit_indices)]
        for group in plan.groups:
            self.assertEqual(sum(bool(set(group.rows) & rows) for rows in row_sets), 1)
        self.assertEqual(result["membership"]["member_group_trials"], 50)
        self.assertEqual(result["membership"]["nonmember_group_trials"], 25)

    def test_duplicate_signed_zero_is_one_group(self):
        # Public normalization is the authority before grouping.
        groups = native._groups(native._arrays(np.array([[0., -0.], [-0., 0.]])))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["rows"], [0, 1])

    def test_small_unique_group_count_is_unsupported_with_retained_plan(self):
        x, y = examples(count=40)
        result = invoke(self.output, x, y)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["reason"], "insufficient_unique_feature_groups")
        self.assertTrue((self.output / "plan.json").is_file())
        self.assertFalse((self.output / "candidate.json").exists())
        self.assertEqual(read(self.output / "result.json")["status"], "unsupported")
        self.assertEqual(native.replay_run(self.output)["status"], "failed")

    def test_unsupported_task_including_unhashable_retains_result(self):
        for index, task in enumerate(("image", ["classification"], None)):
            result = invoke(Path(self.temp.name) / str(index), task=task, x=examples()[0], y=examples()[1])
            self.assertEqual(result["status"], "unsupported")
            self.assertTrue((Path(self.temp.name) / str(index) / "result.json").is_file())

    def test_malformed_inputs_are_not_coerced_or_truncated(self):
        x, y = examples()
        invalid = [
            (x.astype(str), y, {}), (x.astype(object), y, {}), (x.astype(bool), y, {}),
            (x, y.astype(bool), {}), (x, y[:-1], {}), (x.ravel(), y, {}),
            (np.zeros((4097, 6)), np.zeros(4097), {}), (np.zeros((240, 129)), y, {}),
            (x, y, {"feature_names": ["same"] * 6}), (x, y, {"feature_names": ["bad\n", *list("abcde")]}),
            (x, y, {"seed": True}), (x, y, {"source_sha256": "bad"}),
        ]
        for index, (features, labels, args) in enumerate(invalid):
            with self.subTest(index=index):
                feature_names = args.pop("feature_names", ["a", "b", "c", "d", "e", "f"])
                result = native.run_native(features, labels, dataset_id="test", source_sha256=args.pop("source_sha256", "a" * 64),
                    feature_names=feature_names, output=Path(self.temp.name) / f"bad{index}", **args)
                self.assertEqual(result["status"], "failed")

    def test_nonfinite_and_out_of_bound_inputs_fail(self):
        for index, value in enumerate((float("nan"), float("inf"), -float("inf"), 1e13)):
            x, y = examples()
            x[0, 0] = value
            result = invoke(Path(self.temp.name) / str(index), x, y)
            self.assertEqual(result["status"], "failed")

    def test_unsupported_classification_labels_do_not_fit(self):
        x, y = examples()
        for index, labels in enumerate((np.ones(240), np.arange(240), y + .1)):
            result = invoke(Path(self.temp.name) / str(index), x, labels)
            self.assertEqual(result["status"], "unsupported")
            self.assertFalse((Path(self.temp.name) / str(index) / "candidate.json").exists())

    def test_missing_training_class_is_not_resplit(self):
        x, y = examples()
        base_plan = parse_plan((self.classification / "plan.json").read_bytes())
        y[base_plan.audit_indices[0]] = 1234
        result = invoke(self.output, x, y)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["reason"], "frozen_training_split_missing_class")
        plan = parse_plan((self.output / "plan.json").read_bytes())
        self.assertEqual(plan.train_indices, base_plan.train_indices)

    def test_training_failure_keeps_frozen_inputs_and_safe_reason(self):
        with patch("sklearn.naive_bayes.GaussianNB.fit", side_effect=RuntimeError("must-not-echo")):
            result = invoke(self.output)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "native_adapter_failed:RuntimeError")
        self.assertIn("plan.json", result["files"])
        self.assertNotIn("must-not-echo", json.dumps(result))

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            invoke(self.output)
        self.assertEqual(marker.read_bytes(), b"keep")
        self.assertEqual([path.name for path in self.output.iterdir()], ["keep.txt"])

    def test_traversal_output_is_refused(self):
        with self.assertRaises(ValueError):
            invoke(Path(self.temp.name) / "x" / ".." / "escape")

    def test_strict_json_rejects_duplicate_nonfinite_overflow_and_deep_values(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
                    b'[' * 25 + b'0' + b']' * 25, b'\xff', b''):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                strict_json(raw)

    def test_candidate_rejects_unknown_fields_versions_models_and_unsafe_formats(self):
        baseline = read(self.classification / "candidate.json")
        mutations = [lambda x: x.update(arbitrary_import="pickle"), lambda x: x.update(schema_version="future"),
                     lambda x: x.update(parents=["a" * 64]), lambda x: x["model"].update(kind="python-pickle"),
                     lambda x: x.update(task="regression"), lambda x: x.pop("schema_version"),
                     lambda x: x["preprocessing"].update(scale=[0.] * 6),
                     lambda x: x["model"].update(classes=[-2, -2, 11]),
                     lambda x: x["model"].update(prior=[.5, .5, .5]),
                     lambda x: x["model"].update(variance=[[-1.] * 6] * 3),
                     lambda x: x["model"].update(theta=[[0.]] * 3),
                     lambda x: x.update(feature_names=["a"] * 6),
                     lambda x: x.update(training_rows=True)]
        for mutate in mutations:
            candidate = copy.deepcopy(baseline)
            mutate(candidate)
            with self.assertRaises(ValueError):
                parse_candidate(canonical_bytes(candidate))
        with self.assertRaises(ValueError):
            parse_candidate(b'\x80\x04pickle')

    def test_regression_bool_alpha_is_not_accepted_as_numeric_one(self):
        candidate = read(self.regression / "candidate.json")
        candidate["model"]["alpha"] = True
        with self.assertRaises(ValueError):
            parse_candidate(canonical_bytes(candidate))

    def test_candidate_prediction_dimensions_and_overflow_are_checked(self):
        raw = (self.classification / "candidate.json").read_bytes()
        with self.assertRaises(ValueError):
            native.replay_candidate(raw, np.ones((10, 5)))
        candidate = read(self.classification / "candidate.json")
        candidate["preprocessing"]["scale"] = [1e-300] * 6
        with self.assertRaises(ValueError):
            native.replay_candidate(canonical_bytes(candidate), np.ones((10, 6)))

    def test_all_finalized_artifact_bytes_are_bound(self):
        for name in self.result["files"]:
            destination = Path(self.temp.name) / name.replace(".", "_")
            shutil.copytree(self.classification, destination)
            with (destination / name).open("ab") as stream:
                stream.write(b" ")
            self.assertEqual(native.replay_run(destination)["status"], "failed", name)

    def test_final_receipt_status_metrics_and_replay_are_checked(self):
        self.copy_run()
        original = read(self.output / "result.json")
        for mutation in (lambda x: x.update(status="failed"), lambda x: x["utility"].update(accuracy=True),
                         lambda x: x.update(production_authorized=True), lambda x: x["replay"].update(status="failed"),
                         lambda x: x["controls"].update(passed=False), lambda x: x.update(source_sha256="b" * 64)):
            altered = copy.deepcopy(original)
            mutation(altered)
            write(self.output / "result.json", altered)
            self.assertEqual(native.replay_run(self.output)["status"], "failed")

    def test_metrics_and_predictions_are_recomputed_even_if_receipt_hash_is_restamped(self):
        self.copy_run()
        report = read(self.output / "report.json")
        report["membership"]["true_positives"] = not bool(report["membership"]["true_positives"])
        write(self.output / "report.json", report)
        self.update_receipt_hash("report.json")
        self.assertEqual(native.replay_run(self.output)["status"], "failed")

    def test_prediction_bool_alias_is_not_equal_to_float_zero(self):
        self.copy_run()
        predictions = read(self.output / "predictions.json")
        predictions["predictions"][0][0] = False
        write(self.output / "predictions.json", predictions)
        self.update_receipt_hash("predictions.json")
        self.assertEqual(native.replay_run(self.output)["status"], "failed")

    def test_candidate_source_context_tamper_fails_after_restamped_file_hash(self):
        self.copy_run()
        candidate = read(self.output / "candidate.json")
        candidate["source_sha256"] = "b" * 64
        write(self.output / "candidate.json", candidate)
        self.update_receipt_hash("candidate.json")
        self.assertEqual(native.replay_run(self.output)["status"], "failed")

    def test_new_runtime_or_implementation_refuses_stale_replay(self):
        with patch.object(native, "_runtime", return_value={"python": "new", "numpy": "new", "scipy": "new", "scikit-learn": "new"}):
            self.assertEqual(native.replay_run(self.classification)["status"], "failed")
        with patch.object(native, "implementation_sha256", return_value="b" * 64):
            self.assertEqual(native.replay_run(self.classification)["status"], "failed")

    def test_extra_or_missing_final_artifacts_fail(self):
        self.copy_run()
        (self.output / "extra.json").write_bytes(b"{}")
        self.assertEqual(native.replay_run(self.output)["status"], "failed")
        (self.output / "extra.json").unlink()
        (self.output / "result.json").unlink()
        self.assertEqual(native.replay_run(self.output)["status"], "failed")

    def test_plan_overlapping_partition_and_miscount_are_refused(self):
        plan = read(self.classification / "plan.json")
        plan["audit_indices"][0] = plan["train_indices"][0]
        with self.assertRaises(ValueError):
            parse_plan(canonical_bytes(plan))
        plan = read(self.classification / "plan.json")
        plan["duplicate_groups"] += 1
        with self.assertRaises(ValueError):
            parse_plan(canonical_bytes(plan))

    def test_auc_ties_and_inverted_signal_match_independent_reference(self):
        from sklearn.metrics import roc_auc_score
        for members, nonmembers in (([1.] * 20, [0.] * 20), ([0.] * 20, [1.] * 20),
                                    ([.2, .5, .8, .8] * 5, [.2, .3, .8, .9] * 5)):
            expected = roc_auc_score([1] * len(members) + [0] * len(nonmembers), members + nonmembers)
            self.assertAlmostEqual(native._auc(members, nonmembers), expected)
        metrics = native._score_report([0.] * 20, [1.] * 20, [1.] * 20)
        self.assertEqual(metrics["raw_auc"], 0.)
        self.assertEqual(metrics["symmetric_auc"], 1.)

    def test_conditional_cp_intervals_match_exact_binomial_edges(self):
        metrics = native._score_report([1.] * 20, [0.] * 20, [0.] * 20)
        self.assertEqual(metrics["true_positives"], 20)
        self.assertEqual(metrics["false_positives"], 0)
        # Check defining tail inequalities at high precision; binary64 pow
        # and subtract can misorder an outward endpoint by one ULP.
        with localcontext() as context:
            context.prec = 70
            lower = Decimal(str(metrics["tpr_interval_95"][0]))
            upper = Decimal(str(metrics["fpr_interval_95"][1]))
            self.assertLessEqual(lower ** 20, Decimal(".025"))
            self.assertLessEqual((1 - upper) ** 20, Decimal(".025"))
        self.assertIn("not_population", metrics["interval_assumption"])

    def test_report_rejects_forged_control_pass_and_count_inconsistency(self):
        report = read(self.classification / "report.json")
        report["positive_control"]["raw_auc"] = .6
        report["positive_control"]["symmetric_auc"] = .6
        with self.assertRaises(ValidationError):
            NativeReport.model_validate(report)
        report = read(self.classification / "report.json")
        report["membership"]["true_positives"] = 4096
        with self.assertRaises(ValidationError):
            NativeReport.model_validate(report)

    def test_bounded_reader_checks_open_handle_and_disallows_hardlinks(self):
        target = Path(self.temp.name) / "real.json"
        target.write_bytes(b"{}")
        other = Path(self.temp.name) / "other.json"
        other.write_bytes(b"[]  ")
        descriptor = os.open(other, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        with patch.object(native.os, "open", return_value=descriptor):
            with self.assertRaises(ValueError):
                native._read(target)
        link = Path(self.temp.name) / "linked.json"
        os.link(target, link)
        with self.assertRaises(ValueError):
            native._read(target)


if __name__ == "__main__":
    unittest.main()
