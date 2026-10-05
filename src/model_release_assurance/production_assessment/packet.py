"""Signed local handoff packet; integrity is not independent attack replay.

The trusted fixture bootstrap seals observations and raw owned fixture files.
External manifest/key pins are mandatory. The generated key is not agency
identity; successful verification cannot close findings or restore authority.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ..production_capacity import io
from ..production_capacity.contracts import CapacityError
from . import contracts as c

MAX_FILES = 256
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 512 * 1024
_METADATA = frozenset({"assessment-plan.json", "assessment-observations.json",
    "assessment-findings.json", "public-key.json"})
_FLAGS = {"current_authorization_checked": False, "probe_execution_reconstructed": False,
          "agency_signer_authenticated": False}


def _fail():
    raise c.AssessmentError("Local assessment packet rejected")


def _canonical(value):
    try:
        from ..production_capacity.contracts import canonical_bytes
        return canonical_bytes(value, max_bytes=MAX_METADATA_BYTES)
    except (ValueError, TypeError):
        _fail()


def _json(raw):
    try:
        from ..production_capacity.contracts import strict_json
        value = strict_json(raw, max_bytes=MAX_METADATA_BYTES)
        if _canonical(value) != raw:
            _fail()
        return value
    except (ValueError, TypeError):
        _fail()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(_canonical(value))


def _hex(value, size):
    if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is None:
        _fail()
    return value


def _path(name):
    if (type(name) is not str or len(name) > 512 or "\\" in name
            or ":" in name or not name or PurePosixPath(name).is_absolute()):
        _fail()
    parts = name.split("/")
    if (len(parts) > 10 or any(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", part) is None
            or part in {".", ".."} for part in parts)):
        _fail()
    return parts


def _version(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _directory_identity(info):
    return info.st_dev, info.st_ino


def _capture(root, *, manifest_present):
    """Bounded inventory and same-handle file reads, retaining physical identity."""
    try:
        root = io.directory(root)
        rows, identities, total = [], {}, 0
        pending = [root]
        entries_seen = 0
        while pending:
            folder = pending.pop()
            io.directory(folder)
            identities[folder.relative_to(root).as_posix() + "/"] = _directory_identity(folder.lstat())
            # scandir is consumed with a total-entry bound, not an unbounded list.
            with os.scandir(folder) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > MAX_FILES * 2:
                        _fail()
                    path = Path(entry.path)
                    name = path.relative_to(root).as_posix()
                    _path(name)
                    info = path.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                        _fail()
                    if stat.S_ISDIR(info.st_mode):
                        if name.split("/")[0] != "fixture":
                            _fail()
                        pending.append(path)
                        continue
                    if name == "manifest.json":
                        if not manifest_present:
                            _fail()
                        continue
                    if name.split("/")[0] != "fixture" and name not in _METADATA:
                        _fail()
                    raw = io.read_file(path, maxbytes=MAX_FILE_BYTES)
                    identities[name] = _version(path.lstat())
                    total += len(raw)
                    if total > MAX_TOTAL_BYTES or len(rows) >= MAX_FILES:
                        _fail()
                    rows.append({"path": name, "sha256": _sha(raw), "size_bytes": len(raw)})
        rows.sort(key=lambda row: row["path"])
        names = {row["path"] for row in rows}
        if not _METADATA <= names or not any(name.startswith("fixture/") for name in names):
            _fail()
        return rows, identities
    except (OSError, ValueError, TypeError, CapacityError):
        _fail()


def implementation_sha256():
    """Bind all bounded package Python bytes, in source or installed wheels."""
    root = io.directory(Path(__file__).absolute().parents[1])
    rows = []
    # Bound directory entries too, including trees containing no Python files.
    pending, seen = [root], 0
    while pending:
        folder = pending.pop()
        io.directory(folder)
        with os.scandir(folder) as entries:
            for entry in entries:
                seen += 1
                if seen > MAX_FILES * 8:
                    _fail()
                p = Path(entry.path)
                info = p.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    _fail()
                if stat.S_ISDIR(info.st_mode):
                    if p.name != "__pycache__":
                        pending.append(p)
                    continue
                if p.suffix != ".py":
                    continue
                if len(rows) >= MAX_FILES:
                    _fail()
                name = p.relative_to(root).as_posix()
                _path(name)
                try:
                    raw = io.read_file(p, maxbytes=2 * 1024 * 1024)
                except CapacityError:
                    _fail()
                rows.append({"path": name, "sha256": _sha(raw)})
    rows.sort(key=lambda row: row["path"])
    if not rows:
        _fail()
    return _digest(rows)


def runtime_observation():
    return {"python": platform.python_version(), "packages": {
        name: importlib.metadata.version(name) for name in
        ("cryptography", "fastapi", "numpy", "PyJWT", "scikit-learn")}}


def _metadata(root):
    plan = _json(io.read_file(root / "assessment-plan.json", maxbytes=MAX_METADATA_BYTES))
    observations = _json(io.read_file(root / "assessment-observations.json", maxbytes=MAX_METADATA_BYTES))
    findings = _json(io.read_file(root / "assessment-findings.json", maxbytes=MAX_METADATA_BYTES))
    if (type(plan) is not dict or type(observations) is not dict
            or type(findings) is not dict):
        _fail()
    # The fixed probe contract is the only accepted observation shape.
    from .probes import probe_plan, validate_result
    c.validate_catalog(findings)
    if _canonical(plan) != _canonical(probe_plan()):
        _fail()
    validate_result(observations)
    return plan, observations, findings


def seal_packet(root, *, profile="agency_private_cloud"):
    c.require_local(profile)
    try:
        root = io.directory(root)
        if (root / "manifest.json").exists() or (root / "public-key.json").exists():
            _fail()
        plan, observations, findings = _metadata(root)
        key = Ed25519PrivateKey.generate()
        public = {"schema": "mra-local-assessment-key/v1",
                  "algorithm": "Ed25519",
                  "public_key_hex": key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
                  "agency_signer_authenticated": False}
        key_raw = _canonical(public)
        io.exclusive_write(root / "public-key.json", key_raw)
        inventory, identities = _capture(root, manifest_present=False)
        payload = {"schema": "mra-local-assessment-packet/v1",
            "scope": "historical_local_fixture_assessment",
            "plan_sha256": _digest(plan), "observations_sha256": _digest(observations),
            "finding_catalog_sha256": _digest(findings),
            "implementation_sha256": implementation_sha256(),
            "runtime": runtime_observation(), "files": inventory, **c.FLAGS, **_FLAGS}
        signed = {"payload": payload, "signature_hex": key.sign(_canonical(payload)).hex()}
        raw = _canonical(signed)
        io.exclusive_write(root / "manifest.json", raw)
        if _capture(root, manifest_present=True) != (inventory, identities):
            _fail()
        return {"manifest_sha256": _sha(raw), "key_sha256": _sha(key_raw), **c.FLAGS, **_FLAGS}
    except (OSError, ValueError, TypeError, CapacityError):
        _fail()


def verify_packet(root, *, expected_manifest_sha256, expected_key_sha256):
    """Historical byte/contract replay with explicit externally retained pins.

    This does not repeat the probes, independently replay all nested SQLite
    histories, establish an appointed signer or check current release authority.
    """
    _hex(expected_manifest_sha256, 64)
    _hex(expected_key_sha256, 64)
    try:
        root = io.directory(root)
        root_id = _directory_identity(root.lstat())
        manifest_path = root / "manifest.json"
        manifest_raw = io.read_file(manifest_path, maxbytes=MAX_METADATA_BYTES)
        manifest_identity = _version(manifest_path.lstat())
        key_path = root / "public-key.json"
        key_raw = io.read_file(key_path, maxbytes=MAX_METADATA_BYTES)
        if _sha(manifest_raw) != expected_manifest_sha256 or _sha(key_raw) != expected_key_sha256:
            _fail()
        signed, public = _json(manifest_raw), _json(key_raw)
        if (type(signed) is not dict or set(signed) != {"payload", "signature_hex"}
                or type(public) is not dict or set(public) !=
                {"schema", "algorithm", "public_key_hex", "agency_signer_authenticated"}
                or public["schema"] != "mra-local-assessment-key/v1"
                or public["algorithm"] != "Ed25519"
                or public["agency_signer_authenticated"] is not False):
            _fail()
        public_bytes = bytes.fromhex(_hex(public["public_key_hex"], 64))
        signature = bytes.fromhex(_hex(signed["signature_hex"], 128))
        payload = signed["payload"]
        keys = {"schema", "scope", "plan_sha256", "observations_sha256",
                "finding_catalog_sha256", "implementation_sha256", "runtime", "files",
                *c.FLAGS, *_FLAGS}
        if (type(payload) is not dict or set(payload) != keys
                or payload["schema"] != "mra-local-assessment-packet/v1"
                or payload["scope"] != "historical_local_fixture_assessment"
                or any(payload[name] is not value for name, value in {**c.FLAGS, **_FLAGS}.items())
                or payload["implementation_sha256"] != implementation_sha256()
                or payload["runtime"] != runtime_observation()):
            _fail()
        for name in ("plan_sha256", "observations_sha256", "finding_catalog_sha256", "implementation_sha256"):
            _hex(payload[name], 64)
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, _canonical(payload))
        rows, identities = _capture(root, manifest_present=True)
        if type(payload["files"]) is not list or len(payload["files"]) != len(rows):
            _fail()
        for row in payload["files"]:
            if type(row) is not dict or set(row) != {"path", "sha256", "size_bytes"}:
                _fail()
            _path(row["path"]); _hex(row["sha256"], 64)
            if type(row["size_bytes"]) is not int or not 0 <= row["size_bytes"] <= MAX_FILE_BYTES:
                _fail()
        if rows != payload["files"]:
            _fail()
        plan, observations, findings = _metadata(root)
        if (payload["plan_sha256"] != _digest(plan)
                or payload["observations_sha256"] != _digest(observations)
                or payload["finding_catalog_sha256"] != _digest(findings)):
            _fail()
        if (_capture(root, manifest_present=True) != (rows, identities)
                or io.read_file(manifest_path, maxbytes=MAX_METADATA_BYTES) != manifest_raw
                or _version(manifest_path.lstat()) != manifest_identity
                or _directory_identity(root.lstat()) != root_id):
            _fail()
        return {"schema": "mra-local-assessment-verification/v1",
                "status": "historical_packet_verified", "manifest_sha256": expected_manifest_sha256,
                "key_sha256": expected_key_sha256, "file_count": len(rows),
                "total_bytes": sum(row["size_bytes"] for row in rows),
                "finding_catalog_sha256": payload["finding_catalog_sha256"],
                "implementation_sha256": payload["implementation_sha256"], **c.FLAGS, **_FLAGS}
    except (OSError, ValueError, TypeError, KeyError, InvalidSignature, CapacityError):
        _fail()
