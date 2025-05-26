import json
import threading
from typing import Dict

class NonceManager:
    """Manage nonces per address to prevent replay attacks."""

    def __init__(self, web3=None):
        self.web3 = web3
        self._nonce_lock = threading.Lock()
        self._nonces: Dict[str, int] = {}

    def get_next_nonce(self, address: str) -> int:
        with self._nonce_lock:
            if address not in self._nonces:
                if self.web3 is None:
                    current = 0
                else:
                    current = self.web3.eth.get_transaction_count(address)
                self._nonces[address] = current
            nonce = self._nonces[address]
            self._nonces[address] += 1
            return nonce

    def set_nonce(self, address: str, nonce: int) -> None:
        with self._nonce_lock:
            self._nonces[address] = nonce

    def snapshot(self, path: str) -> None:
        with self._nonce_lock, open(path, 'w') as fh:
            json.dump(self._nonces, fh)

    def restore(self, path: str) -> None:
        with open(path, 'r') as fh:
            data = json.load(fh)
        with self._nonce_lock:
            self._nonces = {k: int(v) for k, v in data.items()}
