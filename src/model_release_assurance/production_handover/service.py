"""Current signed local handover preparation over a live restricted plan.

The original pilot contexts and new reviewers share one authorization bridge,
identity lock and final timestamp after packet work. JSON cannot reconstruct any
of these capabilities. Retirement stops this preparation only; no gateway or
agency authority is created, revoked, transferred or restored.
"""
from __future__ import annotations

from functools import wraps
from ..production_identity.policy import FixtureIdentityService, PermissionDenied, IdentityUnavailable
from ..production_review.authorization import ReviewAuthorization
from ..production_pilot.service import FixturePilotPlanService, MAX_EVENTS as PILOT_MAX_EVENTS
from ..production_pilot.evidence import check_capability
from . import contracts as c

MAX_EVENTS = 8


def _fail():
    raise c.HandoverError("Current local handover preparation unavailable")


def _generic(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            raise c.HandoverError("Current local handover preparation unavailable") from None
    return call


class FixtureHandoverService:
    """One immutable local preparation; raw signed tokens are the only callers."""
    @_generic
    def __init__(self, pilot_service, *, profile="agency_private_cloud"):
        c.require_local(profile)
        if type(pilot_service) is not FixturePilotPlanService:
            _fail()
        identity, authorization = pilot_service._identity, pilot_service._authorization
        if (type(identity) is not FixtureIdentityService or type(authorization) is not ReviewAuthorization
                or authorization._identity is not identity):
            _fail()
        self._pilot, self._identity, self._authorization = pilot_service, identity, authorization
        with identity._lock:
            self._plan = c._wrap(c.pilot.validate_plan, pilot_service._plan)
            self._pilot_plan_sha256, self._binding = c.digest(self._plan), c.owned(self._plan["binding"])
            self._evidence_snapshot = c.owned(pilot_service._evidence_snapshot)
            self._pilot_contexts = pilot_service._contexts()
            if (type(pilot_service._people) is not tuple or len(pilot_service._people) != 7
                    or any(item is None for item in (pilot_service._producer, pilot_service._owner,
                                                    pilot_service._assessor, pilot_service._approver))
                    or len(self._pilot_contexts) != 11):
                _fail()
            self._operator = self._owner = self._assessor = self._approver = None
            self._preparation = self._preparation_sha256 = None
            self._state, self._events = "awaiting_operator", []
            self._final(self._contexts())

    def _check_pilot(self):
        selected = c._wrap(c.pilot.validate_plan, self._pilot._plan)
        if (self._pilot._state != "acknowledged"
                or type(self._pilot._events) is not list
                or not 5 <= len(self._pilot._events) < PILOT_MAX_EVENTS - 2
                or self._pilot._contexts() != self._pilot_contexts
                or c.canonical_bytes(selected) != c.canonical_bytes(self._plan)
                or self._pilot._plan_sha256 != self._pilot_plan_sha256
                or c.canonical_bytes(self._pilot._binding) != c.canonical_bytes(self._binding)
                or c.canonical_bytes(self._pilot._evidence_snapshot) != c.canonical_bytes(self._evidence_snapshot)
                or self._pilot._authorization is not self._authorization
                or self._pilot._identity is not self._identity):
            _fail()

    def _access(self, token, case_id, action, *, person=None):
        if type(case_id) is not str or case_id != self._binding["case_id"]:
            _fail()
        context = self._authorization.access(token, case_id, action)
        if ((context.case.agency_id, context.case.project_id) !=
                (self._binding["agency_id"], self._binding["project_id"])
                or person is not None and context.principal.person_id != person):
            _fail()
        return context

    def _contexts(self, *extra):
        retained = tuple(item for item in (self._operator, self._owner, self._assessor, self._approver)
                         if item is not None)
        return (*self._pilot_contexts, *retained, *extra)

    def _final(self, contexts, *, evidence=True, window=True):
        if evidence:
            self._check_pilot()
            c._wrap(check_capability, self._pilot._evidence)
            actual = c._wrap(self._pilot._evidence.recheck)
            if c.canonical_bytes(actual) != c.canonical_bytes(self._evidence_snapshot):
                _fail()
            # Binding/state checks and bounded canonical work finish BEFORE the
            # single shared current-authority timestamp for all original people.
            self._check_pilot()
        now = self._authorization.recheck_many(contexts)
        for context in contexts:
            self._pilot._named_at(context, now)
        if window and not self._plan["window"]["starts_at"] <= now < self._plan["window"]["ends_at"]:
            _fail()
        return now

    def _view(self, *, state=None, events=None, preparation=None, preparation_sha256=None):
        return c.owned({"schema": "mra-local-handover-status/v1",
            "state": self._state if state is None else state,
            "preparation": self._preparation if preparation is None else preparation,
            "preparation_sha256": self._preparation_sha256 if preparation_sha256 is None else preparation_sha256,
            "pilot_plan_sha256": self._pilot_plan_sha256, "binding": self._binding,
            "events": self._events if events is None else events,
            "local_handover_preparation_ready": False, "current_checks_satisfied": False,
            "readiness": "no_go", "production_blockers": list(c.pilot.assessment.BLOCKING_FINDING_IDS),
            "historical_records_only": True, "checked_at": 0, **c.FLAGS})

    def _prospective(self, kind, context, state, *, preparation=None):
        limit = MAX_EVENTS if kind == "retirement" else MAX_EVENTS - 1
        if len(self._events) >= limit:
            _fail()
        selected = self._preparation if preparation is None else preparation
        selected_sha256 = c.digest(selected) if selected is not None else None
        record = c.owned({"schema": "mra-local-handover-event/v1",
            "sequence": len(self._events) + 1, "kind": kind,
            "pilot_plan_sha256": self._pilot_plan_sha256,
            "preparation_sha256": selected_sha256,
            "previous_event_sha256": self._events[-1]["sha256"] if self._events else None,
            "actor": context.actor, "recorded_at": context.recheck(), **c.FLAGS})
        record["sha256"] = c.digest(record)
        events = [*self._events, record]
        result = self._view(state=state, events=events, preparation=selected,
                            preparation_sha256=selected_sha256)
        return events, result

    def _install(self, state, events, result, now, *, all_current=True):
        result["checked_at"] = now
        result["current_checks_satisfied"] = all_current
        result["local_handover_preparation_ready"] = all_current and state == "acknowledged"
        self._state, self._events = state, events
        return result

    @_generic
    def record_operator(self, token, case_id):
        with self._identity._lock:
            if self._state != "awaiting_operator":
                _fail()
            context = self._access(token, case_id, "start", person="person-operator")
            events, result = self._prospective("operator", context, "operator_recorded")
            now = self._final(self._contexts(context))
            self._operator = context
            return self._install("operator_recorded", events, result, now)

    @_generic
    def propose(self, token, case_id, preparation):
        preparation = c.validate_preparation(preparation, pilot_plan=self._plan)
        with self._identity._lock:
            if self._state != "operator_recorded" or self._preparation is not None:
                _fail()
            context = self._access(token, case_id, "propose", person="person-owner")
            events, result = self._prospective("proposal", context, "proposed", preparation=preparation)
            now = self._final(self._contexts(context))
            self._preparation, self._preparation_sha256, self._owner = preparation, result["preparation_sha256"], context
            return self._install("proposed", events, result, now)

    @_generic
    def assess(self, token, case_id):
        with self._identity._lock:
            if self._state != "proposed" or self._assessor is not None:
                _fail()
            context = self._access(token, case_id, "assess", person="person-assessor")
            if context.principal.person_id in {item.principal.person_id for item in (self._operator, self._owner)}:
                _fail()
            events, result = self._prospective("preparation_assessment", context, "assessed")
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
                    (self._operator, self._owner, self._assessor)}:
                _fail()
            events, result = self._prospective("local_preparation_acknowledgment", context, "acknowledged")
            now = self._final(self._contexts(context))
            self._approver = context
            return self._install("acknowledged", events, result, now)

    @_generic
    def retire(self, token, case_id):
        with self._identity._lock:
            if self._state == "retired":
                _fail()
            context = self._access(token, case_id, "approve", person="person-releaser")
            events, result = self._prospective("retirement", context, "retired")
            # Restrictive retirement retains history and needs only this current
            # release authority, even if old evidence, reviewers or windows fail.
            now = self._final((context,), evidence=False, window=False)
            return self._install("retired", events, result, now, all_current=False)

    @_generic
    def status(self, token, case_id):
        with self._identity._lock:
            context = self._access(token, case_id, "read")
            result = self._view()
            if self._state != "retired":
                try:
                    now = self._final(self._contexts(context))
                    result["current_checks_satisfied"] = True
                    result["local_handover_preparation_ready"] = self._state == "acknowledged"
                except (c.HandoverError, PermissionDenied, IdentityUnavailable):
                    now = self._final((context,), evidence=False, window=False)
            else:
                now = self._final((context,), evidence=False, window=False)
            result["checked_at"] = now
            return result
