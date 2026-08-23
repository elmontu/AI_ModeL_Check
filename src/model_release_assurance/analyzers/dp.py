from __future__ import annotations

import math

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    DpInput,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    ReleaseContract,
    ThreatContract,
    ThreatKind,
)
from .base import evidence_context_fields


def membership_roc_ceiling(
    epsilon: float,
    delta: float,
    false_positive_rate: float,
) -> tuple[float, float, float]:
    """Return the symmetric (epsilon, delta)-DP TPR ceiling and its two limbs.

    The calculation is algebraically identical to
    ``min(exp(epsilon) * FPR + delta,
    1 - exp(-epsilon) * (1 - FPR - delta))`` but clips each limb before
    returning it and avoids overflow for large finite epsilon.
    """
    if false_positive_rate == 0.0:
        first = delta
    else:
        log_scaled_fpr = epsilon + math.log(false_positive_rate)
        first = 1.0 if log_scaled_fpr >= 0.0 else math.exp(log_scaled_fpr) + delta
    first = min(1.0, max(0.0, first))
    second = 1.0 - math.exp(-epsilon) * (1.0 - false_positive_rate - delta)
    second = min(1.0, max(0.0, second))
    return min(first, second), first, second


def equal_prior_membership_ceiling(epsilon: float, delta: float) -> float:
    """Bayes success ceiling for symmetric membership hypotheses with prior 1/2."""
    inverse_likelihood_ratio = math.exp(-epsilon)
    return (
        1.0 + delta * inverse_likelihood_ratio
    ) / (1.0 + inverse_likelihood_ratio)


def finite_secret_exact_guess_ceiling(
    epsilon: float,
    delta: float,
    maximum_secret_prior: float,
) -> float:
    """Bayes exact-guess ceiling under pairwise DP and a prior-mass cap.

    If every ordered pair of secret-conditioned output laws satisfies
    (epsilon, delta)-DP and ``max_s pi(s) <= p``, the success of every decoder
    is at most

        (exp(epsilon) p + delta (1-p)) / (1-p + exp(epsilon) p).

    The inverse-exponential form below is numerically stable for arbitrarily
    large finite epsilon.  Contract validation supplies ``0 < p < 1``.
    """
    inverse_likelihood_ratio = math.exp(-epsilon)
    complement = 1.0 - maximum_secret_prior
    return (
        maximum_secret_prior
        + delta * complement * inverse_likelihood_ratio
    ) / (
        maximum_secret_prior
        + complement * inverse_likelihood_ratio
    )


