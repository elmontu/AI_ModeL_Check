"""Strict local preparation declarations; no completed agency pilot or handover.

Hashes bind exact historical declarations. Current signed review is established
only by the in-process service, never by this JSON or previous readiness records.
Capacity, cost, support schedules and agency retention obligations remain pending.
"""
from __future__ import annotations

from types import MappingProxyType
from ..production_pilot import contracts as pilot

MAX_BYTES = 65536
PREPARATION_SCHEMA = "mra-local-handover-preparation/v1"
FLAGS = MappingProxyType({**pilot.FLAGS,
    "agency_pilot_started": False, "agency_pilot_exit_passed": False,
    "operational_authority_transferred": False, "agency_handover_accepted": False,
    "agency_capacity_qualified": False, "cost_qualified": False,
    "retirement_deletion_verified": False,
})
LOCAL_PREPARATION_CRITERIA = (
    "exact_current_pilot_plan_and_assessment_bound",
    "original_signed_pilot_people_and_window_current",
    "distinct_current_owner_operator_assessor_release_authority",
    "agency_capacity_and_itemized_cost_requirements_pending",
    "support_maintenance_retention_and_retirement_declared_only",
    "all_production_blockers_remain_open",
)


class HandoverError(ValueError):
    """The bounded local handover preparation cannot establish its facts."""


def fail():
    raise HandoverError("Local handover preparation rejected")


def _wrap(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception:
        raise HandoverError("Local handover preparation rejected") from None


def require_local(profile):
    if type(profile) is not str or profile != "local_public_fixture":
        raise HandoverError("Production pilot exit and handover are unavailable")


def integer(value, minimum=0, maximum=2**53-1):
    return _wrap(pilot.integer, value, minimum, maximum)


def validate_digest(value):
    return _wrap(pilot.validate_digest, value)


def canonical_bytes(value, max_bytes=MAX_BYTES):
    integer(max_bytes, 1, MAX_BYTES)
    return _wrap(pilot.canonical_bytes, value, max_bytes=max_bytes)


def strict_json(raw, max_bytes=MAX_BYTES):
    integer(max_bytes, 1, MAX_BYTES)
    return _wrap(pilot.strict_json, raw, max_bytes=max_bytes)


def digest(value, max_bytes=MAX_BYTES):
    import hashlib
    return hashlib.sha256(canonical_bytes(value, max_bytes)).hexdigest()


def owned(value):
    return strict_json(canonical_bytes(value))


def handover_preparation(*, pilot_plan, profile="agency_private_cloud"):
    """Declare preparation only; the default refuses before dependency access.

    The original plan window is copied unchanged. Cadences are future review
    declarations, never authority TTLs, active schedules or retention acceptance.
    No caller-supplied measurements, cloud prices or alleged exit passes enter.
    """
    require_local(profile)
    plan = _wrap(pilot.validate_plan, pilot_plan)
    return {
        "schema": PREPARATION_SCHEMA, "profile": "local_public_fixture",
        "purpose": "public_fixture_exit_and_handover_preparation_only",
        "pilot_plan_sha256": digest(plan), "binding": plan["binding"],
        "window": plan["window"],
        "model": plan["model"], "recipient": plan["recipient"],
        "interface": plan["interface"],
        "limits": {"models": 1, "named_people": 7, "interfaces": 1,
                   "model_runs": 0, "model_queries": 0, "delivered_bytes": 0,
                   "max_preparation_bytes": MAX_BYTES},
        "capacity": {"status": "pending_agency_qualification",
            "reference": "PRD21_public_fixture_only",
            "scope": "historical_public_fixture_reference_only",
            "local_measurements_replayed": False, "approved_peak_load": None,
            "scaling_objective": None, "latency_objective_seconds": None,
            "rto_seconds": None, "rpo_seconds": None,
            "provider": None, "region": None, "population_inference": False},
        "cost": {"status": "pending_agency_qualification", "currency": None,
            "unit_price": None, "estimated_monthly_cost": None,
            "compute": None, "storage": None, "network": None,
            "evidence_retention": None, "support": None,
            "cloud_price_verified": False},
        "support": {"person_id": "person-operator", "required_role": "test_operator",
            "interface_id": pilot.INTERFACE_ID, "scope": "this_preparation_only",
            "agency_service_owner": None, "on_call_service_active": False,
            "escalation_person_id": "person-releaser", "external_messages_sent": False},
        "maintenance": {"review_cadence_days": 7, "schedule_active": False,
            "required_change_reviews": ["access", "trust", "keys", "policy",
                "dependencies", "schemas", "source", "model_or_data"],
            "change_policy": "fresh_evidence_and_current_independent_review_required",
            "authority_or_evidence_ttl_extended": False},
        "retention": {"scope": "local_historical_preparation_records_only",
            "declaration_review_cadence_days": 30, "schedule_active": False,
            "agency_retention_period_days": None, "agency_legal_hold_status": "pending",
            "immutable_evidence_preserved": True, "automatic_deletion_enabled": False},
        "retirement": {"person_id": "person-releaser", "required_role": "release_authority",
            "scope": "this_preparation_only", "terminal": True,
            "gateway_or_pilot_revocation_performed": False, "evidence_deleted": False,
            "agency_deletion_and_legal_hold_acceptance": "pending"},
        "exit_review": {"local_preparation_criteria": list(LOCAL_PREPARATION_CRITERIA),
            "agency_pilot_status": "not_started", "agency_exit_review_status": "pending",
            "operational_transfer_status": "pending", "agency_acceptance": "pending",
            "production_no_go": list(pilot.assessment.BLOCKING_FINDING_IDS)},
        "open_production_blockers": list(pilot.assessment.BLOCKING_FINDING_IDS),
        "credential_source": "current_signed_fixture_tokens",
        "restart_policy": "historical_records_never_restore_current_authority",
        **FLAGS,
    }


def validate_preparation(value, *, pilot_plan):
    """Require the exact declared scope and supplied plan; no proof from JSON."""
    result = owned(value)
    expected = handover_preparation(pilot_plan=pilot_plan, profile="local_public_fixture")
    if canonical_bytes(result) != canonical_bytes(expected):
        fail()
    return result
