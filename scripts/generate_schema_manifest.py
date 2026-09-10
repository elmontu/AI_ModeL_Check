#!/usr/bin/env python3
"""Generate or verify the current-schema byte inventory.

The checked-in manifest is intentionally unsigned. Release infrastructure must
sign or attest the exact manifest bytes using a protected identity; committing a
private key or a self-signed repository artifact would not add a trust anchor.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from model_release_assurance.schema_registry import (
    SCHEMA_MANIFEST_FILENAME,
    SCHEMA_REGISTRY,
    render_schema_manifest,
    validate_schema_registry,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMAS_DIR = ROOT / "schemas"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def schema_replay_errors(schemas_dir: Path) -> list[str]:
    """Return deterministic diagnostics for missing or stale current schemas."""

    errors: list[str] = []
    allowed = {entry.filename for entry in SCHEMA_REGISTRY.values()} | {SCHEMA_MANIFEST_FILENAME}
    for path in sorted(schemas_dir.glob("*.json")):
        if path.name not in allowed:
            errors.append(f"unregistered or retired schema in active directory: {path.name}")
    for kind in sorted(SCHEMA_REGISTRY):
        registration = SCHEMA_REGISTRY[kind]
        path = schemas_dir / registration.filename
        if not path.is_file():
            errors.append(f"{kind}: missing {path}")
            continue
        actual = path.read_bytes()
        expected = registration.rendered_bytes()
        if actual != expected:
            errors.append(
                f"{kind}: {registration.filename} is stale "
                f"(committed={_sha256(actual)}, generated={_sha256(expected)})"
            )
    return errors


def manifest_check_errors(schemas_dir: Path, manifest_path: Path) -> list[str]:
    """Return deterministic diagnostics for schema or manifest drift."""

    errors = schema_replay_errors(schemas_dir)
    if errors:
        return errors
    expected = render_schema_manifest(schemas_dir)
    if not manifest_path.is_file():
        return [f"manifest: missing {manifest_path}"]
    actual = manifest_path.read_bytes()
    if actual != expected:
        return [
            f"manifest: {manifest_path.name} is stale "
            f"(committed={_sha256(actual)}, generated={_sha256(expected)})"
        ]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="generate or check the deterministic current JSON Schema manifest"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="write the manifest after confirming every registered schema is current",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="fail if a current schema or the committed manifest differs from generation",
    )
    parser.add_argument("--schemas-dir", type=Path, default=DEFAULT_SCHEMAS_DIR)
    parser.add_argument("--refresh-schemas", action="store_true",
                        help="with --write, regenerate every currently registered versioned schema before manifesting")
    parser.add_argument(
        "--output",
        type=Path,
        help=f"manifest path (default: SCHEMAS_DIR/{SCHEMA_MANIFEST_FILENAME})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    schemas_dir = args.schemas_dir.resolve()
    manifest_path = (
        args.output.resolve()
        if args.output is not None
        else schemas_dir / SCHEMA_MANIFEST_FILENAME
    )
    try:
        validate_schema_registry()
        if args.refresh_schemas and not args.write:
            raise ValueError("--refresh-schemas requires --write")
        if args.refresh_schemas:
            schemas_dir.mkdir(parents=True, exist_ok=True)
            for registration in SCHEMA_REGISTRY.values():
                (schemas_dir / registration.filename).write_bytes(registration.rendered_bytes())
        if args.check:
            errors = manifest_check_errors(schemas_dir, manifest_path)
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            print(
                f"verified {len(SCHEMA_REGISTRY)} current schemas and {manifest_path.name} "
                f"(sha256={_sha256(manifest_path.read_bytes())})"
            )
            return 0

        errors = schema_replay_errors(schemas_dir)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            print(
                "refusing to manifest stale schema bytes; regenerate the named schemas first",
                file=sys.stderr,
            )
            return 1
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_schema_manifest(schemas_dir)
        manifest_path.write_bytes(rendered)
        print(f"wrote {manifest_path} (sha256={_sha256(rendered)})")
        return 0
    except (OSError, ValueError) as exc:
        print(f"schema manifest error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