class DpAnalyzer:
    name = "dp"

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, DpInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, DpInput):
            raise AnalyzerError("DP analyzer received an incompatible input")
        validated = (
            value.accountant_replayed
            and value.complete_pipeline
            and value.protected_unit == release.protected_unit
        )
        limitations = [] if validated else [
            "accountant was not independently replayed, pipeline scope is incomplete, or protected unit mismatches"
        ]
        records: list[EvidenceRecord] = []
        common = dict(
            **evidence_context_fields(value.evidence_context),
            threat_id=threat.threat_id,
            analyzer=self.name,
            evidence_class=EvidenceClass.CEILING if validated else EvidenceClass.SCREEN,
            coverage=(
                EvidenceCoverage.COMPLETE_INTERFACE
                if validated
                else EvidenceCoverage.SCREEN_ONLY
            ),
            realizability=Realizability.NOT_APPLICABLE,
            can_clear=validated,
            can_block=False,
            assumptions=(
                f"population_scope_id={value.population_scope_id}",
                f"adjacency={value.adjacency}",
                f"protected_unit={value.protected_unit}",
                f"accountant={value.accountant}",
                f"epsilon={value.epsilon}",
                f"delta={value.delta}",
            ),
            limitations=tuple(limitations),
        )
        if threat.kind is ThreatKind.MEMBERSHIP:
            if value.fpr is not None:
                if threat.decision_metric == "membership_tpr_at_fpr" and abs(
                    value.fpr - threat.metric_parameters["target_fpr"]
                ) > 1e-15:
                    raise ValueError("DP evidence FPR does not match the threat contract target_fpr")
                ceiling, first, second = membership_roc_ceiling(
                    value.epsilon,
                    value.delta,
                    value.fpr,
                )
                records.append(EvidenceRecord(
                    evidence_id=f"{threat.threat_id}:dp:roc",
                    metric="membership_tpr_at_fpr",
                    upper=ceiling if validated else None,
                    value=ceiling,
                    details={"population_scope_id": value.population_scope_id, "fpr": value.fpr, "bound_1": first, "bound_2": second, "source_sha256": value.provenance.source_sha256},
                    **common,
                ))
            equal_prior = equal_prior_membership_ceiling(value.epsilon, value.delta)
            records.append(EvidenceRecord(
                evidence_id=f"{threat.threat_id}:dp:equal-prior",
                metric="equal_prior_membership_success",
                upper=equal_prior if validated else None,
                value=equal_prior,
                details={"population_scope_id": value.population_scope_id, "source_sha256": value.provenance.source_sha256},
                **common,
            ))
        elif value.secret_cardinality is not None:
            finite_limitations = list(limitations)
            if not value.pairwise_secret_relation_validated:
                finite_limitations.append("pairwise DP relation across all finite-secret alternatives was not validated")
            if not value.secret_prior_bound_validated:
                finite_limitations.append("the numerical upper bound on maximum secret-prior mass was not validated")
            policy_prior_cap = threat.metric_parameters.get("maximum_secret_prior")
            prior_matches_game = (
                threat.decision_metric == "finite_secret_exact_guess_success"
                and policy_prior_cap is not None
                and value.maximum_secret_prior is not None
                and value.maximum_secret_prior <= policy_prior_cap + 1e-15
            )
            if not prior_matches_game:
                finite_limitations.append(
                    "the validated maximum secret-prior mass does not satisfy the policy-bound decision game"
                )
            finite_validated = (
                validated
                and value.pairwise_secret_relation_validated
                and value.secret_prior_bound_validated
                and prior_matches_game
            )
            assert value.maximum_secret_prior is not None
            ceiling = finite_secret_exact_guess_ceiling(
                value.epsilon,
                value.delta,
                value.maximum_secret_prior,
            )
            records.append(EvidenceRecord(
                evidence_id=f"{threat.threat_id}:dp:finite-secret",
                metric="finite_secret_exact_guess_success",
                upper=ceiling if finite_validated else None,
                value=ceiling,
                details={
                    "population_scope_id": value.population_scope_id,
                    "secret_cardinality": value.secret_cardinality,
                    "maximum_secret_prior": value.maximum_secret_prior,
                    "policy_maximum_secret_prior": policy_prior_cap,
                    "bound": (
                        "(exp(epsilon)*p + delta*(1-p)) / "
                        "(1-p + exp(epsilon)*p)"
                    ),
                    "source_sha256": value.provenance.source_sha256,
                },
                **{
                    **common,
                    "evidence_class": EvidenceClass.CEILING if finite_validated else EvidenceClass.SCREEN,
                    "can_clear": finite_validated,
                    "assumptions": (
                        *common["assumptions"],
                        f"secret_cardinality={value.secret_cardinality}",
                        f"maximum_secret_prior={value.maximum_secret_prior}",
                        "pairwise DP holds for every ordered pair of secret-conditioned laws",
                    ),
                    "limitations": tuple(finite_limitations),
                },
            ))
        else:
            records.append(EvidenceRecord(
                evidence_id=f"{threat.threat_id}:dp:scope",
                metric="dp_scope_validated",
                value=1.0 if validated else 0.0,
                details={"population_scope_id": value.population_scope_id, "source_sha256": value.provenance.source_sha256},
                **{**common, "can_clear": False},
            ))
        return tuple(records)
