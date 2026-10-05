"""Read-only inventory of executable screens, separate from policy AttackCatalog.

Discovery does not load models, contact Ollama, check optional installations, or
submit evidence. Names come from the executable suite registrations/corpus.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .export_red_team import (ExportRedTeamReport, NATIVE_TOOL_ID, NATIVE_TOOL_VERSION,
                              native_implementation_sha256)
from .integrity import canonical_json_bytes, sha256_bytes, sha256_file
from .language_red_team import corpus
from .regression_red_team import REGRESSION_TOOL_IDS
from .tabular_red_team import tabular_suite_tools


_PACKAGE = Path(__file__).parent
_NUMERIC_INPUTS = "Dense finite numeric features, 40..5000 records in each partition, 1..256 features."

# Descriptions qualify the executable registrations below; they never add tools.
_TABULAR_SCOPE = {
    "structural_disclosure": (
        ["predict", "predict_proba", "model_structure", "training_and_nonmember_records_and_labels"],
        "Parameter/equivalence-class indicators; unsupported for combined ensembles; preprocessing excluded.",
    ),
    "worst_case_membership": (
        ["predict_proba", "training_and_nonmember_records_and_labels"],
        "Repeated learned membership screen with dummy baseline; exploratory suite output is not a validated battery.",
    ),
    "membership_score_attacks": (
        ["predict_proba", "training_and_nonmember_records_and_labels"],
        "Negative loss, confidence and entropy probes; positive/null controls exercise the scoring harness only.",
    ),
    "model_extraction": (
        ["predict", "auxiliary_nonmember_records"],
        "Label-query surrogate imitation with separate query/audit records; does not recover weights.",
    ),
    "attribute_inference": (
        ["predict_proba", "auxiliary_nonmember_records_and_true_labels", "other_transformed_features"],
        "Coarse inference of the first transformed feature; sensitive attribute is not user-declared.",
    ),
    "numeric_robustness": (
        ["predict", "evaluation_records_and_labels", "training_feature_scales"],
        "Random numeric perturbations; no semantic robustness guarantee.",
    ),
    "label_only_membership": (
        ["predict", "training_and_nonmember_records_and_labels"],
        "Correctness threshold with known true labels; strict threshold can abstain on ties.",
    ),
    "adaptive_adversarial_search": (
        ["predict", "predict_proba", "evaluation_records_and_labels", "training_feature_scales"],
        "Bounded greedy score-query perturbation with random-search baseline; no semantic validity claim.",
    ),
    "tree_leaf_exposure": (
        ["apply", "training_and_nonmember_records", "white_box_tree_leaf_indices"],
        "Only xgboost/random-forest leaf adapters; path occupancy is not record reconstruction.",
    ),
    "label_poisoning": (
        ["clone_and_fit", "training_and_evaluation_records_and_labels"],
        "Bounded XGBoost, random forest, logistic or MLP retraining copies; no candidate poisoning detection.",
    ),
    "trigger_backdoor": (
        ["clone_and_fit", "training_and_evaluation_records_and_labels"],
        "Same bounded retraining adapters; one out-of-range first-feature trigger; no candidate backdoor detection.",
    ),
}
_REGRESSION_SCOPE = {
    "regression_loss_membership": (
        ["predict_scalar", "training_and_nonmember_records_and_labels"],
        "Negative squared-loss threshold; positive/null controls cover the scorer, not an end-to-end leaking regressor.",
    ),
    "regression_extraction": (
        ["predict_scalar", "auxiliary_nonmember_records"],
        "Scalar-query surrogate imitation with disjoint query/audit records; no weight recovery.",
    ),
    "regression_perturbation": (
        ["predict_scalar", "evaluation_records_and_labels", "training_feature_scales"],
        "Random and bounded greedy numeric perturbations; no semantic validity claim.",
    ),
}


def _source_identity(filename: str) -> dict[str, str]:
    return {"path": "src/model_release_assurance/" + filename,
            "sha256": sha256_file(_PACKAGE / filename)}


def _entry(tool_id: str, suite_id: str, version: str, entrypoint: str,
           interfaces: list[str], scope: str, dependencies: list[str],
           sources: list[dict[str, str]], model_family: str,
           input_requirements: str, report_collection: str, report_id_field: str,
           *, evidence_role: str = "exploratory_screen") -> dict[str, Any]:
    return {
        "tool_id": tool_id,
        "suite_id": suite_id,
        "implementation_version": version,
        "implementation_sources": sources,
        "entrypoint": entrypoint,
        "implemented": True,
        "implementation_status": "implemented",
        "applicable_model_families": [model_family],
        "supported_interfaces": interfaces,
        "input_requirements": input_requirements,
        "dependencies": dependencies,
        "dependency_availability": "not_checked",
        "evidence_location": {"collection": report_collection, "id_field": report_id_field, "id": tool_id},
        "evidence_role": evidence_role,
        "assessment_eligible": False,
        "authorization_eligible": False,
        "can_clear": False,
        "can_block": False,
        "decision_authority": "none",
        "scope": scope,
    }


def red_team_discovery_catalog() -> dict[str, Any]:
    """Describe all bundled suites without executing an attack or probing a host."""
    tabular_ids = [name for name, _ in tabular_suite_tools()]
    if set(tabular_ids) != set(_TABULAR_SCOPE) or set(REGRESSION_TOOL_IDS) != set(_REGRESSION_SCOPE):
        raise RuntimeError("Executable red-team registrations require matching discovery descriptions")
    entries = []
    for tool_id in tabular_ids:
        interfaces, scope = _TABULAR_SCOPE[tool_id]
        entries.append(_entry(
            tool_id, "tabular", "educational-tabular-red-team/2",
            "model_release_assurance.tabular_red_team:run_tabular_suite",
            interfaces, scope, ["numpy", "scikit-learn", "scipy", "candidate estimator runtime"],
            [_source_identity("tabular_red_team.py"), _source_identity("red_team.py")],
            "numeric_classifier", _NUMERIC_INPUTS, "tools", "tool",
        ))
    for tool_id in REGRESSION_TOOL_IDS:
        interfaces, scope = _REGRESSION_SCOPE[tool_id]
        entries.append(_entry(
            tool_id, "regression", "regression-red-team/2",
            "model_release_assurance.regression_red_team:run_suite",
            interfaces, scope, ["numpy", "scikit-learn", "candidate estimator runtime"],
            [_source_identity("regression_red_team.py"), _source_identity("tabular_red_team.py")],
            "numeric_regressor", _NUMERIC_INPUTS, "tools", "tool",
        ))
    for case in corpus("DISCOVERY_PLACEHOLDER"):
        scope = "Fixed synthetic-context probe; not training-data memorization or comprehensive jailbreak coverage."
        if case["scoring"] == "tool":
            scope += " Tool calls are inert and never executed."
        if case["id"].startswith("rag_"):
            scope += " Synthetic document injection; no live retrieval index."
        entry = _entry(
            case["id"], "language", "local-language-red-team/2",
            "model_release_assurance.language_red_team:run",
            ["local_ollama_chat"] + (["inert_function_call_schema"] if case["scoring"] == "tool" else []),
            scope, ["local Ollama HTTP runtime", "installed Ollama model"],
            [_source_identity("language_red_team.py")], "local_chat_language_model",
            "Installed local Ollama model; synthetic secrets/documents only; bounded context and output.",
            "tests", "id",
        )
        entry["scoring"] = case["scoring"]
        entries.append(entry)

    native = _entry(
        NATIVE_TOOL_ID, "public_export", NATIVE_TOOL_VERSION,
        "model_release_assurance.export_red_team:run_public_tabular_demo",
        ["full_artifact_delivery", "predict_proba", "public_training_and_nonmember_records_and_labels"],
        "One public breast-cancer GaussianNB/StandardScaler fixture; exact JSON package reloaded before scoring. "
        "Known-leak and null controls; illustrative operational AUC threshold, not a scientific privacy ceiling.",
        ["numpy", "scikit-learn"],
        [_source_identity("export_red_team.py"), _source_identity("tabular_red_team.py")],
        "public_fixture_gaussian_nb_classifier",
        "Bundled public breast-cancer fixture only; one frozen seed/model/split/attack; new output directory required.",
        "tools", "tool_id", evidence_role="operational_export_screen",
    )
    native["implementation_sha256"] = native_implementation_sha256()
    native["report_format_version"] = ExportRedTeamReport.model_fields["schema_version"].default
    native["cli_command"] = "python -m model_release_assurance.export_red_team demo --output NEW_DIRECTORY"
    native["evidence_location"]["artifact"] = "report.json"
    native["operational_export_gate"] = True
    entries.append(native)

    # This source-checkout experiment is intentionally not a console execution adapter.
    script = _PACKAGE.parents[1] / "scripts" / "run_openml_multi_shadow.py"
    standalone_sources = [{"path": "scripts/" + name,
                           "sha256": sha256_file(script.with_name(name))}
                          for name in ("run_openml_multi_shadow.py", "run_openml_membership.py", "run_openml_structural.py")
                          if script.with_name(name).is_file()]
    standalone = _entry(
        "multi_shadow_likelihood_ratio", "multi_shadow", "source-hash-versioned",
        "scripts/run_openml_multi_shadow.py --config PATH --shadow-config PATH --subset-manifest PATH",
        ["sealed_target_score_artifacts", "dataset_snapshot", "shadow_training"],
        "Separate OpenML XGBoost experiment; LiRA-style baseline, not full augmented online LiRA or SACRO-ML integration.",
        ["numpy", "pandas", "pyarrow", "joblib", "scikit-learn", "scipy", "xgboost", "sealed target manifests and dataset snapshots"],
        standalone_sources, "xgboost_classifier",
        "Source checkout plus pre-existing matching OpenML snapshots, sealed target manifests/raw scores and declared configs.",
        "records", "experiment", evidence_role="standalone_experiment",
    )
    standalone.update({"execution_surface": "source_checkout_only",
                       "implementation_status": "implemented" if script.is_file() else "source_unavailable",
                       "execution_available": None if script.is_file() else False,
                       "source_available": script.is_file(),
                       "console_integrated": False,
                       "evidence_location": {"artifact": "output/reproduction/openml-multi-shadow-summary.json", "collection": "records"}})
    entries.append(standalone)
    catalog = {
        "format_version": "red-team-discovery/1",
        "catalog_id": "mra.executable-red-team-discovery",
        "catalog_version": "1.0.0",
        "entries": entries,
        "suite_counts": {suite: sum(entry["suite_id"] == suite for entry in entries)
                         for suite in ("tabular", "regression", "language", "public_export", "multi_shadow")},
        "language_controls": ["benign", "unprotected_canary"],
        "external_adapters": [{"name": name, "implementation_status": "not_integrated"}
                              for name in ("SACRO-ML", "ART", "garak", "PyRIT")],
        "execution_requested": False,
        "can_clear": False,
        "can_block": False,
        "assessment_eligible": False,
        "authorization_eligible": False,
        "note": "Discovery is not execution or evidence validation. Completed attacks do not establish safety. "
                "Policy-bound AttackCatalog and validated AttackBatteryInput remain separate contracts. "
                "An operational export gate may halt progression under a bound policy without scientific blocking/clearing authority.",
    }
    return {**catalog, "discovery_sha256": sha256_bytes(canonical_json_bytes(catalog))}
