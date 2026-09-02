#!/usr/bin/env python3
"""Run a bounded, non-authorizing causal-LM training-hook experiment.

The worker loads an immutable Parquet object directly and never executes remote
dataset code.  Reports and telemetry persist no prompt/response text, token
IDs, logits, activations, or gradients.  Offline replay does retain the full
verified source Parquet in a restricted cache, including upstream columns that
the in-memory Arrow projection excludes.  A successful run demonstrates only
that the bounded integration path and its hooks executed; it cannot authorize
a model release.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import types
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DATASET_URL = (
    "https://huggingface.co/datasets/{dataset_id}/resolve/{revision}/{file}"
)
CATALOG_URL = "https://raw.githubusercontent.com/mlabonne/llm-datasets/{revision}/README.md"
MODEL_URL = "https://huggingface.co/{model_id}/resolve/{revision}/{file}"
MAX_CONFIG_BYTES = 128 * 1024
MAX_HOOK_SOURCE_BYTES = 128 * 1024
EXPECTED_MODEL_ARTIFACT_REGISTRY_SHA256 = {
    "distilgpt2": "79f441c2fc8c8fd42842857273fe78c0c21daa7dccc4e75214e3729a02d00ab9",
    "meta-opt-125m": "2112ed3f2bea1c05e94faf8e869f655ad553eafaacdcb73c2ce6474e674e8772",
    "pythia-160m": "46ec2e017c71824798d3ed617ca4f46541e64924105f58e600f54dcefd99ed05",
}
EXPECTED_CONFIG_SECTION_SHA256 = {
    "catalog": "4116430810ba080e8dc66a2f93f31c50050dc09bb8a559f7c727750b1ece6cbb",
    "dataset": "25752de5624dac576556e3547ed9541fcfef35445a03bbc6793fb80ee48d2a6b",
    "models": "ec2998e4dc24d4ba255dda57ece92b9d551a2666750177451cc2b0882bc0c20e",
    "model_matrix": "a57f0c21ae62e7f352fbff80051afda389e70dcb65bf5966b568bac75ba45628",
    "training": "52240b07ea84664f3811171196eef4a160d86a09f4f9b38926d0b1b193ed0b9a",
    "hooks": "d26a8de860f87e5158645e58ee8f01e2a3b86c2a3f9d64a23e5352149b1746ec",
    "context_risk_ladder": "11e1cb208fa35855fc666437c1fb3d1de13ab5abef5ca852ae2f8c64e6c9366e",
    "output": "6ccc662df6d2f30ecf02796edc39aaaf92d5a6cd902747b87a12b7f96eb1bdfe",
}


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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate the experiment's security and reproducibility invariants."""

    _require(raw.get("schema_version") == "1.1", "schema_version must be 1.1")
    _require(
        raw.get("experiment_id") == "llm-training-hook-wildchat-three-model-v1",
        "experiment_id differs from the frozen v1 profile",
    )
    _require(raw.get("experimental_only") is True, "experimental_only must be true")
    _require(raw.get("authorization_eligible") is False, "authorization_eligible must be false")
    _require(raw.get("decision") == "no_release_authorization", "decision must be no_release_authorization")

    catalog = raw.get("catalog", {})
    dataset = raw.get("dataset", {})
    models = raw.get("models", [])
    training = raw.get("training", {})
    hooks = raw.get("hooks", {})
    context_risk = raw.get("context_risk_ladder", {})
    output = raw.get("output", {})
    rows = dataset.get("rows", {})

    _require(HEX40.fullmatch(str(catalog.get("revision", ""))) is not None, "catalog revision must be an immutable 40-hex commit")
    _require(HEX64.fullmatch(str(catalog.get("readme_sha256", ""))) is not None, "catalog README digest must be 64-hex")
    _require(int(catalog.get("readme_bytes", 0)) > 0, "catalog README size must be positive")
    _require(catalog.get("dataset_entry_verified") is True, "catalog dataset entry verification must be required")
    _require(
        catalog.get("repository") == "https://github.com/mlabonne/llm-datasets"
        and catalog.get("revision") == "67c52949f3153e311f0183db0700cca6d611524b"
        and catalog.get("readme_sha256") == "64047256aa9e8a888707cce2611b9d6ab58b50c3a6498ed5abd853de2c9546a1",
        "catalog identity differs from the frozen reproduction",
    )
    _require(catalog.get("readme_bytes") == 24367, "catalog byte size differs from the frozen reproduction")
    _require(HEX40.fullmatch(str(dataset.get("revision", ""))) is not None, "dataset revision must be an immutable 40-hex commit")
    _require(HEX64.fullmatch(str(dataset.get("sha256", ""))) is not None, "dataset digest must be 64-hex")
    _require(int(dataset.get("bytes", 0)) > 0, "dataset byte size must be positive")
    _require(dataset.get("loader") == "direct_parquet", "dataset loader must be direct_parquet")
    _require(dataset.get("trust_remote_code") is False, "remote dataset code must remain disabled")
    _require(str(dataset.get("file", "")).endswith(".parquet"), "dataset file must be Parquet")
    _require(dataset.get("record_adapter") == "wildchat_first_user_assistant_turn_v1", "unsupported dataset record adapter")
    _require(
        dataset.get("id") == "allenai/WildChat-4.8M"
        and dataset.get("revision") == "c827c6df8fcf008219ffaffa4d1dd77491099367"
        and dataset.get("file") == "data/train-00000-of-00086.parquet"
        and dataset.get("url") == DATASET_URL.format(
            dataset_id="allenai/WildChat-4.8M",
            revision="c827c6df8fcf008219ffaffa4d1dd77491099367",
            file="data/train-00000-of-00086.parquet",
        )
        and dataset.get("sha256") == "6df660dca78dd92b865bef09b928992ceb6c913b4f06082315876a5997ad2eaa"
        and dataset.get("bytes") == 125527585
        and dataset.get("license") == "ODC-By-1.0",
        "dataset identity/license differs from the frozen WildChat reproduction",
    )
    expected_governance_sources = {
        "dataset_card": {
            "file": "README.md",
            "url": "https://huggingface.co/datasets/allenai/WildChat-4.8M/resolve/c827c6df8fcf008219ffaffa4d1dd77491099367/README.md",
            "bytes": 14962,
            "sha256": "946c2526ed254c35380b9366b3ca1c1bded65695c21c388194e1b643acac70c6",
        },
        "license_file": {
            "file": "LICENSE.md",
            "url": "https://huggingface.co/datasets/allenai/WildChat-4.8M/resolve/c827c6df8fcf008219ffaffa4d1dd77491099367/LICENSE.md",
            "bytes": 19947,
            "sha256": "a7c7f6bdb20d261b8726c7594afb5832b36926e0cabfa116c41f58625bbc776c",
        },
        "dataset_card_license_declaration": "odc-by",
        "content_rights_cleared": False,
    }
    _require(
        dataset.get("governance_sources") == expected_governance_sources,
        "official dataset governance sources differ from the frozen reproduction",
    )
    _require(
        dataset.get("cache_policy") == {
            "retain_raw_source_for_offline_replay": True,
            "file_mode": "0600",
            "directory_mode": "0700",
            "include_in_recipient_package": False,
            "operator_retention_and_deletion_policy_required": True,
        },
        "raw dataset cache policy mismatch",
    )
    _require(dataset.get("eligibility", {}).get("language") == "English", "the registered WildChat cohort must be English")
    _require(dataset.get("eligibility", {}).get("require_row_toxic_false") is True, "toxic rows must be excluded")
    _require(dataset.get("eligibility", {}).get("require_row_redacted_false") is True, "redacted rows must be excluded")
    expected_projection = [
        "conversation_hash",
        "conversation.list.element.content",
        "conversation.list.element.role",
        "conversation.list.element.turn_identifier",
        "turn",
        "language",
        "model",
        "toxic",
        "redacted",
    ]
    expected_exclusions = [
        "timestamp",
        "openai_moderation",
        "detoxify_moderation",
        "state",
        "country",
        "hashed_ip",
        "header",
        "conversation.list.element.created",
        "conversation.list.element.header",
        "conversation.list.element.hashed_ip",
        "conversation.list.element.country",
        "conversation.list.element.state",
        "conversation.list.element.openai_id",
        "conversation.list.element.temperature",
        "conversation.list.element.timestamp",
        "conversation.list.element.token_counter",
        "conversation.list.element.top_p",
        "conversation.list.element.system_fingerprint",
        "conversation.list.element.usage",
    ]
    expected_eligibility = {
        "first_pair_roles": ["user", "assistant"],
        "require_nonempty_content": True,
        "require_first_pair_turn_identifiers": True,
        "language": "English",
        "require_row_toxic_false": True,
        "require_row_redacted_false": True,
        "deduplicate_exact_first_pair": True,
    }
    _require(dataset.get("projected_columns") == expected_projection, "dataset leaf projection registry mismatch")
    _require(dataset.get("excluded_sensitive_columns") == expected_exclusions, "sensitive-column exclusion registry mismatch")
    _require(dataset.get("eligibility") == expected_eligibility, "dataset eligibility registry mismatch")
    _require(
        dataset.get("source_scale") == {
            "dataset_conversations": 3199860,
            "dataset_size_category": "1M<n<10M",
            "dataset_card_uncompressed_bytes": 42645714270,
            "registered_shards": 86,
            "selected_shard_rows": 37208,
            "selected_shard_eligible_before_deduplication": 16135,
            "selected_shard_eligible_after_deduplication": 15730,
        },
        "dataset source-scale claims differ from the frozen reproduction",
    )
    _require(
        rows == {"total": 9216, "train": 8192, "holdout": 1024}
        and dataset.get("seed") == 3407,
        "dataset selection profile differs from the frozen reproduction",
    )
    _require(isinstance(models, list) and len(models) == 3, "exactly three registered models are required")
    model_keys: list[str] = []
    for model in models:
        _require(isinstance(model, dict), "each model registration must be an object")
        _require(isinstance(model.get("key"), str) and bool(model["key"]), "model key must be non-empty")
        _require(isinstance(model.get("id"), str) and "/" in model["id"], "model id must be a repository identifier")
        _require(HEX40.fullmatch(str(model.get("revision", ""))) is not None, "model revision must be an immutable 40-hex commit")
        _require(isinstance(model.get("hook_modules"), list) and len(model["hook_modules"]) >= 2, "each model requires at least two hook modules")
        _require(len(set(model["hook_modules"])) == len(model["hook_modules"]), "model hook modules must be unique")
        _require(isinstance(model.get("license"), str) and bool(model["license"]), "model license must be declared")
        _require(model.get("trust_remote_code") is False, "model remote code must remain disabled")
        _require(isinstance(model.get("use_safetensors"), bool), "model serialization choice must be explicit")
        if model["use_safetensors"] is False:
            _require(model.get("weights_only") is True, "legacy PyTorch weights must use weights_only=True")
        artifacts = model.get("artifacts")
        _require(isinstance(artifacts, list) and bool(artifacts), "each model requires a bounded artifact registry")
        artifact_files = []
        for artifact in artifacts:
            _require(isinstance(artifact, dict), "model artifact registration must be an object")
            artifact_file = artifact.get("file")
            _require(
                isinstance(artifact_file, str)
                and bool(artifact_file)
                and not Path(artifact_file).is_absolute()
                and ".." not in Path(artifact_file).parts,
                "model artifact path must be relative and contained",
            )
            _require(int(artifact.get("bytes", 0)) > 0, "model artifact byte bound must be positive")
            _require(HEX64.fullmatch(str(artifact.get("sha256", ""))) is not None, "model artifact digest must be 64-hex")
            _require(artifact.get("role") in {"execution", "weights", "governance"}, "model artifact role is unsupported")
            artifact_files.append(artifact_file)
        _require(len(artifact_files) == len(set(artifact_files)), "model artifact files must be unique")
        _require(sum(item.get("role") == "weights" for item in artifacts) == 1, "each model requires one registered weight artifact")
        _require(any(item.get("role") == "governance" for item in artifacts), "each model requires a bound model card/license artifact")
        _require(
            canonical_sha256(artifacts) == EXPECTED_MODEL_ARTIFACT_REGISTRY_SHA256.get(model["key"]),
            "model artifact registry differs from the frozen byte-for-byte manifest",
        )
        _require(
            sum(int(item["bytes"]) for item in artifacts) <= 400_000_000,
            "model artifact registry exceeds the frozen per-model byte ceiling",
        )
        model_keys.append(model["key"])
    _require(len(model_keys) == len(set(model_keys)), "model keys must be unique")
    expected_model_registry = {
        "distilgpt2": {
            "id": "distilbert/distilgpt2",
            "revision": "2290a62682d06624634c1f46a6ad5be0f47f38aa",
            "owner": "Hugging Face",
            "license": "Apache-2.0",
            "hooks": ["transformer.h.0", "transformer.h.5"],
            "use_safetensors": True,
            "weight_file": "model.safetensors",
            "governance_files": ["README.md"],
            "model_card_url": "https://huggingface.co/distilbert/distilgpt2/blob/2290a62682d06624634c1f46a6ad5be0f47f38aa/README.md",
        },
        "meta-opt-125m": {
            "id": "facebook/opt-125m",
            "revision": "27dcfa74d334bc871f3234de431e71c6eeba5dd6",
            "owner": "Meta",
            "license": "OPT-175B-license/non-commercial-research-only",
            "hooks": ["model.decoder.layers.0", "model.decoder.layers.11"],
            "use_safetensors": False,
            "weight_file": "pytorch_model.bin",
            "governance_files": ["LICENSE.md", "README.md"],
            "license_url": "https://huggingface.co/facebook/opt-125m/blob/27dcfa74d334bc871f3234de431e71c6eeba5dd6/LICENSE.md",
        },
        "pythia-160m": {
            "id": "EleutherAI/pythia-160m",
            "revision": "50f5173d932e8e61f858120bcb800b97af589f46",
            "owner": "EleutherAI",
            "license": "Apache-2.0",
            "hooks": ["gpt_neox.layers.0", "gpt_neox.layers.11"],
            "use_safetensors": True,
            "weight_file": "model.safetensors",
            "governance_files": ["README.md"],
            "model_card_url": "https://huggingface.co/EleutherAI/pythia-160m/blob/50f5173d932e8e61f858120bcb800b97af589f46/README.md",
        },
    }
    _require(model_keys == list(expected_model_registry), "model registry order or keys mismatch")
    for model in models:
        expected = expected_model_registry[model["key"]]
        _require(
            all(model[field] == expected[field] for field in ("id", "revision", "owner", "license"))
            and model["hook_modules"] == expected["hooks"]
            and model["use_safetensors"] is expected["use_safetensors"]
            and [item["file"] for item in model["artifacts"] if item["role"] == "weights"] == [expected["weight_file"]]
            and [item["file"] for item in model["artifacts"] if item["role"] == "governance"] == expected["governance_files"],
            "model identity, license, or hook registry mismatch",
        )
        for source_field in ("model_card_url", "license_url"):
            if source_field in expected:
                _require(model.get(source_field) == expected[source_field], f"model {source_field} differs from the frozen source")
    _require(models[1].get("legal_production_commercial_gate") == "BLOCKED", "OPT legal gate must remain blocked")
    _require(models[2].get("human_facing_deployment_policy_gate") == "MANUAL_REVIEW_REQUIRED", "Pythia human-facing gate must require review")
    _require(
        raw.get("model_matrix", {}).get("execution") == "sequential"
        and raw.get("model_matrix", {}).get("shared_dataset_row_split") is True
        and raw.get("model_matrix", {}).get("fresh_model_initialization_per_entry") is True,
        "model matrix must be sequential with a shared split and fresh initialization",
    )
    _require(
        raw["model_matrix"].get("cross_model_results_are_causal") is False
        and raw["model_matrix"].get("cross_model_monotonicity_assumed") is False,
        "cross-model results must remain noncausal and nonmonotone",
    )
    _require(
        raw.get("model_matrix") == {
            "execution": "sequential",
            "shared_dataset_row_split": True,
            "fresh_model_initialization_per_entry": True,
            "cross_model_results_are_causal": False,
            "cross_model_monotonicity_assumed": False,
        },
        "model matrix differs from the frozen v1 experiment",
    )
    _require(rows.get("total") == rows.get("train", 0) + rows.get("holdout", 0), "dataset row counts must add up")
    _require(isinstance(dataset.get("seed"), int), "dataset seed must be an integer")
    _require(dataset.get("selection_algorithm") == "sha256(seed:id) lexical ascending", "unsupported dataset selection algorithm")
    _require(
        training == {
            "seed": 3407,
            "max_sequence_length": 256,
            "max_prompt_length": 128,
            "batch_size": 16,
            "epochs": 1,
            "expected_optimizer_steps": 512,
            "learning_rate": 0.00005,
            "weight_decay": 0.01,
            "deterministic": True,
            "torch_dtype": "float32",
            "holdout_evaluations": ["before_training", "after_training"],
            "holdout_used_for_tuning": False,
            "pretokenization_bounds": {
                "max_field_utf8_bytes": 131072,
                "max_record_utf8_bytes": 262144,
            },
        },
        "training profile differs from the frozen bounded v1 experiment",
    )
    _require(0 < int(training.get("max_prompt_length", 0)) < int(training.get("max_sequence_length", 0)), "max prompt length must be below sequence length")
    _require(int(training.get("batch_size", 0)) > 0, "batch size must be positive")
    _require(int(training.get("epochs", 0)) > 0, "epochs must be positive")
    _require(isinstance(training.get("seed"), int), "training seed must be an integer")
    _require(float(training.get("learning_rate", 0.0)) > 0.0, "learning rate must be positive")
    _require(training.get("torch_dtype") == "float32", "this profile requires float32")
    _require(training.get("deterministic") is True, "deterministic execution must be enabled")
    _require(
        training.get("holdout_evaluations") == ["before_training", "after_training"]
        and training.get("holdout_used_for_tuning") is False,
        "holdout must be evaluated before/after and excluded from tuning",
    )
    computed_steps = int(training["epochs"]) * math.ceil(int(rows["train"]) / int(training["batch_size"]))
    _require(training.get("expected_optimizer_steps") == computed_steps, "expected optimizer steps do not match rows, batch size, and epochs")
    _require(hooks.get("raw_tensors_retained") is False, "raw tensors must not be retained")
    _require(hooks.get("capture") == "aggregate_only", "hook capture must remain aggregate-only")
    _require(hooks.get("fail_on_nonfinite") is True, "non-finite telemetry must fail closed")
    expected_measurements = [
        "loss",
        "activation_finite_fraction",
        "activation_l2_norm",
        "activation_abs_max",
        "backward_gradient_finite_fraction",
        "backward_gradient_l2_norm",
        "backward_gradient_abs_max",
        "parameter_gradient_finite_fraction",
        "parameter_gradient_l2_norm",
        "parameter_gradient_abs_max",
    ]
    _require(hooks.get("measurements") == expected_measurements, "hook measurement registry does not match emitted aggregate fields")
    _require(hooks.get("raw_tokens_retained") is False, "raw tokens must not be retained")
    _require(int(hooks.get("max_events", 0)) > 0, "hook event cap must be positive")
    _require(hooks.get("max_events") == 10000, "hook event cap differs from the frozen bounded v1 experiment")
    _require(
        hooks == {
            "capture": "aggregate_only",
            "measurements": expected_measurements,
            "raw_tensors_retained": False,
            "raw_tokens_retained": False,
            "max_events": 10000,
            "fail_on_nonfinite": True,
        },
        "hook profile differs from the frozen bounded v1 experiment",
    )
    _require(context_risk.get("enabled") is True, "context-risk ladder must be enabled")
    _require(
        context_risk.get("per_model") is True
        and context_risk.get("evaluation_checkpoints") == ["before_training", "after_training"]
        and context_risk.get("causal_interpretation") is False
        and context_risk.get("monotonicity_assumed") is False
        and context_risk.get("protected_unit") == "training_record",
        "context-risk execution semantics mismatch",
    )
    _require(int(context_risk.get("calibration_per_class", 0)) > 0, "context-risk calibration count must be positive")
    _require(int(context_risk.get("audit_per_class", 0)) > 0, "context-risk audit count must be positive")
    _require(
        int(context_risk["calibration_per_class"]) + int(context_risk["audit_per_class"]) <= int(rows["holdout"]),
        "context-risk class counts exceed the holdout class",
    )
    _require(float(context_risk.get("membership_prior", -1.0)) == 0.5, "context-risk profile requires an equal membership prior")
    partition = context_risk.get("partitioning", {})
    _require(
        partition.get("calibration_and_audit_disjoint") is True
        and partition.get("calibration") == {
            "members": int(context_risk["calibration_per_class"]),
            "nonmembers": int(context_risk["calibration_per_class"]),
        }
        and partition.get("audit") == {
            "members": int(context_risk["audit_per_class"]),
            "nonmembers": int(context_risk["audit_per_class"]),
        },
        "context-risk partition registry does not match executable counts",
    )
    registered_levels = [item.get("level") for item in context_risk.get("levels", []) if isinstance(item, dict)]
    _require(
        registered_levels == ["prior_only", "candidate_metadata", "candidate_loss", "metadata_plus_loss", "exact_training_roster"],
        "context-risk level registry does not match the executable profile order",
    )
    registered_features = {
        item["level"]: item.get("features")
        for item in context_risk.get("levels", [])
        if isinstance(item, dict) and isinstance(item.get("level"), str)
    }
    metadata_features = [
        "sequence_tokens",
        "target_tokens",
        "source_turn_count",
        "source_model_is_gpt4",
        "prompt_truncated",
        "response_truncated",
    ]
    _require(registered_features.get("candidate_metadata") == metadata_features, "candidate metadata feature registry mismatch")
    _require(
        registered_features.get("metadata_plus_loss") == [*metadata_features, "target_nll"],
        "combined context feature registry mismatch",
    )
    expected_levels = [
        {
            "level": "prior_only",
            "required_knowledge": ["equal_member_nonmember_prior"],
            "features": [],
            "interface_realizability": "text_only_or_more",
            "evidence_semantics": "descriptive_screen_no_power_claim",
        },
        {
            "level": "candidate_metadata",
            "required_knowledge": [
                "candidate_text",
                "registered_tokenizer_and_preprocessing",
                "source_turn_count",
                "source_response_model_family",
            ],
            "features": metadata_features,
            "interface_realizability": "conditional_on_exact_candidate_metadata_fields",
            "evidence_semantics": "descriptive_screen_no_power_claim",
        },
        {
            "level": "candidate_loss",
            "required_knowledge": ["candidate_text", "arbitrary_candidate_continuation_scoring"],
            "features": ["target_nll"],
            "interface_realizability": "logprob_interface_or_white_box",
            "evidence_semantics": "descriptive_screen_no_power_claim",
        },
        {
            "level": "metadata_plus_loss",
            "required_knowledge": [
                "candidate_text",
                "registered_tokenizer_and_preprocessing",
                "source_turn_count",
                "source_response_model_family",
                "arbitrary_candidate_continuation_scoring",
            ],
            "features": [*metadata_features, "target_nll"],
            "interface_realizability": "conditional_on_exact_metadata_and_arbitrary_candidate_scoring",
            "evidence_semantics": "descriptive_screen_no_power_claim",
        },
        {
            "level": "exact_training_roster",
            "required_knowledge": ["exact_training_roster_manifest"],
            "features": ["exact_training_roster_membership"],
            "interface_realizability": "internal_reconstructible_public_experiment_only",
            "evidence_semantics": "direct_membership_disclosure",
        },
    ]
    _require(context_risk.get("levels") == expected_levels, "context-risk normative registry mismatch")
    screen_policy = context_risk.get("screen_policy", {})
    _require(
        screen_policy.get("powered_for_release") is False
        and screen_policy.get("power_analysis_claimed") is False
        and screen_policy.get("descriptive_only") is True
        and screen_policy.get("can_clear") is False
        and screen_policy.get("can_block") is False,
        "statistical context-risk screens must remain descriptive, unpowered for release, and non-decision-bearing",
    )
    exact_policy = context_risk.get("exact_roster_policy", {})
    _require(
        exact_policy.get("can_clear") is False
        and exact_policy.get("can_block") is True
        and exact_policy.get("real_protected_roster_release_process") == "REDESIGN_REQUIRED",
        "exact protected-roster policy must block and require redesign without clearing",
    )
    safe_name = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    _require(output.get("fresh_run_directory_required") is True, "fresh output run directories must be required")
    _require(
        output.get("run_directory_mode") == "0700"
        and output.get("artifact_file_mode") == "0600",
        "internal output permissions must remain restricted",
    )
    _require(safe_name.fullmatch(str(output.get("json_report", ""))) is not None, "JSON report must be a safe basename")
    _require(safe_name.fullmatch(str(output.get("markdown_report", ""))) is not None, "Markdown report must be a safe basename")
    _require(safe_name.fullmatch(str(output.get("completion_manifest", ""))) is not None, "completion manifest must be a safe basename")
    _require(
        output.get("directory") == "output/llm-training-hook"
        and output.get("run_directory_pattern") == "output/llm-training-hook/{run_id}"
        and output.get("json_report") == "llm-training-hook-report.json"
        and output.get("markdown_report") == "llm-training-hook-report.md"
        and output.get("telemetry_pattern") == "training-telemetry-{model_key}.jsonl"
        and output.get("completion_manifest") == "RUN_COMPLETE.json",
        "output contract differs from the frozen v1 experiment",
    )
    pattern = output.get("telemetry_pattern")
    _require(isinstance(pattern, str) and pattern.count("{model_key}") == 1, "telemetry pattern must contain one model_key field")
    telemetry_names = [pattern.format(model_key=key) for key in model_keys]
    _require(all(safe_name.fullmatch(name) is not None for name in telemetry_names), "telemetry filenames must be safe basenames")
    artifact_names = [output["json_report"], output["markdown_report"], output["completion_manifest"], *telemetry_names]
    _require(len(set(artifact_names)) == len(artifact_names), "output artifact names must be unique")
    for section, expected_sha256 in EXPECTED_CONFIG_SECTION_SHA256.items():
        _require(
            canonical_sha256(raw.get(section)) == expected_sha256,
            f"{section} differs from the exact frozen v1 profile",
        )
    return raw


