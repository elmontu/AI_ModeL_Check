from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from model_release_assurance.analyzers.base import (
    statistical_family_sha256,
    statistical_floor_design_sha256,
)
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes, sha256_file
from model_release_assurance.models import (
    AssessmentRequest,
    EvidenceClass,
    EvidenceRecord,
    Realizability,
    StatisticalFloorDesignRegistration,
    StatisticalFloorFamilyMember,
    StatisticalFloorFamilyPlan,
)
from model_release_assurance.services import default_analyzer_service_registry


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class StatisticalFloorFamilyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _example_request() -> dict:
        raw = json.loads((EXAMPLES / "request.json").read_text(encoding="utf-8"))
        raw["release"]["artifact_sha256"] = sha256_file(
            EXAMPLES / "artifacts" / "demo-tree.json"
        )
        return raw

    def _migrated_request(
        self,
        *,
        plan_members: tuple[str, ...] = ("calibrated-loss",),
        actual_members: tuple[dict[str, object], ...] | None = None,
    ) -> tuple[AssessmentRequest, str]:
        """Build a fully hash-consistent example without mutating checked-in fixtures."""

        raw = self._example_request()
        original_attack = next(
            value for value in raw["analyzer_inputs"] if value["analyzer"] == "attack"
        )
        if actual_members is None:
            actual_members = tuple({"attack_name": member} for member in plan_members)

        family_id = "membership-generic-floor-family"

        def bare_attack(member_id: str) -> dict[str, object]:
            candidate = copy.deepcopy(original_attack)
            candidate["attack_name"] = member_id
            candidate["comparison_family_size"] = len(plan_members)
            return candidate

        planned_attacks: dict[str, dict[str, object]] = {}
        planned_members: list[StatisticalFloorFamilyMember] = []
        for index, member_id in enumerate(plan_members):
            registration = StatisticalFloorDesignRegistration(
                registration_id=f"{family_id}:{member_id}",
                analyzer="attack",
                threat_id=original_attack["threat_id"],
                population_scope_id=original_attack["population_scope_id"],
                member_id=member_id,
                decision_metric=original_attack["metric"],
                registered_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
                dataset_snapshot_sha256="a" * 64,
                procedure_sha256="b" * 64,
                execution_plan_sha256="c" * 64,
                random_seed=3407 + index,
                stopping_rule="collect the predeclared fixed-size audit sample once",
                planned_primary_trials=original_attack["trials"],
                planned_control_trials=original_attack["nonmember_trials"] or 0,
                target_fpr=original_attack["target_fpr"],
            )
            registration_path = self.temp / f"registration-{index}.json"
            registration_path.write_text(
                registration.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            registration_sha256 = sha256_file(registration_path)
            candidate = bare_attack(member_id)
            candidate["preregistration_sha256"] = registration_sha256
            planned_attacks[member_id] = candidate
            planned_members.append(StatisticalFloorFamilyMember(
                member_id=member_id,
                registration_path=str(registration_path),
                registration_sha256=registration_sha256,
                input_design_sha256=statistical_floor_design_sha256(candidate),
            ))

        plan = StatisticalFloorFamilyPlan(
            family_id=family_id,
            analyzer="attack",
            threat_id=original_attack["threat_id"],
            decision_metric=original_attack["metric"],
            members=tuple(planned_members),
            familywise_confidence=0.95,
            multiplicity_method="bonferroni",
            frozen_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
            authority="unit-test assurance authority",
        )
        plan_path = self.temp / "statistical-floor-family.json"
        plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        plan_sha256 = sha256_file(plan_path)

        attacks: list[dict[str, object]] = []
        for changes in actual_members:
            member_id = str(changes["attack_name"])
            candidate = copy.deepcopy(
                planned_attacks.get(member_id, bare_attack(member_id))
            )
            candidate.setdefault("preregistration_sha256", "9" * 64)
            candidate.update(changes)
            candidate["comparison_family_size"] = changes.get(
                "comparison_family_size", len(plan_members)
            )
            if "preregistration_sha256" not in candidate["provenance"]["bound_fields"]:
                candidate["provenance"]["bound_fields"].append(
                    "preregistration_sha256"
                )
            candidate["provenance"]["configuration_path"] = str(plan_path)
            candidate["provenance"]["producer"][
                "configuration_sha256"
            ] = plan_sha256
            attacks.append(candidate)
        raw["analyzer_inputs"] = [
            value for value in raw["analyzer_inputs"] if value["analyzer"] != "attack"
        ] + attacks

        policy_raw = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        descriptors = {
            service.descriptor.input_kind: service.descriptor
            for service in default_analyzer_service_registry().services
        }
        for value in raw["analyzer_inputs"]:
            descriptor = descriptors[value["analyzer"]]
            producer = value["provenance"]["producer"]
            producer["service_id"] = descriptor.service_id
            producer["service_version"] = descriptor.service_version
            producer["implementation_sha256"] = descriptor.implementation_sha256
            requirement = next(
                item
                for item in policy_raw["analyzer_requirements"]
                if item["threat_id"] == value["threat_id"]
                and item["analyzer"] == value["analyzer"]
            )
            requirement["accepted_implementation_sha256s"] = [
                descriptor.implementation_sha256
            ]
        attack_requirement = next(
            value
            for value in policy_raw["analyzer_requirements"]
            if value["analyzer"] == "attack"
        )
        attack_requirement["accepted_configuration_sha256s"] = [plan_sha256]
        attack_requirement["required"] = True
        policy_path = self.temp / "policy.json"
        policy_path.write_text(json.dumps(policy_raw, indent=2) + "\n", encoding="utf-8")
        policy_sha256 = sha256_file(policy_path)
        raw["policy"]["policy_path"] = str(policy_path)
        raw["policy"]["policy_sha256"] = policy_sha256

        for index, value in enumerate(raw["analyzer_inputs"]):
            value["evidence_context"]["policy_sha256"] = policy_sha256
            if value["analyzer"] == "attack_battery":
                value["worker_output"]["policy_sha256"] = policy_sha256
                value["worker_output_sha256"] = sha256_bytes(
                    canonical_json_bytes(value["worker_output"])
                )
            source = self.temp / f"analyzer-{index}.json"
            source.write_text(
                json.dumps(
                    {key: item for key, item in value.items() if key != "provenance"},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            value["provenance"]["source_path"] = str(source)
            value["provenance"]["source_sha256"] = sha256_file(source)

        return AssessmentRequest.model_validate(raw), plan_sha256

    def test_plan_rejects_familywise_confidence_below_95_percent(self) -> None:
        with self.assertRaisesRegex(ValidationError, "greater than or equal to 0.95"):
            StatisticalFloorFamilyPlan(
                family_id="membership-generic-floor-family",
                analyzer="attack",
                threat_id="membership-person",
                decision_metric="equal_prior_membership_success",
                members=(StatisticalFloorFamilyMember(
                    member_id="calibrated-loss",
                    registration_path="registration.json",
                    registration_sha256="1" * 64,
                    input_design_sha256="2" * 64,
                ),),
                familywise_confidence=0.949999,
                multiplicity_method="bonferroni",
                frozen_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
                authority="unit-test assurance authority",
            )

    def test_statistical_blocking_record_requires_both_family_fields(self) -> None:
        request, _ = self._migrated_request()
        attack = next(
            value for value in request.analyzer_inputs if value.analyzer == "attack"
        )
        common = {
            **attack.evidence_context.model_dump(mode="python"),
            "evidence_id": "unbound-statistical-floor",
            "threat_id": attack.threat_id,
            "analyzer": "attack",
            "producer": attack.provenance.producer,
            "evidence_class": EvidenceClass.FLOOR,
            "coverage": "named_projection",
            "metric": attack.metric,
            "value": 0.8,
            "lower": 0.7,
            "realizability": Realizability.RECIPIENT,
            "can_clear": False,
            "can_block": True,
        }
        incomplete_metadata = (
            {},
            {"statistical_family_id": "1" * 64},
            {"familywise_confidence": 0.95},
        )
        for metadata in incomplete_metadata:
            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(ValidationError, "typed family digest"):
                    EvidenceRecord(**common, **metadata)

    def test_engine_rejects_duplicate_missing_and_extra_family_members(self) -> None:
        expected = ("calibrated-loss", "shadow-loss")
        cases = {
            "duplicate": (
                {"attack_name": "calibrated-loss"},
                {"attack_name": "calibrated-loss"},
            ),
            "missing": ({"attack_name": "calibrated-loss"},),
            "extra": (
                {"attack_name": "calibrated-loss"},
                {"attack_name": "shadow-loss"},
                {"attack_name": "gradient-loss"},
            ),
        }
        for label, actual in cases.items():
            with self.subTest(case=label):
                request, _ = self._migrated_request(
                    plan_members=expected,
                    actual_members=actual,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "does not disposition every frozen family member exactly once",
                ):
                    AssuranceEngine().assess(request, EXAMPLES)

    def test_engine_rejects_changed_family_size_and_metric(self) -> None:
        expected = ("calibrated-loss", "shadow-loss")
        cases = {
            "family-size": (
                {"attack_name": "calibrated-loss", "comparison_family_size": 1},
                {"attack_name": "shadow-loss"},
            ),
            "metric": (
                {"attack_name": "calibrated-loss", "metric": "reconstruction_success"},
                {"attack_name": "shadow-loss"},
            ),
        }
        for label, actual in cases.items():
            with self.subTest(case=label):
                request, _ = self._migrated_request(
                    plan_members=expected,
                    actual_members=actual,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "changes its frozen metric, family size, or familywise confidence",
                ):
                    AssuranceEngine().assess(request, EXAMPLES)

    def test_engine_rejects_changed_preregistered_member_design(self) -> None:
        request, _ = self._migrated_request(
            actual_members=({
                "attack_name": "calibrated-loss",
                "calibration_disjoint": False,
            },),
        )

        with self.assertRaisesRegex(
            ValueError,
            "changes its preregistered member design",
        ):
            AssuranceEngine().assess(request, EXAMPLES)

    def test_fully_migrated_typed_example_assesses_successfully(self) -> None:
        request, plan_sha256 = self._migrated_request()

        report = AssuranceEngine().assess(request, EXAMPLES)

        attack_record = next(
            record for record in report.evidence if record.analyzer == "attack"
        )
        self.assertEqual(
            attack_record.statistical_family_id,
            statistical_family_sha256(
                analyzer="attack",
                family_definition_sha256=plan_sha256,
            ),
        )
        self.assertEqual(attack_record.familywise_confidence, 0.95)


if __name__ == "__main__":
    unittest.main()
