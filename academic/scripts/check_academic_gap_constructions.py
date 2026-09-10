"""Exact, seed-free finite constructions for the academic protocol draft.

This is a standalone research control, not an implementation of the MRAP gate.
It uses no model, dataset, random sample, cryptographic implementation, or core
MRA import. Exhaustive finite checks corroborate the named constructions only;
the general mathematical arguments must be read and reviewed separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import permutations, product
import json
from math import comb
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "academic" / "paper" / "gap-construction-results.json"
ARTIFACT_ROLE = "finite_constructed_validation_not_MRAP_contract"
GENERATOR_PATH = "academic/scripts/check_academic_gap_constructions.py"
F = Fraction
ZERO, HALF, ONE = F(0), F(1, 2), F(1)
SAFE = ((ONE, ZERO), (ONE, ZERO))
REVEAL = ((ONE, ZERO), (ZERO, ONE))


def rational(value: Fraction) -> str:
    """Canonical exact rational, never a rounded measurement."""
    return str(value)


def validate_channel(channel: Sequence[Sequence[Fraction]]) -> None:
    if not channel or not channel[0]:
        raise ValueError("channel must have nonempty finite spaces")
    width = len(channel[0])
    for row in channel:
        if len(row) != width or any(not isinstance(x, Fraction) or x < 0 for x in row):
            raise ValueError("channel entries must be nonnegative exact Fractions")
        if sum(row) != ONE:
            raise ValueError("each channel row must sum exactly to one")


def decoder_values(channel: Sequence[Sequence[Fraction]]) -> list[Fraction]:
    """Enumerate all deterministic guessing decoders under the uniform prior."""
    validate_channel(channel)
    states, observations = len(channel), len(channel[0])
    prior = F(1, states)
    return [
        sum(prior * channel[secret][observation]
            for observation, secret in enumerate(decoder))
        for decoder in product(range(states), repeat=observations)
    ]


def guessing_value(channel: Sequence[Sequence[Fraction]]) -> Fraction:
    return max(decoder_values(channel))


def pointwise_bayes_value(channel: Sequence[Sequence[Fraction]]) -> Fraction:
    """Independent finite closed form: choose the best secret at each output."""
    validate_channel(channel)
    return sum(max(row[obs] for row in channel) / len(channel)
               for obs in range(len(channel[0])))


def row_tv(left: Sequence[Sequence[Fraction]], right: Sequence[Sequence[Fraction]]) -> Fraction:
    validate_channel(left)
    validate_channel(right)
    if len(left) != len(right) or len(left[0]) != len(right[0]):
        raise ValueError("TV comparison requires matching finite spaces")
    return max(sum(abs(a - b) for a, b in zip(lrow, rrow)) / 2
               for lrow, rrow in zip(left, right))


def max_posterior(channel: Sequence[Sequence[Fraction]]) -> Fraction:
    """Worst positive-probability observation, with a uniform secret prior."""
    validate_channel(channel)
    return max(
        max(row[obs] for row in channel) / denominator
        for obs in range(len(channel[0]))
        if (denominator := sum(row[obs] for row in channel)) > 0
    )


def require(condition: bool, claim: str) -> None:
    if not condition:
        raise AssertionError(claim)


def floor_construction() -> dict:
    cases = []
    for name, channel in (("constant_output", SAFE), ("secret_output", REVEAL)):
        values = decoder_values(channel)
        require(max(values) == pointwise_bayes_value(channel), "enumerated and pointwise Bayes optima agree")
        blind_value = sum(HALF * channel[0][y] for y in range(len(channel[0])))
        require(blind_value == HALF, "the same blind attack has identical success in both worlds")
        cases.append({"world": name, "blind_success": rational(blind_value),
                      "optimal_success": rational(max(values)),
                      "pointwise_bayes_success": rational(pointwise_bayes_value(channel)),
                      "enumerated_decoders": len(values),
                      "all_decoder_successes": [rational(x) for x in values]})
    require(guessing_value(SAFE) <= F(3, 5) < guessing_value(REVEAL), "opposite true decisions")
    return {
        "id": "G1_floor_nonidentifiability",
        "hypothesis": "Uniform secret bit; auditor receives only the exact blind-attack success, not the channel or raw output transcript.",
        "construction": cases,
        "finite_check_count": 8,
        "count_unit": "distinct deterministic channel/decoder cells across two finite channels",
        "counterexample": "The identical success summary 1/2 is compatible with optimal success 1/2 or 1; no rule using only that summary can distinguish the two.",
        "repair_control": "Enumerating the complete decoder family for the fully specified finite channel recovers 1/2 and 1 exactly.",
        "remaining_boundary": "No claim that a finite attack battery contains all real adversaries, or that a channel can be reconstructed from this summary.",
        "passed": True,
    }


def selection_construction() -> dict:
    n, alpha = 20, F(1, 20)
    cases = []
    for name, per_bound in (("pointwise", alpha), ("bonferroni", alpha / n)):
        histogram = []
        for failures in range(n + 1):
            weight = F(comb(n, failures)) * per_bound ** failures * (1 - per_bound) ** (n - failures)
            histogram.append({"failures": failures, "labeled_configurations": comb(n, failures),
                              "probability": rational(weight), "false_release": failures > 0})
        probability = sum(F(row["probability"]) for row in histogram if row["false_release"])
        require(sum(F(row["probability"]) for row in histogram) == ONE, "histogram normalizes")
        require(sum(row["labeled_configurations"] for row in histogram) == 2 ** n, "histogram covers all configurations")
        require(probability == 1 - (1 - per_bound) ** n, "exact selected failure probability")
        if name == "bonferroni":
            require(probability <= alpha, "Bonferroni repair controls this construction")
        else:
            require(probability > F(3, 5), "pointwise selection is materially anti-conservative")
        cases.append({"allocation": name, "per_bound_failure_probability": rational(per_bound),
                      "sum_allocations": rational(n * per_bound),
                      "selected_false_release_probability": rational(probability),
                      "histogram": histogram})
    return {
        "id": "G2_selection_error",
        "hypothesis": "Twenty independent constructed bounds for true risk 1; each bound is 0 on its failure event and 1 otherwise; select the smallest at tolerance 1/10.",
        "construction": cases,
        "finite_check_count": 42,
        "count_unit": "exact binomial histogram cells (21 per allocation), not sampled repetitions",
        "represented_labeled_configurations_per_allocation": 2 ** n,
        "counterexample": "Pointwise 95% coverage gives selected false-release probability 1-(19/20)^20, not 1/20.",
        "repair_control": "Allocate 1/400 to each of twenty bounds. The exact independent construction is below 1/20; the general union-bound repair does not require independence.",
        "remaining_boundary": "This does not construct valid data-derived confidence bounds. Conditional coverage and allocation across future selection/stopping remain separate premises.",
        "passed": True,
    }


def scope_construction() -> dict:
    universe = list(product((0, 1), repeat=3))
    atoms = {profile: [x for x in universe if x[:2] == profile]
             for profile in product((0, 1), repeat=2)}
    flattened = [x for atom in atoms.values() for x in atom]
    require(len(flattened) == len(set(flattened)) == len(universe), "atoms form an exact partition")
    require(atoms[(0, 0)] != [], "all-false residual atom is explicitly retained")
    masks = []
    for mask in range(2 ** len(universe)):
        declared = [x for index, x in enumerate(universe) if mask & (1 << index)]
        uncovered = sorted(set(universe) - set(declared))
        passed = not uncovered
        require(passed == (mask == 255), "strict coverage accepts only the complete supplied universe")
        masks.append({"declaration_mask": mask, "uncovered_count": len(uncovered),
                      "coverage_accepted": passed})
    auditor_views = [("safe", {"declared_output": 0}), ("hidden_secret_log", {"declared_output": 0})]
    require(auditor_views[0][1] == auditor_views[1][1], "the visible audit transcript is identical")
    return {
        "id": "G3_scope_and_observation",
        "hypothesis": "Eight supplied scenario identifiers with three binary features; taxonomy predicates read the first two. The separate hidden-world pair gives the auditor only constant declared output.",
        "atoms": [{"profile": list(profile), "scenario_ids": [list(x) for x in atom]}
                  for profile, atom in atoms.items()],
        "declaration_masks": masks,
        "hidden_worlds": [{"world": name, "auditor_view": view,
                           "adversary_success": rational(guessing_value(channel))}
                          for (name, view), channel in zip(auditor_views, (SAFE, REVEAL))],
        "finite_check_count": 256,
        "count_unit": "all subsets of the supplied eight-scenario universe",
        "counterexample": "An undeclared secret log changes adversary success from 1/2 to 1 without changing the supplied auditor transcript.",
        "repair_control": "The finite coverage checker retains all-false atoms and rejects each incomplete declaration; explicit justified exclusions must be separate from a claim of full in-scope coverage.",
        "remaining_boundary": "No function of identical auditor observations can universally detect an omitted channel; additional observation or an assumption excluding the hidden world is necessary.",
        "passed": True,
    }


def xor_construction() -> dict:
    joint = [[ZERO] * 4 for _ in range(2)]
    for secret, random_bit in product((0, 1), repeat=2):
        joint[secret][2 * random_bit + (secret ^ random_bit)] += HALF
    marginals = []
    for coordinate in (0, 1):
        channel = []
        for row in joint:
            channel.append([sum(row[2 * a + b] for a, b in product((0, 1), repeat=2)
                                if (a, b)[coordinate] == y) for y in (0, 1)])
        marginals.append(channel)
    independent_joint = [[F(1, 4)] * 4 for _ in range(2)]
    require(all(guessing_value(channel) == HALF for channel in marginals), "both XOR marginals conceal S")
    require(guessing_value(joint) == ONE, "the joint XOR channel reveals S")
    require(guessing_value(independent_joint) == HALF, "joint independent-noise control conceals S")
    channels = [("Y1", marginals[0]), ("Y2", marginals[1]),
                ("XOR_joint", joint), ("independent_noise_joint_control", independent_joint)]
    for _, channel in channels:
        require(guessing_value(channel) == pointwise_bayes_value(channel), "enumerated and pointwise Bayes optima agree")
    for coordinate, marginal in enumerate(marginals):
        control_marginal = [[sum(row[2 * a + b] for a, b in product((0, 1), repeat=2)
                                if (a, b)[coordinate] == y) for y in (0, 1)]
                            for row in independent_joint]
        require(marginal == control_marginal, "safe and unsafe joint channels have identical marginals")
    return {
        "id": "G4_joint_disclosure",
        "hypothesis": "Independent uniform bits S and R; Y1=R and Y2=S XOR R. The control uses two fresh independent noise bits.",
        "channels": [{"name": name, "rows": [[rational(x) for x in row] for row in channel],
                      "optimal_success": rational(guessing_value(channel)),
                      "pointwise_bayes_success": rational(pointwise_bayes_value(channel)),
                      "enumerated_decoders": len(decoder_values(channel))} for name, channel in channels],
        "finite_check_count": sum(len(decoder_values(channel)) for _, channel in channels),
        "count_unit": "distinct deterministic channel/decoder cells across four finite channels",
        "counterexample": "The XOR and independent-noise systems have identical marginal channels but different joint risks; marginal certificates alone cannot distinguish them.",
        "repair_control": "Complete joint-channel enumeration detects success 1 for XOR and 1/2 for independent noise.",
        "remaining_boundary": "Complete composition must include side information and prior releases; this finite example does not validate a live joint-channel model.",
        "passed": True,
    }


def transfer_construction() -> dict:
    erasure = []
    baseline = ((ONE, ZERO, ZERO), (ONE, ZERO, ZERO))
    for epsilon in (F(1, 1000), F(1, 100), F(1, 10), ONE):
        channel = ((1 - epsilon, epsilon, ZERO), (1 - epsilon, ZERO, epsilon))
        value, posterior = guessing_value(channel), max_posterior(channel)
        require(row_tv(baseline, channel) == epsilon, "erasure row TV")
        require(value == HALF + epsilon / 2, "exact erasure expected gain")
        require(posterior == ONE, "revealing observation has posterior one")
        erasure.append({"epsilon": rational(epsilon), "row_tv": rational(row_tv(baseline, channel)),
                        "expected_success": rational(value), "maximum_posterior": rational(posterior),
                        "revealing_event_probability": rational(epsilon),
                        "enumerated_decoders": len(decoder_values(channel))})
    sharpness = []
    fair = ((HALF, HALF), (HALF, HALF))
    for eta in (F(1, 100), F(1, 10), F(1, 4), HALF):
        channel = ((HALF + eta, HALF - eta), (HALF - eta, HALF + eta))
        increase = guessing_value(channel) - guessing_value(fair)
        require(row_tv(fair, channel) == increase == eta, "the additive TV constant one is attained")
        sharpness.append({"eta": rational(eta), "row_tv": rational(row_tv(fair, channel)),
                          "expected_success_increase": rational(increase),
                          "enumerated_decoders": len(decoder_values(channel))})
    return {
        "id": "G5_transfer_metric_boundary",
        "hypothesis": "Uniform binary-secret guessing with gain in [0,1]; TV compares rows on a common output space; maximum posterior ranges over positive-probability observations.",
        "erasure_cases": erasure,
        "expected_gain_sharpness_cases": sharpness,
        "finite_check_count": 8,
        "count_unit": "exact channel-pair parameter cases (four erasure and four sharpness cases)",
        "counterexample": "Arbitrarily small positive erasure probability can coexist with posterior one on a rare revealing event; expected gain and worst-observation posterior are different metrics.",
        "repair_control": "Use the additive TV penalty for bounded expected gain only. The randomized-response construction attains the coefficient one, so no smaller universal coefficient works under these premises.",
        "remaining_boundary": "The finite checks instantiate, but do not prove, the all-parameter result. Posterior guarantees need additional assumptions or a different certificate; they cannot be inferred from a small absolute TV error alone.",
        "passed": True,
    }


def reduce_verdict(threats: Sequence[tuple[Fraction, Fraction, Fraction]], *,
                   missing_mask: int = 0, mandatory_complete: bool = True,
                   acceptance: tuple[bool, int] | None = None,
                   actionable_mask: int = 0) -> str:
    """Standalone normative decision construction, not the production facade.

    A supplied acceptance is valid only if its validity premise is true and its
    mask covers every crossing. This abstracts, not implements, identity,
    signature, ceiling/context binding, expiry, and policy authorization checks.
    """
    if not threats or missing_mask or not mandatory_complete:
        return "BLOCK"
    if any(not all(isinstance(x, Fraction) for x in row)
           or not ZERO <= row[0] <= row[1] <= ONE or not ZERO <= row[2] <= ONE
           for row in threats):
        return "BLOCK"
    crossing = sum(1 << i for i, (lower, upper, threshold) in enumerate(threats)
                   if lower <= threshold < upper)
    if acceptance is not None and (not acceptance[0] or crossing & ~acceptance[1]):
        return "BLOCK"
    if any(lower > threshold for lower, _, threshold in threats):
        return "BLOCK"
    if not crossing:
        return "RELEASE"
    if acceptance is not None:
        return "RELEASE-WITH-RISK"
    if not crossing & ~actionable_mask:
        return "INCONCLUSIVE"
    return "BLOCK"


def selection_admissible(candidate_verdict: str, *, mandatory_clear: bool,
                         other_gates_pass: bool,
                         crossings_optional_only: bool = False,
                         policy_allows_risk: bool = False,
                         exact_valid_acceptance: bool = False) -> bool:
    """Pure strict-selection predicate, distinct from the outward disposition.

    All booleans are externally established premises, not implemented policy,
    identity, signature, scientific-evidence, or organizational trust checks.
    In particular, mandatory_clear means every mandatory cell is already CLEAR;
    an accepted optional crossing cannot supply that missing premise.
    """
    if mandatory_clear is not True or other_gates_pass is not True:
        return False
    if candidate_verdict == "RELEASE":
        return True
    return (candidate_verdict == "RELEASE-WITH-RISK"
            and crossings_optional_only is True and policy_allows_risk is True
            and exact_valid_acceptance is True)


def decision_construction() -> dict:
    grid = (ZERO, HALF, ONE)
    triples = list(product(grid, repeat=3))
    acceptances = (("absent", None), ("valid_covering_both", (True, 3)),
                   ("invalid_supplied", (False, 3)), ("valid_covering_only_first", (True, 1)))
    counts: Counter[str] = Counter()
    violations = 0
    evaluated = 0
    for threats in product(triples, repeat=2):
        intervals_valid = all(l <= u for l, u, _ in threats)
        floor_violation = any(l > tau for l, _, tau in threats)
        crosses = {i for i, (l, u, tau) in enumerate(threats) if l <= tau < u}
        for missing_mask, mandatory, (name, acceptance), actionable_mask in product(
            range(4), (False, True), acceptances, range(4)
        ):
            result = reduce_verdict(threats, missing_mask=missing_mask,
                                    mandatory_complete=mandatory, acceptance=acceptance,
                                    actionable_mask=actionable_mask)
            accepted = set() if acceptance is None else {i for i in range(2) if acceptance[1] & (1 << i)}
            acceptance_invalid = acceptance is not None and (not acceptance[0] or not crosses <= accepted)
            blocked = bool(missing_mask) or not mandatory or not intervals_valid or floor_violation or acceptance_invalid
            # Declarative mutually exclusive conditions, independent of branch order.
            conditions = {
                "BLOCK": blocked or (not blocked and bool(crosses) and acceptance is None
                                     and not all(actionable_mask & (1 << i) for i in crosses)),
                "RELEASE": not blocked and not crosses,
                "RELEASE-WITH-RISK": not blocked and bool(crosses) and acceptance is not None,
                "INCONCLUSIVE": not blocked and bool(crosses) and acceptance is None
                                and all(actionable_mask & (1 << i) for i in crosses),
            }
            require(sum(bool(x) for x in conditions.values()) == 1, "declarative cases partition the grid")
            if not conditions[result]:
                violations += 1
            counts[result] += 1
            evaluated += 1
    require(violations == 0, "ordered reducer agrees with declarative semantics on the exact grid")
    require(evaluated == 27 ** 2 * 4 * 2 * 4 * 4, "complete stated finite Cartesian product")
    named = [
        ("demonstrated_violation_cannot_be_accepted", ((F(7, 10), F(9, 10), F(3, 5)),), {"acceptance": (True, 1)}, "BLOCK"),
        ("crossing_accepted_not_proven_safe", ((F(2, 5), F(4, 5), F(3, 5)),), {"acceptance": (True, 1)}, "RELEASE-WITH-RISK"),
        ("crossing_with_resolver", ((F(2, 5), F(4, 5), F(3, 5)),), {"actionable_mask": 1}, "INCONCLUSIVE"),
        ("crossing_without_resolver_or_acceptance", ((F(2, 5), F(4, 5), F(3, 5)),), {}, "BLOCK"),
        ("contradictory_interval", ((F(7, 10), F(2, 5), F(3, 5)),), {"acceptance": (True, 1)}, "BLOCK"),
        ("missing_evidence_with_acceptance", ((ZERO, ONE, HALF),), {"missing_mask": 1, "acceptance": (True, 1)}, "BLOCK"),
        ("empty_threat_set", (), {}, "BLOCK"),
        ("out_of_range_interval", ((F(-1), ONE, HALF),), {}, "BLOCK"),
        ("ceiling_equal_threshold", ((HALF, F(3, 5), F(3, 5)),), {}, "RELEASE"),
        ("floor_equal_threshold_is_crossing", ((F(3, 5), F(4, 5), F(3, 5)),), {"actionable_mask": 1}, "INCONCLUSIVE"),
    ]
    cases = []
    for name, threats, kwargs, expected in named:
        actual = reduce_verdict(threats, **kwargs)
        require(actual == expected, name)
        cases.append({"name": name, "intervals_and_thresholds": [[rational(x) for x in row] for row in threats],
                      "actual": actual, "expected": expected})
    common = {"mandatory_clear": True, "other_gates_pass": True,
              "crossings_optional_only": True, "policy_allows_risk": True,
              "exact_valid_acceptance": True}
    selection_cases = [
        ("mandatory_CLEAR_optional_INCONCLUSIVE", "INCONCLUSIVE", {}, False),
        ("mandatory_CLEAR_accepted_optional_RWR", "RELEASE-WITH-RISK", {}, True),
        ("mandatory_unresolved_RWR", "RELEASE-WITH-RISK", {"mandatory_clear": False}, False),
        ("optional_RWR_missing_acceptance", "RELEASE-WITH-RISK", {"exact_valid_acceptance": False}, False),
        ("optional_RWR_policy_not_permitted", "RELEASE-WITH-RISK", {"policy_allows_risk": False}, False),
        ("all_RELEASE_mandatory_CLEAR", "RELEASE", {"crossings_optional_only": False,
            "policy_allows_risk": False, "exact_valid_acceptance": False}, True),
    ]
    selection_controls = []
    for name, verdict, changes, expected in selection_cases:
        premises = {**common, **changes}
        actual = selection_admissible(verdict, **premises)
        require(actual == expected, name)
        selection_controls.append({"name": name, "candidate_verdict": verdict,
                                   "supplied_premises": premises,
                                   "eligible": actual, "expected_eligible": expected})
    return {
        "id": "G6_decision_precedence",
        "hypothesis": "Exactly two threats on rational endpoint/threshold grid {0,1/2,1}, including reversed intervals; four missing-evidence masks, two mandatory-obligation flags, four acceptance states, four actionability masks.",
        "grid_evaluations": evaluated,
        "verdict_counts": dict(sorted(counts.items())),
        "declarative_disagreements": violations,
        "named_boundary_cases": cases,
        "selection_controls": selection_controls,
        "selection_control_count": len(selection_controls),
        "selection_control_boundary": "Six separate named strict-selection controls, excluded from the 93,312 reducer-grid cases and ten reducer-boundary cases. Supplied trust/policy/gate predicates are not implemented validators.",
        "finite_check_count": evaluated + len(cases),
        "count_unit": "standalone reducer input cases (93,312 Cartesian cases plus ten named boundary cases)",
        "counterexample": "Acceptance cannot override missing or inconsistent evidence or an excessive floor; accepting a crossing does not imply its unknown true risk is below threshold.",
        "repair_control": "The explicit reducer gives BLOCK precedence, requires acceptance of all crossings, and permits INCONCLUSIVE only for actionable crossings with complete admissible evidence. The separate strict-selection predicate rejects INCONCLUSIVE and requires every mandatory CLEAR; RWR is eligible only for permitted optional crossings with exact valid acceptance.",
        "remaining_boundary": "Acceptance validity and actionable resolution are supplied predicates here. This is neither a production acceptance validator nor a proof/refinement of the core Python or deployed gateway.",
        "passed": True,
    }


def grant_revocation_construction() -> dict:
    """Exhaust the finite interleavings for one request and one revocation.

    A grant permits only this already admitted request, not a future request.
    One initial budget unit is consumed on grant. Completion does not imply
    that a prior disclosure can be undone, and is not a new request grant.
    """
    split_orders = []
    for order in permutations(("check", "revoke", "grant")):
        if order.index("check") > order.index("grant"):
            continue
        authorized, remaining, checked = True, 1, False
        granted, stale_grant = False, False
        for event in order:
            if event == "check":
                checked = authorized and remaining >= 1
            elif event == "revoke":
                authorized = False
            else:
                granted = checked
                if granted:
                    stale_grant = not authorized
                    remaining -= 1
        split_orders.append({"order": list(order), "grant_allowed": granted,
                             "grant_after_revocation": stale_grant,
                             "remaining_budget": remaining})
    require(len(split_orders) == 3, "all legal split check-before-grant orders are enumerated")
    require(sum(row["grant_after_revocation"] for row in split_orders) == 1,
            "split check/revoke/grant permits exactly one stale-grant order")
    atomic_orders = []
    for order in permutations(("atomic_status_budget_grant", "revoke")):
        authorized, remaining, granted = True, 1, False
        stale_grant = False
        for event in order:
            if event == "revoke":
                authorized = False
            else:
                granted = authorized and remaining >= 1
                if granted:
                    stale_grant = not authorized
                    remaining -= 1
        atomic_orders.append({"order": list(order), "grant_allowed": granted,
                              "grant_after_revocation": stale_grant,
                              "remaining_budget": remaining,
                              "already_granted_request_may_complete_after_revocation": granted})
    require(len(atomic_orders) == 2, "both serialized atomic-grant/revocation orders are enumerated")
    require(not any(row["grant_after_revocation"] for row in atomic_orders),
            "no grant linearized after revocation is admitted")
    require(atomic_orders[0]["grant_allowed"] and not atomic_orders[1]["grant_allowed"],
            "atomic ordering distinguishes pre-revocation and post-revocation requests")
    return {
        "hypothesis": "One initially authorized request, one budget unit, one revocation; a captured split check may be stale. The repair assumes a single atomic current-status/budget/grant operation serialized with revocation.",
        "split_status_check_orders": split_orders,
        "atomic_status_budget_grant_orders": atomic_orders,
        "control_count": 5,
        "count_unit": "three legal split orders plus two atomic serialized orders, separate from the two semantic-authenticity worlds",
        "split_stale_grant_orders": 1,
        "atomic_stale_grant_orders": 0,
        "remaining_boundary": "This exact finite state toy is not a gateway implementation or proof of distributed linearizability. Atomic serialization, faithful enforcement, and one-request grant binding are explicit premises. Revocation blocks later grants; it cannot retract prior disclosures and does not necessarily cancel a previously granted in-flight request.",
        "passed": True,
    }


def authentication_construction() -> dict:
    # An ideal authenticity oracle accepts an honestly issued statement. It
    # deliberately has no implementation, key bytes, or cryptographic algorithm.
    statement = {"issuer": "authorized_test_role", "declared_context": "same_declared_context",
                 "lower": "1/2", "upper": "11/20", "tolerance": "3/5"}
    issued_statement = json.dumps(statement, sort_keys=True, separators=(",", ":"))
    cases = []
    for name, channel in (("truthful_constant_world", SAFE), ("false_secret_export_world", REVEAL)):
        received_statement = json.dumps(statement, sort_keys=True, separators=(",", ":"))
        authentic = received_statement == issued_statement
        true_risk = guessing_value(channel)
        valid_premise = true_risk <= F(statement["upper"])
        require(authentic, "honest issuance authenticates the same statement in both semantic worlds")
        verdict = reduce_verdict(((F(statement["lower"]), F(statement["upper"]), F(statement["tolerance"])),))
        require(verdict == "RELEASE", "ignoring semantic admission clears the reported endpoints")
        cases.append({"world": name, "authentic_by_ideal_oracle": authentic,
                      "true_success": rational(true_risk), "ceiling_semantically_valid": valid_premise,
                      "authentication_only_decision": verdict,
                      "complete_finite_channel_admission": "ADMIT" if valid_premise else "REJECT"})
    require(cases[0]["ceiling_semantically_valid"] and not cases[1]["ceiling_semantically_valid"], "same authentic claim can be true or false")
    return {
        "id": "G7_authentication_not_truth",
        "hypothesis": "An ideal authenticity oracle recognizes an authorized issuer's exact statement; truthful computation and complete live channel identity are deliberately not supplied by that oracle.",
        "statement": statement,
        "semantic_worlds": cases,
        "grant_revocation_controls": grant_revocation_construction(),
        "finite_check_count": 2,
        "count_unit": "semantic world evaluations; no signatures are generated or attacked",
        "counterexample": "An authorized issuer can honestly issue bytes containing a false ceiling. Authentication alone cannot establish the proposition those bytes assert.",
        "repair_control": "A separate exact finite-channel admission check rejects the false ceiling. Real deployment needs applicable verified evidence and a justified channel/measurement binding, not a stronger signature on the same assertion.",
        "remaining_boundary": "This is not an Ed25519 experiment, collision, forgery, or claim that the production importer accepts this toy object. No protocol can infer unobserved semantic truth from authenticity alone.",
        "passed": True,
    }


def build_report() -> dict:
    studies = [floor_construction(), selection_construction(), scope_construction(),
               xor_construction(), transfer_construction(), decision_construction(),
               authentication_construction()]
    return {
        "artifact_role": ARTIFACT_ROLE,
        "format_version": "1.0",
        "generator": {"path": GENERATOR_PATH,
                      "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "method": "Exact fractions, finite deterministic decoder enumeration, closed finite probability sums, and exhaustive stated reducer grid. No randomness or statistical sampling.",
        "reproducibility": {"seed": None, "dependencies": "Python standard library only",
                            "network_used": False, "timestamps_in_output": False,
                            "core_code_imported": False, "production_schema_added": False},
        "claim_limits": [
            "These are constructed controls, not additional trained-model privacy or scalability experiments.",
            "Finite checks do not prove universal mathematical statements or implementation refinement.",
            "There is no cryptographic implementation or deployed registry/gateway test in this artifact.",
            "General impossibility claims are conditional on the explicitly restricted observations or premises, not claims that every richer design is impossible.",
            "Counts have different units and must not be pooled into a scientific success rate.",
        ],
        "studies": studies,
        "all_constructed_checks_passed": all(study["passed"] for study in studies),
    }


def report_bytes() -> bytes:
    return (json.dumps(build_report(), indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def validate_output_target(output: Path, *, writing: bool) -> None:
    """Limit ordinary regeneration to this artifact role, never another source.

    The resolved path checks also reject symlinks into protected repository
    directories. They are accidental-overwrite guards, not a claim of safety
    against a concurrent adversary mutating filesystem links after this check.
    """
    if output.suffix.lower() != ".json":
        raise ValueError("the output must be a .json artifact, never a source file")
    protected_roots = [ROOT / name for name in (
        "src", "schemas", "scripts", "tests", "academic/scripts", "academic/tests"
    )]
    if any(output.is_relative_to(path.resolve()) for path in protected_roots):
        raise ValueError("the output cannot target core, schema, script, or test directories")
    if output == (ROOT / "academic" / "paper" / "experimental-data.json").resolve():
        raise ValueError("the historical experimental-data companion is not a gap-construction output")
    if output.exists() and not output.is_file():
        raise ValueError("the output target is not a regular file")
    if writing and output.is_file():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise ValueError("refusing to overwrite an existing unreadable or unrelated JSON artifact") from error
        if (not isinstance(existing, dict) or existing.get("artifact_role") != ARTIFACT_ROLE
                or not isinstance(existing.get("generator"), dict)
                or existing["generator"].get("path") != GENERATOR_PATH):
            raise ValueError("refusing to overwrite an existing unrelated JSON artifact")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare exact generated bytes without writing")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    try:
        validate_output_target(output, writing=not args.check)
    except ValueError as error:
        parser.error(str(error))
    expected = report_bytes()
    if args.check:
        if not output.is_file() or output.read_bytes() != expected:
            print("Finite construction artifact is missing or differs from exact replay.")
            return 1
        print("Seven exact finite constructions replay byte-for-byte; this is not a model experiment or refinement proof.")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(expected)
    print(f"Wrote {len(expected)} bytes of exact finite constructed validation to {output.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
