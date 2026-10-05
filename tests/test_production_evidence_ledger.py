"""Durable evidence challenges, with real independent-process replay races."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
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
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_evidence import ledger as ledgers
from model_release_assurance.production_evidence.contracts import EvidenceError, MAX_INTEGER, digest


# Fixed test-only program. No worker- or request-supplied command is executed.
_CHILD = r"""import sys, json, time, os
from pathlib import Path
configuration = json.loads(sys.argv[1])
sys.path[:0] = configuration['paths']
from model_release_assurance.production_evidence.ledger import ReplayLedger, LedgerUnavailable
from model_release_assurance.production_evidence.contracts import EvidenceError
ledger = ReplayLedger.open(configuration['root'], configuration['ledger_id'])
Path(configuration['ready']).write_text('ready', encoding='ascii')
deadline = time.monotonic() + 10
while not Path(configuration['gate']).exists():
    if time.monotonic() >= deadline:
        raise SystemExit(24)
    time.sleep(.01)
calls = 0
def guard():
    global calls
    calls += 1
    if configuration['operation'] == 'crash_before_commit' and calls == 2:
        os._exit(23)
    return configuration['now']
try:
    operation = configuration['operation']
    if operation == 'issue':
        result = ledger.issue(**configuration['arguments'], guard=guard)
    else:
        result = ledger.consume(**configuration['arguments'], guard=guard)
    if operation == 'crash_after_commit':
        os._exit(23)
    print(json.dumps({'ok': True, 'result': result}), flush=True)
except (EvidenceError, LedgerUnavailable) as error:
    print(json.dumps({'ok': False, 'error': type(error).__name__}), flush=True)
