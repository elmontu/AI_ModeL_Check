from __future__ import annotations



import hashlib
import io
import json
import zipfile
import importlib.util

import tempfile

import time

import unittest

from concurrent.futures import ThreadPoolExecutor

from pathlib import Path

from unittest.mock import patch



from model_release_assurance.console.store import Store

from model_release_assurance.console.worker import work_once



HAS_API = all(importlib.util.find_spec(name) is not None for name in ("fastapi", "httpx"))





class QueueTests(unittest.TestCase):

    def setUp(self):

        self.temp = tempfile.TemporaryDirectory()

        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.store = Store(self.root)



    @unittest.skipUnless(all(importlib.util.find_spec(n) for n in ("xgboost", "pandas", "pyarrow", "sklearn")), "training extras unavailable")
    def test_public_training_creates_reassessable_education_case(self):
        from model_release_assurance import workflow
        job = self.store.enqueue("training", options={"name": "Public sample", "dataset": "sklearn-breast-cancer", "preset": "xgboost-small"})
        work_once(self.store, "trainer")
        done = self.store.job(job["id"])
        self.assertEqual(done["state"], "completed", done["error"])
        result = done["result"]
        self.assertTrue(result["training_executed"])
        self.assertEqual(result["red_team"]["status"], "completed")
        self.assertEqual(len(result["red_team"]["tools"]), 11)
        self.assertFalse(result["red_team"]["assessment_eligible"])
        self.assertEqual(result["dataset"]["rows"], 569)
        root = self.store.case_path(result["case_id"])
        preflight = workflow.inspect_project(root)[0]
        self.assertEqual(preflight["issues"], [])
        self.assertEqual(len(preflight["warnings"]), 3)
        reassess = self.store.enqueue("assess", result["case_id"])
        work_once(self.store, "trainer")
        rerun = self.store.job(reassess["id"])
        self.assertEqual(rerun["state"], "completed", rerun["error"])
        self.assertEqual(rerun["result"]["assessment_verdict"], result["verdict"])
        self.assertFalse(rerun["result"]["authorized"])

    def test_atomic_claims_across_independent_connections(self):

        job = self.store.enqueue("reference")

        with ThreadPoolExecutor(max_workers=4) as pool:

            claimed = list(pool.map(lambda n: Store(self.root).claim(str(n)), range(4)))

        self.assertEqual([j["id"] for j in claimed if j], [job["id"]])



    def test_jobs_persist_and_same_case_cannot_overlap(self):

        case = self.store.create_case("Adapter review", "adapter", "public-weights")

        job = self.store.enqueue("check", case["id"])

        with self.assertRaisesRegex(ValueError, "already has"):

            self.store.enqueue("assess", case["id"])

        self.assertEqual(Store(self.root).job(job["id"])["state"], "queued")

        self.assertTrue(work_once(self.store, "worker"))

        done = self.store.job(job["id"])

        self.assertEqual(done["state"], "completed")

        self.assertEqual(done["result"]["status"], "inputs_incomplete")

        self.assertFalse(done["result"]["authorization_eligible"])

        failed = self.store.enqueue("assess", case["id"])

        work_once(self.store, "worker")

        self.assertEqual(self.store.job(failed["id"])["state"], "failed")

        self.assertTrue(list((self.store.case_path(case["id"]) / "runs").glob("*/workflow-result.json")))



    def test_dead_worker_is_not_silently_retried_or_late_completed(self):

        job = self.store.enqueue("reference")

        self.store.claim("old-worker")

        with self.store.connect() as db:

            db.execute("UPDATE jobs SET heartbeat=? WHERE id=?", (time.time() - 200, job["id"]))

        self.store.recover()

        self.store.finish(job["id"], "old-worker", result={"late": True})

        self.assertEqual(self.store.job(job["id"])["state"], "failed")

        self.assertIsNone(self.store.claim("new-worker"))



    def test_wrong_worker_cannot_finish_claim(self):

        job = self.store.enqueue("reference")

        self.store.claim("owner")

        self.store.finish(job["id"], "impostor", result={})

        self.assertEqual(self.store.job(job["id"])["state"], "running")



    def test_worker_errors_are_non_authorizing_and_do_not_expose_raw_secrets(self):

        job = self.store.enqueue("reference")

        with patch("model_release_assurance.console.worker.execute", side_effect=ValueError("private data in error")):

            work_once(self.store, "worker")

        result = self.store.job(job["id"])

        self.assertEqual(result["state"], "failed")

        self.assertNotIn("private data", result["error"])

        self.assertIsNone(result["result"])



    def test_queue_is_bounded_and_only_accepts_named_tasks(self):

        with self.assertRaises(ValueError):

            self.store.enqueue("shell-command")

        with self.assertRaises(ValueError):

            self.store.enqueue("assess")

        for _ in range(20):

            self.store.enqueue("reference")

        with self.assertRaisesRegex(ValueError, "full"):

            self.store.enqueue("reference")



    def test_identifiers_cannot_escape_data_root(self):

        for value in ("..", "../secrets", "C:/Windows", "0" * 32 + "/.."):

            with self.subTest(value=value), self.assertRaises(ValueError):

                self.store.case_path(value)





