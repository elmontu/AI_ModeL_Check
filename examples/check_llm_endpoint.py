#!/usr/bin/env python3
"""Example: Run prompt safety + content safety checks on an LLM endpoint."""

import os

from aisafety.checkers.llm_prompt_safety import LLMPromptSafetyChecker
from aisafety.checkers.llm_content_safety import LLMContentSafetyChecker
from aisafety.checkers.llm_guardrails import LLMGuardrailsChecker
from aisafety.core.report import ReportBuilder


def main():
    # Option 1: Use a real API endpoint
    # from aisafety.utils.llm_client import make_openai_endpoint
    # endpoint = make_openai_endpoint(model="gpt-4o-mini", system_prompt="You are a helpful assistant.")

    # Option 2: Use a mock endpoint for demo
    def mock_endpoint(prompt: str) -> str:
        prompt_lower = prompt.lower()
        harmful = ["bomb", "hack", "weapon", "malware", "phishing", "harm"]
        if any(kw in prompt_lower for kw in harmful):
            return "I'm sorry, I cannot assist with that request."
        if "ignore" in prompt_lower and "instruction" in prompt_lower:
            return "I cannot comply with attempts to override my instructions."
        if "earth is flat" in prompt_lower:
            return "Actually, the Earth is not flat. It is an oblate spheroid."
        return f"Here is a helpful response about: {prompt[:50]}"

    endpoint = mock_endpoint
    builder = ReportBuilder(target_description="Mock LLM endpoint")

    # 1. Prompt Safety
    print("Running prompt safety checks...")
    checker = LLMPromptSafetyChecker()
    result = checker._timed_check(
        llm_endpoint=endpoint,
        system_prompt="You are a helpful assistant. Be safe and accurate.",
    )
    builder.add_result(result)
    for f in result.findings:
        print(f"  [{f.status.value}] {f.title}: {f.description}")

    # 2. Content Safety
    print("\nRunning content safety checks...")
    content_checker = LLMContentSafetyChecker()
    if content_checker.is_available():
        result = content_checker._timed_check(llm_endpoint=endpoint)
        builder.add_result(result)
        for f in result.findings:
            print(f"  [{f.status.value}] {f.title}: {f.description}")
    else:
        print("  Content safety checker not available (install detoxify)")

    # 3. Guardrails
    print("\nRunning guardrails checks...")
    guardrails = LLMGuardrailsChecker()
    result = guardrails._timed_check(llm_endpoint=endpoint)
    builder.add_result(result)
    for f in result.findings:
        print(f"  [{f.status.value}] {f.title}: {f.description}")

    # Generate report
    report = builder.build()
    builder.to_json("llm_safety_report.json")
    print(f"\n--- Summary ---")
    print(f"Total checks: {report.summary.total_checks}")
    print(f"Passed: {report.summary.passed}, Failed: {report.summary.failed}")
    print(f"Overall: {report.summary.overall_status.value}")
    print(f"Report saved to llm_safety_report.json")


if __name__ == "__main__":
    main()
