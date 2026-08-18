from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .decision_theory import (
    FiniteExperiment,
    GarblingCertificate,
    GarblingVerification,
    decision_value,
    exact_guess_problem,
    verify_garbling,
)
from .integrity import (
    canonical_json_bytes,
    sign_canonical,
    sha256_bytes,
    verify_canonical_signature,
    verify_provenance_binding,
    verify_signed_manifest,
    verify_source_file,
)
from .incomplete_portfolio import (
    AnalyticPortfolioEvidenceEntry,
    verify_analytic_portfolio,
    verify_portfolio_problem_evidence,
    decimal_fraction,
    outward_rounded_fraction,
    verified_upper_fraction,
)
from .models import (
    AssessmentReport,
    InterfaceContract,
    OverallVerdict,
    SignedManifest,
    StrictModel,
    Verdict,
)
from .version import VERSION


class OptimizationOutcome(StrEnum):
    RELEASE_AS_PROPOSED = "release_as_proposed"
    RELEASE_WITH_CONTROLS = "release_with_controls"
    REDESIGN_REQUIRED = "redesign_required"
    REJECT = "reject"


class TrustProfile(StrEnum):
    COOPERATIVE = "cooperative"
    SEPARATED_ASSESSOR = "separated_assessor"
    ADVERSARIAL_SUPPLY_CHAIN = "adversarial_supply_chain"


class PortfolioAssuranceStatus(StrEnum):
    ANALYTICALLY_COMPOSED = "analytically_composed"
    DIRECTLY_JOINT_ASSESSED = "directly_joint_assessed"
    UNASSESSED = "unassessed"


class SearchSpaceStatus(StrEnum):
    CANDIDATE_SET_ONLY = "candidate_set_only"
    CERTIFIED_EXHAUSTIVE = "certified_exhaustive"


class ControlType(StrEnum):
    INFORMATION_REDUCTION = "information_reduction"
    ACCESS_GOVERNANCE = "access_governance"


class AssessmentReportReference(StrictModel):
    report_path: str = Field(min_length=1)
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_manifest_path: str | None = None
    signed_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    assessor_public_key_path: str | None = None
    accepted_signer_key_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def signature_reference_is_complete(self) -> AssessmentReportReference:
        supplied = (
            self.signed_manifest_path,
            self.signed_manifest_sha256,
            self.assessor_public_key_path,
        )
        if any(value is not None for value in supplied) and any(value is None for value in supplied):
            raise ValueError("signed assessment reference requires manifest, manifest hash, and public key")
        if self.signed_manifest_path is not None and not self.accepted_signer_key_ids:
            raise ValueError("signed assessment reference requires an accepted signer-key allowlist")
        return self


class UtilityCertificate(StrictModel):
    configuration_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    population_scope_sha256s: tuple[str, ...] = Field(min_length=1)
    evaluation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metric: str = Field(min_length=1, max_length=256)
    lower_bound: float = Field(ge=0.0, le=1.0)
    point_estimate: float = Field(ge=0.0, le=1.0)
    minimum_required: float = Field(ge=0.0, le=1.0)
    evaluation_population: str = Field(min_length=1, max_length=2048)
    confidence: float = Field(gt=0.5, lt=1.0)
    uncertainty_method: str = Field(min_length=1, max_length=1024)
    audit_disjoint: bool
    raw_evidence_retained: bool
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def interval_and_requirement_are_coherent(self) -> UtilityCertificate:
        if self.lower_bound > self.point_estimate:
            raise ValueError("utility lower bound cannot exceed its point estimate")
        if len(set(self.population_scope_sha256s)) != len(self.population_scope_sha256s):
            raise ValueError("utility population-scope hashes must be unique")
        return self


class ReleaseControl(StrictModel):
    control_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    control_type: ControlType
    kind: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2048)
    changes_information_structure: bool
    credited_for_privacy: bool = True
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interface_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_until: datetime
    evidence_path: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def privacy_credit_is_semantic(self) -> ReleaseControl:
        if self.valid_until.utcoffset() is None:
            raise ValueError("control valid_until must include a timezone offset")
        if self.credited_for_privacy and (
            self.control_type is not ControlType.INFORMATION_REDUCTION
            or not self.changes_information_structure
        ):
            raise ValueError("privacy credit requires a control that changes the information structure")
        return self


class PortfolioCertificate(StrictModel):
    status: PortfolioAssuranceStatus
    composition_domain_id: str = Field(min_length=3, max_length=256)
    population_secret_pairs: tuple[str, ...] = Field(min_length=1)
    registry_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_release_ids: tuple[str, ...] = ()
    method: str = Field(min_length=1, max_length=2048)
    joint_upper_bounds: dict[str, float] = Field(default_factory=dict)
    joint_experiment_ids: dict[str, str] = Field(default_factory=dict)
    evidence_path: str | None = None
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def evidence_matches_status(self) -> PortfolioCertificate:
        if len(set(self.population_secret_pairs)) != len(self.population_secret_pairs):
            raise ValueError("portfolio population-secret pairs must be unique")
        if len(set(self.registered_release_ids)) != len(self.registered_release_ids):
            raise ValueError("registered portfolio release identifiers must be unique")
        assessed = self.status is not PortfolioAssuranceStatus.UNASSESSED
        if assessed != (self.evidence_path is not None and self.evidence_sha256 is not None):
            raise ValueError("assessed portfolio states require evidence; unassessed state must not cite it")
        if assessed and set(self.joint_upper_bounds) != set(self.population_secret_pairs):
            raise ValueError("assessed portfolio evidence requires one joint upper bound per population-secret pair")
        if not assessed and self.joint_upper_bounds:
            raise ValueError("unassessed portfolio state cannot claim joint upper bounds")
        if any(not 0.0 <= value <= 1.0 for value in self.joint_upper_bounds.values()):
            raise ValueError("portfolio joint upper bounds must be probabilities in [0,1]")
        if self.status is PortfolioAssuranceStatus.DIRECTLY_JOINT_ASSESSED:
            if set(self.joint_experiment_ids) != set(self.population_secret_pairs):
                raise ValueError("direct joint assessment requires one replay experiment per population-secret pair")
        elif self.joint_experiment_ids:
            raise ValueError("joint experiment identifiers are only valid for direct joint assessment")
        if self.status is PortfolioAssuranceStatus.ANALYTICALLY_COMPOSED and not self.registered_release_ids:
            raise ValueError("analytic portfolio assessment requires the complete registered release identifiers")
        return self


