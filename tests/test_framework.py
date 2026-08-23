from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from model_release_assurance.analyzers.attack import (
    AttackAnalyzer,
    clopper_pearson_lower,
    clopper_pearson_upper,
    wilson_lower,
)
from model_release_assurance.analyzers.controlled_inference import ControlledInferenceAnalyzer
from model_release_assurance.analyzers.dp import (
    DpAnalyzer,
    equal_prior_membership_ceiling,
    finite_secret_exact_guess_ceiling,
    membership_roc_ceiling,
)
from model_release_assurance.analyzers.tree import TreeLinkageAnalyzer
from model_release_assurance.audit import AuditStore
from model_release_assurance.decision import decision_game_sha256, decide_threat, population_scope_sha256
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import AnalyzerError
from model_release_assurance.integrity import (
    build_signed_manifest,
    generate_ed25519_keypair,
    sha256_file,
    verify_signed_manifest,
)
from model_release_assurance.models import (
    AssessmentRequest,
    AttackInput,
    ControlledInferenceInput,
    DpInput,
    EvidenceClass,
    EvidenceRecord,
    InterfaceContract,
    PolicyRule,
    PopulationSize,
    Realizability,
    ThreatContract,
    Verdict,
)
from model_release_assurance.portfolio import joint_uniform_linkage_value, joint_uniform_secret_guess_value


ROOT = Path(__file__).resolve().parents[1]


def load_example() -> dict:
    raw = json.loads((ROOT / "examples" / "request.json").read_text())
    raw["release"]["artifact_sha256"] = sha256_file(ROOT / "examples" / "artifacts" / "demo-tree.json")
    return raw


def make_paths_absolute(raw: dict) -> None:
    for analyzer in raw["analyzer_inputs"]:
        analyzer["provenance"]["source_path"] = str(
            ROOT / "examples" / analyzer["provenance"]["source_path"]
        )


