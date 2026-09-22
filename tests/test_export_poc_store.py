"""Fault, history and byte-delivery tests for the synthetic export broker."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.export_poc.store import ExportDenied, ExportStore
from model_release_assurance.export_poc import mechanism


class ExportStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ExportStore(self.root)

    def denied(self, code, call, *args, **kwargs):
        with self.assertRaises(ExportDenied) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def first(self):
        self.store.prepare("first", 1, "first", 0)
        return self.store.commit("first", 0)

    def mutate(self, sql, values=()):
        db = sqlite3.connect(self.store.path)
        try:
            with db:
                db.execute(sql, values)
        finally:
            db.close()

    def test_staged_bytes_and_private_state_are_not_public(self):
        candidate = self.store.prepare("first", 1, "first", 0)
        self.assertEqual(candidate["status"], "prepared")
        self.denied("not_committed", self.store.download, "first")
        summary = self.store.status()
        self.assertEqual(summary["privacy_ratio"], 1)
        self.assertEqual(summary["releases"], [])
        self.assertNotIn("artifact_sha256", json.dumps(summary))
        self.assertEqual(summary["mechanism_source_sha256"], self.store.mechanism_sha256)
        self.assertNotIn("private_state", json.dumps(summary))
        self.assertNotIn("bundle", json.dumps(summary))
        self.assertEqual(set(candidate), {"request_id", "stage", "route", "base_revision", "status", "stale"})
        self.assertFalse(any(path.suffix in {".json", ".bin"} for path in self.root.iterdir()))

    def test_actual_committed_bytes_and_parent_binding_survive_restart(self):
        first = self.first()
        first_bytes = self.store.download(first["release_id"])
        self.assertEqual(sha256(first_bytes).hexdigest(), first["artifact_sha256"])
        restored = ExportStore(self.root)
        self.assertEqual(restored.download(first["release_id"]), first_bytes)
        restored.prepare("second", 2, "retained-state", 1)
        second = restored.commit("second", 1)
        second_bytes = restored.download(second["release_id"])
        self.assertEqual(json.loads(second_bytes)["parent_artifact_sha256"], first["artifact_sha256"])
        self.assertEqual(second["parent_artifact_sha256"], first["artifact_sha256"])
        self.assertEqual(restored.status()["privacy_ratio"], 4)
        self.assertEqual(len(restored.status()["releases"]), 2)
        self.assertEqual(restored.download(first["release_id"]), first_bytes)

    def test_prepare_and_commit_retry_do_not_regenerate(self):
        original = self.store.prepare("same", 1, "first", 0)
        with patch("model_release_assurance.export_poc.store.mechanism.first_release", side_effect=AssertionError("redraw")):
            self.assertEqual(self.store.prepare("same", 1, "first", 0), original)
            receipt = self.store.commit("same", 0)
            blob = self.store.download(receipt["release_id"])
            self.assertEqual(self.store.commit("same", 0), receipt)
            self.assertEqual(self.store.prepare("same", 1, "first", 0)["status"], "committed")
            self.assertEqual(self.store.download(receipt["release_id"]), blob)
        self.assertEqual(len(self.store.status()["releases"]), 1)

    def test_request_key_parameter_reuse_is_rejected(self):
        self.store.prepare("same", 1, "first", 0)
        self.denied("idempotency_conflict", self.store.prepare, "same", 2, "retained-state", 0)
        self.denied("idempotency_conflict", self.store.prepare, "same", 1, "first", 1)
        self.denied("stale_history", self.store.commit, "same", 1)

    def test_one_concurrent_commit_wins_and_other_staged_candidate_is_stale(self):
        self.store.prepare("a", 1, "first", 0)
        self.store.prepare("b", 1, "first", 0)
        def commit(key):
            try:
                return ExportStore(self.root).commit(key, 0)
            except ExportDenied as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(commit, ["a", "b"]))
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertIn("stale_history", results)
        status = self.store.status()
        self.assertEqual(status["revision"], 1)
        self.assertEqual(sum(item["stale"] for item in status["candidates"]), 1)
        self.assertEqual(len(status["releases"]), 1)

    def test_no_stage_skips_or_privacy_reset_and_no_alternate_second_commit(self):
        self.denied("invalid_stage", self.store.prepare, "skip", 2, "independent", 0)
        self.first()
        self.denied("invalid_stage", self.store.prepare, "reset", 1, "first", 1)
        self.store.prepare("a", 2, "retained-state", 1)
        self.store.prepare("b", 2, "independent", 1)
        self.store.commit("a", 1)
        self.denied("stale_history", self.store.commit, "b", 1)
        self.denied("budget_exhausted", self.store.prepare, "new", 2, "central-count", 2)
        self.denied("budget_exhausted", self.store.prepare, "reset", 1, "first", 2)

    def test_revocation_retains_history_and_retry_does_not_reactivate(self):
        receipt = self.first()
        downloaded = self.store.download(receipt["release_id"])
        revoked = self.store.revoke(receipt["release_id"])
        self.assertEqual(revoked["privacy_ratio"], 2)
        self.assertEqual(revoked["revision"], 2)
        self.assertEqual(self.store.revoke(receipt["release_id"]), revoked)
        self.assertEqual(self.store.commit("first", 0), receipt)
        self.denied("revoked", self.store.download, receipt["release_id"])
        self.assertEqual(sha256(downloaded).hexdigest(), receipt["artifact_sha256"])
        self.store.prepare("second", 2, "independent", 2)
        second = self.store.commit("second", 2)
        self.assertEqual(second["parent_artifact_sha256"], receipt["artifact_sha256"])
        self.store.revoke(second["release_id"])
        status = self.store.status()
        self.assertEqual(status["privacy_ratio"], 4)
        self.assertEqual(len(status["releases"]), 2)
        self.denied("budget_exhausted", self.store.prepare, "again", 1, "first", status["revision"])

    def test_revocation_invalidates_an_already_prepared_next_candidate(self):
        first = self.first()
        self.store.prepare("next", 2, "retained-state", 1)
        self.store.revoke(first["release_id"])
        self.denied("stale_history", self.store.commit, "next", 1)
        self.assertEqual(self.store.status()["privacy_ratio"], 2)

    def test_precommit_blob_corruption_is_rejected_without_partial_history(self):
        self.store.prepare("first", 1, "first", 0)
        self.mutate("UPDATE candidates SET bundle=? WHERE request_id='first'", (b"changed",))
        self.denied("tampered", self.store.commit, "first", 0)
        self.assertEqual(self.store.status()["releases"], [])
        self.assertEqual(self.store.status()["privacy_ratio"], 1)

    def test_download_rechecks_blob_and_private_state_integrity(self):
        receipt = self.first()
        self.mutate("UPDATE candidates SET private_state='{}' WHERE request_id='first'")
        self.denied("tampered", self.store.download, receipt["release_id"])
        self.denied("tampered", self.store.prepare, "second", 2, "independent", 1)
        self.denied("tampered", self.store.status)
        with closing(sqlite3.connect(self.store.path)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM releases").fetchone()[0], 1)

    def test_certificate_corruption_and_parent_substitution_are_rejected(self):
        first = self.first()
        self.store.prepare("second", 2, "independent", 1)
        self.mutate("UPDATE candidates SET first_digest=? WHERE request_id='second'", ("0" * 64,))
        self.denied("tampered", self.store.commit, "second", 1)
        self.mutate("UPDATE candidates SET certificate='{}' WHERE request_id='first'")
        self.denied("tampered", self.store.download, first["release_id"])

    def test_failed_commit_rolls_back_every_state_change(self):
        self.store.prepare("first", 1, "first", 0)
        for fail_at in ("after_state_write", "before_commit"):
            def fault(point):
                if point == fail_at:
                    raise RuntimeError("injected interruption")
            broken = ExportStore(self.root, failpoint=fault)
            with self.assertRaisesRegex(RuntimeError, "injected"):
                broken.commit("first", 0)
            status = self.store.status()
            self.assertEqual(status["revision"], 0)
            self.assertEqual(status["privacy_ratio"], 1)
            self.assertEqual(status["releases"], [])
            self.assertEqual(status["candidates"][0]["status"], "prepared")
        self.assertEqual(self.store.commit("first", 0)["revision"], 1)

    def test_lost_commit_acknowledgement_returns_same_durable_export_on_retry(self):
        self.store.prepare("first", 1, "first", 0)
        def fault(point):
            if point == "after_commit":
                raise RuntimeError("lost acknowledgement")
        with self.assertRaisesRegex(RuntimeError, "lost"):
            ExportStore(self.root, failpoint=fault).commit("first", 0)
        restored = ExportStore(self.root)
        receipt = restored.status()["releases"][0]
        receipt.pop("revoked")
        self.assertEqual(restored.commit("first", 0), receipt)
        self.assertEqual(sha256(restored.download(receipt["release_id"])).hexdigest(), receipt["artifact_sha256"])
        self.assertEqual(restored.status()["revision"], 1)

    def test_abrupt_process_death_before_commit_does_not_publish_partial_state(self):
        self.store.prepare("first", 1, "first", 0)
        child = """import os, sys
