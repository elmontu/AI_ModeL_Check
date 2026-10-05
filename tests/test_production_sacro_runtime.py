"""Pinned-runtime and typed output tests; real upstream runs are separate receipts."""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.model_selection import train_test_split

from model_release_assurance.production_sacro import runtime


class FakeAttack:
    instances = []
    mutate = None

    def __init__(self, **options):
        self.options = options
        self.result = None
        type(self).instances.append(self)

    def run_attack_reps(self, members, nonmembers):
        self.members, self.nonmembers = members, nonmembers
        labels = np.array([1] * len(members) + [0] * len(nonmembers))
        metrics = []
        for seed in runtime.SEEDS:
            _, test = train_test_split(np.arange(len(labels)), test_size=.5,
                                      stratify=labels, random_state=seed, shuffle=True)
            metrics.append({"AUC": np.float64(1.), "individual": {
                "member": labels[test].astype(float).tolist(),
                "member_prob": labels[test].astype(float).tolist()}})
        self.result = {"mia_metrics": metrics}
        if type(self).mutate:
            type(self).mutate(self.result)
        return self.result


class SacroRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.members = np.tile([.9, .1], (40, 1))
        self.nonmembers = np.tile([.5, .5], (40, 1))
        FakeAttack.instances = []
        FakeAttack.mutate = None

    def invoke(self, members=None, nonmembers=None, **kwargs):
        with patch.object(runtime, "runtime_binding", return_value={"version": "test-double"}), \
                patch.object(runtime, "_load_attack", return_value=FakeAttack):
            return runtime.run_attack(self.members if members is None else members,
                                      self.nonmembers if nonmembers is None else nonmembers,
                                      output_dir=kwargs.get("output_dir", self.root / "output"))

    def test_recipe_and_owned_outputs_reproduce_exact_split(self):
        result = self.invoke()
        self.assertEqual(len(result), 3)
        attack = FakeAttack.instances[0]
        self.assertFalse(np.shares_memory(attack.members, self.members))
        self.assertEqual(attack.options, {"output_dir": str(self.root / "output"),
            "write_report": False, "n_reps": 3, "reproduce_split": list(runtime.SEEDS),
            "n_dummy_reps": 0, "test_prop": .5, "include_model_correct_feature": False,
            "sort_probs": True, "attack_model": "sklearn.ensemble.RandomForestClassifier",
            "attack_model_params": runtime.ATTACK_PARAMETERS,
            "attack_model_param_grid": None, "report_individual": True})
        for item in result:
            self.assertEqual(set(item), {"seed", "train_indices", "test_indices",
                                        "membership_labels", "member_probabilities", "upstream_auc"})
            self.assertEqual(sorted(item["train_indices"] + item["test_indices"]), list(range(80)))
            self.assertFalse(set(item["train_indices"]) & set(item["test_indices"]))
            self.assertEqual(item["membership_labels"], [int(i < 40) for i in item["test_indices"]])
        attack.result["mia_metrics"][0]["individual"]["member_prob"][0] = .25
        self.assertNotEqual(result[0]["member_probabilities"][0], .25)

    def test_three_class_probabilities_are_supported(self):
        result = self.invoke(np.tile([.8, .1, .1], (40, 1)), np.tile([.4, .3, .3], (40, 1)))
        self.assertEqual(len(result), 3)

    def test_bad_inputs_deny_before_optional_import_or_output(self):
        bad = [np.ones(40), np.ones((40, 1)), np.ones((40, 33)), np.ones((19, 2)) / 2,
               np.ones((40, 2)), np.tile([np.nan, .5], (40, 1)),
               np.tile([np.inf, .5], (40, 1)), np.tile([-.1, 1.1], (40, 1)),
               [[True, 0.] for _ in range(40)], np.tile([".5", ".5"], (40, 1)),
               np.ones((4097, 2)) / 2]
        for value in bad:
            with self.subTest(shape=np.shape(value)), patch.object(runtime, "runtime_binding") as binding:
                with self.assertRaises(runtime.SacroRuntimeError):
                    runtime.run_attack(value, self.nonmembers, output_dir=self.root / "output")
                binding.assert_not_called()
                self.assertFalse((self.root / "output").exists())

    def test_mismatched_classes_and_combined_bounds(self):
        with self.assertRaises(runtime.SacroRuntimeError):
            self.invoke(nonmembers=np.ones((40, 3)) / 3)
        with self.assertRaises(runtime.SacroRuntimeError):
            self.invoke(np.ones((2100, 2)) / 2, np.ones((2100, 2)) / 2)

    def test_existing_output_is_never_reused(self):
        output = self.root / "output"
        output.mkdir()
        (output / "retained").write_text("unchanged", encoding="utf-8")
        with self.assertRaises(runtime.SacroRuntimeError):
            self.invoke()
        self.assertEqual((output / "retained").read_text(encoding="utf-8"), "unchanged")
        self.assertEqual(FakeAttack.instances, [])

    def test_bad_labels_length_and_nonfinite_outputs_are_rejected(self):
        changes = [lambda value: value["mia_metrics"].pop(),
            lambda value: value["mia_metrics"][0].update(AUC=float("nan")),
            lambda value: value["mia_metrics"][0].update(AUC=True),
            lambda value: value["mia_metrics"][0]["individual"]["member_prob"].pop(),
            lambda value: value["mia_metrics"][0]["individual"]["member_prob"].__setitem__(0, float("inf")),
            lambda value: value["mia_metrics"][0]["individual"]["member_prob"].__setitem__(0, 1.1),
            lambda value: value["mia_metrics"][0]["individual"]["member"].__setitem__(0, True),
            lambda value: value["mia_metrics"][0]["individual"]["member"].reverse(),
            lambda value: value["mia_metrics"][0]["individual"].update(extra=[])]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                FakeAttack.mutate = change
                with self.assertRaises(runtime.SacroRuntimeError):
                    self.invoke(output_dir=self.root / str(index))

    def test_source_drift_during_import_and_after_attack_denies_output(self):
        for index, bindings in enumerate(([{"pin": 1}, {"pin": 2}],
                                         [{"pin": 1}, {"pin": 1}, {"pin": 2}])):
            with self.subTest(index=index), patch.object(runtime, "runtime_binding", side_effect=bindings), \
                    patch.object(runtime, "_load_attack", return_value=FakeAttack):
                with self.assertRaises(runtime.SacroRuntimeError):
                    runtime.run_attack(self.members, self.nonmembers, output_dir=self.root / str(index))

    def test_optional_dependency_missing_fails_without_fallback(self):
        with patch.object(runtime.importlib.metadata, "distribution", side_effect=runtime.importlib.metadata.PackageNotFoundError), \
                patch.object(runtime, "_load_attack") as factory:
            with self.assertRaises(runtime.SacroRuntimeError):
                runtime.run_attack(self.members, self.nonmembers, output_dir=self.root / "output")
            factory.assert_not_called()
            self.assertFalse((self.root / "output").exists())

    def test_import_and_upstream_errors_do_not_leak_payload(self):
        with patch.object(runtime, "runtime_binding", return_value={}), \
                patch.object(runtime, "_load_attack", side_effect=RuntimeError("private payload")):
            with self.assertRaisesRegex(runtime.SacroRuntimeError, "^SACRO fixture runtime rejected$"):
                runtime.run_attack(self.members, self.nonmembers, output_dir=self.root / "output")

    def installed_fixture(self):
        package = self.root / "sacroml"
        package.mkdir()
        files = {"sacroml/__init__.py": b'"""Fictional package."""\n',
                 "sacroml/version.py": b'__version__ = "2.0.1"\n'}
        pins = {}
        rows = []
        for name, raw in files.items():
            (self.root / name).write_bytes(raw)
            hash_value = hashlib.sha256(raw).hexdigest()
            pins[name] = {"sha256": hash_value, "size_bytes": len(raw)}
            rows.append([name, "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(hash_value)).decode().rstrip("="), str(len(raw))])
        metadata = self.root / "sacroml-2.0.1.dist-info"
        metadata.mkdir()
        (metadata / "METADATA").write_bytes(b"Name: sacroml\nVersion: 2.0.1\n")
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        (metadata / "RECORD").write_text(buffer.getvalue(), encoding="utf-8", newline="")
        distribution = SimpleNamespace(version="2.0.1", locate_file=lambda _: self.root)
        spec = SimpleNamespace(origin=str(package / "__init__.py"), submodule_search_locations=[str(package)])
        return distribution, pins, spec, metadata

    def checked(self, fixture):
        distribution, pins, spec, metadata = fixture
        with patch.object(runtime, "SOURCE_PINS", pins), \
                patch.object(runtime, "METADATA_SHA256", hashlib.sha256(b"Name: sacroml\nVersion: 2.0.1\n").hexdigest()), \
                patch.object(runtime.importlib.util, "find_spec", return_value=spec):
            return runtime._checked_distribution(distribution)

    def test_installed_source_and_record_consistency(self):
        fixture = self.installed_fixture()
        self.assertEqual(self.checked(fixture), self.root)

    def test_changed_installed_source_is_not_trusted(self):
        fixture = self.installed_fixture()
        (self.root / "sacroml/version.py").write_bytes(b'__version__ = "9.0.0"\n')
        with self.assertRaises(ValueError):
            self.checked(fixture)

    def test_changed_record_and_duplicate_record_fail(self):
        fixture = self.installed_fixture()
        record = fixture[3] / "RECORD"
        original = record.read_text(encoding="utf-8")
        for value in (original.replace("sha256=", "md5="), original + original):
            record.write_text(value, encoding="utf-8")
            with self.assertRaises(ValueError):
                self.checked(fixture)

    def test_unpinned_bytecode_or_module_is_refused(self):
        fixture = self.installed_fixture()
        cached = self.root / "sacroml/version.pyc"
        cached.write_bytes(b"not trusted")
        with self.assertRaises(ValueError):
            self.checked(fixture)

    def test_wrong_version_metadata_and_import_origin_fail(self):
        fixture = self.installed_fixture()
        distribution, _, spec, metadata = fixture
        distribution.version = "2.0.2"
        with self.assertRaises(ValueError):
            self.checked(fixture)
        distribution.version = "2.0.1"
        spec.origin = str(self.root / "unrelated.py")
        with self.assertRaises(ValueError):
            self.checked(fixture)
        spec.origin = str(self.root / "sacroml/__init__.py")
        (metadata / "METADATA").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.checked(fixture)

    def test_wrong_numerical_version_fails_without_import(self):
        with patch.object(runtime.importlib.metadata, "distribution", return_value=object()), \
                patch.object(runtime, "_checked_distribution"), \
                patch.object(runtime, "_numerical_versions", return_value={"numpy": "different"}):
            with self.assertRaises(runtime.SacroRuntimeError):
                runtime.runtime_binding()

    def test_binding_is_data_only_and_owns_versions(self):
        versions = dict(runtime.NUMERICAL_VERSIONS)
        with patch.object(runtime.importlib.metadata, "distribution", return_value=object()), \
                patch.object(runtime, "_checked_distribution"), \
                patch.object(runtime, "_numerical_versions", return_value=versions):
            result = runtime.runtime_binding()
        versions["numpy"] = "changed"
        self.assertEqual(result["numerical_versions"], runtime.NUMERICAL_VERSIONS)
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["model_delivery"])


if __name__ == "__main__":
    unittest.main()
