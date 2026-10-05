"""Bounded native GaussianNB/Ridge training and exact inert-candidate replay.

This trusted local research adapter is separate from the fixed PRD10 count job.
It does not load models, execute caller code, qualify hostile isolation, measure
a complete privacy ceiling, or authorize production/data/model release.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
import os
from pathlib import Path
import stat
import sys
import time

from .contracts import (ADAPTER_ID, ADAPTER_VERSION, MAX_FEATURES, MAX_ROWS, MAX_JSON_BYTES,
    NativeCandidate, NativePlan, NativeReport, canonical_bytes, parse_candidate, parse_plan, strict_json)
from ..analyzers.attack import clopper_pearson_lower, clopper_pearson_upper

FLAGS = {"fixture_only": True, "can_clear": False, "authorization_eligible": False,
         "production_authorized": False, "model_delivery": False,
         "hostile_code_isolated": False, "network_isolated": False}
LIMITATIONS = [
    "One fixed native model and negative-loss membership screen; no model/attack selection on audit outcomes.",
    "Identical feature rows are grouped across partitions; a feature group is not a justified person/privacy unit.",
    "Group mean-loss TPR/FPR intervals are conditional binomial calculations; group independence and population representativeness are unverified.",
    "AUC is a descriptive point estimate; no AUC confidence interval, low-FPR certificate, DP claim or privacy ceiling.",
    "Positive/null controls are label-aware scorer-path oracles, not realistic estimators or end-to-end attack validation; regression controls use exact synthetic zero targets and zero/unit residuals.",
    "Finite local input/query bounds are enforced; hostile-code isolation and hard process CPU/memory limits are not established.",
    "Dataset/task mappings, source labels and benchmark sampling are trusted local research inputs, not agency approval.",
]
MAX_ABSOLUTE_INPUT = 1e12
MIN_GROUP_TRIALS = 20


class UnsupportedAdapter(ValueError):
    pass


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _runtime():
    return {"python": sys.version.split()[0], **{name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "scikit-learn")}}


def implementation_sha256():
    package = Path(__file__).parent.parent
    files = {"production_adapters/native.py": Path(__file__),
             "production_adapters/contracts.py": Path(__file__).with_name("contracts.py"),
             "analyzers/attack.py": package / "analyzers/attack.py",
             "portfolio_statistics.py": package / "portfolio_statistics.py"}
    return _sha(canonical_bytes({name: _sha(path.read_bytes()) for name, path in files.items()}))


def _arrays(x, y=None):
    import numpy as np
    source = np.asarray(x)
    if source.dtype.kind not in {"i", "u", "f"} or source.ndim != 2:
        raise ValueError("Only a numeric feature matrix is supported")
    if not 1 <= source.shape[0] <= MAX_ROWS or not 1 <= source.shape[1] <= MAX_FEATURES:
        raise ValueError("Feature matrix exceeds bounded dimensions")
    features = np.array(source, dtype=np.float64, copy=True, order="C")
    if not np.isfinite(features).all() or np.any(np.abs(features) > MAX_ABSOLUTE_INPUT):
        raise ValueError("Features must be finite bounded numbers")
    features[features == 0] = 0.  # Canonicalize signed zero for identical-row grouping.
    if y is None:
        return features
    source_y = np.asarray(y)
    if source_y.dtype.kind not in {"i", "u", "f"} or source_y.ndim != 1 or len(source_y) != len(features):
        raise ValueError("Only aligned numeric targets are supported")
    labels = np.array(source_y, dtype=np.float64, copy=True)
    if not np.isfinite(labels).all() or np.any(np.abs(labels) > MAX_ABSOLUTE_INPUT):
        raise ValueError("Targets must be finite bounded numbers")
    labels[labels == 0] = 0.
    return features, labels


def _real_directory(path):
    for current in (*reversed(path.parents), path):
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
                    or not stat.S_ISDIR(info.st_mode)):
                raise ValueError("Output path contains an unsafe directory")


def _new_output(value):
    raw = Path(value)
    if ".." in raw.parts:
        raise ValueError("Output traversal is refused")
    output = raw.absolute()
    _real_directory(output.parent)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Native adapter output must be new")
    output.mkdir(parents=True, exist_ok=False)
    _real_directory(output)
    return output


def _write(path, value):
    raw = canonical_bytes(value) + b"\n"
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Native adapter artifact exceeds its byte bound")
    with path.open("xb") as stream:
        stream.write(raw)
    return _sha(raw)


def _read(path, maximum=MAX_JSON_BYTES):
    _real_directory(path.parent)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_nlink != 1
            or not 0 < before.st_size <= maximum):
        raise ValueError("Unsafe or oversized native adapter artifact")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or getattr(opened, "st_file_attributes", 0) & 0x400):
            raise ValueError("Opened artifact is not a single regular file")
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError("Artifact identity changed before read")
        raw = stream.read(maximum + 1)
        end = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns):
            raise ValueError("Artifact changed through open descriptor")
    after = path.lstat()
    if (len(raw) != before.st_size or len(raw) > maximum
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ValueError("Native adapter artifact changed during read")
    return raw


def _groups(x):
    import numpy as np
    grouped = {}
    for index, row in enumerate(x):
        digest = _sha(np.asarray(row, dtype="<f8").tobytes())
        grouped.setdefault(digest, []).append(index)
    return [{"feature_sha256": digest, "rows": rows} for digest, rows in grouped.items()]


def _plan(x, y, dataset_id, source_sha256, feature_names, task, seed, data_sha256):
    import numpy as np
    groups = _groups(x)
    order = np.random.default_rng(seed).permutation(len(groups)).tolist()
    cut = len(order) // 2
    remaining = order[cut:]
    group_sets = (order[:cut], remaining[:len(remaining)//2], remaining[len(remaining)//2:])
    rows = lambda ids: sorted(index for group_id in ids for index in groups[group_id]["rows"])
    return NativePlan(task=task, dataset_id=dataset_id, source_sha256=source_sha256,
        data_sha256=data_sha256, implementation_sha256=implementation_sha256(),
        feature_names=list(feature_names), seed=seed, groups=groups,
        model_recipe="standard-scaler+gaussian-nb-1e-9/v1" if task == "classification" else "standard-scaler+ridge-alpha1-svd/v1",
        train_groups=group_sets[0], calibration_groups=group_sets[1], audit_groups=group_sets[2],
        train_indices=rows(group_sets[0]), calibration_indices=rows(group_sets[1]), audit_indices=rows(group_sets[2]),
        duplicate_groups=sum(len(group["rows"]) > 1 for group in groups),
        conflicting_label_groups=sum(len(np.unique(y[group["rows"]])) > 1 for group in groups))


def replay_candidate(raw_bytes, x):
    """Return probabilities (saved class order) or regression values from inert JSON."""
    import numpy as np
    candidate = parse_candidate(raw_bytes)
    features = _arrays(x)
    if features.shape[1] != len(candidate.feature_names):
        raise ValueError("Candidate feature dimensions differ")
    scaler = candidate.preprocessing
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            scaled = (features - np.asarray(scaler.mean)) / np.asarray(scaler.scale)
            if candidate.task == "classification":
                model = candidate.model
                variance, theta = np.asarray(model.variance), np.asarray(model.theta)
                joint = np.log(np.asarray(model.prior))[None, :] - .5 * np.log(2 * math.pi * variance).sum(axis=1)[None, :]
                joint = joint - .5 * (((scaled[:, None, :] - theta[None, :, :]) ** 2) / variance[None, :, :]).sum(axis=2)
                result = np.exp(joint - joint.max(axis=1, keepdims=True))
                result /= result.sum(axis=1, keepdims=True)
            else:
                result = scaled @ np.asarray(candidate.model.coefficients) + candidate.model.intercept
    except FloatingPointError as error:
        raise ValueError("Candidate numeric replay overflowed") from error
    if not np.isfinite(result).all():
        raise ValueError("Candidate replay produced nonfinite output")
    return result


def _row_scores(predictions, y, task, classes):
    import numpy as np
    if task == "classification":
        probabilities = np.asarray(predictions, dtype=np.float64)
        columns = np.searchsorted(classes, y)
        if (probabilities.shape != (len(y), len(classes)) or np.any(columns >= len(classes))
                or not np.array_equal(np.asarray(classes)[columns], y)
                or not np.isfinite(probabilities).all() or np.any(probabilities < 0)
                or np.any(probabilities > 1) or not np.allclose(probabilities.sum(axis=1), 1., rtol=0., atol=1e-12)):
            raise ValueError("Invalid classifier probabilities")
        return np.log(np.clip(probabilities[np.arange(len(y)), columns], 1e-12, 1.))
    prediction = np.asarray(predictions, dtype=np.float64)
    if prediction.shape != y.shape or not np.isfinite(prediction).all():
        raise ValueError("Invalid regression predictions")
    with np.errstate(over="raise", invalid="raise"):
        score = -(prediction - y) ** 2
    if not np.isfinite(score).all():
        raise ValueError("Regression loss overflow")
    return score


def _auc(member, nonmember):
    """Independent deterministic tie-aware rank statistic; no estimator object."""
    import numpy as np
    values = np.concatenate((member, nonmember))
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.
        start = end
    n, m = len(member), len(nonmember)
    return float((ranks[:n].sum() - n * (n + 1) / 2.) / (n * m))


def _score_report(member, calibration, audit):
    import numpy as np
    arrays = [np.asarray(value, dtype=np.float64) for value in (member, calibration, audit)]
    if any(value.ndim != 1 or len(value) < MIN_GROUP_TRIALS or not np.isfinite(value).all() for value in arrays):
        raise UnsupportedAdapter("insufficient_finite_group_trials")
    member, calibration, audit = arrays
    threshold = float(np.quantile(calibration, .9, method="higher"))
    tp, fp = int((member > threshold).sum()), int((audit > threshold).sum())
    auc = _auc(member, audit)
    interval = lambda successes, count: [
        clopper_pearson_lower(successes, count, .975),
        clopper_pearson_upper(successes, count, .975)]
    return {"raw_auc": auc, "symmetric_auc": max(auc, 1 - auc), "threshold": threshold,
        "threshold_comparison": "strict_greater", "calibration_target_fpr": .1,
        "member_group_trials": len(member), "calibration_group_trials": len(calibration),
        "nonmember_group_trials": len(audit), "true_positives": tp, "false_positives": fp,
        "tpr": tp / len(member), "fpr": fp / len(audit),
        "tpr_interval_95": interval(tp, len(member)), "fpr_interval_95": interval(fp, len(audit)),
        "interval_assumption": "conditional_independent_group_trials_not_population_or_privacy_validation",
        "auc_uncertainty": "not_estimated"}


def _utility(prediction, y, plan, classes):
    import numpy as np
    train = np.asarray(plan.train_indices, dtype=int)
    holdout = np.asarray([*plan.calibration_indices, *plan.audit_indices], dtype=int)
    if plan.task == "classification":
        predicted = np.asarray(classes)[prediction[holdout].argmax(axis=1)]
        values, counts = np.unique(y[train], return_counts=True)
        majority = float(values[counts.argmax()])
        actual = y[holdout]
        return {"task": "classification", "records": len(holdout),
            "accuracy": float(np.mean(predicted == actual)),
            "balanced_accuracy": float(np.mean([np.mean(predicted[actual == value] == value) for value in np.unique(actual)])),
            "log_loss": float(-_row_scores(prediction[holdout], actual, plan.task, classes).mean()),
            "majority_accuracy": float(np.mean(actual == majority)),
            "majority_class": majority}
    actual, predicted = y[holdout], prediction[holdout]
    residual = actual - predicted
    denominator = float(((actual - actual.mean()) ** 2).sum())
    return {"task": "regression", "records": len(holdout),
        "rmse": float(np.sqrt(np.mean(residual ** 2))), "mae": float(np.mean(np.abs(residual))),
        "r2": float(1 - (residual ** 2).sum() / denominator) if denominator > 0 else None,
        "training_mean_baseline_rmse": float(np.sqrt(np.mean((actual - y[train].mean()) ** 2)))}


def _measure(raw, x, y, plan):
    import numpy as np
    candidate = parse_candidate(raw)
    prediction = replay_candidate(raw, x)
    classes = candidate.model.classes if plan.task == "classification" else []
    scores = _row_scores(prediction, y, plan.task, classes)
    member_rows = set(plan.train_indices)
    membership = np.asarray([index in member_rows for index in range(len(y))])
    control_y = y
    if plan.task == "classification":
        k = len(classes)
        columns = np.searchsorted(classes, y)
        true_probability = np.where(membership, .99, .01)
        positive = np.repeat(((1 - true_probability) / (k - 1))[:, None], k, axis=1)
        positive[np.arange(len(y)), columns] = true_probability
        null = np.full((len(y), k), 1 / k)
    else:
        # Deliberate label-aware controls exercise residual scoring. They are
        # public fixture oracles, not predictors available to real attackers.
        # Exact representable synthetic targets avoid cancellation turning a
        # theoretically flat null into tiny label-dependent residuals.
        control_y = np.zeros(len(y))
        positive = np.where(membership, 0., 1.)
        null = np.ones(len(y))
    positive_scores = _row_scores(positive, control_y, plan.task, classes)
    null_scores = _row_scores(null, control_y, plan.task, classes)
    def grouped(values, ids):
        result = []
        for index in ids:
            observations = values[plan.groups[index].rows]
            # Preserve exact flat-score controls across unequal group sizes.
            result.append(float(observations[0]) if np.all(observations == observations[0]) else float(np.mean(observations)))
        return result
    groups = (plan.train_groups, plan.calibration_groups, plan.audit_groups)
    raw_scores = {name: {"member": grouped(values, groups[0]), "calibration": grouped(values, groups[1]),
                        "audit": grouped(values, groups[2])}
                  for name, values in (("target", scores), ("positive", positive_scores), ("null", null_scores))}
    summaries = {name: _score_report(**values) for name, values in raw_scores.items()}
    controls = (summaries["positive"]["raw_auc"] >= .9
                and abs(summaries["null"]["raw_auc"] - .5) <= 1e-12
                and summaries["positive"]["tpr"] == 1. and summaries["positive"]["fpr"] == 0.)
    report = {"schema_version": "mra-native-tabular-report/v1", "task": plan.task,
        "candidate_sha256": _sha(raw), "plan_sha256": _sha(canonical_bytes(plan) + b"\n"),
        "data_sha256": plan.data_sha256, "metric_unit": plan.metric_unit,
        "utility": _utility(prediction, y, plan, classes), "membership": summaries["target"],
        "positive_control": summaries["positive"], "null_control": summaries["null"],
        "controls_passed": controls, "scoring_rows": len(y),
        "control_scope": "label-aware public scorer-path oracles; not realistic estimators", **FLAGS}
    report = NativeReport.model_validate(report).model_dump(mode="json")
    score_document = {"schema_version": "mra-native-tabular-scores/v1", "scores": raw_scores}
    prediction_document = {"schema_version": "mra-native-tabular-predictions/v1",
                           "candidate_sha256": _sha(raw), "predictions": prediction.tolist()}
    return report, score_document, prediction_document


def _replay_run(output, *, receipt_required):
    """Recompute predictions, scores, controls and counts from retained inert bytes."""
    import numpy as np
    output = Path(output).absolute()
    try:
        _real_directory(output)
        receipt = strict_json(_read(output / "result.json")) if receipt_required else None
        if receipt_required:
            expected_files = {"dataset.json", "plan.json", "candidate.json", "report.json", "scores.json", "predictions.json", "replay.json"}
            if (type(receipt) is not dict or receipt.get("status") != "completed"
                    or type(receipt.get("files")) is not dict or set(receipt["files"]) != expected_files):
                raise ValueError("Complete retained receipt and exact file roster are required")
            if {path.name for path in output.iterdir()} != expected_files | {"result.json"}:
                raise ValueError("Retained output contains unexpected artifacts")
            for name, digest in receipt["files"].items():
                if _sha(_read(output / name)) != digest:
                    raise ValueError("Retained receipt file binding changed")
        plan_raw = _read(output / "plan.json")
        plan = parse_plan(plan_raw)
        data_raw = _read(output / "dataset.json")
        data = strict_json(data_raw)
        if type(data) is not dict or set(data) != {"schema_version", "x", "y", "feature_names", "task"}:
            raise ValueError("Dataset snapshot shape changed")
        if data["schema_version"] != "mra-native-tabular-data/v1":
            raise ValueError("Dataset snapshot version changed")
        x, y = _arrays(data["x"], data["y"])
        if _sha(data_raw) != plan.data_sha256 or data["feature_names"] != plan.feature_names or data["task"] != plan.task:
            raise ValueError("Dataset binding changed")
        reconstructed = _plan(x, y, plan.dataset_id, plan.source_sha256, plan.feature_names, plan.task, plan.seed, plan.data_sha256)
        if canonical_bytes(reconstructed) != canonical_bytes(plan):
            raise ValueError("Frozen plan or implementation binding changed")
        raw = _read(output / "candidate.json", 2 * 1024 * 1024)
        candidate = parse_candidate(raw)
        if (candidate.plan_sha256 != _sha(plan_raw) or candidate.source_sha256 != plan.source_sha256
                or candidate.data_sha256 != plan.data_sha256 or candidate.dataset_id != plan.dataset_id
                or candidate.feature_names != plan.feature_names or candidate.task != plan.task
                or candidate.implementation_sha256 != plan.implementation_sha256
                or candidate.runtime != _runtime() or candidate.training_rows != len(plan.train_indices)):
            raise ValueError("Candidate lineage changed")
        report, scores, predictions = _measure(raw, x, y, plan)
        for name, expected in (("report.json", report), ("scores.json", scores), ("predictions.json", predictions)):
            if canonical_bytes(strict_json(_read(output / name))) != canonical_bytes(expected):
                raise ValueError("Retained metrics or predictions do not replay")
        if receipt_required and (receipt.get("candidate_sha256") != _sha(raw)
                or receipt.get("plan_sha256") != _sha(plan_raw) or receipt.get("data_sha256") != _sha(data_raw)
                or receipt.get("utility") != report["utility"] or receipt.get("membership") != report["membership"]
                or any(receipt.get(key) is not value for key, value in FLAGS.items())):
            raise ValueError("Receipt summary binding changed")
        if not report["controls_passed"]:
            raise ValueError("Scorer controls failed")
        verified = {"schema_version": "mra-native-tabular-replay/v1", "status": "passed",
            "candidate_sha256": _sha(raw), "plan_sha256": _sha(plan_raw), "data_sha256": _sha(data_raw),
            "predictions_replayed": True, "metrics_replayed": True, "controls_replayed": True,
            "reasons": [], "verification_scope": "local_consistency_not_authenticity_or_original_training_attestation", **FLAGS}
        if receipt_required:
            if (canonical_bytes(strict_json(_read(output / "replay.json"))) != canonical_bytes(verified)
                    or canonical_bytes(receipt.get("replay")) != canonical_bytes(verified)):
                raise ValueError("Retained replay result changed")
            expected_controls = {"passed": True, "positive_auc": report["positive_control"]["raw_auc"],
                "null_auc": report["null_control"]["raw_auc"], "scope": report["control_scope"]}
            if (canonical_bytes(receipt.get("utility")) != canonical_bytes(report["utility"])
                    or canonical_bytes(receipt.get("membership")) != canonical_bytes(report["membership"])
                    or canonical_bytes(receipt.get("controls")) != canonical_bytes(expected_controls)
                    or receipt.get("dataset_id") != plan.dataset_id or receipt.get("source_sha256") != plan.source_sha256
                    or receipt.get("task") != plan.task or receipt.get("adapter_id") != ADAPTER_ID
                    or receipt.get("adapter_version") != ADAPTER_VERSION or receipt.get("runtime") != _runtime()
                    or receipt.get("reason") is not None):
                raise ValueError("Retained result context changed")
        return verified
    except Exception as error:
        return {"schema_version": "mra-native-tabular-replay/v1", "status": "failed",
            "predictions_replayed": False, "metrics_replayed": False, "controls_replayed": False,
            "reasons": ["replay_failed:" + type(error).__name__], **FLAGS}


def replay_run(output):
    """Verify the retained receipt then rerun its exact inert candidate and metrics.

    The receipt is local integrity evidence, not a signature or external proof of
    authorship. Production provenance/attestation is outside this adapter.
    """
    return _replay_run(output, receipt_required=True)


def run_native(x, y, *, dataset_id, source_sha256, feature_names, task="classification", output, seed=20261001):
    output = _new_output(output)
    started = time.monotonic()
    receipt = {"schema_version": "mra-native-tabular-result/v1", "status": "failed",
        "adapter_id": ADAPTER_ID, "adapter_version": ADAPTER_VERSION,
        "dataset_id": dataset_id if type(dataset_id) is str and len(dataset_id) <= 128 else "invalid",
        "task": task if type(task) is str and task in {"classification", "regression"} else "unsupported",
        "source_sha256": source_sha256 if type(source_sha256) is str and len(source_sha256) == 64 else None,
        "files": {}, "reason": None, "limitations": LIMITATIONS, **FLAGS}
    try:
        import numpy as np
        from sklearn.naive_bayes import GaussianNB
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        from threadpoolctl import threadpool_limits
        if type(task) is not str or task not in {"classification", "regression"}:
            raise UnsupportedAdapter("unsupported_task")
        x, y = _arrays(x, y)
        if type(feature_names) not in {list, tuple} or len(feature_names) != x.shape[1]:
            raise ValueError("Feature roster does not match numeric matrix")
        if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
            raise ValueError("A bounded exact random seed is required")
        if task == "classification":
            if not np.array_equal(y, np.rint(y)) or np.any(np.abs(y) >= 2**31):
                raise UnsupportedAdapter("classification_requires_bounded_integer_labels")
            if not 2 <= len(np.unique(y)) <= 32:
                raise UnsupportedAdapter("unsupported_class_count")
        data = {"schema_version": "mra-native-tabular-data/v1", "x": x.tolist(), "y": y.tolist(),
                "feature_names": list(feature_names), "task": task}
        data_digest = _write(output / "dataset.json", data)
        plan = _plan(x, y, dataset_id, source_sha256, feature_names, task, seed, data_digest)
        plan_digest = _write(output / "plan.json", plan)
        receipt.update(data_sha256=data_digest, plan_sha256=plan_digest,
                       duplicate_groups=plan.duplicate_groups, conflicting_label_groups=plan.conflicting_label_groups)
        if min(len(plan.train_groups), len(plan.calibration_groups), len(plan.audit_groups)) < MIN_GROUP_TRIALS:
            raise UnsupportedAdapter("insufficient_unique_feature_groups")
        train = np.asarray(plan.train_indices, dtype=int)
        if task == "classification" and not np.array_equal(np.unique(y[train]), np.unique(y)):
            raise UnsupportedAdapter("frozen_training_split_missing_class")
        scaler = StandardScaler().fit(x[train])
        with threadpool_limits(limits=1):
            if task == "classification":
                if not np.any(np.var(scaler.transform(x[train]), axis=0) > 0):
                    raise UnsupportedAdapter("constant_training_features")
                model = GaussianNB(var_smoothing=1e-9).fit(scaler.transform(x[train]), y[train].astype(int))
                parameters = {"kind": "gaussian-nb/v1", "classes": model.classes_.tolist(),
                    "prior": model.class_prior_.tolist(), "theta": model.theta_.tolist(),
                    "variance": model.var_.tolist(), "var_smoothing": 1e-9}
                expected = model.predict_proba(scaler.transform(x))
            else:
                model = Ridge(alpha=1., solver="svd").fit(scaler.transform(x[train]), y[train])
                parameters = {"kind": "ridge/v1", "coefficients": model.coef_.tolist(),
                              "intercept": float(model.intercept_), "alpha": 1.}
                expected = model.predict(scaler.transform(x))
        candidate = NativeCandidate(task=task, dataset_id=dataset_id, source_sha256=source_sha256,
            data_sha256=data_digest, plan_sha256=plan_digest, implementation_sha256=plan.implementation_sha256,
            feature_names=list(feature_names), training_rows=len(train),
            preprocessing={"kind": "standard-scaler/v1", "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()},
            model=parameters, runtime=_runtime(), parents=[])
        _write(output / "candidate.json", candidate)
        raw = _read(output / "candidate.json", 2 * 1024 * 1024)
        replayed = replay_candidate(raw, x)
        if not np.allclose(replayed, expected, rtol=1e-10, atol=1e-10):
            raise ValueError("Inert candidate differs from fitted native model")
        report, scores, predictions = _measure(raw, x, y, plan)
        _write(output / "report.json", report)
        _write(output / "scores.json", scores)
        _write(output / "predictions.json", predictions)
        replay = _replay_run(output, receipt_required=False)
        _write(output / "replay.json", replay)
        if replay["status"] != "passed" or not report["controls_passed"]:
            raise ValueError("Independent numeric replay or scorer controls failed")
        receipt.update(status="completed", candidate_sha256=_sha(raw), utility=report["utility"],
            membership=report["membership"], controls={"passed": True,
                "positive_auc": report["positive_control"]["raw_auc"], "null_auc": report["null_control"]["raw_auc"],
                "scope": report["control_scope"]}, replay=replay,
            reload_max_absolute_error=float(np.max(np.abs(replayed - expected))),
            runtime=_runtime())
    except UnsupportedAdapter as error:
        receipt.update(status="unsupported", reason=str(error))
    except Exception as error:
        receipt.update(status="failed", reason="native_adapter_failed:" + type(error).__name__)
    receipt["elapsed_seconds"] = time.monotonic() - started
    receipt["files"] = {path.name: _sha(_read(path)) for path in sorted(output.iterdir()) if path.is_file()}
    _write(output / "result.json", receipt)
    return receipt

