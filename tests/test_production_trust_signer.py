"""Bounded fixture signing refuses stale trust, invalid claims and backend faults."""
from __future__ import annotations

from dataclasses import replace
from unittest import mock
import unittest

from model_release_assurance.production_identity.tokens import AccessTokenVerifier
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile
from model_release_assurance.production_trust import signer as signer_module
from model_release_assurance.production_trust.signer import (
    FixtureTokenIssuer, MemoryFixtureSigningProvider, ProviderKeyDescription,
    SigningProvider, TokenSigningUnavailable,
)


class ProductionTrustSignerTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.profile = TrustProfile("agency-a", "public_fixture", "https://fixture.invalid", "fixture-api", "access_token")
        self.provider = MemoryFixtureSigningProvider()
        self.record = self.create_key("access-a")
        self.registry = FixtureTrustRegistry(now=lambda: self.now, fresh_until=1300)
        self.registry.enroll(self.record, expected_revision=self.registry.revision)
        self.capability = self.provider.bind(profile=self.profile, owner_id="fixture-owner")
        self.issuer = FixtureTokenIssuer(self.registry, self.capability, self.profile, "fixture-owner")
        self.claims = {"iss": self.profile.issuer, "aud": self.profile.audience, "sub": "fixture-user", "client_id": "fixture-client",
                       "jti": "fixture-token-a", "iat": 1000, "nbf": 1000, "exp": 1120, "scope": "case:read object:metadata",
                       "case_ids": ["case-a"], "acr": "urn:mra:fixture:mfa", "auth_time": 999}

    def create_key(self, key_id, *, profile=None, owner="fixture-owner", not_before=1000, not_after=1600):
        return self.provider.create_key(key_id=key_id, profile=profile or self.profile, owner_id=owner,
                                        not_before=not_before, not_after=not_after)

    def verify(self, token, record=None):
        record = record or self.record
        return AccessTokenVerifier(record.profile.issuer, record.profile.audience, {record.key_id: record.public_key}).verify(token, now=self.now)

    def assert_unavailable(self, action):
        with self.assertRaises(TokenSigningUnavailable) as caught:
            action()
        self.assertEqual(str(caught.exception), "Fixture token signing unavailable")
        self.assertIsNone(caught.exception.__cause__)

    def test_generated_in_memory_key_signs_exact_access_profile(self):
        token = self.issuer.issue("access-a", self.claims)
        identity = self.verify(token)
        self.assertEqual(identity.subject, "fixture-user")
        self.assertEqual(identity.case_ids, frozenset({"case-a"}))
        self.assertEqual(identity.scopes, frozenset({"case:read", "object:metadata"}))
        self.assertEqual(identity.expires_at, 1120)
        self.assertTrue(isinstance(self.capability, SigningProvider))
        description = self.capability.describe("access-a")
        self.assertEqual(description.version_id, self.record.fingerprint)
        self.assertEqual(description.public_key_pem, self.record.public_key_pem)

    def test_no_raw_key_material_in_repr_or_private_export_interface(self):
        values = (self.provider, self.capability, self.issuer, self.record, self.capability.describe("access-a"))
        for value in values:
            self.assertNotIn("BEGIN PUBLIC KEY", repr(value))
            self.assertNotIn("PRIVATE KEY", repr(value))
            self.assertFalse(hasattr(value, "export_private_key"))
            self.assertFalse(hasattr(value, "private_bytes"))
        self.assertFalse(hasattr(self.provider, "import_private_key"))

    def test_profile_purpose_owner_and_capability_binding_are_not_caller_claims(self):
        other = replace(self.profile, purpose="worker_evidence")
        self.assert_unavailable(lambda: self.provider.bind(profile=other, owner_id="fixture-owner"))
        self.assert_unavailable(lambda: FixtureTokenIssuer(self.registry, self.capability, other, "fixture-owner"))
        wrong_owner = FixtureTokenIssuer(self.registry, self.capability, self.profile, "wrong-owner")
        self.assert_unavailable(lambda: wrong_owner.issue("access-a", self.claims))
        wrong_capability = self.provider.bind(profile=self.profile, owner_id="wrong-owner")
        issuer = FixtureTokenIssuer(self.registry, wrong_capability, self.profile, "fixture-owner")
        self.assert_unavailable(lambda: issuer.issue("access-a", self.claims))
        other_profile = replace(self.profile, agency_id="agency-b")
        self.assert_unavailable(lambda: FixtureTokenIssuer(self.registry, self.capability, other_profile, "fixture-owner").issue("access-a", self.claims))

    def test_invalid_claims_never_reach_private_sign_operation(self):
        variants = [dict(self.claims, roles=["administrator"]), dict(self.claims, iss="https://other.invalid"),
                    dict(self.claims, aud=[self.profile.audience]), dict(self.claims, iat=True),
                    dict(self.claims, iat=1001), dict(self.claims, nbf=1001), dict(self.claims, exp=1000),
                    dict(self.claims, exp=1301), dict(self.claims, auth_time=1001), dict(self.claims, auth_time=1.5),
                    dict(self.claims, sub="contains space"), dict(self.claims, scope="*"),
                    dict(self.claims, scope="case:read case:read"), dict(self.claims, scope="case:read  object:metadata"),
                    dict(self.claims, case_ids=[]), dict(self.claims, case_ids=["case-a", "case-a"]),
                    dict(self.claims, case_ids="case-a"), dict(self.claims, case_ids=[["nested"]]),
                    dict(self.claims, case_ids=["*"]), dict(self.claims, acr=None)]
        missing = dict(self.claims)
        del missing["jti"]
        variants.append(missing)
        with mock.patch.object(self.capability, "sign", side_effect=AssertionError("Private operation must not run")) as sign:
            for claims in variants:
                self.assert_unavailable(lambda claims=claims: self.issuer.issue("access-a", claims))
            sign.assert_not_called()

    def test_overlong_payload_and_unsupported_input_never_sign(self):
        overlong = dict(self.claims, case_ids=[str(index).zfill(3) + "x" * 125 for index in range(64)])
        with mock.patch.object(self.capability, "sign", side_effect=AssertionError("Unexpected private operation")) as sign:
            for claims in (overlong, dict(self.claims, sub="x" * 257), {"claims": self.claims}, b"serialized-input", None):
                self.assert_unavailable(lambda claims=claims: self.issuer.issue("access-a", claims))
            sign.assert_not_called()

    def test_key_not_after_caps_token_expiry_before_signing(self):
        limited = self.create_key("limited", not_after=1100)
        self.registry.enroll(limited, expected_revision=self.registry.revision)
        with mock.patch.object(self.capability, "sign", side_effect=AssertionError("Unexpected private operation")):
            self.assert_unavailable(lambda: self.issuer.issue("limited", self.claims))
        token = self.issuer.issue("limited", dict(self.claims, exp=1100))
        self.assertEqual(self.verify(token, limited).expires_at, 1100)

    def test_wrong_provider_description_is_refused_before_private_operation(self):
        original = self.capability.describe("access-a")
        variants = [replace(original, key_handle="other"), replace(original, key_id="other"),
                    replace(original, version_id="0" * 64), replace(original, fingerprint="0" * 64),
                    replace(original, owner_id="other"), replace(original, profile=replace(self.profile, audience="other")),
                    replace(original, public_key_pem=b"not a public key"), {"fingerprint": self.record.fingerprint}]
        with mock.patch.object(self.capability, "sign", side_effect=AssertionError("Unexpected private operation")) as sign:
            for description in variants:
                with mock.patch.object(self.capability, "describe", return_value=description):
                    self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
            sign.assert_not_called()

    def test_wrong_signature_and_wrong_signing_key_never_produce_a_token(self):
        other = self.create_key("other-key")
        original = self.capability.sign
        with mock.patch.object(self.capability, "sign", return_value=b"\0" * 256):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        with mock.patch.object(self.capability, "sign", side_effect=lambda handle, content: original(other.key_id, content)):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        with mock.patch.object(self.capability, "sign", return_value=b"short"):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_provider_and_registry_outages_and_disabled_key_have_no_fallback(self):
        self.provider.set_available(False)
        self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        self.provider.set_available(True)
        self.provider.set_key_enabled("access-a", False)
        self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        self.provider.set_key_enabled("access-a", True)
        self.registry.set_available(False, expected_revision=self.registry.revision)
        self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_rotation_refuses_old_signing_handle_but_allows_new_active_key(self):
        new = self.create_key("access-b")
        self.registry.rotate("access-a", new, expected_revision=self.registry.revision, overlap_seconds=30)
        with mock.patch.object(self.capability, "sign", side_effect=AssertionError("Old key must not sign")):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        token = self.issuer.issue("access-b", self.claims)
        self.assertEqual(self.verify(token, new).key_id, "access-b")

    def test_revoked_key_and_stale_registry_deny_before_private_operation(self):
        self.registry.revoke("access-a", expected_revision=self.registry.revision)
        with mock.patch.object(self.capability, "sign", side_effect=AssertionError("Unexpected private operation")):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        self.now = 1300
        self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_revocation_during_sign_is_denied_without_returning_token(self):
        original = self.capability.sign
        def revoked(handle, content):
            signature = original(handle, content)
            self.registry.revoke(handle, expected_revision=self.registry.revision)
            return signature
        with mock.patch.object(self.capability, "sign", side_effect=revoked):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_rotation_during_sign_is_denied_without_returning_token(self):
        original = self.capability.sign
        new = self.create_key("access-b")
        def rotated(handle, content):
            signature = original(handle, content)
            self.registry.rotate(handle, new, expected_revision=self.registry.revision, overlap_seconds=30)
            return signature
        with mock.patch.object(self.capability, "sign", side_effect=rotated):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_provider_outage_after_crypto_is_denied(self):
        original = self.capability.sign
        def outage(handle, content):
            signature = original(handle, content)
            self.provider.set_available(False)
            return signature
        with mock.patch.object(self.capability, "sign", side_effect=outage):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_provider_description_change_after_crypto_is_denied(self):
        original = self.capability.describe("access-a")
        changed = replace(original, version_id="f" * 64)
        with mock.patch.object(self.capability, "describe", side_effect=[original, changed]):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_token_expiry_during_crypto_is_denied(self):
        original = self.capability.sign
        def expires(handle, content):
            signature = original(handle, content)
            self.now = self.claims["exp"]
            return signature
        with mock.patch.object(self.capability, "sign", side_effect=expires):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_registry_outage_during_crypto_is_denied(self):
        original = self.capability.sign
        def outage(handle, content):
            signature = original(handle, content)
            self.registry.set_available(False, expected_revision=self.registry.revision)
            return signature
        with mock.patch.object(self.capability, "sign", side_effect=outage):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))

    def test_final_revision_time_observation_cannot_return_expired_token(self):
        original = self.registry._sample_time
        armed = False
        after_sign_calls = 0
        sign = self.capability.sign
        def signed(handle, content):
            nonlocal armed
            signature = sign(handle, content)
            armed = True
            return signature
        def clock(supplied=None):
            nonlocal after_sign_calls
            if armed:
                after_sign_calls += 1
                # Post-sign: current_time, signing_key, revision, then final
                # current_time, signing_key, revision. Expire on that last
                # revision read; claims using its earlier captured now miss it.
                if after_sign_calls == 6:
                    self.now = self.claims["exp"]
            return original(supplied)
        with mock.patch.object(self.capability, "sign", side_effect=signed), mock.patch.object(self.registry, "_sample_time", side_effect=clock):
            self.assert_unavailable(lambda: self.issuer.issue("access-a", self.claims))
        self.assertGreaterEqual(after_sign_calls, 7)

    def test_defensive_claim_snapshot_prevents_caller_mutation_during_sign(self):
        original = self.capability.sign
        def mutate(handle, content):
            self.claims["sub"] = "changed-subject"
            self.claims["case_ids"].append("case-b")
            return original(handle, content)
        with mock.patch.object(self.capability, "sign", side_effect=mutate):
            token = self.issuer.issue("access-a", self.claims)
        identity = self.verify(token)
        self.assertEqual(identity.subject, "fixture-user")
        self.assertEqual(identity.case_ids, frozenset({"case-a"}))

    def test_bootstrap_never_reuses_key_id_and_cap_is_bounded(self):
        with mock.patch.object(signer_module.rsa, "generate_private_key", side_effect=AssertionError("Unexpected generation")) as generation:
            self.assert_unavailable(lambda: self.create_key("access-a"))
            with mock.patch.object(signer_module, "MAX_FIXTURE_KEYS", 1):
                self.assert_unavailable(lambda: self.create_key("access-b"))
            generation.assert_not_called()

    def test_backend_errors_are_generic_and_do_not_echo_sensitive_context(self):
        with mock.patch.object(self.capability, "sign", side_effect=RuntimeError("sensitive-key-or-claims-material")):
            with self.assertRaises(TokenSigningUnavailable) as caught:
                self.issuer.issue("access-a", self.claims)
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
