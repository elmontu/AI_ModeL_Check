"""Fixed pyrit campaign CLI boundaries; process execution is mocked explicitly."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("pyrit_adaptive_cli", Path(__file__).resolve().parents[1] / "scripts/rehearse_pyrit_adaptive_adapter.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
_MANIFEST_BYTES = (CLI.ROOT / "deploy/pyrit/windows-cp312.json").read_bytes()
_MANIFEST = json.loads(_MANIFEST_BYTES)
_REQUIREMENTS_BYTES = (CLI.ROOT / "deploy/pyrit/windows-cp312.requirements.txt").read_bytes()


class PyritAdaptiveCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pyrit-adaptive-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / ".gitignore").write_text(".local/\n")
        self.python = self.root / ".local/env/Scripts/python.exe"
        self.change = None

    def fake(self, **kwargs):
        kwargs["output"].mkdir()
        self.assertEqual(kwargs["timeout_seconds"], 600)
        result = {"status": "completed", "error": None, "source_unchanged": True,
                  "replay": {"status": "completed"}}
        if self.change:
            self.change(result)
        return result

    def run_fixture(self, *, source=None, descriptor=None, replay=None, campaign=None):
        with patch.object(CLI, "load_runtime_manifest", return_value=({}, "a" * 64)), \
             patch.object(CLI, "source_bindings", side_effect=source or [{}, {}]), \
             patch.object(CLI, "runtime_descriptor", side_effect=descriptor or [{}, {}]), \
             patch.object(CLI, "run_campaign", side_effect=campaign or self.fake), \
             patch.object(CLI, "replay_campaign", side_effect=replay or (lambda **kwargs: {"status": "bound_local_replay", "campaign_status": "completed"})):
            return CLI.run_rehearsal(root=self.root, output=".local/run", python=self.python)

    def test_completed_adaptive_campaign_retains_non_authorizing_flags(self):
        report = self.run_fixture()
        self.assertEqual(report["status"], "completed", report)
        self.assertTrue(report["scope_complete"])
        self.assertEqual(report["replay_status"], "bound_local_replay")
        for flag in ("can_clear", "assessment_eligible", "authorization_eligible", "production_authorized",
                     "external_execution_attested", "model_delivery", "tools_executed", "authorized"):
            self.assertIs(report[flag], False)
        self.assertFalse(report["all_pyrit_attack_families_tested"])
        self.assertFalse(report["all_llm_interfaces_tested"])
        self.assertTrue(report["shared_model"])
        self.assertFalse(report["independent_attacker_model"])
        intent = json.loads((self.root / ".local/run/batch-intent.json").read_bytes())
        self.assertEqual(intent["attacker_options"]["num_predict"], 512)
        self.assertEqual(intent["target_options"]["num_predict"], 256)
        self.assertEqual(intent["modes"], ["positive", "null", "adaptive"])

    def test_incomplete_campaign_is_replayed_but_cannot_pass(self):
        self.change = lambda result: result.update(status="incomplete", replay={"status": "incomplete"})
        report = self.run_fixture(replay=lambda **kwargs: {"status": "bound_local_replay", "campaign_status": "incomplete"})
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["scope_complete"])
        self.assertEqual(report["replay_status"], "bound_local_replay")

    def test_missing_runtime_never_falls_back(self):
        self.change = lambda result: result.update(status="unavailable", error={"type": "Dependency"}, replay=None)
        with patch.object(CLI, "replay_campaign", side_effect=AssertionError):
            report = self.run_fixture()
        self.assertEqual(report["status"], "unavailable")
        self.assertIsNone(report["replay_status"])
        self.assertFalse(report["scope_complete"])

    def test_timeout_and_failed_campaigns_remain_incomplete(self):
        for status in ("timed_out", "failed", "unsupported"):
            with self.subTest(status=status):
                self.root = self.root / status
                self.root.mkdir()
                subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
                (self.root / ".gitignore").write_text(".local/\n")
                self.python = self.root / ".local/env/Scripts/python.exe"
                self.change = lambda result: result.update(status=status, error={"type": "Failure"})
                report = self.run_fixture()
                self.assertEqual(report["status"], status)
                self.assertFalse(report["scope_complete"])

    def test_replay_failure_or_changed_completion_cannot_pass(self):
        def replay(**kwargs):
            raise ValueError("Changed attempt")
        report = self.run_fixture(replay=replay)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error"]["stage"], "rehearsal")

    def test_worker_source_drift_prevents_success(self):
        self.change = lambda result: result.update(source_unchanged=False)
        self.assertEqual(self.run_fixture()["status"], "failed")

    def test_driver_source_drift_prevents_success(self):
        report = self.run_fixture(source=[{}, {"change": True}])
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["source_unchanged"])
        self.assertFalse(report["scope_complete"])

    def test_runtime_drift_prevents_success(self):
        report = self.run_fixture(descriptor=[{}, {"change": True}])
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["source_unchanged"])
        self.assertFalse(report["scope_complete"])

    def test_python_must_remain_under_government_local(self):
        for path in (self.root / "elsewhere/python.exe", self.root / ".local/../elsewhere/python.exe"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                CLI.run_rehearsal(root=self.root, output=".local/run", python=path)
        self.assertFalse((self.root / ".local/run").exists())

    def test_timeout_must_be_bounded_integer_before_output_creation(self):
        for timeout in (0, -1, 601, True, 1.5):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                CLI.run_rehearsal(root=self.root, output=".local/run", python=self.python, timeout_seconds=timeout)
        self.assertFalse((self.root / ".local/run").exists())

    def test_new_ignored_output_is_required(self):
        self.run_fixture()
        with self.assertRaises(CLI._BASELINE.BaselineError):
            self.run_fixture()
        with self.assertRaises(CLI._BASELINE.BaselineError):
            CLI.run_rehearsal(root=self.root, output="published-result", python=self.python)

    def test_no_custom_endpoint_model_probe_or_tool_options(self):
        for option in ("--model", "--attacker-model", "--target-model", "--url", "--host", "--seed", "--probe", "--private-data", "--tools"):
            with self.subTest(option=option), patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                CLI.main(["--output", ".local/run", "--python", str(self.python), option, "value"])

    def test_main_success_incomplete_failure_and_refusal_exit_codes(self):
        for status, expected in (("completed", 0), ("incomplete", 1), ("failed", 1), ("unavailable", 1)):
            with patch.object(CLI, "run_rehearsal", return_value={"status": status,
                "scope_complete": status == "completed", "replay_status": None}), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(CLI.main(["--output", ".local/run", "--python", str(self.python)]), expected)
        with patch.object(CLI, "run_rehearsal", side_effect=ValueError), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(CLI.main(["--output", ".local/run", "--python", str(self.python)]), 2)

    def manifest(self, change=None):
        value = copy.deepcopy(_MANIFEST)
        if change:
            change(value)
        directory = self.root / "deploy/pyrit"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "windows-cp312.json").write_bytes(json.dumps(value).encode("utf-8") if change else _MANIFEST_BYTES)
        (directory / "windows-cp312.requirements.txt").write_bytes(_REQUIREMENTS_BYTES)
        return value

    def test_exact_component_manifest_accepted(self):
        self.manifest()
        versions, digest = CLI.load_runtime_manifest(self.root)
        self.assertEqual(versions, CLI.runtime.LOCKED_VERSIONS)
        self.assertEqual(len(digest), 64)

    def test_manifest_artifact_ambiguity_or_bad_bounds_refused(self):
        for change in (lambda value: value["artifacts"].append(copy.deepcopy(value["artifacts"][0])),
                       lambda value: value["artifacts"].pop(),
                       lambda value: value["artifacts"][0].update(sha256=True),
                       lambda value: value["artifacts"][0].update(filename="../escape.whl"),
                       lambda value: value["artifacts"][0].update(size_bytes=True)):
            self.manifest(change)
            with self.assertRaises(ValueError):
                CLI.load_runtime_manifest(self.root)

    def test_dependency_lock_bytes_and_requirements_cannot_be_restamped(self):
        self.manifest()
        manifest = self.root / "deploy/pyrit/windows-cp312.json"
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            CLI.load_runtime_manifest(self.root)
        self.manifest()
        requirements = self.root / "deploy/pyrit/windows-cp312.requirements.txt"
        requirements.write_bytes(requirements.read_bytes() + b"# changed\n")
        with self.assertRaises(ValueError):
            CLI.load_runtime_manifest(self.root)

    def test_version_only_manifest_cannot_change_an_official_wheel_digest(self):
        self.manifest(lambda value: value["artifacts"][0].update(sha256="c" * 64))
        with self.assertRaises(ValueError):
            CLI.load_runtime_manifest(self.root)

    def test_changed_frozen_batch_intent_prevents_acceptance(self):
        def campaign(**kwargs):
            result = self.fake(**kwargs)
            (kwargs["output"].parent / "batch-intent.json").write_bytes(b"{}")
            return result
        report = self.run_fixture(campaign=campaign)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error"]["stage"], "rehearsal")

    def test_manifest_cannot_claim_full_dependencies_or_change_scope(self):
        for key, value in (("schema", "other"), ("pyrit_version", "9"), ("target", {}),
                           ("fixture_only", False), ("production_authorized", True), ("model_delivery", True),
                           ("full_upstream_dependency_set", True), ("component_scope", "all_plugins"),
                           ("unsupported_dependencies", []), ("upstream_requires_dist", [])):
            self.manifest(lambda manifest: manifest.update({key: value}))
            with self.assertRaises(ValueError):
                CLI.load_runtime_manifest(self.root)


if __name__ == "__main__":
    unittest.main()
