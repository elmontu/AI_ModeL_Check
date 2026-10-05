"""Strict metadata only. Sensitive values are omitted, never hashed for redaction."""
from __future__ import annotations

from types import MappingProxyType
import re

from ..production_witness import contracts as bounded

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 2048
GENESIS_SHA256 = "0" * 64
FLAGS = MappingProxyType({
    "local_public_fixture": True,
    "production_ready": False,
    "can_clear": False,
    "authorization_eligible": False,
    "private_data_admitted": False,
    "independent_custody_verified": False,
    "external_notifications_sent": False,
})
RULES = MappingProxyType({
    "worker_unavailable": MappingProxyType({"route": "sre", "severity": "high", "runbook": "RB-WORKER"}),
    "key_unavailable": MappingProxyType({"route": "security", "severity": "critical", "runbook": "RB-KEY"}),
    "data_unavailable": MappingProxyType({"route": "security", "severity": "critical", "runbook": "RB-DATA"}),
    "ledger_inconsistent": MappingProxyType({"route": "security", "severity": "critical", "runbook": "RB-LEDGER"}),
})


class MonitoringContractError(ValueError):
    pass


def fail():
    raise MonitoringContractError("Monitoring metadata rejected")


def integer(value, minimum=0, maximum=2**53 - 1):
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


def owned(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        fail()
    return strict_json(canonical_bytes(value))


def _flags(value):
    for key, expected in FLAGS.items():
        if type(value[key]) is not bool or value[key] is not expected:
            fail()


def validate_event(value):
    value = owned(value, {"schema", "event_id", "resource_id", "observed_at", "code", "condition", *FLAGS})
    if value["schema"] != "mra-fixture-monitor-event/v1":
        fail()
    hex_id(value["event_id"]); hex_id(value["resource_id"]); integer(value["observed_at"])
    if (type(value["code"]) is not str or type(value["condition"]) is not str
            or value["code"] not in RULES or value["condition"] not in {"fault", "healthy"}):
        fail()
    _flags(value)
    return value


def validate_pin(value):
    value = owned(value, {"schema", "store_id", "sequence", "head_sha256"})
    if value["schema"] != "mra-fixture-monitor-pin/v1":
        fail()
    hex_id(value["store_id"]); integer(value["sequence"], 0, MAX_RECORDS)
    validate_digest(value["head_sha256"])
    if value["sequence"] == 0 and value["head_sha256"] != GENESIS_SHA256:
        fail()
    if value["sequence"] > 0 and value["head_sha256"] == GENESIS_SHA256:
        fail()
    return value


def validate_actor(value):
    value = owned(value, {"kind", "authority_revision"})
    if value["kind"] != "human":
        fail()
    integer(value["authority_revision"], 1)
    return value


def validate_alert(value):
    value = owned(value, {"alert_id", "incident_id", "event", "route", "severity", "runbook",
                          "acknowledged", "receiver_pin"})
    event = validate_event(value["event"])
    if event["condition"] != "fault" or value["alert_id"] != event["event_id"]:
        fail()
    hex_id(value["incident_id"])
    rule = RULES[event["code"]]
    if any(value[key] != rule[key] for key in rule):
        fail()
    if type(value["acknowledged"]) is not bool:
        fail()
    if value["acknowledged"]:
        validate_pin(value["receiver_pin"])
    elif value["receiver_pin"] is not None:
        fail()
    return value
