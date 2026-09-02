#!/usr/bin/env python3
"""Run the real-data LLM composition-scaling experiment.

The primary experiment is a 3-model x 3-scale x 5-training-seed matrix of
fresh-model cells.  Every scale/seed bundle evaluates all seven non-empty
model-loss subsets before and after training.  A separately labelled
cumulative trajectory is collected from the 8,192-row/seed-3407 cell and is
never treated as independent scale evidence.

Only aggregate, non-authorizing records are durable.  A hash-chained journal
contains one hook-microbenchmark bundle and fifteen complete scale/seed
bundles.  An interrupted model or bundle is rerun; no record identifiers,
per-example values, dialogue, token arrays, raw telemetry, or weights are
written.  RUN_COMPLETE.json is published last and only after exact closure.
"""

from __future__ import annotations

import argparse
import bisect
import gc
import hashlib
import importlib.util
import json
import math
import os
import platform
import random
import re
import resource
import statistics
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = Path(__file__).resolve()
DEFAULT_CONFIG_PATH = ROOT / "reproduction" / "composition-scaling" / "llm-config.json"
DEFAULT_CACHE_DIR = ROOT / "output" / "llm-training-hook" / "cache"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_BASENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAX_CONFIG_BYTES = 256 * 1024
MAX_JOURNAL_LINE_BYTES = 16 * 1024 * 1024
EXPECTED_BASELINE_CONFIG_SHA256 = "39e5b5fe8eed4ebb1d512063d6e13a0e8f24656f9043063e879bd0d5d5141480"
EXPECTED_BASELINE_RUNNER_SHA256 = "8b0bca73293e20232ac45e35b2762e254977fbdbe09f70967be257ee05719ffd"
EXPECTED_HOOK_SHA256 = "595de99355974866524ca1e11c0cd4d2d14c80a0846657daea36d66ee26ff33c"
# Filled after the frozen JSON profile is finalized.  Both the file and
# canonical digests are checked, so whitespace drift and semantic drift fail.
EXPECTED_CONFIG_FILE_SHA256 = "4924a2a4bf3f5176d28793a10295e7b7d50c5e007011a8f0d8cd06b90ba4f416"
EXPECTED_CONFIG_CANONICAL_SHA256 = "d9fe26d95dc9568d9bfd48d42e9265cd7ce5a4c8de3021477f6d6a7ef9b77d8a"
MODEL_KEYS = ("distilgpt2", "meta-opt-125m", "pythia-160m")
TRAINING_SEEDS = (3407, 499625614, 4288481424, 2669540432, 2937338177)
TRAIN_SCALES = (2048, 4096, 8192)
TRAJECTORY_ROWS = (0, 1024, 2048, 4096, 8192)
MODEL_SUBSETS = (
    ("distilgpt2",),
    ("meta-opt-125m",),
    ("pythia-160m",),
    ("distilgpt2", "meta-opt-125m"),
    ("distilgpt2", "pythia-160m"),
    ("meta-opt-125m", "pythia-160m"),
    ("distilgpt2", "meta-opt-125m", "pythia-160m"),
)
AUTHORITY = {
    "experimental_only": True,
    "assessment_input_emitted": False,
    "attack_battery_eligible": False,
    "authorization_eligible": False,
    "authorization_granted": False,
    "can_clear": False,
    "can_block": False,
    "requires_approved_recollection": True,
    "decision": "no_release_authorization",
}


