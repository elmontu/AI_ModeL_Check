"""Atomic local evidence acceptance under current trust and server-owned bindings.

This trusted Python boundary is not an HTTP submission or identity service. The
caller supplies a current-context observer from its control plane, never from a
worker report. A committed local replay receipt cannot authorize release. The
production profile has no implemented isolation verifier and always fails closed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import sys
from .contracts import (EvidenceError, canonical_bytes, digest, execution_digest,
                        validate_context)
from .signing import verify_envelope
from .replay import artifact_manifest, replay_native_bundle, snapshot_native_bundle
from ..production_adapters.contracts import parse_plan
from ..production_adapters import native
from ..production_trust.registry import FixtureTrustRegistry, TrustProfile, TrustDenied

FLAGS = {"fixture_only": True, "authorization_eligible": False,
         "production_authorized": False, "model_delivery": False,
         "original_training_attested": False, "image_verified": False,
         "hostile_code_isolated": False, "network_isolated": False,
         "filesystem_isolated": False, "resource_limits_verified": False}


def _fail():
    raise EvidenceError("Worker evidence rejected")


def runtime_observation():
    """Observe this Python launcher and version tuple, not an image attestation."""
    try:
        path = Path(sys.executable).resolve(strict=True)
        before = path.stat()
        if not 0 < before.st_size <= 32 * 1024 * 1024:
            _fail()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read(32 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
        def stamp(info):
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
        if (stamp(before) != stamp(opened) or stamp(opened) != stamp(after)
                or stamp(after) != stamp(path.stat()) or len(raw) != before.st_size):
            _fail()
        return {"schema": "mra-local-python-observation/v1", "python": platform.python_version(),
                "platform": platform.platform(), "adapter_runtime": native._runtime(),
                "python_launcher_sha256": hashlib.sha256(raw).hexdigest()}
    except Exception:
        raise EvidenceError("Worker evidence rejected") from None


class LocalEvidenceVerifier:
    """One-use admission of replay evidence, separate from PRD10 job completion.

    ``current_context`` must independently resample current authorized job,
    source, policy, plan, adapter and runtime bindings. Revocation/cancellation
    must make it raise or return a different context. It is trusted in-process
    bootstrap, not authority granted by a request or by signed worker claims.
    The registry operation lock must also guard that observer's mutable state.
    """

    def __init__(self, registry, profile, owner_id, ledger):
        if (type(registry) is not FixtureTrustRegistry or type(profile) is not TrustProfile
                or profile.purpose != "worker_evidence"):
            _fail()
        self.registry, self.profile = registry, profile
        self.owner_id, self.ledger = owner_id, ledger

    def _context(self, expected, current_context):
        if not callable(current_context):
            _fail()
        current = validate_context(current_context())
        if (canonical_bytes(current) != canonical_bytes(expected)
                or expected["agency_id"] != self.profile.agency_id
                or expected["worker_id"] != self.owner_id
                or expected["runtime_sha256"] != digest(runtime_observation())):
            _fail()

    def issue(self, context, *, current_context, ttl_seconds=120):
        expected = validate_context(context)
        with self.registry.operation_lock:
            def guard():
                self._context(expected, current_context)
                key_ids = tuple(self.registry.public_keys(self.profile))
                now = self.registry.current_time()
                # Require a current active key for this exact worker at the
                # same final time sampled for challenge issuance/commit.
                for key_id in key_ids:
                    try:
                        self.registry.signing_key_at(key_id, self.profile, owner_id=self.owner_id, now=now)
                    except TrustDenied:
                        continue
                    return now
                _fail()
            return self.ledger.issue(digest(expected), execution_digest(expected),
                                     ttl_seconds=ttl_seconds, guard=guard)

    def accept(self, raw, *, expected_context, artifact_root, current_context,
               required_profile="agency_private_cloud"):
        """Verify and commit once; default production requirements cannot be waived.

        ``local_public_replay`` is an explicit non-authorizing fixture profile.
        Return values bind immutable hashes, not future reads of mutable paths.
        Consumers must independently verify those hashes at any later use.
        """
        expected = validate_context(expected_context)
        if type(required_profile) is not str or required_profile != "local_public_replay":
            _fail()  # No qualified image/isolation attestation adapter exists yet.
        if expected["image_sha256"] is not None:
            _fail()  # This process observed a local runtime, not an OCI image.
        with self.registry.operation_lock:
            self._context(expected, current_context)
            signed = verify_envelope(raw, self.registry, self.profile, self.owner_id)
            statement = signed["statement"]
            if canonical_bytes(statement["context"]) != canonical_bytes(expected):
                _fail()
            blobs = snapshot_native_bundle(artifact_root)
            manifest = artifact_manifest(blobs)
            if canonical_bytes(manifest) != canonical_bytes(statement["artifacts"]):
                _fail()
            plan = parse_plan(blobs["plan.json"])
            if (hashlib.sha256(blobs["plan.json"]).hexdigest() != expected["plan_sha256"]
                    or plan.source_sha256 != expected["source_sha256"]
                    or plan.implementation_sha256 != expected["adapter_sha256"]):
                _fail()
            # This replays exactly the immutable byte snapshot above. It performs
            # no subsequent reads through worker-controlled artifact paths.
            replay = replay_native_bundle(blobs)
            expected_signed = canonical_bytes(signed)

            def guard():
                self._context(expected, current_context)
                # Detect replacement of the original bundle as well as changes
                # to server-owned source/policy/job bindings before consumption.
                if canonical_bytes(artifact_manifest(snapshot_native_bundle(artifact_root))) != canonical_bytes(manifest):
                    _fail()
                current_signed = verify_envelope(raw, self.registry, self.profile, self.owner_id)
                if canonical_bytes(current_signed) != expected_signed:
                    _fail()
                # verify_envelope ends with an exact current-time/key check.
                # A new sample below must still be before evidence expiration.
                now = self.registry.current_time()
                self.registry.signing_key_at(current_signed["key_id"], self.profile,
                                              owner_id=self.owner_id, now=now)
                if not statement["issued_at"] <= now < statement["expires_at"]:
                    _fail()
                return now

            consumed = self.ledger.consume(statement["challenge"], signed["envelope_sha256"], guard=guard)
            return {"schema": "mra-local-evidence-admission/v1", "status": "accepted_local_replay",
                    "context_sha256": digest(expected), "artifacts_sha256": digest(manifest),
                    "envelope_sha256": signed["envelope_sha256"], "key_id": signed["key_id"],
                    "key_fingerprint": signed["key_fingerprint"], "consumption": consumed,
                    "replay": replay, **FLAGS}
