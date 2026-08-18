from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import Field, model_validator

from .models import StrictModel


class FiniteExperiment(StrictModel):
    """A finite information structure P(observation | secret state)."""

    experiment_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    decision_game_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    state_ids: tuple[str, ...] = Field(min_length=2)
    observation_ids: tuple[str, ...] = Field(min_length=1)
    channel: tuple[tuple[float, ...], ...]
    prior: tuple[float, ...]
    interface_description: str = Field(min_length=1, max_length=2048)
    interface_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def finite_channel_is_valid(self) -> FiniteExperiment:
        if len(set(self.state_ids)) != len(self.state_ids):
            raise ValueError("experiment state identifiers must be unique")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("experiment observation identifiers must be unique")
        if len(self.channel) != len(self.state_ids):
            raise ValueError("experiment requires one channel row per state")
        if len(self.prior) != len(self.state_ids):
            raise ValueError("experiment prior must align with states")
        if any(probability < 0.0 or probability > 1.0 for probability in self.prior):
            raise ValueError("experiment prior probabilities must lie in [0,1]")
        if abs(sum(self.prior) - 1.0) > 1e-10:
            raise ValueError("experiment prior must sum to one")
        width = len(self.observation_ids)
        for row in self.channel:
            if len(row) != width:
                raise ValueError("experiment channel rows must align with observations")
            if any(probability < 0.0 or probability > 1.0 for probability in row):
                raise ValueError("experiment channel probabilities must lie in [0,1]")
            if abs(sum(row) - 1.0) > 1e-10:
                raise ValueError("each experiment channel row must sum to one")
        return self


class DecisionProblem(StrictModel):
    """A bounded success functional g(secret state, adversary action)."""

    problem_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    state_ids: tuple[str, ...] = Field(min_length=2)
    action_ids: tuple[str, ...] = Field(min_length=1)
    gain: tuple[tuple[float, ...], ...]
    interpretation: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def gain_table_is_valid(self) -> DecisionProblem:
        if len(set(self.state_ids)) != len(self.state_ids):
            raise ValueError("decision-problem state identifiers must be unique")
        if len(set(self.action_ids)) != len(self.action_ids):
            raise ValueError("decision-problem action identifiers must be unique")
        if len(self.gain) != len(self.state_ids):
            raise ValueError("decision problem requires one gain row per state")
        width = len(self.action_ids)
        for row in self.gain:
            if len(row) != width:
                raise ValueError("decision-problem gain rows must align with actions")
            if any(value < 0.0 or value > 1.0 for value in row):
                raise ValueError("success gains must lie in [0,1]")
        return self


class PopulationAnchor(StrictModel):
    anchor_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    state_ids: tuple[str, ...] = Field(min_length=2)
    prior: tuple[float, ...]
    population_definition: str = Field(min_length=1, max_length=4096)
    source: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def anchored_prior_is_valid(self) -> PopulationAnchor:
        if len(set(self.state_ids)) != len(self.state_ids):
            raise ValueError("anchor state identifiers must be unique")
        if len(self.prior) != len(self.state_ids):
            raise ValueError("anchor prior must align with states")
        if any(value < 0.0 or value > 1.0 for value in self.prior):
            raise ValueError("anchor probabilities must lie in [0,1]")
        if abs(sum(self.prior) - 1.0) > 1e-10:
            raise ValueError("anchor prior must sum to one")
        return self


class GarblingCertificate(StrictModel):
    """Replayable exact/approximate witness that dominated is a garbling of dominant."""

    certificate_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    dominant_experiment_id: str
    dominated_experiment_id: str
    kernel: tuple[tuple[float, ...], ...]
    maximum_row_total_variation: float = Field(default=0.0, ge=0.0, le=1.0)
    numerical_tolerance: float = Field(default=1e-12, gt=0.0, le=1e-9)
    construction: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def kernel_entries_are_probabilities(self) -> GarblingCertificate:
        if self.dominant_experiment_id == self.dominated_experiment_id:
            raise ValueError("a garbling certificate must connect distinct experiment identifiers")
        if not self.kernel:
            raise ValueError("garbling kernel cannot be empty")
        width = len(self.kernel[0])
        if width == 0:
            raise ValueError("garbling kernel cannot have empty rows")
        for row in self.kernel:
            if len(row) != width:
                raise ValueError("garbling kernel must be rectangular")
            if any(value < 0.0 or value > 1.0 for value in row):
                raise ValueError("garbling-kernel probabilities must lie in [0,1]")
            if abs(sum(row) - 1.0) > 1e-10:
                raise ValueError("garbling-kernel rows must sum to one")
        return self


