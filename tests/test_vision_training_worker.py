from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import stat
import sys
import tempfile
import unittest
import urllib.error
import warnings
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_vision_training_hook_audit import (  # noqa: E402
    CLASS_COUNTS,
    DATASET_DIRECTORY,
    _verify_extraction_manifest,
    apply_brightness,
    apply_deterministic_noise,
    apply_fgsm_pixels,
    atomic_write_new,
    build_markdown_report,
    canonical_json,
    canonical_sha256,
    capture_registered_cuda_nondeterminism,
    download_verified_archive,
    enforce_runtime_provenance_registration,
    load_bound_hook_collector,
    load_config_with_digest,
    measured_pixel_linf,
    open_with_validated_redirects,
    publish_completion_artifacts,
    replay_context_bound_telemetry,
    reserve_output_directory,
    resolve_disjoint_directory_trees,
    source_snapshot,
    summarize_cuda_nondeterminism,
    serialize_context_bound_telemetry,
    stratified_path_split,
    validate_archive_members,
    validate_config,
    validate_download_url,
    validate_split_content_digests,
)

try:  # Optional experiment runtime is absent from dependency-minimal CI.
    import torch
    import torchvision

    from llm_training_hooks import AggregateTrainingHookCollector

    HAS_VISION_RUNTIME = True
except (ImportError, OSError):
    HAS_VISION_RUNTIME = False


CONFIG_PATH = ROOT / "reproduction" / "vision-training-hook" / "config.json"


def _config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _valid_members() -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = [zipfile.ZipInfo(f"{DATASET_DIRECTORY}/")]
    for class_name, count in CLASS_COUNTS.items():
        members.append(zipfile.ZipInfo(f"{DATASET_DIRECTORY}/{class_name}/"))
        for index in range(1, count + 1):
            member = zipfile.ZipInfo(
                f"{DATASET_DIRECTORY}/{class_name}/{class_name}_{index}.jpg"
            )
            member.file_size = 1
            member.external_attr = (stat.S_IFREG | 0o644) << 16
            members.append(member)
    return members


