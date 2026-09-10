from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_llm_composition_scaling import (  # noqa: E402
    AUTHORITY,
    EXPECTED_BASELINE_CONFIG_SHA256,
    EXPECTED_BASELINE_RUNNER_SHA256,
    EXPECTED_CONFIG_CANONICAL_SHA256,
    EXPECTED_CONFIG_FILE_SHA256,
    EXPECTED_HOOK_SHA256,
    ExecutionBudget,
    MODEL_KEYS,
    MODEL_SUBSETS,
    ResourceBudgetExceeded,
    TRAINING_SEEDS,
    TRAIN_SCALES,
    _assert_aggregate_only,
    _parse_journal,
    append_journal_record,
    balanced_accuracy,
    build_subset_screens,
    calibrate_threshold,
    canonical_sha256,
    deterministic_bootstrap_interval,
    enforce_aggregate_artifact_budget,
    enforce_gpu_memory_budget,
    expected_journal_keys,
    finalize_publication,
    load_config,
    load_verified_baseline_module,
    host_peak_rss_bytes,
    release_interface_matrix,
    roc_auc,
    validate_completion_manifest,
    validate_config,
    validate_suite_export,
)


CONFIG_PATH = ROOT / "reproduction" / "composition-scaling" / "llm-config.json"


def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class LlmCompositionScalingTests(unittest.TestCase):
    def test_host_peak_memory_has_real_positive_byte_measurement(self) -> None:
        value = host_peak_rss_bytes()
        self.assertIsInstance(value, int)
        self.assertGreater(value, 0)

    def test_frozen_config_is_immutable_and_revised_baseline_is_rejected(self) -> None:
        validated, payload = load_config(CONFIG_PATH)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), EXPECTED_CONFIG_FILE_SHA256)
        self.assertEqual(canonical_sha256(validated), EXPECTED_CONFIG_CANONICAL_SHA256)
        self.assertEqual(
            hashlib.sha256((ROOT / "reproduction/llm-training-hook/config.json").read_bytes()).hexdigest(),
            EXPECTED_BASELINE_CONFIG_SHA256,
        )
        self.assertNotEqual(
            hashlib.sha256((ROOT / "scripts/run_llm_training_hook_audit.py").read_bytes()).hexdigest(),
            EXPECTED_BASELINE_RUNNER_SHA256,
        )
        # Portability changes are not retroactively part of the completed study.
        # A fresh run needs a fresh registration, never a silently updated digest.
        with mock.patch("run_llm_composition_scaling._BASELINE_MODULE", None):
            with self.assertRaisesRegex(ValueError, "baseline helper runner hash mismatch"):
                load_verified_baseline_module()
        self.assertEqual(
            hashlib.sha256((ROOT / "scripts/llm_training_hooks.py").read_bytes()).hexdigest(),
            EXPECTED_HOOK_SHA256,
        )

    def test_primary_matrix_and_secondary_trajectory_are_distinct(self) -> None:
        value = validate_config(config())
        workload = value["workload"]
        self.assertEqual(tuple(workload["training_seeds"]), TRAINING_SEEDS)
        self.assertEqual(tuple(workload["independent_train_scales"]), TRAIN_SCALES)
        self.assertEqual(workload["independent_fresh_model_cells"], 45)
        self.assertTrue(workload["fresh_model_initialization_per_model_scale_training_seed_cell"])
        self.assertFalse(workload["secondary_trajectory_is_independent_scale_evidence"])
        self.assertEqual(
            [item["exposed_rows"] for item in workload["secondary_cumulative_trajectory_checkpoints"]],
            [0, 1024, 2048, 4096, 8192],
        )
        self.assertEqual(value["composition"]["nonempty_model_subsets"], [list(item) for item in MODEL_SUBSETS])
        self.assertEqual(len(MODEL_SUBSETS), 7)
        self.assertEqual(len(TRAINING_SEEDS) * len(TRAIN_SCALES) * len(MODEL_KEYS), 45)
        resource_budget = value["resource_budget"]
        self.assertEqual(resource_budget["peak_host_rss_bytes_ceiling"], 20 * 1024**3)
        self.assertEqual(resource_budget["aggregate_artifact_bytes_ceiling"], 20 * 1024**3)
        self.assertTrue(resource_budget["check_host_rss_alongside_every_budget_and_gpu_check"])
        self.assertTrue(resource_budget["check_aggregate_artifact_bytes_before_append_and_completion"])

    def test_config_rejects_authority_scale_and_hash_drift(self) -> None:
        mutations = []
        candidate = copy.deepcopy(config())
        candidate["can_clear"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["workload"]["independent_train_scales"] = [1024, 2048, 8192]
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["composition"]["best_singleton_primary_contrast"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["resource_budget"]["peak_gpu_reserved_bytes_ceiling"] += 1
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["resource_budget"]["peak_host_rss_bytes_ceiling"] += 1
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["resource_budget"]["aggregate_artifact_bytes_ceiling"] += 1
        mutations.append(candidate)
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_config(mutation, enforce_frozen_hash=False)

        candidate = copy.deepcopy(config())
        candidate["hook_profiles"]["microbenchmark"]["rounds"] = 4
        with self.assertRaisesRegex(ValueError, "frozen canonical"):
            validate_config(candidate)

    def test_authority_vocabulary_is_normalized_and_non_authorizing(self) -> None:
        self.assertEqual(AUTHORITY, {
            "experimental_only": True,
            "assessment_input_emitted": False,
            "attack_battery_eligible": False,
            "authorization_eligible": False,
            "authorization_granted": False,
            "can_clear": False,
            "can_block": False,
            "requires_approved_recollection": True,
            "decision": "no_release_authorization",
        })
        value = config()
        for key in (
            "assessment_input_emitted",
            "attack_battery_eligible",
            "authorization_eligible",
            "can_clear",
            "can_block",
        ):
            self.assertFalse(value[key])
        self.assertTrue(value["requires_approved_recollection"])

    def test_auc_threshold_and_ties_are_deterministic(self) -> None:
        self.assertEqual(roc_auc([1.0, 1.0], [1.0, 1.0]), 0.5)
        self.assertEqual(roc_auc([2.0, 3.0], [0.0, 1.0]), 1.0)
        threshold = calibrate_threshold([2.0, 3.0], [0.0, 1.0])
        self.assertEqual(balanced_accuracy([2.0, 3.0], [0.0, 1.0], threshold), 1.0)
        self.assertTrue(math.isfinite(threshold))
        self.assertEqual(calibrate_threshold([0.0, 0.0], [0.0, 0.0]), 1.0)

    def test_stratified_bootstrap_is_reproducible_and_bounded(self) -> None:
        kwargs = {
            "threshold": 0.5,
            "replicates": 100,
            "confidence_level": 0.95,
            "seed": 123456,
        }
        first = deterministic_bootstrap_interval([0.7, 0.8, 0.9], [0.1, 0.2, 0.3], **kwargs)
        second = deterministic_bootstrap_interval([0.7, 0.8, 0.9], [0.1, 0.2, 0.3], **kwargs)
        self.assertEqual(first, second)
        for interval in first["intervals"].values():
            self.assertLessEqual(interval["lower"], interval["upper"])
            self.assertGreaterEqual(interval["lower"], -1.0)
            self.assertLessEqual(interval["upper"], 1.0)

    def test_all_subset_screens_are_aggregate_only_and_use_member_singleton_mean(self) -> None:
        members = [f"m-{index}" for index in range(8)]
        nonmembers = [f"n-{index}" for index in range(8)]
        losses = {
            "distilgpt2": {
                **{key: 0.5 + index * 0.01 for index, key in enumerate(members)},
                **{key: 1.5 + index * 0.01 for index, key in enumerate(nonmembers)},
            },
            "meta-opt-125m": {
                **{key: 0.7 + index * 0.02 for index, key in enumerate(members)},
                **{key: 1.3 + index * 0.02 for index, key in enumerate(nonmembers)},
            },
            "pythia-160m": {
                **{key: 0.6 + index * 0.015 for index, key in enumerate(members)},
                **{key: 1.4 + index * 0.015 for index, key in enumerate(nonmembers)},
            },
        }
        kwargs = {
            "partition_seeds": [11, 17, 23],
            "calibration_per_class": 2,
            "audit_per_class": 2,
            "bootstrap_replicates": 100,
            "confidence_level": 0.95,
            "checkpoint_steps": 64,
        }
        first = build_subset_screens(losses, members, nonmembers, **kwargs)
        second = build_subset_screens(losses, members, nonmembers, **kwargs)
        self.assertEqual(first, second)
        self.assertEqual(len(first["partition_results"]), 3)
        for partition in first["partition_results"]:
            self.assertEqual(len(partition["subsets"]), 7)
            singles = {
                item["model_keys"][0]: item
                for item in partition["subsets"]
                if item["subset_size"] == 1
            }
            pair = next(item for item in partition["subsets"] if item["model_keys"] == ["distilgpt2", "meta-opt-125m"])
            expected = pair["metrics"]["roc_auc"] - (
                singles["distilgpt2"]["metrics"]["roc_auc"]
                + singles["meta-opt-125m"]["metrics"]["roc_auc"]
            ) / 2.0
            self.assertAlmostEqual(
                pair["primary_contrast_vs_mean_member_singletons"]["roc_auc"],
                expected,
            )
            for item in partition["subsets"]:
                self.assertEqual(item["decision"], "no_release_authorization")
                self.assertFalse(item["assessment_input_emitted"])
                self.assertFalse(item["attack_battery_eligible"])
                self.assertFalse(item["can_clear"])
                self.assertFalse(item["can_block"])
        _assert_aggregate_only(first)
        serialized = json.dumps(first)
        for prohibited in members + nonmembers:
            self.assertNotIn(prohibited, serialized)

    def test_release_interface_realizability_is_exact(self) -> None:
        matrix = {item["key"]: item for item in release_interface_matrix(config())}
        self.assertEqual(matrix["text_only_generation"]["realizable_model_loss_subsets"], [])
        self.assertEqual(matrix["generated_token_log_probabilities_only"]["realizable_model_loss_subsets"], [])
        self.assertEqual(len(matrix["candidate_scorers_all_three"]["realizable_model_loss_subsets"]), 7)
        self.assertEqual(len(matrix["white_box_all_three"]["realizable_model_loss_subsets"]), 7)
        roster = matrix["protected_data_package_with_exact_roster"]
        self.assertTrue(roster["exact_protected_roster_direct_disclosure"])
        self.assertEqual(roster["hypothetical_membership_gate"], "BLOCKED_AND_REDESIGN_REQUIRED")
        self.assertFalse(roster["can_block"])
        self.assertFalse(roster["assessment_input_emitted"])

    def test_hash_chained_journal_resumes_exact_prefix_and_repairs_partial_tail(self) -> None:
        context_sha256 = "a" * 64
        payload = {
            "resource": {"wall_clock_seconds": 1.25},
            "aggregate_only": True,
            **AUTHORITY,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "COMPLETED_CELLS.jsonl"
            records = []
            append_journal_record(
                path,
                records,
                context_sha256=context_sha256,
                record_type="hook_microbenchmark_bundle",
                record_key="hook-microbenchmark-bundle",
                payload=payload,
                artifact_bytes_ceiling=20 * 1024**3,
            )
            if os.name != "nt":
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            parsed = _parse_journal(path, context_sha256=context_sha256, repair_trailing_partial=False)
            self.assertEqual(parsed, records)
            clean_size = path.stat().st_size
            with path.open("ab") as stream:
                stream.write(b'{"incomplete"')
            repaired = _parse_journal(path, context_sha256=context_sha256, repair_trailing_partial=True)
            self.assertEqual(repaired, records)
            self.assertEqual(path.stat().st_size, clean_size)
            with self.assertRaisesRegex(ValueError, "context mismatch"):
                _parse_journal(path, context_sha256="b" * 64, repair_trailing_partial=False)

    def test_journal_schedule_has_one_preflight_and_fifteen_bundles(self) -> None:
        keys = expected_journal_keys()
        self.assertEqual(len(keys), 16)
        self.assertEqual(keys[0], "hook-microbenchmark-bundle")
        self.assertEqual(keys[1], f"scale-2048-seed-{TRAINING_SEEDS[0]}")
        self.assertEqual(keys[-1], f"scale-8192-seed-{TRAINING_SEEDS[-1]}")

    def test_host_rss_is_enforced_by_wall_and_gpu_budget_checks(self) -> None:
        value = config()
        ceiling = value["resource_budget"]["peak_host_rss_bytes_ceiling"]
        with mock.patch(
            "run_llm_composition_scaling.host_peak_rss_bytes",
            return_value=ceiling + 1,
        ):
            budget = ExecutionBudget(
                value,
                previously_consumed_seconds=0.0,
                deadline_utc=None,
            )
            with self.assertRaisesRegex(ResourceBudgetExceeded, "host RSS"):
                budget.check()
            with self.assertRaisesRegex(ResourceBudgetExceeded, "host RSS"):
                enforce_gpu_memory_budget(
                    {
                        "allocated_bytes": 0,
                        "reserved_bytes": 0,
                        "peak_allocated_bytes": 0,
                        "peak_reserved_bytes": 0,
                    },
                    value,
                )

    def test_aggregate_artifact_budget_blocks_journal_append_and_completion_sizes(self) -> None:
        self.assertEqual(enforce_aggregate_artifact_budget([10, 20], 30), 30)
        with self.assertRaisesRegex(ResourceBudgetExceeded, "artifact byte ceiling"):
            enforce_aggregate_artifact_budget([10, 21], 30)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "COMPLETED_CELLS.jsonl"
            with self.assertRaisesRegex(ResourceBudgetExceeded, "artifact byte ceiling"):
                append_journal_record(
                    path,
                    [],
                    context_sha256="a" * 64,
                    record_type="hook_microbenchmark_bundle",
                    record_key="hook-microbenchmark-bundle",
                    payload={
                        "resource": {"wall_clock_seconds": 1.0},
                        **AUTHORITY,
                    },
                    artifact_bytes_ceiling=32,
                )
            self.assertFalse(path.exists())

    def test_final_resource_breach_after_reports_leaves_completion_absent(self) -> None:
        class MinimalBaseline:
            @staticmethod
            def _atomic_write_bytes(path: Path, payload: bytes) -> None:
                with path.open("xb") as stream:
                    stream.write(payload)
                os.chmod(path, 0o600)

            @staticmethod
            def verify_registered_artifact_entries(*_args, **_kwargs) -> None:
                raise AssertionError("verification must not run after the forced resource breach")

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            journal = output_dir / config()["output"]["checkpoint_journal"]
            journal.write_bytes(b"{}\n")
            with (
                mock.patch(
                    "run_llm_composition_scaling.assemble_report",
                    return_value={"aggregate_only": True, "authority": dict(AUTHORITY)},
                ),
                mock.patch(
                    "run_llm_composition_scaling.build_markdown_report",
                    return_value="# aggregate report\n",
                ),
                mock.patch(
                    "run_llm_composition_scaling.enforce_host_rss_budget",
                    side_effect=[1, ResourceBudgetExceeded("forced host RSS breach")],
                ),
            ):
                with self.assertRaisesRegex(ResourceBudgetExceeded, "forced host RSS breach"):
                    finalize_publication(
                        MinimalBaseline(),
                        config(),
                        {},
                        {},
                        [],
                        output_dir,
                    )
            output = config()["output"]
            self.assertTrue((output_dir / output["json_report"]).is_file())
            self.assertTrue((output_dir / output["markdown_report"]).is_file())
            self.assertFalse((output_dir / output["completion_manifest"]).exists())

    def test_final_artifact_breach_after_reports_leaves_completion_absent(self) -> None:
        class MinimalBaseline:
            @staticmethod
            def _atomic_write_bytes(path: Path, payload: bytes) -> None:
                with path.open("xb") as stream:
                    stream.write(payload)
                os.chmod(path, 0o600)

            @staticmethod
            def verify_registered_artifact_entries(*_args, **_kwargs) -> None:
                raise AssertionError("verification must not run after the forced artifact breach")

        value = config()
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            (output_dir / value["output"]["checkpoint_journal"]).write_bytes(b"{}\n")
            with (
                mock.patch(
                    "run_llm_composition_scaling.assemble_report",
                    return_value={"aggregate_only": True, "authority": dict(AUTHORITY)},
                ),
                mock.patch(
                    "run_llm_composition_scaling.build_markdown_report",
                    return_value="# aggregate report\n",
                ),
                mock.patch(
                    "run_llm_composition_scaling.enforce_host_rss_budget",
                    return_value=1,
                ),
                mock.patch(
                    "run_llm_composition_scaling.enforce_aggregate_artifact_budget",
                    side_effect=[1, ResourceBudgetExceeded("forced artifact byte breach")],
                ),
            ):
                with self.assertRaisesRegex(ResourceBudgetExceeded, "forced artifact byte breach"):
                    finalize_publication(
                        MinimalBaseline(), value, {}, {}, [], output_dir
                    )
            self.assertTrue((output_dir / value["output"]["json_report"]).is_file())
            self.assertTrue((output_dir / value["output"]["markdown_report"]).is_file())
            self.assertFalse((output_dir / value["output"]["completion_manifest"]).exists())

    def test_completion_manifest_has_exact_shared_shape(self) -> None:
        manifest = {
            "schema_version": "1.0",
            "status": "complete",
            "experiment_id": "llm-composition-scaling-wildchat-three-model-v1",
            "report": {
                "path": "llm-composition-scaling-report.json",
                "sha256": "c" * 64,
                "bytes": 123,
            },
            "authority": dict(AUTHORITY),
        }
        self.assertEqual(validate_completion_manifest(manifest), manifest)
        mutation = copy.deepcopy(manifest)
        mutation["authority"]["can_clear"] = True
        with self.assertRaisesRegex(ValueError, "authority mismatch"):
            validate_completion_manifest(mutation)
        mutation = copy.deepcopy(manifest)
        mutation["extra"] = True
        with self.assertRaisesRegex(ValueError, "closure mismatch"):
            validate_completion_manifest(mutation)

    def test_suite_export_has_exact_105_row_scalar_contract(self) -> None:
        metric_names = (
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
        export = {
            "schema_version": "1.0",
            "modality": "llm",
            "protected_unit_population": "wildchat_training_record",
            "model_keys": list(MODEL_KEYS),
            "seeds": list(TRAINING_SEEDS),
            "scales": list(TRAIN_SCALES),
            "authority": dict(AUTHORITY),
            "resources": [
                {
                    "model_key": model_key,
                    "wall_clock_seconds": 1.0,
                    "peak_gpu_reserved_bytes": 2,
                    "peak_host_rss_bytes": 3,
                    "artifact_bytes": 4,
                }
                for model_key in MODEL_KEYS
            ],
            "subset_scalars": [
                {
                    "model_keys": list(model_subset),
                    "scale": scale,
                    "seed": seed,
                    "metrics": {key: 0.0 for key in metric_names},
                }
                for scale in TRAIN_SCALES
                for seed in TRAINING_SEEDS
                for model_subset in MODEL_SUBSETS
            ],
        }
        self.assertEqual(validate_suite_export(export), export)
        self.assertEqual(len(export["subset_scalars"]), 105)
        mutation = copy.deepcopy(export)
        mutation["subset_scalars"].pop()
        with self.assertRaisesRegex(ValueError, "closure mismatch"):
            validate_suite_export(mutation)

    def test_durable_privacy_guard_rejects_examples_and_absolute_paths(self) -> None:
        _assert_aggregate_only({"aggregate": {"count": 3, "sha256": "d" * 64}})
        for value in (
            {"record_ids": ["secret"]},
            {"per_example": [0.1]},
            {"artifact": "/home/" + "ubuntu/private.json"},
            {"artifact": "/Users/example/private.json"},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _assert_aggregate_only(value)


if __name__ == "__main__":
    unittest.main()
