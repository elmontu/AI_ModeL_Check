"""Bounded native-artifact snapshots and numerical replay from captured bytes.

The replayer never reopens artifact paths. Existing trusted native helpers may
read their own implementation files and installed runtime metadata. This is
local numerical consistency, not original-training attestation, independent
scientific validation, or a production isolation/authorization decision.
"""
from __future__ import annotations

import hashlib
from itertools import islice
import math
import os
from pathlib import Path
import stat

from .contracts import EvidenceError, NATIVE_ARTIFACT_NAMES, validate_artifacts
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, parse_candidate, parse_plan, strict_json

MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_CANDIDATE_BYTES = 2 * 1024 * 1024
_RECEIPT_FIELDS = frozenset({
    "schema_version", "status", "adapter_id", "adapter_version", "dataset_id", "task",
    "source_sha256", "files", "reason", "limitations", "data_sha256", "plan_sha256",
    "duplicate_groups", "conflicting_label_groups", "candidate_sha256", "utility", "membership",
    "controls", "replay", "reload_max_absolute_error", "runtime", "elapsed_seconds", *native.FLAGS,
})


def _fail():
    raise EvidenceError("Native evidence bundle rejected")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _owned_bundle(blobs):
    if type(blobs) is not dict:
        _fail()
    owned = dict(blobs)
    if set(owned) != set(NATIVE_ARTIFACT_NAMES):
        _fail()
    total = 0
    for name, content in owned.items():
        maximum = MAX_CANDIDATE_BYTES if name == "candidate.json" else MAX_ARTIFACT_BYTES
        if type(content) is not bytes or not 1 <= len(content) <= maximum:
            _fail()
        total += len(content)
    if total > MAX_BUNDLE_BYTES:
        _fail()
    # Exact bytes are immutable; an owned mapping prevents later caller edits.
    return owned


def artifact_manifest(blobs: dict[str, bytes]) -> dict:
    """Hash the exact bounded byte bundle; this does not assert successful replay."""
    try:
        owned = _owned_bundle(blobs)
        manifest = {name: {"sha256": _sha(owned[name]), "size_bytes": len(owned[name])}
                    for name in sorted(owned)}
        validate_artifacts(manifest)
        return manifest
    except EvidenceError:
        raise
    except Exception:
        raise EvidenceError("Native evidence bundle rejected") from None


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directories(root):
    stamps = []
    for path in (*reversed(root.parents), root):
        info = path.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            _fail()
        stamps.append((path, info.st_dev, info.st_ino))
    return tuple(stamps)


def _file_stamp(info):
    if _unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _fail()
    # Windows Python 3.12 lstat/fstat have different ctime semantics.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _roster(root):
    paths = list(islice(root.iterdir(), len(NATIVE_ARTIFACT_NAMES) + 1))
    if len(paths) != len(NATIVE_ARTIFACT_NAMES) or {path.name for path in paths} != set(NATIVE_ARTIFACT_NAMES):
        _fail()
    stamps, total = {}, 0
    for path in paths:
        stamp = _file_stamp(path.lstat())
        maximum = MAX_CANDIDATE_BYTES if path.name == "candidate.json" else MAX_ARTIFACT_BYTES
        if not 1 <= stamp[2] <= maximum:
            _fail()
        total += stamp[2]
        stamps[path.name] = stamp
    if total > MAX_BUNDLE_BYTES:
        _fail()
    return stamps


