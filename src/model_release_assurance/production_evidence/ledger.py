"""Durable one-use challenges for authenticated local execution evidence.

The trusted caller supplies current authorization and time under its own trust
lock. SQLite arbitrates independent callers; consumed and expired challenges
are never deleted. This is not a whole-database rollback witness or protection
against a privileged filesystem administrator.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import secrets
import sqlite3
import stat

from .contracts import EvidenceError, MAX_INTEGER, canonical_bytes, validate_challenge, validate_digest

MAX_CHALLENGES = 1024
MAX_DATABASE_BYTES = 16 * 1024 * 1024
_DATABASE_NAME = "replay.sqlite"
_SCHEMA_ID = "mra-evidence-ledger/v1"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    """CREATE TABLE challenges (nonce TEXT PRIMARY KEY, context_sha256 TEXT NOT NULL,
       execution_sha256 TEXT NOT NULL UNIQUE, issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
       envelope_sha256 TEXT, consumed_at INTEGER,
       CHECK ((envelope_sha256 IS NULL AND consumed_at IS NULL) OR
              (envelope_sha256 IS NOT NULL AND consumed_at IS NOT NULL))) STRICT""",
)
_ID = re.compile(r"[0-9a-f]{32}\Z")


class LedgerUnavailable(RuntimeError):
    """The existing ledger cannot safely establish its state or current time."""


class LedgerConflict(EvidenceError):
    """The challenge is unknown, spent, expired, or conflicts with an execution."""


def _unavailable():
    raise LedgerUnavailable("Evidence ledger unavailable")


def _integer(value):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise EvidenceError("Evidence ledger time rejected")
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


class ReplayLedger:
    """Explicitly created local ledger; opening never repairs or resets state."""

    def __init__(self, root, expected_ledger_id):
        if type(expected_ledger_id) is not str or not _ID.fullmatch(expected_ledger_id):
            _unavailable()
        self._ledger_id = expected_ledger_id
        try:
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE_NAME
            _directories(self._root)
            self._root_identity = _identity(self._root.lstat())
            self._db_identity = _identity(self._path.lstat())
        except (OSError, TypeError, ValueError):
            raise LedgerUnavailable("Evidence ledger unavailable") from None
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
    def ledger_id(self):
        return self._ledger_id

    @classmethod
    def create(cls, root):
        """Create a new directory and ledger, refusing any existing directory."""
        try:
            root = Path(root).absolute()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            _directories(root)
            path = root / _DATABASE_NAME
            with path.open("xb"):
                pass
            ledger_id = secrets.token_hex(16)
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
                    ("schema", _SCHEMA_ID), ("ledger_id", ledger_id), ("last_clock", "0")))
                connection.commit()
            finally:
                connection.close()
            return cls(root, ledger_id)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            raise LedgerUnavailable("Evidence ledger creation unavailable") from None

    @classmethod
    def open(cls, root, expected_ledger_id):
        return cls(root, expected_ledger_id)

    def _paths(self):
        try:
            _directories(self._root)
            if _identity(self._root.lstat()) != self._root_identity:
                _unavailable()
            info = self._path.lstat()
            if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or _identity(info) != self._db_identity
                    or not 1 <= info.st_size <= MAX_DATABASE_BYTES):
                _unavailable()
            for suffix in ("-journal", "-wal", "-shm"):
                try:
                    info = (self._root / (_DATABASE_NAME + suffix)).lstat()
                except FileNotFoundError:
                    continue
                if (suffix != "-journal" or _unsafe(info) or not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1 or info.st_size > MAX_DATABASE_BYTES + 65536):
                    _unavailable()
        except OSError:
            raise LedgerUnavailable("Evidence ledger filesystem unavailable") from None

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self._paths()
            # URI mode=rw never recreates a missing database. as_uri also quotes
            # literal spaces, percent signs and hash characters in local paths.
            connection = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True,
                                         timeout=1.0, isolation_level=None)
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
            raise LedgerUnavailable("Evidence ledger database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def _challenge(self, row):
        return validate_challenge({"schema": "mra-evidence-challenge/v1", "ledger_id": self.ledger_id,
            "nonce": row["nonce"], "context_sha256": row["context_sha256"],
            "execution_sha256": row["execution_sha256"], "issued_at": row["issued_at"],
            "expires_at": row["expires_at"]})

    def _validate(self, connection):
        """Validate bounded persistent state on every operation, not just open."""
        try:
            schema = connection.execute(
                "SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if (len(schema) != 2 or {row["name"] for row in schema} != {"meta", "challenges"}
                    or any(row["type"] != "table" for row in schema)
                    or {row["sql"] for row in schema} != set(_SCHEMA)):
                _unavailable()
            if (connection.execute("PRAGMA page_size").fetchone()[0] != 4096
                    or connection.execute("PRAGMA page_count").fetchone()[0] > 4096
                    or connection.execute("PRAGMA quick_check").fetchall()[0][0] != "ok"):
                _unavailable()
            metadata = dict(connection.execute("SELECT key,value FROM meta").fetchall())
            if (set(metadata) != {"schema", "ledger_id", "last_clock"}
                    or metadata["schema"] != _SCHEMA_ID or metadata["ledger_id"] != self.ledger_id):
                _unavailable()
            last_clock = _integer(int(metadata["last_clock"]))
            if str(last_clock) != metadata["last_clock"]:
                _unavailable()
            rows = connection.execute("SELECT * FROM challenges LIMIT ?", (MAX_CHALLENGES + 1,)).fetchall()
            if len(rows) > MAX_CHALLENGES:
                _unavailable()
            nonces, executions = set(), set()
            for row in rows:
                challenge = self._challenge(row)
                if (challenge["nonce"] in nonces or challenge["execution_sha256"] in executions
                        or challenge["issued_at"] > last_clock):
                    _unavailable()
                nonces.add(challenge["nonce"])
                executions.add(challenge["execution_sha256"])
                if row["envelope_sha256"] is None:
                    if row["consumed_at"] is not None:
                        _unavailable()
                else:
                    validate_digest(row["envelope_sha256"])
                    consumed = _integer(row["consumed_at"])
                    if not challenge["issued_at"] <= consumed < challenge["expires_at"] or consumed > last_clock:
                        _unavailable()
        except (EvidenceError, ValueError, TypeError, KeyError, IndexError, OverflowError):
            raise LedgerUnavailable("Evidence ledger state rejected") from None

    @staticmethod
    def _clock(connection, guard):
        now = _integer(guard())
        previous = int(connection.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
        if now < previous:
            raise LedgerUnavailable("Evidence ledger clock moved backwards")
        connection.execute("UPDATE meta SET value=? WHERE key='last_clock'", (str(now),))
        return now

    @contextmanager
    def _transaction(self, guard):
        if not callable(guard):
            raise EvidenceError("A trusted current authorization guard is required")
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._validate(connection)
                now = self._clock(connection, guard)
                deadlines, finalizers = [], []
                yield connection, now, deadlines, finalizers
                self._paths()
                final = self._clock(connection, guard)
                if any(final >= deadline for deadline in deadlines):
                    raise LedgerConflict("Evidence challenge expired before commit")
                self._paths()
                for finalize in finalizers:
                    finalize(final)
                connection.commit()
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def issue(self, context_sha256, execution_sha256, *, ttl_seconds=300, guard):
        context_sha256, execution_sha256 = validate_digest(context_sha256), validate_digest(execution_sha256)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise EvidenceError("Evidence challenge lifetime rejected")
        with self._transaction(guard) as (connection, now, deadlines, _):
            if (connection.execute("SELECT 1 FROM challenges WHERE execution_sha256=?", (execution_sha256,)).fetchone()
                    or connection.execute("SELECT count(*) FROM challenges").fetchone()[0] >= MAX_CHALLENGES):
                raise LedgerConflict("Evidence execution is reserved or ledger capacity reached")
            challenge = validate_challenge({"schema": "mra-evidence-challenge/v1", "ledger_id": self.ledger_id,
                "nonce": secrets.token_hex(32), "context_sha256": context_sha256,
                "execution_sha256": execution_sha256, "issued_at": now, "expires_at": now + ttl_seconds})
            if connection.execute("SELECT 1 FROM challenges WHERE nonce=?", (challenge["nonce"],)).fetchone():
                raise LedgerConflict("Evidence nonce is already reserved")
            connection.execute("INSERT INTO challenges VALUES(?,?,?,?,?,NULL,NULL)",
                (challenge["nonce"], context_sha256, execution_sha256, now, challenge["expires_at"]))
            deadlines.append(challenge["expires_at"])
        return challenge

    def consume(self, challenge, envelope_sha256, *, guard):
        challenge, envelope_sha256 = validate_challenge(challenge), validate_digest(envelope_sha256)
        with self._transaction(guard) as (connection, now, deadlines, finalizers):
            row = connection.execute("SELECT * FROM challenges WHERE nonce=?", (challenge["nonce"],)).fetchone()
            if (row is None or canonical_bytes(self._challenge(row)) != canonical_bytes(challenge)
                    or row["envelope_sha256"] is not None
                    or not challenge["issued_at"] <= now < challenge["expires_at"]):
                raise LedgerConflict("Evidence challenge is unknown, spent or expired")
            receipt = {"schema": "mra-evidence-consumption/v1", "ledger_id": self.ledger_id,
                "nonce": challenge["nonce"], "context_sha256": challenge["context_sha256"],
                "execution_sha256": challenge["execution_sha256"], "envelope_sha256": envelope_sha256,
                "consumed_at": now}
            deadlines.append(challenge["expires_at"])
            def finalize(final):
                connection.execute("UPDATE challenges SET envelope_sha256=?,consumed_at=? WHERE nonce=?",
                                   (envelope_sha256, final, challenge["nonce"]))
                receipt["consumed_at"] = final
            finalizers.append(finalize)
        return receipt
