"""Fixed local workload contracts; measurements cannot qualify agency targets."""
from __future__ import annotations
from types import MappingProxyType
import re
from ..production_witness import contracts as bounded

MAX_BYTES = 32 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
FLAGS = MappingProxyType({
    "local_public_fixture": True,
    "production_ready": False,
    "approved_agency_scale": False,
    "can_clear": False,
    "authorization_eligible": False,
    "current_authorization_recovered": False,
    "private_data_admitted": False,
    "cloud_failover_tested": False,
    "independent_custody_verified": False,
    "privacy_accounting_supported": False,
    "external_notifications_sent": False,
})
WORKLOAD_PLAN = MappingProxyType({
    "schema": "mra-fixture-capacity-plan/v1",
    "dataset": "bundled-public-wine",
    "data_interpretation": "tiled_public_bytes_for_io_only",
    "io_target_bytes": (1048576, 8388608, 33554432),
    "read_chunk_bytes": 65536,
    "job_concurrency": (1, 2, 4),
    "jobs_per_concurrency": 4,
    "job_recipe": "fixed_public_counts",
    "cache_state": "uncontrolled",
    "performance_target_status": "not_agency_qualified",
    "agency_peak_load": None,
    "agency_rto_seconds": None,
})


class CapacityError(ValueError):
    """A local capacity/restore operation cannot establish its required facts."""


CAPACITYError = CapacityError


def fail():
    raise CapacityError("Capacity fixture metadata rejected")


def integer(value, minimum=0, maximum=2**53-1):
    if type(value) is not int or not minimum <= value <= maximum:
        fail()
    return value


def hex_id(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        fail()
    return value


def validate_digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        fail()
    return value


def require_local(profile):
    if type(profile) is not str or profile != "local_public_fixture":
        raise CapacityError("Production capacity qualification unavailable")


def canonical_bytes(value, max_bytes=65536):
    try:
        integer(max_bytes, 1, MAX_BYTES)
        return bounded.canonical_bytes(value, max_bytes=max_bytes)
    except Exception:
        fail()


def strict_json(raw, max_bytes=65536):
    try:
        integer(max_bytes, 1, MAX_BYTES)
        return bounded.strict_json(raw, max_bytes=max_bytes)
    except Exception:
        fail()


def digest(value, max_bytes=65536):
    import hashlib
    return hashlib.sha256(canonical_bytes(value, max_bytes=max_bytes)).hexdigest()


def workload_plan():
    """Own mutable lists without accepting caller workload substitutions."""
    return {key: list(value) if type(value) is tuple else value for key,value in WORKLOAD_PLAN.items()}


def workload_plan_sha256():
    return digest(workload_plan())


def percentiles(samples):
    if type(samples) is not list or not 1 <= len(samples) <= 4096:
        fail()
    values=sorted(integer(value) for value in samples)
    def nearest_rank(percent):
        return values[(percent * len(values) + 99)//100 - 1]
    return {"sample_count":len(values), "min_ns":values[0], "p50_ns":nearest_rank(50),
            "p95_ns":nearest_rank(95), "max_ns":values[-1],
            "percentile_method":"nearest_rank", "population_inference":False}
