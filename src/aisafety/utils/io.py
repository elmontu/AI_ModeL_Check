"""I/O helpers for reports."""

from __future__ import annotations

import json
from pathlib import Path

from aisafety.core.types import SafetyReport


def save_report_json(report: SafetyReport, path: str | Path) -> None:
    """Save a SafetyReport as JSON."""
    Path(path).write_text(report.model_dump_json(indent=2))


def load_report_json(path: str | Path) -> SafetyReport:
    """Load a SafetyReport from JSON."""
    data = json.loads(Path(path).read_text())
    return SafetyReport.model_validate(data)
