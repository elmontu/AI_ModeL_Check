"""Regressions for concrete false-success and incomplete CLI evidence risks."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_assessment import contracts as c
from model_release_assurance.production_assessment.probes import _SUMMARY
from model_release_assurance.production_assessment.rehearsal import REQUIRED_CHECKS

ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("assessment_cli_test", ROOT / "scripts/rehearse_independent_assessment.py")
cli = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(cli)


def successful_result():
    flags = {**c.FLAGS, "current_authorization_checked": False,
             "probe_execution_reconstructed": False, "agency_signer_authenticated": False}
    pins = {"manifest_sha256": "a"*64, "key_sha256": "b"*64, **flags}
    packet = {"schema": "mra-local-assessment-verification/v1", "status": "historical_packet_verified",
              "manifest_sha256": "a"*64, "key_sha256": "b"*64, "file_count": 30, "total_bytes": 10000,
              "finding_catalog_sha256": c.catalog_sha256(), "implementation_sha256": "c"*64, **flags}
    return {"schema": "mra-local-assessment-exercise/v1", "status": "passed",
            "checks": [{"name": name, "passed": True} for name in sorted(REQUIRED_CHECKS)], "errors": [],
            "summary": {"probes": dict(_SUMMARY), "review": {
                "production_blocker_count": 11, "local_residual_count": 2,
                "production_blockers_open": True, "current_local_review_demonstrated": True,
                "expired_review_unusable": True, "serialized_review_restored": False,
                "agency_assessor_appointed": False}},
            "packet": packet, "pins": pins, **c.FLAGS}


class CliTests(unittest.TestCase):
    def run_result(self, value, *, report_bound=None, source=None):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(cli._BASELINE, "prepare_output", return_value=out), patch.object(
                    cli, "source_snapshot", return_value=source or {"files": [], "sha256": "d"*64}), patch.object(
                    cli, "exercise", return_value=value), patch.object(cli, "MAX_REPORT_BYTES",
                    report_bound if report_bound is not None else 512*1024):
                result = cli.run_rehearsal(root=ROOT, output=".local/test", profile="local_public_fixture")
            saved = json.loads((out / "result.json").read_bytes())
            return result, saved

    def test_production_profile_refuses_before_output_helper(self):
        with patch.object(cli._BASELINE, "prepare_output") as helper, self.assertRaises(cli.ProfileRefused):
            cli.run_rehearsal(root=object(), output=object())
        helper.assert_not_called()

    def test_missing_handoff_evidence_cannot_pass(self):
        value = successful_result(); del value["packet"]
        result, saved = self.run_result(value)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(saved["status"], "failed")

    def test_pins_must_match_verified_packet(self):
        value = successful_result(); value["pins"]["manifest_sha256"] = "e"*64
        result, _ = self.run_result(value)
        self.assertEqual(result["status"], "failed")

    def test_boolean_file_count_cannot_pass(self):
        value = successful_result(); value["packet"]["file_count"] = True
        result, _ = self.run_result(value)
        self.assertEqual(result["status"], "failed")

    def test_modified_blocker_count_cannot_pass(self):
        value = successful_result(); value["summary"]["review"]["production_blocker_count"] = 0
        result, _ = self.run_result(value)
        self.assertEqual(result["status"], "failed")

    def test_missing_probe_check_cannot_pass(self):
        value = successful_result(); value["checks"].pop()
        result, _ = self.run_result(value)
        self.assertEqual(result["status"], "failed")

    def test_non_authorizing_flag_required(self):
        value = successful_result(); value["packet"]["production_ready"] = True
        result, _ = self.run_result(value)
        self.assertEqual(result["status"], "failed")

    def test_oversized_report_returns_same_failed_result_as_disk(self):
        result, saved = self.run_result(successful_result(), report_bound=1)
        self.assertEqual(result, saved)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"stage": "report", "code": "InvalidOrOversizedAssessment"}])

    def test_nonfinite_report_returns_same_failed_result_as_disk(self):
        result, saved = self.run_result(successful_result(), source={"not_finite": float("nan")})
        self.assertEqual(result, saved)
        self.assertEqual(result["status"], "failed")

    def test_source_change_refuses_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(cli._BASELINE, "prepare_output", return_value=out), patch.object(
                    cli, "source_snapshot", side_effect=[{"sha256": "a"*64}, {"sha256": "b"*64}]), patch.object(
                    cli, "exercise", return_value=successful_result()):
                value = cli.run_rehearsal(root=ROOT, output=".local/test", profile="local_public_fixture")
            self.assertEqual(value["status"], "failed")
            self.assertTrue(any(row["stage"] == "source_stability" for row in value["errors"]))

    def test_required_assessment_module_cannot_be_omitted(self):
        reader = cli._HELPERS._HELPERS._HELPERS
        original = reader._read_source
        def read(root, name):
            if name.endswith("/production_assessment/packet.py"):
                raise ValueError("Source missing")
            return original(root, name)
        with patch.object(reader, "_read_source", side_effect=read), self.assertRaises(ValueError):
            cli.source_snapshot(ROOT)


if __name__ == "__main__":
    unittest.main()
