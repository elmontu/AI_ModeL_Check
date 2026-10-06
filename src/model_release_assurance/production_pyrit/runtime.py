"""Pinned public pyrit runtime; package checks do not attest execution or isolation."""
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
from .pins import (SOURCE_PINS, METADATA_SHA256, LOCKED_VERSIONS, UNSUPPORTED_DEPENDENCIES,
                   COMPONENT_SCOPE, PYRIT_VERSION, WHEEL_SHA256, PYTHON_VERSION,
                   APPDIRS_SHA256, APPDIRS_SIZE, APPDIRS_METADATA_SHA256)
from ..version import VERSION

class PyritRuntimeError(ValueError):
    """Installed source or runtime binding was rejected."""

class PyritRuntimeUnavailable(PyritRuntimeError):
    """A declared dependency is not installed; there is no substitute attack."""

def _fail():
    raise PyritRuntimeError("pyrit fixture runtime rejected")

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



# Exact namespace directories from the verified PyRIT wheel, never a generic exception.
NAMESPACE_PACKAGES = frozenset({
    "pyrit.converter.ansi_escape", "pyrit.datasets.executors",
    "pyrit.datasets.executors.question_answer", "pyrit.datasets.jailbreak",
    "pyrit.datasets.seed_datasets", "pyrit.memory.alembic", "pyrit.memory.alembic.versions",
    "pyrit.prompt_target.common", "pyrit.prompt_target.http_target",
    "pyrit.prompt_target.hugging_face", "pyrit.prompt_target.openai",
    "pyrit.score.float_scale", "pyrit.score.scorer_evaluation", "pyrit.score.true_false",
})


def _check_modules(base):
    for name, module in tuple(sys.modules.items()):
        if name != "pyrit" and not name.startswith("pyrit."):
            continue
        if module is None:
            _fail()
        relative = name.replace(".", "/")
        candidates = [relative + ".py", relative + "/__init__.py"]
        expected = [base / item for item in candidates if item in SOURCE_PINS]
        actual = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        if name in NAMESPACE_PACKAGES:
            folder = base / relative
            native._real_directory(folder)
            # These allowlisted upstream namespace directories have no package marker.
            # Their entire contents remain covered by SOURCE_PINS and RECORD.
            if (expected or actual is not None or spec is None or spec.origin is not None
                    or list(getattr(module, "__path__", [])) != [str(folder)]
                    or list(spec.submodule_search_locations or []) != [str(folder)]
                    or not any(item.startswith(relative + "/") for item in SOURCE_PINS)):
                _fail()
            continue
        if (len(expected) != 1 or not actual or Path(actual).absolute() != expected[0]
                or spec is None or Path(str(spec.origin)).absolute() != expected[0]):
            _fail()
        if expected[0].name == "__init__.py":
            locations = list(getattr(module, "__path__", []))
            if locations != [str(expected[0].parent)]:
                _fail()


