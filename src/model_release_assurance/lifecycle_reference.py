"""Experimental single-host lifecycle mechanics, not a production authorizer.

SQLite supplies transaction isolation and durability, subject to its documented
filesystem/hardware assumptions. Authority and gate attestations, wall clock,
artifact measurements and the independent checkpoint store are trusted inputs.
This module does not verify the paper's assessment, selection, governmental
obligations, signatures, complete disclosure scope, or distributed serving.
Receipts are local audit records, never bearer credentials to a model endpoint.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable


class LifecycleDenied(ValueError):
    """A failed check leaves the attempted transition unapplied."""


@dataclass(frozen=True)
class Checkpoint:
    registry_id: str
    sequence: int
    head: str


@dataclass(frozen=True)
class Receipt:
    checkpoint: Checkpoint
    operation: str
    release_id: str | None


@dataclass(frozen=True)
class Authority:
    authority_id: str
    epoch: int
    status: str
    valid_until: int


@dataclass(frozen=True)
class CommitRequest:
    release_id: str
    nonce: str
    artifact_sha256: str
    interface_sha256: str
    context_sha256: str
    selection_sha256: str
    authority_id: str
    authority_epoch: int
    expires_at: int
    evidence_expires_at: int
    policy_expires_at: int
    max_accesses: int
    expected_disclosed_release_ids: tuple[str, ...]
    # These attestations are premises, not independently verified conclusions.
    assessment_disposition: str
    obligations_status: str
    joint_portfolio_status: str
    commit_budget_cost: int = 0
    access_budget_units: int = 1
    reserve_disclosure_on_commit: bool = True


_STATE_TABLES = {
    "meta": "registry_id, budget_limit, last_time",
    "authorities": "authority_id, epoch, status, valid_until",
    "releases": "release_id, request_json, status, lease_until",
    "nonces": "nonce",
    "disclosures": "release_id",
    "charges": "charge_id, release_id, units",
    "grants": "grant_id, release_id, artifact_sha256, interface_sha256, admitted_at",
}


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LifecycleDenied(message)


def _natural(value: object, *, positive: bool = False) -> bool:
    return type(value) is int and value >= (1 if positive else 0)


class LifecycleRegistry:
    """Local registry whose writes require an independently retained checkpoint.

    All writers, including the simulated gateway, use BEGIN IMMEDIATE on the
    same database. The clock is sampled after acquiring the write lock. Test
    clocks/failpoints must never be treated as an operational time authority.
    """

    def __init__(
        self, path: Path | str, *, clock: Callable[[], float] = time.time,
        failpoint: Callable[[str], None] | None = None,
    ) -> None:
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.clock = clock
        self.failpoint = failpoint

    @classmethod
    def create(
        cls, path: Path | str, *, registry_id: str, budget_limit: int,
        clock: Callable[[], float] = time.time,
    ) -> LifecycleRegistry:
        path = Path(path).resolve()
        _require(bool(registry_id.strip()), "registry identity is required")
        _require(_natural(budget_limit), "budget must be a nonnegative integer")
        # Exclusive creation avoids replacing an existing or historical database.
        with path.open("xb"):
            pass
        registry = cls(path, clock=clock)
        with closing(registry._connect()) as db:
            db.executescript("""
                CREATE TABLE meta(registry_id TEXT NOT NULL, budget_limit INTEGER NOT NULL,
                                  last_time INTEGER NOT NULL);
                CREATE TABLE authorities(authority_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL,
                                         status TEXT NOT NULL, valid_until INTEGER NOT NULL);
                CREATE TABLE releases(release_id TEXT PRIMARY KEY, request_json TEXT NOT NULL,
                                      status TEXT NOT NULL, lease_until INTEGER);
                CREATE TABLE nonces(nonce TEXT PRIMARY KEY);
                CREATE TABLE disclosures(release_id TEXT PRIMARY KEY);
                CREATE TABLE charges(charge_id INTEGER PRIMARY KEY, release_id TEXT NOT NULL,
                                     units INTEGER NOT NULL CHECK(units >= 0));
                CREATE TABLE grants(grant_id INTEGER PRIMARY KEY, release_id TEXT NOT NULL,
                                    artifact_sha256 TEXT NOT NULL, interface_sha256 TEXT NOT NULL,
                                    admitted_at INTEGER NOT NULL);
                CREATE TABLE events(sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL,
                                    head TEXT NOT NULL);
            """)
            for table in ("nonces", "disclosures", "charges", "grants", "events"):
                for operation in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER immutable_{table}_{operation} BEFORE {operation} "
                               f"ON {table} BEGIN SELECT RAISE(ABORT, 'append-only table'); END")
            now = registry._now()
            db.execute("INSERT INTO meta VALUES (?, ?, ?)", (registry_id, budget_limit, now))
            registry._append(db, "create", None, now, extra={"registry_id": registry_id})
            db.commit()
        return registry

    def _connect(self) -> sqlite3.Connection:
        # mode=rw refuses silently recreating a missing database after rollback/loss.
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _now(self) -> int:
        value = self.clock()
        _require(isinstance(value, (int, float)) and not isinstance(value, bool), "invalid clock")
        _require(value >= 0 and value < 2**63, "invalid clock")
        return int(value)

    @staticmethod
    def _state_digest(db: sqlite3.Connection) -> str:
        state = {}
        for table, columns in _STATE_TABLES.items():
            state[table] = [list(row) for row in db.execute(
                f"SELECT {columns} FROM {table} ORDER BY 1")]
        return _digest(state)

    def _verify(self, db: sqlite3.Connection, expected: Checkpoint | None = None) -> Checkpoint:
        previous = "0" * 64
        events = db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        _require(bool(events), "registry has no genesis event")
        for sequence, event in enumerate(events):
            payload = json.loads(event["payload"])
            _require(event["sequence"] == sequence and payload["sequence"] == sequence,
                     "event sequence is discontinuous")
            _require(payload["previous_head"] == previous and _digest(payload) == event["head"],
                     "event chain does not verify")
            previous = event["head"]
        _require(payload["state_sha256"] == self._state_digest(db), "state commitment mismatch")
        identity = db.execute("SELECT registry_id FROM meta").fetchone()[0]
        checkpoint = Checkpoint(identity, len(events) - 1, previous)
        if expected is not None:
            _require(checkpoint == expected,
                     "external checkpoint mismatch: stale writer, rollback, or wrong registry")
        return checkpoint

    def checkpoint(self, *, expected: Checkpoint | None = None) -> Checkpoint:
        """Read local state; rollback detection requires a trusted external expected value."""
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            return self._verify(db, expected)

    def _append(self, db, operation, release_id, now, *, extra=None) -> Receipt:
        previous = db.execute("SELECT sequence, head FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        sequence, previous_head = (previous[0] + 1, previous[1]) if previous else (0, "0" * 64)
        db.execute("UPDATE meta SET last_time=?", (now,))
        payload = {"sequence": sequence, "previous_head": previous_head, "operation": operation,
                   "release_id": release_id, "at": now, "details": extra or {},
                   "state_sha256": self._state_digest(db)}
        head = _digest(payload)
        db.execute("INSERT INTO events VALUES (?, ?, ?)", (sequence, _json(payload), head))
        identity = db.execute("SELECT registry_id FROM meta").fetchone()[0]
        return Receipt(Checkpoint(identity, sequence, head), operation, release_id)

    def _transition(self, expected, operation, release_id, action) -> Receipt:
        _require(isinstance(expected, Checkpoint), "an external expected checkpoint is required")
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            self._verify(db, expected)
            now = self._now()
            _require(now >= db.execute("SELECT last_time FROM meta").fetchone()[0],
                     "clock moved backwards")
            details = action(db, now)
            if self.failpoint:
                self.failpoint("after_state_write")
            receipt = self._append(db, operation, release_id, now, extra=details)
            if self.failpoint:
                self.failpoint("before_commit")
            final_now = self._now()
            _require(final_now >= now, "clock moved backwards during the transaction")
            self._recheck_before_commit(db, operation, release_id, details, final_now)
            db.commit()
            # No receipt leaves the API before SQLite reports successful commit.
            return receipt
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _recheck_before_commit(self, db, operation, release_id, details, now):
        # Recheck after potentially slow event preparation. This narrows the
        # expiry race but cannot prove physical time at the durable commit or
        # at eventual output; a real gateway must enforce its own deadline.
        if operation in {"commit", "activate", "grant"}:
            row, request, _ = self._live_release(db, release_id, now)
            self._current_history(db, request)
            if operation in {"activate", "grant"}:
                _require(now < row["lease_until"], "lease expired before commit")
        elif operation == "revoke":
            self._authority(db, details["authority_id"], details["authority_epoch"], now)

    def set_authority(self, authority: Authority, *, expected: Checkpoint) -> Receipt:
        """Trusted administrative fixture input; this is not issuer authentication."""
        _require(bool(authority.authority_id.strip()), "authority identity is required")
        _require(_natural(authority.epoch) and _natural(authority.valid_until), "invalid authority epoch/time")
        _require(authority.status in {"valid", "unknown", "revoked"}, "invalid authority status")
        def apply(db, now):
            old = db.execute("SELECT epoch FROM authorities WHERE authority_id=?", (authority.authority_id,)).fetchone()
            _require(old is None or authority.epoch > old[0], "authority epoch must increase")
            db.execute("INSERT OR REPLACE INTO authorities VALUES (?, ?, ?, ?)",
                       (authority.authority_id, authority.epoch, authority.status, authority.valid_until))
            return asdict(authority)
        return self._transition(expected, "authority", None, apply)

    @staticmethod
    def _authority(db, authority_id, epoch, now):
        row = db.execute("SELECT * FROM authorities WHERE authority_id=?", (authority_id,)).fetchone()
        _require(row is not None, "authority status is unknown")
        _require(row["status"] == "valid", "authority is not currently valid")
        _require(row["epoch"] == epoch, "authority epoch changed")
        _require(now < row["valid_until"], "authority expired")
        return row

    @staticmethod
    def _charge(db, release_id, units):
        _require(_natural(units), "budget units must be a nonnegative integer")
        used = db.execute("SELECT COALESCE(SUM(units), 0) FROM charges").fetchone()[0]
        limit = db.execute("SELECT budget_limit FROM meta").fetchone()[0]
        _require(used + units <= limit, "cumulative budget exhausted")
        db.execute("INSERT INTO charges(release_id, units) VALUES (?, ?)", (release_id, units))

    def commit(self, request: CommitRequest, *, expected: Checkpoint) -> Receipt:
        _require(bool(request.release_id.strip()) and bool(request.nonce.strip()), "release and nonce are required")
        for name in ("artifact_sha256", "interface_sha256", "context_sha256", "selection_sha256"):
            _require(bool(re.fullmatch(r"[0-9a-f]{64}", getattr(request, name))), f"invalid {name}")
        _require(request.assessment_disposition == "RELEASE" and request.obligations_status == "pass"
                 and request.joint_portfolio_status == "pass",
                 "clear assessment, obligations and joint-portfolio attestations are required; RWR is unsupported")
        _require(all(_natural(getattr(request, name), positive=True) for name in
                     ("expires_at", "evidence_expires_at", "policy_expires_at", "max_accesses")),
                 "invalid release times or access limit")
        _require(_natural(request.authority_epoch), "invalid authority epoch")
        _require(_natural(request.commit_budget_cost) and _natural(request.access_budget_units, positive=True),
                 "budget costs must be frozen nonnegative commit / positive access integers")
        _require(request.reserve_disclosure_on_commit is True,
                 "this conservative subset requires disclosure reservation at commit")
        history = request.expected_disclosed_release_ids
        _require(len(set(history)) == len(history), "duplicate history identifiers")
        def apply(db, now):
            self._authority(db, request.authority_id, request.authority_epoch, now)
            _require(now < min(request.expires_at, request.evidence_expires_at, request.policy_expires_at),
                     "authorization, policy or evidence expired")
            actual = {row[0] for row in db.execute("SELECT release_id FROM disclosures")}
            _require(set(history) == actual, "cumulative disclosure history changed or is incomplete")
            _require(db.execute("SELECT 1 FROM nonces WHERE nonce=?", (request.nonce,)).fetchone() is None,
                     "nonce was already consumed")
            _require(db.execute("SELECT 1 FROM releases WHERE release_id=?", (request.release_id,)).fetchone() is None,
                     "release identity is immutable and already registered")
            db.execute("INSERT INTO nonces VALUES (?)", (request.nonce,))
            # A new disclosure invalidates every earlier service certificate.
            # A later candidate's joint attestation does not silently authorize
            # an older endpoint or permit its original context to be reused.
            db.execute("UPDATE releases SET status='suspended', lease_until=NULL "
                       "WHERE status IN ('authorized', 'active')")
            db.execute("INSERT INTO releases VALUES (?, ?, 'authorized', NULL)",
                       (request.release_id, _json(asdict(request))))
            self._charge(db, request.release_id, request.commit_budget_cost)
            db.execute("INSERT OR IGNORE INTO disclosures VALUES (?)", (request.release_id,))
            return {"request_sha256": _digest(asdict(request))}
        return self._transition(expected, "commit", request.release_id, apply)

    def _live_release(self, db, release_id, now):
        row = db.execute("SELECT * FROM releases WHERE release_id=?", (release_id,)).fetchone()
        _require(row is not None, "release is unknown")
        request = json.loads(row["request_json"])
        authority = self._authority(db, request["authority_id"], request["authority_epoch"], now)
        _require(now < min(request["expires_at"], request["evidence_expires_at"], request["policy_expires_at"]),
                 "authorization, policy or evidence expired")
        return row, request, authority

    @staticmethod
    def _current_history(db, request):
        actual = {row[0] for row in db.execute("SELECT release_id FROM disclosures")}
        bound = set(request["expected_disclosed_release_ids"]) | {request["release_id"]}
        _require(actual == bound, "disclosure history changed after this candidate's joint attestation")

    @staticmethod
    def _measure(request, artifact, interface):
        _require(request["artifact_sha256"] == artifact and request["interface_sha256"] == interface,
                 "measured artifact or complete interface differs from committed snapshot")

    def activate(self, release_id: str, *, expected: Checkpoint, artifact_sha256: str,
                 interface_sha256: str, lease_until: int) -> Receipt:
        _require(_natural(lease_until, positive=True), "invalid lease expiry")
        def apply(db, now):
            row, request, authority = self._live_release(db, release_id, now)
            _require(row["status"] == "authorized", "activation requires authorized status")
            self._current_history(db, request)
            self._measure(request, artifact_sha256, interface_sha256)
            _require(now < lease_until <= min(request["expires_at"], request["evidence_expires_at"],
                                             request["policy_expires_at"], authority["valid_until"]),
                     "lease is expired or exceeds a live prerequisite")
            db.execute("UPDATE releases SET status='active', lease_until=? WHERE release_id=?",
                       (lease_until, release_id))
            return {"lease_until": lease_until}
        return self._transition(expected, "activate", release_id, apply)

    def grant_access(self, release_id: str, *, expected: Checkpoint, artifact_sha256: str,
                     interface_sha256: str) -> Receipt:
        """Atomically record a grant to a measured snapshot; no model is served here."""
        def apply(db, now):
            row, request, _ = self._live_release(db, release_id, now)
            _require(row["status"] == "active", "access requires active status")
            self._current_history(db, request)
            self._measure(request, artifact_sha256, interface_sha256)
            _require(now < row["lease_until"], "lease expired")
            accesses = db.execute("SELECT COUNT(*) FROM grants WHERE release_id=?", (release_id,)).fetchone()[0]
            _require(accesses < request["max_accesses"], "access allowance exhausted")
            budget_units = request["access_budget_units"]
            self._charge(db, release_id, budget_units)
            db.execute("INSERT OR IGNORE INTO disclosures VALUES (?)", (release_id,))
            db.execute("INSERT INTO grants(release_id, artifact_sha256, interface_sha256, admitted_at) "
                       "VALUES (?, ?, ?, ?)", (release_id, artifact_sha256, interface_sha256, now))
            return {"access_number": accesses + 1, "budget_units": budget_units}
        return self._transition(expected, "grant", release_id, apply)

    def revoke(self, release_id: str, *, expected: Checkpoint, authority_id: str,
               authority_epoch: int, reason: str) -> Receipt:
        _require(bool(reason.strip()), "revocation requires a reason")
        def apply(db, now):
            # In this fixture every locally installed authority is a registry-wide
            # revoker. Real role/delegation authorization is deliberately absent.
            self._authority(db, authority_id, authority_epoch, now)
            row = db.execute("SELECT status FROM releases WHERE release_id=?", (release_id,)).fetchone()
            _require(row is not None and row[0] != "revoked", "unknown or already revoked release")
            db.execute("UPDATE releases SET status='revoked', lease_until=NULL WHERE release_id=?", (release_id,))
            return {"reason": reason, "authority_id": authority_id, "authority_epoch": authority_epoch}
        return self._transition(expected, "revoke", release_id, apply)

    def snapshot(self, *, expected: Checkpoint) -> dict:
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            checkpoint = self._verify(db, expected)
            return {"checkpoint": asdict(checkpoint),
                    "disclosed_release_ids": [row[0] for row in db.execute("SELECT release_id FROM disclosures ORDER BY 1")],
                    "release_statuses": dict(db.execute("SELECT release_id, status FROM releases ORDER BY 1")),
                    "budget_used": db.execute("SELECT COALESCE(SUM(units), 0) FROM charges").fetchone()[0],
                    "grant_count": db.execute("SELECT COUNT(*) FROM grants").fetchone()[0],
                    "nonce_count": db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0]}
