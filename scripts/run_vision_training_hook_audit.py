#!/usr/bin/env python3
"""Run the full-EuroSAT-RGB AlexNet/DenseNet aggregate-hook experiment.

This worker is deliberately non-authorizing.  It downloads one byte-pinned
archive from its canonical Zenodo record, trains two torchvision architectures from
scratch, and retains only aggregate measurements and hash-bound provenance in
its result artifacts.  The governed source cache holds the verified corpus;
reports and telemetry never contain image values, labels, paths, model tensors,
activations, or gradients.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request
import warnings
import zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin, urlparse


ROOT = Path(__file__).resolve().parents[1]
HEX32 = set("0123456789abcdef")
DATASET_DIRECTORY = "EuroSAT_RGB"
CLASS_COUNTS = {
    "AnnualCrop": 3000,
    "Forest": 3000,
    "HerbaceousVegetation": 3000,
    "Highway": 2500,
    "Industrial": 2500,
    "Pasture": 2000,
    "PermanentCrop": 2500,
    "Residential": 3000,
    "River": 2500,
    "SeaLake": 3000,
}
JPEG_NAME = re.compile(r"^[A-Za-z]+_[1-9][0-9]*\.jpg$")
MODEL_HOOKS = {
    # MaxPool outputs avoid torchvision's in-place ReLU/view conflict with
    # full backward hooks while still covering the early and late feature path.
    "alexnet": ["features.2", "features.12", "classifier.6"],
    "densenet121": ["features.conv0", "features.denseblock4", "classifier"],
}
FROZEN_ARCHIVE_SHA256 = (
    "b4f5b234ecb7d7ff9c6cddb046543b4717c53fd6e9815be6c0e80cc614f51b90"
)
FROZEN_ARCHIVE_MD5 = "f46e308c4d50d4bf32fedad2d3d62f3b"
FROZEN_EXTRACTION_CANONICAL_SHA256 = (
    "ffe4a9c460a2b20b3f2c86898733efaceac581b4d9dfc900fc73e8b553067c61"
)
FROZEN_EXTRACTION_SERIALIZED_SHA256 = (
    "f09028023218981546f9c4896a4f1b7201e4b73b3bdeb2c0b0fbe0003582a4d3"
)
FROZEN_TRAIN_ROSTER_SHA256 = (
    "3e26b9ee7014071cd257715e8c0895f478d9256464f3afb40a26bfed3c148b75"
)
FROZEN_TEST_ROSTER_SHA256 = (
    "c0e582d0dd8b88b41ffb08998eb0fcef5d31742815098b18c7c6e8ef2e1f0387"
)
EXPECTED_EXTRACTED_BYTES = 91_844_360
FROZEN_IMPLEMENTATION_SOURCE = (
    "https://github.com/pytorch/vision/tree/v0.28.0/torchvision/models"
)
FROZEN_IMPLEMENTATION_LICENSE_URL = (
    "https://github.com/pytorch/vision/blob/v0.28.0/LICENSE"
)
HOOK_MEASUREMENTS = [
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
    "duration_seconds",
    "gpu_memory",
]
EXPECTED_PROVENANCE_FIELDS = (
    "pillow_version",
    "libjpeg_version",
    "torch_distribution_version",
    "torch_distribution_regular_file_count",
    "torch_distribution_regular_file_bytes",
    "torch_distribution_file_manifest_sha256",
    "torchvision_distribution_file_manifest_sha256",
    "torchvision_package_file_manifest_sha256",
    "alexnet_constructor_source_sha256",
    "densenet121_constructor_source_sha256",
    "imagefolder_class_source_sha256",
    "default_loader_source_sha256",
    "pillow_distribution_file_manifest_sha256",
    "pillow_package_file_manifest_sha256",
    "pillow_image_source_sha256",
    "pillow_imaging_extension_sha256",
)
PROVENANCE_TEXT_FIELDS = (
    "pillow_version",
    "libjpeg_version",
    "torch_distribution_version",
)
PROVENANCE_INTEGER_FIELDS = (
    "torch_distribution_regular_file_count",
    "torch_distribution_regular_file_bytes",
)
PROVENANCE_DIGEST_FIELDS = EXPECTED_PROVENANCE_FIELDS[5:]
EXPECTED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "experiment_id",
    "experimental_only",
    "authorization_eligible",
    "assessment_input_emitted",
    "decision",
    "dataset",
    "runtime",
    "preprocessing",
    "models",
    "training",
    "evaluation",
    "hooks",
    "hook_non_interference_control",
    "red_team",
    "metadata_release_profiles",
    "roster_release_handling",
    "release_gate_summary",
    "output",
}
EXPECTED_CONFIG_SECTION_SHA256 = {
    "dataset": "ffa283cd244502ef8067889ff5a4d64b74a0579d7718cebc2c78fa081fc90d60",
    "runtime": "7b08f83a624be19fc80ad9d4875615396fa63702ee5a052bb37125ee2786d776",
    "preprocessing": "8abcf981c1636dc61a3f64b0e2ad1d1a1b74e48dbfb79aec8a370079e0d62e82",
    "models": "cb9cde26eb9171103ed6fd713efac964f4ec1243c3411e18b1e2d4fb4027af15",
    "training": "fe5965351b98d5953db552cd495aad22adb429f3d35073c24420895bb56b2ff1",
    "evaluation": "f4eb6825275f64c8698bb6ec24c591f3696ee4205df5517f90c32a2874950b26",
    "hooks": "9bde8472574fb19814715752683d4caacf5a5388bb02613ec6f7ac549a14b0fa",
    "hook_non_interference_control": "559a8d21a269b7588eb48f2c29bea608fadafc3bafcf242a099db3e84f1d6372",
    "red_team": "81c2cd348db2c6b083f434da9e841a3d259d7b06e466b0ff32db438a369b85f1",
    "metadata_release_profiles": "70401b878471f9aaaea9f6cbfe14f6a021ef5e3704bfe8eed5408198d217a6c2",
    "roster_release_handling": "1836f0dc603d5e4676c99b930bbb3226f729e71f2e20c008082540ff14682d75",
    "release_gate_summary": "e1118b2e9699ef3429a81a675fe83ba38b0f283c59cb2616760b14351cf6c597",
    "output": "a9bb4c1c65048b9a8672456ace5daa3f00ab1cecd05e5b8d55f0bf19848e8186",
}
_BOUND_HOOK_COLLECTOR: Any | None = None
_BOUND_HOOK_EVIDENCE: dict[str, Any] | None = None


def canonical_json(value: Any) -> bytes:
    """Encode strict, stable JSON for hashes and JSONL telemetry."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def repo_logical_name(path: Path) -> str:
    """Return a repository-relative logical name without a machine path."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.name


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    # MD5 is retained only to cross-check the checksum published by Zenodo.
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_bounded_regular_file(path: Path, max_bytes: int, label: str) -> bytes:
    """Read a regular file only after an fd-bound size and identity check.

    The lstat happens before ``open`` and therefore before any content read. A
    second fstat binds the opened descriptor to that path observation, while a
    bounded ``os.read`` loop protects against special-file and concurrent-size
    surprises even on platforms without ``O_NOFOLLOW``.
    """

    _require(
        isinstance(max_bytes, int)
        and not isinstance(max_bytes, bool)
        and max_bytes >= 0,
        f"{label} byte cap is invalid",
    )
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode), f"{label} must be a regular file")
    _require(before.st_size <= max_bytes, f"{label} exceeds its byte cap")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} could not be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        _require(stat.S_ISREG(opened.st_mode), f"{label} must be a regular file")
        _require(
            (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
            f"{label} changed before it was opened",
        )
        _require(opened.st_size <= max_bytes, f"{label} exceeds its byte cap")

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        _require(len(payload) <= max_bytes, f"{label} exceeds its byte cap")

        after = os.fstat(descriptor)
        _require(
            (after.st_dev, after.st_ino, after.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size)
            and after.st_mtime_ns == opened.st_mtime_ns
            and after.st_ctime_ns == opened.st_ctime_ns,
            f"{label} changed while it was read",
        )
        _require(
            len(payload) == after.st_size,
            f"{label} byte count changed while reading",
        )
        return payload
    finally:
        os.close(descriptor)


def load_bound_hook_collector(
    path: Path, expected_sha256: str
) -> tuple[Any, dict[str, Any]]:
    """Compile the exact hook bytes that were hashed into run provenance."""

    _require(_is_lower_hex(expected_sha256, 64), "hook source digest is invalid")
    resolved = path.resolve()
    payload = read_bounded_regular_file(
        resolved, 1024 * 1024, "hook implementation source"
    )
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    _require(
        observed_sha256 == expected_sha256,
        "hook implementation changed between source snapshot and load",
    )

    module_token = hashlib.sha256(
        f"{resolved}:{observed_sha256}:{os.getpid()}:{time.time_ns()}".encode("utf-8")
    ).hexdigest()
    module_name = f"_vision_audit_bound_hooks_{module_token}"
    module = types.ModuleType(module_name)
    module.__file__ = str(resolved)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        code = compile(payload, str(resolved), "exec", dont_inherit=True)
        exec(code, module.__dict__)
        collector = getattr(module, "AggregateTrainingHookCollector", None)
        _require(isinstance(collector, type), "bound hook collector class is missing")
        _require(
            collector.__module__ == module_name,
            "bound hook collector did not originate from the byte-bound module",
        )
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    return collector, {
        "load_strategy": "compile_exact_prehashed_bytes",
        "source_logical_name": repo_logical_name(resolved),
        "source_bytes": len(payload),
        "source_sha256": observed_sha256,
    }


def bind_hook_collector(path: Path, expected_sha256: str) -> dict[str, Any]:
    """Bind the shared collector used by both control and training paths."""

    global _BOUND_HOOK_COLLECTOR, _BOUND_HOOK_EVIDENCE
    collector, evidence = load_bound_hook_collector(path, expected_sha256)
    _BOUND_HOOK_COLLECTOR = collector
    _BOUND_HOOK_EVIDENCE = evidence
    return dict(evidence)


def bound_hook_collector() -> Any:
    _require(
        _BOUND_HOOK_COLLECTOR is not None and _BOUND_HOOK_EVIDENCE is not None,
        "hook collector has not been bound to its prehashed source bytes",
    )
    return _BOUND_HOOK_COLLECTOR


def _is_lower_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in HEX32 for character in value)
    )


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if reproducibility, privacy, or release bounds drift."""

    _require(
        set(raw) == EXPECTED_TOP_LEVEL_FIELDS,
        "configuration top-level fields differ from the frozen profile",
    )
    _require(raw.get("schema_version") == "1.1", "schema_version must be 1.1")
    _require(
        raw.get("experiment_id") == "vision-training-hooks-full-eurosat-rgb-v1",
        "experiment_id differs from the frozen vision profile",
    )
    _require(raw.get("experimental_only") is True, "experimental_only must be true")
    _require(
        raw.get("authorization_eligible") is False,
        "authorization_eligible must be false",
    )
    _require(
        raw.get("assessment_input_emitted") is False,
        "the experiment must not emit formal assessment input",
    )
    _require(
        raw.get("decision") == "no_release_authorization",
        "decision must be no_release_authorization",
    )

    mapping_sections = (
        "dataset",
        "runtime",
        "preprocessing",
        "training",
        "evaluation",
        "hooks",
        "hook_non_interference_control",
        "red_team",
        "roster_release_handling",
        "release_gate_summary",
        "output",
    )
    _require(
        all(isinstance(raw.get(section), dict) for section in mapping_sections),
        "all registered configuration mapping sections must be objects",
    )
    _require(isinstance(raw.get("models"), list), "models must be a list")
    _require(
        isinstance(raw.get("metadata_release_profiles"), list),
        "metadata_release_profiles must be a list",
    )

    dataset = raw["dataset"]
    runtime = raw["runtime"]
    preprocessing = raw["preprocessing"]
    training = raw["training"]
    evaluation = raw["evaluation"]
    hooks = raw["hooks"]
    release = raw["release_gate_summary"]
    output = raw["output"]

    _require(dataset.get("name") == "EuroSAT RGB", "dataset must be EuroSAT RGB")
    _require(dataset.get("doi") == "10.5281/zenodo.7711810", "dataset DOI must remain frozen")
    _require(dataset.get("official_page") == "https://zenodo.org/records/7711810", "dataset page must remain the canonical Zenodo record")
    _require(dataset.get("url") == "https://zenodo.org/api/records/7711810/files/EuroSAT_RGB.zip/content", "dataset object URL must remain canonical")
    _require(dataset.get("allowed_redirect_hosts") == ["zenodo.org", "www.zenodo.org"], "dataset redirect allowlist must remain exact")
    _require(dataset.get("archive_file") == "EuroSAT_RGB.zip", "unexpected dataset archive name")
    _require(
        _is_lower_hex(dataset.get("sha256"), 64)
        and dataset.get("sha256") == FROZEN_ARCHIVE_SHA256,
        "dataset SHA-256 must equal the frozen archive digest",
    )
    _require(
        _is_lower_hex(dataset.get("official_md5"), 32)
        and dataset.get("official_md5") == FROZEN_ARCHIVE_MD5,
        "dataset MD5 must equal the official published checksum",
    )
    expected_bytes = dataset.get("archive_bytes")
    max_bytes = dataset.get("max_download_bytes")
    _require(
        isinstance(expected_bytes, int) and not isinstance(expected_bytes, bool),
        "archive_bytes must be an integer",
    )
    _require(
        expected_bytes == 94_658_721 and max_bytes == expected_bytes,
        "archive byte count and download cap must equal the frozen object size",
    )
    _require(
        dataset.get("loader") == "verified_zip_torchvision_imagefolder_no_download",
        "dataset loader must not execute a network-aware loader",
    )
    _require(dataset.get("synthetic_samples") is False, "synthetic samples are forbidden")
    _require(dataset.get("augmented_samples") is False, "augmented samples are forbidden")
    _require(
        dataset.get("train_rows") == 21_600
        and dataset.get("test_rows") == 5_400
        and dataset.get("total_rows") == 27_000,
        "the complete deterministic 21,600/5,400 EuroSAT split is required",
    )
    _require(
        dataset.get("expected_unique_image_sha256") == 27_000
        and dataset.get("expected_cross_split_content_overlap") == 0,
        "the canonical corpus must contain 27,000 unique images and no split overlap",
    )
    _require(
        dataset.get("classes") == 10
        and dataset.get("native_shape") == [3, 64, 64]
        and dataset.get("class_counts") == CLASS_COUNTS,
        "EuroSAT class counts and native shape must remain frozen",
    )
    _require(
        dataset.get("split") == {
            "algorithm": "per_class_sha256(seed:relative_path)_lexical_ascending",
            "seed": 3407,
            "train_fraction": 0.8,
            "class_stratified": True,
            "train_relative_path_set_sha256": FROZEN_TRAIN_ROSTER_SHA256,
            "test_relative_path_set_sha256": FROZEN_TEST_ROSTER_SHA256,
        },
        "dataset split algorithm must remain exact",
    )
    _require(dataset.get("license") == "MIT", "EuroSAT license declaration must remain MIT")
    _require(dataset.get("sentinel_data_terms_review") == "REQUIRED", "Sentinel terms review must remain required")
    _require(dataset.get("rights_gate") == "MANUAL_REVIEW_REQUIRED", "dataset rights must retain manual review")
    _require(
        dataset.get("max_extracted_bytes") == 200_000_000
        and dataset.get("extracted_bytes") == EXPECTED_EXTRACTED_BYTES,
        "unexpected extracted-data byte count or cap",
    )
    _require(
        dataset.get("extraction_manifest")
        == {
            "schema_version": "1.0",
            "canonical_sha256": FROZEN_EXTRACTION_CANONICAL_SHA256,
            "canonical_bytes": 3_324_046,
            "serialized_sha256": FROZEN_EXTRACTION_SERIALIZED_SHA256,
            "serialized_bytes": 4_053_063,
            "max_bytes": 4_053_063,
            "file_count": 27_000,
            "max_file_bytes": 1_000_000,
            "total_file_bytes": EXPECTED_EXTRACTED_BYTES,
        },
        "extraction manifest registration must remain exact",
    )
    _require(
        dataset.get("decoded_validation")
        == {
            "format": "JPEG",
            "mode": "RGB",
            "width": 64,
            "height": 64,
            "expected_images": 27_000,
        },
        "decoded JPEG validation registry must remain exact",
    )

    _require(runtime.get("required_device_type") == "cuda", "CUDA is required")
    _require(runtime.get("torch_version") == "2.13.0", "torch must be pinned")
    _require(
        runtime.get("torchvision_version") == "0.28.0",
        "torchvision must be pinned",
    )
    _require(runtime.get("num_workers") == 0, "num_workers must remain zero")
    _require(
        runtime.get("reproducibility")
        == {
            "seeded": True,
            "split_and_batch_order_deterministic": True,
            "deterministic_algorithms_mode": "warn_only",
            "known_nondeterministic_cuda_kernels": [
                "adaptive_avg_pool2d_backward_cuda"
            ],
            "unexpected_nondeterminism_warning_policy": "fail_closed",
            "known_warning_must_be_observed": True,
            "bitwise_reproducible": False,
            "single_run_variance_estimated": False,
            "cudnn_benchmark": False,
            "cudnn_deterministic": True,
        },
        "runtime reproducibility policy differs from the seeded warn-only CUDA profile",
    )
    expected_provenance = runtime.get("expected_provenance", {})
    _require(
        isinstance(expected_provenance, dict)
        and set(expected_provenance)
        == {
            "schema_version",
            "registration_status",
            "target_environment",
            "capture_only_can_authorize",
            "exact",
        }
        and expected_provenance.get("schema_version") == "1.0"
        and expected_provenance.get("target_environment")
        == "g6.4xlarge_ap-southeast-1_test_environment"
        and expected_provenance.get("capture_only_can_authorize") is False,
        "runtime provenance registry is invalid",
    )
    provenance_status = expected_provenance.get("registration_status")
    _require(
        provenance_status in {"PENDING_EC2_BASELINE_CAPTURE", "REGISTERED"},
        "runtime provenance registration status is invalid",
    )
    exact_provenance = expected_provenance.get("exact")
    _require(
        isinstance(exact_provenance, dict)
        and tuple(exact_provenance) == EXPECTED_PROVENANCE_FIELDS,
        "runtime provenance exact-field registry is invalid",
    )
    if provenance_status == "PENDING_EC2_BASELINE_CAPTURE":
        _require(
            all(exact_provenance[field] is None for field in EXPECTED_PROVENANCE_FIELDS),
            "pending runtime provenance fields must remain null",
        )
    else:
        for field in PROVENANCE_TEXT_FIELDS:
            _require(
                isinstance(exact_provenance[field], str)
                and bool(exact_provenance[field]),
                f"registered runtime provenance field is invalid: {field}",
            )
        for field in PROVENANCE_INTEGER_FIELDS:
            _require(
                isinstance(exact_provenance[field], int)
                and not isinstance(exact_provenance[field], bool)
                and exact_provenance[field] > 0,
                f"registered runtime provenance integer is invalid: {field}",
            )
        for field in PROVENANCE_DIGEST_FIELDS:
            _require(
                _is_lower_hex(exact_provenance[field], 64),
                f"registered runtime provenance digest is invalid: {field}",
            )

    _require(preprocessing.get("resize") == [96, 96], "resize must remain 96x96")
    _require(preprocessing.get("interpolation") == "bilinear", "unexpected interpolation")
    _require(preprocessing.get("antialias") is True, "resize antialiasing is required")
    _require(preprocessing.get("augmentation") == [], "augmentation is forbidden")
    _require(preprocessing.get("deterministic") is True, "preprocessing must be deterministic")
    means = preprocessing.get("normalize_mean")
    stds = preprocessing.get("normalize_std")
    _require(
        means == [0.485, 0.456, 0.406]
        and stds == [0.229, 0.224, 0.225]
        and all(
            not isinstance(item, bool) and math.isfinite(float(item))
            for item in [*means, *stds]
        )
        and all(float(item) > 0 for item in stds),
        "normalization must equal the frozen finite RGB statistics",
    )

    models = raw.get("models")
    _require(isinstance(models, list) and len(models) == 2, "exactly two models are required")
    observed_keys: list[str] = []
    for model in models:
        _require(isinstance(model, dict), "model registrations must be objects")
        key = model.get("key")
        observed_keys.append(key)
        _require(key in MODEL_HOOKS, f"unregistered model key: {key!r}")
        _require(model.get("constructor") == key, f"constructor for {key} must remain canonical")
        _require(model.get("weights") is None, f"{key} must not download pretrained weights")
        _require(model.get("num_classes") == 10, f"{key} must use the ten-class head")
        _require(
            model.get("adaptation") == "ten_class_output_head_only",
            f"{key} architecture adaptation must remain explicit",
        )
        _require(model.get("train_all_parameters") is True, f"{key} must train all parameters")
        _require(
            model.get("hook_modules") == MODEL_HOOKS[key],
            f"{key} hook modules must remain the exact safe allowlist",
        )
        _require(model.get("implementation_license") == "BSD-3-Clause", "implementation license must be declared")
        _require(
            model.get("implementation_source") == FROZEN_IMPLEMENTATION_SOURCE
            and model.get("implementation_license_url")
            == FROZEN_IMPLEMENTATION_LICENSE_URL,
            "torchvision implementation provenance must remain release-pinned",
        )
        _require(model.get("remote_code") is False, "remote model code is forbidden")
    _require(observed_keys == ["alexnet", "densenet121"], "model order must be alexnet then densenet121")

    _require(training.get("seed") == 3407, "training seed must remain frozen")
    _require(training.get("epochs") == 1, "this experiment requires exactly one epoch")
    batch_size = training.get("batch_size")
    _require(batch_size == 128, "training batch size must remain 128")
    expected_steps = math.ceil(dataset["train_rows"] / batch_size)
    _require(
        training.get("expected_optimizer_steps_per_model") == expected_steps,
        "expected optimizer steps do not match the full training split",
    )
    _require(training.get("optimizer") == "SGD", "optimizer must remain SGD")
    _require(training.get("learning_rate") == 0.01, "learning rate must remain frozen")
    _require(training.get("weight_decay") == 0.0005, "weight decay must remain frozen")
    _require(training.get("momentum") == 0.9, "momentum must remain frozen")
    _require(training.get("shuffle") is True, "training must use the frozen shuffle")
    _require(
        training.get("shuffle_algorithm") == "torch_RandomSampler_seeded_generator",
        "shuffle algorithm must remain explicit",
    )
    _require(
        training.get("seeded") is True
        and training.get("data_order_deterministic") is True
        and training.get("bitwise_reproducible") is False,
        "training must be seeded with deterministic order and no bitwise CUDA claim",
    )
    _require(training.get("torch_dtype") == "float32", "training must remain FP32")

    _require(evaluation.get("test_rows") == 5_400, "the complete test split is required")
    _require(
        evaluation.get("checkpoints") == ["before_training", "after_training"],
        "both before/after test evaluations are required",
    )
    _require(evaluation.get("used_for_tuning") is False, "test data must not tune training")
    _require(evaluation.get("batch_size") == 256, "evaluation batch size must remain 256")
    _require(
        evaluation.get("metrics")
        == ["mean_cross_entropy", "top1_accuracy", "examples_per_second"],
        "evaluation metric registry must remain exact",
    )

    _require(hooks.get("collector") == "AggregateTrainingHookCollector", "unexpected hook collector")
    _require(hooks.get("capture") == "aggregate_only", "hooks must remain aggregate-only")
    _require(hooks.get("raw_images_retained") is False, "raw images must not be retained")
    _require(hooks.get("raw_tensors_retained") is False, "raw tensors must not be retained")
    _require(hooks.get("raw_labels_retained") is False, "raw labels must not be retained")
    _require(hooks.get("fail_on_nonfinite") is True, "non-finite values must fail closed")
    _require(
        hooks.get("measurements") == HOOK_MEASUREMENTS,
        "hook measurement registry must match emitted aggregate fields",
    )
    maximum_required_events = max(
        expected_steps * (2 * len(model["hook_modules"]) + 1)
        for model in models
    )
    _require(
        hooks.get("max_events_per_model") == 1_500
        and maximum_required_events <= hooks["max_events_per_model"] <= 10_000,
        "hook event cap cannot cover the run or is not bounded",
    )

    _require(
        raw.get("hook_non_interference_control")
        == {
            "enabled": True,
            "seed": 8819,
            "paired_real_examples": 2,
            "control_device": "cpu",
            "exact_match_required": True,
            "cuda_noninterference_proven": False,
            "comparisons": [
                "initial_state_sha256",
                "loss_hex",
                "gradient_sha256",
                "post_step_state_sha256",
            ],
        },
        "hook non-interference control must remain exact",
    )

    red_team = raw.get("red_team", {})
    _require(red_team.get("enabled") is True and red_team.get("test_rows") == 512 and red_team.get("seed") == 3407, "red-team sample registry must remain bounded and exact")
    _require(red_team.get("screens") == {"brightness_factor": 1.25, "gaussian_noise_std": 0.05, "fgsm_epsilon": 2 / 255}, "red-team perturbations must remain exact")
    _require(
        red_team.get("threat_model") == "untargeted_white_box_true_label"
        and red_team.get("attack_success_denominator")
        == "clean_correct_examples"
        and red_team.get("fgsm_norm") == "pixel_linf"
        and red_team.get("max_linf_tolerance") == 1e-7,
        "red-team threat model and norm assertion must remain exact",
    )
    _require(
        red_team.get("evidence_direction") == "screen"
        and red_team.get("descriptive_only") is True
        and red_team.get("can_clear") is False
        and red_team.get("can_block") is False
        and red_team.get("attack_battery_eligible") is False
        and red_team.get("assessment_input_emitted") is False
        and red_team.get("requires_approved_recollection") is True,
        "red-team screens must remain descriptive, non-decision-bearing, and ineligible for assessment reuse",
    )
    profiles = raw.get("metadata_release_profiles")
    expected_profiles = [
        {"level": "M0_label_only", "disclosed": ["predicted_class"], "gate": "MANUAL_REVIEW_REQUIRED"},
        {"level": "M1_scores", "disclosed": ["class_probabilities", "confidence"], "gate": "PRIVACY_AND_EXTRACTION_REVIEW_REQUIRED"},
        {"level": "M2_internal_features", "disclosed": ["embeddings", "activations", "per_example_loss"], "gate": "RESTRICTED_AUDITOR_ONLY"},
        {"level": "M3_source_provenance", "disclosed": ["source_relative_path", "exact_training_roster", "geolocation_if_available"], "gate": "BLOCKED_REDESIGN_REQUIRED"},
    ]
    _require(profiles == expected_profiles, "metadata profiles and gates must remain the exact M0-M3 registry")
    _require(
        raw.get("roster_release_handling")
        == {
            "public_benchmark_reconstructible": True,
            "experiment_roster_visibility": "internal_provenance_not_a_recipient_interface",
            "protected_exact_roster_can_clear": False,
            "protected_exact_roster_gate": "BLOCKED_REDESIGN_REQUIRED",
            "required_remediation": "remove_roster_disclosure_and_reassess_changed_interface",
        },
        "public benchmark and protected-roster handling must remain explicit",
    )

    _require(
        release.get("contract_semantics")
        == "illustrative_non_mrap_gate_summary"
        and release.get("mrap_release_contract_required") is True,
        "release gate summary must not be represented as an MRAP ReleaseContract",
    )
    _require(release.get("operational_pass_can_authorize") is False, "operational evidence cannot authorize")
    _require(release.get("dataset_rights_gate") == dataset["rights_gate"], "release rights gate must bind the dataset gate")
    _require(
        release.get("model_implementation_license_gate")
        == "DECLARED_REQUIRES_INDEPENDENT_REVIEW",
        "model implementation license gate must remain independently reviewed",
    )
    _require(release.get("quality_gate") == "NOT_ASSESSED", "quality must remain unassessed")
    _require(release.get("privacy_gate") == "NOT_ASSESSED", "privacy must remain unassessed")
    _require(release.get("security_gate") == "NOT_ASSESSED", "security must remain unassessed")
    _require(release.get("robustness_gate") == "NOT_ASSESSED", "robustness must remain unassessed")
    _require(release.get("fairness_gate") == "NOT_ASSESSED", "fairness must remain unassessed")
    _require(
        release.get("production_distribution_gate") == "NOT_ASSESSED",
        "production distribution must remain unassessed",
    )
    _require(release.get("decision") == "no_release_authorization", "release decision must remain non-authorizing")

    artifact_names = [
        output.get("json_report"),
        output.get("markdown_report"),
        *[
            output.get("telemetry_pattern", "").format(model_key=model["key"])
            for model in models
        ],
    ]
    _require(
        output.get("directory") == "output/vision-training-hook",
        "output root must remain frozen",
    )
    _require(
        output.get("telemetry_pattern") == "training-telemetry-{model_key}.jsonl",
        "telemetry filename pattern must remain frozen",
    )
    _require(
        output.get("json_report") == "vision-training-hook-report.json"
        and output.get("markdown_report") == "vision-training-hook-report.md"
        and output.get("completion_signal") == output.get("json_report"),
        "output reports and JSON-last completion signal must remain frozen",
    )
    _require(output.get("fresh_run_directory_required") is True, "fresh output directories are required")
    _require(
        all(isinstance(name, str) and name and Path(name).name == name for name in artifact_names),
        "output artifact names must be safe basenames",
    )
    _require(
        len(artifact_names) == len(set(artifact_names)),
        "output artifact basenames must be unique",
    )
    for section, expected_sha256 in EXPECTED_CONFIG_SECTION_SHA256.items():
        _require(
            canonical_sha256(raw[section]) == expected_sha256,
            f"{section} differs from the exact frozen vision profile",
        )
    return raw


