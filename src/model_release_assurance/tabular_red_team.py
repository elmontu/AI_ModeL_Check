"""Bounded tabular red-team screens. No result is release authorization."""
from __future__ import annotations

from pathlib import Path
from .red_team import RedTeamConfig, RedTeamTarget, default_red_team_tool_registry
from .integrity import sha256_file


def threshold_probe(member, nonmember, seed):
    import numpy as np
    from sklearn.metrics import roc_auc_score
    member, nonmember = np.asarray(member, dtype=float), np.asarray(nonmember, dtype=float)
    if any(values.ndim != 1 or not np.isfinite(values).all() for values in (member, nonmember)):
        raise ValueError("membership scores must be finite one-dimensional arrays")
    rng = np.random.default_rng(seed)
    m, n = rng.permutation(member), rng.permutation(nonmember)
    cut_m, cut_n = len(m) // 2, len(n) // 2
    if min(cut_m, cut_n) < 10:
        raise ValueError("at least 20 member and 20 nonmember observations required")
    # Threshold is chosen on calibration nonmembers, never evaluation observations.
    threshold = float(np.quantile(n[:cut_n], .9, method="higher"))
    m, n = m[cut_m:], n[cut_n:]
    return {"auc": float(roc_auc_score(np.r_[np.ones(len(m)), np.zeros(len(n))], np.r_[m,n])),
            "threshold": threshold, "member_trials": len(m), "nonmember_trials": len(n),
            "true_positives": int((m > threshold).sum()), "false_positives": int((n > threshold).sum()),
            "tpr": float((m > threshold).mean()), "fpr": float((n > threshold).mean()),
            "target_fpr": .1, "threshold_comparison": "strict_greater",
            "calibration_separate_from_evaluation": True,
            "interpretation": "empirical screen; no certified operating point or privacy ceiling"}


def _probabilities(model, x, labels):
    """Validate classifier output and map class values to probability columns."""
    import numpy as np
    p = np.asarray(model.predict_proba(x), dtype=float)
    if p.ndim != 2 or p.shape[0] != len(labels) or p.shape[1] < 2:
        raise ValueError("predict_proba must return one row per record and at least two classes")
    if not np.isfinite(p).all() or np.any(p < 0) or np.any(p > 1) or not np.allclose(p.sum(axis=1), 1):
        raise ValueError("predict_proba must return finite normalized probabilities")
    classes = np.asarray(getattr(model, "classes_", np.arange(p.shape[1])))
    if classes.ndim != 1 or len(classes) != p.shape[1] or len(np.unique(classes)) != len(classes):
        raise ValueError("classifier class order is invalid")
    matches = np.asarray(labels)[:, None] == classes[None, :]
    if matches.ndim != 2 or not np.all(matches.sum(axis=1) == 1):
        raise ValueError("every label must map to one classifier probability column")
    return np.clip(p, 1e-12, 1), matches.argmax(axis=1)


def membership_scores(target, config):
    import numpy as np
    views = [_probabilities(target.model, x, y) for x, y in
             ((target.train_x, target.train_y), (target.test_x, target.test_y))]
    probes = {}
    for name in ("negative_loss", "confidence", "negative_entropy"):
        values=[]
        for p,y in views:
            if name == "negative_loss": score=np.log(p[np.arange(len(y)), y])
            elif name == "confidence": score=p.max(axis=1)
            else: score=(p*np.log(p)).sum(axis=1)
            values.append(score)
        probes[name]=threshold_probe(*values, config.seed)
    # Deliberately leaking and constant-score controls exercise the same scorer.
    leak=threshold_probe(np.ones(80), np.zeros(80), config.seed)
    null=threshold_probe(np.zeros(80), np.zeros(80), config.seed)
    controls={"known_leak_detected": leak["auc"] == 1 and leak["tpr"] == 1 and leak["fpr"] == 0,
              "constant_output_baseline": null["auc"] == .5 and null["tpr"] == 0}
    return {"probes": probes, "controls": controls,
            "control_scope": "score-evaluation harness only; not an end-to-end leaking-model control"}


