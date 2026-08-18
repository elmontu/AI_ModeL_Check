from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .analyzers.attack import clopper_pearson_lower, clopper_pearson_upper
from .decision_theory import DecisionProblem
from .integrity import canonical_json_bytes, sha256_file, verify_source_file
from .incomplete_portfolio import (
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    IncompletePortfolioProblem,
    JointEventBound,
    StatisticalCoverage,
)
from .models import StrictModel


MAX_SIMULTANEOUS_CELLS = 10_000
MIN_ALLOCATED_ALPHA = 1e-8
MAX_ASSURANCE_ALPHA = 0.05


class SourceFileReference(StrictModel):
    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MultinomialStateCounts(StrictModel):
    state_id: str = Field(min_length=1, max_length=256)
    counts: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_are_nonempty(self) -> MultinomialStateCounts:
        if any(value < 0 for value in self.counts):
            raise ValueError("multinomial counts must be non-negative")
        if sum(self.counts) < 1:
            raise ValueError("every multinomial state row needs at least one trial")
        return self


class MultinomialSamplingPlanRelease(StrictModel):
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    observation_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def observations_are_unique(self) -> MultinomialSamplingPlanRelease:
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("sampling-plan observation identifiers must be unique")
        return self


class MultinomialSamplingPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    family_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    portfolio_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    registered_at: datetime
    sampling_model: Literal["iid_multinomial"] = "iid_multinomial"
    state_ids: tuple[str, ...] = Field(min_length=2)
    releases: tuple[MultinomialSamplingPlanRelease, ...] = Field(min_length=1)
    minimum_trials_per_state: int = Field(gt=0)
    selection_scope: str = Field(min_length=1, max_length=4096)
    audit_sample_definition: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def plan_is_complete(self) -> MultinomialSamplingPlan:
        if self.registered_at.utcoffset() is None:
            raise ValueError("sampling-plan registered_at must include a timezone offset")
        if len(set(self.state_ids)) != len(self.state_ids):
            raise ValueError("sampling-plan state identifiers must be unique")
        if len({release.release_id for release in self.releases}) != len(self.releases):
            raise ValueError("sampling-plan release identifiers must be unique")
        cells = sum(len(self.state_ids) * len(value.observation_ids) for value in self.releases)
        if cells > MAX_SIMULTANEOUS_CELLS:
            raise ValueError(
                f"sampling plan exceeds the hard limit of {MAX_SIMULTANEOUS_CELLS} cells"
            )
        return self


