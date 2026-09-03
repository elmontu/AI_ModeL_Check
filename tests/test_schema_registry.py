from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from model_release_assurance.schema_registry import (
    PACKAGE_NAME,
    SCHEMA_MANIFEST_FILENAME,
    SCHEMA_REGISTRY,
    render_schema_manifest,
    schema_manifest,
    validate_schema_registry,
)
from model_release_assurance.version import VERSION
from scripts.generate_schema_manifest import manifest_check_errors


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


class SchemaRegistryTests(unittest.TestCase):
    def test_registry_is_unique_and_matches_model_declarations(self) -> None:
        validate_schema_registry()
        self.assertEqual(len(SCHEMA_REGISTRY), 32)
        self.assertEqual(len({entry.filename for entry in SCHEMA_REGISTRY.values()}), 32)
        for kind, registration in SCHEMA_REGISTRY.items():
            self.assertEqual(kind, registration.kind)
            schema = registration.rendered_schema()
            self.assertEqual(schema["title"], registration.model.__name__)
            self.assertEqual(
                schema["properties"]["schema_version"]["const"],
                registration.declared_schema_version,
            )

    def test_committed_manifest_is_the_exact_deterministic_inventory(self) -> None:
        manifest_path = SCHEMAS / SCHEMA_MANIFEST_FILENAME
        self.assertEqual(manifest_path.read_bytes(), render_schema_manifest(SCHEMAS))
        manifest = schema_manifest(SCHEMAS)
        self.assertEqual(manifest["package_name"], PACKAGE_NAME)
        self.assertEqual(manifest["package_version"], VERSION)
        self.assertEqual(manifest["digest_algorithm"], "sha256")
        self.assertEqual(manifest["digest_scope"], "exact_file_bytes")
        self.assertEqual(len(manifest["contracts"]), len(SCHEMA_REGISTRY))
        self.assertFalse(manifest["attestation"]["committed_signature"])
        self.assertTrue(manifest["attestation"]["release_attestation_required"])

    def test_checker_detects_schema_byte_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schemas = Path(directory)
            for registration in SCHEMA_REGISTRY.values():
                (schemas / registration.filename).write_bytes(registration.rendered_bytes())
            manifest_path = schemas / SCHEMA_MANIFEST_FILENAME
            manifest_path.write_bytes(render_schema_manifest(schemas))
            self.assertEqual(manifest_check_errors(schemas, manifest_path), [])

            target = schemas / SCHEMA_REGISTRY["request"].filename
            target.write_bytes(target.read_bytes() + b" ")
            errors = manifest_check_errors(schemas, manifest_path)
            self.assertEqual(len(errors), 1)
            self.assertIn("request", errors[0])
            self.assertIn("is stale", errors[0])

    def test_manifest_has_complete_machine_readable_fields(self) -> None:
        manifest = json.loads(render_schema_manifest(SCHEMAS))
        required = {
            "kind",
            "model_import",
            "model_title",
            "filename",
            "declared_schema_version",
            "sha256",
        }
        self.assertEqual(
            [entry["kind"] for entry in manifest["contracts"]],
            sorted(SCHEMA_REGISTRY),
        )
        for entry in manifest["contracts"]:
            self.assertEqual(set(entry), required)
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
