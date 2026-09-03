from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from model_release_assurance.decision import decision_game_sha256, population_scope_sha256
from model_release_assurance.decision_theory import exact_guess_problem
from model_release_assurance.incomplete_portfolio import (
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    IncompletePortfolioProblem,
    StatisticalCoverage,
    finite_prior_contract_sha256,
    solve_analytic_portfolio,
)
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes
from model_release_assurance.model_coverage import (
    MODEL_FAMILY_CATALOG,
    assess_request_model_coverage,
    resolve_model_family,
)
from model_release_assurance.models import (
    AnalyzerProvenance,
    AssessmentRequest,
    EvidenceContext,
    FiniteDecisionGame,
    FiniteChannelCeilingInput,
    FiniteGameState,
    RationalProbability,
    ThreatContract,
)
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
FINITE_PATH = "finite_channel_ceiling_complete_declared_interface"


def _evidence_reference(evidence_id: str, *supports: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        source_path="finite-channel-test-evidence.json",
        source_sha256="a" * 64,
        supports=tuple(supports),
    )


def _request_for_family(model_family: str) -> AssessmentRequest:
    raw = json.loads((ROOT / "examples" / "request.json").read_text())
    raw["release"]["model_family"] = model_family
    raw["release"]["model_profile"]["component_model_families"] = [model_family]
    return AssessmentRequest.model_validate(raw)


def _with_finite_game(threat: ThreatContract) -> ThreatContract:
    state_ids = ("a", "b", "c", "d") if threat.kind.value == "linkage" else ("out", "in")
    denominator = len(state_ids)
    game = FiniteDecisionGame(
        game_id=f"finite-{threat.threat_id}",
        states=tuple(
            FiniteGameState(
                state_id=state_id,
                secret_value_definition=f"policy-defined secret state {state_id}",
            )
            for state_id in state_ids
        ),
        prior=tuple(
            RationalProbability(numerator=1, denominator=denominator)
            for _ in state_ids
        ),
        prior_basis="policy-frozen uniform audit game",
        authority="unit-test policy authority",
    )
    return threat.model_copy(update={"finite_game": game})


def _finite_channel_input(
    request: AssessmentRequest,
    threat: ThreatContract,
    *,
    statistical: bool = False,
    bind_complete_release: bool = True,
) -> FiniteChannelCeilingInput:
    scope = next(
        item for item in request.population_scopes
        if item.scope_id == threat.population_scope_id
    )
    if threat.kind.value == "linkage":
        state_ids = ("a", "b", "c", "d")
    else:
        state_ids = ("out", "in")
    prior = tuple(1.0 / len(state_ids) for _ in state_ids)
    rational_prior = tuple(
        RationalProbability(numerator=1, denominator=len(state_ids))
        for _ in state_ids
    )
    coverage = (
        StatisticalCoverage.SIMULTANEOUS
        if statistical
        else StatisticalCoverage.DETERMINISTIC
    )
    release_id = request.release.release_id
    interface_sha256 = sha256_bytes(canonical_json_bytes(request.release.interface))
    release_claims = (
        (
            f"artifact:{request.release.artifact_sha256}",
            f"interface:{interface_sha256}",
            f"complete-transcript:{release_id}",
        )
        if bind_complete_release
        else ()
    )
    problem = IncompletePortfolioProblem(
        portfolio_id=f"finite-{threat.threat_id}",
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        threat_id=threat.threat_id,
        decision_game_sha256=decision_game_sha256(threat, scope),
        state_ids=state_ids,
        prior=prior,
        rational_prior=rational_prior,
        releases=(
            ConditionalMarginalBounds(
                release_id=release_id,
                observation_ids=("response-0", "response-1"),
                lower=tuple((0.5, 0.5) for _ in state_ids),
                upper=tuple((0.5, 0.5) for _ in state_ids),
                evidence=_evidence_reference(
                    f"marginal-{threat.threat_id}",
                    f"marginal:{release_id}",
                    f"coverage:{coverage.value}",
                    *(("confidence-endpoints:outward-validated",)
                      if statistical else ()),
                ),
            ),
        ),
        decision_problem=exact_guess_problem(state_ids, threat.decision_metric),
        coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
        coverage=coverage,
        coverage_confidence=0.95 if statistical else 1.0,
        selection_scope="all frozen states, outputs, and selected release interfaces",
        prior_evidence=_evidence_reference(
            f"prior-{threat.threat_id}",
            "prior",
            f"decision-game:{decision_game_sha256(threat, scope)}",
            "finite-prior:"
            f"{finite_prior_contract_sha256(state_ids, rational_prior)}",
        ),
        mechanism_assumptions=("one complete recipient-visible release transcript",),
        mechanism_evidence=(
            _evidence_reference(
                f"mechanism-{threat.threat_id}",
                f"coupling:{CouplingModel.CONDITIONAL_INDEPENDENCE.value}",
                *release_claims,
            ),
        ),
    )
    context = EvidenceContext(
        release_id=release_id,
        release_contract_sha256=sha256_bytes(canonical_json_bytes(request.release)),
        policy_sha256=request.policy.policy_sha256,
        artifact_sha256=request.release.artifact_sha256,
        interface_sha256=interface_sha256,
        population_scope_id=scope.scope_id,
        population_scope_sha256=population_scope_sha256(scope),
        decision_game_sha256=decision_game_sha256(threat, scope),
        observed_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
    )
    return FiniteChannelCeilingInput(
        threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,
        analytic_evidence=solve_analytic_portfolio(problem, method="envelope"),
        observed_interface_sha256=interface_sha256,
        observed_artifact_sha256=request.release.artifact_sha256,
        interface_observation_definition=(
            "complete serialized response transcript: response-0 or response-1"
        ),
        release_enforced_finite_alphabet=True,
        complete_interface_coverage=True,
        recipient_realizable=True,
        bounded_transcript_complete=True,
        state_trials=tuple(100 for _ in state_ids) if statistical else None,
        evidence_context=context,
        provenance=AnalyzerProvenance(
            tool="finite-channel-test-worker",
            tool_version="1.0",
            producer={
                "service_id": "mra.analyzer.finite-channel-test",
                "service_version": "1.0.0",
                "implementation_sha256": "b" * 64,
                "configuration_sha256": "c" * 64,
            },
            configuration_path="finite-channel-test-config.json",
            source_path="finite-channel-test-evidence.json",
            source_sha256="a" * 64,
            bound_fields=("analytic_evidence", "evidence_context"),
        ),
    )


