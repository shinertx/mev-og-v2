"""Token bridge API adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger

LOGGER = StructuredLogger("bridge_adapter")


class BridgeAdapter:
    """Handle token bridging via a third-party API."""

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
            self.ops_agent.notify(f"bridge_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    # ------------------------------------------------------------------
    def bridge(
        self, from_chain: str, to_chain: str, token: str, amount: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        data = {"from": from_chain, "to": to_chain, "token": token, "amount": amount}
        try:
            import requests  # type: ignore

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"bridge": "bad"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.post(f"{self.api_url}/bridge", json=data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("bridge_fail", exc)
            if self.alt_api_url:
                try:
                    resp = requests.post(
                        f"{self.alt_api_url}/bridge", json=data, timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low")
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            raise


