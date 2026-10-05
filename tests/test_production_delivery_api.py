"""HTTP boundary validation; actual candidate transfers are covered by gateway tests."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from model_release_assurance.production_delivery.api import create_fixture_app
from model_release_assurance.production_delivery.contracts import DeliveryError, FLAGS
from model_release_assurance.production_delivery.rehearsal import DeliveryFixture
from model_release_assurance.production_delivery.store import StoreUnavailable


class DeliveryAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="mra-delivery-http-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.f = DeliveryFixture(Path(cls.temporary.name))
        cls.app = create_fixture_app(cls.f.gateway, profile="local_public_fixture")
        cls.client = TestClient(cls.app)
        cls.addClassCleanup(cls.client.close)
        cls.token = cls.f.token("recipient")
        cls.headers = {"Authorization": "Bearer " + cls.token}
        cls.chunk_path = "/v1/cases/case-a/activations/" + "a"*32 + "/chunks"
        cls.payload = {"grant_id": "b"*32, "transfer_id": "c"*32, "offset": 0,
                       "length": 3, "request_id": "d"*32, "chunk_id": "e"*32}

    def test_default_production_and_other_object_services_cannot_start(self):
        for kwargs in ({}, {"profile": "agency_private_cloud"}, {"profile": "production"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(DeliveryError):
                create_fixture_app(self.f.gateway, **kwargs)
        with self.assertRaises(DeliveryError): create_fixture_app(self.f.identity, profile="local_public_fixture")

    def test_health_and_metadata_are_uncacheable_and_never_contain_candidate_bytes(self):
        for path, headers in (("/healthz", {}), ("/v1/cases/case-a", {"Authorization": "Bearer " + self.f.token("auditor")})):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["pragma"], "no-cache")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertNotIn("bytes", response.json())
            for key, value in FLAGS.items(): self.assertIs(response.json()[key], value)

    def test_direct_file_object_model_download_and_traversal_routes_are_absent(self):
        for path in ("/v1/objects/"+"a"*64, "/v1/models/a", "/files/candidate.json", "/static/candidate.json",
                     "/native/candidate.json", "/docs", "/openapi.json", "/v1/cases/case-a/../../candidate.json",
                     "/v1/cases/case-a/activations/a/chunks"):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path, headers=self.headers).status_code, (404, 405))

    def test_url_credentials_query_parameters_cookie_and_origin_are_rejected_before_gateway(self):
        with mock.patch.object(self.f.gateway, "deliver_chunk") as deliver:
            for suffix in ("?token=secret", "?access_token=secret", "?path=C%3A%5Ccandidate.json"):
                self.assertEqual(self.client.post(self.chunk_path+suffix, headers=self.headers, json=self.payload).status_code, 400)
            for key in ("Origin", "Cookie"):
                headers = {**self.headers, key: "untrusted"}
                self.assertEqual(self.client.post(self.chunk_path, headers=headers, json=self.payload).status_code, 403)
            deliver.assert_not_called()

    def test_missing_duplicate_malformed_and_wrong_scheme_bearers_are_rejected(self):
        variants = ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "},
                    {"Authorization": "Bearer a b"}, [("Authorization", "Bearer "+self.token),
                                                       ("authorization", "Bearer "+self.token)])
        with mock.patch.object(self.f.gateway, "deliver_chunk") as deliver:
            for headers in variants:
                with self.subTest(headers_type=type(headers).__name__):
                    self.assertEqual(self.client.post(self.chunk_path, headers=headers, json=self.payload).status_code, 401)
            deliver.assert_not_called()

    def test_exact_body_disallows_caller_paths_formats_writers_and_unknown_fields(self):
        with mock.patch.object(self.f.gateway, "deliver_chunk") as deliver:
            for extra in ("artifact_path", "model", "format", "writer", "recipient_id", "admission"):
                self.assertEqual(self.client.post(self.chunk_path, headers=self.headers,
                    json={**self.payload, extra: "untrusted"}).status_code, 400)
            body = dict(self.payload); body.pop("request_id")
            self.assertEqual(self.client.post(self.chunk_path, headers=self.headers, json=body).status_code, 400)
            deliver.assert_not_called()

    def test_duplicate_nonfinite_nonobject_oversized_and_nonjson_bodies_fail_closed(self):
        with mock.patch.object(self.f.gateway, "deliver_chunk") as deliver:
            for raw in (b'{"offset":0,"offset":1}', b'{"offset":NaN}', b'[]', b'null', b'{'):
                response = self.client.post(self.chunk_path, headers={**self.headers, "Content-Type": "application/json"}, content=raw)
                self.assertEqual(response.status_code, 400)
            response = self.client.post(self.chunk_path, headers={**self.headers, "Content-Type": "application/json"}, content=b" "*8193)
            self.assertEqual(response.status_code, 413)
            self.assertEqual(self.client.post(self.chunk_path, headers=self.headers, content="{}").status_code, 415)
            deliver.assert_not_called()

    def test_signed_scope_case_and_wrong_actor_cannot_read_metadata(self):
        for token in (self.f.token("auditor", scopes={"case:read"}), self.f.token("auditor", cases=["case-b"]), self.f.token("owner", scopes={"delivery:read"})):
            self.assertEqual(self.client.get("/v1/cases/case-a", headers={"Authorization": "Bearer "+token}).status_code, 403)

    def test_server_owned_buffer_returns_exact_bytes_and_explicit_nonreceipt_metadata(self):
        receipt = {"status": "returned", "observation_recorded": True,
                   "admission": {"sha256": "a"*64}, **FLAGS}
        def deliver(*args, **kwargs):
            self.assertEqual(args[0], self.token)
            self.assertEqual(kwargs["request_id"], self.payload["request_id"])
            self.assertEqual(kwargs["writer"](b"abc"), 3)
            return receipt
        with mock.patch.object(self.f.gateway, "deliver_chunk", side_effect=deliver):
            response = self.client.post(self.chunk_path, headers=self.headers, json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"abc")
        self.assertEqual(response.headers["x-mra-admission"], "a"*64)
        import json
        self.assertEqual(json.loads(base64.b64decode(response.headers["x-mra-receipt"])), receipt)
        self.assertIn("public-fixture.chunk", response.headers["content-disposition"])

    def test_buffer_is_not_returned_when_observation_or_gateway_fails(self):
        for status, recorded in (("returned", False), ("interrupted", True), ("failed", True)):
            def uncertain(*args, **kwargs):
                kwargs["writer"](b"SHOULD-NOT-RETURN")
                return {"status": status, "observation_recorded": recorded}
            with mock.patch.object(self.f.gateway, "deliver_chunk", side_effect=uncertain):
                response = self.client.post(self.chunk_path, headers=self.headers, json=self.payload)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b"SHOULD-NOT-RETURN", response.content)
        with mock.patch.object(self.f.gateway, "deliver_chunk", side_effect=StoreUnavailable("private detail")):
            response = self.client.post(self.chunk_path, headers=self.headers, json=self.payload)
        self.assertNotIn("private detail", response.text)
        self.assertEqual(response.status_code, 503)

    def test_lifecycle_endpoints_reject_nonempty_bodies_and_get_methods(self):
        for action in ("suspend", "resume", "revoke"):
            path = "/v1/cases/case-a/activations/" + "a"*32 + "/"+action
            with mock.patch.object(self.f.gateway, action) as method:
                self.assertEqual(self.client.post(path, headers=self.headers, json={"reason": "caller"}).status_code, 400)
                self.assertEqual(self.client.get(path, headers=self.headers).status_code, 405)
                method.assert_not_called()

    def test_activation_unknown_field_and_grant_recipient_name_are_not_authority(self):
        headers = {"Authorization": "Bearer "+self.f.token("releaser")}
        with mock.patch.object(self.f.gateway, "activate") as activate:
            response = self.client.post("/v1/cases/case-a/activations", headers=headers,
                json={"campaign_id": "a"*32, "ttl_seconds": 20, "artifact_path": "candidate.json"})
            self.assertEqual(response.status_code, 400); activate.assert_not_called()
        with mock.patch.object(self.f.gateway, "grant") as grant:
            response = self.client.post("/v1/cases/case-a/activations/a/grants", headers=headers,
                json={"recipient_id": "fixture-recipient", "ttl_seconds": 20})
            self.assertEqual(response.status_code, 400); grant.assert_not_called()


if __name__ == "__main__": unittest.main()