"""


class ProductionEvidenceLedgerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-evidence-ledger-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / "ledger # percent%"
        self.ledger = ledgers.ReplayLedger.create(self.root)
        self.database = self.root / "replay.sqlite"
        self.now = 100
        self.context = digest({"context": "public-fixture"})
        self.execution = digest({"execution": "attempt-a"})
        self.envelope = digest({"envelope": "signed-fixture"})

    def guard(self):
        return self.now

    def issue(self, **changes):
        arguments = dict(context_sha256=self.context, execution_sha256=self.execution, guard=self.guard)
        arguments.update(changes)
        return self.ledger.issue(**arguments)

    def consume(self, challenge, **changes):
        arguments = dict(challenge=challenge, envelope_sha256=self.envelope, guard=self.guard)
        arguments.update(changes)
        return self.ledger.consume(**arguments)

    def query(self, sql, arguments=()):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(sql, arguments).fetchall()

    def change(self, sql, arguments=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(sql, arguments)
            connection.commit()

    def processes(self, operations):
        gate = self.parent / ("gate-" + uuid.uuid4().hex)
        paths = list(dict.fromkeys([str(Path(__file__).resolve().parents[1] / "src"),
                                  sysconfig.get_path("purelib"), sysconfig.get_path("platlib")]))
        interpreter = getattr(sys, "_base_executable", sys.executable)
        processes, ready_files = [], []
        try:
            for operation, arguments in operations:
                ready = self.parent / ("ready-" + uuid.uuid4().hex)
                configuration = dict(paths=paths, root=str(self.root), ledger_id=self.ledger.ledger_id,
                    ready=str(ready), gate=str(gate), now=self.now, operation=operation, arguments=arguments)
                process = subprocess.Popen([interpreter, "-I", "-S", "-B", "-c", _CHILD, json.dumps(configuration)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                processes.append(process)
                ready_files.append(ready)
            deadline = time.monotonic() + 15
            while not all(path.exists() for path in ready_files):
                if any(process.poll() is not None for process in processes) or time.monotonic() >= deadline:
                    outputs = [(process.poll(), process.communicate(timeout=2) if process.poll() is not None else "running")
                               for process in processes]
                    self.fail("Independent ledger processes did not reach barrier: " + repr(outputs))
                time.sleep(.01)
            gate.write_text("go", encoding="ascii")
            outcomes = []
            for process, (operation, _) in zip(processes, operations):
                output, error = process.communicate(timeout=15)
                if operation.startswith("crash_"):
                    self.assertEqual(process.returncode, 23, error)
                    outcomes.append({"crashed": True})
                else:
                    self.assertEqual(process.returncode, 0, error)
                    self.assertEqual(error, "")
                    outcomes.append(json.loads(output))
            return outcomes
        finally:
            # Fixed children create no descendants; cleanup uses owned handles.
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_exact_challenge_receipt_and_restart(self):
        challenge = self.issue(ttl_seconds=20)
        self.assertEqual(set(challenge), {"schema", "ledger_id", "nonce", "context_sha256",
                                          "execution_sha256", "issued_at", "expires_at"})
        self.assertRegex(challenge["nonce"], r"^[a-f0-9]{64}$")
        self.assertRegex(challenge["ledger_id"], r"^[a-f0-9]{32}$")
        self.assertEqual(challenge["issued_at"], 100)
        self.assertEqual(challenge["expires_at"], 120)
        restored = ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
        ticks = iter([101, 102])
        receipt = restored.consume(challenge, self.envelope, guard=lambda: next(ticks))
        self.assertEqual(receipt, {"schema": "mra-evidence-consumption/v1", "ledger_id": self.ledger.ledger_id,
            "nonce": challenge["nonce"], "context_sha256": self.context, "execution_sha256": self.execution,
            "envelope_sha256": self.envelope, "consumed_at": 102})
        self.assertEqual(self.query("SELECT envelope_sha256,consumed_at FROM challenges"), [(self.envelope, 102)])
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='last_clock'"), [("102",)])
        self.assertEqual(ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id).ledger_id, self.ledger.ledger_id)

    def test_duplicate_acceptance_even_identical_bytes_rejected_after_restart(self):
        challenge = self.issue()
        self.consume(challenge)
        for envelope in (self.envelope, "b" * 64):
            with self.subTest(envelope=envelope):
                restored = ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
                with self.assertRaises(ledgers.LedgerConflict):
                    restored.consume(challenge, envelope, guard=self.guard)
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(1,)])

    def test_execution_never_gets_fresh_nonce_even_with_new_context(self):
        challenge = self.issue(ttl_seconds=1)
        for now, consumed in ((100, False), (100, True), (101, True)):
            self.now = now
            if consumed and now == 100:
                self.consume(challenge)
            with self.subTest(now=now, consumed=consumed):
                with self.assertRaises(ledgers.LedgerConflict):
                    self.issue(context_sha256="b" * 64)
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(1,)])

    def test_expired_unconsumed_execution_stays_reserved(self):
        challenge = self.issue(ttl_seconds=1)
        self.now = 101
        with self.assertRaises(ledgers.LedgerConflict):
            self.consume(challenge)
        with self.assertRaises(ledgers.LedgerConflict):
            self.issue()

    def test_all_registered_fields_are_bound(self):
        challenge = self.issue(ttl_seconds=10)
        replacements = {"ledger_id": "b" * 32, "nonce": "b" * 64, "context_sha256": "b" * 64,
                        "execution_sha256": "b" * 64, "issued_at": 99, "expires_at": 111}
        for field, value in replacements.items():
            with self.subTest(field=field):
                changed = {**challenge, field: value}
                with self.assertRaises(ledgers.LedgerConflict):
                    self.consume(changed)
        self.consume(challenge)

    def test_invalid_shapes_digest_types_and_times_rejected(self):
        for value in (True, 0, "A" * 64, "a" * 63, {}, None):
            with self.subTest(value=value):
                with self.assertRaises(EvidenceError):
                    self.issue(context_sha256=value)
                with self.assertRaises(EvidenceError):
                    self.issue(execution_sha256=value)
        for ttl in (True, 0, -1, 301, 1.0, "1"):
            with self.subTest(ttl=ttl), self.assertRaises(EvidenceError):
                self.issue(ttl_seconds=ttl)
        challenge = self.issue()
        for changed in ({**challenge, "extra": False}, {**challenge, "issued_at": True},
                        {**challenge, "issued_at": 100.0}):
            with self.assertRaises(EvidenceError):
                self.consume(changed)
        with self.assertRaises(EvidenceError):
            self.consume(challenge, envelope_sha256="invalid")
        self.consume(challenge)

    def test_guard_is_required_and_malformed_clock_rejected(self):
        for value in (True, -1, 100.0, "100", MAX_INTEGER + 1):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                self.issue(guard=lambda: value)
        with self.assertRaises(EvidenceError):
            self.issue(guard=None)
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(0,)])

    def test_guard_called_twice_and_issue_expiry_rolls_back(self):
        ticks = iter([100, 101])
        with self.assertRaises(ledgers.LedgerConflict):
            self.issue(ttl_seconds=1, guard=lambda: next(ticks))
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(0,)])
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='last_clock'"), [("0",)])
        challenge = self.issue(ttl_seconds=1)
        self.assertEqual(challenge["issued_at"], 100)

    def test_expiry_during_final_consume_guard_never_commits(self):
        challenge = self.issue(ttl_seconds=10)
        ticks = iter([109, 110])
        with self.assertRaises(ledgers.LedgerConflict):
            self.consume(challenge, guard=lambda: next(ticks))
        self.assertEqual(self.query("SELECT envelope_sha256,consumed_at FROM challenges"), [(None, None)])
        self.now = 109
        self.consume(challenge)

    def test_trust_failure_rolls_back_without_translating_permission_error(self):
        challenge = self.issue()
        calls = []
        def guard():
            calls.append(1)
            if len(calls) == 2:
                raise PermissionError("fixture revocation")
            return 101
        with self.assertRaises(PermissionError):
            self.consume(challenge, guard=guard)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.query("SELECT envelope_sha256 FROM challenges"), [(None,)])
        self.consume(challenge)

    def test_committed_clock_floor_survives_restart(self):
        challenge = self.issue()
        self.now = 101
        self.consume(challenge)
        restored = ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
        with self.assertRaises(ledgers.LedgerUnavailable):
            restored.issue(self.context, "b" * 64, guard=lambda: 100)
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue(execution_sha256="b" * 64, guard=iter([102, 101]).__next__)
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='last_clock'"), [("101",)])

    def test_owned_challenge_not_changed_during_guard(self):
        challenge = self.issue()
        expected = copy.deepcopy(challenge)
        def guard():
            challenge["context_sha256"] = "b" * 64
            return 100
        receipt = self.consume(challenge, guard=guard)
        self.assertEqual(receipt["context_sha256"], expected["context_sha256"])

    def test_nonce_collision_does_not_replace_previous_execution(self):
        challenge = self.issue()
        with mock.patch.object(ledgers.secrets, "token_hex", return_value=challenge["nonce"]):
            with self.assertRaises(ledgers.LedgerConflict):
                self.issue(execution_sha256="b" * 64)
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(1,)])

    def test_independent_processes_accept_only_once(self):
        challenge = self.issue()
        arguments = {"challenge": challenge, "envelope_sha256": self.envelope}
        outcomes = self.processes([("consume", arguments), ("consume", arguments)])
        self.assertEqual(sorted(result["ok"] for result in outcomes), [False, True])
        self.assertEqual([result["error"] for result in outcomes if not result["ok"]], ["LedgerConflict"])
        self.assertEqual(self.query("SELECT envelope_sha256 FROM challenges"), [(self.envelope,)])

    def test_independent_processes_reserve_execution_only_once(self):
        arguments = {"context_sha256": self.context, "execution_sha256": self.execution}
        outcomes = self.processes([("issue", arguments), ("issue", arguments)])
        self.assertEqual(sorted(result["ok"] for result in outcomes), [False, True])
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(1,)])

    def test_crash_after_commit_does_not_allow_retry(self):
        challenge = self.issue()
        self.processes([("crash_after_commit", {"challenge": challenge, "envelope_sha256": self.envelope})])
        restored = ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
        with self.assertRaises(ledgers.LedgerConflict):
            restored.consume(challenge, self.envelope, guard=self.guard)

    def test_crash_before_commit_retains_outstanding_challenge(self):
        challenge = self.issue()
        self.processes([("crash_before_commit", {"challenge": challenge, "envelope_sha256": self.envelope})])
        restored = ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
        self.assertEqual(restored.consume(challenge, self.envelope, guard=self.guard)["consumed_at"], 100)

    def test_clock_is_sampled_after_sqlite_write_lock_wait(self):
        lock = sqlite3.connect(self.database, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        started, guarded = Event(), Event()
        def operation():
            started.set()
            def guard():
                guarded.set()
                return self.now
            return self.issue(guard=guard)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(operation)
                self.assertTrue(started.wait(1))
                time.sleep(.1)
                self.assertFalse(guarded.is_set())
                self.now = 150
                lock.rollback()
                challenge = future.result(timeout=3)
                self.assertEqual(challenge["issued_at"], 150)
        finally:
            lock.close()

    def test_expiry_while_waiting_for_write_lock_is_rejected(self):
        challenge = self.issue(ttl_seconds=10)
        lock = sqlite3.connect(self.database, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        started = Event()
        def operation():
            started.set()
            return self.consume(challenge)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(operation)
                self.assertTrue(started.wait(1))
                time.sleep(.1)
                self.now = 110
                lock.rollback()
                with self.assertRaises(ledgers.LedgerConflict):
                    future.result(timeout=3)
        finally:
            lock.close()
        self.assertEqual(self.query("SELECT envelope_sha256 FROM challenges"), [(None,)])

    def test_busy_database_is_bounded_and_never_calls_guard(self):
        lock = sqlite3.connect(self.database, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        guard = mock.Mock(return_value=100)
        started = time.monotonic()
        try:
            with self.assertRaises(ledgers.LedgerUnavailable):
                self.issue(guard=guard)
        finally:
            lock.rollback()
            lock.close()
        guard.assert_not_called()
        self.assertLess(time.monotonic() - started, 4)

    def test_missing_database_and_root_are_not_recreated(self):
        self.database.unlink()
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
        self.assertFalse(self.database.exists())
        missing = self.parent / "missing"
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.open(missing, self.ledger.ledger_id)
        self.assertFalse(missing.exists())

    def test_create_refuses_existing_and_open_requires_exact_identity(self):
        original = self.database.read_bytes()
        self.assertEqual(self.ledger.root, self.root)
        with self.assertRaises(AttributeError):
            self.ledger.root = self.parent
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.create(self.root)
        for identity in ("b" * 32, True, "not-an-id"):
            with self.assertRaises(ledgers.LedgerUnavailable):
                ledgers.ReplayLedger.open(self.root, identity)
        self.assertEqual(self.database.read_bytes(), original)
        with self.assertRaises(AttributeError):
            self.ledger.ledger_id = "b" * 32

    def test_database_substitution_even_identical_bytes_is_rejected(self):
        replacement = self.root / "replacement.sqlite"
        replacement.write_bytes(self.database.read_bytes())
        os.replace(replacement, self.database)
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()

    def test_root_substitution_is_rejected(self):
        moved = self.parent / "old-ledger"
        self.root.rename(moved)
        self.root.mkdir()
        shutil.copyfile(moved / "replay.sqlite", self.database)
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()

    def test_filesystem_identity_is_rechecked_after_final_guard(self):
        challenge = self.issue()
        alias = self.parent / "late-alias.sqlite"
        calls = []
        def guard():
            calls.append(True)
            if len(calls) == 2:
                os.link(self.database, alias)
            return 100
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.consume(challenge, guard=guard)
        self.assertEqual(self.query("SELECT envelope_sha256 FROM challenges"), [(None,)])
        alias.unlink()
        self.consume(challenge)

    def test_hardlinks_are_rejected_on_database_and_journal(self):
        alias = self.parent / "alias.sqlite"
        os.link(self.database, alias)
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()
        alias.unlink()
        journal = self.root / "replay.sqlite-journal"
        journal.write_bytes(b"")
        os.link(journal, alias)
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()

    def test_reparse_flags_on_directory_or_database_rejected(self):
        original = Path.lstat
        for unsafe in (self.root, self.database):
            def patched(path):
                info = original(path)
                if path == unsafe:
                    return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400,
                        st_dev=info.st_dev, st_ino=info.st_ino, st_nlink=info.st_nlink, st_size=info.st_size)
                return info
            with self.subTest(path=unsafe.name), mock.patch.object(Path, "lstat", patched):
                with self.assertRaises(ledgers.LedgerUnavailable):
                    self.issue()

    def test_wal_or_shm_sidecars_are_always_rejected(self):
        for suffix in ("-wal", "-shm"):
            path = self.root / ("replay.sqlite" + suffix)
            path.write_bytes(b"")
            with self.subTest(suffix=suffix), self.assertRaises(ledgers.LedgerUnavailable):
                self.issue()
            path.unlink()

    def test_schema_change_is_rejected_on_existing_instance(self):
        self.change("CREATE TABLE extra (value TEXT) STRICT")
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)

    def test_trigger_change_is_rejected_before_it_can_run(self):
        self.change("CREATE TRIGGER extra AFTER INSERT ON challenges BEGIN DELETE FROM challenges; END")
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(0,)])

    def test_metadata_change_is_rejected_on_existing_instance(self):
        self.change("UPDATE meta SET value='00' WHERE key='last_clock'")
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()
        self.change("UPDATE meta SET value='0' WHERE key='last_clock'")
        self.change("UPDATE meta SET value=? WHERE key='ledger_id'", ("b" * 32,))
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()

    def test_malformed_persistent_challenge_or_consumption_rejected(self):
        challenge = self.issue()
        self.change("UPDATE challenges SET expires_at=issued_at")
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue(execution_sha256="b" * 64)
        self.change("UPDATE challenges SET expires_at=?", (challenge["expires_at"],))
        self.change("UPDATE challenges SET envelope_sha256=?,consumed_at=999", (self.envelope,))
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue(execution_sha256="b" * 64)

    def test_corrupt_database_rejected_without_reset(self):
        self.database.write_bytes(b"not a sqlite database")
        with self.assertRaises(ledgers.LedgerUnavailable):
            self.issue()
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.open(self.root, self.ledger.ledger_id)
        self.assertEqual(self.database.read_bytes(), b"not a sqlite database")

    def test_capacity_never_prunes_consumed_or_expired_records(self):
        with mock.patch.object(ledgers, "MAX_CHALLENGES", 2):
            challenge = self.issue(ttl_seconds=1)
            self.consume(challenge)
            self.issue(execution_sha256="b" * 64, ttl_seconds=1)
            self.now = 101
            with self.assertRaises(ledgers.LedgerConflict):
                self.issue(execution_sha256="c" * 64)
        self.assertEqual(self.query("SELECT count(*) FROM challenges"), [(2,)])
        with mock.patch.object(ledgers, "MAX_CHALLENGES", 1):
            with self.assertRaises(ledgers.LedgerUnavailable):
                self.issue(execution_sha256="c" * 64)

    def test_database_size_bound_checked_before_opening(self):
        with mock.patch.object(ledgers, "MAX_DATABASE_BYTES", 1):
            with self.assertRaises(ledgers.LedgerUnavailable):
                self.issue()

    def test_unsafe_root_spelling_and_nondirectory_parent_rejected(self):
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.create(self.root / ".." / "other")
        with self.assertRaises(ledgers.LedgerUnavailable):
            ledgers.ReplayLedger.create(self.database / "other")


if __name__ == "__main__":
    unittest.main()
