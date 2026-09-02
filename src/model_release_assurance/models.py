from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .runtime_identity import RuntimeIdentity


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


def _canonical_model_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_model_sha256(value: BaseModel) -> str:
    return hashlib.sha256(_canonical_model_bytes(value)).hexdigest()


class ThreatKind(StrEnum):
    LINKAGE = "linkage"
    MEMBERSHIP = "membership"
    ATTRIBUTE = "attribute"
    RECONSTRUCTION = "reconstruction"


class EvidenceClass(StrEnum):
    EXACT = "exact"
    CEILING = "ceiling"
    FLOOR = "floor"
    SCREEN = "screen"


class EvidenceCoverage(StrEnum):
    COMPLETE_INTERFACE = "complete_interface"
    NAMED_PROJECTION = "named_projection"
    SCREEN_ONLY = "screen_only"


class Realizability(StrEnum):
    RECIPIENT = "recipient_realizable"
    AUDITOR_ONLY = "auditor_only"
    POPULATION_MODEL = "population_model"
    NOT_APPLICABLE = "not_applicable"


class Verdict(StrEnum):
    CLEAR = "clear"
    BLOCK = "block"
    INCONCLUSIVE = "inconclusive"


class OverallVerdict(StrEnum):
    CLEAR = "clear"
    BLOCK = "block"
    INCONCLUSIVE = "inconclusive"


class EvidenceConsistency(StrEnum):
    CONSISTENT = "consistent"
    INSUFFICIENT = "insufficient"
    CONTRADICTORY = "contradictory"


class PopulationUnitKind(StrEnum):
    PERSON = "person"
    HOUSEHOLD = "household"
    ORGANIZATION = "organization"
    ESTABLISHMENT = "establishment"
    RECORD = "record"
    DEVICE = "device"
    TRANSACTION = "transaction"
    EVENT = "event"
    SESSION = "session"
    CUSTOM = "custom"


class PopulationSizeBasis(StrEnum):
    EXACT_REGISTRY = "exact_registry"
    BOUNDED_ESTIMATE = "bounded_estimate"
    POINT_ESTIMATE = "point_estimate"
    OPEN_DYNAMIC = "open_dynamic"


class PopulationSize(StrictModel):
    basis: PopulationSizeBasis
    lower_bound: int | None = Field(default=None, ge=0)
    point_estimate: int | None = Field(default=None, ge=0)
    upper_bound: int | None = Field(default=None, ge=0)
    source: str = Field(min_length=1, max_length=2048)
    measured_at: datetime

    @model_validator(mode="after")
    def size_statement_is_coherent(self) -> PopulationSize:
        if self.measured_at.utcoffset() is None:
            raise ValueError("population size measured_at must include a timezone offset")
        values = [value for value in (self.lower_bound, self.point_estimate, self.upper_bound) if value is not None]
        if values != sorted(values):
            raise ValueError("population size must satisfy lower_bound <= point_estimate <= upper_bound")
        if self.basis is PopulationSizeBasis.EXACT_REGISTRY:
            if self.point_estimate is None:
                raise ValueError("exact_registry requires point_estimate")
            if self.lower_bound not in (None, self.point_estimate) or self.upper_bound not in (None, self.point_estimate):
                raise ValueError("exact_registry bounds must equal point_estimate")
        elif self.basis is PopulationSizeBasis.BOUNDED_ESTIMATE:
            if self.lower_bound is None or self.upper_bound is None:
                raise ValueError("bounded_estimate requires lower_bound and upper_bound")
        elif self.basis is PopulationSizeBasis.POINT_ESTIMATE and self.point_estimate is None:
            raise ValueError("point_estimate basis requires point_estimate")
        return self


class PopulationScope(StrictModel):
    scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str = Field(min_length=1, max_length=256)
    unit_kind: PopulationUnitKind
    custom_unit_definition: str | None = Field(default=None, min_length=1, max_length=1024)
    universe_definition: str = Field(min_length=1, max_length=4096)
    inclusion_criteria: tuple[str, ...] = Field(min_length=1)
    exclusion_criteria: tuple[str, ...] = ()
    jurisdictions: tuple[str, ...] = Field(min_length=1)
    reference_date: date
    valid_until: date | None = None
    population_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    size: PopulationSize
    subgroup_dimensions: tuple[str, ...] = ()
    data_steward: str = Field(min_length=1, max_length=256)
    notes: str = ""

    @model_validator(mode="after")
    def population_definition_is_complete(self) -> PopulationScope:
        if self.unit_kind is PopulationUnitKind.CUSTOM and self.custom_unit_definition is None:
            raise ValueError("custom population unit requires custom_unit_definition")
        if self.unit_kind is not PopulationUnitKind.CUSTOM and self.custom_unit_definition is not None:
            raise ValueError("custom_unit_definition is only valid for a custom population unit")
        if len(set(self.jurisdictions)) != len(self.jurisdictions):
            raise ValueError("population jurisdictions must be unique")
        if len(set(self.subgroup_dimensions)) != len(self.subgroup_dimensions):
            raise ValueError("population subgroup dimensions must be unique")
        if self.valid_until is not None and self.valid_until < self.reference_date:
            raise ValueError("population valid_until cannot precede reference_date")
        return self


DecisionMetric = Literal[
    "bayes_linkage_success",
    "incremental_bayes_linkage_success",
    "worst_observation_success",
    "membership_tpr_at_fpr",
    "equal_prior_membership_success",
    "finite_secret_exact_guess_success",
    "attribute_attack_success",
    "incremental_attribute_attack_success",
    "reconstruction_success",
    "incremental_reconstruction_success",
]


class LlmProtocolContract(StrictModel):
    schema_version: Literal["1.0"]
    model_provider: str = Field(min_length=1, max_length=256)
    model_identifier: str = Field(min_length=1, max_length=256)
    model_version: str = Field(min_length=1, max_length=256)
    tokenizer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decoding_parameters: dict[str, str | int | float | bool] = Field(min_length=1)
    system_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_sha256s: tuple[str, ...]
    retrieval_corpus_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    retriever_config_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    tool_names: tuple[str, ...]
    tool_policy_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    memory_mode: Literal["none", "session", "persistent"]
    memory_ttl_seconds: int | None = Field(ge=0)
    logging_mode: Literal["none", "security_only", "full_transcript"]
    provider_retention_days: int = Field(ge=0)
    maximum_session_tokens: int = Field(gt=0)
    maximum_lifetime_queries: int = Field(gt=0)
    maximum_concurrent_sessions: int = Field(gt=0)
    reset_semantics: str = Field(min_length=1, max_length=2048)
    filter_bundle_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    update_policy: Literal["immutable", "versioned_reassessment_required"]
    valid_until: datetime

    @model_validator(mode="after")
    def interactive_protocol_is_complete(self) -> LlmProtocolContract:
        if self.valid_until.utcoffset() is None:
            raise ValueError("LLM protocol valid_until must include a timezone offset")
        if (self.retrieval_corpus_sha256 is None) != (self.retriever_config_sha256 is None):
            raise ValueError("retrieval corpus and retriever configuration hashes must be supplied together")
        if self.tool_names and self.tool_policy_sha256 is None:
            raise ValueError("tool-enabled LLM protocols require a tool-policy hash")
        if self.memory_mode == "none" and self.memory_ttl_seconds not in (None, 0):
            raise ValueError("stateless LLM protocols cannot declare a positive memory TTL")
        if self.memory_mode in ("session", "persistent") and (
            self.memory_ttl_seconds is None or self.memory_ttl_seconds <= 0
        ):
            raise ValueError("stateful LLM protocols require a positive memory TTL")
        if len(set(self.tool_names)) != len(self.tool_names):
            raise ValueError("LLM tool names must be unique")
        if len(set(self.adapter_sha256s)) != len(self.adapter_sha256s):
            raise ValueError("LLM adapter hashes must be unique")
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in self.adapter_sha256s
        ):
            raise ValueError("LLM adapter hashes must be lowercase SHA-256 digests")
        return self


