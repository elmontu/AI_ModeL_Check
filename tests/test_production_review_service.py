"""Actual public training plus adversarial current-review/custody regressions."""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_identity.policy import PermissionDenied
from model_release_assurance.production_review import service as module
from model_release_assurance.production_review.contracts import FLAGS, ReviewError
from model_release_assurance.production_review.rehearsal import ReviewFixture, SCOPES
from model_release_assurance.production_review.store import StoreConflict
from model_release_assurance.production_evidence.contracts import strict_json, canonical_bytes


def campaign(fixture, *, case="case-a", delegated=False, policy_expires=1240):
    key, snapshot = fixture.propose(case)
    delegation = None
    if delegated:
        delegation = fixture.delegate(key, case, expires_at=1120)
    fixture.service.approve_policy(fixture.token("delegatepolicy" if delegated else "policy", expires_at=policy_expires),
                                   case, key, delegation_id=delegation)
    return key, delegation


def complete(fixture, *, delegated=False, policy_expires=1240):
    key, delegation = campaign(fixture, delegated=delegated, policy_expires=policy_expires)
    output = fixture.root / "training"
    snapshot = fixture.service.execute(fixture.token("operator"), "case-a", key, output=output)
    return key, delegation, output, snapshot["campaigns"][key]


def final_reviews(fixture, key):
    fixture.service.assess(fixture.token("assessor"), "case-a", key)
    fixture.service.approve(fixture.token("releaser"), "case-a", key)


class ReviewServicePreapprovalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-review-service-")
        self.addCleanup(temporary.cleanup)
        self.f = ReviewFixture(Path(temporary.name))

    def test_policy_must_exist_before_native_fit_or_training_output(self):
        key, _ = self.f.propose()
        output = self.f.root / "training"
        with mock.patch.object(module.native, "run_native") as run:
            with self.assertRaises(PermissionDenied):
                self.f.service.execute(self.f.token("operator"), "case-a", key, output=output)
            run.assert_not_called()
        self.assertFalse(output.exists())
        self.assertEqual(self.f.store.get("case-a", guard=self.f.clock)["campaigns"][key]["state"], "proposed")

    def test_policy_scope_and_current_role_are_both_required(self):
        key, _ = self.f.propose()
        for token in (self.f.token("policy", scopes={"case:read"}), self.f.token("auditor")):
            with self.assertRaises(PermissionDenied): self.f.service.approve_policy(token, "case-a", key)
        self.assertIsNone(self.f.store.get("case-a", guard=self.f.clock)["campaigns"][key]["policy_approval"])

    def test_revoked_policy_delegation_cannot_start_even_with_valid_delegate_token(self):
        key, delegation = campaign(self.f, delegated=True)
        self.f.service.revoke(self.f.token("policy"), "case-a", delegation)
        with mock.patch.object(module.native, "run_native") as run:
            with self.assertRaises((PermissionDenied, StoreConflict)):
                self.f.service.execute(self.f.token("operator"), "case-a", key, output=self.f.root / "training")
            run.assert_not_called()
        self.assertIsNone(self.f.store.get("case-a", guard=self.f.clock)["campaigns"][key]["start"])

    def test_delegate_scope_cannot_be_inferred_from_approval_role(self):
        key, _ = self.f.propose()
        with self.assertRaises(PermissionDenied):
            self.f.service.delegate(self.f.token("policy", scopes=SCOPES - {"review:delegate"}), "case-a", key,
                action="policy", delegate_person_id="person-delegatepolicy", expires_at=1100)
        self.assertEqual(self.f.store.get("case-a", guard=self.f.clock)["delegations"], {})

    def test_foreign_campaign_and_case_do_not_create_policy_approval(self):
        key, _ = self.f.propose()
        with self.assertRaises(StoreConflict): self.f.service.approve_policy(self.f.token("policy"), "case-b", key)
        with self.assertRaises(PermissionDenied):
            self.f.service.approve_policy(self.f.token("policy", cases=["case-b"]), "case-a", key)
        self.assertIsNone(self.f.store.get("case-a", guard=self.f.clock)["campaigns"][key]["policy_approval"])

    def test_changed_review_head_during_execution_cannot_commit_completion(self):
        key, _ = campaign(self.f)
        snapshot = self.f.store.get("case-a", guard=self.f.clock)
        policy = snapshot["campaigns"][key]["policy"]
        payload = {"campaign_id": key, "policy_sha256": module.digest(policy), "registration_id": "a" * 32,
            **{name: "b" * 64 for name in ("registration_sha256", "candidate_sha256", "report_sha256", "artifacts_sha256",
                "envelope_sha256", "admission_sha256", "context_sha256")},
            "utility_improvement_bps": 100, "membership_auc_bps": 5000}
        def completed(*args):
            self.f.propose("case-b")  # Another committed decision changes the global CAS head.
            return payload, self.f.clock
        with mock.patch.object(module._ApprovedWorkflow, "run", return_value={"status": "review_recorded"}) as run,                 mock.patch.object(self.f.service, "_completion", side_effect=completed):
            with self.assertRaises(StoreConflict):
                self.f.service.execute(self.f.token("operator"), "case-a", key, output=self.f.root / "unused")
            run.assert_called_once()
        result = self.f.store.get("case-a", guard=self.f.clock)["campaigns"][key]
        self.assertNotEqual(result["state"], "completed")
        self.assertIsNone(result["completion"])


