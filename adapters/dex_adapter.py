"""DEX aggregator adapter (1inch/CowSwap style)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger

LOGGER = StructuredLogger("dex_adapter")


class DEXAdapter:
    """Interact with a DEX aggregator to fetch quotes and execute trades."""

    def __init__(
        self,
        api_url: str,
        *,
        alt_api_url: str | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.alt_api_url = alt_api_url.rstrip("/") if alt_api_url else None
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
        params = {"sellToken": sell_token, "buyToken": buy_token, "amount": amount}
        try:
            import requests  # type: ignore

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
            if self.alt_api_url:
                try:
                    resp = requests.get(
                        f"{self.alt_api_url}/quote", params=params, timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low")
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            raise

    # ------------------------------------------------------------------
    def execute_trade(
        self,
        tx_data: Dict[str, Any],
        *,
        simulate_failure: str | None = None,
    ) -> Dict[str, Any]:
        try:
            import requests  # type: ignore

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
            if self.alt_api_url:
                try:
                    resp = requests.post(
                        f"{self.alt_api_url}/swap", json=tx_data, timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low")
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            raise

