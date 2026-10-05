"""Fresh native-replay evidence bound to a checked retained SACRO comparison.

The signature authenticates local verification and exact retained bytes under a
new ephemeral fixture key. It does not attest SACRO's external execution, the
original training, an isolated worker, scientific validity or release authority.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import time
import uuid

from .execution import MAX_INPUT, MAX_OUTPUT, source_snapshot
from .worker import validate_request
from .workflow import FLAGS as COMPARISON_FLAGS, expected_binding, verify_worker
from .protocol import prepare_input, frozen_splits
from .runtime import ATTACK_PARAMETERS
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes as artifact_bytes, strict_json, parse_plan
from ..production_evidence.contracts import (EvidenceError, OBSERVATIONS, canonical_bytes,
                                            digest, validate_context)
from ..production_evidence.ledger import ReplayLedger
from ..production_evidence.replay import snapshot_native_bundle, artifact_manifest
from ..production_evidence.signing import MemoryFixtureEvidenceSigner
from ..production_evidence.verifier import LocalEvidenceVerifier, runtime_observation
from ..production_trust.registry import FixtureTrustRegistry, TrustProfile

FLAGS = {**native.FLAGS, "assessment_eligible": False, "external_execution_attested": False,
         "original_training_attested": False, "agency_trust_established": False}
POLICY = {"schema": "mra-sacro-bound-replay-policy/v1", "environment": "public_fixture",
          "operation": "retained_native_replay", "required_profile": "local_public_replay",
          "signature_scope": "local_native_replay_bound_to_retained_comparison_bytes",
          "external_execution_attested": False, "production_authorized": False}
FILES = {"input.json": MAX_INPUT, "plan.json": 2 * 1024 * 1024,
         "worker/worker.json": MAX_OUTPUT, "worker/process.json": 65536,
         "comparison.json": MAX_OUTPUT, "result.json": MAX_OUTPUT}


def _fail():
    raise EvidenceError("Bound comparison replay rejected")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _same(left, right):
    return artifact_bytes(left) == artifact_bytes(right)


def _write(path, value):
    with path.open("xb") as stream:
        stream.write(canonical_bytes(value) + b"\n")


def _read_comparison(root):
    return {name: native._read(root / name, bound) for name, bound in FILES.items()}


def _process(value, request, input_raw):
    fields = {"status", "input_sha256", "source_sha256", "runtime_descriptor", "exit_code",
              "cleanup_confirmed", "stdout_bytes", "stderr_bytes", "elapsed_seconds",
              "hostile_code_isolated", "network_isolated", "filesystem_isolated", "resource_limits_verified"}
    if type(value) is not dict or set(value) != fields:
        _fail()
    fixed = {"status": "completed", "input_sha256": _sha(input_raw), "source_sha256": request["source_sha256"],
             "exit_code": 0, "cleanup_confirmed": True, "hostile_code_isolated": False,
             "network_isolated": False, "filesystem_isolated": False, "resource_limits_verified": False}
    if not _same({key: value[key] for key in fixed}, fixed):
        _fail()
    for key in ("stdout_bytes", "stderr_bytes"):
        if type(value[key]) is not int or not 0 <= value[key] <= 65536:
            _fail()
    elapsed = value["elapsed_seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= 3600:
        _fail()
    descriptor = value["runtime_descriptor"]
    names = {"python", "launcher_sha256", "base_python", "base_sha256", "site_packages", "configuration_sha256"}
    if type(descriptor) is not dict or set(descriptor) != names:
        _fail()
    for key, item in descriptor.items():
        if type(item) is not str or not 1 <= len(item) <= 4096:
            _fail()
        if key.endswith("sha256") and (len(item) != 64 or any(char not in "0123456789abcdef" for char in item)):
            _fail()


def _capture(native_root, comparison_root):
    source = source_snapshot()
    native_blobs = snapshot_native_bundle(native_root)
    prepared = prepare_input(native_blobs)  # Includes independent numeric replay.
    raw = _read_comparison(comparison_root)
    values = {name: strict_json(value, maximum=FILES[name]) for name, value in raw.items()}
    request = values["input.json"]
    checked = validate_request(request)
    if not _same(checked, prepared) or request["source_sha256"] != digest(source):
        _fail()
    expected_plan = {"schema": "mra-sacro-frozen-comparison/v1", "prepared_sha256": _sha(artifact_bytes(prepared)),
        "source_sha256": digest(source), "lock_sha256": request["lock_sha256"], "runtime_binding": expected_binding(),
        "runtime_versions": request["versions"], "attack_parameters": dict(ATTACK_PARAMETERS),
        "protocol": prepared["protocol"], "splits": frozen_splits(prepared),
        "required_cases": ["target", "positive", "null"], **COMPARISON_FLAGS}
    if not _same(values["plan.json"], expected_plan):
        _fail()
    worker = values["worker/worker.json"]
    compared = verify_worker(prepared, request, worker)
    if not _same(compared, values["comparison.json"]):
        _fail()
    process = values["worker/process.json"]
    _process(process, request, raw["input.json"])
    expected_result = {"schema": "mra-sacro-comparison/v1", "profile_id": prepared["profile_id"],
        "status": "completed", "error": None, "comparison": compared, "process": process,
        "plan_sha256": _sha(artifact_bytes(expected_plan)), "prepared_sha256": _sha(artifact_bytes(prepared)),
        "worker_output_sha256": _sha(artifact_bytes(worker)), **COMPARISON_FLAGS}
    if not _same(values["result.json"], expected_result):
        _fail()
    manifest = artifact_manifest(native_blobs)
    bindings = {"schema": "mra-sacro-retained-bindings/v1", "profile_id": prepared["profile_id"],
        "comparison_files": {name: {"sha256": _sha(value), "size_bytes": len(value)} for name, value in raw.items()},
        "native_artifacts": manifest, "source_sha256": digest(source), "policy_sha256": digest(POLICY),
        "external_execution_attested": False}
    if source_snapshot() != source:
        _fail()
    return source, native_blobs, raw, bindings


def authenticate_comparison(native_root, comparison_root, *, output):
    """Authenticate one fresh replay; every production/release flag stays false.

    Inputs are retained trusted-local fixture outputs, not a submission API.
    Initial invalid inputs are rejected before creating output. Later failures
    retain a generic failed receipt and any already-written public evidence.
    No caller-supplied signing key, observer or external attestation is accepted.
    """
    destination = registry = signer = None
    revoked = False
    try:
        native_root, comparison_root = Path(native_root).absolute(), Path(comparison_root).absolute()
        output_path = Path(output).absolute()
        if output_path == native_root or native_root in output_path.parents:
            _fail()  # Retained native bundles must never receive new evidence files.
        source, blobs, raw, bindings = _capture(native_root, comparison_root)
        plan = parse_plan(blobs["plan.json"])
        observed_runtime = runtime_observation()
        context = validate_context({"schema": "mra-execution-context/v1", "environment": "public_fixture",
            "operation": "retained_native_replay", "agency_id": "public-fixture", "project_id": "sacro-comparison",
            "case_id": bindings["profile_id"], "worker_id": "local-native-replay", "job_id": uuid.uuid4().hex,
            "attempt_id": uuid.uuid4().hex, "fence": 1, "job_sha256": digest(bindings),
            "source_sha256": plan.source_sha256, "policy_sha256": digest(POLICY),
            "plan_sha256": _sha(blobs["plan.json"]), "adapter_sha256": plan.implementation_sha256,
            "runtime_sha256": digest(observed_runtime), "image_sha256": None})

        def observe():
            if (source_snapshot() != source or _read_comparison(comparison_root) != raw
                    or not _same(artifact_manifest(snapshot_native_bundle(native_root)), bindings["native_artifacts"])
                    or runtime_observation() != observed_runtime):
                _fail()
            return copy.deepcopy(context)

        observe()  # Close changes during initial semantic verification before output creation.
        destination = native._new_output(output)
        now = int(time.time())
        profile = TrustProfile("public-fixture", "public_fixture", "https://sacro-fixture.invalid",
                               "urn:mra:sacro-bound-replay", "worker_evidence")
        registry = FixtureTrustRegistry(now=lambda: int(time.time()), fresh_until=now + 300)
        signer = MemoryFixtureEvidenceSigner(profile, context["worker_id"], "sacro-replay-" + uuid.uuid4().hex, now, now + 300)
        registry.enroll(signer.registration, expected_revision=registry.revision)
        ledger = ReplayLedger.create(destination / "ledger")
        verifier = LocalEvidenceVerifier(registry, profile, context["worker_id"], ledger)
        challenge = verifier.issue(context, current_context=observe, ttl_seconds=120)
        statement = {"schema": "mra-worker-evidence/v1", "context": context, "challenge": challenge,
            "artifacts": bindings["native_artifacts"], "observations": dict(OBSERVATIONS),
            "issued_at": registry.current_time(), "expires_at": challenge["expires_at"]}
        envelope = signer.sign(statement, registry)
        _write(destination / "policy.json", POLICY)
        _write(destination / "bindings.json", bindings)
        _write(destination / "context.json", context)
        _write(destination / "challenge.json", challenge)
        with (destination / "envelope.json").open("xb") as stream:
            stream.write(envelope)
        with (destination / "public-key.pem").open("xb") as stream:
            stream.write(signer.registration.public_key_pem)
        admission = verifier.accept(envelope, expected_context=context, artifact_root=native_root,
                                    current_context=observe, required_profile="local_public_replay")
        observe()
        _write(destination / "admission.json", admission)
        registry.revoke(signer.registration.key_id, expected_revision=registry.revision)
        revoked = True
        result = {"schema": "mra-sacro-bound-replay/v1", "status": "accepted_bound_native_replay",
            "profile_id": bindings["profile_id"], "bindings_sha256": digest(bindings),
            "context_sha256": digest(context), "envelope_sha256": _sha(envelope),
            "admission_sha256": digest(admission), "key_fingerprint": signer.registration.fingerprint,
            "fixture_key_revoked": True, "ledger_id": challenge["ledger_id"],
            "signature_scope": POLICY["signature_scope"], **FLAGS}
        _write(destination / "result.json", result)
        return result
    except Exception:
        if destination is not None:
            try:
                _write(destination / "result.json", {"schema": "mra-sacro-bound-replay/v1", "status": "failed",
                        "error": "bound_comparison_replay_rejected", **FLAGS})
            except Exception:
                pass
        raise EvidenceError("Bound comparison replay rejected") from None
    finally:
        if registry is not None and signer is not None and not revoked:
            try:
                registry.revoke(signer.registration.key_id, expected_revision=registry.revision)
            except Exception:
                pass  # No successful receipt exists; the private key is never persisted.
