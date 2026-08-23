from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORMAL = ROOT / "formal" / "lean"


class FormalVerificationArtifactTests(unittest.TestCase):
    def test_toolchain_is_pinned(self) -> None:
        self.assertEqual(
            (FORMAL / "lean-toolchain").read_text(encoding="utf-8").strip(),
            "leanprover/lean4:v4.32.1",
        )

    def test_no_proof_placeholders(self) -> None:
        placeholder = re.compile(r"\b(?:sorry|admit)\b")
        for source in FORMAL.rglob("*.lean"):
            self.assertIsNone(placeholder.search(source.read_text(encoding="utf-8")), source)

    def test_claimed_theorems_are_in_the_kernel_audit(self) -> None:
        main = (FORMAL / "Main.lean").read_text(encoding="utf-8")
        for theorem in (
            "MRAP.reachable_authorization_integrity",
            "MRAP.active_implies_committed_clear_and_bound",
            "MRAP.step_preserves_release_identity",
            "MRAP.terminal_release_phase_is_absorbing",
            "MRAP.stale_head_second_commit_fails",
            "MRAP.every_step_is_role_authorized",
            "MRAP.reachable_registry_head_never_decreases",
            "MRAP.valid_active_trace_exists",
            "MRAP.Deployment.commit_succeeds_iff_admissible",
            "MRAP.Deployment.successful_commit_is_atomic_and_bound",
            "MRAP.Deployment.committed_request_replay_is_rejected",
            "MRAP.Deployment.used_nonce_commit_is_rejected",
            "MRAP.Deployment.stale_concurrent_commit_is_rejected",
            "MRAP.Deployment.activation_succeeds_iff_current_record_admissible",
            "MRAP.Deployment.successful_activation_can_serve",
            "MRAP.Deployment.can_serve_implies_current_live_bound_authorization",
            "MRAP.Deployment.artifact_substitution_cannot_be_served",
            "MRAP.Deployment.interface_substitution_cannot_be_served",
            "MRAP.Deployment.stale_gateway_cannot_serve",
            "MRAP.Deployment.expired_lease_cannot_serve",
            "MRAP.Deployment.authorization_deadline_cannot_serve",
            "MRAP.Deployment.revocation_stops_existing_gateway",
            "MRAP.Deployment.suspension_stops_existing_gateway",
            "MRAP.Deployment.reachable_active_has_serving_realization",
            "MRAP.Deployment.ideal_commit_and_activation_are_executable",
            "MRAP.Security.successful_acceptance_is_authenticated_authorized_and_bound",
            "MRAP.Security.accepted_envelope_replay_is_rejected",
            "MRAP.Security.mismatched_artifact_is_rejected",
            "MRAP.Security.compromised_signer_is_rejected",
            "MRAP.Security.expired_envelope_is_rejected",
            "MRAP.Security.authenticated_step_requires_a_bound_message",
            "MRAP.Security.authenticated_reachable_projects",
            "MRAP.Security.authenticated_reachable_authorization_integrity",
            "MRAP.Security.authenticated_active_implies_committed_clear_and_bound",
            "MRAP.Statistics.finite_false_authorization_bound",
            "MRAP.Statistics.finite_false_authorization_within_budget",
            "MRAP.Statistics.rational_experiment_false_authorization_within_budget",
            "MRAP.Statistics.registered_component_budget_controls_false_authorization",
            "MRAP.Mutants.direct_unsafe_activation_is_rejected",
        ):
            self.assertIn(f"#print axioms {theorem}", main)

    def test_formal_claims_are_scoped_as_non_refinement(self) -> None:
        documentation = (ROOT / "docs" / "formal-verification.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("not a refinement proof", documentation)
        self.assertIn("does not prove that a released model is safe", documentation)

    def test_ideal_deployment_boundary_is_explicit(self) -> None:
        deployment = (FORMAL / "MRAP" / "Deployment.lean").read_text(
            encoding="utf-8"
        )
        documentation = (ROOT / "docs" / "formal-verification.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("ideal functionality", deployment)
        self.assertIn("ideal deployment", documentation)
        self.assertIn("does not verify PostgreSQL", documentation)

    def test_public_protocol_library_excludes_audit_mutants(self) -> None:
        public_umbrella = (FORMAL / "MRAP.lean").read_text(encoding="utf-8")
        audit_entry = (FORMAL / "Main.lean").read_text(encoding="utf-8")
        self.assertIn("import MRAP.Deployment", public_umbrella)
        self.assertNotIn("import MRAP.Mutants", public_umbrella)
        self.assertIn("import MRAP.Mutants", audit_entry)


if __name__ == "__main__":
    unittest.main()
