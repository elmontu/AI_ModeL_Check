"""HTTP-level export boundary tests on a new synthetic-only database."""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


HAS_API = all(importlib.util.find_spec(p) is not None for p in ("fastapi", "httpx"))


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class ExportAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(create_app(Path(self.temp.name)))
        self.addCleanup(self.client.close)

    def post(self, endpoint, payload, expected=200):
        result = self.client.post(endpoint, json=payload)
        self.assertEqual(result.status_code, expected, result.text)
        return result.json()

    def first(self):
        self.post("/api/prepare", {"request_id": "first", "stage": 1, "route": "first", "expected_revision": 0})
        return self.post("/api/commit", {"request_id": "first", "expected_revision": 0})

    def test_dp_planning_preserves_history_and_does_not_certify_unsupported_routes(self):
        before = self.client.get("/api/status").json()
        plan = self.client.get("/api/plan?route=first").json()
        self.assertTrue(plan["ready"])
        self.assertFalse(plan["can_authorize"])
        self.assertEqual(plan["proposed_history_ratio"], 2)
        self.assertFalse(self.client.get("/api/plan?route=retained-state").json()["ready"])
        self.assertEqual(self.client.get("/api/plan?route=dp-sgd").status_code, 422)
        self.assertEqual(before, self.client.get("/api/status").json())
        first = self.first()
        reuse = self.client.get("/api/plan?route=reuse").json()
        self.assertEqual(reuse["reuse_release_id"], first["release_id"])
        self.assertEqual(reuse["current_epsilon"], reuse["proposed_epsilon"])
        self.post("/api/revoke", {"release_id": first["release_id"]})
        blocked = self.client.get("/api/plan?route=reuse").json()
        self.assertEqual(blocked["block_reason"], "latest_release_revoked")

    def test_http_commit_binds_actual_bytes_and_retry_is_identical(self):
        prepared = self.post("/api/prepare", {"request_id": "first", "stage": 1, "route": "first", "expected_revision": 0})
        self.assertNotIn("artifact_sha256", prepared)
        self.assertEqual(self.client.get("/api/exports/first").status_code, 409)
        receipt = self.post("/api/commit", {"request_id": "first", "expected_revision": 0})
        response = self.client.get("/api/exports/" + receipt["release_id"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), receipt["artifact_sha256"])
        self.assertEqual(response.headers["X-Artifact-SHA256"], receipt["artifact_sha256"])
        self.assertEqual(receipt, self.post("/api/commit", {"request_id": "first", "expected_revision": 0}))
        self.assertEqual(response.content, self.client.get("/api/exports/" + receipt["release_id"]).content)

    def test_two_stages_then_revocation_preserves_disclosure(self):
        first = self.first()
        self.post("/api/prepare", {"request_id": "second", "stage": 2, "route": "retained-state", "expected_revision": 1})
        second = self.post("/api/commit", {"request_id": "second", "expected_revision": 1})
        self.assertEqual(second["parent_artifact_sha256"], first["artifact_sha256"])
        evaluation = self.client.get("/api/exports/" + second["release_id"] + "/evaluation")
        self.assertEqual(evaluation.status_code, 200)
        self.assertEqual(evaluation.json()["citizens"], 2048)
        self.post("/api/revoke", {"release_id": second["release_id"]})
        self.assertEqual(self.client.get("/api/exports/" + second["release_id"]).status_code, 409)
        state = self.client.get("/api/status").json()
        self.assertEqual(state["privacy_ratio"], 4)
        self.assertEqual(len(state["releases"]), 2)
        self.assertFalse(state["agency_deployed"])

    def test_unsupported_upload_certificate_and_cross_origin_rejected(self):
        payload = {"request_id": "forged", "stage": 1, "route": "first", "expected_revision": 0, "certificate": {"pass": True}}
        self.post("/api/prepare", payload, expected=422)
        del payload["certificate"]
        result = self.client.post("/api/prepare", json=payload, headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.client.post("/api/prepare", content="x", headers={"Content-Type": "text/plain"}).status_code, 415)
        self.assertEqual(self.client.post("/api/prepare", content="x" * 4097, headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertEqual(self.client.get("/api/status", headers={"Host": "attacker.invalid"}).status_code, 400)
        self.assertEqual(self.client.get("/api/status").json()["revision"], 0)

    def test_no_private_files_or_staged_state_endpoint(self):
        self.first()
        for path in ("/export.sqlite3", "/api/private_state", "/api/jobs/first/bundle", "/assets/store.py"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        status = self.client.get("/api/status").json()
        forbidden = {"private_state", "X", "Y", "A", "E", "B", "noisy_counts", "seed"}
        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for v in value.values():
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)
        walk(status)

    def test_ui_assets_and_security_headers(self):
        page = self.client.get("/synthetic")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Synthetic data only", page.text)
        self.assertEqual(page.headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        for path in ("/assets/app.js", "/assets/style.css"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_capability_discovery_matches_shared_catalog_without_preparing(self):
        from model_release_assurance.export_poc.tools import export_construction_catalog
        response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), export_construction_catalog())
        self.assertFalse(response.json()["can_authorize"])
        status = self.client.get("/api/status").json()
        self.assertEqual(status["candidates"], [])
        self.assertEqual(status["releases"], [])
        self.assertEqual(status["history_ratio"], 1)

    def test_history_verification_is_non_authorizing_and_omits_private_state(self):
        self.first()
        self.post("/api/prepare", {"request_id": "second", "stage": 2,
                                   "route": "independent", "expected_revision": 1})
        response = self.client.get("/api/history/verify")
        self.assertEqual(response.status_code, 200)
        verified = response.json()
        self.assertTrue(verified["valid"])
        self.assertFalse(verified["can_authorize"])
        self.assertEqual(verified["committed_count"], 1)
        self.assertEqual(verified["prepared_count"], 1)
        self.assertEqual(verified["history_ratio"], 2)
        encoded = json.dumps(verified)
        for key in ('"private_state"', '"X"', '"Y"', '"A"', '"E"', '"state_digest"'):
            self.assertNotIn(key, encoded)

    def test_accounting_corruption_blocks_verification_status_and_delivery(self):
        first = self.first()
        with closing(sqlite3.connect(Path(self.temp.name) / "export.sqlite3")) as db:
            db.execute("UPDATE meta SET privacy_ratio=1 WHERE id=1")
            db.commit()
        for endpoint in ("/api/history/verify", "/api/status", "/api/exports/" + first["release_id"]):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["code"], "tampered")
        with closing(sqlite3.connect(Path(self.temp.name) / "export.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM releases").fetchone()[0], 1)


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class ConsoleExportDiscoveryTests(unittest.TestCase):
    def test_console_discovers_export_capabilities_without_creating_export_store(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.console.api import create_app
        from model_release_assurance.export_poc.tools import export_construction_catalog
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with TestClient(create_app(root)) as client:
                response = client.get("/api/export-capabilities")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), export_construction_catalog())
                self.assertFalse(response.json()["agency_deployed"])
                self.assertEqual(client.post("/api/prepare", json={}).status_code, 404)
            self.assertEqual(list(root.rglob("export.sqlite3")), [])
            self.assertEqual(list(root.rglob(".export-history")), [])


if __name__ == "__main__":
    unittest.main()
