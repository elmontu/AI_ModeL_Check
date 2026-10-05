"""Pinned runtime selection and non-authorizing public-profile CLI boundaries."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_profile import runtime
from model_release_assurance.production_profile.contracts import FLAGS

REPO = Path(__file__).resolve().parents[1]
CLI = None


def _load_cli():
    global CLI
    if CLI is None:
        spec = importlib.util.spec_from_file_location('mra_public_profile_cli', REPO / 'scripts/rehearse_public_profile.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        CLI = module
    return CLI


class RuntimeSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mra-profile-runtime-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'deploy/sacro').mkdir(parents=True)
        for name in (runtime.LOCK_PATH, runtime.REQUIREMENTS_PATH):
            (self.root / name).write_bytes((REPO / name).read_bytes())
        self.versions = {item['name']: item['version'] for item in json.loads((self.root / runtime.LOCK_PATH).read_bytes())['artifacts']}
        env = self.root / '.local/sacro-env'
        self.site = env / 'Lib/site-packages'
        self.site.mkdir(parents=True)
        self.python = env / 'Scripts/python.exe'
        self.python.parent.mkdir()
        self.python.write_bytes(b'test-launcher')
        self.metadata = {}
        for name, version in self.versions.items():
            path = self.site / (name.replace('-', '_') + '-' + version + '.dist-info')
            path.mkdir()
            raw = ('Name: ' + name + '\nVersion: ' + version + '\n\n').encode()
            self.metadata[name] = path / 'METADATA'
            self.metadata[name].write_bytes(raw)
        self.descriptor = {'python': str(self.python), 'site_packages': str(self.site),
            'base_python': str(self.root / 'base-python.exe'), 'base_sha256': 'b' * 64,
            'launcher_sha256': 'a' * 64, 'configuration_sha256': 'c' * 64}
        patcher = mock.patch.object(runtime, 'runtime_descriptor', return_value=self.descriptor)
        self.describe = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(runtime, 'SACRO_METADATA_SHA256', hashlib.sha256(self.metadata['sacroml'].read_bytes()).hexdigest())
        patcher.start()
        self.addCleanup(patcher.stop)

    def load(self):
        return runtime.load_runtime(self.root, self.python)

    def test_exact_runtime_metadata_is_read_only_and_owned(self):
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = self.load()
        self.assertEqual(result['versions'], self.versions)
        self.assertEqual(result['lock_sha256'], runtime.LOCK_SHA256)
        result['versions']['numpy'] = 'changed'
        self.assertEqual(self.load()['versions'], self.versions)
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_direct_spec_requires_exact_roster_and_pinned_hash(self):
        self.assertEqual(runtime.validate_spec(self.versions, runtime.LOCK_SHA256), self.versions)
        for versions, pin in (({**self.versions, 'numpy': '0'}, runtime.LOCK_SHA256),
            ({k: v for k, v in self.versions.items() if k != 'sacroml'}, runtime.LOCK_SHA256),
            ({**self.versions, 'extra': '1'}, runtime.LOCK_SHA256),
            (self.versions, '0' * 64), ({**self.versions, 'numpy': True}, runtime.LOCK_SHA256),
            (list(self.versions.items()), runtime.LOCK_SHA256)):
            with self.subTest(pin=pin), self.assertRaises(runtime.RuntimeError):
                runtime.validate_spec(versions, pin)

    def test_changed_lock_or_requirements_are_rejected_before_descriptor(self):
        for name in (runtime.LOCK_PATH, runtime.REQUIREMENTS_PATH):
            path = self.root / name
            saved = path.read_bytes()
            path.write_bytes(saved + b' ')
            with self.subTest(name=name), self.assertRaises(runtime.RuntimeError):
                self.load()
            path.write_bytes(saved)
        self.describe.assert_not_called()

    def test_outside_and_traversal_runtime_paths_are_rejected(self):
        for python in (self.root / 'elsewhere/python.exe', self.root / '.local/../elsewhere/python.exe'):
            with self.subTest(python=python), self.assertRaises(runtime.RuntimeError):
                runtime.load_runtime(self.root, python)
        self.describe.assert_not_called()

    def test_missing_or_changed_dependency_version_is_rejected(self):
        path = self.metadata['numpy']
        saved = path.read_bytes()
        path.write_bytes(b'Name: numpy\nVersion: 0\n\n')
        with self.assertRaises(runtime.RuntimeError):
            self.load()
        path.write_bytes(saved)
        path.unlink()
        with self.assertRaises(runtime.RuntimeError):
            self.load()

    def test_duplicate_metadata_headers_or_distribution_are_rejected(self):
        path = self.metadata['numpy']
        saved = path.read_bytes()
        path.write_bytes(b'Name: numpy\nName: pandas\nVersion: 2.5.3\n\n')
        with self.assertRaises(runtime.RuntimeError):
            self.load()
        path.write_bytes(saved)
        duplicate = self.site / 'duplicate.dist-info'
        duplicate.mkdir()
        (duplicate / 'METADATA').write_bytes(saved)
        with self.assertRaises(runtime.RuntimeError):
            self.load()

    def test_only_prior_mra_distribution_may_be_extra(self):
        extra = self.site / 'model_release_assurance-0.dist-info'
        extra.mkdir()
        metadata = extra / 'METADATA'
        metadata.write_bytes(b'Name: model-release-assurance\nVersion: 0\n\n')
        self.load()
        metadata.write_bytes(b'Name: unexpected-runtime-plugin\nVersion: 0\n\n')
        with self.assertRaises(runtime.RuntimeError):
            self.load()

    def test_sacro_metadata_and_runtime_descriptor_drift_are_rejected(self):
        path = self.metadata['sacroml']
        saved = path.read_bytes()
        path.write_bytes(saved + b'changed')
        with self.assertRaises(runtime.RuntimeError):
            self.load()
        path.write_bytes(saved)
        self.describe.side_effect = [self.descriptor, {**self.descriptor, 'base_sha256': 'd' * 64}]
        with self.assertRaises(runtime.RuntimeError):
            self.load()

    def test_metadata_is_rechecked_after_runtime_observation(self):
        calls = []
        def descriptor(python):
            calls.append(python)
            if len(calls) == 2:
                path = self.metadata['numpy']
                path.write_bytes(path.read_bytes() + b'changed')
            return dict(self.descriptor)
        self.describe.side_effect = descriptor
        with self.assertRaises(runtime.RuntimeError):
            self.load()

    def test_hardlinked_metadata_is_rejected(self):
        os.link(self.metadata['numpy'], self.root / 'other-metadata')
        with self.assertRaises(runtime.RuntimeError):
            self.load()

    def test_metadata_size_and_enumeration_are_bounded(self):
        self.metadata['numpy'].write_bytes(b'x' * (runtime.MAX_METADATA + 1))
        with self.assertRaises(runtime.RuntimeError):
            self.load()
        enumerated = []
        def excessive(path):
            for index in range(runtime.MAX_SITE_ENTRIES + 100):
                enumerated.append(index)
                yield self.site / str(index)
        with mock.patch.object(Path, 'iterdir', excessive), self.assertRaises(runtime.RuntimeError):
            self.load()
        self.assertEqual(len(enumerated), runtime.MAX_SITE_ENTRIES + 1)


class PublicProfileCLITests(unittest.TestCase):
    def setUp(self):
        _load_cli()
        temporary = tempfile.TemporaryDirectory(prefix='mra-public-profile-cli-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], capture_output=True, check=True)
        (self.root / '.gitignore').write_text('.local/\n', encoding='utf-8')
        self.snapshot = {'scope': 'test', 'files': [], 'sha256': 'a' * 64}
        self.spec = {'python': str(self.root / '.local/runtime/Scripts/python.exe'),
            'versions': {'sacroml': '2.0.1'}, 'lock_sha256': runtime.LOCK_SHA256,
            'descriptor': {'test': 'runtime'}}
        self.success = {'status': 'passed', 'checks': [{'name': name, 'passed': True}
            for name in sorted(CLI.REQUIRED_CHECKS - {'source_unchanged'})], **FLAGS}

    def run_fixture(self, name='run'):
        with mock.patch.object(CLI, 'source_snapshot', return_value=self.snapshot), mock.patch.object(CLI, 'load_runtime', return_value=self.spec):
            return CLI.run_rehearsal(root=self.root, output='.local/' + name,
                python=self.spec['python'], profile='local_public_fixture')

    def test_default_production_refusal_precedes_runtime_output_and_training(self):
        with mock.patch.object(CLI, 'load_runtime') as load, mock.patch.object(CLI, 'exercise') as exercise:
            with self.assertRaises(CLI.ProfileRefused):
                CLI.run_rehearsal(root=self.root, output='.local/blocked', python='missing')
        load.assert_not_called()
        exercise.assert_not_called()
        self.assertFalse((self.root / '.local').exists())

    def test_unavailable_runtime_creates_no_output(self):
        with mock.patch.object(CLI, 'load_runtime', side_effect=runtime.RuntimeError), mock.patch.object(CLI, 'exercise') as exercise:
            with self.assertRaises(runtime.RuntimeError):
                CLI.run_rehearsal(root=self.root, output='.local/blocked', python='missing', profile='local_public_fixture')
        exercise.assert_not_called()
        self.assertFalse((self.root / '.local').exists())

    def test_exact_complete_fixture_report_passes_with_owned_version_input(self):
        def exercise(output, **kwargs):
            self.assertEqual(kwargs['lock_sha256'], runtime.LOCK_SHA256)
            kwargs['versions']['sacroml'] = 'mutated'
            return self.success
        with mock.patch.object(CLI, 'exercise', side_effect=exercise):
            report = self.run_fixture()
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['runtime']['versions'], {'sacroml': '2.0.1'})
        self.assertEqual(report, json.loads((self.root / '.local/run/result.json').read_bytes()))
        self.assertEqual(len(report['checks']), 18)

    def test_missing_duplicate_false_or_nonboolean_milestones_cannot_pass(self):
        checks = self.success['checks'] + [{'name': 'source_unchanged', 'passed': True}]
        self.assertTrue(CLI._complete_checks(checks))
        for bad in (checks[:-1], [*checks[:-1], checks[0]],
                    [{**checks[0], 'passed': False}, *checks[1:]],
                    [{**checks[0], 'passed': 1}, *checks[1:]]):
            self.assertFalse(CLI._complete_checks(bad))
        with mock.patch.object(CLI, 'exercise', return_value={'status': 'passed', 'checks': [], **FLAGS}):
            self.assertEqual(self.run_fixture()['status'], 'failed')

    def test_flags_cannot_be_forged_and_exception_text_is_redacted(self):
        with mock.patch.object(CLI, 'exercise', return_value={**self.success, 'production_authorized': True}):
            report = self.run_fixture('flags')
        self.assertEqual(report['status'], 'failed')
        self.assertIs(report['production_authorized'], False)
        with mock.patch.object(CLI, 'exercise', side_effect=ValueError('secret-token')):
            report = self.run_fixture('error')
        self.assertNotIn('secret-token', json.dumps(report))
        self.assertEqual(report['errors'][0]['type'], 'ValueError')

    def test_source_or_runtime_change_blocks_success(self):
        with mock.patch.object(CLI, 'exercise', return_value=self.success), mock.patch.object(CLI, 'source_snapshot', side_effect=[self.snapshot, {**self.snapshot, 'sha256': 'b' * 64}]), mock.patch.object(CLI, 'load_runtime', return_value=self.spec):
            report = CLI.run_rehearsal(root=self.root, output='.local/source', python='fixture', profile='local_public_fixture')
        self.assertEqual(report['status'], 'failed')
        with mock.patch.object(CLI, 'exercise', return_value=self.success), mock.patch.object(CLI, 'source_snapshot', return_value=self.snapshot), mock.patch.object(CLI, 'load_runtime', side_effect=[self.spec, {**self.spec, 'lock_sha256': '0' * 64}]):
            report = CLI.run_rehearsal(root=self.root, output='.local/runtime', python='fixture', profile='local_public_fixture')
        self.assertEqual(report['status'], 'failed')

    def test_existing_or_outside_output_does_not_overwrite(self):
        with mock.patch.object(CLI, 'exercise', return_value=self.success):
            self.run_fixture()
        saved = (self.root / '.local/run/result.json').read_bytes()
        with mock.patch.object(CLI, 'load_runtime', return_value=self.spec):
            for output in ('.local/run', '.local/../elsewhere', 'elsewhere/run'):
                with self.subTest(output=output), self.assertRaises(CLI._BASELINE.BaselineError):
                    CLI.run_rehearsal(root=self.root, output=output, python='fixture', profile='local_public_fixture')
        self.assertEqual(saved, (self.root / '.local/run/result.json').read_bytes())

    def test_missing_source_prevents_exercise(self):
        with mock.patch.object(CLI, 'load_runtime', return_value=self.spec), mock.patch.object(CLI, 'exercise') as exercise:
            report = CLI.run_rehearsal(root=self.root, output='.local/run', python='fixture', profile='local_public_fixture')
        self.assertEqual(report['status'], 'failed')
        exercise.assert_not_called()

    def test_nonfinite_or_oversized_report_is_bounded_failure(self):
        for index, evidence in enumerate((float('nan'), 'x' * CLI.MAX_REPORT_BYTES)):
            with mock.patch.object(CLI, 'exercise', return_value={**self.success, 'evidence': evidence}):
                report = self.run_fixture('report-' + str(index))
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['errors'][0]['type'], 'InvalidOrOversizedReport')

    def test_cli_default_and_bad_modes_create_nothing(self):
        with mock.patch.object(CLI, 'ROOT', self.root), mock.patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(CLI.main(['--output', '.local/default']), 2)
        for arguments in (['--output', '.local/missing-python'],
            ['--replay', '.local/missing-pins'],
            ['--output', '.local/no-replay', '--python', 'fixture', '--expected-key-sha256', 'a' * 64]):
            with mock.patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                CLI.main(['--profile', 'local_public_fixture', *arguments])
            self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / '.local').exists())

    def test_cli_rejects_arbitrary_data_model_benchmark_and_recipient_arguments(self):
        for option in ('--data', '--data-root', '--model', '--artifact', '--benchmark', '--recipient'):
            with self.subTest(option=option), mock.patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                CLI.main(['--profile', 'local_public_fixture', '--output', '.local/no-input', '--python', 'fixture', option, 'caller-input'])
            self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / '.local').exists())

    def test_replay_is_read_only_requires_both_pins_and_skips_training(self):
        target = self.root / '.local/historical'
        target.mkdir(parents=True)
        (target / 'marker').write_bytes(b'unchanged')
        expected = {'status': 'historical_fixture_replay_verified', 'current_authorization_checked': False, **FLAGS}
        with mock.patch.object(CLI, 'verify_receipt', return_value=expected) as verify, mock.patch.object(CLI, 'exercise') as exercise, mock.patch.object(CLI, 'load_runtime') as load:
            actual = CLI.replay(root=self.root, path='.local/historical', expected_receipt_sha256='a' * 64,
                                expected_key_sha256='b' * 64, profile='local_public_fixture')
        self.assertEqual(actual, expected)
        verify.assert_called_once_with(target, expected_receipt_sha256='a' * 64, expected_key_sha256='b' * 64)
        exercise.assert_not_called()
        load.assert_not_called()
        self.assertEqual(list(target.iterdir()), [target / 'marker'])
        self.assertEqual((target / 'marker').read_bytes(), b'unchanged')

    def test_replay_default_bad_pins_missing_and_outside_paths_fail_before_verifier(self):
        with mock.patch.object(CLI, 'verify_receipt') as verify:
            with self.assertRaises(CLI.ProfileRefused):
                CLI.replay(root=self.root, path='.local/none', expected_receipt_sha256='a' * 64, expected_key_sha256='b' * 64)
            for path, receipt, key in (('.local/none', 'A' * 64, 'b' * 64),
                ('outside', 'a' * 64, 'b' * 64), ('.local/../outside', 'a' * 64, 'b' * 64),
                ('.local', 'a' * 64, 'b' * 64), ('.local/missing', 'a' * 64, 'b' * 64)):
                with self.subTest(path=path), self.assertRaises((CLI.RehearsalError, CLI._BASELINE.BaselineError)):
                    CLI.replay(root=self.root, path=path, expected_receipt_sha256=receipt, expected_key_sha256=key, profile='local_public_fixture')
        verify.assert_not_called()

    def test_replay_cannot_claim_current_or_production_authority(self):
        (self.root / '.local/historical').mkdir(parents=True)
        for change in ({'current_authorization_checked': True}, {'production_authorized': True}, {'status': 'passed'}):
            fake = {'status': 'historical_fixture_replay_verified', 'current_authorization_checked': False, **FLAGS, **change}
            with mock.patch.object(CLI, 'verify_receipt', return_value=fake), self.assertRaises(CLI.RehearsalError):
                CLI.replay(root=self.root, path='.local/historical', expected_receipt_sha256='a' * 64, expected_key_sha256='b' * 64, profile='local_public_fixture')

    def test_source_snapshot_includes_all_profile_sources_and_both_pinned_locks(self):
        snapshot = CLI.source_snapshot(REPO)
        names = {row['path'] for row in snapshot['files']}
        self.assertTrue(set(CLI.SOURCE_FILES) <= names)
        self.assertIn('src/model_release_assurance/production_sacro/execution.py', names)
        self.assertIn('src/model_release_assurance/production_delivery/gateway.py', names)


if __name__ == '__main__':
    unittest.main()
