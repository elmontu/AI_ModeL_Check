"""Dataset-first read projection of retained console jobs and exact case links.

This module never scans a corpus, replays evidence, recovers jobs or changes the
queue. A configured research directory is not a verified source. Observations
are labels copied from retained results, not a current scientific assessment.
"""
from __future__ import annotations

import json
import math
import re
import stat
from types import MappingProxyType

from .options import TrainingOptions
from .research_data import MAX_ROWS, SOURCE_KIND, configured_research_root

_DATASETS = MappingProxyType({
    "sklearn-breast-cancer": ("Wisconsin breast cancer", "classification", 569, 30),
    "sklearn-wine": ("Wine classification", "classification", 178, 13),
    "sklearn-digits": ("Handwritten digits", "classification", 1797, 64),
    "sklearn-diabetes": ("Diabetes progression", "regression", 442, 10),
    "research-acs": ("ACS census and income", "classification", None, None),
    "research-bts": ("BTS aviation", "classification", None, None),
    "research-hmda": ("HMDA mortgage lending", "classification", None, None),
    "research-tlc": ("NYC TLC taxi mobility", "classification", None, None),
})
_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_STATES = frozenset({"queued", "running", "completed", "failed", "cancelled"})
_VERDICTS = frozenset({"clear", "block", "inconclusive"})
_LIMITS = (
    "Read-only grouping of stored training options, results and exact case references.",
    "Model results and source metadata are historical observations, not current evidence verification.",
    "This overview does not authorize release or establish privacy, licensing or scientific qualification.",
)


def _object(raw):
    if type(raw) is not str or not 1 <= len(raw) <= 2_000_000:
        return None
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("nonfinite value")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        return value if type(value) is dict else None
    except (ValueError, TypeError, RecursionError):
        return None


def _id(value):
    return value if type(value) is str and _ID.fullmatch(value) else None


def _integer(value, maximum=2**53 - 1):
    return value if type(value) is int and 0 <= value <= maximum else None


