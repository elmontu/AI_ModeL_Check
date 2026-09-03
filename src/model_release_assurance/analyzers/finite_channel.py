from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

from ..decision_theory import exact_guess_problem
from ..errors import AnalyzerError
from ..incomplete_portfolio import (
    StatisticalCoverage,
    decimal_fraction,
    finite_prior_contract_sha256,
    outward_rounded_fraction,
    portfolio_prior_fractions,
    verified_upper_fraction,
    verify_analytic_portfolio,
)
from ..integrity import canonical_json_bytes, sha256_bytes
from ..models import (
    AnalyzerInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    FiniteChannelCeilingInput,
    RationalProbability,
    Realizability,
    ReleaseContract,
    ThreatContract,
)
from .base import (
    evidence_context_fields,
    evidence_producer_fields,
    statistical_family_sha256,
)


SUPPORTED_METRICS = frozenset({
    "bayes_linkage_success",
    "incremental_bayes_linkage_success",
    "equal_prior_membership_success",
    "finite_secret_exact_guess_success",
})


def _effective_lower_rows(value: FiniteChannelCeilingInput) -> tuple[tuple[Fraction, ...], ...]:
    release = value.analytic_evidence.problem.releases[0]
    rows: list[tuple[Fraction, ...]] = []
    for lower, upper in zip(release.lower, release.upper, strict=True):
        converted = tuple(decimal_fraction(item) for item in lower)
        # The portfolio contract interprets equal lower/upper rows as exact
        # decimal weights and normalizes them.  Mirror that interpretation in
        # the confidence-floor calculation.
        if lower == upper:
            total = sum(converted, Fraction(0))
            if total <= 0:
                raise AnalyzerError("deterministic finite-channel row has no mass")
            converted = tuple(item / total for item in converted)
        rows.append(converted)
    return tuple(rows)


def _exact_guess_floor(value: FiniteChannelCeilingInput) -> Fraction:
    """A simultaneous lower confidence bound using a fixed decoder.

    On the event that every serialized marginal lower endpoint is valid, the
    decoder choosing ``argmax_s pi_s L[s,o]`` achieves at least the returned
    value.  The decoder may be selected from the interval family because that
    family covers every cell simultaneously.
    """

    prior = portfolio_prior_fractions(value.analytic_evidence.problem)
    rows = _effective_lower_rows(value)
    observation_count = len(rows[0])
    floor = sum(
        max(prior[state] * rows[state][observation] for state in range(len(rows)))
        for observation in range(observation_count)
    )
    return min(Fraction(1), max(Fraction(0), floor))


def _downward_float(value: Fraction) -> float:
    """Return a binary64 whose canonical JSON decimal is at most ``value``."""

    candidate = float(value)
    while Fraction(Decimal(str(candidate))) > value:
        candidate = math.nextafter(candidate, -math.inf)
    return min(1.0, max(0.0, candidate))


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _planning_disposition(
    *,
    eligible: bool,
    lower: Fraction,
    upper: Fraction,
    tolerance: Fraction,
    state_trials: tuple[int, ...] | None,
    invalid_reasons: tuple[str, ...],
    ineligible_resolution: str,
) -> dict[str, object]:
    """Return an operational next step; never treat the estimate as evidence."""

    if not eligible:
        return {
            "resolution": ineligible_resolution,
            "release_gate": "hold",
            "missing_obligations": list(invalid_reasons),
            "planning_estimate_is_decision_evidence": False,
        }
    if upper <= tolerance:
        return {
            "resolution": "ceiling_below_tolerance",
            "release_gate": "clear_if_all_other_protocol_gates_pass",
            "planning_estimate_is_decision_evidence": False,
        }
    if lower > tolerance:
        return {
            "resolution": "floor_above_tolerance",
            "release_gate": "block",
            "planning_estimate_is_decision_evidence": False,
        }

    result: dict[str, object] = {
        "resolution": "recollect_more_state_conditioned_samples",
        "release_gate": "hold",
        "resolution_options": [
            "continue the preregistered state-conditioned sampling plan",
            "restrict the released observation alphabet or query protocol",
            "submit a sharper exact certificate without changing the evidence family",
        ],
        "planning_estimate_is_decision_evidence": False,
    }
    if state_trials:
        midpoint = (lower + upper) / 2
        distance = abs(tolerance - midpoint)
        half_width = (upper - lower) / 2
        minimum_current = min(state_trials)
        if distance > 0 and half_width > 0:
            # Confidence widths usually contract at n^-1/2.  This is an
            # intentionally labelled planning estimate; only a newly replayed
            # confidence family can change the gate.
            target_half_width = distance * Fraction(4, 5)
            multiplier = max(1.0, float(half_width / target_half_width) ** 2)
            multiplier = min(multiplier, 1_000_000.0)
            recommended = math.ceil(minimum_current * multiplier)
            result.update({
                "indicative_sample_multiplier": multiplier,
                "indicative_minimum_trials_per_state": recommended,
                "indicative_additional_trials_per_state": max(
                    0,
                    recommended - minimum_current,
                ),
            })
        else:
            result["sample_plan_note"] = (
                "the interval midpoint is at the tolerance; a finite sample target "
                "cannot be inferred until a directional margin is specified"
            )
    return result


