"""Strict non-authorizing metadata for bounded public-fixture delivery."""
from __future__ import annotations

import hashlib

from ..production_review import contracts as review

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_CHUNK_BYTES = 16 * 1024
MAX_STATE_BYTES = 16 * 1024 * 1024
FLAGS = {"fixture_only": True, "production_authorized": False, "authorization_eligible": False,
         "model_delivery": False, "private_data": False, "independent_custody_verified": False,
         "recipient_receipt_verified": False}
_ACTIVATION = {"schema", "activation_id", "campaign_id", "agency_id", "project_id", "case_id", "recipient_id",
    "artifact_sha256", "artifact_size", "policy_sha256", "binding_sha256", "approval_sha256", "review_store_id",
    "review_head_sha256", "expires_at", "format", "profile"}
_GRANT = {"grant_id", "activation_id", "transfer_id", "recipient_id", "recipient_person_id",
          "recipient_credential_sha256", "expires_at", "max_attempted_bytes"}
_CHUNK = {"activation_id", "grant_id", "transfer_id", "request_id", "chunk_id", "offset", "length"}
_PIN = {"schema", "store_id", "sequence", "head_sha256"}


class DeliveryError(ValueError):
    """Malformed public-fixture delivery metadata or inert candidate."""


def _fail():
    raise DeliveryError("Public fixture delivery metadata rejected")


def _wrapped(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception:
        raise DeliveryError("Public fixture delivery metadata rejected") from None


def canonical_bytes(value, max_bytes=65536):
    return _wrapped(review.canonical_bytes, value, max_bytes=max_bytes)


def strict_json(raw, max_bytes=65536):
    return _wrapped(review.strict_json, raw, max_bytes=max_bytes)


def digest(value, max_bytes=65536):
    return hashlib.sha256(canonical_bytes(value, max_bytes)).hexdigest()


def owned(value, fields=None, max_bytes=65536):
    return _wrapped(review.owned, value, fields=fields, max_bytes=max_bytes)


def integer(value, minimum=0, maximum=2 ** 53 - 1):
    return _wrapped(review.integer, value, minimum, maximum)


def identifier(value):
    return _wrapped(review.identifier, value)


def hex_id(value):
    return _wrapped(review.hex_id, value)


def validate_digest(value):
    return _wrapped(review.validate_digest, value)


def validate_actor(value):
    return _wrapped(review.validate_actor, value)


def validate_case(value):
    return _wrapped(review.validate_case, value)


def validate_pin(value):
    result = owned(value, _PIN)
    if result["schema"] != "mra-fixture-delivery-pin/v1":
        _fail()
    hex_id(result["store_id"])
    integer(result["sequence"], 1)
    validate_digest(result["head_sha256"])
    if result["head_sha256"] == "0" * 64:
        _fail()
    return result


def validate_activation(value):
    result = owned(value, _ACTIVATION)
    if (result["schema"] != "mra-fixture-delivery-activation/v1"
            or result["format"] != "native_candidate_json" or result["profile"] != "local_public_fixture"):
        _fail()
    for key in ("activation_id", "campaign_id", "review_store_id"):
        hex_id(result[key])
    for key in ("agency_id", "project_id", "case_id", "recipient_id"):
        identifier(result[key])
    for key in _ACTIVATION:
        if key.endswith("_sha256"):
            validate_digest(result[key])
    integer(result["artifact_size"], 1, MAX_ARTIFACT_BYTES)
    integer(result["expires_at"], 1)
    return result


def validate_grant(value):
    result = owned(value, _GRANT)
    for key in ("grant_id", "activation_id", "transfer_id"):
        hex_id(result[key])
    for key in ("recipient_id", "recipient_person_id"):
        identifier(result[key])
    validate_digest(result["recipient_credential_sha256"])
    integer(result["expires_at"], 1)
    integer(result["max_attempted_bytes"], 1, 3 * MAX_ARTIFACT_BYTES)
    return result


def validate_chunk(value):
    result = owned(value, _CHUNK)
    for key in _CHUNK - {"offset", "length"}:
        hex_id(result[key])
    integer(result["offset"], 0, MAX_ARTIFACT_BYTES - 1)
    integer(result["length"], 1, MAX_CHUNK_BYTES)
    if result["offset"] + result["length"] > MAX_ARTIFACT_BYTES:
        _fail()
    return result


def validate_payload(operation, value):
    if operation == "activate":
        return validate_activation(value)
    if operation == "grant":
        return validate_grant(value)
    if operation == "admit":
        return validate_chunk(value)
    if operation in ("suspend", "resume", "revoke"):
        result = owned(value, {"activation_id", "reason"})
        hex_id(result["activation_id"])
        if result["reason"] != "operator_request":
            _fail()
        return result
    if operation == "revoke_grant":
        result = owned(value, {"grant_id"})
        hex_id(result["grant_id"])
        return result
    if operation == "observe":
        result = owned(value, {"request_id", "bytes_written", "status", "write_extent_known", "recipient_receipt_verified"})
        hex_id(result["request_id"])
        if type(result["write_extent_known"]) is not bool:
            _fail()
        if result["write_extent_known"]:
            integer(result["bytes_written"], 0, MAX_CHUNK_BYTES)
        elif result["bytes_written"] is not None or result["status"] != "failed":
            _fail()
        if result["status"] not in ("returned", "interrupted", "failed") or result["recipient_receipt_verified"] is not False:
            _fail()
        if result["status"] == "failed" and result["write_extent_known"] and result["bytes_written"] != 0:
            _fail()
        return result
    _fail()


def validate_artifact(raw, activation):
    """Parse bounded inert native JSON; no estimator loading or execution."""
    activation = validate_activation(activation)
    if (type(raw) is not bytes or not 1 <= len(raw) <= MAX_ARTIFACT_BYTES
            or len(raw) != activation["artifact_size"]
            or hashlib.sha256(raw).hexdigest() != activation["artifact_sha256"]):
        _fail()
    try:
        from ..production_adapters.contracts import parse_candidate
        parse_candidate(raw)
    except Exception:
        raise DeliveryError("Public fixture candidate rejected") from None
    return raw
