from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_composition_scaling_suite as suite  # noqa: E402


CONFIG_PATH = ROOT / "reproduction" / "composition-scaling" / "suite-config.json"


def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def child_export(modality: str) -> dict:
    if modality == "llm":
        models = suite.LLM_MODEL_KEYS
        subsets = suite.LLM_SUBSETS
        metrics = suite.LLM_METRICS
    else:
        models = suite.VISION_MODEL_KEYS
        subsets = suite.VISION_SUBSETS
        metrics = suite.VISION_METRICS
    rows = []
    for subset in subsets:
        for scale in suite.SCALES[modality]:
            for seed in suite.SEEDS:
                values = {}
                for name in metrics:
                    if name == "clean_mean_cross_entropy":
                        values[name] = 1.25
                    elif name.endswith("_change") or name.endswith("_singletons"):
                        values[name] = 0.01
                    else:
                        values[name] = 0.55
                rows.append(
                    {
                        "model_keys": list(subset),
                        "scale": scale,
                        "seed": seed,
                        "metrics": values,
                    }
                )
    return {
        "schema_version": "1.0",
        "modality": modality,
        "protected_unit_population": suite.PROTECTED_UNIT_POPULATIONS[modality],
        "model_keys": list(models),
        "seeds": list(suite.SEEDS),
        "scales": list(suite.SCALES[modality]),
        "authority": dict(suite.AUTHORITY),
        "resources": [
            {
                "model_key": model,
                "wall_clock_seconds": 10.0,
                "peak_gpu_reserved_bytes": 1024,
                "peak_host_rss_bytes": 2048,
                "artifact_bytes": 4096,
            }
            for model in models
        ],
        "subset_scalars": rows,
    }


