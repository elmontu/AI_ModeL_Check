"""In-process capability for exact historical assessment integrity only.

This capability never carries current identity, review, agency acceptance or
delivery authority. New code requires a fresh matching assessment; previous
milestone packets remain untouched historical evidence.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from weakref import WeakSet

from ..production_assessment import contracts as assessment
from ..production_assessment import packet
from ..production_capacity import io
from . import contracts as c

_CAPABILITIES = WeakSet()


def _fail():
    raise c.PilotError("Restricted pilot evidence unavailable")


def _identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino


class VerifiedAssessment:
    """Exact generated-key packet with externally supplied historical pins."""
    def __init__(self, root, *, expected_manifest_sha256, expected_key_sha256,
                 profile="agency_private_cloud"):
        c.require_local(profile)
        try:
            c.validate_digest(expected_manifest_sha256)
            c.validate_digest(expected_key_sha256)
            self._root = io.directory(root)
            self._manifest_sha256 = expected_manifest_sha256
            self._key_sha256 = expected_key_sha256
            self._physical = tuple(_identity(self._root / name) if name else _identity(self._root)
                                   for name in ("", "manifest.json", "public-key.json"))
            self._binding = self._observe()
            _CAPABILITIES.add(self)
        except Exception:
            _fail()

    def _observe(self):
        physical = tuple(_identity(self._root / name) if name else _identity(self._root)
                         for name in ("", "manifest.json", "public-key.json"))
        if physical != self._physical:
            _fail()
        verified = packet.verify_packet(self._root,
            expected_manifest_sha256=self._manifest_sha256, expected_key_sha256=self._key_sha256)
        manifest_raw = io.read_file(self._root / "manifest.json", maxbytes=packet.MAX_METADATA_BYTES)
        if hashlib.sha256(manifest_raw).hexdigest() != self._manifest_sha256:
            _fail()
        payload = packet._json(manifest_raw)["payload"]
        def pinned_read(name):
            rows = [row for row in payload["files"] if row["path"] == name]
            if len(rows) != 1:
                _fail()
            raw = io.read_file(self._root / name, maxbytes=65536)
            if len(raw) != rows[0]["size_bytes"] or hashlib.sha256(raw).hexdigest() != rows[0]["sha256"]:
                _fail()
            return raw
        observations_raw = pinned_read("assessment-observations.json")
        if hashlib.sha256(observations_raw).hexdigest() != payload["observations_sha256"]:
            _fail()
        observations = packet._json(observations_raw)
        from ..production_assessment.probes import validate_result
        observations = validate_result(observations)
        candidate = pinned_read("fixture/fixture/training/native/candidate.json")
        if hashlib.sha256(candidate).hexdigest() != observations["evidence_hashes"]["candidate_sha256"]:
            _fail()
        from ..production_registration.contracts import validate_registration, native_json
        registration = validate_registration(native_json(pinned_read("fixture/fixture/training/registration.json")))
        if (registration["agency_id"], registration["project_id"], registration["case_id"],
                registration["profile_id"], registration["plan"]["rows"], registration["plan"]["seed"]) != (
                "agency", "project", "case-a", "sklearn-wine", 128, 20261001):
            _fail()
        if type(registration["plan"]["rows"]) is not int or type(registration["plan"]["seed"]) is not int:
            _fail()
        binding = {"schema": "mra-local-pilot-assessment-binding/v1",
            "candidate_sha256": observations["evidence_hashes"]["candidate_sha256"],
            "assessment_manifest_sha256": self._manifest_sha256,
            "assessment_key_sha256": self._key_sha256,
            "catalog_sha256": assessment.catalog_sha256(),
            "agency_id": "agency", "project_id": "project", "case_id": "case-a",
            "implementation_sha256": verified["implementation_sha256"],
            "profile_id": "sklearn-wine", "max_rows": 128,
            "evidence_profile": "PRD18_native_public_fixture",
            "production_blockers": list(assessment.BLOCKING_FINDING_IDS),
            "current_authorization_checked": False,
            "probe_execution_reconstructed": False, "agency_signer_authenticated": False,
            **c.FLAGS}
        # All expensive historical replay precedes the service's final shared
        # current-authority timestamp. This object supplies no clock/deadline.
        if packet.verify_packet(self._root,
                expected_manifest_sha256=self._manifest_sha256,
                expected_key_sha256=self._key_sha256) != verified:
            _fail()
        if tuple(_identity(self._root / name) if name else _identity(self._root)
                for name in ("", "manifest.json", "public-key.json")) != self._physical:
            _fail()
        return c.owned(binding)

    def snapshot(self):
        check_capability(self)
        return c.owned(self._binding)

    def recheck(self):
        check_capability(self)
        try:
            current = self._observe()
            if c.canonical_bytes(current) != c.canonical_bytes(self._binding):
                _fail()
            return c.owned(current)
        except Exception:
            _fail()


def check_capability(value):
    if type(value) is not VerifiedAssessment or value not in _CAPABILITIES:
        _fail()
    return value
