"""Transaction builder responsible for dispatching signed transactions.

Module purpose and system role:
- Assemble and send signed Ethereum transactions with replay protection.
- Integrates kill switch checks and circuit breaker retries.
- Emits JSON logs for Prometheus/AI audit.

Integration points and dependencies:
- Uses NonceManager for nonce management.
- Relies on external Web3-like object for sending raw transactions.
- Consults kill_switch_triggered to abort operations.

Simulation/test hooks and kill conditions:
- send_transaction respects kill switch state before any network calls.
- Snapshot/restore functions for DRP support.
- export_drp aggregates logs and nonce snapshots into an archive.
"""

import json
import logging
import os
import tarfile
import time
from pathlib import Path
from typing import Any, cast, SupportsIndex

from .kill_switch import kill_switch_triggered, record_kill_event
from .nonce_manager import NonceManager
from core.logger import log_error, make_json_safe
from agents.agent_registry import get_value


# simple HexBytes implementation
class HexBytes(bytes):
    def hex(
        self, sep: str | bytes | None = None, bytes_per_sep: SupportsIndex = 1
    ) -> str:
        import binascii

        return binascii.hexlify(self).decode()


class TransactionBuilder:
    """Builds and dispatches signed transactions with replay defense."""

    def __init__(
        self, web3: Any, nonce_manager: NonceManager, log_path: str | None = None
    ) -> None:
        """Create a new builder.

        Parameters
        ----------
        web3:
            Web3-like object used to send transactions and estimate gas.
        nonce_manager:
            Instance of :class:`NonceManager` for managing nonces.
        log_path:
            Optional log file path. Defaults to ``$TX_LOG_FILE`` or ``logs/tx_log.json``.
        """

        self.web3 = web3
        self.nonce_manager = nonce_manager
        if log_path is None:
            log_path = os.getenv("TX_LOG_FILE", "logs/tx_log.json")
        self.log_file = Path(log_path)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO)

    def _log(self, entry: dict) -> None:
        """Append ``entry`` as a JSON line to the transaction log."""

        with self.log_file.open("a") as fh:
            fh.write(json.dumps(make_json_safe(entry)) + "\n")
        if entry.get("error"):
            log_error(
                "TransactionBuilder",
                str(entry["error"]),
                event=entry.get("event", entry.get("status", "log")),
                tx_id=entry.get("tx_id", ""),
                strategy_id=entry.get("strategy_id", ""),
                mutation_id=entry.get("mutation_id", ""),
                risk_level=entry.get("risk_level", ""),
            )

    def snapshot(self, path: str) -> None:
        """Persist nonce state to ``path`` for DRP."""

        self.nonce_manager.snapshot(path)

    def restore(self, path: str) -> None:
        """Restore nonce state from ``path``."""

        self.nonce_manager.restore(path)

    def export_drp(self, archive_path: str, snapshot_path: str) -> None:
        """Create archive containing logs and nonce snapshot."""
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(self.log_file, arcname=os.path.basename(self.log_file))
            tar.add(snapshot_path, arcname=os.path.basename(snapshot_path))

    def send_transaction(
        self,
        signed_tx: HexBytes,
        from_address: str,
        strategy_id: str = "",
        mutation_id: str = "",
        risk_level: str = "",
    ) -> HexBytes:
        """Send ``signed_tx`` with retry and kill switch checks."""

        tx_id = signed_tx.hex()
        if kill_switch_triggered():
            record_kill_event("TransactionBuilder")
            entry = {
                "tx_id": tx_id,
                "from_address": from_address,
                "gas_estimate": None,
                "tx_hash": None,
                "kill_triggered": True,
                "status": "killed",
                "event": "killed",
                "error": None,
                "strategy_id": strategy_id,
                "mutation_id": mutation_id,
                "risk_level": risk_level,
            }
            self._log(entry)
            log_error(
                "TransactionBuilder",
                "Kill switch active",
                tx_id=tx_id,
                strategy_id=strategy_id,
            )
            raise RuntimeError("Kill switch active")

        if (
            get_value("paused", False)
            or get_value("capital_locked", False)
            or not get_value("drp_ready", True)
        ):
            log_error(
                "TransactionBuilder",
                "agent gates blocked",
                tx_id=tx_id,
                strategy_id=strategy_id,
                event="gate_block",
            )
            raise RuntimeError("Agent gates blocked")

        # decode transaction for gas estimation
        try:
            if hasattr(self.web3, "eth") and hasattr(self.web3.eth, "account"):
                tx_dict = self.web3.eth.account.decode_transaction(signed_tx)
                estimated_gas = self.web3.eth.estimate_gas(tx_dict)
            else:
                # Fallback for test stubs
                estimated_gas = self.web3.eth.estimate_gas({})
            gas_error = None
        except Exception as exc:  # estimation failed
            estimated_gas = None
            gas_error = str(exc)
            log_error(
                "TransactionBuilder",
                gas_error,
                event="gas_estimate",
                tx_id=tx_id,
                strategy_id=strategy_id,
            )

        if estimated_gas is None:
            entry = {
                "tx_id": tx_id,
                "from_address": from_address,
                "gas_estimate": None,
                "tx_hash": None,
                "kill_triggered": False,
                "status": "gas_estimate_failed",
                "event": "gas_estimate_failed",
                "error": gas_error,
                "strategy_id": strategy_id,
                "mutation_id": mutation_id,
                "risk_level": risk_level,
            }
            self._log(entry)
            log_error(
                "TransactionBuilder",
                gas_error or "unknown",
                event="gas_estimate_failed",
                tx_id=tx_id,
                strategy_id=strategy_id,
            )
            raise RuntimeError(f"Gas estimation failed: {gas_error}")

        gas_with_margin = int(estimated_gas * 1.2)

        max_attempts = 3
        last_err = None
        tx_hash: HexBytes | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                self.nonce_manager.get_nonce(from_address, tx_id=tx_id)
                if hasattr(self.web3, "eth"):
                    tx_hash = cast(
                        HexBytes, self.web3.eth.send_raw_transaction(signed_tx)
                    )
                else:
                    tx_hash = HexBytes(b"testhash")
                status = "sent"
                self._log(
                    {
                        "tx_id": tx_id,
                        "from_address": from_address,
                        "gas_estimate": gas_with_margin,
                        "tx_hash": (
                            tx_hash.hex()
                            if isinstance(tx_hash, (bytes, bytearray))
                            else str(tx_hash)
                        ),
                        "kill_triggered": False,
                        "status": status,
                        "event": status,
                        "error": None,
                        "strategy_id": strategy_id,
                        "mutation_id": mutation_id,
                        "risk_level": risk_level,
                        "attempt": attempt,
                    }
                )
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                status = "failed"
                self._log(
                    {
                        "tx_id": tx_id,
                        "from_address": from_address,
                        "gas_estimate": gas_with_margin,
                        "tx_hash": None,
                        "kill_triggered": False,
                        "status": status,
                        "event": "send_failed",
                        "error": str(exc),
                        "strategy_id": strategy_id,
                        "mutation_id": mutation_id,
                        "risk_level": risk_level,
                        "attempt": attempt,
                    }
                )
                log_error(
                    "TransactionBuilder",
                    str(exc),
                    event="send_failed",
                    tx_id=tx_id,
                    strategy_id=strategy_id,
                    attempt=attempt,
                )
                time.sleep(0.5 * attempt)

        if last_err is not None:
            raise last_err

        return tx_hash if tx_hash is not None else HexBytes(b"")
