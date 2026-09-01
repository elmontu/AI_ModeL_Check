from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import Field, ValidationError, model_validator

from .errors import IntegrityError
from .integrity import canonical_json_bytes, sha256_bytes
from .models import AssessmentReport, AssessmentRequest, StrictModel
from .optimizer import OptimizationReport, OptimizationRequest
from .runtime_identity import RuntimeIdentity, current_runtime_identity


GENESIS = "0" * 64
_AUDIT_SCHEMA_VERSION = "2.0"
_AUDIT_EVENT_HASH_FORMAT = "mra-audit-event-v2"
_LEGACY_EVENT_HASH_FORMAT = "legacy-v1"
_AUDIT_EVENT_DOMAIN = b"AI_MODE_L_CHECK:AUDIT_EVENT"
_LEGACY_EVENT_TYPES = frozenset({"assessment_report", "optimization_report"})
_INTENT_EVENT_TYPES = {
    "assessment_intent": "assessment",
    "optimization_intent": "optimization",
}
_COMPLETED_EVENT_TYPES = {
    "assessment_completed": "assessment",
    "optimization_completed": "optimization",
}
_FAILED_EVENT_TYPES = {
    "assessment_failed": "assessment",
    "optimization_failed": "optimization",
}
_TERMINAL_EVENT_TYPES = frozenset((*_COMPLETED_EVENT_TYPES, *_FAILED_EVENT_TYPES))
_EVENT_OPERATIONS = {
    "assessment_report": "assessment",
    "optimization_report": "optimization",
    **_INTENT_EVENT_TYPES,
    **_COMPLETED_EVENT_TYPES,
    **_FAILED_EVENT_TYPES,
}


AuditOperation = Literal["assessment", "optimization"]
AuditEventHashFormat = Literal["mra-audit-event-v2"]


def _canonical_json_text(value: StrictModel) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _canonical_object(value: str, label: str) -> dict:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must encode a JSON object")
    if canonical_json_bytes(decoded).decode("utf-8") != value:
        raise ValueError(f"{label} is not canonical MRA JSON")
    return decoded


def _required_mapping(raw: dict, key: str, label: str) -> dict:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{label} omits object field {key!r}")
    return value


def _required_value(raw: dict, key: str, label: str) -> Any:
    if key not in raw:
        raise ValueError(f"{label} omits field {key!r}")
    return raw[key]


def _required_model_fields(raw: dict, model: type[StrictModel], label: str) -> None:
    missing = sorted(
        name
        for name, field in model.model_fields.items()
        if field.is_required() and name not in raw
    )
    if missing:
        raise ValueError(f"{label} omits required fields: {missing}")


def _binding_sha256(operation: AuditOperation, raw: dict, *, report: bool) -> str:
    label = f"{operation} {'report' if report else 'request'}"
    if operation == "assessment":
        if report:
            assessment_scope = _required_mapping(raw, "assessment_scope", label)
            release_interface = _required_mapping(raw, "release_interface", label)
            release_model_profile = _required_mapping(
                raw, "release_model_profile", label
            )
            binding = {
                "release_id": _required_value(raw, "release_id", label),
                "artifact_sha256": _required_value(raw, "artifact_sha256", label),
                "release_contract_sha256": _required_value(
                    raw, "release_contract_sha256", label
                ),
                "policy_id": _required_value(raw, "policy_id", label),
                "policy_version": _required_value(raw, "policy_version", label),
                "policy_sha256": _required_value(raw, "policy_sha256", label),
                "release_model_family": _required_value(
                    raw, "release_model_family", label
                ),
                "release_model_profile_sha256": sha256_bytes(
                    canonical_json_bytes(release_model_profile)
                ),
                "release_interface_sha256": sha256_bytes(
                    canonical_json_bytes(release_interface)
                ),
                "release_expires_at": raw.get("release_expires_at"),
                "previous_release_ids": _required_value(
                    assessment_scope, "declared_previous_release_ids", label
                ),
            }
        else:
            release = _required_mapping(raw, "release", label)
            policy = _required_mapping(raw, "policy", label)
            release_interface = _required_mapping(release, "interface", label)
            release_model_profile = _required_mapping(
                release, "model_profile", label
            )
            binding = {
                "release_id": _required_value(release, "release_id", label),
                "artifact_sha256": _required_value(
                    release, "artifact_sha256", label
                ),
                "release_contract_sha256": sha256_bytes(
                    canonical_json_bytes(release)
                ),
                "policy_id": _required_value(policy, "policy_id", label),
                "policy_version": _required_value(policy, "policy_version", label),
                "policy_sha256": _required_value(policy, "policy_sha256", label),
                "release_model_family": _required_value(
                    release, "model_family", label
                ),
                "release_model_profile_sha256": sha256_bytes(
                    canonical_json_bytes(release_model_profile)
                ),
                "release_interface_sha256": sha256_bytes(
                    canonical_json_bytes(release_interface)
                ),
                "release_expires_at": release.get("expires_at"),
                "previous_release_ids": release.get("previous_release_ids", []),
            }
    elif report:
        selection_policy = _required_mapping(raw, "selection_policy", label)
        binding = {
            "policy_id": _required_value(raw, "policy_id", label),
            "policy_version": _required_value(raw, "policy_version", label),
            "policy_sha256": _required_value(raw, "policy_sha256", label),
            "trust_profile": _required_value(raw, "trust_profile", label),
            "portfolio_registry_id": _required_value(
                raw, "portfolio_registry_id", label
            ),
            "portfolio_registry_head_sha256": _required_value(
                raw, "portfolio_registry_head_sha256", label
            ),
            "portfolio_registry_sequence": _required_value(
                raw, "portfolio_registry_sequence", label
            ),
            "composition_domain_id": _required_value(
                raw, "composition_domain_id", label
            ),
            "selection_policy_sha256": sha256_bytes(
                canonical_json_bytes(selection_policy)
            ),
        }
        claimed_selection_hash = _required_value(
            raw, "selection_policy_sha256", label
        )
        if binding["selection_policy_sha256"] != claimed_selection_hash:
            raise ValueError("optimization report selection-policy hash does not replay")
    else:
        policy = _required_mapping(raw, "active_policy", label)
        registry = _required_mapping(raw, "portfolio_registry", label)
        selection_policy = _required_mapping(raw, "selection_policy", label)
        binding = {
            "policy_id": _required_value(policy, "policy_id", label),
            "policy_version": _required_value(policy, "policy_version", label),
            "policy_sha256": _required_value(policy, "policy_sha256", label),
            "trust_profile": _required_value(raw, "trust_profile", label),
            "portfolio_registry_id": _required_value(
                registry, "registry_id", label
            ),
            "portfolio_registry_head_sha256": _required_value(
                registry, "registry_head_sha256", label
            ),
            "portfolio_registry_sequence": _required_value(
                registry, "registry_sequence", label
            ),
            "composition_domain_id": _required_value(
                registry, "composition_domain_id", label
            ),
            "selection_policy_sha256": sha256_bytes(
                canonical_json_bytes(selection_policy)
            ),
        }
    return sha256_bytes(canonical_json_bytes(binding))