class GarblingVerification(StrictModel):
    certificate_id: str
    dominant_experiment_id: str
    dominated_experiment_id: str
    valid: bool
    maximum_absolute_error: float = Field(ge=0.0)
    maximum_row_total_variation: float = Field(ge=0.0, le=1.0)
    decision_value_penalty: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...]


class DecisionReversalWitness(StrictModel):
    left_experiment_id: str
    right_experiment_id: str
    left_favouring_problem_id: str
    right_favouring_problem_id: str
    left_problem_values: tuple[float, float]
    right_problem_values: tuple[float, float]
    minimum_value_gap: float = Field(gt=0.0)
    supported_states: int = Field(ge=2)
    non_degenerate: bool
    interpretation: str


class SeparationWitness(StrictModel):
    evaluated_experiment_id: str
    released_experiment_id: str
    separating_problem_id: str
    evaluated_value: float = Field(ge=0.0, le=1.0)
    released_value: float = Field(ge=0.0, le=1.0)
    value_gap: float = Field(gt=0.0)
    supported_states: int = Field(ge=2)
    proves_evaluated_does_not_dominate_released: bool = True


class AnchoringReversalWitness(StrictModel):
    left_experiment_id: str
    right_experiment_id: str
    problem_id: str
    left_favouring_anchor_id: str
    right_favouring_anchor_id: str
    left_anchor_values: tuple[float, float]
    right_anchor_values: tuple[float, float]
    minimum_value_gap: float = Field(gt=0.0)
    minimum_anchor_support: int = Field(ge=2)
    non_degenerate: bool
    interpretation: str


def deterministic_experiment(
    *,
    experiment_id: str,
    threat_id: str,
    population_scope_id: str,
    state_ids: Sequence[str],
    observations: Sequence[str],
    prior: Sequence[float] | None = None,
    interface_description: str,
    decision_game_sha256: str | None = None,
    interface_sha256: str | None = None,
    artifact_sha256: str | None = None,
) -> FiniteExperiment:
    if len(state_ids) != len(observations):
        raise ValueError("deterministic observations must align with states")
    observation_ids = tuple(sorted(set(observations)))
    positions = {value: index for index, value in enumerate(observation_ids)}
    channel = tuple(
        tuple(1.0 if index == positions[value] else 0.0 for index in range(len(observation_ids)))
        for value in observations
    )
    probabilities = tuple(prior) if prior is not None else tuple(1.0 / len(state_ids) for _ in state_ids)
    return FiniteExperiment(
        experiment_id=experiment_id,
        threat_id=threat_id,
        population_scope_id=population_scope_id,
        state_ids=tuple(state_ids),
        observation_ids=observation_ids,
        channel=channel,
        prior=probabilities,
        interface_description=interface_description,
        decision_game_sha256=decision_game_sha256,
        interface_sha256=interface_sha256,
        artifact_sha256=artifact_sha256,
    )


def exact_guess_problem(state_ids: Sequence[str], problem_id: str = "exact-guess") -> DecisionProblem:
    states = tuple(state_ids)
    return DecisionProblem(
        problem_id=problem_id,
        state_ids=states,
        action_ids=states,
        gain=tuple(
            tuple(1.0 if state == action else 0.0 for action in states)
            for state in states
        ),
        interpretation="exact recovery of the secret state",
    )


def decision_value(
    experiment: FiniteExperiment,
    problem: DecisionProblem,
    prior: Sequence[float] | None = None,
) -> float:
    if experiment.state_ids != problem.state_ids:
        raise ValueError("experiment and decision problem must use the same ordered state space")
    probabilities = tuple(prior) if prior is not None else experiment.prior
    if len(probabilities) != len(experiment.state_ids):
        raise ValueError("decision prior must align with experiment states")
    if any(value < 0.0 or value > 1.0 for value in probabilities):
        raise ValueError("decision prior probabilities must lie in [0,1]")
    if abs(sum(probabilities) - 1.0) > 1e-10:
        raise ValueError("decision prior must sum to one")
    value = 0.0
    for observation in range(len(experiment.observation_ids)):
        action_values = [
            sum(
                probabilities[state]
                * experiment.channel[state][observation]
                * problem.gain[state][action]
                for state in range(len(experiment.state_ids))
            )
            for action in range(len(problem.action_ids))
        ]
        value += max(action_values)
    return min(1.0, max(0.0, float(value)))


