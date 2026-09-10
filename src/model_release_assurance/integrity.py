from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel, ValidationError

from .errors import IntegrityError

if TYPE_CHECKING:
    from .models import AssessmentReport, AssessmentRequest, PolicyBundle, ReleaseContract, SignedManifest


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    # Required-explicit nullable contract fields are part of the governed
    # representation and therefore of its digest. Callers supplying a raw dict
    # remain responsible for providing the complete validated representation.
    raw = value.model_dump(mode="json", exclude_none=False) if isinstance(value, BaseModel) else value

    def encode_special(item: Any) -> Any:
        if isinstance(item, (datetime, date)):
            return item.isoformat().replace("+00:00", "Z")
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"cannot canonically encode {type(item).__name__}")

    return json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=encode_special,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_release_artifact(contract: ReleaseContract, base_dir: Path) -> Path:
    path = Path(contract.artifact_path)
    resolved = path if path.is_absolute() else base_dir / path
    resolved = resolved.resolve(strict=True)
    if not resolved.is_file():
        raise IntegrityError(f"artifact is not a regular file: {resolved}")
    actual = sha256_file(resolved)
    if actual != contract.artifact_sha256:
        raise IntegrityError(f"artifact hash mismatch: expected {contract.artifact_sha256}, got {actual}")
    return resolved


def verify_source_file(source_path: str, expected_sha256: str, base_dir: Path) -> Path:
    path = Path(source_path)
    resolved = path if path.is_absolute() else base_dir / path
    resolved = resolved.resolve(strict=True)
    if not resolved.is_file():
        raise IntegrityError(f"evidence source is not a regular file: {resolved}")
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise IntegrityError(f"evidence source hash mismatch for {resolved}: expected {expected_sha256}, got {actual}")
    return resolved


def read_verified_source_bytes(source_path: str, expected_sha256: str, base_dir: Path) -> bytes:
    """Return the exact captured bytes whose digest was verified.

    Parsing the returned immutable value avoids the hash-then-reopen race of a
    verified pathname. This does not freeze the file for other readers or prove
    continuing custody of a deployed artifact.
    """
    path = Path(source_path)
    resolved = path if path.is_absolute() else base_dir / path
    resolved = resolved.resolve(strict=True)
    if not resolved.is_file():
        raise IntegrityError(f"evidence source is not a regular file: {resolved}")
    captured = resolved.read_bytes()
    actual = sha256_bytes(captured)
    if actual != expected_sha256:
        raise IntegrityError(f"evidence source hash mismatch for {resolved}: expected {expected_sha256}, got {actual}")
    return captured


def verify_provenance_binding(
    value: BaseModel,
    source_path: Path,
    bound_fields: tuple[str, ...],
    *,
    require_complete: bool = False,
    source_bytes: bytes | None = None,
    expected_sha256: str | None = None,
) -> None:
    """Compare a claim to captured source JSON, optionally checking its digest.

    Clearance-critical callers must supply an expected digest and preferably
    bytes from read_verified_source_bytes. Path-only calls remain available for
    legacy structural comparisons, but do not authenticate source content.
    """
    captured = source_path.read_bytes() if source_bytes is None else source_bytes
    if expected_sha256 is not None and sha256_bytes(captured) != expected_sha256:
        raise IntegrityError(f"evidence source hash mismatch for {source_path}")
    try:
        source = json.loads(captured.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"evidence source is not valid UTF-8 JSON: {source_path}") from exc
    if not isinstance(source, dict):
        raise IntegrityError("evidence source must be a JSON object")
    claimed = value.model_dump(
        mode="json",
        exclude={"provenance"} if require_complete else None,
        exclude_none=not require_complete,
    )
    if require_complete:
        required_fields = set(claimed)
        supplied_fields = set(bound_fields)
        if supplied_fields != required_fields:
            missing = sorted(required_fields - supplied_fields)
            extra = sorted(supplied_fields - required_fields)
            raise IntegrityError(
                "provenance bound_fields must equal the framework-owned analyzer payload; "
                f"missing={missing}, extra={extra}"
            )
        if set(source) != required_fields:
            missing = sorted(required_fields - set(source))
            extra = sorted(set(source) - required_fields)
            raise IntegrityError(
                "evidence source must contain exactly the framework-owned analyzer payload; "
                f"missing={missing}, extra={extra}"
            )
    for field in bound_fields:
        if field not in claimed:
            raise IntegrityError(f"bound field {field!r} is absent from the claimed payload")
        if field not in source:
            raise IntegrityError(f"bound field {field!r} is absent from the evidence source")
        if claimed[field] != source[field]:
            raise IntegrityError(f"bound field {field!r} differs between analyzer input and evidence source")


