"""Bounded regression attack screens with controls; never clearing evidence."""
from pathlib import Path

import numpy as np

from .integrity import sha256_file
from .tabular_red_team import threshold_probe


def _predict(model, features):
    prediction = np.asarray(model.predict(features), dtype=float)
    if prediction.shape != (len(features),) or not np.isfinite(prediction).all():
        raise ValueError("regressor must return one finite scalar per record")
    return prediction


def run_suite(model, train_x, train_y, test_x, test_y, seed=3407):
    from sklearn.tree import DecisionTreeRegressor

    train_x, test_x = np.asarray(train_x, dtype=float), np.asarray(test_x, dtype=float)
    train_y, test_y = np.asarray(train_y, dtype=float), np.asarray(test_y, dtype=float)
    for x, y in ((train_x, train_y), (test_x, test_y)):
        if x.ndim != 2 or not 1 <= x.shape[1] <= 256 or y.shape != (len(x),):
            raise ValueError("regression requires dense features and one scalar label per record")
        if not 40 <= len(y) <= 5000 or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("regression requires 40..5000 finite records per partition")
    if train_x.shape[1] != test_x.shape[1]:
        raise ValueError("training and evaluation feature counts must match")

    def membership():
        member = -np.square(_predict(model, train_x) - train_y)
        nonmember = -np.square(_predict(model, test_x) - test_y)
        result = threshold_probe(member, nonmember, seed)
        leak = threshold_probe(np.ones(80), np.zeros(80), seed)
        null = threshold_probe(np.zeros(80), np.zeros(80), seed)
        result['controls'] = {'known_leak_detected': leak['auc'] == 1 and leak['tpr'] == 1 and leak['fpr'] == 0,
                              'constant_score_baseline': null['auc'] == .5 and null['tpr'] == 0}
        result['attacker_access'] = 'scalar prediction queries and true labels of candidate records'
        result['control_scope'] = 'score harness; no end-to-end leaking regressor control'
        return result

    def extraction():
        order = np.random.default_rng(seed).permutation(len(test_y))
        split = len(test_y) // 2
        query, audit = test_x[order[:split]], test_x[order[split:]]
        answers, expected = _predict(model, query), _predict(model, audit)
        student = DecisionTreeRegressor(max_depth=4, random_state=seed).fit(query, answers)
        return {'query_budget': len(query), 'audit_target_queries': len(audit), 'audit_records': len(audit),
                'surrogate_teacher_mse': float(np.mean((expected - student.predict(audit)) ** 2)),
                'constant_baseline_mse': float(np.mean((expected - answers.mean()) ** 2)),
                'query_audit_partitions_disjoint': True,
                'scope': 'functional imitation from scalar outputs; no weight recovery',
                'attacker_access': 'auxiliary nonmember records and scalar prediction queries; no training records'}

    def perturbation():
        rng = np.random.default_rng(seed)
        scale = np.std(train_x, axis=0)
        clean = _predict(model, test_x)
        noise = []
        for epsilon in (.05, .2):
            prediction = _predict(model, test_x + rng.normal(size=test_x.shape) * scale * epsilon)
            noise.append({'training_std_fraction': epsilon, 'mse': float(np.mean((test_y - prediction) ** 2)),
                          'prediction_shift_mse': float(np.mean((clean - prediction) ** 2))})
        order = rng.permutation(len(test_y))[:128]
        x, truth = test_x[order], test_y[order]
        initial = np.square(clean[order] - truth)
        searches = []
        for epsilon in (.1, .3):
            best, loss, random_loss = x.copy(), initial.copy(), initial.copy()
            for _ in range(24):
                query = best + rng.choice([-1., 1.], size=x.shape) * scale * epsilon / 4
                query = np.clip(query, x - epsilon * scale, x + epsilon * scale)
                value = np.square(_predict(model, query) - truth)
                best[value > loss] = query[value > loss]
                loss = np.maximum(loss, value)
                query = x + rng.uniform(-1, 1, size=x.shape) * scale * epsilon
                random_loss = np.maximum(random_loss, np.square(_predict(model, query) - truth))
            searches.append({'epsilon_training_std': epsilon, 'evaluation_records': len(x),
                             'optimization_steps': 24, 'attack_queries': 24 * len(x),
                             'random_baseline_queries': 24 * len(x), 'clean_mse': float(initial.mean()),
                             'optimized_mse': float(loss.mean()), 'random_search_mse': float(random_loss.mean())})
        return {'clean_mse': float(np.mean((test_y - clean) ** 2)), 'tests': noise,
                'adaptive_search': searches, 'shared_initial_queries': len(test_x),
                'attacker_access': 'scalar prediction queries, true labels, and training feature scales',
                'scope': 'random and greedy untargeted numeric perturbations; no claim of semantic validity'}

    reports = []
    for name, operation in [('regression_loss_membership', membership), ('regression_extraction', extraction),
                            ('regression_perturbation', perturbation)]:
        try:
            result = operation()
            status = 'completed' if all(result.get('controls', {}).values()) else 'failed'
            reports.append({'tool': name, 'status': status, 'result': result, 'can_clear': False, 'can_block': False})
        except Exception as exc:
            reports.append({'tool': name, 'status': 'failed', 'error_type': type(exc).__name__,
                            'can_clear': False, 'can_block': False})
    return {'format_version': 'regression-red-team/2', 'seed': seed,
            'status': 'completed' if all(item['status'] == 'completed' for item in reports) else 'incomplete',
            'tools': reports, 'implementation_sha256': sha256_file(Path(__file__)),
            'membership_scorer_sha256': sha256_file(Path(__file__).with_name('tabular_red_team.py')),
            'execution_summary': {status: sum(item['status'] == status for item in reports) for status in ('completed', 'failed', 'unsupported')},
            'coverage_gaps': ['Regression attribute reconstruction and poisoning are not covered',
                              'No end-to-end positive control for every attack', 'No complete-interface privacy ceiling'],
            'note': 'Completed means executed, not safe or passed. These screens are exploratory.',
            'assessment_eligible': False, 'authorization_eligible': False, 'can_clear': False, 'can_block': False}
