"""Fixed pinned PyRIT prepare/run worker; no substitute orchestration."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, strict_json
from . import protocol as p
from .runtime import probe_runtime, expected_binding, LOCKED_VERSIONS, PyritRuntimeUnavailable
from .execution import source_snapshot
from . import upstream
MAX_INPUT = p.MAX_BYTES
MAX_OUTPUT = p.MAX_BYTES


def validate_request(value, *, mode=None):
    request = p.owned(value)
    p.exact(request, {"schema", "mode", "versions", "source_sha256", "lock_sha256", "model", "plan"})
    if request["schema"] != "mra-pyrit-worker-request/v1" or request["mode"] not in ("prepare", "run"):
        raise ValueError("Only fixed PyRIT prepare and run requests are supported")
    if mode is not None and request["mode"] != mode: raise ValueError("Worker phase mismatch")
    p.same(request["versions"], LOCKED_VERSIONS); p.validate_model(request["model"])
    p._hex(request["source_sha256"]); p._hex(request["lock_sha256"])
    if request["mode"] == "prepare":
        if request["plan"] is not None: raise ValueError("Prepare cannot contain a caller plan")
    else:
        plan = p.validate_plan(request["plan"])
        p.same(plan["model"], request["model"])
        if plan["source_sha256"] != request["source_sha256"] or plan["lock_sha256"] != request["lock_sha256"]:
            raise ValueError("Frozen run bindings disagree")
    return request


def _before(request):
    source = source_snapshot()
    if p.sha(source) != request["source_sha256"]: raise ValueError("Trusted PyRIT adapter changed")
    runtime = probe_runtime(request["versions"]); p.same(runtime, expected_binding())
    return source, runtime


def _after(request, source, runtime):
    p.same(probe_runtime(request["versions"]), runtime); p.same(source_snapshot(), source)
    return upstream.check_paths()


def _common(request, runtime, path_binding):
    return {"schema": "mra-pyrit-worker-output/v1", "mode": request["mode"], "runtime": runtime,
        "versions": request["versions"], "source_sha256": request["source_sha256"], "lock_sha256": request["lock_sha256"],
        "model": request["model"], "path_binding": path_binding, **p.FLAGS}


def prepare_request(value):
    request = validate_request(value, mode="prepare"); source, runtime = _before(request)
    plan = p.make_plan(model=request["model"], runtime=runtime, source_sha256=request["source_sha256"],
        lock_sha256=request["lock_sha256"], identifiers=upstream.build_identifiers())
    binding = _after(request, source, runtime)
    return {**_common(request, runtime, binding), "status": "prepared", "plan": plan, "target_calls": 0}


def run_request(value, *, client=None):
    request = validate_request(value, mode="run"); source, runtime = _before(request)
    plan = p.make_plan(model=request["model"], runtime=runtime, source_sha256=request["source_sha256"],
        lock_sha256=request["lock_sha256"], identifiers=upstream.build_identifiers())
    p.same(plan, request["plan"])
    campaign = upstream.run_campaign(plan, client=client); summary = p.replay_campaign(plan, campaign)
    binding = _after(request, source, runtime)
    result = {**_common(request, runtime, binding), "status": summary["status"], "plan_sha256": p.sha(plan), "campaign": campaign, "replay": summary}
    p.replay(plan, result); return result


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3: return 2
    input_path, expected_sha256, output_directory = args; output = Path(output_directory)
    try:
        native._real_directory(output); raw = native._read(Path(input_path), MAX_INPUT)
        if hashlib.sha256(raw).hexdigest() != p._hex(expected_sha256): raise ValueError("Owned request bytes changed")
        request = validate_request(strict_json(raw, maximum=MAX_INPUT))
        result = prepare_request(request) if request["mode"] == "prepare" else run_request(request)
        native._write(output / "worker.json", result)
        return 0
    except Exception as exc:
        unavailable = isinstance(exc, PyritRuntimeUnavailable)
        try: native._write(output / "error.json", {"schema": "mra-pyrit-worker-error/v1", "status": "unavailable" if unavailable else "failed", "error_type": type(exc).__name__, **p.FLAGS})
        except Exception: pass
        return 3 if unavailable else 2


if __name__ == "__main__": raise SystemExit(main())
