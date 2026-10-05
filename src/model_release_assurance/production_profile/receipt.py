"""Bounded historical fixture receipts; no current release or agency authority.

The detached key is ephemeral and public-only on disk. Verification requires
independently supplied exact-byte receipt/key pins. Replaying captured SQLite
bytes and retained predictions does not attest original training, external
execution, current identity permissions, independent custody or recipient receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding

from .contracts import FLAGS as PROFILE_FLAGS
from ..production_evidence import contracts as evidence
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes as numeric_bytes, strict_json as numeric_json
from ..production_evidence.replay import replay_native_bundle, artifact_manifest
from ..production_evidence.signing import _envelope
from ..production_trust.registry import KeyRegistration, TrustProfile
from ..production_review import store as reviews
from ..production_registration import store as registrations
from ..production_delivery import store as deliveries
from ..production_evidence import ledger as replay_ledger

DOMAIN = b"mra-public-profile-receipt/v1\x00"
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 256
MAX_RECEIPT_BYTES = 1024 * 1024
FLAGS = {**PROFILE_FLAGS, "fixture_only": True, "production_authorized": False, "authorization_eligible": False,
         "model_delivery": False, "can_clear": False, "privacy_accounting_supported": False,
         "current_authorization_checked": False, "original_training_attested": False,
         "external_execution_attested": False, "recipient_receipt_verified": False,
         "independent_custody_verified": False, "agency_trust_established": False}
NATIVE_NAMES = tuple(sorted(("dataset.json", "plan.json", "candidate.json", "report.json",
                            "scores.json", "predictions.json", "replay.json", "result.json")))
TRAINING_NAMES = ("registration.json", "reservation.json", "training-start.json", "replay-context.json",
                  "replay-challenge.json", "replay-envelope.json", "replay-admission.json", "review.json",
                  "registration-record.json", "result.json")
FILE_BOUNDS = {
    **{"fixture/training/native/"+name: 32*1024*1024 for name in NATIVE_NAMES},
    **{"fixture/training/"+name: 65536 for name in TRAINING_NAMES},
    "fixture/evidence-key.json": 65536,
    "fixture/review/reviews/reviews.sqlite": 16*1024*1024,
    "fixture/review/registrations/registrations.sqlite": 16*1024*1024,
    "fixture/review/replay-ledger/replay.sqlite": 16*1024*1024,
    "fixture/delivery/delivery.sqlite": 32*1024*1024,
    "journal/journal.sqlite": 16*1024*1024,
    "external/input.json": 16*1024*1024, "external/plan.json": 2*1024*1024,
    "external/worker/worker.json": 4*1024*1024, "external/worker/process.json": 65536,
    "external/comparison.json": 4*1024*1024, "external/result.json": 4*1024*1024,
    "external/worker/stdout.log": 65536, "external/worker/stderr.log": 65536,
    "combined-binding.json": 65536, "delivery-summary.json": 65536, "lifecycle.json": 65536,
}
OPTIONAL_BOUNDS = {"external/worker/cache/fontlist-v3.11.0.json": 1024*1024}
# The pinned SACRO constructor creates these directories even with reporting
# disabled. No files or additional descendants inside them are accepted.
UPSTREAM_DIRECTORIES = frozenset({
    "external/worker/target", "external/worker/target/shadow_models",
    "external/worker/positive", "external/worker/positive/shadow_models",
    "external/worker/null", "external/worker/null/shadow_models",
})
# These later driver diagnostics are not authorization or replay inputs. They
# are never parsed as evidence and their content cannot alter verification.
DIAGNOSTIC_FILES = frozenset({"result.json", "source.json"})
SEAL_FILES = frozenset({"receipt.json", "public-key.pem", "signature.bin"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CHECKPOINT = re.compile(r"fixture/checkpoints/([1-9][0-9]{0,3})\.json\Z")


class ReceiptError(ValueError):
    """The bounded historical receipt cannot be established."""


def _fail():
    raise ReceiptError("Historical public-fixture receipt rejected")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(numeric_bytes(value))


def _same(left, right):
    return numeric_bytes(left) == numeric_bytes(right)


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys): _fail()
    return value


def _hash(value):
    if type(value) is not str or not _SHA.fullmatch(value): _fail()
    return value


def _integer(value, minimum=0, maximum=2**53-1):
    if type(value) is not int or not minimum <= value <= maximum: _fail()
    return value


def _id(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directory(path):
    if ".." in path.parts or str(path).startswith(("//", "\\\\")): _fail()
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode): _fail()


def _read(path, maximum, *, empty=False):
    _directory(path.parent)
    before = path.lstat()
    def valid(info):
        return (not _unsafe(info) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and (0 if empty else 1) <= info.st_size <= maximum)
    if not valid(before): _fail()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not valid(opened) or _id(opened) != _id(before): _fail()
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    final = path.lstat()
    if (not valid(after) or not valid(final) or _id(opened) != _id(after) or _id(after) != _id(final)
            or len(raw) != final.st_size or len(raw) > maximum): _fail()
    _directory(path.parent)
    return raw


def _inventory(root, *, sealed):
    root = Path(root).absolute(); _directory(root)
    before = root.lstat()
    names, todo, directories = [], [(root, 0)], {}
    while todo:
        parent, depth = todo.pop()
        if depth > 8: _fail()
        directories[parent] = (parent.lstat().st_dev, parent.lstat().st_ino)
        for path in parent.iterdir():
            if len(names) + len(todo) + len(directories) > MAX_FILES*2: _fail()
            info = path.lstat()
            if _unsafe(info): _fail()
            if stat.S_ISDIR(info.st_mode):
                directory_name = path.relative_to(root).as_posix()
                allowed = any(name.startswith(directory_name+"/") for name in (*FILE_BOUNDS, *OPTIONAL_BOUNDS))
                if (not allowed and directory_name not in UPSTREAM_DIRECTORIES
                        and directory_name not in ("fixture/checkpoints", "external/worker/temporary")): _fail()
                todo.append((path, depth+1)); continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: _fail()
            name = path.relative_to(root).as_posix()
            if name in DIAGNOSTIC_FILES:
                if info.st_size > MAX_RECEIPT_BYTES: _fail()
                continue
            if name in SEAL_FILES:
                if not sealed: _fail()
                continue
            if name not in FILE_BOUNDS and name not in OPTIONAL_BOUNDS and not _CHECKPOINT.fullmatch(name): _fail()
            names.append(name)
            if len(names) > MAX_FILES: _fail()
    if not set(FILE_BOUNDS) <= set(names): _fail()
    blobs = {}
    total = 0
    for name in sorted(names):
        bound = FILE_BOUNDS.get(name, OPTIONAL_BOUNDS.get(name, 65536))
        raw = _read(root/name, bound, empty=name.endswith(("stdout.log", "stderr.log")))
        total += len(raw)
        if total > MAX_TOTAL_BYTES: _fail()
        blobs[name] = raw
    for path, identity in directories.items():
        info = path.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identity: _fail()
    if (root.lstat().st_dev, root.lstat().st_ino) != (before.st_dev, before.st_ino): _fail()
    return blobs


def _manifest(blobs):
    return {name: {"sha256": _sha(raw), "size_bytes": len(raw)} for name, raw in sorted(blobs.items())}


def _json(blobs, name):
    return numeric_json(blobs[name], maximum=FILE_BOUNDS.get(name, 65536))


@contextmanager
def _database(raw, schema):
    if type(raw) is not bytes or not 4096 <= len(raw) <= 32*1024*1024: _fail()
    connection = sqlite3.connect(":memory:")
    try:
        connection.enable_load_extension(False)
        connection.deserialize(raw)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        work = [0]
        def progress():
            work[0] += 1000
            return int(work[0] > 2_000_000)
        connection.set_progress_handler(progress, 1000)
        rows = connection.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if (len(rows) != len(schema) or any(row["type"] != "table" for row in rows)
                or {row["sql"] for row in rows} != set(schema)): _fail()
        yield connection
    finally:
        connection.close()


def _store_state(raw, module, cls, *, identity=None):
    with _database(raw, module._SCHEMA) as connection:
        values = dict(connection.execute("SELECT key,value FROM meta").fetchall())
        value = values.get("store_id")
        if module in (reviews, deliveries): value = module._decode(value.encode("ascii"))
        if type(value) is not str or not re.fullmatch("[0-9a-f]{32}", value): _fail()
        if identity is not None and identity != value: _fail()
        store = object.__new__(cls); store._store_id = value
        state = store._validate(connection)
        rows = connection.execute("SELECT event_json FROM events ORDER BY sequence").fetchall()
        events = [module._decode(row[0].encode("ascii")) for row in rows]
        return value, state, events


def _historical_signature(raw, public_record):
    _exact(public_record, {"schema", "key_id", "profile", "owner_id", "not_before", "not_after", "public_key_pem", "fingerprint"})
    if public_record["schema"] != "mra-public-profile-evidence-key/v1": _fail()
    _exact(public_record["profile"], {"agency_id", "environment", "issuer", "audience", "purpose"})
    profile = TrustProfile(**public_record["profile"])
    record = KeyRegistration(public_record["key_id"], profile, public_record["owner_id"],
                             public_record["public_key_pem"], public_record["not_before"], public_record["not_after"])
    if (profile.purpose != "worker_evidence" or record.fingerprint != public_record["fingerprint"]
            or record.public_key_pem.decode("ascii") != public_record["public_key_pem"]): _fail()
    envelope, signature, message = _envelope(raw, profile, record.owner_id)
    if envelope["key_id"] != record.key_id or envelope["key_fingerprint"] != record.fingerprint: _fail()
    statement = envelope["statement"]
    if (not record.not_before <= statement["issued_at"] < statement["expires_at"] <= record.not_after
            or statement["context"]["agency_id"] != profile.agency_id
            or statement["context"]["worker_id"] != record.owner_id): _fail()
    record.public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
    return statement


def _write(path, raw):
    with path.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def seal_receipt(root, *, journal_pin, delivery_pin):
    """Create detached historical evidence, never a reusable admission token."""
    try:
        root = Path(root).absolute()
        _directory(root); root_identity = (root.lstat().st_dev, root.lstat().st_ino)
        journal_pin = numeric_json(numeric_bytes(journal_pin))
        delivery_pin = numeric_json(numeric_bytes(delivery_pin))
        blobs = _inventory(root, sealed=False)
        replay = _semantic_capture(root, blobs, journal_pin=journal_pin, delivery_pin=delivery_pin)
        receipt = {"schema": "mra-public-profile-receipt/v1", "environment": "public_fixture",
                   "profile_id": "sklearn-wine", "files": _manifest(blobs), "journal_pin": journal_pin,
                   "delivery_pin": delivery_pin, "historical_replay": replay, **FLAGS}
        raw = numeric_bytes(receipt)
        if len(raw) > MAX_RECEIPT_BYTES: _fail()
        private = ed25519.Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        signature = private.sign(DOMAIN + raw)
        if (_inventory(root, sealed=False) != blobs
                or (root.lstat().st_dev, root.lstat().st_ino) != root_identity): _fail()
        _write(root/"receipt.json", raw)
        _write(root/"public-key.pem", public)
        _write(root/"signature.bin", signature)
        pins = {"receipt_sha256": _sha(raw), "key_sha256": _sha(public)}
        verify_receipt(root, expected_receipt_sha256=pins["receipt_sha256"], expected_key_sha256=pins["key_sha256"])
        return pins
    except Exception:
        raise ReceiptError("Historical public-fixture receipt rejected") from None


def verify_receipt(root, *, expected_receipt_sha256, expected_key_sha256):
    """Read-only replay with mandatory external pins; never check current grants."""
    try:
        _hash(expected_receipt_sha256); _hash(expected_key_sha256)
        root = Path(root).absolute()
        _directory(root); root_identity = (root.lstat().st_dev, root.lstat().st_ino)
        raw = _read(root/"receipt.json", MAX_RECEIPT_BYTES)
        public = _read(root/"public-key.pem", 4096)
        signature = _read(root/"signature.bin", 64)
        if len(signature) != 64 or _sha(raw) != expected_receipt_sha256 or _sha(public) != expected_key_sha256: _fail()
        key = serialization.load_pem_public_key(public)
        if not isinstance(key, ed25519.Ed25519PublicKey) or key.public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo) != public: _fail()
        key.verify(signature, DOMAIN + raw)
        receipt = numeric_json(raw, maximum=MAX_RECEIPT_BYTES)
        _exact(receipt, {"schema", "environment", "profile_id", "files", "journal_pin", "delivery_pin", "historical_replay", *FLAGS})
        if (receipt["schema"] != "mra-public-profile-receipt/v1" or receipt["environment"] != "public_fixture"
                or receipt["profile_id"] != "sklearn-wine" or not _same({k: receipt[k] for k in FLAGS}, FLAGS)
                or numeric_bytes(receipt) != raw): _fail()
        blobs = _inventory(root, sealed=True)
        if not _same(receipt["files"], _manifest(blobs)): _fail()
        replay = _semantic_capture(root, blobs, journal_pin=receipt["journal_pin"], delivery_pin=receipt["delivery_pin"])
        if not _same(replay, receipt["historical_replay"]): _fail()
        if (_inventory(root, sealed=True) != blobs or _read(root/"receipt.json", MAX_RECEIPT_BYTES) != raw
                or _read(root/"public-key.pem", 4096) != public or _read(root/"signature.bin", 64) != signature
                or (root.lstat().st_dev, root.lstat().st_ino) != root_identity): _fail()
        return {"schema": "mra-public-profile-receipt-verification/v1", "status": "historical_fixture_replay_verified",
                "receipt_sha256": expected_receipt_sha256, "key_sha256": expected_key_sha256,
                "files_verified": len(blobs), "historical_replay": replay, **FLAGS}
    except Exception:
        raise ReceiptError("Historical public-fixture receipt rejected") from None


def _journal(raw, expected_pin):
    from . import journal
    from .contracts import validate_pin
    pin = validate_pin(expected_pin)
    with _database(raw, journal._SCHEMA) as connection:
        item = object.__new__(journal.Journal); item._store_id = pin["store_id"]
        state = item._validate(connection)
        item._floor(state, pin)
        snapshot = item._snapshot(state)
        if not _same(snapshot["pin"], pin) or snapshot["stage"] != "complete": _fail()
        return snapshot


def _registration(blobs, native_blobs, plan):
    from ..production_registration.contracts import build_registration, evaluate_native
    from ..production_registration.profiles import load_profile
    from ..production_registration.workflow import prepare_native_input, workflow_sha256, FLAGS as RUN_FLAGS
    record = _json(blobs, "fixture/training/registration-record.json")
    registration = _json(blobs, "fixture/training/registration.json")
    ledger_id, state, events = _store_state(blobs["fixture/review/registrations/registrations.sqlite"],
                                          registrations, registrations.RegistrationStore)
    identifier = registration["registration_id"]
    if (set(state["registrations"]) != {identifier} or not _same(state["registrations"][identifier], record)
            or record["state"] != "completed" or len(events) != 3
            or [event["kind"] for event in events] != ["registered", "training", "completed"]
            or not _same(record["registration"], registration)
            or [record[k] for k in ("registered_sequence", "training_sequence", "terminal_sequence")] != [1, 2, 3]): _fail()
    data = load_profile("sklearn-wine", max_rows=128)
    data, data_raw, plan_raw = prepare_native_input(data, 20261001)
    if data_raw != native_blobs["dataset.json"] or plan_raw != native_blobs["plan.json"]: _fail()
    rebuilt = build_registration(registration_id=identifier, agency_id=plan["agency_id"], project_id=plan["project_id"],
        case_id=plan["case_id"], profile_id="sklearn-wine", data=data, data_bytes=data_raw, plan_bytes=plan_raw,
        history=registration["history"], workflow_sha256=workflow_sha256(), runtime_sha256=registration["plan"]["runtime_sha256"])
    if not _same(rebuilt, registration): _fail()
    expected_review = evaluate_native(registration, native_blobs)
    if not _same(expected_review, _json(blobs, "fixture/training/review.json")): _fail()
    for index, (name, status) in enumerate((("reservation.json", "registered"), ("training-start.json", "training"))):
        event = events[index]
        ticket = {"ledger_id": ledger_id, "registration_id": identifier,
            "registration_sha256": _digest(registration), "scope_id": event["scope_id"],
            "sequence": event["scope_sequence"], "head_sha256": _digest(event), "state": status}
        if not _same(_json(blobs, "fixture/training/"+name), ticket): _fail()
    expected_result = {"schema": "mra-prospective-training-run/v1", "status": "review_recorded",
        "profile_id": "sklearn-wine", "registration_id": identifier, "registration_sha256": _digest(registration),
        "error": None, "review": expected_review, **RUN_FLAGS}
    if not _same(expected_result, _json(blobs, "fixture/training/result.json")): _fail()
    return registration, record, events, expected_review


def _evidence(blobs, native_blobs, registration, record, reg_events, native_replay):
    from ..production_evidence.verifier import FLAGS as ADMISSION_FLAGS
    envelope = blobs["fixture/training/replay-envelope.json"]
    key = _json(blobs, "fixture/evidence-key.json")
    statement = _historical_signature(envelope, key)
    context, challenge = statement["context"], statement["challenge"]
    if (not _same(context, _json(blobs, "fixture/training/replay-context.json"))
            or not _same(challenge, _json(blobs, "fixture/training/replay-challenge.json"))
            or not _same(statement["artifacts"], artifact_manifest(native_blobs))): _fail()
    start = reg_events[1]
    started_history = {"ledger_id": start["ledger_id"], "scope_id": start["scope_id"],
        "sequence": 2, "head_sha256": _digest(start), "local_registrations": 1, "known_disclosures": 0,
        "external_history": "unknown", "privacy_accounting_supported": False}
    expected_context = {"schema": "mra-execution-context/v1", "operation": "retained_native_replay",
        "environment": "public_fixture", "agency_id": registration["agency_id"], "project_id": registration["project_id"],
        "case_id": registration["case_id"], "job_id": registration["registration_id"], "attempt_id": context["attempt_id"],
        "fence": 1, "worker_id": key["owner_id"],
        "job_sha256": _digest({"registration_sha256": _digest(registration), "started_history": started_history,
                               "artifacts": artifact_manifest(native_blobs)}),
        "source_sha256": registration["source"]["source_sha256"], "policy_sha256": _digest(registration),
        "plan_sha256": _sha(native_blobs["plan.json"]), "adapter_sha256": native.implementation_sha256(),
        "runtime_sha256": registration["plan"]["runtime_sha256"], "image_sha256": None}
    if not _same(context, expected_context): _fail()
    with _database(blobs["fixture/review/replay-ledger/replay.sqlite"], replay_ledger._SCHEMA) as connection:
        ledger = object.__new__(replay_ledger.ReplayLedger); ledger._ledger_id = challenge["ledger_id"]
        ledger._validate(connection)
        rows = connection.execute("SELECT * FROM challenges").fetchall()
        if len(rows) != 1: _fail()
        row = rows[0]
        if not _same(ledger._challenge(row), challenge) or row["envelope_sha256"] != _sha(envelope): _fail()
        consumed = {"schema": "mra-evidence-consumption/v1", "ledger_id": challenge["ledger_id"],
            "nonce": challenge["nonce"], "context_sha256": challenge["context_sha256"],
            "execution_sha256": challenge["execution_sha256"], "envelope_sha256": _sha(envelope),
            "consumed_at": row["consumed_at"]}
    admission = {"schema": "mra-local-evidence-admission/v1", "status": "accepted_local_replay",
        "context_sha256": _digest(context), "artifacts_sha256": _digest(artifact_manifest(native_blobs)),
        "envelope_sha256": _sha(envelope), "key_id": key["key_id"], "key_fingerprint": key["fingerprint"],
        "consumption": consumed, "replay": native_replay, **ADMISSION_FLAGS}
    if not _same(admission, _json(blobs, "fixture/training/replay-admission.json")): _fail()
    completion = {"registration_sha256": _digest(registration), "artifacts_sha256": _digest(artifact_manifest(native_blobs)),
        "candidate_sha256": _sha(native_blobs["candidate.json"]), "report_sha256": _sha(native_blobs["report.json"]),
        "evidence_envelope_sha256": _sha(envelope), "evidence_admission_sha256": _digest(admission),
        "review": _json(blobs, "fixture/training/review.json")}
    if (not _same(record["completion"], completion)
            or not reg_events[1]["occurred_at"] <= statement["issued_at"] <= consumed["consumed_at"] <= reg_events[2]["occurred_at"]): _fail()
    return statement, admission


def _delivery(blobs, state, events, plan, campaign, delivery_pin):
    from .contracts import FLAGS as FIXTURE_FLAGS
    from ..production_delivery.contracts import validate_pin
    pin = validate_pin(delivery_pin)
    if pin["sequence"] != state["count"] or pin["head_sha256"] != state["head"]: _fail()
    case = state["cases"][plan["case_id"]]
    summary = _json(blobs, "delivery-summary.json")
    _exact(summary, {"schema", "activation_id", "grant_id", "transfer_id", "artifact_sha256", "artifact_size",
        "completed_chunks", "collected_sha256", "partial_request_id", "partial_attempted_bytes", "partial_bytes_written", *FIXTURE_FLAGS})
    if summary["schema"] != "mra-public-profile-delivery-summary/v1" or not _same({k: summary[k] for k in FIXTURE_FLAGS}, FIXTURE_FLAGS): _fail()
    aid, gid = summary["activation_id"], summary["grant_id"]
    activation, grant = case["activations"][aid], case["grants"][gid]
    raw = blobs["fixture/training/native/candidate.json"]
    if (state["artifacts"][aid] != raw or summary["artifact_sha256"] != _sha(raw)
            or type(summary["artifact_size"]) is not int or summary["artifact_size"] != len(raw)
            or summary["collected_sha256"] != _sha(raw)
            or grant["payload"]["activation_id"] != aid or grant["payload"]["transfer_id"] != summary["transfer_id"]): _fail()
    expected = {"campaign_id": plan["campaign_id"], "agency_id": plan["agency_id"], "project_id": plan["project_id"],
        "case_id": plan["case_id"], "recipient_id": plan["recipient_id"], "artifact_sha256": _sha(raw),
        "artifact_size": len(raw), "policy_sha256": campaign["policy_sha256"], "binding_sha256": campaign["binding_sha256"],
        "approval_sha256": campaign["approval"]["sha256"]}
    if not _same({key: activation["payload"][key] for key in expected}, expected): _fail()
    chunks = summary["completed_chunks"]
    if type(chunks) is not list or not 2 <= len(chunks) <= 256: _fail()
    offset, ids = 0, set()
    for chunk in chunks:
        _exact(chunk, {"request_id", "chunk_id", "offset", "length", "chunk_sha256", "bytes_written", "status", "write_extent_known", "observation_recorded"})
        admission = case["admissions"][chunk["request_id"]]
        observation = case["observations"][chunk["request_id"]]["payload"]
        expected_chunk = {key: admission[key] for key in ("request_id", "chunk_id", "offset", "length", "chunk_sha256")}
        expected_chunk.update(bytes_written=admission["length"], status="returned", write_extent_known=True, observation_recorded=True)
        if (not _same(chunk, expected_chunk) or admission["grant_id"] != gid or admission["offset"] != offset
                or chunk["request_id"] in ids or observation["status"] != "returned"
                or observation["bytes_written"] != admission["length"] or observation["write_extent_known"] is not True): _fail()
        ids.add(chunk["request_id"]); offset += admission["length"]
    if offset != len(raw) or grant["attempted_bytes"] != len(raw) or grant["next_offset"] != len(raw): _fail()
    if {r for r, row in case["admissions"].items() if row["grant_id"] == gid} != ids: _fail()
    partial = case["admissions"][summary["partial_request_id"]]
    observed = case["observations"][summary["partial_request_id"]]["payload"]
    if (not _same({k: summary[k] for k in ("partial_attempted_bytes", "partial_bytes_written")},
                  {"partial_attempted_bytes": 128, "partial_bytes_written": 1})
            or partial["activation_id"] != aid or partial["length"] != 128 or partial["offset"] != 0
            or observed["status"] != "interrupted" or observed["bytes_written"] != 1
            or observed["write_extent_known"] is not True or observed["recipient_receipt_verified"] is not False): _fail()
    lifecycle = _json(blobs, "lifecycle.json")
    _exact(lifecycle, {"schema", "checks", "activation_id", "live_grant_id", "partial_grant_id", "expiry_activation_id",
        "expiry_grant_id", "resumed_request_id", "expiry_at", *FIXTURE_FLAGS})
    checks = {name: True for name in ("suspension_denied", "resumed_fresh_admission", "grant_revocation_denied", "activation_revocation_permanent", "expiry_denied")}
    if (lifecycle["schema"] != "mra-public-profile-lifecycle/v1" or not _same(lifecycle["checks"], checks)
            or not _same({k: lifecycle[k] for k in FIXTURE_FLAGS}, FIXTURE_FLAGS)
            or lifecycle["activation_id"] != aid or lifecycle["expiry_activation_id"] != aid
            or lifecycle["partial_grant_id"] != partial["grant_id"] or lifecycle["expiry_grant_id"] != partial["grant_id"]
            or activation["state"] != "revoked"): _fail()
    declared_grants = {gid, lifecycle["live_grant_id"], lifecycle["partial_grant_id"]}
    if (len(declared_grants) != 3 or state["activation_ids"] != {aid}
            or state["grant_ids"] != declared_grants or set(case["grants"]) != declared_grants): _fail()
    live = case["grants"][lifecycle["live_grant_id"]]
    expiring = case["grants"][lifecycle["expiry_grant_id"]]
    _integer(lifecycle["expiry_at"])
    if (not live["revoked"] or expiring["revoked"] or lifecycle["expiry_at"] != expiring["payload"]["expires_at"]
            or state["clock"] < lifecycle["expiry_at"] or expiring["attempted_bytes"] != 128): _fail()
    resumed = case["admissions"][lifecycle["resumed_request_id"]]
    if resumed["grant_id"] != lifecycle["live_grant_id"] or resumed["offset"] != 128 or resumed["length"] != 128: _fail()
    live_admissions = {key: row for key, row in case["admissions"].items() if row["grant_id"] == lifecycle["live_grant_id"]}
    if (len(live_admissions) != 2 or sorted(row["offset"] for row in live_admissions.values()) != [0, 128]
            or any(row["length"] != 128 for row in live_admissions.values()) or live["attempted_bytes"] != 256
            or set(case["admissions"]) != ids | {summary["partial_request_id"]} | set(live_admissions)
            or set(case["observations"]) != set(case["admissions"])
            or state["request_ids"] != set(case["admissions"])
            or any(case["observations"][key]["payload"]["status"] != "returned"
                   or case["observations"][key]["payload"]["bytes_written"] != 128
                   or case["observations"][key]["payload"]["write_extent_known"] is not True for key in live_admissions)): _fail()
    lifecycle_ops = [event for event in events if event["operation"] in ("suspend", "resume", "revoke")
                     and event["payload"]["activation_id"] == aid]
    if [event["operation"] for event in lifecycle_ops] != ["suspend", "resume", "revoke"]: _fail()
    resumed_event = next(event for event in events if event["operation"] == "admit" and event["payload"]["request_id"] == lifecycle["resumed_request_id"])
    if not lifecycle_ops[1]["sequence"] < resumed_event["sequence"] < lifecycle_ops[2]["sequence"]: _fail()
    checkpoints = {int(_CHECKPOINT.fullmatch(name).group(1)): numeric_json(raw) for name, raw in blobs.items() if _CHECKPOINT.fullmatch(name)}
    if not checkpoints or max(checkpoints) != pin["sequence"] or not _same(checkpoints[pin["sequence"]], pin): _fail()
    for sequence, checkpoint in checkpoints.items():
        checked = validate_pin(checkpoint)
        if checked["store_id"] != pin["store_id"] or state["pins"].get(sequence) != checked["head_sha256"]: _fail()
    return summary, lifecycle, activation


def _semantic_capture(root, blobs, *, journal_pin, delivery_pin):
    """Recompute the cross-store story from captured bytes, not report booleans."""
    import math
    from .contracts import validate_pin, validate_delivery_pin
    from .runtime import validate_spec
    from .workflow import recipe_sha256, implementation_sha256, combined_binding, check_external
    from ..production_sacro.evidence import _capture
    from ..production_review.contracts import completion_binding
    journal_pin, delivery_pin = validate_pin(journal_pin), validate_delivery_pin(delivery_pin)
    journal = _journal(blobs["journal/journal.sqlite"], journal_pin)
    plan, stages = journal["plan"], journal["stages"]
    if plan["sacro_recipe_sha256"] != recipe_sha256() or plan["implementation_sha256"] != implementation_sha256(): _fail()
    native_blobs = {name: blobs["fixture/training/native/"+name] for name in NATIVE_NAMES}
    replay = replay_native_bundle(native_blobs)
    if replay["status"] != "passed": _fail()
    registration, record, reg_events, native_review = _registration(blobs, native_blobs, plan)
    statement, admission = _evidence(blobs, native_blobs, registration, record, reg_events, replay)
    review_id, review_state, review_events = _store_state(blobs["fixture/review/reviews/reviews.sqlite"], reviews, reviews.ReviewStore)
    campaigns = [(case, row) for case in review_state["cases"].values() for row in case["campaigns"].values()]
    if len(campaigns) != 1: _fail()
    case, campaign = campaigns[0]
    policy = campaign["policy"]
    if (campaign["state"] != "completed" or policy["campaign_id"] != plan["campaign_id"]
            or campaign["policy_sha256"] != plan["native_policy_sha256"]
            or any(policy[key] != plan[key] for key in ("agency_id", "project_id", "case_id", "recipient_id", "profile_id", "seed", "max_rows"))): _fail()
    source_bindings = {"source_sha256": registration["source"]["source_sha256"],
        "data_sha256": _sha(native_blobs["dataset.json"]), "metadata_sha256": registration["source"]["metadata_sha256"],
        "plan_sha256": _sha(native_blobs["plan.json"]), "workflow_sha256": registration["plan"]["workflow_sha256"],
        "runtime_sha256": registration["plan"]["runtime_sha256"], "adapter_sha256": native.implementation_sha256()}
    if not _same({key: policy[key] for key in source_bindings}, source_bindings): _fail()
    report = numeric_json(native_blobs["report.json"])
    gain = report["utility"]["accuracy"] - report["utility"]["majority_accuracy"]
    auc = report["membership"]["raw_auc"]
    completion = {"campaign_id": plan["campaign_id"], "policy_sha256": campaign["policy_sha256"],
        "registration_id": registration["registration_id"], "registration_sha256": _digest(registration),
        "candidate_sha256": _sha(native_blobs["candidate.json"]), "report_sha256": _sha(native_blobs["report.json"]),
        "artifacts_sha256": _digest(artifact_manifest(native_blobs)),
        "envelope_sha256": _sha(blobs["fixture/training/replay-envelope.json"]), "admission_sha256": _digest(admission),
        "context_sha256": _digest(statement["context"]), "utility_improvement_bps": max(-10000, min(10000, math.floor(gain*10000))),
        "membership_auc_bps": math.ceil(auc*10000) if auc >= .5 else math.floor(auc*10000)}
    if (not _same(campaign["completion"]["payload"], completion)
            or campaign["binding_sha256"] != completion_binding(policy, completion)
            or campaign["assessment"]["payload"]["verdict"] != "accept"): _fail()
    expected_native = {"campaign_id": plan["campaign_id"], "policy_sha256": campaign["policy_sha256"],
        "completion_sha256": campaign["completion"]["sha256"], "candidate_sha256": completion["candidate_sha256"],
        "binding_sha256": campaign["binding_sha256"], "registration_id": registration["registration_id"],
        "registration_sha256": _digest(registration)}
    if not _same(stages["native"]["payload"], expected_native): _fail()
    for stage, decision in (("planned", "policy_approval"), ("native", "start"), ("assess", "assessment"), ("approve", "approval")):
        if not _same(stages[stage]["actor"], campaign[decision]["actor"]): _fail()
    if (stages["planned"]["at"] > reg_events[0]["occurred_at"]
            or campaign["start"]["recorded_at"] > reg_events[0]["occurred_at"]
            or reg_events[2]["occurred_at"] > stages["native"]["at"]
            or campaign["policy_approval"]["recorded_at"] > stages["planned"]["at"]): _fail()
    _, external_native, external_raw, bindings = _capture(root/"fixture/training/native", root/"external")
    if external_native != native_blobs or any(blobs["external/"+name] != raw for name, raw in external_raw.items()): _fail()
    request = numeric_json(external_raw["input.json"], maximum=16*1024*1024)
    versions = validate_spec(request["versions"], plan["sacro_lock_sha256"])
    external_auc = check_external(external_raw, lock_sha256=plan["sacro_lock_sha256"], versions=versions,
                                  maximum=plan["max_external_auc_bps"])
    combined = combined_binding(journal["plan_sha256"], campaign["binding_sha256"], bindings)
    if not _same(combined, _json(blobs, "combined-binding.json")): _fail()
    expected_external = {"combined_sha256": _digest(combined), "files_sha256": _digest(bindings["comparison_files"]),
        "external_plan_sha256": _sha(external_raw["plan.json"]), "external_result_sha256": _sha(external_raw["result.json"])}
    if not _same(stages["external"]["payload"], expected_external): _fail()
    if not _same(stages["external"]["actor"], stages["native"]["actor"]): _fail()
    for stage, key in (("assess", "assessment"), ("approve", "approval")):
        if not stages["external"]["at"] <= campaign[key]["recorded_at"] <= stages[stage]["at"]: _fail()
        expected = {"combined_sha256": _digest(combined), "native_"+key+"_sha256": campaign[key]["sha256"]}
        if stage == "approve": expected["assessment_sha256"] = stages["assess"]["sha256"]
        if not _same(stages[stage]["payload"], expected): _fail()
    store_id, delivery_state, delivery_events = _store_state(blobs["fixture/delivery/delivery.sqlite"], deliveries,
        deliveries.DeliveryStore, identity=delivery_pin["store_id"])
    summary, lifecycle, activation = _delivery(blobs, delivery_state, delivery_events, plan, campaign, delivery_pin)
    if (activation["payload"]["review_store_id"] != review_id
            or activation["payload"]["review_head_sha256"] != review_state["head"]
            or not _same(stages["authorize"]["actor"], activation["actor"])
            or not stages["approve"]["at"] <= activation["recorded_at"] <= stages["authorize"]["at"]): _fail()
    authorization = stages["authorize"]["payload"]
    expected_authorization = {"combined_sha256": _digest(combined), "approval_sha256": stages["approve"]["sha256"],
        "activation_id": summary["activation_id"], "activation_sha256": activation["sha256"], "delivery_pin": authorization["delivery_pin"]}
    if not _same(authorization, expected_authorization): _fail()
    initial = validate_delivery_pin(authorization["delivery_pin"])
    if initial["store_id"] != store_id or delivery_state["pins"].get(initial["sequence"]) != initial["head_sha256"]: _fail()
    activate_event = next(event for event in delivery_events if event["operation"] == "activate"
                          and event["payload"]["activation_id"] == summary["activation_id"])
    if activate_event["sequence"] != initial["sequence"]: _fail()
    expected_complete = {"combined_sha256": _digest(combined), "activation_id": summary["activation_id"],
        "final_delivery_pin": delivery_pin, "delivery_summary_sha256": _digest(summary), "lifecycle_sha256": _digest(lifecycle)}
    if not _same(stages["complete"]["payload"], expected_complete): _fail()
    for event in delivery_events:
        if event["operation"] in ("activate", "grant", "admit", "resume"):
            if not statement["issued_at"] <= event["occurred_at"] < statement["expires_at"]: _fail()
        if event["operation"] == "admit" and event["occurred_at"] < stages["authorize"]["at"]: _fail()
    if delivery_events[-1]["occurred_at"] > stages["complete"]["at"]: _fail()
    return {"schema": "mra-public-profile-historical-checks/v1", "run_id": plan["run_id"],
        "campaign_id": plan["campaign_id"], "registration_id": registration["registration_id"],
        "profile_id": "sklearn-wine", "plan_sha256": journal["plan_sha256"],
        "combined_sha256": _digest(combined), "candidate_sha256": completion["candidate_sha256"],
        "native_artifacts_sha256": _digest(artifact_manifest(native_blobs)),
        "external_files_sha256": _digest(bindings["comparison_files"]), "external_max_auc_bps": external_auc,
        "registration_events": len(reg_events), "review_events": len(review_events), "delivery_events": len(delivery_events),
        "journal_events": journal_pin["sequence"], "completed_chunks": len(summary["completed_chunks"]),
        "collected_sha256": summary["collected_sha256"], "attempted_partial_bytes": 128, "observed_partial_bytes": 1,
        "signature_scope": "historical_local_receipt_integrity_with_external_pins",
        "negative_probe_scope": "trusted_fixture_observations_not_reconstructed_execution", **FLAGS}
