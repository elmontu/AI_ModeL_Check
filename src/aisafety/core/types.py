"""Shared data models for all safety checkers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    ERROR = "error"
    SKIPPED = "skipped"


class Finding(BaseModel):
    """One discrete safety finding."""

    check_id: str
    title: str
    description: str
    severity: Severity
    status: CheckStatus
    details: dict = Field(default_factory=dict)
    recommendation: str = ""


class CheckResult(BaseModel):
    """Output of a single checker module."""

    checker_name: str
    category: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float = 0.0
    findings: list[Finding] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ReportSummary(BaseModel):
    """Aggregated summary statistics."""

    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    errors: int = 0
    critical_findings: int = 0
    overall_status: CheckStatus = CheckStatus.PASS


class SafetyReport(BaseModel):
    """Unified report from the orchestrator."""

    report_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    target_description: str = ""
    results: list[CheckResult] = Field(default_factory=list)
    summary: ReportSummary = Field(default_factory=ReportSummary)
