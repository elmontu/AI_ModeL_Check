"""Deterministic source-swap regressions for captured-byte trust boundaries."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pydantic import BaseModel

from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import (
    canonical_json_bytes, read_verified_source_bytes, sha256_bytes, verify_provenance_binding,
)
from model_release_assurance.models import AssessmentRequest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class SmallClaim(BaseModel):
    value: int


class VerifiedSourceReadTests(unittest.TestCase):
    def test_helper_hashes_and_returns_same_capture_despite_path_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.json"
            good, replacement = b'{"value":1}', b'{"value":999}'
            source.write_bytes(good)
            original_read = Path.read_bytes
            captures = []
            def read_then_swap(path):
                result = original_read(path)
                if path == source:
                    captures.append(result)
                    source.write_bytes(replacement)
                return result
            with patch.object(Path, "read_bytes", read_then_swap), patch(
                "model_release_assurance.integrity.sha256_file",
                side_effect=AssertionError("captured-byte verifier must not hash a separate open"),
            ):
                captured = read_verified_source_bytes(source.name, sha256_bytes(good), base)
            self.assertEqual(captured, good)
            self.assertEqual(captures, [good])
            self.assertEqual(source.read_bytes(), replacement)

    def test_helper_rejects_swapped_bytes_before_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.json"
            source.write_bytes(b'{"value":999}')
            with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
                read_verified_source_bytes(source.name, sha256_bytes(b'{"value":1}'), base)

    def test_provenance_uses_supplied_capture_without_reopening_path(self):
        captured = b'{"value":1}'
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected path reread")):
            verify_provenance_binding(SmallClaim(value=1), Path("not-needed.json"), ("value",),
                source_bytes=captured, expected_sha256=sha256_bytes(captured))

    def test_provenance_authenticates_supplied_capture_not_just_its_fields(self):
        with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
            verify_provenance_binding(SmallClaim(value=999), Path("not-needed.json"), ("value",),
                source_bytes=b'{"value":999}', expected_sha256=sha256_bytes(b'{"value":1}'))

    def test_provenance_preserves_strict_utf8_requirement(self):
        captured = '{"value":1}'.encode("utf-16")
        with self.assertRaisesRegex(IntegrityError, "not valid UTF-8 JSON"):
            verify_provenance_binding(SmallClaim(value=1), Path("not-needed.json"), ("value",),
                source_bytes=captured, expected_sha256=sha256_bytes(captured))

    def test_engine_policy_uses_verified_capture_after_malicious_file_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shutil.copytree(EXAMPLES, base, dirs_exist_ok=True)
            raw = json.loads((base / "request.json").read_text(encoding="utf-8"))
            removed = next(t["threat_id"] for t in raw["threats"] if t["kind"] == "membership")
            raw["threats"] = [t for t in raw["threats"] if t["threat_id"] != removed]
            raw["analyzer_inputs"] = [i for i in raw["analyzer_inputs"] if i["threat_id"] != removed]
            request = AssessmentRequest.model_validate(raw)
            policy_path = (base / request.policy.policy_path).resolve()
            malicious = json.loads(policy_path.read_text(encoding="utf-8"))
            next(r for r in malicious["rules"] if r["threat_id"] == removed)["mandatory"] = False
            malicious_bytes = canonical_json_bytes(malicious)
            swapped = []
            def capture_then_swap(source_path, expected, base_dir):
                captured = read_verified_source_bytes(source_path, expected, base_dir)
                path = Path(source_path)
                path = (path if path.is_absolute() else base_dir / path).resolve()
                if path == policy_path:
                    path.write_bytes(malicious_bytes)
                    swapped.append(path)
                return captured
            with patch("model_release_assurance.engine.read_verified_source_bytes", side_effect=capture_then_swap):
                with self.assertRaisesRegex(ValueError, "omits mandatory policy threats"):
                    AssuranceEngine().assess(request, base)
            self.assertEqual(swapped, [policy_path])
            self.assertEqual(policy_path.read_bytes(), malicious_bytes)

    def test_engine_provenance_cannot_bind_unverified_post_capture_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shutil.copytree(EXAMPLES, base, dirs_exist_ok=True)
            raw = json.loads((base / "request.json").read_text(encoding="utf-8"))
            attack = next(i for i in raw["analyzer_inputs"] if i["analyzer"] == "attack")
            attack["successes"] += 1
            request = AssessmentRequest.model_validate(raw)
            claim = next(i for i in request.analyzer_inputs if i.analyzer == "attack")
            target = (base / claim.provenance.source_path).resolve()
            malicious_bytes = canonical_json_bytes(claim.model_dump(mode="json", exclude={"provenance"}))
            swapped = []
            def capture_then_swap(source_path, expected, base_dir):
                captured = read_verified_source_bytes(source_path, expected, base_dir)
                path = Path(source_path)
                path = (path if path.is_absolute() else base_dir / path).resolve()
                if path == target:
                    path.write_bytes(malicious_bytes)
                    swapped.append(path)
                return captured
            with patch("model_release_assurance.engine.read_verified_source_bytes", side_effect=capture_then_swap):
                with self.assertRaisesRegex(IntegrityError, "bound field 'successes' differs"):
                    AssuranceEngine().assess(request, base)
            self.assertEqual(swapped, [target])
            self.assertEqual(target.read_bytes(), malicious_bytes)


if __name__ == "__main__":
    unittest.main()
