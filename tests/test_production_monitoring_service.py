"""Signed local operations and durable redacted custody, never release authority."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import uuid

from test_production_review_authorization import AuthorizationFixture
from model_release_assurance.production_identity.policy import PermissionDenied, IdentityUnavailable
from model_release_assurance.production_monitoring import contracts as c
from model_release_assurance.production_monitoring.service import FixtureMonitoringService
from model_release_assurance.production_monitoring.receiver import FixtureAlertReceiver
from model_release_assurance.production_monitoring.store import MonitorStore, MonitorError, MonitorConflict, MonitorUnavailable


def event(*, resource=None, condition="fault", code="worker_unavailable", at=1000):
    return {"schema": "mra-fixture-monitor-event/v1", "event_id": uuid.uuid4().hex,
            "resource_id": resource or uuid.uuid4().hex, "observed_at": at,
            "code": code, "condition": condition, **c.FLAGS}


def alert(*, event_value=None):
    item = event_value or event()
    return {"alert_id": item["event_id"], "incident_id": uuid.uuid4().hex, "event": item,
            **c.RULES[item["code"]], "acknowledged": False, "receiver_pin": None}


class MonitoringServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.f = AuthorizationFixture()
        self.store = MonitorStore.create(self.root / "monitor", profile="local_public_fixture")
        self.saved = []
        self.service = FixtureMonitoringService(self.f.identity, self.store,
            expected_pin=self.store.initial_pin, checkpoint_sink=lambda pin: self.saved.append(pin),
            profile="local_public_fixture")

    def token(self, **changes):
        return self.f.token("reader", **changes)

    def state(self):
        return self.store.read(expected_pin=self.service.pin, guard=lambda: self.f.now)

    def test_production_default_refuses_before_access_or_sink(self):
        sink = mock.Mock()
        with self.assertRaises(MonitorError):
            FixtureMonitoringService(None, None, expected_pin={}, checkpoint_sink=sink)
        sink.assert_not_called()

    def test_redacted_fault_recovery_ack_resolve_has_no_release_effect(self):
        first = event()
        state = self.service.observe(first)
        incident = state["incidents"][0]["id"]
        self.assertEqual(state["incidents"][0]["status"], "open")
        self.service.observe(event(resource=first["resource_id"], condition="healthy"))
        self.service.incident(self.token(), "case-a", uuid.uuid4().hex, incident, "acknowledge")
        final = self.service.incident(self.token(), "case-a", uuid.uuid4().hex, incident, "resolve")
        self.assertEqual(final["incidents"][0]["status"], "resolved")
        encoded = json.dumps(final)
        for secret in ("reader", "person-reader", "client", "Bearer", "https://review"):
            self.assertNotIn(secret, encoded)
        self.assertTrue(all(final[key] is value for key, value in c.FLAGS.items()))
        self.assertEqual(self.f.identity.read_case(self.token(), "case-a")["proposal"], None)
        actors = [op["actor"] for op in final["operations"] if op["kind"] == "action"]
        self.assertEqual(actors, [{"kind": "human", "authority_revision": 1}] * 2)

    def test_exact_auditor_role_required_not_broad_case_reader_or_worker(self):
        for subject in ("owner", "operator", "policy", "assessor", "approver", "worker"):
            with self.subTest(subject=subject), self.assertRaises(Exception):
                self.service.snapshot(self.f.token(subject))
        self.assertEqual(self.service.snapshot(self.token())["events"], [])

    def test_scope_and_case_and_signature_are_required(self):
        for token, case in ((self.token(scopes={"review:assess"}), "case-a"),
                            (self.token(cases=["case-b"]), "case-a"),
                            (self.token(), "case-b"), ("not.a.token", "case-a")):
            with self.subTest(case=case), self.assertRaises(Exception):
                self.service.snapshot(token, case)
        self.assertEqual(self.state()["events"], [])

    def test_fresh_mfa_required(self):
        for changes in ({"acr": "wrong"}, {"auth_time": 600}):
            with self.subTest(changes=changes), self.assertRaises(Exception):
                self.service.snapshot(self.token(**changes))

    def test_current_role_removal_denies(self):
        token = self.token()
        grants = tuple(replace(g, roles=frozenset({"model_owner"}))
                       if g.person_id == "person-reader" else g for g in self.f.authority.grants)
        self.f.update(grants=grants)
        with self.assertRaises(PermissionDenied):
            self.service.snapshot(token)
        self.assertEqual(self.state()["events"], [])

    def test_current_token_and_signing_key_revocation_deny(self):
        token = self.token(jti="revoked-monitor-token")
        self.f.update(revoked_token_ids=frozenset({"revoked-monitor-token"}))
        with self.assertRaises(PermissionDenied):
            self.service.snapshot(token)
        fresh = self.token()
        self.f.trust.revoke("key", expected_revision=self.f.trust.revision)
        with self.assertRaises(Exception):
            self.service.snapshot(fresh)
        self.service.observe(event(code="key_unavailable"))
        self.assertEqual(len(self.state()["events"]), 1)

    def test_key_outage_denies_people_but_internal_observation_survives(self):
        token = self.token()
        self.f.trust.set_available(False, expected_revision=self.f.trust.revision)
        self.service.observe(event(code="key_unavailable"))
        with self.assertRaises(Exception):
            self.service.snapshot(token)
        self.assertEqual(len(self.state()["events"]), 1)
        self.f.trust.set_available(True, expected_revision=self.f.trust.revision)
        self.assertEqual(len(self.service.snapshot(self.token())["events"]), 1)

    def test_expired_authority_does_not_stop_internal_observation(self):
        token = self.token()
        self.f.now = 1250
        self.service.observe(event(code="key_unavailable", at=1250))
        with self.assertRaises(Exception):
            self.service.snapshot(token)
        self.assertEqual(self.state()["events"][0]["observed_at"], 1250)

    def test_future_or_private_fields_refused_before_sink(self):
        calls = len(self.saved)
        for item in (event(at=1001), {**event(), "details": "secret@example.invalid"},
                     {**event(), "observed_at": True}):
            with self.subTest(item=item), self.assertRaises(Exception):
                self.service.observe(item)
        self.assertEqual(len(self.saved), calls)
        self.assertEqual(self.state()["events"], [])

    def test_observation_input_is_owned_before_sink_mutates_caller(self):
        original = event()
        expected = json.loads(json.dumps(original))
        self.service._sink = lambda pin: original.update(resource_id="e" * 32)
        self.service.observe(original)
        self.assertEqual(self.state()["events"], [expected])

    def test_sink_failure_retains_committed_head_and_flush_recovers(self):
        initial = self.service.pin
        self.service._sink = mock.Mock(side_effect=RuntimeError("private path/token"))
        with self.assertRaisesRegex(MonitorUnavailable, "^Monitoring checkpoint unavailable$"):
            self.service.observe(event())
        self.assertGreater(self.service.pin["sequence"], initial["sequence"])
        self.assertEqual(len(self.state()["events"]), 1)
        self.service._sink = lambda pin: self.saved.append(pin)
        result = self.service.flush_checkpoint()
        self.assertEqual(self.saved[-1], result["pin"])

    def test_checkpoint_input_cannot_mutate_held_floor(self):
        self.service._sink = lambda pin: pin.update(head_sha256="f" * 64)
        self.service.observe(event())
        self.assertNotEqual(self.service.pin["head_sha256"], "f" * 64)
        self.assertEqual(self.service.pin, self.state()["pin"])

    def test_sink_expiry_denies_return_after_durable_action(self):
        state = self.service.observe(event())
        incident_id = state["incidents"][0]["id"]
        token = self.token(expires=1001)
        self.service._sink = lambda pin: setattr(self.f, "now", 1001) if pin["sequence"] > state["pin"]["sequence"] else None
        with self.assertRaises(Exception):
            self.service.incident(token, "case-a", uuid.uuid4().hex, incident_id, "acknowledge")
        self.assertEqual(self.state()["incidents"][0]["status"], "acknowledged")
        self.assertEqual(self.service.pin, self.state()["pin"])

    def test_sink_current_role_change_denies_snapshot(self):
        token = self.token()
        def sink(pin):
            grants = tuple(replace(g, roles=frozenset({"model_owner"}))
                           if g.person_id == "person-reader" else g for g in self.f.authority.grants)
            self.f.update(grants=grants)
        self.service._sink = sink
        with self.assertRaises(PermissionDenied):
            self.service.snapshot(token)

    def test_restart_uses_external_floor_and_catches_restore(self):
        old_bytes = (self.store.root / "monitor.sqlite").read_bytes()
        self.service.observe(event())
        pin = self.service.pin
        reopened = MonitorStore.open(self.store.root, expected_pin=pin)
        restored = FixtureMonitoringService(self.f.identity, reopened, expected_pin=pin,
            checkpoint_sink=lambda value: None, profile="local_public_fixture")
        self.assertEqual(restored.snapshot(self.token())["events"], self.state()["events"])
        (self.store.root / "monitor.sqlite").write_bytes(old_bytes)
        with self.assertRaises(MonitorError):
            MonitorStore.open(self.store.root, expected_pin=pin)

    def test_route_is_local_custody_and_not_operator_incident_ack(self):
        state = self.service.observe(event())
        pending = state["alerts"][0]
        receiver = FixtureAlertReceiver.create(self.root / "receiver")
        state = self.service.route_pending(self.token(), "case-a", receiver)
        self.assertTrue(state["alerts"][0]["acknowledged"])
        self.assertEqual(state["incidents"][0]["status"], "open")
        self.assertFalse(state["external_notifications_sent"])
        pin = receiver.pin
        receiver.receive(pending, expected_pin=pin, guard=lambda: self.f.now)
        self.assertEqual(receiver.pin, pin)
        self.assertEqual(len(receiver.snapshot(guard=lambda: self.f.now)["deliveries"]), 1)
        self.assertEqual(self.service.route_pending(self.token(), "case-a", receiver)["pin"], state["pin"])

    def test_expiry_after_receiver_commit_retains_pending_then_deduplicates(self):
        self.service.observe(event())
        receiver = FixtureAlertReceiver.create(self.root / "receiver")
        token = self.token(expires=1001)
        original = receiver.receive
        def receive(*args, **kwargs):
            result = original(*args, **kwargs)
            self.f.now = 1001
            return result
        with mock.patch.object(receiver, "receive", side_effect=receive), self.assertRaises(Exception):
            self.service.route_pending(token, "case-a", receiver)
        self.assertFalse(self.state()["alerts"][0]["acknowledged"])
        self.assertEqual(receiver.pin["sequence"], 1)
        self.service.route_pending(self.token(), "case-a", receiver)
        self.assertTrue(self.state()["alerts"][0]["acknowledged"])
        self.assertEqual(receiver.pin["sequence"], 1)

    def test_committed_incident_retry_at_later_time_reuses_original_operation(self):
        state = self.service.observe(event())
        incident_id = state["incidents"][0]["id"]
        operation_id = uuid.uuid4().hex
        def sink(pin):
            if pin["sequence"] > state["pin"]["sequence"]:
                raise RuntimeError("lost acknowledgment")
        self.service._sink = sink
        with self.assertRaises(MonitorUnavailable):
            self.service.incident(self.token(), "case-a", operation_id, incident_id, "acknowledge")
        retained = self.state()
        self.f.now = 1005
        self.service._sink = lambda pin: self.saved.append(pin)
        retried = self.service.incident(self.token(), "case-a", operation_id, incident_id, "acknowledge")
        self.assertEqual(retried["pin"], retained["pin"])
        self.assertEqual(retried["operations"], retained["operations"])
        with self.assertRaises(MonitorConflict):
            self.service.incident(self.token(), "case-a", operation_id, incident_id, "resolve")

    def test_acknowledged_alert_rejects_replacement_or_unavailable_receiver(self):
        self.service.observe(event())
        receiver = FixtureAlertReceiver.create(self.root / "receiver")
        self.service.route_pending(self.token(), "case-a", receiver)
        replacement = FixtureAlertReceiver.create(self.root / "replacement")
        with self.assertRaises(MonitorUnavailable):
            self.service.route_pending(self.token(), "case-a", replacement)
        (receiver.root / "receiver.sqlite").unlink()
        with self.assertRaises(MonitorUnavailable):
            self.service.route_pending(self.token(), "case-a", receiver)

    def test_acknowledged_alert_floor_detects_receiver_restore_even_reopened_old(self):
        self.service.observe(event())
        receiver = FixtureAlertReceiver.create(self.root / "receiver")
        initial, raw = receiver.pin, (receiver.root / "receiver.sqlite").read_bytes()
        self.service.route_pending(self.token(), "case-a", receiver)
        (receiver.root / "receiver.sqlite").write_bytes(raw)
        reopened = FixtureAlertReceiver.open(receiver.root, initial)
        with self.assertRaises(MonitorUnavailable):
            self.service.route_pending(self.token(), "case-a", reopened)

    def test_checkpoint_callback_cannot_reenter_and_commit_uncheckpointed_event(self):
        self.service._sink = lambda pin: self.service.observe(event())
        with self.assertRaises(MonitorUnavailable):
            self.service.observe(event())
        self.assertEqual(len(self.state()["events"]), 1)

    def test_unknown_action_and_arbitrary_receiver_are_refused(self):
        state = self.service.observe(event())
        for action in ("approve", "release", "revoke_model", "grant"):
            with self.subTest(action=action), self.assertRaises(Exception):
                self.service.incident(self.token(), "case-a", uuid.uuid4().hex,
                                      state["incidents"][0]["id"], action)
        with self.assertRaises(MonitorError):
            self.service.route_pending(self.token(), "case-a", mock.Mock())
        self.assertEqual(self.state()["operations"], [])


class AlertReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receiver = FixtureAlertReceiver.create(self.root / "receiver")
        self.now = 1000

    def send(self, value=None, guard=None):
        return self.receiver.receive(value or alert(), expected_pin=self.receiver.pin,
                                     guard=guard or (lambda: self.now))

    def test_exact_retry_and_restart_keep_one_effect_and_receipt(self):
        value = alert()
        first = self.send(value)
        self.assertEqual(self.send(value), first)
        self.receiver = FixtureAlertReceiver.open(self.receiver.root, self.receiver.pin)
        self.assertEqual(self.send(value), first)
        self.assertEqual(len(self.receiver.snapshot(guard=lambda: self.now)["deliveries"]), 1)

    def test_same_alert_id_changed_envelope_is_not_deduplicated(self):
        value = alert()
        self.send(value)
        for changed in ({**value, "incident_id": uuid.uuid4().hex},
                        {**value, "event": {**value["event"], "resource_id": uuid.uuid4().hex}}):
            with self.subTest(changed=changed), self.assertRaises(MonitorConflict):
                self.send(changed)
        self.assertEqual(self.receiver.pin["sequence"], 1)

    def test_routing_labels_unknown_fields_and_future_time_rejected(self):
        value = alert()
        called = mock.Mock(return_value=1000)
        for changed in ({**value, "route": "email:secret@example.invalid"},
                        {**value, "diagnostic": "private-data"}):
            with self.assertRaises(c.MonitoringContractError):
                self.send(changed, guard=called)
        called.assert_not_called()
        with self.assertRaises(MonitorError):
            self.send(alert(event_value=event(at=1001)))
        self.assertEqual(self.receiver.pin["sequence"], 0)

    def test_final_guard_failure_rolls_back_all_effects(self):
        calls = []
        def guard():
            calls.append(1)
            if len(calls) == 2:
                raise PermissionDenied("expired")
            return 1000
        with self.assertRaises(PermissionDenied):
            self.send(guard=guard)
        self.assertEqual(self.receiver.pin["sequence"], 0)
        self.assertEqual(self.receiver.snapshot(guard=lambda: self.now)["deliveries"], [])

    def test_restored_prefix_wrong_store_and_clock_rollback_fail(self):
        old = (self.receiver.root / "receiver.sqlite").read_bytes()
        self.send()
        pin = self.receiver.pin
        self.now = 999
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now)
        self.now = 1000
        with self.assertRaises(MonitorUnavailable):
            FixtureAlertReceiver.open(self.receiver.root, {**pin, "store_id": "e" * 32})
        (self.receiver.root / "receiver.sqlite").write_bytes(old)
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now)
        with self.assertRaises(MonitorUnavailable):
            FixtureAlertReceiver.open(self.receiver.root, pin)

    def test_changed_stored_envelope_and_unknown_schema_fail_closed(self):
        self.send()
        db = sqlite3.connect(self.receiver.root / "receiver.sqlite")
        db.execute("UPDATE deliveries SET record_json='{}'")
        db.commit(); db.close()
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now)

    def test_hardlinks_and_reparse_flag_refused(self):
        database = self.receiver.root / "receiver.sqlite"
        linked = self.root / "linked.sqlite"
        os.link(database, linked)
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now)
        linked.unlink()
        with mock.patch("model_release_assurance.production_monitoring.receiver._unsafe", return_value=True):
            with self.assertRaises(MonitorUnavailable):
                self.receiver.snapshot(guard=lambda: self.now)

    def test_capacity_retains_existing_effects_and_exact_retry(self):
        first = alert()
        with mock.patch.object(c, "MAX_RECORDS", 1):
            self.send(first)
            with self.assertRaises(MonitorConflict):
                self.send()
            self.send(first)
        self.assertEqual(self.receiver.pin["sequence"], 1)

    def test_input_snapshot_precedes_trusted_guard(self):
        value = alert()
        expected = json.loads(json.dumps(value))
        def guard():
            value["event"]["resource_id"] = "e" * 32
            return 1000
        result = self.send(value, guard=guard)
        self.assertEqual(result["delivery"]["alert"]["event"], expected["event"])

    def test_custody_requires_exact_envelope_present_before_recorded_floor(self):
        first, second = alert(), alert()
        self.send(first)
        first_pin = self.receiver.pin
        self.send(second)
        wrong_time = {**second, "acknowledged": True, "receiver_pin": first_pin}
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now, expected_alerts=[wrong_time])
        changed = {**first, "incident_id": "e" * 32, "acknowledged": True, "receiver_pin": first_pin}
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now, expected_alerts=[changed])
        exact = {**first, "acknowledged": True, "receiver_pin": first_pin}
        self.assertEqual(len(self.receiver.snapshot(guard=lambda: self.now, expected_alerts=[exact])["deliveries"]), 2)

    def test_missing_database_is_not_recreated(self):
        (self.receiver.root / "receiver.sqlite").unlink()
        with self.assertRaises(MonitorUnavailable):
            self.receiver.snapshot(guard=lambda: self.now)
        self.assertFalse((self.receiver.root / "receiver.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
