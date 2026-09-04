from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    verify_release_artifact,
)
from model_release_assurance.models import (
    AssessmentReport,
    AssessmentRequest,
    OverallVerdict,
    ReleaseContract,
    StatisticalFloorDesignRegistration,
    StatisticalFloorFamilyPlan,
)
from model_release_assurance.release_protocol import (
    ReleaseProtocolEventType,
    ReleaseProtocolRun,
    ReleaseProtocolState,
    verify_release_protocol_run,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_training_release_demo.py"
HAS_EXPERIMENT_STACK = all(
    importlib.util.find_spec(name) is not None
    for name in (
        "joblib",
        "numpy",
        "pandas",
        "pyarrow",
        "scipy",
        "sklearn",
        "xgboost",
    )
)


def _load_demo_module() -> Any:
    spec = importlib.util.spec_from_file_location("run_training_release_demo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise AssertionError(f"timestamp is not timezone-aware: {value!r}")
    return parsed


def _artifact_records(report: dict[str, Any]) -> list[dict[str, str]]:
    raw = report["artifacts"]
    records = list(raw.values()) if isinstance(raw, dict) else list(raw)
    for record in records:
        if not isinstance(record, dict) or not {"path", "sha256"}.issubset(record):
            raise AssertionError("every artifact record must contain path and sha256")
    return records


def _verification_is_valid(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        return result.get("valid") is True
    return getattr(result, "valid", None) is True


@unittest.skipUnless(
    HAS_EXPERIMENT_STACK,
    "training-release demo requires the optional experiments dependencies",
)
class TrainingReleaseDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SCRIPT.is_file():
            raise AssertionError(f"training-release demo script is missing: {SCRIPT}")
        cls.module = _load_demo_module()

    def test_public_xgboost_training_flows_through_mra_and_stops_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            run_dir = Path(directory_name) / "training-release-run"
            report = self.module.run_training_release_demo(
                run_dir,
                dataset_profile="sklearn-breast-cancer",
            )

            # This is a real model-training run over sklearn's bundled public
            # Wisconsin Diagnostic Breast Cancer dataset. It is intentionally
            # not a claim about private clinical data or production readiness.
            self.assertTrue(report["training_executed"])
            dataset = report["dataset"]
            self.assertEqual(dataset["profile"], "sklearn-breast-cancer")
            self.assertTrue(dataset["real_public_data"])
            self.assertFalse(dataset["contains_personal_data"])
            self.assertFalse(dataset["contains_production_data"])
            self.assertEqual(dataset["rows"], 569)
            self.assertIn("breast cancer", dataset["source"].lower())
            dataset_path = (run_dir / dataset["dataset_path"]).resolve(strict=True)
            self.assertTrue(dataset_path.is_relative_to(run_dir.resolve()))
            self.assertEqual(dataset["dataset_sha256"], sha256_file(dataset_path))

            training = report["training"]
            self.assertTrue(training["model_fit_completed"])
            self.assertEqual(training["model_family"], "xgboost.XGBClassifier")
            hook = training["training_hook"]
            self.assertGreater(hook["hook_iterations"], 0)
            self.assertTrue(hook["diagnostic_only"])
            self.assertFalse(hook["admitted_as_release_evidence"])

            worker_manifests = list(
                (run_dir / "training" / "worker").glob("seed-*/run-manifest.json")
            )
            self.assertEqual(len(worker_manifests), 1)
            worker_manifest = json.loads(worker_manifests[0].read_text(encoding="utf-8"))
            telemetry_record = worker_manifest["artifacts"]["training_telemetry"]
            telemetry_path = (
                worker_manifests[0].parent / telemetry_record["path"]
            ).resolve(strict=True)
            self.assertEqual(telemetry_record["sha256"], sha256_file(telemetry_path))
            telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
            self.assertEqual(hook["telemetry"], telemetry)
            self.assertEqual(worker_manifest["training_telemetry"], telemetry)
            self.assertEqual(telemetry["evidence_class"], "diagnostic")
            self.assertFalse(telemetry["can_clear"])
            self.assertFalse(telemetry["contains_row_level_data"])
            for role in ("target", "reference"):
                model_telemetry = telemetry["models"][role]
                self.assertEqual(model_telemetry["model_role"], role)
                self.assertEqual(model_telemetry["begin_hook_calls"], 1)
                self.assertEqual(model_telemetry["end_hook_calls"], 1)
                self.assertGreater(model_telemetry["iteration_count"], 0)
                self.assertTrue(model_telemetry["metrics"])
                self.assertTrue(
                    all(
                        metric["nonfinite"] == 0
                        for metric in model_telemetry["metrics"].values()
                    )
                )

            release_path = run_dir / "contracts" / "release-contract.json"
            request_path = run_dir / "assessment" / "assessment-request.json"
            assessment_path = run_dir / "assessment" / "assessment-report.json"
            protocol_path = run_dir / "workflow" / "release-protocol-run.json"
            machine_report_path = run_dir / "pipeline-report.json"
            guide_path = run_dir / "START-HERE.md"
            for path in (
                release_path,
                request_path,
                assessment_path,
                protocol_path,
                machine_report_path,
                guide_path,
            ):
                self.assertTrue(path.is_file(), path)

            release = ReleaseContract.model_validate_json(
                release_path.read_text(encoding="utf-8")
            )
            request = AssessmentRequest.model_validate_json(
                request_path.read_text(encoding="utf-8")
            )
            assessment = AssessmentReport.model_validate_json(
                assessment_path.read_text(encoding="utf-8")
            )
            protocol = ReleaseProtocolRun.model_validate_json(
                protocol_path.read_text(encoding="utf-8")
            )

            persisted_report = json.loads(machine_report_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted_report, report)

            release_contract_sha256 = sha256_bytes(canonical_json_bytes(release))
            request_sha256 = sha256_bytes(canonical_json_bytes(request))
            release_bundle = Path(release.artifact_path)
            if not release_bundle.is_absolute():
                release_bundle = run_dir / release_bundle
            release_bundle_sha256 = sha256_file(release_bundle)

            # One exported byte sequence must be joined all the way through the
            # contract, analyzer input, assessment, human report, and protocol.
            self.assertEqual(request.release, release)
            self.assertEqual(release.artifact_sha256, release_bundle_sha256)
            self.assertEqual(assessment.artifact_sha256, release_bundle_sha256)
            self.assertEqual(assessment.release_contract_sha256, release_contract_sha256)
            self.assertEqual(assessment.request_sha256, request_sha256)
            self.assertEqual(protocol.release_instance_sha256, sha256_file(release_path))
            self.assertEqual(protocol.artifact_sha256, release_bundle_sha256)
            for analyzer_input in request.analyzer_inputs:
                self.assertEqual(
                    analyzer_input.evidence_context.artifact_sha256,
                    release_bundle_sha256,
                )
                self.assertEqual(
                    analyzer_input.evidence_context.release_contract_sha256,
                    release_contract_sha256,
                )
            for evidence in assessment.evidence:
                self.assertEqual(evidence.artifact_sha256, release_bundle_sha256)
                self.assertEqual(
                    evidence.release_contract_sha256,
                    release_contract_sha256,
                )

            bindings = report["bindings"]
            self.assertTrue(bindings["all_equal"])
            self.assertEqual(
                {
                    bindings["release_bundle_sha256"],
                    bindings["release_contract_artifact_sha256"],
                    bindings["assessment_artifact_sha256"],
                    bindings["protocol_artifact_sha256"],
                    release_bundle_sha256,
                },
                {release_bundle_sha256},
            )

            # Preregistration must precede model fitting; confirmatory evidence
            # must be generated only after the exact candidate bytes exist.
            workflow = report["workflow"]
            plan_frozen_at = _parse_timestamp(workflow["plan_frozen_at"])
            training_started_at = _parse_timestamp(workflow["training_started_at"])
            training_completed_at = _parse_timestamp(workflow["training_completed_at"])
            evidence_observed_at = _parse_timestamp(workflow["evidence_observed_at"])
            evidence_frozen_at = _parse_timestamp(workflow["evidence_frozen_at"])
            self.assertLessEqual(plan_frozen_at, training_started_at)
            self.assertLessEqual(training_started_at, training_completed_at)
            self.assertLessEqual(training_completed_at, evidence_observed_at)
            self.assertLessEqual(evidence_observed_at, evidence_frozen_at)

            attack_inputs = [
                value for value in request.analyzer_inputs if value.analyzer == "attack"
            ]
            self.assertEqual(len(attack_inputs), 1)
            attack_input = attack_inputs[0]
            self.assertEqual(
                attack_input.evidence_context.observed_at,
                evidence_observed_at,
            )
            family_plan_path = Path(attack_input.provenance.configuration_path)
            if not family_plan_path.is_absolute():
                family_plan_path = run_dir / family_plan_path
            family_plan = StatisticalFloorFamilyPlan.model_validate_json(
                family_plan_path.read_text(encoding="utf-8")
            )
            self.assertLessEqual(family_plan.frozen_at, training_started_at)
            self.assertEqual(
                attack_input.comparison_family_size,
                len(family_plan.members),
            )
            member = next(
                value
                for value in family_plan.members
                if value.registration_sha256 == attack_input.preregistration_sha256
            )
            registration_path = Path(member.registration_path)
            if not registration_path.is_absolute():
                registration_path = run_dir / registration_path
            self.assertEqual(member.registration_sha256, sha256_file(registration_path))
            registration = StatisticalFloorDesignRegistration.model_validate_json(
                registration_path.read_text(encoding="utf-8")
            )
            self.assertLessEqual(registration.registered_at, family_plan.frozen_at)
            self.assertEqual(
                registration.dataset_snapshot_sha256,
                dataset["dataset_sha256"],
            )
            self.assertEqual(registration.planned_primary_trials, attack_input.trials)
            self.assertEqual(
                registration.planned_control_trials,
                attack_input.nonmember_trials,
            )

            event_types = tuple(event.event_type for event in protocol.events)
            self.assertEqual(
                event_types,
                (
                    ReleaseProtocolEventType.REGISTER_SCOPE,
                    ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN,
                    ReleaseProtocolEventType.CLOSE_EVIDENCE,
                    ReleaseProtocolEventType.RECORD_ASSESSMENT,
                ),
            )
            self.assertEqual(protocol.claimed_state, ReleaseProtocolState.ASSESSED)
            self.assertEqual(workflow["final_state"], "assessed")
            self.assertFalse(workflow["optimization_executed"])
            self.assertFalse(workflow["authorization_issued"])
            self.assertFalse(workflow["deployment_active"])
            self.assertFalse(assessment.assessment_scope.authorization_eligible)
            self.assertIn(
                assessment.overall_verdict,
                (OverallVerdict.INCONCLUSIVE, OverallVerdict.BLOCK),
            )
            self.assertEqual(
                protocol.events[-1].assessment_verdict,
                assessment.overall_verdict,
            )
            self.assertNotIn(OverallVerdict.CLEAR, {assessment.overall_verdict})
            self.assertTrue(all(not evidence.can_clear for evidence in assessment.evidence))

            replay = verify_release_protocol_run(
                protocol,
                protocol_path.parent,
                verify_artifact_files=True,
                as_of=protocol.events[-1].occurred_at + timedelta(seconds=1),
            )
            self.assertTrue(replay.valid, replay.reasons)
            self.assertTrue(replay.artifact_files_verified)
            self.assertEqual(replay.final_state, ReleaseProtocolState.ASSESSED)
            self.assertFalse(replay.authorization_issued)
            self.assertFalse(replay.deployment_active)
            self.assertTrue(workflow["valid"])

            for record in _artifact_records(report):
                artifact_path = (run_dir / record["path"]).resolve(strict=True)
                self.assertTrue(artifact_path.is_relative_to(run_dir.resolve()))
                self.assertEqual(record["sha256"], sha256_file(artifact_path))

            guide = guide_path.read_text(encoding="utf-8")
            self.assertIn("ACTUAL MODEL TRAINED", guide.upper())
            self.assertIn("DO NOT RELEASE", guide.upper())
            self.assertIn("XGBOOST", guide.upper())
            self.assertIn("CLINIC", guide.upper())

            # The core verifier must reject changed candidate bytes. If the
            # demo exposes a bundle-level verifier, exercise that as well.
            helper = getattr(self.module, "verify_pipeline_bindings", None)
            if helper is not None:
                self.assertTrue(_verification_is_valid(helper(run_dir)))
            original_bundle = release_bundle.read_bytes()
            try:
                release_bundle.write_bytes(original_bundle + b"tampered")
                with self.assertRaises(IntegrityError):
                    verify_release_artifact(release, run_dir)
                if helper is not None:
                    try:
                        tampered = helper(run_dir)
                    except (IntegrityError, ValueError):
                        pass
                    else:
                        self.assertFalse(_verification_is_valid(tampered))
            finally:
                release_bundle.write_bytes(original_bundle)

            # The CLI is an operator entry point into this same executable path,
            # not a separate fixture-only mock.
            cli_output_root = Path(directory_name) / "cli-output"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--dataset-profile",
                    "sklearn-breast-cancer",
                    "--output-root",
                    str(cli_output_root),
                    "--run-id",
                    "cli-run",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertEqual(sha256_file(release_bundle), release_bundle_sha256)
            cli_report = json.loads(
                (cli_output_root / "cli-run" / "pipeline-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(cli_report["training_executed"])
            self.assertFalse(cli_report["production_authorization_issued"])
            self.assertFalse(cli_report["production_deployment_active"])


if __name__ == "__main__":
    unittest.main()
