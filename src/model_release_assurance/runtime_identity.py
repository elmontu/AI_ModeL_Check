from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .version import VERSION


class RuntimeIdentity(BaseModel):
    """Replayable identity of the software component that emitted an artifact."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    schema_version: Literal["1.0"] = "1.0"
    package_name: Literal["model-release-assurance"] = "model-release-assurance"
    package_version: str
    package_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    component_id: str = Field(min_length=1, max_length=128)
    component_version: str = Field(min_length=1, max_length=64)
    algorithm_profile: dict[str, Any]
    algorithm_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    python_implementation: str = Field(min_length=1, max_length=64)
    python_version: str = Field(min_length=1, max_length=64)
    dependency_versions: dict[str, str]

    @model_validator(mode="after")
    def algorithm_profile_digest_replays(self) -> RuntimeIdentity:
        if not self.algorithm_profile:
            raise ValueError("runtime identity requires a non-empty algorithm profile")
        if self.algorithm_profile_sha256 != _canonical_sha256(self.algorithm_profile):
            raise ValueError("runtime identity algorithm-profile digest does not replay")
        return self


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=1)
def package_source_sha256() -> str:
    """Hash the installed package's Python sources with relative-path framing."""

    package_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    sources = sorted(
        path for path in package_root.rglob("*.py") if path.is_file()
    )
    if not sources:
        raise RuntimeError("model-release-assurance package contains no Python sources")
    for path in sources:
        relative = path.relative_to(package_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def current_runtime_identity(
    component_id: str,
    component_version: str,
    algorithm_profile: dict[str, Any],
) -> RuntimeIdentity:
    """Build the runtime identity embedded in a generated report or verification."""

    return RuntimeIdentity(
        package_version=VERSION,
        package_source_sha256=package_source_sha256(),
        component_id=component_id,
        component_version=component_version,
        algorithm_profile=algorithm_profile,
        algorithm_profile_sha256=_canonical_sha256(algorithm_profile),
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        dependency_versions={
            "cryptography": _installed_version("cryptography"),
            "numpy": _installed_version("numpy"),
            "pydantic": _installed_version("pydantic"),
            "scikit-learn": _installed_version("scikit-learn"),
            "scipy": _installed_version("scipy"),
        },
    )
