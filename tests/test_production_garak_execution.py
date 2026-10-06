"""Owned fixed-program garak lifecycle tests; no upstream dependency is needed."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from model_release_assurance.production_garak import execution

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv-pipeline' / 'Scripts' / 'python.exe'
GATE = "import sys\nif sys.stdin.buffer.read(1) != b'G': raise SystemExit(70)\n"
RESULT = "from pathlib import Path\nPath(sys.argv[-1], 'worker.json').write_bytes(b'{}')\n"
SOURCE = {'trusted-fixture.py': 'a' * 64}
DESCRIPTOR = {'base_python': 'fixed-base-python', 'site_packages': 'fixed-site-packages'}


class GarakExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mra-garak-executor-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root / 'input.json'
        self.input.write_bytes(b'{}\n')
        self.sequence = 0

    def destination(self):
        self.sequence += 1
        return self.root / ('attempt-' + str(self.sequence))

    def require_windows(self):
        if os.name == 'nt':
            return True
        # This milestone deliberately refuses an unqualified process platform.
        with mock.patch.object(execution.subprocess, 'Popen') as start:
            with self.assertRaises(ValueError):
                execution.run_worker(PYTHON, self.input, self.destination())
            start.assert_not_called()
        return False

    def live(self, tail=RESULT, **options):
        destination = self.destination()
        with mock.patch.object(execution, 'BOOTSTRAP', GATE + tail), \
                mock.patch.object(execution, 'source_snapshot', return_value=SOURCE):
            result = execution.run_worker(PYTHON, self.input, destination, **options)
        return result, destination

    def mocked(self, *, capture_factory=None, before_return=None, stop=True, source_values=None, descriptor_values=None, **options):
        destination = self.destination()
        stdin, stdout, stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
        process = SimpleNamespace(stdin=stdin, stdout=stdout, stderr=stderr,
                                  returncode=0, poll=lambda: 0)
        captures = []
        def capture(stream, maximum, overflow):
            if capture_factory is not None:
                value = capture_factory(stream, maximum, overflow, len(captures))
            else:
                value = SimpleNamespace(stream=stream, count=0, content=bytearray(), error=False,
                        thread=SimpleNamespace(start=lambda: None, join=lambda **_: None, is_alive=lambda: False))
            captures.append(value)
            return value
        def spawn(*args, **kwargs):
            (destination / 'worker.json').write_bytes(b'{}')
            if before_return is not None:
                before_return(process, destination)
            return process
        with mock.patch.object(execution, 'runtime_descriptor', return_value=DESCRIPTOR, side_effect=descriptor_values), \
                mock.patch.object(execution, 'source_snapshot', return_value=SOURCE, side_effect=source_values), \
                mock.patch.object(execution, '_WindowsJob') as job, \
                mock.patch.object(execution, '_Capture', side_effect=capture), \
                mock.patch.object(execution, '_stop', return_value=stop) as cleanup, \
                mock.patch.object(execution.subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
                mock.patch.object(execution.subprocess, 'Popen', side_effect=spawn) as start:
            result = execution.run_worker(PYTHON, self.input, destination, **options)
        return result, destination, process, captures, start, cleanup, job

    def test_real_owned_success_is_bound_and_retains_nonisolation_flags(self):
        if not self.require_windows():
            return
        result, destination = self.live()
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['result'], {})
        self.assertEqual(result['input_sha256'], execution.sha(self.input.read_bytes()))
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['exit_code'], 0)
        for name in ('hostile_code_isolated', 'network_isolated', 'filesystem_isolated', 'resource_limits_verified'):
            self.assertIs(result[name], False)
        retained = json.loads((destination / 'process.json').read_bytes())
        self.assertNotIn('result', retained)
        self.assertEqual(retained, {key: value for key, value in result.items() if key != 'result'})
        self.assertEqual((destination / 'stdout.log').read_bytes(), b'')
        self.assertEqual((destination / 'stderr.log').read_bytes(), b'')

    def test_real_environment_excludes_secrets_and_site_startup(self):
        if not self.require_windows():
            return
        code = RESULT + "import os, json\nPath('environment.json').write_text(json.dumps({'keys': sorted(os.environ), 'isolated': sys.flags.isolated, 'no_site': sys.flags.no_site, 'bytecode': sys.dont_write_bytecode}))\n"
        with mock.patch.dict(os.environ, {'MRA_PRIVATE_TEST': 'not-forwarded', 'HTTPS_PROXY': 'invalid',
                                         'AWS_SECRET_ACCESS_KEY': 'not-forwarded', 'PYTHONPATH': 'invalid'}):
            result, destination = self.live(code)
        self.assertEqual(result['status'], 'completed', result)
        observed = json.loads((destination / 'environment.json').read_bytes())
        self.assertEqual(observed['isolated'], 1)
        self.assertEqual(observed['no_site'], 1)
        self.assertTrue(observed['bytecode'])
        for key in ('APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'GARAK_LOG_FILE', 'NLTK_DATA'):
            self.assertIn(key, observed['keys'])
        for key in ('MRA_PRIVATE_TEST', 'HTTPS_PROXY', 'AWS_SECRET_ACCESS_KEY', 'PYTHONPATH', 'PATH'):
            self.assertNotIn(key, observed['keys'])

    def test_real_timeout_terminates_owned_process_before_return(self):
        if not self.require_windows():
            return
        started = time.monotonic()
        result, destination = self.live("import time\ntime.sleep(60)\n", timeout_seconds=1)
        self.assertEqual(result['status'], 'timed_out', result)
        self.assertTrue(result['cleanup_confirmed'])
        self.assertNotIn('result', result)
        self.assertLess(time.monotonic() - started, 10)
        self.assertTrue((destination / 'process.json').is_file())

    def test_real_stdout_and_stderr_floods_never_return_worker_result(self):
        if not self.require_windows():
            return
        for name in ('stdout', 'stderr'):
            with self.subTest(stream=name):
                code = RESULT + f"sys.{name}.buffer.write(b'x' * (128 * 1024))\nsys.{name}.flush()\n"
                result, destination = self.live(code, timeout_seconds=5)
                self.assertEqual(result['status'], 'output_limit', result)
                self.assertTrue(result['cleanup_confirmed'])
                self.assertNotIn('result', result)
                self.assertGreater(result[name + '_bytes'], 64 * 1024)
                self.assertLessEqual((destination / (name + '.log')).stat().st_size, 64 * 1024)

    def test_real_timeout_removes_descendant_inheriting_pipes(self):
        if not self.require_windows():
            return
        child = "import time; from pathlib import Path; time.sleep(2); Path('descendant-survived').write_text('bad')"
        tail = "import subprocess, time\nsubprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', " + repr(child) + "])\ntime.sleep(60)\n"
        result, destination = self.live(tail, timeout_seconds=1)
        self.assertEqual(result['status'], 'timed_out', result)
        self.assertTrue(result['cleanup_confirmed'])
        time.sleep(1.2)
        self.assertFalse((destination / 'descendant-survived').exists())

    def test_assignment_failure_never_releases_gate_and_closes_all_pipes(self):
        if not self.require_windows():
            return
        launched = []
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            launched.append(process)
            return process
        with mock.patch.object(execution.subprocess, 'Popen', side_effect=spawn), \
                mock.patch.object(execution._WindowsJob, 'assign', side_effect=RuntimeError('assignment refused')):
            result, destination = self.live("from pathlib import Path\nPath('gate-released').write_text('bad')\n")
        self.assertEqual(result['status'], 'failed', result)
        self.assertTrue(result['cleanup_confirmed'])
        self.assertFalse((destination / 'gate-released').exists())
        self.assertIsNotNone(launched[0].poll())
        self.assertTrue(all(stream.closed for stream in (launched[0].stdin, launched[0].stdout, launched[0].stderr)))
        self.assertTrue((destination / 'process.json').is_file())

    def test_launch_failure_still_closes_job_and_writes_failure_receipt(self):
        destination = self.destination()
        with mock.patch.object(execution, 'runtime_descriptor', return_value=DESCRIPTOR), \
                mock.patch.object(execution, 'source_snapshot', return_value=SOURCE), \
                mock.patch.object(execution, '_WindowsJob') as job, \
                mock.patch.object(execution.subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
                mock.patch.object(execution.subprocess, 'Popen', side_effect=OSError('launch refused')):
            result = execution.run_worker(PYTHON, self.input, destination)
        self.assertEqual(result['status'], 'failed', result)
        self.assertTrue(result['cleanup_confirmed'])
        job.return_value.close.assert_called_once()
        self.assertNotIn('result', result)
        self.assertEqual(json.loads((destination / 'process.json').read_bytes()), result)

    def test_late_capture_overflow_after_successful_exit_is_rejected(self):
        def captures(stream, maximum, overflow, index):
            value = SimpleNamespace(stream=stream, count=0, content=bytearray(), error=False)
            def join(**_):
                if index == 0:
                    value.count = maximum + 1
                    value.content.extend(b'x' * maximum)
                    overflow.set()
            value.thread = SimpleNamespace(start=lambda: None, join=join, is_alive=lambda: False)
            return value
        result, destination, process, captures, start, _, _ = self.mocked(capture_factory=captures)
        self.assertEqual(result['status'], 'output_limit', result)
        self.assertEqual(result['exit_code'], 0)
        self.assertNotIn('result', result)
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(start.call_args.kwargs['bufsize'], 0)
        self.assertEqual((destination / 'stdout.log').stat().st_size, 64 * 1024)
        self.assertTrue(all(stream.closed for stream in (process.stdin, process.stdout, process.stderr)))

    def test_close_error_does_not_skip_other_handles_or_receipt(self):
        closed = []
        class BrokenClose(io.BytesIO):
            def close(self):
                closed.append('broken')
                super().close()
                raise OSError('close failed after release')
        def replace(process, _destination):
            process.stdout = BrokenClose()
        result, destination, process, _, _, _, _ = self.mocked(before_return=replace)
        self.assertEqual(result['status'], 'cleanup_unconfirmed', result)
        self.assertFalse(result['cleanup_confirmed'])
        self.assertNotIn('result', result)
        self.assertTrue(closed)
        self.assertTrue(process.stderr.closed)
        self.assertTrue(process.stdin.closed)
        self.assertTrue((destination / 'process.json').is_file())

    def test_unconfirmed_cleanup_never_exposes_valid_output(self):
        result, destination, *_ = self.mocked(stop=False)
        self.assertEqual(result['status'], 'cleanup_unconfirmed')
        self.assertFalse(result['cleanup_confirmed'])
        self.assertNotIn('result', result)
        self.assertTrue((destination / 'worker.json').is_file())

    def test_input_change_during_child_is_rejected(self):
        def replace(_process, _destination):
            self.input.write_bytes(b'{"changed":true}')
        result, _, *_ = self.mocked(before_return=replace)
        self.assertEqual(result['status'], 'binding_changed', result)
        self.assertNotIn('result', result)

    def test_source_or_runtime_change_during_child_is_rejected(self):
        changes = ({'source_values': [SOURCE, {'trusted-fixture.py': 'b' * 64}]},
                   {'descriptor_values': [DESCRIPTOR, {**DESCRIPTOR, 'base_sha256': 'b' * 64}]})
        for options in changes:
            with self.subTest(binding=next(iter(options))):
                result, destination, *_ = self.mocked(**options)
                self.assertEqual(result['status'], 'binding_changed', result)
                self.assertTrue(result['cleanup_confirmed'])
                self.assertNotIn('result', result)
                self.assertTrue((destination / 'process.json').is_file())

    def test_invalid_timeout_is_refused_before_spawn_or_output(self):
        with mock.patch.object(execution.subprocess, 'Popen') as start:
            for value in (True, False, 0, -1, 601, 1.0, '1', None):
                destination = self.destination()
                with self.subTest(value=value), self.assertRaises(ValueError):
                    execution.run_worker(PYTHON, self.input, destination, timeout_seconds=value)
                self.assertFalse(destination.exists())
            start.assert_not_called()

    def test_missing_critical_source_is_rejected_without_deleting_files(self):
        package = Path(execution.__file__).parent.parent
        original = Path.rglob
        for missing in ('production_garak/pins.py', 'production_jobs/executor.py',
                        'production_evidence/replay.py', 'production_identity/tokens.py'):
            def filtered(path, pattern):
                return (item for item in original(path, pattern)
                        if path != package or item.relative_to(package).as_posix() != missing)
            with self.subTest(missing=missing), mock.patch.object(Path, 'rglob', filtered):
                with self.assertRaises(ValueError):
                    execution.source_snapshot()

    def test_source_inventory_is_bounded_and_includes_required_sources(self):
        snapshot = execution.source_snapshot()
        self.assertLessEqual(len(snapshot), 256)
        for name in ('production_garak/pins.py', 'production_jobs/executor.py',
                     'production_evidence/replay.py', 'production_identity/tokens.py'):
            self.assertIn(name, snapshot)
            self.assertEqual(len(snapshot[name]), 64)
        package = Path(execution.__file__).parent.parent
        def oversized(_path, _pattern):
            for index in range(258):
                if index == 257:
                    self.fail('Source enumeration continued beyond its bounded sentinel')
                yield package / ('fake-' + str(index) + '.py')
        with mock.patch.object(Path, 'rglob', oversized), self.assertRaises(ValueError):
            execution.source_snapshot()

    def test_real_malformed_or_oversized_worker_file_cannot_be_returned(self):
        if not self.require_windows():
            return
        for content in (b'{"a":1,"a":1}', b'{"a":NaN}', b'x' * (execution.MAX_OUTPUT + 1)):
            with self.subTest(size=len(content)):
                destination = self.destination()
                # Only fixed trusted fault code is substituted; no caller program API exists.
                if len(content) > execution.MAX_OUTPUT:
                    tail = "from pathlib import Path\nPath(sys.argv[-1], 'worker.json').write_bytes(b'x' * (4 * 1024 * 1024 + 1))\n"
                else:
                    tail = "from pathlib import Path\nPath(sys.argv[-1], 'worker.json').write_bytes(" + repr(content) + ")\n"
                with mock.patch.object(execution, 'BOOTSTRAP', GATE + tail), \
                        mock.patch.object(execution, 'source_snapshot', return_value=SOURCE):
                    with self.assertRaises(ValueError):
                        execution.run_worker(PYTHON, self.input, destination)
                self.assertTrue(json.loads((destination / 'process.json').read_bytes())['cleanup_confirmed'])


if __name__ == '__main__':
    unittest.main()
