"""Append-only local fixture review workflow, never release authorization.

Current identity/role checks belong to the trusted service guard. This store
retains exact policy ordering, canonical-person independence, scoped delegation
and immutable evidence links. It does not protect against whole-store rollback.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from .contracts import (FLAGS, MAX_STATE_BYTES, ReviewError, canonical_bytes, digest, strict_json,
    owned, integer, identifier, hex_id, validate_digest, validate_case, validate_actor,
    validate_payload, completion_binding, meets_policy)

MAX_DATABASE_BYTES = 16 * 1024 * 1024
MAX_CASES = 32
MAX_CAMPAIGNS = 128
MAX_DELEGATIONS = 256
MAX_EVENTS = 2048
_DATABASE = "reviews.sqlite"
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT",
    "CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_sha256 TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL) STRICT",
)
_META = {"store_id", "event_count", "head_sha256", "last_clock"}
_REVIEW_ACTIONS = ("policy", "assess", "approve")
_REUSE_FIELDS = ("registration_id", "registration_sha256", "envelope_sha256", "admission_sha256", "context_sha256")


class StoreError(ReviewError):
    """Malformed local review request."""


class StoreConflict(StoreError):
    """A transition, immutable binding, independence or delegation conflicts."""


class StoreUnavailable(RuntimeError):
    """Current local review state, filesystem or clock is unavailable."""


def _unavailable():
    raise StoreUnavailable("Fixture review store unavailable")


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise StoreError("Review metadata rejected")


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
        raise StoreError("Review metadata is not canonical")
    return value


def _configuration(cases):
    if type(cases) is not list or not 1 <= len(cases) <= MAX_CASES:
        raise StoreError("Explicit bounded cases are required")
    cases = [validate_case(case) for case in cases]
    if len({case["case_id"] for case in cases}) != len(cases):
        raise StoreError("Case IDs must be unique")
    return sorted(cases, key=lambda case: case["case_id"])


def _blank():
    return {"cases": {}, "campaign_ids": set(), "delegation_ids": set(), "thresholds": {},
            "reuse": {key: set() for key in _REUSE_FIELDS}, "decisions": set(),
            "count": 0, "head": "0" * 64, "clock": 0}


def _project(case):
    return digest({key: case["case"][key] for key in ("agency_id", "project_id")})


def _decision(operation, payload, actor, now):
    body = {"operation": operation, "actor": actor, "recorded_at": now, "payload": payload}
    return {**body, "sha256": digest(body)}


class ReviewStore:
    def __init__(self, root, expected_store_id):
        hex_id(expected_store_id)
        self._store_id = expected_store_id
        try:
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE
            _directories(self.root)
            self._root_identity, self._db_identity = _identity(self.root.lstat()), _identity(self._path.lstat())
            with self._connect() as connection:
                connection.execute("BEGIN")
                try:
                    self._validate(connection)
                    self._paths()
                finally:
                    connection.rollback()
        except OSError:
            raise StoreUnavailable("Fixture review store unavailable") from None

    @property
    def root(self):
        return self._root

    @property
    def store_id(self):
        return self._store_id

    @classmethod
    def open(cls, root, expected_store_id):
        return cls(root, expected_store_id)

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
            store._root_identity, store._db_identity = _identity(root.lstat()), _identity(path.lstat())
            connection = sqlite3.connect(path, timeout=3., isolation_level=None)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA page_size=4096")
                connection.execute("PRAGMA max_page_count=4096")
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
            finally:
                connection.close()
            return store
        except (OSError, sqlite3.Error):
            raise StoreUnavailable("Fixture review creation unavailable") from None

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
            raise StoreUnavailable("Fixture review filesystem unavailable") from None

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
            raise StoreUnavailable("Fixture review database unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _clock(guard, floor):
        if not callable(guard):
            raise StoreError("A trusted current guard is required")
        now = guard()
        if type(now) is not int or not floor <= now <= 2 ** 53 - 1:
            raise StoreUnavailable("Review clock moved backwards or is invalid")
        return now

    @staticmethod
    def _meta(connection, key, value):
        connection.execute("UPDATE meta SET value=? WHERE key=?", (canonical_bytes(value).decode("ascii"), key))

    @staticmethod
    def _case(state, case_id):
        identifier(case_id)
        if case_id not in state["cases"]:
            raise StoreConflict("Review case is not configured")
        return state["cases"][case_id]

    @staticmethod
    def _independent(case, action, person):
        if person == case["case"]["submitter_person_id"] or person in case["operators"]:
            raise StoreConflict("Canonical review principal is not independent")
        for other in _REVIEW_ACTIONS:
            if other != action and person in case["review_people"][other]:
                raise StoreConflict("Canonical review roles must remain distinct")

    @staticmethod
    def _strong_enough(state, case, policy):
        floor, ceiling = state["thresholds"].get(_project(case), (0, 10000))
        if policy["utility_floor_bps"] < floor or policy["max_membership_auc_bps"] > ceiling:
            raise StoreConflict("Started project outcomes prevent policy weakening")

    @staticmethod
    def _campaign(case, campaign_id):
        hex_id(campaign_id)
        campaign = case["campaigns"].get(campaign_id)
        if campaign is None:
            raise StoreConflict("Campaign is outside the configured case")
        return campaign

    def _delegation(self, case, campaign, action, actor, delegation_id, now):
        if delegation_id is None:
            return None
        record = case["delegations"].get(delegation_id)
        if record is None or record["revoked"]:
            raise StoreConflict("Delegation is absent or revoked")
        payload = record["payload"]
        if (payload["campaign_id"] != campaign["policy"]["campaign_id"]
                or payload["policy_sha256"] != campaign["policy_sha256"]
                or payload["action"] != action or payload["delegate_person_id"] != actor["person_id"]
                or not record["recorded_at"] <= now < payload["expires_at"]):
            raise StoreConflict("Delegation does not cover this exact current action")
        self._independent(case, action, record["actor"]["person_id"])
        return payload["expires_at"]

    def _usable_decision(self, case, campaign, action, now):
        key = "policy_approval" if action == "policy" else "assessment"
        record = campaign[key]
        if record is None:
            raise StoreConflict("Required independent review is missing")
        return self._delegation(case, campaign, action, record["actor"], record["payload"]["delegation_id"], now)

    def _deadlines(self, case, operation, payload, actor, now):
        if operation in ("propose", "revoke", "fail"):
            return []
        campaign = self._campaign(case, payload["campaign_id"])
        deadlines = []
        if operation in _REVIEW_ACTIONS:
            deadlines.append(self._delegation(case, campaign, operation, actor, payload["delegation_id"], now))
        if operation in ("start", "complete", "assess", "approve"):
            deadlines.append(self._usable_decision(case, campaign, "policy", now))
        if operation == "approve":
            deadlines.append(self._usable_decision(case, campaign, "assess", now))
        if operation == "delegate":
            deadlines.append(payload["expires_at"])
        return [deadline for deadline in deadlines if deadline is not None]

    @staticmethod
    def _renew(campaign, action, payload):
        previous = campaign["_payloads"].get(action)
        if previous is not None:
            ignored = {"assessment_sha256"} if action == "approve" else set()
            if {k: v for k, v in previous.items() if k not in ignored} != {k: v for k, v in payload.items() if k not in ignored}:
                raise StoreConflict("Review renewal cannot alter its frozen payload")
        campaign["_payloads"][action] = payload

    def _transition(self, state, case, operation, payload, actor, now):
        person = actor["person_id"]
        duplicate = digest({"case_id": case["case"]["case_id"], "operation": operation, "payload": payload, "actor": actor})
        if duplicate in state["decisions"]:
            raise StoreConflict("Exact credential and decision replay rejected")
        record = _decision(operation, payload, actor, now)
        if operation == "propose":
            if (person != case["case"]["submitter_person_id"]
                    or any(payload[key] != case["case"][key] for key in ("agency_id", "project_id", "case_id"))):
                raise StoreConflict("Policy proposal differs from its configured owner or scope")
            if payload["campaign_id"] in state["campaign_ids"] or len(state["campaign_ids"]) >= MAX_CAMPAIGNS:
                raise StoreConflict("Campaign ID is permanent or capacity reached")
            self._strong_enough(state, case, payload)
            case["campaigns"][payload["campaign_id"]] = {"state": "proposed", "policy": payload,
                "policy_sha256": digest(payload), "policy_approval": None, "start": None, "completion": None,
                "binding_sha256": None, "assessment": None, "approval": None, "failure": None,
                "operators": [], "_payloads": {}}
            state["campaign_ids"].add(payload["campaign_id"])
        elif operation == "revoke":
            delegation = case["delegations"].get(payload["delegation_id"])
            if delegation is None or delegation["revoked"] or delegation["actor"]["person_id"] != person:
                raise StoreConflict("Only the original direct grantor can revoke an active delegation")
            delegation.update(revoked=True, revocation=record)
        else:
            campaign = self._campaign(case, payload["campaign_id"])
            if "policy_sha256" in payload and payload["policy_sha256"] != campaign["policy_sha256"]:
                raise StoreConflict("Campaign policy binding differs")
            self._deadlines(case, operation, payload, actor, now)
            if operation == "delegate":
                action = payload["action"]
                delegate = payload["delegate_person_id"]
                self._independent(case, action, person)
                self._independent(case, action, delegate)
                if (delegate == person or not now < payload["expires_at"] <= now + 300
                        or payload["delegation_id"] in state["delegation_ids"]
                        or len(state["delegation_ids"]) >= MAX_DELEGATIONS):
                    raise StoreConflict("Delegation is repeated, recursive, excessive or expired")
                if any(row["payload"]["campaign_id"] == payload["campaign_id"]
                       and row["payload"]["action"] == action and row["payload"]["delegate_person_id"] == person
                       for row in case["delegations"].values()):
                    raise StoreConflict("Delegation cannot be recursively regranted")
                case["delegations"][payload["delegation_id"]] = {**record, "revoked": False, "revocation": None}
                state["delegation_ids"].add(payload["delegation_id"])
                case["review_people"][action].update((person, delegate))
            elif operation == "policy":
                if campaign["state"] == "failed":
                    raise StoreConflict("Failed campaigns cannot regain approval")
                self._independent(case, operation, person)
                self._strong_enough(state, case, campaign["policy"])
                self._renew(campaign, operation, payload)
                campaign["policy_approval"] = record
                campaign["assessment"] = campaign["approval"] = None
                if campaign["state"] == "proposed":
                    campaign["state"] = "approved"
                case["review_people"][operation].add(person)
            elif operation == "start":
                if campaign["state"] != "approved" or campaign["start"] is not None:
                    raise StoreConflict("Campaign execution requires an unused policy approval")
                if person == case["case"]["submitter_person_id"] or any(person in people for people in case["review_people"].values()):
                    raise StoreConflict("Canonical operator is not independent of owner/review roles")
                self._strong_enough(state, case, campaign["policy"])
                policy = campaign["policy"]
                floor, ceiling = state["thresholds"].get(_project(case), (0, 10000))
                state["thresholds"][_project(case)] = (max(floor, policy["utility_floor_bps"]),
                    min(ceiling, policy["max_membership_auc_bps"]))
                campaign.update(state="started", start=record)
                campaign["operators"].append(person)
                case["operators"].add(person)
            elif operation in ("complete", "fail"):
                if campaign["state"] != "started" or campaign["start"]["actor"]["person_id"] != person:
                    raise StoreConflict("Only the recorded current execution can finish once")
                if operation == "fail":
                    campaign.update(state="failed", failure=record)
                else:
                    if any(payload[key] in state["reuse"][key] for key in _REUSE_FIELDS):
                        raise StoreConflict("Registration or consumed evidence was already used")
                    for key in _REUSE_FIELDS:
                        state["reuse"][key].add(payload[key])
                    campaign.update(state="completed", completion=record,
                        binding_sha256=completion_binding(campaign["policy"], payload))
            elif operation in ("assess", "approve"):
                if campaign["state"] != "completed" or payload["binding_sha256"] != campaign["binding_sha256"]:
                    raise StoreConflict("Review must bind the exact completed campaign")
                self._independent(case, operation, person)
                if operation == "assess":
                    if payload["verdict"] == "accept" and not meets_policy(campaign["policy"], campaign["completion"]["payload"]):
                        raise StoreConflict("Observed fixture result does not meet frozen policy")
                    self._renew(campaign, operation, payload)
                    campaign["assessment"], campaign["approval"] = record, None
                else:
                    assessment = campaign["assessment"]
                    if (assessment is None or assessment["sha256"] != payload["assessment_sha256"]
                            or assessment["payload"]["verdict"] != "accept"
                            or not meets_policy(campaign["policy"], campaign["completion"]["payload"])):
                        raise StoreConflict("Approval requires the exact current accepted assessment")
                    self._renew(campaign, operation, payload)
                    campaign["approval"] = record
                case["review_people"][operation].add(person)
            else:
                raise StoreError("Unknown fixture review operation")
        state["decisions"].add(duplicate)

    def _apply_event(self, state, event, event_hash):
        _exact(event, {"schema", "store_id", "sequence", "previous_sha256", "occurred_at", "operation", "case_id", "payload", "actor"})
        integer(event["sequence"], 1, MAX_EVENTS)
        integer(event["occurred_at"])
        if (event["schema"] != "mra-fixture-review-history/v1" or event["store_id"] != self.store_id
                or event["sequence"] != state["count"] + 1 or event["previous_sha256"] != state["head"]
                or event["occurred_at"] < state["clock"]):
            raise StoreConflict("Review history changed")
        operation = event["operation"]
        if operation == "created":
            _exact(event["payload"], {"cases"})
            cases = _configuration(event["payload"]["cases"])
            if state["count"] != 0 or event["case_id"] is not None or event["actor"] is not None or cases != event["payload"]["cases"]:
                raise StoreConflict("Review bootstrap cannot be replayed")
            for case in cases:
                state["cases"][case["case_id"]] = {"case": case, "campaigns": {}, "delegations": {},
                    "operators": set(), "review_people": {action: set() for action in _REVIEW_ACTIONS}}
        elif state["count"] == 0:
            raise StoreConflict("Review bootstrap is missing")
        else:
            case = self._case(state, event["case_id"])
            payload = validate_payload(operation, event["payload"])
            actor = validate_actor(event["actor"])
            self._transition(state, case, operation, payload, actor, event["occurred_at"])
        state.update(count=event["sequence"], head=event_hash, clock=event["occurred_at"])

    def _append(self, connection, state, operation, case_id, payload, actor, now):
        if state["count"] >= MAX_EVENTS:
            raise StoreConflict("Review history capacity reached")
        event = {"schema": "mra-fixture-review-history/v1", "store_id": self.store_id,
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
            rows = connection.execute("SELECT * FROM events ORDER BY sequence LIMIT ?", (MAX_EVENTS + 1,)).fetchall()
            if len(rows) != meta["event_count"]:
                _unavailable()
            state = _blank()
            for index, row in enumerate(rows, 1):
                event = _decode(row["event_json"].encode("ascii"))
                event_hash = digest(event)
                if row["sequence"] != index or row["event_sha256"] != event_hash:
                    _unavailable()
                self._apply_event(state, event, event_hash)
            if state["head"] != meta["head_sha256"] or state["clock"] > meta["last_clock"]:
                _unavailable()
            state["clock"] = meta["last_clock"]
            return state
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            raise StoreUnavailable("Fixture review state validation failed") from None

    @contextmanager
    def _transaction(self, guard):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                state = self._validate(connection)
                now = self._clock(guard, state["clock"])
                deadlines = []
                yield connection, state, now, deadlines
                current = self._validate(connection)
                if (current["count"], current["head"]) != (state["count"], state["head"]):
                    raise StoreConflict("Review history changed before commit")
                final = self._clock(guard, max(now, current["clock"]))
                if any(final >= deadline for deadline in deadlines):
                    raise StoreConflict("Delegation expired before commit")
                self._meta(connection, "last_clock", final)
                self._paths()
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _snapshot(self, state, case):
        campaigns = {key: {name: value for name, value in row.items() if not name.startswith("_")}
                     for key, row in sorted(case["campaigns"].items())}
        return owned({"schema": "mra-fixture-review-case/v1", "store_id": self.store_id,
            "case": case["case"], "campaigns": campaigns, "delegations": case["delegations"],
            "operators": sorted(case["operators"]), "event_count": state["count"], "head_sha256": state["head"],
            **FLAGS}, max_bytes=MAX_STATE_BYTES)

    def apply(self, case_id, operation, payload, actor, *, guard, expected_head_sha256=None):
        payload, actor = validate_payload(operation, payload), validate_actor(actor)
        if expected_head_sha256 is not None:
            validate_digest(expected_head_sha256)
        with self._transaction(guard) as (connection, state, now, deadlines):
            if expected_head_sha256 is not None and state["head"] != expected_head_sha256:
                raise StoreConflict("Review state changed after authority was captured")
            case = self._case(state, case_id)
            deadlines.extend(self._deadlines(case, operation, payload, actor, now))
            self._append(connection, state, operation, case_id, payload, actor, now)
            result = self._snapshot(state, case)
        return result

    def get(self, case_id, *, guard):
        with self._transaction(guard) as (_, state, _, _):
            result = self._snapshot(state, self._case(state, case_id))
        return result

    def inspect(self, *, guard):
        with self._transaction(guard) as (_, state, _, _):
            result = owned({"schema": "mra-fixture-review-inspection/v1", "store_id": self.store_id,
                "cases": {key: self._snapshot(state, case) for key, case in sorted(state["cases"].items())},
                "event_count": state["count"], "head_sha256": state["head"], **FLAGS}, max_bytes=MAX_STATE_BYTES)
        return result