def generate_ed25519_keypair(private_path: Path, public_path: Path) -> None:
    if private_path.exists() or public_path.exists():
        raise IntegrityError("refusing to overwrite an existing signing key")
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    private_path.chmod(0o600)
    public_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _load_private(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise IntegrityError("private key is not Ed25519")
    return key


def _load_public(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise IntegrityError("public key is not Ed25519")
    return key


def signer_key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sha256_bytes(raw)[:24]


def sign_canonical(value: BaseModel | dict[str, Any], private_key_path: Path) -> tuple[str, str]:
    """Sign canonical MRA JSON and return the signer identifier and Base64 signature."""
    private_key = _load_private(private_key_path)
    signature = private_key.sign(canonical_json_bytes(value))
    return signer_key_id(private_key.public_key()), base64.b64encode(signature).decode("ascii")


def verify_canonical_signature(
    value: BaseModel | dict[str, Any],
    *,
    signer_id: str,
    signature_b64: str,
    public_key_path: Path,
) -> None:
    """Verify a canonical MRA JSON signature and its signer-key binding."""
    public_key = _load_public(public_key_path)
    if signer_id != signer_key_id(public_key):
        raise IntegrityError("signer key identifier mismatch")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, canonical_json_bytes(value))
    except (InvalidSignature, ValueError, binascii.Error) as exc:
        raise IntegrityError("manifest signature verification failed") from exc


def _validated_report(report: AssessmentReport) -> AssessmentReport:
    from .models import AssessmentReport

    try:
        return AssessmentReport.model_validate(report.model_dump(mode="python"))
    except (ValidationError, ValueError) as exc:
        raise IntegrityError(f"assessment report contract is invalid: {exc}") from exc


def _validate_report_freshness(report: AssessmentReport, as_of: datetime | None) -> datetime:
    now = as_of or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise IntegrityError("assessment verification time must include a timezone offset")
    # Match the engine's explicit allowance for independently timestamped workers.
    skew = timedelta(minutes=5)
    if report.created_at > now + skew:
        raise IntegrityError("assessment report created_at is implausibly in the future")
    for label, expiry in (("release", report.release_expires_at), ("policy", report.policy_expires_at)):
        if expiry is not None and (report.created_at >= expiry or now >= expiry):
            raise IntegrityError(f"assessment report {label} has expired")
    if any(record.observed_at > report.created_at + skew for record in report.evidence):
        raise IntegrityError("assessment report predates its evidence observations")
    if any(
        expiry is not None and record.observed_at >= expiry
        for record in report.evidence
        for expiry in (report.release_expires_at, report.policy_expires_at)
    ):
        raise IntegrityError("assessment evidence was observed after release or policy expiry")
    return now


def validate_report_against_policy(
    report: AssessmentReport,
    policy: PolicyBundle,
    *,
    policy_sha256: str,
    request: AssessmentRequest | None = None,
    as_of: datetime | None = None,
) -> None:
    """Check report semantics against an already hash-verified active policy.

    This performs no file reads and does not authenticate the caller's policy.
    Supply the original request for game/input/reduction and battery-policy
    replay. Report-only validation cannot reconstruct anonymous game inputs.
    """
    from .models import AssessmentRequest, AttackBatteryInput, CeilingAttackBatteryMode, PolicyBundle

    report = _validated_report(report)
    try:
        policy = PolicyBundle.model_validate(policy.model_dump(mode="python"))
    except (ValidationError, ValueError) as exc:
        raise IntegrityError(f"assessment policy contract is invalid: {exc}") from exc
    now = _validate_report_freshness(report, as_of)
    if (report.policy_id, report.policy_version, report.policy_sha256) != (
        policy.policy_id, policy.policy_version, policy_sha256
    ):
        raise IntegrityError("assessment report does not bind the active policy identity and hash")
    if report.policy_expires_at != policy.expires_at:
        raise IntegrityError("assessment report policy expiry does not match the active policy")
    if policy.effective_from > now or report.created_at < policy.effective_from:
        raise IntegrityError("assessment report was not created under an effective policy")
    if policy.expires_at is not None and now >= policy.expires_at:
        raise IntegrityError("active assessment policy has expired")
    rules = {rule.threat_id: rule for rule in policy.rules}
    decisions = {decision.threat_id: decision for decision in report.decisions}
    missing = {key for key, rule in rules.items() if rule.mandatory} - decisions.keys()
    unknown = decisions.keys() - rules.keys()
    if missing or unknown:
        raise IntegrityError(f"assessment policy threat roster mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}")
    if request is not None:
        from .engine import AssuranceEngine

        validate_report_against_request(report, request, as_of=as_of)
        request = AssessmentRequest.model_validate(request.model_dump(mode="python"))
        for threat in request.threats:
            rule = rules[threat.threat_id]
            for field in ("kind", "mandatory", "decision_metric", "metric_parameters", "finite_game", "tolerance", "tolerance_basis"):
                if getattr(threat, field) != getattr(rule, field):
                    raise IntegrityError(f"assessment request threat {threat.threat_id} changes policy field {field}")
            try:
                expected_battery = AssuranceEngine._attack_battery_status(request, policy, threat.threat_id)
            except (ValueError, KeyError, StopIteration) as exc:
                raise IntegrityError(f"assessment battery policy replay failed: {exc}") from exc
            if decisions[threat.threat_id].ceiling_attack_battery != expected_battery:
                raise IntegrityError(f"assessment threat {threat.threat_id} battery differs from deterministic policy replay")
        for value in request.analyzer_inputs:
            if isinstance(value, AttackBatteryInput):
                output = value.worker_output
                if output.started_at < policy.effective_from:
                    raise IntegrityError("assessment attack worker started before the policy became effective")
                if output.completed_at > now + timedelta(minutes=5):
                    raise IntegrityError("assessment attack worker completion is implausibly in the future")
                for expiry in (policy.expires_at, request.release.expires_at):
                    if expiry is not None and output.completed_at >= expiry:
                        raise IntegrityError("assessment attack worker completed after policy or release expiry")
    requirements = {(r.threat_id, r.analyzer): r for r in policy.analyzer_requirements}
    present = {(r.threat_id, r.analyzer) for r in report.evidence}
    missing_analyzers = {
        key for key, requirement in requirements.items()
        if requirement.required and key[0] in decisions
    } - present
    if missing_analyzers:
        raise IntegrityError(f"assessment report omits policy-required analyzers: {sorted(missing_analyzers)}")
    for record in report.evidence:
        requirement = requirements.get((record.threat_id, record.analyzer))
        if requirement is None:
            raise IntegrityError("assessment report contains an analyzer not authorized by policy")
        producer = record.producer
        try:
            actual_version = tuple(int(part) for part in producer.service_version.split("."))
            minimum_version = tuple(int(part) for part in requirement.minimum_service_version.split("."))
        except ValueError as exc:
            raise IntegrityError("assessment analyzer service version is malformed") from exc
        if len(actual_version) != 3 or actual_version < minimum_version:
            raise IntegrityError("assessment analyzer service version is below policy minimum")
        if producer.implementation_sha256 not in requirement.accepted_implementation_sha256s:
            raise IntegrityError("assessment analyzer implementation is not accepted by policy")
        if producer.configuration_sha256 not in requirement.accepted_configuration_sha256s:
            raise IntegrityError("assessment analyzer configuration is not accepted by policy")
        if record.observed_at < policy.effective_from or (
            policy.expires_at is not None and record.observed_at >= policy.expires_at
        ):
            raise IntegrityError("assessment evidence was observed outside policy validity")
    batteries = {r.threat_id: r for r in policy.attack_battery_requirements}
    for threat_id, decision in decisions.items():
        rule = rules[threat_id]
        for field in ("kind", "mandatory", "decision_metric", "tolerance", "tolerance_basis"):
            if getattr(decision, field) != getattr(rule, field):
                raise IntegrityError(f"assessment threat {threat_id} changes policy field {field}")
        battery = decision.ceiling_attack_battery
        if battery.mode is not rule.ceiling_attack_battery_mode:
            raise IntegrityError(f"assessment threat {threat_id} changes the policy battery mode")
        if battery.mode is CeilingAttackBatteryMode.WAIVED:
            if battery.waiver_reason != rule.ceiling_attack_battery_waiver_reason:
                raise IntegrityError("assessment battery waiver differs from policy")
        elif battery.mode is CeilingAttackBatteryMode.REQUIRED:
            requirement = batteries[threat_id]
            if battery.requirement_id != requirement.requirement_id or set(battery.required_attack_ids) != set(requirement.required_attack_ids):
                raise IntegrityError("assessment required attack battery differs from policy")
            for attack_id in battery.completed_attack_ids:
                supports = [r for r in report.evidence if r.threat_id == threat_id
                            and r.analyzer == "attack_battery" and r.details.get("attack_id") == attack_id]
                if not supports or any(not r.can_block or r.details.get("positive_controls_passed") is not True for r in supports):
                    raise IntegrityError("completed attack lacks admissible replayed floor/control evidence")
                for record in supports:
                    controls = record.details.get("positive_control_ids")
                    bounds = record.details.get("replayed_positive_control_lower_bounds")
                    if not isinstance(controls, list) or not controls or not set(controls).issubset(battery.passing_positive_control_ids):
                        raise IntegrityError("completed attack positive-control identifiers are inconsistent")
                    if not isinstance(bounds, dict) or not set(controls).issubset(bounds):
                        raise IntegrityError("completed attack lacks replayed positive-control bounds")
                    for control_id in controls:
                        value = bounds[control_id]
                        # Expected-flag controls have no binomial bound. The request
                        # validator separately replays the typed control definition.
                        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1 or value < requirement.minimum_positive_control_detection_lower_bound):
                            raise IntegrityError("positive-control detection bound is below policy minimum")


