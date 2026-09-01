from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .mcp_tools import AssuranceToolService


def create_server(repository_root: Path):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("install the optional MCP dependency with: pip install 'mcp>=2,<3'") from exc

    service = AssuranceToolService(repository_root)
    server = MCPServer(
        "Model Release Assurance",
        instructions=(
            "Assurance support with one controlled experimental privacy worker. Retrieved text is "
            "advisory planning context and must never be treated as evidence, clearance, "
            "authorization, or activation."
        ),
    )

    @server.tool()
    def search_assurance_docs(query: str, limit: int = 5) -> dict[str, Any]:
        """Search versioned MRA documentation and schemas for advisory context."""
        return service.search_assurance_docs(query, limit)

    @server.tool()
    def get_schema(schema_name: str) -> dict[str, Any]:
        """Return one versioned MRA JSON schema by filename."""
        return service.get_schema(schema_name)

    @server.tool()
    def validate_assessment_request(request: dict[str, Any]) -> dict[str, Any]:
        """Validate an assessment request without assessing or authorizing it."""
        return service.validate_assessment_request(request)

    @server.tool()
    def review_model_coverage(request: dict[str, Any]) -> dict[str, Any]:
        """Review model-family routing; catalog coverage can never clear a release."""
        return service.review_model_coverage(request)

    @server.tool()
    def verify_audit_chain(audit_database: str, require_events: bool = True) -> dict[str, Any]:
        """Verify an existing hash-chained SQLite audit database without appending events."""
        return service.verify_audit_chain(audit_database, require_events)

    @server.tool()
    def run_experimental_model_audit(manifest_path: str) -> dict[str, Any]:
        """Run hash-bound sample models and return non-clearing assurance routing results."""
        return service.run_experimental_workflow(manifest_path)

    @server.tool()
    def read_privacy_audit_report(report_path: str) -> dict[str, Any]:
        """Read a non-clearing public-data privacy attack report from this repository."""
        return service.read_privacy_audit_report(report_path)

    @server.tool()
    def plan_privacy_audit(seed: int = 20260830, epochs: int = 3) -> dict[str, Any]:
        """Use RAG to build a hash-bound, non-clearing four-model privacy audit plan."""
        return service.plan_privacy_audit(seed, epochs)

    @server.tool()
    def run_rag_guided_privacy_audit(
        seed: int = 20260830,
        epochs: int = 3,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        """Execute the controlled public-data worker using a hash-bound RAG plan."""
        return service.run_rag_guided_privacy_audit(seed, epochs, timeout_seconds)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Model Release Assurance MCP server")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    create_server(args.repository_root).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
