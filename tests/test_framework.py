from __future__ import annotations

import json
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
from model_release_assurance.audit import AuditStore
from model_release_assurance.decision import decision_game_sha256, decide_threat, population_scope_sha256
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import (
    build_signed_manifest,
    canonical_json_bytes,
    generate_ed25519_keypair,
    sha256_bytes,
    sha256_file,
    verify_signed_manifest,
)
from model_release_assurance.models import (
    AssessmentRequest,
    AttackInput,
    ControlledInferenceInput,
    EvidenceClass,
    EvidenceRecord,
    InterfaceContract,
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
    raw["policy"]["policy_path"] = str(ROOT / "examples" / raw["policy"]["policy_path"])
    raw["release"]["artifact_path"] = str(ROOT / "examples" / raw["release"]["artifact_path"])
    for analyzer in raw["analyzer_inputs"]:
        analyzer["provenance"]["source_path"] = str(
            ROOT / "examples" / analyzer["provenance"]["source_path"]
        )


class ContractTests(unittest.TestCase):
    def test_interactive_llm_requires_a_complete_versioned_protocol(self) -> None:
        with self.assertRaises(ValidationError):
            InterfaceContract.model_validate({
                "protocol_type": "interactive_llm",
                "access": "score",
            })
        contract = InterfaceContract.model_validate({
            "protocol_type": "interactive_llm",
            "access": "score",
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
        self.assertEqual(contract.protocol_type, "interactive_llm")

    def test_unknown_field_fails_closed(self) -> None:
        raw = load_example()
        raw["release"]["undeclared_control"] = True
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

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
        make_paths_absolute(raw)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tree.json"
            source_raw = json.loads((ROOT / "examples" / "evidence" / "tree-linkage.json").read_text())
            source_raw["recipient_has_target_signal"] = False
            source.write_text(json.dumps(source_raw))
            raw["analyzer_inputs"][0]["provenance"]["source_path"] = str(source)
            raw["analyzer_inputs"][0]["provenance"]["source_sha256"] = sha256_file(source)
            request = AssessmentRequest.model_validate(raw)
            report = AssuranceEngine().assess(request, ROOT)
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
            report = AssuranceEngine().assess(request, ROOT)
            decision = next(d for d in report.decisions if d.threat_id == "membership-person")
            self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)

    def test_attack_floor_blocks(self) -> None:
        request = AssessmentRequest.model_validate(load_example())
        threat = request.threats[1]
        scope = request.population_scopes[0]
        interface_hash = sha256_bytes(canonical_json_bytes(request.release.interface))
        floor = EvidenceRecord(
            evidence_id="floor",
            threat_id=threat.threat_id,
            analyzer="attack",
            evidence_class=EvidenceClass.FLOOR,
            coverage="named_projection",
            population_scope_id=scope.scope_id,
            population_scope_sha256=population_scope_sha256(scope),
            decision_game_sha256=decision_game_sha256(threat, scope),
            interface_sha256=interface_hash,
            artifact_sha256=request.release.artifact_sha256,
            metric="equal_prior_membership_success",
            value=0.9,
            lower=0.8,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=True,
        )
        self.assertEqual(decide_threat(threat, scope, request.release, (floor,)).verdict, Verdict.BLOCK)

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
            manifest = build_signed_manifest(report, request.release, private)
            verify_signed_manifest(manifest, report, public)
            tampered = manifest.model_copy(update={"artifact_sha256": "0" * 64})
            with self.assertRaises(Exception):
                verify_signed_manifest(tampered, report, public)
            store = AuditStore(temp / "audit.sqlite3")
            store.append_report(report)
            self.assertEqual(store.verify_chain(), 1)
            with sqlite3.connect(temp / "audit.sqlite3") as connection:
                connection.execute("UPDATE audit_events SET payload_json = '{}' WHERE sequence = 1")
                connection.commit()
            with self.assertRaises(Exception):
                store.verify_chain()


if __name__ == "__main__":
    unittest.main()
