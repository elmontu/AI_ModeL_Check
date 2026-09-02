"""Single source of truth for the package's current public JSON Schemas."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel

from .audit import AuditCheckpoint, AuditVerification
from .incomplete_portfolio import AnalyticPortfolioEvidenceEntry, IncompletePortfolioProblem
from .models import (
    AssessmentReport,
    AssessmentRequest,
    AttackBatteryConfiguration,
    AttackBatteryInput,
    AttackBatteryWorkerOutput,
    AttackCatalog,
    AttackPositiveControlResult,
    PolicyBundle,
    SignedManifest,
)
from .optimizer import (
    OptimizationReport,
    OptimizationRequest,
    SignedOptimizationManifest,
)
from .portfolio_statistics import (
    AssuranceErrorBudget,
    IncompletePortfolioSpecification,
    MultinomialCountsFile,
    MultinomialEvidenceRequest,
    MultinomialSamplingPlan,
    SimultaneousMultinomialEvidence,
)
from .protocol_feasibility import ProtocolFeasibilityCertificate, ProtocolFeasibilityProblem
from .release_protocol import ReleaseProtocolRun, ReleaseProtocolVerification
from .version import VERSION


PACKAGE_NAME = "model-release-assurance"
SCHEMA_MANIFEST_FILENAME = "current-schema-manifest-v1.json"


@dataclass(frozen=True, slots=True)
class SchemaRegistration:
    """A current CLI schema kind and its versioned repository artifact."""

    kind: str
    model: type[BaseModel]
    filename: str
    declared_schema_version: str

    @property
    def model_import(self) -> str:
        return f"{self.model.__module__}.{self.model.__qualname__}"

    def rendered_schema(self) -> dict[str, object]:
        return self.model.model_json_schema()

    def rendered_bytes(self) -> bytes:
        return (
            json.dumps(self.rendered_schema(), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")


def _registration(
    kind: str,
    model: type[BaseModel],
    filename: str,
    declared_schema_version: str,
) -> SchemaRegistration:
    return SchemaRegistration(kind, model, filename, declared_schema_version)


_REGISTRATIONS = (
    _registration("request", AssessmentRequest, "assessment-request-v5.json", "5.0"),
    _registration("policy", PolicyBundle, "policy-bundle-v3.json", "3.0"),
    _registration("report", AssessmentReport, "assessment-report-v5.json", "5.0"),
    _registration("manifest", SignedManifest, "signed-manifest-v3.json", "3.0"),
    _registration("attack-catalog", AttackCatalog, "attack-catalog-v1.json", "1.0"),
    _registration(
        "attack-battery-configuration",
        AttackBatteryConfiguration,
        "attack-battery-configuration-v1.json",
        "1.0",
    ),
    _registration(
        "attack-positive-control-result",
        AttackPositiveControlResult,
        "attack-positive-control-result-v1.json",
        "1.0",
    ),
    _registration(
        "attack-battery-worker-output",
        AttackBatteryWorkerOutput,
        "attack-battery-worker-output-v1.json",
        "1.0",
    ),
    _registration(
        "attack-battery-submission",
        AttackBatteryInput,
        "attack-battery-submission-v1.json",
        "1.0",
    ),
    _registration("optimization", OptimizationRequest, "optimization-request-v4.json", "4.0"),
    _registration(
        "optimization-report", OptimizationReport, "optimization-report-v4.json", "4.0"
    ),
    _registration(
        "optimization-manifest",
        SignedOptimizationManifest,
        "signed-optimization-manifest-v4.json",
        "4.0",
    ),
    _registration(
        "portfolio-problem",
        IncompletePortfolioProblem,
        "incomplete-portfolio-problem-v1.json",
        "1.0",
    ),
    _registration(
        "portfolio-certificate",
        AnalyticPortfolioEvidenceEntry,
        "incomplete-portfolio-certificate-v1.1.json",
        "1.1",
    ),
    _registration(
        "portfolio-multinomial-counts",
        MultinomialCountsFile,
        "portfolio-multinomial-counts-v1.json",
        "1.0",
    ),
    _registration(
        "portfolio-multinomial-plan",
        MultinomialSamplingPlan,
        "portfolio-multinomial-plan-v1.json",
        "1.0",
    ),
    _registration(
        "portfolio-error-budget",
        AssuranceErrorBudget,
        "portfolio-error-budget-v1.json",
        "1.0",
    ),
    _registration(
        "portfolio-multinomial-request",
        MultinomialEvidenceRequest,
        "portfolio-multinomial-request-v1.json",
        "1.0",
    ),
    _registration(
        "portfolio-multinomial-evidence",
        SimultaneousMultinomialEvidence,
        "portfolio-multinomial-evidence-v1.json",
        "1.0",
    ),
    _registration(
        "portfolio-specification",
        IncompletePortfolioSpecification,
        "incomplete-portfolio-specification-v1.json",
        "1.0",
    ),
    _registration(
        "protocol-problem",
        ProtocolFeasibilityProblem,
        "protocol-feasibility-problem-v1.json",
        "1.0",
    ),
    _registration(
        "protocol-certificate",
        ProtocolFeasibilityCertificate,
        "protocol-feasibility-certificate-v1.json",
        "1.0",
    ),
    _registration(
        "release-protocol-run",
        ReleaseProtocolRun,
        "release-protocol-run-v1.1.json",
        "1.1",
    ),
    _registration(
        "release-protocol-verification",
        ReleaseProtocolVerification,
        "release-protocol-verification-v2.json",
        "2.0",
    ),
    _registration(
        "audit-verification", AuditVerification, "audit-verification-v3.json", "3.0"
    ),
    _registration("audit-checkpoint", AuditCheckpoint, "audit-checkpoint-v1.json", "1.0"),
)


SCHEMA_REGISTRY: Mapping[str, SchemaRegistration] = MappingProxyType(
    {registration.kind: registration for registration in _REGISTRATIONS}
)


def _declared_version_from_schema(schema: dict[str, object]) -> str:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("schema has no object-valued properties")
    version = properties.get("schema_version")
    if not isinstance(version, dict) or not isinstance(version.get("const"), str):
        raise ValueError("schema_version must be declared as a string const")
    return version["const"]


def validate_schema_registry() -> None:
    """Reject duplicate artifacts and registry metadata that drifted from a model."""

    if len(SCHEMA_REGISTRY) != len(_REGISTRATIONS):
        raise ValueError("schema registry contains duplicate kinds")
    filenames = [registration.filename for registration in _REGISTRATIONS]
    if len(set(filenames)) != len(filenames):
        raise ValueError("schema registry contains duplicate filenames")
    for registration in _REGISTRATIONS:
        major, separator, minor = registration.declared_schema_version.partition(".")
        if not separator or not major.isdigit() or not minor.isdigit():
            raise ValueError(
                f"{registration.kind}: invalid declared schema version "
                f"{registration.declared_schema_version!r}"
            )
        version_label = f"v{major}" if minor == "0" else f"v{major}.{minor}"
        if not registration.filename.endswith(f"-{version_label}.json"):
            raise ValueError(
                f"{registration.kind}: {registration.filename!r} does not encode "
                f"schema version {registration.declared_schema_version!r}"
            )
        schema = registration.rendered_schema()
        title = schema.get("title")
        if title != registration.model.__name__:
            raise ValueError(
                f"{registration.kind}: schema title {title!r} does not match "
                f"model {registration.model.__name__!r}"
            )
        actual_version = _declared_version_from_schema(schema)
        if actual_version != registration.declared_schema_version:
            raise ValueError(
                f"{registration.kind}: registered schema version "
                f"{registration.declared_schema_version!r} does not match {actual_version!r}"
            )


def schema_manifest(schemas_dir: Path) -> dict[str, object]:
    """Build the deterministic inventory of committed current schema bytes."""

    validate_schema_registry()
    contracts: list[dict[str, object]] = []
    for kind in sorted(SCHEMA_REGISTRY):
        registration = SCHEMA_REGISTRY[kind]
        path = schemas_dir / registration.filename
        raw = path.read_bytes()
        parsed = json.loads(raw)
        if parsed.get("title") != registration.model.__name__:
            raise ValueError(f"{path}: title does not match {registration.model.__name__}")
        actual_version = _declared_version_from_schema(parsed)
        if actual_version != registration.declared_schema_version:
            raise ValueError(
                f"{path}: schema_version {actual_version!r} does not match "
                f"{registration.declared_schema_version!r}"
            )
        contracts.append(
            {
                "declared_schema_version": registration.declared_schema_version,
                "filename": registration.filename,
                "kind": registration.kind,
                "model_import": registration.model_import,
                "model_title": registration.model.__name__,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return {
        "schema_version": "1.0",
        "manifest_type": "current_schema_registry",
        "digest_algorithm": "sha256",
        "digest_scope": "exact_file_bytes",
        "package_name": PACKAGE_NAME,
        "package_version": VERSION,
        "coverage": {
            "registered_contract_count": len(contracts),
            "manifest_self_included": False,
            "self_exclusion_reason": (
                "A byte inventory cannot recursively contain the digest of its own final bytes."
            ),
            "manifest_integrity": (
                "deterministic exact-byte regeneration plus detached protected release attestation"
            ),
        },
        "contracts": contracts,
        "attestation": {
            "committed_signature": False,
            "release_attestation_required": True,
            "trust_boundary": (
                "A protected release process must sign or externally attest these exact "
                "manifest bytes; the repository does not contain a trusted private key."
            ),
        },
    }


def render_schema_manifest(schemas_dir: Path) -> bytes:
    return (json.dumps(schema_manifest(schemas_dir), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