class ContractTests(unittest.TestCase):
    def test_interactive_llm_requires_a_complete_versioned_protocol(self) -> None:
        with self.assertRaises(ValidationError):
            InterfaceContract.model_validate({
                "protocol_type": "interactive_llm",
                "access": "text",
            })
        raw = {
            "protocol_type": "interactive_llm",
            "access": "text",
            "outputs": ["text"],
            "query_budget": 100,
            "adaptive_queries": True,
            "llm_protocol": {
                "model_provider": "test provider",
                "model_identifier": "test model",
                "model_version": "2026-08-13",
                "tokenizer_sha256": "1" * 64,
                "decoding_parameters": {"temperature": 0.0},
                "system_prompt_sha256": "2" * 64,
                "memory_mode": "none",
                "logging_mode": "security_only",
                "provider_retention_days": 0,
                "maximum_session_tokens": 4096,
                "maximum_lifetime_queries": 100,
                "maximum_concurrent_sessions": 1,
                "reset_semantics": "fresh context per authenticated session",
                "update_policy": "versioned_reassessment_required",
                "valid_until": "2099-01-01T00:00:00Z",
            },
        }
        contract = InterfaceContract.model_validate(raw)
        self.assertEqual(contract.protocol_type, "interactive_llm")
        self.assertEqual(contract.access, "text")

        empty_decoding = json.loads(json.dumps(raw))
        empty_decoding["llm_protocol"]["decoding_parameters"] = {}
        with self.assertRaises(ValidationError):
            InterfaceContract.model_validate(empty_decoding)

        invalid_adapter = json.loads(json.dumps(raw))
        invalid_adapter["llm_protocol"]["adapter_sha256s"] = ["not-a-digest"]
        with self.assertRaises(ValidationError):
            InterfaceContract.model_validate(invalid_adapter)

        stateful_without_ttl = json.loads(json.dumps(raw))
        stateful_without_ttl["llm_protocol"]["memory_mode"] = "session"
        with self.assertRaises(ValidationError):
            InterfaceContract.model_validate(stateful_without_ttl)

        budget_mismatch = json.loads(json.dumps(raw))
        budget_mismatch["query_budget"] = 99
        with self.assertRaises(ValidationError):
            InterfaceContract.model_validate(budget_mismatch)

    def test_unknown_field_fails_closed(self) -> None:
        raw = load_example()
        raw["release"]["undeclared_control"] = True
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_generic_attack_cannot_create_an_interactive_llm_floor(self) -> None:
        raw = load_example()
        release = AssessmentRequest.model_validate(raw).release.model_copy(
            update={
                "interface": InterfaceContract.model_validate({
                    "protocol_type": "interactive_llm",
                    "access": "text",
                    "outputs": ["text"],
                    "query_budget": 100,
                    "adaptive_queries": True,
                    "llm_protocol": {
                        "model_provider": "test provider",
                        "model_identifier": "test model",
                        "model_version": "2026-08-13",
                        "tokenizer_sha256": "1" * 64,
                        "decoding_parameters": {"temperature": 0.0},
                        "system_prompt_sha256": "2" * 64,
                        "memory_mode": "none",
                        "logging_mode": "security_only",
                        "provider_retention_days": 0,
                        "maximum_session_tokens": 4096,
                        "maximum_lifetime_queries": 100,
                        "maximum_concurrent_sessions": 1,
                        "reset_semantics": "fresh context per authenticated session",
                        "update_policy": "versioned_reassessment_required",
                        "valid_until": "2099-01-01T00:00:00Z",
                    },
                })
            }
        )
        attack = AttackInput.model_validate(raw["analyzer_inputs"][2])
        threat = ThreatContract.model_validate(raw["threats"][1])
        with self.assertRaisesRegex(AnalyzerError, "dedicated transcript-bound LLM analyzer"):
            AttackAnalyzer().analyze(release, threat, attack)

    def test_tree_evidence_cannot_be_applied_to_another_model_family(self) -> None:
        raw = load_example()
        request = AssessmentRequest.model_validate(raw)
        release = request.release.model_copy(update={"model_family": "linear_generalized_linear"})
        with self.assertRaisesRegex(AnalyzerError, "tree-ensemble"):
            TreeLinkageAnalyzer().analyze(release, request.threats[0], request.analyzer_inputs[0])

    def test_linkage_requires_target_signal(self) -> None:
        raw = load_example()
        raw["threats"][0]["target_signal_source"] = None
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_exact_summary_adversary_profile_is_mandatory(self) -> None:
        raw = load_example()
        request = AssessmentRequest.model_validate(raw)
        self.assertTrue(all(
            threat.adversary_metadata_profile == "exact_database_feature_summaries_v1"
            for threat in request.threats
        ))
        raw["threats"][0]["adversary_metadata_profile"] = "public-schema-only"
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_unknown_analyzer_threat_fails(self) -> None:
        raw = load_example()
        raw["analyzer_inputs"][0]["threat_id"] = "missing"
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_unknown_population_scope_fails(self) -> None:
        raw = load_example()
        raw["threats"][0]["population_scope_id"] = "unknown-scope"
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_analyzer_population_scope_must_match_threat(self) -> None:
        raw = load_example()
        raw["population_scopes"].append({
            **raw["population_scopes"][0],
            "scope_id": "different-scope",
            "name": "Different defined cohort",
        })
        raw["analyzer_inputs"][0]["population_scope_id"] = "different-scope"
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_organization_population_is_supported(self) -> None:
        raw = load_example()
        raw["population_scopes"][0].update(
            unit_kind="organization",
            universe_definition="Registered companies in the declared programme as at the reference date.",
            size={
                "basis": "exact_registry",
                "lower_bound": 240,
                "point_estimate": 240,
                "upper_bound": 240,
                "source": "Demonstration organization register",
                "measured_at": "2026-01-01T00:00:00Z",
            },
        )
        raw["release"]["protected_unit"] = "organization"
        raw["analyzer_inputs"][1]["protected_unit"] = "organization"
        request = AssessmentRequest.model_validate(raw)
        self.assertEqual(request.population_scopes[0].unit_kind, "organization")
        self.assertEqual(request.population_scopes[0].size.point_estimate, 240)

    def test_population_size_bounds_must_be_coherent(self) -> None:
        with self.assertRaises(ValidationError):
            PopulationSize.model_validate({
                "basis": "bounded_estimate",
                "lower_bound": 100,
                "point_estimate": 80,
                "upper_bound": 120,
                "source": "invalid demonstration",
                "measured_at": "2026-01-01T00:00:00Z",
            })

    def test_evidence_classes_enforce_direction(self) -> None:
        context = load_example()["analyzer_inputs"][2]["evidence_context"]
        common = {
            **context,
            "evidence_id": "direction-test",
            "threat_id": "membership-person",
            "analyzer": "test",
            "coverage": "complete_interface",
            "metric": "equal_prior_membership_success",
            "value": 0.5,
            "realizability": "recipient_realizable",
        }
        with self.assertRaisesRegex(ValidationError, "screen evidence cannot"):
            EvidenceRecord.model_validate({
                **common,
                "evidence_class": "screen",
                "lower": 0.4,
                "can_block": True,
                "can_clear": False,
            })
        with self.assertRaisesRegex(ValidationError, "floor evidence cannot clear"):
            EvidenceRecord.model_validate({
                **common,
                "evidence_class": "floor",
                "lower": 0.4,
                "upper": 0.6,
                "can_block": True,
                "can_clear": True,
            })
        with self.assertRaisesRegex(ValidationError, "ceiling evidence cannot block"):
            EvidenceRecord.model_validate({
                **common,
                "evidence_class": "ceiling",
                "lower": 0.4,
                "upper": 0.6,
                "can_block": True,
                "can_clear": True,
            })
        with self.assertRaisesRegex(ValidationError, "auditor-only evidence cannot clear"):
            EvidenceRecord.model_validate({
                **common,
                "evidence_class": "exact",
                "lower": 0.5,
                "upper": 0.5,
                "realizability": "auditor_only",
                "can_block": False,
                "can_clear": True,
            })

    def test_policy_accepts_incremental_controlled_inference_metrics(self) -> None:
        for kind, metric in (
            ("attribute", "incremental_attribute_attack_success"),
            ("reconstruction", "incremental_reconstruction_success"),
        ):
            rule = PolicyRule.model_validate({
                "threat_id": f"{kind}-incremental",
                "kind": kind,
                "mandatory": True,
                "decision_metric": metric,
                "tolerance": 0.05,
                "tolerance_basis": "incremental",
            })
            self.assertEqual(rule.decision_metric, metric)

    def test_finite_secret_contract_requires_a_policy_bound_prior_cap(self) -> None:
        raw = {
            "threat_id": "attribute-secret",
            "kind": "attribute",
            "mandatory": True,
            "decision_metric": "finite_secret_exact_guess_success",
            "tolerance": 0.4,
            "tolerance_basis": "absolute",
        }
        with self.assertRaisesRegex(ValidationError, "maximum_secret_prior"):
            PolicyRule.model_validate(raw)
        rule = PolicyRule.model_validate({
            **raw,
            "metric_parameters": {"maximum_secret_prior": 0.4},
        })
        self.assertEqual(rule.metric_parameters["maximum_secret_prior"], 0.4)

    def test_finite_secret_dp_input_rejects_an_impossible_prior_cap(self) -> None:
        raw = load_example()["analyzer_inputs"][1]
        raw.update(
            secret_cardinality=4,
            maximum_secret_prior=0.2,
            pairwise_secret_relation_validated=True,
            secret_prior_bound_validated=True,
        )
        with self.assertRaisesRegex(ValidationError, "1 / secret_cardinality"):
            DpInput.model_validate(raw)


