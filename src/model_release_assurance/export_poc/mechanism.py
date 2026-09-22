"""Two-stage model export on one fixed, public synthetic fixture.

This is an executable finite-mechanism reference, not an agency-data adapter.
The private coordinator retains X, Y, A and E=X xor A; E together with A is
equivalent to retaining X. Trainers receive only protected values and public
groups. The model is an actual fitted group Bernoulli forecast, not the raw
protected records. No model-quality or real-data suitability claim follows.

Random draws use the OS-backed ``secrets`` API. Two-sided geometric noise is
sampled without a floating-point inverse CDF or truncating its support. The
DP statement concerns the ideal mechanism with private, faithful randomness;
these Python checks are not a proof of a production random-number generator.
"""

from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import random
import secrets
from typing import Any


ROUTES = ("retained-state", "independent", "central-count")
PUBLIC_GROUP_IDS = tuple(f"group_{i}" for i in range(8))
PEOPLE_PER_GROUP = 64
FIXTURE = "fixed-public-service-use-v1"
PROTECTED_UNIT = "one fixed-roster citizen two-bit profile"
BUNDLE_SCHEMA = "mra-export-poc-model-v1"
STATE_SCHEMA = "mra-export-poc-state-v1"
CERTIFICATE_SCHEMA = "mra-export-poc-certificate-v1"


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _fixture() -> tuple[list[str], list[int], list[int]]:
    """Return public deterministic data; no citizen identifiers are generated."""
    groups, xs, ys = [], [], []
    for g, group in enumerate(PUBLIC_GROUP_IDS):
        for i in range(PEOPLE_PER_GROUP):
            groups.append(group)
            xs.append(int((i * 29 + g * 7) % 64 < 8 + g * 6))
            ys.append(int((i * 17 + g * 13) % 64 < 12 + g * 5))
    return groups, xs, ys


def _truth(numerator: int, denominator: int) -> bool:
    if (type(numerator) is not int or type(denominator) is not int
            or denominator <= 0 or not 0 <= numerator <= denominator):
        raise ValueError("Invalid exact Bernoulli probability")
    return secrets.randbelow(denominator) < numerator


def _geometric() -> int:
    """P(G=k)=2^(-k-1), k>=0, with unbounded support."""
    count = 0
    while secrets.randbelow(2) == 0:
        count += 1
    return count


def _two_sided_geometric() -> int:
    """P(N=k)=2^(-abs(k))/3; neighboring count ratio is at most 2."""
    return _geometric() - _geometric()


def _clip(value: Fraction) -> float:
    return float(max(Fraction(0), min(Fraction(1), value)))


def _fit_perturbed(groups: list[str], values: list[int], truth: Fraction) -> dict:
    """Fit Bernoulli rates by inverting known RR bias, then clipping.

    This deterministic estimator uses protected observations only. Its input
    truth probability is the marginal truth probability of the specified
    channel. Fitting error is not the channel's per-person answer accuracy.
    """
    result = {}
    for group in PUBLIC_GROUP_IDS:
        selected = [v for g, v in zip(groups, values) if g == group]
        mean = Fraction(sum(selected), len(selected))
        result[group] = _clip((mean - (1 - truth)) / (2 * truth - 1))
    return result


def _bundle(stage: int, route: str, probabilities: dict,
            parent: str | None) -> bytes:
    return _canonical({
        "schema": BUNDLE_SCHEMA,
        "stage": stage,
        "route": route,
        "fixture": FIXTURE,
        "model": {
            "family": "group-bernoulli-forecast",
            "target": f"period{stage}_service_use",
            "probabilities": probabilities,
        },
        "preprocessing": {
            "public_group_ids": list(PUBLIC_GROUP_IDS),
            "unknown_group": "reject",
        },
        "guarantee": {
            "history_ratio": 2 if stage == 1 else 4,
            "delta": 0,
            "protected_unit": PROTECTED_UNIT,
            "scope": "fixed roster and public group membership; replacement privacy",
        },
        "parent_artifact_sha256": parent,
    })


def _certificate(stage: int, route: str, parent: str | None) -> dict:
    return {
        "schema": CERTIFICATE_SCHEMA,
        "stage": stage,
        "route": route,
        "history_ratio": 2 if stage == 1 else 4,
        "delta": 0,
        "protected_unit": PROTECTED_UNIT,
        "trusted_producer": "fixed-synthetic-fixture-v1",
        "first_artifact_sha256": parent,
    }


