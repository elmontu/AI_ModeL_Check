"""Diagnostic boundaries and inert MCP registration; no SDK transport claim."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from model_release_assurance.export_poc import mechanism
from model_release_assurance.export_poc.store import ExportDenied, ExportStore
from model_release_assurance.export_poc.tools import ExportToolService, export_construction_catalog
from model_release_assurance.mcp_server import create_server
from model_release_assurance.mcp_tools import AssuranceToolService


ROOT = Path(__file__).resolve().parents[1]


class ExportToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.service = ExportToolService(self.root)

    @staticmethod
    def artifact():
        with patch.object(mechanism.secrets, "randbelow", return_value=0):
            return mechanism.first_release()[1]

    @staticmethod
    def source_snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_catalog_is_inert_shared_and_calibrated(self):
        with patch.object(mechanism, "first_release") as first, patch.object(mechanism, "next_release") as second:
            catalog = self.service.list_export_constructions()
            self.assertEqual(catalog, export_construction_catalog())
            first.assert_not_called()
            second.assert_not_called()
        self.assertEqual({r["route"] for r in catalog["second_stage_routes"]}, set(mechanism.ROUTES))
        self.assertEqual(catalog["history"]["maximum_committed_stages"], 2)
        self.assertEqual(catalog["history"]["complete_history_ratio"], 4)
        self.assertTrue(catalog["history"]["second_stage_branches_are_alternatives"])
        self.assertFalse(catalog["history"]["new_directory_resets_citizen_exposure"])
        self.assertFalse(catalog["agency_deployed"])
        self.assertFalse(catalog["external_data_supported"])
        self.assertFalse(catalog["can_authorize"])
        self.assertEqual(catalog["mechanism_source_sha256"],
                         hashlib.sha256(Path(mechanism.__file__).read_bytes()).hexdigest())
        catalog["history"]["complete_history_ratio"] = 1
        self.assertEqual(self.service.list_export_constructions()["history"]["complete_history_ratio"], 4)

    def test_inspection_binds_supplied_bytes_without_normalization(self):
        artifact = self.artifact()
        result = self.service.inspect_export_bundle(artifact.decode("utf-8"))
        self.assertEqual(result["artifact_sha256"], hashlib.sha256(artifact).hexdigest())
        self.assertEqual(result["bytes"], len(artifact))
        self.assertFalse(result["can_authorize"])
        self.assertFalse(result["producer_authenticated"])
        self.assertFalse(result["privacy_attested"])
        different = json.dumps(json.loads(artifact), indent=2)
        again = self.service.inspect_export_bundle(different)
        self.assertEqual(again["declared_guarantee"], result["declared_guarantee"])
        self.assertNotEqual(again["artifact_sha256"], result["artifact_sha256"])

    def test_inspection_rejects_private_fields_and_ambiguous_json(self):
        value = json.loads(self.artifact())
        value["private_state"] = {"X": [0, 1]}
        for supplied in (json.dumps(value), '{"schema":"one","schema":"two"}',
                         "x" * 16385, "\ud800", {}, b"{}", "NaN"):
            with self.subTest(type=type(supplied).__name__):
                with self.assertRaises(ValueError):
                    self.service.inspect_export_bundle(supplied)

    def test_schema_valid_forgery_is_explicitly_not_attested(self):
        value = json.loads(self.artifact())
        value["model"]["probabilities"] = {g: 0.5 for g in mechanism.PUBLIC_GROUP_IDS}
        result = self.service.inspect_export_bundle(json.dumps(value))
        self.assertTrue(result["valid"])
        self.assertFalse(result["producer_authenticated"])
        self.assertFalse(result["privacy_attested"])

    def test_existing_history_read_is_consistent_and_does_not_modify_source(self):
        history = self.root / "history"
        store = ExportStore(history)
        with patch.object(mechanism.secrets, "randbelow", return_value=0):
            store.prepare("stage-one", 1, "first", 0)
        receipt = store.commit("stage-one", 0)
        store.revoke(receipt["release_id"])
        before = self.source_snapshot(self.root)
        report = self.service.read_export_history("history")
        self.assertEqual(self.source_snapshot(self.root), before)
        self.assertTrue(report["read_only"])
        self.assertFalse(report["can_authorize"])
        self.assertTrue(report["verification"]["valid"])
        self.assertEqual(report["verification"]["history_ratio"], 2)
        self.assertEqual(report["verification"]["revision"], 2)
        raw = json.dumps(report)
        for forbidden in ('"private_state"', '"X"', '"Y"', '"A"', '"E"', '"state_digest"'):
            self.assertNotIn(forbidden, raw)

    def test_missing_and_outside_history_never_creates_database(self):
        existing = self.root / "empty"
        existing.mkdir()
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = Path(elsewhere)
            ExportStore(outside)
            for name in ("missing", "empty", str(outside), "../outside", "", None):
                with self.subTest(path=name):
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        self.service.read_export_history(name)
        self.assertEqual(self.source_snapshot(self.root), {})
        self.assertFalse((self.root / "missing").exists())

    def test_history_verification_failure_is_not_returned_as_success(self):
        history = self.root / "history"
        ExportStore(history)
        with patch.object(ExportStore, "verify_history", side_effect=ExportDenied("tampered", "bad history")):
            with self.assertRaises(ExportDenied):
                self.service.read_export_history("history")

    def test_planning_is_read_only_and_reports_stage_blocks_and_actual_joint_cost(self):
        history = self.root / "history"
        store = ExportStore(history)
        before = self.source_snapshot(self.root)
        with patch.object(mechanism, "first_release", side_effect=AssertionError("planner sampled")), \
             patch.object(mechanism, "next_release", side_effect=AssertionError("planner sampled")):
            first_plan = self.service.plan_export("history", "first")
            early_extension = self.service.plan_export("history", "retained-state")
        self.assertEqual(self.source_snapshot(self.root), before)
        self.assertTrue(first_plan["ready"])
        self.assertFalse(first_plan["can_authorize"])
        self.assertEqual(first_plan["proposed_history_ratio"], 2)
        self.assertEqual(early_extension["block_reason"], "first_release_required")
        self.assertIsNone(early_extension["proposed_history_ratio"])
        with patch.object(mechanism.secrets, "randbelow", return_value=1):
            store.prepare("first", 1, "first", 0)
        receipt = store.commit("first", 0)
        before = self.source_snapshot(self.root)
        extension = self.service.plan_export("history", "retained-state")
        reuse = self.service.plan_export("history", "reuse")
        reset = self.service.plan_export("history", "first")
        self.assertEqual(self.source_snapshot(self.root), before)
        self.assertTrue(extension["ready"])
        self.assertEqual(extension["accounting_method"], "complete-history-joint-certificate")
        self.assertEqual((extension["current_history_ratio"], extension["proposed_history_ratio"]), (2, 4))
        self.assertTrue(reuse["ready"])
        self.assertEqual(reuse["reuse_release_id"], receipt["release_id"])
        self.assertEqual((reuse["current_history_ratio"], reuse["proposed_history_ratio"]), (2, 2))
        self.assertEqual(reset["block_reason"], "history_not_empty")
        store.revoke(receipt["release_id"])
        revoked = self.service.plan_export("history", "reuse")
        self.assertEqual(revoked["block_reason"], "latest_release_revoked")
        self.assertEqual(revoked["current_history_ratio"], 2)

    def test_planning_refuses_missing_or_unconfined_histories_without_creating_them(self):
        with tempfile.TemporaryDirectory() as outside:
            ExportStore(Path(outside))
            for directory in ("missing", outside):
                with self.subTest(directory=directory):
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        self.service.plan_export(directory, "first")
        self.assertEqual(self.source_snapshot(self.root), {})
        self.assertFalse((self.root / "missing").exists())

    def test_optional_sidecar_resolving_outside_history_is_rejected_before_open(self):
        history = self.root / "history"
        ExportStore(history)
        outside = self.root / "outside-sidecar"
        outside.write_bytes(b"must not be consumed")
        original_resolve = Path.resolve
        for name in ("export.sqlite3-wal", ExportStore.MARKER):
            sidecar = history / name
            if not sidecar.exists():
                sidecar.write_bytes(b"placeholder")

            def resolved(path, *args, **kwargs):
                # Emulate an escaped symlink without requiring Windows symlink
                # privileges. The trusted Path.resolve operation supplies this
                # resolved target; no source-file read may occur afterward.
                if path == sidecar:
                    return outside
                return original_resolve(path, *args, **kwargs)

            with self.subTest(sidecar=name), patch.object(Path, "resolve", resolved), patch.object(ExportStore, "open_read_only") as opened:
                with self.assertRaisesRegex(ValueError, "sidecars"):
                    self.service.read_export_history("history")
                with self.assertRaisesRegex(ValueError, "sidecars"):
                    self.service.plan_export("history", "first")
                opened.assert_not_called()


class ExportMcpRegistrationTests(unittest.TestCase):
    def test_service_and_registration_use_shared_non_authorizing_tools(self):
        class InertMCPServer:
            def __init__(self, name, instructions):
                self.name = name
                self.instructions = instructions
                self.registered = {}

            def tool(self):
                def register(function):
                    self.registered[function.__name__] = function
                    return function
                return register

        package = types.ModuleType("mcp")
        package.__path__ = []
        server_module = types.ModuleType("mcp.server")
        server_module.MCPServer = InertMCPServer
        package.server = server_module
        with patch.dict(sys.modules, {"mcp": package, "mcp.server": server_module}):
            server = create_server(ROOT)
        expected = {"list_export_constructions", "inspect_export_bundle", "read_export_history", "plan_model_export"}
        self.assertTrue(expected <= server.registered.keys())
        self.assertFalse({"prepare_export", "commit_export", "download_export", "revoke_export"}
                         & server.registered.keys())
        service = AssuranceToolService(ROOT)
        self.assertEqual(server.registered["list_export_constructions"](),
                         service.list_export_constructions())
        artifact = ExportToolTests.artifact().decode("utf-8")
        self.assertEqual(server.registered["inspect_export_bundle"](artifact),
                         service.inspect_export_bundle(artifact))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            ExportStore(Path(directory))
            self.assertEqual(server.registered["read_export_history"](directory),
                             service.read_export_history(directory))
            before = ExportToolTests.source_snapshot(Path(directory))
            self.assertEqual(server.registered["plan_model_export"](directory, "first"),
                             service.plan_model_export(directory, "first"))
            self.assertFalse(server.registered["plan_model_export"](directory, "first")["can_authorize"])
            self.assertEqual(ExportToolTests.source_snapshot(Path(directory)), before)


if __name__ == "__main__":
    unittest.main()
