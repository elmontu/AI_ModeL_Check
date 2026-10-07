"""Real Wine training with trusted-local model-only geometric-DP clearance.

Privacy starts at accepted training-record input. The public benchmark split and
operator audit bundle are excluded from the recipient release. This is a local
source-bound mechanism demonstration, not remote attestation or authorization.
"""
from __future__ import annotations
import argparse
import bisect
import copy
import json
import math
import secrets
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any
from .decision import decision_game_sha256, population_scope_sha256
from .engine import AssuranceEngine
from .integrity import canonical_json_bytes, sha256_bytes, sha256_file
from .models import (AnalyzerRequirement, AssessmentReport, AssessmentRequest, DpInput,
    EvidenceContext, EvidenceProducer, PolicyBundle, PolicyReference, PolicyRule,
    PopulationScope, ReleaseContract, ThreatContract)
from .services import default_analyzer_service_registry

PROFILE = "local-private-wine-model-only-v1"
PRESET = "dp-histogram"
TRAINER = "categorical-naive-bayes-with-two-sided-geometric-counts"
PROVENANCE_TOOL = "local-private-wine-geometric-nb"
ACCOUNTANT = "independent-geometric-count-rational-bound-v1"
DATASET = "sklearn-wine"
FEATURES = (
    {"index": 0, "name": "alcohol", "edges": [11, 12, 13, 14]},
    {"index": 12, "name": "proline", "edges": [250, 500, 750, 1000, 1250, 1500]},
)
CLASSES = (0, 1, 2)
SENSITIVITY = 3
GEOMETRIC_B = 9
TARGET_FPR = 0.1
TOLERANCE = 0.2
EPSILON_FRACTION = Fraction(1, 3)
EPSILON = math.nextafter(float(EPSILON_FRACTION), math.inf)
CLEARANCE_SCOPE = (
    "Single model-only package; add/remove one accepted training record; "
    "membership TPR at FPR <= 0.10. No agency-data or person-level authorization."
)
WAIVER = (
    "Prospectively scoped local mathematical mechanism demonstration: the "
    "source-bound pure-DP count mechanism supplies a complete model-only ceiling. "
    "Exploratory attacks and independent known-leak/null controls are retained "
    "separately and are not an institutionally qualified attack battery. "
    "No agency release or deployment authorization is conferred."
)
LIMITATIONS = [
    "The assessed recipient release is recipient-package.json only; the operator audit bundle is not covered.",
    "Protection starts at accepted training-record input; public benchmark selection and held-out utility remain operator-only.",
    "One add/remove record is protected, not every record associated with a person.",
    "Only the declared membership threat is assessed; utility, fairness, other privacy threats and security require review.",
    "Each fresh fit consumes another privacy budget; repeated releases and previous models need composition before authorization.",
    "The bound assumes independent, unbiased hidden OS entropy for every secrets.randbelow draw; host compromise or disclosed randomness is outside scope.",
    "Local source-bound verification does not attest remote execution, operating-system isolation or custody.",
    "The ceiling attack battery is prospectively and explicitly waived for this local mathematical demonstration.",
]
SOURCE_FILES = (
    "private_model_clearance.py", "analyzers/dp.py", "integrity.py", "models.py",
    "decision.py", "engine.py", "services.py", "runtime_identity.py",
    "red_team.py", "tabular_red_team.py",
)
FROZEN_FILES = ("training-config.json", "data-manifest.json", "evaluation-plan.json",
                "selection-policy.json", "policy.json")
COMPLETED_FILES = (
    "recipient-package.json", "accountant-ledger.json", "training-receipt.json",
    "utility-report.json", "positive-controls.json", "red-team-report.json",
    "export-verification.json", "dp-source.json", "assessment-request.json",
    "assessment-report.json", "evidence-freeze.json",
)

class PrivateModelEvidenceError(ValueError):
    """The local private-training evidence is incomplete or inconsistent."""

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")

