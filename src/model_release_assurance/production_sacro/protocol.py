"""Fixed public-fixture comparison inputs and independently recomputed metrics.

Captured native bytes are numerically replayed; the target model is never refit.
Each identical-feature group contributes one probability vector and one mean
log-loss score, not one observation per duplicate row. A feature group is not a
justified person/privacy unit. Repeated splits are overlapping descriptive
comparisons, not independent samples, uncertainty estimates or low-FPR proofs.

Profile IDs/source pins are local plan bindings, not authenticated upstream
provenance. The trusted PRD13 caller establishes the source-to-registration
binding. Synthetic controls deliberately encode membership; they are learner
path fixtures, not evidence about the target model's privacy. No SACRO import,
arbitrary model loading, release approval or external runtime occurs here.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from ..production_adapters import native
from ..production_adapters.contracts import (ClassificationUtility, MembershipMetrics,
    canonical_bytes, parse_candidate, parse_plan, strict_json)
from ..production_evidence.replay import artifact_manifest, replay_native_bundle
from ..production_registration.profiles import PROFILE_IDS, profile_descriptor

FIXED_SEED = 20261001
REPEATS = 3
SEEDS = (20261001, 20261002, 20261003)
TEST_FRACTION = .5
MAX_GROUPS = 4096
MAX_CLASSES = 32
MIN_GROUPS_PER_CLASS = 20
MAX_PROTOCOL_BYTES = 16 * 1024 * 1024
SUPPORTED_PROFILES = tuple(name for name in PROFILE_IDS if name != "sklearn-diabetes")
_CASES = ("target", "positive", "null")
_FLAGS = dict(native.FLAGS)
_PROTOCOL = {"seeds": list(SEEDS), "test_fraction": TEST_FRACTION, "membership_threshold": .5,
    "threshold_comparison": "strict_greater", "metric_unit": "identical_feature_group",
    "control_scope": "membership-conditioned synthetic confidence matrices"}
_INPUT_KEYS = {"schema", "status", "profile_id", "task", "artifacts_sha256", "plan_sha256",
    "candidate_sha256", "source_sha256", "data_sha256", "row_count", "group_count", "member_group_count",
    "nonmember_group_count", "classes", "group_ids", "membership_labels", "cases", "native_full_run_metrics",
    "protocol", *_FLAGS}
_REPETITION_KEYS = {"seed", "train_indices", "test_indices", "membership_labels", "member_probabilities", "upstream_auc"}
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


class ProtocolError(ValueError):
    """Bounded comparison data or metric binding was rejected."""


class UnsupportedProfile(ProtocolError):
    """A numerically valid native bundle has no approved comparison profile."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _fail():
    raise ProtocolError("Public fixture comparison rejected")


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail()
    return value


def _number(value, low=-1e12, high=1e12):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        _fail()
    return float(value)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _owned(value):
    # Bound traversal before encoding; unknown opaque objects, ndarray, bool
    # scores and nested probability vectors are never silently coerced.
    remaining = 600000
    def visit(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 16:
            _fail()
        if type(item) is dict:
            if len(item) > 64 or any(type(key) is not str or len(key) > 128 for key in item):
                _fail()
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            if len(item) > MAX_GROUPS:
                _fail()
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            if len(item) > 16384:
                _fail()
        elif type(item) is bool or item is None:
            pass
        elif type(item) is int:
            if abs(item) > 2**53 - 1:
                _fail()
        elif type(item) is float:
            if not math.isfinite(item):
                _fail()
        else:
            _fail()
    try:
        visit(value)
        raw = canonical_bytes(value)
        if len(raw) > MAX_PROTOCOL_BYTES:
            _fail()
        return json.loads(raw)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise ProtocolError("Public fixture comparison rejected") from None


def _labels_scores(labels, scores, *, probabilities=False):
    if type(labels) is not list or type(scores) is not list or not 2 <= len(labels) <= MAX_GROUPS or len(scores) != len(labels):
        _fail()
    if any(type(label) is not int or label not in (0, 1) for label in labels) or set(labels) != {0, 1}:
        _fail()
    return list(labels), [_number(value, 0., 1.) if probabilities else _number(value) for value in scores]


def rank_auc(labels, scores):
    """Tie-aware Mann-Whitney rank AUC, without sklearn or score-direction flips."""
    labels, scores = _labels_scores(labels, scores)
    ordered = sorted(zip(scores, labels), key=lambda pair: pair[0])
    rank_sum = 0.
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][0] == ordered[start][0]:
            end += 1
        mean_rank = (start + 1 + end) / 2.
        rank_sum += mean_rank * sum(label for _, label in ordered[start:end])
        start = end
    members = sum(labels)
    nonmembers = len(labels) - members
    return (rank_sum - members * (members + 1) / 2.) / (members * nonmembers)


