"""Shared registry for inter-agent communication."""

from __future__ import annotations

from multiprocessing import Manager
from typing import Any

_manager = Manager()
_REGISTRY = _manager.dict()


def set_value(key: str, value: Any) -> None:
    """Store ``value`` under ``key``."""
    _REGISTRY[key] = value


def get_value(key: str, default: Any | None = None) -> Any:
    """Retrieve ``key`` from the registry."""
    return _REGISTRY.get(key, default)


def get_registry() -> dict[str, Any]:
    """Return a snapshot of the registry."""
    return dict(_REGISTRY)
