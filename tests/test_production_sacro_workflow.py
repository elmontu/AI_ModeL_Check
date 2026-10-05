"""Frozen comparison workflow tests use explicit synthetic worker outputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_evidence.replay import snapshot_native_bundle
from model_release_assurance.production_registration.profiles import load_profile
from model_release_assurance.production_sacro import protocol,workflow,worker

class SacroWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace=tempfile.TemporaryDirectory(prefix='sacro-workflow-');cls.root=Path(cls.workspace.name);cls.bundles={}
        for name in ('sklearn-wine','sklearn-diabetes'):
            data=load_profile(name,max_rows=128);dest=cls.root/name
            result=native.run_native(data['x'],data['y'],dataset_id=data['dataset_id'],source_sha256=data['source_sha256'],feature_names=data['feature_names'],task=data['task'],output=dest)
            assert result['status']=='completed';cls.bundles[name]=snapshot_native_bundle(dest)
    @classmethod
    def tearDownClass(cls):cls.workspace.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='sacro-run-');self.addCleanup(self.temp.cleanup);self.output=Path(self.temp.name)/'run';self.change=None
    def external(self,python,input_path,output):
        raw=input_path.read_bytes();request=json.loads(raw);prepared=request['prepared'];cases={}
        self.assertTrue((input_path.parent/'plan.json').exists())
        for name in ('target','positive','null'):
            rows=[]
            for split in protocol.frozen_splits(prepared):
                labels=split['membership_labels'];probs=[.5]*len(labels) if name=='null' else [.95 if x else .05 for x in labels]
                rows.append({**split,'member_probabilities':probs,'upstream_auc':round(protocol.membership_metrics(labels,probs)['raw_auc'],8)})
            cases[name]=rows
        result={'schema':'mra-sacro-worker-output/v1','status':'completed','prepared_sha256':workflow.digest(prepared),
                'runtime':workflow.expected_binding(),'versions':request['versions'],'source_sha256':request['source_sha256'],
                'lock_sha256':request['lock_sha256'],'cases':cases,'fixture_only':True,'can_clear':False,
                'assessment_eligible':False,'authorization_eligible':False,'production_authorized':False}
        process={'status':'completed','cleanup_confirmed':True}
        output.mkdir();workflow.write(output/'worker.json',result)
        if self.change:self.change(request,result,process,input_path)
        return {**process,'result':result}
    def run_case(self,profile='sklearn-wine',blobs=None):
        with patch.object(workflow,'run_worker',side_effect=self.external):
            return workflow.run_comparison(blobs or self.bundles[profile],profile_id=profile,output=self.output,python='unused',versions={'a':'1','b':'1','c':'1','d':'1'},lock_sha256='a'*64)
    def test_freezes_before_execution_and_retains_independent_comparison(self):
        r=self.run_case();self.assertEqual(r['status'],'completed',r);self.assertEqual(r['comparison']['null']['summary']['attack_raw_auc_mean'],.5)
        for k in ('can_clear','assessment_eligible','authorization_eligible','production_authorized','external_execution_attested'):self.assertIs(r[k],False)
    def test_regression_is_unsupported_without_external_execution(self):
        with patch.object(workflow,'run_worker',side_effect=AssertionError):r=self.run_case('sklearn-diabetes')
        self.assertEqual(r['status'],'unsupported');self.assertEqual(r['error']['code'],'regression_not_supported')
    def test_wrong_profile_cannot_hide_as_unsupported(self):self.assertEqual(self.run_case(blobs=self.bundles['sklearn-diabetes'])['status'],'failed')
    def test_changed_frozen_plan_is_refused(self):
        self.change=lambda req,result,process,path:(path.parent/'plan.json').write_bytes(b'{}')
        self.assertEqual(self.run_case()['status'],'failed')
    def test_changed_input_is_refused(self):
        self.change=lambda req,result,process,path:path.write_bytes(b'{}')
        self.assertEqual(self.run_case()['status'],'failed')
    def test_changed_raw_worker_is_refused(self):
        self.change=lambda req,result,process,path:(path.parent/'worker/worker.json').write_bytes(b'{}')
        self.assertEqual(self.run_case()['status'],'failed')
    def test_missing_control_refused(self):
        self.change=lambda req,result,process,path:result['cases'].pop('positive')
        self.assertEqual(self.run_case()['status'],'failed')
    def test_weakened_positive_refused(self):
        def change(req,result,process,path):
            result['cases']['positive']=copy.deepcopy(result['cases']['null'])
        self.change=change;self.assertEqual(self.run_case()['status'],'failed')
    def test_relabelled_upstream_metrics_refused(self):
        self.change=lambda req,result,process,path:result['cases']['target'][0].update(upstream_auc=.2)
        self.assertEqual(self.run_case()['status'],'failed')
    def test_worker_runtime_claim_changed_refused(self):
        self.change=lambda req,result,process,path:result['runtime'].update(sacroml_version='9')
        self.assertEqual(self.run_case()['status'],'failed')
    def test_timeout_is_retained(self):
        self.change=lambda req,result,process,path:process.update(status='timed_out')
        self.assertEqual(self.run_case()['status'],'timed_out')
    def test_unconfirmed_cleanup_never_success(self):
        self.change=lambda req,result,process,path:process.update(cleanup_confirmed=False)
        self.assertNotEqual(self.run_case()['status'],'completed')
    def test_missing_dependency_never_falls_back(self):
        with patch.object(workflow,'run_worker',side_effect=ModuleNotFoundError):
            r=workflow.run_comparison(self.bundles['sklearn-wine'],profile_id='sklearn-wine',output=self.output,python='unused',versions={'a':'1','b':'1','c':'1','d':'1'},lock_sha256='a'*64)
        self.assertEqual(r['status'],'failed');self.assertIsNone(r['comparison'])
    def test_overwrite_refused(self):
        self.run_case();before=(self.output/'result.json').read_bytes()
        with self.assertRaises((ValueError,FileExistsError)):self.run_case()
        self.assertEqual(before,(self.output/'result.json').read_bytes())
    def test_worker_rejects_unbounded_or_unknown_request_fields(self):
        self.run_case();req=json.loads((self.output/'input.json').read_bytes())
        for changed in ({**req,'pickle':'x'},{**req,'versions':{}},{**req,'lock_sha256':True}):
            with self.assertRaises(ValueError):worker.validate_request(changed)

if __name__=='__main__':unittest.main()
