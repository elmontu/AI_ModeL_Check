"""Seven-stage local public-profile journal, with an external checkpoint floor.

This ordinary SQLite ledger is not independent custody, a cross-store transaction,
execution attestation or model-delivery authority. An exact caller-held pin detects
rollback relative to that pin; initial pins cannot be rediscovered by reopening.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from .contracts import (FLAGS, STAGES, MAX_STATE_BYTES, ProfileError, canonical_bytes, strict_json,
    digest, owned, integer, hex_id, validate_digest, validate_actor, validate_plan, validate_pin,
    validate_payload, validate_record)

MAX_DATABASE_BYTES = 2 * 1024 * 1024
_DATABASE = "journal.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
)
_META = {"store_id", "event_count", "head_sha256", "last_clock"}


class StoreError(ProfileError):
    """Malformed journal operation."""


class StoreConflict(StoreError):
    """Checkpoint, stage order, identity or permanent binding conflict."""


class StoreUnavailable(RuntimeError):
    """Journal history, paths or current clock cannot be verified."""


def _unavailable():
    raise StoreUnavailable("Public profile journal unavailable")


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


def _decode(text):
    if type(text) is not str:
        _unavailable()
    raw = text.encode("ascii")
    result = strict_json(raw)
    if canonical_bytes(result) != raw:
        _unavailable()
    return result


def _blank():
    return {"count": 0, "head": "0" * 64, "clock": 0, "pins": {}, "stages": {}, "plan": None}


class Journal:
    def __init__(self, root, *, expected_pin):
        pin = validate_pin(expected_pin)
        self._store_id = pin["store_id"]
        self._initial_pin = None
        try:
            self._root = Path(root).absolute()
            self._path = self.root / _DATABASE
            _directories(self.root)
            self._root_identity, self._db_identity = _identity(self.root.lstat()), _identity(self._path.lstat())
            with self._connect() as connection:
                connection.execute("BEGIN")
                try:
                    self._floor(self._validate(connection), pin)
                    self._paths()
                finally:
                    connection.rollback()
        except OSError:
            raise StoreUnavailable("Public profile journal unavailable") from None

    @property
    def root(self):
        return self._root

    @property
    def store_id(self):
        return self._store_id

    @property
    def initial_pin(self):
        if self._initial_pin is None:
            raise StoreError("Initial pin exists only on a newly created journal")
        return owned(self._initial_pin)

    @classmethod
    def open(cls, root, *, expected_pin):
        return cls(root, expected_pin=expected_pin)

    @classmethod
    def create(cls, root, plan, actor, *, guard):
        plan, actor = validate_plan(plan), validate_actor(actor)
        now = cls._clock(guard, 0)
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            path = root / _DATABASE
            with path.open("xb"):
                pass
            journal = object.__new__(cls)
            journal._root, journal._path, journal._store_id = root, path, secrets.token_hex(16)
            journal._initial_pin = None
            journal._root_identity, journal._db_identity = _identity(root.lstat()), _identity(path.lstat())
            connection = sqlite3.connect(path, timeout=3., isolation_level=None)
            try:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA page_size=4096")
                connection.execute("PRAGMA max_page_count=512")
                connection.execute("BEGIN IMMEDIATE")
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version=1")
                meta = {"store_id": journal.store_id, "event_count": 0, "head_sha256": "0" * 64, "last_clock": now}
                connection.executemany("INSERT INTO meta VALUES (?, ?)",
                    [(key, canonical_bytes(value).decode("ascii")) for key, value in meta.items()])
                state = _blank()
                journal._append(connection, state, "planned", plan, actor, now)
                journal._validate(connection)
                journal._meta(connection, "last_clock", journal._clock(guard, now))
                journal._paths()
                connection.commit()
                journal._initial_pin = journal._pin(state)
            finally:
                connection.close()
            return journal
        except (OSError, sqlite3.Error):
            raise StoreUnavailable("Public profile journal creation unavailable") from None

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
            raise StoreUnavailable("Public profile journal filesystem unavailable") from None

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self._paths()
            connection = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=3., isolation_level=None)
            connection.enable_load_extension(False)
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA max_page_count=512")
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                _unavailable()
            self._paths()
            yield connection
        except sqlite3.Error:
            raise StoreUnavailable("Public profile journal database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _clock(guard, floor):
        if not callable(guard):
            raise StoreError("A trusted current guard is required")
        now = guard()
        if type(now) is not int or not floor <= now <= 2 ** 53 - 1:
            raise StoreUnavailable("Journal clock moved backwards or is invalid")
        return now

    @staticmethod
    def _meta(connection, key, value):
        connection.execute("UPDATE meta SET value=? WHERE key=?", (canonical_bytes(value).decode("ascii"), key))

    def _pin(self, state):
        return {"schema": "mra-public-profile-journal-pin/v1", "store_id": self.store_id,
                "sequence": state["count"], "head_sha256": state["head"]}

    def _floor(self, state, expected_pin):
        pin = validate_pin(expected_pin)
        if pin["store_id"] != self.store_id or state["pins"].get(pin["sequence"]) != pin["head_sha256"]:
            raise StoreConflict("Journal pin is not an exact retained ancestor")

    @staticmethod
    def _transition(state, record):
        stage, payload = record["stage"], record["payload"]
        if state["count"] >= len(STAGES) or stage != STAGES[state["count"]]:
            raise StoreConflict("Stages are permanent and must follow the fixed order")
        rows = state["stages"]
        if stage == "planned":
            state["plan"] = payload
        elif stage == "native":
            if payload["campaign_id"] != state["plan"]["campaign_id"] or payload["policy_sha256"] != state["plan"]["native_policy_sha256"]:
                raise StoreConflict("Native result differs from the prospective policy")
        elif stage in ("assess", "approve", "authorize", "complete"):
            if payload["combined_sha256"] != rows["external"]["payload"]["combined_sha256"]:
                raise StoreConflict("Combined comparison binding differs")
            if stage in ("assess", "approve"):
                excluded = {rows[name]["actor"]["person_id"] for name in ("planned", "native")}
                if stage == "approve":
                    excluded.add(rows["assess"]["actor"]["person_id"])
                    if payload["assessment_sha256"] != rows["assess"]["sha256"]:
                        raise StoreConflict("Approval differs from the independent assessment")
                if record["actor"]["person_id"] in excluded:
                    raise StoreConflict("Canonical reviewers must be independent")
            elif stage == "authorize":
                if payload["approval_sha256"] != rows["approve"]["sha256"]:
                    raise StoreConflict("Activation differs from the independent approval")
            else:
                initial = rows["authorize"]["payload"]
                before, after = initial["delivery_pin"], payload["final_delivery_pin"]
                if (payload["activation_id"] != initial["activation_id"] or before["store_id"] != after["store_id"]
                        or after["sequence"] < before["sequence"]
                        or (after["sequence"] == before["sequence"] and after["head_sha256"] != before["head_sha256"])):
                    raise StoreConflict("Completion differs from the retained activation checkpoint")
        rows[stage] = record

    def _apply(self, state, event, event_sha256):
        event = owned(event, {"schema", "store_id", "sequence", "previous_sha256", "record"})
        if (event["schema"] != "mra-public-profile-history/v1" or event["store_id"] != self.store_id
                or type(event["sequence"]) is not int or event["sequence"] != state["count"] + 1
                or event["previous_sha256"] != state["head"] or digest(event) != event_sha256):
            _unavailable()
        record = validate_record(event["record"])
        if record["at"] < state["clock"]:
            _unavailable()
        self._transition(state, record)
        state["count"], state["head"], state["clock"] = event["sequence"], event_sha256, record["at"]
        state["pins"][state["count"]] = event_sha256

    def _validate(self, connection):
        """Pure full replay, including for owned in-memory archival SQLite bytes.

        Only self._store_id is used; no path I/O, guard or credential checks occur.
        Archival replay cannot establish current live eligibility.
        """
        try:
            schema = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            expected = sorted([("table", name, name, statement) for name, statement in zip(("meta", "events"), _SCHEMA)], key=lambda row: row[1])
            if ([tuple(row) for row in schema] != expected or connection.execute("PRAGMA user_version").fetchone()[0] != 1
                    or connection.execute("PRAGMA application_id").fetchone()[0] != 0):
                _unavailable()
            rows = connection.execute("SELECT key,value FROM meta LIMIT 6").fetchall()
            if len(rows) != len(_META) or {row[0] for row in rows} != _META:
                _unavailable()
            meta = {key: _decode(value) for key, value in rows}
            hex_id(meta["store_id"])
            integer(meta["event_count"], 1, len(STAGES))
            integer(meta["last_clock"])
            validate_digest(meta["head_sha256"])
            if meta["store_id"] != self.store_id:
                _unavailable()
            state = _blank()
            rows = connection.execute("SELECT sequence,event_sha256,event_json FROM events ORDER BY sequence LIMIT 8").fetchall()
            if len(rows) != meta["event_count"]:
                _unavailable()
            for sequence, event_sha256, text in rows:
                if sequence != state["count"] + 1:
                    _unavailable()
                self._apply(state, _decode(text), event_sha256)
            if state["head"] != meta["head_sha256"] or meta["last_clock"] < state["clock"]:
                _unavailable()
            state["clock"] = meta["last_clock"]
            return state
        except (ProfileError, TypeError, KeyError, UnicodeError, sqlite3.Error):
            raise StoreUnavailable("Public profile journal history rejected") from None

    def _append(self, connection, state, stage, payload, actor, now):
        body = {"stage": stage, "actor": actor, "at": now, "payload": payload}
        record = {**body, "sha256": digest(body)}
        event = {"schema": "mra-public-profile-history/v1", "store_id": self.store_id,
                 "sequence": state["count"] + 1, "previous_sha256": state["head"], "record": record}
        event_sha256 = digest(event)
        self._apply(state, event, event_sha256)
        connection.execute("INSERT INTO events VALUES (?,?,?)", (state["count"], event_sha256, canonical_bytes(event).decode("ascii")))
        for key, value in (("event_count", state["count"]), ("head_sha256", state["head"]), ("last_clock", now)):
            self._meta(connection, key, value)

    def _snapshot(self, state):
        return owned({"schema": "mra-public-profile-journal/v1", "store_id": self.store_id,
            "plan": state["plan"], "plan_sha256": digest(state["plan"]), "stage": STAGES[state["count"] - 1],
            "stages": state["stages"], "pin": self._pin(state), **FLAGS}, max_bytes=MAX_STATE_BYTES)

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
                replayed = self._validate(connection)
                if self._snapshot(replayed) != self._snapshot(state):
                    _unavailable()
                self._meta(connection, "last_clock", self._clock(guard, max(now, replayed["clock"])))
                self._paths()
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def append(self, stage, payload, actor, *, expected_pin, guard):
        payload, actor = validate_payload(stage, payload), validate_actor(actor)
        pin = validate_pin(expected_pin)
        with self._transaction(pin, guard) as (connection, state, now):
            if self._pin(state) != pin:
                raise StoreConflict("Append requires the exact current journal checkpoint")
            self._append(connection, state, stage, payload, actor, now)
            result = self._snapshot(state)
        return result

    def read(self, *, expected_pin, guard):
        with self._transaction(expected_pin, guard) as (_, state, _):
            result = self._snapshot(state)
        return result


ProfileJournal = Journal
