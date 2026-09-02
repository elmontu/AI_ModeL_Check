#!/usr/bin/env python3
"""Validate, optionally execute, and aggregate the five-model composition suite.

The suite deliberately keeps two kinds of composition separate:

* empirical scalar composition is permitted only for models evaluated over the
  same registered protected-unit population; and
* mixed LLM/vision subsets expose only resource and policy-gate vectors.

Child reports are untrusted inputs.  Only their small, aggregate-only
``suite_export`` objects are accepted, and an unfamiliar shape fails closed.
This module is standard-library-only so its contract tests do not require an ML
runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "reproduction" / "composition-scaling" / "suite-config.json"

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_BASENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_JSON_BYTES = 64 * 1024 * 1024

MODEL_KEYS = (
    "distilgpt2",
    "meta-opt-125m",
    "pythia-160m",
    "alexnet",
    "densenet121",
)
LLM_MODEL_KEYS = MODEL_KEYS[:3]
VISION_MODEL_KEYS = MODEL_KEYS[3:]
SEEDS = (3407, 499625614, 4288481424, 2669540432, 2937338177)
SCALES = {
    "llm": (2048, 4096, 8192),
    "vision": (5400, 10800, 21600),
}
PROTECTED_UNIT_POPULATIONS = {
    "llm": "wildchat_training_record",
    "vision": "eurosat_test_image",
}

MAX_WALL_CLOCK_SECONDS = 12 * 60 * 60
MAX_BYTES = 20 * 1024**3

BASE_BINDINGS = {
    "llm": {
        "config_path": "reproduction/llm-training-hook/config.json",
        "config_sha256": "39e5b5fe8eed4ebb1d512063d6e13a0e8f24656f9043063e879bd0d5d5141480",
        "runner_path": "scripts/run_llm_training_hook_audit.py",
        "runner_sha256": "8b0bca73293e20232ac45e35b2762e254977fbdbe09f70967be257ee05719ffd",
        "hook_path": "scripts/llm_training_hooks.py",
        "hook_sha256": "595de99355974866524ca1e11c0cd4d2d14c80a0846657daea36d66ee26ff33c",
    },
    "vision": {
        "config_path": "reproduction/vision-training-hook/config.json",
        "config_sha256": "3f2ef402e9e2a6fb3a2fb47a930de30384056682d85dae6c2134694dd6aa1412",
        "runner_path": "scripts/run_vision_training_hook_audit.py",
        "runner_sha256": "85261cd39de3036211fff174b7b9bce5aaf87a69baac17cd42b03aff9eb03e81",
        "hook_path": "scripts/llm_training_hooks.py",
        "hook_sha256": "595de99355974866524ca1e11c0cd4d2d14c80a0846657daea36d66ee26ff33c",
    },
}

CHILD_BINDINGS = {
    "llm": {
        "config_path": "reproduction/composition-scaling/llm-config.json",
        "config_sha256": "4924a2a4bf3f5176d28793a10295e7b7d50c5e007011a8f0d8cd06b90ba4f416",
        "runner_path": "scripts/run_llm_composition_scaling.py",
        "runner_sha256": "dbe867cd3df97552fd97680c7df0a4d7a1ff9825617c57f4d8399ad3f714cd92",
        "experiment_id": "llm-composition-scaling-wildchat-three-model-v1",
        "report_basename": "llm-composition-scaling-report.json",
        "completion_manifest_basename": "RUN_COMPLETE.json",
    },
    "vision": {
        "config_path": "reproduction/composition-scaling/vision-config.json",
        "config_sha256": "e58f0fa0043c9cfe53a6970e05b8d40fbb3bc52a0b59d4928edb85aee126839b",
        "runner_path": "scripts/run_vision_composition_scaling.py",
        "runner_sha256": "1fec50133c6f6f60e087ce2e373acfdf0a6d9a1854d606752e86bfbae660994b",
        "experiment_id": "vision-eurosat-hook-composition-scaling-v1",
        "report_basename": "vision-composition-scaling-report.json",
        "completion_manifest_basename": "RUN_COMPLETE.json",
    },
}

INTERFACE_FIELDS = (
    "basic_prediction",
    "generated_token_log_probabilities",
    "class_scores",
    "exact_candidate_source_metadata",
    "exact_candidate_preprocessing_metadata",
    "arbitrary_candidate_scoring",
    "model_weights",
    "embeddings_and_activations",
    "per_example_loss",
    "gradients",
    "source_provenance",
    "exact_protected_training_roster",
)

EXPECTED_INTERFACE_MASKS = {
    # These are explicit recipient interfaces, not an ordinal or cumulative
    # disclosure ladder.  In particular, R2 and R3 expose different channels.
    "R0": (1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "R1": (1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "R2": (1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0),
    "R3": (1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0),
    "R4": (1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0),
    "R5": (1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1),
}

INTERFACE_KNOWLEDGE_BINDINGS = {
    "R0": {"llm_knowledge_levels": ["K0"], "vision_profile": "M0_label_only"},
    "R1": {"llm_knowledge_levels": ["K0"], "vision_profile": "M1_scores"},
    "R2": {"llm_knowledge_levels": ["K0", "K1"], "vision_profile": "NOT_MEASURED"},
    "R3": {"llm_knowledge_levels": ["K0", "K2"], "vision_profile": "M2_internal_features"},
    "R4": {"llm_knowledge_levels": ["K0", "K1", "K2", "K3"], "vision_profile": "M2_internal_features"},
    "R5": {"llm_knowledge_levels": ["K0", "K4"], "vision_profile": "M3_source_provenance"},
}

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

GATE_AXES = (
    "model_license",
    "data_rights",
    "interface_disclosure",
    "evidence_authority",
    "robustness",
    "fairness",
)
GATE_SEVERITY = (
    "NOT_ASSESSED",
    "DECLARED_REQUIRES_INDEPENDENT_REVIEW",
    "LEGAL_REVIEW_REQUIRED",
    "MANUAL_REVIEW_REQUIRED",
    "APPROVED_RECOLLECTION_REQUIRED",
    "RESTRICTED_AUDITOR_ONLY",
    "BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY",
    "BLOCKED_AND_REDESIGN_REQUIRED",
)
ABSORBING_GATES = {
    "BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY",
    "BLOCKED_AND_REDESIGN_REQUIRED",
}

MODEL_GATE_CONTRIBUTIONS = {
    "distilgpt2": {
        "model_license": "DECLARED_REQUIRES_INDEPENDENT_REVIEW",
        "data_rights": "MANUAL_REVIEW_REQUIRED",
        "evidence_authority": "APPROVED_RECOLLECTION_REQUIRED",
    },
    "meta-opt-125m": {
        "model_license": "BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY",
        "data_rights": "MANUAL_REVIEW_REQUIRED",
        "evidence_authority": "APPROVED_RECOLLECTION_REQUIRED",
    },
    "pythia-160m": {
        "model_license": "MANUAL_REVIEW_REQUIRED",
        "data_rights": "MANUAL_REVIEW_REQUIRED",
        "evidence_authority": "APPROVED_RECOLLECTION_REQUIRED",
    },
    "alexnet": {
        "model_license": "DECLARED_REQUIRES_INDEPENDENT_REVIEW",
        "data_rights": "MANUAL_REVIEW_REQUIRED",
        "evidence_authority": "APPROVED_RECOLLECTION_REQUIRED",
    },
    "densenet121": {
        "model_license": "DECLARED_REQUIRES_INDEPENDENT_REVIEW",
        "data_rights": "MANUAL_REVIEW_REQUIRED",
        "evidence_authority": "APPROVED_RECOLLECTION_REQUIRED",
    },
}

INTERFACE_GATE_CONTRIBUTIONS = {
    "R0": "MANUAL_REVIEW_REQUIRED",
    "R1": "MANUAL_REVIEW_REQUIRED",
    "R2": "MANUAL_REVIEW_REQUIRED",
    "R3": "RESTRICTED_AUDITOR_ONLY",
    "R4": "RESTRICTED_AUDITOR_ONLY",
    "R5": "BLOCKED_AND_REDESIGN_REQUIRED",
}

LLM_METRICS = (
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
)

# The vision worker emits this fixed aggregate vocabulary.  The disagreement
# field names its registered 512-image ensemble-FGSM condition explicitly;
# singleton rows encode not-applicable as 0.  No per-image values or source
# names are accepted by the shared suite.
VISION_METRICS = (
    "clean_top1_accuracy",
    "clean_mean_cross_entropy",
    "brightness_top1_accuracy",
    "gaussian_noise_top1_accuracy",
    "ensemble_fgsm_top1_accuracy",
    "ensemble_fgsm_attack_success_rate_on_clean_correct",
    "ensemble_fgsm_member_prediction_disagreement",
)

CHILD_EXPORT_KEYS = {
    "schema_version",
    "modality",
    "protected_unit_population",
    "model_keys",
    "seeds",
    "scales",
    "authority",
    "resources",
    "subset_scalars",
}
RESOURCE_KEYS = {
    "model_key",
    "wall_clock_seconds",
    "peak_gpu_reserved_bytes",
    "peak_host_rss_bytes",
    "artifact_bytes",
}
SCALAR_ROW_KEYS = {"model_keys", "scale", "seed", "metrics"}

FORBIDDEN_AGGREGATE_KEYS = {
    "path",
    "paths",
    "identifier",
    "identifiers",
    "record_id",
    "record_ids",
    "row_id",
    "row_ids",
    "sample_id",
    "sample_ids",
    "example_id",
    "example_ids",
    "run_id",
    "run_ids",
    "per_example",
    "per_record",
    "dialogue_text",
    "prompt_text",
    "raw_tokens",
    "raw_images",
    "raw_logits",
    "raw_activations",
    "raw_gradients",
}


class SuiteValidationError(ValueError):
    """Raised when a registered suite or child artifact fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SuiteValidationError(message)


