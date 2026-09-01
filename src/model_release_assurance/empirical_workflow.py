from __future__ import annotations

import platform
from statistics import mean
from typing import Any, Literal

from pydantic import Field

from .analyzers.attack import clopper_pearson_lower, clopper_pearson_upper
from .integrity import canonical_json_bytes, sha256_bytes
from .models import StrictModel
from .red_team import (
    RedTeamConfig,
    RedTeamTarget,
    default_red_team_tool_registry,
)


class EmpiricalWorkflowConfig(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    workflow_id: str = Field(min_length=1, max_length=256)
    seed: int = Field(ge=0)
    replicates: int = Field(ge=2, le=10)
    samples_per_replicate: int = Field(ge=400, le=20_000)
    features: int = Field(ge=4, le=200)
    informative_features: int = Field(ge=2)
    redundant_features: int = Field(ge=0)
    test_fraction: float = Field(gt=0.1, lt=0.5)
    familywise_alpha: float = Field(gt=0.0, lt=0.2)
    xgboost_parameters: dict[str, int | float | str | bool]
    mlp_parameters: dict[str, int | float | str | bool | list[int]]


def empirical_dependencies_available() -> bool:
    try:
        import sklearn  # noqa: F401
        import xgboost  # noqa: F401
    except Exception:
        return False
    return True


def _versions() -> dict[str, str]:
    import numpy
    import sklearn
    import xgboost

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
    }


def _binary_losses(probabilities: Any, target: Any) -> Any:
    import numpy as np

    clipped = np.clip(np.asarray(probabilities), 1e-12, 1.0 - 1e-12)
    labels = np.asarray(target)
    return -(labels * np.log(clipped) + (1 - labels) * np.log1p(-clipped))


def _calibrate_membership_threshold(member_losses: Any, nonmember_losses: Any) -> tuple[float, float]:
    """Choose a loss threshold on a disjoint shadow model with pessimistic tie-breaking."""
    import numpy as np

    combined = np.unique(np.concatenate((member_losses, nonmember_losses)))
    candidates = np.concatenate((
        np.asarray([np.nextafter(combined[0], -np.inf)]),
        (combined[:-1] + combined[1:]) / 2.0,
        np.asarray([combined[-1]]),
    ))
    best_threshold = float(candidates[0])
    best_score = -1.0
    for threshold in candidates:
        tpr = float(np.mean(member_losses <= threshold))
        fpr = float(np.mean(nonmember_losses <= threshold))
        score = 0.5 * (tpr + 1.0 - fpr)
        if score > best_score + 1e-15 or (
            abs(score - best_score) <= 1e-15 and threshold < best_threshold
        ):
            best_score = score
            best_threshold = float(threshold)
    return best_threshold, best_score


