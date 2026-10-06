"""Strict two-stage pyrit binding tests with explicit synthetic process fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_pyrit_adaptive import protocol, runtime, worker, workflow
from test_production_pyrit_adaptive_protocol import fixture_plan, fixture_campaign, fixture_output, fixture_response, fixture_attacker_failure


class PyritAdaptiveWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pyrit-adaptive-workflow-")
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
            result = {"schema": "mra-pyrit-adaptive-worker-output/v1", "mode": "prepare", "status": "prepared",
                "plan": plan, "runtime": runtime.expected_binding(), "versions": request["versions"],
                "source_sha256": request["source_sha256"], "lock_sha256": request["lock_sha256"],
                "model": request["model"], "target_calls": 0, "attacker_calls": 0,
                **protocol.ROLE_FLAGS, **protocol.FLAGS}
        else:
            self.assertTrue((input_path.parent.parent / "plan.json").exists())
            self.assertEqual(json.loads((input_path.parent.parent / "plan.json").read_bytes()), request["plan"])
            result = fixture_output(request["plan"])
        result["path_binding"] = {"schema": "mra-pyrit-cache-binding/v1", "root": str(output / "cache"),
            "db_data_path": str(output / "cache/pyrit/dbdata"), "cache_path": str(output / "cache/pyrit/.pyrit_cache"),
            "log_path": str(output / "cache/pyrit/dbdata/logs.txt"),
            "hook": "trusted_fixed_appdirs_pyrit/v1", "profile_discovery": False}
        if mode == "run":
            result["campaign"]["path_binding"] = copy.deepcopy(result["path_binding"])
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

    def test_adaptive_plan_is_frozen_before_the_only_run_phase(self):
        result = self.run_fixture()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.calls, ["prepare", "run"])
        self.assertEqual(result["replay"]["status"], "completed")
        self.assertEqual(json.loads((self.output / "plan.json").read_bytes())["bounds"], protocol.BOUNDS)
        self.assertEqual(self.replay()["status"], "bound_local_replay")
        intent = json.loads((self.output / "intent.json").read_bytes())
        self.assertTrue(intent["shared_model"])
        self.assertFalse(intent["independent_attacker_model"])
        self.assertEqual(intent["bounds"]["total_live_calls"], 12)
        for flag in ("can_clear", "assessment_eligible", "authorization_eligible", "authorized",
                     "production_authorized", "external_execution_attested", "tools_executed", "model_delivery"):
            self.assertIs(result[flag], False)




    def test_incomplete_marker_replies_retain_hits_without_completed_scores(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"],
                    response=fixture_response(protocol.MARKER, done=False), cache_root=path.parent / "worker/cache"))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertEqual(result["replay"]["unscoreable"], 6)
        self.assertEqual(result["replay"]["observed_literal_hits"], 6)
        self.assertEqual(result["replay"]["scored"], 0)
        self.assertFalse(result["can_clear"])
        self.assertEqual(self.replay()["campaign_status"], "incomplete")

    def test_real_target_hit_counts_exclude_scripted_positive_controls(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"],
                    response=fixture_response(protocol.MARKER), cache_root=path.parent / "worker/cache"))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["replay"]["target_turns"], 2)
        self.assertEqual(result["replay"]["observed_literal_hits"], 2)
        self.assertTrue(result["replay"]["positive_stop_at_2"])
        self.assertTrue(result["replay"]["null_exhaust_at_3"])
        self.assertFalse(result["production_authorized"])

    def test_case_sensitive_miss_is_retained_as_a_lexical_limitation(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"],
                    response=fixture_response(protocol.MARKER.lower()), cache_root=path.parent / "worker/cache"))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["replay"]["target_turns"], 6)
        self.assertEqual(result["replay"]["observed_literal_hits"], 0)
        self.assertEqual(result["replay"]["human_review"], "pending")
        self.assertFalse(result["can_clear"])

    def test_forged_retained_memory_hash_cannot_pass_the_workflow(self):
        self.change = lambda mode, request, result, process, path: result["campaign"]["runs"][2]["target_memory"][0].update(original_sha256="c" * 64) if mode == "run" else None
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["replay"])

    def test_score_reassigned_to_another_response_cannot_pass_the_workflow(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                row = result["campaign"]["runs"][2]
                row["scores"][0]["message_piece_id"] = row["target_calls"][1]["response_id"]
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["replay"])

    def test_terminal_attacker_failure_retains_zero_target_calls_and_raw_marker(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"],
                    attacker_response=fixture_attacker_failure(protocol.MARKER, done=False),
                    cache_root=path.parent / "worker/cache"))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertEqual(result["replay"]["attacker_failures"], 2)
        self.assertEqual(result["replay"]["attacker_calls"], 2)
        self.assertEqual(result["replay"]["target_turns"], 0)
        self.assertEqual(result["replay"]["attacker_literal_marker_observations"], 2)
        self.assertEqual(result["replay"]["observed_literal_hits"], 0)
        saved = json.loads((self.output / "run/worker/worker.json").read_bytes())
        for index in (2, 5):
            row = saved["campaign"]["runs"][index]
            self.assertEqual(row["target_calls"], [])
            self.assertEqual(row["result"]["outcome"], "error")
            self.assertEqual(row["attacker_calls"][0]["response"]["message"]["content"], protocol.MARKER)
            self.assertIsNotNone(row["terminal_error"])
        self.assertEqual(self.replay()["campaign_status"], "incomplete")
        self.assertFalse(result["can_clear"])

    def test_partial_attacker_failure_keeps_prior_target_turns_and_other_case(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"], attacker_response=fixture_attacker_failure(),
                    fail_turn=2, failure_cases=["direct_chat"], cache_root=path.parent / "worker/cache"))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertEqual(result["replay"]["attacker_failures"], 1)
        self.assertEqual(result["replay"]["attacker_calls"], 5)
        self.assertEqual(result["replay"]["target_turns"], 4)
        self.assertTrue(result["replay"]["positive_stop_at_2"])
        self.assertTrue(result["replay"]["null_exhaust_at_3"])
        self.assertEqual(self.replay()["campaign_status"], "incomplete")
        self.assertFalse(result["production_authorized"])

    def test_attacker_failure_cannot_be_restamped_as_completed(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                result.update(fixture_output(request["plan"], attacker_response=fixture_attacker_failure(),
                    cache_root=path.parent / "worker/cache"))
                result["campaign"]["runs"][2]["terminal_error"] = None
                result["status"] = "completed"
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["replay"])

    def test_role_option_or_schema_changes_stop_before_inference(self):
        for key, value in (("attacker_options", protocol.TARGET_OPTIONS), ("response_schema_sha256", "c" * 64),
                           ("attacker_system_template", "An unrelated attacker system")):
            self.output = self.root / key
            self.calls.clear()
            self.change = lambda mode, request, result, process, path: result["plan"].update({key: value}) if mode == "prepare" else None
            result = self.run_fixture()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(self.calls, ["prepare"])

    def test_swapped_attacker_and_target_identities_cannot_replay(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                identity = result["campaign"]["runs"][2]["identifiers"]
                identity["adversarial_chat"] = copy.deepcopy(identity["objective_target"])
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["replay"])

    def test_cached_other_role_history_cannot_replay(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                row = result["campaign"]["runs"][2]
                row["attacker_calls"][1]["history"][-1]["text"] = "TARGET_FEEDBACK: cached response from another case"
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["replay"])

    def test_attacker_provider_model_or_request_role_cannot_change(self):
        for field in ("model", "wire_role", "format_schema"):
            self.output = self.root / field
            def change(mode, request, result, process, path):
                if mode == "run":
                    row = result["campaign"]["runs"][2]
                    if field == "model": row["attacker_calls"][0]["response"]["model"] = "another-model"
                    elif field == "wire_role": result["campaign"]["client"]["requests"][0]["role"] = "target"
                    else: row["attacker_calls"][0]["format_schema"] = {"type": "string"}
            self.change = change
            result = self.run_fixture()
            self.assertEqual(result["status"], "failed", field)
            self.assertIsNone(result["replay"])

    def test_same_conversation_for_both_roles_cannot_replay(self):
        def change(mode, request, result, process, path):
            if mode == "run":
                row = result["campaign"]["runs"][2]
                row["attacker_calls"][0]["conversation_id"] = row["target_calls"][0]["conversation_id"]
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["replay"])

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

    def test_prepare_must_declare_zero_attacker_calls(self):
        self.change = lambda mode, request, result, process, path: result.update(attacker_calls=1) if mode == "prepare" else None
        self.assertEqual(self.run_fixture()["status"], "failed")
        self.assertEqual(self.calls, ["prepare"])

    def test_worker_envelopes_cannot_claim_independent_models(self):
        for mode in ("prepare", "run"):
            for key, value in (("shared_model", False), ("shared_model", 1), ("independent_models", True), ("independent_models", 0),
                               ("independent_attacker_model", True), ("independent_attacker_model", 0)):
                self.output = self.root / (mode + key + str(value))
                self.change = lambda current, request, result, process, path: result.update({key: value}) if current == mode else None
                result = self.run_fixture()
                self.assertEqual(result["status"], "failed")
                self.assertIsNone(result["replay"])

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
        for filename in ("plan.json", "intent.json", "run/input.json", "run/worker/process.json", "prepare/input.json", "prepare/worker/worker.json", "prepare/worker/process.json"):
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

    def test_cache_root_must_match_the_exact_owned_stage(self):
        def change(mode, request, result, process, path):
            root = path.parent / "worker/other-cache"
            result["path_binding"].update(root=str(root), db_data_path=str(root / "pyrit/dbdata"),
                cache_path=str(root / "pyrit/.pyrit_cache"), log_path=str(root / "pyrit/dbdata/logs.txt"))
        self.change = change
        result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.calls, ["prepare"])

    def test_cache_profile_discovery_and_other_log_paths_are_refused(self):
        for key, value in (("profile_discovery", True), ("profile_discovery", 0),
                           ("log_path", "C:/Users/fixture/OneDrive/logs.txt"),
                           ("hook", "unrestricted_appdirs"), ("unknown", True)):
            self.output = self.root / (key + str(value).replace("/", "-").replace(":", "-"))
            self.change = lambda mode, request, result, process, path: result["path_binding"].update({key: value})
            self.assertEqual(self.run_fixture()["status"], "failed", key)

    def test_retained_replay_rejects_cross_stage_cache_binding(self):
        self.assertEqual(self.run_fixture()["status"], "completed")
        prepare_path = self.output / "prepare/worker/worker.json"
        run_path = self.output / "run/worker/worker.json"
        prepared = json.loads(prepare_path.read_bytes())
        prepared["path_binding"] = json.loads(run_path.read_bytes())["path_binding"]
        prepare_path.write_bytes(canonical_bytes(prepared) + b"\n")
        with self.assertRaises(ValueError):
            self.replay()

    def test_timeout_is_bounded_before_output_creation(self):
        for timeout in (0, 601, True):
            with self.assertRaises(ValueError):
                workflow.run_campaign(output=self.output, python="unused", versions=runtime.LOCKED_VERSIONS,
                    lock_sha256="b" * 64, timeout_seconds=timeout)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
