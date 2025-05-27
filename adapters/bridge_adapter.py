"""Token bridge API adapter."""

from __future__ import annotations

from typing import Any, Dict

from core.logger import StructuredLogger

LOGGER = StructuredLogger("bridge_adapter")


class BridgeAdapter:
    """Handle token bridging via a third-party API."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    # ------------------------------------------------------------------
    def bridge(self, from_chain: str, to_chain: str, token: str, amount: float) -> Dict[str, Any]:
        data = {"from": from_chain, "to": to_chain, "token": token, "amount": amount}
        try:
            import requests  # type: ignore

            resp = requests.post(f"{self.api_url}/bridge", json=data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            LOGGER.log("bridge_fail", risk_level="high", error=str(exc))
            raise


