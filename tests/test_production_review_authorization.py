"""Current signed policy authority and canonical independent-review boundary."""
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_identity.policy import (
    AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, PrincipalAuthority,
    PermissionDenied, IdentityUnavailable)
from model_release_assurance.production_identity.tokens import TokenError, AccessTokenVerifier
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile
from model_release_assurance.production_trust.signer import FixtureTokenIssuer, MemoryFixtureSigningProvider
from model_release_assurance.production_trust.verification import RegistryAccessTokenVerifier
from model_release_assurance.production_review.authorization import ReviewAuthorization

ISSUER = "https://review.example.invalid"
AUDIENCE = "urn:mra:review:fixture"
SCOPES = {"case:read", "proposal:submit", "job:run", "review:policy", "review:assess", "review:approve", "review:delegate"}
ROLES = {"owner": {"model_owner", "policy_authority", "assessor", "release_authority"},
         "operator": {"test_operator", "policy_authority", "assessor", "release_authority"},
         "policy": {"policy_authority"}, "assessor": {"assessor"}, "approver": {"release_authority"},
         "reader": {"auditor"}, "other-owner": {"model_owner"}, "worker": {"worker", "policy_authority"}}


class AuthorizationFixture:
    def __init__(self):
        self.now = 1000
        self.profile = TrustProfile(agency_id="agency", environment="public_fixture", issuer=ISSUER,
                                    audience=AUDIENCE, purpose="access_token")
        self.trust = FixtureTrustRegistry(now=lambda: self.now, fresh_until=1250)
        provider = MemoryFixtureSigningProvider()
        self.key = provider.create_key(key_id="key", profile=self.profile, owner_id="fixture-idp", not_before=900, not_after=2000)
        self.trust.enroll(self.key, expected_revision=self.trust.revision)
        self.issuer = FixtureTokenIssuer(self.trust, provider.bind(profile=self.profile, owner_id="fixture-idp"),
                                        self.profile, "fixture-idp")
        principals = {(ISSUER, subject): PrincipalAuthority(ISSUER, subject, "person-" + subject,
            "workload" if subject == "worker" else "human", client_ids=frozenset({"client"})) for subject in ROLES}
        for original in ("owner", "operator"):
            principals[(ISSUER, original + "-alias")] = replace(principals[(ISSUER, original)], subject=original + "-alias")
        self.cases = [CaseRecord("case-a", "agency", "project", "person-owner"),
                      CaseRecord("case-b", "agency", "other-project", "person-owner")]
        grants = tuple(CaseGrant("person-" + person, case.agency_id, case.project_id, case.case_id, frozenset(roles))
                       for person, roles in ROLES.items() for case in self.cases)
        self.authority = AuthorityState(1, 1250, True, frozenset({"key"}), frozenset(), principals, grants)
        self.identity = FixtureIdentityService(RegistryAccessTokenVerifier(self.trust, self.profile), self.authority, self.cases)
        self.auth = ReviewAuthorization(self.identity)

    def token(self, person, *, scopes=None, cases=None, expires=None, auth_time=None, acr="urn:mra:fixture:mfa", **changes):
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": person, "client_id": "client", "jti": uuid.uuid4().hex,
                  "iat": self.now, "nbf": self.now, "exp": self.now + 240 if expires is None else expires,
                  "scope": " ".join(sorted(SCOPES if scopes is None else scopes)), "case_ids": cases or ["case-a", "case-b"]}
        if person != "worker":
            claims.update(acr=acr, auth_time=self.now if auth_time is None else auth_time)
        claims.update(changes)
        return self.issuer.issue("key", claims)

    def update(self, **changes):
        self.authority = replace(self.authority, revision=self.authority.revision + 1, **changes)
        self.identity._replace_authority_for_fixture(self.authority)


class ReviewAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.f = AuthorizationFixture()

    def access(self, person, action, **token_options):
        return self.f.auth.access(self.f.token(person, **token_options), "case-a", action)

    def test_each_action_requires_its_current_signed_role_and_returns_minimal_actor(self):
        for person, action in (("owner", "propose"), ("operator", "start"), ("policy", "policy"),
                               ("assessor", "assess"), ("approver", "approve"), ("reader", "read")):
            context = self.access(person, action)
            self.assertEqual(set(context.actor), {"person_id", "authority_revision", "credential_sha256"})
            self.assertEqual(context.actor["person_id"], "person-" + person)
            self.assertEqual(context.recheck(), self.f.now)
            self.assertEqual(len(context.credential_sha256), 64)
            self.assertEqual(context.case.project_id, "project")
            self.assertNotIn("AccessIdentity", repr(context))

    def test_policy_requires_dedicated_signed_scope_and_base_case_read(self):
        for scopes in ({"case:read"}, {"review:policy"}, {"review:assess", "case:read"}):
            with self.subTest(scopes=scopes), self.assertRaises(PermissionDenied):
                self.access("policy", "policy", scopes=scopes)
        self.access("policy", "policy", scopes={"case:read", "review:policy"})

    def test_signed_policy_scope_cannot_replace_current_policy_role(self):
        for person in ("reader", "assessor", "approver"):
            with self.subTest(person=person), self.assertRaises(PermissionDenied):
                self.access(person, "policy")

    def test_foreign_case_project_or_subject_client_binding_is_denied(self):
        token = self.f.token("policy", cases=["case-b"])
        with self.assertRaises(PermissionDenied): self.f.auth.access(token, "case-a", "policy")
        grants = tuple(grant for grant in self.f.authority.grants if not (grant.person_id == "person-policy" and grant.case_id == "case-a"))
        self.f.update(grants=grants)
        with self.assertRaises(PermissionDenied): self.access("policy", "policy")
        with self.assertRaises(PermissionDenied): self.access("assessor", "assess", client_id="different")

    def test_owner_and_alias_cannot_review_despite_combined_roles(self):
        for person in ("owner", "owner-alias"):
            for action in ("policy", "assess", "approve"):
                with self.subTest(person=person, action=action), self.assertRaises(PermissionDenied):
                    self.access(person, action)

    def test_recorded_operator_and_alias_cannot_review_even_if_work_fails(self):
        self.access("operator", "start")
        self.assertIn("person-operator", self.f.identity._case("case-a").operators)
        for person in ("operator", "operator-alias"):
            for action in ("policy", "assess", "approve"):
                with self.subTest(person=person, action=action), self.assertRaises(PermissionDenied):
                    self.access(person, action)

    def test_new_operator_status_invalidates_saved_reviewer_without_role_revision(self):
        context = self.access("operator", "policy")
        self.access("operator-alias", "start")
        with self.assertRaises(PermissionDenied): context.recheck()

    def test_workload_cannot_use_any_human_review_bridge_action(self):
        for action in ("propose", "start", "policy", "assess", "approve", "read"):
            with self.subTest(action=action), self.assertRaises(PermissionDenied):
                self.access("worker", action)

    def test_model_owner_role_does_not_replace_registered_canonical_submitter(self):
        with self.assertRaises(PermissionDenied): self.access("other-owner", "propose")
        self.assertEqual(self.access("owner-alias", "propose").principal.person_id, "person-owner")

    def test_missing_stale_or_wrong_mfa_is_denied(self):
        for options in ({"acr": "urn:wrong"}, {"auth_time": 699}):
            with self.subTest(options=options), self.assertRaises(PermissionDenied):
                self.access("policy", "policy", **options)
        self.f.now = 1100
        context = self.access("policy", "policy", auth_time=800)
        self.f.now += 1
        with self.assertRaises(PermissionDenied): context.recheck()

    def test_role_removal_unavailable_and_stale_authority_deny_saved_context(self):
        for mode in ("role", "unavailable", "stale"):
            fixture = AuthorizationFixture()
            context = fixture.auth.access(fixture.token("policy"), "case-a", "policy")
            if mode == "role":
                fixture.update(grants=tuple(grant for grant in fixture.authority.grants if grant.person_id != "person-policy"))
            elif mode == "unavailable": fixture.update(available=False)
            else: fixture.now = 1250
            with self.subTest(mode=mode), self.assertRaises((PermissionDenied, IdentityUnavailable)):
                context.recheck()

    def test_revoked_key_and_token_never_reactivate_saved_review(self):
        context = self.access("policy", "policy")
        self.f.update(revoked_token_ids=frozenset({context.identity.token_id}))
        with self.assertRaises(PermissionDenied): context.recheck()
        self.f.update(revoked_token_ids=frozenset())
        with self.assertRaises(PermissionDenied): self.f.auth.access(self.f.token("policy", jti=context.identity.token_id), "case-a", "policy")
        context = self.access("assessor", "assess")
        self.f.trust.revoke("key", expected_revision=self.f.trust.revision)
        with self.assertRaises(PermissionDenied): context.recheck()

    def test_trust_outage_and_unrelated_revision_invalidate_context(self):
        for mode in ("outage", "refresh"):
            fixture = AuthorizationFixture()
            context = fixture.auth.access(fixture.token("policy"), "case-a", "policy")
            if mode == "outage": fixture.trust.set_available(False, expected_revision=fixture.trust.revision)
            else: fixture.trust.refresh(fresh_until=1251, expected_revision=fixture.trust.revision)
            with self.subTest(mode=mode), self.assertRaises((PermissionDenied, IdentityUnavailable)):
                context.recheck()

    def test_final_revision_time_sample_cannot_hide_token_expiry(self):
        context = self.access("policy", "policy", expires=1001)
        def sampled_revision():
            self.f.now = 1001
            return context.trust_revision
        with mock.patch.object(type(self.f.trust), "revision", new_callable=mock.PropertyMock, side_effect=sampled_revision):
            with self.assertRaises(PermissionDenied): context.recheck()

    def test_verification_latency_is_rechecked_before_context_return(self):
        token = self.f.token("policy", expires=1001)
        original = RegistryAccessTokenVerifier.verify
        def slow(verifier, raw, *, now):
            identity = original(verifier, raw, now=now)
            self.f.now = 1001
            return identity
        with mock.patch.object(RegistryAccessTokenVerifier, "verify", slow):
            with self.assertRaises(PermissionDenied): self.f.auth.access(token, "case-a", "policy")

    def test_final_recheck_detects_authority_change_and_clock_rollback(self):
        context = self.access("policy", "policy")
        self.f.update()
        with self.assertRaises(PermissionDenied): context.recheck()
        self.f.now = 999
        with self.assertRaises((PermissionDenied, IdentityUnavailable)): context.recheck()

    def test_context_is_immutable_owned_and_cannot_be_cloned_as_identity_proof(self):
        context = self.access("policy", "policy")
        actor = context.actor; actor["person_id"] = "forged"
        self.assertEqual(context.actor["person_id"], "person-policy")
        with self.assertRaises(FrozenInstanceError): context.action = "approve"
        with self.assertRaises(PermissionDenied): self.f.auth.recheck_saved(replace(context))
        other = ReviewAuthorization(self.f.identity)
        with self.assertRaises(PermissionDenied): other.recheck_saved(context)
        with self.assertRaises(PermissionDenied): self.f.auth.recheck_saved(context.actor)

    def test_all_saved_reviewers_share_one_final_current_timestamp(self):
        policy = self.access("policy", "policy", expires=1001)
        assessor = self.access("assessor", "assess")
        with mock.patch.object(self.f.identity, "_time", wraps=self.f.identity._time) as clock:
            self.assertEqual(policy.recheck_with(assessor), 1000)
            self.assertEqual(clock.call_count, 1)
        # A prior policy check at 1000 cannot carry forward when the later
        # assessor/evidence work reaches the policy token's exclusive deadline.
        self.assertEqual(policy.recheck(), 1000)
        self.f.now = 1001
        self.assertEqual(assessor.recheck(), 1001)
        with self.assertRaises(PermissionDenied):
            self.f.auth.recheck_many([policy, assessor])

    def test_many_contexts_are_bounded_and_only_this_factorys_verified_instances(self):
        context = self.access("policy", "policy")
        foreign = ReviewAuthorization(self.f.identity).access(self.f.token("policy"), "case-a", "policy")
        for contexts in ([], [context] * 33, (context, foreign), (context, replace(context)), {context}):
            with self.subTest(kind=type(contexts).__name__), self.assertRaises(PermissionDenied):
                self.f.auth.recheck_many(contexts)

    def test_raw_token_and_known_action_required(self):
        for token in (None, {}, "unsigned", ""):
            with self.subTest(token=token), self.assertRaises((TokenError, TypeError, ValueError, PermissionDenied)):
                self.f.auth.access(token, "case-a", "policy")
        for action in ([], None, "delegate", "policy_authority"):
            with self.subTest(action=action), self.assertRaises(PermissionDenied):
                self.f.auth.access(self.f.token("policy"), "case-a", action)

    def test_static_key_or_duck_typed_identity_cannot_bypass_current_trust(self):
        with self.assertRaises(ValueError): ReviewAuthorization(object())
        static = AccessTokenVerifier(ISSUER, AUDIENCE, {"key": self.f.key.public_key})
        identity = FixtureIdentityService(static, self.f.authority, self.f.cases, now=lambda: self.f.now)
        with self.assertRaises(ValueError): ReviewAuthorization(identity)

    def test_credentials_bind_full_signed_identity_and_canonical_person(self):
        first, second = self.access("policy", "policy"), self.access("policy", "policy")
        self.assertNotEqual(first.credential_sha256, second.credential_sha256)
        self.assertEqual(first.actor["person_id"], second.actor["person_id"])
        self.assertNotIn("token", first.actor)


if __name__ == "__main__": unittest.main()
