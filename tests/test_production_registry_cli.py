"""Safe PRD15 command evidence and exact complete workflow requirements."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_registry.rehearsal import FixtureTokenIssuer

SPEC = importlib.util.spec_from_file_location("mra_registry_cli", Path(__file__).resolve().parents[1] / "scripts/rehearse_registry_transactions.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class RegistryCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-registry-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True, check=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.snapshot = {"scope": "test", "files": [], "sha256": "a"*64}

    def run_fixture(self, name="run"):
        with mock.patch.object(CLI, "source_snapshot", return_value=self.snapshot):
            return CLI.run_rehearsal(root=self.root, output=".local/" + name)

    def test_actual_signed_migration_and_lost_ack_rehearsal_retains_no_credentials(self):
        issued = []; original = FixtureTokenIssuer.issue
        def remember(issuer, *args, **kwargs):
            token = original(issuer, *args, **kwargs); issued.append(token); return token
        with mock.patch.object(FixtureTokenIssuer, "issue", remember): result = self.run_fixture()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual({check["name"] for check in result["checks"]}, CLI.REQUIRED_CHECKS)
        self.assertTrue(all(check["passed"] for check in result["checks"]))
        self.assertEqual(result["summary"]["committed_requests"], 2)
        self.assertEqual(result["summary"]["receiver_effects"], 2)
        self.assertEqual(result["summary"]["engineering_charge_units"], 2)
        self.assertFalse(result["independent_witness"])
        self.assertFalse(result["cloud_failover_tested"])
        self.assertGreater(len(issued), 15)
        self.assertEqual(result, json.loads((self.root / ".local/run/result.json").read_bytes()))
        for path in (self.root / ".local/run").rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                self.assertNotIn(b"PRIVATE KEY", raw)
                for token in issued: self.assertNotIn(token.encode(), raw)

    def test_failed_workflow_retains_type_without_sensitive_exception_text(self):
        with mock.patch.object(CLI, "exercise", side_effect=ValueError("private-token")):
            result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"stage": "fixture_workflow", "type": "ValueError"}])
        self.assertNotIn("private-token", json.dumps(result))

    def test_incomplete_result_cannot_report_success(self):
        with mock.patch.object(CLI, "exercise", return_value={"status": "passed", "checks": []}):
            result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][-1]["type"], "IncompleteWorkflow")

    def test_existing_and_outside_output_never_overwrites(self):
        with mock.patch.object(CLI, "exercise", side_effect=ValueError): self.run_fixture()
        saved = (self.root / ".local/run/result.json").read_bytes()
        for output in (".local/run", ".local/../outside", "outside/run"):
            with self.subTest(output=output), self.assertRaises(CLI._BASELINE.BaselineError):
                CLI.run_rehearsal(root=self.root, output=output)
        self.assertEqual(saved, (self.root / ".local/run/result.json").read_bytes())

    def test_source_changes_block_result(self):
        other = {**self.snapshot, "sha256": "b"*64}
        with mock.patch.object(CLI, "source_snapshot", side_effect=[self.snapshot, other]), mock.patch.object(CLI, "exercise", return_value={"checks": []}):
            result = CLI.run_rehearsal(root=self.root, output=".local/run")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checks"][-1], {"name": "source_unchanged", "passed": False})

    def test_missing_required_source_is_rejected_before_workflow(self):
        with mock.patch.object(CLI, "exercise") as exercise:
            result = CLI.run_rehearsal(root=self.root, output=".local/run")
        self.assertEqual(result["status"], "failed")
        exercise.assert_not_called()

    def test_cli_refuses_arbitrary_private_data_and_preserves_exit_codes(self):
        with mock.patch.object(CLI, "ROOT", self.root), mock.patch.object(CLI, "source_snapshot", return_value=self.snapshot), mock.patch.object(CLI, "exercise", side_effect=RuntimeError), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(CLI.main(["--output", ".local/failure"]), 1)
            self.assertEqual(CLI.main(["--output", ".local/failure"]), 2)
        with mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
            CLI.main(["--output", ".local/data", "--data", "private.csv"])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / ".local/data").exists())

    def test_source_reader_refuses_overflow_and_growth_after_stat(self):
        path = self.root / "source.py"; path.write_bytes(b"abcd")
        with self.assertRaises(CLI.RehearsalError): CLI._read_source(self.root, "source.py", 3)
        original = CLI.os.fdopen
        def growing(fd, *args, **kwargs):
            with path.open("ab") as writer: writer.write(b"efgh")
            return original(fd, *args, **kwargs)
        with mock.patch.object(CLI.os, "fdopen", side_effect=growing):
            with self.assertRaises(CLI.RehearsalError): CLI._read_source(self.root, "source.py", 4)

    def test_source_reader_reads_at_most_limit_plus_one(self):
        path = self.root / "source.py"; path.write_bytes(b"abcd")
        real = CLI.os.fdopen
        counts = []
        class Stream:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(self, count): counts.append(count); return self.stream.read(count)
        with mock.patch.object(CLI.os, "fdopen", side_effect=lambda *a, **k: Stream(real(*a, **k))):
            self.assertEqual(CLI._read_source(self.root, "source.py", 4), b"abcd")
        self.assertEqual(counts, [5])

    def test_source_snapshot_includes_all_new_registry_modules(self):
        snapshot = CLI.source_snapshot(Path(__file__).resolve().parents[1])
        names = {row["path"] for row in snapshot["files"]}
        for name in ("contracts", "store", "service", "receiver", "rehearsal"):
            self.assertIn("src/model_release_assurance/production_registry/" + name + ".py", names)

if __name__ == "__main__": unittest.main()
