#!/usr/bin/env python3
"""Run a model-backed, finite-population experiment for the MRA ceiling.

The upstream public-data worker is used only to obtain ephemeral target-model
losses.  This runner immediately maps those losses to a preregistered finite
alphabet and never writes them to its output directory.  It proves statements
only about a closed hidden-record benchmark wrapper and its frozen finite target
pool.  It does not assess an ordinary prediction API or authorize a release.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model_release_assurance.analyzers.finite_channel import (  # noqa: E402
    FiniteChannelCeilingAnalyzer,
)
from model_release_assurance.analyzers.attack import (  # noqa: E402
    bonferroni_per_bound_confidence,
    clopper_pearson_lower,
    clopper_pearson_upper,
)
from model_release_assurance.decision import (  # noqa: E402
    decision_game_sha256,
    population_scope_sha256,
)
from model_release_assurance.decision_theory import exact_guess_problem  # noqa: E402
from model_release_assurance.engine import AssuranceEngine  # noqa: E402
from model_release_assurance.errors import IntegrityError  # noqa: E402
from model_release_assurance.experimental_finite_wrapper import (  # noqa: E402
    validate_closed_hidden_record_wrapper,
)
from model_release_assurance.incomplete_portfolio import (  # noqa: E402
    CouplingModel,
    EvidenceReference,
    FiniteStatePriorEvidence,
    finite_prior_contract_sha256,
    solve_analytic_portfolio,
)
from model_release_assurance.integrity import (  # noqa: E402
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from model_release_assurance.models import (  # noqa: E402
    AnalyzerProvenance,
    AnalyzerRequirement,
    AssessmentRequest,
    CeilingAttackBatteryMode,
    DataModality,
    EvidenceBindingContext,
    EvidenceClass,
    EvidenceContext,
    FiniteDecisionGame,
    FiniteChannelCeilingInput,
    FiniteGameState,
    InterfaceContract,
    ModelProfile,
    ModelTask,
    PolicyBundle,
    PolicyReference,
    PolicyRule,
    PopulationScope,
    PopulationSize,
    PopulationSizeBasis,
    PopulationUnitKind,
    RationalProbability,
    ReleaseContract,
    ThreatContract,
    ThreatKind,
    TrainingParadigm,
    Verdict,
)
from model_release_assurance.portfolio_statistics import (  # noqa: E402
    AssuranceErrorBudget,
    ErrorBudgetAllocation,
    IncompletePortfolioSpecification,
    MultinomialCountsFile,
    MultinomialEvidenceRequest,
    MultinomialReleaseCounts,
    MultinomialSamplingPlan,
    MultinomialSamplingPlanRelease,
    MultinomialStateCounts,
    SourceFileReference,
    compile_multinomial_portfolio_problem,
    exact_two_sided_binomial_interval,
    generate_simultaneous_multinomial_evidence,
)
from model_release_assurance.services import (  # noqa: E402
    AnalyzerServiceRegistry,
    LocalAnalyzerService,
)


DEFAULT_CONFIG = ROOT / "reproduction" / "model-backed-finite-channel" / "config.json"
DEFAULT_OUTPUT = ROOT / "output" / "model-backed-finite-channel"
DEFAULT_CACHE = ROOT / "reproduction" / "public-privacy" / "raw"

EXPECTED_MODELS = (
    "cnn",
    "xgboost",
    "compact_transformer_llm_proxy",
)
EXPECTED_VARIANTS = ("raw_bins", "erasure_0p9")
EXPECTED_OBSERVATIONS = (
    "nll_negative",
    "nll_0_to_0p5",
    "nll_0p5_to_1",
    "nll_1_to_2",
    "nll_2_to_4",
    "nll_4_or_more",
    "nll_nonfinite",
    "wrapper_error",
    "wrapper_timeout",
    "state_independent_erasure",
)
EXPECTED_STAGES = (
    "validate_closed_hidden_record_wrapper",
    "generate_simultaneous_multinomial_evidence",
    "compile_multinomial_portfolio_problem",
    "solve_analytic_portfolio",
    "AssuranceEngine._verify_finite_channel_sources",
    "FiniteChannelCeilingAnalyzer.analyze",
)
EXPECTED_NEGATIVE_CONTROLS = (
    "visible_candidate_or_model_must_be_ineligible",
    "tampered_counts_must_fail_source_replay",
    "changed_prior_must_fail_binding",
    "missing_observation_symbol_must_fail_plan_replay",
)
EXPECTED_ACCEPTANCE_CRITERIA = (
    "all_six_oracle_risks_covered",
    "all_source_and_engine_replays_complete",
    "all_four_negative_controls_pass",
    "no_raw_scores_retained",
    "erasure_never_increases_exact_oracle_risk",
    "all_six_one_shot_engine_decisions_clear",
    "all_six_simultaneous_clear_rate_lowers_meet_minimum",
    "all_six_simultaneous_undercoverage_bounds_meet_maximum",
    "all_executable_wrapper_conformance_checks_pass",
)
FORBIDDEN_RETAINED_KEYS = frozenset({
    "raw_scores",
    "target_member_losses",
    "target_nonmember_losses",
    "calibration_member_losses",
    "calibration_nonmember_losses",
})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_PRIMARY_SEEDS = {
    "cnn": {
        "raw_bins": {"out": 609030101, "in": 609030102},
        "erasure_0p9": {"out": 609030103, "in": 609030104},
    },
    "xgboost": {
        "raw_bins": {"out": 609030201, "in": 609030202},
        "erasure_0p9": {"out": 609030203, "in": 609030204},
    },
    "compact_transformer_llm_proxy": {
        "raw_bins": {"out": 609030301, "in": 609030302},
        "erasure_0p9": {"out": 609030303, "in": 609030304},
    },
}
EXPECTED_MODEL_IDENTITIES = {
    "cnn": {
        "model_family": "cnn",
        "dataset_key": "mnist",
        "display_name": "CNN on public MNIST",
        "llm_proxy_only": False,
    },
    "xgboost": {
        "model_family": "xgboost",
        "dataset_key": "adult",
        "display_name": "XGBoost on public Adult Census Income",
        "llm_proxy_only": False,
    },
    "compact_transformer_llm_proxy": {
        "model_family": "llm_proxy_compact_transformer",
        "dataset_key": "20newsgroups",
        "display_name": (
            "Compact Transformer text classifier on public 20 Newsgroups "
            "(LLM proxy only)"
        ),
        "llm_proxy_only": True,
    },
}


class ExperimentValidationError(ValueError):
    """The preregistration or collector output is not the frozen experiment."""


def _reject_constant(value: str) -> None:
    raise ExperimentValidationError(f"non-standard JSON constant {value!r}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentValidationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def parse_json_object_bytes(
    payload: bytes,
    *,
    source: str,
    allow_nonfinite: bool = False,
) -> dict[str, Any]:
    """Parse one JSON object from the exact bytes whose digest is reported."""

    try:
        arguments: dict[str, Any] = {"object_pairs_hook": _unique_object}
        if not allow_nonfinite:
            arguments["parse_constant"] = _reject_constant
        value = json.loads(payload.decode("utf-8"), **arguments)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentValidationError(f"cannot load JSON object {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExperimentValidationError(f"JSON root must be an object: {source}")
    return value


def load_json_object(path: Path, *, allow_nonfinite: bool = False) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ExperimentValidationError(f"cannot load JSON object {path}: {exc}") from exc
    return parse_json_object_bytes(
        payload,
        source=str(path),
        allow_nonfinite=allow_nonfinite,
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_python_tree(path: Path) -> str:
    """Hash every Python source path and byte sequence in a trust-core tree."""

    files = sorted(value for value in path.rglob("*.py") if value.is_file())
    if not files:
        raise ExperimentValidationError(f"registered Python trust-core tree is empty: {path}")
    digest = hashlib.sha256(b"MRA-PYTHON-TRUST-CORE-TREE-1\0")
    for source in files:
        relative = source.relative_to(path).as_posix().encode("utf-8")
        payload = source.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def rational(value: Mapping[str, Any]) -> Fraction:
    if set(value) != {"numerator", "denominator"}:
        raise ExperimentValidationError("rational probability keys changed")
    try:
        numerator = value["numerator"]
        denominator = value["denominator"]
        if (
            isinstance(numerator, bool)
            or isinstance(denominator, bool)
            or not isinstance(numerator, int)
            or not isinstance(denominator, int)
        ):
            raise TypeError("rational components must be integers")
        result = Fraction(numerator, denominator)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ExperimentValidationError("invalid rational probability") from exc
    if result.numerator != numerator or result.denominator != denominator:
        raise ExperimentValidationError("rational probability must be in lowest terms")
    return result


def rational_payload(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentValidationError(message)


def validate_config(
    config: Mapping[str, Any],
    *,
    verify_files: bool = True,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Fail closed if the prospective design drifts from the registered study."""

    _require(set(config) == {
        "schema_version", "experiment_id", "registered_at", "authority",
        "collector", "finite_wrapper", "models", "sampling",
        "repeated_validation", "decision_game", "production_path",
        "negative_controls", "acceptance_criteria",
    }, "config top-level schema changed")
    _require(config.get("schema_version") == "1.0", "unsupported config schema")
    _require(
        config.get("experiment_id") == "model-backed-finite-channel-public-data-v1",
        "unexpected experiment identifier",
    )
    try:
        registered_at = datetime.fromisoformat(str(config["registered_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ExperimentValidationError("registered_at must be timezone-aware ISO-8601") from exc
    _require(registered_at.utcoffset() is not None, "registered_at must include a timezone")

    authority = config.get("authority", {})
    _require(set(authority) == {
        "experimental_only", "benchmark_population_conditional",
        "authorization_eligible", "authorization_granted",
        "real_world_privacy_claimed", "decision",
    }, "authority schema changed")
    _require(authority.get("experimental_only") is True, "experiment must remain experimental")
    _require(
        authority.get("benchmark_population_conditional") is True,
        "claim must remain benchmark-population conditional",
    )
    for field in ("authorization_eligible", "authorization_granted", "real_world_privacy_claimed"):
        _require(authority.get(field) is False, f"{field} must remain false")
    _require(authority.get("decision") == "no_release_authorization", "decision authority drift")

    collector = config.get("collector", {})
    _require(set(collector) == {
        "experiment_id", "runner_path", "runner_sha256", "seed", "epochs",
        "raw_output_use",
    }, "collector schema changed")
    _require(bool(HEX64.fullmatch(str(collector.get("runner_sha256", "")))), "collector digest is not lowercase SHA-256")
    _require(collector.get("runner_path") == "scripts/run_public_privacy_audit.py", "collector runner path changed")
    _require(type(collector.get("seed")) is int and collector["seed"] == 2026090301, "collector seed changed")
    _require(collector["seed"] != 20260830, "pilot seed cannot be reused")
    _require(type(collector.get("epochs")) is int and collector["epochs"] == 5, "collector epochs changed")
    _require(
        collector.get("raw_output_use")
        == "temporary_disposable_directory_then_aggregate_only_output",
        "raw collector output retention changed",
    )

    wrapper = config.get("finite_wrapper", {})
    _require(set(wrapper) == {
        "wrapper_id", "mechanism", "query_budget", "hidden_record_sampling",
        "recipient_input_fields", "recipient_observes_only",
        "candidate_record_visible", "model_or_weights_visible", "raw_loss_visible",
        "timing_visible", "identifiers_or_metadata_visible", "arbitrary_query_path",
        "observation_ids", "finite_nll_bins", "nonfinite_observation_id",
        "error_observation_id", "timeout_observation_id", "variants",
    }, "finite-wrapper schema changed")
    _require(
        wrapper.get("mechanism") == "one_query_closed_hidden_record_sampler",
        "wrapper is not the closed hidden-record sampler",
    )
    _require(wrapper.get("wrapper_id") == "closed-hidden-record-semantic-nll-v1", "wrapper identity changed")
    _require(
        wrapper.get("hidden_record_sampling")
        == (
            "auditor selects one target-pool record conditional on the sealed IN/OUT state; "
            "recipient cannot select or observe the record"
        ),
        "hidden-record sampling definition changed",
    )
    _require(
        wrapper.get("recipient_observes_only")
        == "one categorical symbol from the complete observation_ids list",
        "recipient-visible transcript definition changed",
    )
    _require(
        type(wrapper.get("query_budget")) is int and wrapper["query_budget"] == 1,
        "wrapper must allow exactly one query",
    )
    _require(wrapper.get("recipient_input_fields") == [], "recipient input must be closed")
    for field in (
        "candidate_record_visible",
        "model_or_weights_visible",
        "raw_loss_visible",
        "timing_visible",
        "identifiers_or_metadata_visible",
        "arbitrary_query_path",
    ):
        _require(wrapper.get(field) is False, f"visible channel {field} invalidates the ceiling")
    _require(tuple(wrapper.get("observation_ids", ())) == EXPECTED_OBSERVATIONS, "observation alphabet changed")
    _require(wrapper.get("nonfinite_observation_id") == "nll_nonfinite", "nonfinite output missing")
    _require(wrapper.get("error_observation_id") == "wrapper_error", "error output missing")
    _require(wrapper.get("timeout_observation_id") == "wrapper_timeout", "timeout output missing")
    variants = wrapper.get("variants", [])
    _require(tuple(value.get("variant_id") for value in variants) == EXPECTED_VARIANTS, "variant family changed")
    _require(
        all(
            isinstance(value, dict)
            and set(value) == {"variant_id", "state_independent_erasure"}
            for value in variants
        ),
        "wrapper variant schema changed",
    )
    _require(rational(variants[0]["state_independent_erasure"]) == 0, "raw variant changed")
    _require(rational(variants[1]["state_independent_erasure"]) == Fraction(9, 10), "erasure variant changed")

    bins = wrapper.get("finite_nll_bins", [])
    _require(
        all(
            isinstance(value, dict)
            and set(value) == {
                "observation_id", "lower", "upper", "lower_closed", "upper_closed",
            }
            for value in bins
        ),
        "semantic NLL-bin schema changed",
    )
    expected_edges = (
        ("nll_negative", None, "0", False, False),
        ("nll_0_to_0p5", "0", "0.5", True, False),
        ("nll_0p5_to_1", "0.5", "1", True, False),
        ("nll_1_to_2", "1", "2", True, False),
        ("nll_2_to_4", "2", "4", True, False),
        ("nll_4_or_more", "4", None, True, False),
    )
    observed_edges = tuple(
        (
            value.get("observation_id"), value.get("lower"), value.get("upper"),
            value.get("lower_closed"), value.get("upper_closed"),
        )
        for value in bins
    )
    _require(observed_edges == expected_edges, "semantic NLL bin boundaries changed")

    models = config.get("models", [])
    _require(tuple(value.get("collector_model") for value in models) == EXPECTED_MODELS, "model roster changed")
    _require(models[2].get("llm_proxy_only") is True, "Transformer must remain labelled LLM proxy only")
    seeds: list[int] = []
    for model in models:
        expected_model_keys = {
            "collector_model", "model_family", "dataset_key", "display_name",
            "sample_seeds",
        }
        if model.get("collector_model") == "compact_transformer_llm_proxy":
            expected_model_keys.add("llm_proxy_only")
        _require(set(model) == expected_model_keys, "model registration schema changed")
        identity = EXPECTED_MODEL_IDENTITIES[model["collector_model"]]
        _require(
            model["model_family"] == identity["model_family"]
            and model["dataset_key"] == identity["dataset_key"]
            and model["display_name"] == identity["display_name"]
            and model.get("llm_proxy_only", False) is identity["llm_proxy_only"],
            "model identity or dataset binding changed",
        )
        model_seeds = model.get("sample_seeds", {})
        _require(tuple(model_seeds) == EXPECTED_VARIANTS, "sampling variant seeds changed")
        for variant_id in EXPECTED_VARIANTS:
            _require(tuple(model_seeds[variant_id]) == ("out", "in"), "state seed order changed")
            seeds.extend(int(model_seeds[variant_id][state]) for state in ("out", "in"))
        _require(
            model_seeds == EXPECTED_PRIMARY_SEEDS[model["collector_model"]],
            "primary sampling seed registration changed",
        )
    _require(len(seeds) == len(set(seeds)), "sampling seeds must be globally unique")
    _require(int(collector["seed"]) not in seeds, "collector and sampling seeds must differ")

    sampling = config.get("sampling", {})
    _require(set(sampling) == {
        "model", "trials_per_state", "state_ids", "family_selection_scope",
        "assurance_alpha", "per_model_variant_alpha", "registered_family_count",
    }, "sampling schema changed")
    _require(
        sampling.get("model") == "iid_multinomial_with_replacement_conditional_on_finite_target_pool",
        "sampling model changed",
    )
    trials = sampling.get("trials_per_state")
    _require(type(trials) is int and trials == 5000, "trials_per_state changed from the registered 5000")
    _require(tuple(sampling.get("state_ids", ())) == ("out", "in"), "state order changed")
    family_count = len(models) * len(variants)
    _require(sampling.get("registered_family_count") == family_count, "family count changed")
    total_alpha = rational(sampling["assurance_alpha"])
    allocation_alpha = rational(sampling["per_model_variant_alpha"])
    _require(total_alpha == Fraction(1, 20), "assurance alpha changed")
    _require(allocation_alpha * family_count <= total_alpha, "alpha allocations exceed ledger")

    repeated = config.get("repeated_validation", {})
    _require(set(repeated) == {
        "replicates_per_model_variant", "master_seed", "seed_derivation",
        "meta_family_alpha", "maximum_simultaneous_undercoverage_upper",
        "minimum_simultaneous_clear_rate_lower", "retain_all_aggregate_count_rows",
        "production_analyzer_replay_every_replicate", "full_engine_replay",
    }, "repeated-validation schema changed")
    _require(type(repeated["replicates_per_model_variant"]) is int and repeated["replicates_per_model_variant"] == 200, "repeat count changed")
    _require(type(repeated["master_seed"]) is int and repeated["master_seed"] == 609039999, "repeat master seed changed")
    _require(
        repeated["seed_derivation"]
        == "sha256-first-64-bits:MRA-MODEL-BACKED-REPEAT-1:model:variant:replicate:state",
        "repeat seed derivation changed",
    )
    _require(rational(repeated["meta_family_alpha"]) == Fraction(1, 20), "meta alpha changed")
    _require(
        type(repeated["maximum_simultaneous_undercoverage_upper"]) is float
        and repeated["maximum_simultaneous_undercoverage_upper"] == 0.05,
        "undercoverage acceptance maximum changed",
    )
    _require(
        type(repeated["minimum_simultaneous_clear_rate_lower"]) is float
        and repeated["minimum_simultaneous_clear_rate_lower"] == 0.95,
        "clear-rate lower-bound acceptance minimum changed",
    )
    _require(repeated["retain_all_aggregate_count_rows"] is True, "repeat counts must be retained")
    _require(repeated["production_analyzer_replay_every_replicate"] is True, "every repeat must replay the analyzer")
    _require(
        repeated["full_engine_replay"] == "one_independent_primary_draw_per_model_variant",
        "full Engine replay scope changed",
    )

    game = config.get("decision_game", {})
    _require(set(game) == {"game_id", "prior", "tolerance", "metric"}, "decision-game schema changed")
    _require(game.get("metric") == "equal_prior_membership_success", "decision metric changed")
    _require(tuple(rational(value) for value in game.get("prior", ())) == (Fraction(1, 2), Fraction(1, 2)), "decision prior changed")
    _require(
        isinstance(game.get("tolerance"), (int, float))
        and not isinstance(game.get("tolerance"), bool)
        and math.isfinite(float(game["tolerance"]))
        and
        Fraction(Decimal(str(game.get("tolerance")))) == Fraction(13, 20),
        "tolerance changed from the registered 0.65",
    )
    production = config.get("production_path", {})
    _require(set(production) == {
        "experiment_runner_path", "experiment_runner_sha256",
        "assurance_engine_path", "assurance_engine_sha256",
        "analytic_solver_path", "analytic_solver_sha256",
        "wrapper_conformance_path", "wrapper_conformance_sha256",
        "attack_statistics_path", "attack_statistics_sha256",
        "trust_core_path", "trust_core_tree_sha256",
        "project_manifest_path", "project_manifest_sha256",
        "experiment_requirements_path", "experiment_requirements_sha256",
        "portfolio_statistics_sha256", "finite_channel_analyzer_sha256",
        "required_stages",
    }, "production-path schema changed")
    for field in (
        "experiment_runner_sha256",
        "assurance_engine_sha256",
        "analytic_solver_sha256",
        "wrapper_conformance_sha256",
        "attack_statistics_sha256",
        "trust_core_tree_sha256",
        "project_manifest_sha256",
        "experiment_requirements_sha256",
        "portfolio_statistics_sha256",
        "finite_channel_analyzer_sha256",
    ):
        _require(bool(HEX64.fullmatch(str(production.get(field, "")))), f"{field} is not lowercase SHA-256")
    expected_production_paths = {
        "experiment_runner_path": "scripts/run_model_backed_finite_channel.py",
        "assurance_engine_path": "src/model_release_assurance/engine.py",
        "analytic_solver_path": "src/model_release_assurance/incomplete_portfolio.py",
        "wrapper_conformance_path": "src/model_release_assurance/experimental_finite_wrapper.py",
        "attack_statistics_path": "src/model_release_assurance/analyzers/attack.py",
        "trust_core_path": "src/model_release_assurance",
        "project_manifest_path": "pyproject.toml",
        "experiment_requirements_path": "requirements-experiments.txt",
    }
    for field, expected in expected_production_paths.items():
        _require(production.get(field) == expected, f"registered source path changed: {field}")
    _require(tuple(config.get("production_path", {}).get("required_stages", ())) == EXPECTED_STAGES, "production replay stages changed")
    _require(tuple(config.get("negative_controls", ())) == EXPECTED_NEGATIVE_CONTROLS, "negative-control family changed")
    _require(tuple(config.get("acceptance_criteria", ())) == EXPECTED_ACCEPTANCE_CRITERIA, "acceptance criteria changed")

    if verify_files:
        bindings = (
            (collector["runner_path"], collector["runner_sha256"]),
            (
                config["production_path"]["experiment_runner_path"],
                config["production_path"]["experiment_runner_sha256"],
            ),
            (
                config["production_path"]["assurance_engine_path"],
                config["production_path"]["assurance_engine_sha256"],
            ),
            (
                config["production_path"]["analytic_solver_path"],
                config["production_path"]["analytic_solver_sha256"],
            ),
            (
                config["production_path"]["wrapper_conformance_path"],
                config["production_path"]["wrapper_conformance_sha256"],
            ),
            (
                config["production_path"]["attack_statistics_path"],
                config["production_path"]["attack_statistics_sha256"],
            ),
            (
                "src/model_release_assurance/portfolio_statistics.py",
                config["production_path"]["portfolio_statistics_sha256"],
            ),
            (
                "src/model_release_assurance/analyzers/finite_channel.py",
                config["production_path"]["finite_channel_analyzer_sha256"],
            ),
            (
                config["production_path"]["project_manifest_path"],
                config["production_path"]["project_manifest_sha256"],
            ),
            (
                config["production_path"]["experiment_requirements_path"],
                config["production_path"]["experiment_requirements_sha256"],
            ),
        )
        for relative, expected in bindings:
            path = root / str(relative)
            _require(path.is_file(), f"registered source missing: {relative}")
            _require(sha256_file(path) == expected, f"registered source digest changed: {relative}")
        trust_core = root / str(production["trust_core_path"])
        _require(trust_core.is_dir(), "registered trust-core tree is missing")
        _require(
            sha256_python_tree(trust_core) == production["trust_core_tree_sha256"],
            "registered Python trust-core tree digest changed",
        )
    return dict(config)


def classify_loss(value: Any, wrapper: Mapping[str, Any]) -> str:
    """Map one raw target NLL (or wrapper sentinel) to the complete alphabet."""

    if value == "__WRAPPER_ERROR__":
        return str(wrapper["error_observation_id"])
    if value == "__WRAPPER_TIMEOUT__":
        return str(wrapper["timeout_observation_id"])
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(wrapper["error_observation_id"])
    number = float(value)
    if not math.isfinite(number):
        return str(wrapper["nonfinite_observation_id"])
    for interval in wrapper["finite_nll_bins"]:
        lower = None if interval["lower"] is None else float(Decimal(interval["lower"]))
        upper = None if interval["upper"] is None else float(Decimal(interval["upper"]))
        lower_ok = lower is None or number > lower or (interval["lower_closed"] and number == lower)
        upper_ok = upper is None or number < upper or (interval["upper_closed"] and number == upper)
        if lower_ok and upper_ok:
            return str(interval["observation_id"])
    return str(wrapper["error_observation_id"])


def _count_observations(values: Sequence[Any], wrapper: Mapping[str, Any]) -> tuple[int, ...]:
    observation_ids = tuple(wrapper["observation_ids"])
    index = {value: position for position, value in enumerate(observation_ids)}
    counts = [0] * len(observation_ids)
    for value in values:
        counts[index[classify_loss(value, wrapper)]] += 1
    return tuple(counts)


def exact_channel_risk(
    state_counts: Mapping[str, Sequence[int]],
    *,
    erasure: Fraction = Fraction(0),
    erased_index: int,
) -> Fraction:
    """Exact equal-prior Bayes risk of a finite-population wrapper channel."""

    totals = {state: sum(counts) for state, counts in state_counts.items()}
    if set(state_counts) != {"out", "in"} or any(value <= 0 for value in totals.values()):
        raise ExperimentValidationError("oracle requires non-empty out/in finite populations")
    retained = Fraction(1) - erasure
    probabilities: dict[str, tuple[Fraction, ...]] = {}
    for state in ("out", "in"):
        row = [retained * Fraction(value, totals[state]) for value in state_counts[state]]
        row[erased_index] += erasure
        probabilities[state] = tuple(row)
    return sum(
        max(probabilities["out"][index], probabilities["in"][index])
        for index in range(len(probabilities["out"]))
    ) / 2


def compile_oracle(
    model_report: Mapping[str, Any],
    model_config: Mapping[str, Any],
    config: Mapping[str, Any],
    dataset: Mapping[str, Any],
) -> dict[str, Any]:
    """Consume raw losses once and return aggregate-only finite populations."""

    _require(model_report.get("model") == model_config["collector_model"], "collector model mismatch")
    model_sha256 = model_report.get("ephemeral_model_artifact_sha256")
    _require(
        isinstance(model_sha256, str) and bool(HEX64.fullmatch(model_sha256)),
        "collector did not hash the ephemeral trained model/pipeline",
    )
    attack = model_report.get("attack", {})
    raw = attack.get("raw_scores", {})
    _require(isinstance(raw, dict), "collector raw-score object missing")
    member = raw.get("target_member_losses")
    nonmember = raw.get("target_nonmember_losses")
    _require(isinstance(member, list) and isinstance(nonmember, list), "target loss pools missing")
    _require(len(member) > 0 and len(nonmember) > 0, "target loss pools must be non-empty")
    _require(attack.get("member_trials") == len(member), "member pool length changed")
    _require(attack.get("nonmember_trials") == len(nonmember), "nonmember pool length changed")

    wrapper = config["finite_wrapper"]
    counts = {
        "out": _count_observations(nonmember, wrapper),
        "in": _count_observations(member, wrapper),
    }
    erased_index = tuple(wrapper["observation_ids"]).index("state_independent_erasure")
    raw_risk = exact_channel_risk(counts, erased_index=erased_index)
    snapshot_payload = {
        "domain": "MRA-MODEL-BACKED-FINITE-POPULATION-1",
        "collector_seed": config["collector"]["seed"],
        "dataset_snapshot_sha256": dataset["processed_snapshot_sha256"],
        "ephemeral_model_artifact_sha256": model_sha256,
        "wrapper_id": wrapper["wrapper_id"],
        "state_ids": ("out", "in"),
        "observation_ids": wrapper["observation_ids"],
        "state_counts": counts,
    }
    return {
        "collector_model": model_config["collector_model"],
        "model_family": model_config["model_family"],
        "display_name": model_config["display_name"],
        "llm_proxy_only": bool(model_config.get("llm_proxy_only", False)),
        "dataset_key": model_config["dataset_key"],
        "dataset_snapshot_sha256": dataset["processed_snapshot_sha256"],
        "ephemeral_model_artifact_sha256": model_sha256,
        "utility_accuracy": model_report["utility_accuracy"],
        "training_rows": model_report["training_rows"],
        "finite_population_sha256": sha256_bytes(canonical_json_bytes(snapshot_payload)),
        "state_population_sizes": {state: sum(row) for state, row in counts.items()},
        "observation_ids": list(wrapper["observation_ids"]),
        "state_counts": {state: list(row) for state, row in counts.items()},
        "raw_wrapper_exact_bayes_risk": rational_payload(raw_risk),
    }


def sample_state_counts(
    population_counts: Sequence[int],
    *,
    trials: int,
    seed: int,
    erasure: Fraction,
    erased_index: int,
) -> tuple[int, ...]:
    """IID sampling with replacement from one frozen finite state population."""

    total = sum(population_counts)
    if total <= 0:
        raise ExperimentValidationError("cannot sample an empty finite population")
    cumulative: list[int] = []
    running = 0
    for value in population_counts:
        if value < 0:
            raise ExperimentValidationError("finite population counts cannot be negative")
        running += value
        cumulative.append(running)
    rng = random.Random(seed)
    sampled = [0] * len(population_counts)
    for _ in range(trials):
        draw = rng.randrange(total)
        observation = bisect.bisect_right(cumulative, draw)
        if erasure and rng.randrange(erasure.denominator) < erasure.numerator:
            observation = erased_index
        sampled[observation] += 1
    return tuple(sampled)


def _derived_repeat_seed(
    master_seed: int,
    model: str,
    variant: str,
    replicate: int,
    state: str,
) -> int:
    payload = (
        f"MRA-MODEL-BACKED-REPEAT-1:{master_seed}:{model}:"
        f"{variant}:{replicate}:{state}"
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _downward_alpha(value: Fraction) -> float:
    candidate = float(value)
    while Fraction(Decimal(str(candidate))) > value:
        candidate = math.nextafter(candidate, 0.0)
    if candidate <= 0.0:
        raise ExperimentValidationError("allocated per-tail alpha is not representable")
    return candidate


def _repeat_analyzer_replay(
    context: Mapping[str, Any],
    *,
    counts: Mapping[str, Sequence[int]],
    replicate: int,
    service: LocalAnalyzerService,
    allocation_alpha: Fraction,
    true_risk: Fraction,
    tolerance: Fraction,
) -> dict[str, Any]:
    """Run one repeat through production endpoints, certificate, and analyzer.

    The primary draw separately exercises source replay and the full Engine. A
    repeated draw is intentionally analyzer-level so 1,200 independent count
    families remain affordable, but it uses the same endpoint implementation,
    analytic solver, exact verifier, and finite-channel analyzer.
    """

    base: FiniteChannelCeilingInput = context["submission"]
    problem = base.analytic_evidence.problem
    observation_count = len(problem.releases[0].observation_ids)
    cell_count = len(problem.state_ids) * observation_count
    per_tail_alpha = _downward_alpha(allocation_alpha / (2 * cell_count))
    rows = tuple(tuple(counts[state]) for state in problem.state_ids)
    intervals = tuple(
        tuple(
            exact_two_sided_binomial_interval(successes, sum(row), per_tail_alpha)
            for successes in row
        )
        for row in rows
    )
    marginal = problem.releases[0].model_copy(update={
        "lower": tuple(tuple(value[0] for value in row) for row in intervals),
        "upper": tuple(tuple(value[1] for value in row) for row in intervals),
    })
    changed_problem = problem.model_copy(update={"releases": (marginal,)})
    analytic = solve_analytic_portfolio(
        changed_problem,
        method="envelope",
        certificate_id=(
            f"repeat-{context['model']['collector_model']}-"
            f"{context['variant']['variant_id']}-{replicate}"
        ),
    )
    repeat_count_sha256 = sha256_bytes(canonical_json_bytes({
        "replicate": replicate,
        "state_ids": problem.state_ids,
        "observation_ids": marginal.observation_ids,
        "counts": rows,
    }))
    value = base.model_copy(update={
        "analytic_evidence": analytic,
        "state_trials": tuple(sum(row) for row in rows),
        "provenance": base.provenance.model_copy(update={
            "source_path": "aggregate-repeat-count-row-not-source-backed.json",
            "source_sha256": repeat_count_sha256,
        }),
    })
    records = service.analyze(context["release"], context["threat"], value)
    floor = next(record for record in records if record.evidence_class is EvidenceClass.FLOOR)
    ceiling = next(record for record in records if record.evidence_class is EvidenceClass.CEILING)
    assert floor.exact_lower is not None and ceiling.exact_upper is not None
    exact_floor = floor.exact_lower.as_fraction()
    exact_ceiling = ceiling.exact_upper.as_fraction()
    decision = (
        "BLOCK" if exact_floor > tolerance
        else "CLEAR" if exact_ceiling <= tolerance
        else "HOLD"
    )
    return {
        "replicate": replicate,
        "state_counts": {state: list(counts[state]) for state in problem.state_ids},
        "aggregate_count_sha256": repeat_count_sha256,
        "production_analyzer_replayed": True,
        "full_source_and_engine_replay": False,
        "exact_floor": rational_payload(exact_floor),
        "exact_ceiling": rational_payload(exact_ceiling),
        "floor": floor.lower,
        "ceiling": ceiling.upper,
        "interval_width": float(exact_ceiling - exact_floor),
        "ceiling_excess_over_oracle": float(max(Fraction(0), exact_ceiling - true_risk)),
        "covers_oracle": exact_floor <= true_risk <= exact_ceiling,
        "decision": decision,
    }


def _validate_collector_report(report: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    collector = config["collector"]
    _require(set(report) == {
        "schema_version", "experiment_id", "orchestration", "experimental_only",
        "evidence_semantics", "seed", "epochs", "datasets", "software",
        "models", "elapsed_seconds", "decision",
    }, "collector report schema changed")
    _require(report.get("schema_version") == "1.0", "collector schema version changed")
    _require(report.get("experiment_id") == collector["experiment_id"], "collector experiment mismatch")
    _require(report.get("seed") == collector["seed"], "collector seed mismatch")
    _require(report.get("epochs") == collector["epochs"], "collector epochs mismatch")
    _require(report.get("experimental_only") is True, "collector authority changed")
    _require(report.get("decision") == "no_release_authorization", "collector decision authority changed")
    _require(
        report.get("evidence_semantics") == "empirical_attack_floors_and_screens_never_clear",
        "collector evidence semantics changed",
    )
    elapsed = report.get("elapsed_seconds")
    _require(
        isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool)
        and math.isfinite(float(elapsed)) and elapsed >= 0,
        "collector elapsed time is invalid",
    )
    orchestration = report.get("orchestration", {})
    _require(set(orchestration) == {"mode", "plan_id", "plan_sha256", "plan_path", "guidance"}, "collector orchestration schema changed")
    _require(orchestration.get("mode") == "rag_planned_mcp_executable", "collector orchestration mode changed")
    _require(bool(HEX64.fullmatch(str(orchestration.get("plan_sha256", "")))), "RAG plan digest missing")
    _require(isinstance(orchestration.get("plan_id"), str) and orchestration["plan_id"], "RAG plan id missing")
    _require(isinstance(orchestration.get("guidance"), dict), "RAG guidance bindings missing")

    software = report.get("software", {})
    _require(set(software) == {"python", "numpy", "scipy", "sklearn", "torch", "xgboost"}, "collector software schema changed")
    _require(all(isinstance(value, str) and value for value in software.values()), "collector software identity is incomplete")
    models = report.get("models")
    _require(isinstance(models, list), "collector model list missing")
    _require(len(models) == 4 and all(isinstance(value, dict) for value in models), "collector must contain four model objects")
    names = [value.get("model") for value in models]
    _require(names == ["cnn", "lstm", "xgboost", "compact_transformer_llm_proxy"], "collector model roster/order changed")
    expected_pool_sizes = {
        "cnn": 400,
        "lstm": 400,
        "xgboost": 400,
        "compact_transformer_llm_proxy": 350,
    }
    expected_training_rows = {
        "cnn": 1200,
        "lstm": 1200,
        "xgboost": 1200,
        "compact_transformer_llm_proxy": 1000,
    }
    expected_attack_keys = {
        "attack", "threshold", "member_trials", "nonmember_trials",
        "true_members", "true_nonmembers", "successes", "trials",
        "equal_prior_success", "one_sided_95pct_clopper_pearson_lower",
        "advantage_over_random", "evidence_class", "can_block", "can_clear",
        "raw_scores",
    }
    for model in models:
        _require(set(model) == {
            "model", "ephemeral_model_artifact_sha256", "utility_accuracy",
            "training_rows", "attack",
        }, f"collector model schema changed for {model.get('model')}")
        _require(bool(HEX64.fullmatch(str(model["ephemeral_model_artifact_sha256"]))), "model artifact digest is invalid")
        utility = model["utility_accuracy"]
        _require(
            isinstance(utility, (int, float)) and not isinstance(utility, bool)
            and math.isfinite(float(utility)) and 0.0 <= utility <= 1.0,
            "model utility must be a finite probability",
        )
        name = model["model"]
        _require(model["training_rows"] == expected_training_rows[name], "model training-row count changed")
        attack = model["attack"]
        _require(isinstance(attack, dict) and set(attack) == expected_attack_keys, "collector attack schema changed")
        _require(attack["attack"] == "disjoint_reference_calibrated_per_example_loss_threshold", "collector attack procedure changed")
        _require(attack["evidence_class"] == "floor" and attack["can_block"] is True and attack["can_clear"] is False, "collector floor authority changed")
        pool_size = expected_pool_sizes[name]
        _require(attack["member_trials"] == pool_size and attack["nonmember_trials"] == pool_size, "collector audit-pool shape changed")
        _require(attack["trials"] == 2 * pool_size, "collector attack trial count changed")
        raw = attack["raw_scores"]
        _require(isinstance(raw, dict) and set(raw) == {
            "target_member_losses", "target_nonmember_losses",
            "calibration_member_losses", "calibration_nonmember_losses",
        }, "collector raw-loss schema changed")
        for key, losses in raw.items():
            _require(isinstance(losses, list) and len(losses) == pool_size, f"collector {key} shape changed")
            _require(all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in losses
            ), f"collector {key} must contain only finite numeric losses")
        for field in (
            "threshold", "equal_prior_success",
            "one_sided_95pct_clopper_pearson_lower", "advantage_over_random",
        ):
            value = attack[field]
            _require(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)),
                f"collector attack field {field} is not finite",
            )
    datasets = report.get("datasets")
    _require(isinstance(datasets, dict) and set(datasets) == {"mnist", "adult", "20newsgroups"}, "collector dataset roster changed")
    dataset_keys = {
        "mnist": {"name", "openml_data_id", "openml_version", "url", "license", "processed_snapshot_sha256"},
        "adult": {"name", "openml_data_id", "openml_version", "url", "license", "processed_snapshot_sha256"},
        "20newsgroups": {"name", "url", "license", "processed_snapshot_sha256", "vocabulary_size"},
    }
    for key, dataset in datasets.items():
        _require(isinstance(dataset, dict) and set(dataset) == dataset_keys[key], f"dataset schema changed for {key}")
        _require(bool(HEX64.fullmatch(str(dataset.get("processed_snapshot_sha256", "")))), f"dataset digest invalid for {key}")
    for model in config["models"]:
        dataset = datasets.get(model["dataset_key"])
        _require(isinstance(dataset, dict), f"dataset {model['dataset_key']} missing")


def _interface(config: Mapping[str, Any]) -> InterfaceContract:
    wrapper = config["finite_wrapper"]
    return InterfaceContract.model_validate({
        "schema_version": "3.0",
        "protocol_type": "predictive",
        "access": "label",
        "outputs": ["one categorical hidden-record NLL-bin symbol"],
        "output_channels": {
            "aggregates": False,
            "labels": True,
            "scores": False,
            "probabilities": False,
            "logits": False,
            "explanations": False,
            "text": False,
            "embeddings": False,
            "gradients": False,
            "parameters": False,
            "downloadable_files": [],
            "shipped_summary_metadata": [],
            "custom_channels": ["fixed semantic NLL-bin category"],
        },
        "precision_bits": None,
        "query_budget": 1,
        "adaptive_queries": False,
        "authenticated": True,
        "rate_limited": True,
        "rate_limit": {
            "enabled": True,
            "scope": "per_identity",
            "requests_per_window": 1,
            "window_seconds": 315360000,
            "burst_capacity": 1,
            "retry_after_exposed": False,
            "enforcement": "shared_strong",
            "custom_parameters": {},
        },
        "timing": {
            "recipient_observable": False,
            "measurement_resolution_milliseconds": None,
            "includes_queue_time": False,
            "mitigation": "not_applicable",
            "mitigation_parameters": {},
        },
        "errors": {
            "transport_status": "none",
            "documented_status_codes": [],
            "error_content": "none",
            "error_schema_sha256": None,
            "retry_metadata": False,
        },
        "execution": {
            "batching": "none",
            "maximum_batch_size": 1,
            "maximum_concurrent_requests": 1,
            "cross_request_state": "none",
            "cross_request_state_ttl_seconds": None,
        },
        "access_paths": {
            "side_channels": [],
            "custom_side_channels": [],
            "admin_access": "none",
            "admin_capabilities": [],
            "local_access": "none",
            "local_capabilities": [],
        },
        "serialization": {
            "formats": ["categorical-symbol"],
            "media_types": ["application/vnd.mra.hidden-record-bin+json"],
            "encodings": ["utf-8"],
            "compression": [],
            "schema_sha256": sha256_bytes(canonical_json_bytes(wrapper["observation_ids"])),
            "endianness": "not_applicable",
        },
        "llm_protocol": None,
        "notes": (
            "Experimental closed hidden-record sampler. The caller supplies no X and cannot "
            "observe X, model weights, raw NLL, timing, identifiers, metadata, or another path. "
            "All underlying failures and timeouts become registered categorical symbols."
        ),
    })


def _profile(model_config: Mapping[str, Any]) -> ModelProfile:
    family = model_config["model_family"]
    modality = (
        DataModality.IMAGE if family == "cnn"
        else DataModality.TEXT if family == "llm_proxy_compact_transformer"
        else DataModality.TABULAR
    )
    return ModelProfile(
        task=ModelTask.CLASSIFICATION,
        input_modalities=(modality,),
        output_modalities=(DataModality.TABULAR,),
        training_paradigm=TrainingParadigm.SUPERVISED,
        component_model_families=(),
        generative=False,
        stateful=False,
    )


def _write_contract_scaffold(
    context: dict[str, Any],
    *,
    config: Mapping[str, Any],
    config_path: Path,
    config_sha256: str,
    registered_at: datetime,
    service: LocalAnalyzerService,
) -> None:
    directory: Path = context["directory"]
    oracle = context["oracle"]
    model = context["model"]
    variant = context["variant"]
    release_id = context["release_id"]

    artifact_identity = {
        "schema_version": "1.0",
        "identity_kind": "nondeployable_ephemeral_model_identity_envelope",
        "collector_model": oracle["collector_model"],
        "model_family": oracle["model_family"],
        "llm_proxy_only": oracle["llm_proxy_only"],
        "ephemeral_model_artifact_sha256": oracle["ephemeral_model_artifact_sha256"],
        "dataset_snapshot_sha256": oracle["dataset_snapshot_sha256"],
        "collector_seed": config["collector"]["seed"],
        "collector_epochs": config["collector"]["epochs"],
        "finite_population_sha256": oracle["finite_population_sha256"],
        "note": "Weights are hash-bound but intentionally not retained by this experiment.",
    }
    artifact_path = directory / "artifact-identity.json"
    write_json(artifact_path, artifact_identity)

    release = ReleaseContract(
        release_id=release_id,
        owner="MRA public-data experiment",
        recipient="closed hidden-record benchmark participant",
        purpose="Evaluate finite-channel ceiling coverage on a frozen public-data model population",
        model_family=model["model_family"],
        model_profile=_profile(model),
        protected_unit="record",
        artifact_path=artifact_path.name,
        artifact_sha256=sha256_file(artifact_path),
        interface=_interface(config),
        previous_release_ids=(),
        expires_at=None,
    )
    scope = PopulationScope(
        scope_id=f"benchmark-{model['collector_model']}-{variant['variant_id']}",
        name=f"Frozen target audit pools for {model['display_name']}",
        unit_kind=PopulationUnitKind.RECORD,
        universe_definition=(
            "The target model's finite member and nonmember audit pools produced by the "
            "registered public-data collector seed; no population extrapolation is permitted."
        ),
        inclusion_criteria=("appears in the collector target member or target nonmember audit pool",),
        exclusion_criteria=("reference-model calibration records",),
        jurisdictions=("public-benchmark-only",),
        reference_date=date(2026, 9, 3),
        valid_until=date(2099, 1, 1),
        population_snapshot_sha256=oracle["finite_population_sha256"],
        size=PopulationSize(
            basis=PopulationSizeBasis.EXACT_REGISTRY,
            lower_bound=sum(oracle["state_population_sizes"].values()),
            point_estimate=sum(oracle["state_population_sizes"].values()),
            upper_bound=sum(oracle["state_population_sizes"].values()),
            source="aggregate target-pool counts from the registered public-data collector",
            measured_at=registered_at,
        ),
        subgroup_dimensions=("sealed_membership_state",),
        data_steward="MRA experimental benchmark",
        notes="Finite empirical benchmark scope; not a deployment population.",
    )
    game = FiniteDecisionGame(
        game_id=config["decision_game"]["game_id"],
        states=(
            FiniteGameState(
                state_id="out",
                secret_value_definition="hidden sampled benchmark record is from target nonmembers",
            ),
            FiniteGameState(
                state_id="in",
                secret_value_definition="hidden sampled benchmark record is from target members",
            ),
        ),
        prior=tuple(RationalProbability(**value) for value in config["decision_game"]["prior"]),
        prior_basis="preregistered equal-prior randomized hidden-record benchmark game",
        authority="MRA experimental benchmark registration",
    )
    threat = ThreatContract(
        threat_id=f"membership-{model['collector_model']}-{variant['variant_id']}",
        kind=ThreatKind.MEMBERSHIP,
        mandatory=True,
        secret="whether the hidden benchmark record came from the target training-member pool",
        prior="exact equal prior over sealed OUT and IN states",
        side_information=(
            "public wrapper definition and categorical alphabet",
            "no target record, model artifact, raw loss, timing, identifiers, or arbitrary query access",
        ),
        success_metric="equal-prior exact membership-state guessing success",
        decision_metric="equal_prior_membership_success",
        metric_parameters={},
        finite_game=game,
        tolerance=float(config["decision_game"]["tolerance"]),
        tolerance_basis="absolute",
        harm_rationale="Experimental threshold for testing whether the computed ceiling becomes useful.",
        population_scope_id=scope.scope_id,
    )

    policy = PolicyBundle(
        policy_id=f"experimental-{model['collector_model']}-{variant['variant_id']}",
        policy_version="1.0.0",
        effective_from=registered_at,
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        rules=(PolicyRule(
            threat_id=threat.threat_id,
            kind=threat.kind,
            mandatory=True,
            decision_metric=threat.decision_metric,
            metric_parameters={},
            finite_game=game,
            tolerance=threat.tolerance,
            tolerance_basis="absolute",
            ceiling_attack_battery_mode=CeilingAttackBatteryMode.WAIVED,
            ceiling_attack_battery_waiver_reason=(
                "Experimental finite-population validation only; this waiver cannot authorize deployment."
            ),
        ),),
        analyzer_requirements=(AnalyzerRequirement(
            threat_id=threat.threat_id,
            analyzer="finite_channel_ceiling",
            minimum_service_version=service.descriptor.service_version,
            accepted_implementation_sha256s=(service.descriptor.implementation_sha256,),
            accepted_configuration_sha256s=(config_sha256,),
            required=True,
        ),),
        attack_battery_requirements=(),
        accepted_selection_policy_sha256s=(config_sha256,),
    )
    policy_path = directory / "experimental-policy.json"
    write_json(policy_path, policy.model_dump(mode="json"))
    policy_sha256 = sha256_file(policy_path)

    release_sha256 = sha256_bytes(canonical_json_bytes(release))
    interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))
    scope_sha256 = population_scope_sha256(scope)
    game_sha256 = decision_game_sha256(threat, scope)
    binding = EvidenceBindingContext(
        release_id=release.release_id,
        release_contract_sha256=release_sha256,
        policy_sha256=policy_sha256,
        artifact_sha256=release.artifact_sha256,
        interface_sha256=interface_sha256,
        population_scope_id=scope.scope_id,
        population_scope_sha256=scope_sha256,
        decision_game_sha256=game_sha256,
    )

    prior = FiniteStatePriorEvidence(
        threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,
        population_scope_sha256=scope_sha256,
        decision_game_sha256=game_sha256,
        state_ids=("out", "in"),
        prior=(RationalProbability(numerator=1, denominator=2),) * 2,
        prior_definition="preregistered equal prior for the hidden-record membership game",
        authority="MRA experimental benchmark registration",
    )
    prior_path = directory / "finite-prior.json"
    write_json(prior_path, prior.model_dump(mode="json"))

    mechanism_claims = (
        f"coupling:{CouplingModel.CONDITIONAL_INDEPENDENCE.value}",
        f"artifact:{release.artifact_sha256}",
        f"interface:{interface_sha256}",
        f"complete-transcript:{release.release_id}",
    )
    mechanism = {
        "schema_version": "1.0",
        "mechanism_id": config["finite_wrapper"]["wrapper_id"],
        "variant_id": variant["variant_id"],
        "complete_recipient_transcript": list(config["finite_wrapper"]["observation_ids"]),
        "closed_hidden_record_sampler": True,
        "query_budget": 1,
        "state_independent_erasure": variant["state_independent_erasure"],
        "supports": list(mechanism_claims),
        "experimental_only": True,
    }
    mechanism_path = directory / "mechanism-evidence.json"
    write_json(mechanism_path, mechanism)

    shutil.copyfile(config_path, directory / "experiment-config.json")
    plan = MultinomialSamplingPlan(
        plan_id=f"plan-{model['collector_model']}-{variant['variant_id']}",
        family_id=f"family-{model['collector_model']}-{variant['variant_id']}",
        portfolio_id=f"portfolio-{model['collector_model']}-{variant['variant_id']}",
        population_scope_id=scope.scope_id,
        threat_id=threat.threat_id,
        registered_at=registered_at,
        state_ids=("out", "in"),
        releases=(MultinomialSamplingPlanRelease(
            release_id=release.release_id,
            observation_ids=tuple(config["finite_wrapper"]["observation_ids"]),
        ),),
        minimum_trials_per_state=int(config["sampling"]["trials_per_state"]),
        selection_scope=config["sampling"]["family_selection_scope"],
        audit_sample_definition=(
            "independent with-replacement draws from each complete finite target pool, "
            "using the preregistered per-model, per-variant, per-state seeds "
            f"out={model['sample_seeds'][variant['variant_id']]['out']} and "
            f"in={model['sample_seeds'][variant['variant_id']]['in']}"
        ),
        binding_context=binding,
    )
    plan_path = directory / "sampling-plan.json"
    write_json(plan_path, plan.model_dump(mode="json"))
    context.update({
        "release": release,
        "scope": scope,
        "threat": threat,
        "policy": policy,
        "policy_path": policy_path,
        "policy_sha256": policy_sha256,
        "binding": binding,
        "prior": prior,
        "prior_path": prior_path,
        "mechanism_path": mechanism_path,
        "mechanism_claims": mechanism_claims,
        "plan": plan,
        "plan_path": plan_path,
    })


