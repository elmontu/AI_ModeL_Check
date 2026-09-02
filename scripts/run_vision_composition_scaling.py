#!/usr/bin/env python3
"""Run the frozen EuroSAT vision composition/scaling experiment on one L4.

The workload measures operational scaling and descriptive model-output
composition. It emits aggregate observations only and cannot clear, block, or
serve as input to a release assessment or attack battery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import stat
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_vision_training_hook_audit as vision  # noqa: E402


EXPECTED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "experiment_id",
    "experimental_only",
    "authorization_eligible",
    "assessment_input_emitted",
    "attack_battery_eligible",
    "can_clear",
    "can_block",
    "decision",
    "requires_approved_recollection",
    "base_vision_protocol",
    "runtime",
    "resource_budget",
    "matrix",
    "measurement",
    "model_output_composition",
    "release_interface_scenarios",
    "artifact_policy",
    "output",
}
EXPECTED_SECTION_SHA256 = {
    "base_vision_protocol": "1ef1c90b45d151b3b74b5594ffc55c04c67c3c3e953a290c7f924fe3130c7759",
    "runtime": "fd44f81f2da348aaace4642f62aeb1feedf6b15b3b98391a2c5557eb95a73cfa",
    "resource_budget": "f327e519f46bf4115785855b333e6a2a59364427094daba88ae7c3ca570d69bd",
    "matrix": "1d10f6238ae0dd19b24e297ead91459cc043aabca80a8d09e3817e61cb6f3aaa",
    "measurement": "42ae21e5d0e008a3ee9f3bc6eedfd7aab77c8e8a745867ddd64843e9db094e94",
    "model_output_composition": "cfda31a895e44e4d4d15f8ec13d7b538b41c81586d5c570fad49a4ea64050fab",
    "release_interface_scenarios": "1b8da23a7494f0638f3958ffcbd8355ceaabe35c736706fb0d90e339385074e7",
    "artifact_policy": "dcdf7225f077b549b0ea1d40403fd74a40ac550e056d17c8d3f63acc0194a923",
    "output": "745fe178ed5e266002677612a54fbed20bc4443b8b6b909132e57e16c5639ddc",
}
SCALE_COUNTS = {
    "nested_5400": {
        "AnnualCrop": 600,
        "Forest": 600,
        "HerbaceousVegetation": 600,
        "Highway": 500,
        "Industrial": 500,
        "Pasture": 400,
        "PermanentCrop": 500,
        "Residential": 600,
        "River": 500,
        "SeaLake": 600,
    },
    "nested_10800": {
        "AnnualCrop": 1200,
        "Forest": 1200,
        "HerbaceousVegetation": 1200,
        "Highway": 1000,
        "Industrial": 1000,
        "Pasture": 800,
        "PermanentCrop": 1000,
        "Residential": 1200,
        "River": 1000,
        "SeaLake": 1200,
    },
    "nested_21600": {
        "AnnualCrop": 2400,
        "Forest": 2400,
        "HerbaceousVegetation": 2400,
        "Highway": 2000,
        "Industrial": 2000,
        "Pasture": 1600,
        "PermanentCrop": 2000,
        "Residential": 2400,
        "River": 2000,
        "SeaLake": 2400,
    },
}
SCALE_ROSTER_SHA256 = {
    "nested_5400": "a7e42ed008ea1d3bee3c4c585b893242a6fa3b97fa2a7dfe33b90058fb0b57f7",
    "nested_10800": "03a0b4cdf04a0cf84091114bb3e6d5c55dc70f02978aa7a8cd80e810377318f0",
    "nested_21600": "3e26b9ee7014071cd257715e8c0895f478d9256464f3afb40a26bfed3c148b75",
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_json(value: Any) -> bytes:
    return vision.canonical_json(value)


def canonical_sha256(value: Any) -> str:
    return vision.canonical_sha256(value)


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate exact matrix, authority-negative semantics, and output bounds."""

    _require(set(raw) == EXPECTED_TOP_LEVEL_FIELDS, "unexpected top-level configuration fields")
    expected_scalars = {
        "schema_version": "1.0",
        "experiment_id": "vision-eurosat-hook-composition-scaling-v1",
        "experimental_only": True,
        "authorization_eligible": False,
        "assessment_input_emitted": False,
        "attack_battery_eligible": False,
        "can_clear": False,
        "can_block": False,
        "decision": "no_release_authorization",
        "requires_approved_recollection": True,
    }
    _require(
        all(raw.get(key) == value for key, value in expected_scalars.items()),
        "authority or experiment identity differs from the frozen profile",
    )
    _require(
        all(isinstance(raw.get(section), dict) for section in EXPECTED_SECTION_SHA256),
        "all registered configuration sections must be objects",
    )
    _require(
        raw["resource_budget"]
        == {
            "wall_clock_seconds": 43_200,
            "peak_gpu_reserved_bytes": 21_474_836_480,
            "peak_host_rss_bytes": 21_474_836_480,
            "max_aggregate_artifact_bytes": 21_474_836_480,
            "check_before_each_training_or_composition_phase": True,
            "check_after_each_training_or_composition_phase": True,
            "optional_deadline_utc_may_only_tighten": True,
            "budget_breach_emits_completion": False,
        },
        "child resource budget differs from the frozen ceiling",
    )

    matrix = raw["matrix"]
    architectures = matrix.get("architectures")
    scales = matrix.get("dataset_scales")
    hooks = matrix.get("hook_profiles")
    _require(
        isinstance(architectures, list)
        and [item.get("key") for item in architectures] == ["alexnet", "densenet121"],
        "architecture order differs from the frozen matrix",
    )
    _require(
        [item.get("key") for item in scales]
        == ["nested_5400", "nested_10800", "nested_21600"],
        "dataset scale order differs from the frozen nested matrix",
    )
    for scale in scales:
        key = scale["key"]
        _require(scale.get("class_counts") == SCALE_COUNTS[key], f"{key} class counts differ")
        _require(sum(scale["class_counts"].values()) == scale["rows"], f"{key} row count differs")
        _require(
            scale.get("relative_path_set_sha256") == SCALE_ROSTER_SHA256[key],
            f"{key} roster digest differs",
        )
    _require(matrix.get("batch_sizes") == [64, 128], "batch-size matrix differs")
    _require(
        matrix.get("replicate_seeds")
        == [3407, 499625614, 4288481424, 2669540432, 2937338177],
        "seed matrix differs",
    )
    _require(
        hooks
        == [
            {"key": "no_hook", "enabled": False, "module_policy": "none"},
            {
                "key": "current_registered",
                "enabled": True,
                "module_policy": "base_model_exact_allowlist",
            },
        ],
        "hook profile matrix differs",
    )
    combinations = len(architectures) * len(scales) * len(matrix["batch_sizes"]) * len(matrix["replicate_seeds"])
    _require(
        matrix.get("paired_factor_combinations") == combinations
        and matrix.get("total_training_cells") == combinations * len(hooks)
        and matrix.get("epochs_per_cell") == 1
        and matrix.get("training_scales_are_independent_fresh_model_cells") is True,
        "registered matrix cell counts differ from the Cartesian product",
    )
    maximum_steps = max(
        math.ceil(int(scale["rows"]) / int(batch))
        for scale in scales
        for batch in matrix["batch_sizes"]
    )
    maximum_events = maximum_steps * 7
    _require(
        maximum_events <= matrix.get("max_hook_events_per_cell", 0) == 2500,
        "hook event cap cannot cover the largest cell",
    )
    _require(
        matrix.get("required_pair_matches")
        == [
            "initial_state_sha256",
            "first_batch_manifest_sha256",
            "first_pre_backward_loss_hex",
            "batch_order_sha256",
        ],
        "paired exact-match registry differs",
    )

    output = raw["output"]
    names = [output.get("json_report"), output.get("markdown_report"), output.get("completion_manifest")]
    _require(
        output.get("directory") == "output/composition-scaling/vision"
        and output.get("fresh_run_directory_required") is True
        and output.get("resume_existing_incomplete_run_directory_allowed") is True
        and output.get("checkpoint_directory") == ".checkpoint"
        and output.get("checkpoint_context") == "CONTEXT.json"
        and output.get("checkpoint_ledger") == "completed-records.jsonl"
        and output.get("run_directory_mode") == "0700"
        and output.get("artifact_file_mode") == "0600"
        and names
        == [
            "vision-composition-scaling-report.json",
            "vision-composition-scaling-report.md",
            "RUN_COMPLETE.json",
        ],
        "output contract differs from the frozen profile",
    )
    _require(
        len(set(names)) == len(names)
        and all(isinstance(name, str) and Path(name).name == name for name in names),
        "output names must be unique safe basenames",
    )

    artifact_policy = raw["artifact_policy"]
    _require(
        artifact_policy
        == {
            "raw_images_retained": False,
            "raw_labels_retained": False,
            "raw_tensors_retained": False,
            "per_example_predictions_retained": False,
            "model_weights_retained": False,
            "source_paths_retained": False,
            "aggregate_cell_results_only": True,
        },
        "artifact minimization policy differs",
    )
    composition = raw["model_output_composition"]
    _require(
        composition.get("enabled") is True
        and composition.get("reference_cells")
        == {
            "dataset_scales": ["nested_5400", "nested_10800", "nested_21600"],
            "batch_size": 128,
            "hook_profile": "current_registered",
        }
        and composition.get("clean_test_rows") == 5400
        and composition.get("perturbation_test_rows") == 512
        and composition.get("ensemble_rule")
        == "arithmetic_mean_of_member_class_probabilities"
        and composition.get("aggregate_only") is True
        and composition.get("descriptive_only") is True
        and composition.get("ordered_model_quality_claimed") is False
        and composition.get("causal_composition_claimed") is False
        and composition.get("release_evidence") is False,
        "model-output composition semantics differ",
    )
    _require(
        composition.get("conditions")
        == [
            "clean",
            "brightness",
            "gaussian_noise",
            "alexnet_fgsm",
            "densenet121_fgsm",
            "ensemble_fgsm",
        ]
        and composition.get("fgsm_sources")
        == ["alexnet", "densenet121", "probability_average_ensemble"]
        and composition.get("source_target_transfer_matrix_evaluated") is True,
        "FGSM source-target transfer registry differs",
    )
    _require(
        composition.get("primary_pair_contrast")
        == "pair_metric_minus_arithmetic_mean_of_two_singleton_metrics"
        and composition.get("best_singleton_contrast_used") is False
        and composition.get("suite_export_singleton_ensemble_fgsm_disagreement_encoding")
        == "not_applicable_finite_zero",
        "model-output contrast or suite-export encoding differs",
    )
    release_scenarios = raw["release_interface_scenarios"]
    _require(
        release_scenarios.get("measured_by_training_matrix") is False
        and release_scenarios.get("risk_ordering_claimed") is False
        and release_scenarios.get("numerical_risk_score_emitted") is False,
        "release-interface scenarios must remain non-empirical and unordered",
    )
    for section, expected in EXPECTED_SECTION_SHA256.items():
        _require(canonical_sha256(raw[section]) == expected, f"{section} differs from the frozen profile")
    return raw


