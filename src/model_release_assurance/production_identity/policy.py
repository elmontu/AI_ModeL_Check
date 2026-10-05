"""Current-authority and independent-review fixture; never authorizes delivery.

All state is in memory. The trusted Python bootstrap is not an administration
API, persistent identity registry, production approval service or cloud control.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
from threading import RLock
import time
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .tokens import AccessIdentity

ROLES = frozenset({"model_owner", "test_operator", "assessor", "policy_authority", "release_authority",
                   "data_steward", "auditor", "platform", "worker"})
ACTION_ROLES = MappingProxyType({
    "case:read": ROLES - {"worker"},
    "proposal:submit": frozenset({"model_owner"}),
    "review:assess": frozenset({"assessor"}),
    "review:approve": frozenset({"release_authority"}),
    "job:run": frozenset({"test_operator", "worker"}),
    "object:register": frozenset({"data_steward"}),
    "object:grant": frozenset({"data_steward"}),
    "object:hold": frozenset({"data_steward"}),
    "snapshot:freeze": frozenset({"data_steward"}),
    "object:metadata": ROLES - {"worker"},
    "object:read": frozenset({"worker"}),
})
FIXTURE_FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class PermissionDenied(PermissionError):
    """A verified identity lacks a current exact grant or independent role."""


class IdentityUnavailable(RuntimeError):
    """Current authoritative state is missing, unavailable or stale."""


class Conflict(ValueError):
    """A proposal/review reference is stale or the mutation would replay a review."""


def _integer(value, name, minimum=0, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " must be a bounded integer")
    return value


def _identifier(value, name):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ValueError(name + " must be a bounded identifier")
    return value


def _text(value, name, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum or any(ord(char) < 32 for char in value):
        raise ValueError(name + " must be bounded nonempty text")
    return value


def _strings(values, name, *, allow_empty=False):
    if not isinstance(values, (set, frozenset, tuple, list)) or len(values) > 256:
        raise ValueError(name + " must be a bounded collection")
    result = frozenset(_text(value, name) for value in values)
    if len(result) != len(values) or (not result and not allow_empty):
        raise ValueError(name + " must contain unique nonempty values")
    return result


@dataclass(frozen=True)
class PrincipalAuthority:
    issuer: str
    subject: str
    person_id: str
    kind: str
    enabled: bool = True
    client_ids: frozenset[str] = field(default_factory=frozenset)
    tokens_valid_after: int = 0

    def __post_init__(self):
        _text(self.issuer, "issuer", 512)
        _text(self.subject, "subject")
        _identifier(self.person_id, "person_id")
        if self.kind not in {"human", "workload"} or type(self.enabled) is not bool:
            raise ValueError("Principal kind/enabled must be explicit")
        object.__setattr__(self, "client_ids", _strings(self.client_ids, "client_ids"))
        _integer(self.tokens_valid_after, "tokens_valid_after")


@dataclass(frozen=True)
class CaseGrant:
    person_id: str
    agency_id: str
    project_id: str
    case_id: str
    roles: frozenset[str]

    def __post_init__(self):
        for name in ("person_id", "agency_id", "project_id", "case_id"):
            _identifier(getattr(self, name), name)
        roles = _strings(self.roles, "roles")
        if not roles <= ROLES:
            raise ValueError("Unknown server-side role")
        object.__setattr__(self, "roles", roles)


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    agency_id: str
    project_id: str
    submitter_person_id: str

    def __post_init__(self):
        for name in ("case_id", "agency_id", "project_id", "submitter_person_id"):
            _identifier(getattr(self, name), name)


@dataclass(frozen=True)
class AuthorityState:
    revision: int
    fresh_until: int
    available: bool
    active_key_ids: frozenset[str]
    revoked_token_ids: frozenset[str]
    principals: Mapping[tuple[str, str], PrincipalAuthority]
    grants: tuple[CaseGrant, ...]

    def __post_init__(self):
        _integer(self.revision, "revision", 1)
        _integer(self.fresh_until, "fresh_until")
        if type(self.available) is not bool:
            raise ValueError("Authority availability must be explicit")
        object.__setattr__(self, "active_key_ids", _strings(self.active_key_ids, "active_key_ids", allow_empty=True))
        object.__setattr__(self, "revoked_token_ids", _strings(self.revoked_token_ids, "revoked_token_ids", allow_empty=True))
        if not isinstance(self.principals, Mapping) or len(self.principals) > 256:
            raise ValueError("Principals must be a bounded authority mapping")
        principals = dict(self.principals)
        kinds = {}
        for key, principal in principals.items():
            if not isinstance(principal, PrincipalAuthority) or key != (principal.issuer, principal.subject):
                raise ValueError("Principal mapping key must match its canonical issuer/subject")
            if principal.person_id in kinds and kinds[principal.person_id] != principal.kind:
                raise ValueError("Aliases of one canonical person cannot mix human/workload kinds")
            kinds[principal.person_id] = principal.kind
        if not isinstance(self.grants, (list, tuple)) or len(self.grants) > 1024:
            raise ValueError("Grants must be a bounded collection")
        grants = tuple(self.grants)
        seen = set()
        for grant in grants:
            if not isinstance(grant, CaseGrant):
                raise ValueError("Invalid case grant")
            key = (grant.person_id, grant.agency_id, grant.project_id, grant.case_id)
            if key in seen:
                raise ValueError("Duplicate case grants are not unioned")
            seen.add(key)
        object.__setattr__(self, "principals", MappingProxyType(principals))
        object.__setattr__(self, "grants", grants)


@dataclass(frozen=True)
class _Review:
    person_id: str
    action: str
    identity: Any
    proposal_digest: str
    proposal_revision: int
    authority_revision: int
    recorded_at: int


@dataclass
class _Case:
    metadata: CaseRecord
    proposal: dict | None = None
    assessment: _Review | None = None
    approval: _Review | None = None
    operators: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _FixtureAuthorizationContext:
    """Trusted internal callback context; never an HTTP input or identity proof."""
    _service: Any
    identity: Any
    principal: PrincipalAuthority
    case: CaseRecord
    action: str
    authority_revision: int
    checked_at: int

    def recheck(self):
        return self.recheck_with()

    def recheck_with(self, *others):
        # One current timestamp binds issuer and worker checks to the same
        # authorization decision; a later grant expiry test uses this timestamp.
        with self._service._lock:
            contexts = (self, *others)
            if any(type(context) is not _FixtureAuthorizationContext or context._service is not self._service for context in contexts):
                raise PermissionDenied("Mismatched fixture authorization context")
            now = self._service._time()
            for context in contexts:
                case = self._service._case(context.case.case_id)
                principal = self._service._authorize_identity(context.identity, case, context.action, now)
                if self._service._authority.revision != context.authority_revision or principal.person_id != context.principal.person_id:
                    raise PermissionDenied("Current authority no longer matches the fixture operation")
            return now

    def verify_target(self, token, action):
        with self._service._lock:
            now, identity, principal, _ = self._service._access(token, self.case.case_id, action)
            return _FixtureAuthorizationContext(self._service, identity, principal, self.case, action,
                                                self._service._authority.revision, now)


class FixtureIdentityService:
    """Raw-token-only fixture methods serialize current authorization and mutation.

    Every authority revision invalidates existing review usability. Unrelated
    authority revisions do not by themselves revoke all signed access tokens:
    current grants are recomputed, while explicit revocation/floors deny tokens.
    """

    def __init__(self, verifier, authority: AuthorityState, cases: Sequence[CaseRecord], *,
                 now: Callable[[], int] = lambda: int(time.time()), accepted_acr="urn:mra:fixture:mfa",
                 mfa_max_age_seconds=300):
        if not isinstance(authority, AuthorityState) or not callable(getattr(verifier, "verify", None)):
            raise ValueError("A trusted verifier and authority snapshot are required")
        _text(accepted_acr, "accepted_acr")
        _integer(mfa_max_age_seconds, "mfa_max_age_seconds", 1, 300)
        if not callable(now) or not isinstance(cases, (list, tuple)) or not 1 <= len(cases) <= 256:
            raise ValueError("A clock and bounded trusted case metadata are required")
        registered = {}
        for case in cases:
            if not isinstance(case, CaseRecord) or case.case_id in registered:
                raise ValueError("Case registration must be unique trusted metadata")
            registered[case.case_id] = _Case(case)
        self._verifier, self._authority, self._cases = verifier, authority, registered
        self._now, self._accepted_acr, self._mfa_age = now, accepted_acr, mfa_max_age_seconds
        # A dynamic trust verifier supplies its registry lock so key rotation,
        # revocation and outages serialize with all identity/storage operations.
        # Static pinned verifiers retain the original per-service lock.
        trust_lock = getattr(verifier, "operation_lock", None)
        trust_check = getattr(verifier, "check_current", None)
        trust_clock = getattr(verifier, "current_time", None)
        if any(value is not None for value in (trust_lock, trust_check, trust_clock)):
            if (trust_lock is None or not callable(trust_check) or not callable(trust_clock)
                    or any(not callable(getattr(trust_lock, name, None))
                           for name in ("acquire", "release", "__enter__", "__exit__"))):
                raise ValueError("Dynamic trust requires one lock, clock and current-key guard")
            trust_agency = _identifier(getattr(verifier, "agency_id", None), "trust_agency_id")
            if any(case.metadata.agency_id != trust_agency for case in registered.values()):
                raise ValueError("Registered cases must match the dynamic trust agency")
            # Every identity, review and storage-grant decision uses the same
            # registry clock. A guarded check must not resample it mid-decision.
            self._now = trust_clock
        self._lock = trust_lock if trust_lock is not None else RLock()
        self._last_now = None
        self._revoked_tokens = set(authority.revoked_token_ids)
        self._retired_keys = set()
        self._subject_floors = {key: value.tokens_valid_after for key, value in authority.principals.items()}

    def _time(self):
        try:
            current = _integer(self._now(), "clock")
        except (TypeError, ValueError) as error:
            raise IdentityUnavailable("Current authority clock unavailable") from error
        if self._last_now is not None and current < self._last_now:
            raise IdentityUnavailable("Current authority clock moved backwards")
        self._last_now = current
        return current

    def _replace_authority_for_fixture(self, state: AuthorityState):
        """Trusted fixture bootstrap hook only; never expose as an HTTP operation.

        Credential tombstones/floors survive revoke/regrant within this process.
        Restart persistence and durable revocation are outside this fixture.
        """
        with self._lock:
            if not isinstance(state, AuthorityState) or state.revision <= self._authority.revision:
                raise ValueError("Authority replacement requires a strictly increasing revision")
            now = self._time()
            previous = self._authority
            self._revoked_tokens.update(state.revoked_token_ids)
            self._retired_keys.update(previous.active_key_ids - state.active_key_ids)
            for key, old in previous.principals.items():
                new = state.principals.get(key)
                changed_identity = (new is None or not new.enabled or not old.enabled
                                    or (old.person_id, old.kind) != (new.person_id, new.kind))
                if changed_identity:
                    self._subject_floors[key] = max(self._subject_floors.get(key, 0), now + 1)
            for key, principal in state.principals.items():
                if key not in previous.principals and key in self._subject_floors:
                    # Restoring a previously removed subject cannot activate a
                    # token issued during its absence from current authority.
                    self._subject_floors[key] = max(self._subject_floors[key], now + 1)
                self._subject_floors[key] = max(self._subject_floors.get(key, 0), principal.tokens_valid_after)
            self._authority = state

    def _fresh(self, now):
        state = self._authority
        if state is None or not state.available or now >= state.fresh_until:
            raise IdentityUnavailable("Current authority is unavailable or stale")
        return state

    def _case(self, case_id):
        if type(case_id) is not str or case_id not in self._cases:
            raise PermissionDenied("Case access denied")
        return self._cases[case_id]

    def _authorize_identity(self, identity, case, action, now):
        state = self._fresh(now)
        current_trust = getattr(self._verifier, "check_current", None)
        if current_trust is not None:
            current_trust(identity, now=now)
        if (identity.key_id not in state.active_key_ids or identity.key_id in self._retired_keys
                or identity.token_id in self._revoked_tokens or not identity.issued_at <= now < identity.expires_at):
            raise PermissionDenied("Credential is not currently eligible")
        key = (identity.issuer, identity.subject)
        principal = state.principals.get(key)
        if principal is None or not principal.enabled or identity.client_id not in principal.client_ids:
            raise PermissionDenied("Principal/client is not currently enabled")
        if identity.issued_at < max(principal.tokens_valid_after, self._subject_floors.get(key, 0)):
            raise PermissionDenied("Credential predates current authority floor")
        if action not in identity.scopes or case.metadata.case_id not in identity.case_ids:
            raise PermissionDenied("Token does not grant this case action")
        if principal.kind == "workload" and action not in {"job:run", "object:read"}:
            raise PermissionDenied("Workload identities cannot act as human reviewers")
        if action == "object:read" and principal.kind != "workload":
            raise PermissionDenied("Object bytes require a scoped workload identity")
        if principal.kind == "human" and (identity.acr != self._accepted_acr or type(identity.auth_time) is not int
                                         or not 0 <= now - identity.auth_time <= self._mfa_age):
            raise PermissionDenied("Fresh approved human MFA is required")
        matching = [grant for grant in state.grants
                    if (grant.person_id, grant.agency_id, grant.project_id, grant.case_id)
                    == (principal.person_id, case.metadata.agency_id, case.metadata.project_id, case.metadata.case_id)]
        if len(matching) != 1 or not matching[0].roles & ACTION_ROLES[action]:
            raise PermissionDenied("Current exact case grant is required")
        return principal

    def _access(self, token, case_id, action):
        # Caller holds this service's RLock through verification, current lookups
        # and any subsequent state mutation. No caller-created identity is proof.
        now = self._time()
        self._fresh(now)
        identity = self._verifier.verify(token, now=now)
        # Signature verification does not stop token, MFA or authority time.
        now = self._time()
        case = self._case(case_id)
        principal = self._authorize_identity(identity, case, action, now)
        return now, identity, principal, case

    def _with_fixture_authorization(self, token, case_id, action, callback):
        """Trusted storage bridge: identity lock precedes any callback storage lock.

        The callback is server code, never a caller-supplied HTTP operation. No
        preconstructed principal bypasses token verification. Bounded I/O must
        recheck this context before mutation or returning data. Recheck again
        here so exceptions/expiry cannot silently return a stale authorization.
        """
        if action not in {"object:register", "object:grant", "object:hold", "snapshot:freeze", "object:metadata", "object:read"}:
            raise PermissionDenied("Unsupported fixture storage action")
        with self._lock:
            now, identity, principal, case = self._access(token, case_id, action)
            context = _FixtureAuthorizationContext(self, identity, principal, case.metadata, action,
                                                   self._authority.revision, now)
            result = callback(context)
            context.recheck()
            return result

    def _with_fixture_job_authorization(self, token, case_id, action, callback):
        """Trusted job coordinator bridge; never accepts a caller-built identity.

        Job operators are recorded before invoking the bounded callback, even if
        the attempt fails, so failed execution cannot restore review independence.
        Long child execution must happen outside this lock and reauthorize later.
        """
        if action not in {"job:run", "case:read"}:
            raise PermissionDenied("Unsupported fixture job action")
        with self._lock:
            now, identity, principal, case = self._access(token, case_id, action)
            if action == "job:run":
                needed_role = "test_operator" if principal.kind == "human" else "worker"
                matching = [grant for grant in self._authority.grants
                            if (grant.person_id, grant.agency_id, grant.project_id, grant.case_id)
                            == (principal.person_id, case.metadata.agency_id, case.metadata.project_id, case.metadata.case_id)]
                if len(matching) != 1 or needed_role not in matching[0].roles:
                    raise PermissionDenied("Exact job operator role is required")
                case.operators.add(principal.person_id)
            context = _FixtureAuthorizationContext(self, identity, principal, case.metadata, action,
                                                    self._authority.revision, now)
            result = callback(context)
            context.recheck()
            return result

    def _review_status(self, review, case, now):
        if review is None:
            return None
        reason = None
        try:
            if case.proposal is None or review.proposal_digest != case.proposal["digest"] or review.proposal_revision != case.proposal["revision"]:
                reason = "proposal_changed"
            elif review.authority_revision != self._fresh(now).revision:
                reason = "authority_changed"
            else:
                principal = self._authorize_identity(review.identity, case, review.action, now)
                if principal.person_id != review.person_id:
                    reason = "actor_identity_changed"
                elif principal.person_id == case.metadata.submitter_person_id or principal.person_id in case.operators:
                    reason = "actor_not_independent"
                elif review.action == "review:approve" and (case.assessment is None or principal.person_id == case.assessment.person_id):
                    reason = "actor_not_independent"
        except (PermissionDenied, IdentityUnavailable):
            reason = "actor_not_currently_eligible"
        return {"person_id": review.person_id, "proposal_digest": review.proposal_digest,
                "proposal_revision": review.proposal_revision, "authority_revision": review.authority_revision,
                "recorded_at": review.recorded_at, "usable": reason is None, "reason": reason}

    def _snapshot(self, case, now):
        assessment = self._review_status(case.assessment, case, now)
        approval = self._review_status(case.approval, case, now)
        if approval is not None and (assessment is None or not assessment["usable"]):
            approval = {**approval, "usable": False, "reason": "current_independent_assessment_required"}
        return {**FIXTURE_FLAGS, "case": {name: getattr(case.metadata, name)
                for name in ("case_id", "agency_id", "project_id", "submitter_person_id")},
                "proposal": dict(case.proposal) if case.proposal else None,
                "proposal_digest": case.proposal["digest"] if case.proposal else None,
                "assessment": assessment, "approval": approval,
                "reviews_usable": bool(assessment and assessment["usable"] and approval and approval["usable"]),
                "authority_revision": self._authority.revision}

    def read_case(self, token, case_id):
        with self._lock:
            now, _, _, case = self._access(token, case_id, "case:read")
            return self._snapshot(case, now)

    def submit_proposal(self, token, case_id, payload):
        with self._lock:
            now, identity, principal, case = self._access(token, case_id, "proposal:submit")
            if principal.kind != "human" or principal.person_id != case.metadata.submitter_person_id:
                raise PermissionDenied("Only the registered canonical model owner may submit")
            expected = {"artifact_sha256", "evidence_sha256", "policy_sha256", "recipient_id", "revision"}
            if type(payload) is not dict or set(payload) != expected:
                raise Conflict("Proposal requires exactly the registered material fields")
            # Own the primitive input snapshot before validation/hash/commit;
            # a caller mutating its dictionary cannot substitute digest-bound bytes.
            payload = dict(payload)
            for key in ("artifact_sha256", "evidence_sha256", "policy_sha256"):
                if type(payload[key]) is not str or not _SHA256.fullmatch(payload[key]):
                    raise Conflict("Proposal digests must be lowercase SHA256")
            try:
                _identifier(payload["recipient_id"], "recipient_id")
                _integer(payload["revision"], "proposal revision", 1, 1_000_000)
            except ValueError as error:
                raise Conflict("Invalid proposal recipient or revision") from error
            if payload["revision"] != (case.proposal["revision"] + 1 if case.proposal else 1):
                raise Conflict("Proposal revision must be the next revision")
            bound = {"case_id": case.metadata.case_id, "agency_id": case.metadata.agency_id,
                     "project_id": case.metadata.project_id, "submitted_by": principal.person_id, **payload}
            digest = hashlib.sha256(json.dumps(bound, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            now = self._time()
            self._authorize_identity(identity, case, "proposal:submit", now)
            case.proposal = {**payload, "submitted_by": principal.person_id, "digest": digest}
            # Material changes never inherit a former review/acknowledgement.
            case.assessment = case.approval = None
            return self._snapshot(case, now)

    def _expected_proposal(self, case, expected_digest):
        if (case.proposal is None or type(expected_digest) is not str or not _SHA256.fullmatch(expected_digest)
                or not hmac.compare_digest(case.proposal["digest"], expected_digest)):
            raise Conflict("The exact current proposal digest is required")

    def _independent(self, principal, case):
        if principal.kind != "human" or principal.person_id == case.metadata.submitter_person_id or principal.person_id in case.operators:
            raise PermissionDenied("Independent canonical human reviewer is required")

    def assess(self, token, case_id, expected_digest):
        with self._lock:
            now, identity, principal, case = self._access(token, case_id, "review:assess")
            self._expected_proposal(case, expected_digest)
            self._independent(principal, case)
            if case.assessment is not None:
                raise Conflict("Assessment already recorded; duplicate reviews are refused")
            now = self._time()
            self._authorize_identity(identity, case, "review:assess", now)
            case.assessment = _Review(principal.person_id, "review:assess", identity, case.proposal["digest"],
                                      case.proposal["revision"], self._authority.revision, now)
            return self._snapshot(case, now)

    def approve(self, token, case_id, expected_digest):
        with self._lock:
            now, identity, principal, case = self._access(token, case_id, "review:approve")
            self._expected_proposal(case, expected_digest)
            self._independent(principal, case)
            assessment = self._review_status(case.assessment, case, now)
            if assessment is None or not assessment["usable"]:
                raise Conflict("A current independent assessment is required")
            if principal.person_id == case.assessment.person_id:
                raise PermissionDenied("Release acknowledgement must be independent of assessor")
            if case.approval is not None:
                raise Conflict("Acknowledgement already recorded; duplicate reviews are refused")
            now = self._time()
            self._authorize_identity(identity, case, "review:approve", now)
            if not self._review_status(case.assessment, case, now)["usable"]:
                raise Conflict("A current independent assessment is required")
            case.approval = _Review(principal.person_id, "review:approve", identity, case.proposal["digest"],
                                    case.proposal["revision"], self._authority.revision, now)
            return self._snapshot(case, now)

    def check_job(self, token, case_id):
        with self._lock:
            now, identity, principal, case = self._access(token, case_id, "job:run")
            now = self._time()
            self._authorize_identity(identity, case, "job:run", now)
            case.operators.add(principal.person_id)
            return {**FIXTURE_FLAGS, "action": "job:run", "allowed": True, "case_id": case.metadata.case_id,
                    "actor_person_id": principal.person_id, "authority_revision": self._authority.revision,
                    "checked_at": now, "job_executed": False}