def extraction(target, config):
    import numpy as np
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.dummy import DummyClassifier
    # Attacker gets a bounded auxiliary query set, not the model's training records.
    x=np.asarray(target.test_x); split=len(x)//2
    if split < 20: raise ValueError("at least 40 auxiliary records required")
    order=np.random.default_rng(config.seed).permutation(len(x)); query, audit=x[order[:split]],x[order[split:]]
    answers=target.model.predict(query); expected=target.model.predict(audit)
    surrogate=DecisionTreeClassifier(max_depth=4, random_state=config.seed).fit(query, answers)
    baseline=DummyClassifier(strategy="most_frequent").fit(query,answers)
    return {"query_budget": len(query), "evaluation_records": len(audit),
            "surrogate_agreement": float(np.mean(surrogate.predict(audit)==expected)),
            "majority_baseline_agreement": float(np.mean(baseline.predict(audit)==expected)),
            "scope": "label-only functional imitation; does not demonstrate weight recovery"}


def attribute_inference(target, config):
    import numpy as np
    # Fixed first transformed feature and bins chosen from auxiliary calibration data.
    x=np.asarray(target.test_x); split=len(x)//2
    if split < 20: raise ValueError("at least 40 auxiliary records required")
    order=np.random.default_rng(config.seed).permutation(len(x)); cal=x[order[:split]]; audit=x[order[split:]]
    labels=np.asarray(target.test_y)[order[split:]]
    edges=np.unique(np.quantile(cal[:,0],[1/3,2/3]))
    bins=np.digitize(cal[:,0], edges)
    candidates=np.array([np.median(cal[bins==i,0]) if np.any(bins==i) else np.median(cal[:,0]) for i in range(len(edges)+1)])
    scores=[]
    for value in candidates:
        query=audit.copy();query[:,0]=value
        probabilities, columns = _probabilities(target.model, query, labels)
        scores.append(probabilities[np.arange(len(query)), columns])
    guessed=np.argmax(scores,axis=0); truth=np.digitize(audit[:,0],edges)
    majority=int(np.bincount(bins,minlength=len(candidates)).argmax())
    return {"feature_index": 0, "bins": len(candidates), "evaluation_records": len(audit),
            "query_budget": len(audit)*len(candidates), "accuracy": float(np.mean(guessed==truth)),
            "majority_baseline_accuracy": float(np.mean(truth==majority)),
            "assumption": "attacker knows other transformed features and true class; first feature is illustrative, not declared sensitive",
            "scope": "coarse attribute inference, not full-record reconstruction"}


def robustness(target, config):
    import numpy as np
    x=np.asarray(target.test_x); y=np.asarray(target.test_y)
    scale=np.std(target.train_x,axis=0);rng=np.random.default_rng(config.seed)
    clean=target.model.predict(x); results=[]
    for magnitude in (.05,.2):
        perturbed=x+rng.normal(size=x.shape)*scale*magnitude
        prediction=target.model.predict(perturbed)
        results.append({"standard_deviation_fraction": magnitude,
                        "accuracy": float(np.mean(prediction==y)),
                        "prediction_flip_rate": float(np.mean(prediction!=clean))})
    return {"clean_accuracy":float(np.mean(clean==y)),"perturbations":results,
            "scope":"random numeric perturbation screen; not optimized adversarial or semantic robustness"}


