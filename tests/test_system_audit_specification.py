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

    def test_track_navigation_prioritizes_academic_work(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in (
            "docs/model-release-assurance-protocol.md#academic-track",
            "reproduction/README.md#academic-plan",
            "docs/system-audit-specification.md#industrial-track",
        ):
            self.assertIn(target, readme)
        self.assertLess(
            readme.index("## Academic track"),
            readme.index("## Reference implementation quick start"),
        )
        self.assertIn("one shared core", readme)

    def test_track_anchors_preserve_the_proof_and_deployment_boundaries(self) -> None:
        protocol = (ROOT / "docs" / "model-release-assurance-protocol.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('<a id="academic-track"></a>', protocol)
        self.assertIn("four-verdict facade is not proved to refine Lean", protocol)
        self.assertIn('<a id="industrial-track"></a>', self.text)
        self.assertIn("Deferral changes priority", self.text)
        self.assertIn("every applicable lifecycle requirement and gate remains mandatory", self.text)

    def test_academic_plan_is_not_a_completed_experiment(self) -> None:
        reproduction = (ROOT / "reproduction" / "README.md").read_text(encoding="utf-8")
        self.assertIn('<a id="academic-plan"></a>', reproduction)
        plan = reproduction.split('<a id="academic-plan"></a>', 1)[1].split(
            "## Asset matrix", 1
        )[0]
        self.assertIn("proposed, not executed", plan)
        self.assertIn("not a registration", plan)
        for question in ("RQ1:", "RQ2:", "RQ3:"):
            self.assertIn(question, plan)

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
