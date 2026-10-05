"""Strict public-only job descriptors; no arbitrary data, commands or delivery."""
from __future__ import annotations
import hashlib
import json
import re
from ..production_storage.contracts import ObjectReference

ADAPTER_ID = "public-count-summary/v1"
FLAGS = {"fixture_only": True, "production_authorized": False, "model_delivery": False}
LEASE_FIELDS = {"job_id", "fence", "attempt_id", "holder", "authority_revision", "broker_id", "grant_id", "expires_at"}

class JobError(RuntimeError):
    """A local fixture job cannot perform the requested operation."""

class JobConflict(JobError):
    """Stale, exhausted, consumed or inconsistent job state."""

class JobUnavailable(JobError):
    """Job custody, current broker or trusted time is unavailable."""

def integer(value, minimum=0, maximum=2**53-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("A bounded integer is required")
    return value

def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError("A bounded identifier is required")
    return value

def hex_id(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("An exact fixture identifier is required")
    return value

def digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("An exact SHA256 is required")
    return value

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def validate_descriptor(value):
    fields = {"schema", "environment", "agency_id", "project_id", "case_id", "object_reference",
              "adapter_id", "worker_sha256", "max_attempts", "lease_seconds", "timeout_seconds"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("An exact public job descriptor is required")
    if value["schema"] != "mra-fixture-job/v1" or value["environment"] != "public_fixture" or value["adapter_id"] != ADAPTER_ID:
        raise ValueError("Only the fixed public job profile is supported")
    reference = ObjectReference.from_dict(value["object_reference"])
    for name in ("agency_id", "project_id", "case_id"):
        identifier(value[name])
        if getattr(reference, name) != value[name]:
            raise ValueError("Reference is outside the exact job scope")
    digest(value["worker_sha256"])
    integer(value["max_attempts"], 1, 3)
    integer(value["lease_seconds"], 1, 60)
    integer(value["timeout_seconds"], 1, min(30, value["lease_seconds"]))
    return {**value, "object_reference": reference.to_dict()}

def validate_lease(value):
    if type(value) is not dict or set(value) != LEASE_FIELDS:
        raise ValueError("An exact lease is required")
    for name in ("job_id", "attempt_id", "broker_id", "grant_id"):
        hex_id(value[name])
    digest(value["holder"])
    integer(value["fence"], 1, 3)
    integer(value["authority_revision"], 1)
    integer(value["expires_at"])
    return dict(value)

def validate_result(value, descriptor, lease):
    expected = {"schema": ADAPTER_ID, "job_id": lease["job_id"], "attempt_id": lease["attempt_id"],
                "input_sha256": descriptor["object_reference"]["sha256"], "categories": 2, "total": 19}
    if type(value) is not dict or set(value) != set(expected) or any(
            type(value[key]) is not type(expected[key]) or value[key] != expected[key] for key in expected):
        raise ValueError("Unexpected public worker result")
    return dict(value)
