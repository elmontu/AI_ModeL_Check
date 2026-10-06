"""Pinned public garak runtime; package checks do not attest execution or isolation."""
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

GARAK_VERSION = "0.17.0"
WHEEL_SHA256 = "9a67e6298e4d7025358fecafa9d473c77ff70acdae103aa5251ad60fca3db145"
PYTHON_VERSION = "3.12.14"
COMPONENT_SCOPE = 'promptinject.HijackLongPrompt + promptinject.AttackRogueString + fixed local generators only'
UNSUPPORTED_DEPENDENCIES = ['mikeshardmind-base2048>=1.0.2',
 'transformers>=5.14.1,<6.0',
 'datasets>=3.0.0,<4.0',
 'cohere>=5.16.0',
 'anthropic>=0.40.0,<1.0.0',
 'openai>=2.0,<3.0',
 'replicate>=0.8.3',
 'google-api-python-client>=2.0',
 'backoff>=2.1.1',
 'accelerate>=0.23.0',
 'avidtools==0.1.2',
 'stdlibs>=2022.10.9',
 'langchain>=1.3.14',
 'cmd2==2.4.3',
 'torch>=2.13.0',
 'sentencepiece>=0.1.99',
 'markdown>=3.10.0',
 'zalgolib>=0.2.2',
 'ecoji>=0.1.1',
 'deepl==1.17.0',
 'litellm>=1.84.0',
 'llm>=0.31',
 'jsonpath-ng>=1.6.1',
 'huggingface_hub>=1.0',
 'python-magic-bin>=0.4.14; sys_platform == "win32"',
 'python-magic>=0.4.21; sys_platform != "win32"',
 'lorem==0.1.1',
 'wn==0.9.5',
 'ollama>=0.4.7',
 'nvidia-riva-client==2.16.0',
 'google-cloud-translate>=2.0.4',
 'grpcio-tools>=1.71.0',
 'tiktoken>=0.7.0',
 'mistralai==1.5.2',
 'pillow>=12.3.0',
 'ftfy>=6.3.1',
 'websockets>=13.0',
 'boto3>=1.28.0',
 'py-markdown-table>=1.2.0',
 'soundfile>=0.13.1 ; extra == "audio"',
 'librosa>=0.10.2 ; extra == "audio"',
 'detoxify>=0.5.0 ; extra == "dra"',
 'black>=26.5.1 ; extra == "lint"',
 'pylint>=3.1.0 ; extra == "lint"',
 'pytest>=9.1 ; extra == "tests"',
 'pytest-mock>=3.14.0 ; extra == "tests"',
 'requests-mock==1.12.1 ; extra == "tests"',
 'respx>=0.21.1 ; extra == "tests"',
 'pytest-cov>=5.0.0 ; extra == "tests"',
 'pytest_httpserver>=1.1.0 ; extra == "tests"',
 'pytest-asyncio>=0.21.0 ; extra == "tests"',
 'langcodes>=3.4.0 ; extra == "tests"']

class GarakRuntimeError(ValueError):
    """Installed source or runtime binding was rejected."""

class GarakRuntimeUnavailable(GarakRuntimeError):
    """A declared dependency is not installed; there is no substitute attack."""

def _fail():
    raise GarakRuntimeError("garak fixture runtime rejected")

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



LOCKED_VERSIONS = {'annotated-doc': '0.0.5',
 'annotated-types': '0.8.0',
 'anyio': '4.15.1',
 'certifi': '2026.7.22',
 'cffi': '2.1.0',
 'click': '8.5.0',
 'cloudpickle': '3.1.2',
 'colorama': '0.4.6',
 'cryptography': '50.0.0',
 'defusedxml': '0.7.1',
 'fastapi': '0.142.2',
 'garak': '0.17.0',
 'h11': '0.16.0',
 'httpcore': '1.0.9',
 'httpx': '0.28.1',
 'idna': '3.20',
 'joblib': '1.6.0',
 'langdetect': '1.0.9',
 'nltk': '3.10.3',
 'numpy': '2.5.3',
 'opentelemetry-api': '1.45.0',
 'packaging': '26.3',
 'pip': '26.2.1',
 'pycparser': '3.0',
 'pydantic': '2.13.4',
 'pydantic-core': '2.46.4',
 'pyjwt': '2.15.1',
 'pyyaml': '6.0.3',
 'regex': '2026.9.29',
 'scikit-learn': '1.6.1',
 'scipy': '1.18.1',
 'setuptools': '84.0.0',
 'six': '1.17.0',
 'starlette': '1.7.0',
 'threadpoolctl': '3.7.0',
 'tqdm': '4.70.1',
 'typing-extensions': '4.16.0',
 'typing-inspection': '0.4.2',
 'uvicorn': '0.54.0',
 'wheel': '0.48.0',
 'xdg-base-dirs': '6.0.3'}

NAMESPACE_PACKAGES = {"garak.langproviders", "garak.resources.api", "garak.services"}


def _check_modules(base):
    for name, module in tuple(sys.modules.items()):
        if name != "garak" and not name.startswith("garak."):
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
            # These three upstream namespace directories have no package marker.
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
    if distribution.version != GARAK_VERSION:
        _fail()
    base = Path(distribution.locate_file("")).absolute()
    package = base / "garak"
    native._real_directory(package)
    metadata = base / ("garak-" + GARAK_VERSION + ".dist-info")
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
    spec = importlib.util.find_spec("garak")
    if (spec is None or not spec.origin or Path(spec.origin).absolute() != package / "__init__.py"
            or list(spec.submodule_search_locations or []) != [str(package)]):
        _fail()
    _check_modules(base)
    return base



def expected_binding():
    return {"schema": "mra-garak-runtime-binding/v1", "garak_version": GARAK_VERSION,
            "wheel_sha256": WHEEL_SHA256, "metadata_sha256": METADATA_SHA256,
            "package_sha256": _digest(SOURCE_PINS), "source_files": len(SOURCE_PINS),
            "python_version": PYTHON_VERSION, "component_scope": COMPONENT_SCOPE,
            "full_upstream_dependency_set": False, "unsupported_dependencies": list(UNSUPPORTED_DEPENDENCIES), "fixture_only": True,
            "production_authorized": False, "model_delivery": False}

def _normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def probe_runtime(expected_versions):
    """Verify the exact declared package roster and garak files before importing garak.

    Only the selected component closure is supported, not the full upstream CLI.
    Transitive package versions are checked; garak contents are pinned against the
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
            raise GarakRuntimeUnavailable("Declared garak dependency unavailable")
        if observed != LOCKED_VERSIONS or platform.python_version() != PYTHON_VERSION:
            _fail()
        _checked_distribution(importlib.metadata.distribution('garak'))
        return expected_binding()
    except importlib.metadata.PackageNotFoundError:
        raise GarakRuntimeUnavailable("Declared garak dependency unavailable") from None
    except GarakRuntimeError:
        raise
    except Exception:
        raise GarakRuntimeError("garak fixture runtime rejected") from None
