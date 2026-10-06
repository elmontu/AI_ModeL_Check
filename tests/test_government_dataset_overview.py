"""Read-only dataset grouping over complete retained console job history."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

from fastapi.testclient import TestClient

from model_release_assurance.console import dataset_overview as d
from model_release_assurance.console.api import create_app
from model_release_assurance.console.research_data import ENV
from model_release_assurance.console.store import Store
from model_release_assurance.public_models import DATASETS


class DatasetOverviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-dataset-overview-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Store(self.root / "console")
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(ENV, None)
        self.tick = 1000

    def case(self, name="Unrelated case label"):
        return self.store.create_case(name, "trained", "named-party-weights")

    def job(self, dataset="sklearn-wine", *, state="completed", preset="logistic", result=None,
            case_id=None, kind="training", options=None, raw_options=None, raw_result=None, retry_of=None):
        self.tick += 1
        job_id = uuid.uuid4().hex
        selection = {"name": "Arbitrary name without dataset semantics", "dataset": dataset, "preset": preset}
        encoded_options = raw_options if raw_options is not None else json.dumps(selection if options is None else options)
        encoded_result = raw_result if raw_result is not None else json.dumps(result) if result is not None else None
        with self.store.connect() as db:
            db.execute("INSERT INTO jobs (id,kind,case_id,state,created,started,finished,options,result,retry_of) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, kind, case_id, state, self.tick, self.tick + .1 if state != "queued" else None,
                 self.tick + .2 if state in {"completed", "failed", "cancelled"} else None,
                 encoded_options, encoded_result, retry_of))
        return job_id

    def item(self, dataset="sklearn-wine"):
        return d.dataset_detail(self.store, dataset)

    def source(self, dataset="research-acs"):
        return {"dataset_id": dataset, "profile_id": dataset.removeprefix("research-"),
            "source_kind": "historical_public_research_matrix", "source_sha256": "a" * 64,
            "metadata": {"source_rows": 27840, "selected_rows": 4096, "feature_count": 8,
                "selection_seed": 20261001, "manifest_sha256": "b" * 64, "sampled_matrix_sha256": "c" * 64,
                "local_public_fixture_pin_verified": True, "historical_training_data_reused": True,
                "fresh_audit_evidence": False, "authenticated_upstream_provenance": False,
                "current_license_approval": False, "person_level_disjointness_established": False,
                "private_path": str(self.root), "source_relative_path": str(self.root / "secret-location"),
                "z": [1, 2], "keys": ["not-for-projection"], "strata": [7]}}

    def test_empty_catalog_has_exact_fixed_eight_datasets_and_honest_metadata(self):
        result = d.dataset_overview(self.store)
        self.assertEqual([item["id"] for item in result["datasets"]], list(DATASETS))
        self.assertEqual(len(result["datasets"]), 8)
        self.assertEqual(result["unlinked_case_count"], 0)
        self.assertEqual(result["unclassified_training_run_count"], 0)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["authorization_eligible"])
        wine = self.item()
        self.assertEqual((wine["source_rows"], wine["features"], wine["task"]), (178, 13, "classification"))
        self.assertEqual(self.item("sklearn-diabetes")["task"], "regression")
        for dataset in ("research-acs", "research-bts", "research-hmda", "research-tlc"):
            item = self.item(dataset)
            self.assertIsNone(item["source_rows"])
            self.assertIsNone(item["features"])
            self.assertEqual(item["max_rows"], 4096)
            self.assertFalse(item["configured"])
            self.assertEqual(item["configuration_status"], "unconfigured")
            self.assertFalse(item["source_verified_currently"])
            self.assertEqual(item["training_runs"], [])
            self.assertEqual(item["summary"], {"training_runs": 0, "completed": 0, "failed": 0,
                "cancelled": 0, "active": 0, "unknown": 0, "linked_cases": 0, "followup_jobs": 0})

    def test_all_training_history_includes_more_than_queue_latest_hundred(self):
        for index in range(137):
            self.job("sklearn-wine" if index % 2 else "sklearn-breast-cancer", state="failed")
        self.assertEqual(len(self.store.list_jobs()), 100)
        result = d.dataset_overview(self.store)
        self.assertEqual(sum(item["summary"]["training_runs"] for item in result["datasets"]), 137)
        wine = self.item()
        self.assertEqual(wine["summary"]["training_runs"], 68)
        self.assertEqual(wine["summary"]["failed"], 68)
        self.assertEqual([run["created"] for run in wine["training_runs"]],
                         sorted((run["created"] for run in wine["training_runs"]), reverse=True))

    def test_states_retries_and_missing_observations_are_not_invented(self):
        failed = self.job(state="failed", result={"verdict": "clear", "dataset": {"rows": 900}})
        completed = self.job(result={"verdict": "inconclusive", "dataset": {"rows": 128, "features": 13}}, retry_of=failed)
        queued = self.job(state="queued")
        running = self.job(state="running")
        cancelled = self.job(state="cancelled")
        item = self.item()
        self.assertEqual(item["summary"], {"training_runs": 5, "completed": 1, "failed": 1,
            "cancelled": 1, "active": 2, "unknown": 0, "linked_cases": 0, "followup_jobs": 0})
        runs = {run["job_id"]: run for run in item["training_runs"]}
        self.assertEqual(runs[completed]["retry_of"], failed)
        self.assertEqual((runs[completed]["verdict"], runs[completed]["rows"], runs[completed]["features"]),
                         ("inconclusive", 128, 13))
        self.assertIsNone(runs[queued]["started"])
        self.assertIsNone(runs[running]["finished"])
        self.assertIsNotNone(runs[cancelled]["finished"])
        for job_id in (failed, queued, running, cancelled):
            self.assertIsNone(runs[job_id]["verdict"])
            self.assertIsNone(runs[job_id]["rows"])
            self.assertIsNone(runs[job_id]["case_id"])
        self.assertTrue(all(run["authorization_eligible"] is False for run in runs.values()))

    def test_only_completed_exact_result_case_links_count_unique_cases(self):
        linked = self.case("No dataset in this label")
        misleading = self.case("Wine classification logistic results")
        result = {"case_id": linked["id"], "verdict": "block", "dataset": {"rows": 178, "features": 13}}
        self.job(result=result)
        self.job(result=result)
        self.job(state="failed", result={"case_id": misleading["id"]})
        self.job(state="queued", case_id=misleading["id"], result={"case_id": misleading["id"]})
        self.job(result={"case_id": "f" * 32})
        item = self.item()
        self.assertEqual(item["case_ids"], [linked["id"]])
        self.assertEqual(item["summary"]["linked_cases"], 1)
        self.assertEqual(len(item["training_runs"]), 5)
        self.assertEqual(d.dataset_overview(self.store)["unlinked_case_count"], 1)
        self.assertEqual(item["cases"][0]["name"], linked["name"])

    def test_missing_case_directory_or_project_is_not_a_current_link(self):
        existing = self.case()
        self.job(result={"case_id": existing["id"]})
        self.assertEqual(self.item()["case_ids"], [existing["id"]])
        (self.store.case_path(existing["id"]) / "project.json").unlink()
        self.assertEqual(self.item()["case_ids"], [])
        self.assertEqual(d.dataset_overview(self.store)["unlinked_case_count"], 1)

    def test_followup_check_and_assessment_jobs_link_only_by_exact_case_id(self):
        linked = self.case()
        unrelated = self.case("Wine")
        self.job(result={"case_id": linked["id"]})
        check = self.job(kind="check", case_id=linked["id"], result={"case_id": unrelated["id"]})
        assess = self.job(kind="assess", case_id=linked["id"], result={"assessment_verdict": "block"})
        self.job(kind="assess", case_id=unrelated["id"], result={"assessment_verdict": "clear"})
        self.job(kind="reference", result={"case_id": linked["id"]})
        item = self.item()
        followups = item["cases"][0]["followup_jobs"]
        self.assertEqual([job["job_id"] for job in followups], [assess, check])
        self.assertEqual(followups[0]["verdict"], "block")
        self.assertEqual(followups[0]["kind"], "assess")
        self.assertEqual(followups[1]["case_id"], linked["id"])
        self.assertIsNone(followups[1]["verdict"])
        self.assertEqual(item["summary"]["followup_jobs"], 2)
        self.assertEqual(item["summary"]["training_runs"], 1)

    def test_invalid_options_unknown_ids_and_defaultless_legacy_records_are_unclassified(self):
        self.job(raw_options='{"dataset":"sklearn-wine","dataset":"sklearn-digits","preset":"logistic"}')
        self.job(options={"preset": "logistic"}, result={"dataset": {"name": "Wine"}})
        self.job(options={"dataset": "sklearn-wine"})
        self.job(dataset="research-unknown")
        self.job(dataset="research-acs", preset="ridge")
        self.job(raw_options="not json")
        self.job(options={"dataset": "sklearn-wine", "preset": "logistic", "other": True})
        self.job(kind="language", options={"model": "wine"}, result={"dataset": "sklearn-wine"})
        result = d.dataset_overview(self.store)
        self.assertEqual(result["unclassified_training_run_count"], 7)
        self.assertEqual(sum(item["summary"]["training_runs"] for item in result["datasets"]), 0)

    def test_invalid_result_is_still_a_run_but_does_not_invent_case_or_verdict(self):
        self.job(raw_result='{"verdict":"clear","verdict":"block"}')
        self.job(raw_result='{"verdict":NaN}')
        self.job(result={"case_id": "../case", "verdict": "authorized", "dataset": {"rows": True, "features": -1}})
        for run in self.item()["training_runs"]:
            self.assertIsNone(run["verdict"])
            self.assertIsNone(run["case_id"])
            self.assertIsNone(run["rows"])
            self.assertIsNone(run["features"])
        self.assertEqual(self.item()["summary"]["completed"], 3)

    def test_configured_research_is_not_verified_or_loaded_on_http_reads(self):
        ordinary = self.root / "ordinary-research-root"
        ordinary.mkdir()
        os.environ[ENV] = str(ordinary)
        with mock.patch("model_release_assurance.production_registration.profiles.load_profile",
                        side_effect=AssertionError("overview must not load a corpus")) as loader:
            item = self.item("research-acs")
            self.assertTrue(item["configured"])
            self.assertEqual(item["configuration_status"], "configured_directory_only")
            self.assertFalse(item["source_verified_currently"])
            self.assertIsNone(item["source_rows"])
            self.assertEqual(item["training_runs"], [])
        loader.assert_not_called()
        self.assertNotIn(str(ordinary), json.dumps(item))
        os.environ[ENV] = "unavailable-relative-configuration"
        rejected = self.item("research-acs")
        self.assertFalse(rejected["configured"])
        self.assertEqual(rejected["configuration_status"], "invalid_configuration")
        self.assertNotIn(os.environ[ENV], json.dumps(rejected))

    def test_research_metadata_comes_only_from_matching_retained_result_and_is_sanitized(self):
        source = self.source()
        self.job("research-acs", result={"dataset": {"rows": 4096, "features": 8, "research_source": source}})
        self.job("research-bts", result={"dataset": {"rows": 4096, "features": 7, "research_source": source}})
        item = self.item("research-acs")
        self.assertFalse(item["configured"])
        self.assertIsNone(item["source_rows"])
        run = item["training_runs"][0]
        projected = run["research_source"]
        self.assertEqual(projected["source_sha256"], "a" * 64)
        self.assertEqual(projected["metadata"]["source_rows"], 27840)
        self.assertEqual(projected["metadata"]["selected_rows"], 4096)
        self.assertTrue(projected["metadata"]["local_public_fixture_pin_verified"])
        self.assertFalse(projected["verified_currently"])
        self.assertEqual(projected["observation_scope"], "stored_training_result_only")
        self.assertNotIn(str(self.root), json.dumps(projected))
        self.assertFalse({"z", "keys", "strata", "private_path", "source_relative_path"} & set(projected["metadata"]))
        self.assertIsNone(self.item("research-bts")["training_runs"][0]["research_source"])
        projected["metadata"]["source_rows"] = 1
        self.assertEqual(self.item("research-acs")["training_runs"][0]["research_source"]["metadata"]["source_rows"], 27840)

    def test_research_metadata_boolean_aliases_bounds_and_strings_are_not_coerced(self):
        source = self.source()
        source["metadata"].update(source_rows=True, selected_rows=4097, feature_count=-1,
                                  selection_seed="20261001", local_public_fixture_pin_verified=1)
        source["source_sha256"] = "not-a-digest"
        self.job("research-acs", result={"dataset": {"research_source": source}})
        projected = self.item("research-acs")["training_runs"][0]["research_source"]
        self.assertIsNone(projected["source_sha256"])
        for field in ("source_rows", "selected_rows", "feature_count", "selection_seed", "local_public_fixture_pin_verified"):
            self.assertNotIn(field, projected["metadata"])

    def test_current_scientific_clear_label_never_grants_authorization(self):
        self.job(result={"verdict": "clear", "authorized": True, "authorization_eligible": True})
        item = self.item()
        self.assertEqual(item["training_runs"][0]["verdict"], "clear")
        self.assertFalse(item["training_runs"][0]["authorization_eligible"])
        self.assertFalse(item["authorization_eligible"])
        self.assertTrue(any("not current evidence verification" in line for line in item["limitations"]))

    def test_reads_do_not_recover_jobs_modify_database_or_read_case_evidence(self):
        linked = self.case()
        self.job(state="running")
        self.job(result={"case_id": linked["id"], "verdict": "inconclusive"})
        def retained_rows():
            with self.store.connect() as db:
                return list(db.iterdump())
        before = retained_rows()
        with mock.patch.object(self.store, "recover", side_effect=AssertionError("read must not recover")), \
                mock.patch("model_release_assurance.workflow.load_project", side_effect=AssertionError("read must not replay")), \
                mock.patch.object(self.store, "list_jobs", side_effect=AssertionError("read must not truncate history")):
            result = d.dataset_overview(self.store)
            self.assertEqual(sum(item["summary"]["active"] for item in result["datasets"]), 1)
        self.assertEqual(retained_rows(), before)

    def test_fixed_detail_lookup_rejects_unknown_and_path_inputs_before_store_access(self):
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError("store touched")
        for value in ("../research-acs", "research-adult", "acs", "", None, True, {}):
            with self.subTest(value=value), self.assertRaises(KeyError):
                d.dataset_detail(Poison(), value)

    def test_http_collection_detail_and_unknown_ids_use_read_only_projection(self):
        linked = self.case()
        self.job(result={"case_id": linked["id"], "verdict": "block", "dataset": {"rows": 178, "features": 13}})
        with TestClient(create_app(self.store.root)) as client:
            collection = client.get("/api/datasets")
            self.assertEqual(collection.status_code, 200)
            self.assertEqual(len(collection.json()["datasets"]), 8)
            detail = client.get("/api/datasets/sklearn-wine")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json(), self.item())
            self.assertEqual(detail.json()["case_ids"], [linked["id"]])
            self.assertEqual(detail.headers["Cache-Control"], "no-store")
            for value in ("unknown", "research-adult", "%2e%2e%2fprivate", "research-acs%2fchild"):
                with self.subTest(value=value):
                    self.assertEqual(client.get("/api/datasets/" + value).status_code, 404)
            self.assertEqual(client.post("/api/datasets", json={}).status_code, 405)
        self.assertEqual(self.store.case(linked["id"])["id"], linked["id"])


if __name__ == "__main__":
    unittest.main()