def load_config_with_digest(path: Path) -> tuple[dict[str, Any], str]:
    """Hash the exact configuration bytes before decoding or parsing them."""

    payload = read_bounded_regular_file(path, 256 * 1024, "configuration")
    digest = hashlib.sha256(payload).hexdigest()
    raw = json.loads(payload.decode("utf-8", errors="strict"))
    _require(isinstance(raw, dict), "configuration must be a JSON object")
    return validate_config(raw), digest


def load_config(path: Path) -> dict[str, Any]:
    return load_config_with_digest(path)[0]


def reserve_output_directory(path: Path) -> Path:
    """Create one fresh directory and never adopt or overwrite an old run."""

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to reuse output directory: {path}") from exc
    return path


def resolve_disjoint_directory_trees(
    output_dir: Path, cache_dir: Path
) -> tuple[Path, Path]:
    """Resolve and reject cache/output equality or containment either way."""

    resolved_output = output_dir.resolve()
    resolved_cache = cache_dir.resolve()
    overlap = (
        resolved_output == resolved_cache
        or resolved_output in resolved_cache.parents
        or resolved_cache in resolved_output.parents
    )
    _require(
        not overlap,
        "output and governed cache directory trees must be disjoint",
    )
    return resolved_output, resolved_cache


def atomic_write_new(path: Path, payload: str) -> None:
    """Atomically publish a UTF-8 artifact without replacement semantics."""

    _require(not path.exists(), f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise FileExistsError(f"refusing to overwrite artifact: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def publish_completion_artifacts(
    output_dir: Path,
    pending_telemetry: list[tuple[str, str]],
    report: dict[str, Any],
    json_name: str,
    markdown_name: str,
    *,
    writer: Any | None = None,
) -> dict[str, Any]:
    """Publish prerequisites first and the JSON completion signal last.

    A failed telemetry or Markdown publication may leave diagnostic partials in
    the fresh run directory, but it can never leave the JSON report that marks
    the artifact set complete.
    """

    artifact_writer = atomic_write_new if writer is None else writer
    names = [
        *[name for name, _payload in pending_telemetry],
        markdown_name,
        json_name,
    ]
    _require(
        all(
            isinstance(name, str) and name and Path(name).name == name
            for name in names
        ),
        "resolved output artifact names must be safe basenames",
    )
    _require(
        len(names) == len(set(names)),
        "resolved output artifact basenames are not unique",
    )

    publication = {
        "completion_signal": json_name,
        "completion_signal_published_last": True,
        "directory_complete_only_if_completion_signal_present": True,
        "failure_behavior": (
            "partial prerequisites may remain; absent completion signal means incomplete"
        ),
    }
    report["artifact_handling"]["publication_protocol"] = publication
    report_markdown = build_markdown_report(report)
    prerequisite_payloads = [
        *pending_telemetry,
        (markdown_name, report_markdown),
    ]
    publication["prerequisite_artifacts"] = [
        {
            "name": name,
            "bytes": len(payload.encode("utf-8")),
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }
        for name, payload in prerequisite_payloads
    ]
    report_json = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"

    for name, payload in prerequisite_payloads:
        artifact_writer(output_dir / name, payload)
    artifact_writer(output_dir / json_name, report_json)
    return report


def verify_archive(path: Path, dataset: Mapping[str, Any]) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), "dataset archive is missing or not a regular file")
    size = path.stat().st_size
    _require(size <= int(dataset["max_download_bytes"]), "dataset archive exceeds the byte cap")
    _require(size == int(dataset["archive_bytes"]), "dataset archive byte count mismatch")
    sha256 = sha256_file(path)
    md5 = md5_file(path)
    _require(sha256 == dataset["sha256"], "dataset archive SHA-256 mismatch")
    _require(md5 == dataset["official_md5"], "dataset archive official MD5 mismatch")
    return {"bytes": size, "sha256": sha256, "official_md5": md5}


