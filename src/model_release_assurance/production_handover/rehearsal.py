"""Fresh public-evidence exit-review and handover preparation, never agency go-live."""
from __future__ import annotations
from ..production_assessment.rehearsal import exercise as assess
from ..production_capacity import io
from ..production_delivery.rehearsal import DeliveryFixture
from ..production_pilot import contracts as pilot
from ..production_pilot.evidence import VerifiedAssessment
from ..production_pilot.service import FixturePilotPlanService
from . import contracts as c
from .service import FixtureHandoverService

REQUIRED_CHECKS = frozenset({
    "production_refused_before_output", "intent_frozen_before_assessment",
    "fresh_current_source_assessment", "acknowledged_exact_pilot_required",
    "capacity_cost_and_agency_exit_pending", "scope_and_unsigned_proposals_refused",
    "owner_operator_cannot_review", "independent_current_preparation_acknowledged",
    "suspended_pilot_blocks_preparation", "resume_preserves_exact_scope",
    "expired_original_roster_blocks_preparation", "local_retirement_terminal",
    "serialized_history_cannot_restore_preparation", "historical_records_retained",
    "all_production_blockers_stay_open", "final_packet_and_intent_unchanged",
})
EXPECTED_SUMMARY = {
    "fresh_native_runs": 1, "named_signed_people": 7, "named_models": 1,
    "model_queries": 0, "pilot_delivered_bytes": 0, "production_blockers_open": 11,
    "independent_preparation_review_demonstrated": True,
    "capacity_agency_qualified": False, "cloud_prices_verified": False,
    "agency_pilot_started": False, "agency_pilot_exit_accepted": False,
    "operational_handover_accepted": False, "expired_roster_unusable": True,
    "local_retirement_terminal": True, "serialized_handover_restored": False,
}


def _deny(call):
    try:
        call()
    except (c.HandoverError, pilot.PilotError):
        return True
    return False


