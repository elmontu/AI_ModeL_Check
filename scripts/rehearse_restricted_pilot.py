#!/usr/bin/env python3
"""Rehearse a bounded local pilot plan; agency admission remains unavailable."""
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
_SPEC = importlib.util.spec_from_file_location("mra_pilot_assessment_helpers", ROOT / "scripts/rehearse_independent_assessment.py")
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
_BASELINE = _HELPERS._BASELINE
_SOURCE_READER = _HELPERS._HELPERS._HELPERS._HELPERS
from model_release_assurance.production_assessment import contracts as assessment
from model_release_assurance.production_pilot import contracts as c
from model_release_assurance.production_pilot.rehearsal import exercise, REQUIRED_CHECKS as EXERCISE_CHECKS, EXPECTED_SUMMARY

REQUIRED_CHECKS = frozenset((*EXERCISE_CHECKS, "source_unchanged"))
MAX_REPORT_BYTES = 512 * 1024
SOURCE_FILES = ("scripts/rehearse_restricted_pilot.py",
    *("src/model_release_assurance/production_pilot/" + name + ".py" for name in
      ("__init__", "contracts", "evidence", "service", "rehearsal")))
HISTORICAL_FLAGS = {"current_authorization_checked": False,
                    "probe_execution_reconstructed": False, "agency_signer_authenticated": False}
_BINDING_FIELDS = frozenset({"candidate_sha256", "assessment_manifest_sha256", "assessment_key_sha256",
                            "catalog_sha256", "agency_id", "project_id", "case_id"})
LIMITATIONS = [
    "The fixed native public Wine128 PRD18 evidence supports local planning integrity only; SACRO and DP qualification remain absent.",
    "Named people authenticate through current signed local fixture credentials; actual agency owners, provider and region remain pending.",
    "Historical assessment verification neither reconstructs probe execution nor supplies current identity, agency acceptance or delivery authority.",
    "The declared synthetic planning window never extends gateway activation, recipient grants or authenticated evidence deadlines.",
    "Suspension and withdrawal restrict this local plan; they do not operate an agency gateway.",
    "Eleven production blockers remain open. No private data, model query, model delivery or pilot admission is permitted.",
    "Saved records are historical and cannot reconstruct current planning authority after restart.",
]


class ProfileRefused(ValueError):
    pass


