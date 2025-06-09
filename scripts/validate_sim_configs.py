#!/usr/bin/env python3.11
"""Validate simulation config JSON files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_KEYS = {"env", "block_number", "strategy_id", "expected_pnl", "max_drawdown", "validators"}


def validate_file(path: Path) -> None:
    data = json.loads(path.read_text())
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise SystemExit(f"{path.name}: missing keys {', '.join(sorted(missing))}")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    base = Path("sim/configs")
    for file in base.glob("*.json"):
        validate_file(file)
    print("config validation passed")
