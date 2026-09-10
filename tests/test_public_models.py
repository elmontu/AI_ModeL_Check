import tempfile
import unittest
import json
import joblib
from pathlib import Path
import numpy as np
from model_release_assurance.public_models import run_public, capability_inventory
from model_release_assurance.console.store import Store
from model_release_assurance.console.worker import work_once
from model_release_assurance import workflow

class PublicModelTests(unittest.TestCase):
    def test_all_local_classifier_and_regressor_adapters_train_export_and_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            for preset,dataset in [('logistic','sklearn-wine'),('random-forest','sklearn-breast-cancer'),('mlp','sklearn-digits'),('svm','sklearn-wine'),('ensemble','sklearn-breast-cancer'),('cnn','sklearn-digits'),('ridge','sklearn-diabetes'),('forest-regression','sklearn-diabetes'),('mlp-finetuned','sklearn-breast-cancer')]:
                with self.subTest(preset=preset):
                    output=Path(temporary)/preset
                    result=run_public(preset,dataset,output)
                    self.assertTrue(result['training_executed'])
                    self.assertIn(result['verdict'],{'inconclusive','block'})
                    self.assertTrue((output/'assessment-request.json').is_file())
                    self.assertFalse(result['authorized'])
                    self.assertEqual(len(result['red_team']['tools']),3 if preset in {'ridge','forest-regression'} else 11)
                    self.assertFalse(any(t['status']=='failed' for t in result['red_team']['tools']),result['red_team'])
                    self.assertEqual(result['red_team']['release_artifact_sha256'],workflow.digest(output/'model.joblib'))
                    with np.load(output/'public-dataset.npz') as data:
                        self.assertFalse(set(data['train']) & set(data['test']))
                        self.assertFalse(set(data['calibration']) & set(data['audit']))
                        bundle=joblib.load(output/'model.joblib')
                        expected_training=data['base_train'] if preset=='mlp-finetuned' else data['train']
                        np.testing.assert_allclose(bundle['scaler'].mean_,data['x'][expected_training].mean(axis=0))
                        baseline=result['training']['utility']['baseline']
                        self.assertEqual(baseline['fit_records'],len(data['train']))
                        self.assertEqual(baseline['evaluation_records'],len(data['test']))
                        if preset in {'ridge','forest-regression'}:
                            expected_mean=float(data['y'][data['train']].mean())
                            self.assertEqual(baseline['prediction'],expected_mean)
                            self.assertAlmostEqual(baseline['mean_squared_error'],float(np.mean((data['y'][data['test']]-expected_mean)**2)))
                        else:
                            labels,counts=np.unique(data['y'][data['train']],return_counts=True)
                            majority=labels[counts.argmax()]
                            self.assertEqual(baseline['prediction'],majority)
                            self.assertEqual(baseline['accuracy'],float(np.mean(data['y'][data['test']]==majority)))
                            recalls=[float(np.mean(np.full(np.sum(data['y'][data['test']]==label),majority)==label)) for label in np.unique(data['y'][data['test']])]
                            self.assertAlmostEqual(baseline['balanced_accuracy'],float(np.mean(recalls)))
                        for parent in result['component_comparisons']:
                            component=joblib.load(output/parent['path'])
                            self.assertEqual(len(component['model'].predict(component['scaler'].transform(data['x'][data['test']]))),len(data['test']))
                    recipe=json.loads((output/'training-config.json').read_text())
                    self.assertIsInstance(recipe['parameters']['parameters'],dict)
                    self.assertTrue((output/'training-verification.json').is_file())
                    self.assertTrue(json.loads((output/'export-verification.json').read_text())['preprocessing_identical'])
                    if preset=='ensemble':self.assertEqual(len(result['component_comparisons']),2)

    def test_worker_creates_honest_incomplete_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary))
            job=store.enqueue('training',options={'name':'Forest wine','preset':'random-forest','dataset':'sklearn-wine'})
            work_once(store,'test')
            done=store.job(job['id'])
            self.assertEqual(done['state'],'completed',done['error'])
            case=store.case_path(done['result']['case_id'])
            check=workflow.inspect_project(case)[0]
            self.assertEqual(check['issues'],[])
            run=workflow.assess(case)
            self.assertTrue((run/'assessment-report.json').is_file())
            self.assertEqual(workflow.load_project(case).kind,'trained')

    def test_inventory_does_not_claim_llm_console_training(self):
        self.assertEqual(len(capability_inventory()['presets']),10)
        self.assertIn('not a console trainer',capability_inventory()['other_framework_paths'][1]['status'])

    def test_weak_wine_mlp_is_reported_against_train_only_baseline_without_retuning(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'mlp-wine'
            result=run_public('mlp','sklearn-wine',output)
            utility=result['training']['utility']
            self.assertLessEqual(utility['accuracy'],utility['baseline']['accuracy'])
            self.assertFalse(utility['beats_baseline'])
            self.assertTrue(any('held-out accuracy' in warning and 'no better' in warning for warning in result['warnings']))
            self.assertTrue(set(result['training']['warnings']).issubset(result['warnings']))
            recipe=json.loads((output/'training-config.json').read_text())
            self.assertEqual(recipe['parameters']['parameters']['max_iter'],120)
            self.assertTrue(recipe['parameters']['parameters']['early_stopping'])

    def test_registered_raw_scores_and_frozen_inputs_are_rechecked_without_loading_model(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);output=root/'artifacts'
            run_public('logistic','sklearn-wine',output)
            case=root/'case';workflow.initialize(case,'trained','named-party-weights','education')
            for slot,name in [('candidate','model.joblib'),('request','assessment-request.json'),('evaluation-plan','family-plan.json'),('utility-report','utility-report.json')]:
                workflow.bind(case,slot,output/name)
            workflow.create_lineage(case,[],output/'training-config.json',output/'data-manifest.json',output/'data-manifest.json','single-source',[])
            self.assertIn('training-verification',workflow.load_project(case).supporting_files)
            with patch('joblib.load',side_effect=AssertionError('preflight must not execute model bytes')):
                self.assertEqual(workflow.inspect_project(case)[0]['issues'],[])
                for name in ['registered-attack-scores.npz','public-dataset.npz','training-config.json','source-snapshots/public_models.py']:
                    with self.subTest(tamper=name):
                        path=output/name;before=path.read_bytes()
                        path.write_bytes(before+b' tampered')
                        try:self.assertTrue(workflow.inspect_project(case)[0]['issues'])
                        finally:path.write_bytes(before)
            # Rebinding a changed raw-score digest cannot invent different attack counts.
            path=output/'registered-attack-scores.npz'
            with np.load(path) as scores: arrays={k:scores[k].copy() for k in scores.files}
            source=json.loads((output/'attack-source.json').read_text())
            verification=json.loads((output/'training-verification.json').read_text())
            arrays['member'][:]=verification['threshold']+(1 if source['successes']!=len(arrays['member']) else -1)
            np.savez_compressed(path,**arrays)
            verification['files'][path.name]=workflow.digest(path)
            workflow.write_json(output/'training-verification.json',verification,replace=True)
            workflow.bind(case,'request',output/'assessment-request.json')
            self.assertIn('counts do not replay',str(workflow.inspect_project(case)[0]['issues']))
            with self.assertRaisesRegex(ValueError,'preflight failed'):workflow.assess(case)

    def test_cnn_rejects_nonfinite_and_invalid_shape_inputs(self):
        from model_release_assurance.tiny_cnn import TinyCNN
        x=np.zeros((4,64));y=np.array([0,1,0,1])
        for invalid in [np.zeros((4,63)),np.full((4,64),np.nan),np.zeros(64)]:
            with self.subTest(shape=invalid.shape):
                with self.assertRaises(ValueError):TinyCNN(epochs=1).fit(invalid,y)
        model=TinyCNN(epochs=1).fit(x,y)
        with self.assertRaises(ValueError):model.predict(np.full((2,64),np.inf))
        np.testing.assert_allclose(model.predict_proba(x).sum(axis=1),1)
