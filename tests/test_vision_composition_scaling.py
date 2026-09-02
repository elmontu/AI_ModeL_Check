from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_vision_composition_scaling as composition  # noqa: E402
import run_vision_training_hook_audit as vision  # noqa: E402


CONFIG_PATH = ROOT / "reproduction" / "composition-scaling" / "vision-config.json"


def _config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _composition_record(seed: int, scale_key: str) -> dict:
    evaluators = ["alexnet", "densenet121", "probability_average_ensemble"]
    clean = {
        key: {"top1_accuracy": 0.2 + index * 0.1, "mean_cross_entropy": 2.0 - index * 0.1}
        for index, key in enumerate(evaluators)
    }
    conditions = {}
    for condition_index, condition in enumerate(
        [
            "clean",
            "brightness",
            "gaussian_noise",
            "alexnet_fgsm",
            "densenet121_fgsm",
            "ensemble_fgsm",
        ]
    ):
        conditions[condition] = {
            "examples": 512,
            "evaluators": {
                key: {
                    "top1_accuracy": 0.19 + evaluator_index * 0.1 - condition_index * 0.005,
                    "mean_cross_entropy": 2.1 - evaluator_index * 0.1 + condition_index * 0.01,
                    "attack_successes_on_clean_correct": 4 + evaluator_index,
                    "clean_correct_denominator": 20 + evaluator_index,
                    "attack_success_rate_on_clean_correct": (4 + evaluator_index) / (20 + evaluator_index),
                }
                for evaluator_index, key in enumerate(evaluators)
            },
            "member_prediction_disagreement": 0.125 + condition_index * 0.01,
            "measured_max_pixel_linf": 0.0 if condition == "clean" else 0.01,
        }
    return {
        "seed": seed,
        "dataset_scale": scale_key,
        "full_clean": {"examples": 5400, "evaluators": clean, "member_prediction_disagreement": 0.1},
        "perturbation_subset": conditions,
        "cuda_warning_observation": {
            "phase": f"fixture:{seed}:{scale_key}",
            "warning_count": 1,
            "kernel_counts": {"adaptive_avg_pool2d_backward_cuda": 1},
            "message_sha256_counts": {"0" * 64: 1},
            "unexpected_nondeterminism_warning_count": 0,
            "other_warning_count": 0,
            "other_warning_sha256_counts": {},
        },
        "aggregate_only": True,
        "authority": dict(composition.AUTHORITY),
        "resource_observation": {
            "duration_seconds": 1.0,
            "peak_gpu_allocated_bytes": 1024,
            "peak_gpu_reserved_bytes": 2048,
            "peak_host_rss_bytes": 4096,
        },
    }


def _cells(config: dict) -> list[dict]:
    rows = []
    ordinal = 0
    for seed in config["matrix"]["replicate_seeds"]:
        for scale in config["matrix"]["dataset_scales"]:
            for batch in config["matrix"]["batch_sizes"]:
                for architecture in config["matrix"]["architectures"]:
                    for hook in config["matrix"]["hook_profiles"]:
                        ordinal += 1
                        rows.append(
                            {
                                "seed": seed,
                                "dataset_scale": scale["key"],
                                "batch_size": batch,
                                "architecture": architecture["key"],
                                "hook_profile": hook["key"],
                                "duration_seconds": float(ordinal),
                                "peak_gpu_reserved_bytes": ordinal * 1024,
                                "peak_host_rss_bytes": ordinal * 2048,
                            }
                        )
    return rows


