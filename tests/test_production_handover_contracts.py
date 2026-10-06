"""Exact local preparation scope; no caller measurements or agency acceptance."""
from __future__ import annotations
import unittest
from model_release_assurance.production_pilot import contracts as pilot
from model_release_assurance.production_handover import contracts as c
LOCAL = "local_public_fixture"

def plan(**changes):
    return pilot.pilot_plan(candidate_sha256=changes.pop("candidate_sha256", "a"*64),
        assessment_manifest_sha256=changes.pop("assessment_manifest_sha256", "b"*64),
        assessment_key_sha256=changes.pop("assessment_key_sha256", "c"*64),
        profile=LOCAL, **changes)

def preparation():
    return c.handover_preparation(pilot_plan=plan(), profile=LOCAL)

class HandoverContractTests(unittest.TestCase):
    def reject(self, value):
        with self.assertRaises(c.HandoverError):
            c.validate_preparation(value, pilot_plan=plan())

    def test_default_refuses_before_dependency_access(self):
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError("dependency touched")
        for profile in (None, True, "agency_private_cloud", "production", ""):
            with self.subTest(profile=profile), self.assertRaises(c.HandoverError):
                c.handover_preparation(pilot_plan=Poison(), profile=profile)
        with self.assertRaises(c.HandoverError):
            c.handover_preparation(pilot_plan=Poison())

    def test_exact_owned_bounded_preparation_and_original_window(self):
        source = plan(starts_at=1005, ends_at=1080)
        value = c.handover_preparation(pilot_plan=source, profile=LOCAL)
        self.assertEqual(c.validate_preparation(value, pilot_plan=source), value)
        self.assertEqual(value["window"], source["window"])
        self.assertEqual(value["pilot_plan_sha256"], c.digest(source))
        self.assertEqual(value["binding"], source["binding"])
        self.assertLess(len(c.canonical_bytes(value)), c.MAX_BYTES)
        source["binding"]["candidate_sha256"] = "e"*64
        self.assertEqual(value["binding"]["candidate_sha256"], "a"*64)

    def test_agency_pilot_exit_and_handover_never_accepted(self):
        value = preparation()
        self.assertEqual(value["exit_review"]["agency_pilot_status"], "not_started")
        for key in ("agency_exit_review_status", "operational_transfer_status", "agency_acceptance"):
            self.assertEqual(value["exit_review"][key], "pending")
            changed = preparation(); changed["exit_review"][key] = "accepted"
            self.reject(changed)
        for key, flag in c.FLAGS.items():
            self.assertIs(value[key], flag)
            changed = preparation(); changed[key] = not flag
            self.reject(changed)

    def test_all_eleven_blockers_stay_open_in_both_locations(self):
        self.assertEqual(len(preparation()["open_production_blockers"]), 11)
        for index, finding in enumerate(pilot.assessment.BLOCKING_FINDING_IDS):
            for path in ("top", "exit"):
                changed = preparation()
                target = changed["open_production_blockers"] if path == "top" else changed["exit_review"]["production_no_go"]
                target.pop(index)
                with self.subTest(finding=finding, path=path):
                    self.reject(changed)

    def test_capacity_and_cost_unknowns_never_become_zero_or_qualified(self):
        for section in ("capacity", "cost"):
            for key, original in preparation()[section].items():
                if original is None:
                    for replacement in (0, True, "approved"):
                        changed = preparation(); changed[section][key] = replacement
                        self.reject(changed)
        for section, key in (("cost", "cloud_price_verified"), ("capacity", "population_inference"),
                             ("capacity", "local_measurements_replayed")):
            changed = preparation(); changed[section][key] = True
            self.reject(changed)
        changed = preparation(); changed["capacity"]["observed_throughput"] = 999
        self.reject(changed)

    def test_support_maintenance_retention_retirement_are_fixed_declarations(self):
        mutations = [("support","person_id","person-owner"), ("support","agency_service_owner","appointed"),
            ("support","on_call_service_active",True), ("support","external_messages_sent",True),
            ("maintenance","review_cadence_days",8), ("maintenance","schedule_active",True),
            ("maintenance","authority_or_evidence_ttl_extended",True),
            ("retention","agency_retention_period_days",30), ("retention","agency_legal_hold_status","cleared"),
            ("retention","automatic_deletion_enabled",True), ("retirement","scope","all_pilots"),
            ("retirement","terminal",False), ("retirement","gateway_or_pilot_revocation_performed",True),
            ("retirement","evidence_deleted",True)]
        for section, key, replacement in mutations:
            changed = preparation(); changed[section][key] = replacement
            with self.subTest(section=section, key=key): self.reject(changed)
        changed = preparation(); changed["maintenance"]["required_change_reviews"].pop()
        self.reject(changed)

    def test_model_recipient_interface_and_no_execution_scope(self):
        for section,key,replacement in [("model","profile_id","sklearn-diabetes"), ("model","dp_qualified",True),
            ("recipient","person_id","person-auditor"), ("interface","model_queries",1),
            ("binding","case_id","case-b"), ("binding","catalog_sha256","d"*64)]:
            changed = preparation(); changed[section][key] = replacement
            self.reject(changed)
        for key, original in preparation()["limits"].items():
            for replacement in (bool(original), float(original), original+1, -1):
                changed = preparation(); changed["limits"][key] = replacement
                self.reject(changed)

    def test_original_hashes_window_and_criteria_cannot_change(self):
        for key in ("candidate_sha256","assessment_manifest_sha256","assessment_key_sha256"):
            changed = preparation(); changed["binding"][key] = "e"*64
            self.reject(changed)
        for key,value in (("pilot_plan_sha256","e"*64),):
            changed = preparation(); changed[key] = value
            self.reject(changed)
        changed = preparation(); changed["window"]["ends_at"] = 1101
        self.reject(changed)
        changed = preparation(); changed["exit_review"]["local_preparation_criteria"].reverse()
        self.reject(changed)
        with self.assertRaises(c.HandoverError):
            c.validate_preparation(preparation(), pilot_plan=plan(candidate_sha256="e"*64))

    def test_exact_fields_missing_unknown_and_inherited_permission_refuse(self):
        for key in preparation():
            changed = preparation(); changed.pop(key)
            self.reject(changed)
        for key in ("allow_private_data","authorization","all_checks_passed","risk_accepted"):
            changed = preparation(); changed[key] = True
            self.reject(changed)
        changed = preparation(); changed["credential_source"] = "caller_jwt_claims"
        self.reject(changed)
        changed = preparation(); changed["restart_policy"] = "restore_previous_approval"
        self.reject(changed)

    def test_strict_json_duplicate_nonfinite_depth_and_oversized_content(self):
        for raw in (b'{"ready":false,"ready":true}', b'{"n":1.0}', b'{"n":NaN}',
                    b'['*34+b'0'+b']'*34, b'"'+b'x'*c.MAX_BYTES+b'"', "{}"):
            with self.assertRaises(c.HandoverError): c.strict_json(raw)
        for value in (float("nan"), (1,2), object(), {1:"value"}):
            with self.assertRaises(c.HandoverError): c.canonical_bytes(value)
        for bound in (True, 0, c.MAX_BYTES+1):
            with self.assertRaises(c.HandoverError): c.canonical_bytes({}, max_bytes=bound)

    def test_generic_errors_do_not_echo_private_content(self):
        with self.assertRaises(c.HandoverError) as error:
            c.validate_preparation({"private":"never-echo-private-token"}, pilot_plan=plan())
        self.assertNotIn("never-echo-private-token", str(error.exception))

if __name__ == "__main__":
    unittest.main()