def _checked_distribution(distribution):
    if distribution.version != PYRIT_VERSION:
        _fail()
    base = Path(distribution.locate_file("")).absolute()
    package = base / "pyrit"
    native._real_directory(package)
    metadata = base / ("pyrit-" + PYRIT_VERSION + ".dist-info")
    if hashlib.sha256(_file(metadata / "METADATA", 256 * 1024)).hexdigest() != METADATA_SHA256:
        _fail()
    rows = list(csv.reader(io.StringIO(_file(metadata / "RECORD", 1024 * 1024).decode("utf-8"))))
    if not 1 <= len(rows) <= 2048 or any(len(row) != 3 for row in rows):
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
            if relative not in SOURCE_PINS or len(actual) > 2048:
                _fail()
    if actual != set(SOURCE_PINS):
        _fail()
    for name, pin in SOURCE_PINS.items():
        raw = _file(base / name, pin["size_bytes"])
        expected_record = "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(pin["sha256"])).decode("ascii").rstrip("=")
        if (len(raw) != pin["size_bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]
                or record.get(name) != (expected_record, str(pin["size_bytes"]))):
            _fail()
    spec = importlib.util.find_spec("pyrit")
    if (spec is None or not spec.origin or Path(spec.origin).absolute() != package / "__init__.py"
            or list(spec.submodule_search_locations or []) != [str(package)]):
        _fail()
    _check_modules(base)
    return base



def _checked_appdirs(distribution, expected_base):
    """Check the exact dependency whose directory API the adapter redirects."""
    if distribution.version != "1.4.4":
        _fail()
    base = Path(distribution.locate_file("")).absolute()
    if base != Path(expected_base).absolute():
        _fail()
    native._real_directory(base)
    metadata = base / "appdirs-1.4.4.dist-info"
    metadata_raw = _file(metadata / "METADATA", 64 * 1024)
    if hashlib.sha256(metadata_raw).hexdigest() != APPDIRS_METADATA_SHA256:
        _fail()
    rows = list(csv.reader(io.StringIO(_file(metadata / "RECORD", 64 * 1024).decode("utf-8"))))
    if not 1 <= len(rows) <= 64 or any(len(row) != 3 for row in rows):
        _fail()
    record = {}
    for name, value, size in rows:
        if name in record:
            _fail()
        record[name] = (value, size)
    path = base / "appdirs.py"
    raw = _file(path, APPDIRS_SIZE)
    if len(raw) != APPDIRS_SIZE or hashlib.sha256(raw).hexdigest() != APPDIRS_SHA256:
        _fail()
    for name, digest, size in (("appdirs.py", APPDIRS_SHA256, APPDIRS_SIZE),
                               ("appdirs-1.4.4.dist-info/METADATA", APPDIRS_METADATA_SHA256, len(metadata_raw))):
        expected_record = "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(digest)).decode("ascii").rstrip("=")
        if record.get(name) != (expected_record, str(size)):
            _fail()
    spec = importlib.util.find_spec("appdirs")
    if (spec is None or not spec.origin or Path(spec.origin).absolute() != path
            or spec.submodule_search_locations is not None):
        _fail()
    for name, module in tuple(sys.modules.items()):
        if name != "appdirs" and not name.startswith("appdirs."):
            continue
        loaded_spec = getattr(module, "__spec__", None)
        actual = getattr(module, "__file__", None)
        if (name != "appdirs" or module is None or not actual or Path(actual).absolute() != path
                or loaded_spec is None or not loaded_spec.origin
                or Path(loaded_spec.origin).absolute() != path
                or loaded_spec.submodule_search_locations is not None):
            _fail()
    return base


def expected_binding():
    return {"schema": "mra-pyrit-runtime-binding/v1", "pyrit_version": PYRIT_VERSION,
            "wheel_sha256": WHEEL_SHA256, "metadata_sha256": METADATA_SHA256,
            "package_sha256": _digest(SOURCE_PINS), "source_files": len(SOURCE_PINS),
            "python_version": PYTHON_VERSION, "component_scope": COMPONENT_SCOPE,
            "appdirs_version": "1.4.4", "appdirs_source_sha256": APPDIRS_SHA256,
            "appdirs_metadata_sha256": APPDIRS_METADATA_SHA256,
            "namespace_packages": sorted(NAMESPACE_PACKAGES),
            "storage_hook": "adapter redirects appdirs.user_data_dir to the fresh owned D child cache before PyRIT imports",
            "full_upstream_dependency_set": False, "unsupported_dependencies": list(UNSUPPORTED_DEPENDENCIES), "fixture_only": True,
            "production_authorized": False, "model_delivery": False}

def _normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def probe_runtime(expected_versions):
    """Verify the exact declared package roster and pyrit files before importing pyrit.

    Only the selected component closure is supported, not the full upstream CLI.
    Transitive package versions are checked; pyrit contents are pinned against the
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
            raise PyritRuntimeUnavailable("Declared pyrit dependency unavailable")
        if observed != LOCKED_VERSIONS or platform.python_version() != PYTHON_VERSION:
            _fail()
        base = _checked_distribution(importlib.metadata.distribution('pyrit'))
        _checked_appdirs(importlib.metadata.distribution('appdirs'), base)
        return expected_binding()
    except importlib.metadata.PackageNotFoundError:
        raise PyritRuntimeUnavailable("Declared pyrit dependency unavailable") from None
    except PyritRuntimeError:
        raise
    except Exception:
        raise PyritRuntimeError("pyrit fixture runtime rejected") from None