def source_snapshot(root):
    base = _HELPERS.source_snapshot(root)
    files = {row["path"]: dict(row) for row in base["files"]}
    for name in SOURCE_FILES:
        raw = _SOURCE_READER._read_source(Path(root), name)
        files[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    if len(files) > 256:
        raise ValueError("Pilot source inventory exceeds bound")
    selected = [files[name] for name in sorted(files)]
    return {"scope": "All package Python and fixed pilot/assessment/runtime/output helpers",
            "files": selected, "sha256": _SOURCE_READER._digest(selected)}


def _checks(value, expected, *, complete):
    if (type(value) is not list or len(value) > len(expected)
            or any(type(row) is not dict or set(row) != {"name", "passed"}
                   or type(row["name"]) is not str or row["name"] not in expected
                   or type(row["passed"]) is not bool for row in value)):
        return False
    names = [row["name"] for row in value]
    if len(set(names)) != len(names):
        return False
    return not complete or (set(names) == expected and all(row["passed"] is True for row in value))


def _complete(checks):
    return _checks(checks, REQUIRED_CHECKS, complete=True)


def _successful_result(value):
    value = c.owned(value)
    fields = {"schema", "status", "checks", "errors", "summary", "evidence", "plan_sha256", "pins",
              "serialized_plan_restored", *c.FLAGS}
    if (type(value) is not dict or set(value) != fields
            or value["schema"] != "mra-local-pilot-rehearsal-exercise/v1"
            or value["status"] != "passed" or value["errors"] != []
            or value["serialized_plan_restored"] is not False
            or any(value.get(key) is not flag for key, flag in c.FLAGS.items())):
        raise ValueError("Invalid local pilot result")
    if not _checks(value["checks"], EXERCISE_CHECKS, complete=True):
        raise ValueError("Incomplete local pilot checks")
    if c.canonical_bytes(value["summary"]) != c.canonical_bytes(dict(EXPECTED_SUMMARY)):
        raise ValueError("Invalid local pilot summary")
    evidence = value["evidence"]
    evidence_fields = {"schema", *_BINDING_FIELDS, "implementation_sha256", "profile_id", "max_rows",
                       "evidence_profile", "production_blockers", *HISTORICAL_FLAGS, *c.FLAGS}
    if (type(evidence) is not dict or set(evidence) != evidence_fields
            or evidence["schema"] != "mra-local-pilot-assessment-binding/v1"
            or evidence["profile_id"] != "sklearn-wine"
            or type(evidence["max_rows"]) is not int or evidence["max_rows"] != 128
            or evidence["evidence_profile"] != c.EVIDENCE_PROFILE
            or c.canonical_bytes(evidence["production_blockers"]) != c.canonical_bytes(list(assessment.BLOCKING_FINDING_IDS))
            or any(evidence[key] is not flag for key, flag in {**c.FLAGS, **HISTORICAL_FLAGS}.items())):
        raise ValueError("Invalid historical pilot evidence")
    c.validate_binding({key: evidence[key] for key in _BINDING_FIELDS})
    c.validate_digest(evidence["implementation_sha256"])
    c.validate_digest(value["plan_sha256"])
    expected_plan = c.pilot_plan(candidate_sha256=evidence["candidate_sha256"],
                                 assessment_manifest_sha256=evidence["assessment_manifest_sha256"],
                                 assessment_key_sha256=evidence["assessment_key_sha256"],
                                 profile="local_public_fixture")
    if value["plan_sha256"] != c.digest(expected_plan):
        raise ValueError("Plan hash does not bind the fixed declared plan")
    if value["plan_sha256"] == "0" * 64 or evidence["implementation_sha256"] == "0" * 64:
        raise ValueError("Missing exact implementation or plan binding")
    pins = value["pins"]
    if type(pins) is not dict or set(pins) != {"manifest_sha256", "key_sha256"}:
        raise ValueError("Missing external assessment pins")
    for pin, binding in (("manifest_sha256", "assessment_manifest_sha256"), ("key_sha256", "assessment_key_sha256")):
        c.validate_digest(pins[pin])
        if pins[pin] != evidence[binding]:
            raise ValueError("External pins do not bind assessment")
    return value


def _retain_failed(value):
    """Keep only bounded recognized observations from a failed trusted exercise."""
    safe = c.owned(value)
    if (type(safe) is not dict or safe.get("schema") != "mra-local-pilot-rehearsal-exercise/v1"
            or safe.get("status") != "failed"
            or any(safe.get(key) is not flag for key, flag in c.FLAGS.items())):
        raise ValueError("Invalid failed pilot result")
    checks = safe.get("checks", [])
    summary = safe.get("summary", {})
    if (not _checks(checks, EXERCISE_CHECKS, complete=False) or type(summary) is not dict
            or not set(summary) <= set(EXPECTED_SUMMARY)
            or any(c.canonical_bytes(summary[key]) != c.canonical_bytes(EXPECTED_SUMMARY[key]) for key in summary)):
        raise ValueError("Unrecognized failed pilot observations")
    return checks, summary


def _serialize(report):
    try:
        raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("Oversized pilot report")
        return report, raw
    except (TypeError, ValueError):
        # Retain bounded completed observations, while removing unavailable or
        # oversized source/evidence. The returned object is exactly persisted.
        checks = report.get("checks", [])
        summary = report.get("summary", {})
        if not _checks(checks, REQUIRED_CHECKS, complete=False):
            checks = []
        try:
            summary = c.owned(summary)
            if (type(summary) is not dict or not set(summary) <= set(EXPECTED_SUMMARY)
                    or any(c.canonical_bytes(summary[key]) != c.canonical_bytes(EXPECTED_SUMMARY[key]) for key in summary)):
                summary = {}
        except Exception:
            summary = {}
        failed = {"schema": "mra-local-restricted-pilot-rehearsal/v1", "status": "failed",
                  "profile": "local_public_fixture", "checks": checks, "summary": summary,
                  "errors": [{"stage": "report", "code": "InvalidOrOversizedPilotReport"}], **c.FLAGS}
        return failed, json.dumps(failed, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"


def run_rehearsal(*, root, output, profile="agency_private_cloud"):
    if type(profile) is not str or profile != "local_public_fixture":
        raise ProfileRefused("Agency pilot admission is unavailable")
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-local-restricted-pilot-rehearsal/v1", "status": "failed",
              "profile": profile, "checks": [], "errors": [], "summary": {}, "source": None,
              "limitations": list(LIMITATIONS), **c.FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report["source"] = baseline
        result = exercise(destination / "pilot", profile=profile)
        if type(result) is dict and result.get("status") == "failed":
            report["checks"], report["summary"] = _retain_failed(result)
            raise ValueError("Local pilot stages incomplete")
        safe = _successful_result(result)
        for key in ("checks", "summary", "evidence", "plan_sha256", "pins", "serialized_plan_restored"):
            report[key] = safe[key]
    except Exception:
        report["errors"].append({"stage": "pilot", "code": "LocalPilotPlanFailed"})
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
        report["errors"].append({"stage": "checks", "code": "IncompletePilotPlan"})
    report, raw = _serialize(report)
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
        print(json.dumps({"status": "profile_refused", **c.FLAGS})); return 2
    except Exception:
        print(json.dumps({"status": "failed", "errors": [{"code": "OutputUnavailable"}], **c.FLAGS})); return 1
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), **c.FLAGS}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
