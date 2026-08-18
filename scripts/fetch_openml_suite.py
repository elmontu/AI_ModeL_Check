#!/usr/bin/env python3
"""Freeze an OpenML suite into hashed local snapshots and manifests."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "model-release-assurance-openml-reproduction/0.1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def get_json(url: str) -> dict[str, Any]:
    result = subprocess.run(
        ("curl", "-fsSL", "--retry", "3", "--user-agent", USER_AGENT, url),
        check=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def download_file(url: str, path: Path) -> None:
    if path.is_file() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    subprocess.run(
        (
            "curl", "-fsSL", "--retry", "3", "--user-agent", USER_AGENT,
            "--output", str(temporary), url,
        ),
        check=True,
    )
    temporary.replace(path)


def package_versions() -> dict[str, str]:
    names = ("numpy", "pandas", "scikit-learn", "scipy", "xgboost", "joblib", "pyarrow")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    return versions


def validate_frame(frame: pd.DataFrame, target_name: str) -> None:
    duplicate_names = frame.columns[frame.columns.duplicated()].tolist()
    if duplicate_names:
        raise ValueError(f"duplicate feature names: {duplicate_names}")
    if target_name not in frame.columns:
        raise ValueError(f"default target {target_name!r} is absent from OpenML parquet columns")


def dataset_manifest(dataset_id: int, data_home: Path, raw_dir: Path) -> dict[str, Any]:
    del data_home
    details = get_json(f"https://www.openml.org/api/v1/json/data/{dataset_id}")["data_set_description"]
    target_name = str(details.get("default_target_attribute") or "")
    if not target_name or "," in target_name:
        raise ValueError(f"expected one default target, got {target_name!r}")
    parquet_url = details.get("parquet_url")
    if not parquet_url:
        raise ValueError("OpenML metadata does not provide a parquet_url")
    snapshot = raw_dir / f"openml-{dataset_id}.parquet"
    download_file(str(parquet_url), snapshot)
    frame = pd.read_parquet(snapshot)
    validate_frame(frame, target_name)
    target = frame[target_name].astype("string").fillna("<NA>")
    features = frame.drop(columns=[target_name])
    return {
        "dataset_id": dataset_id,
        "name": details.get("name"),
        "version": int(details["version"]),
        "status": details.get("status"),
        "openml_url": details.get("url"),
        "parquet_url": parquet_url,
        "file_id": details.get("file_id"),
        "openml_md5_checksum": details.get("md5_checksum"),
        "target": target_name,
        "rows": int(len(frame)),
        "features": int(len(features.columns)),
        "classes": int(target.nunique(dropna=False)),
        "class_counts": {str(key): int(value) for key, value in target.value_counts(dropna=False).items()},
        "missing_feature_values": int(features.isna().sum().sum()),
        "snapshot_path": str(snapshot.relative_to(ROOT)),
        "snapshot_sha256": sha256_file(snapshot),
        "snapshot_bytes": snapshot.stat().st_size,
        "feature_names": [str(column) for column in features.columns],
        "feature_dtypes": {
            str(column): str(frame[column].dtype)
            for column in features.columns
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    study_id = int(config["study_id"])
    base = ROOT / "reproduction" / "openml"
    manifests = base / "manifests"
    raw_dir = base / "raw"
    cache = base / "cache"
    study_url = f"https://www.openml.org/api/v1/json/study/{study_id}"
    study = get_json(study_url)
    study_bytes = canonical_json(study)
    dataset_ids = [int(value) for value in study["study"]["data"]["data_id"]]
    if args.limit is not None:
        dataset_ids = dataset_ids[: args.limit]

    write_json(manifests / f"suite-{study_id}-source.json", study)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for position, dataset_id in enumerate(dataset_ids, start=1):
        print(f"[{position}/{len(dataset_ids)}] OpenML dataset {dataset_id}", flush=True)
        try:
            result = dataset_manifest(dataset_id, cache, raw_dir)
            results.append(result)
            write_json(manifests / "datasets" / f"openml-{dataset_id}.json", result)
        except Exception as exc:
            failure = {"dataset_id": dataset_id, "error_type": type(exc).__name__, "error": str(exc)}
            failures.append(failure)
            print(f"  failed: {failure}", file=sys.stderr, flush=True)
            if not args.continue_on_error:
                break

    manifest = {
        "manifest_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "study_id": study_id,
        "study_alias": study["study"].get("alias"),
        "study_url": study_url,
        "study_sha256": sha256_bytes(study_bytes),
        "configured_dataset_count": len(dataset_ids),
        "successful_dataset_count": len(results),
        "failed_dataset_count": len(failures),
        "datasets": results,
        "failures": failures,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": package_versions(),
            "executable": Path(sys.executable).name,
        },
        "config_path": str(args.config),
        "config_sha256": sha256_file(args.config),
    }
    write_json(manifests / f"suite-{study_id}-datasets.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("configured_dataset_count", "successful_dataset_count", "failed_dataset_count")}, indent=2))
    return 0 if not failures and len(results) == len(dataset_ids) else 2


if __name__ == "__main__":
    raise SystemExit(main())
