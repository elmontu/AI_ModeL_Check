"""Offline educational model adapters and capability inventory."""
from __future__ import annotations

from pathlib import Path

PRESETS = {
    "xgboost-small": "XGBoost (registered assessment demo)",
    "logistic": "Logistic regression",
    "random-forest": "Random forest",
    "mlp": "Small neural network (MLP)",
    "mlp-finetuned": "Fine-tuned MLP with retained base model",
    "cnn": "CPU convolutional digit classifier",
    "ridge": "Ridge regression",
    "forest-regression": "Random forest regression",
    "svm": "RBF support-vector classifier",
    "ensemble": "Soft-voting linear + forest ensemble",
}
DATASETS = {
    "sklearn-breast-cancer": "Wisconsin breast cancer · 569 rows · 30 features · 2 classes",
    "sklearn-wine": "Wine · 178 rows · 13 features · 3 classes",
    "sklearn-digits": "Handwritten digits · 1797 images · 64 pixels · 10 classes",
    "sklearn-diabetes": "Diabetes progression · 442 records · 10 features · continuous target",
}

def capability_inventory():
    return {"presets": PRESETS, "datasets": DATASETS,
            "training": "Ten CPU presets across four public datasets, including a convolutional classifier and regression; dataset compatibility is enforced",
            "red_team": "Classification and regression attacks, derivative/component comparisons, image translations and nine local Ollama language tests with two controls; unsupported adapters remain explicit",
            "assessment": "All ten presets generate registered membership-evidence assessments; the broader attack suite remains exploratory",
            "other_framework_paths": [
                {"family": "larger vision CNN", "entry": "scripts/run_vision_training_hook_audit.py", "status": "separate experiment profile; the small digits CNN is available in the wizard"},
                {"family": "LLM", "entry": "scripts/run_llm_training_hook_audit.py", "status": "separate experiment script; not a console trainer"},
                {"family": "composition", "entry": "scripts/run_llm_composition_scaling.py", "status": "separate experiment script; joint-release evidence still required"}],
            "missing": ["Large-model fine-tuning requires an external training runtime", "High-resolution vision training requires an external runtime",
                        "Live retrieval-index and real agent integration beyond synthetic document/inert-tool tests",
                        "Diffusion/audio/generative-model workers", 
                        "Threat-specific ceilings and independent review for real agency data", "Production deployment controls"]}


def make_model(preset, seed):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, VotingClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.svm import SVC
    if preset == "ridge":
        from sklearn.linear_model import Ridge
        return Ridge(alpha=1.)
    if preset == "forest-regression":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(n_estimators=32,max_depth=5,n_jobs=1,random_state=seed)
    if preset == "cnn":
        from .tiny_cnn import TinyCNN
        return TinyCNN(random_state=seed)
    if preset == "logistic": return LogisticRegression(max_iter=300, random_state=seed)
    if preset == "random-forest": return RandomForestClassifier(n_estimators=32,max_depth=5,n_jobs=1,random_state=seed)
    if preset in {"mlp", "mlp-finetuned"}: return MLPClassifier(hidden_layer_sizes=(24,),max_iter=120,early_stopping=preset!="mlp-finetuned",random_state=seed)
    if preset == "svm": return SVC(C=1,probability=True,random_state=seed)
    if preset == "ensemble":
        return VotingClassifier(estimators=[("linear",make_model("logistic",seed)),("forest",make_model("random-forest",seed))],voting="soft",n_jobs=1)
    raise ValueError("unsupported local adapter")


