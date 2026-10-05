#!/usr/bin/env python3
"""Prepare bounded local assessment evidence; independent agency work is pending."""
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
_SPEC = importlib.util.spec_from_file_location("mra_assessment_capacity_helpers", ROOT / "scripts/rehearse_capacity_recovery.py")
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
_BASELINE = _HELPERS._BASELINE
from model_release_assurance.production_assessment import contracts as c, packet as packet_contract
from model_release_assurance.production_assessment.contracts import FLAGS
from model_release_assurance.production_assessment.probes import _SUMMARY as PROBE_SUMMARY
from model_release_assurance.production_assessment.rehearsal import exercise, REQUIRED_CHECKS as EXERCISE_CHECKS

REQUIRED_CHECKS = frozenset((*EXERCISE_CHECKS, "source_unchanged"))
MAX_REPORT_BYTES = 512 * 1024
SOURCE_FILES = ("scripts/rehearse_independent_assessment.py",
    *("src/model_release_assurance/production_assessment/" + name + ".py" for name in
      ("__init__", "contracts", "review", "probes", "packet", "rehearsal")))
LIMITATIONS = [
    "Fresh public native Wine128 delivery probes cover a fixed local PRD18 path, not PRD19 SACRO or deployed agency routes.",
    "Generated Ed25519 packet keys and same-host external pins establish local historical integrity, not appointed agency identity or independent custody.",
    "Packet verification checks exact bytes and fixed contracts; it does not reconstruct probe execution or independently replay all nested SQLite histories.",
    "Current signed fixture reviewers are distinct and scoped, but records are historical after expiry and have no serialized restore path.",
    "Eleven production blockers remain open; two local residuals have narrow fixed justifications and cannot permit deployment.",
    "Scientific adequacy, attack completeness, real private populations, DP accounting, cloud penetration testing and agency approval remain pending.",
]


class ProfileRefused(ValueError):
    pass


def source_snapshot(root):
    base = _HELPERS.source_snapshot(root)
    files = {row["path"]: dict(row) for row in base["files"]}
    for name in SOURCE_FILES:
        raw = _HELPERS._HELPERS._HELPERS._read_source(Path(root), name)
        files[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    selected = [files[name] for name in sorted(files)]
    if len(selected) > 256:
        raise ValueError("Assessment source inventory exceeds bound")
    return {"scope": "All package Python and fixed rehearsal/runtime/output helpers",
            "files": selected, "sha256": _HELPERS._HELPERS._HELPERS._digest(selected)}


def _complete(checks):
    return (type(checks) is list and len(checks) == len(REQUIRED_CHECKS)
        and all(type(row) is dict and set(row) == {"name", "passed"}
                and type(row["name"]) is str and row["passed"] is True for row in checks)
        and {row["name"] for row in checks} == REQUIRED_CHECKS)


def _successful_result(value):
    fields = {"schema", "status", "checks", "errors", "summary", "packet", "pins", *FLAGS}
    if (type(value) is not dict or set(value) != fields
            or value["schema"] != "mra-local-assessment-exercise/v1"
            or value["status"] != "passed" or value["errors"] != []
            or any(value.get(key) is not flag for key, flag in FLAGS.items())):
        raise ValueError("Invalid assessment result")
    checks = value["checks"]
    if (type(checks) is not list or len(checks) != len(EXERCISE_CHECKS)
            or any(type(row) is not dict or set(row) != {"name", "passed"}
                or type(row["name"]) is not str or row["passed"] is not True for row in checks)
            or {row["name"] for row in checks} != EXERCISE_CHECKS):
        raise ValueError("Incomplete checks")
    expected_review = {"production_blocker_count": 11, "local_residual_count": 2,
        "production_blockers_open": True, "current_local_review_demonstrated": True,
        "expired_review_unusable": True, "serialized_review_restored": False,
        "agency_assessor_appointed": False}
    if c.canonical_bytes(value["summary"]) != c.canonical_bytes({"probes": PROBE_SUMMARY, "review": expected_review}):
        raise ValueError("Invalid assessment summary")
    pins, verified = value["pins"], value["packet"]
    historical_flags = {"current_authorization_checked": False, "probe_execution_reconstructed": False,
                        "agency_signer_authenticated": False}
    if (type(pins) is not dict or set(pins) != {"manifest_sha256", "key_sha256", *FLAGS, *historical_flags}
            or type(verified) is not dict or set(verified) != {"schema", "status", "manifest_sha256", "key_sha256",
                "file_count", "total_bytes", "finding_catalog_sha256", "implementation_sha256", *FLAGS, *historical_flags}
            or verified["schema"] != "mra-local-assessment-verification/v1"
            or verified["status"] != "historical_packet_verified"
            or verified["finding_catalog_sha256"] != c.catalog_sha256()):
        raise ValueError("Missing historical packet")
    for item in (pins, verified):
        if any(item.get(key) is not flag for key, flag in {**FLAGS, **historical_flags}.items()):
            raise ValueError("Invalid historical flags")
        c.validate_digest(item["manifest_sha256"]); c.validate_digest(item["key_sha256"])
    if any(pins[key] != verified[key] for key in ("manifest_sha256", "key_sha256")):
        raise ValueError("Pins do not bind packet")
    c.validate_digest(verified["implementation_sha256"])
    c.integer(verified["file_count"], 1, packet_contract.MAX_FILES)
    c.integer(verified["total_bytes"], 1, packet_contract.MAX_TOTAL_BYTES)


def run_rehearsal(*, root, output, profile="agency_private_cloud"):
    if type(profile) is not str or profile != "local_public_fixture":
        raise ProfileRefused("Independent agency assessment unavailable")
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-local-assessment-rehearsal/v1", "status": "failed",
              "profile": profile, "checks": [], "errors": [], "source": None,
              "limitations": LIMITATIONS, **FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report["source"] = baseline
        result = exercise(destination / "assessment", profile=profile)
        if type(result) is dict and result.get("status") == "failed":
            # The trusted exercise emits only bounded fixed stage metadata.
            safe = c.owned(result)
            if (safe.get("schema") == "mra-local-assessment-exercise/v1"
                    and all(safe.get(key) is flag for key, flag in FLAGS.items())):
                report["checks"] = safe.get("checks", [])
                report["summary"] = safe.get("summary", {})
            raise ValueError("Assessment stages incomplete")
        _successful_result(result)
        for key in ("checks", "summary", "packet", "pins"):
            report[key] = result[key]
    except Exception:
        report["errors"].append({"stage": "assessment", "code": "LocalAssessmentFailed"})
    if baseline is not None:
        try:
            stable = source_snapshot(root) == baseline
            report["checks"].append({"name": "source_unchanged", "passed": stable})
            if not stable:
                raise ValueError("Source changed")
        except Exception:
            report["errors"].append({"stage": "source_stability", "code": "SourceUnavailableOrChanged"})
    if not report["errors"] and _complete(report["checks"]):
        report["status"] = "passed"
    elif not report["errors"]:
        report["errors"].append({"stage": "checks", "code": "IncompleteAssessment"})
    try:
        raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("Oversized assessment")
    except (TypeError, ValueError):
        report = {"schema": "mra-local-assessment-rehearsal/v1", "status": "failed",
                  "checks": [], "errors": [{"stage": "report", "code": "InvalidOrOversizedAssessment"}], **FLAGS}
        raw = json.dumps(report, sort_keys=True).encode("utf-8") + b"\n"
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
    except Exception:
        print(json.dumps({"status": "failed", "errors": [{"code": "OutputUnavailable"}], **FLAGS})); return 1
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), **FLAGS}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