def membership_metrics(labels, member_probabilities):
    """Recompute AUC and scalar class-1 probabilities at strict >0.5 cutoff.

    A probability of exactly .5 predicts nonmember, matching binary argmax's
    first-class tie. Symmetric AUC is diagnostic only; raw direction is retained.
    No confidence interval, low-FPR claim, privacy ceiling or approval is added.
    """
    labels, probabilities = _labels_scores(labels, member_probabilities, probabilities=True)
    member_count = sum(labels)
    nonmember_count = len(labels) - member_count
    tp = sum(label == 1 and value > .5 for label, value in zip(labels, probabilities))
    fp = sum(label == 0 and value > .5 for label, value in zip(labels, probabilities))
    auc = rank_auc(labels, probabilities)
    return {"raw_auc": auc, "symmetric_auc": max(auc, 1. - auc), "member_count": member_count,
        "nonmember_count": nonmember_count, "total": len(labels), "true_positives": tp,
        "false_positives": fp, "true_negatives": nonmember_count - fp, "false_negatives": member_count - tp,
        "tpr": tp / member_count, "fpr": fp / nonmember_count}


def _profile(plan):
    if plan.task == "regression":
        raise UnsupportedProfile("regression_not_supported")
    for name in SUPPORTED_PROFILES:
        descriptor = profile_descriptor(name)
        dataset_id = ("research." + name + ".mixed-model-export-20260929-v1"
                      if descriptor["source_kind"] == "research_prepared" else name)
        if plan.dataset_id == dataset_id and plan.source_sha256 == descriptor["expected_source_sha256"]:
            return name
    raise UnsupportedProfile("unregistered_profile")


def _control_probabilities(labels, classes, positive):
    uniform = [1. / classes] * classes
    concentrated = [.99] + [(1. - .99) / (classes - 1)] * (classes - 1)
    return [list(concentrated if positive and label else uniform) for label in labels]


def prepare_input(blobs):
    """Replay eight captured artifacts and return owned group-level scalar input.

    Members come first in frozen plan.train_groups order; nonmembers follow in
    calibration_groups then audit_groups order. Original native full-run metrics
    retain their original calibration/audit definitions. Paired comparisons use
    the combined nonmember pool and therefore measure a different fixed split.
    """
    try:
        if type(blobs) is not dict:
            _fail()
        owned = dict(blobs)
        manifest = artifact_manifest(owned)
        replay_native_bundle(owned)
        plan = parse_plan(owned["plan.json"])
        profile_id = _profile(plan)
        candidate = parse_candidate(owned["candidate.json"])
        data = strict_json(owned["dataset.json"])
        x, y = native._arrays(data["x"], data["y"])
        probabilities = native.replay_candidate(owned["candidate.json"], x)
        row_scores = native._row_scores(probabilities, y, "classification", candidate.model.classes)
        group_ids = list(plan.train_groups) + list(plan.calibration_groups) + list(plan.audit_groups)
        labels = [1] * len(plan.train_groups) + [0] * (len(plan.calibration_groups) + len(plan.audit_groups))
        grouped_probabilities, grouped_scores = [], []
        import numpy as np
        for group_id in group_ids:
            rows = plan.groups[group_id].rows
            vectors = probabilities[rows]
            if not np.all(vectors == vectors[0]):
                _fail()
            grouped_probabilities.append(vectors[0].tolist())
            values = row_scores[rows]
            grouped_scores.append(float(values[0]) if np.all(values == values[0]) else float(np.mean(values)))
        classes = list(candidate.model.classes)
        cases = {"target": {"probabilities": grouped_probabilities, "native_loss_scores": grouped_scores,
                            "native_score_definition": "mean_log_true_class_probability_per_feature_group"}}
        for name, positive in (("positive", True), ("null", False)):
            values = _control_probabilities(labels, len(classes), positive)
            cases[name] = {"probabilities": values, "native_loss_scores": [math.log(row[0]) for row in values],
                           "native_score_definition": "log_synthetic_class_zero_probability"}
        report = strict_json(owned["report.json"])
        result = {"schema": "mra-sacro-comparison-input/v1", "status": "prepared", "profile_id": profile_id,
            "task": "classification", "artifacts_sha256": _sha(canonical_bytes(manifest)),
            "plan_sha256": _sha(owned["plan.json"]), "candidate_sha256": _sha(owned["candidate.json"]),
            "source_sha256": plan.source_sha256, "data_sha256": plan.data_sha256, "row_count": len(y),
            "group_count": len(group_ids), "member_group_count": sum(labels), "nonmember_group_count": len(labels) - sum(labels),
            "classes": classes, "group_ids": group_ids, "membership_labels": labels, "cases": cases,
            "native_full_run_metrics": {key: report[key] for key in ("utility", "membership", "positive_control", "null_control", "controls_passed")},
            "protocol": dict(_PROTOCOL), **_FLAGS}
        return validate_input(result)
    except UnsupportedProfile:
        raise
    except Exception:
        raise ProtocolError("Public fixture comparison rejected") from None


