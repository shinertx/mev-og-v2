"""Discover new DEX pools across domains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.logger import StructuredLogger

LOG = StructuredLogger("pool_scanner")


@dataclass
class PoolInfo:
    pool: str
    domain: str


class PoolScanner:
    """Scan subgraph or RPC endpoints for newly deployed pools."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def scan(self) -> List[PoolInfo]:
        try:
            import requests  # type: ignore

            resp = requests.get(f"{self.api_url}/pools", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return [PoolInfo(**d) for d in data]
        except Exception as exc:  # pragma: no cover - network errors
            LOG.log("scan_fail", risk_level="high", error=str(exc))
            return []
