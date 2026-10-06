"""Optional ART dependency and installed-source rejection boundaries."""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from model_release_assurance.production_art import runtime


class ArtRuntimeRosterTests(unittest.TestCase):
    def roster(self, versions=None):
        values = runtime.LOCKED_VERSIONS if versions is None else versions
        return [SimpleNamespace(metadata={"Name": name}, version=version)
                for name, version in values.items()]

    def probe(self, distributions=None, *, python=None, distribution_error=None):
        with patch.object(runtime.importlib.metadata, "distributions", return_value=
                          self.roster() if distributions is None else distributions), \
                patch.object(runtime.platform, "python_version", return_value=
                             runtime.NUMERICAL_VERSIONS["python"] if python is None else python), \
                patch.object(runtime.importlib.metadata, "distribution", side_effect=distribution_error,
                             return_value=object()), \
                patch.object(runtime, "_checked_distribution") as checked:
            result = runtime.probe_runtime(dict(runtime.LOCKED_VERSIONS))
        self.assertEqual(checked.call_count, 1)
        return result

    def test_exact_roster_returns_non_authorizing_owned_binding(self):
        result = self.probe()
        self.assertEqual(result, runtime.expected_binding())
        self.assertTrue(result["fixture_only"])
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["model_delivery"])
        result["numerical_versions"]["numpy"] = "modified"
        self.assertEqual(runtime.NUMERICAL_VERSIONS["numpy"], "2.5.3")
        self.assertEqual(runtime.expected_binding()["numerical_versions"]["numpy"], "2.5.3")

    def test_distribution_names_are_normalized_without_losing_exact_roster(self):
        distributions = self.roster()
        for value in distributions:
            value.metadata["Name"] = value.metadata["Name"].upper().replace("-", "_")
        self.assertEqual(self.probe(distributions), runtime.expected_binding())

    def test_missing_art_is_explicitly_unavailable_before_source_check(self):
        values = dict(runtime.LOCKED_VERSIONS)
        values.pop("adversarial-robustness-toolbox")
        with patch.object(runtime, "_checked_distribution") as checked:
            with self.assertRaises(runtime.ArtRuntimeUnavailable):
                self.probe(self.roster(values))
            checked.assert_not_called()

    def test_missing_transitive_dependency_has_no_substitute(self):
        values = dict(runtime.LOCKED_VERSIONS)
        values.pop("numpy")
        with self.assertRaises(runtime.ArtRuntimeUnavailable):
            self.probe(self.roster(values))

    def test_distribution_disappearing_after_roster_check_is_unavailable(self):
        with self.assertRaises(runtime.ArtRuntimeUnavailable):
            self.probe(distribution_error=runtime.importlib.metadata.PackageNotFoundError("art"))

    def test_changed_version_is_rejected(self):
        values = dict(runtime.LOCKED_VERSIONS)
        values["adversarial-robustness-toolbox"] = "1.20.2"
        with self.assertRaises(runtime.ArtRuntimeError) as rejected:
            self.probe(self.roster(values))
        self.assertNotIsInstance(rejected.exception, runtime.ArtRuntimeUnavailable)

    def test_extra_distribution_is_rejected(self):
        values = dict(runtime.LOCKED_VERSIONS, unapproved="1.0")
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(self.roster(values))

    def test_duplicate_normalized_name_is_rejected(self):
        distributions = self.roster()
        distributions.append(SimpleNamespace(metadata={"Name": "Scikit_Learn"}, version="1.6.1"))
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(distributions)

    def test_wrong_python_is_rejected(self):
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(python="3.12.15")

    def test_declared_versions_cannot_widen_or_restamp_locked_roster(self):
        changes = [dict(runtime.LOCKED_VERSIONS, numpy="unapproved"),
                   {name: version for name, version in runtime.LOCKED_VERSIONS.items() if name != "numpy"},
                   dict(runtime.LOCKED_VERSIONS, unapproved="1.0")]
        for values in changes:
            with self.subTest(values=len(values)), \
                    patch.object(runtime.importlib.metadata, "distributions") as discover:
                with self.assertRaises(runtime.ArtRuntimeError):
                    runtime.probe_runtime(values)
                discover.assert_not_called()

    def test_unexpected_metadata_error_does_not_echo_payload(self):
        with patch.object(runtime.importlib.metadata, "distributions",
                          side_effect=RuntimeError("sensitive sentinel")):
            with self.assertRaisesRegex(runtime.ArtRuntimeError, "^ART fixture runtime rejected$"):
                runtime.probe_runtime(dict(runtime.LOCKED_VERSIONS))

    def test_source_error_cannot_be_reported_as_available(self):
        with patch.object(runtime.importlib.metadata, "distributions", return_value=self.roster()), \
                patch.object(runtime.platform, "python_version", return_value=runtime.NUMERICAL_VERSIONS["python"]), \
                patch.object(runtime.importlib.metadata, "distribution", return_value=object()), \
                patch.object(runtime, "_checked_distribution", side_effect=ValueError("source changed")):
            with self.assertRaisesRegex(runtime.ArtRuntimeError, "^ART fixture runtime rejected$"):
                runtime.probe_runtime(dict(runtime.LOCKED_VERSIONS))


    def application(self, *, version="0.8.0", base=None, package=None, name="model-release-assurance"):
        owned = Path(runtime.__file__).absolute().parent.parent
        location = owned.parent if base is None else Path(base)
        content = owned if package is None else Path(package)
        return SimpleNamespace(metadata={"Name": name}, version=version,
            locate_file=lambda item: location if item == "" else content if item == "model_release_assurance" else location / item)

    def test_only_physically_owned_application_distribution_is_allowed(self):
        result = self.probe(self.roster() + [self.application()])
        self.assertEqual(result, runtime.expected_binding())
        self.assertEqual(set(runtime.LOCKED_VERSIONS), set(value.metadata["Name"] for value in self.roster()))
        self.assertNotIn("model-release-assurance", runtime.LOCKED_VERSIONS)

    def test_owned_application_normalized_name_is_allowed(self):
        self.assertEqual(self.probe(self.roster() + [self.application(name="Model_Release_Assurance")]),
                         runtime.expected_binding())

    def test_wrong_application_version_is_rejected(self):
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(self.roster() + [self.application(version="0.8.1")])

    def test_shadow_application_package_is_rejected(self):
        owned = Path(runtime.__file__).absolute().parent.parent
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(self.roster() + [self.application(package=owned.parent / "shadow/model_release_assurance")])

    def test_matching_package_does_not_excuse_foreign_distribution_base(self):
        owned = Path(runtime.__file__).absolute().parent.parent
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(self.roster() + [self.application(base=owned.parent / "shadow")])

    def test_duplicate_owned_application_metadata_is_rejected(self):
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(self.roster() + [self.application(), self.application(name="Model_Release_Assurance")])

    def test_application_allowance_does_not_mask_a_missing_art_dependency(self):
        values = dict(runtime.LOCKED_VERSIONS)
        values.pop("adversarial-robustness-toolbox")
        with self.assertRaises(runtime.ArtRuntimeUnavailable):
            self.probe(self.roster(values) + [self.application()])

    def test_similarly_named_application_is_still_an_extra_distribution(self):
        with self.assertRaises(runtime.ArtRuntimeError):
            self.probe(self.roster() + [self.application(name="model-release-assurance-shadow")])


class ArtInstalledSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "art"
        self.package.mkdir()
        self.files = {"art/__init__.py": b'"""Fictional package, never imported."""\n',
                      "art/version.py": b'__version__ = "1.20.1"\n',
                      "art/attacks/__init__.py": b""}
        self.pins = {}
        self.rows = []
        for name, raw in self.files.items():
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            sha = hashlib.sha256(raw).hexdigest()
            self.pins[name] = {"sha256": sha, "size_bytes": len(raw)}
            self.rows.append([name, "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(sha)).decode("ascii").rstrip("="), str(len(raw))])
        self.metadata = self.root / ("adversarial_robustness_toolbox-" + runtime.ART_VERSION + ".dist-info")
        self.metadata.mkdir()
        self.metadata_raw = b"Name: adversarial-robustness-toolbox\nVersion: 1.20.1\n"
        (self.metadata / "METADATA").write_bytes(self.metadata_raw)
        self.write_record(self.rows)
        self.distribution = SimpleNamespace(version=runtime.ART_VERSION, locate_file=lambda _: self.root)
        self.spec = SimpleNamespace(origin=str(self.package / "__init__.py"), submodule_search_locations=[str(self.package)])

    def write_record(self, rows):
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        (self.metadata / "RECORD").write_text(buffer.getvalue(), encoding="utf-8", newline="")

    def checked(self):
        with patch.object(runtime, "SOURCE_PINS", self.pins), \
                patch.object(runtime, "METADATA_SHA256", hashlib.sha256(self.metadata_raw).hexdigest()), \
                patch.object(runtime.importlib.util, "find_spec", return_value=self.spec):
            return runtime._checked_distribution(self.distribution)

    def test_verified_source_accepts_pinned_empty_package_marker(self):
        self.assertEqual((self.package / "attacks/__init__.py").stat().st_size, 0)
        self.assertEqual(self.checked(), self.root)

    def test_same_size_source_drift_is_rejected(self):
        path = self.package / "version.py"
        original = path.read_bytes()
        changed = original.replace(b"1.20.1", b"1.20.2")
        self.assertEqual(len(original), len(changed))
        path.write_bytes(changed)
        with self.assertRaises(ValueError):
            self.checked()

    def test_missing_pinned_file_is_rejected(self):
        (self.package / "attacks/__init__.py").unlink()
        with self.assertRaises(ValueError):
            self.checked()

    def test_unpinned_bytecode_is_rejected(self):
        (self.package / "__pycache__").mkdir()
        (self.package / "__pycache__/version.pyc").write_bytes(b"unapproved")
        with self.assertRaises(ValueError):
            self.checked()

    def test_record_hash_and_declared_size_are_checked(self):
        changes = [copy.deepcopy(self.rows), copy.deepcopy(self.rows)]
        changes[0][1][1] = "sha256=" + "a" * 43
        changes[1][1][2] = str(int(changes[1][1][2]) + 1)
        for index, rows in enumerate(changes):
            with self.subTest(index=index):
                self.write_record(rows)
                with self.assertRaises(ValueError):
                    self.checked()

    def test_duplicate_and_malformed_record_rows_are_rejected(self):
        changes = [self.rows + [self.rows[0]], [self.rows[0][:2]], []]
        for index, rows in enumerate(changes):
            with self.subTest(index=index):
                self.write_record(rows)
                with self.assertRaises(ValueError):
                    self.checked()

    def test_record_must_cover_every_pinned_source(self):
        self.write_record(self.rows[:-1])
        with self.assertRaises(ValueError):
            self.checked()

    def test_changed_metadata_is_rejected(self):
        (self.metadata / "METADATA").write_bytes(self.metadata_raw + b"changed")
        with self.assertRaises(ValueError):
            self.checked()

    def test_wrong_distribution_version_is_rejected(self):
        self.distribution.version = "1.20.2"
        with self.assertRaises(runtime.ArtRuntimeError):
            self.checked()

    def test_invalid_package_spec_origin_or_search_path_is_rejected(self):
        changes = [None, SimpleNamespace(origin=str(self.root / "foreign.py"), submodule_search_locations=[str(self.package)]),
                   SimpleNamespace(origin=str(self.package / "__init__.py"), submodule_search_locations=[str(self.root)])]
        for index, spec in enumerate(changes):
            with self.subTest(index=index):
                self.spec = spec
                with self.assertRaises(runtime.ArtRuntimeError):
                    self.checked()

    def test_imported_package_and_submodule_locations_are_bound(self):
        package = SimpleNamespace(__file__=str(self.package / "__init__.py"), __spec__=self.spec, __path__=[str(self.package)])
        module = SimpleNamespace(__file__=str(self.package / "version.py"),
                                 __spec__=SimpleNamespace(origin=str(self.package / "version.py")))
        with patch.dict(runtime.sys.modules, {"art": package, "art.version": module}):
            self.assertEqual(self.checked(), self.root)
            module.__file__ = str(self.root / "foreign.py")
            with self.assertRaises(runtime.ArtRuntimeError):
                self.checked()

    def test_imported_package_search_path_is_bound(self):
        package = SimpleNamespace(__file__=str(self.package / "__init__.py"), __spec__=self.spec, __path__=[str(self.root)])
        with patch.dict(runtime.sys.modules, {"art": package}):
            with self.assertRaises(runtime.ArtRuntimeError):
                self.checked()

    def test_unknown_or_none_imported_module_is_rejected(self):
        for module in (None, SimpleNamespace(__file__=str(self.package / "unexpected.py"),
                                           __spec__=SimpleNamespace(origin=str(self.package / "unexpected.py")))):
            with self.subTest(module=module), patch.dict(runtime.sys.modules, {"art.unexpected": module}):
                with self.assertRaises(runtime.ArtRuntimeError):
                    self.checked()

    def test_hardlinked_source_is_rejected(self):
        source = self.package / "version.py"
        os.link(source, self.root / "alias.py")
        self.assertGreater(source.stat().st_nlink, 1)
        with self.assertRaises(ValueError):
            self.checked()

    def test_hardlinked_metadata_is_rejected(self):
        source = self.metadata / "METADATA"
        os.link(source, self.root / "metadata-alias")
        with self.assertRaises(ValueError):
            self.checked()

    def simulated_link(self, target, *, symbolic=False):
        original = Path.lstat
        def changed(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path.absolute() != target.absolute():
                return info
            value = SimpleNamespace(**{key: getattr(info, key) for key in dir(info) if key.startswith("st_")})
            if symbolic:
                value.st_mode = stat.S_IFLNK | stat.S_IMODE(info.st_mode)
            else:
                value.st_file_attributes = getattr(info, "st_file_attributes", 0) | 0x400
            return value
        return patch.object(Path, "lstat", changed)

    def test_symbolic_source_path_is_rejected_before_open(self):
        with self.simulated_link(self.package / "version.py", symbolic=True), \
                patch.object(runtime.os, "open", wraps=runtime.os.open) as opened:
            with self.assertRaises(ValueError):
                self.checked()
            self.assertNotIn(str(self.package / "version.py"), [str(call.args[0]) for call in opened.call_args_list])

    def test_file_reparse_point_is_rejected(self):
        with self.simulated_link(self.package / "version.py"):
            with self.assertRaises(ValueError):
                self.checked()

    def test_directory_reparse_point_is_rejected(self):
        with self.simulated_link(self.package / "attacks"):
            with self.assertRaises(runtime.ArtRuntimeError):
                self.checked()

    def test_tampered_source_pin_is_rejected_without_restamping_record(self):
        self.pins["art/version.py"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.checked()


if __name__ == "__main__":
    unittest.main()
