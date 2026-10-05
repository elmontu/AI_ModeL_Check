"""Durable ordering, independence, policy weakening and evidence reuse tests."""
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_review.contracts import digest
from model_release_assurance.production_review.store import ReviewStore, StoreConflict, StoreUnavailable
from test_production_review_contracts import policy_fixture, actor_fixture, completion_fixture


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1000
        self.cases = [{"agency_id": "agency", "project_id": "project", "case_id": name,
                       "submitter_person_id": "owner"} for name in ("case-a", "case-b")]
        self.store = ReviewStore.create(self.root / "reviews", cases=self.cases, guard=self.guard)
        self.policy = policy_fixture()
        self.cid = self.policy["campaign_id"]

    def guard(self):
        return self.now

    def get(self, case="case-a"):
        return self.store.get(case, guard=self.guard)

    def run_op(self, operation, payload, person, *, case="case-a", credential="a", revision=1):
        before = self.get(case)
        return self.store.apply(case, operation, payload, actor_fixture(person, credential=credential, revision=revision),
            expected_head_sha256=before["head_sha256"], guard=self.guard)

    def binding(self, policy=None):
        policy = policy or self.policy
        return {"campaign_id": policy["campaign_id"], "policy_sha256": digest(policy)}

    def proposed(self, policy=None):
        policy = policy or self.policy
        return self.run_op("propose", policy, "owner", case=policy["case_id"])

    def approved(self, policy=None, *, delegation_id=None, person="policymaker"):
        policy = policy or self.policy
        self.proposed(policy)
        return self.run_op("policy", {**self.binding(policy), "delegation_id": delegation_id}, person, case=policy["case_id"])

    def started(self, policy=None):
        policy = policy or self.policy
        self.approved(policy)
        return self.run_op("start", self.binding(policy), "operator", case=policy["case_id"])

    def completed(self, *, completion=None):
        self.started()
        return self.run_op("complete", completion or completion_fixture(self.policy), "operator")

    def assess(self, *, verdict="accept", person="assessor", credential="a", delegation_id=None):
        campaign = self.get()["campaigns"][self.cid]
        return self.run_op("assess", {"campaign_id": self.cid, "binding_sha256": campaign["binding_sha256"],
            "verdict": verdict, "delegation_id": delegation_id}, person, credential=credential)

    def approve(self, *, person="approver", credential="a", delegation_id=None):
        campaign = self.get()["campaigns"][self.cid]
        return self.run_op("approve", {"campaign_id": self.cid, "binding_sha256": campaign["binding_sha256"],
            "assessment_sha256": campaign["assessment"]["sha256"], "delegation_id": delegation_id},
            person, credential=credential)

    def delegate(self, action, person, *, delegate="delegate", expires_at=1100, delegation_id="d" * 32):
        return self.run_op("delegate", {**self.binding(), "delegation_id": delegation_id,
            "action": action, "delegate_person_id": delegate, "expires_at": expires_at}, person)

    def test_complete_workflow_remains_non_authorizing_and_reopens_exactly(self):
        self.completed()
        self.assess()
        result = self.approve()
        campaign = result["campaigns"][self.cid]
        self.assertEqual(campaign["state"], "completed")
        self.assertIsNotNone(campaign["approval"])
        self.assertFalse(result["authorization_eligible"])
        self.assertFalse(result["model_delivery"])
        reopened = ReviewStore.open(self.store.root, self.store.store_id)
        self.assertEqual(reopened.get("case-a", guard=self.guard), result)
        result["campaigns"].clear()
        self.assertIn(self.cid, self.get()["campaigns"])

    def test_durable_approval_must_precede_execution_and_start_is_single_use(self):
        self.proposed()
        with self.assertRaises(StoreConflict):
            self.run_op("start", self.binding(), "operator")
        with self.assertRaises(StoreConflict):
            self.run_op("complete", completion_fixture(), "operator")
        self.run_op("policy", {**self.binding(), "delegation_id": None}, "policymaker")
        self.run_op("start", self.binding(), "operator")
        reopened = ReviewStore.open(self.store.root, self.store.store_id)
        self.assertEqual(reopened.get("case-a", guard=self.guard)["campaigns"][self.cid]["state"], "started")
        with self.assertRaises(StoreConflict):
            self.run_op("start", self.binding(), "operator", credential="b")

    def test_owner_operator_and_all_review_roles_are_canonically_distinct(self):
        self.proposed()
        with self.assertRaises(StoreConflict):
            self.run_op("policy", {**self.binding(), "delegation_id": None}, "owner", credential="b")
        self.run_op("policy", {**self.binding(), "delegation_id": None}, "policymaker")
        for person in ("owner", "policymaker"):
            with self.assertRaises(StoreConflict):
                self.run_op("start", self.binding(), person, credential="c")
        self.run_op("start", self.binding(), "operator")
        self.run_op("complete", completion_fixture(), "operator")
        for person in ("owner", "operator", "policymaker"):
            with self.assertRaises(StoreConflict):
                self.assess(person=person, credential="e")
        self.assess()
        for person in ("owner", "operator", "policymaker", "assessor"):
            with self.assertRaises(StoreConflict):
                self.approve(person=person, credential="f")

    def test_case_scope_owner_and_campaign_ids_are_exact(self):
        with self.assertRaises(StoreConflict):
            self.run_op("propose", self.policy, "other")
        with self.assertRaises(StoreConflict):
            self.run_op("propose", self.policy, "owner", case="case-b")
        self.proposed()
        with self.assertRaises(StoreConflict):
            self.proposed(policy_fixture(case_id="case-b"))
        with self.assertRaises(StoreConflict):
            self.store.get("unknown", guard=self.guard)

    def test_policy_and_recipient_cannot_be_replaced_under_same_campaign(self):
        self.proposed()
        for change in ({"recipient_id": "other"}, {"plan_sha256": "4" * 64}, {"utility_floor_bps": 100}):
            with self.assertRaises(StoreConflict):
                self.proposed(policy_fixture(**change))
        with self.assertRaises(StoreConflict):
            self.run_op("policy", {**self.binding(), "policy_sha256": "4" * 64, "delegation_id": None}, "policymaker")

    def test_project_wide_post_start_weakening_rejected_even_new_case_or_id(self):
        strict = policy_fixture(utility_floor_bps=400, max_membership_auc_bps=6500)
        self.started(strict)
        self.run_op("fail", {**self.binding(strict), "reason": "execution_failed"}, "operator")
        for changes in ({"utility_floor_bps": 399, "max_membership_auc_bps": 6500},
                        {"utility_floor_bps": 400, "max_membership_auc_bps": 6501}):
            with self.assertRaises(StoreConflict):
                self.proposed(policy_fixture(campaign_id="3" * 32, case_id="case-b", **changes))
        stronger = policy_fixture(campaign_id="4" * 32, case_id="case-b", utility_floor_bps=500, max_membership_auc_bps=6400)
        self.proposed(stronger)

    def test_draft_created_before_stricter_project_start_cannot_bypass_floor(self):
        weak = policy_fixture(campaign_id="3" * 32, case_id="case-b", max_membership_auc_bps=9000)
        self.approved(weak)
        self.started(self.policy)
        with self.assertRaises(StoreConflict):
            self.run_op("start", self.binding(weak), "operator", case="case-b")

    def test_permanent_evidence_and_registration_reuse_denied_across_cases(self):
        self.completed()
        second = policy_fixture(campaign_id="3" * 32, case_id="case-b")
        self.started(second)
        fresh = completion_fixture(second, serial="4")
        original = completion_fixture()
        for field in ("registration_id", "registration_sha256", "envelope_sha256", "admission_sha256", "context_sha256"):
            with self.subTest(field=field), self.assertRaises(StoreConflict):
                self.run_op("complete", {**fresh, field: original[field]}, "operator", case="case-b")
        self.run_op("complete", fresh, "operator", case="case-b")

    def test_completion_wrong_operator_policy_and_repeated_result_rejected(self):
        self.started()
        for person, payload in (("other-operator", completion_fixture()),
                                ("operator", completion_fixture(policy_sha256="f" * 64))):
            with self.assertRaises(StoreConflict):
                self.run_op("complete", payload, person)
        self.run_op("complete", completion_fixture(), "operator")
        with self.assertRaises(StoreConflict):
            self.run_op("complete", completion_fixture(serial="5"), "operator", credential="b")

    def test_raw_low_auc_is_not_misclassified_as_meeting_policy(self):
        self.completed(completion=completion_fixture(membership_auc_bps=2000))
        with self.assertRaises(StoreConflict):
            self.assess()
        result = self.assess(verdict="reject")
        self.assertEqual(result["campaigns"][self.cid]["assessment"]["payload"]["verdict"], "reject")
        with self.assertRaises(StoreConflict):
            self.approve()

    def test_failed_utility_blocks_acceptance_but_retains_negative_result(self):
        self.completed(completion=completion_fixture(utility_improvement_bps=-1))
        with self.assertRaises(StoreConflict):
            self.assess()
        self.assertEqual(self.get()["campaigns"][self.cid]["completion"]["payload"]["utility_improvement_bps"], -1)

    def test_assessment_and_approval_pin_exact_bindings(self):
        self.completed()
        with self.assertRaises(StoreConflict):
            self.run_op("assess", {"campaign_id": self.cid, "binding_sha256": "a" * 64,
                "verdict": "accept", "delegation_id": None}, "assessor")
        self.assess()
        campaign = self.get()["campaigns"][self.cid]
        with self.assertRaises(StoreConflict):
            self.run_op("approve", {"campaign_id": self.cid, "binding_sha256": campaign["binding_sha256"],
                "assessment_sha256": "b" * 64, "delegation_id": None}, "approver")

    def test_fresh_review_credentials_renew_exact_payload_and_clear_dependents(self):
        self.completed()
        self.assess()
        first = self.approve()
        with self.assertRaises(StoreConflict):
            self.approve()
        renewed = self.assess(credential="b")
        self.assertIsNone(renewed["campaigns"][self.cid]["approval"])
        second = self.approve(credential="b")
        self.assertNotEqual(first["campaigns"][self.cid]["approval"]["sha256"], second["campaigns"][self.cid]["approval"]["sha256"])
        policy = self.run_op("policy", {**self.binding(), "delegation_id": None}, "policymaker", credential="b")
        self.assertIsNone(policy["campaigns"][self.cid]["assessment"])
        self.assertIsNone(policy["campaigns"][self.cid]["approval"])
        with self.assertRaises(StoreConflict):
            self.assess(verdict="reject", credential="c")

    def test_rejected_assessment_cannot_be_changed_after_policy_renewal(self):
        self.completed()
        self.assess(verdict="reject")
        self.run_op("policy", {**self.binding(), "delegation_id": None}, "policymaker", credential="b")
        with self.assertRaises(StoreConflict):
            self.assess(verdict="accept", credential="b")

    def test_scoped_delegation_success_and_nonrecursive_grant(self):
        self.proposed()
        self.delegate("policy", "policymaker")
        self.run_op("policy", {**self.binding(), "delegation_id": "d" * 32}, "delegate")
        with self.assertRaises(StoreConflict):
            self.delegate("policy", "delegate", delegate="delegate-two", delegation_id="e" * 32)
        self.run_op("start", self.binding(), "operator")
        self.run_op("complete", completion_fixture(), "operator")
        self.assertEqual(self.get()["campaigns"][self.cid]["state"], "completed")

    def test_delegation_cannot_change_action_person_campaign_or_case(self):
        self.proposed()
        self.delegate("policy", "policymaker")
        for person in ("wrong-person", "owner"):
            with self.assertRaises(StoreConflict):
                self.run_op("policy", {**self.binding(), "delegation_id": "d" * 32}, person)
        second = policy_fixture(campaign_id="3" * 32)
        self.proposed(second)
        with self.assertRaises(StoreConflict):
            self.run_op("policy", {**self.binding(second), "delegation_id": "d" * 32}, "delegate")
        with self.assertRaises(StoreConflict):
            self.run_op("policy", {**self.binding(), "delegation_id": "d" * 32}, "delegate", case="case-b")

    def test_revoked_policy_delegation_invalidates_start_and_cannot_be_recreated(self):
        self.proposed()
        self.delegate("policy", "policymaker")
        self.run_op("policy", {**self.binding(), "delegation_id": "d" * 32}, "delegate")
        self.run_op("revoke", {"delegation_id": "d" * 32}, "policymaker")
        with self.assertRaises(StoreConflict):
            self.run_op("start", self.binding(), "operator")
        with self.assertRaises(StoreConflict):
            self.delegate("policy", "policymaker", expires_at=1200)
        with self.assertRaises(StoreConflict):
            self.run_op("policy", {**self.binding(), "delegation_id": None}, "policymaker", credential="b")

    def test_revoked_policy_delegation_blocks_completion_but_failure_remains_recordable(self):
        self.proposed()
        self.delegate("policy", "policymaker")
        self.run_op("policy", {**self.binding(), "delegation_id": "d" * 32}, "delegate")
        self.run_op("start", self.binding(), "operator")
        self.run_op("revoke", {"delegation_id": "d" * 32}, "policymaker")
        with self.assertRaises(StoreConflict):
            self.run_op("complete", completion_fixture(), "operator")
        result = self.run_op("fail", {**self.binding(), "reason": "execution_failed"}, "operator")
        self.assertEqual(result["campaigns"][self.cid]["state"], "failed")
        with self.assertRaises(StoreConflict):
            self.run_op("start", self.binding(), "operator", credential="b")

    def test_revoked_assessment_delegation_blocks_approval(self):
        self.completed()
        self.delegate("assess", "assessor", delegate="assessor-delegate")
        self.assess(person="assessor-delegate", delegation_id="d" * 32)
        self.run_op("revoke", {"delegation_id": "d" * 32}, "assessor")
        with self.assertRaises(StoreConflict):
            self.approve()

    def test_delegation_expiry_is_exclusive_and_checked_after_final_validation(self):
        self.proposed()
        self.delegate("policy", "policymaker", expires_at=1001)
        original = self.store._validate
        calls = [0]
        def validate(connection):
            result = original(connection)
            calls[0] += 1
            if calls[0] == 2:
                self.now = 1001
            return result
        with patch.object(self.store, "_validate", side_effect=validate):
            with self.assertRaises(StoreConflict):
                self.store.apply("case-a", "policy", {**self.binding(), "delegation_id": "d" * 32},
                    actor_fixture("delegate"), guard=self.guard)
        self.assertIsNone(self.get()["campaigns"][self.cid]["policy_approval"])

    def test_final_authority_guard_expiry_rolls_back_after_expensive_replay(self):
        self.proposed()
        original = self.store._validate
        calls = [0]
        def validate(connection):
            result = original(connection)
            calls[0] += 1
            if calls[0] == 2:
                self.now = 1001
            return result
        def deadline():
            if self.now >= 1001:
                raise PermissionError("expired")
            return self.now
        with patch.object(self.store, "_validate", side_effect=validate):
            with self.assertRaises(PermissionError):
                self.store.apply("case-a", "policy", {**self.binding(), "delegation_id": None},
                    actor_fixture("policymaker"), guard=deadline)
        self.assertIsNone(self.get()["campaigns"][self.cid]["policy_approval"])

    def test_exact_head_cas_rejects_stale_authority_capture(self):
        before = self.get()
        self.proposed()
        with self.assertRaises(StoreConflict):
            self.store.apply("case-a", "policy", {**self.binding(), "delegation_id": None},
                actor_fixture("policymaker"), expected_head_sha256=before["head_sha256"], guard=self.guard)

    def test_clock_invalid_or_backwards_fails_closed(self):
        for now in (999, True, 1000.0):
            with self.assertRaises(StoreUnavailable):
                self.store.get("case-a", guard=lambda: now)

    def test_corruption_schema_and_wrong_identity_cannot_be_reopened(self):
        for name, sql in (("events", "DELETE FROM events"), ("schema", "CREATE TABLE unexpected (x INTEGER)")):
            path = self.root / name
            shutil.copytree(self.store.root, path)
            with closing(sqlite3.connect(path / "reviews.sqlite")) as connection:
                connection.execute(sql)
                connection.commit()
            with self.assertRaises(StoreUnavailable):
                ReviewStore.open(path, self.store.store_id)
        with self.assertRaises(StoreUnavailable):
            ReviewStore.open(self.store.root, "f" * 32)

    def test_existing_root_no_overwrite_and_no_missing_open_creation(self):
        with self.assertRaises(StoreUnavailable):
            ReviewStore.create(self.store.root, cases=self.cases, guard=self.guard)
        with self.assertRaises(StoreUnavailable):
            ReviewStore.open(self.root / "absent", self.store.store_id)
        self.assertFalse((self.root / "absent").exists())

    def test_hardlink_and_path_traversal_rejected(self):
        alias = self.root / "alias"
        os.link(self.store.root / "reviews.sqlite", alias)
        with self.assertRaises(StoreUnavailable):
            self.get()
        alias.unlink()
        with self.assertRaises(StoreUnavailable):
            ReviewStore.open(self.store.root / ".." / "reviews", self.store.store_id)


    def _child(self, operation, payload, actor, *, expected_head, mode="normal"):
        parameters = json.dumps({"root": str(self.store.root), "store_id": self.store.store_id,
            "operation": operation, "payload": payload, "actor": actor, "head": expected_head, "mode": mode})
        script = """
import json,os,sys
from model_release_assurance.production_review.store import ReviewStore,StoreConflict
p=json.loads(sys.argv[1]); store=ReviewStore.open(p['root'],p['store_id'])
if p['mode']=='before_commit':
    original=store._append
    def crash(*args,**kwargs):
        original(*args,**kwargs)
        os._exit(73)
    store._append=crash
try:
    result=store.apply('case-a',p['operation'],p['payload'],p['actor'],guard=lambda:1000,expected_head_sha256=p['head'])
except StoreConflict:
    print('conflict',flush=True)
else:
    if p['mode']=='after_commit':
        os._exit(74)
    print(json.dumps({'head':result['head_sha256'],'count':result['event_count']}),flush=True)
"""
        return subprocess.Popen([sys.executable, "-B", "-c", script, parameters],
            cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_independent_process_exact_head_race_has_one_durable_winner(self):
        head = self.get()["head_sha256"]
        children = [self._child("propose", policy, actor_fixture(), expected_head=head)
                    for policy in (self.policy, policy_fixture(campaign_id="3" * 32))]
        outputs = []
        for child in children:
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, stderr)
            outputs.append(stdout.strip())
        self.assertEqual(outputs.count("conflict"), 1)
        reopened = ReviewStore.open(self.store.root, self.store.store_id)
        result = reopened.get("case-a", guard=self.guard)
        self.assertEqual(len(result["campaigns"]), 1)
        self.assertEqual(result["event_count"], 2)

    def test_process_crash_before_and_after_start_commit_preserves_barrier(self):
        self.approved()
        head = self.get()["head_sha256"]
        for mode, code, expected in (("before_commit", 73, "approved"), ("after_commit", 74, "started")):
            child = self._child("start", self.binding(), actor_fixture("operator"), expected_head=head, mode=mode)
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, code, stdout + stderr)
            reopened = ReviewStore.open(self.store.root, self.store.store_id)
            campaign = reopened.get("case-a", guard=self.guard)["campaigns"][self.cid]
            self.assertEqual(campaign["state"], expected)
            self.assertIsNotNone(campaign["policy_approval"])
            self.assertIsNone(campaign["completion"])
            if expected == "started":
                self.assertEqual(campaign["start"]["payload"], self.binding())
                with self.assertRaises(StoreConflict):
                    reopened.apply("case-a", "start", self.binding(), actor_fixture("operator", credential="b"), guard=self.guard)

    def test_same_bytes_database_replacement_is_denied_by_existing_instance(self):
        replacement = self.root / "copy.sqlite"
        shutil.copyfile(self.store.root / "reviews.sqlite", replacement)
        os.replace(replacement, self.store.root / "reviews.sqlite")
        with self.assertRaises(StoreUnavailable):
            self.get()
        # A trusted explicit reopen can accept the unchanged exact store ID;
        # rollback resistance is a separate witness/custody requirement.
        self.assertEqual(ReviewStore.open(self.store.root, self.store.store_id).get("case-a", guard=self.guard)["campaigns"], {})

    def test_unknown_schema_and_restamped_corrupt_transition_are_rejected(self):
        path = self.root / "version"
        shutil.copytree(self.store.root, path)
        with closing(sqlite3.connect(path / "reviews.sqlite")) as connection:
            connection.execute("PRAGMA user_version=99")
            connection.commit()
        with self.assertRaises(StoreUnavailable):
            ReviewStore.open(path, self.store.store_id)
        self.proposed()
        from model_release_assurance.production_review.contracts import canonical_bytes
        with closing(sqlite3.connect(self.store.root / "reviews.sqlite")) as connection:
            raw = connection.execute("SELECT event_json FROM events WHERE sequence=2").fetchone()[0]
            event = json.loads(raw)
            event["actor"]["person_id"] = "not-the-configured-owner"
            changed = digest(event)
            connection.execute("UPDATE events SET event_sha256=?,event_json=? WHERE sequence=2", (changed, canonical_bytes(event).decode('ascii')))
            connection.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (json.dumps(changed),))
            connection.commit()
        with self.assertRaises(StoreUnavailable):
            self.get()

    def test_prior_policy_delegation_expiring_during_final_replay_blocks_start(self):
        self.proposed()
        self.delegate("policy", "policymaker", expires_at=1001)
        self.run_op("policy", {**self.binding(), "delegation_id": "d" * 32}, "delegate")
        original = self.store._validate
        calls = [0]
        def validate(connection):
            result = original(connection)
            calls[0] += 1
            if calls[0] == 2:
                self.now = 1001
            return result
        with patch.object(self.store, "_validate", side_effect=validate):
            with self.assertRaises(StoreConflict):
                self.store.apply("case-a", "start", self.binding(), actor_fixture("operator"), guard=self.guard)
        self.assertEqual(self.get()["campaigns"][self.cid]["state"], "approved")

    def test_historical_operator_cannot_return_as_reviewer_in_new_campaign(self):
        self.started()
        self.run_op("fail", {**self.binding(), "reason": "execution_failed"}, "operator")
        second = policy_fixture(campaign_id="3" * 32)
        self.proposed(second)
        with self.assertRaises(StoreConflict):
            self.run_op("policy", {**self.binding(second), "delegation_id": None}, "operator", credential="b")


if __name__ == "__main__":
    unittest.main()
