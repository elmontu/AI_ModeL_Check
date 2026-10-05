"""In-memory public-fixture RS256 trust registry with bounded permanent tombstones.

Lifecycle calls are trusted Python bootstrap operations, not an authenticated
administration API. Multiple active keys per exact profile permit staging; each
signer must choose an exact active key. Recovery refresh/availability changes and
emergency revocation may run while stale or unavailable, but always require the
current revision and a valid non-rollback clock. There is no persistence,
independent witness, managed KMS/HSM, administrator isolation or restart recovery.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
import hashlib
import re
from threading import RLock
from types import MappingProxyType

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..production_identity.tokens import AccessIdentity

MAX_KEYS = 32
MAX_FRESH_SECONDS = 300
MAX_INTEGER = 2**53 - 1
PURPOSES = frozenset({"access_token", "worker_evidence", "policy", "registry", "gateway"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PUBLIC_PEM = re.compile(rb"[ \t\r\n]*-----BEGIN (PUBLIC KEY|RSA PUBLIC KEY)-----\r?\n(?:[A-Za-z0-9+/=]+\r?\n)+-----END \1-----[ \t\r\n]*\Z")


class TrustDenied(ValueError):
    """Trust profile, registration or current eligibility is invalid."""


class TrustUnavailable(RuntimeError):
    """Clock, freshness or availability prevents a current trust decision."""


class TrustConflict(ValueError):
    """A lifecycle revision, tombstone or bounded capacity conflicts."""


def _deny():
    raise TrustDenied("Trust key is not eligible")


def _unavailable():
    raise TrustUnavailable("Trust registry unavailable")


def _conflict():
    raise TrustConflict("Trust registry mutation conflict")


def _integer(value):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        _deny()
    return value


def _text(value, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _deny()
    if any(ord(char) < 33 or ord(char) > 126 or char in "*?[]" for char in value):
        _deny()
    return value


def _identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _deny()
    return value


@dataclass(frozen=True, slots=True)
class TrustProfile:
    agency_id: str
    environment: str
    issuer: str
    audience: str
    purpose: str

    def __post_init__(self):
        _identifier(self.agency_id)
        _text(self.issuer, 512)
        _text(self.audience)
        if type(self.environment) is not str or self.environment != "public_fixture":
            _deny()
        if type(self.purpose) is not str or self.purpose not in PURPOSES:
            _deny()


def _profile(profile):
    if type(profile) is not TrustProfile:
        _deny()
    return TrustProfile(profile.agency_id, profile.environment, profile.issuer, profile.audience, profile.purpose)


@dataclass(frozen=True, slots=True)
class KeyRegistration:
    key_id: str
    profile: TrustProfile
    owner_id: str
    public_key_pem: bytes | str = field(repr=False)
    not_before: int
    not_after: int
    fingerprint: str = field(init=False)
    _public_key: rsa.RSAPublicKey = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        try:
            _identifier(self.key_id)
            _identifier(self.owner_id)
            profile = _profile(self.profile)
            _integer(self.not_before)
            _integer(self.not_after)
            if self.not_after <= self.not_before:
                _deny()
            material = self.public_key_pem
            if type(material) is str:
                material = material.encode("ascii")
            if (type(material) is not bytes or not 1 <= len(material) <= 16384
                    or not _PUBLIC_PEM.fullmatch(material)):
                _deny()
            key = serialization.load_pem_public_key(material)
            if not isinstance(key, rsa.RSAPublicKey) or not 2048 <= key.key_size <= 8192:
                _deny()
            der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            pem = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            object.__setattr__(self, "profile", profile)
            object.__setattr__(self, "public_key_pem", pem)
            object.__setattr__(self, "fingerprint", hashlib.sha256(der).hexdigest())
            object.__setattr__(self, "_public_key", key)
        except (ValueError, TypeError, UnicodeError, UnsupportedAlgorithm):
            raise TrustDenied("Trust key is not eligible") from None

    @property
    def public_key(self):
        return self._public_key


def _record(record):
    if type(record) is not KeyRegistration:
        _deny()
    # Do not retain caller-owned or overridden cached key objects.
    return KeyRegistration(record.key_id, record.profile, record.owner_id, record.public_key_pem,
                           record.not_before, record.not_after)


@dataclass(frozen=True, slots=True)
class _Entry:
    record: KeyRegistration
    status: str
    issuance_cutoff: int | None = None
    verify_until: int | None = None


class FixtureTrustRegistry:
    def __init__(self, *, now: Callable[[], int], fresh_until: int):
        if not callable(now):
            _deny()
        self._lock = RLock()
        self._clock = now
        self._last_now = None
        current = self._sample_time()
        self._validate_fresh_until(fresh_until, current)
        self._fresh_until = fresh_until
        self._available = True
        self._revision = 1
        self._entries: dict[str, _Entry] = {}
        self._fingerprints: set[str] = set()

    @property
    def operation_lock(self):
        return self._lock

    @property
    def revision(self):
        with self._lock:
            self._sample_time()
            return self._revision

    def _sample_time(self, supplied=None):
        try:
            current = self._clock()
        except Exception:
            raise TrustUnavailable("Trust registry unavailable") from None
        if type(current) is not int or not 0 <= current <= MAX_INTEGER:
            _unavailable()
        if self._last_now is not None and current < self._last_now:
            _unavailable()
        self._last_now = current
        if supplied is not None and (type(supplied) is not int or not 0 <= supplied <= current):
            _unavailable()
        return current

    def current_time(self):
        """Sample only the monotonic fixture clock; eligibility methods check health."""
        with self._lock:
            return self._sample_time()

    def _current(self, supplied=None):
        current = self._sample_time(supplied)
        if not self._available or current >= self._fresh_until:
            _unavailable()
        return current

    def _expected(self, revision):
        if type(revision) is not int or revision != self._revision or self._revision >= MAX_INTEGER:
            _conflict()

    @staticmethod
    def _validate_fresh_until(fresh_until, current):
        _integer(fresh_until)
        if not current < fresh_until <= current + MAX_FRESH_SECONDS:
            _deny()

    def _new_record(self, record, current):
        record = _record(record)
        if record.key_id in self._entries or record.fingerprint in self._fingerprints or len(self._entries) >= MAX_KEYS:
            _conflict()
        if not record.not_before <= current < record.not_after:
            _deny()
        return record

    def enroll(self, record, *, expected_revision):
        with self._lock:
            current = self._current()
            self._expected(expected_revision)
            record = self._new_record(record, current)
            self._entries[record.key_id] = _Entry(record, "active")
            self._fingerprints.add(record.fingerprint)
            self._revision += 1
            return self._revision

    def rotate(self, old_key_id, new_record, *, expected_revision, overlap_seconds):
        with self._lock:
            current = self._current()
            self._expected(expected_revision)
            _identifier(old_key_id)
            if type(overlap_seconds) is not int or not 1 <= overlap_seconds <= 300:
                _deny()
            old = self._entries.get(old_key_id)
            if old is None or old.status != "active" or not old.record.not_before <= current < old.record.not_after:
                _deny()
            new = self._new_record(new_record, current)
            if (new.profile, new.owner_id) != (old.record.profile, old.record.owner_id):
                _deny()
            # All validation completes before either entry changes.
            retired = replace(old, status="verify_only", issuance_cutoff=current,
                              verify_until=min(old.record.not_after, current + overlap_seconds))
            self._entries[old_key_id] = retired
            self._entries[new.key_id] = _Entry(new, "active")
            self._fingerprints.add(new.fingerprint)
            self._revision += 1
            return self._revision

    def revoke(self, key_id, *, expected_revision):
        with self._lock:
            self._sample_time()  # Emergency revocation remains possible during an outage.
            self._expected(expected_revision)
            _identifier(key_id)
            entry = self._entries.get(key_id)
            if entry is None:
                _deny()
            if entry.status == "revoked":
                _conflict()
            self._entries[key_id] = replace(entry, status="revoked")
            self._revision += 1
            return self._revision

    def refresh(self, *, fresh_until, expected_revision):
        with self._lock:
            current = self._sample_time()
            self._expected(expected_revision)
            self._validate_fresh_until(fresh_until, current)
            self._fresh_until = fresh_until
            self._revision += 1
            return self._revision

    def set_available(self, available, *, expected_revision):
        with self._lock:
            self._sample_time()
            self._expected(expected_revision)
            if type(available) is not bool:
                _deny()
            if available == self._available:
                _conflict()
            self._available = available
            self._revision += 1
            return self._revision

    def public_keys(self, profile, *, now=None) -> Mapping[str, rsa.RSAPublicKey]:
        with self._lock:
            current = self._current(now)
            profile = _profile(profile)
            result = {}
            for key_id, entry in self._entries.items():
                if entry.record.profile != profile or not entry.record.not_before <= current < entry.record.not_after:
                    continue
                if entry.status == "active" or (entry.status == "verify_only" and current < entry.verify_until):
                    result[key_id] = entry.record.public_key
            return MappingProxyType(result)

    def signing_key(self, key_id, profile, *, owner_id, now=None) -> KeyRegistration:
        with self._lock:
            current = self._current(now)
            profile = _profile(profile)
            _identifier(key_id)
            _identifier(owner_id)
            entry = self._entries.get(key_id)
            if (entry is None or entry.status != "active" or entry.record.profile != profile or entry.record.owner_id != owner_id
                    or not entry.record.not_before <= current < entry.record.not_after):
                _deny()
            return entry.record

    def signing_key_at(self, key_id, profile, *, owner_id, now) -> KeyRegistration:
        """Trusted server-only active key check at one shared-operation time.

        Caller must own operation_lock and supply the exact last clock sample.
        This mirrors check_current_at without allowing verify-only signing keys.
        """
        owns_lock = getattr(self._lock, "_is_owned", None)
        if owns_lock is None or not owns_lock():
            _unavailable()
        if type(now) is not int or now != self._last_now:
            _unavailable()
        if not self._available or now >= self._fresh_until:
            _unavailable()
        profile = _profile(profile)
        _identifier(key_id)
        _identifier(owner_id)
        entry = self._entries.get(key_id)
        if (entry is None or entry.status != "active" or entry.record.profile != profile or entry.record.owner_id != owner_id
                or not entry.record.not_before <= now < entry.record.not_after):
            _deny()
        return entry.record

    def check_current(self, identity, profile, *, now=None):
        """Apply current key eligibility after independent JWT signature verification."""
        with self._lock:
            self._check_identity_current(identity, profile, self._current(now))

    def check_current_at(self, identity, profile, *, now):
        """Trusted server-only check at an already sampled shared-operation time.

        Caller must already own ``operation_lock`` and pass the exact last clock
        sample from ``current_time``. This prevents an identity/grant operation
        from mixing multiple instants. Normal callers use ``check_current``.
        CPython RLock ownership introspection is required; otherwise fail closed.
        """
        owns_lock = getattr(self._lock, "_is_owned", None)
        if owns_lock is None or not owns_lock():
            _unavailable()
        if type(now) is not int or now != self._last_now:
            _unavailable()
        if not self._available or now >= self._fresh_until:
            _unavailable()
        self._check_identity_current(identity, profile, now)

    def _check_identity_current(self, identity, profile, current):
        profile = _profile(profile)
        if profile.purpose != "access_token" or type(identity) is not AccessIdentity:
            _deny()
        _text(identity.issuer, 512)
        for value in (identity.subject, identity.client_id, identity.token_id):
            _text(value)
        _identifier(identity.key_id)
        issued_at, expires_at = _integer(identity.issued_at), _integer(identity.expires_at)
        for values in (identity.scopes, identity.case_ids):
            if type(values) is not frozenset or not 1 <= len(values) <= 64:
                _deny()
            for value in values:
                _text(value, 128)
        if identity.acr is not None:
            _text(identity.acr)
        if identity.auth_time is not None and _integer(identity.auth_time) > issued_at:
            _deny()
        if identity.issuer != profile.issuer or not issued_at <= current < expires_at or not 0 < expires_at - issued_at <= 300:
            _deny()
        entry = self._entries.get(identity.key_id)
        if (entry is None or entry.record.profile != profile or entry.status not in {"active", "verify_only"}
                or not entry.record.not_before <= issued_at or expires_at > entry.record.not_after
                or not entry.record.not_before <= current < entry.record.not_after):
            _deny()
        if entry.status == "verify_only" and not (issued_at < entry.issuance_cutoff and current < entry.verify_until):
            _deny()
