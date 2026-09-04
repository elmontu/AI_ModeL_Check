#!/usr/bin/env python3
"""Run one real XGBoost training-to-MRAP assessment pipeline.

The outer application workflow owns data intake, outcome-free planning, model
training, and packaging.  MRAP/1.0 begins only after the exact release bundle
exists: it registers those bytes, approves the frozen evidence plan, closes a
post-registration evidence run, and records the reference-core assessment.

This is a teaching and integration profile.  It never authorizes or deploys a
model.  The default public medical datasets are not private-government data and
their results are not clinical validation.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.datasets import load_breast_cancer
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_openml_membership import (  # noqa: E402
    equalized_target,
    per_record_loss,
    save_scores,
)
from run_openml_structural import (  # noqa: E402
    capped_indices,
    make_splits,
)
from run_xgboost_audit import (  # noqa: E402
    CANONICAL_GAME_FIELDS,
    evaluate_membership_scores,
    implementation_binding,
    load_dataset,
    local_row_ids,
    run_experiment,
)

from model_release_assurance.analyzers.base import (  # noqa: E402
    statistical_floor_design_sha256,
)
from model_release_assurance.decision import (  # noqa: E402
    decision_game_sha256,
    population_scope_sha256,
)
from model_release_assurance.engine import AssuranceEngine  # noqa: E402
from model_release_assurance.integrity import (  # noqa: E402
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from model_release_assurance.models import (  # noqa: E402
    AnalyzerRequirement,
    AssessmentRequest,
    AttackInput,
    EvidenceContext,
    EvidenceProducer,
    OverallVerdict,
    PolicyBundle,
    PolicyReference,
    PolicyRule,
    PopulationScope,
    ReleaseContract,
    StatisticalFloorDesignRegistration,
    StatisticalFloorFamilyMember,
    StatisticalFloorFamilyPlan,
    ThreatContract,
)
from model_release_assurance.release_protocol import (  # noqa: E402
    ControlStatus,
    ReleaseProtocolActor,
    ReleaseProtocolArtifact,
    ReleaseProtocolArtifactKind,
    ReleaseProtocolEvent,
    ReleaseProtocolEventType,
    ReleaseProtocolRole,
    ReleaseProtocolRun,
    ReleaseProtocolState,
    release_protocol_event_sha256,
    verify_release_protocol_run,
)
from model_release_assurance.services import (  # noqa: E402
    default_analyzer_service_registry,
)


DEFAULT_OUTPUT_ROOT = ROOT / "output" / "training-release-demo"
DEFAULT_PROFILE = "openml-sick"
SEED = 3407
TARGET_FPR = 0.10
FAMILY_CONFIDENCE = 0.95
MEMBERSHIP_TOLERANCE = 0.20
SPLIT_FRACTIONS = {
    "target_train": 0.35,
    "reference_train": 0.25,
    "attack_calibration": 0.15,
    "attack_audit_nonmember": 0.15,
    "utility_test": 0.10,
}
OPENML_SICK_MANIFEST = (
    ROOT / "reproduction" / "openml" / "manifests" / "datasets" / "openml-38.json"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=False)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_value(value) if hasattr(value, "model_dump") else value
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            default=_json_value,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _relative(run_dir: Path, path: Path) -> str:
    resolved = path.resolve(strict=True)
    root = run_dir.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"pipeline artifact escapes run directory: {resolved}")
    return resolved.relative_to(root).as_posix()


def _artifact_record(run_dir: Path, path: Path) -> dict[str, str]:
    return {"path": _relative(run_dir, path), "sha256": sha256_file(path)}


def _download_verified(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        actual = sha256_file(temporary)
        if actual != expected_sha256:
            raise ValueError(
                f"downloaded dataset hash mismatch: expected {expected_sha256}, got {actual}"
            )
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _prepare_dataset(
    run_dir: Path,
    *,
    dataset_profile: str,
    dataset_path: Path | None,
    target_column: str | None,
) -> tuple[Path, str, dict[str, Any]]:
    intake = run_dir / "intake"
    intake.mkdir(parents=True, exist_ok=True)
    if dataset_path is not None:
        resolved = dataset_path.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("--dataset-path must identify a regular CSV or Parquet file")
        if not target_column:
            raise ValueError("--target-column is required with --dataset-path")
        frame = load_dataset(resolved, target_column)
        metadata = {
            "profile": "approved-local",
            "kind": "operator_supplied",
            "is_synthetic": False,
            "name": resolved.name,
            "source": "operator-supplied approved local dataset",
            "source_url": None,
            "license_reviewed_by_demo": False,
            "real_public_data": False,
            "contains_personal_data": "operator_must_classify",
            "contains_production_data": "operator_must_classify",
            "rows": int(len(frame)),
            "features": int(len(frame.columns) - 1),
            "target_column": target_column,
            "dataset_path": str(resolved),
            "dataset_sha256": sha256_file(resolved),
            "path": str(resolved),
            "sha256": sha256_file(resolved),
            "warning": (
                "The local path is recorded in worker manifests. Use only inside an approved "
                "enclave; this runner does not grant data authority or de-identify records."
            ),
        }
        _write_json(intake / "data-source.json", metadata)
        return resolved, target_column, metadata

    if dataset_profile == "sklearn-breast-cancer":
        bunch = load_breast_cancer(as_frame=True)
        frame = bunch.frame.copy()
        target_name = "diagnosis"
        frame = frame.rename(columns={str(bunch.target.name): target_name})
        frame[target_name] = frame[target_name].map({0: "malignant", 1: "benign"})
        destination = intake / "wisconsin-diagnostic-breast-cancer.csv"
        frame.to_csv(destination, index=False, lineterminator="\n")
        metadata = {
            "profile": dataset_profile,
            "kind": "real_public",
            "is_synthetic": False,
            "name": "Wisconsin Diagnostic Breast Cancer",
            "source": (
                "scikit-learn packaged copy of the UCI Wisconsin Diagnostic "
                "Breast Cancer (WDBC) dataset"
            ),
            "source_url": "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic",
            "license_reviewed_by_demo": False,
            "real_public_data": True,
            "contains_personal_data": False,
            "contains_production_data": False,
            "rows": int(len(frame)),
            "features": int(len(frame.columns) - 1),
            "target_column": target_name,
            "dataset_path": _relative(run_dir, destination),
            "dataset_sha256": sha256_file(destination),
            "path": _relative(run_dir, destination),
            "sha256": sha256_file(destination),
            "warning": (
                "Public teaching data only. This is not private hospital data, a current "
                "clinical population, clinical validation, or a scalability benchmark."
            ),
        }
        _write_json(intake / "data-source.json", metadata)
        return destination, target_name, metadata

    if dataset_profile != "openml-sick":
        raise ValueError(
            "dataset_profile must be 'openml-sick' or 'sklearn-breast-cancer'"
        )
    manifest = json.loads(OPENML_SICK_MANIFEST.read_text(encoding="utf-8"))
    expected_sha256 = str(manifest["snapshot_sha256"])
    destination = intake / "openml-38-sick.parquet"
    cached = ROOT / str(manifest["snapshot_path"])
    if cached.is_file() and sha256_file(cached) == expected_sha256:
        shutil.copyfile(cached, destination)
    else:
        try:
            _download_verified(str(manifest["parquet_url"]), destination, expected_sha256)
        except Exception as exc:
            raise RuntimeError(
                "OpenML sick dataset acquisition failed. Connect once and retry, or use "
                "--dataset-profile sklearn-breast-cancer for the packaged offline profile."
            ) from exc
    target_name = str(manifest["target"])
    frame = load_dataset(destination, target_name)
    metadata = {
        "profile": dataset_profile,
        "kind": "real_public",
        "is_synthetic": False,
        "name": str(manifest["name"]),
        "source": "digest-pinned OpenML dataset 38 public snapshot",
        "source_url": str(manifest["parquet_url"]),
        "openml_dataset_id": int(manifest["dataset_id"]),
        "license_reviewed_by_demo": False,
        "real_public_data": True,
        "contains_personal_data": False,
        "contains_production_data": False,
        "rows": int(len(frame)),
        "features": int(len(frame.columns) - 1),
        "target_column": target_name,
        "dataset_path": _relative(run_dir, destination),
        "dataset_sha256": sha256_file(destination),
        "path": _relative(run_dir, destination),
        "sha256": sha256_file(destination),
        "warning": (
            "Public historical medical teaching data only. It is not private hospital data, "
            "a current government-health population, or clinical validation."
        ),
    }
    _write_json(intake / "data-source.json", metadata)
    return destination, target_name, metadata


def _planned_counts(
    frame: pd.DataFrame,
    *,
    target_column: str,
    dataset_sha256: str,
    row_cap: int,
) -> dict[str, int]:
    encoder = LabelEncoder()
    target = encoder.fit_transform(frame[target_column].astype("string"))
    selected = capped_indices(target, row_cap, SEED)
    selected_target = target[selected]
    splits = make_splits(selected_target, SEED, SPLIT_FRACTIONS)
    target_indices = equalized_target(
        splits["target_train"],
        selected_target,
        len(splits["reference_train"]),
        SEED + 100,
    )
    # Derive identifiers here as an additional outcome-free consistency check.
    identities = local_row_ids(dataset_sha256, len(frame))[selected]
    if len(set(identities.tolist())) != len(identities):
        raise RuntimeError("derived dataset row identifiers are not unique")
    return {
        "selected": int(len(selected)),
        "members": int(len(target_indices)),
        "nonmember_calibration": int(len(splits["attack_calibration"])),
        "nonmember_audit": int(len(splits["attack_audit_nonmember"])),
        "utility": int(len(splits["utility_test"])),
    }


def _build_population_scope(
    dataset_sha256: str,
    metadata: dict[str, Any],
    frozen_at: datetime,
) -> PopulationScope:
    return PopulationScope.model_validate(
        {
            "scope_id": "training-demo-records",
            "name": f"Rows in the hash-bound {metadata['name']} teaching snapshot",
            "unit_kind": "record",
            "custom_unit_definition": None,
            "universe_definition": (
                "Exactly the rows in the dataset snapshot named by population_snapshot_sha256; "
                "no inference is made about a current healthcare population."
            ),
            "inclusion_criteria": ["present in the hash-bound input snapshot"],
            "exclusion_criteria": [],
            "jurisdictions": ["public teaching dataset; jurisdiction not asserted"],
            "reference_date": frozen_at.date().isoformat(),
            "valid_until": None,
            "population_snapshot_sha256": dataset_sha256,
            "size": {
                "basis": "exact_registry",
                "lower_bound": int(metadata["rows"]),
                "point_estimate": int(metadata["rows"]),
                "upper_bound": int(metadata["rows"]),
                "source": "row count replayed from the hash-bound dataset snapshot",
                "measured_at": _iso(frozen_at),
            },
            "subgroup_dimensions": [],
            "data_steward": "Public-data demo operator",
            "notes": "Integration-demo scope only; not an approved health-data population.",
        }
    )


def _build_threat(scope_id: str) -> ThreatContract:
    return ThreatContract.model_validate(
        {
            "threat_id": "membership-record",
            "kind": "membership",
            "mandatory": True,
            "secret": "whether one hash-bound record was used to train the target model",
            "prior": "attack TPR is evaluated at the separately controlled false-positive rate",
            "side_information": [
                "candidate record and true label",
                "class probabilities from the packaged full-artifact model",
                "complete schema and exact dataset summary metadata",
                "registered XGBoost family and hyperparameters",
            ],
            "adversary_metadata_profile": "exact_database_feature_summaries_v1",
            "success_metric": f"membership true-positive rate at FPR <= {TARGET_FPR}",
            "decision_metric": "membership_tpr_at_fpr",
            "metric_parameters": {"target_fpr": TARGET_FPR},
            "finite_game": None,
            "tolerance": MEMBERSHIP_TOLERANCE,
            "tolerance_basis": "absolute",
            "harm_rationale": (
                "Training membership can reveal association with a sensitive medical dataset; "
                "the public teaching run demonstrates the mechanism, not actual patient harm."
            ),
            "population_scope_id": scope_id,
            "candidate_set": None,
            "target_signal_source": None,
            "realizability": "not_applicable",
        }
    )


def _build_interface() -> dict[str, Any]:
    return {
        "schema_version": "3.0",
        "protocol_type": "predictive",
        "access": "full_artifact",
        "outputs": ["predicted class", "class probabilities"],
        "output_channels": {
            "aggregates": False,
            "labels": True,
            "scores": False,
            "probabilities": True,
            "logits": False,
            "explanations": False,
            "text": False,
            "embeddings": False,
            "gradients": False,
            "parameters": True,
            "downloadable_files": ["release-bundle.zip"],
            "shipped_summary_metadata": [],
            "custom_channels": [],
        },
        "precision_bits": 32,
        "query_budget": None,
        "adaptive_queries": False,
        "authenticated": True,
        "rate_limited": False,
        "rate_limit": {
            "enabled": False,
            "scope": "none",
            "requests_per_window": None,
            "window_seconds": None,
            "burst_capacity": None,
            "retry_after_exposed": False,
            "enforcement": "not_applicable",
            "custom_parameters": {},
        },
        "timing": {
            "recipient_observable": False,
            "measurement_resolution_milliseconds": None,
            "includes_queue_time": False,
            "mitigation": "not_applicable",
            "mitigation_parameters": {},
        },
        "errors": {
            "transport_status": "none",
            "documented_status_codes": [],
            "error_content": "none",
            "error_schema_sha256": None,
            "retry_metadata": False,
        },
        "execution": {
            "batching": "recipient_controlled",
            "maximum_batch_size": None,
            "maximum_concurrent_requests": None,
            "cross_request_state": "none",
            "cross_request_state_ttl_seconds": None,
        },
        "access_paths": {
            "side_channels": [],
            "custom_side_channels": [],
            "admin_access": "none",
            "admin_capabilities": [],
            "local_access": "artifact_only",
            "local_capabilities": ["read and execute the complete packaged model"],
        },
        "serialization": {
            "formats": ["zip", "xgboost-ubj", "joblib"],
            "media_types": ["application/zip", "application/octet-stream"],
            "encodings": ["binary"],
            "compression": ["zip-stored"],
            "schema_sha256": None,
            "endianness": "not_applicable",
        },
        "llm_protocol": None,
        "notes": "Teaching bundle only; joblib must be loaded only in a trusted worker.",
    }


def _attack_descriptor() -> Any:
    return next(
        service.descriptor
        for service in default_analyzer_service_registry().services
        if service.descriptor.input_kind == "attack"
    )


def _read_split_manifest(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _run_post_registration_attack(
    *,
    run_dir: Path,
    dataset_path: Path,
    target_column: str,
    dataset_sha256: str,
    worker_run_dir: Path,
    worker_manifest: dict[str, Any],
    release_bundle_sha256: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], datetime]:
    """Re-execute the frozen attack after registration on the exact target bytes."""

    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    bundle_path = worker_run_dir / worker_manifest["artifacts"]["release_bundle"]["path"]
    if sha256_file(bundle_path) != release_bundle_sha256:
        raise ValueError("registered release bundle changed before evidence collection")
    model_path = worker_run_dir / worker_manifest["artifacts"]["target_model"]["path"]
    preprocessing_path = (
        worker_run_dir / worker_manifest["artifacts"]["target_preprocessing"]["path"]
    )
    with zipfile.ZipFile(bundle_path) as archive:
        if archive.read("target-model.ubj") != model_path.read_bytes():
            raise ValueError("target model file differs from the registered bundle member")
        if archive.read("target-preprocessing.joblib") != preprocessing_path.read_bytes():
            raise ValueError("target preprocessing differs from the registered bundle member")

    target_pipeline = joblib.load(preprocessing_path)
    reference_pipeline_path = (
        worker_run_dir / worker_manifest["artifacts"]["reference_preprocessing"]["path"]
    )
    reference_pipeline = joblib.load(reference_pipeline_path)
    target_model = XGBClassifier()
    target_model.load_model(model_path)
    reference_model_path = (
        worker_run_dir / worker_manifest["artifacts"]["reference_model"]["path"]
    )
    reference_model = XGBClassifier()
    reference_model.load_model(reference_model_path)

    frame = load_dataset(dataset_path, target_column)
    features = frame.drop(columns=[target_column])
    labels = target_pipeline["label_encoder"].transform(frame[target_column].astype("string"))
    identities = local_row_ids(dataset_sha256, len(frame))
    index_by_id = {row_id: index for index, row_id in enumerate(identities.tolist())}
    split_path = worker_run_dir / worker_manifest["artifacts"]["splits"]["path"]
    split_manifest = _read_split_manifest(split_path)

    group_ids = {
        "member_audit": split_manifest["target_training_row_ids"],
        "nonmember_calibration": split_manifest["splits"]["attack_calibration"],
        "nonmember_audit": split_manifest["splits"]["attack_audit_nonmember"],
    }
    raw_rows: list[dict[str, Any]] = []
    for group, row_ids in group_ids.items():
        try:
            indices = np.asarray([index_by_id[row_id] for row_id in row_ids], dtype=int)
        except KeyError as exc:
            raise ValueError("retained split identifies a row outside the bound dataset") from exc
        target_view = target_pipeline["preprocessor"].transform(features.iloc[indices])
        reference_view = reference_pipeline["preprocessor"].transform(features.iloc[indices])
        group_labels = labels[indices]
        target_loss = per_record_loss(target_model, target_view, group_labels)
        reference_loss = per_record_loss(reference_model, reference_view, group_labels)
        score = reference_loss - target_loss
        raw_rows.extend(
            {
                "row_id": identities[index],
                "group": group,
                "is_member": group == "member_audit",
                "true_class": int(labels[index]),
                "target_loss": float(target_item),
                "reference_loss": float(reference_item),
                "membership_score": float(score_item),
            }
            for index, target_item, reference_item, score_item in zip(
                indices, target_loss, reference_loss, score, strict=True
            )
        )

    raw_scores_path = evidence_dir / "post-registration-membership-scores.parquet"
    save_scores(raw_scores_path, raw_rows)
    attack = evaluate_membership_scores(
        pd.DataFrame(raw_rows),
        target_fpr=float(config["attack"]["target_fpr"]),
        confidence_family=float(config["attack"]["confidence"]),
        registered_comparisons=1,
        membership_priors=list(config["attack"]["membership_priors"]),
    )
    completed_at = _utc_now()
    result = {
        "schema_version": "mra-training-demo-post-registration-attack-1.0",
        "status": "complete",
        "started_at": _iso(started_at),
        "completed_at": _iso(completed_at),
        "release_bundle_sha256_before": release_bundle_sha256,
        "release_bundle_sha256_after": sha256_file(bundle_path),
        "registered_plan_executed": True,
        "same_artifact_verified": True,
        "target_model_loaded_from_verified_bundle_member": True,
        "raw_scores": _artifact_record(run_dir, raw_scores_path),
        "attack": attack,
        "limitations": [
            "This is a single registered membership attack, not a complete red-team battery.",
            "It is a floor or screen and cannot prove a privacy ceiling or clear release.",
        ],
    }
    result_path = evidence_dir / "post-registration-attack-result.json"
    _write_json(result_path, result)
    return result, completed_at


def _actors() -> tuple[ReleaseProtocolActor, ...]:
    organizations = {
        ReleaseProtocolRole.MODEL_OWNER: "Demo model team",
        ReleaseProtocolRole.POLICY_AUTHORITY: "Demo policy authority",
        ReleaseProtocolRole.POPULATION_STEWARD: "Demo data steward",
        ReleaseProtocolRole.CONFIGURATION_GENERATOR: "Demo release engineering",
        ReleaseProtocolRole.EVIDENCE_AUTHORITY: "Demo evidence worker",
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR: "MRA reference assessor",
        ReleaseProtocolRole.OPTIMIZATION_AUTHORITY: "External optimization authority",
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY: "External accountable authority",
        ReleaseProtocolRole.PORTFOLIO_REGISTRY: "External portfolio registry",
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY: "External deployment gateway",
        ReleaseProtocolRole.MONITORING_AUTHORITY: "External monitoring authority",
        ReleaseProtocolRole.INCIDENT_AUTHORITY: "External incident authority",
    }
    return tuple(
        ReleaseProtocolActor(
            actor_id=f"actor:{role.value}",
            role=role,
            organization=organizations[role],
            key_id=f"demo-only:{role.value}",
        )
        for role in ReleaseProtocolRole
    )


def _protocol_artifact(
    *,
    run_dir: Path,
    artifact_id: str,
    kind: ReleaseProtocolArtifactKind,
    path: Path,
    role: ReleaseProtocolRole,
) -> ReleaseProtocolArtifact:
    return ReleaseProtocolArtifact(
        artifact_id=artifact_id,
        kind=kind,
        path=_relative(run_dir, path),
        sha256=sha256_file(path),
        producer_actor_id=f"actor:{role.value}",
    )


def _build_protocol_run(
    *,
    run_dir: Path,
    release: ReleaseContract,
    policy_path: Path,
    release_path: Path,
    scope: PopulationScope,
    scope_path: Path,
    threat_path: Path,
    family_plan_path: Path,
    evidence_bundle_path: Path,
    assessment_path: Path,
    verdict: OverallVerdict,
    registered_at: datetime,
    plan_approved_at: datetime,
    evidence_frozen_at: datetime,
    assessment_recorded_at: datetime,
) -> tuple[ReleaseProtocolRun, Any]:
    workflow_dir = run_dir / "workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    protocol_artifact_dir = workflow_dir / "artifacts"
    protocol_artifact_dir.mkdir(parents=True, exist_ok=True)
    registration_path = run_dir / "contracts" / "registration.json"
    portfolio_path = run_dir / "contracts" / "portfolio-snapshot.json"
    error_budget_path = run_dir / "plan" / "assurance-error-budget.json"
    monitoring_path = run_dir / "plan" / "monitoring-plan.json"
    registered_head = sha256_bytes(
        canonical_json_bytes(
            {
                "domain": "MRA-TRAINING-DEMO-EMPTY-PORTFOLIO-1",
                "sequence": 0,
            }
        )
    )
    _write_json(
        registration_path,
        {
            "release_id": release.release_id,
            "artifact_sha256": release.artifact_sha256,
            "interface_sha256": sha256_bytes(canonical_json_bytes(release.interface)),
            "registered_at": _iso(registered_at),
            "identity_assurance": "demo_only",
            "separation_of_duties_enforced": False,
        },
    )
    _write_json(
        portfolio_path,
        {"sequence": 0, "head_sha256": registered_head, "entries": []},
    )
    _write_json(
        error_budget_path,
        {
            "familywise_alpha": 1.0 - FAMILY_CONFIDENCE,
            "familywise_confidence": FAMILY_CONFIDENCE,
            "method": "bonferroni",
        },
    )
    _write_json(
        monitoring_path,
        {
            "status": "planned_not_started",
            "reason": "monitoring starts only after external authorization and activation",
            "production_monitor_created": False,
        },
    )
    # A protocol run is a self-contained replay bundle.  Copy the exact files
    # it references beneath workflow/ so verifiers need no parent traversal.
    source_artifacts = {
        "registration": registration_path,
        "policy": policy_path,
        "release": release_path,
        "population": scope_path,
        "threat": threat_path,
        "portfolio": portfolio_path,
        "plan": family_plan_path,
        "budget": error_budget_path,
        "monitoring": monitoring_path,
        "evidence": evidence_bundle_path,
        "assessment": assessment_path,
    }
    staged_artifacts: dict[str, Path] = {}
    for name, source in source_artifacts.items():
        staged = protocol_artifact_dir / f"{name}{source.suffix}"
        shutil.copyfile(source, staged)
        staged_artifacts[name] = staged
    actors = _actors()
    artifacts = {
        "registration": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:registration",
            kind=ReleaseProtocolArtifactKind.REGISTRATION,
            path=staged_artifacts["registration"],
            role=ReleaseProtocolRole.MODEL_OWNER,
        ),
        "policy": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:policy",
            kind=ReleaseProtocolArtifactKind.POLICY_SNAPSHOT,
            path=staged_artifacts["policy"],
            role=ReleaseProtocolRole.POLICY_AUTHORITY,
        ),
        "release": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:release",
            kind=ReleaseProtocolArtifactKind.RELEASE_INSTANCE,
            path=staged_artifacts["release"],
            role=ReleaseProtocolRole.CONFIGURATION_GENERATOR,
        ),
        "population": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:population",
            kind=ReleaseProtocolArtifactKind.POPULATION_REGISTER,
            path=staged_artifacts["population"],
            role=ReleaseProtocolRole.POPULATION_STEWARD,
        ),
        "threat": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:threat",
            kind=ReleaseProtocolArtifactKind.THREAT_REGISTER,
            path=staged_artifacts["threat"],
            role=ReleaseProtocolRole.POLICY_AUTHORITY,
        ),
        "portfolio": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:portfolio",
            kind=ReleaseProtocolArtifactKind.PORTFOLIO_SNAPSHOT,
            path=staged_artifacts["portfolio"],
            role=ReleaseProtocolRole.PORTFOLIO_REGISTRY,
        ),
        "plan": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:evidence-plan",
            kind=ReleaseProtocolArtifactKind.EVIDENCE_PLAN,
            path=staged_artifacts["plan"],
            role=ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        ),
        "budget": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:error-budget",
            kind=ReleaseProtocolArtifactKind.ASSURANCE_ERROR_BUDGET,
            path=staged_artifacts["budget"],
            role=ReleaseProtocolRole.POLICY_AUTHORITY,
        ),
        "monitoring": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:monitoring-plan",
            kind=ReleaseProtocolArtifactKind.MONITORING_PLAN,
            path=staged_artifacts["monitoring"],
            role=ReleaseProtocolRole.MONITORING_AUTHORITY,
        ),
        "evidence": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:evidence-bundle",
            kind=ReleaseProtocolArtifactKind.EVIDENCE_BUNDLE,
            path=staged_artifacts["evidence"],
            role=ReleaseProtocolRole.EVIDENCE_AUTHORITY,
        ),
        "assessment": _protocol_artifact(
            run_dir=workflow_dir,
            artifact_id="artifact:assessment",
            kind=ReleaseProtocolArtifactKind.ASSESSMENT_REPORT,
            path=staged_artifacts["assessment"],
            role=ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        ),
    }

    events: list[ReleaseProtocolEvent] = []

    def add(
        event_type: ReleaseProtocolEventType,
        role: ReleaseProtocolRole,
        occurred_at: datetime,
        event_artifacts: tuple[ReleaseProtocolArtifact, ...],
        **values: Any,
    ) -> None:
        sequence = len(events) + 1
        events.append(
            ReleaseProtocolEvent(
                sequence=sequence,
                event_id=f"event:{sequence}:{event_type.value}",
                event_type=event_type,
                occurred_at=occurred_at,
                actor_id=f"actor:{role.value}",
                actor_role=role,
                previous_event_sha256=(
                    release_protocol_event_sha256(events[-1]) if events else None
                ),
                artifacts=event_artifacts,
                **values,
            )
        )

    add(
        ReleaseProtocolEventType.REGISTER_SCOPE,
        ReleaseProtocolRole.MODEL_OWNER,
        registered_at,
        (
            artifacts["registration"],
            artifacts["policy"],
            artifacts["release"],
            artifacts["population"],
            artifacts["threat"],
            artifacts["portfolio"],
        ),
    )
    add(
        ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        plan_approved_at,
        (artifacts["plan"], artifacts["budget"], artifacts["monitoring"]),
        assurance_alpha_budget=Decimal("0.05"),
    )
    add(
        ReleaseProtocolEventType.CLOSE_EVIDENCE,
        ReleaseProtocolRole.EVIDENCE_AUTHORITY,
        evidence_frozen_at,
        (artifacts["evidence"],),
        mandatory_evidence_complete=True,
        selection_coverage_valid=False,
        positive_control_status=ControlStatus.NOT_APPLICABLE,
        assurance_alpha_spent=Decimal("0.05"),
    )
    add(
        ReleaseProtocolEventType.RECORD_ASSESSMENT,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        assessment_recorded_at,
        (artifacts["assessment"],),
        assessment_verdict=verdict,
    )
    protocol = ReleaseProtocolRun(
        release_id=release.release_id,
        release_instance_sha256=sha256_file(release_path),
        artifact_sha256=release.artifact_sha256,
        interface_sha256=sha256_bytes(canonical_json_bytes(release.interface)),
        policy_sha256=sha256_file(policy_path),
        population_scope_sha256s={scope.scope_id: population_scope_sha256(scope)},
        registered_portfolio_head_sha256=registered_head,
        registered_portfolio_sequence=0,
        actors=actors,
        events=tuple(events),
        claimed_state=ReleaseProtocolState.ASSESSED,
    )
    verification = verify_release_protocol_run(
        protocol,
        workflow_dir,
        verify_artifact_files=True,
        as_of=assessment_recorded_at + timedelta(microseconds=1),
    )
    if not verification.valid:
        raise RuntimeError(f"generated protocol transcript is invalid: {verification.reasons}")
    return protocol, verification


def verify_pipeline_bindings(run_dir: Path, report: dict[str, Any] | None = None) -> bool:
    """Replay the same-artifact invariant across training, contracts, core, and MRAP."""

    run_dir = run_dir.resolve(strict=True)
    if report is None:
        report = json.loads((run_dir / "pipeline-report.json").read_text(encoding="utf-8"))
    bundle_record = report["artifacts"]["release_bundle"]
    bundle_path = run_dir / bundle_record["path"]
    actual_bundle_sha256 = sha256_file(bundle_path)
    release = ReleaseContract.model_validate_json(
        (run_dir / "contracts" / "release-contract.json").read_text(encoding="utf-8")
    )
    request = AssessmentRequest.model_validate_json(
        (run_dir / "assessment" / "assessment-request.json").read_text(encoding="utf-8")
    )
    assessment = json.loads(
        (run_dir / "assessment" / "assessment-report.json").read_text(encoding="utf-8")
    )
    protocol = ReleaseProtocolRun.model_validate_json(
        (run_dir / "workflow" / "release-protocol-run.json").read_text(encoding="utf-8")
    )
    attack = next(value for value in request.analyzer_inputs if value.analyzer == "attack")
    values = {
        actual_bundle_sha256,
        bundle_record["sha256"],
        release.artifact_sha256,
        request.release.artifact_sha256,
        attack.evidence_context.artifact_sha256,
        assessment["artifact_sha256"],
        protocol.artifact_sha256,
    }
    if len(values) != 1:
        raise ValueError(f"same-artifact binding failed: {sorted(values)}")
    return True


def verify_training_release_demo(run_dir: Path) -> bool:
    """Replay artifact digests, release identity, and the MRAP transcript."""

    run_dir = run_dir.resolve(strict=True)
    report = json.loads(
        (run_dir / "pipeline-report.json").read_text(encoding="utf-8")
    )
    for record in report["artifacts"].values():
        path = (run_dir / record["path"]).resolve(strict=True)
        if not path.is_relative_to(run_dir) or sha256_file(path) != record["sha256"]:
            raise ValueError(f"demo artifact digest mismatch: {record['path']}")
    verify_pipeline_bindings(run_dir, report)
    protocol_path = run_dir / "workflow" / "release-protocol-run.json"
    protocol = ReleaseProtocolRun.model_validate_json(
        protocol_path.read_text(encoding="utf-8")
    )
    replay = verify_release_protocol_run(
        protocol,
        protocol_path.parent,
        verify_artifact_files=True,
        as_of=protocol.events[-1].occurred_at + timedelta(microseconds=1),
    )
    if not replay.valid or replay.final_state is not ReleaseProtocolState.ASSESSED:
        raise ValueError(f"demo MRAP transcript did not replay: {replay.reasons}")
    return True


def _render_guide(report: dict[str, Any]) -> str:
    verdict = report["assessment"]["verdict"]
    disposition = "BLOCK AND REDESIGN" if verdict == "block" else "HOLD — CEILING MISSING"
    hook = report["training"]["training_hook"]
    dataset = report["dataset"]
    return "\n".join(
        [
            "# Start here: real training-to-assessment demo",
            "",
            "**ACTUAL MODEL TRAINED: YES.**",
            f"**Decision: {disposition}. DO NOT RELEASE. NOT AUTHORIZED. NOT DEPLOYED.**",
            "",
            "This run trained a real XGBoost classifier, recorded a callback during every "
            "boosting round, packaged the exact model and preprocessing, registered those "
            "bytes, reran the frozen membership test on that exact candidate, and submitted "
            "the result to the MRA reference core.",
            "",
            "## One-screen result",
            "",
            f"- Actual model trained: **YES** (`{report['training']['model_family']}`)",
            f"- Data: **{dataset['name']}**, {dataset['rows']} real public teaching rows",
            f"- Training-hook rounds observed: **{hook['hook_iterations']}**",
            f"- Same artifact bound throughout: **{str(report['bindings']['all_equal']).upper()}**",
            "- Confirmatory post-registration attack admitted: **YES**",
            f"- Assessment: **{verdict.upper()}**",
            "- Optimization executed: **NO** (a non-clear assessment is ineligible)",
            "- Production authorization issued: **NO**",
            "- Production deployment active: **NO**",
            "",
            "## What the clinic or programme team does",
            "",
            "1. The programme owner writes the permitted research purpose and prohibited uses.",
            "2. The data steward checks authority and freezes the exact dataset hash.",
            "3. The assessor freezes the membership test, sample counts, false-positive rate, "
            "confidence, seed, and stopping rule before training.",
            "4. The model team trains XGBoost. The hook records aggregate loss behavior; it "
            "does not copy patient rows and it cannot clear privacy risk.",
            "5. Release engineering packages the model and preprocessor into one ZIP and "
            "registers its SHA-256 in the ReleaseContract.",
            "6. After MRAP registration and plan approval, the evidence worker verifies the ZIP "
            "and reruns the frozen membership attack against its exact model bytes.",
            "7. The independent assessor runs the core. An attack floor can block, but it can "
            "never prove safety. With no valid ceiling, the workflow holds the candidate.",
            "8. Optimization, authorization, deployment, and monitoring do not start. The model "
            "team must add valid same-artifact ceiling evidence or redesign and submit a new candidate.",
            "",
            "## Contract, pipeline, workflow",
            "",
            "- **Contracts** are in `contracts/`, `plan/`, and `assessment/`.",
            "- **Pipeline execution** is in `training/` and `evidence/`.",
            "- **Workflow state** is replayed in `workflow/release-protocol-run.json` and ends "
            "at `assessed`; local code never claims `authorized` or `active`.",
            "- MRAP/1.0 starts after model export. The outer application workflow intentionally "
            "covers intake, preregistration, training, and packaging before MRAP registration.",
            "",
            "## Important limits",
            "",
            f"- {dataset['warning']}",
            "- Prediction accuracy is not privacy, fairness, safety, clinical utility, or legality.",
            "- The one registered membership attack is not a complete red-team battery.",
            "- The transcript is structural and demo-only; it does not authenticate separate people.",
            "- Use of local/private data requires an approved enclave and independent authorities.",
            "",
        ]
    )


def run_training_release_demo(
    run_dir: Path,
    *,
    dataset_profile: str = "sklearn-breast-cancer",
    dataset_path: Path | None = None,
    target_column: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Execute a real model-training pipeline and stop fail-closed after assessment."""

    run_dir = run_dir.resolve(strict=False)
    if run_dir.exists() and any(run_dir.iterdir()):
        if not force:
            raise FileExistsError(f"run directory is not empty: {run_dir}")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    pipeline_started_at = _utc_now()

    dataset_path, target_column, dataset_metadata = _prepare_dataset(
        run_dir,
        dataset_profile=dataset_profile,
        dataset_path=dataset_path,
        target_column=target_column,
    )
    dataset_sha256 = sha256_file(dataset_path)
    frame = load_dataset(dataset_path, target_column)
    row_cap = min(len(frame), 5_000)
    counts = _planned_counts(
        frame,
        target_column=target_column,
        dataset_sha256=dataset_sha256,
        row_cap=row_cap,
    )

    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    planning_started_at = _utc_now()
    scope = _build_population_scope(dataset_sha256, dataset_metadata, planning_started_at)
    threat = _build_threat(scope.scope_id)
    scope_path = plan_dir / "population-scope.json"
    threat_path = plan_dir / "threat-contract.json"
    _write_json(scope_path, scope)
    _write_json(threat_path, threat)
    threat_sha256 = sha256_bytes(canonical_json_bytes(threat))

    config = {
        "schema_version": "1.1",
        "experiment_id": f"training-release-demo-{dataset_metadata['profile']}",
        "dataset": {
            "path": str(dataset_path),
            "sha256": dataset_sha256,
            "target_column": target_column,
        },
        "master_seed": SEED,
        "replicate_seeds": [SEED],
        "row_cap": row_cap,
        "split_fractions": dict(SPLIT_FRACTIONS),
        "model": {
            "n_estimators": 32,
            "max_depth": 3,
            "learning_rate": 0.08,
            "min_child_weight": 1.0,
            "subsample": 1.0,
            "colsample_bytree": 1.0,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
            "gamma": 0.0,
            "max_bin": 256,
        },
        "attack": {
            "target_fpr": TARGET_FPR,
            "confidence": FAMILY_CONFIDENCE,
            "membership_priors": [0.5, 0.1, 0.01],
        },
        "decision_game": {
            "game_id": "training-demo-membership-game",
            "threat_contract_sha256": threat_sha256,
            "population_scope_id": scope.scope_id,
            **CANONICAL_GAME_FIELDS,
        },
    }
    # The canonical fields also contain protected/access values. Explicit values above
    # intentionally agree; dictionary expansion is last to enforce the worker profile.
    config["decision_game"]["game_id"] = "training-demo-membership-game"
    config["decision_game"]["threat_contract_sha256"] = threat_sha256
    config["decision_game"]["population_scope_id"] = scope.scope_id
    config_path = plan_dir / "training-config.json"
    _write_json(config_path, config)

    registration = StatisticalFloorDesignRegistration(
        registration_id="training-demo-membership-family:reference-loss",
        analyzer="attack",
        threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,
        member_id="reference-loss",
        decision_metric="membership_tpr_at_fpr",
        registered_at=_utc_now(),
        dataset_snapshot_sha256=dataset_sha256,
        procedure_sha256=sha256_file(Path(__file__).resolve()),
        execution_plan_sha256=sha256_file(config_path),
        random_seed=SEED,
        stopping_rule=(
            "execute exactly one fixed target/reference split and one post-registration "
            "audit; report every result without best-seed or threshold selection"
        ),
        planned_primary_trials=counts["members"],
        planned_control_trials=counts["nonmember_audit"],
        target_fpr=TARGET_FPR,
        notes="Outcome-free teaching registration; no release authority.",
    )
    registration_path = plan_dir / "statistical-floor-registration.json"
    _write_json(registration_path, registration)
    registration_sha256 = sha256_file(registration_path)
    design = {
        "analyzer": "attack",
        "threat_id": threat.threat_id,
        "population_scope_id": scope.scope_id,
        "attack_name": "reference-loss",
        "preregistration_sha256": registration_sha256,
        "metric": "membership_tpr_at_fpr",
        "trials": counts["members"],
        "confidence": FAMILY_CONFIDENCE,
        "comparison_family_size": 1,
        "calibration_disjoint": True,
        "audit_disjoint": True,
        "raw_counts_retained": True,
        "threshold_pre_registered": True,
        "nonmember_trials": counts["nonmember_audit"],
        "target_fpr": TARGET_FPR,
    }
    plan_frozen_at = _utc_now()
    family_plan = StatisticalFloorFamilyPlan(
        family_id="training-demo-membership-family",
        analyzer="attack",
        threat_id=threat.threat_id,
        decision_metric="membership_tpr_at_fpr",
        members=(
            StatisticalFloorFamilyMember(
                member_id="reference-loss",
                registration_path=_relative(run_dir, registration_path),
                registration_sha256=registration_sha256,
                input_design_sha256=statistical_floor_design_sha256(design),
            ),
        ),
        familywise_confidence=FAMILY_CONFIDENCE,
        multiplicity_method="bonferroni",
        frozen_at=plan_frozen_at,
        authority="Demo independent assessor; not an institutional approval",
    )
    family_plan_path = plan_dir / "statistical-floor-family.json"
    _write_json(family_plan_path, family_plan)
    family_plan_sha256 = sha256_file(family_plan_path)
    selection_policy_path = plan_dir / "selection-policy.json"
    _write_json(
        selection_policy_path,
        {
            "schema_version": "demo-1.0",
            "rule": "optimization is prohibited unless AssessmentReport is clear",
            "non_clear_action": "hold_or_redesign",
        },
    )
    descriptor = _attack_descriptor()
    policy = PolicyBundle(
        policy_id="training-demo-membership-policy",
        policy_version="1.0.0",
        effective_from=planning_started_at - timedelta(seconds=1),
        expires_at=None,
        rules=(
            PolicyRule(
                threat_id=threat.threat_id,
                kind="membership",
                mandatory=True,
                decision_metric="membership_tpr_at_fpr",
                metric_parameters={"target_fpr": TARGET_FPR},
                finite_game=None,
                tolerance=MEMBERSHIP_TOLERANCE,
                tolerance_basis="absolute",
                ceiling_attack_battery_mode="ceiling_prohibited",
                ceiling_attack_battery_waiver_reason=None,
            ),
        ),
        analyzer_requirements=(
            AnalyzerRequirement(
                threat_id=threat.threat_id,
                analyzer="attack",
                minimum_service_version=descriptor.service_version,
                accepted_implementation_sha256s=(descriptor.implementation_sha256,),
                accepted_configuration_sha256s=(family_plan_sha256,),
                required=True,
            ),
        ),
        attack_battery_requirements=(),
        accepted_selection_policy_sha256s=(sha256_file(selection_policy_path),),
    )
    policy_path = plan_dir / "policy.json"
    _write_json(policy_path, policy)
    policy_sha256 = sha256_file(policy_path)
    if not (registration.registered_at <= family_plan.frozen_at):
        raise RuntimeError("evidence design was not registered before family freeze")

    training_started_at = _utc_now()
    if training_started_at < plan_frozen_at:
        raise RuntimeError("training began before the evidence plan was frozen")
    training_dir = run_dir / "training" / "worker"
    summary = run_experiment(config_path, training_dir, force=True)
    training_completed_at = _utc_now()
    worker_run_dir = training_dir / f"seed-{SEED}"
    worker_manifest_path = worker_run_dir / "run-manifest.json"
    worker_manifest = json.loads(worker_manifest_path.read_text(encoding="utf-8"))
    release_bundle_path = (
        worker_run_dir / worker_manifest["artifacts"]["release_bundle"]["path"]
    )
    release_bundle_sha256 = sha256_file(release_bundle_path)
    if release_bundle_sha256 != worker_manifest["release_binding"]["release_artifact_sha256"]:
        raise RuntimeError("training worker did not bind the exported bundle")

    release = ReleaseContract.model_validate(
        {
            "release_id": f"xgboost-{dataset_sha256[:16]}",
            "owner": "Demo model owner",
            "recipient": "Approved research sandbox operator",
            "purpose": (
                "Exercise a model-release assurance pipeline on public teaching data; "
                "never diagnose, prioritize, deny, or alter care"
            ),
            "model_family": "xgboost.XGBClassifier",
            "model_profile": {
                "task": "classification",
                "input_modalities": ["tabular"],
                "output_modalities": ["tabular"],
                "training_paradigm": "supervised",
                "component_model_families": [],
                "generative": False,
                "stateful": False,
                "custom_task_definition": None,
            },
            "protected_unit": "record",
            "artifact_path": _relative(run_dir, release_bundle_path),
            "artifact_sha256": release_bundle_sha256,
            "interface": _build_interface(),
            "previous_release_ids": [],
            "expires_at": _iso(training_completed_at + timedelta(days=30)),
        }
    )
    contracts_dir = run_dir / "contracts"
    release_path = contracts_dir / "release-contract.json"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    # ReleaseProtocolRun.release_instance_sha256 and the AssessmentReport use
    # the same canonical ReleaseContract identity.  Persist those canonical
    # bytes directly so the file digest is that identity as well.
    release_path.write_bytes(canonical_json_bytes(release))
    release_contract_sha256 = sha256_bytes(canonical_json_bytes(release))
    interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))
    registered_at = _utc_now()
    plan_approved_at = _utc_now()

    attack_result, evidence_observed_at = _run_post_registration_attack(
        run_dir=run_dir,
        dataset_path=dataset_path,
        target_column=target_column,
        dataset_sha256=dataset_sha256,
        worker_run_dir=worker_run_dir,
        worker_manifest=worker_manifest,
        release_bundle_sha256=release_bundle_sha256,
        config=config,
    )
    attack = attack_result["attack"]
    evidence_context = EvidenceContext(
        release_id=release.release_id,
        release_contract_sha256=release_contract_sha256,
        policy_sha256=policy_sha256,
        artifact_sha256=release_bundle_sha256,
        interface_sha256=interface_sha256,
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        decision_game_sha256=decision_game_sha256(threat, scope),
        observed_at=evidence_observed_at,
    )
    attack_payload = {
        "analyzer": "attack",
        "threat_id": threat.threat_id,
        "population_scope_id": scope.scope_id,
        "attack_name": "reference-loss",
        "preregistration_sha256": registration_sha256,
        "metric": "membership_tpr_at_fpr",
        "successes": int(attack["true_positives"]),
        "trials": int(attack["true_positives"] + attack["false_negatives"]),
        "confidence": FAMILY_CONFIDENCE,
        "comparison_family_size": 1,
        "calibration_disjoint": True,
        "audit_disjoint": True,
        "raw_counts_retained": True,
        "threshold_pre_registered": True,
        "false_positives": int(attack["false_positives"]),
        "nonmember_trials": int(attack["false_positives"] + attack["true_negatives"]),
        "target_fpr": TARGET_FPR,
        "evidence_context": evidence_context.model_dump(mode="json", exclude_none=False),
    }
    source_path = run_dir / "evidence" / "attack-input-source.json"
    _write_json(source_path, attack_payload)
    producer = EvidenceProducer(
        service_id=descriptor.service_id,
        service_version=descriptor.service_version,
        implementation_sha256=descriptor.implementation_sha256,
        configuration_sha256=family_plan_sha256,
    )
    attack_input = AttackInput.model_validate(
        {
            **attack_payload,
            "provenance": {
                "tool": "mra-training-demo-post-registration-reference-loss",
                "tool_version": "1.0.0",
                "producer": producer.model_dump(mode="json"),
                "configuration_path": _relative(run_dir, family_plan_path),
                "source_path": _relative(run_dir, source_path),
                "source_sha256": sha256_file(source_path),
                "bound_fields": list(attack_payload),
            },
        }
    )
    if statistical_floor_design_sha256(attack_input) != family_plan.members[0].input_design_sha256:
        raise RuntimeError("observed attack changed the frozen statistical design")

    request = AssessmentRequest(
        policy=PolicyReference(
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_path=_relative(run_dir, policy_path),
            policy_sha256=policy_sha256,
        ),
        release=release,
        population_scopes=(scope,),
        threats=(threat,),
        analyzer_inputs=(attack_input,),
    )
    assessment_dir = run_dir / "assessment"
    request_path = assessment_dir / "assessment-request.json"
    _write_json(request_path, request)
    assessment = AssuranceEngine().assess(request, run_dir)
    if assessment.overall_verdict is OverallVerdict.CLEAR:
        raise RuntimeError("a floor-only XGBoost assessment must not clear")
    assessment_path = assessment_dir / "assessment-report.json"
    _write_json(assessment_path, assessment)
    evidence_frozen_at = _utc_now()
    evidence_bundle_path = run_dir / "evidence" / "evidence-bundle.json"
    _write_json(
        evidence_bundle_path,
        {
            "release_id": release.release_id,
            "artifact_sha256": release_bundle_sha256,
            "plan_sha256": family_plan_sha256,
            "post_registration_result": _artifact_record(
                run_dir, run_dir / "evidence" / "post-registration-attack-result.json"
            ),
            "attack_input_source": _artifact_record(run_dir, source_path),
            "raw_scores": attack_result["raw_scores"],
            "training_time_exploratory_screen_admitted": False,
            "closed_at": _iso(evidence_frozen_at),
        },
    )
    assessment_recorded_at = max(_utc_now(), assessment.created_at)
    protocol, verification = _build_protocol_run(
        run_dir=run_dir,
        release=release,
        policy_path=policy_path,
        release_path=release_path,
        scope=scope,
        scope_path=scope_path,
        threat_path=threat_path,
        family_plan_path=family_plan_path,
        evidence_bundle_path=evidence_bundle_path,
        assessment_path=assessment_path,
        verdict=assessment.overall_verdict,
        registered_at=registered_at,
        plan_approved_at=plan_approved_at,
        evidence_frozen_at=evidence_frozen_at,
        assessment_recorded_at=assessment_recorded_at,
    )
    protocol_path = run_dir / "workflow" / "release-protocol-run.json"
    verification_path = run_dir / "workflow" / "release-protocol-verification.json"
    _write_json(protocol_path, protocol)
    _write_json(verification_path, verification)

    telemetry = worker_manifest.get("training_telemetry")
    if not isinstance(telemetry, dict):
        raise RuntimeError("XGBoost worker omitted required training-hook telemetry")
    models_telemetry = telemetry.get("models")
    target_telemetry = (
        models_telemetry.get("target") if isinstance(models_telemetry, dict) else None
    )
    if not isinstance(target_telemetry, dict):
        raise RuntimeError("XGBoost worker omitted target-model training telemetry")
    reference_telemetry = (
        models_telemetry.get("reference") if isinstance(models_telemetry, dict) else None
    )
    if not isinstance(reference_telemetry, dict):
        raise RuntimeError("XGBoost worker omitted reference-model training telemetry")
    hook_iterations = int(target_telemetry.get("iteration_count", 0))
    if hook_iterations < 1:
        raise RuntimeError("XGBoost training hook observed no boosting rounds")

    report: dict[str, Any] = {
        "schema_version": "mra-training-release-demo-1.0",
        "pipeline_id": "real-xgboost-training-to-mrap-assessment",
        "pipeline_started_at": _iso(pipeline_started_at),
        "pipeline_completed_at": _iso(_utc_now()),
        "training_executed": True,
        "dataset": dataset_metadata,
        "training": {
            "model_family": "xgboost.XGBClassifier",
            "model_fit_completed": True,
            "training_started_at": _iso(training_started_at),
            "training_completed_at": _iso(training_completed_at),
            "worker_implementation": implementation_binding(),
            "utility": worker_manifest["utility"],
            "training_hook": {
                "hook_iterations": hook_iterations,
                "telemetry": telemetry,
                "diagnostic_only": True,
                "admitted_as_release_evidence": False,
            },
            "exploratory_membership_screen_admitted": False,
            "release_bundle_sha256": release_bundle_sha256,
        },
        "evidence": {
            "post_registration_execution": True,
            "same_artifact_verified": True,
            "observed_at": _iso(evidence_observed_at),
            "evidence_class": attack["evidence_class"],
            "operating_point_attained": attack["operating_point_attained"],
            "true_positives": attack["true_positives"],
            "false_negatives": attack["false_negatives"],
            "false_positives": attack["false_positives"],
            "true_negatives": attack["true_negatives"],
            "certified_tpr_floor": attack["certified_tpr_floor_at_controlled_fpr"],
            "can_clear": False,
        },
        "assessment": {
            "verdict": assessment.overall_verdict.value,
            "release_id": assessment.release_id,
            "reason": (
                "A valid attack floor may block; without complete-interface ceiling evidence, "
                "the candidate cannot clear."
            ),
        },
        "bindings": {
            "release_bundle_sha256": release_bundle_sha256,
            "release_contract_artifact_sha256": release.artifact_sha256,
            "assessment_request_artifact_sha256": request.release.artifact_sha256,
            "assessment_artifact_sha256": assessment.artifact_sha256,
            "protocol_artifact_sha256": protocol.artifact_sha256,
            "all_equal": len(
                {
                    release_bundle_sha256,
                    release.artifact_sha256,
                    request.release.artifact_sha256,
                    assessment.artifact_sha256,
                    protocol.artifact_sha256,
                }
            )
            == 1,
        },
        "workflow": {
            "outer_application_workflow_wraps_mrap": True,
            "mrap_begins_after_export": True,
            "plan_frozen_at": _iso(plan_frozen_at),
            "training_started_at": _iso(training_started_at),
            "training_completed_at": _iso(training_completed_at),
            "registered_at": _iso(registered_at),
            "plan_approved_at": _iso(plan_approved_at),
            "evidence_observed_at": _iso(evidence_observed_at),
            "evidence_frozen_at": _iso(evidence_frozen_at),
            "final_state": verification.final_state.value,
            "valid": verification.valid,
            "identity_assurance": "demo_only",
            "separation_of_duties_enforced": False,
            "optimization_executed": False,
            "authorization_issued": verification.authorization_issued,
            "deployment_active": verification.deployment_active,
            "monitoring_started": False,
        },
        "pipeline": [
            {"stage": "data_intake", "status": "complete"},
            {"stage": "outcome_free_plan", "status": "frozen_before_training"},
            {"stage": "model_training_with_hook", "status": "complete"},
            {"stage": "deterministic_export", "status": "complete"},
            {"stage": "mrap_registration", "status": "complete"},
            {"stage": "post_registration_evidence", "status": "complete"},
            {"stage": "typed_assessment", "status": assessment.overall_verdict.value},
            {"stage": "optimization", "status": "not_run_non_clear"},
            {"stage": "authorization", "status": "not_issued"},
            {"stage": "deployment", "status": "not_active"},
        ],
        "artifacts": {
            "dataset_source": _artifact_record(run_dir, run_dir / "intake" / "data-source.json"),
            "training_config": _artifact_record(run_dir, config_path),
            "statistical_registration": _artifact_record(run_dir, registration_path),
            "statistical_family_plan": _artifact_record(run_dir, family_plan_path),
            "release_bundle": _artifact_record(run_dir, release_bundle_path),
            "release_contract": _artifact_record(run_dir, release_path),
            "post_registration_attack": _artifact_record(
                run_dir, run_dir / "evidence" / "post-registration-attack-result.json"
            ),
            "assessment_request": _artifact_record(run_dir, request_path),
            "assessment_report": _artifact_record(run_dir, assessment_path),
            "protocol_run": _artifact_record(run_dir, protocol_path),
            "protocol_verification": _artifact_record(run_dir, verification_path),
        },
        "production_authorization_issued": False,
        "production_deployment_active": False,
        "limitations": [
            "Public teaching data are not evidence for private government-health data.",
            "No clinical validity, fairness, legal compliance, safety, or production readiness is established.",
            "The XGBoost membership result is a floor or screen, never a ceiling.",
            "The structural MRAP replay is not a durable production orchestrator or identity system.",
        ],
    }
    if not report["bindings"]["all_equal"]:
        raise RuntimeError("the pipeline changed release artifact identity between stages")
    report_path = run_dir / "pipeline-report.json"
    _write_json(report_path, report)
    verify_pipeline_bindings(run_dir, report)
    (run_dir / "START-HERE.md").write_text(
        _render_guide(report), encoding="utf-8", newline="\n"
    )
    return report


