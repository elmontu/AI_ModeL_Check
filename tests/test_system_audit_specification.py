from __future__ import annotations

import unittest
from pathlib import Path

from model_release_assurance.release_protocol import (
    ReleaseProtocolArtifactKind,
    ReleaseProtocolEventType,
    ReleaseProtocolState,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOCUMENT = ROOT / "docs" / "system-audit-specification.md"


class SystemAuditSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = AUDIT_DOCUMENT.read_text(encoding="utf-8")

    def test_primary_indexes_link_the_integrated_audit_document(self) -> None:
        for path in (ROOT / "README.md", ROOT / "docs" / "README.md"):
            self.assertIn("system-audit-specification.md", path.read_text(encoding="utf-8"))

    def test_current_protocol_vocabulary_is_complete(self) -> None:
        for state in ReleaseProtocolState:
            self.assertIn(f"`{state.value.upper()}`", self.text)
        for event in ReleaseProtocolEventType:
            self.assertIn(f"`{event.value}`", self.text)
        for kind in ReleaseProtocolArtifactKind:
            self.assertIn(f"`{kind.value}`", self.text)
        for gate in range(15):
            self.assertIn(f"`G{gate}", self.text)

    def test_current_public_contracts_are_named(self) -> None:
        current_schemas = (
            "assessment-request-v4.json",
            "assessment-report-v4.json",
            "policy-bundle-v2.json",
            "signed-manifest-v2.json",
            "optimization-request-v3.json",
            "optimization-report-v3.json",
            "signed-optimization-manifest-v3.json",
            "incomplete-portfolio-problem-v1.json",
            "incomplete-portfolio-certificate-v1.1.json",
            "incomplete-portfolio-specification-v1.json",
            "portfolio-multinomial-counts-v1.json",
            "portfolio-multinomial-plan-v1.json",
            "portfolio-error-budget-v1.json",
            "portfolio-multinomial-request-v1.json",
            "portfolio-multinomial-evidence-v1.json",
            "protocol-feasibility-problem-v1.json",
            "protocol-feasibility-certificate-v1.json",
            "release-protocol-run-v1.1.json",
            "release-protocol-verification-v1.json",
            "audit-verification-v2.json",
            "audit-checkpoint-v1.json",
        )
        for schema in current_schemas:
            self.assertIn(f"`{schema}`", self.text)
            self.assertTrue((ROOT / "schemas" / schema).is_file())

    def test_authority_and_formal_boundaries_are_explicit(self) -> None:
        required = (
            "No report, manifest, signature, certificate, local audit event, optimization result",
            "Only an external registry compare-and-swap may create `AUTHORIZED`",
            "Python-to-Lean refinement",
            "live_interface_verified=false",
            "authorization_eligible=false",
            "locally_valid_unanchored",
        )
        for statement in required:
            self.assertIn(statement, self.text)

    def test_supplied_critique_and_residual_gaps_are_auditable(self) -> None:
        findings = (
            "C1",
            "C2",
            "C3",
            "C4",
            "C5",
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
            "S6",
            "S7",
            "S8",
        )
        for finding in findings:
            self.assertIn(f"`{finding}`", self.text)
        for boundary in (
            "`legacy_event_count == 0`",
            "Pre-validation audit ingress",
            "Normative/runtime lifecycle parity",
            "Binary64 decision boundaries",
            "full canonical envelope",
            "narrower transition relation",
        ):
            self.assertIn(boundary, self.text)


if __name__ == "__main__":
    unittest.main()
