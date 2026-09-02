from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from model_release_assurance.decision import decision_game_sha256
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import AnalyzerError
from model_release_assurance.integrity import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from model_release_assurance.models import (
    AssessmentRequest,
    AttackBatteryConfiguration,
    AttackBatteryWorkerOutput,
    AttackCatalog,
    EvidenceClass,
    PolicyBundle,
    PopulationScope,
    ReleaseContract,
    ThreatContract,
    Verdict,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _load_request() -> dict:
    return json.loads((EXAMPLES / "request.json").read_text(encoding="utf-8"))


def _battery(raw: dict) -> dict:
    return next(
        value
        for value in raw["analyzer_inputs"]
        if value["analyzer"] == "attack_battery"
    )


def _model_sha256(model) -> str:
    return sha256_bytes(canonical_json_bytes(model))


def _rehash_worker_output(battery: dict) -> None:
    output = AttackBatteryWorkerOutput.model_validate(battery["worker_output"])
    battery["worker_output_sha256"] = _model_sha256(output)


def _rehash_configuration(battery: dict) -> None:
    configuration = AttackBatteryConfiguration.model_validate(battery["configuration"])
    configuration_sha256 = _model_sha256(configuration)
    battery["configuration_sha256"] = configuration_sha256
    battery["worker_output"]["configuration_sha256"] = configuration_sha256
    battery["worker_output"]["worker"]["configuration_sha256"] = configuration_sha256
    profile = battery["worker_output"]["worker_runtime_identity"]["algorithm_profile"]
    profile["configuration_sha256"] = configuration_sha256
    battery["worker_output"]["worker_runtime_identity"][
        "algorithm_profile_sha256"
    ] = sha256_bytes(canonical_json_bytes(profile))
    _rehash_worker_output(battery)


def _rehash_catalog_and_configuration(battery: dict) -> None:
    catalog = AttackCatalog.model_validate(battery["catalog"])
    catalog_sha256 = _model_sha256(catalog)
    battery["catalog_sha256"] = catalog_sha256
    battery["configuration"]["catalog_sha256"] = catalog_sha256
    battery["worker_output"]["catalog_sha256"] = catalog_sha256
    profile = battery["worker_output"]["worker_runtime_identity"]["algorithm_profile"]
    profile["catalog_sha256"] = catalog_sha256
    _rehash_configuration(battery)


def _membership_decision(report):
    return next(
        decision
        for decision in report.decisions
        if decision.threat_id == "membership-person"
    )


class AttackBatteryRegressionTests(unittest.TestCase):
    def _materialize_request(self, raw: dict, example_dir: Path) -> AssessmentRequest:
        """Write every exact analyzer payload expected by provenance replay."""

        parsed_request = AssessmentRequest.model_validate(raw)
        for claimed, parsed in zip(
            raw["analyzer_inputs"],
            parsed_request.analyzer_inputs,
            strict=True,
        ):
            source = example_dir / claimed["provenance"]["source_path"]
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                json.dumps(
                    parsed.model_dump(mode="json", exclude={"provenance"}),
                    indent=2,
                    ensure_ascii=True,
                )
                + "\n",
                encoding="utf-8",
            )
            claimed["provenance"]["source_sha256"] = sha256_file(source)
        return AssessmentRequest.model_validate(raw)

    def _assess(self, raw: dict):
        with tempfile.TemporaryDirectory() as temporary:
            example_dir = Path(temporary) / "examples"
            shutil.copytree(EXAMPLES, example_dir)
            request = self._materialize_request(raw, example_dir)
            return AssuranceEngine().assess(request, example_dir)

    def _assess_with_authorized_battery(self, raw: dict, policy_raw: dict):
        """Authorize a mutated frozen battery and rebind policy/context provenance."""

        battery = _battery(raw)
        requirement = policy_raw["attack_battery_requirements"][0]
        requirement["accepted_catalog_sha256s"] = [battery["catalog_sha256"]]
        requirement["accepted_configuration_sha256s"] = [
            battery["configuration_sha256"]
        ]

        with tempfile.TemporaryDirectory() as temporary:
            example_dir = Path(temporary) / "examples"
            shutil.copytree(EXAMPLES, example_dir)
            policy_path = example_dir / raw["policy"]["policy_path"]
            PolicyBundle.model_validate(policy_raw)
            policy_path.write_text(
                json.dumps(policy_raw, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            policy_sha256 = sha256_file(policy_path)
            raw["policy"]["policy_sha256"] = policy_sha256

            scopes = {
                scope.scope_id: scope
                for scope in (
                    PopulationScope.model_validate(value)
                    for value in raw["population_scopes"]
                )
            }
            threats = {
                threat.threat_id: threat
                for threat in (
                    ThreatContract.model_validate(value) for value in raw["threats"]
                )
            }
            games = {
                threat_id: decision_game_sha256(
                    threat,
                    scopes[threat.population_scope_id],
                )
                for threat_id, threat in threats.items()
            }
            for value in raw["analyzer_inputs"]:
                value["evidence_context"]["policy_sha256"] = policy_sha256
                value["evidence_context"]["decision_game_sha256"] = games[
                    value["threat_id"]
                ]
            battery["worker_output"]["policy_sha256"] = policy_sha256
            battery["worker_output"]["decision_game_sha256"] = games[
                battery["threat_id"]
            ]
            _rehash_worker_output(battery)

            request = self._materialize_request(raw, example_dir)
            return AssuranceEngine().assess(request, example_dir)

    def test_valid_example_battery_allows_its_policy_bound_ceiling(self) -> None:
        request = AssessmentRequest.model_validate(_load_request())
        report = AssuranceEngine().assess(request, EXAMPLES)
        decision = _membership_decision(report)

        self.assertEqual(decision.verdict, Verdict.CLEAR)
        self.assertTrue(decision.ceiling_attack_battery.satisfied)
        self.assertEqual(
            decision.ceiling_attack_battery.completed_attack_ids,
            ("membership_loss_threshold",),
        )
        battery_records = [
            record for record in report.evidence if record.analyzer == "attack_battery"
        ]
        self.assertEqual(len(battery_records), 1)
        self.assertEqual(battery_records[0].evidence_class, EvidenceClass.FLOOR)
        self.assertFalse(battery_records[0].can_clear)
        self.assertEqual(
            battery_records[0].details["attack_service_id"],
            "mra.red-team.membership-loss-threshold",
        )
        self.assertEqual(
            battery_records[0].details["attack_implementation_sha256"],
            _battery(_load_request())["catalog"]["entries"][0][
                "implementation_sha256"
            ],
        )

    def test_arbitrary_standalone_noop_attack_cannot_replace_required_battery(self) -> None:
        raw = _load_request()
        raw["analyzer_inputs"] = [
            value
            for value in raw["analyzer_inputs"]
            if value["analyzer"] != "attack_battery"
        ]
        standalone_attack = next(
            value for value in raw["analyzer_inputs"] if value["analyzer"] == "attack"
        )
        standalone_attack["attack_name"] = "arbitrary-unlisted-noop"
        request = AssessmentRequest.model_validate(raw)

        with self.assertRaisesRegex(ValueError, "membership-person/attack_battery"):
            AssuranceEngine().assess(request, EXAMPLES)

    def test_missing_planned_result_is_rejected_as_an_incomplete_contract(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["worker_output"]["results"] = []

        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_failed_and_timed_out_runs_make_ceiling_inconclusive(self) -> None:
        for status in ("failed", "timed_out"):
            with self.subTest(status=status):
                raw = _load_request()
                battery = _battery(raw)
                result = battery["worker_output"]["results"][0]
                result.update(
                    status=status,
                    successes=None,
                    trials=None,
                    false_positives=None,
                    nonmember_trials=None,
                    target_fpr=None,
                )
                _rehash_worker_output(battery)

                decision = _membership_decision(self._assess(raw))
                self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
                self.assertFalse(decision.ceiling_attack_battery.satisfied)
                self.assertTrue(any(
                    "non-successful runs" in reason
                    for reason in decision.ceiling_attack_battery.failure_reasons
                ))

    def test_failed_positive_control_makes_ceiling_inconclusive(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        control = battery["worker_output"]["positive_controls"][0]
        control.update(
            status="failed",
            successes=None,
            trials=None,
            reported_detection_lower_bound=None,
            expected_flag_observed=None,
        )
        _rehash_worker_output(battery)

        decision = _membership_decision(self._assess(raw))
        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertFalse(decision.ceiling_attack_battery.satisfied)
        self.assertTrue(any(
            "failed positive controls" in reason
            for reason in decision.ceiling_attack_battery.failure_reasons
        ))

    def test_declared_digest_substitution_is_rejected(self) -> None:
        raw = _load_request()
        _battery(raw)["worker_output_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValidationError, "worker output digest"):
            AssessmentRequest.model_validate(raw)

    def test_rehashed_configuration_substitution_is_rejected_by_policy(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["configuration"]["runs"][0]["parameters"][
            "unlisted_noop_mutation"
        ] = True
        _rehash_configuration(battery)

        with self.assertRaisesRegex(ValueError, "configuration is not accepted by policy"):
            self._assess(raw)

    def test_arbitrary_rehashed_attack_catalog_is_rejected_by_policy(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        replacement = "arbitrary_unlisted_noop"
        battery["catalog"]["entries"][0]["attack_id"] = replacement
        battery["configuration"]["runs"][0]["attack_id"] = replacement
        battery["configuration"]["positive_controls"][0]["attack_id"] = replacement
        battery["worker_output"]["results"][0]["attack_id"] = replacement
        battery["worker_output"]["positive_controls"][0]["attack_id"] = replacement
        battery["worker_output"]["worker_runtime_identity"]["algorithm_profile"][
            "attacks"
        ] = [replacement]
        _rehash_catalog_and_configuration(battery)

        with self.assertRaisesRegex(ValueError, "catalog digest is not accepted by policy"):
            self._assess(raw)

    def test_unsafe_declared_isolation_makes_ceiling_inconclusive(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        isolation = battery["worker_output"]["isolation"]
        isolation["network_access"] = "unrestricted"
        isolation["writable_audit_path"] = True
        _rehash_worker_output(battery)

        decision = _membership_decision(self._assess(raw))
        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertFalse(decision.ceiling_attack_battery.satisfied)
        self.assertIn(
            "worker network access is not disabled",
            decision.ceiling_attack_battery.failure_reasons,
        )
        self.assertIn(
            "worker can write an audit, key, or governance path",
            decision.ceiling_attack_battery.failure_reasons,
        )

    def test_self_declared_external_attestation_does_not_satisfy_policy(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        isolation = battery["worker_output"]["isolation"]
        isolation.update(
            assurance="externally_attested",
            attester_key_id="self-declared-test-key",
            statement_sha256="d" * 64,
            signature="not-a-verified-signature",
        )
        _rehash_worker_output(battery)
        request = AssessmentRequest.model_validate(raw)

        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        requirement = policy_raw["attack_battery_requirements"][0]
        requirement["minimum_isolation_assurance"] = "externally_attested"
        requirement["accepted_attester_key_ids"] = ["self-declared-test-key"]
        policy = PolicyBundle.model_validate(policy_raw)

        status = AssuranceEngine._attack_battery_status(
            request,
            policy,
            "membership-person",
        )
        self.assertFalse(status.satisfied)
        self.assertIn(
            "external isolation signature verification is unavailable in the reference core",
            status.failure_reasons,
        )

    def test_attack_battery_cannot_self_grant_clearance(self) -> None:
        for path in (
            ("catalog", "entries", 0),
            ("worker_output", "results", 0),
            ("worker_output",),
        ):
            with self.subTest(path=path):
                candidate = copy.deepcopy(_load_request())
                target = _battery(candidate)
                for segment in path:
                    target = target[segment]
                target["can_clear"] = True
                with self.assertRaises(ValidationError):
                    AssessmentRequest.model_validate(candidate)

    def test_worker_runtime_component_and_profile_are_semantically_bound(self) -> None:
        for field, value, message in (
            ("component_id", "untrusted_worker", "wrong component"),
            ("component_version", "AttackBatteryWorkerOutput/9.0", "wrong component"),
        ):
            with self.subTest(field=field):
                raw = _load_request()
                identity = _battery(raw)["worker_output"]["worker_runtime_identity"]
                identity[field] = value
                with self.assertRaisesRegex(ValidationError, message):
                    AssessmentRequest.model_validate(raw)

        raw = _load_request()
        identity = _battery(raw)["worker_output"]["worker_runtime_identity"]
        identity["algorithm_profile"]["attacks"] = ["substituted_attack"]
        identity["algorithm_profile_sha256"] = sha256_bytes(
            canonical_json_bytes(identity["algorithm_profile"])
        )
        with self.assertRaisesRegex(ValidationError, "substitutes attacks"):
            AssessmentRequest.model_validate(raw)

    def test_each_attack_run_is_bound_to_its_catalogued_tool_identity(self) -> None:
        substitutions = (
            ("service_id", "mra.red-team.substituted"),
            ("attack_version", "9.9.9"),
            ("implementation_sha256", "f" * 64),
        )
        for result_collection, message in (
            ("results", "attack result service, version, or implementation"),
            ("positive_controls", "positive-control service, version, or implementation"),
        ):
            for status in ("succeeded", "failed", "timed_out"):
                for field, value in substitutions:
                    with self.subTest(
                        result_collection=result_collection,
                        status=status,
                        field=field,
                    ):
                        raw = _load_request()
                        battery = _battery(raw)
                        result = battery["worker_output"][result_collection][0]
                        result[field] = value
                        if status != "succeeded":
                            result["status"] = status
                            for count_field in (
                                "successes",
                                "trials",
                                "false_positives",
                                "nonmember_trials",
                                "target_fpr",
                                "reported_detection_lower_bound",
                                "expected_flag_observed",
                            ):
                                if count_field in result:
                                    result[count_field] = None
                        _rehash_worker_output(battery)

                        with self.assertRaisesRegex(ValidationError, message):
                            AssessmentRequest.model_validate(raw)

    def test_engine_revalidates_models_constructed_with_validator_bypasses(self) -> None:
        request = AssessmentRequest.model_validate(_load_request())
        battery = next(
            value for value in request.analyzer_inputs if value.analyzer == "attack_battery"
        )
        result = battery.worker_output.results[0].model_copy(
            update={"implementation_sha256": "f" * 64}
        )
        output = battery.worker_output.model_copy(update={"results": (result,)})
        bypassed_battery = battery.model_copy(update={"worker_output": output})
        inputs = tuple(
            bypassed_battery if value is battery else value
            for value in request.analyzer_inputs
        )
        bypassed_request = request.model_copy(update={"analyzer_inputs": inputs})

        with self.assertRaises(ValidationError):
            AssuranceEngine().assess(bypassed_request, EXAMPLES)

    def test_catalog_validity_covers_freeze_and_execution(self) -> None:
        for field, value, message in (
            ("valid_from", "2026-08-19T00:00:00Z", "frozen outside catalog validity"),
            ("valid_until", "2026-08-18T00:03:00Z", "execution falls outside catalog validity"),
        ):
            with self.subTest(field=field):
                raw = _load_request()
                battery = _battery(raw)
                battery["catalog"][field] = value
                _rehash_catalog_and_configuration(battery)

                with self.assertRaisesRegex(ValidationError, message):
                    AssessmentRequest.model_validate(raw)

    def test_worker_execution_interval_is_bound_to_evidence_observation(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["worker_output"]["started_at"] = "2026-08-18T00:01:00Z"
        _rehash_worker_output(battery)

        with self.assertRaisesRegex(ValidationError, "observation must fall within"):
            AssessmentRequest.model_validate(raw)

    def test_worker_completion_must_not_be_future_dated(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        battery["evidence_context"]["observed_at"] = now.isoformat()
        battery["worker_output"]["started_at"] = now.isoformat()
        battery["worker_output"]["completed_at"] = (
            now + timedelta(minutes=10)
        ).isoformat()
        battery["configuration"]["resource_limits"]["timeout_seconds"] = 900
        _rehash_configuration(battery)

        with self.assertRaisesRegex(ValueError, "completion is implausibly in the future"):
            self._assess(raw)

    def test_worker_execution_cannot_predate_policy_effectiveness(self) -> None:
        raw = _load_request()
        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        policy_raw["effective_from"] = "2026-08-18T00:02:00Z"
        for value in raw["analyzer_inputs"]:
            value["evidence_context"]["observed_at"] = "2026-08-18T00:03:00Z"

        with self.assertRaisesRegex(ValueError, "execution predates the effective policy"):
            self._assess_with_authorized_battery(raw, policy_raw)

    def test_worker_execution_cannot_outlive_policy(self) -> None:
        raw = _load_request()
        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        battery = _battery(raw)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        policy_raw["expires_at"] = (now + timedelta(minutes=3)).isoformat()
        battery["evidence_context"]["observed_at"] = now.isoformat()
        battery["worker_output"]["started_at"] = now.isoformat()
        battery["worker_output"]["completed_at"] = (
            now + timedelta(minutes=4)
        ).isoformat()
        _rehash_worker_output(battery)

        with self.assertRaisesRegex(
            ValueError,
            "execution completed after policy expiry",
        ):
            self._assess_with_authorized_battery(raw, policy_raw)

    def test_worker_execution_cannot_outlive_release_contract(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        raw["release"]["expires_at"] = (now + timedelta(minutes=3)).isoformat()
        release_sha256 = _model_sha256(ReleaseContract.model_validate(raw["release"]))
        for value in raw["analyzer_inputs"]:
            value["evidence_context"]["release_contract_sha256"] = release_sha256
        battery["evidence_context"]["observed_at"] = now.isoformat()
        battery["worker_output"]["release_contract_sha256"] = release_sha256
        battery["worker_output"]["started_at"] = now.isoformat()
        battery["worker_output"]["completed_at"] = (
            now + timedelta(minutes=4)
        ).isoformat()
        _rehash_worker_output(battery)

        with self.assertRaisesRegex(
            ValueError,
            "execution completed after release-contract expiry",
        ):
            self._assess(raw)

    def test_mechanically_observable_resource_limits_are_enforced(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["worker_output"]["completed_at"] = "2026-08-18T00:05:01Z"
        _rehash_worker_output(battery)
        with self.assertRaisesRegex(ValidationError, "exceeds the frozen timeout"):
            AssessmentRequest.model_validate(raw)

        raw = _load_request()
        battery = _battery(raw)
        battery["worker_output"]["results"][0]["trials"] = 10_001
        _rehash_worker_output(battery)
        with self.assertRaisesRegex(ValidationError, "exceed the frozen record limit"):
            AssessmentRequest.model_validate(raw)

        raw = _load_request()
        battery = _battery(raw)
        battery["configuration"]["resource_limits"]["maximum_output_bytes"] = 1
        _rehash_configuration(battery)
        with self.assertRaisesRegex(ValidationError, "exceeds the frozen byte limit"):
            AssessmentRequest.model_validate(raw)

    def test_unsupported_multiplicity_methods_are_rejected(self) -> None:
        for method in ("holm", "preallocated"):
            with self.subTest(method=method):
                raw = _load_request()
                _battery(raw)["configuration"]["multiplicity_method"] = method
                with self.assertRaises(ValidationError):
                    AssessmentRequest.model_validate(raw)

    def test_heterogeneous_battery_keeps_executor_and_orchestrator_identities_distinct(
        self,
    ) -> None:
        raw = _load_request()
        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        battery = _battery(raw)

        second_entry = copy.deepcopy(battery["catalog"]["entries"][0])
        second_entry.update(
            attack_id="membership_shadow_screen",
            attack_version="2.0.0",
            service_id="mra.red-team.shadow-screen",
            implementation_sha256="e" * 64,
            evidence_role="screen_only",
        )
        battery["catalog"]["entries"].append(second_entry)

        second_control = copy.deepcopy(battery["configuration"]["positive_controls"][0])
        second_control.update(
            control_id="known-leak-shadow-control",
            attack_id="membership_shadow_screen",
        )
        battery["configuration"]["positive_controls"].append(second_control)
        second_plan = copy.deepcopy(battery["configuration"]["runs"][0])
        second_plan.update(
            run_id="membership-shadow-run-1",
            attack_id="membership_shadow_screen",
            attack_version="2.0.0",
            evidence_role="screen_only",
            positive_control_ids=["known-leak-shadow-control"],
        )
        battery["configuration"]["runs"].append(second_plan)

        second_control_result = copy.deepcopy(
            battery["worker_output"]["positive_controls"][0]
        )
        second_control_result.update(
            control_id="known-leak-shadow-control",
            attack_id="membership_shadow_screen",
            service_id="mra.red-team.shadow-screen",
            attack_version="2.0.0",
            implementation_sha256="e" * 64,
        )
        battery["worker_output"]["positive_controls"].append(second_control_result)
        second_result = copy.deepcopy(battery["worker_output"]["results"][0])
        second_result.update(
            run_id="membership-shadow-run-1",
            attack_id="membership_shadow_screen",
            service_id="mra.red-team.shadow-screen",
            attack_version="2.0.0",
            implementation_sha256="e" * 64,
        )
        battery["worker_output"]["results"].append(second_result)
        profile = battery["worker_output"]["worker_runtime_identity"]["algorithm_profile"]
        profile["attacks"].append("membership_shadow_screen")
        profile["positive_controls"].append("known-leak-shadow-control")
        _rehash_catalog_and_configuration(battery)

        report = self._assess_with_authorized_battery(raw, policy_raw)
        records = [record for record in report.evidence if record.analyzer == "attack_battery"]
        self.assertEqual(len(records), 2)
        identities = {
            record.details["attack_id"]: record.details["attack_service_id"]
            for record in records
        }
        self.assertEqual(
            identities,
            {
                "membership_loss_threshold": "mra.red-team.membership-loss-threshold",
                "membership_shadow_screen": "mra.red-team.shadow-screen",
            },
        )
        self.assertEqual(_membership_decision(report).verdict, Verdict.CLEAR)

    def test_control_lower_bound_is_recomputed_not_trusted(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["worker_output"]["positive_controls"][0][
            "reported_detection_lower_bound"
        ] = 0.99
        _rehash_worker_output(battery)

        with self.assertRaisesRegex(AnalyzerError, "failed deterministic replay"):
            self._assess(raw)

    def test_blocking_multiplicity_must_match_complete_frozen_battery(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["configuration"]["runs"][0]["comparison_family_size"] = 2
        _rehash_configuration(battery)

        with self.assertRaisesRegex(ValidationError, "derived from the complete battery"):
            AssessmentRequest.model_validate(raw)

    def test_high_valid_attack_floor_blocks_release(self) -> None:
        raw = _load_request()
        battery = _battery(raw)
        battery["worker_output"]["results"][0]["successes"] = 900
        _rehash_worker_output(battery)

        report = self._assess(raw)
        decision = _membership_decision(report)
        self.assertEqual(decision.verdict, Verdict.BLOCK)
        self.assertGreater(decision.lower_bound, decision.tolerance)
        self.assertTrue(decision.ceiling_attack_battery.satisfied)

    def test_required_screen_only_plan_cannot_enable_ceiling_clearance(self) -> None:
        raw = _load_request()
        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        battery = _battery(raw)
        battery["catalog"]["entries"][0]["evidence_role"] = "screen_only"
        battery["configuration"]["runs"][0]["evidence_role"] = "screen_only"
        _rehash_catalog_and_configuration(battery)

        report = self._assess_with_authorized_battery(raw, policy_raw)
        decision = _membership_decision(report)

        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertFalse(decision.ceiling_attack_battery.satisfied)
        self.assertTrue(any(
            "cannot produce a validated floor" in reason
            for reason in decision.ceiling_attack_battery.failure_reasons
        ))
        battery_record = next(
            record for record in report.evidence if record.analyzer == "attack_battery"
        )
        self.assertEqual(battery_record.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(battery_record.can_block)

    def test_succeeded_low_fpr_run_that_misses_operating_point_is_inconclusive(
        self,
    ) -> None:
        raw = _load_request()
        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        target_fpr = 0.001

        threat = next(
            value for value in raw["threats"] if value["threat_id"] == "membership-person"
        )
        threat["decision_metric"] = "membership_tpr_at_fpr"
        threat["metric_parameters"] = {"target_fpr": target_fpr}
        rule = next(
            value
            for value in policy_raw["rules"]
            if value["threat_id"] == "membership-person"
        )
        rule["decision_metric"] = "membership_tpr_at_fpr"
        rule["metric_parameters"] = {"target_fpr": target_fpr}

        standalone_attack = next(
            value for value in raw["analyzer_inputs"] if value["analyzer"] == "attack"
        )
        standalone_attack.update(
            metric="membership_tpr_at_fpr",
            false_positives=0,
            nonmember_trials=100,
            target_fpr=target_fpr,
        )

        battery = _battery(raw)
        battery["catalog"]["entries"][0]["supported_metrics"] = [
            "membership_tpr_at_fpr"
        ]
        plan = battery["configuration"]["runs"][0]
        plan["metric"] = "membership_tpr_at_fpr"
        plan["target_fpr"] = target_fpr
        result = battery["worker_output"]["results"][0]
        result.update(
            metric="membership_tpr_at_fpr",
            false_positives=0,
            nonmember_trials=100,
            target_fpr=target_fpr,
        )
        _rehash_catalog_and_configuration(battery)

        report = self._assess_with_authorized_battery(raw, policy_raw)
        decision = _membership_decision(report)

        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertFalse(decision.ceiling_attack_battery.satisfied)
        self.assertTrue(any(
            "cannot produce a validated floor" in reason
            for reason in decision.ceiling_attack_battery.failure_reasons
        ))
        battery_record = next(
            record for record in report.evidence if record.analyzer == "attack_battery"
        )
        self.assertEqual(battery_record.evidence_class, EvidenceClass.SCREEN)
        self.assertFalse(battery_record.details["operating_point_attained"])
        self.assertGreater(
            battery_record.details["one_sided_fpr_upper"],
            target_fpr,
        )


if __name__ == "__main__":
    unittest.main()
