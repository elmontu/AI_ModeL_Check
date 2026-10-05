from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from model_release_assurance.export_red_team import (
    ExportRedTeamMetricThreshold, ExportRedTeamPolicy, ExportRedTeamReport,
    ExportRedTeamToolRequirement, ExportRedTeamToolResult, MAX_JSON_BYTES,
    _predict_package, evaluate_export_red_team, main, parse_policy_json,
    parse_report_json, policy_sha256, recipient_interface_sha256, report_sha256,
    run_public_tabular_demo, strict_load_policy, strict_load_report, native_implementation_sha256,
)
from model_release_assurance.integrity import canonical_json_bytes, sha256_file


class ExportRedTeamContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.requirement = ExportRedTeamToolRequirement(
            tool_id="native.membership_loss", implementation_version="1.0.0",
            implementation_sha256="b" * 64, control_protocol_sha256="c" * 64,
            thresholds=[ExportRedTeamMetricThreshold(metric="membership_auc", maximum=.6)],
        )
        self.policy = ExportRedTeamPolicy(
            artifact_sha256="a" * 64, recipient_interface="full_artifact",
            recipient_interface_sha256=recipient_interface_sha256("full_artifact"),
            dataset_sha256="d" * 64, created_at=self.now - timedelta(minutes=10),
            expires_at=self.now + timedelta(hours=1), max_report_age_seconds=300,
            tools=[self.requirement],
        )
        self.result = ExportRedTeamToolResult(
            tool_id=self.requirement.tool_id, implementation_version=self.requirement.implementation_version,
            implementation_sha256=self.requirement.implementation_sha256,
            control_protocol_sha256=self.requirement.control_protocol_sha256,
            status="completed", metrics={"membership_auc": .52},
            member_records=20, nonmember_records=20,
            positive_control_auc=1., null_control_auc=.5,
            positive_control_member_records=20, positive_control_nonmember_records=20,
            null_control_member_records=20, null_control_nonmember_records=20,
            queries_used=120, runtime_seconds=.01,
        )
        self.report = ExportRedTeamReport(
            policy_sha256=policy_sha256(self.policy), artifact_sha256=self.policy.artifact_sha256,
            recipient_interface_sha256=self.policy.recipient_interface_sha256,
            dataset_sha256=self.policy.dataset_sha256,
            started_at=self.now - timedelta(seconds=3), completed_at=self.now - timedelta(seconds=2),
            tools=[self.result],
        )

    def evaluate(self, report=None, policy=None, artifact=None):
        return evaluate_export_red_team(policy or self.policy, report or self.report,
                                        artifact_sha256=artifact or self.policy.artifact_sha256, now=self.now)

    def with_result(self, **changes):
        return self.report.model_copy(update={"tools": [self.result.model_copy(update=changes)]})

    def assertBlocked(self, report, reason):
        outcome = self.evaluate(report)
        self.assertFalse(outcome["satisfied"], outcome)
        self.assertTrue(any(reason in item for item in outcome["reasons"]), outcome)
        self.assertIs(outcome["can_clear"], False)
        self.assertIs(outcome["authorization_eligible"], False)

    def test_valid_screen_is_non_authorizing(self):
        result = self.evaluate()
        self.assertTrue(result["satisfied"], result)
        self.assertEqual(result["reasons"], [])
        self.assertIs(result["can_clear"], False)
        self.assertIs(result["authorization_eligible"], False)
        self.assertEqual(result["report_sha256"], report_sha256(self.report))
        self.assertEqual(result["policy_sha256"], policy_sha256(self.policy))

    def test_missing_report_blocks(self):
        result = evaluate_export_red_team(self.policy, None, artifact_sha256=self.policy.artifact_sha256, now=self.now)
        self.assertFalse(result["satisfied"])
        self.assertIn("report_missing", result["reasons"])
        self.assertIsNone(result["report_sha256"])

    def test_artifact_replacement_blocks(self):
        result = self.evaluate(artifact="f" * 64)
        self.assertIn("artifact_digest_mismatch", result["reasons"])
        self.assertIn("report_artifact_sha256_mismatch", result["reasons"])

    def test_report_binding_mismatches_block(self):
        for field in ("policy_sha256", "artifact_sha256", "recipient_interface_sha256", "dataset_sha256"):
            with self.subTest(field=field):
                self.assertBlocked(self.report.model_copy(update={field: "f" * 64}), f"report_{field}_mismatch")

    def test_policy_expiry_and_future_policy_block(self):
        for changes, expected in (
            ({"expires_at": self.now}, "policy_expired"),
            ({"created_at": self.now + timedelta(seconds=1)}, "policy_not_yet_valid"),
        ):
            with self.subTest(reason=expected):
                outcome = self.evaluate(policy=self.policy.model_copy(update=changes))
                self.assertIn(expected, outcome["reasons"])

    def test_stale_future_and_prefreeze_reports_block(self):
        for changes, expected in (
            ({"started_at": self.now - timedelta(seconds=400), "completed_at": self.now - timedelta(seconds=301)}, "report_stale"),
            ({"completed_at": self.now + timedelta(seconds=1)}, "report_from_future"),
            ({"started_at": self.policy.created_at - timedelta(seconds=1)}, "report_predates_policy"),
        ):
            with self.subTest(reason=expected):
                self.assertBlocked(self.report.model_copy(update=changes), expected)

    def test_missing_and_unexpected_tools_block(self):
        self.assertBlocked(self.report.model_copy(update={"tools": []}), "missing")
        unexpected = self.result.model_copy(update={"tool_id": "unknown.attack"})
        self.assertBlocked(self.report.model_copy(update={"tools": [self.result, unexpected]}), "unexpected_tools")

    def test_failed_unsupported_and_unrun_tools_block(self):
        for status in ("failed", "unsupported", "not_run"):
            with self.subTest(status=status):
                self.assertBlocked(self.with_result(status=status), status)

    def test_implementation_and_control_identity_changes_block(self):
        for field in ("implementation_sha256", "implementation_version", "control_protocol_sha256"):
            with self.subTest(field=field):
                value = "2.0.0" if field.endswith("version") else "f" * 64
                self.assertBlocked(self.with_result(**{field: value}), f"{field}_mismatch")

    def test_positive_and_null_controls_must_succeed(self):
        for field, value, reason in (
            ("positive_control_auc", None, "positive_control_failed"),
            ("positive_control_auc", .5, "positive_control_failed"),
            ("null_control_auc", None, "null_control_failed"),
            ("null_control_auc", .8, "null_control_failed"),
            ("null_control_auc", .2, "null_control_failed"),
        ):
            with self.subTest(field=field, value=value):
                self.assertBlocked(self.with_result(**{field: value}), reason)

    def test_each_sample_count_is_checked(self):
        for field in (
            "member_records", "nonmember_records", "positive_control_member_records",
            "positive_control_nonmember_records", "null_control_member_records", "null_control_nonmember_records",
        ):
            with self.subTest(field=field):
                self.assertBlocked(self.with_result(**{field: 19}), f"{field}_insufficient")

    def test_resource_usage_is_bounded_and_nonempty(self):
        for changes, reason in (
            ({"queries_used": 119}, "query_budget_invalid"),
            ({"queries_used": 2001}, "query_budget_invalid"),
            ({"runtime_seconds": 0.}, "runtime_budget_invalid"),
            ({"runtime_seconds": 61.}, "runtime_budget_invalid"),
            ({"error": "model runtime error"}, "completed_with_error"),
        ):
            with self.subTest(changes=changes):
                self.assertBlocked(self.with_result(**changes), reason)

    def test_blocking_and_inverted_membership_findings_block(self):
        for auc in (.61, .1):
            with self.subTest(auc=auc):
                self.assertBlocked(self.with_result(metrics={"membership_auc": auc}), "above_maximum")

    def test_exact_metric_set_required(self):
        for metrics in ({}, {"other": .5}, {"membership_auc": .5, "extra": .5}):
            with self.subTest(metrics=metrics):
                self.assertBlocked(self.with_result(metrics=metrics), "metric_set_mismatch")

    def test_nan_infinite_negative_and_above_one_metrics_rejected(self):
        for value in (float("nan"), float("inf"), -.1, 1.1, True, "0.5"):
            with self.subTest(value=value):
                raw = self.result.model_dump()
                raw["metrics"] = {"membership_auc": value}
                with self.assertRaises(ValidationError):
                    ExportRedTeamToolResult.model_validate(raw)

    def test_opaque_interface_digest_and_unsupported_descriptor_rejected(self):
        for changes in ({"recipient_interface_sha256": "f" * 64}, {"recipient_interface": "arbitrary-code"}):
            raw = self.policy.model_dump()
            raw.update(changes)
            with self.assertRaises(ValidationError):
                ExportRedTeamPolicy.model_validate(raw)

    def test_flags_and_unknown_fields_never_authorize(self):
        for changes in ({"passed": True}, {"severity": "safe"}, {"can_clear": True}, {"authorization_eligible": True}):
            raw = self.report.model_dump()
            raw.update(changes)
            with self.assertRaises(ValidationError):
                ExportRedTeamReport.model_validate(raw)

    def test_empty_policy_and_duplicate_ids_rejected(self):
        for tools in ([], [self.requirement, self.requirement]):
            raw = self.policy.model_dump()
            raw["tools"] = tools
            with self.assertRaises(ValidationError):
                ExportRedTeamPolicy.model_validate(raw)
        with self.assertRaises(ValidationError):
            ExportRedTeamReport.model_validate({**self.report.model_dump(), "tools": [self.result, self.result]})

    def test_empty_duplicate_and_reversed_thresholds_rejected(self):
        for data in ({"metric": "auc"}, {"metric": "auc", "minimum": .8, "maximum": .2}):
            with self.assertRaises(ValidationError):
                ExportRedTeamMetricThreshold(**data)
        threshold = ExportRedTeamMetricThreshold(metric="auc", maximum=.6)
        raw = self.requirement.model_dump()
        raw["thresholds"] = [threshold, threshold]
        with self.assertRaises(ValidationError):
            ExportRedTeamToolRequirement.model_validate(raw)

    def test_control_requirements_cannot_be_vacuous(self):
        for changes in ({"min_member_records": 0}, {"positive_control_min_auc": 0.}, {"null_control_max_auc": 1.}):
            with self.assertRaises(ValidationError):
                ExportRedTeamToolRequirement.model_validate({**self.requirement.model_dump(), **changes})

    def test_naive_and_reverse_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_export_red_team(self.policy, self.report, artifact_sha256=self.policy.artifact_sha256,
                                     now=datetime(2026, 10, 1))
        raw = self.report.model_dump()
        for changes in ({"started_at": datetime(2026, 10, 1)}, {"started_at": self.now}):
            with self.assertRaises(ValidationError):
                ExportRedTeamReport.model_validate({**raw, **changes})

    def test_duplicate_json_keys_nonfinite_and_oversized_inputs_rejected(self):
        for loader in (parse_policy_json, parse_report_json):
            for raw in ('{"x":1,"x":2}', '{"metrics":{"auc":1,"auc":0}}', '{"x":NaN}', '{"x":Infinity}', ' ' * (MAX_JSON_BYTES + 1)):
                with self.subTest(loader=loader.__name__, raw=raw[:30]):
                    with self.assertRaises(ValueError):
                        loader(raw)

    def test_deep_json_rejected_without_recursion_error(self):
        for depth in (40, 2000):
            raw = '[' * depth + '0' + ']' * depth
            with self.assertRaises(ValueError):
                parse_policy_json(raw)

    def test_native_identity_includes_statistical_scorer_dependency(self):
        with patch("model_release_assurance.export_red_team.sha256_file", side_effect=lambda path: "a" * 64):
            first = native_implementation_sha256()
        with patch("model_release_assurance.export_red_team.sha256_file", side_effect=lambda path: ("b" if path.name == "tabular_red_team.py" else "a") * 64):
            second = native_implementation_sha256()
        self.assertNotEqual(first, second)

    def test_canonical_digest_and_parse_round_trip(self):
        policy = parse_policy_json(self.policy.model_dump_json(indent=2))
        report = parse_report_json(self.report.model_dump_json(indent=2))
        self.assertEqual(policy_sha256(policy), policy_sha256(self.policy))
        self.assertEqual(report_sha256(report), report_sha256(self.report))

    def test_unvalidated_copy_and_nested_mutations_rechecked(self):
        with self.assertRaises(ValueError):
            self.evaluate(self.report.model_copy(update={"tools": [self.result, self.result]}))
        poisoned = copy.deepcopy(self.report)
        poisoned.tools[0].metrics["membership_auc"] = float("nan")
        with self.assertRaises(ValueError):
            self.evaluate(poisoned)


class PublicRedTeamPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import sklearn  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as error:
            raise unittest.SkipTest(str(error))
        cls.temp = tempfile.TemporaryDirectory(prefix="mra-red-team-test-")
        cls.output = Path(cls.temp.name) / "pilot"
        cls.receipt = run_public_tabular_demo(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_public_fixture_exact_package_reload_and_controls(self):
        self.assertLessEqual(self.receipt["reload_max_probability_error"], 1e-12)
        self.assertGreater(self.receipt["holdout_accuracy"], .8)
        self.assertEqual(self.receipt["positive_control"]["auc"], 1.)
        self.assertEqual(self.receipt["null_control"]["auc"], .5)
        self.assertEqual(self.receipt["artifact_sha256"], sha256_file(self.output / "candidate.json"))
        self.assertTrue(self.receipt["evaluation"]["satisfied"], self.receipt["evaluation"])
        self.assertIs(self.receipt["can_clear"], False)
        self.assertIs(self.receipt["authorization_eligible"], False)

    def test_reviewer_bundle_hashes_and_no_pickle_or_registry(self):
        self.assertEqual({item.name for item in self.output.iterdir()}, {
            "plan.json", "candidate.json", "policy.json", "report.json", "evaluation.json", "reviewer-receipt.json",
        })
        for filename, digest in self.receipt["files"].items():
            self.assertEqual(sha256_file(self.output / filename), digest)
        plan = json.loads((self.output / "plan.json").read_text())
        self.assertFalse(set(plan["training_indices"]) & set(plan["holdout_indices"]))
        policy = strict_load_policy(self.output / "policy.json")
        report = strict_load_report(self.output / "report.json")
        self.assertGreaterEqual(report.started_at, policy.created_at)
        self.assertEqual(policy.dataset_sha256, self.receipt["dataset_sha256"])

    def test_existing_output_is_never_overwritten(self):
        before = {item.name: item.read_bytes() for item in self.output.iterdir()}
        with self.assertRaises(FileExistsError):
            run_public_tabular_demo(self.output)
        self.assertEqual(before, {item.name: item.read_bytes() for item in self.output.iterdir()})

    def test_cli_evaluate_detects_replaced_artifact_and_invalid_input(self):
        arguments = ["evaluate", "--policy", str(self.output / "policy.json"), "--report", str(self.output / "report.json")]
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            status = main(arguments + ["--artifact", str(self.output / "candidate.json")])
        self.assertEqual(status, 0, buffer.getvalue())
        changed = Path(self.temp.name) / "replacement.json"
        changed.write_bytes((self.output / "candidate.json").read_bytes() + b" ")
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            status = main(arguments + ["--artifact", str(changed)])
        self.assertEqual(status, 1)
        self.assertIn("artifact_digest_mismatch", buffer.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(arguments + ["--artifact", str(Path(self.temp.name) / "absent")]), 2)

    def test_inert_loader_rejects_callable_and_malformed_parameters(self):
        import numpy as np
        package = json.loads((self.output / "candidate.json").read_text())
        for kind in ("extra", "nonfinite", "negative_variance", "wrong_shape"):
            bad = copy.deepcopy(package)
            if kind == "extra":
                bad["callable"] = "os.system"
            elif kind == "nonfinite":
                bad["preprocessing"]["mean"][0] = float("nan")
            elif kind == "negative_variance":
                bad["model"]["var"][0][0] = -1.
            else:
                bad["model"]["theta"] = [[0.]]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _predict_package(bad, np.zeros((1, 30)))


if __name__ == "__main__":
    unittest.main()

