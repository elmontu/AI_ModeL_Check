#!/usr/bin/env python3
"""Rehearse trusted local console processes with fictional cases; never deploy cloud resources."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request

ROOT = Path(__file__).absolute().parents[1]
DEFAULT_PLAN = ROOT / "deploy/agency-private-cloud/blueprint.json"
BIND_ADDRESS = "127.0.0.1"
ENVIRONMENTS = ("dev", "staging")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
NONCLAIMS = [
    "This is a trusted single-host public/synthetic fixture rehearsal, not cloud deployment or provider infrastructure-as-code.",
    "Separate local stores do not prove IAM, network isolation, independent custody, hostile-code containment or agency data readiness.",
    "The nonce identifies the owned local test process; it is not worker attestation or production authentication.",
    "Only an incomplete fictional case is submitted by this harness; it does not train, load, assess or deliver a model, and it submits no private data.",
    "Production and private-data admission remain unsupported; the existing console outside this harness is not production-gated by it.",
]

# Port 0 is bound inside the API process. The parent never selects a free port
# then hopes that its child, rather than another process, acquires that port.
API_CHILD = r'''
import json, os, sys
from pathlib import Path
import uvicorn
from model_release_assurance.console.api import create_app
root, ready, nonce = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
app = create_app(root)
identity = {"nonce": nonce, "pid": os.getpid(), "data": str(root), "role": "api"}
@app.get("/_local-rehearsal-identity")
def local_identity():
    return identity
class ReadyServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if not self.started:
            return
        addresses = [sock.getsockname() for server in self.servers for sock in server.sockets]
        if len(addresses) != 1 or addresses[0][0] != "127.0.0.1":
            raise RuntimeError("Unexpected rehearsal listener")
        with ready.open("x", encoding="utf-8") as stream:
            json.dump({**identity, "port": addresses[0][1]}, stream)
ReadyServer(uvicorn.Config(app, host="127.0.0.1", port=0, access_log=False, log_level="warning")).run()
'''

# Observe the real worker's first successful persisted heartbeat. This avoids
# accepting a previous worker's still-fresh heartbeat after a restart.
WORKER_CHILD = r'''
import json, os, sys, time
from pathlib import Path
from model_release_assurance.console.store import Store
from model_release_assurance.console.worker import run
root, ready, nonce = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
original = Store.heartbeat
announced = False
def observed_heartbeat(self, worker):
    global announced
    original(self, worker)
    if not announced:
        with ready.open("x", encoding="utf-8") as stream:
            json.dump({"nonce": nonce, "pid": os.getpid(), "data": str(root), "role": "worker", "worker_id": worker}, stream)
        announced = True
Store.heartbeat = observed_heartbeat
run(root)
'''


class RehearsalError(RuntimeError):
    pass


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_new(path, value):
    with Path(path).open("xb") as stream:
        stream.write(_json_bytes(value))


def _reject_links(path):
    """Inspect every existing ancestor without resolving a link or junction."""
    path = Path(path).absolute()
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RehearsalError("Symlink or reparse point refused: " + str(component))


def prepare_output(root, output):
    root = Path(root).absolute()
    supplied = Path(output)
    if ".." in supplied.parts:
        raise RehearsalError("Output traversal is refused")
    target = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise RehearsalError("Output must be below this repository's .local directory") from error
    if len(relative.parts) < 2 or relative.parts[0] != ".local":
        raise RehearsalError("Output must be a new ignored child of .local")
    _reject_links(target)
    if target.exists():
        raise RehearsalError("Output already exists; retained stores and evidence must not be overwritten")
    check = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "--quiet", "--", relative.as_posix()],
                           capture_output=True, check=False)
    if check.returncode != 0:
        raise RehearsalError("Output is not ignored by Git")
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_links(target.parent)
    target.mkdir(exist_ok=False)
    return target


def load_rehearsal_plan(path):
    """Use the shared strict validator and bind validation to unchanged bytes."""
    path = Path(path)
    _reject_links(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 128 * 1024:
        raise RehearsalError("Plan must be a bounded regular JSON file")
    content = path.read_bytes()
    spec = importlib.util.spec_from_file_location("local_rehearsal_plan_validator", ROOT / "scripts/validate_infrastructure_plan.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    plan = validator.load_plan(path)
    if path.read_bytes() != content:
        raise RehearsalError("Infrastructure plan changed during validation")
    local = plan["local_rehearsal"]
    if local["allowed_environments"] != list(ENVIRONMENTS) or local["bind_address"] != BIND_ADDRESS:
        raise RehearsalError("Only dev/staging loopback rehearsal is supported; production is always refused")
    return plan, content


def source_snapshot(root):
    root = Path(root)
    package = root / "src/model_release_assurance"
    files = set(package.rglob("*.py"))
    files.update(path for path in (package / "console/static").rglob("*") if path.is_file())
    files.update(root / name for name in (
        "scripts/rehearse_local_deployment.py", "scripts/validate_infrastructure_plan.py",
        "pyproject.toml", "requirements.lock", "requirements-experiments.txt", "requirements-console.txt"))
    hashes = {}
    for path in sorted(files):
        _reject_links(path)
        if not path.is_file():
            raise RehearsalError("Required rehearsal source is missing: " + str(path))
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": hashes, "sha256": hashlib.sha256(_json_bytes(hashes)).hexdigest(),
            "scope": "package Python, console static assets, rehearsal/validator scripts and runtime declarations; not a complete build provenance claim"}


def child_environment(root, output):
    # Do not forward developer credentials, proxy settings or arbitrary Python
    # search paths into these public-fixture processes. This is not a sandbox.
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "LANG", "LC_ALL"}}
    temporary = output / "temp"
    temporary.mkdir(exist_ok=True)
    environment.update(PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1",
                       PYTHONNOUSERSITE="1", TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary),
                       OMP_NUM_THREADS="1")
    return environment


def child_python(environment):
    """Retain the real Windows interpreter handle while selecting this venv.

    Windows venv python.exe can be a launcher whose PID differs from the real
    interpreter. Never weaken the readiness PID check or kill by discovered PID.
    Current CPython on Windows uses this same venv-preserving direct launch in
    Lib/multiprocessing/popen_spawn_win32.py (CPython 3.12, lines 57-63):
    https://github.com/python/cpython/blob/3.12/Lib/multiprocessing/popen_spawn_win32.py
    This internal CPython behavior is exercised by the local lifecycle rehearsal.
    """
    environment = dict(environment)
    if os.name == "nt":
        executable = getattr(sys, "_base_executable", None)
        if not executable or not os.path.isabs(executable) or not os.path.isfile(executable):
            raise RehearsalError("Windows rehearsal requires an available absolute base interpreter; venv launcher fallback is refused")
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        return executable, environment
    return sys.executable, environment


class OwnedProcess:
    def __init__(self, process, log, role, environment, data, ready, nonce):
        self.process, self.log = process, log
        self.role, self.environment = role, environment
        self.data, self.ready, self.nonce = data, ready, nonce
        self.port = None
        self.running_expected = True
        self.cleanup_complete = False


def spawn_owned(owners, root, output, environment, role, attempt):
    if environment not in ENVIRONMENTS or role not in {"api", "worker"}:
        raise RehearsalError("Unsupported local process; production is always refused")
    data = output / environment
    data.mkdir(exist_ok=True)
    _reject_links(data)
    nonce = uuid.uuid4().hex
    ready = output / f"{environment}-{role}-{attempt}-ready.json"
    log = (output / f"{environment}-{role}-{attempt}.log").open("x", encoding="utf-8")
    code = API_CHILD if role == "api" else WORKER_CHILD
    try:
        executable, environment_variables = child_python(child_environment(root, output))
        process = subprocess.Popen([executable, "-B", "-c", code, str(data), str(ready), nonce],
                                   cwd=root, env=environment_variables, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except BaseException:
        log.close()
        raise
    owned = OwnedProcess(process, log, role, environment, data, ready, nonce)
    owners.append(owned)  # Register immediately: every successful launch is cleaned up.
    return owned


def read_ready(owned):
    if not owned.ready.exists():
        return None
    _reject_links(owned.ready)
    if owned.ready.stat().st_size > 4096:
        raise RehearsalError("Oversized readiness record")
    try:
        result = json.loads(owned.ready.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None  # A bounded retry permits the initial file write to finish.
    identity = {"pid": owned.process.pid, "nonce": owned.nonce, "role": owned.role, "data": str(owned.data)}
    if not isinstance(result, dict) or any(result.get(key) != value for key, value in identity.items()):
        raise RehearsalError("Readiness identity does not match the owned process")
    if owned.role == "api":
        port = result.get("port")
        if type(port) is not int or not 1 <= port <= 65535:
            raise RehearsalError("Invalid readiness port")
        owned.port = port
    elif not isinstance(result.get("worker_id"), str) or len(result["worker_id"]) != 32:
        raise RehearsalError("Invalid worker heartbeat identity")
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(api, path, payload=None, expected=200):
    if api.role != "api" or api.port is None or not api.running_expected or api.process.poll() is not None:
        raise RehearsalError("HTTP access requires a live owned API")
    url = f"http://{BIND_ADDRESS}:{api.port}{path}"
    data = _json_bytes(payload) if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
        if response.status != expected or len(content) > MAX_RESPONSE_BYTES:
            raise RehearsalError(f"Unexpected HTTP result for {path}: {response.status}")
    return json.loads(content)


def wait_until(predicate, owners, deadline, label):
    while time.monotonic() < deadline:
        for owned in owners:
            if owned.running_expected and owned.process.poll() is not None:
                raise RehearsalError(f"Owned {owned.environment}/{owned.role} exited during {label}")
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise RehearsalError("Timed out: " + label)


def stop_owned(owners):
    """Try every retained handle; failures cannot suppress later cleanup or its receipt."""
    records = []
    for owned in reversed(owners):
        if owned.cleanup_complete:
            continue
        record = {"environment": owned.environment, "role": owned.role, "pid": owned.process.pid,
                  "stopped": False, "cleanup_errors": []}
        try:
            before = owned.process.poll()
            if owned.running_expected and before is not None:
                record["cleanup_errors"].append("Process exited unexpectedly before harness shutdown: " + str(before))
            owned.running_expected = False
            if before is None:
                try:
                    owned.process.terminate()
                    owned.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    owned.process.kill()
                    owned.process.wait(timeout=5)
            record.update(stopped=owned.process.poll() is not None, returncode=owned.process.poll())
        except Exception as error:
            record["cleanup_errors"].append(type(error).__name__ + ": " + str(error))
            try:
                if owned.process.poll() is None:
                    owned.process.kill()
                    owned.process.wait(timeout=5)
                record.update(stopped=owned.process.poll() is not None, returncode=owned.process.poll())
            except Exception as cleanup_error:
                record["cleanup_errors"].append(type(cleanup_error).__name__ + ": " + str(cleanup_error))
        # Log close and socket observation are independent of process shutdown.
        # Neither can skip another owned handle or prevent the failed receipt.
        log_closed = False
        try:
            owned.log.close()
            log_closed = True
        except Exception as error:
            record["cleanup_errors"].append("Log close failed: " + str(error))
        if owned.port is not None:
            record.update(port=owned.port, listener_closed=False)
            try:
                with socket.socket() as probe:
                    probe.settimeout(1)
                    record["listener_closed"] = probe.connect_ex((BIND_ADDRESS, owned.port)) != 0
            except Exception as error:
                record["cleanup_errors"].append("Listener observation failed: " + str(error))
            # A reused port is observed as a failure; its new owner is never killed.
        owned.cleanup_complete = record["stopped"] and log_closed and record.get("listener_closed", True)
        records.append(record)
    return records


def read_worker_heartbeat(data, worker_id):
    # as_uri percent-escapes spaces, # and % in accepted output directory names.
    uri = (Path(data) / "console.sqlite3").absolute().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as database:
        return database.execute("SELECT heartbeat FROM workers WHERE id=?", (worker_id,)).fetchone()


def _check(report, name, condition, **details):
    report["checks"].append({"name": name, "passed": bool(condition), **details})
    if not condition:
        raise RehearsalError("Lifecycle check failed: " + name)


def start_environment(owners, root, output, environment, attempt, deadline, report):
    api = spawn_owned(owners, root, output, environment, "api", attempt)
    ready = wait_until(lambda: read_ready(api), owners, deadline, environment + " API readiness")
    identity = request_json(api, "/_local-rehearsal-identity")
    _check(report, f"{environment}_{attempt}_owned_api_identity",
           identity == {key: ready[key] for key in ("pid", "nonce", "role", "data")}, pid=api.process.pid, port=api.port)
    health = request_json(api, "/healthz")
    _check(report, f"{environment}_{attempt}_health", health == {"status": "ok", "authorization_eligible": False})
    worker = spawn_owned(owners, root, output, environment, "worker", attempt)
    worker_ready = wait_until(lambda: read_ready(worker), owners, deadline, environment + " worker readiness")
    row = read_worker_heartbeat(worker.data, worker_ready["worker_id"])
    _check(report, f"{environment}_{attempt}_fresh_worker_heartbeat",
           row is not None and 0 <= time.time() - row[0] < 30, pid=worker.process.pid, worker_id=worker_ready["worker_id"])
    status = request_json(api, "/api/status")
    _check(report, f"{environment}_{attempt}_worker_online",
           status.get("worker_online") is True and status.get("authorization_eligible") is False)
    catalog = request_json(api, "/api/red-team-tools")
    _check(report, f"{environment}_{attempt}_catalog",
           catalog.get("authorization_eligible") is False and isinstance(catalog.get("discovery_sha256"), str))
    return api, worker


def exercise_lifecycle(root, output, report, owners):
    deadline = time.monotonic() + 90
    dev, dev_worker = start_environment(owners, root, output, "dev", "initial", deadline, report)
    staging, _ = start_environment(owners, root, output, "staging", "initial", deadline, report)
    _check(report, "fresh_distinct_stores", dev.data != staging.data
           and request_json(dev, "/api/cases") == [] and request_json(staging, "/api/cases") == [])
    case = request_json(dev, "/api/cases", {"name": "Fictional public-fixture lifecycle case",
                        "kind": "trained", "route": "named-party-weights", "mode": "education"}, expected=201)
    job = request_json(dev, "/api/jobs", {"kind": "check", "case_id": case["id"]}, expected=202)
    report["fixture"] = {"id": "fictional-empty-case/v1", "classification": "synthetic_metadata_only",
                         "case_id": case["id"], "job_id": job["id"], "job_kind": "check"}
    def completed():
        observed = request_json(dev, "/api/jobs/" + job["id"])
        return observed if observed["state"] in {"completed", "failed"} else None
    finished = wait_until(completed, owners, deadline, "inline preflight completion")
    _check(report, "honest_incomplete_non_authorizing_result", finished["state"] == "completed"
           and finished["result"].get("status") == "inputs_incomplete"
           and finished["result"].get("authorization_eligible") is False)
    _check(report, "staging_cannot_find_dev_case", request_json(staging, "/api/cases") == []
           and request_json(staging, "/api/cases/" + case["id"], expected=404).get("detail") == "case or job not found")
    stopped = stop_owned([dev, dev_worker])
    report["cleanup"].extend(stopped)
    _check(report, "dev_stopped_before_restart", all(item["stopped"] and item.get("listener_closed", True) and not item["cleanup_errors"] for item in stopped))
    dev, _ = start_environment(owners, root, output, "dev", "restart", deadline, report)
    persisted = request_json(dev, "/api/cases/" + case["id"])
    persisted_job = request_json(dev, "/api/jobs/" + job["id"])
    _check(report, "restart_preserves_case_and_job", persisted["id"] == case["id"] and persisted_job == finished)
    _check(report, "restart_preserves_staging_separation", request_json(staging, "/api/cases") == [])


def run_rehearsal(plan_path, output, *, root=ROOT):
    root = Path(root).absolute()
    destination = prepare_output(root, output)
    report = {"schema": "local-deployment-rehearsal/v1", "status": "failed", "environments": list(ENVIRONMENTS),
              "cloud_deployable": False, "authorization_eligible": False, "private_data_admission": False,
              "model_delivery": False, "checks": [], "cleanup": [], "errors": [], "nonclaims": NONCLAIMS,
              "python_version": sys.version, "source_root": str(root), "started_at_unix": time.time()}
    owners = []
    source = None
    plan_content = None
    try:
        _, plan_content = load_rehearsal_plan(plan_path)
        report["plan_sha256"] = hashlib.sha256(plan_content).hexdigest()
        with (destination / "plan.json").open("xb") as stream:
            stream.write(plan_content)
        source = source_snapshot(root)
        report["source"] = source
        exercise_lifecycle(root, destination, report, owners)
    except (Exception, KeyboardInterrupt) as error:
        report["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        # An unexpected cleanup implementation error must not replace the primary
        # failure or prevent attempts to stop every other retained handle.
        for owned in reversed(owners):
            try:
                report["cleanup"].extend(stop_owned([owned]))
            except Exception as error:
                report["errors"].append("Unexpected cleanup failure: " + str(error))
        for record in report["cleanup"]:
            if not record["stopped"] or not record.get("listener_closed", True) or record.get("cleanup_errors"):
                report["errors"].append("Owned process/listener cleanup could not be verified: " + record["environment"] + "/" + record["role"])
        try:
            if source is not None and source_snapshot(root) != source:
                report["errors"].append("Rehearsal source changed during execution")
            if plan_content is not None and Path(plan_path).read_bytes() != plan_content:
                report["errors"].append("Infrastructure plan changed during execution")
        except Exception as error:
            report["errors"].append("Final input verification failed: " + str(error))
        report["finished_at_unix"] = time.time()
        if not report["errors"] and report["checks"] and all(item["passed"] for item in report["checks"]):
            report["status"] = "passed"
        _write_new(destination / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, required=True, help="New ignored directory below this repository's .local")
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(args.plan, args.output)
    except (OSError, RehearsalError) as error:
        print(json.dumps({"status": "refused", "error": str(error), "cloud_deployable": False, "authorization_eligible": False}))
        return 2
    print(json.dumps({key: result[key] for key in ("status", "cloud_deployable", "authorization_eligible", "errors")}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
