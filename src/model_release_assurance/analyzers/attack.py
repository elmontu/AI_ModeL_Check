from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from statistics import NormalDist

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    AttackInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    ReleaseContract,
    ThreatContract,
)
from .base import (
    evidence_context_fields,
    evidence_producer_fields,
    statistical_family_sha256,
)


# The directed proof below may need a binary64 search after the fast floating
# approximation.  Bounding the shorter defining tail to 25,000 terms keeps the
# worst-case search below roughly two million directed summation terms.  This
# is intentionally stricter than the finite-channel compiler's per-endpoint
# cap: generic attack records do not carry its assurance-wide work ledger.
MAX_GENERIC_CP_TAIL_TERMS = 25_000
MAX_GENERIC_CP_TRIALS = 10_000_000


def downward_canonical_float(value: Fraction) -> float:
    """Return a float whose canonical JSON decimal does not exceed ``value``."""

    candidate = float(value)
    while Fraction(Decimal(str(candidate))) > value:
        candidate = math.nextafter(candidate, 0.0)
    return candidate


def bonferroni_per_bound_confidence(
    familywise_confidence: float,
    simultaneous_bound_count: int,
) -> float:
    """Allocate canonical-decimal family alpha conservatively over all bounds."""

    if (
        not math.isfinite(familywise_confidence)
        or not 0.0 < familywise_confidence < 1.0
    ):
        raise ValueError("familywise confidence must lie in (0, 1)")
    if simultaneous_bound_count < 1:
        raise ValueError("simultaneous_bound_count must be positive")
    family_alpha = Fraction(1) - Fraction(Decimal(str(familywise_confidence)))
    allocated_alpha = family_alpha / simultaneous_bound_count
    target_confidence = Fraction(1) - allocated_alpha
    candidate = float(target_confidence)
    while (
        Fraction(1) - Fraction(Decimal(str(candidate))) > allocated_alpha
    ):
        candidate = math.nextafter(candidate, 1.0)
    if candidate >= 1.0:
        raise ValueError(
            "Bonferroni allocation is too small for a non-unit canonical confidence"
        )
    return candidate


def _validate_binomial_endpoint_request(
    successes: int,
    trials: int,
    confidence: float,
    *,
    side: str,
) -> tuple[float, int]:
    if trials < 1 or successes < 0 or successes > trials:
        raise ValueError("binomial counts must satisfy 0 <= successes <= trials")
    if trials > MAX_GENERIC_CP_TRIALS:
        raise ValueError(
            f"binomial trials exceed the hard limit {MAX_GENERIC_CP_TRIALS}"
        )
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie in (0, 1)")
    exact_alpha = Fraction(1) - Fraction(Decimal(str(confidence)))
    if exact_alpha <= 0:
        raise ValueError("confidence leaves no positive canonical alpha")
    alpha = downward_canonical_float(exact_alpha)
    if alpha <= 0.0:
        raise ValueError("confidence alpha is below the canonical float range")
    terms = min(
        trials - successes + 1 if side == "lower" else successes + 1,
        successes if side == "lower" else trials - successes,
    )
    if terms > MAX_GENERIC_CP_TAIL_TERMS:
        raise ValueError(
            "binomial endpoint proof exceeds the generic directed-tail work cap "
            f"of {MAX_GENERIC_CP_TAIL_TERMS} terms"
        )
    return alpha, terms


def _prove_outward_endpoint(
    successes: int,
    trials: int,
    endpoint: float,
    alpha: float,
    *,
    side: str,
) -> float:
    # Imported lazily to avoid a module-initialization cycle:
    # portfolio_statistics uses these lightweight attack helpers as its
    # no-SciPy quantile seed, while its directed Decimal verifier is the shared
    # security-critical implementation.
    from ..portfolio_statistics import _move_endpoint_outward_until_proven

    return _move_endpoint_outward_until_proven(
        successes,
        trials,
        endpoint,
        alpha,
        side=side,  # type: ignore[arg-type]
    )


def wilson_lower(successes: int, trials: int, confidence: float) -> float:
    alpha = 1.0 - confidence
    z = NormalDist().inv_cdf(1.0 - alpha)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    spread = z * ((p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) ** 0.5)
    return max(0.0, (centre - spread) / denominator)


def wilson_upper(successes: int, trials: int, confidence: float) -> float:
    alpha = 1.0 - confidence
    z = NormalDist().inv_cdf(1.0 - alpha)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    spread = z * ((p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) ** 0.5)
    return min(1.0, (centre + spread) / denominator)


def _binomial_cdf(successes: int, trials: int, probability: float) -> float:
    """Stable binomial CDF using log-PMF summation; no SciPy runtime dependency."""
    if successes < 0:
        return 0.0
    if successes >= trials:
        return 1.0
    if probability <= 0.0:
        return 1.0
    if probability >= 1.0:
        return 0.0
    logs = []
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    normalizer = math.lgamma(trials + 1)
    for count in range(successes + 1):
        logs.append(
            normalizer
            - math.lgamma(count + 1)
            - math.lgamma(trials - count + 1)
            + count * log_p
            + (trials - count) * log_q
        )
    maximum = max(logs)
    return min(1.0, math.exp(maximum) * math.fsum(math.exp(item - maximum) for item in logs))


