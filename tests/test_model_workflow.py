from __future__ import annotations

import unittest
from pathlib import Path

from model_release_assurance.experimental_workflow import (
    LocalModelWorker,
    ModelWorkerRegistry,
    default_model_worker_registry,
    evaluate_sample_artifact,
    run_experimental_workflow,
)
from model_release_assurance.knowledge import KnowledgeIndex


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reproduction" / "model-audit-workflow" / "xgboost-mlp-manifest.json"


class XgboostMlpWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_experimental_workflow(
            MANIFEST,
            knowledge_index=KnowledgeIndex.build(ROOT),
        )

    def test_executes_xgboost_and_mlp_workers(self) -> None:
        models = {item["kind"]: item for item in self.report["models"]}
        self.assertEqual(set(models), {"xgboost", "mlp"})
        self.assertEqual(models["xgboost"]["functional_evaluation"]["value"], 1.0)
        self.assertEqual(models["mlp"]["functional_evaluation"]["value"], 1.0)
        self.assertEqual(models["xgboost"]["worker"]["service_id"], "mra.model-worker.xgboost")
        self.assertEqual(models["mlp"]["worker"]["service_id"], "mra.model-worker.mlp")

    def test_records_complete_fail_closed_stage_ledger(self) -> None:
        stages = self.report["stages"]
        self.assertEqual(stages[0]["stage"], "manifest_validation")
        self.assertEqual(stages[-1], {
            "stage": "decision_aggregation",
            "status": "completed",
            "decision": "no_release_authorization",
        })
        for experiment_id in ("sample-xgboost-tabular-v1", "sample-mlp-tabular-v1"):
            names = {
                item["stage"] for item in stages if item.get("experiment_id") == experiment_id
            }
            self.assertEqual(names, {"artifact_integrity", "model_execution", "assurance_routing"})
        self.assertEqual(self.report["decision"], "no_release_authorization")
        self.assertTrue(all(not item["can_clear"] for item in self.report["models"]))

    def test_workers_publish_mcp_migration_metadata(self) -> None:
        services = {item["kind"]: item for item in self.report["services"]}
        self.assertEqual(services["xgboost"]["mcp_tool"], "evaluate_xgboost_model")
        self.assertEqual(services["mlp"]["mcp_tool"], "evaluate_mlp_model")
        self.assertTrue(all(not item["can_clear"] for item in services.values()))

    def test_worker_registry_is_replaceable_by_kind(self) -> None:
        replacement = LocalModelWorker("mlp", evaluate_sample_artifact)
        defaults = default_model_worker_registry().workers
        registry = ModelWorkerRegistry((replacement,) + tuple(
            worker for worker in defaults if worker.kind != "mlp"
        ))
        report = run_experimental_workflow(
            MANIFEST,
            knowledge_index=KnowledgeIndex.build(ROOT),
            worker_registry=registry,
        )
        self.assertEqual(len(report["models"]), 2)


if __name__ == "__main__":
    unittest.main()