class _RejectAutomaticRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def validate_download_url(url: str, allowed_hosts: Iterable[str]) -> str:
    """Validate one concrete request URL before any connection is attempted."""

    parsed = urlparse(url)
    allowed = {str(host).lower() for host in allowed_hosts}
    _require(parsed.scheme == "https", "dataset requests must use HTTPS")
    _require(parsed.username is None and parsed.password is None, "dataset URL credentials are forbidden")
    _require(parsed.port in (None, 443), "dataset URL uses an unexpected port")
    _require((parsed.hostname or "").lower() in allowed, "dataset request host is not allowlisted")
    _require(not parsed.fragment, "dataset URL fragments are forbidden")
    return url


def open_with_validated_redirects(
    url: str,
    allowed_hosts: Iterable[str],
    *,
    timeout: int = 60,
    maximum_redirects: int = 5,
    opener: Any | None = None,
) -> tuple[Any, list[str]]:
    """Open a URL while validating every redirect target before requesting it."""

    client = opener or urllib.request.build_opener(_RejectAutomaticRedirects())
    current = url
    requested: list[str] = []
    redirect_codes = {301, 302, 303, 307, 308}
    for redirect_index in range(maximum_redirects + 1):
        validate_download_url(current, allowed_hosts)
        requested.append(current)
        request = urllib.request.Request(
            current,
            headers={"User-Agent": "model-release-assurance-vision-experiment/1.0"},
        )
        try:
            response = client.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in redirect_codes:
                raise
            location = exc.headers.get("Location")
            exc.close()
            _require(location is not None and location.strip(), "dataset redirect omitted Location")
            _require(redirect_index < maximum_redirects, "dataset redirect limit exceeded")
            current = urljoin(current, location)
            # Validate now as well as immediately before the next request.  An
            # unregistered redirect is rejected without contacting its host.
            validate_download_url(current, allowed_hosts)
            continue
        final_url = response.geturl()
        _require(
            final_url == current,
            "HTTP client performed an unvalidated automatic redirect",
        )
        return response, requested
    raise ValueError("dataset redirect limit exceeded")


def download_verified_archive(
    dataset: Mapping[str, Any], cache_dir: Path, *, offline: bool
) -> tuple[Path, dict[str, Any]]:
    """Fetch exactly one bounded official object, or replay cached bytes."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / str(dataset["archive_file"])
    if destination.exists():
        report = verify_archive(destination, dataset)
        report.update(
            {
                "retrieval_mode": "verified_cache",
                "validated_request_urls": [],
                "redirect_validation": "not_applicable_offline_or_cached_replay",
            }
        )
        return destination, report
    if offline:
        raise FileNotFoundError(f"offline replay requires cached archive: {destination}")

    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{time.time_ns()}.part"
    )
    total = 0
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    try:
        response, requested_urls = open_with_validated_redirects(
            str(dataset["url"]), dataset["allowed_redirect_hosts"], timeout=60
        )
        with response:
            declared = response.headers.get("Content-Length")
            if declared is not None:
                _require(int(declared) == dataset["archive_bytes"], "remote Content-Length mismatch")
            with temporary.open("xb") as stream:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    _require(total <= dataset["max_download_bytes"], "download exceeded the exact byte cap")
                    sha256.update(chunk)
                    md5.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        _require(total == dataset["archive_bytes"], "downloaded dataset byte count mismatch")
        _require(sha256.hexdigest() == dataset["sha256"], "downloaded dataset SHA-256 mismatch")
        _require(md5.hexdigest() == dataset["official_md5"], "downloaded dataset MD5 mismatch")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            # A concurrent writer won the race.  Accept only its verified bytes.
            report = verify_archive(destination, dataset)
            report.update(
                {
                    "retrieval_mode": "verified_concurrent_cache",
                    "validated_request_urls": requested_urls,
                    "redirect_validation": "every_network_request_url_validated_before_open",
                }
            )
            return destination, report
        report = verify_archive(destination, dataset)
        report.update(
            {
                "retrieval_mode": "network",
                "validated_request_urls": requested_urls,
                "redirect_validation": "every_network_request_url_validated_before_open",
            }
        )
        return destination, report
    finally:
        temporary.unlink(missing_ok=True)


def validate_archive_members(
    members: Iterable[zipfile.ZipInfo],
    *,
    max_extracted_bytes: int,
    expected_extracted_bytes: int | None = None,
) -> dict[str, Any]:
    """Reject traversal, links, non-JPEG payloads, duplicates, and zip bombs."""

    member_list = list(members)
    names = [member.filename.rstrip("/") for member in member_list]
    _require(len(names) == len(set(names)), "archive contains duplicate member names")
    counts = {name: 0 for name in CLASS_COUNTS}
    total = 0
    file_count = 0
    allowed_directories = {DATASET_DIRECTORY} | {
        f"{DATASET_DIRECTORY}/{name}" for name in CLASS_COUNTS
    }
    for member, normalized in zip(member_list, names):
        pure = PurePosixPath(normalized)
        _require(not pure.is_absolute() and ".." not in pure.parts, "archive path traversal detected")
        mode = (member.external_attr >> 16) & 0xFFFF
        _require(not stat.S_ISLNK(mode), "archive links are forbidden")
        if member.is_dir():
            _require(
                mode == 0 or stat.S_ISDIR(mode),
                "archive directory has an unexpected file type",
            )
            _require(normalized in allowed_directories, "unexpected archive directory")
            continue
        _require(
            mode == 0 or stat.S_ISREG(mode),
            "archive payload has an unexpected file type",
        )
        _require(len(pure.parts) == 3 and pure.parts[0] == DATASET_DIRECTORY, "unexpected archive file path")
        class_name = pure.parts[1]
        _require(class_name in CLASS_COUNTS, "unexpected EuroSAT class directory")
        _require(JPEG_NAME.fullmatch(pure.name) is not None, "archive contains a non-JPEG or malformed image name")
        _require(pure.name.startswith(f"{class_name}_"), "image filename/class directory mismatch")
        _require((member.flag_bits & 0x1) == 0, "encrypted archive members are forbidden")
        _require(0 < member.file_size <= 1_000_000, "archive image exceeds its file cap")
        total += member.file_size
        file_count += 1
        counts[class_name] += 1
        _require(total <= max_extracted_bytes, "archive exceeds the extracted byte cap")
    _require(file_count == 27_000 and counts == CLASS_COUNTS, "EuroSAT image/class counts do not match the frozen corpus")
    if expected_extracted_bytes is not None:
        _require(total == expected_extracted_bytes, "archive extracted byte count mismatch")
    return {"member_count": len(member_list), "file_count": file_count, "declared_extracted_bytes": total, "class_counts": counts}


def _image_paths(dataset_dir: Path) -> list[Path]:
    _require(dataset_dir.is_dir() and not dataset_dir.is_symlink(), "invalid extracted dataset directory")
    for class_name in CLASS_COUNTS:
        class_dir = dataset_dir / class_name
        _require(class_dir.is_dir() and not class_dir.is_symlink(), f"invalid extracted class directory: {class_name}")
    paths = sorted(dataset_dir.glob("*/*.jpg"))
    _require(len(paths) == 27_000, "extracted EuroSAT image count mismatch")
    return paths


def _observed_extraction_paths(dataset_dir: Path) -> set[str]:
    observed: set[str] = set()
    allowed_directories = set(CLASS_COUNTS)
    for path in dataset_dir.iterdir():
        _require(not path.is_symlink(), "symlinks are forbidden in the extracted corpus")
        relative = path.relative_to(dataset_dir).as_posix()
        _require(path.is_dir() and relative in allowed_directories, "unexpected extracted root entry")
        for child in path.iterdir():
            _require(
                child.is_file() and not child.is_symlink(),
                f"unexpected extracted entry: {child.relative_to(dataset_dir).as_posix()}",
            )
            observed.add(child.relative_to(dataset_dir).as_posix())
    return observed


def _build_extraction_manifest(
    dataset_dir: Path, dataset: Mapping[str, Any]
) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for path in _image_paths(dataset_dir):
        relative = path.relative_to(dataset_dir).as_posix()
        _require(path.is_file() and not path.is_symlink(), f"invalid extracted image: {relative}")
        files[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {
        "schema_version": "1.0",
        "archive_sha256": dataset["sha256"],
        "files": files,
    }
    registration = dataset["extraction_manifest"]
    _require(
        len(canonical_json(manifest)) == registration["canonical_bytes"]
        and canonical_sha256(manifest) == registration["canonical_sha256"],
        "fresh extraction does not match the preregistered canonical manifest",
    )
    return manifest


def _verify_extraction_manifest(
    dataset_dir: Path,
    manifest_path: Path,
    dataset: Mapping[str, Any],
) -> dict[str, Any]:
    registration = dataset["extraction_manifest"]
    serialized = read_bounded_regular_file(
        manifest_path,
        int(registration["max_bytes"]),
        "extraction manifest",
    )
    _require(
        len(serialized) == registration["serialized_bytes"]
        and hashlib.sha256(serialized).hexdigest()
        == registration["serialized_sha256"],
        "serialized extraction manifest does not match its preregistered digest",
    )
    manifest = json.loads(serialized.decode("utf-8", errors="strict"))
    _require(isinstance(manifest, dict), "extraction manifest must be an object")
    _require(
        set(manifest) == {"schema_version", "archive_sha256", "files"},
        "invalid extraction manifest fields",
    )
    _require(manifest.get("schema_version") == registration["schema_version"], "invalid extraction manifest schema")
    _require(manifest.get("archive_sha256") == dataset["sha256"], "extraction is bound to another archive")
    _require(
        len(canonical_json(manifest)) == registration["canonical_bytes"]
        and canonical_sha256(manifest) == registration["canonical_sha256"],
        "extraction manifest does not match the preregistered canonical digest",
    )
    files = manifest.get("files")
    _require(isinstance(files, dict) and len(files) == registration["file_count"], "extraction manifest image count mismatch")
    counts = {name: 0 for name in CLASS_COUNTS}
    declared_total = 0
    content_digests: set[str] = set()
    for relative, expected in files.items():
        _require(isinstance(relative, str), "extraction manifest path must be a string")
        pure = PurePosixPath(relative)
        _require(
            not pure.is_absolute()
            and ".." not in pure.parts
            and len(pure.parts) == 2,
            "invalid extraction manifest path",
        )
        class_name = pure.parts[0]
        _require(class_name in CLASS_COUNTS, "unknown extraction-manifest class")
        _require(
            JPEG_NAME.fullmatch(pure.name) is not None
            and pure.name.startswith(f"{class_name}_"),
            "invalid extraction-manifest JPEG name",
        )
        _require(
            isinstance(expected, dict) and set(expected) == {"bytes", "sha256"},
            "invalid extraction-manifest file record",
        )
        size = expected["bytes"]
        digest = expected["sha256"]
        _require(
            isinstance(size, int)
            and not isinstance(size, bool)
            and 0 < size <= registration["max_file_bytes"],
            "invalid extraction-manifest file size",
        )
        _require(_is_lower_hex(digest, 64), "invalid extraction-manifest file digest")
        counts[class_name] += 1
        declared_total += size
        _require(declared_total <= dataset["max_extracted_bytes"], "cached extraction exceeds the expanded byte cap")
        content_digests.add(digest)
    _require(counts == CLASS_COUNTS, "cached extraction class counts do not match EuroSAT")
    _require(
        declared_total == registration["total_file_bytes"]
        == dataset["extracted_bytes"],
        "cached extraction total byte count mismatch",
    )
    _require(
        len(content_digests) == dataset["expected_unique_image_sha256"],
        "cached extraction contains duplicate image content",
    )
    observed = _observed_extraction_paths(dataset_dir)
    _require(observed == set(files), "extraction manifest path registry mismatch")
    for relative, expected in files.items():
        path = dataset_dir / relative
        _require(path.is_file() and not path.is_symlink(), f"invalid extracted image: {relative}")
        _require(path.stat().st_size == expected["bytes"], f"extracted byte count mismatch: {relative}")
        _require(sha256_file(path) == expected["sha256"], f"extracted digest mismatch: {relative}")
    return manifest


def prepare_verified_extraction(archive: Path, cache_dir: Path, dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize only the validated 27,000 JPEG members."""

    dataset_dir = cache_dir / DATASET_DIRECTORY
    manifest_path = cache_dir / "eurosat-rgb-extraction-manifest.json"
    if dataset_dir.exists() or manifest_path.exists():
        _require(dataset_dir.is_dir() and manifest_path.is_file(), "incomplete cached extraction; manual cleanup required")
        return _verify_extraction_manifest(dataset_dir, manifest_path, dataset)

    temporary_root = Path(tempfile.mkdtemp(prefix=".eurosat-extract-", dir=cache_dir))
    try:
        with zipfile.ZipFile(archive, mode="r") as bundle:
            members = bundle.infolist()
            validate_archive_members(
                members,
                max_extracted_bytes=int(dataset["max_extracted_bytes"]),
                expected_extracted_bytes=int(dataset["extracted_bytes"]),
            )
            (temporary_root / DATASET_DIRECTORY).mkdir()
            for member in members:
                normalized = member.filename.rstrip("/")
                if member.is_dir():
                    if normalized != DATASET_DIRECTORY:
                        (temporary_root / normalized).mkdir(exist_ok=True)
                    continue
                destination = temporary_root / normalized
                destination.parent.mkdir(parents=True, exist_ok=True)
                copied = 0
                with bundle.open(member, "r") as source, destination.open("xb") as stream:
                    while chunk := source.read(1024 * 1024):
                        copied += len(chunk)
                        _require(copied <= member.file_size, f"archive member exceeded declared size: {normalized}")
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                _require(copied == member.file_size, f"archive member size mismatch: {normalized}")
        temporary_dataset = temporary_root / DATASET_DIRECTORY
        manifest = _build_extraction_manifest(temporary_dataset, dataset)
        serialized = json.dumps(
            manifest, allow_nan=False, indent=2, sort_keys=True
        ) + "\n"
        registration = dataset["extraction_manifest"]
        _require(
            len(serialized.encode("utf-8")) == registration["serialized_bytes"]
            and hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            == registration["serialized_sha256"],
            "fresh serialized extraction manifest does not match preregistration",
        )
        _require(not dataset_dir.exists(), "concurrent EuroSAT extraction detected")
        os.replace(temporary_dataset, dataset_dir)
        atomic_write_new(manifest_path, serialized)
        return _verify_extraction_manifest(dataset_dir, manifest_path, dataset)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def validate_decoded_images(
    dataset_dir: Path, registration: Mapping[str, Any]
) -> dict[str, Any]:
    """Decode every JPEG and fail if its actual image contract differs."""

    try:
        from PIL import Image
    except (ImportError, OSError) as exc:
        raise RuntimeError("Pillow is required to validate decoded EuroSAT images") from exc
    count = 0
    for path in _image_paths(dataset_dir):
        with Image.open(path) as image:
            image.load()
            _require(image.format == registration["format"], "decoded image format mismatch")
            _require(image.mode == registration["mode"], "decoded image mode mismatch")
            _require(
                image.size == (registration["width"], registration["height"]),
                "decoded image dimensions mismatch",
            )
        count += 1
    _require(count == registration["expected_images"], "decoded image count mismatch")
    return {
        "images_decoded": count,
        "format": registration["format"],
        "mode": registration["mode"],
        "width": registration["width"],
        "height": registration["height"],
        "raw_pixels_persisted": False,
    }


