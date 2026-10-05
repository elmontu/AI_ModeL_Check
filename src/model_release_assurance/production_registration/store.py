"""Append-only local registration and observed-disclosure history.

Only bounded public-fixture metadata is stored. Replayed event chains establish
local continuity, not completeness of external history, privacy accounting,
production authorization, or protection against privileged database rollback.
Every operation requires a trusted authorization/time guard before commit.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import stat

from .contracts import validate_registration, validate_review

MAX_DATABASE_BYTES = 16 * 1024 * 1024
MAX_REGISTRATIONS = 128
MAX_EVENTS = 1024
MAX_DISCLOSURES = 256
MAX_JSON_BYTES = 65536
MAX_INTEGER = 2**53 - 1
_DATABASE_NAME = "registrations.sqlite"
_SCHEMA_ID = "mra-local-registration-store/v1"
_ZERO = "0" * 64
_ID = re.compile(r"[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REASONS = frozenset(("source_changed", "training_failed", "evidence_failed", "history_changed", "interrupted"))
_CHANNELS = frozenset(("model_parameters", "metrics", "selection_metadata", "refusal"))
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
)
_HISTORY_KEYS = {"ledger_id", "scope_id", "sequence", "head_sha256", "local_registrations",
                 "known_disclosures", "external_history", "privacy_accounting_supported"}
_TICKET_KEYS = {"ledger_id", "registration_id", "registration_sha256", "scope_id", "sequence", "head_sha256", "state"}
_COMPLETION_KEYS = {"registration_sha256", "artifacts_sha256", "candidate_sha256", "report_sha256",
                    "evidence_envelope_sha256", "evidence_admission_sha256", "review"}
_EVENT_KEYS = {"schema", "ledger_id", "sequence", "scope_id", "scope_sequence", "previous_sha256",
               "previous_scope_sha256", "agency_id", "project_id", "occurred_at", "kind", "payload"}


class StoreError(ValueError):
    """Malformed local registration metadata."""


class StoreConflict(StoreError):
    """Stale history, replay, illegal transition, or bounded capacity reached."""


class StoreUnavailable(RuntimeError):
    """Existing state, filesystem, or trusted time cannot be established."""


def _unavailable():
    raise StoreUnavailable("Registration store unavailable")


def _exact(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise StoreError("Registration store metadata rejected")
    return value


def _text(value, pattern):
    if type(value) is not str or not pattern.fullmatch(value):
        raise StoreError("Registration store identifier rejected")
    return value


def _integer(value):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise StoreError("Registration store integer rejected")
    return value


def _encode(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("utf-8")
        if len(raw) > MAX_JSON_BYTES:
            raise StoreError("Registration store metadata exceeds its bound")
        return raw
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise StoreError("Registration store metadata rejected") from None


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise StoreError("Duplicate registration store JSON field")
            result[key] = value
        return result
    def invalid(_):
        raise StoreError("Registration store JSON rejected")
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_JSON_BYTES:
            raise StoreError("Registration store JSON exceeds its bound")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
        if _encode(value) != raw:
            raise StoreError("Registration store JSON is not canonical")
        return value
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise StoreError("Registration store JSON rejected") from None


def _owned(value):
    return _decode(_encode(value))


def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _scope(agency_id, project_id):
    _text(agency_id, _IDENTIFIER)
    _text(project_id, _IDENTIFIER)
    return _digest({"agency_id": agency_id, "project_id": project_id})


def _history(value):
    _exact(value, _HISTORY_KEYS)
    _text(value["ledger_id"], _ID)
    for key in ("scope_id", "head_sha256"):
        _text(value[key], _DIGEST)
    for key in ("sequence", "local_registrations", "known_disclosures"):
        _integer(value[key])
    if value["external_history"] != "unknown" or value["privacy_accounting_supported"] is not False:
        raise StoreError("External history and privacy accounting are not established")
    return _owned(value)


def _ticket(value):
    _exact(value, _TICKET_KEYS)
    for key in ("ledger_id", "registration_id"):
        _text(value[key], _ID)
    for key in ("registration_sha256", "scope_id", "head_sha256"):
        _text(value[key], _DIGEST)
    if _integer(value["sequence"]) < 1 or value["state"] not in ("registered", "training"):
        raise StoreError("Registration ticket rejected")
    return _owned(value)


def _registration(value):
    try:
        value = validate_registration(value)
        _text(value["registration_id"], _ID)
        _scope(value["agency_id"], value["project_id"])
        _history(value["history"])
        return _owned(value)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise StoreError("Registration metadata rejected") from None


def _completion(value):
    _exact(value, _COMPLETION_KEYS)
    for key in _COMPLETION_KEYS - {"review"}:
        _text(value[key], _DIGEST)
    try:
        review = validate_review(value["review"])
        for key in ("registration_sha256", "artifacts_sha256", "candidate_sha256", "report_sha256"):
            if review[key] != value[key]:
                raise StoreError("Completion and review differ")
        return _owned({**value, "review": review})
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise StoreError("Registration completion rejected") from None


def _disclosure(value):
    _exact(value, {"disclosure_id", "artifact_sha256", "source_reference_sha256",
                   "recipient_id", "channel", "occurred_at"})
    _text(value["disclosure_id"], _ID)
    _text(value["artifact_sha256"], _DIGEST)
    _text(value["source_reference_sha256"], _DIGEST)
    _text(value["recipient_id"], _IDENTIFIER)
    _integer(value["occurred_at"])
    if type(value["channel"]) is not str or value["channel"] not in _CHANNELS:
        raise StoreError("Observed disclosure channel rejected")
    return _owned(value)


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


class RegistrationStore:
    """Explicit new/open store. No deletion, reset, retry, or publication API.

    Independent callers serialize through SQLite. The trusted caller holds its
    own authority lock while supplying guards; no authentication is fabricated
    by this store. Opening pending work never resumes training automatically.
    """

    def __init__(self, root, expected_store_id):
        try:
            _text(expected_store_id, _ID)
            self._store_id = expected_store_id
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE_NAME
            _directories(self._root)
            self._root_identity = _identity(self._root.lstat())
            self._db_identity = _identity(self._path.lstat())
        except (OSError, TypeError, ValueError):
            raise StoreUnavailable("Registration store unavailable") from None
        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                self._validate(connection)
                self._paths()
            finally:
                connection.rollback()

    @property
    def root(self):
        return self._root

    @property
    def store_id(self):
        return self._store_id

    @classmethod
    def create(cls, root):
        """Create a fresh root; never overwrite or repair an existing store."""
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            _directories(root)
            path = root / _DATABASE_NAME
            with path.open("xb"):
                pass
            store_id = secrets.token_hex(16)
            connection = sqlite3.connect(path, timeout=1.0, isolation_level=None)
            try:
                connection.enable_load_extension(False)
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA page_size=4096")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA max_page_count=4096")
                connection.execute("BEGIN IMMEDIATE")
                for sql in _SCHEMA:
                    connection.execute(sql)
                connection.executemany("INSERT INTO meta VALUES(?,?)", (
                    ("schema", _SCHEMA_ID), ("store_id", store_id), ("last_clock", "0"),
                    ("event_count", "0"), ("head_sha256", _ZERO)))
                connection.commit()
            finally:
                connection.close()
            return cls(root, store_id)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            raise StoreUnavailable("Registration store creation unavailable") from None

    @classmethod
    def open(cls, root, expected_store_id):
        return cls(root, expected_store_id)

    def _paths(self):
        try:
            _directories(self._root)
            if _identity(self._root.lstat()) != self._root_identity:
                _unavailable()
            info = self._path.lstat()
            if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or _identity(info) != self._db_identity or not 1 <= info.st_size <= MAX_DATABASE_BYTES):
                _unavailable()
            for suffix in ("-journal", "-wal", "-shm"):
                try:
                    info = (self._root / (_DATABASE_NAME + suffix)).lstat()
                except FileNotFoundError:
                    continue
                if (suffix != "-journal" or _unsafe(info) or not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1 or info.st_size > MAX_DATABASE_BYTES + MAX_JSON_BYTES):
                    _unavailable()
        except OSError:
            raise StoreUnavailable("Registration store filesystem unavailable") from None

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self._paths()
            connection = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True,
                                         timeout=2.0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.enable_load_extension(False)
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA max_page_count=4096")
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                _unavailable()
            self._paths()
            yield connection
        except sqlite3.Error:
            raise StoreUnavailable("Registration store database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def _history_for(self, state, agency_id, project_id):
        scope = _scope(agency_id, project_id)
        return {"ledger_id": self.store_id, "scope_id": scope,
            **state["scopes"].get(scope, {"sequence": 0, "head_sha256": _ZERO,
                "local_registrations": 0, "known_disclosures": 0}),
            "external_history": "unknown", "privacy_accounting_supported": False}

    def _ticket_for(self, record, history):
        return {"ledger_id": self.store_id, "registration_id": record["registration"]["registration_id"],
            "registration_sha256": record["registration_sha256"], "scope_id": history["scope_id"],
            "sequence": history["sequence"], "head_sha256": history["head_sha256"], "state": record["state"]}

    def _require_ticket(self, state, ticket):
        record = state["registrations"].get(ticket["registration_id"])
        if record is None or record["state"] not in ("registered", "training"):
            raise StoreConflict("Registration ticket is not current")
        registration = record["registration"]
        history = self._history_for(state, registration["agency_id"], registration["project_id"])
        if ticket != self._ticket_for(record, history):
            raise StoreConflict("Registration ticket or history changed")
        return record

    def _apply(self, state, body, event_digest):
        """Validate and replay one event; no mutable state rows can disagree."""
        _exact(body, _EVENT_KEYS)
        history = self._history_for(state, body["agency_id"], body["project_id"])
        now = _integer(body["occurred_at"])
        sequence = _integer(body["sequence"])
        scope_sequence = _integer(body["scope_sequence"])
        if (body["schema"] != "mra-registration-event/v1" or body["ledger_id"] != self.store_id
                or sequence != state["count"] + 1 or body["previous_sha256"] != state["head"]
                or body["scope_id"] != history["scope_id"] or scope_sequence != history["sequence"] + 1
                or body["previous_scope_sha256"] != history["head_sha256"] or now < state["clock"]):
            raise StoreError("Registration event continuity rejected")
        kind, payload = body["kind"], body["payload"]
        if kind == "registered":
            registration = _registration(payload)
            identifier = registration["registration_id"]
            if (registration["agency_id"] != body["agency_id"] or registration["project_id"] != body["project_id"]
                    or registration["history"] != history or identifier in state["registrations"]
                    or len(state["registrations"]) >= MAX_REGISTRATIONS):
                raise StoreConflict("Registration or observed history changed")
            state["registrations"][identifier] = {"registration": registration,
                "registration_sha256": _digest(registration), "state": "registered", "completion": None,
                "failure_reason": None, "registered_sequence": scope_sequence,
                "training_sequence": None, "terminal_sequence": None}
            history["local_registrations"] += 1
        elif kind in ("training", "completed"):
            _exact(payload, {"ticket"} if kind == "training" else {"ticket", "completion"})
            record = self._require_ticket(state, _ticket(payload["ticket"]))
            if (record["registration"]["agency_id"] != body["agency_id"]
                    or record["registration"]["project_id"] != body["project_id"]):
                raise StoreConflict("Registration event scope changed")
            if kind == "training":
                if record["state"] != "registered":
                    raise StoreConflict("Registration has already started")
                record.update(state="training", training_sequence=scope_sequence)
            else:
                completion = _completion(payload["completion"])
                if (record["state"] != "training" or completion["registration_sha256"] != record["registration_sha256"]
                        or completion["review"]["profile_id"] != record["registration"]["profile_id"]):
                    raise StoreConflict("Completion does not match current training")
                record.update(state="completed", completion=completion, terminal_sequence=scope_sequence)
        elif kind == "failed":
            _exact(payload, {"registration_id", "reason"})
            identifier = _text(payload["registration_id"], _ID)
            reason = payload["reason"]
            record = state["registrations"].get(identifier)
            if (type(reason) is not str or reason not in _REASONS or record is None
                    or record["state"] not in ("registered", "training")
                    or record["registration"]["agency_id"] != body["agency_id"]
                    or record["registration"]["project_id"] != body["project_id"]):
                raise StoreConflict("Registration cannot enter failed state")
            record.update(state="failed", failure_reason=reason, terminal_sequence=scope_sequence)
        elif kind == "disclosure":
            disclosure = _disclosure(payload)
            identifier = disclosure["disclosure_id"]
            if (identifier in state["disclosures"] or len(state["disclosures"]) >= MAX_DISCLOSURES
                    or disclosure["occurred_at"] > now):
                raise StoreConflict("Observed disclosure is duplicated, future, or capacity bounded")
            state["disclosures"].add(identifier)
            history["known_disclosures"] += 1
        else:
            raise StoreError("Unknown registration event")
        state["scopes"][history["scope_id"]] = {"sequence": scope_sequence, "head_sha256": event_digest,
            "local_registrations": history["local_registrations"], "known_disclosures": history["known_disclosures"]}
        state.update(count=sequence, head=event_digest, clock=now)

    def _validate(self, connection):
        try:
            schema = connection.execute(
                "SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if (len(schema) != 2 or {row["name"] for row in schema} != {"meta", "events"}
                    or any(row["type"] != "table" for row in schema)
                    or {row["sql"] for row in schema} != set(_SCHEMA)):
                _unavailable()
            check = connection.execute("PRAGMA quick_check").fetchall()
            if (connection.execute("PRAGMA page_size").fetchone()[0] != 4096
                    or connection.execute("PRAGMA page_count").fetchone()[0] > 4096
                    or len(check) != 1 or check[0][0] != "ok"):
                _unavailable()
            metadata = dict(connection.execute("SELECT key,value FROM meta").fetchall())
            if (set(metadata) != {"schema", "store_id", "last_clock", "event_count", "head_sha256"}
                    or metadata["schema"] != _SCHEMA_ID or metadata["store_id"] != self.store_id):
                _unavailable()
            last_clock, count = _integer(int(metadata["last_clock"])), _integer(int(metadata["event_count"]))
            if str(last_clock) != metadata["last_clock"] or str(count) != metadata["event_count"] or count > MAX_EVENTS:
                _unavailable()
            _text(metadata["head_sha256"], _DIGEST)
            rows = connection.execute("SELECT * FROM events ORDER BY sequence LIMIT ?", (MAX_EVENTS + 1,)).fetchall()
            if len(rows) != count:
                _unavailable()
            state = {"registrations": {}, "disclosures": set(), "scopes": {}, "count": 0, "head": _ZERO, "clock": 0}
            for row in rows:
                if type(row["event_json"]) is not str:
                    _unavailable()
                raw = row["event_json"].encode("utf-8")
                event_digest = hashlib.sha256(raw).hexdigest()
                body = _decode(raw)
                if event_digest != row["event_sha256"] or row["sequence"] != body["sequence"]:
                    _unavailable()
                self._apply(state, body, event_digest)
            if state["head"] != metadata["head_sha256"] or state["clock"] > last_clock:
                _unavailable()
            return state
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, UnicodeError, RecursionError):
            raise StoreUnavailable("Registration store state rejected") from None

    @staticmethod
    def _clock(connection, guard):
        now = _integer(guard())
        previous = int(connection.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
        if now < previous:
            raise StoreUnavailable("Registration store clock moved backwards")
        connection.execute("UPDATE meta SET value=? WHERE key='last_clock'", (str(now),))
        return now

    @contextmanager
    def _transaction(self, guard):
        if not callable(guard):
            raise StoreError("A trusted current authorization and time guard is required")
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                state = self._validate(connection)
                now = self._clock(connection, guard)
                yield connection, state, now
                self._paths()
                current = self._validate(connection)
                if (current["count"], current["head"]) != (state["count"], state["head"]):
                    raise StoreConflict("Registration history changed before commit")
                # Replay can take time. Check live authority only after that
                # work, immediately before the final pinned-path check/commit.
                self._clock(connection, guard)
                self._paths()
                connection.commit()
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def _append(self, connection, state, agency_id, project_id, kind, payload, now):
        if state["count"] >= MAX_EVENTS:
            raise StoreConflict("Registration event capacity reached")
        history = self._history_for(state, agency_id, project_id)
        body = {"schema": "mra-registration-event/v1", "ledger_id": self.store_id,
            "sequence": state["count"] + 1, "scope_id": history["scope_id"],
            "scope_sequence": history["sequence"] + 1, "previous_sha256": state["head"],
            "previous_scope_sha256": history["head_sha256"], "agency_id": agency_id,
            "project_id": project_id, "occurred_at": now, "kind": kind, "payload": payload}
        raw = _encode(body)
        event_digest = hashlib.sha256(raw).hexdigest()
        self._apply(state, body, event_digest)
        connection.execute("INSERT INTO events VALUES(?,?,?)", (body["sequence"], event_digest, raw.decode("utf-8")))
        connection.execute("UPDATE meta SET value=? WHERE key='event_count'", (str(state["count"]),))
        connection.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (state["head"],))

    def history(self, agency_id, project_id, *, guard):
        """Observed local counts only; an empty scope does not imply no disclosures."""
        _scope(agency_id, project_id)
        with self._transaction(guard) as (_, state, _):
            result = self._history_for(state, agency_id, project_id)
        return _owned(result)

    def reserve(self, registration, *, guard):
        registration = _registration(registration)
        agency, project = registration["agency_id"], registration["project_id"]
        with self._transaction(guard) as (connection, state, now):
            self._append(connection, state, agency, project, "registered", registration, now)
            record = state["registrations"][registration["registration_id"]]
            ticket = self._ticket_for(record, self._history_for(state, agency, project))
        return _owned(ticket)

    def start(self, ticket, *, guard):
        ticket = _ticket(ticket)
        with self._transaction(guard) as (connection, state, now):
            record = self._require_ticket(state, ticket)
            registration = record["registration"]
            agency, project = registration["agency_id"], registration["project_id"]
            self._append(connection, state, agency, project, "training", {"ticket": ticket}, now)
            result = self._ticket_for(record, self._history_for(state, agency, project))
        return _owned(result)

    def complete(self, ticket, completion, *, guard):
        ticket, completion = _ticket(ticket), _completion(completion)
        with self._transaction(guard) as (connection, state, now):
            record = self._require_ticket(state, ticket)
            registration = record["registration"]
            self._append(connection, state, registration["agency_id"], registration["project_id"],
                         "completed", {"ticket": ticket, "completion": completion}, now)
            result = _owned(record)
        return result

    def fail(self, registration_id, reason, *, guard):
        registration_id = _text(registration_id, _ID)
        if type(reason) is not str or reason not in _REASONS:
            raise StoreError("Registration failure reason rejected")
        with self._transaction(guard) as (connection, state, now):
            record = state["registrations"].get(registration_id)
            if record is None:
                raise StoreConflict("Registration is unknown")
            registration = record["registration"]
            self._append(connection, state, registration["agency_id"], registration["project_id"],
                         "failed", {"registration_id": registration_id, "reason": reason}, now)
            result = _owned(record)
        return result

    def get(self, registration_id, *, guard):
        registration_id = _text(registration_id, _ID)
        with self._transaction(guard) as (_, state, _):
            record = state["registrations"].get(registration_id)
            if record is None:
                raise StoreConflict("Registration is unknown")
            result = _owned(record)
        return result

    def record_disclosure(self, agency_id, project_id, disclosure, *, expected_history, guard):
        _scope(agency_id, project_id)
        disclosure, expected_history = _disclosure(disclosure), _history(expected_history)
        with self._transaction(guard) as (connection, state, now):
            if expected_history != self._history_for(state, agency_id, project_id):
                raise StoreConflict("Observed disclosure history changed")
            self._append(connection, state, agency_id, project_id, "disclosure", disclosure, now)
            result = self._history_for(state, agency_id, project_id)
        return _owned(result)
