"""Typed inert contracts for bounded native tabular adapter fixtures."""
from __future__ import annotations

import json
import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_ROWS = 4096
MAX_FEATURES = 128
MAX_CLASSES = 32
MAX_JSON_BYTES = 32 * 1024 * 1024
ADAPTER_ID = "native.tabular-loss/v1"
ADAPTER_VERSION = "1.0.0"
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=128)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Index = Annotated[int, Field(ge=0, lt=MAX_ROWS)]
Task = Literal["classification", "regression"]
Status = Literal["completed", "unsupported", "failed", "timed_out", "not_run"]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class StandardScalerParameters(StrictContract):
    kind: Literal["standard-scaler/v1"] = "standard-scaler/v1"
    mean: list[Finite] = Field(min_length=1, max_length=MAX_FEATURES)
    scale: list[Finite] = Field(min_length=1, max_length=MAX_FEATURES)

    @model_validator(mode="after")
    def positive_scale(self):
        if len(self.mean) != len(self.scale) or any(value <= 0 for value in self.scale):
            raise ValueError("Scaler dimensions and positive scale are required")
        return self


class GaussianNBParameters(StrictContract):
    kind: Literal["gaussian-nb/v1"] = "gaussian-nb/v1"
    classes: list[Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]] = Field(min_length=2, max_length=MAX_CLASSES)
    prior: list[Finite] = Field(min_length=2, max_length=MAX_CLASSES)
    theta: list[list[Finite]] = Field(min_length=2, max_length=MAX_CLASSES)
    variance: list[list[Finite]] = Field(min_length=2, max_length=MAX_CLASSES)
    var_smoothing: Literal[1e-9] = 1e-9

    @model_validator(mode="after")
    def dimensions(self):
        k = len(self.classes)
        if (len(set(self.classes)) != k or self.classes != sorted(self.classes)
                or len(self.prior) != k or len(self.theta) != k or len(self.variance) != k):
            raise ValueError("Unique ordered classes and aligned parameters are required")
        widths = {len(row) for row in [*self.theta, *self.variance]}
        if len(widths) != 1 or not 1 <= next(iter(widths)) <= MAX_FEATURES:
            raise ValueError("Gaussian parameter dimensions are invalid")
        if any(value <= 0 for value in self.prior) or not math.isclose(sum(self.prior), 1., rel_tol=0., abs_tol=1e-12):
            raise ValueError("Normalized positive class priors are required")
        if any(value <= 0 for row in self.variance for value in row):
            raise ValueError("Positive Gaussian variances are required")
        return self


class RidgeParameters(StrictContract):
    kind: Literal["ridge/v1"] = "ridge/v1"
    coefficients: list[Finite] = Field(min_length=1, max_length=MAX_FEATURES)
    intercept: Finite
    alpha: Literal[1.0] = 1.0


class NativeCandidate(StrictContract):
    schema_version: Literal["mra-native-tabular-candidate/v1"] = "mra-native-tabular-candidate/v1"
    adapter_id: Literal["native.tabular-loss/v1"] = ADAPTER_ID
    adapter_version: Literal["1.0.0"] = ADAPTER_VERSION
    task: Task
    dataset_id: Name
    source_sha256: Digest
    data_sha256: Digest
    plan_sha256: Digest
    implementation_sha256: Digest
    feature_names: list[Name] = Field(min_length=1, max_length=MAX_FEATURES)
    training_rows: Annotated[int, Field(ge=1, le=MAX_ROWS)]
    preprocessing: StandardScalerParameters
    model: Annotated[Union[GaussianNBParameters, RidgeParameters], Field(discriminator="kind")]
    runtime: dict[str, str]
    parents: list[Digest] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def context(self):
        width = len(self.feature_names)
        if (len(set(self.feature_names)) != width or any(any(ord(c) < 32 for c in name) for name in self.feature_names)
                or len(self.preprocessing.mean) != width):
            raise ValueError("Unique feature roster must match preprocessing")
        if self.task == "classification":
            if not isinstance(self.model, GaussianNBParameters) or len(self.model.theta[0]) != width:
                raise ValueError("Classification requires aligned GaussianNB parameters")
        elif not isinstance(self.model, RidgeParameters) or len(self.model.coefficients) != width:
            raise ValueError("Regression requires aligned ridge parameters")
        if set(self.runtime) != {"python", "numpy", "scipy", "scikit-learn"} or any(
                not 1 <= len(value) <= 128 for value in self.runtime.values()):
            raise ValueError("Exact bounded runtime roster is required")
        return self


class FeatureGroup(StrictContract):
    feature_sha256: Digest
    rows: list[Index] = Field(min_length=1, max_length=MAX_ROWS)