@unittest.skipUnless(HAS_API, "optional console API dependencies unavailable")

class ConsoleApiTests(unittest.TestCase):

    def setUp(self):

        from fastapi.testclient import TestClient

        from model_release_assurance.console.api import create_app

        self.temp = tempfile.TemporaryDirectory()

        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.client = TestClient(create_app(self.root))

        self.addCleanup(self.client.close)

        self.headers = {"X-MRA-Console": "1"}



    def test_console_assets_and_health(self):

        self.assertEqual(self.client.get("/healthz").status_code, 200)

        index = self.client.get("/")

        self.assertIn("Test before you release", index.text)

        self.assertIn("frame-ancestors 'none'", index.headers["content-security-policy"])

        self.assertEqual(self.client.get("/assets/app.js").status_code, 200)

        self.assertEqual(self.client.get("/assets/project.json").status_code, 404)



    def test_create_case_and_queue_preflight(self):

        payload = {"name": "Fine-tuning test", "kind": "fine-tuned", "route": "named-party-weights"}

        created = self.client.post("/api/cases", json=payload, headers=self.headers)

        self.assertEqual(created.status_code, 201, created.text)

        case = created.json()

        detail = self.client.get("/api/cases/" + case["id"]).json()

        self.assertEqual(len(detail["inputs"]), 8)

        self.assertTrue(all(not item["bound"] for item in detail["inputs"]))

        queued = self.client.post("/api/jobs", json={"kind": "check", "case_id": case["id"]}, headers=self.headers)

        self.assertEqual(queued.status_code, 202)

        work_once(Store(self.root), "worker")

        result = self.client.get("/api/jobs/" + queued.json()["id"]).json()

        self.assertEqual(result["result"]["status"], "inputs_incomplete")



    def test_cross_origin_mutations_and_unknown_hosts_denied(self):

        payload = {"kind": "reference"}

        self.assertEqual(self.client.post("/api/jobs", json=payload).status_code, 202)

        self.assertEqual(self.client.post("/api/jobs", json=payload, headers={**self.headers, "Origin": "https://evil.example"}).status_code, 403)

        self.assertEqual(self.client.get("/api/status", headers={"Host": "evil.example"}).status_code, 400)



    def test_unknown_fields_and_large_bodies_rejected(self):

        result = self.client.post("/api/jobs", json={"kind": "reference", "command": "anything"}, headers=self.headers)

        self.assertEqual(result.status_code, 422)

        result = self.client.post("/api/cases", content='{"name":"' + "x" * 17000 + '"}', headers={**self.headers, "Content-Type": "application/json"})

        self.assertEqual(result.status_code, 413)



    def test_education_binding_modes_and_active_case_guard(self):

        case = self.client.post("/api/cases", json={"name": "Exercise", "kind": "trained", "route": "api"}).json()

        url = "/api/cases/" + case["id"]

        detail = self.client.get(url).json()

        self.assertEqual(detail["mode"], "education")

        self.assertEqual(sum(x["required"] for x in detail["inputs"]), 5)

        artifact = self.root / "fixture.json"

        artifact.write_text("synthetic fixture")

        payload = {"slot": "candidate", "path": str(artifact)}

        self.assertEqual(self.client.post(url + "/bindings", json=payload).status_code, 200)

        self.assertTrue(self.client.get(url).json()["inputs"][0]["bound"])

        for path in ("relative.json", str(self.root), str(self.root / "missing")):

            self.assertEqual(self.client.post(url + "/bindings", json={**payload, "path": path}).status_code, 409)

        self.assertEqual(self.client.post(url + "/bindings", json={**payload, "slot": "other"}).status_code, 422)

        self.assertEqual(self.client.post(url + "/mode", json={"mode": "review"}).status_code, 200)

        self.assertEqual(self.client.post(url + "/bindings", json=payload).status_code, 200)

        self.assertTrue(self.client.get(url).json()["inputs"][0]["bound"])

        self.client.post(url + "/mode", json={"mode": "education"})

        self.client.post("/api/jobs", json={"kind": "check", "case_id": case["id"]})

        self.assertEqual(self.client.post(url + "/bindings", json=payload).status_code, 409)

        self.assertEqual(self.client.post(url + "/mode", json={"mode": "review"}).status_code, 409)



    def test_training_options_persist_and_reject_unsupported_presets(self):
        options = {"name": "Sample training", "dataset": "sklearn-breast-cancer", "preset": "xgboost-small"}
        response = self.client.post("/api/jobs", json={"kind": "training", "training": options})
        self.assertEqual(response.status_code, 202, response.text)
        job = Store(self.root).job(response.json()["id"])
        self.assertEqual(job["options"], options)
        claimed = Store(self.root).claim("trainer")
        Store(self.root).progress(claimed, "Training and exporting XGBoost")
        self.assertEqual(self.client.get("/api/jobs/" + job["id"]).json()["progress"], "Training and exporting XGBoost")
        response = self.client.post("/api/jobs", json={"kind": "reference", "training": options})
        self.assertEqual(response.status_code, 409)
        for field in ("dataset", "preset"):
            response = self.client.post("/api/jobs", json={"kind": "training", "training": {**options, field: "arbitrary"}})
            self.assertEqual(response.status_code, 422)

    def test_model_capabilities_and_dataset_pair_validation(self):
        response = self.client.get("/api/capabilities")
        self.assertEqual(len(response.json()["presets"]), 10)
        response = self.client.post("/api/jobs", json={"kind":"training","training":{"preset":"mlp","dataset":"sklearn-digits"}})
        self.assertEqual(response.status_code, 202)
        response = self.client.post("/api/jobs", json={"kind":"training","training":{"preset":"xgboost-small","dataset":"sklearn-digits"}})
        self.assertEqual(response.status_code, 422)

    def test_worker_status_and_unknown_objects(self):

        self.assertFalse(self.client.get("/api/status").json()["worker_online"])

        Store(self.root).heartbeat("worker")

        self.assertTrue(self.client.get("/api/status").json()["worker_online"])

        self.assertEqual(self.client.get("/api/jobs/" + "0" * 32).status_code, 404)

    def test_language_job_persists_options_and_rejects_mixed_payloads(self):
        response = self.client.post("/api/jobs", json={"kind":"language", "language":{"model":"local-fixture"}})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(Store(self.root).job(response.json()["id"])["options"], {"model":"local-fixture"})
        for payload in ({"kind":"language"}, {"kind":"reference", "language":{"model":"local-fixture"}},
                        {"kind":"language", "language":{"model":"local-fixture"}, "training":{}}):
            self.assertEqual(self.client.post("/api/jobs", json=payload).status_code, 409)


    def test_default_training_options_and_whitespace_language_rejected(self):
        job = self.client.post("/api/jobs", json={"kind":"training"}).json()
        self.assertEqual(job["options"], {"name":"Public data training", "dataset":"sklearn-breast-cancer", "preset":"xgboost-small"})
        response = self.client.post("/api/jobs", json={"kind":"language", "language":{"model":"  "}})
        self.assertEqual(response.status_code, 422)
        with self.assertRaises(ValueError):
            Store(self.root).enqueue("training", options={"preset":"cnn", "dataset":"sklearn-wine"})
        with self.assertRaises(ValueError):
            Store(self.root).enqueue("language")

    def test_cancel_and_explicit_retry_preserve_options_and_attempts(self):
        options = {"name":"Queued lesson", "preset":"logistic", "dataset":"sklearn-wine"}
        job = self.client.post("/api/jobs", json={"kind":"training", "training":options}).json()
        url = "/api/jobs/" + job["id"]
        self.assertEqual(self.client.post(url + "/cancel", json={}).json()["state"], "cancelled")
        self.assertIsNone(Store(self.root).claim("worker"))
        retry = self.client.post(url + "/retry", json={})
        self.assertEqual(retry.status_code, 202, retry.text)
        retry = retry.json()
        self.assertEqual(retry["retry_of"], job["id"])
        self.assertEqual(retry["options"], options)
        self.assertNotEqual(retry["id"], job["id"])
        self.assertEqual(self.client.get(url).json()["state"], "cancelled")
        Store(self.root).claim("worker")
        for action in ("cancel", "retry"):
            self.assertEqual(self.client.post("/api/jobs/"+retry["id"]+"/"+action,json={}).status_code,409)

    def test_artifact_exports_preserve_hashes_and_download_actual_bytes(self):
        store = Store(self.root)
        job = store.enqueue("reference")
        folder = self.root / "jobs" / job["id"] / "artifacts"
        folder.mkdir(parents=True)
        payload = b"synthetic model bytes\x00\xff"
        (folder / "model.bin").write_bytes(payload)
        store.claim("worker")
        store.finish(job["id"], "worker", result={"authorized":False})
        url = "/api/jobs/" + job["id"]
        response = self.client.get(url + "/artifacts")
        self.assertEqual(response.status_code,200,response.text)
        inventory = response.json()
        self.assertFalse(inventory["partial"])
        item = inventory["files"][0]
        self.assertEqual(item["path"], "job/artifacts/model.bin")
        self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())
        download = self.client.get(item["download_url"])
        self.assertEqual(download.content,payload)
        self.assertIn("attachment",download.headers["content-disposition"])
        exported = self.client.get(url + "/bundle")
        self.assertEqual(exported.status_code,200,exported.text if exported.status_code!=200 else "")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            self.assertEqual(archive.read(item["path"]),payload)
            self.assertEqual(json.loads(archive.read("manifest.json"))["files"], inventory["files"])
        for name in ("job/%2E%2E%2Fconsole.sqlite3", "job/C:%5CWindows", "other/console.sqlite3", "job/missing"):
            self.assertIn(self.client.get(url+"/artifacts/"+name).status_code,(404,409))
        with patch("model_release_assurance.console.artifacts.MAX_BUNDLE_BYTES",1):
            self.assertEqual(self.client.get(url + "/bundle").status_code,409)

    def test_failed_assessment_retains_downloadable_diagnostics_and_can_retry(self):
        store = Store(self.root)
        case = store.create_case("Missing evidence", "trained", "public-weights")
        job = store.enqueue("assess",case["id"])
        work_once(store,"worker")
        url = "/api/jobs/"+job["id"]
        done = self.client.get(url).json()
        self.assertEqual(done["state"],"failed")
        inventory = self.client.get(url+"/artifacts").json()
        self.assertTrue(inventory["partial"])
        paths = {item["path"] for item in inventory["files"]}
        self.assertTrue({"job/worker-error.log", "assessment/preflight.json", "assessment/workflow-result.json"}.issubset(paths),paths)
        preflight = self.client.get(url+"/artifacts/assessment/preflight.json").json()
        self.assertTrue(preflight["issues"])
        self.assertEqual(self.client.get(url+"/bundle").status_code,200)
        retry = self.client.post(url+"/retry",json={})
        self.assertEqual(retry.status_code,202,retry.text)
        self.assertEqual(retry.json()["case_id"],case["id"])

    def test_queued_bundle_refused_and_completed_check_has_evidence(self):
        store = Store(self.root)
        case = store.create_case("Preflight", "trained", "api")
        job = store.enqueue("check",case["id"])
        url = "/api/jobs/"+job["id"]
        self.assertEqual(self.client.get(url+"/bundle").status_code,409)
        work_once(store,"worker")
        paths = {item["path"] for item in self.client.get(url+"/artifacts").json()["files"]}
        self.assertTrue({"job/preflight.json","job/console-result.json","job/job-input.json"}.issubset(paths))

    def test_cancelled_case_can_be_edited_and_null_heartbeat_recovers(self):
        store = Store(self.root)
        case = store.create_case("Case cancellation","trained","api")
        first = store.enqueue("check",case["id"])
        store.cancel(first["id"])
        store.edit_case(case["id"],mode="review")
        second = store.enqueue("check",case["id"])
        store.claim("worker")
        with store.connect() as db:
            db.execute("UPDATE jobs SET heartbeat=NULL,started=? WHERE id=?",(time.time()-200,second["id"]))
        store.recover()
        self.assertEqual(store.job(second["id"])["state"],"failed")


if __name__ == "__main__":

    unittest.main()
