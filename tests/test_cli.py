from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from model_release_assurance.integrity import sha256_file
from model_release_assurance.incomplete_portfolio import (
    ConditionalMarginalBounds,
    CouplingModel,
    EvidenceReference,
    IncompletePortfolioProblem,
    StatisticalCoverage,
)
from model_release_assurance.decision_theory import exact_guess_problem


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_protocol_solve_verify_and_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            certificate = temp / "protocol-certificate.json"
            problem_schema = temp / "protocol-problem-schema.json"
            certificate_schema = temp / "protocol-certificate-schema.json"
            base = [sys.executable, "-m", "model_release_assurance"]
            for command in (
                base + [
                    "protocol-solve",
                    str(ROOT / "examples" / "protocol-feasibility-problem.json"),
                    "--output",
                    str(certificate),
                ],
                base + [
                    "protocol-verify",
                    str(certificate),
                    "--problem",
                    str(ROOT / "examples" / "protocol-feasibility-problem.json"),
                ],
                base + [
                    "schema", "--kind", "protocol-problem", "--output", str(problem_schema),
                ],
                base + [
                    "schema", "--kind", "protocol-certificate", "--output", str(certificate_schema),
                ],
            ):
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, msg=result.stderr)
            raw = json.loads(certificate.read_text())
            self.assertEqual(raw["status"], "target_met")
            self.assertEqual(raw["primal"]["minimum_liveness"], {"numerator": 9, "denominator": 10})
            self.assertEqual(raw["dual"]["objective_upper"], {"numerator": 9, "denominator": 10})
            self.assertEqual(json.loads(problem_schema.read_text())["title"], "ProtocolFeasibilityProblem")
            self.assertEqual(
                json.loads(certificate_schema.read_text())["title"],
                "ProtocolFeasibilityCertificate",
            )

    def test_multinomial_portfolio_pipeline_and_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            evidence = temp / "simultaneous-evidence.json"
            problem = temp / "compiled-problem.json"
            certificate = temp / "portfolio-certificate.json"
            base = [sys.executable, "-m", "model_release_assurance"]
            commands = (
                base + [
                    "portfolio-multinomial-generate",
                    str(ROOT / "examples" / "portfolio-multinomial-request.json"),
                    "--output", str(evidence),
                ],
                base + ["portfolio-multinomial-verify", str(evidence)],
                base + [
                    "portfolio-multinomial-compile", str(evidence),
                    str(ROOT / "examples" / "incomplete-portfolio-specification.json"),
                    "--output", str(problem),
                ],
                base + ["portfolio-solve", str(problem), "--output", str(certificate)],
                base + ["portfolio-verify", str(certificate)],
            )
            for command in commands:
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                self.assertIn("not a release authorization", result.stdout)

            evidence_json = json.loads(evidence.read_text())
            problem_json = json.loads(problem.read_text())
            certificate_json = json.loads(certificate.read_text())
            self.assertTrue(evidence_json["selection_valid"])
            self.assertEqual(evidence_json["coverage"], "simultaneous")
            self.assertAlmostEqual(problem_json["coverage_confidence"], 0.95)
            self.assertAlmostEqual(certificate_json["exact_certificate"]["upper_bound"], 1.0)

            for kind, expected_title in (
                ("portfolio-multinomial-plan", "MultinomialSamplingPlan"),
                ("portfolio-multinomial-counts", "MultinomialCountsFile"),
                ("portfolio-error-budget", "AssuranceErrorBudget"),
                ("portfolio-multinomial-request", "MultinomialEvidenceRequest"),
                ("portfolio-multinomial-evidence", "SimultaneousMultinomialEvidence"),
                ("portfolio-specification", "IncompletePortfolioSpecification"),
            ):
                schema = temp / f"{kind}.json"
                result = subprocess.run(
                    base + ["schema", "--kind", kind, "--output", str(schema)],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                self.assertEqual(json.loads(schema.read_text())["title"], expected_title)

    def test_full_cli_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            request = ROOT / "examples" / "request.json"
            report = temp / "report.json"
            audit = temp / "audit.sqlite3"
            private = temp / "private.pem"
            public = temp / "public.pem"
            manifest = temp / "manifest.json"
            optimization_request = temp / "optimization.json"
            optimization_report = temp / "optimization-report.json"
            optimization_manifest = temp / "optimization-manifest.json"
            base = [sys.executable, "-m", "model_release_assurance"]

            initial_commands = (
                base + ["validate", str(request)],
                base + ["assess", str(request), "--output", str(report), "--audit-db", str(audit)],
            )
            for command in initial_commands:
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            optimization = json.loads((ROOT / "examples" / "optimization-request.json").read_text())
            optimization["configurations"][0]["assessment"] = {
                "report_path": str(report),
                "report_sha256": sha256_file(report),
            }
            optimization["configurations"][0]["release_artifact_path"] = str(
                ROOT / "examples" / "artifacts" / "demo-tree.json"
            )
            optimization["configurations"][0]["utility"]["source_path"] = str(
                ROOT / "examples" / "evidence" / "optimization-utility.json"
            )
            optimization["configurations"][0]["controls"][0]["evidence_path"] = str(
                ROOT / "examples" / "evidence" / "bounded-api-control.json"
            )
            optimization["configurations"][0]["portfolio"]["evidence_path"] = str(
                ROOT / "examples" / "evidence" / "bounded-api-portfolio.json"
            )
            optimization_request.write_text(json.dumps(optimization))

            for command in (
                base + ["optimize", str(optimization_request), "--output", str(optimization_report), "--audit-db", str(audit)],
                base + ["keygen", "--private", str(private), "--public", str(public)],
                base + ["optimize-sign", str(optimization_report), "--private", str(private), "--output", str(optimization_manifest)],
                base + ["optimize-verify", str(optimization_manifest), str(optimization_report), "--public", str(public)],
                base + ["sign", str(request), str(report), "--private", str(private), "--output", str(manifest)],
                base + ["verify", str(manifest), str(report), "--public", str(public)],
                base + ["audit-verify", str(audit)],
            ):
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(json.loads(optimization_report.read_text())["outcome"], "release_with_controls")
            self.assertTrue(json.loads(optimization_manifest.read_text())["fail_safe_gate_passed"])
            tampered = json.loads(optimization_report.read_text())
            tampered["selection_rule"] = "tampered selection rule"
            optimization_report.write_text(json.dumps(tampered))
            result = subprocess.run(
                base + ["optimize-verify", str(optimization_manifest), str(optimization_report), "--public", str(public)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2)

    def test_portfolio_solve_verify_and_tamper_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            evidence_path = temp / "portfolio-source.json"
            evidence_path.write_text(json.dumps({"fixture": "uniform-bit-marginals"}) + "\n")
            evidence_hash = sha256_file(evidence_path)

            def evidence(evidence_id: str, *supports: str) -> EvidenceReference:
                return EvidenceReference(
                    evidence_id=evidence_id,
                    source_path=evidence_path.name,
                    source_sha256=evidence_hash,
                    supports=tuple(supports),
                )

            releases = tuple(
                ConditionalMarginalBounds(
                    release_id=release_id,
                    observation_ids=("0", "1"),
                    lower=((0.5, 0.5), (0.5, 0.5)),
                    upper=((0.5, 0.5), (0.5, 0.5)),
                    evidence=evidence(
                        f"{release_id}-marginal-evidence",
                        f"marginal:{release_id}",
                        "coverage:deterministic",
                    ),
                )
                for release_id in ("release-one", "release-two")
            )
            problem = IncompletePortfolioProblem(
                portfolio_id="cli-xor-portfolio",
                population_scope_id="cli-population",
                population_scope_sha256="a" * 64,
                threat_id="guess-secret",
                decision_game_sha256="b" * 64,
                state_ids=("0", "1"),
                prior=(0.5, 0.5),
                releases=releases,
                decision_problem=exact_guess_problem(("0", "1")),
                coupling_model=CouplingModel.ARBITRARY,
                coverage=StatisticalCoverage.DETERMINISTIC,
                coverage_confidence=1.0,
                selection_scope="complete CLI fixture",
                prior_evidence=evidence("prior-evidence", "prior"),
                mechanism_assumptions=("arbitrary conditional coupling",),
                mechanism_evidence=(
                    evidence("coupling-evidence", "coupling:arbitrary"),
                ),
            )
            problem_path = temp / "problem.json"
            problem_path.write_text(problem.model_dump_json(indent=2) + "\n")
            certificate_path = temp / "detached" / "certificate.json"
            schema_path = temp / "portfolio-schema.json"
            base = [sys.executable, "-m", "model_release_assurance"]

            commands = (
                base + [
                    "portfolio-solve", str(problem_path), "--output", str(certificate_path),
                    "--method", "exact",
                ],
                base + [
                    "portfolio-verify", str(certificate_path), "--evidence-base", str(temp),
                ],
                base + [
                    "schema", "--kind", "portfolio-certificate", "--output", str(schema_path),
                ],
            )
            for command in commands:
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                if command[3] in {"portfolio-solve", "portfolio-verify"}:
                    self.assertIn("not a release authorization", result.stdout)
                    self.assertIn("exact_upper=1/1", result.stdout)
                    self.assertIn("rational_replay=true", result.stdout)

            certificate = json.loads(certificate_path.read_text())
            self.assertAlmostEqual(certificate["exact_certificate"]["upper_bound"], 1.0)
            self.assertEqual(certificate["schema_version"], "1.1")
            self.assertEqual(
                certificate["rational_upper_audit"]["number_interpretation"],
                "exact_decimal_weights_normalized_per_probability_vector",
            )
            self.assertEqual(json.loads(schema_path.read_text())["title"], "AnalyticPortfolioEvidenceEntry")

            certificate["exact_certificate"]["upper_bound"] = 0.5
            certificate_path.write_text(json.dumps(certificate))
            result = subprocess.run(
                base + [
                    "portfolio-verify", str(certificate_path), "--evidence-base", str(temp),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("global upper bound does not replay", result.stderr)


if __name__ == "__main__":
    unittest.main()
