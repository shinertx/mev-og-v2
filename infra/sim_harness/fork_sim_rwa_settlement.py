"""Fork simulation for rwa_settlement."""

import os
import time
from pathlib import Path


from strategies.rwa_settlement.strategy import RWASettlementMEV, VenueConfig

try:  # pragma: no cover
    from web3 import Web3
except Exception:
    raise SystemExit("web3 required for fork simulation")

FORK_BLOCK = int(os.getenv("FORK_BLOCK", "19741234"))
RPC_ETH = os.getenv("RPC_ETHEREUM_URL", "http://localhost:8545")

VENUES = {
    "dex": VenueConfig("dex", "asset"),
    "cex": VenueConfig("cex", "asset"),
}


def main() -> None:  # pragma: no cover
    w3 = Web3(Web3.HTTPProvider(RPC_ETH))
    if w3.eth.block_number < FORK_BLOCK:
        raise SystemExit("RPC must be forked at or after block %s" % FORK_BLOCK)
    strat = RWASettlementMEV(VENUES)
    found = False
    for _ in range(5):
        result = strat.run_once()
        if result and result.get("opportunity"):
            found = True
            break
        time.sleep(1)
    assert found, "no settlement opportunity detected"
    Path("logs/sim_complete.txt").write_text("done")


if __name__ == "__main__":  # pragma: no cover
    main()
