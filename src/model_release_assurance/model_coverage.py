from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .models import AssessmentRequest, ThreatKind


class CoverageStatus(StrEnum):
    GENERIC_CORE_APPLICABLE = "generic_core_applicable"
    DEDICATED_WORKER_REQUIRED = "dedicated_worker_required"
    INTERACTIVE_PROTOCOL_NOT_CLEARABLE = "interactive_protocol_not_clearable"
    CUSTOM_REVIEW_REQUIRED = "custom_review_required"


@dataclass(frozen=True)
class ModelFamilyCoverage:
    family_id: str
    display_name: str
    aliases: tuple[str, ...]
    primary_risks: tuple[str, ...]
    recommended_threats: tuple[ThreatKind, ...]
    evidence_routes: tuple[str, ...]
    status: CoverageStatus

    def as_dict(self) -> dict[str, object]:
        return {
            "family_id": self.family_id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "primary_risks": list(self.primary_risks),
            "recommended_threats": [item.value for item in self.recommended_threats],
            "evidence_routes": list(self.evidence_routes),
            "status": self.status.value,
        }


_L = ThreatKind.LINKAGE
_M = ThreatKind.MEMBERSHIP
_A = ThreatKind.ATTRIBUTE
_R = ThreatKind.RECONSTRUCTION


