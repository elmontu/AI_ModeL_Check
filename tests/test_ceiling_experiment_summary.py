from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import summarize_ceiling_experiments as summary_tool  # noqa: E402


def rational(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def known_group(
    scenario_id: str,
    role: str,
    risk: Fraction,
    sample_size: int,
    replicates: int,
    floor: float,
    ceiling: float,
) -> dict:
    expected_decision = {"safe": "CLEAR", "boundary": "HOLD", "unsafe": "BLOCK"}[role]
    return {
        "tier_id": "representative-full-replay" if sample_size == 2000 else "fast-calibration",
        "tier_role": "primary" if sample_size == 2000 else "diagnostic_only",
        "scenario_id": scenario_id,
        "model_family": "test-label",
        "risk_role": role,
        "sample_size_per_state": sample_size,
        "replicates": replicates,
        "true_exact_risk": rational(risk),
        "simultaneous_family_coverage_rate": 1.0,
        "ceiling_coverage_rate": 1.0,
        "undercoverage": {"count": 0, "rate": 0.0, "exact_binomial_upper": 0.0156},
        "decision_counts": {"CLEAR": 0, "HOLD": 0, "BLOCK": 0},
        "decision_rates": {"CLEAR": 0.0, "HOLD": 0.0, "BLOCK": 0.0},
        "decision_power": {
            "expected_decision": expected_decision,
            "count": replicates,
            "rate": 1.0,
            "simultaneous_exact_binomial_lower": 0.984,
        },
        "false_clear": {"count": 0, "rate": 0.0, "exact_binomial_upper": 0.0156},
        "false_block": {"count": 0, "rate": 0.0, "exact_binomial_upper": 0.0156},
        "coverage_exact_binomial_lower": 0.984,
        "mean_floor": floor,
        "mean_ceiling": ceiling,
        "median_ceiling": ceiling,
        "mean_interval_width": ceiling - floor,
        "mean_ceiling_conservatism": ceiling - float(risk),
        "production_replays": replicates if sample_size == 2000 else 3,
        "production_replay_mismatches": 0,
    }


def known_report() -> dict:
    scenarios = (
        ("xgboost-safe-margin", "safe", Fraction(11, 20), 0.50, 0.61),
        ("cnn-policy-boundary", "boundary", Fraction(13, 20), 0.60, 0.71),
        ("llm-unsafe-margin", "unsafe", Fraction(4, 5), 0.74, 0.86),
    )
    groups = []
    width_checks = []
    widths = {
        "xgboost-safe-margin": (0.50, 0.22),
        "cnn-policy-boundary": (0.51, 0.23),
        "llm-unsafe-margin": (0.44, 0.23),
    }
    for scenario_id, role, risk, primary_floor, primary_ceiling in scenarios:
        small_width, large_width = widths[scenario_id]
        groups.extend([
            known_group(scenario_id, role, risk, 100, 100, 1.0 - small_width, 1.0),
            known_group(scenario_id, role, risk, 500, 100, 0.50, 0.50 + large_width),
            known_group(scenario_id, role, risk, 2000, 400, primary_floor, primary_ceiling),
        ])
        width_checks.append({
            "scenario_id": scenario_id,
            "smallest_n": 100,
            "largest_n": 500,
            "smallest_n_mean_width": small_width,
            "largest_n_mean_width": large_width,
            "passed": True,
        })
    claims = {name: True for name in summary_tool.KNOWN_CLAIMS}
    return {
        "schema_version": "1.0",
        "experiment_id": summary_tool.KNOWN_EXPERIMENT_ID,
        "design": {
            "authority": {
                "experimental_only": True,
                "assessment_input_emitted": False,
                "authorization_eligible": False,
                "prior_screens_promoted": False,
            },
            "scenarios": [
                {
                    "scenario_id": scenario_id,
                    "model_family": "test-label",
                    "risk_role": role,
                    "controlled_ground_truth_only": True,
                    "real_data_target": "not used",
                    "exact_channel_risk": rational(risk),
                }
                for scenario_id, role, risk, _, _ in scenarios
            ],
        },
        "completion": {
            "expected_records": 1800,
            "completed_records": 1800,
            "all_predeclared_cells_reported": True,
            "failed_cells": 0,
        },
        "headline": {
            "all_registered_claims_passed": True,
            "registered_claims": claims,
            "minimum_primary_ceiling_coverage_rate": 1.0,
            "maximum_primary_undercoverage_exact_upper": 0.0156,
            "maximum_primary_false_clear_exact_upper": 0.0156,
        },
        "groups": groups,
        "width_tightening_checks": width_checks,
        "model_family_invariance_checks": [
            {
                "scenario_id": scenario_id,
                "sample_size_per_state": sample_size,
                "exactly_invariant": True,
            }
            for scenario_id, _, _, _, _ in scenarios
            for sample_size in (100, 500, 2000)
        ],
        "tamper_checks": [
            {"check": "incomplete_interface_cannot_clear", "passed": True},
            {"check": "wrong_artifact_binding_cannot_clear", "passed": True},
            {"check": "tampered_certificate_cannot_clear", "passed": True},
        ],
        "assurance_engine_decision_chain": [
            {"release_gate": gate, "passed": True, "experimental_waiver_not_deployment_valid": True}
            for gate in ("clear", "hold", "block")
        ],
        "replay_scope": {
            "primary_analyzer_replays": 1200,
            "full_source_backed_engine_replays": 3,
        },
        # Audit-only fields and a sentinel must never enter publication outputs.
        "raw_count_records": [{"private_value": "/Users/example/private/record.json"}],
    }


def model_result(model: str, family: str, proxy: bool, variant: str, risk: Fraction) -> dict:
    floor = Fraction(1, 2)
    ceiling = Fraction(16, 25) if variant == "raw_bins" else Fraction(14, 25)
    return {
        "collector_model": model,
        "model_family": family,
        "display_name": "ignored source label",
        "llm_proxy_only": proxy,
        "variant_id": variant,
        "state_independent_erasure": rational(Fraction(0) if variant == "raw_bins" else Fraction(9, 10)),
        "sample_seeds": {"out": 1, "in": 2},
        "sample_binding_sha256": "a" * 64,
        "sampling_seed_replayed": True,
        "wrapper_sampling_equivalence": {
            "reference_schedule": {"out": True, "in": True},
            "seed_replay": {"out": True, "in": True},
            "all_passed": True,
        },
        "wrapper_execution_evidence": {
            "path": "wrapper-execution-evidence.json",
            "sha256": "d" * 64,
            "engine_source_bound": True,
        },
        "trials_per_state": 5000,
        "finite_population_sha256": "b" * 64,
        "oracle_exact_bayes_risk": rational(risk),
        "oracle_exact_bayes_risk_decimal": float(risk),
        "sampled_counts": {"out": [1], "in": [1]},
        "production_interval": {
            "exact_floor": rational(floor),
            "exact_ceiling": rational(ceiling),
            "floor": float(floor),
            "ceiling": float(ceiling),
            "width": float(ceiling - floor),
            "covers_oracle": True,
        },
        "experimental_engine_verdict": "clear",
        "engine_chain_completed": True,
        "release_authorization": "none",
        "artifact_directory": "/private/model/artifact",
    }


def model_report() -> dict:
    risk_by_model = {
        "cnn": (Fraction(3, 5), Fraction(51, 100)),
        "xgboost": (Fraction(5, 8), Fraction(41, 80)),
        "compact_transformer_llm_proxy": (Fraction(23, 40), Fraction(203, 400)),
    }
    results = []
    repeated = []
    wrappers = []
    for model, (_, family, proxy) in summary_tool.MODEL_IDENTITIES.items():
        for variant_index, variant in enumerate(summary_tool.MODEL_VARIANTS):
            risk = risk_by_model[model][variant_index]
            results.append(model_result(model, family, proxy, variant, risk))
            margin = abs(risk - Fraction(13, 20))
            eligible = margin >= Fraction(1, 10)
            repeated.append({
                "collector_model": model,
                "model_family": family,
                "variant_id": variant,
                "replicates": 200,
                "trials_per_state": 5000,
                "true_exact_oracle_risk": rational(risk),
                "undercoverage_count": 0,
                "undercoverage_rate": 0.0,
                "simultaneous_clopper_pearson_undercoverage_upper": 0.02,
                "simultaneous_meta_confidence": 1.0 - 0.05 / 18,
                "meta_simultaneous_bound_count": 18,
                "meta_multiplicity_method": summary_tool.META_MULTIPLICITY_METHOD,
                "expected_direction": "CLEAR",
                "absolute_margin_from_tolerance": rational(margin),
                "absolute_margin_from_tolerance_decimal": float(margin),
                "margin_eligible_for_resolution_claim": eligible,
                "decision_counts": {"CLEAR": 200, "HOLD": 0, "BLOCK": 0},
                "clear_count": 200,
                "clear_rate": 1.0,
                "wrong_direction_count": 0,
                "wrong_direction_rate": 0.0,
                "simultaneous_clopper_pearson_wrong_direction_upper": 0.02,
                "correct_direction_count": 200,
                "correct_direction_rate": 1.0,
                "simultaneous_clopper_pearson_correct_direction_lower": 0.96,
                "mean_ceiling": float(risk) + 0.05,
                "p95_ceiling": float(risk) + 0.08,
                "mean_interval_width": 0.10,
                "p95_interval_width": 0.11,
                "maximum_interval_width": 0.12,
                "mean_ceiling_excess_over_oracle": 0.05,
                "p95_ceiling_excess_over_oracle": 0.08,
                "maximum_ceiling_excess_over_oracle": 0.10,
                "every_production_analyzer_replay_completed": True,
                "every_wrapper_sampling_equivalence_check_passed": True,
                "retained_rows_path": "/private/repeated-rows.json",
            })
            wrappers.append({
                "collector_model": model,
                "variant_id": variant,
                "conformant": True,
                "interface": {
                    "state_independent_erasure": rational(
                        Fraction(0) if variant == "raw_bins" else Fraction(9, 10)
                    ),
                },
                "checks": [
                    {"check_id": check_id, "passed": True}
                    for check_id in sorted(summary_tool.WRAPPER_CONFORMANCE_CHECK_IDS)
                ],
            })
    criteria = {name: True for name in summary_tool.MODEL_ACCEPTANCE_CRITERIA}
    return {
        "schema_version": "1.0",
        "experiment_id": summary_tool.MODEL_EXPERIMENT_ID,
        "authority": {
            "experimental_only": True,
            "benchmark_population_conditional": True,
            "authorization_eligible": False,
            "authorization_granted": False,
            "real_world_privacy_claimed": False,
            "decision": "no_release_authorization",
        },
        "collector": {
            "software": {"python": "/Users/example/private/python"},
            "ephemeral_model_artifact_sha256s": {"cnn": "c" * 64},
        },
        "results": results,
        "repeated_validation": {
            "replicates_per_model_variant": 200,
            "meta_simultaneous_bound_count": 18,
            "summaries": repeated,
        },
        "decision_evaluation": {
            "wrong_direction_definition": {
                "oracle_below_tolerance": "BLOCK",
                "oracle_above_tolerance": "CLEAR",
                "oracle_equal_tolerance": "none; any result is non-directional",
                "hold": "never a wrong-direction decision",
            },
            "margin_threshold": rational(Fraction(1, 10)),
            "margin_eligible_family_count": 3,
            "resolved_margin_family_count": 3,
            "minimum_required_resolved_families": 3,
            "eligible_families": [
                f"{model}/erasure_0p9" for model in summary_tool.MODEL_IDENTITIES
            ],
            "resolved_families": [
                f"{model}/erasure_0p9" for model in summary_tool.MODEL_IDENTITIES
            ],
        },
        "wrapper_conformance": {"all_conformant": True, "results": wrappers},
        "erasure_comparisons": [
            {
                "collector_model": model,
                "raw_oracle_risk": rational(risks[0]),
                "erased_oracle_risk": rational(risks[1]),
                "oracle_risk_nonincreasing": True,
                "expected_erased_oracle_risk": rational(risks[1]),
                "exact_erasure_contraction_identity": True,
            }
            for model, risks in risk_by_model.items()
        ],
        "negative_controls": [
            {"control_id": control, "executed": True, "passed": True}
            for control in sorted(summary_tool.MODEL_NEGATIVE_CONTROLS)
        ],
        "acceptance": {"criteria": criteria, "passed": True},
        "checks": {
            "all_oracles_covered": True,
            "all_source_engine_and_repeat_replays_complete": True,
            "full_source_and_engine_replays": {"completed": 6, "expected": 6},
            "production_analyzer_replays": {"completed": 1200, "expected": 1200},
            "raw_scores_retained": False,
            "registered_model_count": 3,
            "registered_family_count": 6,
        },
        "decision": "no_release_authorization",
    }


def predecessor_model_report() -> dict:
    report = copy.deepcopy(model_report())
    report["experiment_id"] = summary_tool.PREDECESSOR_MODEL_EXPERIMENT_ID
    report["repeated_validation"].pop("meta_simultaneous_bound_count")
    report.pop("decision_evaluation")
    report["negative_controls"] = [
        value
        for value in report["negative_controls"]
        if value["control_id"] in summary_tool.PREDECESSOR_MODEL_NEGATIVE_CONTROLS
    ]
    criteria = {
        name: True for name in summary_tool.PREDECESSOR_MODEL_ACCEPTANCE_CRITERIA
    }
    failed = next(
        value
        for value in report["repeated_validation"]["summaries"]
        if value["collector_model"] == "compact_transformer_llm_proxy"
        and value["variant_id"] == "raw_bins"
    )
    for value in report["repeated_validation"]["summaries"]:
        value["simultaneous_clopper_pearson_clear_rate_lower"] = 0.96
    failed["clear_count"] = 109
    failed["clear_rate"] = 0.545
    failed["simultaneous_clopper_pearson_clear_rate_lower"] = 0.44943065755844724
    criteria["all_six_simultaneous_clear_rate_lowers_meet_minimum"] = False
    report["acceptance"] = {"criteria": criteria, "passed": False}
    report["checks"]["all_source_and_engine_replays_complete"] = report["checks"].pop(
        "all_source_engine_and_repeat_replays_complete"
    )
    return report


class CeilingExperimentSummaryTests(unittest.TestCase):
    def build(self) -> dict:
        return summary_tool.build_publication_summary(
            known_report(),
            model_report(),
            known_report_sha256="1" * 64,
            model_report_sha256="2" * 64,
        )

    def test_projection_distinguishes_evidence_levels_and_retains_metrics(self) -> None:
        summary = self.build()
        self.assertEqual(summary["interpretation"]["proof"]["status"], "not_established_by_experiments")
        self.assertEqual(summary["interpretation"]["controlled_evidence"]["status"], "accepted")
        self.assertEqual(
            summary["interpretation"]["model_conditional_evidence"]["status"],
            "all_registered_criteria_passed",
        )
        self.assertEqual(summary["known_channel"]["completed_records"], 1800)
        self.assertEqual(summary["known_channel"]["primary_analyzer_replays"], 1200)
        self.assertEqual(summary["model_backed"]["production_analyzer_replays"], 1200)
        self.assertEqual(len(summary["model_backed"]["results"]), 6)
        self.assertEqual(
            summary["model_backed"]["headline"]["above_tolerance_family_count"],
            0,
        )
        serialized = json.dumps(summary, sort_keys=True)
        self.assertNotIn("/Users/example/private", serialized)
        for forbidden in summary_tool.FORBIDDEN_PUBLIC_KEYS:
            self.assertNotIn(f'"{forbidden}"', serialized)

    def test_markdown_and_svg_render_only_validated_aggregate_results(self) -> None:
        summary = self.build()
        markdown = summary_tool.render_markdown(summary)
        svg = summary_tool.render_svg(summary)
        self.assertIn("not a universal proof", markdown)
        self.assertIn("Controlled exact-ground-truth", markdown)
        self.assertIn("V3 role-aware model-conditional", markdown)
        self.assertIn("not model-backed BLOCK power", markdown)
        self.assertIn("controlled R*=0.80 channel", markdown)
        self.assertIn("Repeated-sample tightness", markdown)
        self.assertIn("Mean excess U-R*", markdown)
        self.assertIn("1200 analyzer + 3 Engine replays", markdown)
        self.assertIn("LLM proxy, not a generative endpoint", markdown)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("tolerance 0.65", svg)
        self.assertEqual(svg.count("<circle"), 10)  # legend plus nine experiment rows

    def test_wrong_ids_inconsistent_acceptance_and_incomplete_runs_fail_closed(self) -> None:
        mutations = []
        wrong_known = known_report()
        wrong_known["experiment_id"] = "other"
        mutations.append((wrong_known, model_report(), "unexpected known experiment id"))
        incomplete_known = known_report()
        incomplete_known["completion"]["completed_records"] = 1799
        mutations.append((incomplete_known, model_report(), "known experiment is incomplete"))
        inconsistent_model = model_report()
        inconsistent_model["acceptance"]["passed"] = False
        mutations.append((known_report(), inconsistent_model, "aggregate acceptance disagrees"))
        incomplete_model = model_report()
        incomplete_model["checks"]["production_analyzer_replays"]["completed"] = 1199
        mutations.append((known_report(), incomplete_model, "v3 analyzer replay family is incomplete"))
        for known, model, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(summary_tool.PublicationSummaryError, message):
                    summary_tool.build_publication_summary(
                        known,
                        model,
                        known_report_sha256="1" * 64,
                        model_report_sha256="2" * 64,
                    )

    def test_v3_meta_wrapper_erasure_margin_and_count_invariants_fail_closed(self) -> None:
        mutations = []
        wrong_meta = model_report()
        wrong_meta["repeated_validation"]["meta_simultaneous_bound_count"] = 17
        mutations.append((wrong_meta, "18 meta endpoints"))

        unbound_wrapper = model_report()
        unbound_wrapper["results"][0]["wrapper_execution_evidence"][
            "engine_source_bound"
        ] = False
        mutations.append((unbound_wrapper, "not source-bound"))

        wrong_erasure = model_report()
        wrong_erasure["erasure_comparisons"][0]["expected_erased_oracle_risk"] = rational(
            Fraction(1, 2)
        )
        mutations.append((wrong_erasure, "erasure contraction identity failed"))

        wrong_rate = model_report()
        wrong_rate["repeated_validation"]["summaries"][0]["wrong_direction_rate"] = 0.1
        mutations.append((wrong_rate, "wrong-direction count/rate mismatch"))

        wrong_margin = model_report()
        eligible = next(
            value
            for value in wrong_margin["repeated_validation"]["summaries"]
            if value["collector_model"] == "cnn"
            and value["variant_id"] == "erasure_0p9"
        )
        eligible["margin_eligible_for_resolution_claim"] = False
        mutations.append((wrong_margin, "inclusive 0.10 threshold"))

        for report, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(summary_tool.PublicationSummaryError, message):
                    summary_tool.build_publication_summary(
                        known_report(),
                        report,
                        known_report_sha256="1" * 64,
                        model_report_sha256="2" * 64,
                    )

    def test_v3_margin_threshold_is_inclusive(self) -> None:
        row = copy.deepcopy(model_report()["repeated_validation"]["summaries"][0])
        row["true_exact_oracle_risk"] = rational(Fraction(11, 20))
        row["absolute_margin_from_tolerance"] = rational(Fraction(1, 10))
        row["absolute_margin_from_tolerance_decimal"] = 0.1
        row["margin_eligible_for_resolution_claim"] = True
        row["mean_ceiling"] = 0.60
        row["p95_ceiling"] = 0.63
        key, public, risk = summary_tool._repeat_summary_v3(row, 0)
        self.assertEqual(key, ("cnn", "raw_bins"))
        self.assertEqual(risk, Fraction(11, 20))
        self.assertTrue(public["margin_eligible_for_resolution_claim"])

    def test_complete_negative_acceptance_is_published_without_promotion(self) -> None:
        report = model_report()
        failed = next(
            value
            for value in report["repeated_validation"]["summaries"]
            if value["collector_model"] == "cnn"
            and value["variant_id"] == "erasure_0p9"
        )
        failed["simultaneous_clopper_pearson_correct_direction_lower"] = 0.94
        failed_criteria = [
            "all_margin_eligible_correct_decision_lowers_meet_minimum",
            "at_least_three_margin_eligible_families_resolve",
        ]
        for criterion in failed_criteria:
            report["acceptance"]["criteria"][criterion] = False
        report["acceptance"]["passed"] = False
        report["decision_evaluation"]["resolved_margin_family_count"] = 2
        report["decision_evaluation"]["resolved_families"].remove("cnn/erasure_0p9")
        result = summary_tool.build_publication_summary(
            known_report(),
            report,
            known_report_sha256="1" * 64,
            model_report_sha256="2" * 64,
        )
        self.assertEqual(result["status"], "controlled_passed_model_acceptance_not_met")
        self.assertFalse(result["model_backed"]["acceptance"]["passed"])
        self.assertEqual(
            result["model_backed"]["acceptance"]["failed_criteria"],
            sorted(failed_criteria),
        )
        self.assertEqual(result["model_backed"]["headline"]["resolved_margin_family_count"], 2)
        markdown = summary_tool.render_markdown(result)
        self.assertIn("Registered acceptance not met", markdown)
        self.assertIn("resolution FAIL", markdown)
        self.assertIn("2/3 margin-eligible families resolved", markdown)

    def test_failed_v2_predecessor_is_retained_separately(self) -> None:
        result = summary_tool.build_publication_summary(
            known_report(),
            model_report(),
            known_report_sha256="1" * 64,
            model_report_sha256="2" * 64,
            predecessor_model_report=predecessor_model_report(),
            predecessor_model_report_sha256="3" * 64,
        )
        previous = result["predecessor_model_backed_v2"]
        self.assertFalse(previous["acceptance"]["passed"])
        self.assertEqual(
            previous["experiment_id"], summary_tool.PREDECESSOR_MODEL_EXPERIMENT_ID
        )
        markdown = summary_tool.render_markdown(result)
        self.assertIn("Historical v2 predecessor — acceptance failed", markdown)
        self.assertIn("109/200", markdown)
        self.assertIn("not relabelled as v3 evidence", markdown)

    def test_generator_writes_all_three_artifacts_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            known_path = base / "known.json"
            model_path = base / "model.json"
            predecessor_path = base / "predecessor.json"
            known_path.write_text(json.dumps(known_report()), encoding="utf-8")
            model_path.write_text(json.dumps(model_report()), encoding="utf-8")
            predecessor_path.write_text(
                json.dumps(predecessor_model_report()), encoding="utf-8"
            )
            json_path = base / "publication" / "summary.json"
            markdown_path = base / "publication" / "results.md"
            svg_path = base / "publication" / "figure.svg"
            result = summary_tool.generate_artifacts(
                known_path,
                model_path,
                json_path,
                markdown_path,
                svg_path,
                predecessor_path,
            )
            self.assertEqual(result["summary_id"], summary_tool.SUMMARY_ID)
            self.assertEqual(json.loads(json_path.read_text())["summary_id"], summary_tool.SUMMARY_ID)
            self.assertIn("![Ceiling validation intervals](figure.svg)", markdown_path.read_text())
            self.assertIn("Historical v2 predecessor", markdown_path.read_text())
            self.assertIn("<svg", svg_path.read_text())

    def test_committed_publication_and_retained_manifests_are_reproducible(self) -> None:
        known = ROOT / "reproduction/finite-channel-ceiling/results/ground-truth-report.json"
        current = ROOT / "reproduction/model-backed-finite-channel/results/v3/model-backed-finite-channel-report.json"
        predecessor = ROOT / "reproduction/model-backed-finite-channel/results/v2/model-backed-finite-channel-report.json"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            json_path = base / "reproduction/ceiling-experiment-summary.json"
            markdown_path = base / "paper/ceiling-experiment-results.md"
            svg_path = base / "paper/figures/ceiling-validation.svg"
            summary_tool.generate_artifacts(
                known,
                current,
                json_path,
                markdown_path,
                svg_path,
                predecessor,
            )
            self.assertEqual(
                json_path.read_bytes(),
                (ROOT / "reproduction/ceiling-experiment-summary.json").read_bytes(),
            )
            self.assertEqual(
                markdown_path.read_bytes(),
                (ROOT / "paper/ceiling-experiment-results.md").read_bytes(),
            )
            self.assertEqual(
                svg_path.read_bytes(),
                (ROOT / "paper/figures/ceiling-validation.svg").read_bytes(),
            )

        retained = (
            (
                ROOT / "reproduction/finite-channel-ceiling/results",
                "manifest.json",
                {
                    "ground_truth_report_sha256": "ground-truth-report.json",
                    "execution_log_sha256": "execution.log",
                    "resource_usage_sha256": "resource-usage.txt",
                },
            ),
            (
                ROOT / "reproduction/model-backed-finite-channel/results/v2",
                "manifest.json",
                {
                    "report_sha256": "model-backed-finite-channel-report.json",
                    "finite_population_oracles_sha256": "finite-population-oracles.json",
                    "wrapper_conformance_sha256": "wrapper-conformance.json",
                    "execution_log_sha256": "model-backed-finite-channel-execution.log",
                    "resource_usage_sha256": "model-backed-finite-channel-resource-usage.txt",
                },
            ),
            (
                ROOT / "reproduction/model-backed-finite-channel/results/v3",
                "manifest.json",
                {
                    "report_sha256": "model-backed-finite-channel-report.json",
                    "finite_population_oracles_sha256": "finite-population-oracles.json",
                    "wrapper_conformance_sha256": "wrapper-conformance.json",
                    "execution_log_sha256": "model-backed-finite-channel-execution.log",
                    "resource_usage_sha256": "model-backed-finite-channel-resource-usage.txt",
                },
            ),
        )
        for directory, manifest_name, bindings in retained:
            with self.subTest(directory=directory):
                manifest = json.loads((directory / manifest_name).read_text())
                self.assertEqual(
                    manifest["retained_artifacts"]["artifact_count_including_manifest"],
                    sum(path.is_file() for path in directory.rglob("*")),
                )
                for field, relative in bindings.items():
                    digest = hashlib.sha256((directory / relative).read_bytes()).hexdigest()
                    self.assertEqual(manifest["retained_artifacts"][field], digest)

    def test_generator_does_not_create_outputs_when_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            known_path = base / "known.json"
            model_path = base / "model.json"
            failed = model_report()
            failed["acceptance"]["criteria"]["all_six_oracle_risks_covered"] = False
            known_path.write_text(json.dumps(known_report()), encoding="utf-8")
            model_path.write_text(json.dumps(failed), encoding="utf-8")
            outputs = [base / "summary.json", base / "results.md", base / "figure.svg"]
            with self.assertRaises(summary_tool.PublicationSummaryError):
                summary_tool.generate_artifacts(known_path, model_path, *outputs)
            self.assertTrue(all(not output.exists() for output in outputs))

    def test_strict_loader_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.json"
            for payload in ('{"x": 1, "x": 2}', '{"x": NaN}'):
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaises(summary_tool.PublicationSummaryError):
                        summary_tool.load_report(path)


if __name__ == "__main__":
    unittest.main()
