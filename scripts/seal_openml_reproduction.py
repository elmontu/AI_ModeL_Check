#!/usr/bin/env python3
"""Create a top-level hash manifest for the completed OpenML study."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, str | int]:
    return {
        "path": str(path if path.is_absolute() else path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def main() -> None:
    suite_path = ROOT / "reproduction/openml/manifests/suite-99-datasets.json"
    suite = json.loads(suite_path.read_text())
    snapshot_errors = []
    snapshot_bytes = 0
    for dataset in suite["datasets"]:
        path = ROOT / dataset["snapshot_path"]
        snapshot_bytes += path.stat().st_size if path.is_file() else 0
        if not path.is_file():
            snapshot_errors.append({"dataset_id": dataset["dataset_id"], "error": "missing"})
        elif sha256_file(path) != dataset["snapshot_sha256"]:
            snapshot_errors.append({"dataset_id": dataset["dataset_id"], "error": "hash mismatch"})

    tier_names = (
        "structural",
        "membership",
        "mlp",
        "composition",
        "metadata-adversary",
        "dp-sgd",
        "multi-shadow",
        "attribute",
        "reconstruction",
        "population-validation",
    )
    summaries = {
        name: json.loads((ROOT / f"output/reproduction/openml-{name}-summary.json").read_text())
        for name in tier_names
    }
    analyses = {
        name: json.loads((ROOT / f"output/reproduction/openml-{name}-analysis.json").read_text())
        for name in tier_names
    }
    decision_summary = json.loads(
        (ROOT / "output/reproduction/openml-decision-witnesses-summary.json").read_text()
    )
    decision_analysis = json.loads(
        (ROOT / "output/reproduction/openml-decision-witnesses-analysis.json").read_text()
    )
    portfolio_stochastic = json.loads(
        (ROOT / "output/reproduction/portfolio-stochastic-analysis.json").read_text()
    )
    protocol_feasibility = json.loads(
        (ROOT / "output/reproduction/protocol-feasibility-benchmark-analysis.json").read_text()
    )
    prospective_training = json.loads(
        (ROOT / "output/reproduction/v05-prospective-training-summary.json").read_text()
    )
    prospective_decision = json.loads(
        (ROOT / "output/reproduction/v05-prospective-decision-summary.json").read_text()
    )
    prospective_primary = next(
        row
        for row in prospective_decision["aggregate_methods"]
        if row["method"] == "simultaneous-joint"
    )
    runtime = json.loads(
        (ROOT / "reproduction/openml/runtime.json").read_text(encoding="utf-8")
    )
    validation_flags = {
        "structural": analyses["structural"]["validation"][
            "artifact_hashes_histograms_splits_and_rosters_valid"
        ],
        "membership": analyses["membership"]["validation"]["artifact_hashes_and_counts_valid"],
        "mlp": analyses["mlp"]["validation"]["artifact_hashes_and_counts_valid"],
        "composition": analyses["composition"]["validation"][
            "artifact_hashes_counts_and_bounds_valid"
        ],
        "metadata-adversary": analyses["metadata-adversary"]["validation"][
            "artifact_hashes_metadata_fields_counts_and_scores_valid"
        ],
        "dp-sgd": analyses["dp-sgd"]["validation"][
            "artifact_hashes_counts_and_independent_accountant_replay_valid"
        ],
        "multi-shadow": analyses["multi-shadow"]["validation"][
            "artifact_hashes_assignments_counts_and_scores_valid"
        ],
        "attribute": analyses["attribute"]["validation"][
            "artifact_hashes_raw_counts_and_metrics_valid"
        ],
        "reconstruction": analyses["reconstruction"]["validation"][
            "artifact_hashes_raw_counts_and_metrics_valid"
        ],
        "population-validation": analyses["population-validation"]["validation"][
            "artifact_hashes_histograms_designs_counts_and_bounds_valid"
        ],
    }
    tier_status = {
        name: {
            "expected_runs": summaries[name]["expected_runs"],
            "completed_runs": summaries[name]["completed_runs"],
            "failed_runs": summaries[name]["failed_runs"],
            "validation_passed": bool(validation_flags[name]),
        }
        for name in tier_names
    }
    if snapshot_errors or not all(item["failed_runs"] == 0 for item in tier_status.values()):
        raise RuntimeError("cannot seal: missing or failed data/runs")
    if not all(validation_flags.values()):
        raise RuntimeError("cannot seal: an artifact validation failed")
    if not decision_analysis["validation"]["raw_hash_and_all_values_replayed"]:
        raise RuntimeError("cannot seal: decision-theory witness replay failed")
    if decision_analysis["validation"]["errors"]:
        raise RuntimeError("cannot seal: decision-theory witness replay reported errors")
    if not portfolio_stochastic["validation"]["valid"]:
        raise RuntimeError("cannot seal: stochastic portfolio benchmark replay failed")
    if not all(protocol_feasibility["validation"].values()):
        raise RuntimeError("cannot seal: protocol-feasibility benchmark replay failed")
    if (
        prospective_training["failed_runs"]
        or prospective_training["completed_runs"] != prospective_training["expected_runs"]
    ):
        raise RuntimeError("cannot seal: full-corpus training grid is incomplete")
    if prospective_training["design_sha256"] != sha256_file(
        ROOT / "reproduction/prospective-v05/config.json"
    ):
        raise RuntimeError("cannot seal: full-corpus design hash mismatch")
    prospective_validation = prospective_decision["validation"]
    if not (
        prospective_validation["training_grid_complete"]
        and prospective_validation["all_development_accountants_valid"]
        and prospective_validation["all_training_accountants_valid"]
        and prospective_validation["all_training_artifact_hashes_valid"]
        and prospective_validation["all_training_attack_counts_valid"]
        and prospective_validation["all_selected_privacy_budgets_valid"]
    ):
        raise RuntimeError("cannot seal: full-corpus validation failed")

    retained = [
        "reproduction/openml/config.json",
        "reproduction/openml/runtime.json",
        "reproduction/openml/mlp-config.json",
        "reproduction/openml/metadata-adversary-config.json",
        "reproduction/openml/dp-sgd-config.json",
        "reproduction/openml/multi-shadow-config.json",
        "reproduction/openml/inference-config.json",
        "reproduction/openml/population-validation-config.json",
        "reproduction/portfolio-stochastic/config.json",
        "reproduction/prospective-v05/config.json",
        "reproduction/openml/manifests/suite-99-source.json",
        "reproduction/openml/manifests/suite-99-datasets.json",
        "reproduction/openml/manifests/expensive-subsets.json",
        "output/reproduction/openml-structural-summary.json",
        "output/reproduction/openml-structural-summary.csv",
        "output/reproduction/openml-structural-analysis.json",
        "output/reproduction/openml-membership-summary.json",
        "output/reproduction/openml-membership-summary.csv",
        "output/reproduction/openml-membership-analysis.json",
        "output/reproduction/openml-mlp-summary.json",
        "output/reproduction/openml-mlp-summary.csv",
        "output/reproduction/openml-mlp-analysis.json",
        "output/reproduction/openml-composition-summary.json",
        "output/reproduction/openml-composition-summary.csv",
        "output/reproduction/openml-composition-analysis.json",
        "output/reproduction/openml-metadata-adversary-summary.json",
        "output/reproduction/openml-metadata-adversary-summary.csv",
        "output/reproduction/openml-metadata-adversary-analysis.json",
        "output/reproduction/openml-dp-sgd-summary.json",
        "output/reproduction/openml-dp-sgd-summary.csv",
        "output/reproduction/openml-dp-sgd-analysis.json",
        "output/reproduction/openml-multi-shadow-summary.json",
        "output/reproduction/openml-multi-shadow-summary.csv",
        "output/reproduction/openml-multi-shadow-analysis.json",
        "output/reproduction/openml-attribute-summary.json",
        "output/reproduction/openml-attribute-summary.csv",
        "output/reproduction/openml-attribute-analysis.json",
        "output/reproduction/openml-reconstruction-summary.json",
        "output/reproduction/openml-reconstruction-summary.csv",
        "output/reproduction/openml-reconstruction-analysis.json",
        "output/reproduction/openml-population-validation-summary.json",
        "output/reproduction/openml-population-validation-summary.csv",
        "output/reproduction/openml-population-validation-analysis.json",
        "output/reproduction/openml-decision-witnesses-summary.json",
        "output/reproduction/openml-decision-witnesses-raw.json.gz",
        "output/reproduction/openml-decision-witnesses-analysis.json",
        "output/reproduction/portfolio-stochastic-summary.json",
        "output/reproduction/portfolio-stochastic-raw.json.gz",
        "output/reproduction/portfolio-stochastic-analysis.json",
        "output/reproduction/protocol-feasibility-benchmark-raw.json",
        "output/reproduction/protocol-feasibility-benchmark-summary.json",
        "output/reproduction/protocol-feasibility-benchmark-analysis.json",
        "output/reproduction/v05-prospective-training-summary.json",
        "output/reproduction/v05-prospective-decision-summary.json",
        "output/reproduction/v05-prospective-decision-analysis.json",
        "output/reproduction/v05-prospective-decision-raw.json.gz",
        "output/evaluation/framework-effectiveness.json",
        "docs/README.md",
        "docs/architecture.md",
        "docs/reference/threat-model.md",
        "docs/reference/production-roadmap.md",
        "docs/reference/adaptation-profiles.md",
        "reproduction/openml/README.md",
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "schemas/README.md",
        "scripts/README.md",
        "examples/README.md",
        "schemas/assessment-request-v2.json",
        "schemas/assessment-report-v2.json",
        "schemas/optimization-request-v2.json",
        "schemas/optimization-report-v2.json",
        "schemas/signed-optimization-manifest-v2.json",
        "schemas/incomplete-portfolio-problem-v1.json",
        "schemas/protocol-feasibility-problem-v1.json",
        "schemas/protocol-feasibility-certificate-v1.json",
        "schemas/incomplete-portfolio-certificate-v1.json",
        "schemas/incomplete-portfolio-certificate-v1.1.json",
        "schemas/incomplete-portfolio-specification-v1.json",
        "schemas/portfolio-multinomial-plan-v1.json",
        "schemas/portfolio-multinomial-counts-v1.json",
        "schemas/portfolio-error-budget-v1.json",
        "schemas/portfolio-multinomial-request-v1.json",
        "schemas/portfolio-multinomial-evidence-v1.json",
        "examples/optimization-request.json",
        "examples/incomplete-portfolio-problem.json",
        "examples/protocol-feasibility-problem.json",
        "examples/incomplete-portfolio-specification.json",
        "examples/portfolio-multinomial-request.json",
        "examples/evidence/optimization-utility.json",
        "examples/evidence/bounded-api-control.json",
        "examples/evidence/bounded-api-portfolio.json",
        "examples/evidence/assessment-clear-report.json",
        "examples/evidence/incomplete-portfolio-uniform-bit.json",
        "examples/evidence/portfolio-multinomial-counts.json",
        "examples/evidence/portfolio-multinomial-plan.json",
        "examples/evidence/portfolio-error-budget.json",
        "output/assessments/demo-optimization.json",
        "output/assessments/demo-protocol-feasibility-certificate.json",
        "src/model_release_assurance/models.py",
        "src/model_release_assurance/engine.py",
        "src/model_release_assurance/integrity.py",
        "src/model_release_assurance/audit.py",
        "src/model_release_assurance/cli.py",
        "src/model_release_assurance/__init__.py",
        "src/model_release_assurance/decision_theory.py",
        "src/model_release_assurance/decision.py",
        "src/model_release_assurance/portfolio.py",
        "src/model_release_assurance/incomplete_portfolio.py",
        "src/model_release_assurance/portfolio_statistics.py",
        "src/model_release_assurance/protocol_feasibility.py",
        "src/model_release_assurance/optimizer.py",
        "src/model_release_assurance/version.py",
        "src/model_release_assurance/analyzers/__init__.py",
        "src/model_release_assurance/analyzers/attack.py",
        "src/model_release_assurance/analyzers/controlled_inference.py",
        "tests/test_framework.py",
        "tests/test_decision_theory.py",
        "tests/test_incomplete_portfolio.py",
        "tests/test_portfolio_statistics.py",
        "tests/test_portfolio_stochastic_benchmark.py",
        "tests/test_protocol_feasibility.py",
        "tests/test_protocol_feasibility_benchmark.py",
        "tests/test_effectiveness.py",
        "tests/test_cli.py",
        "tests/test_openml_reproduction.py",
        "tests/test_v05_prospective_study.py",
        "scripts/fetch_openml_suite.py",
        "scripts/select_openml_subsets.py",
        "scripts/run_portfolio_stochastic_benchmark.py",
        "scripts/run_protocol_feasibility_benchmark.py",
        "scripts/run_v05_prospective_study.py",
        "scripts/analyze_v05_prospective_study.py",
        "scripts/evaluate_framework_effectiveness.py",
        "scripts/analyze_portfolio_stochastic_benchmark.py",
        "scripts/run_openml_structural.py",
        "scripts/analyze_openml_structural.py",
        "scripts/run_openml_membership.py",
        "scripts/analyze_openml_membership.py",
        "scripts/run_openml_mlp.py",
        "scripts/analyze_openml_mlp.py",
        "scripts/run_openml_composition.py",
        "scripts/analyze_openml_composition.py",
        "scripts/run_openml_metadata_adversary.py",
        "scripts/analyze_openml_metadata_adversary.py",
        "scripts/run_openml_dp_sgd.py",
        "scripts/analyze_openml_dp_sgd.py",
        "scripts/run_openml_multi_shadow.py",
        "scripts/analyze_openml_multi_shadow.py",
        "scripts/run_openml_inference.py",
        "scripts/analyze_openml_inference.py",
        "scripts/run_openml_population_validation.py",
        "scripts/analyze_openml_population_validation.py",
        "scripts/build_openml_decision_witnesses.py",
        "scripts/analyze_openml_decision_witnesses.py",
        "pyproject.toml",
        "requirements.lock",
        "requirements-experiments.txt",
    ]
    manifest = {
        "manifest_version": 6,
        "study": "OpenML-CC18 clean-room reproduction, finite-portfolio and protocol benchmarks, and Version 0.5 full-corpus proxy release study",
        "sealed_at": "2026-08-17",
        "claim_boundary": "new clean-room and fixed-frame proxy evidence; neither exact recovery of source-writeup artifacts nor representative government release yield",
        "source_artifacts": [],
        "dataset_corpus": {
            "suite_id": 99,
            "datasets": len(suite["datasets"]),
            "source_rows": sum(int(item["rows"]) for item in suite["datasets"]),
            "snapshot_bytes": snapshot_bytes,
            "snapshot_hashes_verified": not snapshot_errors,
            "snapshot_errors": snapshot_errors,
        },
        "tiers": tier_status,
        "decision_theory_witnesses": {
            "datasets_considered": decision_summary["search"]["datasets_considered"],
            "common_roster_rows_examined": decision_summary["search"]["common_roster_rows_examined"],
            "metric_reversal_candidates": decision_summary["search"]["metric_reversal_candidates"],
            "anchoring_reversal_candidates": decision_summary["search"]["anchoring_reversal_candidates"],
            "substitution_separation_candidates": decision_summary["search"]["substitution_separation_candidates"],
            "raw_hash_and_all_values_replayed": True,
        },
        "stochastic_incomplete_portfolio": {
            "raw_records_replayed": portfolio_stochastic["validation"]["raw_records_replayed"],
            "groups_replayed": portfolio_stochastic["validation"]["groups_replayed"],
            "minimum_empirical_family_coverage": portfolio_stochastic["headline"][
                "minimum_empirical_family_coverage"
            ],
            "maximum_observed_false_clear_rate": portfolio_stochastic["headline"][
                "maximum_false_clear_rate"
            ],
            "maximum_safe_case_false_block_rate": portfolio_stochastic["headline"][
                "maximum_safe_case_false_block_rate"
            ],
            "certificate_and_special_case_replay_valid": (
                portfolio_stochastic["headline"]["all_certificate_replays_passed"]
                and portfolio_stochastic["headline"][
                    "all_special_case_equivalence_checks_passed"
                ]
            ),
        },
        "finite_protocol_feasibility": {
            "all_binary_frontiers_tight": protocol_feasibility["validation"][
                "all_binary_frontiers_tight"
            ],
            "all_decision_oracles_passed": protocol_feasibility["validation"][
                "all_decision_oracles_passed"
            ],
            "all_retained_tiers_complete_and_valid": protocol_feasibility["validation"][
                "all_retained_tiers_complete_and_valid"
            ],
            "representative_release_yield_identified": False,
            "claim_boundary": protocol_feasibility["claim_boundary"],
        },
        "full_corpus_proxy_study": {
            "study_id": prospective_decision["study_id"],
            "design_status": prospective_decision["design_status"],
            "extension_disclosure": prospective_decision.get("extension_disclosure"),
            "claim_boundary": prospective_decision["claim_boundary"],
            "datasets": prospective_decision["datasets"],
            "training_cells": prospective_decision["trained_model_cells"],
            "trained_ml_artifacts": prospective_decision["trained_ml_artifacts"],
            "failed_training_cells": prospective_training["failed_runs"],
            "development_runs": prospective_decision["development_runs"],
            "evaluation_runs": prospective_decision["evaluation_runs"],
            "raw_decision_rows": prospective_decision["raw_decision_rows"],
            "primary_requested_positions": prospective_primary["requested_positions"],
            "primary_released_positions": prospective_primary["released_positions"],
            "primary_proxy_false_clear_actions": prospective_primary[
                "proxy_false_clear_actions"
            ],
            "primary_privacy_budget_violations": prospective_primary[
                "privacy_budget_violations"
            ],
            "stratified_aggregate_methods": prospective_decision[
                "stratified_aggregate_methods"
            ],
            "representative_government_release_yield_identified": False,
        },
        "trained_release_or_reference_model_artifacts": (
            summaries["structural"]["completed_runs"]
            + 2 * summaries["membership"]["completed_runs"]
            + 2 * summaries["mlp"]["completed_runs"]
            + 3 * summaries["dp-sgd"]["completed_runs"]
        ),
        "trained_shadow_model_artifacts": (
            15 * summaries["multi-shadow"]["completed_runs"]
        ),
        "trained_attack_classifier_artifacts": (
            2 * summaries["metadata-adversary"]["completed_runs"]
            + 4 * summaries["attribute"]["completed_runs"]
        ),
        "composition_reuses_structural_models": True,
        "runtime": runtime,
        "retained_files": [file_record(ROOT / path) for path in retained],
        "remaining_claim_limits": {
            "complete_private_pipeline": "The DP mechanism conditions on fixed public benchmark preprocessing and does not cover separately released confidential summaries.",
            "augmented_online_lira": "The executed 15-shadow likelihood-ratio tier is LiRA-style, not the full augmented online protocol.",
            "full_record_reconstruction": "The executed reconstruction tier recovers one declared feature, not a full row or training set.",
            "deployment_population": "Finite-population validity is established only for enumerated OpenML snapshots, not a government adopter population.",
            "production_service": "Identity, sandboxing, KMS/HSM, append-only external anchoring, portfolio locking, and accreditation are outside the clean-room study.",
        },
    }
    manifest["total_trained_ml_artifacts"] = (
        manifest["trained_release_or_reference_model_artifacts"]
        + manifest["trained_shadow_model_artifacts"]
        + manifest["trained_attack_classifier_artifacts"]
    )
    output = ROOT / "output/reproduction/openml-study-manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(output),
        "datasets": manifest["dataset_corpus"]["datasets"],
        "trained_release_or_reference_model_artifacts": manifest["trained_release_or_reference_model_artifacts"],
        "total_trained_ml_artifacts": manifest["total_trained_ml_artifacts"],
        "tiers": tier_status,
    }, indent=2))


if __name__ == "__main__":
    main()