def _public_version(version: str) -> str:
    return version.split("+", 1)[0]


def require_ml_runtime(config: Mapping[str, Any]) -> tuple[Any, Any]:
    try:
        import torch
        import torchvision
    except (ImportError, OSError) as exc:
        raise RuntimeError("torch and torchvision are required for the vision experiment") from exc
    runtime = config["runtime"]
    _require(_public_version(torch.__version__) == runtime["torch_version"], "installed torch version does not match the frozen runtime")
    _require(_public_version(torchvision.__version__) == runtime["torchvision_version"], "installed torchvision version does not match the frozen runtime")
    _require(torch.cuda.is_available(), "the registered full-scale experiment requires CUDA")
    return torch, torchvision


def seed_runtime(
    torch: Any, seed: int, *, deterministic_algorithms_mode: str
) -> None:
    import random

    random.seed(seed)
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - torchvision depends on numpy.
        raise RuntimeError("numpy is required by torchvision") from exc
    numpy.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    _require(
        deterministic_algorithms_mode in {"error", "warn_only"},
        "deterministic algorithm mode must be error or warn_only",
    )
    torch.use_deterministic_algorithms(
        True,
        warn_only=deterministic_algorithms_mode == "warn_only",
    )
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


@contextmanager
def capture_registered_cuda_nondeterminism(
    config: Mapping[str, Any], phase: str
) -> Iterable[dict[str, Any]]:
    """Capture warnings and reject unexpected CUDA nondeterminism warnings."""

    policy = config["runtime"]["reproducibility"]
    allowed_kernels = tuple(policy["known_nondeterministic_cuda_kernels"])
    state: dict[str, Any] = {}
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        try:
            yield state
        except Exception:
            raise
        else:
            kernel_counts: Counter[str] = Counter()
            message_digests: Counter[str] = Counter()
            other_warning_digests: Counter[str] = Counter()
            unexpected_nondeterminism: list[str] = []
            for record in records:
                message = str(record.message)
                lowered = message.lower()
                is_nondeterminism_warning = (
                    "nondeterministic" in lowered
                    or (
                        "deterministic" in lowered
                        and (
                            "implementation" in lowered
                            or "algorithm" in lowered
                        )
                    )
                )
                if not is_nondeterminism_warning:
                    other_key = (
                        f"{record.category.__name__}:"
                        f"{hashlib.sha256(message.encode('utf-8')).hexdigest()}"
                    )
                    other_warning_digests[other_key] += 1
                    continue
                matches = [
                    kernel
                    for kernel in allowed_kernels
                    if kernel in message
                ]
                if len(matches) != 1 or not issubclass(record.category, UserWarning):
                    unexpected_nondeterminism.append(
                        f"{record.category.__name__}:{message[:500]}"
                    )
                    continue
                kernel_counts[matches[0]] += 1
                message_digests[hashlib.sha256(message.encode("utf-8")).hexdigest()] += 1
            _require(
                not unexpected_nondeterminism,
                f"unexpected nondeterminism warning during {phase}: {unexpected_nondeterminism[:3]}",
            )
            state.update(
                {
                    "phase": phase,
                    "warning_count": sum(kernel_counts.values()),
                    "kernel_counts": dict(sorted(kernel_counts.items())),
                    "message_sha256_counts": dict(sorted(message_digests.items())),
                    "unexpected_nondeterminism_warning_count": 0,
                    "other_warning_count": sum(other_warning_digests.values()),
                    "other_warning_sha256_counts": dict(
                        sorted(other_warning_digests.items())
                    ),
                }
            )


def summarize_cuda_nondeterminism(
    config: Mapping[str, Any], phases: list[Mapping[str, Any]]
) -> dict[str, Any]:
    policy = config["runtime"]["reproducibility"]
    totals: Counter[str] = Counter()
    other_warning_count = 0
    for phase in phases:
        totals.update(phase["kernel_counts"])
        other_warning_count += int(phase["other_warning_count"])
    required = policy["known_nondeterministic_cuda_kernels"]
    if policy["known_warning_must_be_observed"]:
        _require(
            all(totals[kernel] > 0 for kernel in required),
            "registered CUDA nondeterminism warning was not observed",
        )
    return {
        "seeded": policy["seeded"],
        "split_and_batch_order_deterministic": policy[
            "split_and_batch_order_deterministic"
        ],
        "deterministic_algorithms_mode": policy["deterministic_algorithms_mode"],
        "bitwise_reproducible": policy["bitwise_reproducible"],
        "single_run_variance_estimated": policy[
            "single_run_variance_estimated"
        ],
        "known_nondeterministic_cuda_kernels": list(required),
        "observed_kernel_warning_counts": dict(sorted(totals.items())),
        "unexpected_nondeterminism_warning_policy": policy[
            "unexpected_nondeterminism_warning_policy"
        ],
        "unexpected_nondeterminism_warning_count": 0,
        "other_warning_count": other_warning_count,
        "phases": [dict(phase) for phase in phases],
    }


class IndexedDataset:
    """Apply an immutable subset and expose transient source positions."""

    def __init__(self, dataset: Any, indices: Iterable[int]) -> None:
        self.dataset = dataset
        self.indices = tuple(indices)

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int) -> tuple[Any, int, int]:
        source_index = self.indices[index]
        image, label = self.dataset[source_index]
        return image, int(label), source_index


def stratified_path_split(
    samples: Iterable[tuple[str, int]],
    root: Path,
    class_names: list[str],
    expected_counts: Mapping[str, int],
    *,
    seed: int,
    train_fraction: float,
) -> tuple[list[int], list[int], dict[str, Any]]:
    """Split each natural class by a stable hash of its relative path."""

    sample_list = list(samples)
    by_class: dict[int, list[int]] = {index: [] for index in range(len(class_names))}
    relatives: dict[int, str] = {}
    for index, (path, label) in enumerate(sample_list):
        _require(label in by_class, "sample label is outside the class registry")
        relative = Path(path).resolve().relative_to(root.resolve()).as_posix()
        relatives[index] = relative
        by_class[label].append(index)
    train_indices: list[int] = []
    test_indices: list[int] = []
    train_counts: list[int] = []
    test_counts: list[int] = []
    for label, class_name in enumerate(class_names):
        candidates = by_class[label]
        _require(len(candidates) == expected_counts[class_name], f"class count mismatch: {class_name}")
        ordered = sorted(
            candidates,
            key=lambda index: (
                hashlib.sha256(f"{seed}:{relatives[index]}".encode("utf-8")).hexdigest(),
                relatives[index],
            ),
        )
        boundary = int(len(ordered) * train_fraction)
        train_indices.extend(ordered[:boundary])
        test_indices.extend(ordered[boundary:])
        train_counts.append(boundary)
        test_counts.append(len(ordered) - boundary)
    _require(set(train_indices).isdisjoint(test_indices), "split overlap detected")
    details = {
        "train_class_counts": train_counts,
        "test_class_counts": test_counts,
        "train_relative_path_set_sha256": canonical_sha256(
            sorted(relatives[index] for index in train_indices)
        ),
        "test_relative_path_set_sha256": canonical_sha256(
            sorted(relatives[index] for index in test_indices)
        ),
    }
    return train_indices, test_indices, details


def validate_split_content_digests(
    train_indices: Iterable[int],
    test_indices: Iterable[int],
    relative_by_index: Mapping[int, str],
    manifest_files: Mapping[str, Mapping[str, Any]],
    *,
    expected_overlap: int,
) -> dict[str, int]:
    train_list = list(train_indices)
    test_list = list(test_indices)
    train_content = {
        manifest_files[relative_by_index[index]]["sha256"] for index in train_list
    }
    test_content = {
        manifest_files[relative_by_index[index]]["sha256"] for index in test_list
    }
    cross_split_overlap = train_content & test_content
    _require(
        len(train_content) == len(train_list)
        and len(test_content) == len(test_list),
        "duplicate image content exists within a split",
    )
    _require(
        len(cross_split_overlap) == expected_overlap,
        "image content digest overlap exists across train and test",
    )
    return {
        "unique_image_content_sha256": len(train_content | test_content),
        "train_unique_content_sha256": len(train_content),
        "test_unique_content_sha256": len(test_content),
        "cross_split_content_sha256_overlap": len(cross_split_overlap),
    }