def validate_input(prepared):
    """Validate a prepared JSON contract; this does not authenticate its origin."""
    try:
        _exact(prepared, _INPUT_KEYS)
        result = _owned(prepared)
        if (result["schema"] != "mra-sacro-comparison-input/v1" or result["status"] != "prepared"
                or result["task"] != "classification" or result["profile_id"] not in SUPPORTED_PROFILES
                or canonical_bytes(result["protocol"]) != canonical_bytes(_PROTOCOL)):
            _fail()
        for key, value in _FLAGS.items():
            if result[key] is not value:
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
                or sorted(ids) != list(range(groups)) or type(classes) is not list or not 2 <= len(classes) <= MAX_CLASSES
                or any(type(value) is not int or not -(2**31) <= value < 2**31 for value in classes)
                or classes != sorted(set(classes))):
            _fail()
        _exact(result["cases"], _CASES)
        for name, case in result["cases"].items():
            _exact(case, {"probabilities", "native_loss_scores", "native_score_definition"})
            values, scores = case["probabilities"], case["native_loss_scores"]
            if type(values) is not list or len(values) != groups or type(scores) is not list or len(scores) != groups:
                _fail()
            for vector in values:
                if type(vector) is not list or len(vector) != len(classes):
                    _fail()
                numbers = [_number(value, 0., 1.) for value in vector]
                if abs(math.fsum(numbers) - 1.) > 1e-12:
                    _fail()
            for score in scores:
                _number(score, math.log(1e-12), 0.)
            if name == "target":
                if case["native_score_definition"] != "mean_log_true_class_probability_per_feature_group":
                    _fail()
            else:
                expected = _control_probabilities(labels, len(classes), name == "positive")
                if (case["native_score_definition"] != "log_synthetic_class_zero_probability"
                        or canonical_bytes(values) != canonical_bytes(expected)
                        or canonical_bytes(scores) != canonical_bytes([math.log(row[0]) for row in expected])):
                    _fail()
        full = result["native_full_run_metrics"]
        _exact(full, {"utility", "membership", "positive_control", "null_control", "controls_passed"})
        if full["controls_passed"] is not True:
            _fail()
        utility = ClassificationUtility.model_validate(full["utility"])
        if (canonical_bytes(utility) != canonical_bytes(full["utility"])
                or not nonmembers <= utility.records < rows or utility.majority_class not in classes):
            _fail()
        for name in ("membership", "positive_control", "null_control"):
            metric = MembershipMetrics.model_validate(full[name])
            if (canonical_bytes(metric) != canonical_bytes(full[name]) or metric.member_group_trials != members
                    or metric.calibration_group_trials + metric.nonmember_group_trials != nonmembers):
                _fail()
        target = full["membership"]
        audit_start = members + target["calibration_group_trials"]
        target_scores = result["cases"]["target"]["native_loss_scores"]
        raw_auc = rank_auc([1] * members + [0] * (groups - audit_start),
                           target_scores[:members] + target_scores[audit_start:])
        if abs(raw_auc - target["raw_auc"]) > 1e-12:
            _fail()
        return result
    except ProtocolError:
        raise
    except Exception:
        raise ProtocolError("Public fixture comparison rejected") from None