def _timestamp(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _text(value, maximum=150):
    if type(value) is str and 0 < len(value) <= maximum and not any(ord(char) < 32 for char in value):
        return value
    return None


def _ordinary(path, kind):
    try:
        info = path.lstat()
        return (kind(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def _current_case(store, row):
    case_id = _id(row["id"])
    if case_id is None:
        return None
    try:
        path = store.case_path(case_id)
        # No project parsing or evidence reads: only the exact stored case's
        # ordinary directory and project-file presence establish a usable link.
        if not _ordinary(store.cases / case_id, stat.S_ISDIR) or not _ordinary(path / "project.json", stat.S_ISREG):
            return None
    except (ValueError, OSError):
        return None
    return {"case_id": case_id, "name": _text(row["name"], 100), "kind": _text(row["kind"]),
            "route": _text(row["route"]), "created": _timestamp(row["created"]),
            "followup_jobs": [], "authorization_eligible": False}


def _source(result, dataset):
    observed = result.get("dataset")
    source = observed.get("research_source") if type(observed) is dict else None
    if (type(source) is not dict or source.get("dataset_id") != dataset
            or source.get("profile_id") != dataset.removeprefix("research-")
            or source.get("source_kind") != SOURCE_KIND or type(source.get("metadata")) is not dict):
        return None
    metadata = source["metadata"]
    retained = {}
    bounds = {"source_rows": 200000, "selected_rows": MAX_ROWS, "feature_count": 128, "selection_seed": 2**53 - 1}
    for field, maximum in bounds.items():
        value = _integer(metadata.get(field), maximum)
        if value is not None:
            retained[field] = value
    for field in ("manifest_sha256", "sampled_matrix_sha256", "selection_indices_sha256"):
        value = metadata.get(field)
        if type(value) is str and _SHA.fullmatch(value):
            retained[field] = value
    for field in ("local_public_fixture_pin_verified", "historical_training_data_reused", "fresh_audit_evidence",
                  "authenticated_upstream_provenance", "current_license_approval", "person_level_disjointness_established"):
        if type(metadata.get(field)) is bool:
            retained[field] = metadata[field]
    digest = source.get("source_sha256")
    digest = digest if type(digest) is str and _SHA.fullmatch(digest) else None
    return {"dataset_id": dataset, "profile_id": dataset.removeprefix("research-"), "source_kind": SOURCE_KIND,
            "source_sha256": digest, "metadata": retained, "observation_scope": "stored_training_result_only",
            "verified_currently": False, "authorization_eligible": False}


def _job(row):
    return {"job_id": row["id"], "state": row["state"] if row["state"] in _STATES else "unknown",
            "created": _timestamp(row["created"]), "started": _timestamp(row["started"]),
            "finished": _timestamp(row["finished"]), "retry_of": _id(row["retry_of"]),
            "authorization_eligible": False}


def _verdict(value):
    return value if type(value) is str and value in _VERDICTS else None


def dataset_overview(store):
    """Project all stored training runs in one read transaction, without recovery.

    Malformed/unknown training options are counted as unclassified, never guessed
    from names, results, defaults or case descriptions. Case links require an
    exact completed training result plus a currently present stored case.
    """
    try:
        configured = configured_research_root() is not None
        configuration_status = "configured_directory_only" if configured else "unconfigured"
    except (OSError, ValueError):
        configured, configuration_status = False, "invalid_configuration"
    items = {}
    for dataset, (name, task, rows, features) in _DATASETS.items():
        research = dataset.startswith("research-")
        items[dataset] = {"id": dataset, "name": name, "source_kind": SOURCE_KIND if research else "sklearn_bundled",
            "task": task, "source_rows": rows, "features": features, "max_rows": MAX_ROWS if research else rows,
            "configured": configured if research else True,
            "configuration_status": configuration_status if research else "bundled",
            "source_verified_currently": False, "training_runs": [], "case_ids": [], "cases": [],
            "summary": {}, "limitations": [*_LIMITS, *(["Research configuration checks the directory only; pinned bytes were checked only when a retained run reports that observation.",
                "Retained research samples contain at most 4096 rows and are not the complete raw collection or fresh audit evidence."] if research else [])],
            "read_only": True, "authorization_eligible": False}
    unclassified = 0
    with store.connect() as db:
        db.execute("BEGIN")
        case_rows = list(db.execute("SELECT id,name,kind,route,created FROM cases ORDER BY created DESC,id"))
        cases = {row["id"]: case for row in case_rows if (case := _current_case(store, row)) is not None}
        # Store.list_jobs intentionally limits its separate queue view to 100.
        # This dataset projection must include older training history as well.
        for row in db.execute("SELECT id,state,created,started,finished,retry_of,options,result FROM jobs WHERE kind='training' ORDER BY created DESC,id"):
            options = _object(row["options"])
            try:
                if not options or type(options.get("dataset")) is not str or options["dataset"] not in items or "preset" not in options:
                    raise ValueError("unclassified training options")
                selection = TrainingOptions.model_validate(options)
                if _id(row["id"]) is None:
                    raise ValueError("invalid job identifier")
            except ValueError:
                unclassified += 1
                continue
            result = _object(row["result"]) if row["state"] == "completed" else None
            result = {} if result is None else result
            observed = result.get("dataset")
            observed = observed if type(observed) is dict else {}
            case_id = _id(result.get("case_id"))
            case_id = case_id if case_id in cases else None
            run = {**_job(row), "preset": selection.preset, "case_id": case_id,
                "verdict": _verdict(result.get("verdict")), "rows": _integer(observed.get("rows")),
                "features": _integer(observed.get("features"), 128), "research_source": None}
            if selection.dataset.startswith("research-"):
                run["research_source"] = _source(result, selection.dataset)
            items[selection.dataset]["training_runs"].append(run)
        linked = set()
        for item in items.values():
            ids = list(dict.fromkeys(run["case_id"] for run in item["training_runs"] if run["case_id"] is not None))
            item["case_ids"] = ids
            item["cases"] = [dict(cases[case_id], followup_jobs=[]) for case_id in ids]
            linked.update(ids)
        case_targets = {}
        for item in items.values():
            for case in item["cases"]:
                case_targets.setdefault(case["case_id"], []).append(case)
        for row in db.execute("SELECT id,kind,case_id,state,created,started,finished,retry_of,result FROM jobs WHERE kind IN ('check','assess') ORDER BY created DESC,id"):
            if row["case_id"] not in case_targets or _id(row["id"]) is None:
                continue
            result = _object(row["result"]) if row["state"] == "completed" else None
            result = {} if result is None else result
            followup = {**_job(row), "kind": row["kind"], "case_id": row["case_id"],
                        "verdict": _verdict(result.get("assessment_verdict", result.get("verdict")))}
            for case in case_targets[row["case_id"]]:
                case["followup_jobs"].append(dict(followup))
    for item in items.values():
        runs = item["training_runs"]
        item["summary"] = {"training_runs": len(runs), "completed": sum(run["state"] == "completed" for run in runs),
            "failed": sum(run["state"] == "failed" for run in runs), "cancelled": sum(run["state"] == "cancelled" for run in runs),
            "active": sum(run["state"] in {"queued", "running"} for run in runs),
            "unknown": sum(run["state"] == "unknown" for run in runs), "linked_cases": len(item["cases"]),
            "followup_jobs": sum(len(case["followup_jobs"]) for case in item["cases"])}
    return {"datasets": list(items.values()), "unlinked_case_count": len(case_rows) - len(linked),
            "unclassified_training_run_count": unclassified, "projection": "stored_metadata_only",
            "read_only": True, "authorization_eligible": False}


def dataset_detail(store, dataset_id):
    """Return a fixed dataset item. No path, arbitrary corpus or name lookup."""
    if type(dataset_id) is not str or dataset_id not in _DATASETS:
        raise KeyError("dataset not found")
    return next(item for item in dataset_overview(store)["datasets"] if item["id"] == dataset_id)
