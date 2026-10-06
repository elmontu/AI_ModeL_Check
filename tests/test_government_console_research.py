"""Fixed research selections, safe configuration and retained source provenance."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from model_release_assurance.console import research_data as r
from model_release_assurance.production_adapters.datasets import DatasetError, DatasetUnavailable


class ConsoleResearchBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-console-research-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data_root = self.root / "research"
        self.data_root.mkdir()
        self.environment = mock.patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop(r.ENV, None)

    def loaded(self, corpus="acs"):
        x = np.arange(48, dtype=float).reshape(16, 3)
        y = np.array([0, 1] * 8, dtype=np.uint8)
        x.setflags(write=False)
        y.setflags(write=False)
        return {"x": x, "y": y, "feature_names": ["public-a", "public-b", "public-c"],
            "dataset_id": "research." + corpus + ".explicit-unit-fixture",
            "profile_id": corpus, "task": "classification", "source_sha256": "a" * 64,
            "metadata": {"source_relative_path": "experiments/explicit-unit-fixture/data.npz",
                "manifest_sha256": "b" * 64, "historical_training_data_reused": True,
                "fresh_audit_evidence": False, "authenticated_upstream_provenance": False,
                "local_public_fixture_pin_verified": True, "production_authorized": False,
                "private_data_admitted": False, "person_level_disjointness_established": False,
                "current_license_approval": False, "omitted_fields": ["z", "keys", "strata"],
                "source_array_shapes": {"B": [16, 3], "y": [16], "z": [16]},
                "nested": {"provenance": ["unchanged"]}},
            # Deliberate extra loader fields prove only explicitly selected B/y
            # can cross this bridge, even if an upstream return shape expands.
            "z": np.full(16, 12345), "keys": np.array(["unit-id"] * 16), "strata": np.arange(16)}

    def test_unconfigured_inventory_is_bounded_and_loading_has_no_fallback(self):
        self.assertIsNone(r.configured_research_root())
        self.assertEqual(r.research_inventory(), {"configured": False, "max_rows": 4096,
                                                "source_kind": "historical_public_research_matrix"})
        with mock.patch("model_release_assurance.production_registration.profiles.load_profile") as loader:
            with self.assertRaises(r.ResearchDataUnavailable):
                r.load_console_research("research-acs")
        loader.assert_not_called()
        os.environ[r.ENV] = ""
        self.assertIsNone(r.configured_research_root())

    def test_configured_root_and_http_inventory_never_disclose_absolute_path(self):
        os.environ[r.ENV] = str(self.data_root)
        self.assertEqual(r.configured_research_root(), self.data_root)
        report = r.research_inventory()
        self.assertEqual(set(report), {"configured", "max_rows", "source_kind"})
        self.assertIs(report["configured"], True)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertFalse(any(self.data_root.iterdir()))

    def test_relative_missing_file_traversal_and_network_roots_refuse(self):
        file = self.root / "not-a-directory"
        file.write_bytes(b"preserve")
        for value in ("relative/research", str(file), str(self.root / "research" / ".." / "research"),
                      "//server/share/research", "\\\\server\\share\\research"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {r.ENV: value}):
                with self.assertRaises(r.ResearchDataError):
                    r.configured_research_root()
        with mock.patch.dict(os.environ, {r.ENV: str(self.root / "absent")}), self.assertRaises(r.ResearchDataUnavailable) as caught:
            r.research_inventory()
        self.assertNotIn(str(self.root), str(caught.exception))
        self.assertEqual(file.read_bytes(), b"preserve")

    def test_symlink_or_reparse_ancestor_is_not_resolved_or_followed(self):
        original = Path.lstat
        for kind in ("symlink", "reparse"):
            def fake(path, *args, **kwargs):
                actual = original(path, *args, **kwargs)
                if path == self.root:
                    return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else actual.st_mode,
                        st_file_attributes=0x400 if kind == "reparse" else 0,
                        st_dev=actual.st_dev, st_ino=actual.st_ino)
                return actual
            with self.subTest(kind=kind), mock.patch.object(Path, "lstat", fake), \
                    mock.patch.dict(os.environ, {r.ENV: str(self.data_root)}), self.assertRaises(r.ResearchDataError):
                r.configured_research_root()

    def test_unknown_ids_rejected_before_configuration_or_loader(self):
        with mock.patch.object(r, "configured_research_root") as configured, \
                mock.patch("model_release_assurance.production_registration.profiles.load_profile") as loader:
            for value in ("acs", "research-adult", "research-../acs", "research-acs/", "sklearn-wine", {}, True, None):
                with self.subTest(value=value), self.assertRaises(r.ResearchDataError):
                    r.load_console_research(value)
        configured.assert_not_called()
        loader.assert_not_called()
        with self.assertRaises(TypeError):
            r.RESEARCH_DATASETS["research-other"] = "replacement"
        self.assertEqual(set(r.RESEARCH_DATASETS), {"research-acs", "research-bts", "research-hmda", "research-tlc"})

    def test_all_four_ids_use_unchanged_pinned_loader_at_exact_bound(self):
        os.environ[r.ENV] = str(self.data_root)
        for dataset in r.RESEARCH_DATASETS:
            corpus = dataset.removeprefix("research-")
            loaded = self.loaded(corpus)
            original_metadata = copy.deepcopy(loaded["metadata"])
            with self.subTest(dataset=dataset), \
                    mock.patch("model_release_assurance.production_registration.profiles.load_profile", return_value=loaded) as loader:
                data, provenance = r.load_console_research(dataset)
            loader.assert_called_once_with(corpus, data_root=self.data_root, max_rows=4096)
            self.assertEqual(set(data), {"data", "target", "feature_names", "target_names"})
            np.testing.assert_array_equal(data.data, loaded["x"])
            np.testing.assert_array_equal(data.target, loaded["y"])
            self.assertFalse(data.data.flags.writeable)
            self.assertFalse(data.target.flags.writeable)
            self.assertEqual(data.target_names, ["0", "1"])
            self.assertEqual(provenance, {"dataset_id": dataset, "profile_id": corpus,
                "source_kind": "historical_public_research_matrix", "source_sha256": loaded["source_sha256"],
                "metadata": original_metadata})
            self.assertNotIn(str(self.data_root), json.dumps(provenance))
            provenance["metadata"]["nested"]["provenance"].append("mutated")
            data.feature_names[0] = "mutated"
            self.assertEqual(loaded["metadata"], original_metadata)
            self.assertEqual(loaded["feature_names"][0], "public-a")
            self.assertFalse(any(self.data_root.iterdir()))

    def test_explicit_trusted_root_overrides_environment_without_exposing_it(self):
        os.environ[r.ENV] = "invalid-relative-root"
        with mock.patch("model_release_assurance.production_registration.profiles.load_profile", return_value=self.loaded()) as loader:
            data, provenance = r.load_console_research("research-acs", data_root=self.data_root)
        loader.assert_called_once_with("acs", data_root=self.data_root, max_rows=4096)
        self.assertEqual(len(data.target), 16)
        self.assertNotIn(str(self.root), json.dumps(provenance))
        for value in ("relative", True, {}, b"bytes"):
            with self.subTest(value=value), self.assertRaises(r.ResearchDataError):
                r.load_console_research("research-acs", data_root=value)

    def test_pinned_loader_missing_tamper_and_runtime_errors_are_never_fallbacks(self):
        for error in (DatasetUnavailable("unit source absent"), DatasetError("unit byte pin changed"),
                      RuntimeError("unit runtime unavailable")):
            with self.subTest(error=type(error).__name__), \
                    mock.patch("model_release_assurance.production_registration.profiles.load_profile", side_effect=error) as loader:
                with self.assertRaises(type(error)) as caught:
                    r.load_console_research("research-acs", data_root=self.data_root)
            self.assertIs(caught.exception, error)
            loader.assert_called_once()
        self.assertFalse(any(self.data_root.iterdir()))

    def test_directory_identity_change_after_load_is_rejected(self):
        with mock.patch("model_release_assurance.production_registration.profiles.load_profile", return_value=self.loaded()), \
                mock.patch.object(r, "_directory_stamp", side_effect=[((1, 1),), ((1, 1),), ((1, 2),)]), \
                self.assertRaises(r.ResearchDataError):
            r.load_console_research("research-acs", data_root=self.data_root)


    def test_training_options_allow_classifiers_only_and_no_http_source_path(self):
        from pydantic import ValidationError
        from model_release_assurance.console.options import TrainingOptions
        for dataset in r.RESEARCH_DATASETS:
            for preset in ("logistic", "random-forest", "mlp", "mlp-finetuned", "svm", "ensemble"):
                with self.subTest(dataset=dataset, preset=preset):
                    self.assertEqual(TrainingOptions(dataset=dataset, preset=preset).dataset, dataset)
            for preset in ("ridge", "forest-regression", "cnn", "xgboost-small"):
                with self.subTest(dataset=dataset, preset=preset), self.assertRaises(ValidationError):
                    TrainingOptions(dataset=dataset, preset=preset)
        with self.assertRaises(ValidationError):
            TrainingOptions(dataset="research-acs", preset="logistic", research_data_root=str(self.data_root))

    def test_research_training_without_configuration_refuses_before_output_or_fit(self):
        from model_release_assurance.public_models import run_public
        output = self.root / "must-not-exist"
        with mock.patch("sklearn.linear_model.LogisticRegression.fit") as fit, self.assertRaises(r.ResearchDataUnavailable):
            run_public("logistic", "research-acs", output)
        fit.assert_not_called()
        self.assertFalse(output.exists())

    def test_capability_inventory_lists_sources_without_claiming_availability_or_paths(self):
        from model_release_assurance.public_models import capability_inventory
        unconfigured = capability_inventory()
        self.assertTrue(set(r.RESEARCH_DATASETS).issubset(unconfigured["datasets"]))
        self.assertFalse(unconfigured["research_data"]["configured"])
        os.environ[r.ENV] = str(self.data_root)
        configured = capability_inventory()
        self.assertTrue(configured["research_data"]["configured"])
        self.assertNotIn(str(self.data_root), json.dumps(configured))
        self.assertFalse(any(self.data_root.iterdir()))

    def test_training_retains_exact_provenance_and_rejects_changed_source_during_replay(self):
        from sklearn.utils import Bunch
        from sklearn.linear_model import LogisticRegression
        from model_release_assurance import public_models, registered_training, workflow
        from model_release_assurance.models import AssessmentRequest
        from model_release_assurance.errors import IntegrityError
        # Explicit synthetic unit fixture at the bridge boundary, not a claim
        # that invented bytes satisfy the production registration's source pins.
        rng = np.random.default_rng(7401)
        x = rng.normal(size=(160, 4))
        y = np.array([0, 1] * 80, dtype=np.uint8)
        data = Bunch(data=x, target=y, feature_names=["unit-a", "unit-b", "unit-c", "unit-d"],
                     target_names=["0", "1"])
        provenance = {"dataset_id": "research-tlc", "profile_id": "tlc", "source_kind": r.SOURCE_KIND,
            "source_sha256": "a" * 64, "metadata": {"explicit_synthetic_unit_fixture": True,
                "local_public_fixture_pin_verified": False, "historical_training_data_reused": True,
                "fresh_audit_evidence": False, "authenticated_upstream_provenance": False,
                "current_license_approval": False, "person_level_disjointness_established": False,
                "source_relative_path": "unit-fixture-only", "manifest_sha256": "b" * 64,
                "omitted_fields": ["z", "keys", "strata"], "selected_rows": 160,
                "limitations": ["Explicit synthetic unit fixture; no real source-pin verification claimed."]}}
        output = self.root / "classification"
        original_fit = LogisticRegression.fit
        seen = []
        research_files = ["research-source.json", "source-snapshots/console/research_data.py",
            "source-snapshots/production_registration/profiles.py", "source-snapshots/production_adapters/datasets.py"]
        def fit(model, *args, **kwargs):
            if not seen:
                freeze = json.loads((output / "evidence-freeze.json").read_text())
                self.assertTrue(set(research_files).issubset(freeze["files"]))
                for name in research_files:
                    self.assertEqual(freeze["files"][name], workflow.digest(output / name))
                self.assertFalse((output / "model.joblib").exists())
            seen.append(True)
            return original_fit(model, *args, **kwargs)
        with mock.patch.object(public_models, "load_console_research", return_value=(data, provenance)) as loader, \
                mock.patch.object(LogisticRegression, "fit", fit):
            result = public_models.run_public("logistic", "research-tlc", output, research_data_root=self.data_root)
        loader.assert_called_once_with("research-tlc", data_root=self.data_root)
        self.assertTrue(seen)
        self.assertTrue(result["training_executed"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["authorization_eligible"])
        self.assertIn(result["verdict"], {"block", "inconclusive"})
        self.assertEqual(result["dataset"]["research_source"], provenance)
        self.assertEqual(json.loads((output / "training-config.json").read_text())["research_source"], provenance)
        self.assertEqual(json.loads((output / "data-manifest.json").read_text())["research_source"], provenance)
        self.assertEqual(json.loads((output / "research-source.json").read_text()), provenance)
        with np.load(output / "public-dataset.npz", allow_pickle=False) as snapshot:
            self.assertEqual(set(snapshot.files), {"x", "y", "train", "test", "calibration", "audit", "base_train"})
            np.testing.assert_array_equal(snapshot["x"], x)
            np.testing.assert_array_equal(snapshot["y"], y)
        self.assertNotIn(str(self.data_root), json.dumps(result))
        request = AssessmentRequest.model_validate_json((output / "assessment-request.json").read_bytes())
        verification_sha = workflow.digest(output / "training-verification.json")
        request_sha = workflow.digest(output / "assessment-request.json")
        def replay():
            return registered_training.verify_local_training_evidence(request, output, verification_sha, request_sha)
        with mock.patch("joblib.load", side_effect=AssertionError("replay must not load estimator bytes")):
            replay()
            for name in [*research_files, "public-dataset.npz"]:
                path = output / name
                before = path.read_bytes()
                path.write_bytes(before + b" changed")
                try:
                    with self.subTest(tamper=name), self.assertRaises(IntegrityError):
                        replay()
                finally:
                    path.write_bytes(before)
            replay()
        self.assertFalse(any(self.data_root.iterdir()))


    def test_http_requires_configuration_before_queueing_and_never_accepts_source_paths(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.console.api import create_app
        from model_release_assurance.console.store import Store
        state = self.root / "api-state"
        payload = {"kind": "training", "training": {"name": "Research unit selection",
                                                    "preset": "logistic", "dataset": "research-acs"}}
        with TestClient(create_app(state)) as client, \
                mock.patch("model_release_assurance.production_registration.profiles.load_profile",
                           side_effect=AssertionError("queueing must not load scientific data")) as loader:
            response = client.post("/api/jobs", json=payload)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(Store(state).list_jobs(), [])
            os.environ[r.ENV] = "relative-misconfiguration"
            response = client.post("/api/jobs", json=payload)
            self.assertEqual(response.status_code, 409)
            self.assertNotIn("relative-misconfiguration", response.text)
            self.assertEqual(Store(state).list_jobs(), [])
            os.environ[r.ENV] = str(self.data_root)
            malformed = copy.deepcopy(payload)
            malformed["training"]["research_data_root"] = str(self.root / "unapproved")
            self.assertEqual(client.post("/api/jobs", json=malformed).status_code, 422)
            self.assertEqual(Store(state).list_jobs(), [])
            response = client.post("/api/jobs", json=payload)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["options"]["dataset"], "research-acs")
            self.assertEqual(response.json()["state"], "queued")
            self.assertEqual(len(Store(state).list_jobs()), 1)
            self.assertNotIn(str(self.data_root), response.text)
            loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
