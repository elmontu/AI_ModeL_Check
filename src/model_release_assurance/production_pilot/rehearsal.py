"""Restricted local pilot planning after a fresh non-authorizing assessment."""
from __future__ import annotations
from ..production_assessment.rehearsal import exercise as assess
from ..production_capacity import io
from ..production_delivery.rehearsal import DeliveryFixture
from . import contracts as c
from .evidence import VerifiedAssessment
from .service import FixturePilotPlanService

REQUIRED_CHECKS = frozenset({
    "production_refused_before_output", "intent_frozen_before_assessment",
    "fresh_current_source_assessment", "exact_candidate_and_packet_bound",
    "seven_current_signed_people_enrolled", "scope_and_unsigned_proposals_refused",
    "owner_operator_cannot_review", "distinct_current_plan_review_is_planning_only",
    "suspension_resume_scoped", "expired_roster_makes_plan_unusable",
    "withdrawal_terminal_without_pilot_delivery", "serialized_history_does_not_restore_plan",
    "all_production_blockers_stay_no_go", "final_packet_unchanged",
})
EXPECTED_SUMMARY = {"fresh_native_runs": 1, "named_signed_people": 7, "named_models": 1,
    "named_interfaces": 1, "model_queries": 0, "pilot_delivered_bytes": 0,
    "production_blockers_open": 11, "planning_review_demonstrated": True,
    "suspension_scope": "local_plan_only", "withdrawal_terminal": True,
    "expired_roster_unusable": True, "serialized_plan_restored": False,
    "agency_pilot_started": False, "external_sacro_qualified": False}


def _deny(call):
    try:
        call()
    except c.PilotError:
        return True
    return False


