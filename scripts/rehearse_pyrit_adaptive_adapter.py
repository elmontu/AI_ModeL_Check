#!/usr/bin/env python3
"""Run bounded local PyRIT adaptive attacker roles with retained independent replay."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("pyrit_adaptive_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import strict_json
from model_release_assurance.production_pyrit_adaptive import protocol, runtime
from model_release_assurance.production_pyrit import runtime as dependency_runtime
from model_release_assurance.production_pyrit_adaptive.workflow import run_campaign, replay_campaign, FLAGS, write, digest, _read, _same
from model_release_assurance.production_pyrit_adaptive.execution import source_snapshot, runtime_descriptor

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_DEPENDENCY_MANIFEST_SHA256 = "e93ffeb365b3fa36f026d035a42fdda6f817dd94c4f20ee800428a059e314b26"
_DEPENDENCY_REQUIREMENTS_SHA256 = "c853d69b52a8bed308eebc76905116fa8c9d8fb85696b0469b96eaa88eee13fe"
_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")


def source_bindings(root):
    return {"package": source_snapshot(),
        "driver": hashlib.sha256(native._read(root / "scripts/rehearse_pyrit_adaptive_adapter.py", 1024 * 1024)).hexdigest(),
        "manifest": hashlib.sha256(native._read(root / "deploy/pyrit/windows-cp312.json", 4 * 1024 * 1024)).hexdigest(),
        "requirements": hashlib.sha256(native._read(root / "deploy/pyrit/windows-cp312.requirements.txt", 128 * 1024)).hexdigest()}


def load_runtime_manifest(root):
    raw = native._read(root / "deploy/pyrit/windows-cp312.json", 4 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != _DEPENDENCY_MANIFEST_SHA256:
        raise ValueError("The unchanged PyRIT dependency manifest bytes changed")
    requirements = native._read(root / "deploy/pyrit/windows-cp312.requirements.txt", 128 * 1024)
    if hashlib.sha256(requirements).hexdigest() != _DEPENDENCY_REQUIREMENTS_SHA256:
        raise ValueError("The unchanged PyRIT dependency requirements bytes changed")
    value = strict_json(raw, maximum=4 * 1024 * 1024)
    fields = {"schema", "pyrit_version", "target", "component_scope", "full_upstream_dependency_set",
        "unsupported_dependencies", "upstream_requires_dist", "artifacts", "fixture_only", "production_authorized", "model_delivery"}
    if (type(value) is not dict or set(value) != fields
            or value["schema"] != "mra-pyrit-windows-component-lock/v1"
            or value["pyrit_version"] != dependency_runtime.PYRIT_VERSION
            or value["component_scope"] != dependency_runtime.COMPONENT_SCOPE
            or value["full_upstream_dependency_set"] is not False
            or value["unsupported_dependencies"] != dependency_runtime.UNSUPPORTED_DEPENDENCIES
            or value["fixture_only"] is not True or value["production_authorized"] is not False
            or value["model_delivery"] is not False
            or value["target"] != {"python_version": "3.12", "python_full_version": dependency_runtime.PYTHON_VERSION,
                "implementation": "cpython", "platform": "win_amd64"}
            or type(value["upstream_requires_dist"]) is not list or not 1 <= len(value["upstream_requires_dist"]) <= 128
            or any(type(item) is not str or not 1 <= len(item) <= 4096 for item in value["upstream_requires_dist"])
            or type(value["artifacts"]) is not list or not 4 <= len(value["artifacts"]) <= 128):
        raise ValueError("PyRIT component runtime lock rejected")
    versions, normalized, filenames = {}, set(), set()
    for item in value["artifacts"]:
        artifact_fields = {"name", "version", "filename", "sha256", "size_bytes"}
        if (type(item) is not dict or set(item) != artifact_fields
                or type(item["name"]) is not str or not _NAME.fullmatch(item["name"])
                or type(item["version"]) is not str or not 1 <= len(item["version"]) <= 128
                or type(item["sha256"]) is not str or not _DIGEST.fullmatch(item["sha256"])
                or type(item["filename"]) is not str or not 1 <= len(item["filename"]) <= 240
                or Path(item["filename"]).name != item["filename"]
                or any(char in item["filename"] for char in ":/\\") or not item["filename"].endswith(".whl")
                or type(item["size_bytes"]) is not int or not 1 <= item["size_bytes"] <= 256 * 1024 * 1024):
            raise ValueError("PyRIT component artifact rejected")
        name = re.sub(r"[-_.]+", "-", item["name"]).lower()
        if name in normalized or item["filename"] in filenames:
            raise ValueError("Duplicate pyrit component artifact")
        normalized.add(name)
        filenames.add(item["filename"])
        versions[item["name"]] = item["version"]
    if versions != runtime.LOCKED_VERSIONS:
        raise ValueError("PyRIT component dependency roster changed")
    return versions, hashlib.sha256(raw).hexdigest()


def _local_python(root, supplied):
    raw = Path(supplied)
    if ".." in raw.parts or str(raw).startswith(("//", "\\\\")):
        raise ValueError("Runtime traversal or network location refused")
    path = raw if raw.is_absolute() else root / raw
    path = path.absolute()
    if not path.is_relative_to(root / ".local"):
        raise ValueError("Use a fixture runtime under this government .local")
    native._real_directory(path.parent)
    return path


def run_rehearsal(*, output, python, timeout_seconds=600, root=ROOT):
    root = Path(root).absolute()
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        raise ValueError("A process timeout between one and 600 seconds is required")
    python = _local_python(root, python)
    destination = _BASELINE.prepare_output(root, output)
    report = {"schema": "mra-pyrit-adaptive-rehearsal/v1", "status": "failed", "error": None,
        "campaign": None, "replay_status": None, "source_unchanged": False,
        "scope_complete": False, "shared_model": True, "independent_attacker_model": False,
        "all_pyrit_attack_families_tested": False, "all_llm_interfaces_tested": False, **FLAGS}
    try:
        versions, lock_sha256 = load_runtime_manifest(root)
        source, descriptor = source_bindings(root), runtime_descriptor(python)
        report.update(source=source, runtime=descriptor)
        intent = {"schema": "mra-pyrit-adaptive-batch-intent/v1",
            "source_sha256": digest(source), "lock_sha256": lock_sha256,
            "runtime": descriptor, "runtime_binding_expected": runtime.expected_binding(),
            "process_timeout_seconds": timeout_seconds, "model": dict(protocol.MODEL),
            "shared_model": True, "independent_attacker_model": False,
            "attacker_options": dict(protocol.ATTACKER_OPTIONS), "target_options": dict(protocol.TARGET_OPTIONS),
            "bounds": dict(protocol.BOUNDS), "interfaces": list(protocol.INTERFACES), "modes": list(protocol.MODES),
            "attacker_contract_sha256": digest({"system": protocol.ATTACKER_SYSTEM_TEMPLATE,
                "first": protocol.FIRST_TEMPLATE, "next": protocol.NEXT_TEMPLATE, "response_schema": protocol.RESPONSE_SCHEMA}), **FLAGS}
        write(destination / "batch-intent.json", intent)
        campaign = run_campaign(python=python, output=destination / "campaign", versions=versions,
            lock_sha256=lock_sha256, timeout_seconds=timeout_seconds)
        report["campaign"] = campaign
        report["status"] = campaign["status"] if campaign["status"] in {"completed", "incomplete", "timed_out", "unavailable", "unsupported", "failed"} else "failed"
        if campaign["status"] in {"completed", "incomplete"} and campaign["error"] is None:
            binding = replay_campaign(output=destination / "campaign", versions=versions, lock_sha256=lock_sha256)
            if binding["status"] != "bound_local_replay" or binding["campaign_status"] != campaign["status"]:
                raise ValueError("PyRIT independent retained replay unavailable")
            write(destination / "binding.json", binding)
            _same(_read(destination / "binding.json"), binding)
            report["replay_status"] = binding["status"]
        _same(_read(destination / "batch-intent.json"), intent)
        report["source_unchanged"] = source_bindings(root) == source and runtime_descriptor(python) == descriptor
        report["scope_complete"] = (campaign["status"] == "completed" and campaign["error"] is None
            and report["replay_status"] == "bound_local_replay" and campaign["source_unchanged"] is True
            and report["source_unchanged"] is True)
        if not report["source_unchanged"] or (report["status"] == "completed" and not report["scope_complete"]):
            report["status"] = "failed"
    except Exception as error:
        report.update(status="failed", scope_complete=False, error={"type": type(error).__name__, "stage": "rehearsal"})
    write(destination / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        report = run_rehearsal(output=args.output, python=args.python, timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError, _BASELINE.BaselineError) as error:
        print(json.dumps({"status": "refused", "type": type(error).__name__}))
        return 2
    print(json.dumps({"status": report["status"], "scope_complete": report["scope_complete"],
                      "replay_status": report["replay_status"]}))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
