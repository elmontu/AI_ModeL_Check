from __future__ import annotations

import importlib.util
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from unittest.mock import patch

from model_release_assurance import government_audit, workflow
from model_release_assurance.console.store import Store


class GovernmentAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Store(self.root / "console")
        self.case = self.store.create_case("Government education case", "fine-tuned", "public-weights")
        self.case_id = self.case["id"]
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text('{"review":"local evidence, not approval"}\n', encoding="utf-8")
        self.store.edit_case(self.case_id, slot="evaluation-plan", path=str(self.evidence))

    def report(self):
        return self.store.government_audit_report(self.case_id)

    def payload(self, **changes):
        result = {"control_id": "purpose-omission-utility", "status": "evidence_recorded",
                  "rationale": "The bound plan records a proposed omission comparison for review.",
                  "evidence_slots": ["evaluation-plan"],
                  "expected_context_sha256": self.report()["context_sha256"]}
        result.update(changes)
        return result

    @staticmethod
    def control(report, identifier="purpose-omission-utility"):
        return next(item for item in report["controls"] if item["id"] == identifier)

    def test_catalog_and_empty_case_are_non_authorizing(self):
        catalog = government_audit.catalog()
        self.assertEqual(len(catalog["controls"]), 12)
        self.assertEqual(len({item["id"] for item in catalog["controls"]}), 12)
        report = self.report()
        self.assertEqual(report["summary"], {"recorded": 0, "needs_work": 0, "not_started": 12})
        self.assertEqual(report["history_count"], 0)
        self.assertFalse(report["authorization_eligible"])
        self.assertFalse(report["scientific_adequacy_verified"])
        self.assertEqual(report["mode"], "education")
        catalog["controls"][0]["title"] = "mutated caller copy"
        self.assertNotEqual(government_audit.catalog()["controls"][0]["title"], "mutated caller copy")

    def test_append_history_persists_and_read_does_not_write(self):
        first = self.store.record_government_audit(self.case_id, self.payload())
        self.assertEqual(self.control(first)["state"], "recorded")
        second = self.store.record_government_audit(self.case_id, self.payload(
            status="gap", evidence_slots=[], rationale="The omission comparison has not yet been independently reviewed."))
        current = self.control(second)
        self.assertEqual(current["state"], "needs_work")
        self.assertEqual(current["history_count"], 2)
        self.assertEqual([item["status"] for item in current["history"]], ["gap", "evidence_recorded"])
        self.assertGreater(current["history"][0]["id"], current["history"][1]["id"])
        restarted = Store(self.store.root)
        self.assertEqual(restarted.government_audit_report(self.case_id), second)
        self.assertEqual(restarted.government_audit_report(self.case_id)["history_count"], 2)
        self.assertFalse(second["authorization_eligible"])
        self.assertFalse(second["scientific_adequacy_verified"])

    def test_history_is_bounded_and_count_retains_all_records(self):
        payload = self.payload(status="gap", evidence_slots=[])
        for _ in range(22):
            report = self.store.record_government_audit(self.case_id, payload)
        control = self.control(report)
        self.assertEqual(control["history_count"], 22)
        self.assertEqual(len(control["history"]), 20)
        self.assertTrue(control["history_truncated"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM government_audit_reviews").fetchone()[0], 22)

    def test_not_applicable_is_explicit_rationale_and_never_clearance(self):
        report = self.store.record_government_audit(self.case_id, self.payload(
            status="not_applicable", evidence_slots=[],
            rationale="This declared route does not deliver an interactive hosted endpoint."))
        control = self.control(report)
        self.assertEqual(control["state"], "recorded")
        self.assertEqual(control["latest_review"]["status"], "not_applicable")
        self.assertFalse(report["authorization_eligible"])
        self.assertFalse(report["scientific_adequacy_verified"])
        self.assertEqual(workflow.load_project(self.store.case_path(self.case_id)).mode, "education")

    def test_invalid_review_inputs_cannot_append(self):
        bad_inputs = [
            {"control_id": "invented-control"}, {"status": "approved"},
            {"rationale": "short"}, {"rationale": " " * 25}, {"rationale": "x" * 2001},
            {"evidence_slots": []}, {"evidence_slots": ["candidate"]},
            {"evidence_slots": ["unknown"]}, {"evidence_slots": [str(self.evidence)]},
            {"evidence_slots": ["evaluation-plan", "evaluation-plan"]},
            {"evidence_slots": ["x" * 201]}, {"evidence_slots": [str(i) for i in range(17)]},
            {"expected_context_sha256": "not-a-digest"}, {"unexpected": True},
        ]
        for changes in bad_inputs:
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValueError):
                    self.store.record_government_audit(self.case_id, self.payload(**changes))
        self.assertEqual(self.report()["history_count"], 0)

    def test_supporting_slots_are_bound_and_rechecked(self):
        root = self.store.case_path(self.case_id)
        project = workflow.load_project(root)
        project.supporting_files["training-verification"] = workflow.FileBinding(
            path=str(self.evidence), sha256=workflow.digest(self.evidence))
        workflow.write_json(root / "project.json", project.model_dump(), replace=True)
        report = self.store.record_government_audit(self.case_id, self.payload(evidence_slots=["training-verification"]))
        self.assertEqual(self.control(report)["state"], "recorded")
        self.evidence.write_text("changed training verification", encoding="utf-8")
        self.assertEqual(self.control(self.report())["issues"], ["evidence_changed"])

    def test_mode_change_stales_all_prior_reviews_and_old_submission(self):
        payload = self.payload()
        self.store.record_government_audit(self.case_id, payload)
        self.store.edit_case(self.case_id, mode="review")
        report = self.report()
        self.assertNotEqual(payload["expected_context_sha256"], report["context_sha256"])
        self.assertEqual(self.control(report)["issues"], ["context_changed"])
        self.assertTrue(self.control(report)["latest_review"]["stale"])
        with self.assertRaisesRegex(ValueError, "case context changed"):
            self.store.record_government_audit(self.case_id, payload)
        self.assertEqual(self.report()["history_count"], 1)

    def test_unrelated_package_binding_stales_review(self):
        payload = self.payload()
        self.store.record_government_audit(self.case_id, payload)
        self.store.edit_case(self.case_id, slot="candidate", path=str(self.evidence))
        control = self.control(self.report())
        self.assertEqual(control["issues"], ["context_changed"])
        self.assertEqual(control["state"], "needs_work")

    def test_cited_rebinding_stales_review_even_if_previous_bytes_unchanged(self):
        self.store.record_government_audit(self.case_id, self.payload())
        replacement = self.root / "replacement.json"
        replacement.write_bytes(self.evidence.read_bytes())
        self.store.edit_case(self.case_id, slot="evaluation-plan", path=str(replacement))
        control = self.control(self.report())
        self.assertEqual(control["issues"], ["context_changed", "evidence_changed"])
        self.assertEqual(control["state"], "needs_work")

    def test_review_history_retains_original_hashes_after_new_evidence_binding(self):
        old_hash = workflow.digest(self.evidence)
        self.store.record_government_audit(self.case_id, self.payload())
        self.evidence.write_text("A newly reviewed set of evidence bytes", encoding="utf-8")
        new_hash = workflow.digest(self.evidence)
        self.store.edit_case(self.case_id, slot="evaluation-plan", path=str(self.evidence))
        report = self.report()
        control = self.control(report)
        self.assertEqual(report["evidence_slots"][0]["sha256"], new_hash)
        self.assertNotEqual(old_hash, new_hash)
        self.assertEqual(control["latest_review"]["evidence_sha256"], {"evaluation-plan": old_hash})
        self.assertEqual(control["history"][0]["evidence_sha256"], {"evaluation-plan": old_hash})
        self.assertTrue(control["latest_review"]["stale"])
        self.assertNotIn("evidence_bindings", control["latest_review"])
        self.assertNotIn(str(self.evidence), str(control["history"]))
        report = self.store.record_government_audit(self.case_id, self.payload())
        history = self.control(report)["history"]
        self.assertEqual([item["evidence_sha256"]["evaluation-plan"] for item in history], [new_hash, old_hash])

    def test_tampered_and_missing_bytes_are_never_verified_or_recorded(self):
        original = self.evidence.read_bytes()
        payload = self.payload()
        self.store.record_government_audit(self.case_id, payload)
        self.evidence.write_text("tampered exact bytes", encoding="utf-8")
        for unavailable in (False, True):
            if unavailable:
                self.evidence.unlink()
            report = self.report()
            self.assertEqual(self.control(report)["issues"], ["evidence_changed"])
            self.assertTrue(self.control(report)["latest_review"]["stale"])
            self.assertFalse(report["evidence_slots"][0]["bytes_valid"])
            with self.assertRaisesRegex(ValueError, "evidence changed or is unreadable"):
                self.store.record_government_audit(self.case_id, payload)
        self.evidence.write_bytes(original)
        self.assertEqual(self.control(self.report())["state"], "recorded")
        self.assertEqual(self.report()["history_count"], 1)

    def test_protocol_version_is_part_of_context(self):
        self.store.record_government_audit(self.case_id, self.payload())
        with patch.object(government_audit, "PROTOCOL_VERSION", "future-controls/2"):
            self.assertEqual(self.control(self.report())["issues"], ["context_changed"])

    def test_review_cannot_be_recorded_during_queued_or_running_job(self):
        payload = self.payload()
        self.store.enqueue("check", self.case_id)
        with self.assertRaisesRegex(ValueError, "queued or running job"):
            self.store.record_government_audit(self.case_id, payload)
        self.store.claim("review-test-worker")
        with self.assertRaisesRegex(ValueError, "queued or running job"):
            self.store.record_government_audit(self.case_id, payload)
        self.assertEqual(self.report()["history_count"], 0)

    def test_review_and_rebinding_serialize_then_review_is_stale(self):
        payload = self.payload()
        entered = threading.Event()
        release = threading.Event()
        original = government_audit.checked_bindings

        def paused_check(*args):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test review was never released")
            return original(*args)

        with patch.object(government_audit, "checked_bindings", side_effect=paused_check):
            with ThreadPoolExecutor(max_workers=2) as pool:
                record = pool.submit(self.store.record_government_audit, self.case_id, payload)
                try:
                    self.assertTrue(entered.wait(5))
                    rebind = pool.submit(self.store.edit_case, self.case_id, mode="review")
                    with self.assertRaises(TimeoutError):
                        rebind.result(timeout=0.1)
                finally:
                    release.set()
                self.assertEqual(self.control(record.result(timeout=5))["state"], "recorded")
                rebind.result(timeout=5)
        self.assertEqual(self.control(self.report())["issues"], ["context_changed"])

    def test_rebinding_first_rejects_concurrent_old_context_review(self):
        payload = self.payload()
        entered = threading.Event()
        release = threading.Event()
        original = workflow.bind

        def paused_bind(*args):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test rebinding was never released")
            return original(*args)

        with patch.object(workflow, "bind", side_effect=paused_bind):
            with ThreadPoolExecutor(max_workers=2) as pool:
                rebind = pool.submit(self.store.edit_case, self.case_id, slot="candidate", path=str(self.evidence))
                try:
                    self.assertTrue(entered.wait(5))
                    record = pool.submit(self.store.record_government_audit, self.case_id, payload)
                    with self.assertRaises(TimeoutError):
                        record.result(timeout=0.1)
                finally:
                    release.set()
                rebind.result(timeout=5)
                with self.assertRaisesRegex(ValueError, "case context changed"):
                    record.result(timeout=5)
        self.assertEqual(self.report()["history_count"], 0)


HAS_API = all(importlib.util.find_spec(name) is not None for name in ("fastapi", "httpx"))


@unittest.skipUnless(HAS_API, "console API extras unavailable")
class GovernmentAuditApiTests(unittest.TestCase):
    def test_download_revalidates_bytes_and_preserves_original_evidence_hash(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.console.api import create_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root / "console")
            case = store.create_case("Download review", "trained", "public-weights")
            evidence = root / "evidence.json"
            evidence.write_text('{"review":"original evidence"}', encoding="utf-8")
            original_hash = workflow.digest(evidence)
            store.edit_case(case["id"], slot="evaluation-plan", path=str(evidence))
            payload = {"control_id": "purpose-omission-utility", "status": "evidence_recorded",
                       "rationale": "The bound evidence is recorded for a later independent review.",
                       "evidence_slots": ["evaluation-plan"],
                       "expected_context_sha256": store.government_audit_report(case["id"])["context_sha256"]}
            store.record_government_audit(case["id"], payload)
            client = TestClient(create_app(store.root))
            url = f"/api/cases/{case['id']}/government-audit/download"
            initial = client.get(url)
            self.assertEqual(initial.status_code, 200)
            self.assertEqual(initial.headers["content-disposition"], f'attachment; filename="government-audit-{case["id"]}.json"')
            self.assertEqual(initial.headers["cache-control"], "no-store")
            self.assertEqual(initial.headers["content-type"], "application/json")
            self.assertEqual(GovernmentAuditTests.control(initial.json())["state"], "recorded")
            evidence.write_text("tampered after the earlier report was rendered", encoding="utf-8")
            refreshed = client.get(url)
            report = refreshed.json()
            control = GovernmentAuditTests.control(report)
            self.assertEqual(refreshed.status_code, 200)
            self.assertEqual(control["state"], "needs_work")
            self.assertEqual(control["issues"], ["evidence_changed"])
            self.assertEqual(control["latest_review"]["evidence_sha256"], {"evaluation-plan": original_hash})
            self.assertEqual(control["history"][0]["evidence_sha256"], {"evaluation-plan": original_hash})
            self.assertEqual(report["history_count"], 1)
            self.assertFalse(report["evidence_slots"][0]["bytes_valid"])
            self.assertFalse(report["authorization_eligible"])
            self.assertFalse(report["scientific_adequacy_verified"])
            invalid = client.get("/api/cases/not-a-valid-case-id/government-audit/download")
            self.assertEqual(invalid.status_code, 409)
            self.assertNotIn("content-disposition", invalid.headers)

    def test_catalog_case_records_validation_staleness_and_request_limit(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.console.api import create_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "scope.json"
            evidence.write_text("{}\n", encoding="utf-8")
            client = TestClient(create_app(root / "console"))
            catalog = client.get("/api/government-audit")
            self.assertEqual(catalog.status_code, 200)
            self.assertEqual(len(catalog.json()["controls"]), 12)
            case = client.post("/api/cases", json={"name": "Agency review", "kind": "merged", "route": "named-party-weights"}).json()
            url = f"/api/cases/{case['id']}/government-audit"
            self.assertEqual(client.get(url).status_code, 200)
            self.assertEqual(client.post(f"/api/cases/{case['id']}/bindings", json={"slot": "agency-scope", "path": str(evidence)}).status_code, 200)
            payload = {"control_id": "privacy-adjacency", "status": "evidence_recorded",
                       "rationale": "A reviewer must check the bounded evidence for the protected unit.",
                       "evidence_slots": ["agency-scope"], "expected_context_sha256": client.get(url).json()["context_sha256"]}
            response = client.post(url, json=payload)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertFalse(response.json()["authorization_eligible"])
            self.assertFalse(response.json()["scientific_adequacy_verified"])
            self.assertEqual(client.post(url, json={**payload, "status": "approved"}).status_code, 422)
            self.assertEqual(client.post(url, json={**payload, "evidence_slots": ["../scope.json"]}).status_code, 409)
            self.assertEqual(client.post(url, json={**payload, "rationale": "x" * 17_000}).status_code, 413)
            self.assertEqual(client.post(url, json=payload, headers={"origin": "https://unrelated.example"}).status_code, 403)
            self.assertEqual(client.post(f"/api/cases/{case['id']}/mode", json={"mode": "review"}).status_code, 200)
            self.assertEqual(client.post(url, json=payload).status_code, 409)
            self.assertEqual(client.get(url).json()["history_count"], 1)
            self.assertEqual(client.get("/api/cases/" + "0" * 32 + "/government-audit").status_code, 404)


if __name__ == "__main__":
    unittest.main()
