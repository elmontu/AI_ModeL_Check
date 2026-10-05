"""Signed plan-state tests; mocked historical packet cryptography is explicit.

The actual VerifiedAssessment constructor and pinned middle reads are exercised.
Only signature replay and the registration parser are unit seams; these tests
never assert that this deliberately tiny packet is production or scientific evidence.
The parent rehearsal separately creates and verifies a real fresh packet.
"""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from model_release_assurance.production_assessment import probes
from model_release_assurance.production_delivery.rehearsal import DeliveryFixture
from model_release_assurance.production_pilot import contracts as c
from model_release_assurance.production_pilot import evidence as e
from model_release_assurance.production_pilot import service as s
from model_release_assurance.production_review.rehearsal import ISSUER

LOCAL = "local_public_fixture"
SUBJECTS = ("owner", "policy", "operator", "assessor", "releaser", "auditor", "recipient")


class PilotPlanServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-pilot-service-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.f = DeliveryFixture(self.root / "authority")
        self.packet_root = self.root / "unit-packet"
        self.packet_root.mkdir()
        candidate = b'{"explicit_unit_candidate":true}'
        observations = {"schema": "mra-local-adversarial-probes/v1", "status": "passed",
            "plan_sha256": c.digest(probes.probe_plan()),
            "probes": [{"name": name, "status": "passed", "expected_denials": list(probes._EXPECTED[name]),
                        "observed_denials": list(probes._OBSERVED[name]),
                        "observations": copy.deepcopy(probes._OBSERVATIONS[name])} for name in probes.PROBE_NAMES],
            "summary": dict(probes._SUMMARY),
            "evidence_hashes": {key: "a" * 64 for key in ("candidate_sha256", "policy_sha256", "binding_sha256",
                "final_delivery_head_sha256", "positive_chunks_sha256")}, **dict(probes.c.FLAGS)}
        observations["evidence_hashes"]["candidate_sha256"] = hashlib.sha256(candidate).hexdigest()
        registration = {"agency_id": "agency", "project_id": "project", "case_id": "case-a",
            "profile_id": "sklearn-wine", "plan": {"rows": 128, "seed": 20261001}}
        self.buffers = {"assessment-observations.json": c.canonical_bytes(observations),
            "fixture/fixture/training/native/candidate.json": candidate,
            "fixture/fixture/training/registration.json": c.canonical_bytes(registration)}
        for name, raw in self.buffers.items():
            path = self.packet_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        manifest = {"payload": {"files": [{"path": name, "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in self.buffers.items()],
            "observations_sha256": hashlib.sha256(self.buffers["assessment-observations.json"]).hexdigest()}}
        manifest_raw = c.canonical_bytes(manifest)
        (self.packet_root / "manifest.json").write_bytes(manifest_raw)
        public_raw = b'{"explicit_unit_public_key":true}'
        (self.packet_root / "public-key.json").write_bytes(public_raw)
        self.packet_verify = mock.patch.object(e.packet, "verify_packet", return_value={"implementation_sha256": "d" * 64}).start()
        self.addCleanup(mock.patch.stopall)
        mock.patch("model_release_assurance.production_registration.contracts.validate_registration", side_effect=c.owned).start()
        self.evidence = e.VerifiedAssessment(self.packet_root,
            expected_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            expected_key_sha256=hashlib.sha256(public_raw).hexdigest(), profile=LOCAL)
        binding = self.evidence.snapshot()
        self.plan = c.pilot_plan(**{key: binding[key] for key in
            ("candidate_sha256", "assessment_manifest_sha256", "assessment_key_sha256")}, profile=LOCAL)
        self.service = self.make()

    def make(self):
        return s.FixturePilotPlanService(self.f.identity, self.evidence, profile=LOCAL)

    def roster(self, **changes):
        return {subject: changes.get(subject) or self.f.token(subject) for subject in SUBJECTS}

    def enroll(self, **changes):
        return self.service.enroll_people(self.roster(**changes), "case-a")

    def propose(self, *, owner_token=None, roster=None):
        self.service.enroll_people(roster or self.roster(), "case-a")
        self.service.record_producer(self.f.token("operator"), "case-a")
        return self.service.propose(owner_token or self.f.token("owner"), "case-a", self.plan)

    def acknowledge(self, *, roster=None, assessor_token=None):
        self.propose(roster=roster)
        self.service.assess(assessor_token or self.f.token("assessor"), "case-a")
        return self.service.acknowledge(self.f.token("releaser"), "case-a")

    def status(self):
        return self.service.status(self.f.token("auditor"), "case-a")

    def assert_no_change(self, action):
        before = c.canonical_bytes(self.service._view())
        with self.assertRaises(c.PilotError):
            action()
        self.assertEqual(c.canonical_bytes(self.service._view()), before)

    def test_real_signed_seven_person_plan_is_ready_only_for_local_planning(self):
        result = self.acknowledge()
        self.assertTrue(result["local_planning_ready"])
        self.assertTrue(result["current_checks_satisfied"])
        self.assertEqual(result["state"], "acknowledged")
        self.assertEqual(result["readiness"], "no_go")
        self.assertEqual(result["production_blockers"], list(s.BLOCKING_FINDING_IDS))
        self.assertEqual(len(result["production_blockers"]), 11)
        self.assertEqual([row["kind"] for row in result["events"]],
            ["named_people", "producer", "proposal", "assessment", "local_plan_acknowledgment"])
        for key, value in c.FLAGS.items():
            self.assertIs(result[key], value)
        self.assertIn("person-operator", self.f.identity._case("case-a").operators)
        self.assertEqual(len(self.service._people), 7)
        self.assertFalse(self.f.output.exists())
        for name in ("run", "admit", "grant", "deliver", "activate", "restore"):
            self.assertFalse(hasattr(self.service, name))
        self.assertTrue(self.status()["local_planning_ready"])

    def test_default_and_other_profiles_refuse_before_touching_dependencies(self):
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError("dependency touched")
        for profile in (None, True, "agency_private_cloud", "production"):
            with self.subTest(profile=profile), self.assertRaises(c.PilotError):
                s.FixturePilotPlanService(Poison(), Poison(), profile=profile)
        with self.assertRaises(c.PilotError):
            s.FixturePilotPlanService(Poison(), Poison())

    def test_only_real_registered_capability_and_dynamic_identity_are_accepted(self):
        for fake in ({"verified": True}, object(), object.__new__(e.VerifiedAssessment)):
            with self.subTest(fake=type(fake).__name__), self.assertRaises(c.PilotError):
                s.FixturePilotPlanService(self.f.identity, fake, profile=LOCAL)
        with self.assertRaises(c.PilotError):
            s.FixturePilotPlanService(object(), self.evidence, profile=LOCAL)

    def test_all_named_people_and_actual_producer_are_required_in_order(self):
        self.assert_no_change(lambda: self.service.record_producer(self.f.token("operator"), "case-a"))
        self.assert_no_change(lambda: self.service.propose(self.f.token("owner"), "case-a", self.plan))
        self.enroll()
        self.assert_no_change(lambda: self.service.propose(self.f.token("owner"), "case-a", self.plan))
        self.service.record_producer(self.f.token("operator"), "case-a")
        self.assert_no_change(lambda: self.service.record_producer(self.f.token("operator"), "case-a"))
        self.service.propose(self.f.token("owner"), "case-a", self.plan)
        self.assert_no_change(lambda: self.service.propose(self.f.token("owner"), "case-a", self.plan))
        self.assert_no_change(lambda: self.service.acknowledge(self.f.token("releaser"), "case-a"))

    def test_roster_missing_extra_alias_and_unsigned_claims_refuse_atomically(self):
        complete = self.roster()
        variations = [dict(complete), {**complete, "outsider": complete["auditor"]},
            {**complete, "recipient": complete["auditor"]},
            {**complete, "policy": {"person_id": "person-policy", "verified": True}}]
        variations[0].pop("policy")
        for roster in variations:
            self.assert_no_change(lambda roster=roster: self.service.enroll_people(roster, "case-a"))
        self.enroll()
        self.assert_no_change(lambda: self.service.enroll_people(complete, "case-a"))

    def test_named_policy_and_recipient_roles_are_checked_not_just_any_case_grant(self):
        foundation = self.f.review_fixture
        foundation.update(grants=tuple(replace(grant, roles=frozenset({"assessor"}))
            if grant.person_id == "person-policy" else grant for grant in foundation.authority.grants))
        self.assert_no_change(lambda: self.enroll())

    def test_named_participant_expiry_blocks_acknowledgment(self):
        self.propose(roster=self.roster(recipient=self.f.token("recipient", expires_at=1001)))
        self.service.assess(self.f.token("assessor"), "case-a")
        self.f.now = 1001
        self.assert_no_change(lambda: self.service.acknowledge(self.f.token("releaser"), "case-a"))
        status = self.status()
        self.assertFalse(status["local_planning_ready"])
        self.assertFalse(status["current_checks_satisfied"])
        self.assertEqual(status["checked_at"], 1001)

    def test_valid_changed_packet_or_candidate_pin_cannot_rebind_plan(self):
        self.enroll()
        self.service.record_producer(self.f.token("operator"), "case-a")
        for key in ("candidate_sha256", "assessment_manifest_sha256", "assessment_key_sha256"):
            altered = copy.deepcopy(self.plan)
            altered["binding"][key] = "e" * 64
            c.validate_plan(altered)
            self.assert_no_change(lambda altered=altered: self.service.propose(self.f.token("owner"), "case-a", altered))

    def test_widened_scope_recipient_interface_and_payloads_refuse_before_mutation(self):
        self.enroll()
        self.service.record_producer(self.f.token("operator"), "case-a")
        changes = [("binding", "case_id", "case-b"), ("recipient", "person_id", "person-auditor"),
            ("interface", "model_delivery_bytes", 1), ("limits", "max_queries", True)]
        for section, field, value in changes:
            altered = copy.deepcopy(self.plan)
            altered[section][field] = value
            self.assert_no_change(lambda altered=altered: self.service.propose(self.f.token("owner"), "case-a", altered))
        self.assert_no_change(lambda: self.service.propose(self.f.token("owner"), "case-b", self.plan))

    def test_owner_alias_operator_and_wrong_signed_scope_are_not_reviewers(self):
        self.propose()
        for subject in ("owner", "owner-alias", "operator", "policy"):
            self.assert_no_change(lambda subject=subject: self.service.assess(self.f.token(subject), "case-a"))
        self.assert_no_change(lambda: self.service.assess(self.f.token("assessor", scopes={"case:read"}), "case-a"))
        self.assert_no_change(lambda: self.service.assess(self.f.token("assessor", cases=["case-b"]), "case-a"))
        self.service.assess(self.f.token("assessor"), "case-a")
        self.assert_no_change(lambda: self.service.acknowledge(self.f.token("operator"), "case-a"))
        self.assert_no_change(lambda: self.service.acknowledge(self.f.token("assessor"), "case-a"))

    def test_canonical_assessor_alias_with_both_roles_still_cannot_acknowledge(self):
        f = self.f.review_fixture
        principals = dict(f.authority.principals)
        principals[(ISSUER, "assessor-alias")] = replace(principals[(ISSUER, "assessor")], subject="assessor-alias")
        f.update(principals=principals, grants=tuple(replace(grant, roles=grant.roles | {"release_authority"})
            if grant.person_id == "person-assessor" else grant for grant in f.authority.grants))
        self.propose()
        self.service.assess(self.f.token("assessor"), "case-a")
        self.assert_no_change(lambda: self.service.acknowledge(self.f.token("assessor-alias"), "case-a"))

    def test_forged_and_unsigned_tokens_and_excluded_reader_are_denied(self):
        self.propose()
        token = self.f.token("assessor")
        prefix, body, signature = token.split(".")
        forged = prefix + "." + body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        for bad in (forged, {"person_id": "person-assessor"}, "", None):
            self.assert_no_change(lambda bad=bad: self.service.assess(bad, "case-a"))
        with self.assertRaises(c.PilotError):
            self.service.status(self.f.token("delegatepolicy"), "case-a")

    def test_raw_pinned_candidate_tamper_blocks_current_plan_and_exact_repair_recovers(self):
        self.acknowledge()
        path = self.packet_root / "fixture/fixture/training/native/candidate.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        self.assertFalse(self.status()["local_planning_ready"])
        self.service.suspend(self.f.token("releaser"), "case-a")
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))
        path.write_bytes(original)
        self.assertTrue(self.service.resume(self.f.token("releaser"), "case-a")["local_planning_ready"])

    def test_observation_and_registration_buffers_must_match_external_manifest(self):
        self.acknowledge()
        for name in ("assessment-observations.json", "fixture/fixture/training/registration.json"):
            path = self.packet_root / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            self.assertFalse(self.status()["current_checks_satisfied"])
            path.write_bytes(original)
            self.assertTrue(self.status()["local_planning_ready"])

    def test_returned_plan_events_roster_and_snapshot_are_defensive_copies(self):
        proposed = self.propose()
        self.plan["binding"]["candidate_sha256"] = "e" * 64
        proposed["events"][0]["details"]["people"][0]["person_id"] = "replacement"
        proposed["plan"]["recipient"]["person_id"] = "replacement"
        evidence = self.evidence.snapshot()
        evidence["candidate_sha256"] = "f" * 64
        current = self.status()
        self.assertNotEqual(current["plan"]["binding"]["candidate_sha256"], "e" * 64)
        self.assertEqual(current["plan"]["recipient"]["person_id"], "person-recipient")
        self.assertEqual(current["events"][0]["details"]["people"][0]["person_id"], "person-owner")

    def test_current_revocation_cannot_be_cured_by_replacing_original_signed_contexts(self):
        self.acknowledge()
        self.service.suspend(self.f.token("releaser"), "case-a")
        f = self.f.review_fixture
        f.update(revoked_token_ids=frozenset({self.service._assessor.identity.token_id}))
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))
        self.assertFalse(self.status()["local_planning_ready"])
        f.update(revoked_token_ids=frozenset())
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))
        self.assert_no_change(lambda: self.service.enroll_people(self.roster(), "case-a"))
        self.assertEqual(self.status()["state"], "suspended")

    def test_suspend_and_withdraw_remain_possible_when_historical_evidence_is_stale(self):
        self.acknowledge()
        self.packet_verify.side_effect = ValueError("unit missing packet")
        suspended = self.service.suspend(self.f.token("releaser"), "case-a")
        self.assertFalse(suspended["local_planning_ready"])
        self.assertFalse(suspended["current_checks_satisfied"])
        self.assert_no_change(lambda: self.service.resume(self.f.token("owner"), "case-a"))
        withdrawn = self.service.withdraw(self.f.token("releaser"), "case-a")
        self.assertEqual(withdrawn["state"], "withdrawn")
        self.assertFalse(withdrawn["current_checks_satisfied"])
        self.packet_verify.side_effect = None
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))
        self.assert_no_change(lambda: self.service.propose(self.f.token("owner"), "case-a", self.plan))

    def test_original_roster_expiry_prevents_resume_with_fresh_caller(self):
        self.acknowledge(roster=self.roster(policy=self.f.token("policy", expires_at=1001)))
        self.service.suspend(self.f.token("releaser"), "case-a")
        self.f.now = 1001
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))
        self.assertFalse(self.status()["local_planning_ready"])
        self.assertEqual(self.service.withdraw(self.f.token("releaser"), "case-a")["state"], "withdrawn")

    def test_evidence_latency_crossing_window_deadline_blocks_final_mutation(self):
        self.plan["window"]["ends_at"] = 1001
        self.enroll()
        self.service.record_producer(self.f.token("operator"), "case-a")
        token = self.f.token("owner")
        original = self.evidence.recheck
        def late():
            result = original()
            self.f.now = 1001
            return result
        with mock.patch.object(self.evidence, "recheck", side_effect=late):
            self.assert_no_change(lambda: self.service.propose(token, "case-a", self.plan))
        self.assertIsNone(self.service._plan)

    def test_evidence_latency_rechecks_original_reviewer_at_final_shared_timestamp(self):
        self.propose()
        self.service.assess(self.f.token("assessor", expires_at=1001), "case-a")
        token = self.f.token("releaser")
        original = self.evidence.recheck
        def late():
            result = original()
            self.f.now = 1001
            return result
        with mock.patch.object(self.evidence, "recheck", side_effect=late):
            self.assert_no_change(lambda: self.service.acknowledge(token, "case-a"))
        self.assertIsNone(self.service._approver)
        self.assertEqual(self.status()["checked_at"], 1001)

    def test_no_serialization_or_digest_after_last_authority_check(self):
        self.enroll()
        self.service.record_producer(self.f.token("operator"), "case-a")
        token = self.f.token("owner")
        final = self.service._final
        sampled = [False]
        digest = c.digest
        def check_last(*args, **kwargs):
            now = final(*args, **kwargs)
            sampled[0] = True
            return now
        def before_time_only(value, *args, **kwargs):
            self.assertFalse(sampled[0], "digest after final current-time check")
            return digest(value, *args, **kwargs)
        with mock.patch.object(self.service, "_final", side_effect=check_last), mock.patch.object(c, "digest", side_effect=before_time_only):
            result = self.service.propose(token, "case-a", self.plan)
        self.assertEqual(result["state"], "proposed")

    def test_status_last_reader_check_rejects_expired_reader_even_when_old_state_stale(self):
        self.acknowledge()
        token = self.f.token("auditor", expires_at=1001)
        original = self.evidence.recheck
        def late():
            result = original()
            self.f.now = 1001
            return result
        with mock.patch.object(self.evidence, "recheck", side_effect=late), self.assertRaises(c.PilotError):
            self.service.status(token, "case-a")

    def test_clock_rollback_fails_closed(self):
        token = self.f.token("auditor")
        self.f.now = 999
        with self.assertRaises(c.PilotError):
            self.service.status(token, "case-a")

    def test_current_key_revocation_denies_even_restrictive_action(self):
        self.acknowledge()
        token = self.f.token("releaser")
        self.f.trust.revoke("human-key", expected_revision=self.f.trust.revision)
        self.assert_no_change(lambda: self.service.suspend(token, "case-a"))

    def test_authority_outage_denies_named_current_reader(self):
        token = self.f.token("auditor")
        self.f.review_fixture.update(available=False)
        with self.assertRaises(c.PilotError):
            self.service.status(token, "case-a")

    def test_serialized_history_never_reconstructs_live_review_or_roster(self):
        history = self.acknowledge()
        fresh = self.make()
        result = fresh.status(self.f.token("auditor"), "case-a")
        self.assertEqual(result["state"], "awaiting_producer")
        self.assertIsNone(result["plan"])
        self.assertEqual(result["events"], [])
        self.assertFalse(result["local_planning_ready"])
        with self.assertRaises(c.PilotError):
            fresh.propose(history, "case-a", history["plan"])
        with self.assertRaises(c.PilotError):
            fresh.enroll_people(history, "case-a")

    def test_readiness_expires_at_fixed_end_without_extending_old_time_limits(self):
        self.acknowledge()
        self.f.now = 1100
        status = self.status()
        self.assertFalse(status["local_planning_ready"])
        self.assertEqual(status["checked_at"], 1100)
        self.assertEqual(status["plan"]["window"]["ends_at"], 1100)
        self.service.suspend(self.f.token("releaser"), "case-a")
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))

    def test_finite_event_capacity_preserves_restrictive_transitions(self):
        self.acknowledge()
        while len(self.service._events) < s.MAX_EVENTS - 2:
            if self.service._state == "acknowledged":
                self.service.suspend(self.f.token("releaser"), "case-a")
            else:
                self.service.resume(self.f.token("releaser"), "case-a")
        self.assertFalse(self.status()["local_planning_ready"])
        if self.service._state == "acknowledged":
            self.service.suspend(self.f.token("releaser"), "case-a")
        self.assert_no_change(lambda: self.service.resume(self.f.token("releaser"), "case-a"))
        withdrawn = self.service.withdraw(self.f.token("releaser"), "case-a")
        self.assertEqual(withdrawn["state"], "withdrawn")
        self.assertLessEqual(len(withdrawn["events"]), s.MAX_EVENTS)

    def test_concurrent_acknowledgments_produce_exactly_one_event(self):
        self.propose()
        self.service.assess(self.f.token("assessor"), "case-a")
        tokens = [self.f.token("releaser"), self.f.token("releaser")]
        barrier = threading.Barrier(2)
        def attempt(token):
            barrier.wait()
            try:
                self.service.acknowledge(token, "case-a")
                return "recorded"
            except c.PilotError:
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, tokens))
        self.assertEqual(sorted(results), ["denied", "recorded"])
        self.assertEqual(len(self.service._events), 5)

    def test_service_outputs_no_raw_tokens_keys_paths_or_execution_capabilities(self):
        roster = self.roster()
        tokens = [*roster.values(), self.f.token("operator"), self.f.token("owner"),
            self.f.token("assessor"), self.f.token("releaser")]
        self.service.enroll_people(roster, "case-a")
        self.service.record_producer(tokens[-4], "case-a")
        self.service.propose(tokens[-3], "case-a", self.plan)
        self.service.assess(tokens[-2], "case-a")
        result = self.service.acknowledge(tokens[-1], "case-a")
        raw = c.canonical_bytes(result)
        self.assertNotIn(str(self.root).encode(), raw)
        self.assertNotIn(b"PRIVATE KEY", raw)
        for token in tokens:
            self.assertNotIn(token.encode(), raw)
        self.assertIs(result["model_delivery"], False)
        self.assertIs(result["pilot_admission"], False)


if __name__ == "__main__":
    unittest.main()
