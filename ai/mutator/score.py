"""Strategy scoring utilities.

Module purpose and system role:
    - Evaluate performance metrics for each strategy and produce a ranking.
    - Penalize chaos drill failures and DR events so unstable modules are pruned.
    - Emit scores to JSON and structured logs for later mutation.

Integration points and dependencies:
    - Consumes metrics dictionaries (e.g., from ``core.metrics`` or strategy logs).
    - Uses :class:`core.logger.StructuredLogger` for logging.

Simulation/test hooks and kill conditions:
    - Pure-python; deterministic for unit and chaos tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typing import Any, Dict, List
import hashlib

from core.logger import StructuredLogger

LOGGER = StructuredLogger("strategy_score")


def _version_hash(sid: str, data: Dict[str, Any]) -> str:
    """Return a short SHA-256 hash for versioning."""

    digest = hashlib.sha256(json.dumps({"sid": sid, "data": data}, sort_keys=True).encode()).hexdigest()
    return digest[:8]


def score_strategies(
    metrics: Dict[str, Dict[str, Any]],
    output_path: str = "logs/strategy_scores.json",
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Compute scores for strategies based solely on live metrics.

    Parameters
    ----------
    metrics:
        Mapping of ``strategy_id`` to metric dictionary loaded from live trade
        results or databases. Expected keys are ``realized_pnl``, ``sharpe``,
        ``drawdown``, ``win_rate`` and ``failures``. Optional ``parent_hash``
        can track lineage between mutants.
    output_path:
        JSON file path where ranked scores will be written.
    """

    ranking: List[Dict[str, Any]] = []
    for sid, data in metrics.items():
        pnl = float(data.get("realized_pnl", 0.0))
        sharpe = float(data.get("sharpe", 0.0))
        drawdown = float(data.get("drawdown", 0.0))
        win_rate = float(data.get("win_rate", 0.0))
        failures = int(data.get("failures", 0))
        chaos = int(data.get("chaos_failures", 0))
        dr_triggers = int(data.get("dr_triggers", 0))

        score = (
            pnl
            + sharpe * 100
            - drawdown * 50
            + win_rate * 10
            - failures * 20
            - chaos * 10
            - dr_triggers * 5
        )

        vh = _version_hash(sid, data)

        ranking.append(
            {
                "strategy": sid,
                "version": vh,
                "parent": data.get("parent_hash"),
                "score": score,
                "pnl": pnl,
                "sharpe": sharpe,
                "drawdown": drawdown,
                "win_rate": win_rate,
                "failures": failures,
                "chaos_failures": chaos,
                "dr_triggers": dr_triggers,
            }
        )

    ranking.sort(key=lambda x: x["score"], reverse=True)
    top = ranking[:top_n]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(top, fh, indent=2)
    LOGGER.log(
        "strategy_scores",
        strategy_id="scoring",
        mutation_id=os.getenv("MUTATION_ID", "dev"),
        risk_level="low",
        scores=top,
    )
    return top
