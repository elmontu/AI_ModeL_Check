"""Regressions against incomplete or falsely successful pilot CLI reports."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_assessment import contracts as assessment
from model_release_assurance.production_pilot import contracts as c
from model_release_assurance.production_pilot.rehearsal import REQUIRED_CHECKS, EXPECTED_SUMMARY

ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("restricted_pilot_cli_test", ROOT / "scripts/rehearse_restricted_pilot.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def successful_result():
    declared = c.pilot_plan(candidate_sha256="a" * 64, assessment_manifest_sha256="b" * 64,
                            assessment_key_sha256="c" * 64, profile="local_public_fixture")
    evidence = {"schema": "mra-local-pilot-assessment-binding/v1", **declared["binding"],
                "implementation_sha256": "d" * 64, "profile_id": "sklearn-wine", "max_rows": 128,
                "evidence_profile": c.EVIDENCE_PROFILE, "production_blockers": list(assessment.BLOCKING_FINDING_IDS),
                **cli.HISTORICAL_FLAGS, **c.FLAGS}
    return {"schema": "mra-local-pilot-rehearsal-exercise/v1", "status": "passed",
            "checks": [{"name": name, "passed": True} for name in sorted(REQUIRED_CHECKS)],
            "errors": [], "summary": copy.deepcopy(dict(EXPECTED_SUMMARY)), "evidence": evidence,
            "pins": {"manifest_sha256": "b" * 64, "key_sha256": "c" * 64},
            "plan_sha256": c.digest(declared), "serialized_plan_restored": False, **c.FLAGS}


class PilotCliTests(unittest.TestCase):
    def run_result(self, value, *, report_bound=512 * 1024, source=None):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(cli._BASELINE, "prepare_output", return_value=out), patch.object(
                    cli, "source_snapshot", return_value=source if source is not None else {"sha256": "e" * 64}), patch.object(
                    cli, "exercise", return_value=value), patch.object(cli, "MAX_REPORT_BYTES", report_bound):
                result = cli.run_rehearsal(root=ROOT, output=".local/test", profile="local_public_fixture")
            saved = json.loads((out / "result.json").read_bytes())
            self.assertEqual(result, saved)
            return result

    def test_production_refusal_precedes_output_source_and_exercise(self):
        with patch.object(cli._BASELINE, "prepare_output") as output, patch.object(
                cli, "source_snapshot") as source, patch.object(cli, "exercise") as exercise:
            for profile in ("agency_private_cloud", None, True, [], "production"):
                with self.assertRaises(cli.ProfileRefused):
                    cli.run_rehearsal(root=object(), output=object(), profile=profile)
        output.assert_not_called()
        source.assert_not_called()
        exercise.assert_not_called()

    def test_complete_fixed_report_passes_and_returns_owned_evidence(self):
        original = successful_result()
        result = self.run_result(original)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["checks"]), len(REQUIRED_CHECKS) + 1)
        original["evidence"]["candidate_sha256"] = "f" * 64
        self.assertEqual(result["evidence"]["candidate_sha256"], "a" * 64)

    def test_missing_or_unknown_top_level_fields_cannot_pass(self):
        for key in successful_result():
            changed = successful_result()
            del changed[key]
            with self.subTest(missing=key):
                self.assertEqual(self.run_result(changed)["status"], "failed")
        changed = successful_result()
        changed["caller_accepted"] = True
        self.assertEqual(self.run_result(changed)["status"], "failed")

    def test_wrong_pins_or_unbound_plan_hash_cannot_pass(self):
        for key in ("manifest_sha256", "key_sha256"):
            changed = successful_result()
            changed["pins"][key] = "f" * 64
            with self.subTest(pin=key):
                self.assertEqual(self.run_result(changed)["status"], "failed")
        for digest in ("f" * 64, "0" * 64, True, "F" * 64):
            changed = successful_result()
            changed["plan_sha256"] = digest
            self.assertEqual(self.run_result(changed)["status"], "failed")

    def test_boolean_counts_and_altered_fixed_summary_cannot_pass(self):
        for key, expected in EXPECTED_SUMMARY.items():
            changed = successful_result()
            changed["summary"][key] = bool(expected) if type(expected) is int else 1 if type(expected) is bool else "changed"
            with self.subTest(summary=key):
                self.assertEqual(self.run_result(changed)["status"], "failed")
        changed = successful_result()
        changed["summary"]["production_blockers_open"] = 0
        self.assertEqual(self.run_result(changed)["status"], "failed")
        changed = successful_result()
        changed["evidence"]["max_rows"] = True
        self.assertEqual(self.run_result(changed)["status"], "failed")

    def test_each_flag_and_historical_flag_requires_exact_boolean(self):
        for key, expected in {**c.FLAGS, **cli.HISTORICAL_FLAGS}.items():
            for replacement in (not expected, int(expected)):
                changed = successful_result()
                changed["evidence"][key] = replacement
                with self.subTest(flag=key, replacement=replacement):
                    self.assertEqual(self.run_result(changed)["status"], "failed")
        for key, expected in c.FLAGS.items():
            changed = successful_result()
            changed[key] = not expected
            self.assertEqual(self.run_result(changed)["status"], "failed")
        for replacement in (True, 0):
            changed = successful_result()
            changed["serialized_plan_restored"] = replacement
            self.assertEqual(self.run_result(changed)["status"], "failed")

    def test_evidence_exact_fields_scope_profile_and_catalog_cannot_change(self):
        evidence = successful_result()["evidence"]
        for key in evidence:
            changed = successful_result()
            del changed["evidence"][key]
            with self.subTest(missing=key):
                self.assertEqual(self.run_result(changed)["status"], "failed")
        for key, value in (("agency_id", "another-agency"), ("project_id", "another-project"),
                           ("case_id", "case-b"), ("catalog_sha256", "f" * 64),
                           ("profile_id", "sklearn-diabetes"), ("max_rows", 129),
                           ("evidence_profile", "SACRO_qualified"), ("production_blockers", []),
                           ("candidate_sha256", "0" * 64), ("implementation_sha256", "0" * 64)):
            changed = successful_result()
            changed["evidence"][key] = value
            with self.subTest(key=key):
                self.assertEqual(self.run_result(changed)["status"], "failed")
        changed = successful_result()
        changed["evidence"]["agency_accepted"] = True
        self.assertEqual(self.run_result(changed)["status"], "failed")

    def test_missing_duplicate_unknown_numeric_and_failed_checks_cannot_pass(self):
        changes = [lambda rows: rows.pop(), lambda rows: rows.append(rows[0]),
                   lambda rows: rows[0].update(name="caller_check"),
                   lambda rows: rows[0].update(passed=1), lambda rows: rows[0].update(passed=False),
                   lambda rows: rows[0].update(caller_pass=True)]
        for mutation in changes:
            changed = successful_result()
            mutation(changed["checks"])
            self.assertEqual(self.run_result(changed)["status"], "failed")
        changed = successful_result()
        changed["errors"] = [{"code": "failed"}]
        self.assertEqual(self.run_result(changed)["status"], "failed")

    def test_safe_completed_failed_stages_and_fixed_summary_are_retained(self):
        original = successful_result()
        checks = original["checks"][:3]
        summary = {"fresh_native_runs": EXPECTED_SUMMARY["fresh_native_runs"]}
        failed = {"schema": original["schema"], "status": "failed", "checks": checks,
                  "summary": summary, "errors": [{"stage": "private-stage", "code": "private-error"}], **c.FLAGS}
        result = self.run_result(failed)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checks"][:3], checks)
        self.assertEqual(result["summary"], summary)
        self.assertNotIn("private-error", json.dumps(result))
        self.assertNotIn("private-stage", json.dumps(result))

    def test_malformed_failed_stage_metadata_is_not_retained(self):
        original = successful_result()
        failed = {"schema": original["schema"], "status": "failed", "checks": original["checks"][:1],
                  "summary": {"production_blockers_open": True}, "errors": [], **c.FLAGS}
        result = self.run_result(failed)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["summary"], {})
        self.assertEqual(result["checks"], [{"name": "source_unchanged", "passed": True}])

    def test_source_change_or_missing_final_snapshot_forces_failure(self):
        for snapshots in ([{"sha256": "a" * 64}, {"sha256": "b" * 64}],
                          [{"sha256": "a" * 64}, ValueError("private path")]):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                with patch.object(cli._BASELINE, "prepare_output", return_value=out), patch.object(
                        cli, "source_snapshot", side_effect=snapshots), patch.object(cli, "exercise", return_value=successful_result()):
                    result = cli.run_rehearsal(root=ROOT, output=".local/test", profile="local_public_fixture")
                self.assertEqual(result, json.loads((out / "result.json").read_bytes()))
                self.assertEqual(result["status"], "failed")
                self.assertTrue(any(row["stage"] == "source_stability" for row in result["errors"]))
                self.assertNotIn("private path", json.dumps(result))

    def test_oversized_and_nonfinite_report_return_same_failed_disk_object(self):
        result = self.run_result(successful_result(), report_bound=1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], [{"stage": "report", "code": "InvalidOrOversizedPilotReport"}])
        self.assertEqual(result["summary"], dict(EXPECTED_SUMMARY))
        self.assertEqual(len(result["checks"]), len(REQUIRED_CHECKS) + 1)
        result = self.run_result(successful_result(), source={"private": float("nan")})
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("source", result)

    def test_main_returns_failure_for_serialization_fallback_and_refusal_for_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(cli._BASELINE, "prepare_output", return_value=out), patch.object(
                    cli, "source_snapshot", return_value={"sha256": "e" * 64}), patch.object(
                    cli, "exercise", return_value=successful_result()), patch.object(cli, "MAX_REPORT_BYTES", 1), contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli.main(["--profile", "local_public_fixture", "--output", ".local/test"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "failed")
            self.assertEqual(json.loads((out / "result.json").read_bytes())["status"], "failed")
        with patch.object(cli._BASELINE, "prepare_output") as helper, contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(["--output", ".local/test"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "profile_refused")
        helper.assert_not_called()

    def test_every_required_pilot_source_file_is_mandatory(self):
        original = cli._SOURCE_READER._read_source
        for required in cli.SOURCE_FILES:
            def read(root, name, missing=required):
                if name == missing:
                    raise ValueError("Missing source")
                return original(root, name)
            with self.subTest(required=required), patch.object(cli._SOURCE_READER, "_read_source", side_effect=read), self.assertRaises(ValueError):
                cli.source_snapshot(ROOT)

    def test_source_inventory_cannot_exceed_fixed_bound(self):
        oversized = {"files": [{"path": "extra%d.py" % index, "sha256": "e" * 64, "size_bytes": 1}
                               for index in range(257)]}
        with patch.object(cli._HELPERS, "source_snapshot", return_value=oversized), self.assertRaises(ValueError):
            cli.source_snapshot(ROOT)


if __name__ == "__main__":
    unittest.main()
