"""Current signed human incident management for one redacted local fixture.

Internal observation is deliberately independent of key eligibility. No service
method can approve a model, alter release policy or send an external message.
"""
from __future__ import annotations

import secrets

from ..production_identity.policy import PermissionDenied
from ..production_review.authorization import ReviewAuthorization
from . import contracts as c
from .store import MonitorStore, MonitorError, MonitorConflict, MonitorUnavailable
from .receiver import FixtureAlertReceiver


def _owned(value):
    return c.strict_json(c.canonical_bytes(value, max_bytes=c.MAX_BYTES), max_bytes=c.MAX_BYTES)


class FixtureMonitoringService:
    """Fixed agency/project/case-a metadata namespace, not agency authorization."""
    def __init__(self, identity, store, *, expected_pin, checkpoint_sink,
                 profile="agency_private_cloud"):
        if type(profile) is not str or profile != "local_public_fixture":
            raise MonitorError("Production monitoring is unavailable")
        if type(store) is not MonitorStore or not callable(checkpoint_sink):
            raise MonitorError("Trusted local monitoring components required")
        self._authorization = ReviewAuthorization(identity)
        self._identity, self._store = identity, store
        self._pin = c.validate_pin(expected_pin)
        if self._pin["store_id"] != store.store_id:
            raise MonitorError("Monitoring checkpoint rejected")
        self._sink, self._publishing = checkpoint_sink, False
        # Promote the latest validated history before accepting new work.
        with identity._lock:
            self._publish(store.read(expected_pin=self._pin, guard=identity._time), identity._time)

    @property
    def pin(self):
        with self._identity._lock:
            return c.validate_pin(self._pin)

    def _available(self):
        if self._publishing:
            raise MonitorUnavailable("Monitoring checkpoint unavailable")

    def _access(self, token, case_id):
        self._available()
        if case_id != "case-a" or type(case_id) is not str:
            raise PermissionDenied("Monitoring scope denied")
        context = self._authorization.access(token, case_id, "read")
        if (context.case.agency_id, context.case.project_id, context.case.case_id) != ("agency", "project", "case-a"):
            raise PermissionDenied("Monitoring scope denied")
        self._guard(context)
        return context

    def _guard(self, context):
        now = self._authorization.recheck_many((context,))
        grants = [grant for grant in self._identity._fresh(now).grants
                  if (grant.person_id, grant.agency_id, grant.project_id, grant.case_id)
                  == (context.principal.person_id, "agency", "project", "case-a")]
        if len(grants) != 1 or "auditor" not in grants[0].roles:
            raise PermissionDenied("Current monitoring auditor authority required")
        return now

    def _publish(self, snapshot, guard):
        snapshot = _owned(snapshot)
        pin = c.validate_pin(snapshot["pin"])
        if (pin["store_id"] != self._pin["store_id"] or pin["sequence"] < self._pin["sequence"]
                or pin["sequence"] == self._pin["sequence"] and pin != self._pin):
            raise MonitorUnavailable("Monitoring checkpoint rejected")
        # A committed head must never be forgotten, including sink failures.
        self._pin = pin
        if self._publishing:
            raise MonitorUnavailable("Monitoring checkpoint unavailable")
        self._publishing = True
        try:
            self._sink(c.validate_pin(pin))
        except Exception:
            raise MonitorUnavailable("Monitoring checkpoint unavailable") from None
        finally:
            self._publishing = False
        guard()  # Check current authority AFTER arbitrary trusted sink latency.
        return snapshot

    def flush_checkpoint(self):
        """Trusted recovery only; persists known history, never grants permission."""
        with self._identity._lock:
            self._available()
            return self._publish(self._store.read(expected_pin=self._pin, guard=self._identity._time),
                                 self._identity._time)

    def observe(self, event):
        event = c.validate_event(event)
        with self._identity._lock:
            self._available()
            def guard():
                now = self._identity._time()
                if event["observed_at"] > now:
                    raise MonitorError("Future monitoring observation rejected")
                return now
            guard()
            return self._publish(self._store.record(event, expected_pin=self._pin, guard=guard), guard)

    def snapshot(self, token, case_id="case-a"):
        with self._identity._lock:
            context = self._access(token, case_id)
            guard = lambda: self._guard(context)
            return self._publish(self._store.read(expected_pin=self._pin, guard=guard), guard)

    def incident(self, token, case_id, operation_id, incident_id, action):
        with self._identity._lock:
            context = self._access(token, case_id)
            guard = lambda: self._guard(context)
            c.hex_id(operation_id); c.hex_id(incident_id)
            actor = {"kind": "human", "authority_revision": context.authority_revision}
            state = self._publish(self._store.read(expected_pin=self._pin, guard=guard), guard)
            existing = next((item for item in state["operations"] if item["operation_id"] == operation_id), None)
            at = guard()
            if existing is not None:
                intent = {"kind": "action", "operation_id": operation_id,
                          "incident_id": incident_id, "action": action, "actor": actor}
                if {key: value for key, value in existing.items() if key != "at"} != intent:
                    raise MonitorConflict("Incident operation already binds different intent")
                at = existing["at"]
            snapshot = self._store.action(operation_id, incident_id, action, actor,
                at=at, expected_pin=self._pin, guard=guard)
            return self._publish(snapshot, guard)

    def route_pending(self, token, case_id, receiver):
        """Local custody + sender acknowledgment, not external notification."""
        if type(receiver) is not FixtureAlertReceiver:
            raise MonitorError("Trusted local receiver required")
        with self._identity._lock:
            context = self._access(token, case_id)
            guard = lambda: self._guard(context)
            state = self._publish(self._store.read(expected_pin=self._pin, guard=guard), guard)
            receiver.snapshot(guard=guard, expected_alerts=state["alerts"])
            for alert in state["alerts"]:
                alert = c.validate_alert(alert)
                if alert["acknowledged"]:
                    continue
                guard()
                received = receiver.receive(alert, expected_pin=receiver.pin, guard=guard)
                immutable = {key: value for key, value in alert.items()
                             if key not in {"acknowledged", "receiver_pin"}}
                if received["delivery"]["alert"] != immutable:
                    raise MonitorUnavailable("Local receiver binding rejected")
                guard()
                state = self._store.acknowledge_alert(secrets.token_hex(16), alert["alert_id"],
                    received["pin"], at=guard(), expected_pin=self._pin, guard=guard)
                state = self._publish(state, guard)
            receiver.snapshot(guard=guard, expected_alerts=state["alerts"])
            guard()
            return state
