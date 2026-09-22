"""A trusted, local, fail-closed temporal release broker.

The registry is an administrative interface, not a verifier of arbitrary DP
certificates. Its caller must establish that each immutable cache really is an
attribute-DP randomization at the stated epsilon, that all model/score inputs
use that cache, and that exported bytes contain no raw-data side channel. The
broker checks the registered contract, binds bytes, and accounts sequentially;
it neither inspects model semantics nor supplies authentication over a network.

Record IDs are STABLE protected-unit keys, never dataset/model/version IDs.
Changing an attribute requires a new cache event for the SAME unit key. This
prototype covers one fixed-roster attribute-neighbour relation represented by
scope_digest. Its scope does not include participation, whole records, groups,
identity linkage, or changing a roster. A dishonest administrator, rollback or
deletion of this database, bypass exports, and post-download revocation are
outside the assurance boundary. Internal manifests/receipts may contain private
commitments: download returns ONLY the prevalidated recipient artifact bytes.

Expiry times are integer UTC epoch seconds. With now=None (the default), the
injected trusted clock is sampled INSIDE the SQLite transaction, after lock
acquisition and again at the authorization decision before publication/return.
Explicit integer now values are for deterministic operation-time simulation;
they are not a live-clock expiry guarantee. Already admitted/downloaded bytes
cannot be recalled when an expiry or revocation occurs later. Production must
provide a trusted clock, authorization, durable backup/anti-rollback controls,
source/cache verification and a protected packaging adapter. SQLite serializes
commits, not the training system or arbitrary external service requests.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from typing import Iterable


class AssuranceError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code, message):
    raise AssuranceError(code, message)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: bytes):
    return hashlib.sha256(value).hexdigest()


def _digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _fail("invalid_digest", "Expected a lowercase SHA-256 hexadecimal digest")
    return value


def _integer(value, name):
    if type(value) is not int or value < 0 or value > 2**63 - 1:
        _fail("invalid_integer", f"{name} must be a nonnegative SQLite-range integer")
    return value


def _key(value):
    if (not isinstance(value, str) or not value or value.strip() != value
            or unicodedata.normalize("NFC", value) != value or "\x00" in value):
        _fail("invalid_key", "IDs must be nonempty canonical NFC strings without edge whitespace or NUL")
    return value


def _records(values: Iterable[str], *, allow_empty=False):
    if isinstance(values, (str, bytes)):
        _fail("invalid_records", "Record IDs must be a collection of stable unit keys")
    original = [_key(v) for v in values]
    if len(set(original)) != len(original) or (not original and not allow_empty):
        _fail("invalid_records", "Record IDs must be unique and nonempty")
    return sorted(original)


class AssuranceStore:
    """SQLite reference broker; every registration method is TRUSTED ADMIN ONLY."""

    def __init__(self, path, *, budget_micros: int, scope_digest: str, clock=time.time):
        self.path = str(Path(path))
        self.budget_micros = _integer(budget_micros, "budget_micros")
        self.scope_digest = _digest(scope_digest)
        if not callable(clock):
            _fail("invalid_clock", "Clock must be a trusted callable returning UTC epoch seconds")
        self.clock = clock
        # Opening a new database is explicit construction. Deletion/rollback by
        # an administrator cannot be detected without an external trust anchor.
        with self._connection() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS evidence(digest TEXT PRIMARY KEY, payload BLOB NOT NULL,
                expires_at INTEGER NOT NULL, invalidated INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, records TEXT NOT NULL,
                evidence TEXT NOT NULL, expires_at INTEGER NOT NULL, attribute_version TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS caches(id TEXT PRIMARY KEY, cache_digest TEXT NOT NULL,
                epsilon INTEGER NOT NULL, records TEXT NOT NULL, evidence TEXT NOT NULL,
                expires_at INTEGER NOT NULL, attribute_version TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY, cache_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL, records TEXT NOT NULL, artifact BLOB NOT NULL,
                artifact_digest TEXT NOT NULL, evidence TEXT NOT NULL, expires_at INTEGER NOT NULL,
                scoring TEXT NOT NULL, serving_records TEXT NOT NULL, serving_cache_id TEXT);
              CREATE TABLE IF NOT EXISTS authorities(id TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                manifest TEXT NOT NULL, charge_records TEXT NOT NULL, receipt TEXT,
                revoked INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS charges(cache_id TEXT NOT NULL, record_id TEXT NOT NULL,
                epsilon INTEGER NOT NULL, request_id TEXT NOT NULL,
                PRIMARY KEY(cache_id, record_id));
              CREATE INDEX IF NOT EXISTS charge_unit ON charges(record_id);
            """)
            db.execute("BEGIN IMMEDIATE")
            expected = {"schema": "1", "budget_micros": str(self.budget_micros), "scope_digest": self.scope_digest}
            old = dict(db.execute("SELECT key, value FROM meta"))
            if old:
                if any(old.get(k) != v for k, v in expected.items()) or "revision" not in old:
                    _fail("configuration_mismatch", "Existing ledger budget, scope, or schema differs")
            else:
                db.executemany("INSERT INTO meta VALUES(?, ?)", [*expected.items(), ("revision", "0")])
            db.commit()

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        # Do not silently recreate an erased ledger through an ordinary operation.
        if not Path(self.path).is_file():
            _fail("ledger_missing", "Ledger was removed; administrative recovery is required")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()

    @staticmethod
    def _get(db, table, key):
        # table names are internal constants, never user values.
        row = db.execute(f"SELECT * FROM {table} WHERE {'digest' if table == 'evidence' else 'id'}=?", (key,)).fetchone()
        if row is None:
            _fail("missing_evidence", f"Unregistered {table} entry: {key}")
        return row

    @staticmethod
    def _immutable_insert(db, table, values):
        key = "digest" if table == "evidence" else "id"
        old = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (values[key],)).fetchone()
        if old is not None:
            if any(old[k] != v for k, v in values.items()):
                _fail("immutable_binding", f"Cannot rebind existing {table} identity")
            return
        columns = ",".join(values)
        marks = ",".join("?" for _ in values)
        db.execute(f"INSERT INTO {table}({columns}) VALUES({marks})", tuple(values.values()))

    def register_evidence(self, evidence_bytes: bytes, *, expires_at: int) -> str:
        if not isinstance(evidence_bytes, bytes) or not evidence_bytes:
            _fail("invalid_evidence", "Evidence must be nonempty immutable bytes")
        digest = _hash(evidence_bytes)
        with self._transaction() as db:
            self._immutable_insert(db, "evidence", {"digest": digest, "payload": evidence_bytes,
                                                   "expires_at": _integer(expires_at, "expires_at")})
        return digest

    def register_dataset(self, dataset_digest, *, record_ids, evidence_digest, expires_at, attribute_version="v1"):
        records = _records(record_ids)
        with self._transaction() as db:
            self._get(db, "evidence", _digest(evidence_digest))
            self._immutable_insert(db, "datasets", {"id": _digest(dataset_digest), "records": _json(records),
                "evidence": evidence_digest, "expires_at": _integer(expires_at, "expires_at"),
                "attribute_version": _key(attribute_version)})

    def register_cache(self, cache_id, *, cache_digest, epsilon_micros, record_ids,
                       evidence_digest, expires_at, scope_digest=None, attribute_version="v1"):
        if scope_digest is not None and scope_digest != self.scope_digest:
            _fail("scope_mismatch", "A cache cannot change the ledger privacy scope")
        records = _records(record_ids)
        with self._transaction() as db:
            self._get(db, "evidence", _digest(evidence_digest))
            self._immutable_insert(db, "caches", {"id": _key(cache_id), "cache_digest": _digest(cache_digest),
                "epsilon": _integer(epsilon_micros, "epsilon_micros"), "records": _json(records),
                "evidence": evidence_digest, "expires_at": _integer(expires_at, "expires_at"),
                "attribute_version": _key(attribute_version)})

    def register_model(self, model_id, *, cache_id, dataset_digest, record_ids, artifact_bytes,
                       evidence_digest, expires_at, scoring="model_only", serving_records=(), serving_cache_id=None):
        if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
            _fail("invalid_artifact", "Recipient package must be nonempty immutable bytes")
        records = _records(record_ids)
        serving = _records(serving_records, allow_empty=True)
        if scoring not in {"model_only", "cached", "fresh"}:
            _fail("serving_denied", "Only model_only, cached, or separately accounted fresh-cache scoring is permitted")
        if scoring == "model_only" and (serving or serving_cache_id is not None):
            _fail("serving_denied", "Model-only packages cannot carry score inputs")
        if scoring != "model_only" and (not serving or serving_cache_id is None):
            _fail("serving_denied", "Scored packages need explicit serving units and a registered serving cache")
        if scoring == "cached" and serving_cache_id != cache_id:
            _fail("serving_denied", "Cached scoring must reuse the training randomization")
        if scoring == "fresh" and serving_cache_id == cache_id:
            _fail("serving_denied", "Fresh scoring requires a distinct accounted cache event")
        with self._transaction() as db:
            data = self._get(db, "datasets", _digest(dataset_digest))
            cache = self._get(db, "caches", _key(cache_id))
            self._get(db, "evidence", _digest(evidence_digest))
            if records != json.loads(data["records"]) or not set(records).issubset(json.loads(cache["records"])):
                _fail("lineage_mismatch", "Training unit set must equal its dataset and be covered by its cache")
            if data["attribute_version"] != cache["attribute_version"]:
                _fail("version_mismatch", "Training data and cache refer to different attribute versions")
            if scoring != "model_only":
                score_cache = self._get(db, "caches", _key(serving_cache_id))
                if not set(serving).issubset(json.loads(score_cache["records"])):
                    _fail("lineage_mismatch", "Scoring includes units outside its immutable cache")
                if score_cache["attribute_version"] != data["attribute_version"]:
                    _fail("version_mismatch", "Serving cache and training data refer to different attribute versions")
            self._immutable_insert(db, "models", {"id": _key(model_id), "cache_id": cache_id,
                "dataset_id": dataset_digest, "records": _json(records), "artifact": artifact_bytes,
                "artifact_digest": _hash(artifact_bytes), "evidence": evidence_digest,
                "expires_at": _integer(expires_at, "expires_at"), "scoring": scoring,
                "serving_records": _json(serving), "serving_cache_id": serving_cache_id})

    def register_authority(self, authority_id, *, expires_at):
        with self._transaction() as db:
            self._immutable_insert(db, "authorities", {"id": _key(authority_id),
                                                       "expires_at": _integer(expires_at, "expires_at")})

    @staticmethod
    def _revision(db):
        return int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])

    def revision(self):
        with self._transaction() as db:
            return self._revision(db)

    def _operation_time(self, now):
        if now is not None:
            return _integer(now, "now")
        value = self.clock()
        if (type(value) not in (int, float) or value < 0 or value > 2**63 - 1
                or not math.isfinite(value)):
            _fail("invalid_clock", "Trusted clock returned an invalid UTC epoch time")
        return _integer(int(value), "clock")

    def _live(self, db, model_id, authority_id, now, *, check_integrity=True):
        authority = self._get(db, "authorities", authority_id)
        model = self._get(db, "models", model_id)
        cache = self._get(db, "caches", model["cache_id"])
        dataset = self._get(db, "datasets", model["dataset_id"])
        required = [("model", model), ("cache", cache), ("dataset", dataset)]
        if model["serving_cache_id"] is not None:
            required.append(("serving_cache", self._get(db, "caches", model["serving_cache_id"])))
        evidence_rows = [(label, self._get(db, "evidence", item["evidence"])) for label, item in required]
        if check_integrity:
            for _, evidence in evidence_rows:
                if _hash(evidence["payload"]) != evidence["digest"]:
                    _fail("integrity_failure", "Evidence payload does not match its commitment")
            if _hash(model["artifact"]) != model["artifact_digest"]:
                _fail("integrity_failure", "Stored artifact does not match its commitment")
        # The clock read occurs after lock acquisition, registry loads and hash
        # work. A final check also follows budget/ledger or package preparation.
        current = self._operation_time(now)
        if authority["revoked"] or current >= authority["expires_at"]:
            _fail("authority_inactive", "Current authority is revoked or expired")
        for label, item in required:
            if current >= item["expires_at"]:
                _fail("evidence_expired", f"{label} registration has expired")
        for label, evidence in evidence_rows:
            if evidence["invalidated"]:
                _fail("evidence_invalidated", f"{label} evidence has been invalidated")
            if current >= evidence["expires_at"]:
                _fail("evidence_expired", f"{label} evidence has expired")
        return model, cache, dataset

    def _charge_plan(self, db, footprints):
        # Compute using Python integers to prevent SQLite SUM overflow.
        spent = {}
        existing = set()
        for cache, record, value in db.execute("SELECT cache_id, record_id, epsilon FROM charges"):
            existing.add((cache, record))
            spent[record] = spent.get(record, 0) + value
        needed = []
        for cache_id, records in sorted(footprints.items()):
            epsilon = self._get(db, "caches", cache_id)["epsilon"]
            for record in sorted(set(records)):
                if (cache_id, record) not in existing:
                    spent[record] = spent.get(record, 0) + epsilon
                    if spent[record] > self.budget_micros:
                        _fail("budget_exceeded", "At least one stable protected unit would exceed its cumulative epsilon cap")
                    needed.append((cache_id, record, epsilon))
        return needed

    @staticmethod
    def _footprints(model):
        footprints = {model["cache_id"]: set(json.loads(model["records"]))}
        if model["serving_cache_id"] is not None:
            footprints.setdefault(model["serving_cache_id"], set()).update(json.loads(model["serving_records"]))
        return {key: sorted(value) for key, value in footprints.items()}

    def prepare(self, request_id, model_id, *, expected_revision, authority_id, now=None):
        request_id, model_id, authority_id = map(_key, (request_id, model_id, authority_id))
        expected_revision = _integer(expected_revision, "expected_revision")
        args = {"model_id": model_id, "expected_revision": expected_revision,
                "authority_id": authority_id}
        fingerprint = _hash(_json(args).encode())
        with self._transaction() as db:
            old = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    _fail("idempotency_conflict", "Request ID already binds different parameters")
                if old["revoked"]:
                    _fail("release_revoked", "Request has been revoked")
                result = json.loads(old["manifest"])
                self._live(db, model_id, authority_id, now)
                return result
            if self._revision(db) != expected_revision:
                _fail("revision_conflict", "Prepare against the current ledger revision")
            model, cache, dataset = self._live(db, model_id, authority_id, now)
            footprints = self._footprints(model)
            charged = sorted(set().union(*map(set, footprints.values())))
            serving = json.loads(model["serving_records"])
            needed = self._charge_plan(db, footprints)
            cache_evidence = {self._get(db, "caches", cache_id)["evidence"] for cache_id in footprints}
            manifest = {"schema": "temporal-assurance-v1", "request_id": request_id,
                "model_id": model_id, "authority_id": authority_id, "expected_revision": expected_revision,
                "scope_digest": self.scope_digest, "privacy_scope": "fixed_roster_attribute_dp",
                "budget_micros": self.budget_micros, "cache_id": cache["id"],
                "cache_digest": cache["cache_digest"], "epsilon_micros": cache["epsilon"],
                "dataset_digest": dataset["id"], "artifact_digest": model["artifact_digest"],
                "evidence_digests": sorted({model["evidence"], dataset["evidence"]} | cache_evidence),
                "attribute_version": dataset["attribute_version"],
                "training_units_digest": _hash(model["records"].encode()),
                "covered_units_digest": _hash(_json(charged).encode()), "covered_units": len(charged),
                "new_unit_charges": len(needed), "scoring": model["scoring"],
                "serving_cache_id": model["serving_cache_id"],
                "cache_footprints": [{"cache_id": key, "cache_digest": self._get(db, "caches", key)["cache_digest"],
                    "epsilon_micros": self._get(db, "caches", key)["epsilon"],
                    "units": len(value), "units_digest": _hash(_json(value).encode())}
                    for key, value in sorted(footprints.items())],
                "serving_units_digest": _hash(_json(serving).encode()), "serving_units": len(serving),
                "prepared_at": self._operation_time(now), "recipient_package_excludes_manifest": True}
            db.execute("INSERT INTO requests(id,fingerprint,manifest,charge_records) VALUES(?,?,?,?)",
                       (request_id, fingerprint, _json(manifest), _json(footprints)))
            self._live(db, model_id, authority_id, now, check_integrity=False)
            return manifest

    def _after_ledger_write(self, db):
        """Fault injection boundary for crash tests; never perform external I/O here."""

    def commit(self, request_id, *, now=None):
        with self._transaction() as db:
            request = self._get(db, "requests", _key(request_id))
            manifest = json.loads(request["manifest"])
            if request["revoked"]:
                _fail("release_revoked", "Request has been revoked")
            model, cache, _ = self._live(db, manifest["model_id"], manifest["authority_id"], now)
            if request["receipt"] is not None:
                return json.loads(request["receipt"])
            if self._revision(db) != manifest["expected_revision"]:
                _fail("revision_conflict", "Ledger changed after preparation; use a new request at the current revision")
            footprints = json.loads(request["charge_records"])
            needed = self._charge_plan(db, footprints)
            db.executemany("INSERT INTO charges(cache_id,record_id,epsilon,request_id) VALUES(?,?,?,?)",
                           [(cache_id, record, epsilon, request_id) for cache_id, record, epsilon in needed])
            self._after_ledger_write(db)
            revision = self._revision(db) + 1
            receipt = {"request_id": request_id, "model_id": model["id"], "revision": revision,
                "manifest_digest": _hash(request["manifest"].encode()), "artifact_digest": model["artifact_digest"],
                "committed_at": self._operation_time(now), "new_unit_charges": len(needed),
                "training_cache_epsilon_micros": cache["epsilon"], "cache_id": cache["id"],
                "charge_events": [{"cache_id": key,
                    "epsilon_micros": self._get(db, "caches", key)["epsilon"],
                    "new_unit_charges": sum(1 for event in needed if event[0] == key)} for key in sorted(footprints)],
                "scoring": manifest["scoring"], "privacy_scope": "fixed_roster_attribute_dp"}
            db.execute("UPDATE requests SET receipt=? WHERE id=?", (_json(receipt), request_id))
            db.execute("UPDATE meta SET value=? WHERE key='revision'", (str(revision),))
            self._live(db, manifest["model_id"], manifest["authority_id"], now, check_integrity=False)
            return receipt

    def download(self, request_id, *, authority_id, now=None):
        with self._transaction() as db:
            request = self._get(db, "requests", _key(request_id))
            manifest = json.loads(request["manifest"])
            if request["revoked"]:
                _fail("release_revoked", "Future downloads are revoked; past recipients retain their bytes")
            if not request["receipt"]:
                _fail("not_committed", "Prepared artifacts are not available for download")
            if _key(authority_id) != manifest["authority_id"]:
                _fail("authority_mismatch", "Download authority differs from the committed authorization")
            model, _, _ = self._live(db, manifest["model_id"], authority_id, now)
            if _hash(request["manifest"].encode()) != json.loads(request["receipt"])["manifest_digest"]:
                _fail("integrity_failure", "Committed manifest was changed")
            result = bytes(model["artifact"])
            self._live(db, manifest["model_id"], authority_id, now, check_integrity=False)
            return result

    def invalidate_evidence(self, evidence_digest):
        with self._transaction() as db:
            self._get(db, "evidence", _digest(evidence_digest))
            db.execute("UPDATE evidence SET invalidated=1 WHERE digest=?", (evidence_digest,))

    def revoke_authority(self, authority_id):
        with self._transaction() as db:
            self._get(db, "authorities", _key(authority_id))
            db.execute("UPDATE authorities SET revoked=1 WHERE id=?", (authority_id,))

    def revoke_release(self, request_id):
        with self._transaction() as db:
            self._get(db, "requests", _key(request_id))
            db.execute("UPDATE requests SET revoked=1 WHERE id=?", (request_id,))

    def ledger(self):
        """Private audit view; never automatically exported with a model."""
        with self._transaction() as db:
            spent = {}
            charges = [dict(r) for r in db.execute("SELECT * FROM charges ORDER BY record_id, cache_id")]
            for row in charges:
                spent[row["record_id"]] = spent.get(row["record_id"], 0) + row["epsilon"]
            return {"revision": self._revision(db), "budget_micros": self.budget_micros,
                    "scope_digest": self.scope_digest, "spent_micros": spent, "charges": charges,
                    "committed_releases": db.execute("SELECT COUNT(*) FROM requests WHERE receipt IS NOT NULL").fetchone()[0]}