class ResourceBudgetExceeded(RuntimeError):
    """Raised when the registered wall/deadline/GPU-memory budget is crossed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_json_object(payload: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    _require(isinstance(decoded, dict), "configuration must be a JSON object")
    return decoded


def _all_nonempty_subsets(keys: Sequence[str]) -> list[list[str]]:
    result: list[list[str]] = []
    for size in range(1, len(keys) + 1):
        for mask in range(1, 1 << len(keys)):
            subset = [keys[index] for index in range(len(keys)) if mask & (1 << index)]
            if len(subset) == size:
                result.append(subset)
    return result


def validate_config(raw: dict[str, Any], *, enforce_frozen_hash: bool = True) -> dict[str, Any]:
    """Validate exact experiment closure and every non-authorizing invariant."""

    expected_top = {
        "schema_version",
        "experiment_id",
        "experimental_only",
        "assessment_input_emitted",
        "attack_battery_eligible",
        "authorization_eligible",
        "can_clear",
        "can_block",
        "decision",
        "requires_approved_recollection",
        "baseline_binding",
        "workload",
        "composition",
        "hook_profiles",
        "release_interfaces",
        "release_policy",
        "resource_budget",
        "output",
    }
    _require(set(raw) == expected_top, "composition config top-level closure mismatch")
    _require(raw.get("schema_version") == "1.0", "schema_version must be 1.0")
    _require(
        raw.get("experiment_id") == "llm-composition-scaling-wildchat-three-model-v1",
        "experiment_id differs from the frozen profile",
    )
    for key in (
        "assessment_input_emitted",
        "attack_battery_eligible",
        "authorization_eligible",
        "can_clear",
        "can_block",
    ):
        _require(raw.get(key) is False, f"{key} must remain false")
    _require(raw.get("experimental_only") is True, "experimental_only must remain true")
    _require(raw.get("decision") == "no_release_authorization", "decision must deny authorization")
    _require(raw.get("requires_approved_recollection") is True, "approved recollection must be required")

    binding = raw.get("baseline_binding")
    _require(isinstance(binding, dict), "baseline_binding must be an object")
    _require(
        binding.get("config_path") == "reproduction/llm-training-hook/config.json"
        and binding.get("config_sha256") == EXPECTED_BASELINE_CONFIG_SHA256
        and binding.get("runner_path") == "scripts/run_llm_training_hook_audit.py"
        and binding.get("runner_sha256") == EXPECTED_BASELINE_RUNNER_SHA256
        and binding.get("hook_path") == "scripts/llm_training_hooks.py"
        and binding.get("hook_sha256") == EXPECTED_HOOK_SHA256,
        "baseline source binding mismatch",
    )
    dataset = binding.get("dataset", {})
    _require(
        dataset == {
            "id": "allenai/WildChat-4.8M",
            "revision": "c827c6df8fcf008219ffaffa4d1dd77491099367",
            "file": "data/train-00000-of-00086.parquet",
            "sha256": "6df660dca78dd92b865bef09b928992ceb6c913b4f06082315876a5997ad2eaa",
            "bytes": 125527585,
            "selected_rows": 9216,
            "train_rows": 8192,
            "holdout_rows": 1024,
            "selection_seed": 3407,
        },
        "WildChat binding differs from the completed run",
    )
    registered_models = binding.get("models")
    _require(isinstance(registered_models, list), "baseline model registry must be a list")
    _require([item.get("key") for item in registered_models] == list(MODEL_KEYS), "model order mismatch")
    expected_revisions = (
        "2290a62682d06624634c1f46a6ad5be0f47f38aa",
        "27dcfa74d334bc871f3234de431e71c6eeba5dd6",
        "50f5173d932e8e61f858120bcb800b97af589f46",
    )
    _require(
        tuple(item.get("revision") for item in registered_models) == expected_revisions,
        "model revisions differ from the frozen registry",
    )

    workload = raw.get("workload", {})
    _require(tuple(workload.get("training_seeds", [])) == TRAINING_SEEDS, "training seed closure mismatch")
    _require(tuple(workload.get("independent_train_scales", [])) == TRAIN_SCALES, "scale closure mismatch")
    _require(workload.get("independent_fresh_model_cells") == 45, "exactly 45 fresh model cells are required")
    _require(
        workload.get("fresh_model_initialization_per_model_scale_training_seed_cell") is True,
        "every primary cell must start from fresh model weights",
    )
    _require(workload.get("shared_dataset_split") is True, "all cells must share the registered split")
    _require(workload.get("batch_size") == 16, "batch size must remain 16")
    _require(workload.get("candidate_member_pool_rows") == 1024, "member pool must remain 1,024")
    _require(workload.get("candidate_nonmember_pool_rows") == 1024, "nonmember pool must remain 1,024")
    checkpoints = workload.get("secondary_cumulative_trajectory_checkpoints", [])
    _require(
        [(item.get("exposed_rows"), item.get("optimizer_steps")) for item in checkpoints]
        == [(rows, rows // 16) for rows in TRAJECTORY_ROWS],
        "secondary trajectory closure mismatch",
    )
    _require(workload.get("secondary_trajectory_training_seed") == TRAINING_SEEDS[0], "trajectory seed mismatch")
    _require(workload.get("secondary_trajectory_is_independent_scale_evidence") is False, "trajectory cannot be scale evidence")
    _require(workload.get("persist_model_weights") is False, "model weights must never be persisted")

    composition = raw.get("composition", {})
    _require(tuple(composition.get("model_keys", [])) == MODEL_KEYS, "composition model keys mismatch")
    _require(
        composition.get("nonempty_model_subsets") == [list(item) for item in MODEL_SUBSETS]
        == _all_nonempty_subsets(MODEL_KEYS),
        "all and only seven nonempty model subsets are required",
    )
    _require(tuple(composition.get("partition_seeds", [])) == TRAINING_SEEDS, "partition seed closure mismatch")
    _require(composition.get("suite_export_partition_seed") == TRAINING_SEEDS[0], "suite export partition seed mismatch")
    _require(composition.get("calibration_per_class") == 256, "calibration arm must remain 256/class")
    _require(composition.get("audit_per_class") == 256, "audit arm must remain 256/class")
    bootstrap = composition.get("bootstrap", {})
    _require(
        bootstrap.get("enabled") is True
        and bootstrap.get("replicates") == 1000
        and bootstrap.get("confidence_level") == 0.95
        and bootstrap.get("threshold_recalibrated_per_replicate") is False,
        "bootstrap profile mismatch",
    )
    _require(composition.get("causal_interpretation") is False, "causal interpretation is forbidden")
    _require(composition.get("monotonicity_assumed") is False, "monotonicity cannot be assumed")
    _require(composition.get("powered_for_release") is False, "screens are not powered for release")
    _require(composition.get("best_singleton_primary_contrast") is False, "best-singleton contrast is forbidden")

    hooks = raw.get("hook_profiles", {})
    _require(
        hooks.get("profiles") == [
            {"name": "none", "module_selection": "disabled"},
            {"name": "early", "module_selection": "first_registered_hook_module"},
            {"name": "full", "module_selection": "all_registered_hook_modules"},
        ],
        "hook profile closure mismatch",
    )
    _require(hooks.get("training_profile") == "full", "primary training must use full hooks")
    for key in ("raw_event_stream_persisted", "raw_tensors_retained", "raw_tokens_retained", "raw_gradients_retained"):
        _require(hooks.get(key) is False, f"{key} must remain false")
    micro = hooks.get("microbenchmark", {})
    _require(micro.get("profile_order_by_round") == [
        ["none", "early", "full"],
        ["early", "full", "none"],
        ["full", "none", "early"],
    ], "microbenchmark order must remain balanced")

    interfaces = raw.get("release_interfaces")
    _require(isinstance(interfaces, list) and len(interfaces) == 11, "exact release-interface matrix required")
    interface_keys = [item.get("key") for item in interfaces]
    _require(len(interface_keys) == len(set(interface_keys)), "release interface keys must be unique")
    for interface in interfaces:
        _require(set(interface) == {
            "key",
            "generated_token_log_probabilities",
            "arbitrary_candidate_scorers",
            "white_box_model_keys",
            "training_roster",
            "training_roster_membership_protected",
        }, "release interface closure mismatch")
        for field in ("arbitrary_candidate_scorers", "white_box_model_keys"):
            values = interface[field]
            _require(isinstance(values, list) and len(values) == len(set(values)), f"{field} must be unique")
            _require(set(values) <= set(MODEL_KEYS), f"{field} contains an unknown model")

    policy = raw.get("release_policy", {})
    for key in (
        "assessment_input_emitted",
        "attack_battery_eligible",
        "can_clear",
        "can_block",
        "authorization_eligible",
        "authorization_granted",
        "assessment_complete",
    ):
        _require(policy.get(key) is False, f"release_policy.{key} must remain false")
    _require(policy.get("requires_approved_recollection") is True, "release policy must require recollection")
    _require(policy.get("decision") == "no_release_authorization", "release policy decision mismatch")

    budget = raw.get("resource_budget", {})
    _require(budget.get("maximum_gpu_hours") == 12, "GPU-hour budget must remain 12")
    _require(
        budget.get("peak_gpu_allocated_bytes_ceiling") == 20 * 1024**3
        and budget.get("peak_gpu_reserved_bytes_ceiling") == 20 * 1024**3,
        "GPU-memory ceilings must remain 20 GiB",
    )
    _require(
        budget.get("peak_host_rss_bytes_ceiling") == 20 * 1024**3
        and budget.get("aggregate_artifact_bytes_ceiling") == 20 * 1024**3,
        "host-RSS and aggregate-artifact ceilings must remain 20 GiB",
    )
    _require(
        budget.get("check_host_rss_alongside_every_budget_and_gpu_check") is True
        and budget.get("check_aggregate_artifact_bytes_before_append_and_completion") is True,
        "host and artifact ceiling checks must remain mandatory",
    )
    _require(budget.get("budget_breach_semantics") == "fail_closed_without_completion_manifest", "budget must fail closed")

    output = raw.get("output", {})
    _require(
        output.get("directory") == "output/composition-scaling/llm"
        and output.get("run_directory_pattern") == "output/composition-scaling/llm/{run_id}"
        and output.get("json_report") == "llm-composition-scaling-report.json"
        and output.get("markdown_report") == "llm-composition-scaling-report.md"
        and output.get("completion_manifest") == "RUN_COMPLETE.json"
        and output.get("checkpoint_journal") == "COMPLETED_CELLS.jsonl",
        "output contract mismatch",
    )
    names = [output[key] for key in ("json_report", "markdown_report", "completion_manifest", "checkpoint_journal")]
    _require(len(names) == len(set(names)), "output artifact names must be unique")
    _require(all(SAFE_BASENAME.fullmatch(name) is not None for name in names), "output names must be safe basenames")
    _require(output.get("expected_checkpoint_records") == 16, "journal must close at exactly 16 records")
    for key in (
        "persist_per_example_values",
        "persist_record_identifiers",
        "persist_dialogue_text",
        "persist_model_weights",
        "persist_raw_telemetry_events",
    ):
        _require(output.get(key) is False, f"output.{key} must remain false")

    if enforce_frozen_hash:
        _require(
            EXPECTED_CONFIG_CANONICAL_SHA256 != "TO_BE_FINALIZED"
            and canonical_sha256(raw) == EXPECTED_CONFIG_CANONICAL_SHA256,
            "composition config differs from the frozen canonical profile",
        )
    return raw


def load_config(path: Path) -> tuple[dict[str, Any], bytes]:
    _require(path.is_file() and not path.is_symlink(), "config must be a regular non-symlink file")
    _require(path.stat().st_size <= MAX_CONFIG_BYTES, "configuration exceeds its byte bound")
    payload = path.read_bytes()
    _require(
        EXPECTED_CONFIG_FILE_SHA256 != "TO_BE_FINALIZED"
        and hashlib.sha256(payload).hexdigest() == EXPECTED_CONFIG_FILE_SHA256,
        "composition config file bytes differ from the frozen profile",
    )
    return validate_config(_strict_json_object(payload)), payload


def _percentile(values: Sequence[float], probability: float) -> float:
    _require(bool(values), "percentile input must not be empty")
    _require(0.0 <= probability <= 1.0, "percentile probability is outside [0,1]")
    ordered = sorted(float(value) for value in values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def numeric_summary(values: Sequence[float]) -> dict[str, float | int]:
    _require(bool(values), "numeric summary requires observations")
    converted = [float(value) for value in values]
    _require(all(math.isfinite(value) for value in converted), "numeric summary contains non-finite values")
    mean = sum(converted) / len(converted)
    variance = sum((value - mean) ** 2 for value in converted) / len(converted)
    return {
        "count": len(converted),
        "minimum": min(converted),
        "p05": _percentile(converted, 0.05),
        "median": _percentile(converted, 0.5),
        "mean": mean,
        "p95": _percentile(converted, 0.95),
        "maximum": max(converted),
        "population_standard_deviation": math.sqrt(variance),
    }


def roc_auc(member_scores: Sequence[float], nonmember_scores: Sequence[float]) -> float:
    _require(bool(member_scores) and bool(nonmember_scores), "ROC AUC requires both classes")
    ordered_nonmembers = sorted(float(value) for value in nonmember_scores)
    wins = 0.0
    for member in member_scores:
        left = bisect.bisect_left(ordered_nonmembers, float(member))
        right = bisect.bisect_right(ordered_nonmembers, float(member))
        wins += left + 0.5 * (right - left)
    return wins / (len(member_scores) * len(nonmember_scores))


def balanced_accuracy(member_scores: Sequence[float], nonmember_scores: Sequence[float], threshold: float) -> float:
    _require(bool(member_scores) and bool(nonmember_scores), "balanced accuracy requires both classes")
    tpr = sum(float(value) >= threshold for value in member_scores) / len(member_scores)
    tnr = sum(float(value) < threshold for value in nonmember_scores) / len(nonmember_scores)
    return (tpr + tnr) / 2.0


def calibrate_threshold(member_scores: Sequence[float], nonmember_scores: Sequence[float]) -> float:
    values = sorted(set(float(value) for value in [*member_scores, *nonmember_scores]))
    _require(bool(values), "calibration scores are empty")
    candidates = [values[0] - 1.0, *values]
    candidates.extend((left + right) / 2.0 for left, right in zip(values, values[1:]))
    candidates.append(values[-1] + 1.0)
    return max(
        candidates,
        key=lambda item: (
            balanced_accuracy(member_scores, nonmember_scores, item),
            item,
        ),
    )


def _screen_metrics(member_scores: Sequence[float], nonmember_scores: Sequence[float], threshold: float) -> dict[str, float]:
    true_positive_rate = sum(float(value) >= threshold for value in member_scores) / len(member_scores)
    false_positive_rate = sum(float(value) >= threshold for value in nonmember_scores) / len(nonmember_scores)
    return {
        "balanced_accuracy": (true_positive_rate + (1.0 - false_positive_rate)) / 2.0,
        "roc_auc": roc_auc(member_scores, nonmember_scores),
        "membership_advantage_at_threshold": true_positive_rate - false_positive_rate,
    }


def deterministic_bootstrap_interval(
    member_scores: Sequence[float],
    nonmember_scores: Sequence[float],
    *,
    threshold: float,
    replicates: int,
    confidence_level: float,
    seed: int,
) -> dict[str, Any]:
    """Stratified audit-arm percentile sensitivity intervals with fixed threshold."""

    _require(replicates >= 100, "bootstrap requires at least 100 replicates")
    _require(0.0 < confidence_level < 1.0, "confidence level must be inside (0,1)")
    rng = random.Random(int(seed))
    member_values = [float(value) for value in member_scores]
    nonmember_values = [float(value) for value in nonmember_scores]
    distributions = {
        "balanced_accuracy": [],
        "roc_auc": [],
        "membership_advantage_at_threshold": [],
    }
    for _ in range(replicates):
        sampled_members = [member_values[rng.randrange(len(member_values))] for _ in member_values]
        sampled_nonmembers = [nonmember_values[rng.randrange(len(nonmember_values))] for _ in nonmember_values]
        measured = _screen_metrics(sampled_members, sampled_nonmembers, threshold)
        for key, value in measured.items():
            distributions[key].append(value)
    alpha = (1.0 - confidence_level) / 2.0
    return {
        "method": "deterministic_stratified_audit_arm_percentile",
        "replicates": replicates,
        "confidence_level": confidence_level,
        "threshold_recalibrated_per_replicate": False,
        "sampling_unit": "candidate_training_record",
        "intervals": {
            key: {
                "lower": _percentile(values, alpha),
                "upper": _percentile(values, 1.0 - alpha),
            }
            for key, values in distributions.items()
        },
    }


def subset_key(model_keys: Sequence[str]) -> str:
    return "+".join(model_keys)


def _ordered_partition_keys(keys: Iterable[str], *, seed: int, arm: str, required: int) -> list[str]:
    ordered = sorted(
        keys,
        key=lambda key: hashlib.sha256(
            f"llm-composition:{seed}:{arm}:{key}".encode("utf-8")
        ).hexdigest(),
    )
    _require(len(ordered) >= required, f"{arm} candidate pool is too small")
    return ordered[:required]


def _pooled_standardization(
    calibration_member: Sequence[float], calibration_nonmember: Sequence[float]
) -> tuple[float, float]:
    pooled = [*map(float, calibration_member), *map(float, calibration_nonmember)]
    mean = sum(pooled) / len(pooled)
    scale = math.sqrt(sum((value - mean) ** 2 for value in pooled) / len(pooled))
    return mean, max(scale, 1e-12)


def build_subset_screens(
    losses_by_model: Mapping[str, Mapping[str, float]],
    member_keys: Sequence[str],
    nonmember_keys: Sequence[str],
    *,
    partition_seeds: Sequence[int],
    calibration_per_class: int,
    audit_per_class: int,
    bootstrap_replicates: int,
    confidence_level: float,
    checkpoint_steps: int,
) -> dict[str, Any]:
    """Build all seven composition screens without returning candidate keys."""

    _require(tuple(losses_by_model) == MODEL_KEYS, "loss matrix model order mismatch")
    member_set = set(member_keys)
    nonmember_set = set(nonmember_keys)
    _require(len(member_set) == len(member_keys), "member keys must be unique")
    _require(len(nonmember_set) == len(nonmember_keys), "nonmember keys must be unique")
    _require(member_set.isdisjoint(nonmember_set), "member/nonmember pools overlap")
    expected = member_set | nonmember_set
    for model_key, values in losses_by_model.items():
        _require(set(values) == expected, f"loss coverage mismatch for {model_key}")
        _require(all(math.isfinite(float(value)) for value in values.values()), "loss matrix is non-finite")

    required = calibration_per_class + audit_per_class
    partition_results: list[dict[str, Any]] = []
    for partition_seed in partition_seeds:
        selected_members = _ordered_partition_keys(member_keys, seed=partition_seed, arm="member", required=required)
        selected_nonmembers = _ordered_partition_keys(nonmember_keys, seed=partition_seed, arm="nonmember", required=required)
        cal_member_keys = selected_members[:calibration_per_class]
        audit_member_keys = selected_members[calibration_per_class:]
        cal_nonmember_keys = selected_nonmembers[:calibration_per_class]
        audit_nonmember_keys = selected_nonmembers[calibration_per_class:]

        standardized: dict[str, dict[str, list[float]]] = {}
        for model_key in MODEL_KEYS:
            losses = losses_by_model[model_key]
            calibration_members = [-float(losses[key]) for key in cal_member_keys]
            calibration_nonmembers = [-float(losses[key]) for key in cal_nonmember_keys]
            mean, scale = _pooled_standardization(calibration_members, calibration_nonmembers)
            standardized[model_key] = {
                "calibration_members": [(value - mean) / scale for value in calibration_members],
                "calibration_nonmembers": [(value - mean) / scale for value in calibration_nonmembers],
                "audit_members": [(-float(losses[key]) - mean) / scale for key in audit_member_keys],
                "audit_nonmembers": [(-float(losses[key]) - mean) / scale for key in audit_nonmember_keys],
            }

        subset_results: list[dict[str, Any]] = []
        for model_subset in MODEL_SUBSETS:
            def compose(field: str) -> list[float]:
                columns = [standardized[key][field] for key in model_subset]
                _require(len({len(column) for column in columns}) == 1, "composition columns differ in length")
                rows = zip(*columns)
                return [sum(row) / len(model_subset) for row in rows]

            calibration_members = compose("calibration_members")
            calibration_nonmembers = compose("calibration_nonmembers")
            audit_members = compose("audit_members")
            audit_nonmembers = compose("audit_nonmembers")
            threshold = calibrate_threshold(calibration_members, calibration_nonmembers)
            metrics = _screen_metrics(audit_members, audit_nonmembers, threshold)
            derived_seed = int.from_bytes(
                hashlib.sha256(
                    f"bootstrap:{partition_seed}:{checkpoint_steps}:{subset_key(model_subset)}".encode("utf-8")
                ).digest()[:8],
                "big",
            )
            bootstrap = deterministic_bootstrap_interval(
                audit_members,
                audit_nonmembers,
                threshold=threshold,
                replicates=bootstrap_replicates,
                confidence_level=confidence_level,
                seed=derived_seed,
            )
            subset_results.append({
                "model_keys": list(model_subset),
                "subset_size": len(model_subset),
                "calibration_threshold": threshold,
                "calibration_members": calibration_per_class,
                "calibration_nonmembers": calibration_per_class,
                "audit_members": audit_per_class,
                "audit_nonmembers": audit_per_class,
                "metrics": metrics,
                "bootstrap_sensitivity_interval": bootstrap,
                "evidence_semantics": "descriptive_unpowered_recipient_conditional_screen",
                **AUTHORITY,
            })

        singleton_metrics = {
            item["model_keys"][0]: item["metrics"]
            for item in subset_results
            if item["subset_size"] == 1
        }
        for item in subset_results:
            members = item["model_keys"]
            reference = {
                metric: sum(singleton_metrics[key][metric] for key in members) / len(members)
                for metric in (
                    "balanced_accuracy",
                    "roc_auc",
                    "membership_advantage_at_threshold",
                )
            }
            item["primary_contrast_vs_mean_member_singletons"] = {
                metric: item["metrics"][metric] - reference[metric]
                for metric in reference
            }
        partition_results.append({
            "partition_seed": int(partition_seed),
            "partition_sizes": {
                "calibration_members": calibration_per_class,
                "calibration_nonmembers": calibration_per_class,
                "audit_members": audit_per_class,
                "audit_nonmembers": audit_per_class,
            },
            "candidate_keys_persisted": False,
            "subsets": subset_results,
        })

    sensitivity: list[dict[str, Any]] = []
    for model_subset in MODEL_SUBSETS:
        key = subset_key(model_subset)
        matched = [
            next(item for item in partition["subsets"] if subset_key(item["model_keys"]) == key)
            for partition in partition_results
        ]
        sensitivity.append({
            "model_keys": list(model_subset),
            "metrics_across_partition_seeds": {
                metric: numeric_summary([item["metrics"][metric] for item in matched])
                for metric in (
                    "balanced_accuracy",
                    "roc_auc",
                    "membership_advantage_at_threshold",
                )
            },
            "primary_contrast_across_partition_seeds": {
                metric: numeric_summary([
                    item["primary_contrast_vs_mean_member_singletons"][metric]
                    for item in matched
                ])
                for metric in (
                    "balanced_accuracy",
                    "roc_auc",
                    "membership_advantage_at_threshold",
                )
            },
        })
    return {
        "checkpoint_optimizer_steps": checkpoint_steps,
        "partition_seed_count": len(partition_seeds),
        "partition_results": partition_results,
        "partition_sensitivity": sensitivity,
        "candidate_keys_persisted": False,
        "per_example_values_persisted": False,
        "causal_interpretation": False,
        "monotonicity_assumed": False,
        **AUTHORITY,
    }


def _source_snapshot(config_path: Path, config_bytes: bytes) -> dict[str, Any]:
    binding_paths = {
        "composition_config": config_path,
        "composition_runner": RUNNER_PATH,
        "baseline_config": ROOT / "reproduction" / "llm-training-hook" / "config.json",
        "baseline_runner": ROOT / "scripts" / "run_llm_training_hook_audit.py",
        "hook_implementation": ROOT / "scripts" / "llm_training_hooks.py",
    }
    for path in binding_paths.values():
        _require(path.is_file() and not path.is_symlink(), "bound source must be a regular non-symlink file")
    result = {f"{name}_sha256": sha256_file(path) for name, path in binding_paths.items()}
    _require(
        result["composition_config_sha256"] == hashlib.sha256(config_bytes).hexdigest(),
        "composition config changed during snapshot",
    )
    _require(result["baseline_config_sha256"] == EXPECTED_BASELINE_CONFIG_SHA256, "baseline config hash drift")
    _require(result["baseline_runner_sha256"] == EXPECTED_BASELINE_RUNNER_SHA256, "baseline runner hash drift")
    _require(result["hook_implementation_sha256"] == EXPECTED_HOOK_SHA256, "hook implementation hash drift")
    result["composition_config_canonical_sha256"] = EXPECTED_CONFIG_CANONICAL_SHA256
    result["source_paths_emitted"] = False
    return result


_BASELINE_MODULE: types.ModuleType | None = None


def load_verified_baseline_module() -> types.ModuleType:
    global _BASELINE_MODULE
    if _BASELINE_MODULE is not None:
        return _BASELINE_MODULE
    path = ROOT / "scripts" / "run_llm_training_hook_audit.py"
    _require(sha256_file(path) == EXPECTED_BASELINE_RUNNER_SHA256, "baseline helper runner hash mismatch")
    name = f"_mra_verified_baseline_{EXPECTED_BASELINE_RUNNER_SHA256}"
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, "unable to load verified baseline runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    _require(sha256_file(path) == EXPECTED_BASELINE_RUNNER_SHA256, "baseline helper changed while loading")
    _BASELINE_MODULE = module
    return module


def load_and_validate_baseline_config(config: dict[str, Any], baseline: types.ModuleType) -> dict[str, Any]:
    path = ROOT / config["baseline_binding"]["config_path"]
    _require(sha256_file(path) == EXPECTED_BASELINE_CONFIG_SHA256, "baseline config bytes changed")
    raw = _strict_json_object(path.read_bytes())
    validated = baseline.validate_config(raw)
    binding = config["baseline_binding"]
    _require(validated["experiment_id"] == binding["experiment_id"], "baseline experiment mismatch")
    _require(validated["dataset"]["id"] == binding["dataset"]["id"], "baseline dataset mismatch")
    _require(validated["dataset"]["revision"] == binding["dataset"]["revision"], "baseline dataset revision mismatch")
    _require(validated["dataset"]["sha256"] == binding["dataset"]["sha256"], "baseline dataset digest mismatch")
    _require([model["key"] for model in validated["models"]] == list(MODEL_KEYS), "baseline model order mismatch")
    _require(
        [model["revision"] for model in validated["models"]]
        == [model["revision"] for model in binding["models"]],
        "baseline model revision mismatch",
    )
    training = validated["training"]
    workload = config["workload"]
    for baseline_key, workload_key in (
        ("batch_size", "batch_size"),
        ("max_sequence_length", "max_sequence_length"),
        ("max_prompt_length", "max_prompt_length"),
        ("learning_rate", "learning_rate"),
        ("weight_decay", "weight_decay"),
        ("torch_dtype", "torch_dtype"),
    ):
        _require(training[baseline_key] == workload[workload_key], f"training binding mismatch: {baseline_key}")
    return validated


def _package_version(name: str) -> str:
    import importlib.metadata

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def runtime_identity(torch: Any, transformers: Any) -> dict[str, Any]:
    gpu = "unavailable"
    compute_capability: list[int] | None = None
    if torch.cuda.is_available():
        gpu = str(torch.cuda.get_device_name(0))
        compute_capability = list(torch.cuda.get_device_capability(0))
    return {
        "python": platform.python_version(),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "torch": str(torch.__version__),
        "transformers": str(transformers.__version__),
        "pyarrow": _package_version("pyarrow"),
        "safetensors": _package_version("safetensors"),
        "cuda_runtime": str(torch.version.cuda),
        "cudnn": int(torch.backends.cudnn.version() or 0),
        "gpu": gpu,
        "compute_capability": compute_capability,
        "cuda_device_count": int(torch.cuda.device_count()),
    }


def journal_context(
    config: dict[str, Any], source: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "experiment_id": config["experiment_id"],
        "configuration_canonical_sha256": canonical_sha256(config),
        "source": source,
        "runtime": runtime,
        "model_keys": list(MODEL_KEYS),
        "training_seeds": list(TRAINING_SEEDS),
        "independent_train_scales": list(TRAIN_SCALES),
        "dataset_file_sha256": config["baseline_binding"]["dataset"]["sha256"],
        "authority": dict(AUTHORITY),
    }


def expected_journal_keys() -> list[str]:
    return [
        "hook-microbenchmark-bundle",
        *[
            f"scale-{scale}-seed-{seed}"
            for scale in TRAIN_SCALES
            for seed in TRAINING_SEEDS
        ],
    ]


def _record_digest(record_without_digest: dict[str, Any]) -> str:
    return canonical_sha256(record_without_digest)


def _parse_journal(
    path: Path,
    *,
    context_sha256: str,
    repair_trailing_partial: bool,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    _require(path.is_file() and not path.is_symlink(), "journal must be a regular non-symlink file")
    _require((path.stat().st_mode & 0o777) == 0o600, "journal mode must remain 0600")
    payload = path.read_bytes()
    if payload and not payload.endswith(b"\n"):
        boundary = payload.rfind(b"\n") + 1
        trailing = payload[boundary:]
        _require(len(trailing) <= MAX_JOURNAL_LINE_BYTES, "journal trailing fragment exceeds its bound")
        _require(repair_trailing_partial, "journal has an unterminated trailing record; resume is required")
        with path.open("r+b") as stream:
            stream.truncate(boundary)
            stream.flush()
            os.fsync(stream.fileno())
        payload = payload[:boundary]
    lines = payload.splitlines()
    keys = expected_journal_keys()
    _require(len(lines) <= len(keys), "journal contains more than the exact expected records")
    records: list[dict[str, Any]] = []
    previous = "0" * 64
    for sequence, line in enumerate(lines):
        _require(len(line) <= MAX_JOURNAL_LINE_BYTES, "journal record exceeds its byte bound")
        record = _strict_json_object(line)
        _require(set(record) == {
            "schema_version",
            "sequence",
            "previous_sha256",
            "context_sha256",
            "record_type",
            "record_key",
            "payload",
            "record_sha256",
        }, "journal record closure mismatch")
        _require(record["schema_version"] == "1.0", "journal schema mismatch")
        _require(record["sequence"] == sequence, "journal sequence mismatch")
        _require(record["previous_sha256"] == previous, "journal predecessor mismatch")
        _require(record["context_sha256"] == context_sha256, "journal source/config/runtime context mismatch")
        _require(record["record_key"] == keys[sequence], "journal is not an exact expected-key prefix")
        expected_type = "hook_microbenchmark_bundle" if sequence == 0 else "scale_seed_model_bundle"
        _require(record["record_type"] == expected_type, "journal record type mismatch")
        candidate = dict(record)
        claimed = candidate.pop("record_sha256")
        replayed = _record_digest(candidate)
        _require(claimed == replayed, "journal record digest mismatch")
        previous = replayed
        _assert_aggregate_only(record["payload"])
        records.append(record)
    return records


def append_journal_record(
    path: Path,
    records: list[dict[str, Any]],
    *,
    context_sha256: str,
    record_type: str,
    record_key: str,
    payload: dict[str, Any],
    artifact_bytes_ceiling: int,
) -> dict[str, Any]:
    keys = expected_journal_keys()
    sequence = len(records)
    _require(sequence < len(keys), "journal is already complete")
    _require(record_key == keys[sequence], "attempted journal record is out of schedule")
    _assert_aggregate_only(payload)
    record = {
        "schema_version": "1.0",
        "sequence": sequence,
        "previous_sha256": records[-1]["record_sha256"] if records else "0" * 64,
        "context_sha256": context_sha256,
        "record_type": record_type,
        "record_key": record_key,
        "payload": payload,
    }
    record["record_sha256"] = _record_digest(record)
    encoded = canonical_json(record) + b"\n"
    _require(len(encoded) <= MAX_JOURNAL_LINE_BYTES, "journal record exceeds its byte bound")
    existing_bytes = path.stat().st_size if path.exists() else 0
    enforce_aggregate_artifact_budget(
        [existing_bytes, len(encoded)], artifact_bytes_ceiling
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.chmod(path, 0o600)
        written = 0
        while written < len(encoded):
            count = os.write(descriptor, encoded[written:])
            _require(count > 0, "journal append made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    records.append(record)
    return record


def _assert_aggregate_only(value: Any, *, path: str = "report") -> None:
    """Fail if a durable object contains a prohibited example-level surface."""

    forbidden_keys = {
        "record_id",
        "record_ids",
        "member_ids",
        "nonmember_ids",
        "member_keys",
        "nonmember_keys",
        "train_record_ids",
        "holdout_record_ids",
        "prompt",
        "response",
        "assistant",
        "user",
        "messages",
        "input_ids",
        "labels",
        "logits",
        "activations",
        "gradients",
        "events",
        "per_example",
        "model_weights",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            _require(key not in forbidden_keys, f"durable aggregate contains prohibited key at {path}.{key}")
            _assert_aggregate_only(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_aggregate_only(child, path=f"{path}[{index}]")
    elif isinstance(value, str):
        _require("/Users/" not in value and "/home/" not in value, f"durable aggregate discloses an absolute path at {path}")
    elif isinstance(value, float):
        _require(math.isfinite(value), f"durable aggregate contains non-finite number at {path}")


def host_peak_rss_bytes() -> int:
    observed = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return observed if platform.system() == "Darwin" else observed * 1024


class ExecutionBudget:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        previously_consumed_seconds: float,
        deadline_utc: datetime | None,
    ) -> None:
        self._started = time.perf_counter()
        self._previous = float(previously_consumed_seconds)
        self._maximum = float(config["resource_budget"]["maximum_gpu_hours"]) * 3600.0
        self._host_rss_ceiling = int(config["resource_budget"]["peak_host_rss_bytes_ceiling"])
        self._deadline = deadline_utc

    @property
    def consumed_seconds(self) -> float:
        return self._previous + (time.perf_counter() - self._started)

    @property
    def remaining_seconds(self) -> float:
        budget_remaining = self._maximum - self.consumed_seconds
        if self._deadline is None:
            return budget_remaining
        deadline_remaining = (self._deadline - datetime.now(timezone.utc)).total_seconds()
        return min(budget_remaining, deadline_remaining)

    def check(self, *, minimum_remaining_seconds: float = 0.0) -> None:
        if host_peak_rss_bytes() > self._host_rss_ceiling:
            raise ResourceBudgetExceeded(
                "peak host RSS ceiling exceeded; completion remains unpublished"
            )
        if self.remaining_seconds < minimum_remaining_seconds:
            raise ResourceBudgetExceeded(
                "registered wall/deadline budget would be exceeded; completion remains unpublished"
            )


def gpu_memory_snapshot(torch: Any, device: Any) -> dict[str, int]:
    if device.type != "cuda":
        return {
            "allocated_bytes": 0,
            "reserved_bytes": 0,
            "peak_allocated_bytes": 0,
            "peak_reserved_bytes": 0,
        }
    torch.cuda.synchronize(device)
    return {
        "allocated_bytes": int(torch.cuda.memory_allocated(device)),
        "reserved_bytes": int(torch.cuda.memory_reserved(device)),
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
    }


def enforce_gpu_memory_budget(snapshot: Mapping[str, int], config: dict[str, Any]) -> None:
    budget = config["resource_budget"]
    if int(snapshot["peak_allocated_bytes"]) > int(budget["peak_gpu_allocated_bytes_ceiling"]):
        raise ResourceBudgetExceeded("peak GPU allocated-byte ceiling exceeded")
    if int(snapshot["peak_reserved_bytes"]) > int(budget["peak_gpu_reserved_bytes_ceiling"]):
        raise ResourceBudgetExceeded("peak GPU reserved-byte ceiling exceeded")
    enforce_host_rss_budget(config)


def enforce_host_rss_budget(config: dict[str, Any]) -> int:
    observed = host_peak_rss_bytes()
    if observed > int(config["resource_budget"]["peak_host_rss_bytes_ceiling"]):
        raise ResourceBudgetExceeded("peak host RSS ceiling exceeded")
    return observed


def enforce_aggregate_artifact_budget(
    artifact_sizes: Sequence[int], ceiling_bytes: int
) -> int:
    _require(
        isinstance(ceiling_bytes, int) and not isinstance(ceiling_bytes, bool)
        and ceiling_bytes > 0,
        "aggregate artifact ceiling must be a positive integer",
    )
    converted = []
    for value in artifact_sizes:
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            "artifact sizes must be nonnegative integers",
        )
        converted.append(value)
    total = sum(converted)
    if total > ceiling_bytes:
        raise ResourceBudgetExceeded(
            "aggregate artifact byte ceiling exceeded; completion remains unpublished"
        )
    return total


def _parse_deadline(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    _require(parsed.tzinfo is not None, "deadline must include a timezone")
    return parsed.astimezone(timezone.utc)


def release_interface_matrix(config: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for interface in config["release_interfaces"]:
        available = set(interface["arbitrary_candidate_scorers"]) | set(interface["white_box_model_keys"])
        realizable = [
            list(model_subset)
            for model_subset in MODEL_SUBSETS
            if set(model_subset) <= available
        ]
        direct_disclosure = bool(
            interface["training_roster"]
            and interface["training_roster_membership_protected"]
        )
        results.append({
            "key": interface["key"],
            "contract_fragment_sha256": canonical_sha256(interface),
            "arbitrary_candidate_loss_model_keys": sorted(available, key=MODEL_KEYS.index),
            "realizable_model_loss_subsets": realizable,
            "generated_token_log_probabilities_are_arbitrary_candidate_scoring": False,
            "exact_protected_roster_direct_disclosure": direct_disclosure,
            "hypothetical_membership_gate": "BLOCKED_AND_REDESIGN_REQUIRED" if direct_disclosure else "INCONCLUSIVE",
            **AUTHORITY,
        })
    return results


def subset_release_route(model_subset: Sequence[str]) -> dict[str, Any]:
    contains_opt = "meta-opt-125m" in model_subset
    contains_pythia = "pythia-160m" in model_subset
    return {
        "model_keys": list(model_subset),
        "release_process_state": "BLOCKED" if contains_opt else "ASSESSMENT_INCOMPLETE",
        "meta_opt_noncommercial_research_license_gate": "BLOCKED" if contains_opt else "NOT_IN_SUBSET",
        "pythia_human_facing_policy_gate": "MANUAL_REVIEW_REQUIRED" if contains_pythia else "NOT_IN_SUBSET",
        "dataset_content_rights_gate": "LEGAL_REVIEW_REQUIRED",
        **AUTHORITY,
    }


def acquire_registered_dataset(
    baseline: types.ModuleType,
    baseline_config: dict[str, Any],
    cache_dir: Path,
    *,
    offline: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    catalog_path = baseline.download_verified_catalog(
        baseline_config, cache_dir / "catalog", offline=offline
    )
    _require(
        baseline_config["dataset"]["id"] in catalog_path.read_text(encoding="utf-8"),
        "pinned catalog does not contain the registered WildChat entry",
    )
    governance_paths = baseline.download_verified_dataset_governance(
        baseline_config, cache_dir / "dataset-governance", offline=offline
    )
    dataset_path = baseline.download_verified_dataset(
        baseline_config, cache_dir / "dataset", offline=offline
    )
    rows = baseline.load_dataset_rows(dataset_path)
    source_rows = len(rows)
    records, adapter = baseline.extract_wildchat_records(rows)
    del rows
    gc.collect()
    expected_scale = baseline_config["dataset"]["source_scale"]
    _require(source_rows == expected_scale["selected_shard_rows"], "source row count mismatch")
    _require(
        adapter["eligible_before_deduplication"]
        == expected_scale["selected_shard_eligible_before_deduplication"],
        "eligible pre-deduplication count mismatch",
    )
    _require(
        adapter["eligible_after_deduplication"]
        == expected_scale["selected_shard_eligible_after_deduplication"],
        "eligible post-deduplication count mismatch",
    )
    rows_config = baseline_config["dataset"]["rows"]
    train_records, holdout_records = baseline.select_records(
        records,
        int(baseline_config["dataset"]["seed"]),
        int(rows_config["total"]),
        int(rows_config["train"]),
    )
    eligible_pool_rows = len(records)
    del records
    gc.collect()
    split_integrity = baseline.validate_content_disjointness(train_records, holdout_records)
    risks = baseline.scan_dataset_risks([*train_records, *holdout_records])
    risk_counts = {
        key: value["record_count"]
        for key, value in risks.items()
        if isinstance(value, dict) and "record_count" in value
    }
    governance = {
        key: {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for key, path in sorted(governance_paths.items())
    }
    report = {
        "id": baseline_config["dataset"]["id"],
        "revision": baseline_config["dataset"]["revision"],
        "file_sha256": baseline_config["dataset"]["sha256"],
        "file_bytes": baseline_config["dataset"]["bytes"],
        "license": baseline_config["dataset"]["license"],
        "source_dataset_conversations": expected_scale["dataset_conversations"],
        "source_registered_shards": expected_scale["registered_shards"],
        "verified_shard_rows": source_rows,
        "eligible_pool_rows": eligible_pool_rows,
        "selected_rows": len(train_records) + len(holdout_records),
        "train_rows": len(train_records),
        "holdout_rows": len(holdout_records),
        "adapter": adapter,
        "split_integrity": split_integrity,
        "heuristic_risk_record_counts": dict(sorted(risk_counts.items())),
        "governance_artifacts": governance,
        "raw_source_cache_retained_for_offline_replay": True,
        "raw_source_cache_in_recipient_package": False,
        "raw_source_cache_requires_retention_and_deletion_policy": True,
        "source_identifiers_persisted": False,
        "dialogue_text_persisted": False,
    }
    _assert_aggregate_only(report)
    return train_records, holdout_records, report


def _load_tokenizer_and_snapshot(
    baseline: types.ModuleType,
    model_config: dict[str, Any],
    baseline_config: dict[str, Any],
    train_records: Sequence[dict[str, Any]],
    holdout_records: Sequence[dict[str, Any]],
    cache_dir: Path,
    *,
    offline: bool,
) -> dict[str, Any]:
    from transformers import AutoTokenizer

    snapshot, cache_manifest = baseline.download_verified_model_snapshot(
        model_config, cache_dir, offline=offline
    )
    load_options = {
        "local_files_only": True,
        "trust_remote_code": False,
        "token": False,
    }
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), **load_options)
    if tokenizer.pad_token_id is None:
        _require(tokenizer.eos_token_id is not None, "tokenizer has neither pad nor EOS token")
        tokenizer.pad_token = tokenizer.eos_token
    training = baseline_config["training"]
    bounds = training["pretokenization_bounds"]
    train_items, train_summary = baseline.tokenize_records(
        train_records,
        tokenizer,
        max_length=int(training["max_sequence_length"]),
        max_prompt_length=int(training["max_prompt_length"]),
        max_field_utf8_bytes=int(bounds["max_field_utf8_bytes"]),
        max_record_utf8_bytes=int(bounds["max_record_utf8_bytes"]),
    )
    holdout_items, holdout_summary = baseline.tokenize_records(
        holdout_records,
        tokenizer,
        max_length=int(training["max_sequence_length"]),
        max_prompt_length=int(training["max_prompt_length"]),
        max_field_utf8_bytes=int(bounds["max_field_utf8_bytes"]),
        max_record_utf8_bytes=int(bounds["max_record_utf8_bytes"]),
    )
    return {
        "model_config": model_config,
        "snapshot": snapshot,
        "cache_manifest": cache_manifest,
        "tokenizer": tokenizer,
        "tokenizer_sha256": baseline.tokenizer_sha256(tokenizer),
        "pad_token_id": int(tokenizer.pad_token_id),
        "train_items": train_items,
        "holdout_items": holdout_items,
        "tokenization": {
            "train": train_summary,
            "holdout": holdout_summary,
        },
    }


def _load_fresh_model(prepared: dict[str, Any], torch: Any, device: Any) -> Any:
    from transformers import AutoModelForCausalLM

    model_config = prepared["model_config"]
    options: dict[str, Any] = {
        "local_files_only": True,
        "trust_remote_code": False,
        "token": False,
        "use_safetensors": bool(model_config["use_safetensors"]),
        "torch_dtype": torch.float32,
    }
    if model_config.get("weights_only") is True:
        options["weights_only"] = True
    model = AutoModelForCausalLM.from_pretrained(str(prepared["snapshot"]), **options)
    model.config.use_cache = False
    model.config.pad_token_id = prepared["pad_token_id"]
    if hasattr(model, "gradient_checkpointing_disable"):
        model.gradient_checkpointing_disable()
    model.to(device)
    return model


def _reset_cuda_peak(torch: Any, device: Any) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)


def _candidate_loss_maps(
    baseline: types.ModuleType,
    model: Any,
    prepared: dict[str, Any],
    device: Any,
    config: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float], dict[str, Any]]:
    pool_rows = int(config["workload"]["candidate_member_pool_rows"])
    member_items = prepared["train_items"][:pool_rows]
    nonmember_items = prepared["holdout_items"]
    member_metrics = baseline.per_example_loss_metrics(
        model,
        member_items,
        prepared["pad_token_id"],
        device,
        batch_size=int(config["workload"]["batch_size"]),
    )
    nonmember_metrics = baseline.per_example_loss_metrics(
        model,
        nonmember_items,
        prepared["pad_token_id"],
        device,
        batch_size=int(config["workload"]["batch_size"]),
    )
    members = {item["id"]: float(item["target_nll"]) for item in member_metrics}
    nonmembers = {item["id"]: float(item["target_nll"]) for item in nonmember_metrics}
    _require(len(members) == pool_rows, "member loss coverage mismatch")
    _require(len(nonmembers) == len(nonmember_items), "nonmember loss coverage mismatch")
    public = {
        "member_candidates": len(members),
        "nonmember_candidates": len(nonmembers),
        "member_target_nll": numeric_summary(list(members.values())),
        "nonmember_target_nll": numeric_summary(list(nonmembers.values())),
        "candidate_keys_persisted": False,
        "per_example_values_persisted": False,
    }
    del member_metrics, nonmember_metrics
    return members, nonmembers, public


def _evaluate_checkpoint(
    baseline: types.ModuleType,
    model: Any,
    prepared: dict[str, Any],
    device: Any,
    torch: Any,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, float], dict[str, float]]:
    _reset_cuda_peak(torch, device)
    holdout = baseline.evaluate(
        model,
        prepared["holdout_items"],
        int(config["workload"]["batch_size"]),
        prepared["pad_token_id"],
        device,
    )
    members, nonmembers, loss_summary = _candidate_loss_maps(
        baseline, model, prepared, device, config
    )
    memory = gpu_memory_snapshot(torch, device)
    enforce_gpu_memory_budget(memory, config)
    public = {
        "holdout": holdout,
        "candidate_loss": loss_summary,
        "evaluation_peak_gpu_allocated_bytes": memory["peak_allocated_bytes"],
        "evaluation_peak_gpu_reserved_bytes": memory["peak_reserved_bytes"],
    }
    return public, members, nonmembers


def _telemetry_segment_summary(
    baseline: types.ModuleType,
    hook_report: dict[str, Any],
) -> dict[str, Any]:
    events = hook_report.pop("events")
    replay = baseline.verify_telemetry_events(
        events,
        hook_report["event_chain_head_sha256"],
        genesis_sha256=hook_report["event_chain_genesis_sha256"],
    )
    steps = [item for item in events if item.get("event_type") == "step"]
    losses = [float(item["loss"]) for item in steps]
    result = {
        "status": hook_report["status"],
        "aggregate_only": hook_report["aggregate_only"],
        "coverage_status": hook_report["coverage_status"],
        "expected_steps": hook_report["expected_steps"],
        "observed_steps": hook_report["observed_steps"],
        "observed_forward_events": hook_report["observed_forward_events"],
        "observed_backward_events": hook_report["observed_backward_events"],
        "event_count": hook_report["event_count"],
        "nonfinite_elements": hook_report["nonfinite_elements"],
        "handles_removed": hook_report["handles_removed"],
        "event_chain_genesis_sha256": hook_report["event_chain_genesis_sha256"],
        "event_chain_head_sha256": hook_report["event_chain_head_sha256"],
        "independent_chain_replay": replay,
        "input_tokens_seen": sum(int(item.get("tokens", 0)) for item in steps),
        "target_tokens_seen": sum(int(item.get("target_tokens", 0)) for item in steps),
        "step_loss": numeric_summary(losses),
        "raw_event_stream_persisted": False,
        "raw_tensors_persisted": False,
        "raw_gradients_persisted": False,
    }
    del events
    return result


def train_segment(
    baseline: types.ModuleType,
    model: Any,
    prepared: dict[str, Any],
    optimizer: Any,
    *,
    start_step: int,
    end_step: int,
    model_key: str,
    scale: int,
    training_seed: int,
    collector_class: Any,
    torch: Any,
    device: Any,
    config: dict[str, Any],
    budget: ExecutionBudget,
) -> dict[str, Any]:
    batch_size = int(config["workload"]["batch_size"])
    items = prepared["train_items"][start_step * batch_size:end_step * batch_size]
    expected_steps = end_step - start_step
    _require(len(items) == expected_steps * batch_size, "training segment is not an exact full-batch prefix")
    context = {
        "experiment_id": config["experiment_id"],
        "model_key": model_key,
        "scale": scale,
        "training_seed": training_seed,
        "segment_start_step": start_step,
        "segment_end_step": end_step,
        "dataset_file_sha256": config["baseline_binding"]["dataset"]["sha256"],
        "configuration_sha256": canonical_sha256(config),
    }
    collector = collector_class(
        model,
        module_names=tuple(prepared["model_config"]["hook_modules"]),
        expected_steps=expected_steps,
        max_events=int(config["hook_profiles"]["training_event_cap_per_segment"]),
        fail_on_nonfinite=True,
        context_sha256=canonical_sha256(context),
    )
    durations: list[float] = []
    memory_peaks_allocated: list[float] = []
    memory_peaks_reserved: list[float] = []
    started_segment = time.perf_counter()
    model.train()
    try:
        with collector:
            for local_step, items_batch in enumerate(
                baseline.iter_batches(items, batch_size)
            ):
                budget.check()
                _reset_cuda_peak(torch, device)
                batch = baseline.collate_batch(items_batch, prepared["pad_token_id"], device)
                optimizer.zero_grad(set_to_none=True)
                started = time.perf_counter()
                output = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    labels=batch["labels"],
                )
                loss = output.loss
                if not bool(torch.isfinite(loss).item()):
                    raise FloatingPointError("training loss is non-finite")
                loss.backward()
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                forward_backward_seconds = time.perf_counter() - started
                global_step = start_step + local_step
                collector.step(
                    step=local_step,
                    epoch=0,
                    batch_index=global_step,
                    loss=float(loss.detach().cpu()),
                    model=model,
                    learning_rate=float(optimizer.param_groups[0]["lr"]),
                    input_tokens=int(batch["input_tokens"]),
                    target_tokens=int(batch["target_tokens"]),
                    truncated_records=int(batch["truncated_records"]),
                    batch_manifest_sha256=canonical_sha256(sorted(batch["record_ids"])),
                    duration_seconds=forward_backward_seconds,
                )
                optimizer.step()
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                duration = time.perf_counter() - started
                snapshot = gpu_memory_snapshot(torch, device)
                enforce_gpu_memory_budget(snapshot, config)
                durations.append(duration)
                memory_peaks_allocated.append(float(snapshot["peak_allocated_bytes"]))
                memory_peaks_reserved.append(float(snapshot["peak_reserved_bytes"]))
    finally:
        collector.remove()
    hook_report = collector.finalize(expected_steps=expected_steps)
    telemetry = _telemetry_segment_summary(baseline, hook_report)
    wall = time.perf_counter() - started_segment
    telemetry.update({
        "segment_start_step": start_step,
        "segment_end_step": end_step,
        "rows_exposed_in_segment": len(items),
        "training_wall_seconds": wall,
        "end_to_end_step_seconds": numeric_summary(durations),
        "peak_gpu_allocated_bytes": int(max(memory_peaks_allocated, default=0)),
        "peak_gpu_reserved_bytes": int(max(memory_peaks_reserved, default=0)),
        "rows_per_second": len(items) / wall,
    })
    return telemetry


def _microbenchmark_group(
    baseline: types.ModuleType,
    model: Any,
    batch: dict[str, Any],
    *,
    modules: Sequence[str],
    steps: int,
    seed_base: int,
    context_base: dict[str, Any],
    collector_class: Any,
    torch: Any,
    device: Any,
    config: dict[str, Any],
    budget: ExecutionBudget,
) -> dict[str, Any]:
    durations: list[float] = []
    peaks_allocated: list[float] = []
    peaks_reserved: list[float] = []
    losses: list[float] = []
    collector = None
    if modules:
        collector = collector_class(
            model,
            module_names=tuple(modules),
            expected_steps=steps,
            max_events=max(100, steps * (2 * len(modules) + 1)),
            fail_on_nonfinite=True,
            context_sha256=canonical_sha256(context_base),
        )
    model.train()

    def execute(active_collector: Any | None, step: int) -> None:
        budget.check()
        torch.manual_seed(seed_base + step)
        torch.cuda.manual_seed_all(seed_base + step)
        model.zero_grad(set_to_none=True)
        _reset_cuda_peak(torch, device)
        started = time.perf_counter()
        output = model(
            input_ids=batch["input_ids"],
            attention_mask=batch["attention_mask"],
            labels=batch["labels"],
        )
        loss = output.loss
        _require(bool(torch.isfinite(loss).item()), "microbenchmark loss is non-finite")
        loss.backward()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        if active_collector is not None:
            active_collector.step(
                step=step,
                loss=float(loss.detach().cpu()),
                model=model,
                input_tokens=int(batch["input_tokens"]),
                target_tokens=int(batch["target_tokens"]),
                truncated_records=int(batch["truncated_records"]),
                batch_manifest_sha256=canonical_sha256(sorted(batch["record_ids"])),
                duration_seconds=time.perf_counter() - started,
            )
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        durations.append(time.perf_counter() - started)
        losses.append(float(loss.detach().cpu()))
        memory = gpu_memory_snapshot(torch, device)
        enforce_gpu_memory_budget(memory, config)
        peaks_allocated.append(float(memory["peak_allocated_bytes"]))
        peaks_reserved.append(float(memory["peak_reserved_bytes"]))

    if collector is None:
        for step in range(steps):
            execute(None, step)
        telemetry = {
            "collector_enabled": False,
            "event_count": 0,
            "observed_forward_events": 0,
            "observed_backward_events": 0,
            "coverage_status": "not_applicable",
            "raw_event_stream_persisted": False,
        }
    else:
        try:
            with collector:
                for step in range(steps):
                    execute(collector, step)
        finally:
            collector.remove()
        telemetry = _telemetry_segment_summary(
            baseline, collector.finalize(expected_steps=steps)
        )
        telemetry["collector_enabled"] = True
    model.zero_grad(set_to_none=True)
    return {
        "step_seconds": durations,
        "loss_trace_sha256": canonical_sha256(losses),
        "peak_gpu_allocated_bytes": peaks_allocated,
        "peak_gpu_reserved_bytes": peaks_reserved,
        "telemetry": telemetry,
    }


def run_hook_microbenchmark(
    baseline: types.ModuleType,
    prepared: dict[str, Any],
    *,
    collector_class: Any,
    torch: Any,
    device: Any,
    config: dict[str, Any],
    budget: ExecutionBudget,
) -> dict[str, Any]:
    model_key = prepared["model_config"]["key"]
    benchmark_started = time.perf_counter()
    budget.check(
        minimum_remaining_seconds=float(
            config["resource_budget"]["minimum_remaining_seconds_to_start_model_cell"]
        )
    )
    model = _load_fresh_model(prepared, torch, device)
    initial_state = baseline.model_state_sha256(model)
    micro = config["hook_profiles"]["microbenchmark"]
    batch_rows = int(micro["batch_rows"])
    batch = baseline.collate_batch(
        prepared["train_items"][:batch_rows], prepared["pad_token_id"], device
    )
    modules_by_profile = {
        "none": (),
        "early": (prepared["model_config"]["hook_modules"][0],),
        "full": tuple(prepared["model_config"]["hook_modules"]),
    }
    measurements: dict[str, dict[str, list[Any]]] = {
        profile: {
            "step_seconds": [],
            "peak_gpu_allocated_bytes": [],
            "peak_gpu_reserved_bytes": [],
            "event_counts": [],
            "forward_event_counts": [],
            "backward_event_counts": [],
            "loss_trace_sha256s": [],
        }
        for profile in modules_by_profile
    }
    warmup_steps = int(micro["warmup_steps_per_profile_per_round"])
    measured_steps = int(micro["measured_steps_per_profile_per_round"])
    for round_index, order in enumerate(micro["profile_order_by_round"]):
        for profile_index, profile in enumerate(order):
            modules = modules_by_profile[profile]
            warmup = _microbenchmark_group(
                baseline,
                model,
                batch,
                modules=modules,
                steps=warmup_steps,
                seed_base=100_000 + round_index * 100 + profile_index * 10,
                context_base={
                    "experiment_id": config["experiment_id"],
                    "model_key": model_key,
                    "phase": "microbenchmark_warmup",
                    "profile": profile,
                    "round": round_index,
                },
                collector_class=collector_class,
                torch=torch,
                device=device,
                config=config,
                budget=budget,
            )
            del warmup
            measured = _microbenchmark_group(
                baseline,
                model,
                batch,
                modules=modules,
                steps=measured_steps,
                seed_base=200_000 + round_index * 100,
                context_base={
                    "experiment_id": config["experiment_id"],
                    "model_key": model_key,
                    "phase": "microbenchmark_measured",
                    "profile": profile,
                    "round": round_index,
                },
                collector_class=collector_class,
                torch=torch,
                device=device,
                config=config,
                budget=budget,
            )
            target = measurements[profile]
            target["step_seconds"].extend(measured["step_seconds"])
            target["peak_gpu_allocated_bytes"].extend(measured["peak_gpu_allocated_bytes"])
            target["peak_gpu_reserved_bytes"].extend(measured["peak_gpu_reserved_bytes"])
            target["event_counts"].append(measured["telemetry"]["event_count"])
            target["forward_event_counts"].append(measured["telemetry"]["observed_forward_events"])
            target["backward_event_counts"].append(measured["telemetry"]["observed_backward_events"])
            target["loss_trace_sha256s"].append(measured["loss_trace_sha256"])
    final_state = baseline.model_state_sha256(model)
    _require(final_state == initial_state, "hook microbenchmark changed model weights")
    profiles = []
    none_median = float(numeric_summary(measurements["none"]["step_seconds"])["median"])
    for profile in ("none", "early", "full"):
        observed = measurements[profile]
        duration_summary = numeric_summary(observed["step_seconds"])
        profile_report = {
            "profile": profile,
            "selected_module_count": len(modules_by_profile[profile]),
            "rounds": int(micro["rounds"]),
            "measured_steps": len(observed["step_seconds"]),
            "step_seconds": duration_summary,
            "median_ratio_to_no_hook": float(duration_summary["median"]) / none_median,
            "peak_gpu_allocated_bytes": numeric_summary(observed["peak_gpu_allocated_bytes"]),
            "peak_gpu_reserved_bytes": numeric_summary(observed["peak_gpu_reserved_bytes"]),
            "total_event_count": sum(observed["event_counts"]),
            "total_forward_event_count": sum(observed["forward_event_counts"]),
            "total_backward_event_count": sum(observed["backward_event_counts"]),
            "loss_trace_digest_count": len(set(observed["loss_trace_sha256s"])),
            "raw_timings_persisted": False,
            "raw_telemetry_persisted": False,
        }
        profiles.append(profile_report)
    memory = gpu_memory_snapshot(torch, device)
    enforce_gpu_memory_budget(memory, config)
    report = {
        "model_key": model_key,
        "model_revision": prepared["model_config"]["revision"],
        "base_state_sha256": initial_state,
        "final_state_sha256": final_state,
        "weights_unchanged": True,
        "batch_rows": batch_rows,
        "same_real_batch_for_every_profile": True,
        "optimizer_step": False,
        "balanced_profile_order": True,
        "profiles": profiles,
        "interpretation": "descriptive synchronized microbenchmark; ratios are not causal production-capacity estimates",
        **AUTHORITY,
        "resource": {
            "wall_clock_seconds": time.perf_counter() - benchmark_started,
            "peak_gpu_allocated_bytes": int(max(
                float(profile["peak_gpu_allocated_bytes"]["maximum"])
                for profile in profiles
            )),
            "peak_gpu_reserved_bytes": int(max(
                float(profile["peak_gpu_reserved_bytes"]["maximum"])
                for profile in profiles
            )),
            "peak_host_rss_bytes": host_peak_rss_bytes(),
        },
    }
    del model, batch
    gc.collect()
    torch.cuda.empty_cache()
    return report


def _aggregate_training_segments(segments: Sequence[dict[str, Any]], scale: int) -> dict[str, Any]:
    steps = sum(int(item["observed_steps"]) for item in segments)
    wall = sum(float(item["training_wall_seconds"]) for item in segments)
    _require(steps == scale // 16, "segment optimizer-step closure mismatch")
    return {
        "optimizer_steps": steps,
        "exposed_rows": scale,
        "segment_count": len(segments),
        "training_wall_seconds": wall,
        "rows_per_second": scale / wall,
        "input_tokens_seen": sum(int(item["input_tokens_seen"]) for item in segments),
        "target_tokens_seen": sum(int(item["target_tokens_seen"]) for item in segments),
        "event_count": sum(int(item["event_count"]) for item in segments),
        "observed_forward_events": sum(int(item["observed_forward_events"]) for item in segments),
        "observed_backward_events": sum(int(item["observed_backward_events"]) for item in segments),
        "peak_gpu_allocated_bytes": max(int(item["peak_gpu_allocated_bytes"]) for item in segments),
        "peak_gpu_reserved_bytes": max(int(item["peak_gpu_reserved_bytes"]) for item in segments),
        "coverage_complete": all(item["coverage_status"] == "complete" for item in segments),
        "nonfinite_elements": sum(int(item["nonfinite_elements"]) for item in segments),
        "raw_event_stream_persisted": False,
        "segments": list(segments),
    }


def run_model_cell(
    baseline: types.ModuleType,
    prepared: dict[str, Any],
    *,
    scale: int,
    training_seed: int,
    collect_trajectory: bool,
    base_cache: dict[str, Any],
    collector_class: Any,
    torch: Any,
    device: Any,
    config: dict[str, Any],
    budget: ExecutionBudget,
) -> tuple[dict[str, Any], dict[int, tuple[dict[str, float], dict[str, float]]]]:
    model_key = prepared["model_config"]["key"]
    minimum = float(config["resource_budget"]["minimum_remaining_seconds_to_start_model_cell"])
    budget.check(minimum_remaining_seconds=minimum)
    cell_started = time.perf_counter()
    model = _load_fresh_model(prepared, torch, device)
    cache_now = baseline.model_cache_manifest(prepared["snapshot"])
    _require(
        cache_now["manifest_sha256"] == prepared["cache_manifest"]["manifest_sha256"],
        "verified model cache changed before cell load",
    )
    base_state = baseline.model_state_sha256(model)
    parameter_report = {
        "total": sum(int(parameter.numel()) for parameter in model.parameters()),
        "trainable": sum(int(parameter.numel()) for parameter in model.parameters() if parameter.requires_grad),
    }
    if model_key not in base_cache:
        base_public, base_members, base_nonmembers = _evaluate_checkpoint(
            baseline, model, prepared, device, torch, config
        )
        base_cache[model_key] = {
            "state_sha256": base_state,
            "public": base_public,
            "members": base_members,
            "nonmembers": base_nonmembers,
        }
    cached = base_cache[model_key]
    _require(cached["state_sha256"] == base_state, "fresh base model state differs across cells")
    private_by_rows: dict[int, tuple[dict[str, float], dict[str, float]]] = {
        0: (cached["members"], cached["nonmembers"])
    }
    stages = [{
        "exposed_rows": 0,
        "optimizer_steps": 0,
        "model_state_sha256": base_state,
        "evaluation": cached["public"],
        "stage_semantics": "prospective_full_run_member_pool_before_training_not_observed_membership",
    }]
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config["workload"]["learning_rate"]),
        weight_decay=float(config["workload"]["weight_decay"]),
        foreach=False,
        fused=False,
    )
    torch.manual_seed(int(training_seed))
    torch.cuda.manual_seed_all(int(training_seed))
    end_step = scale // int(config["workload"]["batch_size"])
    if collect_trajectory:
        boundaries = [rows // 16 for rows in TRAJECTORY_ROWS[1:]]
    else:
        boundaries = [end_step]
    _require(boundaries[-1] == end_step, "trajectory boundary does not end at cell scale")
    start_step = 0
    segments = []
    for boundary in boundaries:
        segment = train_segment(
            baseline,
            model,
            prepared,
            optimizer,
            start_step=start_step,
            end_step=boundary,
            model_key=model_key,
            scale=scale,
            training_seed=training_seed,
            collector_class=collector_class,
            torch=torch,
            device=device,
            config=config,
            budget=budget,
        )
        segments.append(segment)
        exposed_rows = boundary * 16
        public_eval, members, nonmembers = _evaluate_checkpoint(
            baseline, model, prepared, device, torch, config
        )
        state_hash = baseline.model_state_sha256(model)
        private_by_rows[exposed_rows] = (members, nonmembers)
        stages.append({
            "exposed_rows": exposed_rows,
            "optimizer_steps": boundary,
            "model_state_sha256": state_hash,
            "evaluation": public_eval,
            "stage_semantics": "cumulative_training_trajectory" if collect_trajectory else "independent_fresh_scale_endpoint",
        })
        start_step = boundary
    final_state = stages[-1]["model_state_sha256"]
    _require(final_state != base_state, "training did not change model state")
    training = _aggregate_training_segments(segments, scale)
    _require(training["coverage_complete"], "training hook coverage is incomplete")
    _require(training["nonfinite_elements"] == 0, "training telemetry contains non-finite elements")
    cache_final = baseline.model_cache_manifest(prepared["snapshot"])
    _require(cache_final["manifest_sha256"] == cache_now["manifest_sha256"], "model cache changed during cell")
    memory = gpu_memory_snapshot(torch, device)
    enforce_gpu_memory_budget(memory, config)
    cell_wall = time.perf_counter() - cell_started
    report = {
        "model_key": model_key,
        "model_revision": prepared["model_config"]["revision"],
        "training_seed": training_seed,
        "independent_train_scale": scale,
        "fresh_model_initialization": True,
        "parameters": parameter_report,
        "tokenizer_sha256": prepared["tokenizer_sha256"],
        "verified_model_cache_manifest_sha256": cache_now["manifest_sha256"],
        "verified_model_cache_file_count": cache_now["file_count"],
        "tokenization": prepared["tokenization"],
        "base_state_sha256": base_state,
        "final_state_sha256": final_state,
        "state_changed": True,
        "stages": stages,
        "training": training,
        "trajectory_collected": collect_trajectory,
        "model_weights_persisted": False,
        "per_example_values_persisted": False,
        "record_identifiers_persisted": False,
        "resource": {
            "wall_clock_seconds": cell_wall,
            "peak_gpu_allocated_bytes": max(
                int(training["peak_gpu_allocated_bytes"]),
                int(memory["peak_allocated_bytes"]),
            ),
            "peak_gpu_reserved_bytes": max(
                int(training["peak_gpu_reserved_bytes"]),
                int(memory["peak_reserved_bytes"]),
            ),
            "peak_host_rss_bytes": host_peak_rss_bytes(),
        },
        **AUTHORITY,
    }
    del model, optimizer
    gc.collect()
    torch.cuda.empty_cache()
    return report, private_by_rows


def _composition_at_rows(
    private_by_model: Mapping[str, Mapping[int, tuple[dict[str, float], dict[str, float]]]],
    *,
    exposed_rows: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    losses: dict[str, dict[str, float]] = {}
    member_keys: list[str] | None = None
    nonmember_keys: list[str] | None = None
    for model_key in MODEL_KEYS:
        members, nonmembers = private_by_model[model_key][exposed_rows]
        if member_keys is None:
            member_keys = list(members)
            nonmember_keys = list(nonmembers)
        else:
            _require(set(member_keys) == set(members), "member candidate alignment differs across models")
            _require(set(nonmember_keys or []) == set(nonmembers), "nonmember candidate alignment differs across models")
        losses[model_key] = {**members, **nonmembers}
    _require(member_keys is not None and nonmember_keys is not None, "composition candidate matrix is empty")
    composition = config["composition"]
    return build_subset_screens(
        losses,
        member_keys,
        nonmember_keys,
        partition_seeds=[int(seed) for seed in composition["partition_seeds"]],
        calibration_per_class=int(composition["calibration_per_class"]),
        audit_per_class=int(composition["audit_per_class"]),
        bootstrap_replicates=int(composition["bootstrap"]["replicates"]),
        confidence_level=float(composition["bootstrap"]["confidence_level"]),
        checkpoint_steps=exposed_rows // int(config["workload"]["batch_size"]),
    )


def run_scale_seed_bundle(
    baseline: types.ModuleType,
    prepared_by_model: Mapping[str, dict[str, Any]],
    *,
    scale: int,
    training_seed: int,
    base_cache: dict[str, Any],
    collector_class: Any,
    torch: Any,
    device: Any,
    config: dict[str, Any],
    budget: ExecutionBudget,
) -> dict[str, Any]:
    bundle_started = time.perf_counter()
    trajectory = scale == 8192 and training_seed == int(
        config["workload"]["secondary_trajectory_training_seed"]
    )
    models: list[dict[str, Any]] = []
    private_by_model: dict[str, Mapping[int, tuple[dict[str, float], dict[str, float]]]] = {}
    for model_key in MODEL_KEYS:
        print(
            f"model cell start: scale={scale} seed={training_seed} model={model_key}",
            file=sys.stderr,
            flush=True,
        )
        model_report, private = run_model_cell(
            baseline,
            prepared_by_model[model_key],
            scale=scale,
            training_seed=training_seed,
            collect_trajectory=trajectory,
            base_cache=base_cache,
            collector_class=collector_class,
            torch=torch,
            device=device,
            config=config,
            budget=budget,
        )
        models.append(model_report)
        private_by_model[model_key] = private
    before = _composition_at_rows(private_by_model, exposed_rows=0, config=config)
    after = _composition_at_rows(private_by_model, exposed_rows=scale, config=config)
    trajectory_report = None
    if trajectory:
        trajectory_report = {
            "training_seed": training_seed,
            "independent_scale_evidence": False,
            "confounds": list(config["workload"]["secondary_trajectory_confounds"]),
            "checkpoints": [
                {
                    "exposed_rows": exposed_rows,
                    "composition": _composition_at_rows(
                        private_by_model, exposed_rows=exposed_rows, config=config
                    ),
                }
                for exposed_rows in TRAJECTORY_ROWS
            ],
            "interpretation": "one cumulative optimizer trajectory; exposure, order, optimizer state, and training progress are inseparable",
            **AUTHORITY,
        }
    bundle_memory = gpu_memory_snapshot(torch, device)
    enforce_gpu_memory_budget(bundle_memory, config)
    payload = {
        "schema_version": "1.0",
        "bundle_key": f"scale-{scale}-seed-{training_seed}",
        "independent_train_scale": scale,
        "training_seed": training_seed,
        "fresh_model_cells": len(models),
        "model_keys": list(MODEL_KEYS),
        "models": models,
        "composition": {
            "before_training": before,
            "after_training": after,
            "all_nonempty_model_subsets_evaluated": True,
            "subset_count": len(MODEL_SUBSETS),
            "primary_contrast": config["composition"]["primary_subset_contrast"],
            "best_singleton_primary_contrast": False,
            "cross_model_fusion_dataset": "WildChat_registered_shared_split_only",
        },
        "secondary_cumulative_trajectory": trajectory_report,
        "resource": {
            "wall_clock_seconds": time.perf_counter() - bundle_started,
            "peak_gpu_allocated_bytes": max(
                [int(bundle_memory["peak_allocated_bytes"])]
                + [int(item["resource"]["peak_gpu_allocated_bytes"]) for item in models]
            ),
            "peak_gpu_reserved_bytes": max(
                [int(bundle_memory["peak_reserved_bytes"])]
                + [int(item["resource"]["peak_gpu_reserved_bytes"]) for item in models]
            ),
            "peak_host_rss_bytes": max(
                [host_peak_rss_bytes()]
                + [int(item["resource"]["peak_host_rss_bytes"]) for item in models]
            ),
        },
        "record_identifiers_persisted": False,
        "per_example_values_persisted": False,
        "model_weights_persisted": False,
        "raw_telemetry_persisted": False,
        **AUTHORITY,
    }
    _assert_aggregate_only(payload)
    del private_by_model
    gc.collect()
    return payload


def _partition_subset(
    composition: dict[str, Any], partition_seed: int, model_subset: Sequence[str]
) -> dict[str, Any]:
    partition = next(
        item for item in composition["partition_results"]
        if int(item["partition_seed"]) == int(partition_seed)
    )
    key = subset_key(model_subset)
    return next(item for item in partition["subsets"] if subset_key(item["model_keys"]) == key)


def _sensitivity_subset(
    composition: dict[str, Any], model_subset: Sequence[str]
) -> dict[str, Any]:
    key = subset_key(model_subset)
    return next(
        item for item in composition["partition_sensitivity"]
        if subset_key(item["model_keys"]) == key
    )


def _build_cross_seed_summary(bundle_payloads: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for scale in TRAIN_SCALES:
        bundles = [item for item in bundle_payloads if int(item["independent_train_scale"]) == scale]
        _require(len(bundles) == len(TRAINING_SEEDS), "cross-seed scale closure mismatch")
        for model_subset in MODEL_SUBSETS:
            before = [
                _sensitivity_subset(item["composition"]["before_training"], model_subset)
                for item in bundles
            ]
            after = [
                _sensitivity_subset(item["composition"]["after_training"], model_subset)
                for item in bundles
            ]
            metrics = {}
            for metric in (
                "balanced_accuracy",
                "roc_auc",
                "membership_advantage_at_threshold",
            ):
                before_values = [float(item["metrics_across_partition_seeds"][metric]["median"]) for item in before]
                after_values = [float(item["metrics_across_partition_seeds"][metric]["median"]) for item in after]
                metrics[metric] = {
                    "before_across_training_seeds": numeric_summary(before_values),
                    "after_across_training_seeds": numeric_summary(after_values),
                    "paired_change_across_training_seeds": numeric_summary([
                        after_value - before_value
                        for before_value, after_value in zip(before_values, after_values)
                    ]),
                }
            result.append({
                "independent_train_scale": scale,
                "model_keys": list(model_subset),
                "training_seed_count": len(TRAINING_SEEDS),
                "partition_seed_count_per_training_seed": len(TRAINING_SEEDS),
                "metrics": metrics,
                "independent_fresh_model_cells_underlying": len(TRAINING_SEEDS) * len(model_subset),
                **AUTHORITY,
            })
    return result


def _build_suite_export(
    preflight: dict[str, Any], bundle_payloads: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    primary_partition_seed = TRAINING_SEEDS[0]
    subset_scalars = []
    for scale in TRAIN_SCALES:
        for training_seed in TRAINING_SEEDS:
            bundle = next(
                item for item in bundle_payloads
                if int(item["independent_train_scale"]) == scale
                and int(item["training_seed"]) == training_seed
            )
            for model_subset in MODEL_SUBSETS:
                before = _partition_subset(
                    bundle["composition"]["before_training"], primary_partition_seed, model_subset
                )
                after = _partition_subset(
                    bundle["composition"]["after_training"], primary_partition_seed, model_subset
                )
                before_metrics = before["metrics"]
                after_metrics = after["metrics"]
                after_contrast = after["primary_contrast_vs_mean_member_singletons"]
                subset_scalars.append({
                    "model_keys": list(model_subset),
                    "scale": scale,
                    "seed": training_seed,
                    "metrics": {
                        "before_balanced_accuracy": float(before_metrics["balanced_accuracy"]),
                        "after_balanced_accuracy": float(after_metrics["balanced_accuracy"]),
                        "balanced_accuracy_change": float(after_metrics["balanced_accuracy"] - before_metrics["balanced_accuracy"]),
                        "before_roc_auc": float(before_metrics["roc_auc"]),
                        "after_roc_auc": float(after_metrics["roc_auc"]),
                        "roc_auc_change": float(after_metrics["roc_auc"] - before_metrics["roc_auc"]),
                        "before_membership_advantage": float(before_metrics["membership_advantage_at_threshold"]),
                        "after_membership_advantage": float(after_metrics["membership_advantage_at_threshold"]),
                        "membership_advantage_change": float(
                            after_metrics["membership_advantage_at_threshold"]
                            - before_metrics["membership_advantage_at_threshold"]
                        ),
                        "after_balanced_accuracy_minus_mean_singletons": float(after_contrast["balanced_accuracy"]),
                        "after_roc_auc_minus_mean_singletons": float(after_contrast["roc_auc"]),
                    },
                })
    _require(len(subset_scalars) == 7 * 3 * 5, "suite export subset scalar closure mismatch")

    micro_by_key = {
        item["model_key"]: item for item in preflight["hook_microbenchmarks"]
    }
    resources = []
    for model_key in MODEL_KEYS:
        cell_models = [
            next(item for item in bundle["models"] if item["model_key"] == model_key)
            for bundle in bundle_payloads
        ]
        micro = micro_by_key[model_key]
        artifact_bytes = sum(len(canonical_json(item)) for item in cell_models) + len(canonical_json(micro))
        resources.append({
            "model_key": model_key,
            "wall_clock_seconds": sum(float(item["resource"]["wall_clock_seconds"]) for item in cell_models)
            + float(micro["resource"]["wall_clock_seconds"]),
            "peak_gpu_reserved_bytes": max(
                [int(item["resource"]["peak_gpu_reserved_bytes"]) for item in cell_models]
                + [int(micro["resource"]["peak_gpu_reserved_bytes"])]
            ),
            "peak_host_rss_bytes": max(
                [int(item["resource"]["peak_host_rss_bytes"]) for item in cell_models]
                + [int(micro["resource"]["peak_host_rss_bytes"])]
            ),
            "artifact_bytes": artifact_bytes,
        })
    suite_authority = dict(AUTHORITY)
    return validate_suite_export({
        "schema_version": "1.0",
        "modality": "llm",
        "protected_unit_population": "wildchat_training_record",
        "model_keys": list(MODEL_KEYS),
        "seeds": list(TRAINING_SEEDS),
        "scales": list(TRAIN_SCALES),
        "authority": suite_authority,
        "resources": resources,
        "subset_scalars": subset_scalars,
    })


def validate_suite_export(export: dict[str, Any]) -> dict[str, Any]:
    """Validate the exact aggregate interchange contract used by the suite."""

    _require(set(export) == {
        "schema_version",
        "modality",
        "protected_unit_population",
        "model_keys",
        "seeds",
        "scales",
        "authority",
        "resources",
        "subset_scalars",
    }, "suite export closure mismatch")
    _require(export["schema_version"] == "1.0", "suite export schema mismatch")
    _require(export["modality"] == "llm", "suite export modality mismatch")
    _require(export["protected_unit_population"] == "wildchat_training_record", "suite protected unit mismatch")
    _require(tuple(export["model_keys"]) == MODEL_KEYS, "suite model-key mismatch")
    _require(tuple(export["seeds"]) == TRAINING_SEEDS, "suite seed mismatch")
    _require(tuple(export["scales"]) == TRAIN_SCALES, "suite scale mismatch")
    _require(export["authority"] == AUTHORITY, "suite authority mismatch")
    resources = export["resources"]
    _require(isinstance(resources, list) and len(resources) == len(MODEL_KEYS), "suite resources mismatch")
    _require([item.get("model_key") for item in resources] == list(MODEL_KEYS), "suite resource order mismatch")
    resource_keys = {
        "model_key",
        "wall_clock_seconds",
        "peak_gpu_reserved_bytes",
        "peak_host_rss_bytes",
        "artifact_bytes",
    }
    for item in resources:
        _require(set(item) == resource_keys, "suite resource closure mismatch")
        for key in resource_keys - {"model_key"}:
            _require(
                isinstance(item[key], (int, float))
                and not isinstance(item[key], bool)
                and math.isfinite(float(item[key]))
                and float(item[key]) >= 0.0,
                f"suite resource {key} must be finite and nonnegative",
            )
    metric_keys = {
        "before_balanced_accuracy",
        "after_balanced_accuracy",
        "balanced_accuracy_change",
        "before_roc_auc",
        "after_roc_auc",
        "roc_auc_change",
        "before_membership_advantage",
        "after_membership_advantage",
        "membership_advantage_change",
        "after_balanced_accuracy_minus_mean_singletons",
        "after_roc_auc_minus_mean_singletons",
    }
    scalars = export["subset_scalars"]
    _require(isinstance(scalars, list) and len(scalars) == 105, "suite subset-scalar closure mismatch")
    expected_cells = [
        (tuple(model_subset), scale, seed)
        for scale in TRAIN_SCALES
        for seed in TRAINING_SEEDS
        for model_subset in MODEL_SUBSETS
    ]
    observed_cells = []
    for row in scalars:
        _require(set(row) == {"model_keys", "scale", "seed", "metrics"}, "suite scalar row closure mismatch")
        observed_cells.append((tuple(row["model_keys"]), int(row["scale"]), int(row["seed"])))
        _require(set(row["metrics"]) == metric_keys, "suite scalar metric closure mismatch")
        _require(
            all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in row["metrics"].values()
            ),
            "suite scalar metrics must all be finite",
        )
    _require(observed_cells == expected_cells, "suite scalar cell order or coverage mismatch")
    return export


def assemble_report(
    config: dict[str, Any],
    source: dict[str, Any],
    context: dict[str, Any],
    records: Sequence[dict[str, Any]],
    journal_path: Path,
) -> dict[str, Any]:
    keys = expected_journal_keys()
    _require(len(records) == len(keys), "report assembly requires exact journal closure")
    _require([item["record_key"] for item in records] == keys, "journal key closure mismatch")
    preflight = records[0]["payload"]
    bundles = [item["payload"] for item in records[1:]]
    _require(len(bundles) == len(TRAIN_SCALES) * len(TRAINING_SEEDS), "bundle closure mismatch")
    expected_bundles = [
        (scale, seed) for scale in TRAIN_SCALES for seed in TRAINING_SEEDS
    ]
    for bundle, (scale, seed) in zip(bundles, expected_bundles):
        _require(
            bundle.get("bundle_key") == f"scale-{scale}-seed-{seed}"
            and bundle.get("independent_train_scale") == scale
            and bundle.get("training_seed") == seed,
            "bundle payload order or identity mismatch",
        )
        _require(
            [item.get("model_key") for item in bundle.get("models", [])]
            == list(MODEL_KEYS),
            "bundle model closure mismatch",
        )
        for key, value in AUTHORITY.items():
            _require(bundle.get(key) == value, f"bundle authority mismatch: {key}")
    suite_export = _build_suite_export(preflight, bundles)
    report = {
        "schema_version": "1.0",
        "report_type": "experimental_real_data_llm_composition_scaling",
        "experiment_id": config["experiment_id"],
        "execution": {
            "status": "complete",
            "completed_checkpoint_records": len(records),
            "expected_checkpoint_records": len(keys),
            "independent_fresh_model_cells": 45,
            "scale_seed_bundles": 15,
            "all_nonempty_model_subsets_per_bundle": 7,
            "resumable_aggregate_journal": True,
            "completion_manifest_is_final_publication_signal": True,
        },
        "aggregate_only": True,
        "authority": dict(AUTHORITY),
        "decision": "no_release_authorization",
        "suite_export": suite_export,
        "resources": suite_export["resources"],
        "gates": {
            "dataset_content_rights": "LEGAL_REVIEW_REQUIRED",
            "meta_opt_production_commercial": "BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY",
            "pythia_human_facing_deployment": "MANUAL_REVIEW_REQUIRED",
            "membership_evidence": "INCONCLUSIVE_DESCRIPTIVE_ONLY",
            "assessment_input_emitted": False,
            "attack_battery_eligible": False,
            "authorization_eligible": False,
            "authorization_granted": False,
            "can_clear": False,
            "can_block": False,
            "requires_approved_recollection": True,
            "decision": "no_release_authorization",
        },
        "source_provenance": source,
        "execution_context_sha256": canonical_sha256(context),
        "runtime": context["runtime"],
        "dataset": preflight["dataset"],
        "model_keys": list(MODEL_KEYS),
        "independent_train_scales": list(TRAIN_SCALES),
        "training_seeds": list(TRAINING_SEEDS),
        "partition_seeds": list(TRAINING_SEEDS),
        "primary_design": {
            "cell_count": 45,
            "fresh_model_initialization_per_model_scale_training_seed_cell": True,
            "nested_real_training_prefixes": list(TRAIN_SCALES),
            "before_after_composition_subsets": [list(item) for item in MODEL_SUBSETS],
            "primary_subset_contrast": config["composition"]["primary_subset_contrast"],
            "suite_export_partition_seed": config["composition"]["suite_export_partition_seed"],
            "five_partition_sensitivity_retained": True,
        },
        "hook_microbenchmarks": preflight["hook_microbenchmarks"],
        "scale_seed_bundles": bundles,
        "cross_training_seed_summary": _build_cross_seed_summary(bundles),
        "secondary_cumulative_trajectory": next(
            item["secondary_cumulative_trajectory"]
            for item in bundles
            if item["secondary_cumulative_trajectory"] is not None
        ),
        "release_interfaces": release_interface_matrix(config),
        "subset_release_routes": [subset_release_route(item) for item in MODEL_SUBSETS],
        "resource_budget": {
            **config["resource_budget"],
            "observed_completed_bundle_wall_seconds": sum(
                float(item["resource"]["wall_clock_seconds"]) for item in bundles
            ) + float(preflight["resource"]["wall_clock_seconds"]),
            "completed_under_registered_budget": True,
        },
        "evidence_limits": [
            "Every statistical result is a descriptive, unpowered screen and cannot clear or block release.",
            "The before-training member labels are prospective full-run labels, not observed membership at checkpoint zero.",
            "The five-point cumulative trajectory confounds exposure volume, fixed record order, optimizer-state progress, and training progress; it is not independent scale evidence.",
            "The independent scale cells use nested prefixes from one WildChat shard and do not establish population, domain, or deployment generalization.",
            "Bootstrap intervals resample audit candidates within a fixed constructed split; they are sensitivity intervals, not deployment-population confidence guarantees.",
            "The exploratory matrix has no multiple-comparison correction and makes no monotonicity or causal claim.",
            "Composition requires arbitrary-candidate scoring for every model in a subset; text-only and generated-token-only interfaces do not realize these screens.",
            "WildChat database licensing does not itself clear rights in conversation contents or provider outputs; legal review remains required.",
            "Meta OPT-125M is blocked for production/commercial release by its registered non-commercial research license.",
            "The report is not an MRAP assessment input; approved recollection under a signed recipient-realizable contract is required.",
        ],
        "privacy": {
            "aggregate_only": True,
            "dialogue_text_persisted": False,
            "record_identifiers_persisted": False,
            "per_example_values_persisted": False,
            "token_arrays_persisted": False,
            "raw_telemetry_events_persisted": False,
            "raw_tensors_persisted": False,
            "model_weights_persisted": False,
            "absolute_paths_persisted": False,
        },
        "checkpoint_journal": {
            "path": journal_path.name,
            "sha256": sha256_file(journal_path),
            "bytes": journal_path.stat().st_size,
            "record_count": len(records),
            "chain_head_sha256": records[-1]["record_sha256"],
            "exact_expected_closure": True,
            "aggregate_only": True,
        },
        "output_contract": config["output"],
    }
    _assert_aggregate_only(report)
    return report


def build_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# LLM composition-scaling empirical report",
        "",
        f"- Execution: **{report['execution']['status']}**",
        f"- Decision: **{report['decision']}**",
        "- Authority: experimental only; no assessment input, attack-battery eligibility, clearance, blocking authority, or authorization",
        f"- Primary matrix: {report['execution']['independent_fresh_model_cells']} fresh model cells across 3 models, 3 scales, and 5 training seeds",
        "- Composition: all 7 nonempty model-loss subsets before and after every primary cell; five deterministic partition seeds with stratified bootstrap sensitivity intervals",
        "",
        "## Independent fresh-cell summary",
        "",
        "Each value below is the median across training seeds of that seed's median across the five partition seeds. The contrast is the subset result minus the mean of its member-model singleton results, never the best singleton.",
        "",
        "| Rows | Models | After BA | After AUC | BA contrast | AUC contrast |",
        "| ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in report["cross_training_seed_summary"]:
        metric = item["metrics"]
        # Cross-seed summaries retain the subset metric.  The suite export
        # carries the preregistered partition's exact within-cell contrasts.
        after_ba = metric["balanced_accuracy"]["after_across_training_seeds"]["median"]
        after_auc = metric["roc_auc"]["after_across_training_seeds"]["median"]
        matching = [
            row for row in report["suite_export"]["subset_scalars"]
            if row["scale"] == item["independent_train_scale"]
            and row["model_keys"] == item["model_keys"]
        ]
        ba_contrast = _percentile(
            [row["metrics"]["after_balanced_accuracy_minus_mean_singletons"] for row in matching],
            0.5,
        )
        auc_contrast = _percentile(
            [row["metrics"]["after_roc_auc_minus_mean_singletons"] for row in matching],
            0.5,
        )
        lines.append(
            f"| {item['independent_train_scale']:,} | {' + '.join(item['model_keys'])} | "
            f"{after_ba:.4f} | {after_auc:.4f} | {ba_contrast:+.4f} | {auc_contrast:+.4f} |"
        )

    lines.extend([
        "",
        "## Hook-profile microbenchmarks",
        "",
        "The no-hook, early-layer, and full registered-hook profiles use the same real WildChat batch, balanced profile ordering, synchronized forward/backward timing, and no optimizer step. Ratios are descriptive, not causal production-capacity claims.",
        "",
        "| Model | Profile | Median step (s) | Ratio to none | Peak reserved bytes | Events |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for model in report["hook_microbenchmarks"]:
        for profile in model["profiles"]:
            lines.append(
                f"| {model['model_key']} | {profile['profile']} | "
                f"{profile['step_seconds']['median']:.6f} | {profile['median_ratio_to_no_hook']:.3f} | "
                f"{int(profile['peak_gpu_reserved_bytes']['maximum']):,} | {profile['total_event_count']} |"
            )

    lines.extend([
        "",
        "## Secondary cumulative trajectory",
        "",
        "This five-point curve is one 8,192-row, seed-3407 optimizer trajectory. It is explicitly not independent scale evidence because cumulative exposure, fixed order, optimizer state, and training progress are confounded.",
        "",
        "| Exposed rows | Steps | Triple BA | Triple AUC |",
        "| ---: | ---: | ---: | ---: |",
    ])
    triple = MODEL_SUBSETS[-1]
    for checkpoint in report["secondary_cumulative_trajectory"]["checkpoints"]:
        sensitivity = _sensitivity_subset(checkpoint["composition"], triple)
        lines.append(
            f"| {checkpoint['exposed_rows']:,} | {checkpoint['exposed_rows'] // 16:,} | "
            f"{sensitivity['metrics_across_partition_seeds']['balanced_accuracy']['median']:.4f} | "
            f"{sensitivity['metrics_across_partition_seeds']['roc_auc']['median']:.4f} |"
        )

    lines.extend([
        "",
        "## Interface and release semantics",
        "",
        "Model-loss composition is realizable only when a recipient can score the complete arbitrary candidate continuation under every model in the subset (or has equivalent white-box access). Text-only generation and generated-token log probabilities do not realize this test. A protected, authenticated exact training roster is a separate direct-disclosure channel that would block the membership gate and require redesign; this experiment releases no roster.",
        "",
        "Meta OPT-125M remains blocked for production/commercial use by its registered non-commercial research license. All subsets retain the WildChat content-rights legal-review gate, and Pythia subsets retain the registered human-facing manual-review gate.",
        "",
        "## Evidence limits",
        "",
    ])
    lines.extend(f"- {item}" for item in report["evidence_limits"])
    lines.extend([
        "",
        "## Durable artifacts",
        "",
        "Only aggregate JSON, this Markdown report, the hash-chained completed-cell journal, and the final completion manifest are durable. No dialogue, record identifiers, per-example values, token arrays, raw telemetry events, tensors, gradients, model weights, or absolute paths are persisted.",
        "",
        "This experiment is not an assessment input and cannot clear, block, or authorize release. An approved recollection under a signed recipient-realizable release contract is required.",
        "",
    ])
    return "\n".join(lines)


def _write_or_verify(path: Path, payload: bytes, baseline: types.ModuleType) -> None:
    if path.exists():
        _require(path.is_file() and not path.is_symlink(), f"artifact is not a regular file: {path.name}")
        _require(path.read_bytes() == payload, f"existing finalization artifact differs: {path.name}")
        _require((path.stat().st_mode & 0o777) == 0o600, f"artifact mode differs: {path.name}")
        return
    baseline._atomic_write_bytes(path, payload)


def validate_completion_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _require(set(manifest) == {
        "schema_version",
        "status",
        "experiment_id",
        "report",
        "authority",
    }, "completion manifest closure mismatch")
    _require(manifest["schema_version"] == "1.0", "completion schema mismatch")
    _require(manifest["status"] == "complete", "completion status mismatch")
    _require(
        manifest["experiment_id"] == "llm-composition-scaling-wildchat-three-model-v1",
        "completion experiment mismatch",
    )
    _require(manifest["authority"] == AUTHORITY, "completion authority mismatch")
    registration = manifest["report"]
    _require(set(registration) == {"path", "sha256", "bytes"}, "completion report registration closure mismatch")
    _require(SAFE_BASENAME.fullmatch(str(registration["path"])) is not None, "completion report path must be a basename")
    _require(HEX64.fullmatch(str(registration["sha256"])) is not None, "completion report digest mismatch")
    _require(isinstance(registration["bytes"], int) and registration["bytes"] > 0, "completion report bytes invalid")
    return manifest


def finalize_publication(
    baseline: types.ModuleType,
    config: dict[str, Any],
    source: dict[str, Any],
    context: dict[str, Any],
    records: Sequence[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    output = config["output"]
    journal_path = output_dir / output["checkpoint_journal"]
    json_path = output_dir / output["json_report"]
    markdown_path = output_dir / output["markdown_report"]
    completion_path = output_dir / output["completion_manifest"]
    report = assemble_report(config, source, context, records, journal_path)
    markdown = build_markdown_report(report).encode("utf-8")
    report["artifact_manifest"] = [
        {
            "path": journal_path.name,
            "sha256": sha256_file(journal_path),
            "bytes": journal_path.stat().st_size,
            "classification": "hash-chained aggregate completed-cell journal",
        },
        {
            "path": markdown_path.name,
            "sha256": hashlib.sha256(markdown).hexdigest(),
            "bytes": len(markdown),
            "classification": "aggregate public-facing experimental summary",
        },
    ]
    report["report_body_sha256"] = canonical_sha256(report)
    _assert_aggregate_only(report)
    # Markdown intentionally ignores artifact_manifest/report_body_sha256, so
    # it can be hash-bound by the JSON without a circular dependency.
    _require(build_markdown_report(report).encode("utf-8") == markdown, "Markdown rendering is not stable")
    json_payload = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"
    completion = validate_completion_manifest({
        "schema_version": "1.0",
        "status": "complete",
        "experiment_id": config["experiment_id"],
        "report": {
            "path": json_path.name,
            "sha256": hashlib.sha256(json_payload).hexdigest(),
            "bytes": len(json_payload),
        },
        "authority": dict(AUTHORITY),
    })
    completion_payload = json.dumps(completion, indent=2, ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"
    enforce_host_rss_budget(config)
    artifact_ceiling = int(config["resource_budget"]["aggregate_artifact_bytes_ceiling"])
    enforce_aggregate_artifact_budget(
        [
            journal_path.stat().st_size,
            len(json_payload),
            len(markdown),
            len(completion_payload),
        ],
        artifact_ceiling,
    )
    _write_or_verify(json_path, json_payload, baseline)
    _write_or_verify(markdown_path, markdown, baseline)
    enforce_host_rss_budget(config)
    enforce_aggregate_artifact_budget(
        [
            journal_path.stat().st_size,
            json_path.stat().st_size,
            markdown_path.stat().st_size,
            len(completion_payload),
        ],
        artifact_ceiling,
    )
    # RUN_COMPLETE is the final publication signal.  All fallible resource
    # checks use actual journal/report sizes plus the exact completion payload
    # before this write; no resource check is allowed after it exists.
    _write_or_verify(completion_path, completion_payload, baseline)
    registrations = [
        {
            "path": path.name,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in (journal_path, json_path, markdown_path)
    ]
    baseline.verify_registered_artifact_entries(
        output_dir,
        registrations,
        completion_manifest_name=completion_path.name,
    )
    _require(
        json.loads(completion_path.read_text(encoding="utf-8")) == completion,
        "completion manifest changed after publication",
    )
    return completion


def _prepare_output_directory(output_dir: Path, config: dict[str, Any], *, resume: bool) -> None:
    if output_dir.exists():
        _require(output_dir.is_dir() and not output_dir.is_symlink(), "output must be a non-symlink directory")
        entries = {item.name for item in output_dir.iterdir()}
        allowed = {
            config["output"]["checkpoint_journal"],
            config["output"]["json_report"],
            config["output"]["markdown_report"],
            config["output"]["completion_manifest"],
        }
        _require(entries <= allowed, "output directory contains unexpected artifacts")
        _require(resume or not entries, "non-empty output requires --resume")
        os.chmod(output_dir, 0o700)
    else:
        output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(output_dir, 0o700)


def _validate_existing_completion(output_dir: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    completion_path = output_dir / config["output"]["completion_manifest"]
    if not completion_path.exists():
        return None
    _require(completion_path.is_file() and not completion_path.is_symlink(), "completion manifest is not regular")
    manifest = validate_completion_manifest(_strict_json_object(completion_path.read_bytes()))
    report_path = output_dir / manifest["report"]["path"]
    _require(report_path.is_file() and not report_path.is_symlink(), "registered report is missing")
    _require(report_path.stat().st_size == manifest["report"]["bytes"], "registered report byte size mismatch")
    _require(sha256_file(report_path) == manifest["report"]["sha256"], "registered report digest mismatch")
    report = _strict_json_object(report_path.read_bytes())
    validate_suite_export(report.get("suite_export", {}))
    _require(report.get("authority") == AUTHORITY, "completed report authority mismatch")
    artifact_manifest = report.get("artifact_manifest")
    _require(isinstance(artifact_manifest, list) and len(artifact_manifest) == 2, "completed artifact manifest mismatch")
    registered_names = {item.get("path") for item in artifact_manifest}
    _require(
        registered_names == {
            config["output"]["checkpoint_journal"],
            config["output"]["markdown_report"],
        },
        "completed companion artifact closure mismatch",
    )
    for item in artifact_manifest:
        path = output_dir / str(item["path"])
        _require(path.is_file() and not path.is_symlink(), "completed companion artifact is missing")
        _require(path.stat().st_size == int(item["bytes"]), "completed companion artifact byte mismatch")
        _require(sha256_file(path) == item["sha256"], "completed companion artifact digest mismatch")
    _require(
        {item.name for item in output_dir.iterdir()} == {
            config["output"]["checkpoint_journal"],
            config["output"]["json_report"],
            config["output"]["markdown_report"],
            config["output"]["completion_manifest"],
        },
        "completed output artifact closure mismatch",
    )
    enforce_host_rss_budget(config)
    enforce_aggregate_artifact_budget(
        [item.stat().st_size for item in output_dir.iterdir()],
        int(config["resource_budget"]["aggregate_artifact_bytes_ceiling"]),
    )
    return manifest


def _previously_consumed_seconds(records: Sequence[dict[str, Any]]) -> float:
    return sum(float(record["payload"]["resource"]["wall_clock_seconds"]) for record in records)


def run(
    config_path: Path,
    output_dir: Path,
    cache_dir: Path,
    *,
    offline: bool,
    resume: bool,
    deadline_utc: datetime | None,
) -> dict[str, Any]:
    config, config_bytes = load_config(config_path)
    source_start = _source_snapshot(config_path, config_bytes)
    baseline = load_verified_baseline_module()
    baseline_config = load_and_validate_baseline_config(config, baseline)
    baseline.require_disjoint_run_and_cache_paths(output_dir, cache_dir)
    _prepare_output_directory(output_dir, config, resume=resume)
    existing_completion = _validate_existing_completion(output_dir, config)
    if existing_completion is not None:
        _require(resume, "completed output cannot be reused without --resume")
        return existing_completion

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    import transformers

    _require(torch.cuda.is_available(), "the registered composition experiment requires CUDA")
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda")
    runtime = runtime_identity(torch, transformers)
    context = journal_context(config, source_start, runtime)
    context_sha256 = canonical_sha256(context)
    journal_path = output_dir / config["output"]["checkpoint_journal"]
    records = _parse_journal(
        journal_path,
        context_sha256=context_sha256,
        repair_trailing_partial=resume,
    )
    if len(records) < len(expected_journal_keys()):
        for final_name in (config["output"]["json_report"], config["output"]["markdown_report"]):
            _require(not (output_dir / final_name).exists(), "final report exists before exact journal closure")

    if deadline_utc is not None:
        _require(
            (deadline_utc - datetime.now(timezone.utc)).total_seconds()
            <= float(config["resource_budget"]["maximum_gpu_hours"]) * 3600.0,
            "deadline override may only tighten the registered 12-hour budget",
        )
    budget = ExecutionBudget(
        config,
        previously_consumed_seconds=_previously_consumed_seconds(records),
        deadline_utc=deadline_utc,
    )
    if len(records) == len(expected_journal_keys()):
        source_end = _source_snapshot(config_path, config_bytes)
        _require(source_end == source_start, "source files changed before finalization")
        return finalize_publication(
            baseline, config, source_start, context, records, output_dir
        )

    train_records, holdout_records, dataset_report = acquire_registered_dataset(
        baseline, baseline_config, cache_dir, offline=offline
    )
    if records:
        _require(
            records[0]["payload"]["dataset"] == dataset_report,
            "reacquired dataset aggregates differ from the completed preflight",
        )
    hook_path = ROOT / config["baseline_binding"]["hook_path"]
    hook_bytes = hook_path.read_bytes()
    _require(hashlib.sha256(hook_bytes).hexdigest() == EXPECTED_HOOK_SHA256, "hook source hash mismatch")
    hook_module = baseline.load_verified_hook_module(
        hook_bytes, hook_path, EXPECTED_HOOK_SHA256
    )
    collector_class = hook_module.AggregateTrainingHookCollector
    prepared_by_model: dict[str, dict[str, Any]] = {}
    for model_config in baseline_config["models"]:
        prepared_by_model[model_config["key"]] = _load_tokenizer_and_snapshot(
            baseline,
            model_config,
            baseline_config,
            train_records,
            holdout_records,
            cache_dir,
            offline=offline,
        )

    if not records:
        preflight_started = time.perf_counter()
        microbenchmarks = []
        for model_key in MODEL_KEYS:
            print(f"hook microbenchmark start: model={model_key}", file=sys.stderr, flush=True)
            microbenchmarks.append(run_hook_microbenchmark(
                baseline,
                prepared_by_model[model_key],
                collector_class=collector_class,
                torch=torch,
                device=device,
                config=config,
                budget=budget,
            ))
        preflight_memory = gpu_memory_snapshot(torch, device)
        enforce_gpu_memory_budget(preflight_memory, config)
        preflight = {
            "schema_version": "1.0",
            "dataset": dataset_report,
            "hook_microbenchmarks": microbenchmarks,
            "resource": {
                "wall_clock_seconds": time.perf_counter() - preflight_started,
                "peak_gpu_allocated_bytes": max(
                    [int(preflight_memory["peak_allocated_bytes"])]
                    + [int(item["resource"]["peak_gpu_allocated_bytes"]) for item in microbenchmarks]
                ),
                "peak_gpu_reserved_bytes": max(
                    [int(preflight_memory["peak_reserved_bytes"])]
                    + [int(item["resource"]["peak_gpu_reserved_bytes"]) for item in microbenchmarks]
                ),
                "peak_host_rss_bytes": max(
                    [host_peak_rss_bytes()]
                    + [int(item["resource"]["peak_host_rss_bytes"]) for item in microbenchmarks]
                ),
            },
            "record_identifiers_persisted": False,
            "per_example_values_persisted": False,
            "raw_telemetry_persisted": False,
            **AUTHORITY,
        }
        append_journal_record(
            journal_path,
            records,
            context_sha256=context_sha256,
            record_type="hook_microbenchmark_bundle",
            record_key="hook-microbenchmark-bundle",
            payload=preflight,
            artifact_bytes_ceiling=int(
                config["resource_budget"]["aggregate_artifact_bytes_ceiling"]
            ),
        )

    schedule = [(scale, seed) for scale in TRAIN_SCALES for seed in TRAINING_SEEDS]
    completed_bundles = len(records) - 1
    base_cache: dict[str, Any] = {}
    for scale, training_seed in schedule[completed_bundles:]:
        budget.check(
            minimum_remaining_seconds=float(
                config["resource_budget"]["minimum_remaining_seconds_to_start_model_cell"]
            )
        )
        bundle = run_scale_seed_bundle(
            baseline,
            prepared_by_model,
            scale=scale,
            training_seed=training_seed,
            base_cache=base_cache,
            collector_class=collector_class,
            torch=torch,
            device=device,
            config=config,
            budget=budget,
        )
        append_journal_record(
            journal_path,
            records,
            context_sha256=context_sha256,
            record_type="scale_seed_model_bundle",
            record_key=f"scale-{scale}-seed-{training_seed}",
            payload=bundle,
            artifact_bytes_ceiling=int(
                config["resource_budget"]["aggregate_artifact_bytes_ceiling"]
            ),
        )
        print(
            f"bundle complete: scale={scale} seed={training_seed}; journal={len(records)}/16",
            file=sys.stderr,
            flush=True,
        )

    _require(len(records) == len(expected_journal_keys()), "execution ended without exact journal closure")
    source_end = _source_snapshot(config_path, config_bytes)
    _require(source_end == source_start, "source files changed during execution")
    return finalize_publication(
        baseline, config, source_start, context, records, output_dir
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the resumable real-WildChat three-model composition-scaling matrix"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--run-id")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--deadline-utc", help="ISO-8601 UTC deadline; may only tighten the 12-hour budget")
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
    else:
        run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        _require(SAFE_BASENAME.fullmatch(run_id) is not None, "run-id must be a safe basename")
        output_dir = (ROOT / "output" / "composition-scaling" / "llm" / run_id).resolve()
    completion = run(
        config_path,
        output_dir,
        args.cache_dir.resolve(),
        offline=args.offline,
        resume=args.resume,
        deadline_utc=_parse_deadline(args.deadline_utc),
    )
    print(json.dumps({
        "status": completion["status"],
        "experiment_id": completion["experiment_id"],
        "decision": completion["authority"]["decision"],
        "report": completion["report"]["path"],
        "report_sha256": completion["report"]["sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
