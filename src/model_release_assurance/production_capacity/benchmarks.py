"""Fixed public I/O and real signed-job observations, never agency capacity approval.

No caller selects data, code, workload sizes or credentials. Parent RSS is a
process-lifetime high-water mark, excludes children and is not a memory limit.
Concurrency means simultaneous runner calls, not a count of live child PIDs.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import sys
from threading import Lock
import time
import uuid

from ..production_registration.profiles import load_profile
from ..production_identity.policy import AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, PrincipalAuthority
from ..production_jobs.executor import ADAPTER_ID, FixtureProcessRunner, worker_sha256
from ..production_jobs.service import FixtureJobService
from ..production_jobs.store import JobStore
from ..production_storage.backend import FixtureObjectStore
from ..production_storage.service import FixtureStorageService
from ..production_trust.registry import FixtureTrustRegistry, TrustProfile
from ..production_trust.signer import FixtureTokenIssuer, MemoryFixtureSigningProvider
from ..production_trust.verification import RegistryAccessTokenVerifier
from . import contracts as c
from . import io

IO_SIZES = tuple(c.WORKLOAD_PLAN["io_target_bytes"])
CONCURRENCIES = tuple(c.WORKLOAD_PLAN["job_concurrency"])
JOBS_PER_ROW = c.WORKLOAD_PLAN["jobs_per_concurrency"]
CHUNK_BYTES = 64 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
_LOCAL = "local_public_fixture"
_CASE, _AGENCY, _PROJECT = "capacity-case", "capacity-agency", "capacity-project"
_ISSUER, _AUDIENCE = "https://capacity.example.invalid", "urn:mra:fixture:capacity"


def _require(condition):
    if not condition:
        raise c.CapacityError("Fixed capacity observation rejected")


def _elapsed(start):
    value = time.perf_counter_ns() - start
    _require(type(value) is int and value > 0)
    return value


def _rss():
    """Actual parent process high-water RSS, never aggregate child RSS."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes as w
        class Counters(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD)] + [(name, ctypes.c_size_t)
                for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                             "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        api = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = w.HANDLE
        api.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Counters), w.DWORD]
        api.GetProcessMemoryInfo.restype = w.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        _require(bool(api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)))
        value, method = int(counters.PeakWorkingSetSize), "GetProcessMemoryInfo.PeakWorkingSetSize"
    elif sys.platform.startswith("linux") or sys.platform == "darwin":
        import resource
        observed = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        value = int(observed) * (1 if sys.platform == "darwin" else 1024)
        method = "getrusage(RUSAGE_SELF).ru_maxrss"
    else:
        raise c.CapacityError("Parent high-water RSS observation unavailable")
    _require(type(value) is int and value > 0)
    return {"bytes": value, "method": method, "scope": "parent_process_lifetime_high_water",
            "includes_children": False, "enforced_memory_limit": False}


def _stamp(info):
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
             and not getattr(info, "st_file_attributes", 0) & 0x400)
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _piece(projection, position, count):
    offset = position % len(projection)
    repeats = (offset + count + len(projection) - 1) // len(projection)
    return (projection * repeats)[offset:offset + count]


