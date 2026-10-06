"""Strict two-stage garak binding tests with explicit synthetic process fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_garak import protocol, runtime, worker, workflow
from test_production_garak_protocol import fixture_plan, fixture_campaign, fixture_output


class GarakWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="garak-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "campaign"
        self.source = {"fixture.py": "0" * 64}
        self.descriptor = {"python": str(self.root / "env/Scripts/python.exe"),
            "launcher_sha256": "d" * 64, "base_python": str(self.root / "base/python.exe"),
            "base_sha256": "e" * 64, "site_packages": str(self.root / "env/Lib/site-packages"),
            "configuration_sha256": "f" * 64}
        self.change = self.after_change = None
        self.calls = []
        source_mock = patch.object(workflow, "source_snapshot", side_effect=lambda: dict(self.source))
        descriptor_mock = patch.object(workflow, "runtime_descriptor", side_effect=lambda python: dict(self.descriptor))
        source_mock.start(); descriptor_mock.start()
        self.addCleanup(source_mock.stop); self.addCleanup(descriptor_mock.stop)

    def external(self, python, input_path, output, *, timeout_seconds):
        request = json.loads(input_path.read_bytes())
        worker.validate_request(request)
        mode = request["mode"]
        self.calls.append(mode)
        self.assertEqual(timeout_seconds, 600)
        self.assertTrue((input_path.parent.parent / "intent.json").exists())
        if mode == "prepare":
            self.assertIsNone(request["plan"])
            self.assertFalse((input_path.parent.parent / "plan.json").exists())
            plan = fixture_plan(source_sha256=request["source_sha256"], lock_sha256=request["lock_sha256"])
            result = {"schema": "mra-garak-worker-output/v1", "mode": "prepare", "status": "prepared",
                "plan": plan, "runtime": runtime.expected_binding(), "versions": request["versions"],
                "source_sha256": request["source_sha256"], "lock_sha256": request["lock_sha256"],
                "model": request["model"], "target_calls": 0, **protocol.FLAGS}
        else:
            self.assertTrue((input_path.parent.parent / "plan.json").exists())
            self.assertEqual(json.loads((input_path.parent.parent / "plan.json").read_bytes()), request["plan"])
            result = fixture_output(request["plan"])
        process = {"status": "completed", "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "source_sha256": request["source_sha256"], "runtime_descriptor": dict(self.descriptor),
            "exit_code": 0, "cleanup_confirmed": True, "stdout_bytes": 0, "stderr_bytes": 0,
            "elapsed_seconds": .25, "hostile_code_isolated": False, "network_isolated": False,
            "filesystem_isolated": False, "resource_limits_verified": False}
        if self.change:
            self.change(mode, request, result, process, input_path)
        output.mkdir()
        # Nonfinite process tests deliberately return an inadmissible in-memory diagnostic.
        if all(not isinstance(value, float) or value != float("inf") for value in process.values()):
            workflow.write(output / "process.json", process)
        workflow.write(output / "worker.json", result)
        if self.after_change:
            self.after_change(mode, request, result, process, input_path)
        return {**process, "result": result}

    def run_fixture(self):
        with patch.object(workflow, "run_worker", side_effect=self.external):
            return workflow.run_campaign(output=self.output, python=self.descriptor["python"],
                versions=dict(runtime.LOCKED_VERSIONS), lock_sha256="b" * 64)

    def replay(self):
        return workflow.replay_campaign(output=self.output, versions=dict(runtime.LOCKED_VERSIONS), lock_sha256="b" * 64)

    def test_fixed_plan_is_frozen_before_the_only_run_phase(self):
        result = self.run_fixture()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.calls, ["prepare", "run"])
        self.assertEqual(result["replay"]["attempts"], 12)
        self.assertEqual(result["replay"]["scored"], 12)
        self.assertTrue(result["replay"]["target_controls_valid"])
        self.assertEqual(self.replay()["status"], "bound_local_replay")
        for flag in ("can_clear", "assessment_eligible", "authorization_eligible", "authorized",
                     "production_authorized", "external_execution_attested", "tools_executed", "model_delivery"):
            self.assertIs(result[flag], False)

    def test_literal_hits_are_retained_without_claiming_model_safety(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"], fixture_campaign(request["plan"], target_text=protocol.TRIGGER)))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["replay"]["observed_literal_hits"], 12)
        self.assertFalse(result["can_clear"])

    def test_valid_incomplete_target_controls_are_retained_and_replayed(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                campaign = fixture_campaign(request["plan"])
                row = campaign["target_controls"][0]
                row["response"]["message"]["content"] = "Unexpected reply"
                row["observation"] = protocol.observe_response(row["response"])
                row["valid"] = False
                result.update(fixture_output(request["plan"], campaign))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertFalse(result["replay"]["target_controls_valid"])
        self.assertEqual(self.replay()["campaign_status"], "incomplete")

    def test_empty_target_outputs_are_not_a_success(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"], fixture_campaign(request["plan"], target_text="")))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertEqual(result["replay"]["unscoreable"], 12)

    def test_prepare_failure_never_starts_the_target_phase(self):
        self.change = lambda mode, request, result, process, path: process.update(status="failed", exit_code=2)
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.calls, ["prepare"])
        self.assertIsNone(result["processes"]["run"])

    def test_prepare_must_declare_zero_target_calls(self):
        self.change = lambda mode, request, result, process, path: result.update(target_calls=1) if mode == "prepare" else None
        self.assertEqual(self.run_fixture()["status"], "failed")
        self.assertEqual(self.calls, ["prepare"])

    def test_prepare_binding_change_or_unknown_fields_refused(self):
        for key, value in (("runtime", {}), ("model", {}), ("versions", {}),
                           ("source_sha256", "c" * 64), ("lock_sha256", "c" * 64), ("unknown", True)):
            self.output = self.root / key
            self.calls.clear()
            self.change = lambda mode, request, result, process, path: result.update({key: value}) if mode == "prepare" else None
            self.assertEqual(self.run_fixture()["status"], "failed", key)
            self.assertEqual(self.calls, ["prepare"])

    def test_run_bindings_or_authorizing_flags_refused(self):
        for key, value in (("plan_sha256", "c" * 64), ("versions", {}), ("can_clear", True),
                           ("tools_executed", True), ("production_authorized", True), ("unknown", True)):
            self.output = self.root / key
            self.change = lambda mode, request, result, process, path: result.update({key: value}) if mode == "run" else None
            self.assertEqual(self.run_fixture()["status"], "failed", key)

    def test_attempt_transcript_and_false_score_cannot_disagree(self):
        self.change = lambda mode, request, result, process, path: result["campaign"]["attacks"][0].update(upstream_score=1.) if mode == "run" else None
        self.assertEqual(self.run_fixture()["status"], "failed")

    def test_required_attempt_cannot_be_omitted(self):
        self.change = lambda mode, request, result, process, path: result["campaign"]["attacks"].pop() if mode == "run" else None
        self.assertEqual(self.run_fixture()["status"], "failed")

    def test_raw_upstream_report_cannot_be_relabelled(self):
        self.change = lambda mode, request, result, process, path: result["campaign"]["upstream_reports"][0].update(report_sha256="c" * 64) if mode == "run" else None
        self.assertEqual(self.run_fixture()["status"], "failed")

    def test_source_change_between_prepare_and_run_stops_target_phase(self):
        self.after_change = lambda mode, request, result, process, path: self.source.update({"fixture.py": "c" * 64}) if mode == "prepare" else None
        self.assertEqual(self.run_fixture()["status"], "failed")
        self.assertEqual(self.calls, ["prepare"])

    def test_runtime_change_during_run_stops_completion(self):
        self.after_change = lambda mode, request, result, process, path: self.descriptor.update(base_sha256="c" * 64) if mode == "run" else None
        self.assertEqual(self.run_fixture()["status"], "failed")

    def test_timeout_unavailable_and_cleanup_failures_never_fall_back(self):
        for status in ("timed_out", "unavailable", "cleanup_unconfirmed", "output_limit"):
            self.output = self.root / status
            self.change = lambda mode, request, result, process, path: process.update(status=status) if mode == "run" else None
            result = self.run_fixture()
            self.assertEqual(result["status"], status if status in ("timed_out", "unavailable") else "failed")
            self.assertIsNone(result["replay"])

    def test_unconfirmed_prepare_cleanup_stops_target_phase(self):
        self.change = lambda mode, request, result, process, path: process.update(cleanup_confirmed=False)
        self.assertEqual(self.run_fixture()["status"], "failed")
        self.assertEqual(self.calls, ["prepare"])

    def test_process_claims_are_exact_and_bounded(self):
        for key, value in (("input_sha256", "c" * 64), ("source_sha256", "c" * 64),
                           ("exit_code", True), ("stdout_bytes", True), ("stderr_bytes", 65537),
                           ("elapsed_seconds", float("inf")), ("network_isolated", True),
                           ("resource_limits_verified", True), ("unknown", 0)):
            self.output = self.root / key
            self.change = lambda mode, request, result, process, path: process.update({key: value})
            self.assertEqual(self.run_fixture()["status"], "failed", key)

    def test_frozen_plan_input_or_process_bytes_cannot_change(self):
        for filename in ("plan.json", "intent.json", "run/input.json", "run/worker/process.json"):
            self.output = self.root / filename.replace("/", "-")
            self.after_change = lambda mode, request, result, process, path: (self.output / filename).write_bytes(b"{}") if mode == "run" else None
            self.assertEqual(self.run_fixture()["status"], "failed", filename)

    def test_saved_replay_rejects_changed_process(self):
        self.assertEqual(self.run_fixture()["status"], "completed")
        path = self.output / "run/worker/process.json"
        value = json.loads(path.read_bytes()); value["elapsed_seconds"] = .5
        path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ValueError):
            self.replay()

    def test_saved_replay_rejects_changed_summary_or_receipt(self):
        self.assertEqual(self.run_fixture()["status"], "completed")
        path = self.output / "replay.json"
        value = json.loads(path.read_bytes()); value["observed_literal_hits"] = 12
        path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ValueError):
            self.replay()

    def test_saved_replay_rejects_noncanonical_bytes(self):
        self.assertEqual(self.run_fixture()["status"], "completed")
        path = self.output / "intent.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.replay()

    def test_missing_dependency_exception_is_explicit_unavailable(self):
        with patch.object(workflow, "run_worker", side_effect=ModuleNotFoundError):
            result = workflow.run_campaign(output=self.output, python=self.descriptor["python"],
                versions=dict(runtime.LOCKED_VERSIONS), lock_sha256="b" * 64)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["replay"])

    def test_output_overwrite_refused(self):
        self.run_fixture(); before = (self.output / "result.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_fixture()
        self.assertEqual((self.output / "result.json").read_bytes(), before)

    def test_timeout_is_bounded_before_output_creation(self):
        for timeout in (0, 601, True):
            with self.assertRaises(ValueError):
                workflow.run_campaign(output=self.output, python="unused", versions=runtime.LOCKED_VERSIONS,
                    lock_sha256="b" * 64, timeout_seconds=timeout)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