def _with_finite_inputs(
    request: AssessmentRequest,
    *,
    statistical: bool = True,
) -> AssessmentRequest:
    request = request.model_copy(update={
        "threats": tuple(_with_finite_game(threat) for threat in request.threats),
    })
    return request.model_copy(update={
        "analyzer_inputs": tuple(
            _finite_channel_input(request, threat, statistical=statistical)
            for threat in request.threats
        ),
    })


class ModelCoverageTests(unittest.TestCase):
    def test_catalog_has_unique_all_model_families_and_aliases(self) -> None:
        ids = [entry.family_id for entry in MODEL_FAMILY_CATALOG]
        aliases = [alias for entry in MODEL_FAMILY_CATALOG for alias in entry.aliases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(aliases), len(set(aliases)))
        self.assertGreaterEqual(len(ids), 20)

    def test_common_families_resolve(self) -> None:
        expected = {
            "XGBoost": "tree_ensemble",
            "logistic regression": "linear_generalized_linear",
            "CNN": "vision_model",
            "AlexNet": "vision_model",
            "DenseNet": "vision_model",
            "LLM": "generative_text_llm",
            "Meta-Llama": "generative_text_llm",
            "Mistral": "generative_text_llm",
            "GNN": "graph_model",
            "agentic system": "reinforcement_learning_agent",
        }
        for value, family_id in expected.items():
            self.assertEqual(resolve_model_family(value).family_id, family_id)

    def test_unknown_family_fails_to_custom_review(self) -> None:
        result = resolve_model_family("future-quantum-model")
        self.assertEqual(result.family_id, "custom")
        self.assertEqual(result.status, "custom_review_required")

    def test_request_coverage_reports_missing_scope_without_clearing(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text())
        request = AssessmentRequest.model_validate(raw)
        result = assess_request_model_coverage(request)
        self.assertEqual(result["resolved_family"]["family_id"], "tree_ensemble")
        self.assertFalse(result["can_clear"])
        self.assertTrue(result["coverage_ready"])
        self.assertTrue(result["portfolio_assessment_required"])
        self.assertTrue(result["authoritative_portfolio_registry_required"])
        self.assertIn("attribute", result["missing_recommended_threats"])
        self.assertIn("reconstruction", result["missing_recommended_threats"])
        self.assertFalse(result["threats_without_default_clearing_path"])
        self.assertTrue(all(result["default_clearing_paths"].values()))
        self.assertFalse(any("percent" in key or "fraction" in key for key in result))
        self.assertTrue(result["advisories"])

    def test_non_dp_neural_request_names_missing_default_clearing_paths(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text())
        raw["release"]["model_family"] = "mlp"
        raw["release"]["model_profile"]["component_model_families"] = ["mlp"]
        raw["analyzer_inputs"] = [
            value for value in raw["analyzer_inputs"] if value["analyzer"] == "attack"
        ]
        request = AssessmentRequest.model_validate(raw)
        result = assess_request_model_coverage(request)
        self.assertEqual(
            result["threats_without_default_clearing_path"],
            ["linkage-person", "membership-person"],
        )
        self.assertTrue(
            all(not paths for paths in result["default_clearing_paths"].values())
        )

    def test_complete_finite_channel_is_candidate_route_for_dedicated_family(self) -> None:
        request = _with_finite_inputs(_request_for_family("cnn"))

        result = assess_request_model_coverage(request)

        self.assertEqual(result["resolved_family"]["family_id"], "vision_model")
        self.assertTrue(result["coverage_ready"])
        self.assertFalse(result["can_clear"])
        self.assertFalse(result["threats_without_default_clearing_path"])
        self.assertTrue(all(
            paths == [FINITE_PATH]
            for paths in result["default_clearing_paths"].values()
        ))

    def test_finite_channel_candidate_requires_every_core_eligibility_flag(self) -> None:
        request = _with_finite_inputs(_request_for_family("cnn"))
        flags = (
            "release_enforced_finite_alphabet",
            "complete_interface_coverage",
            "recipient_realizable",
            "bounded_transcript_complete",
        )
        for flag in flags:
            with self.subTest(flag=flag):
                inputs = list(request.analyzer_inputs)
                inputs[0] = inputs[0].model_copy(update={flag: False})
                changed = request.model_copy(update={"analyzer_inputs": tuple(inputs)})

                result = assess_request_model_coverage(changed)

                self.assertNotIn(
                    FINITE_PATH,
                    result["default_clearing_paths"][inputs[0].threat_id],
                )
                self.assertFalse(result["coverage_ready"])

    def test_statistical_finite_channel_candidate_requires_sampling_and_endpoint_proofs(self) -> None:
        request = _with_finite_inputs(_request_for_family("cnn"), statistical=True)
        self.assertTrue(assess_request_model_coverage(request)["coverage_ready"])
        inputs = list(request.analyzer_inputs)
        value = inputs[0]
        problem = value.analytic_evidence.problem
        marginal = problem.releases[0]
        evidence = marginal.evidence.model_copy(update={
            "supports": tuple(
                claim
                for claim in marginal.evidence.supports
                if claim != "confidence-endpoints:outward-validated"
            ),
        })
        changed_problem = problem.model_copy(update={
            "releases": (marginal.model_copy(update={"evidence": evidence}),),
        })
        inputs[0] = value.model_copy(update={
            "analytic_evidence": solve_analytic_portfolio(
                changed_problem,
                method="envelope",
            ),
        })
        changed = request.model_copy(update={"analyzer_inputs": tuple(inputs)})
        result = assess_request_model_coverage(changed)
        self.assertNotIn(
            FINITE_PATH,
            result["default_clearing_paths"][inputs[0].threat_id],
        )
        self.assertFalse(result["coverage_ready"])

    def test_deterministic_finite_channel_requires_point_valued_rows(self) -> None:
        request = _with_finite_inputs(
            _request_for_family("cnn"),
            statistical=False,
        )
        value = request.analyzer_inputs[0]
        self.assertIsInstance(value, FiniteChannelCeilingInput)
        self.assertFalse(assess_request_model_coverage(request)["coverage_ready"])
        release = value.analytic_evidence.problem.releases[0]
        widened_release = release.model_copy(update={
            "upper": tuple((0.6, 0.6) for _ in release.upper),
        })
        widened_problem = value.analytic_evidence.problem.model_copy(update={
            "releases": (widened_release,),
        })
        changed = value.model_copy(update={
            "analytic_evidence": solve_analytic_portfolio(
                widened_problem,
                method="envelope",
            ),
        })

        with self.assertRaisesRegex(ValidationError, "point-valued channel rows"):
            FiniteChannelCeilingInput.model_validate(
                changed.model_dump(mode="python", exclude_none=False)
            )

    def test_finite_channel_candidate_requires_release_and_context_bindings(self) -> None:
        request = _with_finite_inputs(_request_for_family("cnn"))
        original = request.analyzer_inputs[0]
        variants = {
            "observed artifact": original.model_copy(
                update={"observed_artifact_sha256": "f" * 64}
            ),
            "context release": original.model_copy(update={
                "evidence_context": original.evidence_context.model_copy(
                    update={"release_id": "another-release"}
                ),
            }),
            "certificate release": original.model_copy(update={
                "analytic_evidence": original.analytic_evidence.model_copy(update={
                    "problem": original.analytic_evidence.problem.model_copy(update={
                        "releases": (
                            original.analytic_evidence.problem.releases[0].model_copy(
                                update={"release_id": "another-release"}
                            ),
                        ),
                    }),
                }),
            }),
        }
        for label, changed_input in variants.items():
            with self.subTest(binding=label):
                inputs = (changed_input, *request.analyzer_inputs[1:])
                changed = request.model_copy(update={"analyzer_inputs": inputs})

                result = assess_request_model_coverage(changed)

                self.assertNotIn(
                    FINITE_PATH,
                    result["default_clearing_paths"][changed_input.threat_id],
                )

    def test_finite_channel_candidate_requires_complete_release_claims(self) -> None:
        request = _with_finite_inputs(_request_for_family("cnn"))
        unbound = _finite_channel_input(
            request,
            request.threats[0],
            bind_complete_release=False,
        )
        changed = request.model_copy(update={
            "analyzer_inputs": (unbound, *request.analyzer_inputs[1:]),
        })

        result = assess_request_model_coverage(changed)

        self.assertNotIn(
            FINITE_PATH,
            result["default_clearing_paths"][unbound.threat_id],
        )
        self.assertFalse(result["coverage_ready"])

    def test_finite_channel_candidate_rejects_unsupported_metric(self) -> None:
        request = _request_for_family("cnn")
        membership = next(
            threat for threat in request.threats if threat.kind.value == "membership"
        ).model_copy(update={
            "decision_metric": "membership_tpr_at_fpr",
            "metric_parameters": {"target_fpr": 0.001},
        })
        threats = tuple(
            membership if threat.kind.value == "membership" else threat
            for threat in request.threats
        )
        request = request.model_copy(update={"threats": threats})
        request = _with_finite_inputs(request)

        result = assess_request_model_coverage(request)

        self.assertNotIn(
            FINITE_PATH,
            result["default_clearing_paths"][membership.threat_id],
        )
        self.assertFalse(result["coverage_ready"])

    def test_finite_channel_does_not_make_unknown_custom_family_ready(self) -> None:
        request = _with_finite_inputs(_request_for_family("future-quantum-model"))

        result = assess_request_model_coverage(request)

        self.assertEqual(result["resolved_family"]["family_id"], "custom")
        self.assertFalse(result["coverage_ready"])
        self.assertTrue(all(
            FINITE_PATH not in paths
            for paths in result["default_clearing_paths"].values()
        ))
        self.assertIn("model_family is not in the governed catalog", result["reasons"])

    def test_interactive_caution_requires_complete_bounded_transcript_routes(self) -> None:
        request = _request_for_family("llm")
        # Isolate the coverage planner's protocol branch; InterfaceContract validation is
        # independently exercised by the framework tests.
        interface = request.release.interface.model_copy(
            update={"protocol_type": "interactive_llm", "query_budget": 100}
        )
        release = request.release.model_copy(update={"interface": interface})
        request = request.model_copy(update={"release": release})
        complete = _with_finite_inputs(request)

        result = assess_request_model_coverage(complete)

        self.assertTrue(result["coverage_ready"])
        self.assertNotIn(
            "interactive transcript clearance is deliberately unsupported",
            result["reasons"],
        )

        partial = complete.model_copy(update={
            "analyzer_inputs": complete.analyzer_inputs[:-1],
        })
        partial_result = assess_request_model_coverage(partial)
        self.assertFalse(partial_result["coverage_ready"])
        self.assertIn(
            "interactive transcript clearance is deliberately unsupported",
            partial_result["reasons"],
        )

    def test_assessment_v5_requires_a_structured_model_profile(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text())
        raw["release"].pop("model_profile")
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_cli_lists_catalog_and_reviews_request(self) -> None:
        base = [sys.executable, "-m", "model_release_assurance", "model-coverage"]
        listing = subprocess.run(base + ["--json"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(listing.returncode, 0, msg=listing.stderr)
        self.assertGreaterEqual(len(json.loads(listing.stdout)), 20)
        review = subprocess.run(
            base + [str(ROOT / "examples" / "request.json"), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(review.returncode, 0, msg=review.stderr)
        self.assertFalse(json.loads(review.stdout)["can_clear"])


if __name__ == "__main__":
    unittest.main()
