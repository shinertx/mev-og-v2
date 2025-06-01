"""Market event feed adapter.

This adapter ingests, normalizes and broadcasts market events from
multiple realtime sources (DEX/CEX listings, launchpad/IDO, social
feeds, NFT/bridge events). It integrates with the agent registry so
strategies can subscribe to events without direct dependencies. All
errors and anomalies are logged via :class:`core.logger.StructuredLogger`
and Prometheus metrics via ``core.metrics``. The adapter triggers DRP
snapshots on critical failures and supports dry-run simulation via the
``SIM_MARKET_EVENTS`` environment variable.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agents.agent_registry import set_value
from agents.ops_agent import OpsAgent
from core.logger import StructuredLogger
from core import metrics

LOGGER = StructuredLogger("market_event_feed")


@dataclass
class MarketEvent:
    """Normalized market event."""

    source: str
    event_type: str
    data: Dict[str, Any]
    timestamp: float


class MarketEventFeedAdapter:
    """Ingest and publish market events from multiple feeds.

    Parameters are lists of base URLs for each feed type. Fallbacks are
    attempted in order if a feed returns an error. Subscribers are
    notified with :class:`MarketEvent` instances and events are cached in
    ``agents.agent_registry`` under the ``market_events`` key.
    """

    def __init__(
        self,
        dex_urls: Optional[List[str]] = None,
        cex_urls: Optional[List[str]] = None,
        launchpad_urls: Optional[List[str]] = None,
        social_urls: Optional[List[str]] = None,
        nft_urls: Optional[List[str]] = None,
        bridge_urls: Optional[List[str]] = None,
        *,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.dex_urls = [u.rstrip("/") for u in dex_urls or []]
        self.cex_urls = [u.rstrip("/") for u in cex_urls or []]
        self.launchpad_urls = [u.rstrip("/") for u in launchpad_urls or []]
        self.social_urls = [u.rstrip("/") for u in social_urls or []]
        self.nft_urls = [u.rstrip("/") for u in nft_urls or []]
        self.bridge_urls = [u.rstrip("/") for u in bridge_urls or []]
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0
        self.subscribers: List[Callable[[MarketEvent], None]] = []

    # ---------------------------------------------------------------
    def subscribe(self, func: Callable[[MarketEvent], None]) -> None:
        """Register ``func`` to receive all future events."""

        self.subscribers.append(func)

    # ---------------------------------------------------------------
    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOGGER.log(event, risk_level="high", error=str(err))
        metrics.record_fail()
        if self.ops_agent:
            self.ops_agent.notify(f"market_event_feed:{event}:{err}")
        if self.failures >= self.fail_threshold:
            self._export_snapshot()
            raise RuntimeError("circuit breaker open")

    # ---------------------------------------------------------------
    def _export_snapshot(self) -> None:
        """Invoke DRP snapshot script in dry-run mode."""

        try:
            subprocess.run([
                "bash",
                "scripts/export_state.sh",
                "--dry-run",
            ], check=True, capture_output=True, text=True)
            LOGGER.log("snapshot_export", risk_level="low")
        except Exception as exc:
            LOGGER.log("snapshot_export_fail", risk_level="high", error=str(exc))

    # ---------------------------------------------------------------
    def _request(self, url: str) -> Any:
        import requests  # type: ignore

        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()

    # ---------------------------------------------------------------
    def _load_sim_events(self) -> List[MarketEvent]:
        path = os.getenv("SIM_MARKET_EVENTS")
        if not path or not os.path.exists(path):
            return []
        try:
            data = json.loads(open(path).read())
            events = [
                MarketEvent(
                    e.get("source", "sim"),
                    e.get("event_type", "sim"),
                    e.get("data", {}),
                    float(e.get("timestamp", time.time())),
                )
                for e in data
                if isinstance(e, dict)
            ]
            LOGGER.log("load_sim_events", risk_level="low", count=len(events))
            return events
        except Exception as exc:
            LOGGER.log("sim_event_fail", risk_level="high", error=str(exc))
            return []

    # ---------------------------------------------------------------
    def _fetch_list(self, urls: List[str], path: str) -> List[Dict[str, Any]]:
        for url in urls:
            try:
                data = self._request(f"{url}/{path}")
                if isinstance(data, list):
                    LOGGER.log("fetch_success", risk_level="low", source=url)
                    self.failures = 0
                    return data
            except Exception as exc:  # pragma: no cover - network
                self._alert("fetch_fail", exc)
                continue
        return []

    # ---------------------------------------------------------------
    def fetch_dex_listings(self) -> List[MarketEvent]:
        data = self._fetch_list(self.dex_urls, "listings")
        return [
            MarketEvent("dex", "dex_listing", d, time.time()) for d in data
        ]

    # ---------------------------------------------------------------
    def fetch_cex_listings(self) -> List[MarketEvent]:
        data = self._fetch_list(self.cex_urls, "listings")
        return [
            MarketEvent("cex", "cex_listing", d, time.time()) for d in data
        ]

    # ---------------------------------------------------------------
    def fetch_launchpad_events(self) -> List[MarketEvent]:
        data = self._fetch_list(self.launchpad_urls, "events")
        return [
            MarketEvent("launchpad", "launchpad_event", d, time.time())
            for d in data
        ]

    # ---------------------------------------------------------------
    def fetch_social_events(self) -> List[MarketEvent]:
        data = self._fetch_list(self.social_urls, "events")
        return [
            MarketEvent("social", "social_event", d, time.time()) for d in data
        ]

    # ---------------------------------------------------------------
    def fetch_nft_events(self) -> List[MarketEvent]:
        data = self._fetch_list(self.nft_urls, "events")
        return [
            MarketEvent("nft", "nft_event", d, time.time()) for d in data
        ]

    # ---------------------------------------------------------------
    def fetch_bridge_events(self) -> List[MarketEvent]:
        data = self._fetch_list(self.bridge_urls, "events")
        return [
            MarketEvent("bridge", "bridge_event", d, time.time()) for d in data
        ]

    # ---------------------------------------------------------------
    def poll(self) -> List[MarketEvent]:
        """Fetch all events and notify subscribers."""

        events: List[MarketEvent] = []
        events.extend(self._load_sim_events())
        fetchers = [
            self.fetch_dex_listings,
            self.fetch_cex_listings,
            self.fetch_launchpad_events,
            self.fetch_social_events,
            self.fetch_nft_events,
            self.fetch_bridge_events,
        ]
        for func in fetchers:
            try:
                events.extend(func())
            except Exception as exc:  # pragma: no cover - network
                self._alert("poll_fail", exc)
        if not events:
            LOGGER.log("no_events", risk_level="low")
        set_value("market_events", [e.__dict__ for e in events])
        for e in events:
            LOGGER.log(
                "market_event",
                event_type=e.event_type,
                source=e.source,
                risk_level="low",
            )
            metrics.record_mutation_event()
            for sub in list(self.subscribers):
                try:
                    sub(e)
                except Exception as exc:  # pragma: no cover - runtime
                    LOGGER.log("callback_fail", risk_level="high", error=str(exc))
        return events


if __name__ == "__main__":  # pragma: no cover - manual run
    adapter = MarketEventFeedAdapter(
        dex_urls=[os.getenv("DEX_FEED_URL", "http://dex")],
        cex_urls=[os.getenv("CEX_FEED_URL", "http://cex")],
    )
    adapter.poll()
