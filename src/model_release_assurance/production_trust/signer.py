"""Memory-only signing provider and bounded access-token issuer for public fixtures.

The provider protocol is an adapter boundary, not a real KMS/HSM integration.
Private keys are accessible to this Python process; no non-exportability, IAM,
independent custody, durable trust registry or production authority is claimed.
There is no private-key import/export, persistence, login or HTTP minting route.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import re
from threading import RLock
from typing import Protocol, runtime_checkable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ..production_identity.tokens import (AccessTokenVerifier, MAX_HEADER_BYTES, MAX_INTEGER,
    MAX_PAYLOAD_BYTES, MAX_TOKEN_BYTES, OPTIONAL_CLAIMS, REQUIRED_CLAIMS)
from .registry import KeyRegistration, TrustProfile

MAX_FIXTURE_KEYS = 32
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class TokenSigningUnavailable(RuntimeError):
    """Safe generic failure: never contains claims, token bytes or key material."""


def _unavailable():
    raise TokenSigningUnavailable("Fixture token signing unavailable")


def _identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _unavailable()
    return value


def _text(value, maximum):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _unavailable()
    if any(ord(char) < 33 or ord(char) > 126 or char in "*?[]" for char in value):
        _unavailable()
    return value


def _integer(value):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        _unavailable()
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _segment(content):
    return base64.urlsafe_b64encode(content).rstrip(b"=")


@dataclass(frozen=True, slots=True)
class ProviderKeyDescription:
    key_handle: str
    key_id: str
    version_id: str
    profile: TrustProfile
    owner_id: str
    public_key_pem: bytes = field(repr=False)
    fingerprint: str


@runtime_checkable
class SigningProvider(Protocol):
    """Bound public-description/sign-only interface; never exports private keys."""

    def describe(self, key_handle: str) -> ProviderKeyDescription: ...

    def sign(self, key_handle: str, signing_input: bytes) -> bytes: ...


@dataclass(frozen=True, slots=True)
class _FixtureKey:
    registration: KeyRegistration
    description: ProviderKeyDescription
    private_key: rsa.RSAPrivateKey = field(repr=False)


class MemoryFixtureSigningProvider:
    """Trusted fixture bootstrap only; generated keys live solely in memory.

    A unique public key_id is this fixture's immutable handle. Its SPKI SHA256
    is the content-defined immutable version. Real provider handle/version/IAM
    binding would need a separate reviewed adapter and deployment acceptance.
    """

    def __init__(self):
        self._lock = RLock()
        self._keys: dict[str, _FixtureKey] = {}
        self._available = True
        self._disabled: set[str] = set()

    def create_key(self, *, key_id, profile, owner_id, not_before, not_after):
        """Generate a new RSA2048 fixture key; return public registration only."""
        try:
            _identifier(key_id)
            _identifier(owner_id)
            if type(profile) is not TrustProfile:
                _unavailable()
            _integer(not_before)
            _integer(not_after)
            if not_before >= not_after:
                _unavailable()
            with self._lock:
                if not self._available or key_id in self._keys or len(self._keys) >= MAX_FIXTURE_KEYS:
                    _unavailable()
                private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
                record = KeyRegistration(key_id=key_id, profile=profile, owner_id=owner_id,
                                         public_key_pem=public, not_before=not_before, not_after=not_after)
                description = ProviderKeyDescription(key_handle=key_id, key_id=key_id, version_id=record.fingerprint,
                            profile=profile, owner_id=owner_id, public_key_pem=record.public_key_pem,
                            fingerprint=record.fingerprint)
                self._keys[key_id] = _FixtureKey(record, description, private)
                return record
        except Exception:
            raise TokenSigningUnavailable("Fixture token signing unavailable") from None

    def bind(self, *, profile, owner_id):
        """Trusted in-process bootstrap grants a profile/owner-limited capability.

        Supplying owner_id is not authentication or an assertion of cloud IAM.
        Do not expose this method through an HTTP/admin route.
        """
        if type(profile) is not TrustProfile or profile.purpose != "access_token":
            _unavailable()
        _identifier(owner_id)
        return _BoundFixtureSigningProvider(self, profile, owner_id)

    def set_available(self, available):
        """Trusted outage simulation; not a production control-plane endpoint."""
        if type(available) is not bool:
            _unavailable()
        with self._lock:
            self._available = available

    def set_key_enabled(self, key_id, enabled):
        """Trusted fixture key disablement; registry revocation remains separate."""
        if type(enabled) is not bool:
            _unavailable()
        with self._lock:
            if key_id not in self._keys:
                _unavailable()
            if enabled:
                self._disabled.discard(key_id)
            else:
                self._disabled.add(key_id)

    def _entry(self, key_handle, profile, owner_id):
        _identifier(key_handle)
        entry = self._keys.get(key_handle)
        if (not self._available or key_handle in self._disabled or entry is None
                or entry.registration.profile != profile or entry.registration.owner_id != owner_id
                or profile.purpose != "access_token"):
            _unavailable()
        return entry


class _BoundFixtureSigningProvider:
    """Capability with no caller-selected owner/profile on individual operations."""

    def __init__(self, provider, profile, owner_id):
        self._provider, self._profile, self._owner_id = provider, profile, owner_id

    def describe(self, key_handle):
        try:
            with self._provider._lock:
                return self._provider._entry(key_handle, self._profile, self._owner_id).description
        except Exception:
            raise TokenSigningUnavailable("Fixture token signing unavailable") from None

    def sign(self, key_handle, signing_input):
        try:
            if type(signing_input) is not bytes or not 1 <= len(signing_input) <= MAX_TOKEN_BYTES or not signing_input.isascii():
                _unavailable()
            with self._provider._lock:
                entry = self._provider._entry(key_handle, self._profile, self._owner_id)
                return entry.private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            raise TokenSigningUnavailable("Fixture token signing unavailable") from None


def _prepared_claims(claims, profile, record, now):
    """Validate the existing narrow access profile BEFORE any private operation.

    This explicit builder mirrors AccessTokenVerifier's public profile. The
    resulting signed token is also independently verified by that verifier.
    """
    if type(claims) is not dict or not len(REQUIRED_CLAIMS) <= len(claims) <= len(REQUIRED_CLAIMS | OPTIONAL_CLAIMS):
        _unavailable()
    if not REQUIRED_CLAIMS <= set(claims) or set(claims) - REQUIRED_CLAIMS - OPTIONAL_CLAIMS:
        _unavailable()
    owned = dict(claims)
    if type(owned["case_ids"]) is list:
        owned["case_ids"] = list(owned["case_ids"])
    if _text(owned["iss"], 512) != profile.issuer or _text(owned["aud"], 256) != profile.audience:
        _unavailable()
    for name in ("sub", "jti", "client_id"):
        _text(owned[name], 256)
    issued_at, not_before, expires_at = (_integer(owned[name]) for name in ("iat", "nbf", "exp"))
    if (not record.not_before <= issued_at <= not_before <= now < expires_at <= record.not_after
            or not 0 < expires_at - issued_at <= 300):
        _unavailable()
    raw_scope = owned["scope"]
    if type(raw_scope) is not str or not 1 <= len(raw_scope) <= 4096:
        _unavailable()
    scopes = raw_scope.split(" ")
    if not 1 <= len(scopes) <= 64 or len(set(scopes)) != len(scopes):
        _unavailable()
    for scope in scopes:
        _text(scope, 128)
    cases = owned["case_ids"]
    if type(cases) is not list or not 1 <= len(cases) <= 64:
        _unavailable()
    for case in cases:
        _text(case, 128)
    if len(set(cases)) != len(cases):
        _unavailable()
    if "acr" in owned:
        _text(owned["acr"], 256)
    if "auth_time" in owned and _integer(owned["auth_time"]) > issued_at:
        _unavailable()
    content = _canonical(owned)
    if len(content) > MAX_PAYLOAD_BYTES:
        _unavailable()
    return owned, content


class FixtureTokenIssuer:
    """Sign exact trusted fixture claims under one current-registry operation lock.

    The input is trusted fixture setup, not a user login/token issuance API.
    All failures are generic. There is no cached key/approval or signing fallback.
    """

    def __init__(self, registry, provider: SigningProvider, profile: TrustProfile, owner_id: str):
        if (type(profile) is not TrustProfile or profile.purpose != "access_token"
                or not isinstance(provider, SigningProvider)
                or not hasattr(registry, "operation_lock") or not callable(getattr(registry, "signing_key", None))):
            _unavailable()
        _identifier(owner_id)
        self._registry, self._provider, self._profile, self._owner_id = registry, provider, profile, owner_id

    def _description(self, record):
        description = self._provider.describe(record.key_id)
        if (type(description) is not ProviderKeyDescription
                or description.key_handle != record.key_id or description.key_id != record.key_id
                or description.version_id != record.fingerprint or description.fingerprint != record.fingerprint
                or description.owner_id != self._owner_id or description.profile != self._profile
                or description.public_key_pem != record.public_key_pem):
            _unavailable()
        # Recompute the public fingerprint as well as comparing provider labels.
        public = serialization.load_pem_public_key(description.public_key_pem)
        if not isinstance(public, rsa.RSAPublicKey):
            _unavailable()
        fingerprint = hashlib.sha256(public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
        if fingerprint != record.fingerprint:
            _unavailable()
        return description

    def _same_current_key(self, key_id, record, revision, now):
        current = self._registry.signing_key(key_id, self._profile, owner_id=self._owner_id, now=now)
        if current != record or self._registry.revision != revision:
            _unavailable()
        return current

    def issue(self, key_id, claims):
        try:
            _identifier(key_id)
            with self._registry.operation_lock:
                now = self._registry.current_time()
                record = self._registry.signing_key(key_id, self._profile, owner_id=self._owner_id, now=now)
                revision = self._registry.revision
                description = self._description(record)
                owned_claims, payload = _prepared_claims(claims, self._profile, record, now)
                header = _canonical({"alg": "RS256", "typ": "at+jwt", "kid": key_id})
                if len(header) > MAX_HEADER_BYTES:
                    _unavailable()
                signing_input = _segment(header) + b"." + _segment(payload)
                signature_size = (record.public_key.key_size + 7) // 8
                if len(signing_input) + 1 + len(_segment(bytes(signature_size))) > MAX_TOKEN_BYTES:
                    _unavailable()
                # Description/profile validation can take time. Recheck current
                # signing permission and claims before the private operation.
                now = self._registry.current_time()
                self._same_current_key(key_id, record, revision, now)
                _prepared_claims(owned_claims, self._profile, record, now)
                signature = self._provider.sign(description.key_handle, signing_input)
                if type(signature) is not bytes or len(signature) != signature_size:
                    _unavailable()
                token = (signing_input + b"." + _segment(signature)).decode("ascii")
                now = self._registry.current_time()
                self._same_current_key(key_id, record, revision, now)
                verifier = AccessTokenVerifier(self._profile.issuer, self._profile.audience, {key_id: record.public_key})
                identity = verifier.verify(token, now=now)
                # Do not return a signature minted during an outage, rotation,
                # revocation, key expiry or changed provider description.
                if self._description(record) != description:
                    _unavailable()
                now = self._registry.current_time()
                self._same_current_key(key_id, record, revision, now)
                _prepared_claims(owned_claims, self._profile, record, now)
                # signing_key/revision also observe time. This must be the last
                # operation: check the independently verified identity against
                # one newly sampled current registry/key/token deadline. The
                # held operation lock preserves the preceding active status.
                self._registry.check_current(identity, self._profile)
                return token
        except Exception:
            raise TokenSigningUnavailable("Fixture token signing unavailable") from None
