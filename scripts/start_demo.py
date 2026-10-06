#!/usr/bin/env python3
"""Install once, then start the local public-data web console and worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKER = "mra-demo-install.json"
INPUTS = ("requirements.lock", "requirements-experiments.txt", "requirements-console.txt",
          "pyproject.toml", "scripts/setup_pipeline.py")

PROBE = r'''
import importlib, json, sys, tomllib
from importlib import metadata
from pathlib import Path
try:
    from packaging.requirements import Requirement
except ModuleNotFoundError:
    from pip._vendor.packaging.requirements import Requirement
root, target = map(lambda value: Path(value).resolve(), sys.argv[1:])
if Path(sys.prefix).resolve() != target:
    raise RuntimeError("Python does not belong to the selected demo environment")
if sys.version_info < (3, 11):
    raise RuntimeError("Demo environment requires Python 3.11 or newer")
package = importlib.import_module("model_release_assurance")
if Path(package.__file__).resolve() != root / "src/model_release_assurance/__init__.py":
    raise RuntimeError("Installed MRA package belongs to another checkout")
requirements = []
for name in ("requirements.lock", "requirements-experiments.txt", "requirements-console.txt"):
    requirements.extend(line.strip() for line in (root/name).read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.lstrip().startswith("#"))
project = tomllib.loads((root/"pyproject.toml").read_text(encoding="utf-8"))["project"]
requirements.extend(project["dependencies"])
for extra in ("experiments", "console"):
    requirements.extend(project["optional-dependencies"][extra])
versions = {}
for text in requirements:
    req = Requirement(text)
    if req.marker is not None and not req.marker.evaluate():
        continue
    version = metadata.version(req.name)
    if req.specifier and version not in req.specifier:
        raise RuntimeError(f"{req.name} {version} does not satisfy {req.specifier}")
    versions[req.name] = version
for name in ("cryptography", "jwt", "pydantic", "fastapi", "uvicorn", "httpx",
             "joblib", "numpy", "pandas", "pyarrow", "sklearn", "scipy", "xgboost",
             "model_release_assurance.console.api", "model_release_assurance.console.worker"):
    importlib.import_module(name)
print(json.dumps({"status":"verified", "python":sys.executable, "prefix":str(target),
                  "source":str(Path(package.__file__).resolve()), "versions":versions}, sort_keys=True))
'''


def installation_binding() -> dict:
    return {"schema": "mra-local-demo-install/v1", "repository": str(ROOT.resolve()),
            "inputs": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in INPUTS}}


def environment_python(target: Path) -> Path:
    return target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _process_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(PIP_NO_CACHE_DIR="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", PYTHONSAFEPATH="1")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return environment


def install_environment(target: Path, wheelhouse: Path | None) -> None:
    temporary = ROOT / ".local/demo-install-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment = _process_environment()
    environment.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    command = [sys.executable, "-B", str(ROOT/"scripts/setup_pipeline.py"),
               "--profile", "console", "--venv", str(target)]
    if wheelhouse is not None:
        command.extend(["--wheelhouse", str(wheelhouse)])
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def validate_environment(target: Path) -> dict:
    python = environment_python(target)
    if not python.is_file():
        raise ValueError("Demo environment Python is missing; choose a new --venv path")
    environment = _process_environment()
    commands = ([str(python), "-I", "-B", "-c", PROBE, str(ROOT), str(target)],
                [str(python), "-I", "-B", "-m", "pip", "check"])
    results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise ValueError("Demo environment validation failed: " + (detail[-1] if detail else "no diagnostic"))
        results.append(result.stdout)
    return json.loads(results[0])


def launch_console(target: Path, data: Path, port: int) -> int:
    command = [str(environment_python(target)), "-I", "-B", "-m", "model_release_assurance.console",
               "local", "--data", str(data), "--port", str(port)]
    # The existing console launcher owns the API, worker and their shutdown.
    console = subprocess.Popen(command, cwd=ROOT, env=_process_environment())
    try:
        return console.wait()
    except KeyboardInterrupt:
        print("Stopping the demo web service and worker...", flush=True)
        try:
            console.wait(timeout=30)
        except subprocess.TimeoutExpired:
            print("Demo shutdown is unconfirmed. The console supervisor was retained so it can "
                  "finish its API/worker cleanup; inspect the service logs before restarting.",
                  file=sys.stderr)
            return 2
        return 130


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=ROOT/".local/demo-venv")
    parser.add_argument("--data", type=Path, default=ROOT/".local/demo-data")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--wheelhouse", type=Path, help="install from a prepared local wheel directory")
    parser.add_argument("--install-only", action="store_true", help="install or validate without starting services")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    target, data = args.venv.resolve(), args.data.resolve()
    wheelhouse = args.wheelhouse.resolve() if args.wheelhouse is not None else None
    try:
        if wheelhouse is not None and not wheelhouse.is_dir():
            raise ValueError("wheelhouse must be an existing prepared local directory")
        binding = installation_binding()
        marker = target/MARKER
        if target.exists():
            if not marker.is_file() or marker.stat().st_size > 16_384:
                raise ValueError("Existing environment is not a complete launcher-managed demo; choose a new --venv path")
            if json.loads(marker.read_text(encoding="utf-8")) != binding:
                raise ValueError("Environment checkout or installation inputs changed; choose a new --venv path")
            validate_environment(target)
            if installation_binding() != binding:
                raise ValueError("Installation inputs changed during validation; choose a new --venv path")
            print(f"Reusing validated demo environment: {target}", flush=True)
        else:
            print(f"Installing the demo environment: {target}", flush=True)
            install_environment(target, wheelhouse)
            validate_environment(target)
            if installation_binding() != binding:
                raise ValueError("Installation inputs changed during setup; choose a new --venv path")
            with marker.open("x", encoding="utf-8", newline="\n") as output:
                json.dump(binding, output, indent=2, sort_keys=True)
                output.write("\n")
            print(f"Demo installation verified: {target}", flush=True)
        if args.install_only:
            print("Installation ready. Run the same command without --install-only to start the demo.")
            return 0
        print(f"Open http://127.0.0.1:{args.port}/ after the services start. Ctrl+C stops both.", flush=True)
        return launch_console(target, data, args.port)
    except KeyboardInterrupt:
        print("Demo stopped. Any partial installation and existing evidence were retained.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Demo failed: {exc}\nEnvironment and evidence retained; no fallback or overwrite.\nEnvironment: {target}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
