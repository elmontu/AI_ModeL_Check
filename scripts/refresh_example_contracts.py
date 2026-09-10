#!/usr/bin/env python3
"""Regenerate the current, hash-bound demonstration contracts.

This script is intentionally limited to the small files under ``examples/``.
It constructs the attack-battery example from typed runtime models so nested
digests, policy allowlists, provenance sources, and the retained assessment
report cannot be updated independently.
"""

from __future__ import annotations

import json
from pathlib import Path

from model_release_assurance.analyzers.attack import clopper_pearson_lower
from model_release_assurance.analyzers.attack_battery import AttackBatteryAnalyzer
from model_release_assurance.analyzers.base import statistical_floor_design_sha256
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes, sha256_file
from model_release_assurance.models import (
    AnalyzerProvenance,
    AttackBatteryConfiguration,
    AttackBatteryInput,
    AttackBatteryWorkerOutput,
    AttackCatalog,
    AttackCatalogEntry,
    AttackIsolationEvidence,
    AttackPositiveControlPlan,
    AttackPositiveControlResult,
    AttackResourceLimits,
    AttackRunPlan,
    AttackRunResult,
    AssessmentRequest,
    EvidenceContext,
    EvidenceProducer,
    InterfaceContract,
    PolicyBundle,
    PopulationScope,
    ReleaseContract,
    RuntimeIdentity,
    StatisticalFloorFamilyPlan,
    StatisticalFloorDesignRegistration,
    StatisticalFloorFamilyMember,
    ThreatContract,
)
from model_release_assurance.decision import (
    decision_game_sha256,
    population_scope_sha256,
)
from model_release_assurance.optimizer import OptimizationRequest, SelectionPolicy
from model_release_assurance.runtime_identity import current_runtime_identity
from model_release_assurance.services import LocalAnalyzerService, default_analyzer_service_registry


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")


