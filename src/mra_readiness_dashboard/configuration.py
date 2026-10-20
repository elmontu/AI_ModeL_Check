"""Explicit private configuration; fictional lessons remain the public default."""
from __future__ import annotations
import json
from pathlib import Path
import stat
from .console_integration import ReadinessConfig

SCHEMA = "mra-readiness-captured-config/1"
READINESS_CONFIG_ENV = "MRA_READINESS_CONFIG"
_FIELDS = {"schema", "bundle", "manifest_sha256", "intake_report", "intake_manifest_sha256",
           "handoff_packet", "handoff_archive_sha256", "handoff_manifest_sha256", "suspend_presentation"}
_PATHS = {"bundle", "intake_report", "handoff_packet"}


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("Duplicate configuration key")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError("Non-finite configuration value")


def load_readiness_config(path: Path) -> ReadinessConfig:
    """Read an explicit bounded profile without accepting its evidence.

    Relative paths use the profile directory. Existing captured-input checks
    retain all pins and run on every request. Failure never selects demo mode.
    """
    path = Path(path).absolute()
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_size > 65536):
        raise ValueError("Readiness profile must be a bounded ordinary JSON file")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Readiness profile exceeds its size limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid readiness profile JSON") from exc
    if (not isinstance(value, dict) or set(value) - _FIELDS
            or value.get("schema") != SCHEMA
            or not {"bundle", "manifest_sha256"} <= set(value)):
        raise ValueError("Unknown or incomplete readiness profile schema")
    values = {key: item for key, item in value.items() if key != "schema"}
    for key in _PATHS & values.keys():
        item = values[key]
        if item is None and key != "bundle":
            continue
        if (type(item) is not str or not item.strip() or len(item) > 4096
                or any(ord(char) < 32 for char in item)):
            raise ValueError("Readiness input paths must be nonempty local paths")
        item = Path(item)
        values[key] = item if item.is_absolute() else path.parent / item
    return ReadinessConfig(**values)
