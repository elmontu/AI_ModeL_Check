"""Exact bounded data contracts for local worker-evidence fixtures.

These records bind claims and retained artifact bytes. They do not establish
worker honesty, process isolation, remote attestation or production authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

MAX_JSON_BYTES = 65536
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_INTEGER = 2**53 - 1
NATIVE_ARTIFACT_NAMES = (
    "dataset.json", "plan.json", "candidate.json", "report.json", "scores.json",
    "predictions.json", "replay.json", "result.json",
)
OBSERVATIONS = {
    "schema": "mra-local-observation/v1",
    "image_verified": False,
    "hostile_code_isolated": False,
    "network_isolated": False,
    "filesystem_isolated": False,
    "resource_limits_verified": False,
}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[0-9a-f]{32}\Z")
_CONTEXT_FIELDS = frozenset({
    "schema", "environment", "operation", "agency_id", "project_id", "case_id", "worker_id",
    "job_id", "attempt_id", "fence", "job_sha256", "source_sha256", "policy_sha256",
    "plan_sha256", "adapter_sha256", "runtime_sha256", "image_sha256",
})
_CHALLENGE_FIELDS = frozenset({
    "schema", "ledger_id", "nonce", "context_sha256", "execution_sha256", "issued_at", "expires_at",
})


class EvidenceError(ValueError):
    """Generic payload-free validation or fixture trust failure."""


def _reject():
    raise EvidenceError("Worker evidence rejected")


def _tree(value, depth=0, budget=None):
    if budget is None:
        budget = [16384]
    budget[0] -= 1
    if depth > 16 or budget[0] < 0:
        _reject()
    kind = type(value)
    if kind is dict:
        for key, child in value.items():
            if type(key) is not str or not 1 <= len(key) <= MAX_JSON_BYTES:
                _reject()
            _tree(child, depth + 1, budget)
    elif kind is list:
        for child in value:
            _tree(child, depth + 1, budget)
    elif kind is float:
        if not math.isfinite(value):
            _reject()
    elif kind is int:
        if not -MAX_INTEGER <= value <= MAX_INTEGER:
            _reject()
    elif kind is str:
        if len(value) > MAX_JSON_BYTES:
            _reject()
    elif value is not None and kind is not bool:
        _reject()


def canonical_bytes(value):
    """Strict JSON encoding; booleans and integers retain distinct encodings."""
    try:
        _tree(value)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("ascii")
        if len(raw) > MAX_JSON_BYTES:
            _reject()
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise EvidenceError("Worker evidence rejected") from None


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_digest(value):
    if type(value) is not str or not _DIGEST.fullmatch(value):
        _reject()
    return value


def _pairs(items):
    output = {}
    for key, value in items:
        if key in output:
            _reject()
        output[key] = value
    return output


def strict_json(raw, max_bytes=MAX_JSON_BYTES):
    if (type(raw) is not bytes or type(max_bytes) is not int
            or not 1 <= max_bytes <= MAX_TOTAL_ARTIFACT_BYTES or not 1 <= len(raw) <= max_bytes):
        _reject()
    try:
        def constant(_):
            _reject()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=constant)
        _tree(value)
        return value
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise EvidenceError("Worker evidence rejected") from None


def _owned(value, fields):
    if type(value) is not dict or set(value) != fields:
        _reject()
    return strict_json(canonical_bytes(value))


def _integer(value, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        _reject()
    return value


def _identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _reject()
    return value


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _reject()
    return value


def _literal(value, expected):
    if type(value) is not type(expected) or value != expected:
        _reject()


def validate_context(value):
    result = _owned(value, _CONTEXT_FIELDS)
    _literal(result["schema"], "mra-execution-context/v1")
    _literal(result["environment"], "public_fixture")
    _literal(result["operation"], "retained_native_replay")
    for key in ("agency_id", "project_id", "case_id", "worker_id"):
        _identifier(result[key])
    for key in ("job_id", "attempt_id"):
        _id(result[key])
    _integer(result["fence"], 1, 3)
    for key in ("job_sha256", "source_sha256", "policy_sha256", "plan_sha256", "adapter_sha256", "runtime_sha256"):
        validate_digest(result[key])
    if result["image_sha256"] is not None:
        validate_digest(result["image_sha256"])
    return result


def execution_digest(context):
    context = validate_context(context)
    return digest({key: context[key] for key in ("agency_id", "project_id", "case_id", "job_id", "attempt_id", "fence")})


def validate_challenge(value):
    result = _owned(value, _CHALLENGE_FIELDS)
    _literal(result["schema"], "mra-evidence-challenge/v1")
    _id(result["ledger_id"])
    for key in ("nonce", "context_sha256", "execution_sha256"):
        validate_digest(result[key])
    issued = _integer(result["issued_at"])
    expires = _integer(result["expires_at"])
    if not 1 <= expires - issued <= 300:
        _reject()
    return result


def validate_artifacts(value):
    result = _owned(value, frozenset(NATIVE_ARTIFACT_NAMES))
    total = 0
    for name in NATIVE_ARTIFACT_NAMES:
        record = result[name]
        if type(record) is not dict or set(record) != {"sha256", "size_bytes"}:
            _reject()
        validate_digest(record["sha256"])
        total += _integer(record["size_bytes"], 1, MAX_ARTIFACT_BYTES)
    if total > MAX_TOTAL_ARTIFACT_BYTES:
        _reject()
    return result


def validate_observations(value):
    # Compare type as well as value: 0 must never impersonate False.
    fields = frozenset({"schema", "image_verified", "hostile_code_isolated", "network_isolated",
                        "filesystem_isolated", "resource_limits_verified"})
    result = _owned(value, fields)
    _literal(result["schema"], "mra-local-observation/v1")
    for key in fields - {"schema"}:
        _literal(result[key], False)
    return result


def validate_statement(value):
    result = _owned(value, frozenset({"schema", "context", "challenge", "artifacts", "observations", "issued_at", "expires_at"}))
    _literal(result["schema"], "mra-worker-evidence/v1")
    context = result["context"] = validate_context(result["context"])
    challenge = result["challenge"] = validate_challenge(result["challenge"])
    result["artifacts"] = validate_artifacts(result["artifacts"])
    result["observations"] = validate_observations(result["observations"])
    issued, expires = _integer(result["issued_at"]), _integer(result["expires_at"])
    if (not 1 <= expires - issued <= 300
            or not challenge["issued_at"] <= issued < expires <= challenge["expires_at"]
            or challenge["context_sha256"] != digest(context)
            or challenge["execution_sha256"] != execution_digest(context)):
        _reject()
    return result
