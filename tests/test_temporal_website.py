"""The mounted website preserves local request and artifact boundaries."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


HAS_API = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class TemporalWebsiteTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.operator = self.root / "absent-operator"
        self.client = TestClient(create_app(
            self.root / "synthetic", repository=self.root / "missing-study-repository",
            temporal_run=self.root / "missing-study", temporal_operator=self.operator,
        ))
        self.addCleanup(self.client.close)

    def test_temporal_home_and_retained_synthetic_lab(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/temporal-assets/app.js", page.text)
        self.assertIn("/synthetic", page.text)
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        self.assertNotIn("'unsafe-inline'", page.headers["Content-Security-Policy"])
        previous = self.client.get("/synthetic")
        self.assertEqual(previous.status_code, 200)
        self.assertIn("Synthetic data only", previous.text)
        self.assertEqual(self.client.get("/api/status").json()["revision"], 0)

    def test_asset_allowlist_and_no_private_study_file_route(self):
        for path in ("/temporal-assets/app.js", "/temporal-assets/style.css"):
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ("/temporal-assets/store.py", "/temporal-assets/assurance.sqlite3",
                     "/api/temporal/evidence/assurance.sqlite3",
                     "/api/temporal/evidence/sanitized-inputs.npz"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_temporal_mutations_share_existing_origin_json_size_and_host_checks(self):
        body = {"request_id": "website-test", "model_id": "missing", "expected_revision": 0}
        for operation in ("prepare", "checks", "review", "commit", "revoke"):
            with self.subTest(operation=operation):
                response = self.client.post("/api/temporal/" + operation, json=body,
                                            headers={"Origin": "https://other.example"})
                self.assertEqual(response.status_code, 403)
                response = self.client.post("/api/temporal/" + operation, content="request_id=test",
                                            headers={"Content-Type": "text/plain"})
                self.assertEqual(response.status_code, 415)
        response = self.client.post("/api/temporal/commit", content='{"request_id":"' + "x"*5000 + '"}',
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.client.get("/api/temporal/operator", headers={"Host": "other.example"}).status_code, 400)
        self.assertFalse(self.operator.exists())

    def test_browsing_unavailable_operator_never_initializes_a_budget(self):
        self.client.get("/api/temporal/study")
        self.client.get("/api/temporal/operator")
        self.client.get("/")
        self.assertFalse(self.operator.exists())


if __name__ == "__main__":
    unittest.main()