class VisionCompositionScalingTests(unittest.TestCase):
    def test_frozen_matrix_and_authority_contract(self) -> None:
        config = composition.validate_config(_config())
        self.assertEqual(
            [item["rows"] for item in config["matrix"]["dataset_scales"]],
            [5400, 10800, 21600],
        )
        self.assertEqual(
            config["matrix"]["replicate_seeds"],
            [3407, 499625614, 4288481424, 2669540432, 2937338177],
        )
        self.assertEqual(config["matrix"]["paired_factor_combinations"], 60)
        self.assertEqual(config["matrix"]["total_training_cells"], 120)
        self.assertEqual(config["resource_budget"]["wall_clock_seconds"], 43_200)
        self.assertEqual(config["resource_budget"]["peak_gpu_reserved_bytes"], 21_474_836_480)
        self.assertEqual(config["resource_budget"]["peak_host_rss_bytes"], 21_474_836_480)
        self.assertEqual(config["resource_budget"]["max_aggregate_artifact_bytes"], 21_474_836_480)
        self.assertTrue(config["matrix"]["training_scales_are_independent_fresh_model_cells"])
        self.assertTrue(config["model_output_composition"]["source_target_transfer_matrix_evaluated"])
        self.assertFalse(config["model_output_composition"]["best_singleton_contrast_used"])
        for key in (
            "assessment_input_emitted",
            "attack_battery_eligible",
            "authorization_eligible",
            "can_clear",
            "can_block",
        ):
            self.assertFalse(config[key])

    def test_config_rejects_unknown_top_level_and_any_section_mutation(self) -> None:
        candidate = copy.deepcopy(_config())
        candidate["unknown"] = True
        with self.assertRaisesRegex(ValueError, "top-level"):
            composition.validate_config(candidate)
        for section in composition.EXPECTED_SECTION_SHA256:
            with self.subTest(section=section):
                candidate = copy.deepcopy(_config())
                candidate[section]["unknown"] = True
                with self.assertRaises(ValueError):
                    composition.validate_config(candidate)

    def test_registered_nested_rosters_reproduce_from_real_corpus_paths(self) -> None:
        config = _config()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / vision.DATASET_DIRECTORY
            classes = sorted(vision.CLASS_COUNTS)
            samples = []
            for label, class_name in enumerate(classes):
                for index in range(1, vision.CLASS_COUNTS[class_name] + 1):
                    samples.append((str(root / class_name / f"{class_name}_{index}.jpg"), label))

            class FakeImageFolder:
                def __init__(self) -> None:
                    self.classes = classes
                    self.samples = samples

            train, _test, details = vision.stratified_path_split(
                samples,
                root,
                classes,
                vision.CLASS_COUNTS,
                seed=3407,
                train_fraction=0.8,
            )
            self.assertEqual(
                details["train_relative_path_set_sha256"],
                config["base_vision_protocol"]["train_roster_sha256"],
            )
            nested, observations = composition.build_nested_scale_datasets(
                vision.IndexedDataset(FakeImageFolder(), train),
                root,
                config["matrix"]["dataset_scales"],
            )
            self.assertEqual([len(nested[item["key"]]) for item in observations], [5400, 10800, 21600])
            self.assertTrue(set(nested["nested_5400"].indices).issubset(nested["nested_10800"].indices))
            self.assertTrue(set(nested["nested_10800"].indices).issubset(nested["nested_21600"].indices))

    def test_matched_pair_requires_all_preconditions(self) -> None:
        pair = composition.pair_id(3407, "alexnet", "nested_5400", 64)
        base = {
            "seed": 3407,
            "architecture": "alexnet",
            "dataset_scale": "nested_5400",
            "batch_size": 64,
            "initial_state_sha256": "1" * 64,
            "first_batch_manifest_sha256": "2" * 64,
            "first_pre_backward_loss_hex": "0x1.0p+0",
            "batch_order_sha256": "3" * 64,
            "duration_seconds": 2.0,
            "examples_per_second": 10.0,
            "peak_gpu_allocated_bytes": 100,
            "final_state_sha256": "4" * 64,
        }
        cells = [
            {**base, "hook_profile": "no_hook"},
            {
                **base,
                "hook_profile": "current_registered",
                "duration_seconds": 3.0,
                "examples_per_second": 8.0,
                "peak_gpu_allocated_bytes": 120,
            },
        ]
        result = composition.compare_pair(pair, cells, _config()["matrix"]["required_pair_matches"])
        self.assertTrue(all(result["required_exact_matches"].values()))
        cells[1]["first_pre_backward_loss_hex"] = "0x1.1p+0"
        with self.assertRaisesRegex(ValueError, "preconditions diverged"):
            composition.compare_pair(pair, cells, _config()["matrix"]["required_pair_matches"])

    def test_primary_pair_contrast_uses_singleton_mean_not_best_singleton(self) -> None:
        observed = composition.pair_minus_singleton_mean(0.6, [0.2, 0.4])
        self.assertAlmostEqual(observed, 0.3)
        self.assertNotAlmostEqual(observed, 0.2)

    def test_suite_export_has_exact_45_rows_and_finite_aggregate_contract(self) -> None:
        config = _config()
        records = [
            _composition_record(seed, scale["key"])
            for seed in config["matrix"]["replicate_seeds"]
            for scale in config["matrix"]["dataset_scales"]
        ]
        export = composition.build_suite_export(config, _cells(config), records)
        self.assertEqual(
            set(export),
            {
                "schema_version",
                "modality",
                "protected_unit_population",
                "model_keys",
                "seeds",
                "scales",
                "authority",
                "resources",
                "subset_scalars",
            },
        )
        self.assertEqual(len(export["subset_scalars"]), 45)
        self.assertEqual(export["scales"], [5400, 10800, 21600])
        self.assertEqual(
            set(export["authority"]),
            {
                "experimental_only",
                "assessment_input_emitted",
                "attack_battery_eligible",
                "authorization_eligible",
                "authorization_granted",
                "can_clear",
                "can_block",
                "requires_approved_recollection",
                "decision",
            },
        )
        singleton_rows = [item for item in export["subset_scalars"] if len(item["model_keys"]) == 1]
        pair_rows = [item for item in export["subset_scalars"] if len(item["model_keys"]) == 2]
        self.assertTrue(all(item["metrics"]["ensemble_fgsm_member_prediction_disagreement"] == 0.0 for item in singleton_rows))
        self.assertTrue(all(item["metrics"]["ensemble_fgsm_member_prediction_disagreement"] > 0.0 for item in pair_rows))
        self.assertTrue(all(item["artifact_bytes"] == 0 for item in export["resources"]))

    def test_checkpoint_round_trip_context_binding_and_incomplete_tail(self) -> None:
        config = _config()
        source = {
            "composition_config_bytes_sha256": "1" * 64,
            "composition_runner_sha256": "2" * 64,
            "base_runner_sha256": "3" * 64,
            "hook_sha256": "4" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run-1"
            context = composition.checkpoint_context(
                config,
                source,
                output.name,
                datetime(2026, 9, 2, tzinfo=timezone.utc),
                None,
            )
            output, checkpoint = composition.prepare_output_directory(
                output, config, context, resume=False
            )
            ledger = checkpoint / config["output"]["checkpoint_ledger"]
            pair = composition.pair_id(3407, "alexnet", "nested_5400", 64)
            record_id = composition.training_cell_record_id(pair, "no_hook")
            aggregate = {
                "seed": 3407,
                "architecture": "alexnet",
                "dataset_scale": "nested_5400",
                "batch_size": 64,
                "hook_profile": "no_hook",
                "raw_per_example_material_retained": False,
                "authority": dict(composition.AUTHORITY),
            }
            digest = composition.canonical_sha256(context)
            composition.append_checkpoint_record(
                ledger,
                record_type="completed_training_cell",
                record_id=record_id,
                aggregate=aggregate,
                context_sha256=digest,
            )
            records = composition.load_checkpoint_records(ledger, context_sha256=digest)
            composition.validate_resumed_records(config, records)
            self.assertEqual(records[("completed_training_cell", record_id)], aggregate)
            composition.prepare_output_directory(output, config, context, resume=True)
            changed = dict(context)
            changed["composition_runner_sha256"] = "9" * 64
            with self.assertRaisesRegex(ValueError, "does not match"):
                composition.prepare_output_directory(output, config, changed, resume=True)
            with ledger.open("ab") as stream:
                stream.write(b"{")
                stream.flush()
                os.fsync(stream.fileno())
            with self.assertRaisesRegex(ValueError, "incomplete tail"):
                composition.load_checkpoint_records(ledger, context_sha256=digest)

    def test_deadline_can_only_tighten_and_budget_breaches_fail_before_completion(self) -> None:
        config = _config()
        started = datetime(2026, 9, 2, tzinfo=timezone.utc)
        later_than_ceiling = (started + timedelta(hours=20)).isoformat()
        effective, report = composition.resolve_effective_deadline(
            started,
            config["resource_budget"]["wall_clock_seconds"],
            later_than_ceiling,
        )
        self.assertEqual(effective, started + timedelta(hours=12))
        self.assertFalse(report["supplied_deadline_tightened_local_ceiling"])
        tighter = (started + timedelta(hours=3)).isoformat()
        effective, report = composition.resolve_effective_deadline(
            started,
            config["resource_budget"]["wall_clock_seconds"],
            tighter,
        )
        self.assertEqual(effective, started + timedelta(hours=3))
        self.assertTrue(report["supplied_deadline_tightened_local_ceiling"])
        with self.assertRaisesRegex(ValueError, "timezone"):
            composition.parse_deadline_utc("2026-09-02T12:00:00")

        budget = config["resource_budget"]
        observation = composition.enforce_resource_budget(
            budget,
            started_monotonic=100.0,
            run_started_at_utc=started,
            effective_deadline_utc=started + timedelta(hours=12),
            phase="fixture",
            gpu_reserved_bytes=budget["peak_gpu_reserved_bytes"],
            host_rss_bytes=budget["peak_host_rss_bytes"],
            monotonic_now=100.0 + budget["wall_clock_seconds"],
            utc_now=started + timedelta(hours=12),
        )
        self.assertTrue(observation["within_budget"])
        for field, kwargs in (
            (
                "wall-clock",
                {
                    "gpu_reserved_bytes": 0,
                    "host_rss_bytes": 0,
                    "monotonic_now": 100.0 + budget["wall_clock_seconds"] + 0.1,
                    "utc_now": started + timedelta(hours=11),
                },
            ),
            (
                "GPU-reserved-memory",
                {
                    "gpu_reserved_bytes": budget["peak_gpu_reserved_bytes"] + 1,
                    "host_rss_bytes": 0,
                    "monotonic_now": 101.0,
                    "utc_now": started + timedelta(seconds=1),
                },
            ),
            (
                "host-RSS",
                {
                    "gpu_reserved_bytes": 0,
                    "host_rss_bytes": budget["peak_host_rss_bytes"] + 1,
                    "monotonic_now": 101.0,
                    "utc_now": started + timedelta(seconds=1),
                },
            ),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                composition.enforce_resource_budget(
                    budget,
                    started_monotonic=100.0,
                    run_started_at_utc=started,
                    effective_deadline_utc=started + timedelta(hours=12),
                    phase="fixture",
                    **kwargs,
                )

    def test_checkpoint_append_and_resume_require_exact_normalized_authority(self) -> None:
        config = _config()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "records.jsonl"
            aggregate = {
                "seed": 3407,
                "architecture": "alexnet",
                "dataset_scale": "nested_5400",
                "batch_size": 64,
                "hook_profile": "no_hook",
                "raw_per_example_material_retained": False,
                "authority": dict(composition.AUTHORITY),
            }
            composition.append_checkpoint_record(
                ledger,
                record_type="completed_training_cell",
                record_id=composition.training_cell_record_id(
                    composition.pair_id(3407, "alexnet", "nested_5400", 64),
                    "no_hook",
                ),
                aggregate=aggregate,
                context_sha256="1" * 64,
            )
            changed = copy.deepcopy(aggregate)
            changed["authority"]["can_block"] = True
            with self.assertRaisesRegex(ValueError, "authority differs"):
                composition.append_checkpoint_record(
                    ledger,
                    record_type="completed_training_cell",
                    record_id="invalid",
                    aggregate=changed,
                    context_sha256="1" * 64,
                )
            record_id = composition.training_cell_record_id(
                composition.pair_id(3407, "alexnet", "nested_5400", 64),
                "no_hook",
            )
            with self.assertRaisesRegex(ValueError, "checkpoint authority differs"):
                composition.validate_resumed_records(
                    config,
                    {("completed_training_cell", record_id): changed},
                )

    def test_publication_writes_exact_completion_last_and_failure_cannot_complete(self) -> None:
        config = _config()
        authority_keys = {
            "experimental_only",
            "assessment_input_emitted",
            "attack_battery_eligible",
            "authorization_eligible",
            "authorization_granted",
            "can_clear",
            "can_block",
            "requires_approved_recollection",
            "decision",
        }
        for fail_report in (False, True):
            with self.subTest(fail_report=fail_report), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                checkpoint = output / config["output"]["checkpoint_directory"]
                checkpoint.mkdir()
                (checkpoint / config["output"]["checkpoint_context"]).write_text("{}\n", encoding="utf-8")
                (checkpoint / config["output"]["checkpoint_ledger"]).write_text("{}\n", encoding="utf-8")
                report = {"run_id": "fixture"}
                if fail_report:
                    original = vision.atomic_write_new

                    def writer(path: Path, payload: str) -> None:
                        if path.name == config["output"]["json_report"]:
                            raise OSError("injected report failure")
                        original(path, payload)

                    with mock.patch.object(composition, "build_markdown", return_value="# fixture\n"), mock.patch.object(
                        composition.vision, "atomic_write_new", side_effect=writer
                    ):
                        with self.assertRaisesRegex(OSError, "injected"):
                            composition.publish(output, report, config)
                    self.assertFalse((output / config["output"]["completion_manifest"]).exists())
                    continue
                with mock.patch.object(composition, "build_markdown", return_value="# fixture\n"):
                    composition.publish(output, report, config)
                completion_path = output / config["output"]["completion_manifest"]
                completion = json.loads(completion_path.read_text(encoding="utf-8"))
                self.assertEqual(set(completion), {"schema_version", "status", "experiment_id", "report", "authority"})
                self.assertEqual(set(completion["authority"]), authority_keys)
                report_path = output / completion["report"]["path"]
                payload = report_path.read_bytes()
                self.assertEqual(completion["report"]["bytes"], len(payload))
                self.assertEqual(completion["report"]["sha256"], hashlib.sha256(payload).hexdigest())

    def test_aggregate_artifact_budget_is_checked_before_completion(self) -> None:
        config = copy.deepcopy(_config())
        config["resource_budget"]["max_aggregate_artifact_bytes"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            checkpoint = output / config["output"]["checkpoint_directory"]
            checkpoint.mkdir()
            (checkpoint / config["output"]["checkpoint_context"]).write_text("{}\n", encoding="utf-8")
            (checkpoint / config["output"]["checkpoint_ledger"]).write_text("{}\n", encoding="utf-8")
            with mock.patch.object(composition, "build_markdown", return_value="# fixture\n"):
                with self.assertRaisesRegex(ValueError, "artifact-byte budget"):
                    composition.publish(output, {"run_id": "fixture"}, config)
            for name in (
                config["output"]["markdown_report"],
                config["output"]["json_report"],
                config["output"]["completion_manifest"],
            ):
                self.assertFalse((output / name).exists())

    def test_registered_source_bindings_match_workspace_files(self) -> None:
        config = _config()["base_vision_protocol"]
        for logical, digest_field in (
            (config["runner_logical_name"], "runner_sha256"),
            (config["hook_logical_name"], "hook_sha256"),
        ):
            self.assertEqual(vision.sha256_file(ROOT / logical), config[digest_field])
        self.assertEqual(
            hashlib.sha256((ROOT / config["config_logical_name"]).read_bytes()).hexdigest(),
            config["config_bytes_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
