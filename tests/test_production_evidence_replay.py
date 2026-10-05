"""Captured-byte numerical replay and bounded artifact-custody regressions."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_evidence import replay
from model_release_assurance.production_evidence.contracts import EvidenceError, NATIVE_ARTIFACT_NAMES


def encoded(value):
    return canonical_bytes(value) + b"\n"


def decoded(blobs, name):
    return json.loads(blobs[name])


def restamp(blobs, name, value):
    blobs[name] = encoded(value)
    if name != "result.json":
        receipt = decoded(blobs, "result.json")
        receipt["files"][name] = hashlib.sha256(blobs[name]).hexdigest()
        blobs["result.json"] = encoded(receipt)


class EvidenceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="evidence-replay-")
        cls.root = Path(cls.workspace.name)
        cls.runs, cls.bundles = {}, {}
        generator = np.random.default_rng(982)
        x = generator.normal(size=(240, 4))
        for task in ("classification", "regression"):
            y = (np.where(x[:, 0] < -.5, -2, np.where(x[:, 0] > .5, 5, 1))
                 if task == "classification" else x[:, 0] + .1 * x[:, 1])
            output = cls.root / task
            receipt = native.run_native(x, y, dataset_id="public-synthetic-evidence-test", source_sha256="a" * 64,
                feature_names=["a", "b", "c", "d"], task=task, output=output)
            if receipt["status"] != "completed":
                raise AssertionError(receipt)
            cls.runs[task] = output
            cls.bundles[task] = replay.snapshot_native_bundle(output)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root, prefix="case-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"
        self.blobs = dict(self.bundles["classification"])

    def copy_run(self):
        shutil.copytree(self.runs["classification"], self.output)
        return self.output

    def test_classification_and_regression_replay_match_existing_native_verifier(self):
        for task, blobs in self.bundles.items():
            with self.subTest(task=task):
                verified = replay.replay_native_bundle(blobs)
                self.assertEqual(verified, native.replay_run(self.runs[task]))
                self.assertEqual(verified["status"], "passed")
                self.assertIn("not_authenticity_or_original_training", verified["verification_scope"])
                for flag in ("can_clear", "authorization_eligible", "production_authorized", "model_delivery",
                             "hostile_code_isolated", "network_isolated"):
                    self.assertIs(verified[flag], False)

    def test_exact_manifest_of_captured_bytes_is_owned(self):
        manifest = replay.artifact_manifest(self.blobs)
        self.assertEqual(set(manifest), set(NATIVE_ARTIFACT_NAMES))
        for name, content in self.blobs.items():
            self.assertEqual(manifest[name], {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)})
        expected = copy.deepcopy(manifest)
        manifest["candidate.json"]["sha256"] = "0" * 64
        self.assertEqual(replay.artifact_manifest(self.blobs), expected)

    def test_no_artifact_path_reads_after_snapshot(self):
        self.copy_run()
        blobs = replay.snapshot_native_bundle(self.output)
        (self.output / "candidate.json").write_bytes(b"changed after capture")
        with mock.patch.object(native, "_read", side_effect=AssertionError("Artifact path reopened")):
            self.assertEqual(replay.replay_native_bundle(blobs)["status"], "passed")
        with self.assertRaises(EvidenceError):
            replay.replay_native_bundle(replay.snapshot_native_bundle(self.output))

    def test_owned_mapping_survives_caller_mutation_during_replay(self):
        original = native._arrays
        called = []
        def mutate(*args, **kwargs):
            called.append(True)
            self.blobs.clear()
            return original(*args, **kwargs)
        with mock.patch.object(native, "_arrays", mutate):
            self.assertEqual(replay.replay_native_bundle(self.blobs)["status"], "passed")
        self.assertTrue(called)
        self.assertEqual(self.blobs, {})

    def test_changed_artifact_fails_receipt_integrity(self):
        for name in NATIVE_ARTIFACT_NAMES:
            with self.subTest(name=name):
                blobs = dict(self.blobs)
                if name == "result.json":
                    value = decoded(blobs, name)
                    value["status"] = "failed"
                    blobs[name] = encoded(value)
                else:
                    blobs[name] += b" "
                with self.assertRaises(EvidenceError):
                    replay.replay_native_bundle(blobs)

    def test_consistently_restamped_metrics_are_recomputed(self):
        report = decoded(self.blobs, "report.json")
        report["utility"]["accuracy"] = .123
        restamp(self.blobs, "report.json", report)
        receipt = decoded(self.blobs, "result.json")
        receipt["utility"] = report["utility"]
        self.blobs["result.json"] = encoded(receipt)
        with self.assertRaises(EvidenceError):
            replay.replay_native_bundle(self.blobs)

    def test_restamped_predictions_and_group_scores_are_recomputed(self):
        for name in ("predictions.json", "scores.json"):
            with self.subTest(name=name):
                blobs = dict(self.blobs)
                value = decoded(blobs, name)
                if name == "predictions.json":
                    value["predictions"][0] = [.333, .333, .334]
                else:
                    value["scores"]["target"]["member"][0] = 123.
                restamp(blobs, name, value)
                with self.assertRaises(EvidenceError):
                    replay.replay_native_bundle(blobs)

    def test_dataset_receipt_restamp_cannot_substitute_plan_data(self):
        data = decoded(self.blobs, "dataset.json")
        data["y"][0] = 123
        restamp(self.blobs, "dataset.json", data)
        with self.assertRaises(EvidenceError):
            replay.replay_native_bundle(self.blobs)

    def test_candidate_lineage_runtime_source_and_task_changes_fail(self):
        for field, value in (("source_sha256", "b" * 64), ("dataset_id", "other-dataset"),
                             ("implementation_sha256", "0" * 64), ("training_rows", 1),
                             ("adapter_version", "2.0.0")):
            with self.subTest(field=field):
                blobs = dict(self.blobs)
                candidate = decoded(blobs, "candidate.json")
                candidate[field] = value
                restamp(blobs, "candidate.json", candidate)
                with self.assertRaises(EvidenceError):
                    replay.replay_native_bundle(blobs)
        candidate = decoded(self.blobs, "candidate.json")
        candidate["runtime"]["numpy"] = "unreviewed-runtime"
        restamp(self.blobs, "candidate.json", candidate)
        with self.assertRaises(EvidenceError):
            replay.replay_native_bundle(self.blobs)

    def test_exact_receipt_fields_flags_counts_and_limitations(self):
        mutations = (
            lambda value: value.update(unexpected="ignored"),
            lambda value: value.update(schema_version="wrong"),
            lambda value: value.update(fixture_only=1),
            lambda value: value.update(duplicate_groups=True),
            lambda value: value.update(conflicting_label_groups=99),
            lambda value: value.update(elapsed_seconds=-1),
            lambda value: value.update(reload_max_absolute_error=True),
            lambda value: value.update(limitations=[]),
            lambda value: value["controls"].update(passed=1),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                blobs = dict(self.blobs)
                receipt = decoded(blobs, "result.json")
                mutate(receipt)
                blobs["result.json"] = encoded(receipt)
                with self.assertRaises(EvidenceError):
                    replay.replay_native_bundle(blobs)

    def test_missing_extra_mutable_or_unbounded_blobs_fail(self):
        cases = []
        missing = dict(self.blobs); missing.pop("plan.json"); cases.append(missing)
        extra = dict(self.blobs); extra["../extra.json"] = b"{}"; cases.append(extra)
        mutable = dict(self.blobs); mutable["plan.json"] = bytearray(mutable["plan.json"]); cases.append(mutable)
        oversized = dict(self.blobs); oversized["candidate.json"] = b"x" * (replay.MAX_CANDIDATE_BYTES + 1); cases.append(oversized)
        for blobs in cases:
            with self.assertRaises(EvidenceError):
                replay.artifact_manifest(blobs)
            with self.assertRaises(EvidenceError):
                replay.replay_native_bundle(blobs)
        with mock.patch.object(replay, "MAX_BUNDLE_BYTES", sum(map(len, self.blobs.values())) - 1):
            with self.assertRaises(EvidenceError):
                replay.artifact_manifest(self.blobs)

    def test_duplicate_nonfinite_huge_or_nested_json_errors_are_generic(self):
        payloads = (b'{"status":"completed",' + self.blobs["result.json"].lstrip()[1:],
                    b'{"number":NaN}', b'{"number":1e999}', b'{"number":' + b"9" * 5000 + b'}',
                    b"[" * 2000 + b"0" + b"]" * 2000)
        for content in payloads:
            with self.subTest(prefix=content[:20]):
                blobs = dict(self.blobs); blobs["result.json"] = content
                with self.assertRaisesRegex(EvidenceError, "^Native evidence bundle rejected$"):
                    replay.replay_native_bundle(blobs)

    def test_snapshot_opens_each_artifact_once(self):
        self.copy_run()
        opened = []
        original = replay.os.open
        def capture(path, *args, **kwargs):
            opened.append(Path(path).name)
            return original(path, *args, **kwargs)
        with mock.patch.object(replay.os, "open", capture):
            blobs = replay.snapshot_native_bundle(self.output)
        self.assertEqual(sorted(opened), sorted(NATIVE_ARTIFACT_NAMES))
        self.assertEqual(blobs, self.blobs)

    def test_oversized_directory_stops_enumerating_at_nine_entries(self):
        observed = []
        def entries():
            for index in range(9):
                observed.append(index)
                yield Path(f"unexpected-{index}.json")
            raise AssertionError("Directory enumeration exceeded its bound")
        directory = mock.Mock()
        directory.iterdir.return_value = entries()
        with self.assertRaises(EvidenceError):
            replay._roster(directory)
        self.assertEqual(observed, list(range(9)))

    def test_snapshot_extra_file_subdirectory_missing_file_and_size_fail(self):
        self.copy_run()
        extra = self.output / "extra.json"
        extra.write_bytes(b"{}")
        with self.assertRaises(EvidenceError):
            replay.snapshot_native_bundle(self.output)
        extra.unlink()
        extra.mkdir()
        with self.assertRaises(EvidenceError):
            replay.snapshot_native_bundle(self.output)
        extra.rmdir()
        candidate = self.output / "candidate.json"
        candidate.unlink()
        with self.assertRaises(EvidenceError):
            replay.snapshot_native_bundle(self.output)
        candidate.write_bytes(b"x" * (replay.MAX_CANDIDATE_BYTES + 1))
        with self.assertRaises(EvidenceError):
            replay.snapshot_native_bundle(self.output)

    def test_snapshot_hardlink_substitution_fails(self):
        self.copy_run()
        candidate = self.output / "candidate.json"
        outside = Path(self.temp.name) / "original.json"
        candidate.rename(outside)
        os.link(outside, candidate)
        with self.assertRaises(EvidenceError):
            replay.snapshot_native_bundle(self.output)

    def test_snapshot_reparse_symlink_and_nonregular_metadata_fail(self):
        for mode, attributes in ((stat.S_IFREG, 0x400), (stat.S_IFLNK, 0), (stat.S_IFDIR, 0)):
            with self.subTest(mode=mode):
                info = SimpleNamespace(st_mode=mode, st_file_attributes=attributes, st_nlink=1)
                with self.assertRaises(EvidenceError):
                    replay._file_stamp(info)

    def test_snapshot_roster_mutation_during_capture_fails(self):
        self.copy_run()
        original = replay._roster
        calls = 0
        def changed(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.output / "new.json").write_bytes(b"{}")
            return original(path)
        with mock.patch.object(replay, "_roster", changed):
            with self.assertRaises(EvidenceError):
                replay.snapshot_native_bundle(self.output)

    def test_snapshot_same_handle_content_change_fails(self):
        self.copy_run()
        original = replay.os.fstat
        calls = 0
        def changed(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                # candidate.json is alphabetically first; preserve the pathname
                # while changing the open file's contents and size.
                with (self.output / "candidate.json").open("ab") as stream:
                    stream.write(b" ")
            return original(descriptor)
        with mock.patch.object(replay.os, "fstat", changed):
            with self.assertRaises(EvidenceError):
                replay.snapshot_native_bundle(self.output)

    def test_snapshot_root_traversal_and_unc_are_rejected(self):
        for path in (self.root / "child" / "..", "//server/share/native-run"):
            with self.subTest(path=str(path)):
                with self.assertRaises(EvidenceError):
                    replay.snapshot_native_bundle(path)


if __name__ == "__main__":
    unittest.main()
