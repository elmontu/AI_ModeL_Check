"""Eight pinned public profiles; no external data or downloads in unit tests."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
import sklearn
from sklearn import datasets as sklearn_datasets

from model_release_assurance.production_adapters import datasets as research
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_registration import profiles
from model_release_assurance.production_registration.profiles import DatasetError, DatasetUnavailable


class RegistrationProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-registration-profile-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def fixture(self, corpus="acs"):
        directory = self.root / "experiments" / "mixed-model-export-20260929-v1" / corpus / "data"
        directory.mkdir(parents=True)
        columns = len(research._FEATURE_NAMES[corpus])
        np.savez_compressed(directory / "data.npz",
            B=np.arange(256 * columns, dtype=np.int64).reshape(256, columns) % 17,
            y=np.arange(256, dtype=np.uint8) % 2, z=np.arange(256, dtype=np.uint8) % 2,
            keys=np.full(256, "fixture-key-never-returned", dtype="<U40"))
        blob = (directory / "data.npz").read_bytes()
        manifest = {"schema": "mra.mixed-model-data.v1", "corpus": corpus, "selected_rows": 256,
                    "b_names": list(research._FEATURE_NAMES[corpus]),
                    "data_receipt": {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}}
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        pins = (hashlib.sha256(blob).hexdigest(), hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        return directory, pins

    def test_exact_eight_profile_allowlist_and_descriptor_shape(self):
        self.assertEqual(profiles.PROFILE_IDS, ("acs", "bts", "hmda", "tlc", "sklearn-breast-cancer",
                                               "sklearn-wine", "sklearn-digits", "sklearn-diabetes"))
        for identifier in profiles.PROFILE_IDS:
            descriptor = profiles.profile_descriptor(identifier)
            self.assertEqual(set(descriptor), {"id", "task", "source_kind", "expected_source_sha256",
                                               "expected_manifest_sha256"})
            self.assertEqual(descriptor["id"], identifier)
            self.assertRegex(descriptor["expected_source_sha256"], r"^[a-f0-9]{64}$")
            if identifier in research.CORPORA:
                self.assertEqual(descriptor["source_kind"], "research_prepared")
                self.assertRegex(descriptor["expected_manifest_sha256"], r"^[a-f0-9]{64}$")
            else:
                self.assertEqual(descriptor["source_kind"], "bundled")
                self.assertIsNone(descriptor["expected_manifest_sha256"])
            self.assertEqual(descriptor["task"], "regression" if identifier == "sklearn-diabetes" else "classification")

    def test_descriptor_is_owned_and_cannot_mutate_pins(self):
        descriptor = profiles.profile_descriptor("acs")
        before = copy.deepcopy(descriptor)
        descriptor["expected_source_sha256"] = "f" * 64
        self.assertEqual(profiles.profile_descriptor("acs"), before)

    def test_unknown_ids_rejected_before_any_loader_or_path_io(self):
        for identifier in ("../acs", "ACS", "acs/../bts", "uci-adult", "openml-1590", "private", "",
                           "sklearn-iris", True, None, [], {"id": "acs"}):
            with self.subTest(identifier=identifier), mock.patch.object(profiles, "load_research_dataset") as loader, \
                    mock.patch.object(profiles, "_bundled") as bundled:
                with self.assertRaises(DatasetError):
                    profiles.load_profile(identifier, data_root=object())
                loader.assert_not_called()
                bundled.assert_not_called()

    def test_invalid_row_bounds_are_rejected_before_loading(self):
        for rows in (True, False, 127, 4097, 128.0, "128", None):
            with self.subTest(rows=rows), mock.patch.object(profiles, "load_research_dataset") as loader:
                with self.assertRaises(DatasetError):
                    profiles.load_profile("acs", data_root=self.root, max_rows=rows)
                loader.assert_not_called()

    def test_no_private_custom_matrix_or_model_import_argument(self):
        for argument in ("x", "y", "model", "model_path", "source_url", "classification", "loader"):
            with self.subTest(argument=argument), self.assertRaises(TypeError):
                profiles.load_profile("acs", **{argument: "not-accepted"})

    def test_all_bundled_sources_preserve_prd11_pin_sample_and_task(self):
        expected = {
            "sklearn-breast-cancer": (569, 30, "d08f00631c909e2c45d29eeb435baa544c887ce888406b7de02e62d646420e23"),
            "sklearn-wine": (178, 13, "dff0821beaef6be12d102fedd77e50fb836ad592eacccbb1c54f1da645609984"),
            "sklearn-digits": (1797, 64, "324e3559227b16544346c7ac62530d449d0393a8d82eced0c0cc1a63855b2871"),
            "sklearn-diabetes": (442, 10, "d0c4650a339dfce5bb2e36d2e95b98060dcf1191177b82dee757b7de2b8a181e"),
        }
        for identifier, (rows, columns, sample_hash) in expected.items():
            with self.subTest(identifier=identifier):
                result = profiles.load_profile(identifier, data_root=self.root / "never-accessed")
                self.assertEqual(set(result), {"x", "y", "feature_names", "dataset_id", "source_sha256",
                                              "metadata", "profile_id", "task"})
                self.assertEqual(result["x"].shape, (rows, columns))
                self.assertEqual(result["y"].shape, (rows,))
                self.assertEqual(result["source_sha256"], profiles.profile_descriptor(identifier)["expected_source_sha256"])
                self.assertEqual(result["metadata"]["selected_matrix_sha256"], sample_hash)
                self.assertEqual(result["metadata"]["sklearn_version"], "1.6.1")
                self.assertEqual(result["task"], "regression" if identifier == "sklearn-diabetes" else "classification")
                self.assertEqual(result["profile_id"], identifier)
                self.assertFalse(result["x"].flags.writeable)
                self.assertFalse(result["y"].flags.writeable)

    def test_bundled_selection_is_exact_fixed_seed_prefix(self):
        original = sklearn_datasets.load_wine()
        indices = np.random.default_rng(20261001).permutation(len(original.target))[:128]
        result = profiles.load_profile("sklearn-wine", max_rows=128)
        np.testing.assert_array_equal(result["x"], original.data[indices])
        np.testing.assert_array_equal(result["y"], original.target[indices])
        self.assertEqual(result["metadata"]["selection_indices_sha256"],
                         hashlib.sha256(canonical_bytes(indices.tolist())).hexdigest())

    def test_owned_results_are_deterministic_and_read_only(self):
        first = profiles.load_profile("sklearn-wine", max_rows=128)
        again = profiles.load_profile("sklearn-wine", max_rows=128)
        self.assertEqual(first["metadata"], again["metadata"])
        self.assertEqual(first["feature_names"], again["feature_names"])
        np.testing.assert_array_equal(first["x"], again["x"])
        np.testing.assert_array_equal(first["y"], again["y"])
        with self.assertRaises(ValueError):
            first["x"][0, 0] = 0
        with self.assertRaises(ValueError):
            first["y"][0] = 0
        first["metadata"]["loader"] = "changed"
        first["feature_names"][0] = "changed"
        first["x"].setflags(write=True)
        first["x"][0, 0] = 0
        self.assertEqual(profiles.load_profile("sklearn-wine", max_rows=128)["metadata"], again["metadata"])
        np.testing.assert_array_equal(profiles.load_profile("sklearn-wine", max_rows=128)["x"], again["x"])

    def test_changed_sklearn_version_rejected_before_dataset_loading(self):
        with mock.patch.object(sklearn, "__version__", "unreviewed"), \
                mock.patch.object(sklearn_datasets, "load_wine") as loader:
            with self.assertRaises(DatasetError):
                profiles.load_profile("sklearn-wine")
            loader.assert_not_called()

    def test_changed_bundled_source_is_rejected(self):
        original = sklearn_datasets.load_wine()
        original.data = np.array(original.data, copy=True)
        original.data[0, 0] += 1
        with mock.patch.object(sklearn_datasets, "load_wine", return_value=original):
            with self.assertRaises(DatasetError):
                profiles.load_profile("sklearn-wine")

    def test_changed_feature_name_or_target_is_rejected(self):
        for field in ("feature_names", "target"):
            original = sklearn_datasets.load_wine()
            if field == "feature_names":
                original.feature_names[0] = "substituted"
            else:
                original.target = np.array(original.target, copy=True)
                original.target[0] = 2
            with self.subTest(field=field), mock.patch.object(sklearn_datasets, "load_wine", return_value=original):
                with self.assertRaises(DatasetError):
                    profiles.load_profile("sklearn-wine")

    def test_diabetes_upstream_scaling_is_explicit(self):
        result = profiles.load_profile("sklearn-diabetes")
        note = result["metadata"]["upstream_preprocessing"]
        self.assertIn("scaled=True", note)
        self.assertIn("full-cohort", note)
        self.assertIn("before this benchmark split", note)

    def test_common_metadata_never_claims_freshness_authority_or_complete_history(self):
        for identifier in ("sklearn-wine", "sklearn-diabetes"):
            metadata = profiles.load_profile(identifier)["metadata"]
            self.assertTrue(metadata["historical_training_data_reused"])
            self.assertTrue(metadata["local_public_fixture_pin_verified"])
            for field in ("authenticated_upstream_provenance", "current_license_approval", "fresh_audit_evidence",
                          "person_level_disjointness_established", "disclosure_history_complete", "private_data_admitted",
                          "authorization_eligible", "production_authorized", "model_delivery"):
                self.assertIs(metadata[field], False)
            self.assertLess(len(canonical_bytes(metadata)), 65536)

    def test_missing_research_root_is_distinct_from_rejected_source(self):
        with self.assertRaises(DatasetUnavailable):
            profiles.load_profile("acs")
        with self.assertRaises(DatasetUnavailable):
            profiles.load_profile("acs", data_root=self.root / "absent")
        self.fixture()
        with self.assertRaises(DatasetError):
            profiles.load_profile("acs", data_root=self.root)

    def test_research_path_traversal_and_relative_root_are_rejected(self):
        for root in (Path("relative"), self.root / ".." / self.root.name):
            with self.subTest(root=root), self.assertRaises(DatasetError):
                profiles.load_profile("acs", data_root=root)

    def test_research_sources_reuse_safe_loader_and_return_only_public_arrays(self):
        for identifier in research.CORPORA:
            directory, pins = self.fixture(identifier)
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
            with mock.patch.dict(profiles._PINS, {identifier: pins}):
                result = profiles.load_profile(identifier, data_root=self.root, max_rows=128)
                old = research.load_research_dataset(self.root, identifier, max_rows=128)
            np.testing.assert_array_equal(result["x"], old["x"])
            np.testing.assert_array_equal(result["y"], old["y"])
            self.assertEqual(result["source_sha256"], old["source_sha256"])
            self.assertEqual(result["metadata"]["sampled_matrix_sha256"], old["metadata"]["sampled_matrix_sha256"])
            self.assertEqual(result["metadata"]["selection_indices_sha256"], old["metadata"]["selection_indices_sha256"])
            self.assertEqual(result["metadata"]["manifest_sha256"], pins[1])
            self.assertEqual(result["metadata"]["returned_covariates"], "B only")
            self.assertNotIn("fixture-key-never-returned", json.dumps(result["metadata"]))
            self.assertNotIn("z", result["feature_names"])
            self.assertEqual(before, {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()})

    def test_pinned_manifest_change_is_rejected_even_with_unchanged_npz(self):
        directory, pins = self.fixture()
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["unreviewed_provenance"] = "changed"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        # Existing research loader verifies the NPZ receipt, while new profiles
        # also bind the reviewed provenance manifest's exact bytes.
        self.assertEqual(research.load_research_dataset(self.root, "acs")["source_sha256"], pins[0])
        with mock.patch.dict(profiles._PINS, {"acs": pins}):
            with self.assertRaises(DatasetError):
                profiles.load_profile("acs", data_root=self.root)

    def test_consistently_restamped_source_is_rejected_by_independent_pin(self):
        directory, pins = self.fixture()
        np.savez_compressed(directory / "data.npz", B=np.ones((256, 8)), y=np.arange(256, dtype=np.uint8) % 2)
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text())
        blob = (directory / "data.npz").read_bytes()
        manifest["data_receipt"] = {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        research.load_research_dataset(self.root, "acs")
        with mock.patch.dict(profiles._PINS, {"acs": pins}):
            with self.assertRaises(DatasetError):
                profiles.load_profile("acs", data_root=self.root)

    def test_changed_source_bytes_without_receipt_remain_rejected_not_missing(self):
        directory, pins = self.fixture()
        (directory / "data.npz").write_bytes(b"invalid changed archive")
        with mock.patch.dict(profiles._PINS, {"acs": pins}):
            with self.assertRaises(DatasetError):
                profiles.load_profile("acs", data_root=self.root)

    def test_loader_metadata_and_arrays_are_not_mutated_or_shared(self):
        self.fixture()
        original = research.load_research_dataset(self.root, "acs", max_rows=128)
        before = copy.deepcopy(original["metadata"])
        pins = original["source_sha256"], original["metadata"]["manifest_sha256"]
        with mock.patch.dict(profiles._PINS, {"acs": pins}), \
                mock.patch.object(profiles, "load_research_dataset", return_value=original):
            result = profiles.load_profile("acs", data_root=self.root, max_rows=128)
        self.assertEqual(original["metadata"], before)
        self.assertFalse(np.shares_memory(original["x"], result["x"]))
        self.assertFalse(np.shares_memory(original["y"], result["y"]))
        result["metadata"]["source_array_shapes"]["B"][0] = 1
        self.assertEqual(original["metadata"], before)


if __name__ == "__main__":
    unittest.main()
