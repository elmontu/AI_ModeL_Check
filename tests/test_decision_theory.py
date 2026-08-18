from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from model_release_assurance.decision_theory import (
    DecisionProblem,
    FiniteExperiment,
    GarblingCertificate,
    PopulationAnchor,
    anchoring_reversal_witness,
    decision_reversal_witness,
    deterministic_experiment,
    deterministic_garbling_certificate,
    exact_guess_problem,
    order_soundness_check,
    separation_witness,
    verify_garbling,
)
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes, sha256_file
from model_release_assurance.incomplete_portfolio import (
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    IncompletePortfolioProblem,
    StatisticalCoverage,
    solve_analytic_portfolio,
)
from model_release_assurance.models import AssessmentRequest
from model_release_assurance.optimizer import OptimizationRequest, ReleaseOptimizer


ROOT = Path(__file__).resolve().parents[1]


def load_example() -> dict:
    raw = json.loads((ROOT / "examples" / "request.json").read_text())
    raw["release"]["artifact_sha256"] = sha256_file(ROOT / "examples" / "artifacts" / "demo-tree.json")
    return raw


class BlackwellDecisionTheoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.states = tuple(f"record-{index:02d}" for index in range(30))
        self.prior = tuple(1.0 / len(self.states) for _ in self.states)

    def test_order_soundness_replays_deterministic_garbling(self) -> None:
        exact = deterministic_experiment(
            experiment_id="exact-observation",
            threat_id="linkage-record",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=self.states,
            prior=self.prior,
            interface_description="exact record signal",
        )
        coarse = deterministic_experiment(
            experiment_id="three-groups",
            threat_id="linkage-record",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=tuple(f"group-{index % 3}" for index in range(30)),
            prior=self.prior,
            interface_description="three-group signal",
        )
        certificate = deterministic_garbling_certificate(
            exact,
            coarse,
            certificate_id="exact-to-three-groups",
        )
        result = order_soundness_check(exact, coarse, certificate, exact_guess_problem(self.states))
        self.assertAlmostEqual(result["dominant_value"], 1.0)
        self.assertAlmostEqual(result["dominated_value"], 0.1)

    def test_row_total_variation_accumulates_small_cell_errors(self) -> None:
        dominant = FiniteExperiment(
            experiment_id="one-cell",
            threat_id="wide-channel",
            population_scope_id="population-30",
            state_ids=("s0", "s1"),
            observation_ids=("source",),
            channel=((1.0,), (1.0,)),
            prior=(0.5, 0.5),
            interface_description="one source observation",
        )
        width = 10_000
        uniform = 1.0 / width
        perturbed = tuple(
            uniform + (1e-6 if index < width // 2 else -1e-6)
            for index in range(width)
        )
        dominated = FiniteExperiment(
            experiment_id="wide-perturbed",
            threat_id="wide-channel",
            population_scope_id="population-30",
            state_ids=("s0", "s1"),
            observation_ids=tuple(f"y{index}" for index in range(width)),
            channel=(perturbed, perturbed),
            prior=(0.5, 0.5),
            interface_description="ten-thousand-cell channel",
        )
        certificate = GarblingCertificate(
            certificate_id="elementwise-trap",
            dominant_experiment_id=dominant.experiment_id,
            dominated_experiment_id=dominated.experiment_id,
            kernel=(tuple(uniform for _ in range(width)),),
            maximum_row_total_variation=0.0,
            construction="uniform kernel used to expose accumulated row error",
        )
        verification = verify_garbling(dominant, dominated, certificate)
        self.assertFalse(verification.valid)
        self.assertAlmostEqual(verification.maximum_absolute_error, 1e-6, places=12)
        self.assertAlmostEqual(verification.maximum_row_total_variation, 0.005, places=12)

    def test_non_degenerate_decision_reversal(self) -> None:
        modulo_three = deterministic_experiment(
            experiment_id="modulo-three",
            threat_id="multi-purpose-release",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=tuple(f"m3-{index % 3}" for index in range(30)),
            prior=self.prior,
            interface_description="three-way attribute signal",
        )
        modulo_five = deterministic_experiment(
            experiment_id="modulo-five",
            threat_id="multi-purpose-release",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=tuple(f"m5-{index % 5}" for index in range(30)),
            prior=self.prior,
            interface_description="five-way record partition",
        )
        attribute = DecisionProblem(
            problem_id="three-class-attribute",
            state_ids=self.states,
            action_ids=("class-0", "class-1", "class-2"),
            gain=tuple(
                tuple(1.0 if action == index % 3 else 0.0 for action in range(3))
                for index in range(30)
            ),
            interpretation="exact recovery of a three-class sensitive attribute",
        )
        witness = decision_reversal_witness(
            modulo_three,
            modulo_five,
            attribute,
            exact_guess_problem(self.states, "record-identity"),
            minimum_supported_states=30,
        )
        self.assertTrue(witness.non_degenerate)
        self.assertGreater(witness.left_problem_values[0], witness.left_problem_values[1])
        self.assertGreater(witness.right_problem_values[1], witness.right_problem_values[0])

    def test_substitution_separation_has_operational_direction(self) -> None:
        evaluated = deterministic_experiment(
            experiment_id="label-only-evaluation",
            threat_id="linkage-record",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=tuple(f"label-{index % 3}" for index in range(30)),
            prior=self.prior,
            interface_description="label-only assessment",
        )
        released = deterministic_experiment(
            experiment_id="full-artifact-release",
            threat_id="linkage-record",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=self.states,
            prior=self.prior,
            interface_description="full artifact exposing record-specific observations",
        )
        witness = separation_witness(evaluated, released, exact_guess_problem(self.states))
        self.assertTrue(witness.proves_evaluated_does_not_dominate_released)
        self.assertGreater(witness.value_gap, 0.8)

    def test_population_anchor_can_reverse_same_metric(self) -> None:
        left_observations = tuple(
            f"left-unique-{index}" if index < 15 else "left-common"
            for index in range(30)
        )
        right_observations = tuple(
            "right-common" if index < 15 else f"right-unique-{index}"
            for index in range(30)
        )
        left = deterministic_experiment(
            experiment_id="first-stratum-detailed",
            threat_id="linkage-record",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=left_observations,
            prior=self.prior,
            interface_description="detailed first stratum",
        )
        right = deterministic_experiment(
            experiment_id="second-stratum-detailed",
            threat_id="linkage-record",
            population_scope_id="population-30",
            state_ids=self.states,
            observations=right_observations,
            prior=self.prior,
            interface_description="detailed second stratum",
        )
        first_prior = tuple(1.0 / 15 if index < 15 else 0.0 for index in range(30))
        second_prior = tuple(0.0 if index < 15 else 1.0 / 15 for index in range(30))
        first = PopulationAnchor(
            anchor_id="first-stratum",
            state_ids=self.states,
            prior=first_prior,
            population_definition="first predeclared population stratum",
            source="unit-test finite population",
        )
        second = PopulationAnchor(
            anchor_id="second-stratum",
            state_ids=self.states,
            prior=second_prior,
            population_definition="second predeclared population stratum",
            source="unit-test finite population",
        )
        witness = anchoring_reversal_witness(
            left,
            right,
            exact_guess_problem(self.states),
            first,
            second,
            minimum_anchor_support=10,
        )
        self.assertTrue(witness.non_degenerate)
        self.assertGreater(witness.minimum_value_gap, 0.8)


class ReleaseOptimizerTests(unittest.TestCase):
    def _write_clear_report(self, directory: Path):
        request = AssessmentRequest.model_validate(load_example())
        report = AssuranceEngine().assess(request, ROOT / "examples")
        path = directory / "assessment.json"
        path.write_text(report.model_dump_json(indent=2, exclude_none=True) + "\n")
        return path, report

    def _experiments(self, report) -> list[dict]:
        interface_sha256 = sha256_bytes(canonical_json_bytes(report.release_interface))
        games = {decision.threat_id: decision.decision_game_sha256 for decision in report.decisions}
        linkage = deterministic_experiment(
            experiment_id="linkage-assessed",
            threat_id="linkage-person",
            population_scope_id="service-participants-2026",
            state_ids=("a", "b", "c", "d"),
            observations=("L1", "L1", "L2", "L2"),
            interface_description="assessed linkage surface",
            decision_game_sha256=games["linkage-person"],
            interface_sha256=interface_sha256,
            artifact_sha256=report.artifact_sha256,
        )
        membership = deterministic_experiment(
            experiment_id="membership-assessed",
            threat_id="membership-person",
            population_scope_id="service-participants-2026",
            state_ids=("member", "nonmember"),
            observations=("response-a", "response-b"),
            interface_description="assessed membership surface",
            decision_game_sha256=games["membership-person"],
            interface_sha256=interface_sha256,
            artifact_sha256=report.artifact_sha256,
        )
        linkage_joint = deterministic_experiment(
            experiment_id="linkage-portfolio-joint",
            threat_id="linkage-person",
            population_scope_id="service-participants-2026",
            state_ids=("a", "b", "c", "d"),
            observations=("constant", "constant", "constant", "constant"),
            interface_description="directly assessed registered release portfolio",
            decision_game_sha256=games["linkage-person"],
            interface_sha256=interface_sha256,
            artifact_sha256=report.artifact_sha256,
        )
        membership_joint = deterministic_experiment(
            experiment_id="membership-portfolio-joint",
            threat_id="membership-person",
            population_scope_id="service-participants-2026",
            state_ids=("member", "nonmember"),
            observations=("constant", "constant"),
            interface_description="directly assessed registered release portfolio",
            decision_game_sha256=games["membership-person"],
            interface_sha256=interface_sha256,
            artifact_sha256=report.artifact_sha256,
        )
        return [
            linkage.model_dump(), membership.model_dump(),
            linkage_joint.model_dump(), membership_joint.model_dump(),
        ]

    def _configuration(
        self,
        *,
        identifier: str,
        report_path: Path,
        report,
        proposed: bool,
        utility_lower: float,
        cost: float,
        with_control: bool = False,
        linkage_released: str = "linkage-assessed",
        linkage_certificate: str | None = None,
    ) -> dict:
        interface = load_example()["release"]["interface"]
        interface_sha256 = sha256_bytes(canonical_json_bytes(report.release_interface))
        population_hashes = tuple(sorted(report.population_scope_sha256s.values()))
        utility_payload = {
            "configuration_id": identifier,
            "artifact_sha256": report.artifact_sha256,
            "interface_sha256": interface_sha256,
            "population_scope_sha256s": list(population_hashes),
            "evaluation_split_sha256": "e" * 64,
            "metric": "balanced_accuracy",
            "lower_bound": utility_lower,
            "point_estimate": max(utility_lower, 0.82),
            "minimum_required": 0.7,
            "evaluation_population": "disjoint demonstration utility set",
            "confidence": 0.95,
            "uncertainty_method": "one-sided stratified bootstrap lower confidence bound",
            "audit_disjoint": True,
            "raw_evidence_retained": True,
        }
        utility_path = report_path.parent / f"{identifier}-utility.json"
        utility_path.write_text(json.dumps(utility_payload) + "\n")
        pairs = tuple(sorted(
            f"{decision.population_scope_id}|{decision.threat_id}"
            for decision in report.decisions if decision.mandatory
        ))
        portfolio_payload = {
            "status": "directly_joint_assessed",
            "composition_domain_id": f"{identifier}-joint-domain",
            "population_secret_pairs": list(pairs),
            "registry_head_sha256": "1" * 64,
            "registered_release_ids": [],
            "method": "direct finite joint-channel unit-test replay",
            "joint_upper_bounds": {
                "service-participants-2026|linkage-person": 0.0,
                "service-participants-2026|membership-person": 0.5,
            },
            "joint_experiment_ids": {
                "service-participants-2026|linkage-person": "linkage-portfolio-joint",
                "service-participants-2026|membership-person": "membership-portfolio-joint",
            },
        }
        portfolio_path = report_path.parent / f"{identifier}-portfolio.json"
        portfolio_path.write_text(json.dumps(portfolio_payload) + "\n")
        controls = []
        if with_control:
            control_payload = {
                "control_id": "authenticated-api",
                "control_type": "information_reduction",
                "kind": "interface",
                "description": "authenticated bounded-output API",
                "changes_information_structure": True,
                "credited_for_privacy": True,
                "artifact_sha256": report.artifact_sha256,
                "interface_sha256": interface_sha256,
                "valid_until": "2099-01-01T00:00:00Z",
            }
            control_path = report_path.parent / f"{identifier}-control.json"
            control_path.write_text(json.dumps(control_payload) + "\n")
            controls.append({
                **control_payload,
                "evidence_path": str(control_path),
                "evidence_sha256": sha256_file(control_path),
            })
        return {
            "configuration_id": identifier,
            "name": identifier,
            "is_proposed_configuration": proposed,
            "assessment": {
                "report_path": str(report_path),
                "report_sha256": sha256_file(report_path),
            },
            "release_artifact_path": str(ROOT / "examples" / "artifacts" / "demo-tree.json"),
            "release_artifact_sha256": report.artifact_sha256,
            "release_interface": interface,
            "utility": {
                **utility_payload,
                "source_path": str(utility_path),
                "source_sha256": sha256_file(utility_path),
            },
            "implementation_cost": cost,
            "controls": controls,
            "threat_experiments": [
                {
                    "threat_id": "linkage-person",
                    "assessed_experiment_id": "linkage-assessed",
                    "released_experiment_id": linkage_released,
                    "substitution_certificate_id": linkage_certificate,
                },
                {
                    "threat_id": "membership-person",
                    "assessed_experiment_id": "membership-assessed",
                    "released_experiment_id": "membership-assessed",
                },
            ],
            "portfolio": {
                **portfolio_payload,
                "evidence_path": str(portfolio_path),
                "evidence_sha256": sha256_file(portfolio_path),
            },
        }

    @staticmethod
    def _request(
        experiments: list[dict],
        configurations: list[dict],
        certificates: list[dict] | None = None,
    ) -> OptimizationRequest:
        return OptimizationRequest.model_validate({
            "optimization_id": "release-search",
            "trust_profile": "cooperative",
            "authorization_expires_at": "2099-01-01T00:00:00Z",
            "portfolio_registry_head_sha256": "1" * 64,
            "experiments": experiments,
            "garbling_certificates": certificates or [],
            "configurations": configurations,
            "search_space_status": "candidate_set_only",
        })

    def test_optimizer_selects_releasable_controlled_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            proposed = self._configuration(
                identifier="proposed",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.6,
                cost=0.0,
            )
            controlled = self._configuration(
                identifier="controlled",
                report_path=report_path,
                report=report,
                proposed=False,
                utility_lower=0.8,
                cost=1.0,
                with_control=True,
            )
            request = self._request(self._experiments(report), [proposed, controlled])
            result = ReleaseOptimizer().optimize(request, directory)
            self.assertEqual(result.outcome, "release_with_controls")
            self.assertEqual(result.selected_configuration_id, "controlled")
            self.assertTrue(result.fail_safe_gate_passed)

    def test_optimizer_rejects_uncertified_more_informative_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            interface_sha256 = sha256_bytes(canonical_json_bytes(report.release_interface))
            games = {decision.threat_id: decision.decision_game_sha256 for decision in report.decisions}
            experiments = self._experiments(report)
            detailed = deterministic_experiment(
                experiment_id="linkage-more-informative",
                threat_id="linkage-person",
                population_scope_id="service-participants-2026",
                state_ids=("a", "b", "c", "d"),
                observations=("a", "b", "c", "d"),
                interface_description="uncertified full-detail release",
                decision_game_sha256=games["linkage-person"],
                interface_sha256=interface_sha256,
                artifact_sha256=report.artifact_sha256,
            )
            experiments.append(detailed.model_dump())
            candidate = self._configuration(
                identifier="unsafe-substitution",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
                linkage_released="linkage-more-informative",
            )
            request = self._request(experiments, [candidate])
            result = ReleaseOptimizer().optimize(request, directory)
            self.assertEqual(result.outcome, "redesign_required")
            self.assertFalse(result.fail_safe_gate_passed)
            self.assertIn("lacks its referenced garbling certificate", result.candidate_evaluations[0].reasons[-1])

    def test_approximate_substitution_adds_row_tv_to_the_assessed_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            experiments = self._experiments(report)
            assessed = FiniteExperiment.model_validate(experiments[0])
            released = assessed.model_copy(update={
                "experiment_id": "linkage-approximate",
                "channel": (
                    (0.94, 0.06), (0.94, 0.06),
                    (0.06, 0.94), (0.06, 0.94),
                ),
            })
            experiments.append(released.model_dump())
            certificate = GarblingCertificate(
                certificate_id="approximate-linkage-substitution",
                dominant_experiment_id=assessed.experiment_id,
                dominated_experiment_id=released.experiment_id,
                kernel=((1.0, 0.0), (0.0, 1.0)),
                maximum_row_total_variation=0.06,
                construction="identity observation map with a replayed six-percent row-TV residual",
            )
            candidate = self._configuration(
                identifier="approximate-candidate",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
                linkage_released=released.experiment_id,
                linkage_certificate=certificate.certificate_id,
            )
            request = self._request(experiments, [candidate], [certificate.model_dump()])
            result = ReleaseOptimizer().optimize(request, directory)
            self.assertEqual(result.outcome, "redesign_required")
            self.assertAlmostEqual(
                result.candidate_evaluations[0].substitution_penalties["linkage-person"],
                0.06,
            )
            self.assertTrue(any("raises the certified ceiling" in reason for reason in result.candidate_evaluations[0].reasons))

    def test_utility_floor_precedes_blackwell_minimal_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            experiments = self._experiments(report)
            assessed = FiniteExperiment.model_validate(experiments[0])
            private = deterministic_experiment(
                experiment_id="linkage-less-informative",
                threat_id=assessed.threat_id,
                population_scope_id=assessed.population_scope_id,
                state_ids=assessed.state_ids,
                observations=("constant",) * len(assessed.state_ids),
                prior=assessed.prior,
                interface_description="less informative utility-qualified surface",
                decision_game_sha256=assessed.decision_game_sha256,
                interface_sha256=assessed.interface_sha256,
                artifact_sha256=assessed.artifact_sha256,
            )
            experiments.append(private.model_dump())
            certificate = deterministic_garbling_certificate(
                assessed,
                private,
                certificate_id="linkage-information-minimization",
            )
            cheaper_more_informative = self._configuration(
                identifier="cheap-more-informative",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
            )
            costly_less_informative = self._configuration(
                identifier="costly-less-informative",
                report_path=report_path,
                report=report,
                proposed=False,
                utility_lower=0.71,
                cost=10.0,
                linkage_released=private.experiment_id,
                linkage_certificate=certificate.certificate_id,
            )
            request = self._request(
                experiments,
                [cheaper_more_informative, costly_less_informative],
                [certificate.model_dump()],
            )
            result = ReleaseOptimizer().optimize(request, directory)
            self.assertEqual(result.assurance_frontier_configuration_ids, ("costly-less-informative",))
            self.assertEqual(result.selected_configuration_id, "costly-less-informative")

    def test_unassessed_portfolio_cannot_clear(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            candidate = self._configuration(
                identifier="unassessed-portfolio",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
            )
            candidate["portfolio"] = {
                "status": "unassessed",
                "composition_domain_id": "registered-domain",
                "population_secret_pairs": [
                    "service-participants-2026|linkage-person",
                    "service-participants-2026|membership-person",
                ],
                "registry_head_sha256": "1" * 64,
                "method": "not assessed",
            }
            request = self._request(self._experiments(report), [candidate])
            result = ReleaseOptimizer().optimize(request, directory)
            self.assertFalse(result.fail_safe_gate_passed)
            self.assertIn("portfolio composition is explicitly unassessed", result.candidate_evaluations[0].reasons)

    def test_analytic_incomplete_portfolio_certificate_can_clear(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            candidate = self._configuration(
                identifier="analytic-portfolio",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
            )
            decisions = {decision.threat_id: decision for decision in report.decisions}
            mechanism_path = directory / "analytic-mechanism.json"
            mechanism_path.write_text(json.dumps({
                "method": "unit-test mechanism fixture",
                "claim": "registered transcript is constant in every state",
            }) + "\n")
            problems = {}
            for threat_id, states in (
                ("linkage-person", ("a", "b", "c", "d")),
                ("membership-person", ("member", "nonmember")),
            ):
                width = len(states)
                marginal = ConditionalMarginalBounds(
                    release_id=f"{threat_id}-registered-portfolio",
                    observation_ids=("constant",),
                    lower=tuple((1.0,) for _ in states),
                    upper=tuple((1.0,) for _ in states),
                    evidence=EvidenceReference(
                        evidence_id=f"{threat_id}-marginal",
                        source_path=str(mechanism_path),
                        source_sha256=sha256_file(mechanism_path),
                        supports=(
                            f"marginal:{threat_id}-registered-portfolio",
                            "coverage:deterministic",
                        ),
                    ),
                )
                problem = IncompletePortfolioProblem(
                    portfolio_id=f"{threat_id}-analytic",
                    population_scope_id="service-participants-2026",
                    population_scope_sha256=decisions[threat_id].population_scope_sha256,
                    threat_id=threat_id,
                    decision_game_sha256=decisions[threat_id].decision_game_sha256,
                    state_ids=states,
                    prior=tuple(1.0 / width for _ in states),
                    releases=(
                        marginal,
                        ConditionalMarginalBounds(
                            release_id=(
                                "membership-person-registered-portfolio"
                                if threat_id == "linkage-person"
                                else "linkage-person-registered-portfolio"
                            ),
                            observation_ids=("constant",),
                            lower=tuple((1.0,) for _ in states),
                            upper=tuple((1.0,) for _ in states),
                            evidence=EvidenceReference(
                                evidence_id=f"{threat_id}-second-marginal",
                                source_path=str(mechanism_path),
                                source_sha256=sha256_file(mechanism_path),
                                supports=(
                                    "marginal:membership-person-registered-portfolio"
                                    if threat_id == "linkage-person"
                                    else "marginal:linkage-person-registered-portfolio",
                                    "coverage:deterministic",
                                ),
                            ),
                        ),
                    ),
                    decision_problem=exact_guess_problem(states, f"{threat_id}-exact-guess"),
                    coupling_model=CouplingModel.ARBITRARY,
                    coverage=StatisticalCoverage.DETERMINISTIC,
                    coverage_confidence=1.0,
                    selection_scope="all mandatory portfolio games in the optimization request",
                    prior_evidence=EvidenceReference(
                        evidence_id=f"{threat_id}-prior",
                        source_path=str(mechanism_path),
                        source_sha256=sha256_file(mechanism_path),
                        supports=("prior", "prior:unit-test-uniform"),
                    ),
                    mechanism_assumptions=("registered transcript is constant in every state",),
                    mechanism_evidence=(
                        EvidenceReference(
                            evidence_id=f"{threat_id}-mechanism",
                            source_path=str(mechanism_path),
                            source_sha256=sha256_file(mechanism_path),
                            supports=("coupling:arbitrary",),
                        ),
                    ),
                )
                entry = solve_analytic_portfolio(problem, method="exact")
                assert entry.exact_certificate is not None
                problems[f"service-participants-2026|{threat_id}"] = {
                    "schema_version": entry.schema_version,
                    "problem": problem.model_dump(mode="json"),
                    "exact_certificate": entry.exact_certificate.model_dump(mode="json"),
                    "rational_upper_audit": entry.rational_upper_audit.model_dump(mode="json"),
                }

            portfolio_payload = {
                "status": "analytically_composed",
                "composition_domain_id": "analytic-joint-domain",
                "population_secret_pairs": [
                    "service-participants-2026|linkage-person",
                    "service-participants-2026|membership-person",
                ],
                "registry_head_sha256": "1" * 64,
                "registered_release_ids": [
                    "linkage-person-registered-portfolio",
                    "membership-person-registered-portfolio",
                ],
                "method": "certified incomplete-portfolio ambiguity optimization",
                "joint_upper_bounds": {
                    "service-participants-2026|linkage-person": 0.0,
                    "service-participants-2026|membership-person": 0.5,
                },
                "joint_experiment_ids": {},
                "analytic_assessments": problems,
            }
            portfolio_path = directory / "analytic-portfolio-evidence.json"
            portfolio_path.write_text(json.dumps(portfolio_payload) + "\n")
            candidate["portfolio"] = {
                key: value for key, value in portfolio_payload.items() if key != "analytic_assessments"
            }
            candidate["portfolio"].update({
                "evidence_path": str(portfolio_path),
                "evidence_sha256": sha256_file(portfolio_path),
            })
            request = self._request(self._experiments(report), [candidate])
            result = ReleaseOptimizer().optimize(request, directory)

            self.assertTrue(result.fail_safe_gate_passed)
            self.assertEqual(result.selected_portfolio_status, "analytically_composed")

    def test_separated_assessor_refuses_an_unsigned_assessment(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            candidate = self._configuration(
                identifier="unsigned-separated-assessment",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
            )
            raw = self._request(self._experiments(report), [candidate]).model_dump(mode="json")
            raw["trust_profile"] = "separated_assessor"
            request = OptimizationRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "requires a signed assessment manifest"):
                ReleaseOptimizer().optimize(request, directory)

    def test_adversarial_supply_chain_is_not_silently_downgraded(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            report_path, report = self._write_clear_report(directory)
            candidate = self._configuration(
                identifier="hostile-supply-chain",
                report_path=report_path,
                report=report,
                proposed=True,
                utility_lower=0.8,
                cost=0.0,
            )
            raw = self._request(self._experiments(report), [candidate]).model_dump(mode="json")
            raw["trust_profile"] = "adversarial_supply_chain"
            request = OptimizationRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "unsupported without sandboxed independent artifact replay"):
                ReleaseOptimizer().optimize(request, directory)


if __name__ == "__main__":
    unittest.main()
