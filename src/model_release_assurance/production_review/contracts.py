"""Strict metadata for a prospective, non-authorizing public-fixture review.

Digest bindings and policy thresholds are engineering requirements. They do not
establish scientific adequacy, agency approval, privacy accounting or release.
"""
from __future__ import annotations

import hashlib
import json
import re

MAX_JSON_BYTES = 65536
MAX_STATE_BYTES = 16 * 1024 * 1024
FLAGS = {"fixture_only": True, "authorization_eligible": False, "production_authorized": False,
         "model_delivery": False, "can_clear": False, "scientific_evidence_qualified": False,
         "privacy_accounting_supported": False}
PROFILE_IDS = ("acs", "bts", "hmda", "tlc", "sklearn-breast-cancer", "sklearn-wine",
               "sklearn-digits", "sklearn-diabetes")
CONTROLS = ["known_leak", "null", "loss_membership"]
_POLICY = {"schema", "campaign_id", "agency_id", "project_id", "case_id", "recipient_id", "profile_id",
    "source_sha256", "data_sha256", "metadata_sha256", "plan_sha256", "workflow_sha256", "runtime_sha256",
    "adapter_sha256", "seed", "max_rows", "utility_floor_bps", "max_membership_auc_bps", "required_controls", *FLAGS}
_BINDING = {"campaign_id", "policy_sha256"}
_COMPLETION = _BINDING | {"registration_id", "registration_sha256", "candidate_sha256", "report_sha256",
    "artifacts_sha256", "envelope_sha256", "admission_sha256", "context_sha256",
    "utility_improvement_bps", "membership_auc_bps"}
_OPERATIONS = {
    "policy": _BINDING | {"delegation_id"}, "start": _BINDING, "complete": _COMPLETION,
    "fail": _BINDING | {"reason"},
    "assess": {"campaign_id", "binding_sha256", "verdict", "delegation_id"},
    "approve": {"campaign_id", "binding_sha256", "assessment_sha256", "delegation_id"},
    "delegate": _BINDING | {"delegation_id", "action", "delegate_person_id", "expires_at"},
    "revoke": {"delegation_id"},
}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HEX = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class ReviewError(ValueError):
    """A bounded review record is malformed or contradictory."""


def _fail():
    raise ReviewError("Fixture review metadata rejected")


def integer(value, minimum=0, maximum=2 ** 53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def identifier(value):
    if type(value) is not str or not _NAME.fullmatch(value):
        _fail()
    return value


def hex_id(value):
    if type(value) is not str or not _HEX.fullmatch(value):
        _fail()
    return value


def validate_digest(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail()
    return value


def _tree(value, depth=0, remaining=None):
    if remaining is None:
        remaining = [131072]
    remaining[0] -= 1
    if depth > 24 or remaining[0] < 0:
        _fail()
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not 1 <= len(key) <= 128:
                _fail()
            _tree(item, depth + 1, remaining)
    elif type(value) is list:
        for item in value:
            _tree(item, depth + 1, remaining)
    elif type(value) is str:
        if len(value) > 65536:
            _fail()
    elif type(value) is int:
        integer(value, -(2 ** 53 - 1))
    elif value is not None and type(value) is not bool:
        _fail()


def canonical_bytes(value, max_bytes=MAX_JSON_BYTES):
    try:
        integer(max_bytes, 1, MAX_STATE_BYTES)
        _tree(value)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
        if len(raw) > max_bytes:
            _fail()
        return raw
    except Exception:
        raise ReviewError("Fixture review metadata rejected") from None


def digest(value, max_bytes=MAX_JSON_BYTES):
    return hashlib.sha256(canonical_bytes(value, max_bytes)).hexdigest()


def strict_json(raw, max_bytes=MAX_JSON_BYTES):
    try:
        integer(max_bytes, 1, MAX_STATE_BYTES)
        if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
            _fail()
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    _fail()
                result[key] = value
            return result
        def noninteger(_):
            _fail()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_float=noninteger, parse_constant=noninteger)
        _tree(value)
        return value
    except Exception:
        raise ReviewError("Fixture review metadata rejected") from None


def owned(value, fields=None, max_bytes=MAX_JSON_BYTES):
    if fields is not None and (type(value) is not dict or set(value) != set(fields)):
        _fail()
    return strict_json(canonical_bytes(value, max_bytes), max_bytes)


def validate_case(value):
    result = owned(value, {"agency_id", "project_id", "case_id", "submitter_person_id"})
    for item in result.values():
        identifier(item)
    return result


def validate_actor(value):
    result = owned(value, {"person_id", "authority_revision", "credential_sha256"})
    identifier(result["person_id"])
    integer(result["authority_revision"], 1)
    validate_digest(result["credential_sha256"])
    return result


def validate_policy(value):
    result = owned(value, _POLICY)
    if result["schema"] != "mra-fixture-review-policy/v1":
        _fail()
    hex_id(result["campaign_id"])
    for key in ("agency_id", "project_id", "case_id", "recipient_id"):
        identifier(result[key])
    if result["profile_id"] not in PROFILE_IDS or type(result["profile_id"]) is not str:
        _fail()
    for key in _POLICY:
        if key.endswith("_sha256"):
            validate_digest(result[key])
    integer(result["seed"], 0, 2 ** 32 - 1)
    integer(result["max_rows"], 128, 4096)
    integer(result["utility_floor_bps"], 0, 10000)
    integer(result["max_membership_auc_bps"], 5000, 10000)
    if canonical_bytes(result["required_controls"]) != canonical_bytes(CONTROLS):
        _fail()
    if canonical_bytes({key: result[key] for key in FLAGS}) != canonical_bytes(FLAGS):
        _fail()
    return result


def validate_payload(operation, value):
    if operation == "propose":
        return validate_policy(value)
    if type(operation) is not str or operation not in _OPERATIONS:
        _fail()
    result = owned(value, _OPERATIONS[operation])
    for key, item in result.items():
        if key.endswith("_sha256"):
            validate_digest(item)
        elif key in ("campaign_id", "registration_id"):
            hex_id(item)
    if "delegation_id" in result:
        if result["delegation_id"] is None:
            if operation not in ("policy", "assess", "approve"):
                _fail()
        else:
            hex_id(result["delegation_id"])
    if operation == "complete":
        integer(result["utility_improvement_bps"], -10000, 10000)
        integer(result["membership_auc_bps"], 0, 10000)
    elif operation == "fail" and result["reason"] != "execution_failed":
        _fail()
    elif operation == "assess" and result["verdict"] not in ("accept", "reject"):
        _fail()
    elif operation == "delegate":
        if result["action"] not in ("policy", "assess", "approve"):
            _fail()
        identifier(result["delegate_person_id"])
        integer(result["expires_at"], 1)
    return result


def completion_binding(policy, completion):
    policy = validate_policy(policy)
    completion = validate_payload("complete", completion)
    if (completion["campaign_id"] != policy["campaign_id"] or completion["policy_sha256"] != digest(policy)):
        _fail()
    return digest({"policy": policy, "completion": completion})


def meets_policy(policy, completion):
    policy = validate_policy(policy)
    completion = validate_payload("complete", completion)
    completion_binding(policy, completion)
    raw = completion["membership_auc_bps"]
    return (completion["utility_improvement_bps"] >= policy["utility_floor_bps"]
            and max(raw, 10000 - raw) <= policy["max_membership_auc_bps"])