def load_datasets(
    torchvision: Any,
    cache_dir: Path,
    config: Mapping[str, Any],
    extraction_manifest: Mapping[str, Any],
) -> tuple[Any, Any, dict[str, Any]]:
    transforms = torchvision.transforms
    interpolation = transforms.InterpolationMode.BILINEAR
    preprocessing = config["preprocessing"]
    transform = transforms.Compose(
        [
            transforms.Resize(
                tuple(preprocessing["resize"]),
                interpolation=interpolation,
                antialias=True,
            ),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=preprocessing["normalize_mean"],
                std=preprocessing["normalize_std"],
            ),
        ]
    )
    base = torchvision.datasets.ImageFolder(
        root=str(cache_dir / DATASET_DIRECTORY), transform=transform
    )
    dataset = config["dataset"]
    _require(len(base) == dataset["total_rows"], "EuroSAT row count mismatch")
    _require(base.classes == sorted(CLASS_COUNTS), "EuroSAT class registry mismatch")
    train_indices, test_indices, split_details = stratified_path_split(
        base.samples,
        cache_dir / DATASET_DIRECTORY,
        base.classes,
        CLASS_COUNTS,
        seed=int(dataset["split"]["seed"]),
        train_fraction=float(dataset["split"]["train_fraction"]),
    )
    _require(len(train_indices) == dataset["train_rows"] and len(test_indices) == dataset["test_rows"], "EuroSAT split row counts mismatch")
    _require(set(train_indices).isdisjoint(test_indices), "EuroSAT split overlap detected")
    _require(
        split_details["train_relative_path_set_sha256"]
        == dataset["split"]["train_relative_path_set_sha256"]
        == FROZEN_TRAIN_ROSTER_SHA256,
        "training roster path digest does not match preregistration",
    )
    _require(
        split_details["test_relative_path_set_sha256"]
        == dataset["split"]["test_relative_path_set_sha256"]
        == FROZEN_TEST_ROSTER_SHA256,
        "test roster path digest does not match preregistration",
    )
    root = (cache_dir / DATASET_DIRECTORY).resolve()
    relative_by_index = {
        index: Path(path).resolve().relative_to(root).as_posix()
        for index, (path, _label) in enumerate(base.samples)
    }
    content_details = validate_split_content_digests(
        train_indices,
        test_indices,
        relative_by_index,
        extraction_manifest["files"],
        expected_overlap=int(dataset["expected_cross_split_content_overlap"]),
    )
    report = {
        "train_rows": len(train_indices),
        "test_rows": len(test_indices),
        "total_rows": len(base),
        "native_shape": [3, 64, 64],
        **split_details,
        "class_names": base.classes,
        "split_algorithm": dataset["split"]["algorithm"],
        "synthetic_samples": False,
        "augmented_samples": False,
        "raw_images_retained_in_report_or_telemetry": False,
        "raw_labels_retained_in_report_or_telemetry": False,
        "verified_source_cache_retained": True,
        **content_details,
        "roster_digest_visibility": "internal_provenance_not_a_recipient_interface",
        "benchmark_split_publicly_reconstructible": True,
    }
    return IndexedDataset(base, train_indices), IndexedDataset(base, test_indices), report


def build_model(torchvision: Any, model_config: Mapping[str, Any]) -> Any:
    constructor = getattr(torchvision.models, str(model_config["constructor"]))
    model = constructor(weights=None, num_classes=int(model_config["num_classes"]))
    named_modules = dict(model.named_modules())
    _require(
        all(name in named_modules for name in model_config["hook_modules"]),
        f"torchvision module graph does not match {model_config['key']} allowlist",
    )
    return model


def model_state_sha256(model: Any) -> str:
    """Hash tensors incrementally; the state itself is never persisted."""

    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        metadata = {
            "name": name,
            "dtype": str(value.dtype),
            "shape": list(value.shape),
        }
        encoded = canonical_json(metadata)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(value.numpy().tobytes(order="C"))
    return digest.hexdigest()


def model_gradient_sha256(model: Any) -> str:
    """Hash the complete named gradient state without persisting gradients."""

    digest = hashlib.sha256()
    for name, parameter in sorted(model.named_parameters()):
        gradient = parameter.grad
        metadata: dict[str, Any] = {"name": name, "present": gradient is not None}
        if gradient is not None:
            value = gradient.detach().cpu().contiguous()
            _require(bool(value.isfinite().all().item()), "non-interference gradient was non-finite")
            metadata.update({"dtype": str(value.dtype), "shape": list(value.shape)})
        encoded = canonical_json(metadata)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        if gradient is not None:
            digest.update(value.numpy().tobytes(order="C"))
    return digest.hexdigest()


def run_hook_non_interference_control(
    torch: Any,
    torchvision: Any,
    train_dataset: IndexedDataset,
    config: Mapping[str, Any],
    model_config: Mapping[str, Any],
    device: Any,
) -> dict[str, Any]:
    """Compare one strict-deterministic CPU step with and without the collector."""

    AggregateTrainingHookCollector = bound_hook_collector()

    registered = config["hook_non_interference_control"]
    _require(
        device.type == registered["control_device"] == "cpu",
        "the exact non-interference control must execute on CPU",
    )
    count = int(registered["paired_real_examples"])
    examples = [train_dataset[index] for index in range(count)]
    images = torch.stack([item[0] for item in examples]).to(device)
    labels = torch.tensor([item[1] for item in examples], dtype=torch.long, device=device)
    source_indices = [int(item[2]) for item in examples]
    training = config["training"]

    def execute(*, hooked: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
        seed_runtime(
            torch,
            int(registered["seed"]),
            deterministic_algorithms_mode="error",
        )
        model = build_model(torchvision, model_config).to(device)
        optimizer = torch.optim.SGD(
            model.parameters(),
            lr=float(training["learning_rate"]),
            momentum=float(training["momentum"]),
            weight_decay=float(training["weight_decay"]),
        )
        initial = model_state_sha256(model)
        model.train()
        optimizer.zero_grad(set_to_none=True)
        collector = None
        if hooked:
            collector = AggregateTrainingHookCollector(
                model,
                module_names=model_config["hook_modules"],
                expected_steps=1,
                max_events=2 * len(model_config["hook_modules"]) + 1,
                fail_on_nonfinite=True,
            )
            with collector:
                logits = model(images)
                loss = torch.nn.functional.cross_entropy(logits, labels)
                loss.backward()
                collector.step(
                    loss,
                    step=0,
                    epoch=0,
                    batch_index=0,
                    model=model,
                    learning_rate=float(training["learning_rate"]),
                    tokens=int(images.numel()),
                    target_tokens=int(labels.numel()),
                    batch_manifest_sha256=canonical_sha256(
                        {"control": True, "source_indices": source_indices}
                    ),
                )
        else:
            logits = model(images)
            loss = torch.nn.functional.cross_entropy(logits, labels)
            loss.backward()
        _require(bool(torch.isfinite(loss).item()), "non-interference loss was non-finite")
        result = {
            "initial_state_sha256": initial,
            "loss_hex": float(loss.detach().item()).hex(),
            "gradient_sha256": model_gradient_sha256(model),
        }
        optimizer.step()
        result["post_step_state_sha256"] = model_state_sha256(model)
        coverage = collector.finalize(expected_steps=1) if collector is not None else None
        if coverage is not None:
            coverage.pop("events")
            _require(coverage["coverage_status"] == "complete", "control hook coverage was incomplete")
            _require(coverage["nonfinite_elements"] == 0, "control hook telemetry was non-finite")
            _require(coverage["handles_removed"] is True, "control hooks were not removed")
        del model
        return result, coverage

    baseline, _unused = execute(hooked=False)
    instrumented, coverage = execute(hooked=True)
    comparisons = {
        field: baseline[field] == instrumented[field]
        for field in registered["comparisons"]
    }
    _require(all(comparisons.values()), "aggregate hooks changed paired training behavior")
    return {
        "status": "PASS",
        "paired_real_examples": count,
        "source_index_set_sha256": canonical_sha256(sorted(source_indices)),
        "seed": int(registered["seed"]),
        "control_device": "cpu",
        "exact_match_required": True,
        "cuda_noninterference_proven": False,
        "comparisons": comparisons,
        "baseline": baseline,
        "instrumented": instrumented,
        "hook_coverage": coverage,
        "raw_images_or_labels_retained": False,
    }


def evaluate_model(torch: Any, model: Any, loader: Any, device: Any) -> dict[str, Any]:
    model.eval()
    total_loss = 0.0
    correct = 0
    examples = 0
    torch.cuda.synchronize(device)
    started = time.perf_counter()
    with torch.no_grad():
        for images, labels, _indices in loader:
            images = images.to(device, non_blocking=False)
            labels = labels.to(device, non_blocking=False)
            logits = model(images)
            if not bool(torch.isfinite(logits).all().item()):
                raise RuntimeError("evaluation logits contained non-finite values")
            loss_sum = torch.nn.functional.cross_entropy(logits, labels, reduction="sum")
            if not bool(torch.isfinite(loss_sum).item()):
                raise RuntimeError("evaluation loss was non-finite")
            total_loss += float(loss_sum.item())
            correct += int((logits.argmax(dim=1) == labels).sum().item())
            examples += int(labels.numel())
    torch.cuda.synchronize(device)
    duration = time.perf_counter() - started
    _require(examples > 0 and duration > 0.0, "evaluation observed no data or duration")
    return {
        "examples": examples,
        "mean_cross_entropy": total_loss / examples,
        "top1_accuracy": correct / examples,
        "correct": correct,
        "duration_seconds": duration,
        "examples_per_second": examples / duration,
    }


def build_red_team_subset(test_dataset: IndexedDataset, count: int, seed: int) -> IndexedDataset:
    """Choose a deterministic near-balanced subset without persisting paths."""

    by_label: dict[int, list[int]] = {label: [] for label in range(10)}
    for source_index in test_dataset.indices:
        by_label[int(test_dataset.dataset.targets[source_index])].append(source_index)
    selected: list[int] = []
    base, remainder = divmod(count, 10)
    for label in range(10):
        target = base + (1 if label < remainder else 0)
        ordered = sorted(
            by_label[label],
            key=lambda index: hashlib.sha256(f"{seed}:{index}".encode("ascii")).hexdigest(),
        )
        selected.extend(ordered[:target])
    _require(len(selected) == count, "red-team subset size mismatch")
    return IndexedDataset(test_dataset.dataset, selected)


def apply_brightness(pixels: Any, factor: float) -> Any:
    return (pixels * factor).clamp(0.0, 1.0)


def apply_deterministic_noise(
    torch: Any, pixels: Any, standard_deviation: float, generator: Any
) -> Any:
    noise = torch.randn(
        pixels.shape,
        generator=generator,
        dtype=pixels.dtype,
        device="cpu",
    ).to(pixels.device)
    return (pixels + noise * standard_deviation).clamp(0.0, 1.0)


def apply_fgsm_pixels(pixels: Any, normalized_gradient: Any, epsilon: float) -> Any:
    # RGB normalization scales are positive, so the normalized-input gradient
    # has the same sign as the pixel-space gradient.
    return (pixels + epsilon * normalized_gradient.sign()).clamp(0.0, 1.0)


def measured_pixel_linf(torch: Any, left: Any, right: Any) -> float:
    value = float((left - right).detach().abs().max().item())
    _require(math.isfinite(value), "perturbation L-infinity norm was non-finite")
    return value


def run_red_team_screens(
    torch: Any,
    model: Any,
    test_dataset: IndexedDataset,
    config: Mapping[str, Any],
    device: Any,
) -> dict[str, Any]:
    """Run bounded brightness, Gaussian-noise, and white-box FGSM screens."""

    registered = config["red_team"]
    subset = build_red_team_subset(test_dataset, int(registered["test_rows"]), int(registered["seed"]))
    loader = torch.utils.data.DataLoader(
        subset,
        batch_size=int(config["evaluation"]["batch_size"]),
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )
    mean = torch.tensor(config["preprocessing"]["normalize_mean"], device=device).view(1, 3, 1, 1)
    std = torch.tensor(config["preprocessing"]["normalize_std"], device=device).view(1, 3, 1, 1)
    screens = registered["screens"]
    noise_generator = torch.Generator(device="cpu")
    noise_generator.manual_seed(int(registered["seed"]))
    totals = {
        name: {
            "loss": 0.0,
            "correct": 0,
            "attack_successes_on_clean_correct": 0,
            "clean_correct_denominator": 0,
            "measured_max_pixel_linf": 0.0,
        }
        for name in ("clean", "brightness", "gaussian_noise", "fgsm")
    }
    examples = 0
    model.eval()

    def score(
        name: str,
        inputs: Any,
        labels: Any,
        clean_correct: Any,
        pixel_linf: float,
    ) -> None:
        with torch.no_grad():
            logits = model(inputs)
            _require(bool(torch.isfinite(logits).all().item()), f"{name} logits were non-finite")
            totals[name]["loss"] += float(torch.nn.functional.cross_entropy(logits, labels, reduction="sum").item())
            predictions = logits.argmax(1)
            totals[name]["correct"] += int((predictions == labels).sum().item())
            totals[name]["attack_successes_on_clean_correct"] += int(
                (clean_correct & (predictions != labels)).sum().item()
            )
            totals[name]["clean_correct_denominator"] += int(clean_correct.sum().item())
            totals[name]["measured_max_pixel_linf"] = max(
                totals[name]["measured_max_pixel_linf"], pixel_linf
            )

    for images, labels, _indices in loader:
        images = images.to(device)
        labels = labels.to(device)
        batch = int(labels.numel())
        pixels = (images * std + mean).clamp(0.0, 1.0)
        with torch.no_grad():
            clean_logits = model(images)
            _require(bool(torch.isfinite(clean_logits).all().item()), "clean logits were non-finite")
            clean_correct = clean_logits.argmax(1) == labels
        # Score clean through the same aggregate path; by definition it cannot
        # be an attack success against itself.
        score("clean", images, labels, clean_correct, 0.0)
        bright = apply_brightness(pixels, float(screens["brightness_factor"]))
        score(
            "brightness",
            (bright - mean) / std,
            labels,
            clean_correct,
            measured_pixel_linf(torch, bright, pixels),
        )
        noisy = apply_deterministic_noise(
            torch,
            pixels,
            float(screens["gaussian_noise_std"]),
            noise_generator,
        )
        score(
            "gaussian_noise",
            (noisy - mean) / std,
            labels,
            clean_correct,
            measured_pixel_linf(torch, noisy, pixels),
        )
        adversarial_input = images.detach().clone().requires_grad_(True)
        logits = model(adversarial_input)
        _require(bool(torch.isfinite(logits).all().item()), "FGSM source logits were non-finite")
        loss = torch.nn.functional.cross_entropy(logits, labels)
        gradient = torch.autograd.grad(loss, adversarial_input, only_inputs=True)[0]
        _require(bool(torch.isfinite(gradient).all().item()), "FGSM gradient was non-finite")
        epsilon = float(screens["fgsm_epsilon"])
        adversarial_pixels = apply_fgsm_pixels(pixels, gradient, epsilon)
        fgsm_linf = measured_pixel_linf(torch, adversarial_pixels, pixels)
        _require(
            fgsm_linf <= epsilon + float(registered["max_linf_tolerance"]),
            "FGSM exceeded its registered pixel-space L-infinity bound",
        )
        score(
            "fgsm",
            (adversarial_pixels - mean) / std,
            labels,
            clean_correct,
            fgsm_linf,
        )
        examples += batch
    _require(examples == registered["test_rows"], "red-team evaluation was incomplete")
    clean_accuracy = totals["clean"]["correct"] / examples
    results = {}
    for name, values in totals.items():
        accuracy = values["correct"] / examples
        denominator = values["clean_correct_denominator"]
        results[name] = {
            "mean_cross_entropy": values["loss"] / examples,
            "top1_accuracy": accuracy,
            "accuracy_drop_from_clean": clean_accuracy - accuracy,
            "attack_successes_on_clean_correct": values[
                "attack_successes_on_clean_correct"
            ],
            "clean_correct_denominator": denominator,
            "attack_success_rate_on_clean_correct": (
                values["attack_successes_on_clean_correct"] / denominator
                if denominator
                else None
            ),
            "measured_max_pixel_linf": values["measured_max_pixel_linf"],
        }
    _require(results["clean"]["attack_successes_on_clean_correct"] == 0, "clean ASR invariant failed")
    _require(
        results["fgsm"]["measured_max_pixel_linf"]
        <= float(screens["fgsm_epsilon"])
        + float(registered["max_linf_tolerance"]),
        "aggregate FGSM L-infinity assertion failed",
    )
    return {
        "examples": examples,
        "condition_evaluations": examples * len(totals),
        "subset_index_set_sha256": canonical_sha256(sorted(subset.indices)),
        "screens": results,
        "threat_model": registered["threat_model"],
        "attack_success_denominator": registered["attack_success_denominator"],
        "fgsm_norm": registered["fgsm_norm"],
        "fgsm_registered_epsilon": float(screens["fgsm_epsilon"]),
        "fgsm_norm_assertion_passed": True,
        "evidence_direction": registered["evidence_direction"],
        "descriptive_only": registered["descriptive_only"],
        "can_clear": registered["can_clear"],
        "can_block": registered["can_block"],
        "attack_battery_eligible": registered["attack_battery_eligible"],
        "assessment_input_emitted": registered["assessment_input_emitted"],
        "requires_approved_recollection": registered[
            "requires_approved_recollection"
        ],
        "limitations": "bounded known-perturbation screen; not a robustness guarantee",
    }


def replay_collector_event_chain(
    events: Iterable[Mapping[str, Any]],
    genesis_sha256: str,
    *,
    expected_head_sha256: str | None = None,
) -> dict[str, Any]:
    """Independently replay the collector's hash chain from its context genesis."""

    _require(_is_lower_hex(genesis_sha256, 64), "invalid telemetry genesis digest")
    previous = genesis_sha256
    count = 0
    for count, stored in enumerate(events, start=1):
        _require(isinstance(stored, Mapping), "telemetry event must be an object")
        event = dict(stored)
        _require(event.get("sequence") == count - 1, "telemetry sequence mismatch")
        _require(event.get("previous_sha256") == previous, "telemetry previous digest mismatch")
        claimed = event.pop("event_sha256", None)
        _require(_is_lower_hex(claimed, 64), "telemetry event digest is invalid")
        measured = hashlib.sha256(canonical_json(event)).hexdigest()
        _require(claimed == measured, "telemetry event digest mismatch")
        previous = claimed
    if expected_head_sha256 is not None:
        _require(previous == expected_head_sha256, "telemetry chain head mismatch")
    return {
        "event_count": count,
        "event_chain_genesis_sha256": genesis_sha256,
        "event_chain_head_sha256": previous,
        "independent_replay_passed": True,
    }


def serialize_context_bound_telemetry(
    events: Iterable[Mapping[str, Any]], context: Mapping[str, Any]
) -> str:
    header = {
        "record_type": "run_context",
        "schema_version": "1.0",
        "context": dict(context),
        "context_sha256": canonical_sha256(context),
    }
    return "".join(
        canonical_json(record).decode("ascii") + "\n"
        for record in [header, *list(events)]
    )


def replay_context_bound_telemetry(payload: str) -> dict[str, Any]:
    """Parse and independently replay a published context-bound JSONL ledger."""

    _require(payload.endswith("\n"), "telemetry JSONL must end with a newline")
    lines = payload.splitlines()
    _require(len(lines) >= 2, "telemetry ledger must contain context and events")
    records = [json.loads(line) for line in lines]
    header = records[0]
    _require(
        isinstance(header, dict)
        and set(header)
        == {"record_type", "schema_version", "context", "context_sha256"}
        and header["record_type"] == "run_context"
        and header["schema_version"] == "1.0"
        and isinstance(header["context"], dict),
        "invalid telemetry context header",
    )
    _require(
        canonical_sha256(header["context"]) == header["context_sha256"],
        "telemetry context digest mismatch",
    )
    replay = replay_collector_event_chain(records[1:], header["context_sha256"])
    replay["context_sha256"] = header["context_sha256"]
    replay["payload_sha256"] = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return replay


def train_model(
    torch: Any,
    model: Any,
    train_dataset: Any,
    config: Mapping[str, Any],
    model_config: Mapping[str, Any],
    device: Any,
    run_context: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    AggregateTrainingHookCollector = bound_hook_collector()

    training = config["training"]
    runtime = config["runtime"]
    hooks = config["hooks"]
    generator = torch.Generator()
    generator.manual_seed(int(training["seed"]))
    loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=int(training["batch_size"]),
        shuffle=True,
        generator=generator,
        num_workers=int(runtime["num_workers"]),
        pin_memory=False,
        drop_last=False,
    )
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=float(training["learning_rate"]),
        momentum=float(training["momentum"]),
        weight_decay=float(training["weight_decay"]),
    )
    expected_steps = int(training["expected_optimizer_steps_per_model"])
    collector = AggregateTrainingHookCollector(
        model,
        module_names=model_config["hook_modules"],
        expected_steps=expected_steps,
        max_events=int(hooks["max_events_per_model"]),
        fail_on_nonfinite=True,
        context_sha256=canonical_sha256(run_context),
    )

    model.train()
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    started = time.perf_counter()
    examples = 0
    step_index = 0
    total_loss = 0.0
    batch_order = hashlib.sha256()
    with collector:
        for epoch in range(int(training["epochs"])):
            for batch_index, (images, labels, indices) in enumerate(loader):
                batch_size = int(labels.numel())
                batch_manifest = canonical_sha256(
                    {
                        "epoch": epoch,
                        "batch_index": batch_index,
                        "dataset_indices": [int(index) for index in indices.tolist()],
                    }
                )
                batch_order.update(bytes.fromhex(batch_manifest))
                images = images.to(device, non_blocking=False)
                labels = labels.to(device, non_blocking=False)
                optimizer.zero_grad(set_to_none=True)
                logits = model(images)
                loss = torch.nn.functional.cross_entropy(logits, labels)
                loss.backward()
                collector.step(
                    loss,
                    step=step_index,
                    epoch=epoch,
                    batch_index=batch_index,
                    model=model,
                    learning_rate=float(training["learning_rate"]),
                    # The reused LLM collector calls this field ``tokens``.
                    # Here it is explicitly the number of normalized image
                    # scalar inputs; no pixel values are retained.
                    tokens=int(images.numel()),
                    target_tokens=batch_size,
                    batch_manifest_sha256=batch_manifest,
                )
                optimizer.step()
                total_loss += float(loss.detach().item()) * batch_size
                examples += batch_size
                step_index += 1
    torch.cuda.synchronize(device)
    duration = time.perf_counter() - started
    telemetry = collector.finalize(expected_steps=expected_steps)
    events = telemetry.pop("events")

    _require(step_index == expected_steps, "training step count mismatch")
    _require(examples == config["dataset"]["train_rows"], "training did not consume the full split")
    _require(telemetry["coverage_status"] == "complete", "hook coverage was incomplete")
    _require(telemetry["nonfinite_elements"] == 0, "hook telemetry was non-finite")
    _require(telemetry["handles_removed"] is True, "hook handles were not removed")
    _require(math.isfinite(total_loss) and duration > 0.0, "training aggregate was not finite")

    context_sha256 = canonical_sha256(run_context)
    independent_collector_replay = replay_collector_event_chain(
        events,
        context_sha256,
        expected_head_sha256=telemetry["event_chain_head_sha256"],
    )
    telemetry_payload = serialize_context_bound_telemetry(events, run_context)
    independent_payload_replay = replay_context_bound_telemetry(telemetry_payload)
    _require(
        independent_payload_replay["event_chain_head_sha256"]
        == telemetry["event_chain_head_sha256"],
        "published telemetry replay did not reach the collector chain head",
    )
    telemetry.update(
        {
            "events_externalized": True,
            "event_file_sha256": hashlib.sha256(telemetry_payload.encode("ascii")).hexdigest(),
            "run_context": dict(run_context),
            "run_context_sha256": context_sha256,
            "collector_replay": independent_collector_replay,
            "published_payload_replay": independent_payload_replay,
            "legacy_tokens_field_semantics": "normalized_input_scalar_elements",
            "legacy_target_tokens_field_semantics": "classification_targets",
        }
    )
    training_report = {
        "epochs": int(training["epochs"]),
        "optimizer_steps": step_index,
        "examples_seen": examples,
        "normalized_input_scalar_elements_seen": examples
        * 3
        * int(config["preprocessing"]["resize"][0])
        * int(config["preprocessing"]["resize"][1]),
        "mean_batch_weighted_cross_entropy": total_loss / examples,
        "duration_seconds": duration,
        "examples_per_second": examples / duration,
        "peak_gpu_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "peak_gpu_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        "batch_order_sha256": batch_order.hexdigest(),
        "seeded": bool(training["seeded"]),
        "data_order_deterministic": bool(training["data_order_deterministic"]),
        "bitwise_reproducible": bool(training["bitwise_reproducible"]),
        "single_run_variance_estimated": bool(
            config["runtime"]["reproducibility"][
                "single_run_variance_estimated"
            ]
        ),
        "all_parameters_trained": True,
        "full_training_split_consumed": True,
    }
    return {"training": training_report, "telemetry": telemetry}, telemetry_payload