def _splits(validated):
    from sklearn.model_selection import train_test_split
    labels = validated["membership_labels"]
    result = []
    for seed in SEEDS:
        train, test = train_test_split(list(range(len(labels))), test_size=TEST_FRACTION,
                                      stratify=labels, random_state=seed, shuffle=True)
        result.append({"seed": seed, "train_indices": train, "test_indices": test,
                       "membership_labels": [labels[index] for index in test]})
    return result


def frozen_splits(prepared):
    """Freeze SACRO 2.0.1's no-tuning train_test_split membership partitions.

    The three seeds are fixed before external execution. This is not a search
    for favorable runs. Identical-feature groups cannot cross one split, while
    distinct repeats overlap and must not be pooled as independent observations.
    """
    return _owned(_splits(validate_input(prepared)))


def compare_repetitions(prepared, case_name, repetitions):
    """Verify fixed indices/labels and recompute attack versus paired native AUC.

    Each external repetition must contain exactly seed, train_indices,
    test_indices, membership_labels, member_probabilities, upstream_auc. Scalar
    probabilities mean membership class 1, in test_indices order. Upstream AUC
    is only a consistency check at SACRO 2.0.1's eight decimal places;
    reported metrics retain independently recomputed full precision.
    """
    try:
        data = validate_input(prepared)
        if type(case_name) is not str or case_name not in _CASES or type(repetitions) is not list or len(repetitions) != REPEATS:
            _fail()
        repetitions = _owned(repetitions)
        fixed = _splits(data)
        result = []
        for actual, expected in zip(repetitions, fixed):
            _exact(actual, _REPETITION_KEYS)
            for key in ("seed", "train_indices", "test_indices", "membership_labels"):
                if canonical_bytes(actual[key]) != canonical_bytes(expected[key]):
                    _fail()
            metrics = membership_metrics(actual["membership_labels"], actual["member_probabilities"])
            # SACRO 2.0.1 rounds its exported AUC to eight decimal places.
            # Validate that representation without rounding our own estimate.
            if abs(round(metrics["raw_auc"], 8) - _number(actual["upstream_auc"], 0., 1.)) > 1e-12:
                _fail()
            native_scores = [data["cases"][case_name]["native_loss_scores"][index] for index in expected["test_indices"]]
            native_auc = rank_auc(expected["membership_labels"], native_scores)
            native_metrics = {"raw_auc": native_auc, "symmetric_auc": max(native_auc, 1. - native_auc),
                **{key: metrics[key] for key in ("member_count", "nonmember_count", "total")}}
            result.append({"seed": expected["seed"], "train_group_count": len(expected["train_indices"]),
                "test_group_count": len(expected["test_indices"]),
                "test_indices_sha256": _sha(canonical_bytes(expected["test_indices"])),
                "membership_labels_sha256": _sha(canonical_bytes(expected["membership_labels"])),
                "member_probabilities_sha256": _sha(canonical_bytes(actual["member_probabilities"])),
                "attack": metrics, "native_loss": native_metrics,
                "paired_raw_auc_difference": metrics["raw_auc"] - native_auc})
        mean = lambda values: math.fsum(values) / REPEATS
        controls_satisfied = (all(row["attack"]["raw_auc"] >= .9 for row in result) if case_name == "positive"
                              else all(abs(row["attack"]["raw_auc"] - .5) <= 1e-12 for row in result) if case_name == "null" else None)
        return _owned({"schema": "mra-sacro-comparison/v1", "status": "completed", "case_name": case_name,
            "profile_id": data["profile_id"], "input_sha256": _sha(canonical_bytes(data)),
            "artifacts_sha256": data["artifacts_sha256"], "repetitions": result,
            "summary": {"attack_raw_auc_mean": mean(row["attack"]["raw_auc"] for row in result),
                "native_loss_raw_auc_mean": mean(row["native_loss"]["raw_auc"] for row in result),
                "paired_raw_auc_difference_mean": mean(row["paired_raw_auc_difference"] for row in result),
                "auc_uncertainty": "not_estimated", "repetitions_are_not_independent_samples": True},
            "controls_satisfied": controls_satisfied, "native_full_run_metrics": data["native_full_run_metrics"],
            "protocol": dict(_PROTOCOL), **_FLAGS})
    except ProtocolError:
        raise
    except Exception:
        raise ProtocolError("Public fixture comparison rejected") from None
