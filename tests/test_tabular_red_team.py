import unittest
from unittest.mock import patch
import numpy as np
from model_release_assurance.tabular_red_team import threshold_probe, run_tabular_suite
from model_release_assurance.red_team import RedTeamConfig, RedTeamTarget

class TabularRedTeamTests(unittest.TestCase):
    def test_known_leak_and_constant_baseline(self):
        leak=threshold_probe(np.ones(80),np.zeros(80),42)
        null=threshold_probe(np.zeros(80),np.zeros(80),42)
        self.assertEqual((leak['auc'],leak['tpr'],leak['fpr']),(1,1,0))
        self.assertEqual((null['auc'],null['tpr'],null['fpr']),(.5,0,0))
        self.assertEqual(leak,threshold_probe(np.ones(80),np.zeros(80),42))
    def test_invalid_numeric_view_rejected(self):
        target=RedTeamTarget('bad','xgboost',None,np.full((40,2),np.nan),np.zeros(40),np.zeros((40,2)),np.zeros(40))
        with self.assertRaises(ValueError):run_tabular_suite(target,RedTeamConfig(seed=1))
    def test_invalid_score_shapes_and_values_are_rejected(self):
        for values in (np.ones((80,1)), np.r_[np.nan,np.ones(79)], np.r_[np.inf,np.ones(79)], np.ones(19)):
            with self.subTest(shape=values.shape):
                with self.assertRaises(ValueError):threshold_probe(values,np.zeros(80),42)

    def test_mismatched_rows_and_features_rejected(self):
        for train, labels, test in ((np.zeros((40,2)),np.zeros(41),np.zeros((40,2))),
                                    (np.zeros((40,2)),np.zeros((40,1)),np.zeros((40,2))),
                                    (np.zeros((40,2)),np.zeros(40),np.zeros((40,3)))):
            with self.assertRaises(ValueError):
                run_tabular_suite(RedTeamTarget('invalid','linear',None,train,labels,test,np.zeros(40)),RedTeamConfig(seed=1))

    def test_nonzero_class_labels_map_to_probability_columns(self):
        from sklearn.linear_model import LogisticRegression
        from model_release_assurance.tabular_red_team import membership_scores, attribute_inference
        rng=np.random.default_rng(13); x=rng.normal(size=(200,3)); y=np.where(x[:,0]>0,9,4)
        model=LogisticRegression().fit(x[:100],y[:100])
        target=RedTeamTarget('classes','logistic',model,x[:100],y[:100],x[100:],y[100:])
        result=membership_scores(target,RedTeamConfig(seed=1))
        self.assertTrue(all(result['controls'].values()))
        self.assertEqual(attribute_inference(target,RedTeamConfig(seed=1))['evaluation_records'],50)
        suite=run_tabular_suite(target,RedTeamConfig(seed=1))
        self.assertFalse(any(item['status']=='failed' for item in suite['tools']),suite)

    def test_invalid_probabilities_fail_without_becoming_completed(self):
        from model_release_assurance.tabular_red_team import membership_scores
        class BadModel:
            classes_=np.array([0,1])
            def predict_proba(self,x):return np.tile([.9,.9],(len(x),1))
        target=RedTeamTarget('bad-probability','unknown',BadModel(),np.zeros((40,2)),np.zeros(40),np.zeros((40,2)),np.zeros(40))
        with self.assertRaises(ValueError):membership_scores(target,RedTeamConfig(seed=1))

    def test_deliberately_leaking_model_is_detected_end_to_end(self):
        from model_release_assurance.tabular_red_team import membership_scores
        class LeakingModel:
            classes_=np.array([0,1])
            def predict_proba(self,x):
                confidence=np.where(x[:,0]<0,.99,.51)
                return np.column_stack((confidence,1-confidence))
        target=RedTeamTarget('leak','unknown',LeakingModel(),-np.ones((80,2)),np.zeros(80),np.ones((80,2)),np.zeros(80))
        result=membership_scores(target,RedTeamConfig(seed=1))
        self.assertTrue(all(probe['auc']==1 and probe['tpr']==1 and probe['fpr']==0 for probe in result['probes'].values()))

    def test_actual_predict_defines_initially_correct_and_budget_is_counted(self):
        from model_release_assurance.tabular_red_team import adversarial_search
        class DisagreeingModel:
            classes_=np.array([4,9])
            queries=0
            def predict_proba(self,x):
                self.queries+=len(x)
                return np.tile([.8,.2],(len(x),1))
            def predict(self,x):
                self.queries+=len(x)
                return np.full(len(x),9)
        model=DisagreeingModel()
        target=RedTeamTarget('different-decisions','unknown',model,np.zeros((40,2)),np.full(40,9),np.zeros((40,2)),np.full(40,9))
        result=adversarial_search(target,RedTeamConfig(seed=1))
        self.assertEqual([budget['initially_correct'] for budget in result['budgets']],[40,40])
        total=result['shared_initial_queries']+sum(b['attack_queries_excluding_shared_initial']+b['random_baseline_queries'] for b in result['budgets'])
        self.assertEqual(model.queries,total)
    def test_failures_are_incomplete_not_passed(self):
        target=RedTeamTarget('bad-model','xgboost',None,np.zeros((40,2)),np.zeros(40),np.zeros((40,2)),np.zeros(40))
        report=run_tabular_suite(target,RedTeamConfig(seed=1))
        self.assertEqual(report['status'],'incomplete')
        self.assertTrue(all(t['status'] in {'failed','unsupported'} for t in report['tools']))
        self.assertFalse(report['can_clear'])
        self.assertFalse(report['assessment_eligible'])
        self.assertTrue(report['coverage_gaps'])

    def test_adaptive_attack_preserves_inputs_and_increases_loss(self):
        from sklearn.linear_model import LogisticRegression
        from model_release_assurance.tabular_red_team import adversarial_search
        rng=np.random.default_rng(7)
        x=rng.normal(size=(100,4)); y=(x[:,0]>0).astype(int)
        model=LogisticRegression().fit(x,y)
        target=RedTeamTarget('linear','linear',model,x,y,x.copy(),y.copy())
        before=target.test_x.copy()
        report=adversarial_search(target,RedTeamConfig(seed=9))
        clean=-np.log(model.predict_proba(x)[np.arange(len(y)),y]).mean()
        self.assertTrue(all(b['mean_optimized_loss']>=clean-1e-8 for b in report['budgets']))
        np.testing.assert_array_equal(target.test_x,before)
        self.assertEqual(report,adversarial_search(target,RedTeamConfig(seed=9)))

    def test_poisoned_copies_leave_candidate_and_arrays_unchanged(self):
        from xgboost import XGBClassifier
        from model_release_assurance.tabular_red_team import label_poisoning, trigger_backdoor
        rng=np.random.default_rng(11); x=rng.normal(size=(160,4)); y=(x[:,0]+x[:,1]>0).astype(int)
        model=XGBClassifier(n_estimators=8,max_depth=2,n_jobs=1,random_state=1).fit(x[:100],y[:100])
        target=RedTeamTarget('small','xgboost',model,x[:100],y[:100],x[100:],y[100:])
        raw=bytes(model.get_booster().save_raw()); before=x.copy(); labels=y.copy()
        for tool in (label_poisoning,trigger_backdoor):
            result=tool(target,RedTeamConfig(seed=1))
            self.assertEqual(result['training_fits'],5)
            self.assertEqual(len(result['trials']),4)
            self.assertEqual({r['poisoned_records'] for r in result['trials']},{5,15})
        np.testing.assert_array_equal(x,before);np.testing.assert_array_equal(y,labels)
        self.assertEqual(bytes(model.get_booster().save_raw()),raw)

    def test_multiclass_poisoning_and_trigger_have_controls(self):
        from sklearn.linear_model import LogisticRegression
        from model_release_assurance.tabular_red_team import label_poisoning,trigger_backdoor
        rng=np.random.default_rng(12);x=rng.normal(size=(180,3));y=np.digitize(x[:,0],[-.4,.4])*3+4
        model=LogisticRegression(max_iter=100).fit(x[:120],y[:120])
        target=RedTeamTarget('multiclass','logistic',model,x[:120],y[:120],x[120:],y[120:])
        before=model.coef_.copy();labels=y.copy()
        for tool in (label_poisoning,trigger_backdoor):
            report=tool(target,RedTeamConfig(seed=1))
            self.assertEqual(report['class_count'],3)
            self.assertEqual(report['training_fits'],5)
            self.assertEqual(len(report['trials']),4)
            if tool==trigger_backdoor:
                self.assertEqual(report['target_class'],10)
                self.assertTrue(all('clean_model_trigger_baseline' in trial for trial in report['trials']))
        np.testing.assert_array_equal(y,labels);np.testing.assert_array_equal(model.coef_,before)