def validate_report_against_request(
    report: AssessmentReport,
    request: AssessmentRequest,
    *,
    as_of: datetime | None = None,
) -> None:
    """Replay inline evidence and its exact request-bound reduction before use.

    No evidence/policy files are read here. Their bytes, origins, actual worker
    execution and live interface must be verified at the surrounding boundary.
    Unsupported/non-equivalent analyzer outputs fail closed on replay.
    """
    from .analyzers import (
        AttackAnalyzer, AttackBatteryAnalyzer, ControlledInferenceAnalyzer,
        DpAnalyzer, FiniteChannelCeilingAnalyzer, LlmCanaryAnalyzer,
        LlmWatermarkAnalyzer, PopulationAnalyzer, TreeLinkageAnalyzer,
    )
    from .analyzers.attack_battery import _positive_control_passes
    from .decision import decide_threat, decision_game_sha256
    from .errors import AssuranceError
    from .models import AssessmentRequest, AttackBatteryInput, CeilingAttackBatteryMode, EvidenceContext
    from .decision import population_scope_sha256

    report = _validated_report(report)
    try:
        request = AssessmentRequest.model_validate(request.model_dump(mode="python"))
    except (ValidationError, ValueError) as exc:
        raise IntegrityError(f"assessment request contract is invalid: {exc}") from exc
    _validate_report_freshness(report, as_of)
    release = request.release
    bindings = {
        "request_sha256": sha256_bytes(canonical_json_bytes(request)),
        "release_contract_sha256": sha256_bytes(canonical_json_bytes(release)),
        "release_id": release.release_id, "artifact_sha256": release.artifact_sha256,
        "release_model_family": release.model_family, "release_model_profile": release.model_profile,
        "release_interface": release.interface, "release_expires_at": release.expires_at,
        "policy_id": request.policy.policy_id, "policy_version": request.policy.policy_version,
        "policy_sha256": request.policy.policy_sha256,
    }
    for field, expected in bindings.items():
        if getattr(report, field) != expected:
            raise IntegrityError(f"report {field} does not match the assessment request")
    if report.assessment_scope.declared_previous_release_ids != release.previous_release_ids:
        raise IntegrityError("report composition lineage does not match the assessment request")
    scopes = {scope.scope_id: scope for scope in request.population_scopes}
    if {scope.scope_id: scope for scope in report.population_scopes} != scopes:
        raise IntegrityError("report population scopes do not match the assessment request")
    threats = {threat.threat_id: threat for threat in request.threats}
    decisions = {decision.threat_id: decision for decision in report.decisions}
    if set(decisions) != set(threats):
        raise IntegrityError("report threat roster does not exactly match the assessment request")
    analyzers = {a.name: a for a in (
        AttackAnalyzer(), AttackBatteryAnalyzer(), ControlledInferenceAnalyzer(),
        DpAnalyzer(), FiniteChannelCeilingAnalyzer(), LlmCanaryAnalyzer(),
        LlmWatermarkAnalyzer(), PopulationAnalyzer(), TreeLinkageAnalyzer(),
    )}
    replayed = []
    try:
        for value in request.analyzer_inputs:
            threat = threats[value.threat_id]
            scope = scopes[threat.population_scope_id]
            expected_context = EvidenceContext(
                release_id=release.release_id,
                release_contract_sha256=bindings["release_contract_sha256"],
                policy_sha256=request.policy.policy_sha256,
                artifact_sha256=release.artifact_sha256,
                interface_sha256=sha256_bytes(canonical_json_bytes(release.interface)),
                population_scope_id=scope.scope_id,
                population_scope_sha256=population_scope_sha256(scope),
                decision_game_sha256=decision_game_sha256(threat, scope),
                observed_at=value.evidence_context.observed_at,
            )
            if value.evidence_context != expected_context:
                raise IntegrityError(f"assessment request evidence context does not match the release, scope or game for {value.threat_id}")
            replayed.extend(analyzers[value.analyzer].analyze(release, threats[value.threat_id], value))
    except (AssuranceError, ValueError, KeyError, TypeError) as exc:
        raise IntegrityError(f"assessment request inline evidence replay failed: {exc}") from exc
    expected_records = {record.evidence_id: record for record in replayed}
    if len(expected_records) != len(replayed):
        raise IntegrityError("assessment request replay produced duplicate evidence identifiers")
    if {record.evidence_id: record for record in report.evidence} != expected_records:
        raise IntegrityError("assessment report evidence differs from deterministic request replay")
    for threat_id, threat in threats.items():
        decision = decisions[threat_id]
        scope = scopes[threat.population_scope_id]
        if decision.decision_game_sha256 != decision_game_sha256(threat, scope):
            raise IntegrityError(f"report threat {threat_id} does not bind the requested decision game")
        battery = decision.ceiling_attack_battery
        if battery.mode is CeilingAttackBatteryMode.REQUIRED:
            candidates = [value for value in request.analyzer_inputs
                          if isinstance(value, AttackBatteryInput) and value.threat_id == threat_id]
            if len(candidates) != 1:
                raise IntegrityError("required attack status has no unique request battery")
            source = candidates[0]
            control_results = {result.control_id: result for result in source.worker_output.positive_controls}
            try:
                passing = {control.control_id for control in source.configuration.positive_controls
                           if _positive_control_passes(control, control_results[control.control_id])[0]}
            except (AssuranceError, ValueError, KeyError) as exc:
                raise IntegrityError(f"positive-control replay failed: {exc}") from exc
            if not set(battery.passing_positive_control_ids).issubset(passing):
                raise IntegrityError("assessment claims positive controls that did not pass replay")
            for attack_id in battery.completed_attack_ids:
                plans = [plan for plan in source.configuration.runs if plan.attack_id == attack_id]
                if not plans:
                    raise IntegrityError("completed attack is absent from the frozen request battery")
                for plan in plans:
                    records = [record for record in replayed if record.threat_id == threat_id
                               and record.analyzer == "attack_battery" and record.details.get("run_id") == plan.run_id]
                    if not records or any(not record.can_block for record in records) or not set(plan.positive_control_ids).issubset(battery.passing_positive_control_ids):
                        raise IntegrityError("completed attack lacks its successful runs and passing controls")
        expected = decide_threat(threat, scope, release, report.evidence, request.policy.policy_sha256, battery)
        if decision != expected:
            raise IntegrityError(f"report threat {threat_id} differs from deterministic evidence reduction")


