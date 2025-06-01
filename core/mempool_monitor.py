"""Lightweight Ethereum mempool monitor for bridge transactions."""

from __future__ import annotations

from typing import Any, Dict, List, cast

from agents.ops_agent import OpsAgent
try:
    from hexbytes import HexBytes
except Exception:  # pragma: no cover - optional
    HexBytes = bytes  # type: ignore

from core.logger import StructuredLogger

try:
    from web3 import Web3 as Web3Type
    Web3: Any = Web3Type
except Exception:  # pragma: no cover - optional
    Web3 = cast(Any, None)

LOG = StructuredLogger("mempool_monitor")


class MempoolMonitor:
    """Monitor pending transactions for bridge activity."""

    def __init__(
        self, web3: Web3 | None, *, ops_agent: OpsAgent | None = None, fail_threshold: int = 3
    ) -> None:
        self.web3 = web3
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOG.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"mempool_monitor:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    def listen_bridge_txs(
        self, limit: int = 10, *, simulate_failure: str | None = None
    ) -> List[Dict[str, object]]:
        """Return a list of pending bridge transactions up to ``limit``."""
        if self.web3 is None:
            return []
        results: List[Dict[str, object]] = []
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return [{"bad": True}]
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

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
            self._alert("mempool_fail", exc)
            return []
        return results
