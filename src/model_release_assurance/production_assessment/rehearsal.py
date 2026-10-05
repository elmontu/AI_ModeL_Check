"""Prepare a local evidence handoff and demonstrate bounded finding review."""
from __future__ import annotations

from pathlib import Path
from ..production_capacity import io
from ..production_review.rehearsal import ReviewFixture
from ..production_review.authorization import ReviewAuthorization
from . import contracts as c
from . import packet
from .probes import run_probes, probe_plan, validate_result
from .review import LocalFindingReview

REQUIRED_CHECKS = frozenset({
    "production_profile_refused_before_output", "frozen_plan_matches_observations",
    "all_fixed_probes_accounted", "externally_pinned_packet_verified",
    "wrong_external_pins_refused", "bound_fixture_tamper_refused",
    "producer_review_refused", "production_blockers_stay_open",
    "distinct_current_local_review_complete", "expired_review_is_historical_only",
    "serialized_records_do_not_restore_review", "all_results_non_authorizing",
})


def _deny(function):
    try:
        function()
    except c.AssessmentError:
        return True
    return False


def exercise(output, *, profile="agency_private_cloud"):
    c.require_local(profile)
    destination = io.fresh_directory(output)
    result = {"schema": "mra-local-assessment-exercise/v1", "status": "failed",
              "checks": [], "errors": [], "summary": {}, **c.FLAGS}
    stage = "production_refusal"
    def check(name, condition):
        result["checks"].append({"name": name, "passed": bool(condition)})
        if condition is not True:
            c.fail()
    try:
        denied_root = destination / "denied-production"
        check("production_profile_refused_before_output", _deny(lambda: run_probes(denied_root))
              and not denied_root.exists())
        stage = "adversarial_probes"
        handoff = io.fresh_directory(destination / "packet")
        plan = probe_plan()
        io.exclusive_write(handoff / "assessment-plan.json", c.canonical_bytes(plan))
        observed = run_probes(handoff / "fixture", profile=profile)
        validate_result(observed)
        result["summary"]["probes"] = observed["summary"]
        io.exclusive_write(handoff / "assessment-observations.json", c.canonical_bytes(observed))
        io.exclusive_write(handoff / "assessment-findings.json", c.canonical_bytes(c.finding_catalog()))
        check("frozen_plan_matches_observations", plan == probe_plan()
              and observed["plan_sha256"] == c.digest(plan))
        check("all_fixed_probes_accounted", observed["status"] == "passed")
        stage = "packet_integrity"
        pins = packet.seal_packet(handoff, profile=profile)
        verified = packet.verify_packet(handoff,
            expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256=pins["key_sha256"])
        result["packet"] = verified
        result["pins"] = pins
        check("externally_pinned_packet_verified", verified["status"] == "historical_packet_verified")
        check("wrong_external_pins_refused", _deny(lambda: packet.verify_packet(handoff,
            expected_manifest_sha256="0"*64, expected_key_sha256=pins["key_sha256"]))
            and _deny(lambda: packet.verify_packet(handoff,
                expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256="0"*64)))
        # Newly owned, quiescent local evidence only. Repair exact bytes, never
        # restamp the packet or modify any previous milestone's files.
        bound_file = handoff / "fixture" / "plan.json"
        saved = io.read_file(bound_file)
        try:
            bound_file.write_bytes(saved + b" ")
            tamper_refused = _deny(lambda: packet.verify_packet(handoff,
                expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256=pins["key_sha256"]))
        finally:
            bound_file.write_bytes(saved)
        repaired = packet.verify_packet(handoff,
            expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256=pins["key_sha256"])
        check("bound_fixture_tamper_refused", tamper_refused and repaired == verified)
        stage = "local_finding_review"
        fixture = ReviewFixture(destination / "local-review")
        # Legitimate signed start authorization records the actual fixture
        # producer as an operator for canonical-person independence.
        with fixture.identity._lock:
            ReviewAuthorization(fixture.identity).access(fixture.token("operator"), "case-a", "start").recheck()
        service = LocalFindingReview(fixture.identity, packet_sha256=pins["manifest_sha256"],
            agency_id="agency", project_id="project", case_id="case-a", profile=profile)
        dispositions = c.default_dispositions()
        check("producer_review_refused", all(_deny(lambda subject=subject: service.assess(
            fixture.token(subject), expected_packet_sha256=pins["manifest_sha256"], dispositions=dispositions))
            for subject in ("owner", "owner-alias", "operator")))
        changed = c.owned(dispositions)
        changed[0]["disposition"] = "accepted_for_local_fixture"
        check("production_blockers_stay_open", _deny(lambda: service.assess(fixture.token("assessor"),
            expected_packet_sha256=pins["manifest_sha256"], dispositions=changed)))
        assessment = service.assess(fixture.token("assessor"), expected_packet_sha256=pins["manifest_sha256"],
                                    dispositions=dispositions)
        approval = service.approve(fixture.token("releaser"), expected_packet_sha256=pins["manifest_sha256"],
                                  expected_assessment_sha256=c.digest(assessment))
        status = service.status(fixture.token("auditor"), expected_packet_sha256=pins["manifest_sha256"])
        check("distinct_current_local_review_complete", status["review_usable"] is True
            and status["status"] == "local_review_complete"
            and assessment["actor"]["person_id"] != approval["actor"]["person_id"])
        # Persist historical records only; serialized data has no restore path.
        io.exclusive_write(destination / "local-review-records.json",
            c.canonical_bytes({"assessment": assessment, "approval": approval}))
        fixture.now = 1240  # Monotonic test-clock advance; original credentials expire.
        stale = service.status(fixture.token("auditor", expires_at=1249),
                               expected_packet_sha256=pins["manifest_sha256"])
        check("expired_review_is_historical_only", stale["review_usable"] is False
              and stale["status"] == "local_review_stale" and stale["assessment"] == assessment
              and stale["approval"] == approval)
        reopened = LocalFindingReview(fixture.identity, packet_sha256=pins["manifest_sha256"],
            agency_id="agency", project_id="project", case_id="case-a", profile=profile)
        history = reopened.status(fixture.token("auditor", expires_at=1249),
                                  expected_packet_sha256=pins["manifest_sha256"])
        check("serialized_records_do_not_restore_review", history["status"] == "awaiting_assessment"
              and history["assessment"] is None and history["approval"] is None)
        result["summary"]["review"] = {"production_blocker_count": len(c.BLOCKING_FINDING_IDS),
            "local_residual_count": len(c.LOCAL_FINDING_IDS), "production_blockers_open": True,
            "current_local_review_demonstrated": True, "expired_review_unusable": True,
            "serialized_review_restored": False, "agency_assessor_appointed": False}
        check("all_results_non_authorizing", all(verified[key] is flag for key, flag in c.FLAGS.items())
              and all(status[key] is flag for key, flag in c.FLAGS.items()))
        # Final exact historical replay after review/expiry work. No earlier
        # integrity observation is carried over as a current handoff guarantee.
        final_packet = packet.verify_packet(handoff,
            expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256=pins["key_sha256"])
        if final_packet != verified:
            c.fail()
        if {row["name"] for row in result["checks"]} != REQUIRED_CHECKS:
            c.fail()
        result["status"] = "passed"
    except Exception:
        # Failed stages and successful prior measurements remain available.
        result["errors"].append({"stage": stage, "code": "LocalAssessmentStageFailed"})
    io.exclusive_write(destination / "exercise-result.json", c.canonical_bytes(result))
    return result
