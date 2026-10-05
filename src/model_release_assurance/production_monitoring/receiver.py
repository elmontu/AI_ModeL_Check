"""Independent local alert metadata custody with durable exact deduplication.

This receiver performs no network sending. Its own retained checkpoint can
expose a prefix restore; coherent replacement of every trusted floor is outside
this trusted fixture. No private data, exception text or identity names enter.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat
import threading

from . import contracts as c
from .store import MonitorError, MonitorConflict, MonitorUnavailable, _directories, _unsafe, _identity

_DATABASE = "receiver.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE deliveries (sequence INTEGER PRIMARY KEY, alert_id TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL UNIQUE) STRICT",
)
_META = {"schema", "store_id", "count", "head_sha256", "last_clock"}
_SCHEMA_ID = "mra-fixture-monitor-receiver/v1"


def _unavailable():
    raise MonitorUnavailable("Local alert receiver unavailable")


def _immutable(alert):
    alert = c.validate_alert(alert)
    return {key: value for key, value in alert.items() if key not in {"acknowledged", "receiver_pin"}}


def _decode(text):
    raw = text.encode("ascii")
    value = c.strict_json(raw)
    if c.canonical_bytes(value) != raw:
        _unavailable()
    return value


class FixtureAlertReceiver:
    """Explicit new root or externally pinned reopen; no repair/reset/delete."""
    def __init__(self, root, expected_pin):
        self._pin = c.validate_pin(expected_pin)
        self._store_id = self._pin["store_id"]
        self._initial_pin = None
        self._lock = threading.RLock()
        try:
            self._root = Path(root).absolute()
            self._path = self.root / _DATABASE
            _directories(self.root)
            self._root_identity = _identity(self.root.lstat())
            self._db_identity = _identity(self._path.lstat())
            with self._connect() as db:
                db.execute("BEGIN")
                state = self._validate(db)
                self._floor(state, self._pin)
                self._pin = self._state_pin(state)
                self._paths()
                db.rollback()
        except (OSError, ValueError, TypeError):
            raise MonitorUnavailable("Local alert receiver open rejected") from None

    @property
    def root(self):
        return self._root

    @property
    def pin(self):
        with self._lock:
            return c.validate_pin(self._pin)

    @property
    def initial_pin(self):
        if self._initial_pin is None:
            raise MonitorError("Initial checkpoint exists only after creation")
        return c.validate_pin(self._initial_pin)

    @classmethod
    def create(cls, root, profile="local_public_fixture"):
        if type(profile) is not str or profile != "local_public_fixture":
            raise MonitorError("Production receiver unavailable")
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            _directories(root)
            path = root / _DATABASE
            with path.open("xb"):
                pass
            identifier = secrets.token_hex(16)
            db = sqlite3.connect(path, timeout=3, isolation_level=None)
            try:
                db.enable_load_extension(False)
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA page_size=4096")
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA max_page_count=2048")
                db.execute("BEGIN IMMEDIATE")
                for sql in _SCHEMA:
                    db.execute(sql)
                db.executemany("INSERT INTO meta VALUES(?,?)", (("schema", _SCHEMA_ID),
                    ("store_id", identifier), ("count", "0"), ("head_sha256", c.GENESIS_SHA256), ("last_clock", "0")))
                db.commit()
            finally:
                db.close()
            pin = {"schema": "mra-fixture-monitor-pin/v1", "store_id": identifier,
                   "sequence": 0, "head_sha256": c.GENESIS_SHA256}
            result = cls(root, pin)
            result._initial_pin = pin
            return result
        except (OSError, sqlite3.Error, TypeError, ValueError):
            raise MonitorUnavailable("Local alert receiver creation rejected") from None

    @classmethod
    def open(cls, root, expected_pin):
        return cls(root, expected_pin)

    def _paths(self):
        try:
            _directories(self.root)
            info = self._path.lstat()
            if (_identity(self.root.lstat()) != self._root_identity
                    or _identity(info) != self._db_identity or _unsafe(info)
                    or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or not 1 <= info.st_size <= c.MAX_BYTES):
                _unavailable()
            for suffix in ("-wal", "-shm", "-journal"):
                path = self._path.with_name(_DATABASE + suffix)
                try:
                    side = path.lstat()
                except FileNotFoundError:
                    continue
                if (suffix != "-journal" or _unsafe(side) or not stat.S_ISREG(side.st_mode)
                        or side.st_nlink != 1 or side.st_size > c.MAX_BYTES + 65536):
                    _unavailable()
        except OSError:
            raise MonitorUnavailable("Local alert receiver path rejected") from None

    @contextmanager
    def _connect(self):
        db = None
        try:
            self._paths()
            db = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=3, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.enable_load_extension(False)
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA max_page_count=2048")
            if db.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                _unavailable()
            self._paths()
            yield db
        except sqlite3.Error:
            raise MonitorUnavailable("Local alert receiver database rejected") from None
        finally:
            if db is not None:
                db.close()

    def _state_pin(self, state):
        return {"schema": "mra-fixture-monitor-pin/v1", "store_id": self._store_id,
                "sequence": state["count"], "head_sha256": state["head"]}

    def _floor(self, state, pin):
        if pin["store_id"] != self._store_id or state["pins"].get(pin["sequence"]) != pin["head_sha256"]:
            _unavailable()

    def _validate(self, db):
        try:
            schema = db.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if (len(schema) != 2 or {row["name"] for row in schema} != {"meta", "deliveries"}
                    or any(row["type"] != "table" for row in schema) or {row["sql"] for row in schema} != set(_SCHEMA)
                    or db.execute("PRAGMA page_size").fetchone()[0] != 4096
                    or db.execute("PRAGMA page_count").fetchone()[0] > 2048
                    or [row[0] for row in db.execute("PRAGMA quick_check")] != ["ok"]):
                _unavailable()
            meta = dict(db.execute("SELECT key,value FROM meta"))
            if set(meta) != _META or meta["schema"] != _SCHEMA_ID or meta["store_id"] != self._store_id:
                _unavailable()
            count = c.integer(int(meta["count"]), 0, c.MAX_RECORDS)
            clock = c.integer(int(meta["last_clock"]))
            if str(count) != meta["count"] or str(clock) != meta["last_clock"]:
                _unavailable()
            rows = db.execute("SELECT * FROM deliveries ORDER BY sequence LIMIT ?", (c.MAX_RECORDS + 1,)).fetchall()
            if len(rows) != count:
                _unavailable()
            state = {"count": count, "clock": clock, "head": c.GENESIS_SHA256,
                     "pins": {0: c.GENESIS_SHA256}, "deliveries": [], "alerts": {}}
            previous = 0
            for index, row in enumerate(rows, 1):
                record = _decode(row["record_json"])
                if type(record) is not dict or set(record) != {"sequence", "alert", "received_at", "previous_sha256"}:
                    _unavailable()
                alert = record["alert"]
                checked = _immutable({**alert, "acknowledged": False, "receiver_pin": None})
                received = c.integer(record["received_at"])
                if (c.canonical_bytes(alert) != c.canonical_bytes(checked)
                        or type(record["sequence"]) is not int or record["sequence"] != index
                        or row["sequence"] != index or row["alert_id"] != alert["alert_id"]
                        or not previous <= received <= clock or alert["event"]["observed_at"] > received
                        or record["previous_sha256"] != state["head"]
                        or alert["alert_id"] in state["alerts"]):
                    _unavailable()
                head = c.digest(record)
                if row["record_sha256"] != head:
                    _unavailable()
                delivery = {"alert": alert, "sequence": index, "received_at": received, "sha256": head}
                state["deliveries"].append(delivery)
                state["alerts"][alert["alert_id"]] = delivery
                state["head"], state["pins"][index], previous = head, head, received
            if state["head"] != meta["head_sha256"]:
                _unavailable()
            return state
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, IndexError):
            raise MonitorUnavailable("Local alert receiver state rejected") from None

    def _clock(self, db, guard):
        now = c.integer(guard())
        previous = int(db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
        if now < previous:
            _unavailable()
        db.execute("UPDATE meta SET value=? WHERE key='last_clock'", (str(now),))
        return now

    @contextmanager
    def _transaction(self, expected_pin, guard):
        if not callable(guard):
            raise MonitorError("Trusted current guard required")
        expected_pin = c.validate_pin(expected_pin)
        with self._lock, self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                state = self._validate(db)
                self._floor(state, expected_pin)
                self._floor(state, self._pin)
                now = self._clock(db, guard)
                yield db, state, now
                state = self._validate(db)
                self._paths()
                self._clock(db, guard)
                self._paths()
                db.commit()
                self._pin = self._state_pin(state)
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise

    def receive(self, alert, *, expected_pin, guard):
        alert = _immutable(alert)  # Own before any trusted callback.
        expected_pin = c.validate_pin(expected_pin)
        with self._transaction(expected_pin, guard) as (db, state, now):
            if expected_pin != self._state_pin(state):
                raise MonitorConflict("Current receiver checkpoint required")
            if alert["event"]["observed_at"] > now:
                raise MonitorError("Future alert rejected")
            delivery = state["alerts"].get(alert["alert_id"])
            if delivery is not None:
                if c.canonical_bytes(delivery["alert"]) != c.canonical_bytes(alert):
                    raise MonitorConflict("Alert identity already binds different bytes")
            else:
                if state["count"] >= c.MAX_RECORDS:
                    raise MonitorConflict("Local receiver capacity reached")
                record = {"sequence": state["count"] + 1, "alert": alert,
                          "received_at": now, "previous_sha256": state["head"]}
                head = c.digest(record)
                db.execute("INSERT INTO deliveries VALUES(?,?,?,?)", (record["sequence"], alert["alert_id"],
                    c.canonical_bytes(record).decode("ascii"), head))
                db.execute("UPDATE meta SET value=? WHERE key='count'", (str(record["sequence"]),))
                db.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (head,))
                delivery = {"alert": alert, "sequence": record["sequence"], "received_at": now, "sha256": head}
            result_pin = {"schema": "mra-fixture-monitor-pin/v1", "store_id": self._store_id,
                          "sequence": max(state["count"], delivery["sequence"]),
                          "head_sha256": delivery["sha256"] if delivery["sequence"] > state["count"] else state["head"]}
        return {"schema": "mra-fixture-alert-receipt/v1", "status": "recorded",
                "delivery": delivery, "pin": result_pin, **c.FLAGS}

    def snapshot(self, *, guard, expected_alerts=()):
        if type(expected_alerts) not in (list, tuple) or len(expected_alerts) > c.MAX_RECORDS:
            raise MonitorError("Bounded alert custody check required")
        expected = [c.validate_alert(item) for item in expected_alerts]
        with self._transaction(self.pin, guard) as (_db, state, _now):
            for alert in expected:
                if not alert["acknowledged"]:
                    continue
                floor = alert["receiver_pin"]
                self._floor(state, floor)
                delivery = state["alerts"].get(alert["alert_id"])
                if (delivery is None or delivery["sequence"] > floor["sequence"]
                        or c.canonical_bytes(delivery["alert"]) != c.canonical_bytes(_immutable(alert))):
                    _unavailable()
            deliveries, pin = state["deliveries"], self._state_pin(state)
        return {"schema": "mra-fixture-alert-receiver-state/v1", "status": "available",
                "deliveries": deliveries, "pin": pin, **c.FLAGS}
