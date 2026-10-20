"""Prospective public-domain benchmark custody and exclusive execution.

Local hashes and deterministic replay establish retained consistency only.
This store never authorizes release or admits private data.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import threading
from typing import Any
import zipfile

from . import benchmark, web
from .certificates import verify_certificate, RRParameters, ResearchContext
from .cli import _load

PREFIX = "/api/research-benchmark"
ARTIFACTS = ("evaluation.json", "models.json", "predictions.json", "reference-blocks.json",
             "simulation-diagnostics.json", "reproducibility.json", "evaluation.txt")
AUTHORITY = {"authorization_effect": "none", "production_execution_qualified": False,
             "operational_usefulness": "not_evaluated"}
_REGISTRATION = ("specification.json", "runtime.json", "preregistration.json", "cohorts.json",
                 "inputs.json", "registration-completion.json")
_SOURCE = tuple(f"source-{c}-{name}" for c in ("acs", "bts", "hmda", "tlc")
                for name in ("manifest.json", "data.npz"))
_NAMES = frozenset((*_REGISTRATION, *_SOURCE, "evaluation-reservation.json",
                    "evaluation-completion.json", *ARTIFACTS))
_RUN = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_MAX = 16 * 1024 * 1024
_MEMBERS = {"old_indices", "overlap_indices", "isolated_indices", "utility_indices", "strata",
            "attack_train_indices", "attack_cal_indices", "attack_eval_indices",
            "B", "z", "y", "keys", "source_row_indices", "source_panel"}
_REQUIRED = {"B", "z", "y", "keys", "source_panel"}
_IMPLEMENTATION = ("benchmark.py", "benchmark_store.py", "benchmark_routes.py",
                   "benchmark_console_app.py", "certificates.py", "sampling.py", "cli.py")


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path, limit: int = _MAX) -> bytes:
    web._check_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise web.ResearchWebError("Benchmark artifacts must be ordinary single-link files")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise web.ResearchWebError("Benchmark source identity changed during capture")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    web._check_path(path)
    current = path.lstat()
    if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) !=
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
        raise web.ResearchWebError("Benchmark source changed during capture")
    if len(data) > limit:
        raise web.ResearchWebError("Benchmark artifact exceeds its size bound")
    return data


def _write(path: Path, data: bytes):
    web._check_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _json(path, value):
    _write(path, benchmark.canonical_bytes(value))


def _decode(data):
    # The certificate CLI enforces unique keys, finite numbers and bounded JSON.
    # Cohort/prediction artifacts exceed its certificate-specific 128 KiB bound.
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate benchmark JSON field")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        if benchmark.canonical_bytes(value) != data:
            raise ValueError("Noncanonical benchmark evidence")
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise web.ResearchWebError("Invalid immutable benchmark JSON evidence") from exc


def _same(actual, expected, label):
    if benchmark.canonical_bytes(actual) != benchmark.canonical_bytes(expected):
        raise web.ResearchWebError(f"The {label} differs from its frozen benchmark registration")


def _runtime():
    base = Path(__file__).parent
    packages = {}
    for name in ("model-release-assurance", "numpy", "scipy", "scikit-learn", "fastapi", "starlette", "threadpoolctl"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "packages": packages, "implementation_sha256": {
                name: web._sha(_read(base / name)) for name in _IMPLEMENTATION}}


def _arrays(data: bytes, manifest: dict[str, Any]) -> dict[str, np.ndarray]:
    """Inspect bounded NPY headers before loading only the five needed arrays."""
    import numpy as np
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            names = [m.filename for m in members]
            if (len(names) != len(set(names)) or not _REQUIRED.issubset({n.removesuffix(".npy") for n in names})
                    or any(n not in {name + ".npy" for name in _MEMBERS} for n in names)
                    or sum(m.file_size for m in members) > 64 * 1024 * 1024):
                raise ValueError("Unsafe NPZ members or expansion")
            for member in members:
                if member.flag_bits & 1 or member.file_size > 32 * 1024 * 1024:
                    raise ValueError("Unsafe NPZ member")
                with archive.open(member) as stream:
                    version = np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
                    else:
                        raise ValueError("Unsupported NPY version")
                    count = int(np.prod(shape, dtype=object))
                    if (dtype.hasobject or dtype.kind not in "iuUS" or len(shape) not in (1, 2)
                            or count < 1 or count > 30000 * 128 or dtype.itemsize > 512
                            or member.file_size != stream.tell() + count * dtype.itemsize or fortran):
                        raise ValueError("Unsafe NPY shape or dtype")
                    declaration = manifest.get("arrays", {}).get(member.filename[:-4])
                    if declaration is None or declaration.get("shape") != list(shape) or declaration.get("dtype") != str(dtype):
                        raise ValueError("NPZ header differs from pinned manifest")
        with np.load(io.BytesIO(data), allow_pickle=False) as source:
            result = {name: np.array(source[name], copy=True) for name in _REQUIRED}
        count = manifest["selected_rows"]
        if type(count) is not int or not 1 <= count <= 30000 or len(result["y"]) != count:
            raise ValueError("Invalid declared public row count")
        return result
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile, EOFError, OverflowError) as exc:
        raise web.ResearchWebError("Pinned public NPZ representation is unsafe or inconsistent") from exc


def _bundle(bundle):
    if type(bundle) is not dict or set(bundle) != set(ARTIFACTS):
        raise web.ResearchWebError("Benchmark evaluator returned an incomplete artifact set")
    result = {}
    for name in ARTIFACTS:
        value = bundle[name]
        if name.endswith(".txt"):
            if type(value) is not str:
                raise web.ResearchWebError("Benchmark text report must be inert text")
            raw = value.encode("utf-8")
        else:
            if type(value) is not dict:
                raise web.ResearchWebError("Benchmark result artifacts must be JSON objects")
            raw = benchmark.canonical_bytes(value)
        if len(raw) > _MAX:
            raise web.ResearchWebError("Benchmark result exceeds its bounded artifact size")
        result[name] = raw
    return result


class BenchmarkRunStore:
    """Canonical source/spec/runtime experiment with durable incomplete states."""

    def __init__(self, data_dir: str | Path, *, source_base: str | Path | None = None,
                 specification_override: dict[str, Any] | None = None):
        self.root = Path(data_dir).absolute()
        web._check_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        web._check_path(self.root)
        self.spec = (benchmark.specification() if specification_override is None
                     else _decode(benchmark.canonical_bytes(specification_override)))
        self.spec_raw = benchmark.canonical_bytes(self.spec)
        self.spec_hash = web._sha(self.spec_raw)
        self.source_base = Path(source_base if source_base is not None else self.spec["source_base"]).absolute()
        web._check_path(self.source_base)
        self._cache = OrderedDict()
        self._cache_lock = threading.RLock()

    def _directory(self, run_id):
        if type(run_id) is not str or not _RUN.fullmatch(run_id):
            raise web.ResearchWebError("Benchmark run not found", 404)
        path = self.root / run_id
        web._check_path(path)
        if not path.is_dir():
            raise web.ResearchWebError("Benchmark run not found", 404)
        return path

    def _source_capture(self):
        captured = {}
        for corpus in self.spec["tasks_order"]:
            descriptor = self.spec["sources"][corpus]
            for name, pin in (("manifest.json", "manifest_sha256"), ("data.npz", "data_sha256")):
                raw = _read(self.source_base / corpus / "data" / name)
                if web._sha(raw) != descriptor[pin]:
                    raise web.ResearchWebError(f"Public {corpus} {name} differs from its frozen source hash")
                captured[f"source-{corpus}-{name}"] = raw
        return captured

    def _sources(self, captured=None):
        result = []
        for corpus in self.spec["tasks_order"]:
            descriptor = self.spec["sources"][corpus]
            item = {"corpus": corpus, **descriptor, "available": True, "status": "ready"}
            if captured is None:
                try:
                    for name, pin in (("manifest.json", "manifest_sha256"), ("data.npz", "data_sha256")):
                        if web._sha(_read(self.source_base / corpus / "data" / name)) != descriptor[pin]:
                            raise web.ResearchWebError("Frozen source hash differs")
                except (OSError, web.ResearchWebError) as exc:
                    item.update(available=False, status="rejected", reason=str(exc))
            result.append(item)
        return result

    def catalog(self):
        dependency = benchmark.dependency_status()
        sources = self._sources()
        return {"available": dependency["available"] and all(item["available"] for item in sources), "sources": sources,
                "dependencies": dependency, "reason": dependency.get("reason"),
                "specification": self.spec, "specification_sha256": self.spec_hash, "authority": AUTHORITY}

    def _identity(self, runtime):
        return {"specification_sha256": self.spec_hash, "sources": {
            corpus: {name: self.spec["sources"][corpus][name]
                     for name in ("data_sha256", "manifest_sha256")}
            for corpus in self.spec["tasks_order"]}, "runtime": runtime}

    def _prepare(self, source):
        datasets = {}
        for corpus in self.spec["tasks_order"]:
            raw = source[f"source-{corpus}-manifest.json"]
            # Source manifests retain historical pretty formatting, unlike new evidence.
            manifest = _load(raw)
            descriptor = self.spec["sources"][corpus]
            if (manifest.get("corpus") != corpus or manifest.get("b_names") != descriptor["features"]
                    or manifest.get("b_sizes") != descriptor["category_sizes"]
                    or manifest.get("data_receipt", {}).get("sha256") != descriptor["data_sha256"]):
                raise web.ResearchWebError("Pinned public manifest semantics differ from the registered source")
            datasets[corpus] = _arrays(source[f"source-{corpus}-data.npz"], manifest)
        cohorts = benchmark.prepare_cohorts(self.spec, datasets)
        inputs = benchmark.prepare_inputs(self.spec, cohorts)
        return cohorts, inputs

    def create(self):
        dependency = benchmark.dependency_status()
        if not dependency["available"]:
            raise web.ResearchWebError(dependency.get("reason", "Public benchmark numeric dependencies are unavailable"))
        source = self._source_capture()
        runtime = _runtime()
        identity = self._identity(runtime)
        run_id = web._sha(benchmark.canonical_bytes(identity))[:32]
        directory = self.root / run_id
        web._check_path(directory)
        try:
            directory.mkdir(exist_ok=False)
        except FileExistsError:
            if not (directory / "registration-completion.json").exists():
                raise web.ResearchWebError("Canonical benchmark registration is incomplete; it cannot be retried")
            return self.detail(run_id)
        # No source target arrays or seeded retained RNG have been read at this point.
        _write(directory / "specification.json", self.spec_raw)
        _json(directory / "runtime.json", runtime)
        _json(directory / "preregistration.json", {
            "schema": "mra-public-benchmark-preregistration/1.0", "run_id": run_id,
            "registered_at": _now(), "identity": identity,
            "registered_before_target_loading": True, "registered_before_retained_rng": True,
            "registered_before_fitting": True, **AUTHORITY})
        for name, raw in source.items():
            _write(directory / name, raw)
        cohorts, inputs = self._prepare(source)
        _json(directory / "cohorts.json", cohorts)
        _json(directory / "inputs.json", inputs)
        names = (*_REGISTRATION[:-1], *_SOURCE)
        captured = {name: _read(directory / name) for name in names}
        key = ("registration", web._sha(benchmark.canonical_bytes({
            name: web._sha(raw) for name, raw in captured.items() if name not in
            {"cohorts.json", "inputs.json", "registration-completion.json"}})))
        self._cache_get(key, lambda: (cohorts, inputs))
        _json(directory / "registration-completion.json", {
            "schema": "mra-public-benchmark-registration-completion/1.0", "run_id": run_id,
            "completed_at": _now(), "artifacts": {name: web._sha(raw) for name, raw in captured.items()},
            **AUTHORITY})
        return self.detail(run_id)

    def _cache_get(self, key, function):
        with self._cache_lock:
            if key not in self._cache:
                self._cache[key] = function()
                while len(self._cache) > 4:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(key)
            return self._cache[key]

    def _registered(self, run_id):
        directory = self._directory(run_id)
        captured = {name: _read(directory / name) for name in (*_REGISTRATION, *_SOURCE)}
        spec = _decode(captured["specification.json"])
        _same(spec, self.spec, "specification")
        runtime = _decode(captured["runtime.json"])
        _same(runtime, _runtime(), "current runtime")
        identity = self._identity(runtime)
        if web._sha(benchmark.canonical_bytes(identity))[:32] != run_id:
            raise web.ResearchWebError("Canonical benchmark identity changed")
        prospective = _decode(captured["preregistration.json"])
        if type(prospective.get("registered_at")) is not str:
            raise web.ResearchWebError("Invalid prospective benchmark time")
        _same(prospective, {
            "schema": "mra-public-benchmark-preregistration/1.0", "run_id": run_id,
            "registered_at": prospective["registered_at"], "identity": identity,
            "registered_before_target_loading": True, "registered_before_retained_rng": True,
            "registered_before_fitting": True, **AUTHORITY}, "prospective declaration")
        source = {name: captured[name] for name in _SOURCE}
        # Check current official-local source bytes too; snapshots never replace source eligibility.
        if self._source_capture() != source:
            raise web.ResearchWebError("Registered public source changed")
        completion = _decode(captured["registration-completion.json"])
        if type(completion.get("completed_at")) is not str:
            raise web.ResearchWebError("Invalid registration completion time")
        _same(completion, {
            "schema": "mra-public-benchmark-registration-completion/1.0", "run_id": run_id,
            "completed_at": completion["completed_at"],
            "artifacts": {name: web._sha(raw) for name, raw in captured.items()
                          if name != "registration-completion.json"}, **AUTHORITY}, "registration receipt")
        key = ("registration", web._sha(benchmark.canonical_bytes({
            name: web._sha(raw) for name, raw in captured.items() if name not in
            {"cohorts.json", "inputs.json", "registration-completion.json"}})))
        cohorts, inputs = self._cache_get(key, lambda: self._prepare(source))
        if (captured["cohorts.json"] != benchmark.canonical_bytes(cohorts)
                or captured["inputs.json"] != benchmark.canonical_bytes(inputs)):
            raise web.ResearchWebError("Captured benchmark cohorts or certificate inputs changed semantically")
        return directory, prospective, captured, cohorts, inputs

    def _lineage(self, captured):
        return {name: web._sha(raw) for name, raw in captured.items()}

    def _completed(self, run_id, registered=None):
        directory, prospective, captured, cohorts, inputs = registered or self._registered(run_id)
        reservation_raw = _read(directory / "evaluation-reservation.json")
        reservation = _decode(reservation_raw)
        if type(reservation.get("reserved_at")) is not str:
            raise web.ResearchWebError("Invalid evaluation reservation time")
        _same(reservation, {"schema": "mra-public-benchmark-reservation/1.0", "run_id": run_id,
                            "reserved_at": reservation["reserved_at"], "status": "reserved_incomplete",
                            "registration_artifacts": self._lineage(captured), **AUTHORITY},
              "captured evaluation reservation")
        outputs = {name: _read(directory / name) for name in ARTIFACTS}
        complete_raw = _read(directory / "evaluation-completion.json")
        complete = _decode(complete_raw)
        if type(complete.get("completed_at")) is not str:
            raise web.ResearchWebError("Invalid evaluation completion time")
        _same(complete, {"schema": "mra-public-benchmark-evaluation-completion/1.0", "run_id": run_id,
                         "completed_at": complete["completed_at"], "reservation_sha256": web._sha(reservation_raw),
                         "registration_artifacts": self._lineage(captured),
                         "artifacts": {name: web._sha(raw) for name, raw in outputs.items()}, **AUTHORITY},
              "captured evaluation completion")
        key = ("evaluation", web._sha(benchmark.canonical_bytes(self._lineage(captured))))
        expected = self._cache_get(key, lambda: _bundle(benchmark.evaluate_benchmark(self.spec, cohorts, inputs)))
        if outputs != expected:
            raise web.ResearchWebError("Captured benchmark outputs differ from deterministic registered evaluation")
        # Reject a swap after initial validation while returning only already checked bytes.
        after = {name: _read(directory / name) for name in captured}
        if after != captured:
            raise web.ResearchWebError("Registered benchmark evidence changed during output validation")
        all_raw = {**captured, **outputs, "evaluation-reservation.json": reservation_raw,
                   "evaluation-completion.json": complete_raw}
        return all_raw, _decode(outputs["evaluation.json"])

    def evaluate(self, run_id):
        dependency = benchmark.dependency_status()
        if not dependency["available"]:
            raise web.ResearchWebError(dependency.get("reason", "Public benchmark numeric dependencies are unavailable"))
        registered = self._registered(run_id)
        directory, _, captured, cohorts, inputs = registered
        if (directory / "evaluation-completion.json").exists():
            self._completed(run_id, registered)
            return self.detail(run_id)
        try:
            _json(directory / "evaluation-reservation.json", {
                "schema": "mra-public-benchmark-reservation/1.0", "run_id": run_id,
                "reserved_at": _now(), "status": "reserved_incomplete",
                "registration_artifacts": self._lineage(captured), **AUTHORITY})
        except FileExistsError:
            raise web.ResearchWebError("Benchmark evaluation is already reserved or interrupted; no duplicate execution") from None
        self._after_reservation()
        bundle = _bundle(benchmark.evaluate_benchmark(self.spec, cohorts, inputs))
        if {name: _read(directory / name) for name in captured} != captured:
            raise web.ResearchWebError("Benchmark input changed during evaluation; reservation remains blocked")
        for name, raw in bundle.items():
            _write(directory / name, raw)
        written = {name: _read(directory / name) for name in ARTIFACTS}
        if written != bundle:
            raise web.ResearchWebError("Captured written benchmark output differs before completion")
        reservation_raw = _read(directory / "evaluation-reservation.json")
        expected_reservation = {
            "schema": "mra-public-benchmark-reservation/1.0", "run_id": run_id,
            "reserved_at": _decode(reservation_raw).get("reserved_at"), "status": "reserved_incomplete",
            "registration_artifacts": self._lineage(captured), **AUTHORITY}
        _same(_decode(reservation_raw), expected_reservation, "evaluation reservation before completion")
        _json(directory / "evaluation-completion.json", {
            "schema": "mra-public-benchmark-evaluation-completion/1.0", "run_id": run_id,
            "completed_at": _now(), "reservation_sha256": web._sha(reservation_raw),
            "registration_artifacts": self._lineage(captured),
            "artifacts": {name: web._sha(raw) for name, raw in written.items()}, **AUTHORITY})
        key = ("evaluation", web._sha(benchmark.canonical_bytes(self._lineage(captured))))
        self._cache_get(key, lambda: bundle)
        self._completed(run_id)
        return self.detail(run_id)

    def _after_reservation(self):
        """Explicit test hook; production never repairs an unknown outcome."""

    def _detail(self, run_id):
        directory, prospective, captured, cohorts, inputs = self._registered(run_id)
        status, result = "registered", None
        raw = captured
        if (directory / "evaluation-completion.json").exists():
            raw, result = self._completed(run_id, (directory, prospective, captured, cohorts, inputs))
            status = "completed"
        elif (directory / "evaluation-reservation.json").exists():
            # An incomplete reservation may be inspected but never silently retried.
            reserved_raw = _read(directory / "evaluation-reservation.json")
            reserved = _decode(reserved_raw)
            _same(reserved, {"schema": "mra-public-benchmark-reservation/1.0", "run_id": run_id,
                            "reserved_at": reserved.get("reserved_at"), "status": "reserved_incomplete",
                            "registration_artifacts": self._lineage(captured), **AUTHORITY},
                  "incomplete reservation")
            status = "reserved_incomplete"
            raw = {**captured, "evaluation-reservation.json": reserved_raw}
        certificates = []
        for corpus in self.spec["tasks_order"]:
            task = inputs["tasks"][corpus]
            verified = verify_certificate(task["certificate"], expected_parameters=RRParameters.from_dict(task["parameters"]),
                                          expected_context=ResearchContext.from_dict(task["context"]))
            certificates.append({"corpus": corpus, "title": self.spec["sources"][corpus]["title"],
                                 "status": "verified", "parameters": task["parameters"],
                                 "marginal_accuracy": str(verified.marginal_accuracy)})
        detail = {"run_id": run_id, "registered_at": prospective["registered_at"], "status": status,
                  "specification": self.spec, "specification_sha256": self.spec_hash,
                  "sources": self._sources(captured), "certificates": certificates, "result": result,
                  "artifacts": [{"name": name, "url": f"{PREFIX}/runs/{run_id}/artifacts/{name}"}
                                for name in sorted(raw)],
                  "prospective": prospective, "authority": AUTHORITY}
        return detail, raw

    def detail(self, run_id):
        return self._detail(run_id)[0]

    def runs(self):
        runs = []
        entries = []
        for position, entry in enumerate(self.root.iterdir()):
            if position >= 1024:
                raise web.ResearchWebError("Benchmark store entry limit reached")
            entries.append(entry)
        if sum(bool(_RUN.fullmatch(entry.name)) for entry in entries) > 128:
            raise web.ResearchWebError("Benchmark store run limit reached")
        for entry in sorted(entries):
            if not _RUN.fullmatch(entry.name):
                continue
            web._check_path(entry)
            if not entry.is_dir():
                raise web.ResearchWebError("Unsafe benchmark run entry")
            if not (entry / "registration-completion.json").exists():
                runs.append({"run_id": entry.name, "registered_at": None, "status": "reserved_incomplete",
                             "result_status": None, "specification_sha256": self.spec_hash})
                continue
            detail = self.detail(entry.name)
            runs.append({name: detail[name] for name in ("run_id", "registered_at", "status", "specification_sha256")})
            runs[-1]["result_status"] = None if detail["result"] is None else detail["result"].get("status")
        return {"runs": runs}

    def artifact(self, run_id, name):
        if type(name) is not str or name not in _NAMES:
            raise web.ResearchWebError("Benchmark artifact not found", 404)
        _, captured = self._detail(run_id)
        if name not in captured:
            raise web.ResearchWebError("Benchmark artifact is incomplete or unavailable", 404)
        return captured[name]

