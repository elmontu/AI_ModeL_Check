"""Additive current gate binding fresh native and external public-fixture tests.

The private bootstrap composes frozen services. Its atomic authorization is one
PRD18 fixture activation commit, never a cross-store privacy-charge transaction.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import time
import uuid

from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes as artifact_bytes, strict_json as artifact_json
from ..production_delivery.rehearsal import DeliveryFixture
from ..production_identity.policy import PermissionDenied
from ..production_sacro.evidence import _capture, FILES as EXTERNAL_FILES
from ..production_sacro.runtime import ATTACK_PARAMETERS
from ..production_sacro.workflow import expected_binding, run_comparison
from ..production_evidence.replay import artifact_manifest, snapshot_native_bundle
from .contracts import FLAGS, ProfileError, canonical_bytes, digest, owned
from .journal import Journal
from .runtime import validate_spec

PROFILE = "sklearn-wine"
CASE = "case-a"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    raw = canonical_bytes(value, max_bytes=1024 * 1024) + b"\n"
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        import os
        os.fsync(stream.fileno())


def recipe_sha256():
    return _sha(artifact_bytes({"binding": expected_binding(), "parameters": dict(ATTACK_PARAMETERS),
        "cases": ["target", "positive", "null"], "seeds": [20261001, 20261002, 20261003],
        "selection": "all_cases_all_repetitions", "threshold": "maximum_symmetric_auc_bps_ceil"}))


def implementation_sha256():
    directory = Path(__file__).parent
    names = ("__init__", "contracts", "journal", "receipt", "runtime", "workflow", "rehearsal")
    return digest({name: _sha(native._read(directory / (name + ".py"), 2 * 1024 * 1024))
                   for name in names})


def combined_binding(plan_sha256, native_binding_sha256, bindings):
    return {"schema": "mra-public-profile-binding/v1", "plan_sha256": plan_sha256,
        "native_binding_sha256": native_binding_sha256,
        "native_artifacts_sha256": digest(bindings["native_artifacts"]),
        "external_files_sha256": digest(bindings["comparison_files"])}


def check_external(raw, *, lock_sha256, versions, maximum=9900):
    request = artifact_json(raw["input.json"], maximum=16 * 1024 * 1024)
    result = artifact_json(raw["result.json"], maximum=4 * 1024 * 1024)
    if request["lock_sha256"] != lock_sha256 or request["versions"] != versions:
        raise ProfileError("External runtime binding changed")
    comparison = result["comparison"]
    for name in ("target", "positive", "null"):
        repetitions = comparison[name]["repetitions"]
        if len(repetitions) != 3 or [item["seed"] for item in repetitions] != [20261001, 20261002, 20261003]:
            raise ProfileError("Required external repetitions unavailable")
    if not all(comparison[name]["controls_satisfied"] is True for name in ("positive", "null")):
        raise ProfileError("Required external controls unavailable")
    aucs = [item["attack"]["symmetric_auc"] for item in comparison["target"]["repetitions"]]
    if any(type(value) not in (int, float) or not math.isfinite(value) or not .5 <= value <= 1 for value in aucs):
        raise ProfileError("External descriptive scores rejected")
    if max(math.ceil(value * 10000) for value in aucs) > maximum:
        raise PermissionDenied("Frozen external descriptive threshold failed")
    return max(math.ceil(value * 10000) for value in aucs)


class PublicProfileWorkflow:
    """One new fixed run, scoped human decisions, no attach/import API."""
    def __init__(self, root, *, python, versions, lock_sha256, profile="agency_private_cloud"):
        if profile != "local_public_fixture":
            raise PermissionDenied("Agency production profile is unavailable")
        self._versions = validate_spec(versions, lock_sha256)
        self._lock_sha256, self._python = lock_sha256, Path(python).absolute()
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)
        self._fixture = DeliveryFixture(self.root / "fixture")
        self._origin, self._offset = time.monotonic(), 0
        foundation = self._fixture.review_fixture
        # The existing fixture's explicit trust clock now advances with elapsed
        # real time. No evidence lifetime is extended or re-signed.
        foundation.trust._clock = self.clock
        foundation.clock = self.clock
        self._review, self._gateway = self._fixture.review, self._fixture.gateway
        self._journal, self._pin = None, None
        self._contexts = []
        self._combined, self._native_observer = None, None
        self._external_files, self._external_native_manifest = None, None
        self._activation_id = None
        self._implementation = implementation_sha256()
        key = foundation.workflow.signer.registration
        write_json(self.root / "fixture/evidence-key.json", {
            "schema": "mra-public-profile-evidence-key/v1", "key_id": key.key_id,
            "profile": asdict(key.profile), "owner_id": key.owner_id,
            "not_before": key.not_before, "not_after": key.not_after,
            "public_key_pem": key.public_key_pem.decode("ascii"), "fingerprint": key.fingerprint})

    def clock(self):
        return 1000 + int(time.monotonic() - self._origin) + self._offset

    def advance_to(self, timestamp):
        now = self.clock()
        if type(timestamp) is not int or timestamp < now:
            raise ProfileError("Fixture clock cannot move backward")
        self._offset += timestamp - now

    def token(self, subject, **kwargs):
        self._fixture.review_fixture.now = self.clock()
        return self._fixture.token(subject, **kwargs)

    @property
    def journal_pin(self):
        return owned(self._pin)

    @property
    def delivery_pin(self):
        return self._gateway.required_pin

    def _state(self):
        if self._journal is None:
            raise PermissionDenied("Prospective combined plan unavailable")
        return self._journal.read(expected_pin=self._pin, guard=self.clock)

    def _campaign(self):
        return self._review.store.get(CASE, guard=self.clock)["campaigns"][self._campaign_id]

    def _require(self, stage):
        state = self._state()
        if state["stage"] != stage:
            raise PermissionDenied("Profile stage is unavailable")
        return state

    def _source_guard(self):
        if implementation_sha256() != self._implementation:
            raise PermissionDenied("Composite implementation changed")

    def _append(self, stage, payload, context, guard):
        snapshot = self._journal.append(stage, payload, context.actor,
            expected_pin=self._pin, guard=guard)
        self._pin = snapshot["pin"]
        return snapshot

    def freeze(self, policy_token):
        if self._journal is not None:
            raise PermissionDenied("Combined plan is immutable")
        with self._review.identity._lock:
            campaign_id, _ = self._fixture.review_fixture.propose(
                profile_id=PROFILE, max_rows=128, seed=20261001)
            self._campaign_id = campaign_id
            context = self._review.authorization.access(policy_token, CASE, "policy")
            self._review.approve_policy(policy_token, CASE, campaign_id)
            campaign = self._campaign()
            plan = {"schema": "mra-public-profile-plan/v1", "run_id": uuid.uuid4().hex,
                "campaign_id": campaign_id, "agency_id": "agency", "project_id": "project",
                "case_id": CASE, "recipient_id": "fixture-recipient", "profile_id": PROFILE,
                "seed": 20261001, "max_rows": 128, "native_policy_sha256": campaign["policy_sha256"],
                "sacro_lock_sha256": self._lock_sha256, "sacro_recipe_sha256": recipe_sha256(),
                "implementation_sha256": self._implementation, "max_external_auc_bps": 9900,
                "required_cases": ["target", "positive", "null"],
                "atomicity": "single_store_fixture_activation_only", **FLAGS}
            def guard():
                self._source_guard()
                return context.recheck()
            self._journal = Journal.create(self.root / "journal", plan, context.actor, guard=guard)
            self._pin = self._journal.initial_pin
            self._contexts.append(context)
            return self._state()

    def execute(self, operator_token):
        with self._review.identity._lock:
            self._require("planned")
            context = self._review.authorization.access(operator_token, CASE, "start")
            self._source_guard()
            snapshot = self._fixture.bridge.execute(operator_token, CASE, self._campaign_id,
                                                     output=self._fixture.output)
            campaign = snapshot["campaigns"][self._campaign_id]
            completion = campaign["completion"]
            self._native_observer = self._review._evidence[self._campaign_id]
            def guard():
                self._source_guard()
                self._native_observer()
                return self._current_contexts(extra=(context,))
            payload = {"campaign_id": self._campaign_id, "policy_sha256": campaign["policy_sha256"],
                "completion_sha256": completion["sha256"],
                "candidate_sha256": completion["payload"]["candidate_sha256"],
                "binding_sha256": campaign["binding_sha256"],
                "registration_id": completion["payload"]["registration_id"],
                "registration_sha256": completion["payload"]["registration_sha256"]}
            result = self._append("native", payload, context, guard)
            self._contexts.append(context)
            return result

    def compare(self, operator_token):
        with self._review.identity._lock:
            state = self._require("native")
            context = self._review.authorization.access(operator_token, CASE, "start")
            if context.actor != state["stages"]["native"]["actor"]:
                raise PermissionDenied("Original execution credential required")
            self._source_guard()
            self._native_observer()
            result = run_comparison(snapshot_native_bundle(self._fixture.output / "native"),
                profile_id=PROFILE, output=self.root / "external", python=self._python,
                versions=self._versions, lock_sha256=self._lock_sha256)
            if result["status"] != "completed":
                raise PermissionDenied("Required external execution unavailable")
            _, _, raw, bindings = _capture(self._fixture.output / "native", self.root / "external")
            self._external_auc = check_external(raw, lock_sha256=self._lock_sha256, versions=self._versions)
            combined = combined_binding(state["plan_sha256"],
                state["stages"]["native"]["payload"]["binding_sha256"], bindings)
            def guard():
                self._source_guard()
                self._native_observer()  # Exclusive native evidence expiry after external work.
                return self._current_contexts()
            guard()
            write_json(self.root / "combined-binding.json", combined)
            payload = {"combined_sha256": digest(combined),
                "files_sha256": digest(bindings["comparison_files"]),
                "external_plan_sha256": _sha(raw["plan.json"]),
                "external_result_sha256": _sha(raw["result.json"])}
            snapshot = self._append("external", payload, context, guard)
            self._combined = owned(combined)
            self._external_files = owned(bindings["comparison_files"])
            self._external_native_manifest = owned(bindings["native_artifacts"])
            # The exact original observer remains first. The additive observer
            # is only this trusted run's live evidence and is never rehydrated.
            self._review._evidence[self._campaign_id] = self._observe
            return snapshot

    def _current_contexts(self, *, extra=(), deadlines=()):
        now = self._review.authorization.recheck_many((*self._contexts, *extra))
        issued, expires = self._review._evidence_deadlines[self._campaign_id]
        if any(not begin <= now < end for begin, end in ((issued, expires), *deadlines)):
            raise PermissionDenied("Original evidence or activation expired")
        return now

    def _observe(self, state=None, *, extra=(), deadlines=()):
        self._source_guard()
        if self._native_observer is None or self._combined is None:
            raise PermissionDenied("Fresh combined evidence unavailable")
        self._native_observer()
        state = self._state() if state is None else state
        if state["stage"] not in ("external", "assess", "approve", "authorize"):
            raise PermissionDenied("Live composite evidence unavailable")
        # Semantic comparison was independently replayed before its immutable
        # binding was committed. Identical bytes retain identical semantics.
        # The original observer above already rehashes all package sources,
        # registered native artifacts and the original signed evidence.
        raw = {name: native._read(self.root / "external" / name, bound)
               for name, bound in EXTERNAL_FILES.items()}
        manifest = {name: {"sha256": _sha(content), "size_bytes": len(content)}
                    for name, content in raw.items()}
        if manifest != self._external_files:
            raise PermissionDenied("Required external evidence changed")
        expected = combined_binding(state["plan_sha256"],
            state["stages"]["native"]["payload"]["binding_sha256"], {
                "native_artifacts": self._external_native_manifest,
                "comparison_files": manifest})
        retained = native._read(self.root / "combined-binding.json", 65536)
        if (expected != self._combined or retained != canonical_bytes(self._combined) + b"\n"
                or digest(expected) != state["stages"]["external"]["payload"]["combined_sha256"]):
            raise PermissionDenied("Combined reviewed bytes changed")
        # All expensive work precedes this shared current-time sample.
        return self._current_contexts(extra=extra, deadlines=deadlines)

    def assess(self, assessor_token):
        with self._review.identity._lock:
            state = self._require("external")
            context = self._review.authorization.access(assessor_token, CASE, "assess")
            self._observe()
            snapshot = self._review.assess(assessor_token, CASE, self._campaign_id)
            decision = snapshot["campaigns"][self._campaign_id]["assessment"]
            def guard():
                return self._observe(state, extra=(context,))
            result = self._append("assess", {"combined_sha256": digest(self._combined),
                "native_assessment_sha256": decision["sha256"]}, context, guard)
            self._contexts.append(context)
            return result

    def approve(self, release_token):
        with self._review.identity._lock:
            state = self._require("assess")
            context = self._review.authorization.access(release_token, CASE, "approve")
            self._observe()
            snapshot = self._review.approve(release_token, CASE, self._campaign_id)
            decision = snapshot["campaigns"][self._campaign_id]["approval"]
            def guard():
                return self._observe(state, extra=(context,))
            result = self._append("approve", {"combined_sha256": digest(self._combined),
                "assessment_sha256": state["stages"]["assess"]["sha256"],
                "native_approval_sha256": decision["sha256"]}, context, guard)
            self._contexts.append(context)
            return result

    def authorize(self, release_token):
        with self._review.identity._lock:
            state = self._require("approve")
            context = self._review.authorization.access(release_token, CASE, "approve")
            self._observe()
            before = self._gateway.status(self.token("auditor"), CASE)["activations"]
            snapshot = self._gateway.activate(release_token, CASE, self._campaign_id,
                                               profile="local_public_fixture", ttl_seconds=30)
            added = set(snapshot["activations"]) - set(before)
            if len(added) != 1:
                raise ProfileError("One atomic fixture activation required")
            activation_id = added.pop()
            activation = snapshot["activations"][activation_id]
            def guard():
                return self._observe(state, extra=(context,), deadlines=(
                    (activation["recorded_at"], activation["payload"]["expires_at"]),))
            result = self._append("authorize", {"combined_sha256": digest(self._combined),
                "approval_sha256": state["stages"]["approve"]["sha256"],
                "activation_id": activation_id, "activation_sha256": activation["sha256"],
                "delivery_pin": self.delivery_pin}, context, guard)
            # A failure between stores leaves a historical activation unusable
            # through this facade; it never rolls back another store commit.
            self._activation_id = activation_id
            return result

    def _authorized(self):
        state = self._require("authorize")
        # Positive gateway operations invoke the installed combined observer
        # in their own activation/frame and final admission guards. Retain the
        # immutable facade fence here without an extra optimistic replay.
        if self._activation_id != state["stages"]["authorize"]["payload"]["activation_id"]:
            raise PermissionDenied("Exact composite activation unavailable")

    def grant(self, release_token, recipient_token):
        with self._review.identity._lock:
            self._authorized()
            before = self._gateway.status(self.token("auditor"), CASE)["grants"]
            state = self._gateway.grant(release_token, CASE, self._activation_id, recipient_token, ttl_seconds=20)
            added = set(state["grants"]) - set(before)
            if len(added) != 1:
                raise ProfileError("One fresh transfer grant required")
            grant_id = added.pop()
            return grant_id, state["grants"][grant_id]

    def deliver_chunk(self, recipient_token, grant_id, transfer_id, offset, length, *, writer, **ids):
        with self._review.identity._lock:
            self._authorized()
            return self._gateway.deliver_chunk(recipient_token, CASE, self._activation_id,
                grant_id, transfer_id, offset, length, writer=writer, **ids)

    def suspend(self, token):
        self._authorized()
        return self._gateway.suspend(token, CASE, self._activation_id)

    def resume(self, token):
        self._authorized()
        return self._gateway.resume(token, CASE, self._activation_id)

    def revoke_grant(self, token, grant_id):
        self._authorized()
        return self._gateway.revoke_grant(token, CASE, grant_id)

    def revoke(self, token):
        # Revocation requires current scoped authority even after grant expiry.
        self._require("authorize")
        return self._gateway.revoke(token, CASE, self._activation_id)

    def status(self, auditor_token):
        state = self._gateway.status(auditor_token, CASE)
        return {"journal": self._state(), "delivery": state, **FLAGS}

    def finish(self, auditor_token, summary, lifecycle):
        with self._review.identity._lock:
            state = self._require("authorize")
            context = self._review.authorization.access(auditor_token, CASE, "read")
            delivery = self._gateway.status(auditor_token, CASE)
            if delivery["activations"][self._activation_id]["state"] != "revoked":
                raise PermissionDenied("Terminal revocation required")
            write_json(self.root / "delivery-summary.json", summary)
            write_json(self.root / "lifecycle.json", lifecycle)
            return self._append("complete", {"combined_sha256": digest(self._combined),
                "activation_id": self._activation_id, "final_delivery_pin": self.delivery_pin,
                "delivery_summary_sha256": digest(summary), "lifecycle_sha256": digest(lifecycle)},
                context, context.recheck)
