"""Freeze registration before fresh local fitting and bind reviewed evidence.

The only inputs are fixed public profile IDs and bounded sample sizes. There is
no estimator, artifact-import, parent-model or private-data entry point. The
trusted local driver is not an agency identity/approval or cloud worker service.
"""
from __future__ import annotations

import copy
import hashlib
from itertools import islice
from pathlib import Path
import uuid

from .contracts import (RegistrationError, build_registration, canonical_bytes, digest,
                        evaluate_native, validate_registration)
from .profiles import load_profile
from .store import RegistrationStore
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes as native_bytes
from ..production_evidence.contracts import OBSERVATIONS
from ..production_evidence.ledger import ReplayLedger
from ..production_evidence.replay import artifact_manifest, snapshot_native_bundle
from ..production_evidence.signing import MemoryFixtureEvidenceSigner, verify_envelope
from ..production_evidence.verifier import LocalEvidenceVerifier, runtime_observation
from ..production_trust.registry import FixtureTrustRegistry

FLAGS = {"fixture_only": True, "authorization_eligible": False, "production_authorized": False,
         "model_delivery": False, "original_training_attested": False, "privacy_accounting_supported": False,
         "image_verified": False, "hostile_code_isolated": False, "network_isolated": False}


def _reject():
    raise RegistrationError("Prospective training registration rejected")


def workflow_sha256():
    """Pin participating local Python sources, not a remotely measured runtime."""
    package = Path(__file__).parent.parent
    required = {"__init__.py", "analyzers/attack.py", "portfolio_statistics.py", "production_identity/tokens.py"}
    for group, names in (
        ("production_registration", ("__init__", "workflow", "contracts", "profiles", "store")),
        ("production_adapters", ("__init__", "native", "contracts", "datasets", "catalog")),
        ("production_evidence", ("__init__", "contracts", "signing", "verifier", "replay", "ledger")),
        ("production_trust", ("__init__", "registry", "signer", "verification")),
    ):
        required.update(group + "/" + name + ".py" for name in names)
    paths = set(islice(package.rglob("*.py"), 257))
    if len(paths) > 256 or not required <= {path.relative_to(package).as_posix() for path in paths}:
        _reject()
    return digest({path.relative_to(package).as_posix(): hashlib.sha256(native._read(path, 2 * 1024 * 1024)).hexdigest()
                   for path in sorted(paths)})


def prepare_native_input(data, seed):
    """Own the data and derive the exact existing native bytes before any fit."""
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        _reject()
    owned = {key: copy.deepcopy(value) for key, value in data.items() if key not in {"x", "y"}}
    x, y = native._arrays(data["x"], data["y"])
    x.setflags(write=False); y.setflags(write=False)
    owned.update(x=x, y=y)
    payload = {"schema_version": "mra-native-tabular-data/v1", "x": x.tolist(), "y": y.tolist(),
               "feature_names": list(data["feature_names"]), "task": data["task"]}
    data_bytes = native_bytes(payload) + b"\n"
    plan = native._plan(x, y, data["dataset_id"], data["source_sha256"], data["feature_names"],
                        data["task"], seed, hashlib.sha256(data_bytes).hexdigest())
    plan_bytes = native_bytes(plan) + b"\n"
    return owned, data_bytes, plan_bytes


def _write(path, value):
    with path.open("xb") as stream:
        stream.write(canonical_bytes(value) + b"\n")


