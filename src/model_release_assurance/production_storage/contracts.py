"""Immutable, exact references for a local fictional JSON fixture only."""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import re
from types import MappingProxyType

MAX_OBJECT_BYTES = 64 * 1024
FIXTURE_ID = "public-counts-v1"
PROVENANCE = MappingProxyType({"source_id": "fictional-aggregate-source-v1", "query_id": "fixed-count-query-v1",
                               "transform_id": "no-transform-v1", "linkage_id": "no-linkage-v1"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ReferenceError(ValueError):
    """Malformed or unsupported fixture reference."""


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _invalid():
    raise ReferenceError("Invalid fixture reference")


def _identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _invalid()


def _integer(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        _invalid()


def _common(reference, identity_field):
    identity = getattr(reference, identity_field)
    if type(identity) is not str or not _HEX_ID.fullmatch(identity):
        _invalid()
    for name in ("agency_id", "project_id", "case_id"):
        _identifier(getattr(reference, name))
    for name, expected in PROVENANCE.items():
        if type(getattr(reference, name)) is not str or getattr(reference, name) != expected:
            _invalid()
    _integer(reference.created_at)
    _integer(reference.retention_until)
    if reference.retention_until < reference.created_at:
        _invalid()


@dataclass(frozen=True, slots=True)
class ObjectReference:
    object_id: str
    version_id: str
    agency_id: str
    project_id: str
    case_id: str
    sha256: str
    size_bytes: int
    format: str
    fixture_id: str
    source_id: str
    query_id: str
    transform_id: str
    linkage_id: str
    created_at: int
    retention_until: int

    def __post_init__(self):
        _common(self, "object_id")
        if type(self.version_id) is not str or not _HEX_ID.fullmatch(self.version_id):
            _invalid()
        if type(self.sha256) is not str or not _SHA256.fullmatch(self.sha256):
            _invalid()
        if type(self.size_bytes) is not int or not 1 <= self.size_bytes <= MAX_OBJECT_BYTES:
            _invalid()
        if self.format != "application/json" or type(self.format) is not str:
            _invalid()
        if self.fixture_id != FIXTURE_ID or type(self.fixture_id) is not str:
            _invalid()

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
            _invalid()
        return cls(**value)

    @property
    def reference_digest(self):
        return hashlib.sha256(canonical_bytes(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    snapshot_id: str
    agency_id: str
    project_id: str
    case_id: str
    objects: tuple[ObjectReference, ...]
    source_id: str
    query_id: str
    transform_id: str
    linkage_id: str
    created_at: int
    retention_until: int

    def __post_init__(self):
        _common(self, "snapshot_id")
        if type(self.objects) not in (tuple, list) or not 1 <= len(self.objects) <= 8:
            _invalid()
        objects = tuple(self.objects)
        for item in objects:
            if type(item) is not ObjectReference:
                _invalid()
            ObjectReference.from_dict(item.to_dict())
            if (item.agency_id, item.project_id, item.case_id) != (self.agency_id, self.project_id, self.case_id):
                _invalid()
            if item.created_at > self.created_at or self.retention_until > item.retention_until:
                _invalid()
        if len({(item.object_id, item.version_id) for item in objects}) != len(objects):
            _invalid()
        object.__setattr__(self, "objects", objects)

    def to_dict(self):
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["objects"] = [item.to_dict() for item in self.objects]
        return result

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)} or type(value["objects"]) is not list:
            _invalid()
        return cls(**dict(value, objects=tuple(ObjectReference.from_dict(item) for item in value["objects"])))

    @property
    def reference_digest(self):
        return hashlib.sha256(canonical_bytes(self.to_dict())).hexdigest()

    @property
    def snapshot_digest(self):
        return self.reference_digest
