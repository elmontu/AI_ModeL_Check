"""New-root, memory-catalogued storage for server-known fictional count fixtures.

Exclusive writes, file identity and same-buffer hash checks detect local
substitution. This is not production WORM, encryption, provider custody,
adversarial-administrator isolation, persistence or restart/recovery support.
There is deliberately no deletion or arbitrary-byte ingestion operation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from threading import RLock
import uuid

from .contracts import FIXTURE_ID, MAX_OBJECT_BYTES, PROVENANCE, ObjectReference, ReferenceError, SnapshotReference, canonical_bytes

MAX_OBJECTS = 256
FIXTURE_FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False}
_FIXTURE = {"schema": "fictional-count-fixture/v1", "fixture_id": FIXTURE_ID,
            "classification": "fictional_public_fixture", "provenance": dict(PROVENANCE),
            "counts": [{"category": "fictional-a", "count": 12}, {"category": "fictional-b", "count": 7}]}
_FIXTURE_BYTES = canonical_bytes(_FIXTURE) + b"\n"


class StorageError(RuntimeError):
    """Unavailable, unknown or unsafe local storage; never include source paths."""


def _unavailable():
    raise StorageError("Fixture storage unavailable")


def _json_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            _unavailable()
        result[name] = value
    return result


def _json_integer(value):
    if len(value) > 16:
        _unavailable()
    return int(value)


def _json_noninteger(value):
    _unavailable()


def _validate_fixture_bytes(content, fixture_id=FIXTURE_ID):
    """Validate real bounded JSON shape, never decompress or deserialize candidates."""
    try:
        if type(content) is not bytes or not 1 <= len(content) <= MAX_OBJECT_BYTES or fixture_id != FIXTURE_ID:
            _unavailable()
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_json_pairs,
                           parse_int=_json_integer, parse_float=_json_noninteger, parse_constant=_json_noninteger)
        if type(value) is not dict or canonical_bytes(value) != canonical_bytes(_FIXTURE):
            _unavailable()
        return content
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise StorageError("Fixture storage unavailable") from None


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _identity(info):
    return info.st_dev, info.st_ino


def _directory_chain(path):
    for current in (*reversed(path.parents), path):
        info = current.lstat()
        if _link(info) or not stat.S_ISDIR(info.st_mode):
            _unavailable()


def _regular(info):
    if _link(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _unavailable()


class FixtureObjectStore:
    def __init__(self, root):
        try:
            raw = Path(root)
            if ".." in raw.parts:
                _unavailable()
            root = raw.absolute()
            _directory_chain(root.parent)
            if root.exists() or root.is_symlink():
                _unavailable()
            root.mkdir(mode=0o700, exist_ok=False)
            _directory_chain(root)
            self._root = root
            self._root_identity = _identity(root.lstat())
            self._objects = {}
            self._created_objects = 0
            self._snapshots = {}
            self._lock = RLock()
        except (OSError, ValueError, TypeError):
            raise StorageError("Fixture storage unavailable") from None

    def _check_root(self):
        _directory_chain(self._root)
        if _identity(self._root.lstat()) != self._root_identity:
            _unavailable()

    def _reference(self, reference):
        if type(reference) is ObjectReference:
            return ObjectReference.from_dict(reference.to_dict())
        return ObjectReference.from_dict(reference)

    def _lookup(self, reference):
        reference = self._reference(reference)
        entry = self._objects.get((reference.object_id, reference.version_id))
        if entry is None or entry[0] != reference:
            _unavailable()
        return reference, entry[1], entry[2]

    def register_fixture(self, *, case_id, agency_id, project_id, fixture_id, created_at, retention_until):
        if type(fixture_id) is not str or fixture_id != FIXTURE_ID:
            raise ReferenceError("Invalid fixture reference")
        content = _validate_fixture_bytes(_FIXTURE_BYTES, fixture_id)
        reference = ObjectReference(object_id=uuid.uuid4().hex, version_id=uuid.uuid4().hex,
                                    case_id=case_id, agency_id=agency_id, project_id=project_id,
                                    sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content),
                                    format="application/json", fixture_id=fixture_id, **PROVENANCE,
                                    created_at=created_at, retention_until=retention_until)
        with self._lock:
            try:
                if self._created_objects >= MAX_OBJECTS:
                    _unavailable()
                self._check_root()
                path = self._root / (reference.object_id + "." + reference.version_id + ".json")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(path, flags, 0o600)
                # Failed post-create checks retain evidence and consume capacity.
                self._created_objects += 1
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                    info = os.fstat(stream.fileno())
                    _regular(info)
                self._check_root()
                on_disk = path.lstat()
                _regular(on_disk)
                if _identity(info) != _identity(on_disk) or on_disk.st_size != len(content):
                    _unavailable()
                self._objects[(reference.object_id, reference.version_id)] = (reference, path, _identity(info))
                return reference
            except OSError:
                raise StorageError("Fixture storage unavailable") from None

    def read(self, reference):
        with self._lock:
            try:
                self._check_root()
                reference, path, expected_identity = self._lookup(reference)
                before = path.lstat()
                _regular(before)
                if _identity(before) != expected_identity or before.st_size != reference.size_bytes:
                    _unavailable()
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                with os.fdopen(os.open(path, flags), "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    _regular(opened)
                    if _identity(opened) != expected_identity or opened.st_size != reference.size_bytes:
                        _unavailable()
                    content = stream.read(MAX_OBJECT_BYTES + 1)
                    after = os.fstat(stream.fileno())
                    _regular(after)
                self._check_root()
                on_disk = path.lstat()
                _regular(on_disk)
                if (_identity(after) != expected_identity or _identity(on_disk) != expected_identity
                        or (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                        or after.st_size != on_disk.st_size or len(content) != reference.size_bytes
                        or hashlib.sha256(content).hexdigest() != reference.sha256):
                    _unavailable()
                return _validate_fixture_bytes(content, reference.fixture_id)
            except OSError:
                raise StorageError("Fixture storage unavailable") from None

    def metadata(self, reference):
        """Inspect known reference/path metadata without opening or rehashing bytes.

        Authorization can resolve an exact reference before a worker read grant
        is checked. Only ``read`` and snapshot freezing verify current content.
        """
        with self._lock:
            try:
                self._check_root()
                reference, path, expected_identity = self._lookup(reference)
                info = path.lstat()
                _regular(info)
                if _identity(info) != expected_identity or info.st_size != reference.size_bytes:
                    _unavailable()
                return {"reference": reference.to_dict(), "reference_digest": reference.reference_digest,
                        "content_integrity_checked": False, **FIXTURE_FLAGS}
            except OSError:
                raise StorageError("Fixture storage unavailable") from None

    def freeze_snapshot(self, *, case_id, agency_id, project_id, references, created_at, retention_until):
        if type(references) not in (tuple, list) or not 1 <= len(references) <= 8:
            raise ReferenceError("Invalid fixture reference")
        with self._lock:
            objects = tuple(self._reference(item) for item in references)
            snapshot = SnapshotReference(snapshot_id=uuid.uuid4().hex, agency_id=agency_id, project_id=project_id,
                                         case_id=case_id, objects=objects, **PROVENANCE,
                                         created_at=created_at, retention_until=retention_until)
            for item in objects:
                self.read(item)
            if snapshot.snapshot_id in self._snapshots:
                _unavailable()
            self._snapshots[snapshot.snapshot_id] = snapshot
            return snapshot
