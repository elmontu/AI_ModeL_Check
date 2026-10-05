"""Safety and lifecycle checks for the strictly local public-fixture rehearsal."""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import importlib.util
import io
import json
from pathlib import Path
import socket
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_deployment_rehearsal", ROOT / "scripts/rehearse_local_deployment.py")
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class FakeProcess:
    def __init__(self, pid=12345, *, ignores_terminate=False, terminate_error=False, kill_error=False):
        self.pid = pid
        self.running = True
        self.returncode = None
        self.ignores_terminate = ignores_terminate
        self.terminate_error = terminate_error
        self.kill_error = kill_error
        self.terminated = self.killed = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1
        if self.terminate_error:
            raise OSError("controlled terminate failure")
        if not self.ignores_terminate:
            self.running, self.returncode = False, -15

    def kill(self):
        self.killed += 1
        if self.kill_error:
            raise OSError("controlled kill failure")
        self.running, self.returncode = False, -9

    def wait(self, timeout):
        if self.running:
            raise subprocess.TimeoutExpired("owned fixture", timeout)
        return self.returncode


class LocalDeploymentRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-local-rehearsal-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.plan = json.loads(HARNESS.DEFAULT_PLAN.read_bytes())
        self.plan_path = self.root / "blueprint.json"
        self.write_plan(self.plan)

    def write_plan(self, plan):
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")

    def make_owned(self, role="api", process=None):
        data = self.root / "dev"
        data.mkdir(exist_ok=True)
        return HARNESS.OwnedProcess(process or FakeProcess(), io.StringIO(), role, "dev", data,
                                    self.root / (role + "-ready.json"), "owned-nonce")

    def ready_payload(self, owned, **updates):
        value = {"nonce": owned.nonce, "pid": owned.process.pid, "data": str(owned.data), "role": owned.role}
        value.update({"port": 12345} if owned.role == "api" else {"worker_id": "a" * 32})
        value.update(updates)
        owned.ready.write_text(json.dumps(value), encoding="utf-8")
        return value

    def run_mock_lifecycle(self, action, source=None):
        with mock.patch.object(HARNESS, "source_snapshot", side_effect=source or [{"sha256": "a"}, {"sha256": "a"}]), \
                mock.patch.object(HARNESS, "exercise_lifecycle", side_effect=action):
            return HARNESS.run_rehearsal(self.plan_path, ".local/run", root=self.root)

    def test_shared_validator_accepts_only_fixed_local_contract(self):
        plan, content = HARNESS.load_rehearsal_plan(self.plan_path)
        self.assertEqual(plan["local_rehearsal"]["allowed_environments"], ["dev", "staging"])
        self.assertEqual(content, self.plan_path.read_bytes())
        self.assertFalse(plan["deployment"]["cloud_deployable"])
        for mutation in (lambda p: p["local_rehearsal"].update(allowed_environments=["dev", "prod"]),
                         lambda p: p["local_rehearsal"].update(bind_address="0.0.0.0"),
                         lambda p: p["scope"].update(private_data_admission=True),
                         lambda p: p["environments"]["prod"].update(cloud_enabled=True)):
            changed = deepcopy(self.plan)
            mutation(changed)
            self.write_plan(changed)
            with self.assertRaises(ValueError):
                HARNESS.load_rehearsal_plan(self.plan_path)

    def test_production_or_malformed_plan_refused_before_any_service_spawn_with_receipt(self):
        for index, content in enumerate(("{}", '{"schema":1,"schema":2}', "not JSON")):
            self.plan_path.write_text(content, encoding="utf-8")
            with mock.patch.object(HARNESS, "spawn_owned") as spawn:
                result = HARNESS.run_rehearsal(self.plan_path, f".local/bad-{index}", root=self.root)
            spawn.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["cloud_deployable"])
            self.assertEqual(json.loads((self.root / f".local/bad-{index}/result.json").read_bytes()), result)
        changed = deepcopy(self.plan)
        changed["deployment"]["cloud_deployable"] = True
        self.write_plan(changed)
        with mock.patch.object(HARNESS, "spawn_owned") as spawn:
            result = HARNESS.run_rehearsal(self.plan_path, ".local/production-refused", root=self.root)
        spawn.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["authorization_eligible"])

    def test_output_must_be_new_ignored_child_and_preserves_existing_files(self):
        for output in (".local", "source-output", ".local/../escape", self.root.parent / "escape"):
            with self.assertRaises(HARNESS.RehearsalError):
                HARNESS.prepare_output(self.root, output)
        created = HARNESS.prepare_output(self.root, ".local/run")
        sentinel = created / "existing.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with self.assertRaises(HARNESS.RehearsalError):
            HARNESS.prepare_output(self.root, created)
        self.assertEqual(sentinel.read_text(), "preserve")
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(HARNESS.RehearsalError, "ignored"):
            HARNESS.prepare_output(self.root, ".local/not-ignored")

    def test_symlink_or_windows_reparse_ancestor_refused_before_creation(self):
        original = Path.lstat
        ancestor = self.root / ".local"
        ancestor.mkdir()
        for mode, attributes in ((stat.S_IFLNK, 0), (stat.S_IFDIR, 0x400)):
            def injected(path, *args, **kwargs):
                if path == ancestor:
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, "lstat", injected):
                with self.assertRaisesRegex(HARNESS.RehearsalError, "Symlink or reparse"):
                    HARNESS.prepare_output(self.root, ".local/refused")
            self.assertFalse((ancestor / "refused").exists())

    def test_fixed_process_allowlist_rejects_prod_and_arbitrary_execution(self):
        with mock.patch.object(HARNESS.subprocess, "Popen") as popen:
            for environment, role in (("prod", "api"), ("dev", "training"), ("other", "worker")):
                with self.assertRaises(HARNESS.RehearsalError):
                    HARNESS.spawn_owned([], self.root, self.root, environment, role, "initial")
        popen.assert_not_called()

    def test_child_environment_does_not_forward_credentials_or_proxy_and_uses_local_temp(self):
        with mock.patch.dict(HARNESS.os.environ, {"SECRET_KEY": "private", "HTTP_PROXY": "http://example.invalid",
                                               "PYTHONPATH": "elsewhere", "TEMP": "C:/not-approved"}):
            environment = HARNESS.child_environment(self.root, self.root)
        self.assertNotIn("SECRET_KEY", environment)
        self.assertNotIn("HTTP_PROXY", environment)
        self.assertEqual(environment["PYTHONPATH"], str(self.root / "src"))
        for name in ("TEMP", "TMP", "TMPDIR"):
            self.assertEqual(environment[name], str(self.root / "temp"))

    def test_successful_launch_registers_handle_and_no_shell_or_configurable_host(self):
        owned = []
        process = FakeProcess()
        with mock.patch.object(HARNESS.subprocess, "Popen", return_value=process) as popen:
            api = HARNESS.spawn_owned(owned, self.root, self.root, "dev", "api", "initial")
        self.addCleanup(api.log.close)
        self.assertEqual(owned, [api])
        args, kwargs = popen.call_args
        executable, _ = HARNESS.child_python({})
        self.assertEqual(args[0][:3], [executable, "-B", "-c"])
        self.assertIn('host="127.0.0.1", port=0', args[0][3])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["cwd"], self.root)

    def test_readiness_requires_matching_owned_pid_nonce_data_and_valid_port(self):
        owned = self.make_owned()
        self.addCleanup(owned.log.close)
        for mutation in ({"nonce": "wrong"}, {"pid": 999}, {"data": "other"}, {"port": True}, {"port": 0}):
            self.ready_payload(owned, **mutation)
            with self.assertRaises(HARNESS.RehearsalError):
                HARNESS.read_ready(owned)
        expected = self.ready_payload(owned)
        self.assertEqual(HARNESS.read_ready(owned), expected)
        self.assertEqual(owned.port, 12345)
        owned.ready.write_text("{", encoding="utf-8")
        self.assertIsNone(HARNESS.read_ready(owned))

    def test_readiness_and_worker_child_code_compile_without_optional_dependency_skips(self):
        compile(HARNESS.API_CHILD, "api-child", "exec")
        compile(HARNESS.WORKER_CHILD, "worker-child", "exec")

    def test_wait_detects_exit_and_honors_deadline(self):
        owned = self.make_owned()
        self.addCleanup(owned.log.close)
        owned.process.terminate()
        with self.assertRaisesRegex(HARNESS.RehearsalError, "exited"):
            HARNESS.wait_until(lambda: True, [owned], time.monotonic() + 1, "startup")
        with self.assertRaisesRegex(HARNESS.RehearsalError, "Timed out"):
            HARNESS.wait_until(lambda: True, [], time.monotonic() - 1, "startup")

    def test_cleanup_escalates_only_owned_handle_and_is_idempotent(self):
        process = FakeProcess(ignores_terminate=True)
        owned = self.make_owned(process=process)
        records = HARNESS.stop_owned([owned])
        self.assertTrue(records[0]["stopped"])
        self.assertEqual((process.terminated, process.killed), (1, 1))
        self.assertTrue(owned.log.closed)
        self.assertEqual(HARNESS.stop_owned([owned]), [])
        self.assertEqual((process.terminated, process.killed), (1, 1))

    def test_cleanup_continues_after_a_handle_cannot_be_stopped(self):
        good = self.make_owned(process=FakeProcess(pid=1))
        bad = self.make_owned("worker", FakeProcess(pid=2, terminate_error=True, kill_error=True))
        records = HARNESS.stop_owned([good, bad])
        self.assertFalse(records[0]["stopped"])
        self.assertTrue(records[1]["stopped"])
        self.assertTrue(good.log.closed and bad.log.closed)

    def test_cleanup_observes_reused_listener_without_killing_its_owner(self):
        with socket.socket() as unrelated:
            unrelated.bind(("127.0.0.1", 0))
            unrelated.listen()
            owned = self.make_owned()
            owned.port = unrelated.getsockname()[1]
            records = HARNESS.stop_owned([owned])
            self.assertFalse(records[0]["listener_closed"])
            self.assertNotEqual(unrelated.fileno(), -1)
            self.assertEqual(owned.process.terminated, 1)

    def test_partial_launch_failure_cleans_existing_process_and_retains_logs_and_result(self):
        processes = []
        def fail_after_launch(root, output, report, owners):
            process = FakeProcess()
            processes.append(process)
            with mock.patch.object(HARNESS.subprocess, "Popen", return_value=process):
                HARNESS.spawn_owned(owners, root, output, "dev", "api", "initial")
            with mock.patch.object(HARNESS.subprocess, "Popen", side_effect=OSError("controlled second launch failure")):
                HARNESS.spawn_owned(owners, root, output, "dev", "worker", "initial")
        result = self.run_mock_lifecycle(fail_after_launch)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(processes[0].terminated, 1)
        self.assertTrue(result["cleanup"][0]["stopped"])
        destination = self.root / ".local/run"
        self.assertTrue((destination / "dev-api-initial.log").is_file())
        self.assertTrue((destination / "dev-worker-initial.log").is_file())
        self.assertEqual(json.loads((destination / "result.json").read_bytes()), result)
        self.assertEqual((destination / "plan.json").read_bytes(), self.plan_path.read_bytes())

    def test_source_drift_cannot_receive_successful_receipt(self):
        def completed(root, output, report, owners):
            report["checks"].append({"name": "controlled fixture", "passed": True})
        result = self.run_mock_lifecycle(completed, source=[{"sha256": "before"}, {"sha256": "after"}])
        self.assertEqual(result["status"], "failed")
        self.assertIn("Rehearsal source changed during execution", result["errors"])

    def test_plan_drift_and_keyboard_interrupt_preserve_failed_receipt(self):
        def interrupted(root, output, report, owners):
            self.plan_path.write_text("{}", encoding="utf-8")
            raise KeyboardInterrupt()
        result = self.run_mock_lifecycle(interrupted)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("KeyboardInterrupt" in item for item in result["errors"]))
        self.assertIn("Infrastructure plan changed during execution", result["errors"])
        self.assertFalse(result["authorization_eligible"])

    def test_empty_lifecycle_cannot_claim_pass(self):
        result = self.run_mock_lifecycle(lambda *args: None)
        self.assertEqual(result["status"], "failed")

    def test_http_never_targets_unowned_or_dead_api(self):
        owned = self.make_owned()
        self.addCleanup(owned.log.close)
        with mock.patch.object(HARNESS.urllib.request, "build_opener") as opener:
            with self.assertRaises(HARNESS.RehearsalError):
                HARNESS.request_json(owned, "/healthz")
            owned.port = 12345
            owned.process.terminate()
            with self.assertRaises(HARNESS.RehearsalError):
                HARNESS.request_json(owned, "/healthz")
        opener.assert_not_called()


    def test_cleanup_log_and_probe_errors_do_not_skip_other_handles_or_receipt(self):
        handles = []
        def launched(root, output, report, owners):
            good = self.make_owned(process=FakeProcess(pid=1))
            bad = self.make_owned("worker", FakeProcess(pid=2))
            bad.port = 12345
            bad.log = mock.Mock()
            bad.log.close.side_effect = OSError("controlled log close failure")
            handles.extend((good, bad))
            owners.extend(handles)
            raise RuntimeError("primary fixture failure")
        with mock.patch.object(HARNESS.socket, "socket", side_effect=OSError("controlled probe failure")):
            result = self.run_mock_lifecycle(launched)
        self.assertEqual(result["status"], "failed")
        self.assertEqual([item.process.terminated for item in handles], [1, 1])
        self.assertTrue(any("primary fixture failure" in error for error in result["errors"]))
        self.assertTrue(any("Log close failed" in error for record in result["cleanup"] for error in record["cleanup_errors"]))
        self.assertTrue(any("Listener observation failed" in error for record in result["cleanup"] for error in record["cleanup_errors"]))
        self.assertTrue((self.root / ".local/run/result.json").is_file())

    def test_unresolved_process_cleanup_is_retried_and_early_exit_is_reported(self):
        process = FakeProcess(terminate_error=True, kill_error=True)
        owned = self.make_owned(process=process)
        first = HARNESS.stop_owned([owned])
        self.assertFalse(first[0]["stopped"])
        self.assertFalse(owned.cleanup_complete)
        process.terminate_error = process.kill_error = False
        second = HARNESS.stop_owned([owned])
        self.assertTrue(second[0]["stopped"])
        self.assertEqual(process.terminated, 2)
        exited = self.make_owned("worker")
        exited.process.returncode = 7
        early = HARNESS.stop_owned([exited])
        self.assertTrue(early[0]["stopped"])
        self.assertIn("exited unexpectedly", early[0]["cleanup_errors"][0])

    def test_unexpected_worker_exit_makes_whole_rehearsal_fail(self):
        def completed(root, output, report, owners):
            report["checks"].append({"name": "fixture readiness", "passed": True})
            exited = self.make_owned("worker")
            exited.process.returncode = 7
            owners.append(exited)
        result = self.run_mock_lifecycle(completed)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["errors"])

    def test_heartbeat_uri_preserves_hash_percent_and_spaces_in_directory_name(self):
        data = self.root / "store #percent% spaces"
        data.mkdir()
        with closing(sqlite3.connect(data / "console.sqlite3")) as database:
            database.execute("CREATE TABLE workers (id TEXT, heartbeat REAL)")
            database.execute("INSERT INTO workers VALUES (?, ?)", ("fixture", 123.5))
            database.commit()
        self.assertEqual(HARNESS.read_worker_heartbeat(data, "fixture"), (123.5,))
        self.assertIsNone(HARNESS.read_worker_heartbeat(data, "missing"))

    def test_http_redirect_is_rejected_without_following_destination(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            owned = self.make_owned()
            self.addCleanup(owned.log.close)
            owned.port = server.server_port
            with self.assertRaisesRegex(HARNESS.RehearsalError, "302"):
                HARNESS.request_json(owned, "/redirect")
            self.assertEqual(requests, ["/redirect"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


    def test_windows_children_use_base_binary_and_preserve_venv_without_mutating_input(self):
        environment = {"PATH": "public-fixture-path"}
        with mock.patch.object(HARNESS.os, "name", "nt"), \
                mock.patch.object(HARNESS.sys, "_base_executable", "base-python.exe"), \
                mock.patch.object(HARNESS.sys, "executable", "venv-python.exe"), \
                mock.patch.object(HARNESS.os.path, "isabs", return_value=True), \
                mock.patch.object(HARNESS.os.path, "isfile", return_value=True):
            executable, child = HARNESS.child_python(environment)
        self.assertEqual(executable, "base-python.exe")
        self.assertEqual(child["__PYVENV_LAUNCHER__"], "venv-python.exe")
        self.assertEqual(child["PATH"], environment["PATH"])
        self.assertNotIn("__PYVENV_LAUNCHER__", environment)

    def test_windows_missing_or_relative_base_interpreter_has_no_launcher_fallback(self):
        with mock.patch.object(HARNESS.os, "name", "nt"):
            with mock.patch.object(HARNESS.sys, "_base_executable", None):
                with self.assertRaisesRegex(HARNESS.RehearsalError, "fallback is refused"):
                    HARNESS.child_python({})
            with mock.patch.object(HARNESS.sys, "_base_executable", "missing-base.exe"), \
                    mock.patch.object(HARNESS.os.path, "isabs", return_value=True), \
                    mock.patch.object(HARNESS.os.path, "isfile", return_value=False):
                with self.assertRaises(HARNESS.RehearsalError):
                    HARNESS.child_python({})
            with mock.patch.object(HARNESS.sys, "_base_executable", "relative-base.exe"), \
                    mock.patch.object(HARNESS.os.path, "isabs", return_value=False):
                with self.assertRaises(HARNESS.RehearsalError):
                    HARNESS.child_python({})

    def test_non_windows_children_keep_current_interpreter_and_environment(self):
        environment = {"PATH": "fixture-path", "TEMP": "fixture-temp"}
        with mock.patch.object(HARNESS.os, "name", "posix"), \
                mock.patch.object(HARNESS.sys, "executable", "/fixture/venv/bin/python"), \
                mock.patch.object(HARNESS.sys, "_base_executable", None):
            executable, child = HARNESS.child_python(environment)
        self.assertEqual(executable, "/fixture/venv/bin/python")
        self.assertEqual(child, environment)
        self.assertNotIn("__PYVENV_LAUNCHER__", child)
        self.assertIsNot(child, environment)


if __name__ == "__main__":
    unittest.main()
