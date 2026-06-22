"""Report builder — aggregates CheckResults into a unified SafetyReport."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aisafety.core.types import CheckResult, CheckStatus, ReportSummary, SafetyReport, Severity


class ReportBuilder:
    """Collects checker results and produces a unified safety report."""

    def __init__(self, target_description: str = ""):
        self._target = target_description
        self._results: list[CheckResult] = []

    def add_result(self, result: CheckResult) -> None:
        self._results.append(result)

    def build(self) -> SafetyReport:
        summary = self._summarize()
        return SafetyReport(
            report_id=f"sr-{uuid.uuid4().hex[:12]}",
            generated_at=datetime.now(timezone.utc),
            target_description=self._target,
            results=self._results,
            summary=summary,
        )

    def _summarize(self) -> ReportSummary:
        passed = 0
        failed = 0
        warnings = 0
        errors = 0
        critical = 0
        total = 0

        for result in self._results:
            for finding in result.findings:
                total += 1
                match finding.status:
                    case CheckStatus.PASS:
                        passed += 1
                    case CheckStatus.FAIL:
                        failed += 1
                    case CheckStatus.WARN:
                        warnings += 1
                    case CheckStatus.ERROR:
                        errors += 1
                if finding.severity == Severity.CRITICAL:
                    critical += 1

        if failed > 0 or critical > 0:
            overall = CheckStatus.FAIL
        elif errors > 0:
            overall = CheckStatus.ERROR
        elif warnings > 0:
            overall = CheckStatus.WARN
        else:
            overall = CheckStatus.PASS

        return ReportSummary(
            total_checks=total,
            passed=passed,
            failed=failed,
            warnings=warnings,
            errors=errors,
            critical_findings=critical,
            overall_status=overall,
        )

    def to_json(self, path: str | Path | None = None) -> str:
        report = self.build()
        data = report.model_dump_json(indent=2)
        if path:
            Path(path).write_text(data)
        return data

    def to_dict(self) -> dict:
        return self.build().model_dump(mode="json")
