from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .errors import IntegrityError
from .integrity import canonical_json_bytes, sha256_bytes
from .models import AssessmentReport
from .optimizer import OptimizationReport


GENESIS = "0" * 64


class AuditStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                )
                """
            )

    def append_report(self, report: AssessmentReport) -> str:
        return self._append_event("assessment_report", report.assessment_id, report)

    def append_optimization_report(self, report: OptimizationReport) -> str:
        return self._append_event("optimization_report", report.optimization_id, report)

    def _append_event(
        self,
        event_type: str,
        record_id: str,
        report: AssessmentReport | OptimizationReport,
    ) -> str:
        payload = canonical_json_bytes(report).decode("utf-8")
        occurred_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = row[0] if row else GENESIS
            material = json.dumps(
                {
                    "occurred_at": occurred_at,
                    "event_type": event_type,
                    "assessment_id": record_id,
                    "payload_json": payload,
                    "previous_hash": previous,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            event_hash = sha256_bytes(material)
            connection.execute(
                """
                INSERT INTO audit_events
                (occurred_at, event_type, assessment_id, payload_json, previous_hash, event_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (occurred_at, event_type, record_id, payload, previous, event_hash),
            )
        return event_hash

    def verify_chain(self, require_events: bool = False) -> int:
        previous = GENESIS
        count = 0
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT occurred_at, event_type, assessment_id, payload_json, previous_hash, event_hash
                FROM audit_events ORDER BY sequence
                """
            )
            for occurred_at, event_type, assessment_id, payload, stored_previous, stored_hash in rows:
                if stored_previous != previous:
                    raise IntegrityError(f"audit-chain predecessor mismatch at event {count + 1}")
                material = json.dumps(
                    {
                        "occurred_at": occurred_at,
                        "event_type": event_type,
                        "assessment_id": assessment_id,
                        "payload_json": payload,
                        "previous_hash": stored_previous,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                actual = sha256_bytes(material)
                if actual != stored_hash:
                    raise IntegrityError(f"audit-chain hash mismatch at event {count + 1}")
                previous = stored_hash
                count += 1
        if require_events and count == 0:
            raise IntegrityError("audit database contains no events")
        return count
