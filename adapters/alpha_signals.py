"""External alpha signal adapters."""

from __future__ import annotations

import json
import threading
import time
import os
import random
from typing import Dict, List

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger
from ai.mutation_log import log_mutation
from core.rate_limiter import RateLimiter
from core.strategy_scoreboard import SignalProvider


class DuneAnalyticsAdapter(SignalProvider):
    """Fetch query results from Dune Analytics."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        query_id: str,
        rate: float = 1.0,
        *,
        alt_api_url: str | None = None,
        alt_api_urls: List[str] | None = None,
        alt_api_urls: List[str] | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        alts = []
        if alt_api_urls:
            alts.extend(alt_api_urls)
        if alt_api_url:
            alts.append(alt_api_url)
        self.alt_api_urls = [a.rstrip("/") for a in alts]
        self.api_key = api_key
        self.query_id = query_id
        self.rate = RateLimiter(rate)
        self.logger = StructuredLogger("dune_adapter")
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        self.logger.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"dune_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    def fetch(self, *, simulate_failure: str | None = None) -> Dict[str, float]:
        self.rate.wait()
        try:
            import requests  # type: ignore

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"bad": float("nan")}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 429")

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
            self._alert("dune_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    self.logger.log("fallback_try", risk_level="low", alt=alt)
                    resp = requests.get(
                        f"{alt}/v1/query/{self.query_id}/results",
                        headers={"X-Dune-API-Key": self.api_key},
                        timeout=5,
                    )
                    resp.raise_for_status()
                    self.logger.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    data = resp.json().get("result", {})
                    log_mutation(
                        "adapter_chaos",
                        adapter="dune_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="dune_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            return {}


class WhaleAlertAdapter(SignalProvider):
    """Realtime whale transaction alerts."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        rate: float = 0.5,
        *,
        alt_api_url: str | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        alts = []
        if alt_api_urls:
            alts.extend(alt_api_urls)
        if alt_api_url:
            alts.append(alt_api_url)
        self.alt_api_urls = [a.rstrip("/") for a in alts]
        self.api_key = api_key
        self.rate = RateLimiter(rate)
        self.logger = StructuredLogger("whale_alert")
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        self.logger.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"whale_alert:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    def fetch(self, *, simulate_failure: str | None = None) -> Dict[str, float]:
        self.rate.wait()
        try:
            import requests  # type: ignore

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"whale_flow": float("nan")}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 429")

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
            self._alert("whale_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    self.logger.log("fallback_try", risk_level="low", alt=alt)
                    resp = requests.get(
                        f"{alt}/transactions",
                        params={"api_key": self.api_key},
                        timeout=5,
                    )
                    resp.raise_for_status()
                    self.logger.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    data = resp.json().get("transactions", [])
                    score = float(len(data))
                    log_mutation(
                        "adapter_chaos",
                        adapter="whale_alert",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return {"whale_flow": score}
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="whale_alert",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            return {}


class CoinbaseWebSocketAdapter(SignalProvider):
    """Live Coinbase futures orderbook feed."""

    def __init__(
        self,
        ws_url: str,
        product: str = "BTC-USD",
        *,
        alt_ws_url: str | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.ws_url = ws_url
        self.alt_ws_url = alt_ws_url
        self.product = product
        self.logger = StructuredLogger("coinbase_ws")
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0
        self.latest: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        self.logger.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"coinbase_ws:{event}:{err}")
        if self.failures >= self.fail_threshold:
            self._stop = True
            raise RuntimeError("circuit breaker open")

    def _run(self) -> None:
        try:
            import websocket  # type: ignore
        except Exception as exc:  # pragma: no cover - missing dep
            self._alert("ws_import_fail", exc)
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
                self._alert("ws_error", exc)
                if self.alt_ws_url:
                    self.ws_url = self.alt_ws_url
                    self.alt_ws_url = None
                    self.failures = 0
                    self.logger.log("fallback_success", risk_level="low")
                time.sleep(1)
            finally:
                try:
                    ws.close()
                except Exception:
                    pass

    def fetch(self, *, simulate_failure: str | None = None) -> Dict[str, float]:
        if simulate_failure == "data_poison":
            return {"coinbase_price": float("nan")}
        with self._lock:
            return dict(self.latest)

    def stop(self) -> None:
        self._stop = True
