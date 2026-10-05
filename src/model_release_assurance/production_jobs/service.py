"""Current-authority coordinator for one durable public-fixture job recipe.

SQLite records jobs, lease fences and one-use reservation tombstones. Existing
PRD07 object/grant and identity state remain in memory: a fresh broker fences old
work and does not reconstruct old grants or authorize historical output.
The runner is a fixed local process fixture, not hostile-code/network isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from threading import Event
import uuid

from ..production_identity.policy import Conflict, PermissionDenied
from ..production_storage.backend import _validate_fixture_bytes
from ..production_storage.contracts import ObjectReference
from .executor import ADAPTER_ID, MAX_STDERR_BYTES, MAX_STDOUT_BYTES, worker_sha256

FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False,
         "production_authorized": False, "hostile_code_isolated": False, "network_isolated": False}
_ID = re.compile(r"[0-9a-f]{32}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
MAX_ATTEMPTS = 3
LEASE_SECONDS = 30
TIMEOUT_SECONDS = 5
MAX_CAPTURE_COUNT_BYTES = 2**40
_EXECUTION_FIELDS = {"status", "output", "input_sha256", "worker_sha256", "exit_code", "stdout_bytes",
                     "stderr_bytes", "cleanup_confirmed", "elapsed_seconds", "fixture_only",
                     "hostile_code_isolated", "network_isolated"}
_STATUSES = {"completed", "failed", "timed_out", "cancelled", "output_limit", "cleanup_failed"}


def _hash(value):
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("An exact lowercase SHA256 is required")
    return value


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _credential(context):
    identity = context.identity
    return {"issuer": identity.issuer, "subject": identity.subject, "client_id": identity.client_id,
            "token_id": identity.token_id, "key_id": identity.key_id, "issued_at": identity.issued_at,
            "expires_at": identity.expires_at, "scopes": sorted(identity.scopes), "case_ids": sorted(identity.case_ids),
            "acr": identity.acr, "auth_time": identity.auth_time,
            "person_id": context.principal.person_id, "authority_revision": context.authority_revision}


def _holder(context):
    return hashlib.sha256(json.dumps(_credential(context), sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class _Binding:
    submitter: object
    grantor: object
    worker_job: object
    worker_read: object
    grant_id: str
    storage_grant_id: str
    holder: str


class FixtureJobService:
    """Trusted bootstrap only; every operation receives and verifies a raw JWT."""

    def __init__(self, identity_service, storage_service, job_store, runner):
        if any(not callable(getattr(identity_service, method, None)) for method in (
                "_with_fixture_authorization", "_with_fixture_job_authorization", "_time")):
            raise ValueError("A current fixture identity service is required")
        if getattr(storage_service, "_identity", None) is not identity_service:
            raise ValueError("Job storage must share the exact identity service")
        if not callable(getattr(runner, "run", None)):
            raise ValueError("The fixed public fixture runner is required")
        if any(not callable(getattr(job_store, method, None)) for method in (
                "activate_broker", "submit", "get", "cancel", "authorize_input", "claim",
                "consume_input", "with_current_lease", "complete", "fail")):
            raise ValueError("A durable bounded fixture job store is required")
        self._identity, self._storage, self._store, self._runner = identity_service, storage_service, job_store, runner
        self.instance_id = uuid.uuid4().hex
        self._submissions = {}
        self._bindings: dict[str, _Binding] = {}
        self._result_bindings: dict[tuple[str, str], _Binding] = {}
        self._running = {}
        with self._identity._lock:
            self._store.activate_broker(self.instance_id, guard=self._identity._time)

    def _run(self, token, case_id, action, operation):
        bridge = (self._identity._with_fixture_job_authorization if action in {"job:run", "case:read"}
                  else self._identity._with_fixture_authorization)
        return bridge(token, case_id, action, operation)

    @staticmethod
    def _kind(context, kind):
        if context.principal.kind != kind:
            raise PermissionDenied("Job operation requires the designated actor kind")

    def _get(self, context, job_id):
        if type(job_id) is not str or not _ID.fullmatch(job_id):
            raise ValueError("An exact fixture job identifier is required")
        row = self._store.get(job_id=job_id, broker_id=self.instance_id, guard=context.recheck)
        descriptor = row["descriptor"]
        if (descriptor["agency_id"], descriptor["project_id"], descriptor["case_id"]) != (
                context.case.agency_id, context.case.project_id, context.case.case_id):
            raise PermissionDenied("Job is outside the authorized case")
        return row

    def _binding(self, row):
        binding = self._bindings.get(row["job_id"])
        if binding is None:
            raise PermissionDenied("Fresh broker input authorization is required")
        return binding

    def _guard(self, context, binding):
        return context.recheck_with(binding.submitter, binding.grantor, binding.worker_job, binding.worker_read)

    def _public(self, row, context):
        value = _copy(row)
        current = False
        if value.get("result") is not None:
            binding = self._result_bindings.get((value["job_id"], value["result"].get("attempt_id")))
            try:
                if binding is not None:
                    self._guard(context, binding)
                    current = True
            except Exception:
                # Historical public fixture output is not reauthorized by a
                # current reader alone; old actor/trust state must remain valid.
                current = False
            if not current:
                value["result"] = None
        return {**value, **FLAGS, "result_authorization_current": current,
                "storage_authority_restart_durable": False}

    def submit(self, operator_token, case_id, recipe_id, reference, request_id):
        def submit(context):
            self._kind(context, "human")
            if recipe_id != ADAPTER_ID or type(recipe_id) is not str:
                raise ValueError("Only the fixed public count recipe is supported")
            if type(request_id) is not str or not _REQUEST.fullmatch(request_id):
                raise ValueError("A bounded idempotency request identifier is required")
            if type(reference) is ObjectReference:
                checked = ObjectReference.from_dict(reference.to_dict())
            elif type(reference) is dict:
                checked = ObjectReference.from_dict(_copy(reference))
            else:
                raise ValueError("An exact registered object reference is required")
            # Submission requires the explicit metadata scope as well as job:run.
            metadata = self._storage.metadata(operator_token, case_id, checked)
            if metadata["reference"] != checked.to_dict():
                raise PermissionDenied("Registered object reference changed")
            descriptor = {"schema": "mra-fixture-job/v1", "environment": "public_fixture",
                "agency_id": context.case.agency_id, "project_id": context.case.project_id,
                "case_id": context.case.case_id, "object_reference": checked.to_dict(),
                "adapter_id": ADAPTER_ID, "worker_sha256": _hash(worker_sha256()),
                "max_attempts": MAX_ATTEMPTS, "lease_seconds": LEASE_SECONDS, "timeout_seconds": TIMEOUT_SECONDS}
            row = self._store.submit(descriptor=descriptor, request_id=request_id,
                submitter=context.principal.person_id, broker_id=self.instance_id, guard=context.recheck)
            existing = self._submissions.get(row["job_id"])
            if existing is None:
                self._submissions[row["job_id"]] = context
            elif existing.identity != context.identity:
                raise Conflict("Idempotent job cannot replace its authoritative submitter credential")
            return self._public(row, context)
        return self._run(operator_token, case_id, "job:run", submit)

    def authorize_input(self, steward_token, case_id, job_id, worker_token, ttl_seconds):
        def authorize(context):
            self._kind(context, "human")
            if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 60:
                raise ValueError("Input grant lifetime must be from one to sixty seconds")
            row = self._get(context, job_id)
            now = context.recheck()
            if row["state"] == "running" and any(attempt["fence"] == row["fence"]
                    and attempt["state"] == "running" and now < attempt["expires_at"]
                    for attempt in row["attempts"]):
                raise Conflict("A current running attempt cannot replace its input authority")
            submitter = self._submissions.get(job_id)
            if submitter is None:
                raise PermissionDenied("A fresh broker submission is required")
            worker_job = context.verify_target(worker_token, "job:run")
            worker_read = context.verify_target(worker_token, "object:read")
            self._kind(worker_job, "workload")
            if worker_job.identity != worker_read.identity or "job:" + job_id not in worker_job.identity.scopes:
                raise PermissionDenied("Worker credential lacks the exact signed job scope")
            holder = _holder(worker_job)
            def guard():
                return context.recheck_with(submitter, worker_job, worker_read)
            guard()
            storage_grant = self._storage.issue_read_grant(steward_token, case_id,
                row["descriptor"]["object_reference"], worker_token, job_id, ttl_seconds)
            grant = self._store.authorize_input(job_id=job_id, holder=holder,
                authority_revision=context.authority_revision, storage_grant_id=storage_grant["grant_id"],
                expires_at=storage_grant["expires_at"], broker_id=self.instance_id, guard=guard)
            self._bindings[job_id] = _Binding(submitter, context, worker_job, worker_read,
                grant["id"], storage_grant["grant_id"], holder)
            return {**FLAGS, "job_id": job_id, "grant_id": grant["id"], "expires_at": grant["expires_at"],
                    "single_use": True, "storage_grant_remains_process_local": True}
        return self._run(steward_token, case_id, "object:grant", authorize)

    def _failed_owned(self, lease, reason):
        if lease is None:
            return
        try:
            with self._identity._lock:
                # Internal cleanup can record failure despite revoked authority.
                # This clock-only guard can never commit a successful result.
                self._store.fail(lease=lease, reason=reason, broker_id=self.instance_id, guard=self._identity._time)
        except Exception:
            # Old broker/fence/expired lease is deliberately not resurrected.
            pass

    def _validate_execution(self, result, lease, descriptor, content):
        if not callable(getattr(result, "to_dict", None)):
            raise ValueError("Invalid fixture execution receipt")
        receipt = _copy(result.to_dict())
        if type(receipt) is not dict or set(receipt) != _EXECUTION_FIELDS:
            raise ValueError("Invalid fixture execution receipt")
        if (receipt["status"] not in _STATUSES or receipt["fixture_only"] is not True
                or receipt["hostile_code_isolated"] is not False or receipt["network_isolated"] is not False
                or type(receipt["cleanup_confirmed"]) is not bool
                or receipt["input_sha256"] != hashlib.sha256(content).hexdigest()
                or receipt["worker_sha256"] != descriptor["worker_sha256"]
                or receipt["worker_sha256"] != worker_sha256()):
            raise ValueError("Fixture execution identity or status mismatch")
        for key in ("stdout_bytes", "stderr_bytes"):
            # Counts measure all drained bytes, including discarded overflow;
            # they are evidence counters, never allocation or retained-content sizes.
            if type(receipt[key]) is not int or not 0 <= receipt[key] <= MAX_CAPTURE_COUNT_BYTES:
                raise ValueError("Invalid bounded fixture output receipt")
        elapsed = receipt["elapsed_seconds"]
        if type(elapsed) not in {float, int} or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid fixture elapsed time")
        if receipt["exit_code"] is not None and type(receipt["exit_code"]) is not int:
            raise ValueError("Invalid fixture exit status")
        if receipt["status"] == "completed":
            expected = {"schema": ADAPTER_ID, "input_sha256": hashlib.sha256(content).hexdigest(),
                        "categories": 2, "total": 19, "job_id": lease["job_id"], "attempt_id": lease["attempt_id"]}
            if (receipt["output"] != expected or receipt["exit_code"] != 0
                    or receipt["stdout_bytes"] > MAX_STDOUT_BYTES or receipt["stderr_bytes"] > MAX_STDERR_BYTES
                    or receipt["cleanup_confirmed"] is not True
                    or type(receipt["output"].get("categories")) is not int
                    or type(receipt["output"].get("total")) is not int):
                raise ValueError("Invalid completed public fixture output")
        elif receipt["output"] is not None:
            raise ValueError("Failed fixture execution cannot expose output")
        return receipt

    def run(self, worker_token, case_id, job_id, expected_descriptor_sha256):
        _hash(expected_descriptor_sha256)
        started = {}
        def start(context):
            self._kind(context, "workload")
            row = self._get(context, job_id)
            if not hmac.compare_digest(row["digest"], expected_descriptor_sha256):
                raise Conflict("The exact current job descriptor digest is required")
            if row["descriptor"]["worker_sha256"] != worker_sha256():
                raise Conflict("The approved fixture implementation changed")
            binding = self._binding(row)
            if _holder(context) != binding.holder or context.identity != binding.worker_job.identity:
                raise PermissionDenied("Worker credential differs from authorized job holder")
            guard = lambda: self._guard(context, binding)
            guard()
            lease = self._store.claim(job_id=job_id, grant_id=binding.grant_id, holder=binding.holder,
                authority_revision=context.authority_revision, credential_expires=context.identity.expires_at,
                broker_id=self.instance_id, guard=guard)
            if lease is None:
                raise Conflict("Job has no eligible fixture attempt")
            started.update(lease=lease, binding=binding, descriptor=row["descriptor"])
            reserved = self._store.consume_input(lease=lease, broker_id=self.instance_id, guard=guard)
            if (reserved["storage_grant_id"] != binding.storage_grant_id
                    or reserved["reference"] != row["descriptor"]["object_reference"]):
                raise PermissionDenied("Durable input reservation differs from authorized object")
            def read_reserved():
                content = self._storage.read(worker_token, case_id, reserved["reference"], binding.storage_grant_id)
                _validate_fixture_bytes(content)
                guard()
                return content
            content = self._store.with_current_lease(lease=lease, broker_id=self.instance_id,
                guard=guard, operation=read_reserved)
            event = Event()
            self._running[job_id] = (lease["attempt_id"], event)
            started.update(content=content, event=event)
        try:
            self._run(worker_token, case_id, "job:run", start)
        except Exception:
            self._failed_owned(started.get("lease"), "input_unavailable")
            raise
        lease, binding = started["lease"], started["binding"]
        try:
            result = self._runner.run(job_id=job_id, attempt_id=lease["attempt_id"],
                fixture_bytes=started["content"], timeout_seconds=started["descriptor"]["timeout_seconds"],
                cancel_event=started["event"])
            receipt = self._validate_execution(result, lease, started["descriptor"], started["content"])
            def finish(context):
                self._kind(context, "workload")
                if _holder(context) != binding.holder or context.identity != binding.worker_job.identity:
                    raise PermissionDenied("Completing worker identity changed")
                guard = lambda: self._guard(context, binding)
                guard()
                if receipt["status"] == "completed":
                    row = self._store.complete(lease=lease, result=receipt["output"],
                        broker_id=self.instance_id, guard=guard)
                    self._result_bindings[(job_id, lease["attempt_id"])] = binding
                else:
                    reason = receipt["status"] if receipt["cleanup_confirmed"] else "cleanup_failed"
                    row = self._store.fail(lease=lease, reason=reason, broker_id=self.instance_id, guard=guard)
                return self._public(row, context)
            return self._run(worker_token, case_id, "job:run", finish)
        except Exception:
            self._failed_owned(lease, "failed")
            raise
        finally:
            with self._identity._lock:
                running = self._running.get(job_id)
                if running is not None and running[0] == lease["attempt_id"]:
                    self._running.pop(job_id, None)

    def read_job(self, human_token, case_id, job_id):
        def read(context):
            self._kind(context, "human")
            return self._public(self._get(context, job_id), context)
        return self._run(human_token, case_id, "case:read", read)

    def cancel(self, operator_token, case_id, job_id):
        def cancel(context):
            self._kind(context, "human")
            self._get(context, job_id)
            row = self._store.cancel(job_id=job_id, broker_id=self.instance_id, guard=context.recheck)
            running = self._running.get(job_id)
            if running is not None:
                running[1].set()
            return self._public(row, context)
        return self._run(operator_token, case_id, "job:run", cancel)