def _execute_contract_path(
    context: dict[str, Any],
    *,
    config: Mapping[str, Any],
    config_sha256: str,
    budget: AssuranceErrorBudget,
    service: LocalAnalyzerService,
) -> dict[str, Any]:
    directory: Path = context["directory"]
    model = context["model"]
    variant = context["variant"]
    oracle = context["oracle"]
    release: ReleaseContract = context["release"]
    threat: ThreatContract = context["threat"]
    scope: PopulationScope = context["scope"]
    plan: MultinomialSamplingPlan = context["plan"]
    trials = int(config["sampling"]["trials_per_state"])
    observation_ids = tuple(config["finite_wrapper"]["observation_ids"])
    erased_index = observation_ids.index("state_independent_erasure")
    erasure = rational(variant["state_independent_erasure"])
    state_seeds = {
        state: int(model["sample_seeds"][variant["variant_id"]][state])
        for state in ("out", "in")
    }

    budget_path = directory / "assurance-error-budget.json"
    write_json(budget_path, budget.model_dump(mode="json"))
    sampling_started = datetime.now(timezone.utc)
    sampled_rows = {
        state: sample_state_counts(
            oracle["state_counts"][state],
            trials=trials,
            seed=state_seeds[state],
            erasure=erasure,
            erased_index=erased_index,
        )
        for state in ("out", "in")
    }
    replayed_rows = {
        state: sample_state_counts(
            oracle["state_counts"][state],
            trials=trials,
            seed=state_seeds[state],
            erasure=erasure,
            erased_index=erased_index,
        )
        for state in ("out", "in")
    }
    if replayed_rows != sampled_rows:
        raise ExperimentValidationError("primary state seeds did not replay exact counts")
    sampling_ended = datetime.now(timezone.utc)
    sample_binding = {
        "finite_population_sha256": oracle["finite_population_sha256"],
        "variant_id": variant["variant_id"],
        "state_independent_erasure": variant["state_independent_erasure"],
        "trials_per_state": trials,
        "state_seeds": state_seeds,
        "sampler": config["sampling"]["model"],
    }
    sample_binding_sha256 = sha256_bytes(canonical_json_bytes(sample_binding))
    count_file = MultinomialCountsFile(
        count_file_id=f"counts-{model['collector_model']}-{variant['variant_id']}",
        sampling_plan_id=plan.plan_id,
        sampling_plan_sha256=sha256_file(context["plan_path"]),
        portfolio_id=plan.portfolio_id,
        population_scope_id=plan.population_scope_id,
        threat_id=plan.threat_id,
        family_id=plan.family_id,
        sampling_started_at=sampling_started,
        sampling_ended_at=sampling_ended,
        audit_sample_sha256=sample_binding_sha256,
        sampling_protocol=(
            "Python random.Random with independent preregistered state seeds; integer-uniform "
            "with-replacement finite-population draw followed by exact rational, "
            f"state-independent erasure; out_seed={state_seeds['out']}; "
            f"in_seed={state_seeds['in']}; trials_per_state={trials}"
        ),
        state_ids=("out", "in"),
        releases=(MultinomialReleaseCounts(
            release_id=release.release_id,
            observation_ids=observation_ids,
            state_rows=tuple(
                MultinomialStateCounts(state_id=state, counts=sampled_rows[state])
                for state in ("out", "in")
            ),
        ),),
        binding_context=context["binding"],
    )
    counts_path = directory / "sampled-counts.json"
    write_json(counts_path, count_file.model_dump(mode="json"))
    request = MultinomialEvidenceRequest(
        generation_id=f"generation-{model['collector_model']}-{variant['variant_id']}",
        allocation_id=f"allocation-{model['collector_model']}-{variant['variant_id']}",
        sampling_plan_reference=SourceFileReference(
            source_id=plan.plan_id,
            source_path=context["plan_path"].name,
            source_sha256=sha256_file(context["plan_path"]),
        ),
        counts_reference=SourceFileReference(
            source_id=count_file.count_file_id,
            source_path=counts_path.name,
            source_sha256=sha256_file(counts_path),
        ),
        budget_reference=SourceFileReference(
            source_id=budget.budget_id,
            source_path=budget_path.name,
            source_sha256=sha256_file(budget_path),
        ),
        family_pre_registered=True,
        all_cells_reported=True,
        selection_process_covered=True,
        assurance_ledger_complete=True,
        selection_scope=plan.selection_scope,
    )
    evidence = generate_simultaneous_multinomial_evidence(request, directory)
    evidence_path = directory / "simultaneous-evidence.json"
    write_json(evidence_path, evidence.model_dump(mode="json"))

    game_sha256 = decision_game_sha256(threat, scope)
    rational_prior = (RationalProbability(numerator=1, denominator=2),) * 2
    specification = IncompletePortfolioSpecification(
        portfolio_id=plan.portfolio_id,
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        threat_id=threat.threat_id,
        decision_game_sha256=game_sha256,
        prior=(0.5, 0.5),
        rational_prior=rational_prior,
        decision_problem=exact_guess_problem(("out", "in"), problem_id=game_sha256),
        coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
        prior_evidence=EvidenceReference(
            evidence_id=f"prior-{model['collector_model']}-{variant['variant_id']}",
            source_path=context["prior_path"].name,
            source_sha256=sha256_file(context["prior_path"]),
            supports=(
                "prior",
                f"decision-game:{game_sha256}",
                f"finite-prior:{finite_prior_contract_sha256(('out', 'in'), rational_prior)}",
            ),
        ),
        mechanism_assumptions=(
            "one closed hidden-record query produces the complete categorical transcript",
            "state-conditioned sampling is IID with replacement from each frozen finite pool",
            "erasure, if enabled, is independent of the hidden state and underlying bin",
        ),
        mechanism_evidence=(EvidenceReference(
            evidence_id=f"mechanism-{model['collector_model']}-{variant['variant_id']}",
            source_path=context["mechanism_path"].name,
            source_sha256=sha256_file(context["mechanism_path"]),
            supports=context["mechanism_claims"],
        ),),
    )
    problem = compile_multinomial_portfolio_problem(
        evidence,
        specification,
        evidence_source_path=evidence_path.name,
        evidence_source_sha256=sha256_file(evidence_path),
    )
    analytic = solve_analytic_portfolio(
        problem,
        method="envelope",
        certificate_id=f"certificate-{model['collector_model']}-{variant['variant_id']}",
    )
    observed_at = max(datetime.now(timezone.utc), sampling_ended + timedelta(microseconds=1))
    evidence_context = EvidenceContext(
        release_id=release.release_id,
        release_contract_sha256=sha256_bytes(canonical_json_bytes(release)),
        policy_sha256=context["policy_sha256"],
        artifact_sha256=release.artifact_sha256,
        interface_sha256=sha256_bytes(canonical_json_bytes(release.interface)),
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        decision_game_sha256=game_sha256,
        observed_at=observed_at,
    )
    placeholder = AnalyzerProvenance(
        tool="model-backed-finite-channel-experiment",
        tool_version="1.0",
        producer={
            "service_id": service.descriptor.service_id,
            "service_version": service.descriptor.service_version,
            "implementation_sha256": service.descriptor.implementation_sha256,
            "configuration_sha256": config_sha256,
        },
        configuration_path="experiment-config.json",
        source_path="finite-channel-input.json",
        source_sha256="0" * 64,
        bound_fields=("analyzer",),
    )
    value = FiniteChannelCeilingInput(
        threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,
        analytic_evidence=analytic,
        observed_interface_sha256=evidence_context.interface_sha256,
        observed_artifact_sha256=release.artifact_sha256,
        interface_observation_definition=(
            "complete one-query categorical transcript of the closed hidden-record sampler, "
            "including negative, nonfinite, wrapper-error, timeout, and erasure outcomes"
        ),
        release_enforced_finite_alphabet=True,
        complete_interface_coverage=True,
        recipient_realizable=True,
        bounded_transcript_complete=True,
        state_trials=(trials, trials),
        evidence_context=evidence_context,
        provenance=placeholder,
    )
    input_payload = value.model_dump(mode="json", exclude={"provenance"}, exclude_none=False)
    input_path = directory / "finite-channel-input.json"
    write_json(input_path, input_payload)
    value = value.model_copy(update={
        "provenance": placeholder.model_copy(update={
            "source_sha256": sha256_file(input_path),
            "bound_fields": tuple(input_payload),
        })
    })
    submission_path = directory / "finite-channel-submission.json"
    write_json(submission_path, value.model_dump(mode="json"))

    AssuranceEngine._verify_finite_channel_sources(value, directory)
    records = service.analyze(release, threat, value)
    floors = [record for record in records if record.evidence_class is EvidenceClass.FLOOR]
    ceilings = [record for record in records if record.evidence_class is EvidenceClass.CEILING]
    if len(floors) != 1 or len(ceilings) != 1:
        raise RuntimeError("eligible replay did not emit exactly one floor and ceiling")
    floor, ceiling = floors[0], ceilings[0]
    records_path = directory / "analyzer-evidence.json"
    write_json(records_path, [record.model_dump(mode="json") for record in records])

    assessment_request = AssessmentRequest(
        policy=PolicyReference(
            policy_id=context["policy"].policy_id,
            policy_version=context["policy"].policy_version,
            policy_path=context["policy_path"].name,
            policy_sha256=context["policy_sha256"],
        ),
        release=release,
        population_scopes=(scope,),
        threats=(threat,),
        analyzer_inputs=(value,),
    )
    report = AssuranceEngine(
        service_registry=AnalyzerServiceRegistry((service,))
    ).assess(assessment_request, directory)
    assessment_path = directory / "experimental-assessment-report.json"
    write_json(assessment_path, report.model_dump(mode="json"))
    context["submission"] = value

    true_risk = exact_channel_risk(
        oracle["state_counts"],
        erasure=erasure,
        erased_index=erased_index,
    )
    assert floor.exact_lower is not None and ceiling.exact_upper is not None
    exact_floor = floor.exact_lower.as_fraction()
    exact_ceiling = ceiling.exact_upper.as_fraction()
    return {
        "collector_model": model["collector_model"],
        "model_family": model["model_family"],
        "display_name": model["display_name"],
        "llm_proxy_only": bool(model.get("llm_proxy_only", False)),
        "variant_id": variant["variant_id"],
        "state_independent_erasure": variant["state_independent_erasure"],
        "sample_seeds": model["sample_seeds"][variant["variant_id"]],
        "sample_binding_sha256": sample_binding_sha256,
        "sampling_seed_replayed": replayed_rows == sampled_rows,
        "trials_per_state": trials,
        "finite_population_sha256": oracle["finite_population_sha256"],
        "oracle_exact_bayes_risk": rational_payload(true_risk),
        "oracle_exact_bayes_risk_decimal": float(true_risk),
        "sampled_counts": {state: list(row) for state, row in sampled_rows.items()},
        "production_interval": {
            "exact_floor": rational_payload(exact_floor),
            "exact_ceiling": rational_payload(exact_ceiling),
            "floor": floor.lower,
            "ceiling": ceiling.upper,
            "width": float(exact_ceiling - exact_floor),
            "covers_oracle": exact_floor <= true_risk <= exact_ceiling,
            "coverage_confidence": problem.coverage_confidence,
            "endpoint_validation": "source_replayed_and_directed_tail_validated",
        },
        "experimental_engine_verdict": report.overall_verdict.value,
        "engine_chain_completed": True,
        "release_authorization": "none",
        "artifact_directory": directory.name,
    }


