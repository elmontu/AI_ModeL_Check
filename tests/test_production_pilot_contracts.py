"""Pilot scope widening and caller acceptance claims cannot create authority."""
import copy
import hashlib
import unittest

from model_release_assurance.production_assessment import contracts as assessment
from model_release_assurance.production_pilot import contracts as c

LOCAL = "local_public_fixture"
PINS = {"candidate_sha256": "a" * 64,
        "assessment_manifest_sha256": "b" * 64,
        "assessment_key_sha256": "c" * 64}


def plan(**changes):
    return c.pilot_plan(**{**PINS, "profile": LOCAL, **changes})


class PilotContractTests(unittest.TestCase):
    def test_production_default_refuses_before_any_caller_value_is_inspected(self):
        class Poison:
            def __str__(self):
                raise AssertionError("Caller data was inspected")
        for profile in ("agency_private_cloud", "production", None, True, [], "local_public_fixture "):
            with self.subTest(profile=profile), self.assertRaises(c.PilotError):
                c.pilot_plan(candidate_sha256=Poison(), assessment_manifest_sha256=Poison(),
                             assessment_key_sha256=Poison(), profile=profile)
        with self.assertRaises(c.PilotError):
            c.pilot_plan(**PINS)

    def test_plan_and_validation_own_nested_inputs_without_shared_state(self):
        first = plan()
        validated = c.validate_plan(first)
        self.assertEqual(first, validated)
        first["named_users"][0]["person_id"] = "caller-person"
        first["binding"]["candidate_sha256"] = "d" * 64
        first["go_no_go"]["production_no_go"].clear()
        self.assertEqual(validated, plan())
        validated["agency"]["provider"] = "caller-provider"
        self.assertEqual(plan()["agency"]["provider"], None)
        self.assertEqual(c.digest(plan()), hashlib.sha256(c.canonical_bytes(plan())).hexdigest())

    def test_every_permanent_flag_rejects_numeric_and_boolean_clearance_claims(self):
        with self.assertRaises(TypeError):
            c.FLAGS["pilot_admission"] = True
        for key, expected in c.FLAGS.items():
            replacements = (False, 1) if expected is True else (True, 0)
            for replacement in replacements:
                changed = plan()
                changed[key] = replacement
                with self.subTest(flag=key, replacement=replacement), self.assertRaises(c.PilotError):
                    c.validate_plan(changed)
        self.assertTrue(all(value is False for key, value in c.FLAGS.items() if key != "local_public_fixture"))

    def test_all_eleven_production_blockers_stay_open_despite_local_go(self):
        valid = plan()
        self.assertEqual(len(valid["open_production_blockers"]), 11)
        self.assertEqual(valid["open_production_blockers"], list(assessment.BLOCKING_FINDING_IDS))
        self.assertEqual(valid["binding"]["catalog_sha256"], assessment.catalog_sha256())
        for index, finding in enumerate(assessment.BLOCKING_FINDING_IDS):
            for key in ("open_production_blockers",):
                changed = plan()
                changed[key].pop(index)
                with self.subTest(finding=finding), self.assertRaises(c.PilotError):
                    c.validate_plan(changed)
            changed = plan()
            changed["go_no_go"]["production_no_go"].pop(index)
            with self.assertRaises(c.PilotError):
                c.validate_plan(changed)
        for key in ("prd22_accepted", "agency_accepted", "risk_accepted", "all_checks_passed", "can_admit"):
            changed = plan()
            changed["go_no_go"][key] = True
            with self.subTest(claim=key), self.assertRaises(c.PilotError):
                c.validate_plan(changed)

    def test_model_dataset_profile_and_scientific_qualification_cannot_be_substituted(self):
        for key, value in (("profile_id", "sklearn-diabetes"), ("max_rows", 129),
                           ("seed", 20261002), ("format", "pickle"),
                           ("evidence_profile", "PRD19_native_sacro"),
                           ("external_sacro_qualified", True), ("dp_qualified", True)):
            changed = plan()
            changed["model"][key] = value
            with self.subTest(key=key), self.assertRaises(c.PilotError):
                c.validate_plan(changed)
        changed = plan()
        changed["model"]["private_data_path"] = "private-cohort.csv"
        with self.assertRaises(c.PilotError):
            c.validate_plan(changed)

    def test_named_people_roles_aliases_support_and_suspension_cannot_be_widened(self):
        mutations = [
            lambda row: row["named_users"].append({"person_id": "person-extra", "required_role": "auditor"}),
            lambda row: row["named_users"][0].update(person_id="owner-alias"),
            lambda row: row["named_users"][2].update(required_role="release_authority"),
            lambda row: row["named_users"].reverse(),
            lambda row: row["support"].update(person_id="person-owner"),
            lambda row: row["support"].update(required_role="model_owner"),
            lambda row: row["suspension"].update(person_id="person-operator"),
            lambda row: row["suspension"].update(scope="all_models_and_gateways"),
            lambda row: row.update(credential_source="caller_jwt_claims"),
        ]
        for mutation in mutations:
            changed = plan()
            mutation(changed)
            with self.assertRaises(c.PilotError):
                c.validate_plan(changed)

    def test_recipient_interface_scope_and_inherited_approval_cannot_change(self):
        mutations = [
            lambda row: row["binding"].update(agency_id="another-agency"),
            lambda row: row["binding"].update(project_id="another-project"),
            lambda row: row["binding"].update(case_id="case-b"),
            lambda row: row["recipient"].update(recipient_id="another-recipient"),
            lambda row: row["recipient"].update(person_id="person-auditor"),
            lambda row: row["interface"].update(interface_id="https_api"),
            lambda row: row["interface"].update(model_queries=1),
            lambda row: row["interface"].update(model_delivery_bytes=1),
            lambda row: row.update(expansion_policy="inherit_previous_acceptance"),
            lambda row: row.update(profile="agency_private_cloud"),
        ]
        for mutation in mutations:
            changed = plan()
            mutation(changed)
            with self.assertRaises(c.PilotError):
                c.validate_plan(changed)

    def test_every_fixed_limit_refuses_bool_float_zero_and_increase(self):
        for key, value in plan()["limits"].items():
            for replacement in (bool(value), float(value), value + 1, -1):
                changed = plan()
                changed["limits"][key] = replacement
                with self.subTest(limit=key, replacement=replacement), self.assertRaises(c.PilotError):
                    c.validate_plan(changed)

    def test_bounded_declared_windows_allow_future_start_and_nonzero_duration(self):
        for start, end in ((1000, 1100), (1000, 1001), (1005, 1080), (1099, 1100)):
            valid = plan(starts_at=start, ends_at=end)
            self.assertEqual(c.validate_plan(valid), valid)
        for start, end in ((999, 1100), (1000, 1101), (1001, 1001), (1002, 1001),
                           (True, 1100), (1000, False), (1000.0, 1100), (1000, "1100")):
            with self.subTest(start=start, end=end), self.assertRaises(c.PilotError):
                plan(starts_at=start, ends_at=end)
        changed = plan()
        changed["window"]["max_duration_seconds"] = 101
        with self.assertRaises(c.PilotError):
            c.validate_plan(changed)
        changed = plan()
        changed["window"]["activation_ttl_seconds"] = 100
        with self.assertRaises(c.PilotError):
            c.validate_plan(changed)

    def test_agency_provider_region_and_actual_owners_remain_unappointed(self):
        for key in ("provider", "region", "sponsor", "service_owner", "data_steward", "independent_assessor"):
            changed = plan()
            self.assertIsNone(changed["agency"][key])
            changed["agency"][key] = "caller-appointed"
            with self.subTest(key=key), self.assertRaises(c.PilotError):
                c.validate_plan(changed)
        changed = plan()
        changed["agency"]["status"] = "accepted"
        with self.assertRaises(c.PilotError):
            c.validate_plan(changed)

    def test_pins_are_exact_typed_external_declarations_and_not_clearance(self):
        for key in PINS:
            for replacement in ("0" * 64, "A" * 64, True, "a" * 63, ["a" * 64]):
                with self.subTest(pin=key, replacement=replacement), self.assertRaises(c.PilotError):
                    plan(**{key: replacement})
        changed = plan()
        changed["binding"]["catalog_sha256"] = "d" * 64
        with self.assertRaises(c.PilotError):
            c.validate_plan(changed)
        # Structural hash declarations cannot claim verification or acceptance.
        alternate = plan(candidate_sha256="d" * 64)
        self.assertEqual(c.validate_plan(alternate)["binding"]["candidate_sha256"], "d" * 64)
        self.assertIs(alternate["pilot_admission"], False)
        alternate["binding"]["packet_verified"] = True
        with self.assertRaises(c.PilotError):
            c.validate_plan(alternate)

    def test_exact_fields_missing_unknown_and_reordered_criteria_rejected(self):
        valid = plan()
        for key in valid:
            changed = plan()
            del changed[key]
            with self.subTest(missing=key), self.assertRaises(c.PilotError):
                c.validate_plan(changed)
        for key in ("private_data", "authorization", "allow_extra_models"):
            changed = plan()
            changed[key] = True
            with self.assertRaises(c.PilotError):
                c.validate_plan(changed)
        changed = plan()
        changed["go_no_go"]["local_plan_go"].reverse()
        with self.assertRaises(c.PilotError):
            c.validate_plan(changed)

    def test_duplicate_nonfinite_nonjson_depth_and_oversized_metadata_rejected(self):
        for raw in (b'{"pilot_admission":false,"pilot_admission":true}', b'{"count":1.0}',
                    b'{"count":NaN}', b'{"count":1e999}', b'[' * 34 + b'0' + b']' * 34,
                    b'"' + b'x' * MAX_SAFE_TEST_BYTES + b'"', '{"pilot_admission":false}'):
            with self.assertRaises(c.PilotError):
                c.strict_json(raw)
        for value in (float("nan"), (1, 2), object(), {1: "payload"}):
            with self.assertRaises(c.PilotError):
                c.canonical_bytes(value)
        for bound in (True, 0, c.MAX_BYTES + 1):
            with self.assertRaises(c.PilotError):
                c.canonical_bytes({}, max_bytes=bound)

    def test_generic_errors_do_not_expose_private_caller_content(self):
        private = "private-token-never-echo"
        with self.assertRaises(c.PilotError) as error:
            c.validate_plan({"private": private})
        self.assertNotIn(private, str(error.exception))
        with self.assertRaises(c.PilotError) as error:
            c.validate_binding({"private": private})
        self.assertNotIn(private, str(error.exception))


MAX_SAFE_TEST_BYTES = c.MAX_BYTES

if __name__ == "__main__":
    unittest.main()
