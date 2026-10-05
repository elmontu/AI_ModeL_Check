"""Current signed identity around a bounded, non-authorizing registry fixture.

The trusted bootstrap owns the registry/accounts, identity, fixed storage and
broker handover. Public methods accept raw JWTs and exact metadata, never caller
roles, charge sizes, account selection, policies or purported approvals.
"""
from __future__ import annotations

import hashlib
import uuid

from ..production_identity.policy import PermissionDenied
from ..production_storage.contracts import ObjectReference
from ..production_trust.verification import RegistryAccessTokenVerifier
from .contracts import (FLAGS, FIXTURE_SHA256, FIXTURE_SIZE_BYTES, account_id,
                        digest, fixed_policy, hex_id, validate_request,
                        validate_commit_context, canonical_bytes, strict_json)


class FixtureRegistryService:
    """Single-host metadata rehearsal using existing PRD06/07/08 authority.

    Human test operators prepare/commit a fictional test transaction using
    job:run. Workloads with job:run publish metadata for their authorized case.
    Case readers see historical metadata. None of these are release roles.
    """

    def __init__(self, identity_service, storage_service, registry_store):
        verifier = getattr(identity_service, "_verifier", None)
        if not isinstance(verifier, RegistryAccessTokenVerifier):
            raise ValueError("Current fixture trust registry is required")
        if getattr(storage_service, "_identity", None) is not identity_service:
            raise ValueError("Storage and registry must share current identity")
        self._identity, self._storage, self._store = identity_service, storage_service, registry_store
        self._trust = verifier.registry
        self.instance_id = uuid.uuid4().hex
        with self._identity._lock:
            status = registry_store.inspect(guard=self._identity._time)
            self._broker = registry_store.activate_broker(self.instance_id,
                expected_epoch=status["broker_epoch"], guard=self._identity._time)

    @staticmethod
    def _kind(context, kind):
        if context.principal.kind != kind:
            raise PermissionDenied("Registry operation requires the designated actor kind")

    @staticmethod
    def _scope(context):
        case = context.case
        return case.agency_id, case.project_id, case.case_id

    @staticmethod
    def _credential(context):
        identity = context.identity
        return digest({"issuer": identity.issuer, "subject": identity.subject,
            "client_id": identity.client_id, "token_id": identity.token_id,
            "key_id": identity.key_id, "issued_at": identity.issued_at,
            "expires_at": identity.expires_at, "scopes": sorted(identity.scopes),
            "case_ids": sorted(identity.case_ids), "acr": identity.acr,
            "auth_time": identity.auth_time, "person_id": context.principal.person_id})

    @staticmethod
    def _owner(context):
        # A refreshed current token for the same worker can acknowledge its
        # lease. A different subject/client/person cannot steal that lease.
        identity = context.identity
        return digest({"issuer": identity.issuer, "subject": identity.subject,
                       "client_id": identity.client_id, "person_id": context.principal.person_id})

    def _run(self, token, case_id, action, callback):
        return self._identity._with_fixture_job_authorization(token, case_id, action, callback)

    def _guard(self, context, trust_revision, reference=None):
        def current():
            if self._trust.revision != trust_revision:
                raise PermissionDenied("Trust revision changed during registry operation")
            if reference is not None:
                self._storage._reference(context, reference.to_dict())
                # This internal verifier reads only PRD07's exact 357-byte
                # fictional count object; no bytes escape to a registry caller.
                data = self._storage._store.read(reference)
                if len(data) != FIXTURE_SIZE_BYTES or hashlib.sha256(data).hexdigest() != FIXTURE_SHA256:
                    raise PermissionDenied("Registered fixture bytes changed")
                if self._trust.revision != trust_revision:
                    raise PermissionDenied("Trust revision changed during byte verification")
            # The revision property samples the clock. The LAST sample must
            # authorize the token and retention together, before DB commit.
            now = context.recheck()
            if reference is not None and not reference.created_at <= now < reference.retention_until:
                raise PermissionDenied("Registered fixture retention expired")
            return now
        return current

    def prepare(self, token, case_id, reference, request_id):
        """Capture immutable intent once; callers retain it for exact retries."""
        hex_id(request_id)
        parsed = ObjectReference.from_dict(reference)
        def prepare(context):
            self._kind(context, "human")
            agency, project, case = self._scope(context)
            guard = self._guard(context, self._trust.revision, parsed)
            with self._storage._lock, self._storage._store._lock:
                guard()
                account = self._store.account(agency, project, broker=self._broker, guard=guard)
                head = self._store.case(agency, project, case, broker=self._broker, guard=guard)
                request = validate_request({"schema": "mra-fixture-registry-request/v1",
                    "environment": "public_fixture", "store_id": self._store.store_id,
                    "account_id": account_id(agency, project), "request_id": request_id,
                    "agency_id": agency, "project_id": project, "case_id": case,
                    "actor_person_id": context.principal.person_id,
                    "expected_account_sequence": account["sequence"],
                    "expected_account_head_sha256": account["head_sha256"],
                    "expected_case_sequence": head["sequence"],
                    "expected_case_head_sha256": head["head_sha256"],
                    "object_reference": parsed.to_dict(), "source_sha256": parsed.sha256,
                    "policy_sha256": digest(fixed_policy()), **FLAGS})
                guard()
                return request
        return self._run(token, case_id, "job:run", prepare)

    def commit(self, token, case_id, request):
        request = validate_request(request)
        parsed = ObjectReference.from_dict(request["object_reference"])
        def commit(context):
            self._kind(context, "human")
            if (request["agency_id"], request["project_id"], request["case_id"]) != self._scope(context):
                raise PermissionDenied("Intent is outside the authorized case")
            if request["actor_person_id"] != context.principal.person_id:
                raise PermissionDenied("Intent belongs to another current principal")
            revision = self._trust.revision
            guard = self._guard(context, revision, parsed)
            current = validate_commit_context({"broker_id": self._broker["broker_id"],
                "broker_epoch": self._broker["epoch"], "actor_person_id": context.principal.person_id,
                "actor_credential_sha256": self._credential(context),
                "authority_revision": context.authority_revision, "trust_revision": revision})
            with self._storage._lock, self._storage._store._lock:
                guard()
                return self._store.commit(request, current, broker=self._broker, guard=guard)
        return self._run(token, case_id, "job:run", commit)

    def state(self, token, case_id):
        def state(context):
            agency, project, case = self._scope(context)
            guard = self._guard(context, self._trust.revision)
            # Separate snapshots can become stale between reads. Every commit
            # still compares BOTH heads under a single database write lock.
            return {"account": self._store.account(agency, project, broker=self._broker, guard=guard),
                    "case": self._store.case(agency, project, case, broker=self._broker, guard=guard),
                    "storage_authority_restart_durable": False, **FLAGS}
        return self._run(token, case_id, "case:read", state)

    def read(self, token, case_id, request_id):
        hex_id(request_id)
        def read(context):
            agency, project, case = self._scope(context)
            receipt = self._store.get_receipt(agency, project, request_id, broker=self._broker,
                guard=self._guard(context, self._trust.revision))
            if receipt is not None and receipt["receipt"]["case_id"] != case:
                raise PermissionDenied("Historical receipt is outside the authorized case")
            return receipt  # Historical metadata, never current release permission.
        return self._run(token, case_id, "case:read", read)

    def claim_outbox(self, token, case_id, lease_seconds=30):
        def claim(context):
            self._kind(context, "workload")
            return self._store.claim_outbox(*self._scope(context), owner_sha256=self._owner(context),
                broker=self._broker, lease_seconds=lease_seconds,
                guard=self._guard(context, self._trust.revision))
        return self._run(token, case_id, "job:run", claim)

    def acknowledge(self, token, case_id, lease):
        lease = strict_json(canonical_bytes(lease))
        def acknowledge(context):
            self._kind(context, "workload")
            agency, project, case = self._scope(context)
            if type(lease) is not dict or lease.get("account_id") != account_id(agency, project) or lease.get("case_id") != case:
                raise PermissionDenied("Lease is outside the authorized case")
            return self._store.acknowledge(lease, owner_sha256=self._owner(context), broker=self._broker,
                guard=self._guard(context, self._trust.revision))
        return self._run(token, case_id, "job:run", acknowledge)
