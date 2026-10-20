"""Durable public evaluation of the unchanged Phase 5 preregistration.

One exclusive reservation binds captured historical evidence, the prospective
execution contract and the new runtime before outcomes, histories or fits.
Interrupted work is retained and blocks fresh execution on restart. Local
integrity checks provide no independent agency custody or release authority.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
import platform
import re
import threading
from typing import Any

from . import benchmark, qualified_evaluation as evaluator, qualified_store, web
from .benchmark_store import _decode, _read, _write

PREFIX = "/api/research-qualified-evaluation"
PHASE5_RUN = "1f533833767c74bf262c18145c9bbe8c"
PHASE5_SPEC_SHA = "b6fd59634f6ca82224f7febabf0e1c9bd960101a4de6e676df00a49039244295"
PHASE5_REGISTRATION_SHA = "3c5c9bbf13c76d9035bebb11004bb0307640f084878b74298ff3759633186a41"
OUTPUTS = ("evaluation.json", "models.json", "predictions.json", "reference-blocks.json",
           "simulation-diagnostics.json", "reproducibility.json", "evaluation.txt")
HISTORICAL = tuple("phase5-" + name for name in qualified_store.ARTIFACTS)
BEFORE = ("evaluation-reservation.json", "execution-contract.json", "execution-runtime.json")
INPUTS = ("cohorts.json", "inputs.json")
ARTIFACTS = (*HISTORICAL, *BEFORE, *INPUTS, *OUTPUTS, "evaluation-completion.json")
IMPLEMENTATION = ("qualified_evaluation.py", "qualified_evaluation_store.py",
                  "qualified_evaluation_routes.py", "qualified_evaluation_console_app.py",
                  "static/qualified-evaluation.html", "static/qualified-evaluation.js",
                  "static/qualified-evaluation.css")
AUTHORITY = {"agency_acceptance": "pending", "operational_usefulness": "not_evaluated",
             "authorization_effect": "none", "production_execution_qualified": False}
_RUN = re.compile(r"[a-f0-9]{32}\Z")
_MAX = 64 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    return benchmark.canonical_bytes(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(path: Path, value: Any):
    _write(path, _canonical(value))


def _runtime():
    base = Path(__file__).parent
    packages = {}
    for name in ("model-release-assurance", "fastapi", "starlette", "numpy", "threadpoolctl"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {"schema": "mra-qualified-evaluation-runtime/1.0",
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "packages": packages, "implementation_sha256": {
                name: web._sha(_read(base / name)) for name in IMPLEMENTATION}}


class QualifiedEvaluationStore:
    def __init__(self, data_dir: str | Path, *, preregistration_root: str | Path | None = None):
        self.root = Path(data_dir).absolute()
        web._check_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        web._check_path(self.root)
        self.preregistration_root = (Path(preregistration_root).absolute()
                                     if preregistration_root is not None else
                                     self.root.parent / "demo-data-rr-qualified-benchmark")
        self.phase5 = qualified_store.QualifiedRunStore(self.preregistration_root)
        self.runtime = _runtime()
        self.contract = evaluator.execution_contract()
        self.contract_raw = _canonical(self.contract)
        self.contract_sha = web._sha(self.contract_raw)
        self._lock = threading.RLock()
        self._replay_lock = threading.RLock()
        self._replay_cache = OrderedDict()
        self._active: dict[str, dict[str, Any]] = {}

    def _ensure_runtime(self):
        if _runtime() != self.runtime or _canonical(evaluator.execution_contract()) != self.contract_raw:
            raise web.ResearchWebError("Bound evaluation implementation or execution contract changed; execution and delivery are blocked")

    def _historical(self):
        self._ensure_runtime()
        captured, registration, _ = self.phase5._verified(PHASE5_RUN)
        if (self.phase5.spec_sha != PHASE5_SPEC_SHA
                or web._sha(captured["preregistration.json"]) != PHASE5_REGISTRATION_SHA
                or _canonical(evaluator.specification()) != captured["specification.json"]):
            raise web.ResearchWebError("Historical public preregistration differs from the unchanged frozen Phase 5 plan")
        return captured, registration

    def _identity(self, captured):
        return {"phase5_run_id": PHASE5_RUN, "phase5_specification_sha256": PHASE5_SPEC_SHA,
                "phase5_preregistration_sha256": PHASE5_REGISTRATION_SHA,
                "phase5_artifact_sha256": {name: web._sha(data) for name, data in captured.items()},
                "execution_contract_sha256": self.contract_sha, "runtime": self.runtime}

    def catalog(self):
        ready, reasons = False, []
        tasks = []
        try:
            _, _, audit = self.phase5._verified(PHASE5_RUN)
            self._historical()
            tasks = self.phase5._tasks(audit)
            ready = True
        except (OSError, ValueError, KeyError, TypeError, web.ResearchWebError):
            reasons.append("The frozen Phase 5 preregistration, source encodings, runtime or execution contract could not be verified")
        return {"schema": "mra-qualified-evaluation-catalog/1.0", "ready": ready,
                "blocked_reasons": reasons, "phase5_run_id": PHASE5_RUN,
                "specification_sha256": PHASE5_SPEC_SHA,
                "execution_contract_sha256": self.contract_sha,
                "repetitions_per_task": 16384, "comparisons_required": 6,
                "tasks": tasks, "scope": dict(AUTHORITY),
                "replay_scope": "Every first or changed captured fingerprint requires a complete deterministic Monte Carlo replay; unchanged captured bytes use a bounded in-memory verification cache. Restarts require a fresh full replay."}

    def _folder(self, run_id):
        if type(run_id) is not str or not _RUN.fullmatch(run_id):
            raise web.ResearchWebError("Unknown public evaluation identifier", 404)
        folder = self.root / run_id
        web._check_path(folder)
        if not folder.is_dir():
            raise web.ResearchWebError("Unknown public evaluation identifier", 404)
        return folder

    def _reserve(self):
        captured, registration = self._historical()
        identity = self._identity(captured)
        run_id = web._sha(_canonical(identity))[:32]
        folder = self.root / run_id
        web._check_path(folder)
        try:
            folder.mkdir(exist_ok=False)
        except FileExistsError:
            return run_id, None, self.detail(run_id)
        reservation = {"schema": "mra-qualified-evaluation-reservation/1.0",
                       "run_id": run_id, "reserved_at": _now(), "identity": identity,
                       "phase5_preregistered_at": registration["preregistered_at"],
                       "execution_contract_before_outcome_derivation": True,
                       "execution_contract_before_retained_history": True,
                       "execution_contract_before_fresh_randomness_and_fits": True,
                       "scope": dict(AUTHORITY)}
        # Exclusive reservation, contract and runtime precede label/history
        # derivation. Every write is O_EXCL and fsynced; completion is last.
        _json(folder / BEFORE[0], reservation)
        _write(folder / BEFORE[1], self.contract_raw)
        _json(folder / BEFORE[2], self.runtime)
        for name, data in captured.items():
            _write(folder / ("phase5-" + name), data)
        with self._lock:
            self._active[run_id] = {"stage": "preparing_inputs", "task": None, "done": 0, "total": 16384}
        return run_id, (captured, reservation), None

    def _execute(self, run_id, prepared):
        folder = self._folder(run_id)
        captured, reservation = prepared
        try:
            self._ensure_runtime()
            spec = _decode(captured["specification.json"])
            sources = {agency: captured[f"source-{agency}.csv"] for agency in qualified_store.AGENCIES}
            cohorts = evaluator.prepare_cohorts(spec, sources)
            _json(folder / "cohorts.json", cohorts)
            inputs = evaluator.prepare_inputs(spec, cohorts)
            _json(folder / "inputs.json", inputs)
            evaluator.verify_inputs(spec, cohorts, inputs)
            self._ensure_runtime()

            def progress(value):
                self._ensure_runtime()
                if type(value) is not dict:
                    raise ValueError("Invalid evaluation progress")
                with self._lock:
                    task = value.get("task_id")
                    done, total = value.get("completed_repetitions"), value.get("repetitions_per_task")
                    if (task not in qualified_store.AGENCIES or type(done) is not int
                            or type(total) is not int or total != 16384 or not 0 <= done <= total
                            or value.get("fixed_batch_size") != 256):
                        raise ValueError("Progress differs from the fixed public batch contract")
                    self._active[run_id] = {"stage": "evaluating", "task": task, "done": done, "total": total}

            bundle = evaluator.evaluate_benchmark(spec, cohorts, inputs, progress=progress)
            if type(bundle) is not dict or set(bundle) != set(OUTPUTS):
                raise ValueError("Evaluation artifact bundle differs from fixed publication set")
            if any(type(data) is not bytes for data in bundle.values()):
                raise ValueError("Evaluation artifacts must be captured immutable bytes")
            evaluator.verify_results(spec, cohorts, inputs, bundle)
            self._ensure_runtime()
            for name in OUTPUTS:
                _write(folder / name, bundle[name])
            evidence = {name: _read(folder / name, _MAX) for name in ARTIFACTS
                        if name != "evaluation-completion.json"}
            completion = {"schema": "mra-qualified-evaluation-completion/1.0",
                          "run_id": run_id, "completed_at": _now(),
                          "execution_contract_sha256": self.contract_sha,
                          "phase5_specification_sha256": PHASE5_SPEC_SHA,
                          "retained_inputs_saved_before_evaluation": True,
                          "artifacts": {name: {"sha256": web._sha(data), "bytes": len(data)}
                                        for name, data in evidence.items()}}
            _json(folder / "evaluation-completion.json", completion)
        except BaseException as exc:
            # Preserve interrupted evidence. No replacement run, retries,
            # fabricated completion or resampled retained history.
            try:
                _json(folder / "evaluation-incident.json",
                      {"schema": "mra-qualified-evaluation-incident/1.0", "run_id": run_id,
                       "failed_at": _now(), "error_type": type(exc).__name__,
                       "status": "blocked", "instruction": "Preserve this exclusive reservation and its evidence; execution is not resumable"})
            except (OSError, ValueError):
                pass
            raise
        finally:
            with self._lock:
                self._active.pop(run_id, None)
        return self.detail(run_id)

    def evaluate(self):
        run_id, prepared, existing = self._reserve()
        return existing if prepared is None else self._execute(run_id, prepared)

    def start(self):
        run_id, prepared, existing = self._reserve()
        if prepared is None:
            return existing
        def job():
            try:
                self._execute(run_id, prepared)
            except BaseException:
                # Incident evidence is already flushed; the next read reports
                # blocked without exposing source paths or a server traceback.
                pass
        thread = threading.Thread(target=job, name="mra-public-qualified-evaluation", daemon=True)
        thread.start()
        return self.detail(run_id)

    def _capture_verified(self, run_id):
        self._ensure_runtime()
        folder = self._folder(run_id)
        if not (folder / "evaluation-completion.json").exists():
            raise web.ResearchWebError("Incomplete public evaluation is exclusively reserved and blocked; preserve its incident evidence", 409)
        captured = {name: _read(folder / name, _MAX) for name in ARTIFACTS}
        completion = _decode(captured["evaluation-completion.json"])
        reservation = _decode(captured["evaluation-reservation.json"])
        historical, registration = self._historical()
        identity = self._identity(historical)
        expected_reservation = {"schema": "mra-qualified-evaluation-reservation/1.0",
                                "run_id": run_id, "reserved_at": reservation.get("reserved_at"),
                                "identity": identity,
                                "phase5_preregistered_at": registration["preregistered_at"],
                                "execution_contract_before_outcome_derivation": True,
                                "execution_contract_before_retained_history": True,
                                "execution_contract_before_fresh_randomness_and_fits": True,
                                "scope": dict(AUTHORITY)}
        if (_canonical(reservation) != _canonical(expected_reservation) or web._sha(_canonical(identity))[:32] != run_id
                or captured["execution-contract.json"] != self.contract_raw
                or captured["execution-runtime.json"] != _canonical(self.runtime)
                or any(captured["phase5-" + name] != data for name, data in historical.items())):
            raise web.ResearchWebError("Evaluation custody, runtime or captured preregistration differs from its frozen identity")
        for value in (reservation.get("reserved_at"), completion.get("completed_at")):
            if type(value) is not str or not value.endswith("Z") or len(value) > 32:
                raise ValueError("Invalid evaluation timestamp")
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
            if parsed.isoformat().replace("+00:00", "Z") != value:
                raise ValueError("Noncanonical evaluation timestamp")
        if not (datetime.fromisoformat(registration["preregistered_at"].replace("Z", "+00:00"))\
                <= datetime.fromisoformat(reservation["reserved_at"].replace("Z", "+00:00"))\
                <= datetime.fromisoformat(completion["completed_at"].replace("Z", "+00:00"))):
            raise ValueError("Inconsistent prospective evaluation ordering")
        expected_completion = {"schema": "mra-qualified-evaluation-completion/1.0",
                               "run_id": run_id, "completed_at": completion["completed_at"],
                               "execution_contract_sha256": self.contract_sha,
                               "phase5_specification_sha256": PHASE5_SPEC_SHA,
                               "retained_inputs_saved_before_evaluation": True,
                               "artifacts": {name: {"sha256": web._sha(data), "bytes": len(data)}
                                             for name, data in captured.items()
                                             if name != "evaluation-completion.json"}}
        if _canonical(completion) != _canonical(expected_completion):
            raise web.ResearchWebError("Saved evaluation artifact bytes differ from immutable completion hashes")
        spec = _decode(historical["specification.json"])
        sources = {agency: historical[f"source-{agency}.csv"] for agency in qualified_store.AGENCIES}
        cohorts = _decode(captured["cohorts.json"])
        if _canonical(cohorts) != _canonical(evaluator.prepare_cohorts(spec, sources)):
            raise web.ResearchWebError("Captured cohorts differ from exact frozen source reconstruction")
        inputs = _decode(captured["inputs.json"])
        evaluator.verify_inputs(spec, cohorts, inputs)
        bundle = {name: captured[name] for name in OUTPUTS}
        evaluator.verify_results(spec, cohorts, inputs, bundle)
        fingerprint = web._sha(_canonical({
            "artifacts": {name: web._sha(data) for name, data in captured.items()},
            "runtime": self.runtime, "execution_contract_sha256": self.contract_sha}))
        key = (run_id, fingerprint)
        # Captured bytes, not filenames or mtimes, identify an accepted replay.
        # Coherent restamping changes the fingerprint and must reproduce every
        # Monte Carlo artifact. The cache is local, bounded and lost on restart.
        with self._replay_lock:
            self._ensure_runtime()
            if key not in self._replay_cache:
                evaluator.verify_results(spec, cohorts, inputs, bundle, full_replay=True)
                self._ensure_runtime()
                self._replay_cache[key] = True
                while len(self._replay_cache) > 4:
                    self._replay_cache.popitem(last=False)
            else:
                self._replay_cache.move_to_end(key)
            self._ensure_runtime()
        return captured, reservation, completion, _decode(bundle["evaluation.json"])

    def _verified(self, run_id):
        try:
            return self._capture_verified(run_id)
        except web.ResearchWebError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError) as exc:
            raise web.ResearchWebError("Captured public evaluation evidence failed replay verification; delivery is blocked") from exc

    def detail(self, run_id):
        folder = self._folder(run_id)
        if not (folder / "evaluation-completion.json").exists():
            self._ensure_runtime()
            with self._lock:
                progress = self._active.get(run_id)
                if progress is not None:
                    return {"schema": "mra-qualified-evaluation-run/1.0", "run_id": run_id,
                            "status": "running", "progress": dict(progress),
                            "specification_sha256": PHASE5_SPEC_SHA,
                            "execution_contract_sha256": self.contract_sha,
                            "phase5_run_id": PHASE5_RUN, "scope": dict(AUTHORITY),
                            "artifacts": [], "result": None}
            raise web.ResearchWebError("Incomplete public evaluation is exclusively reserved and blocked; preserve its incident evidence", 409)
        captured, reservation, completion, result = self._verified(run_id)
        return {"schema": "mra-qualified-evaluation-run/1.0", "run_id": run_id,
                "status": "evaluated", "reserved_at": reservation["reserved_at"],
                "completed_at": completion["completed_at"],
                "specification_sha256": PHASE5_SPEC_SHA,
                "execution_contract_sha256": self.contract_sha,
                "phase5_run_id": PHASE5_RUN, "scope": dict(AUTHORITY),
                "progress": None, "result": result,
                "artifacts": [{"name": name, "url": f"{PREFIX}/runs/{run_id}/artifacts/{name}",
                               "sha256": web._sha(data), "bytes": len(data)}
                              for name, data in captured.items()]}

    def artifact(self, run_id, name):
        if type(name) is not str or name not in ARTIFACTS:
            raise web.ResearchWebError("Unknown public evaluation artifact", 404)
        captured, _, _, _ = self._verified(run_id)
        return captured[name]

    def runs(self):
        result = []
        for folder in sorted(self.root.iterdir()):
            if _RUN.fullmatch(folder.name) and folder.is_dir():
                try:
                    detail = self.detail(folder.name)
                    result.append({"run_id": folder.name, "status": detail["status"],
                                   "completed_at": detail.get("completed_at")})
                except (web.ResearchWebError, OSError, ValueError):
                    result.append({"run_id": folder.name, "status": "blocked", "completed_at": None})
        return {"schema": "mra-qualified-evaluation-runs/1.0", "runs": result}

