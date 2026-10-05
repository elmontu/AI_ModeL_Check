"""Bounded real public-fault rehearsal, evidence redaction and safe CLI output."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_monitoring import rehearsal
from model_release_assurance.production_monitoring.contracts import FLAGS
from model_release_assurance.production_registry.rehearsal import FixtureTokenIssuer

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mra_monitoring_cli", ROOT / "scripts/rehearse_monitoring.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class MonitoringRehearsalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-monitoring-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True, check=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.source = {"scope": "test", "files": [], "sha256": "a" * 64}

    def run_fixture(self, name="run"):
        with mock.patch.object(CLI, "source_snapshot", return_value=self.source):
            return CLI.run_rehearsal(root=self.root, output=".local/" + name, profile="local_public_fixture")

    def synthetic_result(self):
        return {"status": "passed", "checks": [{"name": name, "passed": True}
            for name in sorted(rehearsal.REQUIRED_CHECKS)], **FLAGS}

    def test_actual_four_faults_recover_with_no_credentials_or_external_notifications(self):
        issued = []
        original = FixtureTokenIssuer.issue
        def remember(issuer, *args, **kwargs):
            token = original(issuer, *args, **kwargs)
            issued.append(token)
            return token
        with mock.patch.object(FixtureTokenIssuer, "issue", remember):
            result = self.run_fixture()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual({row["name"] for row in result["checks"]}, CLI.REQUIRED_CHECKS)
        self.assertTrue(all(row["passed"] for row in result["checks"]))
        self.assertEqual(result["summary"], {"faults_observed": 4, "healthy_observations": 4,
            "resolved_incidents": 4, "local_alert_deliveries": 4, "worker_timeout_seconds": 1,
            "synthetic_authority_clock": True})
        faults = result["evidence"]["fault_checks"]
        self.assertEqual(faults["worker"]["failed_status"], "timed_out")
        self.assertTrue(faults["worker"]["cleanup_confirmed"])
        self.assertEqual(faults["worker"]["recovery_total"], 19)
        self.assertEqual(faults["ledger"]["engineering_charge_units"], 1)
        self.assertTrue(faults["ledger"]["same_receipt_recovered"])
        self.assertFalse(faults["ledger"]["privacy_accounting_claimed"])
        for key, value in FLAGS.items():
            self.assertIs(result[key], value)
        self.assertTrue(issued)
        output = self.root / ".local/run"
        self.assertEqual(result, json.loads((output / "result.json").read_bytes()))
        for path in output.rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                self.assertNotIn(b"PRIVATE KEY", raw)
                for token in issued:
                    self.assertNotIn(token.encode(), raw)

    def test_production_default_refuses_before_output_and_source_inspection(self):
        with mock.patch.object(CLI, "source_snapshot") as source, mock.patch.object(CLI, "exercise") as exercise:
            with self.assertRaises(CLI.ProfileRefused):
                CLI.run_rehearsal(root=self.root, output=".local/refused")
            with mock.patch.object(CLI, "ROOT", self.root), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(CLI.main(["--output", ".local/refused"]), 2)
                self.assertEqual(json.loads(out.getvalue())["status"], "profile_refused")
        source.assert_not_called()
        exercise.assert_not_called()
        self.assertFalse((self.root / ".local").exists())

    def test_direct_rehearsal_rejects_production_before_mkdir(self):
        with self.assertRaises(rehearsal.RehearsalError):
            rehearsal.exercise(self.root / "refused")
        self.assertFalse((self.root / "refused").exists())

    def test_failed_workflow_retains_safe_type_and_source_check(self):
        with mock.patch.object(CLI, "exercise", side_effect=ValueError("secret-token private/path")):
            result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"stage": "fixture_workflow", "type": "ValueError"}])
        self.assertEqual(result["checks"], [{"name": "source_unchanged", "passed": True}])
        saved = (self.root / ".local/run/result.json").read_text()
        self.assertNotIn("secret-token", saved)
        self.assertNotIn("private/path", saved)
        self.assertEqual(json.loads(saved), result)

    def test_existing_traversing_unignored_and_outside_output_are_refused(self):
        with mock.patch.object(CLI, "exercise", side_effect=ValueError):
            self.run_fixture()
        path = self.root / ".local/run/result.json"
        saved = path.read_bytes()
        for output in (".local/run", ".local/../outside", "outside/run", str(self.root.parent / "outside")):
            with self.subTest(output=output), self.assertRaises(CLI._BASELINE.BaselineError):
                CLI.run_rehearsal(root=self.root, output=output, profile="local_public_fixture")
        self.assertEqual(path.read_bytes(), saved)

    def test_missing_duplicate_false_and_foreign_milestones_cannot_pass(self):
        for mutation in ("missing", "duplicate", "false", "foreign"):
            result = self.synthetic_result()
            if mutation == "missing": result["checks"].pop()
            if mutation == "duplicate": result["checks"][-1] = dict(result["checks"][0])
            if mutation == "false": result["checks"][0]["passed"] = False
            if mutation == "foreign": result["checks"][0]["name"] = "fictional_success"
            with self.subTest(mutation=mutation), mock.patch.object(CLI, "exercise", return_value=result):
                report = self.run_fixture(mutation)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["errors"][-1]["type"], "IncompleteWorkflow")

    def test_weakened_non_authorization_flags_are_refused(self):
        result = self.synthetic_result()
        result["can_clear"] = True
        with mock.patch.object(CLI, "exercise", return_value=result):
            report = self.run_fixture()
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["can_clear"])

    def test_source_changes_fail_even_when_all_fault_milestones_pass(self):
        changed = {**self.source, "sha256": "b" * 64}
        with mock.patch.object(CLI, "source_snapshot", side_effect=[self.source, changed]), \
                mock.patch.object(CLI, "exercise", return_value=self.synthetic_result()):
            result = CLI.run_rehearsal(root=self.root, output=".local/run", profile="local_public_fixture")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checks"][-1], {"name": "source_unchanged", "passed": False})
        self.assertEqual(result["errors"][-1]["stage"], "source_stability")

    def test_missing_source_fails_before_exercise_with_retained_result(self):
        with mock.patch.object(CLI, "exercise") as exercise:
            report = CLI.run_rehearsal(root=self.root, output=".local/run", profile="local_public_fixture")
        exercise.assert_not_called()
        self.assertEqual(report["status"], "failed")
        self.assertTrue((self.root / ".local/run/result.json").is_file())

    def test_source_inventory_covers_monitoring_fixed_worker_and_identity(self):
        snapshot = CLI.source_snapshot(ROOT)
        names = {row["path"] for row in snapshot["files"]}
        self.assertTrue(set(CLI.SOURCE_FILES).issubset(names))
        for package, name in (("production_jobs", "executor"), ("production_identity", "policy"),
                              ("production_witness", "rehearsal"), ("production_storage", "backend")):
            self.assertIn("src/model_release_assurance/" + package + "/" + name + ".py", names)

    def test_cli_exit_codes_and_no_arbitrary_program_or_data_inputs(self):
        args = ["--profile", "local_public_fixture", "--output", ".local/failure"]
        with mock.patch.object(CLI, "ROOT", self.root), \
                mock.patch.object(CLI, "source_snapshot", return_value=self.source), \
                mock.patch.object(CLI, "exercise", side_effect=RuntimeError), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(CLI.main(args), 1)
            self.assertEqual(CLI.main(args), 2)
        for option in ("--data", "--python", "--url"):
            with self.subTest(option=option), mock.patch("sys.stderr", new_callable=io.StringIO), \
                    self.assertRaises(SystemExit) as error:
                CLI.main(["--profile", "local_public_fixture", "--output", ".local/invalid", option, "private"])
            self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / ".local/invalid").exists())

    def test_oversized_report_fails_without_writing_unbounded_evidence(self):
        result = self.synthetic_result()
        result["evidence"] = {"unexpected": "x" * CLI.MAX_REPORT_BYTES}
        with mock.patch.object(CLI, "exercise", return_value=result):
            report = self.run_fixture()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["errors"][0]["type"], "InvalidOrOversizedReport")
        self.assertLess((self.root / ".local/run/result.json").stat().st_size, 1024)

    def test_interrupted_worker_injection_always_restores_original_bootstrap(self):
        original = rehearsal.executor._write_request
        runner = mock.Mock()
        runner.run.side_effect = RuntimeError("fixture interruption")
        with mock.patch.object(rehearsal.executor, "FixtureProcessRunner", return_value=runner):
            with self.assertRaises(RuntimeError):
                rehearsal._worker(self.root / "worker", mock.Mock(), mock.Mock())
        self.assertIs(rehearsal.executor._write_request, original)


if __name__ == "__main__":
    unittest.main()