def adversarial_search(target, config):
    """Greedy score-query attack inside a bounded numeric box, with random baseline."""
    import numpy as np
    rng = np.random.default_rng(config.seed)
    order = rng.permutation(len(target.test_y))[:128]
    x = np.asarray(target.test_x)[order].copy()
    y = np.asarray(target.test_y)[order]
    scale = np.std(target.train_x, axis=0)
    initial, columns = _probabilities(target.model, x, y)
    # Calibrated estimators can predict a label different from probability argmax.
    correct = np.asarray(target.model.predict(x)) == y
    rows = np.arange(len(y))
    results = []
    for epsilon in (.1, .3):
        best = x.copy()
        loss = -np.log(initial[rows, columns])
        random_best = loss.copy()
        random_points = x.copy()
        for _ in range(24):
            proposal = best + rng.choice([-1., 1.], size=x.shape) * scale * epsilon / 4
            proposal = np.clip(proposal, x - epsilon * scale, x + epsilon * scale)
            probabilities, _ = _probabilities(target.model, proposal, y)
            score = -np.log(probabilities[rows, columns])
            improved = score > loss
            best[improved] = proposal[improved]
            loss = np.maximum(loss, score)
            baseline = x + rng.uniform(-1, 1, size=x.shape) * scale * epsilon
            probabilities, _ = _probabilities(target.model, baseline, y)
            baseline_loss = -np.log(probabilities[rows, columns])
            random_points[baseline_loss > random_best] = baseline[baseline_loss > random_best]
            random_best = np.maximum(random_best, baseline_loss)
        prediction = target.model.predict(best)
        baseline_prediction = target.model.predict(random_points)
        results.append({"epsilon_training_std": epsilon, "optimization_steps": 24,
                        "attack_queries_excluding_shared_initial": int(25 * len(x)), "random_baseline_queries": int(25 * len(x)),
                        "initially_correct": int(correct.sum()),
                        "successful_flips": int(((prediction != y) & correct).sum()),
                        "attack_success_rate_on_correct": float(np.mean(prediction[correct] != y[correct])) if correct.any() else None,
                        "random_baseline_success_rate_on_correct": float(np.mean(baseline_prediction[correct] != y[correct])) if correct.any() else None,
                        "attacked_accuracy": float(np.mean(prediction == y)),
                        "mean_optimized_loss": float(loss.mean()), "mean_random_search_loss": float(random_best.mean())})
    return {"evaluation_records": len(x), "shared_initial_queries": int(2 * len(x)), "budgets": results,
            "attacker_access": "probability and label queries, true evaluation labels, and feature scales from training data",
            "scope": "adaptive score-query untargeted attack in transformed numeric space; perturbations may not be semantically valid"}


def leaf_exposure(target, config):
    import numpy as np
    if target.model_kind not in {"xgboost", "random-forest"}:
        return {"unsupported": True, "reason": "requires a supported tree model with leaf-index access"}
    train = np.asarray(target.model.apply(target.train_x)).reshape(len(target.train_y), -1)
    test = np.asarray(target.model.apply(target.test_x)).reshape(len(target.test_y), -1)
    smallest = np.full(len(train), len(train))
    unseen = 0
    for column in range(train.shape[1]):
        leaf, inverse, counts = np.unique(train[:, column], return_inverse=True, return_counts=True)
        smallest = np.minimum(smallest, counts[inverse])
        unseen += int((~np.isin(test[:, column], leaf)).sum())
    _, signatures = np.unique(train, axis=0, return_counts=True)
    return {"trees": train.shape[1], "train_records": len(train),
            "records_with_singleton_leaf": int((smallest == 1).sum()),
            "records_with_leaf_occupancy_below_five": int((smallest < 5).sum()),
            "unique_full_path_signatures": int((signatures == 1).sum()),
            "test_leaf_visits_absent_from_training": unseen,
            "scope": "white-box path uniqueness and occupancy; not a demonstrated record reconstruction"}


