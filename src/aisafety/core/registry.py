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
