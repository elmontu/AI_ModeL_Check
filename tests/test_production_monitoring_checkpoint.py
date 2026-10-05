"""Retained monitor floors reject replacement, fork and rollback."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_monitoring.checkpoint import FileCheckpointSink
from model_release_assurance.production_monitoring import contracts as c
from model_release_assurance.production_monitoring.store import MonitorConflict, MonitorUnavailable


def pin(sequence=0, head=None, store="a"*32):
    return {"schema": "mra-fixture-monitor-pin/v1", "store_id": store,
            "sequence": sequence, "head_sha256": head or format(sequence, "064x")}


class MonitoringCheckpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mra-monitor-floor-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/"floor"
        self.sink = FileCheckpointSink(self.root, pin())

    def test_explicit_monotonic_floor_survives_reopen(self):
        self.sink(pin(1)); self.sink(pin(2)); self.sink(pin(2))
        self.assertEqual(FileCheckpointSink.open(self.root, expected_pin=pin(1)).floor, pin(2))
        self.assertEqual((self.root/"2.json").read_bytes(), c.canonical_bytes(pin(2))+b"\n")
        with self.assertRaises(TypeError):
            FileCheckpointSink.open(self.root)

    def test_rollback_fork_and_foreign_floor_rejected(self):
        self.sink(pin(1))
        for bad in (pin(), pin(1,"b"*64), pin(2,store="b"*32)):
            with self.assertRaises(MonitorConflict):
                self.sink(bad)
        self.assertEqual(self.sink.floor, pin(1))

    def test_reopen_requires_known_floor_presence_and_exact_head(self):
        for bad in (pin(1),pin(0,"b"*64),pin(store="b"*32)):
            with self.assertRaises((ValueError,MonitorUnavailable)):
                FileCheckpointSink.open(self.root, expected_pin=bad)

    def test_observed_ancestor_contents_cannot_be_rewritten(self):
        self.sink(pin(1)); self.sink(pin(2))
        (self.root/"1.json").write_bytes(c.canonical_bytes(pin(1,"b"*64))+b"\n")
        with self.assertRaises(MonitorConflict):
            self.sink.read()

    def test_known_file_removal_is_custody_failure(self):
        self.sink(pin(1)); (self.root/"0.json").unlink()
        with self.assertRaises(MonitorUnavailable):
            self.sink.read()

    def test_same_bytes_inode_replacement_is_rejected(self):
        path=self.root/"0.json"; raw=path.read_bytes()
        path.rename(self.root.parent/"old")
        path.write_bytes(raw)
        with self.assertRaises(MonitorUnavailable):
            self.sink.read()

    def test_hardlink_and_unknown_inventory_rejected(self):
        path=self.root/"0.json"
        os.link(path,self.root.parent/"link")
        with self.assertRaises(MonitorUnavailable):
            self.sink.read()
        (self.root.parent/"link").unlink()
        (self.root/"unknown.txt").write_bytes(b"metadata")
        with self.assertRaises(MonitorUnavailable):
            self.sink.read()

    def test_duplicate_fields_and_noncanonical_pin_rejected(self):
        path=self.root/"0.json"; raw=path.read_bytes()
        for bad in (json.dumps(pin(),indent=2).encode(),
                    raw.replace(b'"sequence":0',b'"sequence":0,"sequence":0')):
            path.write_bytes(bad)
            with self.assertRaises(ValueError):
                self.sink.read()

    def test_failed_fsync_keeps_prior_floor_and_retry_resyncs(self):
        with patch("model_release_assurance.production_monitoring.checkpoint.os.fsync",side_effect=OSError("PRIVATE-CANARY")):
            with self.assertRaises(MonitorUnavailable):
                self.sink(pin(1))
        self.assertEqual(self.sink._floor,pin())
        self.assertTrue((self.root/"1.json").exists())
        with patch("model_release_assurance.production_monitoring.checkpoint.os.fsync",wraps=os.fsync) as sync:
            self.sink(pin(1))
            self.assertTrue(sync.called)
        self.assertEqual(self.sink.floor,pin(1))

    def test_lexical_traversal_and_secret_paths_are_generic(self):
        parent=self.root.parent
        (parent/"existing").mkdir()
        with self.assertRaises(MonitorUnavailable):
            FileCheckpointSink(parent/"existing"/".."/"other",pin())
        self.assertFalse((parent/"other").exists())
        with self.assertRaises(MonitorUnavailable) as denied:
            FileCheckpointSink(parent/"PRIVATE-CANARY"/"missing",pin())
        self.assertNotIn("PRIVATE-CANARY",str(denied.exception))
