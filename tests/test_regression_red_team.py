import unittest

import numpy as np

from model_release_assurance.regression_red_team import run_suite


class RegressionRedTeamTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(42)
        self.x=rng.normal(size=(160,3))
        self.y=2*self.x[:,0]-self.x[:,1]

    def test_linear_model_runs_all_attacks_with_reproducible_controls_and_bounds(self):
        from sklearn.linear_model import Ridge
        model=Ridge(alpha=.1).fit(self.x[:80],self.y[:80])
        before=self.x.copy(); coefficients=model.coef_.copy()
        result=run_suite(model,self.x[:80],self.y[:80],self.x[80:],self.y[80:])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['execution_summary'],{'completed':3,'failed':0,'unsupported':0})
        self.assertTrue(all(result['tools'][0]['result']['controls'].values()))
        self.assertTrue(result['tools'][1]['result']['query_audit_partitions_disjoint'])
        for budget in result['tools'][2]['result']['adaptive_search']:
            self.assertGreaterEqual(budget['optimized_mse'],budget['clean_mse'])
            self.assertGreaterEqual(budget['random_search_mse'],budget['clean_mse'])
            self.assertEqual(budget['attack_queries'],budget['random_baseline_queries'])
        self.assertEqual(result,run_suite(model,self.x[:80],self.y[:80],self.x[80:],self.y[80:]))
        np.testing.assert_array_equal(before,self.x);np.testing.assert_array_equal(coefficients,model.coef_)
        self.assertFalse(result['can_clear']);self.assertFalse(result['authorization_eligible'])

    def test_deliberately_memorizing_regressor_triggers_membership(self):
        members={tuple(x):y for x,y in zip(self.x[:80],self.y[:80])}
        class Memorizer:
            def predict(self,x):return np.array([members.get(tuple(row),2*row[0]-row[1]+10) for row in x])
        report=run_suite(Memorizer(),self.x[:80],self.y[:80],self.x[80:],self.y[80:])
        probe=report['tools'][0]['result']
        self.assertEqual((probe['auc'],probe['tpr'],probe['fpr']),(1,1,0))

    def test_missing_or_nonfinite_prediction_fails_every_tool_and_retains_report(self):
        for prediction in (np.nan,np.inf):
            class Invalid:
                def predict(self,x):return np.full(len(x),prediction)
            report=run_suite(Invalid(),self.x[:80],self.y[:80],self.x[80:],self.y[80:])
            self.assertEqual(report['status'],'incomplete')
            self.assertEqual(report['execution_summary']['failed'],3)

    def test_column_vector_predictions_cannot_silently_broadcast(self):
        class Invalid:
            def predict(self,x):return np.zeros((len(x),1))
        report=run_suite(Invalid(),self.x[:80],self.y[:80],self.x[80:],self.y[80:])
        self.assertEqual(report['execution_summary']['failed'],3)

    def test_infinite_inputs_and_mismatched_labels_rejected(self):
        from sklearn.linear_model import Ridge
        for labels in (self.y[:79],self.y[:80,None],np.full(80,np.inf)):
            with self.assertRaises(ValueError):run_suite(Ridge(),self.x[:80],labels,self.x[80:],self.y[80:])
