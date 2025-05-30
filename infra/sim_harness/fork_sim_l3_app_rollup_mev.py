"""Fork simulation for L3AppRollupMEV."""

import os
import time
from pathlib import Path


from strategies.l3_app_rollup_mev.strategy import (
    L3AppRollupMEV,
    PoolConfig,
    BridgeConfig,
)

try:  # pragma: no cover
    from web3 import Web3
    from web3.middleware import geth_poa_middleware  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    raise SystemExit("web3 required for fork simulation")

FORK_BLOCK = int(os.getenv("FORK_BLOCK", "19741234"))
RPC_L2 = os.getenv("RPC_ARBITRUM_URL", "http://localhost:8547")
RPC_L3 = os.getenv("RPC_ZKSYNC_URL", "http://localhost:8550")

POOLS = {
    "l2": PoolConfig(
        os.getenv("POOL_ARBITRUM", "0xb3f8e4262c5bfcc0a304143cfb33c7a9a64e0fe0"),
        "arbitrum",
    ),
    # zkSync ETH/USDC pool
    "l3": PoolConfig(
        os.getenv("POOL_ZKSYNC", "0x8e5cE2F599bEb742DB3A07b0C3aAf7c297C91701"),
        "zksync",
    ),
}

BRIDGES = {
    ("zksync", "arbitrum"): BridgeConfig(0.0005, latency_sec=10),
}


def main() -> None:  # pragma: no cover
    w3 = Web3(Web3.HTTPProvider(RPC_L2))
    w3.middleware_onion.add(geth_poa_middleware)
    if w3.eth.block_number < FORK_BLOCK:
        raise SystemExit("RPC must be forked at or after block %s" % FORK_BLOCK)
    strat = L3AppRollupMEV(POOLS, BRIDGES)
    found = False
    for _ in range(10):
        result = strat.run_once()
        if result and result.get("opportunity"):
            found = True
            break
        time.sleep(1)
    assert found, "no L3 opportunity detected in window"
    Path("logs/sim_complete.txt").write_text("done")


if __name__ == "__main__":  # pragma: no cover
    main()
