"""Normative model-release lifecycle transcript and structural verifier.

The finite protocol-feasibility solver answers whether a declared family of
evidence laws can support a sound and live gate.  This module answers a
different question: whether one concrete release followed the mandatory
end-to-end lifecycle from registration through evidence, assessment,
authorization, atomic portfolio commit, deployment, monitoring, and terminal
action.

The verifier checks typed state transitions, hash chaining, role separation,
artifact digests, and fail-closed authorization preconditions.  It does not
authenticate actors or prove that referenced evidence is scientifically true;
production must verify signatures and identities in separately protected
services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .errors import IntegrityError
from .integrity import canonical_json_bytes, sha256_bytes, verify_source_file
from .models import OverallVerdict, StrictModel
from .optimizer import OptimizationOutcome


class ReleaseProtocolRole(StrEnum):
    MODEL_OWNER = "model_owner"
    POLICY_AUTHORITY = "policy_authority"
    POPULATION_STEWARD = "population_steward"
    CONFIGURATION_GENERATOR = "configuration_generator"
    EVIDENCE_AUTHORITY = "evidence_authority"
    INDEPENDENT_ASSESSOR = "independent_assessor"
    OPTIMIZATION_AUTHORITY = "optimization_authority"
    AUTHORIZATION_AUTHORITY = "authorization_authority"
    PORTFOLIO_REGISTRY = "portfolio_registry"
    DEPLOYMENT_GATEWAY = "deployment_gateway"
    MONITORING_AUTHORITY = "monitoring_authority"
    INCIDENT_AUTHORITY = "incident_authority"


class ReleaseProtocolState(StrEnum):
    DRAFT = "draft"
    REGISTERED = "registered"
    PLAN_FROZEN = "plan_frozen"
    EVIDENCE_FROZEN = "evidence_frozen"
    ASSESSED = "assessed"
    OPTIMIZED = "optimized"
    COMMIT_PENDING = "commit_pending"
    AUTHORIZED = "authorized"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"
    REDESIGN_REQUIRED = "redesign_required"
    REJECTED = "rejected"
    ABORTED = "aborted"


class ReleaseProtocolEventType(StrEnum):
    REGISTER_SCOPE = "register_scope"
    APPROVE_EVIDENCE_PLAN = "approve_evidence_plan"
    CLOSE_EVIDENCE = "close_evidence"
    RECORD_ASSESSMENT = "record_assessment"
    RECORD_SELECTION = "record_selection"
    SUBMIT_AUTHORIZATION = "submit_authorization"
    COMMIT_PORTFOLIO = "commit_portfolio"
    ACTIVATE_DEPLOYMENT = "activate_deployment"
    REVIEW_MONITORING = "review_monitoring"
    SUSPEND_RELEASE = "suspend_release"
    REVOKE_RELEASE = "revoke_release"
    EXPIRE_RELEASE = "expire_release"
    ABORT_RELEASE = "abort_release"


class ReleaseProtocolArtifactKind(StrEnum):
    REGISTRATION = "registration"
    POLICY_SNAPSHOT = "policy_snapshot"
    RELEASE_INSTANCE = "release_instance"
    POPULATION_REGISTER = "population_register"
    THREAT_REGISTER = "threat_register"
    PORTFOLIO_SNAPSHOT = "portfolio_snapshot"
    EVIDENCE_PLAN = "evidence_plan"
    ASSURANCE_ERROR_BUDGET = "assurance_error_budget"
    MONITORING_PLAN = "monitoring_plan"
    EVIDENCE_BUNDLE = "evidence_bundle"
    ASSESSMENT_REPORT = "assessment_report"
    OPTIMIZATION_REPORT = "optimization_report"
    AUTHORIZATION_COMMIT_REQUEST = "authorization_commit_request"
    AUTHORIZATION_RECEIPT = "authorization_receipt"
    PORTFOLIO_COMMIT = "portfolio_commit"
    ACTIVATION_RECEIPT = "activation_receipt"
    MONITORING_REPORT = "monitoring_report"
    INCIDENT_RECORD = "incident_record"
    DECOMMISSION_RECORD = "decommission_record"
    ABORT_RECORD = "abort_record"


class ControlStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class MonitoringOutcome(StrEnum):
    CONTINUE = "continue"
    SUSPEND = "suspend"
    REVOKE = "revoke"
    EXPIRE = "expire"


class ReleaseProtocolActor(StrictModel):
    actor_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    role: ReleaseProtocolRole
    organization: str = Field(min_length=1, max_length=256)
    key_id: str = Field(min_length=1, max_length=256)


class ReleaseProtocolArtifact(StrictModel):
    artifact_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: ReleaseProtocolArtifactKind
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_actor_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")

    @model_validator(mode="after")
    def path_is_confined_to_the_protocol_bundle(self) -> ReleaseProtocolArtifact:
        candidate = Path(self.path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("protocol artifact paths must be relative and cannot traverse parents")
        return self


class ReleaseProtocolEvent(StrictModel):
    sequence: int = Field(ge=1)
    event_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    event_type: ReleaseProtocolEventType
    occurred_at: datetime
    actor_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    actor_role: ReleaseProtocolRole
    previous_event_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[ReleaseProtocolArtifact, ...] = ()

    mandatory_evidence_complete: bool | None = None
    selection_coverage_valid: bool | None = None
    positive_control_status: ControlStatus | None = None
    assurance_alpha_budget: Decimal | None = Field(default=None, ge=0, le=1)
    assurance_alpha_spent: Decimal | None = Field(default=None, ge=0, le=1)

    assessment_verdict: OverallVerdict | None = None
    optimization_outcome: OptimizationOutcome | None = None
    selected_configuration_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    exhaustive_search_replayed: bool | None = None

    authorization_expires_at: datetime | None = None
    expected_registry_head_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    committed_registry_head_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    atomic_compare_and_swap_succeeded: bool | None = None
    deployed_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    deployed_interface_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    monitoring_outcome: MonitoringOutcome | None = None
    reason: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def event_is_structurally_valid(self) -> ReleaseProtocolEvent:
        if self.occurred_at.utcoffset() is None:
            raise ValueError("protocol event occurred_at must include a timezone offset")
        if self.authorization_expires_at is not None:
            if self.authorization_expires_at.utcoffset() is None:
                raise ValueError("authorization expiry must include a timezone offset")
            if self.authorization_expires_at <= self.occurred_at:
                raise ValueError("authorization expiry must follow its issue event")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("event artifact identifiers must be unique")

        payload_fields = {
            "mandatory_evidence_complete",
            "selection_coverage_valid",
            "positive_control_status",
            "assurance_alpha_budget",
            "assurance_alpha_spent",
            "assessment_verdict",
            "optimization_outcome",
            "selected_configuration_id",
            "exhaustive_search_replayed",
            "authorization_expires_at",
            "expected_registry_head_sha256",
            "committed_registry_head_sha256",
            "atomic_compare_and_swap_succeeded",
            "deployed_artifact_sha256",
            "deployed_interface_sha256",
            "monitoring_outcome",
            "reason",
        }
        allowed_fields = {
            ReleaseProtocolEventType.REGISTER_SCOPE: set(),
            ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN: {"assurance_alpha_budget"},
            ReleaseProtocolEventType.CLOSE_EVIDENCE: {
                "mandatory_evidence_complete",
                "selection_coverage_valid",
                "positive_control_status",
                "assurance_alpha_spent",
            },
            ReleaseProtocolEventType.RECORD_ASSESSMENT: {"assessment_verdict"},
            ReleaseProtocolEventType.RECORD_SELECTION: {
                "optimization_outcome",
                "selected_configuration_id",
                "exhaustive_search_replayed",
            },
            ReleaseProtocolEventType.SUBMIT_AUTHORIZATION: {"authorization_expires_at"},
            ReleaseProtocolEventType.COMMIT_PORTFOLIO: {
                "expected_registry_head_sha256",
                "committed_registry_head_sha256",
                "atomic_compare_and_swap_succeeded",
            },
            ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT: {
                "deployed_artifact_sha256",
                "deployed_interface_sha256",
            },
            ReleaseProtocolEventType.REVIEW_MONITORING: {"monitoring_outcome"},
            ReleaseProtocolEventType.SUSPEND_RELEASE: {"reason"},
            ReleaseProtocolEventType.REVOKE_RELEASE: {"reason"},
            ReleaseProtocolEventType.EXPIRE_RELEASE: set(),
            ReleaseProtocolEventType.ABORT_RELEASE: {"reason"},
        }[self.event_type]
        populated_fields = {
            field
            for field in payload_fields
            if (value := getattr(self, field)) is not None and value != ""
        }
        forbidden_fields = populated_fields - allowed_fields
        if forbidden_fields:
            raise ValueError(
                f"event {self.event_type.value} contains fields for another event type: "
                f"{sorted(forbidden_fields)}"
            )
        return self


class ReleaseProtocolRun(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    protocol_id: Literal["MRAP/1.0"] = "MRAP/1.0"
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    release_instance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    population_scope_sha256s: dict[str, str] = Field(min_length=1)
    registered_portfolio_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actors: tuple[ReleaseProtocolActor, ...]
    events: tuple[ReleaseProtocolEvent, ...] = Field(min_length=1)
    claimed_state: ReleaseProtocolState

    @model_validator(mode="after")
    def run_identifiers_are_unique(self) -> ReleaseProtocolRun:
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in self.population_scope_sha256s.values()
        ):
            raise ValueError("population-scope values must be lowercase SHA-256 digests")
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("protocol actor identifiers must be unique")
        missing_roles = set(ReleaseProtocolRole) - {actor.role for actor in self.actors}
        if missing_roles:
            raise ValueError(
                "protocol run omits required roles: "
                f"{sorted(role.value for role in missing_roles)}"
            )
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("protocol event identifiers must be unique")
        if tuple(event.sequence for event in self.events) != tuple(range(1, len(self.events) + 1)):
            raise ValueError("protocol event sequence must be contiguous and start at one")
        if self.events[0].event_type is not ReleaseProtocolEventType.REGISTER_SCOPE:
            raise ValueError("the first protocol event must register the immutable release scope")
        artifact_ids = [
            artifact.artifact_id
            for event in self.events
            for artifact in event.artifacts
        ]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact identifiers must be unique across the protocol run")
        return self


class ReleaseProtocolVerification(StrictModel):
    valid: bool
    final_state: ReleaseProtocolState
    authorization_issued: bool
    deployment_active: bool
    event_sha256s: tuple[str, ...]
    reasons: tuple[str, ...]


_EVENT_ROLES: dict[ReleaseProtocolEventType, frozenset[ReleaseProtocolRole]] = {
    ReleaseProtocolEventType.REGISTER_SCOPE: frozenset({ReleaseProtocolRole.MODEL_OWNER}),
    ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN: frozenset({ReleaseProtocolRole.INDEPENDENT_ASSESSOR}),
    ReleaseProtocolEventType.CLOSE_EVIDENCE: frozenset({ReleaseProtocolRole.EVIDENCE_AUTHORITY}),
    ReleaseProtocolEventType.RECORD_ASSESSMENT: frozenset({ReleaseProtocolRole.INDEPENDENT_ASSESSOR}),
    ReleaseProtocolEventType.RECORD_SELECTION: frozenset({ReleaseProtocolRole.OPTIMIZATION_AUTHORITY}),
    ReleaseProtocolEventType.SUBMIT_AUTHORIZATION: frozenset({ReleaseProtocolRole.AUTHORIZATION_AUTHORITY}),
    ReleaseProtocolEventType.COMMIT_PORTFOLIO: frozenset({ReleaseProtocolRole.PORTFOLIO_REGISTRY}),
    ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT: frozenset({ReleaseProtocolRole.DEPLOYMENT_GATEWAY}),
    ReleaseProtocolEventType.REVIEW_MONITORING: frozenset({ReleaseProtocolRole.MONITORING_AUTHORITY}),
    ReleaseProtocolEventType.SUSPEND_RELEASE: frozenset({
        ReleaseProtocolRole.MONITORING_AUTHORITY,
        ReleaseProtocolRole.INCIDENT_AUTHORITY,
    }),
    ReleaseProtocolEventType.REVOKE_RELEASE: frozenset({
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        ReleaseProtocolRole.INCIDENT_AUTHORITY,
    }),
    ReleaseProtocolEventType.EXPIRE_RELEASE: frozenset({
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
    }),
    ReleaseProtocolEventType.ABORT_RELEASE: frozenset({
        ReleaseProtocolRole.MODEL_OWNER,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        ReleaseProtocolRole.PORTFOLIO_REGISTRY,
    }),
}


_REQUIRED_ARTIFACTS: dict[
    ReleaseProtocolEventType,
    frozenset[ReleaseProtocolArtifactKind],
] = {
    ReleaseProtocolEventType.REGISTER_SCOPE: frozenset({
        ReleaseProtocolArtifactKind.REGISTRATION,
        ReleaseProtocolArtifactKind.POLICY_SNAPSHOT,
        ReleaseProtocolArtifactKind.RELEASE_INSTANCE,
        ReleaseProtocolArtifactKind.POPULATION_REGISTER,
        ReleaseProtocolArtifactKind.THREAT_REGISTER,
        ReleaseProtocolArtifactKind.PORTFOLIO_SNAPSHOT,
    }),
    ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN: frozenset({
        ReleaseProtocolArtifactKind.EVIDENCE_PLAN,
        ReleaseProtocolArtifactKind.ASSURANCE_ERROR_BUDGET,
        ReleaseProtocolArtifactKind.MONITORING_PLAN,
    }),
    ReleaseProtocolEventType.CLOSE_EVIDENCE: frozenset({ReleaseProtocolArtifactKind.EVIDENCE_BUNDLE}),
    ReleaseProtocolEventType.RECORD_ASSESSMENT: frozenset({ReleaseProtocolArtifactKind.ASSESSMENT_REPORT}),
    ReleaseProtocolEventType.RECORD_SELECTION: frozenset({ReleaseProtocolArtifactKind.OPTIMIZATION_REPORT}),
    ReleaseProtocolEventType.SUBMIT_AUTHORIZATION: frozenset({ReleaseProtocolArtifactKind.AUTHORIZATION_COMMIT_REQUEST}),
    ReleaseProtocolEventType.COMMIT_PORTFOLIO: frozenset({
        ReleaseProtocolArtifactKind.AUTHORIZATION_RECEIPT,
        ReleaseProtocolArtifactKind.PORTFOLIO_COMMIT,
    }),
    ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT: frozenset({ReleaseProtocolArtifactKind.ACTIVATION_RECEIPT}),
    ReleaseProtocolEventType.REVIEW_MONITORING: frozenset({ReleaseProtocolArtifactKind.MONITORING_REPORT}),
    ReleaseProtocolEventType.SUSPEND_RELEASE: frozenset({ReleaseProtocolArtifactKind.INCIDENT_RECORD}),
    ReleaseProtocolEventType.REVOKE_RELEASE: frozenset({ReleaseProtocolArtifactKind.INCIDENT_RECORD}),
    ReleaseProtocolEventType.EXPIRE_RELEASE: frozenset({ReleaseProtocolArtifactKind.DECOMMISSION_RECORD}),
    ReleaseProtocolEventType.ABORT_RELEASE: frozenset({ReleaseProtocolArtifactKind.ABORT_RECORD}),
}


_ARTIFACT_PRODUCER_ROLES: dict[
    ReleaseProtocolArtifactKind,
    frozenset[ReleaseProtocolRole],
] = {
    ReleaseProtocolArtifactKind.REGISTRATION: frozenset({ReleaseProtocolRole.MODEL_OWNER}),
    ReleaseProtocolArtifactKind.POLICY_SNAPSHOT: frozenset({ReleaseProtocolRole.POLICY_AUTHORITY}),
    ReleaseProtocolArtifactKind.RELEASE_INSTANCE: frozenset({
        ReleaseProtocolRole.MODEL_OWNER,
        ReleaseProtocolRole.CONFIGURATION_GENERATOR,
    }),
    ReleaseProtocolArtifactKind.POPULATION_REGISTER: frozenset({ReleaseProtocolRole.POPULATION_STEWARD}),
    ReleaseProtocolArtifactKind.THREAT_REGISTER: frozenset({ReleaseProtocolRole.POLICY_AUTHORITY}),
    ReleaseProtocolArtifactKind.PORTFOLIO_SNAPSHOT: frozenset({ReleaseProtocolRole.PORTFOLIO_REGISTRY}),
    ReleaseProtocolArtifactKind.EVIDENCE_PLAN: frozenset({ReleaseProtocolRole.INDEPENDENT_ASSESSOR}),
    ReleaseProtocolArtifactKind.ASSURANCE_ERROR_BUDGET: frozenset({ReleaseProtocolRole.POLICY_AUTHORITY}),
    ReleaseProtocolArtifactKind.MONITORING_PLAN: frozenset({ReleaseProtocolRole.MONITORING_AUTHORITY}),
    ReleaseProtocolArtifactKind.EVIDENCE_BUNDLE: frozenset({ReleaseProtocolRole.EVIDENCE_AUTHORITY}),
    ReleaseProtocolArtifactKind.ASSESSMENT_REPORT: frozenset({ReleaseProtocolRole.INDEPENDENT_ASSESSOR}),
    ReleaseProtocolArtifactKind.OPTIMIZATION_REPORT: frozenset({ReleaseProtocolRole.OPTIMIZATION_AUTHORITY}),
    ReleaseProtocolArtifactKind.AUTHORIZATION_COMMIT_REQUEST: frozenset({ReleaseProtocolRole.AUTHORIZATION_AUTHORITY}),
    ReleaseProtocolArtifactKind.AUTHORIZATION_RECEIPT: frozenset({ReleaseProtocolRole.PORTFOLIO_REGISTRY}),
    ReleaseProtocolArtifactKind.PORTFOLIO_COMMIT: frozenset({ReleaseProtocolRole.PORTFOLIO_REGISTRY}),
    ReleaseProtocolArtifactKind.ACTIVATION_RECEIPT: frozenset({ReleaseProtocolRole.DEPLOYMENT_GATEWAY}),
    ReleaseProtocolArtifactKind.MONITORING_REPORT: frozenset({ReleaseProtocolRole.MONITORING_AUTHORITY}),
    ReleaseProtocolArtifactKind.INCIDENT_RECORD: frozenset({
        ReleaseProtocolRole.MONITORING_AUTHORITY,
        ReleaseProtocolRole.INCIDENT_AUTHORITY,
    }),
    ReleaseProtocolArtifactKind.DECOMMISSION_RECORD: frozenset({
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
        ReleaseProtocolRole.INCIDENT_AUTHORITY,
    }),
    ReleaseProtocolArtifactKind.ABORT_RECORD: frozenset({
        ReleaseProtocolRole.MODEL_OWNER,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        ReleaseProtocolRole.PORTFOLIO_REGISTRY,
    }),
}


def release_protocol_event_sha256(event: ReleaseProtocolEvent) -> str:
    """Return the canonical hash chained by the next lifecycle event."""
    return sha256_bytes(canonical_json_bytes(event))


def _transition_error(
    reasons: list[str],
    event: ReleaseProtocolEvent,
    state: ReleaseProtocolState,
    expected: tuple[ReleaseProtocolState, ...],
) -> bool:
    if state not in expected:
        reasons.append(
            f"event {event.event_id} ({event.event_type.value}) is invalid from state "
            f"{state}; expected one of {[value.value for value in expected]}"
        )
        return True
    return False


def verify_release_protocol_run(
    run: ReleaseProtocolRun,
    base_dir: Path,
    *,
    verify_artifact_files: bool = True,
    as_of: datetime | None = None,
) -> ReleaseProtocolVerification:
    """Replay the complete lifecycle transcript without mutating external state."""
    verification_time = as_of or datetime.now(timezone.utc)
    if verification_time.utcoffset() is None:
        raise ValueError("protocol verification time must include a timezone offset")
    reasons: list[str] = []
    actors = {actor.actor_id: actor for actor in run.actors}
    event_hashes: list[str] = []
    previous_hash: str | None = None
    previous_time: datetime | None = None
    state = ReleaseProtocolState.DRAFT

    alpha_budget: Decimal | None = None
    evidence_complete = False
    selection_coverage_valid = False
    controls_passed = False
    assessment_verdict: OverallVerdict | None = None
    optimization_outcome: OptimizationOutcome | None = None
    authorization_expiry: datetime | None = None
    committed_registry_head: str | None = None
    authorization_issued = False

    for event in run.events:
        event_reason_start = len(reasons)
        next_state: ReleaseProtocolState | None = None
        next_alpha_budget = alpha_budget
        next_evidence_complete = evidence_complete
        next_selection_coverage_valid = selection_coverage_valid
        next_controls_passed = controls_passed
        next_assessment_verdict = assessment_verdict
        next_optimization_outcome = optimization_outcome
        next_authorization_expiry = authorization_expiry
        next_committed_registry_head = committed_registry_head
        next_authorization_issued = authorization_issued

        actor = actors.get(event.actor_id)
        if actor is None or actor.role is not event.actor_role:
            reasons.append(f"event {event.event_id} does not match its designated actor and role")
        if event.actor_role not in _EVENT_ROLES[event.event_type]:
            reasons.append(
                f"role {event.actor_role.value} cannot perform event {event.event_type.value}"
            )
        if event.previous_event_sha256 != previous_hash:
            reasons.append(f"event {event.event_id} breaks the protocol hash chain")
        if previous_time is not None and event.occurred_at < previous_time:
            reasons.append(f"event {event.event_id} precedes an earlier protocol event")
        previous_time = event.occurred_at

        kinds = {artifact.kind for artifact in event.artifacts}
        missing = _REQUIRED_ARTIFACTS[event.event_type] - kinds
        if missing:
            reasons.append(
                f"event {event.event_id} omits required artifacts: "
                f"{sorted(kind.value for kind in missing)}"
            )
        for artifact in event.artifacts:
            producer = actors.get(artifact.producer_actor_id)
            if producer is None:
                reasons.append(
                    f"artifact {artifact.artifact_id} names an unknown producer actor"
                )
            elif producer.role not in _ARTIFACT_PRODUCER_ROLES[artifact.kind]:
                reasons.append(
                    f"artifact {artifact.artifact_id} cannot be produced by role "
                    f"{producer.role.value}"
                )
            if verify_artifact_files:
                try:
                    resolved_base = base_dir.resolve(strict=True)
                    resolved_artifact = (resolved_base / artifact.path).resolve(strict=True)
                    if not resolved_artifact.is_relative_to(resolved_base):
                        raise IntegrityError(
                            "protocol artifact resolves outside the declared artifact base"
                        )
                    verify_source_file(artifact.path, artifact.sha256, base_dir)
                except (IntegrityError, OSError, ValueError) as exc:
                    reasons.append(f"artifact {artifact.artifact_id} failed digest replay: {exc}")

        event_hash = release_protocol_event_sha256(event)
        event_hashes.append(event_hash)
        previous_hash = event_hash

        if event.event_type is ReleaseProtocolEventType.REGISTER_SCOPE:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.DRAFT,)):
                policy_hashes = {
                    artifact.sha256
                    for artifact in event.artifacts
                    if artifact.kind is ReleaseProtocolArtifactKind.POLICY_SNAPSHOT
                }
                instance_hashes = {
                    artifact.sha256
                    for artifact in event.artifacts
                    if artifact.kind is ReleaseProtocolArtifactKind.RELEASE_INSTANCE
                }
                if policy_hashes != {run.policy_sha256}:
                    reasons.append(f"event {event.event_id} does not bind the registered policy")
                if instance_hashes != {run.release_instance_sha256}:
                    reasons.append(
                        f"event {event.event_id} does not bind the registered release instance"
                    )
                next_state = ReleaseProtocolState.REGISTERED

        elif event.event_type is ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.REGISTERED,)):
                if event.assurance_alpha_budget is None:
                    reasons.append(f"event {event.event_id} omits the assurance alpha budget")
                else:
                    next_alpha_budget = event.assurance_alpha_budget
                next_state = ReleaseProtocolState.PLAN_FROZEN

        elif event.event_type is ReleaseProtocolEventType.CLOSE_EVIDENCE:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.PLAN_FROZEN,)):
                required_values = (
                    event.mandatory_evidence_complete,
                    event.selection_coverage_valid,
                    event.positive_control_status,
                    event.assurance_alpha_spent,
                )
                if any(value is None for value in required_values):
                    reasons.append(f"event {event.event_id} omits evidence-closure assertions")
                next_evidence_complete = event.mandatory_evidence_complete is True
                next_selection_coverage_valid = event.selection_coverage_valid is True
                next_controls_passed = event.positive_control_status in (
                    ControlStatus.PASS,
                    ControlStatus.NOT_APPLICABLE,
                )
                if (
                    alpha_budget is not None
                    and event.assurance_alpha_spent is not None
                    and event.assurance_alpha_spent > alpha_budget
                ):
                    reasons.append(
                        f"event {event.event_id} exceeds the registered assurance alpha budget"
                    )
                next_state = ReleaseProtocolState.EVIDENCE_FROZEN

        elif event.event_type is ReleaseProtocolEventType.RECORD_ASSESSMENT:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.EVIDENCE_FROZEN,)):
                if event.assessment_verdict is None:
                    reasons.append(f"event {event.event_id} omits the assessment verdict")
                else:
                    if event.assessment_verdict is OverallVerdict.CLEAR:
                        clearance_gates = {
                            "mandatory evidence is incomplete": evidence_complete,
                            "selection-valid coverage is absent": selection_coverage_valid,
                            "positive controls failed": controls_passed,
                        }
                        for message, satisfied in clearance_gates.items():
                            if not satisfied:
                                reasons.append(
                                    f"event {event.event_id} cannot record clear: {message}"
                                )
                    next_assessment_verdict = event.assessment_verdict
                next_state = ReleaseProtocolState.ASSESSED

        elif event.event_type is ReleaseProtocolEventType.RECORD_SELECTION:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.ASSESSED,)):
                if event.optimization_outcome is None:
                    reasons.append(f"event {event.event_id} omits the optimization outcome")
                else:
                    next_optimization_outcome = event.optimization_outcome
                    if event.optimization_outcome in (
                        OptimizationOutcome.RELEASE_AS_PROPOSED,
                        OptimizationOutcome.RELEASE_WITH_CONTROLS,
                    ):
                        if assessment_verdict is not OverallVerdict.CLEAR:
                            reasons.append(
                                f"event {event.event_id} selects release after a non-clear assessment"
                            )
                        if event.selected_configuration_id is None:
                            reasons.append(
                                f"event {event.event_id} omits the selected configuration"
                            )
                        next_state = ReleaseProtocolState.OPTIMIZED
                    elif event.optimization_outcome is OptimizationOutcome.REJECT:
                        if event.exhaustive_search_replayed is not True:
                            reasons.append(
                                f"event {event.event_id} claims reject without replayed exhaustive search"
                            )
                        next_state = ReleaseProtocolState.REJECTED
                    else:
                        next_state = ReleaseProtocolState.REDESIGN_REQUIRED

        elif event.event_type is ReleaseProtocolEventType.SUBMIT_AUTHORIZATION:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.OPTIMIZED,)):
                gates = {
                    "mandatory evidence is incomplete": evidence_complete,
                    "selection-valid coverage is absent": selection_coverage_valid,
                    "positive controls failed": controls_passed,
                    "assessment is not clear": assessment_verdict is OverallVerdict.CLEAR,
                    "optimizer did not select a releasable configuration": optimization_outcome in (
                        OptimizationOutcome.RELEASE_AS_PROPOSED,
                        OptimizationOutcome.RELEASE_WITH_CONTROLS,
                    ),
                    "authorization expiry is absent": event.authorization_expires_at is not None,
                }
                for message, satisfied in gates.items():
                    if not satisfied:
                        reasons.append(f"event {event.event_id} cannot request authorization: {message}")
                next_authorization_expiry = event.authorization_expires_at
                next_state = ReleaseProtocolState.COMMIT_PENDING

        elif event.event_type is ReleaseProtocolEventType.COMMIT_PORTFOLIO:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.COMMIT_PENDING,)):
                if event.expected_registry_head_sha256 != run.registered_portfolio_head_sha256:
                    reasons.append(f"event {event.event_id} compares against the wrong portfolio head")
                if event.atomic_compare_and_swap_succeeded is not True:
                    reasons.append(f"event {event.event_id} lacks a successful atomic compare-and-swap")
                if event.committed_registry_head_sha256 in (
                    None,
                    run.registered_portfolio_head_sha256,
                ):
                    reasons.append(f"event {event.event_id} does not establish a new portfolio head")
                if authorization_expiry is None or event.occurred_at >= authorization_expiry:
                    reasons.append(f"event {event.event_id} commits an absent or expired request")
                next_committed_registry_head = event.committed_registry_head_sha256
                next_authorization_issued = True
                next_state = ReleaseProtocolState.AUTHORIZED

        elif event.event_type is ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.AUTHORIZED,)):
                if event.deployed_artifact_sha256 != run.artifact_sha256:
                    reasons.append(f"event {event.event_id} deploys a different artifact")
                if event.deployed_interface_sha256 != run.interface_sha256:
                    reasons.append(f"event {event.event_id} deploys a different interface")
                if committed_registry_head is None:
                    reasons.append(f"event {event.event_id} has no committed portfolio head")
                if authorization_expiry is None or event.occurred_at >= authorization_expiry:
                    reasons.append(f"event {event.event_id} uses an absent or expired authorization")
                next_state = ReleaseProtocolState.ACTIVE

        elif event.event_type is ReleaseProtocolEventType.REVIEW_MONITORING:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.ACTIVE,)):
                if event.monitoring_outcome is None:
                    reasons.append(f"event {event.event_id} omits the monitoring outcome")
                else:
                    next_state = {
                        MonitoringOutcome.CONTINUE: ReleaseProtocolState.ACTIVE,
                        MonitoringOutcome.SUSPEND: ReleaseProtocolState.SUSPENDED,
                        MonitoringOutcome.REVOKE: ReleaseProtocolState.REVOKED,
                        MonitoringOutcome.EXPIRE: ReleaseProtocolState.EXPIRED,
                    }[event.monitoring_outcome]

        elif event.event_type is ReleaseProtocolEventType.SUSPEND_RELEASE:
            if not _transition_error(reasons, event, state, (ReleaseProtocolState.ACTIVE,)):
                if not event.reason:
                    reasons.append(f"event {event.event_id} omits the suspension reason")
                next_state = ReleaseProtocolState.SUSPENDED

        elif event.event_type is ReleaseProtocolEventType.REVOKE_RELEASE:
            if not _transition_error(
                reasons, event, state,
                (ReleaseProtocolState.ACTIVE, ReleaseProtocolState.SUSPENDED),
            ):
                if not event.reason:
                    reasons.append(f"event {event.event_id} omits the revocation reason")
                next_state = ReleaseProtocolState.REVOKED

        elif event.event_type is ReleaseProtocolEventType.EXPIRE_RELEASE:
            if not _transition_error(
                reasons, event, state,
                (
                    ReleaseProtocolState.AUTHORIZED,
                    ReleaseProtocolState.ACTIVE,
                    ReleaseProtocolState.SUSPENDED,
                ),
            ):
                next_state = ReleaseProtocolState.EXPIRED

        elif event.event_type is ReleaseProtocolEventType.ABORT_RELEASE:
            if not _transition_error(
                reasons, event, state,
                (
                    ReleaseProtocolState.REGISTERED,
                    ReleaseProtocolState.PLAN_FROZEN,
                    ReleaseProtocolState.EVIDENCE_FROZEN,
                    ReleaseProtocolState.ASSESSED,
                    ReleaseProtocolState.OPTIMIZED,
                    ReleaseProtocolState.COMMIT_PENDING,
                ),
            ):
                if not event.reason:
                    reasons.append(f"event {event.event_id} omits the abort reason")
                next_state = ReleaseProtocolState.ABORTED

        if len(reasons) == event_reason_start and next_state is not None:
            state = next_state
            alpha_budget = next_alpha_budget
            evidence_complete = next_evidence_complete
            selection_coverage_valid = next_selection_coverage_valid
            controls_passed = next_controls_passed
            assessment_verdict = next_assessment_verdict
            optimization_outcome = next_optimization_outcome
            authorization_expiry = next_authorization_expiry
            committed_registry_head = next_committed_registry_head
            authorization_issued = next_authorization_issued

    if state is not run.claimed_state:
        reasons.append(
            f"claimed state {run.claimed_state.value} does not match replayed state {state.value}"
        )
    if state in (
        ReleaseProtocolState.COMMIT_PENDING,
        ReleaseProtocolState.AUTHORIZED,
        ReleaseProtocolState.ACTIVE,
        ReleaseProtocolState.SUSPENDED,
    ) and (
        authorization_expiry is None or verification_time >= authorization_expiry
    ):
        reasons.append(
            f"claimed state {state.value} has an absent or expired authorization at verification time"
        )

    return ReleaseProtocolVerification(
        valid=not reasons,
        final_state=state,
        authorization_issued=authorization_issued,
        deployment_active=not reasons and state is ReleaseProtocolState.ACTIVE,
        event_sha256s=tuple(event_hashes),
        reasons=tuple(reasons),
    )
