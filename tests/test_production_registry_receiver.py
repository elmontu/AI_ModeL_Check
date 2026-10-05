"""Durable local event effects and receipts; never an external-witness test."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_registry import receiver as receivers
from model_release_assurance.production_registry.contracts import (FLAGS, FIXTURE_SHA256,
    POLICY, account_id, canonical_bytes, digest, validate_outbox_event)

_CHILD = r'''import sys,json,time,os
from pathlib import Path
config=json.loads(sys.argv[1])
sys.path[:0]=config['paths']
from model_release_assurance.production_registry.receiver import FixtureEventReceiver
receiver=FixtureEventReceiver.open(config['root'],config['receiver_id'])
Path(config['ready']).write_text('ready')
deadline=time.monotonic()+10
while not Path(config['gate']).exists():
    if time.monotonic()>=deadline: raise SystemExit(24)
    time.sleep(.01)
calls=0
def guard():
    global calls
    calls+=1
    if config['mode']=='before_commit' and calls==2: os._exit(23)
    return 100
result=receiver.receive(config['event'],guard=guard)
if config['mode']=='after_commit': os._exit(23)
print(json.dumps(result),flush=True)
'''


def event(**changes):
    value = {'schema': 'mra-fixture-registry-outbox/v1', 'environment': 'public_fixture',
        'store_id': 'a' * 32, 'event_id': 'b' * 32, 'account_id': account_id('agency', 'project'),
        'agency_id': 'agency', 'project_id': 'project', 'case_id': 'case-a', 'request_id': 'c' * 32,
        'receipt_sha256': 'd' * 64, 'object_reference_sha256': 'e' * 64,
        'artifact_sha256': FIXTURE_SHA256, 'source_sha256': FIXTURE_SHA256,
        'policy_sha256': digest(POLICY), **FLAGS}
    value.update(changes)
    return validate_outbox_event(value)


class RegistryReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mra-registry-receiver-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'receiver # percent%'
        self.receiver = receivers.FixtureEventReceiver.create(self.root)
        self.database = self.root / 'receiver.sqlite'
        self.now = 100

    def guard(self):
        return self.now

    def receive(self, value=None, **options):
        return self.receiver.receive(event() if value is None else value, guard=options.get('guard', self.guard))

    def snapshot(self):
        return self.receiver.snapshot(guard=self.guard)

    def change(self, sql, args=()):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute(sql, args)
            db.commit()

    def rows(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT sequence,event_json,receipt_json FROM events').fetchall()

    def processes(self, modes):
        gate = self.parent / ('gate-' + uuid.uuid4().hex)
        paths = list(dict.fromkeys([str(Path(__file__).resolve().parents[1] / 'src'),
                                  sysconfig.get_path('purelib'), sysconfig.get_path('platlib')]))
        children, ready = [], []
        try:
            for mode in modes:
                marker = self.parent / ('ready-' + uuid.uuid4().hex)
                config = {'paths': paths, 'root': str(self.root), 'receiver_id': self.receiver.receiver_id,
                          'gate': str(gate), 'ready': str(marker), 'mode': mode, 'event': event()}
                child = subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-I', '-S', '-B',
                    '-c', _CHILD, json.dumps(config)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8', close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                children.append(child)
                ready.append(marker)
            deadline = time.monotonic() + 15
            while not all(path.exists() for path in ready):
                if any(child.poll() is not None for child in children) or time.monotonic() >= deadline:
                    self.fail('Receiver fixture process failed to reach bounded barrier')
                time.sleep(.01)
            gate.write_text('go')
            results = []
            for child, mode in zip(children, modes):
                output, error = child.communicate(timeout=15)
                self.assertEqual(error, '')
                self.assertEqual(child.returncode, 0 if mode == 'receive' else 23)
                results.append(json.loads(output) if output else None)
            return results
        finally:
            # These fixed test programs spawn no descendants. Own every handle.
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)

    def test_exact_event_applies_one_durable_effect_and_nonwitness_receipt(self):
        receipt = self.receive()
        self.assertEqual(receipt, {'schema': 'mra-fixture-registry-receiver/v1',
            'receiver_id': self.receiver.receiver_id, 'store_id': 'a' * 32, 'event_id': 'b' * 32,
            'event_sha256': digest(event()), 'applied_sequence': 1, 'applied_at': 100,
            'independent_witness': False, **FLAGS})
        snapshot = self.snapshot()
        self.assertEqual(snapshot['applied_events'], 1)
        self.assertEqual(snapshot['receipts'], [receipt])
        self.assertFalse(snapshot['independent_witness'])
        self.assertEqual(len(self.rows()), 1)
        for key, value in FLAGS.items():
            self.assertIs(snapshot[key], value)

    def test_reopen_and_exact_duplicate_return_original_receipt_without_second_effect(self):
        receipt = self.receive()
        self.receiver = receivers.FixtureEventReceiver.open(self.root, self.receiver.receiver_id)
        self.now = 110
        self.assertEqual(self.receive(), receipt)
        self.assertEqual(self.snapshot()['applied_events'], 1)
        self.assertEqual(self.snapshot()['receipts'], [receipt])

    def test_conflicting_bytes_for_same_event_id_are_rejected_and_original_survives(self):
        receipt = self.receive()
        for changes in ({'receipt_sha256': 'f' * 64}, {'case_id': 'renamed-case'}, {'request_id': 'f' * 32}):
            with self.subTest(changes=changes), self.assertRaises(receivers.ReceiverConflict):
                self.receive(event(**changes))
        self.assertEqual(self.snapshot()['receipts'], [receipt])

    def test_registry_id_is_part_of_event_identity(self):
        first = self.receive()
        second = self.receive(event(store_id='f' * 32))
        self.assertEqual(second['applied_sequence'], 2)
        self.assertEqual(self.snapshot()['receipts'], [first, second])

    def test_independent_processes_deduplicate_to_one_effect_and_one_receipt(self):
        left, right = self.processes(['receive', 'receive'])
        self.assertEqual(left, right)
        self.assertEqual(self.snapshot()['applied_events'], 1)
        self.assertEqual(self.snapshot()['receipts'], [left])

    def test_crash_before_commit_rolls_back_effect_and_receipt_together(self):
        self.processes(['before_commit'])
        self.receiver = receivers.FixtureEventReceiver.open(self.root, self.receiver.receiver_id)
        self.assertEqual(self.snapshot()['applied_events'], 0)
        self.assertEqual(self.receive()['applied_sequence'], 1)

    def test_crash_after_commit_redelivery_returns_original_durable_receipt(self):
        self.processes(['after_commit'])
        self.receiver = receivers.FixtureEventReceiver.open(self.root, self.receiver.receiver_id)
        receipt = self.snapshot()['receipts'][0]
        self.now = 101
        self.assertEqual(self.receive(), receipt)
        self.assertEqual(self.snapshot()['applied_events'], 1)

    def test_guard_denial_at_final_commit_rolls_back_everything(self):
        calls = []
        def guard():
            calls.append(True)
            if len(calls) == 2:
                raise PermissionError('authority revoked')
            return 100
        with self.assertRaises(PermissionError):
            self.receive(guard=guard)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.snapshot()['applied_events'], 0)
        self.assertEqual(self.rows(), [])

    def test_guard_final_time_is_retained_after_state_revalidation(self):
        clock = iter((100, 101))
        result = self.receive(guard=lambda: next(clock))
        self.assertEqual(result['applied_at'], 101)
        self.now = 101
        self.assertEqual(self.snapshot()['receipts'], [result])
        original = self.receiver._validate
        count = []
        def validation(db):
            value = original(db)
            count.append(True)
            if len(count) == 2:
                self.now = 104
            return value
        with mock.patch.object(self.receiver, '_validate', validation):
            result = self.receive(event(event_id='f' * 32))
        self.assertEqual(result['applied_at'], 104)

    def test_caller_mutation_during_guard_does_not_change_bound_event(self):
        supplied = event()
        expected = digest(supplied)
        def guard():
            supplied['receipt_sha256'] = 'f' * 64
            return 100
        receipt = self.receive(supplied, guard=guard)
        self.assertEqual(receipt['event_sha256'], expected)
        self.assertEqual(self.receive()['event_sha256'], expected)
        receipt['applied_at'] = 999
        self.assertEqual(self.snapshot()['receipts'][0]['applied_at'], 100)

    def test_persisted_clock_rollback_and_invalid_guard_never_commit(self):
        self.receive()
        self.receiver = receivers.FixtureEventReceiver.open(self.root, self.receiver.receiver_id)
        for value in (99, True, 1.0, -1, None):
            with self.subTest(value=value), self.assertRaises(receivers.ReceiverUnavailable):
                self.receiver.snapshot(guard=lambda: value)
        with self.assertRaises(receivers.ReceiverError):
            self.receiver.snapshot(guard=None)
        self.assertEqual(self.snapshot()['applied_events'], 1)

    def test_invalid_events_fail_before_guard_and_cannot_claim_clearance(self):
        cases = []
        for name, value in (('source_sha256', '0' * 64), ('artifact_sha256', '0' * 64),
                            ('production_authorized', True), ('fixture_only', 1),
                            ('account_id', '0' * 64), ('environment', 'production'), ('private_bytes', 'secret')):
            candidate = event()
            candidate[name] = value
            cases.append(candidate)
        cases.extend((None, b'{}', {'event_id': 'b' * 32}))
        guard = mock.Mock(return_value=100)
        for value in cases:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(receivers.ReceiverError):
                self.receive(value, guard=guard) if value is not None else self.receiver.receive(None, guard=guard)
        guard.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_capacity_retains_tombstones_and_still_accepts_exact_duplicate(self):
        with mock.patch.object(receivers, 'MAX_EVENTS', 1):
            receipt = self.receive()
            self.assertEqual(self.receive(), receipt)
            with self.assertRaises(receivers.ReceiverConflict):
                self.receive(event(event_id='f' * 32))
            self.assertEqual(self.snapshot()['applied_events'], 1)

    def test_existing_output_wrong_identity_and_missing_database_never_reset(self):
        with self.assertRaises(receivers.ReceiverUnavailable):
            receivers.FixtureEventReceiver.create(self.root)
        with self.assertRaises(receivers.ReceiverUnavailable):
            receivers.FixtureEventReceiver.open(self.root, 'f' * 32)
        self.database.unlink()
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()
        with self.assertRaises(receivers.ReceiverUnavailable):
            receivers.FixtureEventReceiver.open(self.root, self.receiver.receiver_id)
        self.assertFalse(self.database.exists())

    def test_same_bytes_database_replacement_is_rejected_on_existing_instance(self):
        replacement = self.root / 'replacement.sqlite'
        shutil.copyfile(self.database, replacement)
        self.database.unlink()
        replacement.rename(self.database)
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()

    def test_hardlinks_and_reparse_flags_are_rejected(self):
        link = self.parent / 'linked-database'
        os.link(self.database, link)
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()
        link.unlink()
        original = Path.lstat
        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == self.root:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return info
        with mock.patch.object(Path, 'lstat', reparse), self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()

    def test_sidecars_traversal_and_oversized_database_fail_closed(self):
        sidecar = self.root / 'receiver.sqlite-wal'
        sidecar.write_bytes(b'')
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()
        sidecar.unlink()
        with mock.patch.object(receivers, 'MAX_DATABASE_BYTES', 1), self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()
        with self.assertRaises(receivers.ReceiverUnavailable):
            receivers.FixtureEventReceiver.create(self.root / '..' / 'outside')
        self.assertFalse((self.parent / 'outside').exists())

    def test_deleted_event_or_tail_is_detected_each_operation(self):
        self.receive()
        self.change('DELETE FROM events')
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()

    def test_modified_event_receipt_or_chain_is_rejected(self):
        self.receive()
        row = self.rows()[0]
        mutations = [('event_json', canonical_bytes(event(receipt_sha256='f' * 64)).decode()),
                     ('receipt_json', row[2].replace('"applied_sequence":1', '"applied_sequence":true')),
                     ('chain_sha256', '0' * 64)]
        with closing(sqlite3.connect(self.database)) as db:
            chain = db.execute('SELECT chain_sha256 FROM events').fetchone()[0]
        for field, replacement in mutations:
            original = row[1] if field == 'event_json' else row[2] if field == 'receipt_json' else chain
            self.change('UPDATE events SET ' + field + '=?', (replacement,))
            with self.subTest(field=field), self.assertRaises(receivers.ReceiverUnavailable):
                self.snapshot()
            self.change('UPDATE events SET ' + field + '=?', (original,))
        self.assertEqual(self.snapshot()['applied_events'], 1)

    def test_unknown_schema_trigger_and_metadata_are_rejected_before_effect(self):
        self.change('CREATE TRIGGER injected AFTER INSERT ON events BEGIN DELETE FROM events; END')
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.receive()
        self.change('DROP TRIGGER injected')
        self.change("UPDATE meta SET value='mra-fixture-event-receiver/v999' WHERE key='schema'")
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.receive()
        self.assertEqual(self.rows(), [])

    def test_corrupt_database_fails_without_repair(self):
        self.database.write_bytes(b'not a database')
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.snapshot()
        self.assertEqual(self.database.read_bytes(), b'not a database')

    def test_late_filesystem_substitution_during_final_guard_does_not_commit(self):
        link = self.parent / 'late-link'
        count = []
        def guard():
            count.append(True)
            if len(count) == 2:
                os.link(self.database, link)
            return 100
        with self.assertRaises(receivers.ReceiverUnavailable):
            self.receive(guard=guard)
        link.unlink()
        self.assertEqual(self.snapshot()['applied_events'], 0)


if __name__ == '__main__':
    unittest.main()
