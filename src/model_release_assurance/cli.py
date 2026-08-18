from __future__ import annotations

import argparse
import json
import sys
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
from .models import AssessmentReport, AssessmentRequest, PolicyBundle, SignedManifest
from .optimizer import (
    OptimizationReport,
    OptimizationRequest,
    ReleaseOptimizer,
    SignedOptimizationManifest,
    build_signed_optimization_manifest,
    verify_signed_optimization_manifest,
)
from .portfolio_statistics import (
    AssuranceErrorBudget,
    IncompletePortfolioSpecification,
    MultinomialCountsFile,
    MultinomialEvidenceRequest,
    MultinomialSamplingPlan,
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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_model(path: Path, model) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mra", description="Model Release Assurance engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a release assessment contract")
    validate.add_argument("request", type=Path)

    assess = subparsers.add_parser("assess", help="run an assessment")
    assess.add_argument("request", type=Path)
    assess.add_argument("--output", type=Path, required=True)
    assess.add_argument("--audit-db", type=Path)

    optimize = subparsers.add_parser(
        "optimize",
        help="select the least-cost release configuration that passes privacy and utility gates",
    )
    optimize.add_argument("request", type=Path)
    optimize.add_argument("--output", type=Path, required=True)
    optimize.add_argument("--audit-db", type=Path)

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

    schema = subparsers.add_parser("schema", help="write the versioned request JSON schema")
    schema.add_argument(
        "--kind",
        choices=(
            "request", "policy", "report", "manifest", "optimization",
            "optimization-report", "optimization-manifest", "portfolio-problem",
            "portfolio-certificate", "portfolio-multinomial-counts",
            "portfolio-multinomial-plan",
            "portfolio-error-budget", "portfolio-multinomial-request",
            "portfolio-multinomial-evidence", "portfolio-specification",
            "protocol-problem", "protocol-certificate",
        ),
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            AssessmentRequest.model_validate(_read_json(args.request))
            print("valid")
        elif args.command == "schema":
            schema_models = {
                "request": AssessmentRequest,
                "policy": PolicyBundle,
                "report": AssessmentReport,
                "manifest": SignedManifest,
                "optimization": OptimizationRequest,
                "optimization-report": OptimizationReport,
                "optimization-manifest": SignedOptimizationManifest,
                "portfolio-problem": IncompletePortfolioProblem,
                "portfolio-certificate": AnalyticPortfolioEvidenceEntry,
                "portfolio-multinomial-counts": MultinomialCountsFile,
                "portfolio-multinomial-plan": MultinomialSamplingPlan,
                "portfolio-error-budget": AssuranceErrorBudget,
                "portfolio-multinomial-request": MultinomialEvidenceRequest,
                "portfolio-multinomial-evidence": SimultaneousMultinomialEvidence,
                "portfolio-specification": IncompletePortfolioSpecification,
                "protocol-problem": ProtocolFeasibilityProblem,
                "protocol-certificate": ProtocolFeasibilityCertificate,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(schema_models[args.kind].model_json_schema(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        elif args.command == "assess":
            request = AssessmentRequest.model_validate(_read_json(args.request))
            report = AssuranceEngine().assess(request, args.request.parent)
            _write_model(args.output, report)
            if args.audit_db:
                AuditStore(args.audit_db).append_report(report)
            print(report.overall_verdict)
        elif args.command == "optimize":
            request = OptimizationRequest.model_validate(_read_json(args.request))
            report = ReleaseOptimizer().optimize(request, args.request.parent)
            _write_model(args.output, report)
            if args.audit_db:
                AuditStore(args.audit_db).append_optimization_report(report)
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
            manifest = build_signed_manifest(report, request.release, args.private)
            _write_model(args.output, manifest)
        elif args.command == "verify":
            manifest = SignedManifest.model_validate(_read_json(args.manifest))
            report = AssessmentReport.model_validate(_read_json(args.report))
            verify_signed_manifest(manifest, report, args.public)
            print("verified")
        elif args.command == "audit-verify":
            if not args.audit_db.is_file():
                raise AssuranceError("audit database does not exist")
            print(f"verified {AuditStore(args.audit_db).verify_chain(require_events=True)} audit event(s)")
        return 0
    except (AssuranceError, ValidationError, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
