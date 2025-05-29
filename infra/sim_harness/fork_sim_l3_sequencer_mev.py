"""Fork simulation for l3_sequencer_mev."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from strategies.l3_sequencer_mev.strategy import L3SequencerMEV, PoolConfig

try:  # pragma: no cover
    from web3 import Web3
except Exception:
    raise SystemExit("web3 required for fork simulation")

FORK_BLOCK = int(os.getenv("FORK_BLOCK", "19741234"))
RPC_ETH = os.getenv("RPC_ETHEREUM_URL", "http://localhost:8545")

POOLS = {
    # Scroll ETH/USDC pool
    "l3": PoolConfig(
        os.getenv("POOL_L3", "0x6B3d1a6B4a7a4c294aB6C2bC8F6F4FDb61F7E5B8"),
        "ethereum",
    ),
}


def main() -> None:  # pragma: no cover
    w3 = Web3(Web3.HTTPProvider(RPC_ETH))
    if w3.eth.block_number < FORK_BLOCK:
        raise SystemExit("RPC must be forked at or after block %s" % FORK_BLOCK)
    strat = L3SequencerMEV(POOLS)
    found = False
    for _ in range(5):
        result = strat.run_once()
        if result and result.get("opportunity"):
            found = True
            break
        time.sleep(1)
    assert found, "no sequencer opportunity detected"
    Path("logs/sim_complete.txt").write_text("done")


if __name__ == "__main__":  # pragma: no cover
    main()