class ReviewCompletedBindingTests(unittest.TestCase):
    """Share one immutable genuine Wine run; each tamper is restored in finally."""
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="mra-review-completed-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.f = ReviewFixture(Path(cls.temporary.name))
        cls.key, _, cls.output, cls.campaign = complete(cls.f)
        cls.run_receipt = strict_json((cls.output / "result.json").read_bytes())
        final_reviews(cls.f, cls.key)

    def check_completion(self, *, run=None, guard=None):
        with self.f.identity._lock:
            context = self.f.service.authorization.access(self.f.token("operator"), "case-a", "start")
            return self.f.service._completion(self.output, self.campaign["policy"], context,
                                              context.recheck if guard is None else guard,
                                              self.run_receipt if run is None else run)

    def test_actual_fit_replay_and_independent_reviews_are_bound_but_non_authorizing(self):
        status = self.f.service.status(self.f.token("auditor"), "case-a", self.key)
        self.assertTrue(status["reviews_usable"])
        self.assertTrue((self.output / "native/candidate.json").is_file())
        self.assertTrue((self.output / "replay-envelope.json").is_file())
        completion = self.campaign["completion"]["payload"]
        self.assertEqual(completion["registration_id"], self.run_receipt["registration_id"])
        self.assertNotEqual(completion["registration_id"], self.key)
        self.assertEqual(completion["registration_sha256"], self.run_receipt["registration_sha256"])
        for name, expected in FLAGS.items(): self.assertIs(status[name], expected)
        self.assertEqual(self.run_receipt["review"]["status"], "production_blocked")

    def test_prior_coherent_bundle_cannot_replace_current_run_identity(self):
        for field, value in (("registration_id", "f" * 32), ("registration_sha256", "f" * 64)):
            changed = copy.deepcopy(self.run_receipt); changed[field] = value
            with self.subTest(field=field), self.assertRaises(PermissionDenied):
                self.check_completion(run=changed)
        changed = copy.deepcopy(self.run_receipt)
        changed["review"]["utility"]["candidate"] = 0.0
        with self.assertRaises(PermissionDenied): self.check_completion(run=changed)

    def test_terminal_record_and_file_matching_each_other_cannot_hide_wrong_materials(self):
        path = self.output / "registration-record.json"
        original = path.read_bytes()
        for field in ("candidate_sha256", "report_sha256", "artifacts_sha256", "evidence_envelope_sha256", "evidence_admission_sha256"):
            changed = strict_json(original); changed["completion"][field] = "f" * 64
            try:
                path.write_bytes(canonical_bytes(changed) + b"\n")
                with mock.patch.object(self.f.workflow.store, "get", return_value=changed):
                    with self.subTest(field=field), self.assertRaises(PermissionDenied): self.check_completion()
            finally:
                path.write_bytes(original)

    def test_caller_edited_admission_is_not_authority_despite_matching_summary_fields(self):
        path = self.output / "replay-admission.json"; original = path.read_bytes()
        changed = strict_json(original); changed["fixture_only"] = False
        try:
            path.write_bytes(canonical_bytes(changed) + b"\n")
            with self.assertRaises(PermissionDenied): self.check_completion()
            self.assertFalse(self.f.service.status(self.f.token("auditor"), "case-a", self.key)["reviews_usable"])
        finally:
            path.write_bytes(original)
        self.assertTrue(self.f.service.status(self.f.token("auditor"), "case-a", self.key)["reviews_usable"])

    def test_retained_candidate_byte_change_invalidates_current_review_usability(self):
        path = self.output / "native/candidate.json"; original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            self.assertFalse(self.f.service.status(self.f.token("auditor"), "case-a", self.key)["reviews_usable"])
        finally:
            path.write_bytes(original)
        self.assertTrue(self.f.service.status(self.f.token("auditor"), "case-a", self.key)["reviews_usable"])

    def test_canonical_owner_alias_and_operator_cannot_review_completed_campaign(self):
        for subject in ("owner", "owner-alias"):
            with self.subTest(subject=subject), self.assertRaises(PermissionDenied):
                self.f.service.assess(self.f.token(subject), "case-a", self.key)
        with self.assertRaises(PermissionDenied): self.f.service.approve(self.f.token("operator"), "case-a", self.key)


class ReviewServiceDeadlineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-review-deadline-")
        self.addCleanup(temporary.cleanup)
        self.f = ReviewFixture(Path(temporary.name))

    def test_revoked_policy_delegation_invalidates_completed_assessment_and_status(self):
        key, delegation, _, _ = complete(self.f, delegated=True)
        final_reviews(self.f, key)
        self.assertTrue(self.f.service.status(self.f.token("auditor"), "case-a", key)["reviews_usable"])
        self.f.service.revoke(self.f.token("policy"), "case-a", delegation)
        with self.assertRaises((PermissionDenied, StoreConflict)):
            self.f.service.assess(self.f.token("assessor"), "case-a", key)
        self.assertFalse(self.f.service.status(self.f.token("auditor"), "case-a", key)["reviews_usable"])

    def test_policy_expiry_during_final_status_read_cannot_return_usable(self):
        key, _, _, _ = complete(self.f, policy_expires=1001)
        final_reviews(self.f, key)
        original = self.f.service._case
        calls = [0]
        def slow(context):
            result = original(context); calls[0] += 1
            if calls[0] == 2: self.f.now = 1001
            return result
        with mock.patch.object(self.f.service, "_case", side_effect=slow):
            status = self.f.service.status(self.f.token("auditor"), "case-a", key)
        self.assertEqual(calls[0], 2)
        self.assertFalse(status["reviews_usable"])

    def test_evidence_expiry_after_signature_check_but_before_final_guard_denies(self):
        key, _, _, _ = complete(self.f)
        observer = self.f.service._evidence[key]
        deadline = observer.evidence_lifetime[1]
        original = self.f.workflow.store.get
        calls = [0]
        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            calls[0] += 1
            self.f.now = deadline  # Signature was checked before this retained-record read.
            return result
        with mock.patch.object(self.f.workflow.store, "get", side_effect=slow):
            with self.assertRaises(PermissionDenied): observer()
        self.assertEqual(calls[0], 1)
        self.assertFalse(self.f.service.status(self.f.token("auditor"), "case-a", key)["reviews_usable"])


if __name__ == "__main__": unittest.main()