class MultinomialReleaseCounts(StrictModel):
    release_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    observation_ids: tuple[str, ...] = Field(min_length=1)
    state_rows: tuple[MultinomialStateCounts, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def release_table_is_rectangular(self) -> MultinomialReleaseCounts:
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("multinomial observation identifiers must be unique")
        if len({row.state_id for row in self.state_rows}) != len(self.state_rows):
            raise ValueError("multinomial state rows must be unique")
        if any(len(row.counts) != len(self.observation_ids) for row in self.state_rows):
            raise ValueError("multinomial counts must align with observation identifiers")
        return self


class MultinomialCountsFile(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    count_file_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    sampling_plan_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    sampling_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    portfolio_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    family_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    sampling_started_at: datetime
    sampling_ended_at: datetime
    audit_sample_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sampling_protocol: str = Field(min_length=1, max_length=4096)
    state_ids: tuple[str, ...] = Field(min_length=2)
    releases: tuple[MultinomialReleaseCounts, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_count_family(self) -> MultinomialCountsFile:
        if self.sampling_started_at.utcoffset() is None or self.sampling_ended_at.utcoffset() is None:
            raise ValueError("multinomial sampling timestamps must include timezone offsets")
        if self.sampling_ended_at < self.sampling_started_at:
            raise ValueError("sampling_ended_at must not precede sampling_started_at")
        if len(set(self.state_ids)) != len(self.state_ids):
            raise ValueError("multinomial state identifiers must be unique")
        if len({release.release_id for release in self.releases}) != len(self.releases):
            raise ValueError("multinomial release identifiers must be unique")
        for release in self.releases:
            if tuple(row.state_id for row in release.state_rows) != self.state_ids:
                raise ValueError(
                    "every release must contain the canonical complete ordered state family"
                )
        cells = sum(len(self.state_ids) * len(value.observation_ids) for value in self.releases)
        if cells > MAX_SIMULTANEOUS_CELLS:
            raise ValueError(
                f"simultaneous family exceeds the hard limit of {MAX_SIMULTANEOUS_CELLS} cells"
            )
        return self


class ErrorBudgetAllocation(StrictModel):
    allocation_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    generation_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    family_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    portfolio_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    sampling_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    alpha: float = Field(ge=MIN_ALLOCATED_ALPHA, le=MAX_ASSURANCE_ALPHA)
    status: Literal["committed"] = "committed"


class AssuranceErrorBudget(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    budget_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    authority: str = Field(min_length=1, max_length=512)
    committed_at: datetime
    period_start: date
    period_end: date
    total_alpha: float = Field(ge=MIN_ALLOCATED_ALPHA, le=MAX_ASSURANCE_ALPHA)
    allocations: tuple[ErrorBudgetAllocation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ledger_is_coherent(self) -> AssuranceErrorBudget:
        if self.committed_at.utcoffset() is None:
            raise ValueError("error-budget committed_at must include a timezone offset")
        if self.period_end < self.period_start:
            raise ValueError("error-budget period_end must not precede period_start")
        if len({value.allocation_id for value in self.allocations}) != len(self.allocations):
            raise ValueError("error-budget allocation identifiers must be unique")
        if len({value.generation_id for value in self.allocations}) != len(self.allocations):
            raise ValueError("an evidence generation may consume only one ledger allocation")
        if len({value.family_id for value in self.allocations}) != len(self.allocations):
            raise ValueError("a pre-declared assurance family may have only one allocation")
        committed = sum(value.alpha for value in self.allocations)
        if committed > self.total_alpha + 1e-15:
            raise ValueError(
                f"committed alpha {committed:.12g} exceeds ledger total {self.total_alpha:.12g}"
            )
        return self


class MultinomialEvidenceRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generation_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    allocation_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    sampling_plan_reference: SourceFileReference
    counts_reference: SourceFileReference
    budget_reference: SourceFileReference
    sampling_model: Literal["iid_multinomial"] = "iid_multinomial"
    family_pre_registered: bool
    all_cells_reported: bool
    selection_process_covered: bool
    assurance_ledger_complete: bool
    selection_scope: str = Field(min_length=1, max_length=4096)


class SimultaneousMultinomialRow(StrictModel):
    release_id: str
    state_id: str
    observation_ids: tuple[str, ...]
    counts: tuple[int, ...]
    trials: int = Field(gt=0)
    lower: tuple[float, ...]
    upper: tuple[float, ...]


class SimultaneousMultinomialEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_type: Literal["simultaneous_multinomial_marginals"] = (
        "simultaneous_multinomial_marginals"
    )
    request: MultinomialEvidenceRequest
    count_file_id: str
    budget_id: str
    family_id: str
    portfolio_id: str
    population_scope_id: str
    threat_id: str
    state_ids: tuple[str, ...]
    method: Literal["bonferroni_two_sided_clopper_pearson"] = (
        "bonferroni_two_sided_clopper_pearson"
    )
    family_alpha: float = Field(gt=0.0, le=MAX_ASSURANCE_ALPHA)
    assurance_wide_alpha: float = Field(gt=0.0, le=MAX_ASSURANCE_ALPHA)
    family_coverage_confidence: float = Field(ge=0.95, lt=1.0)
    assurance_wide_confidence: float = Field(ge=0.95, lt=1.0)
    simultaneous_cell_count: int = Field(gt=0, le=MAX_SIMULTANEOUS_CELLS)
    per_tail_alpha: float = Field(gt=0.0)
    coverage: StatisticalCoverage
    selection_valid: bool
    rows: tuple[SimultaneousMultinomialRow, ...] = Field(min_length=2)
    assumptions: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...]


class MultinomialEvidenceVerification(StrictModel):
    valid: bool
    selection_valid: bool
    coverage_confidence: float = Field(gt=0.0, le=1.0)
    reasons: tuple[str, ...]


class IncompletePortfolioSpecification(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    portfolio_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    population_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threat_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    decision_game_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior: tuple[float, ...]
    decision_problem: DecisionProblem
    coupling_model: CouplingModel
    joint_event_bounds: tuple[JointEventBound, ...] = ()
    prior_evidence: EvidenceReference
    mechanism_assumptions: tuple[str, ...] = Field(min_length=1)
    mechanism_evidence: tuple[EvidenceReference, ...] = Field(min_length=1)


def _load_model(path: Path, model_type):
    try:
        return model_type.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid UTF-8 JSON evidence source: {path}") from exc


def exact_two_sided_binomial_interval(
    successes: int,
    trials: int,
    per_tail_alpha: float,
) -> tuple[float, float]:
    """Exact Clopper--Pearson interval, with a SciPy fast path for portfolio workloads."""
    if trials < 1 or successes < 0 or successes > trials:
        raise ValueError("binomial counts must satisfy 0 <= successes <= trials")
    if not 0.0 < per_tail_alpha < 0.5:
        raise ValueError("per_tail_alpha must lie in (0, 0.5)")
    try:
        from scipy.stats import beta
    except ImportError:  # pragma: no cover - minimal non-portfolio installation
        confidence = 1.0 - per_tail_alpha
        return (
            clopper_pearson_lower(successes, trials, confidence),
            clopper_pearson_upper(successes, trials, confidence),
        )
    lower = 0.0 if successes == 0 else float(
        beta.ppf(per_tail_alpha, successes, trials - successes + 1)
    )
    upper = 1.0 if successes == trials else float(
        beta.ppf(1.0 - per_tail_alpha, successes + 1, trials - successes)
    )
    return lower, upper


def _resolve_sources(
    request: MultinomialEvidenceRequest,
    base_dir: Path,
) -> tuple[
    Path,
    Path,
    Path,
    MultinomialSamplingPlan,
    MultinomialCountsFile,
    AssuranceErrorBudget,
]:
    plan_path = verify_source_file(
        request.sampling_plan_reference.source_path,
        request.sampling_plan_reference.source_sha256,
        base_dir,
    )
    counts_path = verify_source_file(
        request.counts_reference.source_path,
        request.counts_reference.source_sha256,
        base_dir,
    )
    budget_path = verify_source_file(
        request.budget_reference.source_path,
        request.budget_reference.source_sha256,
        base_dir,
    )
    return (
        plan_path,
        counts_path,
        budget_path,
        _load_model(plan_path, MultinomialSamplingPlan),
        _load_model(counts_path, MultinomialCountsFile),
        _load_model(budget_path, AssuranceErrorBudget),
    )


def generate_simultaneous_multinomial_evidence(
    request: MultinomialEvidenceRequest,
    base_dir: Path,
) -> SimultaneousMultinomialEvidence:
    """Build an exact finite-sample simultaneous marginal confidence family."""
    _, _, _, plan, counts, budget = _resolve_sources(request, base_dir)
    allocations = [
        value for value in budget.allocations if value.allocation_id == request.allocation_id
    ]
    if len(allocations) != 1:
        raise ValueError("the requested committed error-budget allocation does not exist exactly once")
    allocation = allocations[0]
    if plan.registered_at > counts.sampling_started_at:
        raise ValueError("sampling plan was not registered before multinomial sampling began")
    if budget.committed_at > counts.sampling_started_at:
        raise ValueError("error budget was not committed before multinomial sampling began")
    if not (
        budget.period_start <= counts.sampling_started_at.date()
        and counts.sampling_ended_at.date() <= budget.period_end
    ):
        raise ValueError("multinomial sampling falls outside the committed error-budget period")
    bindings = {
        "generation_id": request.generation_id,
        "family_id": counts.family_id,
        "portfolio_id": counts.portfolio_id,
        "population_scope_id": counts.population_scope_id,
        "threat_id": counts.threat_id,
        "sampling_plan_sha256": request.sampling_plan_reference.source_sha256,
    }
    for field, expected in bindings.items():
        if getattr(allocation, field) != expected:
            raise ValueError(f"error-budget allocation changes the bound {field}")
    if counts.sampling_plan_id != plan.plan_id:
        raise ValueError("count file changes the registered sampling-plan identifier")
    if counts.sampling_plan_sha256 != request.sampling_plan_reference.source_sha256:
        raise ValueError("count file changes the registered sampling-plan hash")
    for field in ("family_id", "portfolio_id", "population_scope_id", "threat_id", "state_ids"):
        if getattr(counts, field) != getattr(plan, field):
            raise ValueError(f"count file changes sampling-plan field {field}")
    planned_releases = tuple(
        (value.release_id, value.observation_ids) for value in plan.releases
    )
    observed_releases = tuple(
        (value.release_id, value.observation_ids) for value in counts.releases
    )
    if observed_releases != planned_releases:
        raise ValueError("count file changes the registered release/output family")
    if any(
        sum(row.counts) < plan.minimum_trials_per_state
        for release in counts.releases
        for row in release.state_rows
    ):
        raise ValueError("count file does not meet the registered per-state sample-size floor")
    if request.selection_scope != plan.selection_scope:
        raise ValueError("evidence request changes the registered selection scope")

    cell_count = sum(
        len(counts.state_ids) * len(release.observation_ids)
        for release in counts.releases
    )
    per_tail_alpha = allocation.alpha / (2.0 * cell_count)
    if 1.0 - per_tail_alpha >= 1.0:
        raise ValueError("allocated alpha is too small for stable floating-point exact bounds")

    rows: list[SimultaneousMultinomialRow] = []
    for release in counts.releases:
        for state_row in release.state_rows:
            trials = sum(state_row.counts)
            intervals = tuple(
                exact_two_sided_binomial_interval(value, trials, per_tail_alpha)
                for value in state_row.counts
            )
            lower = tuple(value[0] for value in intervals)
            upper = tuple(value[1] for value in intervals)
            rows.append(SimultaneousMultinomialRow(
                release_id=release.release_id,
                state_id=state_row.state_id,
                observation_ids=release.observation_ids,
                counts=state_row.counts,
                trials=trials,
                lower=lower,
                upper=upper,
            ))

    selection_valid = (
        request.family_pre_registered
        and request.all_cells_reported
        and request.selection_process_covered
        and request.assurance_ledger_complete
    )
    limitations = () if selection_valid else tuple(
        message
        for condition, message in (
            (request.family_pre_registered, "assurance family was not pre-registered"),
            (request.all_cells_reported, "not every selected state/release/cell was reported"),
            (
                request.selection_process_covered,
                "the data-dependent selection process is neither covered by the family nor disjoint",
            ),
            (
                request.assurance_ledger_complete,
                "the supplied ledger is not the complete assurance-wide allocation ledger",
            ),
        )
        if not condition
    )
    return SimultaneousMultinomialEvidence(
        request=request,
        count_file_id=counts.count_file_id,
        budget_id=budget.budget_id,
        family_id=counts.family_id,
        portfolio_id=counts.portfolio_id,
        population_scope_id=counts.population_scope_id,
        threat_id=counts.threat_id,
        state_ids=counts.state_ids,
        family_alpha=allocation.alpha,
        assurance_wide_alpha=budget.total_alpha,
        family_coverage_confidence=1.0 - allocation.alpha,
        assurance_wide_confidence=1.0 - budget.total_alpha,
        simultaneous_cell_count=cell_count,
        per_tail_alpha=per_tail_alpha,
        coverage=(
            StatisticalCoverage.SIMULTANEOUS
            if selection_valid
            else StatisticalCoverage.POINTWISE
        ),
        selection_valid=selection_valid,
        rows=tuple(rows),
        assumptions=(
            "within each secret-state row, retained observations are IID draws from one fixed multinomial channel row",
            "the committed ledger contains the complete assurance-wide allocation family",
            "Bonferroni union bounds require no independence between cells, releases, or allocated families",
        ),
        limitations=limitations,
    )


def verify_simultaneous_multinomial_evidence(
    evidence: SimultaneousMultinomialEvidence,
    base_dir: Path,
) -> MultinomialEvidenceVerification:
    """Replay source hashes, the committed allocation, and every exact interval."""
    expected = generate_simultaneous_multinomial_evidence(evidence.request, base_dir)
    reasons: list[str] = []
    if canonical_json_bytes(expected) != canonical_json_bytes(evidence):
        reasons.append("simultaneous multinomial evidence does not replay from raw sources")
    return MultinomialEvidenceVerification(
        valid=not reasons,
        selection_valid=expected.selection_valid,
        coverage_confidence=expected.assurance_wide_confidence,
        reasons=tuple(reasons),
    )


def _relative_source_path(path: Path, output_base_dir: Path) -> str:
    return os.path.relpath(path.resolve(strict=True), output_base_dir.resolve())


def rebase_multinomial_evidence_sources(
    evidence: SimultaneousMultinomialEvidence,
    *,
    current_base_dir: Path,
    output_base_dir: Path,
) -> SimultaneousMultinomialEvidence:
    """Preserve source meaning when writing evidence into another directory."""
    request = evidence.request
    plan_path = verify_source_file(
        request.sampling_plan_reference.source_path,
        request.sampling_plan_reference.source_sha256,
        current_base_dir,
    )
    counts_path = verify_source_file(
        request.counts_reference.source_path,
        request.counts_reference.source_sha256,
        current_base_dir,
    )
    budget_path = verify_source_file(
        request.budget_reference.source_path,
        request.budget_reference.source_sha256,
        current_base_dir,
    )
    rebased = request.model_copy(update={
        "sampling_plan_reference": request.sampling_plan_reference.model_copy(update={
            "source_path": _relative_source_path(plan_path, output_base_dir),
        }),
        "counts_reference": request.counts_reference.model_copy(update={
            "source_path": _relative_source_path(counts_path, output_base_dir),
        }),
        "budget_reference": request.budget_reference.model_copy(update={
            "source_path": _relative_source_path(budget_path, output_base_dir),
        }),
    })
    return evidence.model_copy(update={"request": rebased})


def _rebase_evidence_reference(
    reference: EvidenceReference,
    *,
    current_base_dir: Path,
    output_base_dir: Path,
) -> EvidenceReference:
    source = verify_source_file(reference.source_path, reference.source_sha256, current_base_dir)
    return reference.model_copy(update={
        "source_path": _relative_source_path(source, output_base_dir),
    })


def rebase_portfolio_specification_sources(
    specification: IncompletePortfolioSpecification,
    *,
    current_base_dir: Path,
    output_base_dir: Path,
) -> IncompletePortfolioSpecification:
    return specification.model_copy(update={
        "prior_evidence": _rebase_evidence_reference(
            specification.prior_evidence,
            current_base_dir=current_base_dir,
            output_base_dir=output_base_dir,
        ),
        "mechanism_evidence": tuple(
            _rebase_evidence_reference(
                value,
                current_base_dir=current_base_dir,
                output_base_dir=output_base_dir,
            )
            for value in specification.mechanism_evidence
        ),
    })


def verify_portfolio_specification_evidence(
    specification: IncompletePortfolioSpecification,
    base_dir: Path,
) -> tuple[Path, ...]:
    return tuple(
        verify_source_file(value.source_path, value.source_sha256, base_dir)
        for value in (specification.prior_evidence, *specification.mechanism_evidence)
    )


def compile_multinomial_portfolio_problem(
    evidence: SimultaneousMultinomialEvidence,
    specification: IncompletePortfolioSpecification,
    *,
    evidence_source_path: str,
    evidence_source_sha256: str,
) -> IncompletePortfolioProblem:
    """Compile replayed marginal intervals into the analytic portfolio contract."""
    for field in ("portfolio_id", "population_scope_id", "threat_id"):
        if getattr(evidence, field) != getattr(specification, field):
            raise ValueError(f"multinomial evidence changes specification field {field}")
    if evidence.state_ids != specification.decision_problem.state_ids:
        raise ValueError("multinomial evidence and decision problem use different state spaces")
    if len(specification.prior) != len(evidence.state_ids):
        raise ValueError("portfolio prior does not align with multinomial evidence states")

    grouped: dict[str, list[SimultaneousMultinomialRow]] = {}
    for row in evidence.rows:
        grouped.setdefault(row.release_id, []).append(row)
    releases = []
    coverage_claim = f"coverage:{evidence.coverage.value}"
    for release_id, rows in grouped.items():
        if tuple(row.state_id for row in rows) != evidence.state_ids:
            raise ValueError("multinomial evidence rows are not in canonical state order")
        observation_ids = rows[0].observation_ids
        if any(row.observation_ids != observation_ids for row in rows):
            raise ValueError("multinomial evidence changes an observation alphabet between states")
        releases.append(ConditionalMarginalBounds(
            release_id=release_id,
            observation_ids=observation_ids,
            lower=tuple(row.lower for row in rows),
            upper=tuple(row.upper for row in rows),
            evidence=EvidenceReference(
                evidence_id=f"{evidence.request.generation_id}:{release_id}",
                source_path=evidence_source_path,
                source_sha256=evidence_source_sha256,
                supports=(
                    f"marginal:{release_id}",
                    coverage_claim,
                    f"error-budget:{evidence.budget_id}:{evidence.request.allocation_id}",
                ),
            ),
        ))

    return IncompletePortfolioProblem(
        portfolio_id=specification.portfolio_id,
        population_scope_id=specification.population_scope_id,
        population_scope_sha256=specification.population_scope_sha256,
        threat_id=specification.threat_id,
        decision_game_sha256=specification.decision_game_sha256,
        state_ids=evidence.state_ids,
        prior=specification.prior,
        releases=tuple(releases),
        decision_problem=specification.decision_problem,
        coupling_model=specification.coupling_model,
        joint_event_bounds=specification.joint_event_bounds,
        coverage=evidence.coverage,
        coverage_confidence=evidence.assurance_wide_confidence,
        selection_scope=evidence.request.selection_scope,
        prior_evidence=specification.prior_evidence,
        mechanism_assumptions=specification.mechanism_assumptions,
        mechanism_evidence=specification.mechanism_evidence,
    )


def verify_problem_against_multinomial_evidence(
    problem: IncompletePortfolioProblem,
    evidence: SimultaneousMultinomialEvidence,
    evidence_path: Path,
) -> None:
    """Reject any compiled problem that changes generated bounds or coverage semantics."""
    verification = verify_simultaneous_multinomial_evidence(evidence, evidence_path.parent)
    if not verification.valid:
        raise ValueError("; ".join(verification.reasons))
    if (
        problem.portfolio_id != evidence.portfolio_id
        or problem.population_scope_id != evidence.population_scope_id
        or problem.threat_id != evidence.threat_id
        or problem.state_ids != evidence.state_ids
    ):
        raise ValueError("portfolio problem changes the statistical evidence scope")
    expected = {
        row.release_id: []
        for row in evidence.rows
    }
    for row in evidence.rows:
        expected[row.release_id].append(row)
    if set(expected) != {release.release_id for release in problem.releases}:
        raise ValueError("portfolio problem omits or adds a statistically assessed release")
    for release in problem.releases:
        rows = expected[release.release_id]
        if (
            release.observation_ids != rows[0].observation_ids
            or release.lower != tuple(row.lower for row in rows)
            or release.upper != tuple(row.upper for row in rows)
        ):
            raise ValueError(
                f"portfolio problem changes generated intervals for {release.release_id}"
            )
        required = f"error-budget:{evidence.budget_id}:{evidence.request.allocation_id}"
        if required not in release.evidence.supports:
            raise ValueError(f"portfolio problem omits the committed error budget for {release.release_id}")
    if (
        problem.coverage is not evidence.coverage
        or problem.selection_valid != evidence.selection_valid
        or abs(problem.coverage_confidence - evidence.assurance_wide_confidence) > 1e-15
        or problem.selection_scope != evidence.request.selection_scope
    ):
        raise ValueError("portfolio problem changes generated selection-coverage semantics")
