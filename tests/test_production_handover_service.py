"""Signed handover over the real live pilot service.

Only historical signature replay and registration parsing are explicit unit seams
reused from the pilot tests. Signed identities, canonical people, pinned middle
reads, current roles and original contexts are real. The separate rehearsal
verifies a genuine fresh assessment packet; no unit evidence claims agency use.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import unittest
from unittest import mock
import test_production_pilot_service as pilot_tests
from model_release_assurance.production_pilot.service import FixturePilotPlanService
from model_release_assurance.production_review.rehearsal import ISSUER
from model_release_assurance.production_handover import contracts as c
from model_release_assurance.production_handover import service as s

LOCAL = "local_public_fixture"
SUBJECTS = ("owner","policy","operator","assessor","releaser","auditor","recipient")

class HandoverServiceTests(unittest.TestCase):
    def setUp(self):
        self.unit = pilot_tests.PilotPlanServiceTests(methodName="runTest")
        self.unit.setUp()
        self.addCleanup(self.unit.doCleanups)
        self.f, self.evidence, self.plan = self.unit.f, self.unit.evidence, self.unit.plan
        self.pilot = self.unit.service
        self.unit.acknowledge()
        self.service = self.make()
        self.preparation = c.handover_preparation(pilot_plan=self.plan, profile=LOCAL)

    def make(self):
        return s.FixtureHandoverService(self.pilot, profile=LOCAL)

    def fresh_pilot(self, **token_changes):
        self.pilot = FixturePilotPlanService(self.f.identity, self.evidence, profile=LOCAL)
        roster = {subject:token_changes.get(subject) or self.f.token(subject) for subject in SUBJECTS}
        self.pilot.enroll_people(roster,"case-a")
        self.pilot.record_producer(self.f.token("operator"),"case-a")
        self.pilot.propose(self.f.token("owner"),"case-a",self.plan)
        self.pilot.assess(self.f.token("assessor"),"case-a")
        self.pilot.acknowledge(self.f.token("releaser"),"case-a")
        self.service = self.make()

    def propose(self):
        self.service.record_operator(self.f.token("operator"),"case-a")
        return self.service.propose(self.f.token("owner"),"case-a",self.preparation)

    def acknowledge(self, *, assessor_token=None):
        self.propose()
        self.service.assess(assessor_token or self.f.token("assessor"),"case-a")
        return self.service.acknowledge(self.f.token("releaser"),"case-a")

    def status(self):
        return self.service.status(self.f.token("auditor"),"case-a")

    def assert_no_change(self, call):
        before = c.canonical_bytes(self.service._view())
        with self.assertRaises(c.HandoverError): call()
        self.assertEqual(c.canonical_bytes(self.service._view()),before)

    def test_signed_workflow_is_preparation_only_with_open_blockers(self):
        result = self.acknowledge()
        self.assertTrue(result["local_handover_preparation_ready"])
        self.assertTrue(result["current_checks_satisfied"])
        self.assertEqual(result["readiness"],"no_go")
        self.assertEqual(len(result["production_blockers"]),11)
        self.assertEqual(result["pilot_plan_sha256"],self.pilot._plan_sha256)
        self.assertEqual(result["preparation_sha256"],c.digest(self.preparation))
        self.assertEqual([row["kind"] for row in result["events"]],
            ["operator","proposal","preparation_assessment","local_preparation_acknowledgment"])
        for key,flag in c.FLAGS.items(): self.assertIs(result[key],flag)
        self.assertIs(self.service._authorization,self.pilot._authorization)
        self.assertEqual(len(self.service._pilot_contexts),11)
        self.assertFalse(self.f.output.exists())
        for name in ("run","admit","grant","deliver","activate","restore","resume"):
            self.assertFalse(hasattr(self.service,name))
        self.assertTrue(self.status()["local_handover_preparation_ready"])

    def test_default_refuses_before_dependency_access(self):
        class Poison:
            def __getattribute__(self,name): raise AssertionError("dependency touched")
        for profile in (None,True,"agency_private_cloud","production"):
            with self.assertRaises(c.HandoverError): s.FixtureHandoverService(Poison(),profile=profile)
        with self.assertRaises(c.HandoverError): s.FixtureHandoverService(Poison())

    def test_only_exact_real_acknowledged_pilot_is_accepted(self):
        for fake in ({},self.pilot._view(),object(),object.__new__(FixturePilotPlanService)):
            with self.assertRaises(c.HandoverError): s.FixtureHandoverService(fake,profile=LOCAL)
        class Subclass(FixturePilotPlanService): pass
        with self.assertRaises(c.HandoverError):
            s.FixtureHandoverService(object.__new__(Subclass),profile=LOCAL)
        unreviewed = FixturePilotPlanService(self.f.identity,self.evidence,profile=LOCAL)
        with self.assertRaises(c.HandoverError): s.FixtureHandoverService(unreviewed,profile=LOCAL)
        self.pilot.suspend(self.f.token("releaser"),"case-a")
        with self.assertRaises(c.HandoverError): self.make()

    def test_workflow_order_and_duplicate_actions_fail_atomically(self):
        self.assert_no_change(lambda:self.service.propose(self.f.token("owner"),"case-a",self.preparation))
        self.assert_no_change(lambda:self.service.assess(self.f.token("assessor"),"case-a"))
        self.assert_no_change(lambda:self.service.acknowledge(self.f.token("releaser"),"case-a"))
        self.propose()
        self.assert_no_change(lambda:self.service.record_operator(self.f.token("operator"),"case-a"))
        self.assert_no_change(lambda:self.service.propose(self.f.token("owner"),"case-a",self.preparation))
        self.service.assess(self.f.token("assessor"),"case-a")
        self.service.acknowledge(self.f.token("releaser"),"case-a")
        self.assert_no_change(lambda:self.service.assess(self.f.token("assessor"),"case-a"))
        self.assert_no_change(lambda:self.service.acknowledge(self.f.token("releaser"),"case-a"))

    def test_operator_owner_alias_unsigned_and_forged_tokens_cannot_review(self):
        self.propose()
        for subject in ("operator","owner","owner-alias","policy","releaser"):
            self.assert_no_change(lambda subject=subject:self.service.assess(self.f.token(subject),"case-a"))
        for token in ({},{"verified":True},"",None):
            self.assert_no_change(lambda token=token:self.service.assess(token,"case-a"))
        prefix,body,signature = self.f.token("assessor").split(".")
        forged = prefix+"."+body+"."+("A" if signature[0]!="A" else "B")+signature[1:]
        self.assert_no_change(lambda:self.service.assess(forged,"case-a"))
        self.service.assess(self.f.token("assessor"),"case-a")
        for subject in ("operator","owner","assessor"):
            self.assert_no_change(lambda subject=subject:self.service.acknowledge(self.f.token(subject),"case-a"))

    def test_assessor_alias_with_release_role_is_still_same_canonical_person(self):
        foundation = self.f.review_fixture
        principals = dict(foundation.authority.principals)
        principals[(ISSUER,"assessor-alias")] = replace(principals[(ISSUER,"assessor")],subject="assessor-alias")
        foundation.update(principals=principals,grants=tuple(
            replace(grant,roles=grant.roles|{"release_authority"}) if grant.person_id=="person-assessor"
            else grant for grant in foundation.authority.grants))
        self.fresh_pilot()
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        self.assert_no_change(lambda:self.service.acknowledge(self.f.token("assessor-alias"),"case-a"))

    def test_wrong_case_scope_and_owner_identity_fail(self):
        self.service.record_operator(self.f.token("operator"),"case-a")
        for token in (self.f.token("owner",scopes={"case:read"}),self.f.token("owner",cases=["case-b"]),
                      self.f.token("operator")):
            self.assert_no_change(lambda token=token:self.service.propose(token,"case-a",self.preparation))
        self.assert_no_change(lambda:self.service.propose(self.f.token("owner"),"case-b",self.preparation))
        self.service.propose(self.f.token("owner"),"case-a",self.preparation)
        self.assert_no_change(lambda:self.service.assess(self.f.token("assessor",scopes={"case:read"}),"case-a"))

    def test_substituted_hashes_and_acceptance_claims_fail(self):
        self.service.record_operator(self.f.token("operator"),"case-a")
        for key in ("candidate_sha256","assessment_manifest_sha256","assessment_key_sha256","catalog_sha256"):
            changed = c.owned(self.preparation); changed["binding"][key]="e"*64
            self.assert_no_change(lambda changed=changed:self.service.propose(self.f.token("owner"),"case-a",changed))
        changed = c.owned(self.preparation); changed["agency_pilot_exit_passed"]=True
        self.assert_no_change(lambda:self.service.propose(self.f.token("owner"),"case-a",changed))

    def test_caller_mutation_cannot_change_owned_preparation_or_events(self):
        proposed = self.propose()
        self.preparation["capacity"]["provider"]="caller-selected"
        proposed["preparation"]["binding"]["candidate_sha256"]="e"*64
        proposed["events"][0]["actor"]["person_id"]="replacement"
        status = self.status()
        self.assertIsNone(status["preparation"]["capacity"]["provider"])
        self.assertNotEqual(status["preparation"]["binding"]["candidate_sha256"],"e"*64)
        self.assertEqual(status["events"][0]["actor"]["person_id"],"person-operator")

    def test_pilot_suspension_withdrawal_and_current_resume_control_readiness(self):
        self.acknowledge()
        self.pilot.suspend(self.f.token("releaser"),"case-a")
        stale = self.status()
        self.assertFalse(stale["current_checks_satisfied"])
        self.assertFalse(stale["local_handover_preparation_ready"])
        self.pilot.resume(self.f.token("releaser"),"case-a")
        self.assertTrue(self.status()["local_handover_preparation_ready"])
        self.pilot.withdraw(self.f.token("releaser"),"case-a")
        self.assertFalse(self.status()["local_handover_preparation_ready"])
        self.assertEqual(self.service.retire(self.f.token("releaser"),"case-a")["state"],"retired")

    def test_packet_tamper_makes_status_stale_without_mutation(self):
        self.acknowledge()
        before = c.canonical_bytes(self.service._view())
        path = self.unit.packet_root/"fixture/fixture/training/native/candidate.json"
        original = path.read_bytes()
        path.write_bytes(original+b" ")
        self.assertFalse(self.status()["current_checks_satisfied"])
        self.assertEqual(c.canonical_bytes(self.service._view()),before)
        path.write_bytes(original)
        self.assertTrue(self.status()["local_handover_preparation_ready"])

    def test_original_named_person_expiry_cannot_be_replaced_by_fresh_callers(self):
        self.fresh_pilot(recipient=self.f.token("recipient",expires_at=1001))
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        self.f.now=1001
        self.assert_no_change(lambda:self.service.acknowledge(self.f.token("releaser"),"case-a"))
        self.assertFalse(self.status()["local_handover_preparation_ready"])
        self.assertFalse(self.status()["current_checks_satisfied"])

    def test_packet_latency_crossing_window_blocks_final_atomic_install(self):
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        token = self.f.token("releaser")
        original = self.evidence.recheck
        def late():
            result = original(); self.f.now=1100
            return result
        with mock.patch.object(self.evidence,"recheck",side_effect=late):
            self.assert_no_change(lambda:self.service.acknowledge(token,"case-a"))
        self.assertIsNone(self.service._approver)
        self.assertEqual(self.status()["checked_at"],1100)

    def test_packet_latency_rechecks_original_roster_at_final_timestamp(self):
        self.fresh_pilot(recipient=self.f.token("recipient",expires_at=1001))
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        token = self.f.token("releaser")
        original = self.evidence.recheck
        def late():
            result = original(); self.f.now=1001
            return result
        with mock.patch.object(self.evidence,"recheck",side_effect=late):
            self.assert_no_change(lambda:self.service.acknowledge(token,"case-a"))

    def test_packet_latency_rechecks_new_assessor_at_final_timestamp(self):
        self.propose()
        self.service.assess(self.f.token("assessor",expires_at=1001),"case-a")
        token = self.f.token("releaser")
        original = self.evidence.recheck
        def late():
            result = original(); self.f.now=1001
            return result
        with mock.patch.object(self.evidence,"recheck",side_effect=late):
            self.assert_no_change(lambda:self.service.acknowledge(token,"case-a"))

    def test_original_and_new_contexts_use_one_final_shared_bridge(self):
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        original = self.service._authorization.recheck_many
        batches=[]
        def recheck(contexts):
            batches.append(tuple(contexts))
            return original(contexts)
        with mock.patch.object(self.service._authorization,"recheck_many",side_effect=recheck):
            self.service.acknowledge(self.f.token("releaser"),"case-a")
        final = batches[-1]
        self.assertEqual(len(final),15)
        self.assertEqual(final[:11],self.pilot._contexts())
        self.assertEqual({context.principal.person_id for context in final},{"person-"+subject for subject in SUBJECTS})

    def test_no_serialization_or_digest_after_final_authority_sample(self):
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        final = self.service._final
        sampled=[False]
        def check_last(*args,**kwargs):
            result=final(*args,**kwargs); sampled[0]=True
            return result
        patches=[]
        for name in ("canonical_bytes","owned","digest"):
            original=getattr(c,name)
            def before(value,*args,original=original,**kwargs):
                self.assertFalse(sampled[0],"serialization after final current-time sample")
                return original(value,*args,**kwargs)
            patches.append(mock.patch.object(c,name,side_effect=before))
        with mock.patch.object(self.service,"_final",side_effect=check_last),patches[0],patches[1],patches[2]:
            result=self.service.acknowledge(self.f.token("releaser"),"case-a")
        self.assertTrue(result["local_handover_preparation_ready"])

    def test_changed_pilot_state_during_packet_work_denies_before_commit(self):
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        original=self.evidence.recheck
        def suspended():
            value=original(); self.pilot._state="suspended"
            return value
        with mock.patch.object(self.evidence,"recheck",side_effect=suspended):
            self.assert_no_change(lambda:self.service.acknowledge(self.f.token("releaser"),"case-a"))

    def test_stale_evidence_people_and_window_allow_terminal_local_retirement(self):
        self.acknowledge()
        self.f.now=1100
        self.unit.packet_verify.side_effect=ValueError("missing unit packet")
        result=self.service.retire(self.f.token("releaser"),"case-a")
        self.assertEqual(result["state"],"retired")
        self.assertFalse(result["current_checks_satisfied"])
        self.assertFalse(result["local_handover_preparation_ready"])
        self.assertEqual(self.status()["events"],result["events"])
        for call in (
            lambda:self.service.record_operator(self.f.token("operator"),"case-a"),
            lambda:self.service.propose(self.f.token("owner"),"case-a",self.preparation),
            lambda:self.service.assess(self.f.token("assessor"),"case-a"),
            lambda:self.service.acknowledge(self.f.token("releaser"),"case-a"),
            lambda:self.service.retire(self.f.token("releaser"),"case-a")):
            self.assert_no_change(call)
        self.assertEqual(self.pilot._state,"acknowledged")
        self.assertTrue(self.unit.packet_root.exists())

    def test_retirement_needs_current_exact_release_authority(self):
        self.acknowledge()
        self.unit.packet_verify.side_effect=ValueError("missing unit packet")
        for subject in ("owner","operator","assessor","policy"):
            self.assert_no_change(lambda subject=subject:self.service.retire(self.f.token(subject),"case-a"))
        token=self.f.token("releaser",expires_at=1001)
        self.f.now=1001
        self.assert_no_change(lambda:self.service.retire(token,"case-a"))
        self.assertEqual(self.service.retire(self.f.token("releaser"),"case-a")["state"],"retired")

    def test_hashed_event_chain_preserves_reserved_retirement_slot(self):
        self.acknowledge()
        for index,event in enumerate(self.service._events):
            record=dict(event); actual=record.pop("sha256")
            self.assertEqual(actual,c.digest(record))
            self.assertEqual(event["sequence"],index+1)
            self.assertEqual(event["previous_event_sha256"],self.service._events[index-1]["sha256"] if index else None)
        with mock.patch.object(s,"MAX_EVENTS",len(self.service._events)+1):
            result=self.service.retire(self.f.token("releaser"),"case-a")
        self.assertLessEqual(len(result["events"]),s.MAX_EVENTS)

    def test_concurrent_acknowledgments_produce_one_atomic_event(self):
        self.propose()
        self.service.assess(self.f.token("assessor"),"case-a")
        tokens=[self.f.token("releaser"),self.f.token("releaser")]
        barrier=threading.Barrier(2)
        def attempt(token):
            barrier.wait()
            try:
                self.service.acknowledge(token,"case-a")
                return "recorded"
            except c.HandoverError:
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,tokens))
        self.assertEqual(sorted(results),["denied","recorded"])
        self.assertEqual(len(self.service._events),4)

    def test_current_key_revocation_denies_even_restrictive_action(self):
        token=self.f.token("releaser")
        self.f.trust.revoke("human-key",expected_revision=self.f.trust.revision)
        self.assert_no_change(lambda:self.service.retire(token,"case-a"))
        with self.assertRaises(c.HandoverError): self.service.status(token,"case-a")

    def test_authority_outage_fails_closed(self):
        token=self.f.token("auditor")
        self.f.review_fixture.update(available=False)
        with self.assertRaises(c.HandoverError): self.service.status(token,"case-a")

    def test_current_reader_expiry_after_packet_work_cannot_return_old_readiness(self):
        self.acknowledge()
        token=self.f.token("auditor",expires_at=1001)
        original=self.evidence.recheck
        def late():
            value=original(); self.f.now=1001
            return value
        with mock.patch.object(self.evidence,"recheck",side_effect=late),self.assertRaises(c.HandoverError):
            self.service.status(token,"case-a")

    def test_original_revision_changes_cannot_be_cured_by_fresh_callers(self):
        self.acknowledge()
        self.f.review_fixture.update(revoked_token_ids=frozenset({self.service._assessor.identity.token_id}))
        self.assertFalse(self.status()["local_handover_preparation_ready"])
        self.f.review_fixture.update(revoked_token_ids=frozenset())
        self.assertFalse(self.status()["local_handover_preparation_ready"])
        self.assertEqual(self.service.retire(self.f.token("releaser"),"case-a")["state"],"retired")

    def test_serialized_history_never_restores_current_handover(self):
        history=self.acknowledge()
        restarted=self.make()
        status=restarted.status(self.f.token("auditor"),"case-a")
        self.assertIsNone(status["preparation"])
        self.assertEqual(status["events"],[])
        self.assertEqual(status["state"],"awaiting_operator")
        self.assertFalse(status["local_handover_preparation_ready"])
        with self.assertRaises(c.HandoverError): s.FixtureHandoverService(history,profile=LOCAL)
        with self.assertRaises(c.HandoverError):
            restarted.propose(history,"case-a",history["preparation"])

    def test_outputs_omit_tokens_keys_paths_and_preserve_no_delivery(self):
        self.propose()
        tokens=[self.f.token("assessor"),self.f.token("releaser")]
        self.service.assess(tokens[0],"case-a")
        result=self.service.acknowledge(tokens[1],"case-a")
        raw=c.canonical_bytes(result)
        for token in tokens: self.assertNotIn(token.encode(),raw)
        self.assertNotIn(str(self.unit.root).encode(),raw)
        self.assertNotIn(b"PRIVATE KEY",raw)
        self.assertFalse(self.f.output.exists())
        self.assertFalse(self.f.store.get("case-a",expected_pin=self.f.gateway.required_pin,
                                         guard=self.f.review_fixture.clock)["admissions"])


    def test_clock_rollback_fails_closed(self):
        token=self.f.token("auditor")
        self.f.now=999
        with self.assertRaises(c.HandoverError): self.service.status(token,"case-a")

if __name__ == "__main__":
    unittest.main()