def first_release() -> tuple[dict, bytes, dict]:
    """Produce the first model; returned state must remain inside the broker."""
    groups, xs, ys = _fixture()
    answers = [x if _truth(2, 3) else 1 - x for x in xs]
    flips = [x ^ answer for x, answer in zip(xs, answers)]
    bundle = _bundle(1, "first-rr", _fit_perturbed(groups, answers, Fraction(2, 3)), None)
    state = {
        "schema": STATE_SCHEMA,
        "stage": 1,
        "fixture": FIXTURE,
        "groups": groups,
        "X": xs,
        "Y": ys,
        "A": answers,
        "E": flips,
        "first_bundle_sha256": hashlib.sha256(bundle).hexdigest(),
    }
    return state, bundle, _certificate(1, "first-rr", None)


def _validate_first_state(state: dict) -> None:
    expected = {"schema", "stage", "fixture", "groups", "X", "Y", "A", "E",
                "first_bundle_sha256"}
    if type(state) is not dict or set(state) != expected:
        raise ValueError("Expected authentic first-stage private state")
    if (state["schema"] != STATE_SCHEMA or type(state["stage"]) is not int
            or state["stage"] != 1 or state["fixture"] != FIXTURE):
        raise ValueError("Only the fixed fixture's first stage can be extended")
    groups, xs, ys = _fixture()
    for key, target in (("groups", groups), ("X", xs), ("Y", ys)):
        if state[key] != target:
            raise ValueError("External or modified datasets are unsupported")
    for key in ("X", "Y", "A", "E"):
        values = state[key]
        if (type(values) is not list or len(values) != len(groups)
                or any(type(v) is not int or v not in (0, 1) for v in values)):
            raise ValueError("Invalid bit-vector state")
    if any(x ^ a != e for x, a, e in zip(xs, state["A"], state["E"])):
        raise ValueError("Retained flip does not match the first answer")
    first = _bundle(1, "first-rr", _fit_perturbed(groups, state["A"], Fraction(2, 3)), None)
    if state["first_bundle_sha256"] != hashlib.sha256(first).hexdigest():
        raise ValueError("Private state does not match its first model artifact")


