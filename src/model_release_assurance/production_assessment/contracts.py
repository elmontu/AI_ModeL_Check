"""Strict local assessment metadata with permanently open production blockers.

The catalog describes unmet production work. Local automation cannot assert its
completion, appoint an assessor, grant risk acceptance for deployment or turn
engineering observations into privacy accounting.
"""
from __future__ import annotations

from types import MappingProxyType
import re
from ..production_capacity import contracts as bounded

MAX_BYTES = 65536
FLAGS = MappingProxyType({
    "local_public_fixture": True, "production_ready": False, "can_clear": False,
    "authorization_eligible": False, "private_data_admitted": False,
    "privacy_accounting_supported": False, "independent_agency_assessment": False,
    "model_delivery": False,
})


class AssessmentError(ValueError):
    """The bounded local assessment protocol could not establish its facts."""


def fail():
    raise AssessmentError("Local assessment record rejected")


def _wrap(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception:
        raise AssessmentError("Local assessment record rejected") from None


def integer(value, minimum=0, maximum=2**53-1):
    return _wrap(bounded.integer, value, minimum, maximum)


def validate_digest(value):
    return _wrap(bounded.validate_digest, value)


def identifier(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is None:
        fail()
    return value


def require_local(profile):
    if type(profile) is not str or profile != "local_public_fixture":
        raise AssessmentError("Production assessment is unavailable")


def canonical_bytes(value, max_bytes=MAX_BYTES):
    integer(max_bytes, 1, MAX_BYTES)
    return _wrap(bounded.canonical_bytes, value, max_bytes=max_bytes)


def strict_json(raw, max_bytes=MAX_BYTES):
    integer(max_bytes, 1, MAX_BYTES)
    return _wrap(bounded.strict_json, raw, max_bytes=max_bytes)


def digest(value, max_bytes=MAX_BYTES):
    import hashlib
    return hashlib.sha256(canonical_bytes(value, max_bytes)).hexdigest()


def owned(value):
    return strict_json(canonical_bytes(value))


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        fail()
    return owned(value)


# Fixed descriptions of outstanding work, not claims that a mitigation exists.
_PRODUCTION = (
    ("deployment_pentest", "Deployed-system penetration testing has not been independently completed."),
    ("network_isolation", "Production network and execution isolation have not been independently verified."),
    ("real_idp_kms", "Agency IdP, key management and production custody are not integrated and qualified."),
    ("independent_custody", "Independently administered evidence and checkpoint custody is not established."),
    ("private_cohort", "Private-cohort intake, lineage and protected population qualification remain unapproved."),
    ("scientific_acceptance", "Agency scientific criteria, protected units and independent audit data remain unapproved."),
    ("dp_accountant", "A justified DP mechanism and cumulative privacy accountant are absent; attack scores provide no DP clearance."),
    ("agency_scale", "Agency peak-load, service objectives and disaster recovery acceptance remain unqualified."),
    ("appointed_owners", "Named agency accountability and independent assessment owners remain unappointed."),
    ("agency_acceptance", "The agency has not issued production acceptance or residual-risk authorization."),
    ("publication", "Repository publication and authenticated external review remain pending."),
)
_LOCAL = (
    ("local_small_sample_measurements", "Fixed public fixtures yield small-sample engineering observations only.",
     "descriptive_fixture_measurements_only"),
    ("local_in_process_trust", "The local fixture uses ephemeral in-process identities and trusted test components.",
     "trusted_local_fixture_only"),
)
BLOCKING_FINDING_IDS = tuple(row[0] for row in _PRODUCTION)
LOCAL_FINDING_IDS = tuple(row[0] for row in _LOCAL)


def finding_catalog():
    findings = [{"finding_id": key, "category": "production_blocker", "description": description,
                 "allowed_dispositions": ["open"], "allowed_justifications": []}
                for key, description in _PRODUCTION]
    findings += [{"finding_id": key, "category": "local_residual", "description": description,
                  "allowed_dispositions": ["acknowledged", "accepted_for_local_fixture"],
                  "allowed_justifications": [reason]} for key, description, reason in _LOCAL]
    return {"schema": "mra-local-assessment-catalog/v1", "findings": findings, **FLAGS}


def catalog_sha256():
    return digest(finding_catalog())


def validate_catalog(value):
    result = owned(value)
    if canonical_bytes(result) != canonical_bytes(finding_catalog()):
        fail()
    return result


def default_dispositions():
    return [{"finding_id": key, "disposition": "open", "justification": None}
            for key in BLOCKING_FINDING_IDS] + [
        {"finding_id": key, "disposition": "acknowledged", "justification": None}
        for key in LOCAL_FINDING_IDS]


def validate_dispositions(value):
    result = owned(value)
    catalog = finding_catalog()["findings"]
    if type(result) is not list or len(result) != len(catalog):
        fail()
    for row, definition in zip(result, catalog):
        row = _exact(row, {"finding_id", "disposition", "justification"})
        if (type(row["finding_id"]) is not str or row["finding_id"] != definition["finding_id"]
                or type(row["disposition"]) is not str
                or row["disposition"] not in definition["allowed_dispositions"]):
            fail()
        if row["disposition"] == "accepted_for_local_fixture":
            if type(row["justification"]) is not str or row["justification"] not in definition["allowed_justifications"]:
                fail()
        elif row["justification"] is not None:
            fail()
    return result


def validate_binding(value):
    result = _exact(value, {"schema", "packet_sha256", "catalog_sha256", "agency_id", "project_id", "case_id"})
    if result["schema"] != "mra-local-assessment-binding/v1" or result["catalog_sha256"] != catalog_sha256():
        fail()
    validate_digest(result["packet_sha256"])
    for name in ("agency_id", "project_id", "case_id"):
        identifier(result[name])
    return result


def validate_actor(value):
    result = _exact(value, {"person_id", "authority_revision", "credential_sha256"})
    identifier(result["person_id"])
    integer(result["authority_revision"], 1)
    validate_digest(result["credential_sha256"])
    return result


def validate_review_record(value):
    if type(value) is not dict or type(value.get("kind")) is not str:
        fail()
    kind = value["kind"]
    extra = {"dispositions"} if kind == "assessment" else {"assessment_sha256"} if kind == "approval" else None
    if extra is None:
        fail()
    result = _exact(value, {"schema", "kind", "binding", "actor", "recorded_at", *extra, *FLAGS})
    if result["schema"] != "mra-local-assessment-review/v1" or any(result[key] is not flag for key, flag in FLAGS.items()):
        fail()
    validate_binding(result["binding"])
    validate_actor(result["actor"])
    integer(result["recorded_at"])
    if kind == "assessment":
        validate_dispositions(result["dispositions"])
    else:
        validate_digest(result["assessment_sha256"])
    return result
