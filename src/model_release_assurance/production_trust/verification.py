"""Current-registry adapter for the existing strict RS256 access-token profile."""
from __future__ import annotations

from dataclasses import dataclass

from ..production_identity.tokens import AccessTokenVerifier, TokenError
from ..production_identity.policy import IdentityUnavailable, PermissionDenied
from .registry import FixtureTrustRegistry, TrustDenied, TrustProfile, TrustUnavailable


@dataclass(frozen=True, slots=True)
class RegistryAccessTokenVerifier:
    """Use trusted public metadata only; registry and identity share one lock.

    The registry owns the clock. Identity/bootstrap must use that same trusted
    clock; an identity observation from its future is refused, not tolerated.
    This adapter has no discovery, key URL, cached-trust or private-key fallback.
    """
    registry: FixtureTrustRegistry
    profile: TrustProfile
    max_ttl_seconds: int = 300

    def __post_init__(self):
        if not isinstance(self.registry, FixtureTrustRegistry) or not isinstance(self.profile, TrustProfile):
            raise ValueError("An explicit fixture trust registry and profile are required")
        if self.profile.purpose != "access_token":
            raise ValueError("Only access-token verification is implemented")
        if type(self.max_ttl_seconds) is not int or not 1 <= self.max_ttl_seconds <= 300:
            raise ValueError("Invalid access-token lifetime")

    @property
    def agency_id(self):
        return self.profile.agency_id

    @property
    def operation_lock(self):
        return self.registry.operation_lock

    def current_time(self):
        try:
            return self.registry.current_time()
        except TrustUnavailable:
            raise IdentityUnavailable("Current key trust clock unavailable") from None

    def verify(self, token: str, *, now: int):
        with self.operation_lock:
            try:
                keys = self.registry.public_keys(self.profile, now=now)
                checked_at = self.registry.current_time()
                verifier = AccessTokenVerifier(self.profile.issuer, self.profile.audience,
                                               keys, self.max_ttl_seconds)
                identity = verifier.verify(token, now=checked_at)
                # Resample after cryptography: key/overlap/registry deadlines
                # still govern the returned credential.
                self.registry.check_current(identity, self.profile, now=checked_at)
                return identity
            except TrustUnavailable:
                raise IdentityUnavailable("Current key trust unavailable") from None
            except TrustDenied:
                raise TokenError("Access token rejected") from None

    def check_current(self, identity, *, now: int):
        """Recheck saved reviewers and grants without reusing cached key trust."""
        with self.operation_lock:
            try:
                self.registry.check_current_at(identity, self.profile, now=now)
            except TrustUnavailable:
                raise IdentityUnavailable("Current key trust unavailable") from None
            except TrustDenied:
                raise PermissionDenied("Credential key is not currently eligible") from None
