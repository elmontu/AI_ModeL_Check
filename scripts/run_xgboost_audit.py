#!/usr/bin/env python3
"""Train and audit local XGBoost classifiers outside the trusted MRA core."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow
import scipy
import sklearn
import xgboost
from sklearn.preprocessing import LabelEncoder


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_VERSION = 3
SPLIT_NAMES = (
    "target_train",
    "reference_train",
    "attack_calibration",
    "attack_audit_nonmember",
    "utility_test",
)
MODEL_DEFAULTS: dict[str, int | float] = {
    "n_estimators": 100,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_weight": 1.0,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "gamma": 0.0,
    "max_bin": 256,
}
CANONICAL_GAME_FIELDS: dict[str, Any] = {
    "protected_unit": "record",
    "attacker_observation": "class_probabilities_and_true_label",
    "true_label_known": True,
    "candidate_population": (
        "rows selected by deterministic row-cap stratified sampling from the hash-bound dataset"
    ),
    "candidate_sampling": (
        "target members, calibration nonmembers, and audit nonmembers from deterministic "
        "stratified disjoint five-way splits"
    ),
    "reference_data_relationship": (
        "disjoint same-dataset reference training split equalized in size with target training"
    ),
    "model_knowledge": "xgboost_family_and_registered_hyperparameters",
    "threshold_selection": "nonmember_calibration_only_fixed_target_fpr",
    "recipient_access": "full_artifact",
    "query_budget": None,
}

sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_membership import (  # noqa: E402
    equalized_target,
    one_sided_clopper_pearson,
    per_record_loss,
    save_scores,
    threshold_at_fpr,
)
from run_openml_structural import (  # noqa: E402
    _xgb_classifier,
    build_preprocessor,
    canonical_json,
    capped_indices,
    make_splits,
    sha256_bytes,
    sha256_file,
    signature_histogram,
    utility_metrics,
    write_json,
    write_json_gz,
)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _strict_keys(
    value: dict[str, Any],
    *,
    name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise ValueError(f"{name} is missing required fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {sorted(unknown)}")


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str, *, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        suffix = f" and <= {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be >= {minimum}{suffix}")
    return result


def normalize_model_config(model_config: dict[str, Any]) -> dict[str, int | float]:
    unknown = set(model_config) - set(MODEL_DEFAULTS)
    if unknown:
        raise ValueError(f"model contains unknown or controlled parameters: {sorted(unknown)}")
    merged = {**MODEL_DEFAULTS, **model_config}
    return {
        "n_estimators": _integer(merged["n_estimators"], "model.n_estimators", minimum=1),
        "max_depth": _integer(merged["max_depth"], "model.max_depth", minimum=1),
        "learning_rate": _number(merged["learning_rate"], "model.learning_rate", minimum=1e-12),
        "min_child_weight": _number(
            merged["min_child_weight"], "model.min_child_weight", minimum=0.0
        ),
        "subsample": _number(merged["subsample"], "model.subsample", minimum=1e-12, maximum=1.0),
        "colsample_bytree": _number(
            merged["colsample_bytree"],
            "model.colsample_bytree",
            minimum=1e-12,
            maximum=1.0,
        ),
        "reg_alpha": _number(merged["reg_alpha"], "model.reg_alpha", minimum=0.0),
        "reg_lambda": _number(merged["reg_lambda"], "model.reg_lambda", minimum=0.0),
        "gamma": _number(merged["gamma"], "model.gamma", minimum=0.0),
        "max_bin": _integer(merged["max_bin"], "model.max_bin", minimum=2),
    }


def xgboost_parameters(model_config: dict[str, Any], class_count: int, seed: int) -> dict[str, Any]:
    """Return strict, deterministic CPU parameters for an XGBClassifier."""

    parameters: dict[str, Any] = {
        **normalize_model_config(model_config),
        "tree_method": "hist",
        "device": "cpu",
        "random_state": int(seed),
        "n_jobs": 1,
        "verbosity": 0,
    }
    if class_count < 2:
        raise ValueError("classification requires at least two target classes")
    if class_count == 2:
        parameters.update(objective="binary:logistic", eval_metric="logloss")
    else:
        parameters.update(
            objective="multi:softprob",
            eval_metric="mlogloss",
            num_class=int(class_count),
        )
    return parameters


def simultaneous_bound_confidence(family_confidence: float, comparisons: int) -> float:
    """Bonferroni confidence for the TPR-lower/FPR-upper pair in each comparison."""

    if not 0.5 < family_confidence < 1.0:
        raise ValueError("family_confidence must be > 0.5 and < 1")
    if comparisons < 1:
        raise ValueError("comparisons must be at least one")
    return 1.0 - (1.0 - family_confidence) / (2.0 * comparisons)


def positive_predictive_value(
    tpr: float,
    fpr: float,
    membership_prior: float,
) -> float | None:
    """Return attack PPV under a declared deployment membership prior."""

    numerator = membership_prior * tpr
    denominator = numerator + (1.0 - membership_prior) * fpr
    return numerator / denominator if denominator > 0.0 else None


def zero_false_positive_minimum_trials(target_fpr: float, confidence: float) -> int:
    """Minimum nonmembers whose zero-FP upper bound can attain ``target_fpr``."""

    return int(math.ceil(math.log1p(-confidence) / math.log1p(-target_fpr)))


def validate_config(value: Any) -> dict[str, Any]:
    config = _mapping(value, "configuration")
    _strict_keys(
        config,
        name="configuration",
        required={
            "schema_version",
            "experiment_id",
            "dataset",
            "master_seed",
            "replicate_seeds",
            "row_cap",
            "split_fractions",
            "model",
            "attack",
            "decision_game",
        },
    )
    if config["schema_version"] != "1.1":
        raise ValueError("configuration.schema_version must be '1.1'")
    if not isinstance(config["experiment_id"], str) or not config["experiment_id"].strip():
        raise ValueError("configuration.experiment_id must be a non-empty string")

    dataset = _mapping(config["dataset"], "dataset")
    _strict_keys(dataset, name="dataset", required={"path", "sha256", "target_column"})
    if not isinstance(dataset["path"], str) or not dataset["path"].strip():
        raise ValueError("dataset.path must be a non-empty string")
    if (
        not isinstance(dataset["sha256"], str)
        or len(dataset["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in dataset["sha256"])
    ):
        raise ValueError("dataset.sha256 must be a lowercase SHA-256 digest")
    if not isinstance(dataset["target_column"], str) or not dataset["target_column"].strip():
        raise ValueError("dataset.target_column must be a non-empty string")

    _integer(config["master_seed"], "configuration.master_seed", minimum=0)
    seeds = config["replicate_seeds"]
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("configuration.replicate_seeds must be a non-empty array")
    parsed_seeds = [
        _integer(seed, f"configuration.replicate_seeds[{index}]", minimum=0)
        for index, seed in enumerate(seeds)
    ]
    if len(parsed_seeds) != len(set(parsed_seeds)):
        raise ValueError("configuration.replicate_seeds must be unique")
    _integer(config["row_cap"], "configuration.row_cap", minimum=100)

    fractions = _mapping(config["split_fractions"], "split_fractions")
    _strict_keys(fractions, name="split_fractions", required=set(SPLIT_NAMES))
    parsed_fractions = {
        name: _number(fractions[name], f"split_fractions.{name}", minimum=1e-12, maximum=1.0)
        for name in SPLIT_NAMES
    }
    if abs(sum(parsed_fractions.values()) - 1.0) > 1e-12:
        raise ValueError("split_fractions must sum to one")
    if parsed_fractions["target_train"] < parsed_fractions["reference_train"]:
        raise ValueError("target_train must be at least as large as reference_train")

    model = normalize_model_config(_mapping(config["model"], "model"))

    attack = _mapping(config["attack"], "attack")
    _strict_keys(
        attack,
        name="attack",
        required={"target_fpr", "confidence", "membership_priors"},
    )
    target_fpr = _number(attack["target_fpr"], "attack.target_fpr", minimum=1e-12)
    if target_fpr >= 1.0:
        raise ValueError("attack.target_fpr must be < 1")
    confidence = _number(attack["confidence"], "attack.confidence", minimum=0.5)
    if confidence <= 0.5 or confidence >= 1.0:
        raise ValueError("attack.confidence must be > 0.5 and < 1")
    priors = attack["membership_priors"]
    if not isinstance(priors, list) or not priors:
        raise ValueError("attack.membership_priors must be a non-empty array")
    parsed_priors = [
        _number(prior, f"attack.membership_priors[{index}]", minimum=0.0, maximum=1.0)
        for index, prior in enumerate(priors)
    ]
    if any(prior <= 0.0 or prior >= 1.0 for prior in parsed_priors):
        raise ValueError("attack.membership_priors values must be strictly between zero and one")
    if len(parsed_priors) != len(set(parsed_priors)):
        raise ValueError("attack.membership_priors values must be unique")

    decision_game = _mapping(config["decision_game"], "decision_game")
    _strict_keys(
        decision_game,
        name="decision_game",
        required={
            "game_id",
            "threat_contract_sha256",
            "population_scope_id",
            "protected_unit",
            "attacker_observation",
            "true_label_known",
            "candidate_population",
            "candidate_sampling",
            "reference_data_relationship",
            "model_knowledge",
            "threshold_selection",
            "recipient_access",
            "query_budget",
        },
    )
    for field in (
        "game_id",
        "population_scope_id",
        "candidate_population",
        "candidate_sampling",
        "reference_data_relationship",
    ):
        if not isinstance(decision_game[field], str) or not decision_game[field].strip():
            raise ValueError(f"decision_game.{field} must be a non-empty string")
    threat_digest = decision_game["threat_contract_sha256"]
    if (
        not isinstance(threat_digest, str)
        or len(threat_digest) != 64
        or any(character not in "0123456789abcdef" for character in threat_digest)
    ):
        raise ValueError("decision_game.threat_contract_sha256 must be a lowercase SHA-256 digest")
    if threat_digest == "0" * 64:
        raise ValueError("decision_game.threat_contract_sha256 must not be the placeholder digest")
    for field in ("game_id", "population_scope_id"):
        if decision_game[field].strip().lower().startswith("replace-"):
            raise ValueError(f"decision_game.{field} must not be a replace-* placeholder")
    for field, expected in CANONICAL_GAME_FIELDS.items():
        if decision_game[field] != expected:
            raise ValueError(f"decision_game.{field} must be {expected!r}")
    return {
        **config,
        "dataset": dict(dataset),
        "master_seed": int(config["master_seed"]),
        "replicate_seeds": parsed_seeds,
        "row_cap": int(config["row_cap"]),
        "split_fractions": {
            name: parsed_fractions[name]
            for name in SPLIT_NAMES
        },
        "model": model,
        "attack": {
            "target_fpr": target_fpr,
            "confidence": confidence,
            "membership_priors": parsed_priors,
        },
        "decision_game": dict(decision_game),
    }


def load_config(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"configuration is not valid UTF-8 JSON: {path}") from error
    return validate_config(parsed)


def xgboost_build_binding() -> dict[str, Any]:
    """Return build metadata without exposing a machine-specific library path."""
    build = dict(xgboost.build_info())
    raw_library_path = build.pop("libxgboost", None)
    if raw_library_path is None:
        raise RuntimeError("XGBoost did not report the runtime library required for hash binding")
    library_path = Path(str(raw_library_path))
    if not library_path.is_file():
        raise RuntimeError("XGBoost reported a runtime library that cannot be hash-bound")
    build["libxgboost"] = {
        "name": library_path.name,
        "sha256": sha256_file(library_path),
        "binding_status": "complete",
    }
    return build


def runtime_versions() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyarrow": pyarrow.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "xgboost_build": xgboost_build_binding(),
        "joblib": joblib.__version__,
    }


def implementation_binding() -> dict[str, Any]:
    paths = (
        Path(__file__).resolve(),
        ROOT / "scripts" / "run_openml_structural.py",
        ROOT / "scripts" / "run_openml_membership.py",
    )
    files = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha256_file(path)
        for path in paths
    }
    return {
        "version": IMPLEMENTATION_VERSION,
        "files": files,
        "sha256": sha256_bytes(canonical_json(files)),
    }


def resolve_dataset_path(config_path: Path, config: dict[str, Any]) -> Path:
    candidate = Path(config["dataset"]["path"])
    resolved = candidate if candidate.is_absolute() else config_path.resolve().parent / candidate
    resolved = resolved.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"dataset is not a regular file: {resolved}")
    return resolved


def load_dataset(path: Path, target_column: str) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    else:
        raise ValueError("dataset must be CSV (.csv) or Parquet (.parquet/.pq)")
    if frame.empty:
        raise ValueError("dataset is empty")
    names = [str(column) for column in frame.columns]
    if len(names) != len(set(names)):
        raise ValueError("dataset column names are not unique after string normalization")
    frame = frame.copy()
    frame.columns = names
    if target_column not in frame:
        raise ValueError(f"target column is absent: {target_column}")
    if len(frame.columns) < 2:
        raise ValueError("dataset must contain at least one feature column")
    if frame[target_column].isna().any():
        raise ValueError("target column contains missing values")
    return frame


def local_row_ids(dataset_sha256: str, row_count: int) -> np.ndarray:
    return np.asarray(
        [
            hashlib.sha256(
                f"local-xgboost:{dataset_sha256}:{index}".encode("utf-8")
            ).hexdigest()
            for index in range(row_count)
        ]
    )


def artifact_record(path: Path, run_dir: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(run_dir)).replace("\\", "/"),
        "sha256": sha256_file(path),
    }


def _score_quantiles(values: np.ndarray) -> dict[str, float]:
    probabilities = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)
    quantiles = np.quantile(np.asarray(values, dtype=float), probabilities)
    return {
        f"q{int(probability * 100):02d}": float(value)
        for probability, value in zip(probabilities, quantiles, strict=True)
    }


def evaluate_membership_scores(
    score_frame: pd.DataFrame,
    *,
    target_fpr: float,
    confidence_family: float,
    registered_comparisons: int,
    membership_priors: list[float],
) -> dict[str, Any]:
    """Evaluate the preregistered reference-loss screen from retained raw scores."""

    required_columns = {
        "group",
        "membership_score",
        "target_loss",
        "reference_loss",
        "true_class",
        "is_member",
    }
    if not required_columns.issubset(score_frame.columns):
        raise ValueError("raw membership scores are missing required columns")
    expected_groups = {"member_audit", "nonmember_calibration", "nonmember_audit"}
    groups = set(score_frame["group"].astype(str))
    if groups != expected_groups:
        raise ValueError(f"raw membership score groups differ from the registered design: {sorted(groups)}")
    numeric_columns = ("membership_score", "target_loss", "reference_loss", "true_class")
    numeric_values: dict[str, np.ndarray] = {}
    for column in numeric_columns:
        try:
            values = pd.to_numeric(score_frame[column], errors="raise").to_numpy(dtype=float)
        except (TypeError, ValueError) as error:
            raise ValueError(f"raw membership score column {column!r} must be numeric") from error
        if not np.all(np.isfinite(values)):
            raise ValueError(f"raw membership score column {column!r} must contain finite values")
        numeric_values[column] = values
    classes = numeric_values["true_class"]
    if np.any(classes < 0.0) or not np.all(classes == np.floor(classes)):
        raise ValueError("raw membership score true_class values must be nonnegative integers")
    if not pd.api.types.is_bool_dtype(score_frame["is_member"].dtype):
        raise ValueError("raw membership score is_member values must be boolean")
    expected_membership = score_frame["group"].astype(str).eq("member_audit").to_numpy()
    if not np.array_equal(score_frame["is_member"].to_numpy(dtype=bool), expected_membership):
        raise ValueError("raw membership score is_member values disagree with group labels")
    if not np.allclose(
        numeric_values["membership_score"],
        numeric_values["reference_loss"] - numeric_values["target_loss"],
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("raw membership scores disagree with reference_loss - target_loss")
    scores = {
        group: score_frame.loc[score_frame["group"] == group, "membership_score"].to_numpy(
            dtype=float
        )
        for group in sorted(expected_groups)
    }
    if any(len(values) == 0 for values in scores.values()):
        raise ValueError("raw membership score groups must be non-empty")

    per_bound_confidence = simultaneous_bound_confidence(
        confidence_family,
        registered_comparisons,
    )
    threshold, calibration_fp = threshold_at_fpr(
        scores["nonmember_calibration"], target_fpr
    )
    tp = int(np.sum(scores["member_audit"] >= threshold))
    fn = int(len(scores["member_audit"]) - tp)
    fp = int(np.sum(scores["nonmember_audit"] >= threshold))
    tn = int(len(scores["nonmember_audit"]) - fp)
    tpr_interval = one_sided_clopper_pearson(tp, tp + fn, per_bound_confidence)
    fpr_interval = one_sided_clopper_pearson(fp, fp + tn, per_bound_confidence)
    operating_point_attained = fpr_interval[1] <= target_fpr
    tpr = tp / (tp + fn)
    fpr = fp / (fp + tn)
    prior_ppv = []
    for prior in membership_priors:
        estimate = positive_predictive_value(tpr, fpr, prior)
        lower_bound = positive_predictive_value(
            tpr_interval[0],
            fpr_interval[1],
            prior,
        )
        prior_ppv.append(
            {
                "membership_prior": prior,
                "estimate": estimate,
                "estimate_status": (
                    "defined" if estimate is not None else "undefined_no_positive_predictions"
                ),
                "simultaneous_lower_bound": lower_bound,
            }
        )
    minimum_zero_fp_nonmembers = zero_false_positive_minimum_trials(
        target_fpr,
        per_bound_confidence,
    )

    class_summaries: dict[str, dict[str, float | int]] = {}
    audit_rows = score_frame[score_frame["group"].isin(("member_audit", "nonmember_audit"))]
    for class_value in sorted(int(value) for value in audit_rows["true_class"].unique()):
        member_rows = audit_rows[
            (audit_rows["group"] == "member_audit")
            & (audit_rows["true_class"] == class_value)
        ]
        nonmember_rows = audit_rows[
            (audit_rows["group"] == "nonmember_audit")
            & (audit_rows["true_class"] == class_value)
        ]
        class_tp = int(np.sum(member_rows["membership_score"].to_numpy() >= threshold))
        class_fp = int(np.sum(nonmember_rows["membership_score"].to_numpy() >= threshold))
        class_summaries[str(class_value)] = {
            "member_trials": int(len(member_rows)),
            "nonmember_trials": int(len(nonmember_rows)),
            "true_positives": class_tp,
            "false_positives": class_fp,
            "tpr_descriptive": class_tp / len(member_rows) if len(member_rows) else 0.0,
            "fpr_descriptive": class_fp / len(nonmember_rows) if len(nonmember_rows) else 0.0,
        }

    return {
        "attack_name": "single-reference loss-difference membership screen",
        "score": "reference cross-entropy loss minus target cross-entropy loss",
        "member_rule": "membership_score >= threshold",
        "target_fpr": target_fpr,
        "threshold": threshold,
        "calibration_false_positives": calibration_fp,
        "calibration_nonmembers": len(scores["nonmember_calibration"]),
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "tpr": tpr,
        "fpr": fpr,
        "tpr_clopper_pearson_one_sided": list(tpr_interval),
        "fpr_clopper_pearson_one_sided": list(fpr_interval),
        "confidence_family": confidence_family,
        "per_bound_confidence": per_bound_confidence,
        "multiplicity": {
            "procedure": "bonferroni_one_sided",
            "registered_replicate_comparisons": registered_comparisons,
            "bounds_per_comparison": 2,
            "simultaneous_bound_count": 2 * registered_comparisons,
            "family_definition": "TPR-lower and FPR-upper bounds for every registered replicate seed",
        },
        "tail_claim_support": {
            "audit_nonmember_trials": fp + tn,
            "minimum_nonmember_trials_if_zero_false_positives": minimum_zero_fp_nonmembers,
            "zero_false_positive_sample_size_adequate": fp + tn >= minimum_zero_fp_nonmembers,
            "unsupported_tail_policy": "screen_no_floor",
        },
        "deployment_prior_ppv": prior_ppv,
        "descriptive_score_quantiles": {
            group: _score_quantiles(values) for group, values in scores.items()
        },
        "descriptive_class_operating_points": class_summaries,
        "descriptive_warning": "class and score summaries are noninferential and cannot block or clear",
        "operating_point_attained": operating_point_attained,
        "certified_tpr_floor_at_controlled_fpr": (
            tpr_interval[0] if operating_point_attained else None
        ),
        "simultaneous_membership_advantage_lower_bound": max(
            0.0,
            tpr_interval[0] - fpr_interval[1],
        ),
        "evidence_class": "floor" if operating_point_attained else "screen",
        "can_clear": False,
    }


def write_release_bundle(
    path: Path,
    *,
    release_manifest_path: Path,
    model_path: Path,
    preprocessing_path: Path,
) -> None:
    """Write a byte-stable release artifact containing the complete target pipeline."""

    members = (
        ("release-artifact.json", release_manifest_path),
        ("target-model.ubj", model_path),
        ("target-preprocessing.joblib", preprocessing_path),
    )
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for member_name, source in members:
            info = zipfile.ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())


def _cached_manifest(
    manifest_path: Path,
    *,
    expected: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if any(manifest.get(field) != value for field, value in expected.items()):
        return None
    run_dir = manifest_path.parent.resolve()
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return None
    for record in artifacts.values():
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            return None
        candidate = (run_dir / record["path"]).resolve()
        if not candidate.is_relative_to(run_dir) or not candidate.is_file():
            return None
        if sha256_file(candidate) != record["sha256"]:
            return None
    try:
        evidence_record = artifacts["audit_evidence"]
        evidence_path = (run_dir / evidence_record["path"]).resolve()
        retained_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        protected_fields = (
            "experiment",
            "protected_unit",
            "selected_rows",
            "class_counts",
            "group_counts",
            "utility_rows",
            "model_family",
            "target_model_parameters",
            "reference_model_parameters",
            "preprocessing_fit",
            "utility",
            "target_structural",
            "reference_structural",
            "attack",
            "decision_game",
            "release_binding",
        )
        if any(manifest.get(field) != retained_evidence.get(field) for field in protected_fields):
            return None
        score_record = artifacts["raw_scores"]
        score_path = (run_dir / score_record["path"]).resolve()
        score_frame = pd.read_parquet(score_path)
        recomputed_attack = evaluate_membership_scores(
            score_frame,
            target_fpr=float(config["attack"]["target_fpr"]),
            confidence_family=float(config["attack"]["confidence"]),
            registered_comparisons=len(config["replicate_seeds"]),
            membership_priors=list(config["attack"]["membership_priors"]),
        )
        if manifest.get("attack") != recomputed_attack:
            return None
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return None
    return manifest


def run_one(
    *,
    frame: pd.DataFrame,
    dataset_path: Path,
    dataset_sha256: str,
    config: dict[str, Any],
    config_sha256: str,
    output_dir: Path,
    seed: int,
    force: bool,
) -> tuple[dict[str, Any], Path]:
    run_dir = output_dir / f"seed-{seed}"
    manifest_path = run_dir / "run-manifest.json"
    implementation = implementation_binding()
    runtime = runtime_versions()
    expected_cache = {
        "status": "complete",
        "implementation": implementation,
        "runtime": runtime,
        "config_sha256": config_sha256,
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha256,
        "seed": seed,
    }
    if not force:
        cached = _cached_manifest(manifest_path, expected=expected_cache, config=config)
        if cached is not None:
            return cached, manifest_path

    started = time.monotonic()
    target_name = config["dataset"]["target_column"]
    features = frame.drop(columns=[target_name])
    label_encoder = LabelEncoder()
    target = label_encoder.fit_transform(frame[target_name].astype("string"))
    identities = local_row_ids(dataset_sha256, len(frame))
    selected = capped_indices(target, int(config["row_cap"]), int(config["master_seed"]))
    features = features.iloc[selected].reset_index(drop=True)
    target = target[selected]
    identities = identities[selected]
    class_counts = np.bincount(target)
    if len(class_counts) < 2:
        raise ValueError("classification requires at least two target classes")
    if int(class_counts.min()) < 10:
        raise ValueError("each target class needs at least 10 selected rows for the five-way audit split")

    splits = make_splits(target, seed, config["split_fractions"])
    target_indices = equalized_target(
        splits["target_train"],
        target,
        len(splits["reference_train"]),
        seed + 100,
    )
    reference_indices = splits["reference_train"]
    member_audit = target_indices
    nonmember_calibration = splits["attack_calibration"]
    nonmember_audit = splits["attack_audit_nonmember"]
    utility_indices = splits["utility_test"]

    target_preprocessor, numeric, categorical = build_preprocessor(features)
    reference_preprocessor, reference_numeric, reference_categorical = build_preprocessor(features)
    if numeric != reference_numeric or categorical != reference_categorical:
        raise RuntimeError("target and reference preprocessing schemas differ")
    X_target = target_preprocessor.fit_transform(features.iloc[target_indices])
    X_reference = reference_preprocessor.fit_transform(features.iloc[reference_indices])
    parameters = xgboost_parameters(config["model"], len(label_encoder.classes_), seed)
    reference_parameters = {**parameters, "random_state": seed + 10_000}
    learner = _xgb_classifier()
    target_model = learner(**parameters).fit(X_target, target[target_indices])
    reference_model = learner(**reference_parameters).fit(
        X_reference,
        target[reference_indices],
    )

    target_histogram, target_structural = signature_histogram(target_model.apply(X_target))
    reference_histogram, reference_structural = signature_histogram(
        reference_model.apply(X_reference)
    )
    X_utility = target_preprocessor.transform(features.iloc[utility_indices])
    utility = utility_metrics(target_model, X_utility, target[utility_indices])

    groups = {
        "member_audit": member_audit,
        "nonmember_calibration": nonmember_calibration,
        "nonmember_audit": nonmember_audit,
    }
    raw_rows: list[dict[str, Any]] = []
    for group, indices in groups.items():
        X_target_view = target_preprocessor.transform(features.iloc[indices])
        X_reference_view = reference_preprocessor.transform(features.iloc[indices])
        y = target[indices]
        target_loss = per_record_loss(target_model, X_target_view, y)
        reference_loss = per_record_loss(reference_model, X_reference_view, y)
        score = reference_loss - target_loss
        raw_rows.extend(
            {
                "row_id": identities[index],
                "group": group,
                "is_member": group.startswith("member_"),
                "true_class": int(target[index]),
                "target_loss": float(target_item),
                "reference_loss": float(reference_item),
                "membership_score": float(score_item),
            }
            for index, target_item, reference_item, score_item in zip(
                indices,
                target_loss,
                reference_loss,
                score,
                strict=True,
            )
        )

    score_frame = pd.DataFrame(raw_rows)
    attack = evaluate_membership_scores(
        score_frame,
        target_fpr=float(config["attack"]["target_fpr"]),
        confidence_family=float(config["attack"]["confidence"]),
        registered_comparisons=len(config["replicate_seeds"]),
        membership_priors=list(config["attack"]["membership_priors"]),
    )

    run_dir.mkdir(parents=True, exist_ok=True)
    target_model_path = run_dir / "target-model.ubj"
    reference_model_path = run_dir / "reference-model.ubj"
    target_model.save_model(target_model_path)
    reference_model.save_model(reference_model_path)
    target_preprocessing_path = run_dir / "target-preprocessing.joblib"
    reference_preprocessing_path = run_dir / "reference-preprocessing.joblib"
    joblib.dump(
        {"preprocessor": target_preprocessor, "label_encoder": label_encoder},
        target_preprocessing_path,
        compress=3,
    )
    joblib.dump(
        {"preprocessor": reference_preprocessor, "label_encoder": label_encoder},
        reference_preprocessing_path,
        compress=3,
    )
    scores_path = run_dir / "raw-membership-scores.parquet"
    save_scores(scores_path, raw_rows)
    split_path = run_dir / "split-manifest.json.gz"
    write_json_gz(
        split_path,
        {
            "selected_row_ids": identities.tolist(),
            "splits": {name: identities[indices].tolist() for name, indices in splits.items()},
            "target_training_row_ids": identities[target_indices].tolist(),
            "reference_training_row_ids": identities[reference_indices].tolist(),
            "member_audit_row_ids": identities[member_audit].tolist(),
        },
    )
    target_histogram_path = run_dir / "target-leaf-signature-histogram.json.gz"
    reference_histogram_path = run_dir / "reference-leaf-signature-histogram.json.gz"
    write_json_gz(target_histogram_path, target_histogram)
    write_json_gz(reference_histogram_path, reference_histogram)

    target_model_record = artifact_record(target_model_path, run_dir)
    target_preprocessing_record = artifact_record(target_preprocessing_path, run_dir)
    release_manifest = {
        "schema_version": "mra-xgboost-release-artifact-1.0",
        "model_family": "xgboost.XGBClassifier",
        "model_format": "XGBoost UBJ",
        "model": target_model_record,
        "preprocessing_format": "joblib (trusted-worker use only)",
        "preprocessing": target_preprocessing_record,
        "features": {
            "numeric": numeric,
            "categorical": categorical,
            "transformed_feature_count": int(X_target.shape[1]),
        },
        "class_labels": label_encoder.classes_.tolist(),
        "public_metadata_policy": (
            "Training-data, experiment-configuration, implementation, and runtime fingerprints "
            "are retained in internal audit evidence and omitted from the recipient bundle."
        ),
        "trust_boundary": (
            "This inert manifest is packaged with the model and preprocessing in the release "
            "bundle. The trusted MRA core must not deserialize the bundle or joblib file."
        ),
    }
    release_manifest_path = run_dir / "release-artifact.json"
    write_json(release_manifest_path, release_manifest)
    release_bundle_path = run_dir / "release-bundle.zip"
    write_release_bundle(
        release_bundle_path,
        release_manifest_path=release_manifest_path,
        model_path=target_model_path,
        preprocessing_path=target_preprocessing_path,
    )
    release_bundle_record = artifact_record(release_bundle_path, run_dir)

    decision_game = dict(config["decision_game"])
    release_binding = {
        "release_artifact_sha256": release_bundle_record["sha256"],
        "target_model_sha256": target_model_record["sha256"],
        "decision_game_sha256": sha256_bytes(canonical_json(decision_game)),
        "threat_contract_sha256": decision_game["threat_contract_sha256"],
        "recipient_access": decision_game["recipient_access"],
        "tested_observation": decision_game["attacker_observation"],
        "interface_binding_status": (
            "probability-and-true-label screen realizable by a full-artifact recipient; "
            "white-box artifact internals are not tested"
        ),
        "decision_game_binding_status": (
            "worker game bound; authoritative MRA population and policy bindings still required"
        ),
    }
    class_count_summary = {
        str(label): int(count)
        for label, count in zip(label_encoder.classes_.tolist(), class_counts, strict=True)
    }
    group_count_summary = {name: int(len(indices)) for name, indices in groups.items()}
    provenance_evidence = {
        "experiment": config["experiment_id"],
        "protected_unit": "record",
        "selected_rows": int(len(selected)),
        "class_counts": class_count_summary,
        "group_counts": group_count_summary,
        "utility_rows": int(len(utility_indices)),
        "model_family": "xgboost.XGBClassifier",
        "target_model_parameters": parameters,
        "reference_model_parameters": reference_parameters,
        "preprocessing_fit": "independently fitted on each model's own training split",
    }
    audit_evidence = {
        **provenance_evidence,
        "utility": utility,
        "target_structural": target_structural,
        "reference_structural": reference_structural,
        "attack": attack,
        "decision_game": decision_game,
        "release_binding": release_binding,
    }
    audit_evidence_path = run_dir / "audit-evidence.json"
    write_json(audit_evidence_path, audit_evidence)

    artifacts = {
        "release_bundle": release_bundle_record,
        "release_manifest": artifact_record(release_manifest_path, run_dir),
        "target_model": target_model_record,
        "reference_model": artifact_record(reference_model_path, run_dir),
        "target_preprocessing": target_preprocessing_record,
        "reference_preprocessing": artifact_record(reference_preprocessing_path, run_dir),
        "raw_scores": artifact_record(scores_path, run_dir),
        "splits": artifact_record(split_path, run_dir),
        "target_histogram": artifact_record(target_histogram_path, run_dir),
        "reference_histogram": artifact_record(reference_histogram_path, run_dir),
        "audit_evidence": artifact_record(audit_evidence_path, run_dir),
    }
    manifest = {
        "status": "complete",
        "implementation": implementation,
        "runtime": runtime,
        "config_sha256": config_sha256,
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha256,
        "seed": seed,
        **provenance_evidence,
        "target_structural": target_structural,
        "reference_structural": reference_structural,
        "utility": utility,
        "attack": attack,
        "decision_game": decision_game,
        "release_binding": release_binding,
        "artifacts": artifacts,
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(manifest_path, manifest)
    return manifest, manifest_path


def run_experiment(config_path: Path, output_dir: Path, *, force: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve(strict=True)
    config = load_config(config_path)
    config_sha256 = sha256_bytes(canonical_json(config))
    dataset_path = resolve_dataset_path(config_path, config)
    dataset_sha256 = sha256_file(dataset_path)
    expected_dataset_sha256 = config["dataset"]["sha256"]
    if dataset_sha256 != expected_dataset_sha256:
        raise ValueError(
            f"dataset hash mismatch: expected {expected_dataset_sha256}, got {dataset_sha256}"
        )
    frame = load_dataset(dataset_path, config["dataset"]["target_column"])
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for position, seed_value in enumerate(config["replicate_seeds"], start=1):
        seed = int(seed_value)
        print(
            f"[{position}/{len(config['replicate_seeds'])}] XGBoost audit seed {seed}",
            flush=True,
        )
        manifest, manifest_path = run_one(
            frame=frame,
            dataset_path=dataset_path,
            dataset_sha256=dataset_sha256,
            config=config,
            config_sha256=config_sha256,
            output_dir=output_dir,
            seed=seed,
            force=force,
        )
        records.append(
            {
                "seed": seed,
                "run_manifest": artifact_record(manifest_path, output_dir),
                "release_artifact": artifact_record(
                    manifest_path.parent / manifest["artifacts"]["release_bundle"]["path"],
                    output_dir,
                ),
                "utility": manifest["utility"],
                "attack": manifest["attack"],
            }
        )
    summary = {
        "status": "complete",
        "experiment": config["experiment_id"],
        "implementation": implementation_binding(),
        "runtime": runtime_versions(),
        "config_path": str(config_path),
        "config_sha256": config_sha256,
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha256,
        "decision_game_sha256": sha256_bytes(canonical_json(config["decision_game"])),
        "completed_runs": len(records),
        "multiplicity": {
            "procedure": "bonferroni_one_sided",
            "registered_replicate_comparisons": len(config["replicate_seeds"]),
            "simultaneous_bound_count": 2 * len(config["replicate_seeds"]),
            "aggregation_policy": "report_every_registered_seed_no_best_seed_selection",
        },
        "records": records,
        "interpretation": (
            "Attack results are screens or validated lower bounds and cannot clear a release. "
            "PPV is reported only for preregistered deployment membership priors. "
            "The release-artifact manifest binds the trained target model and preprocessing, but "
            "MRA interface, population, policy, and decision-game bindings remain required."
        ),
    }
    write_json(output_dir / "xgboost-audit-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train and audit a local CSV/Parquet XGBoost classifier"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        summary = run_experiment(args.config, args.output_dir, force=args.force)
    except Exception as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": summary["status"],
                "completed_runs": summary["completed_runs"],
                "summary": str((args.output_dir / "xgboost-audit-summary.json").resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