class LocalRegistrationWorkflow:
    def __init__(self, registry, signer, store, evidence_ledger):
        if (type(registry) is not FixtureTrustRegistry or type(signer) is not MemoryFixtureEvidenceSigner
                or type(store) is not RegistrationStore or type(evidence_ledger) is not ReplayLedger):
            _reject()
        self.registry, self.signer, self.store, self.evidence_ledger = registry, signer, store, evidence_ledger
        self.profile = signer.registration.profile

    def _clock(self):
        return self.registry.current_time()

    def _current_key_time(self):
        now = self.registry.current_time()
        self.registry.signing_key_at(self.signer.registration.key_id, self.profile,
                                     owner_id=self.signer.registration.owner_id, now=now)
        return now

    def run(self, profile_id, *, output, agency_id, project_id, case_id, data_root=None,
            max_rows=4096, seed=20261001):
        """One new registered fit; caller-selected estimator/imports are impossible.

        The output must be fresh. Failure retains its registration/history and
        partial files. There is no retry/resume that reuses an old candidate.
        """
        if agency_id != self.profile.agency_id:
            _reject()
        # Resolve the fixed public profile before creating output or training.
        data = load_profile(profile_id, data_root=data_root, max_rows=max_rows)
        data, frozen_data, frozen_plan = prepare_native_input(data, seed)
        frozen_workflow, frozen_runtime = workflow_sha256(), digest(runtime_observation())
        destination = native._new_output(output)
        registration_id, attempt_id = uuid.uuid4().hex, uuid.uuid4().hex
        result = {"schema": "mra-prospective-training-run/v1", "status": "failed", "profile_id": profile_id,
                  "registration_id": registration_id, "registration_sha256": None, "review": None,
                  "error": None, **FLAGS}
        reserved = False
        registered_bytes = None
        stage = "source_changed"

        def input_guard():
            # Called under the shared registry lock at each custody boundary.
            if workflow_sha256() != frozen_workflow or digest(runtime_observation()) != frozen_runtime:
                _reject()
            if registered_bytes is not None and native._read(destination / "registration.json", 65536) != registered_bytes:
                _reject()
            current = load_profile(profile_id, data_root=data_root, max_rows=max_rows)
            _, actual_data, actual_plan = prepare_native_input(current, seed)
            if (actual_data != frozen_data or actual_plan != frozen_plan
                    or digest(current["metadata"]) != digest(data["metadata"])):
                _reject()
            return self._current_key_time()

        try:
            with self.registry.operation_lock:
                history = self.store.history(agency_id, project_id, guard=input_guard)
                registration = build_registration(registration_id=registration_id, agency_id=agency_id,
                    project_id=project_id, case_id=case_id, profile_id=profile_id, data=data,
                    data_bytes=frozen_data, plan_bytes=frozen_plan, history=history,
                    workflow_sha256=frozen_workflow, runtime_sha256=frozen_runtime)
                registration = validate_registration(registration)
                ticket = self.store.reserve(registration, guard=input_guard)
                reserved = True
                result["registration_sha256"] = digest(registration)
                _write(destination / "registration.json", registration)
                registered_bytes = canonical_bytes(registration) + b"\n"
                _write(destination / "reservation.json", ticket)
                ticket = self.store.start(ticket, guard=input_guard)
                _write(destination / "training-start.json", ticket)
                started_history = self.store.history(agency_id, project_id, guard=input_guard)
            # Both commits and all frozen bytes exist before StandardScaler.fit.
            stage = "training_failed"
            native_result = native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"],
                source_sha256=data["source_sha256"], feature_names=data["feature_names"],
                task=data["task"], seed=seed, output=destination / "native")
            if native_result["status"] != "completed":
                _reject()
            blobs = snapshot_native_bundle(destination / "native")
            if blobs["dataset.json"] != frozen_data or blobs["plan.json"] != frozen_plan:
                _reject()
            stage = "evidence_failed"
            review = evaluate_native(registration, blobs)
            artifacts = artifact_manifest(blobs)
            context = {"schema": "mra-execution-context/v1", "operation": "retained_native_replay",
                "environment": "public_fixture", "agency_id": agency_id, "project_id": project_id,
                "case_id": case_id, "job_id": registration_id, "attempt_id": attempt_id, "fence": 1,
                "worker_id": self.signer.registration.owner_id,
                "job_sha256": digest({"registration_sha256": digest(registration), "started_history": started_history,
                                      "artifacts": artifacts}),
                "source_sha256": data["source_sha256"], "policy_sha256": digest(registration),
                "plan_sha256": hashlib.sha256(frozen_plan).hexdigest(),
                "adapter_sha256": native.implementation_sha256(), "runtime_sha256": frozen_runtime,
                "image_sha256": None}

            def observe():
                input_guard()
                current_history = self.store.history(agency_id, project_id, guard=self._clock)
                if canonical_bytes(current_history) != canonical_bytes(started_history):
                    _reject()
                if canonical_bytes(artifact_manifest(snapshot_native_bundle(destination / "native"))) != canonical_bytes(artifacts):
                    _reject()
                return copy.deepcopy(context)

            verifier = LocalEvidenceVerifier(self.registry, self.profile, self.signer.registration.owner_id, self.evidence_ledger)
            challenge = verifier.issue(context, current_context=observe, ttl_seconds=120)
            with self.registry.operation_lock:
                now = input_guard()
                statement = {"schema": "mra-worker-evidence/v1", "context": context, "challenge": challenge,
                    "artifacts": artifacts, "observations": dict(OBSERVATIONS), "issued_at": now,
                    "expires_at": challenge["expires_at"]}
                envelope = self.signer.sign(statement, self.registry)
            admission = verifier.accept(envelope, expected_context=context, artifact_root=destination / "native",
                                        current_context=observe, required_profile="local_public_replay")
            _write(destination / "replay-context.json", context)
            _write(destination / "replay-challenge.json", challenge)
            with (destination / "replay-envelope.json").open("xb") as stream: stream.write(envelope)
            _write(destination / "replay-admission.json", admission)
            _write(destination / "review.json", review)
            completion = {"registration_sha256": digest(registration), "artifacts_sha256": digest(artifacts),
                "candidate_sha256": hashlib.sha256(blobs["candidate.json"]).hexdigest(),
                "report_sha256": hashlib.sha256(blobs["report.json"]).hexdigest(),
                "evidence_envelope_sha256": hashlib.sha256(envelope).hexdigest(),
                "evidence_admission_sha256": digest(admission), "review": review}

            def final_guard():
                input_guard()
                if canonical_bytes(artifact_manifest(snapshot_native_bundle(destination / "native"))) != canonical_bytes(artifacts):
                    _reject()
                verify_envelope(envelope, self.registry, self.profile, self.signer.registration.owner_id)
                now = self._current_key_time()
                if not statement["issued_at"] <= now < statement["expires_at"]:
                    _reject()
                return now

            stage = "history_changed"
            with self.registry.operation_lock:
                record = self.store.complete(ticket, completion, guard=final_guard)
            _write(destination / "registration-record.json", record)
            result.update(status="review_recorded", review=review)
        except Exception as error:
            result["error"] = {"stage": stage, "type": type(error).__name__}
            if reserved:
                try:
                    # Recording failure is not an authorization; revoked/stale
                    # keys cannot suppress the existing local audit trail.
                    with self.registry.operation_lock:
                        self.store.fail(registration_id, stage, guard=self._clock)
                except Exception as failure:
                    result["failure_recording_error"] = type(failure).__name__
        _write(destination / "result.json", result)
        return result