class VisionTrainingWorkerTests(unittest.TestCase):
    def test_config_freezes_full_real_dataset_and_non_authorizing_gates(self) -> None:
        validated = validate_config(_config())
        self.assertEqual(validated["dataset"]["train_rows"], 21_600)
        self.assertEqual(validated["dataset"]["test_rows"], 5_400)
        self.assertFalse(validated["dataset"]["synthetic_samples"])
        self.assertFalse(validated["dataset"]["augmented_samples"])
        self.assertEqual(validated["schema_version"], "1.1")
        self.assertFalse(validated["assessment_input_emitted"])
        self.assertEqual(
            validated["dataset"]["rights_gate"],
            "MANUAL_REVIEW_REQUIRED",
        )
        self.assertFalse(validated["authorization_eligible"])
        self.assertEqual(validated["decision"], "no_release_authorization")
        self.assertFalse(
            validated["runtime"]["reproducibility"]["bitwise_reproducible"]
        )
        self.assertFalse(
            validated["runtime"]["reproducibility"][
                "single_run_variance_estimated"
            ]
        )
        self.assertEqual(
            validated["hook_non_interference_control"]["control_device"], "cpu"
        )
        self.assertFalse(
            validated["hook_non_interference_control"][
                "cuda_noninterference_proven"
            ]
        )
        self.assertEqual(
            validated["release_gate_summary"]["contract_semantics"],
            "illustrative_non_mrap_gate_summary",
        )
        for field in (
            "can_clear",
            "can_block",
            "attack_battery_eligible",
            "assessment_input_emitted",
        ):
            self.assertFalse(validated["red_team"][field])

        for field, value in (
            ("train_rows", 21_599),
            ("test_rows", 5_399),
            ("synthetic_samples", True),
            ("augmented_samples", True),
            ("max_download_bytes", 94_658_722),
        ):
            with self.subTest(field=field):
                candidate = copy.deepcopy(_config())
                candidate["dataset"][field] = value
                with self.assertRaises(ValueError):
                    validate_config(candidate)

    def test_config_rejects_unknown_fields_and_freezes_every_section(self) -> None:
        candidate = copy.deepcopy(_config())
        candidate["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "top-level"):
            validate_config(candidate)

        candidate = copy.deepcopy(_config())
        candidate["experiment_id"] = "another-experiment"
        with self.assertRaisesRegex(ValueError, "experiment_id"):
            validate_config(candidate)

        sections = (
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
        )
        for section in sections:
            with self.subTest(section=section):
                candidate = copy.deepcopy(_config())
                if isinstance(candidate[section], dict):
                    candidate[section]["unexpected"] = True
                else:
                    candidate[section].append({"unexpected": True})
                with self.assertRaises(ValueError):
                    validate_config(candidate)

    def test_config_freezes_two_canonical_architectures_and_exact_hooks(self) -> None:
        validated = validate_config(_config())
        models = {model["key"]: model for model in validated["models"]}
        self.assertEqual(set(models), {"alexnet", "densenet121"})
        self.assertIsNone(models["alexnet"]["weights"])
        self.assertIsNone(models["densenet121"]["weights"])
        self.assertEqual(
            models["alexnet"]["hook_modules"],
            ["features.2", "features.12", "classifier.6"],
        )
        self.assertEqual(
            models["densenet121"]["hook_modules"],
            ["features.conv0", "features.denseblock4", "classifier"],
        )
        self.assertEqual(
            validated["training"]["expected_optimizer_steps_per_model"], 169
        )
        self.assertGreaterEqual(validated["hooks"]["max_events_per_model"], 169 * 7)

        candidate = copy.deepcopy(_config())
        candidate["models"][0]["hook_modules"][-1] = "classifier"
        with self.assertRaisesRegex(ValueError, "exact safe allowlist"):
            validate_config(candidate)

        pretrained = copy.deepcopy(_config())
        pretrained["models"][0]["weights"] = "DEFAULT"
        with self.assertRaisesRegex(ValueError, "pretrained"):
            validate_config(pretrained)

    def test_config_freezes_manifest_rosters_license_gate_and_unique_outputs(self) -> None:
        mutations = [
            ("manifest", lambda value: value["dataset"]["extraction_manifest"].__setitem__("canonical_sha256", "0" * 64)),
            ("train roster", lambda value: value["dataset"]["split"].__setitem__("train_relative_path_set_sha256", "0" * 64)),
            ("license gate", lambda value: value["release_gate_summary"].__setitem__("model_implementation_license_gate", "PASS")),
            ("roster handling", lambda value: value["roster_release_handling"].__setitem__("protected_exact_roster_can_clear", True)),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = copy.deepcopy(_config())
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate_config(candidate)

        collision = copy.deepcopy(_config())
        collision["output"]["json_report"] = "training-telemetry-alexnet.jsonl"
        with self.assertRaises(ValueError):
            validate_config(collision)

    def test_exact_ec2_runtime_provenance_is_registered_and_compared(self) -> None:
        registered = _config()["runtime"]["expected_provenance"]
        self.assertEqual(registered["registration_status"], "REGISTERED")
        exact = registered["exact"]
        gate = enforce_runtime_provenance_registration(registered, exact)
        self.assertEqual(gate["status"], "MATCH")
        self.assertFalse(gate["can_authorize"])

        altered = dict(exact)
        altered["alexnet_constructor_source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            enforce_runtime_provenance_registration(registered, altered)

        pending = copy.deepcopy(registered)
        pending["registration_status"] = "PENDING_EC2_BASELINE_CAPTURE"
        with self.assertRaisesRegex(ValueError, "pending"):
            enforce_runtime_provenance_registration(pending, exact)

    def test_exact_config_bytes_are_hashed_before_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            payload = CONFIG_PATH.read_bytes()
            path.write_bytes(payload)
            validated, digest = load_config_with_digest(path)
            self.assertEqual(validated["experiment_id"], _config()["experiment_id"])
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_train_model_definition_and_run_call_have_the_same_signature(self) -> None:
        source = (ROOT / "scripts" / "run_vision_training_hook_audit.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        definition = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "train_model"
        )
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "train_model"
        ]
        self.assertEqual(len(definition.args.args), 7)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0].args), 7)
        self.assertEqual(calls[0].keywords, [])
        self.assertEqual(
            [node.id for node in calls[0].args if isinstance(node, ast.Name)],
            [
                "torch",
                "model",
                "train_dataset",
                "config",
                "model_config",
                "device",
                "run_context",
            ],
        )

    @unittest.skipUnless(HAS_VISION_RUNTIME, "optional torch/torchvision runtime unavailable")
    def test_registered_modules_have_complete_forward_backward_coverage(self) -> None:
        for registered in _config()["models"]:
            with self.subTest(model=registered["key"]):
                constructor = getattr(torchvision.models, registered["constructor"])
                model = constructor(weights=None, num_classes=10)
                collector = AggregateTrainingHookCollector(
                    model,
                    module_names=registered["hook_modules"],
                    expected_steps=1,
                    max_events=7,
                )
                model.train()
                with collector:
                    inputs = torch.randn(1, 3, 96, 96)
                    labels = torch.tensor([3])
                    loss = torch.nn.functional.cross_entropy(model(inputs), labels)
                    loss.backward()
                    collector.step(loss, tokens=int(inputs.numel()), target_tokens=1)
                report = collector.finalize(expected_steps=1)
                self.assertEqual(report["event_count"], 7)
                self.assertEqual(report["coverage_status"], "complete")
                self.assertTrue(report["handles_removed"])
                self.assertEqual(report["nonfinite_elements"], 0)

    def test_canonical_hash_is_order_independent_and_strict(self) -> None:
        left = {"dataset": {"rows": 60_000, "real": True}, "models": [2, 1]}
        right = {"models": [2, 1], "dataset": {"real": True, "rows": 60_000}}
        expected = hashlib.sha256(
            b'{"dataset":{"real":true,"rows":60000},"models":[2,1]}'
        ).hexdigest()
        self.assertEqual(canonical_sha256(left), expected)
        self.assertEqual(canonical_sha256(right), expected)
        with self.assertRaises(ValueError):
            canonical_sha256({"invalid": float("nan")})

    def test_path_hash_split_is_deterministic_stratified_and_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = [
                (str(root / "A" / f"A_{index}.jpg"), 0) for index in range(10)
            ] + [
                (str(root / "B" / f"B_{index}.jpg"), 1) for index in range(5)
            ]
            first_train, first_test, first_details = stratified_path_split(
                samples,
                root,
                ["A", "B"],
                {"A": 10, "B": 5},
                seed=3407,
                train_fraction=0.8,
            )
            second_train, second_test, second_details = stratified_path_split(
                samples,
                root,
                ["A", "B"],
                {"A": 10, "B": 5},
                seed=3407,
                train_fraction=0.8,
            )
            self.assertEqual(first_train, second_train)
            self.assertEqual(first_test, second_test)
            self.assertEqual(first_details, second_details)
            self.assertEqual(first_details["train_class_counts"], [8, 4])
            self.assertEqual(first_details["test_class_counts"], [2, 1])
            self.assertTrue(set(first_train).isdisjoint(first_test))
            self.assertEqual(len(first_train) + len(first_test), 15)

    def test_content_digest_split_fails_on_within_or_cross_split_duplicates(self) -> None:
        relative = {0: "A/0.jpg", 1: "A/1.jpg", 2: "B/2.jpg"}
        files = {
            "A/0.jpg": {"sha256": "0" * 64},
            "A/1.jpg": {"sha256": "1" * 64},
            "B/2.jpg": {"sha256": "2" * 64},
        }
        result = validate_split_content_digests(
            [0, 1], [2], relative, files, expected_overlap=0
        )
        self.assertEqual(result["unique_image_content_sha256"], 3)
        files["B/2.jpg"]["sha256"] = "1" * 64
        with self.assertRaisesRegex(ValueError, "across train and test"):
            validate_split_content_digests(
                [0, 1], [2], relative, files, expected_overlap=0
            )
        files["A/1.jpg"]["sha256"] = "0" * 64
        files["B/2.jpg"]["sha256"] = "2" * 64
        with self.assertRaisesRegex(ValueError, "within a split"):
            validate_split_content_digests(
                [0, 1], [2], relative, files, expected_overlap=0
            )

    def test_archive_member_allowlist_rejects_extras_links_and_oversize(self) -> None:
        valid = _valid_members()
        summary = validate_archive_members(valid, max_extracted_bytes=200_000_000)
        self.assertEqual(summary["member_count"], 27_011)
        self.assertEqual(summary["file_count"], 27_000)

        extra = [*valid, zipfile.ZipInfo("unexpected")]
        with self.assertRaisesRegex(ValueError, "path"):
            validate_archive_members(extra, max_extracted_bytes=200_000_000)

        linked = _valid_members()
        target = next(member for member in linked if member.filename.endswith("AnnualCrop_1.jpg"))
        target.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, "links"):
            validate_archive_members(linked, max_extracted_bytes=200_000_000)

        oversized = _valid_members()
        target = next(member for member in oversized if member.filename.endswith("AnnualCrop_1.jpg"))
        target.file_size = 1_000_001
        with self.assertRaisesRegex(ValueError, "file cap"):
            validate_archive_members(oversized, max_extracted_bytes=200_000_000)

    def test_cached_manifest_is_byte_capped_before_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset_dir = root / DATASET_DIRECTORY
            dataset_dir.mkdir()
            manifest = root / "manifest.json"
            cap = _config()["dataset"]["extraction_manifest"]["max_bytes"]
            with manifest.open("wb") as stream:
                stream.seek(cap)
                stream.write(b"x")
            with mock.patch(
                "run_vision_training_hook_audit.os.read",
                side_effect=AssertionError("oversized manifest content was read"),
            ) as read_mock:
                with self.assertRaisesRegex(ValueError, "byte cap"):
                    _verify_extraction_manifest(
                        dataset_dir, manifest, _config()["dataset"]
                    )
            read_mock.assert_not_called()
            manifest.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "preregistered digest"):
                _verify_extraction_manifest(
                    dataset_dir, manifest, _config()["dataset"]
                )

    def test_download_url_validation_rejects_unregistered_hops(self) -> None:
        allowed = ["zenodo.org", "www.zenodo.org"]
        self.assertEqual(
            validate_download_url("https://zenodo.org/records/7711810", allowed),
            "https://zenodo.org/records/7711810",
        )
        for url in (
            "http://zenodo.org/records/7711810",
            "https://evil.example/EuroSAT_RGB.zip",
            "https://zenodo.org.evil.example/EuroSAT_RGB.zip",
            "https://user@zenodo.org/EuroSAT_RGB.zip",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_download_url(url, allowed)

    def test_redirect_target_is_validated_before_the_next_open(self) -> None:
        class Response:
            def __init__(self, url: str) -> None:
                self.url = url

            def geturl(self) -> str:
                return self.url

        class Opener:
            def __init__(self, location: str) -> None:
                self.location = location
                self.calls: list[str] = []

            def open(self, request, timeout):  # noqa: ANN001, ANN201
                self.calls.append(request.full_url)
                if len(self.calls) == 1:
                    raise urllib.error.HTTPError(
                        request.full_url,
                        302,
                        "Found",
                        {"Location": self.location},
                        io.BytesIO(),
                    )
                return Response(request.full_url)

        allowed = ["zenodo.org", "www.zenodo.org"]
        accepted = Opener("https://www.zenodo.org/object")
        response, requested = open_with_validated_redirects(
            "https://zenodo.org/start", allowed, opener=accepted
        )
        self.assertEqual(response.geturl(), "https://www.zenodo.org/object")
        self.assertEqual(requested, accepted.calls)

        rejected = Opener("https://evil.example/object")
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            open_with_validated_redirects(
                "https://zenodo.org/start", allowed, opener=rejected
            )
        self.assertEqual(rejected.calls, ["https://zenodo.org/start"])

    def test_offline_mode_requires_exact_cached_bytes_without_network(self) -> None:
        dataset = _config()["dataset"]
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            with self.assertRaisesRegex(FileNotFoundError, "offline replay"):
                download_verified_archive(dataset, cache, offline=True)

            (cache / dataset["archive_file"]).write_bytes(b"not-eurosat")
            with self.assertRaisesRegex(ValueError, "byte count"):
                download_verified_archive(dataset, cache, offline=True)

    def test_output_directory_and_artifacts_refuse_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run-1"
            self.assertEqual(reserve_output_directory(run), run.resolve())
            with self.assertRaisesRegex(FileExistsError, "refusing to reuse"):
                reserve_output_directory(run)

            artifact = run / "report.json"
            atomic_write_new(artifact, "first\n")
            self.assertEqual(artifact.read_text(encoding="utf-8"), "first\n")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                atomic_write_new(artifact, "second\n")
            self.assertEqual(artifact.read_text(encoding="utf-8"), "first\n")

    def test_output_and_cache_trees_are_disjoint_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for output_dir, cache_dir in (
                (root / "shared", root / "shared"),
                (root / "cache" / "run", root / "cache"),
                (root / "run", root / "run" / "cache"),
            ):
                with self.subTest(output_dir=output_dir, cache_dir=cache_dir):
                    with self.assertRaisesRegex(ValueError, "must be disjoint"):
                        resolve_disjoint_directory_trees(output_dir, cache_dir)

            output_dir, cache_dir = resolve_disjoint_directory_trees(
                root / "results" / "run", root / "cache"
            )
            self.assertEqual(output_dir, (root / "results" / "run").resolve())
            self.assertEqual(cache_dir, (root / "cache").resolve())

    def test_json_completion_signal_is_last_and_absent_after_markdown_failure(self) -> None:
        def report() -> dict:
            return {
                "artifact_handling": {
                    "artifacts_published_without_replacement": True,
                },
                "models": [],
                "decision": "no_release_authorization",
            }

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            calls: list[str] = []

            def failing_writer(path: Path, payload: str) -> None:
                calls.append(path.name)
                if path.name == "report.md":
                    raise OSError("simulated Markdown publication failure")
                atomic_write_new(path, payload)

            with self.assertRaisesRegex(OSError, "Markdown publication failure"):
                publish_completion_artifacts(
                    output_dir,
                    [("telemetry.jsonl", "{}\n")],
                    report(),
                    "report.json",
                    "report.md",
                    writer=failing_writer,
                )
            self.assertEqual(calls, ["telemetry.jsonl", "report.md"])
            self.assertFalse((output_dir / "report.json").exists())

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            calls = []

            def recording_writer(path: Path, payload: str) -> None:
                calls.append(path.name)
                atomic_write_new(path, payload)

            published = publish_completion_artifacts(
                output_dir,
                [("telemetry.jsonl", "{}\n")],
                report(),
                "report.json",
                "report.md",
                writer=recording_writer,
            )
            self.assertEqual(
                calls, ["telemetry.jsonl", "report.md", "report.json"]
            )
            protocol = published["artifact_handling"]["publication_protocol"]
            self.assertTrue(protocol["completion_signal_published_last"])
            self.assertEqual(protocol["completion_signal"], "report.json")
            disk_report = json.loads(
                (output_dir / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(disk_report["artifact_handling"]["publication_protocol"], protocol)

    def test_hook_collector_executes_only_the_prehashed_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            hook = Path(temporary) / "hooks.py"
            trusted = b"class AggregateTrainingHookCollector:\n    marker = 'trusted'\n"
            hook.write_bytes(trusted)
            digest = hashlib.sha256(trusted).hexdigest()
            collector, evidence = load_bound_hook_collector(hook, digest)
            self.assertEqual(collector.marker, "trusted")
            self.assertEqual(evidence["source_sha256"], digest)
            self.assertEqual(evidence["load_strategy"], "compile_exact_prehashed_bytes")
            self.assertEqual(evidence["source_logical_name"], "hooks.py")
            self.assertNotIn(str(Path(temporary)), json.dumps(evidence))

            hook.write_text(
                "class AggregateTrainingHookCollector:\n    marker = 'changed'\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "changed between"):
                load_bound_hook_collector(hook, digest)

    def test_bounded_reader_preserves_crlf_and_control_z_bytes(self) -> None:
        import run_vision_training_hook_audit as worker

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "exact-bytes.txt"
            payload = b"first\r\nsecond\r\n\x1afinal\n"
            path.write_bytes(payload)
            self.assertEqual(worker.read_bounded_regular_file(path, 1024, "binary regression"), payload)

    def test_public_source_provenance_contains_no_absolute_machine_paths(self) -> None:
        source = source_snapshot(CONFIG_PATH)
        hook = ROOT / "scripts" / "llm_training_hooks.py"
        _collector, hook_evidence = load_bound_hook_collector(
            hook, hashlib.sha256(hook.read_bytes()).hexdigest()
        )
        source["hook_runtime_binding"] = hook_evidence
        self.assertEqual(
            source["config_logical_name"],
            "reproduction/vision-training-hook/config.json",
        )
        self.assertEqual(
            hook_evidence["source_logical_name"], "scripts/llm_training_hooks.py"
        )
        self.assertNotIn("config_path", source)
        serialized = json.dumps(source, sort_keys=True)
        self.assertNotIn(str(ROOT.resolve()), serialized)
        self.assertNotIn(str(Path.home()), serialized)

    def test_cuda_warning_capture_allows_hook_warning_and_rejects_unknown_nondeterminism(self) -> None:
        config = _config()
        with capture_registered_cuda_nondeterminism(
            config, "training:fixture"
        ) as phase:
            warnings.warn(
                "adaptive_avg_pool2d_backward_cuda does not have a deterministic implementation",
                UserWarning,
            )
            warnings.warn(
                "Full backward hook is firing when gradients are computed with respect to module outputs",
                UserWarning,
            )
        self.assertEqual(
            phase["kernel_counts"], {"adaptive_avg_pool2d_backward_cuda": 1}
        )
        self.assertEqual(phase["other_warning_count"], 1)
        summary = summarize_cuda_nondeterminism(config, [phase])
        self.assertFalse(summary["bitwise_reproducible"])
        self.assertFalse(summary["single_run_variance_estimated"])
        self.assertEqual(summary["unexpected_nondeterminism_warning_count"], 0)

        with self.assertRaisesRegex(ValueError, "unexpected nondeterminism"):
            with capture_registered_cuda_nondeterminism(
                config, "training:fixture"
            ):
                warnings.warn(
                    "another_backward_cuda has no deterministic implementation",
                    UserWarning,
                )

    def test_context_bound_telemetry_replay_detects_context_and_event_tampering(self) -> None:
        context = {"run_id": "run-1", "archive_sha256": "a" * 64}
        unsigned = {
            "sequence": 0,
            "previous_sha256": canonical_sha256(context),
            "event_type": "step",
            "step": 0,
        }
        event = {
            **unsigned,
            "event_sha256": hashlib.sha256(canonical_json(unsigned)).hexdigest(),
        }
        payload = serialize_context_bound_telemetry([event], context)
        replay = replay_context_bound_telemetry(payload)
        self.assertTrue(replay["independent_replay_passed"])
        self.assertEqual(replay["event_count"], 1)

        records = [json.loads(line) for line in payload.splitlines()]
        records[0]["context"]["run_id"] = "run-2"
        tampered_context = "".join(
            canonical_json(record).decode("ascii") + "\n" for record in records
        )
        with self.assertRaisesRegex(ValueError, "context digest"):
            replay_context_bound_telemetry(tampered_context)

        records = [json.loads(line) for line in payload.splitlines()]
        records[1]["step"] = 1
        tampered_event = "".join(
            canonical_json(record).decode("ascii") + "\n" for record in records
        )
        with self.assertRaisesRegex(ValueError, "event digest"):
            replay_context_bound_telemetry(tampered_event)

    @unittest.skipUnless(HAS_VISION_RUNTIME, "optional torch runtime unavailable")
    def test_red_team_perturbations_are_deterministic_and_fgsm_is_bounded(self) -> None:
        pixels = torch.linspace(0.0, 1.0, steps=24).reshape(1, 3, 2, 4)
        first_generator = torch.Generator(device="cpu").manual_seed(3407)
        second_generator = torch.Generator(device="cpu").manual_seed(3407)
        first = apply_deterministic_noise(torch, pixels, 0.05, first_generator)
        second = apply_deterministic_noise(torch, pixels, 0.05, second_generator)
        self.assertTrue(torch.equal(first, second))
        bright = apply_brightness(pixels, 1.25)
        self.assertGreaterEqual(float(bright.min()), 0.0)
        self.assertLessEqual(float(bright.max()), 1.0)
        epsilon = 2 / 255
        adversarial = apply_fgsm_pixels(pixels, torch.ones_like(pixels), epsilon)
        self.assertLessEqual(
            measured_pixel_linf(torch, adversarial, pixels), epsilon + 1e-7
        )

    def test_markdown_reports_scale_caveats_and_blocking_rights_gate(self) -> None:
        model = {
            "model_key": "alexnet",
            "parameter_count": 57_000_000,
            "before_training_test": {
                "mean_cross_entropy": 2.31,
                "top1_accuracy": 0.10,
            },
            "after_training_test": {
                "mean_cross_entropy": 2.10,
                "top1_accuracy": 0.22,
            },
            "training": {
                "examples_per_second": 123.45,
                "peak_gpu_allocated_bytes": 2 * 1024**3,
                "optimizer_steps": 169,
            },
            "telemetry": {"coverage_status": "complete"},
        }
        report = {
            "execution": {"test_verdict": "passed"},
            "dataset": {
                "archive_sha256": "6" * 64,
                "train_rows": 21_600,
                "test_rows": 5_400,
            },
            "runtime": {
                "gpu": "NVIDIA L4",
                "torch": "2.13.0+cu130",
                "torchvision": "0.28.0+cu130",
            },
            "cuda_reproducibility": {
                "deterministic_algorithms_mode": "warn_only",
                "bitwise_reproducible": False,
                "observed_kernel_warning_counts": {
                    "adaptive_avg_pool2d_backward_cuda": 2
                },
                "unexpected_nondeterminism_warning_count": 0,
                "other_warning_count": 1,
            },
            "models": [model, {**model, "model_key": "densenet121"}],
            "release_gate_summary": {
                "dataset_rights_gate": "MANUAL_REVIEW_REQUIRED",
                "quality_gate": "NOT_ASSESSED",
                "privacy_gate": "NOT_ASSESSED",
                "security_gate": "NOT_ASSESSED",
            },
            "metadata_release_profiles": _config()["metadata_release_profiles"],
            "decision": "no_release_authorization",
            "assessment_input_emitted": False,
        }
        markdown = build_markdown_report(report)
        self.assertIn("21,600 training and 5,400 test", markdown)
        self.assertIn("no synthetic training samples", markdown)
        self.assertIn("BLOCKED_REDESIGN_REQUIRED", markdown)
        self.assertIn("native 64x64", markdown)
        self.assertIn("cannot clear a release contract", markdown)
        self.assertIn("path-hash split", markdown)
        self.assertNotIn("content-hash split", markdown)
        self.assertIn("does not prove CUDA hook non-interference", markdown)
        self.assertIn("illustrative non-MRAP gate summary", markdown)
        self.assertIn("assessment_input_emitted: false", markdown)
        self.assertIn("`no_release_authorization`", markdown)
        self.assertNotIn("release authorized", markdown.lower())


if __name__ == "__main__":
    unittest.main()
