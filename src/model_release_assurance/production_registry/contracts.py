"""Exact engineering-commit records for one fictional count fixture.

These pure validators establish data shape and internal bindings, never current
identity, object custody, database atomicity, independent witness history, a
privacy budget, agency approval, scientific clearance or model delivery.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..production_storage.contracts import ObjectReference, FIXTURE_ID

MAX_JSON_BYTES = 65536
MAX_INTEGER = 2**53 - 1
GENESIS_SHA256 = "0" * 64
FIXTURE_SHA256 = "8012a81724a7d5d70053113e1402d1976c046d7d1c3460be169aa68f59cf709b"
FIXTURE_SIZE_BYTES = 357
CHARGE_UNITS = 1
ACCOUNT_CAPACITY = 8
FLAGS = {"fixture_only": True, "production_authorized": False, "authorization_eligible": False,
         "model_delivery": False, "privacy_accounting_supported": False,
         "assessment_eligible": False, "can_clear": False}
POLICY = {"schema": "mra-fixture-registry-policy/v1", "environment": "public_fixture",
          "purpose": "engineering_atomicity_rehearsal", "fixture_id": FIXTURE_ID,
          "source_sha256": FIXTURE_SHA256, "charge_rule": "fixed_engineering_commit/v1",
          "charge_unit": "fixture_commit", "charge_units": CHARGE_UNITS,
          "account_capacity_units": ACCOUNT_CAPACITY,
          "model_artifacts_supported": False, **FLAGS}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST = frozenset({"schema", "environment", "store_id", "account_id", "request_id", "agency_id",
    "project_id", "case_id", "actor_person_id", "expected_account_sequence", "expected_account_head_sha256",
    "expected_case_sequence", "expected_case_head_sha256", "object_reference", "source_sha256", "policy_sha256", *FLAGS})
_CONTEXT = frozenset({"broker_id", "broker_epoch", "actor_person_id", "actor_credential_sha256",
                      "authority_revision", "trust_revision"})
_RECEIPT = frozenset({"schema", "environment", "store_id", "account_id", "request_id", "request_sha256",
    "agency_id", "project_id", "case_id", "actor_person_id", "commit_context", "receipt_id", "event_id",
    "committed_at", "object_reference_sha256", "source_sha256", "policy_sha256", "previous_account_head_sha256",
    "previous_case_head_sha256", "account_sequence", "case_sequence", "total_engineering_charge_units",
    "charge_units", *FLAGS})


class RegistryContractError(ValueError):
    """Malformed, contradictory or unsupported fictional registry metadata."""


RegistryError = RegistryContractError


def _fail():
    raise RegistryContractError("Fixture registry record rejected")


def integer(value, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _fail()
    return value


def hex_id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail()
    return value


def validate_digest(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail()
    return value


def _tree(value, depth=0, remaining=None):
    if remaining is None:
        remaining = [4096]
    remaining[0] -= 1
    if depth > 16 or remaining[0] < 0:
        _fail()
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not 1 <= len(key) <= MAX_JSON_BYTES:
                _fail()
            _tree(item, depth + 1, remaining)
    elif type(value) is list:
        for item in value:
            _tree(item, depth + 1, remaining)
    elif type(value) is str:
        if len(value) > MAX_JSON_BYTES:
            _fail()
    elif type(value) is int:
        integer(value, -MAX_INTEGER)
    elif value is not None and type(value) is not bool:
        _fail()  # No floats (including 1.0), coercions, tuples or custom objects.


def canonical_bytes(value):
    try:
        _tree(value)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("ascii")
        if len(raw) > MAX_JSON_BYTES:
            _fail()
        return raw
    except Exception:
        raise RegistryContractError("Fixture registry record rejected") from None


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json(raw, max_bytes=MAX_JSON_BYTES):
    try:
        integer(max_bytes, 1, MAX_JSON_BYTES)
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
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_float=noninteger, parse_constant=noninteger)
        _tree(value)
        return value
    except Exception:
        raise RegistryContractError("Fixture registry record rejected") from None


def _owned(value, fields):
    if type(value) is not dict or set(value) != fields:
        _fail()
    return strict_json(canonical_bytes(value))


def _equal(value, expected):
    if canonical_bytes(value) != canonical_bytes(expected):
        _fail()


def _flags(value):
    _equal({key: value[key] for key in FLAGS}, FLAGS)


def fixed_policy():
    return strict_json(canonical_bytes(POLICY))


def account_id(agency_id, project_id):
    return digest({"agency_id": identifier(agency_id), "project_id": identifier(project_id)})


def _scope(value):
    for name in ("agency_id", "project_id", "case_id", "actor_person_id"):
        identifier(value[name])
    _equal(value["account_id"], account_id(value["agency_id"], value["project_id"]))
    hex_id(value["store_id"])
    hex_id(value["request_id"])
    _equal(value["environment"], "public_fixture")
    _equal(value["source_sha256"], FIXTURE_SHA256)
    _equal(value["policy_sha256"], digest(POLICY))
    _flags(value)


def _head(sequence, head):
    integer(sequence)
    validate_digest(head)
    if (sequence == 0) != (head == GENESIS_SHA256):
        _fail()


def validate_request(value):
    """Validate immutable intent; retries do not embed changing credentials.

    The trusted service derives actor_person_id from current signed-token
    authorization. Supplying a matching string is not identity proof. Current
    broker/credential revisions belong to validate_commit_context instead.
    """
    try:
        result = _owned(value, _REQUEST)
        _equal(result["schema"], "mra-fixture-registry-request/v1")
        _scope(result)
        _head(result["expected_account_sequence"], result["expected_account_head_sha256"])
        _head(result["expected_case_sequence"], result["expected_case_head_sha256"])
        integer(result["expected_account_sequence"], 0, ACCOUNT_CAPACITY)
        if result["expected_account_sequence"] < result["expected_case_sequence"]:
            _fail()
        reference = ObjectReference.from_dict(result["object_reference"])
        if (reference.agency_id, reference.project_id, reference.case_id) != (
                result["agency_id"], result["project_id"], result["case_id"]):
            _fail()
        if reference.sha256 != FIXTURE_SHA256 or reference.size_bytes != FIXTURE_SIZE_BYTES:
            _fail()  # Models or other JSON cannot masquerade as the fixed fixture.
        return result
    except Exception:
        raise RegistryContractError("Fixture registry record rejected") from None


def validate_commit_context(value):
    """Validate trusted current guard metadata; this is not a public auth API."""
    result = _owned(value, _CONTEXT)
    hex_id(result["broker_id"])
    identifier(result["actor_person_id"])
    validate_digest(result["actor_credential_sha256"])
    for name in ("broker_epoch", "authority_revision", "trust_revision"):
        integer(result[name], 1)
    return result


def create_receipt(request, commit_context, *, receipt_id, event_id, committed_at):
    """Build fixed charge evidence after the store performs guarded CAS checks."""
    request = validate_request(request)
    context = validate_commit_context(commit_context)
    if context["actor_person_id"] != request["actor_person_id"]:
        _fail()
    hex_id(receipt_id)
    hex_id(event_id)
    integer(committed_at)
    reference = ObjectReference.from_dict(request["object_reference"])
    if not reference.created_at <= committed_at < reference.retention_until:
        _fail()
    body = {"schema": "mra-fixture-registry-receipt/v1", "environment": "public_fixture",
        **{key: request[key] for key in ("store_id", "account_id", "request_id", "agency_id", "project_id",
            "case_id", "actor_person_id", "source_sha256", "policy_sha256")},
        "request_sha256": digest(request), "commit_context": context,
        "receipt_id": receipt_id, "event_id": event_id, "committed_at": committed_at,
        "object_reference_sha256": reference.reference_digest,
        "previous_account_head_sha256": request["expected_account_head_sha256"],
        "previous_case_head_sha256": request["expected_case_head_sha256"],
        "account_sequence": request["expected_account_sequence"] + 1,
        "case_sequence": request["expected_case_sequence"] + 1,
        "total_engineering_charge_units": request["expected_account_sequence"] + CHARGE_UNITS,
        "charge_units": CHARGE_UNITS, **FLAGS}
    return validate_receipt({"receipt": body, "receipt_sha256": digest(body)}, request=request)


def validate_receipt(value, *, request=None):
    """Validate owned receipt bytes; no replay/current-authority claim follows."""
    result = _owned(value, frozenset({"receipt", "receipt_sha256"}))
    body = _owned(result["receipt"], _RECEIPT)
    _equal(body["schema"], "mra-fixture-registry-receipt/v1")
    _scope(body)
    for name in ("receipt_id", "event_id"):
        hex_id(body[name])
    for name in ("request_sha256", "object_reference_sha256"):
        validate_digest(body[name])
    integer(body["committed_at"])
    integer(body["account_sequence"], 1, ACCOUNT_CAPACITY)
    integer(body["case_sequence"], 1, body["account_sequence"])
    integer(body["total_engineering_charge_units"], 1)
    _equal(body["charge_units"], CHARGE_UNITS)
    _equal(body["total_engineering_charge_units"], body["account_sequence"])
    _head(body["account_sequence"] - 1, body["previous_account_head_sha256"])
    _head(body["case_sequence"] - 1, body["previous_case_head_sha256"])
    context = validate_commit_context(body["commit_context"])
    _equal(context["actor_person_id"], body["actor_person_id"])
    _equal(result["receipt_sha256"], digest(body))
    if request is not None:
        intent = validate_request(request)
        _equal(body["request_sha256"], digest(intent))
        for key in ("store_id", "account_id", "request_id", "agency_id", "project_id", "case_id",
                    "actor_person_id", "source_sha256", "policy_sha256"):
            _equal(body[key], intent[key])
        reference = ObjectReference.from_dict(intent["object_reference"])
        _equal(body["object_reference_sha256"], reference.reference_digest)
        if not reference.created_at <= body["committed_at"] < reference.retention_until:
            _fail()
        for domain in ("account", "case"):
            _equal(body[domain + "_sequence"], intent["expected_" + domain + "_sequence"] + 1)
            _equal(body["previous_" + domain + "_head_sha256"], intent["expected_" + domain + "_head_sha256"])
    result["receipt"] = body
    return result


_OUTBOX = frozenset({"schema", "environment", "store_id", "event_id", "account_id", "agency_id",
    "project_id", "case_id", "request_id", "receipt_sha256", "object_reference_sha256", "artifact_sha256",
    "source_sha256", "policy_sha256", *FLAGS})


def create_outbox_event(request, receipt_envelope):
    """Derive an immutable fixture event from one fully bound commit receipt."""
    intent = validate_request(request)
    receipt = validate_receipt(receipt_envelope, request=intent)
    body = receipt["receipt"]
    event = {"schema": "mra-fixture-registry-outbox/v1", "environment": "public_fixture",
        **{key: body[key] for key in ("store_id", "event_id", "account_id", "agency_id", "project_id",
            "case_id", "request_id", "object_reference_sha256", "source_sha256", "policy_sha256")},
        "receipt_sha256": receipt["receipt_sha256"], "artifact_sha256": intent["object_reference"]["sha256"], **FLAGS}
    return validate_outbox_event(event)


def validate_outbox_event(value):
    """Validate receiver input shape; no delivery or independent-witness claim."""
    result = _owned(value, _OUTBOX)
    _equal(result["schema"], "mra-fixture-registry-outbox/v1")
    _equal(result["environment"], "public_fixture")
    for name in ("store_id", "event_id", "request_id"):
        hex_id(result[name])
    for name in ("agency_id", "project_id", "case_id"):
        identifier(result[name])
    _equal(result["account_id"], account_id(result["agency_id"], result["project_id"]))
    for name in ("receipt_sha256", "object_reference_sha256"):
        validate_digest(result[name])
    for name in ("artifact_sha256", "source_sha256"):
        _equal(result[name], FIXTURE_SHA256)
    _equal(result["policy_sha256"], digest(POLICY))
    _flags(result)
    return result
