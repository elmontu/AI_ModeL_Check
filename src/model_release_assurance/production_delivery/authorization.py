"""Current human-recipient authorization for one bounded local delivery fixture.

A directory entry is trusted bootstrap metadata, not identity proof. Only raw
signed tokens enter access(). No workload recipient, arbitrary object path or
production release authority is provided by this additive bridge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from weakref import WeakSet

from ..production_identity.policy import PermissionDenied
from ..production_review.service import FixtureReviewService

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_ACTIONS = {"activate": "approve", "grant": "approve", "suspend": "read",
            "revoke": "read", "resume": "read", "receive": "read", "read": "read"}


def _identifier(value):
    if type(value) is not str or not _NAME.fullmatch(value):
        raise ValueError("Recipient directory metadata rejected")
    return value


def _deny():
    raise PermissionDenied("Current scoped delivery authority is required")


@dataclass(frozen=True)
class RecipientRecord:
    recipient_id: str
    agency_id: str
    project_id: str
    case_id: str
    person_ids: frozenset[str]
    kind: str = "human"

    def __post_init__(self):
        for key in ("recipient_id", "agency_id", "project_id", "case_id"):
            _identifier(getattr(self, key))
        if type(self.kind) is not str or self.kind != "human":
            raise ValueError("Only human fixture recipients are supported")
        if type(self.person_ids) not in (set, frozenset, list, tuple) or not 1 <= len(self.person_ids) <= 32:
            raise ValueError("Recipient people must be explicitly bounded")
        people = frozenset(_identifier(person) for person in self.person_ids)
        if len(people) != len(self.person_ids):
            raise ValueError("Recipient people must be unique")
        object.__setattr__(self, "person_ids", people)


@dataclass(frozen=True, repr=False, eq=False)
class _GatewayContext:
    _authorization: object = field(repr=False)
    _seal: object = field(repr=False)
    review_context: object = field(repr=False)
    action: str
    recipient_id: str | None

    @property
    def identity(self):
        return self.review_context.identity

    @property
    def principal(self):
        return self.review_context.principal

    @property
    def case(self):
        return self.review_context.case

    @property
    def authority_revision(self):
        return self.review_context.authority_revision

    @property
    def credential_sha256(self):
        return self.review_context.credential_sha256

    @property
    def actor(self):
        return self.review_context.actor

    def recheck(self):
        return self._authorization.recheck_many((self,))

    def recheck_with(self, *others, review_contexts=()):
        return self._authorization.recheck_many((self, *others), review_contexts=review_contexts)


class GatewayAuthorization:
    """Use PRD17's original verifier, shared lock and one final time observation.

    The caller must hold review.identity._lock through its storage operation and
    invoke recheck_many after bounded I/O/lock waits, immediately before commit
    or returning bytes. This helper grants no artifact access by itself.
    """
    def __init__(self, review, recipients):
        if type(review) is not FixtureReviewService:
            raise ValueError("An exact current review fixture is required")
        if type(recipients) not in (list, tuple) or not 1 <= len(recipients) <= 32:
            raise ValueError("A bounded explicit recipient directory is required")
        directory = {}
        with review.identity._lock:
            for record in recipients:
                if type(record) is not RecipientRecord or record.recipient_id in directory:
                    raise ValueError("Recipient IDs must be unique exact records")
                case = review.identity._case(record.case_id).metadata
                if (record.agency_id, record.project_id, record.case_id) != (case.agency_id, case.project_id, case.case_id):
                    raise ValueError("Recipient directory case scope differs")
                directory[record.recipient_id] = record
        self._review, self._identity = review, review.identity
        self._authorization = review.authorization
        self._recipients = MappingProxyType(directory)
        self._seal, self._contexts = object(), WeakSet()

    def _requirements(self, context, now):
        if type(context.action) is not str or context.action not in _ACTIONS:
            _deny()
        if context.principal.kind != "human" or "delivery:" + context.action not in context.identity.scopes:
            _deny()
        case = self._identity._case(context.case.case_id)
        matches = [grant for grant in self._identity._fresh(now).grants
            if (grant.person_id, grant.agency_id, grant.project_id, grant.case_id)
            == (context.principal.person_id, context.case.agency_id, context.case.project_id, context.case.case_id)]
        if len(matches) != 1:
            _deny()
        roles = matches[0].roles
        if context.action in ("activate", "grant"):
            if "release_authority" not in roles:
                _deny()
            self._identity._independent(context.principal, case)
        elif context.action in ("suspend", "revoke", "resume"):
            if "data_steward" not in roles:
                if "release_authority" not in roles:
                    _deny()
                self._identity._independent(context.principal, case)
        elif context.action == "receive" and "auditor" not in roles:
            _deny()
        record = None
        if context.recipient_id is not None:
            record = self._recipients.get(context.recipient_id)
            if record is None or (record.agency_id, record.project_id, record.case_id) != (
                    context.case.agency_id, context.case.project_id, context.case.case_id):
                _deny()
        if context.action == "receive" and (record is None or context.principal.person_id not in record.person_ids):
            _deny()

    def access(self, token, case_id, action, recipient_id=None):
        """Authenticate one raw JWT; recipient strings never substitute for it."""
        if type(action) is not str or action not in _ACTIONS:
            _deny()
        if recipient_id is not None:
            try:
                _identifier(recipient_id)
            except ValueError:
                _deny()
        with self._identity._lock:
            base = self._authorization.access(token, case_id, _ACTIONS[action])
            context = _GatewayContext(self, self._seal, base, action, recipient_id)
            self._contexts.add(context)
            context.recheck()
            return context

    def recheck_many(self, contexts, *, review_contexts=()):
        """Check all gateway and retained reviewers at ONE final current time.

        No additional clock sample follows the original authorization check.
        The gateway compares all evidence, delegation and grant deadlines to
        this returned timestamp before committing its admission.
        """
        if (type(contexts) not in (list, tuple) or not 1 <= len(contexts) <= 32
                or type(review_contexts) not in (list, tuple)
                or len(contexts) + len(review_contexts) > 32):
            _deny()
        contexts, review_contexts = tuple(contexts), tuple(review_contexts)
        with self._identity._lock:
            if any(type(context) is not _GatewayContext or context._authorization is not self
                   or context._seal is not self._seal or context not in self._contexts for context in contexts):
                _deny()
            now = self._authorization.recheck_many(tuple(context.review_context for context in contexts) + review_contexts)
            for context in contexts:
                self._requirements(context, now)
            return now
