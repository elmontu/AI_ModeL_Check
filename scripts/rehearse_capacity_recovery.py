#!/usr/bin/env python3
"""Measure fixed public fixtures and historical recovery; production is refused."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("mra_capacity_monitor_helpers", ROOT / "scripts/rehearse_monitoring.py")
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
_BASELINE = _HELPERS._BASELINE
from model_release_assurance.production_capacity.contracts import FLAGS, digest
from model_release_assurance.production_capacity.rehearsal import exercise, workload_plan, REQUIRED_CHECKS as EXERCISE_CHECKS

SOURCE_FILES = ("scripts/rehearse_capacity_recovery.py", "scripts/rehearse_monitoring.py",
    "scripts/rehearse_controlled_delivery.py", "requirements-build.lock",
    "deploy/build/windows-cp312.json", "deploy/build/windows-cp312.requirements.txt",
    "deploy/sacro/windows-cp312.json", "deploy/sacro/windows-cp312.requirements.txt",
    *("src/model_release_assurance/production_capacity/" + name + ".py" for name in
      ("__init__", "contracts", "io", "benchmarks", "backup", "rehearsal")))
REQUIRED_CHECKS = frozenset((*EXERCISE_CHECKS, "source_unchanged"))
MAX_REPORT_BYTES = 2 * 1024 * 1024
LIMITATIONS = [
    "Fixed public Wine byte projections are repeated for I/O, not independent samples or private source data.",
    "Twelve real fixed-public-count jobs use requested concurrency1/2/4; runner overlap is not live child count.",
    "Measured local throughput, small-sample percentiles and historical reopen time do not qualify agency peak load or RTO.",
    "Delivery uses one fresh native Wine128 PRD18 fixture with a synthetic clock, not PRD19 SACRO qualification.",
    "Component restart retains valid local test identity to isolate missing proof contexts; it is not full IdP/KMS recovery.",
    "Historical backup verification preserves fictional engineering charges and local outbox state; no privacy accounting or live permission is restored.",
    "External checkpoint pins remain same-host trusted custody; cloud failover and independently administered witnesses are unverified.",
]


class ProfileRefused(ValueError):
    pass


class RehearsalError(RuntimeError):
    pass


def source_snapshot(root):
    root = Path(root).absolute()
    base = _HELPERS.source_snapshot(root)
    files = {row["path"]: dict(row) for row in base["files"]}
    for name in SOURCE_FILES:
        raw = _HELPERS._HELPERS._read_source(root, name)
        files[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    if len(files) > 256:
        raise RehearsalError("Capacity source inventory exceeds bound")
    selected = [files[name] for name in sorted(files)]
    return {"scope": "All package Python, capacity/monitoring/delivery/output helpers and fixed runtime/build declarations",
            "files": selected, "sha256": _HELPERS._HELPERS._digest(selected)}


def _complete(checks):
    return (type(checks) is list and len(checks) == len(REQUIRED_CHECKS)
        and all(type(item) is dict and set(item) == {"name", "passed"}
                and type(item["name"]) is str and item["passed"] is True for item in checks)
        and {item["name"] for item in checks} == REQUIRED_CHECKS)


def run_rehearsal(*, root, output, profile="agency_private_cloud"):
    if type(profile) is not str or profile != "local_public_fixture":
        raise ProfileRefused("Production capacity qualification unavailable")
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-fixture-capacity-rehearsal/v1", "status": "failed", "profile": profile,
        "checks": [], "errors": [], "source": None, "limitations": LIMITATIONS,
        "target_status": "not_agency_qualified", **FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report["source"] = baseline
        result = exercise(destination / "fixture", profile=profile)
        if (type(result) is not dict or type(result.get("checks")) is not list
                or any(result.get(key) is not value for key, value in FLAGS.items())
                or result.get("target_status") != "not_agency_qualified"
                or type(result.get("summary")) is not dict or set(result["summary"]) != {"delivery", "backup"}
                or type(result.get("evidence")) is not dict or set(result["evidence"]) != {"delivery", "backup"}
                or type(result.get("measurements")) is not dict or set(result["measurements"]) != {"delivery", "backup", "io", "jobs"}
                or result.get("workload_plan_sha256") != digest(workload_plan())):
            raise RehearsalError("Invalid local capacity result")
        for name in ("checks", "summary", "evidence", "measurements", "workload_plan_sha256"):
            if name in result:
                report[name] = result[name]
        if result.get("status") != "passed":
            raise RehearsalError("Local capacity checks incomplete")
    except Exception:
        report["errors"].append({"stage": "fixture_workflow", "type": "LocalFixtureStageFailed"})
    if baseline is not None:
        try:
            stable = source_snapshot(root) == baseline
            report["checks"].append({"name": "source_unchanged", "passed": stable})
            if not stable:
                raise RehearsalError("Source changed")
        except Exception:
            report["errors"].append({"stage": "source_stability", "type": "SourceUnavailableOrChanged"})
    if not report["errors"] and _complete(report["checks"]):
        report["status"] = "passed"
    elif not report["errors"]:
        report["errors"].append({"stage": "milestones", "type": "IncompleteWorkflow"})
    try:
        raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        if len(raw) > MAX_REPORT_BYTES:
            raise RehearsalError("Report exceeds bound")
    except (TypeError, ValueError, RehearsalError):
        report = {"schema": "mra-fixture-capacity-rehearsal/v1", "status": "failed", "checks": [],
                  "errors": [{"stage": "report", "type": "InvalidOrOversizedReport"}], **FLAGS}
        raw = json.dumps(report, sort_keys=True).encode() + b"\n"
    with (destination / "result.json").open("xb") as stream:
        stream.write(raw)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("agency_private_cloud", "local_public_fixture"), default="agency_private_cloud")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(root=ROOT, output=args.output, profile=args.profile)
    except ProfileRefused:
        print(json.dumps({"status": "profile_refused", **FLAGS})); return 2
    except (_BASELINE.BaselineError, OSError, RehearsalError, ValueError):
        print(json.dumps({"status": "output_refused", **FLAGS})); return 2
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]),
                      "errors": result["errors"], **FLAGS}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