def verify_garbling(
    dominant: FiniteExperiment,
    dominated: FiniteExperiment,
    certificate: GarblingCertificate,
) -> GarblingVerification:
    reasons: list[str] = []
    if certificate.dominant_experiment_id != dominant.experiment_id:
        reasons.append("certificate dominant identifier mismatch")
    if certificate.dominated_experiment_id != dominated.experiment_id:
        reasons.append("certificate dominated identifier mismatch")
    if dominant.threat_id != dominated.threat_id:
        reasons.append("experiments concern different threats")
    if dominant.population_scope_id != dominated.population_scope_id:
        reasons.append("experiments use different population scopes")
    if dominant.state_ids != dominated.state_ids:
        reasons.append("experiments use different ordered state spaces")
    if len(certificate.kernel) != len(dominant.observation_ids):
        reasons.append("kernel row count does not match dominant observations")
    elif any(len(row) != len(dominated.observation_ids) for row in certificate.kernel):
        reasons.append("kernel column count does not match dominated observations")
    maximum_error = 1.0
    maximum_row_tv = 1.0
    if not reasons:
        maximum_error = 0.0
        maximum_row_tv = 0.0
        for state in range(len(dominant.state_ids)):
            row_l1 = 0.0
            for target_observation in range(len(dominated.observation_ids)):
                reconstructed = sum(
                    dominant.channel[state][source_observation]
                    * certificate.kernel[source_observation][target_observation]
                    for source_observation in range(len(dominant.observation_ids))
                )
                residual = abs(reconstructed - dominated.channel[state][target_observation])
                maximum_error = max(maximum_error, residual)
                row_l1 += residual
            maximum_row_tv = max(maximum_row_tv, 0.5 * row_l1)
        if maximum_row_tv > (
            certificate.maximum_row_total_variation + certificate.numerical_tolerance
        ):
            reasons.append(
                "maximum row total-variation residual "
                f"{maximum_row_tv:.6g} exceeds declared bound "
                f"{certificate.maximum_row_total_variation:.6g}"
            )
    return GarblingVerification(
        certificate_id=certificate.certificate_id,
        dominant_experiment_id=dominant.experiment_id,
        dominated_experiment_id=dominated.experiment_id,
        valid=not reasons,
        maximum_absolute_error=maximum_error,
        maximum_row_total_variation=maximum_row_tv,
        decision_value_penalty=maximum_row_tv,
        reasons=tuple(reasons),
    )


def deterministic_garbling_certificate(
    dominant: FiniteExperiment,
    dominated: FiniteExperiment,
    *,
    certificate_id: str,
    tolerance: float = 1e-10,
) -> GarblingCertificate:
    if dominant.state_ids != dominated.state_ids:
        raise ValueError("deterministic garbling requires the same ordered state space")
    dominant_observations: list[int] = []
    for row in dominant.channel:
        ones = [index for index, value in enumerate(row) if abs(value - 1.0) <= tolerance]
        if len(ones) != 1 or any(abs(value) > tolerance for index, value in enumerate(row) if index != ones[0]):
            raise ValueError("dominant experiment is not deterministic")
        dominant_observations.append(ones[0])
    kernel: list[tuple[float, ...]] = []
    for observation in range(len(dominant.observation_ids)):
        states = [index for index, value in enumerate(dominant_observations) if value == observation]
        if not states:
            row = tuple(1.0 if index == 0 else 0.0 for index in range(len(dominated.observation_ids)))
        else:
            row = dominated.channel[states[0]]
            if any(
                max(abs(left - right) for left, right in zip(row, dominated.channel[state], strict=True)) > tolerance
                for state in states[1:]
            ):
                raise ValueError("dominated channel is not constant on a dominant observation fibre")
        kernel.append(tuple(row))
    certificate = GarblingCertificate(
        certificate_id=certificate_id,
        dominant_experiment_id=dominant.experiment_id,
        dominated_experiment_id=dominated.experiment_id,
        kernel=tuple(kernel),
        maximum_row_total_variation=0.0,
        numerical_tolerance=min(tolerance, 1e-9),
        construction="deterministic fibre map replayed from the two finite channels",
    )
    verification = verify_garbling(dominant, dominated, certificate)
    if not verification.valid:
        raise ValueError(f"constructed garbling certificate failed replay: {verification.reasons}")
    return certificate


def order_soundness_check(
    dominant: FiniteExperiment,
    dominated: FiniteExperiment,
    certificate: GarblingCertificate,
    problem: DecisionProblem,
    *,
    prior: Sequence[float] | None = None,
    tolerance: float = 1e-10,
) -> dict[str, Any]:
    verification = verify_garbling(dominant, dominated, certificate)
    if not verification.valid:
        raise ValueError(f"invalid garbling certificate: {verification.reasons}")
    dominant_value = decision_value(dominant, problem, prior)
    dominated_value = decision_value(dominated, problem, prior)
    if dominated_value > dominant_value + verification.decision_value_penalty + tolerance:
        raise AssertionError("garbling monotonicity was violated")
    return {
        "dominant_value": dominant_value,
        "dominated_value": dominated_value,
        "monotonicity_margin": dominant_value - dominated_value,
        "decision_value_penalty": verification.decision_value_penalty,
        "certificate_id": certificate.certificate_id,
    }


