"""Intent feed for L3/app-rollup transactions.

This module fetches open intents from a configurable HTTP endpoint. The
endpoint is expected to return JSON lists of intents with minimal fields. The
feed is used in tests with mocked responses and can be pointed at a live
service in production.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import List

from core.logger import log_error

try:  # pragma: no cover - optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover - allow missing dependency
    requests = None  # type: ignore


@dataclass
class IntentData:
    intent_id: str
    domain: str
    action: str
    price: float


class IntentFeed:
    """Fetch intent data from ``INTENT_FEED_URL``."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.getenv("INTENT_FEED_URL", "http://localhost:9000")

    def fetch_intents(self, domain: str) -> List[IntentData]:
        if requests is None:
            raise RuntimeError("requests package required")
        url = f"{self.base_url}/{domain}/intents"
        try:  # pragma: no cover - network
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # pragma: no cover - network
            log_error("IntentFeed", str(exc), event="fetch_intents", domain=domain)
            raise
        intents = []
        for item in data:
            try:
                intents.append(IntentData(**item))
            except Exception as exc:
                log_error("IntentFeed", f"bad intent: {exc}", event="parse", domain=domain)
        return intents
