from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Iterable

from .decision import decision_game_sha256, population_scope_sha256
from .incomplete_portfolio import (
    StatisticalCoverage,
    decimal_fraction,
    finite_prior_contract_sha256,
    portfolio_prior_fractions,
    verify_analytic_portfolio,
)
from .integrity import canonical_json_bytes, sha256_bytes
from .models import (
    AssessmentRequest,
    DpInput,
    FiniteChannelCeilingInput,
    ThreatContract,
    ThreatKind,
    TreeLinkageInput,
)


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

_FINITE_CHANNEL_CLEARING_PATH = "finite_channel_ceiling_complete_declared_interface"
_FINITE_CHANNEL_DECISION_METRICS = frozenset({
    "bayes_linkage_success",
    "incremental_bayes_linkage_success",
    "equal_prior_membership_success",
    "finite_secret_exact_guess_success",
})


MODEL_FAMILY_CATALOG: tuple[ModelFamilyCoverage, ...] = (
    ModelFamilyCoverage("linear_generalized_linear", "Linear and generalized-linear models", ("linear", "linear_model", "logistic_regression", "glm", "elastic_net"), ("coefficient disclosure", "membership", "sensitive-attribute inference"), (_M, _A, _R), ("generic attack floors", "exact finite channel", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("tree_ensemble", "Decision trees and tree ensembles", ("tree", "decision_tree", "random_forest", "extra_trees", "xgboost", "lightgbm", "catboost", "gbdt"), ("leaf/path linkage", "membership", "attribute inference", "model extraction"), (_L, _M, _A, _R), ("tree linkage analyzer", "generic attack floors", "exact finite channel", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("kernel_method", "Kernel methods", ("svm", "support_vector_machine", "kernel_ridge", "gaussian_process"), ("support-vector disclosure", "membership", "model extraction"), (_M, _A, _R), ("generic attack floors", "exact finite channel", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("nearest_neighbor", "Nearest-neighbour and exemplar models", ("knn", "nearest_neighbour", "nearest_neighbor_model"), ("direct exemplar disclosure", "membership", "linkage"), (_L, _M, _A, _R), ("recipient-realizable exact channel", "generic attack floors", "interface restriction"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("probabilistic_bayesian", "Probabilistic and Bayesian models", ("bayesian", "probabilistic", "naive_bayes", "bayesian_network"), ("parameter/posterior leakage", "membership", "attribute inference"), (_M, _A, _R), ("exact finite channel", "generic attack floors", "complete DP mechanism"), CoverageStatus.GENERIC_CORE_APPLICABLE),
    ModelFamilyCoverage("tabular_neural_network", "Tabular and dense neural networks", ("mlp", "neural_network", "tabnet", "transformer_tabular"), ("membership", "attribute inference", "reconstruction", "white-box leakage"), (_M, _A, _R), ("generic and multi-reference attack floors", "complete DP-SGD mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("vision_model", "Computer-vision models", ("cnn", "convnet", "alexnet", "densenet", "resnet", "efficientnet", "vision_transformer", "vit", "object_detector", "segmentation_model"), ("image memorization", "membership", "inversion", "biometric linkage"), (_L, _M, _A, _R), ("modality-specific attack floors", "complete DP mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("speech_audio_model", "Speech and audio models", ("speech_model", "audio_model", "asr", "speaker_model"), ("voice/identity leakage", "memorization", "membership", "reconstruction"), (_L, _M, _A, _R), ("modality-specific attack floors", "complete DP mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("time_series_forecasting", "Time-series and forecasting models", ("time_series", "forecast", "arima", "state_space_model"), ("trajectory linkage", "temporal reconstruction", "membership", "repeated-release composition"), (_L, _M, _A, _R), ("sequence-aware attacks", "exact/analytic channel", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("recommender_ranking", "Recommender and ranking models", ("recommender", "ranking_model", "collaborative_filtering", "learning_to_rank"), ("preference inference", "membership", "user linkage", "adaptive-query composition"), (_L, _M, _A, _R), ("user-level attacks", "bounded-interface channel", "complete user-level DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("clustering_unsupervised", "Clustering and unsupervised models", ("clustering", "kmeans", "mixture_model", "topic_model"), ("cluster-membership disclosure", "membership", "attribute inference"), (_M, _A, _R), ("task-specific attacks", "exact finite channel", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("anomaly_detection", "Anomaly and novelty detectors", ("anomaly_detector", "isolation_forest", "one_class_svm", "novelty_detection"), ("outlier identity disclosure", "membership", "rare-attribute inference"), (_L, _M, _A), ("tail-aware attacks", "bounded-interface channel", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("embedding_representation", "Embedding and representation models", ("embedding", "encoder", "representation_model", "feature_extractor"), ("nearest-neighbour linkage", "membership", "attribute leakage", "inversion"), (_L, _M, _A, _R), ("retrieval/linkage attacks", "inversion attacks", "complete DP mechanism"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("graph_model", "Graph and network models", ("gnn", "graph_neural_network", "graph_embedding", "network_model"), ("node/edge membership", "link inference", "neighbourhood reconstruction"), (_L, _M, _A, _R), ("graph-specific attacks", "node/edge-level DP mechanism", "bounded-interface channel"), CoverageStatus.DEDICATED_WORKER_REQUIRED),
    ModelFamilyCoverage("generative_text_llm", "Generative text and large language models", ("llm", "language_model", "text_generator", "foundation_language_model", "llama", "meta_llama", "mistral", "qwen", "gemma", "phi", "transformer_lm", "huggingface_causal_lm"), ("verbatim extraction", "training membership", "prompt/RAG/tool leakage", "watermark/canary evasion", "adaptive transcript composition"), (_M, _A, _R), ("dedicated watermark analyzer", "randomized IN/OUT canary analyzer", "transcript-level mechanism"), CoverageStatus.INTERACTIVE_PROTOCOL_NOT_CLEARABLE),
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
    default_clearing_paths = _default_clearing_paths(request)
    mandatory_threat_ids = {
        threat.threat_id for threat in request.threats if threat.mandatory
    }
    complete_finite_channel_route = bool(mandatory_threat_ids) and all(
        _FINITE_CHANNEL_CLEARING_PATH in default_clearing_paths[threat_id]
        for threat_id in mandatory_threat_ids
    )
    if entry.family_id == "custom":
        reasons.append("model_family is not in the governed catalog")
    if missing:
        advisories.append(
            "recommended privacy threat families are absent; policy owners must confirm that the omitted secrets/harms are genuinely out of scope"
        )
    if (
        request.release.interface.protocol_type == "interactive_llm"
        and not complete_finite_channel_route
    ):
        reasons.append("interactive transcript clearance is deliberately unsupported")
    if (
        entry.status is not CoverageStatus.GENERIC_CORE_APPLICABLE
        and not complete_finite_channel_route
    ):
        reasons.append("one or more dedicated family/modality workers are required")
    threats_without_default_clearing_path = sorted(
        threat.threat_id
        for threat in request.threats
        if threat.mandatory and not default_clearing_paths[threat.threat_id]
    )
    if threats_without_default_clearing_path:
        advisories.append(
            "the shipped analyzer roster has no candidate clearing path for one or more "
            "declared mandatory threats; floor and screen evidence can still block or diagnose"
        )
    return {
        "release_id": request.release.release_id,
        "submitted_model_family": request.release.model_family,
        "resolved_family": entry.as_dict(),
        "model_profile": profile.model_dump(mode="json"),
        "declared_threats": sorted(kind.value for kind in declared),
        "missing_recommended_threats": missing,
        "declared_lineage_release_count": len(request.release.previous_release_ids),
        "portfolio_assessment_required": True,
        "authoritative_portfolio_registry_required": True,
        "default_clearing_paths": default_clearing_paths,
        "threats_without_default_clearing_path": threats_without_default_clearing_path,
        "coverage_ready": not reasons,
        "taxonomy_complete": False,
        "scope_truth_verified": False,
        "readiness_scope": "analyzer-routing-only; approved scenario/channel partition and exclusions required separately",
        "can_clear": False,
        "advisories": advisories,
        "reasons": reasons or ["catalog routing is available; threat completeness, evidence and the assurance gate remain required"],
    }


def _default_clearing_paths(request: AssessmentRequest) -> dict[str, list[str]]:
    """Report candidate paths in the shipped roster; never claim a release verdict.

    A listed path still has to produce a validated ceiling no greater than policy tolerance.
    All paths assess the submitter-declared interface only; deployment conformance remains a
    separate gateway obligation.
    """

    threats = {threat.threat_id: threat for threat in request.threats}
    paths: dict[str, list[str]] = {threat_id: [] for threat_id in threats}
    interface_sha256 = sha256_bytes(canonical_json_bytes(request.release.interface))
    governed_family = resolve_model_family(request.release.model_family).family_id != "custom"
    for value in request.analyzer_inputs:
        threat = threats[value.threat_id]
        if isinstance(value, FiniteChannelCeilingInput):
            if governed_family and _qualifying_finite_channel_input(
                request,
                threat,
                value,
                interface_sha256=interface_sha256,
            ):
                paths[threat.threat_id].append(_FINITE_CHANNEL_CLEARING_PATH)
            continue
        if isinstance(value, TreeLinkageInput):
            if (
                threat.kind is ThreatKind.LINKAGE
                and value.recipient_has_candidate_roster
                and value.recipient_has_target_signal
                and value.complete_interface_coverage
                and value.observed_interface_sha256 == interface_sha256
            ):
                paths[threat.threat_id].append(
                    "tree_recipient_exact_complete_declared_interface"
                )
            continue
        if not isinstance(value, DpInput):
            continue
        base_valid = (
            value.accountant_replayed
            and value.complete_pipeline
            and value.protected_unit == request.release.protected_unit
        )
        metric_valid = False
        if threat.kind is ThreatKind.MEMBERSHIP:
            metric_valid = threat.decision_metric == "equal_prior_membership_success" or (
                threat.decision_metric == "membership_tpr_at_fpr"
                and value.fpr is not None
                and abs(value.fpr - threat.metric_parameters["target_fpr"]) <= 1e-15
            )
        elif threat.decision_metric == "finite_secret_exact_guess_success":
            policy_prior_cap = threat.metric_parameters.get("maximum_secret_prior")
            metric_valid = (
                value.secret_cardinality is not None
                and value.maximum_secret_prior is not None
                and value.pairwise_secret_relation_validated
                and value.secret_prior_bound_validated
                and policy_prior_cap is not None
                and value.maximum_secret_prior <= policy_prior_cap + 1e-15
            )
        if base_valid and metric_valid:
            paths[threat.threat_id].append("dp_complete_pipeline_declared_interface")
    return paths


def _qualifying_finite_channel_input(
    request: AssessmentRequest,
    threat: ThreatContract,
    value: FiniteChannelCeilingInput,
    *,
    interface_sha256: str,
) -> bool:
    """Recognize a plausible complete-interface ceiling route, never a verdict."""

    if not all((
        value.release_enforced_finite_alphabet,
        value.complete_interface_coverage,
        value.recipient_realizable,
        value.bounded_transcript_complete,
    )):
        return False
    if threat.decision_metric not in _FINITE_CHANNEL_DECISION_METRICS:
        return False
    if threat.finite_game is None:
        return False

    problem = value.analytic_evidence.problem
    context = value.evidence_context
    release = request.release
    scope = next(
        (item for item in request.population_scopes if item.scope_id == threat.population_scope_id),
        None,
    )
    if scope is None:
        return False
    release_contract_sha256 = sha256_bytes(canonical_json_bytes(release))
    expected_scope_sha256 = population_scope_sha256(scope)
    expected_game_sha256 = decision_game_sha256(threat, scope)
    mechanism_claims = {
        claim
        for evidence in problem.mechanism_evidence
        for claim in evidence.supports
    }
    required_release_claims = {
        f"artifact:{release.artifact_sha256}",
        f"interface:{interface_sha256}",
        f"complete-transcript:{release.release_id}",
    }
    bound_prior = (
        problem.rational_prior
        if problem.rational_prior is not None
        else problem.prior
    )
    required_prior_claims = {
        "prior",
        f"decision-game:{problem.decision_game_sha256}",
        f"finite-prior:{finite_prior_contract_sha256(problem.state_ids, bound_prior)}",
    }
    if problem.rational_prior is None:
        return False
    normalized_prior = portfolio_prior_fractions(problem)
    if (
        value.threat_id != threat.threat_id
        or value.population_scope_id != threat.population_scope_id
        or value.observed_interface_sha256 != interface_sha256
        or value.observed_artifact_sha256 != release.artifact_sha256
        or context.release_id != release.release_id
        or context.release_contract_sha256 != release_contract_sha256
        or context.policy_sha256 != request.policy.policy_sha256
        or context.artifact_sha256 != release.artifact_sha256
        or context.interface_sha256 != interface_sha256
        or context.population_scope_id != threat.population_scope_id
        or context.population_scope_sha256 != expected_scope_sha256
        or context.decision_game_sha256 != expected_game_sha256
        or problem.threat_id != threat.threat_id
        or problem.population_scope_id != threat.population_scope_id
        or problem.population_scope_sha256 != expected_scope_sha256
        or problem.decision_game_sha256 != expected_game_sha256
        or threat.finite_game.state_ids != problem.state_ids
        or tuple(
            probability.as_fraction()
            for probability in threat.finite_game.prior
        ) != normalized_prior
        or len(problem.releases) != 1
        or problem.releases[0].release_id != release.release_id
        or not problem.selection_valid
        or problem.coverage is not StatisticalCoverage.SIMULTANEOUS
        or not required_release_claims.issubset(mechanism_claims)
        or "confidence-endpoints:outward-validated"
        not in problem.releases[0].evidence.supports
        or not required_prior_claims.issubset(set(problem.prior_evidence.supports))
        or (
            release.interface.protocol_type == "interactive_llm"
            and release.interface.query_budget is None
        )
    ):
        return False

    if (
        value.state_trials is None
        or len(value.state_trials) != len(problem.state_ids)
        or any(trial < 1 for trial in value.state_trials)
    ):
        return False

    decision_problem = problem.decision_problem
    exact_guess_gain = tuple(
        tuple(1.0 if state == action else 0.0 for action in problem.state_ids)
        for state in problem.state_ids
    )
    if (
        decision_problem.state_ids != problem.state_ids
        or decision_problem.action_ids != problem.state_ids
        or decision_problem.gain != exact_guess_gain
    ):
        return False
    if threat.decision_metric == "equal_prior_membership_success":
        if normalized_prior != (Fraction(1, 2), Fraction(1, 2)):
            return False
    if threat.decision_metric == "finite_secret_exact_guess_success":
        prior_cap = threat.metric_parameters.get("maximum_secret_prior")
        if prior_cap is None or max(normalized_prior) > decimal_fraction(prior_cap):
            return False

    try:
        verification = verify_analytic_portfolio(value.analytic_evidence)
    except (ArithmeticError, AssertionError, TypeError, ValueError):
        return False
    return bool(
        verification.valid
        and verification.rationally_replayed
        and verification.outward_rounded
    )


def known_model_family_ids() -> Iterable[str]:
    return _BY_ID.keys()
