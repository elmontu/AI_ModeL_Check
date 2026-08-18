from __future__ import annotations

import itertools
import json
import math
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .decision_theory import DecisionProblem, FiniteExperiment, decision_value
from .integrity import canonical_json_bytes, sha256_bytes, verify_source_file
from .models import StrictModel


MAX_EXPLICIT_JOINT_CELLS = 100_000
MAX_EXACT_DECODERS = 100_000
MAX_RATIONAL_LINEAR_MECHANISM_CELLS = 64
MIN_CLEARANCE_COVERAGE_CONFIDENCE = 0.95


class StatisticalCoverage(StrEnum):
    """How the channel bounds cover the data-dependent assurance search."""

    DETERMINISTIC = "deterministic"
    SIMULTANEOUS = "simultaneous"
    ANYTIME_VALID = "anytime_valid"
    POINTWISE = "pointwise"


class CouplingModel(StrEnum):
    """Declared relationship between release randomizers conditional on the secret."""

    ARBITRARY = "arbitrary"
    LINEAR_MECHANISM = "linear_mechanism"
    CONDITIONAL_INDEPENDENCE = "conditional_independence"


class ConditionalMarginalBounds(StrictModel):
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    observation_ids: tuple[str, ...] = Field(min_length=1)
    lower: tuple[tuple[float, ...], ...] = Field(min_length=2)
    upper: tuple[tuple[float, ...], ...] = Field(min_length=2)
    evidence: EvidenceReference

    @model_validator(mode="after")
    def bounds_are_valid(self) -> ConditionalMarginalBounds:
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("marginal observation identifiers must be unique")
        if len(self.lower) != len(self.upper):
            raise ValueError("marginal lower and upper bounds must have the same state rows")
        width = len(self.observation_ids)
        for lower_row, upper_row in zip(self.lower, self.upper, strict=True):
            if len(lower_row) != width or len(upper_row) != width:
                raise ValueError("marginal bounds must align with observation identifiers")
            if any(value < 0.0 or value > 1.0 for value in (*lower_row, *upper_row)):
                raise ValueError("marginal probabilities must lie in [0,1]")
            if any(lower > upper for lower, upper in zip(lower_row, upper_row, strict=True)):
                raise ValueError("every marginal lower bound must be at most its upper bound")
            if sum(lower_row) > 1.0 + 1e-10 or sum(upper_row) < 1.0 - 1e-10:
                raise ValueError("each marginal interval row must contain a probability vector")
        return self


class JointEventBound(StrictModel):
    """A mechanism-derived linear bound on a set of joint transcripts in one state."""

    event_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    state_id: str = Field(min_length=1, max_length=256)
    transcripts: tuple[tuple[str, ...], ...] = Field(min_length=1)
    lower: float = Field(default=0.0, ge=0.0, le=1.0)
    upper: float = Field(default=1.0, ge=0.0, le=1.0)
    justification: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def event_is_valid(self) -> JointEventBound:
        if self.lower > self.upper:
            raise ValueError("joint-event lower bound must not exceed its upper bound")
        if len(set(self.transcripts)) != len(self.transcripts):
            raise ValueError("joint-event transcripts must be unique")
        return self


class EvidenceReference(StrictModel):
    evidence_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supports: tuple[str, ...] = Field(min_length=1)


