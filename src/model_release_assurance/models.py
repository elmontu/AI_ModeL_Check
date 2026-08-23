from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


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
    model_provider: str = Field(min_length=1, max_length=256)
    model_identifier: str = Field(min_length=1, max_length=256)
    model_version: str = Field(min_length=1, max_length=256)
    tokenizer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decoding_parameters: dict[str, str | int | float | bool] = Field(min_length=1)
    system_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_sha256s: tuple[str, ...] = ()
    retrieval_corpus_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    retriever_config_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tool_names: tuple[str, ...] = ()
    tool_policy_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    memory_mode: Literal["none", "session", "persistent"]
    memory_ttl_seconds: int | None = Field(default=None, ge=0)
    logging_mode: Literal["none", "security_only", "full_transcript"]
    provider_retention_days: int = Field(ge=0)
    maximum_session_tokens: int = Field(gt=0)
    maximum_lifetime_queries: int = Field(gt=0)
    maximum_concurrent_sessions: int = Field(gt=0)
    reset_semantics: str = Field(min_length=1, max_length=2048)
    filter_bundle_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
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


class InterfaceContract(StrictModel):
    protocol_type: Literal["predictive", "interactive_llm"] = "predictive"
    access: Literal["aggregate", "label", "score", "text", "embedding", "gradient", "weights", "full_artifact"]
    outputs: tuple[str, ...] = ()
    precision_bits: int | None = Field(default=None, ge=1, le=4096)
    query_budget: int | None = Field(default=None, ge=0)
    adaptive_queries: bool = False
    authenticated: bool = False
    rate_limited: bool = False
    llm_protocol: LlmProtocolContract | None = None
    notes: str = ""

    @model_validator(mode="after")
    def protocol_matches_interface(self) -> InterfaceContract:
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


class PolicyRule(StrictModel):
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: ThreatKind
    mandatory: bool
    decision_metric: DecisionMetric
    metric_parameters: dict[str, float] = Field(default_factory=dict)
    tolerance: float = Field(ge=0.0, le=1.0)
    tolerance_basis: Literal["absolute", "incremental"]

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
        return self


class PolicyBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    policy_version: str = Field(min_length=1, max_length=64)
    effective_from: datetime
    expires_at: datetime | None = None
    rules: tuple[PolicyRule, ...]

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


class AnalyzerProvenance(StrictModel):
    tool: str = Field(min_length=1, max_length=256)
    tool_version: str = Field(min_length=1, max_length=128)
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


AnalyzerInput = Annotated[
    TreeLinkageInput | DpInput | AttackInput | PopulationInput | ControlledInferenceInput,
    Field(discriminator="analyzer"),
]


class AssessmentRequest(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
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
    reasons: tuple[str, ...]


class AssessmentReport(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
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
    release_expires_at: datetime | None = None
    policy_expires_at: datetime | None = None
    population_scope_sha256s: dict[str, str]
    population_scopes: tuple[PopulationScope, ...]
    evidence: tuple[EvidenceRecord, ...]
    decisions: tuple[ThreatDecision, ...]
    overall_verdict: OverallVerdict
    engine_version: str

    @model_validator(mode="after")
    def report_bindings_are_complete(self) -> AssessmentReport:
        expected = {scope.scope_id for scope in self.population_scopes}
        if set(self.population_scope_sha256s) != expected:
            raise ValueError("report population-scope hashes do not match its declared scopes")
        for value in (self.created_at, self.release_expires_at, self.policy_expires_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("assessment report timestamps must include timezone offsets")
        return self


class SignedManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assessment_id: str
    release_id: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    artifact_sha256: str
    request_sha256: str
    report_sha256: str
    overall_verdict: OverallVerdict
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
