"""HTTP assurance checks using only temporary toy ledgers and research fixtures."""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model_release_assurance.temporal_assurance import AssuranceStore

HAS_API = all(importlib.util.find_spec(p) is not None for p in ("fastapi", "httpx"))


def sha(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(content)
    return sha(content)


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class TemporalWebFixture:
    def setUp(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo, self.run, self.operator = root / "repo", root / "run", root / "operator"
        self.evidence_root = self.repo / "reproduction/acs-temporal-assurance-20260921"
        self.report = self.evidence_root / "report-v2"
        self.operator.mkdir(parents=True)
        self.run.mkdir()
        self.db = self.operator / "assurance.sqlite3"
        self.store = AssuranceStore(self.db, budget_micros=1_000_000, scope_digest="a" * 64)
        self.until = int(time.time()) + 600
        self.evidence = self.store.register_evidence(b"private administrative evidence", expires_at=self.until)
        self.store.register_authority("local-authority", expires_at=self.until)
        self.store.register_dataset("b" * 64, record_ids=["private-unit-A"], evidence_digest=self.evidence, expires_at=self.until)
        self.store.register_cache("cache", cache_digest="c" * 64, epsilon_micros=1_000_000,
            record_ids=["private-unit-A"], evidence_digest=self.evidence, expires_at=self.until)
        self.package = b"exact committed recipient bytes"
        self.store.register_model("step-01-model-D1", cache_id="cache", dataset_digest="b" * 64,
            record_ids=["private-unit-A"], artifact_bytes=self.package, evidence_digest=self.evidence, expires_at=self.until)
        self.inventory = {"status": "registered_not_released", "db": str(self.db), "scope_digest": "a" * 64,
            "budget_epsilon": 1, "authority_id": "local-authority", "expires_at": self.until,
            "red_team_mode": "legacy_unassessed",
            "models": [{"step": 1, "model_id": "step-01-model-D1", "family": "slm_small", "dataset": "D1"}]}
        write_json(self.operator / "workflow.json", self.inventory)
        self.make_study()
        self.client = TestClient(create_app(root / "legacy", repository=self.repo, temporal_run=self.run, temporal_operator=self.operator))
        self.addCleanup(self.client.close)

    def make_study(self):
        registration = {"schedule": [{"step": 1, "family": "slm_small", "dataset": "D1"}]}
        registration_hash = write_json(self.run / "registration.json", registration)
        result = {"status": "complete", "registration_sha256": registration_hash,
            "attempts": 1, "admitted": 1, "blocked": 0, "distinct_source_models": 1,
            "new_training_runs": 0, "new_randomized_response_draws": 0, "runtime_seconds": 1,
            "study_id": "temporary-fixture", "limitations": ["Toy research fixture"],
            "scenarios": [{"id": "cached", "policy": "cached", "admitted": 1, "blocked": 0, "private_path": "DO NOT EXPOSE"}],
            "prefixes": [{"scenario": "cached", "step": 1, "decision": "committed_within_attribute_dp_budget",
                          "evidence_digest": "PRIVATE_INTERNAL_COMMITMENT", "artifact_path": "DO NOT EXPOSE"}]}
        result_hash = write_json(self.run / "results.json", result)
        completion_hash = write_json(self.run / "completion.json", {"status": "complete", "attempts": 1,
                                    "admitted": 1, "blocked": 0, "results_sha256": result_hash})
        receipt = {"status": "verified", "run": str(self.run), "results_sha256": result_hash,
            "registration_sha256": registration_hash, "attempts": 1, "admitted": 1, "blocked": 0,
            "recipient_packages_verified": 1, "metric_groups_rescored": 2, "unit_channel_charges_reconstructed": 1}
        write_json(self.evidence_root / "verification-v1.json", receipt)
        self.report.mkdir(exist_ok=True)
        self.html = b'<html><head><style>body { color: navy; }</style></head><body>Verified report</body></html>'
        (self.report / "index.html").write_bytes(self.html)
        self.svg = b'<svg xmlns="http://www.w3.org/2000/svg"><text style="fill: navy; font-size: 14px">Report</text></svg>'
        (self.report / "attribute-inference-trajectories.svg").write_bytes(self.svg)
        (self.report / "REPORT.md").write_text("Verified fixture report")
        (self.evidence_root / "README.md").write_text("Research summary")
        (self.evidence_root / "THEORY.md").write_text("Conditional argument")
        write_json(self.report / "verification.json", {"status": "complete", "results_sha256": result_hash,
            "registration_sha256": registration_hash,
            "checked_files": {str((self.run / "completion.json").resolve()): completion_hash},
            "report_files": {"index.html": {"sha256": sha(self.html)},
                "attribute-inference-trajectories.svg": {"sha256": sha(self.svg)},
                "REPORT.md": {"sha256": sha((self.report / "REPORT.md").read_bytes())}}})

    def post(self, name, data, status=200):
        response = self.client.post("/api/temporal/" + name, json=data)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def prepare(self, request="r1", revision=0, status=200):
        return self.post("prepare", {"request_id": request, "model_id": "step-01-model-D1", "expected_revision": revision}, status)

    def commit(self, request="r1"):
        state = next(r for r in self.client.get("/api/temporal/operator").json()["requests"] if r["request_id"] == request)
        if state["state"] == "prepared" and state["pipeline"]["state"] != "reviewed":
            self.approve(request)
        return self.post("commit", {"request_id": request})

    def approve(self, request="r1"):
        checked = self.post("checks", {"request_id": request})["request"]["pipeline"]
        return self.post("review", {"request_id": request, "check_digest": checked["check_digest"],
            "rationale": "I reviewed this temporary local test package and its limited attribute privacy scope.", "accept_scope": True})


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class TemporalWebTests(TemporalWebFixture, unittest.TestCase):
    def test_study_is_verified_whitelisted_aggregate_projection(self):
        response = self.client.get("/api/temporal/study")
        self.assertEqual(response.status_code, 200)
        value = response.json()
        self.assertEqual(value["status"], "verified")
        self.assertEqual(value["summary"]["attempts"], 1)
        self.assertEqual(value["schedule"][0]["family"], "slm_small")
        self.assertNotIn("DO NOT EXPOSE", response.text)
        self.assertNotIn("PRIVATE_INTERNAL_COMMITMENT", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_changed_results_and_completion_fail_closed_across_evidence_routes(self):
        for filename in ("results.json", "completion.json", "registration.json"):
            path = self.run / filename
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            self.assertEqual(self.client.get("/api/temporal/study").json()["status"], "unavailable")
            response = self.client.get("/api/temporal/evidence/report.html")
            self.assertEqual(response.status_code, 503)
            self.assertIn("code", response.json())
            path.write_bytes(original)

    def test_missing_study_does_not_break_operator_and_missing_operator_does_not_break_study(self):
        saved = (self.run / "results.json").read_bytes()
        (self.run / "results.json").unlink()
        self.assertEqual(self.client.get("/api/temporal/study").json()["status"], "unavailable")
        self.assertEqual(self.client.get("/api/temporal/operator").json()["status"], "available")
        (self.run / "results.json").write_bytes(saved)
        self.db.unlink()
        self.assertEqual(self.client.get("/api/temporal/operator").json()["status"], "unavailable")
        self.assertEqual(self.client.get("/api/temporal/study").json()["status"], "verified")
        self.post("commit", {"request_id": "r1"}, 503)
        self.assertFalse(self.db.exists())

    def test_evidence_allowlist_and_hashed_style_csp(self):
        response = self.client.get("/api/temporal/evidence/report.html")
        self.assertEqual(response.content, self.html)
        csp = response.headers["content-security-policy"]
        self.assertIn("'sha256-", csp)
        self.assertIn("script-src 'none'", csp)
        self.assertNotIn("unsafe-inline", csp)
        for name in ("assurance.sqlite3", "release-01.zip", "workflow.json", "verification-v1-private.json", "..%2Fworkflow.json"):
            self.assertEqual(self.client.get("/api/temporal/evidence/" + name).status_code, 404)
        (self.report / "index.html").write_bytes(self.html + b"Changed")
        self.assertEqual(self.client.get("/api/temporal/evidence/report.html").status_code, 503)

    def test_readonly_operator_displays_no_unit_ids_private_bytes_or_package(self):
        before = self.db.read_bytes()
        response = self.client.get("/api/temporal/operator")
        self.assertEqual(response.json()["summary"]["revision"], 0)
        self.assertTrue(response.json()["validity"]["valid"])
        for private in ("private-unit-A", "private administrative evidence", self.package.decode()):
            self.assertNotIn(private, response.text)
        self.assertEqual(self.db.read_bytes(), before)

    def test_verified_svg_permits_only_hashed_style_attributes(self):
        response = self.client.get("/api/temporal/evidence/attribute-inference-trajectories.svg")
        self.assertEqual(response.content, self.svg)
        policy = response.headers["content-security-policy"]
        self.assertIn("style-src-attr 'unsafe-hashes' 'sha256-", policy)
        self.assertIn("script-src 'none'", policy)
        self.assertNotIn("unsafe-inline", policy)
        self.assertNotIn("unsafe-eval", policy)

    def test_explicit_prepare_commit_download_revoke_lifecycle(self):
        prepared = self.prepare()["request"]
        self.assertEqual(prepared["state"], "prepared")
        self.assertEqual(prepared["new_unit_charges"], 1)
        self.assertEqual(prepared["budget_preview"]["maximum_spent_epsilon_after"], 1)
        self.assertFalse(prepared["can_commit"])
        self.assertTrue(prepared["can_check"])
        self.assertIn(self.evidence, prepared["evidence_digests"])
        self.assertEqual(self.client.get("/api/temporal/downloads/r1").status_code, 409)
        committed = self.commit()["request"]
        self.assertEqual(committed["state"], "committed")
        self.assertTrue(committed["can_download"])
        downloaded = self.client.get("/api/temporal/downloads/r1")
        self.assertEqual(downloaded.content, self.package)
        self.assertEqual(downloaded.headers["x-artifact-sha256"], sha(self.package))
        self.assertEqual(self.commit()["request"]["revision"], 1)
        self.post("revoke", {"request_id": "r1"})
        self.assertEqual(self.client.get("/api/temporal/downloads/r1").status_code, 409)
        status = self.client.get("/api/temporal/operator").json()
        self.assertEqual(status["requests"][0]["state"], "revoked")
        self.assertEqual(status["summary"]["maximum_spent_epsilon"], 1)

    def test_stale_prepare_and_conflicting_retry_do_not_spend(self):
        self.prepare("first")
        self.prepare("second")
        self.approve("second")
        self.commit("first")
        error = self.post("commit", {"request_id": "second"}, 409)
        self.assertEqual(error["code"], "pipeline_stale")
        error = self.prepare("first", revision=1, status=409)
        self.assertEqual(error["code"], "idempotency_conflict")
        self.assertEqual(self.store.ledger()["committed_releases"], 1)

    def test_expired_authority_and_invalidated_evidence_block_commit_and_download(self):
        self.prepare()
        self.approve()
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", return_value=self.until):
            self.assertFalse(self.client.get("/api/temporal/operator").json()["validity"]["valid"])
            error = self.post("commit", {"request_id": "r1"}, 409)
            self.assertEqual(error["code"], "authority_inactive")
        self.commit()
        self.store.invalidate_evidence(self.evidence)
        status = self.client.get("/api/temporal/operator").json()
        self.assertFalse(status["requests"][0]["can_download"])
        self.assertEqual(self.client.get("/api/temporal/downloads/r1").json()["code"], "evidence_invalidated")

    def test_changed_scope_budget_inventory_and_ledger_bytes_block_all_actions(self):
        self.prepare()
        with self.store._transaction() as db:
            db.execute("UPDATE meta SET value='2000000' WHERE key='budget_micros'")
        self.assertEqual(self.client.get("/api/temporal/operator").json()["status"], "unavailable")
        self.assertEqual(self.post("commit", {"request_id": "r1"}, 503)["code"], "operator_configuration_changed")
        with self.store._transaction() as db:
            db.execute("UPDATE meta SET value='1000000' WHERE key='budget_micros'")
        changed = dict(self.inventory, scope_digest="d" * 64)
        write_json(self.operator / "workflow.json", changed)
        self.assertEqual(self.client.get("/api/temporal/operator").json()["code"], "operator_configuration_changed")
        self.assertEqual(self.post("revoke", {"request_id": "r1"}, 503)["code"], "operator_configuration_changed")

    def test_changed_artifact_is_visible_as_invalid_and_cannot_download(self):
        self.prepare()
        self.commit()
        with self.store._transaction() as db:
            db.execute("UPDATE models SET artifact=?", (b"replacement",))
        status = self.client.get("/api/temporal/operator").json()
        self.assertFalse(status["models"][0]["validity"]["artifact_valid"])
        self.assertFalse(status["requests"][0]["can_download"])
        self.assertEqual(self.client.get("/api/temporal/downloads/r1").json()["code"], "integrity_failure")

    def test_browser_cannot_supply_authority_path_budget_or_unknown_model(self):
        base = {"request_id": "r1", "model_id": "step-01-model-D1", "expected_revision": 0}
        for extra in ({"authority_id": "attacker"}, {"output": "private"}, {"epsilon": 0}, {"scoring": "model_only"}):
            self.assertEqual(self.post("prepare", base | extra, 422)["code"], "invalid_request")
        self.post("prepare", base | {"model_id": "unregistered"}, 404)
        for name in ("reset", "initialize", "register-model", "set-budget"):
            self.assertEqual(self.client.post("/api/temporal/" + name, json={}).status_code, 404)
        self.assertEqual(self.store.revision(), 0)

    def test_parent_origin_host_json_and_body_limits_apply_to_temporal_routes(self):
        data = {"request_id": "r1", "model_id": "step-01-model-D1", "expected_revision": 0}
        response = self.client.post("/api/temporal/prepare", json=data, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/api/temporal/prepare", content=json.dumps(data)).status_code, 415)
        self.assertEqual(self.client.post("/api/temporal/prepare", json={"oversized": "x" * 5000}).status_code, 413)
        self.assertEqual(self.client.get("/api/temporal/operator", headers={"Host": "untrusted.example"}).status_code, 400)
        self.assertEqual(self.store.revision(), 0)

    def test_requests_created_outside_inventory_scope_cannot_be_acted_on(self):
        self.store.register_authority("another-authority", expires_at=self.until)
        self.store.register_model("outside-model", cache_id="cache", dataset_digest="b" * 64,
            record_ids=["private-unit-A"], artifact_bytes=b"off-inventory bytes", evidence_digest=self.evidence, expires_at=self.until)
        self.store.prepare("foreign-model", "outside-model", expected_revision=0, authority_id="local-authority")
        self.store.prepare("foreign-authority", "step-01-model-D1", expected_revision=0, authority_id="another-authority")
        status = self.client.get("/api/temporal/operator").json()
        for request in status["requests"]:
            self.assertFalse(request["can_commit"])
            self.assertFalse(request["can_download"])
            self.assertFalse(request["can_revoke"])
            self.assertIn("request_scope_mismatch", request["validity"]["reasons"])
        for request in ("foreign-model", "foreign-authority"):
            for action in ("commit", "revoke"):
                self.assertEqual(self.post(action, {"request_id": request}, 403)["code"], "request_scope_mismatch")
            self.assertEqual(self.client.get("/api/temporal/downloads/" + request).status_code, 403)
        self.assertEqual(self.store.revision(), 0)
        # Even a locally committed foreign package cannot use the website as a
        # broader delivery capability than its initialized model inventory.
        self.store.commit("foreign-model")
        self.assertEqual(self.client.get("/api/temporal/downloads/foreign-model").status_code, 403)

    def test_empty_duplicate_and_path_redirected_inventories_fail_closed(self):
        for changed in (dict(self.inventory, models=[]),
                        dict(self.inventory, models=self.inventory["models"] * 2),
                        dict(self.inventory, db=str(self.db.parent / "other.sqlite3"))):
            write_json(self.operator / "workflow.json", changed)
            self.assertEqual(self.client.get("/api/temporal/operator").json()["status"], "unavailable")
            self.assertEqual(self.client.post("/api/temporal/prepare", json={"request_id": "r1",
                "model_id": "step-01-model-D1", "expected_revision": 0}).status_code, 503)
        self.assertEqual(self.store.revision(), 0)


if __name__ == "__main__":
    unittest.main()
