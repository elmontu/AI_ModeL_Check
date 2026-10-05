"""Current-grant and canonical-person separation checks for public identity fixtures."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Event
import unittest
from unittest import mock

from model_release_assurance.production_identity import policy as policy_module

from model_release_assurance.production_identity.policy import (
    AuthorityState, CaseGrant, CaseRecord, Conflict, FixtureIdentityService,
    IdentityUnavailable, PermissionDenied, PrincipalAuthority,
)


@dataclass(frozen=True)
class VerifiedFixtureIdentity:
    issuer: str
    subject: str
    client_id: str
    token_id: str
    key_id: str
    issued_at: int
    expires_at: int
    scopes: frozenset[str]
    case_ids: frozenset[str]
    acr: str | None
    auth_time: int | None


class FixtureVerifier:
    """Trusted verifier double; cryptographic parsing is tested separately."""
    def __init__(self, identities):
        self.identities = identities
        self.entered = self.resume = None

    def verify(self, token, *, now):
        if self.entered is not None:
            self.entered.set()
            if not self.resume.wait(timeout=3):
                raise RuntimeError("controlled verifier wait timed out")
        if type(token) is not str or token not in self.identities:
            raise ValueError("Fixture token rejected")
        return self.identities[token]


class ProductionIdentityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.scopes = frozenset({"case:read", "proposal:submit", "review:assess", "review:approve", "job:run"})
        self.people = {"owner": "person-owner", "owner-alias": "person-owner", "operator": "person-operator",
                       "assessor": "person-assessor", "authority": "person-authority", "auditor": "person-auditor", "worker": "workload-worker"}
        self.identities = {name: VerifiedFixtureIdentity("https://fixture.invalid", name, "client-fixture", "jti-" + name,
                           "fixture-key", 1000, 1290, self.scopes, frozenset({"case-a", "case-b"}),
                           "urn:mra:fixture:mfa" if name != "worker" else None, 1000 if name != "worker" else None)
                           for name in self.people}
        self.principals = {(identity.issuer, identity.subject): PrincipalAuthority(
            identity.issuer, identity.subject, self.people[name], "workload" if name == "worker" else "human",
            client_ids=frozenset({"client-fixture"})) for name, identity in self.identities.items()}
        role_map = {"person-owner": {"model_owner", "assessor", "release_authority"},
                    "person-operator": {"test_operator", "assessor", "release_authority"},
                    "person-assessor": {"assessor", "release_authority", "test_operator"},
                    "person-authority": {"release_authority"}, "person-auditor": {"auditor"},
                    "workload-worker": {"worker", "release_authority", "assessor"}}
        self.grants = tuple(CaseGrant(person, "agency-a", "project-a", "case-a", frozenset(roles))
                            for person, roles in role_map.items())
        self.state = AuthorityState(1, 2000, True, frozenset({"fixture-key"}), frozenset(), self.principals, self.grants)
        self.verifier = FixtureVerifier(self.identities)
        self.service = FixtureIdentityService(self.verifier, self.state,
            [CaseRecord("case-a", "agency-a", "project-a", "person-owner"),
             CaseRecord("case-b", "agency-b", "project-b", "person-owner")], now=lambda: self.now)
        self.payload = {"artifact_sha256": "a" * 64, "evidence_sha256": "b" * 64, "policy_sha256": "c" * 64,
                        "recipient_id": "recipient-a", "revision": 1}

    def update(self, **changes):
        self.state = replace(self.state, revision=self.state.revision + 1, **changes)
        self.service._replace_authority_for_fixture(self.state)

    def submit(self):
        return self.service.submit_proposal("owner", "case-a", self.payload)["proposal_digest"]

    def reviewed(self):
        digest = self.submit()
        self.service.assess("assessor", "case-a", digest)
        return self.service.approve("authority", "case-a", digest)

    def refresh_reader(self):
        old = self.identities["auditor"]
        self.identities["auditor"] = replace(old, issued_at=self.now, expires_at=self.now + 290, auth_time=self.now)

    def test_valid_current_independent_reviews_are_fixture_only_and_never_delivery(self):
        result = self.reviewed()
        self.assertTrue(result["reviews_usable"])
        self.assertEqual(result["assessment"]["person_id"], "person-assessor")
        self.assertEqual(result["approval"]["person_id"], "person-authority")
        for response in (result, self.service.read_case("auditor", "case-a"), self.service.check_job("worker", "case-a")):
            self.assertTrue(response["fixture_only"])
            self.assertFalse(response["authorization_eligible"])
            self.assertFalse(response["model_delivery"])
        self.assertFalse(self.service.check_job("worker", "case-a")["job_executed"])

    def test_owner_and_alias_cannot_assess_or_acknowledge_despite_combined_roles(self):
        digest = self.submit()
        for token in ("owner", "owner-alias"):
            with self.assertRaises(PermissionDenied):
                self.service.assess(token, "case-a", digest)
        self.service.assess("assessor", "case-a", digest)
        for token in ("owner", "owner-alias"):
            with self.assertRaises(PermissionDenied):
                self.service.approve(token, "case-a", digest)

    def test_registered_owner_is_required_not_merely_model_owner_role(self):
        grant = CaseGrant("person-operator", "agency-a", "project-a", "case-a", frozenset({"model_owner"}))
        self.update(grants=tuple(item for item in self.grants if item.person_id != "person-operator") + (grant,))
        with self.assertRaises(PermissionDenied):
            self.service.submit_proposal("operator", "case-a", self.payload)
        self.assertIsNone(self.service.read_case("owner", "case-a")["proposal"])

    def test_operator_and_assessor_are_independent_from_release_acknowledgement(self):
        digest = self.submit()
        self.service.check_job("operator", "case-a")
        with self.assertRaises(PermissionDenied):
            self.service.assess("operator", "case-a", digest)
        self.service.assess("assessor", "case-a", digest)
        for token in ("operator", "assessor"):
            with self.assertRaises(PermissionDenied):
                self.service.approve(token, "case-a", digest)
        self.assertTrue(self.service.approve("authority", "case-a", digest)["reviews_usable"])

    def test_later_operator_decision_invalidates_prior_assessment_and_acknowledgement(self):
        self.reviewed()
        self.service.check_job("assessor", "case-a")
        result = self.service.read_case("auditor", "case-a")
        self.assertFalse(result["reviews_usable"])
        self.assertFalse(result["assessment"]["usable"])
        self.assertFalse(result["approval"]["usable"])

    def test_workload_can_only_request_explicit_job_decision(self):
        digest = self.submit()
        self.assertTrue(self.service.check_job("worker", "case-a")["allowed"])
        for method, args in ((self.service.read_case, ("worker", "case-a")),
                             (self.service.assess, ("worker", "case-a", digest)),
                             (self.service.approve, ("worker", "case-a", digest)),
                             (self.service.submit_proposal, ("worker", "case-a", self.payload))):
            with self.assertRaises(PermissionDenied):
                method(*args)
        with self.assertRaises(PermissionDenied):
            self.service.check_job("worker", "case-b")

    def test_exact_agency_project_case_grant_and_signed_bounds_are_all_required(self):
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-b")
        for field, wrong in (("agency_id", "other-agency"), ("project_id", "other-project"), ("case_id", "other-case")):
            grant = replace(self.grants[0], **{field: wrong})
            self.update(grants=(grant,) + self.grants[1:])
            with self.assertRaises(PermissionDenied):
                self.service.read_case("owner", "case-a")
        self.update(grants=self.grants)
        original = self.identities["owner"]
        for changed in (replace(original, scopes=frozenset({"job:run"})), replace(original, case_ids=frozenset({"case-b"})),
                        replace(original, client_id="unapproved-client")):
            self.identities["owner"] = changed
            with self.assertRaises(PermissionDenied):
                self.service.read_case("owner", "case-a")

    def test_all_human_actions_require_fresh_approved_mfa(self):
        original = self.identities["owner"]
        for changed in (replace(original, acr=None), replace(original, acr="unapproved-mfa"),
                        replace(original, auth_time=None), replace(original, auth_time=699), replace(original, auth_time=1001)):
            self.identities["owner"] = changed
            with self.assertRaises(PermissionDenied):
                self.service.read_case("owner", "case-a")
        self.identities["owner"] = replace(original, auth_time=700)
        self.assertIsNone(self.service.read_case("owner", "case-a")["proposal"])

    def test_missing_unavailable_and_stale_authority_never_use_previous_state(self):
        self.reviewed()
        self.update(available=False)
        with self.assertRaises(IdentityUnavailable):
            self.service.read_case("owner", "case-a")
        self.update(available=True, fresh_until=self.now)
        with self.assertRaises(IdentityUnavailable):
            self.service.read_case("owner", "case-a")
        self.service._authority = None  # Simulated lost authoritative fixture, not an API.
        with self.assertRaises(IdentityUnavailable):
            self.service.read_case("owner", "case-a")

    def test_role_and_authority_change_invalidate_reviews_without_revoking_unrelated_tokens(self):
        self.reviewed()
        self.update(grants=tuple(item for item in self.grants if item.person_id != "person-assessor"))
        result = self.service.read_case("owner", "case-a")
        self.assertFalse(result["reviews_usable"])
        self.assertEqual(result["assessment"]["reason"], "authority_changed")
        self.update(grants=self.grants)
        self.assertFalse(self.service.read_case("owner", "case-a")["reviews_usable"])

    def test_jti_revocation_tombstone_and_key_retirement_survive_regrant(self):
        self.update(revoked_token_ids=frozenset({self.identities["owner"].token_id}))
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.update(revoked_token_ids=frozenset())
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.update(active_key_ids=frozenset())
        self.update(active_key_ids=frozenset({"fixture-key"}))
        with self.assertRaises(PermissionDenied):
            self.service.read_case("auditor", "case-a")

    def test_disabled_subject_reenabled_requires_newly_issued_token(self):
        key = ("https://fixture.invalid", "owner")
        principals = dict(self.principals)
        principals[key] = replace(principals[key], enabled=False)
        self.update(principals=principals)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.update(principals=self.principals)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.now += 1
        self.identities["owner"] = replace(self.identities["owner"], issued_at=self.now, expires_at=self.now + 290, auth_time=self.now)
        self.assertIsNone(self.service.read_case("owner", "case-a")["proposal"])

    def test_explicit_issuance_floor_cannot_be_lowered_to_revive_old_credentials(self):
        key = ("https://fixture.invalid", "owner")
        principals = dict(self.principals)
        principals[key] = replace(principals[key], tokens_valid_after=1001)
        self.update(principals=principals)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.update(principals=self.principals)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")

    def test_expired_prior_reviewer_and_stale_mfa_invalidate_current_approval_read(self):
        self.reviewed()
        self.now = 1290
        self.refresh_reader()
        result = self.service.read_case("auditor", "case-a")
        self.assertFalse(result["assessment"]["usable"])
        self.assertFalse(result["approval"]["usable"])
        self.assertFalse(result["reviews_usable"])

    def test_prior_reviewer_mfa_can_expire_before_access_token(self):
        self.identities["assessor"] = replace(self.identities["assessor"], auth_time=800)
        self.reviewed()
        self.now = 1101
        self.refresh_reader()
        result = self.service.read_case("auditor", "case-a")
        self.assertFalse(result["reviews_usable"])
        self.assertEqual(result["assessment"]["reason"], "actor_not_currently_eligible")

    def test_material_proposal_revision_cannot_inherit_or_replay_reviews(self):
        reviewed = self.reviewed()
        digest = reviewed["proposal_digest"]
        with self.assertRaises(Conflict):
            self.service.assess("assessor", "case-a", digest)
        with self.assertRaises(Conflict):
            self.service.approve("authority", "case-a", digest)
        changed = {**self.payload, "revision": 2, "recipient_id": "recipient-b"}
        result = self.service.submit_proposal("owner", "case-a", changed)
        self.assertNotEqual(result["proposal_digest"], digest)
        self.assertIsNone(result["assessment"])
        self.assertIsNone(result["approval"])
        self.assertFalse(result["reviews_usable"])
        with self.assertRaises(Conflict):
            self.service.assess("assessor", "case-a", digest)
        with self.assertRaises(Conflict):
            self.service.approve("authority", "case-a", result["proposal_digest"])
        with self.assertRaises(Conflict):
            self.service.submit_proposal("owner", "case-a", self.payload)

    def test_proposal_validation_rejects_unknown_fields_bad_hash_and_invalid_revision(self):
        for changed in ({**self.payload, "passed": True}, {**self.payload, "artifact_sha256": "A" * 64},
                        {**self.payload, "revision": True}, {**self.payload, "revision": 2},
                        {**self.payload, "recipient_id": "../escape"}, {**self.payload, "revision": 1_000_001}):
            with self.assertRaises(Conflict):
                self.service.submit_proposal("owner", "case-a", changed)
        self.assertIsNone(self.service.read_case("owner", "case-a")["proposal"])
        result = self.service.submit_proposal("owner", "case-a", self.payload)
        self.payload["artifact_sha256"] = "d" * 64
        result["proposal"]["artifact_sha256"] = "e" * 64
        self.assertEqual(self.service.read_case("owner", "case-a")["proposal"]["artifact_sha256"], "a" * 64)

    def test_authority_and_principal_records_defensively_copy_and_validate(self):
        source = dict(self.principals)
        state = replace(self.state, principals=source)
        source.clear()
        self.assertTrue(state.principals)
        with self.assertRaises(TypeError):
            state.principals[("new", "subject")] = next(iter(self.principals.values()))
        for changes in ({"revision": True}, {"revision": 0}, {"available": 1},
                        {"grants": self.grants + (self.grants[0],)}, {"active_key_ids": ["same", "same"]}):
            with self.assertRaises(ValueError):
                replace(self.state, **changes)
        aliases = dict(self.principals)
        key = ("https://fixture.invalid", "owner-alias")
        aliases[key] = replace(aliases[key], kind="workload")
        with self.assertRaises(ValueError):
            replace(self.state, principals=aliases)
        with self.assertRaises(ValueError):
            replace(self.grants[0], roles=frozenset({"administrator-superuser"}))
        with self.assertRaises(ValueError):
            self.service._replace_authority_for_fixture(self.state)

    def test_duplicate_concurrent_assessment_has_one_success_and_one_conflict(self):
        digest = self.submit()
        def attempt():
            try:
                return self.service.assess("assessor", "case-a", digest)["assessment"]["usable"]
            except Conflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(results, [True, "conflict"])

    def test_authority_update_cannot_interleave_verification_and_mutation(self):
        entered, resume, updated = Event(), Event(), Event()
        self.verifier.entered, self.verifier.resume = entered, resume
        changed = replace(self.state, revision=2, grants=tuple(item for item in self.grants if item.person_id != "person-owner"))
        def update():
            self.service._replace_authority_for_fixture(changed)
            updated.set()
        with ThreadPoolExecutor(max_workers=2) as executor:
            submitted = executor.submit(self.service.submit_proposal, "owner", "case-a", self.payload)
            self.assertTrue(entered.wait(timeout=2))
            update_future = executor.submit(update)
            self.assertFalse(updated.wait(timeout=0.1))
            resume.set()
            result = submitted.result(timeout=2)
            update_future.result(timeout=2)
        self.assertEqual(result["proposal"]["revision"], 1)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")

    def test_public_methods_never_accept_caller_supplied_identity_as_proof(self):
        with self.assertRaises(ValueError):
            self.service.read_case(self.identities["owner"], "case-a")
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "unknown-case")


    def test_clock_rollback_cannot_revive_expired_access(self):
        self.service.read_case("owner", "case-a")
        self.now = 1290
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.now = 1000
        with self.assertRaisesRegex(IdentityUnavailable, "backwards"):
            self.service.read_case("owner", "case-a")

    def test_expiry_during_verification_is_rechecked_before_mutation(self):
        original = self.verifier.verify
        def advancing(token, *, now):
            result = original(token, now=now)
            self.now = 1290
            return result
        self.verifier.verify = advancing
        with self.assertRaises(PermissionDenied):
            self.service.submit_proposal("owner", "case-a", self.payload)
        self.assertIsNone(self.service._cases["case-a"].proposal)

    def test_authority_expiry_during_verification_has_no_cached_fallback(self):
        original = self.verifier.verify
        def advancing(token, *, now):
            result = original(token, now=now)
            self.now = 2000
            return result
        self.verifier.verify = advancing
        with self.assertRaises(IdentityUnavailable):
            self.service.submit_proposal("owner", "case-a", self.payload)
        self.assertIsNone(self.service._cases["case-a"].proposal)

    def test_expiry_during_proposal_hash_is_rechecked_at_mutation(self):
        original = policy_module.hashlib.sha256
        def advancing(content):
            result = original(content)
            self.now = 1290
            return result
        with mock.patch.object(policy_module.hashlib, "sha256", side_effect=advancing):
            with self.assertRaises(PermissionDenied):
                self.service.submit_proposal("owner", "case-a", self.payload)
        self.assertIsNone(self.service._cases["case-a"].proposal)


    def test_caller_payload_mutation_during_hash_cannot_substitute_proposal(self):
        original = policy_module.hashlib.sha256
        def mutate_caller(content):
            self.payload["recipient_id"] = "substituted-recipient"
            self.payload["artifact_sha256"] = "e" * 64
            return original(content)
        with mock.patch.object(policy_module.hashlib, "sha256", side_effect=mutate_caller):
            result = self.service.submit_proposal("owner", "case-a", self.payload)
        self.assertEqual(result["proposal"]["recipient_id"], "recipient-a")
        self.assertEqual(result["proposal"]["artifact_sha256"], "a" * 64)

    def test_token_issued_while_subject_disabled_does_not_revive_at_reenable(self):
        key = ("https://fixture.invalid", "owner")
        principals = dict(self.principals)
        principals[key] = replace(principals[key], enabled=False)
        self.update(principals=principals)
        self.now = 1005
        self.identities["owner"] = replace(self.identities["owner"], issued_at=self.now, expires_at=1290, auth_time=self.now)
        self.now = 1010
        self.update(principals=self.principals)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.now = 1011
        self.identities["owner"] = replace(self.identities["owner"], issued_at=self.now, expires_at=1290, auth_time=self.now)
        self.assertIsNone(self.service.read_case("owner", "case-a")["proposal"])


    def test_token_issued_while_subject_absent_does_not_revive_on_restoration(self):
        key = ("https://fixture.invalid", "owner")
        principals = dict(self.principals)
        del principals[key]
        self.update(principals=principals)
        self.now = 1002
        self.identities["owner"] = replace(self.identities["owner"], issued_at=self.now, expires_at=1290, auth_time=self.now)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.now = 1010
        self.update(principals=self.principals)
        with self.assertRaises(PermissionDenied):
            self.service.read_case("owner", "case-a")
        self.now = 1011
        self.identities["owner"] = replace(self.identities["owner"], issued_at=self.now, expires_at=1290, auth_time=self.now)
        self.assertIsNone(self.service.read_case("owner", "case-a")["proposal"])


    def test_storage_bridge_refuses_unregistered_actions_and_caller_identity_proof(self):
        callback = mock.Mock()
        with self.assertRaises(PermissionDenied):
            self.service._with_fixture_authorization("owner", "case-a", "admin:grant", callback)
        with self.assertRaises(ValueError):
            self.service._with_fixture_authorization(self.identities["owner"], "case-a", "object:metadata", callback)
        callback.assert_not_called()

    def test_storage_bridge_requires_steward_role_and_does_not_upgrade_human_worker_role(self):
        self.identities["owner"] = replace(self.identities["owner"], scopes=self.scopes | {"object:register", "object:read"})
        with self.assertRaises(PermissionDenied):
            self.service._with_fixture_authorization("owner", "case-a", "object:register", lambda context: True)
        grants = tuple(replace(grant, roles=grant.roles | {"worker"}) if grant.person_id == "person-owner" else grant for grant in self.grants)
        self.update(grants=grants)
        with self.assertRaises(PermissionDenied):
            self.service._with_fixture_authorization("owner", "case-a", "object:read", lambda context: b"fixture")

    def test_storage_bridge_rechecks_expiry_after_trusted_callback(self):
        self.identities["owner"] = replace(self.identities["owner"], scopes=self.scopes | {"object:metadata"})
        def delayed(context):
            self.now = 1290
            return {"fixture": "must not be returned"}
        with self.assertRaises(PermissionDenied):
            self.service._with_fixture_authorization("owner", "case-a", "object:metadata", delayed)


if __name__ == "__main__":
    unittest.main()
