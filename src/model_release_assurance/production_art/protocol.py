"""Owned loss-oracle inputs and independent ART learner-score replay.

This interface supplies retained group-mean losses, not a stock target-model
wrapper or a deployed query endpoint. Constant zero regression labels prevent
ART's appended label feature from exposing extra target-label information.
Synthetic membership-conditioned controls validate the fitted attack learner
path, not a realistic target estimator or a public population privacy ceiling.
"""
from __future__ import annotations
import hashlib
import math
import re
from ..production_adapters import native
from ..production_adapters.contracts import (ClassificationUtility, RegressionUtility,
    MembershipMetrics, canonical_bytes, parse_candidate, parse_plan, strict_json)
from ..production_evidence.replay import artifact_manifest, replay_native_bundle
from ..production_registration.profiles import PROFILE_IDS, profile_descriptor
from ..production_sacro.protocol import membership_metrics, _owned as _json_owned

SEEDS = (20261006, 20261007, 20261008)
REPEATS = 3
TEST_FRACTION = .5
MAX_GROUPS = 4096
MIN_GROUPS_PER_CLASS = 20
MAX_PROTOCOL_BYTES = 16 * 1024 * 1024
MAX_LOSS = 1e30
SUPPORTED_PROFILES = tuple(PROFILE_IDS)
CASES = ("target", "positive", "null")
FLAGS = {**native.FLAGS, "assessment_eligible": False}
PROTOCOL = {"seeds": list(SEEDS), "test_fraction": TEST_FRACTION,
    "membership_threshold": .5, "threshold_comparison": "strict_greater",
    "metric_unit": "identical_feature_group", "attack_interface": "precomputed_group_mean_loss_oracle",
    "control_scope": "membership_conditioned_synthetic_loss_learner_path",
    "target_label_feature": "constant_zero_not_target_labels", "loss_cast": "art_float32",
    "repetitions_are_not_independent_samples": True}
_INPUT_KEYS = {"schema", "status", "profile_id", "task", "artifacts_sha256", "plan_sha256",
    "candidate_sha256", "source_sha256", "data_sha256", "row_count", "group_count",
    "member_group_count", "nonmember_group_count", "classes", "group_ids", "membership_labels",
    "cases", "native_full_run_metrics", "protocol", *FLAGS}
_REPETITION_KEYS = {"seed", "train_indices", "test_indices", "membership_labels",
    "member_probabilities", "learned", "loss_features_float32"}
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")

class ProtocolError(ValueError):
    """A bounded public-fixture loss or score binding was rejected."""

