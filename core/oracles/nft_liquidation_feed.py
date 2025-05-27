"""NFT liquidation auction feed.

Module purpose and system role:
    - Fetch open NFT liquidation auctions from an HTTP endpoint.
    - Used by :mod:`strategies.nft_liquidation` to identify snipe opportunities.

Integration points and dependencies:
    - Requires the ``requests`` package when used live.
    - Logs all errors via :func:`core.logger.log_error`.

Simulation/test hooks and kill conditions:
    - Designed for forked-mainnet or unit test environments.
    - Can be stubbed with dummy data for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import os

try:  # pragma: no cover - optional dep
    import requests
except Exception:  # pragma: no cover - tests may skip
    requests = None  # type: ignore

from core.logger import log_error


@dataclass
class AuctionData:
    nft: str
    price: float
    value: float
    auction_id: str
    end_block: int


class NFTLiquidationFeed:
    """Fetch NFT liquidation auctions."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.getenv("NFT_FEED_URL", "http://localhost:9000")

    def fetch_auctions(self, domain: str) -> List[AuctionData]:
        if requests is None:  # pragma: no cover - dependency missing
            raise RuntimeError("requests package required")
        url = f"{self.base_url}/{domain}/auctions"
        try:  # pragma: no cover - network
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            log_error("NFTLiquidationFeed", str(exc), event="fetch_auctions", domain=domain)
            raise
        auctions: List[AuctionData] = []
        for item in data:
            try:
                auctions.append(AuctionData(**item))
            except Exception as exc:
                log_error("NFTLiquidationFeed", f"bad auction: {exc}", event="parse", domain=domain)
        return auctions
