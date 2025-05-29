"""Strategy benchmarking and pruning utilities."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from core.logger import StructuredLogger
from ai.mutator import score_strategies, prune_strategies
from ai.mutation_log import log_mutation


class ExternalSignalFetcher:
    """Fetch external alpha signals from a JSON file."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.getenv("EXTERNAL_ALPHA_PATH", "data/external_signals.json")

    def fetch(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path) as fh:
                return json.load(fh)
        except Exception:
            return {}


class StrategyScoreboard:
    """Collect metrics, rank strategies and trigger pruning."""

    def __init__(self, orchestrator: Any, signal_fetcher: ExternalSignalFetcher | None = None) -> None:
        self.orchestrator = orchestrator
        self.signal_fetcher = signal_fetcher or ExternalSignalFetcher()
        self.logger = StructuredLogger("strategy_scoreboard")

    # --------------------------------------------------------------
    def collect_metrics(self) -> Dict[str, Dict[str, float]]:
        """Return live metrics for all strategies."""
        ext = self.signal_fetcher.fetch()
        market_pnl = float(ext.get("market_pnl", 0.0))
        metrics: Dict[str, Dict[str, float]] = {}
        strategies = getattr(self.orchestrator, "strategies", {})
        for sid, strat in strategies.items():
            trades: List[float] = getattr(getattr(strat, "capital_lock", strat), "trades", [])
            pnl = float(sum(trades))
            losses = sum(1 for t in trades if t < 0)
            risk = losses / float(len(trades) or 1)
            edge = pnl - market_pnl
            metrics[sid] = {
                "realized_pnl": pnl,
                "edge_vs_market": edge,
                "win_rate": 1 - risk,
                "drawdown": risk,
                "failures": 0,
            }
        return metrics

    # --------------------------------------------------------------
    def prune_and_score(self) -> Dict[str, Any]:
        """Score strategies and prune underperformers."""
        metrics = self.collect_metrics()
        scores = score_strategies(metrics, output_path="logs/scoreboard.json")
        flagged = prune_strategies(metrics)
        for sid in flagged:
            self.logger.log("prune_strategy", strategy_id=sid, risk_level="medium")
            log_mutation("auto_prune", strategy_id=sid)
        return {"scores": scores, "pruned": flagged}


if __name__ == "__main__":  # pragma: no cover - CLI entry
    import argparse
    from core.orchestrator import Orchestrator

    parser = argparse.ArgumentParser(description="Run strategy scoreboard")
    parser.add_argument("--config", default="config.yaml", help="Orchestrator config")
    args = parser.parse_args()

    orch = Orchestrator.from_config(args.config)
    board = StrategyScoreboard(orch)
    result = board.prune_and_score()
    print(json.dumps(result, indent=2))


