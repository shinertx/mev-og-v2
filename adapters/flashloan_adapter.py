"""Flashloan execution adapter."""

from __future__ import annotations

from typing import Any, Dict

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger

LOG = StructuredLogger("flashloan_adapter")


class FlashloanAdapter:
    """Execute flashloans to induce price moves for latency farming."""

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
        LOG.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"flashloan_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    def trigger(
        self, token: str, amount: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        """Perform the flashloan using an external service."""
        try:
            import requests  # type: ignore

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"flashloan": "bad"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.post(
                f"{self.api_url}/flashloan",
                json={"token": token, "amount": amount},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("flashloan_fail", exc)
            if self.alt_api_url:
                try:
                    resp = requests.post(
                        f"{self.alt_api_url}/flashloan",
                        json={"token": token, "amount": amount},
                        timeout=5,
                    )
                    resp.raise_for_status()
                    LOG.log("fallback_success", risk_level="low")
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            raise
