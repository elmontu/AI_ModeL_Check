#!/usr/bin/env python3
"""Rehearse witness checkpoints, irreversible intents and rollback recovery offline."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("mra_witness_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_witness.contracts import FLAGS
from model_release_assurance.production_witness.rehearsal import exercise

SOURCE_GROUPS = ("production_witness", "production_registry", "production_identity", "production_storage", "production_trust")
SOURCE_FILES = ("src/model_release_assurance/__init__.py", "scripts/rehearse_witness_recovery.py",
                "scripts/verify_build_baseline.py", "pyproject.toml", "requirements.lock",
                *("src/model_release_assurance/production_witness/" + name + ".py" for name in
                  ("__init__", "contracts", "store", "reader", "service", "rehearsal")))
REQUIRED_CHECKS = frozenset({"intent_checkpoint_precedes_registry_charge",
    "exact_retry_preserves_one_charge_and_receipt", "stale_replica_is_rejected",
    "witness_outage_after_commit_retains_charge", "uncertain_commit_recovers_original_receipt",
    "whole_registry_restore_is_rejected", "witness_restore_below_external_floor_is_rejected",
    "replacement_ledger_id_cannot_reset_namespace", "full_history_and_irreversible_intents_are_retained",
    "all_results_remain_non_authorizing", "source_unchanged"})
LIMITATIONS = [
    "A separate bounded local witness archives complete history and intents; physical independent agency custody remains unverified.",
    "A separately retained expected checkpoint is required; rolling back registry, witness AND that external floor together is outside the guarantee.",
    "Fixed public counts and fictional engineering charges; no private model, accepted privacy accountant or release permission.",
    "Current fixture tokens, authority and object catalogs remain local/in memory; distributed revocation and trust recovery are unqualified.",
    "SQLite process/transaction checks do not qualify PostgreSQL replication, cloud failover or production restore procedures.",
    "Checkpoint hashes are trusted local bindings, not signed external witness responses or independently authenticated delivery.",
]
MAX_REPORT_BYTES = 128 * 1024

class RehearsalError(RuntimeError):
    pass

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()

def _read_source(root, name, maximum=2 * 1024 * 1024):
    path = _BASELINE._checked_path(root, name)
    before = path.lstat()
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    def valid(info):
        return stat.S_ISREG(info.st_mode) and not _BASELINE._is_link(info) and info.st_nlink == 1 and info.st_size <= maximum
    if not valid(before):
        raise RehearsalError("Source is not a bounded ordinary file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not valid(opened) or identity(opened) != identity(before):
            raise RehearsalError("Source changed during open")
        content = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    final = _BASELINE._checked_path(root, name).lstat()
    if (not valid(final) or identity(opened) != identity(after) or identity(after) != identity(final)
            or len(content) != after.st_size or len(content) > maximum):
        raise RehearsalError("Source changed during bounded read")
    return content


def source_snapshot(root):
    """Reselect all involved package sources, including newly added modules."""
    root = Path(root).absolute()
    selected = set(SOURCE_FILES)
    for group in SOURCE_GROUPS:
        directory = _BASELINE._checked_path(root, "src/model_release_assurance/" + group)
        found = list(directory.rglob("*.py"))
        if not found:
            raise RehearsalError("Required source package is missing")
        selected.update(path.relative_to(root).as_posix() for path in found)
    if len(selected) > 256:
        raise RehearsalError("Source snapshot exceeds its file bound")
    files = []
    for name in sorted(selected):
        path = _BASELINE._checked_path(root, name)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise RehearsalError("Source snapshot file exceeds its bound")
        content = _read_source(root, name)
        if len(content) > 2 * 1024 * 1024:
            raise RehearsalError("Source snapshot file exceeds its bound")
        files.append({"path": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)})
    return {"scope": "witness/registry/identity/storage/trust Python packages, package initializer, rehearsal/helper and runtime declarations",
            "files": files, "sha256": _digest(files)}


def run_rehearsal(*, root, output):
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-fixture-witness-rehearsal/v1", "status": "failed", "checks": [],
              "errors": [], "source": None, "limitations": LIMITATIONS, **FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report["source"] = baseline
        result = exercise(destination)
        if type(result) is not dict:
            raise RehearsalError("Incomplete workflow")
        report.update(result)
        report["status"] = "failed"
    except Exception as error:
        report["errors"].append({"stage": "fixture_workflow", "type": type(error).__name__})
    if baseline is not None:
        try:
            stable = source_snapshot(root) == baseline
            report["checks"].append({"name": "source_unchanged", "passed": stable})
            if not stable:
                raise RehearsalError("Source changed")
        except Exception as error:
            report["errors"].append({"stage": "source_stability", "type": type(error).__name__})
    if (not report["errors"] and len(report["checks"]) == len(REQUIRED_CHECKS)
            and {check["name"] for check in report["checks"]} == REQUIRED_CHECKS
            and all(check["passed"] is True for check in report["checks"])):
        report["status"] = "passed"
    if report["status"] != "passed" and not report["errors"]:
        report["errors"].append({"stage": "milestones", "type": "IncompleteWorkflow"})
    report["runtime"] = {"python": platform.python_version(), "system": platform.system()}
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    if len(content) > MAX_REPORT_BYTES:
        report = {"status": "failed", "checks": [], "errors": [{"stage": "report", "type": "ReportBoundExceeded"}], **FLAGS}
        content = json.dumps(report, sort_keys=True).encode() + b"\n"
    with (destination / "result.json").open("xb") as stream:
        stream.write(content)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(root=ROOT, output=args.output)
    except (_BASELINE.BaselineError, OSError):
        print(json.dumps({"status": "output_refused", **FLAGS}))
        return 2
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "errors": result["errors"], **FLAGS}))
    return 0 if result["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
