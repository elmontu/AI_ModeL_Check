"""Bounded records for an independently retained LOCAL fixture witness.

History consistency is derived by replaying the existing PRD15 event rules. It
is not authenticated custody, protection against a privileged rollback of all
copies, agency approval, DP accounting or permission to release a model.
"""
from __future__ import annotations

import hashlib
import json

from ..production_registry import contracts as registry_contracts
from ..production_registry import store as registry_store

MAX_JSON_BYTES = 65536
MAX_HISTORY_BYTES = 16 * 1024 * 1024
MAX_STATE_BYTES = 32 * 1024 * 1024
MAX_NODES = 131072
MAX_DEPTH = 32
MAX_INTENTS = 128
MAX_INTEGER = registry_contracts.MAX_INTEGER
GENESIS_SHA256 = registry_contracts.GENESIS_SHA256
FLAGS = {**registry_contracts.FLAGS, "independent_custody_verified": False}
WITNESSFLAGS = FLAGS
_HISTORY = {"schema", "store_id", "schema_version", "broker_epoch", "broker_id",
            "event_sequence", "event_head_sha256", "observed_at", "events", *FLAGS}
_PIN = {"schema", "witness_id", "namespace_id", "registry_id", "revision", "head_sha256"}
_INTENT = {"schema", "namespace_id", "registry_id", "request", "request_sha256",
           "predecessor_sequence", "predecessor_head_sha256", "broker_epoch", *FLAGS}
_DIAGNOSIS = {"schema", "status", "reconciled", "pin", "namespace_id", "registry_id",
              "registry_sequence", "registry_head_sha256", "registry_epoch", "registry_observed_at",
              "pending_intents", "committed_intents", "aborted_intents", "quarantine_reasons", "intents", *FLAGS}


class WitnessContractError(ValueError):
    """Malformed, contradictory or unsupported local witness metadata."""


def _fail():
    raise WitnessContractError("Fixture witness record rejected")


def integer(value, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _wrapped(validator, value):
    try:
        return validator(value)
    except Exception:
        raise WitnessContractError("Fixture witness record rejected") from None


def identifier(value):
    return _wrapped(registry_contracts.identifier, value)


def hex_id(value):
    return _wrapped(registry_contracts.hex_id, value)


def validate_digest(value):
    return _wrapped(registry_contracts.validate_digest, value)


def _tree(value, depth=0, remaining=None):
    if remaining is None:
        remaining = [MAX_NODES]
    remaining[0] -= 1
    if depth > MAX_DEPTH or remaining[0] < 0:
        _fail()
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not 1 <= len(key) <= MAX_STATE_BYTES:
                _fail()
            _tree(item, depth + 1, remaining)
    elif type(value) is list:
        for item in value:
            _tree(item, depth + 1, remaining)
    elif type(value) is str:
        if len(value) > MAX_STATE_BYTES:
            _fail()
    elif type(value) is int:
        integer(value, -MAX_INTEGER)
    elif value is not None and type(value) is not bool:
        _fail()  # Floats, tuples, custom objects and numeric coercions are unsupported.


def canonical_bytes(value, max_bytes=MAX_JSON_BYTES):
    try:
        integer(max_bytes, 1, MAX_STATE_BYTES)
        _tree(value)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("ascii")
        if len(raw) > max_bytes:
            _fail()
        return raw
    except Exception:
        raise WitnessContractError("Fixture witness record rejected") from None


def digest(value, max_bytes=MAX_JSON_BYTES):
    return hashlib.sha256(canonical_bytes(value, max_bytes=max_bytes)).hexdigest()


def strict_json(raw, max_bytes=MAX_JSON_BYTES):
    try:
        integer(max_bytes, 1, MAX_STATE_BYTES)
        if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
            _fail()
        def pairs(items):
            result = {}
            for name, value in items:
                if name in result:
                    _fail()
                result[name] = value
            return result
        def noninteger(_):
            _fail()
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_float=noninteger, parse_constant=noninteger)
        _tree(result)
        return result
    except Exception:
        raise WitnessContractError("Fixture witness record rejected") from None


def _owned(value, fields, max_bytes=MAX_JSON_BYTES):
    if type(value) is not dict or set(value) != fields:
        _fail()
    return strict_json(canonical_bytes(value, max_bytes), max_bytes)


