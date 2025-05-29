
"""Advanced live strategy benchmarking and pruning."""


from __future__ import annotations

import json
import os

from collections import defaultdict
from typing import Any, Dict, List, cast


from core.logger import StructuredLogger
from core import metrics
from agents.multi_sig import MultiSigApproval
from ai.mutation_manager import MutationManager
from ai.mutator import score_strategies, prune_strategies
from ai.mutation_log import log_mutation


class SignalProvider:
    """Base class for external alpha signal providers."""

    def fetch(self) -> Dict[str, float]:  # pragma: no cover - interface
        return {}


class ExternalSignalFetcher:
    """Aggregate multiple real-time signal providers."""

    def __init__(self, path: str | None = None, providers: List[SignalProvider] | None = None) -> None:
        self.path: str = cast(
            str,
            path or os.getenv("EXTERNAL_ALPHA_PATH", "data/external_signals.json"),
        )
        self.providers = providers or []
        if not providers:
            from adapters.alpha_signals import (
                DuneAnalyticsAdapter,
                WhaleAlertAdapter,
                CoinbaseWebSocketAdapter,
            )
            dune_key = os.getenv("DUNE_API_KEY")
            dune_query = os.getenv("DUNE_QUERY_ID")
            dune_url = os.getenv("DUNE_API_URL", "https://api.dune.com")
            if dune_key and dune_query:
                self.providers.append(DuneAnalyticsAdapter(dune_url, dune_key, dune_query))
            whale_key = os.getenv("WHALE_ALERT_KEY")
            whale_url = os.getenv("WHALE_ALERT_URL", "https://api.whale-alert.io")
            if whale_key:
                self.providers.append(WhaleAlertAdapter(whale_url, whale_key))
            cb_url = os.getenv("COINBASE_WS_URL")
            if cb_url:
                self.providers.append(CoinbaseWebSocketAdapter(cb_url))

    # ------------------------------------------------------------------
    def _file_signals(self) -> Dict[str, float]:

        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path) as fh:

                data = json.load(fh)
                if isinstance(data, dict):
                    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
                return {}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    def fetch(self) -> Dict[str, float]:
        signals: Dict[str, float] = self._file_signals()
        for prov in list(self.providers):
            try:
                signals.update(prov.fetch())
            except Exception:
                continue
        return signals


class AlphaDecayModel:
    """Detect alpha decay using linear or Bayesian regression."""

    def __init__(
        self,
        window: int = 5,
        method: str = "linear",
        sensitivity: float = 0.1,
        retrain: int = 50,
    ) -> None:
        self.history: Dict[str, List[float]] = defaultdict(list)
        self.window = window
        self.method = method
        self.sensitivity = sensitivity
        self.retrain = retrain
        self._counter = 0

    # ------------------------------------------------------------------
    def score(self, sid: str, metric_data: Dict[str, float], signals: Dict[str, float]) -> float:
        base = (
            metric_data.get("realized_pnl", 0.0)
            + metric_data.get("edge_vs_market", 0.0) * 2
            + metric_data.get("win_rate", 0.0) * 10
            - metric_data.get("drawdown", 0.0) * 50
            - metric_data.get("failures", 0.0) * 20
            + signals.get("whale_flow", 0.0) * 2
            + signals.get("news_sentiment", 0.0) * 5
        )
        hist = self.history[sid]
        hist.append(base)
        if len(hist) > self.window:
            hist.pop(0)
        slope = 0.0
        n = len(hist)
        if n > 1:
            x = list(range(n))
            sum_x = sum(x)
            sum_y = sum(hist)
            sum_xy = sum(x[i] * hist[i] for i in range(n))
            sum_xx = sum(i * i for i in x)
            denom = n * sum_xx - sum_x * sum_x
            if denom:
                if self.method == "bayesian":
                    slope = (sum_xy + 0.1) / (sum_xx + 0.1)
                else:
                    slope = (n * sum_xy - sum_x * sum_y) / denom
        return base + slope * 10

    # ------------------------------------------------------------------
    def decayed(self, sid: str) -> bool:
        hist = self.history.get(sid, [])
        if len(hist) < self.window:
            return False
        n = len(hist)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(hist)
        sum_xy = sum(x[i] * hist[i] for i in range(n))
        sum_xx = sum(i * i for i in x)
        denom = n * sum_xx - sum_x * sum_x
        if denom:
            if self.method == "bayesian":
                slope = (sum_xy + 0.1) / (sum_xx + 0.1)
            else:
                slope = (n * sum_xy - sum_x * sum_y) / denom
        else:
            slope = 0.0
        self._counter += 1
        if self._counter % self.retrain == 0:
            self.history[sid] = hist[-self.window :]
        return slope < -self.sensitivity


