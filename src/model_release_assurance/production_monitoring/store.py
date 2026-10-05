"""Bounded local monitoring history and alert outbox; no notification authority.

Trusted Python instrumentation supplies already redacted events. Operators must
be authorized by a facade using the current guard. A retained receiver pin is a
local custody claim, never proof of external sending, human receipt or recovery.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from . import contracts as c

MAX_DATABASE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 2048
_DATABASE = "monitor.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE records (sequence INTEGER PRIMARY KEY, record_sha256 TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL) STRICT",
)
_META = {"store_id", "record_count", "head_sha256", "last_clock"}
_ZERO = "0" * 64


class MonitorError(ValueError):
    """Rejected trusted-local monitoring operation."""


class MonitorConflict(MonitorError):
    """A permanent identity, current checkpoint or transition conflicts."""


class MonitorUnavailable(MonitorError):
    """Local history, filesystem or trusted current time is unavailable."""


def _unavailable():
    raise MonitorUnavailable("Local monitoring state unavailable")


def _conflict():
    raise MonitorConflict("Local monitoring operation conflicts")


def _identity(info):
    return info.st_dev, info.st_ino


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directories(path):
    if ".." in path.parts or str(path).startswith(("//", "\\\\")):
        _unavailable()
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            _unavailable()


def _owned(value, maximum=65536):
    return c.strict_json(c.canonical_bytes(value, max_bytes=maximum), max_bytes=maximum)


def _same(left, right):
    return c.canonical_bytes(left) == c.canonical_bytes(right)


def _decode(text):
    if type(text) is not str:
        _unavailable()
    raw = text.encode("ascii")
    value = c.strict_json(raw)
    if c.canonical_bytes(value) != raw:
        _unavailable()
    return value


def _blank():
    return {"count": 0, "head": _ZERO, "clock": 0, "pins": {0: _ZERO},
            "events": {}, "incidents": {}, "alerts": {}, "operations": {},
            "active": {}, "latest": {}}


def _action_payload(operation_id, incident_id, action, actor, at):
    c.hex_id(operation_id); c.hex_id(incident_id); c.integer(at)
    if type(action) is not str or action not in {"acknowledge", "resolve"}:
        raise MonitorError("Local incident action rejected")
    return {"operation_id": operation_id, "incident_id": incident_id, "action": action,
            "actor": c.validate_actor(actor), "at": at}


def _ack_payload(operation_id, alert_id, receiver_pin, at):
    c.hex_id(operation_id); c.hex_id(alert_id); c.integer(at)
    return {"operation_id": operation_id, "alert_id": alert_id,
            "receiver_pin": c.validate_pin(receiver_pin), "at": at}


class MonitorStore:
    """Append-only full replay with external ancestor floors and current write CAS."""
    def __init__(self, root, *, expected_pin):
        pin = c.validate_pin(expected_pin)
        self._store_id = pin["store_id"]
        self._initial_pin = None
        try:
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE
            _directories(self.root)
            self._root_identity = _identity(self.root.lstat())
            self._db_identity = _identity(self._path.lstat())
            with self._connect() as db:
                db.execute("BEGIN")
                try:
                    self._floor(self._validate(db), pin)
                    self._paths()
                finally:
                    db.rollback()
        except OSError:
            raise MonitorUnavailable("Local monitoring open unavailable") from None

    @property
    def root(self):
        return self._root

    @property
    def store_id(self):
        return self._store_id

    @property
    def initial_pin(self):
        if self._initial_pin is None:
            raise MonitorError("Initial checkpoint exists only after creation")
        return _owned(self._initial_pin)

    @classmethod
    def open(cls, root, *, expected_pin):
        return cls(root, expected_pin=expected_pin)

    @classmethod
    def create(cls, root, profile="agency_private_cloud"):
        if type(profile) is not str or profile != "local_public_fixture":
            raise MonitorError("Production monitoring is not available")
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            _directories(root)
            path = root / _DATABASE
            with path.open("xb"):
                pass
            store = object.__new__(cls)
            store._root, store._path, store._store_id = root, path, secrets.token_hex(16)
            store._root_identity, store._db_identity = _identity(root.lstat()), _identity(path.lstat())
            store._initial_pin = None
            with closing(sqlite3.connect(path, timeout=3, isolation_level=None)) as db:
                db.enable_load_extension(False)
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA page_size=4096")
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA max_page_count=2048")
                db.execute("BEGIN IMMEDIATE")
                for statement in _SCHEMA:
                    db.execute(statement)
                db.execute("PRAGMA user_version=1")
                meta = {"store_id": store.store_id, "record_count": 0, "head_sha256": _ZERO, "last_clock": 0}
                db.executemany("INSERT INTO meta VALUES (?,?)", [(k, c.canonical_bytes(v).decode("ascii")) for k, v in meta.items()])
                store._validate(db)
                store._paths()
                db.commit()
            store._initial_pin = store._pin(_blank())
            return store
        except (OSError, sqlite3.Error):
            raise MonitorUnavailable("Local monitoring creation unavailable") from None

    def _paths(self):
        try:
            _directories(self.root)
            if _identity(self.root.lstat()) != self._root_identity:
                _unavailable()
            info = self._path.lstat()
            if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or _identity(info) != self._db_identity or info.st_size > MAX_DATABASE_BYTES):
                _unavailable()
            for suffix in ("-journal", "-wal", "-shm"):
                try:
                    side = (self.root / (_DATABASE + suffix)).lstat()
                except FileNotFoundError:
                    continue
                if (suffix != "-journal" or _unsafe(side) or not stat.S_ISREG(side.st_mode)
                        or side.st_nlink != 1 or side.st_size > MAX_DATABASE_BYTES + 65536):
                    _unavailable()
        except OSError:
            raise MonitorUnavailable("Local monitoring filesystem unavailable") from None

    @contextmanager
    def _connect(self):
        db = None
        try:
            self._paths()
            db = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=3, isolation_level=None)
            db.enable_load_extension(False)
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA max_page_count=2048")
            if db.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                _unavailable()
            self._paths()
            yield db
        except sqlite3.Error:
            raise MonitorUnavailable("Local monitoring database unavailable") from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _clock(guard, floor):
        if not callable(guard):
            raise MonitorError("A trusted current guard is required")
        now = guard()  # Authorization errors must propagate, never be rewritten as availability.
        if type(now) is not int or not floor <= now <= 2**53-1:
            _unavailable()
        return now

    @staticmethod
    def _meta(db, key, value):
        db.execute("UPDATE meta SET value=? WHERE key=?", (c.canonical_bytes(value).decode("ascii"), key))

    def _pin(self, state):
        return {"schema": "mra-fixture-monitor-pin/v1", "store_id": self.store_id,
                "sequence": state["count"], "head_sha256": state["head"]}

    def _floor(self, state, pin):
        if pin["store_id"] != self.store_id or state["pins"].get(pin["sequence"]) != pin["head_sha256"]:
            _conflict()

    def _current(self, state, pin):
        if not _same(self._pin(state), pin):
            _conflict()

    @staticmethod
    def _payload(kind, payload):
        if type(payload) is not dict:
            raise MonitorError("Local monitoring payload rejected")
        if kind == "event":
            return c.validate_event(payload)
        if kind == "action" and set(payload) == {"operation_id", "incident_id", "action", "actor", "at"}:
            return _action_payload(**payload)
        if kind == "ackalert" and set(payload) == {"operation_id", "alert_id", "receiver_pin", "at"}:
            return _ack_payload(**payload)
        raise MonitorError("Local monitoring record rejected")

    @staticmethod
    def _transition(state, kind, payload, at):
        if kind == "event":
            event = payload
            key = (event["resource_id"], event["code"])
            if event["event_id"] in state["events"] or event["observed_at"] > at:
                _conflict()
            previous = state["latest"].get(key)
            if previous is not None and event["observed_at"] < previous["observed_at"]:
                _conflict()
            state["events"][event["event_id"]] = event
            state["latest"][key] = event
            identifier = state["active"].get(key)
            if event["condition"] == "fault":
                if identifier is None:
                    identifier = event["event_id"]
                    state["incidents"][identifier] = {"id": identifier, "resource_id": event["resource_id"],
                        "code": event["code"], "status": "open", "first_at": event["observed_at"],
                        "latest_event_id": event["event_id"]}
                    state["active"][key] = identifier
                rule = c.RULES[event["code"]]
                state["alerts"][event["event_id"]] = {"alert_id": event["event_id"], "incident_id": identifier,
                    "event": event, "route": rule["route"], "severity": rule["severity"], "runbook": rule["runbook"],
                    "acknowledged": False, "receiver_pin": None}
            if identifier is not None:
                state["incidents"][identifier]["latest_event_id"] = event["event_id"]
        else:
            identifier = payload["operation_id"]
            if identifier in state["operations"] or not state["clock"] <= payload["at"] <= at:
                _conflict()
            if kind == "action":
                incident = state["incidents"].get(payload["incident_id"])
                if incident is None or payload["at"] < incident["first_at"]:
                    _conflict()
                if payload["action"] == "acknowledge":
                    if incident["status"] != "open":
                        _conflict()
                    incident["status"] = "acknowledged"
                else:
                    key = (incident["resource_id"], incident["code"])
                    latest = state["latest"][key]
                    if (incident["status"] != "acknowledged" or latest["condition"] != "healthy"
                            or payload["at"] < latest["observed_at"]):
                        _conflict()
                    incident["status"] = "resolved"
                    del state["active"][key]
            else:
                alert = state["alerts"].get(payload["alert_id"])
                if (alert is None or alert["acknowledged"] or payload["at"] < alert["event"]["observed_at"]
                        or payload["receiver_pin"]["sequence"] == 0):
                    _conflict()
                alert["acknowledged"] = True
                alert["receiver_pin"] = payload["receiver_pin"]
            state["operations"][identifier] = {"kind": kind, **payload}

    def _apply(self, state, record, record_sha256):
        if type(record) is not dict or set(record) != {"schema", "store_id", "sequence", "previous_sha256", "kind", "payload", "at"}:
            _unavailable()
        c.validate_digest(record_sha256)
        if (record["schema"] != "mra-fixture-monitor-history/v1" or record["store_id"] != self.store_id
                or type(record["sequence"]) is not int or record["sequence"] != state["count"] + 1
                or record["previous_sha256"] != state["head"] or c.digest(record) != record_sha256):
            _unavailable()
        at = c.integer(record["at"])
        if at < state["clock"] or state["count"] >= MAX_RECORDS:
            _unavailable()
        payload = self._payload(record["kind"], record["payload"])
        self._transition(state, record["kind"], payload, at)
        state["count"], state["head"], state["clock"] = record["sequence"], record_sha256, at
        state["pins"][state["count"]] = record_sha256

    def _validate(self, db):
        """Pure replay of captured SQLite state; uses only the expected store UUID."""
        try:
            expected = sorted(("table", name, name, sql) for name, sql in zip(("meta", "records"), _SCHEMA))
            rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            if ([tuple(row) for row in rows] != expected or db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or db.execute("PRAGMA application_id").fetchone()[0] != 0
                    or db.execute("PRAGMA page_size").fetchone()[0] != 4096
                    or db.execute("PRAGMA page_count").fetchone()[0] > 2048):
                _unavailable()
            values = db.execute("SELECT key,value FROM meta LIMIT 5").fetchall()
            if len(values) != 4 or {row[0] for row in values} != _META:
                _unavailable()
            meta = {key: _decode(value) for key, value in values}
            c.hex_id(meta["store_id"]); c.validate_digest(meta["head_sha256"])
            c.integer(meta["record_count"], 0, MAX_RECORDS); c.integer(meta["last_clock"])
            if meta["store_id"] != self.store_id:
                _unavailable()
            state = _blank()
            records = db.execute("SELECT sequence,record_sha256,record_json FROM records ORDER BY sequence LIMIT ?", (MAX_RECORDS+1,)).fetchall()
            if len(records) != meta["record_count"]:
                _unavailable()
            for sequence, record_sha256, raw in records:
                if sequence != state["count"] + 1:
                    _unavailable()
                self._apply(state, _decode(raw), record_sha256)
            if meta["head_sha256"] != state["head"] or meta["last_clock"] < state["clock"]:
                _unavailable()
            state["clock"] = meta["last_clock"]
            return state
        except (ValueError, TypeError, KeyError, UnicodeError, IndexError, sqlite3.Error):
            raise MonitorUnavailable("Local monitoring history rejected") from None

    def _append(self, db, state, kind, payload, now):
        if state["count"] >= MAX_RECORDS:
            _conflict()
        record = {"schema": "mra-fixture-monitor-history/v1", "store_id": self.store_id,
            "sequence": state["count"]+1, "previous_sha256": state["head"], "kind": kind, "payload": payload, "at": now}
        record_sha256 = c.digest(record)
        self._apply(state, record, record_sha256)
        db.execute("INSERT INTO records VALUES (?,?,?)", (state["count"], record_sha256, c.canonical_bytes(record).decode("ascii")))
        for key, value in (("record_count", state["count"]), ("head_sha256", state["head"]), ("last_clock", now)):
            self._meta(db, key, value)

    def _snapshot(self, state):
        return _owned({"schema": "mra-fixture-monitor-state/v1", "pin": self._pin(state),
            **{key: list(state[key].values()) for key in ("events", "incidents", "alerts", "operations")}, **c.FLAGS}, MAX_DATABASE_BYTES)

    @contextmanager
    def _transaction(self, expected_pin, guard):
        pin = c.validate_pin(expected_pin)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                state = self._validate(db)
                self._floor(state, pin)
                now = self._clock(guard, state["clock"])
                yield db, state, now, pin
                replayed = self._validate(db)
                if self._snapshot(replayed) != self._snapshot(state):
                    _unavailable()
                self._paths()
                self._meta(db, "last_clock", self._clock(guard, max(now, replayed["clock"])))
                self._paths()
                db.commit()
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise

    def read(self, *, expected_pin, guard):
        with self._transaction(expected_pin, guard) as (_, state, _, _):
            result = self._snapshot(state)
        return result

    def _write(self, kind, payload, *, expected_pin, guard):
        payload = self._payload(kind, payload)  # Own all input before invoking callbacks.
        with self._transaction(expected_pin, guard) as (db, state, now, pin):
            self._current(state, pin)
            if kind == "event":
                existing = state["events"].get(payload["event_id"])
                exact = payload
            else:
                existing = state["operations"].get(payload["operation_id"])
                exact = {"kind": kind, **payload}
            if existing is not None:
                if not _same(existing, exact):
                    _conflict()
            else:
                self._append(db, state, kind, payload, now)
            result = self._snapshot(state)
        return result

    def record(self, event, *, expected_pin, guard):
        return self._write("event", event, expected_pin=expected_pin, guard=guard)

    def action(self, operation_id, incident_id, action, actor, *, at, expected_pin, guard):
        payload = _action_payload(operation_id, incident_id, action, actor, at)
        return self._write("action", payload, expected_pin=expected_pin, guard=guard)

    def acknowledge_alert(self, operation_id, alert_id, receiver_pin, *, at, expected_pin, guard):
        payload = _ack_payload(operation_id, alert_id, receiver_pin, at)
        return self._write("ackalert", payload, expected_pin=expected_pin, guard=guard)
