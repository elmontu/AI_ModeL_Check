"""Fixed-roster CLI dispositions; these unit tests mock external work explicitly."""
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('sacro_cli',Path(__file__).resolve().parents[1]/'scripts/rehearse_sacro_adapter.py')
CLI=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(CLI)
from model_release_assurance.production_sacro import evidence
class SacroCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='sacro-cli-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        subprocess.run(['git','init','-q',str(self.root)],check=True,capture_output=True);(self.root/'.gitignore').write_text('.local/\n')
        self.python=self.root/'.local/env/Scripts/python.exe';self.change=None
    def fake(self,blobs,*,profile_id,**kwargs):
        result={'status':'unsupported' if profile_id=='sklearn-diabetes' else 'completed','error':{'code':'regression_not_supported'} if profile_id=='sklearn-diabetes' else None,
                'comparison':{'target':{'summary':{}},'positive':{'controls_satisfied':True},'null':{'controls_satisfied':True}}}
        if self.change:self.change(profile_id,result)
        return result
    def run_fixture(self):
        with patch.object(CLI,'load_runtime_manifest',return_value=({},'a'*64)),patch.object(CLI,'source_bindings',return_value={}),patch.object(CLI,'runtime_descriptor',return_value={}),patch.object(CLI,'verified_input',return_value={}),patch.object(CLI,'artifact_manifest',return_value={}),patch.object(CLI,'snapshot_native_bundle',return_value={}),patch.object(CLI,'run_comparison',side_effect=self.fake),patch.object(evidence,'authenticate_comparison',return_value={'status':'accepted_bound_native_replay'}):
            return CLI.run_rehearsal(root=self.root,output='.local/run',python=self.python)
    def test_all_eight_dispositions_are_required_and_regression_not_passed(self):
        r=self.run_fixture();self.assertEqual(r['status'],'completed_with_unsupported');self.assertEqual([x['profile_id'] for x in r['cases']],list(CLI.PROFILE_IDS));self.assertEqual(sum(x['status']=='completed' for x in r['cases']),7);self.assertFalse(r['all_research_datasets_tested']);self.assertFalse(r['production_authorized'])
    def test_required_failure_is_not_silently_removed(self):
        self.change=lambda n,r:r.update(status='failed',error={'type':'Example'}) if n=='acs' else None
        r=self.run_fixture();self.assertEqual(r['status'],'failed');self.assertEqual(len(r['cases']),8);self.assertFalse(r['coverage_complete'])
    def test_false_control_prevents_batch_success(self):
        self.change=lambda n,r:r['comparison']['positive'].update(controls_satisfied=False) if n=='acs' else None
        self.assertEqual(self.run_fixture()['status'],'failed')
    def test_regression_cannot_be_relabelled_completed(self):
        self.change=lambda n,r:r.update(status='completed',error=None) if n=='sklearn-diabetes' else None
        self.assertEqual(self.run_fixture()['status'],'failed')
    def test_benchmark_and_python_must_stay_in_government_local(self):
        for kwargs in ({'python':self.root/'outside/python.exe'},{'python':self.python,'benchmark':self.root/'elsewhere'}):
            with self.assertRaises(ValueError):CLI.run_rehearsal(root=self.root,output='.local/run',**kwargs)
        self.assertFalse((self.root/'.local/run').exists())
    def test_overwrite_is_refused(self):
        self.run_fixture()
        with self.assertRaises(CLI._BASELINE.BaselineError):self.run_fixture()
    def test_no_model_threshold_or_custom_attack_cli(self):
        for option in ('--model','--pickle','--threshold','--attack-model','--private-data'):
            with patch('sys.stderr',new_callable=io.StringIO),self.assertRaises(SystemExit):CLI.main(['--output','.local/run','--python',str(self.python),option,'value'])
if __name__=='__main__':unittest.main()
