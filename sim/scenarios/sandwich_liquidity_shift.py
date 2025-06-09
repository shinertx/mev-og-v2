"""Scenario: sandwich liquidity shift using cross-rollup harness."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from infra.sim_harness import fork_sim_cross_rollup_superbot


def main() -> None:  # pragma: no cover - CLI entry
    parser = argparse.ArgumentParser(description="Simulate sandwich liquidity shift")
    parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "optimism_l2.json",
        help="Path to scenario config JSON",
    )
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    os.environ["FORK_BLOCK"] = str(cfg.get("block_number", 19741234))
    fork_sim_cross_rollup_superbot.main()


if __name__ == "__main__":  # pragma: no cover
    main()
