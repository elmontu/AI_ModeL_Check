"""Read-only console bridge for four pinned historical public research matrices.

The environment is trusted local configuration, never an HTTP source-path input.
Configuration confirms an ordinary directory only; source availability and exact
historical byte pins are verified by the unchanged registered-profile loader.
These reused sources are not fresh privacy-audit evidence or release approval.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import stat
from types import MappingProxyType

ENV = "MRA_DEMO_RESEARCH_DATA_ROOT"
MAX_ROWS = 4096
SOURCE_KIND = "historical_public_research_matrix"
RESEARCH_DATASETS = MappingProxyType({
    "research-acs": "ACS public research matrix · up to 4096 rows · 8 covariates · 2 classes",
    "research-bts": "BTS flight public research matrix · up to 4096 rows · 7 covariates · 2 classes",
    "research-hmda": "HMDA mortgage public research matrix · up to 4096 rows · 7 covariates · 2 classes",
    "research-tlc": "TLC taxi public research matrix · up to 4096 rows · 4 covariates · 2 classes",
})


class ResearchDataError(ValueError):
    """The trusted research directory configuration is unsafe or invalid."""


class ResearchDataUnavailable(FileNotFoundError):
    """An explicit ordinary research directory is missing or unconfigured."""


def _directory_stamp(path):
    stamps = []
    try:
        for current in (*reversed(path.parents), path):
            info = current.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise ResearchDataError("Research directory must be ordinary and local")
            stamps.append((info.st_dev, info.st_ino))
    except FileNotFoundError:
        raise ResearchDataUnavailable("Configured research directory is absent") from None
    except OSError:
        raise ResearchDataError("Configured research directory is unavailable") from None
    return tuple(stamps)


def _ordinary_root(value):
    if not isinstance(value, (str, Path)):
        raise ResearchDataError("Research directory must be an absolute local path")
    try:
        path = Path(value)
        if (not path.is_absolute() or ".." in path.parts
                or str(path).startswith(("//", "\\\\"))):
            raise ResearchDataError("Research directory must be an absolute local path")
        _directory_stamp(path)
    except (TypeError, ValueError):
        raise ResearchDataError("Research directory must be an absolute ordinary local path") from None
    return path


def configured_research_root():
    """Return an ordinary absolute configured directory, or None when unset.

    Invalid configuration raises; it is never converted into a bundled fallback.
    This helper does not inspect raw corpora, parse models, or test corpus pins.
    """
    value = os.environ.get(ENV)
    return None if value in (None, "") else _ordinary_root(value)


def research_inventory():
    """Small HTTP-safe configuration metadata; never disclose the local path."""
    return {"configured": configured_research_root() is not None,
            "max_rows": MAX_ROWS, "source_kind": SOURCE_KIND}


def load_console_research(dataset, data_root=None):
    """Return (Bunch of B/y public arrays, owned exact registered provenance).

    Only four fixed binary profiles are accepted. Missing, changed or unpinned
    source bytes fail through the existing loader; no download or fallback runs.
    The withheld arrays and record identifiers never enter the returned Bunch.
    """
    if type(dataset) is not str or dataset not in RESEARCH_DATASETS:
        raise ResearchDataError("Unknown fixed research dataset")
    root = configured_research_root() if data_root is None else _ordinary_root(data_root)
    if root is None:
        raise ResearchDataUnavailable("Research data root is not configured")
    before = _directory_stamp(root)
    from ..production_registration.profiles import load_profile
    from sklearn.utils import Bunch
    profile_id = dataset.removeprefix("research-")
    loaded = load_profile(profile_id, data_root=root, max_rows=MAX_ROWS)
    if _directory_stamp(root) != before:
        raise ResearchDataError("Research directory changed during loading")
    # load_profile already returns owned, read-only B/y arrays. Preserve these
    # flags and select fields explicitly rather than passing the loader mapping.
    data = Bunch(data=loaded["x"], target=loaded["y"],
                 feature_names=list(loaded["feature_names"]), target_names=["0", "1"])
    provenance = {"dataset_id": dataset, "profile_id": profile_id, "source_kind": SOURCE_KIND,
                  "source_sha256": loaded["source_sha256"], "metadata": copy.deepcopy(loaded["metadata"])}
    return data, provenance
