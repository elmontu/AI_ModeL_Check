"""Real signed current-authority boundaries around fictional registry commits."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import sqlite3
from threading import Event, Thread
import tempfile
from pathlib import Path
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_identity.policy import PermissionDenied, IdentityUnavailable
from model_release_assurance.production_identity.tokens import TokenError
from model_release_assurance.production_storage.backend import FixtureObjectStore, StorageError
from model_release_assurance.production_storage.service import FixtureStorageService
from model_release_assurance.production_registry.contracts import FLAGS, RegistryContractError
from model_release_assurance.production_registry.rehearsal import RegistryFixture
from model_release_assurance.production_registry.service import FixtureRegistryService
from model_release_assurance.production_registry.store import RegistryStore, StoreConflict, StoreUnavailable


class RegistryServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-registry-service-")
        self.addCleanup(temporary.cleanup)
        self.fixture = RegistryFixture(Path(temporary.name))
        self.f = self.fixture

    def count(self):
        return self.f.store.inspect(guard=self.f.clock)["receipt_count"]

    def test_real_signed_commit_retry_preserves_original_credential_receipt(self):
        request = self.f.request()
        first = self.f.commit(request)
        self.f.now += 1
        second = self.f.commit(request)
        self.assertEqual(first, second)
        self.assertEqual(self.count(), 1)
        self.assertEqual(first["receipt"]["total_engineering_charge_units"], 1)
        for name, value in FLAGS.items():
            self.assertIs(first["receipt"][name], value)
        self.assertEqual(first, self.f.service.read(self.f.token("auditor"), "case-a", request["request_id"]))

    def test_changed_request_with_same_id_conflicts_even_if_current_heads(self):
        first = self.f.request(); self.f.commit(first)
        changed = self.f.request(request_id=first["request_id"])
        with self.assertRaises(StoreConflict): self.f.commit(changed)
        self.assertEqual(self.count(), 1)

    def test_case_names_share_one_fixed_capacity_and_unknown_projects_fail(self):
        for number in range(8):
            self.f.commit(self.f.request("case-a" if number % 2 else "case-b"))
        with self.assertRaises(StoreConflict): self.f.commit(self.f.request())
        with self.assertRaises((StoreConflict, StoreUnavailable)): self.f.request("case-c")
        state = self.f.service.state(self.f.token("auditor"), "case-b")
        self.assertEqual(state["account"]["total_engineering_charge_units"], 8)
        self.assertEqual(state["case"]["sequence"], 4)
        self.assertEqual(state["account"]["remaining_units"], 0)

    def test_only_current_human_test_operator_can_prepare_or_commit(self):
        request = self.f.request()
        for subject in ("auditor", "steward", "worker"):
            with self.subTest(subject=subject), self.assertRaises(PermissionDenied):
                self.f.service.commit(self.f.token(subject), "case-a", request)
        self.assertEqual(self.count(), 0)

    def test_raw_signed_token_is_required(self):
        request = self.f.request()
        for token in ({"roles": ["test_operator"]}, "unsigned", "", None):
            with self.subTest(token=token), self.assertRaises((TokenError, PermissionDenied, ValueError, TypeError)):
                self.f.service.commit(token, "case-a", request)
        self.assertEqual(self.count(), 0)

    def test_wrong_case_scope_and_different_actor_are_denied(self):
        request = self.f.request()
        actions = [lambda: self.f.service.commit(self.f.token("operator"), "case-b", request),
                   lambda: self.f.service.commit(self.f.token("other"), "case-a", request),
                   lambda: self.f.service.commit(self.f.token("operator", cases=["case-b"]), "case-a", request)]
        for action in actions:
            with self.assertRaises(PermissionDenied): action()
        self.assertEqual(self.count(), 0)

    def test_cross_case_historical_receipt_is_not_exposed(self):
        request = self.f.request(); self.f.commit(request)
        with self.assertRaises(PermissionDenied):
            self.f.service.read(self.f.token("auditor"), "case-b", request["request_id"])

    def test_revoked_role_prevents_exact_retry_without_refund(self):
        request = self.f.request(); self.f.commit(request)
        self.f.update(grants=tuple(g for g in self.f.authority.grants if g.person_id != "person-operator"))
        with self.assertRaises(PermissionDenied): self.f.commit(request)
        self.assertEqual(self.count(), 1)

    def test_revoked_key_prevents_commit_and_historical_read(self):
        request = self.f.request(); token = self.f.token("operator")
        self.f.update(active_key_ids=frozenset({"worker-key"}))
        with self.assertRaises(PermissionDenied): self.f.service.commit(token, "case-a", request)
        self.assertEqual(self.count(), 0)

    def test_authority_mutation_during_byte_read_rolls_back(self):
        request = self.f.request(); original = self.f.storage._store.read
        def revoke(reference):
            data = original(reference)
            self.f.update(grants=tuple(g for g in self.f.authority.grants if g.person_id != "person-operator"))
            return data
        with mock.patch.object(self.f.storage._store, "read", side_effect=revoke):
            with self.assertRaises(PermissionDenied): self.f.commit(request)
        self.assertEqual(self.count(), 0)

    def test_last_revision_clock_sample_cannot_cross_token_deadline(self):
        request = self.f.request(); token = self.f.token("operator")
        original_read = self.f.storage._store.read
        revision = type(self.f.trust).revision
        read_done = [False]
        def read(reference):
            data = original_read(reference); read_done[0] = True; return data
        def current_revision(registry):
            if read_done[0]: self.f.now = 1240
            return revision.fget(registry)
        with mock.patch.object(self.f.storage._store, "read", side_effect=read), mock.patch.object(type(self.f.trust), "revision", new=property(current_revision)):
            with self.assertRaises(PermissionDenied): self.f.service.commit(token, "case-a", request)
        self.assertEqual(self.count(), 0)

    def test_retention_deadline_checked_after_read(self):
        request = self.f.request(); token = self.f.token("operator", expires_at=1249)
        original = self.f.storage._store.read
        def expired(reference):
            data = original(reference); self.f.now = reference.retention_until; return data
        with mock.patch.object(self.f.storage._store, "read", side_effect=expired):
            with self.assertRaises(PermissionDenied): self.f.service.commit(token, "case-a", request)
        self.assertEqual(self.count(), 0)

    def test_replacing_fixture_bytes_is_detected_even_for_duplicate_retry(self):
        request = self.f.request(); self.f.commit(request)
        with mock.patch.object(self.f.storage._store, "read", return_value=b"private data"):
            with self.assertRaises(PermissionDenied): self.f.commit(request)
        self.assertEqual(self.count(), 1)

    def test_object_custody_is_not_established_by_a_well_formed_reference(self):
        request = self.f.request(); request["object_reference"]["object_id"] = uuid.uuid4().hex
        with self.assertRaises(StorageError): self.f.commit(request)
        self.assertEqual(self.count(), 0)

    def test_broker_handover_allows_current_retry_and_fences_old_service(self):
        request = self.f.request(); receipt = self.f.commit(request); old = self.f.service
        self.f.service = FixtureRegistryService(self.f.identity, self.f.storage,
                                               RegistryStore.open(self.f.store.root, self.f.store.store_id))
        self.assertEqual(receipt, self.f.commit(request))
        with self.assertRaises(StoreConflict): old.commit(self.f.token("operator"), "case-a", request)

    def test_restart_without_storage_catalog_only_permits_historical_metadata(self):
        request = self.f.request(); receipt = self.f.commit(request)
        empty = FixtureStorageService(self.f.identity, FixtureObjectStore(self.f.root / "fresh"))
        service = FixtureRegistryService(self.f.identity, empty,
                                        RegistryStore.open(self.f.store.root, self.f.store.store_id))
        self.assertEqual(receipt, service.read(self.f.token("auditor"), "case-a", request["request_id"]))
        with self.assertRaises(StorageError): service.commit(self.f.token("operator"), "case-a", request)
        self.assertEqual(self.count(), 1)

    def test_outbox_requires_current_case_worker_and_exact_owner(self):
        self.f.commit(self.f.request())
        with self.assertRaises(PermissionDenied): self.f.service.claim_outbox(self.f.token("operator"), "case-a")
        self.assertIsNone(self.f.service.claim_outbox(self.f.token("worker"), "case-b"))
        claimed = self.f.service.claim_outbox(self.f.token("worker"), "case-a")
        with self.assertRaises((PermissionDenied, StoreConflict)): self.f.service.acknowledge(self.f.token("worker2"), "case-a", claimed["lease"])
        with self.assertRaises(PermissionDenied): self.f.service.acknowledge(self.f.token("worker"), "case-b", claimed["lease"])
        ack = self.f.service.acknowledge(self.f.token("worker"), "case-a", claimed["lease"])
        self.assertEqual(ack, self.f.service.acknowledge(self.f.token("worker"), "case-a", claimed["lease"]))

    def test_acknowledge_owns_lease_before_authorized_scope_check(self):
        self.f.commit(self.f.request("case-a")); self.f.commit(self.f.request("case-b"))
        a = self.f.service.claim_outbox(self.f.token("worker"), "case-a")
        b = self.f.service.claim_outbox(self.f.token("worker"), "case-b")
        caller_lease = dict(a["lease"])
        owner = self.f.service._owner
        def mutate(context):
            caller_lease.clear(); caller_lease.update(b["lease"])
            return owner(context)
        with mock.patch.object(self.f.service, "_owner", side_effect=mutate):
            result = self.f.service.acknowledge(self.f.token("worker"), "case-a", caller_lease)
        self.assertEqual(result["event_id"], a["event"]["event_id"])
        self.assertEqual(self.f.store.inspect(guard=self.f.clock)["outbox_acknowledged"], 1)

    def test_no_caller_charge_or_policy_or_production_flags_are_accepted(self):
        original = self.f.request()
        for changes in ({"charge_units": 0}, {"policy_sha256": "a"*64}, {"production_authorized": True}):
            with self.subTest(changes=changes), self.assertRaises(RegistryContractError):
                self.f.commit({**original, **changes})
        self.assertEqual(self.count(), 0)

    def test_expiry_while_waiting_for_database_lock_cannot_commit(self):
        request = self.f.request(); token = self.f.token("operator")
        waiting = Event(); errors = []; connect = self.f.store._connect
        @contextmanager
        def observed_connect():
            with connect() as connection:
                connection.set_trace_callback(lambda sql: waiting.set() if sql == "BEGIN IMMEDIATE" else None)
                yield connection
        blocker = sqlite3.connect(self.f.store.root / "registry.sqlite")
        blocker.execute("BEGIN IMMEDIATE")
        def commit():
            try: self.f.service.commit(token, "case-a", request)
            except Exception as error: errors.append(error)
        thread = Thread(target=commit)
        try:
            with mock.patch.object(self.f.store, "_connect", observed_connect):
                thread.start()
                self.assertTrue(waiting.wait(3), "registry did not reach the held database lock")
                self.f.now = 1240
                blocker.rollback()
                thread.join(5)
                self.assertFalse(thread.is_alive())
        finally:
            blocker.rollback(); blocker.close(); thread.join(5)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], PermissionDenied)
        self.assertEqual(self.count(), 0)

    def test_response_expiry_after_commit_is_unknown_outcome_then_exact_retry(self):
        request = self.f.request(); token = self.f.token("operator", expires_at=1010)
        original = self.f.store.commit
        def committed_then_response_expires(*args, **kwargs):
            result = original(*args, **kwargs); self.f.now = 1010; return result
        with mock.patch.object(self.f.store, "commit", side_effect=committed_then_response_expires):
            with self.assertRaises(PermissionDenied): self.f.service.commit(token, "case-a", request)
        self.assertEqual(self.count(), 1)
        prior = self.f.service.read(self.f.token("auditor"), "case-a", request["request_id"])
        self.assertEqual(prior, self.f.commit(request))
        self.assertEqual(self.count(), 1)

    def test_metadata_only_service_never_exposes_fixture_bytes(self):
        request = self.f.request(); receipt = self.f.commit(request)
        self.assertNotIn("object_reference", receipt["receipt"])
        self.assertNotIn("raw_token", str(receipt))
        self.assertNotIn("PRIVATE KEY", str(receipt))


if __name__ == "__main__": unittest.main()
