"""Decision and DP-accounting semantics of the pure export protocol planner."""

from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from model_release_assurance.export_poc.protocol import plan_export
from model_release_assurance.export_poc.store import ExportDenied


def history(count=0, revoked=()):
    """Public status fixture only: no training, private records or noise draws."""
    releases = []
    candidates = []
    for stage in range(1, count + 1):
        route = "first" if stage == 1 else "retained-state"
        releases.append({
            "request_id": f"request-{stage}", "release_id": str(stage) * 32,
            "stage": stage, "route": route, "revision": stage,
            "artifact_sha256": str(stage) * 64,
            "parent_artifact_sha256": None if stage == 1 else "1" * 64,
            "privacy_ratio": 2 ** stage, "history_ratio": 2 ** stage,
            "delta": 0, "status": "committed", "scope": "fixed-synthetic-fixture-only",
            "revoked": stage in revoked,
        })
        candidates.append({"request_id": f"request-{stage}", "stage": stage, "route": route,
                           "base_revision": stage - 1, "status": "committed", "stale": False})
    return {"revision": count + len(revoked), "privacy_ratio": 2 ** count, "history_ratio": 2 ** count,
            "delta": 0, "candidates": candidates, "releases": releases,
            "scope": "fixed-synthetic-fixture-only", "agency_deployed": False,
            "mechanism_source_sha256": "a" * 64}


