from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from model_release_assurance.audit import AuditStore
from model_release_assurance.integrity import sha256_file, verify_signed_manifest
from model_release_assurance.models import AssessmentReport, SignedManifest
from model_release_assurance.optimizer import (
    OptimizationReport,
    SignedOptimizationManifest,
    verify_signed_optimization_manifest,
)
from model_release_assurance.release_protocol import (
    ReleaseProtocolRun,
    ReleaseProtocolState,
    ReleaseProtocolVerificationDegradation,
    verify_release_protocol_run,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_government_health_demo",
    ROOT / "scripts" / "run_government_health_demo.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GovernmentHealthDemoTests(unittest.TestCase):
    def test_full_suite_is_fail_closed_and_never_authorizes_production(self) -> None:
        tracked_example_hashes = {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in (ROOT / "examples").rglob("*")
            if path.is_file()
        }
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "demo-run"
            reference_time = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)
            report = MODULE.run_demo_suite(
                run_dir,
                reference_time=reference_time,
            )

            self.assertTrue(report["demo_only"])
            self.assertFalse(report["contains_real_personal_data"])
            self.assertFalse(report["network_access_required"])
            self.assertFalse(report["training_executed"])
            self.assertFalse(report["production_authorization_issued"])
            self.assertTrue(report["fixture_inventory"]["closed_allowlist"])
            self.assertEqual(
                report["fixture_inventory"]["files"],
                MODULE.DEMO_FIXTURE_SHA256,
            )
            self.assertFalse(report["executed_contract"]["healthcare_specific"])
            self.assertFalse(
                report["fictional_healthcare_discussion_overlay"]
                ["executed_by_live_reference_core"]
            )
            self.assertIn("NOT AUTHORIZED", report["default_conclusion"])
            self.assertIn("NOT ACTIVE", report["default_conclusion"])
            spine = report["operational_spine"]
            self.assertEqual(
                tuple(spine["pipeline"]["stage_order"]),
                MODULE.PIPELINE_STAGE_ORDER,
            )
            self.assertEqual(spine["contract"]["status"], "valid")
            self.assertEqual(
                spine["workflow"]["implemented_operation"],
                "offline_structural_transcript_replay",
            )
            self.assertFalse(spine["workflow"]["production_state_changed"])

            preview = report["model_execution_preview"]
            self.assertFalse(preview["admitted_to_assessment"])
            self.assertEqual(preview["admission_join_status"], "not_implemented")
            self.assertEqual(
                [value["kind"] for value in preview["models"]],
                ["cnn", "lstm", "xgboost", "llm"],
            )
            self.assertTrue(all(value["can_clear"] is False for value in preview["models"]))
            self.assertTrue(
                all(
                    value["framework_model_executed"] is False
                    and value["implementation_disclosure"]
                    for value in preview["models"]
                )
            )

            scenarios = {value["scenario_id"]: value for value in report["scenarios"]}
            self.assertEqual(tuple(scenarios), MODULE.SCENARIO_ORDER)
            self.assertEqual(
                {key: value["result"] for key, value in scenarios.items()},
                {
                    "controlled_candidate": "CONTINUE_TO_EXTERNAL_REVIEW",
                    "missing_evidence": "HOLD",
                    "demonstrated_leakage": "BLOCK_AND_REDESIGN",
                    "artifact_tamper": "STOP",
                    "mock_full_lifecycle": "SIMULATED_ACTIVE",
                    "stale_registry": "REASSESS",
                    "deployment_mismatch": "STOP",
                    "monitoring_incident": "SIMULATED_SUSPENDED",
                },
            )
            self.assertEqual(
                scenarios["controlled_candidate"]["optimization_outcome"],
                "release_with_controls",
            )
            self.assertFalse(scenarios["controlled_candidate"]["authorization_eligible"])
            self.assertEqual(scenarios["missing_evidence"]["assessment_verdict"], "inconclusive")
            self.assertEqual(scenarios["demonstrated_leakage"]["assessment_verdict"], "block")
            self.assertEqual(
                scenarios["artifact_tamper"]["failure_category"],
                "artifact_hash_mismatch",
            )
            self.assertTrue(
                all(
                    value["production_authorization_issued"] is False
                    and value["deployment_active"] is False
                    for value in scenarios.values()
                )
            )

            self.assertTrue(scenarios["mock_full_lifecycle"]["protocol_valid"])
            self.assertEqual(
                scenarios["mock_full_lifecycle"]["protocol_final_state"],
                "active",
            )
            self.assertTrue(
                scenarios["mock_full_lifecycle"]["mock_transcript_records_active"]
            )
            self.assertIn(
                ReleaseProtocolVerificationDegradation.STRUCTURAL_PROFILE_ONLY.value,
                scenarios["mock_full_lifecycle"]["protocol_degradations"],
            )
            self.assertFalse(scenarios["stale_registry"]["protocol_valid"])
            self.assertFalse(
                scenarios["stale_registry"]["authorization_recorded_in_mock_transcript"]
            )
            self.assertFalse(scenarios["deployment_mismatch"]["protocol_valid"])
            self.assertFalse(
                scenarios["deployment_mismatch"]["mock_transcript_records_active"]
            )
            self.assertTrue(scenarios["monitoring_incident"]["protocol_valid"])
            self.assertEqual(
                scenarios["monitoring_incident"]["protocol_final_state"],
                "suspended",
            )
            boundary_notice = (
                run_dir
                / "workflow-rehearsal"
                / "00-DEMO-ONLY-NOT-AUTHORIZED.md"
            )
            self.assertIn("NOT AUTHORIZED", boundary_notice.read_text(encoding="utf-8"))
            self.assertIn("mock transcript", boundary_notice.read_text(encoding="utf-8"))

            audit = AuditStore.open_read_only(run_dir / "audit" / "mra.sqlite3").verify()
            self.assertTrue(audit.complete)
            self.assertEqual(audit.event_count, 10)
            self.assertEqual(audit.intent_count, 5)
            self.assertEqual(audit.completed_count, 4)
            self.assertEqual(audit.failed_count, 1)
            self.assertEqual(audit.orphaned_run_ids, ())

            controlled_report_path = run_dir / "reports" / "controlled-assessment.json"
            controlled_report = AssessmentReport.model_validate_json(
                controlled_report_path.read_text(encoding="utf-8")
            )
            optimization_path = run_dir / "reports" / "controlled-optimization.json"
            optimization = OptimizationReport.model_validate_json(
                optimization_path.read_text(encoding="utf-8")
            )
            rebound_request = json.loads(
                (
                    run_dir
                    / "fixtures"
                    / "controlled-candidate"
                    / "generated-optimization-request.json"
                ).read_text(encoding="utf-8")
            )
            rebound_reference = rebound_request["configurations"][0]["assessment"]
            copied_assessment = (
                run_dir
                / "fixtures"
                / "controlled-candidate"
                / rebound_reference["report_path"]
            )
            self.assertEqual(
                rebound_reference["report_sha256"],
                sha256_file(copied_assessment),
            )
            self.assertEqual(
                optimization.selected_assessment_report_sha256,
                rebound_reference["report_sha256"],
            )

            public_key = run_dir / report["integrity"]["demo_public_key_path"]
            assessment_manifest = SignedManifest.model_validate_json(
                (run_dir / "integrity" / "assessment-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            verify_signed_manifest(assessment_manifest, controlled_report, public_key)
            optimization_manifest = SignedOptimizationManifest.model_validate_json(
                (run_dir / "integrity" / "optimization-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            verify_signed_optimization_manifest(
                optimization_manifest,
                optimization,
                public_key,
            )
            self.assertFalse(report["integrity"]["demo_private_key_retained"])
            self.assertFalse(any(run_dir.rglob("private.pem")))

            for value in report["scenarios"]:
                for artifact in value["artifacts"]:
                    path = (run_dir / artifact["path"]).resolve(strict=True)
                    self.assertTrue(path.is_relative_to(run_dir.resolve()))
                    self.assertEqual(artifact["sha256"], sha256_file(path))

            full_run_path = (
                run_dir
                / "workflow-rehearsal"
                / "mock_full_lifecycle-release-protocol-run.json"
            )
            full_run = ReleaseProtocolRun.model_validate_json(
                full_run_path.read_text(encoding="utf-8")
            )
            replay = verify_release_protocol_run(
                full_run,
                full_run_path.parent,
                verify_artifact_files=True,
                as_of=reference_time.replace(minute=20),
            )
            self.assertTrue(replay.valid, replay.reasons)
            self.assertTrue(replay.artifact_files_verified)
            self.assertEqual(replay.final_state, ReleaseProtocolState.ACTIVE)

            registration = (
                run_dir
                / "workflow-rehearsal"
                / full_run.events[0].artifacts[0].path
            )
            registration.write_bytes(registration.read_bytes() + b"\n")
            tampered_replay = verify_release_protocol_run(
                full_run,
                full_run_path.parent,
                verify_artifact_files=True,
                as_of=reference_time.replace(minute=20),
            )
            self.assertFalse(tampered_replay.valid)
            self.assertFalse(tampered_replay.artifact_files_verified)
            self.assertTrue(
                any("failed digest replay" in reason for reason in tampered_replay.reasons)
            )

            plain_report = (run_dir / "START-HERE.md").read_text(encoding="utf-8")
            self.assertIn("NO REAL PATIENT DATA", plain_report)
            self.assertIn("NOT AUTHORIZED", plain_report)
            self.assertIn("Two deliberately separate cases", plain_report)
            self.assertIn("Discussion overlay (not executed)", plain_report)
            self.assertIn("Decision cards", plain_report)
            self.assertIn("hand-coded additive decision-stump proxy", plain_report)
            self.assertIn("What the live pipeline did", plain_report)
            self.assertFalse((run_dir / "audit" / "mra.sqlite3-wal").exists())
            self.assertFalse((run_dir / "audit" / "mra.sqlite3-shm").exists())

        current_example_hashes = {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in (ROOT / "examples").rglob("*")
            if path.is_file()
        }
        self.assertEqual(current_example_hashes, tracked_example_hashes)

    def test_refuses_to_mix_runs_or_accept_naive_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "existing"
            existing.mkdir()
            with self.assertRaises(FileExistsError):
                MODULE.run_demo_suite(existing)
            with self.assertRaisesRegex(ValueError, "timezone"):
                MODULE.run_demo_suite(
                    Path(directory) / "naive",
                    reference_time=datetime(2026, 9, 4, 1, 0),
                )

    def test_confines_run_and_fixture_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            output_root = temporary_root / "output"
            self.assertEqual(
                MODULE._resolve_run_dir(output_root, "review.run_01"),
                output_root.resolve() / "review.run_01",
            )
            for unsafe_run_id in (".", "..", "../escape", "/tmp/escape"):
                with self.subTest(run_id=unsafe_run_id):
                    with self.assertRaises(ValueError):
                        MODULE._resolve_run_dir(output_root, unsafe_run_id)

            for source_path in ("../escape.json", str(temporary_root / "absolute.json")):
                with self.subTest(source_path=source_path):
                    fixture_root = temporary_root / (
                        "fixture-" + str(abs(hash(source_path)))
                    )
                    shutil.copytree(ROOT / "examples", fixture_root)
                    raw = json.loads(
                        (fixture_root / "request.json").read_text(encoding="utf-8")
                    )
                    raw["analyzer_inputs"][0]["provenance"]["source_path"] = source_path
                    with self.assertRaisesRegex(ValueError, "source path"):
                        MODULE._materialize_analyzer_sources(raw, fixture_root)

                    escaped_target = (
                        temporary_root / "escape.json"
                        if source_path.startswith("..")
                        else Path(source_path)
                    )
                    self.assertFalse(escaped_target.exists())

            with self.assertRaisesRegex(ValueError, "input tree"):
                MODULE.run_demo_suite(ROOT / "examples" / "nested-demo-output")
            with self.assertRaisesRegex(ValueError, "input tree"):
                MODULE.run_demo_suite(
                    ROOT
                    / "reproduction"
                    / "model-audit-workflow"
                    / "nested-demo-output"
                )

    def test_fixture_copy_uses_only_the_pinned_synthetic_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            source = temporary_root / "source"
            shutil.copytree(ROOT / "examples", source)
            (source / "unlisted-private-data.csv").write_text(
                "must,not,be,copied\n",
                encoding="utf-8",
            )
            destination = temporary_root / "destination"
            MODULE._copy_examples(destination, source)
            copied = {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            }
            self.assertEqual(copied, set(MODULE.DEMO_FIXTURE_SHA256))
            self.assertFalse((destination / "unlisted-private-data.csv").exists())
            for relative, expected_sha256 in MODULE.DEMO_FIXTURE_SHA256.items():
                self.assertEqual(
                    sha256_file(destination / relative),
                    expected_sha256,
                )

            changed_source = temporary_root / "changed-source"
            shutil.copytree(ROOT / "examples", changed_source)
            changed_request = changed_source / "request.json"
            changed_request.write_bytes(changed_request.read_bytes() + b"\n")
            changed_destination = temporary_root / "changed-destination"
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                MODULE._copy_examples(changed_destination, changed_source)
            self.assertFalse(changed_destination.exists())

            missing_source = temporary_root / "missing-source"
            shutil.copytree(ROOT / "examples", missing_source)
            (missing_source / "policy.json").unlink()
            missing_destination = temporary_root / "missing-destination"
            with self.assertRaisesRegex(ValueError, "missing pinned"):
                MODULE._copy_examples(missing_destination, missing_source)
            self.assertFalse(missing_destination.exists())

            symlink_source = temporary_root / "symlink-source"
            shutil.copytree(ROOT / "examples", symlink_source)
            symlink_target = symlink_source / "request.json"
            symlink_target.unlink()
            symlink_target.symlink_to(ROOT / "examples" / "request.json")
            symlink_destination = temporary_root / "symlink-destination"
            with self.assertRaisesRegex(ValueError, "symlink"):
                MODULE._copy_examples(symlink_destination, symlink_source)
            self.assertFalse(symlink_destination.exists())


if __name__ == "__main__":
    unittest.main()
