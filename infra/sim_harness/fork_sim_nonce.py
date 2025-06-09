"""Forked mainnet simulation validating nonce drift recovery."""

import os


from core.tx_engine.nonce_manager import NonceManager
from infra.sim_harness import start_metrics
from core import metrics

try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
except ImportError:  # pragma: no cover - requires web3
    raise SystemExit("web3 is required for fork simulation")

FORK_BLOCK = 19338888
RPC_URL = os.environ.get("MAINNET_RPC", "http://localhost:8545")


def main() -> None:
    start_metrics()
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    w3.middleware_onion.add(geth_poa_middleware)
    nonce_manager = NonceManager(w3)

    addr = w3.eth.accounts[0]
    first = nonce_manager.get_nonce(addr)
    print("On-chain nonce:", first)

    # simulate drift
    nonce_manager.update_nonce(addr, first + 5)
    drifted = nonce_manager.get_nonce(addr)
    print("Drifted nonce:", drifted)

    nonce_manager.reset_nonce(addr)
    synced = nonce_manager.get_nonce(addr)
    print("Synced nonce:", synced)
    metrics.record_opportunity(0.0, 0.0, 0.0)


if __name__ == "__main__":
    main()
