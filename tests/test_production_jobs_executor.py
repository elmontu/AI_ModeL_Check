"""Trusted process lifecycle fixtures; never execute request-supplied programs."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from threading import Event, Timer
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from model_release_assurance.production_jobs import executor as jobs
from model_release_assurance.production_storage.backend import _FIXTURE_BYTES, StorageError

JOB = "a" * 32
ATTEMPT = "b" * 32
GATE = "import sys\nif sys.stdin.buffer.read(1) != b'G':\n    raise SystemExit(70)\n"
READ_REQUEST = GATE + "import json, os, time\nfrom pathlib import Path\nrequest=json.loads(sys.stdin.buffer.read(65537))\n"


class ProductionJobsExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-owned-worker-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.runner = jobs.FixtureProcessRunner(self.parent / "runner")
        self.attempt_root = self.runner.root / (JOB + "-" + ATTEMPT)

    def run_worker(self, *, code=None, **kwargs):
        options = {"job_id": JOB, "attempt_id": ATTEMPT, "fixture_bytes": _FIXTURE_BYTES}
        options.update(kwargs)
        if code is None:
            return self.runner.run(**options)
        with mock.patch.object(jobs, "_program", return_value=code):
            return self.runner.run(**options)

    def test_real_fixed_worker_returns_exact_bound_counts_and_frozen_result(self):
        result = self.run_worker()
        self.assertEqual(result.status, "completed", result.to_dict())
        self.assertTrue(result.cleanup_confirmed)
        self.assertEqual(result.exit_code, 0)
        expected = {"schema": jobs.ADAPTER_ID, "input_sha256": hashlib.sha256(_FIXTURE_BYTES).hexdigest(),
                    "categories": 2, "total": 19, "job_id": JOB, "attempt_id": ATTEMPT}
        self.assertEqual(dict(result.output), expected)
        self.assertEqual(result.worker_sha256, jobs.worker_sha256())
        self.assertEqual(result.stderr_bytes, 0)
        self.assertGreater(result.stdout_bytes, 0)
        receipt = result.to_dict()
        self.assertEqual(set(receipt), {"status", "output", "input_sha256", "worker_sha256", "exit_code", "stdout_bytes",
                         "stderr_bytes", "cleanup_confirmed", "elapsed_seconds", "fixture_only", "hostile_code_isolated", "network_isolated"})
        self.assertTrue(receipt["fixture_only"])
        self.assertFalse(receipt["hostile_code_isolated"])
        self.assertFalse(receipt["network_isolated"])
        with self.assertRaises((TypeError, FrozenInstanceError)):
            result.output["total"] = 20
        receipt["output"]["total"] = 20
        self.assertEqual(result.output["total"], 19)
        self.assertEqual({path.name for path in self.attempt_root.iterdir()}, {"temp"})

    def test_invalid_identifiers_private_bytes_timeout_or_stdin_overflow_never_spawn(self):
        cases = [{"job_id": "../elsewhere"}, {"attempt_id": "C" * 32}, {"timeout_seconds": True},
                 {"timeout_seconds": 0}, {"timeout_seconds": 31}, {"fixture_bytes": b'PK\x03\x04'},
                 {"fixture_bytes": b'{"counts":[{"category":"private","count":19}]}'}, {"cancel_event": object()},
                 {"fixture_bytes": _FIXTURE_BYTES + b' ' * (64 * 1024 - len(_FIXTURE_BYTES))}]
        with mock.patch.object(jobs.subprocess, "Popen") as start:
            for changes in cases:
                with self.subTest(changes=list(changes)), self.assertRaises((ValueError, StorageError)):
                    self.run_worker(**changes)
            start.assert_not_called()
        self.assertEqual(list(self.runner.root.iterdir()), [])

    def test_fresh_root_and_attempt_tombstones_refuse_overwrite(self):
        with self.assertRaises(ValueError):
            jobs.FixtureProcessRunner(self.runner.root)
        with self.assertRaises(ValueError):
            jobs.FixtureProcessRunner(self.parent / ".." / "outside")
        event = Event()
        event.set()
        result = self.run_worker(cancel_event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertTrue(result.cleanup_confirmed)
        with self.assertRaises(ValueError):
            self.run_worker()
        with self.assertRaises(ValueError):
            self.run_worker(job_id="d" * 32)
        with mock.patch.object(jobs, "MAX_ATTEMPTS", 1), self.assertRaises(ValueError):
            self.run_worker(attempt_id="c" * 32)

    def test_reparse_or_directory_substitution_fails_before_launch(self):
        original = Path.lstat
        def substituted(path, *args, **kwargs):
            if path == self.runner.root:
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", substituted), mock.patch.object(jobs.subprocess, "Popen") as start:
            with self.assertRaises(ValueError):
                self.run_worker()
            start.assert_not_called()
        old = self.runner.root.with_name("saved-root")
        self.runner.root.rename(old)
        self.runner.root.mkdir()
        with self.assertRaises(ValueError):
            self.run_worker()

    def test_real_child_has_no_inherited_secret_proxy_python_path_or_site_hooks(self):
        code = READ_REQUEST + "Path('environment.json').write_text(json.dumps({'keys': sorted(os.environ), 'isolated': sys.flags.isolated, 'no_site': sys.flags.no_site, 'cwd': os.getcwd()}))\n"
        with mock.patch.dict(os.environ, {"MRA_SECRET_TEST": "never-forward", "HTTPS_PROXY": "http://invalid", "PYTHONPATH": "arbitrary", "AWS_SECRET_ACCESS_KEY": "never-forward"}):
            result = self.run_worker(code=code)
        self.assertEqual(result.status, "failed")  # No valid adapter result.
        self.assertTrue(result.cleanup_confirmed)
        observed = json.loads((self.attempt_root / "environment.json").read_text())
        for forbidden in ("MRA_SECRET_TEST", "HTTPS_PROXY", "PYTHONPATH", "AWS_SECRET_ACCESS_KEY", "PATH"):
            self.assertNotIn(forbidden, observed["keys"])
        self.assertEqual(observed["isolated"], 1)
        self.assertEqual(observed["no_site"], 1)
        self.assertEqual(Path(observed["cwd"]), self.attempt_root)

    def test_real_timeout_terminates_owned_worker(self):
        started = time.monotonic()
        result = self.run_worker(code=READ_REQUEST + "time.sleep(30)\n", timeout_seconds=1)
        self.assertEqual(result.status, "timed_out", result.to_dict())
        self.assertTrue(result.cleanup_confirmed)
        self.assertIsNone(result.output)
        self.assertLess(time.monotonic() - started, 5)

    def test_real_cancellation_terminates_owned_worker(self):
        event = Event()
        timer = Timer(0.25, event.set)
        timer.start()
        self.addCleanup(timer.cancel)
        result = self.run_worker(code=READ_REQUEST + "time.sleep(30)\n", cancel_event=event)
        self.assertEqual(result.status, "cancelled", result.to_dict())
        self.assertTrue(result.cleanup_confirmed)
        self.assertIsNone(result.output)

    def test_stdout_and_stderr_floods_have_bounded_buffers_and_fail(self):
        original = jobs._Capture
        for index, destination in enumerate(("stdout", "stderr")):
            captures = []
            def capture(*args, **kwargs):
                value = original(*args, **kwargs)
                captures.append(value)
                return value
            code = READ_REQUEST + f"while True:\n    sys.{destination}.buffer.write(b'x' * 4096)\n"
            with mock.patch.object(jobs, "_Capture", side_effect=capture):
                result = self.run_worker(code=code, attempt_id=str(index + 1) * 32)
            self.assertEqual(result.status, "output_limit", result.to_dict())
            self.assertTrue(result.cleanup_confirmed)
            self.assertIsNone(result.output)
            self.assertLessEqual(len(captures[0].content), jobs.MAX_STDOUT_BYTES)
            self.assertLessEqual(len(captures[1].content), jobs.MAX_STDERR_BYTES)
            self.assertGreater(getattr(result, destination + "_bytes"), getattr(jobs, "MAX_" + destination.upper() + "_BYTES"))

    def test_malformed_extra_or_mismatched_output_and_nonzero_exit_fail(self):
        for index, tail in enumerate(("sys.stdout.write('{}')\n", "sys.stdout.write('{\"total\":19,\"total\":19}')\n", "raise SystemExit(4)\n")):
            result = self.run_worker(code=READ_REQUEST + tail, attempt_id=str(index + 1) * 32)
            self.assertEqual(result.status, "failed", result.to_dict())
            self.assertTrue(result.cleanup_confirmed)
            self.assertIsNone(result.output)
        result = self.run_worker(code=jobs._WORKER_SOURCE + "sys.stderr.write('unexpected')\n", attempt_id="4" * 32)
        self.assertEqual(result.status, "failed")
        self.assertGreater(result.stderr_bytes, 0)

    def test_real_descendant_cannot_survive_timeout_or_keep_output_pipe_open(self):
        child = "import time; from pathlib import Path; time.sleep(2); Path('descendant-survived').write_text('bad')"
        spawn = "import subprocess\nsubprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', " + repr(child) + "])\n"
        result = self.run_worker(code=READ_REQUEST + spawn + "time.sleep(30)\n", timeout_seconds=1)
        if os.name == "nt":
            self.assertEqual(result.status, "timed_out", result.to_dict())
            self.assertTrue(result.cleanup_confirmed)
        else:
            # Some POSIX supervisors leave killed orphan zombies in the group.
            # The runner must reject unconfirmed cleanup rather than qualify it.
            self.assertIn(result.status, {"timed_out", "cleanup_failed"}, result.to_dict())
            self.assertEqual(result.cleanup_confirmed, result.status == "timed_out")
        self.assertIsNone(result.output)
        time.sleep(1.2)
        self.assertFalse((self.attempt_root / "descendant-survived").exists())

    def test_real_early_parent_exit_cleans_descendant_inherited_pipes(self):
        child = "import time; from pathlib import Path; time.sleep(1); Path('descendant-survived').write_text('bad')"
        spawn = "import subprocess\nsubprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', " + repr(child) + "])\n"
        # The trusted fault fixture produces the valid summary then leaves a
        # descendant holding the pipes. Cleanup must not wait forever for EOF.
        result = self.run_worker(code=jobs._WORKER_SOURCE + spawn, timeout_seconds=5)
        if os.name == "nt":
            self.assertEqual(result.status, "completed", result.to_dict())
            self.assertTrue(result.cleanup_confirmed)
        else:
            self.assertIn(result.status, {"completed", "cleanup_failed"}, result.to_dict())
            self.assertEqual(result.cleanup_confirmed, result.status == "completed")
        if result.status == "cleanup_failed":
            self.assertIsNone(result.output)
        else:
            self.assertEqual(result.output["total"], 19)
            self.assertEqual(result.output["job_id"], JOB)
            self.assertEqual(result.output["attempt_id"], ATTEMPT)
        time.sleep(1.1)
        self.assertFalse((self.attempt_root / "descendant-survived").exists())

    def test_spawn_failure_retains_attempt_and_returns_failed_without_false_output(self):
        with mock.patch.object(jobs.subprocess, "Popen", side_effect=OSError("test launch failed")):
            result = self.run_worker()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.cleanup_confirmed)
        self.assertIsNone(result.exit_code)
        self.assertIsNone(result.output)
        self.assertTrue(self.attempt_root.is_dir())

    def test_assignment_failure_never_releases_bootstrap_and_cleans_owned_handle(self):
        if os.name != "nt":
            self.assertTrue(hasattr(os, "WNOWAIT"))
            return
        code = GATE + "from pathlib import Path\nPath('released-work').write_text('bad')\n"
        with mock.patch.object(jobs._WindowsJob, "assign", side_effect=RuntimeError("test nested assignment refused")):
            result = self.run_worker(code=code)
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.cleanup_confirmed)
        self.assertFalse((self.attempt_root / "released-work").exists())

    def test_cleanup_failure_never_accepts_a_successful_summary(self):
        original = jobs._stop
        def unconfirmed(*args):
            self.assertTrue(original(*args))  # Real cleanup still occurs.
            return False
        with mock.patch.object(jobs, "_stop", side_effect=unconfirmed):
            result = self.run_worker()
        self.assertEqual(result.status, "cleanup_failed")
        self.assertFalse(result.cleanup_confirmed)
        self.assertIsNone(result.output)


if __name__ == "__main__":
    unittest.main()
