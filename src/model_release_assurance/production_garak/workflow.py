"""Frozen local garak preparation, bounded execution and independent replay."""
from __future__ import annotations
import copy
import hashlib
import math
from pathlib import Path
from . import protocol, runtime
from .execution import source_snapshot, runtime_descriptor, run_worker
from .worker import validate_request
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, strict_json

FLAGS = {**protocol.FLAGS, "external_execution_attested": False}
MAX_BYTES = protocol.MAX_BYTES


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write(path, value):
    raw = canonical_bytes(value) + b"\n"
    if len(raw) > MAX_BYTES:
        raise ValueError("Garak artifact exceeds its byte bound")
    with Path(path).open("xb") as stream:
        stream.write(raw)


def _read(path):
    raw = native._read(Path(path), MAX_BYTES)
    value = strict_json(raw, maximum=MAX_BYTES)
    if raw != canonical_bytes(value) + b"\n":
        raise ValueError("Frozen garak artifact bytes changed")
    return value


def _same(left, right):
    if canonical_bytes(left) != canonical_bytes(right):
        raise ValueError("Garak retained binding changed")


def _timeout(value):
    if type(value) is not int or not 1 <= value <= 600:
        raise ValueError("A process timeout between one and 600 seconds is required")
    return value


def _request(mode, versions, source, lock_sha256, plan=None):
    request = {"schema": "mra-garak-worker-request/v1", "mode": mode,
        "versions": copy.deepcopy(versions), "source_sha256": digest(source),
        "lock_sha256": lock_sha256, "model": dict(protocol.MODEL), "plan": copy.deepcopy(plan)}
    validate_request(request)
    return request


def _intent(versions, source, lock_sha256, descriptor, timeout_seconds):
    return {"schema": "mra-garak-frozen-intent/v1", "model": dict(protocol.MODEL),
        "source_sha256": digest(source), "runtime_binding_expected": runtime.expected_binding(),
        "versions": copy.deepcopy(versions), "lock_sha256": lock_sha256,
        "runtime_descriptor": copy.deepcopy(descriptor), "process_timeout_seconds": timeout_seconds,
        "bounds": dict(protocol.BOUNDS), "interfaces": list(protocol.INTERFACES),
        "selection": "fixed_upstream_indices_all_interfaces_and_required_controls_no_outcome_selection", **FLAGS}


def validate_process(value, request, descriptor):
    """Validate retained process metadata without asserting an external attestation."""
    fields = {"status", "input_sha256", "source_sha256", "runtime_descriptor", "exit_code",
        "cleanup_confirmed", "stdout_bytes", "stderr_bytes", "elapsed_seconds", "hostile_code_isolated",
        "network_isolated", "filesystem_isolated", "resource_limits_verified"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Garak process fields rejected")
    fixed = {"status": "completed", "input_sha256": hashlib.sha256(canonical_bytes(request) + b"\n").hexdigest(),
        "source_sha256": request["source_sha256"], "runtime_descriptor": descriptor,
        "exit_code": 0, "cleanup_confirmed": True, "hostile_code_isolated": False,
        "network_isolated": False, "filesystem_isolated": False, "resource_limits_verified": False}
    _same({key: value[key] for key in fixed}, fixed)
    for key in ("stdout_bytes", "stderr_bytes"):
        if type(value[key]) is not int or not 0 <= value[key] <= 65536:
            raise ValueError("Garak process output count rejected")
    elapsed = value["elapsed_seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= 3600:
        raise ValueError("Garak process duration rejected")
    names = {"python", "launcher_sha256", "base_python", "base_sha256", "site_packages", "configuration_sha256"}
    if type(descriptor) is not dict or set(descriptor) != names:
        raise ValueError("Garak runtime descriptor rejected")
    for key, value in descriptor.items():
        if type(value) is not str or not 1 <= len(value) <= 4096:
            raise ValueError("Garak runtime descriptor field rejected")
        if key.endswith("sha256") and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)):
            raise ValueError("Garak runtime descriptor digest rejected")


def _stage(destination, mode, request, python, descriptor, timeout_seconds):
    stage = destination / mode
    stage.mkdir()
    write(stage / "input.json", request)
    execution = run_worker(python, stage / "input.json", stage / "worker", timeout_seconds=timeout_seconds)
    if type(execution) is not dict:
        raise ValueError("Garak process disposition rejected")
    process = dict(execution)
    result = process.pop("result", None)
    # Admit bounded plain JSON before allowing a diagnostic into the final receipt.
    if len(canonical_bytes(process)) > MAX_BYTES:
        raise ValueError("Garak process diagnostic exceeds its byte bound")
    if process.get("status") != "completed" or process.get("cleanup_confirmed") is not True:
        return process, None
    validate_process(process, request, descriptor)
    _same(_read(stage / "worker/process.json"), process)
    _same(_read(stage / "input.json"), request)
    _same(_read(stage / "worker/worker.json"), result)
    return process, result


def _common(request):
    return {"schema": "mra-garak-worker-output/v1", "runtime": runtime.expected_binding(),
        "versions": request["versions"], "source_sha256": request["source_sha256"],
        "lock_sha256": request["lock_sha256"], "model": request["model"], **protocol.FLAGS}


def verify_prepare(request, value):
    fixed = {**_common(request), "mode": "prepare", "status": "prepared", "target_calls": 0}
    protocol.exact(value, set(fixed) | {"plan"})
    _same({key: value[key] for key in fixed}, fixed)
    plan = protocol.validate_plan(value["plan"])
    for key, expected in (("runtime", fixed["runtime"]), ("source_sha256", fixed["source_sha256"]),
                          ("lock_sha256", fixed["lock_sha256"]), ("model", fixed["model"])):
        _same(plan[key], expected)
    return plan