def _equal(value, expected):
    if canonical_bytes(value) != canonical_bytes(expected):
        _fail()


def _flags(value):
    _equal({key: value[key] for key in FLAGS}, FLAGS)


def namespace_id(agency_id, project_id):
    return digest({"agency_id": identifier(agency_id), "project_id": identifier(project_id)})


def _validated_history(value):
    result = _owned(value, _HISTORY, MAX_HISTORY_BYTES)
    _equal(result["schema"], "mra-fixture-registry-history-snapshot/v1")
    _flags(result)
    hex_id(result["store_id"])
    integer(result["schema_version"], 1, 2)
    integer(result["broker_epoch"])
    if result["broker_id"] is not None:
        hex_id(result["broker_id"])
    integer(result["event_sequence"], 1, registry_store.MAX_EVENTS)
    validate_digest(result["event_head_sha256"])
    integer(result["observed_at"])
    events = result["events"]
    if type(events) is not list or len(events) != result["event_sequence"]:
        _fail()
    # This object is only a pure event interpreter. No constructor, filesystem,
    # database, authorization or current-state observation is invoked here.
    interpreter = object.__new__(registry_store.RegistryStore)
    interpreter._store_id = result["store_id"]
    interpreter._version = result["schema_version"]
    state = registry_store._blank()
    for row in events:
        if type(row) is not dict or set(row) != {"event_sha256", "event"}:
            _fail()
        validate_digest(row["event_sha256"])
        # PRD15's own 64KiB/depth/node limits remain authoritative per event.
        event_hash = registry_contracts.digest(row["event"])
        if event_hash != row["event_sha256"]:
            _fail()
        interpreter._apply(state, row["event"], event_hash)
    if (state["count"] != result["event_sequence"] or state["head"] != result["event_head_sha256"]
            or state["version"] != result["schema_version"] or state["epoch"] != result["broker_epoch"]
            or state["broker_id"] != result["broker_id"] or state["clock"] > result["observed_at"]):
        _fail()
    return result, state


def validate_history(value):
    """Return an owned exact snapshot after full PRD15 hash/semantic replay."""
    try:
        return _validated_history(value)[0]
    except Exception:
        raise WitnessContractError("Fixture witness history rejected") from None


def replay_history(value):
    """Return fresh derived internal state, including sets; not JSON or authority."""
    try:
        return _validated_history(value)[1]
    except Exception:
        raise WitnessContractError("Fixture witness history rejected") from None


def _namespace(state, agency_id, project_id):
    scope = namespace_id(agency_id, project_id)
    if len(state["accounts"]) != 1 or scope not in state["accounts"]:
        _fail()
    account = state["accounts"][scope]
    if account["agency_id"] != agency_id or account["project_id"] != project_id:
        _fail()
    return scope


def history_namespace(snapshot, agency_id, project_id):
    """Require exactly one configured account matching the independent bootstrap."""
    try:
        _, state = _validated_history(snapshot)
        return _namespace(state, agency_id, project_id)
    except Exception:
        raise WitnessContractError("Fixture witness namespace rejected") from None


def validate_pin(value):
    """Validate an external checkpoint's shape, not its independent retention."""
    try:
        result = _owned(value, _PIN)
        _equal(result["schema"], "mra-fixture-witness-pin/v1")
        for name in ("witness_id", "registry_id"):
            hex_id(result[name])
        for name in ("namespace_id", "head_sha256"):
            validate_digest(result[name])
        integer(result["revision"], 1)
        if result["head_sha256"] == GENESIS_SHA256:
            _fail()
        return result
    except Exception:
        raise WitnessContractError("Fixture witness pin rejected") from None


def validate_intent(value):
    """Validate immutable request/predecessor bindings, not a live CAS or identity."""
    try:
        result = _owned(value, _INTENT)
        _equal(result["schema"], "mra-fixture-witness-intent/v1")
        _flags(result)
        request = registry_contracts.validate_request(result["request"])
        hex_id(result["registry_id"])
        for name in ("namespace_id", "request_sha256", "predecessor_head_sha256"):
            validate_digest(result[name])
        integer(result["predecessor_sequence"], 2, registry_store.MAX_EVENTS)
        integer(result["broker_epoch"], 1, result["predecessor_sequence"] - 1)
        if (result["registry_id"] != request["store_id"] or result["namespace_id"] != request["account_id"]
                or result["request_sha256"] != registry_contracts.digest(request)
                or result["predecessor_head_sha256"] == GENESIS_SHA256):
            _fail()
        return result
    except Exception:
        raise WitnessContractError("Fixture witness intent rejected") from None