class ExportProtocolTests(unittest.TestCase):
    def denied(self, code, value, route):
        with self.assertRaises(ExportDenied) as caught:
            plan_export(value, route)
        self.assertEqual(caught.exception.code, code)

    def test_first_stage_is_an_initial_protected_training_plan(self):
        plan = plan_export(history(), "first")
        self.assertTrue(plan["supported"])
        self.assertTrue(plan["ready"])
        self.assertIsNone(plan["block_reason"])
        self.assertEqual(plan["current_history_ratio"], 1)
        self.assertEqual(plan["current_epsilon"], 0)
        self.assertEqual(plan["proposed_history_ratio"], 2)
        self.assertEqual(plan["proposed_epsilon"], math.log(2))
        self.assertEqual(plan["stage"], 1)
        self.assertEqual(plan["delta"], 0)
        self.assertFalse(plan["can_authorize"])

    def test_a_complete_history_cannot_be_reset_by_first_route_or_revocation(self):
        for count, revoked in ((1, ()), (1, (1,)), (2, ()), (2, (1, 2))):
            with self.subTest(count=count, revoked=revoked):
                plan = plan_export(history(count, revoked), "first")
                self.assertTrue(plan["supported"])
                self.assertFalse(plan["ready"])
                self.assertEqual(plan["block_reason"], "history_not_empty")
                self.assertEqual(plan["current_history_ratio"], 2 ** count)
                self.assertIsNone(plan["proposed_history_ratio"])
                self.assertIsNone(plan["proposed_epsilon"])

    def test_all_second_routes_require_one_first_release_and_exhaust_after_second(self):
        for route in ("retained-state", "independent", "central-count"):
            for count in (0, 1, 2):
                with self.subTest(route=route, count=count):
                    plan = plan_export(history(count), route)
                    self.assertEqual(plan["ready"], count == 1)
                    self.assertEqual(plan["stage"], 2)
                    self.assertEqual(plan["proposed_history_ratio"], 4 if count == 1 else None)
                    self.assertEqual(plan["block_reason"], None if count == 1 else
                                     "first_release_required" if count == 0 else "history_complete")

    def test_joint_extension_is_not_described_as_independent_per_step_budget(self):
        plan = plan_export(history(1), "retained-state")
        self.assertEqual(plan["accounting_method"], "complete-history-joint-certificate")
        self.assertEqual(plan["protocol_family"], "jointly-certified-extension")
        self.assertEqual((plan["current_history_ratio"], plan["proposed_history_ratio"]), (2, 4))
        self.assertEqual(plan["proposed_epsilon"], math.log(4))
        self.assertIn("does not assign an independent", plan["privacy_cost_interpretation"])
        self.assertIn("reconstructs X", plan["required_private_access"])

    def test_independent_and_central_routes_use_composition_with_different_access(self):
        independent = plan_export(history(1), "independent")
        central = plan_export(history(1), "central-count")
        self.assertEqual(independent["accounting_method"], "sequential-composition")
        self.assertEqual(central["accounting_method"], "sensitivity-one-counts-and-sequential-composition")
        self.assertEqual(central["protocol_family"], "direct-private-training")
        self.assertIn("not a general DP-SGD adapter", central["privacy_cost_interpretation"])
        self.assertEqual(independent["proposed_history_ratio"], central["proposed_history_ratio"])

    def test_reuse_returns_latest_release_without_new_stage_or_cost(self):
        for count in (1, 2):
            plan = plan_export(history(count), "reuse")
            self.assertTrue(plan["ready"])
            self.assertIsNone(plan["stage"])
            self.assertFalse(plan["model_bytes_change"])
            self.assertEqual(plan["reuse_release_id"], str(count) * 32)
            self.assertEqual(plan["current_history_ratio"], plan["proposed_history_ratio"])
            self.assertEqual(plan["current_epsilon"], plan["proposed_epsilon"])
            self.assertIn("does not retrain", plan["privacy_cost_interpretation"])

    def test_reuse_without_commit_is_blocked(self):
        plan = plan_export(history(), "reuse")
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["block_reason"], "no_committed_release")
        self.assertIsNone(plan["reuse_release_id"])
        self.assertIsNone(plan["proposed_history_ratio"])

    def test_revoked_latest_release_is_not_replaced_by_older_unrevoked_release(self):
        plan = plan_export(history(2, (2,)), "reuse")
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["block_reason"], "latest_release_revoked")
        self.assertIsNone(plan["reuse_release_id"])
        self.assertEqual(plan["current_history_ratio"], 4)

    def test_revoking_first_does_not_block_valid_second_or_refund_prior_cost(self):
        plan = plan_export(history(1, (1,)), "central-count")
        self.assertTrue(plan["ready"])
        self.assertEqual(plan["history_revision"], 2)
        self.assertEqual((plan["current_history_ratio"], plan["proposed_history_ratio"]), (2, 4))
        plan = plan_export(history(2, (1,)), "reuse")
        self.assertTrue(plan["ready"])
        self.assertEqual(plan["reuse_release_id"], "2" * 32)

    def test_planning_is_pure_and_never_invokes_a_mechanism(self):
        snapshot = history(1)
        original = deepcopy(snapshot)
        with patch("model_release_assurance.export_poc.mechanism.first_release", side_effect=AssertionError("draw")), \
             patch("model_release_assurance.export_poc.mechanism.next_release", side_effect=AssertionError("draw")):
            for route in ("first", "reuse", "retained-state", "independent", "central-count"):
                result = plan_export(snapshot, route)
                self.assertFalse(result["can_authorize"])
                json.dumps(result, allow_nan=False)
        self.assertEqual(snapshot, original)

    def test_unknown_route_is_reported_without_any_privacy_proposal(self):
        plan = plan_export(history(1), "dp-sgd")
        self.assertFalse(plan["supported"])
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["block_reason"], "unsupported_route")
        self.assertIsNone(plan["stage"])
        self.assertIsNone(plan["proposed_history_ratio"])
        self.assertFalse(plan["model_bytes_change"])

    def test_nonidentifier_routes_are_rejected_without_echoing_private_values(self):
        for route in (None, {"raw_records": [1, 0]}, ["first"], "secret citizen record", "a" * 65):
            self.denied("invalid_request", history(), route)

    def test_private_fields_are_rejected_at_every_input_level(self):
        cases = []
        top = history(1)
        top["private_state"] = {"X": [1]}
        cases.append(top)
        candidate = history(1)
        candidate["candidates"][0]["artifact_sha256"] = "b" * 64
        cases.append(candidate)
        receipt = history(1)
        receipt["releases"][0]["noise_seed"] = 123
        cases.append(receipt)
        for snapshot in cases:
            self.denied("invalid_history", snapshot, "reuse")

    def test_ratio_revision_and_stage_claims_must_agree(self):
        for field, value in (("history_ratio", 1), ("privacy_ratio", 4), ("revision", 0),
                             ("revision", True), ("delta", False), ("scope", "agency-data")):
            snapshot = history(1)
            snapshot[field] = value
            self.denied("invalid_history", snapshot, "retained-state")
        snapshot = history(1)
        snapshot["releases"][0]["stage"] = 2
        self.denied("invalid_history", snapshot, "retained-state")

    def test_missing_or_duplicate_receipts_and_candidates_are_rejected(self):
        missing = history(1)
        missing["candidates"] = []
        self.denied("invalid_history", missing, "reuse")
        duplicate = history(1)
        duplicate["candidates"].append(deepcopy(duplicate["candidates"][0]))
        self.denied("invalid_history", duplicate, "reuse")
        orphan = history()
        orphan["candidates"] = history(1)["candidates"]
        self.denied("invalid_history", orphan, "first")

    def test_parent_mismatch_cannot_be_planned_as_reuse(self):
        snapshot = history(2)
        snapshot["releases"][1]["parent_artifact_sha256"] = "f" * 64
        self.denied("invalid_history", snapshot, "reuse")

    def test_valid_stale_prepared_candidate_does_not_erase_history(self):
        snapshot = history(1)
        snapshot["candidates"].append({"request_id": "older", "stage": 1, "route": "first",
                                       "base_revision": 0, "status": "prepared", "stale": True})
        self.assertTrue(plan_export(snapshot, "retained-state")["ready"])
        self.assertFalse(plan_export(snapshot, "first")["ready"])
        snapshot["candidates"][-1]["stale"] = False
        self.denied("invalid_history", snapshot, "retained-state")

    def test_revocation_before_second_commit_is_a_valid_distinct_revision(self):
        snapshot = history(2, (1,))
        snapshot["releases"][1]["revision"] = 3
        snapshot["candidates"][1]["base_revision"] = 2
        self.assertTrue(plan_export(snapshot, "reuse")["ready"])
        snapshot["releases"][0]["revoked"] = False
        snapshot["revision"] = 2
        self.denied("invalid_history", snapshot, "reuse")

    def test_invalid_shapes_are_export_denials_not_type_errors(self):
        for snapshot in (None, [], {}, {"private_state": [1, 0]}):
            self.denied("invalid_history", snapshot, "first")
        for key, value in (("releases", {}), ("candidates", None), ("revision", "0")):
            snapshot = history()
            snapshot[key] = value
            self.denied("invalid_history", snapshot, "first")
        for key, value in (("route", {}), ("request_id", []), ("revoked", 1)):
            snapshot = history(1)
            snapshot["releases"][0][key] = value
            self.denied("invalid_history", snapshot, "reuse")


if __name__ == "__main__":
    unittest.main()
