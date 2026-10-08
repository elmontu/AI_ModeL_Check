"""Standalone SLM file-integrity guards; no model, download or live-job access.

Run with: python -B -m unittest test_slm_training_history -v
Fixtures remain under the government repository's ignored verification folder.
"""
from __future__ import annotations

import gc
import importlib.util
from contextlib import closing
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("slm_training_history_demo", REPO / "scripts/train_slm_history_demo.py")
TRAINER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAINER)


class IsolatedFixtures(unittest.TestCase):
    def setUp(self):
        root = REPO / ".local/verification/subsequent-training-20261008/trainer-guard-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="guard-", dir=root)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(gc.collect)
        self.root = Path(self.temp.name)

    def checkpoint(self):
        checkpoint = self.root / "checkpoint"
        checkpoint.mkdir()
        # Hash guards operate on bytes, independently of the tensor loader.
        (checkpoint / "model.safetensors").write_bytes(b"fixture weights version 1")
        (checkpoint / "config.json").write_text('{"tie_word_embeddings":false}', encoding="utf-8")
        (checkpoint / "tokenizer.json").write_text('{"fixture":true}', encoding="utf-8")
        return checkpoint

    def fake_repository(self):
        repository = self.root / "repository"
        package = repository / "src/model_release_assurance"
        package.mkdir(parents=True)
        (package / "engine.py").write_bytes(b"# frozen fixture source\n")
        store = repository / ".local/demo-data"
        artifact = store / "jobs/original/artifacts/original.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b'{"retained":true}\n')
        (store / "cases").mkdir()
        database = store / "console.sqlite3"
        with closing(sqlite3.connect(database)) as connection, connection:
            for table in ("jobs", "cases", "government_audit_reviews"):
                connection.execute(f"CREATE TABLE {table}(id TEXT PRIMARY KEY, value TEXT)")
                connection.execute(f"INSERT INTO {table} VALUES(?,?)", ("original", "frozen"))
        return repository, database, artifact

