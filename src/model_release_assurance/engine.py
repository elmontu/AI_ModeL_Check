from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .analyzers.base import Analyzer
from .decision import decision_game_sha256, decide_overall, decide_threat, population_scope_sha256
from .integrity import (
    canonical_json_bytes,
    sha256_bytes,
    verify_provenance_binding,
    verify_release_artifact,
    verify_source_file,
)
from .models import (
    AttackBatteryInput,
    AttackBatteryStatus,
    AssessmentReport,
    AssessmentRequest,
    AssessmentScope,
    CeilingAttackBatteryMode,
    EvidenceContext,
    EvidenceRecord,
    PolicyBundle,
)
from .analyzers.attack_battery import _positive_control_passes
from .analyzers.attack import clopper_pearson_upper
from .services import AnalyzerServiceRegistry, LocalAnalyzerService, default_analyzer_service_registry
from .runtime_identity import current_runtime_identity
from .version import VERSION


class AssuranceEngine:
    def __init__(
        self,
        analyzers: tuple[Analyzer, ...] | None = None,
        *,
        service_registry: AnalyzerServiceRegistry | None = None,
    ):
        if analyzers is not None and service_registry is not None:
            raise ValueError("provide analyzers or service_registry, not both")
        if analyzers is not None:
            services = tuple(
                LocalAnalyzerService(analyzer)
                for analyzer in analyzers
            )
            self.service_registry = AnalyzerServiceRegistry(services)
        else:
            self.service_registry = service_registry or default_analyzer_service_registry()
        # Backward-compatible inspection surface; routing uses the registry.
        self.analyzers = tuple(
            service.analyzer
            for service in self.service_registry.services
            if isinstance(service, LocalAnalyzerService)
        )

    def assess(self, request: AssessmentRequest, base_dir: Path) -> AssessmentReport:
        # Pydantic's model_copy/model_construct helpers intentionally skip
        # validation. Reparse the complete governed document at the trust-core
        # boundary so an in-process caller cannot bypass cross-model bindings.
        request = AssessmentRequest.model_validate(
            request.model_dump(mode="python", exclude_none=False)
        )
        policy_path = verify_source_file(
            request.policy.policy_path,
            request.policy.policy_sha256,
            base_dir,
        )
        policy = PolicyBundle.model_validate_json(policy_path.read_text(encoding="utf-8"))
        self._validate_policy(request, policy)
        verify_release_artifact(request.release, base_dir)
        threat_by_id = {threat.threat_id: threat for threat in request.threats}
        scope_by_id = {scope.scope_id: scope for scope in request.population_scopes}
        records: list[EvidenceRecord] = []
        release_contract_sha256 = sha256_bytes(canonical_json_bytes(request.release))
        interface_sha256 = sha256_bytes(canonical_json_bytes(request.release.interface))
        for value in request.analyzer_inputs:
            source_path = verify_source_file(value.provenance.source_path, value.provenance.source_sha256, base_dir)
            verify_source_file(
                value.provenance.configuration_path,
                value.provenance.producer.configuration_sha256,
                base_dir,
            )
            verify_provenance_binding(
                value,
                source_path,
                value.provenance.bound_fields,
                require_complete=True,
            )
            service = self.service_registry.resolve(value)
            producer = value.provenance.producer
            descriptor = service.descriptor
            if producer.service_id != descriptor.service_id:
                raise ValueError("analyzer producer service identity does not match the resolved service")
            if producer.service_version != descriptor.service_version:
                raise ValueError("analyzer producer version does not match the resolved service")
            if producer.implementation_sha256 != descriptor.implementation_sha256:
                raise ValueError("analyzer producer implementation digest does not match the resolved service")
            requirement = next(
                (
                    item
                    for item in policy.analyzer_requirements
                    if item.threat_id == value.threat_id and item.analyzer == value.analyzer
                ),
                None,
            )
            if requirement is None:
                raise ValueError(
                    f"policy has no analyzer requirement for {value.threat_id}/{value.analyzer}"
                )
            if self._semantic_version(producer.service_version) < self._semantic_version(
                requirement.minimum_service_version
            ):
                raise ValueError(
                    f"analyzer {value.analyzer} version {producer.service_version} is below "
                    f"policy minimum {requirement.minimum_service_version}"
                )
            if producer.implementation_sha256 not in requirement.accepted_implementation_sha256s:
                raise ValueError("analyzer implementation digest is not accepted by policy")
            if producer.configuration_sha256 not in requirement.accepted_configuration_sha256s:
                raise ValueError("analyzer configuration digest is not accepted by policy")
            threat = threat_by_id[value.threat_id]
            scope = scope_by_id[threat.population_scope_id]
            expected_context = EvidenceContext(
                release_id=request.release.release_id,
                release_contract_sha256=release_contract_sha256,
                policy_sha256=request.policy.policy_sha256,
                artifact_sha256=request.release.artifact_sha256,
                interface_sha256=interface_sha256,
                population_scope_id=scope.scope_id,
                population_scope_sha256=population_scope_sha256(scope),
                decision_game_sha256=decision_game_sha256(threat, scope),
                observed_at=value.evidence_context.observed_at,
            )
            if value.evidence_context != expected_context:
                raise ValueError(
                    f"analyzer evidence context does not match release, policy, population, or decision game for {value.threat_id}"
                )
            now = datetime.now(timezone.utc)
            if value.evidence_context.observed_at > now + timedelta(minutes=5):
                raise ValueError("evidence observed_at is implausibly in the future")
            if value.evidence_context.observed_at < policy.effective_from:
                raise ValueError("evidence predates the effective policy")
            if policy.expires_at is not None and value.evidence_context.observed_at >= policy.expires_at:
                raise ValueError("evidence was observed after policy expiry")
            if request.release.expires_at is not None and value.evidence_context.observed_at >= request.release.expires_at:
                raise ValueError("evidence was observed after release-contract expiry")
            if isinstance(value, AttackBatteryInput):
                execution = value.worker_output
                if execution.started_at < policy.effective_from:
                    raise ValueError("attack-worker execution predates the effective policy")
                if execution.completed_at > now + timedelta(minutes=5):
                    raise ValueError("attack-worker completion is implausibly in the future")
                if policy.expires_at is not None and execution.completed_at >= policy.expires_at:
                    raise ValueError("attack-worker execution completed after policy expiry")
                if (
                    request.release.expires_at is not None
                    and execution.completed_at >= request.release.expires_at
                ):
                    raise ValueError(
                        "attack-worker execution completed after release-contract expiry"
                    )
            service_records = service.analyze(request.release, threat, value)
            for record in service_records:
                if record.threat_id != threat.threat_id:
                    raise ValueError("analyzer service returned evidence for the wrong threat")
                if record.analyzer != service.descriptor.input_kind:
                    raise ValueError("analyzer service returned evidence with the wrong analyzer identity")
                if record.producer != producer:
                    raise ValueError("analyzer service returned evidence with mismatched producer bindings")
                returned_context = EvidenceContext.model_validate({
                    "release_id": record.release_id,
                    "release_contract_sha256": record.release_contract_sha256,
                    "policy_sha256": record.policy_sha256,
                    "artifact_sha256": record.artifact_sha256,
                    "interface_sha256": record.interface_sha256,
                    "population_scope_id": record.population_scope_id,
                    "population_scope_sha256": record.population_scope_sha256,
                    "decision_game_sha256": record.decision_game_sha256,
                    "observed_at": record.observed_at,
                })
                if returned_context != expected_context:
                    raise ValueError("analyzer service returned evidence with mismatched source bindings")
                if record.can_clear and not service.descriptor.can_clear:
                    raise ValueError("analyzer service exceeded its declared clearance capability")
                if record.can_block and not service.descriptor.can_block:
                    raise ValueError("analyzer service exceeded its declared blocking capability")
            records.extend(service_records)

        evidence = tuple(records)
        evidence_ids = [record.evidence_id for record in evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("analyzers produced duplicate evidence identifiers")
        battery_statuses = {
            threat.threat_id: self._attack_battery_status(request, policy, threat.threat_id)
            for threat in request.threats
        }
        decisions = tuple(
            decide_threat(
                threat,
                scope_by_id[threat.population_scope_id],
                request.release,
                evidence,
                request.policy.policy_sha256,
                battery_statuses[threat.threat_id],
            )
            for threat in request.threats
        )
        created_at = datetime.now(timezone.utc)
        request_hash = sha256_bytes(canonical_json_bytes(request))
        stable_id = uuid.uuid5(uuid.NAMESPACE_URL, f"mra:{request.release.release_id}:{request_hash}")
        return AssessmentReport(
            assessment_id=str(stable_id),
            release_id=request.release.release_id,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_sha256=request.policy.policy_sha256,
            created_at=created_at,
            request_sha256=request_hash,
            artifact_sha256=request.release.artifact_sha256,
            release_contract_sha256=release_contract_sha256,
            release_model_family=request.release.model_family,
            release_model_profile=request.release.model_profile,
            release_interface=request.release.interface,
            assessment_scope=AssessmentScope(
                declared_previous_release_ids=request.release.previous_release_ids,
            ),
            release_expires_at=request.release.expires_at,
            policy_expires_at=policy.expires_at,
            population_scope_sha256s={
                scope.scope_id: population_scope_sha256(scope)
                for scope in request.population_scopes
            },
            population_scopes=request.population_scopes,
            evidence=evidence,
            decisions=decisions,
            overall_verdict=decide_overall(decisions),
            runtime_identity=current_runtime_identity(
                component_id="assurance_engine",
                component_version="AssessmentReport/5.0",
                algorithm_profile={
                    "ordinary_decision_arithmetic": "Python binary64",
                    "decision_rule": "mandatory threats clear and no threat blocks",
                    "critical_certificate_arithmetic": "analyzer-specific replay",
                    "scipy_invoked_by_assurance_engine": False,
                    "mrap_g7_exact_or_outward_clearance_eligible": False,
                },
            ),
            engine_version=VERSION,
        )

    @staticmethod
    def _semantic_version(value: str) -> tuple[int, int, int]:
        try:
            parsed = tuple(int(part) for part in value.split("."))
        except ValueError as exc:
            raise ValueError(f"invalid analyzer semantic version {value!r}") from exc
        if len(parsed) != 3:
            raise ValueError(f"invalid analyzer semantic version {value!r}")
        return parsed  # type: ignore[return-value]

    @staticmethod
    def _validate_policy(request: AssessmentRequest, policy: PolicyBundle) -> None:
        now = datetime.now(timezone.utc)
        if request.policy.policy_id != policy.policy_id or request.policy.policy_version != policy.policy_version:
            raise ValueError("policy reference does not match the policy bundle")
        if policy.effective_from > now:
            raise ValueError("policy is not yet effective")
        if policy.expires_at is not None and policy.expires_at <= now:
            raise ValueError("policy has expired")
        rules = {rule.threat_id: rule for rule in policy.rules}
        threats = {threat.threat_id: threat for threat in request.threats}
        missing = {rule.threat_id for rule in policy.rules if rule.mandatory} - set(threats)
        if missing:
            raise ValueError(f"request omits mandatory policy threats: {sorted(missing)}")
        unknown = set(threats) - set(rules)
        if unknown:
            raise ValueError(f"request contains threats not authorised by policy: {sorted(unknown)}")
        for threat_id, threat in threats.items():
            rule = rules[threat_id]
            compared = (
                ("kind", threat.kind, rule.kind),
                ("mandatory", threat.mandatory, rule.mandatory),
                ("decision_metric", threat.decision_metric, rule.decision_metric),
                ("metric_parameters", threat.metric_parameters, rule.metric_parameters),
                ("tolerance", threat.tolerance, rule.tolerance),
                ("tolerance_basis", threat.tolerance_basis, rule.tolerance_basis),
            )
            for field, actual, expected in compared:
                if actual != expected:
                    raise ValueError(f"threat {threat_id} changes policy field {field}")
        submitted_analyzers = {
            (value.threat_id, value.analyzer) for value in request.analyzer_inputs
        }
        missing_analyzers = {
            (requirement.threat_id, requirement.analyzer)
            for requirement in policy.analyzer_requirements
            if requirement.required and requirement.threat_id in threats
        } - submitted_analyzers
        if missing_analyzers:
            raise ValueError(
                "request omits policy-required analyzers: "
                f"{sorted(f'{threat}/{analyzer}' for threat, analyzer in missing_analyzers)}"
            )

        battery_counts: dict[str, int] = {}
        for value in request.analyzer_inputs:
            if value.analyzer == "attack_battery":
                battery_counts[value.threat_id] = battery_counts.get(value.threat_id, 0) + 1
        duplicate_batteries = {
            threat_id for threat_id, count in battery_counts.items() if count != 1
        }
        if duplicate_batteries:
            raise ValueError(
                "each threat must submit exactly one complete attack battery: "
                f"{sorted(duplicate_batteries)}"
            )

    @staticmethod
    def _attack_battery_status(
        request: AssessmentRequest,
        policy: PolicyBundle,
        threat_id: str,
    ) -> AttackBatteryStatus:
        rule = next(rule for rule in policy.rules if rule.threat_id == threat_id)
        mode = rule.ceiling_attack_battery_mode
        if mode is CeilingAttackBatteryMode.PROHIBITED:
            return AttackBatteryStatus(mode=mode, satisfied=False)
        if mode is CeilingAttackBatteryMode.WAIVED:
            return AttackBatteryStatus(
                mode=mode,
                satisfied=True,
                waiver_reason=rule.ceiling_attack_battery_waiver_reason,
            )

        requirement = next(
            item for item in policy.attack_battery_requirements if item.threat_id == threat_id
        )
        candidates = [
            value
            for value in request.analyzer_inputs
            if isinstance(value, AttackBatteryInput) and value.threat_id == threat_id
        ]
        if len(candidates) != 1:
            return AttackBatteryStatus(
                mode=mode,
                requirement_id=requirement.requirement_id,
                required_attack_ids=requirement.required_attack_ids,
                satisfied=False,
                failure_reasons=("exactly one complete attack battery was not supplied",),
            )
        battery = candidates[0]
        output = battery.worker_output
        if battery.catalog_sha256 not in requirement.accepted_catalog_sha256s:
            raise ValueError("attack catalog digest is not accepted by policy")
        if battery.configuration_sha256 not in requirement.accepted_configuration_sha256s:
            raise ValueError("complete attack-battery configuration is not accepted by policy")
        if output.worker.service_id not in requirement.accepted_worker_service_ids:
            raise ValueError("attack-worker service identity is not accepted by policy")
        if AssuranceEngine._semantic_version(
            output.worker.service_version
        ) < AssuranceEngine._semantic_version(requirement.minimum_worker_service_version):
            raise ValueError("attack-worker service version is below the policy minimum")
        if (
            output.worker.implementation_sha256
            not in requirement.accepted_worker_implementation_sha256s
        ):
            raise ValueError("attack-worker implementation digest is not accepted by policy")
        isolation = output.isolation
        if isolation.worker_image_sha256 not in requirement.accepted_worker_image_sha256s:
            raise ValueError("attack-worker image digest is not accepted by policy")

        failures: list[str] = []
        required = set(requirement.required_attack_ids)
        catalogued = {entry.attack_id for entry in battery.catalog.entries}
        planned = {plan.attack_id for plan in battery.configuration.runs}
        missing_catalog = required - catalogued
        missing_plans = required - planned
        if missing_catalog:
            failures.append(f"required attacks absent from catalog: {sorted(missing_catalog)}")
        if missing_plans:
            failures.append(f"required attacks absent from frozen battery: {sorted(missing_plans)}")

        results_by_run = {result.run_id: result for result in output.results}
        completed_attack_ids: set[str] = set()
        passing_controls: set[str] = set()
        control_plans = {
            control.control_id: control for control in battery.configuration.positive_controls
        }
        control_results = {
            result.control_id: result for result in output.positive_controls
        }
        control_pass: dict[str, bool] = {}
        for control_id, plan in control_plans.items():
            passed, replayed_lower = _positive_control_passes(
                plan,
                control_results[control_id],
            )
            if (
                passed
                and plan.control_kind == "known_leak_binomial"
                and (
                    replayed_lower is None
                    or replayed_lower
                    < requirement.minimum_positive_control_detection_lower_bound
                )
            ):
                passed = False
            control_pass[control_id] = passed
            if passed:
                passing_controls.add(control_id)

        for attack_id in sorted(required & planned):
            plans = [
                plan for plan in battery.configuration.runs if plan.attack_id == attack_id
            ]
            run_failures = [
                plan.run_id
                for plan in plans
                if results_by_run[plan.run_id].status != "succeeded"
            ]
            failed_controls = sorted({
                control_id
                for plan in plans
                for control_id in plan.positive_control_ids
                if not control_pass[control_id]
            })
            ineligible_floor_runs: list[str] = []
            threat = next(item for item in request.threats if item.threat_id == threat_id)
            for plan in plans:
                result = results_by_run[plan.run_id]
                if plan.evidence_role != "blocking_floor":
                    ineligible_floor_runs.append(plan.run_id)
                    continue
                if result.status != "succeeded":
                    continue
                if plan.metric == "membership_tpr_at_fpr":
                    assert result.false_positives is not None
                    assert result.nonmember_trials is not None
                    assert result.target_fpr is not None
                    expected_target_fpr = threat.metric_parameters.get("target_fpr")
                    bounds_per_comparison = 2
                    simultaneous_bound_count = (
                        plan.comparison_family_size * bounds_per_comparison
                    )
                    per_comparison_confidence = 1.0 - (
                        (1.0 - plan.confidence) / simultaneous_bound_count
                    )
                    fpr_upper = clopper_pearson_upper(
                        result.false_positives,
                        result.nonmember_trials,
                        per_comparison_confidence,
                    )
                    if (
                        expected_target_fpr is None
                        or abs(result.target_fpr - expected_target_fpr) > 1e-15
                        or fpr_upper > result.target_fpr
                    ):
                        ineligible_floor_runs.append(plan.run_id)
            if run_failures:
                failures.append(
                    f"required attack {attack_id} has non-successful runs: {run_failures}"
                )
            if failed_controls:
                failures.append(
                    f"required attack {attack_id} has failed positive controls: "
                    f"{failed_controls}"
                )
            if ineligible_floor_runs:
                failures.append(
                    f"required attack {attack_id} has runs that cannot produce a "
                    f"validated floor: {ineligible_floor_runs}"
                )
            if not run_failures and not failed_controls and not ineligible_floor_runs:
                completed_attack_ids.add(attack_id)

        unsafe_isolation = []
        if not isolation.run_as_non_root:
            unsafe_isolation.append("worker is not declared non-root")
        if not isolation.no_new_privileges:
            unsafe_isolation.append("worker lacks no-new-privileges")
        if not isolation.read_only_root_filesystem:
            unsafe_isolation.append("worker root filesystem is writable")
        if isolation.network_access != "none":
            unsafe_isolation.append("worker network access is not disabled")
        if isolation.writable_audit_path or isolation.writable_key_path or isolation.writable_governance_path:
            unsafe_isolation.append("worker can write an audit, key, or governance path")
        failures.extend(unsafe_isolation)
        if requirement.minimum_isolation_assurance == "externally_attested":
            if isolation.assurance != "externally_attested":
                failures.append("policy requires externally attested worker isolation")
            elif isolation.attester_key_id not in requirement.accepted_attester_key_ids:
                failures.append("worker isolation attester is not accepted by policy")
            else:
                failures.append(
                    "external isolation signature verification is unavailable in the reference core"
                )

        return AttackBatteryStatus(
            mode=mode,
            requirement_id=requirement.requirement_id,
            required_attack_ids=requirement.required_attack_ids,
            completed_attack_ids=tuple(sorted(completed_attack_ids)),
            passing_positive_control_ids=tuple(sorted(passing_controls)),
            satisfied=not failures,
            failure_reasons=tuple(failures),
        )
