"""Prospective public-fixture registration and non-authorizing utility review.

The trusted workflow must persist registration before fitting and authenticate
its later execution. These pure contracts alone neither prove that ordering nor
approve a population, protected unit, mechanism or model release.
"""
from __future__ import annotations

import hashlib
import math
import re

from ..production_evidence import contracts as evidence
from ..production_evidence.replay import artifact_manifest, replay_native_bundle
from ..production_evidence.verifier import runtime_observation
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes as native_bytes, parse_plan, strict_json as native_json
from .profiles import profile_descriptor

FLAGS = {"fixture_only": True, "authorization_eligible": False, "production_authorized": False,
         "model_delivery": False, "can_clear": False, "scientific_evidence_qualified": False}
BLOCK_REASONS = (
    "non_dp_mechanism", "protected_unit_unjustified", "population_unqualified",
    "external_history_unreconciled", "agency_approval_pending", "production_isolation_unverified",
    "historical_audit_reuse", "upstream_preprocessing_unqualified",
)
_SCHEMA = "mra-prospective-native-registration/v1"
_REVIEW_SCHEMA = "mra-native-registration-review/v1"
_ID = re.compile(r"[0-9a-f]{32}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_TOP = frozenset({"schema", "environment", "operation", "registration_id", "agency_id", "project_id",
    "case_id", "profile_id", "source", "plan", "lineage", "population", "mechanism", "utility",
    "recipient", "history", *FLAGS})
_SOURCE = frozenset({"dataset_id", "source_sha256", "data_sha256", "metadata_sha256", "metadata",
    "profile_descriptor_sha256", "profile_descriptor", "task", "feature_names"})
_PLAN = frozenset({"plan_sha256", "seed", "model_recipe", "adapter_id", "adapter_version",
    "adapter_implementation_sha256", "workflow_sha256", "runtime_sha256", "rows", "features",
    "feature_groups", "train_rows", "calibration_rows", "audit_rows", "train_groups",
    "calibration_groups", "audit_groups", "metric_unit", "control_protocol", "stopping_rule"})
_HISTORY = frozenset({"ledger_id", "scope_id", "sequence", "head_sha256", "local_registrations",
    "known_disclosures", "external_history", "privacy_accounting_supported"})
_COMMON_METADATA = frozenset({"profile_id", "profile_source_kind", "local_public_fixture_pin_verified",
    "pin_observation", "authenticated_upstream_provenance", "current_license_approval",
    "historical_training_data_reused", "fresh_audit_evidence", "person_level_disjointness_established",
    "disclosure_history_complete", "private_data_admitted", "authorization_eligible", "production_authorized",
    "model_delivery", "upstream_preprocessing"})
_BUNDLED_METADATA = frozenset({"schema", "source", "loader", "sklearn_version", "available_rows",
    "selected_rows", "selection", "selection_indices_sha256", "full_fixture_sha256", "selected_matrix_sha256",
    "features", "private_data", "historically_untouched_data_claim", "production_license_approval"})
_RESEARCH_METADATA = frozenset({"schema", "corpus", "task", "source_kind", "source_bytes",
    "source_relative_path", "manifest_relative_path", "manifest_sha256", "source_rows", "selected_rows",
    "feature_count", "selection_seed", "selection", "selection_indices_sha256", "sampled_matrix_sha256",
    "source_array_shapes", "source_array_dtypes", "returned_covariates", "omitted_fields",
    "manifest_receipt_hash_matches", "upstream_receipts_rehashed", "historical_training_data_reused",
    "fresh_audit_evidence", "person_level_disjointness_established", "authorization_eligible",
    "production_authorized", "model_delivery", "limitations"})


class RegistrationError(ValueError):
    """Generic payload-free registration/review failure."""


def _fail():
    raise RegistrationError("Public fixture registration rejected")


