"""Independent learner fixtures exercise exact ART workflow failure boundaries."""
import copy
import json
import hashlib
import warnings
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from scipy.optimize import OptimizeWarning
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_evidence.replay import snapshot_native_bundle
from model_release_assurance.production_registration.profiles import load_profile
from model_release_assurance.production_art import protocol, workflow, worker, runtime


def independent_cases(prepared):
    """Explicit synthetic worker substitute: fits sklearn directly, never ART."""
    result = {}
    for name in ("target", "positive", "null"):
        losses = protocol.loss_features_float32(prepared["cases"][name]["loss_values"])
        features = np.asarray([[value, 0.] for value in losses], dtype=np.float32)
        repetitions = []
        for split in protocol.frozen_splits(prepared):
            train, test = split["train_indices"], split["test_indices"]
            labels = [prepared["membership_labels"][index] for index in train]
            scaler = StandardScaler()
            transformed = scaler.fit_transform(features[train])
            estimator = LogisticRegression(C=1., solver="lbfgs", max_iter=500, random_state=20261006)
            # This pinned scipy/sklearn pair emits one known unused-option warning.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Unknown solver options: iprint", category=OptimizeWarning)
                estimator.fit(transformed, labels)
            probabilities = estimator.predict_proba(scaler.transform(features[test]))[:, 1].tolist()
            learned = {"classes": estimator.classes_.tolist(), "coef": estimator.coef_[0].tolist(),
                "intercept": float(estimator.intercept_[0]), "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist(), "n_iter": int(estimator.n_iter_[0])}
            repetitions.append({**split, "member_probabilities": probabilities, "learned": learned,
                                "loss_features_float32": losses})
        result[name] = repetitions
    return result


class ArtWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="art-workflow-")
        cls.root, cls.bundles = Path(cls.workspace.name), {}
        for name in ("sklearn-wine", "sklearn-diabetes"):
            data = load_profile(name, max_rows=128)
            destination = cls.root / name
            receipt = native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"],
                source_sha256=data["source_sha256"], feature_names=data["feature_names"],
                task=data["task"], output=destination)
            assert receipt["status"] == "completed", receipt
            cls.bundles[name] = snapshot_native_bundle(destination)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="art-run-")
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "run"
        self.change = None
        self.source = {"fixture.py": "b" * 64}
        self.descriptor = {"python": str(self.output.parent / "env/Scripts/python.exe"),
            "launcher_sha256": "d" * 64, "base_python": str(self.output.parent / "base/python.exe"),
            "base_sha256": "e" * 64, "site_packages": str(self.output.parent / "env/Lib/site-packages"),
            "configuration_sha256": "f" * 64}
        descriptor_mock = patch.object(workflow, "runtime_descriptor", return_value=self.descriptor)
        descriptor_mock.start()
        self.addCleanup(descriptor_mock.stop)
        self.source_mock = patch.object(workflow, "source_snapshot", return_value=self.source)
        self.source_mock.start()
        self.addCleanup(self.source_mock.stop)

    def external(self, python, input_path, output):
        request = json.loads(input_path.read_bytes())
        self.assertTrue((input_path.parent / "plan.json").exists())
        self.assertEqual(json.loads((input_path.parent / "plan.json").read_bytes())["splits"],
                         protocol.frozen_splits(request["prepared"]))
        worker_result = {"schema": "mra-art-worker-output/v1", "status": "completed",
            "prepared_sha256": workflow.digest(request["prepared"]), "runtime": workflow.expected_binding(),
            "versions": request["versions"], "source_sha256": request["source_sha256"],
            "lock_sha256": request["lock_sha256"], "cases": independent_cases(request["prepared"]),
            "fixture_only": True, "can_clear": False, "assessment_eligible": False,
            "authorization_eligible": False, "production_authorized": False}
        process = {"status": "completed", "cleanup_confirmed": True,
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "source_sha256": request["source_sha256"], "runtime_descriptor": copy.deepcopy(self.descriptor),
            "exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0, "elapsed_seconds": .25,
            "hostile_code_isolated": False, "network_isolated": False,
            "filesystem_isolated": False, "resource_limits_verified": False}
        output.mkdir()
        workflow.write(output / "worker.json", worker_result)
        workflow.write(output / "process.json", process)
        if self.change:
            self.change(request, worker_result, process, input_path)
        return {**process, "result": worker_result}

    def run_case(self, profile="sklearn-wine", blobs=None):
        with patch.object(workflow, "run_worker", side_effect=self.external):
            return workflow.run_comparison(blobs if blobs is not None else self.bundles[profile],
                profile_id=profile, output=self.output, python="unused",
                versions=dict(runtime.LOCKED_VERSIONS), lock_sha256="a" * 64)

    def replay(self, profile="sklearn-wine"):
        return workflow.replay_comparison(self.bundles[profile], profile_id=profile,
            output=self.output, versions=dict(runtime.LOCKED_VERSIONS), lock_sha256="a" * 64)

    def test_classifier_and_regression_both_require_all_three_controls(self):
        for profile in ("sklearn-wine", "sklearn-diabetes"):
            with self.subTest(profile=profile):
                self.output = self.output.parent / profile
                receipt = self.run_case(profile)
                self.assertEqual(receipt["status"], "completed", receipt)
                self.assertEqual(set(receipt["comparison"]), {"target", "positive", "null"})
                self.assertTrue(all(receipt["comparison"][name]["controls_satisfied"]
                                    for name in ("positive", "null")))
                self.assertEqual(self.replay(profile)["status"], "bound_local_replay")
                for flag in ("can_clear", "assessment_eligible", "authorization_eligible",
                             "production_authorized", "external_execution_attested", "model_delivery"):
                    self.assertIs(receipt[flag], False)

    def test_wrong_profile_refused_before_execution(self):
        with patch.object(workflow, "run_worker", side_effect=AssertionError):
            receipt = workflow.run_comparison(self.bundles["sklearn-diabetes"], profile_id="sklearn-wine",
                output=self.output, python="unused", versions=runtime.LOCKED_VERSIONS, lock_sha256="a" * 64)
        self.assertEqual(receipt["status"], "failed")
        self.assertIsNone(receipt["process"])

    def test_missing_or_extra_control_refused(self):
        for change in (lambda cases: cases.pop("positive"), lambda cases: cases.update(extra=[])):
            self.output = self.output.parent / ("missing" if not self.output.parent.joinpath("missing").exists() else "extra")
            self.change = lambda req, result, process, path: change(result["cases"])
            self.assertEqual(self.run_case()["status"], "failed")

    def test_probability_change_cannot_be_hidden_by_consistent_auc(self):
        self.change = lambda req, result, process, path: result["cases"]["target"][0]["member_probabilities"].__setitem__(0, .123)
        self.assertEqual(self.run_case()["status"], "failed")

    def test_loss_feature_change_refused(self):
        self.change = lambda req, result, process, path: result["cases"]["target"][0]["loss_features_float32"].__setitem__(0, 3.)
        self.assertEqual(self.run_case()["status"], "failed")

    def test_repetition_reordering_refused(self):
        self.change = lambda req, result, process, path: result["cases"]["target"].reverse()
        self.assertEqual(self.run_case()["status"], "failed")

    def test_membership_relabeling_refused(self):
        self.change = lambda req, result, process, path: result["cases"]["target"][0]["membership_labels"].reverse()
        self.assertEqual(self.run_case()["status"], "failed")

    def test_runtime_or_source_worker_binding_change_refused(self):
        for key in ("runtime", "source_sha256", "lock_sha256", "prepared_sha256", "versions"):
            self.output = self.output.parent / key
            self.change = lambda req, result, process, path: result.__setitem__(key, {} if key in ("runtime", "versions") else "c" * 64)
            self.assertEqual(self.run_case()["status"], "failed", key)

    def test_worker_unknown_or_authorizing_flags_refused(self):
        for key in ("can_clear", "production_authorized", "assessment_eligible", "unknown"):
            self.output = self.output.parent / key
            self.change = lambda req, result, process, path: result.update({key: True})
            self.assertEqual(self.run_case()["status"], "failed", key)

    def test_frozen_input_plan_or_worker_bytes_cannot_change(self):
        for filename in ("input.json", "plan.json", "worker/worker.json", "worker/process.json"):
            self.output = self.output.parent / filename.replace("/", "-")
            self.change = lambda req, result, process, path: (path.parent / filename).write_bytes(b"{}")
            self.assertEqual(self.run_case()["status"], "failed", filename)

    def test_source_drift_prevents_success(self):
        self.change = lambda req, result, process, path: self.source.update({"fixture.py": "c" * 64})
        # Return distinct snapshots so a caller cannot mutate the captured source mapping.
        with patch.object(workflow, "source_snapshot", side_effect=lambda: dict(self.source)):
            self.assertEqual(self.run_case()["status"], "failed")

    def test_timeout_unavailable_and_unsupported_never_fall_back(self):
        for status in ("timed_out", "unavailable", "unsupported", "output_limit"):
            self.output = self.output.parent / status
            self.change = lambda req, result, process, path: process.update(status=status)
            receipt = self.run_case()
            self.assertEqual(receipt["status"], status if status != "output_limit" else "failed")
            self.assertIsNone(receipt["comparison"])

    def test_unconfirmed_cleanup_cannot_complete(self):
        self.change = lambda req, result, process, path: process.update(cleanup_confirmed=False)
        self.assertEqual(self.run_case()["status"], "failed")

    def test_missing_dependency_is_explicit_unavailable(self):
        with patch.object(workflow, "run_worker", side_effect=ModuleNotFoundError):
            receipt = workflow.run_comparison(self.bundles["sklearn-wine"], profile_id="sklearn-wine",
                output=self.output, python="unused", versions=runtime.LOCKED_VERSIONS, lock_sha256="a" * 64)
        self.assertEqual(receipt["status"], "unavailable")
        self.assertIsNone(receipt["comparison"])

    def test_overwrite_is_refused(self):
        self.run_case()
        before = (self.output / "result.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_case()
        self.assertEqual((self.output / "result.json").read_bytes(), before)

    def test_saved_link_rejects_changed_independent_comparison(self):
        self.assertEqual(self.run_case()["status"], "completed")
        path = self.output / "comparison.json"
        value = json.loads(path.read_bytes())
        value["target"]["summary"] = {}
        path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ValueError):
            self.replay()

    def test_saved_link_rejects_noncanonical_frozen_bytes(self):
        self.assertEqual(self.run_case()["status"], "completed")
        path = self.output / "plan.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.replay()

    def test_saved_link_rejects_authorizing_or_unknown_receipt(self):
        self.assertEqual(self.run_case()["status"], "completed")
        path = self.output / "result.json"
        value = json.loads(path.read_bytes())
        value["external_execution_attested"] = True
        path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ValueError):
            self.replay()

    def test_process_claims_are_exact_and_bounded(self):
        changes = {"input_sha256": "c" * 64, "source_sha256": "c" * 64,
            "exit_code": True, "stdout_bytes": True, "stderr_bytes": 65537,
            "elapsed_seconds": float("inf"), "network_isolated": True,
            "hostile_code_isolated": True, "resource_limits_verified": True, "unknown": 0}
        for key, value in changes.items():
            self.output = self.output.parent / key
            self.change = lambda req, result, process, path: process.update({key: value})
            self.assertEqual(self.run_case()["status"], "failed", key)

    def test_saved_process_cannot_disagree_with_receipt(self):
        self.assertEqual(self.run_case()["status"], "completed")
        path = self.output / "worker/process.json"
        value = json.loads(path.read_bytes())
        value["elapsed_seconds"] = .75
        path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ValueError):
            self.replay()

    def test_live_runtime_descriptor_drift_prevents_success(self):
        with patch.object(workflow, "runtime_descriptor", side_effect=[self.descriptor, {**self.descriptor, "base_sha256": "c" * 64}]):
            self.assertEqual(self.run_case()["status"], "failed")

    def test_unbounded_or_unknown_request_fields_refused(self):
        self.assertEqual(self.run_case()["status"], "completed")
        request = json.loads((self.output / "input.json").read_bytes())
        for changed in ({**request, "pickle": "x"}, {**request, "versions": {}}, {**request, "lock_sha256": True}):
            with self.assertRaises(ValueError):
                worker.validate_request(changed)


if __name__ == "__main__":
    unittest.main()
