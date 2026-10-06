from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


RESEARCH_DATA_ENV = "MRA_DEMO_RESEARCH_DATA_ROOT"


def validate_research_data_root(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("research-data-root must be an absolute path")
    try:
        for entry in reversed((path, *path.parents)):
            attributes = getattr(entry.lstat(), "st_file_attributes", 0)
            if entry.is_symlink() or attributes & 0x400:
                raise ValueError("research-data-root must not contain symlinks or reparse points")
    except FileNotFoundError as exc:
        raise ValueError("research-data-root must be an existing directory") from exc
    if not path.is_dir():
        raise ValueError("research-data-root must be an existing directory")
    return path.resolve(strict=True)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Local MRA API and separate worker; trusted testers only")
    parser.add_argument("mode", choices=("local", "serve", "worker"), nargs="?", default="local")
    parser.add_argument("--data", type=Path, default=Path(".local/console-data"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    parser.add_argument("--research-data-root", type=Path,
                        help="absolute local directory of public research datasets; no uploads or downloads")
    args = parser.parse_args(argv)
    configured_root = args.research_data_root
    if configured_root is None and os.environ.get(RESEARCH_DATA_ENV):
        configured_root = Path(os.environ[RESEARCH_DATA_ENV])
    research_data_root = None
    if configured_root is not None:
        try:
            research_data_root = validate_research_data_root(configured_root)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    environment = dict(os.environ)
    if research_data_root is not None:
        environment[RESEARCH_DATA_ENV] = str(research_data_root)
        if args.mode in {"worker", "serve"}:
            os.environ[RESEARCH_DATA_ENV] = str(research_data_root)
    root = args.data.resolve()
    if args.mode == "worker":
        from .worker import run
        run(root)
        return
    if args.mode == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(root), host=args.host, port=args.port, access_log=False)
        return
    if args.host != "127.0.0.1":
        parser.error("local mode binds loopback only; use the documented Compose setup for containers")
    # Fail before starting an orphan worker if another application owns the port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    root.mkdir(parents=True, exist_ok=True)
    children = []
    logs = []
    log_dir = root / "service-logs"
    log_dir.mkdir(exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for mode in ("worker", "serve"):
            log = (log_dir / f"{mode}.log").open("a", encoding="utf-8", buffering=1)
            logs.append(log)
            children.append(subprocess.Popen(
                [sys.executable, "-m", "model_release_assurance.console", mode,
                 "--data", str(root), "--port", str(args.port)], creationflags=flags, env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT))
        print(f"Console: http://127.0.0.1:{args.port}\nData: {root}\nTrusted local pre-POC. Ctrl+C stops API and worker.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        failed = [(mode, child.returncode) for mode, child in zip(("worker", "serve"), children) if child.poll() is not None]
        raise RuntimeError(f"Service exited: {failed}; review logs in {log_dir}")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