def canonical_bytes(value):
    try:
        return evidence.canonical_bytes(value)
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json(raw, max_bytes=65536):
    try:
        if type(max_bytes) is not int or not 1 <= max_bytes <= 65536:
            _fail()
        return evidence.strict_json(raw, max_bytes=max_bytes)
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None


def _owned(value, fields):
    if type(value) is not dict or set(value) != fields:
        _fail()
    return strict_json(canonical_bytes(value))


def _same(value, expected):
    if canonical_bytes(value) != canonical_bytes(expected):
        _fail()


def _int(value, minimum=0, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _sha(value):
    try:
        return evidence.validate_digest(value)
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None


def _name(value):
    if type(value) is not str or not _NAME.fullmatch(value):
        _fail()
    return value


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail()
    return value


def _text(value, maximum=512):
    if type(value) is not str or not 1 <= len(value) <= maximum or any(ord(char) < 32 for char in value):
        _fail()
    return value


def _upstream(profile):
    if profile["source_kind"] == "research_prepared":
        return "Historical prepared covariates; upstream transformations are not independently reconstructed."
    if profile["id"] == "sklearn-diabetes":
        return "Diabetes bundled scaled=True uses full-cohort centering and scaling before this benchmark split."
    return "Fixed scikit-learn bundled representation; upstream source preparation is not independently audited."


def _metadata(value, profile, rows, features):
    research = profile["source_kind"] == "research_prepared"
    result = _owned(value, _COMMON_METADATA | (_RESEARCH_METADATA if research else _BUNDLED_METADATA))
    fixed = {"profile_id": profile["id"], "profile_source_kind": profile["source_kind"],
        "local_public_fixture_pin_verified": True, "pin_observation": "prd11-adapters-20261001",
        "authenticated_upstream_provenance": False, "current_license_approval": False,
        "historical_training_data_reused": True, "fresh_audit_evidence": False,
        "person_level_disjointness_established": False, "disclosure_history_complete": False,
        "private_data_admitted": False, "authorization_eligible": False, "production_authorized": False,
        "model_delivery": False, "upstream_preprocessing": _upstream(profile), "selected_rows": rows}
    _sha(result["selection_indices_sha256"])
    if research:
        fixed.update(schema="mra-research-dataset/v1", corpus=profile["id"], task="binary_classification",
            source_kind="historical_public_research_matrix", feature_count=features, selection_seed=20261001,
            selection="fixed_seed_permutation_of_all_rows_before_target_inspection", returned_covariates="B only",
            omitted_fields=["z", "keys", "strata", "source_panel", "source_row_indices"],
            manifest_receipt_hash_matches=True, upstream_receipts_rehashed=False,
            manifest_sha256=profile["expected_manifest_sha256"],
            source_relative_path=f"experiments/mixed-model-export-20260929-v1/{profile['id']}/data/data.npz",
            manifest_relative_path=f"experiments/mixed-model-export-20260929-v1/{profile['id']}/data/manifest.json")
        _int(result["source_bytes"], 1, 16 * 1024 * 1024)
        _int(result["source_rows"], rows, 200000)
        _sha(result["sampled_matrix_sha256"])
        shapes, dtypes = result["source_array_shapes"], result["source_array_dtypes"]
        if (type(shapes) is not dict or not 2 <= len(shapes) <= 32 or type(dtypes) is not dict
                or set(shapes) != set(dtypes) or not {"B", "y"} <= set(shapes)):
            _fail()
        for key, shape in shapes.items():
            _name(key)
            if type(shape) is not list or not 1 <= len(shape) <= 4:
                _fail()
            for count in shape:
                _int(count, 1, 200000)
            _text(dtypes[key], 64)
        _same(shapes["B"], [result["source_rows"], features])
        _same(shapes["y"], [result["source_rows"]])
        if type(result["limitations"]) is not list or not 1 <= len(result["limitations"]) <= 8:
            _fail()
        for note in result["limitations"]:
            _text(note)
    else:
        fixed.update(schema="bundled-dataset-observation/v1", source="scikit-learn bundled fixture",
            loader=profile["id"], sklearn_version="1.6.1", features=features,
            selection="fixed20261001 permutation before label inspection",
            full_fixture_sha256=profile["expected_source_sha256"], private_data=False,
            historically_untouched_data_claim=False, production_license_approval=False)
        _int(result["available_rows"], rows, 4096)
        _sha(result["selected_matrix_sha256"])
    for key, expected in fixed.items():
        _same(result[key], expected)
    return result


def _history(value, agency_id, project_id):
    result = _owned(value, _HISTORY)
    _id(result["ledger_id"])
    for key in ("scope_id", "head_sha256"):
        _sha(result[key])
    _same(result["scope_id"], digest({"agency_id": agency_id, "project_id": project_id}))
    sequence = _int(result["sequence"])
    _int(result["local_registrations"], 0, sequence)
    _int(result["known_disclosures"], 0, sequence)
    _same(result["external_history"], "unknown")
    _same(result["privacy_accounting_supported"], False)
    return result


def _utility(task):
    return {"scope": "descriptive_engineering_no_agency_criterion_or_scientific_proof", "task": task,
        "metric": "accuracy" if task == "classification" else "rmse",
        "comparator": "training_majority_accuracy" if task == "classification" else "training_mean_baseline_rmse",
        "improvement": "candidate_minus_comparator" if task == "classification" else "comparator_minus_candidate",
        "criterion": "strict_improvement_gt_zero", "threshold": 0.0,
        "evaluation_partition": "frozen_calibration_plus_audit_rows", "subgroups_qualified": False,
        "agency_criterion_approved": False, "outcome_selection_allowed": False}


def _population(rows, groups, profile):
    return {"scope": "public_numeric_snapshot_only", "records": rows, "feature_groups": groups,
        "measurement_unit": "mean-loss-per-identical-feature-group", "protected_unit": None,
        "contribution_bound": None, "feature_group_is_privacy_unit": False,
        "person_level_disjointness_established": False, "fresh_audit_evidence": False,
        "representativeness_established": False, "historical_training_data_reused": True,
        "upstream_preprocessing": _upstream(profile), "upstream_preprocessing_qualified": False}


def _plan_summary(plan, plan_bytes, workflow_sha256, runtime_sha256):
    return {"plan_sha256": hashlib.sha256(plan_bytes).hexdigest(), "seed": plan.seed,
        "model_recipe": plan.model_recipe, "adapter_id": plan.adapter_id, "adapter_version": plan.adapter_version,
        "adapter_implementation_sha256": plan.implementation_sha256,
        "workflow_sha256": workflow_sha256, "runtime_sha256": runtime_sha256,
        "rows": sum(len(group.rows) for group in plan.groups), "features": len(plan.feature_names),
        "feature_groups": len(plan.groups), "train_rows": len(plan.train_indices),
        "calibration_rows": len(plan.calibration_indices), "audit_rows": len(plan.audit_indices),
        "train_groups": len(plan.train_groups), "calibration_groups": len(plan.calibration_groups),
        "audit_groups": len(plan.audit_groups), "metric_unit": plan.metric_unit,
        "control_protocol": plan.control_protocol, "stopping_rule": plan.stopping_rule}


def validate_registration(value):
    try:
        result = _owned(value, _TOP)
        _same(result["schema"], _SCHEMA)
        _same(result["environment"], "public_fixture")
        _same(result["operation"], "fresh_native_training")
        _id(result["registration_id"])
        for key in ("agency_id", "project_id", "case_id", "profile_id"):
            _name(result[key])
        profile = profile_descriptor(result["profile_id"])
        source = result["source"] = _owned(result["source"], _SOURCE)
        plan = result["plan"] = _owned(result["plan"], _PLAN)
        _same(source["profile_descriptor"], profile)
        _same(source["profile_descriptor_sha256"], digest(profile))
        _same(source["source_sha256"], profile["expected_source_sha256"])
        _same(source["task"], profile["task"])
        expected_dataset_id = ("research." + profile["id"] + ".mixed-model-export-20260929-v1"
                               if profile["source_kind"] == "research_prepared" else profile["id"])
        _same(source["dataset_id"], expected_dataset_id)
        for key in ("source_sha256", "data_sha256", "metadata_sha256", "profile_descriptor_sha256"):
            _sha(source[key])
        for key in ("plan_sha256", "adapter_implementation_sha256", "workflow_sha256", "runtime_sha256"):
            _sha(plan[key])
        _int(plan["seed"], 0, 2**32 - 1)
        rows = _int(plan["rows"], 128, 4096)
        width = _int(plan["features"], 1, 128)
        groups = _int(plan["feature_groups"], 1, rows)
        row_counts = [_int(plan[name + "_rows"], 1, rows) for name in ("train", "calibration", "audit")]
        group_counts = [_int(plan[name + "_groups"], 1, groups) for name in ("train", "calibration", "audit")]
        if sum(row_counts) != rows or sum(group_counts) != groups or any(a < b for a, b in zip(row_counts, group_counts)):
            _fail()
        names = source["feature_names"]
        if type(names) is not list or len(names) != width or len(set(names)) != width:
            _fail()
        for name in names:
            _text(name, 128)
        metadata = source["metadata"] = _metadata(source["metadata"], profile, rows, width)
        _same(source["metadata_sha256"], digest(metadata))
        for key, expected in {"adapter_id": native.ADAPTER_ID, "adapter_version": native.ADAPTER_VERSION,
            "model_recipe": "standard-scaler+gaussian-nb-1e-9/v1" if source["task"] == "classification" else "standard-scaler+ridge-alpha1-svd/v1",
            "metric_unit": "mean-loss-per-identical-feature-group", "control_protocol": "label-aware-scorer-oracles/v1",
            "stopping_rule": "one-frozen-split-one-fit-no-outcome-selection"}.items():
            _same(plan[key], expected)
        _same(result["lineage"], {"mode": "fresh_native_training", "parents": [], "external_import": False,
            "components": ["train_partition_fitted_standard_scaler", plan["model_recipe"]]})
        _same(result["population"], _population(rows, groups, profile))
        _same(result["mechanism"], {"kind": "nonprivate_fixed_native", "protection_claim": "none",
            "epsilon": None, "delta": None, "accountant": None, "adjacency": None, "privacy_budget_supported": False})
        _same(result["utility"], _utility(source["task"]))
        _same(result["recipient"], {"intended_recipient": "unassigned", "interface": "full_numeric_artifact",
            "actual_delivery": "none", "agency_approval": "pending"})
        result["history"] = _history(result["history"], result["agency_id"], result["project_id"])
        for key, expected in FLAGS.items():
            _same(result[key], expected)
        return result
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None


def _sample_binding(x, y, source):
    """Recompute deterministic selected-matrix/row-selection metadata, not upstream custody."""
    import numpy as np
    metadata = source["metadata"]
    if source["task"] == "classification":
        if not np.array_equal(y, np.rint(y)) or not 2 <= len(np.unique(y)) <= 32:
            _fail()
        selected_y = y.astype(np.int64)
    else:
        selected_y = y
    research = source["profile_descriptor"]["source_kind"] == "research_prepared"
    count = metadata["source_rows"] if research else metadata["available_rows"]
    indices = np.random.default_rng(20261001).permutation(count)[:len(y)]
    if research:
        if set(np.unique(y).tolist()) != {0., 1.}:
            _fail()
        indices_bytes = indices.astype("<u8", copy=False).tobytes()
        description = native_bytes({"schema": "mra-research-matrix/v1", "features": source["feature_names"],
            "x_shape": list(x.shape), "x_dtype": "<f8", "y_shape": list(y.shape), "y_dtype": "|u1"})
        expected = hashlib.sha256(description + b"\n" + indices_bytes + np.asarray(x, dtype="<f8", order="C").tobytes()
                                  + np.asarray(y, dtype="u1", order="C").tobytes()).hexdigest()
        _same(metadata["sampled_matrix_sha256"], expected)
        _same(metadata["selection_indices_sha256"], hashlib.sha256(indices_bytes).hexdigest())
    else:
        _same(metadata["selected_matrix_sha256"], hashlib.sha256(native_bytes({"x": x.tolist(), "y": selected_y.tolist()})).hexdigest())
        _same(metadata["selection_indices_sha256"], hashlib.sha256(native_bytes(indices.tolist())).hexdigest())


def build_registration(*, registration_id, agency_id, project_id, case_id, profile_id, data,
                       data_bytes, plan_bytes, history, workflow_sha256, runtime_sha256):
    try:
        if type(data) is not dict or set(data) != {"x", "y", "feature_names", "dataset_id", "source_sha256", "metadata", "profile_id", "task"}:
            _fail()
        profile = profile_descriptor(profile_id)
        _same(data["profile_id"], profile_id)
        _same(data["task"], profile["task"])
        _sha(workflow_sha256)
        _sha(runtime_sha256)
        _same(runtime_sha256, digest(runtime_observation()))
        x, y = native._arrays(data["x"], data["y"])
        expected_data = {"schema_version": "mra-native-tabular-data/v1", "x": x.tolist(), "y": y.tolist(),
                         "feature_names": data["feature_names"], "task": data["task"]}
        if type(data_bytes) is not bytes or data_bytes != native_bytes(expected_data) + b"\n":
            _fail()
        plan = parse_plan(plan_bytes)
        if plan_bytes != native_bytes(plan) + b"\n":
            _fail()
        expected_plan = native._plan(x, y, data["dataset_id"], data["source_sha256"], data["feature_names"],
                                     data["task"], plan.seed, hashlib.sha256(data_bytes).hexdigest())
        if native_bytes(plan) != native_bytes(expected_plan):
            _fail()
        source = {"dataset_id": data["dataset_id"], "source_sha256": data["source_sha256"],
            "data_sha256": hashlib.sha256(data_bytes).hexdigest(), "metadata": data["metadata"],
            "metadata_sha256": digest(data["metadata"]), "profile_descriptor": profile,
            "profile_descriptor_sha256": digest(profile), "task": data["task"], "feature_names": data["feature_names"]}
        summary = _plan_summary(plan, plan_bytes, workflow_sha256, runtime_sha256)
        result = {"schema": _SCHEMA, "environment": "public_fixture", "operation": "fresh_native_training",
            "registration_id": registration_id, "agency_id": agency_id, "project_id": project_id,
            "case_id": case_id, "profile_id": profile_id, "source": source, "plan": summary,
            "lineage": {"mode": "fresh_native_training", "parents": [], "external_import": False,
                        "components": ["train_partition_fitted_standard_scaler", plan.model_recipe]},
            "population": _population(summary["rows"], summary["feature_groups"], profile),
            "mechanism": {"kind": "nonprivate_fixed_native", "protection_claim": "none", "epsilon": None,
                          "delta": None, "accountant": None, "adjacency": None, "privacy_budget_supported": False},
            "utility": _utility(data["task"]), "recipient": {"intended_recipient": "unassigned",
                "interface": "full_numeric_artifact", "actual_delivery": "none", "agency_approval": "pending"},
            "history": history, **FLAGS}
        result = validate_registration(result)
        _sample_binding(x, y, result["source"])
        return result
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None


def _utility_review(task, metrics):
    candidate = metrics["accuracy"] if task == "classification" else metrics["rmse"]
    baseline = metrics["majority_accuracy"] if task == "classification" else metrics["training_mean_baseline_rmse"]
    improvement = candidate - baseline if task == "classification" else baseline - candidate
    return {"scope": "descriptive_engineering_no_agency_criterion_or_scientific_proof", "task": task,
        "metric": "accuracy" if task == "classification" else "rmse",
        "comparator": "training_majority_accuracy" if task == "classification" else "training_mean_baseline_rmse",
        "candidate": candidate, "baseline": baseline, "improvement": improvement,
        "criterion": "strict_improvement_gt_zero", "result": "met" if improvement > 0 else "not_met"}


def validate_review(value):
    try:
        result = _owned(value, frozenset({"schema", "status", "registration_sha256", "artifacts_sha256", "candidate_sha256",
            "report_sha256", "profile_id", "utility", "permanent_block_reasons", "evidence_scope", *FLAGS}))
        _same(result["schema"], _REVIEW_SCHEMA)
        _same(result["status"], "production_blocked")
        profile = profile_descriptor(result["profile_id"])
        for key in ("registration_sha256", "artifacts_sha256", "candidate_sha256", "report_sha256"):
            _sha(result[key])
        _same(result["permanent_block_reasons"], list(BLOCK_REASONS))
        _same(result["evidence_scope"], "numeric_replay_only_prospective_ordering_requires_workflow_ledger")
        utility = _owned(result["utility"], frozenset({"scope", "task", "metric", "comparator", "candidate",
            "baseline", "improvement", "criterion", "result"}))
        for name in ("candidate", "baseline", "improvement"):
            if type(utility[name]) is not float or not math.isfinite(utility[name]):
                _fail()
        if min(utility["candidate"], utility["baseline"]) < 0:
            _fail()
        if profile["task"] == "classification" and max(utility["candidate"], utility["baseline"]) > 1:
            _fail()
        metrics = ({"accuracy": utility["candidate"], "majority_accuracy": utility["baseline"]}
                   if profile["task"] == "classification" else
                   {"rmse": utility["candidate"], "training_mean_baseline_rmse": utility["baseline"]})
        _same(utility, _utility_review(profile["task"], metrics))
        for key, expected in FLAGS.items():
            _same(result[key], expected)
        return result
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None


def evaluate_native(registration, blobs):
    """Replay exact captured bytes and evaluate only the frozen engineering rule.

    This function accepts no caller-supplied admission or training approval.
    The workflow/ledger must independently establish prospective reservation,
    current history and authenticated evidence before recording completion.
    """
    try:
        registration = validate_registration(registration)
        if type(blobs) is not dict:
            _fail()
        blobs = dict(blobs)  # Byte values are immutable; no caller mapping alias.
        manifest = artifact_manifest(blobs)
        replay_native_bundle(blobs)
        source, frozen_plan = registration["source"], registration["plan"]
        plan = parse_plan(blobs["plan.json"])
        _same(_plan_summary(plan, blobs["plan.json"], frozen_plan["workflow_sha256"], frozen_plan["runtime_sha256"]), frozen_plan)
        _same(frozen_plan["runtime_sha256"], digest(runtime_observation()))
        _same(source["source_sha256"], plan.source_sha256)
        _same(source["dataset_id"], plan.dataset_id)
        _same(source["task"], plan.task)
        _same(source["feature_names"], plan.feature_names)
        _same(source["data_sha256"], hashlib.sha256(blobs["dataset.json"]).hexdigest())
        data = native_json(blobs["dataset.json"])
        x, y = native._arrays(data["x"], data["y"])
        _sample_binding(x, y, source)
        report = native_json(blobs["report.json"])
        review = {"schema": _REVIEW_SCHEMA, "status": "production_blocked", "registration_sha256": digest(registration),
            "artifacts_sha256": digest(manifest), "candidate_sha256": hashlib.sha256(blobs["candidate.json"]).hexdigest(),
            "report_sha256": hashlib.sha256(blobs["report.json"]).hexdigest(), "profile_id": registration["profile_id"],
            "utility": _utility_review(source["task"], report["utility"]), "permanent_block_reasons": list(BLOCK_REASONS),
            "evidence_scope": "numeric_replay_only_prospective_ordering_requires_workflow_ledger", **FLAGS}
        return validate_review(review)
    except Exception:
        raise RegistrationError("Public fixture registration rejected") from None
