"""Simple CEX adapter supporting order placement and balance check."""

from __future__ import annotations

from typing import Any, Dict

from core.logger import StructuredLogger

LOGGER = StructuredLogger("cex_adapter")


class CEXAdapter:
    """HTTP-based adapter for a centralized exchange."""

    def __init__(self, api_url: str, api_key: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # ------------------------------------------------------------------
    def get_balance(self) -> Dict[str, Any]:
        try:
            import requests  # type: ignore

            resp = requests.get(f"{self.api_url}/balance", headers=self._headers(), timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            LOGGER.log("balance_fail", risk_level="high", error=str(exc))
            raise

    # ------------------------------------------------------------------
    def place_order(self, side: str, size: float, price: float) -> Dict[str, Any]:
        data = {"side": side, "size": size, "price": price}
        try:
            import requests  # type: ignore

            resp = requests.post(f"{self.api_url}/order", json=data, headers=self._headers(), timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            LOGGER.log("order_fail", risk_level="high", error=str(exc))
            raise

