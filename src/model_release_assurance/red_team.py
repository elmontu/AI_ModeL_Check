from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field

from .analyzers.attack import clopper_pearson_lower, clopper_pearson_upper
from .models import StrictModel


SACRO_ML_REFERENCE = {
    "project": "SACRO-ML",
    "repository": "https://github.com/AI-SDC/SACRO-ML",
    "reviewed_commit": "a94060ce85df52ac4b32d0b134f7afaa81af670d",
    "license": "MIT",
    "adaptation": (
        "independent implementation inspired by the Target, attack registry, repeated worst-case "
        "membership, dummy baseline, structural indicator, and standardized report patterns"
    ),
}


class RedTeamConfig(StrictModel):
    seed: int = Field(ge=0)
    membership_repetitions: int = Field(default=5, ge=2, le=20)
    attack_test_fraction: float = Field(default=0.3, gt=0.15, lt=0.5)
    probability_round_decimals: int = Field(default=6, ge=2, le=12)
    minimum_equivalence_class_size: int = Field(default=5, ge=2, le=100)
    minimum_residual_degrees_of_freedom: int = Field(default=10, ge=1)
    complexity_parameter_ratio: float = Field(default=1.0, gt=0.0)
    low_fpr_target: float = Field(default=0.01, gt=0.0, lt=0.5)
    confidence: float = Field(default=0.95, gt=0.5, lt=1.0)


@dataclass(frozen=True)
class RedTeamTarget:
    target_id: str
    model_kind: str
    model: Any
    train_x: Any
    train_y: Any
    test_x: Any
    test_y: Any


class RedTeamTool(Protocol):
    name: str
    service_id: str
    mcp_tool: str

    def run(self, target: RedTeamTarget, config: RedTeamConfig) -> dict[str, Any]: ...


def _losses(model: Any, features: Any, labels: Any) -> Any:
    import numpy as np

    probabilities = np.asarray(model.predict_proba(features))
    row = np.arange(len(labels))
    chosen = np.clip(probabilities[row, np.asarray(labels, dtype=int)], 1e-12, 1.0)
    return -np.log(chosen)


def _parameter_count(target: RedTeamTarget) -> int:
    import numpy as np

    model = target.model
    if target.model_kind == "xgboost":
        frame = model.get_booster().trees_to_dataframe()
        if frame.empty:
            return 0
        leaves = int((frame["Feature"] == "Leaf").sum())
        internal = int(len(frame) - leaves)
        trees = int(frame["Tree"].max()) + 1
        classes = int(getattr(model, "n_classes_", 2))
        return 2 * internal + (classes - 1) * leaves + trees
    estimator = model.steps[-1][1] if hasattr(model, "steps") else model
    if hasattr(estimator, "coefs_") and hasattr(estimator, "intercepts_"):
        return int(sum(np.size(item) for item in estimator.coefs_) + sum(
            np.size(item) for item in estimator.intercepts_
        ))
    return 0


