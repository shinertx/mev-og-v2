"""DEX aggregator adapter (1inch/CowSwap style)."""

from __future__ import annotations

from typing import Any, Dict

from core.logger import StructuredLogger

LOGGER = StructuredLogger("dex_adapter")


class DEXAdapter:
    """Interact with a DEX aggregator to fetch quotes and execute trades."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    # ------------------------------------------------------------------
    def get_quote(self, sell_token: str, buy_token: str, amount: float) -> Dict[str, Any]:
        params = {"sellToken": sell_token, "buyToken": buy_token, "amount": amount}
        try:
            import requests  # type: ignore

            resp = requests.get(f"{self.api_url}/quote", params=params, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            LOGGER.log("quote_fail", risk_level="high", error=str(exc))
            raise

    # ------------------------------------------------------------------
    def execute_trade(self, tx_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import requests  # type: ignore

            resp = requests.post(f"{self.api_url}/swap", json=tx_data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            LOGGER.log("trade_fail", risk_level="high", error=str(exc))
            raise

