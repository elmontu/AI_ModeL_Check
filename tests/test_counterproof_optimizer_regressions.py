"""Executable closures of the assurance counterexamples, not external-truth proofs.

The signed variants deliberately let a trusted signer sign a false assertion.
They do not break Ed25519, and test semantic rejection separately from signature
authenticity. Positive controls retain both supported optimizer trust profiles.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from unittest import mock

import test_decision_theory as fixtures
from model_release_assurance.decision_theory import FiniteExperiment, GarblingCertificate, verify_garbling
from model_release_assurance.integrity import (
    build_signed_manifest, canonical_json_bytes, generate_ed25519_keypair, sha256_bytes,
    sha256_file, sign_canonical, verify_canonical_signature,
    read_verified_source_bytes,
)
from model_release_assurance.models import AssessmentReport, AssessmentRequest
from model_release_assurance.errors import AssuranceError
from model_release_assurance.optimizer import OptimizationRequest, ReleaseOptimizer


class OptimizerCounterproofRegressions(unittest.TestCase):
    def _fixture(self, directory: Path, profile: str = "cooperative", *, with_control: bool = False) -> tuple[dict, dict]:
        helper = fixtures.ReleaseOptimizerTests()
        report_path, report = helper._write_clear_report(directory)
        configuration = helper._configuration(
            identifier="counterproof-control", report_path=report_path, report=report,
            proposed=True, utility_lower=0.8, cost=1.0,
            with_control=with_control,
        )
        raw = helper._request(helper._experiments(report), [configuration]).model_dump(mode="json")
        raw["trust_profile"] = profile
        if profile == "separated_assessor":
            private, public = directory / "assessor-private.pem", directory / "assessor-public.pem"
            generate_ed25519_keypair(private, public)
            request = AssessmentRequest.model_validate_json((directory / "assessment-request.json").read_text(encoding="utf-8"))
            manifest = build_signed_manifest(report, request, private)
            manifest_path = directory / "assessment-manifest.json"
            manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
            raw["configurations"][0]["assessment"].update({
                "signed_manifest_path": str(manifest_path),
                "signed_manifest_sha256": sha256_file(manifest_path),
                "assessor_public_key_path": str(public),
                "accepted_signer_key_ids": [manifest.signer_key_id],
            })
        return raw, report.model_dump(mode="json")

    def _replace_report(self, directory: Path, raw: dict, report: dict) -> None:
        reference = raw["configurations"][0]["assessment"]
        path = Path(reference["report_path"])
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        reference["report_sha256"] = sha256_file(path)
        if raw["trust_profile"] == "separated_assessor":
            manifest_path = Path(reference["signed_manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["report_sha256"] = sha256_bytes(canonical_json_bytes(report))
            manifest["overall_verdict"] = report["overall_verdict"]
            unsigned = {key: value for key, value in manifest.items() if key != "signature_b64"}
            signer, signature = sign_canonical(unsigned, directory / "assessor-private.pem")
            self.assertIn(signer, reference["accepted_signer_key_ids"])
            verify_canonical_signature(unsigned, signer_id=signer, signature_b64=signature,
                                       public_key_path=directory / "assessor-public.pem")
            manifest["signature_b64"] = signature
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            reference["signed_manifest_sha256"] = sha256_file(manifest_path)

    @staticmethod
    def _run(raw: dict, directory: Path):
        return ReleaseOptimizer().optimize(OptimizationRequest.model_validate(raw), directory)

    def test_complete_controls_pass_both_trust_profiles_without_authorization_claim(self) -> None:
        for profile in ("cooperative", "separated_assessor"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                raw, _ = self._fixture(Path(temporary), profile)
                result = self._run(raw, Path(temporary))
                self.assertTrue(result.fail_safe_gate_passed)
                self.assertEqual(result.selected_configuration_id, "counterproof-control")
                self.assertFalse(result.authorization_eligible)
                self.assertEqual(result.schema_version, "5.0")

    def test_policy_report_mutation_matrix_rejects_even_fresh_trusted_signatures(self) -> None:
        def mutate(report: dict, case: str) -> None:
            member = next(row for row in report["decisions"] if row["threat_id"] == "membership-person")
            if case == "A01_mandatory_omission":
                report["decisions"] = [row for row in report["decisions"] if row["threat_id"] != "membership-person"]
                report["evidence"] = [row for row in report["evidence"] if row["threat_id"] != "membership-person"]
            elif case == "A02_mandatory_demotion":
                member["mandatory"] = False
            elif case == "A03_tolerance_rewrite":
                member["tolerance"] = 0.8
            elif case == "A04_metric_rewrite":
                member["decision_metric"] = "finite_secret_exact_guess_success"
            elif case == "A05_kind_rewrite":
                member["kind"] = "attribute"
            elif case == "A05_basis_rewrite":
                member["tolerance_basis"] = "incremental"
            elif case == "A15_invented_waiver":
                member["ceiling_attack_battery"] = {
                    "mode": "waived", "waiver_reason": "unapproved submitter waiver",
                    "required_attack_ids": [], "completed_attack_ids": [],
                    "passing_positive_control_ids": [], "satisfied": True,
                }
            elif case == "A16_invented_completion":
                member["ceiling_attack_battery"]["completed_attack_ids"] = []
                member["ceiling_attack_battery"]["passing_positive_control_ids"] = []
            elif case == "A17_reduction_rewrite":
                linkage = next(row for row in report["decisions"] if row["threat_id"] == "linkage-person")
                for field in ("lower_bound", "upper_bound"):
                    linkage[field] = 0.0
                    linkage[field + "_fraction"] = {"numerator": 0, "denominator": 1}
            elif case == "A19_unbounded_tolerance":
                member["tolerance"] = 2.0
            elif case == "copied_game_hash":
                member["decision_game_sha256"] = "a" * 64
            else:
                raise AssertionError(case)

        cases = (
            "A01_mandatory_omission", "A02_mandatory_demotion", "A03_tolerance_rewrite",
            "A04_metric_rewrite", "A05_kind_rewrite", "A05_basis_rewrite",
            "A15_invented_waiver", "A16_invented_completion", "A17_reduction_rewrite",
            "A19_unbounded_tolerance", "copied_game_hash",
        )
        for profile in ("cooperative", "separated_assessor"):
            for case in cases:
                with self.subTest(profile=profile, case=case), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    raw, report = self._fixture(directory, profile)
                    OptimizationRequest.model_validate(raw)  # Do not mistake a broken fixture for semantic rejection.
                    mutate(report, case)
                    self._replace_report(directory, raw, report)
                    with self.assertRaises((ValueError, AssuranceError)):
                        self._run(raw, directory)

    def test_original_request_is_required_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw, _ = self._fixture(directory)
            reference = raw["configurations"][0]["assessment"]
            omitted = copy.deepcopy(raw)
            del omitted["configurations"][0]["assessment"]["assessment_request_path"]
            with self.assertRaises(ValueError):
                OptimizationRequest.model_validate(omitted)
            reference["assessment_request_sha256"] = "a" * 64
            with self.assertRaisesRegex(AssuranceError, "hash mismatch"):
                self._run(raw, directory)

    def test_json_imports_parse_the_same_bytes_that_were_hash_verified(self) -> None:
        # Deterministic interleaving: replace the on-disk JSON immediately after
        # the real hash-verified read returns. Every consumer must use that
        # captured immutable value, never reopen the now-malformed pathname.
        roles = ("policy", "report", "request", "manifest", "utility", "control", "portfolio", "registry", "search")
        for role in roles:
            with self.subTest(role=role), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                raw, _ = self._fixture(directory, "separated_assessor", with_control=True)
                policy_path = directory / "active-policy.json"
                policy_path.write_bytes(Path(raw["active_policy"]["policy_path"]).read_bytes())
                raw["active_policy"]["policy_path"] = str(policy_path)
                search_path = directory / "search.json"
                search = {"method": "test finite submitted-domain enumeration", "configuration_ids": ["counterproof-control"]}
                search_path.write_bytes(canonical_json_bytes(search))
                raw["search_space_status"] = "certified_exhaustive"
                raw["search_space_certificate"] = {**search, "evidence_path": str(search_path), "evidence_sha256": sha256_file(search_path)}
                configuration = raw["configurations"][0]
                reference = configuration["assessment"]
                targets = {
                    "policy": policy_path, "report": Path(reference["report_path"]),
                    "request": Path(reference["assessment_request_path"]),
                    "manifest": Path(reference["signed_manifest_path"]),
                    "utility": Path(configuration["utility"]["source_path"]),
                    "control": Path(configuration["controls"][0]["evidence_path"]),
                    "portfolio": Path(configuration["portfolio"]["evidence_path"]),
                    "registry": Path(raw["portfolio_registry"]["source_path"]), "search": search_path,
                }
                captured: list[bytes] = []

                def swap_after_capture(source_path: str, digest: str, base: Path) -> bytes:
                    value = read_verified_source_bytes(source_path, digest, base)
                    resolved = Path(source_path)
                    if not resolved.is_absolute():
                        resolved = base / resolved
                    if resolved.resolve() == targets[role].resolve():
                        captured.append(value)
                        targets[role].write_bytes(b"not valid JSON after concurrent replacement")
                    return value

                with mock.patch("model_release_assurance.optimizer.read_verified_source_bytes", side_effect=swap_after_capture):
                    result = self._run(raw, directory)
                self.assertTrue(result.fail_safe_gate_passed)
                self.assertEqual(len(captured), 1)
                self.assertNotEqual(targets[role].read_bytes(), captured[0])

    def test_self_consistent_request_rewrite_cannot_override_active_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw, report = self._fixture(directory)
            request_path = directory / "assessment-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            member = next(row for row in request["threats"] if row["threat_id"] == "membership-person")
            member["tolerance"] = 0.8
            modified_request = AssessmentRequest.model_validate(request)
            request_path.write_text(modified_request.model_dump_json() + "\n", encoding="utf-8")
            raw["configurations"][0]["assessment"]["assessment_request_sha256"] = sha256_file(request_path)
            report["request_sha256"] = sha256_bytes(canonical_json_bytes(modified_request))
            next(row for row in report["decisions"] if row["threat_id"] == "membership-person")["tolerance"] = 0.8
            self._replace_report(directory, raw, report)
            with self.assertRaises((ValueError, AssuranceError)):
                self._run(raw, directory)

    def test_equal_game_hash_does_not_allow_table_state_or_prior_substitution(self) -> None:
        for change in ("states", "prior"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                raw, _ = self._fixture(directory)
                for experiment in raw["experiments"]:
                    if experiment["threat_id"] == "linkage-person":
                        if change == "states":
                            experiment["state_ids"] = ["not-a", "not-b", "not-c", "not-d"]
                        else:
                            experiment["prior"] = [0.4, 0.2, 0.2, 0.2]
                with self.assertRaisesRegex(ValueError, "policy-frozen ordered states or exact prior"):
                    self._run(raw, directory)

    def test_A14_direct_finite_bounds_are_outward_not_close_enough(self) -> None:
        cases = ((0.60000000005, 0.6, "reject"), (0.6, 0.6, "clear"),
                 (0.6, 0.6000000001, "hold"), (0.7, 0.7, "hold"))
        for exact_success, claim, expected in cases:
            with self.subTest(exact=exact_success, claim=claim), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                raw, _ = self._fixture(directory)
                experiment = next(row for row in raw["experiments"] if row["experiment_id"] == "membership-portfolio-joint")
                complement = float(Fraction(1) - Fraction(str(exact_success)))
                experiment["observation_ids"] = ["yes", "no"]
                experiment["channel"] = [[exact_success, complement], [complement, exact_success]]
                portfolio = raw["configurations"][0]["portfolio"]
                portfolio["joint_upper_bounds"]["service-participants-2026|membership-person"] = claim
                path = Path(portfolio["evidence_path"])
                payload = {key: value for key, value in portfolio.items() if key not in {"evidence_path", "evidence_sha256"}}
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                portfolio["evidence_sha256"] = sha256_file(path)
                if expected == "reject":
                    with self.assertRaisesRegex(ValueError, "understates exact rational"):
                        self._run(raw, directory)
                else:
                    self.assertEqual(self._run(raw, directory).fail_safe_gate_passed, expected == "clear")

    @staticmethod
    def _tiny_residual_pair():
        common = {"threat_id": "membership-person", "population_scope_id": "sample-population",
                  "decision_game_sha256": "a" * 64, "state_ids": ["member", "nonmember"],
                  "prior": [0.5, 0.5], "interface_description": "finite regression channel"}
        dominant = FiniteExperiment(**common, experiment_id="no-information", observation_ids=["constant"], channel=[[1.0], [1.0]])
        dominated = FiniteExperiment(**common, experiment_id="tiny-information", observation_ids=["yes", "no"],
                                    channel=[[0.50000000005, 0.49999999995], [0.49999999995, 0.50000000005]])
        certificate = GarblingCertificate(certificate_id="tiny-residual", dominant_experiment_id=dominant.experiment_id,
                                          dominated_experiment_id=dominated.experiment_id, kernel=[[0.5, 0.5]],
                                          maximum_row_total_variation=0.0, numerical_tolerance=1e-9,
                                          construction="deliberately approximate test witness")
        return dominant, dominated, certificate

    def test_numerical_tolerance_cannot_forge_zero_tv_or_understate_tv(self) -> None:
        dominant, dominated, certificate = self._tiny_residual_pair()
        self.assertTrue(verify_garbling(dominant, dominated, certificate).valid)
        verified, residual = ReleaseOptimizer._verify_garbling_exact(dominant, dominated, certificate)
        self.assertFalse(verified.valid)
        self.assertEqual(residual, Fraction(1, 20_000_000_000))
        conservative = certificate.model_copy(update={"maximum_row_total_variation": 5e-11})
        verified, residual = ReleaseOptimizer._verify_garbling_exact(dominant, dominated, conservative)
        self.assertTrue(verified.valid)
        self.assertNotEqual(residual, 0)  # Cannot be inserted in the exact Blackwell graph.

    def test_almost_normalized_channels_are_not_accepted_as_clearance_probabilities(self) -> None:
        dominant, _, _ = self._tiny_residual_pair()
        almost = dominant.model_copy(update={"channel": ((0.99999999999,), (1.0,))})
        FiniteExperiment.model_validate(almost.model_dump())  # Exploratory schema still permits it.
        with self.assertRaisesRegex(ValueError, "sum to exactly one"):
            ReleaseOptimizer._finite_success_metric_exact(almost, "equal_prior_membership_success")

    def test_conditional_metric_has_no_generic_positive_tv_clearance_transfer(self) -> None:
        # Deliberately isolate the final transfer predicate from import validation.
        # This is a unit-level metric switch, not a claim that a rewritten report
        # can pass the request/policy checks exercised by the matrix above.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw, report_raw = self._fixture(directory)
            report = AssessmentReport.model_validate(report_raw)
            report = report.model_copy(update={"decisions": tuple(
                decision.model_copy(update={"decision_metric": "worst_observation_success"})
                if decision.threat_id == "linkage-person" else decision for decision in report.decisions
            )})
            assessed = FiniteExperiment.model_validate(raw["experiments"][0])
            released = assessed.model_copy(update={"experiment_id": "conditional-approximate"})
            raw["experiments"].append(released.model_dump(mode="json"))
            binding = raw["configurations"][0]["threat_experiments"][0]
            binding["released_experiment_id"] = released.experiment_id
            binding["substitution_certificate_id"] = "conditional-certificate"
            certificate = GarblingCertificate(
                certificate_id="conditional-certificate", dominant_experiment_id=assessed.experiment_id,
                dominated_experiment_id=released.experiment_id, kernel=((1.0, 0.0), (0.0, 1.0)),
                maximum_row_total_variation=0.01, construction="isolated transfer predicate fixture",
            )
            request = OptimizationRequest.model_validate(raw)
            common = (request.configurations[0], report, {row.experiment_id: row for row in request.experiments},
                      {certificate.certificate_id: certificate}, {}, request.portfolio_registry,
                      datetime.now(timezone.utc),
                      {"service-participants-2026|linkage-person": Fraction(0),
                       "service-participants-2026|membership-person": Fraction(1, 2)})
            result = ReleaseOptimizer._evaluate_configuration(*common, {certificate.certificate_id: Fraction(1, 100)})
            self.assertFalse(result.feasible)
            self.assertTrue(any("no proved TV transfer bound" in reason for reason in result.reasons))
            exact_control = ReleaseOptimizer._evaluate_configuration(*common, {certificate.certificate_id: Fraction(0)})
            self.assertTrue(exact_control.feasible)


if __name__ == "__main__":
    unittest.main()
