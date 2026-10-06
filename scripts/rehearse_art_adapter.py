#!/usr/bin/env python3
"""Exercise eight fixed public profiles with retained-loss ART membership diagnostics."""
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
_SPEC = importlib.util.spec_from_file_location("art_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import strict_json, parse_plan
from model_release_assurance.production_evidence.replay import snapshot_native_bundle, artifact_manifest, replay_native_bundle
from model_release_assurance.production_registration.profiles import PROFILE_IDS, load_profile
from model_release_assurance.production_registration.workflow import prepare_native_input
from model_release_assurance.production_art import runtime
from model_release_assurance.production_art.workflow import run_comparison, replay_comparison, FLAGS, write, digest
from model_release_assurance.production_art.execution import source_snapshot, runtime_descriptor

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")


def source_bindings(root):
    return {"package": source_snapshot(),
        "driver": hashlib.sha256(native._read(root / "scripts/rehearse_art_adapter.py", 1024 * 1024)).hexdigest(),
        "manifest": hashlib.sha256(native._read(root / "deploy/art/windows-cp312.json", 4 * 1024 * 1024)).hexdigest(),
        "requirements": hashlib.sha256(native._read(root / "deploy/art/windows-cp312.requirements.txt", 128 * 1024)).hexdigest()}


def verified_input(native_root, profile_id, data_root):
    """Reload fixed public source and replay captured inert candidate bytes."""
    blobs = snapshot_native_bundle(native_root)
    plan = parse_plan(blobs["plan.json"])
    data = load_profile(profile_id, data_root=data_root,
        max_rows=max(128, len(plan.train_indices) + len(plan.calibration_indices) + len(plan.audit_indices)))
    _, expected_data, expected_plan = prepare_native_input(data, plan.seed)
    if blobs["dataset.json"] != expected_data or blobs["plan.json"] != expected_plan:
        raise ValueError("Pinned public source differs from saved native inputs")
    replay_native_bundle(blobs)
    return blobs


def load_runtime_manifest(root):
    raw = native._read(root / "deploy/art/windows-cp312.json", 4 * 1024 * 1024)
    manifest = strict_json(raw, maximum=4 * 1024 * 1024)
    fields = {"schema", "art_version", "target", "artifacts", "fixture_only", "production_authorized", "model_delivery"}
    if (type(manifest) is not dict or set(manifest) != fields
            or manifest["schema"] != "mra-art-windows-wheel-lock/v1"
            or manifest["art_version"] != runtime.ART_VERSION
            or manifest["fixture_only"] is not True
            or manifest["production_authorized"] is not False or manifest["model_delivery"] is not False
            or manifest["target"] != {"python_version": "3.12", "python_full_version": "3.12.14",
                "implementation": "cpython", "platform": "win_amd64"}
            or type(manifest["artifacts"]) is not list or not 4 <= len(manifest["artifacts"]) <= 128):
        raise ValueError("ART runtime lock rejected")
    versions, normalized, filenames = {}, set(), set()
    for item in manifest["artifacts"]:
        if (type(item) is not dict or set(item) != {"name", "version", "filename", "sha256", "size_bytes"}
                or type(item["name"]) is not str or not _NAME.fullmatch(item["name"])
                or type(item["version"]) is not str or not 1 <= len(item["version"]) <= 128
                or type(item["sha256"]) is not str or not _DIGEST.fullmatch(item["sha256"])
                or type(item["filename"]) is not str or not 1 <= len(item["filename"]) <= 240
                or Path(item["filename"]).name != item["filename"]
                or any(c in item["filename"] for c in ":/\\") or not item["filename"].endswith(".whl")
                or type(item["size_bytes"]) is not int or not 1 <= item["size_bytes"] <= 256 * 1024 * 1024):
            raise ValueError("ART runtime lock artifact rejected")
        name = re.sub(r"[-_.]+", "-", item["name"]).lower()
        if name in normalized or item["filename"] in filenames:
            raise ValueError("Duplicate ART runtime lock artifact")
        normalized.add(name)
        filenames.add(item["filename"])
        versions[item["name"]] = item["version"]
    if versions.get("adversarial-robustness-toolbox") != runtime.ART_VERSION:
        raise ValueError("Pinned ART dependency missing")
    if versions != runtime.LOCKED_VERSIONS:
        raise ValueError("Pinned dependency roster changed")
    return versions, hashlib.sha256(raw).hexdigest()


def _local_path(root, supplied):
    raw = Path(supplied)
    if ".." in raw.parts or str(raw).startswith(("//", "\\\\")):
        raise ValueError("Fixture path traversal or network location refused")
    path = raw if raw.is_absolute() else root / raw
    path = path.absolute()
    if not path.is_relative_to(root / ".local"):
        raise ValueError("Use fixture inputs and runtime under this government .local")
    native._real_directory(path.parent)
    return path


def run_rehearsal(*, output, python, benchmark=None, data_root=Path("D:/model_audit_data"), root=ROOT):
    root = Path(root).absolute()
    benchmark = benchmark if benchmark is not None else root / ".local/verification/prd13-registration-20261001/eight-profiles/cases"
    benchmark, python = _local_path(root, benchmark), _local_path(root, python)
    native._real_directory(benchmark)
    destination = _BASELINE.prepare_output(root, output)
    report = {"schema": "mra-art-rehearsal/v1", "status": "failed", "cases": [], "errors": [],
        "coverage_complete": False, "all_research_datasets_tested": False,
        "source_unchanged": False, "original_artifacts_unchanged": False, **FLAGS}
    try:
        versions, lock_sha256 = load_runtime_manifest(root)
        source, descriptor = source_bindings(root), runtime_descriptor(python)
        report.update(source=source, runtime=descriptor)
        write(destination / "batch-intent.json", {"schema": "mra-art-batch-intent/v1",
            "profiles": list(PROFILE_IDS), "required_supported": list(PROFILE_IDS),
            "required_cases": ["target", "positive", "null"], "source_sha256": digest(source),
            "runtime": descriptor, "runtime_binding_expected": runtime.expected_binding(),
            "lock_sha256": lock_sha256,
            "selection": "one_fixed_recipe_all_profiles_all_repetitions_no_outcome_selection", **FLAGS})
        (destination / "cases").mkdir()
        for name in PROFILE_IDS:
            item = {"profile_id": name, "status": "failed", "error": None, "original_artifacts_unchanged": False}
            report["cases"].append(item)
            native_root, frozen = benchmark / name / "native", None
            try:
                frozen = artifact_manifest(snapshot_native_bundle(native_root))
                blobs = verified_input(native_root, name, data_root)
                if artifact_manifest(blobs) != frozen:
                    raise ValueError("Captured native inputs changed before comparison")
                result = run_comparison(blobs, profile_id=name, output=destination / "cases" / name,
                    python=python, versions=versions, lock_sha256=lock_sha256)
                item.update(status=result["status"], error=result["error"])
                if result["status"] == "completed":
                    binding = replay_comparison(blobs, profile_id=name, output=destination / "cases" / name,
                        versions=versions, lock_sha256=lock_sha256)
                    if binding["status"] != "bound_local_replay":
                        raise ValueError("Local ART comparison replay unavailable")
                    write(destination / "cases" / name / "binding.json", binding)
                    item["replay_status"] = binding["status"]
                    item["target_summary"] = result["comparison"]["target"]["summary"]
                    item["controls_passed"] = all(result["comparison"][case]["controls_satisfied"] is True
                        for case in ("positive", "null"))
            except Exception as error:
                item.update(status="failed", error={"type": type(error).__name__, "stage": "profile_comparison"})
            finally:
                if frozen is not None:
                    try:
                        item["original_artifacts_unchanged"] = artifact_manifest(snapshot_native_bundle(native_root)) == frozen
                        if not item["original_artifacts_unchanged"]:
                            raise ValueError("Original native bundle changed")
                    except Exception as error:
                        item.update(status="failed", error={"type": type(error).__name__, "stage": "original_bundle_stability"})
        report["source_unchanged"] = source_bindings(root) == source and runtime_descriptor(python) == descriptor
        report["original_artifacts_unchanged"] = all(item["original_artifacts_unchanged"] is True for item in report["cases"])
        report["coverage_complete"] = (len(report["cases"]) == len(PROFILE_IDS)
            and [item["profile_id"] for item in report["cases"]] == list(PROFILE_IDS)
            and all(item["status"] == "completed" and item["error"] is None
                and item.get("controls_passed") is True and item.get("replay_status") == "bound_local_replay"
                for item in report["cases"]))
        if report["coverage_complete"] and report["source_unchanged"] and report["original_artifacts_unchanged"]:
            report["status"] = "completed"
    except Exception as error:
        report["errors"].append({"type": type(error).__name__, "stage": "rehearsal"})
    write(destination / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("D:/model_audit_data"))
    args = parser.parse_args(argv)
    try:
        report = run_rehearsal(output=args.output, python=args.python, benchmark=args.benchmark, data_root=args.data_root)
    except (OSError, ValueError, _BASELINE.BaselineError) as error:
        print(json.dumps({"status": "refused", "type": type(error).__name__}))
        return 2
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
        "coverage_complete": report["coverage_complete"]}))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
