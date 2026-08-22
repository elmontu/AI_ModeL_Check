from __future__ import annotations

import copy
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_openml_structural import canonical_json, sha256_bytes, sha256_file
from run_xgboost_audit import (
    evaluate_membership_scores,
    load_config,
    positive_predictive_value,
    run_experiment,
    runtime_versions,
    simultaneous_bound_confidence,
    validate_config,
    xgboost_parameters,
    zero_false_positive_minimum_trials,
)


class XGBoostAuditRunnerTests(unittest.TestCase):
    def test_membership_statistics_are_familywise_and_prior_aware(self) -> None:
        self.assertAlmostEqual(simultaneous_bound_confidence(0.95, 2), 0.9875)
        self.assertAlmostEqual(positive_predictive_value(0.8, 0.1, 0.5), 8.0 / 9.0)
        self.assertIsNone(positive_predictive_value(0.0, 0.0, 0.5))
        self.assertLess(
            positive_predictive_value(0.8, 0.1, 0.01),
            positive_predictive_value(0.8, 0.1, 0.5),
        )
        minimum = zero_false_positive_minimum_trials(0.01, 0.975)
        self.assertGreaterEqual(minimum, 367)

        def score_frame(
            nonmember_audit_count: int,
            *,
            member_score: float = 1.0,
        ) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    *(
                        {
                            "group": "nonmember_calibration",
                            "membership_score": 0.0,
                            "target_loss": 0.5,
                            "reference_loss": 0.5,
                            "true_class": index % 2,
                            "is_member": False,
                        }
                        for index in range(100)
                    ),
                    *(
                        {
                            "group": "nonmember_audit",
                            "membership_score": 0.0,
                            "target_loss": 0.5,
                            "reference_loss": 0.5,
                            "true_class": index % 2,
                            "is_member": False,
                        }
                        for index in range(nonmember_audit_count)
                    ),
                    *(
                        {
                            "group": "member_audit",
                            "membership_score": member_score,
                            "target_loss": 0.0,
                            "reference_loss": member_score,
                            "true_class": index % 2,
                            "is_member": True,
                        }
                        for index in range(100)
                    ),
                ]
            )

        unsupported = evaluate_membership_scores(
            score_frame(100),
            target_fpr=0.01,
            confidence_family=0.95,
            registered_comparisons=1,
            membership_priors=[0.5, 0.01],
        )
        self.assertFalse(unsupported["operating_point_attained"])
        self.assertEqual(unsupported["evidence_class"], "screen")
        self.assertIsNone(unsupported["certified_tpr_floor_at_controlled_fpr"])

        supported = evaluate_membership_scores(
            score_frame(1000),
            target_fpr=0.01,
            confidence_family=0.95,
            registered_comparisons=1,
            membership_priors=[0.5, 0.01],
        )
        self.assertTrue(supported["operating_point_attained"])
        self.assertEqual(supported["evidence_class"], "floor")
        self.assertGreater(supported["certified_tpr_floor_at_controlled_fpr"], 0.0)
        self.assertGreater(
            supported["simultaneous_membership_advantage_lower_bound"],
            0.0,
        )

        no_positives = evaluate_membership_scores(
            score_frame(1000, member_score=0.0),
            target_fpr=0.01,
            confidence_family=0.95,
            registered_comparisons=1,
            membership_priors=[0.5],
        )
        self.assertIsNone(no_positives["deployment_prior_ppv"][0]["estimate"])
        self.assertEqual(
            no_positives["deployment_prior_ppv"][0]["estimate_status"],
            "undefined_no_positive_predictions",
        )

        malformed = score_frame(1000)
        malformed.loc[0, "membership_score"] = np.inf
        with self.assertRaisesRegex(ValueError, "finite"):
            evaluate_membership_scores(
                malformed,
                target_fpr=0.01,
                confidence_family=0.95,
                registered_comparisons=1,
                membership_priors=[0.5],
            )
        malformed = score_frame(1000)
        malformed.loc[malformed["group"] == "member_audit", "is_member"] = False
        with self.assertRaisesRegex(ValueError, "disagree"):
            evaluate_membership_scores(
                malformed,
                target_fpr=0.01,
                confidence_family=0.95,
                registered_comparisons=1,
                membership_priors=[0.5],
            )
        malformed = score_frame(1000)
        malformed["true_class"] = malformed["true_class"].astype(float)
        malformed.loc[0, "true_class"] = 0.5
        with self.assertRaisesRegex(ValueError, "nonnegative integers"):
            evaluate_membership_scores(
                malformed,
                target_fpr=0.01,
                confidence_family=0.95,
                registered_comparisons=1,
                membership_priors=[0.5],
            )

    def test_runtime_binding_does_not_expose_xgboost_library_path(self) -> None:
        runtime = runtime_versions()
        library = runtime["xgboost_build"].get("libxgboost")
        self.assertIsNotNone(library)
        self.assertEqual(set(library), {"name", "sha256", "binding_status"})
        self.assertEqual(library["binding_status"], "complete")
        self.assertEqual(library["name"], Path(library["name"]).name)
        self.assertNotIn("/", library["name"])
        self.assertNotIn("\\", library["name"])
        self.assertRegex(library["sha256"], r"^[0-9a-f]{64}$")
        with patch("run_xgboost_audit.xgboost.build_info", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "did not report"):
                runtime_versions()
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_library = Path(temp_dir) / "missing-libxgboost.dll"
            with patch(
                "run_xgboost_audit.xgboost.build_info",
                return_value={"libxgboost": str(missing_library)},
            ):
                with self.assertRaisesRegex(RuntimeError, "cannot be hash-bound"):
                    runtime_versions()

    def test_binary_and_multiclass_objectives_are_controlled(self) -> None:
        binary = xgboost_parameters({}, class_count=2, seed=7)
        multiclass = xgboost_parameters({}, class_count=4, seed=8)
        self.assertEqual(binary["objective"], "binary:logistic")
        self.assertEqual(binary["eval_metric"], "logloss")
        self.assertNotIn("num_class", binary)
        self.assertEqual(multiclass["objective"], "multi:softprob")
        self.assertEqual(multiclass["eval_metric"], "mlogloss")
        self.assertEqual(multiclass["num_class"], 4)
        self.assertEqual(binary["device"], "cpu")
        self.assertEqual(binary["n_jobs"], 1)

    def test_unknown_or_controlled_model_parameter_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown or controlled"):
            xgboost_parameters({"objective": "binary:hinge"}, class_count=2, seed=1)
        with self.assertRaisesRegex(ValueError, "subsample"):
            xgboost_parameters({"subsample": 0.0}, class_count=2, seed=1)

    def test_multiclass_ubj_round_trip_preserves_predictions(self) -> None:
        rng = np.random.default_rng(91)
        features = rng.normal(size=(360, 4))
        scores = np.column_stack(
            [
                features[:, 0] - features[:, 1],
                features[:, 1] + 0.5 * features[:, 2],
                -features[:, 0] - features[:, 2],
            ]
        )
        target = np.argmax(scores, axis=1)
        parameters = xgboost_parameters(
            {"n_estimators": 8, "max_depth": 3},
            class_count=3,
            seed=13,
        )
        model = XGBClassifier(**parameters).fit(features, target)
        before = model.predict_proba(features)
        with tempfile.TemporaryDirectory() as directory_name:
            model_path = Path(directory_name) / "multiclass.ubj"
            model.save_model(model_path)
            reloaded = XGBClassifier()
            reloaded.load_model(model_path)
            np.testing.assert_allclose(
                reloaded.predict_proba(features),
                before,
                rtol=0.0,
                atol=0.0,
            )

    def test_end_to_end_artifacts_attack_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            rng = np.random.default_rng(20260822)
            rows = 600
            numeric_a = rng.normal(size=rows)
            numeric_b = rng.normal(size=rows)
            category = rng.choice(["north", "south", "east"], size=rows)
            signal = numeric_a + 0.5 * numeric_b + (category == "north") * 0.8
            target = np.where(signal + rng.normal(scale=0.5, size=rows) > 0.2, "yes", "no")
            frame = pd.DataFrame(
                {
                    "numeric_a": numeric_a,
                    "numeric_b": numeric_b,
                    "category": category,
                    "target": target,
                }
            )
            frame.loc[::29, "numeric_a"] = np.nan
            frame.loc[::31, "category"] = None
            dataset_path = directory / "classification.csv"
            frame.to_csv(dataset_path, index=False, lineterminator="\n")
            config = {
                "schema_version": "1.1",
                "experiment_id": "synthetic-xgboost-test",
                "dataset": {
                    "path": dataset_path.name,
                    "sha256": sha256_file(dataset_path),
                    "target_column": "target",
                },
                "master_seed": 101,
                "replicate_seeds": [11],
                "row_cap": rows,
                "split_fractions": {
                    "target_train": 0.5,
                    "reference_train": 0.2,
                    "attack_calibration": 0.1,
                    "attack_audit_nonmember": 0.1,
                    "utility_test": 0.1,
                },
                "model": {
                    "n_estimators": 12,
                    "max_depth": 3,
                    "learning_rate": 0.1,
                },
                "attack": {
                    "target_fpr": 0.2,
                    "confidence": 0.95,
                    "membership_priors": [0.5, 0.1, 0.01],
                },
                "decision_game": {
                    "game_id": "synthetic-membership-game",
                    "threat_contract_sha256": "a" * 64,
                    "population_scope_id": "synthetic-records",
                    "protected_unit": "record",
                    "attacker_observation": "class_probabilities_and_true_label",
                    "true_label_known": True,
                    "candidate_population": "rows selected by deterministic row-cap stratified sampling from the hash-bound dataset",
                    "candidate_sampling": "target members, calibration nonmembers, and audit nonmembers from deterministic stratified disjoint five-way splits",
                    "reference_data_relationship": "disjoint same-dataset reference training split equalized in size with target training",
                    "model_knowledge": "xgboost_family_and_registered_hyperparameters",
                    "threshold_selection": "nonmember_calibration_only_fixed_target_fpr",
                    "recipient_access": "full_artifact",
                    "query_budget": None,
                },
            }
            placeholder = copy.deepcopy(config)
            placeholder["decision_game"]["threat_contract_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "placeholder digest"):
                validate_config(placeholder)
            placeholder = copy.deepcopy(config)
            placeholder["decision_game"]["game_id"] = "replace-game"
            with self.assertRaisesRegex(ValueError, "replace-\\* placeholder"):
                validate_config(placeholder)
            weakened = copy.deepcopy(config)
            weakened["decision_game"]["candidate_sampling"] = "claimant-selected sampling"
            with self.assertRaisesRegex(ValueError, "candidate_sampling"):
                validate_config(weakened)
            config_path = directory / "config.json"
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            output_dir = directory / "output"

            summary = run_experiment(config_path, output_dir)
            self.assertEqual(summary["completed_runs"], 1)
            run_dir = output_dir / "seed-11"
            manifest_path = run_dir / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["model_family"], "xgboost.XGBClassifier")
            self.assertEqual(manifest["target_model_parameters"]["n_estimators"], 12)
            self.assertEqual(
                manifest["target_structural"]["records"],
                manifest["group_counts"]["member_audit"],
            )
            self.assertEqual(
                manifest["attack"]["true_positives"]
                + manifest["attack"]["false_negatives"],
                manifest["group_counts"]["member_audit"],
            )
            self.assertEqual(
                manifest["attack"]["false_positives"]
                + manifest["attack"]["true_negatives"],
                manifest["group_counts"]["nonmember_audit"],
            )
            self.assertAlmostEqual(manifest["attack"]["per_bound_confidence"], 0.975)
            self.assertEqual(
                manifest["attack"]["multiplicity"]["simultaneous_bound_count"],
                2,
            )
            self.assertEqual(len(manifest["attack"]["deployment_prior_ppv"]), 3)
            for result in manifest["attack"]["deployment_prior_ppv"]:
                if result["estimate"] is not None:
                    self.assertLessEqual(result["simultaneous_lower_bound"], result["estimate"])
            self.assertFalse(manifest["attack"]["can_clear"])
            self.assertIn(manifest["attack"]["evidence_class"], {"floor", "screen"})
            self.assertGreaterEqual(manifest["utility"]["balanced_accuracy"], 0.5)

            for record in manifest["artifacts"].values():
                artifact_path = run_dir / record["path"]
                self.assertTrue(artifact_path.is_file())
                self.assertEqual(sha256_file(artifact_path), record["sha256"])

            release_manifest_path = run_dir / "release-artifact.json"
            release = json.loads(release_manifest_path.read_text(encoding="utf-8"))
            for private_field in ("training", "implementation", "runtime", "dataset_sha256", "config_sha256"):
                self.assertNotIn(private_field, release)
            self.assertEqual(release["model"]["sha256"], manifest["artifacts"]["target_model"]["sha256"])
            self.assertEqual(
                release["preprocessing"]["sha256"],
                manifest["artifacts"]["target_preprocessing"]["sha256"],
            )
            pipeline = joblib.load(run_dir / release["preprocessing"]["path"])
            self.assertIn("preprocessor", pipeline)
            reloaded = XGBClassifier()
            reloaded.load_model(run_dir / release["model"]["path"])
            self.assertEqual(reloaded.get_booster().num_boosted_rounds(), 12)
            bundle_path = run_dir / manifest["artifacts"]["release_bundle"]["path"]
            self.assertEqual(
                manifest["release_binding"]["release_artifact_sha256"],
                sha256_file(bundle_path),
            )
            with zipfile.ZipFile(bundle_path) as bundle:
                self.assertEqual(
                    bundle.namelist(),
                    [
                        "release-artifact.json",
                        "target-model.ubj",
                        "target-preprocessing.joblib",
                    ],
                )
                self.assertEqual(
                    bundle.read("release-artifact.json"),
                    release_manifest_path.read_bytes(),
                )
                self.assertEqual(
                    bundle.read("target-model.ubj"),
                    (run_dir / release["model"]["path"]).read_bytes(),
                )
                self.assertEqual(
                    bundle.read("target-preprocessing.joblib"),
                    (run_dir / release["preprocessing"]["path"]).read_bytes(),
                )

            with gzip.open(run_dir / manifest["artifacts"]["splits"]["path"], "rt") as handle:
                retained_splits = json.load(handle)
            selected_ids = set(retained_splits["selected_row_ids"])
            split_sets = {
                name: set(row_ids) for name, row_ids in retained_splits["splits"].items()
            }
            self.assertEqual(set().union(*split_sets.values()), selected_ids)
            self.assertEqual(sum(len(values) for values in split_sets.values()), len(selected_ids))
            target_training = set(retained_splits["target_training_row_ids"])
            reference_training = set(retained_splits["reference_training_row_ids"])
            self.assertTrue(target_training.isdisjoint(reference_training))
            self.assertEqual(len(target_training), len(reference_training))
            self.assertEqual(target_training, set(retained_splits["member_audit_row_ids"]))
            self.assertTrue(target_training.isdisjoint(split_sets["utility_test"]))
            self.assertTrue(reference_training.isdisjoint(split_sets["utility_test"]))

            raw_scores = pd.read_parquet(run_dir / manifest["artifacts"]["raw_scores"]["path"])
            np.testing.assert_allclose(
                raw_scores["membership_score"],
                raw_scores["reference_loss"] - raw_scores["target_loss"],
                rtol=0.0,
                atol=1e-12,
            )

            original_bundle_sha256 = sha256_file(bundle_path)
            run_experiment(config_path, output_dir, force=True)
            forced_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                sha256_file(run_dir / forced_manifest["artifacts"]["release_bundle"]["path"]),
                original_bundle_sha256,
            )

            manifest_mtime = manifest_path.stat().st_mtime_ns
            cached = run_experiment(config_path, output_dir)
            self.assertEqual(cached["completed_runs"], 1)
            self.assertEqual(manifest_path.stat().st_mtime_ns, manifest_mtime)

            tampered_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            original_tpr = tampered_manifest["attack"]["tpr"]
            tampered_manifest["attack"]["tpr"] = 1.0 - original_tpr
            manifest_path.write_text(
                json.dumps(tampered_manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            run_experiment(config_path, output_dir)
            repaired_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired_manifest["attack"]["tpr"], original_tpr)

            tampered_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tampered_manifest["target_model_parameters"]["n_estimators"] = 999
            tampered_manifest["protected_unit"] = "claimant-selected-unit"
            manifest_path.write_text(
                json.dumps(tampered_manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            run_experiment(config_path, output_dir)
            repaired_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired_manifest["target_model_parameters"]["n_estimators"], 12)
            self.assertEqual(repaired_manifest["protected_unit"], "record")

            tampered_model = run_dir / manifest["artifacts"]["target_model"]["path"]
            tampered_model.write_bytes(tampered_model.read_bytes() + b"tamper")
            run_experiment(config_path, output_dir)
            repaired = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                sha256_file(tampered_model), repaired["artifacts"]["target_model"]["sha256"]
            )

            crlf_path = directory / "config-crlf.json"
            crlf_path.write_bytes((json.dumps(config, indent=2) + "\n").replace("\n", "\r\n").encode())
            self.assertEqual(
                sha256_bytes(canonical_json(load_config(config_path))),
                sha256_bytes(canonical_json(load_config(crlf_path))),
            )
            reordered = copy.deepcopy(config)
            reordered["split_fractions"] = dict(
                reversed(list(reordered["split_fractions"].items()))
            )
            reordered_path = directory / "config-reordered.json"
            reordered_path.write_text(json.dumps(reordered), encoding="utf-8")
            self.assertEqual(
                list(load_config(reordered_path)["split_fractions"]),
                [
                    "target_train",
                    "reference_train",
                    "attack_calibration",
                    "attack_audit_nonmember",
                    "utility_test",
                ],
            )
            self.assertEqual(
                sha256_bytes(canonical_json(load_config(config_path))),
                sha256_bytes(canonical_json(load_config(reordered_path))),
            )
            cached_manifest_mtime = manifest_path.stat().st_mtime_ns
            run_experiment(reordered_path, output_dir)
            self.assertEqual(manifest_path.stat().st_mtime_ns, cached_manifest_mtime)

            cli_output = directory / "cli-output"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_xgboost_audit.py"),
                    "--config",
                    str(config_path),
                    "--output-dir",
                    str(cli_output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            cli_summary = json.loads(
                (cli_output / "xgboost-audit-summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cli_summary["completed_runs"], 1)

            wrong = copy.deepcopy(config)
            wrong["dataset"]["sha256"] = "0" * 64
            wrong_path = directory / "wrong-config.json"
            wrong_path.write_text(json.dumps(wrong), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dataset hash mismatch"):
                run_experiment(wrong_path, directory / "wrong-output")


if __name__ == "__main__":
    unittest.main()
