"""Fork simulation for cross_rollup_superbot."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from strategies.cross_rollup_superbot.strategy import (
    CrossRollupSuperbot,
    PoolConfig,
    BridgeConfig,
)

try:  # pragma: no cover
    from web3 import Web3
    from web3.middleware import geth_poa_middleware  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    raise SystemExit("web3 required for fork simulation")

FORK_BLOCK = int(os.getenv("FORK_BLOCK", "19741234"))
RPC_ETH = os.getenv("RPC_ETHEREUM_URL", "http://localhost:8545")
RPC_ARB = os.getenv("RPC_ARBITRUM_URL", "http://localhost:8547")
RPC_OPT = os.getenv("RPC_OPTIMISM_URL", "http://localhost:8548")

POOLS = {
    "eth": PoolConfig(Web3.to_checksum_address(os.getenv("POOL_ETHEREUM", "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8")), "ethereum"),
    "arb": PoolConfig(Web3.to_checksum_address(os.getenv("POOL_ARBITRUM", "0xb3f8e4262c5bfcc0a304143cfb33c7a9a64e0fe0")), "arbitrum"),
    "opt": PoolConfig(Web3.to_checksum_address(os.getenv("POOL_OPTIMISM", "0x85149247691df622eaf1a8bd0c4bd90d38a83a1f")), "optimism"),
}

BRIDGES = {
    ("ethereum", "arbitrum"): BridgeConfig(0.0005),
    ("arbitrum", "ethereum"): BridgeConfig(0.0005),
    ("optimism", "ethereum"): BridgeConfig(0.0005),
    ("ethereum", "optimism"): BridgeConfig(0.0005),
}


def main() -> None:  # pragma: no cover
    w3 = Web3(Web3.HTTPProvider(RPC_ETH))
    w3.middleware_onion.add(geth_poa_middleware)
    if w3.eth.block_number < FORK_BLOCK:
        raise SystemExit("RPC must be forked at or after block %s" % FORK_BLOCK)
    strat = CrossRollupSuperbot(POOLS, BRIDGES)
    found = False
    for _ in range(10):
        result = strat.run_once()
        if result and result.get("opportunity"):
            found = True
            break
        time.sleep(1)
    assert found, "no arbitrage opportunity detected in window"
    Path("logs/sim_complete.txt").write_text("done")


if __name__ == "__main__":  # pragma: no cover
    main()