def build_signed_manifest(
    report: AssessmentReport,
    request: AssessmentRequest,
    private_key_path: Path,
) -> SignedManifest:
    # Kept local so the finite-channel assessment contract can reuse the
    # portfolio certificate models without creating an import cycle.
    from .models import SignedManifest

    validate_report_against_request(report, request)
    release = request.release
    if report.request_sha256 != sha256_bytes(canonical_json_bytes(request)):
        raise IntegrityError("report does not bind the supplied assessment request")
    if report.release_contract_sha256 != sha256_bytes(canonical_json_bytes(release)):
        raise IntegrityError("report does not bind the supplied release contract")
    report_bindings = {
        "release_id": release.release_id,
        "artifact_sha256": release.artifact_sha256,
        "release_interface": release.interface,
        "release_expires_at": release.expires_at,
        "policy_id": request.policy.policy_id,
        "policy_version": request.policy.policy_version,
        "policy_sha256": request.policy.policy_sha256,
    }
    for field, expected in report_bindings.items():
        if getattr(report, field) != expected:
            raise IntegrityError(f"report {field} does not match the assessment request")
    release_interface_sha256 = sha256_bytes(canonical_json_bytes(release.interface))
    if any(
        decision.assessed_interface_sha256 != release_interface_sha256
        for decision in report.decisions
    ):
        raise IntegrityError("report decisions do not bind the assessment interface")
    if report.assessment_scope.declared_previous_release_ids != release.previous_release_ids:
        raise IntegrityError("report composition lineage does not match the assessment request")
    private_key = _load_private(private_key_path)
    unsigned = {
        "schema_version": "4.0",
        "assessment_id": report.assessment_id,
        "release_id": report.release_id,
        "policy_id": report.policy_id,
        "policy_version": report.policy_version,
        "policy_sha256": report.policy_sha256,
        "artifact_sha256": report.artifact_sha256,
        "release_interface_sha256": release_interface_sha256,
        "request_sha256": report.request_sha256,
        "report_sha256": sha256_bytes(canonical_json_bytes(report)),
        "overall_verdict": report.overall_verdict,
        "composition_scope": report.assessment_scope.composition_scope,
        "interface_assurance": report.assessment_scope.interface_assurance,
        "authorization_eligible": report.assessment_scope.authorization_eligible,
        "created_at": report.created_at,
        "signer_key_id": signer_key_id(private_key.public_key()),
        "signature_algorithm": "Ed25519",
        "canonicalization": "MRA-PY-JSON-1",
    }
    if report.release_expires_at is not None:
        unsigned["expires_at"] = report.release_expires_at
    signature = private_key.sign(canonical_json_bytes(unsigned))
    return SignedManifest(**unsigned, signature_b64=base64.b64encode(signature).decode("ascii"))


