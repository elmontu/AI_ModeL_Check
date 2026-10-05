"""Bounded command evidence for a real policy-before-fit public rehearsal."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_review.rehearsal import FixtureTokenIssuer
from model_release_assurance.production_review.contracts import FLAGS

SPEC = importlib.util.spec_from_file_location('mra_review_cli', Path(__file__).resolve().parents[1] / 'scripts/rehearse_policy_review.py')
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class ReviewCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mra-review-cli-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], capture_output=True, check=True)
        (self.root / '.gitignore').write_text('.local/\n', encoding='utf-8')
        self.snapshot = {'scope': 'test', 'files': [], 'sha256': 'a' * 64}

    def run_fixture(self, name='run'):
        with mock.patch.object(CLI, 'source_snapshot', return_value=self.snapshot):
            return CLI.run_rehearsal(root=self.root, output='.local/' + name)

    def successful_exercise(self):
        return {'status': 'passed', 'checks': [{'name': name, 'passed': True}
            for name in sorted(CLI.REQUIRED_CHECKS - {'source_unchanged'})], **FLAGS}

    def test_actual_signed_policy_review_uses_fresh_fit_without_retaining_credentials(self):
        issued = []
        original = FixtureTokenIssuer.issue
        def remember(issuer, *args, **kwargs):
            token = original(issuer, *args, **kwargs)
            issued.append(token)
            return token
        with mock.patch.object(FixtureTokenIssuer, 'issue', remember):
            result = self.run_fixture()
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual({check['name'] for check in result['checks']}, CLI.REQUIRED_CHECKS)
        self.assertTrue(all(check['passed'] for check in result['checks']))
        self.assertEqual(result['summary']['fresh_native_runs'], 1)
        self.assertEqual(result['summary']['profile_id'], 'sklearn-wine')
        self.assertEqual(result['summary']['historical_campaigns'], 3)
        self.assertGreaterEqual(result['summary']['utility_improvement_bps'], 0)
        for key, value in FLAGS.items():
            self.assertIs(result[key], value)
        self.assertEqual(result, json.loads((self.root / '.local/run/result.json').read_bytes()))
        self.assertTrue(issued)
        for path in (self.root / '.local/run').rglob('*'):
            if path.is_file():
                raw = path.read_bytes()
                self.assertNotIn(b'PRIVATE KEY', raw)
                for token in issued:
                    self.assertNotIn(token.encode(), raw)

    def test_complete_milestone_roster_can_pass(self):
        with mock.patch.object(CLI, 'exercise', return_value=self.successful_exercise()):
            self.assertEqual(self.run_fixture()['status'], 'passed')

    def test_workflow_exception_retains_type_without_sensitive_text(self):
        with mock.patch.object(CLI, 'exercise', side_effect=ValueError('private-token')):
            result = self.run_fixture()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['errors'], [{'stage': 'fixture_workflow', 'type': 'ValueError'}])
        self.assertNotIn('private-token', json.dumps(result))

    def test_incomplete_or_failed_workflow_never_reports_success(self):
        for index, result in enumerate(({'status': 'passed', 'checks': [], **FLAGS},
                                       {**self.successful_exercise(), 'status': 'failed'})):
            with self.subTest(index=index), mock.patch.object(CLI, 'exercise', return_value=result):
                self.assertEqual(self.run_fixture('run-' + str(index))['status'], 'failed')

    def test_duplicate_or_nonboolean_or_forged_milestones_fail(self):
        checks = self.successful_exercise()['checks'] + [{'name': 'source_unchanged', 'passed': True}]
        self.assertTrue(CLI._complete_checks(checks))
        for changed in ([*checks[:-1], checks[0]],
                        [{**checks[0], 'passed': 1}, *checks[1:]],
                        [{**checks[0], 'note': 'unverified'}, *checks[1:]]):
            self.assertFalse(CLI._complete_checks(changed))

    def test_forged_authorization_flags_fail(self):
        for index, key in enumerate(FLAGS):
            result = self.successful_exercise()
            result[key] = not FLAGS[key]
            with self.subTest(key=key), mock.patch.object(CLI, 'exercise', return_value=result):
                report = self.run_fixture('flag-' + str(index))
                self.assertEqual(report['status'], 'failed')
                self.assertIs(report[key], FLAGS[key])

    def test_workflow_cannot_replace_source_or_errors_or_report_schema(self):
        result = {**self.successful_exercise(), 'source': {'forged': True},
                  'errors': [], 'schema': 'forged'}
        with mock.patch.object(CLI, 'exercise', return_value=result):
            report = self.run_fixture()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['source'], self.snapshot)
        self.assertEqual(report['schema'], 'mra-fixture-policy-review-rehearsal/v1')

    def test_existing_and_outside_output_cannot_overwrite(self):
        with mock.patch.object(CLI, 'exercise', side_effect=ValueError):
            self.run_fixture()
        saved = (self.root / '.local/run/result.json').read_bytes()
        for output in ('.local/run', '.local/../outside', 'outside/run'):
            with self.subTest(output=output), self.assertRaises(CLI._BASELINE.BaselineError):
                CLI.run_rehearsal(root=self.root, output=output)
        self.assertEqual(saved, (self.root / '.local/run/result.json').read_bytes())

    def test_source_change_blocks_success(self):
        other = {**self.snapshot, 'sha256': 'b' * 64}
        with mock.patch.object(CLI, 'source_snapshot', side_effect=[self.snapshot, other]), mock.patch.object(CLI, 'exercise', return_value=self.successful_exercise()):
            result = CLI.run_rehearsal(root=self.root, output='.local/run')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['checks'][-1], {'name': 'source_unchanged', 'passed': False})

    def test_missing_critical_source_rejects_before_fixture(self):
        with mock.patch.object(CLI, 'exercise') as exercise:
            result = CLI.run_rehearsal(root=self.root, output='.local/run')
        self.assertEqual(result['status'], 'failed')
        exercise.assert_not_called()

    def test_cli_rejects_private_inputs_and_returns_distinct_failure_codes(self):
        with mock.patch.object(CLI, 'ROOT', self.root), mock.patch.object(CLI, 'source_snapshot', return_value=self.snapshot), mock.patch.object(CLI, 'exercise', side_effect=RuntimeError), mock.patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(CLI.main(['--output', '.local/failure']), 1)
            self.assertEqual(CLI.main(['--output', '.local/failure']), 2)
        with mock.patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
            CLI.main(['--output', '.local/data', '--data', 'private.csv'])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / '.local/data').exists())

    def test_source_read_is_bounded_and_rejects_growth(self):
        path = self.root / 'source.py'
        path.write_bytes(b'abcd')
        with self.assertRaises(CLI.RehearsalError):
            CLI._read_source(self.root, 'source.py', 3)
        real = CLI.os.fdopen
        def grow(fd, *args, **kwargs):
            with path.open('ab') as writer:
                writer.write(b'efgh')
            return real(fd, *args, **kwargs)
        with mock.patch.object(CLI.os, 'fdopen', side_effect=grow):
            with self.assertRaises(CLI.RehearsalError):
                CLI._read_source(self.root, 'source.py', 4)

    def test_oversized_report_is_replaced_by_bounded_failure(self):
        result = {**self.successful_exercise(), 'evidence': 'x' * CLI.MAX_REPORT_BYTES}
        with mock.patch.object(CLI, 'exercise', return_value=result):
            report = self.run_fixture()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['errors'][0]['type'], 'ReportBoundExceeded')
        self.assertLess((self.root / '.local/run/result.json').stat().st_size, 2048)

    def test_source_snapshot_contains_all_review_modules(self):
        snapshot = CLI.source_snapshot(Path(__file__).resolve().parents[1])
        names = {entry['path'] for entry in snapshot['files']}
        for name in ('__init__', 'contracts', 'store', 'authorization', 'service', 'rehearsal'):
            self.assertIn('src/model_release_assurance/production_review/' + name + '.py', names)
        self.assertIn('src/model_release_assurance/production_registration/workflow.py', names)
        self.assertIn('src/model_release_assurance/production_evidence/verifier.py', names)


if __name__ == '__main__':
    unittest.main()