def _run_negative_controls(
    context: Mapping[str, Any],
    service: LocalAnalyzerService,
) -> list[dict[str, Any]]:
    """Execute the four preregistered fail-closed controls on one replay."""

    directory: Path = context["directory"]
    value: FiniteChannelCeilingInput = context["submission"]
    release: ReleaseContract = context["release"]
    threat: ThreatContract = context["threat"]
    visible_channels = release.interface.output_channels.model_copy(update={
        "parameters": True,
        "downloadable_files": ("artifact-identity.json",),
    })
    visible_interface = release.interface.model_copy(update={
        "access": "full_artifact",
        "outputs": (*release.interface.outputs, "model artifact and weights"),
        "output_channels": visible_channels,
    })
    visible_release = release.model_copy(update={"interface": visible_interface})
    screen = service.analyze(visible_release, threat, value)
    controls = [{
        "control_id": "visible_candidate_or_model_must_be_ineligible",
        "executed": True,
        "passed": (
            len(screen) == 1
            and screen[0].evidence_class is EvidenceClass.SCREEN
            and not screen[0].can_clear
            and screen[0].details.get("release_gate") == "hold"
        ),
        "mechanism": (
            "mutate the governed interface to full artifact/model-weight visibility and "
            "require its changed interface binding to produce a non-clearing HOLD screen"
        ),
    }]

    def with_evidence_hash(
        candidate: FiniteChannelCeilingInput,
        evidence_sha256: str,
        certificate_id: str,
    ) -> FiniteChannelCeilingInput:
        problem = candidate.analytic_evidence.problem
        marginal = problem.releases[0]
        reference = marginal.evidence.model_copy(update={
            "source_sha256": evidence_sha256,
        })
        changed_problem = problem.model_copy(update={
            "releases": (marginal.model_copy(update={"evidence": reference}),),
        })
        return candidate.model_copy(update={
            "analytic_evidence": solve_analytic_portfolio(
                changed_problem,
                method="envelope",
                certificate_id=certificate_id,
            ),
        })

    def tamper_counts(copied: Path) -> FiniteChannelCeilingInput:
        counts_path = copied / "sampled-counts.json"
        counts = load_json_object(counts_path)
        row = counts["releases"][0]["state_rows"][0]["counts"]
        donor = next(index for index, count in enumerate(row) if count > 0)
        receiver = next(index for index in range(len(row)) if index != donor)
        row[donor] -= 1
        row[receiver] += 1
        write_json(counts_path, counts)
        evidence_path = copied / "simultaneous-evidence.json"
        evidence = load_json_object(evidence_path)
        evidence["request"]["counts_reference"]["source_sha256"] = sha256_file(counts_path)
        write_json(evidence_path, evidence)
        return with_evidence_hash(
            value,
            sha256_file(evidence_path),
            "negative-control-tampered-counts",
        )

    def change_prior(copied: Path) -> FiniteChannelCeilingInput:
        prior_path = copied / "finite-prior.json"
        prior = load_json_object(prior_path)
        prior["prior"] = [
            {"numerator": 3, "denominator": 4},
            {"numerator": 1, "denominator": 4},
        ]
        write_json(prior_path, prior)
        problem = value.analytic_evidence.problem
        changed_problem = problem.model_copy(update={
            "prior_evidence": problem.prior_evidence.model_copy(update={
                "source_sha256": sha256_file(prior_path),
            }),
        })
        return value.model_copy(update={
            "analytic_evidence": solve_analytic_portfolio(
                changed_problem,
                method="envelope",
                certificate_id="negative-control-changed-prior-source",
            ),
        })

    def remove_observation(copied: Path) -> FiniteChannelCeilingInput:
        plan_path = copied / "sampling-plan.json"
        plan = load_json_object(plan_path)
        plan["releases"][0]["observation_ids"] = [
            item for item in plan["releases"][0]["observation_ids"]
            if item != "wrapper_timeout"
        ]
        write_json(plan_path, plan)
        plan_sha256 = sha256_file(plan_path)

        counts_path = copied / "sampled-counts.json"
        counts = load_json_object(counts_path)
        counts["sampling_plan_sha256"] = plan_sha256
        write_json(counts_path, counts)
        budget_path = copied / "assurance-error-budget.json"
        budget = load_json_object(budget_path)
        allocation_id = (
            f"allocation-{context['model']['collector_model']}-"
            f"{context['variant']['variant_id']}"
        )
        for allocation in budget["allocations"]:
            if allocation["allocation_id"] == allocation_id:
                allocation["sampling_plan_sha256"] = plan_sha256
        write_json(budget_path, budget)

        evidence_path = copied / "simultaneous-evidence.json"
        evidence = load_json_object(evidence_path)
        request = evidence["request"]
        request["sampling_plan_reference"]["source_sha256"] = plan_sha256
        request["counts_reference"]["source_sha256"] = sha256_file(counts_path)
        request["budget_reference"]["source_sha256"] = sha256_file(budget_path)
        write_json(evidence_path, evidence)
        return with_evidence_hash(
            value,
            sha256_file(evidence_path),
            "negative-control-missing-observation",
        )

    mutations = (
        ("tampered_counts_must_fail_source_replay", tamper_counts),
        ("changed_prior_must_fail_binding", change_prior),
        ("missing_observation_symbol_must_fail_plan_replay", remove_observation),
    )
    for control_id, mutate in mutations:
        with tempfile.TemporaryDirectory(prefix="mra-finite-negative-control-") as temporary:
            copied = Path(temporary) / "replay"
            shutil.copytree(directory, copied)
            changed_value = mutate(copied)
            rejected = False
            failure_type: str | None = None
            try:
                AssuranceEngine._verify_finite_channel_sources(changed_value, copied)
            except (ValueError, IntegrityError) as exc:
                rejected = True
                failure_type = type(exc).__name__
            controls.append({
                "control_id": control_id,
                "executed": True,
                "passed": rejected,
                "mechanism": (
                    "mutate semantic content, recompute its immediate file digest/reference, "
                    "and require deeper source or binding replay rejection"
                ),
                "observed_failure_type": failure_type,
            })
    return controls


