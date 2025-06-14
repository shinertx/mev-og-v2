"""Fork simulation for cross-domain arbitrage detection."""

import os
import time
from pathlib import Path


from strategies.cross_domain_arb.strategy import CrossDomainArb, PoolConfig, BridgeConfig
from infra.sim_harness import start_metrics
from core import metrics

try:  # pragma: no cover
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
except Exception:  # pragma: no cover
    raise SystemExit("web3 required for fork simulation")

FORK_BLOCK = int(os.getenv("FORK_BLOCK", "19741234"))
RPC_ETH = os.getenv("RPC_ETHEREUM_URL", "http://localhost:8545")
RPC_ARB = os.getenv("RPC_ARBITRUM_URL", "http://localhost:8547")
RPC_OPT = os.getenv("RPC_OPTIMISM_URL", "http://localhost:8548")

POOLS: dict[str, PoolConfig] = {
    "eth": PoolConfig(Web3.to_checksum_address(os.getenv("POOL_ETHEREUM", "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8")), "ethereum"),
    "arb": PoolConfig(Web3.to_checksum_address(os.getenv("POOL_ARBITRUM", "0xb3f8e4262c5bfcc0a304143cfb33c7a9a64e0fe0")), "arbitrum"),
    "opt": PoolConfig(Web3.to_checksum_address(os.getenv("POOL_OPTIMISM", "0x85149247691df622eaf1a8bd0c4bd90d38a83a1f")), "optimism"),
}

BRIDGE_COSTS: dict[tuple[str, str], BridgeConfig] = {}


def main() -> None:  # pragma: no cover
    start_metrics()
    w3 = Web3(Web3.HTTPProvider(RPC_ETH))
    w3.middleware_onion.add(geth_poa_middleware)
    if w3.eth.block_number < FORK_BLOCK:
        raise SystemExit("RPC must be forked at or after block %s" % FORK_BLOCK)
    strategy = CrossDomainArb(POOLS, BRIDGE_COSTS)
    found = False
    for _ in range(10):
        result = strategy.run_once()
        if result and result.get("opportunity"):
            metrics.record_opportunity(0.0, float(result.get("profit_eth", 0)), 0.0)
            found = True
            break
        time.sleep(1)
    if not found:
        metrics.record_fail()
        assert False, "no arbitrage opportunity detected in window"
    Path("logs/sim_complete.txt").write_text("done")


if __name__ == "__main__":  # pragma: no cover
    main()
