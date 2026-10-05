"""Immutable fictional object references and adversarial local filesystem fixtures."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

from model_release_assurance.production_storage import (
    FixtureObjectStore, MAX_OBJECT_BYTES, ObjectReference, ReferenceError, SnapshotReference, StorageError,
)
from model_release_assurance.production_storage import backend


class ProductionStorageBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-storage-backend-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "objects"
        self.store = FixtureObjectStore(self.root)

    def register(self, **changes):
        values = dict(case_id="case-a", agency_id="agency-a", project_id="project-a", fixture_id="public-counts-v1",
                      created_at=100, retention_until=200)
        values.update(changes)
        return self.store.register_fixture(**values)

    def path(self, reference):
        return self.root / (reference.object_id + "." + reference.version_id + ".json")

    def test_exact_reference_metadata_and_same_buffer_bytes(self):
        reference = self.register()
        content = self.store.read(reference)
        self.assertEqual(hashlib.sha256(content).hexdigest(), reference.sha256)
        self.assertEqual(len(content), reference.size_bytes)
        self.assertEqual(ObjectReference.from_dict(reference.to_dict()), reference)
        self.assertEqual(len(reference.reference_digest), 64)
        metadata = self.store.metadata(reference.to_dict())
        self.assertEqual(metadata["reference"], reference.to_dict())
        self.assertEqual(metadata["reference_digest"], reference.reference_digest)
        self.assertTrue(metadata["fixture_only"])
        self.assertFalse(metadata["authorization_eligible"])
        self.assertFalse(metadata["model_delivery"])
        fixture = json.loads(content)
        self.assertEqual(fixture["classification"], "fictional_public_fixture")
        self.assertEqual(fixture["counts"], [{"category": "fictional-a", "count": 12}, {"category": "fictional-b", "count": 7}])
        with self.assertRaises(FrozenInstanceError):
            reference.retention_until = 0
        metadata["reference"]["case_id"] = "case-b"
        self.assertEqual(self.store.metadata(reference)["reference"]["case_id"], "case-a")

    def test_registration_generates_distinct_versions_even_for_identical_fixture(self):
        first, second = self.register(), self.register()
        self.assertNotEqual(first.object_id, second.object_id)
        self.assertNotEqual(first.version_id, second.version_id)
        self.assertNotEqual(first.reference_digest, second.reference_digest)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(self.store.read(first), self.store.read(second))
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_unknown_or_changed_well_formed_reference_cannot_substitute_scope_or_metadata(self):
        reference = self.register()
        changes = ({"agency_id": "agency-b"}, {"project_id": "project-b"}, {"case_id": "case-b"},
                   {"sha256": "0" * 64}, {"size_bytes": reference.size_bytes + 1}, {"created_at": 101},
                   {"retention_until": 201}, {"object_id": "0" * 32}, {"version_id": "0" * 32})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(StorageError):
                self.store.read(replace(reference, **change))
        self.assertEqual(self.store.read(reference), self.path(reference).read_bytes())

    def test_paths_urls_latest_unknown_fields_missing_fields_and_types_are_rejected(self):
        reference = self.register()
        for field, value in (("object_id", "../outside"), ("version_id", "latest"), ("case_id", "https://invalid.example/case"),
                             ("fixture_id", "unknown"), ("format", "application/zip"), ("size_bytes", True),
                             ("created_at", True), ("retention_until", 99), ("source_id", "external-source"),
                             ("query_id", "user-supplied-query"), ("transform_id", "changed"), ("linkage_id", "person-linkage")):
            with self.subTest(field=field), self.assertRaises(ReferenceError):
                ObjectReference.from_dict(dict(reference.to_dict(), **{field: value}))
        for field in reference.to_dict():
            value = reference.to_dict()
            del value[field]
            with self.subTest(missing=field), self.assertRaises(ReferenceError):
                ObjectReference.from_dict(value)
        for value in (None, [], "latest", dict(reference.to_dict(), url="https://invalid.example")):
            with self.assertRaises(ReferenceError):
                self.store.read(value)

    def test_invalid_registration_creates_no_files_and_accepts_no_user_bytes(self):
        for change in ({"fixture_id": "../private.json"}, {"fixture_id": "https://invalid.example"}, {"case_id": "../case"},
                       {"retention_until": 99}, {"created_at": True}):
            with self.subTest(change=change), self.assertRaises((ReferenceError, StorageError)):
                self.register(**change)
        with self.assertRaises(TypeError):
            self.register(content=b"arbitrary user bytes")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_roots_cannot_be_reopened_or_overwritten(self):
        reference = self.register()
        before = self.path(reference).read_bytes()
        with self.assertRaises(StorageError):
            FixtureObjectStore(self.root)
        empty = self.parent / "existing-empty"
        empty.mkdir()
        with self.assertRaises(StorageError):
            FixtureObjectStore(empty)
        with self.assertRaises(StorageError):
            FixtureObjectStore(self.parent / "objects/../another")
        self.assertEqual(self.path(reference).read_bytes(), before)
        self.assertFalse((self.parent / "another").exists())

    def test_exclusive_create_collision_never_overwrites_existing_object(self):
        reference = self.register()
        before = self.path(reference).read_bytes()
        generated = [SimpleNamespace(hex=reference.object_id), SimpleNamespace(hex=reference.version_id)]
        with mock.patch.object(backend.uuid, "uuid4", side_effect=generated), self.assertRaises(StorageError):
            self.register(case_id="case-b")
        self.assertEqual(self.path(reference).read_bytes(), before)
        self.assertEqual(self.store.read(reference), before)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_same_length_tamper_oversize_and_missing_files_fail_reads_and_metadata(self):
        reference = self.register()
        path = self.path(reference)
        original = path.read_bytes()
        path.write_bytes(original.replace(b"12", b"99"))
        self.assertEqual(path.stat().st_size, reference.size_bytes)
        with self.assertRaises(StorageError):
            self.store.read(reference)
        # Metadata is a reference/path check, never a content integrity claim.
        self.assertFalse(self.store.metadata(reference)["content_integrity_checked"])
        path.write_bytes(b"x" * (MAX_OBJECT_BYTES + 1))
        with self.assertRaises(StorageError):
            self.store.read(reference)
        path.unlink()
        with self.assertRaises(StorageError):
            self.store.read(reference)

    def test_identical_bytes_with_replaced_file_identity_are_rejected(self):
        reference = self.register()
        original = self.path(reference)
        replacement = self.parent / "replacement.json"
        replacement.write_bytes(original.read_bytes())
        os.replace(replacement, original)
        with self.assertRaises(StorageError):
            self.store.read(reference)

    def test_hardlink_alias_is_refused_even_when_object_bytes_match(self):
        reference = self.register()
        alias = self.parent / "alias.json"
        os.link(self.path(reference), alias)
        with self.assertRaises(StorageError):
            self.store.read(reference)
        alias.unlink()
        self.assertEqual(len(self.store.read(reference)), reference.size_bytes)

    def test_reparse_and_symlink_attributes_are_refused_without_platform_privileges(self):
        reference = self.register()
        original_lstat = Path.lstat
        for mode, attributes in ((stat.S_IFREG | 0o600, 0x400), (stat.S_IFLNK | 0o600, 0)):
            def replaced(path, *args, **kwargs):
                if path == self.path(reference):
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                return original_lstat(path, *args, **kwargs)
            with self.subTest(mode=mode), mock.patch.object(Path, "lstat", replaced), self.assertRaises(StorageError):
                self.store.read(reference)
        def changed_parent(path, *args, **kwargs):
            if path == self.parent:
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", changed_parent), self.assertRaises(StorageError):
            FixtureObjectStore(self.parent / "new-root")
        self.assertFalse((self.parent / "new-root").exists())

    def test_whole_root_replacement_is_refused(self):
        reference = self.register()
        preserved = self.parent / "preserved-root"
        self.root.rename(preserved)
        self.root.mkdir()
        self.path(reference).write_bytes((preserved / self.path(reference).name).read_bytes())
        with self.assertRaises(StorageError):
            self.store.read(reference)
        with self.assertRaises(StorageError):
            self.register()

    def test_private_content_validator_refuses_archives_pickle_and_wrong_json(self):
        valid = self.store.read(self.register())
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            archive.writestr("fixture.json", valid)
        invalid = [gzip.compress(valid), zipped.getvalue(), b"\x80\x04pickle-placeholder", b"x" * (MAX_OBJECT_BYTES + 1),
                   b"[]", b"{}", b"null", b"\xff", valid.replace(b'"count":12', b'"count":NaN'),
                   valid.replace(b'"count":12', b'"count":' + b"9" * 5000),
                   valid.replace(b'"count":12', b'"count":12,"count":12'),
                   valid.replace(b'"counts":', b'"foreign_data":')]
        for content in invalid:
            with self.subTest(size=len(content)), self.assertRaises(StorageError):
                backend._validate_fixture_bytes(content)
        self.assertEqual(backend._validate_fixture_bytes(valid), valid)

    def test_metadata_never_opens_object_content_before_grant_authorization(self):
        reference = self.register()
        with mock.patch.object(backend.os, "open", side_effect=AssertionError("Unexpected object body I/O")):
            metadata = self.store.metadata(reference)
        self.assertEqual(metadata["reference"], reference.to_dict())
        self.assertFalse(metadata["content_integrity_checked"])

    def test_created_objects_and_retained_failed_registrations_consume_capacity(self):
        with mock.patch.object(backend, "MAX_OBJECTS", 2):
            reference = self.register()
            with mock.patch.object(backend.os, "fsync", side_effect=OSError("injected failure")), self.assertRaises(StorageError):
                self.register()
            self.assertEqual(len(list(self.root.iterdir())), 2)
            self.assertEqual(self.store._created_objects, 2)
            with self.assertRaises(StorageError):
                self.register()
            self.assertEqual(len(list(self.root.iterdir())), 2)
            self.assertEqual(len(self.store.read(reference)), reference.size_bytes)

    def test_read_uses_one_bounded_buffer(self):
        reference = self.register()
        limits = []
        original_fdopen = backend.os.fdopen
        class Observer:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def read(self, size):
                limits.append(size)
                return self.stream.read(size)
        with mock.patch.object(backend.os, "fdopen", side_effect=lambda descriptor, mode: Observer(original_fdopen(descriptor, mode))):
            content = self.store.read(reference)
        self.assertEqual(limits, [MAX_OBJECT_BYTES + 1])
        self.assertEqual(hashlib.sha256(content).hexdigest(), reference.sha256)

    def test_snapshot_binds_exact_objects_scope_provenance_and_retention(self):
        first, second = self.register(), self.register(retention_until=150)
        snapshot = self.store.freeze_snapshot(case_id="case-a", agency_id="agency-a", project_id="project-a",
                                              references=[first, second.to_dict()], created_at=110, retention_until=150)
        self.assertEqual(snapshot.objects, (first, second))
        self.assertEqual(SnapshotReference.from_dict(snapshot.to_dict()), snapshot)
        self.assertEqual(snapshot.snapshot_digest, snapshot.reference_digest)
        self.assertNotEqual(snapshot.reference_digest, replace(snapshot, retention_until=149).reference_digest)
        with self.assertRaises(FrozenInstanceError):
            snapshot.objects = ()
        for changes in ({"case_id": "case-b"}, {"retention_until": 151}, {"created_at": 99},
                        {"source_id": "unreviewed-source"}, {"objects": [first.to_dict()] * 9}, {"objects": []}):
            with self.subTest(changes=changes), self.assertRaises(ReferenceError):
                SnapshotReference.from_dict(dict(snapshot.to_dict(), **changes))

    def test_snapshot_rejects_duplicates_unknown_or_tampered_source_objects(self):
        reference = self.register()
        arguments = dict(case_id="case-a", agency_id="agency-a", project_id="project-a", created_at=110, retention_until=150)
        with self.assertRaises(ReferenceError):
            self.store.freeze_snapshot(references=[reference, reference], **arguments)
        with self.assertRaises(StorageError):
            self.store.freeze_snapshot(references=[replace(reference, object_id="0" * 32)], **arguments)
        self.path(reference).write_bytes(b"tampered")
        with self.assertRaises(StorageError):
            self.store.freeze_snapshot(references=[reference], **arguments)
        self.assertEqual(self.store._snapshots, {})


if __name__ == "__main__":
    unittest.main()