def decision_reversal_witness(
    left: FiniteExperiment,
    right: FiniteExperiment,
    left_favouring: DecisionProblem,
    right_favouring: DecisionProblem,
    *,
    minimum_value_gap: float = 0.01,
    minimum_supported_states: int = 30,
) -> DecisionReversalWitness:
    if left.state_ids != right.state_ids or left.prior != right.prior:
        raise ValueError("decision reversal requires common states and prior")
    left_values = (decision_value(left, left_favouring), decision_value(right, left_favouring))
    right_values = (decision_value(left, right_favouring), decision_value(right, right_favouring))
    left_gap = left_values[0] - left_values[1]
    right_gap = right_values[1] - right_values[0]
    if left_gap < minimum_value_gap or right_gap < minimum_value_gap:
        raise ValueError("the supplied decision problems do not establish the required ranking reversal")
    supported = sum(value > 0.0 for value in left.prior)
    return DecisionReversalWitness(
        left_experiment_id=left.experiment_id,
        right_experiment_id=right.experiment_id,
        left_favouring_problem_id=left_favouring.problem_id,
        right_favouring_problem_id=right_favouring.problem_id,
        left_problem_values=left_values,
        right_problem_values=right_values,
        minimum_value_gap=min(left_gap, right_gap),
        supported_states=supported,
        non_degenerate=supported >= minimum_supported_states,
        interpretation=(
            "The experiments are decision-incomparable for the witnessed success functionals; "
            "no gain-independent scalar ranking can agree with both decisions."
        ),
    )


def separation_witness(
    evaluated: FiniteExperiment,
    released: FiniteExperiment,
    problem: DecisionProblem,
    *,
    minimum_value_gap: float = 0.01,
) -> SeparationWitness:
    if evaluated.state_ids != released.state_ids or evaluated.prior != released.prior:
        raise ValueError("substitution separation requires common states and prior")
    evaluated_value = decision_value(evaluated, problem)
    released_value = decision_value(released, problem)
    gap = released_value - evaluated_value
    if gap < minimum_value_gap:
        raise ValueError("the supplied decision problem does not separate released from evaluated experiments")
    return SeparationWitness(
        evaluated_experiment_id=evaluated.experiment_id,
        released_experiment_id=released.experiment_id,
        separating_problem_id=problem.problem_id,
        evaluated_value=evaluated_value,
        released_value=released_value,
        value_gap=gap,
        supported_states=sum(value > 0.0 for value in evaluated.prior),
    )


def anchoring_reversal_witness(
    left: FiniteExperiment,
    right: FiniteExperiment,
    problem: DecisionProblem,
    left_favouring_anchor: PopulationAnchor,
    right_favouring_anchor: PopulationAnchor,
    *,
    minimum_value_gap: float = 0.01,
    minimum_anchor_support: int = 30,
) -> AnchoringReversalWitness:
    if left.state_ids != right.state_ids or problem.state_ids != left.state_ids:
        raise ValueError("anchoring reversal requires a common ordered state space")
    for anchor in (left_favouring_anchor, right_favouring_anchor):
        if anchor.state_ids != left.state_ids:
            raise ValueError("population anchors must use the experiment state space")
    left_values = (
        decision_value(left, problem, left_favouring_anchor.prior),
        decision_value(right, problem, left_favouring_anchor.prior),
    )
    right_values = (
        decision_value(left, problem, right_favouring_anchor.prior),
        decision_value(right, problem, right_favouring_anchor.prior),
    )
    left_gap = left_values[0] - left_values[1]
    right_gap = right_values[1] - right_values[0]
    if left_gap < minimum_value_gap or right_gap < minimum_value_gap:
        raise ValueError("the supplied population anchors do not establish the required ranking reversal")
    supports = (
        sum(value > 0.0 for value in left_favouring_anchor.prior),
        sum(value > 0.0 for value in right_favouring_anchor.prior),
    )
    return AnchoringReversalWitness(
        left_experiment_id=left.experiment_id,
        right_experiment_id=right.experiment_id,
        problem_id=problem.problem_id,
        left_favouring_anchor_id=left_favouring_anchor.anchor_id,
        right_favouring_anchor_id=right_favouring_anchor.anchor_id,
        left_anchor_values=left_values,
        right_anchor_values=right_values,
        minimum_value_gap=min(left_gap, right_gap),
        minimum_anchor_support=min(supports),
        non_degenerate=min(supports) >= minimum_anchor_support,
        interpretation=(
            "The same success functional ranks the experiments differently after a declared population-prior shift; "
            "an unanchored success score is therefore not transportable."
        ),
    )
