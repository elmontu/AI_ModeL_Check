"""Pinned public ART runtime; package checks do not attest execution or isolation."""
from __future__ import annotations
import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import os
from pathlib import Path
import platform
import re
import stat
import sys
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes
from .pins import SOURCE_PINS, METADATA_SHA256
from ..version import VERSION

ART_VERSION = "1.20.1"
WHEEL_SHA256 = "03b15b35d2a1a564a436b023ad90968d64542e3ff191c668bffb8207f38683f5"
NUMERICAL_VERSIONS = {"python": "3.12.14", "numpy": "2.5.3", "scipy": "1.18.1", "scikit-learn": "1.6.1", "joblib": "1.6.0", "threadpoolctl": "3.7.0"}
ATTACK_PARAMETERS = {"input_type": "loss", "attack_model_type": "lr", "scaler_type": "standard", "C": 1.0, "solver": "lbfgs", "max_iter": 500, "random_state": 20261006}

class ArtRuntimeError(ValueError):
    """Installed source or runtime binding was rejected."""

class ArtRuntimeUnavailable(ArtRuntimeError):
    """A declared dependency is not installed; there is no substitute attack."""

def _fail():
    raise ArtRuntimeError("ART fixture runtime rejected")

def _digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def _file(path, maximum):
    native._real_directory(path.parent)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_nlink != 1
            or not 0 <= before.st_size <= maximum):
        raise ValueError("Unsafe or oversized native adapter artifact")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or getattr(opened, "st_file_attributes", 0) & 0x400):
            raise ValueError("Opened artifact is not a single regular file")
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError("Artifact identity changed before read")
        raw = stream.read(maximum + 1)
        end = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns):
            raise ValueError("Artifact changed through open descriptor")
    after = path.lstat()
    if (len(raw) != before.st_size or len(raw) > maximum
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ValueError("Native adapter artifact changed during read")
    return raw



LOCKED_VERSIONS = {'adversarial-robustness-toolbox': '1.20.1', 'annotated-doc': '0.0.5', 'annotated-types': '0.8.0', 'anyio': '4.15.1', 'certifi': '2026.7.22', 'cffi': '2.1.0', 'click': '8.5.0', 'cloudpickle': '3.1.2', 'colorama': '0.4.6', 'cryptography': '50.0.0', 'fastapi': '0.142.2', 'h11': '0.16.0', 'httpcore': '1.0.9', 'httpx': '0.28.1', 'idna': '3.20', 'joblib': '1.6.0', 'numpy': '2.5.3', 'opentelemetry-api': '1.45.0', 'packaging': '26.3', 'pip': '26.2.1', 'pycparser': '3.0', 'pydantic': '2.13.4', 'pydantic-core': '2.46.4', 'pyjwt': '2.15.1', 'scikit-learn': '1.6.1', 'scipy': '1.18.1', 'setuptools': '84.0.0', 'six': '1.17.0', 'starlette': '1.7.0', 'threadpoolctl': '3.7.0', 'tqdm': '4.70.1', 'typing-extensions': '4.16.0', 'typing-inspection': '0.4.2', 'uvicorn': '0.54.0', 'wheel': '0.48.0'}

def _check_modules(base):
    for name, module in tuple(sys.modules.items()):
        if name != "art" and not name.startswith("art."):
            continue
        if module is None:
            _fail()
        relative = name.replace(".", "/")
        candidates = [relative + ".py", relative + "/__init__.py"]
        expected = [base / item for item in candidates if item in SOURCE_PINS]
        actual = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        if (len(expected) != 1 or not actual or Path(actual).absolute() != expected[0]
                or spec is None or Path(str(spec.origin)).absolute() != expected[0]):
            _fail()
        if expected[0].name == "__init__.py":
            locations = list(getattr(module, "__path__", []))
            if locations != [str(expected[0].parent)]:
                _fail()


def _checked_distribution(distribution):
    if distribution.version != ART_VERSION:
        _fail()
    base = Path(distribution.locate_file("")).absolute()
    package = base / "art"
    native._real_directory(package)
    metadata = base / ("adversarial_robustness_toolbox-" + ART_VERSION + ".dist-info")
    if hashlib.sha256(_file(metadata / "METADATA", 256 * 1024)).hexdigest() != METADATA_SHA256:
        _fail()
    rows = list(csv.reader(io.StringIO(_file(metadata / "RECORD", 1024 * 1024).decode("utf-8"))))
    if not 1 <= len(rows) <= 1024 or any(len(row) != 3 for row in rows):
        _fail()
    record = {}
    for name, value, size in rows:
        if name in record:
            _fail()
        record[name] = (value, size)
    actual = set()
    for folder, dirs, files in os.walk(package, followlinks=False):
        for dirname in dirs:
            info = (Path(folder) / dirname).lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                _fail()
        for filename in files:
            relative = (Path(folder) / filename).relative_to(base).as_posix()
            actual.add(relative)
            if relative not in SOURCE_PINS or len(actual) > 1024:
                _fail()
    if actual != set(SOURCE_PINS):
        _fail()
    for name, pin in SOURCE_PINS.items():
        raw = _file(base / name, pin["size_bytes"])
        expected_record = "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(pin["sha256"])).decode("ascii").rstrip("=")
        if (len(raw) != pin["size_bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]
                or record.get(name) != (expected_record, str(pin["size_bytes"]))):
            _fail()
    spec = importlib.util.find_spec("art")
    if (spec is None or not spec.origin or Path(spec.origin).absolute() != package / "__init__.py"
            or list(spec.submodule_search_locations or []) != [str(package)]):
        _fail()
    _check_modules(base)
    return base



def expected_binding():
    return {"schema": "mra-art-runtime-binding/v1", "art_version": ART_VERSION,
            "wheel_sha256": WHEEL_SHA256, "metadata_sha256": METADATA_SHA256,
            "package_sha256": _digest(SOURCE_PINS), "source_files": len(SOURCE_PINS),
            "numerical_versions": dict(NUMERICAL_VERSIONS), "fixture_only": True,
            "production_authorized": False, "model_delivery": False}

def _normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def probe_runtime(expected_versions):
    """Verify the exact declared package roster and ART files before importing ART.

    Transitive package versions are checked; ART contents are pinned against the
    verified upstream wheel. This is trusted local software, not host attestation.
    """
    if canonical_bytes(expected_versions) != canonical_bytes(LOCKED_VERSIONS):
        _fail()
    try:
        observed = {}
        for distribution in importlib.metadata.distributions():
            name = _normalized(distribution.metadata['Name'])
            if name in observed:
                _fail()
            observed[name] = distribution.version
            if name == 'model-release-assurance':
                base = Path(distribution.locate_file('')).absolute()
                loaded = Path(__file__).absolute().parent.parent
                installed = Path(distribution.locate_file('model_release_assurance')).absolute()
                if distribution.version != VERSION or installed != loaded or loaded.parent != base:
                    _fail()
                native._real_directory(installed)
        observed.pop('model-release-assurance', None)
        missing = set(LOCKED_VERSIONS) - set(observed)
        if missing:
            raise ArtRuntimeUnavailable("Declared ART dependency unavailable")
        if observed != LOCKED_VERSIONS or platform.python_version() != NUMERICAL_VERSIONS['python']:
            _fail()
        _checked_distribution(importlib.metadata.distribution('adversarial-robustness-toolbox'))
        return expected_binding()
    except importlib.metadata.PackageNotFoundError:
        raise ArtRuntimeUnavailable("Declared ART dependency unavailable") from None
    except ArtRuntimeError:
        raise
    except Exception:
        raise ArtRuntimeError("ART fixture runtime rejected") from None