def controlled_retraining(target, config, *, backdoor=False):
    import numpy as np
    from sklearn.base import clone
    # Only bounded known estimator classes can enter controlled retraining.
    parameters = target.model.get_params() if target.model is not None else {}
    kind = target.model_kind
    if kind == "xgboost":
        supported = target.model.__class__.__module__.split('.')[0] == 'xgboost' and parameters.get('n_estimators') is not None and parameters['n_estimators'] <= 64 and parameters.get('max_depth') is not None and parameters['max_depth'] <= 6
    elif kind == "random-forest":
        supported = target.model.__class__.__name__ == "RandomForestClassifier" and parameters.get('n_estimators', 1000) <= 64 and parameters.get('max_depth') is not None and parameters['max_depth'] <= 6
    elif kind == "logistic":
        supported = target.model.__class__.__name__ == "LogisticRegression" and parameters.get('max_iter', 1000) <= 300
    elif kind == "mlp":
        supported = target.model.__class__.__name__ == "MLPClassifier" and parameters.get('max_iter', 1000) <= 120
    else:
        supported = False
    if not supported:
        return {"unsupported": True, "reason": "no bounded controlled-retraining adapter for this estimator/configuration"}
    def copy_model():
        model = clone(target.model)
        settings = {"random_state": config.seed}
        if "n_jobs" in model.get_params(): settings["n_jobs"] = 1
        return model.set_params(**settings)
    x = np.asarray(target.train_x).copy(); y = np.asarray(target.train_y).copy()
    test = np.asarray(target.test_x); truth = np.asarray(target.test_y)
    classes = np.unique(y)
    if len(classes) < 2:
        return {"unsupported": True, "reason": "controlled classification poisoning requires at least two classes"}
    clean = copy_model().fit(x, y)
    clean_accuracy = float(np.mean(clean.predict(test) == truth))
    trigger = float(np.max(x[:, 0]) + max(np.std(x[:, 0]), 1.))
    target_class = classes[-1]
    triggered = test.copy(); triggered[:, 0] = trigger
    eligible = truth != target_class
    baseline_asr = float(np.mean(clean.predict(triggered)[eligible] == target_class)) if eligible.any() else None
    trials = []
    for repeat in range(2):
        order = np.random.default_rng(config.seed + repeat).permutation(len(y))
        for fraction in (.05, .15):
            count = max(1, int(len(y) * fraction)); indices = order[:count]
            poisoned_x = x.copy(); poisoned_y = y.copy()
            if backdoor:
                poisoned_x[indices, 0] = trigger; poisoned_y[indices] = target_class
            else:
                # Cycle to a different class, including nonzero and string labels.
                poisoned_y[indices] = classes[(np.searchsorted(classes, y[indices]) + 1) % len(classes)]
            altered = copy_model().fit(poisoned_x, poisoned_y)
            accuracy = float(np.mean(altered.predict(test) == truth))
            item = {"repeat": repeat, "poison_fraction": fraction, "poisoned_records": count,
                    "clean_test_accuracy": accuracy, "accuracy_drop_from_clean_retrain": clean_accuracy - accuracy}
            if backdoor:
                item["non_target_evaluation_records"] = int(eligible.sum())
                item["trigger_attack_success_rate"] = float(np.mean(altered.predict(triggered)[eligible] == target_class)) if eligible.any() else None
                item["clean_model_trigger_baseline"] = baseline_asr
            trials.append(item)
    return {"clean_retrain_accuracy": clean_accuracy, "trials": trials,
            "training_fits": 5, "original_candidate_modified": False,
            "class_count": len(classes), "label_flip_strategy": None if backdoor else "cyclic next class",
            "target_class": target_class.item() if backdoor else None,
            "scope": "in-memory experimental retraining of copies; evaluates a hypothetical compromised training process, not evidence that the released model is poisoned",
            "trigger_feature": 0 if backdoor else None,
            "trigger_scope": "out-of-range first transformed numeric feature" if backdoor else None}


def label_poisoning(target, config):
    return controlled_retraining(target, config)


def trigger_backdoor(target, config):
    return controlled_retraining(target, config, backdoor=True)


def label_only_membership(target, config):
    import numpy as np
    member = (target.model.predict(target.train_x) == target.train_y).astype(float)
    nonmember = (target.model.predict(target.test_x) == target.test_y).astype(float)
    result = threshold_probe(member, nonmember, config.seed)
    result["scope"] = "correctness-based label-only membership; attacker knows true labels; strict threshold can abstain on ties"
    return result


