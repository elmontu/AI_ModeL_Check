
"""Durable, externally pinned execution of the separately frozen Phase 7B plan.

Only a successful numerical qualification permits an execution reservation.
A reservation cannot be deleted, replaced or retried after an interruption.
Verification replay uses captured bytes and does not reserve another run.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
import os
import platform
import stat
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from mra_research_preregistration import registration as prereg

REGISTRATION_ID = "6cbfa4a1494cda5b73fe1652"
REGISTRATION_COMPLETION_SHA256 = "74125db65be9bf8aee9c300f6b5016352df6684b5f0c2357b24c00ff808a8c67"
SPEC_SHA256 = prereg.APPROVED_SPEC_SHA256
CONTRACT_SHA256 = prereg.APPROVED_CONTRACT_SHA256
STORE_RELATIVE = ".local/demo-data-rr-preregistered-evaluation-20261013"
INPUT_RELATIVE = ".local/public-data-rr-preregistered-evaluation-20261013"
STAGES = ("cohorts", "retained", "fresh", "results", "verification")
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")
SOURCE_PATH = ".local/public-data-rr-readiness-20261013/mas/mas-discontinued-i17-monthly-browser-header-response.csv"
SOURCE_SHA256 = "b984e77e8069f43be583f7d09b1e9357660b51ddf691528af9a7db4031d97e71"
SOURCE_BYTES = 15542


class ExecutionError(ValueError):
    """An execution or verification refusal, preserving the reservation."""


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes):
    try:
        return prereg.strict_json(data)
    except prereg.RegistrationError as exc:
        raise ExecutionError(str(exc)) from exc


def _digest(value, name):
    if type(value) is not str or not prereg.HEX.fullmatch(value):
        raise ExecutionError(name + " must be a lowercase SHA256")
    return value


def _check_path(path: Path):
    for entry in reversed((path, *path.parents)):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ExecutionError("Execution paths cannot contain symlinks or reparse points")


def _relative(root: Path, relative: str) -> Path:
    try:
        result = prereg.bound_path(root, relative)
    except prereg.RegistrationError as exc:
        raise ExecutionError(str(exc)) from exc
    _check_path(result)
    return result


def _read(path: Path) -> bytes:
    _check_path(path)
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ExecutionError("Expected a regular captured artifact")
        return path.read_bytes()
    except OSError as exc:
        raise ExecutionError("Missing captured artifact: " + str(path)) from exc


def _fsync_directory(path):
    # Windows does not expose directory fsync through this Python API.
    # Every file is independently fsynced before a following stage is published.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_once(path: Path, data: bytes):
    _check_path(path)
    if type(data) is not bytes:
        raise ExecutionError("Artifacts must be exact bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _binding(relative, data):
    return {"path": relative, "sha256": sha(data), "bytes": len(data)}


def _verify_file(root, binding):
    if type(binding) is not dict or set(binding) != {"path", "sha256", "bytes"} or type(binding["bytes"]) is not int or binding["bytes"] < 0:
        raise ExecutionError("Malformed artifact binding")
    _digest(binding["sha256"], "Artifact digest")
    data = _read(_relative(root, binding["path"]))
    if len(data) != binding["bytes"] or sha(data) != binding["sha256"]:
        raise ExecutionError("Changed artifact: " + binding["path"])
    return data


def verify_registration(repository):
    root = Path(repository).resolve()
    path = _relative(root, prereg.STORE_RELATIVE + "/" + REGISTRATION_ID)
    data = _read(path / "registration-completion.json")
    if sha(data) != REGISTRATION_COMPLETION_SHA256:
        raise ExecutionError("Changed externally pinned Phase 7B completion")
    try:
        complete = prereg.open_completed(root, path)
    except prereg.RegistrationError as exc:
        raise ExecutionError(str(exc)) from exc
    if complete["registration_id"] != REGISTRATION_ID:
        raise ExecutionError("Wrong preregistration")
    return path


def _runtime_environment():
    import numpy
    from threadpoolctl import threadpool_info
    info = threadpool_info()
    if any(item.get("num_threads") != 1 for item in info):
        raise ExecutionError("All BLAS/OpenMP runtime thread pools must be one")
    if any(os.environ.get(name) != "1" for name in THREAD_VARIABLES):
        raise ExecutionError("All frozen thread-control environment variables must equal one")
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "numpy": numpy.__version__,
        "numpy_rng": "numpy.random.Generator(numpy.random.PCG64)",
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "byteorder": sys.byteorder,
        "float_mantissa_bits": sys.float_info.mant_dig,
        "thread_control": {name: os.environ[name] for name in THREAD_VARIABLES},
        "blas": [{k: entry.get(k) for k in ("user_api", "internal_api", "version", "num_threads", "threading_layer", "architecture")} for entry in info],
    }


def _runtime_sources(repository):
    root = Path(repository).resolve()
    directory = root / "src/mra_preregistered_evaluation"
    files = sorted(directory.glob("*.py"))
    names = {item.name for item in files}
    required = {"__init__.py", "__main__.py", "store.py", "web.py", "inputs.py", "numerics.py", "evaluator.py", "verifier.py"}
    if not required.issubset(names):
        raise ExecutionError("Numerical evaluator/verifier source roster is incomplete")
    # Pin the unchanged wrapper and original assurance implementation as well.
    # This covers all transitive in-repository imports, including imported console
    # factories, without invoking their workers during a metadata-only freeze.
    for namespace in ("mra_source_readiness", "mra_rr_continuation", "mra_research_preregistration", "model_release_assurance"):
        files += sorted((root / "src" / namespace).rglob("*.py"))
    return [_binding(item.relative_to(root).as_posix(), _read(item)) for item in sorted(files)]



def _verify_loaded_sources(bindings):
    """Pin source bytes actually available to the executing checkout or wheel.

    Resolve only top-level packages; inspecting unused nested package specs
    could execute their initializers before the runtime freeze. Already imported
    child modules receive an additional direct-origin byte check.
    """
    package_roots = {}
    for item in bindings:
        relative = Path(item["path"])
        parts = list(relative.parts)
        if len(parts) < 3 or parts.pop(0) != "src":
            raise ExecutionError("Runtime source is not an importable namespace")
        package = parts[0]
        if package not in package_roots:
            found = importlib.util.find_spec(package)
            if found is None or found.origin is None or not found.origin.endswith("__init__.py"):
                raise ExecutionError("Missing executing source package: " + package)
            package_roots[package] = Path(found.origin).parent
        executing_path = package_roots[package].joinpath(*parts[1:])
        data = _read(executing_path)
        if len(data) != item["bytes"] or sha(data) != item["sha256"]:
            raise ExecutionError("Executing installed/checkout source bytes differ: " + relative.as_posix())
        module_parts = list(Path(*parts).with_suffix("").parts)
        if module_parts[-1] == "__init__":
            module_parts.pop()
        module = ".".join(module_parts)
        loaded = sys.modules.get(module)
        if loaded is not None:
            origin = getattr(loaded, "__file__", None)
            if origin is None or sha(_read(Path(origin))) != item["sha256"]:
                raise ExecutionError("Imported module origin differs from frozen bytes: " + module)

def freeze_manifest(repository, path: Path):
    """Capture code and environment only; never parse a numeric source."""
    root = Path(repository).resolve()
    verify_registration(root)
    value = {
        "schema": "mra-phase7c-runtime-freeze/1.0",
        "repository_root": root.as_posix().casefold() if os.name == "nt" else root.as_posix(),
        "preregistration_id": REGISTRATION_ID,
        "scientific_specification_sha256": SPEC_SHA256,
        "execution_contract_sha256": CONTRACT_SHA256,
        "registration_completion_sha256": REGISTRATION_COMPLETION_SHA256,
        "source_sha256": SOURCE_SHA256,
        "source_bytes": SOURCE_BYTES,
        "source_outcomes_derived": False,
        "environment": _runtime_environment(),
        "source_files": _runtime_sources(root),
    }
    _verify_loaded_sources(value["source_files"])
    data = canonical(value)
    write_once(Path(path), data)
    return {"runtime_sha256": sha(data), "runtime": value}


def verify_runtime(repository, path, expected_sha256):
    data = _read(Path(path))
    if sha(data) != _digest(expected_sha256, "External runtime pin"):
        raise ExecutionError("Frozen runtime differs from external pin")
    value = _json(data)
    required = {"schema", "preregistration_id", "scientific_specification_sha256", "execution_contract_sha256", "registration_completion_sha256", "source_sha256", "source_bytes", "source_outcomes_derived", "environment", "source_files", "repository_root"}
    if set(value) != required or value["schema"] != "mra-phase7c-runtime-freeze/1.0":
        raise ExecutionError("Malformed runtime freeze")
    if value["preregistration_id"] != REGISTRATION_ID or value["scientific_specification_sha256"] != SPEC_SHA256 or value["execution_contract_sha256"] != CONTRACT_SHA256 or value["registration_completion_sha256"] != REGISTRATION_COMPLETION_SHA256:
        raise ExecutionError("Runtime is not bound to the registered plan")
    if value["source_outcomes_derived"] is not False or value["source_sha256"] != SOURCE_SHA256 or value["source_bytes"] != SOURCE_BYTES:
        raise ExecutionError("Runtime frozen after source derivation or for a changed source")
    repository_root = Path(repository).resolve()
    normalized_root = repository_root.as_posix().casefold() if os.name == "nt" else repository_root.as_posix()
    if value["repository_root"] != normalized_root:
        raise ExecutionError("Frozen execution repository cannot be aliased to another checkout")
    if value["environment"] != _runtime_environment():
        raise ExecutionError("Frozen runtime environment changed")
    if value["source_files"] != _runtime_sources(repository):
        raise ExecutionError("Frozen evaluator or verifier source bytes changed")
    _verify_loaded_sources(value["source_files"])
    return value, data


def _bounded_decimal(value, maximum, name):
    if type(value) not in (str, int, float) or type(value) is bool:
        raise ExecutionError("Missing numerical qualification bound: " + name)
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ExecutionError("Malformed qualification bound") from exc
    if not number.is_finite() or number < 0 or number > Decimal(maximum):
        raise ExecutionError("Numerical qualification bound exceeds protocol: " + name)


def verify_qualification(path, expected_sha256, runtime_sha256):
    data = _read(Path(path))
    if sha(data) != _digest(expected_sha256, "External qualification pin"):
        raise ExecutionError("Numerical qualification differs from external pin")
    value = _json(data)
    if (value.get("schema") != "mra-phase7c-numerical-qualification/1.0" or value.get("passed") is not True
            or value.get("runtime_sha256") != runtime_sha256
            or value.get("scientific_specification_sha256") != SPEC_SHA256
            or value.get("execution_contract_sha256") != CONTRACT_SHA256
            or value.get("source_outcomes_derived") is not False or value.get("synthetic_only") is not True
            or value.get("blocking_issues") != []):
        raise ExecutionError("Numerical qualification is failed, stale, incomplete or not independent")
    _bounded_decimal(value.get("formal_total_gain_error_upper"), "1e-9", "total gain")
    _bounded_decimal(value.get("gradient_arithmetic_uncertainty_upper"), "5e-13", "gradient arithmetic")
    return value, data


def execution_identity(runtime_sha256):
    _digest(runtime_sha256, "Runtime digest")
    payload = {
        "preregistration_id": REGISTRATION_ID,
        "scientific_specification_sha256": SPEC_SHA256,
        "execution_contract_sha256": CONTRACT_SHA256,
        "runtime_sha256": runtime_sha256,
    }
    return sha(b"mra-phase7c-execution-v1\0" + canonical(payload))[:32]


def reserve(store_root: Path, execution_id: str, identity: dict):
    if type(execution_id) is not str or len(execution_id) != 32 or any(c not in "0123456789abcdef" for c in execution_id):
        raise ExecutionError("Malformed execution identity")
    root = Path(store_root).resolve()
    _check_path(root)
    directory = root / execution_id
    directory.mkdir(parents=True, exist_ok=True)
    value = {"schema": "mra-phase7c-execution-reservation/1.0", "execution_id": execution_id,
             "identity": identity, "reserved_at": datetime.now(timezone.utc).isoformat(),
             "execution_attempts_allowed": 1, "replacement_or_retry_allowed": False}
    try:
        write_once(directory / "reservation.json", canonical(value))
    except FileExistsError as exc:
        state = "completed" if (directory / "completion.json").exists() else "incomplete/interrupted"
        raise ExecutionError("Execution already reserved (" + state + "); preserve reservation and use verification replay") from exc
    return value


class PhaseSink:
    """Publish deterministic stage artifacts only after predecessor fsync."""
    def __init__(self, root: Path, reservation_identity: dict, expected_files=None, progress=None):
        self.root = Path(root).resolve()
        self.identity = reservation_identity
        self.expected_files = expected_files
        self.files = []
        self.stage_index = 0
        self.progress = progress or (lambda value: None)

    def commit_stage(self, stage: str, artifacts: dict[str, bytes]):
        if self.stage_index >= len(STAGES) or stage != STAGES[self.stage_index]:
            raise ExecutionError("Stage order violation: " + str(stage))
        if type(artifacts) is not dict or not artifacts:
            raise ExecutionError("Each execution stage needs bound artifacts")
        if "stage-completion.json" in artifacts:
            raise ExecutionError("Reserved stage marker artifact name")
        bound = []
        for name in sorted(artifacts):
            if type(name) is not str or not name or name.startswith("/") or ":" in name or "\\" in name or ".." in Path(name).parts or Path(name).as_posix() != name or name == ".":
                raise ExecutionError("Unsafe stage artifact path")
            data = artifacts[name]
            if type(data) is not bytes:
                raise ExecutionError("Execution artifacts must be byte buffers")
            relative = stage + "/" + name
            item = _binding(relative, data)
            if self.expected_files is None:
                write_once(_relative(self.root, relative), data)
            else:
                if self.expected_files.get(relative) != item:
                    raise ExecutionError("Deterministic replay differs: " + relative)
                if _read(_relative(self.root, relative)) != data:
                    raise ExecutionError("Replay differs from captured bytes: " + relative)
            bound.append(item)
        marker = canonical({"schema": "mra-phase7c-stage-completion/1.0", "stage": stage, "identity": self.identity, "files": bound})
        marker_item = _binding(stage + "/stage-completion.json", marker)
        if self.expected_files is None:
            write_once(_relative(self.root, marker_item["path"]), marker)
        elif self.expected_files.get(marker_item["path"]) != marker_item or _read(_relative(self.root, marker_item["path"])) != marker:
            raise ExecutionError("Deterministic replay stage marker differs")
        self.files += bound + [marker_item]
        self.stage_index += 1
        self.progress({"stage": stage, "artifacts": len(bound)})

    def require_complete(self):
        if self.stage_index != len(STAGES):
            raise ExecutionError("Numerical execution omitted a mandatory stage")


def _production_pipeline(source, identity, sink):
    from .evaluator import run_staged
    return run_staged(source, identity, sink)


def _production_independent(value):
    from .verifier import verify_actual_reference
    result = verify_actual_reference(value["reference_payload"])
    return {"independent-reference.json": canonical(result)}


def _run_pipeline(source, identity, sink, pipeline, independent_verify):
    result = (pipeline or _production_pipeline)(source, identity, sink)
    if sink.stage_index != 4:
        raise ExecutionError("Evaluator did not commit all four mandatory numerical stages")
    independent = (independent_verify or _production_independent)(result)
    if type(independent) is not dict or not independent:
        raise ExecutionError("Independent numerical verification returned no artifacts")
    # Callback returns byte artifacts, including a strict verified check document.
    parsed = [_json(data) for name, data in independent.items() if name.endswith(".json")]
    if not any(item.get("independent_verified") is True and item.get("passed") is True for item in parsed):
        raise ExecutionError("Independent actual-reference verification failed")
    sink.commit_stage("verification", independent)
    sink.require_complete()
    summary = result.get("summary")
    _validate_summary(summary)
    return summary


def _validate_summary(summary):
    if type(summary) is not dict:
        raise ExecutionError("Missing numerical summary")
    if (summary.get("authorization_effect") != "none" or summary.get("agency_acceptance") != "pending"
            or summary.get("agency_practical_margin") is not None):
        raise ExecutionError("Usefulness or a certificate cannot grant release authority")
    comparisons = summary.get("comparisons")
    order = ["independent_rr", "clean_matched_logistic", "clean_persistence", "clean_seasonal_naive", "clean_expanding_month_rate", "clean_expanding_logistic"]
    if type(comparisons) is not list or len(comparisons) != 18 or [(x.get("domain"), x.get("comparator")) for x in comparisons] != [(d, c) for d in ("moh", "mas", "msf") for c in order]:
        raise ExecutionError("Mandatory eighteen-slot comparison roster changed")
    computed = []
    for slot in comparisons:
        if slot["domain"] in ("moh", "msf"):
            if slot.get("verdict") != "not_evaluable" or any(slot.get(key) is not None for key in ("mean_gain", "lower", "upper")):
                raise ExecutionError("Unsupported mandatory domain has fabricated statistics")
        else:
            if slot.get("verdict") not in ("pass", "fail", "inconclusive"):
                raise ExecutionError("MAS mandatory comparison has no valid verdict")
            for key in ("mean_gain", "lower", "upper"):
                value = slot.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
                    raise ExecutionError("Invalid computed comparison statistic")
            computed.append(slot["verdict"])
    overall = "fail" if "fail" in computed else "not_evaluable"
    if summary.get("overall_verdict") != overall:
        raise ExecutionError("Frozen missing-domain/failure aggregation changed")


def execute(repository, runtime_path, runtime_sha256, qualification_path, qualification_sha256,
            pipeline=None, independent_verify=None, progress=None):
    root = Path(repository).resolve()
    registration = verify_registration(root)
    _, runtime = verify_runtime(root, runtime_path, runtime_sha256)
    _, qualification = verify_qualification(qualification_path, qualification_sha256, runtime_sha256)
    # Source captured once and checked as bytes. No parser or randomizer has run.
    source = _read(_relative(root, SOURCE_PATH))
    if len(source) != SOURCE_BYTES or sha(source) != SOURCE_SHA256:
        raise ExecutionError("Pinned MAS source bytes changed before reservation")
    identity = {"preregistration_id": REGISTRATION_ID, "scientific_specification_sha256": SPEC_SHA256,
                "execution_contract_sha256": CONTRACT_SHA256, "runtime_sha256": runtime_sha256,
                "qualification_sha256": qualification_sha256, "source_sha256": SOURCE_SHA256}
    execution_id = execution_identity(runtime_sha256)
    store_root = _relative(root, STORE_RELATIVE)
    reserve(store_root, execution_id, identity)
    directory = store_root / execution_id
    try:
        captured = {"source.csv": source, "scientific-preregistration.json": _read(registration / "scientific-preregistration.json"),
                    "execution-contract.json": _read(registration / "execution-contract.json"),
                    "runtime-freeze.json": runtime, "numerical-qualification.json": qualification}
        inputs = []
        sibling = _relative(root, INPUT_RELATIVE + "/" + execution_id)
        for name, data in captured.items():
            write_once(sibling / name, data)
            write_once(directory / "captured" / name, data)
            inputs.append(_binding("captured/" + name, data))
        capture_index = canonical({"execution_id": execution_id, "identity": identity,
                   "files": [_binding(name, data) for name, data in captured.items()], "source_refresh_performed": False})
        write_once(sibling / "capture-index.json", capture_index)
        source_capture_index = _binding(INPUT_RELATIVE + "/" + execution_id + "/capture-index.json", capture_index)
        sink = PhaseSink(directory, identity, progress=progress)
        summary = _run_pipeline(source, identity, sink, pipeline, independent_verify)
        completion = {"schema": "mra-phase7c-execution-completion/1.0", "execution_id": execution_id,
                      "identity": identity, "input_files": inputs, "files": sink.files, "source_capture_index": source_capture_index,
                      "reservation": _binding("reservation.json", _read(directory / "reservation.json")),
                      "summary": summary, "benchmark_executed": True, "completed_at": datetime.now(timezone.utc).isoformat(),
                      "completion_written_last": True, "authorization_effect": "none"}
        data = canonical(completion)
        write_once(store_root / (execution_id + ".seal.json"), canonical({"schema": "mra-phase7c-local-seal/1.0",
                   "execution_id": execution_id, "completion_sha256": sha(data)}))
        write_once(directory / "completion.json", data)
        return {"execution_id": execution_id, "completion_sha256": sha(data), "completion": completion}
    except BaseException as exc:
        incident = {"schema": "mra-phase7c-execution-incident/1.0", "execution_id": execution_id,
                    "reservation_retained": True, "replacement_or_retry_allowed": False,
                    "error_type": type(exc).__name__, "message": str(exc), "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            write_once(directory / "incident.json", canonical(incident))
        except (OSError, ExecutionError):
            pass
        raise


def open_completed(repository, execution_dir, expected_completion_sha256, runtime_path, runtime_sha256,
                   qualification_path, qualification_sha256, replay=True, pipeline=None, independent_verify=None, progress=None):
    root = Path(repository).resolve()
    directory = Path(execution_dir).resolve()
    permitted = _relative(root, STORE_RELATIVE)
    _check_path(directory)
    if directory.parent != permitted or directory.name != execution_identity(runtime_sha256):
        raise ExecutionError("Execution must use separate registered sibling store and identity")
    verify_registration(root)
    verify_runtime(root, runtime_path, runtime_sha256)
    verify_qualification(qualification_path, qualification_sha256, runtime_sha256)
    data = _read(directory / "completion.json")
    if sha(data) != _digest(expected_completion_sha256, "External completion pin"):
        raise ExecutionError("Completion changed from external trusted pin")
    value = _json(data)
    expected_keys = {"schema", "execution_id", "identity", "input_files", "files", "reservation", "summary", "benchmark_executed", "completed_at", "completion_written_last", "authorization_effect", "source_capture_index"}
    if set(value) != expected_keys or value["schema"] != "mra-phase7c-execution-completion/1.0" or value["execution_id"] != directory.name or value["benchmark_executed"] is not True or value["completion_written_last"] is not True or value["authorization_effect"] != "none":
        raise ExecutionError("Malformed execution completion")
    identity = {"preregistration_id": REGISTRATION_ID, "scientific_specification_sha256": SPEC_SHA256,
                "execution_contract_sha256": CONTRACT_SHA256, "runtime_sha256": runtime_sha256,
                "qualification_sha256": qualification_sha256, "source_sha256": SOURCE_SHA256}
    if value["identity"] != identity:
        raise ExecutionError("Execution identity binding changed")
    seal = _json(_read(permitted / (directory.name + ".seal.json")))
    if seal != {"schema": "mra-phase7c-local-seal/1.0", "execution_id": directory.name, "completion_sha256": expected_completion_sha256}:
        raise ExecutionError("Execution local seal changed")
    reservation_data = _verify_file(directory, value["reservation"])
    reservation = _json(reservation_data)
    if (reservation.get("schema") != "mra-phase7c-execution-reservation/1.0" or reservation.get("execution_id") != directory.name
            or reservation.get("identity") != identity or reservation.get("execution_attempts_allowed") != 1
            or type(reservation.get("execution_attempts_allowed")) is not int or reservation.get("replacement_or_retry_allowed") is not False):
        raise ExecutionError("Execution reservation binding changed")
    expected_inputs = {"captured/source.csv", "captured/scientific-preregistration.json", "captured/execution-contract.json", "captured/runtime-freeze.json", "captured/numerical-qualification.json"}
    if type(value["input_files"]) is not list or len(value["input_files"]) != 5 or {x.get("path") for x in value["input_files"]} != expected_inputs:
        raise ExecutionError("Captured input roster changed")
    captured = {item["path"]: _verify_file(directory, item) for item in value["input_files"]}
    expected_hashes = {"captured/source.csv": SOURCE_SHA256, "captured/scientific-preregistration.json": SPEC_SHA256,
                       "captured/execution-contract.json": CONTRACT_SHA256, "captured/runtime-freeze.json": runtime_sha256,
                       "captured/numerical-qualification.json": qualification_sha256}
    if any(sha(captured[name]) != digest for name, digest in expected_hashes.items()):
        raise ExecutionError("Captured input differs from external protocol/runtime/source pin")
    index_path = INPUT_RELATIVE + "/" + directory.name + "/capture-index.json"
    if value["source_capture_index"].get("path") != index_path:
        raise ExecutionError("Source capture must remain in its separate sibling")
    index_data = _verify_file(root, value["source_capture_index"])
    index = _json(index_data)
    if (set(index) != {"execution_id", "identity", "files", "source_refresh_performed"}
            or index["execution_id"] != directory.name or index["identity"] != identity
            or index["source_refresh_performed"] is not False
            or type(index["files"]) is not list or len(index["files"]) != 5):
        raise ExecutionError("Source capture index changed")
    sibling = _relative(root, INPUT_RELATIVE + "/" + directory.name)
    if {item.get("path") for item in index["files"]} != {Path(name).name for name in expected_inputs}:
        raise ExecutionError("Source sibling capture roster changed")
    for item in index["files"]:
        sibling_data = _verify_file(sibling, item)
        if sibling_data != captured["captured/" + item["path"]]:
            raise ExecutionError("Source sibling differs from saved execution capture")
    if type(value["files"]) is not list:
        raise ExecutionError("Malformed stage artifact roster")
    paths = [item.get("path") for item in value["files"]]
    if len(paths) != len(set(paths)) or not all(stage + "/stage-completion.json" in paths for stage in STAGES):
        raise ExecutionError("Duplicate or incomplete stage artifact roster")
    for binding in value["files"]:
        _verify_file(directory, binding)
    expected_roster = set(paths) | expected_inputs | {"reservation.json", "completion.json"}
    actual_roster = {item.relative_to(directory).as_posix() for item in directory.rglob("*") if item.is_file()}
    if actual_roster != expected_roster:
        raise ExecutionError("Unexpected or missing completed-store artifact")
    _validate_summary(value["summary"])
    if replay:
        sink = PhaseSink(directory, identity, expected_files={item["path"]: item for item in value["files"]}, progress=progress)
        summary = _run_pipeline(captured["captured/source.csv"], identity, sink, pipeline, independent_verify)
        if sink.files != value["files"] or canonical(summary) != canonical(value["summary"]):
            raise ExecutionError("Full deterministic verification replay differs")
    return {"execution_id": directory.name, "completion_sha256": sha(data), "completion": value,
            "full_deterministic_replay": bool(replay), "same_captured_bytes": True}


def status(repository, runtime_sha256=None):
    root = Path(repository).resolve()
    directory = _relative(root, STORE_RELATIVE)
    identity = execution_identity(runtime_sha256) if runtime_sha256 else None
    entries = []
    if directory.exists():
        for item in sorted(directory.iterdir()):
            if item.is_dir() and (identity is None or item.name == identity):
                entries.append({"execution_id": item.name, "reserved": (item / "reservation.json").exists(),
                                "completed": (item / "completion.json").exists(), "incident": (item / "incident.json").exists()})
    return {"schema": "mra-phase7c-store-status/1.0", "preregistration_id": REGISTRATION_ID, "executions": entries,
            "authorization_effect": "none", "agency_acceptance": "pending", "agency_practical_margin": None,
            "readiness": "not_evaluable_mandatory_domains_unsupported"}


