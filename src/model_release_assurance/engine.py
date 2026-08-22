from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .analyzers import AttackAnalyzer, ControlledInferenceAnalyzer, DpAnalyzer, PopulationAnalyzer, TreeLinkageAnalyzer
from .analyzers.base import Analyzer
from .decision import decision_game_sha256, decide_overall, decide_threat, population_scope_sha256
from .integrity import (
    canonical_json_bytes,
    sha256_bytes,
    verify_provenance_binding,
    verify_release_artifact,
    verify_source_file,
)
from .models import AssessmentReport, AssessmentRequest, EvidenceContext, EvidenceRecord, PolicyBundle
from .version import VERSION


class AssuranceEngine:
    def __init__(self, analyzers: tuple[Analyzer, ...] | None = None):
        self.analyzers = analyzers or (
            TreeLinkageAnalyzer(),
            DpAnalyzer(),
            AttackAnalyzer(),
            ControlledInferenceAnalyzer(),
            PopulationAnalyzer(),
        )

    def assess(self, request: AssessmentRequest, base_dir: Path) -> AssessmentReport:
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
            verify_provenance_binding(
                value,
                source_path,
                value.provenance.bound_fields,
                require_complete=True,
            )
            matches = [analyzer for analyzer in self.analyzers if analyzer.supports(value)]
            if len(matches) != 1:
                raise ValueError(f"expected one analyzer for {value.analyzer}, found {len(matches)}")
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
            records.extend(matches[0].analyze(request.release, threat, value))

        evidence = tuple(records)
        evidence_ids = [record.evidence_id for record in evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("analyzers produced duplicate evidence identifiers")
        decisions = tuple(
            decide_threat(
                threat,
                scope_by_id[threat.population_scope_id],
                request.release,
                evidence,
                request.policy.policy_sha256,
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
            engine_version=VERSION,
        )

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