def load_config_with_digest(path: Path) -> tuple[dict[str, Any], str]:
    payload = vision.read_bounded_regular_file(path, 128 * 1024, "composition configuration")
    digest = hashlib.sha256(payload).hexdigest()
    raw = json.loads(payload.decode("utf-8", errors="strict"))
    _require(isinstance(raw, dict), "composition configuration must be an object")
    return validate_config(raw), digest


def load_base_protocol(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = config["base_vision_protocol"]
    base_config_path = ROOT / binding["config_logical_name"]
    base_runner_path = ROOT / binding["runner_logical_name"]
    hook_path = ROOT / binding["hook_logical_name"]
    _require(vision.sha256_file(base_runner_path) == binding["runner_sha256"], "base vision runner digest mismatch")
    _require(vision.sha256_file(hook_path) == binding["hook_sha256"], "training-hook digest mismatch")
    base_config, bytes_digest = vision.load_config_with_digest(base_config_path)
    _require(bytes_digest == binding["config_bytes_sha256"], "base vision config byte digest mismatch")
    _require(canonical_sha256(base_config) == binding["config_canonical_sha256"], "base vision config canonical digest mismatch")
    _require(base_config["dataset"]["sha256"] == binding["dataset_archive_sha256"], "dataset binding mismatch")
    _require(base_config["dataset"]["split"]["train_relative_path_set_sha256"] == binding["train_roster_sha256"], "train roster binding mismatch")
    _require(base_config["dataset"]["split"]["test_relative_path_set_sha256"] == binding["test_roster_sha256"], "test roster binding mismatch")
    vision.bind_hook_collector(hook_path, binding["hook_sha256"])
    return base_config, {
        "base_config_logical_name": binding["config_logical_name"],
        "base_config_bytes_sha256": bytes_digest,
        "base_config_canonical_sha256": canonical_sha256(base_config),
        "base_runner_logical_name": binding["runner_logical_name"],
        "base_runner_sha256": binding["runner_sha256"],
        "hook_logical_name": binding["hook_logical_name"],
        "hook_sha256": binding["hook_sha256"],
    }


def build_nested_scale_datasets(
    train_dataset: Any,
    dataset_root: Path,
    scales: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select registered nested prefixes of each path-hashed training class."""

    base = train_dataset.dataset
    by_class: dict[str, list[int]] = {name: [] for name in base.classes}
    for source_index in train_dataset.indices:
        _path, label = base.samples[source_index]
        by_class[base.classes[int(label)]].append(int(source_index))
    datasets: dict[str, Any] = {}
    observations: list[dict[str, Any]] = []
    previous: set[int] = set()
    for scale in scales:
        selected: list[int] = []
        for class_name in base.classes:
            count = int(scale["class_counts"][class_name])
            _require(len(by_class[class_name]) >= count, f"insufficient {class_name} rows")
            selected.extend(by_class[class_name][:count])
        selected_set = set(selected)
        _require(len(selected) == scale["rows"] == len(selected_set), "nested scale row count or uniqueness mismatch")
        _require(previous.issubset(selected_set), "dataset scale rosters are not nested")
        relatives = sorted(
            Path(base.samples[index][0]).resolve().relative_to(dataset_root.resolve()).as_posix()
            for index in selected
        )
        observed_sha256 = canonical_sha256(relatives)
        _require(observed_sha256 == scale["relative_path_set_sha256"], "nested scale roster digest mismatch")
        datasets[scale["key"]] = vision.IndexedDataset(base, selected)
        observations.append(
            {
                "key": scale["key"],
                "rows": len(selected),
                "class_counts": dict(scale["class_counts"]),
                "relative_path_set_sha256": observed_sha256,
                "nested_in_next_registered_scale": True,
            }
        )
        previous = selected_set
    return datasets, observations


def pair_id(seed: int, architecture: str, scale: str, batch_size: int) -> str:
    return f"seed={seed}|architecture={architecture}|scale={scale}|batch={batch_size}"


def ordered_hook_profiles(pair: str, profiles: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    parity = int(hashlib.sha256(pair.encode("utf-8")).hexdigest(), 16) % 2
    return list(profiles if parity == 0 else reversed(profiles))


def process_peak_rss_bytes() -> int:
    """Return the process-wide high-water RSS with explicit platform units."""

    proc_status = Path("/proc/self/status")
    if proc_status.is_file():
        for line in proc_status.read_text(encoding="ascii", errors="strict").splitlines():
            if line.startswith("VmHWM:"):
                fields = line.split()
                _require(len(fields) == 3 and fields[2] == "kB", "unexpected VmHWM format")
                return int(fields[1]) * 1024
    observed = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return observed if sys.platform == "darwin" else observed * 1024


def parse_deadline_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    _require(isinstance(value, str) and value.strip() == value and value, "deadline must be a nonempty UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        observed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("deadline must be an ISO-8601 timestamp") from exc
    _require(observed.tzinfo is not None and observed.utcoffset() is not None, "deadline must include a timezone")
    return observed.astimezone(timezone.utc)


def resolve_effective_deadline(
    started_at_utc: datetime,
    wall_clock_seconds: int,
    optional_deadline_utc: str | None,
) -> tuple[datetime, dict[str, Any]]:
    _require(
        started_at_utc.tzinfo is not None and started_at_utc.utcoffset() is not None,
        "run start must be timezone-aware",
    )
    local_ceiling = started_at_utc.astimezone(timezone.utc) + timedelta(seconds=wall_clock_seconds)
    supplied = parse_deadline_utc(optional_deadline_utc)
    effective = min(local_ceiling, supplied) if supplied is not None else local_ceiling
    return effective, {
        "run_started_at_utc": started_at_utc.astimezone(timezone.utc).isoformat(),
        "local_12h_deadline_utc": local_ceiling.isoformat(),
        "supplied_deadline_utc": supplied.isoformat() if supplied is not None else None,
        "effective_deadline_utc": effective.isoformat(),
        "supplied_deadline_tightened_local_ceiling": supplied is not None and supplied < local_ceiling,
        "supplied_deadline_could_extend_local_ceiling": False,
    }


def enforce_resource_budget(
    budget: Mapping[str, Any],
    *,
    started_monotonic: float,
    run_started_at_utc: datetime,
    effective_deadline_utc: datetime,
    phase: str,
    gpu_reserved_bytes: int,
    host_rss_bytes: int | None = None,
    monotonic_now: float | None = None,
    utc_now: datetime | None = None,
) -> dict[str, Any]:
    """Fail closed on child wall-clock, GPU-reserved, or host-RSS ceilings."""

    now_monotonic = time.monotonic() if monotonic_now is None else monotonic_now
    now_utc = datetime.now(timezone.utc) if utc_now is None else utc_now.astimezone(timezone.utc)
    invocation_elapsed = now_monotonic - started_monotonic
    absolute_elapsed = (now_utc - run_started_at_utc.astimezone(timezone.utc)).total_seconds()
    elapsed = max(invocation_elapsed, absolute_elapsed)
    host_observed = process_peak_rss_bytes() if host_rss_bytes is None else int(host_rss_bytes)
    gpu_observed = int(gpu_reserved_bytes)
    _require(
        invocation_elapsed >= 0.0 and absolute_elapsed >= 0.0 and math.isfinite(elapsed),
        "resource-budget elapsed time is invalid",
    )
    _require(gpu_observed >= 0 and host_observed >= 0, "resource-budget memory observation is invalid")
    _require(
        elapsed <= int(budget["wall_clock_seconds"]),
        f"child wall-clock budget exceeded after {phase}",
    )
    _require(now_utc <= effective_deadline_utc, f"child UTC deadline exceeded after {phase}")
    _require(
        gpu_observed <= int(budget["peak_gpu_reserved_bytes"]),
        f"child GPU-reserved-memory budget exceeded after {phase}",
    )
    _require(
        host_observed <= int(budget["peak_host_rss_bytes"]),
        f"child host-RSS budget exceeded after {phase}",
    )
    return {
        "phase": phase,
        "elapsed_seconds": elapsed,
        "observed_gpu_reserved_bytes": gpu_observed,
        "observed_host_rss_bytes": host_observed,
        "checked_at_utc": now_utc.isoformat(),
        "effective_deadline_utc": effective_deadline_utc.isoformat(),
        "within_budget": True,
    }


def run_training_cell(
    torch: Any,
    torchvision: Any,
    base_config: Mapping[str, Any],
    composition_config: Mapping[str, Any],
    model_config: Mapping[str, Any],
    train_dataset: Any,
    scale: Mapping[str, Any],
    batch_size: int,
    seed: int,
    hook_profile: Mapping[str, Any],
    device: Any,
    *,
    retain_model: bool,
) -> tuple[dict[str, Any], Any | None]:
    """Train one exact matrix cell and retain aggregate hook evidence only."""

    vision.seed_runtime(torch, seed, deterministic_algorithms_mode="warn_only")
    model = vision.build_model(torchvision, model_config)
    initial_state = vision.model_state_sha256(model)
    model.to(device)
    generator = torch.Generator().manual_seed(seed)
    loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
        num_workers=0,
        pin_memory=False,
        drop_last=False,
    )
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=float(base_config["training"]["learning_rate"]),
        momentum=float(base_config["training"]["momentum"]),
        weight_decay=float(base_config["training"]["weight_decay"]),
    )
    expected_steps = math.ceil(int(scale["rows"]) / batch_size)
    cell_registration = {
        "experiment_id": composition_config["experiment_id"],
        "seed": seed,
        "architecture": model_config["key"],
        "dataset_scale": scale["key"],
        "dataset_roster_sha256": scale["relative_path_set_sha256"],
        "batch_size": batch_size,
        "hook_profile": hook_profile["key"],
        "expected_steps": expected_steps,
        "release_decision": "no_release_authorization",
    }
    collector = None
    if hook_profile["enabled"]:
        collector_class = vision.bound_hook_collector()
        collector = collector_class(
            model,
            module_names=model_config["hook_modules"],
            expected_steps=expected_steps,
            max_events=int(composition_config["matrix"]["max_hook_events_per_cell"]),
            fail_on_nonfinite=True,
            context_sha256=canonical_sha256(cell_registration),
        )

    model.train()
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    started = time.perf_counter()
    examples = 0
    steps = 0
    total_loss = 0.0
    batch_order = hashlib.sha256()
    first_batch_manifest: str | None = None
    first_loss_hex: str | None = None

    with vision.capture_registered_cuda_nondeterminism(
        base_config, f"composition_cell:{canonical_sha256(cell_registration)}"
    ) as warning_report:
        context = collector if collector is not None else _NullContext()
        with context:
            for batch_index, (images, labels, indices) in enumerate(loader):
                manifest = canonical_sha256(
                    {
                        "batch_index": batch_index,
                        "dataset_indices": [int(index) for index in indices.tolist()],
                    }
                )
                batch_order.update(bytes.fromhex(manifest))
                images = images.to(device, non_blocking=False)
                labels = labels.to(device, non_blocking=False)
                optimizer.zero_grad(set_to_none=True)
                logits = model(images)
                loss = torch.nn.functional.cross_entropy(logits, labels)
                if first_batch_manifest is None:
                    first_batch_manifest = manifest
                    first_loss_hex = float(loss.detach().item()).hex()
                loss.backward()
                if collector is not None:
                    collector.step(
                        loss,
                        step=steps,
                        epoch=0,
                        batch_index=batch_index,
                        model=model,
                        learning_rate=float(base_config["training"]["learning_rate"]),
                        tokens=int(images.numel()),
                        target_tokens=int(labels.numel()),
                        batch_manifest_sha256=manifest,
                    )
                optimizer.step()
                count = int(labels.numel())
                total_loss += float(loss.detach().item()) * count
                examples += count
                steps += 1
    torch.cuda.synchronize(device)
    duration = time.perf_counter() - started
    _require(examples == scale["rows"] and steps == expected_steps, "training cell coverage mismatch")
    _require(first_batch_manifest is not None and first_loss_hex is not None, "training cell was empty")

    if collector is None:
        hook_summary = {
            "profile": "no_hook",
            "coverage_status": "not_applicable",
            "event_count": 0,
            "nonfinite_elements": 0,
            "handles_removed": True,
        }
    else:
        finalized = collector.finalize(expected_steps=expected_steps)
        events = finalized.pop("events")
        replay = vision.replay_collector_event_chain(
            events,
            canonical_sha256(cell_registration),
            expected_head_sha256=finalized["event_chain_head_sha256"],
        )
        _require(finalized["coverage_status"] == "complete", "hook coverage incomplete")
        _require(finalized["nonfinite_elements"] == 0, "hook telemetry was non-finite")
        _require(finalized["handles_removed"] is True, "hook handles were not removed")
        hook_summary = {
            "profile": hook_profile["key"],
            "coverage_status": finalized["coverage_status"],
            "event_count": replay["event_count"],
            "event_chain_head_sha256": replay["event_chain_head_sha256"],
            "independent_replay_passed": replay["independent_replay_passed"],
            "nonfinite_elements": finalized["nonfinite_elements"],
            "handles_removed": finalized["handles_removed"],
            "raw_events_retained": False,
        }

    final_state = vision.model_state_sha256(model)
    cell = {
        **cell_registration,
        "cell_registration_sha256": canonical_sha256(cell_registration),
        "initial_state_sha256": initial_state,
        "final_state_sha256": final_state,
        "first_batch_manifest_sha256": first_batch_manifest,
        "first_pre_backward_loss_hex": first_loss_hex,
        "batch_order_sha256": batch_order.hexdigest(),
        "examples_seen": examples,
        "optimizer_steps": steps,
        "mean_batch_weighted_cross_entropy": total_loss / examples,
        "duration_seconds": duration,
        "examples_per_second": examples / duration,
        "peak_gpu_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "peak_gpu_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        "peak_host_rss_bytes": process_peak_rss_bytes(),
        "hook": hook_summary,
        "cuda_warning_observation": warning_report,
        "bitwise_reproducible": False,
        "raw_per_example_material_retained": False,
        "authority": dict(AUTHORITY),
    }
    if retain_model:
        model.to("cpu")
        torch.cuda.empty_cache()
        return cell, model
    del model
    torch.cuda.empty_cache()
    return cell, None


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return False


def compare_pair(pair: str, cells: list[Mapping[str, Any]], required: list[str]) -> dict[str, Any]:
    _require(len(cells) == 2, "matched pair must contain two hook profiles")
    by_hook = {cell["hook_profile"]: cell for cell in cells}
    _require(set(by_hook) == {"no_hook", "current_registered"}, "matched hook pair is incomplete")
    baseline = by_hook["no_hook"]
    hooked = by_hook["current_registered"]
    matches = {field: baseline[field] == hooked[field] for field in required}
    _require(all(matches.values()), f"paired hook preconditions diverged: {pair}")
    return {
        "pair_id": pair,
        "pair_id_sha256": hashlib.sha256(pair.encode("utf-8")).hexdigest(),
        "seed": baseline["seed"],
        "architecture": baseline["architecture"],
        "dataset_scale": baseline["dataset_scale"],
        "batch_size": baseline["batch_size"],
        "profile_execution_order": [cell["hook_profile"] for cell in cells],
        "required_exact_matches": matches,
        "duration_ratio_hooked_over_no_hook": hooked["duration_seconds"] / baseline["duration_seconds"],
        "throughput_ratio_hooked_over_no_hook": hooked["examples_per_second"] / baseline["examples_per_second"],
        "peak_allocated_byte_delta": hooked["peak_gpu_allocated_bytes"] - baseline["peak_gpu_allocated_bytes"],
        "final_state_sha256_equal": hooked["final_state_sha256"] == baseline["final_state_sha256"],
        "causal_claimed": False,
    }


def _metric_summary(values: list[float]) -> dict[str, float | int]:
    _require(len(values) >= 3, "variance summary requires at least three registered seeds")
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sample_standard_deviation": statistics.stdev(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def pair_minus_singleton_mean(pair_value: float, singleton_values: Iterable[float]) -> float:
    values = [float(value) for value in singleton_values]
    _require(len(values) == 2, "vision pair contrast requires exactly two singleton values")
    _require(
        math.isfinite(float(pair_value)) and all(math.isfinite(value) for value in values),
        "vision pair contrast inputs must be finite",
    )
    return float(pair_value) - statistics.fmean(values)


def summarize_cells(cells: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int, str], list[Mapping[str, Any]]] = {}
    for cell in cells:
        key = (cell["architecture"], cell["dataset_scale"], cell["batch_size"], cell["hook_profile"])
        grouped.setdefault(key, []).append(cell)
    result = []
    for key, records in sorted(grouped.items()):
        result.append(
            {
                "architecture": key[0],
                "dataset_scale": key[1],
                "batch_size": key[2],
                "hook_profile": key[3],
                "duration_seconds": _metric_summary([float(item["duration_seconds"]) for item in records]),
                "examples_per_second": _metric_summary([float(item["examples_per_second"]) for item in records]),
                "peak_gpu_allocated_bytes": _metric_summary([float(item["peak_gpu_allocated_bytes"]) for item in records]),
                "mean_cross_entropy": _metric_summary([float(item["mean_batch_weighted_cross_entropy"]) for item in records]),
            }
        )
    return result


def summarize_pairs(pairs: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[Mapping[str, Any]]] = {}
    for pair in pairs:
        key = (pair["architecture"], pair["dataset_scale"], pair["batch_size"])
        grouped.setdefault(key, []).append(pair)
    return [
        {
            "architecture": key[0],
            "dataset_scale": key[1],
            "batch_size": key[2],
            "duration_ratio_hooked_over_no_hook": _metric_summary([float(item["duration_ratio_hooked_over_no_hook"]) for item in records]),
            "throughput_ratio_hooked_over_no_hook": _metric_summary([float(item["throughput_ratio_hooked_over_no_hook"]) for item in records]),
            "peak_allocated_byte_delta": _metric_summary([float(item["peak_allocated_byte_delta"]) for item in records]),
            "final_state_exact_match_count": sum(bool(item["final_state_sha256_equal"]) for item in records),
            "n": len(records),
        }
        for key, records in sorted(grouped.items())
    ]


def _evaluate_probabilities(
    torch: Any,
    probabilities: Mapping[str, Any],
    labels: Any,
    clean_correct: Mapping[str, Any] | None,
    totals: dict[str, dict[str, float | int]],
) -> None:
    for key, probs in probabilities.items():
        safe = probs.clamp_min(torch.finfo(probs.dtype).tiny)
        totals[key]["loss"] += float(-safe[torch.arange(labels.numel(), device=labels.device), labels].log().sum().item())
        predictions = probs.argmax(1)
        totals[key]["correct"] += int((predictions == labels).sum().item())
        if clean_correct is not None:
            mask = clean_correct[key]
            totals[key]["clean_correct"] += int(mask.sum().item())
            totals[key]["attack_successes"] += int((mask & (predictions != labels)).sum().item())


def evaluate_model_output_composition(
    torch: Any,
    models: Mapping[str, Any],
    test_dataset: Any,
    base_config: Mapping[str, Any],
    config: Mapping[str, Any],
    device: Any,
    seed: int,
    scale_key: str,
) -> dict[str, Any]:
    """Evaluate two members and their probability average using aggregates."""

    spec = config["model_output_composition"]
    ordered_keys = spec["member_architectures"]
    _require(set(models) == set(ordered_keys), "composition reference models are incomplete")
    members = [models[key].to(device).eval() for key in ordered_keys]
    evaluator_keys = [*ordered_keys, "probability_average_ensemble"]
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    phase_started = time.perf_counter()

    def probabilities(inputs: Any) -> dict[str, Any]:
        member_probs = [torch.softmax(model(inputs), dim=1) for model in members]
        return {
            ordered_keys[0]: member_probs[0],
            ordered_keys[1]: member_probs[1],
            "probability_average_ensemble": (member_probs[0] + member_probs[1]) / 2,
        }

    clean_totals = {key: {"loss": 0.0, "correct": 0, "clean_correct": 0, "attack_successes": 0} for key in evaluator_keys}
    disagreement = 0
    clean_loader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=int(base_config["evaluation"]["batch_size"]),
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )
    clean_examples = 0
    with torch.no_grad():
        for images, labels, _indices in clean_loader:
            images = images.to(device)
            labels = labels.to(device)
            probs = probabilities(images)
            _evaluate_probabilities(torch, probs, labels, None, clean_totals)
            disagreement += int((probs[ordered_keys[0]].argmax(1) != probs[ordered_keys[1]].argmax(1)).sum().item())
            clean_examples += int(labels.numel())
    _require(clean_examples == spec["clean_test_rows"], "full clean composition evaluation was incomplete")
    clean_report = {
        "examples": clean_examples,
        "evaluators": {
            key: {
                "mean_cross_entropy": clean_totals[key]["loss"] / clean_examples,
                "top1_accuracy": clean_totals[key]["correct"] / clean_examples,
            }
            for key in evaluator_keys
        },
        "member_prediction_disagreement": disagreement / clean_examples,
    }

    subset = vision.build_red_team_subset(
        test_dataset,
        int(spec["perturbation_test_rows"]),
        int(spec["perturbation_subset_seed"]),
    )
    subset_loader = torch.utils.data.DataLoader(
        subset,
        batch_size=int(base_config["evaluation"]["batch_size"]),
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )
    mean = torch.tensor(base_config["preprocessing"]["normalize_mean"], device=device).view(1, 3, 1, 1)
    std = torch.tensor(base_config["preprocessing"]["normalize_std"], device=device).view(1, 3, 1, 1)
    noise_generator = torch.Generator(device="cpu").manual_seed(int(spec["perturbation_subset_seed"]))
    conditions = spec["conditions"]
    condition_totals = {
        condition: {key: {"loss": 0.0, "correct": 0, "clean_correct": 0, "attack_successes": 0} for key in evaluator_keys}
        for condition in conditions
    }
    condition_disagreement = {condition: 0 for condition in conditions}
    condition_linf = {condition: 0.0 for condition in conditions}
    perturbation_examples = 0
    with vision.capture_registered_cuda_nondeterminism(
        base_config, f"model_output_composition:scale={scale_key}:seed={seed}"
    ) as warning_report:
        for images, labels, _indices in subset_loader:
            images = images.to(device)
            labels = labels.to(device)
            pixels = (images * std + mean).clamp(0.0, 1.0)
            with torch.no_grad():
                clean_probs = probabilities(images)
            clean_correct = {key: clean_probs[key].argmax(1) == labels for key in evaluator_keys}
            condition_inputs: dict[str, Any] = {"clean": images}
            bright = vision.apply_brightness(pixels, float(spec["brightness_factor"]))
            condition_inputs["brightness"] = (bright - mean) / std
            noisy = vision.apply_deterministic_noise(
                torch, pixels, float(spec["gaussian_noise_std"]), noise_generator
            )
            condition_inputs["gaussian_noise"] = (noisy - mean) / std

            epsilon = float(spec["fgsm_epsilon"])
            condition_linf["brightness"] = max(condition_linf["brightness"], vision.measured_pixel_linf(torch, bright, pixels))
            condition_linf["gaussian_noise"] = max(condition_linf["gaussian_noise"], vision.measured_pixel_linf(torch, noisy, pixels))
            source_conditions = {
                "alexnet": "alexnet_fgsm",
                "densenet121": "densenet121_fgsm",
                "probability_average_ensemble": "ensemble_fgsm",
            }
            _require(list(source_conditions) == list(spec["fgsm_sources"]), "FGSM source order differs")
            for source, condition in source_conditions.items():
                attack_pixels = pixels.detach().clone().requires_grad_(True)
                attack_probs = probabilities((attack_pixels - mean) / std)[source]
                attack_loss = -attack_probs.clamp_min(torch.finfo(attack_probs.dtype).tiny)[
                    torch.arange(labels.numel(), device=device), labels
                ].log().mean()
                gradient = torch.autograd.grad(attack_loss, attack_pixels, only_inputs=True)[0]
                adversarial_pixels = (pixels + epsilon * gradient.sign()).clamp(0.0, 1.0)
                condition_inputs[condition] = (adversarial_pixels - mean) / std
                condition_linf[condition] = max(
                    condition_linf[condition],
                    vision.measured_pixel_linf(torch, adversarial_pixels, pixels),
                )
                _require(
                    condition_linf[condition] <= epsilon + 1e-7,
                    f"{source} FGSM exceeded its pixel L-infinity bound",
                )

            for condition, inputs in condition_inputs.items():
                with torch.no_grad():
                    observed = probabilities(inputs)
                _evaluate_probabilities(torch, observed, labels, clean_correct, condition_totals[condition])
                condition_disagreement[condition] += int((observed[ordered_keys[0]].argmax(1) != observed[ordered_keys[1]].argmax(1)).sum().item())
            perturbation_examples += int(labels.numel())
    _require(perturbation_examples == spec["perturbation_test_rows"], "perturbation composition evaluation was incomplete")

    perturbation_report: dict[str, Any] = {}
    for condition in conditions:
        evaluators = {}
        for key in evaluator_keys:
            totals = condition_totals[condition][key]
            denominator = int(totals["clean_correct"])
            evaluators[key] = {
                "mean_cross_entropy": float(totals["loss"]) / perturbation_examples,
                "top1_accuracy": int(totals["correct"]) / perturbation_examples,
                "attack_successes_on_clean_correct": int(totals["attack_successes"]),
                "clean_correct_denominator": denominator,
                "attack_success_rate_on_clean_correct": (
                    int(totals["attack_successes"]) / denominator if denominator else None
                ),
            }
        perturbation_report[condition] = {
            "examples": perturbation_examples,
            "evaluators": evaluators,
            "member_prediction_disagreement": condition_disagreement[condition] / perturbation_examples,
            "measured_max_pixel_linf": condition_linf[condition],
        }

    torch.cuda.synchronize(device)
    phase_duration = time.perf_counter() - phase_started
    phase_resources = {
        "duration_seconds": phase_duration,
        "peak_gpu_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "peak_gpu_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        "peak_host_rss_bytes": process_peak_rss_bytes(),
    }
    for model in members:
        model.to("cpu")
    torch.cuda.empty_cache()
    primary_contrasts: dict[str, Any] = {
        "baseline": "arithmetic_mean_of_the_two_singleton_metrics",
        "best_singleton_contrast_used": False,
        "full_clean": {},
        "perturbation_subset": {},
    }
    ensemble_key = "probability_average_ensemble"
    for metric in ("top1_accuracy", "mean_cross_entropy"):
        primary_contrasts["full_clean"][metric] = pair_minus_singleton_mean(
            float(clean_report["evaluators"][ensemble_key][metric]),
            (float(clean_report["evaluators"][key][metric]) for key in ordered_keys),
        )
    for condition in conditions:
        primary_contrasts["perturbation_subset"][condition] = {}
        for metric in (
            "top1_accuracy",
            "mean_cross_entropy",
            "attack_success_rate_on_clean_correct",
        ):
            values = [perturbation_report[condition]["evaluators"][key][metric] for key in ordered_keys]
            ensemble_value = perturbation_report[condition]["evaluators"][ensemble_key][metric]
            primary_contrasts["perturbation_subset"][condition][metric] = (
                pair_minus_singleton_mean(float(ensemble_value), (float(value) for value in values))
                if ensemble_value is not None and all(value is not None for value in values)
                else None
            )

    return {
        "seed": seed,
        "dataset_scale": scale_key,
        "reference_cell": {
            "dataset_scale": scale_key,
            "batch_size": spec["reference_cells"]["batch_size"],
            "hook_profile": spec["reference_cells"]["hook_profile"],
        },
        "member_architectures": list(ordered_keys),
        "ensemble_rule": spec["ensemble_rule"],
        "full_clean": clean_report,
        "perturbation_subset": perturbation_report,
        "fgsm_threat_model": spec["fgsm_threat_model"],
        "attack_success_denominator": spec["attack_success_denominator"],
        "source_target_transfer_matrix_evaluated": True,
        "primary_pair_contrasts": primary_contrasts,
        "cuda_warning_observation": warning_report,
        "aggregate_only": True,
        "descriptive_only": True,
        "ordered_model_quality_claimed": False,
        "causal_composition_claimed": False,
        "release_evidence": False,
        "authority": dict(AUTHORITY),
        "resource_observation": phase_resources,
    }


def summarize_model_output(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    evaluators = ["alexnet", "densenet121", "probability_average_ensemble"]
    for scale in SCALE_COUNTS:
        scale_records = [item for item in records if item["dataset_scale"] == scale]
        _require(len(scale_records) == 5, f"model-output seed closure failed for {scale}")
        for evaluator in evaluators:
            rows.append(
                {
                    "dataset_scale": scale,
                    "scope": "full_clean",
                    "condition": "clean",
                    "evaluator": evaluator,
                    "top1_accuracy": _metric_summary([float(item["full_clean"]["evaluators"][evaluator]["top1_accuracy"]) for item in scale_records]),
                    "mean_cross_entropy": _metric_summary([float(item["full_clean"]["evaluators"][evaluator]["mean_cross_entropy"]) for item in scale_records]),
                }
            )
        for condition in ["clean", "brightness", "gaussian_noise", "alexnet_fgsm", "densenet121_fgsm", "ensemble_fgsm"]:
            for evaluator in evaluators:
                observed = [item["perturbation_subset"][condition]["evaluators"][evaluator] for item in scale_records]
                asr_values = [float(item["attack_success_rate_on_clean_correct"]) for item in observed if item["attack_success_rate_on_clean_correct"] is not None]
                rows.append(
                    {
                        "dataset_scale": scale,
                        "scope": "registered_512_subset",
                        "condition": condition,
                        "evaluator": evaluator,
                        "top1_accuracy": _metric_summary([float(item["top1_accuracy"]) for item in observed]),
                        "mean_cross_entropy": _metric_summary([float(item["mean_cross_entropy"]) for item in observed]),
                        "attack_success_rate_on_clean_correct": _metric_summary(asr_values) if len(asr_values) == 5 else None,
                        "member_prediction_disagreement": _metric_summary([float(item["perturbation_subset"][condition]["member_prediction_disagreement"]) for item in scale_records]),
                    }
                )
    return rows


def build_suite_export(
    config: Mapping[str, Any],
    cells: list[Mapping[str, Any]],
    composition_records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the suite's closed, aggregate-only vision interchange shape."""

    model_keys = [item["key"] for item in config["matrix"]["architectures"]]
    seeds = list(config["matrix"]["replicate_seeds"])
    scales = [int(item["rows"]) for item in config["matrix"]["dataset_scales"]]
    scale_rows = {item["key"]: int(item["rows"]) for item in config["matrix"]["dataset_scales"]}
    resources = []
    for model_key in model_keys:
        model_cells = [cell for cell in cells if cell["architecture"] == model_key]
        _require(len(model_cells) == 60, f"resource cell closure failed for {model_key}")
        resources.append(
            {
                "model_key": model_key,
                "wall_clock_seconds": sum(float(cell["duration_seconds"]) for cell in model_cells),
                "peak_gpu_reserved_bytes": max(int(cell["peak_gpu_reserved_bytes"]) for cell in model_cells),
                "peak_host_rss_bytes": max(int(cell["peak_host_rss_bytes"]) for cell in model_cells),
                "artifact_bytes": 0,
            }
        )

    subset_scalars: list[dict[str, Any]] = []
    evaluator_rows = [
        (["alexnet"], "alexnet"),
        (["densenet121"], "densenet121"),
        (["alexnet", "densenet121"], "probability_average_ensemble"),
    ]
    for record in sorted(
        composition_records,
        key=lambda item: (scale_rows[item["dataset_scale"]], seeds.index(item["seed"])),
    ):
        for subset, evaluator in evaluator_rows:
            full = record["full_clean"]["evaluators"][evaluator]
            brightness = record["perturbation_subset"]["brightness"]["evaluators"][evaluator]
            noise = record["perturbation_subset"]["gaussian_noise"]["evaluators"][evaluator]
            ensemble_fgsm = record["perturbation_subset"]["ensemble_fgsm"]["evaluators"][evaluator]
            asr = ensemble_fgsm["attack_success_rate_on_clean_correct"]
            _require(asr is not None, "suite export requires a nonzero clean-correct FGSM denominator")
            metrics = {
                "clean_top1_accuracy": float(full["top1_accuracy"]),
                "clean_mean_cross_entropy": float(full["mean_cross_entropy"]),
                "brightness_top1_accuracy": float(brightness["top1_accuracy"]),
                "gaussian_noise_top1_accuracy": float(noise["top1_accuracy"]),
                "ensemble_fgsm_top1_accuracy": float(ensemble_fgsm["top1_accuracy"]),
                "ensemble_fgsm_attack_success_rate_on_clean_correct": float(asr),
                "ensemble_fgsm_member_prediction_disagreement": (
                    float(record["perturbation_subset"]["ensemble_fgsm"]["member_prediction_disagreement"])
                    if len(subset) == 2
                    else 0.0
                ),
            }
            _require(
                all(math.isfinite(value) for value in metrics.values()),
                "suite export metrics must be finite",
            )
            subset_scalars.append(
                {
                    "model_keys": subset,
                    "scale": scale_rows[record["dataset_scale"]],
                    "seed": int(record["seed"]),
                    "metrics": metrics,
                }
            )
    _require(len(subset_scalars) == 45, "suite export requires 45 subset/scale/seed rows")
    return {
        "schema_version": "1.0",
        "modality": "vision",
        "protected_unit_population": "eurosat_test_image",
        "model_keys": model_keys,
        "seeds": seeds,
        "scales": scales,
        "authority": dict(AUTHORITY),
        "resources": resources,
        "subset_scalars": subset_scalars,
    }


def training_cell_record_id(pair: str, hook_profile: str) -> str:
    return f"training-cell:{hashlib.sha256(pair.encode('utf-8')).hexdigest()}:{hook_profile}"


def composition_record_id(seed: int, scale_key: str) -> str:
    return f"model-output:seed={seed}:scale={scale_key}"


def checkpoint_context(
    config: Mapping[str, Any],
    source: Mapping[str, Any],
    run_id: str,
    run_started_at_utc: datetime,
    initial_deadline_utc: str | None,
) -> dict[str, Any]:
    effective, deadline = resolve_effective_deadline(
        run_started_at_utc,
        int(config["resource_budget"]["wall_clock_seconds"]),
        initial_deadline_utc,
    )
    return {
        "schema_version": "1.0",
        "experiment_id": config["experiment_id"],
        "run_id": run_id,
        "configuration_canonical_sha256": canonical_sha256(config),
        "configuration_bytes_sha256": source["composition_config_bytes_sha256"],
        "composition_runner_sha256": source["composition_runner_sha256"],
        "base_runner_sha256": source["base_runner_sha256"],
        "hook_sha256": source["hook_sha256"],
        "dataset_archive_sha256": config["base_vision_protocol"]["dataset_archive_sha256"],
        "expected_training_cells": config["matrix"]["total_training_cells"],
        "expected_model_output_records": (
            len(config["matrix"]["replicate_seeds"])
            * len(config["model_output_composition"]["reference_cells"]["dataset_scales"])
        ),
        "raw_or_per_example_material_allowed": False,
        "resource_budget": dict(config["resource_budget"]),
        "run_started_at_utc": deadline["run_started_at_utc"],
        "local_budget_deadline_utc": deadline["local_12h_deadline_utc"],
        "initial_supplied_deadline_utc": deadline["supplied_deadline_utc"],
        "persisted_effective_deadline_utc": effective.isoformat(),
    }


def prepare_output_directory(
    path: Path,
    config: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    resume: bool,
) -> tuple[Path, Path]:
    """Create a fresh run or safely adopt only its matching incomplete ledger."""

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = path / config["output"]["checkpoint_directory"]
    context_path = checkpoint / config["output"]["checkpoint_context"]
    completion = path / config["output"]["completion_manifest"]
    if not path.exists():
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
        checkpoint.mkdir(mode=0o700)
        os.chmod(checkpoint, 0o700)
        payload = json.dumps(context, allow_nan=False, indent=2, sort_keys=True) + "\n"
        vision.atomic_write_new(context_path, payload)
        os.chmod(context_path, 0o600)
        return path, checkpoint

    _require(resume, "existing output directory requires explicit --resume")
    _require(path.is_dir() and not path.is_symlink(), "resume output must be a regular directory")
    _require(not completion.exists(), "a completed run cannot be resumed")
    _require(
        set(item.name for item in path.iterdir()) == {config["output"]["checkpoint_directory"]},
        "resume directory contains non-checkpoint partial artifacts",
    )
    _require(checkpoint.is_dir() and not checkpoint.is_symlink(), "invalid checkpoint directory")
    payload = vision.read_bounded_regular_file(context_path, 64 * 1024, "checkpoint context")
    observed = json.loads(payload.decode("utf-8", errors="strict"))
    _require(observed == context, "checkpoint context does not match config/source/run identity")
    os.chmod(path, 0o700)
    os.chmod(checkpoint, 0o700)
    return path, checkpoint


def load_checkpoint_records(
    ledger_path: Path,
    *,
    context_sha256: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not ledger_path.exists():
        return {}
    payload = vision.read_bounded_regular_file(
        ledger_path, 64 * 1024 * 1024, "composition checkpoint ledger"
    )
    _require(not payload or payload.endswith(b"\n"), "checkpoint ledger has an incomplete tail")
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for line_number, line in enumerate(payload.splitlines(), start=1):
        _require(0 < len(line) <= 1024 * 1024, "checkpoint record exceeds its byte cap")
        envelope = json.loads(line.decode("utf-8", errors="strict"))
        _require(
            isinstance(envelope, dict)
            and set(envelope)
            == {
                "schema_version",
                "record_type",
                "record_id",
                "context_sha256",
                "aggregate_sha256",
                "aggregate",
            },
            f"checkpoint record {line_number} has invalid fields",
        )
        _require(envelope["schema_version"] == "1.0", "checkpoint schema differs")
        _require(
            envelope["record_type"] in {"completed_training_cell", "completed_model_output"},
            "checkpoint record type differs",
        )
        _require(envelope["context_sha256"] == context_sha256, "checkpoint context digest differs")
        _require(
            canonical_sha256(envelope["aggregate"]) == envelope["aggregate_sha256"],
            "checkpoint aggregate digest differs",
        )
        key = (envelope["record_type"], envelope["record_id"])
        _require(key not in records, "duplicate checkpoint record id")
        records[key] = envelope["aggregate"]
    return records


def append_checkpoint_record(
    ledger_path: Path,
    *,
    record_type: str,
    record_id: str,
    aggregate: Mapping[str, Any],
    context_sha256: str,
) -> None:
    """Append and fsync one bounded aggregate record; no tensors or examples."""

    _require(aggregate.get("authority") == AUTHORITY, "durable aggregate authority differs")
    envelope = {
        "schema_version": "1.0",
        "record_type": record_type,
        "record_id": record_id,
        "context_sha256": context_sha256,
        "aggregate_sha256": canonical_sha256(aggregate),
        "aggregate": aggregate,
    }
    payload = canonical_json(envelope) + b"\n"
    _require(len(payload) <= 1024 * 1024, "checkpoint aggregate exceeds its byte cap")
    before = None
    if ledger_path.exists():
        before = ledger_path.lstat()
        _require(
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1
            and before.st_size <= 64 * 1024 * 1024,
            "checkpoint ledger must be one bounded regular file",
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(ledger_path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        _require(
            stat.S_ISREG(opened.st_mode)
            and opened.st_nlink == 1
            and opened.st_size <= 64 * 1024 * 1024,
            "checkpoint ledger must be one bounded regular file",
        )
        if before is not None:
            _require(
                (before.st_dev, before.st_ino, before.st_size)
                == (opened.st_dev, opened.st_ino, opened.st_size),
                "checkpoint ledger changed before append",
            )
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            _require(written > 0, "checkpoint append made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_resumed_records(
    config: Mapping[str, Any],
    records: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    expected_cells: dict[str, tuple[int, str, str, int, str]] = {}
    for seed in config["matrix"]["replicate_seeds"]:
        for scale in config["matrix"]["dataset_scales"]:
            for batch_size in config["matrix"]["batch_sizes"]:
                for architecture in config["matrix"]["architectures"]:
                    pair = pair_id(seed, architecture["key"], scale["key"], batch_size)
                    for hook in config["matrix"]["hook_profiles"]:
                        expected_cells[training_cell_record_id(pair, hook["key"])] = (
                            seed,
                            architecture["key"],
                            scale["key"],
                            batch_size,
                            hook["key"],
                        )
    expected_outputs = {
        composition_record_id(seed, scale_key): (seed, scale_key)
        for seed in config["matrix"]["replicate_seeds"]
        for scale_key in config["model_output_composition"]["reference_cells"]["dataset_scales"]
    }
    for (record_type, record_id), aggregate in records.items():
        if record_type == "completed_training_cell":
            _require(record_id in expected_cells, "checkpoint contains an unregistered training cell")
            expected = expected_cells[record_id]
            observed = (
                aggregate.get("seed"),
                aggregate.get("architecture"),
                aggregate.get("dataset_scale"),
                aggregate.get("batch_size"),
                aggregate.get("hook_profile"),
            )
            _require(observed == expected, "checkpoint training-cell identity differs")
            _require(
                aggregate.get("raw_per_example_material_retained") is False,
                "checkpoint cell retained forbidden material",
            )
        else:
            _require(record_id in expected_outputs, "checkpoint contains an unregistered model-output record")
            _require(
                (aggregate.get("seed"), aggregate.get("dataset_scale"))
                == expected_outputs[record_id],
                "checkpoint model-output identity differs",
            )
            _require(
                aggregate.get("aggregate_only") is True,
                "checkpoint model-output record is not aggregate-only",
            )
        _require(aggregate.get("authority") == AUTHORITY, "checkpoint authority differs")


def build_markdown(report: Mapping[str, Any]) -> str:
    cell_rows = [
        "| {architecture} | {dataset_scale} | {batch_size} | {hook_profile} | {throughput:.2f} | {duration:.2f} |".format(
            architecture=item["architecture"],
            dataset_scale=item["dataset_scale"],
            batch_size=item["batch_size"],
            hook_profile=item["hook_profile"],
            throughput=item["examples_per_second"]["mean"],
            duration=item["duration_seconds"]["mean"],
        )
        for item in report["cell_summaries"]
    ]
    pair_rows = [
        "| {architecture} | {dataset_scale} | {batch_size} | {ratio:.4f} | {std:.4f} |".format(
            architecture=item["architecture"],
            dataset_scale=item["dataset_scale"],
            batch_size=item["batch_size"],
            ratio=item["duration_ratio_hooked_over_no_hook"]["mean"],
            std=item["duration_ratio_hooked_over_no_hook"]["sample_standard_deviation"],
        )
        for item in report["paired_hook_summaries"]
    ]
    composition_rows = [
        "| {dataset_scale} | {scope} | {condition} | {evaluator} | {accuracy:.4f} | {loss:.4f} |".format(
            dataset_scale=item["dataset_scale"],
            scope=item["scope"],
            condition=item["condition"],
            evaluator=item["evaluator"],
            accuracy=item["top1_accuracy"]["mean"],
            loss=item["mean_cross_entropy"]["mean"],
        )
        for item in report["model_output_composition_summary"]
    ]
    return "\n".join(
        [
            "# EuroSAT vision composition-scaling execution report",
            "",
            "This is an experimental operational benchmark and descriptive model-output composition screen. It is not release evidence, an attack battery, a scaling law, or a causal/risk ordering claim.",
            "",
            "## Matrix",
            "",
            f"- {report['matrix_execution']['completed_cells']} aggregate cells in {report['matrix_execution']['completed_pairs']} matched hook/no-hook pairs.",
            "- Factors: AlexNet/DenseNet-121, three nested real EuroSAT training rosters (5,400/10,800/21,600), batches 64/128, current hooks on/off, and five registered seeds.",
            "- Every architecture/scale/batch/seed/hook cell is an independent fresh-model run; nested scales are not cumulative checkpoints.",
            "- Matched profiles share exact initialization, first batch, pre-backward first loss, and batch order. Final CUDA states may differ and are not required to match.",
            "- Timings include the first measured epoch without warm-up exclusion and apply only to the recorded NVIDIA L4 runtime.",
            "",
            "| Architecture | Scale | Batch | Hook profile | Mean examples/s | Mean seconds |",
            "|---|---|---:|---|---:|---:|",
            *cell_rows,
            "",
            "## Paired hook observations",
            "",
            "| Architecture | Scale | Batch | Mean hooked/no-hook duration | Across-seed sample SD |",
            "|---|---|---:|---:|---:|",
            *pair_rows,
            "",
            "Ratios are descriptive paired observations across five seeds, not causal effects or portable overhead constants.",
            "",
            "## Model-output composition",
            "",
            "At every registered scale, the batch-128 current-hook AlexNet and DenseNet-121 cells are evaluated individually and as an arithmetic probability average. Clean metrics use all 5,400 test images; registered perturbations use 512 real held-out images. AlexNet-, DenseNet-, and ensemble-sourced FGSM inputs are evaluated against all three targets. Member disagreement and all evaluator metrics are aggregate-only.",
            "",
            "| Scale | Scope | Condition | Evaluator | Mean accuracy | Mean cross-entropy |",
            "|---|---|---|---|---:|---:|",
            *composition_rows,
            "",
            "Ensemble behavior is descriptive. The experiment makes no ordered-quality, robustness, causal-composition, authorization, or release-evidence claim.",
            "",
            "## Release-interface scenarios",
            "",
            "M0-M3 are copied as policy-only interface scenarios. The timing matrix does not measure them, emit a numerical risk score, or assume risk monotonicity.",
            "",
            "## Decision",
            "",
            "`no_release_authorization`; `authorization_eligible: false`; `assessment_input_emitted: false`; `attack_battery_eligible: false`; `can_clear: false`; `can_block: false`; `requires_approved_recollection: true`.",
            "",
        ]
    )


def publish(output_dir: Path, report: dict[str, Any], config: Mapping[str, Any]) -> None:
    output = config["output"]
    markdown_payload = build_markdown(report)
    markdown_bytes = markdown_payload.encode("utf-8")
    checkpoint_dir = output_dir / output["checkpoint_directory"]
    checkpoint_artifacts = []
    _require(
        checkpoint_dir.is_dir()
        and not checkpoint_dir.is_symlink()
        and set(path.name for path in checkpoint_dir.iterdir())
        == {output["checkpoint_context"], output["checkpoint_ledger"]},
        "checkpoint artifact set differs before publication",
    )
    for name in [output["checkpoint_context"], output["checkpoint_ledger"]]:
        path = checkpoint_dir / name
        payload = vision.read_bounded_regular_file(
            path,
            64 * 1024 if name == output["checkpoint_context"] else 64 * 1024 * 1024,
            f"checkpoint artifact {name}",
        )
        checkpoint_artifacts.append(
            {
                "path": f"{output['checkpoint_directory']}/{name}",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    report["artifact_manifest"] = {
        "markdown": {
            "path": output["markdown_report"],
            "bytes": len(markdown_bytes),
            "sha256": hashlib.sha256(markdown_bytes).hexdigest(),
        },
        "checkpoint_artifacts": checkpoint_artifacts,
        "model_specific_artifact_bytes": 0,
        "raw_or_per_example_artifacts": False,
        "aggregate_artifact_budget": {
            "max_bytes": int(config["resource_budget"]["max_aggregate_artifact_bytes"]),
            "components": ["checkpoint_context", "checkpoint_ledger", "markdown_report", "json_report", "completion_manifest"],
            "completion_payload_included_in_pre_completion_prediction": True,
        },
    }
    report_payload = json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
    report_bytes = report_payload.encode("utf-8")
    markdown_path = output_dir / output["markdown_report"]
    report_path = output_dir / output["json_report"]
    completion = {
        "schema_version": "1.0",
        "status": "complete",
        "experiment_id": config["experiment_id"],
        "report": {
            "path": output["json_report"],
            "sha256": hashlib.sha256(report_bytes).hexdigest(),
            "bytes": len(report_bytes),
        },
        "authority": dict(AUTHORITY),
    }
    completion_payload = json.dumps(completion, allow_nan=False, indent=2, sort_keys=True) + "\n"
    aggregate_artifact_bytes = (
        sum(int(item["bytes"]) for item in checkpoint_artifacts)
        + len(markdown_bytes)
        + len(report_bytes)
        + len(completion_payload.encode("utf-8"))
    )
    _require(
        aggregate_artifact_bytes
        <= int(config["resource_budget"]["max_aggregate_artifact_bytes"]),
        "child aggregate artifact-byte budget exceeded before completion",
    )
    vision.atomic_write_new(markdown_path, markdown_payload)
    os.chmod(markdown_path, 0o600)
    vision.atomic_write_new(report_path, report_payload)
    os.chmod(report_path, 0o600)
    for item in checkpoint_artifacts:
        checkpoint_path = output_dir / item["path"]
        _require(
            checkpoint_path.stat().st_size == item["bytes"]
            and vision.sha256_file(checkpoint_path) == item["sha256"],
            "checkpoint artifact changed during final publication",
        )
    _require(
        set(path.name for path in output_dir.iterdir())
        == {
            output["checkpoint_directory"],
            output["json_report"],
            output["markdown_report"],
        },
        "unexpected pre-completion output entries",
    )
    completion_path = output_dir / output["completion_manifest"]
    vision.atomic_write_new(completion_path, completion_payload)
    os.chmod(completion_path, 0o600)


def run(
    config_path: Path,
    output_dir: Path,
    cache_dir: Path,
    *,
    offline: bool,
    resume: bool,
    deadline_utc: str | None,
) -> dict[str, Any]:
    invocation_started_monotonic = time.monotonic()
    invocation_started_at_utc = datetime.now(timezone.utc)
    config_path = config_path.resolve()
    config, config_bytes_sha256 = load_config_with_digest(config_path)
    base_config, source_binding = load_base_protocol(config)
    output_dir, cache_dir = vision.resolve_disjoint_directory_trees(output_dir, cache_dir)
    source_before = {
        "composition_config_logical_name": vision.repo_logical_name(config_path),
        "composition_config_bytes_sha256": config_bytes_sha256,
        "composition_config_canonical_sha256": canonical_sha256(config),
        "composition_runner_logical_name": "scripts/run_vision_composition_scaling.py",
        "composition_runner_sha256": vision.sha256_file(Path(__file__).resolve()),
        **source_binding,
    }
    if resume and output_dir.exists():
        existing_context_path = (
            output_dir
            / config["output"]["checkpoint_directory"]
            / config["output"]["checkpoint_context"]
        )
        existing_payload = vision.read_bounded_regular_file(
            existing_context_path, 64 * 1024, "checkpoint context"
        )
        existing_context = json.loads(existing_payload.decode("utf-8", errors="strict"))
        _require(isinstance(existing_context, dict), "checkpoint context must be an object")
        persisted_started_at = parse_deadline_utc(existing_context.get("run_started_at_utc"))
        _require(persisted_started_at is not None, "checkpoint run start is missing")
        initial_deadline = existing_context.get("initial_supplied_deadline_utc")
    else:
        persisted_started_at = invocation_started_at_utc
        initial_deadline = deadline_utc
    context = checkpoint_context(
        config,
        source_before,
        output_dir.name,
        persisted_started_at,
        initial_deadline,
    )
    context_sha256 = canonical_sha256(context)
    output_dir, checkpoint_dir = prepare_output_directory(
        output_dir, config, context, resume=resume
    )
    ledger_path = checkpoint_dir / config["output"]["checkpoint_ledger"]
    checkpoint_records = load_checkpoint_records(
        ledger_path, context_sha256=context_sha256
    )
    validate_resumed_records(config, checkpoint_records)
    persisted_deadline = parse_deadline_utc(context["persisted_effective_deadline_utc"])
    _require(persisted_deadline is not None, "persisted effective deadline is missing")
    supplied_this_invocation = parse_deadline_utc(deadline_utc)
    effective_deadline = (
        min(persisted_deadline, supplied_this_invocation)
        if supplied_this_invocation is not None
        else persisted_deadline
    )
    deadline_registry = {
        "run_started_at_utc": persisted_started_at.isoformat(),
        "persisted_effective_deadline_utc": persisted_deadline.isoformat(),
        "supplied_this_invocation_utc": (
            supplied_this_invocation.isoformat() if supplied_this_invocation is not None else None
        ),
        "effective_deadline_utc": effective_deadline.isoformat(),
        "supplied_deadline_may_only_tighten": True,
        "supplied_deadline_extended_persisted_ceiling": False,
    }
    budget_observations = [
        enforce_resource_budget(
            config["resource_budget"],
            started_monotonic=invocation_started_monotonic,
            run_started_at_utc=persisted_started_at,
            effective_deadline_utc=effective_deadline,
            phase="after_checkpoint_preflight",
            gpu_reserved_bytes=0,
        )
    ]

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch, torchvision = vision.require_ml_runtime(base_config)
    device = torch.device("cuda")
    vision.seed_runtime(torch, config["matrix"]["replicate_seeds"][0], deterministic_algorithms_mode="warn_only")
    runtime = vision.runtime_report(torch, torchvision, device)
    _require(runtime["gpu"] == config["runtime"]["required_gpu_name"], "composition experiment requires one NVIDIA L4")
    implementation = vision.implementation_provenance_report(torchvision, base_config)
    observed_provenance = vision.observed_runtime_provenance_registry(runtime, implementation)
    runtime_gate = vision.enforce_runtime_provenance_registration(base_config["runtime"]["expected_provenance"], observed_provenance)

    archive, archive_report = vision.download_verified_archive(base_config["dataset"], cache_dir, offline=offline)
    extraction_manifest = vision.prepare_verified_extraction(archive, cache_dir, base_config["dataset"])
    decoded = vision.validate_decoded_images(cache_dir / vision.DATASET_DIRECTORY, base_config["dataset"]["decoded_validation"])
    full_train, test_dataset, dataset_observation = vision.load_datasets(torchvision, cache_dir, base_config, extraction_manifest)
    scale_datasets, scale_observations = build_nested_scale_datasets(
        full_train,
        cache_dir / vision.DATASET_DIRECTORY,
        config["matrix"]["dataset_scales"],
    )
    base_models = {item["key"]: item for item in base_config["models"]}
    for architecture in config["matrix"]["architectures"]:
        _require(architecture["key"] in base_models, "composition architecture is absent from base protocol")
        _require(
            base_models[architecture["key"]]["constructor"] == architecture["constructor"]
            and base_models[architecture["key"]]["hook_modules"] == architecture["hook_modules"],
            "composition architecture/hook registry differs from base protocol",
        )

    cells: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    composition_records: list[dict[str, Any]] = []
    reference = config["model_output_composition"]["reference_cells"]
    resumed_training_cells = 0
    resumed_model_output_records = 0
    reference_model_reexecutions = 0
    for seed in config["matrix"]["replicate_seeds"]:
        for scale in config["matrix"]["dataset_scales"]:
            output_record_id = composition_record_id(seed, scale["key"])
            saved_output = checkpoint_records.get(
                ("completed_model_output", output_record_id)
            )
            needs_model_output = saved_output is None
            reference_models: dict[str, Any] = {}
            scale_reference_model_reexecutions = 0
            for batch_size in config["matrix"]["batch_sizes"]:
                for architecture in config["matrix"]["architectures"]:
                    identifier = pair_id(seed, architecture["key"], scale["key"], batch_size)
                    pair_cells: list[dict[str, Any]] = []
                    for hook_profile in ordered_hook_profiles(identifier, config["matrix"]["hook_profiles"]):
                        cell_phase = f"training_cell:{identifier}:hook={hook_profile['key']}"
                        budget_observations.append(
                            enforce_resource_budget(
                                config["resource_budget"],
                                started_monotonic=invocation_started_monotonic,
                                run_started_at_utc=persisted_started_at,
                                effective_deadline_utc=effective_deadline,
                                phase=f"before_{cell_phase}",
                                gpu_reserved_bytes=int(torch.cuda.memory_reserved(device)),
                            )
                        )
                        retain = (
                            needs_model_output
                            and scale["key"] in reference["dataset_scales"]
                            and batch_size == reference["batch_size"]
                            and hook_profile["key"] == reference["hook_profile"]
                        )
                        record_id = training_cell_record_id(identifier, hook_profile["key"])
                        record_key = ("completed_training_cell", record_id)
                        saved_cell = checkpoint_records.get(record_key)
                        if saved_cell is not None:
                            resumed_training_cells += 1
                        retained_model = None
                        if saved_cell is None or retain:
                            observed_cell, retained_model = run_training_cell(
                                torch,
                                torchvision,
                                base_config,
                                config,
                                base_models[architecture["key"]],
                                scale_datasets[scale["key"]],
                                scale,
                                batch_size,
                                seed,
                                hook_profile,
                                device,
                                retain_model=retain,
                            )
                            budget_observations.append(
                                enforce_resource_budget(
                                    config["resource_budget"],
                                    started_monotonic=invocation_started_monotonic,
                                    run_started_at_utc=persisted_started_at,
                                    effective_deadline_utc=effective_deadline,
                                    phase=f"after_{cell_phase}",
                                    gpu_reserved_bytes=max(
                                        int(torch.cuda.memory_reserved(device)),
                                        int(observed_cell["peak_gpu_reserved_bytes"]),
                                    ),
                                    host_rss_bytes=max(
                                        process_peak_rss_bytes(),
                                        int(observed_cell["peak_host_rss_bytes"]),
                                    ),
                                )
                            )
                            if saved_cell is None:
                                append_checkpoint_record(
                                    ledger_path,
                                    record_type="completed_training_cell",
                                    record_id=record_id,
                                    aggregate=observed_cell,
                                    context_sha256=context_sha256,
                                )
                                checkpoint_records[record_key] = observed_cell
                                cell = observed_cell
                            else:
                                _require(
                                    all(
                                        observed_cell[field] == saved_cell[field]
                                        for field in config["matrix"]["required_pair_matches"]
                                    ),
                                    "reference-model reexecution diverged from its checkpoint preconditions",
                                )
                                reference_model_reexecutions += 1
                                scale_reference_model_reexecutions += 1
                                cell = dict(saved_cell)
                        else:
                            cell = dict(saved_cell)
                            budget_observations.append(
                                enforce_resource_budget(
                                    config["resource_budget"],
                                    started_monotonic=invocation_started_monotonic,
                                    run_started_at_utc=persisted_started_at,
                                    effective_deadline_utc=effective_deadline,
                                    phase=f"after_checkpoint_reuse_{cell_phase}",
                                    gpu_reserved_bytes=max(
                                        int(torch.cuda.memory_reserved(device)),
                                        int(cell["peak_gpu_reserved_bytes"]),
                                    ),
                                    host_rss_bytes=max(
                                        process_peak_rss_bytes(),
                                        int(cell["peak_host_rss_bytes"]),
                                    ),
                                )
                            )
                        cells.append(cell)
                        pair_cells.append(cell)
                        if retained_model is not None:
                            reference_models[architecture["key"]] = retained_model
                    pairs.append(compare_pair(identifier, pair_cells, config["matrix"]["required_pair_matches"]))
            composition_phase = f"model_output_composition:seed={seed}:scale={scale['key']}"
            budget_observations.append(
                enforce_resource_budget(
                    config["resource_budget"],
                    started_monotonic=invocation_started_monotonic,
                    run_started_at_utc=persisted_started_at,
                    effective_deadline_utc=effective_deadline,
                    phase=f"before_{composition_phase}",
                    gpu_reserved_bytes=int(torch.cuda.memory_reserved(device)),
                )
            )
            if saved_output is None:
                composition_record = evaluate_model_output_composition(
                    torch,
                    reference_models,
                    test_dataset,
                    base_config,
                    config,
                    device,
                    seed,
                    scale["key"],
                )
                composition_record["reference_model_reexecuted_from_aggregate_checkpoint"] = (
                    scale_reference_model_reexecutions > 0
                )
                resources = composition_record["resource_observation"]
                budget_observations.append(
                    enforce_resource_budget(
                        config["resource_budget"],
                        started_monotonic=invocation_started_monotonic,
                        run_started_at_utc=persisted_started_at,
                        effective_deadline_utc=effective_deadline,
                        phase=f"after_{composition_phase}",
                        gpu_reserved_bytes=max(
                            int(torch.cuda.memory_reserved(device)),
                            int(resources["peak_gpu_reserved_bytes"]),
                        ),
                        host_rss_bytes=max(
                            process_peak_rss_bytes(),
                            int(resources["peak_host_rss_bytes"]),
                        ),
                    )
                )
                append_checkpoint_record(
                    ledger_path,
                    record_type="completed_model_output",
                    record_id=output_record_id,
                    aggregate=composition_record,
                    context_sha256=context_sha256,
                )
                checkpoint_records[("completed_model_output", output_record_id)] = composition_record
            else:
                composition_record = dict(saved_output)
                resumed_model_output_records += 1
                resources = composition_record["resource_observation"]
                budget_observations.append(
                    enforce_resource_budget(
                        config["resource_budget"],
                        started_monotonic=invocation_started_monotonic,
                        run_started_at_utc=persisted_started_at,
                        effective_deadline_utc=effective_deadline,
                        phase=f"after_checkpoint_reuse_{composition_phase}",
                        gpu_reserved_bytes=max(
                            int(torch.cuda.memory_reserved(device)),
                            int(resources["peak_gpu_reserved_bytes"]),
                        ),
                        host_rss_bytes=max(
                            process_peak_rss_bytes(),
                            int(resources["peak_host_rss_bytes"]),
                        ),
                    )
                )
            composition_records.append(composition_record)
    _require(len(cells) == config["matrix"]["total_training_cells"], "training matrix was incomplete")
    _require(len(pairs) == config["matrix"]["paired_factor_combinations"], "paired matrix was incomplete")
    expected_composition_records = len(config["matrix"]["replicate_seeds"]) * len(reference["dataset_scales"])
    _require(len(composition_records) == expected_composition_records, "model-output composition matrix was incomplete")
    _require(
        len(checkpoint_records)
        == config["matrix"]["total_training_cells"] + expected_composition_records,
        "checkpoint ledger did not reach exact expected closure",
    )

    archive_after = vision.verify_archive(archive, base_config["dataset"])
    _require(archive_after["sha256"] == archive_report["sha256"], "dataset archive changed during execution")
    runtime_after = vision.runtime_report(torch, torchvision, device)
    implementation_after = vision.implementation_provenance_report(torchvision, base_config)
    _require(runtime_after == runtime and implementation_after == implementation, "runtime or implementation changed during execution")
    source_after = {
        "composition_config_bytes_sha256": vision.sha256_file(config_path),
        "composition_runner_sha256": vision.sha256_file(Path(__file__).resolve()),
        "base_runner_sha256": vision.sha256_file(ROOT / config["base_vision_protocol"]["runner_logical_name"]),
        "hook_sha256": vision.sha256_file(ROOT / config["base_vision_protocol"]["hook_logical_name"]),
    }
    for key, observed in source_after.items():
        expected_key = key
        _require(source_before[expected_key] == observed, f"source changed during execution: {key}")

    budget_observations.append(
        enforce_resource_budget(
            config["resource_budget"],
            started_monotonic=invocation_started_monotonic,
            run_started_at_utc=persisted_started_at,
            effective_deadline_utc=effective_deadline,
            phase="before_final_report_publication",
            gpu_reserved_bytes=int(torch.cuda.memory_reserved(device)),
        )
    )
    expected_budget_checks = (
        2 * config["matrix"]["total_training_cells"]
        + 2 * expected_composition_records
        + 2
    )
    _require(
        len(budget_observations) == expected_budget_checks,
        "resource-budget check coverage is incomplete",
    )
    budget_report = {
        "registered_ceiling": dict(config["resource_budget"]),
        "deadline": deadline_registry,
        "expected_check_count": expected_budget_checks,
        "observed_check_count": len(budget_observations),
        "checks_before_and_after_every_training_and_composition_phase": True,
        "maximum_observed_elapsed_seconds": max(item["elapsed_seconds"] for item in budget_observations),
        "maximum_observed_gpu_reserved_bytes": max(item["observed_gpu_reserved_bytes"] for item in budget_observations),
        "maximum_observed_host_rss_bytes": max(item["observed_host_rss_bytes"] for item in budget_observations),
        "phase_registry_sha256": canonical_sha256([item["phase"] for item in budget_observations]),
        "all_checks_within_budget": all(item["within_budget"] for item in budget_observations),
        "budget_breach_would_emit_completion_manifest": False,
    }
    cuda_warning_summary = vision.summarize_cuda_nondeterminism(
        base_config,
        [
            *[cell["cuda_warning_observation"] for cell in cells],
            *[record["cuda_warning_observation"] for record in composition_records],
        ],
    )
    suite_export = build_suite_export(config, cells, composition_records)
    report = {
        "schema_version": "1.0",
        "report_type": "experimental_vision_composition_scaling_execution",
        "experiment_id": config["experiment_id"],
        "run_id": output_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "aggregate_only": True,
        "experimental_only": True,
        "authorization_eligible": False,
        "authorization_granted": False,
        "assessment_input_emitted": False,
        "attack_battery_eligible": False,
        "can_clear": False,
        "can_block": False,
        "decision": "no_release_authorization",
        "requires_approved_recollection": True,
        "authority": dict(AUTHORITY),
        "model_keys": [item["key"] for item in config["matrix"]["architectures"]],
        "scales": [int(item["rows"]) for item in config["matrix"]["dataset_scales"]],
        "seeds": list(config["matrix"]["replicate_seeds"]),
        "gates": {
            "rights_gate": base_config["dataset"]["rights_gate"],
            "sentinel_data_terms_review": base_config["dataset"]["sentinel_data_terms_review"],
            "runtime_provenance_gate_passed": True,
            "release_authorization": "not_requested_or_emitted",
        },
        "source": source_before,
        "runtime": runtime,
        "runtime_provenance_gate": runtime_gate,
        "implementation_provenance": implementation,
        "cuda_nondeterminism_observation": cuda_warning_summary,
        "resource_budget": budget_report,
        "dataset": {
            "name": base_config["dataset"]["name"],
            "archive_sha256": archive_report["sha256"],
            "retrieval_mode": archive_report["retrieval_mode"],
            "decoded_validation": decoded,
            "full_split_observation": dataset_observation,
            "nested_training_scales": scale_observations,
            "real_images_only": True,
        },
        "matrix_execution": {
            "expected_cells": config["matrix"]["total_training_cells"],
            "completed_cells": len(cells),
            "expected_pairs": config["matrix"]["paired_factor_combinations"],
            "completed_pairs": len(pairs),
            "replicate_seeds": list(config["matrix"]["replicate_seeds"]),
            "training_scales_are_independent_fresh_model_cells": True,
            "between_seed_variance_descriptively_estimated": True,
            "confidence_interval_claimed": False,
        },
        "checkpoint_recovery": {
            "context_sha256": context_sha256,
            "aggregate_completed_record_count": len(checkpoint_records),
            "resumed_training_cell_count": resumed_training_cells,
            "resumed_model_output_record_count": resumed_model_output_records,
            "reference_model_reexecution_count": reference_model_reexecutions,
            "raw_or_per_example_material_retained": False,
            "completion_requires_exact_expected_record_closure": True,
        },
        "cells": cells,
        "matched_hook_pairs": pairs,
        "cell_summaries": summarize_cells(cells),
        "paired_hook_summaries": summarize_pairs(pairs),
        "model_output_composition": composition_records,
        "model_output_composition_summary": summarize_model_output(composition_records),
        "suite_export": suite_export,
        "resource_semantics": {
            "wall_clock_seconds": "sum_of_all_training_cell_timed_regions_for_model_key",
            "peak_gpu_reserved_bytes": "maximum_training_cell_cuda_reserved_high_water_for_model_key",
            "peak_host_rss_bytes": "maximum_observed_process_wide_rss_high_water_after_a_training_cell_for_model_key",
            "artifact_bytes": "sum_of_model_specific_persisted_artifacts_zero_no_weights_are_persisted",
            "singleton_ensemble_fgsm_member_prediction_disagreement": "not_applicable_encoded_as_finite_zero_only_in_suite_export",
        },
        "release_interface_scenarios": config["release_interface_scenarios"],
        "artifact_policy": config["artifact_policy"],
        "limitations": [
            "All timings include the first measured epoch without warm-up exclusion.",
            "Five registered seeds support descriptive sample variance only, not confidence or population inference.",
            "CUDA adaptive average-pooling backward is warn-only nondeterministic; runs are not bitwise reproducible.",
            "Results apply to the recorded NVIDIA L4 software/hardware runtime and are not a scaling law.",
            "Hook/no-hook ratios are paired observations, not portable causal overhead estimates.",
            "Each architecture/scale/batch/seed/hook cell starts from a fresh model and optimizer; nested scales are not cumulative checkpoints.",
            "Probability averaging and perturbation behavior are descriptive and do not order model quality or release risk.",
            "The three FGSM sources form a bounded source-to-target transfer screen, not a complete adversarial evaluation.",
            "Release-interface profiles are policy scenarios and are not measured by the timing matrix.",
        ],
    }
    publish(output_dir, report, config)
    return report


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{os.getpid()}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "reproduction" / "composition-scaling" / "vision-config.json",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "output" / "cache" / "vision-training-hook",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume an incomplete run only when its frozen checkpoint context matches",
    )
    parser.add_argument(
        "--deadline-utc",
        help="optional ISO-8601 UTC deadline; it may tighten but never extend the 12-hour ceiling",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or (
        ROOT / "output" / "composition-scaling" / "vision" / _new_run_id()
    )
    try:
        report = run(
            args.config,
            output_dir,
            args.cache_dir,
            offline=args.offline,
            resume=args.resume,
            deadline_utc=args.deadline_utc,
        )
    except Exception as exc:
        print(f"vision composition-scaling experiment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "completed_cells": report["matrix_execution"]["completed_cells"],
                "decision": report["decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
