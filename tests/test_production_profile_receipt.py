"""Receipt crypto/custody boundaries and real pure SQLite/signature validators.

Cheap seal tests mock only semantic replay over clearly non-model placeholder
files. Actual native/external end-to-end integration belongs to workflow tests.
"""
from dataclasses import asdict
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives.asymmetric import ed25519
from model_release_assurance.production_profile import receipt as module
from model_release_assurance.production_delivery.store import DeliveryStore
from model_release_assurance.production_registration.store import RegistrationStore
from model_release_assurance.production_evidence.contracts import execution_digest, digest, OBSERVATIONS
from model_release_assurance.production_evidence.signing import MemoryFixtureEvidenceSigner
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile

JOURNAL_PIN = {"schema": "mra-public-profile-journal-pin/v1", "store_id": "a"*32,
               "sequence": 7, "head_sha256": "b"*64}
DELIVERY_PIN = {"schema": "mra-fixture-delivery-pin/v1", "store_id": "c"*32,
                "sequence": 2, "head_sha256": "d"*64}
REPLAY = {"schema": "unit-test-mocked-semantic-result/v1", "fixture_only": True}


class ReceiptEnvelopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-profile-receipt-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in module.FILE_BOUNDS:
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"" if name.endswith(".log") else b"unit-fixture-placeholder")
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.capture = mock.patch.object(module, "_semantic_capture", return_value=copy.deepcopy(REPLAY)).start()
        self.addCleanup(mock.patch.stopall)

    def seal(self):
        with mock.patch.object(module.ed25519.Ed25519PrivateKey, "generate", return_value=self.private):
            return module.seal_receipt(self.root, journal_pin=JOURNAL_PIN, delivery_pin=DELIVERY_PIN)

    def verify(self, pins):
        return module.verify_receipt(self.root, expected_receipt_sha256=pins["receipt_sha256"], expected_key_sha256=pins["key_sha256"])

    def rewrite_receipt(self, pins, transform):
        path = self.root/"receipt.json"
        value = json.loads(path.read_bytes()); transform(value)
        raw = module.numeric_bytes(value)
        path.write_bytes(raw)
        (self.root/"signature.bin").write_bytes(self.private.sign(module.DOMAIN+raw))
        return {**pins, "receipt_sha256": hashlib.sha256(raw).hexdigest()}

    def test_round_trip_external_pins_read_only_outputs_and_all_non_authority_flags(self):
        pins = self.seal()
        self.assertEqual(set(pins), {"receipt_sha256", "key_sha256"})
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = self.verify(pins)
        self.assertEqual(result["status"], "historical_fixture_replay_verified")
        self.assertEqual(result["historical_replay"], REPLAY)
        for name, value in module.FLAGS.items(): self.assertIs(result[name], value)
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue((self.root/"public-key.pem").read_bytes().startswith(b"-----BEGIN PUBLIC KEY-----"))
        self.assertFalse(any(b"PRIVATE KEY" in raw for raw in after.values()))

    def test_both_external_pins_are_mandatory_and_wrong_receipt_key_or_signature_fails(self):
        pins = self.seal()
        with self.assertRaises(TypeError): module.verify_receipt(self.root)
        for key in pins:
            with self.subTest(key=key), self.assertRaises(module.ReceiptError): self.verify({**pins, key: "0"*64})
        (self.root/"signature.bin").write_bytes(b"0"*64)
        with self.assertRaises(module.ReceiptError): self.verify(pins)

    def test_schema_and_false_flags_still_required_under_a_valid_signature(self):
        pins = self.seal()
        mutations = (lambda value: value.update(extra=False), lambda value: value.update(production_authorized=True),
                     lambda value: value.update(current_authorization_checked=0), lambda value: value.update(profile_id="acs"))
        original = (self.root/"receipt.json").read_bytes()
        signature = (self.root/"signature.bin").read_bytes()
        for change in mutations:
            (self.root/"receipt.json").write_bytes(original); (self.root/"signature.bin").write_bytes(signature)
            changed = self.rewrite_receipt(pins, change)
            with self.subTest(change=change), self.assertRaises(module.ReceiptError): self.verify(changed)

    def test_byte_tamper_missing_files_unknown_files_and_manifest_type_alias_are_refused(self):
        pins = self.seal(); path = self.root/"combined-binding.json"; original = path.read_bytes()
        path.write_bytes(original+b" ")
        with self.assertRaises(module.ReceiptError): self.verify(pins)
        path.write_bytes(original)
        path.unlink()
        with self.assertRaises(module.ReceiptError): self.verify(pins)
        path.write_bytes(original)
        extra = self.root/"external/extra.json"; extra.write_bytes(b"{}")
        with self.assertRaises(module.ReceiptError): self.verify(pins)
        extra.unlink()
        changed = self.rewrite_receipt(pins, lambda value: value["files"]["combined-binding.json"].update(size_bytes=True))
        with self.assertRaises(module.ReceiptError): self.verify(changed)

    def test_replayed_outcome_is_recomputed_instead_of_trusting_the_signed_summary(self):
        pins = self.seal()
        self.capture.return_value = {**REPLAY, "new_result": True}
        with self.assertRaises(module.ReceiptError): self.verify(pins)

    def test_no_overwrite_and_partial_seal_keeps_failure_artifacts(self):
        pins = self.seal()
        original = (self.root/"receipt.json").read_bytes()
        with self.assertRaises(module.ReceiptError): self.seal()
        self.assertEqual((self.root/"receipt.json").read_bytes(), original)
        self.assertEqual(self.verify(pins)["status"], "historical_fixture_replay_verified")

    def test_interrupted_exclusive_seal_is_not_repaired_or_overwritten(self):
        write = module._write
        def failing(path, raw):
            if path.name == "public-key.pem": raise OSError("fixture write failure")
            write(path, raw)
        with mock.patch.object(module, "_write", side_effect=failing):
            with self.assertRaises(module.ReceiptError): self.seal()
        self.assertTrue((self.root/"receipt.json").exists())
        self.assertFalse((self.root/"signature.bin").exists())
        with self.assertRaises(module.ReceiptError): self.seal()

    def test_change_during_semantic_work_or_signature_verification_is_rejected(self):
        path = self.root/"combined-binding.json"
        original = path.read_bytes()
        def alter(*args, **kwargs):
            path.write_bytes(original+b"changed")
            return REPLAY
        with mock.patch.object(module, "_semantic_capture", side_effect=alter):
            with self.assertRaises(module.ReceiptError): self.seal()
        self.assertFalse((self.root/"receipt.json").exists())
        path.write_bytes(original); pins = self.seal()
        with mock.patch.object(module, "_semantic_capture", side_effect=alter):
            with self.assertRaises(module.ReceiptError): self.verify(pins)

    def test_unknown_directory_hardlinks_and_aggregate_or_individual_bounds_refuse_sealing(self):
        extra = self.root/"unapproved"; extra.mkdir()
        with self.assertRaises(module.ReceiptError): self.seal()
        extra.rmdir()
        path = self.root/"combined-binding.json"
        link = self.root/"source.json"; os.link(path, link)
        with self.assertRaises(module.ReceiptError): self.seal()
        link.unlink()
        with mock.patch.object(module, "MAX_TOTAL_BYTES", 1):
            with self.assertRaises(module.ReceiptError): self.seal()
        path.write_bytes(b"x"*65537)
        with self.assertRaises(module.ReceiptError): self.seal()

    def test_exact_empty_upstream_case_directories_allow_seal_and_replay(self):
        for case in ("target", "positive", "null"):
            (self.root/"external/worker"/case/"shadow_models").mkdir(parents=True)
        pins = self.seal()
        self.assertEqual(self.verify(pins)["status"], "historical_fixture_replay_verified")
        receipt = json.loads((self.root/"receipt.json").read_bytes())
        self.assertFalse(any("shadow_models" in name for name in receipt["files"]))

    def test_upstream_case_directories_reject_files_and_unknown_descendants(self):
        for case in ("target", "positive", "null"):
            (self.root/"external/worker"/case/"shadow_models").mkdir(parents=True)
        pins = self.seal()
        for case in ("target", "positive", "null"):
            for relative in ("report.json", "shadow_models/model.pkl"):
                path = self.root/"external/worker"/case/relative
                path.write_bytes(b"unexpected fixture artifact")
                with self.subTest(case=case, relative=relative), self.assertRaises(module.ReceiptError):
                    self.verify(pins)
                path.unlink()
            extra = self.root/"external/worker"/case/"shadow_models/unexpected"
            extra.mkdir()
            with self.subTest(case=case, directory=True), self.assertRaises(module.ReceiptError):
                self.verify(pins)
            extra.rmdir()
        self.assertEqual(self.verify(pins)["status"], "historical_fixture_replay_verified")

    def test_explicit_later_diagnostics_cannot_change_historical_result(self):
        pins = self.seal()
        for name in ("result.json", "source.json"):
            (self.root/name).write_bytes(b'{"production_authorized":true,"status":"made_up"}')
        self.assertFalse(self.verify(pins)["production_authorized"])
        (self.root/"source-manifest.json").write_bytes(b"{}")
        with self.assertRaises(module.ReceiptError): self.verify(pins)

    def test_mutating_caller_pins_during_capture_does_not_change_signed_pin(self):
        pins = copy.deepcopy(JOURNAL_PIN)
        def mutate(*args, **kwargs):
            pins["head_sha256"] = "e"*64
            return REPLAY
        with mock.patch.object(module, "_semantic_capture", side_effect=mutate):
            result = module.seal_receipt(self.root, journal_pin=pins, delivery_pin=DELIVERY_PIN)
        receipt = json.loads((self.root/"receipt.json").read_bytes())
        self.assertEqual(receipt["journal_pin"], JOURNAL_PIN)
        self.verify(result)


class ReceiptPureReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-profile-historical-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_real_delivery_and_registration_sqlite_replay_never_changes_source_database(self):
        cases = [{"case_id": "case-a", "agency_id": "agency", "project_id": "project", "submitter_person_id": "owner"}]
        delivery = DeliveryStore.create(self.root/"delivery", cases=cases, guard=lambda: 1000)
        registration = RegistrationStore.create(self.root/"registration")
        for path, source, cls in ((delivery.root/"delivery.sqlite", module.deliveries, DeliveryStore),
                                   (registration.root/"registrations.sqlite", module.registrations, RegistrationStore)):
            raw = path.read_bytes()
            identity, state, events = module._store_state(raw, source, cls)
            self.assertEqual(identity, delivery.store_id if cls is DeliveryStore else registration.store_id)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(state["count"], len(events))

    def test_sqlite_extra_schema_or_tampered_hash_chain_fails(self):
        store = DeliveryStore.create(self.root/"delivery", cases=[{"case_id": "case-a", "agency_id": "agency",
            "project_id": "project", "submitter_person_id": "owner"}], guard=lambda: 1000)
        raw = (store.root/"delivery.sqlite").read_bytes()
        with sqlite3.connect(":memory:") as connection:
            connection.deserialize(raw)
            connection.execute("CREATE TABLE extra(value TEXT)")
            changed = connection.serialize()
        with self.assertRaises(module.ReceiptError): module._store_state(changed, module.deliveries, DeliveryStore)
        with sqlite3.connect(":memory:") as connection:
            connection.deserialize(raw)
            connection.execute("UPDATE events SET event_sha256=?", ("0"*64,))
            connection.commit(); changed = connection.serialize()
        with self.assertRaises((module.ReceiptError, module.deliveries.StoreUnavailable)):
            module._store_state(changed, module.deliveries, DeliveryStore)

    def test_delivery_summary_cannot_hide_other_grants_admissions_or_unknown_extents(self):
        # Unit state for the cross-summary join only; independent real store
        # schema/transition replay is exercised above and by workflow integration.
        from model_release_assurance.production_profile.contracts import FLAGS
        from model_release_assurance.production_delivery.contracts import digest as delivery_digest
        aid, full, partial, live = (format(i, "032x") for i in range(1, 5))
        candidate = b"public-fixture-bytes"*20
        plan = {"campaign_id": "5"*32, "agency_id": "agency", "project_id": "project", "case_id": "case-a", "recipient_id": "recipient"}
        campaign = {"policy_sha256": "a"*64, "binding_sha256": "b"*64, "approval": {"sha256": "c"*64}}
        activation = {"state": "revoked", "payload": {**plan, "artifact_sha256": module._sha(candidate), "artifact_size": len(candidate),
            "policy_sha256": campaign["policy_sha256"], "binding_sha256": campaign["binding_sha256"], "approval_sha256": campaign["approval"]["sha256"]}}
        grants = {full: {"payload": {"activation_id": aid, "transfer_id": "6"*32}, "attempted_bytes": len(candidate), "next_offset": len(candidate)},
            partial: {"payload": {"expires_at": 1006}, "revoked": False, "attempted_bytes": 128},
            live: {"payload": {}, "revoked": True, "attempted_bytes": 256}}
        admissions, observations, chunks = {}, {}, []
        for index, (grant, offset, length) in enumerate(((full, 0, 128), (full, 128, len(candidate)-128),
                (partial, 0, 128), (live, 0, 128), (live, 128, 128)), 10):
            rid = format(index, "032x")
            row = {"request_id": rid, "chunk_id": format(index+20, "032x"), "offset": offset, "length": length,
                "chunk_sha256": module._sha(candidate[offset:offset+length]), "activation_id": aid, "grant_id": grant}
            admissions[rid] = row
            observations[rid] = {"payload": {"status": "interrupted" if grant==partial else "returned",
                "bytes_written": 1 if grant==partial else length, "write_extent_known": True, "recipient_receipt_verified": False}}
            if grant == full:
                chunks.append({**{key: row[key] for key in ("request_id", "chunk_id", "offset", "length", "chunk_sha256")},
                    "bytes_written": length, "status": "returned", "write_extent_known": True, "observation_recorded": True})
        partial_id, resumed = format(12, "032x"), format(14, "032x")
        summary = {"schema": "mra-public-profile-delivery-summary/v1", "activation_id": aid, "grant_id": full,
            "transfer_id": "6"*32, "artifact_sha256": module._sha(candidate), "artifact_size": len(candidate),
            "completed_chunks": chunks, "collected_sha256": module._sha(candidate), "partial_request_id": partial_id,
            "partial_attempted_bytes": 128, "partial_bytes_written": 1, **FLAGS}
        lifecycle = {"schema": "mra-public-profile-lifecycle/v1", "checks": {key: True for key in
            ("suspension_denied", "resumed_fresh_admission", "grant_revocation_denied", "activation_revocation_permanent", "expiry_denied")},
            "activation_id": aid, "live_grant_id": live, "partial_grant_id": partial, "expiry_activation_id": aid,
            "expiry_grant_id": partial, "resumed_request_id": resumed, "expiry_at": 1006, **FLAGS}
        pin = {"schema": "mra-fixture-delivery-pin/v1", "store_id": "9"*32, "sequence": 4, "head_sha256": "f"*64}
        case = {"activations": {aid: activation}, "grants": grants, "admissions": admissions, "observations": observations}
        state = {"cases": {"case-a": case}, "artifacts": {aid: candidate}, "activation_ids": {aid},
            "grant_ids": {full, partial, live}, "request_ids": set(admissions), "clock": 1006,
            "count": 4, "head": "f"*64, "pins": {4: "f"*64}}
        events = [{"operation": operation, "sequence": sequence, "payload": {"activation_id": aid}}
                  for sequence, operation in ((1, "suspend"), (2, "resume"), (4, "revoke"))]
        events.insert(2, {"operation": "admit", "sequence": 3, "payload": {"request_id": resumed}})
        blobs = {"fixture/training/native/candidate.json": candidate, "delivery-summary.json": module.numeric_bytes(summary),
            "lifecycle.json": module.numeric_bytes(lifecycle), "fixture/checkpoints/4.json": module.numeric_bytes(pin)}
        self.assertEqual(module._delivery(blobs, state, events, plan, campaign, pin)[0], summary)
        for mutation in (lambda value: value["activation_ids"].add("7"*32),
                         lambda value: value["grant_ids"].add("7"*32),
                         lambda value: value["request_ids"].add("7"*32),
                         lambda value: value["cases"]["case-a"]["observations"].pop(resumed)):
            changed = copy.deepcopy(state); mutation(changed)
            with self.assertRaises(module.ReceiptError): module._delivery(blobs, changed, events, plan, campaign, pin)
        changed = copy.deepcopy(state)
        changed["cases"]["case-a"]["observations"][partial_id]["payload"].update(write_extent_known=False, bytes_written=None)
        with self.assertRaises(module.ReceiptError): module._delivery(blobs, changed, events, plan, campaign, pin)

    def signed_statement(self):
        now = [1000]
        registry = FixtureTrustRegistry(now=lambda: now[0], fresh_until=1100)
        profile = TrustProfile("agency", "public_fixture", "https://fixture.invalid", "urn:mra:fixture", "worker_evidence")
        signer = MemoryFixtureEvidenceSigner(profile, "worker", "key", 999, 1300)
        registry.enroll(signer.registration, expected_revision=registry.revision)
        context = {"schema": "mra-execution-context/v1", "environment": "public_fixture", "operation": "retained_native_replay",
            "agency_id": "agency", "project_id": "project", "case_id": "case-a", "worker_id": "worker",
            "job_id": "1"*32, "attempt_id": "2"*32, "fence": 1, "image_sha256": None,
            **{name: "a"*64 for name in ("job_sha256", "source_sha256", "policy_sha256", "plan_sha256", "adapter_sha256", "runtime_sha256")}}
        challenge = {"schema": "mra-evidence-challenge/v1", "ledger_id": "3"*32, "nonce": "4"*64,
            "context_sha256": digest(context), "execution_sha256": execution_digest(context), "issued_at": 1000, "expires_at": 1005}
        statement = {"schema": "mra-worker-evidence/v1", "context": context, "challenge": challenge,
            "artifacts": {name: {"sha256": "a"*64, "size_bytes": 1} for name in module.NATIVE_NAMES},
            "observations": dict(OBSERVATIONS), "issued_at": 1000, "expires_at": 1005}
        key = signer.registration
        public = {"schema": "mra-public-profile-evidence-key/v1", "key_id": key.key_id, "profile": asdict(profile),
            "owner_id": key.owner_id, "not_before": key.not_before, "not_after": key.not_after,
            "public_key_pem": key.public_key_pem.decode("ascii"), "fingerprint": key.fingerprint}
        return signer.sign(statement, registry), statement, public, registry, now

    def test_expired_revoked_native_signature_is_only_historical_crypto_not_current_trust(self):
        raw, statement, public, registry, now = self.signed_statement()
        registry.revoke("key", expected_revision=registry.revision)
        now[0] = 1400
        with mock.patch.object(registry, "signing_key", side_effect=AssertionError("must not backdate current trust")):
            self.assertEqual(module._historical_signature(raw, public), statement)
        self.assertIs(module.FLAGS["current_authorization_checked"], False)

    def test_historical_signature_rejects_tamper_wrong_owner_key_profile_and_window(self):
        raw, statement, public, registry, now = self.signed_statement()
        for change in ({"owner_id": "other"}, {"fingerprint": "0"*64}, {"not_after": 1004},
                       {"profile": {**public["profile"], "purpose": "access_token"}}, {"extra": None}):
            with self.subTest(change=change), self.assertRaises(Exception): module._historical_signature(raw, {**public, **change})
        mutated = json.loads(raw); mutated["statement"]["context"]["source_sha256"] = "b"*64
        with self.assertRaises(Exception): module._historical_signature(module.numeric_bytes(mutated), public)


if __name__ == "__main__": unittest.main()
