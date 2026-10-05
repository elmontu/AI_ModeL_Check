"""Memory-only RSA worker-evidence signatures under current fixture trust.

This is a distinct domain and key purpose from access tokens. A local signature
proves integrity under an ephemeral pinned fixture key; it is not attestation,
managed-key custody, non-exportability or an authorization to release anything.
"""
from __future__ import annotations

import base64
from dataclasses import asdict
import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .contracts import (
    EvidenceError, canonical_bytes, strict_json, validate_statement, validate_digest,
    _identifier, _integer,
)
from ..production_trust.registry import FixtureTrustRegistry, KeyRegistration, TrustProfile

DOMAIN = b"mra-worker-evidence/v1\x00"
_ENVELOPE_FIELDS = frozenset({
    "schema", "algorithm", "key_id", "key_fingerprint", "profile", "owner_id", "statement", "signature",
})
_PROFILE_FIELDS = frozenset({"agency_id", "environment", "issuer", "audience", "purpose"})


def _reject():
    raise EvidenceError("Worker evidence rejected")


def _profile(profile):
    if type(profile) is not TrustProfile or profile.purpose != "worker_evidence":
        _reject()
    return TrustProfile(**asdict(profile))


def _registry(registry):
    if type(registry) is not FixtureTrustRegistry:
        _reject()
    return registry


def _time_window(statement, record, profile, owner_id, now):
    context = statement["context"]
    if (context["agency_id"] != profile.agency_id or context["worker_id"] != owner_id
            or not record.not_before <= statement["issued_at"] <= now < statement["expires_at"] <= record.not_after
            or not statement["challenge"]["issued_at"] <= now < statement["challenge"]["expires_at"]):
        _reject()


def _current(registry, profile, owner_id, key_id, statement, *, revision=None, record=None):
    # Revision samples the registry clock. Take the final sample only afterward,
    # then use the no-resampling eligibility API at precisely that same instant.
    observed_revision = registry.revision
    now = registry.current_time()
    current = registry.signing_key_at(key_id, profile, owner_id=owner_id, now=now)
    if ((revision is not None and observed_revision != revision)
            or (record is not None and current != record)):
        _reject()
    _time_window(statement, current, profile, owner_id, now)
    return observed_revision, current


def _envelope(raw, profile, owner_id):
    result = strict_json(raw)
    if type(result) is not dict or set(result) != _ENVELOPE_FIELDS or canonical_bytes(result) != raw:
        _reject()
    if (type(result["schema"]) is not str or result["schema"] != "mra-worker-envelope/v1"
            or type(result["algorithm"]) is not str or result["algorithm"] != "RS256"):
        _reject()
    _identifier(result["key_id"])
    _identifier(result["owner_id"])
    validate_digest(result["key_fingerprint"])
    if type(result["profile"]) is not dict or set(result["profile"]) != _PROFILE_FIELDS:
        _reject()
    if TrustProfile(**result["profile"]) != profile or result["owner_id"] != owner_id:
        _reject()
    result["statement"] = validate_statement(result["statement"])
    encoded = result["signature"]
    if type(encoded) is not str or not 1 <= len(encoded) <= 1400:
        _reject()
    signature = base64.b64decode(encoded, validate=True)
    if base64.b64encode(signature).decode("ascii") != encoded:
        _reject()
    unsigned = {key: value for key, value in result.items() if key != "signature"}
    return result, signature, DOMAIN + canonical_bytes(unsigned)


def verify_envelope(raw, registry, profile, owner_id):
    """Verify exact bytes and return owned statement/metadata under current trust.

    Rotation's verify-only overlap is intentionally unsupported for worker
    evidence. Call again under the same registry lock at the ledger commit.
    """
    try:
        registry, profile = _registry(registry), _profile(profile)
        _identifier(owner_id)
        envelope, signature, message = _envelope(raw, profile, owner_id)
        statement = envelope["statement"]
        with registry.operation_lock:
            revision, record = _current(registry, profile, owner_id, envelope["key_id"], statement)
            if envelope["key_fingerprint"] != record.fingerprint or len(signature) != record.public_key.key_size // 8:
                _reject()
            record.public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
            result = {"statement": statement, "key_id": record.key_id,
                      "key_fingerprint": record.fingerprint, "envelope_sha256": hashlib.sha256(raw).hexdigest()}
            _current(registry, profile, owner_id, record.key_id, statement, revision=revision, record=record)
            return result
    except Exception:
        raise EvidenceError("Worker evidence rejected") from None


class MemoryFixtureEvidenceSigner:
    """One generated in-process worker key; no generic/private-key export API."""

    __slots__ = ("_private", "_registration")

    def __init__(self, profile, owner_id, key_id, not_before, not_after):
        try:
            profile = _profile(profile)
            _identifier(owner_id)
            _identifier(key_id)
            _integer(not_before)
            _integer(not_after)
            if not_before >= not_after:
                _reject()
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            self._registration = KeyRegistration(key_id, profile, owner_id, pem, not_before, not_after)
            self._private = private
        except Exception:
            raise EvidenceError("Worker evidence rejected") from None

    @property
    def registration(self):
        return self._registration

    def sign(self, statement, registry):
        try:
            registry = _registry(registry)
            # Snapshot before acquiring authority; no caller mutation can change
            # the statement between validation, signature and final checks.
            statement = validate_statement(statement)
            registration = self.registration
            profile, owner_id = registration.profile, registration.owner_id
            with registry.operation_lock:
                revision, record = _current(registry, profile, owner_id, registration.key_id, statement, record=registration)
                unsigned = {"schema": "mra-worker-envelope/v1", "algorithm": "RS256", "key_id": record.key_id,
                    "key_fingerprint": record.fingerprint, "profile": asdict(profile), "owner_id": owner_id, "statement": statement}
                signature = self._private.sign(DOMAIN + canonical_bytes(unsigned), padding.PKCS1v15(), hashes.SHA256())
                raw = canonical_bytes({**unsigned, "signature": base64.b64encode(signature).decode("ascii")})
                # Independent public-key verification also catches a broken or
                # substituted private operation before any signature is returned.
                verify_envelope(raw, registry, profile, owner_id)
                _current(registry, profile, owner_id, record.key_id, statement, revision=revision, record=record)
                return raw
        except Exception:
            raise EvidenceError("Worker evidence rejected") from None