def child_output(directory: Path, modality: str, cfg: dict) -> dict:
    binding = cfg["source_bindings"]["children"][modality]
    report = {
        "schema_version": "child-specific",
        "suite_export": child_export(modality),
    }
    payload = json.dumps(report, allow_nan=False, sort_keys=True).encode("utf-8") + b"\n"
    report_path = directory / binding["report_basename"]
    report_path.write_bytes(payload)
    manifest = {
        "schema_version": "1.0",
        "status": "complete",
        "experiment_id": binding["experiment_id"],
        "report": {
            "path": report_path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        },
        "authority": dict(suite.AUTHORITY),
    }
    (directory / "RUN_COMPLETE.json").write_text(
        json.dumps(manifest, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


class CompositionScalingSuiteTests(unittest.TestCase):
    def test_json_loader_rejects_duplicate_keys_and_nonfinite_constants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(suite.SuiteValidationError):
                suite.load_json_object(path)
            path.write_text('{"a":NaN}', encoding="utf-8")
            with self.assertRaises(suite.SuiteValidationError):
                suite.load_json_object(path)

    def test_module_is_standard_library_only_and_does_not_import_torch(self) -> None:
        tree = ast.parse(
            (ROOT / "scripts" / "run_composition_scaling_suite.py").read_text(
                encoding="utf-8"
            )
        )
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertNotIn("torch", imported)
        self.assertNotIn("torchvision", imported)

    def test_frozen_config_rejects_revised_workspace_worker_digests(self) -> None:
        validated = suite.validate_config(config(), verify_files=False, root=ROOT)
        # The registered completed study stays immutable after current-worker
        # portability changes; executing it with revised sources must fail.
        with self.assertRaisesRegex(suite.SuiteValidationError, "source digest mismatch"):
            suite.validate_config(config(), verify_files=True, root=ROOT)
        self.assertEqual(validated["decision"], "no_release_authorization")
        self.assertEqual(validated["execution"]["max_wall_clock_seconds"], 43_200)
        self.assertEqual(validated["execution"]["max_gpu_reserved_bytes"], 20 * 1024**3)

    def test_exact_five_models_scales_seeds_and_power_sets(self) -> None:
        validated = suite.validate_config(config(), verify_files=False)
        self.assertEqual(
            tuple(model["key"] for model in validated["models"]), suite.MODEL_KEYS
        )
        self.assertEqual(tuple(validated["matrix"]["seeds"]), suite.SEEDS)
        self.assertEqual(len(suite.ALL_SUBSETS), 31)
        self.assertEqual(len(suite.LLM_SUBSETS), 7)
        self.assertEqual(len(suite.VISION_SUBSETS), 3)
        self.assertEqual(len(suite.CROSS_MODAL_SUBSETS), 21)
        self.assertEqual(suite.SCALES["llm"], (2048, 4096, 8192))
        self.assertEqual(suite.SCALES["vision"], (5400, 10800, 21600))

    def test_config_rejects_matrix_or_resource_ceiling_drift(self) -> None:
        mutations = []
        candidate = config()
        candidate["matrix"]["seeds"][1] += 1
        mutations.append(candidate)
        candidate = config()
        candidate["matrix"]["cross_modal_subsets"].pop()
        mutations.append(candidate)
        candidate = config()
        candidate["execution"]["max_wall_clock_seconds"] = 43_201
        mutations.append(candidate)
        candidate = config()
        candidate["execution"]["max_gpu_reserved_bytes"] = 20 * 1024**3 + 1
        mutations.append(candidate)
        candidate = config()
        candidate["source_bindings"]["children"]["llm"]["runner_sha256"] = "0" * 64
        mutations.append(candidate)
        for index, candidate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(suite.SuiteValidationError):
                suite.validate_config(candidate, verify_files=False)

    def test_authority_uses_normalized_exact_literals(self) -> None:
        expected = {
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
        self.assertEqual(suite.AUTHORITY, expected)
        validated = suite.validate_config(config(), verify_files=False)
        for profile in validated["interfaces"]["profiles"]:
            self.assertEqual(profile["screen_authority"], expected)
        self.assertEqual(validated["matrix"]["cell_authority"], expected)
        candidate = config()
        candidate["assessment_input"] = candidate.pop("assessment_input_emitted")
        with self.assertRaises(suite.SuiteValidationError):
            suite.validate_config(candidate, verify_files=False)

    def test_interface_masks_are_explicit_nonordinal_and_bound_to_k_m_profiles(self) -> None:
        validated = suite.validate_config(config(), verify_files=False)
        profiles = {profile["level"]: profile for profile in validated["interfaces"]["profiles"]}
        self.assertTrue(profiles["R2"]["mask"]["exact_candidate_source_metadata"])
        self.assertFalse(profiles["R2"]["mask"]["arbitrary_candidate_scoring"])
        self.assertTrue(profiles["R3"]["mask"]["arbitrary_candidate_scoring"])
        self.assertFalse(profiles["R3"]["mask"]["exact_candidate_source_metadata"])
        self.assertEqual(profiles["R1"]["llm_knowledge_levels"], ["K0"])
        self.assertEqual(profiles["R4"]["llm_knowledge_levels"], ["K0", "K1", "K2", "K3"])
        self.assertEqual(profiles["R5"]["vision_profile"], "M3_source_provenance")
        candidate = config()
        candidate["interfaces"]["profiles"][2]["mask"]["arbitrary_candidate_scoring"] = True
        with self.assertRaises(suite.SuiteValidationError):
            suite.validate_config(candidate, verify_files=False)

    def test_worst_gate_is_categorical_and_absorbing(self) -> None:
        vector = suite.gate_vector(("distilgpt2", "meta-opt-125m"), "R0")
        self.assertEqual(
            vector["model_license"], "BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY"
        )
        self.assertEqual(vector["data_rights"], "MANUAL_REVIEW_REQUIRED")
        roster = suite.gate_vector(("pythia-160m",), "R5")
        self.assertEqual(
            roster["interface_disclosure"], "BLOCKED_AND_REDESIGN_REQUIRED"
        )
        self.assertEqual(roster["model_license"], "MANUAL_REVIEW_REQUIRED")
        with self.assertRaises(suite.SuiteValidationError):
            suite.worst_gate(["NOT_A_GATE", "MANUAL_REVIEW_REQUIRED"])

    def test_valid_child_exports_have_exact_105_and_45_scalar_cells(self) -> None:
        cfg = config()
        llm = suite.validate_child_export(child_export("llm"), "llm", cfg)
        vision = suite.validate_child_export(child_export("vision"), "vision", cfg)
        self.assertEqual(len(llm["subset_scalars"]), 105)
        self.assertEqual(len(vision["subset_scalars"]), 45)

    def test_child_export_rejects_unknown_missing_duplicate_or_nonfinite_cells(self) -> None:
        cfg = config()
        mutations = []
        candidate = child_export("llm")
        candidate["unexpected"] = True
        mutations.append(candidate)
        candidate = child_export("llm")
        candidate["subset_scalars"].pop()
        mutations.append(candidate)
        candidate = child_export("llm")
        candidate["subset_scalars"][-1] = copy.deepcopy(candidate["subset_scalars"][0])
        mutations.append(candidate)
        candidate = child_export("llm")
        candidate["subset_scalars"][0]["metrics"][suite.LLM_METRICS[0]] = float("nan")
        mutations.append(candidate)
        for index, candidate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(suite.SuiteValidationError):
                suite.validate_child_export(candidate, "llm", cfg)

    def test_child_export_rejects_authority_and_budget_escalation(self) -> None:
        cfg = config()
        candidate = child_export("vision")
        candidate["authority"]["can_clear"] = True
        with self.assertRaises(suite.SuiteValidationError):
            suite.validate_child_export(candidate, "vision", cfg)
        candidate = child_export("vision")
        candidate["resources"][0]["peak_gpu_reserved_bytes"] = 20 * 1024**3 + 1
        with self.assertRaises(suite.SuiteValidationError):
            suite.validate_child_export(candidate, "vision", cfg)

    def test_report_never_builds_a_cross_modal_scalar(self) -> None:
        cfg = config()
        report = suite.build_suite_report(
            cfg,
            {"llm": child_export("llm"), "vision": child_export("vision")},
            observed_wall_clock_seconds=60.0,
        )
        self.assertEqual(report["registered_matrix"]["scalar_cell_count"], 150)
        self.assertEqual(len(report["source_digest_vector"]), 12)
        for modality_rows in report["same_population_scalar_results"].values():
            self.assertTrue(all(row["authority"] == suite.AUTHORITY for row in modality_rows))
        self.assertEqual(len(report["subset_summaries"]), 31)
        mixed = [
            item
            for item in report["subset_summaries"]
            if item["composition_kind"] == "cross_modal_vector_only"
        ]
        self.assertEqual(len(mixed), 21)
        for item in mixed:
            self.assertFalse(item["empirical_scalar_composition"]["permitted"])
            self.assertEqual(item["empirical_scalar_composition"]["cell_count"], 0)
            self.assertIsNone(
                item["empirical_scalar_composition"]["cross_population_scalar"]
            )
            self.assertEqual(len(item["resource_vector"]), len(item["model_keys"]))
            self.assertEqual(len(item["interface_gate_vectors"]), 6)
        all_five = mixed[-1]
        self.assertEqual(all_five["model_keys"], list(suite.MODEL_KEYS))
        self.assertEqual(len(all_five["resource_vector"]), 5)

    def test_safe_aggregate_rejects_paths_identifiers_and_per_example_channels(self) -> None:
        for payload in (
            {"run_id": "run-1"},
            {"record_ids": ["x"]},
            {"machine": "/home/operator/output"},
            {"per_example": [0.1]},
        ):
            with self.subTest(payload=payload), self.assertRaises(suite.SuiteValidationError):
                suite.assert_safe_aggregate(payload)

    def test_child_manifest_binds_safe_basename_bytes_digest_and_final_write(self) -> None:
        cfg = config()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            child_output(directory, "llm", cfg)
            export = suite.verify_child_output(directory, "llm", cfg)
            self.assertEqual(export["model_keys"], list(suite.LLM_MODEL_KEYS))

            report_path = directory / cfg["source_bindings"]["children"]["llm"]["report_basename"]
            report_path.write_bytes(report_path.read_bytes() + b" ")
            with self.assertRaises(suite.SuiteValidationError):
                suite.verify_child_output(directory, "llm", cfg)

    def test_child_manifest_rejects_unknown_shape_and_traversing_report(self) -> None:
        cfg = config()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = child_output(directory, "vision", cfg)
            manifest["unexpected"] = True
            (directory / "RUN_COMPLETE.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(suite.SuiteValidationError):
                suite.verify_child_output(directory, "vision", cfg)

            del manifest["unexpected"]
            manifest["report"]["path"] = "../escaped.json"
            (directory / "RUN_COMPLETE.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(suite.SuiteValidationError):
                suite.verify_child_output(directory, "vision", cfg)

    def test_publish_is_no_clobber_and_completion_manifest_is_last(self) -> None:
        cfg = config()
        report = suite.build_suite_report(
            cfg,
            {"llm": child_export("llm"), "vision": child_export("vision")},
            observed_wall_clock_seconds=60.0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "fresh"
            completion = suite.publish_suite_report(output_dir, cfg, report)
            self.assertEqual(completion["status"], "complete")
            entries = {path.name for path in output_dir.iterdir()}
            self.assertEqual(
                entries,
                {
                    "composition-scaling-suite-report.json",
                    "composition-scaling-suite-report.md",
                    "RUN_COMPLETE.json",
                },
            )
            manifest = output_dir / "RUN_COMPLETE.json"
            other_mtimes = [
                path.stat().st_mtime_ns for path in output_dir.iterdir() if path != manifest
            ]
            self.assertGreaterEqual(manifest.stat().st_mtime_ns, max(other_mtimes))
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(output_dir.stat().st_mode), 0o700)
                for path in output_dir.iterdir():
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(completion["filesystem_durability"]["directory_fsync_supported"], os.name != "nt")
            self.assertFalse(completion["filesystem_durability"]["power_loss_durability_guaranteed"])

            serialized = manifest.read_text(encoding="utf-8")
            self.assertNotIn("path", serialized)
            self.assertNotIn("run_id", serialized)
            parsed = json.loads(serialized)
            for role, filename in (
                ("aggregate_json", "composition-scaling-suite-report.json"),
                ("aggregate_markdown", "composition-scaling-suite-report.md"),
            ):
                payload = (output_dir / filename).read_bytes()
                self.assertEqual(parsed["artifacts"][role]["bytes"], len(payload))
                self.assertEqual(
                    parsed["artifacts"][role]["sha256"],
                    hashlib.sha256(payload).hexdigest(),
                )
            with self.assertRaises(suite.SuiteValidationError):
                suite.publish_suite_report(output_dir, cfg, report)

    @unittest.skipUnless(os.name == "nt", "Windows directory-flush warning policy")
    def test_warning_as_error_does_not_fail_after_suite_completion(self) -> None:
        cfg = config()
        report = suite.build_suite_report(cfg, {"llm": child_export("llm"), "vision": child_export("vision")}, observed_wall_clock_seconds=1.0)
        with tempfile.TemporaryDirectory() as temporary, warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            directory = Path(temporary) / "fresh"
            completion = suite.publish_suite_report(directory, cfg, report)
            self.assertEqual(completion["status"], "complete")
            self.assertFalse(completion["filesystem_durability"]["directory_fsync_supported"])
            self.assertTrue((directory / "RUN_COMPLETE.json").is_file())

    def test_atomic_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact.json"
            suite._atomic_write_new(path, b"first")
            with self.assertRaises(FileExistsError):
                suite._atomic_write_new(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")

    def test_directory_measurement_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "target"
            target.write_text("safe", encoding="utf-8")
            link = directory / "link"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(suite.SuiteValidationError):
                suite.directory_regular_file_bytes(directory)

    def test_output_work_and_modality_caches_must_be_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite._assert_disjoint_directory_trees(
                (root / "out", root / "work", root / "llm-cache", root / "vision-cache")
            )
            with self.assertRaises(suite.SuiteValidationError):
                suite._assert_disjoint_directory_trees(
                    (root / "out", root / "out" / "work")
                )

    def test_cli_has_distinct_verified_cache_roots(self) -> None:
        args = suite._parse_arguments(
            ["--output-dir", "unused", "--validate-only"]
        )
        self.assertEqual(
            args.llm_cache_dir,
            ROOT / "output" / "llm-training-hook" / "cache",
        )
        self.assertEqual(
            args.vision_cache_dir,
            ROOT / "output" / "cache" / "vision-training-hook",
        )

    def test_child_command_is_shell_free_serial_contract_with_direct_cache(self) -> None:
        cfg = config()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = mock.Mock(returncode=0)
            with mock.patch.object(suite.subprocess, "run", return_value=completed) as run:
                suite._run_child(
                    "llm",
                    cfg,
                    root / "output",
                    root / "verified-llm-cache",
                    offline=True,
                    deadline=suite.time.monotonic() + 60,
                )
            command = run.call_args.args[0]
            self.assertIn("--config", command)
            self.assertIn("--output-dir", command)
            self.assertIn("--cache-dir", command)
            self.assertIn(str(root / "verified-llm-cache"), command)
            self.assertEqual(command[-1], "--offline")
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertNotIn("stdout", run.call_args.kwargs)
            self.assertNotIn("stderr", run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"], "0")


if __name__ == "__main__":
    unittest.main()
