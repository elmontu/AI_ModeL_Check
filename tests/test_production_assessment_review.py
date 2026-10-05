"""Real signed current independent local reviews; historical records never grant release."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import threading
import unittest
from unittest.mock import patch

from test_production_review_authorization import AuthorizationFixture, ISSUER
from model_release_assurance.production_assessment import contracts as c
from model_release_assurance.production_assessment.review import LocalFindingReview
from model_release_assurance.production_review.authorization import ReviewAuthorization

PACKET = "a"*64
LOCAL = "local_public_fixture"


class AssessmentReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = AuthorizationFixture()
        self.service = self.make()

    def make(self, **changes):
        return LocalFindingReview(self.f.identity, **{"packet_sha256": PACKET, "agency_id":"agency",
            "project_id":"project", "case_id":"case-a", "profile":LOCAL, **changes})

    def assess(self, token=None, **changes):
        return self.service.assess(token or self.f.token("assessor"), **{"expected_packet_sha256": PACKET,
            "dispositions": c.default_dispositions(), **changes})

    def approve(self, assessment, token=None, **changes):
        return self.service.approve(token or self.f.token("approver"), **{"expected_packet_sha256":PACKET,
            "expected_assessment_sha256":c.digest(assessment), **changes})

    def status(self, token=None, **changes):
        return self.service.status(token or self.f.token("reader"), **{"expected_packet_sha256":PACKET, **changes})

    def test_real_signed_distinct_humans_complete_only_a_local_review(self):
        rows=c.default_dispositions(); rows[-1].update(disposition="accepted_for_local_fixture", justification="trusted_local_fixture_only")
        assessment=self.assess(dispositions=rows); approval=self.approve(assessment); status=self.status()
        self.assertEqual(status["status"],"local_review_complete"); self.assertTrue(status["review_usable"])
        self.assertEqual(approval["assessment_sha256"],c.digest(assessment))
        self.assertNotEqual(assessment["actor"]["person_id"],approval["actor"]["person_id"])
        self.assertEqual(status["production_blockers"],list(c.BLOCKING_FINDING_IDS))
        for item in (assessment,approval,status):
            for key,value in c.FLAGS.items(): self.assertIs(item[key],value)
        self.assertEqual(status["binding"]["packet_sha256"],PACKET)

    def test_default_production_refuses_before_identity_access_or_effects(self):
        class Poison:
            def __getattribute__(self,name): raise AssertionError("Identity touched")
        with self.assertRaises(c.AssessmentError):
            LocalFindingReview(Poison(),packet_sha256=PACKET,agency_id="agency",project_id="project",case_id="case-a")
        self.assertIsNone(self.service._assessment)

    def test_exact_packet_scope_and_assessment_digest_required(self):
        with self.assertRaises(c.AssessmentError): self.make(project_id="other-project")
        with self.assertRaises(c.AssessmentError): self.assess(expected_packet_sha256="b"*64)
        assessment=self.assess()
        with self.assertRaises(c.AssessmentError): self.approve(assessment, expected_assessment_sha256="b"*64)
        with self.assertRaises(c.AssessmentError): self.status(expected_packet_sha256="b"*64)
        self.assertIsNone(self.service._approval)

    def test_missing_signed_scope_wrong_server_role_case_and_workload_denied(self):
        for token in (self.f.token("assessor",scopes={"case:read"}), self.f.token("reader"),
                      self.f.token("assessor",cases=["case-b"]), self.f.token("worker")):
            with self.assertRaises(c.AssessmentError): self.assess(token)
        assessment=self.assess()
        with self.assertRaises(c.AssessmentError): self.approve(assessment,self.f.token("approver",scopes={"case:read"}))
        self.assertIsNone(self.service._approval)

    def test_owner_operator_and_aliases_are_not_independent_reviewers(self):
        ReviewAuthorization(self.f.identity).access(self.f.token("operator"),"case-a","start")
        for person in ("owner","owner-alias","operator","operator-alias"):
            with self.assertRaises(c.AssessmentError): self.assess(self.f.token(person))
        self.assertIsNone(self.service._assessment)

    def test_canonical_assessor_alias_cannot_approve_even_with_both_roles(self):
        principals=dict(self.f.authority.principals)
        principals[(ISSUER,"assessor-alias")]=replace(principals[(ISSUER,"assessor")],subject="assessor-alias")
        grants=tuple(replace(grant,roles=grant.roles|{"release_authority"}) if grant.person_id=="person-assessor" else grant for grant in self.f.authority.grants)
        self.f.update(principals=principals,grants=grants)
        assessment=self.assess()
        with self.assertRaises(c.AssessmentError): self.approve(assessment,self.f.token("assessor-alias"))
        self.assertIsNone(self.service._approval)

    def test_missing_or_stale_human_mfa_denied(self):
        for token in (self.f.token("assessor",acr="wrong"),self.f.token("assessor",auth_time=699)):
            with self.assertRaises(c.AssessmentError): self.assess(token)
        self.assertIsNone(self.service._assessment)

    def test_packet_records_and_dispositions_are_owned_not_caller_mutable(self):
        rows=c.default_dispositions(); assessment=self.assess(dispositions=rows)
        rows[0]["disposition"]="closed";assessment["actor"]["person_id"]="forged"
        status=self.status()
        self.assertEqual(status["assessment"]["dispositions"][0]["disposition"],"open")
        self.assertEqual(status["assessment"]["actor"]["person_id"],"person-assessor")
        status["binding"]["packet_sha256"]="f"*64
        self.assertEqual(self.status()["binding"]["packet_sha256"],PACKET)

    def test_production_blocker_closure_and_replayed_mutations_never_store(self):
        rows=c.default_dispositions();rows[0]["disposition"]="accepted_for_local_fixture"
        with self.assertRaises(c.AssessmentError): self.assess(dispositions=rows)
        assessment=self.assess()
        with self.assertRaises(c.AssessmentError): self.assess()
        self.approve(assessment)
        with self.assertRaises(c.AssessmentError): self.approve(assessment)

    def test_expired_assessor_denies_approval_without_mutation(self):
        assessment=self.assess(self.f.token("assessor",expires=1001))
        self.f.now=1001
        with self.assertRaises(c.AssessmentError): self.approve(assessment)
        self.assertIsNone(self.service._approval)
        status=self.status();self.assertFalse(status["review_usable"]);self.assertEqual(status["status"],"local_review_stale")

    def test_current_status_rechecks_both_old_participants_at_one_final_time(self):
        assessment=self.assess(self.f.token("assessor",expires=1001)); self.approve(assessment)
        original=self.service._authorization.recheck_many
        def delayed(contexts):
            if len(contexts)>1: self.f.now=1001
            return original(contexts)
        with patch.object(self.service._authorization,"recheck_many",side_effect=delayed):
            status=self.status()
        self.assertFalse(status["review_usable"]); self.assertEqual(status["checked_at"],1001)

    def test_time_advanced_by_record_validation_denies_final_mutation(self):
        token=self.f.token("assessor",expires=1001);original=c.validate_review_record
        def delayed(value):
            result=original(value);self.f.now=1001;return result
        with patch.object(c,"validate_review_record",side_effect=delayed):
            with self.assertRaises(c.AssessmentError): self.assess(token)
        self.assertIsNone(self.service._assessment)

    def test_time_advanced_during_approval_rechecks_prior_assessor(self):
        assessment=self.assess(self.f.token("assessor",expires=1001));token=self.f.token("approver")
        original=c.validate_review_record
        def delayed(value):
            result=original(value);self.f.now=1001;return result
        with patch.object(c,"validate_review_record",side_effect=delayed):
            with self.assertRaises(c.AssessmentError): self.approve(assessment,token)
        self.assertIsNone(self.service._approval)

    def test_revoked_jti_role_or_authority_revision_invalidates_retained_review(self):
        assessment=self.assess();self.approve(assessment)
        self.f.update(revoked_token_ids=frozenset({self.service._assessor.identity.token_id}))
        status=self.status();self.assertFalse(status["review_usable"])
        self.f.update(revoked_token_ids=frozenset())
        self.assertFalse(self.status()["review_usable"])
        self.assertEqual(status["assessment"],assessment)

    def test_role_removed_or_subject_disabled_denies_new_review(self):
        for change in ("role","subject"):
            self.setUp()
            if change=="role": self.f.update(grants=tuple(g for g in self.f.authority.grants if g.person_id!="person-assessor"))
            else:
                principals=dict(self.f.authority.principals)
                principals[(ISSUER,"assessor")]=replace(principals[(ISSUER,"assessor")],enabled=False)
                self.f.update(principals=principals)
            with self.assertRaises(c.AssessmentError): self.assess()

    def test_revoked_key_stale_or_unavailable_authority_fail_closed(self):
        for change in ("key","stale","outage","rollback"):
            self.setUp(); token=self.f.token("reader")
            if change=="key": self.f.trust.revoke("key",expected_revision=self.f.trust.revision)
            elif change=="stale": self.f.now=1250
            elif change=="outage": self.f.update(available=False)
            else: self.f.now=999
            with self.assertRaises(c.AssessmentError): self.status(token)

    def test_history_cannot_rehydrate_contexts_and_new_instance_starts_empty(self):
        assessment=self.assess();self.approve(assessment)
        historical=self.status()
        fresh=self.make(); status=fresh.status(self.f.token("reader"),expected_packet_sha256=PACKET)
        self.assertIsNone(status["assessment"]);self.assertFalse(status["review_usable"])
        self.assertEqual(historical["status"],"local_review_complete")
        with self.assertRaises(c.AssessmentError): fresh.assess(historical,expected_packet_sha256=PACKET,dispositions=c.default_dispositions())

    def test_concurrent_assessment_is_single_immutable_write(self):
        tokens=[self.f.token("assessor"),self.f.token("assessor")]; barrier=threading.Barrier(2)
        def attempt(token):
            barrier.wait(timeout=5)
            try: self.assess(token);return "committed"
            except c.AssessmentError:return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(attempt,tokens))
        self.assertEqual(sorted(outcomes),["committed","denied"])
        self.assertIsNotNone(self.service._assessment)

    def test_errors_and_records_never_contain_raw_token(self):
        token="private-invalid-token-never-log"
        with self.assertRaises(c.AssessmentError) as error:self.assess(token)
        self.assertNotIn(token,str(error.exception))
        signed=self.f.token("assessor");record=self.assess(signed)
        self.assertNotIn(signed,json.dumps(record));self.assertNotIn("AccessIdentity",repr(self.service))


if __name__ == "__main__":unittest.main()
