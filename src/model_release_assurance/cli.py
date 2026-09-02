from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .audit import AuditStore
from .engine import AssuranceEngine
from .errors import AssuranceError
from .integrity import (
    build_signed_manifest,
    generate_ed25519_keypair,
    verify_signed_manifest,
)
from .incomplete_portfolio import (
    AnalyticPortfolioEvidenceEntry,
    IncompletePortfolioProblem,
    solve_analytic_portfolio,
    verify_analytic_portfolio,
    verify_portfolio_problem_evidence,
)
from .models import AssessmentReport, AssessmentRequest, SignedManifest
from .model_coverage import assess_request_model_coverage, catalog_as_dicts
from .optimizer import (
    OptimizationReport,
    OptimizationRequest,
    ReleaseOptimizer,
    SignedOptimizationManifest,
    build_signed_optimization_manifest,
    verify_signed_optimization_manifest,
)
from .portfolio_statistics import (
    IncompletePortfolioSpecification,
    MultinomialEvidenceRequest,
    SimultaneousMultinomialEvidence,
    compile_multinomial_portfolio_problem,
    generate_simultaneous_multinomial_evidence,
    rebase_multinomial_evidence_sources,
    rebase_portfolio_specification_sources,
    verify_portfolio_specification_evidence,
    verify_simultaneous_multinomial_evidence,
)
from .integrity import sha256_file
from .protocol_feasibility import (
    ProtocolFeasibilityCertificate,
    ProtocolFeasibilityProblem,
    protocol_problem_sha256,
    solve_protocol_feasibility,
    verify_protocol_feasibility,
)
from .release_protocol import (
    ReleaseProtocolRun,
    ReleaseProtocolVerificationProfile,
    verify_release_protocol_run,
)
from .schema_registry import SCHEMA_REGISTRY
from .version import VERSION


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_model(path: Path, model) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve required-explicit nullable fields in governed CLI artifacts.
    _write_text_lf(path, model.model_dump_json(indent=2, exclude_none=False) + "\n")