def _parameters(value):
    """Retain structured estimator parameters rather than an opaque repr."""
    if hasattr(value, "get_params"):
        return {"class": type(value).__module__ + "." + type(value).__qualname__,
                "parameters": _parameters(value.get_params(deep=False))}
    if isinstance(value, dict): return {str(k): _parameters(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_parameters(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)): return value
    raise ValueError(f"unrecorded training parameter type: {type(value).__name__}")


def _verify_export(path, original_model, original_scaler, raw_x):
    """Verify our freshly written trusted bundle using the recipient's raw input."""
    import joblib
    import numpy as np
    bundle = joblib.load(path)
    transformed = bundle["scaler"].transform(raw_x)
    original_x = original_scaler.transform(raw_x)
    np.testing.assert_allclose(transformed, original_x, rtol=0, atol=0)
    np.testing.assert_allclose(bundle["model"].predict(transformed), original_model.predict(original_x), rtol=0, atol=0)
    if hasattr(original_model, "predict_proba"):
        np.testing.assert_allclose(bundle["model"].predict_proba(transformed), original_model.predict_proba(original_x), rtol=1e-12, atol=1e-12)
    return bundle


def run_public(preset, dataset, output):
    import warnings
    import joblib
    import numpy as np
    from sklearn.datasets import load_breast_cancer, load_wine, load_digits, load_diabetes
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss
    from . import workflow
    from .red_team import RedTeamConfig, RedTeamTarget
    from .tabular_red_team import run_tabular_suite
    if dataset not in DATASETS: raise ValueError("unsupported public dataset")
    if preset == "cnn" and dataset != "sklearn-digits": raise ValueError("CNN preset requires digits")
    regression=preset in {"ridge","forest-regression"}
    if regression != (dataset=="sklearn-diabetes"):raise ValueError("regression presets require the diabetes dataset")
    model=make_model(preset,3407)
    output.mkdir(parents=True,exist_ok=False)
    data={"sklearn-breast-cancer":load_breast_cancer,"sklearn-wine":load_wine,"sklearn-digits":load_digits,"sklearn-diabetes":load_diabetes}[dataset]()
    indices=np.arange(len(data.target))
    train,test=train_test_split(indices,test_size=.35,stratify=None if regression else data.target,random_state=3407)
    # Fit the fixed utility comparator before training, using training labels only.
    if regression:
        baseline_prediction=float(np.mean(data.target[train]))
    else:
        baseline_classes,baseline_counts=np.unique(data.target[train],return_counts=True)
        baseline_prediction=baseline_classes[np.argmax(baseline_counts)].item()
    base_train=train[:len(train)//2] if preset=="mlp-finetuned" else train
    scaler=StandardScaler().fit(data.data[base_train])
    train_x=scaler.transform(data.data[train]);test_x=scaler.transform(data.data[test])
    recipe={"preset":preset,"dataset":dataset,"seed":3407,"test_fraction":.35,
            "scaler":"StandardScaler fitted on base-training subset only" if preset=="mlp-finetuned" else "StandardScaler fitted on training partition only",
            "parameters":_parameters(model),"calibration_rule":"first half of the fixed nonmember partition; remaining rows are audit controls"}
    if preset=="mlp-finetuned": recipe["fine_tuning"]={"base_training_fraction":.5,"base_max_epochs":120,"derivative_max_epochs":30,"warm_start":True,"derivative_training_fraction":1.0}
    workflow.write_json(output/"training-config.json",recipe)
    np.savez_compressed(output/"public-dataset.npz",x=data.data,y=data.target,train=train,test=test,
                        calibration=test[:len(test)//2],audit=test[len(test)//2:],base_train=base_train)
    workflow.write_json(output/"data-manifest.json",{"dataset":dataset,"dataset_sha256":workflow.digest(output/"public-dataset.npz"),"source":"scikit-learn bundled public sample","training_records":len(train),"test_records":len(test)})
    from .registered_training import prepare, assess, now, _iso
    plan=prepare(output,{"name":DATASETS[dataset],"rows":len(data.target)},len(train),len(test)-len(test)//2)
    plan['training_started_at']=_iso(now())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if preset == "mlp-finetuned":
            model.fit(train_x[:len(train)//2],data.target[train][:len(train)//2])
            joblib.dump({"model":model,"scaler":scaler,"classes":getattr(data,"target_names",None)},output/"base-model.joblib")
            _verify_export(output/"base-model.joblib",model,scaler,data.data)
            model.set_params(warm_start=True,early_stopping=False,max_iter=30)
        model.fit(train_x,data.target[train])
    plan['training_completed_at']=_iso(now())
    warnings_seen=sorted({type(w.message).__name__ for w in caught})
    candidate=output/"model.joblib"
    joblib.dump({"model":model,"scaler":scaler,"classes":getattr(data,"target_names",None)},candidate)
    artifact_hash=workflow.digest(candidate)
    # Only reload our own freshly generated local artifact; never arbitrary user joblib.
    exported=_verify_export(candidate,model,scaler,data.data)
    reloaded=exported["model"]
    # Evidence uses the reloaded recipient preprocessing, including on membership rows.
    train_x=exported["scaler"].transform(data.data[train]);test_x=exported["scaler"].transform(data.data[test])
    workflow.write_json(output/"export-verification.json",{"candidate_sha256":artifact_hash,"raw_input_records":len(data.target),
        "preprocessing_identical":True,"predictions_identical":True,"probabilities_identical":not regression,
        "scope":"Fresh trusted joblib model+scaler bundle roundtrip; no claim of safe arbitrary pickle import"})
    assessment=assess(output,plan,reloaded,train_x,data.target[train],test_x,data.target[test],preset,regression=regression)
    if regression:
        from .regression_red_team import run_suite
        red_team=run_suite(reloaded,train_x,data.target[train],test_x,data.target[test])
    else:
        red_team=run_tabular_suite(RedTeamTarget(preset,"mlp" if preset=="mlp-finetuned" else preset,reloaded,train_x,data.target[train],test_x,data.target[test]),RedTeamConfig(seed=3407,membership_repetitions=2))
    red_team["release_artifact_sha256"]=artifact_hash
    red_team["training_config_sha256"]=workflow.digest(output/"training-config.json")
    red_team["dataset_manifest_sha256"]=workflow.digest(output/"data-manifest.json")

    utility_warnings=[]
    baseline={"type":"training_mean" if regression else "training_majority_class",
              "prediction":baseline_prediction,"fit_records":len(train),"evaluation_records":len(test)}
    baseline_predictions=np.full(len(test),baseline_prediction)
    if regression:
        from sklearn.metrics import mean_squared_error,mean_absolute_error,r2_score
        prediction=model.predict(test_x)
        utility={"mean_squared_error":float(mean_squared_error(data.target[test],prediction)),"mean_absolute_error":float(mean_absolute_error(data.target[test],prediction)),"r2":float(r2_score(data.target[test],prediction))}
        baseline["mean_squared_error"]=float(mean_squared_error(data.target[test],baseline_predictions))
        utility["beats_baseline"]=utility["mean_squared_error"]<baseline["mean_squared_error"]
        if not utility["beats_baseline"]:
            utility_warnings.append(f"Utility warning: held-out MSE ({utility['mean_squared_error']:.6g}) is no better than the training-mean baseline ({baseline['mean_squared_error']:.6g}).")
    else:
        utility={"accuracy":float(accuracy_score(data.target[test],model.predict(test_x))),"balanced_accuracy":float(balanced_accuracy_score(data.target[test],model.predict(test_x))),"log_loss":float(log_loss(data.target[test],model.predict_proba(test_x)))}
        baseline.update(accuracy=float(accuracy_score(data.target[test],baseline_predictions)),
                        balanced_accuracy=float(balanced_accuracy_score(data.target[test],baseline_predictions)))
        utility["beats_baseline"]=all(utility[metric]>baseline[metric] for metric in ('accuracy','balanced_accuracy'))
        for metric in ('accuracy','balanced_accuracy'):
            if utility[metric]<=baseline[metric]:
                utility_warnings.append(f"Utility warning: held-out {metric.replace('_',' ')} ({utility[metric]:.6g}) is no better than the training-majority baseline ({baseline[metric]:.6g}).")
    utility["baseline"]=baseline
    workflow.write_json(output/"utility-report.json",utility)
    if dataset == "sklearn-digits":
        image=data.data[test].reshape(-1,8,8)
        image_tests=[]
        for axis in (1,2):
            shifted=np.roll(image,1,axis=axis)
            if axis==1: shifted[:,0,:]=0
            else: shifted[:,:,0]=0
            prediction=model.predict(scaler.transform(shifted.reshape(-1,64)))
            image_tests.append({"transform":"one_pixel_vertical" if axis==1 else "one_pixel_horizontal","accuracy":float(accuracy_score(data.target[test],prediction)),"records":len(test)})
        workflow.write_json(output/"image-tests.json",{"tests":image_tests,"scope":"fixed one-pixel translations with zero fill; no semantic guarantee"})
    comparisons=[]
    if preset == "mlp-finetuned":
        from .tabular_red_team import threshold_probe
        base=joblib.load(output/"base-model.joblib")["model"]
        metrics=[]
        for name,estimator in (("base",base),("fine_tuned",model)):
            member=-np.log(np.clip(estimator.predict_proba(train_x)[np.arange(len(train)),data.target[train]],1e-12,1))
            nonmember=-np.log(np.clip(estimator.predict_proba(test_x)[np.arange(len(test)),data.target[test]],1e-12,1))
            metrics.append({"model":name,"membership":threshold_probe(-member,-nonmember,3407)})
        workflow.write_json(output/"derivative-privacy-comparison.json",{"comparisons":metrics,"scope":"same candidate-training population for comparison; base only trained on its initial subset, so the base score is a transfer baseline, not base membership accuracy","can_clear":False})
        comparisons.append({"component":"base","path":"base-model.joblib","sha256":workflow.digest(output/"base-model.joblib"),"accuracy":float(accuracy_score(data.target[test],base.predict(test_x)))})
    if preset=="ensemble":
        for name,component in zip(("linear","forest"),model.estimators_):
            path=output/(name+".joblib");joblib.dump({"model":component,"scaler":scaler,"classes":getattr(data,"target_names",None)},path)
            _verify_export(path,component,scaler,data.data)
            comparisons.append({"component":name,"path":path.name,"sha256":workflow.digest(path),"accuracy":float(accuracy_score(data.target[test],component.predict(test_x))),"agreement_with_ensemble":float(np.mean(component.predict(test_x)==model.predict(test_x)))})
    if preset == "ensemble":
        from .tabular_red_team import threshold_probe
        member_scores=[];nonmember_scores=[];attacks=[]
        for name,component in zip(("linear","forest"),model.estimators_):
            m=np.log(np.clip(component.predict_proba(train_x)[np.arange(len(train)),data.target[train]],1e-12,1))
            n=np.log(np.clip(component.predict_proba(test_x)[np.arange(len(test)),data.target[test]],1e-12,1))
            member_scores.append(m);nonmember_scores.append(n)
            attacks.append({"interface":name,"membership":threshold_probe(m,n,3407)})
        attacks.append({"interface":"joint_component_max_confidence","membership":threshold_probe(np.max(member_scores,axis=0),np.max(nonmember_scores,axis=0),3407)})
        workflow.write_json(output/"joint-access-privacy.json",{"tests":attacks,"component_hashes":[c["sha256"] for c in comparisons],
            "scope":"predefined maximum true-label confidence from both components; separate calibration/audit split; not exhaustive joint access","can_clear":False})
    related=[]
    for name in ("derivative-privacy-comparison.json","joint-access-privacy.json","image-tests.json"):
        if (output/name).is_file(): related.append({"path":name,"sha256":workflow.digest(output/name)})
    red_team["related_reports"]=related
    if preset in {"ensemble","mlp-finetuned"}:
        red_team["coverage_gaps"]=[g for g in red_team["coverage_gaps"] if 'Fine-tuned/base' not in g]
        red_team["coverage_gaps"].append("Related derivative/component comparisons are limited predefined attacks, not complete joint-access analysis")
    workflow.write_json(output/"red-team-report.json",red_team)
    if workflow.digest(candidate)!=artifact_hash: raise ValueError("candidate changed during tests")
    result={"demo":"multi-model-public-training","preset":preset,"training_executed":True,"training":{"utility":utility,"warnings":warnings_seen},
            "dataset":{"name":DATASETS[dataset],"rows":len(data.target),"features":data.data.shape[1]},"red_team":red_team,
            "component_comparisons":comparisons,"implementation_sha256":workflow.digest(Path(__file__)),"verdict":assessment.overall_verdict.value,"assessment_eligible":True,
            "authorization_eligible":False,"authorized":False,"deployed":False,"warnings":warnings_seen+utility_warnings,
            "limitations":["One registered membership assessment; other red-team tools remain exploratory","Digits use 8x8 public samples; CNN preset learns convolutional kernels, other presets use flattened pixels","Component accuracy comparisons do not establish joint-access privacy"]}
    workflow.write_json(output/"result.json",result)
    return result

if __name__=="__main__":
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument("--preset",required=True,choices=[x for x in PRESETS if x!="xgboost-small"])
    parser.add_argument("--dataset",required=True,choices=DATASETS)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    run_public(args.preset,args.dataset,args.output.resolve())