def _contains_forbidden_retained_key(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_RETAINED_KEYS.intersection(value)) or any(
            _contains_forbidden_retained_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_retained_key(item) for item in value)
    return False


def _aggregate_outputs_are_raw_free(output_dir: Path) -> bool:
    for path in output_dir.rglob("*.json"):
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExperimentValidationError(
                f"cannot scan retained JSON {path}: {exc}"
            ) from exc
        if _contains_forbidden_retained_key(payload):
            return False
    return True


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ExperimentValidationError("cannot summarize an empty repeat family")
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _run_repeated_validation(
    contexts: Sequence[Mapping[str, Any]],
    *,
    config: Mapping[str, Any],
    service: LocalAnalyzerService,
) -> list[dict[str, Any]]:
    """Execute and retain every preregistered fixed-channel analyzer replay."""

    repeated = config["repeated_validation"]
    replicates = int(repeated["replicates_per_model_variant"])
    master_seed = int(repeated["master_seed"])
    trials = int(config["sampling"]["trials_per_state"])
    allocation_alpha = rational(config["sampling"]["per_model_variant_alpha"])
    tolerance = Fraction(Decimal(str(config["decision_game"]["tolerance"])))
    erased_index = tuple(config["finite_wrapper"]["observation_ids"]).index(
        "state_independent_erasure"
    )
    meta_family_alpha = rational(repeated["meta_family_alpha"])
    # The registered meta family contains both a lower CLEAR-rate bound and an
    # upper undercoverage-rate bound for each of the six model/variant families.
    # Spend the single family alpha across all twelve one-sided endpoints.
    simultaneous_bound_count = 2 * len(contexts)
    simultaneous_meta_confidence = bonferroni_per_bound_confidence(
        1.0 - float(meta_family_alpha),
        simultaneous_bound_count,
    )
    summaries: list[dict[str, Any]] = []

    for context in contexts:
        model = context["model"]
        variant = context["variant"]
        oracle = context["oracle"]
        erasure = rational(variant["state_independent_erasure"])
        true_risk = exact_channel_risk(
            oracle["state_counts"],
            erasure=erasure,
            erased_index=erased_index,
        )
        records = []
        for replicate in range(replicates):
            seeds = {
                state: _derived_repeat_seed(
                    master_seed,
                    model["collector_model"],
                    variant["variant_id"],
                    replicate,
                    state,
                )
                for state in ("out", "in")
            }
            counts = {
                state: sample_state_counts(
                    oracle["state_counts"][state],
                    trials=trials,
                    seed=seeds[state],
                    erasure=erasure,
                    erased_index=erased_index,
                )
                for state in ("out", "in")
            }
            row = _repeat_analyzer_replay(
                context,
                counts=counts,
                replicate=replicate,
                service=service,
                allocation_alpha=allocation_alpha,
                true_risk=true_risk,
                tolerance=tolerance,
            )
            row["derived_state_seeds"] = seeds
            records.append(row)

        repeated_path = context["directory"] / "repeated-analyzer-replays.json"
        write_json(repeated_path, {
            "schema_version": "1.0",
            "experimental_only": True,
            "benchmark_population_conditional": True,
            "collector_model": model["collector_model"],
            "variant_id": variant["variant_id"],
            "replicates": replicates,
            "trials_per_state": trials,
            "true_exact_oracle_risk": rational_payload(true_risk),
            "rows": records,
            "raw_model_scores_retained": False,
        })
        undercoverage = sum(not value["covers_oracle"] for value in records)
        clear_count = sum(value["decision"] == "CLEAR" for value in records)
        widths = [float(value["interval_width"]) for value in records]
        excesses = [float(value["ceiling_excess_over_oracle"]) for value in records]
        ceilings = [float(value["ceiling"]) for value in records]
        undercoverage_upper = clopper_pearson_upper(
            undercoverage,
            replicates,
            simultaneous_meta_confidence,
        )
        clear_rate_lower = clopper_pearson_lower(
            clear_count,
            replicates,
            simultaneous_meta_confidence,
        )
        summaries.append({
            "collector_model": model["collector_model"],
            "model_family": model["model_family"],
            "variant_id": variant["variant_id"],
            "replicates": replicates,
            "trials_per_state": trials,
            "true_exact_oracle_risk": rational_payload(true_risk),
            "undercoverage_count": undercoverage,
            "undercoverage_rate": undercoverage / replicates,
            "simultaneous_clopper_pearson_undercoverage_upper": undercoverage_upper,
            "simultaneous_meta_confidence": simultaneous_meta_confidence,
            "meta_simultaneous_bound_count": simultaneous_bound_count,
            "meta_multiplicity_method": (
                "bonferroni_across_twelve_one_sided_bounds:"
                "six_clear_rate_lowers_and_six_undercoverage_uppers"
            ),
            "clear_count": clear_count,
            "clear_rate": clear_count / replicates,
            "simultaneous_clopper_pearson_clear_rate_lower": clear_rate_lower,
            "mean_ceiling": statistics.fmean(ceilings),
            "p95_ceiling": _percentile(ceilings, 0.95),
            "mean_interval_width": statistics.fmean(widths),
            "p95_interval_width": _percentile(widths, 0.95),
            "maximum_interval_width": max(widths),
            "mean_ceiling_excess_over_oracle": statistics.fmean(excesses),
            "p95_ceiling_excess_over_oracle": _percentile(excesses, 0.95),
            "maximum_ceiling_excess_over_oracle": max(excesses),
            "every_production_analyzer_replay_completed": all(
                value["production_analyzer_replayed"] for value in records
            ),
            "retained_rows_path": repeated_path.name,
            "retained_rows_sha256": sha256_file(repeated_path),
        })
    return summaries


