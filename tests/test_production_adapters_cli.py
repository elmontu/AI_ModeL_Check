"""Orchestration checks preserve explicit gaps and failed-data outcomes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC=importlib.util.spec_from_file_location("mra_adapter_cli",Path(__file__).resolve().parents[1]/"scripts/benchmark_research_adapters.py")
CLI=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
REPLAY_SPEC=importlib.util.spec_from_file_location("mra_adapter_replay_cli",Path(__file__).resolve().parents[1]/"scripts/replay_native_adapter.py")
REPLAY=importlib.util.module_from_spec(REPLAY_SPEC)
REPLAY_SPEC.loader.exec_module(REPLAY)

BUNDLED={"id":"sklearn-wine","label":"Wine","kind":"bundled","task":"classification","loader_id":"sklearn-wine"}
MISSING={"id":"wildchat-4.8m","label":"WildChat","kind":"historical_unavailable","task":"unsupported","loader_id":None}
RESEARCH={"id":"acs","label":"ACS","kind":"research_prepared","task":"classification","corpus":"acs"}
SNAPSHOT={"scope":"unit-test observation","files":[],"sha256":"a"*64}


def fake_native(x,y,**kwargs):
    path=Path(kwargs["output"]); path.mkdir()
    report={"status":"completed","authorization_eligible":False,"replay":{"status":"passed"}}
    (path/"result.json").write_text(json.dumps(report))
    return report


class ProductionAdapterCliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="mra-benchmark-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        subprocess.run(["git","init","-q",str(self.root)],capture_output=True,check=True)
        (self.root/".gitignore").write_text(".local/\n")

    def run_profile(self,entries,*,name="run",native=fake_native):
        with mock.patch.object(CLI,"source_snapshot",return_value=SNAPSHOT), mock.patch.object(CLI,"catalog_entries",return_value=entries):
            if native is None:
                return CLI.run_benchmark(root=self.root,data_root=self.root/"absent",output=".local/"+name,max_rows=128)
            with mock.patch.object(CLI,"run_native",side_effect=native):
                return CLI.run_benchmark(root=self.root,data_root=self.root/"absent",output=".local/"+name,max_rows=128)

    def test_real_bundled_native_workflow_and_missing_corpus_are_separate(self):
        report=self.run_profile([BUNDLED,MISSING],native=None)
        self.assertEqual(report["status"],"completed_with_gaps",report)
        self.assertEqual(report["counts"],{"passed":1,"unavailable":1})
        self.assertFalse(report["coverage_complete"])
        self.assertFalse(report["all_research_datasets_tested"])
        self.assertTrue(report["entries"][0]["model_tested"])
        self.assertFalse(report["entries"][1]["model_tested"])
        self.assertEqual(report,json.loads((self.root/".local/run/result.json").read_text()))
        saved=self.root/".local/run/cases/sklearn-wine"
        self.assertTrue((self.root/".local/run/observations/sklearn-wine.json").is_file())
        self.assertEqual(REPLAY.replay_run(saved)["status"],"passed")
        for key,value in CLI.FLAGS.items(): self.assertIs(report[key],value)

    def test_missing_supported_research_data_does_not_count_as_tested(self):
        report=self.run_profile([RESEARCH])
        self.assertEqual(report["counts"],{"unavailable":1})
        self.assertEqual(report["status"],"completed_with_gaps")
        self.assertFalse(report["entries"][0]["model_tested"])

    def test_bad_source_does_not_become_missing_and_next_profile_still_runs(self):
        with mock.patch.object(CLI,"load_research_dataset",side_effect=ValueError("tampered source")):
            report=self.run_profile([RESEARCH,BUNDLED])
        self.assertEqual(report["status"],"failed")
        self.assertEqual(report["counts"],{"failed":1,"passed":1})
        self.assertEqual(report["entries"][0]["reason"],"ValueError")

    def test_adapter_unsupported_is_explicit_and_never_model_tested(self):
        def unsupported(x,y,**kwargs):
            Path(kwargs["output"]).mkdir()
            return {"status":"unsupported","authorization_eligible":False}
        report=self.run_profile([BUNDLED],native=unsupported)
        self.assertEqual(report["status"],"completed_with_gaps")
        self.assertEqual(report["counts"],{"unsupported":1})
        self.assertFalse(report["entries"][0]["model_tested"])

    def test_adapter_exception_retains_failure_evidence_and_never_clean_counts(self):
        def failed(*args,**kwargs): raise RuntimeError("fixture failure")
        report=self.run_profile([BUNDLED],native=failed)
        self.assertEqual(report["status"],"failed")
        self.assertEqual(report["counts"],{"failed":1})
        self.assertTrue((self.root/".local/run/plan.json").exists())
        self.assertTrue((self.root/".local/run/result.json").exists())

    def test_plan_exists_before_training_and_unknown_adapter_outcome_fails(self):
        def unknown(*args,**kwargs):
            plan=json.loads((self.root/".local/run/plan.json").read_text())
            self.assertEqual(plan["catalog"],[BUNDLED])
            self.assertEqual(plan["max_rows"],128)
            Path(kwargs["output"]).mkdir()
            return {"status":"approved"}
        report=self.run_profile([BUNDLED],native=unknown)
        self.assertEqual(report["status"],"failed")
        self.assertFalse(report["entries"][0]["model_tested"])

    def test_duplicate_catalog_refused_before_any_model_runs(self):
        with mock.patch.object(CLI,"run_native") as run:
            report=self.run_profile([BUNDLED,BUNDLED],native=None)
            run.assert_not_called()
        self.assertEqual(report["status"],"failed")
        self.assertEqual(report["entries"],[])

    def test_overwrite_outside_output_and_relative_data_root_refused(self):
        self.run_profile([MISSING])
        before=(self.root/".local/run/result.json").read_bytes()
        with self.assertRaises((ValueError,OSError,CLI._BASELINE.BaselineError)):
            self.run_profile([MISSING])
        self.assertEqual((self.root/".local/run/result.json").read_bytes(),before)
        for output,data_root in ((self.root/"outside",self.root),(".local/relative",Path("relative"))):
            with self.assertRaises((ValueError,OSError,CLI._BASELINE.BaselineError)):
                CLI.run_benchmark(root=self.root,data_root=data_root,output=output)
        self.assertFalse((self.root/"outside").exists())
        self.assertFalse((self.root/".local/relative").exists())

    def test_limits_refuse_bool_and_excessive_inputs_before_output(self):
        for rows,seed in ((True,1),(127,1),(4097,1),(128,True),(128,-1),(128,2**32)):
            with self.subTest(rows=rows,seed=seed),self.assertRaises(ValueError):
                CLI.run_benchmark(root=self.root,data_root=self.root,output=".local/invalid",max_rows=rows,seed=seed)
        self.assertFalse((self.root/".local/invalid").exists())

    def test_source_drift_after_success_invalidates_entire_receipt(self):
        with mock.patch.object(CLI,"catalog_entries",return_value=[BUNDLED]),mock.patch.object(CLI,"run_native",side_effect=fake_native),mock.patch.object(CLI,"source_snapshot",side_effect=[SNAPSHOT,{**SNAPSHOT,"sha256":"b"*64}]):
            report=CLI.run_benchmark(root=self.root,data_root=self.root,output=".local/run",max_rows=128)
        self.assertEqual(report["status"],"failed")
        self.assertIn("source_changed",report["errors"])
        self.assertFalse(report["source_stable"])

    def test_bundled_sampling_is_repeatable_and_does_not_download(self):
        import numpy as np
        first=CLI.load_bundled("sklearn-diabetes",128)
        second=CLI.load_bundled("sklearn-diabetes",128)
        np.testing.assert_array_equal(first["x"],second["x"])
        np.testing.assert_array_equal(first["y"],second["y"])
        self.assertEqual(first["source_sha256"],second["source_sha256"])
        self.assertEqual(first["metadata"]["available_rows"],442)
        self.assertFalse(first["metadata"]["historically_untouched_data_claim"])
        with self.assertRaises(ValueError): CLI.load_bundled("fetch_remote",128)

    def test_require_complete_and_replay_failures_have_nonzero_exit(self):
        import contextlib,io
        report={"status":"completed_with_gaps","counts":{"unavailable":1},"coverage_complete":False,"errors":[]}
        with mock.patch.object(CLI,"run_benchmark",return_value=report),contextlib.redirect_stdout(io.StringIO()):
            args=["--data-root",str(self.root),"--output",".local/run"]
            self.assertEqual(CLI.main(args),0)
            self.assertEqual(CLI.main([*args,"--require-complete"]),3)
        with mock.patch.object(REPLAY,"replay_run",return_value={"status":"failed"}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(REPLAY.main(["--run",str(self.root)]),1)


if __name__=="__main__": unittest.main()
