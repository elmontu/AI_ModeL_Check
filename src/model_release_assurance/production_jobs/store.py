"""Durable local fixture jobs on SQLite, with leases and spent-input tombstones.

One current identity/storage broker owns authorization. No cloud queue,
distributed revocation, hostile-admin protection or rollback witness is claimed.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import uuid
from .contracts import (FLAGS, JobConflict, JobError, JobUnavailable, canonical, digest, hex_id,
                        identifier, integer, sha256, validate_descriptor, validate_lease, validate_result)

MAX_JOBS, MAX_GRANTS, MAX_EVENTS = 256, 1024, 4096
MAX_DATABASE_BYTES = 16 * 1024 * 1024
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    """CREATE TABLE jobs (id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, descriptor TEXT NOT NULL,
       digest TEXT NOT NULL, submitter TEXT NOT NULL, state TEXT NOT NULL, fence INTEGER NOT NULL,
       created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, result TEXT) STRICT""",
    """CREATE TABLE attempts (job_id TEXT NOT NULL REFERENCES jobs(id), fence INTEGER NOT NULL,
       attempt_id TEXT NOT NULL UNIQUE, holder TEXT NOT NULL, authority_revision INTEGER NOT NULL,
       broker_id TEXT NOT NULL, grant_id TEXT NOT NULL, started_at INTEGER NOT NULL,
       expires_at INTEGER NOT NULL, max_until INTEGER NOT NULL, state TEXT NOT NULL, reason TEXT,
       PRIMARY KEY(job_id,fence)) STRICT""",
    """CREATE TABLE grants (id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), broker_id TEXT NOT NULL,
       holder TEXT NOT NULL, authority_revision INTEGER NOT NULL, storage_grant_id TEXT NOT NULL UNIQUE,
       expires_at INTEGER NOT NULL, state TEXT NOT NULL, fence INTEGER) STRICT""",
    """CREATE TABLE events (seq INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
       event TEXT NOT NULL, fence INTEGER NOT NULL, at INTEGER NOT NULL) STRICT""",
)
_NAMES = {"meta", "jobs", "attempts", "grants", "events"}

def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

def _directories(path):
    if ".." in path.parts or str(path).startswith(("//", "\\\\")):
        raise JobUnavailable("A local ordinary job directory is required")
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            raise JobUnavailable("Job directory is unavailable")

def _identity(info):
    return info.st_dev, info.st_ino

class JobStore:
    """Trusted local custody API; a broker guard supplies current authorization and time."""

    def __init__(self, root, store_id):
        self.root = Path(root).absolute()
        self.path = self.root / "jobs.sqlite"
        self.store_id = hex_id(store_id)
        _directories(self.root)
        self._root_identity = _identity(self.root.stat())
        self._db_identity = _identity(self.path.stat())
        self._paths()
        with self._connect() as connection:
            schema = connection.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if ({row["name"] for row in schema} != _NAMES or any(row["type"] != "table" for row in schema)
                    or {row["sql"] for row in schema} != set(_SCHEMA)):
                raise JobUnavailable("Unknown job schema")
            metadata = dict(connection.execute("SELECT key,value FROM meta").fetchall())
            if (set(metadata) != {"schema", "store_id", "broker_id", "broker_history", "last_clock"}
                    or metadata["schema"] != "mra-fixture-jobs/v1" or metadata["store_id"] != self.store_id):
                raise JobUnavailable("Job store identity is unavailable")
            integer(int(metadata["last_clock"]))
            history = json.loads(metadata["broker_history"])
            if type(history) is not list or len(history) > 256 or len(set(history)) != len(history):
                raise JobUnavailable("Invalid broker history")
            for broker in history:
                hex_id(broker)
            if metadata["broker_id"] and metadata["broker_id"] not in history:
                raise JobUnavailable("Current broker is absent from history")
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise JobUnavailable("Job database integrity check failed")

    @classmethod
    def create(cls, root):
        root = Path(root).absolute()
        _directories(root.parent)
        root.mkdir(exist_ok=False)
        _directories(root)
        path = root / "jobs.sqlite"
        with path.open("xb"):
            pass
        store_id = uuid.uuid4().hex
        connection = sqlite3.connect(path, timeout=1.0, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA max_page_count=4096")
            connection.execute("BEGIN IMMEDIATE")
            for sql in _SCHEMA:
                connection.execute(sql)
            connection.executemany("INSERT INTO meta VALUES(?,?)", (
                ("schema", "mra-fixture-jobs/v1"), ("store_id", store_id),
                ("broker_id", ""), ("broker_history", "[]"), ("last_clock", "0")))
            connection.commit()
        finally:
            connection.close()
        return cls(root, store_id)

    @classmethod
    def open(cls, root, expected_store_id):
        try:
            return cls(root, expected_store_id)
        except (OSError, sqlite3.Error, ValueError, TypeError):
            raise JobUnavailable("Existing job store could not be opened") from None

    def _paths(self):
        try:
            self._checked_paths()
        except OSError:
            raise JobUnavailable("Job filesystem is unavailable") from None

    def _checked_paths(self):
        _directories(self.root)
        if _identity(self.root.stat()) != self._root_identity:
            raise JobUnavailable("Job directory identity changed")
        info = self.path.lstat()
        if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 1 <= info.st_size <= MAX_DATABASE_BYTES or _identity(info) != self._db_identity):
            raise JobUnavailable("Job database is unavailable")
        for name in ("jobs.sqlite-journal", "jobs.sqlite-wal", "jobs.sqlite-shm"):
            path = self.root / name
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if _unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise JobUnavailable("Job database sidecar is unsafe")
            if name != "jobs.sqlite-journal":
                raise JobUnavailable("Unexpected job database journal mode")

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self._paths()
            connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=1.0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.enable_load_extension(False)
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA max_page_count=4096")
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise JobUnavailable("Unexpected job journal mode")
            yield connection
        except sqlite3.Error:
            raise JobUnavailable("Job database operation unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _clock(connection, guard):
        if not callable(guard):
            raise ValueError("A current authorization clock guard is required")
        now = integer(guard())
        prior = int(connection.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
        if now < prior:
            raise JobUnavailable("Job clock moved backwards")
        connection.execute("UPDATE meta SET value=? WHERE key='last_clock'", (str(now),))
        return now

    @contextmanager
    def _transaction(self, broker_id, guard, *, activation=False):
        hex_id(broker_id)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("SELECT value FROM meta WHERE key='store_id'").fetchone()[0] != self.store_id:
                    raise JobUnavailable("Job store identity changed")
                if not activation and connection.execute("SELECT value FROM meta WHERE key='broker_id'").fetchone()[0] != broker_id:
                    raise JobUnavailable("Job broker is no longer current")
                now, deadlines = self._clock(connection, guard), []
                yield connection, now, deadlines
                final = self._clock(connection, guard)
                if any(final >= deadline for deadline in deadlines):
                    raise JobConflict("Job operation expired before commit")
                self._paths()
                connection.commit()
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    @staticmethod
    def _event(connection, job_id, event, fence, now):
        if connection.execute("SELECT count(*) FROM events").fetchone()[0] >= MAX_EVENTS:
            raise JobConflict("Fixture event capacity reached")
        connection.execute("INSERT INTO events(job_id,event,fence,at) VALUES(?,?,?,?)", (job_id, event, fence, now))

    @staticmethod
    def _row(connection, job_id):
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (hex_id(job_id),)).fetchone()
        if row is None:
            raise JobConflict("Unknown fixture job")
        descriptor = validate_descriptor(json.loads(row["descriptor"]))
        if sha256(descriptor) != row["digest"]:
            raise JobUnavailable("Job descriptor integrity mismatch")
        return row, descriptor

    def _snapshot(self, connection, job_id):
        row, descriptor = self._row(connection, job_id)
        attempts = [dict(item) for item in connection.execute(
            "SELECT * FROM attempts WHERE job_id=? ORDER BY fence", (job_id,))]
        return {**FLAGS, "id": row["id"], "job_id": row["id"], "descriptor": descriptor,
                "digest": row["digest"], "submitter": row["submitter"], "state": row["state"],
                "fence": row["fence"], "created_at": row["created_at"], "updated_at": row["updated_at"],
                "result": json.loads(row["result"]) if row["result"] is not None else None, "attempts": attempts}

    def activate_broker(self, broker_id, guard):
        with self._transaction(broker_id, guard, activation=True) as (connection, now, deadlines):
            history = json.loads(connection.execute("SELECT value FROM meta WHERE key='broker_history'").fetchone()[0])
            if broker_id in history or len(history) >= 256:
                raise JobConflict("Broker identifier is retired or capacity is exhausted")
            for row in connection.execute("SELECT * FROM jobs WHERE state='running'").fetchall():
                descriptor = json.loads(row["descriptor"])
                state = "queued" if row["fence"] < descriptor["max_attempts"] else "failed"
                connection.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=?", (state, now, row["id"]))
                connection.execute("UPDATE attempts SET state='abandoned',reason='broker_restarted' WHERE job_id=? AND state='running'", (row["id"],))
                self._event(connection, row["id"], "broker_restarted", row["fence"], now)
            connection.execute("UPDATE grants SET state='revoked' WHERE state IN ('authorized','leased')")
            connection.execute("UPDATE meta SET value=? WHERE key='broker_id'", (broker_id,))
            connection.execute("UPDATE meta SET value=? WHERE key='broker_history'", (json.dumps([*history, broker_id]),))
        return {**FLAGS, "store_id": self.store_id, "broker_id": broker_id}

    def submit(self, descriptor, request_id, submitter, broker_id, guard):
        descriptor = validate_descriptor(descriptor)
        identifier(request_id); identifier(submitter)
        if len(request_id) > 64:
            raise ValueError("Request identifier exceeds its bound")
        descriptor_digest = sha256(descriptor)
        request_key = sha256([broker_id, descriptor["agency_id"], descriptor["project_id"], descriptor["case_id"], submitter, request_id])
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            prior = connection.execute("SELECT id,digest FROM jobs WHERE request_key=?", (request_key,)).fetchone()
            if prior:
                if prior["digest"] != descriptor_digest:
                    raise JobConflict("Request identifier is bound to a different descriptor")
                result = self._snapshot(connection, prior["id"])
            else:
                if connection.execute("SELECT count(*) FROM jobs").fetchone()[0] >= MAX_JOBS:
                    raise JobConflict("Fixture job capacity reached")
                job_id = uuid.uuid4().hex
                connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,'queued',0,?,?,NULL)",
                    (job_id, request_key, canonical(descriptor).decode(), descriptor_digest, submitter, now, now))
                self._event(connection, job_id, "submitted", 0, now)
                result = self._snapshot(connection, job_id)
        return result

    def get(self, job_id, broker_id, guard):
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            result = self._snapshot(connection, job_id)
        return result

    def authorize_input(self, job_id, holder, authority_revision, storage_grant_id, expires_at, broker_id, guard):
        digest(holder); integer(authority_revision, 1); hex_id(storage_grant_id); integer(expires_at)
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, _ = self._row(connection, job_id)
            if row["state"] in {"succeeded", "cancelled", "failed"}:
                raise JobConflict("Terminal job cannot receive another input grant")
            if row["state"] == "running":
                active = connection.execute("SELECT expires_at FROM attempts WHERE job_id=? AND fence=?",
                                            (job_id, row["fence"])).fetchone()
                if active is None or now < active["expires_at"]:
                    raise JobConflict("A current attempt cannot replace its input authorization")
            if not now < expires_at <= now + 60:
                raise JobConflict("Input authorization has no bounded current lifetime")
            if connection.execute("SELECT count(*) FROM grants").fetchone()[0] >= MAX_GRANTS:
                raise JobConflict("Fixture grant capacity reached")
            grant_id = uuid.uuid4().hex
            connection.execute("INSERT INTO grants VALUES(?,?,?,?,?,?,?,'authorized',NULL)",
                (grant_id, job_id, broker_id, holder, authority_revision, storage_grant_id, expires_at))
            self._event(connection, job_id, "input_authorized", row["fence"], now)
            deadlines.append(expires_at)
        return {**FLAGS, "id": grant_id, "grant_id": grant_id, "job_id": job_id, "expires_at": expires_at}

    @staticmethod
    def _lease(attempt):
        return {key: attempt[key] for key in ("job_id", "fence", "attempt_id", "holder",
                "authority_revision", "broker_id", "grant_id", "expires_at")}

    def _current(self, connection, lease, broker_id, now):
        lease = validate_lease(lease)
        if lease["broker_id"] != broker_id:
            raise JobConflict("Lease broker mismatch")
        row, descriptor = self._row(connection, lease["job_id"])
        attempt = connection.execute("SELECT * FROM attempts WHERE job_id=? AND fence=?",
                                     (lease["job_id"], lease["fence"])).fetchone()
        if (row["state"] != "running" or row["fence"] != lease["fence"] or attempt is None
                or attempt["state"] != "running" or self._lease(attempt) != lease or now >= attempt["expires_at"]):
            raise JobConflict("Lease is expired, replaced or otherwise ineligible")
        return row, descriptor, attempt

    def claim(self, job_id, grant_id, holder, authority_revision, credential_expires, broker_id, guard):
        hex_id(grant_id); digest(holder); integer(authority_revision, 1); integer(credential_expires)
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor = self._row(connection, job_id)
            if row["state"] in {"succeeded", "cancelled", "failed"}:
                return None
            if row["state"] == "running":
                previous = connection.execute("SELECT * FROM attempts WHERE job_id=? AND fence=?", (job_id, row["fence"])).fetchone()
                if now < previous["expires_at"]:
                    raise JobConflict("Job already has a current lease")
                connection.execute("UPDATE attempts SET state='expired',reason='lease_expired' WHERE job_id=? AND fence=?", (job_id, row["fence"]))
                connection.execute("UPDATE grants SET state='revoked' WHERE job_id=? AND fence=? AND state='leased'", (job_id, row["fence"]))
                self._event(connection, job_id, "lease_expired", row["fence"], now)
            if row["fence"] >= descriptor["max_attempts"]:
                connection.execute("UPDATE jobs SET state='failed',updated_at=? WHERE id=?", (now, job_id))
                return None
            grant = connection.execute("SELECT * FROM grants WHERE id=?", (grant_id,)).fetchone()
            if (grant is None or grant["job_id"] != job_id or grant["broker_id"] != broker_id or grant["holder"] != holder
                    or grant["authority_revision"] != authority_revision or grant["state"] != "authorized" or now >= grant["expires_at"]):
                raise JobConflict("Input grant cannot serve this exact worker attempt")
            expires = min(now + descriptor["lease_seconds"], credential_expires, grant["expires_at"])
            if expires <= now:
                raise JobConflict("No remaining lease lifetime")
            fence, attempt_id = row["fence"] + 1, uuid.uuid4().hex
            connection.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,'running',NULL)",
                (job_id, fence, attempt_id, holder, authority_revision, broker_id, grant_id, now, expires, min(now + 60, credential_expires)))
            connection.execute("UPDATE jobs SET state='running',fence=?,updated_at=? WHERE id=?", (fence, now, job_id))
            connection.execute("UPDATE grants SET state='leased',fence=? WHERE id=?", (fence, grant_id))
            self._event(connection, job_id, "claimed", fence, now)
            result = self._lease(connection.execute("SELECT * FROM attempts WHERE job_id=? AND fence=?", (job_id, fence)).fetchone())
            deadlines.append(expires)
        return result

    def renew(self, lease, credential_expires, broker_id, guard):
        lease = validate_lease(lease); integer(credential_expires)
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor, attempt = self._current(connection, lease, broker_id, now)
            expires = min(now + descriptor["lease_seconds"], credential_expires, attempt["max_until"])
            if expires < attempt["expires_at"]:
                raise JobConflict("Renewal cannot weaken an existing lease")
            connection.execute("UPDATE attempts SET expires_at=? WHERE job_id=? AND fence=?", (expires, lease["job_id"], lease["fence"]))
            self._event(connection, lease["job_id"], "renewed", lease["fence"], now)
            result = {**lease, "expires_at": expires}
            deadlines.append(expires)
        return result

    def consume_input(self, lease, broker_id, guard):
        lease = validate_lease(lease)
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor, attempt = self._current(connection, lease, broker_id, now)
            grant = connection.execute("SELECT * FROM grants WHERE id=?", (lease["grant_id"],)).fetchone()
            if (grant is None or grant["state"] != "leased" or grant["fence"] != lease["fence"]
                    or grant["job_id"] != lease["job_id"] or grant["holder"] != lease["holder"]
                    or grant["broker_id"] != broker_id or grant["authority_revision"] != lease["authority_revision"]
                    or now >= grant["expires_at"]):
                raise JobConflict("Input grant is spent, revoked, expired or mismatched")
            connection.execute("UPDATE grants SET state='consumed' WHERE id=?", (lease["grant_id"],))
            self._event(connection, lease["job_id"], "input_consumed", lease["fence"], now)
            result = {"storage_grant_id": grant["storage_grant_id"], "reference": descriptor["object_reference"]}
            deadlines.extend((attempt["expires_at"], grant["expires_at"]))
        return result

    def with_current_lease(self, lease, broker_id, guard, operation):
        """Read exact public bytes under a live lease; callback is trusted bounded broker code.

        The previous input-consumption transaction has already committed. A
        failure here never restores that grant or accepts a result.
        """
        lease = validate_lease(lease)
        if not callable(operation):
            raise ValueError("A trusted bounded input operation is required")
        # Reserve the physical-read invocation durably before its side effect.
        # Losing the process after this commit never refunds a read invocation.
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor, attempt = self._current(connection, lease, broker_id, now)
            grant = connection.execute("SELECT * FROM grants WHERE id=?", (lease["grant_id"],)).fetchone()
            if grant is None or grant["state"] != "consumed":
                raise JobConflict("Input read was already invoked or not reserved")
            connection.execute("UPDATE grants SET state='read_started' WHERE id=?", (lease["grant_id"],))
            self._event(connection, lease["job_id"], "input_read_started", lease["fence"], now)
            deadlines.extend((attempt["expires_at"], grant["expires_at"]))
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor, attempt = self._current(connection, lease, broker_id, now)
            grant = connection.execute("SELECT * FROM grants WHERE id=?", (lease["grant_id"],)).fetchone()
            if grant is None or grant["state"] != "read_started" or now >= grant["expires_at"]:
                raise JobConflict("Input read invocation is unavailable")
            content = operation()
            reference = descriptor["object_reference"]
            if (type(content) is not bytes or not 1 <= len(content) <= 65536
                    or len(content) != reference["size_bytes"]
                    or hashlib.sha256(content).hexdigest() != reference["sha256"]):
                raise JobConflict("Input operation returned bytes outside the exact job reference")
            connection.execute("UPDATE grants SET state='delivered' WHERE id=?", (lease["grant_id"],))
            self._event(connection, lease["job_id"], "input_delivered", lease["fence"], now)
            deadlines.extend((attempt["expires_at"], grant["expires_at"]))
        return content

    def complete(self, lease, result, broker_id, guard):
        lease = validate_lease(lease)
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor, attempt = self._current(connection, lease, broker_id, now)
            checked = validate_result(result, descriptor, lease)
            grant = connection.execute("SELECT state FROM grants WHERE id=?", (lease["grant_id"],)).fetchone()
            if grant is None or grant["state"] != "delivered":
                raise JobConflict("Successful output requires an exact delivered input grant")
            connection.execute("UPDATE jobs SET state='succeeded',result=?,updated_at=? WHERE id=?",
                               (canonical(checked).decode(), now, lease["job_id"]))
            connection.execute("UPDATE attempts SET state='succeeded' WHERE job_id=? AND fence=?", (lease["job_id"], lease["fence"]))
            connection.execute("UPDATE grants SET state='revoked' WHERE job_id=? AND state IN ('authorized','leased')", (lease["job_id"],))
            self._event(connection, lease["job_id"], "succeeded", lease["fence"], now)
            deadlines.append(attempt["expires_at"])
            snapshot = self._snapshot(connection, lease["job_id"])
        return snapshot

    def fail(self, lease, reason, broker_id, guard):
        lease = validate_lease(lease)
        if type(reason) is not str or reason not in {"failed", "timed_out", "cancelled", "output_limit", "cleanup_failed", "input_unavailable"}:
            raise ValueError("Unknown bounded worker failure")
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, descriptor, attempt = self._current(connection, lease, broker_id, now)
            state = "queued" if lease["fence"] < descriptor["max_attempts"] else "failed"
            connection.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=?", (state, now, lease["job_id"]))
            connection.execute("UPDATE attempts SET state='failed',reason=? WHERE job_id=? AND fence=?", (reason, lease["job_id"], lease["fence"]))
            connection.execute("UPDATE grants SET state='revoked' WHERE id=? AND state='leased'", (lease["grant_id"],))
            self._event(connection, lease["job_id"], reason, lease["fence"], now)
            deadlines.append(attempt["expires_at"])
            snapshot = self._snapshot(connection, lease["job_id"])
        return snapshot

    def cancel(self, job_id, broker_id, guard):
        with self._transaction(broker_id, guard) as (connection, now, deadlines):
            row, _ = self._row(connection, job_id)
            if row["state"] == "succeeded":
                raise JobConflict("A completed result cannot be cancelled retroactively")
            if row["state"] != "cancelled":
                connection.execute("UPDATE jobs SET state='cancelled',updated_at=? WHERE id=?", (now, job_id))
                connection.execute("UPDATE attempts SET state='cancelled',reason='operator_cancelled' WHERE job_id=? AND state='running'", (job_id,))
                connection.execute("UPDATE grants SET state='revoked' WHERE job_id=? AND state IN ('authorized','leased')", (job_id,))
                self._event(connection, job_id, "cancelled", row["fence"], now)
            snapshot = self._snapshot(connection, job_id)
        return snapshot
