"""Fixed public Wine end-to-end rehearsal; no agency authorization."""
from __future__ import annotations
import hashlib
from pathlib import Path
import shutil
from ..production_identity.policy import PermissionDenied, IdentityUnavailable
from ..production_review.contracts import ReviewError
from ..production_delivery.contracts import DeliveryError, MAX_CHUNK_BYTES
from ..production_delivery.store import StoreError as DeliveryStoreError, StoreUnavailable
from .contracts import FLAGS, ProfileError
from .workflow import PublicProfileWorkflow, write_json
from .receipt import seal_receipt, verify_receipt

REQUIRED_CHECKS = frozenset({
    "production_profile_refused_before_fit", "combined_plan_frozen_before_fit",
    "fresh_registered_native_replay", "fixed_external_attack_and_controls",
    "external_bound_before_independent_reviews", "owner_and_operator_review_denied",
    "native_only_activation_denied", "exact_candidate_delivery", "partial_write_retains_attempt",
    "suspension_denies_next_chunk", "resume_requires_new_admission", "grant_revocation_denies_chunk",
    "activation_revocation_permanent", "exclusive_expiry_denies_chunk",
    "historical_receipt_replayed", "pinned_receipt_tamper_denied", "all_results_production_blocked"})

def exercise(output, *, python, versions, lock_sha256):
    destination = Path(output)
    destination.mkdir(exist_ok=True)
    checks = []
    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise ProfileError("Public profile milestone failed: " + name)
    def denied(action):
        try:
            action()
        except (PermissionDenied, IdentityUnavailable, ReviewError, DeliveryError,
                DeliveryStoreError, StoreUnavailable, ProfileError, ValueError):
            return True
        return False

    blocked = destination / "production-refused"
    check("production_profile_refused_before_fit", denied(lambda: PublicProfileWorkflow(
        blocked, python=python, versions=versions, lock_sha256=lock_sha256)) and not blocked.exists())
    workflow = PublicProfileWorkflow(destination / "run", python=python, versions=versions,
        lock_sha256=lock_sha256, profile="local_public_fixture")
    policy, operator = workflow.token("policy"), workflow.token("operator")
    assessor, releaser = workflow.token("assessor"), workflow.token("releaser")
    planned = workflow.freeze(policy)
    check("combined_plan_frozen_before_fit", planned["stage"] == "planned"
        and planned["plan"]["required_cases"] == ["target", "positive", "null"]
        and not (workflow.root / "fixture/training").exists())
    native = workflow.execute(operator)
    check("fresh_registered_native_replay", native["stage"] == "native"
        and (workflow.root / "fixture/training/replay-envelope.json").is_file()
        and native["stages"]["native"]["payload"]["registration_id"] != planned["plan"]["campaign_id"])
    check("native_only_activation_denied", denied(lambda: workflow.authorize(releaser))
        and not workflow.status(workflow.token("auditor"))["delivery"]["activations"])
    before_external = denied(lambda: workflow.assess(assessor))
    compared = workflow.compare(operator)
    check("fixed_external_attack_and_controls", compared["stage"] == "external"
        and workflow._external_auc <= planned["plan"]["max_external_auc_bps"])
    owner_denied = denied(lambda: workflow.assess(workflow.token("owner")))
    assessed = workflow.assess(assessor)
    operator_denied = denied(lambda: workflow.approve(operator))
    check("owner_and_operator_review_denied", owner_denied and operator_denied)
    approved = workflow.approve(releaser)
    combined_sha = compared["stages"]["external"]["payload"]["combined_sha256"]
    check("external_bound_before_independent_reviews", before_external
        and all(snapshot["stages"][stage]["payload"]["combined_sha256"] == combined_sha
                for snapshot, stage in ((assessed, "assess"), (approved, "approve"))))
    authorized = workflow.authorize(releaser)
    activation_id = authorized["stages"]["authorize"]["payload"]["activation_id"]
    recipient = workflow.token("recipient")
    grant_id, grant = workflow.grant(releaser, recipient)
    transfer_id = grant["payload"]["transfer_id"]
    candidate = (workflow.root / "fixture/training/native/candidate.json").read_bytes()
    collected, receipts = [], []
    def writer(content):
        collected.append(content)
        return len(content)
    offset = 0
    while offset < len(candidate):
        length = min(128 if offset == 0 else MAX_CHUNK_BYTES, len(candidate) - offset)
        receipt = workflow.deliver_chunk(recipient, grant_id, transfer_id, offset, length, writer=writer)
        receipts.append(receipt)
        offset += length
    check("exact_candidate_delivery", b"".join(collected) == candidate and len(receipts) >= 2
        and all(r["bytes_written"] == r["admission"]["length"] and r["observation_recorded"] for r in receipts))
    partial_id, partial_grant = workflow.grant(releaser, recipient)
    partial = workflow.deliver_chunk(recipient, partial_id, partial_grant["payload"]["transfer_id"],
                                     0, 128, writer=lambda content: 1)
    state = workflow.status(workflow.token("auditor"))["delivery"]
    check("partial_write_retains_attempt", partial["status"] == "interrupted"
        and partial["bytes_written"] == 1 and state["grants"][partial_id]["attempted_bytes"] == 128
        and partial["admission"]["request_id"] in state["admissions"])
    live_id, live_grant = workflow.grant(releaser, recipient)
    live_transfer = live_grant["payload"]["transfer_id"]
    first = workflow.deliver_chunk(recipient, live_id, live_transfer, 0, 128, writer=lambda content: len(content))
    workflow.suspend(releaser)
    suspended = denied(lambda: workflow.deliver_chunk(recipient, live_id, live_transfer,
                                                      128, 128, writer=lambda content: len(content)))
    check("suspension_denies_next_chunk", suspended)
    workflow.resume(releaser)
    resumed = workflow.deliver_chunk(recipient, live_id, live_transfer, 128, 128,
                                     writer=lambda content: len(content))
    resumed_fresh = resumed["admission"]["request_id"] != first["admission"]["request_id"]
    check("resume_requires_new_admission", resumed_fresh and resumed["bytes_written"] == 128)
    workflow.revoke_grant(releaser, live_id)
    grant_revoked = denied(lambda: workflow.deliver_chunk(recipient, live_id, live_transfer,
                                                          256, 128, writer=lambda content: len(content)))
    check("grant_revocation_denies_chunk", grant_revoked)
    expiry = partial_grant["payload"]["expires_at"]
    workflow.advance_to(expiry)
    emitted = []
    expired = denied(lambda: workflow.deliver_chunk(recipient, partial_id,
        partial_grant["payload"]["transfer_id"], 128, 128, writer=lambda content: emitted.append(content)))
    check("exclusive_expiry_denies_chunk", expired and not emitted)
    workflow.revoke(releaser)
    permanent = denied(lambda: workflow.resume(releaser))
    check("activation_revocation_permanent", permanent)
    completed_chunks = [{**{name: r["admission"][name] for name in
        ("request_id", "chunk_id", "offset", "length", "chunk_sha256")},
        **{name: r[name] for name in ("bytes_written", "status", "write_extent_known", "observation_recorded")}}
        for r in receipts]
    summary = {"schema": "mra-public-profile-delivery-summary/v1", "activation_id": activation_id,
        "grant_id": grant_id, "transfer_id": transfer_id, "artifact_sha256": hashlib.sha256(candidate).hexdigest(),
        "artifact_size": len(candidate), "completed_chunks": completed_chunks,
        "collected_sha256": hashlib.sha256(b"".join(collected)).hexdigest(),
        "partial_request_id": partial["admission"]["request_id"], "partial_attempted_bytes": 128,
        "partial_bytes_written": 1, **FLAGS}
    lifecycle = {"schema": "mra-public-profile-lifecycle/v1", "checks": {
        "suspension_denied": suspended, "resumed_fresh_admission": resumed_fresh,
        "grant_revocation_denied": grant_revoked, "activation_revocation_permanent": permanent,
        "expiry_denied": expired}, "activation_id": activation_id, "live_grant_id": live_id,
        "partial_grant_id": partial_id, "expiry_activation_id": activation_id, "expiry_grant_id": partial_id,
        "resumed_request_id": resumed["admission"]["request_id"], "expiry_at": expiry, **FLAGS}
    terminal = workflow.finish(workflow.token("auditor"), summary, lifecycle)
    pin = seal_receipt(workflow.root, journal_pin=workflow.journal_pin, delivery_pin=workflow.delivery_pin)
    replayed = verify_receipt(workflow.root, expected_receipt_sha256=pin["receipt_sha256"],
                             expected_key_sha256=pin["key_sha256"])
    write_json(destination / "replay-result.json", replayed)
    check("historical_receipt_replayed", replayed["status"] == "historical_fixture_replay_verified"
        and replayed["current_authorization_checked"] is False)
    tamper = destination / "tamper-probe"
    shutil.copytree(workflow.root, tamper)
    changed = tamper / "combined-binding.json"
    changed.write_bytes(changed.read_bytes() + b" ")
    check("pinned_receipt_tamper_denied", denied(lambda: verify_receipt(tamper,
        expected_receipt_sha256=pin["receipt_sha256"], expected_key_sha256=pin["key_sha256"])))
    check("all_results_production_blocked", all(replayed[key] is value for key, value in FLAGS.items())
        and all(receipt[key] is value for receipt in receipts for key, value in FLAGS.items() if key in receipt))
    if {item["name"] for item in checks} != REQUIRED_CHECKS:
        raise ProfileError("Incomplete fixed profile milestones")
    return {"schema": "mra-public-profile-exercise/v1", "status": "passed", "checks": checks,
        "summary": {"profile_id": "sklearn-wine", "max_rows": 128, "fresh_native_runs": 1,
            "external_repetitions": 9, "external_max_symmetric_auc_bps": workflow._external_auc,
            "artifact_size": len(candidate), "completed_transfer_chunks": len(receipts),
            "public_fixture_bytes_delivered": True, "recipient_receipt_verified": False,
            "historical_replay_verified": True},
        "evidence": {"run_path": "run", "run_id": planned["plan"]["run_id"],
            "campaign_id": planned["plan"]["campaign_id"], "plan_sha256": planned["plan_sha256"],
            "combined_sha256": combined_sha, "journal_pin": terminal["pin"],
            "delivery_pin": workflow.delivery_pin, "receipt_pin": pin}, **FLAGS}