def _write_text_lf(path: Path, value: str) -> None:
    """Write canonical CLI output without platform-dependent newline conversion."""
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mra",
        description="Offline model-release contract assessment and replay toolkit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a release assessment contract")
    validate.add_argument("request", type=Path)

    model_coverage = subparsers.add_parser(
        "model-coverage",
        help="list governed model families or review one assessment request for coverage gaps",
    )
    model_coverage.add_argument("request", type=Path, nargs="?")
    model_coverage.add_argument("--json", action="store_true", dest="as_json")

    assess = subparsers.add_parser("assess", help="run an assessment")
    assess.add_argument("request", type=Path)
    assess.add_argument("--output", type=Path, required=True)
    assess.add_argument("--audit-db", type=Path, required=True)

    optimize = subparsers.add_parser(
        "optimize",
        help="select the least-cost release configuration that passes privacy and utility gates",
    )
    optimize.add_argument("request", type=Path)
    optimize.add_argument("--output", type=Path, required=True)
    optimize.add_argument("--audit-db", type=Path, required=True)

    portfolio_solve = subparsers.add_parser(
        "portfolio-solve",
        help="solve a finite incomplete-portfolio problem and write a replayable certificate",
    )
    portfolio_solve.add_argument("problem", type=Path)
    portfolio_solve.add_argument("--output", type=Path, required=True)
    portfolio_solve.add_argument(
        "--method",
        choices=("auto", "exact", "envelope"),
        default="auto",
    )
    portfolio_solve.add_argument("--certificate-id", default="portfolio-certificate")
    portfolio_solve.add_argument("--max-decoders", type=int, default=100_000)
    portfolio_solve.add_argument("--numerical-tolerance", type=float, default=1e-8)
    portfolio_solve.add_argument(
        "--evidence-base",
        type=Path,
        help="directory against which relative evidence paths are resolved (default: problem directory)",
    )
    portfolio_solve.add_argument(
        "--skip-evidence-files",
        action="store_true",
        help="solve the mathematics without checking referenced evidence files; not clearance-grade",
    )

    portfolio_verify = subparsers.add_parser(
        "portfolio-verify",
        help="independently replay an incomplete-portfolio certificate",
    )
    portfolio_verify.add_argument("certificate", type=Path)
    portfolio_verify.add_argument(
        "--evidence-base",
        type=Path,
        help="directory against which embedded relative evidence paths are resolved (default: certificate directory)",
    )

    protocol_solve = subparsers.add_parser(
        "protocol-solve",
        help="solve a finite soundness-liveness protocol frontier and write an exact replay certificate",
    )
    protocol_solve.add_argument("problem", type=Path)
    protocol_solve.add_argument("--output", type=Path, required=True)
    protocol_solve.add_argument("--certificate-id", default="protocol-feasibility-certificate")
    protocol_solve.add_argument("--maximum-denominator", type=int, default=1_000_000_000)
    protocol_solve.add_argument(
        "--maximum-deterministic-protocols",
        type=int,
        default=1_000_000,
    )

    protocol_verify = subparsers.add_parser(
        "protocol-verify",
        help="replay a finite protocol-feasibility certificate in exact rational arithmetic",
    )
    protocol_verify.add_argument("certificate", type=Path)
    protocol_verify.add_argument(
        "--problem",
        type=Path,
        help="externally approved problem whose canonical hash must match the certificate",
    )
    protocol_verify.add_argument(
        "--maximum-deterministic-protocols",
        type=int,
        default=1_000_000,
    )

    release_protocol_verify = subparsers.add_parser(
        "release-protocol-verify",
        help="replay an MRAP/1.0 transcript under its structural or authenticated profile",
    )
    release_protocol_verify.add_argument("transcript", type=Path)
    release_protocol_verify.add_argument(
        "--artifact-base",
        type=Path,
        help="directory for relative protocol-artifact paths (default: transcript directory)",
    )
    release_protocol_verify.add_argument(
        "--skip-artifact-files",
        action="store_true",
        help="replay states without checking artifact files; not conformance-grade",
    )
    release_protocol_verify.add_argument(
        "--as-of",
        type=datetime.fromisoformat,
        help="timezone-aware status-verification time (default: current UTC time)",
    )
    release_protocol_verify.add_argument(
        "--trust-store",
        type=Path,
        help="JSON object mapping trusted signer-key IDs to PEM public-key paths",
    )
    release_protocol_verify.add_argument(
        "--compromised-key-id",
        action="append",
        default=[],
        help="reject a signer key as revoked/compromised; may be repeated",
    )
    release_protocol_verify.add_argument(
        "--require-authenticated",
        action="store_true",
        help="reject structural transcripts to prevent verification-profile downgrade",
    )
    release_protocol_verify.add_argument(
        "--output",
        type=Path,
        help="write the machine-readable verification result, including degraded checks",
    )
    portfolio_verify.add_argument(
        "--skip-evidence-files",
        action="store_true",
        help="verify certificate arithmetic without checking referenced evidence files",
    )

    multinomial_generate = subparsers.add_parser(
        "portfolio-multinomial-generate",
        help="generate selection-qualified simultaneous marginal intervals from raw counts",
    )
    multinomial_generate.add_argument("request", type=Path)
    multinomial_generate.add_argument("--output", type=Path, required=True)

    multinomial_verify = subparsers.add_parser(
        "portfolio-multinomial-verify",
        help="replay simultaneous marginal evidence from raw counts and an error-budget ledger",
    )
    multinomial_verify.add_argument("evidence", type=Path)

    multinomial_compile = subparsers.add_parser(
        "portfolio-multinomial-compile",
        help="compile simultaneous marginal evidence into an incomplete-portfolio problem",
    )
    multinomial_compile.add_argument("evidence", type=Path)
    multinomial_compile.add_argument("specification", type=Path)
    multinomial_compile.add_argument("--output", type=Path, required=True)

    optimize_sign = subparsers.add_parser("optimize-sign", help="sign a final optimization report")
    optimize_sign.add_argument("report", type=Path)
    optimize_sign.add_argument("--private", type=Path, required=True)
    optimize_sign.add_argument("--output", type=Path, required=True)

    optimize_verify = subparsers.add_parser("optimize-verify", help="verify a signed final optimization report")
    optimize_verify.add_argument("manifest", type=Path)
    optimize_verify.add_argument("report", type=Path)
    optimize_verify.add_argument("--public", type=Path, required=True)

    schema = subparsers.add_parser("schema", help="write a current versioned JSON schema")
    schema.add_argument(
        "--kind",
        choices=tuple(SCHEMA_REGISTRY),
        default="request",
    )
    schema.add_argument("--output", type=Path, required=True)

    keygen = subparsers.add_parser("keygen", help="generate an Ed25519 signing keypair")
    keygen.add_argument("--private", type=Path, required=True)
    keygen.add_argument("--public", type=Path, required=True)

    sign = subparsers.add_parser("sign", help="sign an assessment report manifest")
    sign.add_argument("request", type=Path)
    sign.add_argument("report", type=Path)
    sign.add_argument("--private", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="verify a signed manifest")
    verify.add_argument("manifest", type=Path)
    verify.add_argument("report", type=Path)
    verify.add_argument("--public", type=Path, required=True)

    audit = subparsers.add_parser("audit-verify", help="verify the hash-chained audit database")
    audit.add_argument("audit_db", type=Path)
    audit.add_argument("--expected-count", type=int)
    audit.add_argument("--expected-head", dest="expected_head_sha256")
    audit.add_argument("--expected-ledger-id")
    audit.add_argument("--allow-orphans", action="store_true")
    audit.add_argument("--json", action="store_true", dest="as_json")

    checkpoint = subparsers.add_parser(
        "audit-checkpoint",
        help="export an audit ledger ID, event count, and head for external anchoring",
    )
    checkpoint.add_argument("audit_db", type=Path)
    checkpoint.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            AssessmentRequest.model_validate(_read_json(args.request))
            print("valid")
        elif args.command == "model-coverage":
            result = (
                catalog_as_dicts()
                if args.request is None
                else assess_request_model_coverage(
                    AssessmentRequest.model_validate(_read_json(args.request))
                )
            )
            if args.as_json:
                print(json.dumps(result, indent=2, sort_keys=True))
            elif args.request is None:
                for entry in result:
                    print(f"{entry['family_id']}: {entry['status']} - {entry['display_name']}")
            else:
                print(
                    f"{result['submitted_model_family']} -> "
                    f"{result['resolved_family']['family_id']}; "
                    f"coverage_ready={str(result['coverage_ready']).lower()}; can_clear=false"
                )
        elif args.command == "schema":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _write_text_lf(
                args.output,
                SCHEMA_REGISTRY[args.kind].rendered_bytes().decode("utf-8"),
            )
        elif args.command == "assess":
            request = AssessmentRequest.model_validate(_read_json(args.request))
            audit_store = AuditStore(args.audit_db)
            audit_run = audit_store.append_assessment_intent(request)
            try:
                report = AssuranceEngine().assess(request, args.request.parent)
            except Exception as exc:
                audit_store.append_assessment_failed(
                    audit_run,
                    type(exc).__name__,
                    str(exc)[:4096],
                )
                raise
            audit_store.append_assessment_completed(audit_run, report)
            _write_model(args.output, report)
            print(report.overall_verdict)
        elif args.command == "optimize":
            request = OptimizationRequest.model_validate(_read_json(args.request))
            audit_store = AuditStore(args.audit_db)
            audit_run = audit_store.append_optimization_intent(request)
            try:
                report = ReleaseOptimizer().optimize(request, args.request.parent)
            except Exception as exc:
                audit_store.append_optimization_failed(
                    audit_run,
                    type(exc).__name__,
                    str(exc)[:4096],
                )
                raise
            audit_store.append_optimization_completed(audit_run, report)
            _write_model(args.output, report)
            print(report.outcome)
        elif args.command == "portfolio-solve":
            problem = IncompletePortfolioProblem.model_validate(_read_json(args.problem))
            if not args.skip_evidence_files:
                verify_portfolio_problem_evidence(
                    problem,
                    args.evidence_base if args.evidence_base is not None else args.problem.parent,
                )
            entry = solve_analytic_portfolio(
                problem,
                method=args.method,
                certificate_id=args.certificate_id,
                max_decoders=args.max_decoders,
                numerical_tolerance=args.numerical_tolerance,
            )
            verification = verify_analytic_portfolio(entry)
            if not verification.valid:
                raise AssuranceError(
                    "generated portfolio certificate failed replay: "
                    + "; ".join(verification.reasons)
                )
            _write_model(args.output, entry)
            method = "exact" if entry.exact_certificate is not None else "envelope"
            print(
                f"{method} upper_bound={verification.upper_bound:.12g} "
                f"exact_upper={verification.exact_upper_numerator}/"
                f"{verification.exact_upper_denominator} rational_replay=true "
                f"selection_valid={problem.selection_valid} "
                f"coverage_confidence={problem.coverage_confidence:.12g}; "
                "certificate generation is not a release authorization"
            )
        elif args.command == "portfolio-verify":
            entry = AnalyticPortfolioEvidenceEntry.model_validate(_read_json(args.certificate))
            if not args.skip_evidence_files:
                verify_portfolio_problem_evidence(
                    entry.problem,
                    args.evidence_base if args.evidence_base is not None else args.certificate.parent,
                )
            verification = verify_analytic_portfolio(entry)
            if not verification.valid:
                raise AssuranceError(
                    "portfolio certificate failed replay: " + "; ".join(verification.reasons)
                )
            print(
                f"verified upper_bound={verification.upper_bound:.12g} "
                f"exact_upper={verification.exact_upper_numerator}/"
                f"{verification.exact_upper_denominator} rational_replay=true "
                f"selection_valid={entry.problem.selection_valid} "
                f"coverage_confidence={entry.problem.coverage_confidence:.12g}; "
                "certificate verification is not a release authorization"
            )
        elif args.command == "protocol-solve":
            problem = ProtocolFeasibilityProblem.model_validate(_read_json(args.problem))
            certificate = solve_protocol_feasibility(
                problem,
                certificate_id=args.certificate_id,
                maximum_denominator=args.maximum_denominator,
                maximum_deterministic_protocols=args.maximum_deterministic_protocols,
            )
            _write_model(args.output, certificate)
            verification = verify_protocol_feasibility(
                certificate,
                maximum_deterministic_protocols=args.maximum_deterministic_protocols,
            )
            print(
                f"{verification.status} "
                f"exact_lower={verification.exact_lower_numerator}/"
                f"{verification.exact_lower_denominator} "
                f"exact_upper={verification.exact_upper_numerator}/"
                f"{verification.exact_upper_denominator}; "
                "finite-model result is not a production release authorization"
            )
        elif args.command == "protocol-verify":
            certificate = ProtocolFeasibilityCertificate.model_validate(
                _read_json(args.certificate)
            )
            expected_problem_sha256 = None
            if args.problem is not None:
                expected_problem = ProtocolFeasibilityProblem.model_validate(
                    _read_json(args.problem)
                )
                expected_problem_sha256 = protocol_problem_sha256(expected_problem)
            verification = verify_protocol_feasibility(
                certificate,
                maximum_deterministic_protocols=args.maximum_deterministic_protocols,
                expected_problem_sha256=expected_problem_sha256,
            )
            if not verification.valid:
                raise AssuranceError(
                    "protocol certificate failed replay: " + "; ".join(verification.reasons)
                )
            print(
                f"verified {verification.status} "
                f"exact_lower={verification.exact_lower_numerator}/"
                f"{verification.exact_lower_denominator} "
                f"exact_upper={verification.exact_upper_numerator}/"
                f"{verification.exact_upper_denominator}; "
                "finite-model result is not a production release authorization"
            )
        elif args.command == "release-protocol-verify":
            run = ReleaseProtocolRun.model_validate(_read_json(args.transcript))
            trusted_public_keys: dict[str, Path] = {}
            if args.trust_store is not None:
                trust_raw = _read_json(args.trust_store)
                if not isinstance(trust_raw, dict) or not all(
                    isinstance(key, str) and isinstance(value, str)
                    for key, value in trust_raw.items()
                ):
                    raise AssuranceError("protocol trust store must map string key IDs to string paths")
                trusted_public_keys = {
                    key: (
                        Path(value)
                        if Path(value).is_absolute()
                        else args.trust_store.parent / value
                    )
                    for key, value in trust_raw.items()
                }
            verification = verify_release_protocol_run(
                run,
                args.artifact_base
                if args.artifact_base is not None
                else args.transcript.parent,
                verify_artifact_files=not args.skip_artifact_files,
                as_of=args.as_of,
                trusted_public_keys=trusted_public_keys,
                compromised_key_ids=frozenset(args.compromised_key_id),
                required_profile=(
                    ReleaseProtocolVerificationProfile.AUTHENTICATED
                    if args.require_authenticated
                    else None
                ),
            )
            if not verification.valid:
                raise AssuranceError(
                    "release-protocol transcript failed verification: "
                    + "; ".join(verification.reasons)
                )
            if args.output is not None:
                _write_model(args.output, verification)
            profile_label = (
                "authenticated_verified"
                if run.verification_profile.value == "authenticated_v1"
                else "structurally_verified"
            )
            limitation = (
                "authenticated replay validates trust-anchored signatures but does not issue "
                "a production authorization"
                if profile_label == "authenticated_verified"
                else "structural replay does not authenticate actors or issue a production authorization"
            )
            print(
                f"{profile_label} state={verification.final_state.value} "
                f"authorization_recorded={str(verification.authorization_issued).lower()} "
                f"active={str(verification.deployment_active).lower()} "
                f"artifact_files_verified={str(verification.artifact_files_verified).lower()} "
                f"skipped_checks={','.join(verification.skipped_checks) or 'none'}; "
                f"{limitation}"
            )
        elif args.command == "portfolio-multinomial-generate":
            request = MultinomialEvidenceRequest.model_validate(_read_json(args.request))
            evidence = generate_simultaneous_multinomial_evidence(request, args.request.parent)
            evidence = rebase_multinomial_evidence_sources(
                evidence,
                current_base_dir=args.request.parent,
                output_base_dir=args.output.parent,
            )
            _write_model(args.output, evidence)
            print(
                f"{evidence.coverage.value} cells={evidence.simultaneous_cell_count} "
                f"family_confidence={evidence.family_coverage_confidence:.12g} "
                f"assurance_confidence={evidence.assurance_wide_confidence:.12g} "
                f"selection_valid={evidence.selection_valid}; "
                "evidence generation is not a release authorization"
            )
        elif args.command == "portfolio-multinomial-verify":
            evidence = SimultaneousMultinomialEvidence.model_validate(_read_json(args.evidence))
            verification = verify_simultaneous_multinomial_evidence(
                evidence,
                args.evidence.parent,
            )
            if not verification.valid:
                raise AssuranceError(
                    "simultaneous multinomial evidence failed replay: "
                    + "; ".join(verification.reasons)
                )
            print(
                f"verified coverage_confidence={verification.coverage_confidence:.12g} "
                f"selection_valid={verification.selection_valid}; "
                "evidence verification is not a release authorization"
            )
        elif args.command == "portfolio-multinomial-compile":
            evidence = SimultaneousMultinomialEvidence.model_validate(_read_json(args.evidence))
            verification = verify_simultaneous_multinomial_evidence(
                evidence,
                args.evidence.parent,
            )
            if not verification.valid:
                raise AssuranceError(
                    "simultaneous multinomial evidence failed replay: "
                    + "; ".join(verification.reasons)
                )
            specification = IncompletePortfolioSpecification.model_validate(
                _read_json(args.specification)
            )
            verify_portfolio_specification_evidence(specification, args.specification.parent)
            specification = rebase_portfolio_specification_sources(
                specification,
                current_base_dir=args.specification.parent,
                output_base_dir=args.output.parent,
            )
            evidence_path = args.evidence.resolve(strict=True)
            problem = compile_multinomial_portfolio_problem(
                evidence,
                specification,
                evidence_source_path=str(evidence_path),
                evidence_source_sha256=sha256_file(evidence_path),
            )
            _write_model(args.output, problem)
            print(
                f"compiled releases={len(problem.releases)} "
                f"coverage_confidence={problem.coverage_confidence:.12g} "
                f"selection_valid={problem.selection_valid}; "
                "problem compilation is not a release authorization"
            )
        elif args.command == "optimize-sign":
            report = OptimizationReport.model_validate(_read_json(args.report))
            manifest = build_signed_optimization_manifest(report, args.private)
            _write_model(args.output, manifest)
        elif args.command == "optimize-verify":
            manifest = SignedOptimizationManifest.model_validate(_read_json(args.manifest))
            report = OptimizationReport.model_validate(_read_json(args.report))
            verify_signed_optimization_manifest(manifest, report, args.public)
            print("verified")
        elif args.command == "keygen":
            generate_ed25519_keypair(args.private, args.public)
        elif args.command == "sign":
            request = AssessmentRequest.model_validate(_read_json(args.request))
            report = AssessmentReport.model_validate(_read_json(args.report))
            manifest = build_signed_manifest(report, request, args.private)
            _write_model(args.output, manifest)
        elif args.command == "verify":
            manifest = SignedManifest.model_validate(_read_json(args.manifest))
            report = AssessmentReport.model_validate(_read_json(args.report))
            verify_signed_manifest(manifest, report, args.public)
            print("verified")
        elif args.command == "audit-verify":
            if not args.audit_db.is_file():
                raise AssuranceError("audit database does not exist")
            verification = AuditStore.open_read_only(args.audit_db).verify(
                require_events=True,
                require_complete=not args.allow_orphans,
                expected_event_count=args.expected_count,
                expected_head_sha256=args.expected_head_sha256,
                expected_ledger_id=args.expected_ledger_id,
            )
            if args.as_json:
                print(verification.model_dump_json(indent=2))
            else:
                print(
                    f"verified {verification.event_count} audit event(s); "
                    f"ledger={verification.ledger_id} head={verification.head_sha256} "
                    f"complete={str(verification.complete).lower()}"
                )
        elif args.command == "audit-checkpoint":
            if not args.audit_db.is_file():
                raise AssuranceError("audit database does not exist")
            _write_model(
                args.output,
                AuditStore.open_read_only(args.audit_db).export_checkpoint(
                    require_events=True,
                    require_complete=True,
                ),
            )
            print("checkpoint exported; anchor it in a trusted external store")
        return 0
    except (AssuranceError, ValidationError, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