def create_intent(snapshot, request):
    """Freeze exact CAS intent from a fully replayed single-account snapshot."""
    try:
        snapshot, state = _validated_history(snapshot)
        request = registry_contracts.validate_request(request)
        scope = _namespace(state, request["agency_id"], request["project_id"])
        if request["store_id"] != snapshot["store_id"] or state["broker_id"] is None or state["epoch"] < 1:
            _fail()
        account = state["accounts"][scope]
        case = state["cases"].get(registry_store._case_key(request["agency_id"], request["project_id"], request["case_id"]),
                                  {"sequence": 0, "head_sha256": GENESIS_SHA256})
        if (request["expected_account_sequence"] != account["sequence"]
                or request["expected_account_head_sha256"] != account["head_sha256"]
                or request["expected_case_sequence"] != case["sequence"]
                or request["expected_case_head_sha256"] != case["head_sha256"]):
            _fail()
        return validate_intent({"schema": "mra-fixture-witness-intent/v1", "namespace_id": scope,
            "registry_id": snapshot["store_id"], "request": request,
            "request_sha256": registry_contracts.digest(request),
            "predecessor_sequence": state["count"], "predecessor_head_sha256": state["head"],
            "broker_epoch": state["epoch"], **FLAGS})
    except Exception:
        raise WitnessContractError("Fixture witness intent rejected") from None


def validate_diagnosis(value):
    """Validate a local reconciliation summary; never infer release permission."""
    try:
        result = _owned(value, _DIAGNOSIS, MAX_STATE_BYTES)
        _equal(result["schema"], "mra-fixture-witness-diagnosis/v1")
        _flags(result)
        pin = validate_pin(result["pin"])
        validate_digest(result["namespace_id"])
        hex_id(result["registry_id"])
        validate_digest(result["registry_head_sha256"])
        integer(result["registry_sequence"], 1, registry_store.MAX_EVENTS)
        integer(result["registry_observed_at"])
        integer(result["registry_epoch"], 0, result["registry_sequence"] - 1)
        integer(result["pending_intents"], 0, 32)
        integer(result["committed_intents"], 0, registry_contracts.ACCOUNT_CAPACITY)
        integer(result["aborted_intents"], 0, MAX_INTEGER)
        if (result["namespace_id"] != pin["namespace_id"] or result["registry_id"] != pin["registry_id"]
                or result["registry_head_sha256"] == GENESIS_SHA256):
            _fail()
        rows = result["intents"]
        if type(rows) is not list or len(rows) > MAX_INTENTS:
            _fail()
        counts = {"pending": 0, "committed": 0, "aborted": 0}
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != {"intent", "state", "receipt"}:
                _fail()
            intent = validate_intent(row["intent"])
            if type(row["state"]) is not str or row["state"] not in counts:
                _fail()
            request = intent["request"]
            if (intent["namespace_id"] != result["namespace_id"] or intent["registry_id"] != result["registry_id"]
                    or intent["predecessor_sequence"] > result["registry_sequence"]
                    or intent["broker_epoch"] > result["registry_epoch"] or request["request_id"] in seen):
                _fail()
            seen.add(request["request_id"])
            counts[row["state"]] += 1
            if row["state"] == "committed":
                receipt = registry_contracts.validate_receipt(row["receipt"], request=request)
                if (receipt["receipt"]["commit_context"]["broker_epoch"] != intent["broker_epoch"]
                        or receipt["receipt"]["committed_at"] > result["registry_observed_at"]
                        or intent["predecessor_sequence"] >= result["registry_sequence"]):
                    _fail()
            elif row["receipt"] is not None:
                _fail()
            if row["state"] == "aborted" and intent["predecessor_sequence"] >= result["registry_sequence"]:
                _fail()
        for name, count in counts.items():
            integer(result[name + "_intents"], count, count)
        pending = result["pending_intents"] > 0
        _equal(result["status"], "quarantined" if pending else "consistent")
        _equal(result["reconciled"], not pending)
        _equal(result["quarantine_reasons"], ["pending_intent"] if pending else [])
        return result
    except Exception:
        raise WitnessContractError("Fixture witness diagnosis rejected") from None
