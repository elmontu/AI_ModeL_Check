"""Hash-bound, trusted-local export screens; never scientific privacy clearance.

The contract records an operator-approved plan and deterministic gate checks. It
cannot authenticate the operator/worker or establish an upper privacy bound.
The native pilot supports one loss-based membership attack on public tabular data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .integrity import canonical_json_bytes, sha256_file

MAX_JSON_BYTES = 2 * 1024 * 1024
NATIVE_TOOL_ID = "native.membership_loss"
NATIVE_TOOL_VERSION = "1.0.0"
INTERFACE = "full_artifact"
CONTROL_PROTOCOL = {
    "version": "membership-probability-controls/v1",
    "positive": "exact-feature-row memorizer: true-label probability .999 for members and .001 for nonmembers",
    "null": "uniform true-label probability .5 for both groups",
    "scorer": "log true-label probability; calibration nonmember .9 quantile; disjoint audit ROC AUC",
    "scope": "end-to-end declared probability/scoring path; not all white-box attacks",
}
LIMITATIONS = [
    "Trusted local operational screen; identities are hashes, not worker authentication or attestation.",
    "Full artifact delivery exposes parameters; the implemented attack uses probabilities and does not cover all white-box attacks.",
    "One fixed loss membership screen only: extraction, attribute inference, poisoning, robustness and language attacks are not covered.",
    "AUC threshold is an illustrative operator decision rule, not a scientific privacy ceiling or release authorization.",
    "Public breast-cancer fixture only; no protected-data registry or privacy budget is created.",
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.-]+$")]
UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, le=10_000_000)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)


def recipient_interface_sha256(interface: str) -> str:
    """Hash the fixed interface descriptor; currently only full_artifact is supported."""
    return hashlib.sha256(interface.encode("utf-8")).hexdigest()


class ExportRedTeamMetricThreshold(_StrictModel):
    metric: Name
    minimum: UnitFloat | None = None
    maximum: UnitFloat | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum is None and self.maximum is None:
            raise ValueError("a threshold requires minimum or maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum exceeds maximum")
        return self


class ExportRedTeamToolRequirement(_StrictModel):
    tool_id: Name
    implementation_version: Name
    implementation_sha256: Digest
    control_protocol_sha256: Digest
    thresholds: Annotated[list[ExportRedTeamMetricThreshold], Field(min_length=1, max_length=32)]
    min_member_records: Annotated[int, Field(ge=20, le=1_000_000)] = 20
    min_nonmember_records: Annotated[int, Field(ge=20, le=1_000_000)] = 20
    positive_control_min_auc: Annotated[float, Field(ge=.9, le=1)] = .9
    null_control_max_auc: Annotated[float, Field(ge=.5, le=.65)] = .65
    max_queries: Annotated[int, Field(ge=1, le=10_000_000)] = 2000
    max_runtime_seconds: Annotated[float, Field(gt=0, le=86400)] = 60.0

    @model_validator(mode="after")
    def unique_metrics(self):
        names = [threshold.metric for threshold in self.thresholds]
        if len(names) != len(set(names)):
            raise ValueError("duplicate metric thresholds")
        return self


class ExportRedTeamPolicy(_StrictModel):
    schema_version: Literal["export-red-team-policy/v1"] = "export-red-team-policy/v1"
    artifact_sha256: Digest
    recipient_interface: Literal["full_artifact"] = INTERFACE
    recipient_interface_sha256: Digest
    # Identity of the attack evaluation data AND split plan, not a DP registry's dataset ID.
    dataset_sha256: Digest
    created_at: AwareDatetime
    expires_at: AwareDatetime
    max_report_age_seconds: Annotated[int, Field(ge=1, le=31_536_000)]
    tools: Annotated[list[ExportRedTeamToolRequirement], Field(min_length=1, max_length=32)]
    can_clear: Literal[False] = False
    authorization_eligible: Literal[False] = False

    @model_validator(mode="after")
    def consistent(self):
        if self.recipient_interface_sha256 != recipient_interface_sha256(self.recipient_interface):
            raise ValueError("recipient interface digest differs from its descriptor")
        if self.expires_at <= self.created_at:
            raise ValueError("policy expiry must follow creation")
        names = [tool.tool_id for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate required tools")
        return self


class ExportRedTeamToolResult(_StrictModel):
    tool_id: Name
    implementation_version: Name
    implementation_sha256: Digest
    control_protocol_sha256: Digest
    status: Literal["completed", "failed", "unsupported", "not_run"]
    metrics: Annotated[dict[Name, UnitFloat], Field(max_length=32)] = Field(default_factory=dict)
    member_records: Count = 0
    nonmember_records: Count = 0
    positive_control_auc: UnitFloat | None = None
    null_control_auc: UnitFloat | None = None
    positive_control_member_records: Count = 0
    positive_control_nonmember_records: Count = 0
    null_control_member_records: Count = 0
    null_control_nonmember_records: Count = 0
    queries_used: Count = 0
    runtime_seconds: Annotated[float, Field(ge=0, le=86400)] = 0.0
    error: Annotated[str, Field(min_length=1, max_length=1000)] | None = None


class ExportRedTeamReport(_StrictModel):
    schema_version: Literal["export-red-team-report/v1"] = "export-red-team-report/v1"
    policy_sha256: Digest
    artifact_sha256: Digest
    recipient_interface_sha256: Digest
    dataset_sha256: Digest
    started_at: AwareDatetime
    completed_at: AwareDatetime
    tools: Annotated[list[ExportRedTeamToolResult], Field(max_length=32)]
    can_clear: Literal[False] = False
    authorization_eligible: Literal[False] = False

    @model_validator(mode="after")
    def consistent(self):
        if self.completed_at < self.started_at:
            raise ValueError("report completion precedes its start")
        names = [tool.tool_id for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate result tools")
        return self


def native_implementation_sha256() -> str:
    """Bind both the native runner and its reused statistical scorer source."""
    paths = (Path(__file__), Path(__file__).with_name("tabular_red_team.py"))
    return hashlib.sha256(canonical_json_bytes({path.name: sha256_file(path) for path in paths})).hexdigest()


def policy_sha256(policy: ExportRedTeamPolicy) -> str:
    return hashlib.sha256(canonical_json_bytes(policy)).hexdigest()


def report_sha256(report: ExportRedTeamReport) -> str:
    return hashlib.sha256(canonical_json_bytes(report)).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _strict_json(raw: str | bytes) -> Any:
    if not isinstance(raw, (str, bytes)):
        raise TypeError("JSON input must be text or bytes")
    if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_JSON_BYTES:
        raise ValueError("red-team JSON exceeds 2 MiB")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except RecursionError as error:
        raise ValueError("red-team JSON nesting is too deep") from error
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise ValueError("red-team JSON nesting exceeds 32 levels")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def parse_policy_json(raw: str | bytes) -> ExportRedTeamPolicy:
    # JSON validation accepts ISO datetime strings while retaining strict numeric types.
    return ExportRedTeamPolicy.model_validate_json(json.dumps(_strict_json(raw), allow_nan=False))


def parse_report_json(raw: str | bytes) -> ExportRedTeamReport:
    return ExportRedTeamReport.model_validate_json(json.dumps(_strict_json(raw), allow_nan=False))


def strict_load_policy(path: str | Path) -> ExportRedTeamPolicy:
    with Path(path).open("rb") as stream:
        return parse_policy_json(stream.read(MAX_JSON_BYTES + 1))


def strict_load_report(path: str | Path) -> ExportRedTeamReport:
    with Path(path).open("rb") as stream:
        return parse_report_json(stream.read(MAX_JSON_BYTES + 1))


def evaluate_export_red_team(
    policy: ExportRedTeamPolicy,
    report: ExportRedTeamReport | None,
    *,
    artifact_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    """Recompute operational satisfaction from bound measurements, never pass flags.

    A satisfied screen can only remove this additional local blocker. All existing
    mechanism, accounting, authorization and delivery checks remain necessary.
    """
    # Revalidate because Pydantic model_copy(update=...) intentionally skips validation
    # and frozen models may still contain mutable nested list/dict objects.
    policy = parse_policy_json(canonical_json_bytes(policy))
    if report is not None:
        report = parse_report_json(canonical_json_bytes(report))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("evaluation time must be timezone-aware")
    reasons: list[str] = []
    if artifact_sha256 != policy.artifact_sha256:
        reasons.append("artifact_digest_mismatch")
    if now < policy.created_at:
        reasons.append("policy_not_yet_valid")
    if now >= policy.expires_at:
        reasons.append("policy_expired")
    if report is None:
        reasons.append("report_missing")
    else:
        for field, expected in (
            ("policy_sha256", policy_sha256(policy)),
            ("artifact_sha256", artifact_sha256),
            ("recipient_interface_sha256", policy.recipient_interface_sha256),
            ("dataset_sha256", policy.dataset_sha256),
        ):
            if getattr(report, field) != expected:
                reasons.append(f"report_{field}_mismatch")
        if report.started_at < policy.created_at:
            reasons.append("report_predates_policy")
        if report.completed_at > now:
            reasons.append("report_from_future")
        if (now - report.completed_at).total_seconds() > policy.max_report_age_seconds:
            reasons.append("report_stale")
        expected_ids = {requirement.tool_id for requirement in policy.tools}
        results = {result.tool_id: result for result in report.tools}
        if set(results) - expected_ids:
            reasons.append("unexpected_tools")
        for requirement in policy.tools:
            prefix = requirement.tool_id
            result = results.get(prefix)
            if result is None:
                reasons.append(f"{prefix}:missing")
                continue
            for field in ("implementation_version", "implementation_sha256", "control_protocol_sha256"):
                if getattr(result, field) != getattr(requirement, field):
                    reasons.append(f"{prefix}:{field}_mismatch")
            if result.status != "completed":
                reasons.append(f"{prefix}:{result.status}")
                continue
            if result.error is not None:
                reasons.append(f"{prefix}:completed_with_error")
            for field, minimum in (
                ("member_records", requirement.min_member_records),
                ("nonmember_records", requirement.min_nonmember_records),
                ("positive_control_member_records", requirement.min_member_records),
                ("positive_control_nonmember_records", requirement.min_nonmember_records),
                ("null_control_member_records", requirement.min_member_records),
                ("null_control_nonmember_records", requirement.min_nonmember_records),
            ):
                if getattr(result, field) < minimum:
                    reasons.append(f"{prefix}:{field}_insufficient")
            if result.positive_control_auc is None or result.positive_control_auc < requirement.positive_control_min_auc:
                reasons.append(f"{prefix}:positive_control_failed")
            # Symmetric around chance: inverted null detection is still a detected signal.
            if result.null_control_auc is None or abs(result.null_control_auc - .5) > requirement.null_control_max_auc - .5 + 1e-12:
                reasons.append(f"{prefix}:null_control_failed")
            min_queries = sum(getattr(result, field) for field in (
                "member_records", "nonmember_records", "positive_control_member_records",
                "positive_control_nonmember_records", "null_control_member_records", "null_control_nonmember_records",
            ))
            if result.queries_used < min_queries or result.queries_used > requirement.max_queries:
                reasons.append(f"{prefix}:query_budget_invalid")
            if result.runtime_seconds <= 0 or result.runtime_seconds > requirement.max_runtime_seconds:
                reasons.append(f"{prefix}:runtime_budget_invalid")
            metrics = {threshold.metric for threshold in requirement.thresholds}
            if set(result.metrics) != metrics:
                reasons.append(f"{prefix}:metric_set_mismatch")
            for threshold in requirement.thresholds:
                value = result.metrics.get(threshold.metric)
                if value is None:
                    continue
                if threshold.metric == "membership_auc":
                    value = max(value, 1 - value)  # Inverted discrimination is also a signal.
                if threshold.minimum is not None and value < threshold.minimum:
                    reasons.append(f"{prefix}:{threshold.metric}:below_minimum")
                if threshold.maximum is not None and value > threshold.maximum:
                    reasons.append(f"{prefix}:{threshold.metric}:above_maximum")
    return {
        "schema_version": "export-red-team-evaluation/v1",
        "satisfied": not reasons,
        "reasons": reasons,
        "policy_sha256": policy_sha256(policy),
        "report_sha256": report_sha256(report) if report is not None else None,
        "artifact_sha256": artifact_sha256,
        "evaluated_at": now.isoformat(),
        "can_clear": False,
        "authorization_eligible": False,
        "interpretation": "trusted local operational screen only; no privacy ceiling or release authorization",
    }


def _write_new_json(path: Path, value: Any) -> None:
    raw = canonical_json_bytes(value) + b"\n"
    with path.open("xb") as stream:
        stream.write(raw)


def _predict_package(package: dict[str, Any], features):
    """Pure numeric inference from an inert package; no pickle/import/callable loading."""
    import numpy as np
    expected = {"schema_version", "model", "preprocessing", "lineage"}
    if set(package) != expected or package["schema_version"] != "public-gaussian-nb-package/v1":
        raise ValueError("unsupported package schema")
    model, preprocessing = package["model"], package["preprocessing"]
    if set(model) != {"type", "classes", "class_prior", "theta", "var"} or model["type"] != "GaussianNB":
        raise ValueError("unsupported model schema")
    if set(preprocessing) != {"type", "mean", "scale", "feature_names"} or preprocessing["type"] != "StandardScaler":
        raise ValueError("unsupported preprocessing schema")
    x = np.asarray(features, dtype=float)
    mean, scale = (np.asarray(preprocessing[key], dtype=float) for key in ("mean", "scale"))
    theta, var, prior = (np.asarray(model[key], dtype=float) for key in ("theta", "var", "class_prior"))
    if x.ndim != 2 or mean.shape != (x.shape[1],) or scale.shape != mean.shape:
        raise ValueError("invalid package feature dimensions")
    if theta.shape != (2, x.shape[1]) or var.shape != theta.shape or prior.shape != (2,):
        raise ValueError("invalid package model dimensions")
    if model["classes"] != [0, 1] or len(preprocessing["feature_names"]) != x.shape[1]:
        raise ValueError("invalid class or feature roster")
    if not all(np.isfinite(value).all() for value in (x, mean, scale, theta, var, prior)):
        raise ValueError("nonfinite package parameters")
    if np.any(scale <= 0) or np.any(var <= 0) or np.any(prior <= 0) or not np.isclose(prior.sum(), 1):
        raise ValueError("invalid package scale, variance or prior")
    x = (x - mean) / scale
    joint = np.log(prior)[None, :] - .5 * np.log(2 * math.pi * var).sum(axis=1)[None, :]
    joint = joint - .5 * (((x[:, None, :] - theta[None, :, :]) ** 2) / var[None, :, :]).sum(axis=2)
    probabilities = np.exp(joint - joint.max(axis=1, keepdims=True))
    return probabilities / probabilities.sum(axis=1, keepdims=True)


def run_public_tabular_demo(output: str | Path) -> dict[str, Any]:
    """Write one new, reproducible public-data reviewer directory; never overwrite."""
    import numpy as np
    import sklearn
    from sklearn.datasets import load_breast_cancer
    from sklearn.model_selection import train_test_split
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler
    from .tabular_red_team import threshold_probe

    output = Path(output)
    # Atomic mkdir prevents retry/parallel callers from modifying an existing bundle.
    output.mkdir(parents=True, exist_ok=False)
    seed = 20261001
    fixture = load_breast_cancer()
    x, y = np.asarray(fixture.data), np.asarray(fixture.target)
    train, holdout = train_test_split(np.arange(len(y)), test_size=.5, stratify=y, random_state=seed)
    raw_data_sha256 = hashlib.sha256(canonical_json_bytes({"x": x.tolist(), "y": y.tolist()})).hexdigest()
    plan = {
        "schema_version": "public-red-team-plan/v1",
        "fixture": "sklearn.datasets.load_breast_cancer (bundled public data)",
        "data_sha256": raw_data_sha256, "seed": seed,
        "training_indices": train.tolist(), "holdout_indices": holdout.tolist(),
        "attack": NATIVE_TOOL_ID, "membership_auc_maximum": .6,
        "membership_auc_semantics": "max(raw audit AUC, 1 - raw audit AUC); inverted discrimination also blocks",
        "calibration": "threshold_probe permutes each group with fixed seed then uses its first half for calibration",
        "audit": "remaining half of each group; no attack or model selection on final audit",
        "control_protocol": CONTROL_PROTOCOL, "stopping_rule": "one predetermined model and attack run",
        "limitations": LIMITATIONS,
    }
    # Freeze all seeds, splits, controls and thresholds before training/outcome inspection.
    _write_new_json(output / "plan.json", plan)
    dataset_digest = hashlib.sha256(canonical_json_bytes(plan)).hexdigest()
    scaler = StandardScaler().fit(x[train])
    model = GaussianNB().fit(scaler.transform(x[train]), y[train])
    package = {
        "schema_version": "public-gaussian-nb-package/v1",
        "model": {"type": "GaussianNB", "classes": model.classes_.tolist(), "class_prior": model.class_prior_.tolist(),
                  "theta": model.theta_.tolist(), "var": model.var_.tolist()},
        "preprocessing": {"type": "StandardScaler", "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                          "feature_names": fixture.feature_names.tolist()},
        "lineage": {"dataset_sha256": dataset_digest, "parents": [], "components": ["StandardScaler", "GaussianNB"],
                    "numpy_version": np.__version__, "scikit_learn_version": sklearn.__version__,
                    "seed": seed, "protected_data": False},
    }
    candidate_path = output / "candidate.json"
    _write_new_json(candidate_path, package)
    artifact_digest = sha256_file(candidate_path)
    # All subsequent attack outputs come from the exact delivered bytes.
    loaded_package = _strict_json(candidate_path.read_bytes())
    reloaded = _predict_package(loaded_package, x)
    original = model.predict_proba(scaler.transform(x))
    reload_error = float(np.max(np.abs(reloaded - original)))
    if not np.allclose(reloaded, original, rtol=1e-12, atol=1e-12):
        raise ValueError("inert package reload changed predictions")
    created = datetime.now(timezone.utc)
    requirement = ExportRedTeamToolRequirement(
        tool_id=NATIVE_TOOL_ID, implementation_version=NATIVE_TOOL_VERSION,
        implementation_sha256=native_implementation_sha256(),
        control_protocol_sha256=hashlib.sha256(canonical_json_bytes(CONTROL_PROTOCOL)).hexdigest(),
        thresholds=[ExportRedTeamMetricThreshold(metric="membership_auc", maximum=plan["membership_auc_maximum"])],
    )
    policy = ExportRedTeamPolicy(
        artifact_sha256=artifact_digest, recipient_interface=INTERFACE,
        recipient_interface_sha256=recipient_interface_sha256(INTERFACE), dataset_sha256=dataset_digest,
        created_at=created, expires_at=created + timedelta(days=1), max_report_age_seconds=86400, tools=[requirement],
    )
    _write_new_json(output / "policy.json", policy)
    started = datetime.now(timezone.utc)
    monotonic_started = time.perf_counter()

    def score(predictor):
        values = []
        for indices in (train, holdout):
            probabilities = predictor(x[indices], y[indices])
            values.append(np.log(np.clip(probabilities[np.arange(len(indices)), y[indices]], 1e-12, 1)))
        return threshold_probe(*values, seed)

    target = score(lambda features, labels: _predict_package(loaded_package, features))
    training_rows = {row.tobytes() for row in x[train]}
    if training_rows.intersection(row.tobytes() for row in x[holdout]):
        raise ValueError("feature duplicates would invalidate the declared known-leak control")

    def leaking_predictor(features, labels):
        probabilities = np.empty((len(features), 2))
        for index, (row, label) in enumerate(zip(features, labels)):
            correct = .999 if row.tobytes() in training_rows else .001
            probabilities[index, label] = correct
            probabilities[index, 1 - label] = 1 - correct
        return probabilities

    positive = score(leaking_predictor)
    null = score(lambda features, labels: np.full((len(features), 2), .5))
    elapsed = time.perf_counter() - monotonic_started
    result = ExportRedTeamToolResult(
        tool_id=requirement.tool_id, implementation_version=requirement.implementation_version,
        implementation_sha256=requirement.implementation_sha256, control_protocol_sha256=requirement.control_protocol_sha256,
        status="completed", metrics={"membership_auc": max(target["auc"], 1 - target["auc"])},
        member_records=target["member_trials"], nonmember_records=target["nonmember_trials"],
        positive_control_auc=positive["auc"], null_control_auc=null["auc"],
        positive_control_member_records=positive["member_trials"], positive_control_nonmember_records=positive["nonmember_trials"],
        null_control_member_records=null["member_trials"], null_control_nonmember_records=null["nonmember_trials"],
        queries_used=3 * len(y), runtime_seconds=elapsed,
    )
    report = ExportRedTeamReport(
        policy_sha256=policy_sha256(policy), artifact_sha256=artifact_digest,
        recipient_interface_sha256=policy.recipient_interface_sha256, dataset_sha256=dataset_digest,
        started_at=started, completed_at=datetime.now(timezone.utc), tools=[result],
    )
    _write_new_json(output / "report.json", report)
    now = datetime.now(timezone.utc)
    evaluation = evaluate_export_red_team(policy, report, artifact_sha256=sha256_file(candidate_path), now=now)
    _write_new_json(output / "evaluation.json", evaluation)
    receipt = {
        "schema_version": "public-red-team-reviewer-receipt/v1",
        "artifact_sha256": artifact_digest, "policy_sha256": policy_sha256(policy), "report_sha256": report_sha256(report),
        "dataset_sha256": dataset_digest, "reload_max_probability_error": reload_error,
        "holdout_accuracy": float(np.mean(reloaded[holdout].argmax(axis=1) == y[holdout])),
        "target": target, "positive_control": positive, "null_control": null,
        "evaluation": evaluation, "limitations": LIMITATIONS,
        "runtime": {"python": sys.version.split()[0], "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "files": {path.name: sha256_file(path) for path in sorted(output.iterdir()) if path.is_file()},
        "can_clear": False, "authorization_eligible": False,
    }
    _write_new_json(output / "reviewer-receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the single supported public tabular membership screen")
    demo.add_argument("--output", required=True, type=Path)
    evaluate = commands.add_parser("evaluate", help="check a bound trusted-local policy/report against exact artifact bytes")
    evaluate.add_argument("--policy", required=True, type=Path)
    evaluate.add_argument("--report", required=True, type=Path)
    evaluate.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_public_tabular_demo(args.output)["evaluation"]
        else:
            result = evaluate_export_red_team(strict_load_policy(args.policy), strict_load_report(args.report),
                                              artifact_sha256=sha256_file(args.artifact), now=datetime.now(timezone.utc))
    except (OSError, ValueError, TypeError, ImportError) as error:
        print(json.dumps({"satisfied": False, "reasons": [str(error)], "can_clear": False, "authorization_eligible": False}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["satisfied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


