"""Required CI profile fails closed without changing the ordinary unittest suite."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("required_test_runner", Path(__file__).resolve().parents[1] / "scripts/run_required_tests.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
FIXTURE_NAME = "test_required_profile_fixture_7f02"


def tiny_suite(method=None):
    def passing(self):
        self.assertTrue(True)
    case = type("RequiredFixture", (unittest.TestCase,), {"test_behavior": method or passing})
    return unittest.defaultTestLoader.loadTestsFromTestCase(case)


@unittest.skipUnless(shutil.which("git"), "Git is required to validate ignored report destinations")
class RequiredProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-required-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        self.blueprint = self.root / "deploy/agency-private-cloud/blueprint.json"
        self.blueprint.parent.mkdir(parents=True)
        self.blueprint.write_text("{}\n", encoding="utf-8")
        (self.root / "requirements.lock").write_text("# runtime fixture\n", encoding="utf-8")
        for name in RUNNER.REQUIRED_SOURCE_INPUTS:
            path = self.root / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
        self.fixture = self.root / "tests" / (FIXTURE_NAME + ".py")
        self.fixture.write_text("# Unit-test source fixture\n", encoding="utf-8")
        self.addCleanup(sys.modules.pop, FIXTURE_NAME, None)

    def run_fixture(self, *, output=".local/run", suite_loader=lambda path: tiny_suite(), patterns=None,
                    required_temporal=(), ownership=None):
        with mock.patch.object(RUNNER, "package_ownership", return_value=ownership or []):
            return RUNNER.run_profile(self.root, output, suite_loader=suite_loader,
                                      patterns=patterns or (self.fixture.name,), required_temporal=required_temporal)

    def assert_persisted(self, result, output=".local/run"):
        report = json.loads((self.root / output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(report, result)
        self.assertIn("Required profile result: " + result["status"], (self.root / output / "tests.log").read_text(encoding="utf-8"))

    def test_passing_suite_records_test_ids_runtime_hashes_and_readable_log(self):
        result = self.run_fixture()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["counts"]["run"], 1)
        self.assertEqual(result["counts"]["selected"], 1)
        self.assertEqual(len(result["selected_test_ids"]), 1)
        self.assertEqual(result["selected_modules"][0]["test_count"], 1)
        self.assertTrue(result["runtime"]["executable"])
        recorded = {item["path"]: item["sha256"] for item in result["source_hashes"]}
        self.assertIn("tests/" + self.fixture.name, recorded)
        self.assertIn("deploy/agency-private-cloud/blueprint.json", recorded)
        self.assert_persisted(result)

    def test_dependency_skip_is_a_failure_and_preserves_reason(self):
        @unittest.skip("optional HTTP dependencies unavailable")
        def unavailable(self):
            pass
        result = self.run_fixture(suite_loader=lambda path: tiny_suite(unavailable))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"]["skipped"], 1)
        self.assertIn("dependencies unavailable", result["skips"][0]["reason"])
        self.assertEqual(result["missing_dependency_reasons"], result["skips"])
        self.assert_persisted(result)

    def test_actual_missing_module_import_retains_discovery_and_error_evidence(self):
        self.fixture.write_text("import mra_deliberately_missing_dependency_7f02\n", encoding="utf-8")
        result = self.run_fixture(suite_loader=None)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"]["errors"], 1)
        self.assertTrue(result["discovery_problems"])
        self.assertIn("mra_deliberately_missing_dependency_7f02", result["missing_dependency_reasons"][0]["reason"])
        self.assert_persisted(result)

    def test_real_module_optional_dependency_skip_cannot_pass(self):
        self.fixture.write_text("import unittest\ntry:\n    import mra_deliberately_missing_dependency_7f02\nexcept ImportError as error:\n    raise unittest.SkipTest('optional dependency unavailable: ' + str(error))\n", encoding="utf-8")
        result = self.run_fixture(suite_loader=None)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"]["skipped"], 1)
        self.assertTrue(result["missing_dependency_reasons"])
        self.assert_persisted(result)

    def test_missing_pattern_and_required_temporal_module_fail_even_if_other_tests_pass(self):
        result = self.run_fixture(patterns=(self.fixture.name, "test_required_but_missing.py"),
                                  required_temporal=("test_temporal_red_team.py",))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"]["run"], 1)
        self.assertTrue(any("matched no files" in issue for issue in result["discovery_problems"]))
        self.assertTrue(any("temporal module is missing" in issue for issue in result["discovery_problems"]))
        self.assert_persisted(result)

    def test_empty_file_and_zero_profile_fail(self):
        result = self.run_fixture(suite_loader=lambda path: unittest.TestSuite())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"]["run"], 0)
        self.assertTrue(any("module contains zero tests" in issue for issue in result["discovery_problems"]))
        self.assertTrue(any("profile contains zero tests" in issue for issue in result["discovery_problems"]))
        self.assert_persisted(result)

    def test_assertion_failure_is_nonpassing_and_keeps_traceback(self):
        def failing(self):
            self.assertEqual("actual", "expected")
        result = self.run_fixture(suite_loader=lambda path: tiny_suite(failing))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"]["failures"], 1)
        self.assertIn("AssertionError", result["failures"][0]["reason"])
        self.assert_persisted(result)

    def test_expected_failure_and_unexpected_success_both_fail(self):
        @unittest.expectedFailure
        def expected(self):
            self.fail("known but still blocking")
        @unittest.expectedFailure
        def unexpected(self):
            pass
        for name, method, count in (("expected", expected, "expected_failures"), ("unexpected", unexpected, "unexpected_successes")):
            with self.subTest(name=name):
                result = self.run_fixture(output=".local/" + name, suite_loader=lambda path: tiny_suite(method))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["counts"][count], 1)
                self.assert_persisted(result, ".local/" + name)

    def test_duplicate_ids_fail_and_new_temporal_files_are_selected(self):
        for name in (*RUNNER.REQUIRED_TEMPORAL, "test_temporal_new_coverage.py"):
            (self.root / "tests" / name).write_text("# fixture\n", encoding="utf-8")
        selected, issues = RUNNER.select_modules(self.root, ("test_temporal*.py",), RUNNER.REQUIRED_TEMPORAL)
        self.assertEqual(issues, [])
        self.assertEqual(len(selected), len(RUNNER.REQUIRED_TEMPORAL) + 1)
        result = self.run_fixture(patterns=("test_temporal*.py",), required_temporal=RUNNER.REQUIRED_TEMPORAL)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["duplicate_test_ids"]), 1)
        self.assert_persisted(result)

    def test_discovery_exception_still_persists_failure_reports(self):
        def broken(path):
            raise RuntimeError("injected discovery failure")
        result = self.run_fixture(suite_loader=broken)
        self.assertEqual(result["status"], "failed")
        self.assertIn("injected discovery failure", "\n".join(result["discovery_problems"]))
        self.assertEqual(result["selected_modules"][0]["test_count"], 0)
        self.assert_persisted(result)

    def test_source_outside_repository_and_concurrent_change_fail(self):
        result = self.run_fixture(ownership=[{"module": "model_release_assurance", "path": "/elsewhere", "from_current_source": False}])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("outside this repository" in issue for issue in result["discovery_problems"]))
        def mutate(path):
            path.write_text("# changed during discovery\n", encoding="utf-8")
            return tiny_suite()
        result = self.run_fixture(output=".local/changed", suite_loader=mutate)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("changed during tests" in issue for issue in result["discovery_problems"]))
        self.assert_persisted(result, ".local/changed")

    def test_new_matching_test_file_created_during_execution_fails_profile(self):
        added = self.root / "tests/test_required_profile_added_7f02.py"
        def add_matching_file(case):
            added.write_text("# newly added coverage\n", encoding="utf-8")
        result = self.run_fixture(patterns=("test_required_profile*.py",),
                                  suite_loader=lambda path: tiny_suite(add_matching_file))
        self.assertTrue(added.is_file())
        self.assertEqual(result["counts"]["run"], 1)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("file selection changed" in issue for issue in result["discovery_problems"]))
        self.assert_persisted(result)

    def test_missing_required_blueprint_fails_before_discovery_and_persists_evidence(self):
        self.blueprint.unlink()
        loader = mock.Mock(side_effect=AssertionError("Must not discover without required input"))
        result = self.run_fixture(suite_loader=loader)
        loader.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("blueprint.json" in issue for issue in result["discovery_problems"]))
        self.assert_persisted(result)

    def test_runtime_lock_missing_or_changed_cannot_pass(self):
        runtime_lock = self.root / "requirements.lock"
        runtime_lock.unlink()
        missing = self.run_fixture(output=".local/missing-runtime")
        self.assertEqual(missing["status"], "failed")
        self.assertTrue(any("requirements.lock" in issue for issue in missing["discovery_problems"]))
        self.assert_persisted(missing, ".local/missing-runtime")
        runtime_lock.write_text("# initial runtime\n", encoding="utf-8")
        def change_runtime(case):
            runtime_lock.write_text("# changed runtime\n", encoding="utf-8")
        changed = self.run_fixture(output=".local/changed-runtime",
                                   suite_loader=lambda path: tiny_suite(change_runtime))
        self.assertEqual(changed["status"], "failed")
        self.assertTrue(any("changed during tests" in issue for issue in changed["discovery_problems"]))
        self.assert_persisted(changed, ".local/changed-runtime")

    def test_unselected_python_test_helper_is_hashed_and_cannot_change(self):
        helper = self.root / "tests" / "helper.py"
        helper.write_text("VALUE = 1\n", encoding="utf-8")
        first = self.run_fixture(output=".local/helper-inventory")
        self.assertEqual(first["status"], "passed")
        self.assertIn("tests/helper.py", {item["path"] for item in first["source_hashes"]})
        def mutate(case):
            helper.write_text("VALUE = 2\n", encoding="utf-8")
        changed = self.run_fixture(output=".local/helper-mutation",
                                   suite_loader=lambda source: tiny_suite(mutate))
        self.assertEqual(changed["status"], "failed")
        self.assertTrue(any("changed during tests" in issue for issue in changed["discovery_problems"]))

    def test_build_policy_and_lock_missing_or_changed_cannot_pass(self):
        for index, name in enumerate(RUNNER.REQUIRED_SOURCE_INPUTS):
            if not name.startswith("deploy/build/"):
                continue
            path = self.root / name
            original = path.read_bytes()
            path.unlink()
            missing = self.run_fixture(output=".local/missing-build-" + str(index))
            self.assertEqual(missing["status"], "failed")
            path.write_bytes(original)
            def change(case):
                path.write_bytes(original + b"changed")
            changed = self.run_fixture(output=".local/changed-build-" + str(index),
                                       suite_loader=lambda source: tiny_suite(change))
            self.assertEqual(changed["status"], "failed")
            path.write_bytes(original)

    def test_blueprint_mutation_or_deletion_during_tests_cannot_pass(self):
        for action in ("change", "delete"):
            self.blueprint.write_text("{}\n", encoding="utf-8")
            def mutate(case):
                if action == "change":
                    self.blueprint.write_text('{"changed":true}\n', encoding="utf-8")
                else:
                    self.blueprint.unlink()
            result = self.run_fixture(output=".local/blueprint-" + action,
                                      suite_loader=lambda path: tiny_suite(mutate))
            self.assertEqual(result["counts"]["run"], 1)
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["discovery_problems"])
            self.assert_persisted(result, ".local/blueprint-" + action)

    def test_output_overwrite_escape_and_nonignored_path_are_refused_before_writes(self):
        self.run_fixture()
        before = (self.root / ".local/run/result.json").read_bytes()
        for destination in (".local/run", ".local", "elsewhere", ".local/../escape", self.root.parent / "escaped"):
            with self.subTest(destination=destination), self.assertRaises(RUNNER.RequiredTestsError):
                self.run_fixture(output=destination)
        self.assertEqual((self.root / ".local/run/result.json").read_bytes(), before)
        self.assertFalse((self.root / "elsewhere").exists())
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(RUNNER.RequiredTestsError, "ignored by Git"):
            self.run_fixture(output=".local/not-ignored")
        self.assertFalse((self.root / ".local/not-ignored").exists())


if __name__ == "__main__":
    unittest.main()
