"""Fixed public workloads retain exact counts and current guards under measurement."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_capacity import benchmarks as b
from model_release_assurance.production_capacity import contracts as c
from model_release_assurance.production_jobs.executor import FixtureProcessRunner
from model_release_assurance.production_trust.signer import FixtureTokenIssuer


class CapacityBenchmarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-capacity-bench-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def projection(self):
        return bytes(range(64)) * 8

    def write(self, name="public.bin"):
        path = self.root / name
        result = b._write_file(path, self.projection(), b.IO_SIZES[0])
        return path, result

    def test_default_production_and_unknown_profile_refuse_before_output(self):
        for function in (b.benchmark_public_io, b.benchmark_fixture_jobs):
            for profile in ("agency_private_cloud", "unknown", None, True):
                with self.subTest(function=function.__name__, profile=profile), self.assertRaises(c.CapacityError):
                    function(self.root / "no-output", profile=profile)
                self.assertFalse((self.root / "no-output").exists())

    def test_actual_wine_io_sizes_streaming_hashes_and_measurement_scopes(self):
        result = b.benchmark_public_io(self.root / "io", profile="local_public_fixture")
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["summary"]["source_unique_rows"], 178)
        self.assertEqual(result["summary"]["projection_bytes"], 19936)
        self.assertEqual(result["summary"]["requested_bytes"], sum(b.IO_SIZES))
        self.assertEqual(len(result["rows"]), 3)
        for row, size in zip(result["rows"], b.IO_SIZES):
            self.assertEqual(row["requested_bytes"], size)
            self.assertEqual(row["bytes_scanned"], size)
            self.assertEqual(row["bytes_written"], size)
            self.assertEqual(row["chunks_scanned"], size // b.CHUNK_BYTES)
            for field in ("scan_ns", "write_fsync_ns", "scan_bytes_per_second", "write_bytes_per_second"):
                self.assertGreater(row[field], 0)
            memory = row["parent_peak_rss"]
            self.assertGreater(memory["bytes"], 0)
            self.assertFalse(memory["includes_children"])
            self.assertFalse(memory["enforced_memory_limit"])
        self.assertFalse(result["measurement"]["cold_cache_tested"])
        self.assertFalse(result["measurement"]["training_performed"])
        self.assertEqual(result["target_status"], "not_agency_qualified")
        self.assertEqual({key: result[key] for key in c.FLAGS}, dict(c.FLAGS))
        c.canonical_bytes(result)

    def test_actual_twelve_signed_jobs_keep_current_guards_and_no_credentials(self):
        original_issue, tokens = FixtureTokenIssuer.issue, []
        def record(issuer, *args, **kwargs):
            token = original_issue(issuer, *args, **kwargs)
            tokens.append(token)
            return token
        source_paths = [Path(b.__file__).parents[1] / group / name for group, name in
            (("production_jobs", "executor.py"), ("production_jobs", "service.py"), ("production_registration", "profiles.py"))]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths]
        with mock.patch.object(FixtureTokenIssuer, "issue", record):
            result = b.benchmark_fixture_jobs(self.root / "jobs", profile="local_public_fixture")
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["summary"], {"jobs_requested": 12, "jobs_succeeded": 12,
            "jobs_failed": 0, "jobs_unobserved": 0, "concurrency_rows": 3})
        self.assertEqual([row["requested_concurrency"] for row in result["rows"]], [1, 2, 4])
        for row in result["rows"]:
            self.assertEqual(row["succeeded"], 4)
            self.assertEqual(row["failed"], 0)
            self.assertEqual(row["jobs_submitted"], 4)
            self.assertEqual(row["active_runner_calls_after"], 0)
            self.assertGreaterEqual(row["peak_concurrent_runner_calls"], 1)
            self.assertLessEqual(row["peak_concurrent_runner_calls"], row["requested_concurrency"])
            self.assertEqual(row["latency_ns"]["sample_count"], 4)
            self.assertEqual(row["latency_ns"]["percentile_method"], "nearest_rank")
            self.assertFalse(row["latency_ns"]["population_inference"])
            self.assertTrue(all(sample["cleanup_confirmed"] for sample in row["runner_samples"]))
            self.assertEqual(len({sample["attempt_id"] for sample in row["runner_samples"]}), 4)
            self.assertTrue(all(value == 4 for value in row["ledger"].values()))
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths])
        self.assertTrue(tokens)
        raw_result = c.canonical_bytes(result)
        for path in (self.root / "jobs").rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                self.assertNotIn(b"PRIVATE KEY", content)
                for token in tokens:
                    self.assertNotIn(token.encode(), content)
        for token in tokens:
            self.assertNotIn(token.encode(), raw_result)

    def test_overwrite_and_traversal_are_refused(self):
        (self.root / "exists").mkdir()
        (self.root / "exists/marker").write_bytes(b"keep")
        for function in (b.benchmark_public_io, b.benchmark_fixture_jobs):
            for path in (self.root / "exists", self.root / ".." / "outside"):
                with self.subTest(function=function.__name__, path=path), self.assertRaises(c.CapacityError):
                    function(path, profile="local_public_fixture")
        self.assertEqual((self.root / "exists/marker").read_bytes(), b"keep")

    def test_scan_rejects_changed_bytes_wrong_digest_size_and_oversize_before_read(self):
        path, written = self.write()
        params = dict(expected_bytes=b.IO_SIZES[0], projection=self.projection(), expected_sha256=written["sha256"])
        for changes in ({"expected_sha256": "0" * 64}, {"expected_bytes": b.IO_SIZES[0] - 1},
                        {"expected_bytes": b.MAX_FILE_BYTES + 1}, {"expected_bytes": True}):
            with self.subTest(changes=changes), self.assertRaises(c.CapacityError):
                b._scan_file(path, **{**params, **changes})
        with path.open("r+b") as stream:
            stream.write(b"x")
        with self.assertRaises(c.CapacityError):
            b._scan_file(path, **params)

    def test_stream_never_requests_more_than_64k_and_detects_growth(self):
        path, written = self.write()
        original, counts = b.os.fdopen, []
        class Stream:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(self, count): counts.append(count); return self.stream.read(count)
        with mock.patch.object(b.os, "fdopen", side_effect=lambda *args, **kwargs: Stream(original(*args, **kwargs))):
            b._scan_file(path, expected_bytes=b.IO_SIZES[0], projection=self.projection(), expected_sha256=written["sha256"])
        self.assertTrue(counts)
        self.assertLessEqual(max(counts), 65536)
        def growing(*args, **kwargs):
            with path.open("ab") as stream: stream.write(b"x")
            return original(*args, **kwargs)
        with mock.patch.object(b.os, "fdopen", side_effect=growing), self.assertRaises(c.CapacityError):
            b._scan_file(path, expected_bytes=b.IO_SIZES[0], projection=self.projection(), expected_sha256=written["sha256"])

    def test_hardlinks_and_reparse_files_fail_before_scan(self):
        path, written = self.write()
        os.link(path, self.root / "alias.bin")
        with self.assertRaises(c.CapacityError):
            b._scan_file(path, expected_bytes=b.IO_SIZES[0], projection=self.projection(), expected_sha256=written["sha256"])
        original = path.lstat()
        fake = mock.Mock(st_mode=original.st_mode, st_nlink=1, st_file_attributes=0x400)
        with self.assertRaises(c.CapacityError): b._stamp(fake)

    def test_known_writes_are_retained_when_later_scan_fails(self):
        with mock.patch.object(b, "_scan_file", side_effect=c.CapacityError):
            result = b.benchmark_public_io(self.root / "io", profile="local_public_fixture")
        self.assertEqual(result["status"], "failed")
        for row, size in zip(result["rows"], b.IO_SIZES):
            self.assertEqual(row["bytes_written"], size)
            self.assertGreater(row["write_fsync_ns"], 0)
            self.assertNotIn("bytes_scanned", row)

    def test_fixed_workload_bounds_and_no_overwrite(self):
        path, written = self.write()
        with self.assertRaises(FileExistsError): b._write_file(path, self.projection(), b.IO_SIZES[0])
        self.assertEqual(path.stat().st_size, written["bytes_written"])
        for count in (True, 0, 100, b.MAX_FILE_BYTES + 1):
            with self.subTest(count=count), self.assertRaises(c.CapacityError):
                b._write_file(self.root / "refused.bin", self.projection(), count)
        self.assertFalse((self.root / "refused.bin").exists())
        with self.assertRaises(c.CapacityError): b._job_row(self.root / "invalid", 8)
        self.assertFalse((self.root / "invalid").exists())

    def test_missing_os_measurement_never_becomes_zero_or_success(self):
        with mock.patch.object(b, "_rss", side_effect=c.CapacityError):
            result = b.benchmark_public_io(self.root / "io", profile="local_public_fixture")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["rows"]), 3)
        self.assertTrue(all(row["status"] == "failed" for row in result["rows"]))
        self.assertTrue(all("parent_peak_rss" not in row for row in result["rows"]))

    def fixture(self, name):
        root = self.root / name
        root.mkdir()
        return b._Fixture(root)

    def test_current_key_outage_after_real_worker_blocks_result(self):
        fixture = self.fixture("revoked")
        original = fixture.runner.runner.run
        def lose_trust(**kwargs):
            result = original(**kwargs)
            fixture.trust.set_available(False, expected_revision=fixture.trust.revision)
            return result
        with mock.patch.object(fixture.runner.runner, "run", side_effect=lose_trust):
            outcome = fixture.one(0)
        self.assertEqual(outcome["status"], "failed")
        self.assertNotIn("total", outcome)
        self.assertEqual(b._ledger(fixture)["succeeded"], 0)
        self.assertEqual(fixture.runner.samples[0]["status"], "completed")
        self.assertTrue(fixture.runner.samples[0]["cleanup_confirmed"])

    def test_real_elapsed_credential_expiry_is_not_extended(self):
        fixture = self.fixture("expired")
        original = fixture.runner.runner.run
        def expire(**kwargs):
            result = original(**kwargs)
            fixture.origin -= 121 * 1_000_000_000
            return result
        with mock.patch.object(fixture.runner.runner, "run", side_effect=expire):
            outcome = fixture.one(0)
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(b._ledger(fixture)["succeeded"], 0)
        self.assertGreaterEqual(fixture.clock(), 1121)

    def test_cleanup_failure_retains_failure_without_accepting_success(self):
        fixture = self.fixture("cleanup")
        original = fixture.runner.runner.run
        def fail_cleanup(**kwargs):
            result = original(**kwargs)
            return replace(result, status="cleanup_failed", output=None, cleanup_confirmed=False)
        with mock.patch.object(fixture.runner.runner, "run", side_effect=fail_cleanup):
            outcome = fixture.one(0)
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(b._ledger(fixture)["succeeded"], 0)
        self.assertFalse(fixture.runner.samples[0]["cleanup_confirmed"])

    def test_runner_measurement_always_releases_active_count_on_malformed_receipt(self):
        root = self.root / "runner"
        runner = b._MeasuredRunner(root)
        malformed = mock.Mock()
        malformed.to_dict.side_effect = ValueError("unavailable")
        with mock.patch.object(runner.runner, "run", return_value=malformed):
            self.assertIs(runner.run(job_id="a" * 32, attempt_id="b" * 32), malformed)
        self.assertEqual(runner.active, 0)
        self.assertEqual(len(runner.samples), 1)
        self.assertFalse(runner.samples[0]["cleanup_confirmed"])
        self.assertEqual(runner.samples[0]["measurement_error"], "runner_receipt_unavailable")

    def test_memory_measurement_failure_preserves_known_success_counts(self):
        with mock.patch.object(b, "_rss", side_effect=c.CapacityError):
            row = b._job_row(self.root / "jobs", 2)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["succeeded"], 4)
        self.assertEqual(row["failed"], 0)
        self.assertEqual(row["unobserved"], 0)
        self.assertIsNone(row["parent_peak_rss"])
        self.assertEqual(row["measurement_error"], "parent_memory_observation_unavailable")

    def test_ledger_read_failure_retains_already_measured_real_job_outcomes(self):
        with mock.patch.object(b, "_ledger", side_effect=c.CapacityError):
            row = b._job_row(self.root / "jobs", 2)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["succeeded"], 4)
        self.assertEqual(row["failed"], 0)
        self.assertEqual(row["unobserved"], 0)
        self.assertEqual(row["known_job_submission_count"], 4)
        self.assertIsNone(row["jobs_submitted"])
        self.assertFalse(row["ledger_available"])
        self.assertIsNone(row["ledger"])
        self.assertEqual(row["measurement_error"], "ledger_observation_unavailable")
        self.assertEqual(row["latency_ns"]["sample_count"], 4)
        self.assertEqual(len(row["samples"]), 4)
        self.assertEqual(len(row["runner_samples"]), 4)
        self.assertTrue(all(sample["cleanup_confirmed"] for sample in row["runner_samples"]))
        self.assertGreater(row["elapsed_ns"], 0)
        self.assertGreater(row["parent_peak_rss"]["bytes"], 0)

    def test_cross_row_reused_ids_cannot_pass_matrix(self):
        def duplicated(root, concurrency):
            return {"requested_concurrency": concurrency, "status": "passed", "succeeded": 4,
                "failed": 0, "unobserved": 0, "samples": [{key: str(index) * 32
                    for key in ("job_id", "grant_id", "attempt_id")} for index in range(4)]}
        with mock.patch.object(b, "_job_row", side_effect=duplicated):
            result = b.benchmark_fixture_jobs(self.root / "jobs", profile="local_public_fixture")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["measurement"]["identities_unique_across_rows"])

    def test_unobserved_jobs_remain_distinct_from_known_failures(self):
        with mock.patch.object(b, "_job_row", side_effect=RuntimeError("private fault detail")):
            result = b.benchmark_fixture_jobs(self.root / "jobs", profile="local_public_fixture")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["summary"]["jobs_unobserved"], 12)
        self.assertEqual(result["summary"]["jobs_failed"], 0)
        self.assertEqual(result["summary"]["jobs_succeeded"], 0)
        self.assertNotIn(b"private fault detail", c.canonical_bytes(result))


if __name__ == "__main__":
    unittest.main()