from pathlib import Path
from model_release_assurance.export_poc.store import ExportStore
def die(point):
    if point == 'before_commit':
        os._exit(23)
ExportStore(Path(sys.argv[1]), failpoint=die).commit('first', 0)
"""
        result = subprocess.run([sys.executable, "-B", "-c", child, str(self.root)],
                                capture_output=True, timeout=20,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 23, result.stderr.decode(errors="replace"))
        reopened = ExportStore(self.root)
        self.assertEqual(reopened.status()["revision"], 0)
        self.assertEqual(reopened.status()["releases"], [])
        self.assertEqual(reopened.commit("first", 0)["revision"], 1)

    def test_allowlist_rejects_private_fields_even_with_recomputed_blob_digest(self):
        self.store.prepare("first", 1, "first", 0)
        db = sqlite3.connect(self.store.path)
        try:
            blob = db.execute("SELECT bundle FROM candidates WHERE request_id='first'").fetchone()[0]
        finally:
            db.close()
        bundle = json.loads(blob)
        bundle["private_state"] = {"E": [0, 1]}
        corrupted = json.dumps(bundle).encode()
        self.mutate("UPDATE candidates SET bundle=?,artifact_digest=? WHERE request_id='first'",
                    (corrupted, sha256(corrupted).hexdigest()))
        self.denied("tampered", self.store.commit, "first", 0)
        self.assertEqual(self.store.status()["releases"], [])

    def test_trusted_producer_accidentally_including_raw_field_cannot_stage_export(self):
        original = mechanism.first_release
        def bad_producer():
            state, blob, certificate = original()
            bundle = json.loads(blob)
            bundle["raw_records"] = state["X"]
            blob = json.dumps(bundle).encode()
            state["first_bundle_sha256"] = sha256(blob).hexdigest()
            return state, blob, certificate
        with patch("model_release_assurance.export_poc.store.mechanism.first_release", side_effect=bad_producer):
            self.denied("tampered", self.store.prepare, "first", 1, "first", 0)
        self.assertEqual(self.store.status()["candidates"], [])

    def test_corrupted_receipt_cannot_be_replayed_or_used_for_download(self):
        receipt = self.first()
        changed = dict(receipt, artifact_sha256="0" * 64)
        self.mutate("UPDATE candidates SET receipt=? WHERE request_id='first'", (json.dumps(changed),))
        self.denied("tampered", self.store.commit, "first", 0)
        self.denied("tampered", self.store.status)
        self.denied("tampered", self.store.download, receipt["release_id"])

    def test_unsupported_route_invalid_revision_and_unknown_requests_fail_closed(self):
        self.denied("invalid_request", self.store.prepare, "a", 1, "raw-upload", 0)
        self.denied("invalid_request", self.store.prepare, "../file", 1, "first", 0)
        self.denied("invalid_request", self.store.prepare, "a", True, "first", 0)
        self.denied("invalid_request", self.store.prepare, "a", 1, "first", True)
        self.denied("stale_history", self.store.prepare, "a", 1, "first", 9)
        self.denied("not_found", self.store.commit, "unknown", 0)
        self.denied("not_found", self.store.revoke, "unknown")

    def test_restart_rejects_changed_producer_source_without_resetting_history(self):
        receipt = self.first()
        changed_source = self.root / "changed_mechanism.py"
        changed_source.write_text("# different producer revision\n", encoding="utf-8")
        with patch.object(mechanism, "__file__", str(changed_source)):
            self.denied("changed_implementation", ExportStore, self.root)
        restored = ExportStore(self.root)
        self.assertEqual(restored.status()["privacy_ratio"], 2)
        self.assertEqual(sha256(restored.download(receipt["release_id"])).hexdigest(), receipt["artifact_sha256"])

    def test_read_only_open_never_creates_a_missing_directory_or_database(self):
        absent = self.root / "absent"
        self.denied("not_initialized", ExportStore.open_read_only, absent)
        self.denied("not_initialized", ExportStore.open_existing, absent)
        self.assertFalse(absent.exists())

    def test_missing_database_cannot_be_recreated_by_live_handle_or_restart(self):
        self.first()
        self.store.path.unlink()
        self.denied("history_missing", self.store.status)
        self.denied("history_missing", self.store.prepare, "again", 1, "first", 0)
        self.denied("history_missing", ExportStore, self.root)
        self.assertFalse(self.store.path.exists())
        self.assertTrue(self.store.marker.is_file())

    def test_truncated_database_is_not_reinitialized(self):
        self.first()
        self.store.path.write_bytes(b"")
        self.denied("unsupported_schema", ExportStore, self.root)
        self.denied("unsupported_schema", self.store.status)
        self.assertEqual(self.store.path.read_bytes(), b"")

    def test_read_only_diagnostic_does_not_modify_any_source_files(self):
        self.first()
        self.store.prepare("second", 2, "retained-state", 1)
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.iterdir()}
        readonly = ExportStore.open_read_only(self.root)
        report = readonly.verify_history()
        self.assertEqual(report["committed_count"], 1)
        self.assertEqual(report["prepared_count"], 1)
        self.assertTrue(report["snapshot_only"])
        self.assertFalse(report["can_authorize"])
        self.assertEqual(readonly.status()["revision"], 1)
        for call, args in ((readonly.prepare, ("other", 2, "independent", 1)),
                           (readonly.commit, ("second", 1)), (readonly.revoke, ("unknown",)),
                           (readonly.download, ("unknown",))):
            self.denied("read_only", call, *args)
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.iterdir()}
        self.assertEqual(before, after)

    def test_read_only_snapshot_includes_live_wal_without_touching_its_sidecars(self):
        self.first()
        writer = sqlite3.connect(self.store.path)
        try:
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("UPDATE releases SET revoked=1")
            writer.execute("UPDATE meta SET revision=2")
            writer.commit()
            self.assertGreater(Path(str(self.store.path) + "-wal").stat().st_size, 0)
            before = {path.name: path.read_bytes() for path in self.root.iterdir()}
            report = ExportStore.open_read_only(self.root).verify_history()
            self.assertEqual(report["revision"], 2)
            self.assertEqual(report["revoked_count"], 1)
            self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})
        finally:
            writer.close()

    def test_verification_does_not_publish_precommit_hashes_or_private_values(self):
        self.store.prepare("first", 1, "first", 0)
        with closing(sqlite3.connect(self.store.path)) as db, db:
            private = db.execute("SELECT artifact_digest,state_digest,certificate_digest,private_state FROM candidates").fetchone()
        report = self.store.verify_history()
        encoded = json.dumps(report)
        for value in private:
            self.assertNotIn(value, encoded)
        self.assertEqual(report["committed_count"], 0)
        self.assertEqual(report["public_history_sha256"], sha256(b"[]").hexdigest())

    def test_inconsistent_accounting_blocks_all_operations(self):
        first = self.first()
        self.store.prepare("second", 2, "independent", 1)
        self.mutate("UPDATE meta SET privacy_ratio=1")
        for call, args in ((self.store.status, ()), (self.store.verify_history, ()),
                           (self.store.prepare, ("third", 2, "retained-state", 1)),
                           (self.store.commit, ("second", 1)),
                           (self.store.download, (first["release_id"],)),
                           (self.store.revoke, (first["release_id"],))):
            self.denied("tampered", call, *args)

    def test_revision_must_count_each_disclosure_and_revocation(self):
        receipt = self.first()
        self.store.revoke(receipt["release_id"])
        self.mutate("UPDATE meta SET revision=1")
        self.denied("tampered", self.store.verify_history)

    def test_deleted_disclosure_cannot_leave_an_orphan_receipt(self):
        self.first()
        self.mutate("DELETE FROM releases")
        self.mutate("UPDATE meta SET revision=0,privacy_ratio=1")
        self.denied("tampered", self.store.verify_history)

    def test_missing_first_stage_is_detected_even_if_accounting_is_rewritten(self):
        self.first()
        self.store.prepare("second", 2, "retained-state", 1)
        self.store.commit("second", 1)
        self.mutate("DELETE FROM releases WHERE stage=1")
        self.mutate("UPDATE candidates SET receipt=NULL WHERE stage=1")
        self.mutate("UPDATE meta SET revision=1,privacy_ratio=2")
        self.denied("tampered", self.store.status)

    def test_parent_must_bind_actual_first_release_even_if_local_hashes_are_recomputed(self):
        self.first()
        self.store.prepare("second", 2, "retained-state", 1)
        receipt = self.store.commit("second", 1)
        with closing(sqlite3.connect(self.store.path)) as db, db:
            row = db.execute("SELECT private_state,certificate,bundle,receipt FROM candidates WHERE stage=2").fetchone()
            state, certificate, bundle, saved_receipt = map(json.loads, row)
            false_parent = "0" * 64
            state["first_bundle_sha256"] = false_parent
            certificate["first_artifact_sha256"] = false_parent
            bundle["parent_artifact_sha256"] = false_parent
            saved_receipt["parent_artifact_sha256"] = false_parent
            blob = json.dumps(bundle).encode()
            saved_receipt["artifact_sha256"] = sha256(blob).hexdigest()
            state_text, cert_text = json.dumps(state), json.dumps(certificate)
            db.execute("UPDATE candidates SET first_digest=?,private_state=?,state_digest=?,certificate=?,"
                       "certificate_digest=?,bundle=?,artifact_digest=?,receipt=? WHERE stage=2",
                       (false_parent, state_text, sha256(state_text.encode()).hexdigest(), cert_text,
                        sha256(cert_text.encode()).hexdigest(), blob, sha256(blob).hexdigest(), json.dumps(saved_receipt)))
        self.denied("tampered", self.store.download, receipt["release_id"])
        self.denied("tampered", self.store.verify_history)

    def test_corrupted_earlier_artifact_blocks_delivery_of_later_release(self):
        self.first()
        self.store.prepare("second", 2, "independent", 1)
        second = self.store.commit("second", 1)
        self.mutate("UPDATE candidates SET bundle=? WHERE stage=1", (b"broken",))
        self.denied("tampered", self.store.download, second["release_id"])

    def test_legacy_schema_read_only_does_not_migrate_then_writable_open_binds_it(self):
        receipt = self.first()
        self.mutate("DROP TABLE history_identity")
        self.store.marker.unlink()
        before = self.store.path.read_bytes()
        readonly = ExportStore.open_read_only(self.root)
        self.assertEqual(readonly.verify_history()["revision"], 1)
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertFalse(self.store.marker.exists())
        restored = ExportStore.open_existing(self.root)
        self.assertTrue(restored.marker.exists())
        self.assertEqual(restored.commit("first", 0), receipt)

    def test_unknown_schema_and_missing_tables_are_denied_without_reset(self):
        self.mutate("CREATE TABLE unknown_extension (x INTEGER)")
        self.denied("unsupported_schema", ExportStore.open_existing, self.root)
        self.mutate("DROP TABLE unknown_extension")
        self.mutate("DROP TABLE implementation")
        self.denied("unsupported_schema", self.store.verify_history)

    def test_changed_marker_or_identity_cannot_rebind_an_initialized_store(self):
        self.first()
        self.store.marker.write_text('{"version":1,"history_id":"wrong"}', encoding="utf-8")
        self.denied("tampered", ExportStore.open_existing, self.root)

    def test_source_binding_is_rechecked_on_existing_live_handle(self):
        self.first()
        changed = self.root / "different.py"
        changed.write_text("# other implementation", encoding="utf-8")
        with patch.object(mechanism, "__file__", str(changed)):
            self.denied("changed_implementation", self.store.verify_history)

    def test_malformed_sqlite_artifact_types_are_predictably_denied(self):
        self.first()
        for column, bad_value in (("bundle", "not a blob"), ("private_state", b"not text"),
                                   ("certificate", b"not text")):
            with self.subTest(column=column):
                with closing(sqlite3.connect(self.store.path)) as db:
                    original = db.execute(f"SELECT {column} FROM candidates WHERE stage=1").fetchone()[0]
                self.mutate(f"UPDATE candidates SET {column}=? WHERE stage=1", (bad_value,))
                self.denied("tampered", self.store.status)
                self.mutate(f"UPDATE candidates SET {column}=? WHERE stage=1", (original,))

    def test_revocation_then_second_commit_retains_valid_stale_candidate(self):
        first = self.first()
        self.store.prepare("stale", 2, "independent", 1)
        self.store.revoke(first["release_id"])
        self.store.prepare("current", 2, "retained-state", 2)
        self.store.commit("current", 2)
        report = ExportStore.open_existing(self.root).verify_history()
        self.assertEqual((report["revision"], report["committed_count"], report["prepared_count"]), (3, 2, 1))
        self.denied("stale_history", self.store.commit, "stale", 1)

    def test_added_columns_and_schema_versions_require_explicit_migration(self):
        self.mutate("PRAGMA user_version=9")
        self.denied("unsupported_schema", self.store.verify_history)
        self.mutate("PRAGMA user_version=0")
        self.mutate("ALTER TABLE meta ADD COLUMN unknown INTEGER")
        self.denied("unsupported_schema", self.store.status)


if __name__ == "__main__":
    unittest.main()
