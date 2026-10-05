"""Current fixture trust, atomic key rotation and retained lifecycle tombstones."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from model_release_assurance.production_identity import AccessIdentity
from model_release_assurance.production_trust import (
    FixtureTrustRegistry, KeyRegistration, TrustConflict, TrustDenied, TrustProfile, TrustUnavailable,
)
from model_release_assurance.production_trust import registry as module


class ProductionTrustRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(3)]
        cls.weak_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        cls.ec_key = ec.generate_private_key(ec.SECP256R1())

    def setUp(self):
        self.clock = [1000]
        self.profile = TrustProfile("agency-a", "public_fixture", "https://issuer.example.invalid", "resource-api", "access_token")
        self.registry = FixtureTrustRegistry(now=lambda: self.clock[0], fresh_until=1300)
        self.a = self.record("key-a", 0)
        self.b = self.record("key-b", 1)
        self.c = self.record("key-c", 2)

    def record(self, base_key_id, index, **changes):
        values = dict(key_id=base_key_id, profile=self.profile, owner_id="owner-a",
                      public_key_pem=self.keys[index].public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
                      not_before=900, not_after=2000)
        values.update(changes)
        return KeyRegistration(**values)

    def enroll(self, record=None):
        return self.registry.enroll(record or self.a, expected_revision=self.registry.revision)

    def identity(self, **changes):
        values = dict(issuer=self.profile.issuer, subject="owner", client_id="client-a", token_id="token-a", key_id="key-a",
                      issued_at=1000, expires_at=1200, scopes=frozenset({"case:read"}), case_ids=frozenset({"case-a"}),
                      acr=None, auth_time=None)
        values.update(changes)
        return AccessIdentity(**values)

    def test_registration_normalizes_public_pem_and_exposes_only_immutable_public_values(self):
        original = self.a.public_key_pem
        pkcs1 = self.keys[0].public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.PKCS1)
        normalized = self.record("key-a", 0, public_key_pem=pkcs1.decode("ascii"))
        self.assertEqual(normalized.public_key_pem, original)
        der = normalized.public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.assertEqual(normalized.fingerprint, hashlib.sha256(der).hexdigest())
        self.assertNotIn("BEGIN PUBLIC KEY", repr(normalized))
        with self.assertRaises(FrozenInstanceError):
            normalized.not_after = 9999
        self.assertEqual(self.registry.revision, 1)
        self.assertEqual(self.enroll(), 2)
        self.assertEqual(self.registry.signing_key("key-a", self.profile, owner_id="owner-a"), self.a)
        visible = self.registry.public_keys(self.profile)
        with self.assertRaises(TypeError):
            visible["another"] = self.b.public_key
        self.assertIsNone(self.registry.check_current(self.identity(), self.profile))

    def test_invalid_profiles_and_registration_material_are_rejected(self):
        for changes in ({"environment": "prod"}, {"purpose": "unknown"}, {"agency_id": "../agency"},
                        {"issuer": "*"}, {"audience": []}):
            with self.subTest(changes=changes), self.assertRaises(TrustDenied):
                replace(self.profile, **changes)
        private_pem = self.keys[0].private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        weak = self.weak_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        ec_key = self.ec_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for changes in ({"public_key_pem": private_pem}, {"public_key_pem": weak}, {"public_key_pem": ec_key},
                        {"public_key_pem": b"malformed"}, {"public_key_pem": None}, {"key_id": "https://invalid.example/key"},
                        {"owner_id": "*"}, {"not_before": True}, {"not_after": 900}, {"not_after": float("inf")},
                        {"not_before": -1}, {"not_after": 2**53}):
            with self.subTest(fields=list(changes)), self.assertRaises(TrustDenied):
                self.record("key-a", 0, **changes)

    def test_exact_single_public_pem_block_excludes_hidden_private_or_extra_material(self):
        public = self.a.public_key_pem
        private = self.keys[0].private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        for material in (public + private, public + public, public + b"suffix-garbage", b"prefix-garbage" + public):
            with self.subTest(size=len(material)), self.assertRaises(TrustDenied):
                self.record("key-a", 0, public_key_pem=material)
        padded_crlf = b" \t\r\n" + public.replace(b"\n", b"\r\n") + b" \t\n"
        accepted = self.record("key-a", 0, public_key_pem=padded_crlf)
        self.assertEqual(accepted.public_key_pem, public)
        self.assertEqual(accepted.fingerprint, self.a.fingerprint)

    def test_staged_multiple_active_keys_are_explicitly_supported(self):
        self.enroll()
        self.enroll(self.b)
        self.assertEqual(set(self.registry.public_keys(self.profile)), {"key-a", "key-b"})
        self.assertEqual(self.registry.signing_key("key-a", self.profile, owner_id="owner-a").key_id, "key-a")
        self.assertEqual(self.registry.signing_key("key-b", self.profile, owner_id="owner-a").key_id, "key-b")

    def test_rotation_retires_old_signing_and_strictly_bounds_issued_at_and_overlap(self):
        self.enroll()
        old = self.identity()
        self.clock[0] = 1001
        self.assertEqual(self.registry.rotate("key-a", self.b, expected_revision=2, overlap_seconds=10), 3)
        self.assertEqual(set(self.registry.public_keys(self.profile)), {"key-a", "key-b"})
        self.registry.check_current(old, self.profile)
        with self.assertRaises(TrustDenied):
            self.registry.signing_key("key-a", self.profile, owner_id="owner-a")
        self.assertEqual(self.registry.signing_key("key-b", self.profile, owner_id="owner-a"), self.b)
        with self.assertRaises(TrustDenied):
            self.registry.check_current(self.identity(issued_at=1001), self.profile)
        self.clock[0] = 1010
        self.registry.check_current(old, self.profile)
        self.clock[0] = 1011
        with self.assertRaises(TrustDenied):
            self.registry.check_current(old, self.profile)
        self.assertEqual(set(self.registry.public_keys(self.profile)), {"key-b"})

    def test_rotation_overlap_cannot_outlive_old_key_validity(self):
        self.a = self.record("key-a", 0, not_after=1005)
        self.enroll()
        self.clock[0] = 1001
        self.registry.rotate("key-a", self.b, expected_revision=2, overlap_seconds=300)
        identity = self.identity(expires_at=1005)
        self.clock[0] = 1004
        self.registry.check_current(identity, self.profile)
        self.clock[0] = 1005
        self.assertNotIn("key-a", self.registry.public_keys(self.profile))
        with self.assertRaises(TrustDenied):
            self.registry.check_current(identity, self.profile)

    def test_invalid_rotation_is_atomic_and_does_not_consume_new_key(self):
        self.enroll()
        invalid = [self.record("key-b", 1, owner_id="owner-b"), self.record("key-b", 1, profile=replace(self.profile, agency_id="agency-b")),
                   self.record("key-b", 1, not_before=1001), self.record("key-b", 1, not_after=1000)]
        for candidate in invalid:
            with self.assertRaises(TrustDenied):
                self.registry.rotate("key-a", candidate, expected_revision=2, overlap_seconds=10)
            self.assertEqual(self.registry.revision, 2)
            self.assertEqual(set(self.registry.public_keys(self.profile)), {"key-a"})
            self.registry.signing_key("key-a", self.profile, owner_id="owner-a")
        for overlap in (0, 301, True, -1, 1.5, float("nan")):
            with self.subTest(overlap=overlap), self.assertRaises(TrustDenied):
                self.registry.rotate("key-a", self.b, expected_revision=2, overlap_seconds=overlap)
        self.assertEqual(self.registry.rotate("key-a", self.b, expected_revision=2, overlap_seconds=10), 3)

    def test_key_ids_and_fingerprints_are_permanent_cross_profile_tombstones(self):
        self.enroll()
        self.registry.revoke("key-a", expected_revision=2)
        with self.assertRaises(TrustConflict):
            self.registry.enroll(self.record("key-a", 1), expected_revision=3)
        for profile in (self.profile, replace(self.profile, purpose="worker_evidence"), replace(self.profile, agency_id="agency-b")):
            with self.subTest(profile=profile), self.assertRaises(TrustConflict):
                self.registry.enroll(self.record("never-reuse", 0, profile=profile), expected_revision=3)
        with self.assertRaises(TrustConflict):
            self.registry.revoke("key-a", expected_revision=3)
        self.assertEqual(self.registry.revision, 3)

    def test_retired_keys_cannot_reactivate_rotate_or_reuse_capacity(self):
        self.enroll()
        self.clock[0] = 1001
        self.registry.rotate("key-a", self.b, expected_revision=2, overlap_seconds=1)
        self.clock[0] = 1002
        with self.assertRaises(TrustDenied):
            self.registry.rotate("key-a", self.c, expected_revision=3, overlap_seconds=10)
        with self.assertRaises(TrustConflict):
            self.registry.enroll(self.record("different-id", 0), expected_revision=3)
        with mock.patch.object(module, "MAX_KEYS", 2):
            self.registry.revoke("key-a", expected_revision=3)
            with self.assertRaises(TrustConflict):
                self.registry.enroll(self.c, expected_revision=4)
        self.assertEqual(len(self.registry._entries), 2)
        self.assertEqual(module.MAX_KEYS, 32)

    def test_expected_revision_is_exact_and_replay_does_not_change_state(self):
        self.enroll()
        for expected in (1, 3, True, "2", 2.0, None):
            with self.subTest(expected=expected), self.assertRaises(TrustConflict):
                self.registry.enroll(self.b, expected_revision=expected)
        self.assertEqual(self.registry.revision, 2)
        self.assertEqual(set(self.registry.public_keys(self.profile)), {"key-a"})
        self.registry.set_available(False, expected_revision=2)
        with self.assertRaises(TrustConflict):
            self.registry.set_available(True, expected_revision=2)

    def test_stale_outage_and_emergency_revocation_recovery_remain_fail_closed(self):
        self.enroll()
        self.registry.set_available(False, expected_revision=2)
        for operation in (lambda: self.registry.public_keys(self.profile),
                          lambda: self.registry.signing_key("key-a", self.profile, owner_id="owner-a"),
                          lambda: self.registry.check_current(self.identity(), self.profile),
                          lambda: self.registry.enroll(self.b, expected_revision=3),
                          lambda: self.registry.rotate("key-a", self.b, expected_revision=3, overlap_seconds=10)):
            with self.assertRaises(TrustUnavailable):
                operation()
        self.assertEqual(self.registry.revoke("key-a", expected_revision=3), 4)
        self.clock[0] = 1300
        self.registry.set_available(True, expected_revision=4)
        with self.assertRaises(TrustUnavailable):
            self.registry.public_keys(self.profile)
        self.assertEqual(self.registry.refresh(fresh_until=1600, expected_revision=5), 6)
        self.assertEqual(dict(self.registry.public_keys(self.profile)), {})
        with self.assertRaises(TrustConflict):
            self.registry.enroll(self.a, expected_revision=6)
        self.assertEqual(self.registry.enroll(self.b, expected_revision=6), 7)

    def test_stale_registry_allows_emergency_revoke_but_not_normal_enrollment(self):
        self.enroll()
        self.clock[0] = 1300
        with self.assertRaises(TrustUnavailable):
            self.registry.enroll(self.b, expected_revision=2)
        self.assertEqual(self.registry.revoke("key-a", expected_revision=2), 3)
        self.registry.refresh(fresh_until=1400, expected_revision=3)
        self.assertEqual(dict(self.registry.public_keys(self.profile)), {})

    def test_freshness_and_availability_inputs_are_strict_bounded_values(self):
        for fresh in (1000, 1301, True, float("inf"), "1200", None):
            with self.subTest(fresh=fresh), self.assertRaises(TrustDenied):
                FixtureTrustRegistry(now=lambda: 1000, fresh_until=fresh)
        for fresh in (1000, 1301, True, float("nan")):
            with self.subTest(fresh=fresh), self.assertRaises(TrustDenied):
                self.registry.refresh(fresh_until=fresh, expected_revision=1)
        for available in (0, 1, None, "false"):
            with self.subTest(available=available), self.assertRaises(TrustDenied):
                self.registry.set_available(available, expected_revision=1)
        self.assertEqual(self.registry.revision, 1)

    def test_own_clock_is_monotonic_and_supplied_now_cannot_hide_expiry(self):
        self.enroll()
        self.clock[0] = 1200
        with self.assertRaises(TrustDenied):
            self.registry.check_current(self.identity(), self.profile, now=1000)
        for supplied in (1201, True, -1, 1200.0, float("nan")):
            with self.subTest(now=supplied), self.assertRaises(TrustUnavailable):
                self.registry.public_keys(self.profile, now=supplied)
        self.clock[0] = 1199
        for operation in (self.registry.current_time,
                          lambda: self.registry.revoke("key-a", expected_revision=2),
                          lambda: self.registry.refresh(fresh_until=1300, expected_revision=2),
                          lambda: self.registry.set_available(False, expected_revision=2)):
            with self.assertRaises(TrustUnavailable):
                operation()
        self.clock[0] = 1200
        self.assertEqual(self.registry.current_time(), 1200)

    def test_invalid_or_failed_clock_is_unavailable(self):
        for value in (True, 1000.0, -1, 2**53, float("inf"), float("nan"), "1000"):
            with self.subTest(value=value), self.assertRaises(TrustUnavailable):
                FixtureTrustRegistry(now=lambda: value, fresh_until=1200)
        def failed_clock():
            raise OSError("clock implementation detail")
        with self.assertRaisesRegex(TrustUnavailable, "^Trust registry unavailable$"):
            FixtureTrustRegistry(now=failed_clock, fresh_until=1200)

    def test_profile_and_owner_mismatches_never_cross_key_domains(self):
        self.enroll()
        for profile in (replace(self.profile, agency_id="agency-b"), replace(self.profile, issuer="https://other.example.invalid"),
                        replace(self.profile, audience="other-api"), replace(self.profile, purpose="gateway")):
            with self.subTest(profile=profile):
                self.assertEqual(dict(self.registry.public_keys(profile)), {})
                with self.assertRaises(TrustDenied):
                    self.registry.signing_key("key-a", profile, owner_id="owner-a")
                with self.assertRaises(TrustDenied):
                    self.registry.check_current(self.identity(), profile)
        with self.assertRaises(TrustDenied):
            self.registry.signing_key("key-a", self.profile, owner_id="other-owner")
        evidence_profile = replace(self.profile, purpose="worker_evidence")
        self.enroll(self.record("key-b", 1, profile=evidence_profile))
        with self.assertRaises(TrustDenied):
            self.registry.check_current(self.identity(key_id="key-b"), evidence_profile)

    def test_current_identity_types_key_bounds_and_expiry_are_strict(self):
        self.enroll()
        for change in ({"issuer": "https://other.example.invalid"}, {"key_id": "missing"}, {"key_id": "../key"},
                       {"issued_at": 899, "expires_at": 1100}, {"issued_at": 1001}, {"issued_at": True},
                       {"expires_at": 1000}, {"expires_at": 1301}, {"expires_at": float("inf")},
                       {"subject": "*"}, {"client_id": None}, {"token_id": ""}, {"scopes": {"case:read"}},
                       {"case_ids": frozenset({"*"})}, {"acr": ""}, {"auth_time": True}, {"auth_time": 1001}):
            with self.subTest(change=change), self.assertRaises(TrustDenied):
                self.registry.check_current(self.identity(**change), self.profile)
        short = self.record("short", 1, not_after=1100)
        self.enroll(short)
        with self.assertRaises(TrustDenied):
            self.registry.check_current(self.identity(key_id="short", expires_at=1101), self.profile)
        self.registry.check_current(self.identity(key_id="short", expires_at=1100), self.profile)

    def test_cached_public_keys_do_not_make_revoked_or_expired_keys_current(self):
        self.enroll()
        cached = self.registry.public_keys(self.profile)
        self.registry.revoke("key-a", expected_revision=2)
        self.assertIn("key-a", cached)
        self.assertNotIn("key-a", self.registry.public_keys(self.profile))
        with self.assertRaises(TrustDenied):
            self.registry.check_current(self.identity(), self.profile)
        self.assertEqual(self.a.public_key_pem, self.record("key-a", 0).public_key_pem)

    def test_shared_time_helper_requires_held_lock_and_exact_sample_without_resampling(self):
        self.enroll()
        identity = self.identity()
        with self.assertRaises(TrustUnavailable):
            self.registry.check_current_at(identity, self.profile, now=1000)
        with self.registry.operation_lock:
            sampled = self.registry.current_time()
            with mock.patch.object(self.registry, "_clock", side_effect=AssertionError("must not resample")):
                self.registry.check_current_at(identity, self.profile, now=sampled)
                for supplied in (sampled - 1, sampled + 1, True, float(sampled)):
                    with self.subTest(supplied=supplied), self.assertRaises(TrustUnavailable):
                        self.registry.check_current_at(identity, self.profile, now=supplied)
            self.clock[0] = 1001
            self.registry.current_time()
            with self.assertRaises(TrustUnavailable):
                self.registry.check_current_at(identity, self.profile, now=sampled)
        self.registry.set_available(False, expected_revision=2)
        with self.registry.operation_lock, self.assertRaises(TrustUnavailable):
            self.registry.check_current_at(identity, self.profile, now=self.registry.current_time())


if __name__ == "__main__":
    unittest.main()
