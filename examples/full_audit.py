#!/usr/bin/env python3
"""Example: Run a full safety audit using the config-driven orchestrator."""

import tempfile
from pathlib import Path

from aisafety.core.config import DEFAULT_CONFIG_TEMPLATE


def main():
    # Write a config file
    config_path = Path(tempfile.mktemp(suffix=".yaml"))
    config_path.write_text(DEFAULT_CONFIG_TEMPLATE)

    print(f"Config written to {config_path}")
    print("Run the audit with:")
    print(f"  aisafety audit {config_path}")
    print()
    print("Or run individual checkers:")
    print("  aisafety list                          # see available checkers")
    print("  aisafety run fairness --config config.yaml")
    print("  aisafety run llm_prompt_safety --config config.yaml")
    print()
    print("To use programmatically:")
    print()

    # Programmatic usage
    import numpy as np
    from aisafety.checkers.llm.agentic_safety import AgenticSafetyChecker
    from aisafety.checkers.common.alignment import AlignmentChecker
    from aisafety.checkers.common.governance import GovernanceChecker
    from aisafety.core.report import ReportBuilder

    builder = ReportBuilder(target_description="Full audit demo")

    # Agentic safety check
    agentic = AgenticSafetyChecker()
    result = agentic.check(
        tool_definitions=[
            {"name": "search", "description": "Search the web"},
            {"name": "shell_exec", "description": "Run shell commands"},
        ],
        tool_call_logs=[
            {"tool": "search", "status": "success"},
            {"tool": "search", "status": "success"},
            {"tool": "shell_exec", "status": "success"},
        ],
    )
    builder.add_result(result)
    print("Agentic Safety:")
    for f in result.findings:
        print(f"  [{f.status.value}] {f.title}")

    # Alignment check
    rng = np.random.default_rng(42)
    trajectories = [
        {"states": rng.random((10, 4)).tolist(), "actions": rng.integers(0, 3, 10).tolist(),
         "rewards": rng.random(10).tolist()}
        for _ in range(15)
    ]
    alignment = AlignmentChecker()
    result = alignment.check(trajectories=trajectories)
    builder.add_result(result)
    print("\nAlignment:")
    for f in result.findings:
        print(f"  [{f.status.value}] {f.title}")

    # Governance
    gov = GovernanceChecker()
    report = builder.build()
    result = gov.check(
        model_info={
            "name": "Demo Model",
            "version": "0.1",
            "description": "A demonstration model",
            "intended_use": "Educational purposes",
            "training_data": "Synthetic data",
            "limitations": "Not for production use",
            "ethical_considerations": "None — demo only",
        },
        safety_report=report,
        framework="nist",
    )
    builder.add_result(result)
    print("\nGovernance:")
    for f in result.findings:
        print(f"  [{f.status.value}] {f.title}")

    # Final report
    final = builder.build()
    builder.to_json("full_audit_report.json")
    print(f"\n--- Final Summary ---")
    print(f"Total: {final.summary.total_checks} | Pass: {final.summary.passed} | "
          f"Fail: {final.summary.failed} | Warn: {final.summary.warnings}")
    print(f"Overall: {final.summary.overall_status.value.upper()}")
    print("Report saved to full_audit_report.json")


if __name__ == "__main__":
    main()
