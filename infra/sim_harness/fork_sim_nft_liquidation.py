"""Fork simulation for nft_liquidation."""

import os
import time
from pathlib import Path


from strategies.nft_liquidation.strategy import NFTLiquidationMEV, AuctionConfig
from infra.sim_harness import start_metrics
from core import metrics

try:  # pragma: no cover
    from web3 import Web3
except Exception:
    raise SystemExit("web3 required for fork simulation")

FORK_BLOCK = int(os.getenv("FORK_BLOCK", "19741234"))
RPC_ETH = os.getenv("RPC_ETHEREUM_URL", "http://localhost:8545")

AUCTIONS = {
    "proto": AuctionConfig("proto", "ethereum"),
}


def main() -> None:  # pragma: no cover
    start_metrics()
    w3 = Web3(Web3.HTTPProvider(RPC_ETH))
    if w3.eth.block_number < FORK_BLOCK:
        raise SystemExit("RPC must be forked at or after block %s" % FORK_BLOCK)
    strat = NFTLiquidationMEV(AUCTIONS)
    found = False
    for _ in range(5):
        result = strat.run_once()
        if result and result.get("opportunity"):
            metrics.record_opportunity(0.0, float(result.get("profit_eth", 0)), 0.0)
            found = True
            break
        time.sleep(1)
    if not found:
        metrics.record_fail()
        assert False, "no auction opportunity detected"
    Path("logs/sim_complete.txt").write_text("done")


if __name__ == "__main__":  # pragma: no cover
    main()