class StrategyScoreboard:
    """Collect metrics, rank strategies and prune underperformers."""

    def __init__(
        self,
        orchestrator: Any,
        signal_fetcher: ExternalSignalFetcher | None = None,
        model: AlphaDecayModel | None = None,
        multisig: MultiSigApproval | None = None,
        mutator: MutationManager | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.signal_fetcher = signal_fetcher or ExternalSignalFetcher()
        self.model = model or AlphaDecayModel()
        self.multisig = multisig or MultiSigApproval()
        self.mutator = mutator
        self.logger = StructuredLogger("strategy_scoreboard")

    # --------------------------------------------------------------
    def collect_metrics(self) -> Dict[str, Dict[str, float]]:

        """Return live metrics enriched with market signals."""

        ext = self.signal_fetcher.fetch()
        market_pnl = float(ext.get("market_pnl", 0.0))
        metrics_map: Dict[str, Dict[str, float]] = {}
        strategies = getattr(self.orchestrator, "strategies", {})
        for sid, strat in strategies.items():
            trades: List[float] = getattr(getattr(strat, "capital_lock", strat), "trades", [])
            pnl = float(sum(trades))
            losses = sum(1 for t in trades if t < 0)
            risk = losses / float(len(trades) or 1)
            edge = pnl - market_pnl
            metrics_map[sid] = {
                "realized_pnl": pnl,
                "edge_vs_market": edge,
                "win_rate": 1 - risk,
                "drawdown": risk,
                "failures": 0,
            }
        return metrics_map

    # --------------------------------------------------------------
    def prune_and_score(self) -> Dict[str, Any]:

        """Score strategies and auto-prune underperformers."""
        metrics_map = self.collect_metrics()
        signals = self.signal_fetcher.fetch()
        scores = {}
        ranking: List[Dict[str, Any]] = []
        for sid, data in metrics_map.items():
            score = self.model.score(sid, data, signals)
            scores[sid] = score
            metrics.record_strategy_score(sid, score)
            ranking.append({"strategy": sid, "score": score})
        ranking.sort(key=lambda x: x["score"], reverse=True)
        json_path = "logs/scoreboard.json"
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w") as fh:
            json.dump(ranking, fh, indent=2)
        flagged = prune_strategies(metrics_map)
        for sid in list(scores):
            if self.model.decayed(sid):
                metrics.record_decay_alert()
                flagged.append(sid)
        flagged = list(dict.fromkeys(flagged))
        pruned: List[str] = []
        for sid in flagged:
            self.logger.log("prune_strategy", strategy_id=sid, risk_level="medium")
            log_mutation("auto_prune", strategy_id=sid)
            metrics.record_mutation_event()
            if self.multisig.request("prune", {"strategy": sid}):
                self.orchestrator.strategies.pop(sid, None)
                pruned.append(sid)
                metrics.record_prune()
                if hasattr(self.orchestrator, "ops_agent"):
                    self.orchestrator.ops_agent.notify(f"pruned {sid}")
        score_strategies(metrics_map, output_path=json_path)
        if self.mutator:
            dry = os.getenv("MUTATION_DRY_RUN") == "1"
            self.mutator.handle_pruning(pruned, dry_run=dry)
        metrics.record_mutation_event()
        return {"scores": ranking, "pruned": pruned}



if __name__ == "__main__":  # pragma: no cover - CLI entry
    import argparse
    from core.orchestrator import StrategyOrchestrator


    parser = argparse.ArgumentParser(description="Run strategy scoreboard")
    parser.add_argument("--config", default="config.yaml", help="Orchestrator config")
    args = parser.parse_args()


    orch = StrategyOrchestrator(args.config)

    board = StrategyScoreboard(orch)
    result = board.prune_and_score()
    print(json.dumps(result, indent=2))