class FiniteChannelCeilingAnalyzer:
    """Replay a finite-channel confidence interval for any governed model family."""

    name = "finite_channel_ceiling"
    can_clear = True
    can_block = True

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, FiniteChannelCeilingInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, FiniteChannelCeilingInput):
            raise AnalyzerError("finite-channel analyzer received an incompatible input")
        if threat.decision_metric not in SUPPORTED_METRICS:
            raise AnalyzerError(
                "finite-channel assessment implements canonical exact-guess metrics only; "
                f"unsupported metric {threat.decision_metric!r}"
            )

        entry = value.analytic_evidence
        problem = entry.problem
        expected_problem = exact_guess_problem(
            problem.state_ids,
            problem_id=problem.decision_problem.problem_id,
        )
        if (
            problem.decision_problem.state_ids != expected_problem.state_ids
            or problem.decision_problem.action_ids != expected_problem.action_ids
            or problem.decision_problem.gain != expected_problem.gain
        ):
            raise AnalyzerError(
                "finite-channel assessment requires the canonical exact-guess decision problem"
            )

        prior = portfolio_prior_fractions(problem)
        if threat.decision_metric == "equal_prior_membership_success" and (
            len(prior) != 2 or prior != (Fraction(1, 2), Fraction(1, 2))
        ):
            raise AnalyzerError(
                "equal-prior membership requires exactly two states with prior (1/2, 1/2)"
            )
        if threat.decision_metric == "finite_secret_exact_guess_success":
            prior_cap = threat.metric_parameters.get("maximum_secret_prior")
            if prior_cap is None or max(prior) > decimal_fraction(prior_cap):
                raise AnalyzerError(
                    "finite-secret prior exceeds the threat contract maximum_secret_prior"
                )

        verification = verify_analytic_portfolio(entry)
        invalid: list[str] = list(verification.reasons)
        actual_interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))
        mechanism_claims = {
            claim
            for evidence in problem.mechanism_evidence
            for claim in evidence.supports
        }
        required_release_claims = {
            f"artifact:{release.artifact_sha256}",
            f"interface:{actual_interface_sha256}",
            f"complete-transcript:{release.release_id}",
        }
        bound_prior = (
            problem.rational_prior
            if problem.rational_prior is not None
            else problem.prior
        )
        required_prior_claims = {
            "prior",
            f"decision-game:{problem.decision_game_sha256}",
            "finite-prior:"
            f"{finite_prior_contract_sha256(problem.state_ids, bound_prior)}",
        }
        game_checks = (
            (
                threat.finite_game is not None,
                "policy does not freeze a structured finite decision game",
            ),
            (
                problem.rational_prior is not None,
                "certificate omits the authoritative exact rational prior",
            ),
            (
                threat.finite_game is not None
                and threat.finite_game.state_ids == problem.state_ids,
                "certificate state order does not match the policy-frozen finite game",
            ),
            (
                threat.finite_game is not None
                and tuple(
                    probability.as_fraction()
                    for probability in threat.finite_game.prior
                ) == prior,
                "certificate numerical prior does not match the policy-frozen finite game",
            ),
        )
        certificate_checks = (
            (
                verification.valid
                and verification.rationally_replayed
                and verification.outward_rounded,
                "analytic certificate did not pass exact-rational outward replay",
            ),
            (problem.selection_valid, "confidence family is not selection-valid"),
            (
                problem.coverage is StatisticalCoverage.SIMULTANEOUS,
                "the reference finite-channel path requires simultaneous statistical coverage",
            ),
            (
                "confidence-endpoints:outward-validated"
                in problem.releases[0].evidence.supports,
                "generated marginal evidence omits replay-validated outward endpoints",
            ),
        )
        binding_checks = (
            (
                problem.releases[0].release_id == release.release_id,
                "certificate is bound to another release",
            ),
            (
                value.observed_interface_sha256 == actual_interface_sha256,
                "observed channel is bound to another release interface",
            ),
            (
                value.observed_artifact_sha256 == release.artifact_sha256,
                "observed channel is bound to another artifact",
            ),
            (
                required_prior_claims.issubset(set(problem.prior_evidence.supports)),
                "prior evidence does not bind the numerical prior, state order, and decision game",
            ),
        )
        interface_checks = (
            (
                required_release_claims.issubset(mechanism_claims),
                "mechanism evidence does not bind the artifact, interface, and complete transcript",
            ),
            (
                value.release_enforced_finite_alphabet,
                "finite categories were not enforced by the released interface",
            ),
            (
                value.complete_interface_coverage,
                "the channel omits recipient-visible outputs, errors, timing, state, or access paths",
            ),
            (
                value.recipient_realizable,
                "the assessed observation channel is not recipient-realizable",
            ),
            (
                value.bounded_transcript_complete,
                "adaptive queries or transcript outcomes are not completely bounded and enumerated",
            ),
            (
                release.interface.protocol_type != "interactive_llm"
                or release.interface.query_budget is not None,
                "interactive protocol has no enforced lifetime query bound",
            ),
        )
        invalid.extend(
            message
            for condition, message in (
                *game_checks,
                *certificate_checks,
                *binding_checks,
                *interface_checks,
            )
            if not condition
        )
        invalid_reasons = tuple(dict.fromkeys(invalid))
        eligible = not invalid_reasons
        if any(not condition for condition, _ in game_checks):
            ineligible_resolution = "register_policy_bound_finite_game"
        elif any(not condition for condition, _ in interface_checks):
            ineligible_resolution = "redesign_interface"
        elif problem.coverage is StatisticalCoverage.DETERMINISTIC:
            ineligible_resolution = "collect_simultaneous_channel_evidence"
        elif any(not condition for condition, _ in certificate_checks):
            ineligible_resolution = "repair_sampling_evidence_and_replay"
        else:
            ineligible_resolution = "repair_release_bindings_and_replay"

        # The verifier's exact rational upper bound is authoritative.  The
        # floor is calculated only after the canonical exact-guess game and
        # simultaneous-cell semantics have been checked.
        try:
            absolute_upper = verified_upper_fraction(verification)
        except ValueError:
            absolute_upper = Fraction(1)
        absolute_lower = _exact_guess_floor(value)
        baseline = max(prior)
        if threat.decision_metric.startswith("incremental_"):
            lower = max(Fraction(0), absolute_lower - baseline)
            upper = max(Fraction(0), absolute_upper - baseline)
        else:
            lower = absolute_lower
            upper = absolute_upper
        upper = min(Fraction(1), upper)
        lower = min(upper, min(Fraction(1), lower))

        tolerance = decimal_fraction(threat.tolerance)
        disposition = _planning_disposition(
            eligible=eligible,
            lower=lower,
            upper=upper,
            tolerance=tolerance,
            state_trials=value.state_trials,
            invalid_reasons=invalid_reasons,
            ineligible_resolution=ineligible_resolution,
        )
        certificate = entry.exact_certificate or entry.envelope_certificate
        assert certificate is not None
        details = {
            "model_family_neutral": True,
            "interface_observation_definition": value.interface_observation_definition,
            "state_ids": list(problem.state_ids),
            "observation_ids": list(problem.releases[0].observation_ids),
            "state_trials": list(value.state_trials) if value.state_trials else None,
            "coverage": problem.coverage.value,
            "coverage_confidence": problem.coverage_confidence,
            "selection_scope": problem.selection_scope,
            "selection_valid": problem.selection_valid,
            "certificate_id": certificate.certificate_id,
            "certificate_kind": (
                "exact_dual" if entry.exact_certificate is not None else "envelope"
            ),
            "certificate_sha256": sha256_bytes(canonical_json_bytes(entry)),
            "absolute_floor_fraction": _fraction_payload(absolute_lower),
            "absolute_ceiling_fraction": _fraction_payload(absolute_upper),
            "reported_floor_fraction": _fraction_payload(lower),
            "reported_ceiling_fraction": _fraction_payload(upper),
            "baseline_fraction": _fraction_payload(baseline),
            "interval_width": float(upper - lower),
            "tolerance": threat.tolerance,
            "source_sha256": value.provenance.source_sha256,
            **disposition,
        }
        limitations = (
            *invalid_reasons,
            "the confidence statement is conditional on the registered sampling model",
            "the assessment covers one release contract; G9 must compose every active release",
            "live deployment conformance remains an activation-gateway obligation",
        )
        common = dict(
            **evidence_context_fields(value.evidence_context),
            **evidence_producer_fields(value.provenance),
            threat_id=threat.threat_id,
            analyzer=self.name,
            metric=threat.decision_metric,
            baseline=outward_rounded_fraction(baseline),
            realizability=(
                Realizability.RECIPIENT
                if value.recipient_realizable
                else Realizability.AUDITOR_ONLY
            ),
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                "canonical finite-state exact-guess decision game",
                "simultaneous state-by-observation confidence family",
                "released observation alphabet equals the assessed complete transcript",
            ),
            limitations=limitations,
            details=details,
        )

        lower_float = _downward_float(lower)
        upper_float = outward_rounded_fraction(upper)
        # The decision object currently serializes binary64 values.  Preserve
        # the exact-rational no-false-clear/no-false-block directions at an
        # exceptionally close decimal threshold; a false-negative hold is
        # preferable to a threshold reversal.
        if upper > tolerance and upper_float <= threat.tolerance:
            upper_float = math.nextafter(threat.tolerance, math.inf)
        if lower <= tolerance and lower_float > threat.tolerance:
            lower_float = math.nextafter(threat.tolerance, -math.inf)
        if not eligible:
            return (EvidenceRecord(
                evidence_id=f"{threat.threat_id}:finite-channel:screen",
                evidence_class=EvidenceClass.SCREEN,
                coverage=EvidenceCoverage.SCREEN_ONLY,
                value=(lower_float + upper_float) / 2,
                lower=lower_float,
                upper=upper_float,
                statistical_family_id=(
                    statistical_family_sha256(
                        analyzer=self.name,
                        family_definition_sha256=(
                            problem.releases[0].evidence.source_sha256
                        ),
                    )
                    if problem.coverage is StatisticalCoverage.SIMULTANEOUS
                    else None
                ),
                familywise_confidence=(
                    problem.coverage_confidence
                    if problem.coverage is StatisticalCoverage.SIMULTANEOUS
                    else None
                ),
                can_clear=False,
                can_block=False,
                **common,
            ),)

        return (
            EvidenceRecord(
                evidence_id=f"{threat.threat_id}:finite-channel:floor",
                evidence_class=EvidenceClass.FLOOR,
                coverage=EvidenceCoverage.COMPLETE_INTERFACE,
                value=lower_float,
                lower=lower_float,
                exact_lower=RationalProbability(**_fraction_payload(lower)),
                statistical_family_id=statistical_family_sha256(
                    analyzer=self.name,
                    family_definition_sha256=(
                        problem.releases[0].evidence.source_sha256
                    ),
                ),
                familywise_confidence=problem.coverage_confidence,
                can_clear=False,
                can_block=True,
                **common,
            ),
            EvidenceRecord(
                evidence_id=f"{threat.threat_id}:finite-channel:ceiling",
                evidence_class=EvidenceClass.CEILING,
                coverage=EvidenceCoverage.COMPLETE_INTERFACE,
                value=upper_float,
                upper=upper_float,
                exact_upper=RationalProbability(**_fraction_payload(upper)),
                can_clear=True,
                can_block=False,
                **common,
            ),
        )