def _intent_release_identity(
    operation: AuditOperation, raw: dict
) -> tuple[str | None, str]:
    """Return the explicit release identity committed by an intent.

    Assessment requests contain one release contract, so its stable release ID
    and canonical contract digest are the natural identity. Optimization
    requests describe a frozen release-selection instance rather than one
    necessarily selectable release. Its instance digest is therefore the
    canonical request digest. When every candidate portfolio identifies one
    common release beyond the active registry set, that release ID is exposed
    as a searchable convenience; inconclusive/refusal-only searches may have no
    such ID and remain identified by their instance digest.
    """
    if operation == "assessment":
        release = _required_mapping(raw, "release", "assessment request")
        return (
            _required_value(release, "release_id", "assessment request"),
            sha256_bytes(canonical_json_bytes(release)),
        )

    active = set(
        _required_value(
            _required_mapping(raw, "portfolio_registry", "optimization request"),
            "active_release_ids",
            "optimization request",
        )
    )
    candidate_release_ids: set[str] = set()
    configurations = _required_value(raw, "configurations", "optimization request")
    if not isinstance(configurations, list):
        raise ValueError("optimization request configurations must be an array")
    for index, configuration in enumerate(configurations):
        if not isinstance(configuration, dict):
            raise ValueError(
                f"optimization request configuration {index} must be an object"
            )
        portfolio = _required_mapping(
            configuration,
            "portfolio",
            f"optimization request configuration {index}",
        )
        registered = _required_value(
            portfolio,
            "registered_release_ids",
            f"optimization request configuration {index}",
        )
        if not isinstance(registered, list):
            raise ValueError(
                "optimization request registered_release_ids must be an array"
            )
        candidate_release_ids.update(set(registered) - active)
    release_id = (
        next(iter(candidate_release_ids))
        if len(candidate_release_ids) == 1
        else None
    )
    return release_id, sha256_bytes(canonical_json_bytes(raw))


def _validated_document_text(
    value: StrictModel,
    model: type[StrictModel],
    label: str,
) -> str:
    raw = value.model_dump(mode="json", exclude_none=True)
    try:
        validated = model.model_validate(raw)
    except ValidationError as exc:
        raise IntegrityError(f"invalid {label}: {exc}") from exc
    return _canonical_json_text(validated)


def _validate_replayed_request(
    operation: AuditOperation,
    request_json: str,
    event_time: datetime,
) -> None:
    raw = _canonical_object(request_json, f"{operation} request")
    try:
        if operation == "optimization":
            OptimizationRequest.model_validate(raw)
            return

        # AssessmentRequest deliberately rejects contracts that are expired at
        # load time. Audit replay instead asks whether the contract was valid
        # when its intent event was committed, while preserving every other
        # model validator. Substitute only the already-checked temporal values
        # before structural replay so old ledgers remain verifiable.
        release = _required_mapping(raw, "release", "assessment request")
        release_expiry = release.get("expires_at")
        parsed_release_expiry = None
        if release_expiry is not None:
            parsed_release_expiry = datetime.fromisoformat(release_expiry)
            if parsed_release_expiry.utcoffset() is None:
                raise ValueError("assessment release expiry is timezone-naive")
            if parsed_release_expiry <= event_time:
                raise ValueError("assessment release was expired at intent time")
            release["expires_at"] = "9998-01-01T00:00:00+00:00"

        interface = _required_mapping(release, "interface", "assessment release")
        protocol = interface.get("llm_protocol")
        if protocol is not None:
            if not isinstance(protocol, dict):
                raise ValueError("assessment LLM protocol must be an object")
            valid_until = _required_value(
                protocol, "valid_until", "assessment LLM protocol"
            )
            parsed_valid_until = datetime.fromisoformat(valid_until)
            if parsed_valid_until.utcoffset() is None:
                raise ValueError("assessment LLM protocol expiry is timezone-naive")
            if parsed_valid_until <= event_time:
                raise ValueError("assessment LLM protocol was expired at intent time")
            if (
                parsed_release_expiry is not None
                and parsed_release_expiry > parsed_valid_until
            ):
                raise ValueError("assessment release outlives its LLM protocol")
            protocol["valid_until"] = "9999-01-01T00:00:00+00:00"

        AssessmentRequest.model_validate(raw)
    except (TypeError, ValueError, ValidationError) as exc:
        raise IntegrityError(f"invalid replayed {operation} request: {exc}") from exc


class _AuditIntentPayload(StrictModel):
    schema_version: Literal["2.0"] = _AUDIT_SCHEMA_VERSION
    operation: AuditOperation
    run_id: uuid.UUID
    subject_id: str = Field(min_length=1, max_length=256)
    release_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    release_instance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_json: str = Field(min_length=2)
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authorization_expires_at: datetime | None = None

    @model_validator(mode="after")
    def request_binding_is_complete(self) -> _AuditIntentPayload:
        raw = _canonical_object(self.request_json, "audit intent request_json")
        if sha256_bytes(self.request_json.encode("utf-8")) != self.request_sha256:
            raise ValueError("audit intent request hash does not match request_json")
        if self.operation == "assessment":
            if raw.get("schema_version") != "4.0":
                raise ValueError("assessment intent requires an assessment request v4")
            _required_model_fields(raw, AssessmentRequest, "assessment request")
            release = raw.get("release")
            if not isinstance(release, dict):
                raise ValueError("assessment intent request omits the release contract")
            if release.get("release_id") != self.subject_id:
                raise ValueError("assessment intent subject does not match the release")
            if release.get("artifact_sha256") != self.artifact_sha256:
                raise ValueError("assessment intent artifact does not match the release")
            if self.authorization_expires_at is not None:
                raise ValueError("assessment intents have no optimization authorization")
        else:
            if raw.get("schema_version") != "3.0":
                raise ValueError("optimization intent requires an optimization request v3")
            _required_model_fields(raw, OptimizationRequest, "optimization request")
            if raw.get("optimization_id") != self.subject_id:
                raise ValueError("optimization intent subject does not match the request")
            if self.artifact_sha256 is not None:
                raise ValueError("optimization intents do not bind one artifact digest")
            raw_expiry = _required_value(
                raw, "authorization_expires_at", "optimization request"
            )
            parsed_expiry = datetime.fromisoformat(raw_expiry)
            if parsed_expiry.utcoffset() is None:
                raise ValueError("optimization authorization expiry is timezone-naive")
            if self.authorization_expires_at != parsed_expiry:
                raise ValueError(
                    "optimization intent authorization does not match request_json"
                )
        expected_release_id, expected_instance = _intent_release_identity(
            self.operation, raw
        )
        if self.release_id != expected_release_id:
            raise ValueError("audit intent release ID does not match request_json")
        if self.release_instance_sha256 != expected_instance:
            raise ValueError(
                "audit intent release-instance digest does not match request_json"
            )
        if _binding_sha256(self.operation, raw, report=False) != self.binding_sha256:
            raise ValueError("audit intent contract binding does not match request_json")
        return self


