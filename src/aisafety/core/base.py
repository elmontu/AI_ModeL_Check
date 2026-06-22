"""Abstract base class for all safety checkers."""

from __future__ import annotations

import importlib
import time
from abc import ABC, abstractmethod

from aisafety.core.types import CheckResult, CheckStatus, Finding, Severity


class BaseChecker(ABC):
    """All checker modules inherit from this."""

    name: str = "BaseChecker"
    category: str = "base"
    requires: list[str] = []

    @abstractmethod
    def check(self, **kwargs) -> CheckResult:
        """Run all checks in this module."""
        ...

    def is_available(self) -> bool:
        """Return True if required dependencies are installed."""
        for pkg in self.requires:
            try:
                importlib.import_module(pkg)
            except ImportError:
                return False
        return True

    def missing_dependencies(self) -> list[str]:
        """Return list of missing dependency package names."""
        missing = []
        for pkg in self.requires:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)
        return missing

    def _make_result(
        self,
        findings: list[Finding],
        metadata: dict | None = None,
        duration: float = 0.0,
    ) -> CheckResult:
        return CheckResult(
            checker_name=self.name,
            category=self.category,
            duration_seconds=duration,
            findings=findings,
            metadata=metadata or {},
        )

    def _make_finding(
        self,
        check_id: str,
        title: str,
        description: str,
        severity: Severity,
        status: CheckStatus,
        details: dict | None = None,
        recommendation: str = "",
    ) -> Finding:
        return Finding(
            check_id=f"{self.category}.{check_id}",
            title=title,
            description=description,
            severity=severity,
            status=status,
            details=details or {},
            recommendation=recommendation,
        )

    def _timed_check(self, **kwargs) -> CheckResult:
        """Run check() with timing."""
        start = time.perf_counter()
        result = self.check(**kwargs)
        result.duration_seconds = time.perf_counter() - start
        return result
