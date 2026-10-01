from __future__ import annotations

import unittest
from pathlib import Path

from model_release_assurance.release_protocol import (
    ReleaseProtocolArtifactKind,
    ReleaseProtocolEventType,
    ReleaseProtocolState,
)
from model_release_assurance.schema_registry import SCHEMA_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOCUMENT = ROOT / "docs" / "system-audit-specification.md"


class SystemAuditSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = AUDIT_DOCUMENT.read_text(encoding="utf-8")

    def test_primary_indexes_link_the_integrated_audit_document(self) -> None:
        for path in (ROOT / "README.md", ROOT / "CONTRIBUTING.md"):
            self.assertIn("system-audit-specification.md", path.read_text(encoding="utf-8"))

    def test_navigation_prioritizes_government_audit_and_separate_research(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in (
            "docs/government-audit-guide.md",
            "docs/enforced-release-workflow.md",
            "docs/publication/2026-09-28/README.md",
            "docs/system-audit-specification.md#industrial-track",
            "docs/model-release-assurance-protocol.md",
        ):
            self.assertIn(target, readme)
            self.assertTrue((ROOT / target.split("#", 1)[0]).is_file())
        self.assertLess(
            readme.index("docs/government-audit-guide.md"),
            readme.index("https://github.com/elmontu/AI_Model_Academic"),
        )
        self.assertIn("No deployment obligation is waived", readme.replace("\n", " "))
        normalized = " ".join(readme.split())
        for statement in (
            "separate academic repository",
            "public GitHub publication is pending",
            "does not cover studies completed after that date",
            "--temporal-run",
            "--temporal-operator",
        ):
            self.assertIn(statement, normalized)

    def test_track_anchors_preserve_the_proof_and_deployment_boundaries(self) -> None:
        protocol = (ROOT / "docs" / "model-release-assurance-protocol.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('<a id="academic-track"></a>', protocol)
        self.assertIn("four-verdict facade is not proved to refine Lean", protocol)
        self.assertIn('<a id="industrial-track"></a>', self.text)
        self.assertIn("Deferral changes priority", self.text)
        self.assertIn("every applicable lifecycle requirement and gate remains mandatory", self.text)

    def test_dated_advisory_archive_states_its_reproduction_limits(self) -> None:
        bundle = ROOT / "docs" / "publication" / "2026-09-28"
        overview = (bundle / "README.md").read_text(encoding="utf-8")
        self.assertIn("28 September 2026", overview)
        self.assertIn("104 original evidence references", overview)
        self.assertIn("94 distinct source snapshots", overview)
        self.assertIn("Repeating the original training experiments", overview)
        self.assertIn("outside this reporting snapshot", overview)
        for target in ("publication-manifest.json", "verify_publication.py",
                       "evidence/source-manifest.json"):
            self.assertTrue((bundle / target).is_file())

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
        current_schemas = tuple(
            registration.filename for registration in SCHEMA_REGISTRY.values()
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

    def test_current_migration_and_recorded_state_semantics_are_explicit(self) -> None:
        for statement in (
            "`ReleaseProtocolRun 1.2`",
            "`ReleaseProtocolVerification 3.0`",
            "`authenticated_v2`",
            "`authorization_recorded`",
            "`deployment_recorded`",
            "production fields are typed literal `false`",
            "`BEGIN IMMEDIATE`",
            "AssessmentReport 6.0",
            "Git history",
            "mrap_g7_exact_or_outward_clearance_eligible=false",
        ):
            self.assertIn(statement, self.text)
        self.assertNotIn(
            "are not rejected merely for occurring after the verification time",
            self.text,
        )

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
