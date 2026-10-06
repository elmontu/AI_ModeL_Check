"""Frozen retained-loss ART execution and independent replay; never clearance."""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
from . import runtime
from .protocol import prepare_input, frozen_splits, compare_repetitions, UnsupportedProfile
from .execution import run_worker, source_snapshot, runtime_descriptor
from .worker import validate_request
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, parse_plan, strict_json
from ..production_evidence.replay import artifact_manifest
from ..production_registration.profiles import profile_descriptor

FLAGS = {**native.FLAGS, "assessment_eligible": False, "external_execution_attested": False}
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write(path, value):
    encoded = canonical_bytes(value) + b"\n"
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ValueError("ART artifact exceeds its byte bound")
    with Path(path).open("xb") as stream:
        stream.write(encoded)


def expected_binding():
    return runtime.expected_binding()


def _request(prepared, versions, source, lock_sha256):
    request = {"schema": "mra-art-worker-request/v1", "prepared": prepared,
        "versions": copy.deepcopy(versions), "source_sha256": digest(source),
        "lock_sha256": lock_sha256}
    validate_request(request)
    return request


def _plan(prepared, request, descriptor):
    return {"schema": "mra-art-frozen-comparison/v1", "prepared_sha256": digest(prepared),
        "source_sha256": request["source_sha256"], "lock_sha256": request["lock_sha256"],
        "runtime_binding": expected_binding(), "runtime_versions": copy.deepcopy(request["versions"]),
        "runtime_descriptor": copy.deepcopy(descriptor),
        "attack_parameters": copy.deepcopy(runtime.ATTACK_PARAMETERS),
        "protocol": copy.deepcopy(prepared["protocol"]), "splits": frozen_splits(prepared),
        "required_cases": ["target", "positive", "null"], **FLAGS}


def _prepared(blobs, profile_id):
    owned = dict(blobs)
    plan = parse_plan(owned["plan.json"])
    if plan.source_sha256 != profile_descriptor(profile_id)["expected_source_sha256"]:
        raise ValueError("Requested profile differs from captured native source")
    prepared = prepare_input(owned)
    if prepared["profile_id"] != profile_id:
        raise ValueError("Requested profile differs from replayed native identity")
    return prepared


def verify_worker(prepared, request, result):
    """Check exact bindings and independently replay/recompute every repetition."""
    fields = {"schema", "status", "prepared_sha256", "runtime", "versions", "source_sha256",
        "lock_sha256", "cases", "fixture_only", "can_clear", "assessment_eligible",
        "authorization_eligible", "production_authorized"}
    if type(result) is not dict or set(result) != fields:
        raise ValueError("ART worker output fields rejected")
    expected = {"schema": "mra-art-worker-output/v1", "status": "completed",
        "prepared_sha256": digest(prepared), "runtime": expected_binding(),
        "versions": request["versions"], "source_sha256": request["source_sha256"],
        "lock_sha256": request["lock_sha256"], "fixture_only": True, "can_clear": False,
        "assessment_eligible": False, "authorization_eligible": False, "production_authorized": False}
    if canonical_bytes({key: result[key] for key in expected}) != canonical_bytes(expected):
        raise ValueError("ART worker binding rejected")
    if type(result["cases"]) is not dict or set(result["cases"]) != {"target", "positive", "null"}:
        raise ValueError("Required ART attack or control missing")
    compared = {name: compare_repetitions(prepared, name, result["cases"][name])
                for name in ("target", "positive", "null")}
    if any(compared[name]["controls_satisfied"] is not True for name in ("positive", "null")):
        raise ValueError("Required ART learner-path controls failed")
    return compared


def _read_json(path):
    raw = native._read(Path(path), MAX_ARTIFACT_BYTES)
    value = strict_json(raw, maximum=MAX_ARTIFACT_BYTES)
    if raw != canonical_bytes(value) + b"\n":
        raise ValueError("Frozen ART artifact byte representation changed")
    return value



