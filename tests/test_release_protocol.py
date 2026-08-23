from __future__ import annotations

import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from model_release_assurance.cli import main as cli_main
from model_release_assurance.models import OverallVerdict
from model_release_assurance.optimizer import OptimizationOutcome
from model_release_assurance.release_protocol import (
    ControlStatus,
    MonitoringOutcome,
    ReleaseProtocolActor,
    ReleaseProtocolArtifact,
    ReleaseProtocolArtifactKind,
    ReleaseProtocolEvent,
    ReleaseProtocolEventType,
    ReleaseProtocolRole,
    ReleaseProtocolRun,
    ReleaseProtocolState,
    release_protocol_event_sha256,
    verify_release_protocol_run,
)


def _digest(number: int) -> str:
    return f"{number:064x}"


class ReleaseProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_time = datetime(2026, 8, 23, 1, 0, tzinfo=timezone.utc)
        self.actor_ids = {
            role: f"actor:{role.value}" for role in ReleaseProtocolRole
        }
        self.actors = tuple(
            ReleaseProtocolActor(
                actor_id=self.actor_ids[role],
                role=role,
                organization=f"organization:{role.value}",
                key_id=f"key:{role.value}",
            )
            for role in ReleaseProtocolRole
        )
        self.artifact_counter = 100

    def artifact(
        self,
        kind: ReleaseProtocolArtifactKind,
        producer_role: ReleaseProtocolRole,
        *,
        sha256: str | None = None,
    ) -> ReleaseProtocolArtifact:
        self.artifact_counter += 1
        return ReleaseProtocolArtifact(
            artifact_id=f"artifact:{self.artifact_counter}",
            kind=kind,
            path=f"artifact-{self.artifact_counter}.json",
            sha256=sha256 or _digest(self.artifact_counter),
            producer_actor_id=self.actor_ids[producer_role],
        )

    def happy_run(
        self,
        *,
        claimed_state: ReleaseProtocolState = ReleaseProtocolState.ACTIVE,
    ) -> ReleaseProtocolRun:
        events: list[ReleaseProtocolEvent] = []

        def add(
            event_type: ReleaseProtocolEventType,
            role: ReleaseProtocolRole,
            artifacts: tuple[ReleaseProtocolArtifact, ...],
            **values: object,
        ) -> None:
            sequence = len(events) + 1
            previous = release_protocol_event_sha256(events[-1]) if events else None
            events.append(
                ReleaseProtocolEvent(
                    sequence=sequence,
                    event_id=f"event:{sequence}",
                    event_type=event_type,
                    occurred_at=self.base_time + timedelta(minutes=sequence),
                    actor_id=self.actor_ids[role],
                    actor_role=role,
                    previous_event_sha256=previous,
                    artifacts=artifacts,
                    **values,
                )
            )

        add(
            ReleaseProtocolEventType.REGISTER_SCOPE,
            ReleaseProtocolRole.MODEL_OWNER,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.REGISTRATION,
                    ReleaseProtocolRole.MODEL_OWNER,
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.POLICY_SNAPSHOT,
                    ReleaseProtocolRole.POLICY_AUTHORITY,
                    sha256=_digest(4),
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.RELEASE_INSTANCE,
                    ReleaseProtocolRole.CONFIGURATION_GENERATOR,
                    sha256=_digest(1),
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.POPULATION_REGISTER,
                    ReleaseProtocolRole.POPULATION_STEWARD,
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.THREAT_REGISTER,
                    ReleaseProtocolRole.POLICY_AUTHORITY,
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.PORTFOLIO_SNAPSHOT,
                    ReleaseProtocolRole.PORTFOLIO_REGISTRY,
                ),
            ),
        )
        add(
            ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN,
            ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.EVIDENCE_PLAN,
                    ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.ASSURANCE_ERROR_BUDGET,
                    ReleaseProtocolRole.POLICY_AUTHORITY,
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.MONITORING_PLAN,
                    ReleaseProtocolRole.MONITORING_AUTHORITY,
                ),
            ),
            assurance_alpha_budget="0.05",
        )
        add(
            ReleaseProtocolEventType.CLOSE_EVIDENCE,
            ReleaseProtocolRole.EVIDENCE_AUTHORITY,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.EVIDENCE_BUNDLE,
                    ReleaseProtocolRole.EVIDENCE_AUTHORITY,
                ),
            ),
            mandatory_evidence_complete=True,
            selection_coverage_valid=True,
            positive_control_status=ControlStatus.PASS,
            assurance_alpha_spent="0.04",
        )
        add(
            ReleaseProtocolEventType.RECORD_ASSESSMENT,
            ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.ASSESSMENT_REPORT,
                    ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
                ),
            ),
            assessment_verdict=OverallVerdict.CLEAR,
        )
        add(
            ReleaseProtocolEventType.RECORD_SELECTION,
            ReleaseProtocolRole.OPTIMIZATION_AUTHORITY,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.OPTIMIZATION_REPORT,
                    ReleaseProtocolRole.OPTIMIZATION_AUTHORITY,
                ),
            ),
            optimization_outcome=OptimizationOutcome.RELEASE_WITH_CONTROLS,
            selected_configuration_id="configuration:bounded-api",
        )
        add(
            ReleaseProtocolEventType.SUBMIT_AUTHORIZATION,
            ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.AUTHORIZATION_COMMIT_REQUEST,
                    ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
                ),
            ),
            authorization_expires_at=self.base_time + timedelta(days=1),
        )
        add(
            ReleaseProtocolEventType.COMMIT_PORTFOLIO,
            ReleaseProtocolRole.PORTFOLIO_REGISTRY,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.AUTHORIZATION_RECEIPT,
                    ReleaseProtocolRole.PORTFOLIO_REGISTRY,
                ),
                self.artifact(
                    ReleaseProtocolArtifactKind.PORTFOLIO_COMMIT,
                    ReleaseProtocolRole.PORTFOLIO_REGISTRY,
                ),
            ),
            expected_registry_head_sha256=_digest(5),
            committed_registry_head_sha256=_digest(6),
            atomic_compare_and_swap_succeeded=True,
        )
        add(
            ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT,
            ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
            (
                self.artifact(
                    ReleaseProtocolArtifactKind.ACTIVATION_RECEIPT,
                    ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
                ),
            ),
            deployed_artifact_sha256=_digest(2),
            deployed_interface_sha256=_digest(3),
        )
        return ReleaseProtocolRun(
            protocol_id="MRAP/1.0",
            release_id="release:example",
            release_instance_sha256=_digest(1),
            artifact_sha256=_digest(2),
            interface_sha256=_digest(3),
            policy_sha256=_digest(4),
            population_scope_sha256s={"people": _digest(7)},
            registered_portfolio_head_sha256=_digest(5),
            actors=self.actors,
            events=tuple(events),
            claimed_state=claimed_state,
        )

    def replay(self, run: ReleaseProtocolRun):
        return verify_release_protocol_run(
            run,
            Path("."),
            verify_artifact_files=False,
            as_of=self.base_time + timedelta(minutes=10),
        )

    def test_complete_lifecycle_reaches_active(self) -> None:
        verification = self.replay(self.happy_run())
        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(verification.final_state, ReleaseProtocolState.ACTIVE)
        self.assertTrue(verification.authorization_issued)
        self.assertTrue(verification.deployment_active)

    def test_cli_structurally_replays_a_complete_transcript(self) -> None:
        run = self.happy_run()
        with TemporaryDirectory() as directory:
            transcript = Path(directory) / "release-protocol-run.json"
            transcript.write_text(run.model_dump_json(indent=2), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "release-protocol-verify",
                        str(transcript),
                        "--skip-artifact-files",
                        "--as-of",
                        (self.base_time + timedelta(minutes=10)).isoformat(),
                    ]
                )
        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn("structurally_verified state=active", stdout.getvalue())
        self.assertIn("does not authenticate actors", stdout.getvalue())

    def test_failed_atomic_commit_cannot_authorize_or_activate(self) -> None:
        run = self.happy_run()
        events = list(run.events)
        events[6] = events[6].model_copy(
            update={"atomic_compare_and_swap_succeeded": False}
        )
        failed = run.model_copy(update={"events": tuple(events)})
        verification = self.replay(failed)
        self.assertFalse(verification.valid)
        self.assertEqual(verification.final_state, ReleaseProtocolState.COMMIT_PENDING)
        self.assertFalse(verification.authorization_issued)
        self.assertFalse(verification.deployment_active)

    def test_current_status_replay_rejects_an_expired_active_claim(self) -> None:
        run = self.happy_run()
        verification = verify_release_protocol_run(
            run,
            Path("."),
            verify_artifact_files=False,
            as_of=self.base_time + timedelta(days=2),
        )
        self.assertFalse(verification.valid)
        self.assertFalse(verification.deployment_active)
        self.assertTrue(any("expired authorization" in reason for reason in verification.reasons))

    def test_incomplete_evidence_cannot_progress(self) -> None:
        run = self.happy_run()
        events = list(run.events)
        events[2] = events[2].model_copy(update={"mandatory_evidence_complete": False})
        failed = run.model_copy(update={"events": tuple(events)})
        verification = self.replay(failed)
        self.assertFalse(verification.valid)
        self.assertEqual(verification.final_state, ReleaseProtocolState.EVIDENCE_FROZEN)
        self.assertFalse(verification.authorization_issued)

    def test_hash_chain_tampering_is_detected(self) -> None:
        run = self.happy_run()
        events = list(run.events)
        events[4] = events[4].model_copy(update={"previous_event_sha256": _digest(999)})
        verification = self.replay(run.model_copy(update={"events": tuple(events)}))
        self.assertFalse(verification.valid)
        self.assertTrue(any("hash chain" in reason for reason in verification.reasons))

    def test_wrong_artifact_producer_role_is_detected(self) -> None:
        run = self.happy_run()
        events = list(run.events)
        registration_artifacts = list(events[0].artifacts)
        registration_artifacts[1] = registration_artifacts[1].model_copy(
            update={"producer_actor_id": self.actor_ids[ReleaseProtocolRole.MODEL_OWNER]}
        )
        events[0] = events[0].model_copy(update={"artifacts": tuple(registration_artifacts)})
        verification = self.replay(run.model_copy(update={"events": tuple(events)}))
        self.assertFalse(verification.valid)
        self.assertEqual(verification.final_state, ReleaseProtocolState.DRAFT)
        self.assertTrue(any("cannot be produced" in reason for reason in verification.reasons))

    def test_monitoring_can_suspend_an_active_release(self) -> None:
        active = self.happy_run()
        event = ReleaseProtocolEvent(
            sequence=9,
            event_id="event:9",
            event_type=ReleaseProtocolEventType.REVIEW_MONITORING,
            occurred_at=self.base_time + timedelta(minutes=9),
            actor_id=self.actor_ids[ReleaseProtocolRole.MONITORING_AUTHORITY],
            actor_role=ReleaseProtocolRole.MONITORING_AUTHORITY,
            previous_event_sha256=release_protocol_event_sha256(active.events[-1]),
            artifacts=(
                self.artifact(
                    ReleaseProtocolArtifactKind.MONITORING_REPORT,
                    ReleaseProtocolRole.MONITORING_AUTHORITY,
                ),
            ),
            monitoring_outcome=MonitoringOutcome.SUSPEND,
        )
        suspended = active.model_copy(
            update={
                "events": active.events + (event,),
                "claimed_state": ReleaseProtocolState.SUSPENDED,
            }
        )
        verification = self.replay(suspended)
        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(verification.final_state, ReleaseProtocolState.SUSPENDED)
        self.assertFalse(verification.deployment_active)

    def test_all_protocol_roles_are_required(self) -> None:
        run = self.happy_run()
        with self.assertRaises(ValidationError):
            ReleaseProtocolRun.model_validate(
                {
                    **run.model_dump(mode="json"),
                    "actors": run.model_dump(mode="json")["actors"][:-1],
                }
            )

    def test_protocol_artifacts_cannot_escape_the_declared_bundle(self) -> None:
        with self.assertRaises(ValidationError):
            ReleaseProtocolArtifact(
                artifact_id="artifact:escape",
                kind=ReleaseProtocolArtifactKind.EVIDENCE_BUNDLE,
                path="../outside.json",
                sha256=_digest(10),
                producer_actor_id=self.actor_ids[ReleaseProtocolRole.EVIDENCE_AUTHORITY],
            )

    def test_event_rejects_payload_fields_from_another_message_type(self) -> None:
        with self.assertRaises(ValidationError):
            ReleaseProtocolEvent(
                sequence=1,
                event_id="event:ambiguous",
                event_type=ReleaseProtocolEventType.REGISTER_SCOPE,
                occurred_at=self.base_time,
                actor_id=self.actor_ids[ReleaseProtocolRole.MODEL_OWNER],
                actor_role=ReleaseProtocolRole.MODEL_OWNER,
                monitoring_outcome=MonitoringOutcome.CONTINUE,
            )

    def test_registered_instance_can_abort_with_a_retained_record(self) -> None:
        run = self.happy_run()
        registration = run.events[0]
        abort = ReleaseProtocolEvent(
            sequence=2,
            event_id="event:abort",
            event_type=ReleaseProtocolEventType.ABORT_RELEASE,
            occurred_at=self.base_time + timedelta(minutes=2),
            actor_id=self.actor_ids[ReleaseProtocolRole.MODEL_OWNER],
            actor_role=ReleaseProtocolRole.MODEL_OWNER,
            previous_event_sha256=release_protocol_event_sha256(registration),
            artifacts=(
                self.artifact(
                    ReleaseProtocolArtifactKind.ABORT_RECORD,
                    ReleaseProtocolRole.MODEL_OWNER,
                ),
            ),
            reason="submission withdrawn before evidence collection",
        )
        aborted = run.model_copy(
            update={
                "events": (registration, abort),
                "claimed_state": ReleaseProtocolState.ABORTED,
            }
        )
        verification = self.replay(aborted)
        self.assertTrue(verification.valid, verification.reasons)
        self.assertEqual(verification.final_state, ReleaseProtocolState.ABORTED)

    def test_reject_requires_exhaustive_search_replay(self) -> None:
        run = self.happy_run()
        events = list(run.events[:5])
        events[4] = events[4].model_copy(
            update={
                "optimization_outcome": OptimizationOutcome.REJECT,
                "selected_configuration_id": None,
                "exhaustive_search_replayed": False,
            }
        )
        rejected = run.model_copy(
            update={
                "events": tuple(events),
                "claimed_state": ReleaseProtocolState.REJECTED,
            }
        )
        verification = self.replay(rejected)
        self.assertFalse(verification.valid)
        self.assertEqual(verification.final_state, ReleaseProtocolState.ASSESSED)
        self.assertTrue(any("exhaustive search" in reason for reason in verification.reasons))


if __name__ == "__main__":
    unittest.main()
