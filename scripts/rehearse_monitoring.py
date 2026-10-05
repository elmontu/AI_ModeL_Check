#!/usr/bin/env python3
"""Rehearse fixed local monitoring faults; production is refused by default."""
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
_SPEC = importlib.util.spec_from_file_location("mra_monitor_delivery_helpers", ROOT / "scripts/rehearse_controlled_delivery.py")
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
_BASELINE = _HELPERS._BASELINE
from model_release_assurance.production_monitoring.contracts import FLAGS
from model_release_assurance.production_monitoring.rehearsal import exercise, REQUIRED_CHECKS as EXERCISE_CHECKS

SOURCE_FILES = ("scripts/rehearse_monitoring.py", "scripts/rehearse_controlled_delivery.py",
    *("src/model_release_assurance/production_monitoring/" + name + ".py" for name in
      ("__init__", "contracts", "store", "checkpoint", "service", "receiver", "rehearsal")))
REQUIRED_CHECKS = frozenset((*EXERCISE_CHECKS, "source_unchanged"))
MAX_REPORT_BYTES = 256 * 1024
LIMITATIONS = [
    "Four fixed faults affect only newly created fictional public-count fixtures and ephemeral local authority.",
    "The real fixed worker timeout proves owned process cleanup, not hostile-code, filesystem or network isolation.",
    "Key availability recovery does not undo revocation, restore old grants or qualify production key custody.",
    "The witness uncertainty drill retains one fictional engineering charge; no privacy accounting or model release is established.",
    "Alerts go only to a bounded durable receiver in this run's local directory; no external messages are sent.",
    "Incident resolution records a current fixture auditor action and observed recovery, not independent human or agency acknowledgment.",
    "Checkpoints are on the same host; coherent privileged rollback and cloud disaster recovery are unqualified.",
]


class ProfileRefused(ValueError):
    pass


class RehearsalError(RuntimeError):
    pass


def _local(profile):
    if type(profile) is not str or profile != "local_public_fixture":
        raise ProfileRefused("Production monitoring qualification unavailable")


def source_snapshot(root):
    root = Path(root).absolute()
    base = _HELPERS.source_snapshot(root)
    files = {entry["path"]: dict(entry) for entry in base["files"]}
    for name in SOURCE_FILES:
        raw = _HELPERS._read_source(root, name)
        files[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    if len(files) > 256:
        raise RehearsalError("Monitoring source inventory exceeds its bound")
    selected = [files[name] for name in sorted(files)]
    return {"scope": "All package Python, monitoring/delivery/output helpers and runtime declarations",
            "files": selected, "sha256": _HELPERS._digest(selected)}


def _complete(checks):
    return (type(checks) is list and len(checks) == len(REQUIRED_CHECKS)
        and all(type(row) is dict and set(row) == {"name", "passed"} and type(row["name"]) is str
                and row["passed"] is True for row in checks)
        and {row["name"] for row in checks} == REQUIRED_CHECKS)


def run_rehearsal(*, root, output, profile="agency_private_cloud"):
    _local(profile)  # Refuse before filesystem mutation or source inspection.
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-fixture-monitor-rehearsal/v1", "status": "failed", "profile": profile,
        "checks": [], "errors": [], "source": None, "limitations": LIMITATIONS, **FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report["source"] = baseline
        result = exercise(destination / "fixture", profile=profile)
        if (type(result) is not dict or result.get("status") != "passed"
                or any(result.get(key) is not value for key, value in FLAGS.items())):
            raise RehearsalError("Incomplete local monitoring workflow")
        for key in ("checks", "summary", "evidence"):
            if key in result:
                report[key] = result[key]
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
    if not report["errors"] and _complete(report["checks"]):
        report["status"] = "passed"
    elif not report["errors"]:
        report["errors"].append({"stage": "milestones", "type": "IncompleteWorkflow"})
    try:
        raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        if len(raw) > MAX_REPORT_BYTES:
            raise RehearsalError("Report exceeds bound")
    except (TypeError, ValueError, RehearsalError):
        report = {"schema": "mra-fixture-monitor-rehearsal/v1", "status": "failed", "checks": [],
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
        print(json.dumps({"status": "profile_refused", **FLAGS}))
        return 2
    except (_BASELINE.BaselineError, OSError, RehearsalError, ValueError):
        print(json.dumps({"status": "output_refused", **FLAGS}))
        return 2
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "errors": result["errors"], **FLAGS}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