def load_config(path: Path) -> dict[str, Any]:
    _require(path.is_file() and path.stat().st_size <= MAX_CONFIG_BYTES, "configuration exceeds its byte bound")
    raw = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(raw, dict), "configuration must be a JSON object")
    return validate_config(raw)


def validate_and_extract_record(row: dict[str, Any]) -> dict[str, Any]:
    """Validate the legacy two-message fixture schema used by unit tests."""

    record_id = row.get("id")
    messages = row.get("messages")
    _require(isinstance(record_id, str) and bool(record_id.strip()), "dataset record id must be non-empty")
    _require(isinstance(messages, list) and len(messages) == 2, f"record {record_id} must have exactly two messages")
    _require(all(isinstance(item, dict) for item in messages), f"record {record_id} messages must be objects")
    _require([item.get("role") for item in messages] == ["user", "assistant"], f"record {record_id} roles must be user, assistant")
    _require(all(isinstance(item.get("content"), str) and item["content"].strip() for item in messages), f"record {record_id} message content must be non-empty")
    _require(row.get("prompt") == messages[0]["content"], f"record {record_id} prompt must equal the user message")
    constraints = row.get("constraints")
    _require(isinstance(constraints, list), f"record {record_id} constraints must be a list")
    return {
        "id": record_id,
        "user": messages[0]["content"],
        "assistant": messages[1]["content"],
        "source_turn_count": 1,
        "source_language_is_english": True,
        "source_model_is_gpt4": False,
    }


