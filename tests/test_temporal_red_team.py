"""Endpoint-level, hash-bound red-team gates against temporary toy ledgers."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import time
import unittest
from unittest import mock

from test_temporal_assurance_web import HAS_API, TemporalWebFixture, sha, write_json
from model_release_assurance.export_red_team import (
    ExportRedTeamMetricThreshold, ExportRedTeamPolicy, ExportRedTeamReport,
    ExportRedTeamToolRequirement, ExportRedTeamToolResult, policy_sha256,
    recipient_interface_sha256,
)


@unittest.skipUnless(HAS_API, "console dependencies unavailable")
class TemporalRedTeamTests(TemporalWebFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.now = int(time.time())
        instant = datetime.fromtimestamp(self.now, timezone.utc)
        requirement = ExportRedTeamToolRequirement(
            tool_id="native.membership_loss", implementation_version="1.0.0",
            implementation_sha256="d" * 64, control_protocol_sha256="e" * 64,
            thresholds=[ExportRedTeamMetricThreshold(metric="membership_auc", maximum=.6)],
        )
        policy = ExportRedTeamPolicy(
            artifact_sha256=sha(self.package),
            recipient_interface_sha256=recipient_interface_sha256("full_artifact"),
            dataset_sha256="f" * 64, created_at=instant-timedelta(seconds=100),
            expires_at=instant+timedelta(seconds=300), max_report_age_seconds=120,
            tools=[requirement],
        )
        result = ExportRedTeamToolResult(
            tool_id=requirement.tool_id, implementation_version=requirement.implementation_version,
            implementation_sha256=requirement.implementation_sha256,
            control_protocol_sha256=requirement.control_protocol_sha256,
            status="completed", metrics={"membership_auc": .52}, member_records=20,
            nonmember_records=20, positive_control_auc=1.0, null_control_auc=.5,
            positive_control_member_records=20, positive_control_nonmember_records=20,
            null_control_member_records=20, null_control_nonmember_records=20,
            queries_used=120, runtime_seconds=.01,
        )
        self.screening_report = ExportRedTeamReport(
            policy_sha256=policy_sha256(policy), artifact_sha256=policy.artifact_sha256,
            recipient_interface_sha256=policy.recipient_interface_sha256,
            dataset_sha256=policy.dataset_sha256, started_at=instant-timedelta(seconds=2),
            completed_at=instant-timedelta(seconds=1), tools=[result],
        ).model_dump(mode="json")
        self.inventory.pop("red_team_mode")
        self.inventory["models"][0].update(red_team_policy=policy.model_dump(mode="json"),
            red_team_dataset_sha256=policy.dataset_sha256)
        self.save_inventory()

    def save_inventory(self):
        write_json(self.operator / "workflow.json", self.inventory)

    def sql(self, statement, args=()):
        with self.store._transaction() as db:
            return [tuple(row) for row in db.execute(statement, args)]

    def attach(self, report=None, request="r1", status=200):
        return self.post("red-team", {"request_id": request,
            "report": self.screening_report if report is None else report}, status)

    def assert_unspent(self):
        self.assertEqual(self.store.revision(), 0)
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM requests WHERE receipt IS NOT NULL"), [(0,)])

    def restart(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        self.client = TestClient(create_app(self.repo.parent / "legacy", repository=self.repo,
            temporal_run=self.run, temporal_operator=self.operator))
        self.addCleanup(self.client.close)

    def test_missing_policy_or_report_blocks_checks_and_direct_release_routes(self):
        del self.inventory["models"][0]["red_team_policy"]
        self.save_inventory()
        status = self.client.get("/api/temporal/operator").json()
        self.assertEqual(status["status"], "available")
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE name LIKE 'tp_%'"), [])
        prepared = self.prepare()["request"]
        self.assertEqual(prepared["pipeline"]["state"], "blocked")
        self.assertFalse(prepared["pipeline"]["red_team"]["satisfied"])
        self.assertEqual(self.post("checks", {"request_id": "r1"}, 409)["code"], "pipeline_red_team_required")
        self.post("commit", {"request_id": "r1"}, 409)
        self.assertEqual(self.client.get("/api/temporal/downloads/r1").status_code, 409)
        self.assert_unspent()

    def test_required_report_missing_is_visible_and_checks_fail_without_charging(self):
        prepared = self.prepare()["request"]
        self.assertIn("report_missing", prepared["pipeline"]["red_team"]["reasons"])
        self.post("checks", {"request_id": "r1"}, 409)
        self.post("review", {"request_id": "r1", "check_digest": "0" * 64,
            "rationale": "A client cannot bypass missing attack evidence.", "accept_scope": True}, 409)
        self.post("commit", {"request_id": "r1"}, 409)
        self.assert_unspent()

    def test_passing_report_binding_retry_restart_and_exact_byte_delivery(self):
        self.prepare()
        attached = self.attach()["request"]["pipeline"]["red_team"]
        self.assertTrue(attached["satisfied"])
        self.assertFalse(attached["can_clear"])
        self.assertFalse(attached["authorization_eligible"])
        self.attach()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='red_team_attached'"), [(1,)])
        checked = self.post("checks", {"request_id": "r1"})["request"]["pipeline"]
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", return_value=self.now+10):
            self.post("review", {"request_id": "r1", "check_digest": checked["check_digest"],
                "rationale": "I reviewed the toy screen and its declared limited scope.", "accept_scope": True})
        self.restart()
        self.post("commit", {"request_id": "r1"})
        self.post("commit", {"request_id": "r1"})
        delivered = self.client.get("/api/temporal/downloads/r1")
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(delivered.content, self.package)
        self.assertEqual(delivered.headers["X-Artifact-SHA256"], sha(self.package))
        self.assertEqual(self.store.revision(), 1)
        self.assertEqual(len(self.store.ledger()["charges"]), 1)
        binding = json.loads(self.sql("SELECT binding_json FROM tp_checks")[0][0])["static"]["red_team"]
        self.assertEqual(binding["policy_sha256"], attached["policy_sha256"])
        self.assertEqual(binding["report_sha256"], attached["report_sha256"])
        self.assertNotIn("evaluated_at", binding)
        self.assertEqual(self.attach(status=409)["code"], "pipeline_stage_closed")

    def test_structurally_valid_failed_screens_remain_visible_and_never_charge(self):
        changes = [
            {"status": "failed"}, {"status": "unsupported"}, {"status": "not_run"},
            {"positive_control_auc": .4}, {"null_control_auc": .9},
            {"member_records": 0}, {"positive_control_member_records": 0},
            {"metrics": {"membership_auc": .9}}, {"metrics": {}},
            {"implementation_sha256": "0" * 64}, {"control_protocol_sha256": "0" * 64},
            {"queries_used": 0}, {"runtime_seconds": 0.0}, {"error": "worker failure"},
        ]
        self.prepare()
        for change in changes:
            with self.subTest(change=change):
                report = deepcopy(self.screening_report)
                report["tools"][0].update(change)
                summary = self.attach(report)["request"]["pipeline"]["red_team"]
                self.assertFalse(summary["satisfied"])
                self.assertTrue(summary["reasons"])
                self.post("checks", {"request_id": "r1"}, 409)
                self.post("commit", {"request_id": "r1"}, 409)
                self.assertEqual(self.client.get("/api/temporal/downloads/r1").status_code, 409)
                self.assert_unspent()

    def test_report_policy_artifact_dataset_interface_and_missing_tool_bindings(self):
        self.prepare()
        for field in ("policy_sha256", "artifact_sha256", "dataset_sha256", "recipient_interface_sha256"):
            with self.subTest(field=field):
                report = deepcopy(self.screening_report)
                report[field] = "0" * 64
                self.assertFalse(self.attach(report)["request"]["pipeline"]["red_team"]["satisfied"])
                self.post("checks", {"request_id": "r1"}, 409)
        report = deepcopy(self.screening_report)
        report["tools"] = []
        self.attach(report)
        self.post("checks", {"request_id": "r1"}, 409)
        self.assert_unspent()

    def test_changed_report_clears_review_until_new_checks_and_review(self):
        self.prepare()
        self.attach()
        old = self.approve()["request"]["pipeline"]
        report = deepcopy(self.screening_report)
        report["tools"][0]["metrics"]["membership_auc"] = .53
        new = self.attach(report)["request"]["pipeline"]
        self.assertIsNone(new["check_digest"])
        self.assertIsNone(new["reviewed_at"])
        self.assertTrue(new["red_team"]["satisfied"])
        self.post("commit", {"request_id": "r1"}, 409)
        self.assert_unspent()
        self.assertNotEqual(self.approve()["request"]["pipeline"]["check_digest"], old["check_digest"])
        self.post("commit", {"request_id": "r1"})

    def test_report_expiry_after_commit_denies_download_and_retains_budget(self):
        self.prepare()
        self.attach()
        self.commit()
        before = self.store.ledger()
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", return_value=self.now+121):
            response = self.client.get("/api/temporal/downloads/r1")
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["code"], "pipeline_red_team_required")
            state = self.client.get("/api/temporal/operator").json()["requests"][0]
            self.assertFalse(state["can_download"])
            self.assertIn("report_stale", state["pipeline"]["red_team"]["reasons"])
        self.assertEqual(self.store.ledger(), before)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='delivery_authorized'"), [(0,)])

    def test_expiry_during_commit_audit_rolls_back_spending_and_receipt(self):
        from model_release_assurance.temporal_assurance.pipeline import Pipeline
        self.prepare()
        self.attach()
        self.approve()
        current = [self.now]
        original = Pipeline.event
        def expire(pipeline, action, message, **metadata):
            original(pipeline, action, message, **metadata)
            if action == "committed":
                current[0] = self.now + 121
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", side_effect=lambda: current[0]), mock.patch.object(Pipeline, "event", expire):
            self.post("commit", {"request_id": "r1"}, 409)
        self.assert_unspent()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_commits"), [(0,)])
        self.post("commit", {"request_id": "r1"})

    def test_expiry_during_delivery_audit_rolls_back_delivery_record(self):
        from model_release_assurance.temporal_assurance.pipeline import Pipeline
        self.prepare()
        self.attach()
        self.commit()
        current = [self.now]
        original = Pipeline.event
        def expire(pipeline, action, message, **metadata):
            original(pipeline, action, message, **metadata)
            if action == "delivery_authorized":
                current[0] = self.now + 121
        with mock.patch("model_release_assurance.temporal_assurance.web.time.time", side_effect=lambda: current[0]), mock.patch.object(Pipeline, "event", expire):
            self.assertEqual(self.client.get("/api/temporal/downloads/r1").status_code, 409)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_events WHERE action='delivery_authorized'"), [(0,)])
        self.assertEqual(self.store.revision(), 1)

    def test_policy_must_match_registered_artifact_even_when_report_matches_policy(self):
        from model_release_assurance.export_red_team import parse_policy_json
        self.inventory["models"][0]["red_team_policy"]["artifact_sha256"] = "0" * 64
        policy = parse_policy_json(json.dumps(self.inventory["models"][0]["red_team_policy"]))
        self.screening_report.update(artifact_sha256="0" * 64, policy_sha256=policy_sha256(policy))
        self.save_inventory()
        self.prepare()
        summary = self.attach()["request"]["pipeline"]["red_team"]
        self.assertFalse(summary["satisfied"])
        self.assertIn("artifact_digest_mismatch", summary["reasons"])
        self.post("checks", {"request_id": "r1"}, 409)
        self.assert_unspent()

    def test_explicit_legacy_mode_is_visible_and_does_not_silently_override_a_policy(self):
        self.inventory["red_team_mode"] = "legacy_unassessed"
        self.save_inventory()
        self.prepare()
        # A present policy remains required, even under an explicit legacy flag.
        self.post("checks", {"request_id": "r1"}, 409)
        self.assert_unspent()

    def test_report_attachment_audit_failure_restores_previous_review_atomically(self):
        from model_release_assurance.temporal_assurance.pipeline import Pipeline
        self.prepare()
        self.attach()
        self.approve()
        before = self.sql("SELECT report_digest FROM tp_red_team")
        changed = deepcopy(self.screening_report)
        changed["tools"][0]["metrics"]["membership_auc"] = .53
        original = Pipeline.event
        def interrupt(pipeline, action, message, **metadata):
            original(pipeline, action, message, **metadata)
            if action == "red_team_attached":
                raise RuntimeError("Interrupted attachment audit")
        with mock.patch.object(Pipeline, "event", interrupt):
            with self.assertRaises(RuntimeError):
                self.attach(changed)
        self.assertEqual(self.sql("SELECT report_digest FROM tp_red_team"), before)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_reviews"), [(1,)])
        self.assert_unspent()
        self.post("commit", {"request_id": "r1"})

    def test_trusted_inventory_must_pin_evaluation_dataset(self):
        self.inventory["models"][0].pop("red_team_dataset_sha256")
        self.save_inventory()
        self.prepare()
        self.assertFalse(self.attach()["request"]["pipeline"]["red_team"]["satisfied"])
        self.post("checks", {"request_id": "r1"}, 409)
        self.assert_unspent()

    def test_required_profile_refuses_cached_serving_even_with_matching_report(self):
        self.store.register_model("scored", cache_id="cache", dataset_digest="b" * 64,
            record_ids=["private-unit-A"], artifact_bytes=self.package,
            evidence_digest=self.evidence, expires_at=self.until, scoring="cached",
            serving_records=["private-unit-A"], serving_cache_id="cache")
        self.inventory["models"][0]["model_id"] = "scored"
        self.save_inventory()
        self.post("prepare", {"request_id": "r1", "model_id": "scored", "expected_revision": 0})
        summary = self.attach()["request"]["pipeline"]["red_team"]
        self.assertFalse(summary["satisfied"])
        self.assertTrue(any("model-only" in reason for reason in summary["reasons"]))
        self.post("checks", {"request_id": "r1"}, 409)
        self.assert_unspent()

    def test_attachment_rejects_client_policy_unknown_fields_duplicates_and_nonfinite_json(self):
        self.prepare()
        good = {"request_id": "r1", "report": self.screening_report}
        for extra in ({"policy": self.inventory["models"][0]["red_team_policy"]}, {"red_team_mode": "legacy_unassessed"}):
            self.post("red-team", good | extra, 422)
        report = deepcopy(self.screening_report)
        report["can_clear"] = True
        self.attach(report, status=422)
        raw = json.dumps(good)
        cases = [raw.replace('"request_id": "r1"', '"request_id": "r1", "request_id": "r1"'),
                 raw.replace('"membership_auc": 0.52', '"membership_auc": NaN'),
                 raw.replace('"membership_auc": 0.52', '"membership_auc": 1e9999'),
                 raw.replace('"membership_auc": 0.52', '"membership_auc": 0.52, "membership_auc": 0.52')]
        for content in cases:
            response = self.client.post("/api/temporal/red-team", content=content,
                headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_red_team"), [(0,)])
        self.assert_unspent()

    def test_body_bound_and_existing_origin_boundary_apply_to_report_attachment(self):
        self.prepare()
        good = {"request_id": "r1", "report": self.screening_report}
        self.assertEqual(self.client.post("/api/temporal/red-team", json=good,
            headers={"Origin": "https://outside.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/temporal/red-team", content="{}",
            headers={"Content-Type": "text/plain"}).status_code, 415)
        self.assertEqual(self.client.post("/api/temporal/red-team", content=" " * (2*1024*1024+1),
            headers={"Content-Type": "application/json"}).status_code, 413)
        # Reports legitimately larger than the unchanged 4 KiB action limit work.
        padded = json.dumps(good) + " " * 5000
        self.assertEqual(self.client.post("/api/temporal/red-team", content=padded,
            headers={"Content-Type": "application/json"}).status_code, 200)
        self.assert_unspent()

    def test_report_tampering_after_review_fails_checks_and_commit(self):
        self.prepare()
        self.attach()
        self.approve()
        changed = deepcopy(self.screening_report)
        changed["tools"][0]["metrics"]["membership_auc"] = .99
        self.sql("UPDATE tp_red_team SET report_json=? WHERE request_id='r1'", (json.dumps(changed),))
        self.post("commit", {"request_id": "r1"}, 409)
        self.post("checks", {"request_id": "r1"}, 409)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tp_reviews"), [(0,)])
        self.assert_unspent()


if __name__ == "__main__":
    unittest.main()
