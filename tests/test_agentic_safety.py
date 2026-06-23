"""Tests for the Agentic Safety checker."""

from aisafety.checkers.llm.agentic_safety import AgenticSafetyChecker


def test_agentic_tool_definitions(sample_tool_definitions):
    checker = AgenticSafetyChecker()
    result = checker.check(tool_definitions=sample_tool_definitions)

    assert result.category == "agentic_safety"
    assert len(result.findings) >= 1

    # Should detect high-risk tools (shell_exec, file_write, send_email)
    high_risk = next((f for f in result.findings if "high_risk" in f.check_id), None)
    assert high_risk is not None


def test_agentic_tool_call_validation(sample_tool_definitions, sample_tool_call_logs):
    checker = AgenticSafetyChecker()
    result = checker.check(
        tool_definitions=sample_tool_definitions,
        tool_call_logs=sample_tool_call_logs,
    )

    assert len(result.findings) >= 1


def test_agentic_escalation_detection():
    checker = AgenticSafetyChecker()
    # Simulate escalation: low → medium → high
    logs = [
        {"tool": "calculator", "status": "success"},
        {"tool": "file_read", "status": "success"},
        {"tool": "shell_exec", "status": "success"},
    ]
    result = checker.check(tool_call_logs=logs)

    escalation = next((f for f in result.findings if "escalation" in f.check_id), None)
    assert escalation is not None


def test_agentic_excessive_agency():
    checker = AgenticSafetyChecker()
    logs = [{"tool": "shell_exec", "status": "success"} for _ in range(6)]
    result = checker.check(tool_call_logs=logs)

    excessive = next((f for f in result.findings if "excessive" in f.check_id), None)
    assert excessive is not None
    assert excessive.status.value == "fail"


def test_agentic_no_data():
    checker = AgenticSafetyChecker()
    result = checker.check()
    assert result.findings[0].status.value == "skipped"
