#!/usr/bin/env python3
"""Exact arithmetic checks for the guide's synthetic constructive example.

This is a mathematical teaching example, not empirical model validation or an
authorisation tool. It reads no personal data, draws no random numbers, and has
no third-party dependencies. Run: python verify_constructive_example.py
Optional: python verify_constructive_example.py --json result.json
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path


R = F(101, 100)
CUTOFF = 5000
UNIVERSE = 10001
Q = F(1, 1000)
MEMBERSHIP_LIMIT = F(1, 100)
IDENTITY_LIMIT = F(1, 20)
ATTRIBUTE_LIMIT = F(1, 50)
UTILITY_FLOOR = F(3, 4)


def probability_high(count: int) -> F:
    """Exact law of the single released model bit B."""
    assert 0 <= count <= UNIVERSE
    odds = R ** (count - CUTOFF)
    return odds / (1 + odds)


def decimal(value: F, places: int = 12) -> str:
    """Display only; every substantive comparison below uses Fraction."""
    with localcontext() as ctx:
        ctx.prec = 50
        return format(Decimal(value.numerator) / Decimal(value.denominator), f".{places}f")


def main() -> dict:
    # For any odds w>0, with common positive denominator (1+w)(1+R*w):
    # p(s+1)-p(s) has numerator (R-1)*w;
    # R*p(s)-p(s+1) has numerator R*(R-1)*w**2;
    # R*(1-p(s+1))-(1-p(s)) has numerator R-1.
    # These nonnegative coefficients prove both output likelihood-ratio
    # inequalities for EVERY count, without an approximate numerical sweep.
    coefficients = (R - 1, R * (R - 1), R - 1)
    assert all(coefficient >= 0 for coefficient in coefficients)
    for w in (F(1, 100), F(1, 2), F(1), F(2), F(100)):
        p, nxt = w / (1 + w), R * w / (1 + R * w)
        denominator = (1 + w) * (1 + R * w)
        assert (nxt - p) * denominator == (R - 1) * w
        assert (R * p - nxt) * denominator == R * (R - 1) * w * w
        assert (R * (1 - nxt) - (1 - p)) * denominator == R - 1
        assert p <= nxt <= R * p
        assert 1 - nxt <= 1 - p <= R * (1 - nxt)

    membership_upper = R * Q
    assert membership_upper == F(101, 100000) < MEMBERSHIP_LIMIT

    # Attribute: prior a, likelihood ratio l in [1/R,R]. For l>=1,
    # posterior-prior = a(1-a)(l-1)/(1+a(l-1)) <= (R-1)/4.
    # The l<1 case follows by relabelling the binary attribute.
    # Since max(a,1-a) is 1-Lipschitz, this also bounds the increase in
    # optimal binary prediction success, averaged over the output.
    attribute_upper = (R - 1) / 4
    assert attribute_upper == F(1, 400) < ATTRIBUTE_LIMIT

    # Check exact posterior updates at representative priors and both signs.
    # The all-prior proof is the algebraic bound just stated, not these checks.
    for prior in (F(0), F(1, 1000), F(1, 10), F(1, 2), F(9, 10), F(1)):
        for lr in (1 / R, F(1), R):
            posterior = prior * lr / (1 - prior + prior * lr)
            assert abs(posterior - prior) <= attribute_upper

    # Identity is a SEPARATE explicit permutation experiment. I is uniform
    # over 100 candidates; for every I the complete dataset is relabelled,
    # leaving the count, and therefore both output probabilities, unchanged.
    # Bayes cancellation leaves the uniform posterior exactly unchanged.
    identity_upper = F(1, 100)
    for count in (4000, 4001, 6000, 6001):
        high = probability_high(count)
        for likelihood in (high, 1 - high):
            posterior = identity_upper * likelihood / sum(
                (identity_upper * likelihood for _ in range(100)), F(0)
            )
            assert posterior == identity_upper
    assert identity_upper < IDENTITY_LIMIT

    # Useful synthetic population law: G is a fair high/low regime bit.
    # The 10,000 background people contribute 4,000 positives if G=0,
    # 6,000 if G=1. A target is present with fair bit M and has independent
    # fair binary value A, so count=C_G+M*A. The future demand label Z equals
    # G with probability 9/10, independently of the mechanism draw given G.
    # The model predicts the single cached bit B on every permitted request.
    cells = []
    exact_expected_accuracy = F(0)
    min_regime_probability = F(1)
    for regime in (0, 1):
        for present in (0, 1):
            for attribute in (0, 1):
                count = (4000 if regime == 0 else 6000) + present * attribute
                high = probability_high(count)
                regime_probability = high if regime else 1 - high
                accuracy = F(1, 10) + F(4, 5) * regime_probability
                min_regime_probability = min(min_regime_probability, regime_probability)
                exact_expected_accuracy += accuracy / 8
                # Joint observations are (B,B): the old and new recipients
                # receive identical cached bytes, never independent draws.
                transcript = {(0, 0): 1 - high, (1, 1): high}
                assert sum(transcript.values(), F(0)) == 1
                assert (0, 1) not in transcript and (1, 0) not in transcript
                cells.append({
                    "regime": regime, "target_present": present,
                    "target_value": attribute, "positive_count": count,
                    "expected_accuracy_display": decimal(accuracy),
                })
    conservative_regime_probability = R**999 / (1 + R**999)
    assert min_regime_probability == conservative_regime_probability
    conservative_accuracy = F(1, 10) + F(4, 5) * conservative_regime_probability
    assert conservative_regime_probability > F(9999, 10000)
    assert conservative_accuracy > F(8999, 10000) > UTILITY_FLOOR
    assert exact_expected_accuracy >= conservative_accuracy
    # G is fair and Z agrees with it 90%, hence Z is marginally fair:
    # without the release or regime information, either forecast scores 1/2.
    no_release_accuracy = (F(9, 10) + F(1, 10)) / 2
    assert no_release_accuracy == F(1, 2)

    return {
        "status": "PASS — stipulated synthetic example only",
        "basis": "exact rational inequalities and a fully specified finite law; no confidence intervals or empirical measurements",
        "privacy_ratio": "101/100",
        "privacy_epsilon_description": "ln(101/100), pure delta=0, one bounded person; both participation and value adjacency",
        "membership": {"fpr_limit": "1/1000", "tpr_upper": "101/100000", "tpr_limit": "1/100"},
        "attribute": {"binary_success_increment_upper": "1/400", "limit": "1/50", "scope": "same background law under both values, conditional on allowed auxiliary information"},
        "identity": {"success": "1/100", "limit": "1/20", "scope": "uniform 100-candidate permutation game; count invariant"},
        "utility": {
            "metric": "ex ante expected planning-label accuracy under the stipulated synthetic law",
            "floor": "3/4", "certified_accuracy_greater_than": "8999/10000",
            "worst_conditional_expected_accuracy_display": decimal(conservative_accuracy),
            "exact_mean_accuracy_display": decimal(exact_expected_accuracy),
            "regime_selection_probability_greater_than": "9999/10000",
            "no_release_accuracy": "1/2", "cells": cells,
        },
        "history": "one protected source draw; complete pooled transcript (B,B), equivalent to B; no independent rerun",
        "limits": [
            "No real project dataset, measured deployment performance or agency authorisation.",
            "Identity guarantee depends on the stated permutation prior and auxiliary information.",
            "Attribute guarantee does not bound population-correlation inference when the background law changes with the secret.",
            "Expected utility is not a measured confidence lower bound for an individual fitted model.",
            "Python checks do not verify production random sampling, source custody or gateway implementation.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also save the result as UTF-8 JSON")
    args = parser.parse_args()
    report = main()
    rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.json:
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
