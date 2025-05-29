"""Nonce manager with JSON-backed cache and audit logging.

Module purpose and system role:
- Maintain per-address nonces to guard against replay attacks.
- Syncs with on-chain nonce when cache is missing or reset.
- Emits structured logs for AI mutation/audit.

Integration points and dependencies:
- Expects a Web3-like object for RPC calls.
 - Writes cache to ``state/nonce_cache.json`` and logs to ``logs/nonce_log.json``.

Simulation/test hooks and kill conditions:
- Designed for forked-mainnet simulation to validate nonce drift handling.
- Snapshot and restore functions support DRP state export.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Dict, Optional, Any

from core.logger import log_error, make_json_safe


class NonceManager:
    """Thread-safe nonce manager with disk-backed cache and JSON logging."""

    def __init__(
        self,
        web3: Optional[Any] = None,
        cache_file: str | None = None,
        log_file: str | None = None,
    ) -> None:
        self.web3 = web3
        if cache_file is None:
            cache_file = os.getenv("NONCE_CACHE_FILE", "state/nonce_cache.json")
        if log_file is None:
            log_file = os.getenv("NONCE_LOG_FILE", "logs/nonce_log.json")

        self.cache_path = Path(cache_file)
        self.log_path = Path(log_file)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._nonce_lock = threading.RLock()
        self._nonces: Dict[str, int] = {}
        self._load_cache()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_cache(self) -> None:
        """Load nonce cache from disk."""

        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text())
                self._nonces = {k: int(v) for k, v in data.items()}
            except Exception as exc:
                self._nonces = {}
                log_error("NonceManager", f"load_cache failed: {exc}")
        else:
            self.cache_path.write_text("{}")

    def _save_cache(self) -> None:
        """Persist nonce cache to disk."""
        try:
            with self.cache_path.open("w") as fh:
                json.dump(self._nonces, fh)
        except Exception as exc:
            log_error("NonceManager", f"save_cache failed: {exc}")

    def _fetch_onchain_nonce(self, address: str) -> int:
        """Fetch the current on-chain nonce for ``address``."""
        if self.web3 is None or not hasattr(self.web3, "eth"):
            return 0
        try:
            return int(self.web3.eth.get_transaction_count(address))
        except Exception as exc:  # pragma: no cover - RPC failure
            log_error("NonceManager", f"rpc nonce fetch failed: {exc}")
            return 0

    def _log(
        self,
        source: str,
        address: str,
        on_chain_nonce: Optional[int],
        local_nonce: Optional[int],
        tx_id: str = "",
    ) -> None:
        """Write a structured nonce event to the log."""

        entry = {
            "tx_id": tx_id,
            "address": address,
            "on_chain_nonce": on_chain_nonce,
            "local_nonce": local_nonce,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
        }
        with self.log_path.open("a") as fh:
            fh.write(json.dumps(make_json_safe(entry)) + "\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_nonce(self, address: str, tx_id: str = "") -> int:
        """Return next nonce for ``address`` using local cache when available."""
        with self._nonce_lock:
            if address in self._nonces:
                local_nonce = self._nonces[address] + 1
                on_chain = None
            else:
                on_chain = self._fetch_onchain_nonce(address)
                local_nonce = on_chain
            self._nonces[address] = local_nonce
            self._save_cache()
            self._log("get", address, on_chain, local_nonce, tx_id)
            return local_nonce

    # Backwards compatibility
    get_next_nonce = get_nonce

    def update_nonce(self, address: str, nonce: int, tx_id: str = "") -> None:
        """Manually set ``nonce`` for ``address`` and persist to cache."""
        with self._nonce_lock:
            self._nonces[address] = int(nonce)
            self._save_cache()
            on_chain = self._fetch_onchain_nonce(address)
            self._log("update", address, on_chain, int(nonce), tx_id)

    def reset_nonce(self, address: str, tx_id: str = "") -> None:
        """Remove cached nonce for ``address`` to resync with chain."""
        with self._nonce_lock:
            self._nonces.pop(address, None)
            self._save_cache()
            on_chain = self._fetch_onchain_nonce(address)
            self._log("reset", address, on_chain, None, tx_id)

    def snapshot(self, path: str) -> None:
        """Write nonce snapshot to ``path``."""

        with self._nonce_lock, open(path, "w") as fh:
            json.dump(self._nonces, fh)

    def restore(self, path: str) -> None:
        """Restore nonce snapshot from ``path``."""

        with open(path, "r") as fh:
            data = json.load(fh)
        with self._nonce_lock:
            self._nonces = {k: int(v) for k, v in data.items()}
            self._save_cache()


# ---------------------------------------------------------------------------
# Shared instance utilities
# ---------------------------------------------------------------------------
_shared_nonce_manager: Optional[NonceManager] = None
_shared_lock = threading.Lock()


def get_shared_nonce_manager(web3: Optional[Any] = None) -> NonceManager:
    """Return module-wide singleton ``NonceManager``."""

    global _shared_nonce_manager
    with _shared_lock:
        if _shared_nonce_manager is None:
            _shared_nonce_manager = NonceManager(web3)
        elif web3 is not None and _shared_nonce_manager.web3 is None:
            _shared_nonce_manager.web3 = web3
        return _shared_nonce_manager