class ModelTask(StrEnum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    RANKING = "ranking"
    RECOMMENDATION = "recommendation"
    FORECASTING = "forecasting"
    CLUSTERING = "clustering"
    ANOMALY_DETECTION = "anomaly_detection"
    REPRESENTATION = "representation"
    GENERATION = "generation"
    RETRIEVAL = "retrieval"
    CONTROL = "control"
    DECISION_SUPPORT = "decision_support"
    CUSTOM = "custom"


class DataModality(StrEnum):
    TABULAR = "tabular"
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TIME_SERIES = "time_series"
    GRAPH = "graph"
    GEOSPATIAL = "geospatial"
    EMBEDDING = "embedding"
    ACTION = "action"
    MULTIMODAL = "multimodal"
    CUSTOM = "custom"


class TrainingParadigm(StrEnum):
    SUPERVISED = "supervised"
    SEMI_SUPERVISED = "semi_supervised"
    SELF_SUPERVISED = "self_supervised"
    UNSUPERVISED = "unsupervised"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    IN_CONTEXT_OR_PROMPTED = "in_context_or_prompted"
    HYBRID = "hybrid"
    CUSTOM = "custom"


class ModelProfile(StrictModel):
    task: ModelTask
    input_modalities: tuple[DataModality, ...] = Field(min_length=1)
    output_modalities: tuple[DataModality, ...] = Field(min_length=1)
    training_paradigm: TrainingParadigm
    component_model_families: tuple[str, ...] = ()
    generative: bool = False
    stateful: bool = False
    custom_task_definition: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def profile_is_complete(self) -> ModelProfile:
        if len(set(self.input_modalities)) != len(self.input_modalities):
            raise ValueError("model input modalities must be unique")
        if len(set(self.output_modalities)) != len(self.output_modalities):
            raise ValueError("model output modalities must be unique")
        if len(set(self.component_model_families)) != len(self.component_model_families):
            raise ValueError("component model families must be unique")
        if self.task is ModelTask.CUSTOM and self.custom_task_definition is None:
            raise ValueError("custom model tasks require custom_task_definition")
        if self.task is not ModelTask.CUSTOM and self.custom_task_definition is not None:
            raise ValueError("custom_task_definition is only valid for custom tasks")
        return self


class OutputChannelContract(StrictModel):
    """Explicit inventory of every recipient-observable response or shipped output."""

    aggregates: bool
    labels: bool
    scores: bool
    probabilities: bool
    logits: bool
    explanations: bool
    text: bool
    embeddings: bool
    gradients: bool
    parameters: bool
    downloadable_files: tuple[str, ...]
    shipped_summary_metadata: tuple[str, ...]
    custom_channels: tuple[str, ...]

    @model_validator(mode="after")
    def output_inventory_is_coherent(self) -> OutputChannelContract:
        named = self.downloadable_files + self.shipped_summary_metadata + self.custom_channels
        if len(named) != len(set(named)):
            raise ValueError("output-channel names must be unique across file, summary, and custom channels")
        boolean_channels = (
            self.aggregates,
            self.labels,
            self.scores,
            self.probabilities,
            self.logits,
            self.explanations,
            self.text,
            self.embeddings,
            self.gradients,
            self.parameters,
        )
        if not any(boolean_channels) and not named:
            raise ValueError("an interface must declare at least one recipient-observable output channel")
        return self


class TimingChannelContract(StrictModel):
    """Declaration of recipient-observable latency and its mitigation."""

    recipient_observable: bool
    measurement_resolution_milliseconds: float | None = Field(ge=0.0)
    includes_queue_time: bool
    mitigation: Literal["not_applicable", "none", "bucketed", "padded", "constant_time_target"]
    mitigation_parameters: dict[str, str | int | float | bool]

    @model_validator(mode="after")
    def timing_declaration_is_coherent(self) -> TimingChannelContract:
        if self.recipient_observable:
            if self.measurement_resolution_milliseconds is None:
                raise ValueError("observable timing requires an explicit measurement resolution")
            if self.mitigation == "not_applicable":
                raise ValueError("observable timing cannot use not_applicable mitigation")
        elif (
            self.measurement_resolution_milliseconds is not None
            or self.includes_queue_time
            or self.mitigation != "not_applicable"
            or self.mitigation_parameters
        ):
            raise ValueError("a non-observable timing channel must be explicitly not_applicable")
        if self.mitigation in {"bucketed", "padded", "constant_time_target"} and not self.mitigation_parameters:
            raise ValueError("timing mitigation requires its public parameters")
        if self.mitigation in {"not_applicable", "none"} and self.mitigation_parameters:
            raise ValueError("timing parameters are only valid for an active mitigation")
        return self


class ErrorChannelContract(StrictModel):
    """Declaration of transport status, errors, and retry signals."""

    transport_status: Literal["none", "http", "grpc", "custom"]
    documented_status_codes: tuple[str, ...]
    error_content: Literal["none", "opaque", "structured", "free_text"]
    error_schema_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    retry_metadata: bool

    @model_validator(mode="after")
    def error_declaration_is_coherent(self) -> ErrorChannelContract:
        if len(self.documented_status_codes) != len(set(self.documented_status_codes)):
            raise ValueError("documented status codes must be unique")
        if self.transport_status == "none":
            if self.documented_status_codes or self.error_content != "none" or self.error_schema_sha256 is not None:
                raise ValueError("an interface without transport status cannot expose status or error content")
            if self.retry_metadata:
                raise ValueError("an interface without transport status cannot expose retry metadata")
        elif not self.documented_status_codes:
            raise ValueError("a status-bearing transport requires its documented status codes")
        if self.error_content == "structured" and self.error_schema_sha256 is None:
            raise ValueError("structured errors require an error-schema digest")
        if self.error_content != "structured" and self.error_schema_sha256 is not None:
            raise ValueError("error_schema_sha256 is only valid for structured errors")
        return self


class ExecutionChannelContract(StrictModel):
    """Batch, concurrency, and cross-request-state semantics."""

    batching: Literal["none", "fixed", "variable", "recipient_controlled"]
    maximum_batch_size: int | None = Field(gt=0)
    maximum_concurrent_requests: int | None = Field(gt=0)
    cross_request_state: Literal["none", "session", "persistent"]
    cross_request_state_ttl_seconds: int | None = Field(ge=0)

    @model_validator(mode="after")
    def execution_declaration_is_coherent(self) -> ExecutionChannelContract:
        if self.batching == "none" and self.maximum_batch_size != 1:
            raise ValueError("non-batched interfaces must declare maximum_batch_size=1")
        if self.batching in {"fixed", "variable"} and (
            self.maximum_batch_size is None or self.maximum_batch_size < 2
        ):
            raise ValueError("batched interfaces must allow a batch of at least two")
        if self.batching == "recipient_controlled" and self.maximum_batch_size is not None:
            raise ValueError("recipient-controlled batching must not claim an enforced maximum")
        if self.cross_request_state == "none" and self.cross_request_state_ttl_seconds not in (None, 0):
            raise ValueError("stateless interfaces cannot declare a positive cross-request-state TTL")
        if self.cross_request_state == "session" and (
            self.cross_request_state_ttl_seconds is None or self.cross_request_state_ttl_seconds <= 0
        ):
            raise ValueError("session state requires a positive TTL")
        return self


class RateLimitContract(StrictModel):
    """Complete recipient-visible and enforcement semantics for request limiting."""

    enabled: bool
    scope: Literal["none", "per_identity", "per_ip", "per_session", "global", "custom"]
    requests_per_window: int | None = Field(gt=0)
    window_seconds: int | None = Field(gt=0)
    burst_capacity: int | None = Field(gt=0)
    retry_after_exposed: bool
    enforcement: Literal[
        "not_applicable",
        "local",
        "shared_strong",
        "shared_eventual",
        "custom",
    ]
    custom_parameters: dict[str, str | int | float | bool]

    @model_validator(mode="after")
    def rate_limit_is_complete(self) -> RateLimitContract:
        if self.enabled:
            if self.scope == "none" or self.enforcement == "not_applicable":
                raise ValueError(
                    "enabled rate limiting requires a scope and enforcement model"
                )
            if self.requests_per_window is None or self.window_seconds is None:
                raise ValueError(
                    "enabled rate limiting requires a request count and window"
                )
            if self.burst_capacity is None:
                raise ValueError("enabled rate limiting requires a burst capacity")
        elif (
            self.scope != "none"
            or self.requests_per_window is not None
            or self.window_seconds is not None
            or self.burst_capacity is not None
            or self.retry_after_exposed
            or self.enforcement != "not_applicable"
            or self.custom_parameters
        ):
            raise ValueError(
                "disabled rate limiting must explicitly declare no enforcement behavior"
            )
        custom_selected = self.scope == "custom" or self.enforcement == "custom"
        if custom_selected != bool(self.custom_parameters):
            raise ValueError(
                "custom rate-limit parameters must be present exactly for a custom mode"
            )
        return self


class AccessPathContract(StrictModel):
    """Non-primary paths through which a recipient could observe or control the release."""

    side_channels: tuple[
        Literal["timing", "status_code", "error_content", "resource_usage", "cache_behavior", "logs", "telemetry", "custom"],
        ...,
    ]
    custom_side_channels: tuple[str, ...]
    admin_access: Literal["none", "read_only", "read_write", "full_control"]
    admin_capabilities: tuple[str, ...]
    local_access: Literal["none", "artifact_only", "sandboxed_runtime", "process", "host"]
    local_capabilities: tuple[str, ...]

    @model_validator(mode="after")
    def access_paths_are_coherent(self) -> AccessPathContract:
        if len(self.side_channels) != len(set(self.side_channels)):
            raise ValueError("side-channel classes must be unique")
        if len(self.custom_side_channels) != len(set(self.custom_side_channels)):
            raise ValueError("custom side channels must be unique")
        if ("custom" in self.side_channels) != bool(self.custom_side_channels):
            raise ValueError("custom side-channel details and the custom marker must be declared together")
        if (self.admin_access == "none") != (not self.admin_capabilities):
            raise ValueError("admin capabilities must be empty exactly when admin access is none")
        if (self.local_access == "none") != (not self.local_capabilities):
            raise ValueError("local capabilities must be empty exactly when local access is none")
        return self


class SerializationContract(StrictModel):
    """Wire/file representation exposed to the recipient."""

    formats: tuple[str, ...] = Field(min_length=1)
    media_types: tuple[str, ...] = Field(min_length=1)
    encodings: tuple[str, ...] = Field(min_length=1)
    compression: tuple[str, ...]
    schema_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    endianness: Literal["not_applicable", "little", "big", "network", "mixed"]

    @model_validator(mode="after")
    def serialization_is_coherent(self) -> SerializationContract:
        for label, values in (
            ("serialization formats", self.formats),
            ("media types", self.media_types),
            ("encodings", self.encodings),
            ("compression modes", self.compression),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        return self


class InterfaceContract(StrictModel):
    """Versioned, declarably complete recipient-observable release interface."""

    schema_version: Literal["3.0"]
    protocol_type: Literal["predictive", "interactive_llm"]
    access: Literal["aggregate", "label", "score", "text", "embedding", "gradient", "weights", "full_artifact"]
    outputs: tuple[str, ...] = Field(min_length=1)
    output_channels: OutputChannelContract
    precision_bits: int | None = Field(ge=1, le=4096)
    query_budget: int | None = Field(ge=0)
    adaptive_queries: bool
    authenticated: bool
    rate_limited: bool
    rate_limit: RateLimitContract
    timing: TimingChannelContract
    errors: ErrorChannelContract
    execution: ExecutionChannelContract
    access_paths: AccessPathContract
    serialization: SerializationContract
    llm_protocol: LlmProtocolContract | None
    notes: str = ""

    @model_validator(mode="after")
    def protocol_matches_interface(self) -> InterfaceContract:
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("interface output names must be unique")
        channel_for_access = {
            "aggregate": self.output_channels.aggregates,
            "label": self.output_channels.labels,
            "score": self.output_channels.scores or self.output_channels.probabilities or self.output_channels.logits,
            "text": self.output_channels.text,
            "embedding": self.output_channels.embeddings,
            "gradient": self.output_channels.gradients,
            "weights": self.output_channels.parameters,
            "full_artifact": self.output_channels.parameters and bool(self.output_channels.downloadable_files),
        }
        if not channel_for_access[self.access]:
            raise ValueError(f"access={self.access} is inconsistent with the structured output-channel declaration")
        expected_side_channels: set[str] = set()
        if self.timing.recipient_observable:
            expected_side_channels.add("timing")
        if self.errors.transport_status != "none":
            expected_side_channels.add("status_code")
        if self.errors.error_content != "none":
            expected_side_channels.add("error_content")
        if not expected_side_channels.issubset(self.access_paths.side_channels):
            missing = sorted(expected_side_channels - set(self.access_paths.side_channels))
            raise ValueError(f"access-path declaration omits observable side channels: {missing}")
        if self.rate_limited != self.rate_limit.enabled:
            raise ValueError(
                "rate_limited must match the structured rate-limit declaration"
            )
        if self.rate_limit.retry_after_exposed:
            if not self.errors.retry_metadata:
                raise ValueError(
                    "exposed retry-after metadata requires errors.retry_metadata=true"
                )
            expected_status = {
                "http": "429",
                "grpc": "RESOURCE_EXHAUSTED",
            }.get(self.errors.transport_status)
            if (
                expected_status is not None
                and expected_status not in self.errors.documented_status_codes
            ):
                raise ValueError(
                    "exposed retry-after metadata requires the transport's rate-limit status code"
                )
        if self.protocol_type == "interactive_llm" and self.llm_protocol is None:
            raise ValueError("interactive_llm interfaces require a complete LLM protocol contract")
        if self.protocol_type == "predictive" and self.llm_protocol is not None:
            raise ValueError("predictive interfaces cannot contain an LLM protocol contract")
        if self.protocol_type == "interactive_llm":
            assert self.llm_protocol is not None
            if self.access != "text" or "text" not in self.outputs:
                raise ValueError("interactive_llm interfaces must declare text access and text output")
            if self.query_budget != self.llm_protocol.maximum_lifetime_queries:
                raise ValueError("interactive_llm query_budget must equal maximum_lifetime_queries")
            if self.execution.maximum_concurrent_requests != self.llm_protocol.maximum_concurrent_sessions:
                raise ValueError("interactive_llm concurrency must match maximum_concurrent_sessions")
            if self.execution.cross_request_state != self.llm_protocol.memory_mode:
                raise ValueError("interactive_llm cross-request state must match memory_mode")
            if self.execution.cross_request_state_ttl_seconds != self.llm_protocol.memory_ttl_seconds:
                raise ValueError("interactive_llm cross-request-state TTL must match memory_ttl_seconds")
        return self


class ReleaseContract(StrictModel):
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    owner: str = Field(min_length=1, max_length=256)
    recipient: str = Field(min_length=1, max_length=256)
    purpose: str = Field(min_length=1, max_length=2048)
    model_family: str = Field(min_length=1, max_length=128)
    model_profile: ModelProfile
    protected_unit: Literal[
        "record", "person", "household", "organization", "establishment", "episode",
        "event", "session", "device", "transaction", "custom",
    ]
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interface: InterfaceContract
    previous_release_ids: tuple[str, ...] = ()
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def expiry_is_timezone_aware(self) -> ReleaseContract:
        if len(self.previous_release_ids) != len(set(self.previous_release_ids)):
            raise ValueError("previous release identifiers must be unique")
        if self.release_id in self.previous_release_ids:
            raise ValueError("a release cannot list itself in its declared lineage")
        if self.expires_at is not None and self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must include a timezone offset")
        protocol = self.interface.llm_protocol
        if protocol is not None:
            now = datetime.now(timezone.utc)
            if protocol.valid_until <= now:
                raise ValueError("LLM protocol is already expired")
            if self.expires_at is None:
                raise ValueError("interactive LLM releases require an explicit expiry")
            if self.expires_at > protocol.valid_until:
                raise ValueError("release expiry cannot outlive the LLM protocol")
        if self.model_profile is not None:
            if self.interface.protocol_type == "interactive_llm":
                if not self.model_profile.generative or DataModality.TEXT not in self.model_profile.output_modalities:
                    raise ValueError("interactive LLM releases require a generative text model profile")
            if self.model_profile.stateful and not self.interface.adaptive_queries:
                raise ValueError("stateful model profiles require an adaptive-query interface")
        return self


class PolicyReference(StrictModel):
    policy_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    policy_version: str = Field(min_length=1, max_length=64)
    policy_path: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CeilingAttackBatteryMode(StrEnum):
    """Policy disposition for a threat that would otherwise clear on a ceiling."""

    REQUIRED = "required"
    PROHIBITED = "ceiling_prohibited"
    WAIVED = "waived"


class PolicyRule(StrictModel):
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: ThreatKind
    mandatory: bool
    decision_metric: DecisionMetric
    metric_parameters: dict[str, float] = Field(default_factory=dict)
    tolerance: float = Field(ge=0.0, le=1.0)
    tolerance_basis: Literal["absolute", "incremental"]
    ceiling_attack_battery_mode: CeilingAttackBatteryMode
    ceiling_attack_battery_waiver_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=4096,
    )

    @model_validator(mode="after")
    def metric_is_compatible(self) -> PolicyRule:
        allowed = {
            ThreatKind.LINKAGE: {"bayes_linkage_success", "incremental_bayes_linkage_success", "worst_observation_success"},
            ThreatKind.MEMBERSHIP: {"membership_tpr_at_fpr", "equal_prior_membership_success"},
            ThreatKind.ATTRIBUTE: {
                "finite_secret_exact_guess_success",
                "attribute_attack_success",
                "incremental_attribute_attack_success",
            },
            ThreatKind.RECONSTRUCTION: {
                "finite_secret_exact_guess_success",
                "reconstruction_success",
                "incremental_reconstruction_success",
            },
        }
        if self.decision_metric not in allowed[self.kind]:
            raise ValueError("policy decision metric is incompatible with its threat kind")
        is_incremental = self.decision_metric.startswith("incremental_")
        if is_incremental != (self.tolerance_basis == "incremental"):
            raise ValueError("policy tolerance_basis does not match its decision metric")
        if self.decision_metric == "membership_tpr_at_fpr":
            target = self.metric_parameters.get("target_fpr")
            if target is None or not 0.0 < target < 1.0:
                raise ValueError("membership_tpr_at_fpr policy requires target_fpr")
        if self.decision_metric == "finite_secret_exact_guess_success":
            prior_cap = self.metric_parameters.get("maximum_secret_prior")
            if prior_cap is None or not 0.0 < prior_cap < 1.0:
                raise ValueError(
                    "finite_secret_exact_guess_success policy requires "
                    "maximum_secret_prior in (0,1)"
                )
        if any(not 0.0 <= value <= 1.0 for value in self.metric_parameters.values()):
            raise ValueError("policy metric parameters must be probabilities in [0,1]")
        if self.ceiling_attack_battery_mode is CeilingAttackBatteryMode.WAIVED:
            if self.ceiling_attack_battery_waiver_reason is None:
                raise ValueError("a ceiling attack-battery waiver requires a recorded reason")
        elif self.ceiling_attack_battery_waiver_reason is not None:
            raise ValueError(
                "ceiling_attack_battery_waiver_reason is only valid when the battery is waived"
            )
        return self


class AnalyzerRequirement(StrictModel):
    """Policy allowlist for one evidence producer used against one threat."""

    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    analyzer: str = Field(min_length=1, max_length=128)
    minimum_service_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    accepted_implementation_sha256s: tuple[str, ...] = Field(min_length=1)
    accepted_configuration_sha256s: tuple[str, ...] = Field(min_length=1)
    required: bool = True

    @model_validator(mode="after")
    def digests_are_unique_and_valid(self) -> AnalyzerRequirement:
        for label, values in (
            ("implementation", self.accepted_implementation_sha256s),
            ("configuration", self.accepted_configuration_sha256s),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"accepted analyzer {label} digests must be unique")
            if any(
                len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in values
            ):
                raise ValueError(f"accepted analyzer {label} digests must be lowercase SHA-256 values")
        return self


class AttackBatteryRequirement(StrictModel):
    """Policy-authorized complete empirical battery required before ceiling clearance."""

    requirement_id: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    threat_id: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    accepted_catalog_sha256s: tuple[str, ...] = Field(min_length=1)
    required_attack_ids: tuple[str, ...] = Field(min_length=1)
    accepted_configuration_sha256s: tuple[str, ...] = Field(min_length=1)
    accepted_worker_service_ids: tuple[str, ...] = Field(min_length=1)
    minimum_worker_service_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    accepted_worker_implementation_sha256s: tuple[str, ...] = Field(min_length=1)
    accepted_worker_image_sha256s: tuple[str, ...] = Field(min_length=1)
    accepted_attester_key_ids: tuple[str, ...] = ()
    minimum_isolation_assurance: Literal["declared", "externally_attested"]
    positive_controls_required: Literal[True] = True
    minimum_positive_control_detection_lower_bound: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def requirement_is_unambiguous(self) -> AttackBatteryRequirement:
        named_sets = (
            ("required attack identifiers", self.required_attack_ids),
            ("worker service identifiers", self.accepted_worker_service_ids),
            ("attester key identifiers", self.accepted_attester_key_ids),
        )
        for label, values in named_sets:
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        digest_sets = (
            ("catalog", self.accepted_catalog_sha256s),
            ("configuration", self.accepted_configuration_sha256s),
            ("worker implementation", self.accepted_worker_implementation_sha256s),
            ("worker image", self.accepted_worker_image_sha256s),
        )
        for label, values in digest_sets:
            if len(values) != len(set(values)):
                raise ValueError(f"accepted {label} digests must be unique")
            if any(
                len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in values
            ):
                raise ValueError(f"accepted {label} digests must be lowercase SHA-256 values")
        if (
            self.minimum_isolation_assurance == "externally_attested"
            and not self.accepted_attester_key_ids
        ):
            raise ValueError("externally attested isolation requires accepted attester key IDs")
        return self


class PolicyBundle(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    policy_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    policy_version: str = Field(min_length=1, max_length=64)
    effective_from: datetime
    expires_at: datetime | None = None
    rules: tuple[PolicyRule, ...]
    analyzer_requirements: tuple[AnalyzerRequirement, ...] = ()
    attack_battery_requirements: tuple[AttackBatteryRequirement, ...] = ()
    accepted_selection_policy_sha256s: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def policy_is_well_formed(self) -> PolicyBundle:
        if self.effective_from.utcoffset() is None:
            raise ValueError("policy effective_from must include a timezone offset")
        if self.expires_at is not None:
            if self.expires_at.utcoffset() is None:
                raise ValueError("policy expires_at must include a timezone offset")
            if self.expires_at <= self.effective_from:
                raise ValueError("policy expires_at must be after effective_from")
        ids = [rule.threat_id for rule in self.rules]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("policy threat identifiers must be non-empty and unique")
        requirement_keys = [
            (requirement.threat_id, requirement.analyzer)
            for requirement in self.analyzer_requirements
        ]
        if len(requirement_keys) != len(set(requirement_keys)):
            raise ValueError("policy analyzer requirements must be unique per threat and analyzer")
        unknown = {
            requirement.threat_id for requirement in self.analyzer_requirements
        } - set(ids)
        if unknown:
            raise ValueError(f"analyzer requirements reference unknown policy threats: {sorted(unknown)}")
        battery_ids = [item.requirement_id for item in self.attack_battery_requirements]
        battery_threats = [item.threat_id for item in self.attack_battery_requirements]
        if len(battery_ids) != len(set(battery_ids)):
            raise ValueError("attack-battery requirement identifiers must be unique")
        if len(battery_threats) != len(set(battery_threats)):
            raise ValueError("at most one attack-battery requirement is allowed per threat")
        unknown_battery_threats = set(battery_threats) - set(ids)
        if unknown_battery_threats:
            raise ValueError(
                "attack-battery requirements reference unknown policy threats: "
                f"{sorted(unknown_battery_threats)}"
            )
        rules_by_id = {rule.threat_id: rule for rule in self.rules}
        battery_by_threat = {
            requirement.threat_id: requirement
            for requirement in self.attack_battery_requirements
        }
        required_without_battery = {
            threat_id
            for threat_id, rule in rules_by_id.items()
            if rule.ceiling_attack_battery_mode is CeilingAttackBatteryMode.REQUIRED
            and threat_id not in battery_by_threat
        }
        if required_without_battery:
            raise ValueError(
                "ceiling-clearable threats omit required attack batteries: "
                f"{sorted(required_without_battery)}"
            )
        unexpected_batteries = {
            threat_id
            for threat_id in battery_by_threat
            if rules_by_id[threat_id].ceiling_attack_battery_mode
            is not CeilingAttackBatteryMode.REQUIRED
        }
        if unexpected_batteries:
            raise ValueError(
                "attack-battery requirements are only valid for required battery modes: "
                f"{sorted(unexpected_batteries)}"
            )
        analyzer_pairs = {
            (requirement.threat_id, requirement.analyzer): requirement
            for requirement in self.analyzer_requirements
        }
        missing_battery_analyzers = {
            threat_id
            for threat_id in battery_by_threat
            if (threat_id, "attack_battery") not in analyzer_pairs
            or not analyzer_pairs[(threat_id, "attack_battery")].required
        }
        if missing_battery_analyzers:
            raise ValueError(
                "required attack batteries need a required attack_battery analyzer: "
                f"{sorted(missing_battery_analyzers)}"
            )
        if len(self.accepted_selection_policy_sha256s) != len(
            set(self.accepted_selection_policy_sha256s)
        ):
            raise ValueError("accepted selection-policy digests must be unique")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.accepted_selection_policy_sha256s
        ):
            raise ValueError(
                "accepted selection-policy digests must be lowercase SHA-256 values"
            )
        return self


class ThreatContract(StrictModel):
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: ThreatKind
    mandatory: bool = True
    secret: str = Field(min_length=1, max_length=1024)
    prior: str = Field(min_length=1, max_length=2048)
    side_information: tuple[str, ...]
    adversary_metadata_profile: Literal["exact_database_feature_summaries_v1"] = Field(
        default="exact_database_feature_summaries_v1",
        description=(
            "Mandatory conservative profile: complete schema; exact row/class/missingness/cardinality and "
            "categorical frequencies; numeric min, max, range, mean, median, standard deviation, variance, "
            "quartiles/IQR, and median absolute deviation. Pre-existing values belong in the no-release baseline; "
            "newly transferred values belong in the release channel."
        ),
    )
    success_metric: str = Field(min_length=1, max_length=1024)
    decision_metric: DecisionMetric
    metric_parameters: dict[str, float] = Field(default_factory=dict)
    tolerance: float = Field(ge=0.0, le=1.0)
    tolerance_basis: Literal["absolute", "incremental"] = "absolute"
    harm_rationale: str = Field(min_length=1, max_length=4096)
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    candidate_set: str | None = None
    target_signal_source: str | None = None
    realizability: Realizability = Realizability.NOT_APPLICABLE

    @model_validator(mode="after")
    def linkage_has_operational_game(self) -> ThreatContract:
        allowed = {
            ThreatKind.LINKAGE: {
                "bayes_linkage_success",
                "incremental_bayes_linkage_success",
                "worst_observation_success",
            },
            ThreatKind.MEMBERSHIP: {
                "membership_tpr_at_fpr",
                "equal_prior_membership_success",
            },
            ThreatKind.ATTRIBUTE: {
                "finite_secret_exact_guess_success",
                "attribute_attack_success",
                "incremental_attribute_attack_success",
            },
            ThreatKind.RECONSTRUCTION: {
                "finite_secret_exact_guess_success",
                "reconstruction_success",
                "incremental_reconstruction_success",
            },
        }
        if self.decision_metric not in allowed[self.kind]:
            raise ValueError(f"decision_metric {self.decision_metric!r} is incompatible with threat kind {self.kind}")
        if self.tolerance_basis == "incremental" and not self.decision_metric.startswith("incremental_"):
            raise ValueError("incremental tolerance requires an incremental decision metric")
        if self.tolerance_basis == "absolute" and self.decision_metric.startswith("incremental_"):
            raise ValueError("incremental decision metric requires incremental tolerance_basis")
        if self.decision_metric == "membership_tpr_at_fpr":
            target = self.metric_parameters.get("target_fpr")
            if target is None or not 0.0 < target < 1.0:
                raise ValueError("membership_tpr_at_fpr requires metric_parameters.target_fpr in (0,1)")
        if self.decision_metric == "finite_secret_exact_guess_success":
            prior_cap = self.metric_parameters.get("maximum_secret_prior")
            if prior_cap is None or not 0.0 < prior_cap < 1.0:
                raise ValueError(
                    "finite_secret_exact_guess_success requires "
                    "metric_parameters.maximum_secret_prior in (0,1)"
                )
        if any(not 0.0 <= value <= 1.0 for value in self.metric_parameters.values()):
            raise ValueError("metric parameters must be probabilities in [0,1]")
        if self.kind is ThreatKind.LINKAGE:
            if not self.candidate_set or not self.target_signal_source:
                raise ValueError("linkage requires candidate_set and target_signal_source")
            if self.realizability is Realizability.NOT_APPLICABLE:
                raise ValueError("linkage requires an explicit realizability classification")
        return self


class EvidenceProducer(StrictModel):
    service_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    service_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnalyzerProvenance(StrictModel):
    tool: str = Field(min_length=1, max_length=256)
    tool_version: str = Field(min_length=1, max_length=128)
    producer: EvidenceProducer
    configuration_path: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bound_fields: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def fields_are_unique(self) -> AnalyzerProvenance:
        if len(set(self.bound_fields)) != len(self.bound_fields):
            raise ValueError("provenance bound_fields must be unique")
        return self


class EvidenceContext(StrictModel):
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    release_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_game_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime

    @model_validator(mode="after")
    def observation_time_is_aware(self) -> EvidenceContext:
        if self.observed_at.utcoffset() is None:
            raise ValueError("evidence context observed_at must include a timezone offset")
        return self


class AttackCatalogEntry(StrictModel):
    attack_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    service_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    applicable_model_families: tuple[str, ...] = Field(min_length=1)
    applicable_protocol_types: tuple[Literal["predictive", "interactive_llm"], ...] = Field(
        min_length=1
    )
    applicable_threat_kinds: tuple[ThreatKind, ...] = Field(min_length=1)
    supported_metrics: tuple[DecisionMetric, ...]
    evidence_role: Literal["blocking_floor", "screen_only"]
    positive_control_kind: Literal["known_leak_binomial", "expected_flag"]
    minimum_repetitions: int = Field(ge=1)
    requires_model_execution: bool
    can_clear: Literal[False] = False
    decision_authority: Literal["none"] = "none"

    @model_validator(mode="after")
    def entry_sets_are_unique(self) -> AttackCatalogEntry:
        for label, values in (
            ("model families", self.applicable_model_families),
            ("protocol types", self.applicable_protocol_types),
            ("threat kinds", self.applicable_threat_kinds),
            ("metrics", self.supported_metrics),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"attack-catalog {label} must be unique")
        if self.evidence_role == "blocking_floor" and not self.supported_metrics:
            raise ValueError("blocking attack-catalog entries require supported metrics")
        return self


class AttackCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    catalog_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    catalog_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    valid_from: datetime
    valid_until: datetime | None = None
    entries: tuple[AttackCatalogEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def catalog_is_coherent(self) -> AttackCatalog:
        if self.valid_from.utcoffset() is None:
            raise ValueError("attack-catalog valid_from must include a timezone offset")
        if self.valid_until is not None:
            if self.valid_until.utcoffset() is None:
                raise ValueError("attack-catalog valid_until must include a timezone offset")
            if self.valid_until <= self.valid_from:
                raise ValueError("attack-catalog valid_until must follow valid_from")
        ids = [entry.attack_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("attack-catalog entries must have unique attack IDs")
        return self


class AttackResourceLimits(StrictModel):
    timeout_seconds: int = Field(gt=0, le=86_400)
    memory_megabytes: int = Field(
        gt=0,
        description=(
            "Declared worker memory budget; the reference core does not mechanically "
            "observe or attest compliance because the submission carries no memory telemetry."
        ),
    )
    cpu_cores: float = Field(
        gt=0.0,
        description=(
            "Declared worker CPU budget; the reference core does not mechanically "
            "observe or attest compliance because the submission carries no CPU telemetry."
        ),
    )
    maximum_records: int = Field(
        gt=0,
        description="Maximum aggregate statistical trials reported by the worker.",
    )
    maximum_output_bytes: int = Field(
        gt=0,
        description="Maximum canonical governed worker-output size in bytes.",
    )


class AttackPositiveControlPlan(StrictModel):
    control_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    control_kind: Literal["known_leak_binomial", "expected_flag"]
    reference_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    minimum_trials: int = Field(gt=0)
    minimum_detection_lower_bound: float = Field(gt=0.0, le=1.0)
    confidence: float = Field(gt=0.5, lt=1.0)


class AttackRunPlan(StrictModel):
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    metric: DecisionMetric
    evidence_role: Literal["blocking_floor", "screen_only"]
    seed: int = Field(ge=0)
    repetitions: int = Field(ge=1)
    confidence: float = Field(gt=0.5, lt=1.0)
    comparison_family_size: int = Field(ge=1)
    target_fpr: float | None = Field(default=None, gt=0.0, lt=1.0)
    positive_control_ids: tuple[str, ...] = Field(min_length=1)
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def plan_is_coherent(self) -> AttackRunPlan:
        if len(self.positive_control_ids) != len(set(self.positive_control_ids)):
            raise ValueError("attack-run positive-control identifiers must be unique")
        if self.metric == "membership_tpr_at_fpr" and self.target_fpr is None:
            raise ValueError("low-FPR membership attack plans require target_fpr")
        if self.metric != "membership_tpr_at_fpr" and self.target_fpr is not None:
            raise ValueError("target_fpr is only valid for membership_tpr_at_fpr")
        return self


class AttackBatteryConfiguration(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    configuration_id: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_at: datetime
    resource_limits: AttackResourceLimits
    runs: tuple[AttackRunPlan, ...] = Field(min_length=1)
    positive_controls: tuple[AttackPositiveControlPlan, ...] = Field(min_length=1)
    stopping_rule: str = Field(min_length=1, max_length=2048)
    multiplicity_method: Literal["bonferroni"]

    @model_validator(mode="after")
    def configuration_is_complete(self) -> AttackBatteryConfiguration:
        if self.frozen_at.utcoffset() is None:
            raise ValueError("attack-battery frozen_at must include a timezone offset")
        run_ids = [run.run_id for run in self.runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("attack-battery run IDs must be unique")
        control_ids = [control.control_id for control in self.positive_controls]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("attack-battery positive-control IDs must be unique")
        known_controls = set(control_ids)
        missing_controls = {
            control_id
            for run in self.runs
            for control_id in run.positive_control_ids
            if control_id not in known_controls
        }
        if missing_controls:
            raise ValueError(
                "attack runs reference unknown positive controls: "
                f"{sorted(missing_controls)}"
            )
        control_attack = {
            control.control_id: control.attack_id for control in self.positive_controls
        }
        mismatched_controls = {
            control_id
            for run in self.runs
            for control_id in run.positive_control_ids
            if control_attack[control_id] != run.attack_id
        }
        if mismatched_controls:
            raise ValueError(
                "positive controls must be bound to the attack that consumes them: "
                f"{sorted(mismatched_controls)}"
            )
        return self


class AttackPositiveControlResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    control_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    service_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "failed", "timed_out"]
    successes: int | None = Field(default=None, ge=0)
    trials: int | None = Field(default=None, gt=0)
    reported_detection_lower_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_flag_observed: bool | None = None
    raw_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def result_shape_matches_status(self) -> AttackPositiveControlResult:
        if self.status == "succeeded":
            has_binomial = self.successes is not None and self.trials is not None
            has_flag = self.expected_flag_observed is not None
            if has_binomial == has_flag:
                raise ValueError(
                    "a successful positive control must report exactly one typed result"
                )
            if has_binomial:
                assert self.successes is not None and self.trials is not None
                if self.successes > self.trials:
                    raise ValueError("positive-control successes cannot exceed trials")
                if self.reported_detection_lower_bound is None:
                    raise ValueError("binomial positive controls require a reported lower bound")
            elif self.reported_detection_lower_bound is not None:
                raise ValueError("flag controls cannot report a binomial lower bound")
        elif any(
            value is not None
            for value in (
                self.successes,
                self.trials,
                self.reported_detection_lower_bound,
                self.expected_flag_observed,
            )
        ):
            raise ValueError("failed or timed-out positive controls cannot report results")
        return self


class AttackRunResult(StrictModel):
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    service_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    attack_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "failed", "timed_out"]
    metric: DecisionMetric
    successes: int | None = Field(default=None, ge=0)
    trials: int | None = Field(default=None, gt=0)
    false_positives: int | None = Field(default=None, ge=0)
    nonmember_trials: int | None = Field(default=None, gt=0)
    target_fpr: float | None = Field(default=None, gt=0.0, lt=1.0)
    raw_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    negative_control_summary: str = Field(min_length=1, max_length=2048)
    can_clear: Literal[False] = False

    @model_validator(mode="after")
    def counts_match_result_status(self) -> AttackRunResult:
        if self.status == "succeeded":
            if self.successes is None or self.trials is None:
                raise ValueError("successful attack results require successes and trials")
            if self.successes > self.trials:
                raise ValueError("attack successes cannot exceed trials")
            if self.metric == "membership_tpr_at_fpr":
                if (
                    self.false_positives is None
                    or self.nonmember_trials is None
                    or self.target_fpr is None
                ):
                    raise ValueError(
                        "low-FPR attack results require false-positive counts and target_fpr"
                    )
                if self.false_positives > self.nonmember_trials:
                    raise ValueError("false positives cannot exceed nonmember trials")
            elif any(
                value is not None
                for value in (self.false_positives, self.nonmember_trials, self.target_fpr)
            ):
                raise ValueError("false-positive fields are only valid for low-FPR membership")
        elif any(
            value is not None
            for value in (
                self.successes,
                self.trials,
                self.false_positives,
                self.nonmember_trials,
                self.target_fpr,
            )
        ):
            raise ValueError("failed or timed-out attacks cannot report decision counts")
        return self


class AttackIsolationEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assurance: Literal["declared", "externally_attested"]
    worker_image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_as_non_root: bool
    no_new_privileges: bool
    read_only_root_filesystem: bool
    network_access: Literal["none", "restricted", "unrestricted"]
    writable_audit_path: bool
    writable_key_path: bool
    writable_governance_path: bool
    read_only_mount_sha256s: tuple[str, ...]
    attester_key_id: str | None = Field(default=None, min_length=1, max_length=256)
    statement_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signature: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def attestation_fields_are_coherent(self) -> AttackIsolationEvidence:
        attestation = (self.attester_key_id, self.statement_sha256, self.signature)
        if self.assurance == "externally_attested" and any(value is None for value in attestation):
            raise ValueError("externally attested isolation requires key, statement, and signature")
        if self.assurance == "declared" and any(value is not None for value in attestation):
            raise ValueError("declared isolation cannot present unverified attestation fields")
        if len(self.read_only_mount_sha256s) != len(set(self.read_only_mount_sha256s)):
            raise ValueError("read-only mount digests must be unique")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.read_only_mount_sha256s
        ):
            raise ValueError("read-only mount digests must be lowercase SHA-256 values")
        return self


class AttackBatteryWorkerOutput(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    release_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_game_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    worker: EvidenceProducer
    worker_runtime_identity: RuntimeIdentity
    isolation: AttackIsolationEvidence
    started_at: datetime
    completed_at: datetime
    positive_controls: tuple[AttackPositiveControlResult, ...] = Field(min_length=1)
    results: tuple[AttackRunResult, ...] = Field(min_length=1)
    retained_raw_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_authority: Literal["none"] = "none"
    can_clear: Literal[False] = False

    @model_validator(mode="after")
    def output_is_complete(self) -> AttackBatteryWorkerOutput:
        for label, values in (
            ("positive-control IDs", [item.control_id for item in self.positive_controls]),
            ("run IDs", [item.run_id for item in self.results]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"attack-worker {label} must be unique")
        if self.started_at.utcoffset() is None or self.completed_at.utcoffset() is None:
            raise ValueError("attack-worker timestamps must include timezone offsets")
        if self.completed_at < self.started_at:
            raise ValueError("attack-worker completion cannot precede its start")
        if self.worker.configuration_sha256 != self.configuration_sha256:
            raise ValueError("attack-worker producer is not bound to the battery configuration")
        runtime = self.worker_runtime_identity
        if (
            runtime.component_id != "attack_battery_worker"
            or runtime.component_version != "AttackBatteryWorkerOutput/1.0"
        ):
            raise ValueError("attack-worker runtime identity has the wrong component")
        profile = runtime.algorithm_profile
        expected_attacks = sorted({item.attack_id for item in self.results})
        expected_controls = sorted({item.control_id for item in self.positive_controls})
        if profile.get("catalog_sha256") != self.catalog_sha256:
            raise ValueError("attack-worker runtime profile uses another catalog")
        if profile.get("configuration_sha256") != self.configuration_sha256:
            raise ValueError("attack-worker runtime profile uses another configuration")
        profile_attacks = profile.get("attacks")
        if not isinstance(profile_attacks, (list, tuple)) or sorted(
            profile_attacks
        ) != expected_attacks:
            raise ValueError("attack-worker runtime profile omits or substitutes attacks")
        profile_controls = profile.get("positive_controls")
        if not isinstance(profile_controls, (list, tuple)) or sorted(
            profile_controls
        ) != expected_controls:
            raise ValueError(
                "attack-worker runtime profile omits or substitutes positive controls"
            )
        if profile.get("decision_authority") != "none":
            raise ValueError("attack-worker runtime profile cannot claim decision authority")
        return self


class AttackBatteryInput(StrictModel):
    """Complete, policy-matchable attack battery submitted to the assurance core."""

    analyzer: Literal["attack_battery"] = "attack_battery"
    schema_version: Literal["1.0"] = "1.0"
    threat_id: str
    population_scope_id: str
    catalog: AttackCatalog
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration: AttackBatteryConfiguration
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    worker_output: AttackBatteryWorkerOutput
    worker_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def battery_bindings_are_exact(self) -> AttackBatteryInput:
        expected_hashes = (
            ("catalog", self.catalog_sha256, _canonical_model_sha256(self.catalog)),
            (
                "configuration",
                self.configuration_sha256,
                _canonical_model_sha256(self.configuration),
            ),
            (
                "worker output",
                self.worker_output_sha256,
                _canonical_model_sha256(self.worker_output),
            ),
        )
        for label, declared, actual in expected_hashes:
            if declared != actual:
                raise ValueError(f"attack-battery {label} digest does not match its content")
        if self.configuration.catalog_sha256 != self.catalog_sha256:
            raise ValueError("attack-battery configuration references a different catalog")
        if self.configuration.frozen_at < self.catalog.valid_from or (
            self.catalog.valid_until is not None
            and self.configuration.frozen_at >= self.catalog.valid_until
        ):
            raise ValueError("attack-battery configuration was frozen outside catalog validity")
        output = self.worker_output
        if output.catalog_sha256 != self.catalog_sha256:
            raise ValueError("attack-worker output references a different catalog")
        if output.configuration_sha256 != self.configuration_sha256:
            raise ValueError("attack-worker output references a different configuration")
        if output.started_at < self.configuration.frozen_at:
            raise ValueError("attack-worker execution predates the frozen configuration")
        if output.started_at < self.catalog.valid_from or (
            self.catalog.valid_until is not None
            and output.completed_at >= self.catalog.valid_until
        ):
            raise ValueError("attack-worker execution falls outside catalog validity")
        context_fields = (
            "release_id",
            "release_contract_sha256",
            "policy_sha256",
            "artifact_sha256",
            "interface_sha256",
            "population_scope_id",
            "population_scope_sha256",
            "decision_game_sha256",
        )
        if any(
            getattr(output, field) != getattr(self.evidence_context, field)
            for field in context_fields
        ):
            raise ValueError("attack-worker output does not match the evidence context")
        if not output.started_at <= self.evidence_context.observed_at <= output.completed_at:
            raise ValueError(
                "attack-battery evidence observation must fall within the worker execution interval"
            )
        limits = self.configuration.resource_limits
        elapsed_seconds = (output.completed_at - output.started_at).total_seconds()
        if elapsed_seconds > limits.timeout_seconds:
            raise ValueError("attack-worker execution exceeds the frozen timeout")
        reported_records = sum(
            (result.trials or 0) + (result.nonmember_trials or 0)
            for result in output.results
        ) + sum((control.trials or 0) for control in output.positive_controls)
        if reported_records > limits.maximum_records:
            raise ValueError(
                "attack-worker reported statistical trials exceed the frozen record limit"
            )
        if len(_canonical_model_bytes(output)) > limits.maximum_output_bytes:
            raise ValueError("attack-worker governed output exceeds the frozen byte limit")
        if self.population_scope_id != self.evidence_context.population_scope_id:
            raise ValueError("attack battery uses the wrong population scope")
        entries = {entry.attack_id: entry for entry in self.catalog.entries}
        plans = {plan.run_id: plan for plan in self.configuration.runs}
        results = {result.run_id: result for result in output.results}
        if set(plans) != set(results):
            raise ValueError("attack-worker results must disposition every planned run exactly once")
        controls = {
            control.control_id: control for control in self.configuration.positive_controls
        }
        control_results = {
            result.control_id: result for result in output.positive_controls
        }
        if set(controls) != set(control_results):
            raise ValueError(
                "attack-worker output must disposition every positive control exactly once"
            )
        blocking_family_size = sum(
            plan.evidence_role == "blocking_floor" for plan in plans.values()
        )
        for plan in plans.values():
            entry = entries.get(plan.attack_id)
            if entry is None:
                raise ValueError(f"attack plan uses uncatalogued attack {plan.attack_id!r}")
            if entry.attack_version != plan.attack_version:
                raise ValueError("attack plan version does not match the catalog")
            if plan.metric not in entry.supported_metrics:
                raise ValueError("attack plan metric is not supported by its catalog entry")
            if plan.evidence_role != entry.evidence_role:
                raise ValueError("attack plan evidence role does not match the catalog")
            if plan.repetitions < entry.minimum_repetitions:
                raise ValueError("attack plan repetitions are below the catalog minimum")
            if (
                plan.evidence_role == "blocking_floor"
                and plan.comparison_family_size != blocking_family_size
            ):
                raise ValueError(
                    "blocking attack multiplicity must be derived from the complete battery"
                )
            result = results[plan.run_id]
            if result.attack_id != plan.attack_id or result.metric != plan.metric:
                raise ValueError("attack result identity or metric does not match its plan")
            if (
                result.service_id != entry.service_id
                or result.attack_version != entry.attack_version
                or result.implementation_sha256 != entry.implementation_sha256
            ):
                raise ValueError(
                    "attack result service, version, or implementation does not match the catalog"
                )
            if result.target_fpr != plan.target_fpr:
                raise ValueError("attack result target_fpr does not match its plan")
        for control_id, plan in controls.items():
            result = control_results[control_id]
            if result.attack_id != plan.attack_id:
                raise ValueError("positive-control result does not match its plan")
            entry = entries.get(plan.attack_id)
            if entry is None:
                raise ValueError(
                    f"positive-control plan uses uncatalogued attack {plan.attack_id!r}"
                )
            if plan.control_kind != entry.positive_control_kind:
                raise ValueError(
                    "positive-control kind does not match the attack catalog"
                )
            if (
                result.service_id != entry.service_id
                or result.attack_version != entry.attack_version
                or result.implementation_sha256 != entry.implementation_sha256
            ):
                raise ValueError(
                    "positive-control service, version, or implementation does not match the catalog"
                )
        return self


class TreeLinkageInput(StrictModel):
    analyzer: Literal["tree_linkage"] = "tree_linkage"
    threat_id: str
    population_scope_id: str
    candidate_ids: tuple[str, ...]
    observations: tuple[str, ...]
    prior: tuple[float, ...] | None = None
    recipient_has_candidate_roster: bool
    recipient_has_target_signal: bool
    observed_interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete_interface_coverage: bool
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def dimensions_match(self) -> TreeLinkageInput:
        n = len(self.candidate_ids)
        if n == 0 or len(set(self.candidate_ids)) != n:
            raise ValueError("candidate_ids must be non-empty and unique")
        if len(self.observations) != n:
            raise ValueError("observations must align one-to-one with candidate_ids")
        if self.prior is not None:
            if len(self.prior) != n or any(p < 0 for p in self.prior):
                raise ValueError("prior must be non-negative and align with candidate_ids")
            if abs(sum(self.prior) - 1.0) > 1e-9:
                raise ValueError("prior must sum to one")
        return self


class DpInput(StrictModel):
    analyzer: Literal["dp"] = "dp"
    threat_id: str
    population_scope_id: str
    epsilon: float = Field(ge=0.0)
    delta: float = Field(ge=0.0, lt=1.0)
    adjacency: str = Field(min_length=1)
    protected_unit: str = Field(min_length=1)
    accountant: str = Field(min_length=1)
    accountant_replayed: bool
    complete_pipeline: bool
    fpr: float | None = Field(default=None, ge=0.0, le=1.0)
    secret_cardinality: int | None = Field(default=None, ge=2)
    maximum_secret_prior: float | None = Field(default=None, gt=0.0, lt=1.0)
    pairwise_secret_relation_validated: bool = False
    secret_prior_bound_validated: bool = False
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def finite_secret_inputs_are_coherent(self) -> DpInput:
        finite_fields_present = (
            self.maximum_secret_prior is not None
            or self.pairwise_secret_relation_validated
            or self.secret_prior_bound_validated
        )
        if self.secret_cardinality is None:
            if finite_fields_present:
                raise ValueError(
                    "finite-secret DP fields require secret_cardinality"
                )
            return self
        if self.maximum_secret_prior is None:
            raise ValueError(
                "finite-secret DP evidence requires maximum_secret_prior"
            )
        if self.maximum_secret_prior + 1e-15 < 1.0 / self.secret_cardinality:
            raise ValueError(
                "maximum_secret_prior cannot be below 1 / secret_cardinality"
            )
        return self


class AttackInput(StrictModel):
    analyzer: Literal["attack"] = "attack"
    threat_id: str
    population_scope_id: str
    attack_name: str = Field(min_length=1)
    metric: Literal[
        "membership_tpr_at_fpr",
        "equal_prior_membership_success",
        "finite_secret_exact_guess_success",
        "attribute_attack_success",
        "reconstruction_success",
    ]
    successes: int = Field(ge=0)
    trials: int = Field(gt=0)
    confidence: float = Field(default=0.95, gt=0.5, lt=1.0)
    comparison_family_size: int = Field(default=1, ge=1)
    calibration_disjoint: bool
    audit_disjoint: bool
    raw_counts_retained: bool = True
    threshold_pre_registered: bool = True
    false_positives: int | None = Field(default=None, ge=0)
    nonmember_trials: int | None = Field(default=None, gt=0)
    target_fpr: float | None = Field(default=None, gt=0.0, lt=1.0)
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def valid_counts(self) -> AttackInput:
        if self.successes > self.trials:
            raise ValueError("successes cannot exceed trials")
        if self.metric == "membership_tpr_at_fpr":
            if self.false_positives is None or self.nonmember_trials is None or self.target_fpr is None:
                raise ValueError("low-FPR membership evidence requires false_positives, nonmember_trials, and target_fpr")
            if self.false_positives > self.nonmember_trials:
                raise ValueError("false_positives cannot exceed nonmember_trials")
        return self


class PopulationInput(StrictModel):
    analyzer: Literal["population"] = "population"
    threat_id: str
    population_scope_id: str
    simultaneous_lower_match_count: float = Field(ge=0.0)
    required_match_count: float = Field(gt=0.0)
    coverage: float = Field(gt=0.5, lt=1.0)
    fitted_joint_model: bool
    heldout_validated: bool
    multiplicity_adjusted: bool
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance


class ControlledInferenceInput(StrictModel):
    analyzer: Literal["controlled_inference"] = "controlled_inference"
    threat_id: str
    population_scope_id: str
    attack_name: str = Field(min_length=1)
    metric: Literal[
        "attribute_attack_success",
        "incremental_attribute_attack_success",
        "reconstruction_success",
        "incremental_reconstruction_success",
    ]
    trials: int = Field(gt=0)
    combined_successes: int = Field(ge=0)
    baseline_successes: int = Field(ge=0)
    combined_only_successes: int = Field(ge=0)
    baseline_only_successes: int = Field(ge=0)
    confidence_family: float = Field(default=0.95, gt=0.5, lt=1.0)
    comparison_family_size: int = Field(default=1, ge=1)
    attack_training_disjoint: bool
    audit_disjoint: bool
    raw_paired_counts_retained: bool
    comparator_same_side_information: bool
    secret_and_metric_pre_registered: bool
    ground_truth_verified: bool
    training_membership_verified: bool = False
    success_definition: str = Field(min_length=1, max_length=2048)
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def paired_counts_are_consistent(self) -> ControlledInferenceInput:
        if self.combined_successes > self.trials or self.baseline_successes > self.trials:
            raise ValueError("successes cannot exceed trials")
        both_from_combined = self.combined_successes - self.combined_only_successes
        both_from_baseline = self.baseline_successes - self.baseline_only_successes
        if both_from_combined < 0 or both_from_combined != both_from_baseline:
            raise ValueError("paired correctness cells do not reproduce both success totals")
        if both_from_combined + self.combined_only_successes + self.baseline_only_successes > self.trials:
            raise ValueError("paired correctness cells exceed trials")
        return self


class LlmWatermarkInput(StrictModel):
    """Transcript-bound output-watermark screen for an interactive LLM."""

    analyzer: Literal["llm_watermark"] = "llm_watermark"
    threat_id: str
    population_scope_id: str
    study_id: str = Field(min_length=1, max_length=256)
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    detector_id: str = Field(min_length=1, max_length=256)
    detector_version: str = Field(min_length=1, max_length=128)
    opaque_key_id: str = Field(min_length=1, max_length=256)
    detected_outputs: int = Field(ge=0)
    eligible_outputs: int = Field(gt=0)
    null_false_positives: int = Field(ge=0)
    null_outputs: int = Field(gt=0)
    confidence: float = Field(default=0.95, gt=0.5, lt=1.0)
    comparison_family_size: int = Field(default=1, ge=1)
    threshold_pre_registered: bool
    calibration_disjoint: bool
    audit_disjoint: bool
    raw_counts_retained: bool
    key_compromised: bool = False
    key_revoked: bool = False
    complete_protocol_binding: bool
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def counts_are_coherent(self) -> LlmWatermarkInput:
        if self.detected_outputs > self.eligible_outputs:
            raise ValueError("detected_outputs cannot exceed eligible_outputs")
        if self.null_false_positives > self.null_outputs:
            raise ValueError("null_false_positives cannot exceed null_outputs")
        return self


class LlmCanaryInput(StrictModel):
    """Randomized member/decoy canary extraction evidence for an interactive LLM."""

    analyzer: Literal["llm_canary"] = "llm_canary"
    threat_id: str
    population_scope_id: str
    study_id: str = Field(min_length=1, max_length=256)
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_assignment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metric: Literal[
        "membership_tpr_at_fpr", "equal_prior_membership_success", "reconstruction_success"
    ]
    member_successes: int = Field(ge=0)
    member_canaries: int = Field(gt=0)
    decoy_successes: int = Field(ge=0)
    nonmember_decoys: int = Field(gt=0)
    confidence: float = Field(default=0.95, gt=0.5, lt=1.0)
    comparison_family_size: int = Field(default=1, ge=1)
    target_fpr: float | None = Field(default=None, gt=0.0, lt=1.0)
    assignment_randomized: bool
    scoring_frozen_before_unblinding: bool
    exact_match_pre_registered: bool
    audit_disjoint: bool
    raw_counts_retained: bool
    contamination_scan_passed: bool
    complete_protocol_binding: bool
    recipient_realizable: bool
    evidence_context: EvidenceContext
    provenance: AnalyzerProvenance

    @model_validator(mode="after")
    def canary_counts_are_coherent(self) -> LlmCanaryInput:
        if self.member_successes > self.member_canaries:
            raise ValueError("member_successes cannot exceed member_canaries")
        if self.decoy_successes > self.nonmember_decoys:
            raise ValueError("decoy_successes cannot exceed nonmember_decoys")
        if self.metric == "membership_tpr_at_fpr" and self.target_fpr is None:
            raise ValueError("membership canary evidence requires target_fpr")
        if self.metric == "reconstruction_success" and self.target_fpr is not None:
            raise ValueError("target_fpr is only valid for membership canary evidence")
        return self


AnalyzerInput = Annotated[
    TreeLinkageInput | DpInput | AttackInput | AttackBatteryInput
    | PopulationInput | ControlledInferenceInput
    | LlmWatermarkInput | LlmCanaryInput,
    Field(discriminator="analyzer"),
]


class AssessmentRequest(StrictModel):
    schema_version: Literal["5.0"] = "5.0"
    policy: PolicyReference
    release: ReleaseContract
    population_scopes: tuple[PopulationScope, ...]
    threats: tuple[ThreatContract, ...]
    analyzer_inputs: tuple[AnalyzerInput, ...]

    @model_validator(mode="after")
    def identifiers_are_consistent(self) -> AssessmentRequest:
        ids = [t.threat_id for t in self.threats]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("threat identifiers must be non-empty and unique")
        known = set(ids)
        scope_ids = [scope.scope_id for scope in self.population_scopes]
        if not scope_ids or len(scope_ids) != len(set(scope_ids)):
            raise ValueError("population scope identifiers must be non-empty and unique")
        unknown_scopes = {threat.population_scope_id for threat in self.threats} - set(scope_ids)
        if unknown_scopes:
            raise ValueError(f"threats reference unknown population scopes: {sorted(unknown_scopes)}")
        unknown = {i.threat_id for i in self.analyzer_inputs} - known
        if unknown:
            raise ValueError(f"analyzer inputs reference unknown threats: {sorted(unknown)}")
        threat_scopes = {threat.threat_id: threat.population_scope_id for threat in self.threats}
        mismatches = [
            value.threat_id
            for value in self.analyzer_inputs
            if value.population_scope_id != threat_scopes[value.threat_id]
        ]
        if mismatches:
            raise ValueError(f"analyzer inputs use the wrong population scope: {sorted(set(mismatches))}")
        context_mismatches = [
            value.threat_id
            for value in self.analyzer_inputs
            if value.evidence_context.population_scope_id != value.population_scope_id
        ]
        if context_mismatches:
            raise ValueError(
                "analyzer evidence context uses the wrong population scope: "
                f"{sorted(set(context_mismatches))}"
            )
        if self.release.expires_at and self.release.expires_at <= datetime.now(timezone.utc):
            raise ValueError("release contract is already expired")
        return self


class EvidenceRecord(StrictModel):
    evidence_id: str
    threat_id: str
    analyzer: str
    producer: EvidenceProducer
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    release_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    evidence_class: EvidenceClass
    coverage: EvidenceCoverage = EvidenceCoverage.SCREEN_ONLY
    population_scope_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision_game_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    interface_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    metric: str
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    lower: float | None = Field(default=None, ge=0.0, le=1.0)
    upper: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline: float | None = Field(default=None, ge=0.0, le=1.0)
    realizability: Realizability
    can_clear: bool
    can_block: bool
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def evidence_semantics_are_consistent(self) -> EvidenceRecord:
        if self.observed_at.utcoffset() is None:
            raise ValueError("evidence observed_at must include a timezone offset")
        if self.evidence_class is EvidenceClass.SCREEN and (self.can_block or self.can_clear):
            raise ValueError("screen evidence cannot block or clear")
        if self.evidence_class is EvidenceClass.FLOOR and self.can_clear:
            raise ValueError("floor evidence cannot clear")
        if self.evidence_class is EvidenceClass.CEILING and self.can_block:
            raise ValueError("ceiling evidence cannot block")
        if self.realizability is Realizability.AUDITOR_ONLY and self.can_clear:
            raise ValueError("auditor-only evidence cannot clear")
        if self.can_clear and self.upper is None:
            raise ValueError("evidence that can clear must provide an upper bound")
        if self.can_clear and self.coverage is not EvidenceCoverage.COMPLETE_INTERFACE:
            raise ValueError("only complete-interface evidence may clear a threat")
        if self.can_block and self.lower is None:
            raise ValueError("evidence that can block must provide a lower bound")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("evidence lower bound cannot exceed upper bound")
        if self.value is not None and self.lower is not None and self.value < self.lower:
            raise ValueError("evidence value cannot be below its lower bound")
        if self.value is not None and self.upper is not None and self.value > self.upper:
            raise ValueError("evidence value cannot exceed its upper bound")
        if self.evidence_class is EvidenceClass.EXACT:
            if self.lower is None or self.upper is None or abs(self.lower - self.upper) > 1e-12:
                raise ValueError("exact evidence requires equal lower and upper values")
        if self.evidence_class is EvidenceClass.CEILING and self.upper is None:
            raise ValueError("ceiling evidence requires an upper bound")
        if self.evidence_class is EvidenceClass.FLOOR and self.lower is None:
            raise ValueError("floor evidence requires a lower bound")
        return self


class AttackBatteryStatus(StrictModel):
    mode: CeilingAttackBatteryMode
    requirement_id: str | None = Field(default=None, min_length=3, max_length=128)
    required_attack_ids: tuple[str, ...] = ()
    completed_attack_ids: tuple[str, ...] = ()
    passing_positive_control_ids: tuple[str, ...] = ()
    satisfied: bool
    waiver_reason: str | None = Field(default=None, min_length=1, max_length=4096)
    failure_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def status_matches_mode(self) -> AttackBatteryStatus:
        for label, values in (
            ("required attack IDs", self.required_attack_ids),
            ("completed attack IDs", self.completed_attack_ids),
            ("passing positive-control IDs", self.passing_positive_control_ids),
            ("failure reasons", self.failure_reasons),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"attack-battery {label} must be unique")
        if self.mode is CeilingAttackBatteryMode.REQUIRED:
            if self.requirement_id is None or not self.required_attack_ids:
                raise ValueError("a required attack battery needs a requirement and attack IDs")
            if self.waiver_reason is not None:
                raise ValueError("a required attack battery cannot carry a waiver reason")
            if self.satisfied == bool(self.failure_reasons):
                raise ValueError("attack-battery satisfaction must match its failure reasons")
        elif self.mode is CeilingAttackBatteryMode.WAIVED:
            if not self.satisfied or self.waiver_reason is None:
                raise ValueError("a waived attack battery must record its reason")
            if self.requirement_id is not None or self.required_attack_ids or self.failure_reasons:
                raise ValueError("a waived attack battery cannot claim a required execution")
        else:
            if self.satisfied or self.waiver_reason is not None or self.requirement_id is not None:
                raise ValueError("a prohibited ceiling cannot claim a battery or waiver")
        return self


class ThreatDecision(StrictModel):
    threat_id: str
    population_scope_id: str
    population_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_game_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessed_interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessed_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessed_release_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessed_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_metric: DecisionMetric
    kind: ThreatKind
    mandatory: bool
    tolerance: float
    tolerance_basis: Literal["absolute", "incremental"]
    lower_bound: float
    upper_bound: float
    verdict: Verdict
    evidence_ids: tuple[str, ...]
    excluded_evidence_ids: tuple[str, ...] = ()
    evidence_consistency: EvidenceConsistency
    conflicting_evidence_ids: tuple[str, ...] = ()
    clearance_evidence_class: EvidenceClass | None = None
    ceiling_attack_battery: AttackBatteryStatus
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def evidence_consistency_matches_bounds(self) -> ThreatDecision:
        contradictory = self.lower_bound > self.upper_bound + 1e-12
        if contradictory != (self.evidence_consistency is EvidenceConsistency.CONTRADICTORY):
            raise ValueError("evidence consistency does not match the decision bounds")
        if self.evidence_consistency is EvidenceConsistency.CONTRADICTORY:
            if not self.conflicting_evidence_ids:
                raise ValueError("contradictory evidence must identify the conflicting records")
            if not set(self.conflicting_evidence_ids).issubset(self.evidence_ids):
                raise ValueError("conflicting evidence identifiers must belong to the decision")
            if self.verdict is Verdict.CLEAR:
                raise ValueError("contradictory evidence cannot clear a threat")
        elif self.conflicting_evidence_ids:
            raise ValueError("non-contradictory evidence cannot identify conflicting records")
        if (
            self.evidence_consistency is EvidenceConsistency.INSUFFICIENT
            and self.verdict is not Verdict.INCONCLUSIVE
        ):
            raise ValueError("insufficient evidence must produce an inconclusive verdict")
        if (
            self.evidence_consistency is EvidenceConsistency.CONSISTENT
            and self.verdict is Verdict.INCONCLUSIVE
        ):
            raise ValueError("a non-contradictory inconclusive verdict must be insufficient")
        if len(self.conflicting_evidence_ids) != len(set(self.conflicting_evidence_ids)):
            raise ValueError("conflicting evidence identifiers must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("decision evidence identifiers must be unique")
        if len(self.excluded_evidence_ids) != len(set(self.excluded_evidence_ids)):
            raise ValueError("excluded evidence identifiers must be unique")
        if set(self.evidence_ids) & set(self.excluded_evidence_ids):
            raise ValueError("included and excluded evidence identifiers must be disjoint")
        if self.verdict is Verdict.CLEAR:
            if self.clearance_evidence_class not in (EvidenceClass.EXACT, EvidenceClass.CEILING):
                raise ValueError("a clear decision must identify exact or ceiling evidence")
            if self.clearance_evidence_class is EvidenceClass.CEILING:
                battery = self.ceiling_attack_battery
                if battery.mode is CeilingAttackBatteryMode.PROHIBITED:
                    raise ValueError("a policy-prohibited ceiling cannot clear a threat")
                if battery.mode is CeilingAttackBatteryMode.REQUIRED and not battery.satisfied:
                    raise ValueError("ceiling clearance requires a satisfied attack battery")
        elif self.clearance_evidence_class is not None:
            raise ValueError("only a clear decision may name a clearance evidence class")
        return self


class AssessmentCompositionScope(StrEnum):
    SINGLE_RELEASE_NO_PORTFOLIO = "single_release_no_portfolio"


class InterfaceAssurance(StrEnum):
    DECLARED_INTERFACE_ONLY = "declared_interface_only"


class AssessmentScope(StrictModel):
    """Machine-readable limits on what an assessment report establishes."""

    composition_scope: Literal[
        AssessmentCompositionScope.SINGLE_RELEASE_NO_PORTFOLIO
    ] = AssessmentCompositionScope.SINGLE_RELEASE_NO_PORTFOLIO
    declared_previous_release_ids: tuple[str, ...] = ()
    portfolio_assessment_required: Literal[True] = True
    interface_assurance: Literal[
        InterfaceAssurance.DECLARED_INTERFACE_ONLY
    ] = InterfaceAssurance.DECLARED_INTERFACE_ONLY
    live_interface_verified: Literal[False] = False
    gateway_interface_conformance_required: Literal[True] = True
    authorization_eligible: Literal[False] = False


class AssessmentReport(StrictModel):
    schema_version: Literal["5.0"] = "5.0"
    assessment_id: str
    release_id: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    created_at: datetime
    request_sha256: str
    artifact_sha256: str
    release_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_model_family: str = Field(min_length=1, max_length=128)
    release_model_profile: ModelProfile
    release_interface: InterfaceContract
    assessment_scope: AssessmentScope
    release_expires_at: datetime | None = None
    policy_expires_at: datetime | None = None
    population_scope_sha256s: dict[str, str]
    population_scopes: tuple[PopulationScope, ...]
    evidence: tuple[EvidenceRecord, ...]
    decisions: tuple[ThreatDecision, ...]
    overall_verdict: OverallVerdict
    runtime_identity: RuntimeIdentity
    engine_version: str

    @model_validator(mode="after")
    def report_bindings_are_complete(self) -> AssessmentReport:
        expected = {scope.scope_id for scope in self.population_scopes}
        if set(self.population_scope_sha256s) != expected:
            raise ValueError("report population-scope hashes do not match its declared scopes")
        for value in (self.created_at, self.release_expires_at, self.policy_expires_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("assessment report timestamps must include timezone offsets")
        if self.runtime_identity.component_id != "assurance_engine":
            raise ValueError("assessment report runtime identity must name assurance_engine")
        if self.runtime_identity.component_version != "AssessmentReport/5.0":
            raise ValueError("assessment report runtime identity has the wrong component version")
        if self.runtime_identity.package_version != self.engine_version:
            raise ValueError("assessment report engine version does not match its runtime identity")
        evidence_ids = [record.evidence_id for record in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("assessment report evidence identifiers must be unique")
        decision_ids = [decision.threat_id for decision in self.decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("assessment report threat decisions must be unique")
        decisions_by_threat = {decision.threat_id: decision for decision in self.decisions}
        evidence_by_threat: dict[str, set[str]] = {}
        for record in self.evidence:
            evidence_by_threat.setdefault(record.threat_id, set()).add(record.evidence_id)
        if not set(evidence_by_threat).issubset(decisions_by_threat):
            raise ValueError("assessment report contains evidence without a threat decision")
        interface_sha256 = _canonical_model_sha256(self.release_interface)
        for decision in self.decisions:
            disposition = set(decision.evidence_ids) | set(decision.excluded_evidence_ids)
            if disposition != evidence_by_threat.get(decision.threat_id, set()):
                raise ValueError(
                    f"decision {decision.threat_id} does not disposition every evidence record"
                )
            if decision.assessed_interface_sha256 != interface_sha256:
                raise ValueError(
                    f"decision {decision.threat_id} does not bind the report interface"
                )
            if decision.assessed_artifact_sha256 != self.artifact_sha256:
                raise ValueError(
                    f"decision {decision.threat_id} does not bind the report artifact"
                )
            if decision.assessed_release_contract_sha256 != self.release_contract_sha256:
                raise ValueError(
                    f"decision {decision.threat_id} does not bind the report release contract"
                )
            if decision.assessed_policy_sha256 != self.policy_sha256:
                raise ValueError(
                    f"decision {decision.threat_id} does not bind the report policy"
                )
        return self


class SignedManifest(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    assessment_id: str
    release_id: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    artifact_sha256: str
    release_interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str
    report_sha256: str
    overall_verdict: OverallVerdict
    composition_scope: AssessmentCompositionScope
    interface_assurance: InterfaceAssurance
    authorization_eligible: Literal[False] = False
    created_at: datetime
    expires_at: datetime | None = None
    signer_key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    canonicalization: Literal["MRA-PY-JSON-1"] = "MRA-PY-JSON-1"
    signature_b64: str

    @model_validator(mode="after")
    def timestamps_are_timezone_aware(self) -> SignedManifest:
        if self.created_at.utcoffset() is None:
            raise ValueError("manifest created_at must include a timezone offset")
        if self.expires_at is not None and self.expires_at.utcoffset() is None:
            raise ValueError("manifest expires_at must include a timezone offset")
        return self
