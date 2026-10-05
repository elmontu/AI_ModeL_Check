"""Read-only bounded adapters for four existing public-research matrices.

The local manifest binds bytes; it is not an agency approval, fresh holdout,
person-level privacy proof or an authenticated upstream provenance attestation.
No model deserialization or arbitrary source path from a manifest is used.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import zipfile
import zlib

import numpy as np

CORPORA = ("acs", "bts", "hmda", "tlc")
MAX_COMPRESSED_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MEMBERS = 32
MAX_HEADER_BYTES = 4096
SELECTION_SEED = 20261001
_VERSION = "mixed-model-export-20260929-v1"
_FEATURE_NAMES = {
    "acs": ("age_bin", "education", "MAR", "ESR", "RAC1P", "hispanic", "weekly_hours_bin", "COW"),
    "bts": ("flight_year", "flight_month", "flight_weekday", "scheduled_departure_hour",
            "scheduled_arrival_hour", "scheduled_duration_30min_bin", "distance_100mile_bin"),
    "hmda": ("loan_type", "loan_purpose", "lien_status", "occupancy_type", "construction_method", "state_code", "activity_year"),
    "tlc": ("pickup_year", "pickup_month", "pickup_hour", "pickup_weekday"),
}
_MEMBER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\.npy\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class DatasetUnavailable(FileNotFoundError):
    """An explicitly selected research root or source file is absent."""


class DatasetError(ValueError):
    """A fixed research source is unavailable, changed or outside its bounds."""


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directories(path):
    stamps = []
    for current in (*reversed(path.parents), path):
        info = current.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            raise DatasetError("Research source directories must be ordinary local directories")
        stamps.append((current, info.st_dev, info.st_ino))
    return tuple(stamps)


def _file_stamp(info):
    if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise DatasetError("Research source must be an ordinary single-link file")
    # Windows lstat/fstat can expose different ctime semantics; device, inode,
    # size and mtime bind both views, with an independent final byte-hash check.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_file(path, maximum):
    directories = _directories(path.parent)
    stamp = _file_stamp(path.lstat())
    if not 1 <= stamp[2] <= maximum:
        raise DatasetError("Research source exceeds its file bound")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        if _file_stamp(os.fstat(stream.fileno())) != stamp:
            raise DatasetError("Research source changed while opening")
        content = stream.read(maximum + 1)
        if len(content) != stamp[2] or _file_stamp(os.fstat(stream.fileno())) != stamp:
            raise DatasetError("Research source changed while reading")
    if _file_stamp(path.lstat()) != stamp or _directories(path.parent) != directories:
        raise DatasetError("Research source path changed while reading")
    return content, (stamp, directories)


def _recheck(path, maximum, expected_stamp, expected_digest):
    try:
        content, stamp = _read_file(path, maximum)
    except FileNotFoundError:
        raise DatasetError("Research source disappeared during validation") from None
    if stamp != expected_stamp or hashlib.sha256(content).hexdigest() != expected_digest:
        raise DatasetError("Research source changed during validation")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise DatasetError("Duplicate research manifest field")
        result[key] = value
    return result


def _invalid_number(_):
    raise DatasetError("Nonfinite research manifest number")


def _finite_number(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise DatasetError("Nonfinite research manifest number")
    return value


def _manifest(content, corpus, blob):
    value = json.loads(content.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid_number, parse_float=_finite_number)
    if type(value) is not dict or value.get("schema") != "mra.mixed-model-data.v1" or value.get("corpus") != corpus:
        raise DatasetError("Research manifest schema or corpus mismatch")
    receipt = value.get("data_receipt")
    if (type(receipt) is not dict or type(receipt.get("bytes")) is not int
            or receipt["bytes"] != len(blob) or type(receipt.get("sha256")) is not str
            or not _SHA.fullmatch(receipt["sha256"])
            or receipt["sha256"] != hashlib.sha256(blob).hexdigest()):
        raise DatasetError("Research matrix differs from its manifest receipt")
    if value.get("b_names") != list(_FEATURE_NAMES[corpus]):
        raise DatasetError("Research public covariate names differ from the fixed corpus schema")
    if type(value.get("selected_rows")) is not int or not 32 <= value["selected_rows"] <= 200000:
        raise DatasetError("Research manifest row count is outside its bound")
    return value


def _array_header(stream, information):
    version = np.lib.format.read_magic(stream)
    if version not in {(1, 0), (2, 0)}:
        raise DatasetError("Unsupported bounded NumPy header version")
    width, encoding = (2, "<H") if version == (1, 0) else (4, "<I")
    prefix = stream.read(width)
    if len(prefix) != width:
        raise DatasetError("Truncated NumPy header")
    length = struct.unpack(encoding, prefix)[0]
    if not 1 <= length <= MAX_HEADER_BYTES:
        raise DatasetError("NumPy header exceeds its bound")
    header = stream.read(length)
    if len(header) != length:
        raise DatasetError("Truncated NumPy header")
    reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
    shape, fortran, dtype = reader(io.BytesIO(prefix + header), max_header_size=MAX_HEADER_BYTES)
    if (dtype.hasobject or dtype.fields is not None or dtype.kind not in "buifUS"
            or not 1 <= dtype.itemsize <= 4096 or not 1 <= len(shape) <= 4
            or any(type(dimension) is not int or dimension < 1 for dimension in shape)):
        raise DatasetError("Research arrays require bounded non-object primitive dtypes and dimensions")
    payload = math.prod(shape) * dtype.itemsize
    if payload > MAX_EXPANDED_BYTES or 8 + width + length + payload != information.file_size:
        raise DatasetError("NumPy payload size differs from its bounded header")
    # Drain bounded members to check ZIP CRC, including unused arrays; never
    # interpret identifiers or the withheld attribute as training covariates.
    while stream.read(65536):
        pass
    return {"shape": list(shape), "dtype": str(dtype), "kind": dtype.kind, "fortran": bool(fortran)}


def _inspect_npz(blob):
    metadata = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        entries = archive.infolist()
        if not 2 <= len(entries) <= MAX_MEMBERS or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
            raise DatasetError("Research archive count or expansion exceeds its bound")
        names = set()
        for entry in entries:
            mode = entry.external_attr >> 16
            if (not _MEMBER.fullmatch(entry.filename) or entry.filename.casefold() in names
                    or entry.flag_bits & 1 or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                    or not 1 <= entry.file_size <= MAX_EXPANDED_BYTES):
                raise DatasetError("Research archive contains an unsafe or duplicate member")
            names.add(entry.filename.casefold())
            with archive.open(entry) as stream:
                metadata[entry.filename[:-4]] = _array_header(stream, entry)
    if "B" not in metadata or "y" not in metadata:
        raise DatasetError("Research archive lacks public covariates or target")
    return metadata


def _root(data_root):
    supplied = Path(data_root)
    if not supplied.is_absolute() or ".." in supplied.parts or str(supplied).startswith(("//", "\\\\")):
        raise DatasetError("An absolute ordinary local research root is required")
    _directories(supplied)
    return supplied


def load_research_dataset(data_root, corpus, max_rows=4096):
    """Return B/y only, with deterministic sampling and exact local-byte custody.

    Sampling uses only row count and a fixed seed before loading/inspecting target
    values. Existing training overlap means this is a reproducible adapter
    benchmark, never fresh scientific privacy-audit evidence.
    """
    if type(corpus) is not str or corpus not in CORPORA:
        raise DatasetError("Unknown allowlisted research corpus")
    if type(max_rows) is not int or not 32 <= max_rows <= 4096:
        raise DatasetError("Research sample bound must be from 32 to 4096 rows")
    try:
        root = _root(data_root)
        directory = root / "experiments" / _VERSION / corpus / "data"
        data_path, manifest_path = directory / "data.npz", directory / "manifest.json"
        blob, data_stamp = _read_file(data_path, MAX_COMPRESSED_BYTES)
        manifest_blob, manifest_stamp = _read_file(manifest_path, MAX_MANIFEST_BYTES)
        manifest = _manifest(manifest_blob, corpus, blob)
        arrays = _inspect_npz(blob)
        matrix, target = arrays["B"], arrays["y"]
        rows, columns = manifest["selected_rows"], len(_FEATURE_NAMES[corpus])
        if (matrix["shape"] != [rows, columns] or matrix["kind"] not in "buif"
                or target["shape"] != [rows] or target["kind"] not in "bui"):
            raise DatasetError("Research matrix and target must have exact numeric aligned dimensions")
        indices = np.random.default_rng(SELECTION_SEED).permutation(rows)[:min(rows, max_rows)]
        with np.load(io.BytesIO(blob), allow_pickle=False, max_header_size=MAX_HEADER_BYTES) as loaded:
            original_x, original_y = loaded["B"], loaded["y"]
            if not np.isfinite(original_x).all() or not np.isfinite(original_y).all():
                raise DatasetError("Research matrix or target contains nonfinite values")
            if set(np.unique(original_y).tolist()) != {0, 1}:
                raise DatasetError("Research target must contain both fixed binary classes")
            x = np.array(original_x[indices], dtype="<f8", order="C", copy=True)
            y = np.array(original_y[indices], dtype="u1", order="C", copy=True)
        if not np.isfinite(x).all() or set(np.unique(y).tolist()) != {0, 1}:
            raise DatasetError("The fixed sample cannot provide a finite two-class benchmark")
        names = list(_FEATURE_NAMES[corpus])
        selected_indices = indices.astype("<u8", copy=False).tobytes()
        matrix_description = json.dumps({"schema": "mra-research-matrix/v1", "features": names,
            "x_shape": list(x.shape), "x_dtype": "<f8", "y_shape": list(y.shape), "y_dtype": "|u1"},
            sort_keys=True, separators=(",", ":")).encode("ascii")
        sampled_digest = hashlib.sha256(matrix_description + b"\n" + selected_indices + x.tobytes() + y.tobytes()).hexdigest()
        source_digest = hashlib.sha256(blob).hexdigest()
        manifest_digest = hashlib.sha256(manifest_blob).hexdigest()
        metadata = {"schema": "mra-research-dataset/v1", "corpus": corpus, "task": "binary_classification",
            "source_kind": "historical_public_research_matrix", "source_bytes": len(blob),
            "source_relative_path": data_path.relative_to(root).as_posix(),
            "manifest_relative_path": manifest_path.relative_to(root).as_posix(),
            "manifest_sha256": manifest_digest, "source_rows": rows, "selected_rows": len(y),
            "feature_count": columns, "selection_seed": SELECTION_SEED,
            "selection": "fixed_seed_permutation_of_all_rows_before_target_inspection",
            "selection_indices_sha256": hashlib.sha256(selected_indices).hexdigest(),
            "sampled_matrix_sha256": sampled_digest,
            "source_array_shapes": {name: entry["shape"] for name, entry in arrays.items()},
            "source_array_dtypes": {name: entry["dtype"] for name, entry in arrays.items()},
            "returned_covariates": "B only", "omitted_fields": ["z", "keys", "strata", "source_panel", "source_row_indices"],
            "manifest_receipt_hash_matches": True, "upstream_receipts_rehashed": False,
            "historical_training_data_reused": True, "fresh_audit_evidence": False,
            "person_level_disjointness_established": False, "authorization_eligible": False,
            "production_authorized": False, "model_delivery": False,
            "limitations": ["Local manifest byte binding is not authenticated upstream provenance.",
                            "Historical source rows may already have been used in training and attack development.",
                            "Public-source conditional-record experiments do not establish person-level privacy."]}
        x.setflags(write=False)
        y.setflags(write=False)
        _recheck(data_path, MAX_COMPRESSED_BYTES, data_stamp, source_digest)
        _recheck(manifest_path, MAX_MANIFEST_BYTES, manifest_stamp, manifest_digest)
        return {"x": x, "y": y, "feature_names": names,
                "dataset_id": "research." + corpus + "." + _VERSION,
                "source_sha256": source_digest, "metadata": metadata}
    except DatasetError:
        raise
    except FileNotFoundError:
        raise DatasetUnavailable("Research source root or required file is absent") from None
    except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError, RecursionError,
            zipfile.BadZipFile, zlib.error, EOFError, struct.error):
        raise DatasetError("Research source could not pass bounded validation") from None


def source_inventory(data_root):
    """Validate prepared allowlisted sources only; never scan raw corpora or models."""
    try:
        root = _root(data_root)
    except FileNotFoundError:
        raise DatasetUnavailable("Research inventory root is absent") from None
    except (OSError, ValueError, TypeError):
        raise DatasetError("Research inventory root is unavailable") from None
    entries = []
    for corpus in CORPORA:
        try:
            dataset = load_research_dataset(root, corpus)
            entries.append({"corpus": corpus, "availability": "available", "dataset_id": dataset["dataset_id"],
                "source_sha256": dataset["source_sha256"], "feature_names": dataset["feature_names"],
                "metadata": dataset["metadata"]})
        except DatasetUnavailable:
            entries.append({"corpus": corpus, "availability": "missing", "reason": "required_source_absent"})
        except DatasetError:
            entries.append({"corpus": corpus, "availability": "rejected", "reason": "bounded_source_validation_failed"})
    return {"schema": "mra-research-source-inventory/v1", "scope": "four_allowlisted_prepared_matrices_only",
            "datasets": entries, "raw_corpora_scanned": False, "model_artifacts_loaded": False,
            "fresh_audit_evidence": False, "production_authorized": False}
