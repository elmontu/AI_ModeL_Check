"""Signed-token HTTP regressions for the isolated public identity fixture."""
from __future__ import annotations

from dataclasses import replace
import time
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from model_release_assurance.production_identity.tokens import AccessTokenVerifier
from model_release_assurance.production_identity.policy import (
    AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, PrincipalAuthority,
)

try:
    from fastapi.testclient import TestClient
    from model_release_assurance.production_identity.api import create_fixture_app
except ImportError:
    TestClient = None

ISSUER = "https://identity.example.invalid"
AUDIENCE = "urn:mra:public-fixture:identity"
ACTIONS = ("case:read", "proposal:submit", "review:assess", "review:approve", "job:run")
ROLES = {"owner": {"model_owner"}, "assessor": {"assessor"}, "approver": {"release_authority"},
         "auditor": {"auditor"}, "operator": {"test_operator"}, "worker": {"worker"}}


@unittest.skipIf(TestClient is None, "Console HTTP test dependencies are unavailable")
class ProductionIdentityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.now = int(time.time())
        principals = {}
        grants = []
        for subject, roles in ROLES.items():
            principals[(ISSUER, subject)] = PrincipalAuthority(
                issuer=ISSUER, subject=subject, person_id="person-" + subject,
                kind="workload" if subject == "worker" else "human",
                client_ids=frozenset({"fixture-client"}))
            grants.append(CaseGrant(person_id="person-" + subject, agency_id="agency-fixture",
                                    project_id="project-fixture", case_id="case-a", roles=frozenset(roles)))
        self.authority = AuthorityState(
            revision=1, fresh_until=self.now + 120, available=True,
            active_key_ids=frozenset({"fixture-key"}), revoked_token_ids=frozenset(),
            principals=principals, grants=tuple(grants))
        self.service = FixtureIdentityService(
            AccessTokenVerifier(ISSUER, AUDIENCE, {"fixture-key": self.key.public_key()}),
            self.authority,
            [CaseRecord("case-a", "agency-fixture", "project-fixture", "person-owner"),
             CaseRecord("case-b", "agency-fixture", "other-project", "person-owner")],
            now=lambda: self.now)
        self.client = TestClient(create_fixture_app(self.service, environment="public_fixture"))
        self.addCleanup(self.client.close)

    def token(self, subject="owner", **changes):
        payload = {"iss": ISSUER, "sub": subject, "aud": AUDIENCE, "iat": self.now, "nbf": self.now,
                   "exp": self.now + 90, "jti": uuid.uuid4().hex, "client_id": "fixture-client",
                   "scope": " ".join(ACTIONS), "case_ids": ["case-a", "case-b"]}
        if subject != "worker":
            payload.update(acr="urn:mra:fixture:mfa", auth_time=self.now)
        payload.update(changes)
        return jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "fixture-key", "typ": "at+jwt"})

    def headers(self, subject="owner", **changes):
        return {"Authorization": "Bearer " + self.token(subject, **changes)}

    def proposal(self, revision=1):
        return {"artifact_sha256": "a" * 64, "evidence_sha256": "b" * 64,
                "policy_sha256": "c" * 64, "recipient_id": "fictional-recipient", "revision": revision}

    def submit(self, revision=1):
        result = self.client.post("/v1/cases/case-a/proposals", headers=self.headers(), json=self.proposal(revision))
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()["proposal_digest"]

    def review(self, kind, subject, digest, **claims):
        return self.client.post("/v1/cases/case-a/" + kind, headers=self.headers(subject, **claims),
                                json={"expected_digest": digest})

    def update_authority(self, **changes):
        self.authority = replace(self.authority, revision=self.authority.revision + 1, **changes)
        self.service._replace_authority_for_fixture(self.authority)

    def test_explicit_fixture_factory_refuses_production_and_health_is_non_authorizing(self):
        for environment in ("prod", "production", "staging", ""):
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                create_fixture_app(self.service, environment=environment)
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["fixture_only"])
        self.assertFalse(response.json()["authorization_eligible"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        for route in ("/token", "/login", "/v1/roles", "/v1/keys", "/v1/cases/case-a/download", "/api/cases"):
            self.assertEqual(self.client.get(route).status_code, 404)

    def test_bearer_header_is_required_and_duplicate_or_malformed_headers_are_denied(self):
        token = self.token()
        examples = ({}, {"Authorization": token}, {"Authorization": "Basic " + token},
                    {"Authorization": "Bearer  " + token}, {"Authorization": "Bearer not-a-token"},
                    [("Authorization", "Bearer " + token), ("authorization", "Bearer " + token)])
        for headers in examples:
            with self.subTest(headers_kind=type(headers).__name__):
                response = self.client.get("/v1/cases/case-a", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["detail"], "invalid_token")
                self.assertIn("invalid_token", response.headers["www-authenticate"])
                self.assertNotIn(token, response.text)

    def test_browser_cookie_query_token_and_spoofed_identity_headers_do_not_authenticate(self):
        token = self.token()
        self.assertEqual(self.client.get("/v1/cases/case-a?access_token=" + token).status_code, 400)
        self.assertEqual(self.client.get("/v1/cases/case-a", headers={"Cookie": "token=" + token}).status_code, 403)
        self.assertEqual(self.client.get("/v1/cases/case-a", headers={**self.headers(), "Origin": "https://example.invalid"}).status_code, 403)
        self.assertEqual(self.client.get("/v1/cases/case-a", headers={"X-User": "owner", "X-Role": "release_authority"}).status_code, 401)

    def test_real_signed_two_person_review_path_never_authorizes_delivery(self):
        digest = self.submit()
        self.assertEqual(self.review("approval", "approver", digest).status_code, 409)
        self.assertEqual(self.review("assessment", "assessor", digest).status_code, 200)
        response = self.review("approval", "approver", digest)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["reviews_usable"])
        self.assertTrue(response.json()["fixture_only"])
        self.assertFalse(response.json()["authorization_eligible"])
        self.assertFalse(response.json()["model_delivery"])
        reread = self.client.get("/v1/cases/case-a", headers=self.headers("auditor"))
        self.assertEqual(reread.status_code, 200)
        self.assertEqual(reread.json()["proposal_digest"], digest)

    def test_cross_case_project_access_and_cross_case_submission_are_denied(self):
        for path, method, body in (("/v1/cases/case-b", "get", None),
                                   ("/v1/cases/case-b/proposals", "post", self.proposal()),
                                   ("/v1/cases/case-b/assessment", "post", {"expected_digest": "a" * 64})):
            kwargs = {"headers": self.headers()}
            if body is not None:
                kwargs["json"] = body
            self.assertEqual(getattr(self.client, method)(path, **kwargs).status_code, 403)
        self.assertEqual(self.client.get("/v1/cases/case-a", headers=self.headers(case_ids=["case-b"])).status_code, 403)
        self.assertEqual(self.client.get("/v1/cases/unknown", headers=self.headers()).status_code, 403)

    def test_workload_and_auditor_cannot_submit_or_review(self):
        digest = self.submit()
        for subject in ("worker", "auditor"):
            self.assertEqual(self.review("assessment", subject, digest).status_code, 403)
            self.assertEqual(self.review("approval", subject, digest).status_code, 403)
            self.assertEqual(self.client.post("/v1/cases/case-a/proposals", headers=self.headers(subject), json=self.proposal(2)).status_code, 403)
        result = self.client.post("/v1/cases/case-a/job-check", headers=self.headers("worker"), json={})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["allowed"])
        self.assertFalse(result.json()["model_delivery"])
        self.assertEqual(self.client.get("/v1/cases/case-a", headers=self.headers("worker")).status_code, 403)

    def test_current_role_addition_does_not_allow_submitter_or_alias_self_assessment(self):
        digest = self.submit()
        grants = tuple(replace(grant, roles=grant.roles | {"assessor", "release_authority"})
                       if grant.person_id == "person-owner" else grant for grant in self.authority.grants)
        principals = dict(self.authority.principals)
        principals[(ISSUER, "owner-alias")] = replace(principals[(ISSUER, "owner")], subject="owner-alias")
        self.update_authority(grants=grants, principals=principals)
        for subject in ("owner", "owner-alias"):
            self.assertEqual(self.review("assessment", subject, digest).status_code, 403)
            self.assertEqual(self.review("approval", subject, digest).status_code, 403)

    def test_material_change_and_stale_digest_invalidate_earlier_reviews(self):
        first = self.submit()
        self.assertEqual(self.review("assessment", "assessor", first).status_code, 200)
        self.assertEqual(self.review("approval", "approver", first).status_code, 200)
        second = self.submit(2)
        self.assertNotEqual(first, second)
        response = self.client.get("/v1/cases/case-a", headers=self.headers())
        self.assertFalse(response.json()["reviews_usable"])
        self.assertEqual(self.review("approval", "approver", first).status_code, 409)
        self.assertEqual(self.review("approval", "approver", second).status_code, 409)
        self.assertEqual(self.review("assessment", "assessor", second).status_code, 200)
        self.assertEqual(self.review("approval", "approver", second).status_code, 200)
        self.assertEqual(self.review("approval", "approver", second).status_code, 409)

    def test_authority_revision_and_revoked_reviewer_invalidate_stored_approval(self):
        digest = self.submit()
        self.assertEqual(self.review("assessment", "assessor", digest).status_code, 200)
        self.assertEqual(self.review("approval", "approver", digest, jti="review-to-revoke").status_code, 200)
        self.update_authority(revoked_token_ids=frozenset({"review-to-revoke"}))
        current = self.client.get("/v1/cases/case-a", headers=self.headers())
        self.assertEqual(current.status_code, 200)
        self.assertFalse(current.json()["reviews_usable"])
        self.assertEqual(self.review("approval", "approver", digest, jti="review-to-revoke").status_code, 403)

    def test_missing_scope_wrong_client_and_stale_mfa_are_denied_without_mutation(self):
        for claims in ({"scope": "case:read"}, {"client_id": "another-client"},
                       {"acr": "password-only"}, {"auth_time": self.now - 301}):
            response = self.client.post("/v1/cases/case-a/proposals", headers=self.headers(**claims), json=self.proposal())
            self.assertEqual(response.status_code, 403, response.text)
        current = self.client.get("/v1/cases/case-a", headers=self.headers())
        self.assertIsNone(current.json()["proposal"])

    def test_identity_service_outage_and_expired_state_fail_closed(self):
        self.update_authority(available=False)
        self.assertEqual(self.client.get("/v1/cases/case-a", headers=self.headers()).status_code, 503)
        self.update_authority(available=True, fresh_until=self.now)
        self.assertEqual(self.client.post("/v1/cases/case-a/proposals", headers=self.headers(), json=self.proposal()).status_code, 503)

    def test_invalid_bounded_bodies_and_caller_selected_actor_are_refused(self):
        invalid_bodies = ('{"revision":1,"revision":1}', '{"revision":NaN}', "[]", "{" + " " * 8192 + "}")
        for body in invalid_bodies:
            response = self.client.post("/v1/cases/case-a/proposals",
                                        headers={**self.headers(), "Content-Type": "application/json"}, content=body)
            self.assertIn(response.status_code, (400, 413))
        payload = self.proposal()
        payload["submitted_by"] = "person-assessor"
        self.assertEqual(self.client.post("/v1/cases/case-a/proposals", headers=self.headers(), json=payload).status_code, 400)
        self.assertIsNone(self.client.get("/v1/cases/case-a", headers=self.headers()).json()["proposal"])

    def test_invalid_signature_and_id_token_do_not_expose_case_or_claims(self):
        token = self.token()
        wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        payload = jwt.decode(token, options={"verify_signature": False})
        for bad in (jwt.encode(payload, wrong, algorithm="RS256", headers={"kid": "fixture-key", "typ": "at+jwt"}),
                    jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "fixture-key", "typ": "JWT"}),
                    self.token(exp=self.now), self.token(aud="other-service")):
            response = self.client.get("/v1/cases/case-a", headers={"Authorization": "Bearer " + bad})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("case", response.json())
            self.assertNotIn(bad, response.text)


if __name__ == "__main__":
    unittest.main()
