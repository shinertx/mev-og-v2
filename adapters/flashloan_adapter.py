"""Flashloan execution adapter."""

from __future__ import annotations

from typing import Any, Dict

from core.logger import StructuredLogger

LOG = StructuredLogger("flashloan_adapter")


class FlashloanAdapter:
    """Execute flashloans to induce price moves for latency farming."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def trigger(self, token: str, amount: float) -> Dict[str, Any]:
        """Perform the flashloan using an external service."""
        try:
            import requests  # type: ignore

            resp = requests.post(
                f"{self.api_url}/flashloan",
                json={"token": token, "amount": amount},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            LOG.log("flashloan_fail", risk_level="high", error=str(exc))
            raise
