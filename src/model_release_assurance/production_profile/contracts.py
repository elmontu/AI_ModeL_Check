"""Fixed public Wine profile metadata; no scientific or production authority.

All values are owned, bounded canonical metadata. Stage digests bind retained
records, not independently verified execution or recipient receipt.
"""
from __future__ import annotations

from ..production_review import contracts as _review
from ..production_delivery import contracts as _delivery

FLAGS = {**_delivery.FLAGS, "assessment_eligible": False, "production_ready": False}
MAX_JSON_BYTES = 65536
MAX_STATE_BYTES = 1024 * 1024
STAGES = ("planned", "native", "external", "assess", "approve", "authorize", "complete")
_PLAN_FIELDS = {"schema", "run_id", "campaign_id", "agency_id", "project_id", "case_id", "recipient_id",
    "profile_id", "seed", "max_rows", "native_policy_sha256", "sacro_lock_sha256", "sacro_recipe_sha256",
    "implementation_sha256", "max_external_auc_bps", "required_cases", "atomicity", *FLAGS}
_PAYLOADS = {
    "native": {"campaign_id", "policy_sha256", "completion_sha256", "candidate_sha256", "binding_sha256",
               "registration_id", "registration_sha256"},
    "external": {"combined_sha256", "files_sha256", "external_plan_sha256", "external_result_sha256"},
    "assess": {"combined_sha256", "native_assessment_sha256"},
    "approve": {"combined_sha256", "assessment_sha256", "native_approval_sha256"},
    "authorize": {"combined_sha256", "approval_sha256", "activation_id", "activation_sha256", "delivery_pin"},
    "complete": {"combined_sha256", "activation_id", "final_delivery_pin", "delivery_summary_sha256", "lifecycle_sha256"},
}


class ProfileError(ValueError):
    """A fixed public-profile record is malformed or inconsistent."""


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, TypeError, OverflowError):
        raise ProfileError("Public profile metadata rejected") from None


def canonical_bytes(value, max_bytes=MAX_JSON_BYTES):
    return _call(_review.canonical_bytes, value, max_bytes=max_bytes)


def strict_json(raw, max_bytes=MAX_JSON_BYTES):
    return _call(_review.strict_json, raw, max_bytes=max_bytes)


def digest(value, max_bytes=MAX_JSON_BYTES):
    return _call(_review.digest, value, max_bytes=max_bytes)


def owned(value, fields=None, max_bytes=MAX_JSON_BYTES):
    return _call(_review.owned, value, fields, max_bytes=max_bytes)


def integer(value, minimum=0, maximum=2 ** 53 - 1):
    return _call(_review.integer, value, minimum, maximum)


def identifier(value):
    return _call(_review.identifier, value)


def hex_id(value):
    return _call(_review.hex_id, value)


def validate_digest(value):
    return _call(_review.validate_digest, value)


def validate_actor(value):
    return _call(_review.validate_actor, value)


def validate_delivery_pin(value):
    return _call(_delivery.validate_pin, value)


def validate_plan(value):
    result = owned(value, _PLAN_FIELDS)
    for field in ("run_id", "campaign_id"):
        hex_id(result[field])
    for field in ("agency_id", "project_id", "case_id", "recipient_id"):
        identifier(result[field])
    for field in _PLAN_FIELDS:
        if field.endswith("_sha256"):
            validate_digest(result[field])
    fixed = {"schema": "mra-public-profile-plan/v1", "profile_id": "sklearn-wine", "seed": 20261001,
             "max_rows": 128, "max_external_auc_bps": 9900, "required_cases": ["target", "positive", "null"],
             "atomicity": "single_store_fixture_activation_only", **FLAGS}
    if any(canonical_bytes(result[key]) != canonical_bytes(expected) for key, expected in fixed.items()):
        raise ProfileError("Only the fixed public Wine profile is supported")
    return result


def validate_pin(value):
    result = owned(value, {"schema", "store_id", "sequence", "head_sha256"})
    if result["schema"] != "mra-public-profile-journal-pin/v1":
        raise ProfileError("Wrong journal checkpoint domain")
    hex_id(result["store_id"])
    integer(result["sequence"], 1, len(STAGES))
    validate_digest(result["head_sha256"])
    if result["head_sha256"] == "0" * 64:
        raise ProfileError("A checkpoint must bind retained history")
    return result


def validate_payload(stage, value):
    if type(stage) is not str or stage not in STAGES:
        raise ProfileError("Unknown public profile stage")
    if stage == "planned":
        return validate_plan(value)
    result = owned(value, _PAYLOADS[stage])
    for field, item in result.items():
        if field.endswith("_sha256"):
            validate_digest(item)
        elif field.endswith("_id"):
            hex_id(item)
        elif field in ("delivery_pin", "final_delivery_pin"):
            validate_delivery_pin(item)
    return result


def validate_record(value):
    result = owned(value, {"stage", "actor", "at", "payload", "sha256"})
    validate_actor(result["actor"])
    integer(result["at"])
    validate_payload(result["stage"], result["payload"])
    validate_digest(result["sha256"])
    if digest({key: item for key, item in result.items() if key != "sha256"}) != result["sha256"]:
        raise ProfileError("Stage digest differs from retained metadata")
    return result
