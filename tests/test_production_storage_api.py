"""Signed HTTP tests for the separate public-only governed-storage fixture."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from model_release_assurance.production_identity.tokens import AccessTokenVerifier
from model_release_assurance.production_identity.policy import (
    AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, PrincipalAuthority,
)
from model_release_assurance.production_storage.backend import FixtureObjectStore, StorageError
from model_release_assurance.production_storage.service import FixtureStorageService

try:
    from fastapi.testclient import TestClient
    from model_release_assurance.production_storage.api import create_fixture_app, MAX_BODY_BYTES
except ImportError:
    TestClient = None

ISSUER = "https://storage-identity.example.invalid"
AUDIENCE = "urn:mra:public-fixture:storage"
ACTIONS = "object:register object:metadata object:grant object:hold snapshot:freeze object:read job:fixture-job"
ROLES = {"steward": {"data_steward"}, "auditor": {"auditor"}, "operator": {"test_operator"},
         "worker": {"worker"}, "human-worker": {"worker"}, "platform": {"platform"}}
PREFIX = "/v1/cases/case-a/"


@unittest.skipIf(TestClient is None, "Console HTTP test dependencies are unavailable")
class ProductionStorageApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.now = int(time.time())
        principals, grants = {}, []
        for subject, roles in ROLES.items():
            principals[(ISSUER, subject)] = PrincipalAuthority(
                issuer=ISSUER, subject=subject, person_id="person-" + subject,
                kind="workload" if subject == "worker" else "human",
                client_ids=frozenset({"fixture-client"}))
            grants.append(CaseGrant("person-" + subject, "agency-fixture", "project-fixture",
                                    "case-a", frozenset(roles)))
        self.authority = AuthorityState(
            revision=1, fresh_until=self.now + 120, available=True,
            active_key_ids=frozenset({"fixture-key"}), revoked_token_ids=frozenset(),
            principals=principals, grants=tuple(grants))
        self.identity = FixtureIdentityService(
            AccessTokenVerifier(ISSUER, AUDIENCE, {"fixture-key": self.key.public_key()}),
            self.authority,
            [CaseRecord("case-a", "agency-fixture", "project-fixture", "owner"),
             CaseRecord("case-b", "agency-fixture", "other-project", "owner")],
            now=lambda: self.now)
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-storage-http-")
        self.addCleanup(self.temporary.cleanup)
        self.store = FixtureObjectStore(Path(self.temporary.name) / "store")
        self.service = FixtureStorageService(self.identity, self.store)
        self.client = TestClient(create_fixture_app(self.service, environment="public_fixture"))
        self.addCleanup(self.client.close)

    def token(self, subject="steward", **changes):
        payload = {"iss": ISSUER, "sub": subject, "aud": AUDIENCE,
                   "iat": self.now, "nbf": self.now, "exp": self.now + 90,
                   "jti": uuid.uuid4().hex, "client_id": "fixture-client",
                   "scope": ACTIONS, "case_ids": ["case-a", "case-b"]}
        if subject != "worker":
            payload.update(acr="urn:mra:fixture:mfa", auth_time=self.now)
        payload.update(changes)
        return jwt.encode(payload, self.key, algorithm="RS256",
                          headers={"kid": "fixture-key", "typ": "at+jwt"})

    def post(self, route, body, subject="steward", token=None, case="case-a"):
        return self.client.post("/v1/cases/" + case + "/" + route, json=body,
                                headers={"Authorization": "Bearer " + (token or self.token(subject))})

    def register(self):
        response = self.post("fixture-objects", {"fixture_id": "public-counts-v1", "retention_seconds": 60})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["fixture_only"])
        self.assertFalse(response.json()["authorization_eligible"])
        return response.json()["reference"]

    def grant(self, reference, worker_token=None, **changes):
        worker_token = worker_token or self.token("worker")
        body = {"reference": reference, "worker_token": worker_token,
                "job_id": "fixture-job", "ttl_seconds": 30}
        body.update(changes)
        response = self.post("object-read-grants", body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(worker_token, response.text)
        return response.json()["grant_id"], worker_token

    def test_explicit_factory_health_and_no_alternate_intake_routes(self):
        for environment in ("production", "staging", "", None):
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                create_fixture_app(self.service, environment=environment)
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["fixture_only"])
        self.assertFalse(response.json()["model_delivery"])
        for route in ("/upload", "/download", "/token", "/docs", "/openapi.json",
                      PREFIX + "objects", PREFIX + "export", PREFIX + "delete"):
            self.assertEqual(self.client.get(route).status_code, 404)
        self.assertEqual(self.client.delete(PREFIX + "fixture-objects").status_code, 405)

    def test_end_to_end_exact_grant_read_is_single_use_and_disables_caching(self):
        reference = self.register()
        metadata = self.post("object-metadata", {"reference": reference}, "auditor")
        self.assertEqual(metadata.status_code, 200, metadata.text)
        grant_id, token = self.grant(reference)
        response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, token=token)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsInstance(response.json(), dict)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-mra-fixture-only"], "true")
        self.assertEqual(response.headers["x-mra-model-delivery"], "false")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        repeated = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, token=token)
        self.assertIn(repeated.status_code, (403, 409))

    def test_no_cookie_origin_query_or_spoofed_identity_authentication(self):
        reference = self.register()
        payload = {"reference": reference}
        token = self.token()
        for headers, suffix, expected in (
            ({"Cookie": "token=" + token}, "", 403),
            ({"Origin": "https://example.invalid", "Authorization": "Bearer " + token}, "", 403),
            ({}, "?access_token=" + token, 400),
            ({"X-User": "steward", "X-Role": "data_steward"}, "", 401),
        ):
            response = self.client.post(PREFIX + "object-metadata" + suffix, headers=headers, json=payload)
            self.assertEqual(response.status_code, expected)
            self.assertNotIn(token, response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_missing_duplicate_and_malformed_bearer_denied(self):
        for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer  abc"},
                        {"Authorization": "Bearer not-a-token"},
                        [("Authorization", "Bearer " + self.token()),
                         ("authorization", "Bearer " + self.token())]):
            response = self.client.post(PREFIX + "fixture-objects", headers=headers,
                                        json={"fixture_id": "public-counts-v1", "retention_seconds": 60})
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.json()["detail"], "invalid_token")
            self.assertIn("invalid_token", response.headers["www-authenticate"])

    def test_registration_only_accepts_server_catalog_with_bounded_retention(self):
        for body in (
            {"fixture_id": "../private.json", "retention_seconds": 60},
            {"fixture_id": "https://example.invalid/private.json", "retention_seconds": 60},
            {"fixture_id": "public-counts-v1", "retention_seconds": 60, "path": "D:/private.json"},
            {"fixture_id": "public-counts-v1", "retention_seconds": 60, "data": [{"patient": "x"}]},
            {"fixture_id": "public-counts-v1", "retention_seconds": True},
            {"fixture_id": "public-counts-v1", "retention_seconds": 0},
            {"fixture_id": "public-counts-v1", "retention_seconds": 86401},
        ):
            with self.subTest(body=body):
                response = self.post("fixture-objects", body)
                self.assertEqual(response.status_code, 400, response.text)

    def test_http_format_duplicate_nonfinite_encoded_and_oversized_bodies(self):
        headers = {"Authorization": "Bearer " + self.token(), "Content-Type": "application/json"}
        for content in ('{"fixture_id":"public-counts-v1","fixture_id":"other","retention_seconds":60}',
                        '{"fixture_id":"public-counts-v1","retention_seconds":NaN}',
                        "[]", "null", "{", b"\xff"):
            response = self.client.post(PREFIX + "fixture-objects", headers=headers, content=content)
            self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.client.post(PREFIX + "fixture-objects", headers=headers,
                                          content=b" " * (MAX_BODY_BYTES + 1)).status_code, 413)
        self.assertEqual(self.client.post(PREFIX + "fixture-objects",
                                          headers={**headers, "Content-Encoding": "gzip"},
                                          content=b"not decoded").status_code, 415)
        self.assertEqual(self.client.post(PREFIX + "fixture-objects",
                                          headers={**headers, "Content-Type": "application/octet-stream"},
                                          content=b"archive").status_code, 415)

    def test_cross_case_requests_and_altered_reference_fields_are_rejected(self):
        reference = self.register()
        self.assertEqual(self.post("object-metadata", {"reference": reference}, case="case-b").status_code, 403)
        for field, value in (("case_id", "case-b"), ("agency_id", "other"), ("project_id", "other"),
                             ("version_id", "../private"), ("sha256", "0" * 64), ("size_bytes", 0)):
            with self.subTest(field=field):
                response = self.post("object-metadata", {"reference": {**reference, field: value}})
                self.assertIn(response.status_code, (400, 403, 503), response.text)
        response = self.post("object-metadata", {"reference": {**reference, "path": "D:/private.json"}})
        self.assertEqual(response.status_code, 400)

    def test_humans_cannot_read_bytes_even_with_worker_role_or_valid_grant(self):
        reference = self.register()
        grant_id, _ = self.grant(reference)
        for subject in ("steward", "operator", "auditor", "platform", "human-worker"):
            response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, subject)
            self.assertEqual(response.status_code, 403, response.text)
        for subject in ("worker", "operator", "auditor", "platform"):
            response = self.post("fixture-objects", {"fixture_id": "public-counts-v1", "retention_seconds": 60}, subject)
            self.assertEqual(response.status_code, 403, response.text)

    def test_grant_cannot_be_used_by_new_token_or_unsigned_different_job(self):
        reference = self.register()
        grant_id, _ = self.grant(reference)
        response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, "worker")
        self.assertEqual(response.status_code, 403, response.text)
        for worker, job in ((self.token("worker", scope="object:read job:other"), "fixture-job"),
                            (self.token("worker"), "other"), (self.token("human-worker"), "fixture-job")):
            response = self.post("object-read-grants", {"reference": reference, "worker_token": worker,
                                                       "job_id": job, "ttl_seconds": 30})
            self.assertEqual(response.status_code, 403, response.text)

    def test_revoked_grant_stays_denied_and_response_does_not_echo_tokens(self):
        reference = self.register()
        grant_id, token = self.grant(reference)
        response = self.post("object-read-grants/revoke", {"grant_id": grant_id})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, token=token)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertNotIn(token, response.text)

    def test_stale_authority_and_revoked_token_fail_closed(self):
        reference = self.register()
        token = self.token("worker", jti="revoked-worker")
        grant_id, _ = self.grant(reference, token)
        self.authority = replace(self.authority, revision=2, revoked_token_ids=frozenset({"revoked-worker"}))
        self.identity._replace_authority_for_fixture(self.authority)
        response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, token=token)
        self.assertEqual(response.status_code, 403, response.text)
        self.now = self.authority.fresh_until
        self.assertEqual(self.post("object-metadata", {"reference": reference}).status_code, 503)

    def test_storage_failure_is_redacted_and_never_returns_partial_bytes(self):
        reference = self.register()
        grant_id, token = self.grant(reference)
        with patch.object(self.store, "read", side_effect=StorageError("D:/secret/file " + token)):
            response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, token=token)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"], "storage_unavailable")
        self.assertNotIn(token, response.text)
        self.assertNotIn("D:/", response.text)
        self.assertFalse(response.json()["authorization_eligible"])

    def test_snapshot_uses_exact_references_and_refuses_injected_query(self):
        reference = self.register()
        result = self.post("fixture-snapshots", {"references": [reference]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(result.json()["snapshot_digest"]), 64)
        for body in ({"references": []}, {"references": [reference, reference]},
                     {"references": [reference], "query": "SELECT private"},
                     {"references": [reference], "source_url": "https://example.invalid"}):
            response = self.post("fixture-snapshots", body)
            self.assertEqual(response.status_code, 400, response.text)

    def test_hold_and_deletion_checks_do_not_delete_or_read_content(self):
        reference = self.register()
        with patch.object(self.store, "read", side_effect=AssertionError("Metadata must not read bytes")):
            self.assertEqual(self.post("object-hold", {"reference": reference, "held": True}).status_code, 200)
            response = self.post("object-deletion-check", {"reference": reference})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()["model_delivery"])
            self.assertEqual(self.post("object-hold", {"reference": reference, "held": "false"}).status_code, 400)
            self.assertEqual(self.post("object-hold", {"reference": reference, "held": False}, "auditor").status_code, 403)
        grant_id, token = self.grant(reference)
        response = self.post("object-reads", {"reference": reference, "grant_id": grant_id}, token=token)
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
