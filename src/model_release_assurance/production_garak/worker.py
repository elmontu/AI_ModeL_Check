"""Fixed trusted garak worker: pinned prepare, live run, and inert JSON evidence."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, strict_json
from . import protocol as p
from .runtime import probe_runtime, expected_binding, LOCKED_VERSIONS, GarakRuntimeUnavailable
from .execution import source_snapshot
from . import upstream

MAX_INPUT = p.MAX_BYTES
MAX_OUTPUT = p.MAX_BYTES


def validate_request(value, *, mode=None):
    request = p.owned(value)
    p.exact(request, {"schema", "mode", "versions", "source_sha256", "lock_sha256", "model", "plan"})
    if request["schema"] != "mra-garak-worker-request/v1" or request["mode"] not in ("prepare", "run"):
        raise ValueError("Only the fixed prepare and run worker requests are supported")
    if mode is not None and request["mode"] != mode:
        raise ValueError("The requested worker phase does not match")
    if canonical_bytes(request["versions"]) != canonical_bytes(LOCKED_VERSIONS):
        raise ValueError("The exact declared component dependency roster is required")
    p.validate_model(request["model"])
    p._hex(request["source_sha256"])
    p._hex(request["lock_sha256"])
    if request["mode"] == "prepare":
        if request["plan"] is not None:
            raise ValueError("A prepare request cannot contain a caller plan")
    else:
        plan = p.validate_plan(request["plan"])
        if (canonical_bytes(plan["model"]) != canonical_bytes(request["model"])
                or plan["source_sha256"] != request["source_sha256"]
                or plan["lock_sha256"] != request["lock_sha256"]):
            raise ValueError("The run request and prepared plan bindings disagree")
    return request


def _before(request):
    source = source_snapshot()
    if p.sha(source) != request["source_sha256"]:
        raise ValueError("The trusted garak implementation changed")
    runtime = probe_runtime(request["versions"])
    if canonical_bytes(runtime) != canonical_bytes(expected_binding()):
        raise ValueError("The selected garak component binding changed")
    return source, runtime


def _after(request, source, runtime):
    if (canonical_bytes(probe_runtime(request["versions"])) != canonical_bytes(runtime)
            or canonical_bytes(source_snapshot()) != canonical_bytes(source)):
        raise ValueError("The trusted source or component runtime changed during the phase")


def _common(request, runtime):
    return {"schema": "mra-garak-worker-output/v1", "mode": request["mode"],
            "runtime": runtime, "versions": request["versions"], "source_sha256": request["source_sha256"],
            "lock_sha256": request["lock_sha256"], "model": request["model"], **p.FLAGS}


def prepare_request(value):
    request = validate_request(value, mode="prepare")
    source, runtime = _before(request)
    corpus = upstream.build_corpus()  # Constructor and bundled resources only; no target calls.
    plan = p.make_plan(corpus, model=request["model"], runtime=runtime,
                       source_sha256=request["source_sha256"], lock_sha256=request["lock_sha256"])
    _after(request, source, runtime)
    return {**_common(request, runtime), "status": "prepared", "plan": plan, "target_calls": 0}


def run_request(value, *, client=None):
    request = validate_request(value, mode="run")
    source, runtime = _before(request)
    plan = p.make_plan(upstream.build_corpus(), model=request["model"], runtime=runtime,
                       source_sha256=request["source_sha256"], lock_sha256=request["lock_sha256"])
    if canonical_bytes(plan) != canonical_bytes(request["plan"]):
        raise ValueError("The frozen plan no longer matches the actual upstream corpus")
    campaign = upstream.run_campaign(plan, client=client)
    summary = p.replay_campaign(plan, campaign)
    _after(request, source, runtime)
    result = {**_common(request, runtime), "status": summary["status"], "plan_sha256": p.sha(plan),
              "campaign": campaign, "replay": summary}
    p.replay(plan, result)
    return result


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        return 2
    input_path, expected_sha256, output_directory = args
    output = Path(output_directory)
    try:
        native._real_directory(output)
        raw = native._read(Path(input_path), MAX_INPUT)
        if hashlib.sha256(raw).hexdigest() != p._hex(expected_sha256):
            raise ValueError("The owned worker request bytes changed")
        request = strict_json(raw, maximum=MAX_INPUT)
        request = validate_request(request)
        result = prepare_request(request) if request["mode"] == "prepare" else run_request(request)
        native._write(output / "worker.json", result)
        # Valid retained incomplete diagnostics must reach independent parent replay.
        return 0
    except Exception as exc:
        error = {"schema": "mra-garak-worker-error/v1", "status": "unavailable" if isinstance(exc, GarakRuntimeUnavailable) else "failed",
                 "error_type": type(exc).__name__, **p.FLAGS}
        try:
            native._write(output / "error.json", error)
        except Exception:
            pass
        return 3 if isinstance(exc, GarakRuntimeUnavailable) else 2


if __name__ == "__main__":
    raise SystemExit(main())
