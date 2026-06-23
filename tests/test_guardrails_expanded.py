"""Tests for expanded guardrails checks."""

from aisafety.checkers.llm_guardrails import LLMGuardrailsChecker


def test_guardrails_pii_redaction(mock_llm_endpoint):
    checker = LLMGuardrailsChecker()
    result = checker.check(llm_endpoint=mock_llm_endpoint)
    assert result.category == "llm_guardrails"
    # Should have multiple findings now (PII, output filtering, token limits, etc.)
    assert len(result.findings) >= 3


def test_guardrails_sample_outputs():
    checker = LLMGuardrailsChecker()
    outputs = [
        "The user's email is john@example.com and SSN is 123-45-6789.",
        "Normal response without PII.",
        "<script>alert('xss')</script>",
    ]
    result = checker.check(sample_outputs=outputs)

    pii = next((f for f in result.findings if "pii" in f.check_id.lower()), None)
    assert pii is not None
    assert pii.status.value == "fail"

    dangerous = next((f for f in result.findings if "dangerous" in f.check_id.lower()), None)
    assert dangerous is not None


def test_guardrails_error_responses():
    checker = LLMGuardrailsChecker()
    errors = [
        "Internal server error at line 42 in file /app/server.py",
        "Something went wrong. Please try again.",
        "Database error: connection to postgres refused",
    ]
    result = checker.check(error_responses=errors)

    leakage = next((f for f in result.findings if "leakage" in f.check_id), None)
    assert leakage is not None
    assert leakage.status.value == "warn"


def test_guardrails_clean_errors():
    checker = LLMGuardrailsChecker()
    errors = [
        "Something went wrong. Please try again.",
        "Request could not be processed.",
    ]
    result = checker.check(error_responses=errors)

    leakage = next((f for f in result.findings if "leakage" in f.check_id), None)
    assert leakage is not None
    assert leakage.status.value == "pass"
