"""Fresh bounded measurements and historical recovery without live permission.

Delivery is the native PRD18 fixture, not a claim of PRD19 SACRO qualification.
Service-component restart preserves current test identity solely to isolate the
loss of retained proof contexts; no proof dictionaries are copied or restored.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from time import perf_counter_ns
import uuid

from ..production_delivery.rehearsal import DeliveryFixture
from ..production_delivery.authorization import RecipientRecord
from ..production_delivery.review_bridge import DeliveryReviewBridge
from ..production_delivery.gateway import FixtureDeliveryGateway
from ..production_delivery.checkpoint import FileCheckpointSink
from ..production_delivery.store import DeliveryStore, StoreError
from ..production_delivery.contracts import DeliveryError
from ..production_review.service import FixtureReviewService
from ..production_review.store import ReviewStore
from ..production_identity.policy import PermissionDenied, IdentityUnavailable
from ..production_witness.rehearsal import WitnessFixture
from ..production_witness.store import WitnessUnavailable
from ..production_registry.receiver import FixtureEventReceiver
from . import contracts as c
from . import io
from . import benchmarks, backup

_LOCAL = "local_public_fixture"
REQUIRED_CHECKS = frozenset({
    "plan_frozen_before_measurement", "production_profile_refused_before_fit",
    "fresh_registered_native_review", "exact_chunk_and_partial_admission_retained",
    "restart_denials_are_current_and_nonvacuous", "gateway_restart_does_not_restore_old_grant_proofs",
    "review_bridge_restart_does_not_restore_live_authority", "restart_preserves_full_history_and_transfer_counters",
    "revocation_survives_external_checkpoint_restore", "pending_witness_cut_refused",
    "committed_receipt_recovered_without_new_charge", "local_outbox_custody_preserved",
    "witnessed_backup_verified_and_restored", "stale_pair_rejected_by_external_floors",
    "historical_restore_preserves_all_receipts_and_charges", "fixed_public_io_complete",
    "all_twelve_jobs_accounted", "measurements_are_not_agency_targets", "all_results_non_authorizing"})


def workload_plan():
    return {"schema": "mra-fixture-capacity-rehearsal-plan/v1", "capacity": c.workload_plan(),
        "delivery": {"profile_id": "sklearn-wine", "max_rows": 128, "seed": 20261001,
                     "activation_ttl_seconds": 30, "grant_ttl_seconds": 20,
                     "authority_clock": "synthetic_fixed_1000", "chunk_bytes": 128,
                     "partial_attempt_bytes": 128, "partial_observed_bytes": 1,
                     "scope": "PRD18_native_fixture_not_PRD19_SACRO_qualification"},
        "backup": {"committed_requests": 3, "engineering_charge_units": 3,
                   "privacy_accounting_supported": False, "live_authority_restore": False},
        "measurement_clock": "perf_counter_ns", "approved_agency_scale": False}


def _require(value):
    if value is not True:
        raise c.CapacityError("Required local capacity/recovery check failed")


def _deny(call, expected):
    try:
        call()
    except expected:
        return True
    return False


def _copy_database(source, directory, name):
    """Copy a newly generated quiescent fixture file; never replace live state."""
    target = io.fresh_directory(directory)
    io.exclusive_write(target / name, io.read_file(source, maxbytes=32 * 1024 * 1024))
    return target


def _recipients():
    return (RecipientRecord("fixture-recipient", "agency", "project", "case-a",
                            frozenset({"person-recipient"})),)


def _delivery(output):
    fixture = DeliveryFixture(output)
    checks = []
    def check(name, condition):
        _require(bool(condition)); checks.append({"name": name, "passed": True})
    denied = (PermissionDenied, IdentityUnavailable, StoreError, DeliveryError)
    check("production_profile_refused_before_fit", _deny(lambda: fixture.gateway.activate(
        fixture.token("releaser"), "case-a", uuid.uuid4().hex), denied)
        and not fixture.output.exists())
    campaign_id, _ = fixture.prepare()
    campaign = fixture.review.status(fixture.token("auditor"), "case-a", campaign_id)
    check("fresh_registered_native_review", campaign["reviews_usable"]
        and campaign["campaign"]["state"] == "completed" and fixture.activation_blocked_before_reviews)
    aid, activation = fixture.activate()
    recipient = fixture.token("recipient")
    gid, grant = fixture.grant(aid, recipient)
    transfer = grant["payload"]["transfer_id"]
    candidate = io.read_file(fixture.output / "native/candidate.json", maxbytes=2 * 1024 * 1024)
    delivered = []
    first = fixture.gateway.deliver_chunk(recipient, "case-a", aid, gid, transfer, 0, 128,
        writer=lambda raw: delivered.append(raw) or len(raw))
    partial_gid, partial_grant = fixture.grant(aid, recipient)
    partial = fixture.gateway.deliver_chunk(recipient, "case-a", aid, partial_gid,
        partial_grant["payload"]["transfer_id"], 0, 128, writer=lambda raw: 1)
    before = fixture.gateway.status(fixture.token("auditor"), "case-a")
    check("exact_chunk_and_partial_admission_retained", delivered == [candidate[:128]]
        and first["bytes_written"] == 128 and partial["status"] == "interrupted"
        and partial["bytes_written"] == 1 and before["grants"][partial_gid]["attempted_bytes"] == 128
        and first["admission"]["request_id"] in before["admissions"]
        and partial["admission"]["request_id"] in before["admissions"]
        and hashlib.sha256(candidate).hexdigest() == activation["payload"]["artifact_sha256"])
    pin = fixture.gateway.required_pin
    active_copy = _copy_database(fixture.store.root / "delivery.sqlite", fixture.root / "gateway-restart", "delivery.sqlite")
    review_copy = _copy_database(fixture.review_fixture.store.root / "reviews.sqlite", fixture.root / "review-restart", "reviews.sqlite")
    independent_copy = _copy_database(fixture.store.root / "delivery.sqlite", fixture.root / "review-delivery-restart", "delivery.sqlite")
    current_checks = []
    def current():
        valid = fixture.review.status(fixture.token("auditor"), "case-a", campaign_id)["reviews_usable"]
        valid = valid and fixture.now < activation["payload"]["expires_at"] and fixture.now < grant["payload"]["expires_at"]
        _require(valid); current_checks.append(valid)
    writes = []
    def writer(raw):
        writes.append(len(raw)); return len(raw)
    start = perf_counter_ns()
    gateway = FixtureDeliveryGateway(fixture.bridge, DeliveryStore.open(active_copy, expected_pin=pin),
        _recipients(), expected_pin=pin, checkpoint_sink=FileCheckpointSink(fixture.root / "gateway-restart-pins", pin))
    current()
    reopened_state = gateway.status(fixture.token("auditor"), "case-a")
    _require(reopened_state == before)
    check("gateway_restart_does_not_restore_old_grant_proofs",
        _deny(lambda: gateway.grant(fixture.token("releaser"), "case-a", aid, recipient), denied)
        and _deny(lambda: gateway.deliver_chunk(recipient, "case-a", aid, gid, transfer, 128, 128, writer=writer), denied)
        and not writes)
    gateway_reopen_ns = perf_counter_ns() - start
    restarted_review = FixtureReviewService(fixture.identity,
        ReviewStore.open(review_copy, fixture.review_fixture.store.store_id), fixture.review_fixture.workflow)
    start = perf_counter_ns()
    restarted_gateway = FixtureDeliveryGateway(DeliveryReviewBridge(restarted_review),
        DeliveryStore.open(independent_copy, expected_pin=pin), _recipients(), expected_pin=pin,
        checkpoint_sink=FileCheckpointSink(fixture.root / "review-restart-pins", pin))
    current()
    historical = restarted_review.status(fixture.token("auditor"), "case-a", campaign_id)
    _require(historical["campaign"] == campaign["campaign"] and not historical["reviews_usable"])
    check("review_bridge_restart_does_not_restore_live_authority",
        _deny(lambda: restarted_gateway.activate(fixture.token("releaser"), "case-a", campaign_id, profile=_LOCAL), denied)
        and _deny(lambda: restarted_gateway.grant(fixture.token("releaser"), "case-a", aid, recipient), denied)
        and _deny(lambda: restarted_gateway.deliver_chunk(recipient, "case-a", aid, gid, transfer, 128, 128, writer=writer), denied)
        and not writes)
    historical_reopen_ns = perf_counter_ns() - start
    check("restart_preserves_full_history_and_transfer_counters",
        gateway.status(fixture.token("auditor"), "case-a") == before
        and restarted_gateway.status(fixture.token("auditor"), "case-a") == before)
    # A suspended copy makes the resume refusal non-vacuous: the original live
    # facade can resume this exact activation with its original proof contexts.
    suspended = fixture.gateway.suspend(fixture.token("releaser"), "case-a", aid)
    suspended_pin = fixture.gateway.required_pin
    suspended_copy = _copy_database(fixture.store.root / "delivery.sqlite", fixture.root / "suspended-restart", "delivery.sqlite")
    suspended_gateway = FixtureDeliveryGateway(fixture.bridge, DeliveryStore.open(suspended_copy, expected_pin=suspended_pin),
        _recipients(), expected_pin=suspended_pin,
        checkpoint_sink=FileCheckpointSink(fixture.root / "suspended-restart-pins", suspended_pin))
    current()
    _require(_deny(lambda: suspended_gateway.resume(fixture.token("releaser"), "case-a", aid), denied))
    _require(suspended_gateway.status(fixture.token("auditor"), "case-a") == suspended)
    fixture.gateway.resume(fixture.token("releaser"), "case-a", aid)
    current()
    control = fixture.gateway.deliver_chunk(recipient, "case-a", aid, gid, transfer, 128, 128,
                                           writer=lambda raw: len(raw))
    check("restart_denials_are_current_and_nonvacuous", len(current_checks) == 4
          and all(current_checks) and control["bytes_written"] == 128 and not writes)
    stale_copy = _copy_database(fixture.store.root / "delivery.sqlite", fixture.root / "before-revoke-copy", "delivery.sqlite")
    fixture.gateway.revoke(fixture.token("releaser"), "case-a", aid)
    later_pin = fixture.gateway.required_pin
    check("revocation_survives_external_checkpoint_restore",
        fixture.checkpoint_sink.read() == later_pin
        and _deny(lambda: DeliveryStore.open(stale_copy, expected_pin=later_pin), denied)
        and _deny(lambda: fixture.gateway.resume(fixture.token("releaser"), "case-a", aid), denied))
    return {"checks": checks, "summary": {"profile_id": "sklearn-wine", "fresh_native_runs": 1,
        "artifact_size": len(candidate), "initial_admissions": 2, "initial_attempted_bytes": 256,
        "partial_attempted_bytes": 128, "partial_observed_bytes": 1, "denied_writer_calls": len(writes),
        "nonvacuous_current_checks": len(current_checks), "authority_clock": "synthetic_fixed_1000",
        "recipient_receipt_verified": False, "live_authority_rehydrated": False},
        "measurement": {"gateway_component_reopen_and_denial_ns": gateway_reopen_ns,
            "historical_review_bridge_reopen_and_denial_ns": historical_reopen_ns,
            "measurement_clock": "perf_counter_ns", "scope": "local_component_drill_not_agency_RTO"},
        "evidence": {"original_delivery_pin": pin, "post_revoke_pin": later_pin,
            "history_sha256_before": c.digest(before, max_bytes=c.MAX_BYTES),
            "history_sha256_reopened": c.digest(reopened_state, max_bytes=c.MAX_BYTES),
            "candidate_sha256": hashlib.sha256(candidate).hexdigest()}}


def _backup(output):
    fixture = WitnessFixture(output)
    registry = fixture.registry
    checks = []
    def check(name, condition):
        _require(bool(condition)); checks.append({"name": name, "passed": True})
    receiver = FixtureEventReceiver.create(fixture.root / "receiver")
    requests, receipts = [], []
    def commit(case):
        request = fixture.request(case)
        result = fixture.commit(request)
        requests.append(request); receipts.append(result["receipt"])
        return request
    def drain():
        for case in ("case-a", "case-b"):
            worker = registry.token("worker")
            for _ in range(4):
                item = registry.service.claim_outbox(worker, case, 5)
                if item is None:
                    break
                receiver.receive(item["event"], guard=registry.clock)
                registry.service.acknowledge(worker, case, item["lease"])
            else:
                raise c.CapacityError("Bounded outbox drain incomplete")
        return fixture.recover(requests[0])
    def pins():
        return {"expected_registry_anchor": backup.registry_anchor(registry.store, guard=registry.clock),
                "expected_witness_pin": fixture.service.required_pin}
    def capture(name):
        with registry.identity._lock:
            expected = pins()
            report = backup.capture_quiesced(registry.store, fixture.witness, fixture.root / name,
                **expected, guard=registry.clock, profile=_LOCAL)
        return report, {**expected, "expected_manifest_sha256": report["manifest_sha256"]}
    commit("case-a"); commit("case-b"); drain()
    old, old_pins = capture("old-valid-pair")
    third = fixture.request("case-a")
    observer = fixture.witness.observe
    calls = [0]
    def interrupt(history, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise WitnessUnavailable("Fixed local witness interruption")
        return observer(history, **kwargs)
    fixture.witness.observe = interrupt
    try:
        failed = _deny(lambda: fixture.commit(third), (WitnessUnavailable,))
    finally:
        fixture.witness.observe = observer
    requests.append(third)
    third_receipt = registry.service.read(registry.token("auditor"), "case-a", third["request_id"])
    _require(failed and calls[0] == 2)
    with registry.identity._lock:
        pending_pins = pins()
        rejected = _deny(lambda: backup.capture_quiesced(registry.store, fixture.witness,
            fixture.root / "pending-cut", **pending_pins, guard=registry.clock, profile=_LOCAL), (c.CapacityError,))
    check("pending_witness_cut_refused", rejected)
    recovered = fixture.recover(third)
    receipts.append(third_receipt)
    check("committed_receipt_recovered_without_new_charge", recovered["receipt"] == third_receipt
          and registry.service.state(registry.token("auditor"), "case-a")["account"]["total_engineering_charge_units"] == 3)
    drain()
    retained = receiver.snapshot(guard=registry.clock)
    check("local_outbox_custody_preserved", retained["applied_events"] == 3)
    captured, expected = capture("complete-backup")
    verified = backup.verify_backup(fixture.root / "complete-backup", **expected)
    restored = backup.restore_backup(fixture.root / "complete-backup", fixture.root / "restored-historical",
                                      **expected, profile=_LOCAL)
    check("witnessed_backup_verified_and_restored", verified["status"] == "historical_backup_verified"
          and restored["status"] == "historical_restore_verified")
    # The old pair is internally valid with its own receipt, but must not be
    # accepted under the newer independently supplied registry/witness floors.
    check("stale_pair_rejected_by_external_floors", old["status"] == "historical_backup_verified"
          and _deny(lambda: backup.verify_backup(fixture.root / "old-valid-pair",
              expected_manifest_sha256=old_pins["expected_manifest_sha256"],
              expected_registry_anchor=expected["expected_registry_anchor"],
              expected_witness_pin=expected["expected_witness_pin"]), (c.CapacityError,)))
    evidence = captured["evidence"]
    check("historical_restore_preserves_all_receipts_and_charges",
        evidence == verified["evidence"] == restored["evidence"]
        and evidence["engineering_charge_units"] == evidence["receipt_count"] == evidence["outbox_count"] == 3
        and evidence["outbox_acknowledged"] == 3 and evidence["outbox_pending"] == 0
        and evidence["committed_intents"] == 3 and evidence["pending_intents"] == 0
        and all(registry.service.read(registry.token("auditor"), request["case_id"], request["request_id"]) == receipt
                for request, receipt in zip(requests, receipts)))
    return {"checks": checks, "summary": {"committed_requests": 3, "engineering_charge_units": 3,
        "local_receiver_effects": 3, "pending_cut_refused": True, "stale_pair_refused": True,
        "live_registry_service_restored": False, "privacy_accounting_supported": False},
        "measurement": {"capture_elapsed_ns": captured["capture_elapsed_ns"],
            "restore_elapsed_ns": restored["restore_elapsed_ns"], "scope": "historical_local_restore_not_agency_RTO"},
        "evidence": {"manifest_sha256": captured["manifest_sha256"], **expected, "conservation": evidence}}


def exercise(output, *, profile="agency_private_cloud"):
    c.require_local(profile)
    root = io.fresh_directory(output)
    plan = workload_plan()
    io.exclusive_write(root / "workload-plan.json", c.canonical_bytes(plan) + b"\n")
    report = {"schema": "mra-fixture-capacity-recovery-exercise/v1", "status": "failed",
        "checks": [{"name": "plan_frozen_before_measurement", "passed": True}],
        "workload_plan_sha256": c.digest(plan), "summary": {}, "evidence": {},
        "measurements": {}, "errors": [], "target_status": "not_agency_qualified", **c.FLAGS}
    stages = (("delivery", _delivery, root / "delivery"), ("backup", _backup, root / "backup"),
              ("io", lambda path: benchmarks.benchmark_public_io(path, profile=_LOCAL), root / "io"),
              ("jobs", lambda path: benchmarks.benchmark_fixture_jobs(path, profile=_LOCAL), root / "jobs"))
    for name, action, path in stages:
        try:
            result = action(path)
            if name in {"delivery", "backup"}:
                report["checks"].extend(result["checks"])
                report["summary"][name] = result["summary"]
                report["evidence"][name] = result["evidence"]
                report["measurements"][name] = result["measurement"]
            else:
                report["measurements"][name] = result
                _require(type(result) is dict and result.get("status") == "passed"
                    and result.get("target_status") == "not_agency_qualified"
                    and all(result.get(key) is value for key, value in c.FLAGS.items()))
                if name == "io":
                    _require([row["requested_bytes"] for row in result["rows"]] == c.workload_plan()["io_target_bytes"]
                        and all(row["status"] == "passed" and row["bytes_written"] == row["bytes_scanned"] == row["requested_bytes"] for row in result["rows"])
                        and result["summary"]["rows_requested"] == result["summary"]["rows_passed"] == 3
                        and result["summary"]["requested_bytes"] == 42991616)
                    report["checks"].append({"name": "fixed_public_io_complete", "passed": True})
                else:
                    rows = result["rows"]
                    _require([row["requested_concurrency"] for row in rows] == [1, 2, 4]
                        and all(row["status"] == "passed" and row["jobs_submitted"] == row["succeeded"] == 4
                                and row["failed"] == row["unobserved"] == 0 for row in rows)
                        and result["summary"] == {"jobs_requested": 12, "jobs_succeeded": 12,
                            "jobs_failed": 0, "jobs_unobserved": 0, "concurrency_rows": 3}
                        and result["measurement"]["identities_unique_across_rows"] is True)
                    report["checks"].append({"name": "all_twelve_jobs_accounted", "passed": True})
        except Exception:
            report["errors"].append({"stage": name, "type": "LocalFixtureStageFailed"})
    if io.read_file(root / "workload-plan.json") != c.canonical_bytes(plan) + b"\n":
        report["errors"].append({"stage": "plan", "type": "FrozenPlanChanged"})
    report["checks"].extend(({"name": "measurements_are_not_agency_targets", "passed": True},
                              {"name": "all_results_non_authorizing", "passed": True}))
    if (not report["errors"] and len(report["checks"]) == len(REQUIRED_CHECKS)
            and {item["name"] for item in report["checks"]} == REQUIRED_CHECKS
            and all(item["passed"] is True for item in report["checks"])):
        report["status"] = "passed"
    io.exclusive_write(root / "exercise-result.json", c.canonical_bytes(report, max_bytes=c.MAX_BYTES) + b"\n")
    return report
