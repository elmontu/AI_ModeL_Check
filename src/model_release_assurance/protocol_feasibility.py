"""Finite protocol-feasibility solver and exact certificate verifier.

The mathematical protocol treats privacy, utility, control, and portfolio
requirements as one world-dependent acceptability predicate. This module solves
the finite stochastic soundness-liveness program for explicitly supplied rational
evidence laws, exactly replays primal and dual certificates, and retains the
zero-error support-set construction as a corollary. It does not infer a complete
world model or evidence law from deployment data, and it is not a production
authorization service.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from pydantic import Field, model_validator

from .incomplete_portfolio import RationalNumber
from .integrity import canonical_json_bytes, sha256_bytes
from .models import StrictModel


REFUSAL_ACTION_ID = "__REFUSE__"
MAX_DETERMINISTIC_PROTOCOLS = 1_000_000


class AuthorizationMode(StrEnum):
    RANDOMIZED = "randomized"
    DETERMINISTIC = "deterministic"


class ProtocolWorld(StrictModel):
    world_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    evidence_probabilities: tuple[RationalNumber, ...] = Field(min_length=1)
    acceptable_configuration_ids: tuple[str, ...] = ()


class ProtocolFeasibilityProblem(StrictModel):
    """Finite, rationally encoded evidence-protocol decision problem."""

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    configuration_ids: tuple[str, ...] = Field(min_length=1)
    worlds: tuple[ProtocolWorld, ...] = Field(min_length=1)
    unsafe_release_budget: RationalNumber
    liveness_failure_budget: RationalNumber
    authorization_mode: AuthorizationMode = AuthorizationMode.RANDOMIZED

    @model_validator(mode="after")
    def finite_problem_is_coherent(self) -> ProtocolFeasibilityProblem:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence identifiers must be unique")
        if len(set(self.configuration_ids)) != len(self.configuration_ids):
            raise ValueError("configuration identifiers must be unique")
        if REFUSAL_ACTION_ID in self.configuration_ids:
            raise ValueError(f"{REFUSAL_ACTION_ID!r} is reserved for refusal")
        if len(set(world.world_id for world in self.worlds)) != len(self.worlds):
            raise ValueError("world identifiers must be unique")
        configurations = set(self.configuration_ids)
        for world in self.worlds:
            if len(world.evidence_probabilities) != len(self.evidence_ids):
                raise ValueError(
                    f"world {world.world_id} must contain one probability per evidence transcript"
                )
            if sum((_fraction(value) for value in world.evidence_probabilities), Fraction()) != 1:
                raise ValueError(
                    f"world {world.world_id} evidence probabilities must sum exactly to one"
                )
            if len(set(world.acceptable_configuration_ids)) != len(
                world.acceptable_configuration_ids
            ):
                raise ValueError(
                    f"world {world.world_id} acceptable configuration identifiers must be unique"
                )
            unknown = set(world.acceptable_configuration_ids) - configurations
            if unknown:
                raise ValueError(
                    f"world {world.world_id} contains unknown acceptable configurations: "
                    f"{sorted(unknown)}"
                )
        if not any(world.acceptable_configuration_ids for world in self.worlds):
            raise ValueError("at least one world must contain an acceptable release configuration")
        for name, value in (
            ("unsafe_release_budget", self.unsafe_release_budget),
            ("liveness_failure_budget", self.liveness_failure_budget),
        ):
            if _fraction(value) > 1:
                raise ValueError(f"{name} must lie in [0,1]")
        return self


class ProtocolKernelRow(StrictModel):
    evidence_id: str
    action_probabilities: tuple[RationalNumber, ...]


class ProtocolPrimalCertificate(StrictModel):
    action_ids: tuple[str, ...]
    kernel_rows: tuple[ProtocolKernelRow, ...]
    unsafe_by_world: tuple[RationalNumber, ...]
    liveness_by_feasible_world: tuple[RationalNumber, ...]
    minimum_liveness: RationalNumber


class ProtocolDualCertificate(StrictModel):
    feasible_world_ids: tuple[str, ...]
    liveness_multipliers: tuple[RationalNumber, ...]
    world_ids: tuple[str, ...]
    unsafe_multipliers: tuple[RationalNumber, ...]
    evidence_ids: tuple[str, ...]
    simplex_multipliers: tuple[RationalNumber, ...]
    objective_upper: RationalNumber


class ProtocolFeasibilityCertificate(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    certificate_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    problem: ProtocolFeasibilityProblem
    problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    solver: str
    status: Literal["target_met", "target_impossible", "numerically_unresolved"]
    target_liveness: RationalNumber
    primal: ProtocolPrimalCertificate
    dual: ProtocolDualCertificate | None = None
    deterministic_protocols_checked: int | None = Field(default=None, ge=1)


class ProtocolCertificateVerification(StrictModel):
    valid: bool
    status: Literal["target_met", "target_impossible", "numerically_unresolved"]
    exact_lower_numerator: int = Field(ge=0)
    exact_lower_denominator: int = Field(gt=0)
    exact_upper_numerator: int = Field(ge=0)
    exact_upper_denominator: int = Field(gt=0)
    reasons: tuple[str, ...]


def _fraction(value: RationalNumber) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rational(value: Fraction) -> RationalNumber:
    return RationalNumber(numerator=value.numerator, denominator=value.denominator)


def protocol_problem_sha256(problem: ProtocolFeasibilityProblem) -> str:
    return sha256_bytes(canonical_json_bytes(problem))


def _problem_tables(
    problem: ProtocolFeasibilityProblem,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[Fraction, ...], ...],
    tuple[frozenset[str], ...],
]:
    evidence_ids = problem.evidence_ids
    action_ids = (*problem.configuration_ids, REFUSAL_ACTION_ID)
    world_ids = tuple(world.world_id for world in problem.worlds)
    probabilities = tuple(
        tuple(_fraction(value) for value in world.evidence_probabilities)
        for world in problem.worlds
    )
    acceptable = tuple(
        frozenset(world.acceptable_configuration_ids) for world in problem.worlds
    )
    return evidence_ids, action_ids, world_ids, probabilities, acceptable


def _evaluate_kernel(
    problem: ProtocolFeasibilityProblem,
    kernel: tuple[tuple[Fraction, ...], ...],
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...], Fraction]:
    evidence_ids, action_ids, _, probabilities, acceptable = _problem_tables(problem)
    if len(kernel) != len(evidence_ids):
        raise ValueError("protocol kernel has the wrong number of evidence rows")
    for row in kernel:
        if len(row) != len(action_ids) or any(value < 0 for value in row) or sum(row) != 1:
            raise ValueError("every protocol kernel row must be a probability vector")
    unsafe: list[Fraction] = []
    liveness: list[Fraction] = []
    for world_index, world in enumerate(problem.worlds):
        unsafe_value = Fraction()
        liveness_value = Fraction()
        for evidence_index, evidence_probability in enumerate(probabilities[world_index]):
            for action_index, action_id in enumerate(action_ids):
                mass = evidence_probability * kernel[evidence_index][action_index]
                if action_id == REFUSAL_ACTION_ID:
                    continue
                if action_id in acceptable[world_index]:
                    liveness_value += mass
                else:
                    unsafe_value += mass
        unsafe.append(unsafe_value)
        if world.acceptable_configuration_ids:
            liveness.append(liveness_value)
    return tuple(unsafe), tuple(liveness), min(liveness)


def _primal_certificate(
    problem: ProtocolFeasibilityProblem,
    kernel: tuple[tuple[Fraction, ...], ...],
) -> ProtocolPrimalCertificate:
    evidence_ids, action_ids, _, _, _ = _problem_tables(problem)
    unsafe, liveness, minimum = _evaluate_kernel(problem, kernel)
    return ProtocolPrimalCertificate(
        action_ids=action_ids,
        kernel_rows=tuple(
            ProtocolKernelRow(
                evidence_id=evidence_id,
                action_probabilities=tuple(_rational(value) for value in row),
            )
            for evidence_id, row in zip(evidence_ids, kernel, strict=True)
        ),
        unsafe_by_world=tuple(_rational(value) for value in unsafe),
        liveness_by_feasible_world=tuple(_rational(value) for value in liveness),
        minimum_liveness=_rational(minimum),
    )


def _exact_dual_from_float(
    problem: ProtocolFeasibilityProblem,
    liveness_values: Iterable[float],
    unsafe_values: Iterable[float],
    *,
    maximum_denominator: int,
) -> ProtocolDualCertificate:
    evidence_ids, action_ids, world_ids, probabilities, acceptable = _problem_tables(problem)
    feasible_indices = tuple(
        index for index, world in enumerate(problem.worlds)
        if world.acceptable_configuration_ids
    )
    y = tuple(
        Fraction(str(max(0.0, float(value)))).limit_denominator(maximum_denominator)
        for value in liveness_values
    )
    y_total = sum(y, Fraction())
    if y_total <= 0:
        y = tuple(Fraction(1, len(feasible_indices)) for _ in feasible_indices)
    else:
        y = tuple(value / y_total for value in y)
    z = tuple(
        Fraction(str(max(0.0, float(value)))).limit_denominator(maximum_denominator)
        for value in unsafe_values
    )
    q: list[Fraction] = []
    for evidence_index in range(len(evidence_ids)):
        required = Fraction()
        for action_id in action_ids:
            value = Fraction()
            for y_index, world_index in enumerate(feasible_indices):
                if action_id in acceptable[world_index]:
                    value += y[y_index] * probabilities[world_index][evidence_index]
            for world_index in range(len(problem.worlds)):
                if (
                    action_id != REFUSAL_ACTION_ID
                    and action_id not in acceptable[world_index]
                ):
                    value -= z[world_index] * probabilities[world_index][evidence_index]
            required = max(required, value)
        q.append(required)
    alpha = _fraction(problem.unsafe_release_budget)
    objective = sum(q, Fraction()) + alpha * sum(z, Fraction())
    return ProtocolDualCertificate(
        feasible_world_ids=tuple(problem.worlds[index].world_id for index in feasible_indices),
        liveness_multipliers=tuple(_rational(value) for value in y),
        world_ids=world_ids,
        unsafe_multipliers=tuple(_rational(value) for value in z),
        evidence_ids=evidence_ids,
        simplex_multipliers=tuple(_rational(value) for value in q),
        objective_upper=_rational(objective),
    )


def _randomized_protocol(
    problem: ProtocolFeasibilityProblem,
    *,
    maximum_denominator: int,
) -> tuple[ProtocolPrimalCertificate, ProtocolDualCertificate]:
    try:
        import numpy as np
        from scipy.optimize import linprog
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise RuntimeError(
            "randomized protocol optimization requires the optional portfolio dependency"
        ) from exc

    evidence_ids, action_ids, _, probabilities, acceptable = _problem_tables(problem)
    world_count = len(problem.worlds)
    evidence_count = len(evidence_ids)
    action_count = len(action_ids)
    delta_count = evidence_count * action_count
    r_index = delta_count
    feasible_indices = tuple(
        index for index, world in enumerate(problem.worlds)
        if world.acceptable_configuration_ids
    )

    objective = np.zeros(delta_count + 1)
    objective[r_index] = -1.0
    a_eq = np.zeros((evidence_count, delta_count + 1))
    b_eq = np.ones(evidence_count)
    for evidence_index in range(evidence_count):
        start = evidence_index * action_count
        a_eq[evidence_index, start:start + action_count] = 1.0

    a_ub: list[list[float]] = []
    b_ub: list[float] = []
    alpha = float(_fraction(problem.unsafe_release_budget))
    for world_index in range(world_count):
        row = [0.0] * (delta_count + 1)
        for evidence_index in range(evidence_count):
            for action_index, action_id in enumerate(action_ids):
                if (
                    action_id != REFUSAL_ACTION_ID
                    and action_id not in acceptable[world_index]
                ):
                    row[evidence_index * action_count + action_index] = float(
                        probabilities[world_index][evidence_index]
                    )
        a_ub.append(row)
        b_ub.append(alpha)
    for world_index in feasible_indices:
        row = [0.0] * (delta_count + 1)
        for evidence_index in range(evidence_count):
            for action_index, action_id in enumerate(action_ids):
                if action_id in acceptable[world_index]:
                    row[evidence_index * action_count + action_index] = -float(
                        probabilities[world_index][evidence_index]
                    )
        row[r_index] = 1.0
        a_ub.append(row)
        b_ub.append(0.0)

    result = linprog(
        objective,
        A_ub=np.asarray(a_ub),
        b_ub=np.asarray(b_ub),
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=[(0.0, None)] * (delta_count + 1),
        method="highs",
    )
    if not result.success:
        raise RuntimeError(f"protocol primal LP failed: {result.message}")

    rows: list[list[Fraction]] = []
    for evidence_index in range(evidence_count):
        raw = result.x[
            evidence_index * action_count:(evidence_index + 1) * action_count
        ]
        fractions = [
            Fraction(str(max(0.0, float(value)))).limit_denominator(maximum_denominator)
            for value in raw
        ]
        if _fraction(problem.unsafe_release_budget) == 0:
            for action_index, action_id in enumerate(action_ids):
                if action_id == REFUSAL_ACTION_ID:
                    continue
                if any(
                    probabilities[world_index][evidence_index] > 0
                    and action_id not in acceptable[world_index]
                    for world_index in range(world_count)
                ):
                    fractions[action_index] = Fraction()
        total = sum(fractions, Fraction())
        if total <= 0:
            fractions = [Fraction() for _ in action_ids]
            fractions[-1] = Fraction(1)
        else:
            fractions = [value / total for value in fractions]
        rows.append(fractions)

    kernel = tuple(tuple(row) for row in rows)
    unsafe, _, _ = _evaluate_kernel(problem, kernel)
    exact_alpha = _fraction(problem.unsafe_release_budget)
    maximum_unsafe = max(unsafe)
    if maximum_unsafe > exact_alpha:
        if exact_alpha == 0:
            raise RuntimeError("zero-error protocol rationalization introduced unsafe mass")
        scale = exact_alpha / maximum_unsafe
        repaired: list[tuple[Fraction, ...]] = []
        for row in kernel:
            non_refusal = tuple(value * scale for value in row[:-1])
            repaired.append((*non_refusal, 1 - sum(non_refusal, Fraction())))
        kernel = tuple(repaired)
    primal = _primal_certificate(problem, kernel)

    dual_variable_count = len(feasible_indices) + world_count + evidence_count
    dual_objective = np.zeros(dual_variable_count)
    dual_objective[len(feasible_indices):len(feasible_indices) + world_count] = alpha
    dual_objective[len(feasible_indices) + world_count:] = 1.0
    dual_a_ub: list[list[float]] = []
    dual_b_ub: list[float] = []
    dual_sum_y = [0.0] * dual_variable_count
    for index in range(len(feasible_indices)):
        dual_sum_y[index] = -1.0
    dual_a_ub.append(dual_sum_y)
    dual_b_ub.append(-1.0)
    for evidence_index in range(evidence_count):
        for action_id in action_ids:
            row = [0.0] * dual_variable_count
            for y_index, world_index in enumerate(feasible_indices):
                if action_id in acceptable[world_index]:
                    row[y_index] = float(probabilities[world_index][evidence_index])
            for world_index in range(world_count):
                if (
                    action_id != REFUSAL_ACTION_ID
                    and action_id not in acceptable[world_index]
                ):
                    row[len(feasible_indices) + world_index] = -float(
                        probabilities[world_index][evidence_index]
                    )
            row[len(feasible_indices) + world_count + evidence_index] = -1.0
            dual_a_ub.append(row)
            dual_b_ub.append(0.0)
    dual_result = linprog(
        dual_objective,
        A_ub=np.asarray(dual_a_ub),
        b_ub=np.asarray(dual_b_ub),
        bounds=[(0.0, None)] * dual_variable_count,
        method="highs",
    )
    if not dual_result.success:
        raise RuntimeError(f"protocol dual LP failed: {dual_result.message}")
    split_y = len(feasible_indices)
    split_z = split_y + world_count
    dual = _exact_dual_from_float(
        problem,
        dual_result.x[:split_y],
        dual_result.x[split_y:split_z],
        maximum_denominator=maximum_denominator,
    )
    if _fraction(primal.minimum_liveness) > min(Fraction(1), _fraction(dual.objective_upper)):
        raise RuntimeError("exact primal lower bound exceeds exact dual upper bound")
    return primal, dual


def _deterministic_protocol(
    problem: ProtocolFeasibilityProblem,
    *,
    maximum_protocols: int,
) -> tuple[ProtocolPrimalCertificate, int]:
    evidence_ids, action_ids, _, _, _ = _problem_tables(problem)
    protocol_count = len(action_ids) ** len(evidence_ids)
    if protocol_count > maximum_protocols:
        raise RuntimeError(
            f"deterministic frontier requires {protocol_count} protocols, above "
            f"the declared limit {maximum_protocols}"
        )
    alpha = _fraction(problem.unsafe_release_budget)
    best_liveness = Fraction(-1)
    best_assignment: tuple[int, ...] | None = None
    for assignment in itertools.product(range(len(action_ids)), repeat=len(evidence_ids)):
        kernel = tuple(
            tuple(Fraction(int(action_index == chosen)) for action_index in range(len(action_ids)))
            for chosen in assignment
        )
        unsafe, _, liveness = _evaluate_kernel(problem, kernel)
        if max(unsafe) <= alpha and liveness > best_liveness:
            best_liveness = liveness
            best_assignment = assignment
    if best_assignment is None:  # refusal is always feasible, so this is defensive
        raise RuntimeError("deterministic protocol enumeration found no feasible protocol")
    best_kernel = tuple(
        tuple(Fraction(int(action_index == chosen)) for action_index in range(len(action_ids)))
        for chosen in best_assignment
    )
    return _primal_certificate(problem, best_kernel), protocol_count


def solve_protocol_feasibility(
    problem: ProtocolFeasibilityProblem,
    *,
    certificate_id: str = "protocol-feasibility-certificate",
    maximum_denominator: int = 1_000_000_000,
    maximum_deterministic_protocols: int = MAX_DETERMINISTIC_PROTOCOLS,
) -> ProtocolFeasibilityCertificate:
    """Solve the declared finite frontier and emit exact replay material."""

    if maximum_denominator < 1:
        raise ValueError("maximum_denominator must be positive")
    beta = _fraction(problem.liveness_failure_budget)
    target = 1 - beta
    dual: ProtocolDualCertificate | None = None
    deterministic_protocols_checked: int | None = None
    if problem.authorization_mode is AuthorizationMode.DETERMINISTIC:
        primal, deterministic_protocols_checked = _deterministic_protocol(
            problem,
            maximum_protocols=maximum_deterministic_protocols,
        )
        upper = _fraction(primal.minimum_liveness)
        solver = "exact_deterministic_enumeration"
    else:
        primal, dual = _randomized_protocol(
            problem,
            maximum_denominator=maximum_denominator,
        )
        upper = min(Fraction(1), _fraction(dual.objective_upper))
        solver = "scipy_highs_with_exact_rational_primal_and_dual_replay"
    lower = _fraction(primal.minimum_liveness)
    if lower >= target:
        status = "target_met"
    elif upper < target:
        status = "target_impossible"
    else:
        status = "numerically_unresolved"
    certificate = ProtocolFeasibilityCertificate(
        certificate_id=certificate_id,
        problem=problem,
        problem_sha256=protocol_problem_sha256(problem),
        solver=solver,
        status=status,
        target_liveness=_rational(target),
        primal=primal,
        dual=dual,
        deterministic_protocols_checked=deterministic_protocols_checked,
    )
    verification = verify_protocol_feasibility(certificate)
    if not verification.valid:
        raise RuntimeError(
            "generated protocol certificate failed exact replay: "
            + "; ".join(verification.reasons)
        )
    return certificate


def _certificate_kernel(
    certificate: ProtocolFeasibilityCertificate,
) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(
        tuple(_fraction(value) for value in row.action_probabilities)
        for row in certificate.primal.kernel_rows
    )


def _verify_dual(
    problem: ProtocolFeasibilityProblem,
    dual: ProtocolDualCertificate,
) -> tuple[Fraction, list[str]]:
    reasons: list[str] = []
    evidence_ids, action_ids, world_ids, probabilities, acceptable = _problem_tables(problem)
    feasible_indices = tuple(
        index for index, world in enumerate(problem.worlds)
        if world.acceptable_configuration_ids
    )
    expected_feasible = tuple(problem.worlds[index].world_id for index in feasible_indices)
    if dual.feasible_world_ids != expected_feasible:
        reasons.append("dual feasible-world order does not match the problem")
    if dual.world_ids != world_ids or dual.evidence_ids != evidence_ids:
        reasons.append("dual world or evidence order does not match the problem")
    y = tuple(_fraction(value) for value in dual.liveness_multipliers)
    z = tuple(_fraction(value) for value in dual.unsafe_multipliers)
    q = tuple(_fraction(value) for value in dual.simplex_multipliers)
    if len(y) != len(feasible_indices) or len(z) != len(world_ids) or len(q) != len(evidence_ids):
        reasons.append("dual multiplier dimensions do not match the problem")
        return Fraction(), reasons
    if sum(y, Fraction()) < 1:
        reasons.append("dual liveness multipliers sum to less than one")
    for evidence_index in range(len(evidence_ids)):
        for action_id in action_ids:
            lhs = q[evidence_index]
            for world_index in range(len(world_ids)):
                if (
                    action_id != REFUSAL_ACTION_ID
                    and action_id not in acceptable[world_index]
                ):
                    lhs += z[world_index] * probabilities[world_index][evidence_index]
            for y_index, world_index in enumerate(feasible_indices):
                if action_id in acceptable[world_index]:
                    lhs -= y[y_index] * probabilities[world_index][evidence_index]
            if lhs < 0:
                reasons.append(
                    f"dual constraint fails for evidence {evidence_ids[evidence_index]} "
                    f"and action {action_id}"
                )
    objective = sum(q, Fraction()) + _fraction(problem.unsafe_release_budget) * sum(
        z, Fraction()
    )
    if objective != _fraction(dual.objective_upper):
        reasons.append("dual objective does not replay exactly")
    return min(Fraction(1), objective), reasons


def verify_protocol_feasibility(
    certificate: ProtocolFeasibilityCertificate,
    *,
    maximum_deterministic_protocols: int = MAX_DETERMINISTIC_PROTOCOLS,
    expected_problem_sha256: str | None = None,
) -> ProtocolCertificateVerification:
    """Replay every certificate condition using exact rational arithmetic."""

    problem = certificate.problem
    reasons: list[str] = []
    if certificate.problem_sha256 != protocol_problem_sha256(problem):
        reasons.append("certificate is bound to another protocol problem")
    if (
        expected_problem_sha256 is not None
        and certificate.problem_sha256 != expected_problem_sha256
    ):
        reasons.append("certificate does not match the externally supplied protocol problem")
    evidence_ids, action_ids, _, _, _ = _problem_tables(problem)
    if certificate.primal.action_ids != action_ids:
        reasons.append("primal action order does not match the problem")
    if tuple(row.evidence_id for row in certificate.primal.kernel_rows) != evidence_ids:
        reasons.append("primal evidence order does not match the problem")
    try:
        kernel = _certificate_kernel(certificate)
        unsafe, liveness, lower = _evaluate_kernel(problem, kernel)
    except ValueError as exc:
        reasons.append(str(exc))
        unsafe = ()
        liveness = ()
        lower = Fraction()
    if unsafe and tuple(_fraction(value) for value in certificate.primal.unsafe_by_world) != unsafe:
        reasons.append("primal unsafe-release values do not replay")
    if liveness and (
        tuple(_fraction(value) for value in certificate.primal.liveness_by_feasible_world)
        != liveness
    ):
        reasons.append("primal liveness values do not replay")
    if lower != _fraction(certificate.primal.minimum_liveness):
        reasons.append("primal minimum liveness does not replay")
    if unsafe and max(unsafe) > _fraction(problem.unsafe_release_budget):
        reasons.append("primal kernel exceeds the unsafe-release budget")

    if problem.authorization_mode is AuthorizationMode.DETERMINISTIC:
        try:
            exact_primal, count = _deterministic_protocol(
                problem,
                maximum_protocols=maximum_deterministic_protocols,
            )
            upper = _fraction(exact_primal.minimum_liveness)
            if certificate.deterministic_protocols_checked != count:
                reasons.append("deterministic enumeration count does not replay")
            if lower != upper:
                reasons.append("stored deterministic protocol is not frontier-optimal")
            if certificate.dual is not None:
                reasons.append("deterministic certificate must not contain an LP dual")
        except RuntimeError as exc:
            reasons.append(str(exc))
            upper = Fraction(1)
    else:
        if certificate.dual is None:
            reasons.append("randomized certificate is missing its dual")
            upper = Fraction(1)
        else:
            upper, dual_reasons = _verify_dual(problem, certificate.dual)
            reasons.extend(dual_reasons)
        if certificate.deterministic_protocols_checked is not None:
            reasons.append("randomized certificate must not declare deterministic enumeration")
    if lower > upper:
        reasons.append("primal lower bound exceeds dual or exact upper bound")

    target = 1 - _fraction(problem.liveness_failure_budget)
    if _fraction(certificate.target_liveness) != target:
        reasons.append("target liveness does not replay")
    if lower >= target:
        expected_status = "target_met"
    elif upper < target:
        expected_status = "target_impossible"
    else:
        expected_status = "numerically_unresolved"
    if certificate.status != expected_status:
        reasons.append("certificate status does not follow from its exact bounds")
    return ProtocolCertificateVerification(
        valid=not reasons,
        status=expected_status,
        exact_lower_numerator=lower.numerator,
        exact_lower_denominator=lower.denominator,
        exact_upper_numerator=upper.numerator,
        exact_upper_denominator=upper.denominator,
        reasons=tuple(reasons),
    )


def robustly_releasable_configurations(
    compatible_worlds: Iterable[str],
    configuration_ids: Iterable[str],
    acceptable_pairs: Iterable[tuple[str, str]],
) -> tuple[str, ...]:
    """Return configurations acceptable in every compatible world.

    ``acceptable_pairs`` contains ``(configuration_id, world_id)`` pairs for
    which *all* mandatory release conditions hold.  Refusal is intentionally
    not represented as a configuration.
    """

    worlds = tuple(dict.fromkeys(compatible_worlds))
    configurations = tuple(dict.fromkeys(configuration_ids))
    if not worlds:
        raise ValueError("an accepted evidence cell must contain at least one compatible world")
    if not configurations:
        return ()
    accepted = frozenset(acceptable_pairs)
    unknown = {
        pair
        for pair in accepted
        if pair[0] not in configurations or pair[1] not in worlds
    }
    if unknown:
        raise ValueError(f"acceptability matrix contains out-of-domain pairs: {sorted(unknown)}")
    return tuple(
        configuration_id
        for configuration_id in configurations
        if all((configuration_id, world_id) in accepted for world_id in worlds)
    )


def maximal_sound_gate(
    evidence_cells: Mapping[str, Iterable[str]],
    configuration_ids: Iterable[str],
    acceptable_pairs: Iterable[tuple[str, str]],
) -> dict[str, tuple[str, ...]]:
    """Construct the pointwise-largest exact-sound authorization correspondence.

    Each value is the complete set of configurations that any exact-sound gate
    is allowed to release after observing that evidence identifier.  An empty
    tuple means that refusal or an inconclusive result is mandatory.
    """

    configurations = tuple(configuration_ids)
    accepted = tuple(acceptable_pairs)
    result: dict[str, tuple[str, ...]] = {}
    for evidence_id, world_values in evidence_cells.items():
        worlds = tuple(world_values)
        world_set = set(worlds)
        result[evidence_id] = robustly_releasable_configurations(
            worlds,
            configurations,
            (pair for pair in accepted if pair[1] in world_set),
        )
    return result


def assurance_failure_upper_bound(
    coverage_failures: Iterable[Fraction | int | float | str],
    realization_failures: Iterable[Fraction | int | float | str] = (),
) -> Fraction:
    """Return the union-bound ceiling for one or several release decisions.

    Every supplied term must be the probability of a failure event in one declared
    end-to-end experiment. Coverage terms may represent failures of statistical
    ambiguity sets. ``realization_failures`` may contain only separately justified
    event probabilities in that same experiment; a cryptographic distinguishing
    advantage or an informal numerical tolerance is not automatically such a term.
    No independence assumption is made.
    """

    terms = tuple(Fraction(value) for value in (*coverage_failures, *realization_failures))
    if any(value < 0 or value > 1 for value in terms):
        raise ValueError("failure probabilities must lie in [0, 1]")
    return min(Fraction(1), sum(terms, start=Fraction(0)))
