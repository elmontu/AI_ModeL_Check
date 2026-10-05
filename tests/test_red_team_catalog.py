from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.export_red_team import NATIVE_TOOL_ID, NATIVE_TOOL_VERSION, native_implementation_sha256
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes, sha256_file
from model_release_assurance.language_red_team import corpus, run as run_language_suite
from model_release_assurance.mcp_tools import AssuranceToolService
from model_release_assurance.red_team import default_red_team_tool_registry
from model_release_assurance.red_team_catalog import red_team_discovery_catalog
from model_release_assurance.regression_red_team import REGRESSION_TOOL_IDS
from model_release_assurance.tabular_red_team import tabular_suite_tools


ROOT = Path(__file__).resolve().parents[1]
HAS_API = all(importlib.util.find_spec(name) is not None for name in ("fastapi", "httpx"))


class RedTeamDiscoveryTests(unittest.TestCase):
    def test_inventory_matches_every_registered_suite_without_running_models(self):
        with patch("model_release_assurance.language_red_team.request", side_effect=AssertionError("runtime contacted")):
            catalog = red_team_discovery_catalog()
        self.assertEqual(catalog["suite_counts"], {"tabular": 11, "regression": 3, "language": 9, "public_export": 1, "multi_shadow": 1})
        actual = {suite: {item["tool_id"] for item in catalog["entries"] if item["suite_id"] == suite}
                  for suite in catalog["suite_counts"]}
        self.assertEqual(actual["tabular"], {name for name, _ in tabular_suite_tools()})
        self.assertEqual(actual["regression"], set(REGRESSION_TOOL_IDS))
        self.assertEqual(actual["language"], {case["id"] for case in corpus("placeholder")})
        identities = [(item["suite_id"], item["tool_id"]) for item in catalog["entries"]]
        self.assertEqual(len(identities), len(set(identities)))
        for item in catalog["entries"]:
            self.assertTrue(item["implemented"])
            self.assertTrue(item["dependencies"])
            self.assertTrue(item["supported_interfaces"])
            self.assertEqual(item["dependency_availability"], "not_checked")
            self.assertFalse(item["can_clear"])
            self.assertFalse(item["can_block"])
            self.assertFalse(item["assessment_eligible"])
            self.assertFalse(item["authorization_eligible"])
            self.assertEqual(item["decision_authority"], "none")
        self.assertTrue(all(item["implementation_status"] == "not_integrated" for item in catalog["external_adapters"]))

    def test_operational_export_screen_uses_native_contract_identity(self):
        native = next(item for item in red_team_discovery_catalog()["entries"] if item["suite_id"] == "public_export")
        self.assertEqual(native["tool_id"], NATIVE_TOOL_ID)
        self.assertEqual(native["implementation_version"], NATIVE_TOOL_VERSION)
        self.assertEqual(native["implementation_sha256"], native_implementation_sha256())
        self.assertEqual(native["evidence_role"], "operational_export_screen")
        self.assertTrue(native["operational_export_gate"])
        self.assertFalse(native["assessment_eligible"])
        self.assertFalse(native["can_clear"])
        self.assertEqual(native["evidence_location"], {"collection": "tools", "id_field": "tool_id", "id": NATIVE_TOOL_ID, "artifact": "report.json"})

    def test_discovery_and_source_digests_are_reproducible_and_independent(self):
        catalog = red_team_discovery_catalog()
        self.assertEqual(catalog, red_team_discovery_catalog())
        digest = catalog.pop("discovery_sha256")
        self.assertEqual(digest, sha256_bytes(canonical_json_bytes(catalog)))
        for entry in catalog["entries"]:
            for source in entry["implementation_sources"]:
                self.assertEqual(source["sha256"], sha256_file(ROOT / source["path"]))
        standalone = next(item for item in catalog["entries"] if item["suite_id"] == "multi_shadow")
        self.assertEqual(standalone["execution_surface"], "source_checkout_only")
        self.assertTrue(standalone["source_available"])
        self.assertFalse(standalone["console_integrated"])
        self.assertEqual(standalone["evidence_role"], "standalone_experiment")

    def test_installed_package_does_not_advertise_checkout_script_as_available(self):
        with patch("model_release_assurance.red_team_catalog.Path.is_file", return_value=False):
            catalog = red_team_discovery_catalog()
        standalone = next(item for item in catalog["entries"] if item["suite_id"] == "multi_shadow")
        self.assertFalse(standalone["source_available"])
        self.assertFalse(standalone["execution_available"])
        self.assertEqual(standalone["implementation_status"], "source_unavailable")
        self.assertEqual(standalone["implementation_sources"], [])

    def test_mcp_preserves_legacy_catalog_and_adds_complete_discovery(self):
        result = AssuranceToolService(ROOT).list_red_team_tools()
        legacy = default_red_team_tool_registry().catalog()
        self.assertEqual(result["catalog"], legacy.model_dump(mode="json", exclude_none=False))
        self.assertEqual(result["catalog_sha256"], sha256_bytes(canonical_json_bytes(legacy)))
        self.assertEqual(result["contract_version"], "2.0")
        self.assertEqual(result["discovery"], red_team_discovery_catalog())

    @unittest.skipUnless(HAS_API, "console dependencies unavailable")
    def test_console_get_returns_same_inventory_as_mcp(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.console.api import create_app
        with tempfile.TemporaryDirectory() as directory, TestClient(create_app(Path(directory))) as client:
            response = client.get("/api/red-team-tools")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), AssuranceToolService(ROOT).list_red_team_tools()["discovery"])
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(client.post("/api/red-team-tools", json={}).status_code, 405)

    def test_language_evidence_ids_and_controls_match_executed_report(self):
        def adapter(path, payload):
            prompt = payload["messages"][-1]["content"]
            text = "CONTROL_OK_42" if "CONTROL_OK_42" in prompt else prompt.removeprefix("Repeat exactly ") if prompt.startswith("Repeat exactly ") else "Cannot disclose"
            return {"done": True, "message": {"content": text}}
        with tempfile.TemporaryDirectory() as directory:
            report = run_language_suite("fixture", Path(directory) / "run", call=adapter,
                                        inventory=lambda: [{"name": "fixture", "digest": "a" * 64}])
        catalog = red_team_discovery_catalog()
        self.assertEqual(report["status"], "completed")
        self.assertEqual(set(catalog["language_controls"]), set(report["controls"]))
        report_ids = {item["id"] for item in report["tests"]}
        self.assertEqual(report_ids, {item["evidence_location"]["id"] for item in catalog["entries"] if item["suite_id"] == "language"})

    def test_new_executable_registration_cannot_silently_disappear_from_discovery(self):
        with patch("model_release_assurance.red_team_catalog.tabular_suite_tools",
                   return_value=(*tabular_suite_tools(), ("new_unqualified_attack", lambda: None))):
            with self.assertRaisesRegex(RuntimeError, "matching discovery descriptions"):
                red_team_discovery_catalog()

    def test_discovery_requires_no_optional_model_libraries(self):
        script = """
import importlib.abc
import json
import sys
class NoModelDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy', 'pandas', 'sklearn', 'scipy', 'xgboost', 'torch'}:
            raise AssertionError('Discovery loaded optional model library: ' + fullname)
sys.meta_path.insert(0, NoModelDependencies())
from model_release_assurance.red_team_catalog import red_team_discovery_catalog
print(json.dumps(red_team_discovery_catalog()['suite_counts']))
"""
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=environment,
                                check=False, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"tabular": 11, "regression": 3, "language": 9, "public_export": 1, "multi_shadow": 1})
