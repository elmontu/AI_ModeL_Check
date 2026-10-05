"""Capacity rehearsal admission, honest accounting, and actual recovery integration."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_capacity import contracts as c
from model_release_assurance.production_capacity import rehearsal as r

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location('mra_capacity_cli_tests', REPO / 'scripts/rehearse_capacity_recovery.py')
CLI = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(CLI)
LOCAL = 'local_public_fixture'


def _result():
    return {'status': 'passed', 'checks': [{'name': name, 'passed': True} for name in sorted(r.REQUIRED_CHECKS)],
        'summary': {'delivery': {}, 'backup': {}}, 'evidence': {'delivery': {}, 'backup': {}},
        'measurements': {name: {} for name in ('delivery', 'backup', 'io', 'jobs')},
        'workload_plan_sha256': c.digest(r.workload_plan()), 'target_status': 'not_agency_qualified', **c.FLAGS}


def _io_result():
    return {'status': 'passed', 'rows': [{'status': 'passed', 'requested_bytes': size,
        'bytes_written': size, 'bytes_scanned': size} for size in c.workload_plan()['io_target_bytes']],
        'summary': {'rows_requested': 3, 'rows_passed': 3, 'requested_bytes': 42991616},
        'target_status': 'not_agency_qualified', **c.FLAGS}


def _jobs_result():
    return {'status': 'passed', 'rows': [{'status': 'passed', 'requested_concurrency': count,
        'jobs_submitted': 4, 'succeeded': 4, 'failed': 0, 'unobserved': 0} for count in (1, 2, 4)],
        'summary': {'jobs_requested': 12, 'jobs_succeeded': 12, 'jobs_failed': 0, 'jobs_unobserved': 0, 'concurrency_rows': 3},
        'measurement': {'identities_unique_across_rows': True}, 'target_status': 'not_agency_qualified', **c.FLAGS}


class CapacityCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mra-capacity-cli-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True, timeout=20)
        (self.root / '.gitignore').write_text('.local/\n', encoding='utf-8')
        self.snapshot = {'files': [{'path': 'source.py', 'sha256': 'a' * 64, 'size_bytes': 1}], 'sha256': 'b' * 64}

    def run_cli(self, result=None, *, snapshots=None, error=None, name='run'):
        with mock.patch.object(CLI, 'source_snapshot', side_effect=snapshots,
                return_value=self.snapshot), mock.patch.object(CLI, 'exercise',
                return_value=_result() if result is None else result, side_effect=error):
            return CLI.run_rehearsal(root=self.root, output='.local/' + name, profile=LOCAL)

    def test_default_production_refuses_before_any_output_or_work(self):
        with mock.patch.object(CLI._BASELINE, 'prepare_output') as prepare, mock.patch.object(CLI, 'exercise') as exercise:
            with self.assertRaises(CLI.ProfileRefused):
                CLI.run_rehearsal(root=self.root, output='.local/denied')
        prepare.assert_not_called(); exercise.assert_not_called()
        self.assertFalse((self.root / '.local').exists())

    def test_main_production_default_is_nonzero_and_redacted(self):
        with mock.patch.object(CLI, 'ROOT', self.root), mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertEqual(CLI.main(['--output', '.local/denied']), 2)
        report = json.loads(out.getvalue())
        self.assertEqual(report['status'], 'profile_refused')
        self.assertFalse(report['approved_agency_scale'])
        self.assertFalse((self.root / '.local').exists())

    def test_exact_complete_local_result_has_twenty_checks(self):
        result = self.run_cli()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(result['checks']), 20)
        self.assertEqual({row['name'] for row in result['checks']}, CLI.REQUIRED_CHECKS)
        self.assertEqual(json.loads((self.root / '.local/run/result.json').read_bytes()), result)

    def test_output_outside_ignored_local_or_traversal_is_refused(self):
        for name in ('outside', '.local', '.local/../escape'):
            with self.subTest(name=name), self.assertRaises(CLI._BASELINE.BaselineError):
                CLI.run_rehearsal(root=self.root, output=name, profile=LOCAL)

    def test_existing_output_is_unchanged(self):
        target = self.root / '.local/retained'
        target.mkdir(parents=True); (target / 'keep').write_bytes(b'old')
        with self.assertRaises(CLI._BASELINE.BaselineError):
            CLI.run_rehearsal(root=self.root, output=target, profile=LOCAL)
        self.assertEqual((target / 'keep').read_bytes(), b'old')
        self.assertEqual([p.name for p in target.iterdir()], ['keep'])

    def test_missing_duplicate_or_false_milestone_cannot_pass(self):
        for index in range(3):
            result = _result()
            if index == 0: result['checks'].pop()
            elif index == 1: result['checks'][-1] = copy.deepcopy(result['checks'][0])
            else: result['checks'][0]['passed'] = False
            with self.subTest(index=index):
                self.assertEqual(self.run_cli(result, name=str(index))['status'], 'failed')

    def test_missing_stage_or_changed_plan_cannot_pass(self):
        for index, key in enumerate(('summary', 'evidence', 'measurements', 'workload_plan_sha256')):
            result = _result(); result.pop(key)
            with self.subTest(key=key):
                self.assertEqual(self.run_cli(result, name=str(index))['status'], 'failed')
        result = _result(); result['workload_plan_sha256'] = 'f' * 64
        self.assertEqual(self.run_cli(result, name='changed')['status'], 'failed')

    def test_production_flags_and_agency_target_cannot_be_claimed(self):
        for index, key in enumerate(('production_ready', 'approved_agency_scale', 'target_status')):
            result = _result(); result[key] = True if key != 'target_status' else 'agency_qualified'
            answer = self.run_cli(result, name=str(index))
            self.assertEqual(answer['status'], 'failed')
            self.assertFalse(answer['production_ready']); self.assertFalse(answer['approved_agency_scale'])
            self.assertEqual(answer['target_status'], 'not_agency_qualified')

    def test_source_drift_is_failure_after_completed_work(self):
        result = self.run_cli(snapshots=[self.snapshot, {**self.snapshot, 'sha256': 'c' * 64}])
        self.assertEqual(result['status'], 'failed')
        self.assertIn({'name': 'source_unchanged', 'passed': False}, result['checks'])

    def test_missing_source_prevents_work(self):
        with mock.patch.object(CLI, 'source_snapshot', side_effect=OSError('private source path')), \
                mock.patch.object(CLI, 'exercise') as action:
            result = CLI.run_rehearsal(root=self.root, output='.local/no-source', profile=LOCAL)
        action.assert_not_called(); self.assertEqual(result['status'], 'failed')
        self.assertNotIn('private source path', json.dumps(result))

    def test_error_messages_tokens_and_paths_are_not_persisted(self):
        secret = 'eyJsecret.private.token D:/private/input.csv'
        result = self.run_cli(error=RuntimeError(secret))
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn(secret, (self.root / '.local/run/result.json').read_text())
        self.assertEqual(result['errors'][0]['type'], 'LocalFixtureStageFailed')

    def test_oversized_or_nonfinite_result_is_bounded_failure(self):
        for index, value in enumerate(('z' * (CLI.MAX_REPORT_BYTES + 1), float('nan'))):
            result = _result(); result['summary']['delivery']['bad'] = value
            answer = self.run_cli(result, name=str(index))
            self.assertEqual(answer['status'], 'failed')
            self.assertEqual(answer['errors'][0]['type'], 'InvalidOrOversizedReport')
            self.assertLess((self.root / '.local' / str(index) / 'result.json').stat().st_size, 4096)

    def test_snapshot_contains_new_sources_locks_and_old_sources(self):
        snapshot = CLI.source_snapshot(REPO)
        names = {item['path'] for item in snapshot['files']}
        self.assertTrue(set(CLI.SOURCE_FILES) <= names)
        self.assertIn('src/model_release_assurance/production_delivery/gateway.py', names)
        self.assertIn('src/model_release_assurance/production_registry/store.py', names)

    def test_missing_mandatory_capacity_source_is_rejected(self):
        original = CLI._HELPERS._HELPERS._read_source
        def read(root, name):
            if name == 'src/model_release_assurance/production_capacity/backup.py':
                raise OSError('missing fixed source')
            return original(root, name)
        with mock.patch.object(CLI._HELPERS._HELPERS, '_read_source', side_effect=read):
            with self.assertRaises(OSError):
                CLI.source_snapshot(REPO)


class CapacityCompositionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mra-capacity-compose-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        computed = {'plan_frozen_before_measurement', 'fixed_public_io_complete', 'all_twelve_jobs_accounted',
                    'measurements_are_not_agency_targets', 'all_results_non_authorizing'}
        self.delivery = {'checks': [{'name': name, 'passed': True} for name in sorted(r.REQUIRED_CHECKS - computed)],
                         'summary': {}, 'evidence': {}, 'measurement': {}}
        self.backup = {'checks': [], 'summary': {}, 'evidence': {}, 'measurement': {}}

    def execute(self, *, jobs=None, io_result=None, delivery=None, name='run'):
        with mock.patch.object(r, '_delivery', return_value=self.delivery, side_effect=delivery), \
             mock.patch.object(r, '_backup', return_value=self.backup), \
             mock.patch.object(r.benchmarks, 'benchmark_public_io', return_value=_io_result() if io_result is None else io_result), \
             mock.patch.object(r.benchmarks, 'benchmark_fixture_jobs', return_value=_jobs_result() if jobs is None else jobs):
            return r.exercise(self.root / name, profile=LOCAL)

    def test_package_default_profile_refuses_before_creating_root(self):
        with mock.patch.object(r, 'DeliveryFixture') as fixture:
            with self.assertRaises(c.CapacityError): r.exercise(self.root / 'denied')
        fixture.assert_not_called(); self.assertFalse((self.root / 'denied').exists())

    def test_frozen_plan_written_before_first_stage(self):
        def delivery(path):
            self.assertEqual(json.loads((path.parent / 'workload-plan.json').read_bytes()), r.workload_plan())
            return self.delivery
        result = self.execute(delivery=delivery)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['workload_plan_sha256'], c.digest(r.workload_plan()))

    def test_plan_mutation_during_work_fails(self):
        def delivery(path):
            (path.parent / 'workload-plan.json').write_bytes(b'{}')
            return self.delivery
        result = self.execute(delivery=delivery)
        self.assertEqual(result['status'], 'failed')
        self.assertIn({'stage': 'plan', 'type': 'FrozenPlanChanged'}, result['errors'])

    def test_unobserved_or_missing_job_results_cannot_pass(self):
        for index in range(4):
            jobs = _jobs_result()
            if index == 0: jobs['rows'][0]['unobserved'] = 1
            elif index == 1: jobs['summary']['jobs_unobserved'] = 1
            elif index == 2: jobs['rows'].pop()
            else: jobs['measurement']['identities_unique_across_rows'] = False
            answer = self.execute(jobs=jobs, name=str(index))
            self.assertEqual(answer['status'], 'failed')
            self.assertEqual(answer['measurements']['jobs'], jobs)
            self.assertIn({'stage': 'jobs', 'type': 'LocalFixtureStageFailed'}, answer['errors'])

    def test_failed_or_short_io_does_not_pass_complete_measurement(self):
        for index in range(3):
            result = _io_result()
            if index == 0: result['rows'][0]['bytes_scanned'] -= 1
            elif index == 1: result['summary']['rows_passed'] = 2
            else: result['rows'][1]['status'] = 'failed'
            self.assertEqual(self.execute(io_result=result, name=str(index))['status'], 'failed')

    def test_failed_stage_retains_other_actual_measurements_without_secret(self):
        def failed(path): raise RuntimeError('PRIVATE_TOKEN')
        result = self.execute(delivery=failed)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['measurements']['jobs']['summary']['jobs_succeeded'], 12)
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(result))

    def test_new_output_only_preserves_prior_result(self):
        self.execute()
        before = (self.root / 'run/exercise-result.json').read_bytes()
        with self.assertRaises(c.CapacityError): self.execute()
        self.assertEqual((self.root / 'run/exercise-result.json').read_bytes(), before)


class ActualCapacityRecoveryTests(unittest.TestCase):
    def test_fresh_public_fit_real_jobs_and_historical_recovery(self):
        with tempfile.TemporaryDirectory(prefix='mra-capacity-real-') as temporary:
            root = Path(temporary) / 'exercise'
            result = r.exercise(root, profile=LOCAL)
            self.assertEqual(result['status'], 'passed', result['errors'])
            self.assertEqual({row['name'] for row in result['checks']}, r.REQUIRED_CHECKS)
            self.assertEqual(len(result['checks']), 19)
            delivery = result['summary']['delivery']
            self.assertEqual(delivery['fresh_native_runs'], 1)
            self.assertEqual(delivery['denied_writer_calls'], 0)
            self.assertEqual(delivery['nonvacuous_current_checks'], 4)
            self.assertEqual((delivery['partial_attempted_bytes'], delivery['partial_observed_bytes']), (128, 1))
            self.assertFalse(delivery['live_authority_rehydrated'])
            self.assertEqual(delivery['authority_clock'], 'synthetic_fixed_1000')
            de = result['evidence']['delivery']
            self.assertEqual(de['history_sha256_before'], de['history_sha256_reopened'])
            conservation = result['evidence']['backup']['conservation']
            for name in ('engineering_charge_units', 'receipt_count', 'outbox_acknowledged', 'committed_intents'):
                self.assertEqual(conservation[name], 3)
            self.assertEqual(conservation['pending_intents'], 0)
            for name in ('registry.sqlite', 'witness.sqlite', 'manifest.json'):
                self.assertEqual((root / 'backup/complete-backup' / name).read_bytes(),
                                 (root / 'backup/restored-historical' / name).read_bytes())
            jobs = result['measurements']['jobs']
            self.assertEqual(jobs['summary'], {'jobs_requested': 12, 'jobs_succeeded': 12,
                'jobs_failed': 0, 'jobs_unobserved': 0, 'concurrency_rows': 3})
            self.assertTrue(jobs['measurement']['identities_unique_across_rows'])
            self.assertEqual(result['measurements']['io']['summary']['requested_bytes'], 42991616)
            self.assertTrue(all(result[key] is value for key, value in c.FLAGS.items()))
            self.assertEqual(json.loads((root / 'exercise-result.json').read_bytes()), result)


if __name__ == '__main__':
    unittest.main()
