"""Signed access-token profile tests; generated private keys exist only in memory."""
from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError
import json
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
import jwt

from model_release_assurance.production_identity import AccessIdentity, AccessTokenVerifier, TokenError
from model_release_assurance.production_identity.tokens import MAX_TOKEN_BYTES


class ProductionIdentityTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.weak_private = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        cls.ec_private = ec.generate_private_key(ec.SECP256R1())
        cls.issuer = "https://issuer.example.invalid"
        cls.audience = "government-resource-server"
        cls.now = 1_800_000_000

    def setUp(self):
        self.verifier = AccessTokenVerifier(self.issuer, self.audience, {"primary": self.private.public_key()})
        self.claims = {"iss": self.issuer, "aud": self.audience, "sub": "owner", "client_id": "local-public-fixture",
                       "jti": "token-1", "iat": self.now, "nbf": self.now, "exp": self.now + 300,
                       "scope": "case:read case:submit", "case_ids": ["case-a"]}

    def token(self, claims=None, *, headers=None, key=None, algorithm="RS256"):
        return jwt.encode(self.claims if claims is None else claims, key or self.private,
                          algorithm=algorithm, headers=headers or {"typ": "at+jwt", "kid": "primary"})

    def raw_token(self, payload, header=None):
        header = header or b'{"alg":"RS256","typ":"at+jwt","kid":"primary"}'
        encoded = b".".join(base64.urlsafe_b64encode(part).rstrip(b"=") for part in (header, payload))
        signature = self.private.sign(encoded, padding.PKCS1v15(), hashes.SHA256())
        return (encoded + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode("ascii")

    def assert_rejected(self, token, *, now=None):
        with self.assertRaises(TokenError) as caught:
            self.verifier.verify(token, now=self.now if now is None else now)
        self.assertEqual(str(caught.exception), "Access token rejected")
        self.assertIsNone(caught.exception.__cause__)

    def test_signed_access_identity_is_exact_and_immutable(self):
        identity = self.verifier.verify(self.token(), now=self.now)
        self.assertIsInstance(identity, AccessIdentity)
        self.assertEqual(identity.issuer, self.issuer)
        self.assertEqual(identity.subject, "owner")
        self.assertEqual(identity.client_id, "local-public-fixture")
        self.assertEqual(identity.token_id, "token-1")
        self.assertEqual(identity.key_id, "primary")
        self.assertEqual(identity.issued_at, self.now)
        self.assertEqual(identity.expires_at, self.now + 300)
        self.assertEqual(identity.scopes, frozenset({"case:read", "case:submit"}))
        self.assertEqual(identity.case_ids, frozenset({"case-a"}))
        self.assertIsNone(identity.acr)
        self.assertIsNone(identity.auth_time)
        with self.assertRaises(FrozenInstanceError):
            identity.subject = "administrator"
        with self.assertRaises(FrozenInstanceError):
            self.verifier.issuer = "another-issuer"

    def test_application_access_typ_and_signed_optional_auth_context(self):
        claims = dict(self.claims, acr="urn:agency:mfa", auth_time=self.now - 60)
        identity = self.verifier.verify(self.token(claims, headers={"typ": "application/at+jwt", "kid": "primary"}), now=self.now)
        self.assertEqual(identity.acr, "urn:agency:mfa")
        self.assertEqual(identity.auth_time, self.now - 60)
        for optional in ({"acr": "urn:agency:mfa"}, {"auth_time": self.now}):
            with self.subTest(optional=optional):
                identity = self.verifier.verify(self.token(dict(self.claims, **optional)), now=self.now)
                self.assertEqual(identity.acr, optional.get("acr"))
                self.assertEqual(identity.auth_time, optional.get("auth_time"))

    def test_configuration_accepts_public_pem_and_copies_key_map(self):
        pem = self.private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for material in (pem, pem.decode("ascii")):
            mapping = {"primary": material}
            verifier = AccessTokenVerifier(self.issuer, self.audience, mapping)
            mapping["primary"] = self.other_private.public_key()
            self.assertEqual(verifier.verify(self.token(), now=self.now).subject, "owner")
            with self.assertRaises(TypeError):
                verifier._keys["primary"] = self.other_private.public_key()

    def test_missing_invalid_private_weak_and_non_rsa_keys_fail_configuration(self):
        private_pem = self.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        candidates = ({}, None, {"primary": b"not a key"}, {"primary": private_pem}, {"primary": self.private},
                      {"primary": self.weak_private.public_key()}, {"primary": self.ec_private.public_key()},
                      {"https://evil.invalid/key": self.private.public_key()}, {"": self.private.public_key()},
                      {str(number): self.private.public_key() for number in range(33)})
        for keys in candidates:
            with self.subTest(keys_type=type(keys).__name__), self.assertRaises(TokenError) as caught:
                AccessTokenVerifier(self.issuer, self.audience, keys)
            self.assertEqual(str(caught.exception), "Invalid access-token verifier configuration")

    def test_configuration_issuer_audience_and_ttl_must_be_bounded_exact_values(self):
        keys = {"primary": self.private.public_key()}
        for issuer, audience, ttl in (("", self.audience, 300), (self.issuer, "*", 300), (self.issuer, [], 300),
                                      (self.issuer, self.audience, True), (self.issuer, self.audience, 0),
                                      (self.issuer, self.audience, 301), (self.issuer, self.audience, 2.5)):
            with self.subTest(ttl=ttl), self.assertRaises(TokenError):
                AccessTokenVerifier(issuer, audience, keys, max_ttl_seconds=ttl)
        verifier = AccessTokenVerifier(self.issuer, self.audience, keys, max_ttl_seconds=60)
        with self.assertRaises(TokenError):
            verifier.verify(self.token(), now=self.now)
        self.assertEqual(verifier.verify(self.token(dict(self.claims, exp=self.now + 60)), now=self.now).expires_at, self.now + 60)

    def test_wrong_signing_key_unknown_key_and_token_key_urls_are_rejected(self):
        self.assert_rejected(self.token(key=self.other_private))
        for headers in ({"typ": "at+jwt", "kid": "unknown"}, {"typ": "at+jwt", "kid": "https://evil.invalid/key"},
                        {"typ": "at+jwt", "kid": "primary", "jku": "https://evil.invalid/keys"},
                        {"typ": "at+jwt", "kid": "primary", "jwk": {"kty": "RSA"}},
                        {"typ": "at+jwt", "kid": "primary", "x5u": "https://evil.invalid/cert"}):
            with self.subTest(fields=list(headers)):
                self.assert_rejected(self.token(headers=headers))

    def test_algorithm_confusion_none_hmac_and_id_token_types_are_rejected(self):
        self.assert_rejected(self.token(key=b"test-only-hmac-secret-material-0000000000", algorithm="HS256"))
        none = self.raw_token(json.dumps(self.claims).encode(), b'{"alg":"none","typ":"at+jwt","kid":"primary"}')
        self.assert_rejected(none)
        for typ in ("JWT", "id+jwt", "AT+JWT", "", None):
            with self.subTest(typ=typ):
                self.assert_rejected(self.token(headers={"typ": typ, "kid": "primary"}))
        self.assert_rejected(self.token(headers={"kid": "primary"}))
        self.assert_rejected(self.token(headers={"typ": "at+jwt"}))

    def test_pinned_issuer_and_single_audience_have_no_coercions(self):
        for field, value in (("iss", self.issuer + "/"), ("iss", "https://other.example.invalid"),
                              ("aud", "wrong"), ("aud", [self.audience]), ("aud", [self.audience, "other"]),
                              ("aud", True), ("iss", [self.issuer])):
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.raw_token(json.dumps(dict(self.claims, **{field: value})).encode()))

    def test_required_claims_and_unknown_roles_claims_are_rejected(self):
        for name in self.claims:
            claims = dict(self.claims)
            del claims[name]
            with self.subTest(missing=name):
                self.assert_rejected(self.token(claims))
        for name, value in (("roles", ["admin"]), ("role", "owner"), ("groups", ["all"]), ("agency", "agency-a"), ("nonce", "id-token")):
            with self.subTest(unknown=name):
                self.assert_rejected(self.token(dict(self.claims, **{name: value})))

    def test_expiry_future_and_inconsistent_time_intervals_are_rejected(self):
        for changes in ({"exp": self.now}, {"exp": self.now - 1}, {"iat": self.now + 1}, {"nbf": self.now + 1},
                        {"nbf": self.now - 1}, {"exp": self.now + 301}, {"iat": self.now - 1},
                        {"nbf": self.now + 301}, {"auth_time": self.now + 1}):
            with self.subTest(changes=changes):
                self.assert_rejected(self.token(dict(self.claims, **changes)))
        self.assertEqual(self.verifier.verify(self.token(), now=self.now + 299).subject, "owner")
        self.assert_rejected(self.token(), now=self.now + 300)

    def test_time_claims_and_injected_clock_are_nonnegative_integers_not_bools(self):
        for field in ("iat", "nbf", "exp", "auth_time"):
            for value in (True, False, str(self.now), float(self.now), -1, None, 2**53):
                with self.subTest(field=field, value=value):
                    self.assert_rejected(self.token(dict(self.claims, **{field: value})))
        for value in (True, False, str(self.now), float(self.now), -1, 2**53):
            with self.subTest(now=value):
                self.assert_rejected(self.token(), now=value)

    def test_subject_client_and_token_ids_are_bounded_nonempty_strings(self):
        for field in ("sub", "client_id", "jti", "acr"):
            for value in ("", None, True, 1, ["owner"], "x" * 257, "embedded\nnewline", "*", "contains space"):
                with self.subTest(field=field, type=type(value).__name__):
                    self.assert_rejected(self.token(dict(self.claims, **{field: value})))

    def test_scopes_are_unique_bounded_canonical_exact_values_without_wildcards(self):
        for value in ("", [], None, "*", "case:*", "case:?", "case:[ab]", "case:read case:read", " case:read",
                      "case:read ", "case:read  case:submit", "case:read\tcase:submit", "s" * 129,
                      " ".join("scope-" + str(number) for number in range(65))):
            with self.subTest(type=type(value).__name__):
                self.assert_rejected(self.token(dict(self.claims, scope=value)))

    def test_case_ids_are_unique_bounded_json_lists_without_wildcards(self):
        for value in ([], "case-a", None, [True], ["*"], ["case-*"], ["case-a", "case-a"], [""], ["a" * 129],
                      ["case-" + str(number) for number in range(65)]):
            with self.subTest(type=type(value).__name__):
                self.assert_rejected(self.token(dict(self.claims, case_ids=value)))

    def test_duplicate_headers_claims_and_nonfinite_or_huge_json_numbers_are_rejected(self):
        payload = json.dumps(self.claims, separators=(",", ":")).encode()
        self.assert_rejected(self.raw_token(payload, b'{"alg":"RS256","typ":"at+jwt","kid":"primary","kid":"primary"}'))
        duplicate = payload[:-1] + b',"sub":"attacker"}'
        self.assert_rejected(self.raw_token(duplicate))
        for value in (b"NaN", b"Infinity", b"-Infinity", b"1e999", b"9" * 5000):
            changed = payload.replace(str(self.now).encode(), value, 1)
            with self.subTest(size=len(value)):
                self.assert_rejected(self.raw_token(changed))

    def test_malformed_bounded_segments_and_unknown_headers_are_rejected(self):
        token = self.token()
        for value in (None, token.encode(), "", token + ".extra", "a.b", ".".join(["", "", ""]),
                      "x" * (MAX_TOKEN_BYTES + 1), token + "=", " " + token, "é" + token):
            with self.subTest(type=type(value).__name__):
                self.assert_rejected(value)
        header, payload, signature = token.split(".")
        self.assert_rejected(".".join((header + "=", payload, signature)))
        self.assert_rejected(self.raw_token(b"[]"))
        self.assert_rejected(self.raw_token(b"\xff"))
        self.assert_rejected(self.raw_token(json.dumps(self.claims).encode(), b'{"alg":"RS256","typ":"at+jwt","kid":"primary","crit":[]}'))
        self.assert_rejected(self.raw_token(json.dumps(dict(self.claims, sub="x" * 9000)).encode()))

    def test_signature_tampering_and_payload_tampering_never_return_identity(self):
        token = self.token()
        header, payload, signature = token.split(".")
        alternate = self.token(dict(self.claims, sub="attacker")).split(".")[1]
        self.assert_rejected(".".join((header, alternate, signature)))
        changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        self.assert_rejected(".".join((header, payload, changed_signature)))


if __name__ == "__main__":
    unittest.main()
