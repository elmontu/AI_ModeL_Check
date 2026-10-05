"""Bounded local delivery ledger with an externally supplied checkpoint floor.

Only a trusted in-process gateway capability can retain or take candidate bytes.
This is an application boundary, not a hostile-Python sandbox or independent
agency custody. Admissions record attempted emission, never recipient receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import secrets
import sqlite3
import stat

from .contracts import (FLAGS, MAX_ARTIFACT_BYTES, MAX_STATE_BYTES, DeliveryError, canonical_bytes,
    digest, strict_json, owned, integer, identifier, hex_id, validate_digest, validate_case,
    validate_actor, validate_pin, validate_payload, validate_artifact)

MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_CASES = 32
MAX_ACTIVATIONS = 16
MAX_GRANTS = 128
MAX_EVENTS = 2048
MAX_ADMISSIONS = 2048
MAX_TRANSFER_ADMISSIONS = 256
_DATABASE = "delivery.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE artifacts (activation_id TEXT PRIMARY KEY, content BLOB NOT NULL) STRICT",
    "CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
)
_META = {"store_id", "event_count", "head_sha256", "last_clock"}
_PUBLIC_OPERATIONS = {"grant", "suspend", "resume", "revoke", "revoke_grant", "observe"}


class StoreError(DeliveryError):
    """Malformed trusted delivery-store operation."""


class StoreConflict(StoreError):
    """A permanent binding, floor, lifecycle or admission conflicts."""


class StoreUnavailable(RuntimeError):
    """Current retained bytes, event history, path or clock cannot be verified."""


def _unavailable():
    raise StoreUnavailable("Fixture delivery store unavailable")


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise StoreError("Delivery metadata rejected")


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


def _decode(raw):
    value = strict_json(raw)
    if canonical_bytes(value) != raw:
        raise StoreError("Delivery metadata is not canonical")
    return value


def _configuration(cases):
    if type(cases) is not list or not 1 <= len(cases) <= MAX_CASES:
        raise StoreError("Explicit bounded cases are required")
    cases = [validate_case(case) for case in cases]
    if len({case["case_id"] for case in cases}) != len(cases):
        raise StoreError("Case identifiers must be unique")
    return sorted(cases, key=lambda case: case["case_id"])


def _blank(artifacts=None):
    return {"cases": {}, "activation_ids": set(), "grant_ids": set(), "transfer_ids": set(),
            "request_ids": set(), "chunk_ids": set(), "artifacts": artifacts or {},
            "count": 0, "head": "0" * 64, "clock": 0, "pins": {}}


def _record(operation, payload, actor, now):
    body = {"operation": operation, "payload": payload, "actor": actor, "recorded_at": now}
    return {**body, "sha256": digest(body)}


class DeliveryStore:
    def __init__(self, root, *, expected_pin):
        pin = validate_pin(expected_pin)
        self._store_id = pin["store_id"]
        self._initial_pin = None
        self._gateway_owner = self._gateway_capability = None
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
            raise StoreUnavailable("Fixture delivery store unavailable") from None

    @property
    def root(self):
        return self._root

    @property
    def store_id(self):
        return self._store_id

    @property
    def initial_pin(self):
        if self._initial_pin is None:
            raise StoreError("Initial checkpoint exists only on a freshly created store")
        return owned(self._initial_pin)

    @classmethod
    def open(cls, root, *, expected_pin):
        return cls(root, expected_pin=expected_pin)

    @classmethod
    def create(cls, root, *, cases, guard):
        cases = _configuration(cases)
        now = cls._clock(guard, 0)
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            path = root / _DATABASE
            with path.open("xb"):
                pass
            store = object.__new__(cls)
            store._root, store._path, store._store_id = root, path, secrets.token_hex(16)
            store._initial_pin = None
            store._gateway_owner = store._gateway_capability = None
            store._root_identity, store._db_identity = _identity(root.lstat()), _identity(path.lstat())
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
                meta = {"store_id": store.store_id, "event_count": 0, "head_sha256": "0" * 64, "last_clock": now}
                connection.executemany("INSERT INTO meta VALUES (?, ?)", [(key, canonical_bytes(value).decode("ascii")) for key, value in meta.items()])
                state = _blank()
                store._append(connection, state, "created", None, {"cases": cases}, None, now)
                store._validate(connection)
                store._meta(connection, "last_clock", store._clock(guard, now))
                store._paths()
                connection.commit()
                store._initial_pin = store._pin(state)
            finally:
                connection.close()
            return store
        except (OSError, sqlite3.Error):
            raise StoreUnavailable("Fixture delivery creation unavailable") from None

    def _bind_gateway(self, owner):
        """Trusted bootstrap only. A new owner replaces this object's old seal."""
        if owner is None:
            raise StoreError("A trusted gateway owner is required")
        if owner is not self._gateway_owner:
            self._gateway_owner, self._gateway_capability = owner, object()
        return self._gateway_capability

    def _require_capability(self, capability):
        if self._gateway_capability is None or capability is not self._gateway_capability:
            raise StoreConflict("Only the bound trusted gateway can handle fixture bytes")

    def _sealed_guard(self, capability, guard):
        def current():
            self._require_capability(capability)
            now = guard()
            self._require_capability(capability)
            return now
        return current

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
            raise StoreUnavailable("Fixture delivery filesystem unavailable") from None

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
            raise StoreUnavailable("Fixture delivery database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _clock(guard, floor):
        if not callable(guard):
            raise StoreError("A trusted current guard is required")
        now = guard()
        if type(now) is not int or not floor <= now <= 2 ** 53 - 1:
            raise StoreUnavailable("Delivery clock moved backwards or is invalid")
        return now

    @staticmethod
    def _meta(connection, key, value):
        connection.execute("UPDATE meta SET value=? WHERE key=?", (canonical_bytes(value).decode("ascii"), key))

    def _pin(self, state):
        return {"schema": "mra-fixture-delivery-pin/v1", "store_id": self.store_id,
                "sequence": state["count"], "head_sha256": state["head"]}

    def _floor(self, state, pin):
        pin = validate_pin(pin)
        if pin["store_id"] != self.store_id or state["pins"].get(pin["sequence"]) != pin["head_sha256"]:
            raise StoreConflict("External delivery checkpoint is not an exact retained ancestor")

    @staticmethod
    def _case(state, case_id):
        identifier(case_id)
        if case_id not in state["cases"]:
            raise StoreConflict("Delivery case is not configured")
        return state["cases"][case_id]

    @staticmethod
    def _activation(case, activation_id):
        record = case["activations"].get(activation_id)
        if record is None:
            raise StoreConflict("Activation is outside the exact case")
        return record

    @staticmethod
    def _grant(case, grant_id):
        record = case["grants"].get(grant_id)
        if record is None:
            raise StoreConflict("Grant is outside the exact case")
        return record

    def _current(self, case, activation_id, now):
        activation = self._activation(case, activation_id)
        if activation["state"] != "active" or not activation["recorded_at"] <= now < activation["payload"]["expires_at"]:
            raise StoreConflict("Activation is suspended, revoked or expired")
        return activation

    def _deadlines(self, case, operation, payload, now):
        if operation == "activate":
            if payload["expires_at"] <= now:
                raise StoreConflict("Activation deadline is not current")
            return [payload["expires_at"]]
        if operation in ("grant", "resume", "admit"):
            activation = self._activation(case, payload["activation_id"])
            result = [activation["payload"]["expires_at"]]
            if operation == "grant":
                result.append(payload["expires_at"])
            if operation == "admit":
                result.append(self._grant(case, payload["grant_id"])["payload"]["expires_at"])
            if any(now >= deadline for deadline in result):
                raise StoreConflict("Delivery deadline has expired")
            return result
        return []

    def _transition(self, state, case, operation, payload, actor, now):
        record = _record(operation, payload, actor, now)
        self._deadlines(case, operation, payload, now)
        if operation == "activate":
            aid = payload["activation_id"]
            if (any(payload[key] != case["case"][key] for key in ("agency_id", "project_id", "case_id"))
                    or aid in state["activation_ids"] or len(state["activation_ids"]) >= MAX_ACTIVATIONS):
                raise StoreConflict("Activation scope, permanent identifier or capacity conflicts")
            raw = state["artifacts"].get(aid)
            validate_artifact(raw, payload)
            case["activations"][aid] = {**record, "state": "active"}
            state["activation_ids"].add(aid)
        elif operation == "grant":
            activation = self._current(case, payload["activation_id"], now)
            if (payload["grant_id"] in state["grant_ids"] or payload["transfer_id"] in state["transfer_ids"]
                    or len(state["grant_ids"]) >= MAX_GRANTS
                    or payload["recipient_id"] != activation["payload"]["recipient_id"]
                    or not now < payload["expires_at"] <= min(now + 60, activation["payload"]["expires_at"])
                    or payload["max_attempted_bytes"] > 3 * activation["payload"]["artifact_size"]):
                raise StoreConflict("Grant differs from the exact bounded activation or reuses a permanent ID")
            case["grants"][payload["grant_id"]] = {**record, "revoked": False,
                "attempted_bytes": 0, "next_offset": 0, "admission_count": 0}
            state["grant_ids"].add(payload["grant_id"])
            state["transfer_ids"].add(payload["transfer_id"])
        elif operation in ("suspend", "resume", "revoke"):
            activation = self._activation(case, payload["activation_id"])
            required = "suspended" if operation == "resume" else "active"
            if operation == "revoke":
                if activation["state"] == "revoked":
                    raise StoreConflict("Revocation is permanent")
            elif activation["state"] != required:
                raise StoreConflict("Activation lifecycle transition is not current")
            activation["state"] = {"suspend": "suspended", "resume": "active", "revoke": "revoked"}[operation]
        elif operation == "revoke_grant":
            grant = self._grant(case, payload["grant_id"])
            if grant["revoked"]:
                raise StoreConflict("Grant revocation is permanent")
            grant["revoked"] = True
        elif operation == "admit":
            activation = self._current(case, payload["activation_id"], now)
            grant = self._grant(case, payload["grant_id"])
            scope = grant["payload"]
            if (grant["revoked"] or scope["activation_id"] != payload["activation_id"]
                    or scope["transfer_id"] != payload["transfer_id"]
                    or actor["person_id"] != scope["recipient_person_id"]
                    or actor["credential_sha256"] != scope["recipient_credential_sha256"]
                    or not grant["recorded_at"] <= now < scope["expires_at"]):
                raise StoreConflict("Chunk does not have the exact current recipient grant")
            if (payload["request_id"] in state["request_ids"] or payload["chunk_id"] in state["chunk_ids"]
                    or len(state["request_ids"]) >= MAX_ADMISSIONS
                    or grant["admission_count"] >= MAX_TRANSFER_ADMISSIONS
                    or grant["attempted_bytes"] + payload["length"] > scope["max_attempted_bytes"]
                    or payload["offset"] + payload["length"] > activation["payload"]["artifact_size"]):
                raise StoreConflict("Admission is repeated, out of bounds or exhausted")
            next_chunk = payload["offset"] == grant["next_offset"]
            exact_retry = any(row["grant_id"] == payload["grant_id"] and row["offset"] == payload["offset"]
                and row["length"] == payload["length"] for row in case["admissions"].values())
            if not next_chunk and not exact_retry:
                raise StoreConflict("Only the next chunk or an exact newly admitted retry is allowed")
            raw = state["artifacts"][payload["activation_id"]]
            chunk = raw[payload["offset"]:payload["offset"] + payload["length"]]
            body = {**payload, "recipient_id": scope["recipient_id"], "recipient_person_id": scope["recipient_person_id"],
                "chunk_sha256": hashlib.sha256(chunk).hexdigest(), "admitted_at": now, "actor": actor}
            case["admissions"][payload["request_id"]] = {**body, "sha256": digest(body)}
            state["request_ids"].add(payload["request_id"])
            state["chunk_ids"].add(payload["chunk_id"])
            grant["attempted_bytes"] += payload["length"]
            grant["admission_count"] += 1
            if next_chunk:
                grant["next_offset"] += payload["length"]
        elif operation == "observe":
            admission = case["admissions"].get(payload["request_id"])
            if (admission is None or payload["request_id"] in case["observations"]
                    or any(actor[key] != admission["actor"][key] for key in ("person_id", "credential_sha256"))):
                raise StoreConflict("Write observation must match one exact retained admission")
            if payload["write_extent_known"]:
                if payload["bytes_written"] > admission["length"]:
                    raise StoreConflict("Observed bytes exceed the admitted chunk")
                if payload["status"] == "returned" and payload["bytes_written"] != admission["length"]:
                    raise StoreConflict("Returned chunk observation requires its exact admitted length")
            case["observations"][payload["request_id"]] = record
        else:
            raise StoreError("Unknown delivery operation")

    def _apply_event(self, state, event, event_hash):
        _exact(event, {"schema", "store_id", "sequence", "previous_sha256", "occurred_at", "operation", "case_id", "payload", "actor"})
        integer(event["sequence"], 1, MAX_EVENTS)
        integer(event["occurred_at"])
        if (event["schema"] != "mra-fixture-delivery-history/v1" or event["store_id"] != self.store_id
                or event["sequence"] != state["count"] + 1 or event["previous_sha256"] != state["head"]
                or event["occurred_at"] < state["clock"]):
            raise StoreConflict("Delivery history changed")
        operation = event["operation"]
        if operation == "created":
            _exact(event["payload"], {"cases"})
            cases = _configuration(event["payload"]["cases"])
            if state["count"] != 0 or event["case_id"] is not None or event["actor"] is not None or cases != event["payload"]["cases"]:
                raise StoreConflict("Delivery bootstrap cannot be replayed")
            for case in cases:
                state["cases"][case["case_id"]] = {"case": case, "activations": {}, "grants": {}, "admissions": {}, "observations": {}}
        elif state["count"] == 0:
            raise StoreConflict("Delivery bootstrap is missing")
        else:
            case = self._case(state, event["case_id"])
            payload = validate_payload(operation, event["payload"])
            actor = validate_actor(event["actor"])
            self._transition(state, case, operation, payload, actor, event["occurred_at"])
        state.update(count=event["sequence"], head=event_hash, clock=event["occurred_at"])
        state["pins"][state["count"]] = event_hash

    def _append(self, connection, state, operation, case_id, payload, actor, now):
        if state["count"] >= MAX_EVENTS:
            raise StoreConflict("Delivery event capacity reached")
        event = {"schema": "mra-fixture-delivery-history/v1", "store_id": self.store_id,
            "sequence": state["count"] + 1, "previous_sha256": state["head"], "occurred_at": now,
            "operation": operation, "case_id": case_id, "payload": payload, "actor": actor}
        event_hash = digest(event)
        self._apply_event(state, event, event_hash)
        connection.execute("INSERT INTO events VALUES (?, ?, ?)", (event["sequence"], event_hash, canonical_bytes(event).decode("ascii")))
        self._meta(connection, "event_count", state["count"])
        self._meta(connection, "head_sha256", state["head"])
        self._meta(connection, "last_clock", now)

    def _validate(self, connection):
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1 or connection.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                _unavailable()
            rows = connection.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%' ORDER BY name").fetchall()
            if {(row["type"], row["name"]): row["sql"] for row in rows} != {("table", sql.split()[2]): sql for sql in _SCHEMA}:
                _unavailable()
            meta_rows = connection.execute("SELECT key,value FROM meta LIMIT 5").fetchall()
            if {row["key"] for row in meta_rows} != _META or len(meta_rows) != len(_META):
                _unavailable()
            meta = {row["key"]: _decode(row["value"].encode("ascii")) for row in meta_rows}
            if meta["store_id"] != self.store_id:
                _unavailable()
            integer(meta["event_count"], 1, MAX_EVENTS)
            integer(meta["last_clock"])
            validate_digest(meta["head_sha256"])
            roster = connection.execute("SELECT activation_id,length(content) AS size FROM artifacts LIMIT ?", (MAX_ACTIVATIONS + 1,)).fetchall()
            if len(roster) > MAX_ACTIVATIONS or sum(row["size"] for row in roster) > MAX_TOTAL_ARTIFACT_BYTES:
                _unavailable()
            artifacts = {}
            for row in roster:
                hex_id(row["activation_id"])
                integer(row["size"], 1, MAX_ARTIFACT_BYTES)
                raw = connection.execute("SELECT content FROM artifacts WHERE activation_id=?", (row["activation_id"],)).fetchone()[0]
                if type(raw) is not bytes or len(raw) != row["size"]:
                    _unavailable()
                artifacts[row["activation_id"]] = raw
            rows = connection.execute("SELECT * FROM events ORDER BY sequence LIMIT ?", (MAX_EVENTS + 1,)).fetchall()
            if len(rows) != meta["event_count"]:
                _unavailable()
            state = _blank(artifacts)
            for index, row in enumerate(rows, 1):
                event = _decode(row["event_json"].encode("ascii"))
                event_hash = digest(event)
                if row["sequence"] != index or row["event_sha256"] != event_hash:
                    _unavailable()
                self._apply_event(state, event, event_hash)
            if (state["head"] != meta["head_sha256"] or state["clock"] > meta["last_clock"]
                    or state["activation_ids"] != set(artifacts)):
                _unavailable()
            state["clock"] = meta["last_clock"]
            return state
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            raise StoreUnavailable("Fixture delivery state validation failed") from None

    @contextmanager
    def _transaction(self, expected_pin, guard):
        pin = validate_pin(expected_pin)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                state = self._validate(connection)
                self._floor(state, pin)
                now = self._clock(guard, state["clock"])
                deadlines = []
                yield connection, state, now, deadlines
                current = self._validate(connection)
                if (current["count"], current["head"]) != (state["count"], state["head"]):
                    raise StoreConflict("Delivery history changed before commit")
                self._floor(current, pin)
                final = self._clock(guard, max(now, current["clock"]))
                if any(final >= deadline for deadline in deadlines):
                    raise StoreConflict("Delivery eligibility expired before commit")
                self._meta(connection, "last_clock", final)
                self._paths()
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _snapshot(self, state, case):
        return owned({"schema": "mra-fixture-delivery-case/v1", "store_id": self.store_id,
            **case, "event_count": state["count"], "head_sha256": state["head"], "pin": self._pin(state),
            **FLAGS}, max_bytes=MAX_STATE_BYTES)

    def _mutate(self, case_id, operation, payload, actor, *, expected_pin, expected_head_sha256, guard,
                artifact_bytes=None):
        payload, actor = validate_payload(operation, payload), validate_actor(actor)
        validate_digest(expected_head_sha256)
        with self._transaction(expected_pin, guard) as (connection, state, now, deadlines):
            if state["head"] != expected_head_sha256:
                raise StoreConflict("Delivery state changed after current authority was captured")
            case = self._case(state, case_id)
            deadlines.extend(self._deadlines(case, operation, payload, now))
            if operation == "activate":
                raw = validate_artifact(artifact_bytes, payload)
                if payload["activation_id"] in state["artifacts"] or sum(map(len, state["artifacts"].values())) + len(raw) > MAX_TOTAL_ARTIFACT_BYTES:
                    raise StoreConflict("Retained artifact identifier or capacity conflicts")
                connection.execute("INSERT INTO artifacts VALUES (?, ?)", (payload["activation_id"], raw))
                state["artifacts"][payload["activation_id"]] = raw
            self._append(connection, state, operation, case_id, payload, actor, now)
            if operation == "admit":
                raw = state["artifacts"][payload["activation_id"]]
                result = {"admission": owned(case["admissions"][payload["request_id"]]),
                    "bytes": raw[payload["offset"]:payload["offset"] + payload["length"]], "pin": self._pin(state)}
            else:
                result = self._snapshot(state, case)
        # No byte buffer is returned until admission and its final guard commit.
        return result

    def apply(self, case_id, operation, payload, actor, *, expected_pin, expected_head_sha256, guard):
        if type(operation) is not str or operation not in _PUBLIC_OPERATIONS:
            raise StoreError("Public metadata API cannot activate or admit bytes")
        return self._mutate(case_id, operation, payload, actor, expected_pin=expected_pin,
                            expected_head_sha256=expected_head_sha256, guard=guard)

    def _activate(self, case_id, payload, actor, *, artifact_bytes, capability, expected_pin, expected_head_sha256, guard):
        self._require_capability(capability)
        return self._mutate(case_id, "activate", payload, actor, artifact_bytes=artifact_bytes,
            expected_pin=expected_pin, expected_head_sha256=expected_head_sha256, guard=self._sealed_guard(capability, guard))

    def _take_chunk(self, case_id, payload, actor, *, capability, expected_pin, expected_head_sha256, guard):
        self._require_capability(capability)
        return self._mutate(case_id, "admit", payload, actor, expected_pin=expected_pin,
                            expected_head_sha256=expected_head_sha256, guard=self._sealed_guard(capability, guard))

    def get(self, case_id, *, expected_pin, guard):
        with self._transaction(expected_pin, guard) as (_, state, _, _):
            result = self._snapshot(state, self._case(state, case_id))
        return result

    def inspect(self, *, expected_pin, guard):
        with self._transaction(expected_pin, guard) as (_, state, _, _):
            result = owned({"schema": "mra-fixture-delivery-inspection/v1", "store_id": self.store_id,
                "cases": {key: self._snapshot(state, case) for key, case in sorted(state["cases"].items())},
                "event_count": state["count"], "head_sha256": state["head"], "pin": self._pin(state),
                **FLAGS}, max_bytes=MAX_STATE_BYTES)
        return result
