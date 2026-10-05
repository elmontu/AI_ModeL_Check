"""Evidence signatures bind exact owned claims and current active worker trust."""
from __future__ import annotations

import base64
import copy
from dataclasses import replace
import hashlib
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from model_release_assurance.production_evidence import signing
from model_release_assurance.production_evidence.contracts import (
    EvidenceError, NATIVE_ARTIFACT_NAMES, OBSERVATIONS, canonical_bytes, digest,
    execution_digest, strict_json, validate_artifacts, validate_challenge,
    validate_context, validate_digest, validate_observations, validate_statement,
)
from model_release_assurance.production_evidence.signing import MemoryFixtureEvidenceSigner, verify_envelope
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustDenied, TrustProfile, TrustUnavailable


def context_fixture():
    return {
        "schema": "mra-execution-context/v1", "environment": "public_fixture", "operation": "retained_native_replay",
        "agency_id": "agency-a", "project_id": "project-a", "case_id": "case-a", "worker_id": "worker-a",
        "job_id": "1" * 32, "attempt_id": "2" * 32, "fence": 1,
        "job_sha256": "a" * 64, "source_sha256": "b" * 64, "policy_sha256": "c" * 64,
        "plan_sha256": "d" * 64, "adapter_sha256": "e" * 64, "runtime_sha256": "f" * 64,
        "image_sha256": None,
    }


def statement_fixture():
    context = context_fixture()
    challenge = {"schema": "mra-evidence-challenge/v1", "ledger_id": "3" * 32, "nonce": "4" * 64,
                 "context_sha256": digest(context), "execution_sha256": execution_digest(context),
                 "issued_at": 1000, "expires_at": 1120}
    return {"schema": "mra-worker-evidence/v1", "context": context, "challenge": challenge,
            "artifacts": {name: {"sha256": "5" * 64, "size_bytes": 10} for name in NATIVE_ARTIFACT_NAMES},
            "observations": dict(OBSERVATIONS), "issued_at": 1000, "expires_at": 1120}


