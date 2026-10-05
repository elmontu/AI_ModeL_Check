"""Bounded local witness for immutable fixture registry history.

The caller retains a pin outside this database and supplies it on every use.
Rollback detection is relative to that trusted floor, not independent cloud
custody. No production authority, charge refund, deletion or reset exists.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from ..production_registry.contracts import hex_id, integer, validate_digest
from .contracts import (FLAGS, WitnessContractError, canonical_bytes, digest,
    strict_json, validate_history, replay_history, validate_intent, create_intent,
    validate_pin, validate_diagnosis)

MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_HISTORY_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 512
MAX_INTENTS = 128
MAX_PENDING = 32
_DATABASE = "witness.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE events (revision INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
    "CREATE TABLE registry_events (sequence INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
)
_META = {"witness_id", "namespace_id", "registry_id", "revision", "head_sha256", "last_clock"}
_ANCHOR = {"schema", "store_id", "schema_version", "broker_epoch", "broker_id",
           "event_sequence", "event_head_sha256", "observed_at", *FLAGS}


class WitnessError(ValueError):
    """Malformed witness operation."""


class WitnessConflict(WitnessError):
    """An immutable intent, accepted prefix or external pin conflicts."""


class WitnessUnavailable(RuntimeError):
    """The current witness state or trusted clock cannot be established."""


def _unavailable():
    raise WitnessUnavailable("Fixture witness unavailable")


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise WitnessError("Witness metadata rejected")


def _owned(value, maximum=65536):
    return strict_json(canonical_bytes(value, max_bytes=maximum), max_bytes=maximum)


def _decode(raw, maximum=65536):
    value = strict_json(raw, max_bytes=maximum)
    if canonical_bytes(value, max_bytes=maximum) != raw:
        raise WitnessError("Noncanonical witness metadata")
    return value


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _identity(info):
    return info.st_dev, info.st_ino


def _directories(path):
    if ".." in path.parts or str(path).startswith(("//", "\\\\")):
        _unavailable()
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            _unavailable()


def _anchor(history):
    return {key: value for key, value in history.items() if key != "events"}


def _blank():
    return {"revision": 0, "head": "0" * 64, "clock": 0, "history": None,
            "intents": {}, "pins": {}}


class WitnessStore:
    """Trusted local boundary; guards and pins must come from server custody."""

    def __init__(self, root, *, expected_pin):
        pin = validate_pin(expected_pin)
        self._witness_id = pin["witness_id"]
        self._namespace_id, self._registry_id = pin["namespace_id"], pin["registry_id"]
        self._initial_pin = None
        try:
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE
            _directories(self.root)
            self._root_identity, self._db_identity = _identity(self.root.lstat()), _identity(self._path.lstat())
            with self._connect() as connection:
                connection.execute("BEGIN")
                try:
                    state = self._validate(connection)
                    self._floor(state, pin)
                    self._paths()
                finally:
                    connection.rollback()
        except OSError:
            raise WitnessUnavailable("Fixture witness unavailable") from None

    @property
    def root(self):
        return self._root

    @property
    def witness_id(self):
        return self._witness_id

    @property
    def namespace_id(self):
        return self._namespace_id

    @property
    def registry_id(self):
        return self._registry_id

    @property
    def initial_pin(self):
        if self._initial_pin is None:
            raise WitnessError("Initial pin exists only on a freshly created witness")
        return _owned(self._initial_pin)

    @classmethod
    def create(cls, root, *, namespace_id, registry_id, initial_history, guard):
        validate_digest(namespace_id)
        hex_id(registry_id)
        history = validate_history(initial_history)
        state = replay_history(history)
        if (history["store_id"] != registry_id or set(state["accounts"]) != {namespace_id}
                or state["receipts"]):
            raise WitnessConflict("Enrollment requires a fresh single-account registry")
        now = cls._clock(guard, history["observed_at"])
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            path = root / _DATABASE
            with path.open("xb"):
                pass
            store = object.__new__(cls)
            store._root, store._path = root, path
            store._root_identity, store._db_identity = _identity(root.lstat()), _identity(path.lstat())
            store._witness_id, store._namespace_id, store._registry_id = secrets.token_hex(16), namespace_id, registry_id
            store._initial_pin = None
            connection = sqlite3.connect(path, timeout=3., isolation_level=None)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA page_size=4096")
                connection.execute("PRAGMA max_page_count=8192")
                connection.execute("BEGIN IMMEDIATE")
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version=1")
                metadata = {"witness_id": store.witness_id, "namespace_id": namespace_id,
                            "registry_id": registry_id, "revision": 0, "head_sha256": "0" * 64, "last_clock": now}
                connection.executemany("INSERT INTO meta VALUES (?, ?)", [(key, canonical_bytes(value).decode("ascii")) for key, value in metadata.items()])
                store._copy_history(connection, history, 0)
                blank = _blank()
                store._append(connection, blank, "enrolled", {"history": _anchor(history)}, now)
                verified = store._validate(connection)
                final = store._clock(guard, max(now, verified["clock"]))
                store._meta(connection, "last_clock", final)
                store._paths()
                connection.commit()
                store._initial_pin = store._pin(verified)
            finally:
                connection.close()
            return store
        except (OSError, sqlite3.Error):
            raise WitnessUnavailable("Fixture witness creation unavailable") from None

    @classmethod
    def open(cls, root, *, expected_pin):
        return cls(root, expected_pin=expected_pin)

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
                    info = (self.root / (_DATABASE + suffix)).lstat()
                except FileNotFoundError:
                    continue
                if (suffix != "-journal" or _unsafe(info) or not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1 or info.st_size > MAX_DATABASE_BYTES + 65536):
                    _unavailable()
        except OSError:
            raise WitnessUnavailable("Fixture witness filesystem unavailable") from None

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self._paths()
            connection = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=3., isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.enable_load_extension(False)
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA max_page_count=8192")
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                _unavailable()
            self._paths()
            yield connection
        except sqlite3.Error:
            raise WitnessUnavailable("Fixture witness database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _clock(guard, floor):
        if not callable(guard):
            raise WitnessError("A trusted current guard is required")
        now = guard()
        if type(now) is not int or not floor <= now <= 2 ** 53 - 1:
            raise WitnessUnavailable("Witness clock moved backwards or is invalid")
        return now

    def _pin(self, state):
        return {"schema": "mra-fixture-witness-pin/v1", "witness_id": self.witness_id,
                "namespace_id": self.namespace_id, "registry_id": self.registry_id,
                "revision": state["revision"], "head_sha256": state["head"]}

    def _floor(self, state, pin):
        pin = validate_pin(pin)
        if (pin["witness_id"] != self.witness_id or pin["namespace_id"] != self.namespace_id
                or pin["registry_id"] != self.registry_id
                or state["pins"].get(pin["revision"]) != pin["head_sha256"]):
            raise WitnessConflict("External witness floor is not an exact retained ancestor")

    @staticmethod
    def _meta(connection, key, value):
        connection.execute("UPDATE meta SET value=? WHERE key=?", (canonical_bytes(value).decode("ascii"), key))

    def _copy_history(self, connection, history, previous):
        for row in history["events"][previous:]:
            body = row["event"]
            connection.execute("INSERT INTO registry_events VALUES (?, ?, ?)",
                (body["sequence"], row["event_sha256"], canonical_bytes(body).decode("ascii")))

    def _append(self, connection, state, kind, payload, now):
        if state["revision"] >= MAX_EVENTS:
            raise WitnessConflict("Witness event capacity reached")
        event = {"schema": "mra-fixture-witness-history/v1", "witness_id": self.witness_id,
                 "namespace_id": self.namespace_id, "registry_id": self.registry_id,
                 "revision": state["revision"] + 1, "previous_sha256": state["head"],
                 "occurred_at": now, "kind": kind, "payload": payload}
        event_hash = digest(event)
        connection.execute("INSERT INTO events VALUES (?, ?, ?)",
            (event["revision"], event_hash, canonical_bytes(event).decode("ascii")))
        self._meta(connection, "revision", event["revision"])
        self._meta(connection, "head_sha256", event_hash)
        self._meta(connection, "last_clock", now)
        return event_hash

    def _reconcile(self, state, history, registry):
        previous = state["history"]
        if history["store_id"] != self.registry_id or set(registry["accounts"]) != {self.namespace_id}:
            raise WitnessConflict("Registry identity or namespace differs from enrollment")
        if previous is None:
            if registry["receipts"]:
                raise WitnessConflict("Enrollment cannot adopt preexisting commits")
        else:
            count = previous["event_sequence"]
            if (history["event_sequence"] < count or history["observed_at"] < previous["observed_at"]
                    or history["events"][:count] != previous["events"]):
                raise WitnessConflict("Registry is not the exact accepted history extension")
            for row in history["events"][count:]:
                event = row["event"]
                if event["kind"] != "committed":
                    continue
                request, receipt = event["payload"]["request"], event["payload"]["receipt"]
                record = state["intents"].get(request["request_id"])
                if (record is None or record["state"] != "pending"
                        or record["intent"]["request"] != request
                        or record["intent"]["request_sha256"] != digest(request)
                        or record["intent"]["broker_epoch"] != receipt["receipt"]["commit_context"]["broker_epoch"]
                        or record["intent"]["predecessor_sequence"] >= event["sequence"]):
                    raise WitnessConflict("Commit lacks its preexisting exact witness intent")
                record.update(state="committed", receipt=receipt)
            account = registry["accounts"][self.namespace_id]
            for record in state["intents"].values():
                if (record["state"] == "pending"
                        and account["sequence"] > record["intent"]["request"]["expected_account_sequence"]):
                    # The configured account is monotonic in the fully replayed
                    # registry. This CAS can never become current again.
                    record.update(state="aborted", receipt=None)
        state["history"] = history

    def _prepare(self, state, intent, history):
        if intent["namespace_id"] != self.namespace_id or intent["registry_id"] != self.registry_id:
            raise WitnessConflict("Intent differs from the enrolled namespace")
        key = intent["request"]["request_id"]
        existing = state["intents"].get(key)
        if existing is not None:
            if existing["intent"] != intent:
                raise WitnessConflict("Permanent request intent cannot be replaced")
            return
        if (len(state["intents"]) >= MAX_INTENTS
                or sum(row["state"] == "pending" for row in state["intents"].values()) >= MAX_PENDING):
            raise WitnessConflict("Witness intent capacity reached")
        if create_intent(history, intent["request"]) != intent:
            raise WitnessConflict("Intent predecessor is not the current registry snapshot")
        state["intents"][key] = {"intent": intent, "state": "pending", "receipt": None}

    def _apply(self, state, body, event_hash, registry_rows, cache):
        _exact(body, {"schema", "witness_id", "namespace_id", "registry_id", "revision",
                      "previous_sha256", "occurred_at", "kind", "payload"})
        integer(body["revision"], 1, MAX_EVENTS)
        integer(body["occurred_at"])
        if (body["schema"] != "mra-fixture-witness-history/v1"
                or body["witness_id"] != self.witness_id or body["namespace_id"] != self.namespace_id
                or body["registry_id"] != self.registry_id or body["revision"] != state["revision"] + 1
                or body["previous_sha256"] != state["head"] or body["occurred_at"] < state["clock"]):
            raise WitnessConflict("Witness history differs")
        kind, payload = body["kind"], body["payload"]
        if kind not in ("enrolled", "prepared", "observed", "aborted"):
            raise WitnessError("Unknown witness event")
        _exact(payload, {"history", "intent"} if kind in ("prepared", "aborted") else {"history"})
        anchor = payload["history"]
        _exact(anchor, _ANCHOR)
        integer(anchor["event_sequence"], 1, 2048)
        if anchor["event_sequence"] > len(registry_rows) or anchor["observed_at"] > body["occurred_at"]:
            raise WitnessConflict("Witness history observation is incomplete or future")
        key = digest(anchor)
        if key not in cache:
            history = validate_history({**anchor, "events": registry_rows[:anchor["event_sequence"]]})
            cache[key] = (history, replay_history(history))
        history, registry = cache[key]
        if (kind == "enrolled") != (state["revision"] == 0):
            raise WitnessConflict("Witness enrollment cannot be replayed")
        self._reconcile(state, history, registry)
        if kind in ("prepared", "aborted"):
            intent = validate_intent(payload["intent"])
            if kind == "prepared":
                self._prepare(state, intent, history)
            else:
                record = state["intents"].get(intent["request"]["request_id"])
                if record is None or record["intent"] != intent or record["state"] != "aborted":
                    raise WitnessConflict("Absent receipt alone cannot abort an intent")
        state.update(revision=body["revision"], head=event_hash, clock=body["occurred_at"])
        state["pins"][state["revision"]] = event_hash

    def _validate(self, connection):
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                _unavailable()
            if connection.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                _unavailable()
            rows = connection.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%' ORDER BY name").fetchall()
            actual = {(row["type"], row["name"]): row["sql"] for row in rows}
            expected = {("table", statement.split()[2]): statement for statement in _SCHEMA}
            if actual != expected:
                _unavailable()
            metadata_rows = connection.execute("SELECT key, value FROM meta LIMIT 7").fetchall()
            if {row["key"] for row in metadata_rows} != _META or len(metadata_rows) != len(_META):
                _unavailable()
            metadata = {row["key"]: _decode(row["value"].encode("ascii")) for row in metadata_rows}
            if (metadata["witness_id"] != self.witness_id or metadata["namespace_id"] != self.namespace_id
                    or metadata["registry_id"] != self.registry_id):
                _unavailable()
            integer(metadata["revision"], 1, MAX_EVENTS)
            integer(metadata["last_clock"])
            validate_digest(metadata["head_sha256"])
            raw_registry = connection.execute("SELECT * FROM registry_events ORDER BY sequence LIMIT 2049").fetchall()
            if not 1 <= len(raw_registry) <= 2048:
                _unavailable()
            registry_rows, total = [], 0
            for index, row in enumerate(raw_registry, 1):
                raw = row["event_json"].encode("ascii")
                total += len(raw)
                if total > MAX_HISTORY_BYTES or row["sequence"] != index:
                    _unavailable()
                registry_rows.append({"event_sha256": row["event_sha256"], "event": _decode(raw)})
            events = connection.execute("SELECT * FROM events ORDER BY revision LIMIT ?", (MAX_EVENTS + 1,)).fetchall()
            if len(events) != metadata["revision"]:
                _unavailable()
            state, cache = _blank(), {}
            for index, row in enumerate(events, 1):
                raw = row["event_json"].encode("ascii")
                event = _decode(raw)
                event_hash = digest(event)
                if row["revision"] != index or row["event_sha256"] != event_hash:
                    _unavailable()
                self._apply(state, event, event_hash, registry_rows, cache)
            if (state["revision"] != metadata["revision"] or state["head"] != metadata["head_sha256"]
                    or state["clock"] > metadata["last_clock"]
                    or state["history"]["event_sequence"] != len(registry_rows)):
                _unavailable()
            state["clock"] = metadata["last_clock"]
            self._diagnosis(state)
            return state
        except (WitnessContractError, WitnessError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
            raise WitnessUnavailable("Fixture witness state validation failed") from None

    def _diagnosis(self, state):
        rows = [state["intents"][key] for key in sorted(state["intents"])]
        counts = {status: sum(row["state"] == status for row in rows) for status in ("pending", "committed", "aborted")}
        history = state["history"]
        pending = counts["pending"] > 0
        return validate_diagnosis({"schema": "mra-fixture-witness-diagnosis/v1",
            "status": "quarantined" if pending else "consistent", "reconciled": not pending,
            "pin": self._pin(state), "namespace_id": self.namespace_id, "registry_id": self.registry_id,
            "registry_sequence": history["event_sequence"], "registry_head_sha256": history["event_head_sha256"],
            "registry_epoch": history["broker_epoch"], "registry_observed_at": history["observed_at"],
            "pending_intents": counts["pending"], "committed_intents": counts["committed"],
            "aborted_intents": counts["aborted"], "quarantine_reasons": ["pending_intent"] if pending else [],
            "intents": rows, **FLAGS})

    @contextmanager
    def _transaction(self, expected_pin, guard):
        pin = validate_pin(expected_pin)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                state = self._validate(connection)
                self._floor(state, pin)
                now = self._clock(guard, state["clock"])
                yield connection, state, now
                # Revalidate expensive semantic replay BEFORE the last current
                # authorization/clock observation, never after it.
                current = self._validate(connection)
                self._floor(current, pin)
                final = self._clock(guard, max(now, current["clock"]))
                self._meta(connection, "last_clock", final)
                self._paths()
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def status(self, *, expected_pin, guard):
        """Return persisted diagnosis, not an observation of a live registry."""
        with self._transaction(expected_pin, guard) as (_, state, _):
            result = self._diagnosis(state)
        return result

    def _operate(self, kind, history, intent, expected_pin, guard):
        history = validate_history(history)
        registry = replay_history(history)
        if intent is not None:
            intent = validate_intent(intent)
        with self._transaction(expected_pin, guard) as (connection, state, now):
            if history["observed_at"] > now:
                raise WitnessConflict("Registry observation is in the future")
            previous_count = state["history"]["event_sequence"]
            previous_anchor = _anchor(state["history"])
            old_intents = _owned(state["intents"], MAX_DATABASE_BYTES)
            # Existing intent roster only: a commit cannot be retrospectively
            # covered by the intent this same operation is about to prepare.
            self._reconcile(state, history, registry)
            if kind == "prepared":
                self._prepare(state, intent, history)
            elif kind == "aborted":
                record = state["intents"].get(intent["request"]["request_id"])
                if record is None or record["intent"] != intent or record["state"] != "aborted":
                    raise WitnessConflict("Intent has no irreversible noncommit proof")
            if previous_anchor == _anchor(history) and old_intents == state["intents"]:
                result = self._diagnosis(state)
            else:
                payload = {"history": _anchor(history)}
                if intent is not None:
                    payload["intent"] = intent
                self._copy_history(connection, history, previous_count)
                self._append(connection, state, kind, payload, now)
                current = self._validate(connection)
                result = self._diagnosis(current)
        return result

    def prepare(self, intent, history, *, expected_pin, guard):
        return self._operate("prepared", history, intent, expected_pin, guard)

    def observe(self, history, *, expected_pin, guard):
        return self._operate("observed", history, None, expected_pin, guard)

    def abort(self, intent, history, *, expected_pin, guard):
        """Confirm an already irreversible CAS loss; never timeout/refund/reset."""
        return self._operate("aborted", history, intent, expected_pin, guard)