def run_experiment(
    config: Mapping[str, Any],
    collector_report: Mapping[str, Any],
    *,
    output_dir: Path,
    config_path: Path,
    collector_input_bytes: bytes,
    verify_files: bool = True,
) -> dict[str, Any]:
    """Compile model outputs and execute every registered production replay."""

    if not isinstance(collector_input_bytes, bytes):
        raise ExperimentValidationError("collector input must be supplied as exact bytes")
    file_config = load_json_object(config_path)
    _require(
        canonical_json_bytes(file_config) == canonical_json_bytes(config),
        "in-memory config does not match the registered config file",
    )
    parsed_collector = parse_json_object_bytes(
        collector_input_bytes,
        source="collector_input_bytes",
    )
    _require(
        canonical_json_bytes(parsed_collector) == canonical_json_bytes(collector_report),
        "in-memory collector report does not match the supplied collector bytes",
    )
    collector_input_sha256 = sha256_bytes(collector_input_bytes)
    validate_config(config, verify_files=verify_files)
    _validate_collector_report(collector_report, config)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ExperimentValidationError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    config_sha256 = sha256_file(config_path)
    registered_at = datetime.fromisoformat(str(config["registered_at"]).replace("Z", "+00:00"))
    if registered_at >= datetime.now(timezone.utc):
        raise ExperimentValidationError("configuration registration must predate outcome collection")
    service = LocalAnalyzerService(FiniteChannelCeilingAnalyzer())

    collector_models = {value["model"]: value for value in collector_report["models"]}
    datasets = collector_report["datasets"]
    oracles = {
        model["collector_model"]: compile_oracle(
            collector_models[model["collector_model"]],
            model,
            config,
            datasets[model["dataset_key"]],
        )
        for model in config["models"]
    }
    wrapper_conformance = [
        {
            "collector_model": model["collector_model"],
            "variant_id": variant["variant_id"],
            **validate_closed_hidden_record_wrapper(
                config["finite_wrapper"],
                aggregate_population=oracles[model["collector_model"]]["state_counts"],
                state_independent_erasure=variant["state_independent_erasure"],
            ),
        }
        for model in config["models"]
        for variant in config["finite_wrapper"]["variants"]
    ]
    write_json(output_dir / "wrapper-conformance.json", {
        "schema_version": "1.0",
        "experimental_only": True,
        "results": wrapper_conformance,
    })
    write_json(output_dir / "finite-population-oracles.json", {
        "schema_version": "1.0",
        "experimental_only": True,
        "benchmark_population_conditional": True,
        "models": list(oracles.values()),
        "raw_scores_retained": False,
    })

    contexts: list[dict[str, Any]] = []
    for model in config["models"]:
        for variant in config["finite_wrapper"]["variants"]:
            name = f"{model['collector_model']}--{variant['variant_id']}"
            context = {
                "model": model,
                "variant": variant,
                "oracle": oracles[model["collector_model"]],
                "directory": output_dir / name,
                "release_id": f"model-backed-{model['collector_model']}-{variant['variant_id']}",
            }
            context["directory"].mkdir(parents=True, exist_ok=False)
            _write_contract_scaffold(
                context,
                config=config,
                config_path=config_path,
                config_sha256=config_sha256,
                registered_at=registered_at,
                service=service,
            )
            contexts.append(context)

    allocation_alpha = float(rational(config["sampling"]["per_model_variant_alpha"]))
    budget = AssuranceErrorBudget(
        budget_id="model-backed-finite-channel-assurance-budget",
        authority="MRA experimental benchmark registration; no release authority",
        committed_at=registered_at + timedelta(seconds=1),
        period_start=registered_at.date(),
        period_end=date(2099, 1, 1),
        total_alpha=float(rational(config["sampling"]["assurance_alpha"])),
        allocations=tuple(
            ErrorBudgetAllocation(
                allocation_id=f"allocation-{context['model']['collector_model']}-{context['variant']['variant_id']}",
                generation_id=f"generation-{context['model']['collector_model']}-{context['variant']['variant_id']}",
                family_id=context["plan"].family_id,
                portfolio_id=context["plan"].portfolio_id,
                population_scope_id=context["scope"].scope_id,
                threat_id=context["threat"].threat_id,
                sampling_plan_sha256=sha256_file(context["plan_path"]),
                alpha=allocation_alpha,
                binding_context=context["binding"],
            )
            for context in contexts
        ),
    )
    results = [
        _execute_contract_path(
            context,
            config=config,
            config_sha256=config_sha256,
            budget=budget,
            service=service,
        )
        for context in contexts
    ]
    repeated_summaries = _run_repeated_validation(
        contexts,
        config=config,
        service=service,
    )
    negative_controls = _run_negative_controls(contexts[0], service)
    all_oracles_covered = all(
        value["production_interval"]["covers_oracle"] for value in results
    )
    primary_source_and_engine_replays_complete = all(
        value["engine_chain_completed"] and value["sampling_seed_replayed"]
        for value in results
    )
    repeated_analyzer_replays_complete = all(
        value["every_production_analyzer_replay_completed"]
        for value in repeated_summaries
    )
    all_replays_complete = (
        len(results) == 6
        and len(repeated_summaries) == 6
        and primary_source_and_engine_replays_complete
        and repeated_analyzer_replays_complete
    )
    all_negative_controls_pass = (
        len(negative_controls) == len(EXPECTED_NEGATIVE_CONTROLS)
        and tuple(value["control_id"] for value in negative_controls)
        == EXPECTED_NEGATIVE_CONTROLS
        and all(value["executed"] and value["passed"] for value in negative_controls)
    )
    no_raw_scores_retained = _aggregate_outputs_are_raw_free(output_dir)
    result_by_key = {
        (value["collector_model"], value["variant_id"]): value
        for value in results
    }
    erasure_comparisons = []
    for model in EXPECTED_MODELS:
        raw = result_by_key[(model, "raw_bins")]
        erased = result_by_key[(model, "erasure_0p9")]
        raw_risk = rational(raw["oracle_exact_bayes_risk"])
        erased_risk = rational(erased["oracle_exact_bayes_risk"])
        raw_ceiling = rational(raw["production_interval"]["exact_ceiling"])
        erased_ceiling = rational(erased["production_interval"]["exact_ceiling"])
        erasure_comparisons.append({
            "collector_model": model,
            "raw_oracle_risk": raw["oracle_exact_bayes_risk"],
            "erased_oracle_risk": erased["oracle_exact_bayes_risk"],
            "oracle_risk_nonincreasing": erased_risk <= raw_risk,
            "raw_production_ceiling": raw["production_interval"]["exact_ceiling"],
            "erased_production_ceiling": erased["production_interval"]["exact_ceiling"],
            "observed_production_ceiling_nonincreasing": erased_ceiling <= raw_ceiling,
            "production_ceiling_comparison_role": "descriptive_only_not_an_acceptance_criterion",
        })
    erasure_never_increases_oracle = all(
        value["oracle_risk_nonincreasing"] for value in erasure_comparisons
    )
    all_one_shot_clear = len(results) == 6 and all(
        value["experimental_engine_verdict"] == Verdict.CLEAR.value
        for value in results
    )
    minimum_clear_rate_lower = float(
        config["repeated_validation"]["minimum_simultaneous_clear_rate_lower"]
    )
    repeated_clear_rate_lowers_pass = len(repeated_summaries) == 6 and all(
        value["simultaneous_clopper_pearson_clear_rate_lower"]
        >= minimum_clear_rate_lower
        for value in repeated_summaries
    )
    maximum_undercoverage = float(
        config["repeated_validation"]["maximum_simultaneous_undercoverage_upper"]
    )
    repeated_undercoverage_pass = len(repeated_summaries) == 6 and all(
        value["simultaneous_clopper_pearson_undercoverage_upper"]
        <= maximum_undercoverage
        for value in repeated_summaries
    )
    all_wrapper_conformance_pass = len(wrapper_conformance) == 6 and all(
        value["conformant"] for value in wrapper_conformance
    )
    acceptance = {
        "all_six_oracle_risks_covered": all_oracles_covered and len(results) == 6,
        "all_source_and_engine_replays_complete": all_replays_complete,
        "all_four_negative_controls_pass": all_negative_controls_pass,
        "no_raw_scores_retained": no_raw_scores_retained,
        "erasure_never_increases_exact_oracle_risk": erasure_never_increases_oracle,
        "all_six_one_shot_engine_decisions_clear": all_one_shot_clear,
        "all_six_simultaneous_clear_rate_lowers_meet_minimum": repeated_clear_rate_lowers_pass,
        "all_six_simultaneous_undercoverage_bounds_meet_maximum": repeated_undercoverage_pass,
        "all_executable_wrapper_conformance_checks_pass": all_wrapper_conformance_pass,
    }
    acceptance_passed = tuple(acceptance) == EXPECTED_ACCEPTANCE_CRITERIA and all(
        acceptance.values()
    )
    report = {
        "schema_version": "1.0",
        "experiment_id": config["experiment_id"],
        "config_sha256": config_sha256,
        "collector": {
            "experiment_id": collector_report["experiment_id"],
            "collector_input_sha256": collector_input_sha256,
            "seed": collector_report["seed"],
            "epochs": collector_report["epochs"],
            "rag_plan_id": collector_report["orchestration"]["plan_id"],
            "rag_plan_sha256": collector_report["orchestration"]["plan_sha256"],
            "software": dict(collector_report["software"]),
            "datasets": {
                key: {"processed_snapshot_sha256": value["processed_snapshot_sha256"]}
                for key, value in datasets.items()
                if key in {model["dataset_key"] for model in config["models"]}
            },
            "ephemeral_model_artifact_sha256s": {
                value["model"]: value["ephemeral_model_artifact_sha256"]
                for value in collector_report["models"]
                if value["model"] in EXPECTED_MODELS
            },
            "raw_collector_storage": "temporary_directory_deleted_after_aggregate_compilation",
            "raw_scores_retained": False,
        },
        "authority": dict(config["authority"]),
        "claim_scope": (
            "simultaneous finite-sample intervals for each frozen, one-query closed hidden-record "
            "wrapper channel, conditional on the newly trained model's finite target audit pools"
        ),
        "excluded_claims": [
            "privacy of an ordinary model prediction or interactive LLM interface",
            "generalization beyond the frozen benchmark target pools",
            "privacy of another training seed, model artifact, dataset snapshot, or wrapper",
            "persistence or independent replay of the ephemeral trained model weights",
            "operating-system or real serving-endpoint enforcement of the closed wrapper",
            "release authorization",
        ],
        "results": results,
        "repeated_validation": {
            "replicates_per_model_variant": config["repeated_validation"]["replicates_per_model_variant"],
            "full_source_and_engine_replay_scope": (
                "one independent primary draw per model/variant family (6 total)"
            ),
            "production_analyzer_replay_scope": (
                "200 independent repeats per model/variant family (1,200 total)"
            ),
            "summaries": repeated_summaries,
        },
        "wrapper_conformance": {
            "all_conformant": all_wrapper_conformance_pass,
            "results": wrapper_conformance,
            "acceptance_role": "supporting executable evidence; endpoint/OS enforcement remains excluded",
        },
        "erasure_comparisons": erasure_comparisons,
        "negative_controls": negative_controls,
        "acceptance": {
            "criteria": acceptance,
            "passed": acceptance_passed,
        },
        "checks": {
            "all_oracles_covered": all_oracles_covered,
            "all_source_and_engine_replays_complete": all_replays_complete,
            "full_source_and_engine_replays": {
                "completed": sum(
                    value["engine_chain_completed"] and value["sampling_seed_replayed"]
                    for value in results
                ),
                "expected": 6,
                "scope": "one primary replay per model/variant family",
            },
            "production_analyzer_replays": {
                "completed": sum(
                    int(value["replicates"])
                    if value["every_production_analyzer_replay_completed"] else 0
                    for value in repeated_summaries
                ),
                "expected": 1200,
                "scope": "200 repeats per model/variant family; analyzer-level",
            },
            "raw_scores_retained": not no_raw_scores_retained,
            "registered_model_count": len(config["models"]),
            "registered_family_count": len(results),
        },
        "elapsed_seconds": time.perf_counter() - started,
        "decision": "no_release_authorization",
    }
    write_json(output_dir / "model-backed-finite-channel-report.json", report)
    return report