class EvidenceContractTests(unittest.TestCase):
    def test_exact_owned_context_and_scope_digest(self):
        original = context_fixture()
        result = validate_context(original)
        original["case_id"] = "changed"
        self.assertEqual(result["case_id"], "case-a")
        expected = {key: result[key] for key in ("agency_id", "project_id", "case_id", "job_id", "attempt_id", "fence")}
        self.assertEqual(execution_digest(result), digest(expected))
        altered = dict(result, adapter_sha256="1" * 64)
        self.assertEqual(execution_digest(altered), execution_digest(result))
        self.assertNotEqual(digest(altered), digest(result))

    def test_context_types_unknown_fields_and_operation_are_strict(self):
        variations = [dict(fence=True), dict(fence=1.), dict(fence=0), dict(fence=4), dict(job_id="A" * 32),
                      dict(agency_id="../agency"), dict(case_id="a b"), dict(worker_id="*"),
                      dict(image_sha256="bad"), dict(source_sha256="B" * 64), dict(operation="training"),
                      dict(environment="production"), dict(arbitrary="extra")]
        for fields in variations:
            with self.subTest(fields=fields), self.assertRaises(EvidenceError):
                validate_context(dict(context_fixture(), **fields))
        missing = context_fixture()
        del missing["image_sha256"]
        with self.assertRaises(EvidenceError):
            validate_context(missing)

    def test_challenge_exact_lifetime_and_types(self):
        challenge = statement_fixture()["challenge"]
        self.assertEqual(validate_challenge(challenge), challenge)
        for fields in ({"issued_at": True}, {"expires_at": 1000}, {"expires_at": 1301}, {"nonce": "0" * 63},
                       {"ledger_id": "x" * 32}, {"issued_at": -1}, {"expires_at": 1120.}):
            with self.subTest(fields=fields), self.assertRaises(EvidenceError):
                validate_challenge(dict(challenge, **fields))

    def test_artifact_roster_types_and_aggregate_bounds(self):
        artifacts = statement_fixture()["artifacts"]
        self.assertEqual(validate_artifacts(artifacts), artifacts)
        for name, value in (("missing", None), ("extra", None), ("size", True), ("size", 0), ("size", 32 * 1024 * 1024 + 1)):
            altered = copy.deepcopy(artifacts)
            if name == "missing":
                altered.pop("result.json")
            elif name == "extra":
                altered["../model.pkl"] = {"sha256": "a" * 64, "size_bytes": 1}
            else:
                altered["dataset.json"]["size_bytes"] = value
            with self.assertRaises(EvidenceError):
                validate_artifacts(altered)
        too_large = {name: {"sha256": "a" * 64, "size_bytes": 32 * 1024 * 1024} for name in NATIVE_ARTIFACT_NAMES}
        with self.assertRaises(EvidenceError):
            validate_artifacts(too_large)

    def test_all_isolation_observations_are_explicit_false(self):
        for name in set(OBSERVATIONS) - {"schema"}:
            for invalid in (True, 0, None, "false"):
                with self.subTest(name=name, invalid=invalid), self.assertRaises(EvidenceError):
                    validate_observations(dict(OBSERVATIONS, **{name: invalid}))
        with patch.dict(OBSERVATIONS, image_verified=True):
            with self.assertRaises(EvidenceError):
                validate_observations(dict(OBSERVATIONS))

    def test_statement_owned_nested_copy_and_hash_bindings(self):
        statement = statement_fixture()
        validated = validate_statement(statement)
        statement["artifacts"]["dataset.json"]["sha256"] = "f" * 64
        self.assertEqual(validated["artifacts"]["dataset.json"]["sha256"], "5" * 64)
        for field in ("context_sha256", "execution_sha256"):
            altered = statement_fixture()
            altered["challenge"][field] = "0" * 64
            with self.assertRaises(EvidenceError):
                validate_statement(altered)
        for fields in ({"issued_at": 999}, {"expires_at": 1121}, {"issued_at": True}, {"extra": None}):
            with self.assertRaises(EvidenceError):
                validate_statement(dict(statement_fixture(), **fields))

    def test_strict_json_rejects_ambiguity_nonfinite_and_overflow(self):
        inputs = (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}',
                  b'[' * 17 + b'0' + b']' * 17, b'\xff', b'{', b'', b'1' * 1000)
        for raw in inputs:
            with self.subTest(raw=raw[:30]), self.assertRaises(EvidenceError):
                strict_json(raw)
        self.assertNotEqual(canonical_bytes({"x": True}), canonical_bytes({"x": 1}))
        for raw, bound in ((b'{}', True), (b'{}', 1), (b'{}', 0), ('{}', 10)):
            with self.assertRaises(EvidenceError):
                strict_json(raw, max_bytes=bound)

    def test_canonical_json_refuses_nonjson_values_and_oversize(self):
        for value in ({"x": object()}, {"x": (1, 2)}, {1: "x"}, {"x": float("nan")},
                      {"x": "a" * 65536}, {"x": 2**53}):
            with self.assertRaises(EvidenceError):
                canonical_bytes(value)
        self.assertEqual(validate_digest("a" * 64), "a" * 64)
        with self.assertRaises(EvidenceError):
            validate_digest("A" * 64)


class EvidenceSigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = TrustProfile("agency-a", "public_fixture", "https://fixture.invalid/evidence", "native-replay", "worker_evidence")
        cls.signer = MemoryFixtureEvidenceSigner(cls.profile, "worker-a", "evidence-a", 900, 2000)
        cls.other_signer = MemoryFixtureEvidenceSigner(cls.profile, "worker-a", "evidence-b", 900, 2000)

    def setUp(self):
        self.now = 1000
        self.registry = FixtureTrustRegistry(now=lambda: self.now, fresh_until=1300)
        self.registry.enroll(self.signer.registration, expected_revision=self.registry.revision)
        self.statement = statement_fixture()

    def verified(self, raw):
        return verify_envelope(raw, self.registry, self.profile, "worker-a")

    def assert_rejected(self, function):
        with self.assertRaises(EvidenceError) as caught:
            function()
        self.assertEqual(str(caught.exception), "Worker evidence rejected")
        self.assertIsNone(caught.exception.__cause__)

    def test_signature_round_trip_and_independent_public_crypto(self):
        raw = self.signer.sign(self.statement, self.registry)
        verified = self.verified(raw)
        self.assertEqual(verified["statement"], self.statement)
        self.assertEqual(verified["envelope_sha256"], hashlib.sha256(raw).hexdigest())
        envelope = strict_json(raw)
        signature = base64.b64decode(envelope.pop("signature"))
        self.signer.registration.public_key.verify(signature, b"mra-worker-evidence/v1\x00" + canonical_bytes(envelope),
                                                 padding.PKCS1v15(), hashes.SHA256())
        self.assertEqual(canonical_bytes(strict_json(raw)), raw)
        verified["statement"]["context"]["case_id"] = "mutated"
        self.assertEqual(self.verified(raw)["statement"]["context"]["case_id"], "case-a")

    def test_only_worker_evidence_purpose_allowed(self):
        for purpose in ("access_token", "policy", "registry", "gateway"):
            profile = replace(self.profile, purpose=purpose)
            self.assert_rejected(lambda: MemoryFixtureEvidenceSigner(profile, "worker-a", "new-key", 900, 2000))
        raw = self.signer.sign(self.statement, self.registry)
        self.assert_rejected(lambda: verify_envelope(raw, self.registry, replace(self.profile, purpose="access_token"), "worker-a"))

    def test_no_private_key_or_generic_signing_export(self):
        for value in (self.signer, self.signer.registration):
            self.assertNotIn("PRIVATE KEY", repr(value))
            self.assertNotIn("BEGIN PUBLIC KEY", repr(value))
            for name in ("private_bytes", "export_private_key", "import_private_key", "sign_bytes"):
                self.assertFalse(hasattr(value, name))

    def test_unenrolled_or_same_id_wrong_key_signer_is_refused(self):
        self.assert_rejected(lambda: self.other_signer.sign(self.statement, self.registry))
        impostor = MemoryFixtureEvidenceSigner(self.profile, "worker-a", "evidence-a", 900, 2000)
        self.assert_rejected(lambda: impostor.sign(self.statement, self.registry))

    def test_expected_profile_owner_agency_and_worker_bindings(self):
        raw = self.signer.sign(self.statement, self.registry)
        for profile in (replace(self.profile, agency_id="agency-b"), replace(self.profile, audience="other"),
                        replace(self.profile, issuer="https://other.invalid")):
            self.assert_rejected(lambda: verify_envelope(raw, self.registry, profile, "worker-a"))
        self.assert_rejected(lambda: verify_envelope(raw, self.registry, self.profile, "worker-b"))
        for field, value in (("agency_id", "agency-b"), ("worker_id", "worker-b")):
            statement = statement_fixture()
            statement["context"][field] = value
            statement["challenge"]["context_sha256"] = digest(statement["context"])
            statement["challenge"]["execution_sha256"] = execution_digest(statement["context"])
            self.assert_rejected(lambda: self.signer.sign(statement, self.registry))

    def test_invalid_statement_never_reaches_private_operation(self):
        class PrivateTrap:
            calls = 0
            def sign(self, *args):
                self.calls += 1
                raise AssertionError("private operation reached")
        original = self.signer._private
        self.addCleanup(setattr, self.signer, "_private", original)
        trap = self.signer._private = PrivateTrap()
        invalid = dict(self.statement, issued_at=True)
        self.assert_rejected(lambda: self.signer.sign(invalid, self.registry))
        self.assertEqual(trap.calls, 0)

    def test_signed_fields_cannot_be_tampered(self):
        raw = self.signer.sign(self.statement, self.registry)
        original = strict_json(raw)
        for mutate in (lambda x: x.update(algorithm="none"), lambda x: x.update(key_id="evidence-b"),
                       lambda x: x.update(key_fingerprint="0" * 64), lambda x: x.update(owner_id="worker-b"),
                       lambda x: x["statement"]["artifacts"]["result.json"].update(sha256="0" * 64),
                       lambda x: x["statement"].update(expires_at=1119),
                       lambda x: x["profile"].update(audience="changed"),
                       lambda x: x.update(extra=True)):
            envelope = copy.deepcopy(original)
            mutate(envelope)
            self.assert_rejected(lambda: self.verified(canonical_bytes(envelope)))

    def test_domain_separation_refuses_signature_over_bare_statement(self):
        raw = self.signer.sign(self.statement, self.registry)
        envelope = strict_json(raw)
        signature = self.signer._private.sign(canonical_bytes(self.statement), padding.PKCS1v15(), hashes.SHA256())
        envelope["signature"] = base64.b64encode(signature).decode("ascii")
        self.assert_rejected(lambda: self.verified(canonical_bytes(envelope)))

    def test_signature_bytes_encoding_and_envelope_ambiguity_are_rejected(self):
        raw = self.signer.sign(self.statement, self.registry)
        original = strict_json(raw)
        for signature in ("AA==", original["signature"] + "=", " " + original["signature"], "!" * 344, True):
            envelope = dict(original, signature=signature)
            self.assert_rejected(lambda: self.verified(canonical_bytes(envelope)))
        self.assert_rejected(lambda: self.verified(raw + b"\n"))
        self.assert_rejected(lambda: self.verified(raw.replace(b'"algorithm":"RS256"', b'"algorithm":"RS256","algorithm":"RS256"')))
        self.assert_rejected(lambda: self.verified(b"x" * 65537))

    def test_expired_future_and_key_window_evidence_is_refused(self):
        raw = self.signer.sign(self.statement, self.registry)
        self.now = 1120
        self.assert_rejected(lambda: self.verified(raw))
        self.assert_rejected(lambda: self.signer.sign(self.statement, self.registry))
        self.now = 1121
        future = statement_fixture()
        future["issued_at"] = future["challenge"]["issued_at"] = 1122
        future["expires_at"] = future["challenge"]["expires_at"] = 1200
        self.assert_rejected(lambda: self.signer.sign(future, self.registry))

    def test_statement_lifetime_must_fit_registered_key(self):
        short = MemoryFixtureEvidenceSigner(self.profile, "worker-a", "short", 1000, 1100)
        self.registry.enroll(short.registration, expected_revision=self.registry.revision)
        self.assert_rejected(lambda: short.sign(self.statement, self.registry))

    def test_rotated_verify_only_key_is_not_accepted_for_evidence(self):
        raw = self.signer.sign(self.statement, self.registry)
        self.now = 1001
        self.registry.rotate("evidence-a", self.other_signer.registration,
                             expected_revision=self.registry.revision, overlap_seconds=60)
        self.assertIn("evidence-a", self.registry.public_keys(self.profile))
        self.assert_rejected(lambda: self.verified(raw))
        self.assert_rejected(lambda: self.signer.sign(self.statement, self.registry))
        fresh = self.other_signer.sign(self.statement, self.registry)
        self.assertEqual(self.verified(fresh)["key_id"], "evidence-b")

    def test_revocation_outage_staleness_and_clock_rollback_fail_closed(self):
        raw = self.signer.sign(self.statement, self.registry)
        self.registry.revoke("evidence-a", expected_revision=self.registry.revision)
        self.assert_rejected(lambda: self.verified(raw))
        self.setUp()
        raw = self.signer.sign(self.statement, self.registry)
        self.registry.set_available(False, expected_revision=self.registry.revision)
        self.assert_rejected(lambda: self.verified(raw))
        self.setUp()
        raw = self.signer.sign(self.statement, self.registry)
        self.now = 1300
        self.assert_rejected(lambda: self.verified(raw))
        self.now = 999
        self.assert_rejected(lambda: self.verified(raw))

    def test_private_backend_wrong_signature_never_returns_envelope(self):
        class BadPrivate:
            def sign(self, *args):
                return b"\x00" * 256
        with patch.object(self.signer, "_private", BadPrivate()):
            self.assert_rejected(lambda: self.signer.sign(self.statement, self.registry))

    def test_signing_rechecks_revocation_and_revision_after_crypto(self):
        original = self.signer._private
        registry = self.registry
        class ChangingPrivate:
            def sign(self, *args):
                signature = original.sign(*args)
                registry.refresh(fresh_until=1299, expected_revision=registry.revision)
                return signature
        with patch.object(self.signer, "_private", ChangingPrivate()):
            self.assert_rejected(lambda: self.signer.sign(self.statement, self.registry))

    def test_signing_rechecks_expiry_after_crypto(self):
        original = self.signer._private
        test = self
        class SlowPrivate:
            def sign(self, *args):
                signature = original.sign(*args)
                test.now = 1120
                return signature
        with patch.object(self.signer, "_private", SlowPrivate()):
            self.assert_rejected(lambda: self.signer.sign(self.statement, self.registry))

    def test_verification_final_sample_catches_expiry_after_first_key_check(self):
        raw = self.signer.sign(self.statement, self.registry)
        current = signing._current
        calls = []
        def advance(*args, **kwargs):
            result = current(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                self.now = 1120
            return result
        with patch.object(signing, "_current", side_effect=advance):
            self.assert_rejected(lambda: self.verified(raw))
        self.assertEqual(len(calls), 1)

    def test_final_current_time_not_earlier_revision_sample_controls_expiry(self):
        raw = self.signer.sign(self.statement, self.registry)
        current_time = self.registry.current_time
        calls = []
        def sample():
            calls.append(1)
            if len(calls) == 2:
                self.now = 1120
            return current_time()
        with patch.object(self.registry, "current_time", side_effect=sample):
            self.assert_rejected(lambda: self.verified(raw))
        self.assertEqual(len(calls), 2)

    def test_final_verification_refuses_registry_outage_and_revision_change(self):
        raw = self.signer.sign(self.statement, self.registry)
        current = signing._current
        calls = []
        def mutate(*args, **kwargs):
            result = current(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                self.registry.set_available(False, expected_revision=self.registry.revision)
            return result
        with patch.object(signing, "_current", side_effect=mutate):
            self.assert_rejected(lambda: self.verified(raw))

    def test_input_mutation_during_signing_cannot_replace_statement(self):
        original = self.signer._private
        caller_statement = self.statement
        class MutatingPrivate:
            def sign(self, *args):
                caller_statement["artifacts"]["result.json"]["sha256"] = "f" * 64
                return original.sign(*args)
        with patch.object(self.signer, "_private", MutatingPrivate()):
            raw = self.signer.sign(caller_statement, self.registry)
        self.assertEqual(self.verified(raw)["statement"]["artifacts"]["result.json"]["sha256"], "5" * 64)

    def test_shared_time_key_check_requires_lock_and_exact_time(self):
        with self.assertRaises(TrustUnavailable):
            self.registry.signing_key_at("evidence-a", self.profile, owner_id="worker-a", now=1000)
        with self.registry.operation_lock:
            now = self.registry.current_time()
            self.assertEqual(self.registry.signing_key_at("evidence-a", self.profile, owner_id="worker-a", now=now), self.signer.registration)
            for wrong in (999, True, 1000.):
                with self.assertRaises(TrustUnavailable):
                    self.registry.signing_key_at("evidence-a", self.profile, owner_id="worker-a", now=wrong)
            with self.assertRaises(TrustDenied):
                self.registry.signing_key_at("evidence-a", self.profile, owner_id="wrong", now=now)
            self.now = 1300
            now = self.registry.current_time()
            with self.assertRaises(TrustUnavailable):
                self.registry.signing_key_at("evidence-a", self.profile, owner_id="worker-a", now=now)


if __name__ == "__main__":
    unittest.main()
