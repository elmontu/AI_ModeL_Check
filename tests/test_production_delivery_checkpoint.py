"""Local delivery floor preservation and ordinary-file custody regressions."""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_delivery.checkpoint import FileCheckpointSink
from model_release_assurance.production_delivery.contracts import canonical_bytes, DeliveryError
from model_release_assurance.production_delivery.store import StoreConflict, StoreUnavailable


def pin(sequence=1, head=None, store="a" * 32):
    return {"schema": "mra-fixture-delivery-pin/v1", "store_id": store,
            "sequence": sequence, "head_sha256": head or format(sequence, "064x")}


class DeliveryCheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-delivery-floor-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "floor"
        self.sink = FileCheckpointSink(self.root, pin())

    def test_monotonic_canonical_files_reopen_with_explicit_ancestor(self):
        self.sink(pin(2)); self.sink(pin(3)); self.sink(pin(3))
        self.assertEqual(self.sink.read(), pin(3))
        self.assertEqual(FileCheckpointSink.open(self.root, expected_pin=pin(2)).read(), pin(3))
        self.assertEqual((self.root / "3.json").read_bytes(), canonical_bytes(pin(3)) + b"\n")
        self.assertEqual(len(list(self.root.iterdir())), 3)
        with self.assertRaises(TypeError): FileCheckpointSink.open(self.root)
        with self.assertRaises(FileExistsError): FileCheckpointSink(self.root, pin())

    def test_backward_foreign_and_same_sequence_fork_do_not_weaken_floor(self):
        self.sink(pin(2))
        for bad in (pin(), pin(2, "b" * 64), pin(3, store="b" * 32)):
            with self.subTest(bad=bad), self.assertRaises(StoreConflict): self.sink(bad)
        self.assertEqual(self.sink.read(), pin(2))

    def test_open_refuses_missing_newer_external_floor_and_fork(self):
        for expected in (pin(2), pin(1, "b" * 64), pin(1, store="b" * 32)):
            with self.subTest(expected=expected), self.assertRaises((StoreConflict, StoreUnavailable)):
                FileCheckpointSink.open(self.root, expected_pin=expected)

    def test_removing_previously_seen_checkpoint_is_refused(self):
        self.sink(pin(2))
        (self.root / "1.json").unlink()
        with self.assertRaises(StoreUnavailable): self.sink.read()

    def test_same_bytes_file_replacement_is_refused_by_live_sink(self):
        path = self.root / "1.json"
        raw = path.read_bytes()
        path.rename(path.with_suffix(".saved"))
        path.write_bytes(raw)
        # Keep the old inode outside the inventoried directory.
        path.with_suffix(".saved").rename(self.root.parent / "old-pin")
        with self.assertRaises(StoreUnavailable): self.sink.read()

    def test_same_bytes_directory_replacement_is_refused_by_live_sink(self):
        raw = (self.root / "1.json").read_bytes()
        self.root.rename(self.root.with_name("old-floor"))
        self.root.mkdir()
        (self.root / "1.json").write_bytes(raw)
        with self.assertRaises(StoreUnavailable): self.sink.read()

    def test_noncanonical_duplicate_unknown_and_boolean_pin_fields_fail_closed(self):
        path = self.root / "1.json"
        for raw in (json.dumps(pin(), indent=2).encode(), canonical_bytes({**pin(), "extra": False}) + b"\n",
                    canonical_bytes({**pin(), "sequence": True}) + b"\n",
                    b'{"schema":"mra-fixture-delivery-pin/v1","store_id":"' + b'a'*32
                    + b'","sequence":1,"sequence":1,"head_sha256":"' + b'0'*63 + b'1"}\n'):
            path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises((StoreConflict, StoreUnavailable, DeliveryError, ValueError)):
                self.sink.read()
        path.write_bytes(canonical_bytes(pin()) + b"\n")
        self.assertEqual(self.sink.read(), pin())

    def test_unexpected_inventory_directory_or_oversize_file_is_refused(self):
        unexpected = self.root / "extra.txt"
        unexpected.write_text("not a checkpoint")
        with self.assertRaises(StoreUnavailable): self.sink.read()
        unexpected.unlink()
        unexpected.mkdir()
        with self.assertRaises(StoreUnavailable): self.sink.read()
        unexpected.rmdir()
        (self.root / "1.json").write_bytes(b"x" * 65537)
        with self.assertRaises(ValueError): self.sink.read()

    def test_fsync_failure_does_not_claim_new_floor_and_preserves_diagnostic_file(self):
        with mock.patch("model_release_assurance.production_delivery.checkpoint.os.fsync", side_effect=OSError("fixture fault")):
            with self.assertRaises(OSError): self.sink(pin(2))
        self.assertTrue((self.root / "2.json").exists())
        self.assertEqual(self.sink._floor, pin())
        self.sink(pin(2))
        self.assertEqual(self.sink.read(), pin(2))

    def test_hardlinked_checkpoint_is_refused_without_following_another_file(self):
        path = self.root / "1.json"
        os.link(path, self.root.parent / "second-link")
        with self.assertRaises(StoreUnavailable): self.sink.read()

    def test_replacement_during_bounded_read_is_refused(self):
        from model_release_assurance.production_delivery import checkpoint
        original = checkpoint.native._read
        path = self.root / "1.json"
        def swap(target, limit):
            raw = original(target, limit)
            target.rename(self.root.parent / "replaced-during-read")
            target.write_bytes(raw)
            return raw
        with mock.patch.object(checkpoint.native, "_read", side_effect=swap):
            with self.assertRaises(StoreUnavailable): self.sink.read()


if __name__ == "__main__":
    unittest.main()
