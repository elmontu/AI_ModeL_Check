"""Signed human recipient scope, directory and shared-time delivery guards."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_identity.policy import (CaseGrant, PrincipalAuthority, PermissionDenied, IdentityUnavailable)
from model_release_assurance.production_review.rehearsal import ReviewFixture, SCOPES, ISSUER, AUDIENCE
from model_release_assurance.production_review.authorization import ReviewAuthorization
from model_release_assurance.production_delivery.authorization import GatewayAuthorization, RecipientRecord

DELIVERY = {"delivery:" + action for action in ("activate", "grant", "suspend", "revoke", "resume", "receive", "read")}


class DeliveryAuthorizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-delivery-auth-")
        self.addCleanup(temporary.cleanup)
        self.f = ReviewFixture(Path(temporary.name))
        self.record = RecipientRecord("fixture-recipient", "agency", "project", "case-a", frozenset({"person-auditor"}))
        self.auth = GatewayAuthorization(self.f.service, [self.record])

    def token(self, person="auditor", *, scopes=None, **kwargs):
        return self.f.token(person, scopes=SCOPES | DELIVERY if scopes is None else scopes, **kwargs)

    def receive(self, token=None, **kwargs):
        return self.auth.access(self.token() if token is None else token, "case-a", "receive", "fixture-recipient", **kwargs)

    def add_person(self, subject, person, roles, *, kind="human"):
        principals = dict(self.f.authority.principals)
        principals[(ISSUER, subject)] = PrincipalAuthority(ISSUER, subject, person, kind, client_ids=frozenset({"client"}))
        grants = list(self.f.authority.grants)
        if not any(grant.person_id == person and grant.case_id == "case-a" for grant in grants):
            grants.append(CaseGrant(person, "agency", "project", "case-a", frozenset(roles)))
        self.f.update(principals=principals, grants=tuple(grants))

    def test_exact_current_human_recipient_exposes_owned_actor_not_raw_token(self):
        token = self.token()
        context = self.receive(token)
        self.assertEqual(context.recheck(), 1000)
        self.assertEqual(context.principal.person_id, "person-auditor")
        self.assertEqual(context.case.case_id, "case-a")
        self.assertEqual(context.review_context.actor, context.actor)
        self.assertEqual(set(context.actor), {"person_id", "authority_revision", "credential_sha256"})
        self.assertNotIn(token, repr(context))
        actor = context.actor; actor["person_id"] = "changed"
        self.assertEqual(context.actor["person_id"], "person-auditor")

    def test_both_dedicated_receive_and_case_read_scopes_are_required(self):
        for scopes in ({"case:read"}, {"delivery:receive"}, {"case:read", "delivery:grant"}):
            with self.subTest(scopes=scopes), self.assertRaises(PermissionDenied):
                self.receive(self.token(scopes=scopes))
        self.receive(self.token(scopes={"case:read", "delivery:receive"}))

    def test_policy_recipient_mapping_and_case_must_match_current_canonical_person(self):
        for recipient in (None, "other", [], "../fixture-recipient"):
            with self.subTest(recipient=recipient), self.assertRaises(PermissionDenied):
                self.auth.access(self.token(), "case-a", "receive", recipient)
        with self.assertRaises(PermissionDenied):
            self.auth.access(self.token(), "case-b", "receive", "fixture-recipient")
        with self.assertRaises(PermissionDenied):
            self.receive(self.token(cases=["case-b"]))
        self.add_person("other-auditor", "person-other", {"auditor"})
        with self.assertRaises(PermissionDenied): self.receive(self.token("other-auditor"))

    def test_canonical_alias_is_bound_to_same_recipient_but_distinct_credential(self):
        self.add_person("recipient-alias", "person-auditor", {"auditor"})
        first = self.receive(); alias = self.receive(self.token("recipient-alias"))
        self.assertEqual(first.principal.person_id, alias.principal.person_id)
        self.assertNotEqual(first.credential_sha256, alias.credential_sha256)

    def test_directory_membership_does_not_replace_current_auditor_role(self):
        grants = tuple(replace(grant, roles=frozenset({"assessor"})) if grant.person_id == "person-auditor" else grant
                       for grant in self.f.authority.grants)
        self.f.update(grants=grants)
        with self.assertRaises(PermissionDenied): self.receive()

    def test_workload_recipient_is_unsupported_even_with_auditor_and_worker_grants(self):
        self.add_person("worker", "person-worker", {"worker", "auditor"}, kind="workload")
        auth = GatewayAuthorization(self.f.service, [replace(self.record, person_ids=frozenset({"person-worker"}))])
        with self.assertRaises(PermissionDenied):
            auth.access(self.token("worker"), "case-a", "receive", "fixture-recipient")
        with self.assertRaises(ValueError): replace(self.record, kind="workload")

    def test_activation_and_grant_require_independent_release_authority_and_dedicated_scope(self):
        for action in ("activate", "grant"):
            self.auth.access(self.token("releaser"), "case-a", action, "fixture-recipient")
            with self.assertRaises(PermissionDenied): self.auth.access(self.f.token("releaser"), "case-a", action)
            with self.assertRaises(PermissionDenied): self.auth.access(self.token("auditor"), "case-a", action)
        self.f.service.authorization.access(self.f.token("operator"), "case-a", "start")
        with self.assertRaises(PermissionDenied): self.auth.access(self.token("operator"), "case-a", "grant")

    def test_suspend_revoke_resume_allow_current_steward_or_independent_release_role(self):
        self.add_person("steward", "person-steward", {"data_steward"})
        for action in ("suspend", "revoke", "resume"):
            for subject in ("steward", "releaser"):
                self.auth.access(self.token(subject), "case-a", action)
            with self.assertRaises(PermissionDenied): self.auth.access(self.token("auditor"), "case-a", action)
            with self.assertRaises(PermissionDenied): self.auth.access(self.f.token("steward"), "case-a", action)
        self.f.service.authorization.access(self.f.token("operator"), "case-a", "start")
        with self.assertRaises(PermissionDenied): self.auth.access(self.token("operator"), "case-a", "resume")

    def test_metadata_read_requires_its_own_signed_scope_and_does_not_imply_receive(self):
        context = self.auth.access(self.token(scopes={"case:read", "delivery:read"}), "case-a", "read")
        self.assertEqual(context.recheck(), 1000)
        with self.assertRaises(PermissionDenied): self.auth.access(self.f.token("auditor"), "case-a", "read")
        with self.assertRaises(PermissionDenied): self.receive(self.token(scopes={"case:read", "delivery:read"}))

    def test_directory_is_defensively_owned_and_rejects_unknown_scope_or_duplicate_ids(self):
        people = {"person-auditor"}
        record = RecipientRecord("owned", "agency", "project", "case-a", people)
        records = [record]; auth = GatewayAuthorization(self.f.service, records)
        people.clear(); records.clear()
        self.assertEqual(record.person_ids, frozenset({"person-auditor"}))
        self.assertEqual(auth.access(self.token(), "case-a", "receive", "owned").principal.person_id, "person-auditor")
        with self.assertRaises(FrozenInstanceError): record.case_id = "case-b"
        for records in ([], [self.record, self.record], [replace(self.record, project_id="other")], [dict(recipient_id="fake")]):
            with self.subTest(records=records), self.assertRaises((ValueError, PermissionDenied)):
                GatewayAuthorization(self.f.service, records)
        for people in ([], ["a", "a"], ["*"]):
            with self.assertRaises(ValueError): replace(self.record, person_ids=people)
        with self.assertRaises(ValueError): GatewayAuthorization(object(), [self.record])

    def test_saved_recipient_and_issuer_are_rechecked_with_all_reviewers_once(self):
        recipient = self.receive()
        issuer = self.auth.access(self.token("releaser"), "case-a", "grant")
        policy = self.f.service.authorization.access(self.f.token("policy", expires_at=1001), "case-a", "policy")
        with mock.patch.object(self.f.identity, "_time", wraps=self.f.identity._time) as clock:
            self.assertEqual(self.auth.recheck_many([recipient, issuer], review_contexts=[policy]), 1000)
            self.assertEqual(clock.call_count, 1)
        self.f.now = 1001
        self.assertEqual(recipient.recheck(), 1001)
        with self.assertRaises(PermissionDenied):
            recipient.recheck_with(issuer, review_contexts=[policy])

    def test_final_revision_clock_observation_cannot_hide_recipient_token_expiry(self):
        recipient = self.receive(self.token(expires_at=1001))
        policy = self.f.service.authorization.access(self.f.token("policy"), "case-a", "policy")
        revision = self.f.trust.revision
        def current_revision():
            self.f.now = 1001
            return revision
        with mock.patch.object(type(self.f.trust), "revision", new_callable=mock.PropertyMock, side_effect=current_revision):
            with self.assertRaises(PermissionDenied): self.auth.recheck_many([recipient], review_contexts=[policy])

    def test_revoked_recipient_role_or_jti_invalidates_saved_grant_identity(self):
        recipient = self.receive()
        self.f.update(revoked_token_ids=frozenset({recipient.identity.token_id}))
        with self.assertRaises(PermissionDenied): recipient.recheck()
        fresh = self.receive()
        self.f.update(grants=tuple(grant for grant in self.f.authority.grants if grant.person_id != "person-auditor"))
        with self.assertRaises(PermissionDenied): fresh.recheck()
        with self.assertRaises(PermissionDenied): self.receive()

    def test_disabled_subject_or_trust_key_outage_never_uses_directory_as_fallback(self):
        recipient = self.receive()
        principals = dict(self.f.authority.principals)
        principals[(ISSUER, "auditor")] = replace(principals[(ISSUER, "auditor")], enabled=False)
        self.f.update(principals=principals)
        with self.assertRaises(PermissionDenied): recipient.recheck()
        self.f.trust.set_available(False, expected_revision=self.f.trust.revision)
        with self.assertRaises((PermissionDenied, IdentityUnavailable)): recipient.recheck()

    def test_human_mfa_is_required_even_for_exact_directory_person(self):
        for acr, auth_time in (("urn:wrong", 1000), ("urn:mra:fixture:mfa", 699)):
            claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "auditor", "client_id": "client", "jti": uuid.uuid4().hex,
                "iat": 1000, "nbf": 1000, "exp": 1240, "scope": "case:read delivery:receive", "case_ids": ["case-a"],
                "acr": acr, "auth_time": auth_time}
            token = self.f.issuer.issue("human-key", claims)
            with self.subTest(acr=acr), self.assertRaises(PermissionDenied): self.receive(token)

    def test_forged_cloned_cross_factory_contexts_and_unbounded_groups_are_denied(self):
        recipient = self.receive()
        with self.assertRaises(FrozenInstanceError): recipient.recipient_id = "different"
        other = GatewayAuthorization(self.f.service, [self.record]).access(self.token(), "case-a", "receive", "fixture-recipient")
        foreign_review = ReviewAuthorization(self.f.identity).access(self.f.token("policy"), "case-a", "policy")
        for contexts in ([], [recipient] * 33, [replace(recipient)], [other], [recipient.actor]):
            with self.subTest(length=len(contexts)), self.assertRaises(PermissionDenied): self.auth.recheck_many(contexts)
        with self.assertRaises(PermissionDenied): self.auth.recheck_many([recipient], review_contexts=[foreign_review])
        for action in (None, [], "download", "object:read"):
            with self.subTest(action=action), self.assertRaises(PermissionDenied):
                self.auth.access(self.token(), "case-a", action)


if __name__ == "__main__": unittest.main()
