"""Strict record tests; fixture digests are format examples, not evidence."""
import copy
import unittest

from model_release_assurance.production_review.contracts import (
    FLAGS, CONTROLS, ReviewError, canonical_bytes, digest, strict_json, validate_policy,
    validate_actor, validate_case, validate_payload, completion_binding, meets_policy)


def policy_fixture(*, campaign_id="1" * 32, case_id="case-a", **changes):
    value = {"schema": "mra-fixture-review-policy/v1", "campaign_id": campaign_id,
        "agency_id": "agency", "project_id": "project", "case_id": case_id,
        "recipient_id": "public-fixture-reviewer", "profile_id": "sklearn-wine",
        **{key: char * 64 for key, char in (("source_sha256", "a"), ("data_sha256", "b"),
            ("metadata_sha256", "c"), ("plan_sha256", "d"), ("workflow_sha256", "e"),
            ("runtime_sha256", "f"), ("adapter_sha256", "9"))},
        "seed": 20261001, "max_rows": 128, "utility_floor_bps": 0,
        "max_membership_auc_bps": 7000, "required_controls": list(CONTROLS), **FLAGS}
    value.update(changes)
    return value


def actor_fixture(person="owner", *, credential="a", revision=1):
    return {"person_id": person, "authority_revision": revision, "credential_sha256": credential * 64}


def completion_fixture(policy=None, *, serial="2", **changes):
    policy = policy or policy_fixture()
    result = {"campaign_id": policy["campaign_id"], "policy_sha256": digest(policy), "registration_id": serial * 32,
        **{name: serial * 64 for name in ("registration_sha256", "candidate_sha256", "report_sha256",
            "artifacts_sha256", "envelope_sha256", "admission_sha256", "context_sha256")},
        "utility_improvement_bps": 500, "membership_auc_bps": 5500}
    result.update(changes)
    return result


class ReviewContractTests(unittest.TestCase):
    def test_policy_owned_canonical_and_fixture_only(self):
        source = policy_fixture()
        parsed = validate_policy(source)
        source["required_controls"].clear()
        self.assertEqual(parsed["required_controls"], CONTROLS)
        self.assertEqual(digest(parsed), digest(strict_json(canonical_bytes(parsed))))
        self.assertTrue(parsed["fixture_only"])
        self.assertFalse(parsed["authorization_eligible"])

    def test_each_unknown_or_missing_policy_field_rejected(self):
        policy = policy_fixture()
        with self.assertRaises(ReviewError):
            validate_policy({**policy, "education_override": True})
        for key in policy:
            with self.subTest(key=key), self.assertRaises(ReviewError):
                validate_policy({name: item for name, item in policy.items() if name != key})

    def test_scalar_bounds_types_and_no_wildcard(self):
        for key, bad in (("seed", True), ("seed", -1), ("max_rows", 127), ("max_rows", 4097),
            ("utility_floor_bps", -1), ("max_membership_auc_bps", 4999), ("max_membership_auc_bps", 10001),
            ("profile_id", "openml-arbitrary"), ("recipient_id", "*"), ("source_sha256", "A" * 64),
            ("campaign_id", "../file"), ("fixture_only", 1), ("model_delivery", True)):
            with self.subTest(key=key, bad=bad), self.assertRaises(ReviewError):
                validate_policy(policy_fixture(**{key: bad}))

    def test_control_drop_reorder_or_extra_rejected(self):
        for controls in ([], CONTROLS[:2], list(reversed(CONTROLS)), CONTROLS + ["new-tool"]):
            with self.assertRaises(ReviewError):
                validate_policy(policy_fixture(required_controls=controls))

    def test_exact_actor_and_case_contracts(self):
        self.assertEqual(validate_actor(actor_fixture()), actor_fixture())
        with self.assertRaises(ReviewError):
            validate_actor({**actor_fixture(), "role": "release_authority"})
        with self.assertRaises(ReviewError):
            validate_actor(actor_fixture(revision=True))
        case = {"agency_id": "agency", "project_id": "project", "case_id": "case-a", "submitter_person_id": "owner"}
        self.assertEqual(validate_case(case), case)
        with self.assertRaises(ReviewError):
            validate_case({**case, "allow_self_approval": True})

    def test_binding_covers_policy_and_all_completion_fields(self):
        policy = policy_fixture()
        result = completion_fixture(policy)
        original = completion_binding(policy, result)
        self.assertNotEqual(original, completion_binding(policy, {**result, "candidate_sha256": "3" * 64}))
        with self.assertRaises(ReviewError):
            completion_binding(policy_fixture(recipient_id="different"), result)

    def test_symmetric_membership_risk_and_utility_floor(self):
        policy = policy_fixture(max_membership_auc_bps=7000)
        self.assertTrue(meets_policy(policy, completion_fixture(policy, membership_auc_bps=3000)))
        self.assertFalse(meets_policy(policy, completion_fixture(policy, membership_auc_bps=2999)))
        self.assertFalse(meets_policy(policy, completion_fixture(policy, membership_auc_bps=7001)))
        self.assertFalse(meets_policy(policy, completion_fixture(policy, utility_improvement_bps=-1)))

    def test_completion_bounded_integers_only(self):
        for key, value in (("membership_auc_bps", 10001), ("membership_auc_bps", False),
                           ("utility_improvement_bps", -10001), ("utility_improvement_bps", 0.1)):
            with self.assertRaises(ReviewError):
                validate_payload("complete", completion_fixture(**{key: value}))

    def test_operations_exact_and_no_role_or_action_override(self):
        base = {"campaign_id": "1" * 32, "policy_sha256": "a" * 64}
        for op in ("start", "policy", "complete", "assess", "approve", "delegate", "revoke", "fail"):
            with self.subTest(operation=op), self.assertRaises(ReviewError):
                validate_payload(op, {**base, "override": True})
        with self.assertRaises(ReviewError):
            validate_payload("release", base)
        with self.assertRaises(ReviewError):
            validate_payload("fail", {**base, "reason": "refund"})
        self.assertEqual(validate_payload("policy", {**base, "delegation_id": None})["delegation_id"], None)

    def test_strict_json_rejects_duplicate_nonfinite_float_huge_integer_and_depth(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":0.5}',
                    b'{"a":' + b'9' * 5000 + b'}', b'[' * 30 + b'0' + b']' * 30):
            with self.assertRaises(ReviewError):
                strict_json(raw)
        with self.assertRaises(ReviewError):
            strict_json(b'"' + b'a' * 65536 + b'"')

    def test_native_types_cannot_coerce_or_mutate(self):
        policy = policy_fixture()
        policy["required_controls"] = tuple(CONTROLS)
        with self.assertRaises(ReviewError):
            validate_policy(policy)
        with self.assertRaises(ReviewError):
            canonical_bytes({"value": object()})


if __name__ == "__main__":
    unittest.main()