def run_tabular_suite(target: RedTeamTarget, config: RedTeamConfig) -> dict:
    import numpy as np
    # This educational implementation is bounded and accepts numeric classifier views only.
    for x,y in ((target.train_x,target.train_y),(target.test_x,target.test_y)):
        if len(y)>5000 or len(y)<40: raise ValueError("suite requires 40..5000 records per partition")
        if np.asarray(y).ndim != 1 or len(x) != len(y):
            raise ValueError("features and one-dimensional labels must have equal row counts")
        if np.asarray(x).ndim!=2 or not 1 <= np.asarray(x).shape[1] <= 256 or not np.isfinite(x).all():
            raise ValueError("suite requires finite dense numeric inputs with at most 256 features")
    if np.asarray(target.train_x).shape[1] != np.asarray(target.test_x).shape[1]:
        raise ValueError("training and evaluation feature counts must match")
    reports=[]
    tools=[(tool.name,tool.run) for tool in default_red_team_tool_registry().tools]
    tools += [("membership_score_attacks",membership_scores),("model_extraction",extraction),
              ("attribute_inference",attribute_inference),("numeric_robustness",robustness),
              ("label_only_membership",label_only_membership),("adaptive_adversarial_search",adversarial_search),
              ("tree_leaf_exposure",leaf_exposure),("label_poisoning",label_poisoning),
              ("trigger_backdoor",trigger_backdoor)]
    for name,run in tools:
        try:
            if name == "structural_disclosure" and target.model_kind == "ensemble":
                detail = {"unsupported":True,"reason":"composite parameter accounting requires component-aware structural analysis"}
            elif name in {"structural_disclosure", "worst_case_membership"}:
                # The older tools index probability columns with encoded labels.
                # Present a view; never change the candidate or its class values.
                _, train_columns = _probabilities(target.model, target.train_x, target.train_y)
                _, test_columns = _probabilities(target.model, target.test_x, target.test_y)
                classes = np.asarray(getattr(target.model, "classes_", np.unique(target.train_y)))
                class EncodedView:
                    def __getattr__(self, key): return getattr(target.model, key)
                    def predict(self, x):
                        values = np.asarray(target.model.predict(x))
                        matches = values[:, None] == classes[None, :]
                        if not np.all(matches.sum(axis=1) == 1): raise ValueError("invalid predicted class")
                        return matches.argmax(axis=1)
                view = RedTeamTarget(target.target_id, target.model_kind, EncodedView(),
                                     target.train_x, train_columns, target.test_x, test_columns)
                detail = run(view, config)
            else:
                detail=run(target,config)
            status = "unsupported" if detail.get("unsupported") else "completed"
            if "controls" in detail and not all(detail["controls"].values()): status = "failed"
            reports.append({"tool":name,"status":status,"result":detail,"can_clear":False,"can_block":False})
        except Exception as exc:
            reports.append({"tool":name,"status":"failed","error_type":type(exc).__name__,"can_clear":False,"can_block":False})
    return {"format_version":"educational-tabular-red-team/2", "seed":config.seed,
            "configuration":config.model_dump(mode="json"),
            "implementation_sha256":sha256_file(Path(__file__)),
            "legacy_tools_sha256":sha256_file(Path(__file__).with_name("red_team.py")),
            "tools":reports,"status":"completed" if all(r["status"]=="completed" for r in reports) else "incomplete",
            "execution_summary": {status: sum(r["status"] == status for r in reports) for status in ("completed", "failed", "unsupported")},
            "coverage_gaps":["LLM prompt injection and text extraction: unsupported by tabular preset",
                             "Clean-label, targeted and supply-chain poisoning: not tested; current retraining covers label flips and one numeric trigger",
                             "Full-record reconstruction: not tested",
                             "Fine-tuned/base and combined-component comparisons: not tested",
                             "End-to-end positive controls for every attack: not implemented",
                             "Semantic/adversarial guarantees and complete-interface privacy ceilings: not established"],
            "assessment_eligible":False,"can_clear":False,"can_block":False,"authorization_eligible":False,
            "record_level_output_retained":False,
            "note":"Exploratory screens only. Completed means executed, not safe or passed. Auxiliary data access is stronger than many recipient scenarios."}
