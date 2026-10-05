"""Read-only selection of the existing pinned Windows SACRO fixture runtime.

The 73 dependency versions and SACRO METADATA are checked without importing
external code. The existing worker independently verifies SACRO package/RECORD
bytes. This does not install, repair, download, or qualify a production image.
"""
from __future__ import annotations

from email.parser import BytesParser
from itertools import islice
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

from ..production_adapters import native
from ..production_sacro.execution import runtime_descriptor

LOCK_SHA256 = '44e427dfa46d9b40830755055adb953f9c9c884f4434533db813ce3cf8fff377'
REQUIREMENTS_SHA256 = 'b068b2b218eb2987bf3ba61b845ed2a1220bc53ee5327c51cb2ce640a051cf30'
SACRO_WHEEL_SHA256 = '8b0d5d9b32cff57d283a82722cbd244560d04cb6184ae7c493c6c94496957741'
SACRO_METADATA_SHA256 = '5e73a99e94b75ae1b19ff8077cdf42596b9fcf26f99de43f3187fda4040b41b3'
LOCK_PATH = 'deploy/sacro/windows-cp312.json'
REQUIREMENTS_PATH = 'deploy/sacro/windows-cp312.requirements.txt'
MAX_METADATA = 512 * 1024
MAX_SITE_ENTRIES = 4096
MAX_DISTRIBUTIONS = 128


class RuntimeError(ValueError):
    """The exact existing public-fixture runtime cannot be verified."""


def _reject():
    raise RuntimeError('Pinned local SACRO runtime unavailable')


def _name(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value):
        _reject()
    return re.sub(r'[-_.]+', '-', value).lower()


def _path(value):
    path = Path(value)
    if '..' in path.parts or str(path).startswith(('//', '\\\\')):
        _reject()
    return path.absolute()

_PINNED_VERSIONS = MappingProxyType({'Jinja2': '3.1.6',
 'MarkupSafe': '3.0.3',
 'PyJWT': '2.15.1',
 'PyYAML': '6.0.3',
 'acro': '1.0.2',
 'annotated-doc': '0.0.5',
 'annotated-types': '0.8.0',
 'anyio': '4.15.1',
 'certifi': '2026.7.22',
 'cffi': '2.1.0',
 'click': '8.5.0',
 'cloudpickle': '3.1.2',
 'contourpy': '1.4.0',
 'cryptography': '50.0.0',
 'cycler': '0.12.1',
 'dictdiffer': '0.10.0',
 'dill': '0.4.1',
 'et_xmlfile': '2.0.0',
 'fastapi': '0.142.2',
 'filelock': '4.0.8',
 'fonttools': '4.66.1',
 'formulaic': '1.2.2',
 'fpdf': '1.7.2',
 'fsspec': '2026.9.0',
 'h11': '0.16.0',
 'httpcore': '1.0.9',
 'httpx': '0.28.1',
 'idna': '3.20',
 'interface_meta': '2.0.1',
 'joblib': '1.6.0',
 'kiwisolver': '1.5.1',
 'lxml': '6.1.3',
 'matplotlib': '3.11.2',
 'mpmath': '1.3.0',
 'multiprocess': '0.70.19',
 'narwhals': '2.26.0',
 'networkx': '3.7',
 'numpy': '2.5.3',
 'openpyxl': '3.1.5',
 'opentelemetry-api': '1.45.0',
 'packaging': '26.3',
 'pandas': '2.3.3',
 'patsy': '1.0.3',
 'pillow': '12.3.0',
 'pip': '26.2.1',
 'prompt_toolkit': '3.0.53',
 'pycparser': '3.0',
 'pydantic': '2.13.4',
 'pydantic_core': '2.46.4',
 'pyparsing': '3.3.3',
 'pypdf': '6.19.0',
 'python-dateutil': '2.9.0.post0',
 'pytz': '2026.4',
 'rdflib': '7.6.0',
 'sacroml': '2.0.1',
 'scikit-learn': '1.6.1',
 'scipy': '1.18.1',
 'setuptools': '84.0.0',
 'six': '1.17.0',
 'starlette': '1.7.0',
 'statsmodels': '0.15.0',
 'sympy': '1.14.0',
 'tabulate': '0.10.0',
 'threadpoolctl': '3.7.0',
 'torch': '2.14.1',
 'typing-inspection': '0.4.2',
 'typing_extensions': '4.16.0',
 'tzdata': '2026.4',
 'uvicorn': '0.54.0',
 'wcwidth': '0.9.1',
 'wheel': '0.48.0',
 'wrapt': '2.5.0',
 'xgboost': '3.4.1'})


