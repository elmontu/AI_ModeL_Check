"""Adversarial contract/replay regressions, not proof of external evidence truth."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from model_release_assurance.decision import decide_overall
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import (
    build_signed_manifest,
    canonical_json_bytes,
    generate_ed25519_keypair,
    sha256_bytes,
    sha256_file,
    validate_report_against_policy,
    validate_report_against_request,
    verify_signed_manifest,
)
from model_release_assurance.models import (
    AssessmentReport,
    AssessmentRequest,
    AttackBatteryStatus,
    EvidenceRecord,
    OverallVerdict,
    PolicyBundle,
    SignedManifest,
    ThreatDecision,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class CounterproofContractRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request = AssessmentRequest.model_validate_json(
            (EXAMPLES / "request.json").read_text(encoding="utf-8")
        )
        cls.policy = PolicyBundle.model_validate_json(
            (EXAMPLES / "policy.json").read_text(encoding="utf-8")
        )
        cls.policy_sha256 = sha256_file(EXAMPLES / "policy.json")
        cls.report = AssuranceEngine().assess(cls.request, EXAMPLES)

    def omitted_report(self) -> AssessmentReport:
        raw = self.report.model_dump(mode="json")
        removed = raw["decisions"].pop()["threat_id"]
        raw["evidence"] = [r for r in raw["evidence"] if r["threat_id"] != removed]
        raw["overall_verdict"] = decide_overall(tuple(
            ThreatDecision.model_validate(r) for r in raw["decisions"]
        )).value
        return AssessmentReport.model_validate(raw)

    def test_valid_engine_report_replays_with_request_and_active_policy(self) -> None:
        validate_report_against_request(self.report, self.request)
        validate_report_against_policy(
            self.report, self.policy, policy_sha256=self.policy_sha256,
            request=self.request,
        )
        self.assertEqual(self.report.schema_version, "6.0")

    def test_required_battery_cannot_claim_satisfaction_without_completed_attacks(self) -> None:
        with self.assertRaisesRegex(ValidationError, "complete every required attack"):
            AttackBatteryStatus(
                mode="required", requirement_id="required-one",
                required_attack_ids=("attack-one",), satisfied=True,
            )

    def test_required_battery_cannot_claim_unknown_completed_attack(self) -> None:
        with self.assertRaisesRegex(ValidationError, "belong to the required battery"):
            AttackBatteryStatus(
                mode="required", requirement_id="required-one",
                required_attack_ids=("attack-one",), completed_attack_ids=("attack-two",),
                passing_positive_control_ids=("control-one",), satisfied=True,
            )

    def test_completed_battery_requires_positive_control_identifiers(self) -> None:
        with self.assertRaisesRegex(ValidationError, "passing positive-control"):
            AttackBatteryStatus(
                mode="required", requirement_id="required-one",
                required_attack_ids=("attack-one",), completed_attack_ids=("attack-one",),
                satisfied=True,
            )

    def test_waived_and_prohibited_batteries_cannot_smuggle_execution_claims(self) -> None:
        for mode in ("waived", "ceiling_prohibited"):
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                AttackBatteryStatus(
                    mode=mode, satisfied=mode == "waived",
                    waiver_reason="Explicit policy waiver" if mode == "waived" else None,
                    completed_attack_ids=("attack-one",),
                )

    def test_empty_clear_report_is_not_a_complete_assessment(self) -> None:
        raw = self.report.model_dump(mode="json")
        raw.update(decisions=[], evidence=[], overall_verdict="clear")
        with self.assertRaises(ValidationError):
            AssessmentReport.model_validate(raw)

    def test_aggregate_verdict_must_equal_decision_reduction(self) -> None:
        raw = self.report.model_dump(mode="json")
        raw["overall_verdict"] = "block"
        with self.assertRaisesRegex(ValidationError, "overall verdict"):
            AssessmentReport.model_validate(raw)

    def test_population_scope_hashes_bind_content_not_only_identifiers(self) -> None:
        raw = self.report.model_dump(mode="json")
        scope = next(iter(raw["population_scope_sha256s"]))
        raw["population_scope_sha256s"][scope] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "scope hash does not match its content"):
            AssessmentReport.model_validate(raw)

    def test_decision_display_must_not_hide_an_exact_probability(self) -> None:
        raw = self.report.decisions[0].model_dump(mode="json")
        raw["lower_bound"] = 0.0  # outward but materially different from exact 1/4
        with self.assertRaisesRegex(ValidationError, "agree with exact bounds"):
            ThreatDecision.model_validate(raw)

    def test_evidence_display_must_not_hide_an_exact_probability(self) -> None:
        raw = self.report.evidence[0].model_dump(mode="json")
        raw["exact_lower"] = {"numerator": 1, "denominator": 2}
        raw["exact_upper"] = {"numerator": 1, "denominator": 2}
        raw["lower"] = 0.0
        with self.assertRaisesRegex(ValidationError, "agree with its exact bound"):
            EvidenceRecord.model_validate(raw)

    def test_clear_verdict_cannot_contradict_exact_threshold(self) -> None:
        raw = self.report.decisions[0].model_dump(mode="json")
        raw["tolerance"] = 0.1
        with self.assertRaisesRegex(ValidationError, "floor above tolerance"):
            ThreatDecision.model_validate(raw)

    def test_request_replay_rejects_omitted_threat_even_if_report_is_self_consistent(self) -> None:
        with self.assertRaisesRegex(IntegrityError, "threat roster"):
            validate_report_against_request(self.omitted_report(), self.request)

    def test_signing_rejects_omission_before_accessing_private_key(self) -> None:
        with self.assertRaisesRegex(IntegrityError, "threat roster"):
            build_signed_manifest(self.omitted_report(), self.request, Path("missing-key.pem"))

    def test_policy_replay_rejects_missing_mandatory_threat(self) -> None:
        with self.assertRaisesRegex(IntegrityError, "threat roster"):
            validate_report_against_policy(
                self.omitted_report(), self.policy, policy_sha256=self.policy_sha256,
            )

    def test_request_replay_rejects_self_consistent_but_fabricated_reduction(self) -> None:
        raw = self.report.model_dump(mode="json")
        raw["decisions"][0]["lower_bound"] = 0.1
        raw["decisions"][0]["lower_bound_fraction"] = {"numerator": 1, "denominator": 10}
        forged = AssessmentReport.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "deterministic evidence reduction"):
            validate_report_against_request(forged, self.request)

    def test_request_replay_rejects_changed_game(self) -> None:
        raw = self.report.model_dump(mode="json")
        raw["decisions"][0]["decision_game_sha256"] = "0" * 64
        forged = AssessmentReport.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "requested decision game"):
            validate_report_against_request(forged, self.request)

    def test_request_replay_rejects_changed_mandatory_status(self) -> None:
        raw = self.report.model_dump(mode="json")
        raw["decisions"][0]["mandatory"] = False
        forged = AssessmentReport.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "deterministic evidence reduction"):
            validate_report_against_request(forged, self.request)

    def test_request_replay_rejects_mutated_evidence_details(self) -> None:
        raw = self.report.model_dump(mode="json")
        raw["evidence"][0]["details"]["invented_claim"] = "executed"
        forged = AssessmentReport.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "evidence differs"):
            validate_report_against_request(forged, self.request)

    def test_request_context_mismatch_cannot_be_hidden_as_excluded_evidence(self) -> None:
        raw = self.request.model_dump(mode="json")
        raw["analyzer_inputs"][0]["evidence_context"]["decision_game_sha256"] = "0" * 64
        changed = AssessmentRequest.model_validate(raw)
        report = self.report.model_copy(update={
            "request_sha256": sha256_bytes(canonical_json_bytes(changed)),
        })
        with self.assertRaisesRegex(IntegrityError, "evidence context"):
            validate_report_against_request(report, changed)

    def test_model_copy_does_not_bypass_validation_at_signing_boundary(self) -> None:
        forged = self.report.model_copy(update={"overall_verdict": OverallVerdict.BLOCK})
        with self.assertRaisesRegex(IntegrityError, "contract is invalid"):
            build_signed_manifest(forged, self.request, Path("missing-key.pem"))

    def test_future_report_is_rejected(self) -> None:
        forged = self.report.model_copy(update={"created_at": self.report.created_at + timedelta(days=1)})
        with self.assertRaisesRegex(IntegrityError, "future"):
            validate_report_against_request(forged, self.request)

    def test_expired_report_policy_is_rejected(self) -> None:
        forged = self.report.model_copy(update={"policy_expires_at": self.report.created_at})
        with self.assertRaisesRegex(IntegrityError, "expired"):
            validate_report_against_request(forged, self.request)

    def test_report_cannot_predate_evidence(self) -> None:
        earliest = min(record.observed_at for record in self.report.evidence)
        forged = self.report.model_copy(update={"created_at": earliest - timedelta(minutes=6)})
        with self.assertRaisesRegex(IntegrityError, "predates its evidence"):
            validate_report_against_request(forged, self.request)

    def test_policy_validator_checks_threshold_even_with_matching_reference_hash(self) -> None:
        raw = self.policy.model_dump(mode="json")
        raw["rules"][0]["tolerance"] = 0.99
        changed = PolicyBundle.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "changes policy field tolerance"):
            validate_report_against_policy(
                self.report, changed, policy_sha256=self.policy_sha256,
                request=self.request,
            )

    def test_policy_validator_checks_finite_game_content_with_request_context(self) -> None:
        raw = self.policy.model_dump(mode="json")
        raw["rules"][0]["finite_game"]["states"][0]["secret_value_definition"] += " changed"
        changed = PolicyBundle.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "changes policy field finite_game"):
            validate_report_against_policy(
                self.report, changed, policy_sha256=self.policy_sha256,
                request=self.request,
            )

    def test_policy_validator_recomputes_battery_controls_at_policy_threshold(self) -> None:
        raw = self.policy.model_dump(mode="json")
        raw["attack_battery_requirements"][0]["minimum_positive_control_detection_lower_bound"] = 0.999
        changed = PolicyBundle.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "battery differs from deterministic policy replay"):
            validate_report_against_policy(
                self.report, changed, policy_sha256=self.policy_sha256,
                request=self.request,
            )

    def test_policy_validator_checks_worker_acceptance_with_request_context(self) -> None:
        raw = self.policy.model_dump(mode="json")
        raw["attack_battery_requirements"][0]["accepted_worker_implementation_sha256s"] = ["0" * 64]
        changed = PolicyBundle.model_validate(raw)
        with self.assertRaisesRegex(IntegrityError, "worker implementation digest"):
            validate_report_against_policy(
                self.report, changed, policy_sha256=self.policy_sha256,
                request=self.request,
            )

    def test_manifest_v4_roundtrip_replays_supplied_original_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private, public = Path(directory) / "private.pem", Path(directory) / "public.pem"
            generate_ed25519_keypair(private, public)
            manifest = build_signed_manifest(self.report, self.request, private)
            self.assertEqual(manifest.schema_version, "4.0")
            verify_signed_manifest(manifest, self.report, public, request=self.request)
            old = manifest.model_dump(mode="json")
            old["schema_version"] = "3.0"
            with self.assertRaises(ValidationError):
                SignedManifest.model_validate(old)
            with self.assertRaisesRegex(IntegrityError, "manifest contract is invalid"):
                verify_signed_manifest(
                    manifest.model_copy(update={"schema_version": "3.0"}), self.report, public,
                )


if __name__ == "__main__":
    unittest.main()
