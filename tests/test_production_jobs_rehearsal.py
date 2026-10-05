"""Rehearsal evidence and lifecycle tests use only ephemeral public fixtures."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("mra_jobs_rehearsal", Path(__file__).resolve().parents[1] / "scripts/rehearse_fixture_jobs.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


@unittest.skipUnless(shutil.which("git"), "Git is required for safe ignored outputs")
class ProductionJobsRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-job-rehearsal-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True, check=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.snapshot = {"scope": "unit-test source observation", "files": [], "sha256": "a" * 64}

    def result(self, name="run"):
        return json.loads((self.root / ".local" / name / "result.json").read_text(encoding="utf-8"))

    def run_fixture(self, **kwargs):
        with mock.patch.object(CLI, "source_snapshot", return_value=self.snapshot):
            return CLI.run_rehearsal(root=self.root, output=".local/" + kwargs.get("name", "run"))

    def test_real_signed_job_restart_and_spent_input_rehearsal_keeps_no_tokens_or_keys(self):
        issued = []
        original = CLI.FixtureTokenIssuer.issue
        def remember(issuer, *args, **kwargs):
            token = original(issuer, *args, **kwargs)
            issued.append(token)
            return token
        with mock.patch.object(CLI.FixtureTokenIssuer, "issue", remember):
            result = self.run_fixture()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(result["checks"]), 12)
        self.assertEqual({check["name"] for check in result["checks"]}, CLI.REQUIRED_CHECKS)
        self.assertTrue(all(check["passed"] for check in result["checks"]))
        self.assertEqual(result["summary"], {"job_state": "succeeded", "categories": 2, "total": 19,
                                            "attempts": 1, "broker_history_entries": 2})
        for key, value in CLI.FLAGS.items():
            self.assertIs(result[key], value)
        self.assertEqual(result, self.result())
        self.assertLess((self.root / ".local/run/result.json").stat().st_size, CLI.MAX_REPORT_BYTES)
        self.assertEqual(len(issued), 3)
        for path in (self.root / ".local/run").rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                self.assertNotIn(b"PRIVATE KEY", content)
                self.assertNotIn(b"BEGIN PUBLIC KEY", content)
                for token in issued:
                    self.assertNotIn(token.encode(), content)
        self.assertTrue((self.root / ".local/run/jobs/jobs.sqlite").is_file())
        self.assertEqual(list((self.root / ".local/run/objects-after-restart").iterdir()), [])

    def test_failed_workflow_retains_safe_result_without_exception_details(self):
        with mock.patch.object(CLI, "exercise_workflow", side_effect=RuntimeError("raw-token-or-key-must-not-appear")):
            result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"stage": "fixture_workflow", "type": "RuntimeError"}])
        self.assertNotIn("raw-token-or-key", json.dumps(result))
        self.assertEqual(result, self.result())
        self.assertEqual(result["checks"], [{"name": "source_unchanged", "passed": True}])

    def test_empty_or_partial_workflow_never_reports_passed(self):
        with mock.patch.object(CLI, "exercise_workflow", return_value=None):
            result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"stage": "milestones", "type": "IncompleteWorkflow"}])

    def test_existing_output_and_traversal_are_refused_without_overwriting_evidence(self):
        with mock.patch.object(CLI, "exercise_workflow", side_effect=RuntimeError):
            self.run_fixture()
        saved = (self.root / ".local/run/result.json").read_bytes()
        with self.assertRaises(CLI._BASELINE.BaselineError):
            self.run_fixture()
        self.assertEqual(saved, (self.root / ".local/run/result.json").read_bytes())
        for output in (".local/../outside", "outside/run"):
            with self.subTest(output=output), self.assertRaises(CLI._BASELINE.BaselineError):
                CLI.run_rehearsal(root=self.root, output=output)
        self.assertFalse((self.root / "outside").exists())

    def source_tree(self):
        names = set(CLI.SOURCE_FILES)
        names.update("src/model_release_assurance/" + group + "/__init__.py" for group in CLI.SOURCE_GROUPS)
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# trusted unit fixture\n", encoding="utf-8")

    def test_source_snapshot_rescans_files_and_final_mutation_fails(self):
        self.source_tree()
        before = CLI.source_snapshot(self.root)
        def changed(output, report):
            for name in sorted(CLI.REQUIRED_CHECKS - {"source_unchanged"}):
                CLI._check(report, name, True)
            (self.root / "src/model_release_assurance/production_jobs/added.py").write_text("# added during run\n", encoding="utf-8")
        with mock.patch.object(CLI, "exercise_workflow", side_effect=changed):
            result = CLI.run_rehearsal(root=self.root, output=".local/run")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checks"][-1], {"name": "source_unchanged", "passed": False})
        self.assertEqual(result["errors"], [{"stage": "source_stability", "type": "RehearsalError"}])
        self.assertNotEqual(before, CLI.source_snapshot(self.root))
        self.assertEqual(result, self.result())

    def test_source_snapshot_rejects_missing_required_package(self):
        self.source_tree()
        (self.root / "src/model_release_assurance/production_jobs/__init__.py").unlink()
        result = CLI.run_rehearsal(root=self.root, output=".local/run")
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["source"])
        self.assertFalse((self.root / ".local/run/jobs").exists())

    def test_cli_has_only_output_option_and_preserves_failure_exit_codes(self):
        with mock.patch.object(CLI, "ROOT", self.root), mock.patch.object(CLI, "source_snapshot", return_value=self.snapshot), mock.patch.object(CLI, "exercise_workflow", side_effect=RuntimeError), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(CLI.main(["--output", ".local/failure"]), 1)
            self.assertEqual(CLI.main(["--output", ".local/failure"]), 2)
        with mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
            CLI.main(["--output", ".local/no-data", "--data", "private.csv"])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / ".local/no-data").exists())


if __name__ == "__main__":
    unittest.main()
