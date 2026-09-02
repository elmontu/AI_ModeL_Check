from __future__ import annotations

from ..errors import AnalyzerError
from ..models import (
    AnalyzerInput,
    AttackBatteryInput,
    AttackPositiveControlPlan,
    AttackPositiveControlResult,
    EvidenceClass,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    ReleaseContract,
    ThreatContract,
)
from .attack import clopper_pearson_lower, clopper_pearson_upper
from .base import evidence_context_fields, evidence_producer_fields


def _positive_control_passes(
    plan: AttackPositiveControlPlan,
    result: AttackPositiveControlResult,
) -> tuple[bool, float | None]:
    if result.status != "succeeded":
        return False, None
    if plan.control_kind == "known_leak_binomial":
        if result.successes is None or result.trials is None:
            raise AnalyzerError("known-leak positive control omitted binomial counts")
        recomputed = clopper_pearson_lower(
            result.successes,
            result.trials,
            plan.confidence,
        )
        if result.reported_detection_lower_bound is None or abs(
            result.reported_detection_lower_bound - recomputed
        ) > 1e-12:
            raise AnalyzerError("positive-control lower bound failed deterministic replay")
        return (
            result.trials >= plan.minimum_trials
            and recomputed >= plan.minimum_detection_lower_bound,
            recomputed,
        )
    if result.expected_flag_observed is None:
        raise AnalyzerError("expected-flag positive control omitted its flag result")
    return result.expected_flag_observed, None


class AttackBatteryAnalyzer:
    """Translate a complete non-clearing worker battery into guarded floor records."""

    name = "attack_battery"
    can_clear = False
    can_block = True

    def supports(self, value: AnalyzerInput) -> bool:
        return isinstance(value, AttackBatteryInput)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        if not isinstance(value, AttackBatteryInput):
            raise AnalyzerError("attack-battery analyzer received an incompatible input")

        catalog = {entry.attack_id: entry for entry in value.catalog.entries}
        plans = {plan.run_id: plan for plan in value.configuration.runs}
        controls = {
            plan.control_id: plan for plan in value.configuration.positive_controls
        }
        control_results = {
            result.control_id: result for result in value.worker_output.positive_controls
        }
        replayed_controls: dict[str, tuple[bool, float | None]] = {}
        for control_id, plan in controls.items():
            replayed_controls[control_id] = _positive_control_passes(
                plan,
                control_results[control_id],
            )

        records: list[EvidenceRecord] = []
        for result in value.worker_output.results:
            plan = plans[result.run_id]
            entry = catalog[plan.attack_id]
            if release.model_family not in entry.applicable_model_families:
                raise AnalyzerError(
                    f"attack {plan.attack_id!r} is not catalogued for model family "
                    f"{release.model_family!r}"
                )
            if release.interface.protocol_type not in entry.applicable_protocol_types:
                raise AnalyzerError(
                    f"attack {plan.attack_id!r} is not catalogued for protocol "
                    f"{release.interface.protocol_type!r}"
                )
            if threat.kind not in entry.applicable_threat_kinds:
                raise AnalyzerError(
                    f"attack {plan.attack_id!r} is not catalogued for threat kind "
                    f"{threat.kind.value!r}"
                )
            if plan.metric != threat.decision_metric:
                raise AnalyzerError("attack-battery metric does not match the threat contract")

            controls_pass = all(
                replayed_controls[control_id][0]
                for control_id in plan.positive_control_ids
            )
            operating_point_attained = True
            fpr_upper = None
            bounds_per_comparison = 2 if plan.metric == "membership_tpr_at_fpr" else 1
            simultaneous_bound_count = plan.comparison_family_size * bounds_per_comparison
            per_comparison_confidence = 1.0 - (
                (1.0 - plan.confidence) / simultaneous_bound_count
            )
            if result.status == "succeeded" and plan.metric == "membership_tpr_at_fpr":
                assert result.false_positives is not None
                assert result.nonmember_trials is not None
                assert result.target_fpr is not None
                expected_fpr = threat.metric_parameters.get("target_fpr")
                if expected_fpr is None or abs(result.target_fpr - expected_fpr) > 1e-15:
                    raise AnalyzerError("attack-battery target_fpr does not match the threat")
                fpr_upper = clopper_pearson_upper(
                    result.false_positives,
                    result.nonmember_trials,
                    per_comparison_confidence,
                )
                operating_point_attained = fpr_upper <= result.target_fpr

            valid_floor = (
                result.status == "succeeded"
                and plan.evidence_role == "blocking_floor"
                and controls_pass
                and operating_point_attained
            )
            estimate = (
                result.successes / result.trials
                if result.successes is not None and result.trials is not None
                else None
            )
            lower = (
                clopper_pearson_lower(
                    result.successes,
                    result.trials,
                    per_comparison_confidence,
                )
                if valid_floor
                and result.successes is not None
                and result.trials is not None
                else None
            )
            limitations: tuple[str, ...] = ()
            if not valid_floor:
                limitations = (
                    "attack result is screen-only because the planned run failed, timed out, "
                    "lacked a passing positive control, missed its operating point, or was "
                    "catalogued as a screen",
                )
            records.append(
                EvidenceRecord(
                    **evidence_context_fields(value.evidence_context),
                    **evidence_producer_fields(value.provenance),
                    evidence_id=(
                        f"{threat.threat_id}:attack_battery:{plan.attack_id}:{plan.run_id}"
                    ),
                    threat_id=threat.threat_id,
                    analyzer=self.name,
                    evidence_class=(
                        EvidenceClass.FLOOR if valid_floor else EvidenceClass.SCREEN
                    ),
                    coverage=EvidenceCoverage.NAMED_PROJECTION,
                    metric=plan.metric,
                    value=estimate,
                    lower=lower,
                    upper=None,
                    baseline=None,
                    realizability=Realizability.RECIPIENT,
                    can_clear=False,
                    can_block=valid_floor,
                    assumptions=(
                        f"policy-bound attack catalog sha256={value.catalog_sha256}",
                        f"policy-bound complete battery sha256={value.configuration_sha256}",
                        f"comparison family size={plan.comparison_family_size}",
                    ),
                    limitations=limitations,
                    details={
                        "attack_id": plan.attack_id,
                        "attack_version": plan.attack_version,
                        "attack_service_id": result.service_id,
                        "attack_implementation_sha256": result.implementation_sha256,
                        "run_id": plan.run_id,
                        "status": result.status,
                        "successes": result.successes,
                        "trials": result.trials,
                        "positive_control_ids": list(plan.positive_control_ids),
                        "positive_controls_passed": controls_pass,
                        "replayed_positive_control_lower_bounds": {
                            control_id: replayed_controls[control_id][1]
                            for control_id in plan.positive_control_ids
                        },
                        "positive_control_tool_identities": {
                            control_id: {
                                "service_id": control_results[control_id].service_id,
                                "attack_version": control_results[
                                    control_id
                                ].attack_version,
                                "implementation_sha256": control_results[
                                    control_id
                                ].implementation_sha256,
                            }
                            for control_id in plan.positive_control_ids
                        },
                        "per_comparison_confidence": per_comparison_confidence,
                        "simultaneous_bound_count": simultaneous_bound_count,
                        "one_sided_fpr_upper": fpr_upper,
                        "operating_point_attained": operating_point_attained,
                        "worker_output_sha256": value.worker_output_sha256,
                        "raw_result_sha256": result.raw_result_sha256,
                        "retained_raw_bundle_sha256": (
                            value.worker_output.retained_raw_bundle_sha256
                        ),
                    },
                )
            )
        return tuple(records)
