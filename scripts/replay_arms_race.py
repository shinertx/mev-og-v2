#!/usr/bin/env python3
"""Replay historical MEV transactions for benchmarking."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from ai.mutation_log import log_mutation
from core.logger import make_json_safe


def load_txs(path: str) -> List[Dict[str, Any]]:
    file = Path(path)
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("[]")
        return []
    data = json.loads(file.read_text())
    return data if isinstance(data, list) else []


def replay(txs: List[Dict[str, Any]]) -> Dict[str, int]:
    wins = 0
    losses = 0
    for tx in txs:
        if float(tx.get("profit", 0)) > 0:
            wins += 1
        else:
            losses += 1
    log_mutation(
        "arms_race", wins=wins, losses=losses, total=len(txs)
    )
    return {"wins": wins, "losses": losses}


def main() -> None:
    p = argparse.ArgumentParser(description="Replay arms race transactions")
    p.add_argument("--log", required=True, help="JSON file with tx data")
    args = p.parse_args()
    stats = replay(load_txs(args.log))
    print(json.dumps(make_json_safe(stats)))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
