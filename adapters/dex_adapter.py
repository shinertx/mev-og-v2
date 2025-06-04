"""DEX aggregator adapter (1inch/CowSwap style)."""

from __future__ import annotations

import os
import random
from typing import Any, Dict, List
import math

import requests


from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger

try:  # optional kill switch; tests may stub out core
    from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
except Exception:  # pragma: no cover - optional dependency
    kill_switch_triggered = None  # type: ignore[assignment]
    record_kill_event = None  # type: ignore[assignment]
from ai.mutation_log import log_mutation

LOGGER = StructuredLogger("dex_adapter")


class DEXAdapter:
    """Interact with a DEX aggregator to fetch quotes and execute trades."""

    def __init__(
        self,
        api_url: str,
        *,
        alt_api_url: str | None = None,
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
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0
        self.session = requests.Session()

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOGGER.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"dex_adapter:{event}:{err}")

    # ------------------------------------------------------------------
    def _validate_quote(self, data: Dict[str, Any]) -> Dict[str, Any]:
        price = data.get("price")
        if price is not None:
            try:
                val = float(price)
            except Exception as exc:
                raise ValueError("invalid price") from exc
            if not math.isfinite(val):
                raise ValueError("invalid price")
            return {"price": val}
        if "ok" in data:
            if isinstance(data.get("ok"), bool):
                return {"ok": data["ok"]}
        raise ValueError("missing price")

    def _validate_trade(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "tx" in data:
            if isinstance(data["tx"], str):
                return {"tx": data["tx"]}
            raise ValueError("invalid tx")
        if "ok" in data:
            if isinstance(data["ok"], bool):
                return {"ok": data["ok"]}
        raise ValueError("missing tx")

    # ------------------------------------------------------------------
    def get_quote(
        self,
        sell_token: str,
        buy_token: str,
        amount: float,
        *,
        simulate_failure: str | None = None,
    ) -> Dict[str, Any]:
        if kill_switch_triggered and kill_switch_triggered():
            if record_kill_event:
                record_kill_event("dex_adapter.get_quote")
            raise RuntimeError("Kill switch active")
        params = {"sellToken": sell_token, "buyToken": buy_token, "amount": amount}
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim network")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc fail")
            if simulate_failure == "data_poison":
                data: Dict[str, Any] = {"price": "NaN"}
                self._validate_quote(data)
                return data
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = self.session.get(f"{self.api_url}/quote", params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return self._validate_quote(data)
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("quote_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = self.session.get(f"{alt}/quote", params=params, timeout=5)
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="dex_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    data = resp.json()
                    return self._validate_quote(data)
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            if self.failures >= self.fail_threshold:
                os.environ["OPS_CRITICAL_EVENT"] = "1"
                log_mutation(
                    "adapter_chaos",
                    adapter="dex_adapter",
                    failure=simulate_failure or "runtime",
                    fallback="fail",
                )
                raise RuntimeError("circuit breaker open")
            return {}

    # ------------------------------------------------------------------
    def execute_trade(
        self,
        tx_data: Dict[str, Any],
        *,
        simulate_failure: str | None = None,
    ) -> Dict[str, Any]:
        if kill_switch_triggered and kill_switch_triggered():
            if record_kill_event:
                record_kill_event("dex_adapter.execute_trade")
            raise RuntimeError("Kill switch active")
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim network")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc fail")
            if simulate_failure == "data_poison":
                data: Dict[str, Any] = {"tx": "invalid"}
                self._validate_trade(data)
                return data
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = self.session.post(f"{self.api_url}/swap", json=tx_data, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return self._validate_trade(data)
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("trade_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = self.session.post(f"{alt}/swap", json=tx_data, timeout=5)
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="dex_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    data = resp.json()
                    return self._validate_trade(data)
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            if self.failures >= self.fail_threshold:
                os.environ["OPS_CRITICAL_EVENT"] = "1"
                log_mutation(
                    "adapter_chaos",
                    adapter="dex_adapter",
                    failure=simulate_failure or "runtime",
                    fallback="fail",
                )
                raise RuntimeError("circuit breaker open")
            return {}