def next_release(private_state: dict, route: str) -> tuple[dict, bytes, dict]:
    """Extend the fixed first release once through one of three routes.

    The central-count route adds independent ratio-2 geometric noise to each
    public group's Y count. One citizen changes one fixed group's count by
    at most one, so the vector is log(2)-DP; composition with the first
    log(2)-DP release gives log(4). This is a sufficient bound for the model
    history, not a measured sharp leakage or a license to change groups.

    Branches must not all be exported from the same first release under a
    ratio-4 claim. The durable broker is responsible for enforcing this.
    """
    if route not in ROUTES:
        raise ValueError("Unsupported second-stage route")
    _validate_first_state(private_state)
    state = copy.deepcopy(private_state)
    groups, ys = state["groups"], state["Y"]
    if route == "central-count":
        noisy = {
            group: sum(y for g, y in zip(groups, ys) if g == group) + _two_sided_geometric()
            for group in PUBLIC_GROUP_IDS
        }
        probabilities = {g: _clip(Fraction(noisy[g], PEOPLE_PER_GROUP))
                         for g in PUBLIC_GROUP_IDS}
        state["noisy_counts"] = noisy
    else:
        if route == "retained-state":
            answers = [y if _truth(4 if e == 0 else 3, 5) else 1 - y
                       for y, e in zip(ys, state["E"])]
            accuracy = Fraction(11, 15)
        else:
            answers = [y if _truth(2, 3) else 1 - y for y in ys]
            accuracy = Fraction(2, 3)
        state["B"] = answers
        probabilities = _fit_perturbed(groups, answers, accuracy)
    state["stage"] = 2
    state["route"] = route
    parent = state["first_bundle_sha256"]
    return state, _bundle(2, route, probabilities, parent), _certificate(2, route, parent)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def inspect_bundle(bundle_bytes: bytes) -> dict:
    """Strict allowlist validator for exported JSON, not a privacy attestation."""
    if type(bundle_bytes) is not bytes or len(bundle_bytes) > 16384:
        raise ValueError("Invalid model bundle size/type")
    try:
        value = json.loads(bundle_bytes.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid model JSON") from exc
    keys = {"schema", "stage", "route", "fixture", "model", "preprocessing",
            "guarantee", "parent_artifact_sha256"}
    if type(value) is not dict or set(value) != keys or value["schema"] != BUNDLE_SCHEMA:
        raise ValueError("Unexpected export fields/schema")
    stage, route = value["stage"], value["route"]
    if (type(stage) is not int or stage not in (1, 2)
            or (stage == 1 and route != "first-rr") or (stage == 2 and route not in ROUTES)
            or value["fixture"] != FIXTURE):
        raise ValueError("Invalid export stage/route/fixture")
    parent = value["parent_artifact_sha256"]
    if stage == 1:
        if parent is not None:
            raise ValueError("First export cannot have a parent")
    elif (type(parent) is not str or len(parent) != 64
          or any(c not in "0123456789abcdef" for c in parent)):
        raise ValueError("Invalid parent artifact digest")
    model = value["model"]
    if (type(model) is not dict or set(model) != {"family", "target", "probabilities"}
            or model["family"] != "group-bernoulli-forecast"
            or model["target"] != f"period{stage}_service_use"):
        raise ValueError("Unexpected model fields")
    rates = model["probabilities"]
    if (type(rates) is not dict or set(rates) != set(PUBLIC_GROUP_IDS)
            or any(type(p) not in (int, float) or not 0 <= p <= 1 or not math.isfinite(p)
                   for p in rates.values())):
        raise ValueError("Invalid public-group forecasts")
    guarantee = value["guarantee"]
    if (type(guarantee) is not dict
            or type(guarantee.get("history_ratio")) is not int
            or type(guarantee.get("delta")) is not int):
        raise ValueError("Invalid privacy metadata types")
    expected = json.loads(_bundle(stage, route, rates, parent))
    if value != expected:
        raise ValueError("Unexpected preprocessing or privacy metadata")
    return value


def public_fixture_evaluation(bundle_bytes: bytes, target: str | None = None) -> dict:
    """Evaluate a separate PUBLIC synthetic holdout, never agency labels.

    Its fixed simulation stream is unrelated to the secure mechanism draws.
    The task rates are public and predeclared in ``_fixture``. This diagnostic
    can establish performance on this synthetic task, not a real population.
    ``target='period2'`` evaluates an unchanged first model as a reuse baseline.
    """
    bundle = inspect_bundle(bundle_bytes)
    target = target or f"period{bundle['stage']}"
    if target not in ("period1", "period2"):
        raise ValueError("Unknown public evaluation target")
    # This public fixture seed is NEVER used by either privacy mechanism.
    simulator = random.Random(2026092001)
    groups, labels = [], []
    for g, group in enumerate(PUBLIC_GROUP_IDS):
        for _ in range(256):
            x = int(simulator.random() < (8 + g * 6) / 64)
            y = int(simulator.random() < (12 + g * 5) / 64)
            groups.append(group)
            labels.append(x if target == "period1" else y)
    rates = bundle["model"]["probabilities"]
    brier = sum((rates[g] - y) ** 2 for g, y in zip(groups, labels)) / len(labels)
    count_mae = sum(abs(256 * rates[g]
                        - sum(y for group, y in zip(groups, labels) if group == g))
                    for g in PUBLIC_GROUP_IDS) / len(PUBLIC_GROUP_IDS)
    return {"scope": "separate public synthetic holdout; no agency or real-population validation",
            "cohort_type": "fixed synthetic holdout", "target": target,
            "brier_score": brier, "group_count_mae": count_mae,
            "citizens": len(labels), "groups": len(PUBLIC_GROUP_IDS)}


def verify_exact_channels() -> dict:
    """Check all finite binary channels with exact fractions; no simulation.

    This computational check substantiates the specified kernels, not their
    implementation isolation or general model-training utility.
    """
    profiles = [(x, y) for x in (0, 1) for y in (0, 1)]
    outputs = [(a, b) for a in (0, 1) for b in (0, 1)]
    rows = []
    independent_rows = []
    for x, y in profiles:
        row, independent_row = [], []
        for a, b in outputs:
            first = Fraction(2 if x == a else 1, 3)
            truth = Fraction(4 if x == a else 3, 5)
            row.append(first * (truth if y == b else 1 - truth))
            independent_row.append(first * Fraction(2 if y == b else 1, 3))
        if sum(row) != 1 or sum(independent_row) != 1:
            raise AssertionError("Channel normalization failed")
        for a in (0, 1):
            if sum(row[j] for j, (out_a, _) in enumerate(outputs) if out_a == a) != Fraction(2 if x == a else 1, 3):
                raise AssertionError("Immutable first marginal failed")
        rows.append(row)
        independent_rows.append(independent_row)
    ratio = max(rows[i][j] / rows[k][j] for i in range(4) for k in range(4) for j in range(4))
    independent_ratio = max(independent_rows[i][j] / independent_rows[k][j]
                            for i in range(4) for k in range(4) for j in range(4))
    accuracy = sum(rows[i][j] for i, (_, y) in enumerate(profiles)
                   for j, (_, b) in enumerate(outputs) if y == b) / 4
    if ratio != 4 or independent_ratio != 4 or accuracy != Fraction(11, 15):
        raise AssertionError("Joint mechanism contract failed")
    return {"finite_profiles": 4, "outputs": 4, "first_ratio": 2,
            "retained_history_ratio": 4, "independent_history_ratio": 4,
            "retained_answer_accuracy": str(accuracy),
            "scope": "exact finite channel check; no production or model-utility proof"}