class _AuditCompletedPayload(StrictModel):
    schema_version: Literal["2.0"] = _AUDIT_SCHEMA_VERSION
    operation: AuditOperation
    run_id: uuid.UUID
    subject_id: str = Field(min_length=1, max_length=256)
    release_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    release_instance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    intent_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_id: str = Field(min_length=1, max_length=256)
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_json: str = Field(min_length=2)
    outcome: str = Field(min_length=1, max_length=128)
    result_expires_at: datetime | None = None

    @model_validator(mode="after")
    def report_binding_is_complete(self) -> _AuditCompletedPayload:
        raw = _canonical_object(self.report_json, "audit completion report_json")
        if sha256_bytes(self.report_json.encode("utf-8")) != self.report_sha256:
            raise ValueError("audit completion report hash does not match report_json")
        if raw.get("request_sha256") != self.request_sha256:
            raise ValueError("audit completion report binds a different request")
        if self.operation == "assessment":
            if raw.get("schema_version") != "4.0":
                raise ValueError("assessment completion requires an assessment report v4")
            _required_model_fields(raw, AssessmentReport, "assessment report")
            AssessmentReport.model_validate(raw)
            if self.result_expires_at is not None:
                raise ValueError("assessment completions have no optimization authorization")
            expected = (
                raw.get("release_id"),
                raw.get("assessment_id"),
                raw.get("overall_verdict"),
            )
            if self.release_id != raw.get("release_id"):
                raise ValueError("audit completion release ID does not match report_json")
            if self.release_instance_sha256 != raw.get("release_contract_sha256"):
                raise ValueError(
                    "audit completion release-instance digest does not match report_json"
                )
        else:
            if raw.get("schema_version") != "3.0":
                raise ValueError("optimization completion requires an optimization report v3")
            _required_model_fields(raw, OptimizationReport, "optimization report")
            OptimizationReport.model_validate(raw)
            created_at = datetime.fromisoformat(
                _required_value(raw, "created_at", "optimization report")
            )
            expires_at = datetime.fromisoformat(
                _required_value(raw, "expires_at", "optimization report")
            )
            if created_at.utcoffset() is None or expires_at.utcoffset() is None:
                raise ValueError("optimization report timestamps are timezone-naive")
            if created_at > expires_at:
                raise ValueError("optimization report expires before it was created")
            if self.result_expires_at != expires_at:
                raise ValueError(
                    "optimization completion expiry does not match report_json"
                )
            expected = (
                raw.get("optimization_id"),
                raw.get("optimization_id"),
                raw.get("outcome"),
            )
            if self.release_instance_sha256 != self.request_sha256:
                raise ValueError(
                    "optimization completion release instance must bind its request"
                )
        if expected != (self.subject_id, self.result_id, self.outcome):
            raise ValueError("audit completion identity or outcome does not match report_json")
        if _binding_sha256(self.operation, raw, report=True) != self.binding_sha256:
            raise ValueError("audit completion contract binding does not match report_json")
        return self


class _AuditFailedPayload(StrictModel):
    schema_version: Literal["2.0"] = _AUDIT_SCHEMA_VERSION
    operation: AuditOperation
    run_id: uuid.UUID
    subject_id: str = Field(min_length=1, max_length=256)
    release_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    release_instance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    intent_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    error_code: str = Field(min_length=1, max_length=128)
    error_message: str = Field(default="", max_length=4096)


class AuditRun(StrictModel):
    """Handle returned after an intent has durably entered one audit chain."""

    schema_version: Literal["2.0"] = _AUDIT_SCHEMA_VERSION
    operation: AuditOperation
    run_id: uuid.UUID
    subject_id: str = Field(min_length=1, max_length=256)
    release_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    release_instance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    intent_sequence: int = Field(ge=1)
    intent_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AuditEventReceipt(StrictModel):
    schema_version: Literal["2.0"] = _AUDIT_SCHEMA_VERSION
    operation: AuditOperation
    run_id: uuid.UUID
    event_type: str = Field(min_length=1, max_length=64)
    hash_format: AuditEventHashFormat = _AUDIT_EVENT_HASH_FORMAT
    sequence: int = Field(ge=1)
    occurred_at: datetime
    previous_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def time_is_aware(self) -> AuditEventReceipt:
        if self.occurred_at.utcoffset() is None:
            raise ValueError("audit event time must include a timezone offset")
        return self


class AuditVerification(StrictModel):
    """Structured result for one fully replayed local audit chain."""

    schema_version: Literal["2.0"] = _AUDIT_SCHEMA_VERSION
    ledger_id: uuid.UUID
    event_count: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    legacy_event_count: int = Field(ge=0)
    legacy_hash_event_count: int = Field(ge=0)
    domain_separated_hash_event_count: int = Field(ge=0)
    intent_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    release_ids: tuple[str, ...] = ()
    release_instance_sha256s: tuple[str, ...] = ()
    orphaned_run_ids: tuple[uuid.UUID, ...] = ()
    complete: bool
    runtime_identity: RuntimeIdentity

    @model_validator(mode="after")
    def counts_are_coherent(self) -> AuditVerification:
        if self.runtime_identity.component_id != "audit_verifier":
            raise ValueError("audit verification has the wrong runtime component identity")
        if self.runtime_identity.component_version != "AuditVerification/2.0":
            raise ValueError("audit verification has the wrong component version")
        if self.event_count != self.last_sequence:
            raise ValueError("a verified contiguous chain must end at its event count")
        if (self.event_count == 0) != (self.head_sha256 == GENESIS):
            raise ValueError("audit head must be genesis exactly when the chain is empty")
        terminal_count = self.completed_count + self.failed_count
        if self.intent_count != terminal_count + len(self.orphaned_run_ids):
            raise ValueError("audit intent and terminal counts do not reconcile")
        if self.event_count != self.legacy_event_count + self.intent_count + terminal_count:
            raise ValueError("audit event categories do not reconcile with the event count")
        if self.event_count != (
            self.legacy_hash_event_count + self.domain_separated_hash_event_count
        ):
            raise ValueError("audit hash formats do not reconcile with the event count")
        if len(self.release_ids) != len(set(self.release_ids)):
            raise ValueError("verified release identifiers must be unique")
        if len(self.release_instance_sha256s) != len(
            set(self.release_instance_sha256s)
        ):
            raise ValueError("verified release-instance digests must be unique")
        if self.complete != (not self.orphaned_run_ids):
            raise ValueError("audit completeness disagrees with orphaned intents")
        return self


