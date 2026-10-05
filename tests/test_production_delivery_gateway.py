"""Actual reviewed candidates, irreversible admissions, and final current guards."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_delivery.rehearsal import DeliveryFixture
from model_release_assurance.production_delivery.gateway import FixtureDeliveryGateway
from model_release_assurance.production_delivery.authorization import RecipientRecord
from model_release_assurance.production_delivery.contracts import FLAGS, DeliveryError, MAX_CHUNK_BYTES
from model_release_assurance.production_delivery.store import DeliveryStore, StoreConflict, StoreUnavailable
from model_release_assurance.production_identity.policy import PermissionDenied, IdentityUnavailable
from model_release_assurance.production_review.contracts import ReviewError
from model_release_assurance.production_review.rehearsal import ISSUER
from model_release_assurance.production_evidence.verifier import LocalEvidenceVerifier

DENIED = (PermissionDenied, IdentityUnavailable, DeliveryError, StoreUnavailable, ReviewError)


def fresh_transfer(fixture, *, activation_id=None):
    if activation_id is None: activation_id, _ = fixture.activate()
    recipient = fixture.token("recipient")
    grant_id, grant = fixture.grant(activation_id, recipient)
    return recipient, activation_id, grant_id, grant["payload"]["transfer_id"]


def emit(fixture, transfer, *, offset=0, length=128, writer=None, **kwargs):
    token, activation, grant, transfer_id = transfer
    return fixture.gateway.deliver_chunk(token, "case-a", activation, grant, transfer_id, offset, length,
        writer=(lambda raw: len(raw)) if writer is None else writer, **kwargs)


def raw_state(fixture):
    return fixture.store.get("case-a", expected_pin=fixture.gateway.required_pin,
                             guard=fixture.review_fixture.clock)


class DeliveryGatewayActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="mra-delivery-gateway-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.f = DeliveryFixture(Path(cls.temporary.name))
        cls.f.prepare()
        cls.candidate = (cls.f.output / "native/candidate.json").read_bytes()

    def test_exact_candidate_transfer_and_fresh_range_retry_have_distinct_permanent_admissions(self):
        transfer = fresh_transfer(self.f)
        collected = []
        receipts = []
        for offset in (0, *range(128, len(self.candidate), MAX_CHUNK_BYTES)):
            receipt = emit(self.f, transfer, offset=offset, length=min(128 if offset == 0 else MAX_CHUNK_BYTES, len(self.candidate)-offset),
                writer=lambda raw: (collected.append(raw), len(raw))[1])
            receipts.append(receipt)
        self.assertEqual(b"".join(collected), self.candidate)
        self.assertEqual(hashlib.sha256(b"".join(collected)).hexdigest(),
                         raw_state(self.f)["activations"][transfer[1]]["payload"]["artifact_sha256"])
        retry = emit(self.f, transfer, length=128)
        self.assertNotIn(retry["admission"]["request_id"], {r["admission"]["request_id"] for r in receipts})
        self.assertEqual(raw_state(self.f)["grants"][transfer[2]]["attempted_bytes"], len(self.candidate)+128)
        for receipt in [*receipts, retry]:
            self.assertIs(receipt["recipient_receipt_verified"], False)
            self.assertTrue(receipt["observation_recorded"])
            for key, value in FLAGS.items(): self.assertIs(receipt[key], value)
        with self.assertRaises(StoreConflict):
            emit(self.f, transfer, length=128, request_id=retry["admission"]["request_id"], chunk_id=uuid.uuid4().hex)
        with self.assertRaises(StoreConflict): emit(self.f, transfer, offset=1, length=255)

    def test_durable_admission_then_checkpoint_then_writer_order_is_observed(self):
        transfer = fresh_transfer(self.f)
        request_id = uuid.uuid4().hex
        seen = []
        original = self.f.gateway._sink
        def checkpoint(pin):
            state = self.f.store.get("case-a", expected_pin=pin, guard=self.f.review_fixture.clock)
            if request_id in state["admissions"]:
                seen.append("committed")
            original(pin)
            if request_id in state["admissions"]:
                self.assertEqual(self.f.checkpoint_sink.read(), pin)
                seen.append("checkpoint")
        def writer(raw):
            self.assertEqual(seen[:2], ["committed", "checkpoint"])
            self.assertIn(request_id, raw_state(self.f)["admissions"])
            seen.append("writer")
            return len(raw)
        with mock.patch.object(self.f.gateway, "_sink", side_effect=checkpoint):
            receipt = emit(self.f, transfer, request_id=request_id, writer=writer)
        self.assertEqual(seen[:3], ["committed", "checkpoint", "writer"])
        self.assertEqual(receipt["bytes_written"], 128)

    def test_sink_failure_emits_nothing_and_never_refunds_admission_or_known_floor(self):
        transfer = fresh_transfer(self.f)
        request_id, chunk_id = uuid.uuid4().hex, uuid.uuid4().hex
        old = self.f.gateway.required_pin
        writer = mock.Mock(return_value=128)
        sink = self.f.gateway._sink
        def fail_new_pin(pin):
            if pin["sequence"] > old["sequence"]: raise OSError("fixture sink outage")
            sink(pin)
        with mock.patch.object(self.f.gateway, "_sink", side_effect=fail_new_pin):
            with self.assertRaises(OSError): emit(self.f, transfer, request_id=request_id, chunk_id=chunk_id, writer=writer)
        writer.assert_not_called()
        self.assertGreater(self.f.gateway.required_pin["sequence"], old["sequence"])
        state = raw_state(self.f)
        self.assertIn(request_id, state["admissions"])
        self.assertEqual(state["grants"][transfer[2]]["attempted_bytes"], 128)
        self.assertNotIn(request_id, state["observations"])
        with self.assertRaises(StoreConflict): emit(self.f, transfer, request_id=request_id, chunk_id=chunk_id, writer=writer)
        writer.assert_not_called()
        self.assertEqual(self.f.checkpoint_sink.read(), self.f.gateway.required_pin)

    def test_partial_unknown_invalid_and_zero_writer_extents_remain_honest(self):
        transfer = fresh_transfer(self.f)
        def partial_exception(raw):
            escaped.append(raw[:1]); raise OSError("write stopped after one byte")
        escaped = []
        variants = [(lambda raw: 1, "interrupted", 1, True, True),
                    (lambda raw: 0, "interrupted", 0, True, False),
                    (partial_exception, "failed", None, False, True),
                    (lambda raw: None, "failed", None, False, True),
                    (lambda raw: True, "failed", None, False, True),
                    (lambda raw: len(raw)+1, "failed", None, False, True)]
        for writer, status, extent, known, possible in variants:
            with self.subTest(status=status, extent=extent, known=known):
                receipt = emit(self.f, transfer, writer=writer)
                self.assertEqual(receipt["status"], status)
                self.assertEqual(receipt["bytes_written"], extent)
                self.assertIs(receipt["write_extent_known"], known)
                self.assertIs(receipt["disclosure_may_have_occurred"], possible)
                self.assertIs(receipt["recipient_receipt_verified"], False)
                self.assertIn(receipt["admission"]["request_id"], raw_state(self.f)["observations"])
        self.assertEqual(escaped, [self.candidate[:1]])
        self.assertEqual(raw_state(self.f)["grants"][transfer[2]]["attempted_bytes"], 128*len(variants))

    def test_suspend_resume_grant_revoke_and_activation_revoke_are_permanent(self):
        transfer = fresh_transfer(self.f)
        first = emit(self.f, transfer)
        token = self.f.token("releaser")
        self.f.gateway.suspend(token, "case-a", transfer[1])
        writer = mock.Mock(return_value=128)
        with self.assertRaises(StoreConflict): emit(self.f, transfer, offset=128, writer=writer)
        writer.assert_not_called()
        self.f.gateway.resume(token, "case-a", transfer[1])
        resumed = emit(self.f, transfer, offset=128)
        self.assertNotEqual(first["admission"]["request_id"], resumed["admission"]["request_id"])
        self.f.gateway.revoke_grant(token, "case-a", transfer[2])
        with self.assertRaises(StoreConflict): emit(self.f, transfer, offset=256, writer=writer)
        self.f.gateway.revoke(token, "case-a", transfer[1])
        with self.assertRaises(StoreConflict): self.f.gateway.resume(token, "case-a", transfer[1])
        with self.assertRaises(StoreConflict): self.f.grant(transfer[1], transfer[0])
        writer.assert_not_called()

    def test_recipient_refresh_wrong_actor_wrong_case_and_wrong_transfer_emit_nothing(self):
        transfer = fresh_transfer(self.f)
        writer = mock.Mock(return_value=128)
        variants = [(self.f.token("recipient"), *transfer[1:]),
                    (self.f.token("auditor"), *transfer[1:]),
                    (transfer[0], transfer[1], transfer[2], uuid.uuid4().hex)]
        for bad in variants:
            with self.subTest(bad_token_changed=bad[0]!=transfer[0]), self.assertRaises(DENIED):
                emit(self.f, bad, writer=writer)
        with self.assertRaises(DENIED):
            self.f.gateway.deliver_chunk(transfer[0], "case-b", *transfer[1:], 0, 128, writer=writer)
        writer.assert_not_called()
        refreshed = self.f.token("recipient")
        grant, record = self.f.grant(transfer[1], refreshed)
        self.assertEqual(emit(self.f, (refreshed, transfer[1], grant, record["payload"]["transfer_id"]))["bytes_written"], 128)

    def test_source_policy_and_candidate_integrity_are_rechecked_before_output(self):
        transfer = fresh_transfer(self.f)
        writer = mock.Mock(return_value=128)
        candidate = self.f.output / "native/candidate.json"
        saved = candidate.read_bytes()
        try:
            candidate.write_bytes(saved+b" ")
            with self.assertRaises((ValueError, *DENIED)): emit(self.f, transfer, writer=writer)
        finally: candidate.write_bytes(saved)
        with mock.patch("model_release_assurance.production_review.service.workflow_sha256", return_value="f"*64):
            with self.assertRaises(DENIED): emit(self.f, transfer, writer=writer)
        writer.assert_not_called()
        self.assertEqual(emit(self.f, transfer)["bytes_written"], 128)

    def test_current_policy_disabling_and_authority_outage_cannot_use_retained_review(self):
        transfer = fresh_transfer(self.f)
        writer = mock.Mock(return_value=128)
        state = self.f.identity._authority
        principals = dict(state.principals)
        principals[(ISSUER, "policy")] = replace(principals[(ISSUER, "policy")], enabled=False)
        # Inject current-provider responses without manufacturing a durable refresh.
        for unavailable in (replace(state, principals=principals), replace(state, available=False)):
            with mock.patch.object(self.f.identity, "_authority", unavailable):
                with self.assertRaises(DENIED): emit(self.f, transfer, writer=writer)
        writer.assert_not_called()

    def test_metadata_store_and_direct_storage_service_cannot_supply_bytes(self):
        from model_release_assurance.production_storage.backend import FixtureObjectStore
        transfer = fresh_transfer(self.f)
        state = raw_state(self.f)
        self.assertNotIn("artifacts", state)
        self.assertNotIn("bytes", state)
        self.assertNotIn(self.candidate.decode(), str(state))
        with self.assertRaises(DeliveryError):
            self.f.store.apply("case-a", "admit", {}, {}, expected_pin=self.f.gateway.required_pin,
                expected_head_sha256=state["head_sha256"], guard=self.f.review_fixture.clock)
        direct = FixtureObjectStore(self.f.root / "old-object-boundary")
        with self.assertRaises(DeliveryError):
            FixtureDeliveryGateway(self.f.bridge, direct, [], expected_pin=self.f.gateway.required_pin,
                                   checkpoint_sink=self.f.checkpoint_sink)
        with self.assertRaises(TypeError):
            self.f.gateway.activate(self.f.token("releaser"), "case-a", self.f.campaign_id,
                profile="local_public_fixture", artifact_path=self.f.output / "native/candidate.json")
        with self.assertRaises(DeliveryError):
            self.f.gateway.activate(self.f.token("releaser"), "case-a", self.f.campaign_id)

    def test_admission_waiting_for_actual_sqlite_lock_rechecks_exclusive_deadline(self):
        activation, _ = self.f.activate()
        recipient = self.f.token("recipient")
        before = set(raw_state(self.f)["grants"])
        state = self.f.gateway.grant(self.f.token("releaser"), "case-a", activation, recipient, ttl_seconds=1)
        grant = (set(state["grants"])-before).pop()
        transfer = (recipient, activation, grant, state["grants"][grant]["payload"]["transfer_id"])
        deadline = state["grants"][grant]["payload"]["expires_at"]
        original = self.f.store._take_chunk
        def blocked(*args, **kwargs):
            connection = sqlite3.connect(self.f.store.root / "delivery.sqlite", isolation_level=None, check_same_thread=False)
            connection.execute("BEGIN IMMEDIATE")
            ready = threading.Event()
            connect = self.f.store._connect
            @contextmanager
            def waiting():
                with connect() as value:
                    ready.set()
                    yield value
            def release():
                if not ready.wait(2): return
                time.sleep(.05)
                self.f.now = deadline
                connection.commit()
            thread = threading.Thread(target=release)
            thread.start()
            try:
                with mock.patch.object(self.f.store, "_connect", waiting): return original(*args, **kwargs)
            finally:
                thread.join(3)
                connection.close()
        writer = mock.Mock(return_value=128)
        with mock.patch.object(self.f.store, "_take_chunk", side_effect=blocked):
            with self.assertRaises(DENIED): emit(self.f, transfer, writer=writer)
        writer.assert_not_called()
        self.assertEqual(raw_state(self.f)["grants"][grant]["attempted_bytes"], 0)


class DeliveryGatewayFinalGuardTests(unittest.TestCase):
    def fixture(self, *, operator_expiry=None, evidence_ttl=None):
        temporary = tempfile.TemporaryDirectory(prefix="mra-delivery-final-")
        self.addCleanup(temporary.cleanup)
        f = DeliveryFixture(Path(temporary.name))
        token = f.token
        def issue(subject, **kwargs):
            if subject == "operator" and operator_expiry is not None: kwargs["expires_at"] = operator_expiry
            return token(subject, **kwargs)
        original_issue = LocalEvidenceVerifier.issue
        def challenge(verifier, *args, **kwargs):
            if evidence_ttl is not None: kwargs["ttl_seconds"] = evidence_ttl
            return original_issue(verifier, *args, **kwargs)
        with mock.patch.object(f, "token", side_effect=issue), mock.patch.object(LocalEvidenceVerifier, "issue", challenge): f.prepare()
        return f

    def test_original_operator_expires_after_expensive_final_frame_before_shared_time_check(self):
        f = self.fixture(operator_expiry=1005)
        self.final_time_expiry(f, operator=True)

    def test_signed_evidence_expires_after_expensive_final_frame_before_shared_time_check(self):
        f = self.fixture(evidence_ttl=5)
        self.assertEqual(f.review._evidence_deadlines[f.campaign_id], (1000, 1005))
        self.final_time_expiry(f, operator=False)

    def final_time_expiry(self, f, *, operator):
        transfer = fresh_transfer(f)
        request_id = uuid.uuid4().hex
        sink, frame = f.gateway._sink, f.bridge.recheck_frame
        armed = False
        final_shared = []
        def checkpoint(pin):
            nonlocal armed
            sink(pin)
            if request_id in raw_state(f)["admissions"]: armed = True
        def expensive(context, captured):
            result = frame(context, captured)
            if armed: f.now = 1005
            return result
        recheck = f.gateway.authorization.recheck_many
        def current(contexts, *, review_contexts=()):
            if armed:
                final_shared.append([proof.identity.subject for proof in review_contexts])
                self.assertEqual(f.now, 1005)
            return recheck(contexts, review_contexts=review_contexts)
        writer = mock.Mock(return_value=128)
        with mock.patch.object(f.gateway, "_sink", side_effect=checkpoint), \
             mock.patch.object(f.bridge, "recheck_frame", side_effect=expensive), \
             mock.patch.object(f.gateway.authorization, "recheck_many", side_effect=current):
            with self.assertRaises(PermissionDenied): emit(f, transfer, request_id=request_id, writer=writer)
        writer.assert_not_called()
        self.assertTrue(final_shared)
        self.assertIn("operator", final_shared[-1])
        self.assertIn("policy", final_shared[-1])
        self.assertIn(request_id, raw_state(f)["admissions"])
        self.assertEqual(raw_state(f)["grants"][transfer[2]]["attempted_bytes"], 128)
        self.assertNotIn(request_id, raw_state(f)["observations"])
        self.assertEqual(f.checkpoint_sink.read(), f.gateway.required_pin)

    def test_current_recipient_disable_during_checkpoint_emits_nothing_after_durable_admission(self):
        f = self.fixture()
        transfer = fresh_transfer(f)
        request_id = uuid.uuid4().hex
        sink = f.gateway._sink
        disabled = False
        def checkpoint(pin):
            nonlocal disabled
            sink(pin)
            if not disabled and request_id in raw_state(f)["admissions"]:
                disabled = True
                state = f.review_fixture.authority
                principals = dict(state.principals)
                principals[(ISSUER, "recipient")] = replace(principals[(ISSUER, "recipient")], enabled=False)
                f.review_fixture.update(principals=principals)
        writer = mock.Mock(return_value=128)
        with mock.patch.object(f.gateway, "_sink", side_effect=checkpoint):
            with self.assertRaises(PermissionDenied): emit(f, transfer, request_id=request_id, writer=writer)
        writer.assert_not_called()
        self.assertTrue(disabled)
        self.assertIn(request_id, raw_state(f)["admissions"])
        self.assertEqual(raw_state(f)["grants"][transfer[2]]["attempted_bytes"], 128)


if __name__ == "__main__": unittest.main()
