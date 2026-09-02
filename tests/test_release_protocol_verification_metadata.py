from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives import serialization

from model_release_assurance.integrity import (
    canonical_json_bytes,
    generate_ed25519_keypair,
    sha256_bytes,
    sha256_file,
    signer_key_id,
)
from model_release_assurance.release_protocol import (
    ReleaseProtocolActor,
    ReleaseProtocolArtifact,
    ReleaseProtocolArtifactKind,
    ReleaseProtocolEvent,
    ReleaseProtocolEventType,
    ReleaseProtocolRole,
    ReleaseProtocolRun,
    ReleaseProtocolState,
    ReleaseProtocolVerificationCheck,
    ReleaseProtocolVerificationDegradation,
    ReleaseProtocolVerificationProfile,
    sign_release_protocol_artifact,
    sign_release_protocol_event,
    verify_release_protocol_run,
)


def _digest(number: int) -> str:
    return f"{number:064x}"


class ReleaseProtocolVerificationMetadataTests(unittest.TestCase):
    verification_time = datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc)

    def build_registered_run(
        self,
        base_dir: Path,
        profile: ReleaseProtocolVerificationProfile,
    ) -> tuple[ReleaseProtocolRun, dict[str, Path], dict[str, Path]]:
        actor_ids = {role: f"actor:{role.value}" for role in ReleaseProtocolRole}
        private_keys: dict[str, Path] = {}
        trust_store: dict[str, Path] = {}
        actors: list[ReleaseProtocolActor] = []
        for index, role in enumerate(ReleaseProtocolRole):
            if profile is ReleaseProtocolVerificationProfile.AUTHENTICATED:
                private_path = base_dir / f"actor-{index}.private.pem"
                public_path = base_dir / f"actor-{index}.public.pem"
                generate_ed25519_keypair(private_path, public_path)
                public_key = serialization.load_pem_public_key(public_path.read_bytes())
                key_id = signer_key_id(public_key)
                private_keys[actor_ids[role]] = private_path
                trust_store[key_id] = public_path
            else:
                key_id = f"key:{role.value}"
            actors.append(
                ReleaseProtocolActor(
                    actor_id=actor_ids[role],
                    role=role,
                    organization=f"organization:{role.value}",
                    key_id=key_id,
                )
            )

        specifications = (
            (ReleaseProtocolArtifactKind.REGISTRATION, ReleaseProtocolRole.MODEL_OWNER),
            (ReleaseProtocolArtifactKind.POLICY_SNAPSHOT, ReleaseProtocolRole.POLICY_AUTHORITY),
            (ReleaseProtocolArtifactKind.RELEASE_INSTANCE, ReleaseProtocolRole.CONFIGURATION_GENERATOR),
            (ReleaseProtocolArtifactKind.POPULATION_REGISTER, ReleaseProtocolRole.POPULATION_STEWARD),
            (ReleaseProtocolArtifactKind.THREAT_REGISTER, ReleaseProtocolRole.POLICY_AUTHORITY),
            (ReleaseProtocolArtifactKind.PORTFOLIO_SNAPSHOT, ReleaseProtocolRole.PORTFOLIO_REGISTRY),
        )
        artifacts: list[ReleaseProtocolArtifact] = []
        for index, (kind, producer_role) in enumerate(specifications, start=1):
            path = base_dir / f"artifact-{index}.json"
            path.write_text(f'{{"artifact":{index}}}\n', encoding="utf-8")
            artifacts.append(
                ReleaseProtocolArtifact(
                    artifact_id=f"artifact:{index}",
                    kind=kind,
                    path=path.name,
                    sha256=sha256_file(path),
                    producer_actor_id=actor_ids[producer_role],
                )
            )

        event = ReleaseProtocolEvent(
            sequence=1,
            event_id="event:register",
            event_type=ReleaseProtocolEventType.REGISTER_SCOPE,
            occurred_at=self.verification_time - timedelta(hours=1),
            actor_id=actor_ids[ReleaseProtocolRole.MODEL_OWNER],
            actor_role=ReleaseProtocolRole.MODEL_OWNER,
            artifacts=tuple(artifacts),
        )
        run = ReleaseProtocolRun(
            verification_profile=profile,
            release_id="release:verification-metadata",
            release_instance_sha256=artifacts[2].sha256,
            artifact_sha256=_digest(20),
            interface_sha256=_digest(21),
            policy_sha256=artifacts[1].sha256,
            population_scope_sha256s={"people": _digest(22)},
            registered_portfolio_head_sha256=_digest(23),
            registered_portfolio_sequence=1,
            actors=tuple(actors),
            events=(event,),
            claimed_state=ReleaseProtocolState.REGISTERED,
        )

        if profile is ReleaseProtocolVerificationProfile.AUTHENTICATED:
            signed_artifacts = tuple(
                sign_release_protocol_artifact(
                    run,
                    event,
                    artifact,
                    private_keys[artifact.producer_actor_id],
                )
                for artifact in event.artifacts
            )
            event_with_artifacts = event.model_copy(update={"artifacts": signed_artifacts})
            signed_event = sign_release_protocol_event(
                run,
                event_with_artifacts,
                private_keys[event.actor_id],
            )
            run = run.model_copy(update={"events": (signed_event,)})
        return run, private_keys, trust_store

    def test_structural_skip_scope_is_embedded_in_result(self) -> None:
        with TemporaryDirectory() as directory:
            base_dir = Path(directory)
            run, _private_keys, _trust_store = self.build_registered_run(
                base_dir, ReleaseProtocolVerificationProfile.STRUCTURAL
            )
            result = verify_release_protocol_run(
                run,
                base_dir,
                verify_artifact_files=False,
                as_of=self.verification_time,
            )

        self.assertTrue(result.valid, result.reasons)
        self.assertEqual(run.schema_version, "1.1")
        self.assertEqual(result.schema_version, "2.0")
        self.assertEqual(
            result.verification_profile,
            ReleaseProtocolVerificationProfile.STRUCTURAL,
        )
        self.assertFalse(result.artifact_files_verified)
        self.assertFalse(result.authenticated_signatures_verified)
        self.assertEqual(result.verification_time, self.verification_time)
        self.assertEqual(result.run_sha256, sha256_bytes(canonical_json_bytes(run)))
        self.assertEqual(
            result.runtime_identity.component_id,
            "release_protocol_verifier",
        )
        self.assertEqual(len(result.runtime_identity.package_source_sha256), 64)
        self.assertEqual(
            result.skipped_checks,
            frozenset({
                ReleaseProtocolVerificationCheck.ARTIFACT_FILE_DIGESTS,
                ReleaseProtocolVerificationCheck.AUTHENTICATED_SIGNATURES,
            }),
        )
        self.assertEqual(
            result.degradations,
            frozenset({
                ReleaseProtocolVerificationDegradation.ARTIFACT_FILE_VERIFICATION_SKIPPED,
                ReleaseProtocolVerificationDegradation.STRUCTURAL_PROFILE_ONLY,
            }),
        )

    def test_checked_artifact_failure_is_not_reported_as_a_skip(self) -> None:
        with TemporaryDirectory() as directory:
            base_dir = Path(directory)
            run, _private_keys, _trust_store = self.build_registered_run(
                base_dir, ReleaseProtocolVerificationProfile.STRUCTURAL
            )
            (base_dir / run.events[0].artifacts[0].path).unlink()
            result = verify_release_protocol_run(
                run,
                base_dir,
                verify_artifact_files=True,
                as_of=self.verification_time,
            )

        self.assertFalse(result.valid)
        self.assertFalse(result.artifact_files_verified)
        self.assertNotIn(
            ReleaseProtocolVerificationCheck.ARTIFACT_FILE_DIGESTS,
            result.skipped_checks,
        )
        self.assertNotIn(
            ReleaseProtocolVerificationDegradation.ARTIFACT_FILE_VERIFICATION_SKIPPED,
            result.degradations,
        )

    def test_authenticated_result_records_full_verification(self) -> None:
        with TemporaryDirectory() as directory:
            base_dir = Path(directory)
            run, _private_keys, trust_store = self.build_registered_run(
                base_dir, ReleaseProtocolVerificationProfile.AUTHENTICATED
            )
            result = verify_release_protocol_run(
                run,
                base_dir,
                verify_artifact_files=True,
                as_of=self.verification_time,
                trusted_public_keys=trust_store,
            )

        self.assertTrue(result.valid, result.reasons)
        self.assertTrue(result.artifact_files_verified)
        self.assertTrue(result.authenticated_signatures_verified)
        self.assertEqual(result.skipped_checks, frozenset())
        self.assertEqual(result.degradations, frozenset())

    def test_cli_machine_output_records_degraded_scope(self) -> None:
        with TemporaryDirectory() as directory:
            base_dir = Path(directory)
            run, _private_keys, _trust_store = self.build_registered_run(
                base_dir, ReleaseProtocolVerificationProfile.STRUCTURAL
            )
            transcript = base_dir / "run.json"
            output = base_dir / "verification.json"
            transcript.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "model_release_assurance",
                    "release-protocol-verify",
                    str(transcript),
                    "--skip-artifact-files",
                    "--as-of",
                    self.verification_time.isoformat(),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["verification_profile"], "structural_v1")
            self.assertEqual(
                payload["runtime_identity"]["component_id"],
                "release_protocol_verifier",
            )
            self.assertIn("artifact_file_digests", payload["skipped_checks"])
            self.assertIn("authenticated_signatures", payload["skipped_checks"])
            self.assertIn("structural_profile_only", payload["degradations"])


if __name__ == "__main__":
    unittest.main()
