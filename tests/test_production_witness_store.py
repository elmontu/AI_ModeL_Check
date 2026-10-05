"""Adversarial local witness retention and independent-floor tests."""
from __future__ import annotations

import copy
from contextlib import closing
import json
import subprocess
import sys
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_registry.store import RegistryStore
from model_release_assurance.production_registry.contracts import account_id, strict_json as registry_json
from model_release_assurance.production_witness.contracts import (
    FLAGS, WitnessContractError, create_intent, digest, validate_history)
from model_release_assurance.production_witness.store import (
    WitnessStore, WitnessError, WitnessConflict, WitnessUnavailable)
from test_production_registry_contracts import request_fixture, context_fixture


def snapshot(registry, now):
    with registry._transaction(lambda: now) as (connection, state, _, _):
        rows = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        return validate_history({"schema": "mra-fixture-registry-history-snapshot/v1",
            "store_id": registry.store_id, "schema_version": state["version"],
            "broker_epoch": state["epoch"], "broker_id": state["broker_id"],
            "event_sequence": state["count"], "event_head_sha256": state["head"],
            "observed_at": now, "events": [{"event_sha256": row["event_sha256"],
                "event": registry_json(row["event_json"].encode("ascii"))} for row in rows], **FLAGS})


class WitnessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 1000
        self.registry = RegistryStore.create(self.root / "registry", accounts=[{"agency_id": "agency", "project_id": "project"}])
        self.broker = self.registry.activate_broker("5" * 32, expected_epoch=0, guard=self.guard)
        self.history = snapshot(self.registry, self.now)
        self.store = WitnessStore.create(self.root / "witness", namespace_id=account_id("agency", "project"),
            registry_id=self.registry.store_id, initial_history=self.history, guard=self.guard)
        self.pin = self.store.initial_pin

    def guard(self):
        return self.now

    def request(self, **changes):
        return request_fixture(store_id=self.registry.store_id, **changes)

    def intent(self, request=None, history=None):
        return create_intent(history or self.history, request or self.request())

    def prepare(self, intent=None, history=None):
        result = self.store.prepare(intent or self.intent(), history or self.history, expected_pin=self.pin, guard=self.guard)
        self.pin = result["pin"]
        return result

    def commit(self, request=None):
        return self.registry.commit(request or self.request(), context_fixture(broker_id=self.broker["broker_id"],
            broker_epoch=self.broker["epoch"]), broker=self.broker, guard=self.guard)

    def observe(self):
        result = self.store.observe(snapshot(self.registry, self.now), expected_pin=self.pin, guard=self.guard)
        self.pin = result["pin"]
        return result

    def test_enrollment_status_and_owned_initial_pin(self):
        result = self.store.status(expected_pin=self.pin, guard=self.guard)
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["intents"], [])
        self.assertFalse(result["independent_custody_verified"])
        self.assertFalse(result["production_authorized"])
        changed = self.store.initial_pin
        changed["head_sha256"] = "f" * 64
        self.assertEqual(self.store.initial_pin, self.pin)
        reopened = WitnessStore.open(self.store.root, expected_pin=self.pin)
        with self.assertRaises(WitnessError):
            _ = reopened.initial_pin

    def test_fresh_enrollment_requires_single_exact_account_and_no_commits(self):
        self.commit()
        with self.assertRaises(WitnessConflict):
            WitnessStore.create(self.root / "late", namespace_id=self.store.namespace_id,
                registry_id=self.registry.store_id, initial_history=snapshot(self.registry, self.now), guard=self.guard)
        multi = RegistryStore.create(self.root / "multi", accounts=[{"agency_id": "agency", "project_id": "project"},
            {"agency_id": "other", "project_id": "project"}])
        with self.assertRaises(WitnessConflict):
            WitnessStore.create(self.root / "bad", namespace_id=self.store.namespace_id,
                registry_id=multi.store_id, initial_history=snapshot(multi, self.now), guard=self.guard)
        with self.assertRaises(WitnessConflict):
            WitnessStore.create(self.root / "wrong", namespace_id="a" * 64,
                registry_id=self.registry.store_id, initial_history=self.history, guard=self.guard)
        self.assertFalse((self.root / "late").exists())

    def test_pending_intent_is_durable_idempotent_and_quarantined(self):
        intent = self.intent()
        first = self.prepare(intent)
        self.assertFalse(first["reconciled"])
        self.assertEqual(first["quarantine_reasons"], ["pending_intent"])
        self.assertEqual(first["pending_intents"], 1)
        retry = self.prepare(intent)
        self.assertEqual(retry, first)
        reopened = WitnessStore.open(self.store.root, expected_pin=self.pin)
        self.assertEqual(reopened.status(expected_pin=self.pin, guard=self.guard), first)
        first["intents"][0]["intent"]["request"]["case_id"] = "changed"
        self.assertEqual(reopened.status(expected_pin=self.pin, guard=self.guard)["intents"][0]["intent"], intent)

    def test_exact_commit_resolves_preexisting_intent_and_retains_receipt(self):
        self.prepare()
        receipt = self.commit()
        result = self.observe()
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["committed_intents"], 1)
        self.assertEqual(result["intents"][0]["receipt"], receipt)
        self.assertEqual(result["intents"][0]["state"], "committed")
        reopened = WitnessStore.open(self.store.root, expected_pin=self.pin)
        self.assertEqual(reopened.status(expected_pin=self.pin, guard=self.guard), result)

    def test_unknown_commit_is_never_adopted_or_retrospectively_prepared(self):
        intent = self.intent()
        self.commit()
        history = snapshot(self.registry, self.now)
        for action in (lambda: self.store.observe(history, expected_pin=self.pin, guard=self.guard),
                       lambda: self.store.prepare(intent, history, expected_pin=self.pin, guard=self.guard)):
            with self.assertRaises(WitnessConflict):
                action()
        result = self.store.status(expected_pin=self.pin, guard=self.guard)
        self.assertEqual(result["pin"], self.pin)
        self.assertEqual(result["registry_sequence"], self.history["event_sequence"])
        self.assertEqual(result["intents"], [])

    def test_changed_existing_intent_rejected(self):
        self.prepare()
        changed = self.intent(self.request(case_id="case-b"))
        with self.assertRaises(WitnessConflict):
            self.prepare(changed)
        self.assertEqual(self.store.status(expected_pin=self.pin, guard=self.guard)["pending_intents"], 1)

    def test_two_same_predecessor_intents_winner_commits_loser_irreversibly_aborts(self):
        winner = self.intent()
        loser = self.intent(self.request(request_id="3" * 32, case_id="case-b"))
        self.prepare(winner)
        self.prepare(loser)
        self.commit()
        result = self.observe()
        self.assertTrue(result["reconciled"])
        self.assertEqual((result["committed_intents"], result["aborted_intents"]), (1, 1))
        result = self.store.abort(loser, snapshot(self.registry, self.now), expected_pin=self.pin, guard=self.guard)
        self.assertEqual(result["aborted_intents"], 1)
        self.assertEqual(self.prepare(loser, snapshot(self.registry, self.now))["aborted_intents"], 1)

    def test_absence_timeout_or_new_broker_does_not_abort(self):
        intent = self.intent()
        self.prepare(intent)
        self.now = 1001
        self.broker = self.registry.activate_broker("6" * 32, expected_epoch=1, guard=self.guard)
        result = self.observe()
        self.assertFalse(result["reconciled"])
        self.assertEqual(result["pending_intents"], 1)
        with self.assertRaises(WitnessConflict):
            self.store.abort(intent, snapshot(self.registry, self.now), expected_pin=self.pin, guard=self.guard)
        self.now = 1400  # Expiry is deliberately not an abort proof here.
        self.assertEqual(self.observe()["pending_intents"], 1)

    def test_new_broker_commit_does_not_match_old_broker_intent(self):
        self.prepare()
        self.now = 1001
        self.broker = self.registry.activate_broker("6" * 32, expected_epoch=1, guard=self.guard)
        self.commit()
        with self.assertRaises(WitnessConflict):
            self.observe()
        self.assertEqual(self.store.status(expected_pin=self.pin, guard=self.guard)["pending_intents"], 1)

    def test_registry_lower_history_substitution_and_new_uuid_rejected(self):
        self.prepare()
        self.commit()
        self.observe()
        with self.assertRaises(WitnessConflict):
            self.store.observe(self.history, expected_pin=self.pin, guard=self.guard)
        other = RegistryStore.create(self.root / "other", accounts=[{"agency_id": "agency", "project_id": "project"}])
        with self.assertRaises(WitnessConflict):
            self.store.observe(snapshot(other, self.now), expected_pin=self.pin, guard=self.guard)
        bad = snapshot(self.registry, self.now)
        bad["events"][0]["event"]["payload"]["accounts"][0]["agency_id"] = "other"
        with self.assertRaises(WitnessContractError):
            self.store.observe(bad, expected_pin=self.pin, guard=self.guard)

    def test_missing_middle_event_and_head_substitution_rejected(self):
        self.prepare()
        self.commit()
        history = snapshot(self.registry, self.now)
        for mutate in (lambda value: value["events"].pop(1),
                       lambda value: value.update(event_head_sha256="a" * 64)):
            changed = copy.deepcopy(history)
            mutate(changed)
            with self.assertRaises(WitnessContractError):
                self.store.observe(changed, expected_pin=self.pin, guard=self.guard)
        self.assertEqual(self.store.status(expected_pin=self.pin, guard=self.guard)["pin"], self.pin)

    def test_external_pin_detects_own_rollback_and_fork(self):
        backup = self.root / "backup"
        shutil.copytree(self.store.root, backup)
        initial = self.pin
        self.prepare()
        with self.assertRaises(WitnessConflict):
            WitnessStore.open(backup, expected_pin=self.pin)
        old = WitnessStore.open(backup, expected_pin=initial)
        fork = old.prepare(self.intent(self.request(request_id="3" * 32)), self.history, expected_pin=initial, guard=self.guard)
        with self.assertRaises(WitnessConflict):
            WitnessStore.open(backup, expected_pin=self.pin)
        with self.assertRaises(WitnessConflict):
            self.store.status(expected_pin=fork["pin"], guard=self.guard)
        self.assertEqual(self.store.status(expected_pin=initial, guard=self.guard)["pin"], self.pin)

    def test_wrong_pin_identity_or_unknown_floor_rejected(self):
        for key, value in (("witness_id", "f" * 32), ("registry_id", "e" * 32),
                           ("namespace_id", "d" * 64), ("head_sha256", "c" * 64), ("revision", 2)):
            changed = {**self.pin, key: value}
            with self.assertRaises(WitnessConflict):
                self.store.status(expected_pin=changed, guard=self.guard)

    def test_clock_rollback_bool_and_future_history_rejected(self):
        for now in (999, True, 1000.0):
            with self.assertRaises(WitnessUnavailable):
                self.store.status(expected_pin=self.pin, guard=lambda: now)
        history = {**self.history, "observed_at": 1001}
        with self.assertRaises(WitnessConflict):
            self.store.observe(history, expected_pin=self.pin, guard=self.guard)

    def test_final_guard_after_expensive_replay_rolls_back(self):
        original = self.store._validate
        calls = [0]
        def validate(connection):
            result = original(connection)
            calls[0] += 1
            if calls[0] >= 2:
                self.now = 1002
            return result
        def deadline_guard():
            if self.now >= 1002:
                raise PermissionError("expired")
            return self.now
        with patch.object(self.store, "_validate", side_effect=validate):
            with self.assertRaises(PermissionError):
                self.store.prepare(self.intent(), self.history, expected_pin=self.pin, guard=deadline_guard)
        result = self.store.status(expected_pin=self.pin, guard=self.guard)
        self.assertEqual(result["intents"], [])
        self.assertEqual(result["pin"], self.pin)

    def test_corrupt_material_or_schema_fails_closed(self):
        for label, sql in (("head", "UPDATE meta SET value='\"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\"' WHERE key='head_sha256'"),
                           ("row", "DELETE FROM registry_events WHERE sequence=1"),
                           ("schema", "CREATE TABLE surprise (id INTEGER)")):
            with self.subTest(label=label):
                path = self.root / label
                shutil.copytree(self.store.root, path)
                with closing(sqlite3.connect(path / "witness.sqlite")) as connection:
                    connection.execute(sql)
                    connection.commit()
                with self.assertRaises(WitnessUnavailable):
                    WitnessStore.open(path, expected_pin=self.pin)

    def test_existing_root_never_overwritten_and_missing_open_never_created(self):
        with self.assertRaises(WitnessUnavailable):
            WitnessStore.create(self.store.root, namespace_id=self.store.namespace_id,
                registry_id=self.registry.store_id, initial_history=self.history, guard=self.guard)
        with self.assertRaises(WitnessUnavailable):
            WitnessStore.open(self.root / "missing", expected_pin=self.pin)
        self.assertFalse((self.root / "missing").exists())

    def test_hardlink_substitution_and_unsafe_parent_rejected(self):
        import os
        alias = self.root / "alias.sqlite"
        os.link(self.store.root / "witness.sqlite", alias)
        with self.assertRaises(WitnessUnavailable):
            self.store.status(expected_pin=self.pin, guard=self.guard)
        alias.unlink()
        with self.assertRaises(WitnessUnavailable):
            WitnessStore.open(self.store.root / ".." / "witness", expected_pin=self.pin)


    def test_matching_request_id_with_changed_commit_payload_is_not_covered(self):
        self.prepare()
        self.commit(self.request(case_id="case-b"))
        with self.assertRaises(WitnessConflict):
            self.observe()
        self.assertEqual(self.store.status(expected_pin=self.pin, guard=self.guard)["registry_sequence"], 2)

    def test_migration_preserves_pending_and_commit_history(self):
        legacy = RegistryStore.create(self.root / "legacy", accounts=[{"agency_id": "agency", "project_id": "project"}], schema_version=1)
        legacy.activate_broker("a" * 32, expected_epoch=0, guard=self.guard)
        history = snapshot(legacy, self.now)
        witness = WitnessStore.create(self.root / "legacy-witness", namespace_id=self.store.namespace_id,
            registry_id=legacy.store_id, initial_history=history, guard=self.guard)
        intent = create_intent(history, request_fixture(store_id=legacy.store_id))
        pin = witness.prepare(intent, history, expected_pin=witness.initial_pin, guard=self.guard)["pin"]
        RegistryStore.migrate(legacy.root, legacy.store_id, from_version=1, to_version=2, guard=self.guard)
        current = RegistryStore.open(legacy.root, legacy.store_id)
        result = witness.observe(snapshot(current, self.now), expected_pin=pin, guard=self.guard)
        self.assertEqual(result["pending_intents"], 1)
        self.assertFalse(result["reconciled"])
        self.assertEqual(result["registry_epoch"], 2)

    def test_pending_capacity_is_bounded_without_losing_existing_intents(self):
        for number in range(32):
            self.prepare(self.intent(self.request(request_id=f"{number + 1:032x}")))
        before = self.pin
        with self.assertRaises(WitnessConflict):
            self.prepare(self.intent(self.request(request_id="f" * 32)))
        result = self.store.status(expected_pin=self.pin, guard=self.guard)
        self.assertEqual(result["pending_intents"], 32)
        self.assertEqual(result["pin"], before)
        self.assertEqual(len(result["intents"]), 32)

    def test_observed_at_cannot_regress_or_claim_future_freshness(self):
        self.now = 1001
        result = self.observe()
        self.assertEqual(result["registry_observed_at"], 1001)
        with self.assertRaises(WitnessConflict):
            self.store.observe(self.history, expected_pin=self.pin, guard=self.guard)
        with self.assertRaises(WitnessConflict):
            self.store.observe({**self.history, "observed_at": 1002}, expected_pin=self.pin, guard=self.guard)

    def test_event_log_or_registry_copy_mutation_is_detected(self):
        self.prepare()
        for table, key in (("events", "revision"), ("registry_events", "sequence")):
            path = self.root / ("tamper-" + table)
            shutil.copytree(self.store.root, path)
            with closing(sqlite3.connect(path / "witness.sqlite")) as connection:
                connection.execute(f"UPDATE {table} SET event_sha256=? WHERE {key}=1", ("a" * 64,))
                connection.commit()
            with self.assertRaises(WitnessUnavailable):
                WitnessStore.open(path, expected_pin=self.pin)

    def _process(self, intent, *, mode="normal"):
        payload = json.dumps({"root": str(self.store.root), "pin": self.pin,
                              "intent": intent, "history": self.history, "mode": mode})
        script = """
import json,os,sys
from model_release_assurance.production_witness.store import WitnessStore,WitnessConflict
p=json.loads(sys.argv[1])
store=WitnessStore.open(p['root'],expected_pin=p['pin'])
if p['mode']=='before_commit':
    original=store._append
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        os._exit(73)
    store._append=fail
try:
    result=store.prepare(p['intent'],p['history'],expected_pin=p['pin'],guard=lambda:1000)
except WitnessConflict:
    print('conflict',flush=True)
else:
    if p['mode']=='after_commit':
        os._exit(74)
    print(json.dumps({'pin':result['pin'],'pending':result['pending_intents']}),flush=True)
"""
        return subprocess.Popen([sys.executable, "-B", "-c", script, payload],
            cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_process_crash_before_commit_rolls_back_after_commit_retains_pending(self):
        for mode, code, expected in (("before_commit", 73, 0), ("after_commit", 74, 1)):
            child = self._process(self.intent(), mode=mode)
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, code, stdout + stderr)
            reopened = WitnessStore.open(self.store.root, expected_pin=self.pin)
            result = reopened.status(expected_pin=self.pin, guard=self.guard)
            self.assertEqual(result["pending_intents"], expected)
            if expected:
                self.assertFalse(result["reconciled"])
                self.assertEqual(reopened.prepare(self.intent(), self.history,
                    expected_pin=result["pin"], guard=self.guard), result)

    def test_process_exact_retry_preserves_one_permanent_intent(self):
        children = [self._process(self.intent()) for _ in range(2)]
        outputs = []
        for child in children:
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, stderr)
            outputs.append(json.loads(stdout))
        self.assertEqual(outputs[0], outputs[1])
        result = self.store.status(expected_pin=self.pin, guard=self.guard)
        self.assertEqual(result["pending_intents"], 1)
        self.assertEqual(result["pin"]["revision"], 2)

    def test_process_changed_same_id_race_has_one_winner_no_replacement(self):
        children = [self._process(self.intent()), self._process(self.intent(self.request(case_id="case-b")))]
        outputs = []
        for child in children:
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, stderr)
            outputs.append(stdout.strip())
        self.assertEqual(outputs.count("conflict"), 1)
        self.assertEqual(self.store.status(expected_pin=self.pin, guard=self.guard)["pending_intents"], 1)


if __name__ == "__main__":
    unittest.main()