class IncompletePortfolioProblem(StrictModel):
    """Finite ambiguity set built from observable marginals and mechanism constraints."""

    schema_version: Literal["1.0"] = "1.0"
    portfolio_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    decision_game_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_ids: tuple[str, ...] = Field(min_length=2)
    prior: tuple[float, ...]
    releases: tuple[ConditionalMarginalBounds, ...] = Field(min_length=1)
    decision_problem: DecisionProblem
    coupling_model: CouplingModel
    joint_event_bounds: tuple[JointEventBound, ...] = ()
    coverage: StatisticalCoverage
    coverage_confidence: float = Field(gt=0.0, le=1.0)
    selection_scope: str = Field(min_length=1, max_length=4096)
    prior_evidence: EvidenceReference
    mechanism_assumptions: tuple[str, ...] = Field(min_length=1)
    mechanism_evidence: tuple[EvidenceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def problem_is_valid(self) -> IncompletePortfolioProblem:
        if len(set(self.state_ids)) != len(self.state_ids):
            raise ValueError("portfolio state identifiers must be unique")
        if self.decision_problem.state_ids != self.state_ids:
            raise ValueError("portfolio and decision problem must use the same ordered state space")
        if len(self.prior) != len(self.state_ids):
            raise ValueError("portfolio prior must align with states")
        if any(value < 0.0 or value > 1.0 for value in self.prior):
            raise ValueError("portfolio prior probabilities must lie in [0,1]")
        if abs(sum(self.prior) - 1.0) > 1e-10:
            raise ValueError("portfolio prior must sum to one")
        if len({release.release_id for release in self.releases}) != len(self.releases):
            raise ValueError("portfolio release identifiers must be unique")
        joint_cell_count = 1
        for release in self.releases:
            joint_cell_count *= len(release.observation_ids)
            if joint_cell_count > MAX_EXPLICIT_JOINT_CELLS:
                raise ValueError(
                    f"explicit joint alphabet exceeds the hard limit of {MAX_EXPLICIT_JOINT_CELLS} cells"
                )
        evidence_references = (
            self.prior_evidence,
            *(release.evidence for release in self.releases),
            *self.mechanism_evidence,
        )
        if len({value.evidence_id for value in evidence_references}) != len(evidence_references):
            raise ValueError("assurance-evidence identifiers must be unique")
        if "prior" not in self.prior_evidence.supports:
            raise ValueError("prior evidence must support the numerical prior")
        coverage_claim = f"coverage:{self.coverage.value}"
        for release in self.releases:
            required = {f"marginal:{release.release_id}", coverage_claim}
            if not required.issubset(set(release.evidence.supports)):
                raise ValueError(
                    f"marginal evidence for {release.release_id} does not support "
                    f"{sorted(required - set(release.evidence.supports))}"
                )
        supported_claims = {
            claim for evidence in self.mechanism_evidence for claim in evidence.supports
        }
        required_claims = {f"coupling:{self.coupling_model.value}"}
        required_claims.update(event.event_id for event in self.joint_event_bounds)
        if not required_claims.issubset(supported_claims):
            raise ValueError(
                "mechanism evidence does not support every coupling and joint-event claim: "
                f"{sorted(required_claims - supported_claims)}"
            )
        if any(len(release.lower) != len(self.state_ids) for release in self.releases):
            raise ValueError("every marginal release must contain one row per portfolio state")
        if self.coverage is StatisticalCoverage.DETERMINISTIC and self.coverage_confidence != 1.0:
            raise ValueError("deterministic bounds must declare coverage_confidence=1")
        if (
            self.coverage is not StatisticalCoverage.DETERMINISTIC
            and self.coverage_confidence < MIN_CLEARANCE_COVERAGE_CONFIDENCE
        ):
            raise ValueError(
                "statistical portfolio evidence must meet the 0.95 clearance-confidence floor"
            )
        if self.coupling_model is not CouplingModel.LINEAR_MECHANISM and self.joint_event_bounds:
            raise ValueError("joint-event bounds require the linear_mechanism coupling model")

        state_set = set(self.state_ids)
        width = len(self.releases)
        valid_transcripts = set(itertools.product(*(release.observation_ids for release in self.releases)))
        for bound in self.joint_event_bounds:
            if bound.state_id not in state_set:
                raise ValueError(f"unknown joint-event state: {bound.state_id}")
            if any(len(transcript) != width for transcript in bound.transcripts):
                raise ValueError("joint-event transcripts must have one component per release")
            if any(transcript not in valid_transcripts for transcript in bound.transcripts):
                raise ValueError("joint-event transcript contains an unknown release observation")
        return self

    @property
    def selection_valid(self) -> bool:
        return (
            self.coverage is not StatisticalCoverage.POINTWISE
            and self.coverage_confidence >= MIN_CLEARANCE_COVERAGE_CONFIDENCE
        )


class StateDualCertificate(StrictModel):
    state_id: str
    inequality_multipliers: tuple[float, ...]
    normalization_multiplier: float
    raw_dual_objective: float
    maximum_constraint_shortfall: float = Field(ge=0.0)
    objective_bound: float


class DecoderUpperCertificate(StrictModel):
    action_indices: tuple[int, ...]
    state_duals: tuple[StateDualCertificate, ...]
    upper_bound: float


class ExactPortfolioCertificate(StrictModel):
    certificate_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    joint_observation_ids: tuple[str, ...]
    decoder_count: int = Field(gt=0)
    decoder_certificates: tuple[DecoderUpperCertificate, ...]
    upper_bound: float = Field(ge=0.0)
    lower_bound: float = Field(ge=0.0, le=1.0)
    winning_joint_channel: tuple[tuple[float, ...], ...]
    optimality_gap: float = Field(ge=0.0)
    numerical_tolerance: float = Field(default=1e-8, gt=0.0, le=1e-5)
    solver: str = Field(min_length=1, max_length=512)
    selection_valid: bool
    coverage_confidence: float = Field(gt=0.0, le=1.0)


class EnvelopePortfolioCertificate(StrictModel):
    certificate_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    joint_observation_ids: tuple[str, ...]
    cell_upper_bounds: tuple[tuple[float, ...], ...]
    feasible_joint_channel: tuple[tuple[float, ...], ...]
    raw_upper_bound: float = Field(ge=0.0)
    upper_bound: float = Field(ge=0.0, le=1.0)
    derivation: str
    selection_valid: bool
    coverage_confidence: float = Field(gt=0.0, le=1.0)


class CertificateVerification(StrictModel):
    valid: bool
    upper_bound: float = Field(ge=0.0)
    lower_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_upper_numerator: int | None = Field(default=None, ge=0)
    exact_upper_denominator: int | None = Field(default=None, gt=0)
    rationally_replayed: bool = False
    outward_rounded: bool = False
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def rational_result_is_complete(self) -> CertificateVerification:
        has_fraction = (
            self.exact_upper_numerator is not None
            and self.exact_upper_denominator is not None
        )
        if self.rationally_replayed != has_fraction:
            raise ValueError("rational replay requires a complete exact upper fraction")
        if self.outward_rounded and not self.rationally_replayed:
            raise ValueError("outward rounding requires rational replay")
        return self


class RationalNumber(StrictModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def canonical_fraction(self) -> RationalNumber:
        if math.gcd(abs(self.numerator), self.denominator) != 1:
            raise ValueError("rational numbers must be stored in lowest terms")
        return self


class RationalUpperAudit(StrictModel):
    audit_version: Literal["1.0"] = "1.0"
    certificate_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    certificate_kind: Literal["exact_dual", "envelope"]
    problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exact_upper_numerator: int = Field(ge=0)
    exact_upper_denominator: int = Field(gt=0)
    outward_upper_bound: float = Field(ge=0.0, le=1.0)
    feasible_joint_channel: tuple[tuple[RationalNumber, ...], ...]
    number_interpretation: Literal[
        "exact_decimal_weights_normalized_per_probability_vector"
    ] = (
        "exact_decimal_weights_normalized_per_probability_vector"
    )

    @model_validator(mode="after")
    def exact_upper_is_canonical(self) -> RationalUpperAudit:
        if math.gcd(self.exact_upper_numerator, self.exact_upper_denominator) != 1:
            raise ValueError("exact rational upper bound must be stored in lowest terms")
        return self


class AnalyticPortfolioEvidenceEntry(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    problem: IncompletePortfolioProblem
    exact_certificate: ExactPortfolioCertificate | None = None
    envelope_certificate: EnvelopePortfolioCertificate | None = None
    rational_upper_audit: RationalUpperAudit

    @model_validator(mode="after")
    def exactly_one_certificate(self) -> AnalyticPortfolioEvidenceEntry:
        if (self.exact_certificate is None) == (self.envelope_certificate is None):
            raise ValueError("analytic portfolio evidence requires exactly one certificate")
        certificate = self.exact_certificate or self.envelope_certificate
        assert certificate is not None
        expected_kind = "exact_dual" if self.exact_certificate is not None else "envelope"
        if self.rational_upper_audit.certificate_id != certificate.certificate_id:
            raise ValueError("rational audit is bound to another certificate")
        if self.rational_upper_audit.certificate_kind != expected_kind:
            raise ValueError("rational audit declares the wrong certificate kind")
        if self.rational_upper_audit.problem_sha256 != portfolio_problem_sha256(self.problem):
            raise ValueError("rational audit is bound to another portfolio problem")
        return self


def portfolio_problem_sha256(problem: IncompletePortfolioProblem) -> str:
    return sha256_bytes(canonical_json_bytes(problem))


def _fraction(value: float | int) -> Fraction:
    """Interpret a canonical JSON number as its exact decimal-text rational value."""
    if isinstance(value, int):
        return Fraction(value)
    return Fraction(Decimal(str(value)))


def _outward_float(value: Fraction) -> float:
    """Smallest binary64 value greater than or equal to an exact non-negative rational."""
    candidate = float(value)
    if Fraction.from_float(candidate) < value:
        candidate = math.nextafter(candidate, math.inf)
    return min(1.0, max(0.0, candidate))


def _clipped_unit(value: Fraction) -> Fraction:
    return min(Fraction(1), max(Fraction(0), value))


def _normalized_fraction_weights(values: tuple[float, ...]) -> tuple[Fraction, ...]:
    weights = tuple(_fraction(value) for value in values)
    total = sum(weights, Fraction(0))
    if total <= 0:
        raise ValueError("probability weights must have positive total mass")
    return tuple(value / total for value in weights)


def _rational_prior(problem: IncompletePortfolioProblem) -> tuple[Fraction, ...]:
    return _normalized_fraction_weights(problem.prior)


def _rational_marginal_bounds(
    release: ConditionalMarginalBounds,
    state_index: int,
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    lower_raw = release.lower[state_index]
    upper_raw = release.upper[state_index]
    if lower_raw == upper_raw:
        point = _normalized_fraction_weights(lower_raw)
        return point, point
    return (
        tuple(_fraction(value) for value in lower_raw),
        tuple(_fraction(value) for value in upper_raw),
    )


def _effective_marginal_bounds(
    release: ConditionalMarginalBounds,
    state_index: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    lower = release.lower[state_index]
    upper = release.upper[state_index]
    if lower == upper:
        total = sum(lower)
        point = tuple(value / total for value in lower)
        return point, point
    return lower, upper


def _rational_envelope_upper(
    problem: IncompletePortfolioProblem,
) -> Fraction:
    transcripts = joint_transcripts(problem)
    prior = _rational_prior(problem)
    cell_bounds: list[list[Fraction]] = []
    for state_index, state_id in enumerate(problem.state_ids):
        state_bounds: list[Fraction] = []
        for transcript in transcripts:
            components = []
            for release_index, release in enumerate(problem.releases):
                _, upper = _rational_marginal_bounds(release, state_index)
                components.append(
                    upper[release.observation_ids.index(transcript[release_index])]
                )
            upper = (
                math.prod(components)
                if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE
                else min(components)
            )
            for event in problem.joint_event_bounds:
                if event.state_id == state_id and transcript in event.transcripts:
                    upper = min(upper, _fraction(event.upper))
            state_bounds.append(_clipped_unit(upper))
        cell_bounds.append(state_bounds)
    raw = Fraction(0)
    for observation_index in range(len(transcripts)):
        raw += max(
            sum(
                prior[state_index]
                * cell_bounds[state_index][observation_index]
                * _fraction(problem.decision_problem.gain[state_index][action_index])
                for state_index in range(len(problem.state_ids))
            )
            for action_index in range(len(problem.decision_problem.action_ids))
        )
    return _clipped_unit(raw)


def _rational_exact_upper(
    problem: IncompletePortfolioProblem,
    certificate: ExactPortfolioCertificate,
) -> Fraction:
    transcripts = joint_transcripts(problem)
    action_count = len(problem.decision_problem.action_ids)
    expected_decoders = tuple(itertools.product(range(action_count), repeat=len(transcripts)))
    supplied = tuple(value.action_indices for value in certificate.decoder_certificates)
    if supplied != expected_decoders:
        raise ValueError("rational replay requires the canonical exhaustive decoder cover")
    prior = _rational_prior(problem)
    decoder_bounds: list[Fraction] = []
    for decoder_certificate in certificate.decoder_certificates:
        if len(decoder_certificate.state_duals) != len(problem.state_ids):
            raise ValueError("rational replay found the wrong number of state duals")
        decoder_bound = Fraction(0)
        for state_index, dual in enumerate(decoder_certificate.state_duals):
            rows, bounds = _rational_state_constraints(problem, state_index)
            if dual.state_id != problem.state_ids[state_index]:
                raise ValueError("rational replay found a state dual identifier mismatch")
            if len(dual.inequality_multipliers) != len(bounds):
                raise ValueError("rational replay found the wrong dual dimension")
            multipliers = tuple(_fraction(value) for value in dual.inequality_multipliers)
            if any(value < 0 for value in multipliers):
                raise ValueError("rational replay found a negative inequality multiplier")
            normalization = _fraction(dual.normalization_multiplier)
            shortfall = max(
                Fraction(0),
                *(
                    _fraction(problem.decision_problem.gain[state_index][
                        decoder_certificate.action_indices[observation_index]
                    ])
                    - normalization
                    - sum(
                        rows[row_index][observation_index] * multipliers[row_index]
                        for row_index in range(len(rows))
                    )
                    for observation_index in range(len(transcripts))
                ),
            )
            raw_objective = normalization + sum(
                bound * multiplier
                for bound, multiplier in zip(bounds, multipliers, strict=True)
            )
            decoder_bound += prior[state_index] * (
                raw_objective + shortfall
            )
        decoder_bounds.append(decoder_bound)
    return _clipped_unit(max(Fraction(0), *decoder_bounds))


def _rational_number(value: Fraction) -> RationalNumber:
    return RationalNumber(numerator=value.numerator, denominator=value.denominator)


def _validate_rational_probability_contract(problem: IncompletePortfolioProblem) -> None:
    """Check exact normalized semantics for every serialized probability object."""
    _rational_prior(problem)
    for release in problem.releases:
        for state_index in range(len(problem.state_ids)):
            lower, upper = _rational_marginal_bounds(release, state_index)
            lower_total = sum(lower, Fraction(0))
            upper_total = sum(upper, Fraction(0))
            if lower_total > 1 or upper_total < 1:
                raise ValueError(
                    "rational replay found a marginal interval row that does not contain "
                    "an exactly normalized probability vector"
                )


def _rational_interval_point(
    lower: tuple[Fraction, ...],
    upper: tuple[Fraction, ...],
) -> tuple[Fraction, ...]:
    row = list(lower)
    remaining = Fraction(1) - sum(row)
    if remaining < 0:
        raise ValueError("rational marginal lower bounds exceed one")
    for index, upper_value in enumerate(upper):
        addition = min(remaining, upper_value - row[index])
        row[index] += addition
        remaining -= addition
    if remaining != 0:
        raise ValueError("rational marginal intervals do not contain a probability vector")
    return tuple(row)


def _rational_affine_projection(
    equations: list[list[Fraction]],
    targets: list[Fraction],
    seed: tuple[Fraction, ...],
) -> tuple[Fraction, ...] | None:
    """Solve exact affine equations, retaining seed values for free coordinates."""
    width = len(seed)
    matrix = [row[:] + [target] for row, target in zip(equations, targets, strict=True)]
    pivot_columns: list[int] = []
    pivot_row = 0
    for column in range(width):
        selected = next(
            (index for index in range(pivot_row, len(matrix)) if matrix[index][column]),
            None,
        )
        if selected is None:
            continue
        matrix[pivot_row], matrix[selected] = matrix[selected], matrix[pivot_row]
        pivot = matrix[pivot_row][column]
        matrix[pivot_row] = [value / pivot for value in matrix[pivot_row]]
        for row_index in range(len(matrix)):
            if row_index == pivot_row:
                continue
            factor = matrix[row_index][column]
            if factor:
                matrix[row_index] = [
                    left - factor * right
                    for left, right in zip(matrix[row_index], matrix[pivot_row], strict=True)
                ]
        pivot_columns.append(column)
        pivot_row += 1
        if pivot_row == len(matrix):
            break
    if any(all(value == 0 for value in row[:-1]) and row[-1] != 0 for row in matrix):
        return None
    result = list(seed)
    for row_index in range(len(pivot_columns) - 1, -1, -1):
        column = pivot_columns[row_index]
        row = matrix[row_index]
        result[column] = row[-1] - sum(
            row[index] * result[index]
            for index in range(width)
            if index != column
        )
    return tuple(result)


def _rationalize_linear_witness(
    problem: IncompletePortfolioProblem,
    state_index: int,
    witness: tuple[float, ...],
) -> tuple[Fraction, ...]:
    """Reconstruct a nearby exact rational point from an LP feasibility witness."""
    width = len(witness)
    seed = tuple(_fraction(value) for value in witness)
    constraints, bounds = _rational_state_constraints(problem, state_index)
    normalization = [Fraction(1)] * width
    residuals = [
        abs(sum(
            coefficient * value
            for coefficient, value in zip(constraint, seed, strict=True)
        ) - bound)
        for constraint, bound in zip(constraints, bounds, strict=True)
    ]
    for active_tolerance in (
        Fraction(1, 10**12),
        Fraction(1, 10**10),
        Fraction(1, 10**8),
        Fraction(1, 10**7),
    ):
        equations = [normalization]
        targets = [Fraction(1)]
        for constraint, bound, residual in zip(
            constraints, bounds, residuals, strict=True
        ):
            if residual <= active_tolerance:
                equations.append(constraint[:])
                targets.append(bound)
        for index, value in enumerate(seed):
            if value <= active_tolerance:
                unit = [Fraction(0)] * width
                unit[index] = Fraction(1)
                equations.append(unit)
                targets.append(Fraction(0))
        candidate = _rational_affine_projection(equations, targets, seed)
        if candidate is None or any(value < 0 for value in candidate):
            continue
        if all(
            sum(
                coefficient * value
                for coefficient, value in zip(constraint, candidate, strict=True)
            ) <= bound
            for constraint, bound in zip(constraints, bounds, strict=True)
        ):
            return candidate
    raise ValueError("could not reconstruct an exact rational linear-mechanism witness")


def _rational_feasible_channel(
    problem: IncompletePortfolioProblem,
    certificate: ExactPortfolioCertificate | EnvelopePortfolioCertificate,
) -> tuple[tuple[RationalNumber, ...], ...]:
    """Construct an exact ambiguity-set witness without trusting LP feasibility tolerances."""
    transcripts = joint_transcripts(problem)
    rows: list[tuple[Fraction, ...]] = []
    if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE:
        for state_index in range(len(problem.state_ids)):
            marginal_points = []
            for release in problem.releases:
                lower, upper = _rational_marginal_bounds(release, state_index)
                marginal_points.append(_rational_interval_point(lower, upper))
            row = []
            for transcript in transcripts:
                probability = Fraction(1)
                for release_index, release in enumerate(problem.releases):
                    probability *= marginal_points[release_index][
                        release.observation_ids.index(transcript[release_index])
                    ]
                row.append(probability)
            rows.append(tuple(row))
    elif problem.coupling_model is CouplingModel.ARBITRARY:
        # Comonotone quantile coupling: divide [0,1] by all marginal cumulative
        # breakpoints and map every segment to its release outcome tuple.
        for state_index in range(len(problem.state_ids)):
            breakpoints = {Fraction(0), Fraction(1)}
            cumulatives: list[tuple[Fraction, ...]] = []
            for release in problem.releases:
                total = Fraction(0)
                boundaries = [Fraction(0)]
                lower, upper = _rational_marginal_bounds(release, state_index)
                marginal_point = _rational_interval_point(lower, upper)
                for probability in marginal_point:
                    total += probability
                    boundaries.append(total)
                if total != 1:
                    raise ValueError("point marginal does not sum exactly to one")
                cumulatives.append(tuple(boundaries))
                breakpoints.update(boundaries)
            row_by_transcript = {transcript: Fraction(0) for transcript in transcripts}
            ordered = sorted(breakpoints)
            for left, right in zip(ordered, ordered[1:]):
                if right == left:
                    continue
                midpoint = (left + right) / 2
                transcript = tuple(
                    release.observation_ids[next(
                        index
                        for index in range(len(release.observation_ids))
                        if cumulatives[release_index][index]
                        <= midpoint
                        < cumulatives[release_index][index + 1]
                    )]
                    for release_index, release in enumerate(problem.releases)
                )
                row_by_transcript[transcript] += right - left
            rows.append(tuple(row_by_transcript[value] for value in transcripts))
    else:
        # Rationalize the solver witness and verify it exactly below. This is safe
        # for the implemented linear mechanism language when the decimal witness
        # is an exact feasible point; otherwise clearance is refused.
        if len(transcripts) > MAX_RATIONAL_LINEAR_MECHANISM_CELLS:
            raise ValueError(
                "rational linear-mechanism witness exceeds the supported cell limit"
            )
        witness = (
            certificate.winning_joint_channel
            if isinstance(certificate, ExactPortfolioCertificate)
            else certificate.feasible_joint_channel
        )
        rows = [
            _rationalize_linear_witness(problem, state_index, row)
            for state_index, row in enumerate(witness)
        ]

    if len(rows) != len(problem.state_ids):
        raise ValueError("rational feasible witness has the wrong state dimension")
    for state_index, row in enumerate(rows):
        if len(row) != len(transcripts) or any(value < 0 for value in row):
            raise ValueError("rational feasible witness has an invalid row")
        if sum(row) != 1:
            raise ValueError("rational feasible witness row does not sum exactly to one")
        constraints, bounds = _rational_state_constraints(problem, state_index)
        for constraint, bound in zip(constraints, bounds, strict=True):
            lhs = sum(
                coefficient * value
                for coefficient, value in zip(constraint, row, strict=True)
            )
            if lhs > bound:
                raise ValueError("rational feasible witness violates the ambiguity set")
        if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE:
            marginals: list[list[Fraction]] = []
            for release_index, release in enumerate(problem.releases):
                marginals.append([
                    sum(
                        row[cell_index]
                        for cell_index, transcript in enumerate(transcripts)
                        if transcript[release_index] == observation
                    )
                    for observation in release.observation_ids
                ])
            for cell_index, transcript in enumerate(transcripts):
                product = math.prod(
                    marginals[release_index][
                        release.observation_ids.index(transcript[release_index])
                    ]
                    for release_index, release in enumerate(problem.releases)
                )
                if row[cell_index] != product:
                    raise ValueError("rational feasible witness violates conditional independence")
    return tuple(tuple(_rational_number(value) for value in row) for row in rows)


def build_rational_upper_audit(
    problem: IncompletePortfolioProblem,
    certificate: ExactPortfolioCertificate | EnvelopePortfolioCertificate,
) -> RationalUpperAudit:
    _validate_rational_probability_contract(problem)
    exact = (
        _rational_exact_upper(problem, certificate)
        if isinstance(certificate, ExactPortfolioCertificate)
        else _rational_envelope_upper(problem)
    )
    return RationalUpperAudit(
        certificate_id=certificate.certificate_id,
        certificate_kind=(
            "exact_dual" if isinstance(certificate, ExactPortfolioCertificate) else "envelope"
        ),
        problem_sha256=portfolio_problem_sha256(problem),
        exact_upper_numerator=exact.numerator,
        exact_upper_denominator=exact.denominator,
        outward_upper_bound=_outward_float(exact),
        feasible_joint_channel=_rational_feasible_channel(problem, certificate),
    )


def portfolio_evidence_references(
    problem: IncompletePortfolioProblem,
) -> tuple[EvidenceReference, ...]:
    return (
        problem.prior_evidence,
        *(release.evidence for release in problem.releases),
        *problem.mechanism_evidence,
    )


def verify_portfolio_problem_evidence(
    problem: IncompletePortfolioProblem,
    base_dir: Path,
) -> tuple[Path, ...]:
    """Verify every marginal, prior, and mechanism evidence file bound to a problem."""
    paths = tuple(
        verify_source_file(reference.source_path, reference.source_sha256, base_dir)
        for reference in portfolio_evidence_references(problem)
    )
    statistical_sources: dict[Path, EvidenceReference] = {}
    for release in problem.releases:
        if any(value.startswith("error-budget:") for value in release.evidence.supports):
            path = verify_source_file(
                release.evidence.source_path,
                release.evidence.source_sha256,
                base_dir,
            )
            statistical_sources[path] = release.evidence
    for path in statistical_sources:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"statistical marginal evidence is not valid UTF-8 JSON: {path}") from exc
        if payload.get("evidence_type") != "simultaneous_multinomial_marginals":
            raise ValueError("error-budgeted marginal evidence has an unsupported evidence type")
        # Lazy import avoids a module cycle: the statistical compiler consumes the
        # portfolio contract, while this verifier recognizes its evidence subtype.
        from .portfolio_statistics import (
            SimultaneousMultinomialEvidence,
            verify_problem_against_multinomial_evidence,
        )

        evidence = SimultaneousMultinomialEvidence.model_validate(payload)
        verify_problem_against_multinomial_evidence(problem, evidence, path)
    return paths


def joint_transcripts(problem: IncompletePortfolioProblem) -> tuple[tuple[str, ...], ...]:
    return tuple(itertools.product(*(release.observation_ids for release in problem.releases)))


def joint_observation_ids(problem: IncompletePortfolioProblem) -> tuple[str, ...]:
    return tuple(json.dumps(value, separators=(",", ":")) for value in joint_transcripts(problem))


def _state_constraints(
    problem: IncompletePortfolioProblem,
    state_index: int,
) -> tuple[list[list[float]], list[float]]:
    transcripts = joint_transcripts(problem)
    rows: list[list[float]] = []
    bounds: list[float] = []
    for release_index, release in enumerate(problem.releases):
        for observation_index, observation in enumerate(release.observation_ids):
            indicator = [1.0 if value[release_index] == observation else 0.0 for value in transcripts]
            lower, upper = _effective_marginal_bounds(release, state_index)
            rows.append(indicator)
            bounds.append(upper[observation_index])
            rows.append([-value for value in indicator])
            bounds.append(-lower[observation_index])
    state_id = problem.state_ids[state_index]
    for event in problem.joint_event_bounds:
        if event.state_id != state_id:
            continue
        event_set = set(event.transcripts)
        indicator = [1.0 if value in event_set else 0.0 for value in transcripts]
        rows.append(indicator)
        bounds.append(event.upper)
        rows.append([-value for value in indicator])
        bounds.append(-event.lower)
    return rows, bounds


def _rational_state_constraints(
    problem: IncompletePortfolioProblem,
    state_index: int,
) -> tuple[list[list[Fraction]], list[Fraction]]:
    transcripts = joint_transcripts(problem)
    rows: list[list[Fraction]] = []
    bounds: list[Fraction] = []
    for release_index, release in enumerate(problem.releases):
        lower, upper = _rational_marginal_bounds(release, state_index)
        for observation_index, observation in enumerate(release.observation_ids):
            indicator = [
                Fraction(1) if value[release_index] == observation else Fraction(0)
                for value in transcripts
            ]
            rows.append(indicator)
            bounds.append(upper[observation_index])
            rows.append([-value for value in indicator])
            bounds.append(-lower[observation_index])
    state_id = problem.state_ids[state_index]
    for event in problem.joint_event_bounds:
        if event.state_id != state_id:
            continue
        event_set = set(event.transcripts)
        indicator = [Fraction(1) if value in event_set else Fraction(0) for value in transcripts]
        rows.append(indicator)
        bounds.append(_fraction(event.upper))
        rows.append([-value for value in indicator])
        bounds.append(-_fraction(event.lower))
    return rows, bounds


def _linprog() -> Any:
    try:
        from scipy.optimize import linprog
    except ImportError as exc:  # pragma: no cover - exercised in minimal installations
        raise RuntimeError(
            "the exact portfolio solver requires the optional 'portfolio' dependencies"
        ) from exc
    return linprog


def _solve_state_lp(
    problem: IncompletePortfolioProblem,
    state_index: int,
    rewards: list[float],
) -> tuple[tuple[float, ...], StateDualCertificate]:
    linprog = _linprog()
    rows, bounds = _state_constraints(problem, state_index)
    width = len(rewards)
    primal = linprog(
        [-value for value in rewards],
        A_ub=rows or None,
        b_ub=bounds or None,
        A_eq=[[1.0] * width],
        b_eq=[1.0],
        bounds=[(0.0, None)] * width,
        method="highs",
    )
    if not primal.success:
        raise ValueError(
            f"portfolio ambiguity set is infeasible for state {problem.state_ids[state_index]}: "
            f"{primal.message}"
        )

    # Dual of max c.q subject to A q <= b, 1.q=1, q>=0:
    # min b.lambda + nu subject to A^T lambda + nu >= c, lambda>=0.
    dual_constraints = [
        [-rows[row][column] for row in range(len(rows))] + [-1.0]
        for column in range(width)
    ]
    dual = linprog(
        [*bounds, 1.0],
        A_ub=dual_constraints,
        b_ub=[-value for value in rewards],
        bounds=[(0.0, None)] * len(bounds) + [(None, None)],
        method="highs",
    )
    if not dual.success:
        raise RuntimeError(f"failed to construct LP dual certificate: {dual.message}")
    multipliers = tuple(max(0.0, float(value)) for value in dual.x[:-1])
    normalization = float(dual.x[-1])
    raw_objective = (
        sum(bound * value for bound, value in zip(bounds, multipliers, strict=True))
        + normalization
    )
    maximum_shortfall = max(
        0.0,
        *(
            rewards[column]
            - normalization
            - sum(rows[row][column] * multipliers[row] for row in range(len(rows)))
            for column in range(width)
        ),
    )
    return (
        tuple(max(0.0, float(value)) for value in primal.x),
        StateDualCertificate(
            state_id=problem.state_ids[state_index],
            inequality_multipliers=multipliers,
            normalization_multiplier=normalization,
            raw_dual_objective=float(raw_objective),
            maximum_constraint_shortfall=float(maximum_shortfall),
            objective_bound=float(raw_objective + maximum_shortfall),
        ),
    )


def _bounded_decoder_count(action_count: int, observation_count: int, limit: int) -> int | None:
    count = 1
    for _ in range(observation_count):
        if count > limit // action_count:
            return None
        count *= action_count
    return count


def exact_decoder_count(
    problem: IncompletePortfolioProblem,
    *,
    limit: int = MAX_EXACT_DECODERS,
) -> int | None:
    """Return the exact decoder count, or ``None`` when it exceeds the hard/effective limit."""
    effective_limit = min(limit, MAX_EXACT_DECODERS)
    return _bounded_decoder_count(
        len(problem.decision_problem.action_ids),
        len(joint_transcripts(problem)),
        effective_limit,
    )


def solve_exact_portfolio(
    problem: IncompletePortfolioProblem,
    *,
    certificate_id: str = "portfolio-exact",
    max_decoders: int = MAX_EXACT_DECODERS,
    numerical_tolerance: float = 1e-8,
) -> ExactPortfolioCertificate:
    """Globally solve the finite linear ambiguity problem by exhaustive decoder coverage.

    This solver supports arbitrary couplings and row-wise linear mechanism constraints.
    Conditional independence with uncertain marginals is nonlinear and is deliberately
    delegated to the sound envelope solver below.
    """
    if max_decoders < 1:
        raise ValueError("max_decoders must be at least one")
    if not 0.0 < numerical_tolerance <= 1e-5:
        raise ValueError("numerical_tolerance must lie in (0, 1e-5]")
    if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE:
        raise ValueError(
            "exact LP enumeration does not encode conditional independence; use "
            "independent_product_experiment for exact marginals or the envelope certificate"
        )
    transcripts = joint_transcripts(problem)
    action_count = len(problem.decision_problem.action_ids)
    effective_limit = min(max_decoders, MAX_EXACT_DECODERS)
    decoder_count = exact_decoder_count(problem, limit=effective_limit)
    if decoder_count is None:
        raise ValueError(
            f"exact solver exceeds max_decoders={effective_limit}; "
            "use the decoder-free envelope certificate or tighten the output alphabet"
        )

    certificates: list[DecoderUpperCertificate] = []
    best_upper = -1.0
    best_primal_value = -1.0
    best_channel: tuple[tuple[float, ...], ...] | None = None
    for decoder in itertools.product(range(action_count), repeat=len(transcripts)):
        state_duals: list[StateDualCertificate] = []
        channel_rows: list[tuple[float, ...]] = []
        primal_value = 0.0
        decoder_upper = 0.0
        for state_index, state_gain in enumerate(problem.decision_problem.gain):
            rewards = [state_gain[decoder[observation]] for observation in range(len(transcripts))]
            primal_row, dual = _solve_state_lp(problem, state_index, rewards)
            channel_rows.append(primal_row)
            state_duals.append(dual)
            primal_value += problem.prior[state_index] * sum(
                probability * reward for probability, reward in zip(primal_row, rewards, strict=True)
            )
            decoder_upper += problem.prior[state_index] * dual.objective_bound
        certificates.append(
            DecoderUpperCertificate(
                action_indices=tuple(decoder),
                state_duals=tuple(state_duals),
                upper_bound=max(0.0, float(decoder_upper)),
            )
        )
        if decoder_upper > best_upper:
            best_upper = decoder_upper
        if primal_value > best_primal_value:
            best_primal_value = primal_value
            best_channel = tuple(channel_rows)

    assert best_channel is not None
    witness = FiniteExperiment(
        experiment_id=f"{problem.portfolio_id}:worst-witness",
        threat_id=problem.decision_problem.problem_id,
        population_scope_id=f"{problem.portfolio_id}:population",
        state_ids=problem.state_ids,
        observation_ids=joint_observation_ids(problem),
        channel=best_channel,
        prior=problem.prior,
        interface_description="joint channel attaining the certified incomplete-portfolio lower bound",
    )
    lower_bound = decision_value(witness, problem.decision_problem, problem.prior)
    upper_bound = min(1.0, max(0.0, float(best_upper)))
    return ExactPortfolioCertificate(
        certificate_id=certificate_id,
        problem_sha256=portfolio_problem_sha256(problem),
        joint_observation_ids=joint_observation_ids(problem),
        decoder_count=decoder_count,
        decoder_certificates=tuple(certificates),
        upper_bound=upper_bound,
        lower_bound=lower_bound,
        winning_joint_channel=best_channel,
        optimality_gap=max(0.0, upper_bound - lower_bound),
        numerical_tolerance=numerical_tolerance,
        solver="scipy.optimize.linprog(method='highs'); exhaustive deterministic-decoder cover",
        selection_valid=problem.selection_valid,
        coverage_confidence=problem.coverage_confidence,
    )


def _derived_cell_upper_bounds(problem: IncompletePortfolioProblem) -> tuple[tuple[float, ...], ...]:
    transcripts = joint_transcripts(problem)
    result: list[tuple[float, ...]] = []
    for state_index, state_id in enumerate(problem.state_ids):
        state_bounds: list[float] = []
        for transcript in transcripts:
            component_bounds = []
            for release_index, release in enumerate(problem.releases):
                _, upper = _effective_marginal_bounds(release, state_index)
                component_bounds.append(
                    upper[release.observation_ids.index(transcript[release_index])]
                )
            if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE:
                upper = 1.0
                for value in component_bounds:
                    upper *= value
            else:
                upper = min(component_bounds)
            for event in problem.joint_event_bounds:
                if event.state_id == state_id and transcript in event.transcripts:
                    upper = min(upper, event.upper)
            state_bounds.append(max(0.0, min(1.0, upper)))
        result.append(tuple(state_bounds))
    return tuple(result)


def _probability_point(lower: tuple[float, ...], upper: tuple[float, ...]) -> tuple[float, ...]:
    row = list(lower)
    remaining = 1.0 - sum(row)
    for index in range(len(row)):
        addition = min(remaining, upper[index] - row[index])
        row[index] += addition
        remaining -= addition
    if remaining > 1e-10:
        raise ValueError("marginal interval row does not contain a probability vector")
    total = sum(row)
    return tuple(max(0.0, value) / total for value in row)


def _feasible_joint_channel(problem: IncompletePortfolioProblem) -> tuple[tuple[float, ...], ...]:
    if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE:
        rows: list[tuple[float, ...]] = []
        transcripts = joint_transcripts(problem)
        for state_index in range(len(problem.state_ids)):
            marginal_points = [
                _probability_point(*_effective_marginal_bounds(release, state_index))
                for release in problem.releases
            ]
            row = []
            for transcript in transcripts:
                probability = 1.0
                for release_index, release in enumerate(problem.releases):
                    probability *= marginal_points[release_index][
                        release.observation_ids.index(transcript[release_index])
                    ]
                row.append(probability)
            rows.append(tuple(row))
        return tuple(rows)
    return tuple(
        _solve_state_lp(
            problem,
            state_index,
            [0.0] * len(joint_transcripts(problem)),
        )[0]
        for state_index in range(len(problem.state_ids))
    )


def build_envelope_certificate(
    problem: IncompletePortfolioProblem,
    *,
    certificate_id: str = "portfolio-envelope",
) -> EnvelopePortfolioCertificate:
    """Return a decoder-free universal ceiling; it may be conservative.

    Its size is linear in the explicitly enumerated joint alphabet, which may
    itself grow exponentially with the number of releases.
    """
    cell_bounds = _derived_cell_upper_bounds(problem)
    feasible_channel = _feasible_joint_channel(problem)
    raw = _envelope_raw_upper(problem, cell_bounds)
    derivation = (
        "conditional-independence product of marginal upper bounds plus joint-event bounds"
        if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE
        else "Frechet minimum of marginal upper bounds plus joint-event bounds"
    )
    return EnvelopePortfolioCertificate(
        certificate_id=certificate_id,
        problem_sha256=portfolio_problem_sha256(problem),
        joint_observation_ids=joint_observation_ids(problem),
        cell_upper_bounds=cell_bounds,
        feasible_joint_channel=feasible_channel,
        raw_upper_bound=float(raw),
        upper_bound=min(1.0, max(0.0, float(raw))),
        derivation=derivation,
        selection_valid=problem.selection_valid,
        coverage_confidence=problem.coverage_confidence,
    )


def solve_analytic_portfolio(
    problem: IncompletePortfolioProblem,
    *,
    method: Literal["auto", "exact", "envelope"] = "auto",
    certificate_id: str = "portfolio-certificate",
    max_decoders: int = MAX_EXACT_DECODERS,
    numerical_tolerance: float = 1e-8,
) -> AnalyticPortfolioEvidenceEntry:
    """Create the portable evidence object consumed by the CLI and optimizer."""
    if max_decoders < 1:
        raise ValueError("max_decoders must be at least one")
    if not 0.0 < numerical_tolerance <= 1e-5:
        raise ValueError("numerical_tolerance must lie in (0, 1e-5]")
    if method == "auto":
        method = (
            "exact"
            if problem.coupling_model is not CouplingModel.CONDITIONAL_INDEPENDENCE
            and exact_decoder_count(problem, limit=max_decoders) is not None
            else "envelope"
        )
    if method == "exact":
        certificate = solve_exact_portfolio(
            problem,
            certificate_id=certificate_id,
            max_decoders=max_decoders,
            numerical_tolerance=numerical_tolerance,
        )
        return AnalyticPortfolioEvidenceEntry(
            problem=problem,
            exact_certificate=certificate,
            rational_upper_audit=build_rational_upper_audit(problem, certificate),
        )
    if method == "envelope":
        certificate = build_envelope_certificate(
            problem,
            certificate_id=certificate_id,
        )
        return AnalyticPortfolioEvidenceEntry(
            problem=problem,
            envelope_certificate=certificate,
            rational_upper_audit=build_rational_upper_audit(problem, certificate),
        )
    raise ValueError(f"unsupported portfolio solution method: {method}")


def _envelope_raw_upper(
    problem: IncompletePortfolioProblem,
    cell_bounds: tuple[tuple[float, ...], ...],
) -> float:
    raw = 0.0
    for observation_index in range(len(joint_transcripts(problem))):
        raw += max(
            sum(
                problem.prior[state_index]
                * cell_bounds[state_index][observation_index]
                * problem.decision_problem.gain[state_index][action_index]
                for state_index in range(len(problem.state_ids))
            )
            for action_index in range(len(problem.decision_problem.action_ids))
        )
    return float(raw)


def independent_product_experiment(
    problem: IncompletePortfolioProblem,
    *,
    experiment_id: str = "portfolio-independent-product",
) -> FiniteExperiment:
    """Build the unique joint channel when exact marginals and independence are certified."""
    if problem.coupling_model is not CouplingModel.CONDITIONAL_INDEPENDENCE:
        raise ValueError("independent product requires the conditional_independence coupling model")
    if problem.joint_event_bounds:
        raise ValueError("independent product does not accept additional joint-event bounds")
    if any(
        abs(lower - upper) > 1e-12
        for release in problem.releases
        for lower_row, upper_row in zip(release.lower, release.upper, strict=True)
        for lower, upper in zip(lower_row, upper_row, strict=True)
    ):
        raise ValueError("independent product is exact only when every marginal interval is a point")
    channel: list[tuple[float, ...]] = []
    for state_index in range(len(problem.state_ids)):
        marginal_points = [
            _probability_point(*_effective_marginal_bounds(release, state_index))
            for release in problem.releases
        ]
        row = []
        for transcript in joint_transcripts(problem):
            probability = 1.0
            for release_index, release in enumerate(problem.releases):
                observation_index = release.observation_ids.index(transcript[release_index])
                probability *= marginal_points[release_index][observation_index]
            row.append(probability)
        channel.append(tuple(row))
    return FiniteExperiment(
        experiment_id=experiment_id,
        threat_id=problem.decision_problem.problem_id,
        population_scope_id=f"{problem.portfolio_id}:population",
        state_ids=problem.state_ids,
        observation_ids=joint_observation_ids(problem),
        channel=tuple(channel),
        prior=problem.prior,
        interface_description="exact joint channel under certified conditional independence",
    )


def verify_envelope_certificate(
    problem: IncompletePortfolioProblem,
    certificate: EnvelopePortfolioCertificate,
    *,
    tolerance: float = 1e-10,
) -> CertificateVerification:
    reasons: list[str] = []
    expected_ids = joint_observation_ids(problem)
    expected_bounds = _derived_cell_upper_bounds(problem)
    expected_raw = _envelope_raw_upper(problem, expected_bounds)
    expected_upper = min(1.0, max(0.0, expected_raw))
    expected_derivation = (
        "conditional-independence product of marginal upper bounds plus joint-event bounds"
        if problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE
        else "Frechet minimum of marginal upper bounds plus joint-event bounds"
    )
    if certificate.problem_sha256 != portfolio_problem_sha256(problem):
        reasons.append("problem hash mismatch")
    if certificate.joint_observation_ids != expected_ids:
        reasons.append("joint observation ordering mismatch")
    if len(certificate.cell_upper_bounds) != len(expected_bounds) or any(
        len(actual) != len(wanted)
        or any(abs(left - right) > tolerance for left, right in zip(actual, wanted, strict=True))
        for actual, wanted in zip(certificate.cell_upper_bounds, expected_bounds, strict=False)
    ):
        reasons.append("cell envelope does not replay")
    if abs(certificate.raw_upper_bound - expected_raw) > tolerance:
        reasons.append("raw upper bound does not replay")
    if abs(certificate.upper_bound - expected_upper) > tolerance:
        reasons.append("clipped upper bound does not replay")
    if certificate.derivation != expected_derivation:
        reasons.append("envelope derivation label does not replay")
    if not _channel_is_feasible(
        problem,
        certificate.feasible_joint_channel,
        tolerance=tolerance,
        require_independence=(
            problem.coupling_model is CouplingModel.CONDITIONAL_INDEPENDENCE
        ),
    ):
        reasons.append("feasible-channel witness does not satisfy the ambiguity set")
    if certificate.selection_valid != problem.selection_valid:
        reasons.append("selection-validity claim does not match coverage mode")
    if abs(certificate.coverage_confidence - problem.coverage_confidence) > tolerance:
        reasons.append("coverage confidence mismatch")
    return CertificateVerification(
        valid=not reasons,
        # The verifier's recomputation is authoritative. Tolerance may determine
        # whether a serialization is accepted, but never lower the clearing value.
        upper_bound=expected_upper,
        reasons=tuple(reasons),
    )


def verify_exact_certificate(
    problem: IncompletePortfolioProblem,
    certificate: ExactPortfolioCertificate,
    *,
    max_decoders: int = MAX_EXACT_DECODERS,
) -> CertificateVerification:
    tolerance = certificate.numerical_tolerance
    reasons: list[str] = []
    transcripts = joint_transcripts(problem)
    expected_ids = joint_observation_ids(problem)
    action_count = len(problem.decision_problem.action_ids)
    effective_limit = min(max_decoders, MAX_EXACT_DECODERS)
    decoder_count = _bounded_decoder_count(action_count, len(transcripts), effective_limit)
    if decoder_count is None:
        return CertificateVerification(
            valid=False,
            upper_bound=certificate.upper_bound,
            lower_bound=certificate.lower_bound,
            reasons=(
                f"certificate exceeds max_decoders={effective_limit}",
            ),
        )
    expected_decoders = tuple(itertools.product(range(action_count), repeat=len(transcripts)))
    if certificate.problem_sha256 != portfolio_problem_sha256(problem):
        reasons.append("problem hash mismatch")
    if certificate.joint_observation_ids != expected_ids:
        reasons.append("joint observation ordering mismatch")
    if certificate.decoder_count != len(expected_decoders):
        reasons.append("decoder count is not exhaustive")
    supplied_decoders = tuple(value.action_indices for value in certificate.decoder_certificates)
    if supplied_decoders != expected_decoders:
        reasons.append("decoder certificates do not provide the canonical exhaustive cover")

    replayed_bounds: list[float] = []
    if len(certificate.decoder_certificates) == len(expected_decoders):
        for decoder_certificate in certificate.decoder_certificates:
            if (
                len(decoder_certificate.action_indices) != len(transcripts)
                or any(
                    action < 0 or action >= action_count
                    for action in decoder_certificate.action_indices
                )
            ):
                reasons.append("decoder certificate contains an invalid action assignment")
                continue
            if len(decoder_certificate.state_duals) != len(problem.state_ids):
                reasons.append("decoder certificate has the wrong number of state duals")
                continue
            decoder_bound = 0.0
            for state_index, dual in enumerate(decoder_certificate.state_duals):
                rows, bounds = _state_constraints(problem, state_index)
                if dual.state_id != problem.state_ids[state_index]:
                    reasons.append("state dual identifier mismatch")
                    continue
                if len(dual.inequality_multipliers) != len(bounds):
                    reasons.append("state dual has the wrong multiplier dimension")
                    continue
                if any(value < 0.0 for value in dual.inequality_multipliers):
                    reasons.append("state dual contains a negative inequality multiplier")
                    continue
                maximum_shortfall = 0.0
                for observation_index in range(len(transcripts)):
                    lhs = dual.normalization_multiplier + sum(
                        rows[row_index][observation_index] * dual.inequality_multipliers[row_index]
                        for row_index in range(len(rows))
                    )
                    reward = problem.decision_problem.gain[state_index][
                        decoder_certificate.action_indices[observation_index]
                    ]
                    maximum_shortfall = max(maximum_shortfall, reward - lhs)
                raw_objective = dual.normalization_multiplier + sum(
                    bound * value
                    for bound, value in zip(bounds, dual.inequality_multipliers, strict=True)
                )
                maximum_shortfall = max(0.0, maximum_shortfall)
                objective = raw_objective + maximum_shortfall
                if abs(raw_objective - dual.raw_dual_objective) > tolerance:
                    reasons.append("raw state dual objective does not replay")
                if abs(maximum_shortfall - dual.maximum_constraint_shortfall) > tolerance:
                    reasons.append("state dual feasibility penalty does not replay")
                if abs(objective - dual.objective_bound) > tolerance:
                    reasons.append("state dual objective does not replay")
                decoder_bound += problem.prior[state_index] * objective
            if abs(decoder_bound - decoder_certificate.upper_bound) > tolerance:
                reasons.append("decoder upper bound does not replay")
            replayed_bounds.append(decoder_bound)

    replayed_upper = min(1.0, max([0.0, *replayed_bounds]))
    if abs(replayed_upper - certificate.upper_bound) > tolerance:
        reasons.append("global upper bound does not replay")

    if not _channel_is_feasible(
        problem,
        certificate.winning_joint_channel,
        tolerance=tolerance,
        require_independence=False,
    ):
        reasons.append("winning joint channel is infeasible")
        lower = certificate.lower_bound
    else:
        witness = FiniteExperiment(
            experiment_id=f"{problem.portfolio_id}:verified-witness",
            threat_id=problem.decision_problem.problem_id,
            population_scope_id=f"{problem.portfolio_id}:population",
            state_ids=problem.state_ids,
            observation_ids=expected_ids,
            channel=certificate.winning_joint_channel,
            prior=problem.prior,
            interface_description="replayed incomplete-portfolio witness",
        )
        lower = decision_value(witness, problem.decision_problem, problem.prior)
        if abs(lower - certificate.lower_bound) > tolerance:
            reasons.append("lower-bound witness value does not replay")
    if certificate.lower_bound > certificate.upper_bound + tolerance:
        reasons.append("lower bound exceeds upper bound")
    if abs(certificate.optimality_gap - max(0.0, certificate.upper_bound - certificate.lower_bound)) > tolerance:
        reasons.append("optimality gap does not replay")
    if certificate.selection_valid != problem.selection_valid:
        reasons.append("selection-validity claim does not match coverage mode")
    if abs(certificate.coverage_confidence - problem.coverage_confidence) > tolerance:
        reasons.append("coverage confidence mismatch")
    return CertificateVerification(
        valid=not reasons,
        # Use the replayed dual cover rather than the submitted summary. Otherwise
        # a near-tolerance downward edit could alter a threshold decision.
        upper_bound=replayed_upper,
        lower_bound=lower,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def verify_analytic_portfolio(
    entry: AnalyticPortfolioEvidenceEntry,
) -> CertificateVerification:
    """Replay numerical diagnostics and the security-critical exact rational ceiling."""
    certificate: ExactPortfolioCertificate | EnvelopePortfolioCertificate
    numerical: CertificateVerification
    if entry.exact_certificate is not None:
        certificate = entry.exact_certificate
        numerical = verify_exact_certificate(entry.problem, certificate)
    else:
        assert entry.envelope_certificate is not None
        certificate = entry.envelope_certificate
        numerical = verify_envelope_certificate(entry.problem, certificate)
    reasons = list(numerical.reasons)
    try:
        rational = build_rational_upper_audit(entry.problem, certificate)
    except ValueError as exc:
        reasons.append(f"rational replay failed: {exc}")
        return CertificateVerification(
            valid=False,
            upper_bound=1.0,
            lower_bound=numerical.lower_bound,
            reasons=tuple(dict.fromkeys(reasons)),
        )
    if entry.rational_upper_audit != rational:
        reasons.append("rational upper audit does not replay")
    return CertificateVerification(
        valid=not reasons,
        upper_bound=rational.outward_upper_bound,
        lower_bound=numerical.lower_bound,
        exact_upper_numerator=rational.exact_upper_numerator,
        exact_upper_denominator=rational.exact_upper_denominator,
        rationally_replayed=True,
        outward_rounded=True,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _channel_is_feasible(
    problem: IncompletePortfolioProblem,
    channel: tuple[tuple[float, ...], ...],
    *,
    tolerance: float,
    require_independence: bool,
) -> bool:
    transcripts = joint_transcripts(problem)
    if len(channel) != len(problem.state_ids):
        return False
    for state_index, row in enumerate(channel):
        rows, bounds = _state_constraints(problem, state_index)
        if len(row) != len(transcripts) or any(value < 0.0 for value in row):
            return False
        if abs(sum(row) - 1.0) > tolerance:
            return False
        if any(
            sum(coefficient * value for coefficient, value in zip(constraint, row, strict=True))
            > bound + tolerance
            for constraint, bound in zip(rows, bounds, strict=True)
        ):
            return False
        if require_independence:
            marginal_rows: list[list[float]] = []
            for release_index, release in enumerate(problem.releases):
                marginal_rows.append([
                    sum(
                        row[cell_index]
                        for cell_index, transcript in enumerate(transcripts)
                        if transcript[release_index] == observation
                    )
                    for observation in release.observation_ids
                ])
            for cell_index, transcript in enumerate(transcripts):
                product_probability = 1.0
                for release_index, release in enumerate(problem.releases):
                    product_probability *= marginal_rows[release_index][
                        release.observation_ids.index(transcript[release_index])
                    ]
                if abs(row[cell_index] - product_probability) > tolerance:
                    return False
    return True


def certificate_can_clear(
    verification: CertificateVerification,
    *,
    threshold: float,
    selection_valid: bool,
) -> bool:
    """Policy helper: a numerical ceiling is insufficient without selection-valid coverage."""
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("threshold must lie in [0,1]")
    if not verification.rationally_replayed or not verification.outward_rounded:
        return False
    assert verification.exact_upper_numerator is not None
    assert verification.exact_upper_denominator is not None
    return (
        verification.valid
        and selection_valid
        and Fraction(
            verification.exact_upper_numerator,
            verification.exact_upper_denominator,
        ) <= _fraction(threshold)
    )


def verified_upper_fraction(verification: CertificateVerification) -> Fraction:
    """Return the authoritative exact ceiling, refusing a merely floating replay."""
    if (
        not verification.valid
        or not verification.rationally_replayed
        or verification.exact_upper_numerator is None
        or verification.exact_upper_denominator is None
    ):
        raise ValueError("certificate does not contain a valid rationally replayed upper bound")
    return Fraction(
        verification.exact_upper_numerator,
        verification.exact_upper_denominator,
    )


def outward_rounded_fraction(value: Fraction) -> float:
    """Public policy-boundary helper for a non-negative rational success value."""
    return _outward_float(_clipped_unit(value))


def decimal_fraction(value: float | int) -> Fraction:
    """Public helper matching the exact canonical-JSON number interpretation."""
    return _fraction(value)


def parity_interaction_identified_bounds(
    state_0_interval: tuple[Fraction, Fraction],
    state_1_interval: tuple[Fraction, Fraction],
) -> tuple[Fraction, Fraction]:
    """Sharp exact-guess interval for a highest-order binary parity channel.

    The result assumes an equal-prior binary secret and ``m`` binary releases for
    which every proper-subset conditional marginal is uniform.  ``state_x_interval``
    bounds the parity coefficient

        E[(-1) ** sum(Y_j) | X=x]

    in ``[-1, 1]``.  Under these assumptions the complete conditional channel row is
    ``2**-m * (1 + theta_x * parity_sign)``.  The returned lower and upper values are
    the sharp identified interval over the two coefficient intervals.

    Fractions are required deliberately: this helper is theorem arithmetic and must
    not silently import binary floating-point semantics into a policy boundary.
    """
    lower_0, upper_0 = state_0_interval
    lower_1, upper_1 = state_1_interval
    endpoints = (lower_0, upper_0, lower_1, upper_1)
    if any(not isinstance(value, Fraction) for value in endpoints):
        raise TypeError("parity coefficient endpoints must be fractions")
    if lower_0 > upper_0 or lower_1 > upper_1:
        raise ValueError("parity coefficient intervals must be ordered")
    if any(value < -1 or value > 1 for value in endpoints):
        raise ValueError("parity coefficient endpoints must lie in [-1,1]")

    minimum_separation = max(Fraction(0), lower_0 - upper_1, lower_1 - upper_0)
    maximum_separation = max(abs(lower_0 - upper_1), abs(upper_0 - lower_1))
    return (
        Fraction(1, 2) + minimum_separation / 4,
        Fraction(1, 2) + maximum_separation / 4,
    )


def binary_uniform_diagonal_identified_bounds(
    state_0_interval: tuple[Fraction, Fraction],
    state_1_interval: tuple[Fraction, Fraction],
) -> tuple[Fraction, Fraction]:
    """Sharp interval when two conditionally uniform bits have bounded agreement.

    ``state_x_interval`` bounds ``Pr[Y_1 = Y_2 | X=x]``.  This is the two-release
    form of :func:`parity_interaction_identified_bounds` under the transformation
    ``theta_x = 2 * agreement_x - 1``.
    """
    endpoints = (*state_0_interval, *state_1_interval)
    if any(not isinstance(value, Fraction) for value in endpoints):
        raise TypeError("diagonal probability endpoints must be fractions")
    if any(value < 0 or value > 1 for value in endpoints):
        raise ValueError("diagonal probability endpoints must lie in [0,1]")
    return parity_interaction_identified_bounds(
        tuple(2 * value - 1 for value in state_0_interval),
        tuple(2 * value - 1 for value in state_1_interval),
    )
