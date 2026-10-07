"""Provisioning and fail-closed reuse checks for the one-click public datasets."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import sklearn
from sklearn import datasets

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mra_prepare_demo_data", ROOT / "scripts/prepare_demo_data.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)

class DemoDatasetSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verification = ROOT / ".local/verification/demo-dataset-setup-20261007"
        cls.verification.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="test-", dir=cls.verification)
        cls.base = Path(cls.temporary.name) / "datasets"
        cls.manifest = setup.prepare_demo_data(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fixture(self, directory):
        root = Path(directory) / "copied"
        shutil.copytree(self.base, root)
        return root

    def snapshot(self, root):
        return {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in root.iterdir()}

    def test_four_required_public_samples_have_exact_shapes_and_provenance(self):
        self.assertEqual(self.manifest["schema"], "mra-demo-datasets/v1")
        self.assertEqual(self.manifest["sklearn_version"], "1.6.1")
        shapes = {entry["dataset_id"]: (entry["rows"], entry["features"])
                  for entry in self.manifest["datasets"]}
        self.assertEqual(shapes, {
            "sklearn-wine": (178, 13), "sklearn-breast-cancer": (569, 30),
            "sklearn-digits": (1797, 64), "sklearn-diabetes": (442, 10)})
        for entry in self.manifest["datasets"]:
            with np.load(self.base / entry["filename"], allow_pickle=False) as data:
                self.assertEqual(data["x"].shape, shapes[entry["dataset_id"]])
                self.assertEqual(data["y"].shape, (entry["rows"],))
                self.assertTrue(np.isfinite(data["x"]).all())
                self.assertTrue(np.isfinite(data["y"]).all())
                self.assertEqual(set(data.files), {"x", "y"})
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertEqual(len(entry["data_sha256"]), 64)
            self.assertIn("package-local", entry["source"])
        self.assertFalse(self.manifest["external_dataset_downloads"])
        self.assertFalse(self.manifest["research_datasets_provisioned"])
        self.assertFalse(self.manifest["model_training_executed"])

    def test_reuse_verifies_without_replacing_or_touching_files(self):
        before = self.snapshot(self.base)
        self.assertEqual(setup.prepare_demo_data(self.base), self.manifest)
        self.assertEqual(setup.verify_demo_data(self.base), self.manifest)
        self.assertEqual(self.snapshot(self.base), before)

    def test_creation_uses_no_external_dataset_network(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            with patch("urllib.request.urlopen", side_effect=AssertionError("no data download")):
                self.assertEqual(setup.prepare_demo_data(Path(temporary) / "new")["schema"],
                                 setup.SCHEMA)

    def test_partial_cache_refuses_repairs_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = self.fixture(temporary)
            (root / "sklearn-wine.npz").unlink()
            before = self.snapshot(root)
            with self.assertRaisesRegex(setup.DemoDataError, "partial"):
                setup.prepare_demo_data(root)
            self.assertEqual(self.snapshot(root), before)

    def test_tampered_manifest_and_arrays_are_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = self.fixture(temporary)
            manifest = root / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" tampered")
            before = self.snapshot(root)
            with self.assertRaisesRegex(setup.DemoDataError, "manifest"):
                setup.prepare_demo_data(root)
            self.assertEqual(self.snapshot(root), before)
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = self.fixture(temporary)
            path = root / "sklearn-digits.npz"
            path.write_bytes(path.read_bytes() + b" tampered")
            before = self.snapshot(root)
            with self.assertRaisesRegex(setup.DemoDataError, "declared bytes"):
                setup.prepare_demo_data(root)
            self.assertEqual(self.snapshot(root), before)

    def test_consistently_restamped_changed_data_still_fails_installed_loader_replay(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = self.fixture(temporary)
            path = root / "sklearn-wine.npz"
            with np.load(path, allow_pickle=False) as saved:
                x, y = saved["x"].copy(), saved["y"].copy()
            x[0, 0] += 1
            np.savez_compressed(path, x=x, y=y)
            manifest = json.loads((root / "manifest.json").read_text())
            entry = next(item for item in manifest["datasets"]
                         if item["dataset_id"] == "sklearn-wine")
            entry["bytes"] = path.stat().st_size
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (root / "manifest.json").write_bytes(setup._canonical(manifest))
            before = self.snapshot(root)
            with self.assertRaises(setup.DemoDataError):
                setup.prepare_demo_data(root)
            self.assertEqual(self.snapshot(root), before)

    def test_wrong_installed_version_is_rejected_before_creating_cache(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = Path(temporary) / "absent"
            with patch.object(sklearn, "__version__", "1.7.0"):
                with self.assertRaisesRegex(setup.DemoDataError, "1.6.1"):
                    setup.prepare_demo_data(root)
            self.assertFalse(root.exists())

    def test_bad_loader_shape_and_nonfinite_samples_are_rejected_before_creation(self):
        for bad in ("shape", "nonfinite"):
            with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
                root = Path(temporary) / "absent"
                wine = copy.deepcopy(datasets.load_wine())
                if bad == "shape":
                    wine.data = wine.data[:, :-1]
                else:
                    wine.data[0, 0] = np.nan
                with patch.object(datasets, "load_wine", return_value=wine):
                    with self.assertRaises(setup.DemoDataError):
                        setup.prepare_demo_data(root)
                self.assertFalse(root.exists())

    def test_relative_unc_traversal_and_extra_files_are_rejected(self):
        for bad in (Path("relative-cache"), Path("//server/share/cache"),
                    self.verification / "up" / ".." / "cache"):
            with self.assertRaises(setup.DemoDataError):
                setup.prepare_demo_data(bad)
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = self.fixture(temporary)
            (root / "unknown.txt").write_text("preserve this")
            before = self.snapshot(root)
            with self.assertRaisesRegex(setup.DemoDataError, "unexpected"):
                setup.prepare_demo_data(root)
            self.assertEqual(self.snapshot(root), before)

    def test_single_link_requirement_rejects_linked_dataset(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = self.fixture(temporary)
            os.link(root / "sklearn-wine.npz", Path(temporary) / "wine-linked.npz")
            with self.assertRaisesRegex(setup.DemoDataError, "single-link"):
                setup.verify_demo_data(root)

    def test_readonly_verify_does_not_create_missing_output(self):
        with tempfile.TemporaryDirectory(dir=self.verification) as temporary:
            root = Path(temporary) / "absent"
            with self.assertRaisesRegex(setup.DemoDataError, "missing"):
                setup.verify_demo_data(root)
            self.assertFalse(root.exists())

    def test_cli_embeddable_standalone_script_outputs_verified_summary(self):
        before = self.snapshot(self.base)
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(ROOT / "scripts/prepare_demo_data.py"),
             "--output", str(self.base)],
            capture_output=True, text=True, check=True, timeout=30)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["status"], "verified")
        self.assertEqual(len(summary["datasets"]), 4)
        self.assertFalse(summary["external_dataset_downloads"])
        self.assertEqual(self.snapshot(self.base), before)

if __name__ == "__main__":
    unittest.main()