def exercise(output, *, profile="agency_private_cloud"):
    c.require_local(profile)
    root = io.fresh_directory(output)
    result = {"schema": "mra-local-handover-exercise/v1", "status": "failed",
              "checks": [], "errors": [], "summary": {}, **c.FLAGS}
    stage = "production_refusal"
    def check(name, condition):
        result["checks"].append({"name": name, "passed": condition is True})
        if condition is not True:
            raise c.HandoverError("Local handover stage incomplete")
    try:
        check("production_refused_before_output", _deny(lambda: FixtureHandoverService(object())))
        intent = {"schema": "mra-local-handover-intent/v1", "profile_id": "sklearn-wine",
            "max_rows": 128, "interface_id": pilot.INTERFACE_ID,
            "review_scope": "exit_review_and_operational_handover_preparation_only",
            "max_queries": 0, "max_pilot_delivered_bytes": 0,
            "agency_pilot_started": False, "agency_acceptance": "pending"}
        frozen = c.canonical_bytes(intent)
        io.exclusive_write(root / "handover-intent.json", frozen)
        check("intent_frozen_before_assessment", not (root / "assessment").exists())
        stage = "fresh_assessment"
        observed = assess(root / "assessment", profile=profile)
        check("fresh_current_source_assessment", observed["status"] == "passed")
        pins = {key: observed["pins"][key] for key in ("manifest_sha256", "key_sha256")}
        capability = VerifiedAssessment(root / "assessment/packet",
            expected_manifest_sha256=pins["manifest_sha256"], expected_key_sha256=pins["key_sha256"], profile=profile)
        bound = capability.recheck()
        result.update(pins=pins, evidence=bound)
        stage = "pilot_plan"
        fixture = DeliveryFixture(root / "identity")
        service = FixturePilotPlanService(fixture.identity, capability, profile=profile)
        check("acknowledged_exact_pilot_required", _deny(lambda: FixtureHandoverService(service, profile=profile)))
        subjects = ("owner", "policy", "operator", "assessor", "releaser", "auditor", "recipient")
        roster = {subject: fixture.token(subject, expires_at=1001 if subject == "recipient" else 1240)
                  for subject in subjects}
        service.enroll_people(roster, "case-a")
        service.record_producer(fixture.token("operator"), "case-a")
        plan = pilot.pilot_plan(candidate_sha256=bound["candidate_sha256"],
            assessment_manifest_sha256=pins["manifest_sha256"], assessment_key_sha256=pins["key_sha256"], profile=profile)
        service.propose(fixture.token("owner"), "case-a", plan)
        service.assess(fixture.token("assessor"), "case-a")
        acknowledged_plan = service.acknowledge(fixture.token("releaser"), "case-a")
        stage = "handover_preparation"
        handover = FixtureHandoverService(service, profile=profile)
        preparation = c.handover_preparation(pilot_plan=plan, profile=profile)
        check("capacity_cost_and_agency_exit_pending", preparation == c.validate_preparation(preparation, pilot_plan=plan)
              and all(preparation[key] is flag for key, flag in c.FLAGS.items()))
        handover.record_operator(fixture.token("operator"), "case-a")
        altered = c.owned(preparation); altered["pilot_plan_sha256"] = "f" * 64
        before = handover.status(fixture.token("auditor"), "case-a")
        check("scope_and_unsigned_proposals_refused", _deny(lambda: handover.propose(
            fixture.token("owner"), "case-a", altered))
            and _deny(lambda: handover.propose({}, "case-a", preparation))
            and _deny(lambda: handover.propose(fixture.token("owner"), "case-b", preparation))
            and handover.status(fixture.token("auditor"), "case-a")["events"] == before["events"])
        handover.propose(fixture.token("owner"), "case-a", preparation)
        check("owner_operator_cannot_review", all(_deny(lambda subject=subject: handover.assess(
            fixture.token(subject), "case-a")) for subject in ("owner", "owner-alias", "operator")))
        handover.assess(fixture.token("assessor"), "case-a")
        acknowledged = handover.acknowledge(fixture.token("releaser"), "case-a")
        check("independent_current_preparation_acknowledged",
            acknowledged["local_handover_preparation_ready"] is True
            and acknowledged["readiness"] == "no_go"
            and all(not hasattr(handover, name) for name in ("run", "admit", "grant", "deliver", "activate", "restore")))
        service.suspend(fixture.token("releaser"), "case-a")
        suspended = handover.status(fixture.token("auditor"), "case-a")
        check("suspended_pilot_blocks_preparation", suspended["local_handover_preparation_ready"] is False)
        service.resume(fixture.token("releaser"), "case-a")
        resumed = handover.status(fixture.token("auditor"), "case-a")
        check("resume_preserves_exact_scope", resumed["local_handover_preparation_ready"] is True
            and resumed["preparation_sha256"] == acknowledged["preparation_sha256"]
            and resumed["pilot_plan_sha256"] == acknowledged_plan["plan_sha256"])
        fixture.now = 1001
        expired = handover.status(fixture.token("auditor"), "case-a")
        check("expired_original_roster_blocks_preparation", expired["local_handover_preparation_ready"] is False
              and expired["current_checks_satisfied"] is False)
        stage = "local_retirement"
        retired = handover.retire(fixture.token("releaser"), "case-a")
        check("local_retirement_terminal", retired["state"] == "retired"
            and retired["local_handover_preparation_ready"] is False
            and _deny(lambda: handover.acknowledge(fixture.token("releaser"), "case-a")))
        io.exclusive_write(root / "historical-handover-records.json", c.canonical_bytes(retired))
        fresh_pilot = FixturePilotPlanService(fixture.identity, capability, profile=profile)
        check("serialized_history_cannot_restore_preparation", _deny(lambda: FixtureHandoverService(retired, profile=profile))
            and _deny(lambda: FixtureHandoverService(fresh_pilot, profile=profile)))
        check("historical_records_retained", io.read_file(root / "historical-handover-records.json") == c.canonical_bytes(retired)
              and not fixture.output.exists()
              and not fixture.store.get("case-a", expected_pin=fixture.gateway.required_pin,
                                        guard=fixture.review_fixture.clock)["admissions"])
        check("all_production_blockers_stay_open", len(retired["production_blockers"]) == 11
              and retired["readiness"] == "no_go" and all(retired[key] is flag for key, flag in c.FLAGS.items()))
        check("final_packet_and_intent_unchanged", capability.recheck() == bound
              and io.read_file(root / "handover-intent.json") == frozen)
        result.update(summary=c.owned(EXPECTED_SUMMARY), plan_sha256=acknowledged_plan["plan_sha256"],
            preparation=preparation, preparation_sha256=c.digest(preparation), serialized_handover_restored=False)
        if {row["name"] for row in result["checks"]} != REQUIRED_CHECKS:
            raise c.HandoverError("Incomplete handover checks")
        result["status"] = "passed"
    except Exception:
        result["errors"].append({"stage": stage, "code": "LocalHandoverStageFailed"})
    io.exclusive_write(root / "exercise-result.json", c.canonical_bytes(result))
    return result