class FileIntegrityTests(IsolatedFixtures):
    def test_canonical_hash_input_is_deterministic_and_preserves_unicode(self):
        first = {"b": [2, 1], "a": "agency \u03bb"}
        second = {"a": "agency \u03bb", "b": [2, 1]}
        self.assertEqual(TRAINER.canonical(first), TRAINER.canonical(second))
        self.assertIn("\u03bb".encode("utf-8"), TRAINER.canonical(first))
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                TRAINER.canonical({"loss": value})

    def test_immutable_write_refuses_existing_output_without_changing_bytes(self):
        output = self.root / "lineage.json"
        TRAINER.write_new(output, {"stage": 1})
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            TRAINER.write_new(output, {"stage": 2})
        self.assertEqual(output.read_bytes(), original)

    def test_checkpoint_manifest_requires_native_weight_files(self):
        checkpoint = self.root / "empty-checkpoint"
        checkpoint.mkdir()
        (checkpoint / "config.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "safetensors"):
            TRAINER.checkpoint_manifest(checkpoint)

    def test_manifest_binds_sorted_explicit_paths_sizes_and_file_hashes(self):
        checkpoint = self.checkpoint()
        manifest = TRAINER.checkpoint_manifest(checkpoint)
        self.assertEqual(manifest["format_version"], "native-hf-checkpoint/1")
        self.assertEqual([item["path"] for item in manifest["files"]], ["config.json", "model.safetensors", "tokenizer.json"])
        for item in manifest["files"]:
            file = checkpoint / item["path"]
            self.assertEqual(item["size_bytes"], file.stat().st_size)
            self.assertEqual(item["sha256"], TRAINER.digest(file))
        self.assertEqual(manifest, TRAINER.checkpoint_manifest(checkpoint))

    def test_same_size_weight_tampering_changes_native_checkpoint_binding(self):
        checkpoint = self.checkpoint()
        before = TRAINER.checkpoint_manifest(checkpoint)
        weights = checkpoint / "model.safetensors"
        original = weights.read_bytes()
        weights.write_bytes(original[:-1] + b"2")
        after = TRAINER.checkpoint_manifest(checkpoint)
        self.assertEqual(len(original), weights.stat().st_size)
        self.assertNotEqual(before["aggregate_sha256"], after["aggregate_sha256"])

    def test_renaming_identical_weights_changes_checkpoint_binding(self):
        checkpoint = self.checkpoint()
        before = TRAINER.checkpoint_manifest(checkpoint)
        (checkpoint / "model.safetensors").rename(checkpoint / "renamed.safetensors")
        after = TRAINER.checkpoint_manifest(checkpoint)
        self.assertNotEqual(before["aggregate_sha256"], after["aggregate_sha256"])

    def test_changed_tokenizer_bytes_cannot_inherit_the_original_checkpoint_hash(self):
        checkpoint = self.checkpoint()
        before = TRAINER.checkpoint_manifest(checkpoint)
        (checkpoint / "tokenizer.json").write_bytes(b'{"fixture":false}')
        after = TRAINER.checkpoint_manifest(checkpoint)
        self.assertNotEqual(before["aggregate_sha256"], after["aggregate_sha256"])

    @unittest.skipUnless(os.name == "nt", "D-drive cache controls apply to the Windows local demo")
    def test_d_storage_guard_rejects_c_root_onedrive_and_ordinary_files(self):
        for path in (r"C:\unwritten-fixture", "D:\\", r"D:\OneDrive - Agency\unwritten-fixture"):
            with self.assertRaises(ValueError):
                TRAINER.safe_d(path)
        file = self.root / "ordinary-file"
        file.write_bytes(b"file")
        with self.assertRaisesRegex(ValueError, "ordinary directory"):
            TRAINER.safe_d(file)
        self.assertEqual(TRAINER.safe_d(self.root), self.root)

    @unittest.skipUnless(os.name == "nt", "D-drive cache controls apply to the Windows local demo")
    def test_all_configured_caches_and_python_temporary_files_remain_in_d_fixture(self):
        previous_temp = tempfile.tempdir
        self.addCleanup(setattr, tempfile, "tempdir", previous_temp)
        with patch.dict(os.environ):
            TRAINER.configure_caches(self.root)
            for variable in ("HF_HOME", "HF_HUB_CACHE", "HF_XET_CACHE", "TORCH_HOME", "PIP_CACHE_DIR", "TEMP", "TMP"):
                directory = Path(os.environ[variable])
                self.assertEqual(directory.drive.lower(), "d:")
                self.assertTrue(directory.is_relative_to(self.root))
                self.assertTrue(directory.is_dir())
            self.assertEqual(Path(tempfile.tempdir), Path(os.environ["TEMP"]))

    def test_preservation_checks_allow_new_jobs_and_leave_original_rows_and_evidence_unchanged(self):
        repository, database, _ = self.fake_repository()
        before = TRAINER.preserved_snapshot(repository)
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("INSERT INTO jobs VALUES(?,?)", ("new", "new training diagnostic"))
        result = TRAINER.verify_preserved(repository, before)
        self.assertEqual(result["old_jobs_unchanged"], 1)
        self.assertEqual(result["old_cases_unchanged"], 1)
        self.assertEqual(result["old_reviews_unchanged"], 1)
        self.assertEqual(result["package_python_sources_unchanged"], 1)
        self.assertEqual(result["old_evidence_files_unchanged"], 1)

    def test_changed_old_evidence_is_rejected(self):
        repository, _, artifact = self.fake_repository()
        before = TRAINER.preserved_snapshot(repository)
        artifact.write_bytes(b'{"retained":false}\n')
        with self.assertRaisesRegex(ValueError, "retained source/evidence changed"):
            TRAINER.verify_preserved(repository, before)

    def test_changed_old_package_source_is_rejected(self):
        repository, _, _ = self.fake_repository()
        before = TRAINER.preserved_snapshot(repository)
        (repository / "src/model_release_assurance/engine.py").write_bytes(b"# changed fixture source\n")
        with self.assertRaises(ValueError):
            TRAINER.verify_preserved(repository, before)

    def test_new_package_python_file_is_rejected_as_a_change_to_native_clearance_source_inventory(self):
        repository, _, _ = self.fake_repository()
        before = TRAINER.preserved_snapshot(repository)
        (repository / "src/model_release_assurance/new_runtime.py").write_bytes(b"# fixture addition\n")
        with self.assertRaises(ValueError):
            TRAINER.verify_preserved(repository, before)

    def test_updated_or_removed_original_database_rows_are_rejected(self):
        repository, database, _ = self.fake_repository()
        before = TRAINER.preserved_snapshot(repository)
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("UPDATE government_audit_reviews SET value=? WHERE id=?", ("changed", "original"))
        with self.assertRaisesRegex(ValueError, "database rows changed"):
            TRAINER.verify_preserved(repository, before)
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("UPDATE government_audit_reviews SET value=? WHERE id=?", ("frozen", "original"))
            connection.execute("DELETE FROM cases WHERE id=?", ("original",))
        with self.assertRaisesRegex(ValueError, "database rows changed"):
            TRAINER.verify_preserved(repository, before)




class ConversionArchiveGuardTests(IsolatedFixtures):
    @unittest.skipUnless(os.name == "nt", "D-drive conversion tools apply to the Windows local demo")
    def test_conversion_archive_path_traversal_is_rejected_before_writing_outside_destination(self):
        import zipfile
        archive = self.root / "traversal.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("../escaped.py", "untrusted")
        with self.assertRaisesRegex(ValueError, "Unsafe conversion ZIP path"):
            TRAINER.verified_extract(archive, self.root / "tools")
        self.assertFalse((self.root / "escaped.py").exists())

    @unittest.skipUnless(os.name == "nt", "D-drive conversion tools apply to the Windows local demo")
    def test_conversion_zip_symlink_metadata_is_refused_without_creating_a_link(self):
        import stat
        import zipfile
        archive = self.root / "symlink.zip"
        entry = zipfile.ZipInfo("tool-link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(entry, "../outside")
        with self.assertRaisesRegex(ValueError, "ZIP symlink refused"):
            TRAINER.verified_extract(archive, self.root / "tools")
        self.assertFalse((self.root / "tools/tool-link").exists())

    @unittest.skipUnless(os.name == "nt", "D-drive conversion tools apply to the Windows local demo")
    def test_cached_extracted_tool_tampering_is_refused_and_original_bytes_are_not_overwritten(self):
        import zipfile
        archive = self.root / "converter.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("converter.py", "# official fixture\n")
        destination = self.root / "tools"
        self.assertEqual(TRAINER.verified_extract(archive, destination), 1)
        converter = destination / "converter.py"
        converter.write_bytes(b"# altered cached fixture\n")
        with self.assertRaisesRegex(ValueError, "differs from pinned archive"):
            TRAINER.verified_extract(archive, destination)
        self.assertEqual(converter.read_bytes(), b"# altered cached fixture\n")

    def test_cached_official_archive_must_match_its_pinned_hash_without_network_fallback(self):
        archive = self.root / "cached.zip"
        archive.write_bytes(b"immutable official fixture")
        original = archive.read_bytes()
        with patch.object(TRAINER, "build_opener") as network:
            TRAINER.download_official_archive("https://example.invalid/unused", archive, TRAINER.digest(archive))
            with self.assertRaisesRegex(ValueError, "archive hash mismatch"):
                TRAINER.download_official_archive("https://example.invalid/unused", archive, "f" * 64)
            network.assert_not_called()
        self.assertEqual(archive.read_bytes(), original)

if __name__ == "__main__":
    unittest.main()

