#!/usr/bin/env python
"""Batch operations for promoting, pausing, or rolling back strategies."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from ai.promote import promote_strategy, rollback
from core.logger import StructuredLogger

LOGGER = StructuredLogger("batch_ops")


def pause_strategy(path: Path, paused_dir: Path) -> None:
    if not path.exists():
        return
    paused_dir.mkdir(parents=True, exist_ok=True)
    dest = paused_dir / path.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(path), str(dest))
    LOGGER.log("paused", strategy_id=path.name, risk_level="low")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["promote", "pause", "rollback"])
    parser.add_argument("strategies", nargs="+")
    parser.add_argument("--source-dir", default="staging")
    parser.add_argument("--dest-dir", default="active")
    parser.add_argument("--paused-dir", default="paused")
    args = parser.parse_args()

    if os.getenv("FOUNDER_APPROVED") != "1":
        raise SystemExit("Founder approval required")

    src_dir = Path(args.source_dir)
    dst_dir = Path(args.dest_dir)
    paused_dir = Path(args.paused_dir)

    for strat in args.strategies:
        s = src_dir / strat
        d = dst_dir / strat
        if args.action == "promote":
            promote_strategy(s, d, approved=True, evidence={"batch": True})
        elif args.action == "pause":
            pause_strategy(d, paused_dir)
        elif args.action == "rollback":
            rollback(d, "batch")


if __name__ == "__main__":  # pragma: no cover - CLI
    main()