class StructuralDisclosureTool:
    name = "structural_disclosure"
    service_id = "mra.red-team.structural-disclosure"
    mcp_tool = "red_team_structural_disclosure"

    def run(self, target: RedTeamTarget, config: RedTeamConfig) -> dict[str, Any]:
        import numpy as np
        from scipy.stats import ks_2samp

        train_predictions = np.asarray(target.model.predict(target.train_x))
        test_predictions = np.asarray(target.model.predict(target.test_x))
        train_accuracy = float(np.mean(train_predictions == target.train_y))
        test_accuracy = float(np.mean(test_predictions == target.test_y))
        train_losses = _losses(target.model, target.train_x, target.train_y)
        test_losses = _losses(target.model, target.test_x, target.test_y)
        ks = ks_2samp(train_losses, test_losses)
        parameters = _parameter_count(target)
        residual_dof = int(len(target.train_y) - parameters)

        rounded = np.round(
            np.asarray(target.model.predict_proba(target.train_x)),
            decimals=config.probability_round_decimals,
        )
        equivalence_probabilities, inverse, counts = np.unique(
            rounded, axis=0, return_inverse=True, return_counts=True
        )
        small_mask = counts < config.minimum_equivalence_class_size
        small_records = int(np.sum(small_mask[inverse]))
        observed_single_label_groups = 0
        for group_index in range(len(counts)):
            labels = np.unique(np.asarray(target.train_y)[inverse == group_index])
            if len(labels) == 1:
                observed_single_label_groups += 1
        zero_probability_mask = np.any(np.isclose(equivalence_probabilities, 0.0), axis=1)
        zero_probability_groups = int(np.sum(zero_probability_mask))
        estimated_label_counts = equivalence_probabilities * counts[:, np.newaxis]
        small_group_mask = np.any(
            (estimated_label_counts > 0)
            & (estimated_label_counts < config.minimum_equivalence_class_size),
            axis=1,
        )
        small_group_records = int(np.sum(small_group_mask[inverse]))

        return {
            "tool": self.name,
            "service_id": self.service_id,
            "mcp_tool": self.mcp_tool,
            "evidence_semantics": "structural_disclosure_screen_only",
            "method_notes": {
                "equivalence_class_definition": (
                    "identical training-set predict_proba vectors after decimal rounding"
                ),
                "probability_round_decimals": config.probability_round_decimals,
                "equivalence_class_limitation": (
                    "continuous probability outputs are commonly unique; results are highly "
                    "rounding-dependent and are not a calibrated k-anonymity or disclosure claim"
                ),
                "class_disclosure_definition": (
                    "an equivalence-class probability vector contains a value numerically close to zero"
                ),
                "small_group_definition": (
                    "an equivalence-class size multiplied by a nonzero predicted class probability "
                    "is below the configured class-size threshold"
                ),
                "parameter_count_limitation": (
                    "family-specific learned-parameter proxy; preprocessing state is excluded"
                ),
            },
            "metrics": {
                "train_accuracy": train_accuracy,
                "test_accuracy": test_accuracy,
                "generalization_gap": train_accuracy - test_accuracy,
                "loss_distribution_ks_statistic": float(ks.statistic),
                "loss_distribution_ks_pvalue": float(ks.pvalue),
                "learned_parameter_count": parameters,
                "residual_degrees_of_freedom": residual_dof,
                "parameter_to_training_record_ratio": parameters / len(target.train_y),
                "equivalence_class_count": int(len(counts)),
                "minimum_equivalence_class_size": int(counts.min()),
                "records_in_small_equivalence_classes": small_records,
                "zero_probability_equivalence_classes": zero_probability_groups,
                "records_in_probability_small_groups": small_group_records,
                "single_observed_label_equivalence_classes": observed_single_label_groups,
            },
            "flags": {
                "generalization_distribution_shift": bool(ks.pvalue < 0.05),
                "degrees_of_freedom_risk": residual_dof < config.minimum_residual_degrees_of_freedom,
                "complexity_risk": parameters / len(target.train_y) > config.complexity_parameter_ratio,
                "k_anonymity_screen": small_records > 0,
                "class_disclosure_screen": zero_probability_groups > 0,
                "small_group_screen": small_group_records > 0,
            },
            "record_level_output_retained": False,
            "can_clear": False,
            "can_block": False,
        }


