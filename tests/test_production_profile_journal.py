"""Real SQLite replay, floor, independent-review and process-boundary checks."""
from contextlib import closing, contextmanager
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_profile.contracts import STAGES, canonical_bytes, digest
from model_release_assurance.production_profile.journal import Journal, StoreConflict, StoreError, StoreUnavailable
from test_production_profile_contracts import plan_fixture, actor_fixture, payload_fixture

_ROOT = Path(__file__).resolve().parents[1]
_CHILD = r"""
import json, os, sys, time
from contextlib import contextmanager
from pathlib import Path
sys.path[:0] = [str(Path.cwd()/'src'),str(Path.cwd()/'tests')]
from model_release_assurance.production_profile.journal import Journal,StoreConflict
from test_production_profile_contracts import actor_fixture,payload_fixture
root,pin,mode,gate,variant = sys.argv[1:]
pin=json.loads(pin)
store=Journal.open(root,expected_pin=pin)
if gate:
    deadline=time.monotonic()+10
    while not Path(gate).exists():
        if time.monotonic()>deadline: raise RuntimeError('gate timeout')
        time.sleep(.01)
if mode=='after':
    original=Journal._transaction
    @contextmanager
    def crash_after(self,*args,**kwargs):
        with original(self,*args,**kwargs) as value:
            yield value
        os._exit(74)
    Journal._transaction=crash_after
calls=0
def guard():
    global calls
    calls+=1
    if mode=='before' and calls==2: os._exit(73)
    return 100
payload=payload_fixture('native')
if variant: payload['candidate_sha256']=variant*64
try:
    result=store.append('native',payload,actor_fixture(),expected_pin=pin,guard=guard)
    print(json.dumps({'outcome':'committed','pin':result['pin']}),flush=True)
except StoreConflict:
    print(json.dumps({'outcome':'conflict'}),flush=True)
"""


class ProfileJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.clock = 100
        self.journal = Journal.create(self.base / "journal", plan_fixture(), actor_fixture(), guard=self.guard)
        self.pin = self.journal.initial_pin

    def guard(self):
        return self.clock

    def read(self, pin=None, journal=None):
        return (journal or self.journal).read(expected_pin=pin or self.pin, guard=self.guard)

    def advance(self, stage, *, actor=None, payload=None, journal=None, pin=None):
        journal = journal or self.journal
        snapshot = journal.read(expected_pin=pin or self.pin, guard=self.guard)
        actor = actor or actor_fixture({"assess": "assessor", "approve": "approver"}.get(stage, "operator"))
        result = journal.append(stage, payload or payload_fixture(stage, snapshot), actor,
                                expected_pin=pin or snapshot["pin"], guard=self.guard)
        if journal is self.journal:
            self.pin = result["pin"]
        return result

    def through(self, target):
        for stage in STAGES[1:STAGES.index(target) + 1]:
            self.advance(stage)
        return self.read()

    def test_linear_lifecycle_reopen_and_owned_snapshots(self):
        initial = self.pin.copy()
        result = self.through("complete")
        self.assertEqual(result["stage"], "complete")
        self.assertEqual(list(result["stages"]), sorted(STAGES))
        self.assertEqual(result["pin"]["sequence"], 7)
        self.assertFalse(result["production_ready"])
        result["plan"]["recipient_id"] = "tampered"
        self.assertEqual(self.read()["plan"]["recipient_id"], "recipient")
        reopened = Journal.open(self.journal.root, expected_pin=self.pin)
        self.assertEqual(self.read(journal=reopened)["stages"], self.read()["stages"])
        self.assertEqual(self.read(initial)["pin"], self.pin)
        with self.assertRaises(StoreError):
            _ = reopened.initial_pin

    def test_exact_current_cas_and_permanent_no_repeat(self):
        original = self.pin.copy()
        self.advance("native")
        with self.assertRaises(StoreConflict):
            self.journal.append("external", payload_fixture("external"), actor_fixture(), expected_pin=original, guard=self.guard)
        with self.assertRaises(StoreConflict):
            self.advance("native")
        self.assertEqual(self.read()["stage"], "native")

    def test_no_skip_or_reset_stage(self):
        with self.assertRaises(StoreConflict):
            self.advance("external")
        with self.assertRaises(StoreConflict):
            self.advance("planned", payload=plan_fixture())
        self.assertEqual(self.read()["stage"], "planned")

    def test_native_exact_prospective_policy_and_campaign(self):
        for key, value in (("policy_sha256", "f" * 64), ("campaign_id", "f" * 32)):
            bad = payload_fixture("native")
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(StoreConflict):
                self.advance("native", payload=bad)
        self.assertEqual(self.read()["stage"], "planned")

    def test_independence_uses_canonical_person_not_credential(self):
        self.advance("native", actor=actor_fixture("fitter"))
        self.advance("external")
        for person in ("operator", "fitter"):
            actor = {**actor_fixture(person), "credential_sha256": "f" * 64}
            with self.subTest(person=person), self.assertRaises(StoreConflict):
                self.advance("assess", actor=actor)
        self.advance("assess")
        for person in ("operator", "fitter", "assessor"):
            with self.subTest(person=person), self.assertRaises(StoreConflict):
                self.advance("approve", actor=actor_fixture(person))
        self.advance("approve")

    def test_combined_binding_cannot_change_at_any_later_stage(self):
        self.through("external")
        for stage in ("assess", "approve", "authorize", "complete"):
            payload = payload_fixture(stage, self.read())
            payload["combined_sha256"] = "f" * 64
            with self.subTest(stage=stage), self.assertRaises(StoreConflict):
                self.advance(stage, payload=payload)
            self.advance(stage)

    def test_prior_assessment_and_approval_hashes_exact(self):
        self.through("assess")
        payload = payload_fixture("approve", self.read())
        payload["assessment_sha256"] = "f" * 64
        with self.assertRaises(StoreConflict):
            self.advance("approve", payload=payload)
        self.advance("approve")
        payload = payload_fixture("authorize", self.read())
        payload["approval_sha256"] = "f" * 64
        with self.assertRaises(StoreConflict):
            self.advance("authorize", payload=payload)

    def test_completion_exact_activation_store_and_monotonic_pin(self):
        snapshot = self.through("approve")
        payload = payload_fixture("authorize", snapshot)
        payload["delivery_pin"]["sequence"] = 5
        self.advance("authorize", payload=payload)
        for field, value in (("activation_id", "f" * 32), ("store_id", "f" * 32), ("sequence", 4), ("head_sha256", "e" * 64)):
            payload = payload_fixture("complete", self.read())
            if field == "activation_id":
                payload[field] = value
            else:
                payload["final_delivery_pin"][field] = value
            with self.subTest(field=field), self.assertRaises(StoreConflict):
                self.advance("complete", payload=payload)

    def test_clock_rollback_and_guard_failure_do_not_advance(self):
        self.clock = 99
        with self.assertRaises(StoreUnavailable):
            self.read()
        self.clock = 100
        calls = 0
        def expiry():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError("expired")
            return 100
        with self.assertRaises(PermissionError):
            self.journal.append("native", payload_fixture("native"), actor_fixture(), expected_pin=self.pin, guard=expiry)
        self.assertEqual(self.read()["stage"], "planned")

    def test_final_guard_runs_after_expensive_replay(self):
        original = self.journal._validate
        calls = 0
        def validation(connection):
            nonlocal calls
            result = original(connection)
            calls += 1
            if calls == 2:
                self.clock = 101
            return result
        def deadline():
            if self.clock >= 101:
                raise PermissionError("expired after replay")
            return self.clock
        with patch.object(self.journal, "_validate", side_effect=validation):
            with self.assertRaises(PermissionError):
                self.journal.append("native", payload_fixture("native"), actor_fixture(), expected_pin=self.pin, guard=deadline)
        self.assertEqual(self.read()["stage"], "planned")

    def test_clock_bool_and_invalid_guard(self):
        for bad in (lambda: True, lambda: -1, lambda: 2 ** 53):
            with self.assertRaises(StoreUnavailable):
                self.journal.read(expected_pin=self.pin, guard=bad)
        with self.assertRaises(StoreError):
            self.journal.read(expected_pin=self.pin, guard=None)

    def test_pinned_floor_rejects_rollback(self):
        backup = (self.journal.root / "journal.sqlite").read_bytes()
        self.advance("native")
        (self.journal.root / "journal.sqlite").write_bytes(backup)
        with self.assertRaises(StoreConflict):
            Journal.open(self.journal.root, expected_pin=self.pin)
        with self.assertRaises(StoreConflict):
            self.read()

    def test_same_revision_fork_rejected_by_other_history_pin(self):
        root = self.base / "fork"
        shutil.copytree(self.journal.root, root)
        fork = Journal.open(root, expected_pin=self.pin)
        initial = self.pin.copy()
        pin_a = self.advance("native")["pin"]
        payload = payload_fixture("native")
        payload["candidate_sha256"] = "f" * 64
        result_b = self.advance("native", journal=fork, pin=initial, payload=payload)
        self.assertNotEqual(pin_a["head_sha256"], result_b["pin"]["head_sha256"])
        with self.assertRaises(StoreConflict):
            Journal.open(root, expected_pin=pin_a)

    def test_replacement_same_bytes_rejected_on_existing_instance(self):
        path = self.journal.root / "journal.sqlite"
        alternative = self.base / "replacement.sqlite"
        alternative.write_bytes(path.read_bytes())
        os.replace(alternative, path)
        with self.assertRaises(StoreUnavailable):
            self.read()

    def test_hardlink_and_oversized_database_fail_closed(self):
        path = self.journal.root / "journal.sqlite"
        alias = self.base / "alias.sqlite"
        os.link(path, alias)
        with self.assertRaises(StoreUnavailable):
            self.read()
        alias.unlink()
        with path.open("ab") as stream:
            stream.truncate(2 * 1024 * 1024 + 1)
        with self.assertRaises(StoreUnavailable):
            self.read()

    def test_schema_corruption_and_missing_events_fail_closed(self):
        path = self.journal.root / "journal.sqlite"
        original = path.read_bytes()
        for sql in ("CREATE TABLE injected (value TEXT)", "PRAGMA user_version=2", "DELETE FROM events", "UPDATE events SET event_json='{}'"):
            with self.subTest(sql=sql):
                path.write_bytes(original)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(sql)
                with self.assertRaises(StoreUnavailable):
                    self.read()
        path.write_bytes(original)

    def test_restamped_semantically_invalid_record_rejected(self):
        path = self.journal.root / "journal.sqlite"
        with closing(sqlite3.connect(path)) as connection, connection:
            raw = connection.execute("SELECT event_json FROM events").fetchone()[0]
            event = json.loads(raw)
            event["record"]["payload"]["max_external_auc_bps"] = 10000
            body = {k: v for k, v in event["record"].items() if k != "sha256"}
            event["record"]["sha256"] = digest(body)
            event_sha = digest(event)
            connection.execute("UPDATE events SET event_json=?,event_sha256=?", (canonical_bytes(event).decode(), event_sha))
            connection.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (canonical_bytes(event_sha).decode(),))
        with self.assertRaises(StoreUnavailable):
            self.read()

    def test_pure_deserialized_replay_never_requires_paths_or_clock(self):
        self.through("complete")
        memory = sqlite3.connect(":memory:")
        self.addCleanup(memory.close)
        memory.deserialize((self.journal.root / "journal.sqlite").read_bytes())
        memory.execute("PRAGMA query_only=ON")
        reader = object.__new__(Journal)
        reader._store_id = self.journal.store_id
        state = reader._validate(memory)
        reader._floor(state, self.pin)
        self.assertEqual(reader._snapshot(state)["stage"], "complete")

    def test_create_no_overwrite_open_no_create_and_wrong_store(self):
        raw = (self.journal.root / "journal.sqlite").read_bytes()
        with self.assertRaises(StoreUnavailable):
            Journal.create(self.journal.root, plan_fixture(), actor_fixture(), guard=self.guard)
        self.assertEqual((self.journal.root / "journal.sqlite").read_bytes(), raw)
        missing = self.base / "missing"
        with self.assertRaises(StoreUnavailable):
            Journal.open(missing, expected_pin=self.pin)
        self.assertFalse(missing.exists())
        with self.assertRaises(StoreUnavailable):
            Journal.open(self.journal.root, expected_pin={**self.pin, "store_id": "f" * 32})

    def test_traversal_parent_is_rejected(self):
        with self.assertRaises(StoreUnavailable):
            Journal.create(self.base / "journal" / ".." / "other", plan_fixture(), actor_fixture(), guard=self.guard)
        self.assertFalse((self.base / "other").exists())

    def child(self, mode, gate="", variant=""):
        return subprocess.Popen([sys.executable, "-B", "-c", _CHILD, str(self.journal.root),
                                 json.dumps(self.pin), mode, str(gate), variant], cwd=_ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_independent_process_same_stage_race_commits_once(self):
        gate = self.base / "start"
        children = [self.child("race", gate, variant) for variant in ("a", "b")]
        gate.write_text("ready")
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=25)
            self.assertEqual(child.returncode, 0, stderr)
            results.append(json.loads(stdout)["outcome"])
        self.assertCountEqual(results, ["committed", "conflict"])
        snapshot = self.read()
        self.assertEqual(snapshot["pin"]["sequence"], 2)
        self.assertIn(snapshot["stages"]["native"]["payload"]["candidate_sha256"], ("a" * 64, "b" * 64))

    def test_abrupt_process_crash_before_commit_rolls_back(self):
        child = self.child("before")
        _, stderr = child.communicate(timeout=25)
        self.assertEqual(child.returncode, 73, stderr)
        opened = Journal.open(self.journal.root, expected_pin=self.pin)
        self.assertEqual(self.read(journal=opened)["stage"], "planned")
        self.advance("native", journal=opened)

    def test_abrupt_process_crash_after_commit_retains_stage(self):
        child = self.child("after")
        _, stderr = child.communicate(timeout=25)
        self.assertEqual(child.returncode, 74, stderr)
        opened = Journal.open(self.journal.root, expected_pin=self.pin)
        result = self.read(journal=opened)
        self.assertEqual(result["stage"], "native")
        with self.assertRaises(StoreConflict):
            opened.append("native", payload_fixture("native"), actor_fixture(), expected_pin=result["pin"], guard=self.guard)


if __name__ == "__main__":
    unittest.main()
