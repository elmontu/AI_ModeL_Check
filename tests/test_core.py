"""Tests for core types, registry, and report builder."""

from aisafety.core.types import CheckResult, CheckStatus, Finding, Severity
from aisafety.core.report import ReportBuilder
from aisafety.core.registry import register_checker, get_all_checkers, get_checker
from aisafety.core.base import BaseChecker
from aisafety.core.config import load_config, DEFAULT_CONFIG_TEMPLATE

import pytest
import tempfile
from pathlib import Path


def test_finding_creation():
    f = Finding(
        check_id="test.check",
        title="Test Finding",
        description="A test",
        severity=Severity.HIGH,
        status=CheckStatus.FAIL,
    )
    assert f.severity == Severity.HIGH
    assert f.status == CheckStatus.FAIL


def test_check_result_creation():
    r = CheckResult(checker_name="TestChecker", category="test")
    assert r.findings == []
    assert r.checker_name == "TestChecker"


def test_report_builder():
    builder = ReportBuilder(target_description="Test model")

    result = CheckResult(
        checker_name="TestChecker",
        category="test",
        findings=[
            Finding(check_id="t.1", title="Pass", description="ok",
                    severity=Severity.INFO, status=CheckStatus.PASS),
            Finding(check_id="t.2", title="Fail", description="bad",
                    severity=Severity.HIGH, status=CheckStatus.FAIL),
        ],
    )
    builder.add_result(result)
    report = builder.build()

    assert report.summary.total_checks == 2
    assert report.summary.passed == 1
    assert report.summary.failed == 1
    assert report.summary.overall_status == CheckStatus.FAIL


def test_report_builder_all_pass():
    builder = ReportBuilder()
    result = CheckResult(
        checker_name="Test",
        category="test",
        findings=[
            Finding(check_id="t.1", title="OK", description="",
                    severity=Severity.INFO, status=CheckStatus.PASS),
        ],
    )
    builder.add_result(result)
    report = builder.build()
    assert report.summary.overall_status == CheckStatus.PASS


def test_report_to_json():
    builder = ReportBuilder(target_description="Test")
    result = CheckResult(
        checker_name="Test", category="test",
        findings=[Finding(check_id="t.1", title="OK", description="",
                          severity=Severity.INFO, status=CheckStatus.PASS)],
    )
    builder.add_result(result)
    json_str = builder.to_json()
    assert "Test" in json_str
    assert '"pass"' in json_str


def test_config_loading():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(DEFAULT_CONFIG_TEMPLATE)
        f.flush()
        config = load_config(f.name)

    assert config.target["description"] == "My AI Model"
    assert "fairness" in config.checkers
    assert config.checkers["fairness"].enabled is True
    assert config.checkers["adversarial"].enabled is False


def test_registry():
    # Ensure importing checkers populates the registry
    import aisafety.checkers  # noqa: F401
    checkers = get_all_checkers()
    assert len(checkers) >= 11
    assert "fairness" in checkers
    assert "adversarial" in checkers
    assert "llm_prompt_safety" in checkers


def test_get_unknown_checker():
    with pytest.raises(KeyError):
        get_checker("nonexistent_checker")
