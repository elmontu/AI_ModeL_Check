"""Local fictional-fixture storage contracts; no production custody guarantee."""
from .backend import FixtureObjectStore, StorageError
from .contracts import MAX_OBJECT_BYTES, ObjectReference, ReferenceError, SnapshotReference

__all__ = ["FixtureObjectStore", "StorageError", "ObjectReference", "SnapshotReference", "ReferenceError", "MAX_OBJECT_BYTES"]
