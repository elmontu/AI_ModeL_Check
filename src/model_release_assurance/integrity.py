from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel

from .errors import IntegrityError
from .models import AssessmentReport, AssessmentRequest, ReleaseContract, SignedManifest


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    raw = value.model_dump(mode="json", exclude_none=True) if isinstance(value, BaseModel) else value

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


def verify_provenance_binding(
    value: BaseModel,
    source_path: Path,
    bound_fields: tuple[str, ...],
    *,
    require_complete: bool = False,
) -> None:
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
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


def build_signed_manifest(
    report: AssessmentReport,
    request: AssessmentRequest,
    private_key_path: Path,
) -> SignedManifest:
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
    private_key = _load_private(private_key_path)
    unsigned = {
        "schema_version": "1.0",
        "assessment_id": report.assessment_id,
        "release_id": report.release_id,
        "policy_id": report.policy_id,
        "policy_version": report.policy_version,
        "policy_sha256": report.policy_sha256,
        "artifact_sha256": report.artifact_sha256,
        "request_sha256": report.request_sha256,
        "report_sha256": sha256_bytes(canonical_json_bytes(report)),
        "overall_verdict": report.overall_verdict,
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
) -> None:
    public_key = _load_public(public_key_path)
    if manifest.signer_key_id != signer_key_id(public_key):
        raise IntegrityError("signer key identifier mismatch")
    expected_bindings = {
        "assessment_id": report.assessment_id,
        "release_id": report.release_id,
        "policy_id": report.policy_id,
        "policy_version": report.policy_version,
        "policy_sha256": report.policy_sha256,
        "artifact_sha256": report.artifact_sha256,
        "request_sha256": report.request_sha256,
        "overall_verdict": report.overall_verdict,
        "created_at": report.created_at,
    }
    for field, expected in expected_bindings.items():
        if getattr(manifest, field) != expected:
            raise IntegrityError(f"manifest {field} does not match the report")
    if manifest.expires_at != report.release_expires_at:
        raise IntegrityError("manifest expiry does not match the report release expiry")
    if manifest.report_sha256 != sha256_bytes(canonical_json_bytes(report)):
        raise IntegrityError("manifest does not bind this report")
    if manifest.expires_at is not None and manifest.expires_at <= datetime.now(timezone.utc):
        raise IntegrityError("manifest has expired")
    unsigned = manifest.model_dump(mode="json", exclude={"signature_b64"}, exclude_none=True)
    try:
        public_key.verify(base64.b64decode(manifest.signature_b64, validate=True), canonical_json_bytes(unsigned))
    except (InvalidSignature, ValueError, binascii.Error) as exc:
        raise IntegrityError("manifest signature verification failed") from exc
