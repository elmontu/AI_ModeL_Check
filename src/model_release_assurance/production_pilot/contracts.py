"""Strict planning metadata for one non-authorizing public Wine fixture.

Hashes declare exact bindings; they do not prove packet verification or agency
acceptance. Only the current service establishes local review facts. This schema
cannot clear the frozen assessment blockers or admit a pilot.
"""
from __future__ import annotations

from types import MappingProxyType
from ..production_assessment import contracts as assessment

MAX_BYTES = 65536
FLAGS = MappingProxyType({
    **assessment.FLAGS,
    "pilot_admission": False,
    "independent_agency_acceptance": False,
})
PLAN_SCHEMA = "mra-local-restricted-pilot-plan/v1"
EVIDENCE_PROFILE = "PRD18_native_public_fixture"
INTERFACE_ID = "in_process_plan_only"
LOCAL_GO_CRITERIA = (
    "externally_pinned_assessment_packet_verified",
    "exact_public_wine_candidate_bound",
    "distinct_current_independent_local_plan_review",
    "named_signed_fixture_people_current",
    "declared_plan_window_current",
    "named_support_and_suspension_authority_current",
    "all_production_blockers_remain_open",
)
_USER_ROLES = (
    ("person-owner", "model_owner"),
    ("person-policy", "policy_authority"),
    ("person-operator", "test_operator"),
    ("person-assessor", "assessor"),
    ("person-releaser", "release_authority"),
    ("person-auditor", "auditor"),
    ("person-recipient", "auditor"),
)
_BINDING_FIELDS = frozenset({
    "candidate_sha256", "assessment_manifest_sha256", "assessment_key_sha256",
    "catalog_sha256", "agency_id", "project_id", "case_id",
})


class PilotError(ValueError):
    """The bounded local pilot plan could not establish its required facts."""


def fail():
    raise PilotError("Local restricted pilot plan rejected")


def _wrap(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception:
        raise PilotError("Local restricted pilot plan rejected") from None


def integer(value, minimum=0, maximum=2**53-1):
    return _wrap(assessment.integer, value, minimum, maximum)


def identifier(value):
    return _wrap(assessment.identifier, value)


def validate_digest(value):
    return _wrap(assessment.validate_digest, value)


def validate_actor(value):
    return _wrap(assessment.validate_actor, value)


def require_local(profile):
    if type(profile) is not str or profile != "local_public_fixture":
        raise PilotError("Production pilot admission is unavailable")


def canonical_bytes(value, max_bytes=MAX_BYTES):
    integer(max_bytes, 1, MAX_BYTES)
    return _wrap(assessment.canonical_bytes, value, max_bytes=max_bytes)


def strict_json(raw, max_bytes=MAX_BYTES):
    integer(max_bytes, 1, MAX_BYTES)
    return _wrap(assessment.strict_json, raw, max_bytes=max_bytes)


def digest(value, max_bytes=MAX_BYTES):
    import hashlib
    return hashlib.sha256(canonical_bytes(value, max_bytes)).hexdigest()


def owned(value):
    return strict_json(canonical_bytes(value))


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        fail()
    return owned(value)


def validate_binding(value):
    """Validate declarations; candidate/packet authenticity is checked externally."""
    result = _exact(value, _BINDING_FIELDS)
    for name in ("candidate_sha256", "assessment_manifest_sha256", "assessment_key_sha256"):
        validate_digest(result[name])
        if result[name] == "0" * 64:
            fail()
    if (result["catalog_sha256"] != assessment.catalog_sha256()
            or result["agency_id"] != "agency"
            or result["project_id"] != "project"
            or result["case_id"] != "case-a"):
        fail()
    return result


def _window(starts_at, ends_at):
    integer(starts_at, 1000, 1099)
    integer(ends_at, 1001, 1100)
    if not starts_at < ends_at or ends_at - starts_at > 100:
        fail()
    return {"starts_at": starts_at, "ends_at": ends_at,
            "max_duration_seconds": 100, "clock": "synthetic_fixture"}


def pilot_plan(*, candidate_sha256, assessment_manifest_sha256,
               assessment_key_sha256, starts_at=1000, ends_at=1100,
               profile="agency_private_cloud"):
    """Declare one local PLAN; the production default refuses before effects.

    The window bounds planning review only. It never extends original gateway
    activation/grant deadlines or authenticated evidence TTLs. Dynamic hashes
    must be verified externally by the local service.
    """
    require_local(profile)
    binding = validate_binding({
        "candidate_sha256": candidate_sha256,
        "assessment_manifest_sha256": assessment_manifest_sha256,
        "assessment_key_sha256": assessment_key_sha256,
        "catalog_sha256": assessment.catalog_sha256(),
        "agency_id": "agency", "project_id": "project", "case_id": "case-a",
    })
    return {
        "schema": PLAN_SCHEMA,
        "profile": "local_public_fixture",
        "purpose": "restricted_public_fixture_plan_only",
        "binding": binding,
        "model": {"profile_id": "sklearn-wine", "max_rows": 128,
                  "seed": 20261001, "format": "native_candidate_json",
                  "evidence_profile": EVIDENCE_PROFILE,
                  "external_sacro_qualified": False, "dp_qualified": False},
        "recipient": {"recipient_id": "fixture-recipient", "person_id": "person-recipient"},
        "interface": {"interface_id": INTERFACE_ID, "model_queries": 0, "model_delivery_bytes": 0},
        "window": _window(starts_at, ends_at),
        "limits": {"max_named_users": 7, "max_models": 1, "max_interfaces": 1,
                   "max_recipients": 1, "max_queries": 0, "max_delivered_bytes": 0,
                   "max_plan_bytes": MAX_BYTES},
        "named_users": [{"person_id": person, "required_role": role} for person, role in _USER_ROLES],
        "credential_source": "current_signed_fixture_tokens",
        "support": {"person_id": "person-operator", "required_role": "test_operator",
                    "interface_id": INTERFACE_ID},
        "suspension": {"person_id": "person-releaser", "required_role": "release_authority",
                       "scope": "this_plan_only"},
        "go_no_go": {"local_plan_go": list(LOCAL_GO_CRITERIA),
                     "production_no_go": list(assessment.BLOCKING_FINDING_IDS),
                     "local_go_does_not_admit_pilot": True},
        "open_production_blockers": list(assessment.BLOCKING_FINDING_IDS),
        "agency": {"provider": None, "region": None, "sponsor": None,
                   "service_owner": None, "data_steward": None,
                   "independent_assessor": None, "status": "pending"},
        "expansion_policy": "fresh_independent_evidence_and_agency_acceptance_required",
        **FLAGS,
    }


def validate_plan(value):
    """Reject widening, acceptance claims and untyped counts; return owned JSON."""
    result = owned(value)
    if type(result) is not dict:
        fail()
    require_local(result.get("profile"))
    binding = validate_binding(result.get("binding"))
    window = _exact(result.get("window"), {"starts_at", "ends_at", "max_duration_seconds", "clock"})
    expected = pilot_plan(candidate_sha256=binding["candidate_sha256"],
                          assessment_manifest_sha256=binding["assessment_manifest_sha256"],
                          assessment_key_sha256=binding["assessment_key_sha256"],
                          starts_at=window["starts_at"], ends_at=window["ends_at"],
                          profile="local_public_fixture")
    # Canonical comparison distinguishes bools from integers even though Python
    # equality treats True == 1 and False == 0.
    if canonical_bytes(result) != canonical_bytes(expected):
        fail()
    return result
