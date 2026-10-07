"""Scientific, export and tamper checks for real private-model clearance."""
from __future__ import annotations
import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import numpy as np
from model_release_assurance import private_model_clearance as private
from model_release_assurance.analyzers.dp import membership_roc_ceiling
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import canonical_json_bytes, sha256_file
from model_release_assurance.models import AssessmentRequest

class PrivateModelClearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temporary.name) / "real-fit"
        cls.result = private.run_private_model_clearance(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def copied(self, parent):
        root = Path(parent) / "copied"
        shutil.copytree(self.base, root)
        return root

    def test_real_fit_clearance_is_native_engine_dp_ceiling_with_unchanged_thresholds(self):
        request = AssessmentRequest.model_validate(private._read(self.base / "assessment-request.json"))
        report = AssuranceEngine().assess(request, self.base)
        self.assertTrue(self.result["real_training_executed"])
        self.assertEqual(self.result["preset"], "dp-histogram")
        self.assertEqual(self.result["dataset"]["features"], 2)
        self.assertEqual(report.overall_verdict.value, "clear")
        decision = report.decisions[0]
        self.assertEqual(decision.tolerance, 0.2)
        self.assertEqual(decision.decision_metric, "membership_tpr_at_fpr")
        self.assertEqual(request.threats[0].metric_parameters["target_fpr"], 0.1)
        self.assertEqual(request.analyzer_inputs[0].delta, 0)
        self.assertLess(decision.upper_bound, 0.2)
        self.assertAlmostEqual(decision.upper_bound, membership_roc_ceiling(private.EPSILON, 0, 0.1)[0])
        self.assertEqual(decision.clearance_evidence_class.value, "ceiling")
        self.assertEqual(decision.ceiling_attack_battery.mode.value, "waived")
        self.assertIn("local mathematical", decision.ceiling_attack_battery.waiver_reason)
        self.assertFalse(self.result["authorized"])
        self.assertFalse(self.result["authorization_eligible"])
        self.assertFalse(self.result["deployed"])
        self.assertEqual(request.release.artifact_path, "recipient-package.json")

    def test_package_has_only_fixed_public_configuration_and_noisy_postprocessing(self):
        package = private._read(self.base / "recipient-package.json")
        self.assertEqual(set(package), {"format_version", "profile", "public_configuration", "noisy_counts", "model"})
        self.assertEqual(package["public_configuration"], private.public_configuration())
        self.assertEqual(package["model"], private._postprocess(package["noisy_counts"]))
        encoded = (self.base / "recipient-package.json").read_text()
        for forbidden in ("training_indices", "training_records", "noise_values", "random_seed",
                          "raw_counts", "training_input", "training_size"):
            self.assertNotIn(forbidden, encoded)
        self.assertFalse(any(path.name in {"raw-counts.json", "noise.json", "model.joblib"}
                             for path in self.base.rglob("*")))
        request = AssessmentRequest.model_validate(private._read(self.base / "assessment-request.json"))
        self.assertEqual(request.release.interface.output_channels.downloadable_files,
                         ("recipient-package.json",))

    def test_classifier_predictions_replay_inert_noisy_model_without_training_state(self):
        package = private._read(self.base / "recipient-package.json")
        model = private.RecipientModel(package)
        points = np.array([[12.0, 500.0], [13.1, 751.0], [100.0, -1000.0]])
        probabilities = model.predict_proba(points)
        self.assertEqual(probabilities.shape, (3, 3))
        np.testing.assert_allclose(probabilities.sum(axis=1), 1, atol=1e-14)
        self.assertTrue(np.isfinite(probabilities).all())
        self.assertTrue((probabilities > 0).all())
        np.testing.assert_array_equal(model.predict(points), np.argmax(probabilities, axis=1))
        self.assertFalse(hasattr(model, "fit"))
        with self.assertRaises(private.PrivateModelEvidenceError):
            model.predict_proba([[math.nan, 500]])

    def test_integer_sampler_uses_exact_randbelow_and_has_no_truncation(self):
        with patch.object(private.secrets, "randbelow", side_effect=[9, 4, 0, 1, 0]) as source:
            self.assertEqual(private._geometric_noise(), 1)
            self.assertEqual(source.call_args_list[0].args, (10,))
            self.assertEqual(source.call_count, 5)
        with patch.object(private.secrets, "randbelow", side_effect=[1] * 1500 + [0]):
            self.assertEqual(private._geometric_zero(), 1500)

    def test_training_count_contribution_is_three_and_bins_are_fixed(self):
        # Zero noise is used only to examine counting in this unit test, never
        # for a native assessment or retained evidence-supported clearance.
        with patch.object(private, "_geometric_noise", return_value=0):
            empty = private.fit_private_model(np.empty((0, 2)), np.empty(0, dtype=int))
            one = private.fit_private_model(np.array([[12.0, 500.0]]), np.array([1]))
        self.assertEqual(one["noisy_counts"]["class"], [0, 1, 0])
        self.assertEqual(one["noisy_counts"]["features"][0][1], [0, 0, 1, 0, 0])
        self.assertEqual(one["noisy_counts"]["features"][1][1], [0, 0, 1, 0, 0, 0, 0])
        def flatten(counts):
            return counts["class"] + [value for table in counts["features"] for row in table for value in row]
        self.assertEqual(sum(abs(left - right) for left, right in
                             zip(flatten(one["noisy_counts"]), flatten(empty["noisy_counts"]))), 3)
        self.assertEqual(one["public_configuration"], empty["public_configuration"])

    def test_geometric_likelihood_ratio_bound_and_epsilon_rounding_are_conservative(self):
        q = Fraction(9, 10)
        def probability(noise):
            return (1 - q) / (1 + q) * q ** abs(noise)
        largest = Fraction(0)
        for noise in range(-20, 21):
            for increment in (-1, 0, 1):
                largest = max(largest, probability(noise) / probability(noise - increment))
        self.assertEqual(largest, Fraction(10, 9))
        self.assertEqual(largest ** 3, Fraction(1000, 729))
        self.assertLessEqual(3 * math.log(10 / 9), 1 / 3)
        self.assertGreaterEqual(Fraction(str(private.EPSILON)), Fraction(1, 3))
        self.assertGreater(private.EPSILON, 0)
        self.assertLess(private._ledger()["epsilon_upper"], math.log(2))
        self.assertEqual(private._ledger()["vector_l1_sensitivity"], 3)

    def test_real_model_attack_suite_is_exploratory_and_controls_independent(self):
        tools = {tool["tool"]: tool for tool in self.result["red_team"]["tools"]}
        self.assertEqual(len(tools), 11)
        self.assertEqual(tools["membership_score_attacks"]["status"], "completed")
        self.assertIn("probes", tools["membership_score_attacks"]["result"])
        for name in ("structural_disclosure", "tree_leaf_exposure",
                     "label_poisoning", "trigger_backdoor"):
            self.assertEqual(tools[name]["status"], "unsupported")
        self.assertFalse(any(tool["status"] == "failed" for tool in tools.values()))
        self.assertTrue(all(tool["can_clear"] is False and tool["can_block"] is False
                            for tool in tools.values()))
        controls = private._read(self.base / "positive-controls.json")
        self.assertTrue(controls["known_leak"]["passed"])
        self.assertTrue(controls["null_output"]["passed"])
        self.assertEqual(controls["known_leak"]["result"]["tpr"], 1)
        self.assertEqual(controls["null_output"]["result"]["auc"], 0.5)
        self.assertFalse(controls["can_clear"])
        self.assertFalse(controls["institutionally_qualified_battery"])

    def test_all_bound_files_fail_closed_when_missing_or_changed(self):
        names = list(private.FROZEN_FILES) + list(private.COMPLETED_FILES) + [
            "clearance-certificate.json", "source-snapshots/private_model_clearance.py"]
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied(temporary)
            for name in names:
                with self.subTest(name=name):
                    path = root / name
                    saved = path.read_bytes()
                    path.unlink()
                    try:
                        with self.assertRaises((ValueError, FileNotFoundError)):
                            private.verify_private_model_run(root)
                    finally:
                        path.write_bytes(saved)
                    path.write_bytes(saved + b" changed")
                    try:
                        with self.assertRaises((ValueError, FileNotFoundError)):
                            private.verify_private_model_run(root)
                    finally:
                        path.write_bytes(saved)
            self.assertTrue(private.verify_private_model_run(root)["verified"])

    def test_false_accountant_or_pipeline_flags_and_rebound_certificate_do_not_clear(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied(temporary)
            original = private._read(root / "assessment-request.json")
            for field in ("accountant_replayed", "complete_pipeline"):
                with self.subTest(field=field):
                    request = copy.deepcopy(original)
                    request["analyzer_inputs"][0][field] = False
                    private._write(root / "assessment-request.json", request)
                    certificate = private._read(root / "clearance-certificate.json")
                    certificate["files"]["assessment-request.json"] = sha256_file(root / "assessment-request.json")
                    private._write(root / "clearance-certificate.json", certificate)
                    with self.assertRaisesRegex(private.PrivateModelEvidenceError, "assessment request"):
                        private.verify_private_model_run(root)
                    private._write(root / "assessment-request.json", original)

    def test_changed_noisy_model_and_updated_hashes_fail_semantic_postprocessing_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied(temporary)
            package = private._read(root / "recipient-package.json")
            package["model"]["class_prior"] = [1.0, 0.0, 0.0]
            private._write(root / "recipient-package.json", package)
            receipt = private._read(root / "training-receipt.json")
            receipt["recipient_package_sha256"] = sha256_file(root / "recipient-package.json")
            private._write(root / "training-receipt.json", receipt)
            with self.assertRaisesRegex(private.PrivateModelEvidenceError, "does not replay"):
                private.verify_private_model_run(root)

    def test_changed_current_source_or_positive_control_is_rejected(self):
        modified = private._source_hashes()
        modified["private_model_clearance.py"] = "0" * 64
        with patch.object(private, "_source_hashes", return_value=modified):
            with self.assertRaisesRegex(private.PrivateModelEvidenceError, "source changed"):
                private.verify_private_model_run(self.base)
        with patch.object(private, "_positive_controls", return_value={"passed": False}):
            with self.assertRaisesRegex(private.PrivateModelEvidenceError, "controls"):
                private.verify_private_model_run(self.base)

    def test_operator_extra_file_is_allowed_but_cannot_be_added_to_recipient_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied(temporary)
            private._write(root / "console-overlap.json", {"public_operator_helper": True})
            self.assertTrue(private.verify_private_model_run(root)["verified"])
            package = private._read(root / "recipient-package.json")
            package["training_size"] = 115
            with self.assertRaisesRegex(private.PrivateModelEvidenceError, "unexpected"):
                private.validate_recipient_package(package)

    def test_recipient_reader_rejects_duplicate_keys_nonfinite_and_boolean_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "package.json"
            for raw in (b'{"profile":"secret","profile":"public"}', b'{"value":NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(private.PrivateModelEvidenceError):
                    private._read(path)
        package = private._read(self.base / "recipient-package.json")
        package["noisy_counts"]["class"][0] = True
        with self.assertRaisesRegex(private.PrivateModelEvidenceError, "integers"):
            private.validate_recipient_package(package)

    def test_refit_in_existing_output_is_refused_and_recipient_cli_only_predicts(self):
        with self.assertRaisesRegex(private.PrivateModelEvidenceError, "empty"):
            private.run_private_model_clearance(self.base)
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "model_release_assurance.private_model_clearance",
             "--predict-package", str(self.base / "recipient-package.json"),
             "--alcohol", "13.2", "--proline", "750"],
            capture_output=True, text=True, timeout=30, check=True)
        prediction = json.loads(completed.stdout)
        self.assertIn(prediction["predicted_class"], (0, 1, 2))
        self.assertAlmostEqual(sum(prediction["class_probabilities"]), 1)
        self.assertIn("not a new assessment", prediction["scope"])

if __name__ == "__main__":
    unittest.main()