class WorstCaseMembershipTool:
    name = "worst_case_membership"
    service_id = "mra.red-team.worst-case-membership"
    mcp_tool = "red_team_worst_case_membership"

    @staticmethod
    def _attack_features(target: RedTeamTarget) -> tuple[Any, Any]:
        import numpy as np

        train_probabilities = np.sort(
            np.asarray(target.model.predict_proba(target.train_x)), axis=1
        )[:, ::-1]
        test_probabilities = np.sort(
            np.asarray(target.model.predict_proba(target.test_x)), axis=1
        )[:, ::-1]
        features = np.vstack((train_probabilities, test_probabilities))
        membership = np.concatenate((
            np.ones(len(train_probabilities), dtype=int),
            np.zeros(len(test_probabilities), dtype=int),
        ))
        return features, membership

    def run(self, target: RedTeamTarget, config: RedTeamConfig) -> dict[str, Any]:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split

        features, membership = self._attack_features(target)
        bound_count = 2 * config.membership_repetitions
        confidence = 1.0 - (1.0 - config.confidence) / bound_count
        repetitions = []
        for repetition in range(config.membership_repetitions):
            attack_train_x, attack_test_x, attack_train_y, attack_test_y = train_test_split(
                features,
                membership,
                test_size=config.attack_test_fraction,
                stratify=membership,
                random_state=config.seed + repetition,
            )
            attack_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=5,
                min_samples_split=20,
                min_samples_leaf=10,
                n_jobs=1,
                random_state=config.seed + 10_000 + repetition,
            )
            attack_model.fit(attack_train_x, attack_train_y)
            train_scores = np.asarray(attack_model.predict_proba(attack_train_x))[:, 1]
            test_scores = np.asarray(attack_model.predict_proba(attack_test_x))[:, 1]
            train_nonmember = train_scores[attack_train_y == 0]
            threshold = float(np.quantile(train_nonmember, 1.0 - config.low_fpr_target, method="higher"))
            test_member = attack_test_y == 1
            test_nonmember = attack_test_y == 0
            member_successes = int(np.sum(test_scores[test_member] >= threshold))
            member_trials = int(np.sum(test_member))
            false_positives = int(np.sum(test_scores[test_nonmember] >= threshold))
            nonmember_trials = int(np.sum(test_nonmember))
            tpr = member_successes / member_trials
            fpr = false_positives / nonmember_trials
            tpr_lower = clopper_pearson_lower(member_successes, member_trials, confidence)
            fpr_upper = clopper_pearson_upper(false_positives, nonmember_trials, confidence)

            random = np.random.default_rng(config.seed + 20_000 + repetition)
            dummy_train_y = random.permutation(attack_train_y)
            dummy = RandomForestClassifier(
                n_estimators=100,
                max_depth=5,
                min_samples_split=20,
                min_samples_leaf=10,
                n_jobs=1,
                random_state=config.seed + 30_000 + repetition,
            ).fit(attack_train_x, dummy_train_y)
            dummy_auc = float(roc_auc_score(
                attack_test_y, np.asarray(dummy.predict_proba(attack_test_x))[:, 1]
            ))
            repetitions.append({
                "repetition": repetition,
                "auc": float(roc_auc_score(attack_test_y, test_scores)),
                "dummy_auc": dummy_auc,
                "threshold_calibrated_on_attack_train_nonmembers": threshold,
                "target_fpr": config.low_fpr_target,
                "member_successes": member_successes,
                "member_trials": member_trials,
                "false_positives": false_positives,
                "nonmember_trials": nonmember_trials,
                "tpr": tpr,
                "fpr": fpr,
                "simultaneous_tpr_lower": tpr_lower,
                "simultaneous_fpr_upper": fpr_upper,
                "operating_point_attained": fpr_upper <= config.low_fpr_target,
            })
        valid_lowers = [
            item["simultaneous_tpr_lower"]
            for item in repetitions
            if item["operating_point_attained"]
        ]
        return {
            "tool": self.name,
            "service_id": self.service_id,
            "mcp_tool": self.mcp_tool,
            "evidence_semantics": "worst_case_membership_screen_or_floor_never_clear",
            "threat_model": (
                "worst-case diagnostic attacker receives target train/test probability outputs; "
                "this overestimates many deployment attackers"
            ),
            "repetitions": repetitions,
            "summary": {
                "maximum_auc": max(item["auc"] for item in repetitions),
                "maximum_dummy_auc": max(item["dummy_auc"] for item in repetitions),
                "maximum_valid_low_fpr_tpr_lower": max(valid_lowers) if valid_lowers else None,
                "valid_operating_point_repetitions": len(valid_lowers),
            },
            "record_level_output_retained": False,
            "can_clear": False,
            "can_block": False,
            "potentially_blocking_when_bound_to_assessment": bool(valid_lowers),
        }


class RedTeamToolRegistry:
    def __init__(self, tools: tuple[RedTeamTool, ...]):
        names = [tool.name for tool in tools]
        if not tools or len(names) != len(set(names)):
            raise ValueError("red-team tools must be non-empty with unique names")
        self.tools = tools

    def run(self, target: RedTeamTarget, config: RedTeamConfig) -> dict[str, Any]:
        reports = [tool.run(target, config) for tool in self.tools]
        if any(report.get("can_clear") is not False for report in reports):
            raise ValueError("red-team tool exceeded its non-clearing authority")
        return {
            "schema_version": "1.0",
            "suite": "mra_sacro_ml_inspired_red_team",
            "reference": SACRO_ML_REFERENCE,
            "target": {
                "target_id": target.target_id,
                "model_kind": target.model_kind,
                "train_records": len(target.train_y),
                "test_records": len(target.test_y),
            },
            "tools": reports,
            "decision": "no_release_authorization",
            "can_clear": False,
        }


def default_red_team_tool_registry() -> RedTeamToolRegistry:
    return RedTeamToolRegistry((StructuralDisclosureTool(), WorstCaseMembershipTool()))
