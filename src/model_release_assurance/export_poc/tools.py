"""Inert discovery and read-only diagnostics for the synthetic export POC.

This layer cannot prepare, commit, download, or revoke a model. Schema checks
and local hashes are not producer authentication, privacy attestations, or
agency release decisions. The CLI, HTTP discovery endpoint and MCP adapter
share the same catalog rather than maintaining separate capability claims.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import mechanism
from .store import ExportStore


def export_construction_catalog() -> dict[str, Any]:
    """Describe the implemented finite construction; do not run it."""
    return {
        "schema": "mra-export-poc-constructions-v1",
        "scope": "fixed-synthetic-fixture-only",
        "fixture": mechanism.FIXTURE,
        "model_family": "group-bernoulli-forecast",
        "protected_unit": mechanism.PROTECTED_UNIT,
        "adjacency": "replacement of one fixed-roster citizen's two-bit profile; group membership is public and fixed",
        "agency_deployed": False,
        "external_data_supported": False,
        "can_authorize": False,
        "mechanism_source_sha256": hashlib.sha256(Path(mechanism.__file__).read_bytes()).hexdigest(),
        "history": {
            "maximum_committed_stages": 2,
            "initial_history_ratio": 1,
            "first_history_ratio": 2,
            "complete_history_ratio": 4,
            "epsilon_definition": "epsilon = natural logarithm of history_ratio",
            "delta": 0,
            "second_stage_branches_are_alternatives": True,
            "revocation_refunds_privacy": False,
            "new_directory_resets_citizen_exposure": False,
        },
        "first_stage": {
            "request_route": "first",
            "artifact_route": "first-rr",
            "construction": "ratio-2 randomized response of the first bit, then fit public-group Bernoulli forecasts",
        },
        "second_stage_routes": [
            {
                "route": "retained-state",
                "construction": "second-bit randomized response with truth probability 4/5 after a truthful first answer and 3/5 after a flipped answer",
                "required_private_access": "second bit and retained first-response flip; the flip plus first response reconstructs the first bit",
                "evidence": "exact finite binary joint-channel verification at history ratio 4; 11/15 is answer accuracy, not trained-model accuracy",
            },
            {
                "route": "independent",
                "construction": "independent ratio-2 randomized response of the second bit",
                "required_private_access": "second bit",
                "evidence": "standard composition and exact finite binary joint-channel verification at history ratio 4",
            },
            {
                "route": "central-count",
                "construction": "independent two-sided geometric noise of ratio 2 on each fixed public group's second-bit count",
                "required_private_access": "second-bit group counts within the trusted coordinator",
                "evidence": "sensitivity-one count mechanism and sequential composition give a sufficient history ratio of 4; no sharp model-leakage claim",
            },
        ],
        "protocol_coverage": {
            "protected_data_reuse": "identical committed-artifact reuse is planned without a new privacy charge; retrieval rechecks revocation and does not retrain or add a broker stage",
            "joint_extension": "implemented only for the fixed two-bit, two-stage construction",
            "direct_private_training": "implemented only as the central-count sufficient-statistic baseline; no general trainer or DP-SGD adapter",
        },
        "limitations": [
            "No agency dataset adapter, general privacy accountant, or arbitrary model certification.",
            "Mechanism randomness and retained state must remain private; Python tests do not establish production isolation or RNG correctness.",
            "Hashes detect binding drift; a database owner can rewrite data and hashes together.",
            "Recipients retain previously exported bytes; no model recall or privacy-budget refund.",
            "Synthetic workload results do not establish retained-state utility superiority or publication novelty.",
        ],
    }


class ExportToolService:
    """Read-only diagnostics confined to one repository's existing history."""

    def __init__(self, repository_root: Path):
        self.repository_root = Path(repository_root).resolve(strict=True)
        if not self.repository_root.is_dir():
            raise ValueError("repository_root must be an existing directory")

    def list_export_constructions(self) -> dict[str, Any]:
        return export_construction_catalog()

    def inspect_export_bundle(self, model_json: str) -> dict[str, Any]:
        """Check exact supplied UTF-8 JSON bytes without executing a model.

        Hashes refer to the string's UTF-8 encoding, including whitespace and
        any trailing newline. Clients must pass the original decoded UTF-8
        text if they want to compare this digest with an artifact receipt.
        """
        if type(model_json) is not str:
            raise ValueError("model_json must be the exact UTF-8 model JSON text")
        try:
            artifact = model_json.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("model_json must contain valid UTF-8 text") from exc
        bundle = mechanism.inspect_bundle(artifact)
        return {
            "valid": True,
            "validation": "strict schema and metadata allowlist only",
            "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
            "hash_scope": "exact UTF-8 bytes of supplied model_json; no JSON normalization",
            "bytes": len(artifact),
            "schema": bundle["schema"],
            "stage": bundle["stage"],
            "route": bundle["route"],
            "parent_artifact_sha256": bundle["parent_artifact_sha256"],
            "declared_guarantee": bundle["guarantee"],
            "producer_authenticated": False,
            "privacy_attested": False,
            "can_authorize": False,
            "scope": "fixed-synthetic-fixture-only",
        }

    def _history_store(self, data_directory: str) -> ExportStore:
        """Confine every source used by the read-only snapshot opener."""
        if type(data_directory) is not str or not data_directory:
            raise ValueError("data_directory must name an existing repository directory")
        candidate = Path(data_directory)
        if not candidate.is_absolute():
            candidate = self.repository_root / candidate
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self.repository_root) or not resolved.is_dir():
            raise ValueError("export history must be a directory within the repository root")
        database = (resolved / "export.sqlite3").resolve(strict=True)
        if not database.is_relative_to(resolved) or not database.is_file():
            raise ValueError("export database must be a file within its history directory")
        # Snapshot inspection also consumes these optional files. Resolve each
        # separately so a sidecar symlink cannot escape the approved history.
        for name in ("export.sqlite3-wal", ExportStore.MARKER):
            sidecar = resolved / name
            if sidecar.exists() or sidecar.is_symlink():
                target = sidecar.resolve(strict=True)
                if not target.is_relative_to(resolved) or not target.is_file():
                    raise ValueError("export sidecars must be files within their history directory")
        return ExportStore.open_read_only(resolved)

    def plan_export(self, data_directory: str, route: str) -> dict[str, Any]:
        """Plan from validated public history; neither execute nor authorize."""
        from .protocol import plan_export
        return plan_export(self._history_store(data_directory).status(), route)

    def read_export_history(self, data_directory: str) -> dict[str, Any]:
        """Verify an existing history without creating a DB or returning state."""
        verification = self._history_store(data_directory).verify_history()
        return {
            "verification": verification,
            "read_only": True,
            "can_authorize": False,
            "producer_authenticated": False,
            "note": "Local consistency and source-binding diagnostics; not hostile-owner authentication, production validation, or authorization.",
        }
