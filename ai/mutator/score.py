"""Strategy scoring utilities.

Module purpose and system role:
    - Evaluate performance metrics for each strategy and produce a ranking.
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
from statistics import mean, stdev
from typing import Any, Dict, List

from core.logger import StructuredLogger

LOGGER = StructuredLogger("strategy_score")


def score_strategies(metrics: Dict[str, Dict[str, Any]], output_path: str = "logs/strategy_scores.json") -> List[Dict[str, Any]]:
    """Compute scores for strategies based on provided ``metrics``.

    Parameters
    ----------
    metrics:
        Mapping of strategy_id to metric dictionary. Expected keys include
        ``pnl``, ``returns``, ``risk``, ``volatility``, ``wins``, ``losses``,
        ``latencies``, and ``opportunities``.
    output_path:
        JSON file path where ranked scores will be written.
    """

    ranking: List[Dict[str, Any]] = []
    for sid, data in metrics.items():
        pnl = float(data.get("pnl", 0.0))
        returns = data.get("returns", [pnl])
        sharpe = 0.0
        if isinstance(returns, list) and len(returns) > 1:
            try:
                sharpe = mean(returns) / stdev(returns)
            except Exception:
                sharpe = 0.0
        risk = float(data.get("risk", 0.0))
        volatility = float(data.get("volatility", 0.0))
        wins = int(data.get("wins", 0))
        losses = int(data.get("losses", 0))
        win_rate = wins / max(wins + losses, 1)
        latencies = data.get("latencies", [])
        avg_latency = mean(latencies) if isinstance(latencies, list) and latencies else 0.0
        opportunities = int(data.get("opportunities", 0))
        density = opportunities / max(len(latencies), 1)

        score = (
            pnl
            + sharpe * 100
            + win_rate * 10
            - risk * 100
            - volatility * 10
            - avg_latency * 0.1
            + density * 5
        )
        ranking.append(
            {
                "strategy": sid,
                "score": score,
                "pnl": pnl,
                "sharpe": sharpe,
                "risk": risk,
                "volatility": volatility,
                "win_rate": win_rate,
                "avg_latency": avg_latency,
                "opportunity_density": density,
            }
        )

    ranking.sort(key=lambda x: x["score"], reverse=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(ranking, fh, indent=2)
    LOGGER.log(
        "strategy_scores",
        strategy_id="scoring",
        mutation_id=os.getenv("MUTATION_ID", "dev"),
        risk_level="low",
        scores=ranking,
    )
    return ranking
