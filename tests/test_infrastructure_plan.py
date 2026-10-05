"""Provider-neutral preparatory design stays disabled and cannot authorize production."""
from __future__ import annotations

from copy import deepcopy
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "deploy/agency-private-cloud/blueprint.json"
SPEC = importlib.util.spec_from_file_location("infrastructure_plan_validator", ROOT / "scripts/validate_infrastructure_plan.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class InfrastructurePlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(BLUEPRINT.read_bytes())
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-infrastructure-plan-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def assert_invalid(self, plan):
        with self.assertRaises(VALIDATOR.PlanValidationError):
            VALIDATOR.validate_plan(plan)

    def test_checked_in_plan_is_valid_design_with_no_cloud_or_data_authority(self):
        plan = VALIDATOR.load_plan(BLUEPRINT)
        self.assertEqual(plan, self.plan)
        self.assertIs(VALIDATOR.validate_plan(plan), plan)
        self.assertIsNone(plan["deployment"]["provider"])
        self.assertIsNone(plan["deployment"]["runtime"])
        self.assertFalse(plan["deployment"]["cloud_deployable"])
        self.assertFalse(plan["scope"]["private_data_admission"])
        self.assertFalse(plan["scope"]["model_delivery"])
        self.assertEqual(plan["environments"]["prod"]["state"], "planned_disabled")

    def test_missing_or_resolved_provider_runtime_and_regions_are_rejected(self):
        for field in ("provider", "runtime", "primary_region", "recovery_region"):
            for action in ("remove", "resolve"):
                with self.subTest(field=field, action=action):
                    plan = deepcopy(self.plan)
                    if action == "remove":
                        del plan["deployment"][field]
                    else:
                        plan["deployment"][field] = "chosen-without-review"
                    self.assert_invalid(plan)

    def test_each_network_and_custody_control_cannot_be_weakened(self):
        for group, controls in self.plan["controls"].items():
            for name, value in controls.items():
                with self.subTest(group=group, name=name):
                    plan = deepcopy(self.plan)
                    plan["controls"][group][name] = not value if isinstance(value, bool) else "allow"
                    self.assert_invalid(plan)

    def test_cross_environment_and_within_environment_resources_cannot_be_shared(self):
        for role in VALIDATOR.RESOURCE_ROLES:
            plan = deepcopy(self.plan)
            plan["environments"]["staging"]["resources"][role] = plan["environments"]["dev"]["resources"][role]
            with self.subTest(role=role):
                self.assert_invalid(plan)
        plan = deepcopy(self.plan)
        plan["environments"]["dev"]["resources"]["data"] = plan["environments"]["dev"]["resources"]["artifact"]
        self.assert_invalid(plan)

    def test_witness_and_application_administrator_domains_must_be_separate(self):
        for name in VALIDATOR.ENVIRONMENTS:
            plan = deepcopy(self.plan)
            domains = plan["environments"][name]["administrative_domains"]
            domains["witness_admin"] = domains["application_admin"]
            with self.subTest(environment=name):
                self.assert_invalid(plan)
        plan = deepcopy(self.plan)
        plan["environments"]["prod"]["administrative_domains"]["witness_admin"] = "logical:dev:witness-admin"
        self.assert_invalid(plan)

    def test_environment_enablement_or_approval_cannot_be_claimed(self):
        for name in VALIDATOR.ENVIRONMENTS:
            for field, value in (("cloud_enabled", True), ("state", "deployed")):
                plan = deepcopy(self.plan)
                plan["environments"][name][field] = value
                with self.subTest(environment=name, field=field):
                    self.assert_invalid(plan)
        for path, field, value in (("deployment", "cloud_deployable", True), ("scope", "agency_approvals", "approved"),
                                   ("scope", "private_data_admission", True), ("scope", "model_delivery", True),
                                   ("scope", "data", "private")):
            plan = deepcopy(self.plan)
            plan[path][field] = value
            with self.subTest(path=path, field=field):
                self.assert_invalid(plan)

    def test_loopback_rehearsal_remains_public_dev_staging_only(self):
        changes = {"allowed_environments": ["dev", "staging", "prod"], "bind_address": "0.0.0.0",
                   "transport": "cloud_http", "data": "private", "private_data_admission": True, "model_delivery": True}
        for field, value in changes.items():
            plan = deepcopy(self.plan)
            plan["local_rehearsal"][field] = value
            with self.subTest(field=field):
                self.assert_invalid(plan)

    def test_resolved_endpoints_credentials_and_arbitrary_resource_paths_are_refused(self):
        for value in ("https://example.invalid/api", "10.1.2.3", "secret-token", "D:/private/data", "logical:prod:artifact"):
            plan = deepcopy(self.plan)
            plan["environments"]["dev"]["resources"]["artifact"] = value
            with self.subTest(value=value):
                self.assert_invalid(plan)
        plan = deepcopy(self.plan)
        plan["endpoint_roles"]["private_ingress"] = "https://example.invalid/"
        self.assert_invalid(plan)
        plan = deepcopy(self.plan)
        plan["deployment"]["credentials"] = "not-permitted"
        self.assert_invalid(plan)

    def test_unknown_missing_and_wrong_typed_fields_are_rejected(self):
        locations = [(), ("deployment",), ("scope",), ("environments",), ("environments", "prod"),
                     ("environments", "dev", "resources"), ("environments", "dev", "administrative_domains"),
                     ("controls",), ("controls", "network"), ("controls", "custody"), ("endpoint_roles",), ("local_rehearsal",)]
        for location in locations:
            for action in ("unknown", "missing"):
                plan = deepcopy(self.plan)
                node = plan
                for key in location:
                    node = node[key]
                if action == "unknown":
                    node["extra"] = "ignored settings must fail"
                else:
                    del node[next(iter(node))]
                with self.subTest(location=location, action=action):
                    self.assert_invalid(plan)
        for value in (0, "false", None):
            plan = deepcopy(self.plan)
            plan["scope"]["private_data_admission"] = value
            self.assert_invalid(plan)
        self.assert_invalid([])

    def test_duplicate_json_keys_are_rejected_even_when_values_match(self):
        content = BLUEPRINT.read_text(encoding="utf-8").replace('"provider": null', '"provider": null, "provider": null', 1)
        path = self.directory / "duplicate.json"
        path.write_text(content, encoding="utf-8")
        with self.assertRaisesRegex(VALIDATOR.PlanValidationError, "Duplicate JSON field"):
            VALIDATOR.load_plan(path)

    def test_nonfinite_invalid_utf8_and_excessive_json_are_rejected(self):
        path = self.directory / "invalid.json"
        original = BLUEPRINT.read_bytes()
        for value in (b"NaN", b"Infinity", b"-Infinity", b"1e999"):
            path.write_bytes(original.replace(b'"provider": null', b'"provider": ' + value, 1))
            with self.subTest(value=value), self.assertRaises(VALIDATOR.PlanValidationError):
                VALIDATOR.load_plan(path)
        for content in (b"\xff", b"{" * 1200, b" " * (VALIDATOR.MAX_PLAN_BYTES + 1)):
            path.write_bytes(content)
            with self.subTest(size=len(content)), self.assertRaises(VALIDATOR.PlanValidationError):
                VALIDATOR.load_plan(path)

    def test_oversized_integer_fails_as_validation_error_and_cli_json(self):
        path = self.directory / "oversized-integer.json"
        path.write_bytes(b'{"provider":' + b"9" * 5000 + b"}")
        with self.assertRaises(VALIDATOR.PlanValidationError):
            VALIDATOR.load_plan(path)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exit_code = VALIDATOR.main(["--plan", str(path)])
        result = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "invalid_design")
        self.assertFalse(result["cloud_deployable"])
        self.assertTrue(result["errors"])
        self.assertNotIn("Traceback", stream.getvalue())

    def test_cli_success_hashes_exact_bytes_and_always_reports_blockers_without_writes(self):
        before = BLUEPRINT.read_bytes()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exit_code = VALIDATOR.main(["--plan", str(BLUEPRINT)])
        result = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "valid_design")
        self.assertEqual(result["sha256"], hashlib.sha256(before).hexdigest())
        self.assertFalse(result["cloud_deployable"])
        self.assertTrue(result["blockers"])
        self.assertTrue(result["nonclaims"])
        self.assertEqual(BLUEPRINT.read_bytes(), before)

    def test_cli_invalid_or_missing_input_fails_with_non_deployable_json(self):
        invalid = self.directory / "invalid.json"
        invalid.write_text("{}", encoding="utf-8")
        before = set(self.directory.iterdir())
        for path in (invalid, self.directory / "absent.json"):
            stream = io.StringIO()
            with self.subTest(path=path), contextlib.redirect_stdout(stream):
                exit_code = VALIDATOR.main(["--plan", str(path)])
            result = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(result["status"], "invalid_design")
            self.assertFalse(result["cloud_deployable"])
            self.assertTrue(result["errors"])
        self.assertEqual(set(self.directory.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
