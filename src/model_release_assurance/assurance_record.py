"""Four-verdict, exact-bound governance records; never deployment authorization.

The approved request/scope and trust stores are external verifier inputs. A
declared finite scenario partition is checked, not mistaken for world coverage.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Literal, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import Field, model_validator

from .integrity import canonical_json_bytes, sha256_bytes, signer_key_id
from .models import (
    AssessmentReport, AssessmentRequest, CeilingAttackBatteryMode, EvidenceClass,
    EvidenceConsistency, RationalProbability, StrictModel, Verdict, PolicyBundle,
)

REQUIRED_CHANNELS = frozenset({"weights", "outputs", "precision", "metadata", "logs"})
UNVERIFIED_RESOLVING_PLAN = (
    "crossing risk lacks a verified applicable resolving plan; analyzer suggestions are advisory"
)


class AssuranceVerdict(StrEnum):
    RELEASE = "RELEASE"
    RELEASE_WITH_RISK = "RELEASE-WITH-RISK"
    BLOCK = "BLOCK"
    INCONCLUSIVE = "INCONCLUSIVE"


class AdversaryModel(StrictModel):
    access_levels: tuple[str, ...] = Field(min_length=1)
    auxiliary_knowledge: dict[str, tuple[str, ...]]
    metadata_profiles: dict[str, str]
    query_budget: int | None = Field(ge=0)
    adaptive_queries: bool
    joint_transcript_description: str = Field(min_length=20)


class ExportChannel(StrictModel):
    channel_id: str = Field(min_length=1)
    exported: bool
    threat_ids: tuple[str, ...]
    reason: str = Field(min_length=3)

    @model_validator(mode="after")
    def channel_mapping(self):
        if self.exported != bool(self.threat_ids):
            raise ValueError("exported channels need threat mappings; excluded channels need none")
        if len(set(self.threat_ids)) != len(self.threat_ids):
            raise ValueError("duplicate channel threat mapping")
        return self


class ThreatScenario(StrictModel):
    scenario_id: str = Field(min_length=1)
    threat_id: str = Field(min_length=1)
    description: str = Field(min_length=3)
    channel_ids: tuple[str, ...] = Field(min_length=1)


class ScopeExclusion(StrictModel):
    scenario_id: str = Field(min_length=1)
    reason: str = Field(min_length=10)


class AssuranceScope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    scope_id: str = Field(min_length=3)
    adversary: AdversaryModel
    # The approved finite universe is an external premise, not inferred from tests.
    declared_scenario_ids: tuple[str, ...] = Field(min_length=1)
    scenarios: tuple[ThreatScenario, ...] = Field(min_length=1)
    out_of_scope: tuple[ScopeExclusion, ...]
    channels: tuple[ExportChannel, ...] = Field(min_length=5)
    residual_risk_acceptance_permitted: bool = False
    approved_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def declared_partition_is_complete(self):
        universe = set(self.declared_scenario_ids)
        assigned = [s.scenario_id for s in self.scenarios]
        excluded = [s.scenario_id for s in self.out_of_scope]
        if len(universe) != len(self.declared_scenario_ids) or len(set(assigned + excluded)) != len(assigned + excluded):
            raise ValueError("scenario ownership must be unique and disjoint")
        if set(assigned + excluded) != universe:
            raise ValueError("every declared scenario needs one threat cell or a reasoned exclusion")
        channels = {c.channel_id: c for c in self.channels}
        if len(channels) != len(self.channels) or not REQUIRED_CHANNELS <= channels.keys():
            raise ValueError("unique weights/outputs/precision/metadata/logs entries are required")
        for scenario in self.scenarios:
            for name in scenario.channel_ids:
                if name not in channels or not channels[name].exported or scenario.threat_id not in channels[name].threat_ids:
                    raise ValueError("scenario channels must be exported and mapped to its threat")
        for channel in self.channels:
            for threat_id in channel.threat_ids:
                if not any(s.threat_id == threat_id and channel.channel_id in s.channel_ids for s in self.scenarios):
                    raise ValueError("every channel/threat mapping needs an assigned scenario witness")
        for instant in (self.approved_at, self.expires_at):
            if instant.utcoffset() is None:
                raise ValueError("scope times must include timezone offsets")
        if self.expires_at <= self.approved_at:
            raise ValueError("scope expiry must follow approval")
        return self


class ThreatRiskInterval(StrictModel):
    threat_id: str
    metric: str
    game_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    floor: RationalProbability
    ceiling: RationalProbability
    gap: RationalProbability
    threshold: RationalProbability
    evidence_ids: tuple[str, ...]
    decision_flips_in_gap: bool
    resolution_code: str | None = None
    resolving_actions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def exact_interval(self):
        low, high, threshold = self.floor.as_fraction(), self.ceiling.as_fraction(), self.threshold.as_fraction()
        if high < low or self.gap.as_fraction() != high - low:
            raise ValueError("gap must equal the exact nonnegative ceiling minus floor")
        if self.decision_flips_in_gap != (low <= threshold < high):
            raise ValueError("gap-crossing flag disagrees with exact interval")
        return self


class ResidualRiskAcceptance(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_ceilings: dict[str, RationalProbability] = Field(min_length=1)
    reason: str = Field(min_length=20)
    issued_at: datetime
    expires_at: datetime
    signer_key_id: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_time_interval(self):
        if any(t.utcoffset() is None for t in (self.issued_at, self.expires_at)) or self.expires_at <= self.issued_at:
            raise ValueError("acceptance needs ordered timezone-aware issue/expiry times")
        return self


class ReleaseAssuranceRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    release_id: str
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    expires_at: datetime
    verdict: AssuranceVerdict
    threats: tuple[ThreatRiskInterval, ...]
    blocking_reasons: tuple[str, ...] = ()
    accepted_residual_risks: tuple[str, ...] = ()
    acceptance: ResidualRiskAcceptance | None = None
    equality_convention: Literal["ceiling_le_threshold;floor_gt_threshold"] = "ceiling_le_threshold;floor_gt_threshold"
    scope_coverage: Literal["complete_relative_to_approved_declared_universe"] = "complete_relative_to_approved_declared_universe"
    world_scope_truth_verified: Literal[False] = False
    authorization_eligible: Literal[False] = False

    @model_validator(mode="after")
    def consistent_disposition(self):
        if any(t.utcoffset() is None for t in (self.created_at, self.expires_at)):
            raise ValueError("record times must include timezone offsets")
        ids = [t.threat_id for t in self.threats]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate threat intervals")
        if self.verdict is AssuranceVerdict.BLOCK:
            if not self.blocking_reasons or self.accepted_residual_risks:
                raise ValueError("BLOCK needs reasons and cannot accept residual risks")
            return self
        if self.blocking_reasons or not self.threats or self.expires_at <= self.created_at:
            raise ValueError("nonblocking records need live, complete, nonempty intervals")
        if any(t.floor.as_fraction() > t.threshold.as_fraction() for t in self.threats):
            raise ValueError("a demonstrated threshold violation requires BLOCK")
        crossing = {t.threat_id: t.ceiling for t in self.threats if t.decision_flips_in_gap}
        if self.verdict is AssuranceVerdict.RELEASE:
            if crossing or self.acceptance or self.accepted_residual_risks:
                raise ValueError("RELEASE requires every ceiling within threshold and no risk acceptance")
        elif self.verdict is AssuranceVerdict.RELEASE_WITH_RISK:
            if (not crossing or self.acceptance is None
                    or self.acceptance.context_sha256 != self.context_sha256
                    or self.acceptance.accepted_ceilings != crossing
                    or tuple(sorted(crossing)) != self.accepted_residual_risks):
                raise ValueError("RELEASE-WITH-RISK requires exact acceptance of every crossing ceiling")
        elif (not crossing or self.acceptance or self.accepted_residual_risks
                or any(not t.resolution_code or not t.resolving_actions for t in self.threats if t.decision_flips_in_gap)):
            raise ValueError("INCONCLUSIVE requires an actionable crossing and no accepted risk")
        return self


class SignedReleaseAssuranceRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    record: ReleaseAssuranceRecord
    signer_key_id: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


class AssuranceGateResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    verdict: AssuranceVerdict
    recommendation_passed: bool
    authorization_eligible: Literal[False] = False
    reasons: tuple[str, ...]
    external_enforcement_required: tuple[str, ...] = (
        "authenticated complete active-portfolio state and atomic budget commit",
        "independent evidence execution and complete live-channel correspondence",
        "enforcing gateway, current lease/revocation and lifetime monitoring",
    )


def _prob(value: Fraction) -> RationalProbability:
    return RationalProbability(numerator=value.numerator, denominator=value.denominator)


def _hash(model) -> str:
    return sha256_bytes(canonical_json_bytes(model))


def assurance_context_sha256(request, report, scope) -> str:
    return _hash({"domain": "MRA-ASSURANCE-CONTEXT/1", "request": _hash(request), "assessment": _hash(report), "scope": _hash(scope)})


def declared_export_channels(interface) -> dict[str, bool]:
    """Conservative category inventory of the typed declaration, not a live scan."""
    raw = interface.model_dump(mode="json")
    outputs, paths = raw["output_channels"], raw["access_paths"]
    named = outputs["custom_channels"] + paths["side_channels"] + paths["custom_side_channels"]
    return {
        "weights": raw["access"] == "full_artifact" or outputs["parameters"],
        "outputs": bool(raw["outputs"]), "precision": raw["precision_bits"] is not None,
        "metadata": bool(outputs["shipped_summary_metadata"]),
        "logs": any("log" in str(name).lower() for name in named),
        "timing": raw["timing"]["recipient_observable"],
        "errors": raw["errors"]["transport_status"] != "none" or raw["errors"]["error_content"] != "none" or raw["errors"]["retry_metadata"],
        "batching": raw["execution"]["batching"] != "none",
        "concurrency": raw["execution"]["maximum_concurrent_requests"] is not None,
        "state": raw["execution"]["cross_request_state"] != "none",
        "side_channels": bool(paths["side_channels"] or paths["custom_side_channels"]),
        "admin": paths["admin_access"] != "none" or bool(paths["admin_capabilities"]),
        "local": paths["local_access"] != "none" or bool(paths["local_capabilities"]),
        "serialization": bool(raw["serialization"]["formats"]),
        "llm_protocol": raw["llm_protocol"] is not None,
    }


def _signed_bytes(domain: str, payload: dict) -> bytes:
    return canonical_json_bytes({"domain": domain, "payload": payload})


def _verify_signature(domain: str, payload: dict, signature: str, key_id: str, trusted: Mapping[str, Path]):
    if key_id not in trusted:
        raise ValueError("signer is not in the verifier-supplied trust store")
    key = serialization.load_pem_public_key(Path(trusted[key_id]).read_bytes())
    if not isinstance(key, Ed25519PublicKey) or signer_key_id(key) != key_id:
        raise ValueError("trust-store key identity mismatch")
    key.verify(base64.b64decode(signature, validate=True), _signed_bytes(domain, payload))


def build_assurance_record(request: AssessmentRequest, report: AssessmentReport, scope: AssuranceScope,
                           *, policy_bytes: bytes, as_of: datetime | None = None, acceptance: ResidualRiskAcceptance | None = None,
                           trusted_acceptors: Mapping[str, Path] | None = None) -> ReleaseAssuranceRecord:
    from .integrity import validate_report_against_request, validate_report_against_policy
    request = AssessmentRequest.model_validate(request.model_dump(mode="json"))
    report = AssessmentReport.model_validate(report.model_dump(mode="json"))
    scope = AssuranceScope.model_validate(scope.model_dump(mode="json"))
    now = as_of or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("verification time needs a timezone offset")
    # Malformed/inconsistent imports raise: the gate/CLI maps these failures to BLOCK.
    if sha256_bytes(policy_bytes) != request.policy.policy_sha256:
        raise ValueError("active policy bytes do not match the approved request")
    policy = PolicyBundle.model_validate_json(policy_bytes)
    validate_report_against_policy(report, policy, policy_sha256=request.policy.policy_sha256, request=request, as_of=now)
    validate_report_against_request(report, request, as_of=now)
    failures = []
    if not scope.approved_at <= now < scope.expires_at:
        failures.append("approved scope is future-dated or expired")
    interface = request.release.interface
    if (scope.adversary.query_budget != interface.query_budget
            or scope.adversary.adaptive_queries != interface.adaptive_queries
            or scope.adversary.access_levels != (str(interface.access),)):
        failures.append("adversary access/adaptivity/query budget does not match the release contract")
    if (scope.adversary.auxiliary_knowledge != {t.threat_id: t.side_information for t in request.threats}
            or scope.adversary.metadata_profiles != {t.threat_id: t.adversary_metadata_profile for t in request.threats}):
        failures.append("per-threat auxiliary knowledge and metadata profiles must exactly match the evidenced games")
    channel_map = {c.channel_id: c for c in scope.channels}
    inventory = declared_export_channels(interface)
    if channel_map.keys() != inventory.keys():
        failures.append("scope channel inventory must exactly match the supported release-channel inventory")
    for name, observable in inventory.items():
        if name not in channel_map or observable != channel_map[name].exported:
            failures.append(f"declared interface channel {name} is absent or has a different export state")
    expected = {t.threat_id for t in request.threats}
    assigned = {s.threat_id for s in scope.scenarios}
    mapped = {t for c in scope.channels for t in c.threat_ids}
    if expected != assigned or expected != mapped:
        failures.append("scope must partition scenarios and map channels for exactly every requested threat")
    context = assurance_context_sha256(request, report, scope)
    intervals = []
    evidence = {e.evidence_id: e for e in report.evidence}
    for decision in report.decisions:
        low, high = decision.lower_bound_fraction.as_fraction(), decision.upper_bound_fraction.as_fraction()
        threshold = Fraction(Decimal(str(decision.tolerance)))
        if low > high or decision.evidence_consistency is EvidenceConsistency.CONTRADICTORY:
            failures.append(f"{decision.threat_id}: conflicting evidence requires adjudication")
            # Do not manufacture a valid interval from contradictory evidence.
            continue
        records = [evidence[eid] for eid in decision.evidence_ids if eid in evidence]
        if not records or not any(e.can_block or e.can_clear for e in records):
            failures.append(f"{decision.threat_id}: missing admissible decision evidence")
        if decision.resolution.missing_obligations:
            failures.append(f"{decision.threat_id}: missing obligations: " + "; ".join(decision.resolution.missing_obligations))
        battery = decision.ceiling_attack_battery
        if battery.mode is CeilingAttackBatteryMode.REQUIRED and not battery.satisfied:
            failures.append(f"{decision.threat_id}: required attack battery is incomplete")
        if low > threshold:
            failures.append(f"{decision.threat_id}: demonstrated floor exceeds threshold; evidence=" + ",".join(decision.evidence_ids))
        if high <= threshold and decision.verdict is not Verdict.CLEAR:
            failures.append(f"{decision.threat_id}: a non-clearing assessment cannot be promoted by its interval alone")
        crossing = low <= threshold < high
        # No current producer verifies a prospective plan's estimand, procedure,
        # fresh allocation, availability and decision-changing target together.
        # A recognized code and generic recollection text are not that proof.
        # Retain suggestions in the assessment; refuse outward INCONCLUSIVE
        # until a bound plan verifier exists. Explicit acceptance is independent
        # of whether a measurement can resolve the remaining uncertainty.
        code = None
        intervals.append(ThreatRiskInterval(threat_id=decision.threat_id, metric=str(decision.decision_metric),
            game_sha256=decision.decision_game_sha256, floor=_prob(low), ceiling=_prob(high), gap=_prob(high-low),
            threshold=_prob(threshold), evidence_ids=decision.evidence_ids, decision_flips_in_gap=crossing,
            resolution_code=code, resolving_actions=decision.resolution.actions if code else ()))
    crossing = {t.threat_id: t.ceiling for t in intervals if t.decision_flips_in_gap}
    if acceptance is not None:
        acceptance = ResidualRiskAcceptance.model_validate(acceptance.model_dump(mode="json"))
        if not scope.residual_risk_acceptance_permitted or not crossing:
            failures.append("residual-risk acceptance is not permitted or no interval crosses")
        if acceptance.context_sha256 != context or acceptance.accepted_ceilings != crossing:
            failures.append("acceptance must bind this context and every crossing threat's exact ceiling")
        if not acceptance.issued_at <= now < acceptance.expires_at:
            failures.append("residual-risk acceptance is future-dated or expired")
        try:
            _verify_signature("MRA-RESIDUAL-RISK-ACCEPTANCE/1", acceptance.model_dump(mode="json", exclude={"signature_b64"}),
                              acceptance.signature_b64, acceptance.signer_key_id, trusted_acceptors or {})
        except Exception as exc:
            failures.append(f"invalid residual-risk signature: {type(exc).__name__}")
    if failures:
        verdict = AssuranceVerdict.BLOCK
    elif not crossing:
        verdict = AssuranceVerdict.RELEASE
    elif acceptance is not None:
        verdict = AssuranceVerdict.RELEASE_WITH_RISK
    else:
        failures.append(UNVERIFIED_RESOLVING_PLAN)
        verdict = AssuranceVerdict.BLOCK
    expiry = min(t for t in (scope.expires_at, report.policy_expires_at, report.release_expires_at,
                             acceptance.expires_at if acceptance else None) if t is not None)
    return ReleaseAssuranceRecord(release_id=report.release_id, context_sha256=context, request_sha256=_hash(request),
        assessment_sha256=_hash(report), scope_sha256=_hash(scope), created_at=now, expires_at=expiry,
        verdict=verdict, threats=tuple(intervals), blocking_reasons=tuple(failures),
        accepted_residual_risks=tuple(sorted(crossing)) if verdict is AssuranceVerdict.RELEASE_WITH_RISK else (), acceptance=acceptance)


def sign_assurance_record(record: ReleaseAssuranceRecord, private_key_path: Path) -> SignedReleaseAssuranceRecord:
    record = ReleaseAssuranceRecord.model_validate(record.model_dump(mode="json"))
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 private key required")
    key_id = signer_key_id(key.public_key())
    payload = {"record": record.model_dump(mode="json"), "signer_key_id": key_id, "schema_version": "1.0"}
    signature = key.sign(_signed_bytes("MRA-ASSURANCE-RECORD/1", payload))
    return SignedReleaseAssuranceRecord(record=record, signer_key_id=key_id, signature_b64=base64.b64encode(signature).decode("ascii"))


def sign_residual_risk_acceptance(record: ReleaseAssuranceRecord, private_key_path: Path, *,
                                  reason: str, expires_at: datetime, as_of: datetime | None = None) -> ResidualRiskAcceptance:
    """An explicit authority action, never automatically invoked by assessment."""
    record = ReleaseAssuranceRecord.model_validate(record.model_dump(mode="json"))
    actionable = record.verdict is AssuranceVerdict.INCONCLUSIVE and not record.blocking_reasons
    unplanned = (record.verdict is AssuranceVerdict.BLOCK
                 and record.blocking_reasons == (UNVERIFIED_RESOLVING_PLAN,))
    if not (actionable or unplanned):
        raise ValueError("only an otherwise complete crossing record can be accepted")
    now = as_of or datetime.now(timezone.utc)
    if (now.utcoffset() is None or expires_at.utcoffset() is None
            or not record.created_at <= now < expires_at <= record.expires_at):
        raise ValueError("acceptance must be time-qualified and expire within the record lifetime")
    ceilings = {t.threat_id: t.ceiling for t in record.threats if t.decision_flips_in_gap}
    if not ceilings:
        raise ValueError("no crossing risks to accept")
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 private key required")
    draft = ResidualRiskAcceptance(context_sha256=record.context_sha256, accepted_ceilings=ceilings,
        reason=reason, issued_at=now, expires_at=expires_at, signer_key_id=signer_key_id(key.public_key()), signature_b64="unsigned")
    signature = key.sign(_signed_bytes("MRA-RESIDUAL-RISK-ACCEPTANCE/1", draft.model_dump(mode="json", exclude={"signature_b64"})))
    return draft.model_copy(update={"signature_b64": base64.b64encode(signature).decode("ascii")})


def gate_assurance_record(signed: SignedReleaseAssuranceRecord, request: AssessmentRequest, report: AssessmentReport,
                          scope: AssuranceScope, *, policy_bytes: bytes, trusted_record_keys: Mapping[str, Path],
                          trusted_acceptors: Mapping[str, Path] | None = None,
                          as_of: datetime | None = None) -> AssuranceGateResult:
    """Consume a signed verdict and independently replay it; all errors deny passage."""
    now = as_of or datetime.now(timezone.utc)
    try:
        signed = SignedReleaseAssuranceRecord.model_validate(signed.model_dump(mode="json"))
        record = signed.record
        if now.utcoffset() is None or not record.created_at <= now < record.expires_at:
            raise ValueError("record is future-dated, expired, or time is unqualified")
        _verify_signature("MRA-ASSURANCE-RECORD/1", signed.model_dump(mode="json", exclude={"signature_b64"}),
                          signed.signature_b64, signed.signer_key_id, trusted_record_keys)
        replay = build_assurance_record(request, report, scope, policy_bytes=policy_bytes, as_of=record.created_at,
                                        acceptance=record.acceptance, trusted_acceptors=trusted_acceptors)
        if canonical_json_bytes(replay) != canonical_json_bytes(record):
            raise ValueError("signed assurance record disagrees with independent semantic replay")
        # Recheck source and acceptance freshness at the current gate time too.
        current = build_assurance_record(request, report, scope, policy_bytes=policy_bytes, as_of=now,
                                         acceptance=record.acceptance, trusted_acceptors=trusted_acceptors)
        if current.verdict != record.verdict:
            raise ValueError("assurance disposition is no longer current")
        passed = record.verdict in (AssuranceVerdict.RELEASE, AssuranceVerdict.RELEASE_WITH_RISK)
        return AssuranceGateResult(verdict=record.verdict, recommendation_passed=passed,
                                   reasons=record.blocking_reasons or ("signed disposition replayed; external authorization is still required",))
    except Exception as exc:
        return AssuranceGateResult(verdict=AssuranceVerdict.BLOCK, recommendation_passed=False,
                                   reasons=(f"assurance verification failed: {type(exc).__name__}: {exc}",))
