#!/usr/bin/env python3
"""Run deterministic regressions for the controls added after the design critique.

This is an executable implementation check, not a safety score, scientific
adequacy study, production-registry test, or trusted-build attestation.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
for search_path in (ROOT, ROOT / "src"):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from model_release_assurance.runtime_identity import (  # noqa: E402
    current_runtime_identity,
)


CASES = (
    (
        "complete_interface_contract",
        "tests.test_framework.ContractTests."
        "test_complete_interface_requires_every_structured_channel_declaration",
    ),
    (
        "future_registry_snapshot",
        "tests.test_decision_theory.ReleaseOptimizerTests."
        "test_future_dated_portfolio_registry_snapshot_is_rejected",
    ),
    (
        "selection_policy_allowlist",
        "tests.test_contract_v4.OptimizationContractV3Tests."
        "test_selection_policy_must_be_authorized_by_active_policy",
    ),
    (
        "evidence_disposition",
        "tests.test_contract_v4.AssessmentContractV4Tests."
        "test_report_dispositions_name_every_included_and_excluded_record",
    ),
    (
        "signed_interface_binding",
        "tests.test_contract_v4.AssessmentContractV4Tests."
        "test_report_and_manifest_expose_non_authorizing_scope",
    ),
    (
        "audit_metadata_binding",
        "tests.test_audit_v2.AuditV2Tests."
        "test_domain_hash_binds_ledger_and_rejects_metadata_tampering",
    ),
    (
        "audit_splice_resistance",
        "tests.test_audit_v2.AuditV2Tests."
        "test_spliced_events_and_fresh_ledger_impersonation_fail",
    ),
    (
        "registry_sequence_contiguity",
        "tests.test_release_protocol.ReleaseProtocolTests."
        "test_registry_sequence_cannot_jump_forward",
    ),
    (
        "registry_head_replay",
        "tests.test_release_protocol.ReleaseProtocolTests."
        "test_registry_head_is_recomputed_from_commitment",
    ),
    (
        "runtime_identity_replay",
        "tests.test_runtime_identity.RuntimeIdentityTests."
        "test_package_source_digest_and_profile_are_deterministic",
    ),
    (
        "cli_block_outcome",
        "tests.test_cli.CliTests.test_block_is_a_successful_cli_domain_outcome",
    ),
    (
        "binary64_boundary_diagnostic",
        "tests.test_critique_regressions.ContradictoryEvidenceRegressionTests."
        "test_binary64_boundary_is_an_explicit_conformance_gap",
    ),
)


def _run_case(test_name: str) -> tuple[bool, str, int]:
    stream = StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(test_name)
    count = suite.countTestCases()
    with redirect_stdout(stream), redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    return result.wasSuccessful(), stream.getvalue().strip(), count


def evaluate() -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for control_id, test_name in CASES:
        passed, detail, count = _run_case(test_name)
        cases.append(
            {
                "control_id": control_id,
                "test": test_name,
                "test_count": count,
                "passed": passed,
                "detail": detail,
            }
        )

    literal_boundary = 0.6
    computed_boundary = 0.2 + 0.4
    runtime = current_runtime_identity(
        component_id="design_control_evaluator",
        component_version="DesignControlEvaluation/1.0",
        algorithm_profile={
            "case_execution": "named unittest regressions",
            "aggregation": "raw pass counts only",
            "safety_score_emitted": False,
        },
    )
    passed = sum(bool(case["passed"]) for case in cases)
    discovered = sum(int(case["test_count"]) for case in cases)
    expected = len(cases)
    return {
        "schema_version": "1.0",
        "evaluation_id": "post-critique-design-control-regressions-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_identity": runtime.model_dump(mode="json"),
        "case_count": expected,
        "discovered_test_count": discovered,
        "passed_case_count": passed,
        "all_expected_controls_observed": passed == expected and discovered == expected,
        "cases": cases,
        "known_gap_observations": [
            {
                "gap_id": "MRAP-G7-BINARY64",
                "literal_boundary": repr(literal_boundary),
                "literal_boundary_hex": literal_boundary.hex(),
                "computed_boundary_expression": "0.2 + 0.4",
                "computed_boundary": repr(computed_boundary),
                "computed_boundary_hex": computed_boundary.hex(),
                "representation_sensitive": computed_boundary > literal_boundary,
                "disposition": (
                    "Present conformance blocker for ordinary clearance boundaries; "
                    "the optimizer does not invoke SciPy, and this observation is not a risk rate."
                ),
            }
        ],
        "external_controls_not_tested": [
            "authoritative registry completeness and linearizable inclusion",
            "trusted build allowlists, SBOM custody, and release attestation",
            "selection-stage issuer authentication beyond policy preference allowlisting",
            "live gateway conformance and enforcement",
            "scientific adequacy of model-risk evidence",
        ],
        "non_claim": (
            "Passing cases demonstrate the enumerated executable regressions only. "
            "They do not authorize a release or estimate unobserved defect coverage."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    return 0 if report["all_expected_controls_observed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