def verify_signed_manifest(
    manifest: SignedManifest,
    report: AssessmentReport,
    public_key_path: Path,
    *,
    request: AssessmentRequest | None = None,
    as_of: datetime | None = None,
) -> None:
    from .models import SignedManifest

    try:
        manifest = SignedManifest.model_validate(manifest.model_dump(mode="python"))
    except (ValidationError, ValueError) as exc:
        raise IntegrityError(f"assessment manifest contract is invalid: {exc}") from exc
    report = _validated_report(report)
    _validate_report_freshness(report, as_of)
    if request is not None:
        validate_report_against_request(report, request, as_of=as_of)
    public_key = _load_public(public_key_path)
    if manifest.signer_key_id != signer_key_id(public_key):
        raise IntegrityError("signer key identifier mismatch")
    release_interface_sha256 = sha256_bytes(
        canonical_json_bytes(report.release_interface)
    )
    if any(
        decision.assessed_interface_sha256 != release_interface_sha256
        for decision in report.decisions
    ):
        raise IntegrityError("report decisions do not bind the report interface")
    expected_bindings = {
        "assessment_id": report.assessment_id,
        "release_id": report.release_id,
        "policy_id": report.policy_id,
        "policy_version": report.policy_version,
        "policy_sha256": report.policy_sha256,
        "artifact_sha256": report.artifact_sha256,
        "release_interface_sha256": release_interface_sha256,
        "request_sha256": report.request_sha256,
        "overall_verdict": report.overall_verdict,
        "composition_scope": report.assessment_scope.composition_scope,
        "interface_assurance": report.assessment_scope.interface_assurance,
        "authorization_eligible": report.assessment_scope.authorization_eligible,
        "created_at": report.created_at,
    }
    for field, expected in expected_bindings.items():
        if getattr(manifest, field) != expected:
            raise IntegrityError(f"manifest {field} does not match the report")
    if manifest.expires_at != report.release_expires_at:
        raise IntegrityError("manifest expiry does not match the report release expiry")
    if manifest.report_sha256 != sha256_bytes(canonical_json_bytes(report)):
        raise IntegrityError("manifest does not bind this report")
    if manifest.expires_at is not None and manifest.expires_at <= (as_of or datetime.now(timezone.utc)):
        raise IntegrityError("manifest has expired")
    unsigned = manifest.model_dump(mode="json", exclude={"signature_b64"}, exclude_none=True)
    try:
        public_key.verify(base64.b64decode(manifest.signature_b64, validate=True), canonical_json_bytes(unsigned))
    except (InvalidSignature, ValueError, binascii.Error) as exc:
        raise IntegrityError("manifest signature verification failed") from exc
