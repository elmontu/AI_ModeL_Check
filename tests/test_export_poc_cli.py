"""Operator CLI checks on isolated synthetic histories; no deployment or study."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.export_poc import mechanism
from model_release_assurance.export_poc.cli import main
from model_release_assurance.export_poc.tools import ExportToolService, export_construction_catalog


HAS_API = all(importlib.util.find_spec(p) is not None for p in ("fastapi", "uvicorn"))


class ExportCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "history"

    def invoke(self, *tokens, expected=0, data=True):
        args = list(tokens)
        if data:
            args.extend(["--data", str(self.data)])
        stdout, stderr = io.StringIO(), io.StringIO()
        # Deterministic unit-test draws, never a seeded privacy experiment.
        with redirect_stdout(stdout), redirect_stderr(stderr), patch.object(mechanism.secrets, "randbelow", return_value=1):
            code = main(args)
        self.assertEqual(code, expected, stderr.getvalue())
        if expected == 0:
            self.assertEqual(stderr.getvalue(), "")
            return json.loads(stdout.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        return json.loads(stderr.getvalue())

    def first(self):
        self.invoke("init")
        self.invoke("prepare", "--request-id", "first", "--stage", "1", "--route", "first", "--expected-revision", "0")
        return self.invoke("commit", "--request-id", "first", "--expected-revision", "0")

    def test_dp_plan_is_nonmutating_and_distinguishes_joint_extension_and_reuse(self):
        first = self.first()
        before = self.snapshot(self.data)
        plan = self.invoke("plan", "--route", "retained-state")
        self.assertTrue(plan["ready"])
        self.assertEqual(plan["accounting_method"], "complete-history-joint-certificate")
        self.assertEqual((plan["current_history_ratio"], plan["proposed_history_ratio"]), (2, 4))
        self.assertFalse(plan["can_authorize"])
        reuse = self.invoke("plan", "--route", "reuse")
        self.assertEqual(reuse["reuse_release_id"], first["release_id"])
        self.assertEqual(reuse["proposed_history_ratio"], 2)
        self.assertFalse(reuse["model_bytes_change"])
        blocked = self.invoke("plan", "--route", "first")
        self.assertFalse(blocked["ready"])
        self.assertIsNone(blocked["proposed_history_ratio"])
        self.assertEqual(before, self.snapshot(self.data))

    @staticmethod
    def snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_full_two_stage_workflow_binds_exact_bytes_and_commit_retry(self):
        first = self.first()
        self.assertEqual(first, self.invoke("commit", "--request-id", "first", "--expected-revision", "0"))
        output = self.root / "first.json"
        result = self.invoke("download", "--release-id", first["release_id"], "--output", str(output))
        self.assertEqual(result["artifact_sha256"], first["artifact_sha256"])
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), first["artifact_sha256"])
        retry = self.root / "first-copy.json"
        self.invoke("download", "--release-id", first["release_id"], "--output", str(retry))
        self.assertEqual(retry.read_bytes(), output.read_bytes())
        self.invoke("prepare", "--request-id", "second", "--stage", "2", "--route", "retained-state", "--expected-revision", "1")
        second = self.invoke("commit", "--request-id", "second", "--expected-revision", "1")
        self.assertEqual(second["parent_artifact_sha256"], first["artifact_sha256"])
        self.assertEqual(second["history_ratio"], 4)
        report = self.invoke("evaluate", "--release-id", second["release_id"])
        self.assertIn("synthetic", report["scope"])
        self.assertEqual(report["target"], "period2")

    def test_prepare_retry_does_not_draw_again_or_expose_candidate_bytes(self):
        self.invoke("init")
        args = ("prepare", "--request-id", "first", "--stage", "1", "--route", "first", "--expected-revision", "0")
        first = self.invoke(*args)
        with patch.object(mechanism, "first_release", side_effect=AssertionError("retry resampled")):
            self.assertEqual(self.invoke(*args), first)
        self.assertNotIn("artifact_sha256", first)
        result = self.invoke("download", "--release-id", "first", "--output", str(self.root / "bad.json"), expected=2)
        self.assertEqual(result["code"], "not_committed")
        self.assertFalse((self.root / "bad.json").exists())

    def test_download_refuses_to_overwrite_existing_evidence(self):
        first = self.first()
        output = self.root / "existing.json"
        output.write_bytes(b"historical evidence")
        self.invoke("download", "--release-id", first["release_id"], "--output", str(output), expected=2)
        self.assertEqual(output.read_bytes(), b"historical evidence")
        self.assertEqual(self.invoke("status")["history_ratio"], 2)

    def test_revoke_denies_future_download_and_preserves_prior_cost(self):
        first = self.first()
        revoked = self.invoke("revoke", "--release-id", first["release_id"])
        self.assertTrue(revoked["disclosure_retained"])
        self.assertFalse(revoked["recall_of_downloaded_copies"])
        result = self.invoke("download", "--release-id", first["release_id"], "--output", str(self.root / "revoked.json"), expected=2)
        self.assertEqual(result["code"], "revoked")
        self.assertFalse((self.root / "revoked.json").exists())
        status = self.invoke("status")
        self.assertEqual(status["history_ratio"], 2)
        self.assertEqual(len(status["releases"]), 1)
        self.assertTrue(status["releases"][0]["revoked"])

    def test_status_and_verify_are_source_read_only_and_init_cannot_reset(self):
        self.first()
        before = self.snapshot(self.data)
        self.assertEqual(self.invoke("status")["revision"], 1)
        verified = self.invoke("verify-history")
        self.assertTrue(verified["valid"])
        self.assertTrue(verified["snapshot_only"])
        self.assertFalse(verified["can_authorize"])
        self.invoke("init", expected=2)
        self.assertEqual(self.snapshot(self.data), before)

    def test_existing_history_commands_never_initialize_missing_database(self):
        commands = [
            ("status",), ("verify-history",),
            ("prepare", "--request-id", "first", "--stage", "1", "--route", "first", "--expected-revision", "0"),
            ("commit", "--request-id", "first", "--expected-revision", "0"),
            ("download", "--release-id", "missing", "--output", str(self.root / "no.json")),
            ("revoke", "--release-id", "missing"),
        ]
        for command in commands:
            with self.subTest(command=command[0]):
                error = self.invoke(*command, expected=2)
                self.assertEqual(error["code"], "not_initialized")
                self.assertFalse(self.data.exists())
        self.assertEqual(self.snapshot(self.root), {})

    def test_catalog_and_inspector_share_non_attesting_contract(self):
        self.assertEqual(self.invoke("catalog", data=False), export_construction_catalog())
        first = self.first()
        output = self.root / "model.json"
        self.invoke("download", "--release-id", first["release_id"], "--output", str(output))
        expected = ExportToolService(self.root).inspect_export_bundle(output.read_bytes().decode("utf-8"))
        inspected = self.invoke("inspect-bundle", "--input", str(output), data=False)
        self.assertEqual(inspected, expected)
        self.assertEqual(inspected["artifact_sha256"], first["artifact_sha256"])
        self.assertFalse(inspected["producer_authenticated"])
        self.assertFalse(inspected["privacy_attested"])
        self.assertFalse(inspected["can_authorize"])
        output.write_bytes(b"x" * 16385)
        self.invoke("inspect-bundle", "--input", str(output), data=False, expected=2)

    def test_main_mra_command_forwards_export_arguments_and_return_code(self):
        from model_release_assurance.cli import main as mra_main
        with patch("model_release_assurance.export_poc.cli.main", return_value=7) as forwarded:
            self.assertEqual(mra_main(["export", "catalog"]), 7)
        forwarded.assert_called_once_with(["catalog"])

    def test_explicit_service_roots_must_exist_before_any_store_is_opened(self):
        for flag in ("--repository", "--temporal-run", "--temporal-operator"):
            with self.subTest(flag=flag), patch("model_release_assurance.export_poc.cli.ExportStore") as store:
                error = self.invoke("serve", flag, str(self.root / "missing"), expected=2)
                self.assertIn(flag, error["detail"])
                self.assertIn("No registry was initialized", error["detail"])
                store.assert_not_called()
                self.assertFalse(self.data.exists())
                self.assertFalse((self.root / "missing").exists())

    def test_partial_temporal_roots_fail_without_creating_missing_files(self):
        for flag, present, missing in (
            ("--temporal-run", "registration.json", "results.json"),
            ("--temporal-operator", "workflow.json", "assurance.sqlite3"),
        ):
            with self.subTest(flag=flag):
                root = self.root / flag.removeprefix("--")
                root.mkdir()
                (root / present).write_text("{}", encoding="utf-8")
                before = self.snapshot(self.root)
                error = self.invoke("serve", flag, str(root), expected=2)
                self.assertIn(missing, error["detail"])
                self.assertEqual(self.snapshot(self.root), before)

    def test_repository_without_retained_study_receipts_fails_before_store_open(self):
        repository = self.root / "empty-research-workspace"
        repository.mkdir()
        before = self.snapshot(self.root)
        with patch("model_release_assurance.export_poc.cli.ExportStore") as store:
            error = self.invoke("serve", "--repository", str(repository), expected=2)
        self.assertIn("verification-v1.json", error["detail"])
        self.assertIn("--repository", error["detail"])
        self.assertEqual(self.snapshot(self.root), before)
        store.assert_not_called()

    @unittest.skipUnless(HAS_API, "HTTP service dependencies unavailable")
    def test_explicit_service_paths_are_forwarded_without_initialization(self):
        repository, study, operator = (self.root / name for name in ("repo", "run", "operator"))
        for root, files in ((repository, (
                "reproduction/acs-temporal-assurance-20260921/verification-v1.json",
                "reproduction/acs-temporal-assurance-20260921/report-v2/verification.json")),
                            (study, ("registration.json", "results.json", "completion.json")),
                            (operator, ("workflow.json", "assurance.sqlite3"))):
            root.mkdir()
            for name in files:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("fixture", encoding="utf-8")
        before = self.snapshot(self.root)
        sentinel = object()
        with patch("model_release_assurance.export_poc.api.create_app", return_value=sentinel) as create, patch("uvicorn.run") as run:
            self.assertEqual(main(["serve", "--data", str(self.data), "--repository", str(repository),
                                   "--temporal-run", str(study), "--temporal-operator", str(operator)]), 0)
        create.assert_called_once_with(self.data, repository=repository.resolve(),
                                       temporal_run=study.resolve(), temporal_operator=operator.resolve())
        run.assert_called_once_with(sentinel, host="127.0.0.1", port=8767, access_log=False)
        self.assertEqual(self.snapshot(self.root), before)

    @unittest.skipUnless(HAS_API, "HTTP service dependencies unavailable")
    def test_missing_historical_defaults_warn_without_creating_a_temporal_registry(self):
        missing = self.root / "unavailable-default"
        stderr = io.StringIO()
        with patch("model_release_assurance.temporal_assurance.web.DEFAULT_ROOT", missing), \
                patch("model_release_assurance.export_poc.api.create_app"), patch("uvicorn.run"), \
                redirect_stderr(stderr):
            self.assertEqual(main(["serve", "--data", str(self.data)]), 0)
        self.assertIn("--temporal-run EXISTING_DIRECTORY", stderr.getvalue())
        self.assertIn("--temporal-operator EXISTING_DIRECTORY", stderr.getvalue())
        self.assertIn("no temporal registry is initialized", stderr.getvalue())
        self.assertFalse(missing.exists())

    @unittest.skipUnless(HAS_API, "HTTP service dependencies unavailable")
    def test_legacy_launcher_uses_loopback_without_starting_a_server(self):
        sentinel = object()
        with patch("model_release_assurance.export_poc.api.create_app", return_value=sentinel) as create, patch("uvicorn.run") as run:
            self.assertEqual(main(["--data", str(self.data), "--port", "9876"]), 0)
        create.assert_called_once_with(self.data)
        run.assert_called_once_with(sentinel, host="127.0.0.1", port=9876, access_log=False)
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
