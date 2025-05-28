"""Lightweight Ethereum mempool monitor for bridge transactions."""

from __future__ import annotations

from typing import Dict, List, cast
from hexbytes import HexBytes

from core.logger import StructuredLogger

try:
    from web3 import Web3  # type: ignore
except Exception:  # pragma: no cover - optional
    Web3 = None  # type: ignore

LOG = StructuredLogger("mempool_monitor")


class MempoolMonitor:
    """Monitor pending transactions for bridge activity."""

    def __init__(self, web3: Web3 | None) -> None:
        self.web3 = web3

    def listen_bridge_txs(self, limit: int = 10) -> List[Dict[str, object]]:
        """Return a list of pending bridge transactions up to ``limit``."""
        if self.web3 is None:
            return []
        results: List[Dict[str, object]] = []
        try:
            filt = self.web3.eth.filter("pending")
            count = 0
            while count < limit:
                hashes = filt.get_new_entries()
                for h in hashes:
                    tx = self.web3.eth.get_transaction(HexBytes(cast(bytes, h)))
                    if tx and tx.get("to"):
                        results.append(dict(tx))
                        count += 1
                        if count >= limit:
                            break
        except Exception as exc:  # pragma: no cover - network errors
            LOG.log("mempool_fail", risk_level="high", error=str(exc))
            return []
        return results
