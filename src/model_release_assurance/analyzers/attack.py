from __future__ import annotations

import math
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
    """Exact one-sided lower confidence bound for a binomial probability."""
    if successes == 0:
        return 0.0
    alpha = 1.0 - confidence
    low, high = 0.0, 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        upper_tail = 1.0 - _binomial_cdf(successes - 1, trials, midpoint)
        if upper_tail < alpha:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def clopper_pearson_upper(successes: int, trials: int, confidence: float) -> float:
    """Exact one-sided upper confidence bound for a binomial probability."""
    if successes == trials:
        return 1.0
    alpha = 1.0 - confidence
    low, high = 0.0, 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        lower_tail = _binomial_cdf(successes, trials, midpoint)
        if lower_tail > alpha:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


class AttackAnalyzer:
    name = "attack"

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
        operating_point_attained = True
        per_comparison_confidence = 1.0 - (
            (1.0 - value.confidence) / value.comparison_family_size
        )
        fpr_upper = None
        if value.metric == "membership_tpr_at_fpr":
            assert value.false_positives is not None
            assert value.nonmember_trials is not None
            assert value.target_fpr is not None
            if abs(value.target_fpr - threat.metric_parameters["target_fpr"]) > 1e-15:
                raise ValueError("attack target_fpr does not match the threat contract")
            fpr_upper = clopper_pearson_upper(
                value.false_positives, value.nonmember_trials, per_comparison_confidence
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
            evidence_id=f"{threat.threat_id}:attack:{value.attack_name}",
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.FLOOR if valid else EvidenceClass.SCREEN,
            coverage=EvidenceCoverage.NAMED_PROJECTION,
            metric=value.metric,
            value=estimate,
            lower=lower,
            upper=None,
            baseline=None,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=valid,
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                f"exact one-sided Clopper-Pearson confidence={value.confidence}",
                f"comparison family size={value.comparison_family_size}",
            ),
            limitations=limitations,
            details={
                "attack_name": value.attack_name,
                "population_scope_id": value.population_scope_id,
                "successes": value.successes,
                "trials": value.trials,
                "confidence": value.confidence,
                "per_comparison_confidence": per_comparison_confidence,
                "comparison_family_size": value.comparison_family_size,
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
