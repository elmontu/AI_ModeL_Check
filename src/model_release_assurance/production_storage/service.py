"""Case-scoped public-fixture storage controls; no private-data intake or deletion.

Identity authorization always acquires its lock before this service's lock.
Read grants and holds are in memory and are not durable production custody,
worker sandboxing, admission/witness commits or model-delivery authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from threading import RLock
from typing import Any
import uuid

from ..production_identity.policy import Conflict, PermissionDenied
from .contracts import FIXTURE_ID, ObjectReference

FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False}
MAX_GRANTS = 256
MAX_SNAPSHOTS = 64
MAX_SNAPSHOT_OBJECTS = 8
_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_GRANT_ID = re.compile(r"[0-9a-f]{32}\Z")


def _bounded_integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " must be a bounded integer")
    return value


@dataclass
class _ReadGrant:
    grant_id: str
    reference: ObjectReference
    job_id: str
    worker_identity: Any
    worker_person_id: str
    grantor: Any
    authority_revision: int
    created_at: int
    expires_at: int
    consumed: bool = False
    revoked: bool = False


class FixtureStorageService:
    """Trusted bootstrap wires one current-identity service to one fresh store.

    Public methods take raw signed tokens. The internal authorization callback
    and retained verified identities are server state, never caller proofs.
    Capacity includes consumed/revoked/expired grants: tombstones are not reused.
    """

    def __init__(self, identity_service, store):
        if not callable(getattr(identity_service, "_with_fixture_authorization", None)):
            raise ValueError("A current fixture identity service is required")
        if any(not callable(getattr(store, method, None)) for method in ("register_fixture", "metadata", "read", "freeze_snapshot")):
            raise ValueError("A bounded fixture object store is required")
        self._identity = identity_service
        self._store = store
        self._lock = RLock()
        self._grants: dict[str, _ReadGrant] = {}
        self._held: set[str] = set()
        self._snapshots: dict[str, Any] = {}

    def _run(self, token, case_id, action, operation):
        def authorized(context):
            with self._lock:
                return operation(context)
        return self._identity._with_fixture_authorization(token, case_id, action, authorized)

    def _reference(self, context, value):
        if type(value) is ObjectReference:
            reference = ObjectReference.from_dict(value.to_dict())
        elif type(value) is dict:
            reference = ObjectReference.from_dict(dict(value))
        else:
            raise ValueError("An exact object reference is required")
        if (reference.case_id, reference.agency_id, reference.project_id) != (
                context.case.case_id, context.case.agency_id, context.case.project_id):
            raise PermissionDenied("Object reference is outside the authorized case scope")
        self._store.metadata(reference)  # Verify registered exact reference, not caller digest alone.
        context.recheck()
        return reference

    def register_fixture(self, token, case_id, fixture_id, retention_seconds):
        def register(context):
            _bounded_integer(retention_seconds, "retention_seconds", 1, 86400)
            if type(fixture_id) is not str or fixture_id != FIXTURE_ID:
                raise ValueError("The built-in public fixture identifier is required")
            now = context.recheck()
            reference = self._store.register_fixture(case_id=context.case.case_id, agency_id=context.case.agency_id,
                        project_id=context.case.project_id, fixture_id=fixture_id,
                        created_at=now, retention_until=now + retention_seconds)
            context.recheck()
            # A failed authorization recheck may leave retained fixture evidence;
            # there is deliberately no rollback deletion or private-data intake.
            return {**FLAGS, "reference": reference.to_dict(), "reference_digest": reference.reference_digest}
        return self._run(token, case_id, "object:register", register)

    def metadata(self, token, case_id, reference):
        def inspect(context):
            checked = self._reference(context, reference)
            metadata = self._store.metadata(checked)
            context.recheck()
            return {**metadata, **FLAGS, "held": checked.reference_digest in self._held}
        return self._run(token, case_id, "object:metadata", inspect)

    def freeze_snapshot(self, token, case_id, references):
        def freeze(context):
            if not isinstance(references, (tuple, list)) or not 1 <= len(references) <= MAX_SNAPSHOT_OBJECTS:
                raise ValueError("Snapshot requires one to eight exact object references")
            if len(self._snapshots) >= MAX_SNAPSHOTS:
                raise Conflict("Fixture snapshot capacity reached")
            checked = tuple(self._reference(context, value) for value in tuple(references))
            if len({value.reference_digest for value in checked}) != len(checked):
                raise ValueError("Snapshot object references must be unique")
            now = context.recheck()
            retention_until = min(value.retention_until for value in checked)
            if retention_until < now:
                raise Conflict("Snapshot cannot extend an expired source retention commitment")
            snapshot = self._store.freeze_snapshot(case_id=context.case.case_id, agency_id=context.case.agency_id,
                        project_id=context.case.project_id, references=checked, created_at=now,
                        retention_until=retention_until)
            context.recheck()
            if snapshot.snapshot_digest in self._snapshots:
                raise Conflict("Fixture snapshot identity cannot be reused")
            self._snapshots[snapshot.snapshot_digest] = snapshot
            return {**FLAGS, "snapshot": snapshot.to_dict(), "snapshot_digest": snapshot.snapshot_digest}
        return self._run(token, case_id, "snapshot:freeze", freeze)

    def issue_read_grant(self, token, case_id, reference, worker_token, job_id, ttl_seconds):
        def issue(context):
            _bounded_integer(ttl_seconds, "ttl_seconds", 1, 60)
            if type(job_id) is not str or not _JOB_ID.fullmatch(job_id):
                raise ValueError("A bounded exact job identifier is required")
            if len(self._grants) >= MAX_GRANTS:
                raise Conflict("Fixture read-grant capacity reached; tombstones are retained")
            checked = self._reference(context, reference)
            worker = context.verify_target(worker_token, "object:read")
            if "job:" + job_id not in worker.identity.scopes:
                raise PermissionDenied("Target workload token lacks the exact job scope")
            grant_id = uuid.uuid4().hex
            if grant_id in self._grants:
                raise Conflict("Fixture grant identity cannot be reused")
            now = context.recheck_with(worker)
            expires_at = min(now + ttl_seconds, context.identity.expires_at, worker.identity.expires_at)
            if expires_at <= now:
                raise PermissionDenied("Grant has no remaining authorized lifetime")
            self._grants[grant_id] = _ReadGrant(grant_id, checked, job_id, worker.identity,
                      worker.principal.person_id, context, context.authority_revision, now, expires_at)
            return {**FLAGS, "grant_id": grant_id, "job_id": job_id, "expires_at": expires_at,
                    "reference_digest": checked.reference_digest, "single_use": True}
        return self._run(token, case_id, "object:grant", issue)

    def _grant(self, context, grant_id):
        if type(grant_id) is not str or not _GRANT_ID.fullmatch(grant_id):
            raise PermissionDenied("Read grant is not eligible")
        grant = self._grants.get(grant_id)
        if grant is None or (grant.reference.case_id, grant.reference.agency_id, grant.reference.project_id) != (
                context.case.case_id, context.case.agency_id, context.case.project_id):
            raise PermissionDenied("Read grant is not eligible")
        return grant

    def _read_eligible(self, context, checked, grant):
        now = context.recheck_with(grant.grantor)
        if (grant.reference != checked or grant.consumed or grant.revoked or now >= grant.expires_at
                or grant.authority_revision != context.authority_revision
                or grant.worker_identity != context.identity or grant.worker_person_id != context.principal.person_id
                or "job:" + grant.job_id not in context.identity.scopes):
            raise PermissionDenied("Read grant is not currently eligible")
        # The shared-time check includes the verified issuer: revoking its
        # token/client/principal cannot leave an outstanding grant usable.
        return now

    def read(self, token, case_id, reference, grant_id):
        def read_bytes(context):
            checked = self._reference(context, reference)
            grant = self._grant(context, grant_id)
            self._read_eligible(context, checked, grant)
            content = self._store.read(checked)
            # No bytes leave this callback until identity/authority/grant expiry
            # are rechecked after I/O and one use is atomically consumed.
            self._read_eligible(context, checked, grant)
            grant.consumed = True
            return content
        return self._run(token, case_id, "object:read", read_bytes)

    def revoke_grant(self, token, case_id, grant_id):
        def revoke(context):
            grant = self._grant(context, grant_id)
            context.recheck()
            grant.revoked = True
            return {**FLAGS, "grant_id": grant.grant_id, "revoked": True, "consumed": grant.consumed}
        return self._run(token, case_id, "object:grant", revoke)

    def set_hold(self, token, case_id, reference, held):
        def hold(context):
            if type(held) is not bool:
                raise ValueError("held must be an explicit boolean")
            checked = self._reference(context, reference)
            context.recheck()
            if held:
                self._held.add(checked.reference_digest)
            else:
                self._held.discard(checked.reference_digest)
            return {**FLAGS, "reference_digest": checked.reference_digest, "held": held,
                    "hold_scope": "deletion_only", "deletion_performed": False}
        return self._run(token, case_id, "object:hold", hold)

    def deletion_eligibility(self, token, case_id, reference):
        def inspect(context):
            checked = self._reference(context, reference)
            now = context.recheck()
            active = sum(1 for grant in self._grants.values() if grant.reference == checked
                         and not grant.revoked and not grant.consumed and now < grant.expires_at)
            blockers = []
            if now < checked.retention_until:
                blockers.append("retention_active")
            if checked.reference_digest in self._held:
                blockers.append("hold_active")
            if active:
                blockers.append("active_read_grant")
            return {**FLAGS, "reference_digest": checked.reference_digest, "eligible_for_deletion": not blockers,
                    "blockers": blockers, "active_read_grants": active, "deletion_performed": False,
                    "limitation": "Eligibility is an in-memory fixture observation; no deletion API or durable retention enforcement is provided."}
        return self._run(token, case_id, "object:hold", inspect)