class NativePlan(StrictContract):
    schema_version: Literal["mra-native-tabular-plan/v1"] = "mra-native-tabular-plan/v1"
    adapter_id: Literal["native.tabular-loss/v1"] = ADAPTER_ID
    adapter_version: Literal["1.0.0"] = ADAPTER_VERSION
    task: Task
    dataset_id: Name
    source_sha256: Digest
    data_sha256: Digest
    implementation_sha256: Digest
    feature_names: list[Name] = Field(min_length=1, max_length=MAX_FEATURES)
    seed: Annotated[int, Field(ge=0, le=2**32 - 1)]
    groups: list[FeatureGroup] = Field(min_length=1, max_length=MAX_ROWS)
    train_groups: list[Index] = Field(max_length=MAX_ROWS)
    calibration_groups: list[Index] = Field(max_length=MAX_ROWS)
    audit_groups: list[Index] = Field(max_length=MAX_ROWS)
    train_indices: list[Index] = Field(max_length=MAX_ROWS)
    calibration_indices: list[Index] = Field(max_length=MAX_ROWS)
    audit_indices: list[Index] = Field(max_length=MAX_ROWS)
    duplicate_groups: Annotated[int, Field(ge=0, le=MAX_ROWS)]
    conflicting_label_groups: Annotated[int, Field(ge=0, le=MAX_ROWS)]
    model_recipe: Literal["standard-scaler+gaussian-nb-1e-9/v1", "standard-scaler+ridge-alpha1-svd/v1"]
    regression_control_targets: Literal["synthetic-zero-targets-exact-zero-or-unit-residual"] = "synthetic-zero-targets-exact-zero-or-unit-residual"
    metric_unit: Literal["mean-loss-per-identical-feature-group"] = "mean-loss-per-identical-feature-group"
    calibration_quantile: Literal[0.9] = 0.9
    confidence: Literal[0.95] = 0.95
    control_protocol: Literal["label-aware-scorer-oracles/v1"] = "label-aware-scorer-oracles/v1"
    positive_control_min_auc: Literal[0.9] = 0.9
    null_control_auc: Literal[0.5] = 0.5
    bootstrap_iterations: Literal[0] = 0
    stopping_rule: Literal["one-frozen-split-one-fit-no-outcome-selection"] = "one-frozen-split-one-fit-no-outcome-selection"

    @model_validator(mode="after")
    def splits(self):
        expected_recipe = ("standard-scaler+gaussian-nb-1e-9/v1" if self.task == "classification"
                           else "standard-scaler+ridge-alpha1-svd/v1")
        if self.model_recipe != expected_recipe:
            raise ValueError("Task and frozen model recipe differ")
        if (len(set(self.feature_names)) != len(self.feature_names)
                or any(any(ord(c) < 32 for c in name) for name in self.feature_names)):
            raise ValueError("Unique printable feature names are required")
        if (self.duplicate_groups != sum(len(group.rows) > 1 for group in self.groups)
                or self.conflicting_label_groups > self.duplicate_groups):
            raise ValueError("Duplicate group counts are inconsistent")
        ids = [*self.train_groups, *self.calibration_groups, *self.audit_groups]
        if sorted(ids) != list(range(len(self.groups))) or len({group.feature_sha256 for group in self.groups}) != len(self.groups):
            raise ValueError("Groups must be unique and partitioned exactly once")
        rows = [row for group in self.groups for row in group.rows]
        if sorted(rows) != list(range(len(rows))) or len(rows) > MAX_ROWS:
            raise ValueError("Groups must cover each bounded row exactly once")
        for group_ids, indices in ((self.train_groups, self.train_indices),
                                   (self.calibration_groups, self.calibration_indices),
                                   (self.audit_groups, self.audit_indices)):
            if indices != sorted(row for index in group_ids for row in self.groups[index].rows):
                raise ValueError("Explicit indices must match whole-group partitions")
        return self


