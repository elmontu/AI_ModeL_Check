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
                "clear_count": 200,
                "clear_rate": 1.0,
                "simultaneous_clopper_pearson_clear_rate_lower": 0.96,
                "mean_ceiling": float(risk) + 0.05,
                "p95_ceiling": float(risk) + 0.08,
                "mean_interval_width": 0.10,
                "p95_interval_width": 0.11,
                "maximum_interval_width": 0.12,
                "mean_ceiling_excess_over_oracle": 0.05,
                "p95_ceiling_excess_over_oracle": 0.08,
                "maximum_ceiling_excess_over_oracle": 0.10,
                "every_production_analyzer_replay_completed": True,
                "retained_rows_path": "/private/repeated-rows.json",
            })
            wrappers.append({
                "collector_model": model,
                "variant_id": variant,
                "conformant": True,
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
            "summaries": repeated,
        },
        "wrapper_conformance": {"all_conformant": True, "results": wrappers},
        "negative_controls": [
            {"control_id": control, "executed": True, "passed": True}
            for control in sorted(summary_tool.MODEL_NEGATIVE_CONTROLS)
        ],
        "acceptance": {"criteria": criteria, "passed": True},
        "checks": {
            "all_oracles_covered": True,
            "all_source_and_engine_replays_complete": True,
            "full_source_and_engine_replays": {"completed": 6, "expected": 6},
            "production_analyzer_replays": {"completed": 1200, "expected": 1200},
            "raw_scores_retained": False,
            "registered_model_count": 3,
            "registered_family_count": 6,
        },
        "decision": "no_release_authorization",
    }


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
        self.assertIn("Model-conditional public data", markdown)
        self.assertIn("1200 analyzer + 3 full Engine replays", markdown)
        self.assertIn("LLM proxy, not a generative LLM endpoint", markdown)
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
        mutations.append((known_report(), incomplete_model, "analyzer replay family is incomplete"))
        for known, model, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(summary_tool.PublicationSummaryError, message):
                    summary_tool.build_publication_summary(
                        known,
                        model,
                        known_report_sha256="1" * 64,
                        model_report_sha256="2" * 64,
                    )

    def test_complete_negative_acceptance_is_published_without_promotion(self) -> None:
        report = model_report()
        failed = next(
            value
            for value in report["repeated_validation"]["summaries"]
            if value["collector_model"] == "compact_transformer_llm_proxy"
            and value["variant_id"] == "raw_bins"
        )
        failed["clear_count"] = 109
        failed["clear_rate"] = 0.545
        failed["simultaneous_clopper_pearson_clear_rate_lower"] = 0.44943065755844724
        criterion = "all_six_simultaneous_clear_rate_lowers_meet_minimum"
        report["acceptance"]["criteria"][criterion] = False
        report["acceptance"]["passed"] = False
        result = summary_tool.build_publication_summary(
            known_report(),
            report,
            known_report_sha256="1" * 64,
            model_report_sha256="2" * 64,
        )
        self.assertEqual(result["status"], "controlled_passed_model_acceptance_not_met")
        self.assertFalse(result["model_backed"]["acceptance"]["passed"])
        self.assertEqual(result["model_backed"]["acceptance"]["failed_criteria"], [criterion])
        self.assertEqual(result["model_backed"]["headline"]["clear_rate_target_families"], 5)
        markdown = summary_tool.render_markdown(result)
        self.assertIn("Registered acceptance not met", markdown)
        self.assertIn("109/200", markdown)
        self.assertIn("CLEAR power FAIL", markdown)

    def test_generator_writes_all_three_artifacts_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            known_path = base / "known.json"
            model_path = base / "model.json"
            known_path.write_text(json.dumps(known_report()), encoding="utf-8")
            model_path.write_text(json.dumps(model_report()), encoding="utf-8")
            json_path = base / "publication" / "summary.json"
            markdown_path = base / "publication" / "results.md"
            svg_path = base / "publication" / "figure.svg"
            result = summary_tool.generate_artifacts(
                known_path, model_path, json_path, markdown_path, svg_path
            )
            self.assertEqual(result["summary_id"], summary_tool.SUMMARY_ID)
            self.assertEqual(json.loads(json_path.read_text())["summary_id"], summary_tool.SUMMARY_ID)
            self.assertIn("![Ceiling validation intervals](figure.svg)", markdown_path.read_text())
            self.assertIn("<svg", svg_path.read_text())

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
