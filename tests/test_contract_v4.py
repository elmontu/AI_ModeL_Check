from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from model_release_assurance.analyzers.tree import TreeLinkageAnalyzer
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import (
    build_signed_manifest,
    canonical_json_bytes,
    generate_ed25519_keypair,
    sha256_bytes,
    sha256_file,
    verify_signed_manifest,
)
from model_release_assurance.models import AssessmentRequest
from model_release_assurance.optimizer import OptimizationRequest, ReleaseOptimizer
from model_release_assurance.services import (
    AnalyzerServiceRegistry,
    LocalAnalyzerService,
    default_analyzer_service_registry,
)


ROOT = Path(__file__).resolve().parents[1]


def assessment_raw() -> dict:
    return json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))


class AssessmentContractV4Tests(unittest.TestCase):
    def test_report_and_manifest_expose_non_authorizing_scope(self) -> None:
        request = AssessmentRequest.model_validate(assessment_raw())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        self.assertEqual(report.schema_version, "4.0")
        self.assertEqual(
            report.assessment_scope.composition_scope,
            "single_release_no_portfolio",
        )
        self.assertEqual(
            report.assessment_scope.interface_assurance,
            "declared_interface_only",
        )
        self.assertFalse(report.assessment_scope.live_interface_verified)
        self.assertFalse(report.assessment_scope.authorization_eligible)
        self.assertTrue(report.assessment_scope.portfolio_assessment_required)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private = base / "private.pem"
            public = base / "public.pem"
            generate_ed25519_keypair(private, public)
            manifest = build_signed_manifest(report, request, private)
            verify_signed_manifest(manifest, report, public)
            tampered_interface = manifest.model_copy(
                update={"release_interface_sha256": "0" * 64}
            )
            with self.assertRaisesRegex(IntegrityError, "release_interface_sha256"):
                verify_signed_manifest(tampered_interface, report, public)
        self.assertEqual(manifest.schema_version, "2.0")
        self.assertEqual(manifest.composition_scope, "single_release_no_portfolio")
        self.assertEqual(manifest.interface_assurance, "declared_interface_only")
        self.assertFalse(manifest.authorization_eligible)
        self.assertEqual(
            manifest.release_interface_sha256,
            sha256_bytes(canonical_json_bytes(report.release_interface)),
        )

    def test_report_dispositions_name_every_included_and_excluded_record(self) -> None:
        request = AssessmentRequest.model_validate(assessment_raw())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        for decision in report.decisions:
            expected = {
                record.evidence_id
                for record in report.evidence
                if record.threat_id == decision.threat_id
            }
            self.assertEqual(
                set(decision.evidence_ids) | set(decision.excluded_evidence_ids),
                expected,
            )
            self.assertFalse(set(decision.evidence_ids) & set(decision.excluded_evidence_ids))

        raw = report.model_dump(mode="json")
        raw["decisions"][0]["excluded_evidence_ids"] = []
        with self.assertRaisesRegex(ValidationError, "does not disposition"):
            type(report).model_validate(raw)

    def test_evidence_records_bind_typed_producer_identity(self) -> None:
        request = AssessmentRequest.model_validate(assessment_raw())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        expected = {
            value.analyzer: value.provenance.producer
            for value in request.analyzer_inputs
        }
        for record in report.evidence:
            self.assertEqual(record.producer, expected[record.analyzer])

    def test_threat_decision_cannot_omit_consistency_classification(self) -> None:
        request = AssessmentRequest.model_validate(assessment_raw())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        raw = report.model_dump(mode="json")
        raw["decisions"][0].pop("evidence_consistency")
        with self.assertRaises(ValidationError):
            type(report).model_validate(raw)

    def test_policy_minimum_analyzer_version_fails_closed(self) -> None:
        raw = assessment_raw()
        raw["analyzer_inputs"][0]["provenance"]["producer"]["service_version"] = "0.9.0"
        request = AssessmentRequest.model_validate(raw)
        replacement = LocalAnalyzerService(TreeLinkageAnalyzer(), version="0.9.0")
        defaults = default_analyzer_service_registry().services
        registry = AnalyzerServiceRegistry(
            (replacement,)
            + tuple(
                service
                for service in defaults
                if service.descriptor.input_kind != "tree_linkage"
            )
        )
        with self.assertRaisesRegex(ValueError, "below policy minimum"):
            AssuranceEngine(service_registry=registry).assess(request, ROOT / "examples")

    def test_unapproved_analyzer_configuration_fails_closed(self) -> None:
        raw = assessment_raw()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "unapproved-tree-config.json"
            config.write_text('{"profile":"unapproved"}\n', encoding="utf-8")
            provenance = raw["analyzer_inputs"][0]["provenance"]
            provenance["configuration_path"] = str(config)
            provenance["producer"]["configuration_sha256"] = sha256_file(config)
            request = AssessmentRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "configuration digest is not accepted"):
                AssuranceEngine().assess(request, ROOT / "examples")

    def test_policy_required_analyzer_cannot_be_omitted(self) -> None:
        raw = assessment_raw()
        raw["analyzer_inputs"] = [
            value for value in raw["analyzer_inputs"] if value["analyzer"] != "attack"
        ]
        request = AssessmentRequest.model_validate(raw)
        with self.assertRaisesRegex(ValueError, "omits policy-required analyzers"):
            AssuranceEngine().assess(request, ROOT / "examples")


