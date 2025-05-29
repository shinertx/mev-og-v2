"""Simple CEX adapter supporting order placement and balance check."""

from __future__ import annotations

from typing import Any, Dict

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger

LOGGER = StructuredLogger("cex_adapter")


class CEXAdapter:
    """HTTP-based adapter for a centralized exchange."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        alt_api_url: str | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.alt_api_url = alt_api_url.rstrip("/") if alt_api_url else None
        self.api_key = api_key
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOGGER.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"cex_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # ------------------------------------------------------------------
    def get_balance(self, *, simulate_failure: str | None = None) -> Dict[str, Any]:
        try:
            import requests  # type: ignore

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"balance": "bad"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 429")

            resp = requests.get(f"{self.api_url}/balance", headers=self._headers(), timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("balance_fail", exc)
            if self.alt_api_url:
                try:
                    resp = requests.get(
                        f"{self.alt_api_url}/balance", headers=self._headers(), timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low")
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            raise

    # ------------------------------------------------------------------
    def place_order(
        self, side: str, size: float, price: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        data = {"side": side, "size": size, "price": price}
        try:
            import requests  # type: ignore

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"order": "bad"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.post(f"{self.api_url}/order", json=data, headers=self._headers(), timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("order_fail", exc)
            if self.alt_api_url:
                try:
                    resp = requests.post(
                        f"{self.alt_api_url}/order", json=data, headers=self._headers(), timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low")
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            raise

