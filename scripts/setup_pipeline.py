#!/usr/bin/env python3
"""Cross-platform source-checkout bootstrap. Never modifies an existing venv."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def setup_commands(python: Path, profile: str, wheelhouse: Path | None) -> list[list[str]]:
    pip = [str(python), "-m", "pip", "--disable-pip-version-check"]
    source = [] if wheelhouse is None else ["--no-index", "--find-links", str(wheelhouse.resolve())]
    commands = [pip + ["install", *source, "setuptools>=69", "wheel"],
                pip + ["install", *source, "-r", str(ROOT / "requirements.lock")]]
    if profile in {"training", "console"}:
        commands.append(pip + ["install", *source, "-r", str(ROOT / "requirements-experiments.txt")])
    if profile == "console":
        commands.append(pip + ["install", *source, "-r", str(ROOT / "requirements-console.txt")])
    commands.append(pip + ["install", *source, "--no-deps", "--no-build-isolation", "-e", str(ROOT)])
    commands.append([str(python), "-m", "model_release_assurance.workflow", "doctor"])
    return commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "training", "console"), default="core")
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv-pipeline")
    parser.add_argument("--wheelhouse", type=Path, help="install only from an approved local wheel directory")
    parser.add_argument("--dry-run", action="store_true", help="print commands without creating or installing anything")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    target = args.venv.resolve()
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    commands = setup_commands(python, args.profile, args.wheelhouse)
    if args.dry_run:
        print(json.dumps({"create_new_venv": str(target), "commands": commands}, indent=2))
        return 0
    try:
        if target.exists():
            raise ValueError("venv path already exists; choose a new --venv path. No existing environment was changed.")
        if args.wheelhouse is not None and not args.wheelhouse.is_dir():
            raise ValueError("wheelhouse must be an existing approved local directory")
        print(f"Creating {args.profile} environment: {target}", flush=True)
        venv.EnvBuilder(with_pip=True).create(target)
        for command in commands:
            subprocess.run(command, cwd=ROOT, check=True)
        print(f"\nSetup complete. No activation required.\nPython: {python}")
        print("Run this Python with: -m model_release_assurance.workflow init PATH --kind adapter")
        if args.profile in {"training", "console"}:
            print("Offline teaching run: -m model_release_assurance.workflow demo --output NEW_RUN_PATH")
        if args.profile == "console":
            print("Start console and worker: -m model_release_assurance.console local")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}\nAny partially created environment is retained at {target}; no fallback runtime was used.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
