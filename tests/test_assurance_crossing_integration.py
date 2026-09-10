"""Fresh synthetic-channel integration; no mocked import/security validators.

This exercises the actual compiler, engine and four-verdict signature gate.
The test freezes a synthetic binary mechanism, policy and sampling design before
making seeded pseudorandom draws. It is not a trained-model experiment, an
independent worker attestation, or evidence of real-world taxonomy completeness.
The IID statistical interpretation is the declared ideal sampling model;
deterministic seeded replay is used for a stable software regression.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import random
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization

from model_release_assurance.analyzers.finite_channel import FiniteChannelCeilingAnalyzer
from model_release_assurance.assurance_record import (
    AssuranceScope, AssuranceVerdict, build_assurance_record, declared_export_channels, gate_assurance_record,
    sign_assurance_record, sign_residual_risk_acceptance,
)
from model_release_assurance.decision import decision_game_sha256, population_scope_sha256
from model_release_assurance.decision_theory import exact_guess_problem
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.incomplete_portfolio import (
    CouplingModel, EvidenceReference, FiniteStatePriorEvidence,
    finite_prior_contract_sha256, solve_analytic_portfolio,
)
from model_release_assurance.integrity import (
    canonical_json_bytes, generate_ed25519_keypair, sha256_bytes, sha256_file, signer_key_id,
)
from model_release_assurance.models import (
    AnalyzerProvenance, AnalyzerRequirement, AssessmentRequest, EvidenceBindingContext,
    EvidenceContext, FiniteChannelCeilingInput, FiniteDecisionGame, FiniteGameState,
    InterfaceContract, PolicyBundle, PolicyReference, PolicyRule, PopulationScope, RationalProbability,
    ReleaseContract, ThreatContract,
)
from model_release_assurance.portfolio_statistics import (
    AssuranceErrorBudget, ErrorBudgetAllocation, IncompletePortfolioSpecification,
    MultinomialCountsFile, MultinomialEvidenceRequest, MultinomialReleaseCounts,
    MultinomialSamplingPlan, MultinomialSamplingPlanRelease, MultinomialStateCounts,
    SourceFileReference, compile_multinomial_portfolio_problem,
    generate_simultaneous_multinomial_evidence,
)
from model_release_assurance.services import AnalyzerServiceRegistry, LocalAnalyzerService


ROOT = Path(__file__).resolve().parents[1]
SEED, TRIALS_PER_STATE, THRESHOLD = 20260907, 100, 0.55


def _write(path: Path, value) -> None:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash(value) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _reference(path: Path, source_id: str) -> SourceFileReference:
    return SourceFileReference(source_id=source_id, source_path=path.name, source_sha256=sha256_file(path))


def fresh_synthetic_crossing(base: Path):
    """Create all sources afresh; no retained example evidence is restamped."""
    template = AssessmentRequest.model_validate_json((ROOT / "examples/request.json").read_bytes())
    now = datetime.now(timezone.utc)
    artifact_path = base / "synthetic-mechanism.json"
    config_path, policy_path = base / "analyzer-config.json", base / "policy.json"
    plan_path, budget_path = base / "plan.json", base / "budget.json"
    prior_path, mechanism_path = base / "prior.json", base / "mechanism-claims.json"
    observations_path, counts_path = base / "observations.json", base / "counts.json"
    evidence_path, input_path = base / "simultaneous.json", base / "analyzer-input.json"
    mechanism = {
        "mechanism": "state-independent-binary-output",
        "states": ["out", "in"], "observations": ["zero", "one"],
        "conditional_rows": [[0.5, 0.5], [0.5, 0.5]],
        "description": "Each one-query logical transcript is one fair bit; ancillary fields are constant.",
        "scope": "synthetic logical mechanism only; no trained model or live endpoint",
    }
    _write(artifact_path, mechanism)
    _write(config_path, {"fixture_seed": SEED, "trials_per_state": TRIALS_PER_STATE,
                         "threshold": THRESHOLD, "sampler_source_sha256": sha256_file(Path(__file__))})
    raw_interface = template.release.interface.model_dump(mode="json")
    raw_interface.update(access="label", outputs=["synthetic_bit"], precision_bits=1,
                         query_budget=1, adaptive_queries=False, authenticated=False,
                         rate_limited=False, llm_protocol=None, protocol_type="predictive")
    raw_interface["output_channels"] = {
        **{key: False for key in ("aggregates", "labels", "scores", "probabilities", "logits", "explanations", "text", "embeddings", "gradients", "parameters")},
        "labels": True, "downloadable_files": [], "shipped_summary_metadata": [], "custom_channels": [],
    }
    raw_interface["rate_limit"] = {
        "enabled": False, "scope": "none", "requests_per_window": None, "window_seconds": None,
        "burst_capacity": None, "retry_after_exposed": False, "enforcement": "not_applicable", "custom_parameters": {},
    }
    raw_interface["timing"] = {"recipient_observable": False, "measurement_resolution_milliseconds": None,
                               "includes_queue_time": False, "mitigation": "not_applicable", "mitigation_parameters": {}}
    raw_interface["errors"] = {"transport_status": "none", "documented_status_codes": [],
                               "error_content": "none", "error_schema_sha256": None, "retry_metadata": False}
    raw_interface["execution"] = {"batching": "none", "maximum_batch_size": 1, "maximum_concurrent_requests": 1,
                                  "cross_request_state": "none", "cross_request_state_ttl_seconds": None}
    raw_interface["access_paths"] = {"side_channels": [], "custom_side_channels": [], "admin_access": "none",
                                     "admin_capabilities": [], "local_access": "none", "local_capabilities": []}
    interface = InterfaceContract.model_validate(raw_interface)
    release_raw = template.release.model_dump(mode="json")
    release_raw.update(release_id="fresh-synthetic-binary-channel", artifact_path=artifact_path.name,
                       artifact_sha256=sha256_file(artifact_path), interface=interface.model_dump(mode="json"),
                       model_family="synthetic_finite_channel", protected_unit="record", previous_release_ids=[],
                       purpose="Exercise protocol integration with an actually sampled synthetic finite mechanism",
                       expires_at=(now + timedelta(days=1)).isoformat())
    release = ReleaseContract.model_validate(release_raw)
    population = PopulationScope.model_validate({
        "scope_id": "synthetic-single-target", "name": "One artificial target record",
        "unit_kind": "record", "universe_definition": "One synthetic target, with IN/OUT being its hidden state rather than real personal data",
        "inclusion_criteria": ["the fixture's single artificial target"], "jurisdictions": ["synthetic-test-only"],
        "reference_date": now.date(), "valid_until": (now + timedelta(days=1)).date(),
        "population_snapshot_sha256": sha256_file(artifact_path),
        "size": {"basis": "exact_registry", "lower_bound": 1, "point_estimate": 1, "upper_bound": 1,
                 "source": "the fixture defines exactly one target", "measured_at": now},
        "data_steward": "regression fixture authority",
    })
    half = RationalProbability(numerator=1, denominator=2)
    game = FiniteDecisionGame(
        game_id="synthetic-equal-prior-membership", states=(
            FiniteGameState(state_id="out", secret_value_definition="synthetic OUT state, not a real training record"),
            FiniteGameState(state_id="in", secret_value_definition="synthetic IN state, not a real training record"),
        ), prior=(half, half), prior_basis="declared balanced synthetic state game", authority="regression fixture authority",
    )
    threat_raw = next(t for t in template.threats if t.kind.value == "membership").model_dump(mode="json")
    threat_raw.update(threat_id="synthetic-membership", tolerance=THRESHOLD, finite_game=game.model_dump(mode="json"),
                      secret="synthetic IN versus OUT state", prior="equal prior over two synthetic states",
                      population_scope_id=population.scope_id,
                      side_information=["public state-independent mechanism definition; no observation of the secret state"])
    threat = ThreatContract.model_validate(threat_raw)
    service = LocalAnalyzerService(FiniteChannelCeilingAnalyzer())
    policy = PolicyBundle(
        policy_id="fresh-synthetic-policy", policy_version="1.0.0", effective_from=now,
        expires_at=now + timedelta(days=1),
        rules=(PolicyRule(threat_id=threat.threat_id, kind=threat.kind, mandatory=True,
            decision_metric=threat.decision_metric, metric_parameters=threat.metric_parameters,
            finite_game=game, tolerance=THRESHOLD, tolerance_basis=threat.tolerance_basis,
            ceiling_attack_battery_mode="waived",
            ceiling_attack_battery_waiver_reason="Synthetic channel integration checks the finite statistical proof path, not a model red-team battery"),),
        analyzer_requirements=(AnalyzerRequirement(threat_id=threat.threat_id, analyzer=service.descriptor.input_kind,
            minimum_service_version=service.descriptor.service_version,
            accepted_implementation_sha256s=(service.descriptor.implementation_sha256,),
            accepted_configuration_sha256s=(sha256_file(config_path),)),),
        accepted_selection_policy_sha256s=("0" * 64,),
    )
    _write(policy_path, policy)
    binding = EvidenceBindingContext(
        release_id=release.release_id, release_contract_sha256=_hash(release), policy_sha256=sha256_file(policy_path),
        artifact_sha256=release.artifact_sha256, interface_sha256=_hash(interface),
        population_scope_id=population.scope_id, population_scope_sha256=population_scope_sha256(population),
        decision_game_sha256=decision_game_sha256(threat, population),
    )
    plan = MultinomialSamplingPlan(
        plan_id="fresh-synthetic-plan", family_id="fresh-synthetic-family", portfolio_id="fresh-synthetic-portfolio",
        population_scope_id=population.scope_id, threat_id=threat.threat_id, registered_at=datetime.now(timezone.utc),
        state_ids=game.state_ids, releases=(MultinomialSamplingPlanRelease(
            release_id=release.release_id, observation_ids=tuple(mechanism["observations"])),),
        minimum_trials_per_state=TRIALS_PER_STATE, selection_scope="all two states and all binary outputs, one look only",
        audit_sample_definition=f"seed={SEED}; {TRIALS_PER_STATE} state-independent bit draws per state; ideal IID model, seeded regression replay",
        binding_context=binding,
    )
    _write(plan_path, plan)
    budget = AssuranceErrorBudget(
        budget_id="fresh-synthetic-budget", authority="regression fixture authority", committed_at=datetime.now(timezone.utc),
        period_start=now.date(), period_end=(now + timedelta(days=2)).date(), total_alpha=0.05,
        allocations=(ErrorBudgetAllocation(allocation_id="fresh-synthetic-allocation", generation_id="fresh-synthetic-generation",
            family_id=plan.family_id, portfolio_id=plan.portfolio_id, population_scope_id=population.scope_id,
            threat_id=threat.threat_id, sampling_plan_sha256=sha256_file(plan_path), alpha=0.05, binding_context=binding),),
    )
    _write(budget_path, budget)
    prior = FiniteStatePriorEvidence(threat_id=threat.threat_id, population_scope_id=population.scope_id,
        population_scope_sha256=binding.population_scope_sha256, decision_game_sha256=binding.decision_game_sha256,
        state_ids=game.state_ids, prior=game.prior, prior_definition=game.prior_basis, authority=game.authority)
    _write(prior_path, prior)
    claims = ("coupling:conditional_independence", f"artifact:{release.artifact_sha256}",
              f"interface:{binding.interface_sha256}", f"complete-transcript:{release.release_id}")
    _write(mechanism_path, {"claims": claims, "logical_mechanism": mechanism,
                          "scope": "declared synthetic logical transcript; no external live-interface attestation"})
    inventory = declared_export_channels(interface)
    exported = tuple(name for name, visible in inventory.items() if visible)
    scope = AssuranceScope.model_validate({
        "scope_id": "fresh-synthetic-assurance-scope",
        "adversary": {"access_levels": [interface.access],
            "auxiliary_knowledge": {threat.threat_id: threat.side_information},
            "metadata_profiles": {threat.threat_id: threat.adversary_metadata_profile},
            "query_budget": interface.query_budget, "adaptive_queries": interface.adaptive_queries,
            "joint_transcript_description": "One synthetic bit jointly with all fixed ancillary logical observations; no live-service claim"},
        "declared_scenario_ids": ["synthetic-membership-scenario"],
        "scenarios": [{"scenario_id": "synthetic-membership-scenario", "threat_id": threat.threat_id,
                       "description": "Guess the artificial target's balanced IN/OUT state", "channel_ids": exported}],
        "out_of_scope": [], "channels": [{"channel_id": name, "exported": visible,
            "threat_ids": [threat.threat_id] if visible else [],
            "reason": "Explicit inventory of the declared synthetic logical interface"} for name, visible in inventory.items()],
        "residual_risk_acceptance_permitted": True,
        "approved_at": datetime.now(timezone.utc), "expires_at": now + timedelta(days=1),
    })
    scope_path = base / "scope.json"
    _write(scope_path, scope)
    frozen_paths = (artifact_path, config_path, policy_path, plan_path, budget_path, prior_path, mechanism_path, scope_path)
    frozen_hashes = {path.name: sha256_file(path) for path in frozen_paths}
    _write(base / "before-sampling.json", frozen_hashes)

    # Actual observations are generated only after the complete design is saved.
    started = datetime.now(timezone.utc)
    rng = random.Random(SEED)
    loaded_mechanism = json.loads(artifact_path.read_text(encoding="utf-8"))
    observed = {}
    for state, probabilities in zip(loaded_mechanism["states"], loaded_mechanism["conditional_rows"], strict=True):
        observed[state] = ["zero" if rng.random() < probabilities[0] else "one" for _ in range(TRIALS_PER_STATE)]
    ended = datetime.now(timezone.utc)
    _write(observations_path, {"seed": SEED, "started_at": started.isoformat(), "ended_at": ended.isoformat(), "observations": observed})
    counts = MultinomialCountsFile(
        count_file_id="fresh-synthetic-counts", sampling_plan_id=plan.plan_id, sampling_plan_sha256=sha256_file(plan_path),
        portfolio_id=plan.portfolio_id, population_scope_id=population.scope_id, threat_id=threat.threat_id,
        family_id=plan.family_id, sampling_started_at=started, sampling_ended_at=ended,
        audit_sample_sha256=sha256_file(observations_path), sampling_protocol=plan.audit_sample_definition,
        state_ids=game.state_ids, releases=(MultinomialReleaseCounts(release_id=release.release_id,
            observation_ids=tuple(mechanism["observations"]), state_rows=tuple(
                MultinomialStateCounts(state_id=state, counts=tuple(Counter(observed[state])[o] for o in mechanism["observations"]))
                for state in game.state_ids)),), binding_context=binding,
    )
    _write(counts_path, counts)
    if frozen_hashes != {path.name: sha256_file(path) for path in frozen_paths}:
        raise AssertionError("premeasurement design changed after sampling")
    evidence_request = MultinomialEvidenceRequest(
        generation_id="fresh-synthetic-generation", allocation_id="fresh-synthetic-allocation",
        sampling_plan_reference=_reference(plan_path, "fresh-plan-source"),
        counts_reference=_reference(counts_path, "fresh-counts-source"), budget_reference=_reference(budget_path, "fresh-budget-source"),
        family_pre_registered=True, all_cells_reported=True, selection_process_covered=True,
        assurance_ledger_complete=True, selection_scope=plan.selection_scope,
    )
    evidence = generate_simultaneous_multinomial_evidence(evidence_request, base)
    _write(evidence_path, evidence)
    specification = IncompletePortfolioSpecification(
        portfolio_id=plan.portfolio_id, population_scope_id=population.scope_id,
        population_scope_sha256=binding.population_scope_sha256, threat_id=threat.threat_id,
        decision_game_sha256=binding.decision_game_sha256, prior=(0.5, 0.5), rational_prior=prior.prior,
        decision_problem=exact_guess_problem(game.state_ids, problem_id=game.game_id), coupling_model=CouplingModel.CONDITIONAL_INDEPENDENCE,
        prior_evidence=EvidenceReference(evidence_id="fresh-prior", source_path=prior_path.name, source_sha256=sha256_file(prior_path),
            supports=("prior", f"decision-game:{binding.decision_game_sha256}", f"finite-prior:{finite_prior_contract_sha256(game.state_ids, game.prior)}")),
        mechanism_assumptions=("one complete synthetic one-bit logical transcript",),
        mechanism_evidence=(EvidenceReference(evidence_id="fresh-mechanism", source_path=mechanism_path.name,
            source_sha256=sha256_file(mechanism_path), supports=claims),),
    )
    problem = compile_multinomial_portfolio_problem(evidence, specification,
        evidence_source_path=evidence_path.name, evidence_source_sha256=sha256_file(evidence_path))
    entry = solve_analytic_portfolio(problem, method="envelope")
    input_payload = dict(
        analyzer="finite_channel_ceiling", schema_version="1.0", threat_id=threat.threat_id,
        population_scope_id=population.scope_id, analytic_evidence=entry.model_dump(mode="json"),
        observed_interface_sha256=binding.interface_sha256, observed_artifact_sha256=release.artifact_sha256,
        interface_observation_definition="the one-bit synthetic response; all declared ancillary logical observations are constant",
        release_enforced_finite_alphabet=True, complete_interface_coverage=True, recipient_realizable=True,
        bounded_transcript_complete=True, state_trials=[TRIALS_PER_STATE, TRIALS_PER_STATE],
        evidence_context=EvidenceContext(**binding.model_dump(mode="python", exclude={"schema_version"}), observed_at=datetime.now(timezone.utc)).model_dump(mode="json"),
    )
    _write(input_path, input_payload)
    provenance = AnalyzerProvenance(tool="fresh-synthetic-test-sampler", tool_version=service.descriptor.service_version,
        producer={"service_id": service.descriptor.service_id, "service_version": service.descriptor.service_version,
                  "implementation_sha256": service.descriptor.implementation_sha256, "configuration_sha256": sha256_file(config_path)},
        configuration_path=config_path.name, source_path=input_path.name, source_sha256=sha256_file(input_path),
        bound_fields=tuple(input_payload))
    value = FiniteChannelCeilingInput.model_validate({**input_payload, "provenance": provenance})
    request = AssessmentRequest(policy=PolicyReference(policy_id=policy.policy_id, policy_version=policy.policy_version,
        policy_path=policy_path.name, policy_sha256=sha256_file(policy_path)), release=release,
        population_scopes=(population,), threats=(threat,), analyzer_inputs=(value,))
    _write(base / "request.json", request)
    report = AssuranceEngine(service_registry=AnalyzerServiceRegistry((service,))).assess(request, base)
    _write(base / "report.json", report)
    return request, report, policy_path.read_bytes(), counts, frozen_hashes


class FreshAssuranceCrossingIntegration(unittest.TestCase):
    def test_fresh_counts_engine_interval_signed_acceptance_and_semantic_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            request, report, policy_bytes, counts, frozen = fresh_synthetic_crossing(base)
            self.assertEqual([sum(r.counts) for r in counts.releases[0].state_rows], [TRIALS_PER_STATE] * 2)
            self.assertEqual(frozen, {name: sha256_file(base / name) for name in frozen})
            self.assertEqual(counts.audit_sample_sha256, sha256_file(base / "observations.json"))
            scope = AssuranceScope.model_validate_json((base / "scope.json").read_bytes())
            record = build_assurance_record(request, report, scope, policy_bytes=policy_bytes)
            self.assertEqual(record.verdict, AssuranceVerdict.BLOCK)
            interval = record.threats[0]
            self.assertLessEqual(interval.floor.as_fraction(), interval.threshold.as_fraction())
            self.assertLess(interval.threshold.as_fraction(), interval.ceiling.as_fraction())
            self.assertIsNone(interval.resolution_code)
            self.assertFalse(interval.resolving_actions)
            self.assertIn("verified applicable resolving plan", record.blocking_reasons[0])
            # The internal scientific suggestion remains advisory, not an
            # attestation that fresh budget/data or a resolving plan exists.
            self.assertEqual(report.decisions[0].resolution.code, "recollect_more_state_conditioned_samples")
            record_private, record_public = base / "record-private.pem", base / "record-public.pem"
            accept_private, accept_public = base / "accept-private.pem", base / "accept-public.pem"
            generate_ed25519_keypair(record_private, record_public)
            generate_ed25519_keypair(accept_private, accept_public)
            def trust(path):
                return {signer_key_id(serialization.load_pem_public_key(path.read_bytes())): path}
            acceptance = sign_residual_risk_acceptance(record, accept_private,
                reason="Synthetic regression authority accepts precisely the documented conditional residual ceiling for this fixture",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
            accepted = build_assurance_record(request, report, scope, policy_bytes=policy_bytes,
                acceptance=acceptance, trusted_acceptors=trust(accept_public))
            self.assertEqual(accepted.verdict, AssuranceVerdict.RELEASE_WITH_RISK)
            self.assertEqual(acceptance.accepted_ceilings, {interval.threat_id: interval.ceiling})
            # A genuine acceptor signature over a smaller, wrong ceiling is
            # insufficient: acceptance must describe the replayed actual bound.
            wrong_ceiling = Fraction(3, 5)
            wrong_gap = wrong_ceiling - interval.floor.as_fraction()
            altered_interval = interval.model_copy(update={
                "ceiling": RationalProbability(numerator=3, denominator=5),
                "gap": RationalProbability(numerator=wrong_gap.numerator, denominator=wrong_gap.denominator),
            })
            understated = sign_residual_risk_acceptance(record.model_copy(update={"threats": (altered_interval,)}),
                accept_private, reason="Synthetic authority signs an intentionally understated ceiling to test exact binding rejection",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
            rejected = build_assurance_record(request, report, scope, policy_bytes=policy_bytes,
                acceptance=understated, trusted_acceptors=trust(accept_public))
            self.assertEqual(rejected.verdict, AssuranceVerdict.BLOCK)
            self.assertTrue(any("exact ceiling" in reason for reason in rejected.blocking_reasons))
            signed = sign_assurance_record(accepted, record_private)
            gate = gate_assurance_record(signed, request, report, scope, policy_bytes=policy_bytes,
                trusted_record_keys=trust(record_public), trusted_acceptors=trust(accept_public))
            self.assertEqual(gate.verdict, AssuranceVerdict.RELEASE_WITH_RISK)
            self.assertTrue(gate.recommendation_passed)
            self.assertFalse(gate.authorization_eligible)
            revoked = gate_assurance_record(signed, request, report, scope, policy_bytes=policy_bytes,
                trusted_record_keys=trust(record_public), trusted_acceptors={})
            self.assertEqual(revoked.verdict, AssuranceVerdict.BLOCK)
            self.assertFalse(revoked.recommendation_passed)
            expired = gate_assurance_record(signed, request, report, scope, policy_bytes=policy_bytes,
                trusted_record_keys=trust(record_public), trusted_acceptors=trust(accept_public), as_of=acceptance.expires_at)
            self.assertEqual(expired.verdict, AssuranceVerdict.BLOCK)
            self.assertFalse(expired.recommendation_passed)


if __name__ == "__main__":
    unittest.main()