def validate_process(value, request, descriptor):
    """Bind bounded retained process metadata; this is not execution attestation."""
    fields = {"status", "input_sha256", "source_sha256", "runtime_descriptor", "exit_code",
        "cleanup_confirmed", "stdout_bytes", "stderr_bytes", "elapsed_seconds",
        "hostile_code_isolated", "network_isolated", "filesystem_isolated", "resource_limits_verified"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("ART process fields rejected")
    fixed = {"status": "completed", "input_sha256": hashlib.sha256(canonical_bytes(request) + b"\n").hexdigest(),
        "source_sha256": request["source_sha256"], "runtime_descriptor": descriptor,
        "exit_code": 0, "cleanup_confirmed": True, "hostile_code_isolated": False,
        "network_isolated": False, "filesystem_isolated": False, "resource_limits_verified": False}
    if canonical_bytes({key: value[key] for key in fixed}) != canonical_bytes(fixed):
        raise ValueError("ART process binding rejected")
    for key in ("stdout_bytes", "stderr_bytes"):
        if type(value[key]) is not int or not 0 <= value[key] <= 65536:
            raise ValueError("ART process output count rejected")
    elapsed = value["elapsed_seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= 3600:
        raise ValueError("ART process duration rejected")
    names = {"python", "launcher_sha256", "base_python", "base_sha256", "site_packages", "configuration_sha256"}
    if type(descriptor) is not dict or set(descriptor) != names:
        raise ValueError("ART runtime descriptor rejected")
    for key, item in descriptor.items():
        if type(item) is not str or not 1 <= len(item) <= 4096:
            raise ValueError("ART runtime descriptor field rejected")
        if key.endswith("sha256") and (len(item) != 64 or any(char not in "0123456789abcdef" for char in item)):
            raise ValueError("ART runtime descriptor digest rejected")


def replay_comparison(blobs, *, profile_id, output, versions, lock_sha256):
    """Replay saved local comparison bindings, without authenticating execution."""
    destination = Path(output)
    prepared = _prepared(blobs, profile_id)
    source = source_snapshot()
    request = _request(prepared, versions, source, lock_sha256)
    retained_plan = _read_json(destination / "plan.json")
    descriptor = runtime_descriptor(retained_plan["runtime_descriptor"]["python"])
    plan = _plan(prepared, request, descriptor)
    if canonical_bytes(_read_json(destination / "input.json")) != canonical_bytes(request):
        raise ValueError("Saved ART input binding changed")
    if canonical_bytes(_read_json(destination / "plan.json")) != canonical_bytes(plan):
        raise ValueError("Saved ART frozen plan changed")
    worker = _read_json(destination / "worker/worker.json")
    comparison = verify_worker(prepared, request, worker)
    if canonical_bytes(_read_json(destination / "comparison.json")) != canonical_bytes(comparison):
        raise ValueError("Saved independent ART comparison changed")
    process = _read_json(destination / "worker/process.json")
    validate_process(process, request, descriptor)
    receipt = _read_json(destination / "result.json")
    fields = {"schema", "profile_id", "status", "error", "comparison", "process",
              "plan_sha256", "prepared_sha256", "worker_output_sha256", *FLAGS}
    if (type(receipt) is not dict or set(receipt) != fields
            or receipt["schema"] != "mra-art-comparison-result/v1"
            or receipt["profile_id"] != profile_id or receipt["status"] != "completed"
            or receipt["error"] is not None or receipt["plan_sha256"] != digest(plan)
            or receipt["prepared_sha256"] != digest(prepared)
            or receipt["worker_output_sha256"] != digest(worker)
            or canonical_bytes(receipt["comparison"]) != canonical_bytes(comparison)
            or any(receipt[key] is not value for key, value in FLAGS.items())
            or canonical_bytes(receipt["process"]) != canonical_bytes(process)):
        raise ValueError("Saved ART receipt rejected")
    if source_snapshot() != source or runtime_descriptor(descriptor["python"]) != descriptor:
        raise ValueError("ART comparison replay source or runtime changed")
    return {"schema": "mra-art-native-comparison-link/v1", "status": "bound_local_replay",
        "profile_id": profile_id, "native_artifacts_sha256": digest(artifact_manifest(blobs)),
        "prepared_sha256": digest(prepared), "plan_sha256": digest(plan),
        "worker_output_sha256": digest(worker), "comparison_sha256": digest(comparison),
        "verification_scope": "local_numerical_consistency_not_execution_attestation_or_scientific_acceptance",
        **FLAGS}


def run_comparison(blobs, *, profile_id, output, python, versions, lock_sha256):
    destination = native._new_output(output)
    result = {"schema": "mra-art-comparison-result/v1", "profile_id": profile_id,
        "status": "failed", "error": None, "comparison": None, "process": None, **FLAGS}
    try:
        prepared = _prepared(blobs, profile_id)
        source = source_snapshot()
        request = _request(prepared, versions, source, lock_sha256)
        descriptor = runtime_descriptor(python)
        plan = _plan(prepared, request, descriptor)
        write(destination / "plan.json", plan)
        write(destination / "input.json", request)
        result.update(plan_sha256=digest(plan), prepared_sha256=digest(prepared))
        execution = run_worker(python, destination / "input.json", destination / "worker")
        if type(execution) is not dict:
            raise ValueError("ART execution disposition rejected")
        process = dict(execution)
        worker = process.pop("result", None)
        if len(canonical_bytes(process)) > MAX_ARTIFACT_BYTES:
            raise ValueError("ART process diagnostic exceeds its byte bound")
        result["process"] = process
        if process.get("status") != "completed" or process.get("cleanup_confirmed") is not True:
            result["status"] = process.get("status") if process.get("status") in {"timed_out", "unavailable", "unsupported"} else "failed"
            raise ValueError("ART execution did not complete with confirmed cleanup")
        validate_process(process, request, descriptor)
        if canonical_bytes(_read_json(destination / "worker/process.json")) != canonical_bytes(process):
            raise ValueError("Saved ART process metadata changed")
        comparison = verify_worker(prepared, request, worker)
        if source_snapshot() != source or runtime_descriptor(python) != descriptor:
            raise ValueError("ART source changed after comparison")
        for filename, value in (("plan.json", plan), ("input.json", request), ("worker/worker.json", worker)):
            if native._read(destination / filename, MAX_ARTIFACT_BYTES) != canonical_bytes(value) + b"\n":
                raise ValueError("Frozen ART comparison artifact changed")
        result.update(status="completed", comparison=comparison, worker_output_sha256=digest(worker))
        write(destination / "comparison.json", comparison)
    except UnsupportedProfile as error:
        result.update(status="unsupported", error={"type": type(error).__name__, "code": error.code})
    except (ModuleNotFoundError, ImportError) as error:
        result.update(status="unavailable", error={"type": type(error).__name__, "stage": "external_comparison"})
    except Exception as error:
        if result["status"] == "completed":
            result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "stage": "external_comparison"}
    write(destination / "result.json", result)
    return result