def _write(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")

def _read(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise PrivateModelEvidenceError("missing or unsafe evidence: " + path.name)
    try:
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON object key")
                result[key] = value
            return result
        def invalid_constant(value: str) -> Any:
            raise ValueError("nonfinite JSON constant: " + value)
        return json.loads(path.read_bytes(), object_pairs_hook=unique_object,
                          parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as exc:
        raise PrivateModelEvidenceError("invalid JSON evidence: " + path.name) from exc

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PrivateModelEvidenceError(message)

def public_configuration() -> dict[str, Any]:
    return {"classes": list(CLASSES), "features": copy.deepcopy(list(FEATURES)),
            "bin_rule": "bisect_right; finite inputs; fixed unbounded outer bins",
            "smoothing": 1,
            "postprocessing": "clamp noisy counts at zero; add one per category; normalize"}

def training_configuration() -> dict[str, Any]:
    return {
        "format_version": "private-training-config/1", "profile": PROFILE,
        "preset": PRESET, "dataset": DATASET,
        "mechanism": "two-sided-geometric-categorical-counts",
        "public_configuration": public_configuration(),
        "adjacency": "add/remove one accepted training record", "protected_unit": "record",
        "l1_sensitivity": SENSITIVITY,
        "geometric_probability": {"numerator": GEOMETRIC_B, "denominator": GEOMETRIC_B + 1},
        "epsilon_upper_fraction": {"numerator": 1, "denominator": 3}, "delta": 0,
        "randomness": "independent secrets.randbelow OS entropy; no retained seed or noise",
        "sampler": "difference of two unbounded geometric-zero draws; no truncation or retry selection",
        "fits": 1,
        "benchmark_split": {"test_fraction": 0.35, "public_split_random_state": 3407,
                            "stratify": "public Wine labels"},
        "privacy_boundary": "accepted training-record input; benchmark split is public operator preparation",
        "recipient_allowlist": ["recipient-package.json"],
        "recipient_exclusions": ["training records", "raw counts", "noise values",
                                 "random seed", "operator audit evidence"],
        "release_selection": "retain first and only fit regardless of utility; no outcome-based refit",
    }

def _benchmark() -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    import numpy as np
    from sklearn.datasets import load_wine
    from sklearn.model_selection import train_test_split
    data = load_wine()
    train, test = train_test_split(np.arange(len(data.target)), test_size=0.35,
                                  random_state=3407, stratify=data.target)
    selected = data.data[:, [item["index"] for item in FEATURES]]
    public_binding = {"x": data.data.tolist(), "y": data.target.tolist(),
                      "train": train.tolist(), "test": test.tolist()}
    manifest = {
        "format_version": "public-wine-input-binding/1", "profile": PROFILE,
        "dataset": DATASET, "source": "scikit-learn bundled public Wine benchmark",
        "name": "Wine", "rows": len(data.target), "features": 2, "source_features": 13,
        "public_snapshot_sha256": sha256_bytes(canonical_json_bytes(public_binding)),
        "accepted_training_input_sha256": sha256_bytes(canonical_json_bytes({
            "x": selected[train].tolist(), "y": data.target[train].tolist()})),
        "public_training_indices": train.tolist(), "public_test_indices": test.tolist(),
        "scope": "Public benchmark binding only; not a recipient output or confidential-data guarantee.",
    }
    return selected, data.target, train, test, manifest

def _geometric_zero() -> int:
    # Exact Bernoulli stopping trials. Unbounded support is essential for pure DP.
    value = 0
    while secrets.randbelow(GEOMETRIC_B + 1) != 0:
        value += 1
    return value

def _geometric_noise() -> int:
    return _geometric_zero() - _geometric_zero()

def _validate_noisy_counts(counts: Any) -> None:
    _require(isinstance(counts, dict) and set(counts) == {"class", "features"},
             "unexpected noisy-count schema")
    _require(isinstance(counts["class"], list) and len(counts["class"]) == len(CLASSES),
             "invalid class-count shape")
    _require(isinstance(counts["features"], list) and len(counts["features"]) == len(FEATURES),
             "invalid feature-count shape")
    arrays = [counts["class"]]
    for item, table in zip(FEATURES, counts["features"], strict=True):
        _require(isinstance(table, list) and len(table) == len(CLASSES),
                 "invalid feature class order")
        for row in table:
            _require(isinstance(row, list) and len(row) == len(item["edges"]) + 1,
                     "invalid feature-bin count shape")
            arrays.append(row)
    _require(all(type(value) is int for row in arrays for value in row),
             "noisy counts must be Python integers")

def _postprocess(counts: dict[str, Any]) -> dict[str, Any]:
    _validate_noisy_counts(counts)
    def normalized(row: list[int]) -> list[float]:
        weights = [max(0, value) + 1 for value in row]
        total = sum(weights)
        return [value / total for value in weights]
    return {"class_prior": normalized(counts["class"]),
            "feature_probabilities": [[normalized(row) for row in table]
                                      for table in counts["features"]]}

def fit_private_model(x: Any, y: Any) -> dict[str, Any]:
    """Fit once; unperturbed counts exist only in worker memory."""
    import numpy as np
    values, labels = np.asarray(x, dtype=float), np.asarray(y)
    _require(values.ndim == 2 and values.shape[1] == 2 and len(values) == len(labels),
             "accepted training input must have two aligned features")
    _require(labels.ndim == 1 and np.isfinite(values).all(),
             "accepted training inputs must be finite with one-dimensional labels")
    _require(all(type(value) in (int, np.int32, np.int64) and int(value) in CLASSES
                 for value in labels), "training labels are outside the fixed public classes")
    class_counts = [0 for _ in CLASSES]
    feature_counts = [[[0 for _ in range(len(item["edges"]) + 1)] for _ in CLASSES]
                      for item in FEATURES]
    for row, label in zip(values, labels, strict=True):
        index = int(label)
        class_counts[index] += 1
        for feature, item in enumerate(FEATURES):
            category = bisect.bisect_right(item["edges"], float(row[feature]))
            feature_counts[feature][index][category] += 1
    noisy_counts = {
        "class": [count + _geometric_noise() for count in class_counts],
        "features": [[[count + _geometric_noise() for count in row] for row in table]
                     for table in feature_counts],
    }
    return {"format_version": "private-categorical-model/1", "profile": PROFILE,
            "public_configuration": public_configuration(), "noisy_counts": noisy_counts,
            "model": _postprocess(noisy_counts)}

def validate_recipient_package(package: Any) -> dict[str, Any]:
    _require(isinstance(package, dict) and set(package) == {
        "format_version", "profile", "public_configuration", "noisy_counts", "model"},
        "recipient package contains unexpected fields")
    _require(package["format_version"] == "private-categorical-model/1"
             and package["profile"] == PROFILE, "unsupported private-model package")
    _require(canonical_json_bytes(package["public_configuration"]) == canonical_json_bytes(public_configuration()),
             "public recipient configuration changed")
    _require(package["model"] == _postprocess(package["noisy_counts"]),
             "recipient model does not replay from noisy counts")
    return package

class RecipientModel:
    """Inert JSON classifier; no pickle, fit method or hidden training state."""
    def __init__(self, package: dict[str, Any]):
        import numpy as np
        self.package = validate_recipient_package(copy.deepcopy(package))
        self.classes_ = np.asarray(CLASSES)
        self.n_features_in_ = 2
    def get_params(self, deep: bool = True) -> dict[str, Any]:
        return {}
    def predict_proba(self, x: Any) -> Any:
        import numpy as np
        values = np.asarray(x, dtype=float)
        _require(values.ndim == 2 and values.shape[1] == 2 and np.isfinite(values).all(),
                 "recipient inputs must be finite two-feature records")
        model = self.package["model"]
        result = []
        for row in values:
            log_weights = [math.log(value) for value in model["class_prior"]]
            for feature, item in enumerate(FEATURES):
                category = bisect.bisect_right(item["edges"], float(row[feature]))
                for label in CLASSES:
                    log_weights[label] += math.log(model["feature_probabilities"][feature][label][category])
            maximum = max(log_weights)
            weights = [math.exp(value - maximum) for value in log_weights]
            total = sum(weights)
            result.append([value / total for value in weights])
        return np.asarray(result, dtype=float).reshape(len(values), len(CLASSES))
    def predict(self, x: Any) -> Any:
        import numpy as np
        return self.classes_[np.argmax(self.predict_proba(x), axis=1)]

def _ledger() -> dict[str, Any]:
    return {
        "format_version": "geometric-count-accountant/1", "profile": PROFILE,
        "accountant": ACCOUNTANT, "adjacency": "add/remove one accepted training record",
        "protected_unit": "record", "vector_l1_sensitivity": SENSITIVITY,
        "count_coordinates": 3 + 3 * sum(len(item["edges"]) + 1 for item in FEATURES),
        "geometric_q": {"numerator": GEOMETRIC_B, "denominator": GEOMETRIC_B + 1},
        "likelihood_ratio_upper": {"numerator": (GEOMETRIC_B + 1) ** SENSITIVITY,
                                   "denominator": GEOMETRIC_B ** SENSITIVITY},
        "epsilon_upper_fraction": {"numerator": 1, "denominator": 3},
        "epsilon_upper": EPSILON, "delta": 0.0,
        "proof": "product geometric likelihood ratio <= (10/9)^3; 3*log(10/9) <= 3/9 = 1/3",
        "postprocessing": "All published parameters are functions of noisy counts and fixed public configuration.",
        "execution_scope": "one fit; model-only package; no recipient training count, noise, seed or raw records",
    }

def _positive_controls() -> dict[str, Any]:
    import numpy as np
    from .tabular_red_team import threshold_probe
    class KnownLeak:
        def predict_proba(self, x: Any) -> Any:
            probability = np.where(np.asarray(x)[:, 0] < 80, 0.99, 0.5)
            return np.column_stack((probability, 1 - probability))
    class Null:
        def predict_proba(self, x: Any) -> Any:
            return np.full((len(x), 2), 0.5)
    members = np.column_stack((np.arange(80), np.zeros(80)))
    nonmembers = np.column_stack((np.arange(80, 160), np.zeros(80)))
    def probe(model: Any) -> dict[str, Any]:
        return threshold_probe(np.log(model.predict_proba(members)[:, 0]),
                               np.log(model.predict_proba(nonmembers)[:, 0]), 3407)
    known, null = probe(KnownLeak()), probe(Null())
    known_passed = known["auc"] == 1 and known["tpr"] == 1 and known["fpr"] == 0
    null_passed = null["auc"] == 0.5 and null["tpr"] == 0 and null["fpr"] == 0
    return {
        "format_version": "private-model-controls/1", "profile": PROFILE,
        "control_scope": "independent prediction adapters and existing probability/loss membership scorer; synthetic inputs",
        "known_leak": {"passed": known_passed, "result": known},
        "null_output": {"passed": null_passed, "result": null},
        "passed": known_passed and null_passed, "can_clear": False,
        "institutionally_qualified_battery": False,
    }


def _interface() -> dict[str, Any]:
    return {
        "schema_version": "3.0", "protocol_type": "predictive", "access": "full_artifact",
        "outputs": ["predicted class", "class probabilities", "noisy model sufficient counts"],
        "output_channels": {
            "aggregates": False, "labels": True, "scores": False, "probabilities": True,
            "logits": False, "explanations": False, "text": False, "embeddings": False,
            "gradients": False, "parameters": True, "downloadable_files": ["recipient-package.json"],
            "shipped_summary_metadata": [], "custom_channels": [],
        },
        "precision_bits": 64, "query_budget": None, "adaptive_queries": False,
        "authenticated": False, "rate_limited": False,
        "rate_limit": {"enabled": False, "scope": "none", "requests_per_window": None,
                       "window_seconds": None, "burst_capacity": None, "retry_after_exposed": False,
                       "enforcement": "not_applicable", "custom_parameters": {}},
        "timing": {"recipient_observable": False, "measurement_resolution_milliseconds": None,
                   "includes_queue_time": False, "mitigation": "not_applicable", "mitigation_parameters": {}},
        "errors": {"transport_status": "none", "documented_status_codes": [],
                   "error_content": "none", "error_schema_sha256": None, "retry_metadata": False},
        "execution": {"batching": "recipient_controlled", "maximum_batch_size": None,
                      "maximum_concurrent_requests": None, "cross_request_state": "none",
                      "cross_request_state_ttl_seconds": None},
        "access_paths": {"side_channels": [], "custom_side_channels": [], "admin_access": "none",
                         "admin_capabilities": [], "local_access": "artifact_only",
                         "local_capabilities": ["read inert noisy counts and replay class probabilities"]},
        "serialization": {"formats": ["json"], "media_types": ["application/json"],
                          "encodings": ["UTF-8"], "compression": ["none"], "schema_sha256": None,
                          "endianness": "not_applicable"},
        "llm_protocol": None,
        "notes": PROFILE + ": recipient-package.json only. Operator audit evidence excluded; local package interface, not a live service.",
    }

def _scope(manifest: dict[str, Any], timestamp: datetime) -> PopulationScope:
    return PopulationScope.model_validate({
        "scope_id": "private-wine-training-records", "name": "Public Wine accepted training-record input",
        "unit_kind": "record", "custom_unit_definition": None,
        "universe_definition": "Accepted finite two-feature Wine training records; adjacency adds or removes one record after public benchmark preparation.",
        "inclusion_criteria": ["finite alcohol and proline features", "fixed public class labels 0, 1 or 2"],
        "exclusion_criteria": ["production agency data and person-level grouping"],
        "jurisdictions": ["public teaching benchmark; jurisdiction not asserted"],
        "reference_date": timestamp.date().isoformat(), "valid_until": None,
        "population_snapshot_sha256": manifest["accepted_training_input_sha256"],
        "size": {"basis": "exact_registry", "lower_bound": len(manifest["public_training_indices"]),
                 "point_estimate": len(manifest["public_training_indices"]),
                 "upper_bound": len(manifest["public_training_indices"]),
                 "source": "public benchmark input binding; operator-only", "measured_at": _iso(timestamp)},
        "subgroup_dimensions": [], "data_steward": "Local public-data demo operator",
        "notes": "Trainer permits add/remove adjacency; observed benchmark size is operator-only, not recipient metadata.",
    })

def _threat(scope: PopulationScope) -> ThreatContract:
    return ThreatContract.model_validate({
        "threat_id": "membership-record", "kind": "membership", "mandatory": True,
        "secret": "whether one accepted training record was included in this fit",
        "prior": "symmetric add/remove membership hypotheses with fixed auxiliary information",
        "side_information": ["candidate record and true label", "complete model-only recipient package",
                             "fixed public configuration", "exact summaries of the already-public full Wine snapshot; no private training-input summaries"],
        "adversary_metadata_profile": "exact_database_feature_summaries_v1",
        "success_metric": "membership true-positive rate at FPR <= 0.10",
        "decision_metric": "membership_tpr_at_fpr", "metric_parameters": {"target_fpr": TARGET_FPR},
        "finite_game": None, "tolerance": TOLERANCE, "tolerance_basis": "absolute",
        "harm_rationale": "Public-data demonstration of record-membership protection; no agency harm or approval claim.",
        "population_scope_id": scope.scope_id, "candidate_set": None,
        "target_signal_source": None, "realizability": "not_applicable",
    })

def _descriptor() -> Any:
    return next(service.descriptor for service in default_analyzer_service_registry().services
                if service.descriptor.input_kind == "dp")

def _policy(timestamp: datetime, configuration_sha256: str,
            selection_sha256: str) -> PolicyBundle:
    descriptor = _descriptor()
    return PolicyBundle(
        policy_id="private-wine-model-only", policy_version="1.0.0",
        effective_from=timestamp, expires_at=None,
        rules=(PolicyRule(
            threat_id="membership-record", kind="membership", mandatory=True,
            decision_metric="membership_tpr_at_fpr", metric_parameters={"target_fpr": TARGET_FPR},
            finite_game=None, tolerance=TOLERANCE, tolerance_basis="absolute",
            ceiling_attack_battery_mode="waived", ceiling_attack_battery_waiver_reason=WAIVER),),
        analyzer_requirements=(AnalyzerRequirement(
            threat_id="membership-record", analyzer="dp", minimum_service_version=descriptor.service_version,
            accepted_implementation_sha256s=(descriptor.implementation_sha256,),
            accepted_configuration_sha256s=(configuration_sha256,), required=True),),
        attack_battery_requirements=(), accepted_selection_policy_sha256s=(selection_sha256,),
    )

def _evaluation_plan() -> dict[str, Any]:
    return {
        "format_version": "private-model-evaluation-plan/1", "profile": PROFILE,
        "membership": {"target_fpr": TARGET_FPR, "tolerance": TOLERANCE,
                       "metric": "membership_tpr_at_fpr"},
        "clearance_evidence": "independently replayed pure-DP geometric-count mechanism ceiling",
        "attack_battery": {"mode": "waived", "reason": WAIVER},
        "exploratory_tools": "existing tabular suite on single recipient model; no target refits",
        "positive_controls": {
            "known_leak": "synthetic membership-dependent prediction adapter; AUC=1, TPR=1, FPR=0",
            "null_output": "constant probability adapter; AUC=0.5, TPR=0, FPR=0"},
        "public_attack_seed": 3407, "target_training_fits": 1,
        "utility": "fixed public held-out benchmark; descriptive operator-only evidence; never select another fit",
        "scope_limitations": LIMITATIONS,
    }

def _source_hashes() -> dict[str, str]:
    package = Path(__file__).parent
    return {name: sha256_file(package / name) for name in SOURCE_FILES}

def _utility(model: RecipientModel, x: Any, y: Any, train: Any, test: Any) -> dict[str, Any]:
    import numpy as np
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss
    prediction, probabilities = model.predict(x[test]), model.predict_proba(x[test])
    labels, counts = np.unique(y[train], return_counts=True)
    majority = int(labels[np.argmax(counts)])
    baseline_predictions = np.full(len(test), majority)
    utility = {
        "accuracy": float(accuracy_score(y[test], prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y[test], prediction)),
        "log_loss": float(log_loss(y[test], probabilities, labels=list(CLASSES))),
        "baseline": {"type": "public_training_majority_class", "prediction": majority,
                     "fit_records": len(train), "evaluation_records": len(test),
                     "accuracy": float(accuracy_score(y[test], baseline_predictions)),
                     "balanced_accuracy": float(balanced_accuracy_score(y[test], baseline_predictions))},
        "scope": "operator-only held-out public Wine utility; not recipient privacy evidence",
    }
    utility["beats_baseline"] = all(utility[key] > utility["baseline"][key]
                                    for key in ("accuracy", "balanced_accuracy"))
    return utility

def _verify_before_assessment(output: Path) -> dict[str, Any]:
    frozen = _read(output / "evidence-freeze.json")
    _require(set(frozen) == {"format_version", "profile", "frozen_at", "files", "source_sha256s"},
             "invalid evidence freeze")
    _require(frozen["format_version"] == "private-model-freeze/1" and frozen["profile"] == PROFILE,
             "unsupported evidence freeze")
    expected_names = set(FROZEN_FILES) | {"source-snapshots/" + name for name in SOURCE_FILES}
    _require(set(frozen["files"]) == expected_names, "prospective freeze inventory changed")
    _require(frozen["source_sha256s"] == _source_hashes(),
             "installed private-training or verifier source changed")
    for name, expected in frozen["files"].items():
        path = output / name
        _require(path.is_file() and not path.is_symlink() and sha256_file(path) == expected,
                 "prospectively frozen input changed: " + name)
    for name, expected in frozen["source_sha256s"].items():
        _require(frozen["files"]["source-snapshots/" + name] == expected,
                 "retained source differs from accepted implementation")
    configuration = _read(output / "training-config.json")
    _require(configuration == training_configuration(),
             "training configuration differs from supported mechanism")
    x, y, train, test, manifest = _benchmark()
    _require(_read(output / "data-manifest.json") == manifest, "public training input binding does not replay")
    _require(_read(output / "evaluation-plan.json") == _evaluation_plan(), "evaluation plan changed")
    _require(_read(output / "selection-policy.json") == {
        "profile": PROFILE, "rule": "retain first and only fit; no utility or verdict based selection"},
        "selection policy changed")
    policy = PolicyBundle.model_validate(_read(output / "policy.json"))
    _require(policy == _policy(policy.effective_from, sha256_file(output / "training-config.json"),
                               sha256_file(output / "selection-policy.json")), "prospective policy changed")
    freeze_time = datetime.fromisoformat(frozen["frozen_at"].replace("Z", "+00:00"))
    receipt = _read(output / "training-receipt.json")
    _require(set(receipt) == {
        "format_version", "profile", "training_started_at", "training_completed_at",
        "training_executed", "fits", "source_sha256", "configuration_sha256",
        "training_input_sha256", "recipient_package_sha256", "randomness", "trainer"},
        "unexpected training receipt fields")
    started = datetime.fromisoformat(receipt["training_started_at"].replace("Z", "+00:00"))
    completed = datetime.fromisoformat(receipt["training_completed_at"].replace("Z", "+00:00"))
    _require(policy.effective_from <= freeze_time <= started <= completed <= _now(),
             "policy/freeze/training chronology is invalid")
    _require(receipt["format_version"] == "private-model-training-receipt/1"
             and receipt["profile"] == PROFILE, "invalid training receipt")
    _require(receipt["training_executed"] is True and type(receipt["fits"]) is int
             and receipt["fits"] == 1, "receipt does not bind a single real fit")
    _require(receipt["source_sha256"] == frozen["source_sha256s"]["private_model_clearance.py"],
             "training source binding mismatch")
    _require(receipt["configuration_sha256"] == frozen["files"]["training-config.json"],
             "training configuration binding mismatch")
    _require(receipt["training_input_sha256"] == manifest["accepted_training_input_sha256"],
             "training input binding mismatch")
    _require(receipt["randomness"] == configuration["randomness"], "randomness contract changed")
    _require(receipt["trainer"] == TRAINER, "actual trainer identity changed")
    package = validate_recipient_package(_read(output / "recipient-package.json"))
    package_hash = sha256_file(output / "recipient-package.json")
    _require(receipt["recipient_package_sha256"] == package_hash,
             "recipient package differs from trained receipt")
    _require(_read(output / "accountant-ledger.json") == _ledger(),
             "accountant ledger does not independently replay")
    _require(SENSITIVITY * Fraction(1, GEOMETRIC_B) <= EPSILON_FRACTION,
             "privacy budget does not cover count sensitivity")
    _require(Fraction(str(EPSILON)) >= EPSILON_FRACTION, "serialized epsilon rounds inward")
    model = RecipientModel(package)
    _require(_read(output / "export-verification.json") == {
        "format_version": "private-model-export/1", "profile": PROFILE,
        "recipient_package_sha256": package_hash, "model_replayed_from_noisy_counts": True,
        "allowed_recipient_files": ["recipient-package.json"], "recipient_schema_verified": True,
        "no_private_seed_or_raw_counts_exported": True}, "export verification mismatch")
    _require(_read(output / "utility-report.json") == _utility(model, x, y, train, test),
             "held-out utility does not replay from recipient model")
    controls = _read(output / "positive-controls.json")
    _require(controls == _positive_controls() and controls["passed"],
             "independent known-leak/null controls failed replay")
    red_team = _read(output / "red-team-report.json")
    _require(red_team.get("release_artifact_sha256") == package_hash,
             "exploratory attacks bind another model")
    _require(red_team.get("training_config_sha256") == frozen["files"]["training-config.json"],
             "exploratory attacks change configuration")
    _require(red_team.get("dataset_manifest_sha256") == frozen["files"]["data-manifest.json"],
             "exploratory attacks change input binding")
    _require(all(tool.get("can_clear") is False and tool.get("can_block") is False
                 for tool in red_team.get("tools", [])),
             "exploratory probes cannot become decision evidence")
    return {"policy": policy, "manifest": manifest, "package": package,
            "package_hash": package_hash, "completed_at": completed,
            "accountant_replayed": True, "complete_pipeline": True}

def _release(output: Path) -> ReleaseContract:
    digest = sha256_file(output / "recipient-package.json")
    return ReleaseContract.model_validate({
        "release_id": "private-wine-" + digest[:16], "owner": "Local public-data demo operator",
        "recipient": "Local tester receiving only inert model package",
        "purpose": "Evidence-supported model-only record-membership clearance; no institutional authorization.",
        "model_family": "linear_generalized_linear",
        "model_profile": {"task": "classification", "input_modalities": ["tabular"],
                          "output_modalities": ["tabular"], "training_paradigm": "supervised",
                          "component_model_families": [], "generative": False, "stateful": False,
                          "custom_task_definition": None},
        "protected_unit": "record", "artifact_path": "recipient-package.json",
        "artifact_sha256": digest, "interface": _interface(),
        "previous_release_ids": [], "expires_at": None,
    })

def _request(output: Path, verified: dict[str, Any], *, observed_at: datetime) -> AssessmentRequest:
    policy = verified["policy"]
    scope = _scope(verified["manifest"], policy.effective_from)
    threat, release = _threat(scope), _release(output)
    context = EvidenceContext(
        release_id=release.release_id, release_contract_sha256=sha256_bytes(canonical_json_bytes(release)),
        policy_sha256=sha256_file(output / "policy.json"), artifact_sha256=release.artifact_sha256,
        interface_sha256=sha256_bytes(canonical_json_bytes(release.interface)),
        population_scope_id=scope.scope_id, population_scope_sha256=population_scope_sha256(scope),
        decision_game_sha256=decision_game_sha256(threat, scope), observed_at=observed_at,
    )
    payload = {
        "analyzer": "dp", "threat_id": threat.threat_id, "population_scope_id": scope.scope_id,
        "epsilon": EPSILON, "delta": 0.0, "adjacency": "add/remove one accepted training record",
        "protected_unit": "record", "accountant": ACCOUNTANT,
        "accountant_replayed": verified["accountant_replayed"],
        "complete_pipeline": verified["complete_pipeline"], "fpr": TARGET_FPR,
        "secret_cardinality": None, "maximum_secret_prior": None,
        "pairwise_secret_relation_validated": False, "secret_prior_bound_validated": False,
        "evidence_context": context.model_dump(mode="json"),
    }
    descriptor = _descriptor()
    producer = EvidenceProducer(
        service_id=descriptor.service_id, service_version=descriptor.service_version,
        implementation_sha256=descriptor.implementation_sha256,
        configuration_sha256=sha256_file(output / "training-config.json"))
    value = DpInput.model_validate({
        **payload, "provenance": {
            "tool": PROVENANCE_TOOL, "tool_version": "1.0.0",
            "producer": producer.model_dump(mode="json"), "configuration_path": "training-config.json",
            "source_path": "dp-source.json",
            "source_sha256": sha256_bytes(canonical_json_bytes(payload) + b"\n"),
            "bound_fields": list(payload),
        },
    })
    return AssessmentRequest(
        policy=PolicyReference(policy_id=policy.policy_id, policy_version=policy.policy_version,
                               policy_path="policy.json", policy_sha256=sha256_file(output / "policy.json")),
        release=release, population_scopes=(scope,), threats=(threat,), analyzer_inputs=(value,))


def _certificate(output: Path, report: AssessmentReport) -> dict[str, Any]:
    return {
        "format_version": "private-model-clearance-certificate/1", "profile": PROFILE,
        "files": {name: sha256_file(output / name) for name in COMPLETED_FILES},
        "scope": CLEARANCE_SCOPE, "protected_unit": "record", "epsilon": EPSILON, "delta": 0.0,
        "membership_ceiling": report.decisions[0].upper_bound,
        "policy_tolerance": TOLERANCE, "target_fpr": TARGET_FPR,
        "verdict": report.overall_verdict.value, "training_executed": True,
        "authorization_eligible": False, "authorized": False, "deployed": False,
        "trust_boundary": "trusted-local execution and source-bound replay; not remote execution attestation",
        "limitations": list(LIMITATIONS),
    }

def verify_private_model_run(output: Path) -> dict[str, Any]:
    """Replay prospective/completed bindings without retraining or secret noise.

    Hashes bind retained artifacts and accepted installed source; they cannot
    attest execution on an adversarial machine.
    """
    output = Path(output).resolve(strict=True)
    verified = _verify_before_assessment(output)
    request = AssessmentRequest.model_validate(_read(output / "assessment-request.json"))
    _require(len(request.analyzer_inputs) == 1
             and isinstance(request.analyzer_inputs[0], DpInput),
             "private clearance requires exactly its supported DP evidence")
    value = request.analyzer_inputs[0]
    _require(verified["completed_at"] <= value.evidence_context.observed_at <= _now(),
             "DP evidence chronology changed")
    _require(request == _request(output, verified, observed_at=value.evidence_context.observed_at),
             "assessment request does not replay from verified training evidence")
    _require(_read(output / "dp-source.json") ==
             value.model_dump(mode="json", exclude={"provenance"}),
             "DP source differs from verifier-derived contract")
    certificate = _read(output / "clearance-certificate.json")
    _require(set(certificate) == {
        "format_version", "profile", "files", "scope", "protected_unit", "epsilon", "delta",
        "membership_ceiling", "policy_tolerance", "target_fpr", "verdict", "training_executed",
        "authorization_eligible", "authorized", "deployed", "trust_boundary", "limitations"},
        "unexpected clearance certificate fields")
    _require(set(certificate["files"]) == set(COMPLETED_FILES),
             "completed evidence inventory changed")
    for name, expected in certificate["files"].items():
        path = output / name
        _require(path.is_file() and not path.is_symlink() and sha256_file(path) == expected,
                 "completed evidence changed: " + name)
    retained = AssessmentReport.model_validate(_read(output / "assessment-report.json"))
    replayed = AssuranceEngine().assess(request, output)
    _require(retained.model_dump(mode="json", exclude={"created_at"}) ==
             replayed.model_dump(mode="json", exclude={"created_at"}),
             "saved assessment does not replay through native engine")
    _require(certificate == _certificate(output, replayed),
             "certificate differs from native assessment and verified bindings")
    return {
        "verified": True, "clearance_profile": PROFILE, "clearance_scope": CLEARANCE_SCOPE,
        "verdict": replayed.overall_verdict.value, "accountant_replayed": True,
        "complete_pipeline": True, "recipient_package": "recipient-package.json",
        "recipient_package_sha256": verified["package_hash"],
        "certificate_sha256": sha256_file(output / "clearance-certificate.json"),
        "release_authorized": False, "protected_unit": "record",
        "epsilon": EPSILON, "delta": 0.0,
        "membership_ceiling": replayed.decisions[0].upper_bound,
        "scope_limitations": list(LIMITATIONS),
    }

def run_private_model_clearance(output: Path) -> dict[str, Any]:
    """Train one real Wine classifier and assess only its recipient package."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _require(not any(output.iterdir()), "private clearance needs a fresh empty output directory")
    x, y, train, test, manifest = _benchmark()
    timestamp = _now()
    _write(output / "training-config.json", training_configuration())
    _write(output / "data-manifest.json", manifest)
    _write(output / "evaluation-plan.json", _evaluation_plan())
    _write(output / "selection-policy.json", {
        "profile": PROFILE, "rule": "retain first and only fit; no utility or verdict based selection"})
    _write(output / "policy.json", _policy(
        timestamp, sha256_file(output / "training-config.json"),
        sha256_file(output / "selection-policy.json")))
    for name in SOURCE_FILES:
        path = output / "source-snapshots" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((Path(__file__).parent / name).read_bytes())
    _write(output / "evidence-freeze.json", {
        "format_version": "private-model-freeze/1", "profile": PROFILE,
        "frozen_at": _iso(_now()),
        "files": {name: sha256_file(output / name)
                  for name in (*FROZEN_FILES, *("source-snapshots/" + item for item in SOURCE_FILES))},
        "source_sha256s": _source_hashes(),
    })
    started = _now()
    package = fit_private_model(x[train], y[train])
    _write(output / "recipient-package.json", package)
    completed = _now()
    model = RecipientModel(_read(output / "recipient-package.json"))
    _write(output / "accountant-ledger.json", _ledger())
    _write(output / "training-receipt.json", {
        "format_version": "private-model-training-receipt/1", "profile": PROFILE,
        "training_started_at": _iso(started), "training_completed_at": _iso(completed),
        "training_executed": True, "fits": 1,
        "source_sha256": sha256_file(Path(__file__)),
        "configuration_sha256": sha256_file(output / "training-config.json"),
        "training_input_sha256": manifest["accepted_training_input_sha256"],
        "recipient_package_sha256": sha256_file(output / "recipient-package.json"),
        "randomness": training_configuration()["randomness"], "trainer": TRAINER,
    })
    utility = _utility(model, x, y, train, test)
    _write(output / "utility-report.json", utility)
    _write(output / "positive-controls.json", _positive_controls())
    _write(output / "export-verification.json", {
        "format_version": "private-model-export/1", "profile": PROFILE,
        "recipient_package_sha256": sha256_file(output / "recipient-package.json"),
        "model_replayed_from_noisy_counts": True,
        "allowed_recipient_files": ["recipient-package.json"], "recipient_schema_verified": True,
        "no_private_seed_or_raw_counts_exported": True,
    })
    from .red_team import RedTeamConfig, RedTeamTarget
    from .tabular_red_team import run_tabular_suite
    red_team = run_tabular_suite(
        RedTeamTarget(PRESET, "categorical-naive-bayes", model, x[train], y[train], x[test], y[test]),
        RedTeamConfig(seed=3407, membership_repetitions=2))
    for tool in red_team["tools"]:
        if tool["tool"] == "structural_disclosure" and tool["status"] == "completed":
            tool["result"] = {
                "unsupported": True,
                "reason": "No calibrated structural-parameter adapter for inert categorical count model.",
                "exploratory_diagnostics": tool["result"]}
            tool["status"] = "unsupported"
    red_team["execution_summary"] = {
        status: sum(tool["status"] == status for tool in red_team["tools"])
        for status in ("completed", "failed", "unsupported")}
    red_team["status"] = ("incomplete" if red_team["execution_summary"]["unsupported"]
                           or red_team["execution_summary"]["failed"] else "completed")
    red_team["release_artifact_sha256"] = sha256_file(output / "recipient-package.json")
    red_team["training_config_sha256"] = sha256_file(output / "training-config.json")
    red_team["dataset_manifest_sha256"] = sha256_file(output / "data-manifest.json")
    red_team["coverage_gaps"].append(
        "Categorical tree structure, structural parameter accounting and target retraining adapters unsupported.")
    red_team["coverage_gaps"].append(
        "Independent DP certificate covers only declared model-only membership mechanism; these attacks remain exploratory.")
    _write(output / "red-team-report.json", red_team)
    verified = _verify_before_assessment(output)
    request = _request(output, verified, observed_at=_now())
    _write(output / "dp-source.json",
           request.analyzer_inputs[0].model_dump(mode="json", exclude={"provenance"}))
    _write(output / "assessment-request.json", request)
    report = AssuranceEngine().assess(request, output)
    _write(output / "assessment-report.json", report)
    _write(output / "clearance-certificate.json", _certificate(output, report))
    verification = verify_private_model_run(output)
    warnings = [] if utility["beats_baseline"] else [
        "Held-out utility does not beat public training-majority baseline; no refit or selection performed."]
    result = {
        "demo": "real-private-model-clearance", "preset": PRESET, "trainer": TRAINER,
        "training_executed": True, "real_training_executed": True,
        "training": {"utility": utility, "warnings": warnings},
        "dataset": {key: manifest[key] for key in ("name", "rows", "features", "source_features")},
        "red_team": red_team, "component_comparisons": [], "warnings": warnings,
        "implementation_sha256": sha256_file(Path(__file__)),
        "verdict": report.overall_verdict.value, "assessment_eligible": True,
        "authorization_eligible": False, "authorized": False, "deployed": False,
        "release_authorized": False, "clearance_profile": PROFILE,
        "clearance_scope": CLEARANCE_SCOPE,
        "recipient_artifact": "job/artifacts/recipient-package.json",
        "candidate": "recipient-package.json", "request": "assessment-request.json",
        "family_plan": "evaluation-plan.json", "report": "assessment-report.json",
        "clearance": verification, "limitations": list(LIMITATIONS),
    }
    _write(output / "training-result.json", result)
    _write(output / "result.json", result)
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description="Real Wine DP model-only training or inert package prediction.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--predict-package", type=Path)
    parser.add_argument("--alcohol", type=float)
    parser.add_argument("--proline", type=float)
    args = parser.parse_args()
    if args.predict_package:
        if args.alcohol is None or args.proline is None:
            parser.error("--predict-package requires --alcohol and --proline")
        model = RecipientModel(_read(args.predict_package))
        probabilities = model.predict_proba([[args.alcohol, args.proline]])[0]
        print(json.dumps({"predicted_class": int(model.classes_[probabilities.argmax()]),
                          "class_probabilities": probabilities.tolist(),
                          "scope": "standalone inert model prediction; not a new assessment"}))
    else:
        if args.alcohol is not None or args.proline is not None:
            parser.error("--alcohol and --proline are only valid with --predict-package")
        result = run_private_model_clearance(args.output.resolve())
        print(json.dumps({"verdict": result["verdict"],
                          "clearance_scope": result["clearance_scope"], "authorized": False}))

if __name__ == "__main__":
    main()