MODEL_FAMILY_CATALOG: tuple[ModelFamilyCoverage, ...] = (
    ModelFamilyCoverage("linear_generalized_linear", "Linear and generalized-linear models", ("linear", "linear_model", "logistic_regression", "glm", "elastic_net"), ("coefficient disclosure", "membership", "sensitive-attribute inference"), (_M, _A, _R), ("generic attack floors", "exact finite channel", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("tree_ensemble", "Decision trees and tree ensembles", ("tree", "decision_tree", "random_forest", "extra_trees", "xgboost", "lightgbm", "catboost", "gbdt"), ("leaf/path linkage", "membership", "attribute inference", "model extraction"), (_L, _M, _A, _R), ("tree linkage analyzer", "generic attack floors", "exact finite channel", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("kernel_method", "Kernel methods", ("svm", "support_vector_machine", "kernel_ridge", "gaussian_process"), ("support-vector disclosure", "membership", "model extraction"), (_M, _A, _R), ("generic attack floors", "exact finite channel", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("nearest_neighbor", "Nearest-neighbour and exemplar models", ("knn", "nearest_neighbour", "nearest_neighbor_model"), ("direct exemplar disclosure", "membership", "linkage"), (_L, _M, _A, _R), ("recipient-realizable exact channel", "generic attack floors", "interface restriction"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("probabilistic_bayesian", "Probabilistic and Bayesian models", ("bayesian", "probabilistic", "naive_bayes", "bayesian_network"), ("parameter/posterior leakage", "membership", "attribute inference"), (_M, _A, _R), ("exact finite channel", "generic attack floors", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("tabular_neural_network", "Tabular and dense neural networks", ("mlp", "neural_network", "tabnet", "transformer_tabular"), ("membership", "attribute inference", "reconstruction", "white-box leakage"), (_M, _A, _R), ("generic and multi-reference attack floors", "complete DP-SGD mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("vision_model", "Computer-vision models", ("cnn", "vision_transformer", "vit", "object_detector", "segmentation_model"), ("image memorization", "membership", "inversion", "biometric linkage"), (_L, _M, _A, _R), ("modality-specific attack floors", "complete DP mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("speech_audio_model", "Speech and audio models", ("speech_model", "audio_model", "asr", "speaker_model"), ("voice/identity leakage", "memorization", "membership", "reconstruction"), (_L, _M, _A, _R), ("modality-specific attack floors", "complete DP mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("time_series_forecasting", "Time-series and forecasting models", ("time_series", "forecast", "arima", "state_space_model"), ("trajectory linkage", "temporal reconstruction", "membership", "repeated-release composition"), (_L, _M, _A, _R), ("sequence-aware attacks", "exact/analytic channel", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("recommender_ranking", "Recommender and ranking models", ("recommender", "ranking_model", "collaborative_filtering", "learning_to_rank"), ("preference inference", "membership", "user linkage", "adaptive-query composition"), (_L, _M, _A, _R), ("user-level attacks", "bounded-interface channel", "complete user-level DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("clustering_unsupervised", "Clustering and unsupervised models", ("clustering", "kmeans", "mixture_model", "topic_model"), ("cluster-membership disclosure", "membership", "attribute inference"), (_M, _A, _R), ("task-specific attacks", "exact finite channel", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("anomaly_detection", "Anomaly and novelty detectors", ("anomaly_detector", "isolation_forest", "one_class_svm", "novelty_detection"), ("outlier identity disclosure", "membership", "rare-attribute inference"), (_L, _M, _A), ("tail-aware attacks", "bounded-interface channel", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("embedding_representation", "Embedding and representation models", ("embedding", "encoder", "representation_model", "feature_extractor"), ("nearest-neighbour linkage", "membership", "attribute leakage", "inversion"), (_L, _M, _A, _R), ("retrieval/linkage attacks", "inversion attacks", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("graph_model", "Graph and network models", ("gnn", "graph_neural_network", "graph_embedding", "network_model"), ("node/edge membership", "link inference", "neighbourhood reconstruction"), (_L, _M, _A, _R), ("graph-specific attacks", "node/edge-level DP mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("generative_text_llm", "Generative text and large language models", ("llm", "language_model", "text_generator", "foundation_language_model"), ("verbatim extraction", "training membership", "prompt/RAG/tool leakage", "watermark/canary evasion", "adaptive transcript composition"), (_M, _A, _R), ("dedicated watermark analyzer", "randomized IN/OUT canary analyzer", "transcript-level mechanism"), CoverageStatus.INTERACTIVE_PROTOCOL_NOT_CLEARABLE),
    ModelFamilyCoverage("generative_media", "Generative image, audio, and video models", ("diffusion_model", "image_generator", "audio_generator", "video_generator", "gan"), ("training-example extraction", "membership", "identity/style leakage", "adaptive generation composition"), (_L, _M, _A, _R), ("modality-specific extraction and membership workers", "complete DP mechanism", "transcript-level analysis"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("multimodal_foundation", "Multimodal foundation models", ("multimodal", "vlm", "vision_language_model", "multimodal_foundation_model"), ("cross-modal extraction", "membership", "tool/RAG leakage", "adaptive transcript composition"), (_L, _M, _A, _R), ("cross-modal attack workers", "transcript-level mechanism", "complete DP mechanism"), CoverageStatus.INTERACTIVE_PROTOCOL_NOT_CLEARABLE),
    ModelFamilyCoverage("reinforcement_learning_agent", "Reinforcement-learning systems and agents", ("rl", "reinforcement_learning", "agent", "agentic_system", "policy_model"), ("state/history leakage", "tool side effects", "adaptive interaction", "policy extraction"), (_M, _A, _R), ("trajectory/transcript-level mechanism", "environment and tool contract", "complete DP mechanism"), CoverageStatus.INTERACTIVE_PROTOCOL_NOT_CLEARABLE),
    ModelFamilyCoverage("ensemble_composite", "Ensembles, pipelines, and composite systems", ("ensemble", "pipeline", "stacking", "mixture_of_experts", "composite"), ("component leakage", "routing leakage", "cross-component composition", "portfolio accumulation"), (_L, _M, _A, _R), ("complete component inventory", "joint interface assessment", "portfolio certificate"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("custom", "Custom or unclassified model", (), ("unknown family-specific leakage", "under-scoped interface", "unidentified composition"), (_L, _M, _A, _R), ("independent model-family review", "new versioned analyzer", "complete evidence envelope"), CoverageStatus.CUSTOM_REVIEW_REQUIRED),
)


_BY_ID = {entry.family_id: entry for entry in MODEL_FAMILY_CATALOG}
_ALIASES = {
    alias.lower(): entry.family_id
    for entry in MODEL_FAMILY_CATALOG
    for alias in (entry.family_id, *entry.aliases)
}


def resolve_model_family(value: str) -> ModelFamilyCoverage:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _BY_ID[_ALIASES.get(normalized, "custom")]


def catalog_as_dicts() -> list[dict[str, object]]:
    return [entry.as_dict() for entry in MODEL_FAMILY_CATALOG]


def assess_request_model_coverage(request: AssessmentRequest) -> dict[str, object]:
    entry = resolve_model_family(request.release.model_family)
    declared = {threat.kind for threat in request.threats}
    missing = [kind.value for kind in entry.recommended_threats if kind not in declared]
    profile = request.release.model_profile
    reasons: list[str] = []
    advisories: list[str] = []
    if entry.family_id == "custom":
        reasons.append("model_family is not in the governed catalog")
    if missing:
        advisories.append(
            "recommended privacy threat families are absent; policy owners must confirm that the omitted secrets/harms are genuinely out of scope"
        )
    if request.release.interface.protocol_type == "interactive_llm":
        reasons.append("interactive transcript clearance is deliberately unsupported")
    if entry.status is not CoverageStatus.GENERIC_CORE_APPLICABLE:
        reasons.append("one or more dedicated family/modality workers are required")
    return {
        "release_id": request.release.release_id,
        "submitted_model_family": request.release.model_family,
        "resolved_family": entry.as_dict(),
        "model_profile": profile.model_dump(mode="json"),
        "declared_threats": sorted(kind.value for kind in declared),
        "missing_recommended_threats": missing,
        "portfolio_release_count": 1 + len(request.release.previous_release_ids),
        "portfolio_assessment_required": bool(request.release.previous_release_ids),
        "coverage_ready": not reasons,
        "can_clear": False,
        "advisories": advisories,
        "reasons": reasons or ["catalog coverage is complete, but scientific evidence and the final policy gate remain required"],
    }


def known_model_family_ids() -> Iterable[str]:
    return _BY_ID.keys()
