"""Strict fixed-profile records, separate from scientific qualification."""
import copy
import unittest

from model_release_assurance.production_profile.contracts import (FLAGS, ProfileError, canonical_bytes,
    digest, strict_json, validate_actor, validate_plan, validate_payload, validate_pin, validate_record)


def plan_fixture():
    return {"schema": "mra-public-profile-plan/v1", "run_id": "1" * 32, "campaign_id": "2" * 32,
        "agency_id": "agency", "project_id": "project", "case_id": "case", "recipient_id": "recipient",
        "profile_id": "sklearn-wine", "seed": 20261001, "max_rows": 128, "native_policy_sha256": "a" * 64,
        "sacro_lock_sha256": "b" * 64, "sacro_recipe_sha256": "c" * 64, "implementation_sha256": "d" * 64,
        "max_external_auc_bps": 9900, "required_cases": ["target", "positive", "null"],
        "atomicity": "single_store_fixture_activation_only", **FLAGS}


def actor_fixture(person="operator"):
    return {"person_id": person, "authority_revision": 1, "credential_sha256": "e" * 64}


def delivery_pin_fixture(sequence=1, head="f" * 64):
    return {"schema": "mra-fixture-delivery-pin/v1", "store_id": "3" * 32,
            "sequence": sequence, "head_sha256": head}


def payload_fixture(stage, snapshot=None):
    snapshot = snapshot or {"stages": {"assess": {"sha256": "8" * 64}, "approve": {"sha256": "9" * 64}}}
    return {
        "native": {"campaign_id": "2" * 32, "policy_sha256": "a" * 64, "completion_sha256": "1" * 64,
                   "candidate_sha256": "2" * 64, "binding_sha256": "3" * 64, "registration_id": "4" * 32,
                   "registration_sha256": "5" * 64},
        "external": {"combined_sha256": "6" * 64, "files_sha256": "7" * 64,
                     "external_plan_sha256": "8" * 64, "external_result_sha256": "9" * 64},
        "assess": {"combined_sha256": "6" * 64, "native_assessment_sha256": "a" * 64},
        "approve": {"combined_sha256": "6" * 64,
                    "assessment_sha256": snapshot["stages"].get("assess", {}).get("sha256", "8" * 64),
                    "native_approval_sha256": "b" * 64},
        "authorize": {"combined_sha256": "6" * 64,
                      "approval_sha256": snapshot["stages"].get("approve", {}).get("sha256", "9" * 64),
                      "activation_id": "5" * 32, "activation_sha256": "c" * 64, "delivery_pin": delivery_pin_fixture()},
        "complete": {"combined_sha256": "6" * 64, "activation_id": "5" * 32,
                     "final_delivery_pin": delivery_pin_fixture(5), "delivery_summary_sha256": "d" * 64,
                     "lifecycle_sha256": "e" * 64},
    }[stage]


class ProfileContractsTests(unittest.TestCase):
    def test_fixed_plan_is_owned_and_non_authorizing(self):
        source = plan_fixture()
        parsed = validate_plan(source)
        source["required_cases"].append("other")
        self.assertEqual(parsed["required_cases"], ["target", "positive", "null"])
        for key, value in FLAGS.items():
            self.assertIs(parsed[key], value)
        self.assertEqual(strict_json(canonical_bytes(parsed)), parsed)

    def test_fixed_values_unknown_missing_and_weakened_flags(self):
        mutations = {"profile_id": "sklearn-diabetes", "max_rows": 129, "seed": True,
                     "max_external_auc_bps": 10000, "atomicity": "cross_store", "schema": "wrong",
                     "required_cases": ["target", "null"], "agency_id": "../agency", "run_id": "A" * 32,
                     "native_policy_sha256": "z" * 64}
        mutations.update({key: not value for key, value in FLAGS.items()})
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaises(ProfileError):
                validate_plan({**plan_fixture(), key: value})
        for value in ({**plan_fixture(), "extra": 1}, {key: item for key, item in plan_fixture().items() if key != "case_id"}):
            with self.assertRaises(ProfileError):
                validate_plan(value)

    def test_duplicate_nonfinite_float_huge_integer_and_bounds(self):
        bad = [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":0.1}',
               b'{"a":' + b'9' * 5000 + b'}', b'[' * 40 + b'0' + b']' * 40, b'"' + b'x' * 65536 + b'"']
        for raw in bad:
            with self.subTest(length=len(raw)), self.assertRaises(ProfileError):
                strict_json(raw)
        with self.assertRaises(ProfileError):
            canonical_bytes({"custom": object()})

    def test_actor_exact_typed(self):
        self.assertEqual(validate_actor(actor_fixture()), actor_fixture())
        for value in ({**actor_fixture(), "authority_revision": True}, {**actor_fixture(), "roles": ["admin"]}):
            with self.assertRaises(ProfileError):
                validate_actor(value)

    def test_stage_shapes_and_nested_pin_exact(self):
        for stage in ("native", "external", "assess", "approve", "authorize", "complete"):
            original = payload_fixture(stage)
            self.assertEqual(validate_payload(stage, original), original)
            with self.assertRaises(ProfileError):
                validate_payload(stage, {**original, "arbitrary": False})
        invalid = payload_fixture("authorize")
        invalid["delivery_pin"]["production_authorized"] = True
        with self.assertRaises(ProfileError):
            validate_payload("authorize", invalid)
        with self.assertRaises(ProfileError):
            validate_payload("release", {})

    def test_pin_bounds_domain_and_digest(self):
        pin = {"schema": "mra-public-profile-journal-pin/v1", "store_id": "1" * 32,
               "sequence": 1, "head_sha256": "a" * 64}
        self.assertEqual(validate_pin(pin), pin)
        for key, value in (("sequence", 0), ("sequence", 8), ("sequence", True), ("head_sha256", "0" * 64),
                           ("schema", "mra-fixture-delivery-pin/v1")):
            with self.subTest(key=key, value=value), self.assertRaises(ProfileError):
                validate_pin({**pin, key: value})

    def test_record_hash_covers_actor_payload_stage_and_time(self):
        body = {"stage": "planned", "actor": actor_fixture(), "at": 100, "payload": plan_fixture()}
        record = {**body, "sha256": digest(body)}
        self.assertEqual(validate_record(record), record)
        bad = copy.deepcopy(record)
        bad["actor"]["person_id"] = "replacement"
        with self.assertRaises(ProfileError):
            validate_record(bad)


if __name__ == "__main__":
    unittest.main()
