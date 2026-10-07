#!/usr/bin/env python3
"""Provision and verify four package-local public demo datasets.

No network request, model training, research-corpus download or source-directory
mutation is performed. Existing partial or modified caches are never replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
from typing import Any

SKLEARN_VERSION = "1.6.1"
SCHEMA = "mra-demo-datasets/v1"
MANIFEST = "manifest.json"
PROFILES = (
    ("sklearn-wine", "load_wine", 178, 13, "classification"),
    ("sklearn-breast-cancer", "load_breast_cancer", 569, 30, "classification"),
    ("sklearn-digits", "load_digits", 1797, 64, "classification"),
    ("sklearn-diabetes", "load_diabetes", 442, 10, "regression"),
)
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024


class DemoDataError(ValueError):
    """The fixed public dataset cache cannot be created or safely replayed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DemoDataError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8") + b"\n"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _ordinary_directory(path: Path) -> None:
    info = path.lstat()
    _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
             and not getattr(info, "st_file_attributes", 0) & 0x400,
             "Dataset directories must be ordinary local directories")


def _root(output: Path, *, create: bool) -> Path:
    path = Path(output)
    _require(path.is_absolute() and ".." not in path.parts
             and not str(path).startswith(("//", "\\\\")),
             "--output must be an absolute ordinary local path")
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            _ordinary_directory(parent)
    if not path.exists():
        _require(create, "Dataset cache directory is missing")
        path.mkdir(parents=True, exist_ok=False)
    _ordinary_directory(path)
    return path


def _read_file(path: Path, maximum: int) -> bytes:
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
             and not getattr(info, "st_file_attributes", 0) & 0x400 and info.st_nlink == 1,
             "Dataset files must be ordinary single-link files")
    _require(0 < info.st_size <= maximum, "Dataset file exceeds its fixed bound")
    content = path.read_bytes()
    _require(len(content) == info.st_size, "Dataset file changed while reading")
    current = path.lstat()
    _require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
             (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns),
             "Dataset file changed while reading")
    return content


def _expected() -> tuple[dict[str, Any], dict[str, bytes], dict[str, tuple[Any, Any]]]:
    import numpy as np
    import sklearn
    from sklearn import datasets

    _require(sklearn.__version__ == SKLEARN_VERSION,
             "Demo data requires scikit-learn 1.6.1; install the declared demo runtime")
    entries, serialized, arrays = [], {}, {}
    for dataset_id, loader_name, rows, features, task in PROFILES:
        data = getattr(datasets, loader_name)()
        x, y = np.asarray(data.data), np.asarray(data.target)
        _require(x.ndim == 2 and x.shape == (rows, features)
                 and y.ndim == 1 and y.shape == (rows,),
                 "Bundled dataset shape differs from its declared profile: " + dataset_id)
        _require(x.dtype.kind in "iuf" and y.dtype.kind in "iuf"
                 and np.isfinite(x).all() and np.isfinite(y).all(),
                 "Bundled dataset is not a finite aligned numeric matrix: " + dataset_id)
        names = [str(value) for value in data.feature_names]
        _require(len(names) == features, "Bundled feature names do not align: " + dataset_id)
        stream = io.BytesIO()
        np.savez_compressed(stream, x=x, y=y)
        content = stream.getvalue()
        _require(0 < len(content) <= MAX_FILE_BYTES, "Bundled serialized dataset exceeds its bound")
        filename = dataset_id + ".npz"
        serialized[filename] = content
        arrays[filename] = (x, y)
        data_binding = {"dataset_id": dataset_id, "loader": loader_name,
                        "sklearn_version": SKLEARN_VERSION, "x": x.tolist(), "y": y.tolist(),
                        "feature_names": names}
        entries.append({
            "dataset_id": dataset_id, "loader": loader_name, "task": task,
            "rows": rows, "features": features, "feature_names": names,
            "source": "scikit-learn package-local public sample",
            "source_url": "https://scikit-learn.org/1.6/datasets/toy_dataset.html",
            "filename": filename, "bytes": len(content), "sha256": _sha(content),
            "data_sha256": _sha(_canonical(data_binding)),
            "x_dtype": str(x.dtype), "y_dtype": str(y.dtype),
        })
    manifest = {
        "schema": SCHEMA, "sklearn_version": SKLEARN_VERSION,
        "numpy_version": np.__version__, "datasets": entries,
        "provisioning": "copies of installed package-local public samples; no external dataset download",
        "external_dataset_downloads": False, "research_datasets_provisioned": False,
        "private_data_admitted": False, "model_training_executed": False,
        "license_scope": "Source attribution retained; no institutional data-rights approval is asserted",
    }
    return manifest, serialized, arrays


def _verify(root: Path, manifest: dict[str, Any], serialized: dict[str, bytes],
            arrays: dict[str, tuple[Any, Any]]) -> dict[str, Any]:
    import numpy as np

    expected_names = set(serialized) | {MANIFEST}
    _require({path.name for path in root.iterdir()} == expected_names,
             "Dataset cache is partial or contains unexpected files; choose a fresh output directory")
    actual_manifest = _read_file(root / MANIFEST, MAX_MANIFEST_BYTES)
    _require(actual_manifest == _canonical(manifest),
             "Dataset manifest differs from the declared installed samples; existing files retained")
    for filename, expected in serialized.items():
        content = _read_file(root / filename, MAX_FILE_BYTES)
        _require(_sha(content) == _sha(expected) and content == expected,
                 "Dataset file differs from its declared bytes; existing files retained: " + filename)
        with np.load(io.BytesIO(content), allow_pickle=False) as saved:
            _require(set(saved.files) == {"x", "y"},
                     "Dataset archive contains unexpected arrays")
            expected_x, expected_y = arrays[filename]
            _require(saved["x"].dtype == expected_x.dtype and saved["y"].dtype == expected_y.dtype
                     and np.array_equal(saved["x"], expected_x)
                     and np.array_equal(saved["y"], expected_y),
                     "Dataset arrays differ from their package-local loader: " + filename)
    return manifest


def verify_demo_data(output: Path) -> dict[str, Any]:
    """Read-only exact replay of an existing complete fixed public cache."""
    manifest, serialized, arrays = _expected()
    return _verify(_root(output, create=False), manifest, serialized, arrays)


def prepare_demo_data(output: Path) -> dict[str, Any]:
    """Create exclusively in an empty directory, or verify without writes."""
    manifest, serialized, arrays = _expected()
    root = _root(output, create=True)
    if any(root.iterdir()):
        return _verify(root, manifest, serialized, arrays)
    for filename, content in serialized.items():
        with (root / filename).open("xb") as handle:
            handle.write(content)
    # Write this completion receipt last. Interrupted setup stays partial and
    # is never silently repaired by overwriting files on the next attempt.
    with (root / MANIFEST).open("xb") as handle:
        handle.write(_canonical(manifest))
    return _verify(root, manifest, serialized, arrays)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="absolute local directory; empty initially, exactly verified on reuse")
    args = parser.parse_args()
    try:
        manifest = prepare_demo_data(args.output)
    except (DemoDataError, OSError, ValueError) as exc:
        parser.exit(2, "Demo dataset setup failed: " + str(exc) + "\nExisting files retained; no replacement or fallback.\n")
    print(json.dumps({"status": "verified", "schema": SCHEMA,
                      "sklearn_version": manifest["sklearn_version"],
                      "datasets": [{"id": entry["dataset_id"], "rows": entry["rows"],
                                    "features": entry["features"]}
                                   for entry in manifest["datasets"]],
                      "external_dataset_downloads": False}, sort_keys=True))


if __name__ == "__main__":
    main()