class OptimizationContractV3Tests(unittest.TestCase):
    def test_selection_and_portfolio_scope_are_replayable_outputs(self) -> None:
        path = ROOT / "examples" / "optimization-request.json"
        request = OptimizationRequest.model_validate_json(path.read_text(encoding="utf-8"))
        report = ReleaseOptimizer().optimize(request, path.parent)
        self.assertEqual(report.schema_version, "3.0")
        self.assertEqual(report.selection_policy, request.selection_policy)
        self.assertEqual(report.composition_scope, "portfolio_registry_bound")
        self.assertEqual(
            report.selected_covered_release_ids,
            ("whole-government-demo-tree-v1",),
        )
        self.assertEqual(report.selected_interface_assurance, "declared_interface_only")
        self.assertFalse(report.authorization_eligible)

    def test_registry_snapshot_substitution_is_rejected(self) -> None:
        path = ROOT / "examples" / "optimization-request.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["portfolio_registry"]["registry_head_sha256"] = "2" * 64
        request = OptimizationRequest.model_validate(raw)
        with self.assertRaisesRegex(Exception, "differs between"):
            ReleaseOptimizer().optimize(request, path.parent)

    def test_selection_policy_must_be_authorized_by_active_policy(self) -> None:
        path = ROOT / "examples" / "optimization-request.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["selection_policy"]["tie_break_order"] = [
            "utility_lower_bound_descending",
            "implementation_cost_ascending",
            "prefer_proposed_configuration",
            "configuration_id_ascending",
        ]
        request = OptimizationRequest.model_validate(raw)
        with self.assertRaisesRegex(ValueError, "not authorized"):
            ReleaseOptimizer().optimize(request, path.parent)

    def test_active_policy_bump_invalidates_stale_assessment(self) -> None:
        path = ROOT / "examples" / "optimization-request.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        policy = json.loads((ROOT / "examples" / "policy.json").read_text(encoding="utf-8"))
        policy["policy_version"] = "2.1.0"
        with tempfile.TemporaryDirectory() as directory:
            active_path = Path(directory) / "active-policy.json"
            active_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
            raw["active_policy"].update(
                {
                    "policy_version": "2.1.0",
                    "policy_path": str(active_path),
                    "policy_sha256": sha256_file(active_path),
                }
            )
            request = OptimizationRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "active policy hash"):
                ReleaseOptimizer().optimize(request, path.parent)


if __name__ == "__main__":
    unittest.main()