class EngineTests(unittest.TestCase):
    def test_end_to_end_clear(self) -> None:
        request = AssessmentRequest.model_validate(load_example())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        self.assertEqual(report.overall_verdict, "clear")
        linkage = next(d for d in report.decisions if d.threat_id == "linkage-person")
        self.assertEqual(linkage.verdict, Verdict.CLEAR)
        self.assertAlmostEqual(linkage.upper_bound, 0.25)

    def test_auditor_only_exactness_cannot_clear(self) -> None:
        raw = load_example()
        raw["threats"][0]["realizability"] = "auditor_only"
        raw["analyzer_inputs"][0]["recipient_has_target_signal"] = False
        request_for_hashes = AssessmentRequest.model_validate(raw)
        game_hash = decision_game_sha256(
            request_for_hashes.threats[0], request_for_hashes.population_scopes[0]
        )
        raw["analyzer_inputs"][0]["evidence_context"]["decision_game_sha256"] = game_hash
        make_paths_absolute(raw)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tree.json"
            source_raw = json.loads((ROOT / "examples" / "evidence" / "tree-linkage.json").read_text())
            source_raw["recipient_has_target_signal"] = False
            source_raw["evidence_context"]["decision_game_sha256"] = game_hash
            source.write_text(json.dumps(source_raw))
            raw["analyzer_inputs"][0]["provenance"]["source_path"] = str(source)
            raw["analyzer_inputs"][0]["provenance"]["source_sha256"] = sha256_file(source)
            request = AssessmentRequest.model_validate(raw)
            report = AssuranceEngine().assess(request, ROOT / "examples")
            decision = next(d for d in report.decisions if d.threat_id == "linkage-person")
            self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)

    def test_incomplete_dp_cannot_clear(self) -> None:
        raw = load_example()
        raw["analyzer_inputs"][1]["complete_pipeline"] = False
        make_paths_absolute(raw)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dp.json"
            source_raw = json.loads((ROOT / "examples" / "evidence" / "dp-accountant.json").read_text())
            source_raw["complete_pipeline"] = False
            source.write_text(json.dumps(source_raw))
            raw["analyzer_inputs"][1]["provenance"]["source_path"] = str(source)
            raw["analyzer_inputs"][1]["provenance"]["source_sha256"] = sha256_file(source)
            request = AssessmentRequest.model_validate(raw)
            report = AssuranceEngine().assess(request, ROOT / "examples")
            decision = next(d for d in report.decisions if d.threat_id == "membership-person")
            self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)

    def test_attack_floor_blocks(self) -> None:
        request = AssessmentRequest.model_validate(load_example())
        threat = request.threats[1]
        scope = request.population_scopes[0]
        floor = EvidenceRecord(
            **request.analyzer_inputs[2].evidence_context.model_dump(mode="python"),
            evidence_id="floor",
            threat_id=threat.threat_id,
            analyzer="attack",
            evidence_class=EvidenceClass.FLOOR,
            coverage="named_projection",
            metric="equal_prior_membership_success",
            value=0.9,
            lower=0.8,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=True,
        )
        self.assertEqual(
            decide_threat(threat, scope, request.release, (floor,), request.policy.policy_sha256).verdict,
            Verdict.BLOCK,
        )

    def test_hash_mismatch_fails(self) -> None:
        raw = load_example()
        raw["release"]["artifact_sha256"] = "0" * 64
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaises(Exception):
            AssuranceEngine().assess(request, ROOT / "examples")

    def test_evidence_hash_mismatch_fails(self) -> None:
        raw = load_example()
        raw["analyzer_inputs"][0]["provenance"]["source_sha256"] = "0" * 64
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaises(Exception):
            AssuranceEngine().assess(request, ROOT / "examples")

    def test_claim_must_match_bound_evidence_source(self) -> None:
        raw = load_example()
        raw["analyzer_inputs"][0]["observations"] = ["L1", "L2", "L3", "L4"]
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaises(Exception):
            AssuranceEngine().assess(request, ROOT / "examples")

        raw = load_example()
        raw["analyzer_inputs"][2]["provenance"]["bound_fields"].remove("confidence")
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaisesRegex(Exception, "framework-owned analyzer payload"):
            AssuranceEngine().assess(request, ROOT / "examples")

    def test_source_observed_context_cannot_be_rebound(self) -> None:
        raw = load_example()
        make_paths_absolute(raw)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "attack.json"
            source_raw = json.loads(
                (ROOT / "examples" / "evidence" / "attack-counts.json").read_text()
            )
            source_raw["evidence_context"]["artifact_sha256"] = "0" * 64
            source.write_text(json.dumps(source_raw))
            raw["analyzer_inputs"][2]["evidence_context"]["artifact_sha256"] = "0" * 64
            raw["analyzer_inputs"][2]["provenance"]["source_path"] = str(source)
            raw["analyzer_inputs"][2]["provenance"]["source_sha256"] = sha256_file(source)
            request = AssessmentRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "evidence context does not match"):
                AssuranceEngine().assess(request, ROOT / "examples")

    def test_future_source_observation_is_rejected(self) -> None:
        raw = load_example()
        make_paths_absolute(raw)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "attack.json"
            source_raw = json.loads(
                (ROOT / "examples" / "evidence" / "attack-counts.json").read_text()
            )
            source_raw["evidence_context"]["observed_at"] = "2098-01-01T00:00:00Z"
            source.write_text(json.dumps(source_raw))
            raw["analyzer_inputs"][2]["evidence_context"]["observed_at"] = "2098-01-01T00:00:00Z"
            raw["analyzer_inputs"][2]["provenance"]["source_path"] = str(source)
            raw["analyzer_inputs"][2]["provenance"]["source_sha256"] = sha256_file(source)
            request = AssessmentRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "future"):
                AssuranceEngine().assess(request, ROOT / "examples")

    def test_request_cannot_weaken_policy_tolerance(self) -> None:
        raw = load_example()
        raw["threats"][0]["tolerance"] = 0.9
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaises(Exception):
            AssuranceEngine().assess(request, ROOT / "examples")

    def test_request_cannot_omit_mandatory_policy_threat(self) -> None:
        raw = load_example()
        raw["threats"] = [raw["threats"][0]]
        raw["analyzer_inputs"] = [item for item in raw["analyzer_inputs"] if item["threat_id"] == "linkage-person"]
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaises(Exception):
            AssuranceEngine().assess(request, ROOT / "examples")

    def test_policy_hash_mismatch_fails(self) -> None:
        raw = load_example()
        raw["policy"]["policy_sha256"] = "0" * 64
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaises(Exception):
            AssuranceEngine().assess(request, ROOT / "examples")