def validate_spec(versions, lock_sha256):
    """Return an owned exact version roster for direct installed-package callers."""
    if type(versions) is not dict or type(lock_sha256) is not str or lock_sha256 != LOCK_SHA256:
        _reject()
    snapshot = dict(versions)
    if (any(type(name) is not str or type(version) is not str for name, version in snapshot.items())
            or snapshot != dict(_PINNED_VERSIONS)):
        _reject()
    return snapshot


def _metadata(site, versions):
    native._real_directory(site)
    paths = list(islice(site.iterdir(), MAX_SITE_ENTRIES + 1))
    if len(paths) > MAX_SITE_ENTRIES:
        _reject()
    distributions = [path for path in paths if path.name.lower().endswith('.dist-info')]
    if not len(versions) <= len(distributions) <= MAX_DISTRIBUTIONS:
        _reject()
    found, captured = {}, {}
    for path in distributions:
        raw = native._read(path / 'METADATA', MAX_METADATA)
        metadata = BytesParser().parsebytes(raw, headersonly=True)
        if len(metadata.get_all('Name', [])) != 1 or len(metadata.get_all('Version', [])) != 1:
            _reject()
        name, version = _name(metadata['Name']), metadata['Version']
        if name in found or type(version) is not str or not 1 <= len(version) <= 128:
            _reject()
        found[name] = version
        captured[path / 'METADATA'] = raw
        if name == 'sacroml' and hashlib.sha256(raw).hexdigest() != SACRO_METADATA_SHA256:
            _reject()
    if any(found.get(_name(name)) != version for name, version in versions.items()):
        _reject()
    # Prior installed MRA is harmless here: worker module lookup explicitly
    # selects the current trusted package. Other extras are not silently blessed.
    if set(found) - {_name(name) for name in versions} - {'model-release-assurance'}:
        _reject()
    return captured


def load_runtime(root, python):
    """Return an owned pinned runtime descriptor; all operations are read-only."""
    try:
        root, python = _path(root), _path(python)
        native._real_directory(root)
        if not python.is_relative_to(root / '.local'):
            _reject()
        lock_path, requirements_path = root / LOCK_PATH, root / REQUIREMENTS_PATH
        raw = native._read(lock_path, 4 * 1024 * 1024)
        requirements = native._read(requirements_path, 128 * 1024)
        if (hashlib.sha256(raw).hexdigest() != LOCK_SHA256
                or hashlib.sha256(requirements).hexdigest() != REQUIREMENTS_SHA256):
            _reject()
        lock = json.loads(raw)
        if (lock['schema'] != 'mra-sacro-windows-wheel-lock/v1'
                or lock['sacroml_version'] != '2.0.1'
                or lock['sacroml_wheel_sha256'] != SACRO_WHEEL_SHA256
                or lock['fixture_only'] is not True or lock['production_authorized'] is not False
                or lock['target'] != {'platform': 'win_amd64', 'python': '3.12.14'}):
            _reject()
        versions = {item['name']: item['version'] for item in lock['artifacts']}
        versions = validate_spec(versions, LOCK_SHA256)
        if len(lock['artifacts']) != 73:
            _reject()
        descriptor = runtime_descriptor(python)
        site = _path(descriptor['site_packages'])
        if site != python.parent.parent / 'Lib/site-packages':
            _reject()
        captured = _metadata(site, versions)
        if (runtime_descriptor(python) != descriptor or native._read(lock_path, 4 * 1024 * 1024) != raw
                or native._read(requirements_path, 128 * 1024) != requirements
                or any(native._read(path, MAX_METADATA) != content for path, content in captured.items())):
            _reject()
        return {'python': str(python), 'versions': dict(versions), 'lock_sha256': LOCK_SHA256,
                'descriptor': dict(descriptor)}
    except Exception:
        raise RuntimeError('Pinned local SACRO runtime unavailable') from None
