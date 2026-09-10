"""Finite construction regressions, not production MRAP refinement proofs."""
from __future__ import annotations

from fractions import Fraction as F
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "academic_gap_constructions", ROOT / "academic" / "scripts" / "check_academic_gap_constructions.py"
)
assert SPEC is not None and SPEC.loader is not None
GAPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GAPS)


class AcademicGapConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = GAPS.build_report()
        cls.studies = {study["id"]: study for study in cls.report["studies"]}

    def test_retained_artifact_replays_exactly(self) -> None:
        expected = (json.dumps(self.report, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
        self.assertEqual((ROOT / "academic" / "paper" / "gap-construction-results.json").read_bytes(), expected)

    def test_no_model_or_universal_verification_claim_is_emitted(self) -> None:
        self.assertEqual(self.report["artifact_role"], "finite_constructed_validation_not_MRAP_contract")
        self.assertEqual(len(self.studies), 7)
        self.assertTrue(self.report["all_constructed_checks_passed"])
        self.assertFalse(self.report["reproducibility"]["network_used"])
        self.assertFalse(self.report["reproducibility"]["core_code_imported"])
        self.assertIsNone(self.report["reproducibility"]["seed"])
        for study in self.studies.values():
            self.assertTrue(study["hypothesis"])
            self.assertTrue(study["counterexample"])
            self.assertTrue(study["repair_control"])
            self.assertTrue(study["remaining_boundary"])

    def test_channel_primitives_reject_inexact_or_nonstochastic_rows(self) -> None:
        for channel in ((), ((F(1),), (F(1, 2),)), ((0.5, 0.5),), ((F(-1), F(2)),)):
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                GAPS.validate_channel(channel)
        with self.assertRaises(ValueError):
            GAPS.row_tv(((F(1),),), ((F(1), F(0)),))

    def test_blind_floor_cannot_identify_opposite_true_risks(self) -> None:
        rows = self.studies["G1_floor_nonidentifiability"]["construction"]
        self.assertEqual([row["blind_success"] for row in rows], ["1/2", "1/2"])
        self.assertEqual([row["optimal_success"] for row in rows], ["1/2", "1"])
        self.assertEqual(sum(row["enumerated_decoders"] for row in rows), 8)
        self.assertTrue(all(row["optimal_success"] == row["pointwise_bayes_success"] for row in rows))

    def test_selection_mass_and_repair_are_exact(self) -> None:
        study = self.studies["G2_selection_error"]
        plain, repaired = study["construction"]
        self.assertEqual(F(plain["selected_false_release_probability"]), 1 - F(19, 20) ** 20)
        self.assertEqual(F(repaired["selected_false_release_probability"]), 1 - F(399, 400) ** 20)
        self.assertLess(F(repaired["selected_false_release_probability"]), F(1, 20))
        for case in (plain, repaired):
            self.assertEqual(sum(F(row["probability"]) for row in case["histogram"]), 1)
            self.assertEqual(sum(row["labeled_configurations"] for row in case["histogram"]), 2 ** 20)

    def test_scope_partition_keeps_residual_and_rejects_all_omissions(self) -> None:
        study = self.studies["G3_scope_and_observation"]
        residual = next(atom for atom in study["atoms"] if atom["profile"] == [0, 0])
        self.assertEqual(len(residual["scenario_ids"]), 2)
        masks = study["declaration_masks"]
        self.assertEqual(len(masks), 256)
        self.assertEqual(sum(row["coverage_accepted"] for row in masks), 1)
        self.assertEqual(study["hidden_worlds"][0]["auditor_view"], study["hidden_worlds"][1]["auditor_view"])
        self.assertNotEqual(study["hidden_worlds"][0]["adversary_success"], study["hidden_worlds"][1]["adversary_success"])

    def test_joint_channel_control_distinguishes_identical_marginals(self) -> None:
        study = self.studies["G4_joint_disclosure"]
        self.assertEqual([row["optimal_success"] for row in study["channels"]], ["1/2", "1/2", "1", "1/2"])
        self.assertEqual(study["finite_check_count"], 40)
        self.assertTrue(all(row["optimal_success"] == row["pointwise_bayes_success"] for row in study["channels"]))

    def test_small_tv_posterior_failure_and_expected_gain_sharpness(self) -> None:
        study = self.studies["G5_transfer_metric_boundary"]
        for case in study["erasure_cases"]:
            self.assertEqual(F(case["expected_success"]), F(1, 2) + F(case["epsilon"]) / 2)
            self.assertEqual(F(case["maximum_posterior"]), 1)
        for case in study["expected_gain_sharpness_cases"]:
            self.assertEqual(F(case["row_tv"]), F(case["expected_success_increase"]))

    def test_reducer_exhaustive_finite_product_has_no_disagreements(self) -> None:
        study = self.studies["G6_decision_precedence"]
        self.assertEqual(study["grid_evaluations"], 93312)
        self.assertEqual(sum(study["verdict_counts"].values()), 93312)
        self.assertEqual(set(study["verdict_counts"]), {"BLOCK", "RELEASE", "RELEASE-WITH-RISK", "INCONCLUSIVE"})
        self.assertEqual(study["declarative_disagreements"], 0)
        self.assertEqual(len(study["named_boundary_cases"]), 10)

    def test_partial_acceptance_and_missing_evidence_do_not_promote(self) -> None:
        threats = ((F(0), F(1), F(1, 2)),) * 2
        self.assertEqual(GAPS.reduce_verdict(threats, acceptance=(True, 1), actionable_mask=3), "BLOCK")
        self.assertEqual(GAPS.reduce_verdict(threats, acceptance=(True, 3), missing_mask=2), "BLOCK")
        self.assertEqual(GAPS.reduce_verdict(threats, acceptance=(True, 3)), "RELEASE-WITH-RISK")
        self.assertEqual(GAPS.reduce_verdict(threats, actionable_mask=1), "BLOCK")
        self.assertEqual(GAPS.reduce_verdict(threats, actionable_mask=3), "INCONCLUSIVE")

    def test_six_selection_controls_are_separate_from_reducer_case_counts(self) -> None:
        study = self.studies["G6_decision_precedence"]
        self.assertEqual(study["grid_evaluations"], 93312)
        self.assertEqual(study["finite_check_count"], 93322)
        self.assertEqual(study["selection_control_count"], 6)
        self.assertEqual(len(study["selection_controls"]), 6)
        self.assertEqual([row["eligible"] for row in study["selection_controls"]],
                         [False, True, False, False, False, True])
        for case in study["selection_controls"]:
            with self.subTest(selection=case["name"]):
                self.assertEqual(GAPS.selection_admissible(case["candidate_verdict"],
                    **case["supplied_premises"]), case["expected_eligible"])

    def test_selection_requires_other_gates_and_never_accepts_a_mandatory_crossing(self) -> None:
        self.assertFalse(GAPS.selection_admissible("RELEASE", mandatory_clear=True, other_gates_pass=False))
        self.assertFalse(GAPS.selection_admissible("RELEASE-WITH-RISK", mandatory_clear=True,
            other_gates_pass=True, crossings_optional_only=False, policy_allows_risk=True,
            exact_valid_acceptance=True))
        for verdict in ("BLOCK", "INCONCLUSIVE", "UNKNOWN"):
            self.assertFalse(GAPS.selection_admissible(verdict, mandatory_clear=True,
                other_gates_pass=True, crossings_optional_only=True, policy_allows_risk=True,
                exact_valid_acceptance=True))

    def test_float_endpoint_is_not_silently_treated_as_exact(self) -> None:
        self.assertEqual(GAPS.reduce_verdict(((0.5, F(1), F(1, 2)),)), "BLOCK")

    def test_ideal_authentication_does_not_validate_false_ceiling(self) -> None:
        worlds = self.studies["G7_authentication_not_truth"]["semantic_worlds"]
        self.assertTrue(all(row["authentic_by_ideal_oracle"] for row in worlds))
        self.assertEqual([row["authentication_only_decision"] for row in worlds], ["RELEASE", "RELEASE"])
        self.assertEqual([row["complete_finite_channel_admission"] for row in worlds], ["ADMIT", "REJECT"])

    def test_serialized_service_grant_control_closes_the_split_revocation_race(self) -> None:
        study = self.studies["G7_authentication_not_truth"]
        self.assertEqual(study["finite_check_count"], 2, "semantic-world count is unchanged")
        controls = study["grant_revocation_controls"]
        self.assertEqual(controls["control_count"], 5)
        split = {tuple(row["order"]): row for row in controls["split_status_check_orders"]}
        self.assertEqual(set(split), {("check", "grant", "revoke"), ("check", "revoke", "grant"),
                                      ("revoke", "check", "grant")})
        self.assertTrue(split[("check", "revoke", "grant")]["grant_after_revocation"])
        self.assertEqual(sum(row["grant_after_revocation"] for row in split.values()), 1)
        atomic = {tuple(row["order"]): row for row in controls["atomic_status_budget_grant_orders"]}
        self.assertEqual(len(atomic), 2)
        before = atomic[("atomic_status_budget_grant", "revoke")]
        after = atomic[("revoke", "atomic_status_budget_grant")]
        self.assertTrue(before["grant_allowed"])
        self.assertTrue(before["already_granted_request_may_complete_after_revocation"])
        self.assertEqual(before["remaining_budget"], 0)
        self.assertFalse(after["grant_allowed"])
        self.assertFalse(after["already_granted_request_may_complete_after_revocation"])
        self.assertEqual(after["remaining_budget"], 1)
        self.assertFalse(any(row["grant_after_revocation"] for row in atomic.values()))

    def test_check_mode_is_read_only_and_detects_modified_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "gap-results.json"
            self.assertEqual(GAPS.main(["--output", str(target)]), 0)
            self.assertEqual(GAPS.main(["--output", str(target)]), 0, "own-role regeneration is allowed")
            self.assertEqual(GAPS.main(["--check", "--output", str(target)]), 0)
            target.write_bytes(b"{}\n")
            self.assertEqual(GAPS.main(["--check", "--output", str(target)]), 1)
            self.assertEqual(target.read_bytes(), b"{}\n")

    def test_writer_rejects_existing_unrelated_json_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unrelated.json"
            for payload in (b'{"private": "retain"}\n', b'not JSON\n', b'[]\n'):
                target.write_bytes(payload)
                with self.subTest(payload=payload), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    GAPS.main(["--output", str(target)])
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(target.read_bytes(), payload)

    def test_writer_rejects_generator_historical_data_and_schema_targets(self) -> None:
        targets = [ROOT / "academic" / "scripts" / "check_academic_gap_constructions.py",
                   ROOT / "academic" / "paper" / "experimental-data.json",
                   ROOT / "schemas" / "current-schema-manifest-v1.json"]
        for target in targets:
            original = target.read_bytes()
            with self.subTest(target=target.name), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                GAPS.main(["--output", str(target)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(target.read_bytes(), original)
        for directory in ("src", "schemas", "scripts", "tests", "academic/scripts", "academic/tests"):
            fresh_target = ROOT / directory / "not-a-gap-output.json"
            self.assertFalse(fresh_target.exists())
            with self.subTest(directory=directory), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                GAPS.main(["--output", str(fresh_target)])
            self.assertFalse(fresh_target.exists())


if __name__ == "__main__":
    unittest.main()