def _reject_constant(value: str) -> None:
    raise SuiteValidationError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SuiteValidationError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_json_object(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    """Load a bounded JSON object while rejecting duplicates and NaN values."""

    _require(path.is_file(), "registered JSON file is missing")
    size = path.stat().st_size
    _require(0 < size <= max_bytes, "registered JSON size is outside its bound")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SuiteValidationError("registered JSON is unreadable or invalid") from exc
    _require(isinstance(value, dict), "registered JSON root must be an object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    _require(actual == expected, f"{label} keys differ: expected {sorted(expected)}, got {sorted(actual)}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _relative_registered_file(root: Path, logical_name: str) -> Path:
    _require(isinstance(logical_name, str), "registered source name must be a string")
    pure = PurePosixPath(logical_name)
    _require(not pure.is_absolute(), "registered source name must be repository-relative")
    _require(".." not in pure.parts and "." not in pure.parts, "registered source name may not traverse")
    _require(all(part not in {"", "/"} for part in pure.parts), "registered source name is malformed")
    candidate = root.joinpath(*pure.parts)
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    _require(resolved == resolved_root or resolved_root in resolved.parents, "registered source escapes repository")
    _require(candidate.is_file() and not candidate.is_symlink(), "registered source must be a regular non-symlink file")
    return candidate


def _all_nonempty_subsets(keys: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        subset
        for size in range(1, len(keys) + 1)
        for subset in itertools.combinations(keys, size)
    )


ALL_SUBSETS = _all_nonempty_subsets(MODEL_KEYS)
LLM_SUBSETS = _all_nonempty_subsets(LLM_MODEL_KEYS)
VISION_SUBSETS = _all_nonempty_subsets(VISION_MODEL_KEYS)
CROSS_MODAL_SUBSETS = tuple(
    subset
    for subset in ALL_SUBSETS
    if any(key in LLM_MODEL_KEYS for key in subset)
    and any(key in VISION_MODEL_KEYS for key in subset)
)


def _validate_binding(
    binding: Mapping[str, Any],
    *,
    expected: Mapping[str, str] | None,
    root: Path,
    verify_files: bool,
    label: str,
) -> None:
    _exact_keys(binding, {"config_path", "config_sha256", "runner_path", "runner_sha256", "hook_path", "hook_sha256"}, label)
    if expected is not None:
        _require(dict(binding) == dict(expected), f"{label} differs from frozen base binding")
    for path_key, digest_key in (
        ("config_path", "config_sha256"),
        ("runner_path", "runner_sha256"),
        ("hook_path", "hook_sha256"),
    ):
        digest = binding[digest_key]
        _require(isinstance(digest, str) and HEX64.fullmatch(digest) is not None, f"{label} has invalid digest")
        if verify_files:
            source = _relative_registered_file(root, binding[path_key])
            _require(file_sha256(source) == digest, f"{label} source digest mismatch for {path_key}")


def _validate_child_binding(
    binding: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
    root: Path,
    verify_files: bool,
    label: str,
) -> None:
    expected_keys = {
        "config_path",
        "config_sha256",
        "runner_path",
        "runner_sha256",
        "experiment_id",
        "report_basename",
        "completion_manifest_basename",
    }
    _exact_keys(binding, expected_keys, label)
    _require(dict(binding) == dict(expected), f"{label} differs from the frozen composition-worker binding")
    for name in ("report_basename", "completion_manifest_basename"):
        _require(SAFE_BASENAME.fullmatch(str(binding[name])) is not None, f"{label} has unsafe output basename")
    _require(binding["completion_manifest_basename"] == "RUN_COMPLETE.json", f"{label} must publish RUN_COMPLETE.json last")
    for path_key, digest_key in (("config_path", "config_sha256"), ("runner_path", "runner_sha256")):
        digest = binding[digest_key]
        _require(isinstance(digest, str) and HEX64.fullmatch(digest) is not None, f"{label} has invalid digest")
        if verify_files:
            source = _relative_registered_file(root, binding[path_key])
            _require(file_sha256(source) == digest, f"{label} source digest mismatch for {path_key}")


def validate_config(
    raw: Mapping[str, Any], *, verify_files: bool = True, root: Path = ROOT
) -> dict[str, Any]:
    """Validate the closed, frozen suite configuration and source bindings."""

    _require(isinstance(raw, Mapping), "suite config must be an object")
    top_keys = {
        "schema_version",
        "experiment_id",
        "experimental_only",
        "assessment_input_emitted",
        "attack_battery_eligible",
        "authorization_eligible",
        "authorization_granted",
        "can_clear",
        "can_block",
        "requires_approved_recollection",
        "decision",
        "models",
        "source_bindings",
        "matrix",
        "interfaces",
        "gate_policy",
        "execution",
        "child_contract",
        "output",
    }
    _exact_keys(raw, top_keys, "suite config")
    _require(raw["schema_version"] == "1.0", "suite schema_version must be 1.0")
    _require(raw["experiment_id"] == "five-model-composition-scaling-v1", "suite experiment_id is frozen")
    for key, expected in AUTHORITY.items():
        _require(raw[key] == expected and type(raw[key]) is type(expected), f"suite authority flag {key} must be {expected}")

    models = raw["models"]
    _require(isinstance(models, list) and len(models) == 5, "exactly five models are required")
    expected_model_entries = [
        {
            "key": "distilgpt2",
            "modality": "llm",
            "implementation": "distilbert/distilgpt2",
            "revision": "2290a62682d06624634c1f46a6ad5be0f47f38aa",
        },
        {
            "key": "meta-opt-125m",
            "modality": "llm",
            "implementation": "facebook/opt-125m",
            "revision": "27dcfa74d334bc871f3234de431e71c6eeba5dd6",
        },
        {
            "key": "pythia-160m",
            "modality": "llm",
            "implementation": "EleutherAI/pythia-160m",
            "revision": "50f5173d932e8e61f858120bcb800b97af589f46",
        },
        {
            "key": "alexnet",
            "modality": "vision",
            "implementation": "torchvision.models.alexnet",
            "revision": "torchvision-0.28.0",
        },
        {
            "key": "densenet121",
            "modality": "vision",
            "implementation": "torchvision.models.densenet121",
            "revision": "torchvision-0.28.0",
        },
    ]
    _require(models == expected_model_entries, "five-model registry differs from the frozen suite")

    source_bindings = raw["source_bindings"]
    _exact_keys(source_bindings, {"base_protocols", "children"}, "source_bindings")
    _exact_keys(source_bindings["base_protocols"], {"llm", "vision"}, "base_protocols")
    _exact_keys(source_bindings["children"], {"llm", "vision"}, "children")
    for modality in ("llm", "vision"):
        _validate_binding(
            source_bindings["base_protocols"][modality],
            expected=BASE_BINDINGS[modality],
            root=root,
            verify_files=verify_files,
            label=f"base_protocols.{modality}",
        )
        _validate_child_binding(
            source_bindings["children"][modality],
            expected=CHILD_BINDINGS[modality],
            root=root,
            verify_files=verify_files,
            label=f"children.{modality}",
        )

    matrix = raw["matrix"]
    _exact_keys(
        matrix,
        {
            "seeds",
            "real_scales",
            "all_nonempty_model_subsets",
            "llm_same_population_subsets",
            "vision_same_population_subsets",
            "cross_modal_subsets",
            "expected_counts",
            "cell_authority",
            "scalar_composition_rule",
            "cross_modal_composition_rule",
        },
        "matrix",
    )
    _require(tuple(matrix["seeds"]) == SEEDS, "suite seeds differ from the frozen five-seed design")
    _require(tuple(matrix["real_scales"]["llm"]) == SCALES["llm"], "LLM scales must be 2048/4096/8192")
    _require(tuple(matrix["real_scales"]["vision"]) == SCALES["vision"], "vision scales must be 5400/10800/21600")

    def tuples(value: Any, label: str) -> tuple[tuple[str, ...], ...]:
        _require(isinstance(value, list), f"{label} must be a list")
        converted = tuple(tuple(item) for item in value)
        _require(all(item for item in converted), f"{label} may not contain the empty subset")
        return converted

    _require(tuples(matrix["all_nonempty_model_subsets"], "all subsets") == ALL_SUBSETS, "31-subset registry is not the canonical power set")
    _require(tuples(matrix["llm_same_population_subsets"], "LLM subsets") == LLM_SUBSETS, "LLM subset registry must contain the seven nonempty subsets")
    _require(tuples(matrix["vision_same_population_subsets"], "vision subsets") == VISION_SUBSETS, "vision subset registry must contain the three nonempty subsets")
    _require(tuples(matrix["cross_modal_subsets"], "cross-modal subsets") == CROSS_MODAL_SUBSETS, "cross-modal subset registry must contain the remaining 21 subsets")
    _require(
        matrix["expected_counts"]
        == {
            "all_nonempty_model_subsets": 31,
            "llm_same_population_subsets": 7,
            "vision_same_population_subsets": 3,
            "cross_modal_subsets": 21,
            "llm_scalar_cells": 105,
            "vision_scalar_cells": 45,
            "total_scalar_cells": 150,
        },
        "matrix expected counts are frozen",
    )
    _require(matrix["cell_authority"] == AUTHORITY, "every registered matrix cell must remain non-authorizing")
    _require(
        matrix["scalar_composition_rule"]
        == "permitted_only_within_one_registered_shared_protected_unit_population",
        "scalar composition boundary is frozen",
    )
    _require(
        matrix["cross_modal_composition_rule"]
        == "resource_and_gate_vectors_only_no_empirical_scalar",
        "cross-modal composition must remain vector-valued",
    )

    interfaces = raw["interfaces"]
    _exact_keys(interfaces, {"mask_fields", "profiles"}, "interfaces")
    _require(tuple(interfaces["mask_fields"]) == INTERFACE_FIELDS, "interface mask field order is frozen")
    profiles = interfaces["profiles"]
    _require(isinstance(profiles, list) and len(profiles) == 6, "interfaces must define R0-R5")
    for index, profile in enumerate(profiles):
        level = f"R{index}"
        _exact_keys(
            profile,
            {
                "level",
                "description",
                "mask",
                "llm_knowledge_levels",
                "vision_profile",
                "screen_authority",
            },
            f"interface {level}",
        )
        _require(profile["level"] == level, "interface levels must be ordered R0-R5")
        _exact_keys(profile["mask"], set(INTERFACE_FIELDS), f"interface {level} mask")
        observed_mask = tuple(bool(profile["mask"][field]) for field in INTERFACE_FIELDS)
        expected_mask = tuple(bool(value) for value in EXPECTED_INTERFACE_MASKS[level])
        _require(observed_mask == expected_mask, f"interface {level} mask differs from the frozen disclosure boundary")
        _require(
            {
                "llm_knowledge_levels": profile["llm_knowledge_levels"],
                "vision_profile": profile["vision_profile"],
            }
            == INTERFACE_KNOWLEDGE_BINDINGS[level],
            f"interface {level} knowledge mapping differs",
        )
        _require(profile["screen_authority"] == AUTHORITY, f"interface {level} must remain non-authorizing")

    gate = raw["gate_policy"]
    _exact_keys(
        gate,
        {
            "axes",
            "severity_order",
            "absorbing_gates",
            "propagation",
            "gate_averaging_allowed",
            "model_contributions",
            "interface_contributions",
            "commercial_context",
            "exact_roster_rule",
        },
        "gate_policy",
    )
    _require(tuple(gate["axes"]) == GATE_AXES, "gate axes are frozen")
    _require(tuple(gate["severity_order"]) == GATE_SEVERITY, "gate severity order is frozen")
    _require(set(gate["absorbing_gates"]) == ABSORBING_GATES, "absorbing gate set is frozen")
    _require(gate["propagation"] == "worst_per_axis_with_absorbing_blocks", "gate propagation must be worst-per-axis")
    _require(gate["gate_averaging_allowed"] is False, "gates may never be averaged")
    _require(gate["model_contributions"] == MODEL_GATE_CONTRIBUTIONS, "model gate contributions differ")
    _require(gate["interface_contributions"] == INTERFACE_GATE_CONTRIBUTIONS, "interface gate contributions differ")
    _require(gate["commercial_context"] is True, "Meta OPT commercial restriction must be evaluated")
    _require(
        gate["exact_roster_rule"]
        == "logical_direct_disclosure_blocks_and_requires_interface_redesign",
        "exact protected roster must block and require redesign",
    )

    execution = raw["execution"]
    _exact_keys(
        execution,
        {
            "mode",
            "child_order",
            "gpu_parallelism",
            "visible_gpu_index",
            "shell",
            "max_wall_clock_seconds",
            "max_gpu_reserved_bytes",
            "max_host_rss_bytes",
            "max_aggregate_artifact_bytes",
            "child_cache_defaults",
            "child_cli_contract",
        },
        "execution",
    )
    _require(execution["mode"] == "serial_one_gpu", "suite execution must remain serial on one GPU")
    _require(execution["child_order"] == ["llm", "vision"], "child order must be deterministic")
    _require(execution["gpu_parallelism"] == 1 and execution["visible_gpu_index"] == 0, "exactly one visible GPU is required")
    _require(execution["shell"] is False, "child commands must not use a shell")
    _require(
        execution["child_cache_defaults"]
        == {
            "llm": "output/llm-training-hook/cache",
            "vision": "output/cache/vision-training-hook",
        },
        "child cache roots must bind the verified worker caches",
    )
    for key, limit in (
        ("max_wall_clock_seconds", MAX_WALL_CLOCK_SECONDS),
        ("max_gpu_reserved_bytes", MAX_BYTES),
        ("max_host_rss_bytes", MAX_BYTES),
        ("max_aggregate_artifact_bytes", MAX_BYTES),
    ):
        _require(isinstance(execution[key], int) and 0 < execution[key] <= limit, f"execution ceiling {key} exceeds the hard suite limit")
    _require(
        execution["child_cli_contract"]
        == ["--config", "--output-dir", "--cache-dir", "--offline"],
        "child CLI contract is frozen",
    )

    child_contract = raw["child_contract"]
    _exact_keys(
        child_contract,
        {
            "schema_version",
            "completion_status",
            "manifest_report_fields",
            "suite_export_keys",
            "resource_keys",
            "scalar_row_keys",
            "metrics",
            "unknown_shape_policy",
        },
        "child_contract",
    )
    _require(child_contract["schema_version"] == "1.0", "child export schema is frozen")
    _require(child_contract["completion_status"] == "complete", "child completion status is frozen")
    _require(child_contract["manifest_report_fields"] == ["path", "sha256", "bytes"], "child report registration must bind name, digest, and bytes")
    _require(set(child_contract["suite_export_keys"]) == CHILD_EXPORT_KEYS, "child export keys differ")
    _require(set(child_contract["resource_keys"]) == RESOURCE_KEYS, "child resource keys differ")
    _require(set(child_contract["scalar_row_keys"]) == SCALAR_ROW_KEYS, "child scalar row keys differ")
    _require(tuple(child_contract["metrics"]["llm"]) == LLM_METRICS, "LLM aggregate metric vocabulary differs")
    _require(tuple(child_contract["metrics"]["vision"]) == VISION_METRICS, "vision aggregate metric vocabulary differs")
    _require(child_contract["unknown_shape_policy"] == "fail_closed", "unknown child shapes must fail closed")

    output = raw["output"]
    _exact_keys(
        output,
        {
            "aggregate_json",
            "aggregate_markdown",
            "completion_manifest",
            "directory_mode",
            "artifact_mode",
            "contains_record_identifiers",
            "contains_machine_paths",
            "contains_per_example_data",
            "completion_written_last",
        },
        "output",
    )
    expected_names = {
        "aggregate_json": "composition-scaling-suite-report.json",
        "aggregate_markdown": "composition-scaling-suite-report.md",
        "completion_manifest": "RUN_COMPLETE.json",
    }
    for key, expected in expected_names.items():
        _require(output[key] == expected and SAFE_BASENAME.fullmatch(output[key]) is not None, f"output {key} is frozen")
    _require(output["directory_mode"] == "0700" and output["artifact_mode"] == "0600", "output permissions are frozen")
    for key in ("contains_record_identifiers", "contains_machine_paths", "contains_per_example_data"):
        _require(output[key] is False, f"safe output contract requires {key}=false")
    _require(output["completion_written_last"] is True, "RUN_COMPLETE must be the final write")

    return dict(raw)


def load_and_validate_config(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    raw = load_json_object(path, max_bytes=2 * 1024 * 1024)
    return validate_config(raw, verify_files=True, root=root)


def worst_gate(values: Iterable[str]) -> str:
    """Return the worst categorical gate; no numerical averaging is possible."""

    ranks = {gate: index for index, gate in enumerate(GATE_SEVERITY)}
    observed = tuple(values)
    _require(bool(observed), "at least one gate is required")
    _require(all(value in ranks for value in observed), "unknown gate value")
    return max(observed, key=ranks.__getitem__)


def gate_vector(model_keys: Sequence[str], interface_level: str) -> dict[str, str]:
    """Propagate the worst registered contribution independently on each axis."""

    keys = tuple(model_keys)
    _require(keys in ALL_SUBSETS, "gate vector requested for an unregistered model subset")
    _require(interface_level in INTERFACE_GATE_CONTRIBUTIONS, "unknown interface level")
    values: dict[str, list[str]] = {axis: ["NOT_ASSESSED"] for axis in GATE_AXES}
    for model_key in keys:
        for axis, gate in MODEL_GATE_CONTRIBUTIONS[model_key].items():
            values[axis].append(gate)
    values["interface_disclosure"].append(INTERFACE_GATE_CONTRIBUTIONS[interface_level])
    return {axis: worst_gate(axis_values) for axis, axis_values in values.items()}


def _validate_metric_value(name: str, value: Any, modality: str) -> float:
    _require(_is_number(value), f"{modality} metric {name} must be finite numeric aggregate")
    number = float(value)
    if modality == "llm":
        if name in {
            "before_balanced_accuracy",
            "after_balanced_accuracy",
            "before_roc_auc",
            "after_roc_auc",
        }:
            _require(0.0 <= number <= 1.0, f"LLM metric {name} is outside [0,1]")
        else:
            _require(-1.0 <= number <= 1.0, f"LLM difference metric {name} is outside [-1,1]")
    else:
        if name == "clean_mean_cross_entropy":
            _require(number >= 0.0, "vision cross entropy may not be negative")
        else:
            _require(0.0 <= number <= 1.0, f"vision metric {name} is outside [0,1]")
    return number


def validate_child_export(export: Mapping[str, Any], modality: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy one child's bounded aggregate-only export."""

    _require(modality in {"llm", "vision"}, "unknown child modality")
    _exact_keys(export, CHILD_EXPORT_KEYS, f"{modality} suite_export")
    _require(export["schema_version"] == "1.0", f"{modality} suite_export schema differs")
    _require(export["modality"] == modality, f"{modality} suite_export modality differs")
    _require(export["protected_unit_population"] == PROTECTED_UNIT_POPULATIONS[modality], f"{modality} protected-unit population differs")
    expected_models = LLM_MODEL_KEYS if modality == "llm" else VISION_MODEL_KEYS
    expected_subsets = LLM_SUBSETS if modality == "llm" else VISION_SUBSETS
    _require(tuple(export["model_keys"]) == expected_models, f"{modality} model registry differs")
    _require(tuple(export["seeds"]) == SEEDS, f"{modality} seed registry differs")
    _require(tuple(export["scales"]) == SCALES[modality], f"{modality} real scales differ")
    _require(export["authority"] == AUTHORITY, f"{modality} export must remain non-authorizing")

    resources = export["resources"]
    _require(isinstance(resources, list) and len(resources) == len(expected_models), f"{modality} resources must have one vector component per model")
    copied_resources: list[dict[str, Any]] = []
    resource_models: list[str] = []
    execution = config["execution"]
    for item in resources:
        _require(isinstance(item, Mapping), f"{modality} resource component must be an object")
        _exact_keys(item, RESOURCE_KEYS, f"{modality} resource component")
        model_key = item["model_key"]
        _require(model_key in expected_models and model_key not in resource_models, f"{modality} resource model is unknown or duplicated")
        resource_models.append(model_key)
        copied = {"model_key": model_key}
        for key in RESOURCE_KEYS - {"model_key"}:
            if key == "wall_clock_seconds":
                _require(_is_number(item[key]) and item[key] >= 0, f"{modality} resource {key} must be finite and nonnegative")
                _require(item[key] <= execution["max_wall_clock_seconds"], f"{modality} child exceeds wall-clock ceiling")
                copied[key] = float(item[key])
            else:
                _require(isinstance(item[key], int) and not isinstance(item[key], bool) and item[key] >= 0, f"{modality} resource {key} must be a nonnegative integer byte count")
                _require(item[key] <= execution[
                    "max_aggregate_artifact_bytes" if key == "artifact_bytes" else (
                        "max_gpu_reserved_bytes" if key == "peak_gpu_reserved_bytes" else "max_host_rss_bytes"
                    )
                ], f"{modality} child exceeds {key} ceiling")
                copied[key] = int(item[key])
        copied_resources.append(copied)
    _require(tuple(resource_models) == expected_models, f"{modality} resources must follow canonical model order")

    metric_names = LLM_METRICS if modality == "llm" else VISION_METRICS
    rows = export["subset_scalars"]
    expected_cells = {
        (subset, scale, seed)
        for subset in expected_subsets
        for scale in SCALES[modality]
        for seed in SEEDS
    }
    _require(isinstance(rows, list) and len(rows) == len(expected_cells), f"{modality} scalar cell count is incomplete")
    observed_cells: set[tuple[tuple[str, ...], int, int]] = set()
    copied_rows: list[dict[str, Any]] = []
    for row in rows:
        _require(isinstance(row, Mapping), f"{modality} scalar row must be an object")
        _exact_keys(row, SCALAR_ROW_KEYS, f"{modality} scalar row")
        subset = tuple(row["model_keys"])
        scale = row["scale"]
        seed = row["seed"]
        cell = (subset, scale, seed)
        _require(cell in expected_cells and cell not in observed_cells, f"{modality} scalar cell is unknown or duplicated")
        observed_cells.add(cell)
        metrics = row["metrics"]
        _require(isinstance(metrics, Mapping), f"{modality} scalar metrics must be an object")
        _exact_keys(metrics, set(metric_names), f"{modality} scalar metrics")
        copied_rows.append(
            {
                "model_keys": list(subset),
                "scale": scale,
                "seed": seed,
                "metrics": {
                    name: _validate_metric_value(name, metrics[name], modality)
                    for name in metric_names
                },
            }
        )
    _require(observed_cells == expected_cells, f"{modality} scalar matrix is incomplete")
    copied_rows.sort(
        key=lambda row: (
            len(row["model_keys"]),
            tuple(MODEL_KEYS.index(key) for key in row["model_keys"]),
            row["scale"],
            SEEDS.index(row["seed"]),
        )
    )
    return {
        "schema_version": "1.0",
        "modality": modality,
        "protected_unit_population": PROTECTED_UNIT_POPULATIONS[modality],
        "model_keys": list(expected_models),
        "seeds": list(SEEDS),
        "scales": list(SCALES[modality]),
        "authority": dict(AUTHORITY),
        "resources": copied_resources,
        "subset_scalars": copied_rows,
    }


def _safe_child_report_path(output_dir: Path, basename: str) -> Path:
    _require(SAFE_BASENAME.fullmatch(basename) is not None, "child report registration is not a safe basename")
    candidate = output_dir / basename
    _require(candidate.parent.resolve() == output_dir.resolve(), "child report registration escapes output directory")
    _require(candidate.is_file() and not candidate.is_symlink(), "child report must be a regular non-symlink file")
    return candidate


def directory_regular_file_bytes(root: Path) -> int:
    """Measure a tree while rejecting symlinks and special filesystem nodes."""

    _require(root.is_dir() and not root.is_symlink(), "child output must be a regular directory")
    total = 0
    for entry in root.rglob("*"):
        _require(not entry.is_symlink(), "child output may not contain symlinks")
        mode = entry.stat().st_mode
        _require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "child output may contain only directories and regular files")
        if stat.S_ISREG(mode):
            total += entry.stat().st_size
            _require(total <= MAX_BYTES, "child output tree exceeds the 20 GiB hard ceiling")
    return total


def verify_child_output(
    output_dir: Path,
    modality: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify one final manifest, its report registration, and suite export."""

    binding = config["source_bindings"]["children"][modality]
    total_bytes = directory_regular_file_bytes(output_dir)
    _require(total_bytes <= config["execution"]["max_aggregate_artifact_bytes"], f"{modality} output exceeds artifact ceiling")
    manifest_path = _safe_child_report_path(output_dir, binding["completion_manifest_basename"])
    manifest = load_json_object(manifest_path, max_bytes=1024 * 1024)
    _exact_keys(manifest, {"schema_version", "status", "experiment_id", "report", "authority"}, f"{modality} completion manifest")
    _require(manifest["schema_version"] == "1.0" and manifest["status"] == "complete", f"{modality} completion status is not final")
    _require(manifest["experiment_id"] == binding["experiment_id"], f"{modality} completion experiment differs")
    _require(manifest["authority"] == AUTHORITY, f"{modality} completion authority differs")
    registration = manifest["report"]
    _require(isinstance(registration, Mapping), f"{modality} report registration must be an object")
    _exact_keys(registration, {"path", "sha256", "bytes"}, f"{modality} report registration")
    _require(registration["path"] == binding["report_basename"], f"{modality} report basename differs")
    _require(isinstance(registration["sha256"], str) and HEX64.fullmatch(registration["sha256"]) is not None, f"{modality} report digest is invalid")
    report_path = _safe_child_report_path(output_dir, registration["path"])
    _require(isinstance(registration["bytes"], int) and not isinstance(registration["bytes"], bool) and registration["bytes"] > 0, f"{modality} report byte count is invalid")
    _require(report_path.stat().st_size == registration["bytes"], f"{modality} report byte count differs")
    _require(file_sha256(report_path) == registration["sha256"], f"{modality} report digest mismatch")
    _require(manifest_path.stat().st_mtime_ns >= report_path.stat().st_mtime_ns, f"{modality} completion manifest was not written last")
    report = load_json_object(report_path)
    _require("suite_export" in report and isinstance(report["suite_export"], Mapping), f"{modality} report lacks the registered suite_export")
    return validate_child_export(report["suite_export"], modality, config)


def _assert_disjoint_directory_trees(paths: Sequence[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            _require(left != right and left not in right.parents and right not in left.parents, "suite output, work, and cache trees must be disjoint")


def _ensure_fresh_target(path: Path) -> None:
    _require(not path.exists(), "suite requires a fresh output/work directory")
    _require(path.parent.exists() and path.parent.is_dir(), "suite target parent directory must already exist")


def _run_child(
    modality: str,
    config: Mapping[str, Any],
    output_dir: Path,
    cache_dir: Path,
    *,
    offline: bool,
    deadline: float,
) -> None:
    binding = config["source_bindings"]["children"][modality]
    runner = _relative_registered_file(ROOT, binding["runner_path"])
    child_config = _relative_registered_file(ROOT, binding["config_path"])
    command = [
        sys.executable,
        str(runner),
        "--config",
        str(child_config),
        "--output-dir",
        str(output_dir),
        "--cache-dir",
        str(cache_dir),
    ]
    if offline:
        command.append("--offline")
    remaining = deadline - time.monotonic()
    _require(remaining > 0, "suite wall-clock deadline expired before child launch")
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = str(config["execution"]["visible_gpu_index"])
    print(f"composition suite: starting {modality} child", flush=True)
    try:
        completed = subprocess.run(
            command,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
            env=environment,
            timeout=remaining,
        )
    except subprocess.TimeoutExpired as exc:
        raise SuiteValidationError(f"{modality} child exceeded the suite wall-clock ceiling") from exc
    _require(completed.returncode == 0, f"{modality} child failed closed with exit status {completed.returncode}")
    print(f"composition suite: completed {modality} child", flush=True)


def orchestrate_children(
    config: Mapping[str, Any],
    work_dir: Path,
    cache_dirs: Mapping[str, Path],
    *,
    offline: bool,
    started: float,
) -> dict[str, dict[str, Any]]:
    """Execute the two registered child CLIs serially on one visible GPU."""

    _ensure_fresh_target(work_dir)
    work_dir.mkdir(mode=0o700)
    _require(set(cache_dirs) == {"llm", "vision"}, "both modality cache roots are required")
    for cache_dir in cache_dirs.values():
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = started + config["execution"]["max_wall_clock_seconds"]
    exports: dict[str, dict[str, Any]] = {}
    cumulative_bytes = 0
    for modality in config["execution"]["child_order"]:
        child_output = work_dir / modality
        child_cache = cache_dirs[modality]
        _run_child(
            modality,
            config,
            child_output,
            child_cache,
            offline=offline,
            deadline=deadline,
        )
        exports[modality] = verify_child_output(child_output, modality, config)
        cumulative_bytes += directory_regular_file_bytes(child_output)
        _require(cumulative_bytes <= config["execution"]["max_aggregate_artifact_bytes"], "combined child artifacts exceed the 20 GiB ceiling")
    _require(time.monotonic() <= deadline, "suite wall-clock ceiling expired")
    return exports


def _resource_map(exports: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        component["model_key"]: component
        for modality in ("llm", "vision")
        for component in exports[modality]["resources"]
    }


def _subset_kind(subset: tuple[str, ...]) -> str:
    if subset in LLM_SUBSETS:
        return "llm_shared_population"
    if subset in VISION_SUBSETS:
        return "vision_shared_population"
    return "cross_modal_vector_only"


def _interface_summaries(subset: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "interface_level": level,
            "gate_vector": gate_vector(subset, level),
            "absorbing_gates": sorted(
                set(gate_vector(subset, level).values()) & ABSORBING_GATES
            ),
            "authority": dict(AUTHORITY),
        }
        for level in EXPECTED_INTERFACE_MASKS
    ]


def assert_safe_aggregate(value: Any, *, key: str | None = None) -> None:
    """Reject identifier/path/per-example channels in the public aggregate."""

    if key is not None:
        _require(key not in FORBIDDEN_AGGREGATE_KEYS, f"unsafe aggregate key is forbidden: {key}")
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            _require(isinstance(child_key, str), "aggregate object keys must be strings")
            assert_safe_aggregate(child_value, key=child_key)
    elif isinstance(value, list):
        _require(len(value) <= 20_000, "aggregate list exceeds safety bound")
        for item in value:
            assert_safe_aggregate(item)
    elif isinstance(value, str):
        _require(len(value) <= 512, "aggregate string exceeds safety bound")
        _require(not value.startswith(("/", "\\")), "absolute machine paths are forbidden in aggregate output")
        _require("../" not in value and "..\\" not in value, "traversing paths are forbidden in aggregate output")
    elif value is None or isinstance(value, (bool, int)):
        return
    elif isinstance(value, float):
        _require(math.isfinite(value), "aggregate floats must be finite")
    else:
        raise SuiteValidationError("aggregate contains an unsupported value type")


def build_suite_report(
    config: Mapping[str, Any],
    exports: Mapping[str, Mapping[str, Any]],
    *,
    observed_wall_clock_seconds: float,
) -> dict[str, Any]:
    """Build the safe aggregate without cross-population scalar composition."""

    _require(set(exports) == {"llm", "vision"}, "both child exports are required")
    validated_exports = {
        modality: validate_child_export(exports[modality], modality, config)
        for modality in ("llm", "vision")
    }
    resources = _resource_map(validated_exports)
    total_child_wall = sum(component["wall_clock_seconds"] for component in resources.values())
    total_artifacts = sum(component["artifact_bytes"] for component in resources.values())
    _require(observed_wall_clock_seconds <= config["execution"]["max_wall_clock_seconds"], "observed suite wall clock exceeds 12 hours")
    _require(total_child_wall <= config["execution"]["max_wall_clock_seconds"], "registered child wall clock exceeds 12 hours")
    _require(total_artifacts <= config["execution"]["max_aggregate_artifact_bytes"], "registered child artifact bytes exceed 20 GiB")
    _require(max(component["peak_gpu_reserved_bytes"] for component in resources.values()) <= config["execution"]["max_gpu_reserved_bytes"], "registered GPU memory exceeds 20 GiB")
    _require(max(component["peak_host_rss_bytes"] for component in resources.values()) <= config["execution"]["max_host_rss_bytes"], "registered host RSS exceeds 20 GiB")

    subset_summaries: list[dict[str, Any]] = []
    for subset in ALL_SUBSETS:
        kind = _subset_kind(subset)
        modalities = []
        if any(key in LLM_MODEL_KEYS for key in subset):
            modalities.append(PROTECTED_UNIT_POPULATIONS["llm"])
        if any(key in VISION_MODEL_KEYS for key in subset):
            modalities.append(PROTECTED_UNIT_POPULATIONS["vision"])
        same_population = kind != "cross_modal_vector_only"
        subset_summaries.append(
            {
                "model_keys": list(subset),
                "composition_kind": kind,
                "protected_unit_population_vector": modalities,
                "empirical_scalar_composition": {
                    "permitted": same_population,
                    "cell_count": (
                        len(SCALES["llm"]) * len(SEEDS)
                        if subset in LLM_SUBSETS
                        else len(SCALES["vision"]) * len(SEEDS)
                        if subset in VISION_SUBSETS
                        else 0
                    ),
                    "cross_population_scalar": None,
                },
                "resource_vector": [dict(resources[key]) for key in subset],
                "interface_gate_vectors": _interface_summaries(subset),
                "authority": dict(AUTHORITY),
            }
        )

    safe_scalar_results = {
        modality: [
            {**row, "authority": dict(AUTHORITY)}
            for row in validated_exports[modality]["subset_scalars"]
        ]
        for modality in ("llm", "vision")
    }
    bindings = config["source_bindings"]
    source_digest_vector = []
    source_digest_vector.extend(
        [
            {"component": "suite_configuration_canonical", "sha256": canonical_sha256(config)},
            {"component": "suite_runner", "sha256": file_sha256(Path(__file__).resolve())},
        ]
    )
    for modality in ("llm", "vision"):
        base = bindings["base_protocols"][modality]
        child = bindings["children"][modality]
        source_digest_vector.extend(
            [
                {"component": f"{modality}_base_config", "sha256": base["config_sha256"]},
                {"component": f"{modality}_base_runner", "sha256": base["runner_sha256"]},
                {"component": f"{modality}_base_hook", "sha256": base["hook_sha256"]},
                {"component": f"{modality}_composition_config", "sha256": child["config_sha256"]},
                {"component": f"{modality}_composition_runner", "sha256": child["runner_sha256"]},
            ]
        )

    report = {
        "schema_version": "1.0",
        "protocol_name": "five-model-composition-scaling-v1",
        "status": "complete",
        "authority": dict(AUTHORITY),
        "composition_boundary": {
            "scalar_rule": "permitted_only_within_one_registered_shared_protected_unit_population",
            "cross_modal_rule": "resource_and_gate_vectors_only_no_empirical_scalar",
            "gate_propagation": "worst_per_axis_with_absorbing_blocks",
            "gate_averaging_allowed": False,
            "exact_roster_result": "BLOCKED_AND_REDESIGN_REQUIRED",
        },
        "registered_matrix": {
            "model_keys": list(MODEL_KEYS),
            "seeds": list(SEEDS),
            "real_scales": {key: list(value) for key, value in SCALES.items()},
            "all_subset_count": len(ALL_SUBSETS),
            "llm_same_population_subset_count": len(LLM_SUBSETS),
            "vision_same_population_subset_count": len(VISION_SUBSETS),
            "cross_modal_subset_count": len(CROSS_MODAL_SUBSETS),
            "scalar_cell_count": sum(len(export["subset_scalars"]) for export in validated_exports.values()),
        },
        "source_digest_vector": source_digest_vector,
        "resource_ceiling": {
            "serial_one_gpu": True,
            "max_wall_clock_seconds": config["execution"]["max_wall_clock_seconds"],
            "max_gpu_reserved_bytes": config["execution"]["max_gpu_reserved_bytes"],
            "max_host_rss_bytes": config["execution"]["max_host_rss_bytes"],
            "max_aggregate_artifact_bytes": config["execution"]["max_aggregate_artifact_bytes"],
            "observed_suite_wall_clock_seconds": float(observed_wall_clock_seconds),
            "registered_child_wall_clock_seconds": float(total_child_wall),
            "registered_artifact_bytes": int(total_artifacts),
            "resource_vector": [dict(resources[key]) for key in MODEL_KEYS],
        },
        "interface_masks": [
            {
                "interface_level": profile["level"],
                "mask": dict(profile["mask"]),
                "authority": dict(AUTHORITY),
            }
            for profile in config["interfaces"]["profiles"]
        ],
        "same_population_scalar_results": {
            "llm": safe_scalar_results["llm"],
            "vision": safe_scalar_results["vision"],
        },
        "subset_summaries": subset_summaries,
        "limitations": [
            "All empirical screens are descriptive and cannot clear or block a release.",
            "Mixed-modal protected-unit populations have no empirical scalar composition.",
            "The Meta OPT commercial gate and exact-roster redesign gate are absorbing.",
            "Pythia deployment and both real-data rights boundaries require manual review.",
            "A signed release contract and approved recipient-realizable recollection are required.",
        ],
    }
    assert_safe_aggregate(report)
    return report


def _metric_min_median_max(rows: Sequence[Mapping[str, Any]], metric: str) -> tuple[float, float, float]:
    values = sorted(float(row["metrics"][metric]) for row in rows)
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2.0
    return values[0], median, values[-1]


def build_markdown_report(report: Mapping[str, Any]) -> str:
    """Render a compact human-auditable view of the complete JSON matrix."""

    lines = [
        "# Five-model composition-scaling suite",
        "",
        "Status: **complete, experimental, non-authorizing**.",
        "",
        "The JSON companion contains all 31 subset summaries, all six interface masks, "
        "and all 150 aggregate scalar cells. Scalar empirical composition is restricted "
        "to one shared protected-unit population; the 21 mixed LLM/vision subsets carry "
        "only resource and gate vectors.",
        "",
        "## Registered matrix",
        "",
        "| Dimension | Registration |",
        "| --- | --- |",
        "| Models | DistilGPT2, Meta OPT-125M, Pythia-160M, AlexNet, DenseNet121 |",
        "| Seeds | 3407, 499625614, 4288481424, 2669540432, 2937338177 |",
        "| LLM real scales | 2,048; 4,096; 8,192 records |",
        "| Vision real scales | 5,400; 10,800; 21,600 images |",
        "| Subsets | 31 total; 7 LLM; 3 vision; 21 mixed-modal vector-only |",
        "| Scalar cells | 105 LLM + 45 vision = 150 |",
        "",
        "## Resource ceiling",
        "",
        "| Model | Wall seconds | Peak GPU bytes | Peak host RSS bytes | Artifact bytes |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for component in report["resource_ceiling"]["resource_vector"]:
        lines.append(
            f"| {component['model_key']} | {component['wall_clock_seconds']:.3f} | "
            f"{component['peak_gpu_reserved_bytes']} | {component['peak_host_rss_bytes']} | "
            f"{component['artifact_bytes']} |"
        )

    lines.extend(
        [
            "",
            "Hard ceilings are 43,200 seconds and 21,474,836,480 bytes (20 GiB) for "
            "each registered memory/storage bound. Children execute serially with one visible GPU.",
            "",
            "## Aggregate metric ranges",
            "",
            "| Modality | Metric | Minimum | Median | Maximum |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for modality, rows in report["same_population_scalar_results"].items():
        for metric in rows[0]["metrics"]:
            low, median, high = _metric_min_median_max(rows, metric)
            lines.append(f"| {modality} | {metric} | {low:.6f} | {median:.6f} | {high:.6f} |")

    lines.extend(
        [
            "",
            "## Release-interface policy",
            "",
            "| Interface | Added exposure | Interface-disclosure gate |",
            "| --- | --- | --- |",
            "| R0 | Prediction payload only | MANUAL_REVIEW_REQUIRED |",
            "| R1 | Token/class scores | MANUAL_REVIEW_REQUIRED |",
            "| R2 | Exact candidate source and preprocessing metadata | MANUAL_REVIEW_REQUIRED |",
            "| R3 | Arbitrary-candidate scoring and per-example loss | RESTRICTED_AUDITOR_ONLY |",
            "| R4 | White-box internals plus exact candidate metadata | RESTRICTED_AUDITOR_ONLY |",
            "| R5 | Exact protected training roster | BLOCKED_AND_REDESIGN_REQUIRED |",
            "",
            "R0-R5 are explicit, non-ordinal masks. They are not cumulative, and no "
            "risk monotonicity is inferred between R2 and R3.",
            "",
            "Gates propagate independently by axis using the worst registered value; "
            "they are never averaged. Meta OPT-125M makes the commercial model-license "
            "axis `BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY`. Pythia and real-data rights "
            "remain manual gates. R5 is a logical direct disclosure and is absorbing.",
            "",
            "## Authority boundary",
            "",
            "Every screen has `can_clear=false`, `can_block=false`, "
            "`assessment_input_emitted=false`, `attack_battery_eligible=false`, and "
            "`authorization_eligible=false`. Approved "
            "recollection under a signed release contract is required before any release decision.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_new(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def publish_suite_report(output_dir: Path, config: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    """Publish JSON/Markdown and write RUN_COMPLETE as the final filesystem event."""

    assert_safe_aggregate(report)
    _ensure_fresh_target(output_dir)
    output_dir.mkdir(mode=0o700)
    output = config["output"]
    json_bytes = json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    markdown_bytes = build_markdown_report(report).encode("utf-8")
    json_path = output_dir / output["aggregate_json"]
    markdown_path = output_dir / output["aggregate_markdown"]
    _atomic_write_new(json_path, json_bytes)
    _atomic_write_new(markdown_path, markdown_bytes)
    completion = {
        "schema_version": "1.0",
        "status": "complete",
        "protocol_name": "five-model-composition-scaling-v1",
        "authority": dict(AUTHORITY),
        "artifacts": {
            "aggregate_json": {
                "bytes": len(json_bytes),
                "sha256": hashlib.sha256(json_bytes).hexdigest(),
            },
            "aggregate_markdown": {
                "bytes": len(markdown_bytes),
                "sha256": hashlib.sha256(markdown_bytes).hexdigest(),
            },
        },
    }
    assert_safe_aggregate(completion)
    completion_bytes = json.dumps(completion, allow_nan=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write_new(output_dir / output["completion_manifest"], completion_bytes)
    directory_fd = os.open(output_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return completion


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, required=True, help="fresh directory for safe suite aggregates only")
    parser.add_argument(
        "--llm-cache-dir",
        type=Path,
        default=ROOT / "output" / "llm-training-hook" / "cache",
        help="existing verified LLM cache (passed directly to the LLM child)",
    )
    parser.add_argument(
        "--vision-cache-dir",
        type=Path,
        default=ROOT / "output" / "cache" / "vision-training-hook",
        help="existing verified vision cache (passed directly to the vision child)",
    )
    parser.add_argument("--execute-children", action="store_true", help="run the two registered child CLIs serially")
    parser.add_argument("--work-dir", type=Path, help="fresh sibling tree for retained child artifacts when executing")
    parser.add_argument("--llm-output-dir", type=Path, help="existing completed LLM child output")
    parser.add_argument("--vision-output-dir", type=Path, help="existing completed vision child output")
    parser.add_argument("--offline", action="store_true", help="pass --offline to both child CLIs")
    parser.add_argument("--validate-only", action="store_true", help="validate source/config bindings without reading or running children")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_arguments(argv)
    started = time.monotonic()
    config = load_and_validate_config(args.config.resolve())
    if args.validate_only:
        _require(not args.execute_children and args.llm_output_dir is None and args.vision_output_dir is None, "validate-only cannot consume or execute children")
        print("composition suite configuration and source bindings validated")
        return 0

    output_dir = args.output_dir.resolve()
    cache_dirs = {
        "llm": args.llm_cache_dir.resolve(),
        "vision": args.vision_cache_dir.resolve(),
    }
    _ensure_fresh_target(output_dir)
    if args.execute_children:
        _require(args.llm_output_dir is None and args.vision_output_dir is None, "execute mode cannot also consume existing child outputs")
        _require(args.work_dir is not None, "execute mode requires an explicit fresh --work-dir")
        work_dir = args.work_dir.resolve()
        _assert_disjoint_directory_trees((output_dir, work_dir, *cache_dirs.values()))
        exports = orchestrate_children(
            config,
            work_dir,
            cache_dirs,
            offline=args.offline,
            started=started,
        )
    else:
        _require(args.work_dir is None, "--work-dir is only valid with --execute-children")
        _require(args.llm_output_dir is not None and args.vision_output_dir is not None, "aggregation mode requires both completed child output directories")
        llm_output = args.llm_output_dir.resolve()
        vision_output = args.vision_output_dir.resolve()
        _assert_disjoint_directory_trees((output_dir, *cache_dirs.values(), llm_output, vision_output))
        exports = {
            "llm": verify_child_output(llm_output, "llm", config),
            "vision": verify_child_output(vision_output, "vision", config),
        }

    elapsed = time.monotonic() - started
    report = build_suite_report(config, exports, observed_wall_clock_seconds=elapsed)
    publish_suite_report(output_dir, config, report)
    print("composition scaling suite completed with no release authorization")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SuiteValidationError, FileExistsError, OSError) as exc:
        print(f"composition suite failed closed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
