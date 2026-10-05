"""Signed in-memory local planning decisions; no pilot execution or delivery.

The exact historical packet capability establishes only integrity. All current
participants are rechecked at one final shared timestamp after that work. No
serialized plan or review record can recreate these live contexts on restart.
"""
from __future__ import annotations

from functools import wraps
from types import MappingProxyType

from ..production_assessment.contracts import BLOCKING_FINDING_IDS
from ..production_identity.policy import PermissionDenied, IdentityUnavailable
from ..production_review.authorization import ReviewAuthorization
from .evidence import VerifiedAssessment, check_capability
from . import contracts as c

MAX_EVENTS = 32
_BINDING_FIELDS = ("candidate_sha256", "assessment_manifest_sha256", "assessment_key_sha256", "catalog_sha256",
                   "agency_id", "project_id", "case_id")
_PEOPLE = MappingProxyType({"person-owner": "model_owner", "person-policy": "policy_authority",
    "person-operator": "test_operator", "person-assessor": "assessor", "person-releaser": "release_authority",
    "person-auditor": "auditor", "person-recipient": "auditor"})


def _fail():
    raise c.PilotError("Current restricted local plan unavailable")


def _generic(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            raise c.PilotError("Current restricted local plan unavailable") from None
    return call


class FixturePilotPlanService:
    """One immutable plan; every API takes a raw token, never caller proof JSON."""
    @_generic
    def __init__(self, identity, evidence, *, profile="agency_private_cloud"):
        c.require_local(profile)
        check_capability(evidence)
        authorization = ReviewAuthorization(identity)
        with identity._lock:
            captured = evidence.recheck()
            binding = {key: captured[key] for key in _BINDING_FIELDS}
            case = identity._case(binding["case_id"]).metadata
            if (case.agency_id, case.project_id, case.case_id) != (
                    binding["agency_id"], binding["project_id"], binding["case_id"]):
                _fail()
            self._identity, self._authorization, self._evidence = identity, authorization, evidence
            self._evidence_snapshot, self._binding = c.owned(captured), c.owned(binding)
            self._plan = self._plan_sha256 = None
            self._state = "awaiting_producer"
            self._events = []
            self._producer = self._owner = self._assessor = self._approver = None
            self._people = ()

    def _access(self, token, case_id, action, *, person=None):
        if type(case_id) is not str or case_id != self._binding["case_id"]:
            _fail()
        context = self._authorization.access(token, case_id, action)
        if ((context.case.agency_id, context.case.project_id) != (self._binding["agency_id"], self._binding["project_id"])
                or person is not None and context.principal.person_id != person):
            _fail()
        return context

    def _named_at(self, context, now):
        required = _PEOPLE.get(context.principal.person_id)
        if required is None or context.principal.kind != "human":
            _fail()
        matching = [grant for grant in self._identity._fresh(now).grants
            if (grant.person_id, grant.agency_id, grant.project_id, grant.case_id) ==
               (context.principal.person_id, context.case.agency_id, context.case.project_id, context.case.case_id)]
        if len(matching) != 1 or required not in matching[0].roles:
            _fail()

    def _contexts(self, *extra):
        retained = tuple(context for context in (self._producer, self._owner, self._assessor, self._approver)
                         if context is not None)
        return (*self._people, *retained, *extra)

    def _final(self, contexts, *, plan=None, evidence=True, window=True):
        if evidence:
            check_capability(self._evidence)
            actual = self._evidence.recheck()
            if c.canonical_bytes(actual) != c.canonical_bytes(self._evidence_snapshot):
                _fail()
        now = self._authorization.recheck_many(contexts)
        for context in contexts:
            self._named_at(context, now)
        selected = self._plan if plan is None else plan
        if window and selected is not None:
            if not selected["window"]["starts_at"] <= now < selected["window"]["ends_at"]:
                _fail()
        return now

    def _view(self, *, state=None, events=None, plan=None, plan_sha256=None):
        return c.owned({"schema": "mra-local-pilot-plan-status/v1", "state": self._state if state is None else state,
            "plan": self._plan if plan is None else plan,
            "plan_sha256": self._plan_sha256 if plan_sha256 is None else plan_sha256,
            "events": self._events if events is None else events,
            "local_planning_ready": False, "current_checks_satisfied": False, "readiness": "no_go",
            "production_blockers": list(BLOCKING_FINDING_IDS), "historical_records_only": True,
            "checked_at": 0, **c.FLAGS})

    def _prospective(self, kind, context, state, *, plan=None, extra=None):
        limit = MAX_EVENTS if kind == "withdrawal" else MAX_EVENTS - 1 if kind == "suspension" else MAX_EVENTS - 2
        if len(self._events) >= limit:
            _fail()
        chosen = self._plan if plan is None else plan
        plan_digest = c.digest(chosen) if chosen is not None else None
        # This is the record's proposal time. checked_at is the final current
        # timestamp after expensive evidence work; only then is state installed.
        record = {"schema": "mra-local-pilot-plan-event/v1", "sequence": len(self._events) + 1,
            "kind": kind, "plan_sha256": plan_digest, "actor": context.actor,
            "recorded_at": context.recheck(), "details": {} if extra is None else extra, **c.FLAGS}
        record = c.owned(record)
        record["sha256"] = c.digest(record)
        events = [*self._events, record]
        result = self._view(state=state, events=events, plan=chosen, plan_sha256=plan_digest)
        return events, result

    def _install(self, state, events, result, now, *, all_current=True):
        result["checked_at"] = now
        result["current_checks_satisfied"] = all_current
        result["local_planning_ready"] = all_current and state == "acknowledged" and len(events) < MAX_EVENTS - 2
        self._state, self._events = state, events
        return result

    @_generic
    def enroll_people(self, tokens_by_subject, case_id):
        """Retain exactly seven original signed identities; never serialize tokens."""
        with self._identity._lock:
            subjects = tuple(person.removeprefix("person-") for person in _PEOPLE)
            if (self._people or self._state != "awaiting_producer" or type(tokens_by_subject) is not dict
                    or set(tokens_by_subject) != set(subjects)):
                _fail()
            contexts = tuple(self._access(tokens_by_subject[subject], case_id, "read", person="person-" + subject)
                             for subject in subjects)
            events, result = self._prospective("named_people", contexts[0], "people_enrolled",
                extra={"people": [context.actor for context in contexts]})
            now = self._final(contexts)
            self._people = contexts
            return self._install("people_enrolled", events, result, now)

    @_generic
    def record_producer(self, token, case_id):
        with self._identity._lock:
            if self._state != "people_enrolled" or self._producer is not None:
                _fail()
            context = self._access(token, case_id, "start", person="person-operator")
            events, result = self._prospective("producer", context, "producer_recorded")
            now = self._final(self._contexts(context))
            self._producer = context
            return self._install("producer_recorded", events, result, now)

    @_generic
    def propose(self, token, case_id, plan):
        plan = c.validate_plan(plan)
        with self._identity._lock:
            if self._state != "producer_recorded" or self._plan is not None:
                _fail()
            if c.canonical_bytes(plan["binding"]) != c.canonical_bytes(self._binding):
                _fail()
            context = self._access(token, case_id, "propose", person="person-owner")
            events, result = self._prospective("proposal", context, "proposed", plan=plan)
            now = self._final(self._contexts(context), plan=plan)
            self._plan, self._plan_sha256, self._owner = plan, result["plan_sha256"], context
            return self._install("proposed", events, result, now)

    @_generic
    def assess(self, token, case_id):
        with self._identity._lock:
            if self._state != "proposed" or self._assessor is not None:
                _fail()
            context = self._access(token, case_id, "assess", person="person-assessor")
            if context.principal.person_id in {self._producer.principal.person_id, self._owner.principal.person_id}:
                _fail()
            events, result = self._prospective("assessment", context, "assessed")
            now = self._final(self._contexts(context))
            self._assessor = context
            return self._install("assessed", events, result, now)

    @_generic
    def acknowledge(self, token, case_id):
        with self._identity._lock:
            if self._state != "assessed" or self._approver is not None:
                _fail()
            context = self._access(token, case_id, "approve", person="person-releaser")
            if context.principal.person_id in {item.principal.person_id for item in
                    (self._producer, self._owner, self._assessor)}:
                _fail()
            events, result = self._prospective("local_plan_acknowledgment", context, "acknowledged")
            now = self._final(self._contexts(context))
            self._approver = context
            return self._install("acknowledged", events, result, now)

    @_generic
    def suspend(self, token, case_id):
        with self._identity._lock:
            if self._state != "acknowledged":
                _fail()
            context = self._access(token, case_id, "approve", person="person-releaser")
            events, result = self._prospective("suspension", context, "suspended")
            # A restrictive record does not require healthy historical evidence
            # or revive stale original reviewers. Only this caller is current.
            now = self._final((context,), evidence=False, window=False)
            return self._install("suspended", events, result, now, all_current=False)

    @_generic
    def resume(self, token, case_id):
        with self._identity._lock:
            if self._state != "suspended":
                _fail()
            context = self._access(token, case_id, "approve", person="person-releaser")
            events, result = self._prospective("local_plan_resume", context, "acknowledged")
            now = self._final(self._contexts(context))
            return self._install("acknowledged", events, result, now)

    @_generic
    def withdraw(self, token, case_id):
        with self._identity._lock:
            if self._plan is None or self._state == "withdrawn":
                _fail()
            context = self._access(token, case_id, "approve", person="person-releaser")
            events, result = self._prospective("withdrawal", context, "withdrawn")
            now = self._final((context,), evidence=False, window=False)
            return self._install("withdrawn", events, result, now, all_current=False)

    @_generic
    def status(self, token, case_id):
        with self._identity._lock:
            context = self._access(token, case_id, "read")
            result = self._view()
            try:
                now = self._final(self._contexts(context))
                result["current_checks_satisfied"] = True
                result["local_planning_ready"] = self._state == "acknowledged" and len(self._events) < MAX_EVENTS - 2
            except (c.PilotError, PermissionDenied, IdentityUnavailable):
                now = self._final((context,), evidence=False, window=False)
            result["checked_at"] = now
            return result
