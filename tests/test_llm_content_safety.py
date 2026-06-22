"""Tests for the LLM Content Safety checker."""

import pytest

from aisafety.checkers.llm_content_safety import LLMContentSafetyChecker


def test_content_safety_no_endpoint():
    checker = LLMContentSafetyChecker()
    result = checker.check()
    assert result.findings[0].status.value == "skipped"


def test_content_safety_refusal(mock_llm_endpoint):
    checker = LLMContentSafetyChecker()
    if not checker.is_available():
        pytest.skip("detoxify not installed")

    result = checker.check(llm_endpoint=mock_llm_endpoint)

    assert result.category == "llm_content_safety"
    # Should have toxicity, refusal, and sycophancy findings
    check_ids = [f.check_id for f in result.findings]
    assert any("refusal" in cid for cid in check_ids)


def test_content_safety_sycophancy(mock_llm_endpoint):
    checker = LLMContentSafetyChecker()
    if not checker.is_available():
        pytest.skip("detoxify not installed")

    result = checker.check(llm_endpoint=mock_llm_endpoint)

    sycophancy = next((f for f in result.findings if "sycophancy" in f.check_id), None)
    if sycophancy:
        # Mock endpoint corrects wrong facts, so sycophancy should be low
        assert sycophancy.details.get("sycophancy_rate", 1.0) < 0.5
