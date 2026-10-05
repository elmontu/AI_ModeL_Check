#!/usr/bin/env python3
"""Snapshot and repeat an offline local wheel build without altering the Git index.

This developer utility records observed bytes; it is not a sandbox or attestation
against a malicious administrator. Run only on trusted source with no concurrent
editors. All outputs, including failed runs, remain in a NEW ignored .local path.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import site
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).absolute().parents[1]
BUILDERS = {"pip", "setuptools", "wheel", "packaging"}
LIMITATIONS = [
    "Same-input repeatability on this recorded local runtime only; not cross-platform reproducibility.",
    "Installed distribution versions are observed, not authenticated dependency-wheel hashes or build provenance.",
    "Source stability checks detect ordinary concurrent changes, not a malicious filesystem administrator.",
    "Builds reuse the current environment, including .pth/editable hooks; exact wheel-member checks do not make builds hermetic.",
    "No production qualification, signing, release authorization, publication or clean-install smoke test is performed.",
]


class BaselineError(RuntimeError):
    pass


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _git(root, *args):
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, env=env, check=False)
    if result.returncode:
        raise BaselineError("Git inspection failed: " + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _relative(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute()
            or any(part in {"", ".", "..", ".git"} for part in name.split("/"))):
        raise BaselineError("Unsafe repository path: " + repr(name))
    return path


def _is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _checked_path(root, relative, *, missing=False):
    parts = _relative(relative).parts
    current = root
    root_info = root.lstat()
    if _is_link(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise BaselineError("Repository root must be a real directory")
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                return current.joinpath(*parts[index+1:])
            raise BaselineError("Missing source path: " + relative)
        if _is_link(info):
            raise BaselineError("Symlink or reparse point refused: " + relative)
        if index < len(parts)-1 and not stat.S_ISDIR(info.st_mode):
            raise BaselineError("Non-directory path component: " + relative)
    return current


def _read_file(root, relative):
    path = _checked_path(root, relative)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise BaselineError("Only regular source files are supported: " + relative)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if _is_link(opened) or not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise BaselineError("Source identity changed while opening: " + relative)
        content = stream.read()
        after = os.fstat(stream.fileno())
    _checked_path(root, relative)
    if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(content) != after.st_size:
        raise BaselineError("Source changed while reading: " + relative)
    return content


def capture_source(root):
    """Capture Git selection and exact present-file bytes; never run write-tree/add."""
    root = Path(root).absolute()
    top = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).absolute()
    if top != root:
        raise BaselineError("Use the repository root, not a subdirectory")
    index = _git(root, "ls-files", "--stage", "-z")
    entries = []
    tracked = set()
    for raw in index.split(b"\0"):
        if not raw:
            continue
        header, raw_name = raw.split(b"\t", 1)
        mode, oid, stage = header.decode("ascii").split()
        name = os.fsdecode(raw_name)
        _relative(name)
        if stage != "0" or mode not in {"100644", "100755"}:
            raise BaselineError("Unmerged, symlink or submodule index entry is unsupported: " + name)
        entries.append({"path": name, "mode": mode, "object_id": oid, "stage": 0})
        tracked.add(name)
    untracked = {os.fsdecode(name) for name in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if name}
    staged_deleted = sorted(os.fsdecode(name) for name in _git(
        root, "diff", "--cached", "--name-only", "--diff-filter=D", "-z", "HEAD", "--").split(b"\0") if name)
    for name in staged_deleted:
        _relative(name)
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    files, deleted = [], []
    for name in sorted(tracked | untracked):
        path = _checked_path(root, name, missing=True)
        if not path.exists():
            if name not in tracked:
                raise BaselineError("Untracked source disappeared: " + name)
            deleted.append(name)
            continue
        content = _read_file(root, name)
        files.append({"path": name, "size_bytes": len(content), "sha256": sha256(content)})
    return {
        "schema": "local-build-source/v1", "head": _git(root, "rev-parse", "HEAD").decode().strip(),
        "head_tree": _git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
        "branch": _git(root, "branch", "--show-current").decode().strip(),
        "head_commit_epoch": int(_git(root, "show", "-s", "--format=%ct", "HEAD")),
        "index_entries_sha256": sha256(index), "index_entries": entries,
        "status_porcelain_v1_z_base64": base64.b64encode(status).decode(),
        "tracked_deletions": sorted(set(deleted) | set(staged_deleted)),
        "index_worktree_deletions": deleted, "staged_deletions": staged_deleted,
        "nonignored_untracked_paths": sorted(untracked), "files": files,
    }


def verify_source(root, baseline):
    if capture_source(root) != baseline:
        raise BaselineError("Source, Git index, HEAD or dirty state changed during the baseline run")


def prepare_output(root, output):
    root = Path(root).absolute()
    output = Path(output)
    if ".." in output.parts:
        raise BaselineError("Output traversal is refused")
    target = output if output.is_absolute() else root / output
    target = target.absolute()
    try:
        relative = target.relative_to(root).as_posix()
    except ValueError:
        raise BaselineError("Output must be under this repository's ignored .local directory")
    parts = _relative(relative).parts
    if len(parts) < 2 or parts[0] != ".local":
        raise BaselineError("Output must be a new child of .local")
    _checked_path(root, relative, missing=True)
    if target.exists():
        raise BaselineError("Output already exists; choose a new directory")
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "--quiet", "--", relative], capture_output=True, check=False)
    if ignored.returncode != 0:
        raise BaselineError("Output must be ignored by Git")
    target.parent.mkdir(parents=True, exist_ok=True)
    _checked_path(root, target.parent.relative_to(root).as_posix())
    target.mkdir(exist_ok=False)
    return target


def copy_snapshot(root, baseline, target):
    target.mkdir(exist_ok=False)
    for item in baseline["files"]:
        content = _read_file(root, item["path"])
        if len(content) != item["size_bytes"] or sha256(content) != item["sha256"]:
            raise BaselineError("Source changed while snapshotting: " + item["path"])
        destination = target / Path(*_relative(item["path"]).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(content)


def builder_versions():
    versions = {}
    for name in sorted(BUILDERS):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def check_build_lock(content, versions):
    expected = {}
    for raw in content.decode("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([a-z][a-z0-9-]*)==([0-9][a-zA-Z0-9.+!-]*)", line)
        if not match or match[1] in expected:
            raise BaselineError("Build lock must contain unique exact versions")
        expected[match[1]] = match[2]
    if set(expected) != BUILDERS:
        raise BaselineError("Build lock must name exactly pip, setuptools, wheel and packaging")
    if versions != expected:
        raise BaselineError("Installed builder versions differ from requirements-build.lock: " + json.dumps(versions, sort_keys=True))
    return expected


def runtime_pth_files():
    """Inventory active site-package startup hooks, without claiming isolation."""
    directories = set(site.getsitepackages())
    if site.ENABLE_USER_SITE:
        user_site = site.getusersitepackages()
        directories.update([user_site] if isinstance(user_site, str) else user_site)
    observed = []
    for directory in sorted(directories):
        for path in sorted(Path(directory).glob("*.pth")):
            info = path.lstat()
            if _is_link(info) or not stat.S_ISREG(info.st_mode):
                raise BaselineError("Cannot inventory non-regular runtime .pth file: " + str(path))
            content = path.read_bytes()
            observed.append({"path": str(path.absolute()), "size_bytes": len(content), "sha256": sha256(content)})
    return observed


def build_environment(output, epoch, *, label=""):
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("PIP_", "PYTHON"))}
    temporary = output / ("tmp-" + label if label else "tmp")
    temporary.mkdir()
    env.update(SOURCE_DATE_EPOCH=str(epoch), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_CACHE_DIR="1",
               TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    return env


def build_wheel(snapshot, directory, env, log_path):
    directory.mkdir()
    command = [sys.executable, "-B", "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
               "--no-cache-dir", "--wheel-dir", str(directory), str(snapshot)]
    with log_path.open("wb") as log:
        invocation = {"command": command, "cwd": str(snapshot),
                      "source_date_epoch": env["SOURCE_DATE_EPOCH"], "temporary_directory": env["TEMP"]}
        log.write((json.dumps(invocation, sort_keys=True) + "\n").encode("utf-8"))
        log.flush()
        result = subprocess.run(command, cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise BaselineError("Offline wheel build failed; inspect " + log_path.name)
    wheels = list(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise BaselineError("Expected exactly one built wheel")
    return wheels[0]


def verify_wheel(wheel, baseline):
    prefix = "src/model_release_assurance/"
    expected = {item["path"][4:]: item for item in baseline["files"] if item["path"].startswith(prefix)
                and (item["path"].endswith(".py") or "/static/" in item["path"] or item["path"].endswith("/py.typed"))}
    if not expected:
        raise BaselineError("No expected package sources in snapshot")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise BaselineError("Duplicate wheel member")
        for info in archive.infolist():
            _relative(info.filename)
            if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                raise BaselineError("Unexpected non-file wheel member")
        metadata = {name.split("/", 1)[0] for name in names if ".dist-info/" in name}
        if len(metadata) != 1:
            raise BaselineError("Expected one wheel metadata directory")
        dist_info = next(iter(metadata))
        package_names = {name for name in names if not name.startswith(dist_info + "/")}
        if package_names != set(expected):
            raise BaselineError("Missing or unexpected wheel package members")
        for name, item in expected.items():
            content = archive.read(name)
            if len(content) != item["size_bytes"] or sha256(content) != item["sha256"]:
                raise BaselineError("Wheel package member differs from source: " + name)
        record_name = dist_info + "/RECORD"
        if record_name not in names:
            raise BaselineError("Missing wheel RECORD")
        records = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
        if any(len(row) != 3 for row in records) or len({row[0] for row in records}) != len(records):
            raise BaselineError("Invalid wheel RECORD rows")
        if {row[0] for row in records} != set(names):
            raise BaselineError("Wheel RECORD does not inventory every member")
        for name, encoded, size in records:
            if name == record_name:
                if encoded or size:
                    raise BaselineError("RECORD self-entry must have empty hash and size")
                continue
            content = archive.read(name)
            expected_hash = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
            if encoded != expected_hash or size != str(len(content)):
                raise BaselineError("Wheel RECORD hash or size mismatch: " + name)
    return {"filename": wheel.name, "sha256": sha256(wheel.read_bytes()), "size_bytes": wheel.stat().st_size,
            "verified_package_files": len(expected), "verified_record_entries": len(records)}


def run_baseline(root, output, *, builder=build_wheel):
    root = Path(root).absolute()
    output = prepare_output(root, output)
    result = {"schema": "local-build-baseline/v1", "status": "failed", "limitations": LIMITATIONS,
              "output": str(output), "wheels": [], "errors": []}
    baseline = None
    write_json(output / "source-manifest.json", {"status": "not_captured"})
    try:
        versions = builder_versions()
        runtime = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                   "builder_versions": versions, "sys_path": list(sys.path), "site_pth_files": runtime_pth_files(),
                   "installed_distributions": sorted((dist.metadata.get("Name", ""), dist.version)
                       for dist in importlib.metadata.distributions())}
        write_json(output / "runtime.json", runtime)
        baseline = capture_source(root)
        write_json(output / "source-manifest.json", baseline)
        result["source_manifest_sha256"] = sha256((output / "source-manifest.json").read_bytes())
        result["head"] = baseline["head"]
        result["branch"] = baseline["branch"]
        result["source_date_epoch"] = baseline["head_commit_epoch"]
        lock = _read_file(root, "requirements-build.lock")
        result["build_lock_sha256"] = sha256(lock)
        result["builder_versions"] = check_build_lock(lock, versions)
        for label in ("a", "b"):
            copy_snapshot(root, baseline, output / ("source-" + label))
        verify_source(root, baseline)
        for label in ("a", "b"):
            env = build_environment(output, baseline["head_commit_epoch"], label=label)
            wheel = builder(output / ("source-" + label), output / ("wheels-" + label), env,
                            output / ("build-" + label + ".log"))
            result["wheels"].append(verify_wheel(wheel, baseline))
        if result["wheels"][0]["sha256"] != result["wheels"][1]["sha256"]:
            raise BaselineError("The two independent wheel builds differ byte-for-byte")
        result["status"] = "passed"
    except Exception as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        if baseline is not None:
            try:
                verify_source(root, baseline)
                result["source_stable_at_end"] = True
            except Exception as error:
                result["source_stable_at_end"] = False
                result["status"] = "failed"
                result["errors"].append(type(error).__name__ + ": " + str(error))
        write_json(output / "results.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="NEW ignored path under .local, e.g. .local/build-baseline/run-001")
    args = parser.parse_args(argv)
    try:
        result = run_baseline(ROOT, args.output)
    except (BaselineError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps({"status": result["status"], "output": result["output"], "errors": result["errors"]}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
