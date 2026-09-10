"""Read-only export of generated job evidence, with bounded inventories and hashes."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from .store import Store

MAX_FILES = 5000
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def roots(store: Store, job_id: str) -> dict[str, Path]:
    job = store.job(job_id)
    directory = (store.root / "jobs" / job_id).resolve()
    if not directory.is_relative_to(store.root):
        raise ValueError("artifact root escapes the local store")
    result = {"job": directory}
    journal = directory / "workflow-run.json"
    if job["kind"] == "assess" and journal.is_file():
        recorded = json.loads(journal.read_text(encoding="utf-8"))["relative_path"]
        run = (store.root / recorded).resolve()
        expected = store.case_path(job["case_id"]) / "runs"
        if run.parent != expected.resolve():
            raise ValueError("assessment artifacts do not belong to this case")
        result["assessment"] = run
    return result


def file_path(store: Store, job_id: str, name: str) -> Path:
    parts = PurePosixPath(name).parts
    if not parts or "\\" in name or ":" in name or any(part in {".", ".."} for part in parts):
        raise ValueError("invalid artifact path")
    available = roots(store, job_id)
    if parts[0] not in available or len(parts) < 2:
        raise KeyError("artifact not found")
    root = available[parts[0]]
    candidate = (root / Path(*parts[1:])).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise KeyError("artifact not found")
    return candidate


def manifest(store: Store, job_id: str) -> dict:
    job = store.job(job_id)
    files = []
    for prefix, directory in roots(store, job_id).items():
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or not path.resolve().is_relative_to(directory):
                continue
            name = prefix + "/" + path.relative_to(directory).as_posix()
            if len(files) >= MAX_FILES:
                raise ValueError("artifact inventory exceeds 5000 files; inspect the local run directory")
            # The hash describes bytes downloaded at this observation; active runs can change.
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            files.append({"path": name, "size_bytes": size,
                          "sha256": digest.hexdigest(),
                          "download_url": f"/api/jobs/{job_id}/artifacts/{quote(name, safe='/')}"})
    return {"format_version": "local-artifact-inventory/1", "job_id": job_id,
            "state": job["state"], "files": files, "total_bytes": sum(item["size_bytes"] for item in files),
            "partial": job["state"] != "completed", "authorization_eligible": False,
            "note": "Generated local artifacts only. External input bindings remain at their source paths."}


def bundle(store: Store, job_id: str) -> bytes:
    inventory = manifest(store, job_id)
    if inventory["state"] in {"queued", "running"}:
        raise ValueError("wait for the run to finish before exporting a stable evidence bundle")
    if inventory["total_bytes"] > MAX_BUNDLE_BYTES:
        raise ValueError("bundle exceeds 64 MiB; download individual artifacts")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(inventory, indent=2, allow_nan=False))
        for entry in inventory["files"]:
            payload = file_path(store, job_id, entry["path"]).read_bytes()
            if len(payload) != entry["size_bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError("artifact changed during export; inspect the run and retry")
            archive.writestr(entry["path"], payload)
    return buffer.getvalue()