def collect_public_outputs(
    config: Mapping[str, Any],
    cache_dir: Path,
) -> tuple[dict[str, Any], bytes]:
    """Run the pinned collector in disposable storage, returning payload and bytes."""

    with tempfile.TemporaryDirectory(prefix="mra-public-model-collector-") as temporary:
        output = Path(temporary)
        command = [
            sys.executable,
            str(ROOT / config["collector"]["runner_path"]),
            "--output-dir", str(output),
            "--cache-dir", str(cache_dir),
            "--seed", str(config["collector"]["seed"]),
            "--epochs", str(config["collector"]["epochs"]),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        report_path = output / "privacy-audit-report.json"
        report_bytes = report_path.read_bytes()
        return (
            parse_json_object_bytes(report_bytes, source=str(report_path)),
            report_bytes,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Model-backed finite-channel ceiling experiment (experimental, non-authorizing)"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    config = load_json_object(args.config)
    validate_config(config, verify_files=True)
    collector, collector_input_bytes = collect_public_outputs(config, args.cache_dir)
    report = run_experiment(
        config,
        collector,
        output_dir=args.output_dir,
        config_path=args.config,
        collector_input_bytes=collector_input_bytes,
    )
    print(json.dumps({
        "output": str(args.output_dir / "model-backed-finite-channel-report.json"),
        "families": len(report["results"]),
        "oracle_coverage": report["checks"]["all_oracles_covered"],
        "engine_verdicts": {
            f"{value['collector_model']}/{value['variant_id']}": value["experimental_engine_verdict"]
            for value in report["results"]
        },
        "decision": report["decision"],
        "acceptance_passed": report["acceptance"]["passed"],
    }, indent=2))
    return 0 if report["acceptance"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
