"""Strategy TTL enforcement utilities."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from core.logger import StructuredLogger, log_error

try:
    import yaml  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional
    yaml = None  # type: ignore


class StrategyTTLManager:
    """Enforce per-strategy TTL based on ``EDGE_SCHEMA`` metadata."""

    def __init__(self, orchestrator: Any | None = None) -> None:
        self.logger = StructuredLogger("strategy_ttl")
        self.orchestrator = orchestrator

    # ------------------------------------------------------------------
    def _simple_yaml_load(self, text: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        stack: List[tuple[int, Dict[str, Any]]] = [(0, data)]
        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip())
            key, _, value = raw.lstrip().partition(":")
            value = value.strip()
            while stack and indent < stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if not value:
                d: Dict[str, Any] = {}
                parent[key] = d
                stack.append((indent + 1, d))
                continue
            if value == "{}":
                parent[key] = {}
            elif value.startswith("[") and value.endswith("]"):
                items = [v.strip().strip('"\'') for v in value[1:-1].split(",") if v.strip()]
                parent[key] = items
            elif value.lower() in {"true", "false"}:
                parent[key] = value.lower() == "true"
            else:
                try:
                    parent[key] = int(value)
                except ValueError:
                    try:
                        parent[key] = float(value)
                    except ValueError:
                        parent[key] = value.strip('"\'')
        return data

    # ------------------------------------------------------------------
    def _read_edge_schema(self, path: Path) -> Dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        delim = '"""'
        idx = text.find(delim)
        if idx == -1:
            return {}
        end = text.find(delim, idx + 3)
        if end == -1:
            return {}
        block = text[idx + 3 : end]
        if yaml is not None:
            try:
                data = yaml.safe_load(block)
                return data or {}
            except Exception:
                pass
        return self._simple_yaml_load(block)

    # ------------------------------------------------------------------
    def _expired(self, path: Path, ttl_hours: int) -> bool:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        expire_time = mtime + timedelta(hours=ttl_hours)
        return datetime.now(timezone.utc) >= expire_time

    # ------------------------------------------------------------------
    async def enforce_all_ttls(self, paths: List[Path]) -> List[Path]:
        """Return only paths whose TTL has not expired."""
        active: List[Path] = []
        for path in paths:
            if not path.exists():
                log_error("strategy_ttl", "missing strategy", strategy_id=path.stem, event="missing")
                continue
            try:
                schema = self._read_edge_schema(path)
                ttl = int(schema.get("ttl_hours", 0))
            except Exception as exc:  # pragma: no cover - invalid schema
                log_error(
                    "strategy_ttl",
                    f"ttl parse fail: {exc}",
                    strategy_id=path.stem,
                    event="ttl_parse_fail",
                )
                ttl = 0
            if ttl and self._expired(path, ttl):
                self.logger.log(
                    "strategy_expired",
                    strategy_id=schema.get("strategy_id", path.stem),
                    ttl_hours=ttl,
                    risk_level="low",
                )
                continue
            active.append(path)
        return active