def clopper_pearson_lower(successes: int, trials: int, confidence: float) -> float:
    """Outward-proved one-sided lower confidence bound for a binomial rate."""
    alpha, _ = _validate_binomial_endpoint_request(
        successes, trials, confidence, side="lower"
    )
    if successes == 0:
        return 0.0
    low, high = 0.0, 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        if successes <= trials - successes + 1:
            upper_tail = 1.0 - _binomial_cdf(
                successes - 1, trials, midpoint
            )
        else:
            # P_p(X >= k) = P_(1-p)(Y <= n-k); use the shorter edge.
            upper_tail = _binomial_cdf(
                trials - successes, trials, 1.0 - midpoint
            )
        if upper_tail < alpha:
            low = midpoint
        else:
            high = midpoint
    return _prove_outward_endpoint(
        successes,
        trials,
        (low + high) / 2.0,
        alpha,
        side="lower",
    )


def clopper_pearson_upper(successes: int, trials: int, confidence: float) -> float:
    """Outward-proved one-sided upper confidence bound for a binomial rate."""
    alpha, _ = _validate_binomial_endpoint_request(
        successes, trials, confidence, side="upper"
    )
    if successes == trials:
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        if successes + 1 <= trials - successes:
            lower_tail = _binomial_cdf(successes, trials, midpoint)
        else:
            # P_p(X <= k) = P_(1-p)(Y >= n-k); use the shorter edge.
            lower_tail = 1.0 - _binomial_cdf(
                trials - successes - 1, trials, 1.0 - midpoint
            )
        if lower_tail > alpha:
            low = midpoint
        else:
            high = midpoint
    return _prove_outward_endpoint(
        successes,
        trials,
        (low + high) / 2.0,
        alpha,
        side="upper",
    )


class AttackAnalyzer:
    name = "attack"
    can_clear = False
    can_block = True

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, AttackInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, AttackInput):
            raise AnalyzerError("attack analyzer received an incompatible input")
        if release.interface.protocol_type == "interactive_llm":
            raise AnalyzerError(
                "generic attack evidence cannot validate an interactive LLM; "
                "a dedicated transcript-bound LLM analyzer is required"
            )
        operating_point_attained = True
        bounds_per_comparison = 2 if value.metric == "membership_tpr_at_fpr" else 1
        simultaneous_bound_count = value.comparison_family_size * bounds_per_comparison
        per_comparison_confidence = bonferroni_per_bound_confidence(
            value.confidence,
            simultaneous_bound_count,
        )
        fpr_upper = None
        if value.metric == "membership_tpr_at_fpr":
            assert value.false_positives is not None
            assert value.nonmember_trials is not None
            assert value.target_fpr is not None
            if abs(value.target_fpr - threat.metric_parameters["target_fpr"]) > 1e-15:
                raise ValueError("attack target_fpr does not match the threat contract")
            observed_fpr = value.false_positives / value.nonmember_trials
            # If the point estimate already exceeds the frozen operating
            # point, no endpoint can make the run eligible.  Return the
            # conservative unit upper bound without spending directed-tail
            # work on an intentionally rejected screen.
            fpr_upper = (
                1.0
                if observed_fpr > value.target_fpr
                else clopper_pearson_upper(
                    value.false_positives,
                    value.nonmember_trials,
                    per_comparison_confidence,
                )
            )
            operating_point_attained = fpr_upper <= value.target_fpr
        valid = (
            value.calibration_disjoint
            and value.audit_disjoint
            and value.raw_counts_retained
            and value.threshold_pre_registered
            and operating_point_attained
        )
        estimate = value.successes / value.trials
        lower = (
            clopper_pearson_lower(value.successes, value.trials, per_comparison_confidence)
            if valid
            else None
        )
        limitations = () if valid else (
            "attack floor invalid because calibration/audit separation, conservative operating-point attainment, threshold pre-registration, or raw counts are missing",
        )
        return (EvidenceRecord(
            **evidence_context_fields(value.evidence_context),
            **evidence_producer_fields(value.provenance),
            evidence_id=f"{threat.threat_id}:attack:{value.attack_name}",
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.FLOOR if valid else EvidenceClass.SCREEN,
            coverage=EvidenceCoverage.NAMED_PROJECTION,
            metric=value.metric,
            value=estimate,
            lower=lower,
            upper=None,
            statistical_family_id=statistical_family_sha256(
                analyzer=self.name,
                family_definition_sha256=(
                    value.provenance.producer.configuration_sha256
                ),
            ),
            familywise_confidence=value.confidence,
            baseline=None,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=valid,
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                f"exact one-sided Clopper-Pearson confidence={value.confidence}",
                f"comparison family size={value.comparison_family_size}",
                f"simultaneous bound count={simultaneous_bound_count}",
            ),
            limitations=limitations,
            details={
                "attack_name": value.attack_name,
                "preregistration_sha256": value.preregistration_sha256,
                "population_scope_id": value.population_scope_id,
                "successes": value.successes,
                "trials": value.trials,
                "confidence": value.confidence,
                "per_comparison_confidence": per_comparison_confidence,
                "comparison_family_size": value.comparison_family_size,
                "bounds_per_comparison": bounds_per_comparison,
                "simultaneous_bound_count": simultaneous_bound_count,
                "false_positives": value.false_positives,
                "nonmember_trials": value.nonmember_trials,
                "target_fpr": value.target_fpr,
                "one_sided_fpr_upper": fpr_upper,
                "operating_point_attained": operating_point_attained,
                "source_sha256": value.provenance.source_sha256,
                "tool": value.provenance.tool,
                "tool_version": value.provenance.tool_version,
            },
        ),)
