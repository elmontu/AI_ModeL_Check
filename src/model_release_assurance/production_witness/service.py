"""Current-token coordination of external intents, registry commits and witness.

The required checkpoint sink is a trusted bootstrap capability, not a public
parameter. It must retain the returned pin outside database restore custody
before it acknowledges success. Physical independent custody is unverified here.
"""
from __future__ import annotations

from ..production_identity.policy import PermissionDenied
from ..production_registry.contracts import validate_request, digest as request_digest
from .contracts import FLAGS, create_intent, validate_pin, canonical_bytes, strict_json
from .reader import RegistryHistoryReader


class WitnessQuarantined(RuntimeError):
    """Unknown or inconsistent history cannot produce a witnessed success."""


def _copy(value):
    return strict_json(canonical_bytes(value, max_bytes=32 * 1024 * 1024), max_bytes=32 * 1024 * 1024)


class FixtureWitnessService:
    """Trusted local bootstrap, raw-token-only case operations, no delivery."""

    def __init__(self, registry_service, witness_store, *, expected_pin, checkpoint_sink):
        if not callable(checkpoint_sink):
            raise ValueError("An external checkpoint sink is required")
        self._registry, self._identity = registry_service, registry_service._identity
        self._reader = RegistryHistoryReader(registry_service)
        self._witness = witness_store
        self._pin = validate_pin(expected_pin)
        self._sink = checkpoint_sink
        if self._pin["registry_id"] != registry_service._store.store_id:
            raise WitnessQuarantined("Registry is outside the independently pinned namespace")
        # Validate the supplied floor; never enroll or discover a replacement
        # witness/ledger just because a database was reopened.
        with self._identity._lock:
            self._accept(witness_store.status(expected_pin=self._pin, guard=self._identity._time),
                         self._identity._time)

    @property
    def required_pin(self):
        return validate_pin(self._pin)

    def _guard(self, context):
        return self._registry._guard(context, self._registry._trust.revision)

    def _accept(self, diagnosis, guard):
        pin = validate_pin(diagnosis["pin"])
        if pin["revision"] < self._pin["revision"]:
            raise WitnessQuarantined("Witness checkpoint moved backwards")
        # Keep the newest known floor even when the external sink fails. A
        # subsequent call must establish this floor instead of starting over.
        self._pin = pin
        self._sink(validate_pin(pin))
        guard()  # Sink latency cannot outlive current case/token authority.
        return diagnosis

    def _observe(self, context, guard):
        return self._reader.with_snapshot(guard=guard, callback=lambda history:
            self._accept(self._witness.observe(history, expected_pin=self._pin, guard=guard), guard))

    @staticmethod
    def _record(diagnosis, request_id, case_id):
        for row in diagnosis["intents"]:
            request = row["intent"]["request"]
            if request["request_id"] == request_id:
                if request["case_id"] != case_id:
                    raise PermissionDenied("Witness intent is outside the authorized case")
                return row
        return None

    @staticmethod
    def _scope(context, request):
        if (request["agency_id"], request["project_id"], request["case_id"]) != (
                context.case.agency_id, context.case.project_id, context.case.case_id):
            raise PermissionDenied("Intent is outside the authorized case")

    def _namespace(self, context):
        from ..production_registry.contracts import account_id
        if self._pin["namespace_id"] != account_id(context.case.agency_id, context.case.project_id):
            raise PermissionDenied("Case is outside the witnessed namespace")

    def _result(self, diagnosis, row):
        if row is None or row["state"] != "committed" or not diagnosis["reconciled"]:
            raise WitnessQuarantined("Outstanding intent requires recovery before witnessed success")
        return {"schema": "mra-fixture-witnessed-receipt/v1", "status": "witnessed_metadata",
                "witness_pin": validate_pin(diagnosis["pin"]), "receipt": _copy(row["receipt"]),
                "registry_sequence": diagnosis["registry_sequence"],
                "registry_head_sha256": diagnosis["registry_head_sha256"],
                "independent_custody_verified": False, **FLAGS}

    def commit(self, token, case_id, request):
        request = validate_request(request)
        def commit(context):
            self._registry._kind(context, "human")
            self._scope(context, request); self._namespace(context)
            if request["actor_person_id"] != context.principal.person_id:
                raise PermissionDenied("Intent belongs to another principal")
            guard = self._guard(context)
            diagnosis = self._observe(context, guard)
            row = self._record(diagnosis, request["request_id"], case_id)
            if row is not None:
                if request_digest(row["intent"]["request"]) != request_digest(request):
                    raise WitnessQuarantined("Permanent request ID names different intent")
                if row["state"] == "committed":
                    return self._result(diagnosis, row)
                if row["state"] == "aborted":
                    raise WitnessQuarantined("Irreversibly superseded intent cannot be retried")
                if row["intent"]["broker_epoch"] != self._registry._broker["epoch"]:
                    raise WitnessQuarantined("Pending old-broker intent requires recovery")
            else:
                def prepare(history):
                    intent = create_intent(history, request)
                    return self._accept(self._witness.prepare(intent, history,
                        expected_pin=self._pin, guard=guard), guard)
                diagnosis = self._reader.with_snapshot(guard=guard, callback=prepare)
            guard()
            # The external intent checkpoint has been accepted by the required
            # sink before entering the separate atomic registry transaction.
            self._registry.commit(token, case_id, request)
            diagnosis = self._observe(context, guard)
            return self._result(diagnosis, self._record(diagnosis, request["request_id"], case_id))
        return self._identity._with_fixture_job_authorization(token, case_id, "job:run", commit)

    def recover(self, token, case_id, request_id):
        """Current case-reader reconciliation of HISTORICAL metadata only."""
        from ..production_registry.contracts import hex_id
        hex_id(request_id)
        def recover(context):
            self._namespace(context)
            guard = self._guard(context)
            diagnosis = self._observe(context, guard)
            row = self._record(diagnosis, request_id, case_id)
            if row is None:
                raise WitnessQuarantined("Unknown irreversible intent")
            if row["state"] == "committed" and diagnosis["reconciled"]:
                return self._result(diagnosis, row)
            return {"schema": "mra-fixture-witness-recovery/v1", "status": "quarantined",
                    "intent_state": row["state"], "request_id": request_id,
                    "witness_pin": validate_pin(diagnosis["pin"]),
                    "registry_sequence": diagnosis["registry_sequence"],
                    "registry_head_sha256": diagnosis["registry_head_sha256"], **FLAGS}
        return self._identity._with_fixture_job_authorization(token, case_id, "case:read", recover)