def snapshot_native_bundle(root: Path) -> dict[str, bytes]:
    """Capture eight ordinary files once, rechecking identities and exact roster.

    Owned immutable bytes remain usable if the original directory later changes;
    callers admitting evidence must compare this snapshot to their signed manifest.
    No extraction, model loading, executable imports or filesystem writes occur.
    """
    try:
        supplied = Path(root)
        if ".." in supplied.parts or str(supplied).startswith(("//", "\\\\")):
            _fail()
        path = supplied.absolute()
        directories = _directories(path)
        stamps = _roster(path)
        blobs = {}
        for name in sorted(stamps):
            maximum = MAX_CANDIDATE_BYTES if name == "candidate.json" else MAX_ARTIFACT_BYTES
            descriptor = os.open(path / name, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                if _file_stamp(os.fstat(stream.fileno())) != stamps[name]:
                    _fail()
                content = stream.read(maximum + 1)
                if len(content) != stamps[name][2] or _file_stamp(os.fstat(stream.fileno())) != stamps[name]:
                    _fail()
            if _file_stamp((path / name).lstat()) != stamps[name]:
                _fail()
            blobs[name] = content
        if _directories(path) != directories or _roster(path) != stamps:
            _fail()
        return _owned_bundle(blobs)
    except EvidenceError:
        raise
    except Exception:
        raise EvidenceError("Native evidence bundle rejected") from None


def _same(left, right):
    if canonical_bytes(left) != canonical_bytes(right):
        _fail()


def _nonnegative_finite(value):
    return type(value) in {float, int} and math.isfinite(value) and value >= 0


def replay_native_bundle(blobs: dict[str, bytes]) -> dict:
    """Recompute exact native outputs from owned bytes, without artifact-path I/O.

    Frozen grouping, parameters, scores, predictions, controls and receipt fields
    are checked. Self-reported fit timing/reload error are only type/bounds checked:
    replay does not reconstruct a prior estimator fit or attest its historical run.
    Live source hashes/runtime versions are sampled by the trusted native helpers.
    """
    try:
        owned = _owned_bundle(blobs)
        artifact_manifest(owned)
        receipt = strict_json(owned["result.json"])
        expected_files = set(NATIVE_ARTIFACT_NAMES) - {"result.json"}
        if (type(receipt) is not dict or set(receipt) != _RECEIPT_FIELDS
                or receipt["schema_version"] != "mra-native-tabular-result/v1"
                or receipt["status"] != "completed" or receipt["reason"] is not None
                or type(receipt["files"]) is not dict or set(receipt["files"]) != expected_files
                or not _nonnegative_finite(receipt["elapsed_seconds"])
                or not _nonnegative_finite(receipt["reload_max_absolute_error"])):
            _fail()
        _same(receipt["limitations"], native.LIMITATIONS)
        for name in expected_files:
            if type(receipt["files"][name]) is not str or receipt["files"][name] != _sha(owned[name]):
                _fail()
        if any(receipt[key] is not value for key, value in native.FLAGS.items()):
            _fail()
        plan_raw, data_raw, candidate_raw = owned["plan.json"], owned["dataset.json"], owned["candidate.json"]
        plan = parse_plan(plan_raw)
        data = strict_json(data_raw)
        if (type(data) is not dict or set(data) != {"schema_version", "x", "y", "feature_names", "task"}
                or data["schema_version"] != "mra-native-tabular-data/v1"):
            _fail()
        x, y = native._arrays(data["x"], data["y"])
        if (plan.data_sha256 != _sha(data_raw) or data["feature_names"] != plan.feature_names or data["task"] != plan.task):
            _fail()
        reconstructed = native._plan(x, y, plan.dataset_id, plan.source_sha256, plan.feature_names,
                                     plan.task, plan.seed, plan.data_sha256)
        _same(plan, reconstructed)
        candidate = parse_candidate(candidate_raw)
        runtime = native._runtime()
        if (candidate.plan_sha256 != _sha(plan_raw) or candidate.source_sha256 != plan.source_sha256
                or candidate.data_sha256 != plan.data_sha256 or candidate.dataset_id != plan.dataset_id
                or candidate.feature_names != plan.feature_names or candidate.task != plan.task
                or candidate.implementation_sha256 != plan.implementation_sha256
                or candidate.training_rows != len(plan.train_indices)):
            _fail()
        _same(candidate.runtime, runtime)
        report, scores, predictions = native._measure(candidate_raw, x, y, plan)
        for name, expected in (("report.json", report), ("scores.json", scores), ("predictions.json", predictions)):
            _same(strict_json(owned[name]), expected)
        if report["controls_passed"] is not True:
            _fail()
        verified = {"schema_version": "mra-native-tabular-replay/v1", "status": "passed",
            "candidate_sha256": _sha(candidate_raw), "plan_sha256": _sha(plan_raw), "data_sha256": _sha(data_raw),
            "predictions_replayed": True, "metrics_replayed": True, "controls_replayed": True,
            "reasons": [], "verification_scope": "local_consistency_not_authenticity_or_original_training_attestation",
            **native.FLAGS}
        _same(strict_json(owned["replay.json"]), verified)
        _same(receipt["replay"], verified)
        expected_receipt = {"adapter_id": native.ADAPTER_ID, "adapter_version": native.ADAPTER_VERSION,
            "dataset_id": plan.dataset_id, "source_sha256": plan.source_sha256, "task": plan.task,
            "candidate_sha256": _sha(candidate_raw), "plan_sha256": _sha(plan_raw), "data_sha256": _sha(data_raw),
            "duplicate_groups": plan.duplicate_groups, "conflicting_label_groups": plan.conflicting_label_groups,
            "runtime": runtime, "utility": report["utility"], "membership": report["membership"],
            "controls": {"passed": True, "positive_auc": report["positive_control"]["raw_auc"],
                         "null_auc": report["null_control"]["raw_auc"], "scope": report["control_scope"]}}
        for name, expected in expected_receipt.items():
            _same(receipt[name], expected)
        return verified
    except EvidenceError:
        raise
    except Exception:
        raise EvidenceError("Native evidence bundle rejected") from None
