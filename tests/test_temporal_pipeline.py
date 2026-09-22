"""Persistence, transaction and audit tests for the enforced local web pipeline."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock

from test_temporal_assurance_web import HAS_API, TemporalWebFixture


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class TemporalPipelineTests(TemporalWebFixture, unittest.TestCase):
    def sql(self, statement, args=()):
        with self.store._transaction() as db:
            return [tuple(row) for row in db.execute(statement, args)]

    def test_get_creates_no_pipeline_schema_but_prepare_records_first_stage(self):
        response = self.client.get("/api/temporal/operator").json()
        self.assertEqual(response["workflow"]["version"], "temporal-pipeline-v1")
        self.assertTrue(response["workflow"]["server_enforced"])
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE name LIKE 'tp_%'"), [])
        provenance = response["models"][0]["provenance"]
        self.assertEqual(provenance["training_units"], 1)
        self.assertEqual(provenance["serving_units"], 0)
        prepared = self.prepare()["request"]
        self.assertEqual(prepared["pipeline"]["state"], "prepared")
        self.assertEqual([e["action"] for e in prepared["pipeline"]["events"]], ["prepared"])
        self.assertEqual(self.store.ledger()["charges"], [])

    def test_skipping_checks_or_review_and_fabricated_approval_fail(self):
        self.prepare()
        self.assertEqual(self.post("commit", {"request_id": "r1"}, 409)["code"], "pipeline_checks_required")
        checked = self.post("checks", {"request_id": "r1"})["request"]
        self.assertTrue(checked["can_review"])
        self.assertFalse(checked["can_commit"])
        self.assertEqual(self.post("commit", {"request_id": "r1"}, 409)["code"], "pipeline_review_required")
        common = {"request_id": "r1", "check_digest": checked["pipeline"]["check_digest"],
                  "rationale": "I have reviewed the exact prepared package and limited privacy scope.", "accept_scope": True}
        self.assertEqual(self.post("review", common | {"check_digest": "f" * 64}, 409)["code"], "pipeline_stale_check")
        self.assertEqual(self.post("review", common | {"accept_scope": False}, 409)["code"], "pipeline_review_invalid")
        self.assertEqual(self.post("review", common | {"rationale": " " * 30}, 409)["code"], "pipeline_review_invalid")
        self.assertEqual(self.post("review", common | {"authority_id": "injected"}, 422)["code"], "invalid_request")
        self.assertEqual(self.store.revision(), 0)
        approved = self.post("review", common)["request"]
        self.assertTrue(approved["can_commit"])
        self.assertFalse(approved["can_download"])

    def test_checks_review_and_audit_survive_service_restart(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        self.prepare()
        original = self.approve()["request"]["pipeline"]
        replacement = TestClient(create_app(self.repo.parent / "legacy", repository=self.repo,
            temporal_run=self.run, temporal_operator=self.operator))
        self.addCleanup(replacement.close)
        state = replacement.get("/api/temporal/operator").json()["requests"][0]
        self.assertEqual(state["pipeline"]["check_digest"], original["check_digest"])
        self.assertEqual(state["pipeline"]["reviewed_at"], original["reviewed_at"])
        self.assertTrue(state["can_commit"])
        self.assertEqual(replacement.post("/api/temporal/commit", json={"request_id": "r1"}).status_code, 200)
        self.assertEqual(replacement.get("/api/temporal/downloads/r1").content, self.package)

    def test_concurrent_approved_requests_have_one_commit_winner(self):
        for request in ("r1", "r2"):
            self.prepare(request)
            self.approve(request)
        barrier = threading.Barrier(2)
        def attempt(request):
            barrier.wait()
            return self.client.post("/api/temporal/commit", json={"request_id": request})
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, ("r1", "r2")))
        self.assertEqual(sorted(response.status_code for response in outcomes), [200, 409])
        self.assertEqual(self.store.revision(), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_commits")[0][0], 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='committed'")[0][0], 1)

    def test_concurrent_same_request_is_idempotent_without_duplicate_audit(self):
        self.prepare()
        self.approve()
        barrier = threading.Barrier(2)
        def attempt(_):
            barrier.wait()
            return self.client.post("/api/temporal/commit", json={"request_id": "r1"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual([response.status_code for response in outcomes], [200, 200])
        self.assertEqual(self.store.revision(), 1)
        self.assertEqual(len(self.store.ledger()["charges"]), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='committed'")[0][0], 1)

    def test_pipeline_audit_failure_rolls_back_core_receipt_and_spending(self):
        from model_release_assurance.temporal_assurance.pipeline import Pipeline
        self.prepare()
        self.approve()
        original = Pipeline.event
        def interrupted(pipeline, action, message, **metadata):
            original(pipeline, action, message, **metadata)
            if action == "committed":
                raise RuntimeError("Interrupted after pipeline audit write")
        with mock.patch.object(Pipeline, "event", interrupted):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/temporal/commit", json={"request_id": "r1"})
        self.assertEqual(self.store.revision(), 0)
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertEqual(self.sql("SELECT receipt FROM requests WHERE id='r1'"), [(None,)])
        self.assertEqual(self.sql("SELECT * FROM tp_commits"), [])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='committed'")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_reviews")[0][0], 1)
        self.assertEqual(self.commit()["status"], "committed")

    def test_process_crash_after_pipeline_audit_rolls_back_both_layers(self):
        self.prepare()
        self.approve()
        source = str(Path(__file__).resolve().parents[1] / "src")
        code = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from model_release_assurance.export_poc.api import create_app
from model_release_assurance.temporal_assurance.pipeline import Pipeline
original = Pipeline.event
def crash(self, action, message, **metadata):
    original(self, action, message, **metadata)
    if action == 'committed': os._exit(74)
Pipeline.event = crash
client = TestClient(create_app(Path(sys.argv[2]) / 'legacy', repository=Path(sys.argv[3]),
    temporal_run=Path(sys.argv[4]), temporal_operator=Path(sys.argv[5])))
client.post('/api/temporal/commit', json={'request_id': 'r1'})
"""
        result = subprocess.run([sys.executable, "-c", code, source, str(self.repo.parent), str(self.repo),
                                 str(self.run), str(self.operator)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 74, result.stderr.decode())
        self.assertEqual(self.store.revision(), 0)
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertEqual(self.sql("SELECT * FROM tp_commits"), [])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='committed'")[0][0], 0)
        self.assertTrue(self.client.get("/api/temporal/operator").json()["requests"][0]["can_commit"])
        self.assertEqual(self.commit()["status"], "committed")

    def test_later_commit_does_not_expire_original_reviewed_download(self):
        self.prepare()
        self.commit()
        self.prepare("r2", revision=1)
        self.commit("r2")
        self.assertEqual(self.store.revision(), 2)
        self.assertEqual(self.post("commit", {"request_id": "r1"})["request"]["revision"], 1)
        self.assertEqual(self.client.get("/api/temporal/downloads/r1").content, self.package)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='committed'")[0][0], 2)
        delivered = self.sql("SELECT detail FROM tp_events WHERE request_id='r1' AND action='delivery_authorized'")
        self.assertEqual(len(delivered), 1)
        self.assertIn("recipient receipt is not asserted", json.loads(delivered[0][0])["message"])

    def test_changed_review_rationale_remains_in_append_only_audit(self):
        self.prepare()
        first = self.approve()["request"]["pipeline"]
        second_text = "I rechecked the intended recipient scope and accepted this revised local decision rationale."
        self.post("review", {"request_id": "r1", "check_digest": first["check_digest"],
                            "rationale": second_text, "accept_scope": True})
        self.post("review", {"request_id": "r1", "check_digest": first["check_digest"],
                            "rationale": second_text, "accept_scope": True})
        events = [json.loads(row[0]) for row in self.sql("SELECT detail FROM tp_events WHERE action='review_recorded' ORDER BY sequence")]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["review"]["rationale"], first["review_rationale"])
        self.assertEqual(events[1]["review"]["rationale"], second_text)

    def test_committed_core_request_without_pipeline_review_cannot_download(self):
        self.store.prepare("external", "step-01-model-D1", expected_revision=0, authority_id="local-authority")
        self.store.commit("external")
        self.assertEqual(self.client.get("/api/temporal/downloads/external").status_code, 409)
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE name LIKE 'tp_%'"), [])
        state = self.client.get("/api/temporal/operator").json()["requests"][0]
        self.assertEqual(state["pipeline"]["state"], "blocked")
        self.assertFalse(state["can_download"])
        self.assertEqual(self.store.revision(), 1)


if __name__ == "__main__":
    unittest.main()