class AuditCheckpoint(StrictModel):
    """Portable head/count statement to anchor outside the local SQLite file."""

    schema_version: Literal["1.0"] = "1.0"
    ledger_id: uuid.UUID
    event_count: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime

    @model_validator(mode="after")
    def checkpoint_is_coherent(self) -> AuditCheckpoint:
        if self.event_count != self.last_sequence:
            raise ValueError("checkpoint count and sequence must match")
        if (self.event_count == 0) != (self.head_sha256 == GENESIS):
            raise ValueError("checkpoint head must be genesis exactly when the chain is empty")
        if self.created_at.utcoffset() is None:
            raise ValueError("checkpoint time must include a timezone offset")
        return self


def _event_material(
    occurred_at: str,
    event_type: str,
    record_id: str,
    payload_json: str,
    previous_hash: str,
) -> bytes:
    """Return the pre-v2 event material for explicit legacy replay only."""
    return json.dumps(
        {
            "occurred_at": occurred_at,
            "event_type": event_type,
            "assessment_id": record_id,
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _event_hash_context(
    event_type: str,
    record_id: str,
    payload_json: str,
) -> tuple[AuditOperation, str, str | None, str]:
    """Derive the security-relevant context independently from stored payload."""
    raw = _canonical_object(payload_json, f"{event_type} audit payload")
    operation = _EVENT_OPERATIONS.get(event_type)
    if operation is None:
        raise ValueError(f"unknown audit event type: {event_type}")
    event_schema_version = raw.get("schema_version")
    if not isinstance(event_schema_version, str) or not event_schema_version:
        raise ValueError("audit event payload omits its schema version")

    if event_type in _LEGACY_EVENT_TYPES:
        if event_type == "assessment_report":
            release_id = _required_value(raw, "release_id", "assessment report")
            release_instance_sha256 = _required_value(
                raw, "release_contract_sha256", "assessment report"
            )
        else:
            release_id = None
            release_instance_sha256 = _required_value(
                raw, "request_sha256", "optimization report"
            )
    else:
        payload_operation = _required_value(raw, "operation", "audit event")
        if payload_operation != operation:
            raise ValueError("audit event operation disagrees with its event type")
        if _required_value(raw, "subject_id", "audit event") != record_id:
            raise ValueError("audit event subject disagrees with its event row")
        release_id = raw.get("release_id")
        release_instance_sha256 = _required_value(
            raw, "release_instance_sha256", "audit event"
        )
    if release_id is not None and not isinstance(release_id, str):
        raise ValueError("audit event release ID must be a string or null")
    if (
        not isinstance(release_instance_sha256, str)
        or len(release_instance_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in release_instance_sha256
        )
    ):
        raise ValueError("audit event release-instance digest is invalid")
    return operation, event_schema_version, release_id, release_instance_sha256


def _event_material_v2(
    ledger_id: uuid.UUID | str,
    occurred_at: str,
    event_type: str,
    record_id: str,
    payload_json: str,
    previous_hash: str,
) -> bytes:
    """Build a domain-separated, ledger-bound audit-event preimage.

    The payload is decoded only after proving it is canonical JSON. This avoids
    hashing an ambiguous JSON string representation while retaining exact
    semantic bindings to the event schema, operation, subject, release, chain
    predecessor, and timestamp.
    """
    raw = _canonical_object(payload_json, f"{event_type} audit payload")
    operation, event_schema_version, release_id, release_instance_sha256 = (
        _event_hash_context(event_type, record_id, payload_json)
    )
    material = canonical_json_bytes(
        {
            "event_hash_format": _AUDIT_EVENT_HASH_FORMAT,
            "ledger_id": str(uuid.UUID(str(ledger_id))),
            "event_schema_version": event_schema_version,
            "operation": operation,
            "event_type": event_type,
            "subject_id": record_id,
            "release_id": release_id,
            "release_instance_sha256": release_instance_sha256,
            "payload": raw,
            "previous_hash": previous_hash,
            "occurred_at": occurred_at,
        }
    )
    return _AUDIT_EVENT_DOMAIN + b"\x00" + material


class AuditStore:
    def __init__(self, path: Path, *, read_only: bool = False):
        self.path = path
        self._read_only = read_only
        if read_only:
            if not self.path.is_file():
                raise IntegrityError("audit database does not exist")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @classmethod
    def open_read_only(cls, path: Path) -> AuditStore:
        """Open an existing ledger without initialization, migration, or write access."""
        return cls(path, read_only=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._read_only:
            raise IntegrityError("read-only audit store cannot append or initialize events")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    @contextmanager
    def _read_connect(self) -> Iterator[sqlite3.Connection]:
        uri = self.path.resolve(strict=True).as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            yield connection
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            metadata_existed = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'audit_metadata'
                """
            ).fetchone() is not None
            events_existed = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'audit_events'
                """
            ).fetchone() is not None
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    hash_format TEXT NOT NULL
                )
                """
            )
            event_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(audit_events)")
            }
            if "hash_format" not in event_columns:
                connection.execute("ALTER TABLE audit_events ADD COLUMN hash_format TEXT")
                connection.execute(
                    "UPDATE audit_events SET hash_format = ? WHERE hash_format IS NULL",
                    (_LEGACY_EVENT_HASH_FORMAT,),
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            if not metadata_existed:
                if events_existed:
                    event_types = {
                        row[0]
                        for row in connection.execute(
                            "SELECT DISTINCT event_type FROM audit_events"
                        )
                    }
                    if not event_types.issubset(_LEGACY_EVENT_TYPES):
                        raise IntegrityError(
                            "v2 audit events exist without their ledger metadata"
                        )
                connection.execute(
                    "INSERT INTO audit_metadata (key, value) VALUES ('ledger_id', ?)",
                    (str(uuid.uuid4()),),
                )
            ledger_row = connection.execute(
                "SELECT value FROM audit_metadata WHERE key = 'ledger_id'"
            ).fetchone()
            if ledger_row is None:
                raise IntegrityError("audit metadata exists but its ledger identifier is missing")
            try:
                uuid.UUID(ledger_row[0])
            except (ValueError, TypeError) as exc:
                raise IntegrityError("audit ledger identifier is invalid") from exc

    def append_report(self, report: AssessmentReport) -> str:
        """Append a legacy completion-only assessment event.

        New callers should use append_assessment_intent followed by one of the
        assessment terminal methods so omitted outcomes remain detectable.
        """
        return self._append_legacy_event("assessment_report", report.assessment_id, report)

    def append_optimization_report(self, report: OptimizationReport) -> str:
        """Append a legacy completion-only optimization event."""
        return self._append_legacy_event(
            "optimization_report", report.optimization_id, report
        )

    def append_assessment_intent(self, request: AssessmentRequest) -> AuditRun:
        request_json = _validated_document_text(
            request, AssessmentRequest, "assessment request"
        )
        request_raw = _canonical_object(request_json, "assessment request")
        release_id, release_instance_sha256 = _intent_release_identity(
            "assessment", request_raw
        )
        payload = _AuditIntentPayload(
            operation="assessment",
            run_id=uuid.uuid4(),
            subject_id=request.release.release_id,
            release_id=release_id,
            release_instance_sha256=release_instance_sha256,
            request_sha256=sha256_bytes(request_json.encode("utf-8")),
            request_json=request_json,
            binding_sha256=_binding_sha256(
                "assessment", request_raw, report=False
            ),
            artifact_sha256=request.release.artifact_sha256,
        )
        receipt = self._append_v2_event(
            "assessment_intent", payload.subject_id, payload, payload.run_id
        )
        return AuditRun(
            operation=payload.operation,
            run_id=payload.run_id,
            subject_id=payload.subject_id,
            release_id=payload.release_id,
            release_instance_sha256=release_instance_sha256,
            request_sha256=payload.request_sha256,
            intent_sequence=receipt.sequence,
            intent_event_hash=receipt.event_hash,
        )

    def append_optimization_intent(self, request: OptimizationRequest) -> AuditRun:
        request_json = _validated_document_text(
            request, OptimizationRequest, "optimization request"
        )
        request_raw = _canonical_object(request_json, "optimization request")
        release_id, release_instance_sha256 = _intent_release_identity(
            "optimization", request_raw
        )
        payload = _AuditIntentPayload(
            operation="optimization",
            run_id=uuid.uuid4(),
            subject_id=request.optimization_id,
            release_id=release_id,
            release_instance_sha256=release_instance_sha256,
            request_sha256=sha256_bytes(request_json.encode("utf-8")),
            request_json=request_json,
            binding_sha256=_binding_sha256(
                "optimization", request_raw, report=False
            ),
            authorization_expires_at=request.authorization_expires_at,
        )
        receipt = self._append_v2_event(
            "optimization_intent", payload.subject_id, payload, payload.run_id
        )
        return AuditRun(
            operation=payload.operation,
            run_id=payload.run_id,
            subject_id=payload.subject_id,
            release_id=payload.release_id,
            release_instance_sha256=release_instance_sha256,
            request_sha256=payload.request_sha256,
            intent_sequence=receipt.sequence,
            intent_event_hash=receipt.event_hash,
        )

    def append_assessment_completed(
        self, run: AuditRun, report: AssessmentReport
    ) -> AuditEventReceipt:
        if run.operation != "assessment":
            raise IntegrityError("an optimization intent cannot complete an assessment")
        if report.release_id != run.subject_id:
            raise IntegrityError("assessment report release does not match the intent")
        return self._append_completed(
            run,
            event_type="assessment_completed",
            result_id=report.assessment_id,
            request_sha256=report.request_sha256,
            outcome=report.overall_verdict.value,
            report=report,
        )

    def append_optimization_completed(
        self, run: AuditRun, report: OptimizationReport
    ) -> AuditEventReceipt:
        if run.operation != "optimization":
            raise IntegrityError("an assessment intent cannot complete an optimization")
        if report.optimization_id != run.subject_id:
            raise IntegrityError("optimization report does not match the intent")
        return self._append_completed(
            run,
            event_type="optimization_completed",
            result_id=report.optimization_id,
            request_sha256=report.request_sha256,
            outcome=report.outcome.value,
            report=report,
        )

    def append_assessment_failed(
        self,
        run: AuditRun,
        error_code: str,
        error_message: str = "",
    ) -> AuditEventReceipt:
        if run.operation != "assessment":
            raise IntegrityError("an optimization intent cannot fail as an assessment")
        return self._append_failed(run, "assessment_failed", error_code, error_message)

    def append_optimization_failed(
        self,
        run: AuditRun,
        error_code: str,
        error_message: str = "",
    ) -> AuditEventReceipt:
        if run.operation != "optimization":
            raise IntegrityError("an assessment intent cannot fail as an optimization")
        return self._append_failed(run, "optimization_failed", error_code, error_message)

    def _append_completed(
        self,
        run: AuditRun,
        *,
        event_type: str,
        result_id: str,
        request_sha256: str,
        outcome: str,
        report: AssessmentReport | OptimizationReport,
    ) -> AuditEventReceipt:
        if request_sha256 != run.request_sha256:
            raise IntegrityError("completion report binds a different request than the intent")
        report_model = (
            AssessmentReport if run.operation == "assessment" else OptimizationReport
        )
        report_json = _validated_document_text(
            report, report_model, f"{run.operation} completion report"
        )
        report_raw = _canonical_object(report_json, f"{run.operation} completion report")
        payload = _AuditCompletedPayload(
            operation=run.operation,
            run_id=run.run_id,
            subject_id=run.subject_id,
            release_id=run.release_id,
            release_instance_sha256=run.release_instance_sha256,
            request_sha256=run.request_sha256,
            intent_event_hash=run.intent_event_hash,
            binding_sha256=_binding_sha256(
                run.operation, report_raw, report=True
            ),
            result_id=result_id,
            report_sha256=sha256_bytes(report_json.encode("utf-8")),
            report_json=report_json,
            outcome=outcome,
            result_expires_at=(
                report.expires_at if run.operation == "optimization" else None
            ),
        )
        return self._append_v2_event(
            event_type, run.subject_id, payload, run.run_id, terminal_run=run
        )

    def _append_failed(
        self,
        run: AuditRun,
        event_type: str,
        error_code: str,
        error_message: str,
    ) -> AuditEventReceipt:
        payload = _AuditFailedPayload(
            operation=run.operation,
            run_id=run.run_id,
            subject_id=run.subject_id,
            release_id=run.release_id,
            release_instance_sha256=run.release_instance_sha256,
            request_sha256=run.request_sha256,
            intent_event_hash=run.intent_event_hash,
            error_code=error_code,
            error_message=error_message,
        )
        return self._append_v2_event(
            event_type, run.subject_id, payload, run.run_id, terminal_run=run
        )

    def _append_legacy_event(
        self,
        event_type: str,
        record_id: str,
        report: AssessmentReport | OptimizationReport,
    ) -> str:
        receipt = self._append_payload(
            event_type,
            record_id,
            canonical_json_bytes(report).decode("utf-8"),
        )
        return receipt[3]

    def _append_v2_event(
        self,
        event_type: str,
        record_id: str,
        payload: _AuditIntentPayload | _AuditCompletedPayload | _AuditFailedPayload,
        run_id: uuid.UUID,
        *,
        terminal_run: AuditRun | None = None,
    ) -> AuditEventReceipt:
        sequence, occurred_at, previous_hash, event_hash = self._append_payload(
            event_type,
            record_id,
            _canonical_json_text(payload),
            terminal_run=terminal_run,
        )
        operation = (
            _INTENT_EVENT_TYPES.get(event_type)
            or _COMPLETED_EVENT_TYPES.get(event_type)
            or _FAILED_EVENT_TYPES.get(event_type)
        )
        assert operation is not None
        return AuditEventReceipt(
            operation=operation,
            run_id=run_id,
            event_type=event_type,
            hash_format=_AUDIT_EVENT_HASH_FORMAT,
            sequence=sequence,
            occurred_at=datetime.fromisoformat(occurred_at),
            previous_hash=previous_hash,
            event_hash=event_hash,
        )

    def _append_payload(
        self,
        event_type: str,
        record_id: str,
        payload_json: str,
        *,
        terminal_run: AuditRun | None = None,
    ) -> tuple[int, str, str, str]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            occurred_at = datetime.now(timezone.utc).isoformat()
            ledger_row = connection.execute(
                "SELECT value FROM audit_metadata WHERE key = 'ledger_id'"
            ).fetchone()
            if ledger_row is None:
                raise IntegrityError("audit database has no ledger identifier")
            try:
                ledger_id = uuid.UUID(ledger_row[0])
            except (ValueError, TypeError) as exc:
                raise IntegrityError("audit ledger identifier is invalid") from exc
            if terminal_run is not None:
                intent = self._validate_open_run(connection, terminal_run)
                terminal_model = (
                    _AuditCompletedPayload
                    if event_type in _COMPLETED_EVENT_TYPES
                    else _AuditFailedPayload
                )
                terminal = self._parse_payload(
                    terminal_model, payload_json, event_type
                )
                if (
                    terminal.intent_event_hash != terminal_run.intent_event_hash
                    or terminal.operation != intent.operation
                    or terminal.subject_id != intent.subject_id
                    or terminal.release_id != intent.release_id
                    or terminal.release_instance_sha256
                    != intent.release_instance_sha256
                    or terminal.request_sha256 != intent.request_sha256
                    or (
                        isinstance(terminal, _AuditCompletedPayload)
                        and terminal.binding_sha256 != intent.binding_sha256
                    )
                    or (
                        isinstance(terminal, _AuditCompletedPayload)
                        and terminal.operation == "optimization"
                        and (
                            intent.authorization_expires_at is None
                            or terminal.result_expires_at is None
                            or terminal.result_expires_at
                            > intent.authorization_expires_at
                        )
                    )
                ):
                    raise IntegrityError("audit terminal event does not bind its intent")
            count, minimum, maximum = connection.execute(
                "SELECT COUNT(*), MIN(sequence), MAX(sequence) FROM audit_events"
            ).fetchone()
            if count and (minimum != 1 or maximum != count):
                raise IntegrityError(
                    "audit sequence is not contiguous; refusing to extend a corrupt chain"
                )
            row = connection.execute(
                "SELECT sequence, event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            last_sequence, previous = (row[0], row[1]) if row else (0, GENESIS)
            if last_sequence != count:
                raise IntegrityError(
                    "audit sequence is not contiguous; refusing to extend a corrupt chain"
                )
            allocated = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'audit_events'"
            ).fetchone()
            if allocated is not None and allocated[0] != last_sequence:
                raise IntegrityError(
                    "audit sequence metadata does not match the chain tail; possible truncation"
                )
            sequence = last_sequence + 1
            event_hash = sha256_bytes(
                _event_material_v2(
                    ledger_id,
                    occurred_at,
                    event_type,
                    record_id,
                    payload_json,
                    previous,
                )
            )
            connection.execute(
                """
                INSERT INTO audit_events
                (sequence, occurred_at, event_type, assessment_id, payload_json,
                 previous_hash, event_hash, hash_format)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    occurred_at,
                    event_type,
                    record_id,
                    payload_json,
                    previous,
                    event_hash,
                    _AUDIT_EVENT_HASH_FORMAT,
                ),
            )
        return sequence, occurred_at, previous, event_hash

    def _validate_open_run(
        self, connection: sqlite3.Connection, run: AuditRun
    ) -> _AuditIntentPayload:
        row = connection.execute(
            """
            SELECT sequence, occurred_at, event_type, assessment_id, payload_json,
                   previous_hash, event_hash, hash_format
            FROM audit_events WHERE event_hash = ?
            """,
            (run.intent_event_hash,),
        ).fetchone()
        if row is None:
            raise IntegrityError("audit intent is absent from this ledger")
        (
            sequence,
            occurred_at,
            event_type,
            record_id,
            payload_json,
            previous_hash,
            event_hash,
            hash_format,
        ) = row
        expected_event = f"{run.operation}_intent"
        if sequence != run.intent_sequence or event_type != expected_event:
            raise IntegrityError("audit run handle does not identify its intent event")
        if hash_format == _AUDIT_EVENT_HASH_FORMAT:
            ledger_row = connection.execute(
                "SELECT value FROM audit_metadata WHERE key = 'ledger_id'"
            ).fetchone()
            if ledger_row is None:
                raise IntegrityError("audit database has no ledger identifier")
            material = _event_material_v2(
                ledger_row[0],
                occurred_at,
                event_type,
                record_id,
                payload_json,
                previous_hash,
            )
        elif hash_format in {None, _LEGACY_EVENT_HASH_FORMAT}:
            material = _event_material(
                occurred_at,
                event_type,
                record_id,
                payload_json,
                previous_hash,
            )
        else:
            raise IntegrityError(f"unknown audit event hash format: {hash_format}")
        if sha256_bytes(material) != event_hash:
            raise IntegrityError("audit intent event hash does not replay")
        intent = self._parse_payload(_AuditIntentPayload, payload_json, event_type)
        try:
            event_time = datetime.fromisoformat(occurred_at)
        except (TypeError, ValueError) as exc:
            raise IntegrityError("audit intent timestamp is invalid") from exc
        if event_time.utcoffset() is None:
            raise IntegrityError("audit intent timestamp is timezone-naive")
        _validate_replayed_request(intent.operation, intent.request_json, event_time)
        if (
            record_id != run.subject_id
            or intent.run_id != run.run_id
            or intent.operation != run.operation
            or intent.subject_id != run.subject_id
            or intent.release_id != run.release_id
            or intent.release_instance_sha256 != run.release_instance_sha256
            or intent.request_sha256 != run.request_sha256
        ):
            raise IntegrityError("audit run handle does not match the stored intent")
        for terminal_type, terminal_json in connection.execute(
            """
            SELECT event_type, payload_json FROM audit_events
            WHERE event_type IN (?, ?, ?, ?)
            """,
            tuple(sorted(_TERMINAL_EVENT_TYPES)),
        ):
            model = (
                _AuditCompletedPayload
                if terminal_type in _COMPLETED_EVENT_TYPES
                else _AuditFailedPayload
            )
            terminal = self._parse_payload(model, terminal_json, terminal_type)
            if terminal.run_id == run.run_id:
                raise IntegrityError("audit intent already has a terminal event")
        return intent

    @staticmethod
    def _parse_payload(model, payload_json: str, event_type: str):
        try:
            parsed = model.model_validate_json(payload_json)
        except (ValidationError, ValueError) as exc:
            raise IntegrityError(f"invalid {event_type} audit payload: {exc}") from exc
        if _canonical_json_text(parsed) != payload_json:
            raise IntegrityError(f"invalid {event_type} audit payload: non-canonical JSON")
        return parsed

    def verify(
        self,
        require_events: bool = False,
        *,
        require_complete: bool = True,
        allow_legacy_hashes: bool = False,
        expected_event_count: int | None = None,
        expected_head_sha256: str | None = None,
        expected_ledger_id: uuid.UUID | str | None = None,
        expected_release_id: str | None = None,
    ) -> AuditVerification:
        if expected_event_count is not None and expected_event_count < 0:
            raise ValueError("expected audit event count cannot be negative")
        if expected_head_sha256 is not None and (
            len(expected_head_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_head_sha256)
        ):
            raise ValueError("expected audit head must be a lowercase SHA-256 digest")

        previous = GENESIS
        count = 0
        intents: dict[uuid.UUID, tuple[str, _AuditIntentPayload]] = {}
        terminals: dict[uuid.UUID, str] = {}
        completed_count = 0
        failed_count = 0
        legacy_event_count = 0
        legacy_hash_event_count = 0
        domain_separated_hash_event_count = 0
        release_ids: set[str] = set()
        release_instance_sha256s: set[str] = set()
        with self._read_connect() as connection:
            try:
                ledger_row = connection.execute(
                    "SELECT value FROM audit_metadata WHERE key = 'ledger_id'"
                ).fetchone()
            except sqlite3.Error as exc:
                raise IntegrityError("audit database has no readable metadata") from exc
            if ledger_row is None:
                raise IntegrityError("audit database has no ledger identifier")
            try:
                ledger_id = uuid.UUID(ledger_row[0])
            except (ValueError, TypeError) as exc:
                raise IntegrityError("audit ledger identifier is invalid") from exc
            rows = connection.execute(
                """
                SELECT sequence, occurred_at, event_type, assessment_id,
                       payload_json, previous_hash, event_hash, hash_format
                FROM audit_events ORDER BY sequence
                """
            )
            for (
                sequence,
                occurred_at,
                event_type,
                record_id,
                payload_json,
                stored_previous,
                stored_hash,
                hash_format,
            ) in rows:
                expected_sequence = count + 1
                if sequence != expected_sequence:
                    raise IntegrityError(
                        f"audit sequence is not contiguous at event {expected_sequence}"
                    )
                try:
                    event_time = datetime.fromisoformat(occurred_at)
                except (TypeError, ValueError) as exc:
                    raise IntegrityError(
                        f"audit event {expected_sequence} has an invalid timestamp"
                    ) from exc
                if event_time.utcoffset() is None:
                    raise IntegrityError(
                        f"audit event {expected_sequence} has a timezone-naive timestamp"
                    )
                if stored_previous != previous:
                    raise IntegrityError(
                        f"audit-chain predecessor mismatch at event {expected_sequence}"
                    )
                if hash_format == _AUDIT_EVENT_HASH_FORMAT:
                    try:
                        material = _event_material_v2(
                            ledger_id,
                            occurred_at,
                            event_type,
                            record_id,
                            payload_json,
                            stored_previous,
                        )
                    except (TypeError, ValueError) as exc:
                        raise IntegrityError(
                            f"invalid domain-separated audit event {expected_sequence}: {exc}"
                        ) from exc
                    domain_separated_hash_event_count += 1
                    _, _, release_id, release_instance_sha256 = _event_hash_context(
                        event_type, record_id, payload_json
                    )
                    if release_id is not None:
                        release_ids.add(release_id)
                    release_instance_sha256s.add(release_instance_sha256)
                elif hash_format in {None, _LEGACY_EVENT_HASH_FORMAT}:
                    legacy_hash_event_count += 1
                    if not allow_legacy_hashes:
                        raise IntegrityError(
                            "audit chain contains a legacy event hash; "
                            "explicit legacy replay is required"
                        )
                    material = _event_material(
                        occurred_at,
                        event_type,
                        record_id,
                        payload_json,
                        stored_previous,
                    )
                else:
                    raise IntegrityError(
                        f"unknown audit event hash format: {hash_format}"
                    )
                actual = sha256_bytes(material)
                if actual != stored_hash:
                    raise IntegrityError(
                        f"audit-chain hash mismatch at event {expected_sequence}"
                    )

                if event_type in _LEGACY_EVENT_TYPES:
                    legacy_event_count += 1
                    try:
                        _, _, release_id, release_instance_sha256 = (
                            _event_hash_context(event_type, record_id, payload_json)
                        )
                    except (TypeError, ValueError) as exc:
                        raise IntegrityError(
                            f"invalid legacy audit payload: {exc}"
                        ) from exc
                    if release_id is not None:
                        release_ids.add(release_id)
                    release_instance_sha256s.add(release_instance_sha256)
                elif event_type in _INTENT_EVENT_TYPES:
                    intent = self._parse_payload(
                        _AuditIntentPayload, payload_json, event_type
                    )
                    _validate_replayed_request(
                        intent.operation, intent.request_json, event_time
                    )
                    if intent.operation != _INTENT_EVENT_TYPES[event_type]:
                        raise IntegrityError(
                            "audit intent operation disagrees with its event type"
                        )
                    if record_id != intent.subject_id:
                        raise IntegrityError("audit intent subject disagrees with its event row")
                    request_raw = _canonical_object(
                        intent.request_json, f"{intent.operation} request"
                    )
                    release_id, release_instance_sha256 = _intent_release_identity(
                        intent.operation, request_raw
                    )
                    if intent.release_id is not None and intent.release_id != release_id:
                        raise IntegrityError(
                            "audit intent release ID disagrees with its request"
                        )
                    if (
                        intent.release_instance_sha256 is not None
                        and intent.release_instance_sha256
                        != release_instance_sha256
                    ):
                        raise IntegrityError(
                            "audit intent release instance disagrees with its request"
                        )
                    if release_id is not None:
                        release_ids.add(release_id)
                    release_instance_sha256s.add(release_instance_sha256)
                    if intent.run_id in intents:
                        raise IntegrityError("audit chain contains a duplicate run identifier")
                    intents[intent.run_id] = (stored_hash, intent)
                elif event_type in _TERMINAL_EVENT_TYPES:
                    completed = event_type in _COMPLETED_EVENT_TYPES
                    model = _AuditCompletedPayload if completed else _AuditFailedPayload
                    terminal = self._parse_payload(model, payload_json, event_type)
                    expected_operation = (
                        _COMPLETED_EVENT_TYPES.get(event_type)
                        or _FAILED_EVENT_TYPES[event_type]
                    )
                    if terminal.operation != expected_operation:
                        raise IntegrityError(
                            "audit terminal operation disagrees with its event type"
                        )
                    if record_id != terminal.subject_id:
                        raise IntegrityError("audit terminal subject disagrees with its event row")
                    stored_intent = intents.get(terminal.run_id)
                    if stored_intent is None:
                        raise IntegrityError("audit terminal event has no preceding intent")
                    intent_hash, intent = stored_intent
                    if terminal.run_id in terminals:
                        raise IntegrityError("audit intent has more than one terminal event")
                    if (
                        terminal.intent_event_hash != intent_hash
                        or terminal.operation != intent.operation
                        or terminal.subject_id != intent.subject_id
                        or terminal.release_id != intent.release_id
                        or terminal.release_instance_sha256
                        != intent.release_instance_sha256
                        or terminal.request_sha256 != intent.request_sha256
                        or (
                            completed
                            and terminal.binding_sha256 != intent.binding_sha256
                        )
                        or (
                            completed
                            and terminal.operation == "optimization"
                            and (
                                intent.authorization_expires_at is None
                                or terminal.result_expires_at is None
                                or terminal.result_expires_at
                                > intent.authorization_expires_at
                            )
                        )
                    ):
                        raise IntegrityError("audit terminal event does not bind its intent")
                    terminals[terminal.run_id] = event_type
                    if completed:
                        completed_count += 1
                    else:
                        failed_count += 1
                else:
                    raise IntegrityError(f"unknown audit event type: {event_type}")

                previous = stored_hash
                count += 1

            allocated = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'audit_events'"
            ).fetchone()
            if allocated is not None and allocated[0] != count:
                raise IntegrityError(
                    "audit sequence metadata does not match the chain tail; possible truncation"
                )

        if require_events and count == 0:
            raise IntegrityError("audit database contains no events")
        if expected_event_count is not None and count != expected_event_count:
            raise IntegrityError(
                f"audit event count mismatch: expected {expected_event_count}, got {count}"
            )
        if expected_head_sha256 is not None and previous != expected_head_sha256:
            raise IntegrityError(
                f"audit head mismatch: expected {expected_head_sha256}, got {previous}"
            )
        if expected_ledger_id is not None and ledger_id != uuid.UUID(str(expected_ledger_id)):
            raise IntegrityError("audit ledger identifier does not match the expected ledger")
        if expected_release_id is not None and expected_release_id not in release_ids:
            raise IntegrityError(
                "audit chain does not contain the expected release identifier"
            )

        orphaned = tuple(
            sorted((run_id for run_id in intents if run_id not in terminals), key=str)
        )
        if require_complete and orphaned:
            joined = ", ".join(str(run_id) for run_id in orphaned)
            raise IntegrityError(f"audit chain contains orphaned intent(s): {joined}")
        return AuditVerification(
            ledger_id=ledger_id,
            event_count=count,
            last_sequence=count,
            head_sha256=previous,
            legacy_event_count=legacy_event_count,
            legacy_hash_event_count=legacy_hash_event_count,
            domain_separated_hash_event_count=domain_separated_hash_event_count,
            intent_count=len(intents),
            completed_count=completed_count,
            failed_count=failed_count,
            release_ids=tuple(sorted(release_ids)),
            release_instance_sha256s=tuple(sorted(release_instance_sha256s)),
            orphaned_run_ids=orphaned,
            complete=not orphaned,
            runtime_identity=current_runtime_identity(
                component_id="audit_verifier",
                component_version="AuditVerification/2.0",
                algorithm_profile={
                    "canonicalization": "MRA-PY-JSON-1",
                    "event_hash_format": _AUDIT_EVENT_HASH_FORMAT,
                    "legacy_event_hash_format": _LEGACY_EVENT_HASH_FORMAT,
                    "legacy_hash_default": "reject",
                    "release_identity": "explicit-release-id-and-instance-sha256",
                },
            ),
        )

    def verify_chain(
        self,
        require_events: bool = False,
        *,
        require_complete: bool = True,
        allow_legacy_hashes: bool = False,
        expected_event_count: int | None = None,
        expected_head_sha256: str | None = None,
    ) -> int:
        """Backward-compatible count result over the stricter structured replay."""
        return self.verify(
            require_events=require_events,
            require_complete=require_complete,
            allow_legacy_hashes=allow_legacy_hashes,
            expected_event_count=expected_event_count,
            expected_head_sha256=expected_head_sha256,
        ).event_count

    def export_checkpoint(
        self,
        *,
        require_events: bool = False,
        require_complete: bool = True,
    ) -> AuditCheckpoint:
        verification = self.verify(
            require_events=require_events,
            require_complete=require_complete,
        )
        return AuditCheckpoint(
            ledger_id=verification.ledger_id,
            event_count=verification.event_count,
            last_sequence=verification.last_sequence,
            head_sha256=verification.head_sha256,
            created_at=datetime.now(timezone.utc),
        )
