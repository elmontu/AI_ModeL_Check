"""Real trained private-model attachment, replay and recipient-only downloads."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_release_assurance import workflow
from model_release_assurance.console.options import TrainingOptions
from model_release_assurance.console.store import Store
from model_release_assurance.console.worker import attach_private_model_case, work_once

HAS_TRAINING = all(importlib.util.find_spec(name) for name in ("numpy", "sklearn"))
HAS_API = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))
PROFILE = "local-private-wine-model-only-v1"


class PrivateModelOptionsTests(unittest.TestCase):
    def test_private_preset_requires_its_fixed_prospective_dataset(self):
        options = TrainingOptions(preset="dp-histogram", dataset="sklearn-wine")
        self.assertEqual(options.model_dump(), {"name": "Public data training", "preset": "dp-histogram", "dataset": "sklearn-wine"})
        for dataset in ("sklearn-breast-cancer", "sklearn-digits", "sklearn-diabetes", "research-acs", "research-bts", "research-hmda", "research-tlc"):
            with self.subTest(dataset=dataset), self.assertRaises(ValueError):
                TrainingOptions(preset="dp-histogram", dataset=dataset)

    def test_old_default_and_cancelled_attempt_options_remain_compatible(self):
        self.assertEqual(TrainingOptions().model_dump(), {"name": "Public data training", "dataset": "sklearn-breast-cancer", "preset": "xgboost-small"})
        with tempfile.TemporaryDirectory(prefix="mra-private-options-") as temporary:
            store = Store(Path(temporary))
            old = store.enqueue("training", options={"name": "Retained old run", "preset": "logistic", "dataset": "sklearn-wine"})
            store.cancel(old["id"])
            saved = store.job(old["id"])
            retried = store.retry(old["id"])
            self.assertEqual(retried["options"], saved["options"])
            self.assertEqual(retried["retry_of"], saved["id"])
            self.assertEqual(store.job(old["id"]), saved)


@unittest.skipUnless(HAS_TRAINING, "private model training dependencies unavailable")
class PrivateModelConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="mra-private-real-worker-")
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.fixture_store = Store(Path(cls.fixture.name))
        cls.old_case = cls.fixture_store.create_case("Retained original case", "trained", "named-party-weights", "education")
        cls.old_project = (cls.fixture_store.case_path(cls.old_case["id"]) / "project.json").read_bytes()
        old_job = cls.fixture_store.enqueue("training", options={"name": "Retained original attempt", "preset": "logistic", "dataset": "sklearn-wine"})
        cls.fixture_store.cancel(old_job["id"])
        cls.old_job = cls.fixture_store.job(old_job["id"])
        job = cls.fixture_store.enqueue("training", options={"name": "Real private Wine model", "preset": "dp-histogram", "dataset": "sklearn-wine"})
        work_once(cls.fixture_store, "private-fixture-worker")
        cls.completed = cls.fixture_store.job(job["id"])
        if cls.completed["state"] != "completed":
            error = cls.fixture_store.root / "jobs" / job["id"] / "worker-error.log"
            detail = error.read_text(encoding="utf-8") if error.exists() else cls.completed["error"]
            raise AssertionError("real private-model worker did not complete: " + str(detail))
        cls.fixture_output = cls.fixture_store.root / "jobs" / job["id"] / "artifacts"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-private-console-")
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name))
        job = self.store.enqueue("training", options={"name": "Private evidence replay", "preset": "dp-histogram", "dataset": "sklearn-wine"})
        claimed = self.store.claim("private-test-worker")
        self.output = self.store.root / "jobs" / job["id"] / "artifacts"
        shutil.copytree(self.fixture_output, self.output, ignore=shutil.ignore_patterns("console-overlap.json"))
        retained = json.loads((self.output / "training-result.json").read_bytes())
        result = attach_private_model_case(self.store, claimed, self.output, retained)
        self.store.finish(job["id"], "private-test-worker", result=result)
        self.job = self.store.job(job["id"])
        self.case_root = self.store.case_path(result["case_id"])
        if HAS_API:
            from fastapi.testclient import TestClient
            from model_release_assurance.console.api import create_app
            self.client = TestClient(create_app(self.store.root))
            self.addCleanup(self.client.close)

    def write_json(self, path, value):
        path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")

    def test_real_worker_preserves_old_case_and_attempt_and_binds_only_recipient_package(self):
        result = self.completed["result"]
        self.assertTrue(result["training_executed"])
        self.assertTrue(result["real_training_executed"])
        self.assertEqual(result["preset"], "dp-histogram")
        self.assertEqual(result["verdict"], "clear")
        self.assertEqual(result["clearance_profile"], PROFILE)
        self.assertFalse(result["authorized"])
        self.assertFalse(result["deployed"])
        self.assertEqual(self.fixture_store.case(self.old_case["id"]), self.old_case)
        self.assertEqual(self.fixture_store.job(self.old_job["id"]), self.old_job)
        self.assertEqual((self.fixture_store.case_path(self.old_case["id"]) / "project.json").read_bytes(), self.old_project)
        project = workflow.load_project(self.case_root)
        candidate = project.files["candidate"]
        request = json.loads((self.output / "assessment-request.json").read_bytes())
        self.assertEqual(Path(candidate.path).name, "recipient-package.json")
        self.assertEqual(candidate.sha256, request["release"]["artifact_sha256"])
        self.assertEqual(request["release"]["artifact_path"], "recipient-package.json")
        self.assertEqual(project.route, "named-party-weights")
        self.assertEqual(project.mode, "education")
        self.assertIn("private-model-clearance", project.supporting_files)

    def test_preflight_and_case_reassessment_replay_the_real_clearance(self):
        from model_release_assurance.private_model_clearance import verify_private_model_run
        with patch("model_release_assurance.private_model_clearance.verify_private_model_run", wraps=verify_private_model_run) as replay:
            preflight, _, _ = workflow.inspect_project(self.case_root)
            self.assertEqual(preflight["issues"], [])
            self.assertGreaterEqual(replay.call_count, 1)
            reassess = self.store.enqueue("assess", self.job["result"]["case_id"])
            work_once(self.store, "private-reassess-worker")
            finished = self.store.job(reassess["id"])
            self.assertEqual(finished["state"], "completed", finished["error"])
            self.assertEqual(finished["result"]["assessment_verdict"], "clear")
            self.assertEqual(finished["result"]["clearance_profile"], PROFILE)
            self.assertEqual(finished["result"]["clearance_scope"], self.job["result"]["clearance_scope"])
            self.assertFalse(finished["result"]["authorized"])
            self.assertGreaterEqual(replay.call_count, 4)

    def test_tampered_package_stops_preflight_and_reassessment(self):
        package = self.output / "recipient-package.json"
        document = json.loads(package.read_bytes())
        document["unexpected_private_field"] = "must refuse"
        self.write_json(package, document)
        self.assertTrue(workflow.inspect_project(self.case_root)[0]["issues"])
        with self.assertRaises(ValueError):
            workflow.assess(self.case_root)

    def test_missing_bound_certificate_refuses_clearance(self):
        (self.output / "clearance-certificate.json").unlink()
        preflight = workflow.inspect_project(self.case_root)[0]
        self.assertTrue(preflight["issues"])
        with self.assertRaises(ValueError):
            workflow.assess(self.case_root)

    def test_changed_dp_source_is_not_admitted_from_true_flags(self):
        request = json.loads((self.output / "assessment-request.json").read_bytes())
        dp = next(value for value in request["analyzer_inputs"] if value["analyzer"] == "dp")
        source = self.output / dp["provenance"]["source_path"]
        value = json.loads(source.read_bytes())
        value["epsilon"] = 0
        value["accountant_replayed"] = True
        value["complete_pipeline"] = True
        self.write_json(source, value)
        self.assertTrue(workflow.inspect_project(self.case_root)[0]["issues"])

    def test_removed_request_markers_cannot_bypass_private_candidate_or_recipe(self):
        request_path = self.output / "assessment-request.json"
        request = json.loads(request_path.read_bytes())
        request["release"]["interface"]["notes"] = "markers removed"
        for value in request["analyzer_inputs"]:
            value["provenance"]["tool"] = "ordinary-external-evidence"
            if value["analyzer"] == "dp":
                value["accountant"] = "unrecognized"
        self.write_json(request_path, request)
        workflow.bind(self.case_root, "request", request_path)
        project = workflow.load_project(self.case_root)
        self.assertNotIn("private-model-clearance", project.supporting_files)
        preflight = workflow.inspect_project(self.case_root)[0]
        self.assertTrue(any("private-model replay certificate" in issue for issue in preflight["issues"]))

    @unittest.skipUnless(HAS_API, "API dependencies unavailable")
    def test_recipient_download_serves_exact_native_package_after_fresh_replay(self):
        from model_release_assurance.private_model_clearance import verify_private_model_run
        with patch("model_release_assurance.private_model_clearance.verify_private_model_run", wraps=verify_private_model_run) as replay:
            response = self.client.get("/api/jobs/" + self.job["id"] + "/recipient-package")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.content, (self.output / "recipient-package.json").read_bytes())
            self.assertIn("application/json", response.headers["content-type"])
            self.assertIn("recipient-package.json", response.headers["content-disposition"])
            self.assertEqual(replay.call_count, 1)
        inventory = self.client.get("/api/jobs/" + self.job["id"] + "/artifacts").json()
        self.assertIn("job/artifacts/recipient-package.json", [entry["path"] for entry in inventory["files"]])

    @unittest.skipUnless(HAS_API, "API dependencies unavailable")
    def test_recipient_download_refuses_other_jobs_missing_ids_and_path_input(self):
        ordinary = self.store.enqueue("training", options={"preset": "logistic", "dataset": "sklearn-wine"})
        pending = self.store.enqueue("training", options={"preset": "dp-histogram", "dataset": "sklearn-wine"})
        self.store.claim("ordinary-fixture-worker")
        self.store.finish(ordinary["id"], "ordinary-fixture-worker", result={"verdict": "clear"})
        for dataset in ("sklearn-breast-cancer", "research-acs", "sklearn-diabetes"):
            response = self.client.post("/api/jobs", json={"kind": "training", "training": {"preset": "dp-histogram", "dataset": dataset}})
            self.assertEqual(response.status_code, 422)
        for job in (ordinary, pending):
            self.assertEqual(self.client.get("/api/jobs/" + job["id"] + "/recipient-package").status_code, 409)
        self.assertEqual(self.client.get("/api/jobs/" + "0" * 32 + "/recipient-package").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs/not-an-id/recipient-package").status_code, 409)
        self.assertEqual(self.client.get("/api/jobs/" + self.job["id"] + "/recipient-package/other.json").status_code, 404)

    @unittest.skipUnless(HAS_API, "API dependencies unavailable")
    def test_recipient_download_refuses_mutated_candidate_and_stored_result(self):
        url = "/api/jobs/" + self.job["id"] + "/recipient-package"
        package = self.output / "recipient-package.json"
        original = package.read_bytes()
        package.write_bytes(original + b" ")
        self.assertEqual(self.client.get(url).status_code, 409)
        package.write_bytes(original)
        modified = dict(self.job["result"], verdict="inconclusive")
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET result=? WHERE id=?", (json.dumps(modified), self.job["id"]))
        self.assertEqual(self.client.get(url).status_code, 409)

    @unittest.skipUnless(HAS_API, "API dependencies unavailable")
    def test_recipient_download_does_not_accept_bare_clear_flags(self):
        url = "/api/jobs/" + self.job["id"] + "/recipient-package"
        (self.output / "clearance-certificate.json").unlink()
        self.assertEqual(self.client.get(url).status_code, 409)


if __name__ == "__main__":
    unittest.main()
