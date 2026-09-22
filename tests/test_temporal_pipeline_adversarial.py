"""Independent stage-bypass and binding probes using temporary toy data only.

Direct SQL changes here model stale/corrupted evidence and exercise fail-closed
binding. They do not claim protection against an administrator able to rewrite
both the ledger and all of its assurance records.
"""
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

HAS_API = all(importlib.util.find_spec(name) is not None for name in ("fastapi", "httpx"))


@unittest.skipUnless(HAS_API, "optional HTTP dependencies unavailable")
class TemporalPipelineAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.operator = self.root / "operator"
        self.operator.mkdir()
        self.db = self.operator / "assurance.sqlite3"
        self.store = AssuranceStore(self.db, budget_micros=2_000_000, scope_digest="a" * 64)
        self.until = int(time.time()) + 600
        self.evidence = self.store.register_evidence(b"temporary provenance", expires_at=self.until)
        self.store.register_authority("operator", expires_at=self.until)
        self.store.register_dataset("b" * 64, record_ids=["unit-A", "unit-B"],
            evidence_digest=self.evidence, expires_at=self.until)
        self.store.register_cache("cache", cache_digest="c" * 64, epsilon_micros=1_000_000,
            record_ids=["unit-A", "unit-B"], evidence_digest=self.evidence, expires_at=self.until)
        self.package = b"temporary fixed artifact; no real model or citizen data"
        for model in ("model-a", "model-b"):
            self.store.register_model(model, cache_id="cache", dataset_digest="b" * 64,
                record_ids=["unit-A", "unit-B"], artifact_bytes=self.package,
                evidence_digest=self.evidence, expires_at=self.until)
        inventory = {"status": "registered_not_released", "db": str(self.db),
            "scope_digest": "a" * 64, "budget_epsilon": 2,
            "authority_id": "operator", "expires_at": self.until,
            "models": [{"step": number, "model_id": model, "family": "toy", "dataset": "toy"}
                       for number, model in enumerate(("model-a", "model-b"), start=1)]}
        (self.operator / "workflow.json").write_text(json.dumps(inventory), encoding="utf-8")
        self.client = self.new_client()

    def new_client(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        client = TestClient(create_app(self.root / "legacy", repository=self.root / "repo",
            temporal_run=self.root / "missing-study", temporal_operator=self.operator))
        self.addCleanup(client.close)
        return client

    def query(self, statement, args=()):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute(statement, args).fetchall()

    def mutate(self, statement, args=()):
        with closing(sqlite3.connect(self.db)) as db:
            with db:
                db.execute(statement, args)

    def post(self, action, payload, *, ok=True):
        response = self.client.post("/api/temporal/" + action, json=payload)
        if ok:
            self.assertEqual(response.status_code, 200, response.text)
        else:
            self.assertIn(response.status_code, (403, 409, 422, 503), response.text)
        return response

    def prepare(self, request="r1", model="model-a", revision=0):
        return self.post("prepare", {"request_id": request, "model_id": model, "expected_revision": revision})

    def checks(self, request="r1"):
        self.post("checks", {"request_id": request})
        rows = self.query("SELECT check_digest FROM tp_checks WHERE request_id=?", (request,))
        self.assertEqual(len(rows), 1)
        return rows[0][0]

    def review(self, request="r1", digest=None):
        if digest is None:
            digest = self.query("SELECT check_digest FROM tp_checks WHERE request_id=?", (request,))[0][0]
        return self.post("review", {"request_id": request, "check_digest": digest,
            "rationale": "I reviewed the bounded attribute-DP disclosure scope for this toy fixture.",
            "accept_scope": True})

    def approved(self, request="r1", model="model-a", revision=0):
        self.prepare(request, model, revision)
        self.checks(request)
        self.review(request)

    def assert_unspent(self):
        self.assertEqual(self.query("SELECT COUNT(*) FROM charges")[0][0], 0)
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='revision'")[0][0], "0")
        self.assertEqual(self.query("SELECT COUNT(*) FROM requests WHERE receipt IS NOT NULL")[0][0], 0)

    def download(self, request="r1"):
        return self.client.get("/api/temporal/downloads/" + request)

    def test_read_only_status_does_not_install_pipeline_schema(self):
        before = self.db.read_bytes()
        status = self.client.get("/api/temporal/operator")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "available")
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE name LIKE 'tp_%'"), [])

    def test_direct_core_prepare_and_commit_cannot_skip_web_pipeline(self):
        self.store.prepare("legacy", "model-a", expected_revision=0, authority_id="operator")
        self.post("commit", {"request_id": "legacy"}, ok=False)
        self.assert_unspent()
        self.store.commit("legacy")  # Privileged CLI/core remains an explicit boundary.
        response = self.download("legacy")
        self.assertNotEqual(response.status_code, 200)
        self.assertNotEqual(response.content, self.package)

    def test_checks_and_review_cannot_be_skipped(self):
        self.prepare()
        self.post("review", {"request_id": "r1", "check_digest": "0" * 64,
            "rationale": "Acknowledgement without any server-run checks must not approve.",
            "accept_scope": True}, ok=False)
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.checks()
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assertNotEqual(self.download().status_code, 200)
        self.assert_unspent()

    def test_review_cannot_accept_another_request_digest_or_extra_authority(self):
        self.prepare("first")
        first = self.checks("first")
        self.prepare("second", "model-b")
        second = self.checks("second")
        self.assertNotEqual(first, second)
        body = {"request_id": "second", "check_digest": first,
            "rationale": "This copied acknowledgement must not authorize another request.", "accept_scope": True}
        self.post("review", body, ok=False)
        for extra in ({"authority_id": "forged"}, {"reviewer": "government"},
                      {"reviewed_at": 0}, {"passed": True}, {"review_digest": "0" * 64}):
            self.post("review", dict(body, check_digest=second) | extra, ok=False)
        self.post("review", dict(body, check_digest=second, accept_scope=False), ok=False)
        self.post("commit", {"request_id": "second"}, ok=False)
        self.assert_unspent()

    def test_recheck_after_bound_registry_change_requires_a_new_review(self):
        self.approved()
        self.mutate("UPDATE evidence SET expires_at=expires_at+1 WHERE digest=?", (self.evidence,))
        self.checks()
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()
        self.review()
        self.post("commit", {"request_id": "r1"})

    def test_identical_check_retry_does_not_discard_current_review(self):
        self.approved()
        prior = self.query("SELECT * FROM tp_reviews WHERE request_id='r1'")
        self.checks()
        self.assertEqual(self.query("SELECT * FROM tp_reviews WHERE request_id='r1'"), prior)
        self.post("commit", {"request_id": "r1"})

    def test_coordinated_artifact_replacement_after_review_is_detected(self):
        self.approved()
        replacement = b"different internally self-consistent artifact"
        self.mutate("UPDATE models SET artifact=?,artifact_digest=? WHERE id='model-a'",
            (replacement, hashlib.sha256(replacement).hexdigest()))
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()

    def test_prepared_footprint_cannot_be_shrunk_after_review(self):
        self.approved()
        self.mutate("UPDATE requests SET charge_records=? WHERE id='r1'", ('{"cache":[]}',))
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()

    def test_failed_explicit_checks_durably_remove_old_approval(self):
        self.approved()
        original = self.query("SELECT charge_records FROM requests WHERE id='r1'")[0][0]
        self.mutate("UPDATE requests SET charge_records=? WHERE id='r1'", ('{"cache":[]}',))
        self.post("checks", {"request_id": "r1"}, ok=False)
        self.assertEqual(self.query("SELECT COUNT(*) FROM tp_checks WHERE request_id='r1'")[0][0], 0)
        self.assertEqual(self.query("SELECT COUNT(*) FROM tp_reviews WHERE request_id='r1'")[0][0], 0)
        self.assertGreater(self.query("SELECT COUNT(*) FROM tp_events WHERE request_id='r1'")[0][0], 0)
        self.mutate("UPDATE requests SET charge_records=? WHERE id='r1'", (original,))
        self.client = self.new_client()
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()
        self.checks()
        self.review()
        self.post("commit", {"request_id": "r1"})

    def test_malformed_evidence_failure_cannot_revive_a_prior_review(self):
        self.approved()
        original = self.query("SELECT charge_records FROM requests WHERE id='r1'")[0][0]
        self.mutate("UPDATE requests SET charge_records=? WHERE id='r1'", ('{malformed',))
        self.post("checks", {"request_id": "r1"}, ok=False)
        self.mutate("UPDATE requests SET charge_records=? WHERE id='r1'", (original,))
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()

    def test_manifest_cannot_switch_to_another_registered_model(self):
        self.approved()
        manifest = json.loads(self.query("SELECT manifest FROM requests WHERE id='r1'")[0][0])
        manifest["model_id"] = "model-b"
        self.mutate("UPDATE requests SET manifest=? WHERE id='r1'", (json.dumps(manifest),))
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()

    def test_unrelated_commit_makes_precommit_review_stale(self):
        self.approved()
        self.store.prepare("other", "model-b", expected_revision=0, authority_id="operator")
        self.store.commit("other")
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assertIsNone(self.query("SELECT receipt FROM requests WHERE id='r1'")[0][0])
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='revision'")[0][0], "1")

    def test_core_commit_after_review_still_cannot_bypass_pipeline_commit(self):
        self.approved()
        self.store.commit("r1")
        self.assertNotEqual(self.download().status_code, 200)

    def test_restart_preserves_gates_and_later_ledger_changes_do_not_revoke_delivery(self):
        self.approved()
        self.client = self.new_client()
        self.post("commit", {"request_id": "r1"})
        self.client = self.new_client()
        first = self.download()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.content, self.package)
        self.store.prepare("later", "model-b", expected_revision=1, authority_id="operator")
        self.store.commit("later")
        self.assertEqual(self.download().content, self.package)
        self.post("commit", {"request_id": "r1"})  # Idempotent reviewed retry.
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='revision'")[0][0], "2")

    def test_invalidated_evidence_blocks_after_successful_review(self):
        self.approved()
        self.store.invalidate_evidence(self.evidence)
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()

    def test_final_gate_expiry_rolls_back_budget_and_pipeline_commit(self):
        from model_release_assurance.temporal_assurance.web import ExistingStore
        self.approved()
        current = [self.until - 1]
        def advance_clock(_store, _db):
            current[0] = self.until
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", side_effect=lambda: current[0]), \
             mock.patch.object(ExistingStore, "_after_ledger_write", advance_clock):
            self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()
        self.assertEqual(self.query("SELECT COUNT(*) FROM tp_commits")[0][0], 0)

    def test_failed_commit_preserves_budget_and_can_retry_same_approved_request(self):
        from model_release_assurance.temporal_assurance.web import ExistingStore
        self.approved()
        with mock.patch.object(ExistingStore, "_after_ledger_write", side_effect=sqlite3.OperationalError("toy injected failure")):
            self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()
        self.assertEqual(self.query("SELECT COUNT(*) FROM tp_commits")[0][0], 0)
        self.post("commit", {"request_id": "r1"})
        self.assertEqual(self.download().content, self.package)

    def test_expiry_during_pipeline_commit_audit_prevents_publication(self):
        from model_release_assurance.temporal_assurance.pipeline import Pipeline
        self.approved()
        current = [self.until - 1]
        original = Pipeline.event
        def expire_after_audit(pipeline, action, *args, **kwargs):
            original(pipeline, action, *args, **kwargs)
            if action == "committed":
                current[0] = self.until
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", side_effect=lambda: current[0]), \
             mock.patch.object(Pipeline, "event", expire_after_audit):
            self.post("commit", {"request_id": "r1"}, ok=False)
        self.assert_unspent()
        self.assertEqual(self.query("SELECT COUNT(*) FROM tp_commits")[0][0], 0)

    def test_expiry_during_delivery_audit_prevents_return_of_bytes(self):
        from model_release_assurance.temporal_assurance.pipeline import Pipeline
        self.approved()
        self.post("commit", {"request_id": "r1"})
        current = [self.until - 1]
        original = Pipeline.event
        def expire_after_audit(pipeline, action, *args, **kwargs):
            original(pipeline, action, *args, **kwargs)
            if action == "delivery_authorized":
                current[0] = self.until
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", side_effect=lambda: current[0]), \
             mock.patch.object(Pipeline, "event", expire_after_audit):
            response = self.download()
        self.assertNotEqual(response.status_code, 200)
        self.assertNotEqual(response.content, self.package)
        self.assertEqual(self.query("SELECT COUNT(*) FROM tp_events WHERE action='delivery_authorized'")[0][0], 0)

    def test_deleting_review_after_commit_blocks_delivery_and_retry(self):
        self.approved()
        self.post("commit", {"request_id": "r1"})
        self.mutate("DELETE FROM tp_reviews WHERE request_id='r1'")
        self.assertNotEqual(self.download().status_code, 200)
        self.post("commit", {"request_id": "r1"}, ok=False)

    def test_revocation_blocks_deliveries_without_refunding_charges(self):
        self.approved()
        self.post("commit", {"request_id": "r1"})
        before = self.query("SELECT * FROM charges ORDER BY cache_id,record_id")
        self.post("revoke", {"request_id": "r1"})
        self.assertNotEqual(self.download().status_code, 200)
        self.post("commit", {"request_id": "r1"}, ok=False)
        self.assertEqual(self.query("SELECT * FROM charges ORDER BY cache_id,record_id"), before)


if __name__ == "__main__":
    unittest.main()