def _safe_run_dir(output_root: Path, run_id: str) -> Path:
    if (
        not run_id
        or run_id in {".", ".."}
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
            for character in run_id
        )
    ):
        raise ValueError("run-id must be a safe single directory name")
    root = output_root.resolve(strict=False)
    result = (root / run_id).resolve(strict=False)
    if result.parent != root:
        raise ValueError("run-id escapes the output root")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train XGBoost and run the exact exported candidate through MRAP assessment"
    )
    parser.add_argument(
        "--dataset-profile",
        choices=("openml-sick", "sklearn-breast-cancer"),
        default=DEFAULT_PROFILE,
        help="public teaching dataset; OpenML is downloaded and digest-verified once per run",
    )
    parser.add_argument("--dataset-path", type=Path, help="approved local CSV/Parquet path")
    parser.add_argument("--target-column", help="required for --dataset-path")
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="exact run directory; alternative to --output-root/--run-id",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="safe output directory name; defaults to a UTC timestamp")
    parser.add_argument("--force", action="store_true", help="replace only the selected run directory")
    args = parser.parse_args()
    run_id = args.run_id or _utc_now().strftime("run-%Y%m%dT%H%M%S%fZ")
    try:
        if args.run_dir is not None and args.run_id is not None:
            raise ValueError("--run-dir cannot be combined with --run-id")
        run_dir = (
            args.run_dir.resolve(strict=False)
            if args.run_dir is not None
            else _safe_run_dir(args.output_root, run_id)
        )
        report = run_training_release_demo(
            run_dir,
            dataset_profile=args.dataset_profile,
            dataset_path=args.dataset_path,
            target_column=args.target_column,
            force=args.force,
        )
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "complete",
                "training_executed": report["training_executed"],
                "assessment": report["assessment"]["verdict"],
                "workflow_state": report["workflow"]["final_state"],
                "authorized": report["production_authorization_issued"],
                "deployed": report["production_deployment_active"],
                "start_here": str((run_dir / "START-HERE.md").resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
