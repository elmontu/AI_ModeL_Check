"""Durable public-fixture jobs, including independent-process contention."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
import os
from pathlib import Path
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

from model_release_assurance.production_jobs import store as jobs
from model_release_assurance.production_jobs.contracts import JobConflict, JobUnavailable, sha256
from model_release_assurance.production_jobs.executor import ADAPTER_ID, worker_sha256
from model_release_assurance.production_storage.backend import FixtureObjectStore


# Fixed test code, never a request-supplied command. Independent interpreters
# exercise SQLite arbitration without sharing Python locks or store instances.
_CHILD = r"""import sys, json, time, os
from pathlib import Path
configuration = json.loads(sys.argv[1])
sys.path[:0] = configuration['paths']
from model_release_assurance.production_jobs.store import JobStore
from model_release_assurance.production_jobs.contracts import JobError
store = JobStore.open(configuration['root'], configuration['store_id'])
Path(configuration['ready']).write_text('ready', encoding='ascii')
deadline = time.monotonic() + 10
while not Path(configuration['gate']).exists():
    if time.monotonic() >= deadline:
        raise SystemExit(24)
    time.sleep(.01)
guard = lambda: configuration['now']
common = dict(broker_id=configuration['broker'], guard=guard)
try:
    operation = configuration['operation']
    arguments = configuration['arguments']
    if operation == 'claim':
        result = store.claim(**arguments, **common)
    elif operation == 'consume':
        result = store.consume_input(**arguments, **common)
    elif operation == 'cancel':
        result = store.cancel(**arguments, **common)
    elif operation == 'complete':
        result = store.complete(**arguments, **common)
    elif operation == 'crash_read':
        def crash():
            os._exit(23)
        result = store.with_current_lease(**arguments, operation=crash, **common)
    else:
        raise AssertionError('Unknown fixed test operation')
    print(json.dumps({'ok': True, 'result': result}), flush=True)
except JobError as error:
    print(json.dumps({'ok': False, 'error': type(error).__name__}), flush=True)
