from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import IntegrityError
from model_release_assurance.models import FiniteChannelCeilingInput


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_model_backed_finite_channel as experiment  # noqa: E402


CONFIG_PATH = ROOT / "reproduction" / "model-backed-finite-channel" / "config.json"


def config() -> dict:
    return experiment.load_json_object(CONFIG_PATH)


def fake_collector(cfg: dict) -> dict:
    datasets = {
        "mnist": {
            "name": "MNIST", "openml_data_id": 554, "openml_version": 1,
            "url": "https://www.openml.org/d/554", "license": "CC BY-SA 3.0",
            "processed_snapshot_sha256": "1" * 64,
        },
        "adult": {
            "name": "Adult Census Income", "openml_data_id": 1590,
            "openml_version": 2, "url": "https://www.openml.org/d/1590",
            "license": "CC BY 4.0", "processed_snapshot_sha256": "2" * 64,
        },
        "20newsgroups": {
            "name": "20 Newsgroups", "url": "https://example.test/20newsgroups",
            "license": "test", "processed_snapshot_sha256": "3" * 64,
            "vocabulary_size": 2000,
        },
    }
    loss_pairs = {
        "cnn": (
            [0.1, 0.2, 0.4, 0.7, 0.9, 1.2, 1.8, 2.4, 3.7, 4.5, 6.0, 0.3],
            [0.2, 0.4, 0.6, 0.8, 1.1, 1.5, 2.2, 2.8, 4.2, 5.0, 7.0, 0.9],
        ),
        "xgboost": (
            [0.05, 0.15, 0.25, 0.35, 0.55, 0.8, 1.1, 1.6, 2.1, 3.0, 4.1, 5.0],
            [0.1, 0.3, 0.45, 0.65, 0.95, 1.3, 1.9, 2.5, 3.5, 4.5, 6.0, 8.0],
        ),
        "compact_transformer_llm_proxy": (
            [0.2, 0.4, 0.7, 0.9, 1.1, 1.4, 1.8, 2.2, 2.9, 3.8, 4.8, 6.5],
            [0.3, 0.6, 0.8, 1.0, 1.3, 1.7, 2.0, 2.7, 3.4, 4.1, 5.5, 7.5],
        ),
        "lstm": (
            [0.1, 0.4, 0.8, 1.2, 2.2, 4.2],
            [0.2, 0.6, 1.0, 1.8, 3.2, 5.2],
        ),
    }
    models = []
    roster = ("cnn", "lstm", "xgboost", "compact_transformer_llm_proxy")
    for index, name in enumerate(roster, start=4):
        member_pattern, nonmember_pattern = loss_pairs[name]
        pool_size = 350 if name == "compact_transformer_llm_proxy" else 400
        members = (member_pattern * (pool_size // len(member_pattern) + 1))[:pool_size]
        nonmembers = (nonmember_pattern * (pool_size // len(nonmember_pattern) + 1))[:pool_size]
        successes = pool_size
        models.append({
            "model": name,
            "ephemeral_model_artifact_sha256": str(index) * 64,
            "utility_accuracy": 0.75,
            "training_rows": 1000 if name == "compact_transformer_llm_proxy" else 1200,
            "attack": {
                "attack": "disjoint_reference_calibrated_per_example_loss_threshold",
                "threshold": 1.0,
                "member_trials": len(members),
                "nonmember_trials": len(nonmembers),
                "true_members": pool_size // 2,
                "true_nonmembers": pool_size // 2,
                "successes": successes,
                "trials": 2 * pool_size,
                "equal_prior_success": 0.5,
                "one_sided_95pct_clopper_pearson_lower": 0.45,
                "advantage_over_random": 0.0,
                "evidence_class": "floor",
                "can_block": True,
                "can_clear": False,
                "raw_scores": {
                    "target_member_losses": members,
                    "target_nonmember_losses": nonmembers,
                    "calibration_member_losses": list(members),
                    "calibration_nonmember_losses": list(nonmembers),
                },
            },
        })
    return {
        "schema_version": "1.0",
        "experiment_id": cfg["collector"]["experiment_id"],
        "orchestration": {
            "mode": "rag_planned_mcp_executable",
            "plan_id": "unit-test-plan",
            "plan_sha256": "a" * 64,
            "plan_path": "/ephemeral/unit-test-plan.json",
            "guidance": {},
        },
        "experimental_only": True,
        "evidence_semantics": "empirical_attack_floors_and_screens_never_clear",
        "seed": cfg["collector"]["seed"],
        "epochs": cfg["collector"]["epochs"],
        "datasets": datasets,
        "software": {
            "python": "test", "numpy": "test", "scipy": "test",
            "sklearn": "test", "torch": "test", "xgboost": "test",
        },
        "models": models,
        "elapsed_seconds": 1.0,
        "decision": "no_release_authorization",
    }


class ModelBackedFiniteChannelTests(unittest.TestCase):
    def test_registered_config_is_complete_and_source_bound(self) -> None:
        validated = experiment.validate_config(config(), verify_files=True)
        self.assertEqual(
            [value["collector_model"] for value in validated["models"]],
            list(experiment.EXPECTED_MODELS),
        )
        self.assertEqual(validated["collector"]["seed"], 2026090301)
        self.assertNotEqual(validated["collector"]["seed"], 20260830)
        self.assertEqual(validated["sampling"]["registered_family_count"], 6)
        self.assertFalse(validated["authority"]["authorization_eligible"])

    def test_fixed_semantic_bins_cover_edges_errors_and_nonfinite(self) -> None:
        wrapper = config()["finite_wrapper"]
        cases = (
            (-0.01, "nll_negative"),
            (0.0, "nll_0_to_0p5"),
            (0.499, "nll_0_to_0p5"),
            (0.5, "nll_0p5_to_1"),
            (1.0, "nll_1_to_2"),
            (2.0, "nll_2_to_4"),
            (4.0, "nll_4_or_more"),
            (math.inf, "nll_nonfinite"),
            (math.nan, "nll_nonfinite"),
            ("__WRAPPER_ERROR__", "wrapper_error"),
            ("__WRAPPER_TIMEOUT__", "wrapper_timeout"),
            (object(), "wrapper_error"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(experiment.classify_loss(value, wrapper), expected)

    def test_oracle_is_exact_and_erasure_contracts_advantage(self) -> None:
        counts = {
            "out": (8, 2, 0),
            "in": (2, 8, 0),
        }
        raw = experiment.exact_channel_risk(counts, erased_index=2)
        erased = experiment.exact_channel_risk(
            counts,
            erasure=Fraction(9, 10),
            erased_index=2,
        )
        self.assertEqual(raw, Fraction(4, 5))
        self.assertEqual(erased, Fraction(53, 100))
        self.assertEqual(erased - Fraction(1, 2), (raw - Fraction(1, 2)) / 10)

    def test_state_sampling_is_reproducible_independent_and_complete(self) -> None:
        counts = (2, 3, 5, 0)
        first = experiment.sample_state_counts(
            counts,
            trials=500,
            seed=123,
            erasure=Fraction(0),
            erased_index=3,
        )
        repeated = experiment.sample_state_counts(
            counts,
            trials=500,
            seed=123,
            erasure=Fraction(0),
            erased_index=3,
        )
        independent = experiment.sample_state_counts(
            counts,
            trials=500,
            seed=124,
            erasure=Fraction(0),
            erased_index=3,
        )
        erased = experiment.sample_state_counts(
            counts,
            trials=500,
            seed=125,
            erasure=Fraction(9, 10),
            erased_index=3,
        )
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, independent)
        self.assertEqual(sum(first), 500)
        self.assertEqual(sum(erased), 500)
        self.assertGreater(erased[3], 400)

    def test_executable_wrapper_replays_registered_erasure_variant(self) -> None:
        cfg = config()
        population = {
            "out": [1] + [0] * (len(experiment.EXPECTED_OBSERVATIONS) - 1),
            "in": [1] + [0] * (len(experiment.EXPECTED_OBSERVATIONS) - 1),
        }
        result = experiment.validate_closed_hidden_record_wrapper(
            cfg["finite_wrapper"],
            aggregate_population=population,
            state_independent_erasure={"numerator": 9, "denominator": 10},
        )
        self.assertTrue(result["conformant"])
        self.assertEqual(
            result["interface"]["state_independent_erasure"],
            {"numerator": 9, "denominator": 10},
        )
        self.assertEqual(
            result["erasure_probe"]["observed_erasure_count"],
            result["erasure_probe"]["expected_erasure_count"],
        )
        self.assertGreater(result["erasure_probe"]["observed_erasure_count"], 0)

    def test_compile_oracle_retains_only_aggregates(self) -> None:
        cfg = config()
        report = fake_collector(cfg)
        model_cfg = cfg["models"][0]
        model_report = next(
            value for value in report["models"]
            if value["model"] == model_cfg["collector_model"]
        )
        oracle = experiment.compile_oracle(
            model_report,
            model_cfg,
            cfg,
            report["datasets"][model_cfg["dataset_key"]],
        )
        serialized = json.dumps(oracle)
        self.assertNotIn("raw_scores", serialized)
        self.assertNotIn("target_member_losses", serialized)
        self.assertEqual(sum(oracle["state_counts"]["in"]), 400)
        self.assertEqual(sum(oracle["state_counts"]["out"]), 400)
        self.assertRegex(oracle["finite_population_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("raw_wrapper_exact_bayes_risk", oracle)

    def test_full_aggregate_only_production_and_engine_replay(self) -> None:
        cfg = copy.deepcopy(config())
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config_path = base / "config.json"
            experiment.write_json(config_path, cfg)
            output = base / "output"
            repeated = [
                {
                    "collector_model": model,
                    "model_family": next(
                        item["model_family"] for item in cfg["models"]
                        if item["collector_model"] == model
                    ),
                    "variant_id": variant,
                    "replicates": 200,
                    "trials_per_state": 5000,
                    "true_exact_oracle_risk": {"numerator": 1, "denominator": 2},
                    "undercoverage_count": 0,
                    "undercoverage_rate": 0.0,
                    "simultaneous_clopper_pearson_undercoverage_upper": 0.03,
                    "simultaneous_meta_confidence": 1.0 - 0.05 / 12,
                    "meta_simultaneous_bound_count": 12,
                    "meta_multiplicity_method": (
                        "bonferroni_across_twelve_one_sided_bounds:"
                        "six_clear_rate_lowers_and_six_undercoverage_uppers"
                    ),
                    "clear_count": 200,
                    "clear_rate": 1.0,
                    "simultaneous_clopper_pearson_clear_rate_lower": 0.97,
                    "mean_ceiling": 0.6,
                    "p95_ceiling": 0.61,
                    "mean_interval_width": 0.1,
                    "p95_interval_width": 0.11,
                    "maximum_interval_width": 0.12,
                    "mean_ceiling_excess_over_oracle": 0.1,
                    "p95_ceiling_excess_over_oracle": 0.11,
                    "maximum_ceiling_excess_over_oracle": 0.12,
                    "every_production_analyzer_replay_completed": True,
                    "retained_rows_path": "test.json",
                    "retained_rows_sha256": "b" * 64,
                }
                for model in experiment.EXPECTED_MODELS
                for variant in experiment.EXPECTED_VARIANTS
            ]
            collector = fake_collector(cfg)
            with mock.patch.object(
                experiment,
                "_run_repeated_validation",
                return_value=repeated,
            ):
                report = experiment.run_experiment(
                    cfg,
                    collector,
                    output_dir=output,
                    config_path=config_path,
                    collector_input_bytes=experiment.canonical_json_bytes(collector),
                )

            self.assertEqual(len(report["results"]), 6)
            self.assertTrue(report["checks"]["all_source_and_engine_replays_complete"])
            self.assertTrue(all(
                value["experimental_engine_verdict"] == "clear"
                for value in report["results"]
            ))
            self.assertTrue(all(
                value["production_interval"]["covers_oracle"]
                for value in report["results"]
            ))
            self.assertEqual(report["decision"], "no_release_authorization")
            self.assertTrue(report["acceptance"]["passed"])
            self.assertEqual(len(report["negative_controls"]), 4)
            self.assertTrue(all(
                value["executed"] and value["passed"]
                for value in report["negative_controls"]
            ))
            payload = json.dumps(report)
            self.assertNotIn("target_member_losses", payload)
            self.assertNotIn("calibration_member_losses", payload)
            self.assertFalse(experiment._contains_forbidden_retained_key(report))
            self.assertIn("ephemeral_model_artifact_sha256", (
                output / "finite-population-oracles.json"
            ).read_text(encoding="utf-8"))

            first = output / "cnn--raw_bins"
            submission = FiniteChannelCeilingInput.model_validate_json(
                (first / "finite-channel-submission.json").read_text(encoding="utf-8")
            )
            counts_path = first / "sampled-counts.json"
            counts_path.write_text(
                counts_path.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )
            with self.assertRaises(IntegrityError):
                AssuranceEngine._verify_finite_channel_sources(submission, first)

    def test_visibility_and_roster_mutations_fail_closed(self) -> None:
        mutations = []
        candidate = copy.deepcopy(config())
        candidate["finite_wrapper"]["candidate_record_visible"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["finite_wrapper"]["observation_ids"].remove("wrapper_timeout")
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["models"].pop()
        mutations.append(candidate)
        candidate = copy.deepcopy(config())
        candidate["sampling"]["per_model_variant_alpha"] = {
            "numerator": 1,
            "denominator": 10,
        }
        mutations.append(candidate)
        for index, candidate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(experiment.ExperimentValidationError):
                experiment.validate_config(candidate, verify_files=False)


if __name__ == "__main__":
    unittest.main()
