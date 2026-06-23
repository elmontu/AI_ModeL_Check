"""Checker registry — auto-discovery via @register_checker decorator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aisafety.core.base import BaseChecker

_REGISTRY: dict[str, type[BaseChecker]] = {}


def register_checker(cls: type[BaseChecker]) -> type[BaseChecker]:
    """Class decorator that registers a checker by its category."""
    _REGISTRY[cls.category] = cls
    return cls


def get_all_checkers() -> dict[str, type[BaseChecker]]:
    """Return all registered checkers."""
    return dict(_REGISTRY)


def get_checker(category: str) -> type[BaseChecker]:
    """Return checker class by category name."""
    if category not in _REGISTRY:
        raise KeyError(f"Unknown checker category: {category!r}. Available: {list(_REGISTRY)}")
    return _REGISTRY[category]


def get_checkers_for_model_type(model_type: str) -> dict[str, type[BaseChecker]]:
    """Return checkers compatible with a given model type."""
    return {
        cat: cls for cat, cls in _REGISTRY.items()
        if "all" in cls.model_types or model_type in cls.model_types
    }


def get_model_types() -> dict[str, list[str]]:
    """Return mapping of model_type → list of checker categories."""
    types: dict[str, list[str]] = {}
    for cat, cls in _REGISTRY.items():
        for mt in cls.model_types:
            types.setdefault(mt, []).append(cat)
    return types