def package_directory_digest(root: Path) -> dict[str, Any]:
    """Hash the installed package tree, excluding interpreter cache products."""

    root = root.resolve()
    records: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        size = path.stat().st_size
        records.append(
            {
                "path": relative.as_posix(),
                "bytes": size,
                "sha256": sha256_file(path),
            }
        )
        total += size
    _require(records, f"package tree contained no regular files: {root}")
    return {
        "root": str(root),
        "regular_file_count": len(records),
        "regular_file_bytes": total,
        "file_manifest_sha256": canonical_sha256(records),
        "excluded": ["__pycache__", "*.pyc", "*.pyo", "symlinks"],
    }


def distribution_digest(name: str) -> dict[str, Any]:
    distribution = importlib.metadata.distribution(name)
    records: list[dict[str, Any]] = []
    total = 0
    for registered in sorted(distribution.files or [], key=str):
        relative = Path(str(registered))
        if "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}:
            continue
        located = Path(distribution.locate_file(registered))
        if located.is_symlink() or not located.is_file():
            continue
        path = located.resolve()
        size = path.stat().st_size
        records.append(
            {
                "distribution_relative_path": relative.as_posix(),
                "bytes": size,
                "sha256": sha256_file(path),
            }
        )
        total += size
    _require(records, f"installed distribution contained no regular files: {name}")
    return {
        "name": distribution.metadata["Name"],
        "version": distribution.version,
        "regular_file_count": len(records),
        "regular_file_bytes": total,
        "file_manifest_sha256": canonical_sha256(records),
        "excluded": ["__pycache__", "*.pyc", "*.pyo", "symlinks"],
    }


def source_file_report(value: Any, package_root: Path) -> dict[str, Any]:
    source = inspect.getsourcefile(inspect.unwrap(value))
    _require(source is not None, "installed implementation has no inspectable source file")
    path = Path(source).resolve()
    relative = path.relative_to(package_root.resolve())
    return {
        "package_relative_path": relative.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def implementation_provenance_report(
    torchvision: Any, config: Mapping[str, Any]
) -> dict[str, Any]:
    package_root = Path(torchvision.__file__).resolve().parent
    constructors = {
        model["key"]: source_file_report(
            getattr(torchvision.models, model["constructor"]), package_root
        )
        for model in config["models"]
    }
    loader_class = source_file_report(torchvision.datasets.ImageFolder, package_root)
    loader_function = source_file_report(
        torchvision.datasets.folder.default_loader, package_root
    )
    return {
        "torchvision_version": torchvision.__version__,
        "torchvision_distribution_version": importlib.metadata.version("torchvision"),
        "torchvision_distribution": distribution_digest("torchvision"),
        "torchvision_package": package_directory_digest(package_root),
        "model_constructor_sources": constructors,
        "imagefolder_class_source": loader_class,
        "default_loader_source": loader_function,
        "loader": "torchvision.datasets.ImageFolder/default_loader(Pillow)",
    }


def _nvidia_driver_version() -> str:
    try:
        values = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=driver_version",
                "--format=csv,noheader",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("nvidia-smi driver provenance is required") from exc
    unique = sorted({value.strip() for value in values if value.strip()})
    _require(len(unique) == 1, "expected one NVIDIA driver version across devices")
    return unique[0]


def runtime_report(torch: Any, torchvision: Any, device: Any) -> dict[str, Any]:
    try:
        import PIL
        from PIL import Image, _imaging, features
    except (ImportError, OSError) as exc:
        raise RuntimeError("Pillow runtime provenance is required") from exc
    pillow_root = Path(PIL.__file__).resolve().parent
    properties = torch.cuda.get_device_properties(device)
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_distribution_version": importlib.metadata.version("torch"),
        "torch_distribution": distribution_digest("torch"),
        "torchvision": torchvision.__version__,
        "numpy": importlib.metadata.version("numpy"),
        "pillow": PIL.__version__,
        "pillow_distribution_version": importlib.metadata.version("Pillow"),
        "pillow_distribution": distribution_digest("Pillow"),
        "pillow_package": package_directory_digest(pillow_root),
        "pillow_image_source": source_file_report(Image.Image, pillow_root),
        "pillow_imaging_extension": {
            "path": Path(_imaging.__file__).resolve().name,
            "bytes": Path(_imaging.__file__).resolve().stat().st_size,
            "sha256": sha256_file(Path(_imaging.__file__).resolve()),
        },
        "libjpeg_available": bool(features.check("jpg")),
        "libjpeg_version": features.version_codec("jpg"),
        "device_type": device.type,
        "gpu": torch.cuda.get_device_name(device),
        "gpu_compute_capability": [properties.major, properties.minor],
        "gpu_total_memory_bytes": int(properties.total_memory),
        "nvidia_driver": _nvidia_driver_version(),
        "cuda_runtime": torch.version.cuda,
        "cudnn": int(torch.backends.cudnn.version()),
        "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
        "deterministic_algorithms_warn_only": bool(
            torch.is_deterministic_algorithms_warn_only_enabled()
        ),
        "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
        "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
    }


