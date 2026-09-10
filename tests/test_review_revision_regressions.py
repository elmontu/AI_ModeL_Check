"""Counterexample regressions; synthetic software checks, not deployment evidence."""
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

from test_finite_channel_ceiling import _fixture
import test_counterproof_optimizer_regressions as optimizer_fixtures
from model_release_assurance.analyzers.finite_channel import FiniteChannelCeilingAnalyzer
from model_release_assurance.decision import decide_threat
from model_release_assurance.integrity import sha256_file
from model_release_assurance.models import AttackBatteryStatus, CeilingAttackBatteryMode, Verdict
from model_release_assurance.optimizer import OptimizationRequest, ReleaseOptimizer


class ReviewRevisionRegressions(unittest.TestCase):
    def test_prior_strategy_blocks_below_baseline_and_preserves_equality(self):
        for threshold, expected in ((0.4, Verdict.BLOCK), (0.5, Verdict.INCONCLUSIVE)):
            with self.subTest(threshold=threshold):
                release, threat, scope, value = _fixture(
                    ((0.2, 0.2), (0.2, 0.2)), ((0.8, 0.8), (0.8, 0.8)), tolerance=threshold)
                records = FiniteChannelCeilingAnalyzer().analyze(release, threat, value)
                self.assertEqual(records[0].exact_lower.as_fraction(), Fraction(1, 2))
                battery = AttackBatteryStatus(mode=CeilingAttackBatteryMode.WAIVED,
                    satisfied=True, waiver_reason="synthetic test policy")
                decision = decide_threat(threat, scope, release, records,
                    value.evidence_context.policy_sha256, battery)
                self.assertEqual(decision.lower_bound_fraction.as_fraction(), Fraction(1, 2))
                self.assertEqual(decision.verdict, expected)
                # The game itself supports baseline even if no analyzer ran.
                no_evidence = decide_threat(threat, scope, release, (),
                    value.evidence_context.policy_sha256, battery)
                self.assertEqual(no_evidence.lower_bound_fraction.as_fraction(), Fraction(1, 2))
                self.assertEqual(no_evidence.verdict, expected)

    def test_incremental_metric_does_not_receive_absolute_prior_floor(self):
        release, threat, scope, value = _fixture(
            ((0.2, 0.2), (0.2, 0.2)), ((0.8, 0.8), (0.8, 0.8)))
        # Isolated decision algebra: the typed finite exact-guess linkage game
        # has the same prior but reports improvement over ignoring the release.
        raw = threat.model_dump(mode="python")
        raw.update(kind="linkage", decision_metric="incremental_bayes_linkage_success",
            tolerance_basis="incremental", tolerance=0.1, candidate_set="two candidates",
            target_signal_source="synthetic bit", realizability="recipient_realizable")
        threat = type(threat).model_validate(raw)
        decision = decide_threat(threat, scope, release, (), value.evidence_context.policy_sha256,
            AttackBatteryStatus(mode=CeilingAttackBatteryMode.WAIVED,
                satisfied=True, waiver_reason="synthetic test policy"))
        self.assertEqual(decision.lower_bound_fraction.as_fraction(), 0)
        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)

    def test_nonuniform_prior_is_exact_and_display_rounds_outward(self):
        release, threat, scope, value = _fixture(
            ((0.2, 0.2), (0.2, 0.2)), ((0.8, 0.8), (0.8, 0.8)))
        raw = threat.model_dump(mode="json")
        raw.update(kind="attribute", decision_metric="finite_secret_exact_guess_success",
                   metric_parameters={"maximum_secret_prior": 0.9}, tolerance=0.8)
        raw["finite_game"]["prior"] = [{"numerator": 1, "denominator": 6},
                                        {"numerator": 5, "denominator": 6}]
        threat = type(threat).model_validate(raw)
        decision = decide_threat(threat, scope, release, (), value.evidence_context.policy_sha256,
            AttackBatteryStatus(mode=CeilingAttackBatteryMode.WAIVED,
                satisfied=True, waiver_reason="synthetic test policy"))
        self.assertEqual(decision.lower_bound_fraction.as_fraction(), Fraction(5, 6))
        self.assertLessEqual(Fraction(str(decision.lower_bound)), Fraction(5, 6))
        self.assertEqual(decision.verdict, Verdict.BLOCK)

    def test_revocation_cannot_remove_a_previously_disclosed_release_from_portfolio(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            helper = optimizer_fixtures.OptimizerCounterproofRegressions()
            raw, _ = helper._fixture(base)
            self.assertTrue(helper._run(raw, base).fail_safe_gate_passed)
            registry = raw["portfolio_registry"]
            # The old release has no live service, but recipients retain it.
            registry["active_release_ids"] = []
            registry["disclosed_release_ids"] = ["revoked-but-observed"]
            path = Path(registry["source_path"])
            payload = {k: v for k, v in registry.items() if k not in {"source_path", "source_sha256"}}
            path.write_text(json.dumps(payload), encoding="utf-8")
            registry["source_sha256"] = sha256_file(path)
            with self.assertRaisesRegex(ValueError, "cumulative disclosure history"):
                helper._run(raw, base)
            # XOR witness: the retained pad and a later masked secret reveal
            # the secret, even though each marginal success is only one half.
            outcomes = [(s, r, s ^ r) for s in (0, 1) for r in (0, 1)]
            self.assertTrue(all((pad ^ masked) == s for s, pad, masked in outcomes))
            self.assertEqual(sum(s == pad for s, pad, _ in outcomes), 2)
            self.assertEqual(sum(s == masked for s, _, masked in outcomes), 2)

    def test_legacy_snapshot_without_history_is_inspectable_but_not_eligible(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            helper = optimizer_fixtures.OptimizerCounterproofRegressions()
            raw, _ = helper._fixture(base)
            raw["portfolio_registry"].pop("disclosed_release_ids")
            raw["portfolio_registry"]["schema_version"] = "1.0"
            request = OptimizationRequest.model_validate(raw)
            with self.assertRaisesRegex(ValueError, "cumulative disclosure history"):
                ReleaseOptimizer().optimize(request, base)

    def test_optional_nonclear_verdict_never_passes_mandatory_only_overall(self):
        # Unit boundary test: isolate optimizer feasibility from import checks.
        # The unchanged positive control is fully replayed by the helper above.
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            helper = optimizer_fixtures.OptimizerCounterproofRegressions()
            raw, report_raw = helper._fixture(base)
            from model_release_assurance.models import AssessmentReport
            request = OptimizationRequest.model_validate(raw)
            report = AssessmentReport.model_validate(report_raw)
            configuration = request.configurations[0]
            experiments = {e.experiment_id: e for e in request.experiments}
            bounds = ReleaseOptimizer._verify_portfolio(configuration, report, experiments,
                request.portfolio_registry, base)
            for verdict in (Verdict.INCONCLUSIVE, Verdict.BLOCK):
                with self.subTest(verdict=verdict):
                    decision = report.decisions[0].model_copy(update={"mandatory": False, "verdict": verdict})
                    altered = report.model_copy(update={"decisions": (decision, *report.decisions[1:])})
                    result = ReleaseOptimizer._evaluate_configuration(configuration, altered,
                        experiments, {}, {}, request.portfolio_registry,
                        datetime.now(timezone.utc), bounds, {})
                    self.assertFalse(result.feasible)
                    self.assertTrue(any("is not clear" in reason for reason in result.reasons))

    def test_optional_threat_cannot_be_omitted_from_joint_portfolio(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            helper = optimizer_fixtures.OptimizerCounterproofRegressions()
            raw, report_raw = helper._fixture(base)
            from model_release_assurance.models import AssessmentReport
            report = AssessmentReport.model_validate(report_raw)
            optional = report.decisions[0].model_copy(update={"mandatory": False})
            report = report.model_copy(update={"decisions": (optional, *report.decisions[1:])})
            request = OptimizationRequest.model_validate(raw)
            configuration = request.configurations[0]
            pair = f"{optional.population_scope_id}|{optional.threat_id}"
            portfolio = configuration.portfolio.model_dump(mode="json")
            portfolio["population_secret_pairs"].remove(pair)
            portfolio["joint_upper_bounds"].pop(pair)
            portfolio["joint_experiment_ids"].pop(pair, None)
            configuration = configuration.model_copy(update={
                "portfolio": type(configuration.portfolio).model_validate(portfolio)})
            with self.assertRaisesRegex(ValueError, "omits a population-secret pair"):
                ReleaseOptimizer._verify_portfolio(configuration, report,
                    {e.experiment_id: e for e in request.experiments}, request.portfolio_registry, base)


if __name__ == "__main__":
    unittest.main()
