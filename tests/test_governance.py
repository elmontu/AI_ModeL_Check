"""Tests for the Governance checker."""

import tempfile
from pathlib import Path

from aisafety.checkers.common.governance import GovernanceChecker
from aisafety.core.types import CheckResult, CheckStatus, Finding, SafetyReport, Severity, ReportSummary


def test_governance_no_info():
    checker = GovernanceChecker()
    result = checker.check()
    assert result.category == "governance"
    # Should flag missing model card fields
    completeness = next(f for f in result.findings if "completeness" in f.check_id)
    assert completeness.status.value in ("fail", "warn")


def test_governance_complete_info():
    checker = GovernanceChecker()
    info = {
        "name": "Test Model",
        "version": "1.0",
        "description": "A test model",
        "intended_use": "Testing",
        "training_data": "Synthetic data",
        "limitations": "None known",
        "ethical_considerations": "None",
    }
    result = checker.check(model_info=info)
    completeness = next(f for f in result.findings if "completeness" in f.check_id)
    assert completeness.status.value == "pass"


def test_governance_model_card_generation():
    checker = GovernanceChecker()
    info = {
        "name": "Test Model",
        "version": "1.0",
        "description": "A test model",
        "intended_use": "Testing",
        "training_data": "Synthetic",
        "limitations": "None",
        "ethical_considerations": "None",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        path = f.name

    result = checker.check(model_info=info, output_path=path)
    content = Path(path).read_text()

    assert "Test Model" in content
    assert "Model Card" in content


def test_governance_nist_mapping():
    checker = GovernanceChecker()

    report = SafetyReport(
        report_id="test",
        target_description="Test",
        results=[
            CheckResult(
                checker_name="FairnessChecker",
                category="fairness",
                findings=[
                    Finding(check_id="fairness.demographic_parity", title="DP", description="ok",
                            severity=Severity.INFO, status=CheckStatus.PASS),
                ],
            ),
        ],
        summary=ReportSummary(total_checks=1, passed=1),
    )

    result = checker.check(model_info={"name": "Test"}, safety_report=report, framework="nist")
    nist = next((f for f in result.findings if "nist" in f.check_id), None)
    assert nist is not None