def _model_hash(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _upgrade_interface(value: dict) -> None:
    """Materialize the current required-explicit interface contract in fixtures."""

    value["schema_version"] = "3.0"
    if "rate_limit" not in value:
        enabled = bool(value["rate_limited"])
        value["rate_limit"] = {
            "enabled": enabled,
            "scope": "per_identity" if enabled else "none",
            "requests_per_window": value.get("query_budget") or 1_000 if enabled else None,
            "window_seconds": 3_600 if enabled else None,
            "burst_capacity": 20 if enabled else None,
            "retry_after_exposed": enabled,
            "enforcement": "shared_strong" if enabled else "not_applicable",
            "custom_parameters": {},
        }
    protocol = value.get("llm_protocol")
    if protocol is not None:
        protocol["schema_version"] = "1.0"


def _service(kind: str):
    return next(
        service
        for service in default_analyzer_service_registry().services
        if service.descriptor.input_kind == kind
    )


def _source_payload(value: object, bound_fields: tuple[str, ...]) -> dict:
    dumped = value.model_dump(mode="json", exclude_none=False)  # type: ignore[attr-defined]
    return {field: dumped.get(field) for field in bound_fields}


def refresh() -> None:
    request_raw = _load(EXAMPLES / "request.json")
    optimization_raw = _load(EXAMPLES / "optimization-request.json")
    request_raw["schema_version"] = "5.0"
    optimization_raw["schema_version"] = "5.0"
    _upgrade_interface(request_raw["release"]["interface"])
    for configuration_raw in optimization_raw["configurations"]:
        _upgrade_interface(configuration_raw["release_interface"])

    selection_policy = SelectionPolicy.model_validate(optimization_raw["selection_policy"])
    selection_policy_sha256 = _model_hash(selection_policy)

    catalog = AttackCatalog(
        catalog_id="mra.demo.attack-catalog",
        catalog_version="1.0.0",
        valid_from="2026-01-01T00:00:00Z",
        valid_until="2099-01-01T00:00:00Z",
        entries=(
            AttackCatalogEntry(
                attack_id="membership_loss_threshold",
                attack_version="1.0.0",
                service_id="mra.red-team.membership-loss-threshold",
                implementation_sha256=sha256_file(
                    ROOT / "src" / "model_release_assurance" / "red_team.py"
                ),
                applicable_model_families=("tree_ensemble",),
                applicable_protocol_types=("predictive",),
                applicable_threat_kinds=("membership",),
                supported_metrics=("equal_prior_membership_success",),
                evidence_role="blocking_floor",
                positive_control_kind="known_leak_binomial",
                minimum_repetitions=1,
                requires_model_execution=True,
            ),
        ),
    )
    catalog_entry = catalog.entries[0]
    catalog_sha256 = _model_hash(catalog)
    control_plan = AttackPositiveControlPlan(
        control_id="known-leak-membership-control",
        attack_id="membership_loss_threshold",
        control_kind="known_leak_binomial",
        reference_artifact_sha256="a" * 64,
        reference_dataset_sha256="b" * 64,
        minimum_trials=100,
        minimum_detection_lower_bound=0.8,
        confidence=0.95,
    )
    configuration = AttackBatteryConfiguration(
        configuration_id="demo-membership-battery-v1",
        catalog_sha256=catalog_sha256,
        frozen_at="2026-08-17T00:00:00Z",
        resource_limits=AttackResourceLimits(
            timeout_seconds=300,
            memory_megabytes=2048,
            cpu_cores=2.0,
            maximum_records=10_000,
            maximum_output_bytes=10_000_000,
        ),
        runs=(
            AttackRunPlan(
                run_id="membership-loss-run-1",
                attack_id="membership_loss_threshold",
                attack_version="1.0.0",
                metric="equal_prior_membership_success",
                evidence_role="blocking_floor",
                seed=20260817,
                repetitions=1,
                confidence=0.95,
                comparison_family_size=1,
                positive_control_ids=(control_plan.control_id,),
                parameters={
                    "threshold_calibration": "disjoint_reference_model",
                    "audit_partition": "disjoint_target_holdout",
                },
            ),
        ),
        positive_controls=(control_plan,),
        stopping_rule="execute every frozen run and positive control exactly once",
        multiplicity_method="bonferroni",
    )
    configuration_sha256 = _model_hash(configuration)
    _write(EXAMPLES / "config" / "attack-catalog.json", catalog.model_dump(mode="json"))
    _write(
        EXAMPLES / "config" / "attack-battery.json",
        configuration.model_dump(mode="json"),
    )

    analyzer_configuration_path = EXAMPLES / "config" / "attack-battery-analyzer.json"
    _write(
        analyzer_configuration_path,
        {
            "analyzer": "attack_battery",
            "configuration_version": "1.0.0",
            "translation": "typed battery results to positive-control-guarded floor records",
            "multiplicity": "derived from every blocking run in the complete frozen battery",
            "authority": "floor_or_screen_only",
        },
    )
    battery_service = LocalAnalyzerService(AttackBatteryAnalyzer())
    service_by_kind = {
        kind: _service(kind).descriptor
        for kind in ("tree_linkage", "dp", "attack")
    }
    standalone_family_id = "demo-standalone-membership-floor-v1"
    standalone_attack_template = _load(EXAMPLES / "evidence" / "attack-counts.json")
    design_registration = StatisticalFloorDesignRegistration(
        registration_id=f"{standalone_family_id}:calibrated-loss",
        analyzer="attack",
        threat_id="membership-person",
        population_scope_id="service-participants-2026",
        member_id="calibrated-loss",
        decision_metric="equal_prior_membership_success",
        registered_at="2026-08-16T00:00:00Z",
        dataset_snapshot_sha256=sha256_bytes(
            b"demo-private-membership-audit-snapshot-v1"
        ),
        procedure_sha256=sha256_file(
            ROOT / "src" / "model_release_assurance" / "analyzers" / "attack.py"
        ),
        execution_plan_sha256=sha256_bytes(
            b"demo-calibrated-loss-fixed-split-threshold-and-query-plan-v1"
        ),
        random_seed=20260817,
        stopping_rule="collect exactly 1000 disjoint audit decisions",
        planned_primary_trials=standalone_attack_template["trials"],
        planned_control_trials=standalone_attack_template["nonmember_trials"] or 0,
        target_fpr=standalone_attack_template["target_fpr"],
        notes=(
            "Demonstration commitment; production must bind the retained private "
            "dataset snapshot and full attack procedure."
        ),
    )
    design_registration_path = EXAMPLES / "config" / "attack-design-registration.json"
    _write(
        design_registration_path,
        design_registration.model_dump(mode="json", exclude_none=False),
    )
    design_registration_sha256 = sha256_file(design_registration_path)
    standalone_attack_template["preregistration_sha256"] = (
        design_registration_sha256
    )
    standalone_attack_plan = StatisticalFloorFamilyPlan(
        family_id=standalone_family_id,
        analyzer="attack",
        threat_id="membership-person",
        decision_metric="equal_prior_membership_success",
        members=(StatisticalFloorFamilyMember(
            member_id="calibrated-loss",
            registration_path="config/attack-design-registration.json",
            registration_sha256=design_registration_sha256,
            input_design_sha256=statistical_floor_design_sha256(
                standalone_attack_template
            ),
        ),),
        familywise_confidence=0.95,
        multiplicity_method="bonferroni",
        frozen_at="2026-08-17T00:00:00Z",
        authority="whole-government-model-release-demo policy authority",
    )
    _write(
        EXAMPLES / "config" / "attack-analyzer.json",
        standalone_attack_plan.model_dump(mode="json"),
    )

    # Freeze state meaning and exact prior in policy and request before hashing
    # either. A matching game digest on an unrelated numerical table is not enough.
    finite_games = {
        "linkage-person": {
            "game_id": "demo-exact-linkage-four-candidates",
            "states": [{"state_id": value, "secret_value_definition": f"target identity is candidate {value}"} for value in ("a", "b", "c", "d")],
            "prior": [{"numerator": 1, "denominator": 4} for _ in range(4)],
            "prior_basis": "demonstration uniform prior over the frozen four-candidate roster",
            "authority": "whole-government-model-release-demo policy authority",
        },
        "membership-person": {
            "game_id": "demo-equal-prior-membership",
            "states": [
                {"state_id": "member", "secret_value_definition": "target record was included in training"},
                {"state_id": "nonmember", "secret_value_definition": "target record was not included in training"},
            ],
            "prior": [{"numerator": 1, "denominator": 2} for _ in range(2)],
            "prior_basis": "balanced membership challenge with equal prior mass on both states",
            "authority": "whole-government-model-release-demo policy authority",
        },
    }
    for threat_raw in request_raw["threats"]:
        threat_raw["finite_game"] = finite_games[threat_raw["threat_id"]]

    policy_raw = {
        "schema_version": "3.0",
        "policy_id": "whole-government-model-release-demo",
        "policy_version": "3.0.0",
        "effective_from": "2026-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "rules": [
            {
                "threat_id": "linkage-person",
                "kind": "linkage",
                "mandatory": True,
                "decision_metric": "incremental_bayes_linkage_success",
                "metric_parameters": {},
                "finite_game": finite_games["linkage-person"],
                "tolerance": 0.3,
                "tolerance_basis": "incremental",
                "ceiling_attack_battery_mode": "ceiling_prohibited",
            },
            {
                "threat_id": "membership-person",
                "kind": "membership",
                "mandatory": True,
                "decision_metric": "equal_prior_membership_success",
                "metric_parameters": {},
                "finite_game": finite_games["membership-person"],
                "tolerance": 0.6,
                "tolerance_basis": "absolute",
                "ceiling_attack_battery_mode": "required",
            },
        ],
        "analyzer_requirements": [
            {
                "threat_id": "linkage-person",
                "analyzer": "tree_linkage",
                "minimum_service_version": service_by_kind["tree_linkage"].service_version,
                "accepted_implementation_sha256s": [
                    service_by_kind["tree_linkage"].implementation_sha256
                ],
                "accepted_configuration_sha256s": [
                    sha256_file(EXAMPLES / "config" / "tree-linkage-analyzer.json")
                ],
                "required": True,
            },
            {
                "threat_id": "membership-person",
                "analyzer": "dp",
                "minimum_service_version": service_by_kind["dp"].service_version,
                "accepted_implementation_sha256s": [service_by_kind["dp"].implementation_sha256],
                "accepted_configuration_sha256s": [
                    sha256_file(EXAMPLES / "config" / "dp-analyzer.json")
                ],
                "required": True,
            },
            {
                "threat_id": "membership-person",
                "analyzer": "attack",
                "minimum_service_version": service_by_kind["attack"].service_version,
                "accepted_implementation_sha256s": [
                    service_by_kind["attack"].implementation_sha256
                ],
                "accepted_configuration_sha256s": [
                    sha256_file(EXAMPLES / "config" / "attack-analyzer.json")
                ],
                "required": True,
            },
            {
                "threat_id": "membership-person",
                "analyzer": "attack_battery",
                "minimum_service_version": battery_service.descriptor.service_version,
                "accepted_implementation_sha256s": [
                    battery_service.descriptor.implementation_sha256
                ],
                "accepted_configuration_sha256s": [sha256_file(analyzer_configuration_path)],
                "required": True,
            },
        ],
        "attack_battery_requirements": [
            {
                "requirement_id": "membership-required-battery-v1",
                "threat_id": "membership-person",
                "accepted_catalog_sha256s": [catalog_sha256],
                "required_attack_ids": ["membership_loss_threshold"],
                "accepted_configuration_sha256s": [configuration_sha256],
                "accepted_worker_service_ids": ["mra.red-team.membership-loss-threshold"],
                "minimum_worker_service_version": "1.0.0",
                "accepted_worker_implementation_sha256s": [
                    sha256_file(ROOT / "src" / "model_release_assurance" / "red_team.py")
                ],
                "accepted_worker_image_sha256s": ["c" * 64],
                "accepted_attester_key_ids": [],
                "minimum_isolation_assurance": "declared",
                "positive_controls_required": True,
                "minimum_positive_control_detection_lower_bound": 0.8,
            }
        ],
        "accepted_selection_policy_sha256s": [selection_policy_sha256],
    }
    policy = PolicyBundle.model_validate(policy_raw)
    _write(EXAMPLES / "policy.json", policy.model_dump(mode="json", exclude_none=True))
    policy_sha256 = sha256_file(EXAMPLES / "policy.json")

    request_raw["policy"].update(
        {
            "policy_version": policy.policy_version,
            "policy_sha256": policy_sha256,
        }
    )
    release = ReleaseContract.model_validate(request_raw["release"])
    release_contract_sha256 = _model_hash(release)
    interface_sha256 = _model_hash(release.interface)
    scopes = tuple(PopulationScope.model_validate(item) for item in request_raw["population_scopes"])
    threats = tuple(ThreatContract.model_validate(item) for item in request_raw["threats"])
    scopes_by_id = {scope.scope_id: scope for scope in scopes}
    threats_by_id = {threat.threat_id: threat for threat in threats}

    base_inputs = [
        item for item in request_raw["analyzer_inputs"] if item["analyzer"] in {"tree_linkage", "dp"}
    ]
    # Retain the standalone single-attack floor as non-battery evidence. It can
    # block but cannot satisfy the policy's complete-battery precondition.
    standalone_attack = _load(EXAMPLES / "evidence" / "attack-counts.json")
    standalone_attack["preregistration_sha256"] = design_registration_sha256
    standalone_attack["provenance"] = {
        "tool": "mra-demo-attack",
        "tool_version": "1.0",
        "producer": {
            "service_id": "placeholder",
            "service_version": "0.0.0",
            "implementation_sha256": "0" * 64,
            "configuration_sha256": "0" * 64,
        },
        "configuration_path": "config/attack-analyzer.json",
        "source_path": "evidence/attack-counts.json",
        "source_sha256": "0" * 64,
        "bound_fields": [
            "analyzer",
            "threat_id",
            "population_scope_id",
            "attack_name",
            "preregistration_sha256",
            "metric",
            "successes",
            "trials",
            "confidence",
            "comparison_family_size",
            "calibration_disjoint",
            "audit_disjoint",
            "raw_counts_retained",
            "threshold_pre_registered",
            "false_positives",
            "nonmember_trials",
            "target_fpr",
            "evidence_context",
        ],
    }
    base_inputs.append(standalone_attack)
    for item in base_inputs:
        threat = threats_by_id[item["threat_id"]]
        scope = scopes_by_id[threat.population_scope_id]
        if item["analyzer"] == "tree_linkage":
            item["observed_interface_sha256"] = interface_sha256
        context = {
            "release_id": release.release_id,
            "release_contract_sha256": release_contract_sha256,
            "policy_sha256": policy_sha256,
            "artifact_sha256": release.artifact_sha256,
            "interface_sha256": interface_sha256,
            "population_scope_id": scope.scope_id,
            "population_scope_sha256": population_scope_sha256(scope),
            "decision_game_sha256": decision_game_sha256(threat, scope),
            "observed_at": "2026-08-18T00:00:00Z",
        }
        item["evidence_context"] = context
        bound_fields = tuple(item["provenance"]["bound_fields"])
        source_path = EXAMPLES / item["provenance"]["source_path"]
        source_payload = {
            field: item.get(field) for field in bound_fields
        }
        _write(source_path, source_payload)
        item["provenance"]["source_sha256"] = sha256_file(source_path)
        descriptor = service_by_kind[item["analyzer"]]
        item["provenance"]["producer"].update(
            {
                "service_id": descriptor.service_id,
                "service_version": descriptor.service_version,
                "implementation_sha256": descriptor.implementation_sha256,
                "configuration_sha256": sha256_file(
                    EXAMPLES / item["provenance"]["configuration_path"]
                ),
            }
        )

    membership = threats_by_id["membership-person"]
    membership_scope = scopes_by_id[membership.population_scope_id]
    context = EvidenceContext(
        release_id=release.release_id,
        release_contract_sha256=release_contract_sha256,
        policy_sha256=policy_sha256,
        artifact_sha256=release.artifact_sha256,
        interface_sha256=interface_sha256,
        population_scope_id=membership_scope.scope_id,
        population_scope_sha256=population_scope_sha256(membership_scope),
        decision_game_sha256=decision_game_sha256(membership, membership_scope),
        observed_at="2026-08-18T00:00:00Z",
    )
    control_lower = clopper_pearson_lower(95, 100, 0.95)
    worker = EvidenceProducer(
        service_id="mra.red-team.membership-loss-threshold",
        service_version="1.0.0",
        implementation_sha256=sha256_file(
            ROOT / "src" / "model_release_assurance" / "red_team.py"
        ),
        configuration_sha256=configuration_sha256,
    )
    worker_output = AttackBatteryWorkerOutput(
        execution_id="demo-membership-battery-execution",
        **{
            field: getattr(context, field)
            for field in (
                "release_id",
                "release_contract_sha256",
                "policy_sha256",
                "artifact_sha256",
                "interface_sha256",
                "population_scope_id",
                "population_scope_sha256",
                "decision_game_sha256",
            )
        },
        catalog_sha256=catalog_sha256,
        configuration_sha256=configuration_sha256,
        worker=worker,
        worker_runtime_identity=current_runtime_identity(
            component_id="attack_battery_worker",
            component_version="AttackBatteryWorkerOutput/1.0",
            algorithm_profile={
                "catalog_sha256": catalog_sha256,
                "configuration_sha256": configuration_sha256,
                "attacks": ["membership_loss_threshold"],
                "positive_controls": [control_plan.control_id],
                "decision_authority": "none",
            },
        ),
        isolation=AttackIsolationEvidence(
            assurance="declared",
            worker_image_sha256="c" * 64,
            run_as_non_root=True,
            no_new_privileges=True,
            read_only_root_filesystem=True,
            network_access="none",
            writable_audit_path=False,
            writable_key_path=False,
            writable_governance_path=False,
            read_only_mount_sha256s=(release.artifact_sha256,),
        ),
        started_at="2026-08-18T00:00:00Z",
        completed_at="2026-08-18T00:05:00Z",
        positive_controls=(
            AttackPositiveControlResult(
                control_id=control_plan.control_id,
                attack_id=control_plan.attack_id,
                service_id=catalog_entry.service_id,
                attack_version=catalog_entry.attack_version,
                implementation_sha256=catalog_entry.implementation_sha256,
                status="succeeded",
                successes=95,
                trials=100,
                reported_detection_lower_bound=control_lower,
                raw_result_sha256=sha256_bytes(b"demo-positive-control-95-of-100"),
            ),
        ),
        results=(
            AttackRunResult(
                run_id="membership-loss-run-1",
                attack_id="membership_loss_threshold",
                service_id=catalog_entry.service_id,
                attack_version=catalog_entry.attack_version,
                implementation_sha256=catalog_entry.implementation_sha256,
                status="succeeded",
                metric="equal_prior_membership_success",
                successes=520,
                trials=1000,
                raw_result_sha256=sha256_bytes(b"demo-membership-result-520-of-1000"),
                negative_control_summary="permuted labels retained as a null check, not a positive control",
            ),
        ),
        retained_raw_bundle_sha256=sha256_bytes(
            b"demo-positive-control-95-of-100|demo-membership-result-520-of-1000"
        ),
    )
    worker_output_sha256 = _model_hash(worker_output)
    bound_fields = (
        "analyzer",
        "schema_version",
        "threat_id",
        "population_scope_id",
        "catalog",
        "catalog_sha256",
        "configuration",
        "configuration_sha256",
        "worker_output",
        "worker_output_sha256",
        "evidence_context",
    )
    battery_without_provenance = {
        "analyzer": "attack_battery",
        "schema_version": "1.0",
        "threat_id": membership.threat_id,
        "population_scope_id": membership_scope.scope_id,
        "catalog": catalog.model_dump(mode="json", exclude_none=False),
        "catalog_sha256": catalog_sha256,
        "configuration": configuration.model_dump(mode="json", exclude_none=False),
        "configuration_sha256": configuration_sha256,
        "worker_output": worker_output.model_dump(mode="json", exclude_none=False),
        "worker_output_sha256": worker_output_sha256,
        "evidence_context": context.model_dump(mode="json"),
    }
    battery_source = EXAMPLES / "evidence" / "attack-battery.json"
    _write(battery_source, battery_without_provenance)
    battery = AttackBatteryInput.model_validate({
        **battery_without_provenance,
        "provenance": AnalyzerProvenance(
            tool="mra-attack-battery-adapter",
            tool_version="1.0.0",
            producer=EvidenceProducer(
                service_id=battery_service.descriptor.service_id,
                service_version=battery_service.descriptor.service_version,
                implementation_sha256=battery_service.descriptor.implementation_sha256,
                configuration_sha256=sha256_file(analyzer_configuration_path),
            ),
            configuration_path="config/attack-battery-analyzer.json",
            source_path="evidence/attack-battery.json",
            source_sha256=sha256_file(battery_source),
            bound_fields=bound_fields,
        ).model_dump(mode="json"),
    })
    request_raw["analyzer_inputs"] = base_inputs + [battery.model_dump(mode="json")]
    request = AssessmentRequest.model_validate(request_raw)
    _write(EXAMPLES / "request.json", request.model_dump(mode="json", exclude_none=False))

    report = AssuranceEngine().assess(request, EXAMPLES)
    report_path = EXAMPLES / "evidence" / "assessment-clear-report.json"
    # Nullable interface fields are required-explicit in governed contracts, so
    # preserve their JSON nulls in the committed replay fixture.
    _write(report_path, report.model_dump(mode="json", exclude_none=False))

    optimization_raw["active_policy"].update(
        {
            "policy_version": policy.policy_version,
            "policy_sha256": policy_sha256,
        }
    )
    for configuration_raw in optimization_raw["configurations"]:
        configuration_raw["assessment"]["report_sha256"] = sha256_file(report_path)
        configuration_raw["assessment"]["assessment_request_path"] = "request.json"
        configuration_raw["assessment"]["assessment_request_sha256"] = sha256_file(EXAMPLES / "request.json")
        released_interface = InterfaceContract.model_validate(
            configuration_raw["release_interface"]
        )
        released_interface_sha256 = _model_hash(released_interface)

        utility_raw = configuration_raw["utility"]
        utility_raw["interface_sha256"] = released_interface_sha256
        utility_raw["population_scope_sha256s"] = [
            population_scope_sha256(scope) for scope in scopes
        ]
        utility_source_path = EXAMPLES / utility_raw["source_path"]
        utility_source = {
            key: value
            for key, value in utility_raw.items()
            if key not in {"source_path", "source_sha256"}
        }
        _write(utility_source_path, utility_source)
        utility_raw["source_sha256"] = sha256_file(utility_source_path)

        for control_raw in configuration_raw["controls"]:
            control_raw["interface_sha256"] = released_interface_sha256
            control_source_path = EXAMPLES / control_raw["evidence_path"]
            control_source = {
                key: value
                for key, value in control_raw.items()
                if key not in {"evidence_path", "evidence_sha256"}
            }
            _write(control_source_path, control_source)
            control_raw["evidence_sha256"] = sha256_file(control_source_path)

        for experiment_raw in optimization_raw["experiments"]:
            threat = threats_by_id[experiment_raw["threat_id"]]
            experiment_raw["decision_game_sha256"] = decision_game_sha256(threat, scopes_by_id[threat.population_scope_id])
            if experiment_raw["experiment_id"].endswith("-full-artifact"):
                experiment_raw["interface_sha256"] = interface_sha256
            elif experiment_raw["experiment_id"].endswith("-bounded-api"):
                experiment_raw["interface_sha256"] = released_interface_sha256
    optimization = OptimizationRequest.model_validate(optimization_raw)
    _write(
        EXAMPLES / "optimization-request.json",
        optimization.model_dump(mode="json", exclude_none=False),
    )


if __name__ == "__main__":
    refresh()