def extract_wildchat_records(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project the first real user/assistant pair and discard source identifiers.

    The caller loads only the explicitly registered Parquet leaf columns.  This
    adapter rejects redacted or top-level toxic rows, excludes later turns, and
    creates an opaque deterministic record identifier.  Exact duplicate first
    pairs are removed before selection so a dialogue cannot cross the train and
    holdout boundary under different upstream identifiers.
    """

    candidates: list[dict[str, Any]] = []
    rejected = {
        "missing_conversation_hash": 0,
        "redacted_or_toxic": 0,
        "non_english": 0,
        "invalid_first_pair": 0,
        "missing_first_pair_turn_identifier": 0,
        "empty_first_pair_content": 0,
    }
    for row in rows:
        source_id = row.get("conversation_hash")
        if not isinstance(source_id, str) or not source_id:
            rejected["missing_conversation_hash"] += 1
            continue
        if row.get("toxic") is not False or row.get("redacted") is not False:
            rejected["redacted_or_toxic"] += 1
            continue
        if str(row.get("language") or "").casefold() != "english":
            rejected["non_english"] += 1
            continue
        conversation = row.get("conversation")
        if not isinstance(conversation, list) or len(conversation) < 2:
            rejected["invalid_first_pair"] += 1
            continue
        first, second = conversation[0], conversation[1]
        if (
            not isinstance(first, dict)
            or not isinstance(second, dict)
            or first.get("role") != "user"
            or second.get("role") != "assistant"
        ):
            rejected["invalid_first_pair"] += 1
            continue
        if not isinstance(first.get("turn_identifier"), int) or not isinstance(second.get("turn_identifier"), int):
            rejected["missing_first_pair_turn_identifier"] += 1
            continue
        user = first.get("content")
        assistant = second.get("content")
        if (
            not isinstance(user, str)
            or not user.strip()
            or not isinstance(assistant, str)
            or not assistant.strip()
        ):
            rejected["empty_first_pair_content"] += 1
            continue
        dialogue_sha256 = canonical_sha256([user, assistant])
        record_id = canonical_sha256({
            "source_conversation_hash": source_id,
            "first_pair_sha256": dialogue_sha256,
        })
        language = str(row.get("language") or "")
        source_model = str(row.get("model") or "")
        turn_count = row.get("turn")
        candidates.append({
            "id": record_id,
            "user": user,
            "assistant": assistant,
            "source_turn_count": int(turn_count) if isinstance(turn_count, int) and turn_count > 0 else 1,
            "source_model_is_gpt4": source_model.casefold().startswith("gpt-4"),
            "source_language": language or "unknown",
            "source_model": source_model or "unknown",
            "dialogue_sha256": dialogue_sha256,
        })

    unique_ids: dict[str, dict[str, Any]] = {}
    for candidate in sorted(candidates, key=lambda item: item["id"]):
        unique_ids.setdefault(candidate["id"], candidate)
    unique_dialogues: dict[str, dict[str, Any]] = {}
    for candidate in unique_ids.values():
        unique_dialogues.setdefault(candidate["dialogue_sha256"], candidate)
    extracted = sorted(unique_dialogues.values(), key=lambda item: item["id"])
    _require(bool(extracted), "WildChat projection contains no eligible records")
    return extracted, {
        "source_rows": len(rows),
        "eligible_before_deduplication": len(candidates),
        "duplicate_record_ids_removed": len(candidates) - len(unique_ids),
        "duplicate_first_pairs_removed": len(unique_ids) - len(unique_dialogues),
        "eligible_after_deduplication": len(extracted),
        "rejected": rejected,
        "adapter": "wildchat_first_user_assistant_turn_v1",
        "later_turns_excluded": True,
        "source_identifiers_retained_in_report": False,
        "excluded_sensitive_source_fields_loaded": False,
    }


def select_records(
    rows: Sequence[dict[str, Any]],
    seed: int,
    total: int,
    train_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select records without depending on a dataset library's shuffle algorithm."""

    extracted = [
        row if {"id", "user", "assistant", "source_turn_count"}.issubset(row) else validate_and_extract_record(row)
        for row in rows
    ]
    ids = [item["id"] for item in extracted]
    _require(len(ids) == len(set(ids)), "dataset record ids must be unique")
    _require(0 < total <= len(extracted), "requested sample exceeds available rows")
    _require(0 < train_count < total, "train count must leave a non-empty holdout")
    ordered = sorted(
        extracted,
        key=lambda item: (hashlib.sha256(f"{seed}:{item['id']}".encode("utf-8")).hexdigest(), item["id"]),
    )[:total]
    return ordered[:train_count], ordered[train_count:]


def validate_content_disjointness(
    train_records: Sequence[dict[str, Any]],
    holdout_records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    def dialogue_digest(item: dict[str, Any]) -> str:
        return canonical_sha256([item["user"], item["assistant"]])

    train_hashes = [dialogue_digest(item) for item in train_records]
    holdout_hashes = [dialogue_digest(item) for item in holdout_records]
    _require(len(train_hashes) == len(set(train_hashes)), "training split contains duplicate dialogue content")
    _require(len(holdout_hashes) == len(set(holdout_hashes)), "holdout split contains duplicate dialogue content")
    overlap = set(train_hashes) & set(holdout_hashes)
    _require(not overlap, "training and holdout splits contain identical dialogue content")
    return {
        "train_dialogue_hashes_sha256": canonical_sha256(sorted(train_hashes)),
        "holdout_dialogue_hashes_sha256": canonical_sha256(sorted(holdout_hashes)),
        "cross_split_exact_dialogue_overlap_count": 0,
        "within_train_exact_duplicate_count": 0,
        "within_holdout_exact_duplicate_count": 0,
    }


_RISK_PATTERNS = {
    "email_like": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "private_key_marker": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    "url": re.compile(r"https?://", re.IGNORECASE),
    "prompt_injection_phrase": re.compile(r"\b(?:ignore (?:all |the )?previous|reveal (?:the )?system prompt|developer message)\b", re.IGNORECASE),
    "copyright_request_phrase": re.compile(r"\b(?:lyrics|verbatim|full text of|entire (?:book|article|poem))\b", re.IGNORECASE),
    "sensitive_domain_phrase": re.compile(r"\b(?:suicide|self-harm|diagnos(?:e|is)|medical advice|bomb|malware|sexual|religion|politic)\w*\b", re.IGNORECASE),
}


def scan_dataset_risks(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return heuristic counts and ID commitments, never matched text."""

    result: dict[str, Any] = {}
    content_hashes: list[str] = []
    for name, pattern in _RISK_PATTERNS.items():
        matching_ids: list[str] = []
        for item in records:
            combined = f"{item['user']}\n{item['assistant']}"
            if pattern.search(combined):
                matching_ids.append(item["id"])
        result[name] = {
            "record_count": len(matching_ids),
            "record_id_sha256s": [hashlib.sha256(value.encode("utf-8")).hexdigest() for value in sorted(matching_ids)],
        }
    for item in records:
        content_hashes.append(hashlib.sha256(canonical_json([item["user"], item["assistant"]])).hexdigest())
    result["exact_duplicate_dialogues"] = len(content_hashes) - len(set(content_hashes))
    result["semantics"] = "heuristic preflight screen; matches are not adjudicated harms and misses are not safety evidence"
    result["raw_text_retained"] = False
    return result


def _download_verified_object(
    url: str,
    destination: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    offline: bool,
    timeout_seconds: int,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination.parent, 0o700)
    if destination.exists():
        if (
            destination.is_file()
            and destination.stat().st_size == expected_bytes
            and sha256_file(destination) == expected_sha256
        ):
            os.chmod(destination, 0o600)
            return destination
        raise ValueError(f"cached immutable object does not match its registered size/digest: {destination}")
    if offline:
        raise FileNotFoundError(f"verified object is absent from the offline cache: {destination}")

    partial = destination.with_name(f"{destination.name}.partial-{os.getpid()}")
    _require(not partial.exists(), f"download staging path already exists: {partial}")
    digest = hashlib.sha256()
    received = 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "model-release-assurance-training-hook/1.1"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response, partial.open("xb") as output:
            os.chmod(partial, 0o600)
            declared = response.headers.get("Content-Length")
            if declared is not None:
                _require(int(declared) == expected_bytes, "remote object Content-Length differs from the registry")
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                _require(received <= expected_bytes, "remote object exceeded the registered byte bound")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        _require(received == expected_bytes, "remote object ended before the registered byte count")
        _require(digest.hexdigest() == expected_sha256, "remote object digest differs from the registry")
        try:
            os.link(partial, destination)
        except FileExistsError as exc:
            raise ValueError(f"refusing to overwrite concurrently published cache object: {destination}") from exc
        os.chmod(destination, 0o600)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if partial.exists():
            partial.unlink()
    return destination


def download_verified_dataset(config: dict[str, Any], cache_dir: Path, *, offline: bool) -> Path:
    dataset = config["dataset"]
    filename = f"{dataset['revision']}-{Path(dataset['file']).name}"
    destination = cache_dir / filename
    url = DATASET_URL.format(
        dataset_id=dataset["id"],
        revision=dataset["revision"],
        file=dataset["file"],
    )
    return _download_verified_object(
        url,
        destination,
        expected_sha256=dataset["sha256"],
        expected_bytes=int(dataset["bytes"]),
        offline=offline,
        timeout_seconds=120,
    )


def download_verified_catalog(config: dict[str, Any], cache_dir: Path, *, offline: bool) -> Path:
    catalog = config["catalog"]
    destination = cache_dir / f"{catalog['revision']}-README.md"
    return _download_verified_object(
        CATALOG_URL.format(revision=catalog["revision"]),
        destination,
        expected_sha256=catalog["readme_sha256"],
        expected_bytes=int(catalog["readme_bytes"]),
        offline=offline,
        timeout_seconds=60,
    )


def download_verified_dataset_governance(
    config: dict[str, Any],
    cache_dir: Path,
    *,
    offline: bool,
) -> dict[str, Path]:
    dataset = config["dataset"]
    registered = dataset["governance_sources"]
    revision_dir = cache_dir / dataset["revision"]
    paths: dict[str, Path] = {}
    for key in ("dataset_card", "license_file"):
        source = registered[key]
        paths[key] = _download_verified_object(
            source["url"],
            revision_dir / source["file"],
            expected_sha256=source["sha256"],
            expected_bytes=int(source["bytes"]),
            offline=offline,
            timeout_seconds=60,
        )
    card_text = paths["dataset_card"].read_text(encoding="utf-8")
    license_text = paths["license_file"].read_text(encoding="utf-8")
    _require("license: odc-by" in card_text, "pinned dataset card lacks its registered license declaration")
    _require("ODC Attribution License (ODC-By)" in license_text, "pinned dataset license file has an unexpected title")
    return paths


def load_dataset_rows(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    # Use Parquet leaf paths so IP, location, header, timestamp, OpenAI request
    # IDs, moderation arrays, and per-turn request parameters are never loaded.
    table = pq.ParquetFile(path).read(columns=[
        "conversation_hash",
        "conversation.list.element.content",
        "conversation.list.element.role",
        "conversation.list.element.turn_identifier",
        "turn",
        "language",
        "model",
        "toxic",
        "redacted",
    ])
    return table.to_pylist()


def tokenize_records(
    records: Sequence[dict[str, Any]],
    tokenizer: Any,
    *,
    max_length: int,
    max_prompt_length: int,
    max_field_utf8_bytes: int = 131072,
    max_record_utf8_bytes: int = 262144,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    prompt_truncated = 0
    response_truncated = 0
    sequence_lengths: list[int] = []
    target_lengths: list[int] = []
    prompt_prefix_ids = tokenizer("User:\n", add_special_tokens=False, verbose=False)["input_ids"]
    prompt_suffix_ids = tokenizer("\n\nAssistant:\n", add_special_tokens=False, verbose=False)["input_ids"]
    builder = getattr(tokenizer, "build_inputs_with_special_tokens", None)
    probe_text = "MRA-special-token-policy-probe"
    probe_raw = tokenizer(probe_text, add_special_tokens=False, verbose=False)["input_ids"]
    _require(bool(probe_raw), "special-token policy probe produced no ordinary tokens")
    if callable(builder):
        probe_with_special_tokens = list(builder(probe_raw))
        empty_with_special_tokens = list(builder([]))
        special_token_policy_api = "build_inputs_with_special_tokens"
    else:
        probe_with_special_tokens = list(
            tokenizer(probe_text, add_special_tokens=True, verbose=False)["input_ids"]
        )
        empty_with_special_tokens = list(
            tokenizer("", add_special_tokens=True, verbose=False)["input_ids"]
        )
        special_token_policy_api = "tokenizer_call_probe_transformers_v5_compatible"
    matching_offsets = [
        offset
        for offset in range(len(probe_with_special_tokens) - len(probe_raw) + 1)
        if probe_with_special_tokens[offset : offset + len(probe_raw)] == probe_raw
    ]
    _require(
        len(matching_offsets) == 1,
        "tokenizer special-token policy must preserve the ordinary probe token sequence exactly once",
    )
    prefix_length = matching_offsets[0]
    suffix_length = len(probe_with_special_tokens) - prefix_length - len(probe_raw)
    _require(suffix_length == 0, "this completion-only profile supports prefix special tokens only")
    special_prefix_ids = probe_with_special_tokens[:prefix_length]
    _require(
        empty_with_special_tokens == special_prefix_ids,
        "empty-string and ordinary-input special-token prefix policies differ",
    )
    leading_special_token_count = len(special_prefix_ids)
    _require(
        leading_special_token_count + len(prompt_prefix_ids) + len(prompt_suffix_ids) < max_prompt_length,
        "max_prompt_length cannot preserve the registered role framing",
    )
    user_token_budget = (
        max_prompt_length
        - leading_special_token_count
        - len(prompt_prefix_ids)
        - len(prompt_suffix_ids)
    )
    _require(0 < max_field_utf8_bytes <= max_record_utf8_bytes, "invalid pre-tokenization byte bounds")
    maximum_observed_field_utf8_bytes = 0
    maximum_observed_record_utf8_bytes = 0
    for item in records:
        user_utf8_bytes = len(item["user"].encode("utf-8"))
        assistant_utf8_bytes = len(item["assistant"].encode("utf-8"))
        record_utf8_bytes = user_utf8_bytes + assistant_utf8_bytes
        _require(
            user_utf8_bytes <= max_field_utf8_bytes and assistant_utf8_bytes <= max_field_utf8_bytes,
            f"record {item['id']} exceeds the registered per-field pre-tokenization byte bound",
        )
        _require(
            record_utf8_bytes <= max_record_utf8_bytes,
            f"record {item['id']} exceeds the registered per-record pre-tokenization byte bound",
        )
        maximum_observed_field_utf8_bytes = max(
            maximum_observed_field_utf8_bytes,
            user_utf8_bytes,
            assistant_utf8_bytes,
        )
        maximum_observed_record_utf8_bytes = max(maximum_observed_record_utf8_bytes, record_utf8_bytes)
        response = item["assistant"] + (tokenizer.eos_token or "")
        user_ids = tokenizer(item["user"], add_special_tokens=False, verbose=False)["input_ids"]
        response_ids = tokenizer(response, add_special_tokens=False, verbose=False)["input_ids"]
        if len(user_ids) > user_token_budget:
            prompt_truncated += 1
        raw_prompt = [*prompt_prefix_ids, *user_ids[:user_token_budget], *prompt_suffix_ids]
        kept_prompt = [*special_prefix_ids, *raw_prompt]
        available = max_length - len(kept_prompt)
        _require(available > 0, "tokenization left no target-token capacity")
        if len(response_ids) > available:
            response_truncated += 1
        kept_response = response_ids[:available]
        _require(bool(kept_response), f"record {item['id']} has no target tokens")
        input_ids = [*special_prefix_ids, *raw_prompt, *kept_response]
        _require(
            input_ids[:len(kept_prompt)] == kept_prompt
            and len(input_ids) == len(kept_prompt) + len(kept_response),
            "tokenizer special-token policy is incompatible with completion-only masking",
        )
        labels = [-100] * len(kept_prompt) + kept_response
        encoded.append({
            "id": item["id"],
            "input_ids": input_ids,
            "labels": labels,
            "source_turn_count": int(item["source_turn_count"]),
            "source_model_is_gpt4": bool(item["source_model_is_gpt4"]),
            "prompt_truncated": len(user_ids) > user_token_budget,
            "response_truncated": len(response_ids) > available,
        })
        sequence_lengths.append(len(input_ids))
        target_lengths.append(len(kept_response))
    return encoded, {
        "records": len(encoded),
        "prompt_truncated_records": prompt_truncated,
        "response_truncated_records": response_truncated,
        "prompt_role_framing_preserved": True,
        "prompt_role_frame_tokens": len(prompt_prefix_ids) + len(prompt_suffix_ids),
        "prepended_model_special_tokens": leading_special_token_count,
        "special_token_policy_api": special_token_policy_api,
        "special_token_policy_prefix_only_verified": True,
        "maximum_user_tokens_before_truncation": user_token_budget,
        "pretokenization_bounds": {
            "max_field_utf8_bytes": max_field_utf8_bytes,
            "max_record_utf8_bytes": max_record_utf8_bytes,
            "maximum_observed_field_utf8_bytes": maximum_observed_field_utf8_bytes,
            "maximum_observed_record_utf8_bytes": maximum_observed_record_utf8_bytes,
            "all_records_within_bounds": True,
        },
        "sequence_tokens": _integer_distribution(sequence_lengths),
        "target_tokens": _integer_distribution(target_lengths),
    }


def _integer_distribution(values: Sequence[int]) -> dict[str, Any]:
    ordered = sorted(values)
    _require(bool(ordered), "cannot summarize an empty sequence")
    return {
        "minimum": ordered[0],
        "median": ordered[len(ordered) // 2],
        "maximum": ordered[-1],
        "total": sum(ordered),
    }


def collate_batch(items: Sequence[dict[str, Any]], pad_token_id: int, device: Any) -> dict[str, Any]:
    import torch

    length = max(len(item["input_ids"]) for item in items)
    input_rows: list[list[int]] = []
    label_rows: list[list[int]] = []
    masks: list[list[int]] = []
    for item in items:
        padding = length - len(item["input_ids"])
        input_rows.append(item["input_ids"] + [pad_token_id] * padding)
        label_rows.append(item["labels"] + [-100] * padding)
        masks.append([1] * len(item["input_ids"]) + [0] * padding)
    return {
        "input_ids": torch.tensor(input_rows, dtype=torch.long, device=device),
        "labels": torch.tensor(label_rows, dtype=torch.long, device=device),
        "attention_mask": torch.tensor(masks, dtype=torch.long, device=device),
        "record_ids": [item["id"] for item in items],
        "input_tokens": sum(sum(row) for row in masks),
        "target_tokens": sum(sum(value != -100 for value in row) for row in label_rows),
        "truncated_records": sum(bool(item["prompt_truncated"] or item["response_truncated"]) for item in items),
    }


def iter_batches(items: Sequence[dict[str, Any]], batch_size: int) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def evaluate(model: Any, items: Sequence[dict[str, Any]], batch_size: int, pad_token_id: int, device: Any) -> dict[str, Any]:
    import torch

    model.eval()
    weighted_loss = 0.0
    target_tokens = 0
    with torch.no_grad():
        for items_batch in iter_batches(items, batch_size):
            batch = collate_batch(items_batch, pad_token_id, device)
            output = model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
                labels=batch["labels"],
            )
            loss = float(output.loss.detach().cpu())
            _require(math.isfinite(loss), "evaluation loss is non-finite")
            weighted_loss += loss * batch["target_tokens"]
            target_tokens += batch["target_tokens"]
    mean_loss = weighted_loss / target_tokens
    perplexity_exponent_cap = 80.0
    perplexity_capped = mean_loss > perplexity_exponent_cap
    return {
        "mean_target_token_nll": mean_loss,
        "perplexity": math.exp(min(mean_loss, perplexity_exponent_cap)),
        "perplexity_exponent_cap_nll": perplexity_exponent_cap,
        "perplexity_capped": perplexity_capped,
        "perplexity_semantics": "exp(mean target-token NLL); the reported numeric value is capped at exp(80) and the cap flag must be checked",
        "target_tokens": target_tokens,
        "records": len(items),
    }


def per_example_loss_metrics(
    model: Any,
    items: Sequence[dict[str, Any]],
    pad_token_id: int,
    device: Any,
    *,
    batch_size: int = 16,
) -> list[dict[str, Any]]:
    """Measure candidate loss without retaining text, token IDs, or logits."""

    import torch

    model.eval()
    measured: list[dict[str, Any]] = []
    with torch.no_grad():
        for items_batch in iter_batches(items, batch_size):
            batch = collate_batch(items_batch, pad_token_id, device)
            output = model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
            )
            logits = output.logits[:, :-1, :].float()
            labels = batch["labels"][:, 1:]
            token_losses = torch.nn.functional.cross_entropy(
                logits.reshape(-1, logits.shape[-1]),
                labels.reshape(-1),
                ignore_index=-100,
                reduction="none",
            ).reshape(labels.shape)
            target_mask = labels != -100
            target_counts = target_mask.sum(dim=1)
            _require(bool((target_counts > 0).all().item()), "candidate has no shifted target tokens")
            row_losses = (token_losses * target_mask).sum(dim=1) / target_counts
            _require(bool(torch.isfinite(row_losses).all().item()), "candidate loss is non-finite")
            for item, loss, target_count in zip(items_batch, row_losses.tolist(), target_counts.tolist()):
                measured.append({
                    "id": item["id"],
                    "target_nll": float(loss),
                    "sequence_tokens": len(item["input_ids"]),
                    "target_tokens": int(target_count),
                    "source_turn_count": int(item["source_turn_count"]),
                    "source_model_is_gpt4": bool(item["source_model_is_gpt4"]),
                    "prompt_truncated": bool(item["prompt_truncated"]),
                    "response_truncated": bool(item["response_truncated"]),
                })
    return measured


def _balanced_accuracy(member_scores: Sequence[float], nonmember_scores: Sequence[float], threshold: float) -> float:
    tpr = sum(value >= threshold for value in member_scores) / len(member_scores)
    tnr = sum(value < threshold for value in nonmember_scores) / len(nonmember_scores)
    return (tpr + tnr) / 2.0


def _calibrate_threshold(member_scores: Sequence[float], nonmember_scores: Sequence[float]) -> float:
    values = sorted(set([*member_scores, *nonmember_scores]))
    _require(bool(values), "membership calibration scores are empty")
    candidates = [values[0] - 1.0, *values]
    candidates.extend((left + right) / 2.0 for left, right in zip(values, values[1:]))
    candidates.append(values[-1] + 1.0)
    return max(
        sorted(candidates),
        key=lambda threshold: _balanced_accuracy(member_scores, nonmember_scores, threshold),
    )


def _roc_auc(member_scores: Sequence[float], nonmember_scores: Sequence[float]) -> float:
    wins = 0.0
    for member in member_scores:
        for nonmember in nonmember_scores:
            wins += 1.0 if member > nonmember else 0.5 if member == nonmember else 0.0
    return wins / (len(member_scores) * len(nonmember_scores))


def _screen_result(
    calibration_member: Sequence[float],
    calibration_nonmember: Sequence[float],
    audit_member: Sequence[float],
    audit_nonmember: Sequence[float],
) -> dict[str, Any]:
    threshold = _calibrate_threshold(calibration_member, calibration_nonmember)
    true_members = sum(value >= threshold for value in audit_member)
    true_nonmembers = sum(value < threshold for value in audit_nonmember)
    member_count = len(audit_member)
    nonmember_count = len(audit_nonmember)
    return {
        "calibration_threshold": threshold,
        "audit_members": member_count,
        "audit_nonmembers": nonmember_count,
        "true_members": true_members,
        "true_nonmembers": true_nonmembers,
        "balanced_accuracy": ((true_members / member_count) + (true_nonmembers / nonmember_count)) / 2.0,
        "roc_auc": _roc_auc(audit_member, audit_nonmember),
        "membership_advantage_at_threshold": (true_members / member_count) - ((nonmember_count - true_nonmembers) / nonmember_count),
        "evidence_class": "descriptive_constructed_prior_screen",
        "can_block": False,
        "can_clear": False,
    }


def _standardized_linear_scores(
    calibration_member: Sequence[Sequence[float]],
    calibration_nonmember: Sequence[Sequence[float]],
    audit_member: Sequence[Sequence[float]],
    audit_nonmember: Sequence[Sequence[float]],
) -> tuple[list[float], list[float], list[float], list[float]]:
    calibration = [*calibration_member, *calibration_nonmember]
    width = len(calibration[0])
    means = [sum(row[index] for row in calibration) / len(calibration) for index in range(width)]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in calibration) / len(calibration)
        scales.append(max(math.sqrt(variance), 1e-12))

    def standardize(row: Sequence[float]) -> list[float]:
        return [(row[index] - means[index]) / scales[index] for index in range(width)]

    standardized_members = [standardize(row) for row in calibration_member]
    standardized_nonmembers = [standardize(row) for row in calibration_nonmember]
    direction = [
        (sum(row[index] for row in standardized_members) / len(standardized_members))
        - (sum(row[index] for row in standardized_nonmembers) / len(standardized_nonmembers))
        for index in range(width)
    ]

    def score(row: Sequence[float]) -> float:
        return sum(value * weight for value, weight in zip(standardize(row), direction))

    return (
        [score(row) for row in calibration_member],
        [score(row) for row in calibration_nonmember],
        [score(row) for row in audit_member],
        [score(row) for row in audit_nonmember],
    )


def build_context_risk_ladder(
    train_metrics: Sequence[dict[str, Any]],
    holdout_metrics: Sequence[dict[str, Any]],
    *,
    seed: int,
    calibration_per_class: int,
    audit_per_class: int,
) -> dict[str, Any]:
    """Compare membership screens under increasingly informative contexts."""

    required = calibration_per_class + audit_per_class
    train_ids = [item["id"] for item in train_metrics]
    holdout_ids = [item["id"] for item in holdout_metrics]
    _require(len(train_ids) == len(set(train_ids)), "context-risk member IDs must be unique")
    _require(len(holdout_ids) == len(set(holdout_ids)), "context-risk nonmember IDs must be unique")
    _require(set(train_ids).isdisjoint(holdout_ids), "context-risk member and nonmember IDs must be disjoint")
    _require(required <= len(train_metrics), "context-risk member arm lacks registered rows")
    _require(required <= len(holdout_metrics), "context-risk nonmember arm lacks registered rows")

    def ordered(values: Sequence[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
        return sorted(
            values,
            key=lambda item: hashlib.sha256(f"context-risk:{seed}:{arm}:{item['id']}".encode("utf-8")).hexdigest(),
        )[:required]

    members = ordered(train_metrics, "member")
    nonmembers = ordered(holdout_metrics, "nonmember")
    _require(len(members) == required and len(nonmembers) == required, "context-risk split lacks registered rows")
    calibration_members = members[:calibration_per_class]
    audit_members = members[calibration_per_class:]
    calibration_nonmembers = nonmembers[:calibration_per_class]
    audit_nonmembers = nonmembers[calibration_per_class:]

    metadata_fields = (
        "sequence_tokens",
        "target_tokens",
        "source_turn_count",
        "source_model_is_gpt4",
        "prompt_truncated",
        "response_truncated",
    )

    def metadata_vector(item: dict[str, Any]) -> list[float]:
        return [
            math.log1p(float(item["sequence_tokens"])),
            math.log1p(float(item["target_tokens"])),
            math.log1p(float(item["source_turn_count"])),
            float(item["source_model_is_gpt4"]),
            float(item["prompt_truncated"]),
            float(item["response_truncated"]),
        ]

    prior = _screen_result(
        [0.0] * calibration_per_class,
        [0.0] * calibration_per_class,
        [0.0] * audit_per_class,
        [0.0] * audit_per_class,
    )
    metadata_scores = _standardized_linear_scores(
        [metadata_vector(item) for item in calibration_members],
        [metadata_vector(item) for item in calibration_nonmembers],
        [metadata_vector(item) for item in audit_members],
        [metadata_vector(item) for item in audit_nonmembers],
    )
    metadata = _screen_result(*metadata_scores)
    loss = _screen_result(
        [-item["target_nll"] for item in calibration_members],
        [-item["target_nll"] for item in calibration_nonmembers],
        [-item["target_nll"] for item in audit_members],
        [-item["target_nll"] for item in audit_nonmembers],
    )
    combined_scores = _standardized_linear_scores(
        [[*metadata_vector(item), -item["target_nll"]] for item in calibration_members],
        [[*metadata_vector(item), -item["target_nll"]] for item in calibration_nonmembers],
        [[*metadata_vector(item), -item["target_nll"]] for item in audit_members],
        [[*metadata_vector(item), -item["target_nll"]] for item in audit_nonmembers],
    )
    combined = _screen_result(*combined_scores)
    exact_roster = {
        "result_type": "logical_direct_disclosure",
        "measured": False,
        "audit_members": audit_per_class,
        "audit_nonmembers": audit_per_class,
        "balanced_accuracy": None,
        "roc_auc": None,
        "membership_advantage_at_threshold": None,
        "evidence_class": "direct_disclosure_not_statistical_inference",
        "logical_consequence": "an authenticated exact roster resolving the protected unit determines membership by lookup; no classifier or empirical accuracy estimate is involved",
        "conditions": [
            "the roster is complete and authentic",
            "roster identifiers resolve to the declared protected unit and population",
            "membership itself is protected information",
        ],
        "can_block": True,
        "can_clear": False,
    }
    levels = [
        {
            "level": "K0_prior_only",
            "attacker_knowledge": "equal membership prior; no candidate metadata and no model observation",
            "features": [],
            "recipient_realizability": {
                "text_only": "yes",
                "logprob_api": "yes",
                "white_box": "yes",
                "roster_package": "yes",
                "preconditions": ["registered equal-prior audit game"],
            },
            "result": prior,
            "release_route": "inconclusive; no release clearance",
        },
        {
            "level": "K1_candidate_metadata",
            "attacker_knowledge": "candidate token lengths, source conversation-turn count, upstream response-model family, and truncation indicators",
            "features": list(metadata_fields),
            "recipient_realizability": {
                "text_only": "conditional",
                "logprob_api": "conditional",
                "white_box": "conditional",
                "roster_package": "conditional",
                "preconditions": [
                    "attacker has the exact candidate dialogue, source turn count, and upstream response-model family",
                    "tokenizer, formatting, truncation policy, and preprocessing are known",
                ],
            },
            "result": metadata,
            "release_route": "screen only; preregistered powered evidence would be needed to block, and a null cannot clear",
        },
        {
            "level": "K2_candidate_model_loss",
            "attacker_knowledge": "complete candidate dialogue plus its target-model per-token loss",
            "features": ["target_nll"],
            "recipient_realizability": {
                "text_only": "no",
                "logprob_api": "conditional",
                "white_box": "yes",
                "roster_package": "no_unless_model_observation_is_also_exposed",
                "preconditions": [
                    "complete candidate dialogue is known",
                    "the interface scores every supplied candidate continuation token; generated-token-only log probabilities are insufficient",
                ],
            },
            "result": loss,
            "release_route": "not applicable to text-only recipients; screen only for log-probability or white-box recipients",
        },
        {
            "level": "K3_metadata_plus_model_loss",
            "attacker_knowledge": "candidate metadata, complete candidate dialogue, and target-model per-token loss",
            "features": [*metadata_fields, "target_nll"],
            "recipient_realizability": {
                "text_only": "no",
                "logprob_api": "conditional",
                "white_box": "conditional_on_metadata_preconditions",
                "roster_package": "no_unless_metadata_and_model_observation_are_also_exposed",
                "preconditions": [
                    "all K1 metadata preconditions hold",
                    "all K2 arbitrary-candidate scoring preconditions hold",
                ],
            },
            "result": combined,
            "release_route": "not applicable to text-only recipients; screen only for log-probability or white-box recipients",
        },
        {
            "level": "K4_exact_training_roster",
            "attacker_knowledge": "authenticated exact candidate-to-training-roster membership",
            "features": ["exact_training_roster_membership"],
            "recipient_realizability": {
                "text_only": "no_unless_a_separate_roster_path_exists",
                "logprob_api": "no_unless_a_separate_roster_path_exists",
                "white_box": "no_unless_a_separate_roster_path_exists",
                "roster_package": "yes",
                "preconditions": ["roster identifiers are authenticated and resolve to the protected membership unit"],
            },
            "result": exact_roster,
            "release_route": "direct disclosure: block the membership gate and require redesign if roster membership is protected",
        },
    ]
    empty_metadata: list[str] = []
    exact_metadata = list(metadata_fields)
    scenarios = [
        {
            "release_interface": "text_only_generation_without_roster",
            "contract_fragment": {
                "generated_text": True,
                "generated_token_log_probabilities": False,
                "arbitrary_candidate_continuation_scoring": False,
                "white_box_weights": False,
                "training_roster": False,
                "candidate_metadata_fields": empty_metadata,
            },
            "observable_levels": ["K0_prior_only"],
            "membership_gate": "INCONCLUSIVE",
            "release_process_state": "ASSESSMENT_INCOMPLETE",
            "release_process_effect": "no authorization; obtain powered recipient-realizable evidence and satisfy every other gate",
        },
        {
            "release_interface": "text_generation_with_exact_candidate_metadata",
            "contract_fragment": {
                "generated_text": True,
                "generated_token_log_probabilities": False,
                "arbitrary_candidate_continuation_scoring": False,
                "white_box_weights": False,
                "training_roster": False,
                "candidate_metadata_fields": exact_metadata,
            },
            "observable_levels": ["K0_prior_only", "K1_candidate_metadata"],
            "membership_gate": "INCONCLUSIVE",
            "release_process_state": "ASSESSMENT_INCOMPLETE",
            "release_process_effect": "metadata makes K1 recipient-realizable, but this descriptive screen cannot clear or authorize release",
        },
        {
            "release_interface": "generation_with_generated_token_log_probabilities_only",
            "contract_fragment": {
                "generated_text": True,
                "generated_token_log_probabilities": True,
                "arbitrary_candidate_continuation_scoring": False,
                "white_box_weights": False,
                "training_roster": False,
                "candidate_metadata_fields": empty_metadata,
            },
            "observable_levels": ["K0_prior_only"],
            "membership_gate": "INCONCLUSIVE",
            "release_process_state": "ASSESSMENT_INCOMPLETE",
            "release_process_effect": "generated-token log probabilities enlarge other attack surfaces but do not satisfy this experiment's arbitrary-candidate K2 precondition",
        },
        {
            "release_interface": "arbitrary_candidate_scoring_without_source_metadata",
            "contract_fragment": {
                "generated_text": True,
                "generated_token_log_probabilities": True,
                "arbitrary_candidate_continuation_scoring": True,
                "white_box_weights": False,
                "training_roster": False,
                "candidate_metadata_fields": empty_metadata,
            },
            "observable_levels": ["K0_prior_only", "K2_candidate_model_loss"],
            "membership_gate": "INCONCLUSIVE",
            "release_process_state": "ASSESSMENT_INCOMPLETE",
            "release_process_effect": "K2 becomes recipient-realizable; bind the exact scoring interface and obtain powered evidence before any decision",
        },
        {
            "release_interface": "white_box_with_exact_candidate_metadata",
            "contract_fragment": {
                "generated_text": True,
                "generated_token_log_probabilities": False,
                "arbitrary_candidate_continuation_scoring": True,
                "white_box_weights": True,
                "training_roster": False,
                "candidate_metadata_fields": exact_metadata,
            },
            "observable_levels": ["K0_prior_only", "K1_candidate_metadata", "K2_candidate_model_loss", "K3_metadata_plus_model_loss"],
            "membership_gate": "INCONCLUSIVE",
            "release_process_state": "ASSESSMENT_INCOMPLETE",
            "release_process_effect": "K1-K3 become recipient-realizable; white-box release requires a separately powered attack battery and this screen cannot clear",
        },
        {
            "release_interface": "protected_data_package_with_exact_training_roster",
            "contract_fragment": {
                "generated_text": True,
                "generated_token_log_probabilities": False,
                "arbitrary_candidate_continuation_scoring": False,
                "white_box_weights": False,
                "training_roster": True,
                "training_roster_membership_protected": True,
                "candidate_metadata_fields": empty_metadata,
            },
            "observable_levels": ["K0_prior_only", "K4_exact_training_roster"],
            "membership_gate": "BLOCKED",
            "release_process_state": "REDESIGN_REQUIRED",
            "release_process_effect": "BLOCKED when roster membership is protected; remove roster disclosure and reassess a newly hash-bound package",
            "public_benchmark_boundary": "the current public WildChat experiment roster is reconstructible and internal-only; K4 blocking applies to a protected-data recipient package",
        },
    ]
    for scenario in scenarios:
        scenario["contract_fragment_sha256"] = canonical_sha256(scenario["contract_fragment"])
        scenario["contract_semantics"] = "illustrative interface fragment only; a complete MRAP release contract is still required"
        scenario["coverage_complete"] = False
        scenario["untested_surfaces"] = [
            "generated-text extraction and memorization",
            "adaptive repeated queries",
            "canary extraction",
            "RAG, tools, memory, logging, and side channels",
        ]
    return {
        "design": "knowledge-profile lattice with equal-class disjoint calibration/audit membership screens over the deterministic integration subset",
        "structure": {
            "kind": "partial_order_not_monotone_numeric_levels",
            "edges": [
                ["K0_prior_only", "K1_candidate_metadata"],
                ["K0_prior_only", "K2_candidate_model_loss"],
                ["K1_candidate_metadata", "K3_metadata_plus_model_loss"],
                ["K2_candidate_model_loss", "K3_metadata_plus_model_loss"],
            ],
            "separate_direct_disclosure_channel": "K4_exact_training_roster",
        },
        "calibration_members_per_level": calibration_per_class,
        "calibration_nonmembers_per_level": calibration_per_class,
        "audit_members_per_level": audit_per_class,
        "audit_nonmembers_per_level": audit_per_class,
        "calibration_auxiliary_knowledge": "the attacker receives labelled known-member and known-nonmember calibration rows from the same constructed experiment distribution",
        "constructed_membership_prior": 0.5,
        "deployment_prior_or_ppv_estimated": False,
        "metric_resolution_and_uncertainty": f"with {audit_per_class}+{audit_per_class} audit rows, balanced accuracy moves in increments of 1/{2 * audit_per_class}; no confidence interval or deployment-population inference is claimed",
        "member_id_set_sha256": canonical_sha256(sorted(item["id"] for item in members)),
        "nonmember_id_set_sha256": canonical_sha256(sorted(item["id"] for item in nonmembers)),
        "calibration_member_ids_sha256": canonical_sha256(sorted(item["id"] for item in calibration_members)),
        "calibration_nonmember_ids_sha256": canonical_sha256(sorted(item["id"] for item in calibration_nonmembers)),
        "audit_member_ids_sha256": canonical_sha256(sorted(item["id"] for item in audit_members)),
        "audit_nonmember_ids_sha256": canonical_sha256(sorted(item["id"] for item in audit_nonmembers)),
        "raw_candidate_scores_retained": False,
        "levels": levels,
        "release_scenarios": scenarios,
        "release_contract_rule": "Changing an observable surface requires a new hash-bound release contract and reassessment unless an approved same-state, same-prior safe-reduction/garbling certificate supports the limited transfer.",
        "scope_boundary": "The observable profiles enumerate only this partial experiment. They exclude output extraction, adaptive prompting, canaries, RAG/tools/memory, and other attacks relevant even to text-only interfaces.",
        "interpretation": "Different metadata and model-observation profiles change the attack surface and which evidence is recipient-realizable; they do not form one monotone scalar ladder. These post-training screens are descriptive and non-clearing. Exact protected-roster disclosure is a separate direct leak rather than an inferred statistical result.",
    }


def compare_context_profiles(base: dict[str, Any], fine_tuned: dict[str, Any]) -> dict[str, Any]:
    partition_fields = (
        "calibration_member_ids_sha256",
        "calibration_nonmember_ids_sha256",
        "audit_member_ids_sha256",
        "audit_nonmember_ids_sha256",
    )
    _require(
        all(base[field] == fine_tuned[field] for field in partition_fields),
        "base and fine-tuned context profiles use different candidate partitions",
    )
    base_levels = {item["level"]: item for item in base["levels"]}
    final_levels = {item["level"]: item for item in fine_tuned["levels"]}
    comparisons = []
    for level_name in (
        "K0_prior_only",
        "K1_candidate_metadata",
        "K2_candidate_model_loss",
        "K3_metadata_plus_model_loss",
    ):
        before = base_levels[level_name]["result"]
        after = final_levels[level_name]["result"]
        comparisons.append({
            "level": level_name,
            "base_balanced_accuracy": before["balanced_accuracy"],
            "fine_tuned_balanced_accuracy": after["balanced_accuracy"],
            "balanced_accuracy_change": after["balanced_accuracy"] - before["balanced_accuracy"],
            "base_roc_auc": before["roc_auc"],
            "fine_tuned_roc_auc": after["roc_auc"],
            "roc_auc_change": after["roc_auc"] - before["roc_auc"],
            "interpretation": "paired descriptive sensitivity on fixed audit IDs; not a causal effect, uncertainty interval, deployment risk, or release-grade result",
        })
    return {
        "fixed_candidate_partitions_verified": True,
        "levels": comparisons,
        "interpretation": "Pre/post point estimates separate baseline content confounding from changes observed after this fine-tuning run, but refitted calibration rules, bounded 256-per-class audit cells, and no randomized control prevent causal attribution.",
    }


def model_state_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        detached = tensor.detach().cpu().contiguous()
        name_bytes = name.encode("utf-8")
        shape = canonical_json(list(detached.shape))
        dtype = str(detached.dtype).encode("ascii")
        raw = detached.numpy().tobytes(order="C")
        for component in (name_bytes, shape, dtype, raw):
            digest.update(len(component).to_bytes(8, "big"))
            digest.update(component)
    return digest.hexdigest()


def tokenizer_sha256(tokenizer: Any) -> str:
    digest = hashlib.sha256()
    for token, index in sorted(tokenizer.get_vocab().items(), key=lambda pair: (pair[1], pair[0])):
        encoded = token.encode("utf-8")
        digest.update(index.to_bytes(8, "big", signed=False))
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    digest.update(canonical_json(tokenizer.special_tokens_map))
    return digest.hexdigest()


def hook_noninterference_control(device: Any, collector_class: Any) -> dict[str, Any]:
    """Run paired tiny-model training with hooks disabled and enabled."""

    import torch

    torch.manual_seed(913)
    template = torch.nn.Sequential(
        torch.nn.Linear(4, 5),
        torch.nn.Tanh(),
        torch.nn.Linear(5, 2),
    ).to(device)
    initial_state = {name: value.detach().clone() for name, value in template.state_dict().items()}
    inputs = (torch.arange(16, dtype=torch.float32, device=device).reshape(4, 4) / 16.0).requires_grad_(True)
    targets = torch.tensor([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5], [0.25, 0.75]], device=device)

    def execute(with_hooks: bool) -> tuple[list[float], str, dict[str, Any] | None]:
        model = torch.nn.Sequential(
            torch.nn.Linear(4, 5),
            torch.nn.Tanh(),
            torch.nn.Linear(5, 2),
        ).to(device)
        model.load_state_dict(initial_state)
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01, foreach=False)
        collector = (
            collector_class(
                model,
                module_names=("0", "2"),
                expected_steps=2,
                max_events=20,
                fail_on_nonfinite=True,
            )
            if with_hooks
            else None
        )
        losses: list[float] = []

        def step(index: int) -> None:
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.mse_loss(model(inputs), targets)
            loss.backward()
            if collector is not None:
                collector.step(
                    loss,
                    step=index,
                    epoch=0,
                    batch_index=index,
                    input_tokens=int(inputs.numel()),
                    target_tokens=int(targets.numel()),
                    batch_manifest_sha256=canonical_sha256({"positive_control_step": index}),
                    duration_seconds=0.0,
                    learning_rate=0.01,
                )
            optimizer.step()
            losses.append(float(loss.detach().cpu()))

        if collector is None:
            for index in range(2):
                step(index)
            telemetry = None
        else:
            with collector:
                for index in range(2):
                    step(index)
            telemetry = collector.finalize(expected_steps=2)
        return losses, model_state_sha256(model), telemetry

    unhooked_losses, unhooked_hash, _ = execute(False)
    hooked_losses, hooked_hash, telemetry = execute(True)
    exact_loss_match = unhooked_losses == hooked_losses
    exact_state_match = unhooked_hash == hooked_hash
    _require(exact_loss_match and exact_state_match, "training hooks changed the positive-control optimization")
    assert telemetry is not None
    return {
        "design": "paired two-step deterministic tiny-model optimization from identical initial state",
        "exact_loss_trace_match": exact_loss_match,
        "exact_final_state_match": exact_state_match,
        "unhooked_loss_trace_sha256": canonical_sha256(unhooked_losses),
        "hooked_loss_trace_sha256": canonical_sha256(hooked_losses),
        "unhooked_final_state_sha256": unhooked_hash,
        "hooked_final_state_sha256": hooked_hash,
        "hook_coverage_status": telemetry["coverage_status"],
        "observed_forward_events": telemetry["observed_forward_events"],
        "observed_backward_events": telemetry["observed_backward_events"],
        "raw_values_retained": False,
        "status": "pass",
    }


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _git(command: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *command],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def runtime_report(torch: Any, transformers: Any) -> dict[str, Any]:
    gpu = "unavailable"
    driver = "unavailable"
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0 and completed.stdout.strip():
        parts = [part.strip() for part in completed.stdout.strip().split(",", 1)]
        gpu = parts[0]
        if len(parts) == 2:
            driver = parts[1]
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "pyarrow": _package_version("pyarrow"),
        "safetensors": _package_version("safetensors"),
        "cuda_available": torch.cuda.is_available(),
        "cuda_runtime": torch.version.cuda,
        "gpu": gpu,
        "gpu_driver": driver,
    }


def source_report(config_path: Path, runner_path: Path, hook_path: Path) -> dict[str, Any]:
    status = _git(["status", "--porcelain"])
    checkout_commit = _git(["rev-parse", "HEAD"])
    declared_commit = os.environ.get("MRA_SOURCE_COMMIT", "")
    if checkout_commit != "unavailable":
        repository_commit = checkout_commit
        commit_evidence = "local_git_checkout"
    elif HEX40.fullmatch(declared_commit):
        repository_commit = declared_commit
        commit_evidence = "deployment_environment_declaration_bound_with_exact_source_file_hashes"
    else:
        repository_commit = None
        commit_evidence = "unavailable"
    return {
        "repository_commit": repository_commit,
        "repository_commit_evidence": commit_evidence,
        "git_checkout_available": checkout_commit != "unavailable",
        "worktree_status_available": status != "unavailable",
        "worktree_dirty": None if status == "unavailable" else bool(status),
        "worktree_status_sha256": None if status == "unavailable" else hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "configuration_sha256": sha256_file(config_path),
        "runner_sha256": sha256_file(runner_path),
        "hook_implementation_sha256": sha256_file(hook_path),
    }


def load_verified_hook_module(hook_bytes: bytes, hook_path: Path, expected_sha256: str) -> Any:
    """Execute only the already-hashed hook bytes under a private module name."""

    observed_sha256 = hashlib.sha256(hook_bytes).hexdigest()
    _require(observed_sha256 == expected_sha256, "captured hook bytes differ from the source snapshot")
    module_name = f"_mra_verified_llm_training_hooks_{observed_sha256}_{os.getpid()}_{time.time_ns()}"
    _require(module_name not in sys.modules, "private verified hook module name is already occupied")
    module = types.ModuleType(module_name)
    module.__file__ = str(hook_path)
    module.__package__ = ""
    module.__dict__["__verified_source_sha256__"] = observed_sha256
    code = compile(hook_bytes, str(hook_path), "exec", dont_inherit=True)
    sys.modules[module_name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    collector_class = getattr(module, "AggregateTrainingHookCollector", None)
    _require(collector_class is not None, "verified hook module does not define its collector")
    _require(collector_class.__module__ == module_name, "collector identity is not the verified private module")
    return module


def verify_telemetry_events(
    events: Sequence[dict[str, Any]],
    expected_head: str,
    *,
    genesis_sha256: str = "0" * 64,
) -> dict[str, Any]:
    _require(HEX64.fullmatch(genesis_sha256) is not None, "telemetry genesis must be a SHA-256 digest")
    previous = genesis_sha256
    for sequence, event in enumerate(events):
        _require(event.get("sequence") == sequence, f"telemetry sequence mismatch at {sequence}")
        _require(event.get("previous_sha256") == previous, f"telemetry predecessor mismatch at {sequence}")
        candidate = dict(event)
        claimed = candidate.pop("event_sha256", None)
        replayed = canonical_sha256(candidate)
        _require(claimed == replayed, f"telemetry event digest mismatch at {sequence}")
        previous = replayed
    _require(previous == expected_head, "telemetry chain head mismatch")
    return {
        "verified": True,
        "events_replayed": len(events),
        "chain_head_sha256": previous,
        "chain_genesis_sha256": genesis_sha256,
        "verifier": "independent runner-side canonical JSON replay",
    }


def train_model(
    model: Any,
    items: Sequence[dict[str, Any]],
    config: dict[str, Any],
    model_config: dict[str, Any],
    telemetry_context_sha256: str,
    collector_class: Any,
    pad_token_id: int,
    device: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import torch
    training = config["training"]
    hook_config = config["hooks"]
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
        foreach=False,
        fused=False,
    )
    expected_steps = int(training["epochs"]) * math.ceil(len(items) / int(training["batch_size"]))
    collector = collector_class(
        model,
        module_names=tuple(model_config["hook_modules"]),
        expected_steps=expected_steps,
        max_events=int(hook_config["max_events"]),
        fail_on_nonfinite=bool(hook_config["fail_on_nonfinite"]),
        context_sha256=telemetry_context_sha256,
    )
    losses: list[float] = []
    instrumented_forward_backward_seconds: list[float] = []
    post_backward_collector_seal_seconds: list[float] = []
    instrumented_step_seconds: list[float] = []
    instrumented_end_to_end_step_seconds: list[float] = []
    full_step_peak_allocated_bytes: list[int] = []
    full_step_peak_reserved_bytes: list[int] = []
    step_index = 0
    model.train()
    try:
        with collector:
            for epoch in range(int(training["epochs"])):
                for batch_index, items_batch in enumerate(iter_batches(items, int(training["batch_size"]))):
                    if device.type == "cuda":
                        torch.cuda.reset_peak_memory_stats(device)
                        torch.cuda.synchronize(device)
                    batch = collate_batch(items_batch, pad_token_id, device)
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
                    duration = time.perf_counter() - started
                    loss_value = float(loss.detach().cpu())
                    collector_started = time.perf_counter()
                    collector.step(
                        step=step_index,
                        epoch=epoch,
                        batch_index=batch_index,
                        loss=loss_value,
                        model=model,
                        learning_rate=float(optimizer.param_groups[0]["lr"]),
                        input_tokens=int(batch["input_tokens"]),
                        target_tokens=int(batch["target_tokens"]),
                        truncated_records=int(batch["truncated_records"]),
                        batch_manifest_sha256=canonical_sha256(sorted(batch["record_ids"])),
                        duration_seconds=duration,
                    )
                    if device.type == "cuda":
                        torch.cuda.synchronize(device)
                    collector_duration = time.perf_counter() - collector_started
                    pre_optimizer_duration = time.perf_counter() - started
                    optimizer.step()
                    if device.type == "cuda":
                        torch.cuda.synchronize(device)
                        full_step_peak_allocated_bytes.append(int(torch.cuda.max_memory_allocated(device)))
                        full_step_peak_reserved_bytes.append(int(torch.cuda.max_memory_reserved(device)))
                    end_to_end_step_duration = time.perf_counter() - started
                    losses.append(loss_value)
                    instrumented_forward_backward_seconds.append(duration)
                    post_backward_collector_seal_seconds.append(collector_duration)
                    instrumented_step_seconds.append(pre_optimizer_duration)
                    instrumented_end_to_end_step_seconds.append(end_to_end_step_duration)
                    step_index += 1
    finally:
        collector.remove()
    hook_report = collector.finalize(expected_steps=expected_steps)
    return {
        "optimizer": "torch.optim.AdamW",
        "optimizer_steps": step_index,
        "expected_optimizer_steps": expected_steps,
        "mean_step_loss": sum(losses) / len(losses),
        "first_step_loss": losses[0],
        "final_step_loss": losses[-1],
        "loss_trace_sha256": canonical_sha256(losses),
        "loss_trace_retained": False,
        "timing": {
            "instrumented_forward_backward_total_seconds": sum(instrumented_forward_backward_seconds),
            "post_backward_collector_seal_total_seconds": sum(post_backward_collector_seal_seconds),
            "instrumented_pre_optimizer_total_seconds": sum(instrumented_step_seconds),
            "instrumented_end_to_end_step_total_seconds": sum(instrumented_end_to_end_step_seconds),
            "mean_instrumented_forward_backward_seconds": sum(instrumented_forward_backward_seconds) / len(instrumented_forward_backward_seconds),
            "mean_post_backward_collector_seal_seconds": sum(post_backward_collector_seal_seconds) / len(post_backward_collector_seal_seconds),
            "mean_instrumented_end_to_end_step_seconds": sum(instrumented_end_to_end_step_seconds) / len(instrumented_end_to_end_step_seconds),
            "event_duration_field_semantics": "instrumented forward and backward including synchronous per-module hook reductions; excludes the later whole-model parameter-gradient scan, event seal, and optimizer step",
            "post_backward_semantics": "whole-model parameter-gradient aggregation plus scalar event sealing after backward and before the optimizer step",
            "comparison_semantics": "descriptive timing from one instrumented run; neither component is an uninstrumented baseline or a causal overhead estimate",
        },
        "memory": {
            "full_step_peak_allocated_bytes": max(full_step_peak_allocated_bytes, default=0),
            "full_step_peak_reserved_bytes": max(full_step_peak_reserved_bytes, default=0),
            "measurement_window": "per-step reset before batch collation through synchronized optimizer completion",
        },
    }, hook_report


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial-{os.getpid()}")
    _require(not partial.exists(), f"artifact staging path already exists: {partial}")
    published = False
    try:
        with partial.open("xb") as stream:
            os.chmod(partial, 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(partial, path)
        except FileExistsError as exc:
            raise ValueError(f"refusing to overwrite experiment artifact: {path}") from exc
        published = True
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if partial.exists():
            partial.unlink()
            if published:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)


def _atomic_write_text(path: Path, value: str) -> None:
    _atomic_write_bytes(path, value.encode("utf-8"))


def _prepare_fresh_output_dir(path: Path) -> None:
    if path.exists():
        _require(path.is_dir(), f"output path is not a directory: {path}")
        _require(not any(path.iterdir()), f"output run directory is not fresh: {path}")
        os.chmod(path, 0o700)
    else:
        path.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(path, 0o700)


def require_disjoint_run_and_cache_paths(output_dir: Path, cache_dir: Path) -> None:
    """Reject either containment direction between governed run and cache roots."""

    resolved_output = output_dir.resolve()
    resolved_cache = cache_dir.resolve()

    def contains(parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    _require(
        not contains(resolved_output, resolved_cache)
        and not contains(resolved_cache, resolved_output),
        "run output and immutable cache paths must be disjoint siblings, not equal or nested",
    )


def model_cache_manifest(path: Path) -> dict[str, Any]:
    files = []
    for candidate in sorted(path.rglob("*")):
        if not candidate.is_file() or candidate.name.endswith((".lock", ".partial", ".incomplete")):
            continue
        files.append({
            "path": candidate.relative_to(path).as_posix(),
            "bytes": candidate.stat().st_size,
            "sha256": sha256_file(candidate),
        })
    _require(bool(files), f"model cache has no immutable files: {path}")
    return {
        "files": files,
        "file_count": len(files),
        "total_file_bytes_including_snapshot_links": sum(item["bytes"] for item in files),
        "manifest_sha256": canonical_sha256(files),
    }


def download_verified_model_snapshot(
    model_config: dict[str, Any],
    cache_dir: Path,
    *,
    offline: bool,
) -> tuple[Path, dict[str, Any]]:
    snapshot = cache_dir / "model" / model_config["key"] / f"verified-{model_config['revision']}"
    registered = []
    for artifact in model_config["artifacts"]:
        relative = Path(artifact["file"])
        _require(
            not relative.is_absolute() and ".." not in relative.parts and len(relative.parts) >= 1,
            "model artifact path must remain inside its verified snapshot",
        )
        destination = snapshot / relative
        _download_verified_object(
            MODEL_URL.format(
                model_id=model_config["id"],
                revision=model_config["revision"],
                file=artifact["file"],
            ),
            destination,
            expected_sha256=artifact["sha256"],
            expected_bytes=int(artifact["bytes"]),
            offline=offline,
            timeout_seconds=180,
        )
        registered.append({
            "path": artifact["file"],
            "bytes": int(artifact["bytes"]),
            "sha256": artifact["sha256"],
        })
    actual = model_cache_manifest(snapshot)
    expected = sorted(registered, key=lambda item: item["path"])
    _require(actual["files"] == expected, f"verified model snapshot differs from registry: {model_config['key']}")
    actual["verified_before_load"] = True
    actual["registered_manifest_sha256"] = canonical_sha256(expected)
    return snapshot, actual


def _selected_metadata_report(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    languages: dict[str, int] = {}
    source_models: dict[str, int] = {}
    character_counts = []
    turn_counts = []
    for item in records:
        languages[item["source_language"]] = languages.get(item["source_language"], 0) + 1
        source_models[item["source_model"]] = source_models.get(item["source_model"], 0) + 1
        character_counts.append(len(item["user"]) + len(item["assistant"]))
        turn_counts.append(int(item["source_turn_count"]))
    return {
        "language_counts": dict(sorted(languages.items())),
        "upstream_response_model_counts": dict(sorted(source_models.items())),
        "first_pair_character_count": _integer_distribution(character_counts),
        "source_conversation_turn_count": _integer_distribution(turn_counts),
        "raw_text_retained": False,
    }


def _model_release_route(model_config: dict[str, Any]) -> dict[str, Any]:
    legal_gate = model_config.get("legal_production_commercial_gate", "LEGAL_REVIEW_REQUIRED")
    policy_gate = model_config.get("human_facing_deployment_policy_gate", "MANUAL_REVIEW_REQUIRED")
    state = "BLOCKED" if legal_gate == "BLOCKED" else "ASSESSMENT_INCOMPLETE"
    return {
        "release_process_state": state,
        "model_license_gate": legal_gate,
        "model_use_policy_gate": policy_gate,
        "dataset_content_rights_gate": "LEGAL_REVIEW_REQUIRED",
        "dataset_content_rights_reason": "ODC-By governs the database and does not itself clear rights in individual conversation contents or provider outputs",
        "can_clear": False,
        "decision": "no_release_authorization",
    }


def _telemetry_scalability(
    events: Sequence[dict[str, Any]],
    train_rows: int,
    wall_seconds: float,
    training_memory: dict[str, Any],
) -> dict[str, Any]:
    step_events = [event for event in events if event.get("event_type") == "step"]
    input_tokens = sum(int(event.get("tokens", 0)) for event in step_events)
    target_tokens = sum(int(event.get("target_tokens", 0)) for event in step_events)
    pre_optimizer_peak_allocated = max(
        (int(event.get("gpu_memory", {}).get("peak_allocated_bytes", 0)) for event in step_events),
        default=0,
    )
    pre_optimizer_peak_reserved = max(
        (int(event.get("gpu_memory", {}).get("peak_reserved_bytes", 0)) for event in step_events),
        default=0,
    )
    return {
        "training_wall_seconds": wall_seconds,
        "training_rows": train_rows,
        "input_tokens_seen": input_tokens,
        "target_tokens_seen": target_tokens,
        "rows_per_second": train_rows / wall_seconds,
        "input_tokens_per_second": input_tokens / wall_seconds,
        "pre_optimizer_event_peak_allocated_bytes": pre_optimizer_peak_allocated,
        "pre_optimizer_event_peak_reserved_bytes": pre_optimizer_peak_reserved,
        "full_step_peak_allocated_bytes": int(training_memory["full_step_peak_allocated_bytes"]),
        "full_step_peak_reserved_bytes": int(training_memory["full_step_peak_reserved_bytes"]),
        "memory_measurement_window": training_memory["measurement_window"],
        "semantics": "single instrumented sequential run; full-step memory includes synchronized optimizer completion, while event peaks stop at event sealing; descriptive capacity evidence, not an uninstrumented overhead benchmark",
    }


def _run_one_model(
    model_config: dict[str, Any],
    train_records: Sequence[dict[str, Any]],
    holdout_records: Sequence[dict[str, Any]],
    config: dict[str, Any],
    cache_dir: Path,
    output_dir: Path,
    *,
    offline: bool,
    device: Any,
    torch: Any,
    collector_class: Any,
    executed_hook_sha256: str,
    runner_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_snapshot, cache_manifest = download_verified_model_snapshot(
        model_config,
        cache_dir,
        offline=offline,
    )
    load_options = {"local_files_only": True, "trust_remote_code": False, "token": False}
    tokenizer = AutoTokenizer.from_pretrained(str(model_snapshot), **load_options)
    if tokenizer.pad_token_id is None:
        _require(tokenizer.eos_token_id is not None, "tokenizer has neither pad nor EOS token")
        tokenizer.pad_token = tokenizer.eos_token
    model_options = {
        **load_options,
        "use_safetensors": bool(model_config["use_safetensors"]),
        "torch_dtype": torch.float32,
    }
    if model_config.get("weights_only") is True:
        model_options["weights_only"] = True
    model = AutoModelForCausalLM.from_pretrained(str(model_snapshot), **model_options)
    model.config.use_cache = False
    model.config.pad_token_id = int(tokenizer.pad_token_id)
    if hasattr(model, "gradient_checkpointing_disable"):
        model.gradient_checkpointing_disable()
    model.to(device)

    token_config = config["training"]
    pretokenization_bounds = token_config["pretokenization_bounds"]
    batch_size = int(token_config["batch_size"])
    train_items, train_tokenization = tokenize_records(
        train_records,
        tokenizer,
        max_length=int(token_config["max_sequence_length"]),
        max_prompt_length=int(token_config["max_prompt_length"]),
        max_field_utf8_bytes=int(pretokenization_bounds["max_field_utf8_bytes"]),
        max_record_utf8_bytes=int(pretokenization_bounds["max_record_utf8_bytes"]),
    )
    holdout_items, holdout_tokenization = tokenize_records(
        holdout_records,
        tokenizer,
        max_length=int(token_config["max_sequence_length"]),
        max_prompt_length=int(token_config["max_prompt_length"]),
        max_field_utf8_bytes=int(pretokenization_bounds["max_field_utf8_bytes"]),
        max_record_utf8_bytes=int(pretokenization_bounds["max_record_utf8_bytes"]),
    )
    base_model_hash = model_state_sha256(model)
    tokenizer_hash = tokenizer_sha256(tokenizer)
    base_eval = evaluate(model, holdout_items, batch_size, int(tokenizer.pad_token_id), device)
    base_train_metrics = per_example_loss_metrics(
        model, train_items, int(tokenizer.pad_token_id), device, batch_size=batch_size
    )
    base_holdout_metrics = per_example_loss_metrics(
        model, holdout_items, int(tokenizer.pad_token_id), device, batch_size=batch_size
    )
    context_config = config["context_risk_ladder"]
    context_args = {
        "seed": int(config["dataset"]["seed"]),
        "calibration_per_class": int(context_config["calibration_per_class"]),
        "audit_per_class": int(context_config["audit_per_class"]),
    }
    base_context = build_context_risk_ladder(base_train_metrics, base_holdout_metrics, **context_args)
    telemetry_context = {
        "schema_version": "1.0",
        "experiment_id": config["experiment_id"],
        "run_directory_name": output_dir.name,
        "configuration_canonical_sha256": canonical_sha256(config),
        "runner_sha256": runner_sha256,
        "hook_implementation_sha256": executed_hook_sha256,
        "hook_module_identity": collector_class.__module__,
        "dataset_id": config["dataset"]["id"],
        "dataset_revision": config["dataset"]["revision"],
        "dataset_file_sha256": config["dataset"]["sha256"],
        "train_record_ids_sha256": canonical_sha256([item["id"] for item in train_records]),
        "holdout_record_ids_sha256": canonical_sha256([item["id"] for item in holdout_records]),
        "model_key": model_config["key"],
        "model_id": model_config["id"],
        "model_revision": model_config["revision"],
        "base_model_state_sha256": base_model_hash,
        "tokenizer_sha256": tokenizer_hash,
        "model_cache_manifest_sha256": cache_manifest["manifest_sha256"],
    }
    telemetry_context_sha256 = canonical_sha256(telemetry_context)

    training_seed = int(config["training"]["seed"])
    torch.manual_seed(training_seed)
    torch.cuda.manual_seed_all(training_seed)
    training_started = time.perf_counter()
    training_report, telemetry = train_model(
        model,
        train_items,
        config,
        model_config,
        telemetry_context_sha256,
        collector_class,
        int(tokenizer.pad_token_id),
        device,
    )
    torch.cuda.synchronize(device)
    training_wall_seconds = time.perf_counter() - training_started
    final_eval = evaluate(model, holdout_items, batch_size, int(tokenizer.pad_token_id), device)
    final_train_metrics = per_example_loss_metrics(
        model, train_items, int(tokenizer.pad_token_id), device, batch_size=batch_size
    )
    final_holdout_metrics = per_example_loss_metrics(
        model, holdout_items, int(tokenizer.pad_token_id), device, batch_size=batch_size
    )
    final_context = build_context_risk_ladder(final_train_metrics, final_holdout_metrics, **context_args)
    context_comparison = compare_context_profiles(base_context, final_context)
    final_model_hash = model_state_sha256(model)
    final_cache_manifest = model_cache_manifest(model_snapshot)

    _require(base_model_hash != final_model_hash, f"training did not change model state: {model_config['key']}")
    _require(
        final_cache_manifest["manifest_sha256"] == cache_manifest["manifest_sha256"],
        f"verified model snapshot changed during execution: {model_config['key']}",
    )
    _require(telemetry["coverage_status"] == "complete", f"hook coverage is incomplete: {model_config['key']}")
    _require(telemetry["nonfinite_elements"] == 0, f"non-finite telemetry observed: {model_config['key']}")
    events = telemetry.pop("events")
    telemetry["independent_replay"] = verify_telemetry_events(
        events,
        telemetry["event_chain_head_sha256"],
        genesis_sha256=telemetry["event_chain_genesis_sha256"],
    )
    _require(telemetry["event_chain_genesis_sha256"] == telemetry_context_sha256, "telemetry context binding mismatch")
    telemetry["scalability"] = _telemetry_scalability(
        events,
        len(train_items),
        training_wall_seconds,
        training_report["memory"],
    )
    telemetry_name = config["output"]["telemetry_pattern"].format(model_key=model_config["key"])
    telemetry_path = output_dir / telemetry_name
    _atomic_write_text(
        telemetry_path,
        "".join(canonical_json(event).decode("utf-8") + "\n" for event in events),
    )
    telemetry["event_stream"] = {
        "path": telemetry_path.name,
        "format": "canonical JSON Lines",
        "sha256": sha256_file(telemetry_path),
        "bytes": telemetry_path.stat().st_size,
        "file_mode": oct(telemetry_path.stat().st_mode & 0o777),
        "events": len(events),
        "embedded_in_report": False,
    }
    model_result = {
        "key": model_config["key"],
        "kind": "causal_language_model",
        "model_id": model_config["id"],
        "revision": model_config["revision"],
        "owner": model_config["owner"],
        "license": model_config["license"],
        "governance_sources": {
            "model_card_url": model_config.get("model_card_url"),
            "license_url": model_config.get("license_url"),
            "bound_artifacts": [
                {
                    "file": artifact["file"],
                    "bytes": artifact["bytes"],
                    "sha256": artifact["sha256"],
                }
                for artifact in model_config["artifacts"]
                if artifact["role"] == "governance"
            ],
            "semantics": "source-declared metadata bound byte-for-byte; no legal interpretation or rights grant",
        },
        "loader_security": {
            "trust_remote_code": False,
            "credential_token_forwarded": False,
            "use_safetensors": bool(model_config["use_safetensors"]),
            "weights_only": bool(model_config.get("weights_only", False)),
            "pinned_revision": True,
            "bounded_artifacts_verified_before_load": True,
            "loader_network_access_disabled_by_local_files_only": True,
            "os_network_namespace_isolated_during_load": False,
        },
        "cache_manifest": cache_manifest,
        "parameters": {
            "total": sum(int(parameter.numel()) for parameter in model.parameters()),
            "trainable": sum(int(parameter.numel()) for parameter in model.parameters() if parameter.requires_grad),
        },
        "base_state_sha256": base_model_hash,
        "final_state_sha256": final_model_hash,
        "tokenizer_sha256": tokenizer_hash,
        "tokenization": {"train": train_tokenization, "holdout": holdout_tokenization},
        "base_holdout": base_eval,
        "final_holdout": final_eval,
        "training": {
            **config["training"],
            **training_report,
            "effective_training_seed": training_seed,
            "loss_masking": "assistant/completion tokens only",
            "packing": False,
            "gradient_checkpointing": False,
            "torch_compile": False,
        },
        "telemetry": telemetry,
        "telemetry_context": telemetry_context,
        "telemetry_context_sha256": telemetry_context_sha256,
        "knowledge_profiles": {
            "before_training": base_context,
            "after_training": final_context,
            "paired_comparison": context_comparison,
        },
        "release_route": _model_release_route(model_config),
        "state_changed": True,
        "artifact_persisted": False,
        "can_clear": False,
    }
    artifact = {
        "path": telemetry_path.name,
        "sha256": sha256_file(telemetry_path),
        "bytes": telemetry_path.stat().st_size,
        "file_mode": oct(telemetry_path.stat().st_mode & 0o777),
        "classification": "aggregate experimental training telemetry; no raw tensors, tokens, or dialogue text",
    }
    del model, tokenizer, train_items, holdout_items
    gc.collect()
    torch.cuda.empty_cache()
    return model_result, artifact


def _metric(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.3f}"


def build_markdown_report(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    lines = [
        "# LLM training-hook end-to-end test report",
        "",
        f"- Execution: **{report['execution']['status']}**",
        f"- Operational verdict: **{report['execution']['test_verdict']}**",
        "- Release decision: **no release authorization**",
        f"- Runtime: {report['runtime']['gpu']} / CUDA {report['runtime']['cuda_runtime']}",
        f"- Real dataset: `{dataset['id']}` at `{dataset['revision']}`",
        f"- Source scale: {dataset['source_scale']['dataset_conversations']:,} conversations; verified shard {dataset['upstream_rows']:,} rows / {dataset['file_bytes']:,} bytes",
        f"- Shared workload: {dataset['selected_rows']:,} rows ({dataset['train_rows']:,} train, {dataset['holdout_rows']:,} holdout)",
        "",
        "## Three-model training matrix",
        "",
        "| Model | Parameters | Base NLL / PPL | Final NLL / PPL | Steps | Rows/s | Hook coverage | Release route |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for model in report["models"]:
        lines.append(
            f"| `{model['model_id']}` | {model['parameters']['total']:,} | "
            f"{model['base_holdout']['mean_target_token_nll']:.4f} / {model['base_holdout']['perplexity']:.2f} | "
            f"{model['final_holdout']['mean_target_token_nll']:.4f} / {model['final_holdout']['perplexity']:.2f} | "
            f"{model['training']['optimizer_steps']} | {model['telemetry']['scalability']['rows_per_second']:.2f} | "
            f"{model['telemetry']['coverage_status']} | {model['release_route']['release_process_state']} |"
        )
    lines.extend([
        "",
        "Every model started from its own pinned upstream checkpoint and used the same deterministic row split. Cross-model differences are descriptive; they are not randomized causal effects.",
        "",
        "## Metadata and model-context risk",
        "",
        "The same fixed calibration and audit IDs were evaluated before and after fine-tuning. K0–K3 are descriptive membership screens; K4 is a logical disclosure rule, not a measured classifier.",
        "",
        "| Model | Knowledge profile | Before BA / AUC | After BA / AUC | Release-process meaning |",
        "|---|---|---:|---:|---|",
    ])
    for model in report["models"]:
        before_levels = {item["level"]: item for item in model["knowledge_profiles"]["before_training"]["levels"]}
        after_levels = {item["level"]: item for item in model["knowledge_profiles"]["after_training"]["levels"]}
        for level_name in (
            "K0_prior_only",
            "K1_candidate_metadata",
            "K2_candidate_model_loss",
            "K3_metadata_plus_model_loss",
            "K4_exact_training_roster",
        ):
            before = before_levels[level_name]
            after = after_levels[level_name]
            lines.append(
                f"| `{model['key']}` | `{level_name}` | "
                f"{_metric(before['result']['balanced_accuracy'])} / {_metric(before['result']['roc_auc'])} | "
                f"{_metric(after['result']['balanced_accuracy'])} / {_metric(after['result']['roc_auc'])} | "
                f"{after['release_route']} |"
            )
    lines.extend([
        "",
        "K1 can be realized only when candidate preprocessing and source metadata are known. K2/K3 require arbitrary-candidate loss or equivalent log-probability access, so they do not describe a text-only interface. If a package discloses an authenticated protected training roster, K4 blocks the membership gate and requires redesign regardless of K0–K3 point estimates.",
        "",
        "## Data handling and legal boundary",
        "",
        "The in-memory Parquet projection excluded IP hashes, geography, request headers, timestamps, OpenAI request IDs, and moderation payloads before selection. Reports and telemetry retain no dialogue text, token IDs, logits, activations, or gradients. Offline replay does retain the complete verified source Parquet—including excluded columns—in a mode-0600 file under a mode-0700 cache; it requires an explicit retention/deletion policy and must never enter a recipient package. The internal report also retains the public experiment roster for replay.",
        "",
        "WildChat is real human-user/ChatGPT interaction data, not synthetic instruction generation. Its ODC-By database license does not by itself clear rights in individual contents or provider outputs. Legal/provider-output review therefore remains required. Meta OPT-125M additionally has a non-commercial research-only model license, so its production/commercial route is blocked.",
        "",
        "## Interpretation",
        "",
        "This run tests pinned acquisition, real completion-only fine-tuning, before/after holdout evaluation, and exact training-time activation and gradient coverage at a non-toy workload. It does not establish external generalization, privacy, fairness, robustness, content safety, legal clearance, or production scalability. The holdout comes from the same upstream train split; the risk screens are not powered release criteria; throughput is from one instrumented GPU run without an uninstrumented baseline.",
        "",
        "This experimental report is not an MRAP assessment input and cannot clear a release contract. The decision is unconditionally `no_release_authorization`.",
        "",
    ])
    return "\n".join(lines)


def run(config_path: Path, output_dir: Path, cache_dir: Path, *, offline: bool) -> dict[str, Any]:
    require_disjoint_run_and_cache_paths(output_dir, cache_dir)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    import transformers

    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    runner_path = Path(__file__).resolve()
    hook_path = ROOT / "scripts" / "llm_training_hooks.py"
    _require(config_path.is_file() and config_path.stat().st_size <= MAX_CONFIG_BYTES, "configuration exceeds its byte bound")
    _require(hook_path.is_file() and hook_path.stat().st_size <= MAX_HOOK_SOURCE_BYTES, "hook source exceeds its byte bound")
    config_bytes = config_path.read_bytes()
    hook_bytes = hook_path.read_bytes()
    source_start = source_report(config_path, runner_path, hook_path)
    _require(
        hashlib.sha256(config_bytes).hexdigest() == source_start["configuration_sha256"],
        "configuration changed while its start snapshot was read",
    )
    _require(
        hashlib.sha256(hook_bytes).hexdigest() == source_start["hook_implementation_sha256"],
        "hook implementation changed while its start snapshot was read",
    )
    verified_hook_module = load_verified_hook_module(
        hook_bytes,
        hook_path,
        source_start["hook_implementation_sha256"],
    )
    collector_class = verified_hook_module.AggregateTrainingHookCollector
    raw_config = json.loads(config_bytes.decode("utf-8"))
    _require(isinstance(raw_config, dict), "configuration must be a JSON object")
    config = validate_config(raw_config)
    _prepare_fresh_output_dir(output_dir)
    if not torch.cuda.is_available():
        raise RuntimeError("the registered EC2 integration profile requires CUDA")

    training_seed = int(config["training"]["seed"])
    torch.manual_seed(training_seed)
    torch.cuda.manual_seed_all(training_seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda")

    catalog_path = download_verified_catalog(config, cache_dir / "catalog", offline=offline)
    catalog_text = catalog_path.read_text(encoding="utf-8")
    _require(config["dataset"]["id"] in catalog_text, "pinned catalog does not contain the configured dataset entry")
    dataset_governance_paths = download_verified_dataset_governance(
        config,
        cache_dir / "dataset-governance",
        offline=offline,
    )
    dataset_path = download_verified_dataset(config, cache_dir / "dataset", offline=offline)
    raw_rows = load_dataset_rows(dataset_path)
    upstream_row_count = len(raw_rows)
    records, adapter_report = extract_wildchat_records(raw_rows)
    source_scale = config["dataset"]["source_scale"]
    _require(upstream_row_count == int(source_scale["selected_shard_rows"]), "Parquet row count differs from the registry")
    _require(
        adapter_report["eligible_before_deduplication"]
        == int(source_scale["selected_shard_eligible_before_deduplication"]),
        "eligible pre-deduplication count differs from the registry",
    )
    _require(
        adapter_report["eligible_after_deduplication"]
        == int(source_scale["selected_shard_eligible_after_deduplication"]),
        "eligible post-deduplication count differs from the registry",
    )
    del raw_rows
    gc.collect()
    row_config = config["dataset"]["rows"]
    eligible_pool_count = len(records)
    train_records, holdout_records = select_records(
        records,
        int(config["dataset"]["seed"]),
        int(row_config["total"]),
        int(row_config["train"]),
    )
    del records
    gc.collect()
    selected_records = [*train_records, *holdout_records]
    selected_row_count = len(selected_records)
    selected_ids = [item["id"] for item in selected_records]
    split_integrity = validate_content_disjointness(train_records, holdout_records)
    risks = scan_dataset_risks(selected_records)
    metadata_report = _selected_metadata_report(selected_records)
    del selected_records
    noninterference = hook_noninterference_control(device, collector_class)
    print(
        f"dataset ready: {len(train_records)} train / {len(holdout_records)} holdout; "
        f"eligible pool {eligible_pool_count}",
        file=sys.stderr,
        flush=True,
    )

    models = []
    artifacts = []
    for model_config in config["models"]:
        print(f"starting model: {model_config['key']}", file=sys.stderr, flush=True)
        model_result, artifact = _run_one_model(
            model_config,
            train_records,
            holdout_records,
            config,
            cache_dir,
            output_dir,
            offline=offline,
            device=device,
            torch=torch,
            collector_class=collector_class,
            executed_hook_sha256=source_start["hook_implementation_sha256"],
            runner_sha256=source_start["runner_sha256"],
        )
        models.append(model_result)
        artifacts.append(artifact)
        print(
            f"completed model: {model_config['key']} "
            f"({model_result['training']['optimizer_steps']} optimizer steps)",
            file=sys.stderr,
            flush=True,
        )

    immutable_source_fields = ("configuration_sha256", "runner_sha256", "hook_implementation_sha256")
    matched_categories = sum(
        isinstance(value, dict) and int(value.get("record_count", 0)) > 0
        for value in risks.values()
    )
    telemetry_summary = {
        "models": len(models),
        "all_coverage_complete": all(model["telemetry"]["coverage_status"] == "complete" for model in models),
        "total_observed_forward_events": sum(model["telemetry"]["observed_forward_events"] for model in models),
        "total_observed_backward_events": sum(model["telemetry"]["observed_backward_events"] for model in models),
        "total_nonfinite_elements": sum(model["telemetry"]["nonfinite_elements"] for model in models),
    }
    report: dict[str, Any] = {
        "schema_version": "1.1",
        "report_type": "experimental_llm_training_hook_matrix",
        "experiment_id": config["experiment_id"],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "experimental_only": True,
        "authorization_eligible": False,
        "assessment_input_emitted": False,
        "can_clear": False,
        "evidence_semantics": "empirical_real_data_training_integration_and_descriptive_screens_never_clear",
        "decision": "no_release_authorization",
        "artifact_handling": {
            "classification": "internal experimental audit artifact over public real-world conversation data",
            "include_in_recipient_release_package": False,
            "roster_confidentiality_provided": False,
            "suitable_for_protected_training_data_without_redesign": False,
            "reason": "public selection IDs, seed, algorithm, and unsalted batch commitments prioritize replay and make the experiment roster reconstructible",
            "run_directory_mode": oct(output_dir.stat().st_mode & 0o777),
            "artifact_file_mode": "0o600",
        },
        "execution": {"status": "completed", "test_verdict": "passed", "failure_reasons": []},
        "source_provenance": {
            "start": source_start,
            "executed_hook_module": {
                "private_module_name": collector_class.__module__,
                "executed_source_sha256": source_start["hook_implementation_sha256"],
                "loaded_from_captured_verified_bytes": True,
                "ambient_llm_training_hooks_module_used": False,
            },
        },
        "catalog": {
            **config["catalog"],
            "resolved_readme_sha256": sha256_file(catalog_path),
            "configured_dataset_entry_found": True,
        },
        "runtime": runtime_report(torch, transformers),
        "acquisition": {
            "mode": "offline_cache_only" if offline else "online_fetch_with_digest_verification",
            "dataset_remote_code_executed": False,
            "model_remote_code_executed": False,
            "bounded_dataset_catalog_governance_and_model_downloads": True,
        },
        "dataset": {
            "id": config["dataset"]["id"],
            "revision": config["dataset"]["revision"],
            "file": config["dataset"]["file"],
            "file_sha256": sha256_file(dataset_path),
            "file_bytes": dataset_path.stat().st_size,
            "license": config["dataset"]["license"],
            "governance_sources": {
                "dataset_card": {
                    **config["dataset"]["governance_sources"]["dataset_card"],
                    "resolved_sha256": sha256_file(dataset_governance_paths["dataset_card"]),
                },
                "license_file": {
                    **config["dataset"]["governance_sources"]["license_file"],
                    "resolved_sha256": sha256_file(dataset_governance_paths["license_file"]),
                },
                "dataset_card_license_declaration": config["dataset"]["governance_sources"]["dataset_card_license_declaration"],
                "content_rights_cleared": False,
                "semantics": "source-declared database-license metadata bound byte-for-byte; no legal interpretation or individual-content rights grant",
            },
            "content_rights_cleared_by_database_license": False,
            "content_rights_gate": "LEGAL_REVIEW_REQUIRED",
            "membership_is_protected_secret_in_this_experiment": False,
            "loader": "direct_parquet_leaf_projection",
            "projected_columns": config["dataset"]["projected_columns"],
            "excluded_sensitive_columns": config["dataset"]["excluded_sensitive_columns"],
            "remote_code_executed": False,
            "source_scale": config["dataset"]["source_scale"],
            "upstream_rows": upstream_row_count,
            "adapter": adapter_report,
            "selected_rows": selected_row_count,
            "train_rows": len(train_records),
            "holdout_rows": len(holdout_records),
            "selection_algorithm": config["dataset"]["selection_algorithm"],
            "selection_seed": config["dataset"]["seed"],
            "selected_record_ids": sorted(selected_ids),
            "selected_record_ids_sha256": canonical_sha256(sorted(selected_ids)),
            "train_record_ids_sha256": canonical_sha256([item["id"] for item in train_records]),
            "holdout_record_ids_sha256": canonical_sha256([item["id"] for item in holdout_records]),
            "split_overlap_count": len(set(item["id"] for item in train_records) & set(item["id"] for item in holdout_records)),
            "content_split_integrity": split_integrity,
            "selected_metadata": metadata_report,
            "origin": "organic conversations between human users and ChatGPT according to the dataset card; assistant responses are model-generated, not human-authored",
            "deidentification_claim_semantics": "upstream detector/process claim, not a guarantee; this experiment additionally excludes redacted rows and sensitive metadata columns",
            "holdout_semantics": "deterministic internal holdout from an upstream train split; pipeline regression and descriptive risk screen only",
            "raw_source_cache": {
                "registered_policy": config["dataset"]["cache_policy"],
                "retained_for_offline_replay": True,
                "contains_raw_dialogue_text": True,
                "contains_sensitive_columns_excluded_from_in_memory_projection": True,
                "sha256": sha256_file(dataset_path),
                "bytes": dataset_path.stat().st_size,
                "file_mode": oct(dataset_path.stat().st_mode & 0o777),
                "directory_mode": oct(dataset_path.parent.stat().st_mode & 0o777),
                "path_disclosed_in_report": False,
                "recipient_package_inclusion": False,
                "retention_requirement": "operator-defined access, retention, deletion, and legal-hold policy required; delete the cache when offline replay is no longer needed",
            },
        },
        "model_matrix": config["model_matrix"],
        "output_contract": config["output"],
        "publication_contract": {
            "artifact_set_complete_only_when_manifest_present": True,
            "completion_manifest": config["output"]["completion_manifest"],
            "publication_order": ["telemetry", "json_report", "markdown_report", "completion_manifest"],
            "incomplete_directory_semantics": "invalid experiment publication; ignore any passed status unless the completion manifest validates every required artifact",
        },
        "hook_noninterference_control": noninterference,
        "telemetry_summary": telemetry_summary,
        "models": models,
        "release_interface_contracts": models[0]["knowledge_profiles"]["after_training"]["release_scenarios"],
        "red_team": {
            "dataset_preflight": risks,
            "matched_category_count": matched_categories,
            "nonfinite_alarm": telemetry_summary["total_nonfinite_elements"] > 0,
            "training_hook_stability_check": "run_all_models",
            "context_conditioned_membership_screen": "run_before_and_after_training_all_models",
            "scope": "heuristic content triage, training-stability instrumentation, and descriptive membership screens",
            "can_block_release": False,
            "can_clear": False,
            "canary_extraction": "not_run; requires separate preregistration and sealed assignment",
            "generated_output_extraction": "not_run; requires a registered recipient query interface and attack budget",
            "watermark_detection": "not_run; separate output-provenance experiment",
        },
        "data_minimization": {
            "raw_prompts_or_responses_retained_in_report_or_telemetry": False,
            "raw_source_dataset_cache_retained": True,
            "sensitive_upstream_metadata_present_in_raw_cache": True,
            "token_ids_or_labels_retained": False,
            "logits_retained": False,
            "raw_activations_retained": False,
            "raw_gradients_retained": False,
            "sensitive_upstream_metadata_loaded_into_arrow_training_table": False,
            "public_opaque_record_ids_retained_for_replay": True,
            "training_roster_confidentiality": "not provided; internal public-data replay artifact",
            "production_requirement": "exclude the report and telemetry from recipient packages and redesign commitments before any protected-data use",
        },
        "artifact_manifest": artifacts,
        "limitations": [
            "The 8,192-row, one-epoch workload is a scalability observation, not a training-adequacy or production-capacity study.",
            "The 1,024-row holdout is carved from an upstream train split and does not establish external generalization.",
            "Only small causal LMs and one NVIDIA L4 runtime are tested.",
            "No powered or release-eligible membership guarantee is evaluated; membership results are descriptive screens on a constructed equal prior.",
            "Generated-output extraction, canary, watermark, prompt/RAG/tool, fairness, robustness, legal, and differential-privacy claims are not evaluated.",
            "Upstream moderation, deidentification, and secret scans are not guarantees; heuristic experiment scans are triage only.",
            "Aggregate hooks observe two selected blocks and all parameter gradients; they do not attest a production telemetry or serving system.",
        ],
    }
    _require(telemetry_summary["all_coverage_complete"], "not all model hook coverage is complete")
    _require(telemetry_summary["total_nonfinite_elements"] == 0, "matrix observed non-finite telemetry")
    _require(
        dataset_path.stat().st_size == int(config["dataset"]["bytes"])
        and sha256_file(dataset_path) == config["dataset"]["sha256"],
        "dataset cache changed after acquisition",
    )
    _require(
        catalog_path.stat().st_size == int(config["catalog"]["readme_bytes"])
        and sha256_file(catalog_path) == config["catalog"]["readme_sha256"],
        "catalog cache changed after acquisition",
    )
    for governance_key, governance_path in dataset_governance_paths.items():
        registered_source = config["dataset"]["governance_sources"][governance_key]
        _require(
            governance_path.stat().st_size == int(registered_source["bytes"])
            and sha256_file(governance_path) == registered_source["sha256"],
            f"dataset governance cache changed after acquisition: {governance_key}",
        )
    _require(dataset_path.stat().st_mode & 0o077 == 0, "raw dataset cache permissions are too broad")
    _require(dataset_path.parent.stat().st_mode & 0o077 == 0, "raw dataset cache directory permissions are too broad")
    source_end = source_report(config_path, runner_path, hook_path)
    _require(
        all(source_start[field] == source_end[field] for field in immutable_source_fields),
        "configuration or executable source changed during the experiment",
    )
    report["source_provenance"]["end"] = source_end
    report["source_provenance"]["immutable_source_files_unchanged"] = True
    report["report_body_sha256"] = canonical_sha256(report)
    return report


def verify_registered_artifact_entries(
    output_dir: Path,
    required_artifacts: Sequence[dict[str, Any]],
    *,
    completion_manifest_name: str | None,
) -> None:
    """Require an exact flat set of regular files and re-hash every payload."""

    required_names = {str(item["path"]) for item in required_artifacts}
    expected_names = required_names | (
        {completion_manifest_name} if completion_manifest_name is not None else set()
    )
    entries = list(output_dir.iterdir())
    _require(
        {path.name for path in entries} == expected_names,
        "published artifact set contains an unexpected or missing entry",
    )
    _require(
        all(path.is_file() and not path.is_symlink() for path in entries),
        "published artifact set must contain regular files only",
    )
    for registered in required_artifacts:
        artifact_path = output_dir / str(registered["path"])
        _require(
            artifact_path.stat().st_size == int(registered["bytes"])
            and sha256_file(artifact_path) == registered["sha256"],
            f"published artifact changed before completion: {artifact_path.name}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the experimental three-model LLM training-hook matrix")
    parser.add_argument("--config", type=Path, default=ROOT / "reproduction" / "llm-training-hook" / "config.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "output" / "llm-training-hook" / "cache")
    parser.add_argument("--offline", action="store_true", help="require already-cached model and dataset objects")
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.output_dir is None:
        run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S-%fZ")
        output_dir = (ROOT / "output" / "llm-training-hook" / run_id).resolve()
    else:
        output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    require_disjoint_run_and_cache_paths(output_dir, cache_dir)
    report = run(config_path, output_dir, cache_dir, offline=args.offline)
    output_config = report["output_contract"]
    json_path = output_dir / output_config["json_report"]
    markdown_path = output_dir / output_config["markdown_report"]
    completion_path = output_dir / output_config["completion_manifest"]
    _atomic_write_text(json_path, json.dumps(report, indent=2, allow_nan=False) + "\n")
    _atomic_write_text(markdown_path, build_markdown_report(report))
    required_artifacts = [
        {
            "path": artifact_path.name,
            "bytes": artifact_path.stat().st_size,
            "sha256": sha256_file(artifact_path),
        }
        for artifact_path in sorted(
            [
                json_path,
                markdown_path,
                *[output_dir / item["path"] for item in report["artifact_manifest"]],
            ],
            key=lambda path: path.name,
        )
    ]
    completion_manifest = {
        "schema_version": "1.0",
        "complete": True,
        "experiment_id": report["experiment_id"],
        "report_body_sha256": report["report_body_sha256"],
        "decision": "no_release_authorization",
        "required_artifacts": required_artifacts,
        "required_artifact_manifest_sha256": canonical_sha256(required_artifacts),
        "semantics": "the run artifact set is complete only when this final no-clobber manifest is present and every registered artifact digest verifies",
    }
    verify_registered_artifact_entries(
        output_dir,
        required_artifacts,
        completion_manifest_name=None,
    )
    _atomic_write_text(completion_path, json.dumps(completion_manifest, indent=2, allow_nan=False) + "\n")
    try:
        verify_registered_artifact_entries(
            output_dir,
            required_artifacts,
            completion_manifest_name=completion_path.name,
        )
        _require(
            json.loads(completion_path.read_text(encoding="utf-8")) == completion_manifest,
            "completion manifest changed after publication",
        )
    except BaseException:
        if completion_path.exists() and not completion_path.is_symlink():
            completion_path.unlink()
            directory_fd = os.open(output_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        raise
    print(json.dumps({
        "execution": report["execution"],
        "decision": report["decision"],
        "report": str(json_path),
        "markdown_report": str(markdown_path),
        "completion_manifest": str(completion_path),
        "report_body_sha256": report["report_body_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
