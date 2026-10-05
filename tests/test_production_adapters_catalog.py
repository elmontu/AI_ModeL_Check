"""Catalog provenance, strict registration input, and read-only boundary tests."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from model_release_assurance.production_adapters import catalog

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"id", "label", "kind", "task", "corpus", "loader_id", "modality", "sector",
          "provenance_notes", "research_references"}


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / catalog.OPENML_MANIFEST).read_bytes()
        cls.manifest = json.loads(cls.original)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / catalog.OPENML_MANIFEST
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(self.original)

    def write(self, manifest):
        self.path.write_text(json.dumps(manifest, sort_keys=True, ensure_ascii=True), encoding="utf-8")

    def test_checked_in_catalog_exact_ids_and_entry_contract(self):
        entries = catalog.catalog_entries(ROOT)
        self.assertEqual(len(entries), 87)
        self.assertEqual(len({entry["id"] for entry in entries}), 87)
        kinds = {kind: sum(entry["kind"] == kind for entry in entries) for kind in
                 ("research_prepared", "bundled", "historical_unavailable", "openml_registered")}
        self.assertEqual(kinds, {"research_prepared": 4, "bundled": 4,
                               "historical_unavailable": 7, "openml_registered": 72})
        for entry in entries:
            with self.subTest(entry=entry["id"]):
                self.assertEqual(set(entry), FIELDS)
                self.assertIsInstance(entry["provenance_notes"], list)
                self.assertIsInstance(entry["research_references"], list)
                self.assertTrue(entry["provenance_notes"])
                self.assertTrue(entry["research_references"])
                self.assertNotIn("availability", entry)
                self.assertNotIn("passed", entry)
        self.assertEqual({entry["id"] for entry in entries[:4]}, {"acs", "bts", "hmda", "tlc"})
        self.assertEqual({entry["id"] for entry in entries if entry["kind"] == "historical_unavailable"},
                         {"uci-adult", "uci-covertype", "mnist", "eurosat-rgb", "wildchat-4.8m", "dolly-15k", "20newsgroups"})

    def test_catalog_does_not_require_raw_snapshots_or_data_root(self):
        self.assertEqual(len(list(self.root.rglob("*.json"))), 1)
        entries = catalog.catalog_entries(self.root)
        self.assertEqual(len(entries), 87)
        self.assertFalse((self.root / "reproduction/openml/raw").exists())
        self.assertEqual(len(list(self.root.rglob("*.*"))), 1)

    def test_unsupported_and_registration_are_explicit_not_training_success(self):
        for entry in catalog.catalog_entries(self.root):
            if entry["kind"] in {"openml_registered", "historical_unavailable"}:
                self.assertEqual(entry["task"], "unsupported")
                self.assertIsNone(entry["loader_id"])
                self.assertIsNone(entry["corpus"])
            if entry["kind"] == "openml_registered":
                self.assertIn("registered_not_proven_all_trained", " ".join(entry["provenance_notes"]))
                self.assertIn("no dataset license field", " ".join(entry["provenance_notes"]))
        indexed = {entry["id"]: entry for entry in catalog.catalog_entries(self.root)}
        self.assertEqual(indexed["sklearn-diabetes"]["task"], "regression")
        self.assertEqual(indexed["openml-37-v1"]["task"], "unsupported")
        self.assertIn("distinct", " ".join(indexed["sklearn-diabetes"]["provenance_notes"]))
        self.assertIn("distinct", " ".join(indexed["sklearn-digits"]["provenance_notes"]))

    def test_current_references_exist_and_retired_references_are_git_descriptions(self):
        for entry in catalog.catalog_entries(ROOT):
            for reference in entry["research_references"]:
                if reference.startswith("Git object 0b99589:"):
                    self.assertIn("docs/publication/2026-09-28/", reference)
                else:
                    self.assertTrue((ROOT / reference).is_file(), reference)
                    self.assertNotIn("docs/publication/", reference)

    def test_returns_independent_containers_in_stable_order(self):
        first = catalog.catalog_entries(self.root)
        expected = copy.deepcopy(first)
        first[0]["provenance_notes"].append("changed")
        first[1]["research_references"].clear()
        first[-1]["id"] = "changed"
        self.assertEqual(catalog.catalog_entries(self.root), expected)

    def test_formatting_and_crlf_do_not_change_reviewed_semantic_identity(self):
        self.path.write_bytes(json.dumps(self.manifest, indent=1).replace("\n", "\r\n").encode())
        self.assertEqual(catalog.catalog_entries(self.root), catalog.catalog_entries(ROOT))

    def test_missing_manifest_is_not_silent_static_only_success(self):
        self.path.unlink()
        with self.assertRaisesRegex(catalog.CatalogError, "missing"):
            catalog.catalog_entries(self.root)

    def test_size_limit_is_enforced_before_json_read(self):
        self.path.write_bytes(b" " * (catalog.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(catalog.CatalogError, "size bound"):
            catalog.catalog_entries(self.root)

    def test_duplicate_json_keys_nonfinite_and_huge_integers_fail(self):
        bad = (b'{"study_id":99,' + self.original.lstrip()[1:],
               b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}',
               b'{"study_id":' + b"9" * 5000 + b"}", b"\xff", b"[]")
        for content in bad:
            with self.subTest(prefix=content[:30]):
                self.path.write_bytes(content)
                with self.assertRaises(catalog.CatalogError):
                    catalog.catalog_entries(self.root)

    def test_deeply_nested_json_is_a_catalog_error(self):
        self.path.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
        with self.assertRaises(catalog.CatalogError):
            catalog.catalog_entries(self.root)

    def test_duplicate_dataset_ids_fail(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["datasets"][1] = copy.deepcopy(manifest["datasets"][0])
        self.write(manifest)
        with self.assertRaisesRegex(catalog.CatalogError, "duplicate"):
            catalog.catalog_entries(self.root)

    def test_suite_identity_count_unknown_fields_and_typed_ids_fail(self):
        mutations = (
            lambda value: value.update(study_id=100),
            lambda value: value.update(configured_dataset_count=71),
            lambda value: value.update(successful_dataset_count=True),
            lambda value: value.update(extra="ignored"),
            lambda value: value["datasets"][0].update(dataset_id=True),
            lambda value: value["datasets"][0].update(version=False),
            lambda value: value["datasets"][0].update(extra="ignored"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                self.write(manifest)
                with self.assertRaises(catalog.CatalogError):
                    catalog.catalog_entries(self.root)

    def test_dataset_receipt_path_shape_and_feature_integrity_fail(self):
        mutations = (
            lambda item: item.update(snapshot_sha256="bad"),
            lambda item: item.update(snapshot_path="../../outside.parquet"),
            lambda item: item.update(snapshot_path="https://example.invalid/data"),
            lambda item: item.update(snapshot_bytes=-1),
            lambda item: item.update(rows=item["rows"] + 1),
            lambda item: item["feature_names"].append(item["feature_names"][0]),
            lambda item: item["feature_dtypes"].update(unknown="int64"),
            lambda item: item["class_counts"].update(won=True),
            lambda item: item["feature_dtypes"].update(bkblk={"unsupported": "shape"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest["datasets"][0])
                self.write(manifest)
                with self.assertRaises(catalog.CatalogError):
                    catalog.catalog_entries(self.root)

    def test_valid_looking_metadata_mutation_still_breaks_pinned_identity(self):
        for field in ("name", "snapshot_sha256", "openml_url"):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest["datasets"][0][field] = "0" * 64 if field == "snapshot_sha256" else "changed"
                self.write(manifest)
                with self.assertRaisesRegex(catalog.CatalogError, "semantic digest"):
                    catalog.catalog_entries(self.root)

    def test_hardlink_substitution_is_rejected(self):
        original = self.path.with_name("original.json")
        self.path.rename(original)
        os.link(original, self.path)
        with self.assertRaisesRegex(catalog.CatalogError, "single-link"):
            catalog.catalog_entries(self.root)

    def test_reparse_or_symbolic_link_metadata_is_rejected(self):
        for mode, attributes in ((stat.S_IFREG, 0x400), (stat.S_IFLNK, 0)):
            with self.subTest(mode=mode):
                information = SimpleNamespace(st_mode=mode, st_file_attributes=attributes, st_nlink=1)
                with self.assertRaisesRegex(catalog.CatalogError, "single-link"):
                    catalog._stamp(information)

    def test_manifest_mutation_during_read_is_rejected(self):
        original_lstat = Path.lstat
        calls = 0
        path = self.path

        def changing_lstat(current, *args, **kwargs):
            nonlocal calls
            if current == path:
                calls += 1
                if calls == 2:
                    with path.open("ab") as stream:
                        stream.write(b" ")
            return original_lstat(current, *args, **kwargs)

        with mock.patch.object(Path, "lstat", changing_lstat):
            with self.assertRaisesRegex(catalog.CatalogError, "path changed"):
                catalog.catalog_entries(self.root)

    def test_root_traversal_is_rejected(self):
        with self.assertRaisesRegex(catalog.CatalogError, "traversal"):
            catalog.catalog_entries(self.root / "child" / "..")


if __name__ == "__main__":
    unittest.main()