def verify_run(request, value):
    fixed = {**_common(request), "mode": "run", "plan_sha256": digest(request["plan"])}
    protocol.exact(value, set(fixed) | {"status", "campaign", "replay"})
    _same({key: value[key] for key in fixed}, fixed)
    if value["status"] not in ("completed", "incomplete"):
        raise ValueError("Garak campaign status rejected")
    replayed = protocol.replay(request["plan"], value)
    _same(replayed, value["replay"])
    if replayed["status"] != value["status"]:
        raise ValueError("Garak campaign completion claim changed")
    return replayed


def _disposition(process):
    status = process.get("status")
    return status if status in ("timed_out", "unavailable", "unsupported") else "failed"


def run_campaign(*, python, output, versions, lock_sha256, timeout_seconds=600):
    _timeout(timeout_seconds)
    destination = native._new_output(output)
    result = {"schema": "mra-garak-campaign-result/v1", "status": "failed", "stage": "initial",
        "error": None, "plan_sha256": None, "replay": None,
        "worker_output_sha256": {"prepare": None, "run": None},
        "processes": {"prepare": None, "run": None}, "source_unchanged": False, **FLAGS}
    try:
        source, descriptor = source_snapshot(), runtime_descriptor(python)
        intent = _intent(versions, source, lock_sha256, descriptor, timeout_seconds)
        request = _request("prepare", versions, source, lock_sha256)
        write(destination / "intent.json", intent)
        result["stage"] = "prepare"
        process, prepared = _stage(destination, "prepare", request, python, descriptor, timeout_seconds)
        result["processes"]["prepare"] = process
        if prepared is None:
            result["status"] = _disposition(process)
            raise ValueError("Garak plan preparation did not complete")
        plan = verify_prepare(request, prepared)
        result["worker_output_sha256"]["prepare"] = digest(prepared)
        if source_snapshot() != source or runtime_descriptor(python) != descriptor:
            raise ValueError("Garak source or runtime changed during preparation")
        _same(_read(destination / "intent.json"), intent)
        write(destination / "plan.json", plan)
        result["plan_sha256"] = digest(plan)
        request = _request("run", versions, source, lock_sha256, plan)
        result["stage"] = "run"
        process, executed = _stage(destination, "run", request, python, descriptor, timeout_seconds)
        result["processes"]["run"] = process
        if executed is None:
            result["status"] = _disposition(process)
            raise ValueError("Garak campaign execution did not complete")
        replayed = verify_run(request, executed)
        result["worker_output_sha256"]["run"] = digest(executed)
        _same(_read(destination / "plan.json"), plan)
        _same(_read(destination / "intent.json"), intent)
        result["source_unchanged"] = source_snapshot() == source and runtime_descriptor(python) == descriptor
        if not result["source_unchanged"]:
            raise ValueError("Garak source or runtime changed during execution")
        write(destination / "replay.json", replayed)
        result.update(status=replayed["status"], stage="replayed", replay=replayed)
    except (ImportError, ModuleNotFoundError) as error:
        result.update(status="unavailable", error={"type": type(error).__name__, "stage": result["stage"]})
    except Exception as error:
        if result["status"] in ("completed", "incomplete"):
            result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "stage": result["stage"]}
    write(destination / "result.json", result)
    return result


def replay_campaign(*, output, versions, lock_sha256):
    """Independently replay saved local bindings; no provider calls or attestation."""
    destination = Path(output)
    source = source_snapshot()
    retained_intent = _read(destination / "intent.json")
    descriptor = runtime_descriptor(retained_intent["runtime_descriptor"]["python"])
    timeout_seconds = _timeout(retained_intent["process_timeout_seconds"])
    intent = _intent(versions, source, lock_sha256, descriptor, timeout_seconds)
    _same(retained_intent, intent)
    prepare_request = _request("prepare", versions, source, lock_sha256)
    _same(_read(destination / "prepare/input.json"), prepare_request)
    prepared = _read(destination / "prepare/worker/worker.json")
    plan = verify_prepare(prepare_request, prepared)
    _same(_read(destination / "plan.json"), plan)
    prepare_process = _read(destination / "prepare/worker/process.json")
    validate_process(prepare_process, prepare_request, descriptor)
    run_request = _request("run", versions, source, lock_sha256, plan)
    _same(_read(destination / "run/input.json"), run_request)
    executed = _read(destination / "run/worker/worker.json")
    replayed = verify_run(run_request, executed)
    _same(_read(destination / "replay.json"), replayed)
    run_process = _read(destination / "run/worker/process.json")
    validate_process(run_process, run_request, descriptor)
    expected_result = {"schema": "mra-garak-campaign-result/v1", "status": replayed["status"], "stage": "replayed",
        "error": None, "plan_sha256": digest(plan), "replay": replayed,
        "worker_output_sha256": {"prepare": digest(prepared), "run": digest(executed)},
        "processes": {"prepare": prepare_process, "run": run_process}, "source_unchanged": True, **FLAGS}
    _same(_read(destination / "result.json"), expected_result)
    if source_snapshot() != source or runtime_descriptor(descriptor["python"]) != descriptor:
        raise ValueError("Garak replay source or runtime changed")
    return {"schema": "mra-garak-retained-campaign-link/v1", "status": "bound_local_replay",
        "campaign_status": replayed["status"], "plan_sha256": digest(plan),
        "worker_output_sha256": expected_result["worker_output_sha256"], "replay_sha256": digest(replayed),
        "verification_scope": "local_literal_metric_consistency_not_execution_attestation_or_scientific_acceptance",
        **FLAGS}
