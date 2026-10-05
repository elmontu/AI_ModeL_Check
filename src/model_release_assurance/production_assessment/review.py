"""Current independent human review of one sealed local packet digest.

The caller supplies the digest of its already sealed packet. This service does
not authenticate that packet, reconstruct execution, appoint agency reviewers,
restore serialized approvals or authorize release. Its two bounded records and
verified contexts live only in memory, under the existing identity lock.
"""
from __future__ import annotations

from functools import wraps
from ..production_identity.policy import PermissionDenied, IdentityUnavailable
from ..production_review.authorization import ReviewAuthorization
from . import contracts as c


def _generic(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            raise c.AssessmentError("Local assessment review rejected") from None
    return wrapped


class LocalFindingReview:
    """One immutable assessment and approval; new packets need a new instance."""
    @_generic
    def __init__(self, identity, *, packet_sha256, agency_id, project_id, case_id,
                 profile="agency_private_cloud"):
        c.require_local(profile)  # Before identity access or state creation.
        binding = c.validate_binding({"schema": "mra-local-assessment-binding/v1",
            "packet_sha256": packet_sha256, "catalog_sha256": c.catalog_sha256(),
            "agency_id": agency_id, "project_id": project_id, "case_id": case_id})
        authorization = ReviewAuthorization(identity)
        with identity._lock:
            case = identity._case(case_id).metadata
            if (case.agency_id, case.project_id, case.case_id) != (agency_id, project_id, case_id):
                c.fail()
            self._identity, self._authorization, self._binding = identity, authorization, binding
            self._assessment = self._approval = None
            self._assessor = self._approver = None

    def _access(self, token, expected_packet_sha256, action):
        c.validate_digest(expected_packet_sha256)
        if expected_packet_sha256 != self._binding["packet_sha256"]:
            c.fail()
        context = self._authorization.access(token, self._binding["case_id"], action)
        if (context.case.agency_id, context.case.project_id) != (self._binding["agency_id"], self._binding["project_id"]):
            c.fail()
        return context

    @_generic
    def assess(self, token, *, expected_packet_sha256, dispositions):
        dispositions = c.validate_dispositions(dispositions)
        with self._identity._lock:
            context = self._access(token, expected_packet_sha256, "assess")
            if self._assessment is not None:
                c.fail()
            record = c.validate_review_record({"schema": "mra-local-assessment-review/v1", "kind": "assessment",
                "binding": self._binding, "actor": context.actor, "recorded_at": context.recheck(),
                "dispositions": dispositions, **c.FLAGS})
            result = c.owned(record)
            self._authorization.recheck_many((context,))
            self._assessment, self._assessor = record, context
            return result

    @_generic
    def approve(self, token, *, expected_packet_sha256, expected_assessment_sha256):
        c.validate_digest(expected_assessment_sha256)
        with self._identity._lock:
            context = self._access(token, expected_packet_sha256, "approve")
            if (self._assessment is None or self._approval is not None
                    or c.digest(self._assessment) != expected_assessment_sha256
                    or context.principal.person_id == self._assessor.principal.person_id):
                c.fail()
            record = c.validate_review_record({"schema": "mra-local-assessment-review/v1", "kind": "approval",
                "binding": self._binding, "actor": context.actor, "recorded_at": context.recheck(),
                "assessment_sha256": expected_assessment_sha256, **c.FLAGS})
            result = c.owned(record)
            self._authorization.recheck_many((self._assessor, context))
            self._approval, self._approver = record, context
            return result

    @_generic
    def status(self, token, *, expected_packet_sha256):
        with self._identity._lock:
            reader = self._access(token, expected_packet_sha256, "read")
            result = {"schema": "mra-local-assessment-review-status/v1", "binding": self._binding,
                "assessment": self._assessment, "approval": self._approval,
                "review_usable": False, "status": "awaiting_assessment",
                "production_blockers": list(c.BLOCKING_FINDING_IDS),
                "historical_records_only": True, "independent_agency_assessment": False, **c.FLAGS}
            if self._assessment is not None:
                result["status"] = "awaiting_approval" if self._approval is None else "local_review_complete"
            result = c.owned(result)
            contexts = (reader,) + tuple(item for item in (self._assessor, self._approver) if item is not None)
            try:
                now = self._authorization.recheck_many(contexts)
                result["review_usable"] = self._assessment is not None and self._approval is not None
            except (PermissionDenied, IdentityUnavailable):
                # Historical records may remain readable, but only after the
                # caller itself passes one final current authorization check.
                now = self._authorization.recheck_many((reader,))
                result["status"] = "local_review_stale"
            result["checked_at"] = now
            return result
