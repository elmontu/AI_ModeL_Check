"""Prospective local misuse probes against one fresh reviewed public Wine run.

These are controlled engineering observations, not an independent penetration
test or scientific privacy qualification. Only newly generated public evidence
is changed, and reversible corruption restores exact bytes in a finally block.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType
import uuid

from ..production_capacity import io
from ..production_delivery.rehearsal import DeliveryFixture
from ..production_delivery.gateway import FixtureDeliveryGateway
from ..production_delivery.authorization import RecipientRecord
from ..production_delivery.review_bridge import DeliveryReviewBridge
from ..production_delivery.store import DeliveryStore, StoreConflict
from ..production_identity.policy import PermissionDenied
from ..production_identity.tokens import TokenError
from ..production_review.service import FixtureReviewService
from ..production_review.store import ReviewStore
from . import contracts as c

PROBE_NAMES = (
    "policy_required_before_execution", "canonical_review_independence",
    "recipient_forged_expired_wrong_case", "evidence_integrity_before_writer",
    "candidate_integrity_before_activation", "direct_object_route_absent",
    "grant_revocation_before_writer", "admitted_partial_and_unknown_writes_not_refunded",
    "external_floor_rejects_rollback", "gateway_and_review_restart_do_not_restore_authority",
    "valid_current_positive_control",
)
_EXPECTED = MappingProxyType({
    "policy_required_before_execution": ("current_scope_denied",),
    "canonical_review_independence": ("current_scope_denied",),
    "recipient_forged_expired_wrong_case": ("token_rejected", "current_scope_denied"),
    "evidence_integrity_before_writer": ("current_scope_denied",),
    "candidate_integrity_before_activation": ("current_scope_denied",),
    "direct_object_route_absent": ("http_404",),
    "grant_revocation_before_writer": ("durable_conflict",),
    "admitted_partial_and_unknown_writes_not_refunded": ("durable_conflict",),
    "external_floor_rejects_rollback": ("durable_conflict",),
    "gateway_and_review_restart_do_not_restore_authority": ("durable_conflict", "current_scope_denied"),
    "valid_current_positive_control": (),
})
_DENIALS = {PermissionDenied: "current_scope_denied", TokenError: "token_rejected", StoreConflict: "durable_conflict"}


def probe_plan():
    """Fresh owned deterministic plan; no caller-selected probe or threshold."""
    return {"schema": "mra-local-adversarial-probe-plan/v1", "profile": "local_public_fixture",
        "data_profile": "sklearn-wine", "max_rows": 128, "seed": 20261001,
        "workflow": "prd18_native_review_delivery", "external_sacro_tested": False,
        "synthetic_clock_start": 1000, "expiry_probe_clock_advance_seconds": 1,
        "activation_ttl_seconds": 30, "grant_ttl_seconds": 20, "chunk_bytes": 128,
        "probes": [{"name": name, "expected_denials": list(_EXPECTED[name])} for name in PROBE_NAMES], **c.FLAGS}


def _require(condition):
    if not condition:
        raise c.AssessmentError("A fixed local adversarial probe failed")


def _denial(action, expected):
    """Only enumerated expected control rejections count; unrelated errors escape."""
    try:
        action()
    except expected as error:
        code = _DENIALS.get(type(error))
        _require(code is not None)
        return code
    raise c.AssessmentError("Expected control rejection did not occur")


_OBSERVATIONS = {
    "policy_required_before_execution": {"policy_approved_before_fit": True, "rejected_output_created": False,
        "review_head_unchanged_on_rejection": True},
    "canonical_review_independence": {"distinct_current_reviews_usable": True, "owner_alias_denials": 2,
        "early_activation_denied": True, "operator_approval_denied": True},
    "recipient_forged_expired_wrong_case": {"writer_calls": 0, "admission_delta": 0,
        "independent_current_controls": True, "synthetic_clock_advanced_seconds": 1},
    "evidence_integrity_before_writer": {"writer_calls": 0, "admission_delta": 0, "exact_repair_verified": True},
    "candidate_integrity_before_activation": {"writer_calls": 0, "admission_delta": 0, "exact_repair_verified": True},
    "direct_object_route_absent": {"status_code": 404, "admission_delta": 0, "candidate_returned": False},
    "grant_revocation_before_writer": {"writer_calls": 0, "admission_delta": 0, "grant_revocation_retained": True},
    "admitted_partial_and_unknown_writes_not_refunded": {"durable_admissions": 2, "attempted_bytes": 256,
        "known_partial_bytes": 1, "unknown_extent": True, "recipient_receipt_verified": False,
        "duplicate_admission_delta": 0, "disclosure_may_have_occurred": True},
    "external_floor_rejects_rollback": {"admission_delta": 0, "newer_floor_preserved": True,
        "historical_copy_only": True, "independent_custody_verified": False},
    "gateway_and_review_restart_do_not_restore_authority": {"writer_calls": 0, "admission_delta": 0,
        "current_valid_control_before_restart": True, "historical_review_retained": True, "restarted_reviews_usable": False},
    "valid_current_positive_control": {"successful_exact_byte_writes": 4, "chunk_bytes": 128,
        "recipient_receipt_verified": False, "checks_after_exact_repairs": 2},
}
_OBSERVED = {
    "policy_required_before_execution": ["current_scope_denied"],
    "canonical_review_independence": ["current_scope_denied"] * 4,
    "recipient_forged_expired_wrong_case": ["token_rejected", "current_scope_denied", "current_scope_denied", "token_rejected"],
    "evidence_integrity_before_writer": ["current_scope_denied"],
    "candidate_integrity_before_activation": ["current_scope_denied"] * 2,
    "direct_object_route_absent": ["http_404"],
    "grant_revocation_before_writer": ["durable_conflict"],
    "admitted_partial_and_unknown_writes_not_refunded": ["durable_conflict"] * 2,
    "external_floor_rejects_rollback": ["durable_conflict"],
    "gateway_and_review_restart_do_not_restore_authority": ["durable_conflict", "current_scope_denied", "current_scope_denied"],
    "valid_current_positive_control": [],
}
_SUMMARY = {"fresh_native_runs": 1, "profile_id": "sklearn-wine", "max_rows": 128,
    "probes_passed": 11, "positive_controls": 4, "expected_exception_denials": 19,
    "direct_http_denials": 1, "durable_admissions": 6, "uncertain_write_admissions": 2,
    "synthetic_clock_start": 1000, "synthetic_clock_end": 1001,
    "external_sacro_tested": False, "recipient_receipt_verified": False}


def validate_result(value):
    """Strict owned successful receipt; booleans cannot impersonate counts.

    This validates the fixed claim structure, not an arbitrary caller's proof
    of execution. The packet producer must invoke the trusted live probes.
    """
    value = c.strict_json(c.canonical_bytes(value))
    _require(type(value) is dict and set(value) == {"schema", "status", "plan_sha256", "probes", "summary", "evidence_hashes", *c.FLAGS})
    _require(value["schema"] == "mra-local-adversarial-probes/v1" and value["status"] == "passed"
        and value["plan_sha256"] == c.digest(probe_plan())
        and all(value[key] is expected for key, expected in c.FLAGS.items()))
    expected = [{"name": name, "status": "passed", "expected_denials": list(_EXPECTED[name]),
                 "observed_denials": _OBSERVED[name], "observations": _OBSERVATIONS[name]} for name in PROBE_NAMES]
    _require(c.canonical_bytes(value["probes"]) == c.canonical_bytes(expected)
             and c.canonical_bytes(value["summary"]) == c.canonical_bytes(_SUMMARY))
    hashes = value["evidence_hashes"]
    _require(type(hashes) is dict and set(hashes) == {"candidate_sha256", "policy_sha256", "binding_sha256",
        "final_delivery_head_sha256", "positive_chunks_sha256"})
    for digest in hashes.values():
        c.validate_digest(digest)
    return value


class _Writer:
    def __init__(self):
        self.calls = 0
        self.content = []

    def __call__(self, raw):
        self.calls += 1
        self.content.append(bytes(raw))
        return len(raw)


class _Probes:
    def __init__(self, fixture):
        self.f = fixture
        self.gateway = fixture.gateway
        self.rows = {}
        self.denials = 0
        self.positive = 0
        self.positive_hashes = []

    def state(self):
        return self.f.store.get("case-a", expected_pin=self.gateway.required_pin, guard=self.f.review_fixture.clock)

    def row(self, name, codes, **observations):
        _require(name in PROBE_NAMES and name not in self.rows and set(codes).issubset(_EXPECTED[name]))
        self.rows[name] = {"name": name, "status": "passed", "expected_denials": list(_EXPECTED[name]),
                           "observed_denials": list(codes), "observations": observations}

    def rejected(self, action, expected, *, writer=None, review_unchanged=False):
        before = self.state()
        review_before = self.f.review_fixture.store.get("case-a", guard=self.f.review_fixture.clock)["head_sha256"]
        code = _denial(action, expected)
        after = self.state()
        _require(before["pin"] == after["pin"] and before["admissions"] == after["admissions"])
        _require(writer is None or writer.calls == 0)
        if review_unchanged:
            _require(review_before == self.f.review_fixture.store.get("case-a", guard=self.f.review_fixture.clock)["head_sha256"])
        self.denials += 1
        return code

    def live(self, activation, grant=None):
        current = self.f.review.status(self.f.token("auditor"), "case-a", self.f.campaign_id)
        _require(current["reviews_usable"] is True)
        state = self.state()
        record = state["activations"][activation]
        _require(record["state"] == "active" and self.f.now < record["payload"]["expires_at"])
        if grant is not None:
            record = state["grants"][grant]
            _require(not record["revoked"] and self.f.now < record["payload"]["expires_at"])

    def positive_control(self, transfer, offset, candidate):
        token, activation, grant, transfer_id = transfer
        self.live(activation, grant)
        before = self.state()
        writer = _Writer()
        receipt = self.gateway.deliver_chunk(token, "case-a", activation, grant, transfer_id, offset, 128, writer=writer)
        after = self.state()
        _require(writer.calls == 1 and b"".join(writer.content) == candidate[offset:offset + 128]
            and receipt["bytes_written"] == 128 and receipt["status"] == "returned"
            and receipt["observation_recorded"] is True and receipt["recipient_receipt_verified"] is False
            and len(after["admissions"]) == len(before["admissions"]) + 1)
        self.positive += 1
        self.positive_hashes.append(hashlib.sha256(writer.content[0]).hexdigest())
        return receipt

    def transfer(self, activation):
        token = self.f.token("recipient")
        grant_id, grant = self.f.grant(activation, token)
        return token, activation, grant_id, grant["payload"]["transfer_id"]

    def emit(self, transfer, writer, *, offset=384, token=None, gateway=None, **kwargs):
        original, activation, grant, transfer_id = transfer
        return (gateway or self.gateway).deliver_chunk(token or original, "case-a", activation,
            grant, transfer_id, offset, 128, writer=writer, **kwargs)


def run_probes(output, *, profile="agency_private_cloud"):
    c.require_local(profile)  # Refuse before root creation, source reads or fitting.
    root = io.fresh_directory(output)
    plan = probe_plan()
    plan_raw = c.canonical_bytes(plan)
    io.exclusive_write(root / "plan.json", plan_raw)
    fixture = DeliveryFixture(root / "fixture")
    probes = _Probes(fixture)
    foundation, review = fixture.review_fixture, fixture.review
    campaign_id, _ = foundation.propose()
    fixture.campaign_id = campaign_id
    code = probes.rejected(lambda: fixture.bridge.execute(fixture.token("operator"), "case-a", campaign_id,
        output=fixture.output), (PermissionDenied,), review_unchanged=True)
    _require(not fixture.output.exists())
    approved = review.approve_policy(fixture.token("policy"), "case-a", campaign_id)
    _require(approved["campaigns"][campaign_id]["state"] == "approved" and not fixture.output.exists()
             and io.read_file(root / "plan.json", 65536) == plan_raw)
    probes.row("policy_required_before_execution", [code], policy_approved_before_fit=True,
               rejected_output_created=False, review_head_unchanged_on_rejection=True)
    fixture.bridge.execute(fixture.token("operator"), "case-a", campaign_id, output=fixture.output)
    codes = [probes.rejected(lambda subject=subject: review.assess(fixture.token(subject), "case-a", campaign_id),
                            (PermissionDenied,), review_unchanged=True) for subject in ("owner", "owner-alias")]
    codes.append(probes.rejected(lambda: fixture.gateway.activate(fixture.token("releaser"), "case-a", campaign_id,
        profile="local_public_fixture"), (PermissionDenied,)))
    review.assess(fixture.token("assessor"), "case-a", campaign_id)
    codes.append(probes.rejected(lambda: review.approve(fixture.token("operator"), "case-a", campaign_id),
                                (PermissionDenied,), review_unchanged=True))
    reviewed = review.approve(fixture.token("releaser"), "case-a", campaign_id)
    probes.row("canonical_review_independence", codes, distinct_current_reviews_usable=True,
               owner_alias_denials=2, early_activation_denied=True, operator_approval_denied=True)
    campaign = reviewed["campaigns"][campaign_id]
    candidate_path = fixture.output / "native/candidate.json"
    candidate = io.read_file(candidate_path, 2 * 1024 * 1024)
    activation_id, activation = fixture.activate()
    _require(activation["payload"]["artifact_sha256"] == hashlib.sha256(candidate).hexdigest())
    transfer = probes.transfer(activation_id)
    probes.positive_control(transfer, 0, candidate)

    evidence_path = fixture.output / "replay-admission.json"
    original_evidence = io.read_file(evidence_path, 65536)
    probes.live(activation_id, transfer[2])
    writer = _Writer()
    try:
        evidence_path.write_bytes(original_evidence + b" ")
        code = probes.rejected(lambda: probes.emit(transfer, writer, offset=128), (PermissionDenied,), writer=writer)
    finally:
        evidence_path.write_bytes(original_evidence)
    _require(io.read_file(evidence_path, 65536) == original_evidence)
    probes.positive_control(transfer, 128, candidate)
    probes.row("evidence_integrity_before_writer", [code], writer_calls=0, admission_delta=0, exact_repair_verified=True)

    probes.live(activation_id, transfer[2])
    writer = _Writer()
    try:
        candidate_path.write_bytes(candidate + b" ")
        codes = [probes.rejected(lambda: fixture.gateway.activate(fixture.token("releaser"), "case-a", campaign_id,
            profile="local_public_fixture"), (PermissionDenied,))]
        codes.append(probes.rejected(lambda: probes.emit(transfer, writer, offset=256), (PermissionDenied,), writer=writer))
    finally:
        candidate_path.write_bytes(candidate)
    _require(io.read_file(candidate_path, 2 * 1024 * 1024) == candidate)
    probes.positive_control(transfer, 256, candidate)
    probes.row("candidate_integrity_before_activation", codes, writer_calls=0, admission_delta=0, exact_repair_verified=True)

    from fastapi.testclient import TestClient
    from ..production_delivery.api import create_fixture_app
    before = probes.state()
    with TestClient(create_fixture_app(fixture.gateway, profile="local_public_fixture")) as client:
        response = client.get("/v1/objects/" + hashlib.sha256(candidate).hexdigest(),
                              headers={"Authorization": "Bearer " + transfer[0]})
    _require(response.status_code == 404 and response.headers["cache-control"] == "no-store"
             and probes.state()["pin"] == before["pin"] and candidate not in response.content)
    probes.row("direct_object_route_absent", ["http_404"], status_code=404, admission_delta=0, candidate_returned=False)

    expiring = fixture.token("recipient", expires_at=1001)
    segments = transfer[0].split(".")
    segments[2] = ("A" if segments[2][0] != "A" else "B") + segments[2][1:]
    forged = ".".join(segments)
    codes = []
    for bad, expected in ((forged, (TokenError,)), (fixture.token("recipient", cases=["case-b"]), (PermissionDenied,)),
                          (fixture.token("auditor"), (PermissionDenied,))):
        probes.live(activation_id, transfer[2])
        writer = _Writer()
        codes.append(probes.rejected(lambda bad=bad: probes.emit(transfer, writer, token=bad), expected, writer=writer))
    fixture.now = 1001  # Forward only, with every original lifetime unchanged.
    probes.live(activation_id, transfer[2])
    writer = _Writer()
    codes.append(probes.rejected(lambda: probes.emit(transfer, writer, token=expiring), (TokenError,), writer=writer))
    probes.row("recipient_forged_expired_wrong_case", codes, writer_calls=0, admission_delta=0,
               independent_current_controls=True, synthetic_clock_advanced_seconds=1)

    probes.live(activation_id, transfer[2])
    fixture.gateway.revoke_grant(fixture.token("releaser"), "case-a", transfer[2])
    writer = _Writer()
    code = probes.rejected(lambda: probes.emit(transfer, writer), (StoreConflict,), writer=writer)
    probes.row("grant_revocation_before_writer", [code], writer_calls=0, admission_delta=0, grant_revocation_retained=True)

    partial_transfer = probes.transfer(activation_id)
    probes.live(activation_id, partial_transfer[2])
    partial = probes.emit(partial_transfer, lambda raw: 1, offset=0)
    uncertain_transfer = probes.transfer(activation_id)
    probes.live(activation_id, uncertain_transfer[2])
    escaped = []
    def uncertain_writer(raw):
        escaped.append(raw[:1])
        raise OSError("Fixed local interruption")
    unknown = probes.emit(uncertain_transfer, uncertain_writer, offset=0)
    codes = []
    for current, receipt in ((partial_transfer, partial), (uncertain_transfer, unknown)):
        state = probes.state()
        _require(receipt["admission"]["request_id"] in state["admissions"]
            and state["grants"][current[2]]["attempted_bytes"] == 128
            and receipt["observation_recorded"] is True and receipt["recipient_receipt_verified"] is False)
        writer = _Writer()
        codes.append(probes.rejected(lambda current=current, receipt=receipt: probes.emit(current, writer, offset=0,
            request_id=receipt["admission"]["request_id"], chunk_id=receipt["admission"]["chunk_id"]),
            (StoreConflict,), writer=writer))
    _require(partial["status"] == "interrupted" and partial["bytes_written"] == 1
        and partial["write_extent_known"] is True and unknown["status"] == "failed"
        and unknown["bytes_written"] is None and unknown["write_extent_known"] is False
        and unknown["disclosure_may_have_occurred"] is True and escaped == [candidate[:1]])
    probes.row("admitted_partial_and_unknown_writes_not_refunded", codes, durable_admissions=2,
        attempted_bytes=256, known_partial_bytes=1, unknown_extent=True, recipient_receipt_verified=False,
        duplicate_admission_delta=0, disclosure_may_have_occurred=True)

    second_activation, _ = fixture.activate()
    final_transfer = probes.transfer(second_activation)
    probes.positive_control(final_transfer, 0, candidate)
    rollback_root = io.fresh_directory(root / "older-delivery-copy")
    older = io.read_file(fixture.store.root / "delivery.sqlite", 32 * 1024 * 1024)
    io.exclusive_write(rollback_root / "delivery.sqlite", older)
    fixture.gateway.revoke(fixture.token("releaser"), "case-a", activation_id)
    final_pin = fixture.gateway.required_pin
    code = probes.rejected(lambda: DeliveryStore.open(rollback_root, expected_pin=final_pin), (StoreConflict,))
    _require(fixture.checkpoint_sink.read() == final_pin)
    probes.row("external_floor_rejects_rollback", [code], admission_delta=0, newer_floor_preserved=True,
               historical_copy_only=True, independent_custody_verified=False)

    probes.live(second_activation, final_transfer[2])
    recipients = (RecipientRecord("fixture-recipient", "agency", "project", "case-a", frozenset({"person-recipient"})),)
    replacement = FixtureDeliveryGateway(fixture.bridge, fixture.store, recipients,
        expected_pin=final_pin, checkpoint_sink=fixture.checkpoint_sink)
    writer = _Writer()
    codes = [probes.rejected(lambda: probes.emit(final_transfer, writer, offset=128), (StoreConflict,), writer=writer)]
    codes.append(probes.rejected(lambda: probes.emit(final_transfer, writer, offset=128, gateway=replacement),
                                (PermissionDenied,), writer=writer))
    restarted_review = FixtureReviewService(fixture.identity,
        ReviewStore.open(foundation.store.root, foundation.store.store_id), foundation.workflow)
    status = restarted_review.status(fixture.token("auditor"), "case-a", campaign_id)
    _require(status["reviews_usable"] is False and status["campaign"] == campaign)
    restarted_gateway = FixtureDeliveryGateway(DeliveryReviewBridge(restarted_review), fixture.store, recipients,
        expected_pin=replacement.required_pin, checkpoint_sink=fixture.checkpoint_sink)
    codes.append(probes.rejected(lambda: probes.emit(final_transfer, writer, offset=128, gateway=restarted_gateway),
                                (PermissionDenied,), writer=writer))
    probes.row("gateway_and_review_restart_do_not_restore_authority", codes, writer_calls=0,
        admission_delta=0, current_valid_control_before_restart=True, historical_review_retained=True,
        restarted_reviews_usable=False)
    probes.row("valid_current_positive_control", [], successful_exact_byte_writes=probes.positive,
               chunk_bytes=128, recipient_receipt_verified=False, checks_after_exact_repairs=2)
    _require(set(probes.rows) == set(PROBE_NAMES) and probes.positive == 4
        and io.read_file(root / "plan.json", 65536) == plan_raw)
    final = probes.state()
    report = {"schema": "mra-local-adversarial-probes/v1", "status": "passed", "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "probes": [probes.rows[name] for name in PROBE_NAMES],
        "summary": {"fresh_native_runs": 1, "profile_id": "sklearn-wine", "max_rows": 128,
            "probes_passed": 11, "positive_controls": probes.positive, "expected_exception_denials": probes.denials,
            "direct_http_denials": 1, "durable_admissions": len(final["admissions"]), "uncertain_write_admissions": 2,
            "synthetic_clock_start": 1000, "synthetic_clock_end": fixture.now,
            "external_sacro_tested": False, "recipient_receipt_verified": False},
        "evidence_hashes": {"candidate_sha256": hashlib.sha256(candidate).hexdigest(),
            "policy_sha256": campaign["policy_sha256"], "binding_sha256": campaign["binding_sha256"],
            "final_delivery_head_sha256": final["head_sha256"], "positive_chunks_sha256": c.digest(probes.positive_hashes)}, **c.FLAGS}
    report = validate_result(report)
    io.exclusive_write(root / "probes.json", c.canonical_bytes(report))
    return report
