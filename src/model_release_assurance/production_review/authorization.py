"""Additive current-authority bridge for local policy/review fixtures.

Only raw signed tokens enter access(). Contexts are trusted in-process
capabilities, never proof accepted from JSON. This does not modify PRD06 action
roles, create an agency identity, or authorize delivery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from weakref import WeakSet

from ..production_identity.policy import FixtureIdentityService, PermissionDenied, IdentityUnavailable
from ..production_trust.verification import RegistryAccessTokenVerifier
from ..production_trust.registry import TrustUnavailable

_ACTIONS = {
    "propose": ("proposal:submit", "model_owner"),
    "start": ("job:run", "test_operator"),
    "policy": ("case:read", "policy_authority"),
    "assess": ("review:assess", "assessor"),
    "approve": ("review:approve", "release_authority"),
    "read": ("case:read", None),
}
_REVIEWERS = frozenset({"policy", "assess", "approve"})


def _denied():
    raise PermissionDenied("Current independent review authority is required")


def _credential(identity, person_id):
    payload = {"issuer": identity.issuer, "subject": identity.subject,
        "client_id": identity.client_id, "token_id": identity.token_id,
        "key_id": identity.key_id, "issued_at": identity.issued_at,
        "expires_at": identity.expires_at, "scopes": sorted(identity.scopes),
        "case_ids": sorted(identity.case_ids), "acr": identity.acr,
        "auth_time": identity.auth_time, "person_id": person_id}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


@dataclass(frozen=True, repr=False, eq=False)
class _ReviewContext:
    _authorization: object = field(repr=False)
    _seal: object = field(repr=False)
    identity: object = field(repr=False)
    principal: object = field(repr=False)
    case: object = field(repr=False)
    action: str
    authority_revision: int
    trust_revision: int
    credential_sha256: str

    @property
    def actor(self):
        return {"person_id": self.principal.person_id, "authority_revision": self.authority_revision,
                "credential_sha256": self.credential_sha256}

    def recheck(self):
        return self._authorization.recheck_saved(self)

    def recheck_with(self, *others):
        return self._authorization.recheck_many((self, *others))


class ReviewAuthorization:
    """Trusted fixture bridge. Callers hold identity._lock across their mutation.

    Each method also acquires that same reentrant lock. Storage guards must call
    context.recheck() after lock waits/expensive work and just before commit;
    a final recheck is required before returning a current-authority decision.
    """
    def __init__(self, identity):
        if (type(identity) is not FixtureIdentityService
                or type(identity._verifier) is not RegistryAccessTokenVerifier
                or identity._lock is not identity._verifier.operation_lock):
            raise ValueError("An exact dynamic current-authority fixture is required")
        self._identity = identity
        self._trust = identity._verifier.registry
        self._seal = object()
        self._contexts = WeakSet()

    def _revision(self):
        try:
            return self._trust.revision
        except TrustUnavailable:
            raise IdentityUnavailable("Current review trust is unavailable") from None

    def _requirements(self, identity, principal, case, action, now):
        if type(action) is not str or action not in _ACTIONS:
            _denied()
        if principal.kind != "human":
            _denied()
        if action == "policy" and "review:policy" not in identity.scopes:
            _denied()
        role = _ACTIONS[action][1]
        if role is not None:
            matching = [grant for grant in self._identity._fresh(now).grants
                if (grant.person_id, grant.agency_id, grant.project_id, grant.case_id)
                == (principal.person_id, case.metadata.agency_id, case.metadata.project_id, case.metadata.case_id)]
            if len(matching) != 1 or role not in matching[0].roles:
                _denied()
        if action == "propose" and principal.person_id != case.metadata.submitter_person_id:
            _denied()
        if action in _REVIEWERS:
            self._identity._independent(principal, case)

    def access(self, token, case_id, action):
        """Verify a raw token, exact case/action, current role and canonical person."""
        if type(action) is not str or action not in _ACTIONS:
            _denied()
        with self._identity._lock:
            trust_revision = self._revision()
            now, identity, principal, case = self._identity._access(token, case_id, _ACTIONS[action][0])
            self._requirements(identity, principal, case, action, now)
            # Conservative recording occurs before the caller starts work, even
            # if later work fails. Aliases cannot restore review independence.
            if action == "start":
                case.operators.add(principal.person_id)
            context = _ReviewContext(self, self._seal, identity, principal, case.metadata, action,
                self._identity._authority.revision, trust_revision, _credential(identity, principal.person_id))
            self._contexts.add(context)
            context.recheck()
            return context

    def recheck_saved(self, context):
        """Revalidate this bridge's original signed identity, never caller claims."""
        return self.recheck_many((context,))

    def recheck_many(self, contexts):
        """Authorize every retained participant at one final current timestamp.

        Callers evaluate delegation/evidence deadlines against the returned time
        without another clock read. No previously checked reviewer is silently
        carried over from an earlier time sample.
        """
        if type(contexts) not in (list, tuple) or not 1 <= len(contexts) <= 32:
            _denied()
        contexts = tuple(contexts)
        with self._identity._lock:
            if any(type(context) is not _ReviewContext or context._authorization is not self
                   or context._seal is not self._seal or context not in self._contexts for context in contexts):
                _denied()
            # revision reads sample trust time. Read it BEFORE the one shared
            # timestamp used for key/token/MFA/current-role/authority checks.
            revision = self._revision()
            now = self._identity._time()
            for context in contexts:
                if revision != context.trust_revision:
                    _denied()
                case = self._identity._case(context.case.case_id)
                principal = self._identity._authorize_identity(context.identity, case, _ACTIONS[context.action][0], now)
                self._requirements(context.identity, principal, case, context.action, now)
                if (self._identity._authority.revision != context.authority_revision
                        or principal.person_id != context.principal.person_id or case.metadata != context.case
                        or _credential(context.identity, principal.person_id) != context.credential_sha256):
                    _denied()
            return now