def _scan_file(path, *, expected_bytes, projection, expected_sha256):
    _require(type(expected_bytes) is int and 1 <= expected_bytes <= MAX_FILE_BYTES)
    _require(type(projection) is bytes and 1 <= len(projection) <= CHUNK_BYTES)
    c.validate_digest(expected_sha256)
    parent = io.directory(path.parent)
    parent_id = (parent.stat().st_dev, parent.stat().st_ino)
    before = _stamp(path.lstat())
    _require(before[2] == expected_bytes)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    start = time.perf_counter_ns()
    digest, size, chunks = hashlib.sha256(), 0, 0
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = _stamp(os.fstat(stream.fileno()))
        _require(opened == before)
        while size < expected_bytes:
            block = stream.read(min(CHUNK_BYTES, expected_bytes - size))
            _require(bool(block) and block == _piece(projection, size, len(block)))
            digest.update(block)
            size += len(block)
            chunks += 1
        _require(stream.read(1) == b"")
        after = _stamp(os.fstat(stream.fileno()))
    io.directory(path.parent)
    _require(parent_id == (parent.stat().st_dev, parent.stat().st_ino)
             and before == after == _stamp(path.lstat()) and size == expected_bytes
             and digest.hexdigest() == expected_sha256)
    elapsed = _elapsed(start)
    return {"bytes_scanned": size, "chunks_scanned": chunks, "sha256": digest.hexdigest(),
            "scan_ns": elapsed, "scan_bytes_per_second": size * 1_000_000_000 // elapsed}


def _write_file(path, projection, count):
    _require(type(count) is int and count in IO_SIZES)
    _require(type(projection) is bytes and 1 <= len(projection) <= CHUNK_BYTES)
    parent = io.directory(path.parent)
    parent_id = (parent.stat().st_dev, parent.stat().st_ino)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    start = time.perf_counter_ns()
    digest, written = hashlib.sha256(), 0
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        opened = _stamp(os.fstat(stream.fileno()))
        while written < count:
            block = _piece(projection, written, min(CHUNK_BYTES, count - written))
            _require(stream.write(block) == len(block))
            digest.update(block)
            written += len(block)
        stream.flush()
        os.fsync(stream.fileno())
        after = _stamp(os.fstat(stream.fileno()))
    elapsed = _elapsed(start)
    io.directory(path.parent)
    final = _stamp(path.lstat())
    _require(parent_id == (parent.stat().st_dev, parent.stat().st_ino)
             and opened[:2] == after[:2] and after == final and final[2] == count)
    return {"bytes_written": written, "write_fsync_ns": elapsed,
            "write_bytes_per_second": written * 1_000_000_000 // elapsed, "sha256": digest.hexdigest()}


def benchmark_public_io(output, *, profile="agency_private_cloud"):
    c.require_local(profile)
    root = io.fresh_directory(output)
    data = load_profile("sklearn-wine", max_rows=4096)
    # Fixed owned little-endian float64 numeric projection; no model is fitted.
    projection = b"".join(data["x"][index].astype("<f8").tobytes()
                          + data["y"][index:index + 1].astype("<f8").tobytes()
                          for index in range(len(data["y"])))
    _require(data["x"].shape == (178, 13) and len(projection) == 178 * 14 * 8)
    rows = []
    for count in IO_SIZES:
        row = {"requested_bytes": count, "status": "failed"}
        try:
            path = root / (str(count) + ".bin")
            write = _write_file(path, projection, count)
            row.update(write)
            scan = _scan_file(path, expected_bytes=count, projection=projection, expected_sha256=write["sha256"])
            row.update(scan)
            row["parent_peak_rss"] = _rss()
            row["status"] = "passed"
        except Exception:
            row["failure_code"] = "bounded_io_observation_failed"
        rows.append(row)
    return {"schema": "mra-public-io-benchmark/v1", "status": "passed" if all(row["status"] == "passed" for row in rows) else "failed",
            "rows": rows, "summary": {"rows_requested": 3, "rows_passed": sum(row["status"] == "passed" for row in rows),
                "requested_bytes": sum(IO_SIZES), "source_profile": "sklearn-wine", "source_unique_rows": 178,
                "source_sha256": data["source_sha256"], "projection_sha256": hashlib.sha256(projection).hexdigest(),
                "projection_bytes": len(projection)},
            "measurement": {"clock": "perf_counter_ns", "stream_chunk_bytes": CHUNK_BYTES,
                "cache_state": "uncontrolled", "cold_cache_tested": False, "tiled_public_projection": True,
                "agency_scale_tested": False, "training_performed": False, "memory_scope": "parent_process_lifetime_excludes_children"},
            "target_status": "not_agency_qualified", **c.FLAGS}


class _MeasuredRunner:
    def __init__(self, root):
        self.runner = FixtureProcessRunner(root)
        self.lock, self.active, self.peak, self.samples = Lock(), 0, 0, []

    def run(self, **kwargs):
        start, result = time.perf_counter_ns(), None
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            result = self.runner.run(**kwargs)
            return result
        finally:
            sample = {"job_id": kwargs["job_id"], "attempt_id": kwargs["attempt_id"],
                      "elapsed_ns": _elapsed(start), "status": "unavailable", "cleanup_confirmed": False}
            if result is not None:
                try:
                    receipt = result.to_dict()
                    sample.update(status=receipt["status"], cleanup_confirmed=receipt["cleanup_confirmed"],
                        stdout_bytes=receipt["stdout_bytes"], stderr_bytes=receipt["stderr_bytes"],
                        worker_sha256=receipt["worker_sha256"], input_sha256=receipt["input_sha256"])
                except Exception:
                    sample["measurement_error"] = "runner_receipt_unavailable"
            with self.lock:
                self.active -= 1
                self.samples.append(sample)


class _Fixture:
    """Fresh authority with time advancing from 1000 using the real monotonic clock."""
    def __init__(self, root):
        self.origin = time.monotonic_ns()
        self.clock = lambda: 1000 + (time.monotonic_ns() - self.origin) // 1_000_000_000
        self.trust = FixtureTrustRegistry(now=self.clock, fresh_until=1200)
        profile = TrustProfile(_AGENCY, "public_fixture", _ISSUER, _AUDIENCE, "access_token")
        provider = MemoryFixtureSigningProvider()
        for key in ("human-key", "worker-key"):
            self.trust.enroll(provider.create_key(key_id=key, profile=profile, owner_id="fixture-idp",
                not_before=999, not_after=1300), expected_revision=self.trust.revision)
        self.issuer = FixtureTokenIssuer(self.trust, provider.bind(profile=profile, owner_id="fixture-idp"), profile, "fixture-idp")
        roles = {"operator": {"test_operator"}, "steward": {"data_steward"}, "worker": {"worker"}}
        principals = {(_ISSUER, subject): PrincipalAuthority(_ISSUER, subject, "person-" + subject,
            "workload" if subject == "worker" else "human", client_ids=frozenset({"client"})) for subject in roles}
        grants = tuple(CaseGrant("person-" + subject, _AGENCY, _PROJECT, _CASE, frozenset(role)) for subject, role in roles.items())
        state = AuthorityState(1, 1200, True, frozenset({"human-key", "worker-key"}), frozenset(), principals, grants)
        self.identity = FixtureIdentityService(RegistryAccessTokenVerifier(self.trust, profile), state,
            [CaseRecord(_CASE, _AGENCY, _PROJECT, "person-owner")], now=self.clock)
        self.storage = FixtureStorageService(self.identity, FixtureObjectStore(root / "objects"))
        self.store = JobStore.create(root / "store")
        self.runner = _MeasuredRunner(root / "worker")
        self.service = FixtureJobService(self.identity, self.storage, self.store, self.runner)
        self.reference = self.storage.register_fixture(self.token("steward"), _CASE, "public-counts-v1", 200)["reference"]

    def token(self, subject, *, job_id=None):
        scopes = ({"job:run", "case:read", "object:metadata"} if subject == "operator" else
                  {"case:read", "object:register", "object:grant", "object:metadata"} if subject == "steward" else
                  {"job:run", "object:read", "job:" + job_id})
        now = self.clock()
        claims = {"iss": _ISSUER, "aud": _AUDIENCE, "sub": subject, "client_id": "client", "jti": uuid.uuid4().hex,
                  "iat": now, "nbf": now, "exp": now + 120, "scope": " ".join(sorted(scopes)), "case_ids": [_CASE]}
        if subject != "worker":
            claims.update(acr="urn:mra:fixture:mfa", auth_time=now)
        return self.issuer.issue("worker-key" if subject == "worker" else "human-key", claims)

    def one(self, index):
        start = time.perf_counter_ns()
        record = {"ordinal": index, "status": "failed", "job_id": None, "grant_id": None, "attempt_id": None}
        try:
            job = self.service.submit(self.token("operator"), _CASE, ADAPTER_ID, self.reference, uuid.uuid4().hex)
            record["job_id"] = job["job_id"]
            worker = self.token("worker", job_id=job["job_id"])
            grant = self.service.authorize_input(self.token("steward"), _CASE, job["job_id"], worker, 60)
            record["grant_id"] = grant["grant_id"]
            result = self.service.run(worker, _CASE, job["job_id"], job["digest"])
            _require(result["state"] == "succeeded" and result["result_authorization_current"] is True
                     and result["result"]["total"] == 19 and len(result["attempts"]) == 1
                     and result["result"]["input_sha256"] == self.reference["sha256"]
                     and result["result"]["job_id"] == job["job_id"])
            record.update(status="succeeded", attempt_id=result["result"]["attempt_id"], total=19)
        except Exception:
            record["failure_code"] = "current_job_workflow_failed"
        record["elapsed_ns"] = _elapsed(start)
        return record


def _ledger(fixture):
    # Read only the newly created fixed job store; no supplied database path.
    fixture.store._paths()
    with closing(sqlite3.connect(fixture.store.path.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
        connection.execute("PRAGMA query_only=ON")
        states = {name: connection.execute("SELECT count(*) FROM " + name).fetchone()[0]
                  for name in ("jobs", "grants", "attempts")}
        states["succeeded"] = connection.execute("SELECT count(*) FROM jobs WHERE state='succeeded'").fetchone()[0]
        states["delivered_grants"] = connection.execute("SELECT count(*) FROM grants WHERE state='delivered'").fetchone()[0]
        states["input_consumed"] = connection.execute("SELECT count(*) FROM events WHERE event='input_consumed'").fetchone()[0]
        states["input_delivered"] = connection.execute("SELECT count(*) FROM events WHERE event='input_delivered'").fetchone()[0]
    fixture.store._paths()
    return states


def _job_row(root, concurrency):
    _require(type(concurrency) is int and concurrency in CONCURRENCIES)
    io.fresh_directory(root)
    fixture = _Fixture(root)
    start = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        outcomes = list(pool.map(fixture.one, range(JOBS_PER_ROW)))
    elapsed = _elapsed(start)
    samples = sorted(fixture.runner.samples, key=lambda item: item["job_id"])
    ledger, measurement_error = None, None
    try:
        ledger = _ledger(fixture)
    except Exception:
        measurement_error = "ledger_observation_unavailable"
    success = sum(item["status"] == "succeeded" for item in outcomes)
    valid = (success == JOBS_PER_ROW and len(samples) == JOBS_PER_ROW and fixture.runner.active == 0
        and 1 <= fixture.runner.peak <= concurrency
        and all(row["status"] == "completed" and row["cleanup_confirmed"] is True
                and row["worker_sha256"] == worker_sha256() and row["input_sha256"] == fixture.reference["sha256"] for row in samples)
        and all(len({row[key] for row in outcomes}) == JOBS_PER_ROW and all(row[key] is not None for row in outcomes)
                for key in ("job_id", "grant_id", "attempt_id"))
        and ledger == {key: JOBS_PER_ROW for key in ("jobs", "grants", "attempts", "succeeded", "delivered_grants", "input_consumed", "input_delivered")})
    for outcome in outcomes:
        matching = [row for row in samples if row["job_id"] == outcome["job_id"] and row["attempt_id"] == outcome["attempt_id"]]
        valid = valid and len(matching) == 1
    memory = None
    try:
        memory = _rss()
    except Exception:
        valid = False
        measurement_error = measurement_error or "parent_memory_observation_unavailable"
    return {"requested_concurrency": concurrency, "jobs_requested": JOBS_PER_ROW,
        "jobs_submitted": ledger["jobs"] if ledger is not None else None,
        "known_job_submission_count": len({row["job_id"] for row in outcomes if row["job_id"] is not None}),
        "ledger_available": ledger is not None,
        "succeeded": success, "failed": JOBS_PER_ROW - success, "unobserved": 0, "status": "passed" if valid else "failed",
        "elapsed_ns": elapsed, "successful_jobs_per_second_milli": success * 1_000_000_000_000 // elapsed,
        "peak_concurrent_runner_calls": fixture.runner.peak, "active_runner_calls_after": fixture.runner.active,
        "latency_ns": c.percentiles([row["elapsed_ns"] for row in outcomes]),
        "samples": outcomes, "runner_samples": samples, "ledger": ledger, "parent_peak_rss": memory,
        "measurement_error": measurement_error}


def benchmark_fixture_jobs(output, *, profile="agency_private_cloud"):
    c.require_local(profile)
    root = io.fresh_directory(output)
    rows = []
    for concurrency in CONCURRENCIES:
        try:
            row = _job_row(root / ("concurrency-" + str(concurrency)), concurrency)
        except Exception:
            row = {"requested_concurrency": concurrency, "jobs_requested": JOBS_PER_ROW, "status": "failed",
                   "failure_code": "job_observation_unavailable", "succeeded": 0, "failed": 0, "unobserved": JOBS_PER_ROW,
                   "outcomes_complete": False}
        rows.append(row)
    outcomes = [sample for row in rows for sample in row.get("samples", [])]
    unique = len(outcomes) == 12 and all(
        len({sample[key] for sample in outcomes}) == 12 and all(sample[key] is not None for sample in outcomes)
        for key in ("job_id", "grant_id", "attempt_id"))
    return {"schema": "mra-fixture-job-concurrency-benchmark/v1",
        "status": "passed" if unique and all(row["status"] == "passed" for row in rows) else "failed", "rows": rows,
        "summary": {"jobs_requested": 12, "jobs_succeeded": sum(row["succeeded"] for row in rows),
                    "jobs_failed": sum(row["failed"] for row in rows), "jobs_unobserved": sum(row["unobserved"] for row in rows), "concurrency_rows": 3},
        "measurement": {"clock": "perf_counter_ns", "authority_clock": "1000_plus_real_monotonic_elapsed_seconds",
            "concurrency_scope": "simultaneous_runner_calls_including_launch_and_cleanup_not_live_child_count",
            "identities_unique_across_rows": unique, "memory_scope": "parent_process_lifetime_excludes_children", "timeout_seconds": 5,
            "lease_seconds": 30, "grant_seconds": 60, "token_seconds": 120,
            "latency_sample_scope": "four_jobs_per_row_including_current_authorization_and_storage",
            "small_sample_percentiles": True, "performance_slo_approved": False},
        "target_status": "not_agency_qualified", **c.FLAGS}
