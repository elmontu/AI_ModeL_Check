"""Local build-baseline safeguards, using tiny temporary Git repositories/wheels."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

SPEC = importlib.util.spec_from_file_location("verify_build_baseline", Path(__file__).resolve().parents[1] / "scripts/verify_build_baseline.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
VERSIONS = {"pip": "25.0.1", "setuptools": "84.0.0", "wheel": "0.48.0", "packaging": "26.3"}
LOCK = "".join(f"{name}=={version}\n" for name, version in VERSIONS.items()).encode()


def make_wheel(path, files, *, corrupt_record=False, metadata_extra=b""):
    members = dict(files)
    info = "model_release_assurance-0.0.0.dist-info"
    members[info + "/METADATA"] = b"Metadata-Version: 2.1\nName: model-release-assurance\nVersion: 0.0.0\n" + metadata_extra
    members[info + "/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = info + "/RECORD"
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for name, content in sorted(members.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        writer.writerow([name, "sha256=" + ("invalid" if corrupt_record else digest), len(content)])
    writer.writerow([record, "", ""])
    members[record] = buffer.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in sorted(members.items()):
            archive.writestr(zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), content)
    return path


@unittest.skipUnless(shutil.which("git"), "Git is required for build source-baseline tests")
class BuildBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-build-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.write(".gitignore", b".local/\n__pycache__/\n*.egg-info/\n")
        self.write("requirements-build.lock", LOCK)
        self.write("README.md", b"Fixture\n")
        self.write("src/model_release_assurance/__init__.py", b"VALUE = 1\n")
        self.write("src/model_release_assurance/py.typed", b"")
        self.write("src/model_release_assurance/console/static/app.js", b"console.log('fixture');\n")
        self.write("docs/publication/retired.json", b'{"retired":true}\n')
        self.git("add", "--all")
        self.git("-c", "user.name=Baseline Fixture", "-c", "user.email=baseline@example.invalid", "commit", "-q", "-m", "Fixture")

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def package_files(self):
        return {path.relative_to(self.root / "src").as_posix(): path.read_bytes()
                for path in (self.root / "src/model_release_assurance").rglob("*") if path.is_file()}

    @staticmethod
    def fake_builder(snapshot, directory, env, log):
        directory.mkdir()
        log.write_text("Test stub; no builder executed.\n", encoding="utf-8")
        files = {path.relative_to(snapshot / "src").as_posix(): path.read_bytes()
                 for path in (snapshot / "src/model_release_assurance").rglob("*") if path.is_file()}
        return make_wheel(directory / "model_release_assurance-0.0.0-py3-none-any.whl", files)

    def test_snapshot_includes_untracked_sources_and_records_retired_deletions(self):
        new = self.write("src/model_release_assurance/new_gate.py", b"NEW = True\n")
        (self.root / "docs/publication/retired.json").unlink()
        self.write(".local/ignored-private.json", b"ignored")
        self.write("src/model_release_assurance/__pycache__/ignored.pyc", b"ignored")
        source = BUILD.capture_source(self.root)
        self.assertIn(new.relative_to(self.root).as_posix(), source["nonignored_untracked_paths"])
        self.assertEqual(source["tracked_deletions"], ["docs/publication/retired.json"])
        names = {row["path"] for row in source["files"]}
        self.assertNotIn("docs/publication/retired.json", names)
        self.assertFalse(any("ignored" in name or ".git/" in name for name in names))
        output = BUILD.prepare_output(self.root, ".local/baseline")
        BUILD.copy_snapshot(self.root, source, output / "source")
        self.assertEqual((output / "source/src/model_release_assurance/new_gate.py").read_bytes(), new.read_bytes())
        self.assertFalse((output / "source/docs/publication/retired.json").exists())
        BUILD.verify_source(self.root, source)

    def test_staged_retirement_is_recorded_without_restoring_deleted_bytes(self):
        retired = "docs/publication/retired.json"
        self.git("rm", "--", retired)
        source = BUILD.capture_source(self.root)
        self.assertEqual(source["staged_deletions"], [retired])
        self.assertEqual(source["index_worktree_deletions"], [])
        self.assertEqual(source["tracked_deletions"], [retired])
        self.assertNotIn(retired, {item["path"] for item in source["files"]})
        output = BUILD.prepare_output(self.root, ".local/staged-deletion")
        BUILD.copy_snapshot(self.root, source, output / "source")
        self.assertFalse((output / "source" / retired).exists())
        BUILD.verify_source(self.root, source)

    def test_inspection_does_not_change_git_index(self):
        before = (self.root / ".git/index").read_bytes()
        captured = BUILD.capture_source(self.root)
        BUILD.verify_source(self.root, captured)
        self.assertEqual((self.root / ".git/index").read_bytes(), before)
        self.assertEqual(captured["index_entries_sha256"], hashlib.sha256(self.git("ls-files", "--stage", "-z")).hexdigest())

    def test_source_bytes_changed_before_snapshot_are_refused(self):
        source = BUILD.capture_source(self.root)
        self.write("src/model_release_assurance/__init__.py", b"VALUE = 2\n")
        output = BUILD.prepare_output(self.root, ".local/baseline")
        with self.assertRaisesRegex(BUILD.BaselineError, "changed while snapshotting"):
            BUILD.copy_snapshot(self.root, source, output / "source")
        with self.assertRaisesRegex(BUILD.BaselineError, "changed during"):
            BUILD.verify_source(self.root, source)

    def test_source_new_file_and_index_changes_are_refused(self):
        source = BUILD.capture_source(self.root)
        path = self.write("new.txt", b"new")
        with self.assertRaises(BUILD.BaselineError):
            BUILD.verify_source(self.root, source)
        self.git("add", "new.txt")
        path.unlink()
        with self.assertRaises(BUILD.BaselineError):
            BUILD.verify_source(self.root, source)

    def test_output_refuses_overwrite_escape_and_nonignored_destination(self):
        output = BUILD.prepare_output(self.root, ".local/baseline")
        sentinel = output / "sentinel"
        sentinel.write_bytes(b"keep")
        for choice in (".local/baseline", "outside", ".local", ".local/../outside", self.root.parent / "outside"):
            with self.subTest(choice=choice), self.assertRaises(BUILD.BaselineError):
                BUILD.prepare_output(self.root, choice)
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.write(".gitignore", b"")
        with self.assertRaisesRegex(BUILD.BaselineError, "ignored by Git"):
            BUILD.prepare_output(self.root, ".local/not-ignored")

    def test_symlink_source_and_output_parent_are_refused(self):
        target = self.root / "README.md"
        link = self.root / "linked.md"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Platform does not permit test symlink creation")
        with self.assertRaisesRegex(BUILD.BaselineError, "Symlink or reparse"):
            BUILD.capture_source(self.root)
        link.unlink()
        local = self.root / ".local"
        local.mkdir()
        (local / "redirect").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(BUILD.BaselineError, "Symlink or reparse"):
            BUILD.prepare_output(self.root, ".local/redirect/new")

    def test_build_lock_rejects_inexact_missing_duplicate_or_wrong_versions(self):
        self.assertEqual(BUILD.check_build_lock(LOCK, VERSIONS), VERSIONS)
        wrong = dict(VERSIONS, pip="0.0.0")
        with self.assertRaisesRegex(BUILD.BaselineError, "versions differ"):
            BUILD.check_build_lock(LOCK, wrong)
        for content in (LOCK.replace(b"pip==", b"pip>="), LOCK + b"pip==25.0.1\n", b"pip==25.0.1\n"):
            with self.subTest(content=content), self.assertRaises(BUILD.BaselineError):
                BUILD.check_build_lock(content, VERSIONS)

    def test_wheel_inventory_and_record_are_verified(self):
        source = BUILD.capture_source(self.root)
        wheel = make_wheel(self.root / ".local-good.whl", self.package_files())
        result = BUILD.verify_wheel(wheel, source)
        self.assertEqual(result["verified_package_files"], 3)
        self.assertEqual(result["verified_record_entries"], 6)

    def test_missing_extra_and_mutated_wheel_member_are_refused(self):
        source = BUILD.capture_source(self.root)
        files = self.package_files()
        key = "model_release_assurance/__init__.py"
        missing = dict(files)
        missing.pop(key)
        changed = dict(files, **{key: b"VALUE = 7\n"})
        extra = dict(files, **{"model_release_assurance/secret.txt": b"unexpected"})
        for index, content in enumerate((missing, changed, extra)):
            wheel = make_wheel(self.root / f"bad-{index}.whl", content)
            with self.subTest(index=index), self.assertRaises(BUILD.BaselineError):
                BUILD.verify_wheel(wheel, source)

    def test_invalid_wheel_record_is_refused_even_when_source_bytes_match(self):
        source = BUILD.capture_source(self.root)
        wheel = make_wheel(self.root / "bad-record.whl", self.package_files(), corrupt_record=True)
        with self.assertRaisesRegex(BUILD.BaselineError, "RECORD hash"):
            BUILD.verify_wheel(wheel, source)

    def test_success_records_two_equal_wheels_and_preserves_failed_run_outputs(self):
        with mock.patch.object(BUILD, "builder_versions", return_value=VERSIONS):
            result = BUILD.run_baseline(self.root, ".local/good", builder=self.fake_builder)
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["source_stable_at_end"])
        self.assertEqual(result["wheels"][0]["sha256"], result["wheels"][1]["sha256"])
        self.assertTrue((self.root / ".local/good/runtime.json").is_file())
        self.assertTrue((self.root / ".local/good/source-manifest.json").is_file())
        with mock.patch.object(BUILD, "builder_versions", return_value=dict(VERSIONS, wheel="0.0.0")):
            failed = BUILD.run_baseline(self.root, ".local/bad-lock", builder=self.fake_builder)
        self.assertEqual(failed["status"], "failed")
        self.assertTrue((self.root / ".local/bad-lock/source-manifest.json").is_file())
        self.assertEqual(json.loads((self.root / ".local/bad-lock/results.json").read_text())["status"], "failed")
        self.assertTrue((self.root / ".local/good/source-a/README.md").is_file())

    def test_valid_different_wheels_fail_repeatability_and_builds_have_separate_temp(self):
        temporary_directories = []
        def varying_builder(snapshot, directory, env, log):
            wheel = self.fake_builder(snapshot, directory, env, log)
            temporary_directories.append(env["TEMP"])
            if len(temporary_directories) == 2:
                files = {path.relative_to(snapshot / "src").as_posix(): path.read_bytes()
                         for path in (snapshot / "src/model_release_assurance").rglob("*") if path.is_file()}
                make_wheel(wheel, files, metadata_extra=b"Summary: differs between builds\n")
            return wheel
        with mock.patch.object(BUILD, "builder_versions", return_value=VERSIONS):
            result = BUILD.run_baseline(self.root, ".local/differing", builder=varying_builder)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["source_stable_at_end"])
        self.assertEqual(len(result["wheels"]), 2)
        self.assertNotEqual(result["wheels"][0]["sha256"], result["wheels"][1]["sha256"])
        self.assertTrue(any("differ byte-for-byte" in error for error in result["errors"]))
        self.assertEqual(len(set(temporary_directories)), 2)
        self.assertTrue(all(Path(path).is_dir() for path in temporary_directories))

    def test_source_mutation_during_build_fails_end_run_check_and_retains_outputs(self):
        calls = []
        def mutate(snapshot, directory, env, log):
            wheel = self.fake_builder(snapshot, directory, env, log)
            calls.append(snapshot)
            if len(calls) == 1:
                self.write("README.md", b"changed during build\n")
            return wheel
        with mock.patch.object(BUILD, "builder_versions", return_value=VERSIONS):
            result = BUILD.run_baseline(self.root, ".local/changed", builder=mutate)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["source_stable_at_end"])
        self.assertEqual(len(result["wheels"]), 2)
        self.assertTrue((self.root / ".local/changed/source-a/README.md").is_file())

    def test_builder_failure_leaves_manifest_logs_and_failure_result(self):
        def failure(snapshot, directory, env, log):
            log.write_text("Injected failure\n", encoding="utf-8")
            raise BUILD.BaselineError("fixture builder failed")
        with mock.patch.object(BUILD, "builder_versions", return_value=VERSIONS):
            result = BUILD.run_baseline(self.root, ".local/failed", builder=failure)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["source_stable_at_end"])
        self.assertTrue((self.root / ".local/failed/build-a.log").is_file())
        self.assertTrue((self.root / ".local/failed/source-b/README.md").is_file())

    def test_environment_removes_python_and_pip_overrides_and_uses_local_temp(self):
        output = BUILD.prepare_output(self.root, ".local/env")
        with mock.patch.dict(os.environ, {"PYTHONPATH": "outside", "PIP_INDEX_URL": "https://invalid.example", "PYTHONHOME": "outside"}):
            env = BUILD.build_environment(output, 1234567890)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PIP_INDEX_URL", env)
        self.assertEqual(env["SOURCE_DATE_EPOCH"], "1234567890")
        self.assertEqual(Path(env["TEMP"]), output / "tmp")
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)


if __name__ == "__main__":
    unittest.main()