class SearchSpaceCertificate(StrictModel):
    method: str = Field(min_length=1, max_length=2048)
    configuration_ids: tuple[str, ...] = Field(min_length=1)
    evidence_path: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ThreatExperimentBinding(StrictModel):
    threat_id: str
    assessed_experiment_id: str
    released_experiment_id: str
    substitution_certificate_id: str | None = None

    @model_validator(mode="after")
    def changed_surface_has_certificate_reference(self) -> ThreatExperimentBinding:
        unchanged = self.assessed_experiment_id == self.released_experiment_id
        if unchanged and self.substitution_certificate_id is not None:
            raise ValueError("unchanged release surface must not provide a substitution certificate")
        return self


class ReleaseConfiguration(StrictModel):
    configuration_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str = Field(min_length=1, max_length=256)
    is_proposed_configuration: bool
    assessment: AssessmentReportReference
    release_artifact_path: str = Field(min_length=1)
    release_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_interface: InterfaceContract
    utility: UtilityCertificate
    implementation_cost: float = Field(ge=0.0)
    controls: tuple[ReleaseControl, ...] = ()
    threat_experiments: tuple[ThreatExperimentBinding, ...] = Field(min_length=1)
    portfolio: PortfolioCertificate
    notes: str = ""

    @model_validator(mode="after")
    def configuration_identifiers_are_unique(self) -> ReleaseConfiguration:
        control_ids = [control.control_id for control in self.controls]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("release-control identifiers must be unique within a configuration")
        threat_ids = [binding.threat_id for binding in self.threat_experiments]
        if len(threat_ids) != len(set(threat_ids)):
            raise ValueError("a configuration may bind each threat only once")
        if self.utility.configuration_id != self.configuration_id:
            raise ValueError("utility certificate is bound to another configuration")
        return self


class OptimizationRequest(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    optimization_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    objective: str = Field(
        default="utility feasibility, then Blackwell-minimal disclosure, then cost and utility tie-breaks",
        min_length=1,
        max_length=2048,
    )
    trust_profile: TrustProfile
    authorization_expires_at: datetime
    portfolio_registry_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiments: tuple[FiniteExperiment, ...] = Field(min_length=1)
    garbling_certificates: tuple[GarblingCertificate, ...] = ()
    configurations: tuple[ReleaseConfiguration, ...] = Field(min_length=1)
    search_space_status: SearchSpaceStatus = SearchSpaceStatus.CANDIDATE_SET_ONLY
    search_space_certificate: SearchSpaceCertificate | None = None

    @model_validator(mode="after")
    def optimization_identifiers_are_unique(self) -> OptimizationRequest:
        if self.authorization_expires_at.utcoffset() is None:
            raise ValueError("authorization_expires_at must include a timezone offset")
        collections = (
            ("experiment", [item.experiment_id for item in self.experiments]),
            ("garbling certificate", [item.certificate_id for item in self.garbling_certificates]),
            ("configuration", [item.configuration_id for item in self.configurations]),
        )
        for label, identifiers in collections:
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} identifiers must be unique")
        proposed = [item for item in self.configurations if item.is_proposed_configuration]
        if len(proposed) > 1:
            raise ValueError("at most one configuration may be marked as proposed")
        exhaustive = self.search_space_status is SearchSpaceStatus.CERTIFIED_EXHAUSTIVE
        if exhaustive != (self.search_space_certificate is not None):
            raise ValueError("certified exhaustive search requires an enumeration certificate")
        return self


class CandidateEvaluation(StrictModel):
    configuration_id: str
    feasible: bool
    assessment_verdict: OverallVerdict
    utility_margin: float
    implementation_cost: float
    substitution_penalties: dict[str, float]
    reasons: tuple[str, ...]