"""


class ProductionJobsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-job-store-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        objects = FixtureObjectStore(self.parent / "objects")
        self.reference = objects.register_fixture(case_id="case-a", agency_id="agency-a", project_id="project-a",
            fixture_id="public-counts-v1", created_at=100, retention_until=1000)
        self.content = objects.read(self.reference)
        self.now = 100
        self.store = jobs.JobStore.create(self.parent / "jobs # percent%")
        self.broker = uuid.uuid4().hex
        self.store.activate_broker(self.broker, self.guard)
        self.holder = "a" * 64
        self.descriptor = {"schema": "mra-fixture-job/v1", "environment": "public_fixture",
            "agency_id": "agency-a", "project_id": "project-a", "case_id": "case-a",
            "object_reference": self.reference.to_dict(), "adapter_id": ADAPTER_ID,
            "worker_sha256": worker_sha256(), "max_attempts": 3, "lease_seconds": 10, "timeout_seconds": 5}

    def guard(self):
        return self.now

    def common(self):
        return dict(broker_id=self.broker, guard=self.guard)

    def submit(self, request_id="request-a", **changes):
        descriptor = copy.deepcopy(self.descriptor)
        descriptor.update(changes)
        return self.store.submit(descriptor=descriptor, request_id=request_id, submitter="person-a", **self.common())

    def grant(self, job, **changes):
        values = dict(job_id=job["job_id"], holder=self.holder, authority_revision=1,
                      storage_grant_id=uuid.uuid4().hex, expires_at=self.now + 60)
        values.update(changes)
        return self.store.authorize_input(**values, **self.common())

    def claim_arguments(self, job, grant):
        return dict(job_id=job["job_id"], grant_id=grant["id"], holder=self.holder,
                    authority_revision=1, credential_expires=self.now + 120)

    def prepared(self):
        job = self.submit()
        grant = self.grant(job)
        lease = self.store.claim(**self.claim_arguments(job, grant), **self.common())
        return job, grant, lease

    def read(self, lease):
        return self.store.with_current_lease(lease, operation=lambda: self.content, **self.common())

    def delivered(self):
        job, grant, lease = self.prepared()
        self.store.consume_input(lease, **self.common())
        self.assertEqual(self.read(lease), self.content)
        return job, grant, lease

    def result(self, lease):
        return {"schema": ADAPTER_ID, "job_id": lease["job_id"], "attempt_id": lease["attempt_id"],
                "input_sha256": self.reference.sha256, "categories": 2, "total": 19}

    def snapshot(self, job):
        return self.store.get(job["job_id"], **self.common())

    def query(self, sql, arguments=()):
        with closing(sqlite3.connect(self.store.path)) as connection:
            return connection.execute(sql, arguments).fetchall()

    def grant_state(self, grant):
        return self.query("SELECT state FROM grants WHERE id=?", (grant["id"],))[0][0]

    def processes(self, operations):
        gate = self.parent / ("gate-" + uuid.uuid4().hex)
        paths = list(dict.fromkeys([str(Path(__file__).resolve().parents[1] / "src"),
                                  sysconfig.get_path("purelib"), sysconfig.get_path("platlib")]))
        interpreter = getattr(sys, "_base_executable", sys.executable)
        processes, ready_files = [], []
        try:
            for operation, arguments in operations:
                ready = self.parent / ("ready-" + uuid.uuid4().hex)
                configuration = dict(paths=paths, root=str(self.store.root), store_id=self.store.store_id,
                    ready=str(ready), gate=str(gate), now=self.now, broker=self.broker,
                    operation=operation, arguments=arguments)
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
                    self.fail("Independent store processes did not reach barrier: " + repr(outputs))
                time.sleep(.01)
            gate.write_text("go", encoding="ascii")
            outcomes = []
            for process, (operation, _) in zip(processes, operations):
                output, error = process.communicate(timeout=15)
                if operation == "crash_read":
                    self.assertEqual(process.returncode, 23, error)
                    outcomes.append({"crashed": True})
                else:
                    self.assertEqual(process.returncode, 0, error)
                    self.assertEqual(error, "")
                    outcomes.append(json.loads(output))
            return outcomes
        finally:
            # Children execute fixed code and create no descendants. Own handles,
            # rather than discovered PIDs, are used for bounded cleanup.
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def assert_one_winner(self, outcomes):
        self.assertEqual(sum(outcome["ok"] for outcome in outcomes), 1, outcomes)
        self.assertEqual([item["error"] for item in outcomes if not item["ok"]], ["JobConflict"])

    def test_exact_descriptor_digest_idempotency_and_immutable_caller_snapshot(self):
        job = self.submit()
        self.assertEqual(job["digest"], sha256(self.descriptor))
        self.assertEqual(self.submit()["job_id"], job["job_id"])
        self.assertEqual(len(self.query("SELECT * FROM jobs")), 1)
        self.assertFalse(job["production_authorized"])
        self.assertFalse(job["model_delivery"])
        self.assertTrue(job["fixture_only"])
        job["descriptor"]["object_reference"]["sha256"] = "0" * 64
        self.assertEqual(self.snapshot(job)["descriptor"], self.descriptor)
        with self.assertRaises(JobConflict):
            self.submit(timeout_seconds=4)
        self.assertNotEqual(self.submit("different-request")["job_id"], job["job_id"])

    def test_descriptor_rejects_unknown_fields_cross_scope_paths_and_wrong_types(self):
        for change in ({"url": "https://invalid.example"}, {"case_id": "case-b"}, {"agency_id": "../agency"},
                       {"max_attempts": True}, {"max_attempts": 4}, {"lease_seconds": 0},
                       {"timeout_seconds": 11}, {"worker_sha256": "bad"}, {"environment": "production"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.submit(**change)
        reference = self.reference.to_dict()
        reference["version_id"] = "latest"
        with self.assertRaises(ValueError):
            self.submit(object_reference=reference)
        self.assertEqual(self.query("SELECT count(*) FROM jobs"), [(0,)])

    def test_two_independent_processes_claim_exactly_one_attempt(self):
        job = self.submit()
        grant = self.grant(job)
        arguments = self.claim_arguments(job, grant)
        outcomes = self.processes([("claim", arguments), ("claim", arguments)])
        self.assert_one_winner(outcomes)
        snapshot = self.snapshot(job)
        self.assertEqual(snapshot["fence"], 1)
        self.assertEqual(len(snapshot["attempts"]), 1)
        self.assertEqual(self.grant_state(grant), "leased")

    def test_two_independent_processes_consume_once(self):
        job, grant, lease = self.prepared()
        outcomes = self.processes([("consume", {"lease": lease}), ("consume", {"lease": lease})])
        self.assert_one_winner(outcomes)
        self.assertEqual(self.grant_state(grant), "consumed")
        self.assertEqual(self.query("SELECT count(*) FROM events WHERE event='input_consumed'"), [(1,)])

    def test_independent_cancel_and_complete_contention_has_one_terminal_winner(self):
        job, _, lease = self.delivered()
        outcomes = self.processes([("cancel", {"job_id": job["job_id"]}),
                                   ("complete", {"lease": lease, "result": self.result(lease)})])
        self.assert_one_winner(outcomes)
        snapshot = self.snapshot(job)
        self.assertIn(snapshot["state"], {"succeeded", "cancelled"})
        self.assertEqual(snapshot["result"] is not None, snapshot["state"] == "succeeded")
        self.assertEqual(snapshot["attempts"][0]["state"], snapshot["state"])

    def test_spent_reservation_and_delivered_output_survive_reopen(self):
        job, grant, lease = self.prepared()
        self.store.consume_input(lease, **self.common())
        self.store = jobs.JobStore.open(self.store.root, self.store.store_id)
        with self.assertRaises(JobConflict):
            self.store.consume_input(lease, **self.common())
        self.read(lease)
        completed = self.store.complete(lease, self.result(lease), **self.common())
        self.store = jobs.JobStore.open(self.store.root, self.store.store_id)
        self.assertEqual(self.snapshot(job), completed)
        self.assertEqual(self.grant_state(grant), "delivered")
        with self.assertRaises(JobConflict):
            self.store.complete(lease, self.result(lease), **self.common())

    def test_broker_restart_abandons_attempt_revokes_unspent_grants_and_fences_old_process(self):
        job, grant, lease = self.prepared()
        old = self.broker
        reopened = jobs.JobStore.open(self.store.root, self.store.store_id)
        self.broker = uuid.uuid4().hex
        reopened.activate_broker(self.broker, self.guard)
        snapshot = reopened.get(job["job_id"], **self.common())
        self.assertEqual(snapshot["state"], "queued")
        self.assertEqual(snapshot["attempts"][0]["state"], "abandoned")
        self.assertEqual(snapshot["attempts"][0]["reason"], "broker_restarted")
        self.assertEqual(self.grant_state(grant), "revoked")
        with self.assertRaises(JobUnavailable):
            self.store.consume_input(lease, broker_id=old, guard=self.guard)
        with self.assertRaises(JobConflict):
            reopened.activate_broker(old, self.guard)
        with self.assertRaises(JobConflict):
            self.store.complete(lease, self.result(lease), **self.common())

    def test_crash_inside_read_retains_read_started_tombstone_after_reopen(self):
        _, grant, lease = self.prepared()
        self.store.consume_input(lease, **self.common())
        self.processes([("crash_read", {"lease": lease})])
        self.store = jobs.JobStore.open(self.store.root, self.store.store_id)
        self.assertEqual(self.grant_state(grant), "read_started")
        operation = mock.Mock(side_effect=AssertionError("Read must not repeat"))
        with self.assertRaises(JobConflict):
            self.store.with_current_lease(lease, operation=operation, **self.common())
        operation.assert_not_called()
        with self.assertRaises(JobConflict):
            self.store.complete(lease, self.result(lease), **self.common())

    def test_failed_or_wrong_byte_read_is_never_refunded_or_completed(self):
        _, grant, lease = self.prepared()
        self.store.consume_input(lease, **self.common())
        operation = mock.Mock(return_value=self.content + b" ")
        with self.assertRaises(JobConflict):
            self.store.with_current_lease(lease, operation=operation, **self.common())
        self.assertEqual(operation.call_count, 1)
        self.assertEqual(self.grant_state(grant), "read_started")
        with self.assertRaises(JobConflict):
            self.read(lease)
        with self.assertRaises(JobConflict):
            self.store.complete(lease, self.result(lease), **self.common())

    def test_authority_exception_propagates_without_refunding_read(self):
        _, grant, lease = self.prepared()
        self.store.consume_input(lease, **self.common())
        class Denied(PermissionError):
            pass
        def deny():
            raise Denied("Current authority denied")
        with self.assertRaises(Denied):
            self.store.with_current_lease(lease, operation=deny, **self.common())
        self.assertEqual(self.grant_state(grant), "read_started")

    def test_completion_requires_actual_delivered_input_and_exact_result(self):
        _, _, lease = self.prepared()
        for phase in ("leased", "consumed"):
            if phase == "consumed":
                self.store.consume_input(lease, **self.common())
            with self.subTest(phase=phase), self.assertRaises(JobConflict):
                self.store.complete(lease, self.result(lease), **self.common())
        self.read(lease)
        for change in ({"total": True}, {"total": 20}, {"attempt_id": uuid.uuid4().hex},
                       {"input_sha256": "f" * 64}, {"extra": "metadata"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.complete(lease, dict(self.result(lease), **change), **self.common())
        self.assertEqual(self.store.complete(lease, self.result(lease), **self.common())["state"], "succeeded")

    def test_every_lease_nonce_fence_holder_revision_and_expiry_is_exact(self):
        _, _, lease = self.prepared()
        changes = {"job_id": uuid.uuid4().hex, "attempt_id": uuid.uuid4().hex, "broker_id": uuid.uuid4().hex,
                   "grant_id": uuid.uuid4().hex, "holder": "f" * 64, "authority_revision": 2,
                   "fence": 2, "expires_at": lease["expires_at"] + 1}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(JobConflict):
                self.store.consume_input(dict(lease, **{field: value}), **self.common())
        with self.assertRaises(ValueError):
            self.store.consume_input(dict(lease, unexpected=True), **self.common())
        self.store.consume_input(lease, **self.common())

    def test_claim_rejects_wrong_holder_revision_job_or_credential_and_preserves_grant(self):
        job = self.submit()
        grant = self.grant(job)
        arguments = self.claim_arguments(job, grant)
        for change in ({"holder": "f" * 64}, {"authority_revision": 2}, {"job_id": uuid.uuid4().hex},
                       {"grant_id": uuid.uuid4().hex}, {"credential_expires": self.now}):
            with self.subTest(change=change), self.assertRaises(JobConflict):
                self.store.claim(**dict(arguments, **change), **self.common())
        self.assertEqual(self.grant_state(grant), "authorized")
        self.assertEqual(self.snapshot(job)["attempts"], [])

    def test_expiry_reclaim_increments_fence_and_old_attempt_can_never_resume(self):
        job, old_grant, old = self.prepared()
        self.now = old["expires_at"]
        with self.assertRaises(JobConflict):
            self.store.renew(old, self.now + 120, **self.common())
        fresh_grant = self.grant(job)
        fresh = self.store.claim(**self.claim_arguments(job, fresh_grant), **self.common())
        self.assertEqual(fresh["fence"], old["fence"] + 1)
        self.assertNotEqual(fresh["attempt_id"], old["attempt_id"])
        self.assertEqual(self.grant_state(old_grant), "revoked")
        for operation in (lambda: self.store.consume_input(old, **self.common()),
                          lambda: self.read(old), lambda: self.store.complete(old, self.result(old), **self.common())):
            with self.assertRaises(JobConflict):
                operation()
        self.assertEqual([item["state"] for item in self.snapshot(job)["attempts"]], ["expired", "running"])

    def test_active_attempt_cannot_replace_input_authorization(self):
        job, _, _ = self.prepared()
        before = self.query("SELECT count(*) FROM grants")
        with self.assertRaises(JobConflict):
            self.grant(job)
        self.assertEqual(self.query("SELECT count(*) FROM grants"), before)

    def test_renewal_invalidates_old_lease_and_cannot_extend_forever(self):
        _, _, lease = self.prepared()
        self.now = 105
        renewed = self.store.renew(lease, 220, **self.common())
        self.assertEqual(renewed["expires_at"], 115)
        with self.assertRaises(JobConflict):
            self.store.consume_input(lease, **self.common())
        lease = renewed
        for value in range(110, 160, 5):
            self.now = value
            lease = self.store.renew(lease, 220, **self.common())
        self.assertEqual(lease["expires_at"], 160)
        self.now = 160
        with self.assertRaises(JobConflict):
            self.store.renew(lease, 300, **self.common())

    def test_failed_attempts_are_retained_and_retry_bound_is_terminal(self):
        job = self.submit()
        for index in range(3):
            grant = self.grant(job)
            lease = self.store.claim(**self.claim_arguments(job, grant), **self.common())
            snapshot = self.store.fail(lease, "timed_out", **self.common())
            self.assertEqual(snapshot["fence"], index + 1)
            self.assertEqual(len(snapshot["attempts"]), index + 1)
            self.assertEqual(self.grant_state(grant), "revoked")
        self.assertEqual(snapshot["state"], "failed")
        self.assertEqual([item["reason"] for item in snapshot["attempts"]], ["timed_out"] * 3)
        with self.assertRaises(JobConflict):
            self.grant(job)

    def test_cancel_revokes_input_and_late_success_cannot_replace_it(self):
        job, grant, lease = self.prepared()
        cancelled = self.store.cancel(job["job_id"], **self.common())
        self.assertEqual(self.store.cancel(job["job_id"], **self.common()), cancelled)
        self.assertEqual(self.grant_state(grant), "revoked")
        with self.assertRaises(JobConflict):
            self.store.consume_input(lease, **self.common())
        with self.assertRaises(JobConflict):
            self.store.complete(lease, self.result(lease), **self.common())

    def test_missing_corrupt_wrong_identity_and_extra_schema_fail_closed(self):
        with self.assertRaises(JobUnavailable):
            jobs.JobStore.open(self.parent / "missing", self.store.store_id)
        self.assertFalse((self.parent / "missing").exists())
        with self.assertRaises(JobUnavailable):
            jobs.JobStore.open(self.store.root, uuid.uuid4().hex)
        extra = jobs.JobStore.create(self.parent / "extra-schema")
        with closing(sqlite3.connect(extra.path)) as connection:
            connection.execute("CREATE TABLE unexpected (value TEXT)")
            connection.commit()
        with self.assertRaises(JobUnavailable):
            jobs.JobStore.open(extra.root, extra.store_id)
        self.store.path.write_bytes(b"not a sqlite database")
        with self.assertRaises(JobUnavailable):
            jobs.JobStore.open(self.store.root, self.store.store_id)

    def test_missing_existing_database_is_not_silently_recreated(self):
        job = self.submit()
        self.store.path.unlink()
        with self.assertRaises(JobUnavailable):
            self.snapshot(job)
        self.assertFalse(self.store.path.exists())

    def test_hardlinks_reparse_flags_database_and_root_substitution_are_rejected(self):
        job = self.submit()
        alias = self.parent / "database-alias"
        os.link(self.store.path, alias)
        with self.assertRaises(JobUnavailable):
            self.snapshot(job)
        alias.unlink()
        original = Path.lstat
        for target in (self.store.root, self.store.path):
            def reparse(path, *args, **kwargs):
                if path == target:
                    return SimpleNamespace(st_mode=stat.S_IFDIR if path == self.store.root else stat.S_IFREG,
                                           st_file_attributes=0x400)
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, "lstat", reparse), self.assertRaises(JobUnavailable):
                self.snapshot(job)
        replacement = self.parent / "replacement.sqlite"
        replacement.write_bytes(self.store.path.read_bytes())
        os.replace(replacement, self.store.path)
        with self.assertRaises(JobUnavailable):
            self.snapshot(job)

    def test_unexpected_journal_sidecar_is_rejected(self):
        job = self.submit()
        (self.store.root / "jobs.sqlite-wal").write_bytes(b"unexpected")
        with self.assertRaises(JobUnavailable):
            self.snapshot(job)

    def test_descriptor_tamper_is_detected_on_read(self):
        job = self.submit()
        altered = dict(self.descriptor, timeout_seconds=4)
        with closing(sqlite3.connect(self.store.path)) as connection:
            connection.execute("UPDATE jobs SET descriptor=? WHERE id=?", (json.dumps(altered), job["job_id"]))
            connection.commit()
        with self.assertRaises(JobUnavailable):
            self.snapshot(job)

    def test_job_grant_and_event_capacity_fail_atomically(self):
        job = self.submit()
        with mock.patch.object(jobs, "MAX_JOBS", 1), self.assertRaises(JobConflict):
            self.submit("over-capacity")
        self.grant(job)
        with mock.patch.object(jobs, "MAX_GRANTS", 1), self.assertRaises(JobConflict):
            self.grant(job)
        before = self.query("SELECT count(*) FROM events")[0][0]
        with mock.patch.object(jobs, "MAX_EVENTS", before), self.assertRaises(JobConflict):
            self.submit("events-full")
        self.assertEqual(self.query("SELECT count(*) FROM jobs"), [(1,)])
        self.assertEqual(self.query("SELECT count(*) FROM grants"), [(1,)])
        self.assertEqual(self.query("SELECT count(*) FROM events"), [(before,)])

    def test_database_size_and_broker_history_are_bounded(self):
        job = self.submit()
        with mock.patch.object(jobs, "MAX_DATABASE_BYTES", 1), self.assertRaises(JobUnavailable):
            self.snapshot(job)
        history = [uuid.uuid4().hex for _ in range(255)] + [self.broker]
        with closing(sqlite3.connect(self.store.path)) as connection:
            connection.execute("UPDATE meta SET value=? WHERE key='broker_history'", (json.dumps(history),))
            connection.commit()
        with self.assertRaises(JobConflict):
            self.store.activate_broker(uuid.uuid4().hex, self.guard)
        self.assertEqual(self.snapshot(job)["state"], "queued")

    def test_persisted_clock_rollback_and_invalid_clock_are_rejected(self):
        job = self.submit()
        self.now = 110
        self.snapshot(job)
        self.store = jobs.JobStore.open(self.store.root, self.store.store_id)
        self.now = 109
        with self.assertRaises(JobUnavailable):
            self.snapshot(job)
        for value in (True, -1, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.get(job["job_id"], self.broker, lambda: value)
        self.now = 110
        self.assertEqual(self.snapshot(job)["state"], "queued")

    def test_expiry_before_commit_rolls_back_claim_and_authorization(self):
        job = self.submit()
        clock = iter((100, 110))
        with self.assertRaises(JobConflict):
            self.store.authorize_input(job["job_id"], self.holder, 1, uuid.uuid4().hex, 110,
                                       self.broker, lambda: next(clock))
        self.assertEqual(self.query("SELECT count(*) FROM grants"), [(0,)])
        grant = self.grant(job)
        clock = iter((100, 110))
        with self.assertRaises(JobConflict):
            self.store.claim(**self.claim_arguments(job, grant), broker_id=self.broker, guard=lambda: next(clock))
        self.assertEqual(self.snapshot(job)["attempts"], [])
        self.assertEqual(self.grant_state(grant), "authorized")

    def test_expiry_during_bounded_read_burns_invocation_but_returns_no_bytes(self):
        _, grant, lease = self.prepared()
        self.store.consume_input(lease, **self.common())
        def slow_read():
            self.now = lease["expires_at"]
            return self.content
        with self.assertRaises(JobConflict):
            self.store.with_current_lease(lease, operation=slow_read, **self.common())
        self.assertEqual(self.grant_state(grant), "read_started")
        with self.assertRaises(JobConflict):
            self.store.complete(lease, self.result(lease), **self.common())

    def test_clock_and_authority_are_sampled_after_waiting_for_write_lock(self):
        job = self.submit()
        grant = self.grant(job, expires_at=110)
        connection = sqlite3.connect(self.store.path, isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        started, sampled = Event(), Event()
        def guard():
            sampled.set()
            return self.now
        def claim():
            started.set()
            return self.store.claim(**self.claim_arguments(job, grant), broker_id=self.broker, guard=guard)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(claim)
            try:
                self.assertTrue(started.wait(2))
                time.sleep(.1)
                self.assertFalse(sampled.is_set())
                self.now = 110
            finally:
                connection.rollback()
                connection.close()
            with self.assertRaises(JobConflict):
                future.result(timeout=4)
        self.assertTrue(sampled.is_set())
        self.assertEqual(self.snapshot(job)["attempts"], [])

    def test_renewed_lease_does_not_allow_callback_after_input_grant_expiry(self):
        job = self.submit()
        grant = self.grant(job, expires_at=105)
        lease = self.store.claim(**self.claim_arguments(job, grant), **self.common())
        self.now = 103
        lease = self.store.renew(lease, 220, **self.common())
        self.assertEqual(lease["expires_at"], 113)
        self.now = 104
        self.store.consume_input(lease, **self.common())
        clock = iter((104, 104, 105))
        operation = mock.Mock(return_value=self.content)
        with self.assertRaises(JobConflict):
            self.store.with_current_lease(lease, self.broker, lambda: next(clock), operation)
        operation.assert_not_called()
        self.assertEqual(self.grant_state(grant), "read_started")

    def test_busy_database_is_bounded_and_does_not_bypass_guard(self):
        job = self.submit()
        connection = sqlite3.connect(self.store.path, isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        guard = mock.Mock(return_value=self.now)
        started = time.monotonic()
        try:
            with self.assertRaises(JobUnavailable):
                self.store.get(job["job_id"], self.broker, guard)
        finally:
            connection.rollback()
            connection.close()
        self.assertLess(time.monotonic() - started, 4)
        guard.assert_not_called()
        self.assertEqual(self.snapshot(job)["state"], "queued")


if __name__ == "__main__":
    unittest.main()
