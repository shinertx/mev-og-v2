"""DEX aggregator adapter (1inch/CowSwap style)."""

from __future__ import annotations

import os
import random
from typing import Any, Dict, List

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
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

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOGGER.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"dex_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    # ------------------------------------------------------------------
    def get_quote(
        self,
        sell_token: str,
        buy_token: str,
        amount: float,
        *,
        simulate_failure: str | None = None,
    ) -> Dict[str, Any]:
        if kill_switch_triggered():
            record_kill_event("dex_adapter.get_quote")
            raise RuntimeError("Kill switch active")
        params = {"sellToken": sell_token, "buyToken": buy_token, "amount": amount}
        try:
            import requests  # type: ignore[import-untyped]

            if simulate_failure == "network":
                raise RuntimeError("sim network")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc fail")
            if simulate_failure == "data_poison":
                return {"price": "NaN"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.get(f"{self.api_url}/quote", params=params, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("quote_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = requests.get(f"{alt}/quote", params=params, timeout=5)
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="dex_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="dex_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            raise

    # ------------------------------------------------------------------
    def execute_trade(
        self,
        tx_data: Dict[str, Any],
        *,
        simulate_failure: str | None = None,
    ) -> Dict[str, Any]:
        if kill_switch_triggered():
            record_kill_event("dex_adapter.execute_trade")
            raise RuntimeError("Kill switch active")
        try:
            import requests  # type: ignore[import-untyped]

            if simulate_failure == "network":
                raise RuntimeError("sim network")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc fail")
            if simulate_failure == "data_poison":
                return {"tx": "invalid"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.post(f"{self.api_url}/swap", json=tx_data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("trade_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = requests.post(f"{alt}/swap", json=tx_data, timeout=5)
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="dex_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="dex_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            raise