def observed_runtime_provenance_registry(
    runtime: Mapping[str, Any], implementation: Mapping[str, Any]
) -> dict[str, Any]:
    observed = {
        "pillow_version": runtime["pillow"],
        "libjpeg_version": runtime["libjpeg_version"],
        "torch_distribution_version": runtime["torch_distribution_version"],
        "torch_distribution_regular_file_count": runtime["torch_distribution"][
            "regular_file_count"
        ],
        "torch_distribution_regular_file_bytes": runtime["torch_distribution"][
            "regular_file_bytes"
        ],
        "torch_distribution_file_manifest_sha256": runtime[
            "torch_distribution"
        ]["file_manifest_sha256"],
        "torchvision_distribution_file_manifest_sha256": implementation[
            "torchvision_distribution"
        ]["file_manifest_sha256"],
        "torchvision_package_file_manifest_sha256": implementation[
            "torchvision_package"
        ]["file_manifest_sha256"],
        "alexnet_constructor_source_sha256": implementation[
            "model_constructor_sources"
        ]["alexnet"]["sha256"],
        "densenet121_constructor_source_sha256": implementation[
            "model_constructor_sources"
        ]["densenet121"]["sha256"],
        "imagefolder_class_source_sha256": implementation[
            "imagefolder_class_source"
        ]["sha256"],
        "default_loader_source_sha256": implementation["default_loader_source"][
            "sha256"
        ],
        "pillow_distribution_file_manifest_sha256": runtime[
            "pillow_distribution"
        ]["file_manifest_sha256"],
        "pillow_package_file_manifest_sha256": runtime["pillow_package"][
            "file_manifest_sha256"
        ],
        "pillow_image_source_sha256": runtime["pillow_image_source"]["sha256"],
        "pillow_imaging_extension_sha256": runtime["pillow_imaging_extension"][
            "sha256"
        ],
    }
    _require(
        tuple(observed) == EXPECTED_PROVENANCE_FIELDS,
        "observed runtime provenance field registry drifted",
    )
    _require(
        all(
            isinstance(observed[field], str) and bool(observed[field])
            for field in PROVENANCE_TEXT_FIELDS
        )
        and all(
            isinstance(observed[field], int)
            and not isinstance(observed[field], bool)
            and observed[field] > 0
            for field in PROVENANCE_INTEGER_FIELDS
        )
        and all(
            _is_lower_hex(observed[field], 64)
            for field in PROVENANCE_DIGEST_FIELDS
        ),
        "observed runtime provenance contains an invalid value",
    )
    return observed


def enforce_runtime_provenance_registration(
    registered: Mapping[str, Any], observed: Mapping[str, Any]
) -> dict[str, Any]:
    status = registered["registration_status"]
    if status != "REGISTERED":
        raise ValueError(
            "runtime provenance is pending; run --capture-runtime-provenance on "
            "the target EC2 environment, register the exact values, and replay"
        )
    expected = registered["exact"]
    mismatches = [
        field
        for field in EXPECTED_PROVENANCE_FIELDS
        if expected[field] != observed[field]
    ]
    _require(
        not mismatches,
        f"installed runtime provenance does not match registration: {mismatches}",
    )
    return {
        "status": "MATCH",
        "target_environment": registered["target_environment"],
        "expected": dict(expected),
        "observed": dict(observed),
        "mismatches": [],
        "can_authorize": False,
    }


def source_snapshot(
    config_path: Path, *, expected_config_sha256: str | None = None
) -> dict[str, Any]:
    runner = Path(__file__).resolve()
    hook = ROOT / "scripts" / "llm_training_hooks.py"
    result: dict[str, Any] = {
        "config_logical_name": repo_logical_name(config_path),
        "config_sha256": sha256_file(config_path),
        "runner_sha256": sha256_file(runner),
        "hook_implementation_sha256": sha256_file(hook),
        "config_bytes_hashed_before_parse": expected_config_sha256 is not None,
    }
    if expected_config_sha256 is not None:
        _require(
            result["config_sha256"] == expected_config_sha256,
            "configuration changed after its pre-parse byte hash",
        )
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    result["git_commit"] = commit
    return result


def verify_source_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    for field in ("config_sha256", "runner_sha256", "hook_implementation_sha256"):
        _require(before.get(field) == after.get(field), f"source changed during run: {field}")


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{os.getpid()}"


def build_markdown_report(report: Mapping[str, Any]) -> str:
    models = report.get("models", [])
    rows = []
    red_rows = []
    for model in models:
        before = model["before_training_test"]
        after = model["after_training_test"]
        training = model["training"]
        telemetry = model["telemetry"]
        rows.append(
            "| {key} | {parameters:,} | {before_loss:.6f} | {before_accuracy:.4f} | "
            "{after_loss:.6f} | {after_accuracy:.4f} | {rate:.2f} | {peak:.2f} | "
            "{steps} | {coverage} | {control} |".format(
                key=model["model_key"],
                parameters=model["parameter_count"],
                before_loss=before["mean_cross_entropy"],
                before_accuracy=before["top1_accuracy"],
                after_loss=after["mean_cross_entropy"],
                after_accuracy=after["top1_accuracy"],
                rate=training["examples_per_second"],
                peak=training["peak_gpu_allocated_bytes"] / (1024**3),
                steps=training["optimizer_steps"],
                coverage=telemetry["coverage_status"],
                control=model.get("hook_non_interference_control", {}).get(
                    "status", "not_reported"
                ),
            )
        )
        for screen_name, result in model.get("red_team", {}).get("screens", {}).items():
            asr = result.get("attack_success_rate_on_clean_correct")
            asr_display = "n/a" if asr is None else f"{asr:.4f}"
            red_rows.append(
                f"| {model['model_key']} | `{screen_name}` | "
                f"{result['mean_cross_entropy']:.6f} | "
                f"{result['top1_accuracy']:.4f} | "
                f"{result['accuracy_drop_from_clean']:.4f} | {asr_display} | "
                f"{result.get('measured_max_pixel_linf', 0.0):.8f} |"
            )
    dataset = report.get("dataset", {})
    runtime = report.get("runtime", {})
    runtime_gate = report.get("runtime_provenance_gate", {})
    cuda_reproducibility = report.get("cuda_reproducibility", {})
    release = report.get("release_gate_summary", {})
    return "\n".join(
        [
            "# Full-EuroSAT-RGB vision training-hook report",
            "",
            f"Operational execution: **{report.get('execution', {}).get('test_verdict', 'unknown')}**  ",
            "Release decision: **no release authorization**",
            "",
            "This report records an experimental integration and scale run. A passing hook run cannot clear a release contract.",
            "",
            "## Frozen workload",
            "",
            f"- Dataset: 27,000 real Sentinel-2 RGB land-use/land-cover patches from canonical Zenodo DOI `10.5281/zenodo.7711810` (`{dataset.get('archive_sha256', 'unknown')}`).",
            f"- Rows: {dataset.get('train_rows', 0):,} training and {dataset.get('test_rows', 0):,} test; no synthetic training samples or training augmentation.",
            f"- Extraction manifest: preregistered canonical SHA-256 `{dataset.get('extraction_manifest_canonical_sha256', 'unknown')}`; {dataset.get('unique_image_content_sha256', 0):,} unique image digests and {dataset.get('cross_split_content_sha256_overlap', 'unknown')} cross-split content overlaps.",
            "- Input: native 64x64 images deterministically resized to 96x96 for the unmodified architecture stems.",
            f"- Runtime: `{runtime.get('gpu', 'unknown')}`, torch `{runtime.get('torch', 'unknown')}`, torchvision `{runtime.get('torchvision', 'unknown')}`.",
            f"- Exact installed implementation/decoder provenance gate: **{runtime_gate.get('status', 'not_reported')}**.",
            f"- CUDA execution: seeded with deterministic split/batch order, deterministic algorithms `{cuda_reproducibility.get('deterministic_algorithms_mode', 'unknown')}`, bitwise reproducible **{str(cuda_reproducibility.get('bitwise_reproducible', False)).lower()}**.",
            f"- Allowlisted CUDA nondeterminism warning counts: `{json.dumps(cuda_reproducibility.get('observed_kernel_warning_counts', {}), sort_keys=True)}`; unexpected nondeterminism warnings: {cuda_reproducibility.get('unexpected_nondeterminism_warning_count', 'unknown')}; other captured warnings: {cuda_reproducibility.get('other_warning_count', 'unknown')}.",
            "",
            "## Empirical results",
            "",
            "| Model | Parameters | Test loss before | Accuracy before | Test loss after | Accuracy after | Train examples/s | Peak GPU GiB | Steps | Hook coverage | Paired no-hook control |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
            *rows,
            "",
            "Each model consumed all 21,600 training examples for one FP32 epoch. Throughput and memory are observations of this hardware/software configuration, not a general scaling law.",
            "The exact hooked/unhooked non-interference control runs on CPU. It does not prove CUDA hook non-interference; the full CUDA epoch separately requires complete hook coverage.",
            "",
            "## Bounded red-team screens",
            "",
            "| Model | Screen | Cross-entropy | Accuracy | Accuracy drop vs clean | ASR on clean-correct | Measured pixel L∞ |",
            "|---|---|---:|---:|---:|---:|---:|",
            *red_rows,
            "",
            "Brightness, Gaussian-noise, and untargeted true-label white-box FGSM results use the same deterministic near-balanced 512-image subset. Attack success rate is conditioned on clean-correct examples; measured pixel-space L∞ is reported and FGSM must remain within 2/255 plus the registered tolerance. These are descriptive screens: they can neither clear nor block a gate, are not attack-battery evidence or assessment input, and require approved recollection for either use.",
            "",
            "## Metadata disclosure profiles",
            "",
            "| Profile | Disclosed surface | Release gate |",
            "|---|---|---|",
            *[f"| `{item['level']}` | {', '.join(item['disclosed'])} | **{item['gate']}** |" for item in report.get("metadata_release_profiles", [])],
            "",
            "## Release gates",
            "",
            "This is an illustrative non-MRAP gate summary. A complete MRAP AssessmentRequest 5.0 ReleaseContract remains required.",
            f"- Dataset-rights gate: **{release.get('dataset_rights_gate', 'unknown')}**. EuroSAT is declared MIT, while Copernicus Sentinel terms and intended use still require review.",
            f"- Torchvision implementation license gate: **{release.get('model_implementation_license_gate', 'unknown')}**.",
            f"- Quality gate: **{release.get('quality_gate', 'NOT_ASSESSED')}**.",
            f"- Privacy gate: **{release.get('privacy_gate', 'NOT_ASSESSED')}**.",
            f"- Security gate: **{release.get('security_gate', 'NOT_ASSESSED')}**.",
            "- Operational hook evidence can neither clear nor authorize release.",
            "",
            "## Scope limitations",
            "",
            "EuroSAT is a genuine Earth-observation benchmark, but its 27,000 RGB patches cover a bounded European Sentinel-2 distribution. The path-hash split is not spatially separated, so spatial autocorrelation and new-region generalization are untested. It is not representative of higher-resolution production data, temporal shift, rare classes, adversarial behavior, privacy, or safety. One epoch from random initialization and one seed are a systems test, not a competitive quality evaluation; there is no confidence interval, warm-up exclusion, or separate steady-state throughput estimate.",
            "",
            "No images, labels, parameters, activations, gradients, paths, or per-example predictions enter reports or telemetry. The governed cache necessarily retains the verified source archive and extracted corpus; telemetry contains bounded scalar aggregates and batch-index hashes only.",
            "The exact split is reconstructible for this public benchmark and its digests are internal experiment provenance, not a proposed recipient interface. An exact roster for protected data remains blocked; removing that disclosure changes the interface and requires reassessment.",
            "",
            f"Machine decision: `{report.get('decision', 'no_release_authorization')}`; `authorization_eligible: false`; `assessment_input_emitted: false`.",
            "",
        ]
    )