def exercise(output, *, profile="agency_private_cloud"):
    c.require_local(profile)
    root = io.fresh_directory(output)
    result = {"schema": "mra-local-pilot-rehearsal-exercise/v1", "status": "failed",
              "checks": [], "errors": [], "summary": {}, **c.FLAGS}
    stage = "production_refusal"
    def check(name, condition):
        result["checks"].append({"name": name, "passed": condition is True})
        if condition is not True:
            c.fail()
    try:
        check("production_refused_before_output", _deny(lambda: FixturePilotPlanService(object(), object())))
        intent = {"schema": "mra-local-pilot-intent/v1", "profile_id": "sklearn-wine", "max_rows": 128,
            "interface_id": c.INTERFACE_ID, "models": 1, "named_people": 7,
            "max_queries": 0, "max_pilot_delivered_bytes": 0,
            "starts_at": 1000, "ends_at": 1100, "agency_acceptance": "pending"}
        frozen = c.canonical_bytes(intent)
        io.exclusive_write(root / "pilot-intent.json", frozen)
        check("intent_frozen_before_assessment", not (root / "assessment").exists())
        stage = "fresh_assessment"
        observed = assess(root / "assessment", profile=profile)
        check("fresh_current_source_assessment", observed["status"] == "passed")
        pins = {key: observed["pins"][key] for key in ("manifest_sha256", "key_sha256")}
        capability = VerifiedAssessment(root / "assessment/packet",
            expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256=pins["key_sha256"], profile=profile)
        bound = capability.recheck()
        result["pins"], result["evidence"] = pins, bound
        check("exact_candidate_and_packet_bound", bound["profile_id"] == "sklearn-wine"
              and bound["max_rows"] == 128 and bound["current_authorization_checked"] is False)
        stage = "named_plan_review"
        # Identity setup only. No second fit, activation, grant or writer.
        fixture = DeliveryFixture(root / "planning-identity")
        service = FixturePilotPlanService(fixture.identity, capability, profile=profile)
        subjects = ("owner", "policy", "operator", "assessor", "releaser", "auditor", "recipient")
        roster = {subject: fixture.token(subject, expires_at=1001 if subject == "recipient" else 1240)
                  for subject in subjects}
        service.enroll_people(roster, "case-a")
        service.record_producer(fixture.token("operator"), "case-a")
        check("seven_current_signed_people_enrolled", len(roster) == 7 and not fixture.output.exists())
        plan = c.pilot_plan(candidate_sha256=bound["candidate_sha256"],
            assessment_manifest_sha256=pins["manifest_sha256"], assessment_key_sha256=pins["key_sha256"], profile=profile)
        altered = c.owned(plan); altered["binding"]["candidate_sha256"] = "b"*64
        before = service.status(fixture.token("auditor"), "case-a")
        check("scope_and_unsigned_proposals_refused", _deny(lambda: service.propose(
            fixture.token("owner"), "case-a", altered))
            and _deny(lambda: service.propose({}, "case-a", plan))
            and _deny(lambda: service.propose(fixture.token("owner"), "case-b", plan))
            and service.status(fixture.token("auditor"), "case-a")["events"] == before["events"])
        service.propose(fixture.token("owner"), "case-a", plan)
        check("owner_operator_cannot_review", all(_deny(lambda subject=subject: service.assess(
            fixture.token(subject), "case-a")) for subject in ("owner", "owner-alias", "operator")))
        service.assess(fixture.token("assessor"), "case-a")
        acknowledged = service.acknowledge(fixture.token("releaser"), "case-a")
        check("distinct_current_plan_review_is_planning_only", acknowledged["local_planning_ready"] is True
            and acknowledged["readiness"] == "no_go" and acknowledged["pilot_admission"] is False
            and not hasattr(service, "admit") and not hasattr(service, "run"))
        plan_sha = acknowledged["plan_sha256"]
        suspended = service.suspend(fixture.token("releaser"), "case-a")
        bad_resume = _deny(lambda: service.resume(fixture.token("owner"), "case-a"))
        resumed = service.resume(fixture.token("releaser"), "case-a")
        check("suspension_resume_scoped", suspended["state"] == "suspended"
            and suspended["local_planning_ready"] is False and bad_resume
            and resumed["local_planning_ready"] is True and resumed["plan_sha256"] == plan_sha)
        fixture.now = 1001  # Forward only; original recipient roster credential expires.
        expired = service.status(fixture.token("auditor"), "case-a")
        check("expired_roster_makes_plan_unusable", expired["local_planning_ready"] is False
              and expired["current_checks_satisfied"] is False and expired["plan_sha256"] == plan_sha)
        withdrawn = service.withdraw(fixture.token("releaser"), "case-a")
        check("withdrawal_terminal_without_pilot_delivery", withdrawn["state"] == "withdrawn"
            and _deny(lambda: service.resume(fixture.token("releaser"), "case-a"))
            and not fixture.output.exists() and not fixture.store.get("case-a", expected_pin=fixture.gateway.required_pin, guard=fixture.review_fixture.clock)["admissions"])
        io.exclusive_write(root / "historical-plan-records.json", c.canonical_bytes(withdrawn))
        restarted = FixturePilotPlanService(fixture.identity, capability, profile=profile)
        empty = restarted.status(fixture.token("auditor"), "case-a")
        check("serialized_history_does_not_restore_plan", empty["plan"] is None
            and empty["local_planning_ready"] is False and not empty["events"])
        check("all_production_blockers_stay_no_go", len(withdrawn["production_blockers"]) == 11
            and all(withdrawn[key] is flag for key, flag in c.FLAGS.items())
            and withdrawn["readiness"] == "no_go")
        check("final_packet_unchanged", capability.recheck() == bound
              and io.read_file(root / "pilot-intent.json") == frozen)
        result.update(summary=c.owned(EXPECTED_SUMMARY), plan_sha256=plan_sha,
                      serialized_plan_restored=False)
        if {row["name"] for row in result["checks"]} != REQUIRED_CHECKS:
            c.fail()
        result["status"] = "passed"
    except Exception:
        result["errors"].append({"stage": stage, "code": "LocalPilotStageFailed"})
    io.exclusive_write(root / "exercise-result.json", c.canonical_bytes(result))
    return result
