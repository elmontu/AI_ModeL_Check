"""Four reversible local fixture faults and a durable, local-only alert route.

The worker is real and fixed. Only its trusted bootstrap input is withheld for
one bounded timeout; no caller supplies code. Other faults affect newly created
public fixture stores and ephemeral trust. No old source/evidence is changed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock
import uuid

from ..production_jobs import executor
from ..production_storage.backend import FixtureObjectStore, StorageError, _FIXTURE_BYTES
from ..production_registry.rehearsal import RegistryFixture
from ..production_identity.policy import IdentityUnavailable, PermissionDenied
from ..production_witness.rehearsal import WitnessFixture
from ..production_witness.store import WitnessUnavailable
from .contracts import FLAGS, digest
from .store import MonitorStore
from .service import FixtureMonitoringService
from .receiver import FixtureAlertReceiver
from .checkpoint import FileCheckpointSink

_LOCAL = "local_public_fixture"
_WORKER_INJECTION_LOCK = Lock()
REQUIRED_CHECKS = frozenset({"worker_timeout_is_owned_and_outputless", "fresh_worker_recovers_without_reusing_attempt",
    "current_key_outage_denies_access", "restored_key_trust_requires_current_checks",
    "public_object_corruption_returns_no_bytes", "exact_in_place_public_object_repair_recovers",
    "witness_outage_retains_committed_uncertainty", "witness_recovery_keeps_original_receipt_and_charge",
    "each_fault_has_one_durable_redacted_incident", "healthy_events_do_not_auto_resolve",
    "only_current_human_acknowledgment_resolves", "local_alert_route_is_durable_and_idempotent",
    "restart_retains_incidents_and_receiver_dedup", "all_results_remain_non_authorizing"})


class RehearsalError(RuntimeError):
    pass


def _require(condition):
    if not condition:
        raise RehearsalError("Local monitoring fixture milestone failed")


def _worker(root, fault, healthy):
    runner = executor.FixtureProcessRunner(root)
    job, attempt = uuid.uuid4().hex, uuid.uuid4().hex
    # This scoped, serial harness interruption leaves the real fixed child
    # waiting at its pre-existing gate AFTER OS process ownership is assigned.
    # The runner retains the pipe and kills its owned child at its normal limit.
    with _WORKER_INJECTION_LOCK:
        original = executor._write_request
        def withhold(stream, content, done):
            done.set()
        executor._write_request = withhold
        try:
            failed = runner.run(job_id=job, attempt_id=attempt, fixture_bytes=_FIXTURE_BYTES, timeout_seconds=1)
        finally:
            executor._write_request = original
    _require(failed.status == "timed_out" and failed.cleanup_confirmed and failed.output is None
             and failed.exit_code is not None and failed.worker_sha256 == executor.worker_sha256())
    fault("worker_unavailable")
    try:
        runner.run(job_id=job, attempt_id=attempt, fixture_bytes=_FIXTURE_BYTES, timeout_seconds=1)
    except ValueError:
        pass
    else:
        raise RehearsalError("Failed attempt was silently reused")
    fresh = runner.run(job_id=job, attempt_id=uuid.uuid4().hex, fixture_bytes=_FIXTURE_BYTES, timeout_seconds=1)
    _require(fresh.status == "completed" and fresh.cleanup_confirmed and fresh.output["total"] == 19)
    healthy("worker_unavailable")
    return {"failed_status": failed.status, "cleanup_confirmed": True, "same_attempt_rejected": True,
            "recovery_total": 19, "worker_sha256": fresh.worker_sha256}


def _key(root, fault, healthy):
    fixture = RegistryFixture(root)
    token = fixture.token("auditor")
    baseline = fixture.service.state(token, "case-a")
    revision = fixture.trust.revision
    fixture.trust.set_available(False, expected_revision=revision)
    try:
        try:
            fixture.service.state(token, "case-a")
        except IdentityUnavailable:
            fault("key_unavailable")
        else:
            raise RehearsalError("Unavailable current trust was accepted")
    finally:
        fixture.trust.set_available(True, expected_revision=fixture.trust.revision)
    restored = fixture.service.state(fixture.token("auditor"), "case-a")
    _require(restored == baseline and fixture.trust.revision == revision + 2)
    healthy("key_unavailable")
    return {"current_verification_denied": True, "fresh_verification_recovered": True,
            "revision_advanced_by": 2, "revoked_keys_restored": False}


def _data(root, fault, healthy):
    backend = FixtureObjectStore(root)
    reference = backend.register_fixture(case_id="case-a", agency_id="agency", project_id="project",
        fixture_id="public-counts-v1", created_at=1000, retention_until=1240)
    original = backend.read(reference)
    path = root / (reference.object_id + "." + reference.version_id + ".json")
    before = path.stat()
    altered = original.replace(b'"count":12', b'"count":13', 1)
    _require(altered != original and len(altered) == len(original))
    path.write_bytes(altered)
    try:
        try:
            backend.read(reference)
        except StorageError:
            fault("data_unavailable")
        else:
            raise RehearsalError("Corrupt object returned bytes")
    finally:
        # Repair only this newly generated public fixture, preserving its inode.
        path.write_bytes(original)
    after = path.stat()
    _require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
             and backend.read(reference) == original)
    healthy("data_unavailable")
    return {"corrupt_read_denied": True, "original_identity_preserved": True,
            "restored_sha256": hashlib.sha256(original).hexdigest(), "arbitrary_ingestion_enabled": False}


def _ledger(root, fault, healthy):
    fixture = WitnessFixture(root)
    request = fixture.request()
    observe = fixture.witness.observe
    calls = 0
    def interrupt(history, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise WitnessUnavailable("Local fixture witness interruption")
        return observe(history, **kwargs)
    fixture.witness.observe = interrupt
    try:
        try:
            fixture.commit(request)
        except WitnessUnavailable:
            pass
        else:
            raise RehearsalError("Expected post-commit interruption was absent")
    finally:
        fixture.witness.observe = observe
    pending = fixture.witness.status(expected_pin=fixture.service.required_pin, guard=fixture.registry.clock)
    prior = fixture.registry.service.read(fixture.registry.token("auditor"), "case-a", request["request_id"])
    state = fixture.registry.service.state(fixture.registry.token("auditor"), "case-a")
    _require(pending["pending_intents"] == 1 and prior is not None
             and state["account"]["total_engineering_charge_units"] == 1)
    fault("ledger_inconsistent")
    recovered = fixture.recover(request)
    repeated = fixture.commit(request)
    final = fixture.registry.service.state(fixture.registry.token("auditor"), "case-a")
    _require(recovered["status"] == "witnessed_metadata" and recovered["receipt"] == prior
             and repeated["receipt"] == prior and final["account"]["total_engineering_charge_units"] == 1)
    healthy("ledger_inconsistent")
    return {"pending_intent_retained": True, "same_receipt_recovered": True,
            "engineering_charge_units": 1, "receipt_sha256": prior["receipt_sha256"],
            "privacy_accounting_claimed": False}


def exercise(output, *, profile="agency_private_cloud"):
    if profile != _LOCAL:
        raise RehearsalError("Production monitoring qualification unavailable")
    output = Path(output)
    output.mkdir(exist_ok=False)
    identity_fixture = RegistryFixture(output / "authority")
    clock = identity_fixture.clock
    store = MonitorStore.create(output / "monitor", profile=_LOCAL)
    sink = FileCheckpointSink(output / "checkpoints", store.initial_pin)
    service = FixtureMonitoringService(identity_fixture.identity, store, expected_pin=store.initial_pin,
        checkpoint_sink=sink, profile=_LOCAL)
    receiver = FixtureAlertReceiver.create(output / "receiver", profile=_LOCAL)
    token = lambda: identity_fixture.token("auditor")
    resources, incidents, checks = {}, {}, []
    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        _require(condition)
    def event(code, condition):
        resource = resources.setdefault(code, uuid.uuid4().hex)
        return {"schema": "mra-fixture-monitor-event/v1", "event_id": uuid.uuid4().hex,
                "resource_id": resource, "observed_at": clock(), "code": code, "condition": condition, **FLAGS}
    def fault(code):
        value = event(code, "fault")
        service.observe(value)
        pin = service.pin
        service.observe(value)  # Exact observation retry must not create another alert.
        _require(service.pin == pin)
        incidents[code] = value["event_id"]
    def healthy(code):
        service.observe(event(code, "healthy"))
        snapshot = service.snapshot(token(), "case-a")
        _require(next(row for row in snapshot["incidents"] if row["id"] == incidents[code])["status"] == "open")
    evidence = {}
    evidence["worker"] = _worker(output / "worker", fault, healthy)
    check("worker_timeout_is_owned_and_outputless", True)
    check("fresh_worker_recovers_without_reusing_attempt", True)
    evidence["key"] = _key(output / "key", fault, healthy)
    check("current_key_outage_denies_access", True)
    check("restored_key_trust_requires_current_checks", True)
    evidence["data"] = _data(output / "data", fault, healthy)
    check("public_object_corruption_returns_no_bytes", True)
    check("exact_in_place_public_object_repair_recovers", True)
    evidence["ledger"] = _ledger(output / "ledger", fault, healthy)
    check("witness_outage_retains_committed_uncertainty", True)
    check("witness_recovery_keeps_original_receipt_and_charge", True)
    snapshot = service.snapshot(token(), "case-a")
    check("each_fault_has_one_durable_redacted_incident", len(snapshot["events"]) == 8
          and len(snapshot["incidents"]) == 4 and len(snapshot["alerts"]) == 4)
    check("healthy_events_do_not_auto_resolve", all(row["status"] == "open" for row in snapshot["incidents"]))
    for incident in incidents.values():
        try:
            service.incident(identity_fixture.token("operator"), "case-a", uuid.uuid4().hex, incident, "acknowledge")
        except PermissionDenied:
            pass
        else:
            raise RehearsalError("A non-auditor managed an incident")
        service.incident(token(), "case-a", uuid.uuid4().hex, incident, "acknowledge")
        service.incident(token(), "case-a", uuid.uuid4().hex, incident, "resolve")
    snapshot = service.snapshot(token(), "case-a")
    check("only_current_human_acknowledgment_resolves", all(row["status"] == "resolved" for row in snapshot["incidents"]))
    pending = list(snapshot["alerts"])
    service.route_pending(token(), "case-a", receiver)
    receiver_pin = receiver.pin
    receiver.receive(pending[0], expected_pin=receiver_pin, guard=clock)
    service.route_pending(token(), "case-a", receiver)
    routed = service.snapshot(token(), "case-a")
    deliveries = receiver.snapshot(guard=clock)["deliveries"]
    check("local_alert_route_is_durable_and_idempotent", len(deliveries) == 4 and receiver.pin == receiver_pin
          and all(row["acknowledged"] for row in routed["alerts"]))
    reopened = MonitorStore.open(store.root, expected_pin=service.pin)
    reopened_sink = FileCheckpointSink.open(sink.root, expected_pin=service.pin)
    restarted = FixtureMonitoringService(identity_fixture.identity, reopened, expected_pin=service.pin,
        checkpoint_sink=reopened_sink, profile=_LOCAL)
    receiver = FixtureAlertReceiver.open(receiver.root, expected_pin=receiver_pin)
    restarted.route_pending(token(), "case-a", receiver)
    final = restarted.snapshot(token(), "case-a")
    check("restart_retains_incidents_and_receiver_dedup", final == routed and receiver.pin == receiver_pin
          and len(receiver.snapshot(guard=clock)["deliveries"]) == 4)
    check("all_results_remain_non_authorizing", all(final[key] is value for key, value in FLAGS.items()))
    _require({row["name"] for row in checks} == REQUIRED_CHECKS)
    return {"schema": "mra-fixture-monitor-rehearsal/v1", "status": "passed", "checks": checks,
        "summary": {"faults_observed": 4, "healthy_observations": 4, "resolved_incidents": 4,
                    "local_alert_deliveries": 4, "worker_timeout_seconds": 1,
                    "synthetic_authority_clock": True},
        "evidence": {"fault_checks": evidence, "monitor_pin": restarted.pin, "receiver_pin": receiver.pin,
                     "monitor_state_sha256": digest(final, max_bytes=8 * 1024 * 1024)}, **FLAGS}
