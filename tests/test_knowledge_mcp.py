from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from model_release_assurance.knowledge import KnowledgeIndex
from model_release_assurance.mcp_tools import AssuranceToolService
from model_release_assurance.privacy_orchestration import PrivacyAuditPlan


ROOT = Path(__file__).resolve().parents[1]


class KnowledgeIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = KnowledgeIndex.build(ROOT)

    def test_search_returns_hashed_citable_sources(self) -> None:
        hits = self.index.search("atomic registry authorization gateway activation", limit=5)
        self.assertTrue(hits)
        self.assertTrue(any(hit.source == "docs/model-release-assurance-protocol.md" for hit in hits))
        self.assertTrue(all(len(hit.source_sha256) == 64 for hit in hits))
        self.assertTrue(all(len(hit.chunk_id) == 64 for hit in hits))

    def test_index_round_trip_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            self.index.save(path)
            loaded = KnowledgeIndex.load(path)
            self.assertEqual(self.index.chunks, loaded.chunks)
            self.assertEqual(
                self.index.search("lower bound attack cannot clear"),
                loaded.search("lower bound attack cannot clear"),
            )

    def test_empty_query_and_invalid_limit_fail(self) -> None:
        with self.assertRaises(ValueError):
            self.index.search(" ")
        with self.assertRaises(ValueError):
            self.index.search("policy", limit=21)


class AssuranceToolServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = AssuranceToolService(ROOT, KnowledgeIndex.build(ROOT))

    def test_search_is_explicitly_advisory(self) -> None:
        result = self.service.search_assurance_docs("missing evidence", limit=2)
        self.assertTrue(result["advisory_only"])
        self.assertLessEqual(len(result["results"]), 2)

    def test_validate_and_coverage(self) -> None:
        request = json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
        validation = self.service.validate_assessment_request(request)
        self.assertTrue(validation["valid"])
        coverage = self.service.review_model_coverage(request)
        self.assertFalse(coverage["can_clear"])

    def test_schema_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.get_schema("../examples/request.json")
        schema = self.service.get_schema("assessment-request-v3.json")
        self.assertEqual(schema["title"], "AssessmentRequest")

    def test_audit_verification_is_confined_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            database = Path(directory) / "empty.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    """CREATE TABLE audit_events (
                    sequence INTEGER PRIMARY KEY, occurred_at TEXT, event_type TEXT,
                    assessment_id TEXT, payload_json TEXT, previous_hash TEXT, event_hash TEXT
                    )"""
                )
                connection.commit()
            finally:
                connection.close()
            result = self.service.verify_audit_chain(str(database), require_events=False)
            self.assertEqual(result["events"], 0)
        with tempfile.TemporaryDirectory() as outside:
            database = Path(outside) / "outside.sqlite3"
            database.touch()
            with self.assertRaises(ValueError):
                self.service.verify_audit_chain(str(database), require_events=False)

    def test_four_model_experimental_workflow_fails_closed(self) -> None:
        manifest = ROOT / "reproduction" / "model-audit-workflow" / "manifest.json"
        report = self.service.run_experimental_workflow(str(manifest))
        self.assertEqual(report["decision"], "no_release_authorization")
        self.assertEqual({item["kind"] for item in report["models"]}, {"cnn", "lstm", "xgboost", "llm"})
        self.assertTrue(all(item["functional_evaluation"]["value"] == 1.0 for item in report["models"]))
        self.assertTrue(all(not item["can_clear"] for item in report["models"]))
        routes = {item["kind"]: item["assurance_routing"]["status"] for item in report["models"]}
        self.assertEqual(routes["cnn"], "dedicated_worker_required")
        self.assertEqual(routes["lstm"], "dedicated_worker_required")
        self.assertEqual(routes["xgboost"], "generic_core_applicable")
        self.assertEqual(routes["llm"], "interactive_protocol_not_clearable")

    def test_privacy_report_reader_rejects_clearance_claims(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            report_path = Path(directory) / "privacy.json"
            report = {
                "evidence_semantics": "empirical_attack_floors_and_screens_never_clear",
                "decision": "no_release_authorization",
                "models": [{"model": "cnn", "attack": {"can_clear": False}}],
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(
                self.service.read_privacy_audit_report(str(report_path))["decision"],
                "no_release_authorization",
            )
            report["decision"] = "release_as_proposed"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.service.read_privacy_audit_report(str(report_path))

    def test_rag_privacy_plan_is_hash_bound_and_non_clearing(self) -> None:
        raw = self.service.plan_privacy_audit(seed=7, epochs=2)
        plan = PrivacyAuditPlan.model_validate(raw)
        self.assertEqual([item.kind for item in plan.models], ["cnn", "lstm", "xgboost", "llm"])
        self.assertTrue(all(item.guidance for item in plan.models))
        self.assertTrue(all(item.evidence_semantics == "floor_or_screen_never_clear" for item in plan.models))
        raw["epochs"] = 3
        with self.assertRaises(ValueError):
            PrivacyAuditPlan.model_validate(raw)
