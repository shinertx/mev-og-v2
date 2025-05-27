"""RWA price and fee feed.

Module purpose and system role:
    - Provide tokenized real-world asset price and settlement fee data.
    - Used by :mod:`strategies.rwa_settlement` for cross-venue settlement.

Integration points and dependencies:
    - Optional ``requests`` package for live HTTP queries.
    - Logs all failures via :func:`core.logger.log_error`.

Simulation/test hooks and kill conditions:
    - Works with offline stub data for unit tests and forked simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

try:  # pragma: no cover - optional
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from core.logger import log_error


@dataclass
class RWAData:
    price: float
    fee: float
    block: int


class RWAFeed:
    """Fetch RWA price and settlement fee information."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.getenv("RWA_FEED_URL", "http://localhost:9100")

    def fetch(self, asset: str, venue: str) -> RWAData:
        if requests is None:  # pragma: no cover
            raise RuntimeError("requests package required")
        url = f"{self.base_url}/{venue}/{asset}"
        try:  # pragma: no cover - network
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # pragma: no cover
            log_error("RWAFeed", str(exc), event="fetch", asset=asset, venue=venue)
            raise
        try:
            return RWAData(price=float(data["price"]), fee=float(data.get("fee", 0.0)), block=int(data.get("block", 0)))
        except Exception as exc:
            log_error("RWAFeed", f"parse error: {exc}", event="parse", asset=asset, venue=venue)
            raise