class MembershipMetrics(StrictContract):
    raw_auc: Annotated[float, Field(ge=0, le=1)]
    symmetric_auc: Annotated[float, Field(ge=.5, le=1)]
    threshold: Finite
    threshold_comparison: Literal["strict_greater"]
    calibration_target_fpr: Literal[.1]
    member_group_trials: Annotated[int, Field(ge=20, le=MAX_ROWS)]
    calibration_group_trials: Annotated[int, Field(ge=20, le=MAX_ROWS)]
    nonmember_group_trials: Annotated[int, Field(ge=20, le=MAX_ROWS)]
    true_positives: Annotated[int, Field(ge=0, le=MAX_ROWS)]
    false_positives: Annotated[int, Field(ge=0, le=MAX_ROWS)]
    tpr: Annotated[float, Field(ge=0, le=1)]
    fpr: Annotated[float, Field(ge=0, le=1)]
    tpr_interval_95: list[Annotated[float, Field(ge=0, le=1)]] = Field(min_length=2, max_length=2)
    fpr_interval_95: list[Annotated[float, Field(ge=0, le=1)]] = Field(min_length=2, max_length=2)
    interval_assumption: Literal["conditional_independent_group_trials_not_population_or_privacy_validation"]
    auc_uncertainty: Literal["not_estimated"]

    @model_validator(mode="after")
    def counts(self):
        if (self.true_positives > self.member_group_trials or self.false_positives > self.nonmember_group_trials
                or self.tpr != self.true_positives / self.member_group_trials
                or self.fpr != self.false_positives / self.nonmember_group_trials
                or self.symmetric_auc != max(self.raw_auc, 1 - self.raw_auc)):
            raise ValueError("Membership counts/rates are inconsistent")
        for rate, interval in ((self.tpr, self.tpr_interval_95), (self.fpr, self.fpr_interval_95)):
            if not interval[0] <= rate <= interval[1]:
                raise ValueError("Membership interval excludes the observed rate")
        return self


class ClassificationUtility(StrictContract):
    task: Literal["classification"]
    records: Annotated[int, Field(ge=1, le=MAX_ROWS)]
    accuracy: Annotated[float, Field(ge=0, le=1)]
    balanced_accuracy: Annotated[float, Field(ge=0, le=1)]
    log_loss: Annotated[float, Field(ge=0)]
    majority_accuracy: Annotated[float, Field(ge=0, le=1)]
    majority_class: Finite


class RegressionUtility(StrictContract):
    task: Literal["regression"]
    records: Annotated[int, Field(ge=1, le=MAX_ROWS)]
    rmse: Annotated[float, Field(ge=0)]
    mae: Annotated[float, Field(ge=0)]
    r2: Finite | None
    training_mean_baseline_rmse: Annotated[float, Field(ge=0)]


class NativeReport(StrictContract):
    schema_version: Literal["mra-native-tabular-report/v1"]
    task: Task
    candidate_sha256: Digest
    plan_sha256: Digest
    data_sha256: Digest
    metric_unit: Literal["mean-loss-per-identical-feature-group"]
    utility: Annotated[Union[ClassificationUtility, RegressionUtility], Field(discriminator="task")]
    membership: MembershipMetrics
    positive_control: MembershipMetrics
    null_control: MembershipMetrics
    controls_passed: bool
    scoring_rows: Annotated[int, Field(ge=1, le=MAX_ROWS)]
    control_scope: Literal["label-aware public scorer-path oracles; not realistic estimators"]
    fixture_only: Literal[True]
    can_clear: Literal[False]
    authorization_eligible: Literal[False]
    production_authorized: Literal[False]
    model_delivery: Literal[False]
    hostile_code_isolated: Literal[False]
    network_isolated: Literal[False]

    @model_validator(mode="after")
    def derived_controls(self):
        expected = (self.positive_control.raw_auc >= .9 and abs(self.null_control.raw_auc - .5) <= 1e-12
                    and self.positive_control.tpr == 1. and self.positive_control.fpr == 0.)
        if self.task != self.utility.task or self.controls_passed is not expected:
            raise ValueError("Report task/control outcome is inconsistent")
        return self


def canonical_bytes(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def strict_json(raw, *, maximum=MAX_JSON_BYTES):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ValueError("Expected bounded JSON bytes")
    def constant(_):
        raise ValueError("Nonfinite JSON is forbidden")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=constant)
        def check_depth(item, depth=0):
            if depth > 24:
                raise ValueError("JSON nesting is too deep")
            if type(item) is float and not math.isfinite(item):
                raise ValueError("Nonfinite JSON is forbidden")
            if type(item) is dict:
                for child in item.values():
                    check_depth(child, depth + 1)
            elif type(item) is list:
                for child in item:
                    check_depth(child, depth + 1)
        check_depth(value)
        return value
    except (RecursionError, UnicodeError) as error:
        raise ValueError("Invalid bounded JSON") from error


def parse_candidate(raw):
    value = strict_json(raw, maximum=2 * 1024 * 1024)
    candidate = NativeCandidate.model_validate(value)
    # Stored artifacts must carry every version/parameter field explicitly.
    if canonical_bytes(value) != canonical_bytes(candidate):
        raise ValueError("Candidate must use the complete canonical typed shape")
    return candidate


def parse_plan(raw):
    value = strict_json(raw)
    plan = NativePlan.model_validate(value)
    if canonical_bytes(value) != canonical_bytes(plan):
        raise ValueError("Plan must use the complete canonical typed shape")
    return plan