class OptimizationReport(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    optimization_id: str
    created_at: datetime
    expires_at: datetime
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_profile: TrustProfile
    portfolio_registry_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: OptimizationOutcome
    selected_configuration_id: str | None
    selected_configuration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_assessment_id: str | None
    selected_assessment_report_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_release_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_release_interface_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_portfolio_status: PortfolioAssuranceStatus | None = None
    selected_control_ids: tuple[str, ...] = ()
    fail_safe_gate_passed: bool
    assurance_frontier_configuration_ids: tuple[str, ...]
    candidate_evaluations: tuple[CandidateEvaluation, ...]
    selection_rule: str
    reasons: tuple[str, ...]
    engine_version: str

    @model_validator(mode="after")
    def selected_release_matches_gate(self) -> OptimizationReport:
        for value in (self.created_at, self.expires_at):
            if value.utcoffset() is None:
                raise ValueError("optimization report timestamps must include timezone offsets")
        selected = (
            self.selected_configuration_id,
            self.selected_configuration_sha256,
            self.selected_assessment_id,
            self.selected_assessment_report_sha256,
            self.selected_release_artifact_sha256,
            self.selected_release_interface_sha256,
            self.selected_portfolio_status,
        )
        release_outcome = self.outcome in {
            OptimizationOutcome.RELEASE_AS_PROPOSED,
            OptimizationOutcome.RELEASE_WITH_CONTROLS,
        }
        if self.fail_safe_gate_passed != release_outcome:
            raise ValueError("release outcome and fail-safe gate status disagree")
        if self.fail_safe_gate_passed and any(value is None for value in selected):
            raise ValueError("a passing gate requires every selected-release binding")
        if not self.fail_safe_gate_passed and (
            any(value is not None for value in selected) or self.selected_control_ids
        ):
            raise ValueError("a failing gate must not authorize a release or controls")
        return self


class SignedOptimizationManifest(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    optimization_id: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_profile: TrustProfile
    portfolio_registry_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: OptimizationOutcome
    selected_configuration_id: str | None
    selected_configuration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_assessment_id: str | None
    selected_assessment_report_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_release_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_release_interface_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selected_portfolio_status: PortfolioAssuranceStatus | None = None
    selected_control_ids: tuple[str, ...] = ()
    fail_safe_gate_passed: bool
    created_at: datetime
    expires_at: datetime
    signer_key_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    canonicalization: Literal["MRA-PY-JSON-1"] = "MRA-PY-JSON-1"
    signature_b64: str = Field(min_length=1)

    @model_validator(mode="after")
    def release_binding_matches_gate(self) -> SignedOptimizationManifest:
        selected = (
            self.selected_configuration_id,
            self.selected_configuration_sha256,
            self.selected_assessment_id,
            self.selected_assessment_report_sha256,
            self.selected_release_artifact_sha256,
            self.selected_release_interface_sha256,
            self.selected_portfolio_status,
        )
        if self.fail_safe_gate_passed and any(value is None for value in selected):
            raise ValueError("a passing optimization manifest requires every selected-release binding")
        if not self.fail_safe_gate_passed and any(value is not None for value in selected):
            raise ValueError("a failing optimization manifest must not authorize a selected release")
        return self


def build_signed_optimization_manifest(
    report: OptimizationReport,
    private_key_path: Path,
) -> SignedOptimizationManifest:
    unsigned = {
        "schema_version": "2.0",
        "optimization_id": report.optimization_id,
        "request_sha256": report.request_sha256,
        "report_sha256": sha256_bytes(canonical_json_bytes(report)),
        "policy_sha256": report.policy_sha256,
        "trust_profile": report.trust_profile,
        "portfolio_registry_head_sha256": report.portfolio_registry_head_sha256,
        "outcome": report.outcome,
        "selected_configuration_id": report.selected_configuration_id,
        "selected_configuration_sha256": report.selected_configuration_sha256,
        "selected_assessment_id": report.selected_assessment_id,
        "selected_assessment_report_sha256": report.selected_assessment_report_sha256,
        "selected_release_artifact_sha256": report.selected_release_artifact_sha256,
        "selected_release_interface_sha256": report.selected_release_interface_sha256,
        "selected_portfolio_status": report.selected_portfolio_status,
        "selected_control_ids": report.selected_control_ids,
        "fail_safe_gate_passed": report.fail_safe_gate_passed,
        "created_at": report.created_at,
        "expires_at": report.expires_at,
        "signature_algorithm": "Ed25519",
        "canonicalization": "MRA-PY-JSON-1",
    }
    unsigned = {key: value for key, value in unsigned.items() if value is not None}
    signer_id, signature = sign_canonical(unsigned, private_key_path)
    return SignedOptimizationManifest(**unsigned, signer_key_id=signer_id, signature_b64=signature)


def verify_signed_optimization_manifest(
    manifest: SignedOptimizationManifest,
    report: OptimizationReport,
    public_key_path: Path,
) -> None:
    bindings = {
        "optimization_id": report.optimization_id,
        "request_sha256": report.request_sha256,
        "policy_sha256": report.policy_sha256,
        "trust_profile": report.trust_profile,
        "portfolio_registry_head_sha256": report.portfolio_registry_head_sha256,
        "outcome": report.outcome,
        "selected_configuration_id": report.selected_configuration_id,
        "selected_configuration_sha256": report.selected_configuration_sha256,
        "selected_assessment_id": report.selected_assessment_id,
        "selected_assessment_report_sha256": report.selected_assessment_report_sha256,
        "selected_release_artifact_sha256": report.selected_release_artifact_sha256,
        "selected_release_interface_sha256": report.selected_release_interface_sha256,
        "selected_portfolio_status": report.selected_portfolio_status,
        "selected_control_ids": report.selected_control_ids,
        "fail_safe_gate_passed": report.fail_safe_gate_passed,
        "created_at": report.created_at,
        "expires_at": report.expires_at,
    }
    for field, expected in bindings.items():
        if getattr(manifest, field) != expected:
            raise ValueError(f"optimization manifest {field} does not match the report")
    if manifest.report_sha256 != sha256_bytes(canonical_json_bytes(report)):
        raise ValueError("optimization manifest does not bind this report")
    if manifest.expires_at <= datetime.now(timezone.utc):
        raise ValueError("optimization authorization has expired")
    unsigned = manifest.model_dump(mode="json", exclude={"signer_key_id", "signature_b64"}, exclude_none=True)
    verify_canonical_signature(
        unsigned,
        signer_id=manifest.signer_key_id,
        signature_b64=manifest.signature_b64,
        public_key_path=public_key_path,
    )


class ReleaseOptimizer:
    """Certificate-backed inner approximation to the zero-error release gate.

    Verified ceilings, utility floors, controls, and portfolio certificates compile
    submitted evidence into sufficient feasibility checks. Conservative certificates
    preserve soundness but need not preserve release completeness. Blackwell
    minimization and cost/utility tie-breaks run only after those checks have passed.
    """

    def optimize(self, request: OptimizationRequest, base_dir: Path) -> OptimizationReport:
        now = datetime.now(timezone.utc)
        if request.authorization_expires_at <= now:
            raise ValueError("requested release authorization is already expired")
        if request.trust_profile is TrustProfile.ADVERSARIAL_SUPPLY_CHAIN:
            raise ValueError(
                "adversarial_supply_chain is unsupported without sandboxed independent artifact replay; "
                "the gate refuses to downgrade this trust boundary"
            )

        experiments = {item.experiment_id: item for item in request.experiments}
        certificates = {item.certificate_id: item for item in request.garbling_certificates}
        verifications: dict[str, GarblingVerification] = {}
        exact_edges: dict[str, set[str]] = defaultdict(set)
        for certificate in request.garbling_certificates:
            try:
                dominant = experiments[certificate.dominant_experiment_id]
                dominated = experiments[certificate.dominated_experiment_id]
            except KeyError as exc:
                raise ValueError(f"garbling certificate references unknown experiment: {exc.args[0]}") from exc
            verification = verify_garbling(dominant, dominated, certificate)
            if not verification.valid:
                raise ValueError(
                    f"garbling certificate {certificate.certificate_id} failed replay: {verification.reasons}"
                )
            verifications[certificate.certificate_id] = verification
            if verification.maximum_row_total_variation <= certificate.numerical_tolerance:
                exact_edges[dominant.experiment_id].add(dominated.experiment_id)

        self._verify_search_space(request, base_dir)
        reports: dict[str, AssessmentReport] = {}
        evaluations: list[CandidateEvaluation] = []
        policy_hashes: set[str] = set()
        expiries = [request.authorization_expires_at]
        for configuration in request.configurations:
            report = self._load_assessment(configuration.assessment, request.trust_profile, base_dir)
            reports[configuration.configuration_id] = report
            policy_hashes.add(report.policy_sha256)
            if report.release_expires_at is not None:
                expiries.append(report.release_expires_at)
            if report.policy_expires_at is not None:
                expiries.append(report.policy_expires_at)
            verify_source_file(
                configuration.release_artifact_path,
                configuration.release_artifact_sha256,
                base_dir,
            )
            self._verify_utility(configuration, report, base_dir)
            self._verify_controls(configuration, base_dir)
            rational_portfolio_bounds = self._verify_portfolio(
                configuration,
                report,
                experiments,
                request.portfolio_registry_head_sha256,
                base_dir,
            )
            expiries.extend(control.valid_until for control in configuration.controls)
            if configuration.release_interface.llm_protocol is not None:
                expiries.append(configuration.release_interface.llm_protocol.valid_until)
            evaluations.append(
                self._evaluate_configuration(
                    configuration,
                    report,
                    experiments,
                    certificates,
                    verifications,
                    request.portfolio_registry_head_sha256,
                    now,
                    rational_portfolio_bounds,
                )
            )
        if len(policy_hashes) != 1:
            raise ValueError("all release configurations must be assessed under the same policy hash")

        feasible_ids = {item.configuration_id for item in evaluations if item.feasible}
        exact_reachability = self._transitive_reachability(experiments, exact_edges)
        frontier = tuple(
            configuration.configuration_id
            for configuration in request.configurations
            if configuration.configuration_id in feasible_ids
            and not any(
                other.configuration_id != configuration.configuration_id
                and other.configuration_id in feasible_ids
                and self._strictly_less_informative(other, configuration, exact_reachability)
                for other in request.configurations
            )
        )
        frontier_set = set(frontier)
        candidates = [item for item in request.configurations if item.configuration_id in frontier_set]
        selected: ReleaseConfiguration | None = None
        if candidates:
            selected = min(
                candidates,
                key=lambda item: (
                    item.implementation_cost,
                    -item.utility.lower_bound,
                    not item.is_proposed_configuration,
                    item.configuration_id,
                ),
            )
            outcome = (
                OptimizationOutcome.RELEASE_AS_PROPOSED
                if selected.is_proposed_configuration and not selected.controls
                else OptimizationOutcome.RELEASE_WITH_CONTROLS
            )
            reasons = (
                f"selected {selected.configuration_id} from the utility-qualified Blackwell-minimal set",
                "cost and certified utility were used only after privacy, utility and information-minimality gates",
            )
        else:
            outcome = (
                OptimizationOutcome.REJECT
                if request.search_space_status is SearchSpaceStatus.CERTIFIED_EXHAUSTIVE
                else OptimizationOutcome.REDESIGN_REQUIRED
            )
            reasons = (
                "no evaluated configuration passed the fail-safe release gate",
                (
                    "a replayed enumeration certificate establishes the declared search space as exhaustive"
                    if request.search_space_status is SearchSpaceStatus.CERTIFIED_EXHAUSTIVE
                    else "only a candidate set was evaluated; construct and assess another mitigation configuration"
                ),
            )
        expires_at = min(expiries)
        if selected is not None:
            selected_report = reports[selected.configuration_id]
            selected_expiries = [request.authorization_expires_at]
            selected_expiries.extend(
                value for value in (selected_report.release_expires_at, selected_report.policy_expires_at)
                if value is not None
            )
            selected_expiries.extend(control.valid_until for control in selected.controls)
            if selected.release_interface.llm_protocol is not None:
                selected_expiries.append(selected.release_interface.llm_protocol.valid_until)
            expires_at = min(selected_expiries)
        return OptimizationReport(
            optimization_id=request.optimization_id,
            created_at=now,
            expires_at=expires_at,
            request_sha256=sha256_bytes(canonical_json_bytes(request)),
            policy_sha256=next(iter(policy_hashes)),
            trust_profile=request.trust_profile,
            portfolio_registry_head_sha256=request.portfolio_registry_head_sha256,
            outcome=outcome,
            selected_configuration_id=selected.configuration_id if selected else None,
            selected_configuration_sha256=(
                sha256_bytes(canonical_json_bytes(selected)) if selected else None
            ),
            selected_assessment_id=(reports[selected.configuration_id].assessment_id if selected else None),
            selected_assessment_report_sha256=(selected.assessment.report_sha256 if selected else None),
            selected_release_artifact_sha256=(selected.release_artifact_sha256 if selected else None),
            selected_release_interface_sha256=(
                sha256_bytes(canonical_json_bytes(selected.release_interface)) if selected else None
            ),
            selected_portfolio_status=(selected.portfolio.status if selected else None),
            selected_control_ids=(tuple(control.control_id for control in selected.controls) if selected else ()),
            fail_safe_gate_passed=selected is not None,
            assurance_frontier_configuration_ids=frontier,
            candidate_evaluations=tuple(evaluations),
            selection_rule=(
                "privacy and utility feasibility; exact Blackwell-minimal information surface; "
                "minimum implementation cost; maximum utility lower bound; stable identifier"
            ),
            reasons=reasons,
            engine_version=VERSION,
        )

    @staticmethod
    def _load_assessment(
        reference: AssessmentReportReference,
        trust_profile: TrustProfile,
        base_dir: Path,
    ) -> AssessmentReport:
        report_path = verify_source_file(reference.report_path, reference.report_sha256, base_dir)
        report = AssessmentReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        expected_scope_hashes = {
            scope.scope_id: sha256_bytes(canonical_json_bytes(scope))
            for scope in report.population_scopes
        }
        if report.population_scope_sha256s != expected_scope_hashes:
            raise ValueError("assessment report contains inconsistent population-scope hashes")
        interface_hash = sha256_bytes(canonical_json_bytes(report.release_interface))
        for decision in report.decisions:
            if decision.population_scope_sha256 != expected_scope_hashes.get(decision.population_scope_id):
                raise ValueError(f"assessment decision {decision.threat_id} is bound to another population")
            if decision.assessed_interface_sha256 != interface_hash:
                raise ValueError(f"assessment decision {decision.threat_id} is bound to another interface")
            if decision.assessed_artifact_sha256 != report.artifact_sha256:
                raise ValueError(f"assessment decision {decision.threat_id} is bound to another artifact")
        if trust_profile is TrustProfile.SEPARATED_ASSESSOR:
            if reference.signed_manifest_path is None:
                raise ValueError("separated_assessor trust requires a signed assessment manifest")
            assert reference.signed_manifest_sha256 is not None
            assert reference.assessor_public_key_path is not None
            manifest_path = verify_source_file(
                reference.signed_manifest_path,
                reference.signed_manifest_sha256,
                base_dir,
            )
            manifest = SignedManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
            public_key = Path(reference.assessor_public_key_path)
            if not public_key.is_absolute():
                public_key = base_dir / public_key
            verify_signed_manifest(manifest, report, public_key.resolve(strict=True))
            if manifest.signer_key_id not in reference.accepted_signer_key_ids:
                raise ValueError("assessment signer is not in the accepted assessor-key allowlist")
        return report

    @staticmethod
    def _verify_utility(configuration: ReleaseConfiguration, report: AssessmentReport, base_dir: Path) -> None:
        utility = configuration.utility
        source = verify_source_file(utility.source_path, utility.source_sha256, base_dir)
        verify_provenance_binding(
            utility,
            source,
            (
                "configuration_id", "artifact_sha256", "interface_sha256",
                "population_scope_sha256s", "evaluation_split_sha256", "metric",
                "lower_bound", "point_estimate", "minimum_required", "evaluation_population",
                "confidence", "uncertainty_method", "audit_disjoint", "raw_evidence_retained",
            ),
        )
        interface_hash = sha256_bytes(canonical_json_bytes(configuration.release_interface))
        if utility.artifact_sha256 != configuration.release_artifact_sha256:
            raise ValueError(f"utility for {configuration.configuration_id} is bound to another artifact")
        if utility.interface_sha256 != interface_hash:
            raise ValueError(f"utility for {configuration.configuration_id} is bound to another interface")
        expected_scopes = tuple(sorted(report.population_scope_sha256s.values()))
        if tuple(sorted(utility.population_scope_sha256s)) != expected_scopes:
            raise ValueError(f"utility for {configuration.configuration_id} is bound to another population")

    @staticmethod
    def _verify_controls(configuration: ReleaseConfiguration, base_dir: Path) -> None:
        interface_hash = sha256_bytes(canonical_json_bytes(configuration.release_interface))
        for control in configuration.controls:
            source = verify_source_file(control.evidence_path, control.evidence_sha256, base_dir)
            verify_provenance_binding(
                control,
                source,
                (
                    "control_id", "control_type", "kind", "description",
                    "changes_information_structure", "credited_for_privacy",
                    "artifact_sha256", "interface_sha256", "valid_until",
                ),
            )
            if control.artifact_sha256 != configuration.release_artifact_sha256:
                raise ValueError(f"control {control.control_id} is bound to another artifact")
            if control.interface_sha256 != interface_hash:
                raise ValueError(f"control {control.control_id} is bound to another interface")

    @staticmethod
    def _verify_portfolio(
        configuration: ReleaseConfiguration,
        report: AssessmentReport,
        experiments: dict[str, FiniteExperiment],
        registry_head_sha256: str,
        base_dir: Path,
    ) -> dict[str, Fraction]:
        portfolio = configuration.portfolio
        rational_bounds: dict[str, Fraction] = {}
        if portfolio.registry_head_sha256 != registry_head_sha256:
            raise ValueError(f"portfolio record for {configuration.configuration_id} uses another registry head")
        expected_pairs = tuple(sorted(
            f"{decision.population_scope_id}|{decision.threat_id}"
            for decision in report.decisions
            if decision.mandatory
        ))
        if tuple(sorted(portfolio.population_secret_pairs)) != expected_pairs:
            raise ValueError(f"portfolio record for {configuration.configuration_id} omits a population-secret pair")
        if portfolio.status is PortfolioAssuranceStatus.UNASSESSED:
            return rational_bounds
        assert portfolio.evidence_path is not None and portfolio.evidence_sha256 is not None
        source = verify_source_file(portfolio.evidence_path, portfolio.evidence_sha256, base_dir)
        verify_provenance_binding(
            portfolio,
            source,
            (
                "status", "composition_domain_id", "population_secret_pairs",
                "registry_head_sha256", "registered_release_ids", "method",
                "joint_upper_bounds", "joint_experiment_ids",
            ),
        )
        released_experiments = {
            binding.threat_id: experiments[binding.released_experiment_id]
            for binding in configuration.threat_experiments
        }
        if portfolio.status is PortfolioAssuranceStatus.DIRECTLY_JOINT_ASSESSED:
            decisions = {
                f"{decision.population_scope_id}|{decision.threat_id}": decision
                for decision in report.decisions
                if decision.mandatory
            }
            for pair, experiment_id in portfolio.joint_experiment_ids.items():
                experiment = experiments.get(experiment_id)
                if experiment is None:
                    raise ValueError(f"portfolio pair {pair} references unknown joint experiment {experiment_id}")
                decision = decisions[pair]
                if experiment.threat_id != decision.threat_id:
                    raise ValueError(f"joint experiment for {pair} uses another threat")
                if experiment.population_scope_id != decision.population_scope_id:
                    raise ValueError(f"joint experiment for {pair} uses another population")
                if experiment.decision_game_sha256 != decision.decision_game_sha256:
                    raise ValueError(f"joint experiment for {pair} changes or omits the decision game")
                released = released_experiments[decision.threat_id]
                if experiment.state_ids != released.state_ids or experiment.prior != released.prior:
                    raise ValueError(
                        f"joint experiment for {pair} changes the registered secret states or prior"
                    )
                exact = ReleaseOptimizer._finite_success_metric(
                    experiment,
                    decision_metric=decision.decision_metric,
                )
                claimed = portfolio.joint_upper_bounds[pair]
                if abs(exact - claimed) > 1e-10:
                    raise ValueError(
                        f"portfolio upper bound for {pair} does not replay: claimed {claimed:.6g}, exact {exact:.6g}"
                    )
        elif portfolio.status is PortfolioAssuranceStatus.ANALYTICALLY_COMPOSED:
            payload = json.loads(source.read_text(encoding="utf-8"))
            raw_assessments = payload.get("analytic_assessments")
            if not isinstance(raw_assessments, dict):
                raise ValueError("analytic portfolio evidence requires an analytic_assessments object")
            if set(raw_assessments) != set(portfolio.population_secret_pairs):
                raise ValueError("analytic portfolio evidence must cover every population-secret pair exactly")
            decisions = {
                f"{decision.population_scope_id}|{decision.threat_id}": decision
                for decision in report.decisions
                if decision.mandatory
            }
            for pair, raw_entry in raw_assessments.items():
                entry = AnalyticPortfolioEvidenceEntry.model_validate(raw_entry)
                problem = entry.problem
                decision = decisions[pair]
                if f"{problem.population_scope_id}|{problem.threat_id}" != pair:
                    raise ValueError(f"analytic portfolio problem for {pair} is bound to another scope or threat")
                if problem.decision_game_sha256 != decision.decision_game_sha256:
                    raise ValueError(f"analytic portfolio problem for {pair} changes the decision game")
                if problem.population_scope_sha256 != decision.population_scope_sha256:
                    raise ValueError(f"analytic portfolio problem for {pair} changes the population snapshot")
                if {release.release_id for release in problem.releases} != set(portfolio.registered_release_ids):
                    raise ValueError(
                        f"analytic portfolio problem for {pair} omits or adds a registered release"
                    )
                released = released_experiments[decision.threat_id]
                if problem.state_ids != released.state_ids or problem.prior != released.prior:
                    raise ValueError(
                        f"analytic portfolio problem for {pair} changes the registered secret states or prior"
                    )
                verify_portfolio_problem_evidence(problem, base_dir)
                exact_problem = exact_guess_problem(problem.state_ids, problem.decision_problem.problem_id)
                if (
                    problem.decision_problem.state_ids != exact_problem.state_ids
                    or problem.decision_problem.action_ids != exact_problem.action_ids
                    or problem.decision_problem.gain != exact_problem.gain
                ):
                    raise ValueError(
                        f"analytic portfolio problem for {pair} must use the canonical exact-guess gain"
                    )
                if decision.decision_metric == "worst_observation_success":
                    raise ValueError(
                        "analytic incomplete-portfolio certificates do not yet implement "
                        "worst_observation_success"
                    )
                supported_metrics = {
                    "bayes_linkage_success",
                    "incremental_bayes_linkage_success",
                    "equal_prior_membership_success",
                    "finite_secret_exact_guess_success",
                }
                if decision.decision_metric not in supported_metrics:
                    raise ValueError(
                        f"analytic incomplete-portfolio certificates do not implement "
                        f"decision metric {decision.decision_metric!r}"
                    )
                if decision.decision_metric == "equal_prior_membership_success" and any(
                    abs(value - 1.0 / len(problem.prior)) > 1e-10 for value in problem.prior
                ):
                    raise ValueError("equal-prior membership certificates require a uniform prior")
                verification = verify_analytic_portfolio(entry)
                selection_valid = problem.selection_valid
                if not verification.valid:
                    raise ValueError(
                        f"analytic portfolio certificate for {pair} failed replay: "
                        + "; ".join(verification.reasons)
                    )
                certified_exact = verified_upper_fraction(verification)
                if decision.decision_metric.startswith("incremental_"):
                    certified_exact = max(
                        0,
                        certified_exact - max(decimal_fraction(value) for value in problem.prior),
                    )
                certified_upper = outward_rounded_fraction(certified_exact)
                rational_bounds[pair] = certified_exact
                claimed = portfolio.joint_upper_bounds[pair]
                if claimed != certified_upper:
                    raise ValueError(
                        f"portfolio upper bound for {pair} does not replay: claimed {claimed:.6g}, "
                        f"certified {certified_upper:.6g}"
                    )
                if certified_exact <= decimal_fraction(decision.tolerance) and not selection_valid:
                    raise ValueError(
                        f"analytic portfolio certificate for {pair} lacks selection-valid coverage"
                    )
        return rational_bounds

    @staticmethod
    def _finite_success_metric(
        experiment: FiniteExperiment,
        decision_metric: str,
    ) -> float:
        exact = decision_value(experiment, exact_guess_problem(experiment.state_ids))
        supported = {
            "bayes_linkage_success",
            "incremental_bayes_linkage_success",
            "worst_observation_success",
            "equal_prior_membership_success",
            "finite_secret_exact_guess_success",
        }
        if decision_metric not in supported:
            raise ValueError(
                f"direct finite portfolio replay does not implement decision metric {decision_metric!r}"
            )
        if decision_metric == "worst_observation_success":
            values = []
            for observation in range(len(experiment.observation_ids)):
                mass = sum(
                    experiment.prior[state] * experiment.channel[state][observation]
                    for state in range(len(experiment.state_ids))
                )
                if mass > 0.0:
                    values.append(max(
                        experiment.prior[state] * experiment.channel[state][observation] / mass
                        for state in range(len(experiment.state_ids))
                    ))
            return max(values, default=0.0)
        if decision_metric.startswith("incremental_"):
            return max(0.0, exact - max(experiment.prior))
        return exact

    @staticmethod
    def _verify_search_space(request: OptimizationRequest, base_dir: Path) -> None:
        certificate = request.search_space_certificate
        if certificate is None:
            return
        source = verify_source_file(certificate.evidence_path, certificate.evidence_sha256, base_dir)
        verify_provenance_binding(certificate, source, ("method", "configuration_ids"))
        actual = tuple(sorted(item.configuration_id for item in request.configurations))
        if tuple(sorted(certificate.configuration_ids)) != actual:
            raise ValueError("search-space certificate does not enumerate exactly the submitted configurations")

    @staticmethod
    def _evaluate_configuration(
        configuration: ReleaseConfiguration,
        report: AssessmentReport,
        experiments: dict[str, FiniteExperiment],
        certificates: dict[str, GarblingCertificate],
        verifications: dict[str, GarblingVerification],
        registry_head_sha256: str,
        now: datetime,
        rational_portfolio_bounds: dict[str, Fraction],
    ) -> CandidateEvaluation:
        reasons: list[str] = []
        penalties: dict[str, float] = {}
        if report.overall_verdict is not OverallVerdict.CLEAR:
            reasons.append(f"assessment verdict is {report.overall_verdict}, not clear")
        if report.release_expires_at is not None and report.release_expires_at <= now:
            reasons.append("assessed release contract has expired")
        if report.policy_expires_at is not None and report.policy_expires_at <= now:
            reasons.append("assessment policy has expired")
        expired_scopes = [
            scope.scope_id for scope in report.population_scopes
            if scope.valid_until is not None and scope.valid_until < now.date()
        ]
        if expired_scopes:
            reasons.append(f"population scope validity expired: {sorted(expired_scopes)}")
        unversioned_scopes = [
            scope.scope_id for scope in report.population_scopes
            if scope.valid_until is None or scope.population_snapshot_sha256 is None
        ]
        if unversioned_scopes:
            reasons.append(
                "population scopes lack a versioned snapshot and validity horizon: "
                f"{sorted(unversioned_scopes)}"
            )
        utility_margin = configuration.utility.lower_bound - configuration.utility.minimum_required
        if utility_margin < 0.0:
            reasons.append(f"certified utility misses its minimum by {-utility_margin:.6g}")
        if not configuration.utility.audit_disjoint:
            reasons.append("utility certificate is not based on a disjoint audit set")
        if not configuration.utility.raw_evidence_retained:
            reasons.append("utility certificate does not retain replayable raw evidence")
        if configuration.portfolio.status is PortfolioAssuranceStatus.UNASSESSED:
            reasons.append("portfolio composition is explicitly unassessed")
        if configuration.portfolio.registry_head_sha256 != registry_head_sha256:
            reasons.append("portfolio registry head changed")
        expired_controls = [control.control_id for control in configuration.controls if control.valid_until <= now]
        if expired_controls:
            reasons.append(f"control certificates have expired: {sorted(expired_controls)}")
        if configuration.release_interface.protocol_type == "interactive_llm":
            reasons.append(
                "interactive LLM transcript/channel assurance is not implemented; a finite one-shot surrogate cannot clear it"
            )

        mandatory_decisions = {decision.threat_id: decision for decision in report.decisions if decision.mandatory}
        for threat_id, decision in mandatory_decisions.items():
            pair = f"{decision.population_scope_id}|{threat_id}"
            joint_upper = configuration.portfolio.joint_upper_bounds.get(pair)
            rational_upper = rational_portfolio_bounds.get(pair)
            if rational_upper is not None:
                exceeds_tolerance = rational_upper > decimal_fraction(decision.tolerance)
            else:
                exceeds_tolerance = (
                    joint_upper is not None and joint_upper > decision.tolerance
                )
            if joint_upper is not None and exceeds_tolerance:
                reasons.append(
                    f"portfolio joint upper bound {joint_upper:.6g} for {pair} exceeds tolerance {decision.tolerance:.6g}"
                )
        bindings = {binding.threat_id: binding for binding in configuration.threat_experiments}
        missing = set(mandatory_decisions) - set(bindings)
        extra = set(bindings) - set(mandatory_decisions)
        if missing:
            reasons.append(f"missing information-structure bindings for mandatory threats: {sorted(missing)}")
        if extra:
            reasons.append(f"bindings reference non-mandatory or unknown report threats: {sorted(extra)}")
        assessed_interface_sha256 = sha256_bytes(canonical_json_bytes(report.release_interface))
        released_interface_sha256 = sha256_bytes(canonical_json_bytes(configuration.release_interface))
        for threat_id, binding in bindings.items():
            decision = mandatory_decisions.get(threat_id)
            try:
                assessed = experiments[binding.assessed_experiment_id]
                released = experiments[binding.released_experiment_id]
            except KeyError as exc:
                reasons.append(f"binding for {threat_id} references unknown experiment {exc.args[0]}")
                continue
            if assessed.threat_id != threat_id or released.threat_id != threat_id:
                reasons.append(f"binding experiments do not match threat {threat_id}")
            if decision is None:
                continue
            if assessed.population_scope_id != decision.population_scope_id or released.population_scope_id != decision.population_scope_id:
                reasons.append(f"binding for {threat_id} changes the exact population scope")
            if assessed.decision_game_sha256 != decision.decision_game_sha256 or released.decision_game_sha256 != decision.decision_game_sha256:
                reasons.append(f"binding for {threat_id} changes or omits the decision-game hash")
            if assessed.state_ids != released.state_ids or assessed.prior != released.prior:
                reasons.append(f"binding for {threat_id} changes the state space or anchored prior")
            if assessed.artifact_sha256 != report.artifact_sha256:
                reasons.append(f"assessed experiment for {threat_id} is not bound to the assessed artifact")
            if released.artifact_sha256 != configuration.release_artifact_sha256:
                reasons.append(f"released experiment for {threat_id} is not bound to the release artifact")
            if assessed.interface_sha256 != assessed_interface_sha256:
                reasons.append(f"assessed experiment for {threat_id} is not bound to the assessed interface")
            if released.interface_sha256 != released_interface_sha256:
                reasons.append(f"released experiment for {threat_id} is not bound to the release interface")
            if decision.verdict is not Verdict.CLEAR:
                reasons.append(f"mandatory threat {threat_id} is not clear")
            penalty = 0.0
            if binding.assessed_experiment_id != binding.released_experiment_id:
                certificate = certificates.get(binding.substitution_certificate_id or "")
                if certificate is None:
                    reasons.append(f"binding for {threat_id} lacks its referenced garbling certificate")
                else:
                    verification = verifications[certificate.certificate_id]
                    if certificate.dominant_experiment_id != assessed.experiment_id or certificate.dominated_experiment_id != released.experiment_id:
                        reasons.append(f"substitution certificate for {threat_id} has the wrong direction or endpoints")
                    else:
                        penalty = verification.decision_value_penalty
                        if min(1.0, decision.upper_bound + penalty) > decision.tolerance:
                            reasons.append(
                                f"approximate substitution for {threat_id} raises the certified ceiling "
                                f"from {decision.upper_bound:.6g} to {min(1.0, decision.upper_bound + penalty):.6g}, "
                                f"above tolerance {decision.tolerance:.6g}"
                            )
            penalties[threat_id] = penalty
        return CandidateEvaluation(
            configuration_id=configuration.configuration_id,
            feasible=not reasons,
            assessment_verdict=report.overall_verdict,
            utility_margin=utility_margin,
            implementation_cost=configuration.implementation_cost,
            substitution_penalties=penalties,
            reasons=tuple(reasons) if reasons else ("all mandatory release constraints passed",),
        )

    @staticmethod
    def _transitive_reachability(
        experiments: dict[str, FiniteExperiment],
        edges: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        reachability: dict[str, set[str]] = {}
        for start in experiments:
            reached = {start}
            queue = deque([start])
            while queue:
                current = queue.popleft()
                for target in edges.get(current, set()):
                    if target not in reached:
                        reached.add(target)
                        queue.append(target)
            reachability[start] = reached
        return reachability

    @staticmethod
    def _strictly_less_informative(
        candidate: ReleaseConfiguration,
        other: ReleaseConfiguration,
        reachability: dict[str, set[str]],
    ) -> bool:
        """Return true only when candidate is Blackwell-below other for every bound threat."""
        candidate_bindings = {item.threat_id: item for item in candidate.threat_experiments}
        other_bindings = {item.threat_id: item for item in other.threat_experiments}
        if set(candidate_bindings) != set(other_bindings):
            return False
        information_strict = False
        for threat_id in candidate_bindings:
            candidate_experiment = candidate_bindings[threat_id].released_experiment_id
            other_experiment = other_bindings[threat_id].released_experiment_id
            if candidate_experiment not in reachability.get(other_experiment, {other_experiment}):
                return False
            if other_experiment not in reachability.get(candidate_experiment, {candidate_experiment}):
                information_strict = True
        return information_strict