class MathTests(unittest.TestCase):
    def test_joint_partition_refines(self) -> None:
        first = {"1": "a", "2": "a", "3": "b", "4": "b"}
        second = {"1": "x", "2": "y", "3": "x", "4": "y"}
        self.assertEqual(joint_uniform_linkage_value((first,)), 0.5)
        self.assertEqual(joint_uniform_linkage_value((first, second)), 1.0)

    def test_xor_marginals_are_null_but_joint_transcript_reveals_secret(self) -> None:
        secrets = {"x0r0": "0", "x0r1": "0", "x1r0": "1", "x1r1": "1"}
        first = {"x0r0": "0", "x0r1": "1", "x1r0": "0", "x1r1": "1"}
        second = {"x0r0": "0", "x0r1": "1", "x1r0": "1", "x1r1": "0"}
        self.assertEqual(joint_uniform_secret_guess_value(secrets, (first,)), 0.5)
        self.assertEqual(joint_uniform_secret_guess_value(secrets, (second,)), 0.5)
        self.assertEqual(joint_uniform_secret_guess_value(secrets, (first, second)), 1.0)

    def test_wilson_lower_is_conservative(self) -> None:
        lower = wilson_lower(520, 1000, 0.95)
        self.assertLess(lower, 0.52)
        self.assertGreater(lower, 0.45)

    def test_exact_clopper_pearson_low_fpr_bounds(self) -> None:
        self.assertAlmostEqual(
            clopper_pearson_upper(0, 4000, 0.975),
            1.0 - 0.025 ** (1.0 / 4000),
            places=12,
        )
        self.assertAlmostEqual(
            clopper_pearson_lower(50, 4000, 0.975),
            0.009291587489802085,
            places=12,
        )

    def test_dp_probability_bounds_are_stable_for_large_epsilon(self) -> None:
        roc, first, second = membership_roc_ceiling(1000.0, 1e-6, 1e-3)
        self.assertEqual(first, 1.0)
        self.assertEqual(second, 1.0)
        self.assertEqual(roc, 1.0)
        self.assertEqual(equal_prior_membership_ceiling(1000.0, 1e-6), 1.0)
        self.assertEqual(
            finite_secret_exact_guess_ceiling(1000.0, 1e-6, 0.25),
            1.0,
        )

    def test_finite_secret_dp_ceiling_generalizes_the_uniform_bound(self) -> None:
        epsilon = 0.2
        delta = 1e-6
        uniform = finite_secret_exact_guess_ceiling(epsilon, delta, 0.25)
        old_uniform_formula = (
            math.exp(epsilon) + 3 * delta
        ) / (
            math.exp(epsilon) + 3
        )
        self.assertAlmostEqual(uniform, old_uniform_formula, places=14)
        self.assertGreater(
            finite_secret_exact_guess_ceiling(epsilon, delta, 0.7),
            uniform,
        )

    def test_finite_secret_dp_ceiling_requires_pairwise_dp_and_validated_prior(self) -> None:
        raw = load_example()
        release = AssessmentRequest.model_validate(raw).release
        threat_raw = raw["threats"][0]
        threat_raw.update(
            kind="attribute",
            secret="one of four registered secret states",
            prior="registered population prior with maximum mass at most 0.4",
            success_metric="exact secret-state recovery",
            decision_metric="finite_secret_exact_guess_success",
            metric_parameters={"maximum_secret_prior": 0.4},
            tolerance=0.5,
            tolerance_basis="absolute",
            candidate_set=None,
            target_signal_source=None,
            realizability="not_applicable",
        )
        threat = ThreatContract.model_validate(threat_raw)
        dp_raw = raw["analyzer_inputs"][1]
        dp_raw.update(
            threat_id=threat.threat_id,
            fpr=None,
            secret_cardinality=4,
            maximum_secret_prior=0.4,
            pairwise_secret_relation_validated=True,
            secret_prior_bound_validated=True,
        )
        value = DpInput.model_validate(dp_raw)
        evidence = DpAnalyzer().analyze(release, threat, value)[0]
        self.assertEqual(evidence.evidence_class, EvidenceClass.CEILING)
        self.assertTrue(evidence.can_clear)
        self.assertAlmostEqual(
            evidence.upper,
            finite_secret_exact_guess_ceiling(value.epsilon, value.delta, 0.4),
        )

        unvalidated = value.model_copy(update={"secret_prior_bound_validated": False})
        screen = DpAnalyzer().analyze(release, threat, unvalidated)[0]
        self.assertEqual(screen.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(screen.can_clear)

        excessive_prior = value.model_copy(update={"maximum_secret_prior": 0.5})
        mismatch = DpAnalyzer().analyze(release, threat, excessive_prior)[0]
        self.assertEqual(mismatch.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(mismatch.can_clear)

    def test_low_fpr_requires_conservative_attainment(self) -> None:
        raw = load_example()
        source = raw["analyzer_inputs"][2]
        source.update(
            metric="membership_tpr_at_fpr",
            false_positives=0,
            nonmember_trials=100,
            target_fpr=0.001,
        )
        attack = AttackInput.model_validate(source)
        release = AssessmentRequest.model_validate(load_example()).release
        threat_raw = load_example()["threats"][1]
        threat_raw["decision_metric"] = "membership_tpr_at_fpr"
        threat_raw["metric_parameters"] = {"target_fpr": 0.001}
        threat = ThreatContract.model_validate(threat_raw)
        evidence = AttackAnalyzer().analyze(release, threat, attack)[0]
        self.assertEqual(evidence.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(evidence.details["operating_point_attained"])
        self.assertAlmostEqual(evidence.details["per_comparison_confidence"], 0.975)
        self.assertEqual(evidence.details["bounds_per_comparison"], 2)
        self.assertEqual(evidence.details["simultaneous_bound_count"], 2)

    def test_controlled_attribute_gap_uses_paired_cells_and_multiplicity(self) -> None:
        raw = load_example()
        release = AssessmentRequest.model_validate(raw).release
        threat_raw = raw["threats"][0]
        threat_raw.update(
            kind="attribute",
            secret="sensitive attribute",
            decision_metric="incremental_attribute_attack_success",
            tolerance_basis="incremental",
            tolerance=0.01,
            candidate_set=None,
            target_signal_source=None,
            realizability="not_applicable",
        )
        threat = ThreatContract.model_validate(threat_raw)
        provenance = raw["analyzer_inputs"][2]["provenance"]
        value = ControlledInferenceInput.model_validate({
            "analyzer": "controlled_inference",
            "threat_id": threat.threat_id,
            "population_scope_id": threat.population_scope_id,
            "attack_name": "paired-attribute",
            "metric": "incremental_attribute_attack_success",
            "trials": 4000,
            "combined_successes": 2400,
            "baseline_successes": 2000,
            "combined_only_successes": 500,
            "baseline_only_successes": 100,
            "confidence_family": 0.95,
            "comparison_family_size": 16,
            "attack_training_disjoint": True,
            "audit_disjoint": True,
            "raw_paired_counts_retained": True,
            "comparator_same_side_information": True,
            "secret_and_metric_pre_registered": True,
            "ground_truth_verified": True,
            "success_definition": "exact attribute recovery",
            "evidence_context": raw["analyzer_inputs"][2]["evidence_context"],
            "provenance": provenance,
        })
        evidence = ControlledInferenceAnalyzer().analyze(release, threat, value)[0]
        self.assertEqual(evidence.evidence_class, EvidenceClass.FLOOR)
        self.assertAlmostEqual(evidence.value, 0.1)
        self.assertGreater(evidence.lower, 0.0)
        self.assertAlmostEqual(evidence.baseline, 0.5)

    def test_reconstruction_floor_requires_training_membership_verification(self) -> None:
        raw = load_example()
        release = AssessmentRequest.model_validate(raw).release
        threat_raw = raw["threats"][0]
        threat_raw.update(
            kind="reconstruction",
            secret="training-record feature",
            decision_metric="incremental_reconstruction_success",
            tolerance_basis="incremental",
            tolerance=0.01,
            candidate_set=None,
            target_signal_source=None,
            realizability="not_applicable",
        )
        threat = ThreatContract.model_validate(threat_raw)
        value = ControlledInferenceInput.model_validate({
            "analyzer": "controlled_inference",
            "threat_id": threat.threat_id,
            "population_scope_id": threat.population_scope_id,
            "attack_name": "partial-reconstruction",
            "metric": "incremental_reconstruction_success",
            "trials": 100,
            "combined_successes": 70,
            "baseline_successes": 50,
            "combined_only_successes": 25,
            "baseline_only_successes": 5,
            "attack_training_disjoint": True,
            "audit_disjoint": True,
            "raw_paired_counts_retained": True,
            "comparator_same_side_information": True,
            "secret_and_metric_pre_registered": True,
            "ground_truth_verified": True,
            "training_membership_verified": False,
            "success_definition": "within predeclared feature distance",
            "evidence_context": raw["analyzer_inputs"][2]["evidence_context"],
            "provenance": raw["analyzer_inputs"][2]["provenance"],
        })
        evidence = ControlledInferenceAnalyzer().analyze(release, threat, value)[0]
        self.assertEqual(evidence.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(evidence.can_block)


class IntegrityTests(unittest.TestCase):
    def test_manifest_and_audit_chain(self) -> None:
        request = AssessmentRequest.model_validate(load_example())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            private = temp / "private.pem"
            public = temp / "public.pem"
            generate_ed25519_keypair(private, public)
            manifest = build_signed_manifest(report, request, private)
            verify_signed_manifest(manifest, report, public)
            mismatched_request = request.model_copy(
                update={"release": request.release.model_copy(update={"owner": "another owner"})}
            )
            with self.assertRaisesRegex(Exception, "assessment request"):
                build_signed_manifest(report, mismatched_request, private)
            mismatched_expiry = manifest.model_copy(update={"expires_at": report.created_at})
            with self.assertRaisesRegex(Exception, "expiry"):
                verify_signed_manifest(mismatched_expiry, report, public)
            mismatched_creation = manifest.model_copy(update={"created_at": report.created_at.replace(year=2098)})
            with self.assertRaisesRegex(Exception, "created_at"):
                verify_signed_manifest(mismatched_creation, report, public)
            tampered = manifest.model_copy(update={"artifact_sha256": "0" * 64})
            with self.assertRaises(Exception):
                verify_signed_manifest(tampered, report, public)
            store = AuditStore(temp / "audit.sqlite3")
            store.append_report(report)
            self.assertEqual(store.verify_chain(), 1)
            connection = sqlite3.connect(temp / "audit.sqlite3")
            try:
                connection.execute("UPDATE audit_events SET payload_json = '{}' WHERE sequence = 1")
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(Exception):
                store.verify_chain()


if __name__ == "__main__":
    unittest.main()