class UnsupportedProfile(ProtocolError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def _fail():
    raise ProtocolError("ART loss-oracle comparison rejected")

def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()

def _number(value, low=-MAX_LOSS, high=MAX_LOSS):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        _fail()
    return float(value)

def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail()
    return value

def owned(value):
    try:
        return _json_owned(value)
    except Exception:
        raise ProtocolError("ART loss-oracle comparison rejected") from None

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _profile(plan):
    for name in SUPPORTED_PROFILES:
        descriptor = profile_descriptor(name)
        dataset_id = ("research." + name + ".mixed-model-export-20260929-v1"
                      if descriptor["source_kind"] == "research_prepared" else name)
        if (plan.dataset_id == dataset_id and plan.source_sha256 == descriptor["expected_source_sha256"]
                and plan.task == descriptor["task"]):
            return name
    raise UnsupportedProfile("unregistered_profile")

def loss_features_float32(values):
    """Validate finite bounded losses both before and after ART's float32 cast."""
    import numpy as np
    if type(values) is not list or not 2 <= len(values) <= MAX_GROUPS:
        _fail()
    checked = [_number(value, 0., MAX_LOSS) for value in values]
    with np.errstate(over="raise", invalid="raise"):
        result = np.asarray(checked, dtype=np.float32)
    if not np.isfinite(result).all():
        _fail()
    return result.tolist()

def prepare_input(blobs):
    """Replay owned inert artifacts, preserving mean losses of conflicting groups.

    Members precede calibration and audit nonmembers in the frozen native plan
    order. No target fit or model deserialization occurs. Paired repetitions use
    the combined nonmember pool; original full native metrics remain distinct.
    """
    try:
        if type(blobs) is not dict:
            _fail()
        captured = dict(blobs)
        manifest = artifact_manifest(captured)
        replay_native_bundle(captured)
        plan = parse_plan(captured["plan.json"])
        profile_id = _profile(plan)
        candidate = parse_candidate(captured["candidate.json"])
        data = strict_json(captured["dataset.json"])
        x, y = native._arrays(data["x"], data["y"])
        predictions = native.replay_candidate(captured["candidate.json"], x)
        classes = list(candidate.model.classes) if plan.task == "classification" else []
        scores = native._row_scores(predictions, y, plan.task, classes)
        group_ids = list(plan.train_groups) + list(plan.calibration_groups) + list(plan.audit_groups)
        labels = [1] * len(plan.train_groups) + [0] * (len(plan.calibration_groups) + len(plan.audit_groups))
        import numpy as np
        grouped = []
        for group_id in group_ids:
            values = scores[plan.groups[group_id].rows]
            grouped.append(float(values[0]) if np.all(values == values[0]) else float(np.mean(values)))
        definition = ("mean_negative_log_true_class_probability_per_feature_group" if plan.task == "classification"
                      else "mean_squared_error_per_feature_group")
        cases = {"target": {"loss_values": [-value for value in grouped], "native_loss_scores": grouped,
                             "native_score_definition": definition}}
        for name in ("positive", "null"):
            losses = [0. if name == "positive" and label else 1. for label in labels]
            cases[name] = {"loss_values": losses, "native_loss_scores": [-value for value in losses],
                           "native_score_definition": "negative_synthetic_loss"}
        report = strict_json(captured["report.json"])
        result = {"schema": "mra-art-comparison-input/v1", "status": "prepared", "profile_id": profile_id,
            "task": plan.task, "artifacts_sha256": _sha(canonical_bytes(manifest)),
            "plan_sha256": _sha(captured["plan.json"]), "candidate_sha256": _sha(captured["candidate.json"]),
            "source_sha256": plan.source_sha256, "data_sha256": plan.data_sha256, "row_count": len(y),
            "group_count": len(group_ids), "member_group_count": sum(labels),
            "nonmember_group_count": len(labels) - sum(labels), "classes": classes, "group_ids": group_ids,
            "membership_labels": labels, "cases": cases,
            "native_full_run_metrics": {key: report[key] for key in ("utility", "membership", "positive_control", "null_control", "controls_passed")},
            "protocol": dict(PROTOCOL), **FLAGS}
        return validate_input(result)
    except UnsupportedProfile:
        raise
    except Exception:
        raise ProtocolError("ART loss-oracle comparison rejected") from None


def validate_input(prepared):
    """Check the exact owned contract; profile pins are not origin authentication."""
    try:
        _exact(prepared, _INPUT_KEYS)
        result = owned(prepared)
        if (result["schema"] != "mra-art-comparison-input/v1" or result["status"] != "prepared"
                or result["profile_id"] not in SUPPORTED_PROFILES
                or result["task"] != profile_descriptor(result["profile_id"])["task"]
                or canonical_bytes(result["protocol"]) != canonical_bytes(PROTOCOL)):
            _fail()
        for key, expected in FLAGS.items():
            if result[key] is not expected:
                _fail()
        for key in ("artifacts_sha256", "plan_sha256", "candidate_sha256", "source_sha256", "data_sha256"):
            if type(result[key]) is not str or not _DIGEST.fullmatch(result[key]):
                _fail()
        if result["source_sha256"] != profile_descriptor(result["profile_id"])["expected_source_sha256"]:
            _fail()
        groups = _integer(result["group_count"], 2 * MIN_GROUPS_PER_CLASS, MAX_GROUPS)
        rows = _integer(result["row_count"], groups, MAX_GROUPS)
        members = _integer(result["member_group_count"], MIN_GROUPS_PER_CLASS, groups)
        nonmembers = _integer(result["nonmember_group_count"], MIN_GROUPS_PER_CLASS, groups)
        labels, ids, classes = result["membership_labels"], result["group_ids"], result["classes"]
        if (members + nonmembers != groups or type(labels) is not list or len(labels) != groups
                or any(type(value) is not int for value in labels) or labels != [1] * members + [0] * nonmembers
                or type(ids) is not list or len(ids) != groups or any(type(value) is not int for value in ids)
                or sorted(ids) != list(range(groups)) or type(classes) is not list):
            _fail()
        if result["task"] == "classification":
            if (not 2 <= len(classes) <= 32 or classes != sorted(set(classes))
                    or any(type(value) is not int or not -(2**31) <= value < 2**31 for value in classes)):
                _fail()
        elif classes != []:
            _fail()
        _exact(result["cases"], CASES)
        for name, case in result["cases"].items():
            _exact(case, {"loss_values", "native_loss_scores", "native_score_definition"})
            losses, scores = case["loss_values"], case["native_loss_scores"]
            if type(losses) is not list or type(scores) is not list or len(losses) != groups or len(scores) != groups:
                _fail()
            loss_features_float32(losses)
            for loss, score in zip(losses, scores):
                if _number(score, -MAX_LOSS, 0.) != -_number(loss, 0., MAX_LOSS):
                    _fail()
            if name == "target":
                definition = ("mean_negative_log_true_class_probability_per_feature_group" if result["task"] == "classification"
                              else "mean_squared_error_per_feature_group")
                if case["native_score_definition"] != definition:
                    _fail()
                if result["task"] == "classification" and any(loss > -math.log(1e-12) for loss in losses):
                    _fail()
            else:
                expected = [0. if name == "positive" and label else 1. for label in labels]
                if case["native_score_definition"] != "negative_synthetic_loss" or losses != expected:
                    _fail()
        full = result["native_full_run_metrics"]
        _exact(full, {"utility", "membership", "positive_control", "null_control", "controls_passed"})
        if full["controls_passed"] is not True:
            _fail()
        cls = ClassificationUtility if result["task"] == "classification" else RegressionUtility
        utility = cls.model_validate(full["utility"])
        if canonical_bytes(utility) != canonical_bytes(full["utility"]) or not nonmembers <= utility.records < rows:
            _fail()
        if result["task"] == "classification" and utility.majority_class not in classes:
            _fail()
        for name in ("membership", "positive_control", "null_control"):
            metric = MembershipMetrics.model_validate(full[name])
            if (canonical_bytes(metric) != canonical_bytes(full[name]) or metric.member_group_trials != members
                    or metric.calibration_group_trials + metric.nonmember_group_trials != nonmembers):
                _fail()
        target = full["membership"]
        audit_start = members + target["calibration_group_trials"]
        scores = result["cases"]["target"]["native_loss_scores"]
        auc = rank_auc([1] * members + [0] * (groups - audit_start), scores[:members] + scores[audit_start:])
        if abs(auc - target["raw_auc"]) > 1e-12:
            _fail()
        return result
    except ProtocolError:
        raise
    except Exception:
        raise ProtocolError("ART loss-oracle comparison rejected") from None


def _splits(data):
    from sklearn.model_selection import train_test_split
    labels = data["membership_labels"]
    result = []
    for seed in SEEDS:
        train, test = train_test_split(list(range(len(labels))), test_size=TEST_FRACTION,
            stratify=labels, random_state=seed, shuffle=True)
        result.append({"seed": seed, "train_indices": train, "test_indices": test,
                       "membership_labels": [labels[index] for index in test]})
    return result


def frozen_splits(prepared):
    """Return three fixed overlapping stratified group splits, with no tuning."""
    return owned(_splits(validate_input(prepared)))


def replay_probabilities(data, case_name, repetition, expected):
    """Replay the retained binary LR head and float32 scaler operations.

    This checks scores, scaler moments and feature bindings without importing
    ART or calling the upstream attack model's predict method. It does not prove
    that retained coefficients are the optimizer's unique solution.
    """
    import numpy as np
    learned = repetition["learned"]
    _exact(learned, {"classes", "coef", "intercept", "scaler_mean", "scaler_scale", "n_iter"})
    if type(learned["classes"]) is not list or any(type(value) is not int for value in learned["classes"]) or learned["classes"] != [0, 1]:
        _fail()
    _integer(learned["n_iter"], 0, 499)
    for key in ("coef", "scaler_mean", "scaler_scale"):
        if type(learned[key]) is not list or len(learned[key]) != 2:
            _fail()
    coef = [_number(value, -1e6, 1e6) for value in learned["coef"]]
    intercept = _number(learned["intercept"], -1e6, 1e6)
    means = [_number(value) for value in learned["scaler_mean"]]
    scales = [_number(value, 1e-30, MAX_LOSS) for value in learned["scaler_scale"]]
    if coef[1] != 0. or means[1] != 0. or scales[1] != 1.:
        _fail()
    losses = loss_features_float32(data["cases"][case_name]["loss_values"])
    if canonical_bytes(repetition["loss_features_float32"]) != canonical_bytes(losses):
        _fail()
    train = [losses[index] for index in expected["train_indices"]]
    mean = math.fsum(train) / len(train)
    variance = math.fsum((value - mean)**2 for value in train) / len(train)
    eps = np.finfo(np.float64).eps
    constant = variance <= len(train) * eps * variance + (len(train) * mean * eps)**2
    scale = 1. if constant else math.sqrt(variance)
    if (not math.isclose(mean, means[0], rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(scale, scales[0], rel_tol=1e-12, abs_tol=1e-12)):
        _fail()
    features = np.asarray([[losses[index], 0.] for index in expected["test_indices"]], dtype=np.float32)
    # StandardScaler retains float32 arrays and rounds each in-place operation.
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        features -= np.asarray(means, dtype=np.float64)
        features /= np.asarray(scales, dtype=np.float64)
    if not np.isfinite(features).all():
        _fail()
    logits = features.astype(np.float64) @ np.asarray(coef) + intercept
    result = []
    for value in logits:
        value = _number(float(value), -1e12, 1e12)
        result.append(1. / (1. + math.exp(-value)) if value >= 0. else math.exp(value) / (1. + math.exp(value)))
    actual = repetition["member_probabilities"]
    if type(actual) is not list or len(actual) != len(result):
        _fail()
    for observed, replayed in zip(actual, result):
        if not math.isclose(_number(observed, 0., 1.), replayed, rel_tol=1e-12, abs_tol=1e-12):
            _fail()
    return result


def rank_auc(labels, scores):
    """Tie-aware rank AUC retaining the original score direction and loss bound."""
    if (type(labels) is not list or type(scores) is not list or not 2 <= len(labels) <= MAX_GROUPS
            or len(labels) != len(scores) or any(type(value) is not int or value not in (0, 1) for value in labels)
            or set(labels) != {0, 1}):
        _fail()
    ordered = sorted((_number(score), label) for score, label in zip(scores, labels))
    total = 0.
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][0] == ordered[start][0]:
            end += 1
        total += (start + 1 + end) / 2. * sum(label for _, label in ordered[start:end])
        start = end
    members = sum(labels)
    return (total - members * (members + 1) / 2.) / (members * (len(labels) - members))


def compare_repetitions(prepared, case_name, repetitions):
    """Validate fixed splits, replay scores and recompute paired descriptive AUC."""
    try:
        data = validate_input(prepared)
        if type(case_name) is not str or case_name not in CASES or type(repetitions) is not list or len(repetitions) != REPEATS:
            _fail()
        repetitions = owned(repetitions)
        rows = []
        for actual, expected in zip(repetitions, _splits(data)):
            _exact(actual, _REPETITION_KEYS)
            for key in ("seed", "train_indices", "test_indices", "membership_labels"):
                if canonical_bytes(actual[key]) != canonical_bytes(expected[key]):
                    _fail()
            replay_probabilities(data, case_name, actual, expected)
            attack = membership_metrics(actual["membership_labels"], actual["member_probabilities"])
            native_scores = [data["cases"][case_name]["native_loss_scores"][index] for index in expected["test_indices"]]
            native_auc = rank_auc(expected["membership_labels"], native_scores)
            rows.append({"seed": expected["seed"], "train_group_count": len(expected["train_indices"]),
                "test_group_count": len(expected["test_indices"]),
                "test_indices_sha256": _sha(canonical_bytes(expected["test_indices"])),
                "membership_labels_sha256": _sha(canonical_bytes(expected["membership_labels"])),
                "member_probabilities_sha256": _sha(canonical_bytes(actual["member_probabilities"])),
                "learned_sha256": _sha(canonical_bytes(actual["learned"])), "scores_replayed": True,
                "attack": attack, "native_loss": {"raw_auc": native_auc, "symmetric_auc": max(native_auc, 1. - native_auc),
                    **{key: attack[key] for key in ("member_count", "nonmember_count", "total")}},
                "paired_raw_auc_difference": attack["raw_auc"] - native_auc})
        mean = lambda values: math.fsum(values) / REPEATS
        controls = (all(row["attack"]["raw_auc"] >= .9 for row in rows) if case_name == "positive"
                    else all(abs(row["attack"]["raw_auc"] - .5) <= 1e-12 for row in rows) if case_name == "null" else None)
        return owned({"schema": "mra-art-comparison/v1", "status": "completed", "case_name": case_name,
            "profile_id": data["profile_id"], "task": data["task"], "input_sha256": _sha(canonical_bytes(data)),
            "artifacts_sha256": data["artifacts_sha256"], "repetitions": rows,
            "summary": {"attack_raw_auc_mean": mean(row["attack"]["raw_auc"] for row in rows),
                "native_loss_raw_auc_mean": mean(row["native_loss"]["raw_auc"] for row in rows),
                "paired_raw_auc_difference_mean": mean(row["paired_raw_auc_difference"] for row in rows),
                "auc_uncertainty": "not_estimated", "repetitions_are_not_independent_samples": True},
            "controls_satisfied": controls, "native_full_run_metrics": data["native_full_run_metrics"],
            "protocol": dict(PROTOCOL), **FLAGS})
    except ProtocolError:
        raise
    except Exception:
        raise ProtocolError("ART loss-oracle comparison rejected") from None
