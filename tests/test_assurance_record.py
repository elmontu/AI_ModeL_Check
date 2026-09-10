from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from model_release_assurance.assurance_record import (
    AssuranceScope, AssuranceVerdict, build_assurance_record, gate_assurance_record,
    sign_assurance_record, sign_residual_risk_acceptance, declared_export_channels,
)
from model_release_assurance.cli import main
from model_release_assurance.decision import decide_overall, decide_threat
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import generate_ed25519_keypair, signer_key_id
from model_release_assurance.models import AssessmentRequest, EvidenceClass
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]


def scope_for(request):
    threats = [t.threat_id for t in request.threats]
    inventory = declared_export_channels(request.release.interface)
    exported = [name for name, visible in inventory.items() if visible]
    return AssuranceScope.model_validate({
        "scope_id": "unit-approved-scope", "adversary": {
            "access_levels": [str(request.release.interface.access)],
            "auxiliary_knowledge": {t.threat_id: list(t.side_information) for t in request.threats},
            "metadata_profiles": {t.threat_id: t.adversary_metadata_profile for t in request.threats},
            "query_budget": request.release.interface.query_budget, "adaptive_queries": request.release.interface.adaptive_queries,
            "joint_transcript_description": "All declared export observations considered jointly under the registered games.",
        },
        "declared_scenario_ids": ["scenario-" + t for t in threats],
        "scenarios": [{"scenario_id": "scenario-" + t, "threat_id": t,
                       "description": "Declared finite unit-test adversary cell", "channel_ids": exported} for t in threats],
        "out_of_scope": [],
        "channels": [{"channel_id": c, "exported": visible, "threat_ids": threats if visible else [],
                      "reason": "Explicitly inventoried test export surface"}
                     for c, visible in inventory.items()],
        "residual_risk_acceptance_permitted": True,
        "approved_at": "2026-01-01T00:00:00Z", "expires_at": "2098-01-01T00:00:00Z",
    })


class AssuranceRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = AssessmentRequest.model_validate_json((ROOT / "examples/request.json").read_bytes())
        cls.report = AssuranceEngine().assess(cls.request, ROOT / "examples")
        cls.policy_bytes = (ROOT / "examples" / cls.request.policy.policy_path).read_bytes()
        cls.scope = scope_for(cls.request)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.private, self.public = self.base / "test-private.pem", self.base / "test-public.pem"
        generate_ed25519_keypair(self.private, self.public)
        key = serialization.load_pem_public_key(self.public.read_bytes())
        self.trust = {signer_key_id(key): self.public}

    def build(self, report=None, scope=None, **kwargs):
        return build_assurance_record(self.request, report or self.report, scope or self.scope,
                                      policy_bytes=self.policy_bytes, **kwargs)

    def gate(self, signed, **kwargs):
        return gate_assurance_record(signed, self.request, self.report, self.scope,
            policy_bytes=self.policy_bytes, trusted_record_keys=self.trust, **kwargs)

    def test_real_assessment_full_semantic_replay_and_signed_gate(self):
        record = self.build()
        self.assertEqual(record.verdict, AssuranceVerdict.RELEASE)
        self.assertTrue(all(t.ceiling.as_fraction() <= t.threshold.as_fraction() for t in record.threats))
        for threat in record.threats:
            self.assertEqual(threat.gap.as_fraction(), threat.ceiling.as_fraction() - threat.floor.as_fraction())
        result = self.gate(sign_assurance_record(record, self.private))
        self.assertTrue(result.recommendation_passed)
        self.assertFalse(result.authorization_eligible)

    def test_record_signature_tampering_fails_closed(self):
        signed = sign_assurance_record(self.build(), self.private)
        altered = signed.model_copy(update={"record": signed.record.model_copy(update={"release_id": "wrong-release"})})
        self.assertFalse(self.gate(altered).recommendation_passed)

    def test_bad_and_untrusted_signatures_fail_closed(self):
        signed = sign_assurance_record(self.build(), self.private)
        self.assertEqual(self.gate(signed.model_copy(update={"signature_b64": "AAAA"})).verdict, AssuranceVerdict.BLOCK)
        result = gate_assurance_record(signed, self.request, self.report, self.scope,
            policy_bytes=self.policy_bytes, trusted_record_keys={})
        self.assertFalse(result.recommendation_passed)

    def test_freshly_signed_forged_interval_still_fails_semantic_replay(self):
        record = self.build()
        wrong = record.threats[0].model_copy(update={"evidence_ids": ("invented-evidence",)})
        forged = record.model_copy(update={"threats": (wrong,) + record.threats[1:]})
        self.assertFalse(self.gate(sign_assurance_record(forged, self.private)).recommendation_passed)

    def test_policy_substitution_and_missing_policy_bytes_fail(self):
        with self.assertRaises(ValueError):
            build_assurance_record(self.request, self.report, self.scope, policy_bytes=b"{}")

    def test_uncovered_scenario_and_duplicate_ownership_rejected(self):
        raw = self.scope.model_dump(mode="json")
        raw["declared_scenario_ids"].append("unassigned")
        with self.assertRaises(ValidationError):
            AssuranceScope.model_validate(raw)
        raw = self.scope.model_dump(mode="json")
        raw["out_of_scope"].append({"scenario_id": raw["scenarios"][0]["scenario_id"], "reason": "Must not be excluded and included at once"})
        with self.assertRaises(ValidationError):
            AssuranceScope.model_validate(raw)

    def test_reasoned_exclusion_is_explicit_not_silently_dropped(self):
        raw = self.scope.model_dump(mode="json")
        raw["declared_scenario_ids"].append("external-physical-theft")
        raw["out_of_scope"].append({"scenario_id": "external-physical-theft", "reason": "Physical custody is outside this explicitly digital-observation game"})
        scoped = AssuranceScope.model_validate(raw)
        self.assertEqual(self.build(scope=scoped).verdict, AssuranceVerdict.RELEASE)
        self.assertFalse(self.build(scope=scoped).world_scope_truth_verified)

    def test_missing_channel_and_unmapped_threat_rejected_or_blocked(self):
        raw = self.scope.model_dump(mode="json")
        raw["channels"] = [c for c in raw["channels"] if c["channel_id"] != "logs"]
        with self.assertRaises(ValidationError):
            AssuranceScope.model_validate(raw)
        raw = self.scope.model_dump(mode="json")
        first = raw["scenarios"][0]["threat_id"]
        raw["scenarios"] = raw["scenarios"][:1]
        raw["declared_scenario_ids"] = [raw["scenarios"][0]["scenario_id"]]
        for channel in raw["channels"]:
            channel["threat_ids"] = [first] if channel["exported"] else []
        self.assertEqual(self.build(scope=AssuranceScope.model_validate(raw)).verdict, AssuranceVerdict.BLOCK)

    def test_declared_access_budget_and_live_channel_exclusion_cannot_be_weakened(self):
        raw = self.scope.model_dump(mode="json")
        raw["adversary"]["query_budget"] = 1
        self.assertEqual(self.build(scope=AssuranceScope.model_validate(raw)).verdict, AssuranceVerdict.BLOCK)
        raw = self.scope.model_dump(mode="json")
        raw["channels"] = [c for c in raw["channels"] if c["channel_id"] != "serialization"]
        for scenario in raw["scenarios"]:
            scenario["channel_ids"].remove("serialization")
        self.assertEqual(self.build(scope=AssuranceScope.model_validate(raw)).verdict, AssuranceVerdict.BLOCK)

    def test_future_or_expired_signed_record_never_passes(self):
        record = self.build()
        signed = sign_assurance_record(record, self.private)
        self.assertFalse(self.gate(signed, as_of=record.created_at-timedelta(seconds=1)).recommendation_passed)
        self.assertFalse(self.gate(signed, as_of=record.expires_at).recommendation_passed)

    def test_stronger_adversary_or_extra_channel_cannot_reuse_weaker_evidence(self):
        for mutation in ("access", "auxiliary", "profile", "channel", "export_state"):
            with self.subTest(mutation=mutation):
                raw = self.scope.model_dump(mode="json")
                if mutation == "access":
                    raw["adversary"]["access_levels"].append("original-training-data-and-host-memory")
                elif mutation == "auxiliary":
                    raw["adversary"]["auxiliary_knowledge"][self.request.threats[0].threat_id].append("All protected values and membership labels")
                elif mutation == "profile":
                    raw["adversary"]["metadata_profiles"][self.request.threats[0].threat_id] = "unrestricted-secrets"
                else:
                    name = "unregistered-original-training-dataset-download" if mutation == "channel" else "logs"
                    if mutation == "export_state":
                        raw["channels"] = [c for c in raw["channels"] if c["channel_id"] != name]
                    raw["channels"].append({"channel_id": name, "exported": True,
                        "threat_ids": [t.threat_id for t in self.request.threats], "reason": "Unsupported stronger export"})
                    for scenario in raw["scenarios"]:
                        scenario["channel_ids"].append(name)
                scope = AssuranceScope.model_validate(raw)
                record = self.build(scope=scope)
                self.assertEqual(record.verdict, AssuranceVerdict.BLOCK)
                result = gate_assurance_record(sign_assurance_record(record, self.private), self.request,
                    self.report, scope, policy_bytes=self.policy_bytes, trusted_record_keys=self.trust)
                self.assertFalse(result.recommendation_passed)

    def test_internally_inconsistent_verdict_cannot_be_signed(self):
        record = self.build()
        with self.assertRaises(ValidationError):
            sign_assurance_record(record.model_copy(update={"verdict": AssuranceVerdict.INCONCLUSIVE}), self.private)

    def _decision_layer_report(self, *, missing=False, blocking=False):
        """Isolate the new disposition algebra, NOT scientific import validity.

        Both import validators are deliberately mocked only in these unit tests.
        Real-import rejection and a real positive pipeline are tested above.
        """
        index = next(i for i,t in enumerate(self.request.threats) if t.kind.value == "membership")
        threat = self.request.threats[index]
        if blocking:
            threat = threat.model_copy(update={"tolerance": 0.4, "mandatory": False})
        evidence = tuple(e for e in self.report.evidence
                         if e.threat_id != threat.threat_id or (not missing and e.evidence_class is EvidenceClass.FLOOR))
        scope = next(s for s in self.request.population_scopes if s.scope_id == threat.population_scope_id)
        decision = decide_threat(threat=threat, records=evidence, release=self.request.release, population_scope=scope,
                                 policy_sha256=self.request.policy.policy_sha256, ceiling_attack_battery=self.report.decisions[index].ceiling_attack_battery)
        decisions = list(self.report.decisions); decisions[index] = decision
        return self.report.model_copy(update={"decisions": tuple(decisions), "evidence": evidence,
                                               "overall_verdict": decide_overall(tuple(decisions))})

    @patch("model_release_assurance.integrity.validate_report_against_request")
    @patch("model_release_assurance.integrity.validate_report_against_policy")
    def test_unit_missing_evidence_is_block_not_inconclusive(self, *_):
        record = self.build(report=self._decision_layer_report(missing=True))
        self.assertEqual(record.verdict, AssuranceVerdict.BLOCK)
        self.assertTrue(any("missing admissible" in r for r in record.blocking_reasons))

    @patch("model_release_assurance.integrity.validate_report_against_request")
    @patch("model_release_assurance.integrity.validate_report_against_policy")
    def test_unit_optional_in_scope_blocking_floor_blocks(self, *_):
        record = self.build(report=self._decision_layer_report(blocking=True))
        self.assertEqual(record.verdict, AssuranceVerdict.BLOCK)

    @patch("model_release_assurance.integrity.validate_report_against_request")
    @patch("model_release_assurance.integrity.validate_report_against_policy")
    def test_unit_crossing_requires_resolution_or_complete_signed_acceptance(self, *_):
        report = self._decision_layer_report()
        record = self.build(report=report)
        self.assertEqual(record.verdict, AssuranceVerdict.BLOCK)
        crossing = [t for t in record.threats if t.decision_flips_in_gap]
        self.assertTrue(crossing and all(not t.resolving_actions for t in crossing))
        self.assertIn("verified applicable resolving plan", record.blocking_reasons[0])
        acceptance = sign_residual_risk_acceptance(record, self.private,
            reason="Test authority explicitly accepts the enumerated residual ceilings for this scoped experiment",
            expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        accepted = self.build(report=report, acceptance=acceptance, trusted_acceptors=self.trust)
        self.assertEqual(accepted.verdict, AssuranceVerdict.RELEASE_WITH_RISK)
        self.assertEqual(set(accepted.accepted_residual_risks), {t.threat_id for t in crossing})
        self.assertEqual(self.build(report=report, acceptance=acceptance, trusted_acceptors={}).verdict, AssuranceVerdict.BLOCK)
        wrong = acceptance.model_copy(update={"context_sha256": "a"*64})
        self.assertEqual(self.build(report=report, acceptance=wrong, trusted_acceptors=self.trust).verdict, AssuranceVerdict.BLOCK)
        denied_scope = self.scope.model_copy(update={"residual_risk_acceptance_permitted": False})
        self.assertEqual(self.build(report=report, scope=denied_scope, acceptance=acceptance, trusted_acceptors=self.trust).verdict, AssuranceVerdict.BLOCK)

    def test_cli_missing_input_writes_machine_readable_block(self):
        output = self.base / "blocked.json"
        result = main(["assurance-gate", str(self.base/"missing-record.json"), "--request", str(self.base/"missing-request.json"),
            "--report", str(self.base/"missing-report.json"), "--scope", str(self.base/"missing-scope.json"),
            "--trust-store", str(self.base/"missing-trust.json"), "--output", str(output)])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output.read_text())["verdict"], "BLOCK")

    def test_cli_record_sign_and_gate_replay_real_assessment(self):
        report, scope = self.base / "report.json", self.base / "scope.json"
        record, signed, result = (self.base / name for name in ("record.json", "signed.json", "gate.json"))
        trust = self.base / "trust.json"
        report.write_text(self.report.model_dump_json(), encoding="utf-8")
        scope.write_text(self.scope.model_dump_json(), encoding="utf-8")
        trust.write_text(json.dumps({key: path.name for key, path in self.trust.items()}), encoding="utf-8")
        request = ROOT / "examples/request.json"
        self.assertEqual(main(["assurance-record", str(request), str(report), "--scope", str(scope), "--output", str(record)]), 0)
        self.assertEqual(main(["assurance-sign", str(record), "--private-key", str(self.private), "--output", str(signed)]), 0)
        self.assertEqual(main(["assurance-gate", str(signed), "--request", str(request), "--report", str(report),
            "--scope", str(scope), "--trust-store", str(trust), "--output", str(result)]), 0)
        self.assertEqual(json.loads(result.read_text())["verdict"], "RELEASE")
        self.assertFalse(json.loads(result.read_text())["authorization_eligible"])


if __name__ == "__main__":
    unittest.main()
