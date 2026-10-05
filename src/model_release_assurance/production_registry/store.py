"""Bounded authoritative LOCAL fixture registry, transactional migration/outbox.

Each fictional commit costs exactly one engineering unit, never DP epsilon or a
privacy budget. Immutable configured accounts span cases. SQLite transactions
atomically retain heads, charge, receipts and metadata events. Broker epochs
fence one current database, not privileged whole-store rollback or cloud HA.
No model bytes, external send, production approval, reset or refund API exists.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from .contracts import (ACCOUNT_CAPACITY, FLAGS, GENESIS_SHA256, RegistryContractError,
    account_id, canonical_bytes, create_outbox_event, create_receipt, digest, hex_id,
    identifier, integer, strict_json, validate_commit_context, validate_digest,
    validate_outbox_event, validate_receipt, validate_request)

MAX_DATABASE_BYTES = 16 * 1024 * 1024
MAX_ACCOUNTS = 32
MAX_CASES = 128
MAX_RECEIPTS = 256
MAX_EVENTS = 2048
MAX_BROKERS = 64
MAX_DELIVERY_ATTEMPTS = 8
_DATABASE = "registry.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE accounts (id TEXT PRIMARY KEY, record_json TEXT NOT NULL) STRICT",
    "CREATE TABLE cases (id TEXT PRIMARY KEY, record_json TEXT NOT NULL) STRICT",
    "CREATE TABLE receipts (id TEXT PRIMARY KEY, record_json TEXT NOT NULL, receipt_id TEXT NOT NULL UNIQUE, event_id TEXT NOT NULL UNIQUE) STRICT",
    "CREATE TABLE outbox (id TEXT PRIMARY KEY, record_json TEXT NOT NULL) STRICT",
    "CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
)
_DELIVERY_SCHEMA = "CREATE TABLE deliveries (id TEXT PRIMARY KEY, record_json TEXT NOT NULL) STRICT"
_LEASE = {"store_id", "event_id", "account_id", "case_id", "owner_sha256", "lease_id", "generation",
          "broker_id", "broker_epoch", "claimed_at", "expires_at"}
_META = {"store_id", "schema_version", "broker_id", "broker_epoch", "last_clock", "event_count", "head_sha256"}


class StoreError(ValueError):
    """Malformed fixture registry operation."""


class StoreConflict(StoreError):
    """CAS, capacity, broker, lease or permanent idempotency conflict."""


class StoreUnavailable(RuntimeError):
    """Current local state or its filesystem/clock cannot be established."""


def _unavailable():
    raise StoreUnavailable("Fixture registry unavailable")


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise StoreError("Fixture registry metadata rejected")


def _owned(value):
    return strict_json(canonical_bytes(value))


def _decode(raw):
    value = strict_json(raw)
    if canonical_bytes(value) != raw:
        raise StoreError("Fixture registry JSON is not canonical")
    return value


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


def _configuration(accounts):
    if type(accounts) is not list or not 1 <= len(accounts) <= MAX_ACCOUNTS:
        raise StoreError("Explicit bounded fixture accounts are required")
    result, seen = [], set()
    for value in accounts:
        _exact(value, {"agency_id", "project_id"})
        scope = account_id(value["agency_id"], value["project_id"])
        if scope in seen:
            raise StoreError("Fixture account is duplicated")
        seen.add(scope)
        result.append({"agency_id": value["agency_id"], "project_id": value["project_id"]})
    return sorted(result, key=lambda row: account_id(row["agency_id"], row["project_id"]))


def _case_key(agency, project, case):
    identifier(case)
    return digest({"account_id": account_id(agency, project), "case_id": case})


def _request_key(request):
    return digest({"account_id": request["account_id"], "request_id": request["request_id"]})


def _broker(value):
    _exact(value, {"store_id", "broker_id", "epoch"})
    hex_id(value["store_id"])
    hex_id(value["broker_id"])
    integer(value["epoch"], 1)
    return _owned(value)


def _lease(value):
    _exact(value, _LEASE)
    for key in ("store_id", "event_id", "lease_id", "broker_id"):
        hex_id(value[key])
    for key in ("account_id", "owner_sha256"):
        validate_digest(value[key])
    identifier(value["case_id"])
    integer(value["generation"], 1, MAX_DELIVERY_ATTEMPTS)
    integer(value["broker_epoch"], 1)
    integer(value["claimed_at"])
    integer(value["expires_at"])
    if not value["claimed_at"] < value["expires_at"] <= value["claimed_at"] + 60:
        raise StoreError("Outbox lease lifetime rejected")
    return _owned(value)


def _empty_delivery():
    return {"generation": 0, "lease": None, "acknowledgment": None}


def _blank():
    return {"version": 0, "accounts": {}, "cases": {}, "receipts": {}, "outbox": {}, "deliveries": {},
            "brokers": set(), "broker_id": None, "epoch": 0, "lease_ids": set(),
            "count": 0, "head": GENESIS_SHA256, "clock": 0}


def _core_digest(state):
    # Each per-table digest remains below the 64KiB canonical contract bound.
    return digest({name: digest([[key, digest(value)] for key, value in sorted(state[name].items())])
                   for name in ("accounts", "cases", "receipts", "outbox")})


class RegistryStore:
    """Guarded local bootstrap/transaction boundary; not an authentication API."""

    def __init__(self, root, expected_store_id, expected_schema_version=2):
        try:
            hex_id(expected_store_id)
            integer(expected_schema_version, 1, 2)
            self._store_id, self._version = expected_store_id, expected_schema_version
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE
            _directories(self._root)
            self._root_identity = _identity(self._root.lstat())
            self._db_identity = _identity(self._path.lstat())
        except (OSError, ValueError, TypeError):
            raise StoreUnavailable("Fixture registry unavailable") from None
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

    @property
    def schema_version(self):
        return self._version

    @classmethod
    def create(cls, root, *, accounts, schema_version=2):
        accounts = _configuration(accounts)
        integer(schema_version, 1, 2)
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            _directories(root)
            path = root / _DATABASE
            with path.open("xb"):
                pass
            store = object.__new__(cls)
            store._store_id, store._version = secrets.token_hex(16), schema_version
            store._root, store._path = root, path
            store._root_identity, store._db_identity = _identity(root.lstat()), _identity(path.lstat())
            connection = sqlite3.connect(path, timeout=2.0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            try:
                connection.enable_load_extension(False)
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA page_size=4096")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA max_page_count=4096")
                connection.execute("BEGIN IMMEDIATE")
                for sql in _SCHEMA + ((_DELIVERY_SCHEMA,) if schema_version == 2 else ()):
                    connection.execute(sql)
                connection.execute("PRAGMA user_version=" + str(schema_version))
                connection.executemany("INSERT INTO meta VALUES(?,?)", (
                    ("store_id", store.store_id), ("schema_version", str(schema_version)),
                    ("broker_id", ""), ("broker_epoch", "0"), ("last_clock", "0"),
                    ("event_count", "0"), ("head_sha256", GENESIS_SHA256)))
                state = _blank()
                store._append(connection, state, "created", {"schema_version": schema_version, "accounts": accounts}, 0)
                store._validate(connection)
                connection.commit()
            finally:
                connection.close()
            return cls(root, store.store_id, schema_version)
        except (OSError, sqlite3.Error, ValueError, TypeError):
            raise StoreUnavailable("Fixture registry creation unavailable") from None

    @classmethod
    def open(cls, root, expected_store_id, *, expected_schema_version=2):
        return cls(root, expected_store_id, expected_schema_version)

    @classmethod
    def migrate(cls, root, expected_store_id, *, from_version=1, to_version=2, guard):
        if type(from_version) is not int or type(to_version) is not int or (from_version, to_version) != (1, 2):
            raise StoreError("Only explicit registry migration 1 to 2 is supported")
        store = cls.open(root, expected_store_id, expected_schema_version=1)
        with store._transaction(guard) as (connection, state, now, _):
            connection.execute(_DELIVERY_SCHEMA)
            connection.execute("PRAGMA user_version=2")
            store._append(connection, state, "migrated", {"from_version": 1, "to_version": 2,
                          "preserved_sha256": _core_digest(state)}, now)
        return cls.open(root, expected_store_id, expected_schema_version=2)

    def _paths(self):
        try:
            _directories(self.root)
            if _identity(self.root.lstat()) != self._root_identity:
                _unavailable()
            info = self._path.lstat()
            if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or _identity(info) != self._db_identity or not 1 <= info.st_size <= MAX_DATABASE_BYTES):
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
            raise StoreUnavailable("Fixture registry filesystem unavailable") from None

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
            connection.execute("PRAGMA max_page_count=4096")
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                _unavailable()
            self._paths()
            yield connection
        except sqlite3.Error:
            raise StoreUnavailable("Fixture registry database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def _account(self, state, agency, project):
        record = state["accounts"].get(account_id(agency, project))
        if record is None:
            raise StoreConflict("Fixture account is not configured")
        return record

    def _case(self, state, agency, project, case):
        account = self._account(state, agency, project)
        return state["cases"].get(_case_key(agency, project, case), {"agency_id": agency, "project_id": project,
            "case_id": case, "account_id": account["account_id"], "sequence": 0, "head_sha256": GENESIS_SHA256})

    def _require_broker(self, state, broker):
        if broker != {"store_id": self.store_id, "broker_id": state["broker_id"], "epoch": state["epoch"]}:
            raise StoreConflict("Fixture broker is no longer current")

    def _ack(self, lease, now):
        return {"schema": "mra-fixture-registry-ack/v1", **{key: lease[key] for key in
            ("store_id", "event_id", "lease_id", "generation", "broker_id", "broker_epoch", "owner_sha256")},
            "acked_at": now, **FLAGS}

    def _apply(self, state, body, event_hash):
        _exact(body, {"schema", "store_id", "sequence", "previous_sha256", "occurred_at", "kind", "payload"})
        integer(body["sequence"], 1, MAX_EVENTS)
        now = integer(body["occurred_at"])
        if (body["schema"] != "mra-fixture-registry-history/v1" or body["store_id"] != self.store_id
                or body["sequence"] != state["count"] + 1 or body["previous_sha256"] != state["head"]
                or now < state["clock"]):
            raise StoreConflict("Fixture registry history changed")
        kind, payload = body["kind"], body["payload"]
        if kind == "created":
            _exact(payload, {"schema_version", "accounts"})
            version = integer(payload["schema_version"], 1, 2)
            configuration = _configuration(payload["accounts"])
            if state["count"] != 0 or now != 0 or configuration != payload["accounts"]:
                raise StoreConflict("Fixture registry creation replayed")
            state["version"] = version
            for scope in configuration:
                key = account_id(scope["agency_id"], scope["project_id"])
                state["accounts"][key] = {**scope, "account_id": key, "sequence": 0,
                    "head_sha256": GENESIS_SHA256, "total_engineering_charge_units": 0,
                    "capacity_units": ACCOUNT_CAPACITY}
        elif state["version"] not in (1, 2):
            raise StoreConflict("Fixture registry has no creation history")
        elif kind == "broker":
            _exact(payload, {"broker_id", "expected_epoch"})
            broker = hex_id(payload["broker_id"])
            integer(payload["expected_epoch"])
            if (payload["expected_epoch"] != state["epoch"] or broker in state["brokers"]
                    or len(state["brokers"]) >= MAX_BROKERS):
                raise StoreConflict("Fixture broker activation conflicts")
            state["brokers"].add(broker)
            state["broker_id"], state["epoch"] = broker, state["epoch"] + 1
        elif kind == "committed":
            _exact(payload, {"request", "receipt"})
            request = validate_request(payload["request"])
            receipt = validate_receipt(payload["receipt"], request=request)
            record = receipt["receipt"]
            context = record["commit_context"]
            self._require_broker(state, {"store_id": request["store_id"], "broker_id": context["broker_id"], "epoch": context["broker_epoch"]})
            account = self._account(state, request["agency_id"], request["project_id"])
            case = self._case(state, request["agency_id"], request["project_id"], request["case_id"])
            key = _request_key(request)
            if (record["committed_at"] != now or account["sequence"] != request["expected_account_sequence"]
                    or account["head_sha256"] != request["expected_account_head_sha256"]
                    or case["sequence"] != request["expected_case_sequence"]
                    or case["head_sha256"] != request["expected_case_head_sha256"]
                    or account["total_engineering_charge_units"] >= ACCOUNT_CAPACITY
                    or key in state["receipts"] or len(state["receipts"]) >= MAX_RECEIPTS
                    or record["event_id"] in state["outbox"]
                    or any(value["receipt"]["receipt_id"] == record["receipt_id"] for value in state["receipts"].values())):
                raise StoreConflict("Fixture commit conflicts or account capacity is exhausted")
            case_key = _case_key(request["agency_id"], request["project_id"], request["case_id"])
            if case_key not in state["cases"] and len(state["cases"]) >= MAX_CASES:
                raise StoreConflict("Fixture case capacity reached")
            expected = create_receipt(request, context, receipt_id=record["receipt_id"], event_id=record["event_id"], committed_at=now)
            if canonical_bytes(expected) != canonical_bytes(receipt):
                raise StoreConflict("Fixture receipt differs from its exact intent")
            account.update(sequence=record["account_sequence"], head_sha256=receipt["receipt_sha256"],
                           total_engineering_charge_units=record["total_engineering_charge_units"])
            state["cases"][case_key] = {**case, "sequence": record["case_sequence"], "head_sha256": receipt["receipt_sha256"]}
            state["receipts"][key] = receipt
            state["outbox"][record["event_id"]] = create_outbox_event(request, receipt)
            if state["version"] == 2:
                state["deliveries"][record["event_id"]] = _empty_delivery()
        elif kind == "migrated":
            _exact(payload, {"from_version", "to_version", "preserved_sha256"})
            if (type(payload["from_version"]) is not int or type(payload["to_version"]) is not int
                    or (state["version"], payload["from_version"], payload["to_version"]) != (1, 1, 2)
                    or payload["preserved_sha256"] != _core_digest(state)):
                raise StoreConflict("Fixture migration history conflicts")
            state["version"] = 2
            state["deliveries"] = {key: _empty_delivery() for key in state["outbox"]}
            # A schema transition invalidates every pre-migration broker.
            state["broker_id"], state["epoch"] = None, state["epoch"] + 1
        elif kind in ("claimed", "acknowledged"):
            if state["version"] != 2:
                raise StoreConflict("Outbox delivery requires registry schema 2")
            _exact(payload, {"lease"} if kind == "claimed" else {"lease", "acknowledgment"})
            lease = _lease(payload["lease"])
            self._require_broker(state, {"store_id": lease["store_id"], "broker_id": lease["broker_id"], "epoch": lease["broker_epoch"]})
            event = state["outbox"].get(lease["event_id"])
            delivery = state["deliveries"].get(lease["event_id"])
            if (event is None or delivery is None or event["account_id"] != lease["account_id"]
                    or event["case_id"] != lease["case_id"] or delivery["acknowledgment"] is not None):
                raise StoreConflict("Outbox scope or durable acknowledgment differs")
            if kind == "claimed":
                previous = delivery["lease"]
                if (lease["claimed_at"] != now or lease["generation"] != delivery["generation"] + 1
                        or lease["lease_id"] in state["lease_ids"]
                        or (previous is not None and previous["broker_epoch"] == state["epoch"] and now < previous["expires_at"])):
                    raise StoreConflict("Outbox lease is replayed or already current")
                state["lease_ids"].add(lease["lease_id"])
                delivery.update(generation=lease["generation"], lease=lease)
            else:
                expected = self._ack(lease, now)
                if (delivery["lease"] != lease or not lease["claimed_at"] <= now < lease["expires_at"]
                        or canonical_bytes(payload["acknowledgment"]) != canonical_bytes(expected)):
                    raise StoreConflict("Outbox acknowledgment is stale or mismatched")
                delivery["acknowledgment"] = expected
        else:
            raise StoreError("Unknown fixture registry event")
        state.update(count=body["sequence"], head=event_hash, clock=now)

    def _write_record(self, connection, table, key, value):
        """Natural write boundary used by fixed fault-injection tests only."""
        raw = canonical_bytes(value).decode("ascii")
        previous = connection.execute("SELECT record_json FROM " + table + " WHERE id=?", (key,)).fetchone()
        if previous is None:
            if table == "receipts":
                connection.execute("INSERT INTO receipts VALUES(?,?,?,?)", (key, raw, value["receipt"]["receipt_id"], value["receipt"]["event_id"]))
            else:
                connection.execute("INSERT INTO " + table + " VALUES(?,?)", (key, raw))
        elif previous[0] != raw:
            if table in ("receipts", "outbox"):
                raise StoreConflict("Permanent fixture record cannot be replaced")
            connection.execute("UPDATE " + table + " SET record_json=? WHERE id=?", (raw, key))

    def _append(self, connection, state, kind, payload, now):
        if state["count"] >= MAX_EVENTS:
            raise StoreConflict("Fixture event history capacity reached")
        body = {"schema": "mra-fixture-registry-history/v1", "store_id": self.store_id,
            "sequence": state["count"] + 1, "previous_sha256": state["head"], "occurred_at": now,
            "kind": kind, "payload": payload}
        raw = canonical_bytes(body)
        event_hash = digest(body)
        self._apply(state, body, event_hash)
        connection.execute("INSERT INTO events VALUES(?,?,?)", (state["count"], event_hash, raw.decode("ascii")))
        for table in ("accounts", "cases", "receipts", "outbox") + (("deliveries",) if state["version"] == 2 else ()):
            for key, value in state[table].items():
                self._write_record(connection, table, key, value)
        for key, value in (("schema_version", state["version"]), ("broker_epoch", state["epoch"]),
                           ("broker_id", state["broker_id"] or ""), ("event_count", state["count"]), ("head_sha256", state["head"])):
            connection.execute("UPDATE meta SET value=? WHERE key=?", (str(value), key))

    def _validate(self, connection, *, expected_version=None):
        try:
            version = self.schema_version if expected_version is None else expected_version
            schema = connection.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
            expected = _SCHEMA + ((_DELIVERY_SCHEMA,) if version == 2 else ())
            if (len(schema) != len(expected) or any(row["type"] != "table" for row in schema)
                    or {row["sql"] for row in schema} != set(expected)):
                _unavailable()
            check = connection.execute("PRAGMA quick_check").fetchall()
            if (connection.execute("PRAGMA user_version").fetchone()[0] != version
                    or connection.execute("PRAGMA page_size").fetchone()[0] != 4096
                    or connection.execute("PRAGMA page_count").fetchone()[0] > 4096
                    or len(check) != 1 or check[0][0] != "ok"):
                _unavailable()
            metadata = dict(connection.execute("SELECT key,value FROM meta LIMIT 8").fetchall())
            if (set(metadata) != _META or metadata["store_id"] != self.store_id
                    or metadata["schema_version"] != str(version)):
                _unavailable()
            last_clock = integer(int(metadata["last_clock"]))
            count = integer(int(metadata["event_count"]), 1, MAX_EVENTS)
            epoch = integer(int(metadata["broker_epoch"]))
            if any(str(value) != metadata[key] for key, value in (("last_clock", last_clock), ("event_count", count), ("broker_epoch", epoch))):
                _unavailable()
            state = _blank()
            events = connection.execute("SELECT * FROM events ORDER BY sequence LIMIT ?", (MAX_EVENTS + 1,)).fetchall()
            if len(events) != count:
                _unavailable()
            for row in events:
                raw = row["event_json"].encode("ascii")
                body = _decode(raw)
                if digest(body) != row["event_sha256"] or body["sequence"] != row["sequence"]:
                    _unavailable()
                self._apply(state, body, row["event_sha256"])
            if (state["version"] != version or state["clock"] > last_clock or state["epoch"] != epoch
                    or state["head"] != metadata["head_sha256"] or (state["broker_id"] or "") != metadata["broker_id"]):
                _unavailable()
            tables = (("accounts", MAX_ACCOUNTS), ("cases", MAX_CASES), ("receipts", MAX_RECEIPTS), ("outbox", MAX_RECEIPTS))
            if version == 2:
                tables += (("deliveries", MAX_RECEIPTS),)
            for table, bound in tables:
                rows = connection.execute("SELECT * FROM " + table + " LIMIT ?", (bound + 1,)).fetchall()
                if len(rows) != len(state[table]) or len(rows) > bound:
                    _unavailable()
                for row in rows:
                    value = _decode(row["record_json"].encode("ascii"))
                    if row["id"] not in state[table] or canonical_bytes(value) != canonical_bytes(state[table][row["id"]]):
                        _unavailable()
                    if table == "receipts" and (row["receipt_id"] != value["receipt"]["receipt_id"] or row["event_id"] != value["receipt"]["event_id"]):
                        _unavailable()
            return state
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError, RecursionError):
            raise StoreUnavailable("Fixture registry state rejected") from None

    @staticmethod
    def _clock(connection, guard):
        now = integer(guard())
        prior = int(connection.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
        if now < prior:
            raise StoreUnavailable("Fixture registry clock moved backwards")
        connection.execute("UPDATE meta SET value=? WHERE key='last_clock'", (str(now),))
        return now

    @contextmanager
    def _transaction(self, guard, broker=None):
        if not callable(guard):
            raise StoreError("A trusted current authorization and time guard is required")
        broker = None if broker is None else _broker(broker)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                state = self._validate(connection)
                if broker is not None:
                    self._require_broker(state, broker)
                now = self._clock(connection, guard)
                deadlines = []
                yield connection, state, now, deadlines
                self._paths()
                current = self._validate(connection, expected_version=state["version"])
                if (current["count"], current["head"]) != (state["count"], state["head"]):
                    raise StoreConflict("Fixture history changed before commit")
                if broker is not None:
                    self._require_broker(current, broker)
                # No full replay after this guard: it must observe expiry after
                # the expensive final state validation, immediately pre-commit.
                final = self._clock(connection, guard)
                if any(final >= deadline for deadline in deadlines):
                    raise StoreConflict("Fixture operation expired before commit")
                self._paths()
                connection.commit()
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def inspect(self, *, guard):
        """Trusted bootstrap/status observation; opening does not activate a broker."""
        with self._transaction(guard) as (_, state, _, _):
            acknowledged = sum(row["acknowledgment"] is not None for row in state["deliveries"].values())
            result = {"store_id": self.store_id, "schema_version": state["version"], "broker_epoch": state["epoch"],
                "broker_id": state["broker_id"], "event_sequence": state["count"], "event_head_sha256": state["head"],
                "account_count": len(state["accounts"]), "case_count": len(state["cases"]), "receipt_count": len(state["receipts"]),
                "outbox_pending": len(state["outbox"]) - acknowledged, "outbox_acknowledged": acknowledged, **FLAGS}
        return _owned(result)

    def activate_broker(self, broker_id, *, expected_epoch, guard):
        broker_id = hex_id(broker_id)
        integer(expected_epoch)
        with self._transaction(guard) as (connection, state, now, _):
            self._append(connection, state, "broker", {"broker_id": broker_id, "expected_epoch": expected_epoch}, now)
            result = {"store_id": self.store_id, "broker_id": broker_id, "epoch": state["epoch"]}
        return result

    def account(self, agency_id, project_id, *, broker, guard):
        account_id(agency_id, project_id)
        with self._transaction(guard, broker) as (_, state, _, _):
            record = self._account(state, agency_id, project_id)
            result = {"store_id": self.store_id, **record,
                      "remaining_units": ACCOUNT_CAPACITY - record["total_engineering_charge_units"], **FLAGS}
        return _owned(result)

    def case(self, agency_id, project_id, case_id, *, broker, guard):
        _case_key(agency_id, project_id, case_id)
        with self._transaction(guard, broker) as (_, state, _, _):
            result = {"store_id": self.store_id, **self._case(state, agency_id, project_id, case_id), **FLAGS}
        return _owned(result)

    def commit(self, request, commit_context, *, broker, guard):
        request, context, broker = validate_request(request), validate_commit_context(commit_context), _broker(broker)
        if (request["store_id"] != self.store_id or context["actor_person_id"] != request["actor_person_id"]
                or context["broker_id"] != broker["broker_id"] or context["broker_epoch"] != broker["epoch"]):
            raise StoreConflict("Fixture intent and current commit context differ")
        with self._transaction(guard, broker) as (connection, state, now, deadlines):
            self._account(state, request["agency_id"], request["project_id"])
            previous = state["receipts"].get(_request_key(request))
            if previous is not None:
                if previous["receipt"]["request_sha256"] != digest(request):
                    raise StoreConflict("Permanent request ID cannot name changed intent")
                # Current authorization is checked again before returning an
                # unchanged historical receipt. Neither head nor charge moves.
                result = previous
            else:
                account = self._account(state, request["agency_id"], request["project_id"])
                case = self._case(state, request["agency_id"], request["project_id"], request["case_id"])
                if (account["sequence"] != request["expected_account_sequence"]
                        or account["head_sha256"] != request["expected_account_head_sha256"]
                        or case["sequence"] != request["expected_case_sequence"]
                        or case["head_sha256"] != request["expected_case_head_sha256"]
                        or account["total_engineering_charge_units"] >= ACCOUNT_CAPACITY):
                    raise StoreConflict("Fixture heads changed or engineering capacity is exhausted")
                receipt = create_receipt(request, context, receipt_id=secrets.token_hex(16),
                                         event_id=secrets.token_hex(16), committed_at=now)
                self._append(connection, state, "committed", {"request": request, "receipt": receipt}, now)
                deadlines.append(request["object_reference"]["retention_until"])
                result = receipt
        return _owned(result)

    def get_receipt(self, agency_id, project_id, request_id, *, broker, guard):
        key = _request_key({"account_id": account_id(agency_id, project_id), "request_id": hex_id(request_id)})
        with self._transaction(guard, broker) as (_, state, _, _):
            self._account(state, agency_id, project_id)
            result = state["receipts"].get(key)
            if result is None:
                raise StoreConflict("Fixture request is unknown")
        return _owned(result)

    def claim_outbox(self, agency_id, project_id, case_id, *, owner_sha256, broker, lease_seconds=30, guard):
        """Claim oldest available scoped metadata; None does not mean all acked."""
        scope = account_id(agency_id, project_id)
        identifier(case_id)
        owner_sha256, broker = validate_digest(owner_sha256), _broker(broker)
        integer(lease_seconds, 1, 60)
        with self._transaction(guard, broker) as (connection, state, now, deadlines):
            if state["version"] != 2:
                raise StoreConflict("Outbox delivery requires registry schema 2")
            self._account(state, agency_id, project_id)
            result = None
            # Dict insertion order is reconstructed from the immutable event
            # log, so pending selection is by original commit order.
            for event_id, event in state["outbox"].items():
                if event["account_id"] != scope or event["case_id"] != case_id:
                    continue
                delivery = state["deliveries"][event_id]
                if delivery["acknowledgment"] is not None:
                    continue
                previous = delivery["lease"]
                if previous is not None and previous["broker_epoch"] == state["epoch"] and now < previous["expires_at"]:
                    continue
                if delivery["generation"] >= MAX_DELIVERY_ATTEMPTS:
                    raise StoreConflict("Pending outbox event exhausted its bounded delivery attempts")
                lease = _lease({"store_id": self.store_id, "event_id": event_id, "account_id": scope,
                    "case_id": case_id, "owner_sha256": owner_sha256, "lease_id": secrets.token_hex(16),
                    "generation": delivery["generation"] + 1, "broker_id": broker["broker_id"],
                    "broker_epoch": broker["epoch"], "claimed_at": now, "expires_at": now + lease_seconds})
                self._append(connection, state, "claimed", {"lease": lease}, now)
                deadlines.append(lease["expires_at"])
                result = {"lease": lease, "event": event}
                break
        return None if result is None else _owned(result)

    def acknowledge(self, lease, *, owner_sha256, broker, guard):
        lease, broker = _lease(lease), _broker(broker)
        if (validate_digest(owner_sha256) != lease["owner_sha256"] or lease["store_id"] != self.store_id
                or lease["broker_id"] != broker["broker_id"] or lease["broker_epoch"] != broker["epoch"]):
            raise StoreConflict("Outbox owner or broker differs")
        with self._transaction(guard, broker) as (connection, state, now, deadlines):
            if state["version"] != 2:
                raise StoreConflict("Outbox delivery requires registry schema 2")
            delivery = state["deliveries"].get(lease["event_id"])
            if delivery is None or delivery["lease"] != lease:
                raise StoreConflict("Outbox lease is not current")
            if delivery["acknowledgment"] is not None:
                result = delivery["acknowledgment"]
            else:
                result = self._ack(lease, now)
                self._append(connection, state, "acknowledged", {"lease": lease, "acknowledgment": result}, now)
                deadlines.append(lease["expires_at"])
        return _owned(result)
