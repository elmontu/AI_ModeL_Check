"""Native temporary cache namespace for mocked PyRIT orchestration fixtures.

These tests exercise real cache-binding checks and filesystem routing with mocked
source, interpreter, appdirs and worker interfaces. They do not qualify PyRIT or
a non-Windows execution platform. Pure protocol policy tests retain the actual
Windows path class and the production D: boundary without this adapter.
"""
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from model_release_assurance.production_pyrit import protocol
import test_production_pyrit_protocol as protocol_fixtures

_POLICY_ROOT = PureWindowsPath("D:/ChatGPT/model_audit/AI_ModeL_Check_Government/.local")


@contextmanager
def owned_pyrit_cache_fixture(root):
    """Map synthetic policy paths into one real, owned temporary fixture tree."""
    root = Path(root).absolute()
    if not root.is_dir():
        raise ValueError("The cache fixture requires its existing temporary root")

    def fixture_path(value):
        native = Path(value)
        # Actual fixture descendants must remain unchanged even when a local
        # temporary directory itself happens to be beneath the D: policy root.
        if native.is_absolute() and native.is_relative_to(root):
            return native
        windows = PureWindowsPath(str(value))
        if windows.is_relative_to(_POLICY_ROOT):
            return root.joinpath(*windows.relative_to(_POLICY_ROOT).parts)
        return native

    # Preserve the validator itself: shape, traversal, absolute/owned roots,
    # exact stage, descendant paths and fields still receive its real checks.
    with patch.object(protocol, "PureWindowsPath", fixture_path), \
            patch.object(protocol_fixtures, "PureWindowsPath", fixture_path):
        yield root