def run_empirical_xgboost_mlp_workflow(config: EmpiricalWorkflowConfig) -> dict[str, Any]:
    try:
        import numpy as np
        from sklearn.datasets import make_classification
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score
        from sklearn.model_selection import train_test_split
        from sklearn.neural_network import MLPClassifier
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from xgboost import XGBClassifier
    except Exception as exc:
        raise RuntimeError(
            "empirical XGBoost/MLP workflow requires the experiments dependencies and a working OpenMP runtime"
        ) from exc

    if config.informative_features + config.redundant_features > config.features:
        raise ValueError("informative_features + redundant_features cannot exceed features")

    model_count = 2
    # Two accuracy bounds plus member-TPR and nonmember-FPR bounds for every model/replicate.
    interval_count = 4 * model_count * config.replicates
    per_interval_confidence = 1.0 - config.familywise_alpha / interval_count
    stages: list[dict[str, Any]] = [{
        "stage": "configuration_validation",
        "status": "completed",
        "config_sha256": sha256_bytes(canonical_json_bytes(config)),
    }]
    results: dict[str, list[dict[str, Any]]] = {"xgboost": [], "mlp": []}

    for replicate in range(config.replicates):
        replicate_seed = config.seed + replicate
        features, target = make_classification(
            n_samples=config.samples_per_replicate,
            n_features=config.features,
            n_informative=config.informative_features,
            n_redundant=config.redundant_features,
            n_classes=2,
            class_sep=1.25,
            flip_y=0.03,
            random_state=replicate_seed,
        )
        train_x, test_x, train_y, test_y = train_test_split(
            features,
            target,
            test_size=config.test_fraction,
            stratify=target,
            random_state=replicate_seed + 100_000,
        )
        reference_x, reference_y = make_classification(
            n_samples=config.samples_per_replicate,
            n_features=config.features,
            n_informative=config.informative_features,
            n_redundant=config.redundant_features,
            n_classes=2,
            class_sep=1.25,
            flip_y=0.03,
            random_state=replicate_seed + 1_000_000,
        )
        reference_train_x, reference_test_x, reference_train_y, reference_test_y = train_test_split(
            reference_x,
            reference_y,
            test_size=config.test_fraction,
            stratify=reference_y,
            random_state=replicate_seed + 1_100_000,
        )
        stages.append({
            "stage": "dataset_partition",
            "status": "completed",
            "replicate": replicate,
            "seed": replicate_seed,
            "train_samples": int(len(train_y)),
            "test_samples": int(len(test_y)),
            "reference_train_samples": int(len(reference_train_y)),
            "reference_test_samples": int(len(reference_test_y)),
            "overlap": 0,
        })

        def build_models(model_seed: int) -> dict[str, Any]:
            xgb_parameters = dict(config.xgboost_parameters)
            xgb_parameters.update({"random_state": model_seed, "n_jobs": 1})
            mlp_parameters = dict(config.mlp_parameters)
            hidden = mlp_parameters.get("hidden_layer_sizes")
            if isinstance(hidden, list):
                mlp_parameters["hidden_layer_sizes"] = tuple(hidden)
            mlp_parameters.update({"random_state": model_seed, "early_stopping": True})
            return {
                "xgboost": XGBClassifier(**xgb_parameters),
                "mlp": make_pipeline(StandardScaler(), MLPClassifier(**mlp_parameters)),
            }

        models = build_models(replicate_seed)
        reference_models = build_models(replicate_seed + 2_000_000)

        for model_name, model in models.items():
            model.fit(train_x, train_y)
            reference_model = reference_models[model_name]
            reference_model.fit(reference_train_x, reference_train_y)
            probabilities = np.asarray(model.predict_proba(test_x))[:, 1]
            predictions = (probabilities >= 0.5).astype(int)
            successes = int((predictions == test_y).sum())
            trials = int(len(test_y))
            accuracy = float(accuracy_score(test_y, predictions))
            record = {
                "replicate": replicate,
                "seed": replicate_seed,
                "train_samples": int(len(train_y)),
                "test_samples": trials,
                "correct": successes,
                "accuracy": accuracy,
                "balanced_accuracy": float(balanced_accuracy_score(test_y, predictions)),
                "roc_auc": float(roc_auc_score(test_y, probabilities)),
                "log_loss": float(log_loss(test_y, probabilities)),
                "accuracy_lower": clopper_pearson_lower(
                    successes, trials, per_interval_confidence
                ),
                "accuracy_upper": clopper_pearson_upper(
                    successes, trials, per_interval_confidence
                ),
                "can_clear": False,
                "evidence_semantics": "empirical_functional_screen_only",
            }
            reference_member_probabilities = np.asarray(
                reference_model.predict_proba(reference_train_x)
            )[:, 1]
            reference_nonmember_probabilities = np.asarray(
                reference_model.predict_proba(reference_test_x)
            )[:, 1]
            membership_threshold, calibration_score = _calibrate_membership_threshold(
                _binary_losses(reference_member_probabilities, reference_train_y),
                _binary_losses(reference_nonmember_probabilities, reference_test_y),
            )
            target_member_losses = _binary_losses(
                np.asarray(model.predict_proba(train_x))[:, 1], train_y
            )
            target_nonmember_losses = _binary_losses(probabilities, test_y)
            member_successes = int(np.sum(target_member_losses <= membership_threshold))
            nonmember_false_positives = int(
                np.sum(target_nonmember_losses <= membership_threshold)
            )
            member_trials = int(len(target_member_losses))
            nonmember_trials = int(len(target_nonmember_losses))
            member_tpr = member_successes / member_trials
            nonmember_fpr = nonmember_false_positives / nonmember_trials
            membership_success = 0.5 * (member_tpr + 1.0 - nonmember_fpr)
            member_lower = clopper_pearson_lower(
                member_successes, member_trials, per_interval_confidence
            )
            nonmember_fpr_upper = clopper_pearson_upper(
                nonmember_false_positives, nonmember_trials, per_interval_confidence
            )

            feature_scale = np.std(train_x, axis=0)
            random = np.random.default_rng(replicate_seed + 3_000_000)
            corrupted_x = test_x + random.normal(
                0.0, 0.25 * np.maximum(feature_scale, 1e-12), size=test_x.shape
            )
            corrupted_predictions = (
                np.asarray(model.predict_proba(corrupted_x))[:, 1] >= 0.5
            ).astype(int)
            gaussian_accuracy = float(accuracy_score(test_y, corrupted_predictions))
            occlusion_accuracies = []
            for feature_index in range(config.features):
                occluded_x = test_x.copy()
                occluded_x[:, feature_index] = 0.0
                occluded_predictions = (
                    np.asarray(model.predict_proba(occluded_x))[:, 1] >= 0.5
                ).astype(int)
                occlusion_accuracies.append(float(accuracy_score(test_y, occluded_predictions)))
            record["red_team"] = {
                "membership_attack": {
                    "attack": "disjoint_shadow_loss_threshold",
                    "threshold": membership_threshold,
                    "shadow_calibration_equal_prior_success": calibration_score,
                    "target_member_successes": member_successes,
                    "target_member_trials": member_trials,
                    "target_nonmember_false_positives": nonmember_false_positives,
                    "target_nonmember_trials": nonmember_trials,
                    "equal_prior_membership_success": membership_success,
                    "simultaneous_lower": 0.5 * (member_lower + 1.0 - nonmember_fpr_upper),
                    "calibration_and_target_disjoint": True,
                    "can_clear": False,
                    "can_block": False,
                    "potentially_blocking_when_bound_to_assessment": True,
                    "evidence_semantics": "empirical_attack_floor_requires_assessment_binding",
                },
                "feature_corruption": {
                    "gaussian_noise_scale_in_feature_standard_deviations": 0.25,
                    "gaussian_accuracy": gaussian_accuracy,
                    "gaussian_accuracy_drop": accuracy - gaussian_accuracy,
                    "worst_single_feature_occlusion_accuracy": min(occlusion_accuracies),
                    "worst_single_feature_occlusion_index": int(np.argmin(occlusion_accuracies)),
                    "worst_single_feature_occlusion_accuracy_drop": accuracy - min(occlusion_accuracies),
                    "can_clear": False,
                    "evidence_semantics": "recipient_realizable_robustness_screen_only",
                },
            }
            record["red_team"]["sacro_ml_inspired"] = default_red_team_tool_registry().run(
                RedTeamTarget(
                    target_id=f"{config.workflow_id}:{model_name}:{replicate}",
                    model_kind=model_name,
                    model=model,
                    train_x=train_x,
                    train_y=train_y,
                    test_x=test_x,
                    test_y=test_y,
                ),
                RedTeamConfig(
                    seed=replicate_seed + 4_000_000,
                    confidence=1.0 - config.familywise_alpha,
                ),
            )
            results[model_name].append(record)
            stages.append({
                "stage": "model_training_and_evaluation",
                "status": "completed",
                "replicate": replicate,
                "service_id": f"mra.model-worker.{model_name}",
                "mcp_tool": f"train_evaluate_{model_name}",
            })
            stages.append({
                "stage": "red_team_evaluation",
                "status": "completed",
                "replicate": replicate,
                "service_id": f"mra.red-team.{model_name}",
                "tests": [
                    "disjoint_shadow_membership", "gaussian_corruption", "feature_occlusion",
                    "sacro_inspired_structural_disclosure", "sacro_inspired_worst_case_membership",
                ],
            })

    models_report = []
    for model_name, records in results.items():
        models_report.append({
            "kind": model_name,
            "service_id": f"mra.model-worker.{model_name}",
            "service_version": "1.0",
            "transport": "in_process",
            "mcp_tool": f"train_evaluate_{model_name}",
            "replicates": records,
            "mean_accuracy": mean(item["accuracy"] for item in records),
            "minimum_simultaneous_accuracy_lower": min(item["accuracy_lower"] for item in records),
            "maximum_simultaneous_accuracy_upper": max(item["accuracy_upper"] for item in records),
            "mean_roc_auc": mean(item["roc_auc"] for item in records),
            "red_team": {
                "maximum_equal_prior_membership_success": max(
                    item["red_team"]["membership_attack"]["equal_prior_membership_success"]
                    for item in records
                ),
                "maximum_simultaneous_membership_lower": max(
                    item["red_team"]["membership_attack"]["simultaneous_lower"]
                    for item in records
                ),
                "maximum_gaussian_accuracy_drop": max(
                    item["red_team"]["feature_corruption"]["gaussian_accuracy_drop"]
                    for item in records
                ),
                "maximum_feature_occlusion_accuracy_drop": max(
                    item["red_team"]["feature_corruption"]["worst_single_feature_occlusion_accuracy_drop"]
                    for item in records
                ),
                "maximum_worst_case_membership_auc": max(
                    next(
                        tool for tool in item["red_team"]["sacro_ml_inspired"]["tools"]
                        if tool["tool"] == "worst_case_membership"
                    )["summary"]["maximum_auc"]
                    for item in records
                ),
                "structural_flags_observed": sorted({
                    flag
                    for item in records
                    for tool in item["red_team"]["sacro_ml_inspired"]["tools"]
                    if tool["tool"] == "structural_disclosure"
                    for flag, active in tool["flags"].items()
                    if active
                }),
            },
            "can_clear": False,
        })
    stages.append({
        "stage": "decision_aggregation",
        "status": "completed",
        "decision": "no_release_authorization",
    })
    return {
        "schema_version": "1.0",
        "workflow_id": config.workflow_id,
        "config_sha256": sha256_bytes(canonical_json_bytes(config)),
        "runtime": _versions(),
        "statistical_correction": {
            "method": "bonferroni",
            "familywise_alpha": config.familywise_alpha,
            "interval_count": interval_count,
            "per_interval_confidence": per_interval_confidence,
            "interval": "exact_one_sided_clopper_pearson",
        },
        "stages": stages,
        "models": models_report,
        "decision": "no_release_authorization",
        "limitations": [
            "synthetic classification data do not establish deployment utility or safety",
            "functional accuracy is screen-only and cannot clear a privacy or governance threat",
            "red-team floors require complete assessment bindings before they may block a release",
        ],
    }
