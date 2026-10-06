"""Fixed-roster CLI dispositions use explicitly mocked external execution."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("art_cli", Path(__file__).resolve().parents[1] / "scripts/rehearse_art_adapter.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
_MANIFEST = json.loads((CLI.ROOT / "deploy/art/windows-cp312.json").read_bytes())


class ArtCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="art-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / ".gitignore").write_text(".local/\n")
        self.python = self.root / ".local/env/Scripts/python.exe"
        self.change = None

    def fake(self, blobs, *, profile_id, **kwargs):
        kwargs["output"].mkdir()
        result = {"status": "completed", "error": None,
            "comparison": {"target": {"summary": {"fixture": True}},
                           "positive": {"controls_satisfied": True}, "null": {"controls_satisfied": True}}}
        if self.change:
            self.change(profile_id, result)
        return result

    def run_fixture(self, *, source=None, descriptor=None, manifest=None, replay=None, verified=None):
        with patch.object(CLI, "load_runtime_manifest", return_value=({}, "a" * 64)), \
             patch.object(CLI, "source_bindings", side_effect=source or [{}, {}]), \
             patch.object(CLI, "runtime_descriptor", side_effect=descriptor or [{}, {}]), \
             patch.object(CLI, "verified_input", side_effect=verified or (lambda *args, **kwargs: {})), \
             patch.object(CLI, "artifact_manifest", side_effect=manifest or (lambda blobs: {})), \
             patch.object(CLI, "snapshot_native_bundle", return_value={}), \
             patch.object(CLI, "run_comparison", side_effect=self.fake), \
             patch.object(CLI, "replay_comparison", side_effect=replay or (lambda *args, **kwargs: {"status": "bound_local_replay"})):
            return CLI.run_rehearsal(root=self.root, output=".local/run", python=self.python)

    def test_all_eight_profiles_including_regression_are_required(self):
        report = self.run_fixture()
        self.assertEqual(report["status"], "completed", report)
        self.assertEqual([item["profile_id"] for item in report["cases"]], list(CLI.PROFILE_IDS))
        self.assertEqual(sum(item["status"] == "completed" for item in report["cases"]), 8)
        self.assertTrue(report["original_artifacts_unchanged"])
        self.assertFalse(report["all_research_datasets_tested"])
        for flag in ("can_clear", "assessment_eligible", "authorization_eligible", "production_authorized",
                     "external_execution_attested", "model_delivery"):
            self.assertIs(report[flag], False)

    def test_failed_case_stays_in_roster(self):
        self.change = lambda name, result: result.update(status="failed", error={"type": "Example"}) if name == "acs" else None
        report = self.run_fixture()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(report["cases"]), 8)
        self.assertFalse(report["coverage_complete"])

    def test_missing_optional_dependency_is_never_a_batch_success(self):
        self.change = lambda name, result: result.update(status="unavailable", error={"type": "Dependency"}) if name == "acs" else None
        report = self.run_fixture()
        self.assertEqual(report["cases"][0]["status"], "unavailable")
        self.assertEqual(report["status"], "failed")

    def test_regression_cannot_be_relabelled_unsupported(self):
        self.change = lambda name, result: result.update(status="unsupported", error={"code": "regression_not_supported"}) if name == "sklearn-diabetes" else None
        report = self.run_fixture()
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["coverage_complete"])

    def test_false_control_prevents_success(self):
        self.change = lambda name, result: result["comparison"]["null"].update(controls_satisfied=False) if name == "acs" else None
        self.assertEqual(self.run_fixture()["status"], "failed")

    def test_independent_replay_failure_prevents_success(self):
        def replay(blobs, *, profile_id, **kwargs):
            if profile_id == "acs":
                raise ValueError("Changed comparison")
            return {"status": "bound_local_replay"}
        report = self.run_fixture(replay=replay)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["cases"][0]["error"]["stage"], "profile_comparison")

    def test_source_drift_prevents_success(self):
        report = self.run_fixture(source=[{}, {"change": True}])
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["source_unchanged"])

    def test_runtime_drift_prevents_success(self):
        report = self.run_fixture(descriptor=[{}, {"change": True}])
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["source_unchanged"])

    def test_original_bundle_drift_prevents_success(self):
        calls = 0
        def manifest(blobs):
            nonlocal calls
            calls += 1
            return {"change": True} if calls == 3 else {}
        report = self.run_fixture(manifest=manifest)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["original_artifacts_unchanged"])
        self.assertEqual(report["cases"][0]["error"]["stage"], "original_bundle_stability")

    def test_source_input_missing_cannot_be_excluded(self):
        report = self.run_fixture(verified=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
        self.assertEqual(len(report["cases"]), 8)
        self.assertEqual(report["status"], "failed")

    def test_inputs_and_runtime_must_be_government_local(self):
        for kwargs in ({"python": self.root / "outside/python.exe"},
                       {"python": self.python, "benchmark": self.root / "elsewhere"},
                       {"python": self.root / ".local/../elsewhere/python.exe"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CLI.run_rehearsal(root=self.root, output=".local/run", **kwargs)
        self.assertFalse((self.root / ".local/run").exists())

    def test_output_must_be_new_ignored_local(self):
        self.run_fixture()
        with self.assertRaises(CLI._BASELINE.BaselineError):
            self.run_fixture()
        with self.assertRaises(CLI._BASELINE.BaselineError):
            CLI.run_rehearsal(root=self.root, output="published-result", python=self.python)

    def test_no_model_threshold_or_custom_attack_options(self):
        for option in ("--model", "--pickle", "--threshold", "--attack-model", "--private-data"):
            with self.subTest(option=option), patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                CLI.main(["--output", ".local/run", "--python", str(self.python), option, "value"])

    def test_cli_exit_codes_reflect_success_failure_and_refusal(self):
        for status, expected in (("completed", 0), ("failed", 1), ("unavailable", 1)):
            with patch.object(CLI, "run_rehearsal", return_value={"status": status, "cases": [], "coverage_complete": status == "completed"}), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(CLI.main(["--output", ".local/run", "--python", str(self.python)]), expected)
        with patch.object(CLI, "run_rehearsal", side_effect=ValueError), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(CLI.main(["--output", ".local/run", "--python", str(self.python)]), 2)

    def manifest(self, change=None):
        value = copy.deepcopy(_MANIFEST)
        if change:
            change(value)
        directory = self.root / "deploy/art"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "windows-cp312.json").write_text(json.dumps(value), encoding="utf-8")
        return value

    def test_exact_runtime_manifest_is_accepted(self):
        self.manifest()
        versions, digest = CLI.load_runtime_manifest(self.root)
        self.assertEqual(versions, CLI.runtime.LOCKED_VERSIONS)
        self.assertEqual(len(digest), 64)

    def test_manifest_ambiguous_or_missing_artifact_refused(self):
        for change in (lambda value: value["artifacts"].append(copy.deepcopy(value["artifacts"][0])),
                       lambda value: value["artifacts"].pop(),
                       lambda value: value["artifacts"][0].update(name="adversarial_robustness_toolbox"),
                       lambda value: value["artifacts"][0].update(sha256=True),
                       lambda value: value["artifacts"][0].update(filename="../escape.whl"),
                       lambda value: value["artifacts"][0].update(size_bytes=True)):
            self.manifest(change)
            with self.assertRaises(ValueError):
                CLI.load_runtime_manifest(self.root)

    def test_manifest_wrong_target_or_authorizing_flags_refused(self):
        for key, value in (("schema", "other"), ("art_version", "9"), ("target", {}),
                           ("fixture_only", False), ("production_authorized", True), ("model_delivery", True)):
            self.manifest(lambda manifest: manifest.update({key: value}))
            with self.assertRaises(ValueError):
                CLI.load_runtime_manifest(self.root)


if __name__ == "__main__":
    unittest.main()
