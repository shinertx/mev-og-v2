"""External alpha signal adapters."""

from __future__ import annotations

import json
import threading
import time
from typing import Dict

from core.logger import StructuredLogger
from core.rate_limiter import RateLimiter
from core.strategy_scoreboard import SignalProvider


class DuneAnalyticsAdapter(SignalProvider):
    """Fetch query results from Dune Analytics."""

    def __init__(self, api_url: str, api_key: str, query_id: str, rate: float = 1.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.query_id = query_id
        self.rate = RateLimiter(rate)
        self.logger = StructuredLogger("dune_adapter")

    def fetch(self) -> Dict[str, float]:
        self.rate.wait()
        try:
            import requests  # type: ignore

            resp = requests.get(
                f"{self.api_url}/v1/query/{self.query_id}/results",
                headers={"X-Dune-API-Key": self.api_key},
                timeout=5,
            )
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", "1"))
                time.sleep(retry)
                return {}
            resp.raise_for_status()
            data = resp.json().get("result", {})
            return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.log("dune_fail", risk_level="medium", error=str(exc))
            return {}


class WhaleAlertAdapter(SignalProvider):
    """Realtime whale transaction alerts."""

    def __init__(self, api_url: str, api_key: str, rate: float = 0.5) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.rate = RateLimiter(rate)
        self.logger = StructuredLogger("whale_alert")

    def fetch(self) -> Dict[str, float]:
        self.rate.wait()
        try:
            import requests  # type: ignore

            resp = requests.get(
                f"{self.api_url}/transactions", params={"api_key": self.api_key}, timeout=5
            )
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", "1"))
                time.sleep(retry)
                return {}
            resp.raise_for_status()
            data = resp.json().get("transactions", [])
            score = float(len(data))
            return {"whale_flow": score}
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.log("whale_fail", risk_level="medium", error=str(exc))
            return {}


class CoinbaseWebSocketAdapter(SignalProvider):
    """Live Coinbase futures orderbook feed."""

    def __init__(self, ws_url: str, product: str = "BTC-USD") -> None:
        self.ws_url = ws_url
        self.product = product
        self.logger = StructuredLogger("coinbase_ws")
        self.latest: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import websocket  # type: ignore
        except Exception as exc:  # pragma: no cover - missing dep
            self.logger.log("ws_import_fail", risk_level="high", error=str(exc))
            return
        while not self._stop:
            try:
                ws = websocket.create_connection(self.ws_url, timeout=5)
                sub = json.dumps({"type": "subscribe", "product_ids": [self.product], "channels": ["ticker"]})
                ws.send(sub)
                ws.settimeout(5)
                while not self._stop:
                    msg = ws.recv()
                    data = json.loads(msg)
                    if data.get("type") == "ticker":
                        with self._lock:
                            self.latest["coinbase_price"] = float(data.get("price", 0.0))
            except Exception as exc:  # pragma: no cover - network errors
                self.logger.log("ws_error", risk_level="low", error=str(exc))
                time.sleep(1)
            finally:
                try:
                    ws.close()
                except Exception:
                    pass

    def fetch(self) -> Dict[str, float]:
        with self._lock:
            return dict(self.latest)

    def stop(self) -> None:
        self._stop = True
