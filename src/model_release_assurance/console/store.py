"""Single-host SQLite queue; atomic claims and persisted, bounded job results."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .. import workflow
from .options import LanguageOptions, TrainingOptions


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("invalid identifier")
    return value


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases = self.root / "cases"
        self.cases.mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                    route TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, case_id TEXT,
                    state TEXT NOT NULL, created REAL NOT NULL, started REAL,
                    finished REAL, worker TEXT, heartbeat REAL,
                    result TEXT, error TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS active_case_job ON jobs(case_id)
                    WHERE state IN ('queued','running') AND case_id IS NOT NULL;
                CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, heartbeat REAL NOT NULL);
            """)

            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            for column in ("options", "progress", "retry_of"):
                if column not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "console.sqlite3", timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def case_path(self, case_id: str) -> Path:
        path = (self.cases / safe_id(case_id)).resolve()
        if path.parent != self.cases.resolve():
            raise ValueError("case path escapes the case store")
        return path

    def create_case(self, name: str, kind: str, route: str, mode: workflow.Mode = "education") -> dict:
        case_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] >= 500:
                raise ValueError("local case limit reached (500)")
            workflow.initialize(self.case_path(case_id), kind, route, mode)
            db.execute("INSERT INTO cases VALUES (?,?,?,?,?)", (case_id, name, kind, route, time.time()))
        return self.case(case_id)

    def edit_case(self, case_id: str, *, mode=None, slot=None, path=None) -> dict:
        self.case(case_id)
        root = self.case_path(case_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE case_id=? AND state IN ('queued','running')", (case_id,)).fetchone():
                raise ValueError("wait for this case's queued or running job before editing")
            project = workflow.load_project(root)
            if mode is not None:
                updated = project.model_dump()
                updated["mode"] = mode
                project = workflow.Project.model_validate(updated)
                workflow.write_json(root / "project.json", project.model_dump(), replace=True)
            else:
                if path is None or not Path(path).is_absolute():
                    raise ValueError("provide an absolute path on the console computer")
                try:
                    workflow.bind(root, slot, Path(path))
                except OSError as exc:
                    raise ValueError("local file is unavailable or unreadable") from exc
        return {"status": "updated", "mode": project.mode}

    def case(self, case_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM cases WHERE id=?", (safe_id(case_id),)).fetchone()
        if row is None:
            raise KeyError("case not found")
        return dict(row)

    def list_cases(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM cases ORDER BY created DESC LIMIT 500")]

    def enqueue(self, kind: str, case_id: str | None = None, options: dict | None = None, *, retry_of: str | None = None) -> dict:
        if kind not in {"reference", "training", "check", "assess", "language"}:
            raise ValueError("unsupported job type")
        if kind in {"check", "assess"}:
            if case_id is None:
                raise ValueError("case required")
            self.case(case_id)
        elif case_id is not None:
            raise ValueError("demo jobs do not target agency cases")
        if options is not None and kind not in {"training", "language"}:
            raise ValueError("training options require a training job")
        if kind == "training":
            options = TrainingOptions.model_validate(options or {}).model_dump()
        elif kind == "language":
            options = LanguageOptions.model_validate(options or {}).model_dump()
        job_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= 20:
                raise ValueError("local queue is full (20 active jobs)")
            try:
                db.execute("INSERT INTO jobs(id,kind,case_id,state,created,options,retry_of) VALUES (?,?,?,'queued',?,?,?)",
                           (job_id, kind, case_id, time.time(), json.dumps(options) if options else None, retry_of))
            except sqlite3.IntegrityError as exc:
                raise ValueError("this case already has a queued or running job") from exc
        return self.job(job_id)

    def cancel(self, job_id: str) -> dict:
        """Only a still-queued job can be cancelled; never race a claimed worker."""
        self.job(job_id)
        with self.connect() as db:
            changed = db.execute("UPDATE jobs SET state='cancelled',finished=?,progress=? WHERE id=? AND state='queued'",
                                 (time.time(), "Cancelled before execution", job_id)).rowcount
            if not changed:
                raise ValueError("only queued jobs can be cancelled")
        return self.job(job_id)

    def retry(self, job_id: str) -> dict:
        """A deliberate new attempt preserves the failed attempt and original options."""
        previous = self.job(job_id)
        if previous["state"] not in {"failed", "cancelled"}:
            raise ValueError("only failed or cancelled jobs can be retried")
        return self.enqueue(previous["kind"], previous["case_id"], previous["options"], retry_of=job_id)

    @staticmethod
    def decode(row) -> dict:
        result = dict(row)
        for field in ("result", "options"):
            result[field] = json.loads(result[field]) if result[field] else None
        return result

    def job(self, job_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (safe_id(job_id),)).fetchone()
        if row is None:
            raise KeyError("job not found")
        return self.decode(row)

    def list_jobs(self) -> list[dict]:
        with self.connect() as db:
            return [self.decode(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 100")]

    def heartbeat(self, worker: str):
        with self.connect() as db:
            now = time.time()
            db.execute("INSERT INTO workers VALUES (?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat", (worker, now))
            db.execute("UPDATE jobs SET heartbeat=? WHERE worker=? AND state='running'", (now, worker))

    def recover(self, stale_seconds=90):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='failed',finished=?,error=? WHERE state='running' AND COALESCE(heartbeat,started,created)<?",
                       (time.time(), "Worker heartbeat expired. Partial artifacts retained; submit a new job after reviewing them.", time.time() - stale_seconds))

    def claim(self, worker: str) -> dict | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            now = time.time()
            db.execute("UPDATE jobs SET state='running',started=?,worker=?,heartbeat=? WHERE id=?", (now, worker, now, row["id"]))
        return self.job(row["id"])

    def progress(self, job: dict, stage: str):
        with self.connect() as db:
            db.execute("UPDATE jobs SET progress=? WHERE id=? AND worker=? AND state='running'",
                       (stage, job["id"], job["worker"]))

    def finish(self, job_id: str, worker: str, result: dict | None = None, error: str | None = None):
        encoded = json.dumps(result, allow_nan=False) if result is not None else None
        if encoded and len(encoded) > 2_000_000:
            raise ValueError("console result exceeds local result limit")
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?,finished=?,result=?,error=? WHERE id=? AND worker=? AND state='running'",
                       ("failed" if error else "completed", time.time(), encoded, error,
                        safe_id(job_id), worker))

    def status(self) -> dict:
        with self.connect() as db:
            online = db.execute("SELECT COUNT(*) FROM workers WHERE heartbeat>?", (time.time() - 30,)).fetchone()[0]
            counts = {r["state"]: r["n"] for r in db.execute("SELECT state,COUNT(*) AS n FROM jobs GROUP BY state")}
        return {"worker_online": online > 0, "workers_online": online, "jobs": counts,
                "authorization_eligible": False, "mode": "trusted-local-pre-poc"}
