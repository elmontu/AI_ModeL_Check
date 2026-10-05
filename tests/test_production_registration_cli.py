"""The public registration command is bounded, explicit and non-authorizing."""
from __future__ import annotations
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("registration_rehearsal",Path(__file__).resolve().parents[1]/"scripts/rehearse_model_registration.py")
CLI=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(CLI)


class RegistrationCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="registration-cli-");self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);subprocess.run(["git","init","-q",str(self.root)],capture_output=True,check=True)
        (self.root/".gitignore").write_text(".local/\n",encoding="utf-8")
        self.source={"public-source":"a"*64}

    def run_fixture(self,**kwargs):
        with patch.object(CLI,"source_snapshot",return_value=self.source):
            return CLI.run_rehearsal(root=self.root,output=".local/run",max_rows=128,**kwargs)

    def test_real_public_profile_retains_registration_and_known_observations(self):
        result=self.run_fixture();self.assertEqual(result["status"],"passed",result)
        self.assertEqual(len(result["cases"]),1)
        self.assertEqual(result["cases"][0]["status"],"review_recorded")
        self.assertEqual(result["initial_history"]["known_disclosures"],0)
        self.assertEqual(result["final_history"]["known_disclosures"],2)
        self.assertEqual(result["final_history"]["local_registrations"],1)
        self.assertEqual(result["final_history"]["external_history"],"unknown")
        self.assertTrue(result["restart_history_matches"])
        self.assertIs(result["all_research_datasets_tested"],False)
        for key,value in CLI.FLAGS.items():self.assertIs(result[key],value)
        self.assertEqual(result,json.loads((self.root/".local/run/result.json").read_bytes()))

    def test_output_cannot_overwrite_or_escape_government_local(self):
        self.run_fixture();saved=(self.root/".local/run/result.json").read_bytes()
        with self.assertRaises(CLI._BASELINE.BaselineError):self.run_fixture()
        self.assertEqual(saved,(self.root/".local/run/result.json").read_bytes())
        for output in ("outside",".local/../outside"):
            with self.subTest(output=output),self.assertRaises(CLI._BASELINE.BaselineError):CLI.run_rehearsal(root=self.root,output=output)

    def test_workflow_failure_is_retained_and_does_not_become_batch_success(self):
        with patch.object(CLI.LocalRegistrationWorkflow,"run",side_effect=RuntimeError("secret-message-not-printed")):
            result=self.run_fixture()
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["cases"][0]["error"],{"type":"RuntimeError","stage":"profile_workflow"})
        self.assertNotIn("secret-message",json.dumps(result))

    def test_source_drift_rejects_otherwise_completed_batch(self):
        with patch.object(CLI,"source_snapshot",side_effect=[self.source,{"public-source":"b"*64}]):
            result=CLI.run_rehearsal(root=self.root,output=".local/run",max_rows=128)
        self.assertEqual(result["status"],"failed");self.assertFalse(result["source_unchanged"])

    def test_changed_candidate_after_review_cannot_be_recorded_as_observed_disclosure(self):
        original = CLI.LocalRegistrationWorkflow.run
        def tamper(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            self.assertEqual(result["status"], "review_recorded")
            (Path(kwargs["output"]) / "native/candidate.json").write_bytes(b"changed")
            return result
        with patch.object(CLI.LocalRegistrationWorkflow, "run", tamper):
            result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["cases"][0]["error"]["type"], "ValueError")
        self.assertEqual(result["final_history"]["local_registrations"], 1)
        self.assertEqual(result["final_history"]["known_disclosures"], 0)

    def test_cli_does_not_accept_import_or_privacy_budget_arguments(self):
        for option in ("--model","--artifact","--parents","--epsilon","--privacy-budget"):
            with self.subTest(option=option),patch("sys.stderr",new_callable=io.StringIO),self.assertRaises(SystemExit) as caught:
                CLI.main(["--output",".local/run",option,"file.joblib"])
            self.assertEqual(caught.exception.code,2)
        self.assertFalse((self.root/".local/run").exists())

    def test_invalid_limits_refused_before_output(self):
        for limit in (True,0,127,4097):
            with self.subTest(limit=limit),self.assertRaises(ValueError):CLI.run_rehearsal(root=self.root,output=".local/run",max_rows=limit)
        self.assertFalse((self.root/".local/run").exists())

    def test_cli_failure_and_refused_exit_codes(self):
        with patch.object(CLI,"ROOT",self.root),patch.object(CLI,"source_snapshot",side_effect=ValueError),patch("sys.stdout",new_callable=io.StringIO):
            self.assertEqual(CLI.main(["--output",".local/run"]),1)
            self.assertEqual(CLI.main(["--output",".local/run"]),2)


if __name__=="__main__":unittest.main()
