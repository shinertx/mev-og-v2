"""Run transaction builder against historical mainnet state.

This script forks Ethereum mainnet at block 19338888 and replays a historical
transaction using TransactionBuilder. Requires web3 and a forking provider
(such as Hardhat or Ganache) available locally.
"""

import os

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager

try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - only executed when web3 is installed
    raise SystemExit("web3 is required for fork simulation")


FORK_BLOCK = 19338888
RPC_URL = os.environ.get("MAINNET_RPC", "http://localhost:8545")


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    w3.middleware_onion.add(geth_poa_middleware)
    nonce_manager = NonceManager(w3)
    builder = TransactionBuilder(w3, nonce_manager)

    raw_tx = HexBytes(bytes.fromhex(
        "02f8b10185012a05f2008302faf094e592427a0aece92de3edee1f18e0157c05861564"
        "80b844095ea7b300000000000000000000000000000000000000000000000000000000"
        "000000601ba0f9c9c7dd0ef4b5fbf1be738698fb0cdd0d0b29010b191ed257a7b82d49"
        "18dfa04e99ce3b1cd9e4b8b3d299f330feb0b5bb3842fd07b5f48989a4b70318e0a58"
    ))
    builder.send_transaction(raw_tx, w3.eth.accounts[0], strategy_id="sim", mutation_id="fork", risk_level="low")


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
