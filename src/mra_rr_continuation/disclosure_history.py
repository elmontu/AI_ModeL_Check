"""Shared public-synthetic disclosure history with durable local custody checks.

This bounded SQLite fixture supports one retained RR initialization and one
certified continuation. Its separate unsigned witness directory detects a stale
or changed ledger while that witness survives. It is not an independently
administered agency service, privacy accountant, or model-release authority.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Any
from uuid import uuid4

from .certificates import RRParameters, SOURCE_PDF_SHA256

SCHEMA = "mra-rr-shared-history/1.0"
ZERO = "0" * 64
MAX_EVENTS = 4096
MAX_HISTORIES = 512
MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
_INITIALIZATION_WAIT = 5.0
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[a-f0-9]{32}\Z")
INPUT_NAMES = (
    "synthetic-labels.json", "retained-law.json", "retained-responses.json",
    "history.json", "request-plan.json", "plan.json", "certificate.json",
)
OUTPUT_NAMES = ("randomized-block.json", "sample-reservation.json", "sampling-completion.json")
AUTHORITY = {
    "authorization_effect": "none", "production_execution_qualified": False,
    "authoritative_agency_history": False, "independent_custody_verified": False,
    "privacy_accounting_supported": False,
}
_TABLES = {
    "metadata": "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "events": "CREATE TABLE events (seq INTEGER PRIMARY KEY, body TEXT NOT NULL, sha256 TEXT NOT NULL)",
    "histories": "CREATE TABLE histories (history_id TEXT PRIMARY KEY, body TEXT NOT NULL)",
}
_BINDING_KEYS = {
    "preset", "source_pdf_sha256", "retained_law_sha256", "retained_response_sha256",
    "complete_history_sha256", "request_plan_sha256", "certificate_sha256",
    "labels_sha256", "source_input_sha256", "runtime_sha256",
}


class HistoryError(ValueError):
    """Invalid or uncertain research history; informative execution is blocked."""
    status_code = 409


def canonical_bytes(value: Any) -> bytes:
    try:
        data = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise HistoryError("History requires bounded canonical JSON") from exc
    if len(data) > 128 * 1024:
        raise HistoryError("History record exceeds its size limit")
    return data


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _keys(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise HistoryError(f"Invalid {name} fields")
    canonical_bytes(value)
    return value


def _id(value: Any, name: str = "identity") -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise HistoryError(f"Invalid {name}")
    return value


def _sha(value: Any) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise HistoryError("History requires a lowercase SHA-256 digest")
    return value


def _safe(path: Path) -> None:
    for entry in reversed((path, *path.parents)):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise HistoryError("History paths must not contain symlinks or reparse points")


def _read(path: Path, limit: int = MAX_ARTIFACT_BYTES) -> bytes:
    _safe(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise HistoryError("History files must be regular files")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise HistoryError("History file changed during access")
        data = stream.read(limit + 1)
    _safe(path)
    current = path.lstat()
    if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
        raise HistoryError("History file was replaced during access")
    if len(data) > limit:
        raise HistoryError("History file exceeds its size limit")
    return data


def _write(path: Path, value: Any) -> None:
    _safe(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def _load(path: Path) -> dict[str, Any]:
    raw = _read(path, 128 * 1024)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise HistoryError("History JSON is invalid") from exc
    if canonical_bytes(value) != raw or type(value) is not dict:
        raise HistoryError("History JSON bytes are not canonical")
    return value


def _registration(value: Any) -> dict[str, Any]:
    value = _keys(value, {"public_synthetic", "preset", "source_pdf_sha256", "labels_sha256", "request_plan_sha256", "parameters"}, "public registration")
    if value["public_synthetic"] is not True or value["preset"] not in ("optimal", "infeasible", "uniform"):
        raise HistoryError("Only fixed public synthetic presets may enroll")
    if value["source_pdf_sha256"] != SOURCE_PDF_SHA256:
        raise HistoryError("History requires the reviewed research source")
    for name in ("source_pdf_sha256", "labels_sha256", "request_plan_sha256"):
        _sha(value[name])
    try:
        parameters = RRParameters.from_dict(value["parameters"])
    except ValueError as exc:
        raise HistoryError("History parameters are invalid") from exc
    expected = {
        "optimal": {"r": 2, "d": "3/1", "L": "9/1", "tau": "2/3"},
        "infeasible": {"r": 2, "d": "3/1", "L": "9/1", "tau": "3/4"},
        "uniform": {"r": 2, "d": "1/1", "L": "1/1", "tau": "1/2"},
    }[value["preset"]]
    if parameters.to_dict() != expected or canonical_bytes(value["parameters"]) != canonical_bytes(expected):
        raise HistoryError("History requires the fixed preset parameters")
    return value


def _bindings(value: Any, registration: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, _BINDING_KEYS, "retained bindings")
    for name in _BINDING_KEYS - {"preset", "source_input_sha256"}:
        _sha(value[name])
    inputs = _keys(value["source_input_sha256"], set(INPUT_NAMES), "source input hashes")
    for digest in inputs.values():
        _sha(digest)
    for name in ("preset", "source_pdf_sha256", "labels_sha256", "request_plan_sha256"):
        if value[name] != registration[name]:
            raise HistoryError("Retained history differs from its pre-draw registration")
    for artifact, field in (
        ("synthetic-labels.json", "labels_sha256"), ("retained-law.json", "retained_law_sha256"),
        ("retained-responses.json", "retained_response_sha256"), ("history.json", "complete_history_sha256"),
        ("request-plan.json", "request_plan_sha256"),
    ):
        if inputs[artifact] != value[field]:
            raise HistoryError("Source input bindings disagree")
    return value


def _reservation_bindings(value: Any, retained: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"retained", "public_request", "certificate_sha256"}, "reservation bindings")
    if canonical_bytes(value["retained"]) != canonical_bytes(retained) or value["certificate_sha256"] != retained["certificate_sha256"]:
        raise HistoryError("Reservation does not bind the exact retained history and certificate")
    request = _keys(value["public_request"], {"request_plan_sha256", "recipient_scope", "informative_extension"}, "public request")
    if (request["request_plan_sha256"] != retained["request_plan_sha256"] or type(request["recipient_scope"]) is not str
            or not 1 <= len(request["recipient_scope"]) <= 128 or type(request["informative_extension"]) is not int
            or request["informative_extension"] != 1):
        raise HistoryError("Only one bounded public continuation request is supported")
    return value


def _output_path(value: Any) -> str:
    if type(value) is not str or len(value) > 2048 or not Path(value).is_absolute() or Path(value).name != "randomized-block.json":
        raise HistoryError("An absolute canonical block output path is required")
    path = Path(value)
    if str(path.absolute()) != value or ".." in path.parts:
        raise HistoryError("Output path is not canonical")
    _safe(path)
    return value


def _artifacts(value: Any, output_path: str, *, check_files: bool) -> dict[str, Any]:
    value = _keys(value, set(OUTPUT_NAMES), "committed artifacts")
    directory = Path(output_path).parent
    for name, pin in value.items():
        _keys(pin, {"path", "sha256"}, "artifact pin")
        _sha(pin["sha256"])
        if type(pin["path"]) is not str or pin["path"] != str(directory / name):
            raise HistoryError("Artifacts must be bound to the reserved canonical directory")
        if check_files and hashlib.sha256(_read(Path(pin["path"]))).hexdigest() != pin["sha256"]:
            raise HistoryError("Committed artifact bytes differ from their retained pin")
    return value


def _pinned_inputs(state: dict[str, Any], directory: Path) -> None:
    for name, expected in state["retained_bindings"]["source_input_sha256"].items():
        if hashlib.sha256(_read(directory / name)).hexdigest() != expected:
            raise HistoryError("Canonical retained input bytes differ from the shared history pin")


class HistoryLedger:
    """Bounded shared ledger; every admission replays both retained custody stores."""

    def __init__(self, root: str | Path, witness_root: str | Path):
        self.root = Path(root).absolute()
        self.witness_root = Path(witness_root).absolute()
        if self.root == self.witness_root or self.root in self.witness_root.parents or self.witness_root in self.root.parents:
            raise HistoryError("Ledger and local witness require separate sibling custody paths")
        for directory in (self.root, self.witness_root):
            _safe(directory)
            directory.mkdir(parents=True, exist_ok=True)
            _safe(directory)
            if not directory.is_dir():
                raise HistoryError("History storage must be directories")
        self.database = self.root / "history.sqlite3"
        self.bootstrap = self.root / "bootstrap.json"
        self.initialized = self.root / "initialized.json"
        self.anchor = self.witness_root / "ledger.json"
        try:
            if not self.bootstrap.exists():
                if self.database.exists() or any(self.witness_root.iterdir()):
                    if not self.bootstrap.exists():
                        raise HistoryError("Existing custody evidence cannot be reset or adopted")
                else:
                    identity = {"schema": SCHEMA, "ledger_id": uuid4().hex}
                    try:
                        _write(self.bootstrap, identity)
                    except FileExistsError:
                        pass
                    else:
                        self._initialize(identity)
            deadline = time.monotonic() + _INITIALIZATION_WAIT
            while not self.initialized.exists() and time.monotonic() < deadline:
                time.sleep(0.025)
            if not self.initialized.exists():
                raise HistoryError("History bootstrap is incomplete; it cannot be retried or reset")
            identity = _load(self.bootstrap)
            _keys(identity, {"schema", "ledger_id"}, "ledger bootstrap")
            _id(identity["ledger_id"], "ledger identity")
            if identity["schema"] != SCHEMA or _load(self.initialized) != identity or _load(self.anchor) != identity:
                raise HistoryError("Ledger bootstrap and local custody anchor disagree")
            self.ledger_id = identity["ledger_id"]
            with closing(self._connection()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate(connection)
                connection.rollback()
        except (OSError, sqlite3.Error, ValueError) as exc:
            if isinstance(exc, HistoryError):
                raise
            raise HistoryError("History storage is unavailable or invalid; execution is blocked") from exc

    def _initialize(self, identity: dict[str, Any]) -> None:
        _write(self.anchor, identity)
        _safe(self.database)
        # Claim the DB pathname exclusively so a replacement is never adopted.
        descriptor = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(self.database, timeout=30)) as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            for definition in _TABLES.values():
                connection.execute(definition)
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", (("schema", SCHEMA), ("ledger_id", identity["ledger_id"])))
            connection.commit()
        pending = self.root / "initialized.pending.json"
        _write(pending, identity)
        _safe(self.initialized)
        os.rename(pending, self.initialized)

    def _connection(self) -> sqlite3.Connection:
        _safe(self.root)
        _safe(self.witness_root)
        _safe(self.database)
        if not self.database.is_file() or self.database.stat().st_size > MAX_DATABASE_BYTES:
            raise HistoryError("History database is missing or exceeds its size limit")
        connection = sqlite3.connect(f"file:{self.database.as_posix()}?mode=rw", uri=True, timeout=30, isolation_level=None)
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            connection.close()
            raise HistoryError("History database requires the fixed rollback-journal mode")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection

    def _apply(self, states: dict[str, Any], event: dict[str, Any], digest: str) -> None:
        _keys(event, {"schema", "ledger_id", "seq", "previous_sha256", "history_id", "history_revision", "history_previous_sha256", "action", "at", "payload"}, "history event")
        identity = _id(event["history_id"], "history identity")
        state = states.get(identity)
        revision = 1 if state is None else state["revision"] + 1
        predecessor = ZERO if state is None else state["head_sha256"]
        if (event["schema"] != SCHEMA or event["ledger_id"] != self.ledger_id
                or type(event["history_revision"]) is not int or event["history_revision"] != revision
                or event["history_previous_sha256"] != predecessor or type(event["at"]) is not str):
            raise HistoryError("History event predecessor is invalid")
        try:
            parsed = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise HistoryError("History timestamp is invalid") from exc
        payload = event["payload"]
        action = event["action"]
        if action == "create":
            _keys(payload, {"owner_run_id", "registration"}, "creation event")
            if state is not None or len(states) >= MAX_HISTORIES:
                raise HistoryError("History creation is duplicate or exceeds the bound")
            owner = _id(payload["owner_run_id"], "run identity")
            if any(owner in old["run_ids"] for old in states.values()):
                raise HistoryError("A run alias cannot reset disclosure history")
            state = {
                "history_id": identity, "owner_run_id": owner, "run_ids": [owner],
                "state": "initialization_reserved", "registration": _registration(payload["registration"]),
                "retained_bindings": None, "reservation": None, "created_at": event["at"], **AUTHORITY,
            }
        elif state is None:
            raise HistoryError("History event refers to an unregistered source")
        elif action == "bind_retained":
            _keys(payload, {"run_id", "bindings"}, "retained binding event")
            if state["state"] != "initialization_reserved" or payload["run_id"] != state["owner_run_id"]:
                raise HistoryError("Retained initialization cannot be repeated")
            state["retained_bindings"] = _bindings(payload["bindings"], state["registration"])
            state["state"] = "ready"
        elif action == "alias":
            _keys(payload, {"run_id"}, "alias event")
            run_id = _id(payload["run_id"], "alias run identity")
            if state["state"] not in ("ready", "committed") or any(run_id in old["run_ids"] for old in states.values()):
                raise HistoryError("An incomplete or existing run cannot be aliased")
            if len(state["run_ids"]) >= 128:
                raise HistoryError("History alias bound exceeded")
            state["run_ids"].append(run_id)
        elif action == "reserve":
            _keys(payload, {"reservation_id", "run_id", "request_id", "bindings", "output_path"}, "reservation event")
            if state["state"] != "ready" or payload["run_id"] not in state["run_ids"]:
                raise HistoryError("Only one continuation may be reserved for a registered history")
            bindings = _reservation_bindings(payload["bindings"], state["retained_bindings"])
            if _sha(payload["request_id"]) != _digest(bindings):
                raise HistoryError("Request identity must bind the complete public request")
            reservation = {
                "reservation_id": _id(payload["reservation_id"], "reservation identity"),
                "run_id": payload["run_id"], "request_id": payload["request_id"],
                "bindings": bindings, "output_path": _output_path(payload["output_path"]),
                "reserved_at": event["at"], "artifacts": None,
            }
            state["reservation"] = reservation
            state["state"] = "reserved_incomplete"
        elif action == "commit":
            _keys(payload, {"reservation_id", "artifacts"}, "commit event")
            if state["state"] != "reserved_incomplete" or payload["reservation_id"] != state["reservation"]["reservation_id"]:
                raise HistoryError("Commit requires the original incomplete reservation")
            state["reservation"]["artifacts"] = _artifacts(payload["artifacts"], state["reservation"]["output_path"], check_files=False)
            state["reservation"]["committed_at"] = event["at"]
            state["state"] = "committed"
        else:
            raise HistoryError("Unsupported history transition")
        state["revision"] = revision
        state["head_sha256"] = digest
        state["head"] = digest
        states[identity] = state

    def _validate(self, connection: sqlite3.Connection) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        identity = {"schema": SCHEMA, "ledger_id": self.ledger_id}
        if any(_load(path) != identity for path in (self.bootstrap, self.initialized, self.anchor)):
            raise HistoryError("History custody identities changed")
        definitions = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        if definitions != _TABLES or connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger','view') OR (type='index' AND name NOT LIKE 'sqlite_autoindex_%')").fetchone()[0]:
            raise HistoryError("History database schema differs from the fixed definition")
        if dict(connection.execute("SELECT name,value FROM metadata")) != identity:
            raise HistoryError("History metadata differs from its local custody anchor")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise HistoryError("History database integrity check failed")
        count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if count > MAX_EVENTS or connection.execute("SELECT COUNT(*) FROM histories").fetchone()[0] > MAX_HISTORIES:
            raise HistoryError("History replay bounds exceeded")
        states: dict[str, Any] = {}
        events = []
        predecessor = ZERO
        witness_names = {"ledger.json"}
        previous_at = ""
        for expected_seq, (seq, body, digest) in enumerate(connection.execute("SELECT seq,body,sha256 FROM events ORDER BY seq"), 1):
            if type(seq) is not int or seq != expected_seq or type(body) is not str or len(body.encode("utf-8")) > 128 * 1024:
                raise HistoryError("History event order or bounds are invalid")
            try:
                event = json.loads(body)
            except ValueError as exc:
                raise HistoryError("History event is invalid JSON") from exc
            if (type(event) is not dict or canonical_bytes(event).decode("utf-8") != body or _digest(event) != _sha(digest)
                    or type(event.get("seq")) is not int or event["seq"] != seq or event.get("previous_sha256") != predecessor
                    or type(event.get("at")) is not str or event["at"] < previous_at):
                raise HistoryError("History canonical event chain differs")
            name = f"{seq:08d}-{digest}.json"
            if _read(self.witness_root / name, 128 * 1024) != body.encode("utf-8"):
                raise HistoryError("Ledger event differs from its irreversible local witness")
            witness_names.add(name)
            self._apply(states, event, digest)
            events.append(event)
            predecessor = digest
            previous_at = event["at"]
        if {path.name for path in self.witness_root.iterdir()} != witness_names:
            raise HistoryError("Local witness is ahead, missing, or divergent; outcome is uncertain")
        projection = dict(connection.execute("SELECT history_id,body FROM histories"))
        if projection != {identity: canonical_bytes(state).decode("utf-8") for identity, state in states.items()}:
            raise HistoryError("History materialized state differs from complete replay")
        for state in states.values():
            if state["state"] in ("reserved_incomplete", "committed"):
                _pinned_inputs(state, Path(state["reservation"]["output_path"]).parent)
            if state["state"] == "committed":
                _artifacts(state["reservation"]["artifacts"], state["reservation"]["output_path"], check_files=True)
        return states, events

    def _after_checkpoint(self, event: dict[str, Any]) -> None:
        """Crash-test seam after irreversible intent, before SQLite commit."""

    def _after_commit(self, event: dict[str, Any]) -> None:
        """Crash-test seam after commit, before the caller receives a result."""

    def _operation(self, function: Any) -> Any:
        try:
            with closing(self._connection()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                states, events = self._validate(connection)
                result = function(connection, states, events)
                connection.rollback()
                return result
        except (OSError, sqlite3.Error, ValueError) as exc:
            if isinstance(exc, HistoryError):
                raise
            raise HistoryError("History custody is unavailable or invalid; execution is blocked") from exc

    def _append(self, connection: sqlite3.Connection, states: dict[str, Any], events: list[dict[str, Any]], history_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if len(events) >= MAX_EVENTS:
            raise HistoryError("History event bound exceeded")
        state = states.get(history_id)
        at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if events and at < events[-1]["at"]:
            raise HistoryError("History clock moved backwards")
        event = {
            "schema": SCHEMA, "ledger_id": self.ledger_id, "seq": len(events) + 1,
            "previous_sha256": ZERO if not events else _digest(events[-1]),
            "history_id": history_id, "history_revision": 1 if state is None else state["revision"] + 1,
            "history_previous_sha256": ZERO if state is None else state["head_sha256"],
            "action": action, "at": at, "payload": json.loads(canonical_bytes(payload)),
        }
        digest = _digest(event)
        self._apply(states, event, digest)
        result = states[history_id]
        connection.execute("INSERT INTO events VALUES (?,?,?)", (event["seq"], canonical_bytes(event).decode("utf-8"), digest))
        connection.execute("INSERT OR REPLACE INTO histories VALUES (?,?)", (history_id, canonical_bytes(result).decode("utf-8")))
        _write(self.witness_root / f"{event['seq']:08d}-{digest}.json", event)
        self._after_checkpoint(event)
        connection.commit()
        self._after_commit(event)
        return json.loads(canonical_bytes(result))

    @staticmethod
    def _predecessor(state: dict[str, Any], revision: Any, head: Any) -> None:
        if type(revision) is not int or revision != state["revision"] or _sha(head) != state["head_sha256"]:
            raise HistoryError("The shared history predecessor is stale; reload its retained state")

    def create_history(self, run_id: str, registration: dict[str, Any]) -> dict[str, Any]:
        _id(run_id, "run identity")
        _registration(registration)
        history_id = uuid4().hex
        return self._operation(lambda connection, states, events: self._append(connection, states, events, history_id, "create", {"owner_run_id": run_id, "registration": registration}))

    def bind_retained(self, history_id: str, run_id: str, expected_revision: int, expected_head: str, bindings: dict[str, Any]) -> dict[str, Any]:
        def operation(connection, states, events):
            state = self._find(states, history_id)
            self._predecessor(state, expected_revision, expected_head)
            _bindings(bindings, state["registration"])
            return self._append(connection, states, events, history_id, "bind_retained", {"run_id": run_id, "bindings": bindings})
        return self._operation(operation)

    def attach_alias(self, history_id: str, run_id: str, expected_revision: int, expected_head: str) -> dict[str, Any]:
        _id(run_id, "run alias")
        def operation(connection, states, events):
            state = self._find(states, history_id)
            self._predecessor(state, expected_revision, expected_head)
            return self._append(connection, states, events, history_id, "alias", {"run_id": run_id})
        return self._operation(operation)

    @staticmethod
    def _find(states: dict[str, Any], history_id: str) -> dict[str, Any]:
        _id(history_id, "history identity")
        if history_id not in states:
            raise HistoryError("Disclosure history is not registered")
        return states[history_id]

    def snapshot(self, history_id: str) -> dict[str, Any]:
        return self._operation(lambda connection, states, events: json.loads(canonical_bytes(self._find(states, history_id))))

    def history_for_run(self, run_id: str) -> dict[str, Any] | None:
        _id(run_id, "run identity")
        def operation(connection, states, events):
            found = next((state for state in states.values() if run_id in state["run_ids"]), None)
            return None if found is None else json.loads(canonical_bytes(found))
        return self._operation(operation)

    def histories(self) -> list[dict[str, Any]]:
        return self._operation(lambda connection, states, events: json.loads(canonical_bytes(list(states.values()))))

    def reserve(self, history_id: str, run_id: str, expected_revision: int, expected_head: str, request_id: str, bindings: dict[str, Any], output_path: str) -> dict[str, Any]:
        _id(run_id, "run identity")
        _sha(request_id)
        if type(expected_revision) is not int or not 1 <= expected_revision <= MAX_EVENTS:
            raise HistoryError("A bounded integer history predecessor revision is required")
        _sha(expected_head)
        output_path = _output_path(output_path)
        def operation(connection, states, events):
            state = self._find(states, history_id)
            if run_id not in state["run_ids"]:
                raise HistoryError("This run is not an alias of the registered history")
            if state["retained_bindings"] is None:
                raise HistoryError("Retained initialization is incomplete; another draw is refused")
            _reservation_bindings(bindings, state["retained_bindings"])
            if request_id != _digest(bindings):
                raise HistoryError("Request identity differs from its exact bindings")
            if state["state"] == "committed":
                reserved = state["reservation"]
                if (reserved["request_id"] == request_id and canonical_bytes(reserved["bindings"]) == canonical_bytes(bindings)
                        and reserved["output_path"] == output_path):
                    return {"snapshot": json.loads(canonical_bytes(state)), "reservation": json.loads(canonical_bytes(reserved)), "replayed": True}
                raise HistoryError("A changed public or recipient request cannot spend this history again")
            self._predecessor(state, expected_revision, expected_head)
            if state["state"] != "ready":
                raise HistoryError("Disclosure history has an incomplete reservation; another draw is refused")
            _safe(Path(output_path))
            _pinned_inputs(state, Path(output_path).parent)
            if Path(output_path).exists():
                raise HistoryError("The canonical output already exists without a committed reservation")
            result = self._append(connection, states, events, history_id, "reserve", {
                "reservation_id": uuid4().hex, "run_id": run_id, "request_id": request_id,
                "bindings": bindings, "output_path": output_path,
            })
            return {"snapshot": result, "reservation": result["reservation"], "replayed": False}
        return self._operation(operation)

    def commit(self, history_id: str, reservation_id: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        _id(reservation_id, "reservation identity")
        def operation(connection, states, events):
            state = self._find(states, history_id)
            if state["reservation"] is None or state["reservation"]["reservation_id"] != reservation_id:
                raise HistoryError("Commit does not match the original reserved intent")
            _artifacts(artifacts, state["reservation"]["output_path"], check_files=True)
            if state["state"] == "committed":
                if canonical_bytes(state["reservation"]["artifacts"]) != canonical_bytes(artifacts):
                    raise HistoryError("Committed output pins cannot be changed")
                return json.loads(canonical_bytes(state))
            return self._append(connection, states, events, history_id, "commit", {"reservation_id": reservation_id, "artifacts": artifacts})
        return self._operation(operation)

    def export(self, history_id: str) -> bytes:
        def operation(connection, states, events):
            state = self._find(states, history_id)
            return canonical_bytes({
                "schema": SCHEMA, "ledger_id": self.ledger_id, "history": state,
                "events": [event for event in events if event["history_id"] == history_id],
                "custody_scope": "separate unsigned local directories; coordinated rollback remains outside this fixture",
                "joint_law_accounting": "one retained RR law plus one certified continuation; no additive epsilon subtraction",
                **AUTHORITY,
            })
        return self._operation(operation)



