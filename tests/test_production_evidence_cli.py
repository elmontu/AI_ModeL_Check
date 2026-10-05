"""The evidence rehearsal retains a complete, non-authorizing result."""
from __future__ import annotations
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("evidence_rehearsal", Path(__file__).resolve().parents[1] / "scripts/rehearse_execution_evidence.py")
CLI = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(CLI)


class EvidenceRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="evidence-cli-"); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True, check=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.snapshot = {"unit-public-source": "a" * 64}

    def run_fixture(self, **kwargs):
        with patch.object(CLI, "source_snapshot", return_value=self.snapshot):
            return CLI.run_rehearsal(root=self.root, output=".local/run", **kwargs)

    def test_real_public_fixture_replay_and_adversarial_checks_are_retained(self):
        report = self.run_fixture()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(len(report["cases"]), 1)
        item = report["cases"][0]
        self.assertEqual(set(item["checks"]), CLI.REQUIRED_CHECKS)
        self.assertTrue(all(item["checks"].values()))
        self.assertTrue(report["source_unchanged"])
        for key, value in CLI.FLAGS.items(): self.assertIs(report[key], value)
        self.assertEqual(report, json.loads((self.root / ".local/run/result.json").read_bytes()))
        for path in (self.root / ".local/run").rglob("*"):
            if path.is_file(): self.assertNotIn(b"PRIVATE KEY", path.read_bytes())

    def test_failure_retains_safe_error_and_never_passes(self):
        with patch.object(CLI, "_fixture", side_effect=RuntimeError("secret-must-not-appear")):
            report = self.run_fixture()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["errors"], [{"type": "RuntimeError", "stage": "local_replay_evidence"}])
        self.assertNotIn("secret-must", json.dumps(report))

    def test_output_is_new_and_cannot_escape_local(self):
        self.run_fixture()
        before = (self.root / ".local/run/result.json").read_bytes()
        with self.assertRaises(CLI._BASELINE.BaselineError): self.run_fixture()
        self.assertEqual(before, (self.root / ".local/run/result.json").read_bytes())
        for target in ("outside", ".local/../outside"):
            with self.subTest(target=target), self.assertRaises(CLI._BASELINE.BaselineError):
                CLI.run_rehearsal(root=self.root, output=target)

    def test_existing_benchmark_outside_government_local_is_refused(self):
        report = self.run_fixture(benchmark=self.root / "unapproved")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["cases"], [])

    def test_source_drift_never_reports_passed(self):
        actual = CLI.source_snapshot
        calls = [0]
        def observe(root):
            calls[0] += 1
            return self.snapshot if calls[0] == 1 else {"unit-public-source": "b" * 64}
        with patch.object(CLI, "source_snapshot", observe):
            result = CLI.run_rehearsal(root=self.root, output=".local/run")
        self.assertEqual(result["status"], "failed")

    def test_revocation_check_does_not_depend_on_spent_nonce_rejection(self):
        original = CLI.verify_envelope
        calls = []
        def verify(raw, registry, profile, owner):
            calls.append(registry.revision)
            return original(raw, registry, profile, owner)
        with patch.object(CLI, "verify_envelope", verify):
            report = self.run_fixture()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(calls, [2, 3])
        public = json.loads((self.root / ".local/run/public-registration.json").read_bytes())
        self.assertIn("BEGIN PUBLIC KEY", public["public_key_pem"])
        self.assertNotIn("PRIVATE KEY", public["public_key_pem"])

    def test_cli_exit_codes_preserve_failures(self):
        with patch.object(CLI, "ROOT", self.root), patch.object(CLI, "source_snapshot", return_value=self.snapshot), patch.object(CLI, "_fixture", side_effect=RuntimeError), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(CLI.main(["--output", ".local/failure"]), 1)
            self.assertEqual(CLI.main(["--output", ".local/failure"]), 2)


if __name__ == "__main__": unittest.main()
