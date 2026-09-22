"""Durable, single-host export boundary for the fixed synthetic experiment.

The database contains private mechanism state. Only this trusted process may
read it; this module does not provide OS isolation, authenticated custody, or
protection from a database owner rewriting both values and their hashes.
No filesystem artifact path, uploaded model, or caller-provided privacy claim
is accepted. A committed release is conservatively counted before delivery.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Callable
import uuid

from . import mechanism


class ExportDenied(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _deny(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ExportDenied(code, message)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: bytes) -> str:
    return sha256(value).hexdigest()


class ExportStore:
    """Serialized two-stage broker; one DB is one retained disclosure history.

    ``failpoint`` is a test hook called during commit at after_state_write,
    before_commit and after_commit. An after_commit exception represents lost
    acknowledgement: retry returns the already durable receipt and bytes.
    """

    ROUTES = frozenset({"retained-state", "independent", "central-count"})

    SCHEMA_VERSION = 1
    MARKER = ".export-history"

    def __init__(self, root: Path, *, failpoint: Callable[[str], None] | None = None,
                 create: bool = True, read_only: bool = False):
        self.root = Path(root).resolve()
        self.path = self.root / "export.sqlite3"
        self.marker = self.root / self.MARKER
        self.failpoint = failpoint
        self.read_only = read_only
        self.mechanism_sha256 = _hash(Path(mechanism.__file__).read_bytes())
        if not self.path.exists():
            _deny(not self.marker.exists(), "history_missing", "Initialized history is missing; no reset is permitted.")
            _deny(create and not read_only, "not_initialized", "Initialize a new export history explicitly before opening it.")
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("xb"):
                    pass
            except FileExistsError:
                raise ExportDenied("history_busy", "Another process is initializing this history; retry after it finishes.") from None
            self._initialize()
        with self._connect() as db:
            db.execute("BEGIN" if read_only else "BEGIN IMMEDIATE")
            self._validate_history(db)
            if not read_only and not self.marker.exists():
                self._bind_identity(db)

    @classmethod
    def open_existing(cls, root: Path) -> "ExportStore":
        """Open an existing producer history; never initialize a missing DB."""
        return cls(root, create=False)

    @classmethod
    def open_read_only(cls, root: Path) -> "ExportStore":
        """Inspect a stable file snapshot without changing even source sidecars.

        A report is an observation, never a release authorization: another
        process may commit immediately after the snapshot was acquired.
        """
        return cls(root, create=False, read_only=True)

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE meta (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    revision INTEGER NOT NULL, privacy_ratio INTEGER NOT NULL);
                INSERT INTO meta VALUES (1,0,1);
                CREATE TABLE candidates (
                    request_id TEXT PRIMARY KEY, stage INTEGER NOT NULL,
                    route TEXT NOT NULL, base_revision INTEGER NOT NULL,
                    first_digest TEXT, private_state TEXT NOT NULL,
                    state_digest TEXT NOT NULL, certificate TEXT NOT NULL,
                    certificate_digest TEXT NOT NULL, bundle BLOB NOT NULL,
                    artifact_digest TEXT NOT NULL, receipt TEXT);
                CREATE TABLE releases (
                    release_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE REFERENCES candidates(request_id),
                    stage INTEGER NOT NULL UNIQUE, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE implementation (
                    id INTEGER PRIMARY KEY CHECK(id=1), mechanism_sha256 TEXT NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO implementation VALUES (1,?)", (self.mechanism_sha256,))

    def _bind_identity(self, db) -> None:
        """Add a deletion guard only after validating a supported old history.

        The guard is not an external monotonic counter or authentication. An
        owner replacing both the DB and marker can still roll history back.
        """
        identity = uuid.uuid4().hex
        db.execute("CREATE TABLE IF NOT EXISTS history_identity ("
                   "id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, history_id TEXT NOT NULL)")
        saved = db.execute("SELECT history_id FROM history_identity WHERE id=1").fetchone()
        if saved:
            identity = saved[0]
        else:
            db.execute("INSERT INTO history_identity VALUES (1,?,?)", (self.SCHEMA_VERSION, identity))
        db.commit()
        try:
            with self.marker.open("x", encoding="utf-8") as marker:
                marker.write(_json({"version": self.SCHEMA_VERSION, "history_id": identity}))
        except FileExistsError:
            pass
        self._validate_identity(db)

    def _validate_identity(self, db) -> None:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "history_identity" in names:
            rows = db.execute("SELECT id,version,history_id FROM history_identity").fetchall()
            _deny(len(rows) == 1 and rows[0][0] == 1 and rows[0][1] == self.SCHEMA_VERSION
                  and isinstance(rows[0][2], str) and re.fullmatch(r"[0-9a-f]{32}", rows[0][2]) is not None,
                  "unsupported_schema", "History identity schema or version is unsupported.")
            if self.marker.exists():
                try:
                    marker = json.loads(self.marker.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    raise ExportDenied("tampered", "History initialization marker is invalid.") from None
                _deny(marker == {"version": rows[0][1], "history_id": rows[0][2]},
                      "tampered", "Database and initialization marker identify different histories.")
        else:
            _deny(not self.marker.exists(), "tampered", "Initialized history lost its identity table.")

    @contextmanager
    def _snapshot(self):
        # SQLite mode=ro can update -shm. Immutable reads omit uncheckpointed
        # WAL. Inspect a bounded, twice-identical DB/WAL copy instead, replaying
        # any committed WAL frames only inside a temporary directory. Two
        # matching reads detect ordinary concurrent changes; they do not defend
        # against an owner performing ABA replacement or whole-history rollback.
        sources = (self.path, Path(str(self.path) + "-wal"))
        def read_pair():
            result = []
            for index, source in enumerate(sources):
                if index and not source.exists():
                    result.append(None)
                    continue
                _deny(source.stat().st_size <= 256 * 1024 * 1024,
                      "history_too_large", "History exceeds the bounded diagnostic snapshot size.")
                result.append(source.read_bytes())
            return result
        first = read_pair()
        _deny(first == read_pair(), "history_busy", "History changed during inspection; retry a stable snapshot.")
        with tempfile.TemporaryDirectory(prefix="mra-history-inspect-") as temporary:
            path = Path(temporary) / self.path.name
            path.write_bytes(first[0])
            if first[1] is not None:
                Path(str(path) + "-wal").write_bytes(first[1])
            yield path

    @contextmanager
    def _connect(self):
        @contextmanager
        def source():
            if self.read_only:
                with self._snapshot() as path:
                    yield path
            else:
                yield self.path
        try:
            _deny(self.path.is_file(), "history_missing", "History database is missing; no reset is permitted.")
            with source() as path:
                db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=15)
                try:
                    db.row_factory = sqlite3.Row
                    db.execute("PRAGMA synchronous=FULL")
                    db.execute("PRAGMA foreign_keys=ON")
                    if self.read_only:
                        db.execute("PRAGMA query_only=ON")
                    with db:
                        yield db
                finally:
                    db.close()
        except sqlite3.Error:
            raise ExportDenied("invalid_history", "History database is unreadable or has an unsupported schema; no reset was performed.") from None
        except OSError:
            raise ExportDenied("history_unavailable", "History files are unavailable; no reset was performed.") from None

    def _write_allowed(self):
        _deny(not self.read_only, "read_only", "A diagnostic history handle cannot mutate or authorize delivery.")

    @staticmethod
    def _request_id(value: str) -> None:
        _deny(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None,
              "invalid_request", "Use a request key of 1–128 letters, digits, hyphens or underscores.")

    @staticmethod
    def _revision(value: int) -> None:
        _deny(type(value) is int and value >= 0, "invalid_request", "Revision must be a nonnegative integer.")

    @staticmethod
    def _meta(db):
        return db.execute("SELECT revision,privacy_ratio FROM meta WHERE id=1").fetchone()

    def _validate_history(self, db) -> dict:
        """Check internal consistency, not a new mathematical DP certificate."""
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"meta", "candidates", "releases", "implementation"}
        _deny(required <= tables <= required | {"history_identity"},
              "unsupported_schema", "History has missing or unknown tables; explicit migration is required.")
        columns = {
            "meta": ("id", "revision", "privacy_ratio"),
            "candidates": ("request_id", "stage", "route", "base_revision", "first_digest", "private_state",
                           "state_digest", "certificate", "certificate_digest", "bundle", "artifact_digest", "receipt"),
            "releases": ("release_id", "request_id", "stage", "revoked"),
            "implementation": ("id", "mechanism_sha256"),
            "history_identity": ("id", "version", "history_id"),
        }
        _deny(all(tuple(row[1] for row in db.execute(f"PRAGMA table_info({table})")) == columns[table]
                  for table in tables)
              and not db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()
              and db.execute("PRAGMA user_version").fetchone()[0] == 0,
              "unsupported_schema", "Unexpected columns, triggers, views or schema version require explicit migration.")
        self._validate_identity(db)
        bindings = db.execute("SELECT id,mechanism_sha256 FROM implementation").fetchall()
        _deny(len(bindings) == 1 and bindings[0][0] == 1,
              "unbound_implementation", "History has no unique producer source binding.")
        _deny(bindings[0][1] == self.mechanism_sha256 == _hash(Path(mechanism.__file__).read_bytes()),
              "changed_implementation", "The mechanism source changed; review an explicit migration.")
        metas = db.execute("SELECT id,revision,privacy_ratio FROM meta").fetchall()
        _deny(len(metas) == 1 and metas[0]["id"] == 1, "tampered", "History metadata is missing or duplicated.")
        meta = metas[0]
        candidates = db.execute("SELECT * FROM candidates ORDER BY rowid").fetchall()
        releases = db.execute("SELECT * FROM releases ORDER BY stage").fetchall()
        _deny(len(candidates) <= 128 and len(releases) <= 2, "tampered", "History exceeds its fixed mechanism scope.")
        _deny([row["stage"] for row in releases] == list(range(1, len(releases) + 1)),
              "tampered", "Committed stages are not a contiguous disclosure history.")
        _deny(all(row["revoked"] in (0, 1) for row in releases), "tampered", "Invalid revocation state.")
        expected_ratio = (1, 2, 4)[len(releases)]
        _deny(meta["revision"] == len(releases) + sum(row["revoked"] for row in releases)
              and meta["privacy_ratio"] == expected_ratio, "tampered", "Accounting metadata differs from retained disclosures and revocations.")
        by_request = {row["request_id"]: row for row in candidates}
        released = {row["request_id"]: row for row in releases}
        _deny(len(released) == len(releases)
              and set(released) == {row["request_id"] for row in candidates if row["receipt"] is not None},
              "tampered", "Disclosure records and committed candidate receipts do not form a bijection.")
        first = by_request.get(releases[0]["request_id"]) if releases else None
        for row in candidates:
            _deny(row["stage"] in (1, 2) and isinstance(row["request_id"], str)
                  and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", row["request_id"]) is not None
                  and ((row["stage"] == 1 and row["route"] == "first" and row["base_revision"] == 0
                        and row["first_digest"] is None)
                       or (row["stage"] == 2 and row["route"] in self.ROUTES
                           and first is not None and row["first_digest"] == first["artifact_digest"]
                           and row["base_revision"] in (1, 2)
                           and (row["base_revision"] != 2 or releases[0]["revoked"] == 1)))
                  and row["base_revision"] <= meta["revision"],
                  "tampered", "Candidate stage, parent, route or revision is inconsistent with actual history.")
        public = []
        for release in releases:
            row = by_request[release["request_id"]]
            _deny(row["stage"] == release["stage"], "tampered", "Receipt and disclosure stages differ.")
            self._validate_artifact(row)
            receipt = self._receipt(row, release["release_id"])
            receipt["revoked"] = bool(release["revoked"])
            public.append(receipt)
        return {"valid": True, "revision": meta["revision"], "privacy_ratio": expected_ratio,
                "history_ratio": expected_ratio, "delta": 0,
                "committed_count": len(releases), "prepared_count": len(candidates) - len(releases),
                "revoked_count": sum(row["revoked"] for row in releases),
                "public_history_sha256": _hash(_json(public).encode()),
                "mechanism_source_sha256": self.mechanism_sha256,
                "checks": ["supported_schema", "producer_source_binding", "accounting_matches_history",
                           "contiguous_stages", "receipt_candidate_bijection", "actual_parent_binding",
                           "committed_artifact_state_certificate_hashes", "committed_receipt_bindings"],
                "scope": "fixed-synthetic-fixture-only", "snapshot_only": self.read_only,
                "can_authorize": False,
                "limits": "Internal consistency only; not a DP proof, authenticated custody, or external rollback protection."}

    def verify_history(self) -> dict:
        """Return public consistency evidence without exposing staged hashes."""
        with self._connect() as db:
            db.execute("BEGIN")
            return self._validate_history(db)

    @staticmethod
    def _candidate(row, revision: int) -> dict:
        return {"request_id": row["request_id"], "stage": row["stage"], "route": row["route"],
                "base_revision": row["base_revision"],
                "status": "committed" if row["receipt"] else "prepared",
                "stale": not bool(row["receipt"]) and row["base_revision"] != revision}

    @staticmethod
    def _receipt(row, release_id: str) -> dict:
        try:
            receipt = json.loads(row["receipt"])
            ratio = 2 if row["stage"] == 1 else 4
            expected = {"request_id": row["request_id"], "release_id": release_id,
                        "stage": row["stage"], "route": row["route"], "revision": row["base_revision"] + 1,
                        "artifact_sha256": row["artifact_digest"], "parent_artifact_sha256": row["first_digest"],
                        "privacy_ratio": ratio, "history_ratio": ratio, "delta": 0,
                        "status": "committed", "scope": "fixed-synthetic-fixture-only"}
            _deny(receipt == expected, "tampered", "Stored receipt differs from the committed artifact binding.")
            return receipt
        except (ValueError, TypeError) as error:
            if isinstance(error, ExportDenied):
                raise
            raise ExportDenied("tampered", "Stored receipt is invalid.") from None

    @staticmethod
    def _validate_artifact(row) -> tuple[dict, bytes, dict]:
        """Detect corruption and binding drift; not hostile-owner authentication."""
        try:
            _deny(isinstance(row["bundle"], bytes) and 0 < len(row["bundle"]) <= 1_000_000
                  and isinstance(row["private_state"], str) and isinstance(row["certificate"], str),
                  "tampered", "Stored artifact fields have invalid types or size.")
            blob = bytes(row["bundle"])
            _deny(_hash(blob) == row["artifact_digest"], "tampered", "Stored export bytes changed.")
            _deny(_hash(row["private_state"].encode()) == row["state_digest"], "tampered", "Private state changed.")
            _deny(_hash(row["certificate"].encode()) == row["certificate_digest"], "tampered", "Certificate changed.")
            state = json.loads(row["private_state"])
            cert = json.loads(row["certificate"])
            bundle = mechanism.inspect_bundle(blob)
            route = "first-rr" if row["stage"] == 1 else row["route"]
            ratio = 2 if row["stage"] == 1 else 4
            valid = (
                state["schema"] == mechanism.STATE_SCHEMA and state["stage"] == row["stage"]
                and
                cert["schema"] == "mra-export-poc-certificate-v1"
                and cert["stage"] == row["stage"] and cert["route"] == route
                and cert["history_ratio"] == ratio and cert["delta"] == 0
                and cert["trusted_producer"] == "fixed-synthetic-fixture-v1"
                and cert["first_artifact_sha256"] == row["first_digest"]
                and bundle["schema"] == "mra-export-poc-model-v1"
                and bundle["stage"] == row["stage"] and bundle["route"] == route
                and bundle["guarantee"]["history_ratio"] == ratio
                and bundle["guarantee"]["delta"] == 0
                and bundle["parent_artifact_sha256"] == row["first_digest"]
                and state["first_bundle_sha256"] == (row["first_digest"] or row["artifact_digest"])
            )
        except ExportDenied:
            raise
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ExportDenied("tampered", "Stored construction metadata is invalid.") from None
        _deny(valid, "tampered", "Construction metadata does not bind the exact export history.")
        return state, blob, cert

    def status(self) -> dict:
        with self._connect() as db:
            db.execute("BEGIN")
            self._validate_history(db)
            meta = self._meta(db)
            candidates = [self._candidate(row, meta["revision"]) for row in db.execute(
                "SELECT request_id,stage,route,base_revision,receipt FROM candidates ORDER BY rowid")]
            releases = []
            for row in db.execute("SELECT r.release_id,r.revoked,c.* FROM releases r "
                                  "JOIN candidates c USING(request_id) ORDER BY r.stage"):
                release = self._receipt(row, row["release_id"])
                release["revoked"] = bool(row["revoked"])
                releases.append(release)
        return {"revision": meta["revision"], "privacy_ratio": meta["privacy_ratio"],
                "history_ratio": meta["privacy_ratio"], "delta": 0,
                "candidates": candidates, "releases": releases,
                "scope": "fixed-synthetic-fixture-only", "agency_deployed": False,
                "mechanism_source_sha256": self.mechanism_sha256}

    def prepare(self, request_id: str, stage: int, route: str, expected_revision: int) -> dict:
        self._write_allowed()
        self._request_id(request_id)
        self._revision(expected_revision)
        _deny(type(stage) is int and stage in {1, 2}, "invalid_request", "Only stages 1 and 2 are supported.")
        _deny(isinstance(route, str) and ((stage == 1 and route == "first") or (stage == 2 and route in self.ROUTES)),
              "invalid_request", "Unsupported route for this stage.")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._validate_history(db)
            meta = self._meta(db)
            existing = db.execute("SELECT * FROM candidates WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                _deny((existing["stage"], existing["route"], existing["base_revision"]) ==
                      (stage, route, expected_revision), "idempotency_conflict", "Request key already binds different parameters.")
                self._validate_artifact(existing)
                return self._candidate(existing, meta["revision"])
            _deny(meta["revision"] == expected_revision, "stale_history", "Refresh the current history before preparing.")
            _deny(db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] < 128,
                  "candidate_limit", "This bounded experiment retains at most 128 prepared candidates.")
            count = db.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
            _deny(count < 2, "budget_exhausted", "The two-stage experiment is complete; prior disclosures remain counted.")
            _deny(stage == count + 1, "invalid_stage", "Prepare the next uncommitted stage only.")
            first_digest = None
            if stage == 1:
                state, blob, cert = mechanism.first_release()
            else:
                first = db.execute("SELECT c.* FROM candidates c JOIN releases r USING(request_id) WHERE r.stage=1").fetchone()
                old_state, _, _ = self._validate_artifact(first)
                first_digest = first["artifact_digest"]
                state, blob, cert = mechanism.next_release(old_state, route)
            _deny(isinstance(blob, bytes) and 0 < len(blob) <= 1_000_000,
                  "invalid_construction", "Trusted construction returned an invalid export.")
            state_json, cert_json = _json(state), _json(cert)
            db.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                       (request_id, stage, route, expected_revision, first_digest, state_json,
                        _hash(state_json.encode()), cert_json, _hash(cert_json.encode()), blob, _hash(blob)))
            row = db.execute("SELECT * FROM candidates WHERE request_id=?", (request_id,)).fetchone()
            self._validate_artifact(row)
            return self._candidate(row, meta["revision"])

    def commit(self, request_id: str, expected_revision: int) -> dict:
        self._write_allowed()
        self._request_id(request_id)
        self._revision(expected_revision)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._validate_history(db)
            row = db.execute("SELECT * FROM candidates WHERE request_id=?", (request_id,)).fetchone()
            _deny(row is not None, "not_found", "Prepared request not found.")
            _deny(row["base_revision"] == expected_revision, "stale_history", "Commit must name the prepared history revision.")
            self._validate_artifact(row)
            if row["receipt"]:
                release = db.execute("SELECT release_id FROM releases WHERE request_id=?", (request_id,)).fetchone()
                _deny(release is not None, "tampered", "Committed receipt has no disclosure record.")
                return self._receipt(row, release["release_id"])
            meta = self._meta(db)
            _deny(meta["revision"] == expected_revision, "stale_history", "Another history change invalidated this candidate.")
            count = db.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
            _deny(row["stage"] == count + 1 and count < 2, "budget_exhausted", "This stage is already committed.")
            if row["stage"] == 2:
                first = db.execute("SELECT c.* FROM candidates c JOIN releases r USING(request_id) WHERE r.stage=1").fetchone()
                self._validate_artifact(first)
                _deny(row["first_digest"] == first["artifact_digest"], "tampered", "First-release binding changed.")
            ratio = 2 if row["stage"] == 1 else 4
            receipt = {"request_id": request_id, "release_id": uuid.uuid4().hex,
                       "stage": row["stage"], "route": row["route"], "revision": expected_revision + 1,
                       "artifact_sha256": row["artifact_digest"], "parent_artifact_sha256": row["first_digest"],
                       "privacy_ratio": ratio, "history_ratio": ratio, "delta": 0,
                       "status": "committed", "scope": "fixed-synthetic-fixture-only"}
            db.execute("INSERT INTO releases VALUES (?,?,?,0)", (receipt["release_id"], request_id, row["stage"]))
            db.execute("UPDATE candidates SET receipt=? WHERE request_id=?", (_json(receipt), request_id))
            db.execute("UPDATE meta SET revision=?,privacy_ratio=? WHERE id=1", (receipt["revision"], ratio))
            if self.failpoint:
                self.failpoint("after_state_write")
                self.failpoint("before_commit")
            db.commit()
            if self.failpoint:
                self.failpoint("after_commit")
            return receipt

    def download(self, release_id: str) -> bytes:
        self._write_allowed()
        with self._connect() as db:
            # Admission serializes with revocation. A subsequent revoke cannot
            # erase bytes already admitted or held by the caller.
            db.execute("BEGIN IMMEDIATE")
            self._validate_history(db)
            row = db.execute("SELECT c.*,r.revoked FROM releases r JOIN candidates c USING(request_id) WHERE r.release_id=?",
                             (release_id,)).fetchone()
            _deny(row is not None, "not_committed", "No committed export exists for this identifier.")
            _deny(not row["revoked"], "revoked", "Further download admission has been revoked.")
            self._receipt(row, release_id)
            _, blob, _ = self._validate_artifact(row)
            return blob

    def revoke(self, release_id: str) -> dict:
        self._write_allowed()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._validate_history(db)
            row = db.execute("SELECT c.receipt,r.revoked FROM releases r JOIN candidates c USING(request_id) WHERE r.release_id=?",
                             (release_id,)).fetchone()
            _deny(row is not None, "not_found", "Committed release not found.")
            if not row["revoked"]:
                db.execute("UPDATE releases SET revoked=1 WHERE release_id=?", (release_id,))
                db.execute("UPDATE meta SET revision=revision+1 WHERE id=1")
            meta = self._meta(db)
            return {"release_id": release_id, "revoked": True, "revision": meta["revision"],
                    "privacy_ratio": meta["privacy_ratio"], "history_ratio": meta["privacy_ratio"],
                    "disclosure_retained": True, "recall_of_downloaded_copies": False}
