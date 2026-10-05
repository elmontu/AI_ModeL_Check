#!/usr/bin/env python3
"""Rehearse one signed public-fixture job and durable broker fencing locally.

No listener, cloud request, network operation, private input, model execution,
release or deletion is performed. Ephemeral signing keys and JWTs remain in
memory. Retained stores contain only fixed fictional data and local evidence.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("mra_jobs_rehearsal_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)

from model_release_assurance.production_identity.policy import AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, PermissionDenied, PrincipalAuthority
from model_release_assurance.production_jobs.contracts import JobUnavailable
from model_release_assurance.production_jobs.executor import ADAPTER_ID, FixtureProcessRunner, worker_sha256
from model_release_assurance.production_jobs.service import FixtureJobService
from model_release_assurance.production_jobs.store import JobStore
from model_release_assurance.production_storage.backend import FixtureObjectStore, StorageError
from model_release_assurance.production_storage.service import FixtureStorageService
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile
from model_release_assurance.production_trust.signer import FixtureTokenIssuer, MemoryFixtureSigningProvider
from model_release_assurance.production_trust.verification import RegistryAccessTokenVerifier

ISSUER = "https://fixture-jobs.example.invalid"
AUDIENCE = "urn:mra:public-fixture:jobs"
CASE, AGENCY, PROJECT = "fixture-case", "fixture-agency", "fixture-project"
FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False,
         "production_authorized": False, "deployable": False, "hostile_code_isolated": False,
         "network_isolated": False, "storage_authority_restart_durable": False}
SOURCE_GROUPS = ("production_jobs", "production_identity", "production_storage", "production_trust")
SOURCE_FILES = ("src/model_release_assurance/__init__.py", "scripts/rehearse_fixture_jobs.py",
                "scripts/verify_build_baseline.py", "pyproject.toml", "requirements.lock")
MAX_REPORT_BYTES = 128 * 1024
REQUIRED_CHECKS = frozenset({"registered_builtin_public_fixture", "same_request_is_idempotent",
    "signed_worker_scope_is_exact", "real_fixed_worker_completed", "all_results_remain_non_authorizing",
    "input_consumption_is_durable_before_success", "spent_storage_grant_cannot_be_replayed",
    "old_broker_is_fenced", "historical_success_is_retained_but_redacted",
    "fresh_storage_does_not_recreate_prior_authority", "restart_preserves_spent_grants_and_attempt_history",
    "source_unchanged"})
LIMITATIONS = [
    "This is one trusted local fictional-count workflow; no private-data admission, model release or production qualification is established.",
    "Process ownership and bounded I/O are not hostile-code, filesystem, network, CPU or memory isolation.",
    "The broker restart is constructed in the same local process with retained ephemeral trust/identity; it is not full authority recovery or distributed revocation.",
    "SQLite preserves local attempt/grant history; it does not provide rollback resistance, independent witness custody or production recovery.",
    "Source hashes and stability checks cover the listed local files, not interpreter/dependency provenance or protection against a malicious administrator.",
]


class RehearsalError(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def source_snapshot(root):
    """Reselect all involved package sources, including newly added modules."""
    root = Path(root).absolute()
    selected = set(SOURCE_FILES)
    for group in SOURCE_GROUPS:
        directory = _BASELINE._checked_path(root, "src/model_release_assurance/" + group)
        found = list(directory.rglob("*.py"))
        if not found:
            raise RehearsalError("Required source package is missing")
        selected.update(path.relative_to(root).as_posix() for path in found)
    if len(selected) > 256:
        raise RehearsalError("Source snapshot exceeds its file bound")
    files = []
    for name in sorted(selected):
        path = _BASELINE._checked_path(root, name)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise RehearsalError("Source snapshot file exceeds its bound")
        content = _BASELINE._read_file(root, name)
        if len(content) > 2 * 1024 * 1024:
            raise RehearsalError("Source snapshot file exceeds its bound")
        files.append({"path": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)})
    return {"scope": "job/identity/storage/trust Python packages, package initializer, rehearsal/helper and runtime declarations",
            "files": files, "sha256": _digest(files)}


def _check(report, name, condition, evidence=None):
    item = {"name": name, "passed": bool(condition)}
    if evidence is not None:
        item["evidence_sha256"] = _digest(evidence)
    report["checks"].append(item)
    if not condition:
        raise RehearsalError("A fixed local rehearsal milestone failed")


def _denied(action, exception):
    try:
        action()
    except exception:
        return True
    return False


def _ledger(store, job_id):
    """Read-only local inspection of the already-created fictional SQLite store."""
    uri = store.path.absolute().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        metadata = dict(connection.execute("SELECT key,value FROM meta LIMIT 17").fetchall())
        grants = [dict(row) for row in connection.execute(
            "SELECT id,state,fence,storage_grant_id FROM grants WHERE job_id=? ORDER BY id LIMIT 33", (job_id,))]
        events = [dict(row) for row in connection.execute(
            "SELECT seq,event,fence,at FROM events WHERE job_id=? ORDER BY seq LIMIT 33", (job_id,))]
        attempts = [dict(row) for row in connection.execute(
            "SELECT attempt_id,fence,state,reason FROM attempts WHERE job_id=? ORDER BY fence LIMIT 5", (job_id,))]
        row = connection.execute("SELECT state,result FROM jobs WHERE id=?", (job_id,)).fetchone()
    if len(metadata) > 16 or len(grants) > 32 or len(events) > 32 or len(attempts) > 4 or row is None:
        raise RehearsalError("Local ledger inspection exceeded its fixed bounds")
    return {"store_id": metadata["store_id"], "broker_id": metadata["broker_id"],
            "broker_history": json.loads(metadata["broker_history"]), "grants": grants,
            "events": events, "attempts": attempts, "state": row["state"],
            "historical_result": json.loads(row["result"]) if row["result"] is not None else None}


def exercise_workflow(output, report):
    clock = lambda: int(time.time())
    started = clock()
    profile = TrustProfile(agency_id=AGENCY, environment="public_fixture", issuer=ISSUER,
                           audience=AUDIENCE, purpose="access_token")
    registry = FixtureTrustRegistry(now=clock, fresh_until=started + 200)
    provider = MemoryFixtureSigningProvider()
    fingerprints = []
    for key_id in ("fixture-human-key", "fixture-worker-key"):
        record = provider.create_key(key_id=key_id, profile=profile, owner_id="fixture-idp",
                                     not_before=started - 1, not_after=started + 300)
        registry.enroll(record, expected_revision=registry.revision)
        fingerprints.append(record.fingerprint)
    issuer = FixtureTokenIssuer(registry, provider.bind(profile=profile, owner_id="fixture-idp"), profile, "fixture-idp")
    verifier = RegistryAccessTokenVerifier(registry, profile)
    roles = {"operator": {"test_operator"}, "steward": {"data_steward"}, "worker": {"worker"}}
    principals = {(ISSUER, subject): PrincipalAuthority(ISSUER, subject, "fixture-" + subject,
                    "workload" if subject == "worker" else "human", client_ids=frozenset({"fixture-client"}))
                  for subject in roles}
    grants = tuple(CaseGrant("fixture-" + subject, AGENCY, PROJECT, CASE, frozenset(values))
                   for subject, values in roles.items())
    authority = AuthorityState(1, started + 200, True, frozenset({"fixture-human-key", "fixture-worker-key"}),
                               frozenset(), principals, grants)
    identity = FixtureIdentityService(verifier, authority,
                [CaseRecord(CASE, AGENCY, PROJECT, "fixture-owner")], now=clock)
    storage = FixtureStorageService(identity, FixtureObjectStore(output / "objects"))
    store = JobStore.create(output / "jobs")
    service = FixtureJobService(identity, storage, store, FixtureProcessRunner(output / "worker"))

    def token(subject, scopes):
        now = clock()
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "client_id": "fixture-client",
                  "jti": uuid.uuid4().hex, "iat": now, "nbf": now, "exp": now + 120,
                  "scope": " ".join(sorted(scopes)), "case_ids": [CASE]}
        if subject != "worker":
            claims.update(acr="urn:mra:fixture:mfa", auth_time=now)
        return issuer.issue("fixture-worker-key" if subject == "worker" else "fixture-human-key", claims)

    operator = token("operator", {"case:read", "job:run", "object:metadata"})
    steward = token("steward", {"case:read", "object:register", "object:grant", "object:metadata"})
    registered = storage.register_fixture(steward, CASE, "public-counts-v1", 200)
    reference = registered["reference"]
    _check(report, "registered_builtin_public_fixture", registered["fixture_only"] is True
           and registered["authorization_eligible"] is False, registered)
    submitted = service.submit(operator, CASE, ADAPTER_ID, reference, "fixture-rehearsal")
    repeated = service.submit(operator, CASE, ADAPTER_ID, reference, "fixture-rehearsal")
    _check(report, "same_request_is_idempotent", repeated["job_id"] == submitted["job_id"]
           and repeated["digest"] == submitted["digest"], submitted)
    job_id = submitted["job_id"]
    worker = token("worker", {"job:run", "object:read", "job:" + job_id})
    worker_identity = verifier.verify(worker, now=clock())
    _check(report, "signed_worker_scope_is_exact", worker_identity.scopes == frozenset({"job:run", "object:read", "job:" + job_id})
           and worker_identity.case_ids == frozenset({CASE}))
    grant = service.authorize_input(steward, CASE, job_id, worker, 60)
    completed = service.run(worker, CASE, job_id, submitted["digest"])
    expected = {"schema": ADAPTER_ID, "input_sha256": reference["sha256"], "categories": 2,
                "total": 19, "job_id": job_id, "attempt_id": completed["attempts"][0]["attempt_id"]}
    _check(report, "real_fixed_worker_completed", completed["state"] == "succeeded"
           and completed["result"] == expected and completed["result_authorization_current"] is True
           and len(completed["attempts"]) == 1, completed)
    _check(report, "all_results_remain_non_authorizing", all(key in completed and completed[key] is value for key, value in FLAGS.items() if key != "deployable"))
    before = _ledger(store, job_id)
    events = [item["event"] for item in before["events"]]
    delivery_events = ("input_consumed", "input_read_started", "input_delivered", "succeeded")
    _check(report, "input_consumption_is_durable_before_success", len(before["grants"]) == 1
           and before["grants"][0]["id"] == grant["grant_id"] and before["grants"][0]["state"] == "delivered"
           and all(events.count(name) == 1 for name in delivery_events)
           and [events.index(name) for name in delivery_events] == sorted(events.index(name) for name in delivery_events), before)
    _check(report, "spent_storage_grant_cannot_be_replayed", _denied(
        lambda: storage.read(worker, CASE, reference, before["grants"][0]["storage_grant_id"]), PermissionDenied))
    reopened = JobStore.open(store.root, expected_store_id=store.store_id)
    empty_storage = FixtureStorageService(identity, FixtureObjectStore(output / "objects-after-restart"))
    restarted = FixtureJobService(identity, empty_storage, reopened, FixtureProcessRunner(output / "worker-after-restart"))
    _check(report, "old_broker_is_fenced", _denied(lambda: service.read_job(operator, CASE, job_id), JobUnavailable))
    historical = restarted.read_job(operator, CASE, job_id)
    _check(report, "historical_success_is_retained_but_redacted", historical["state"] == "succeeded"
           and historical["result"] is None and historical["result_authorization_current"] is False
           and historical["attempts"] == completed["attempts"]
           and historical["storage_authority_restart_durable"] is False, historical)
    _check(report, "fresh_storage_does_not_recreate_prior_authority", _denied(
        lambda: empty_storage.metadata(steward, CASE, reference), StorageError)
        and _denied(lambda: restarted.authorize_input(steward, CASE, job_id, worker, 60), PermissionDenied))
    after = _ledger(reopened, job_id)
    _check(report, "restart_preserves_spent_grants_and_attempt_history", after["store_id"] == before["store_id"]
           and after["broker_history"] == [service.instance_id, restarted.instance_id]
           and after["broker_id"] == restarted.instance_id and after["grants"] == before["grants"]
           and after["attempts"] == before["attempts"] and after["historical_result"] == expected, after)
    report["summary"] = {"job_state": "succeeded", "categories": 2, "total": 19,
                         "attempts": 1, "broker_history_entries": 2}
    report["evidence"] = {"worker_sha256": worker_sha256(), "object_reference_sha256": registered["reference_digest"],
                          "job_descriptor_sha256": submitted["digest"], "store_id": store.store_id,
                          "completed_result_sha256": _digest(expected), "ledger_before_sha256": _digest(before),
                          "ledger_after_sha256": _digest(after), "public_key_fingerprints_sha256": _digest(fingerprints)}


def run_rehearsal(*, root, output):
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-fixture-jobs-rehearsal/v1", "status": "failed", "checks": [], "errors": [],
              "summary": None, "evidence": {}, "source": None, "limitations": LIMITATIONS,
              "runtime": {"python": platform.python_version(), "implementation": sys.implementation.name,
                          "system": platform.system()}, **FLAGS}
    started = time.monotonic()
    baseline = None
    try:
        baseline = source_snapshot(root)
        report["source"] = baseline
        exercise_workflow(destination, report)
    except Exception as error:
        # Never retain exception text, traces, token claims or key representations.
        report["errors"].append({"stage": "fixture_workflow", "type": type(error).__name__})
    finally:
        if baseline is not None:
            try:
                stable = source_snapshot(root) == baseline
                _check(report, "source_unchanged", stable)
            except Exception as error:
                report["errors"].append({"stage": "source_stability", "type": type(error).__name__})
    report["elapsed_seconds"] = round(max(0.0, time.monotonic() - started), 6)
    if (not report["errors"] and len(report["checks"]) == len(REQUIRED_CHECKS)
            and {check["name"] for check in report["checks"]} == REQUIRED_CHECKS
            and all(check["passed"] for check in report["checks"])):
        report["status"] = "passed"
    if report["status"] != "passed" and not report["errors"]:
        report["errors"].append({"stage": "milestones", "type": "IncompleteWorkflow"})
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    if len(content) > MAX_REPORT_BYTES:
        report = {"schema": "mra-fixture-jobs-rehearsal/v1", "status": "failed", "checks": [],
                  "errors": [{"stage": "report", "type": "ReportBoundExceeded"}], **FLAGS}
        content = _canonical(report) + b"\n"
    with (destination / "result.json").open("xb") as stream:
        stream.write(content)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(root=ROOT, output=args.output)
    except (_BASELINE.BaselineError, OSError):
        print(json.dumps({"status": "output_refused", **FLAGS}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"], "passed_checks": sum(item["passed"] for item in result["checks"]),
                      "errors": result["errors"], **FLAGS}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