def run(
    config_path: Path,
    output_dir: Path,
    cache_dir: Path,
    *,
    offline: bool,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config, preparsed_config_sha256 = load_config_with_digest(config_path)
    source_before = source_snapshot(
        config_path, expected_config_sha256=preparsed_config_sha256
    )
    hook_binding = bind_hook_collector(
        ROOT / "scripts" / "llm_training_hooks.py",
        source_before["hook_implementation_sha256"],
    )
    source_before["hook_runtime_binding"] = hook_binding
    output_dir, cache_dir = resolve_disjoint_directory_trees(output_dir, cache_dir)
    output_dir = reserve_output_directory(output_dir)

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch, torchvision = require_ml_runtime(config)
    seed_runtime(
        torch,
        int(config["training"]["seed"]),
        deterministic_algorithms_mode=config["runtime"]["reproducibility"][
            "deterministic_algorithms_mode"
        ],
    )
    device = torch.device("cuda")
    runtime_observation = runtime_report(torch, torchvision, device)
    implementation_provenance = implementation_provenance_report(
        torchvision, config
    )
    observed_provenance = observed_runtime_provenance_registry(
        runtime_observation, implementation_provenance
    )
    runtime_provenance_gate = enforce_runtime_provenance_registration(
        config["runtime"]["expected_provenance"], observed_provenance
    )

    archive, archive_report = download_verified_archive(
        config["dataset"], cache_dir, offline=offline
    )
    extraction_manifest = prepare_verified_extraction(
        archive, cache_dir, config["dataset"]
    )
    decoded_observation = validate_decoded_images(
        cache_dir / DATASET_DIRECTORY,
        config["dataset"]["decoded_validation"],
    )
    train_dataset, test_dataset, dataset_observation = load_datasets(
        torchvision, cache_dir, config, extraction_manifest
    )

    evaluation_loader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=int(config["evaluation"]["batch_size"]),
        shuffle=False,
        num_workers=int(config["runtime"]["num_workers"]),
        pin_memory=False,
        drop_last=False,
    )
    model_reports: list[dict[str, Any]] = []
    pending_telemetry: list[tuple[str, str]] = []
    nondeterminism_phases: list[dict[str, Any]] = []
    for model_config in config["models"]:
        non_interference = run_hook_non_interference_control(
            torch,
            torchvision,
            train_dataset,
            config,
            model_config,
            torch.device(config["hook_non_interference_control"]["control_device"]),
        )
        seed_runtime(
            torch,
            int(config["training"]["seed"]),
            deterministic_algorithms_mode=config["runtime"]["reproducibility"][
                "deterministic_algorithms_mode"
            ],
        )
        model = build_model(torchvision, model_config)
        initial_state = model_state_sha256(model)
        parameter_count = sum(int(parameter.numel()) for parameter in model.parameters())
        trainable_count = sum(
            int(parameter.numel()) for parameter in model.parameters() if parameter.requires_grad
        )
        _require(parameter_count == trainable_count, "all architecture parameters must be trainable")
        model.to(device)
        before = evaluate_model(torch, model, evaluation_loader, device)
        _require(before["examples"] == config["dataset"]["test_rows"], "before-training evaluation was incomplete")
        run_context = {
            "schema_version": "1.0",
            "context_type": "registered_vision_training_run_context",
            "experiment_id": config["experiment_id"],
            "run_id": output_dir.name,
            "source": {
                "config_sha256": source_before["config_sha256"],
                "runner_sha256": source_before["runner_sha256"],
                "hook_implementation_sha256": source_before[
                    "hook_implementation_sha256"
                ],
                "git_commit": source_before["git_commit"],
            },
            "dataset": {
                "archive_sha256": archive_report["sha256"],
                "extraction_manifest_sha256": canonical_sha256(
                    extraction_manifest
                ),
                "train_relative_path_set_sha256": dataset_observation[
                    "train_relative_path_set_sha256"
                ],
                "test_relative_path_set_sha256": dataset_observation[
                    "test_relative_path_set_sha256"
                ],
                "cross_split_content_sha256_overlap": dataset_observation[
                    "cross_split_content_sha256_overlap"
                ],
            },
            "runtime_sha256": canonical_sha256(runtime_observation),
            "cuda_reproducibility_policy": dict(
                config["runtime"]["reproducibility"]
            ),
            "runtime_provenance_gate_sha256": canonical_sha256(
                runtime_provenance_gate
            ),
            "torchvision_implementation_provenance_sha256": canonical_sha256(
                implementation_provenance
            ),
            "model_registration": dict(model_config),
            "model_constructor_source": implementation_provenance[
                "model_constructor_sources"
            ][model_config["key"]],
            "initial_state_sha256": initial_state,
            "before_training_test_sha256": canonical_sha256(before),
            "hook_non_interference_control_sha256": canonical_sha256(
                non_interference
            ),
            "registered_protocol_sha256": canonical_sha256(
                {
                    "preprocessing": config["preprocessing"],
                    "training": config["training"],
                    "evaluation": config["evaluation"],
                    "hooks": config["hooks"],
                    "red_team": config["red_team"],
                }
            ),
            "release_decision": "no_release_authorization",
            "authorization_eligible": False,
        }
        with capture_registered_cuda_nondeterminism(
            config, f"training:{model_config['key']}"
        ) as training_nondeterminism:
            training_result, telemetry_payload = train_model(
                torch,
                model,
                train_dataset,
                config,
                model_config,
                device,
                run_context,
            )
        nondeterminism_phases.append(training_nondeterminism)
        after = evaluate_model(torch, model, evaluation_loader, device)
        _require(after["examples"] == config["dataset"]["test_rows"], "after-training evaluation was incomplete")
        with capture_registered_cuda_nondeterminism(
            config, f"red_team:{model_config['key']}"
        ) as red_team_nondeterminism:
            red_team = run_red_team_screens(
                torch, model, test_dataset, config, device
            )
        nondeterminism_phases.append(red_team_nondeterminism)
        final_state = model_state_sha256(model)
        _require(initial_state != final_state, "model state did not change during training")
        telemetry_name = config["output"]["telemetry_pattern"].format(
            model_key=model_config["key"]
        )
        pending_telemetry.append((telemetry_name, telemetry_payload))
        model_reports.append(
            {
                "model_key": model_config["key"],
                "constructor": f"torchvision.models.{model_config['constructor']}",
                "weights": None,
                "num_classes": model_config["num_classes"],
                "canonical_architecture_adaptation": "ten_class_output_head_only",
                "implementation_source": model_config["implementation_source"],
                "implementation_license": model_config["implementation_license"],
                "implementation_license_gate": config["release_gate_summary"][
                    "model_implementation_license_gate"
                ],
                "installed_constructor_source": implementation_provenance[
                    "model_constructor_sources"
                ][model_config["key"]],
                "hook_modules": model_config["hook_modules"],
                "hook_non_interference_control": non_interference,
                "cuda_training_nondeterminism": training_nondeterminism,
                "cuda_red_team_nondeterminism": red_team_nondeterminism,
                "parameter_count": parameter_count,
                "trainable_parameter_count": trainable_count,
                "initial_state_sha256": initial_state,
                "final_state_sha256": final_state,
                "before_training_test": before,
                "after_training_test": after,
                "red_team": red_team,
                **training_result,
                "telemetry_file": telemetry_name,
                "operational_gate": "PASS",
                "release_decision": "no_release_authorization",
            }
        )
        del model
        torch.cuda.empty_cache()

    cuda_reproducibility = summarize_cuda_nondeterminism(
        config, nondeterminism_phases
    )

    archive_after = verify_archive(archive, config["dataset"])
    _require(
        all(
            archive_after[field] == archive_report[field]
            for field in ("bytes", "sha256", "official_md5")
        ),
        "dataset archive changed during execution",
    )
    extraction_after = _verify_extraction_manifest(
        cache_dir / DATASET_DIRECTORY,
        cache_dir / "eurosat-rgb-extraction-manifest.json",
        config["dataset"],
    )
    _require(
        canonical_sha256(extraction_after) == canonical_sha256(extraction_manifest),
        "extracted dataset changed during execution",
    )
    runtime_after = runtime_report(torch, torchvision, device)
    implementation_after = implementation_provenance_report(torchvision, config)
    observed_provenance_after = observed_runtime_provenance_registry(
        runtime_after, implementation_after
    )
    _require(
        observed_provenance_after == observed_provenance,
        "installed runtime provenance changed during execution",
    )
    _require(
        canonical_sha256(runtime_after) == canonical_sha256(runtime_observation)
        and canonical_sha256(implementation_after)
        == canonical_sha256(implementation_provenance),
        "runtime or implementation observation changed during execution",
    )
    source_after = source_snapshot(
        config_path, expected_config_sha256=preparsed_config_sha256
    )
    verify_source_unchanged(source_before, source_after)
    _require(
        _BOUND_HOOK_EVIDENCE == hook_binding,
        "byte-bound hook runtime changed during execution",
    )
    report = {
        "schema_version": "1.1",
        "report_type": "experimental_vision_training_hook_execution",
        "experiment_id": config["experiment_id"],
        "run_id": output_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "execution": {
            "status": "completed",
            "test_verdict": "passed",
            "offline_replay": offline,
            "full_dataset_workload": True,
            "runtime_provenance_reverified_after_execution": True,
            "seeded_cuda_warn_only": True,
            "bitwise_reproducible": False,
            "single_run_variance_estimated": False,
        },
        "source": source_before,
        "runtime": runtime_observation,
        "runtime_provenance_gate": runtime_provenance_gate,
        "implementation_provenance": implementation_provenance,
        "cuda_reproducibility": cuda_reproducibility,
        "dataset": {
            "name": config["dataset"]["name"],
            "official_page": config["dataset"]["official_page"],
            "official_url": config["dataset"]["url"],
            "archive_bytes": archive_report["bytes"],
            "archive_sha256": archive_report["sha256"],
            "official_md5": archive_report["official_md5"],
            "retrieval_mode": archive_report["retrieval_mode"],
            "validated_request_urls": archive_report["validated_request_urls"],
            "redirect_validation": archive_report["redirect_validation"],
            "extraction_manifest_canonical_sha256": canonical_sha256(
                extraction_manifest
            ),
            "extraction_manifest_serialized_sha256": config["dataset"][
                "extraction_manifest"
            ]["serialized_sha256"],
            "extraction_manifest_preregistration_match": True,
            "decoded_validation": decoded_observation,
            "license": config["dataset"]["license"],
            "license_declaration_source": config["dataset"]["official_page"],
            "sentinel_data_terms_review": config["dataset"]["sentinel_data_terms_review"],
            "rights_gate": config["dataset"]["rights_gate"],
            **dataset_observation,
        },
        "preprocessing": config["preprocessing"],
        "models": model_reports,
        "scale": {
            "architectures": len(model_reports),
            "unique_real_corpus_inputs": int(config["dataset"]["total_rows"]),
            "unique_training_inputs": int(config["dataset"]["train_rows"]),
            "unique_held_out_inputs": int(config["dataset"]["test_rows"]),
            "training_example_condition_evaluations": sum(
                model["training"]["examples_seen"] for model in model_reports
            ),
            "held_out_example_condition_evaluations": 2
            * len(model_reports)
            * int(config["dataset"]["test_rows"]),
            "red_team_unique_base_inputs": int(config["red_team"]["test_rows"]),
            "red_team_example_condition_evaluations": sum(
                model["red_team"]["condition_evaluations"]
                for model in model_reports
            ),
            "hook_non_interference_example_condition_evaluations": len(
                model_reports
            )
            * int(config["hook_non_interference_control"]["paired_real_examples"])
            * 2,
            "total_optimizer_steps": sum(
                model["training"]["optimizer_steps"] for model in model_reports
            ),
        },
        "red_team_protocol": config["red_team"],
        "artifact_handling": {
            "raw_images_retained_in_report_or_telemetry": False,
            "raw_labels_retained_in_report_or_telemetry": False,
            "raw_tensors_retained_in_report_or_telemetry": False,
            "per_example_predictions_retained": False,
            "model_weights_retained": False,
            "aggregate_telemetry_only": True,
            "batch_indices_retained": False,
            "batch_index_hashes_retained": True,
            "verified_source_dataset_cache_retained": True,
            "fresh_output_directory_reserved": True,
            "artifact_basename_uniqueness_validated": True,
            "artifacts_published_without_replacement": True,
        },
        "metadata_release_profiles": config["metadata_release_profiles"],
        "roster_release_handling": config["roster_release_handling"],
        "release_gate_summary": config["release_gate_summary"],
        "limitations": [
            "EuroSAT RGB images are only 64x64 and are not a production-resolution workload.",
            "The path-hash split is not spatially separated; spatial autocorrelation and new-region generalization are untested.",
            "The benchmark cannot represent current or non-European deployment distributions.",
            "One epoch from random initialization tests execution, not useful model quality.",
            "No privacy, security, robustness, fairness, or distribution-shift claim is evaluated.",
            "The declared MIT license and Copernicus Sentinel data terms still require independent review.",
            "Brightness, noise, and FGSM results are bounded descriptive screens, not robustness guarantees.",
            "Throughput and memory are specific to the recorded hardware and software runtime.",
            "Only one preregistered seed is run; no multi-seed confidence interval is estimated.",
            "CUDA adaptive average-pooling backward is allowlisted warn-only nondeterministic; results are not bitwise reproducible.",
            "Throughput is end-to-end for the single epoch; there is no warm-up exclusion or separate steady-state estimate.",
            "The exact roster is reconstructible for this public benchmark and retained only as internal experiment provenance; a protected-data roster disclosure would remain blocked and require redesign.",
        ],
        "experimental_only": True,
        "authorization_eligible": False,
        "assessment_input_emitted": False,
        "can_clear": False,
        "decision": "no_release_authorization",
    }
    return publish_completion_artifacts(
        output_dir,
        pending_telemetry,
        report,
        config["output"]["json_report"],
        config["output"]["markdown_report"],
    )


def capture_runtime_provenance(config_path: Path) -> dict[str, Any]:
    """Capture the exact target artifacts without touching data or training."""

    config, config_sha256 = load_config_with_digest(config_path.resolve())
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch, torchvision = require_ml_runtime(config)
    seed_runtime(
        torch,
        int(config["training"]["seed"]),
        deterministic_algorithms_mode=config["runtime"]["reproducibility"][
            "deterministic_algorithms_mode"
        ],
    )
    device = torch.device("cuda")
    runtime = runtime_report(torch, torchvision, device)
    implementation = implementation_provenance_report(torchvision, config)
    exact = observed_runtime_provenance_registry(runtime, implementation)
    return {
        "schema_version": "1.0",
        "capture_type": "vision_runtime_provenance_registration_candidate",
        "config_sha256": config_sha256,
        "expected_provenance": {
            "schema_version": "1.0",
            "registration_status": "REGISTERED",
            "target_environment": config["runtime"]["expected_provenance"][
                "target_environment"
            ],
            "capture_only_can_authorize": False,
            "exact": exact,
        },
        "hardware_observation": {
            field: runtime[field]
            for field in (
                "python",
                "numpy",
                "gpu",
                "gpu_compute_capability",
                "gpu_total_memory_bytes",
                "nvidia_driver",
                "cuda_runtime",
                "cudnn",
            )
        },
        "authorization_eligible": False,
        "decision": "no_release_authorization",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "reproduction" / "vision-training-hook" / "config.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Fresh run directory; defaults to output/vision-training-hook/<UTC run id>",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "output" / "cache" / "vision-training-hook",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Forbid network access and require the verified archive cache",
    )
    parser.add_argument(
        "--capture-runtime-provenance",
        action="store_true",
        help="Print an exact runtime registry candidate; do not access data or train",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.capture_runtime_provenance:
        try:
            capture = capture_runtime_provenance(args.config)
        except Exception as exc:
            print(
                f"runtime provenance capture failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(json.dumps(capture, allow_nan=False, indent=2, sort_keys=True))
        return 0
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = ROOT / "output" / "vision-training-hook" / _new_run_id()
    try:
        report = run(args.config, output_dir, args.cache_dir, offline=args.offline)
    except Exception as exc:
        print(f"vision training-hook experiment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_directory": str(output_dir.resolve()),
                "test_verdict": report["execution"]["test_verdict"],
                "decision": report["decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
