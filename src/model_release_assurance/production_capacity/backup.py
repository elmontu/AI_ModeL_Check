"""Quiesced historical registry/witness images, never restored live authority.

The caller holds the shared identity lock before capture. We reserve registry
then witness against writers and serialize the SAME validated SQLite handles.
External manifest/registry/witness pins are mandatory on verify and restore.
No service constructor, broker activation, current grant or release is restored.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from itertools import islice
import hashlib
from pathlib import Path
import sqlite3
import time

from . import contracts as c
from . import io
from ..production_registry import store as registry_module
from ..production_registry import contracts as registry_contracts
from ..production_registry.contracts import account_id
from ..production_witness import store as witness_module
from ..production_witness import contracts as witness_contracts
from ..production_witness.contracts import validate_pin as witness_pin

REGISTRY_LIMIT = 16 * 1024 * 1024
WITNESS_LIMIT = 32 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024
MANIFEST_LIMIT = 65536
_FILES = {"registry.sqlite": REGISTRY_LIMIT, "witness.sqlite": WITNESS_LIMIT, "manifest.json": MANIFEST_LIMIT}
_NAMESPACE = account_id("agency", "project")
_ANCHOR = {"schema", "store_id", "schema_version", "namespace_id", "event_sequence",
           "event_head_sha256", "broker_epoch", "broker_id"}
_FLAGS_EXTRA = {"current_authorization_checked": False, "release_resumed": False,
                "historical_only": True, "independent_custody_verified": False}


def _fail():
    raise c.CapacityError("Historical fixture backup rejected")


def _generic(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            raise c.CapacityError("Historical fixture backup rejected") from None
    return wrapped


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _owned(value, maximum=MANIFEST_LIMIT):
    return c.strict_json(c.canonical_bytes(value, max_bytes=maximum), max_bytes=maximum)


def _same(left, right, maximum=MANIFEST_LIMIT):
    return c.canonical_bytes(left, max_bytes=maximum) == c.canonical_bytes(right, max_bytes=maximum)


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _fail()
    return value


def _flags():
    return {**c.FLAGS, **_FLAGS_EXTRA}


def _validate_anchor(value):
    value = _owned(_exact(value, _ANCHOR))
    if (value["schema"] != "mra-fixture-registry-backup-anchor/v1"
            or type(value["schema_version"]) is not int or value["schema_version"] != 2
            or value["namespace_id"] != _NAMESPACE):
        _fail()
    c.hex_id(value["store_id"])
    c.integer(value["event_sequence"], 1, 2048)
    c.integer(value["broker_epoch"], 0, value["event_sequence"])
    c.validate_digest(value["event_head_sha256"])
    if value["event_head_sha256"] == "0"*64:
        _fail()
    if value["broker_id"] is not None:
        c.hex_id(value["broker_id"])
    return value


def _anchor(store, state):
    if set(state["accounts"]) != {_NAMESPACE}:
        _fail()
    account = state["accounts"][_NAMESPACE]
    if (account["agency_id"], account["project_id"]) != ("agency", "project"):
        _fail()
    return _validate_anchor({"schema": "mra-fixture-registry-backup-anchor/v1",
        "store_id": store.store_id, "schema_version": state["version"], "namespace_id": _NAMESPACE,
        "event_sequence": state["count"], "event_head_sha256": state["head"],
        "broker_epoch": state["epoch"], "broker_id": state["broker_id"]})


def _clock(guard, floor):
    if not callable(guard):
        _fail()
    now = c.integer(guard())
    if now < floor:
        _fail()
    return now


def _registry_clock(connection, state):
    value = connection.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0]
    parsed = c.integer(int(value))
    if str(parsed) != value or parsed < state["clock"]:
        _fail()
    return parsed


def _events(connection):
    rows = connection.execute("SELECT event_sha256,event_json FROM events ORDER BY sequence LIMIT 2049").fetchall()
    if not 1 <= len(rows) <= 2048:
        _fail()
    return [{"event_sha256": row[0], "event": c.strict_json(row[1].encode("ascii"))} for row in rows]


def _implementation_sha256():
    directory = Path(__file__).absolute().parent
    # The frozen historical validators are executable dependencies of this
    # receipt, not merely imported data. Bind their exact installed sources.
    sources = {"production_capacity/"+name: directory/name
               for name in ("backup.py", "contracts.py", "io.py")}
    for package, module, contract in (
            ("production_registry", registry_module, registry_contracts),
            ("production_witness", witness_module, witness_contracts)):
        sources[package+"/store.py"] = Path(module.__file__).absolute()
        sources[package+"/contracts.py"] = Path(contract.__file__).absolute()
    return c.digest({name: _sha(io.read_file(path, 1024*1024))
                     for name, path in sorted(sources.items())})


@contextmanager
def _captured_database(raw, maximum):
    if type(raw) is not bytes or not 4096 <= len(raw) <= maximum or len(raw) % 4096:
        _fail()
    db = sqlite3.connect(":memory:", isolation_level=None)
    try:
        db.enable_load_extension(False)
        db.deserialize(raw)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA query_only=ON")
        work = [0]
        def budget():
            work[0] += 1000
            return int(work[0] > 10_000_000)
        db.set_progress_handler(budget, 1000)
        yield db
    finally:
        db.close()


def _table_digest(table):
    # Bind full values, while keeping each record within the old 64KiB domain.
    return c.digest([[key, c.digest(value)] for key, value in sorted(table.items())])


def _replay_images(registry_raw, witness_raw, anchor, pin):
    """Replay only owned bytes with externally pinned identities; no disk opens."""
    if len(registry_raw) + len(witness_raw) > TOTAL_LIMIT:
        _fail()
    registry = object.__new__(registry_module.RegistryStore)
    registry._store_id, registry._version = anchor["store_id"], anchor["schema_version"]
    witness = object.__new__(witness_module.WitnessStore)
    witness._witness_id, witness._namespace_id, witness._registry_id = (
        pin["witness_id"], pin["namespace_id"], pin["registry_id"])
    if pin["namespace_id"] != _NAMESPACE or pin["registry_id"] != anchor["store_id"]:
        _fail()
    with _captured_database(registry_raw, REGISTRY_LIMIT) as rdb, _captured_database(witness_raw, WITNESS_LIMIT) as wdb:
        registry_state = registry._validate(rdb)
        if not _same(_anchor(registry, registry_state), anchor):
            _fail()
        events = _events(rdb)
        witness_state = witness._validate(wdb)
        witness._floor(witness_state, pin)
        if not _same(witness._pin(witness_state), pin):
            _fail()  # This bundle is an exact cut, not a later descendant.
        diagnosis = witness._diagnosis(witness_state)
        history = witness_state["history"]
        if (not diagnosis["reconciled"] or diagnosis["pending_intents"] != 0
                or history["event_sequence"] != anchor["event_sequence"]
                or history["event_head_sha256"] != anchor["event_head_sha256"]
                or history["schema_version"] != anchor["schema_version"]
                or history["broker_epoch"] != anchor["broker_epoch"]
                or history["broker_id"] != anchor["broker_id"]
                or not _same(history["events"], events, 16*1024*1024)):
            _fail()
        receipts = registry_state["receipts"]
        retained = {row["intent"]["request"]["request_id"]: row["receipt"]
                    for row in witness_state["intents"].values() if row["state"] == "committed"}
        expected = {row["receipt"]["request_id"]: row for row in receipts.values()}
        if not _same(retained, expected, 16*1024*1024):
            _fail()
        charged = registry_state["accounts"][_NAMESPACE]["total_engineering_charge_units"]
        if charged != len(receipts) or len(registry_state["outbox"]) != len(receipts):
            _fail()
        acknowledged = sum(value["acknowledgment"] is not None for value in registry_state["deliveries"].values())
        return {"engineering_charge_units": charged, "receipt_count": len(receipts),
            "outbox_count": len(registry_state["outbox"]), "outbox_acknowledged": acknowledged,
            "outbox_pending": len(registry_state["outbox"])-acknowledged,
            "committed_intents": diagnosis["committed_intents"], "pending_intents": 0,
            "aborted_intents": diagnosis["aborted_intents"],
            **{name+"_sha256": _table_digest(registry_state[name])
               for name in ("receipts", "outbox", "deliveries", "accounts", "cases")},
            "registry_events_sha256": c.digest(events, max_bytes=16*1024*1024)}


def _manifest(images, anchor, pin, evidence, implementation):
    return {"schema": "mra-fixture-recovery-bundle/v1", "profile": "local_public_fixture",
        "registry_anchor": anchor, "witness_pin": pin, "implementation_sha256": implementation,
        "files": {name: {"sha256": _sha(raw), "size_bytes": len(raw)} for name, raw in sorted(images.items())},
        "evidence": evidence, **_flags()}


def _check_manifest(raw, images, expected_sha, anchor, pin):
    c.validate_digest(expected_sha)
    if _sha(raw) != expected_sha:
        _fail()
    manifest = c.strict_json(raw)
    if c.canonical_bytes(manifest) != raw:
        _fail()
    evidence = _replay_images(images["registry.sqlite"], images["witness.sqlite"], anchor, pin)
    wanted = _manifest(images, anchor, pin, evidence, _implementation_sha256())
    if not _same(manifest, wanted):
        _fail()
    return {"schema": "mra-fixture-recovery-verification/v1", "status": "historical_backup_verified",
        "manifest_sha256": expected_sha, "registry_anchor": anchor, "witness_pin": pin,
        "evidence": evidence, "captured_bytes": sum(len(raw) for raw in images.values()), **_flags()}


def _identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino


def _inventory(root):
    root = Path(root).absolute()
    io.directory(root)
    identity = _identity(root)
    paths = list(islice(root.iterdir(), 4))
    if len(paths) != 3 or {path.name for path in paths} != set(_FILES):
        _fail()
    files = {name: _identity(root/name) for name in _FILES}
    blobs = {name: io.read_file(root/name, maximum) for name, maximum in _FILES.items()}
    io.directory(root)
    if (_identity(root) != identity or sum(map(len, blobs.values())) > TOTAL_LIMIT
            or any(_identity(root/name) != expected for name, expected in files.items())):
        _fail()
    return blobs, {"directory": identity, "files": files}


def _assert_same_inventory(root, blobs, identity):
    final, final_identity = _inventory(root)
    if final != blobs or final_identity != identity:
        _fail()


@_generic
def registry_anchor(registry, *, guard):
    """Observe an exact historical head under a writer reservation; no activation."""
    if type(registry) is not registry_module.RegistryStore or registry.schema_version != 2:
        _fail()
    with registry._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            state = registry._validate(db)
            now = _clock(guard, _registry_clock(db, state))
            result = _anchor(registry, state)
            final = registry._validate(db)
            if not _same(_anchor(registry, final), result):
                _fail()
            _clock(guard, max(now, _registry_clock(db, final)))
            registry._paths()
            return result
        finally:
            db.rollback()


@_generic
def capture_quiesced(registry, witness, output, *, expected_registry_anchor, expected_witness_pin,
                     guard, profile="agency_private_cloud"):
    """Caller holds identity lock; acquire registry then witness, without writes."""
    c.require_local(profile)
    started = time.perf_counter_ns()
    anchor, pin = _validate_anchor(expected_registry_anchor), witness_pin(expected_witness_pin)
    if (type(registry) is not registry_module.RegistryStore or type(witness) is not witness_module.WitnessStore
            or registry.store_id != anchor["store_id"] or witness.witness_id != pin["witness_id"]):
        _fail()
    implementation = _implementation_sha256()
    with registry._connect() as rdb:
        rdb.execute("BEGIN IMMEDIATE")
        try:
            with witness._connect() as wdb:
                wdb.execute("BEGIN IMMEDIATE")
                try:
                    rstate, wstate = registry._validate(rdb), witness._validate(wdb)
                    now = _clock(guard, max(_registry_clock(rdb, rstate), wstate["clock"]))
                    if (not _same(_anchor(registry, rstate), anchor)
                            or not _same(witness._pin(wstate), pin)):
                        _fail()
                    images = {"registry.sqlite": rdb.serialize(), "witness.sqlite": wdb.serialize()}
                    evidence = _replay_images(images["registry.sqlite"], images["witness.sqlite"], anchor, pin)
                    manifest = _manifest(images, anchor, pin, evidence, implementation)
                    raw = c.canonical_bytes(manifest)
                    report = _check_manifest(raw, images, _sha(raw), anchor, pin)
                    # Validation and serialization precede any destination creation.
                    current_r, current_w = registry._validate(rdb), witness._validate(wdb)
                    if (not _same(_anchor(registry, current_r), anchor)
                            or not _same(witness._pin(current_w), pin)
                            or rdb.serialize() != images["registry.sqlite"]
                            or wdb.serialize() != images["witness.sqlite"]):
                        _fail()
                    now = _clock(guard, max(now, _registry_clock(rdb, current_r), current_w["clock"]))
                    registry._paths(); witness._paths()
                    destination = Path(output).absolute()
                    io.fresh_directory(destination)
                    destination_identity = _identity(destination)
                    for name, value in images.items():
                        io.exclusive_write(destination/name, value)
                    io.exclusive_write(destination/"manifest.json", raw)
                    captured, captured_identity = _inventory(destination)
                    if (captured_identity["directory"] != destination_identity
                            or captured != {**images, "manifest.json": raw}
                            or _implementation_sha256() != implementation):
                        _fail()
                    _clock(guard, now)
                    registry._paths(); witness._paths()
                    report["capture_elapsed_ns"] = time.perf_counter_ns()-started
                    return report
                finally:
                    wdb.rollback()
        finally:
            rdb.rollback()


@_generic
def verify_backup(root, *, expected_manifest_sha256, expected_registry_anchor, expected_witness_pin):
    """Pure historical replay; externally retained pins cannot be discovered here."""
    anchor, pin = _validate_anchor(expected_registry_anchor), witness_pin(expected_witness_pin)
    blobs, identity = _inventory(root)
    images = {name: blobs[name] for name in ("registry.sqlite", "witness.sqlite")}
    result = _check_manifest(blobs["manifest.json"], images, expected_manifest_sha256, anchor, pin)
    _assert_same_inventory(root, blobs, identity)
    return result


@_generic
def restore_backup(root, output, *, expected_manifest_sha256, expected_registry_anchor,
                   expected_witness_pin, profile="agency_private_cloud"):
    """Restore only inert historical images to a new directory; no live service."""
    c.require_local(profile)
    started = time.perf_counter_ns()
    anchor, pin = _validate_anchor(expected_registry_anchor), witness_pin(expected_witness_pin)
    blobs, source_identity = _inventory(root)
    images = {name: blobs[name] for name in ("registry.sqlite", "witness.sqlite")}
    _check_manifest(blobs["manifest.json"], images, expected_manifest_sha256, anchor, pin)
    destination = Path(output).absolute()
    io.fresh_directory(destination)
    destination_identity = _identity(destination)
    for name in ("registry.sqlite", "witness.sqlite", "manifest.json"):
        io.exclusive_write(destination/name, blobs[name])
    result = verify_backup(destination, expected_manifest_sha256=expected_manifest_sha256,
                           expected_registry_anchor=anchor, expected_witness_pin=pin)
    _assert_same_inventory(root, blobs, source_identity)
    if _identity(destination) != destination_identity:
        _fail()
    return {**result, "status": "historical_restore_verified", "restore_elapsed_ns": time.perf_counter_ns()-started}
