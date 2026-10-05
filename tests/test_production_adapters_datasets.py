"""Bounded read-only research sources; all adversarial data is synthetic."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings
import zipfile

import numpy as np

from model_release_assurance.production_adapters import datasets
from model_release_assurance.production_adapters.datasets import DatasetError, DatasetUnavailable


class ProductionAdapterDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-research-datasets-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.rows = 128
        self.write_fixture()

    def directory(self, corpus="acs"):
        return self.root / "experiments" / "mixed-model-export-20260929-v1" / corpus / "data"

    def write_fixture(self, corpus="acs", **arrays):
        directory = self.directory(corpus)
        directory.mkdir(parents=True, exist_ok=True)
        columns = len(datasets._FEATURE_NAMES[corpus])
        values = {"B": np.arange(self.rows * columns, dtype=np.int64).reshape(self.rows, columns) % 11,
                  "y": np.arange(self.rows, dtype=np.uint8) % 2,
                  "z": np.arange(self.rows, dtype=np.uint8) % 2,
                  "keys": np.full(self.rows, "synthetic-fixture-key", dtype="<U64")}
        values.update(arrays)
        np.savez_compressed(directory / "data.npz", **values)
        manifest = {"schema": "mra.mixed-model-data.v1", "corpus": corpus,
                    "b_names": list(datasets._FEATURE_NAMES[corpus]), "selected_rows": self.rows,
                    "data_receipt": {}}
        self.write_manifest(manifest, corpus)
        return values

    def write_manifest(self, manifest, corpus="acs", *, bind=True):
        directory = self.directory(corpus)
        if bind:
            content = (directory / "data.npz").read_bytes()
            manifest["data_receipt"] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def manifest(self, corpus="acs"):
        return json.loads((self.directory(corpus) / "manifest.json").read_text(encoding="utf-8"))

    def rewrite_zip(self, members):
        content = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in members:
                    archive.writestr(name, data)
        (self.directory() / "data.npz").write_bytes(content.getvalue())
        self.write_manifest(self.manifest())

    @staticmethod
    def npy(value):
        content = io.BytesIO()
        np.save(content, value, allow_pickle=True)
        return content.getvalue()

    def load(self, corpus="acs", max_rows=64):
        return datasets.load_research_dataset(self.root, corpus, max_rows)

    def test_all_four_corpora_return_only_b_y_and_bound_historical_metadata(self):
        for corpus in datasets.CORPORA:
            values = self.write_fixture(corpus)
            result = self.load(corpus)
            self.assertEqual(set(result), {"x", "y", "feature_names", "dataset_id", "source_sha256", "metadata"})
            self.assertEqual(result["x"].shape, (64, len(datasets._FEATURE_NAMES[corpus])))
            self.assertEqual(result["y"].shape, (64,))
            self.assertEqual(result["x"].dtype, np.dtype("float64"))
            self.assertFalse(result["x"].flags.writeable)
            self.assertFalse(result["y"].flags.writeable)
            self.assertEqual(result["feature_names"], list(datasets._FEATURE_NAMES[corpus]))
            self.assertEqual(result["source_sha256"], self.manifest(corpus)["data_receipt"]["sha256"])
            metadata = result["metadata"]
            self.assertEqual(metadata["task"], "binary_classification")
            self.assertTrue(metadata["historical_training_data_reused"])
            self.assertFalse(metadata["fresh_audit_evidence"])
            self.assertFalse(metadata["person_level_disjointness_established"])
            self.assertFalse(metadata["upstream_receipts_rehashed"])
            self.assertFalse(metadata["authorization_eligible"])
            self.assertFalse(metadata["production_authorized"])
            self.assertEqual(metadata["returned_covariates"], "B only")
            serialized = json.dumps(metadata)
            self.assertNotIn("synthetic-fixture-key", serialized)
            self.assertNotIn("z", result["feature_names"])
            self.assertEqual(metadata["source_rows"], len(values["y"]))

    def test_selection_is_deterministic_from_row_count_and_not_target_values(self):
        first = self.load()
        again = self.load()
        self.assertTrue(np.array_equal(first["x"], again["x"]))
        self.assertTrue(np.array_equal(first["y"], again["y"]))
        self.assertEqual(first["metadata"]["sampled_matrix_sha256"], again["metadata"]["sampled_matrix_sha256"])
        self.write_fixture(y=1 - np.arange(self.rows, dtype=np.uint8) % 2)
        changed = self.load()
        self.assertTrue(np.array_equal(first["x"], changed["x"]))
        self.assertEqual(first["metadata"]["selection_indices_sha256"], changed["metadata"]["selection_indices_sha256"])
        self.assertNotEqual(first["metadata"]["sampled_matrix_sha256"], changed["metadata"]["sampled_matrix_sha256"])

    def test_no_source_file_is_written_and_maximum_is_capped_to_available_rows(self):
        before = {path.relative_to(self.root): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                  for path in self.root.rglob("*") if path.is_file()}
        result = self.load(max_rows=4096)
        self.assertEqual(result["x"].shape[0], self.rows)
        after = {path.relative_to(self.root): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_unknown_corpus_traversal_and_invalid_bounds_fail_before_file_access(self):
        with mock.patch.object(datasets, "_read_file") as read:
            for corpus in ("covertype", "../acs", "ACS", None):
                with self.subTest(corpus=corpus), self.assertRaises(DatasetError):
                    self.load(corpus)
            for maximum in (True, 0, 31, 4097, 64.0):
                with self.subTest(maximum=maximum), self.assertRaises(DatasetError):
                    self.load(max_rows=maximum)
            read.assert_not_called()
        for root in (Path("relative-root"), self.root / ".." / "outside"):
            with self.assertRaises(DatasetError):
                datasets.load_research_dataset(root, "acs")

    def test_missing_root_or_file_is_distinct_from_rejected_data(self):
        with self.assertRaises(DatasetUnavailable):
            datasets.load_research_dataset(self.root / "missing", "acs")
        with self.assertRaises(DatasetUnavailable):
            self.load("bts")
        (self.directory() / "manifest.json").unlink()
        with self.assertRaises(DatasetUnavailable):
            self.load()

    def test_manifest_schema_corpus_feature_names_count_and_receipt_are_exact(self):
        original = self.manifest()
        variants = [{**original, "schema": "different"}, {**original, "corpus": "hmda"},
                    {**original, "b_names": ["z"] * 8}, {**original, "selected_rows": True},
                    {**original, "selected_rows": self.rows + 1},
                    {**original, "data_receipt": {"sha256": "0" * 64, "bytes": original["data_receipt"]["bytes"]}},
                    {**original, "data_receipt": {"sha256": original["data_receipt"]["sha256"], "bytes": True}}]
        for variant in variants:
            with self.subTest(variant=list(variant)), self.assertRaises(DatasetError):
                self.write_manifest(variant, bind=False)
                self.load()
        self.write_manifest(original)
        self.load()

    def test_duplicate_nonfinite_and_malformed_manifest_json_are_rejected(self):
        path = self.directory() / "manifest.json"
        for content in ('{"schema":"a","schema":"b"}', '{"value":NaN}', '{"value":1e999}', '[1,2]', '{malformed'):
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(DatasetError):
                self.load()

    def test_manifest_paths_are_never_dereferenced(self):
        manifest = self.manifest()
        manifest["source_receipts"] = [{"path": "C:/unrelated/private-records", "sha256": "0" * 64}]
        self.write_manifest(manifest)
        result = self.load()
        self.assertFalse(result["metadata"]["upstream_receipts_rehashed"])
        self.assertNotIn("private-records", json.dumps(result["metadata"]))

    def test_matrix_and_target_dimensions_types_and_finite_values_are_checked(self):
        columns = len(datasets._FEATURE_NAMES["acs"])
        changes = [{"B": np.ones((self.rows, columns + 1), dtype=np.int64)},
                   {"B": np.full((self.rows, columns), np.nan)},
                   {"B": np.full((self.rows, columns), np.inf)},
                   {"B": np.full((self.rows, columns), "not-numeric")},
                   {"y": np.ones((self.rows, 1), dtype=np.uint8)},
                   {"y": np.arange(self.rows, dtype=np.float64) % 2},
                   {"y": np.arange(self.rows, dtype=np.uint8) % 3},
                   {"y": np.zeros(self.rows, dtype=np.uint8)}]
        for arrays in changes:
            with self.subTest(fields=list(arrays)), self.assertRaises(DatasetError):
                self.write_fixture(**arrays)
                self.load()

    def test_unused_object_array_is_rejected_before_numpy_load(self):
        self.write_fixture(unused=np.array([{"not": "executed"}], dtype=object))
        with mock.patch.object(datasets.np, "load") as load, self.assertRaises(DatasetError):
            self.load()
        load.assert_not_called()

    def test_primitive_fortran_matrix_is_copied_to_finite_readonly_contiguous_output(self):
        matrix = np.asfortranarray(np.arange(self.rows * 8, dtype=np.int64).reshape(self.rows, 8))
        self.write_fixture(B=matrix)
        result = self.load()
        self.assertTrue(result["x"].flags.c_contiguous)
        self.assertFalse(result["x"].flags.writeable)

    def test_duplicate_traversal_nested_and_symlink_zip_members_are_rejected(self):
        matrix = self.npy(np.ones((self.rows, 8), dtype=np.int64))
        target = self.npy(np.arange(self.rows, dtype=np.uint8) % 2)
        link = zipfile.ZipInfo("extra.npy")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        members = [[("B.npy", matrix), ("B.npy", matrix), ("y.npy", target)],
                   [("B.npy", matrix), ("b.npy", matrix), ("y.npy", target)],
                   [("../B.npy", matrix), ("y.npy", target)],
                   [("nested/B.npy", matrix), ("y.npy", target)],
                   [("B.npy", matrix), ("y.npy", target), (link, b"elsewhere")]]
        for entries in members:
            with self.subTest(entries=len(entries)), self.assertRaises(DatasetError):
                self.rewrite_zip(entries)
                self.load()

    def test_archive_header_count_compressed_and_expanded_limits_precede_loading(self):
        with mock.patch.object(datasets, "MAX_COMPRESSED_BYTES", 1), self.assertRaises(DatasetError):
            self.load()
        with mock.patch.object(datasets, "MAX_EXPANDED_BYTES", 1), self.assertRaises(DatasetError):
            self.load()
        with mock.patch.object(datasets, "MAX_MANIFEST_BYTES", 1), self.assertRaises(DatasetError):
            self.load()
        with mock.patch.object(datasets, "MAX_MEMBERS", 2), self.assertRaises(DatasetError):
            self.load()
        header = b"\x93NUMPY\x01\x00" + struct.pack("<H", 4097) + b" " * 4097
        self.rewrite_zip([("B.npy", header), ("y.npy", self.npy(np.arange(self.rows, dtype=np.uint8) % 2))])
        with mock.patch.object(datasets.np, "load") as load, self.assertRaises(DatasetError):
            self.load()
        load.assert_not_called()

    def test_truncated_zip_and_payload_length_mismatch_fail_closed(self):
        path = self.directory() / "data.npz"
        path.write_bytes(path.read_bytes()[:-10])
        self.write_manifest(self.manifest())
        with self.assertRaises(DatasetError):
            self.load()
        self.rewrite_zip([("B.npy", self.npy(np.ones((self.rows, 8), dtype=np.int64)) + b"extra"),
                          ("y.npy", self.npy(np.arange(self.rows, dtype=np.uint8) % 2))])
        with self.assertRaises(DatasetError):
            self.load()

    def test_encrypted_zip_flag_is_rejected_before_member_open(self):
        path = self.directory() / "data.npz"
        blob = bytearray(path.read_bytes())
        local = blob.index(b"PK\x03\x04")
        central = blob.index(b"PK\x01\x02")
        blob[local + 6] |= 1
        blob[central + 8] |= 1
        path.write_bytes(blob)
        self.write_manifest(self.manifest())
        with self.assertRaises(DatasetError):
            self.load()

    def test_hardlinked_sources_are_rejected(self):
        for name in ("data.npz", "manifest.json"):
            path = self.directory() / name
            alias = self.root / ("alias-" + name)
            os.link(path, alias)
            try:
                with self.subTest(name=name), self.assertRaises(DatasetError):
                    self.load()
            finally:
                alias.unlink()
        self.load()

    def test_reparse_source_and_ancestor_are_rejected(self):
        original = Path.lstat
        for target in (self.root, self.directory(), self.directory() / "data.npz"):
            def unsafe(path, *args, **kwargs):
                if path == target:
                    return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, "lstat", unsafe), self.assertRaises(DatasetError):
                self.load()

    def test_file_identity_or_manifest_drift_during_validation_is_rejected(self):
        original = datasets.np.load
        for name in ("data.npz", "manifest.json"):
            self.write_fixture()
            path = self.directory() / name
            def substitute(*args, **kwargs):
                loaded = original(*args, **kwargs)
                replacement = self.root / "replacement"
                replacement.write_bytes(path.read_bytes())
                os.replace(replacement, path)
                return loaded
            with mock.patch.object(datasets.np, "load", side_effect=substitute), self.assertRaises(DatasetError):
                self.load()

    def test_source_content_drift_is_rejected_even_when_manifest_was_initially_valid(self):
        original = datasets.np.load
        path = self.directory() / "data.npz"
        def change(*args, **kwargs):
            loaded = original(*args, **kwargs)
            with path.open("r+b") as stream:
                stream.write(b"changed")
            return loaded
        with mock.patch.object(datasets.np, "load", side_effect=change), self.assertRaises(DatasetError):
            self.load()

    def test_single_class_fixed_sample_fails_without_label_conditioned_resampling(self):
        labels = np.zeros(self.rows, dtype=np.uint8)
        selected = np.random.default_rng(datasets.SELECTION_SEED).permutation(self.rows)[:32]
        outside = next(index for index in range(self.rows) if index not in set(selected))
        labels[outside] = 1
        self.write_fixture(y=labels)
        with self.assertRaises(DatasetError):
            self.load(max_rows=32)

    def test_disappearing_previously_read_source_is_rejected_not_reported_absent(self):
        original = datasets.np.load
        path = self.directory() / "manifest.json"
        def disappear(*args, **kwargs):
            loaded = original(*args, **kwargs)
            path.unlink()
            return loaded
        with mock.patch.object(datasets.np, "load", side_effect=disappear), self.assertRaises(DatasetError):
            self.load()

    def test_invalid_deflate_stream_is_a_controlled_dataset_rejection(self):
        path = self.directory() / "data.npz"
        blob = bytearray(path.read_bytes())
        start = blob.index(b"PK\x03\x04")
        name_length, extra_length = struct.unpack_from("<HH", blob, start + 26)
        payload = start + 30 + name_length + extra_length
        blob[payload] = 255
        path.write_bytes(blob)
        self.write_manifest(self.manifest())
        with self.assertRaises(DatasetError):
            self.load()

    def test_inventory_distinguishes_available_missing_and_rejected_without_exposing_arrays(self):
        self.write_fixture("bts")
        manifest = self.manifest("bts")
        manifest["data_receipt"]["sha256"] = "0" * 64
        self.write_manifest(manifest, "bts", bind=False)
        inventory = datasets.source_inventory(self.root)
        self.assertEqual({item["corpus"]: item["availability"] for item in inventory["datasets"]},
                         {"acs": "available", "bts": "rejected", "hmda": "missing", "tlc": "missing"})
        self.assertFalse(inventory["raw_corpora_scanned"])
        self.assertFalse(inventory["model_artifacts_loaded"])
        self.assertNotIn("synthetic-fixture-key", json.dumps(inventory))
        with self.assertRaises(DatasetUnavailable):
            datasets.source_inventory(self.root / "missing")


if __name__ == "__main__":
    unittest.main()
