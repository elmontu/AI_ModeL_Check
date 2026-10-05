#!/usr/bin/env python3
"""Authenticate fresh local replay operations over public native adapter bundles.

Keys remain in memory. Output is fresh ignored .local evidence. This command
cannot qualify production isolation, attest original training or release a model.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import uuid

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("mra_execution_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)

from model_release_assurance.production_adapters import native
from model_release_assurance.production_evidence.contracts import (EvidenceError, OBSERVATIONS, canonical_bytes, digest)
from model_release_assurance.production_evidence.ledger import ReplayLedger
from model_release_assurance.production_evidence.replay import (artifact_manifest, replay_native_bundle, snapshot_native_bundle)
from model_release_assurance.production_evidence.signing import MemoryFixtureEvidenceSigner, verify_envelope
from model_release_assurance.production_evidence.verifier import FLAGS, LocalEvidenceVerifier, runtime_observation
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile

PROFILES = ("acs", "bts", "hmda", "tlc", "sklearn-breast-cancer", "sklearn-wine", "sklearn-digits", "sklearn-diabetes")
POLICY = {"schema": "mra-local-replay-policy/v1", "operation": "retained_native_replay",
          "admission_profile": "local_public_replay", "original_training_attested": False,
          "production_authorized": False, "artifact_contract": "native.tabular-loss/v1"}
SOURCE_FILES = ("scripts/rehearse_execution_evidence.py", "scripts/verify_build_baseline.py",
                "pyproject.toml", "requirements.lock", "deploy/build/windows-cp312.json")
REQUIRED_CHECKS = frozenset({"signature_tampering_rejected", "changed_policy_rejected",
    "changed_source_rejected", "changed_runtime_rejected", "changed_job_rejected",
    "changed_plan_rejected", "changed_image_rejected", "production_isolation_required",
    "valid_local_replay_accepted", "replay_rejected", "restart_replay_rejected",
    "fresh_nonce_same_execution_rejected", "revoked_signer_rejected"})


def _write(path, value):
    path.write_bytes(canonical_bytes(value) + b"\n")


def source_snapshot(root):
    root = Path(root).absolute()
    names = set(SOURCE_FILES)
    names.update(p.relative_to(root).as_posix() for p in (root / "src/model_release_assurance").rglob("*.py"))
    if not 4 < len(names) <= 256:
        raise EvidenceError("Rehearsal source inventory is invalid")
    return {name: hashlib.sha256(_BASELINE._read_file(root, name)).hexdigest() for name in sorted(names)}


def runtime_snapshot():
    return runtime_observation()


def _denied(call):
    try:
        call()
    except (EvidenceError, RuntimeError):
        return True
    return False


def _fixture(output):
    from sklearn.datasets import load_wine
    sample = load_wine()
    source = digest({"source": "sklearn-bundled-wine", "x": sample.data.tolist(), "y": sample.target.tolist()})
    result = native.run_native(sample.data, sample.target, dataset_id="sklearn-wine",
        source_sha256=source, feature_names=list(sample.feature_names), output=output)
    if result["status"] != "completed":
        raise EvidenceError("Native public fixture did not complete")
    return {"sklearn-wine": output}


def _existing_cases(root, benchmark):
    path = Path(benchmark)
    if not path.is_absolute():
        path = root / path
    if ".." in path.parts or not path.is_relative_to(root / ".local"):
        raise EvidenceError("Existing benchmark must be inside government .local")
    _BASELINE._checked_path(root, path.relative_to(root).as_posix())
    # The caller selects retained public benchmark material. No claim is made
    # that local files or historical training are independently authenticated.
    return {name: path / "cases" / name for name in PROFILES}


def exercise_case(root, output, source_root, name, frozen_source, ledger, registry, profile, signer):
    output.mkdir()
    blobs = snapshot_native_bundle(source_root)
    plan = json.loads(blobs["plan.json"])
    frozen_runtime = runtime_snapshot()
    job = {"schema": "mra-replay-job/v1", "operation": "retained_native_replay", "profile": name,
           "input_artifacts": artifact_manifest(blobs), "code_sha256": digest(frozen_source)}
    context = {"schema": "mra-execution-context/v1", "operation": "retained_native_replay",
        "environment": "public_fixture", "agency_id": profile.agency_id, "project_id": "cross-sector-fixture",
        "case_id": name, "job_id": uuid.uuid4().hex, "attempt_id": uuid.uuid4().hex, "fence": 1,
        "worker_id": signer.registration.owner_id, "job_sha256": digest(job),
        "source_sha256": plan["source_sha256"], "policy_sha256": digest(POLICY),
        "plan_sha256": hashlib.sha256(blobs["plan.json"]).hexdigest(),
        "adapter_sha256": native.implementation_sha256(), "runtime_sha256": digest(frozen_runtime),
        "image_sha256": None}

    def observe():
        observed = copy.deepcopy(context)
        live_job = {**job, "code_sha256": digest(source_snapshot(root)),
                    "input_artifacts": artifact_manifest(snapshot_native_bundle(source_root))}
        observed.update(job_sha256=digest(live_job), policy_sha256=digest(POLICY),
                        adapter_sha256=native.implementation_sha256(), runtime_sha256=digest(runtime_snapshot()))
        return observed

    verifier = LocalEvidenceVerifier(registry, profile, signer.registration.owner_id, ledger)
    challenge = verifier.issue(context, current_context=observe, ttl_seconds=120)
    _write(output / "job.json", job)
    _write(output / "context.json", context)
    _write(output / "challenge.json", challenge)
    # The challenge precedes this new replay operation, not the historical fit.
    replay = replay_native_bundle(blobs)
    now = registry.current_time()
    statement = {"schema": "mra-worker-evidence/v1", "context": context, "challenge": challenge,
                 "artifacts": artifact_manifest(blobs), "observations": dict(OBSERVATIONS),
                 "issued_at": now, "expires_at": min(now + 120, challenge["expires_at"])}
    raw = signer.sign(statement, registry)
    (output / "envelope.json").write_bytes(raw)
    checks = {}
    def accept(data=raw, observer=observe, required="local_public_replay"):
        return verifier.accept(data, expected_context=context, artifact_root=source_root,
                               current_context=observer, required_profile=required)
    tampered = json.loads(raw)
    signature = tampered["signature"]
    tampered["signature"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    checks["signature_tampering_rejected"] = _denied(lambda: accept(canonical_bytes(tampered)))
    for label, key in (("policy", "policy_sha256"), ("source", "source_sha256"), ("runtime", "runtime_sha256"),
                       ("job", "job_sha256"), ("plan", "plan_sha256"), ("image", "image_sha256")):
        changed = copy.deepcopy(context)
        changed[key] = "f" * 64 if context[key] != "f" * 64 else "e" * 64
        checks["changed_" + label + "_rejected"] = _denied(lambda c=changed: accept(observer=lambda: c))
    checks["production_isolation_required"] = _denied(lambda: accept(required="agency_private_cloud"))
    admitted = accept()
    _write(output / "admission.json", admitted)
    checks["valid_local_replay_accepted"] = admitted["status"] == "accepted_local_replay"
    checks["replay_rejected"] = _denied(accept)
    reopened = ReplayLedger.open(ledger.root, ledger.ledger_id)
    reopened_verifier = LocalEvidenceVerifier(registry, profile, signer.registration.owner_id, reopened)
    checks["restart_replay_rejected"] = _denied(lambda: reopened_verifier.accept(raw, expected_context=context,
        artifact_root=source_root, current_context=observe, required_profile="local_public_replay"))
    checks["fresh_nonce_same_execution_rejected"] = _denied(lambda: verifier.issue(context, current_context=observe))
    return {"profile": name, "operation": "retained_native_replay", "checks": checks,
            "input_artifacts": artifact_manifest(blobs), "replay": replay, "context": context,
            "source_bundle_unchanged": artifact_manifest(snapshot_native_bundle(source_root)) == artifact_manifest(blobs),
            **FLAGS}, (raw, context, source_root, observe)


def run_rehearsal(*, root=ROOT, output, benchmark=None):
    root = Path(root).absolute()
    output = _BASELINE.prepare_output(root, output)
    report = {"schema": "mra-execution-evidence-rehearsal/v1", "status": "failed", "cases": [],
              "source": None, "source_unchanged": False, "errors": [], **FLAGS}
    try:
        source = source_snapshot(root)
        report["source"] = source
        cases = _fixture(output / "public-fixture") if benchmark is None else _existing_cases(root, benchmark)
        clock = lambda: int(time.time())
        profile = TrustProfile("fixture-agency", "public_fixture", "https://worker.example.invalid",
                               "urn:mra:local-replay", "worker_evidence")
        now = clock()
        registry = FixtureTrustRegistry(now=clock, fresh_until=now + 300)
        signer = MemoryFixtureEvidenceSigner(profile=profile, owner_id="replay-worker", key_id="fixture-worker-key",
                                              not_before=now, not_after=now + 300)
        registry.enroll(signer.registration, expected_revision=registry.revision)
        registration = signer.registration
        _write(output / "public-registration.json", {"profile": asdict(profile), "key_id": registration.key_id,
            "owner_id": registration.owner_id, "fingerprint": registration.fingerprint,
            "not_before": registration.not_before, "not_after": registration.not_after,
            "public_key_pem": registration.public_key_pem.decode("ascii"),
            "trust_scope": "observed_ephemeral_fixture_key_not_independent_production_trust"})
        ledger = ReplayLedger.create(output / "ledger")
        (output / "cases").mkdir()
        attempts = []
        for name, path in cases.items():
            item, attempt = exercise_case(root, output / "cases" / name, path, name, source, ledger, registry, profile, signer)
            report["cases"].append(item)
            attempts.append(attempt)
        # The revocation drill verifies signatures directly, independently of
        # already-spent challenges, so replay refusal cannot mask a trust bug.
        for raw, _, _, _ in attempts:
            verify_envelope(raw, registry, profile, signer.registration.owner_id)
        registry.revoke(signer.registration.key_id, expected_revision=registry.revision)
        for item, (raw, context, path, observer) in zip(report["cases"], attempts):
            item["checks"]["revoked_signer_rejected"] = _denied(lambda: verify_envelope(raw,
                registry, profile, signer.registration.owner_id))
        report["ledger_id"] = ledger.ledger_id
        report["public_signer"] = {"key_id": signer.registration.key_id, "fingerprint": signer.registration.fingerprint,
                                   "revoked_after_run": True}
        report["source_unchanged"] = source_snapshot(root) == source
        if (report["source_unchanged"] and report["cases"]
                and all(set(item["checks"]) == REQUIRED_CHECKS and all(item["checks"].values())
                        and item["source_bundle_unchanged"] for item in report["cases"])):
            report["status"] = "passed"
    except Exception as error:
        report["errors"].append({"type": type(error).__name__, "stage": "local_replay_evidence"})
    _write(output / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--benchmark", type=Path, help="Existing public PRD11 benchmark under this repository's .local")
    args = parser.parse_args(argv)
    try:
        report = run_rehearsal(root=ROOT, output=args.output, benchmark=args.benchmark)
    except (OSError, EvidenceError, _BASELINE.BaselineError) as error:
        print(json.dumps({"status": "refused", "type": type(error).__name__}))
        return 2
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "errors": report["errors"]}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
