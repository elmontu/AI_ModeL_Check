from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .audit import GENESIS
from .integrity import sha256_bytes
from .experimental_workflow import run_experimental_workflow
from .knowledge import KnowledgeIndex
from .model_coverage import assess_request_model_coverage
from .models import AssessmentRequest
from .privacy_orchestration import build_privacy_audit_plan


class AssuranceToolService:
    """Assurance operations suitable for an MCP adapter.

    Most operations are read-only. The experimental privacy runner may write
    only beneath output/ and the public dataset cache; it cannot authorize,
    activate, sign, revoke, append audit events, or commit portfolio state.
    """

    def __init__(self, repository_root: Path, index: KnowledgeIndex | None = None):
        self.repository_root = repository_root.resolve(strict=True)
        self.index = index or KnowledgeIndex.build(self.repository_root)

    def search_assurance_docs(self, query: str, limit: int = 5) -> dict[str, Any]:
        return {
            "advisory_only": True,
            "query": query,
            "results": [asdict(hit) for hit in self.index.search(query, limit=limit)],
        }

    def get_schema(self, schema_name: str) -> dict[str, Any]:
        if not schema_name.endswith(".json") or Path(schema_name).name != schema_name:
            raise ValueError("schema_name must be a JSON filename without a directory")
        schema_root = (self.repository_root / "schemas").resolve(strict=True)
        path = (schema_root / schema_name).resolve(strict=True)
        if path.parent != schema_root or not path.is_file():
            raise ValueError("unknown schema")
        return json.loads(path.read_text(encoding="utf-8"))

    def validate_assessment_request(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = AssessmentRequest.model_validate(request)
        except ValidationError as exc:
            return {"valid": False, "errors": exc.errors(include_url=False)}
        return {
            "valid": True,
            "release_id": parsed.release.release_id,
            "schema_version": parsed.schema_version,
        }

    def review_model_coverage(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = AssessmentRequest.model_validate(request)
        return assess_request_model_coverage(parsed)

    def verify_audit_chain(self, audit_database: str, require_events: bool = True) -> dict[str, Any]:
        candidate = Path(audit_database)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self.repository_root):
            raise ValueError("audit database must be within the repository root")
        if resolved.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
            raise ValueError("audit database must be a SQLite file")
        # URI read-only mode prevents this MCP tool from creating a database,
        # initializing tables, or mutating an existing assurance chain.
        connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
        rows = None
        try:
            rows = connection.execute(
                """
                SELECT occurred_at, event_type, assessment_id, payload_json,
                       previous_hash, event_hash
                FROM audit_events ORDER BY sequence
                """
            )
            previous = GENESIS
            count = 0
            for occurred_at, event_type, assessment_id, payload, stored_previous, stored_hash in rows:
                if stored_previous != previous:
                    raise ValueError(f"audit-chain predecessor mismatch at event {count + 1}")
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
                if sha256_bytes(material) != stored_hash:
                    raise ValueError(f"audit-chain hash mismatch at event {count + 1}")
                previous = stored_hash
                count += 1
        finally:
            if rows is not None:
                rows.close()
            connection.close()
        if require_events and count == 0:
            raise ValueError("audit database contains no events")
        return {"valid": True, "events": count, "path": str(resolved)}

    def run_experimental_workflow(self, manifest_path: str) -> dict[str, Any]:
        candidate = Path(manifest_path)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self.repository_root):
            raise ValueError("experimental manifest must be within the repository root")
        return run_experimental_workflow(resolved, knowledge_index=self.index)

    def read_privacy_audit_report(self, report_path: str) -> dict[str, Any]:
        resolved = Path(report_path).resolve(strict=True)
        if not resolved.is_relative_to(self.repository_root) or resolved.suffix.lower() != ".json":
            raise ValueError("privacy audit report must be a JSON file within the repository root")
        report = json.loads(resolved.read_text(encoding="utf-8"))
        if report.get("evidence_semantics") != "empirical_attack_floors_and_screens_never_clear":
            raise ValueError("report does not declare the required non-clearing evidence semantics")
        if report.get("decision") != "no_release_authorization":
            raise ValueError("privacy experiment must not claim release authorization")
        models = report.get("models")
        if not isinstance(models, list) or not models:
            raise ValueError("privacy audit report has no model results")
        return report

    def plan_privacy_audit(self, seed: int = 20260830, epochs: int = 3) -> dict[str, Any]:
        plan = build_privacy_audit_plan(self.index, seed=seed, epochs=epochs)
        return plan.model_dump(mode="json")

    def run_rag_guided_privacy_audit(
        self,
        seed: int = 20260830,
        epochs: int = 3,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        if not 60 <= timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be between 60 and 3600")
        plan = build_privacy_audit_plan(self.index, seed=seed, epochs=epochs)
        run_root = self.repository_root / "output" / "public-privacy-audit" / plan.plan_sha256[:16]
        run_root.mkdir(parents=True, exist_ok=True)
        plan_path = run_root / "rag-audit-plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        windows_python = self.repository_root / ".privacy-venv" / "Scripts" / "python.exe"
        unix_python = self.repository_root / ".privacy-venv" / "bin" / "python"
        python_executable = windows_python if windows_python.is_file() else unix_python
        if not python_executable.is_file():
            raise RuntimeError("privacy runtime is missing; create .privacy-venv and install privacy dependencies")
        script = self.repository_root / "scripts" / "run_public_privacy_audit.py"
        cache = self.repository_root / "reproduction" / "public-privacy" / "raw"
        completed = subprocess.run(
            [
                str(python_executable), str(script),
                "--plan", str(plan_path),
                "--seed", str(seed),
                "--epochs", str(epochs),
                "--output-dir", str(run_root),
                "--cache-dir", str(cache),
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip()[-4000:]
            raise RuntimeError(f"privacy worker failed with exit code {completed.returncode}: {detail}")
        report_path = run_root / "privacy-audit-report.json"
        report = self.read_privacy_audit_report(str(report_path))
        if report.get("orchestration", {}).get("plan_sha256") != plan.plan_sha256:
            raise ValueError("privacy report is not bound to the MCP/RAG audit plan")
        return report
