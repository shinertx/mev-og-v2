"""
Strategy Scoreboard with Auto-Pruning and Edge Decay.
Benchmarks strategies against real-time signals and manages lifecycle.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
from collections import defaultdict
import aiohttp

from core.logger import StructuredLogger
from core.metrics import record_scoreboard_event
from ai.voting import VotingQuorum

LOG = StructuredLogger("strategy_scoreboard", log_file="logs/scoreboard.json")
SCOREBOARD_STATE_FILE = Path("state/strategy_scoreboard.json")
MUTATION_LOG_FILE = Path("logs/mutation_log.json")


class StrategyStatus(Enum):
    ACTIVE = "active"
    PROBATION = "probation"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class SignalSource(Enum):
    DEX_CEX_GAP = "dex_cex_gap"
    WHALE_ALERT = "whale_alert"
    DUNE_QUERY = "dune_query"
    COINBASE_FLOW = "coinbase_flow"
    SOCIAL_SIGNAL = "social_signal"


@dataclass
class StrategyScore:
    strategy_id: str
    total_opportunities: int
    captured_opportunities: int
    total_profit_eth: float
    avg_latency_ms: float
    error_rate: float
    success_rate: float
    edge_decay_factor: float
    last_opportunity: Optional[str]
    last_update: str
    status: StrategyStatus
    performance_trend: List[float]  # Last 7 days
    signal_scores: Dict[str, float]  # Score by signal source


@dataclass
class MarketSignal:
    source: SignalSource
    timestamp: datetime
    opportunity_value_eth: float
    confidence: float
    metadata: Dict[str, Any]


class StrategyScoreboard:
    """Benchmarks strategies against real-time market signals."""
    
    def __init__(
        self,
        dune_api_key: Optional[str] = None,
        whale_alert_key: Optional[str] = None,
        coinbase_ws_url: Optional[str] = None,
        prune_threshold: float = 0.3,
        decay_rate: float = 0.95,  # Daily decay
        probation_threshold: float = 0.5
    ):
        self.dune_api_key = dune_api_key or os.getenv("DUNE_API_KEY")
        self.whale_alert_key = whale_alert_key or os.getenv("WHALE_ALERT_KEY")
        self.coinbase_ws_url = coinbase_ws_url or os.getenv("COINBASE_WS_URL")
        
        self.prune_threshold = prune_threshold
        self.decay_rate = decay_rate
        self.probation_threshold = probation_threshold
        
        self.scores: Dict[str, StrategyScore] = {}
        self.market_signals: List[MarketSignal] = []
        self.voting_quorum = VotingQuorum()
        
        self._load_state()
        self._start_signal_collection()
    
    def _load_state(self):
        """Load scoreboard state from disk."""
        if SCOREBOARD_STATE_FILE.exists():
            with open(SCOREBOARD_STATE_FILE) as f:
                data = json.load(f)
                for sid, score_data in data.get("scores", {}).items():
                    score_data["status"] = StrategyStatus(score_data["status"])
                    self.scores[sid] = StrategyScore(**score_data)
    
    def _save_state(self):
        """Save scoreboard state to disk."""
        SCOREBOARD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "scores": {
                sid: {**asdict(score), "status": score.status.value}
                for sid, score in self.scores.items()
            },
            "last_update": datetime.now(timezone.utc).isoformat()
        }
        
        with open(SCOREBOARD_STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def _start_signal_collection(self):
        """Start background tasks for signal collection."""
        asyncio.create_task(self._collect_dex_cex_gaps())
        asyncio.create_task(self._collect_whale_alerts())
        asyncio.create_task(self._collect_dune_signals())
        asyncio.create_task(self._collect_coinbase_flow())
    
    async def _collect_dex_cex_gaps(self):
        """Monitor DEX/CEX price gaps."""
        while True:
            try:
                # Simulate DEX/CEX monitoring - in production, use real APIs
                # This would connect to Binance, Coinbase, etc. and compare with Uniswap
                
                # Example signal
                signal = MarketSignal(
                    source=SignalSource.DEX_CEX_GAP,
                    timestamp=datetime.now(timezone.utc),
                    opportunity_value_eth=0.05,
                    confidence=0.8,
                    metadata={
                        "dex": "uniswap_v3",
                        "cex": "binance",
                        "pair": "ETH/USDC",
                        "gap_percent": 0.3
                    }
                )
                
                self.market_signals.append(signal)
                
                # Keep only last 1000 signals
                if len(self.market_signals) > 1000:
                    self.market_signals = self.market_signals[-1000:]
                
            except Exception as e:
                LOG.log("signal_collection_error", source="dex_cex", error=str(e))
            
            await asyncio.sleep(60)  # Check every minute
    
    async def _collect_whale_alerts(self):
        """Monitor whale movements."""
        if not self.whale_alert_key:
            return
        
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    url = "https://api.whale-alert.io/v1/transactions"
                    params = {
                        "api_key": self.whale_alert_key,
                        "min_value": "1000000",  # $1M+ transactions
                        "limit": 100
                    }
                    
                    async with session.get(url, params=params, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            
                            for tx in data.get("transactions", []):
                                if tx.get("blockchain") == "ethereum":
                                    signal = MarketSignal(
                                        source=SignalSource.WHALE_ALERT,
                                        timestamp=datetime.fromisoformat(tx["timestamp"]),
                                        opportunity_value_eth=float(tx.get("amount_usd", 0)) / 2000,  # Rough ETH conversion
                                        confidence=0.7,
                                        metadata={
                                            "from": tx.get("from", {}).get("address"),
                                            "to": tx.get("to", {}).get("address"),
                                            "symbol": tx.get("symbol"),
                                            "amount": tx.get("amount")
                                        }
                                    )
                                    
                                    self.market_signals.append(signal)
                
            except Exception as e:
                LOG.log("signal_collection_error", source="whale_alert", error=str(e))
            
            await asyncio.sleep(300)  # Check every 5 minutes
    
    async def _collect_dune_signals(self):
        """Collect signals from Dune Analytics."""
        if not self.dune_api_key:
            return
        
        # Example Dune queries for MEV opportunities
        queries = [
            {"id": "1234567", "name": "sandwich_opportunities"},
            {"id": "2345678", "name": "arbitrage_gaps"},
            {"id": "3456789", "name": "liquidation_targets"}
        ]
        
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"X-Dune-API-Key": self.dune_api_key}
                    
                    for query in queries:
                        url = f"https://api.dune.com/api/v1/query/{query['id']}/results"
                        
                        async with session.get(url, headers=headers, timeout=30) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                
                                # Process query results
                                for row in data.get("result", {}).get("rows", []):
                                    signal = MarketSignal(
                                        source=SignalSource.DUNE_QUERY,
                                        timestamp=datetime.now(timezone.utc),
                                        opportunity_value_eth=float(row.get("opportunity_eth", 0)),
                                        confidence=0.85,
                                        metadata={
                                            "query": query["name"],
                                            "data": row
                                        }
                                    )
                                    
                                    self.market_signals.append(signal)
                
            except Exception as e:
                LOG.log("signal_collection_error", source="dune", error=str(e))
            
            await asyncio.sleep(600)  # Check every 10 minutes
    
    async def _collect_coinbase_flow(self):
        """Monitor Coinbase order flow via WebSocket."""
        if not self.coinbase_ws_url:
            return
        
        # In production, implement WebSocket connection to Coinbase
        # Monitor large orders, unusual flow patterns, etc.
        pass
    
    def update_strategy_score(
        self,
        strategy_id: str,
        captured_opportunity: bool,
        profit_eth: float,
        latency_ms: float,
        error: bool = False
    ):
        """Update strategy score based on performance."""
        if strategy_id not in self.scores:
            self.scores[strategy_id] = StrategyScore(
                strategy_id=strategy_id,
                total_opportunities=0,
                captured_opportunities=0,
                total_profit_eth=0.0,
                avg_latency_ms=0.0,
                error_rate=0.0,
                success_rate=0.0,
                edge_decay_factor=1.0,
                last_opportunity=None,
                last_update=datetime.now(timezone.utc).isoformat(),
                status=StrategyStatus.ACTIVE,
                performance_trend=[],
                signal_scores=defaultdict(float)
            )
        
        score = self.scores[strategy_id]
        
        # Update counters
        score.total_opportunities += 1
        if captured_opportunity:
            score.captured_opportunities += 1
            score.total_profit_eth += profit_eth
        
        # Update averages
        alpha = 0.1  # Exponential moving average factor
        score.avg_latency_ms = (1 - alpha) * score.avg_latency_ms + alpha * latency_ms
        
        # Update rates
        score.success_rate = score.captured_opportunities / score.total_opportunities
        if error:
            score.error_rate = (score.error_rate * (score.total_opportunities - 1) + 1) / score.total_opportunities
        else:
            score.error_rate = (score.error_rate * (score.total_opportunities - 1)) / score.total_opportunities
        
        score.last_opportunity = datetime.now(timezone.utc).isoformat()
        score.last_update = datetime.now(timezone.utc).isoformat()
        
        # Apply edge decay
        self._apply_edge_decay(score)
        
        # Check status transitions
        self._check_status_transition(score)
        
        self._save_state()
        
        LOG.log(
            "strategy_score_updated",
            strategy_id=strategy_id,
            success_rate=score.success_rate,
            total_profit=score.total_profit_eth,
            status=score.status.value
        )
    
    def _apply_edge_decay(self, score: StrategyScore):
        """Apply time-based decay to strategy edge."""
        if score.last_opportunity:
            last_opp = datetime.fromisoformat(score.last_opportunity)
            days_since = (datetime.now(timezone.utc) - last_opp).days
            
            # Apply daily decay
            score.edge_decay_factor = self.decay_rate ** days_since
            
            # Decay affects effective success rate
            effective_success = score.success_rate * score.edge_decay_factor
            
            # Update performance trend
            score.performance_trend.append(effective_success)
            if len(score.performance_trend) > 7:
                score.performance_trend = score.performance_trend[-7:]
    
    def _check_status_transition(self, score: StrategyScore):
        """Check if strategy should transition status."""
        effective_score = score.success_rate * score.edge_decay_factor
        
        if score.status == StrategyStatus.ACTIVE:
            if effective_score < self.probation_threshold:
                score.status = StrategyStatus.PROBATION
                LOG.log(
                    "strategy_probation",
                    strategy_id=score.strategy_id,
                    effective_score=effective_score
                )
            elif effective_score < self.prune_threshold:
                score.status = StrategyStatus.DEPRECATED
                LOG.log(
                    "strategy_deprecated",
                    strategy_id=score.strategy_id,
                    effective_score=effective_score
                )
        
        elif score.status == StrategyStatus.PROBATION:
            if effective_score >= self.probation_threshold:
                score.status = StrategyStatus.ACTIVE
                LOG.log(
                    "strategy_reactivated",
                    strategy_id=score.strategy_id,
                    effective_score=effective_score
                )
            elif effective_score < self.prune_threshold:
                score.status = StrategyStatus.DEPRECATED
    
    def benchmark_against_signals(self, strategy_id: str, time_window_hours: int = 24) -> Dict[str, float]:
        """Benchmark strategy against market signals."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
        recent_signals = [s for s in self.market_signals if s.timestamp > cutoff]
        
        if not recent_signals:
            return {}
        
        score = self.scores.get(strategy_id)
        if not score:
            return {}
        
        # Group signals by source
        signals_by_source = defaultdict(list)
        for signal in recent_signals:
            signals_by_source[signal.source].append(signal)
        
        # Calculate capture rate by source
        benchmark_scores = {}
        
        for source, signals in signals_by_source.items():
            total_value = sum(s.opportunity_value_eth for s in signals)
            
            # Estimate captured value (simplified - in production, match actual trades)
            if score.last_opportunity:
                last_opp_time = datetime.fromisoformat(score.last_opportunity)
                if last_opp_time > cutoff:
                    # Assume strategy captured proportional value
                    capture_rate = score.success_rate * score.edge_decay_factor
                    captured_value = total_value * capture_rate * 0.1  # Conservative estimate
                else:
                    captured_value = 0
            else:
                captured_value = 0
            
            benchmark_scores[source.value] = captured_value / max(total_value, 0.001)
            score.signal_scores[source.value] = benchmark_scores[source.value]
        
        return benchmark_scores
    
    def get_pruning_candidates(self) -> List[str]:
        """Get strategies that should be pruned."""
        candidates = []
        
        for strategy_id, score in self.scores.items():
            effective_score = score.success_rate * score.edge_decay_factor
            
            if score.status == StrategyStatus.DEPRECATED or effective_score < self.prune_threshold:
                candidates.append(strategy_id)
        
        return candidates
    
    async def prune_and_score(self) -> Dict[str, Any]:
        """Execute pruning with multi-sig approval."""
        pruning_candidates = self.get_pruning_candidates()
        
        if not pruning_candidates:
            LOG.log("no_pruning_needed")
            return {"pruned": [], "message": "No strategies need pruning"}
        
        # Create voting proposal
        proposal_data = {
            "action": "prune_strategies",
            "strategies": pruning_candidates,
            "scores": {
                sid: {
                    "success_rate": self.scores[sid].success_rate,
                    "edge_decay": self.scores[sid].edge_decay_factor,
                    "total_profit": self.scores[sid].total_profit_eth,
                    "status": self.scores[sid].status.value
                }
                for sid in pruning_candidates
            }
        }
        
        proposal_id = self.voting_quorum.create_mutation_proposal(
            strategy_id="scoreboard",
            mutation_type="strategy_pruning",
            mutation_data=proposal_data,
            proposer="scoreboard_system",
            risk_level="high"
        )
        
        LOG.log(
            "pruning_proposal_created",
            proposal_id=proposal_id,
            candidate_count=len(pruning_candidates)
        )
        
        # Wait for quorum (in production, this would be async)
        max_wait = 3600  # 1 hour
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if self.voting_quorum.quorum_met(proposal_id):
                break
            await asyncio.sleep(60)
        
        if not self.voting_quorum.quorum_met(proposal_id):
            LOG.log("pruning_quorum_timeout", proposal_id=proposal_id)
            return {"pruned": [], "message": "Quorum not reached"}
        
        # Execute pruning
        pruned = []
        for strategy_id in pruning_candidates:
            if strategy_id in self.scores:
                self.scores[strategy_id].status = StrategyStatus.ARCHIVED
                pruned.append(strategy_id)
                
                # Log to mutation log
                self._log_mutation(
                    "strategy_pruned",
                    strategy_id=strategy_id,
                    final_score=self.scores[strategy_id].success_rate,
                    reason="below_threshold"
                )
        
        self._save_state()
        
        LOG.log(
            "pruning_complete",
            pruned_count=len(pruned),
            pruned_strategies=pruned
        )
        
        return {
            "pruned": pruned,
            "message": f"Pruned {len(pruned)} strategies"
        }
    
    def _log_mutation(self, event: str, **kwargs):
        """Log mutation event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **kwargs
        }
        
        with open(MUTATION_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def get_leaderboard(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get top performing strategies."""
        active_scores = [
            score for score in self.scores.values()
            if score.status in [StrategyStatus.ACTIVE, StrategyStatus.PROBATION]
        ]
        
        # Sort by effective score
        sorted_scores = sorted(
            active_scores,
            key=lambda s: s.success_rate * s.edge_decay_factor * (1 + s.total_profit_eth),
            reverse=True
        )
        
        leaderboard = []
        for i, score in enumerate(sorted_scores[:top_n]):
            effective_score = score.success_rate * score.edge_decay_factor
            
            leaderboard.append({
                "rank": i + 1,
                "strategy_id": score.strategy_id,
                "effective_score": round(effective_score, 4),
                "success_rate": round(score.success_rate, 4),
                "total_profit_eth": round(score.total_profit_eth, 4),
                "avg_latency_ms": round(score.avg_latency_ms, 2),
                "edge_decay_factor": round(score.edge_decay_factor, 4),
                "status": score.status.value,
                "trend": "up" if len(score.performance_trend) >= 2 and score.performance_trend[-1] > score.performance_trend[-2] else "down"
            })
        
        return leaderboard
    
    def export_metrics(self) -> Dict[str, Any]:
        """Export metrics for Grafana dashboard."""
        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_strategies": len(self.scores),
            "active_strategies": sum(1 for s in self.scores.values() if s.status == StrategyStatus.ACTIVE),
            "probation_strategies": sum(1 for s in self.scores.values() if s.status == StrategyStatus.PROBATION),
            "deprecated_strategies": sum(1 for s in self.scores.values() if s.status == StrategyStatus.DEPRECATED),
            "total_profit_eth": sum(s.total_profit_eth for s in self.scores.values()),
            "avg_success_rate": np.mean([s.success_rate for s in self.scores.values()]) if self.scores else 0,
            "avg_latency_ms": np.mean([s.avg_latency_ms for s in self.scores.values()]) if self.scores else 0,
            "signal_counts": {
                source.value: len([s for s in self.market_signals if s.source == source])
                for source in SignalSource
            },
            "leaderboard": self.get_leaderboard()
        }
        
        # Record to Prometheus
        for strategy_id, score in self.scores.items():
            record_scoreboard_event(
                strategy_id=strategy_id,
                success_rate=score.success_rate,
                total_profit=score.total_profit_eth,
                edge_decay=score.edge_decay_factor,
                status=score.status.value
            )
        
        return metrics


# Global scoreboard instance
_scoreboard: Optional[StrategyScoreboard] = None


def get_scoreboard() -> StrategyScoreboard:
    """Get or create global scoreboard instance."""
    global _scoreboard
    if _scoreboard is None:
        _scoreboard = StrategyScoreboard()
    return _scoreboard


# CLI interface
async def scoreboard_cli():
    """Interactive CLI for scoreboard management."""
    scoreboard = get_scoreboard()
    
    print("=== MEV-OG Strategy Scoreboard ===")
    
    while True:
        print("\nOptions:")
        print("1. View leaderboard")
        print("2. View strategy details")
        print("3. Run pruning check")
        print("4. Export metrics")
        print("5. Benchmark strategies")
        print("0. Exit")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "1":
            leaderboard = scoreboard.get_leaderboard()
            print("\n=== Strategy Leaderboard ===")
            print(f"{'Rank':<5} {'Strategy':<20} {'Score':<10} {'Profit':<10} {'Status':<10}")
            print("-" * 65)
            for entry in leaderboard:
                print(f"{entry['rank']:<5} {entry['strategy_id']:<20} "
                      f"{entry['effective_score']:<10.4f} {entry['total_profit_eth']:<10.4f} "
                      f"{entry['status']:<10}")
        
        elif choice == "2":
            strategy_id = input("Enter strategy ID: ").strip()
            if strategy_id in scoreboard.scores:
                score = scoreboard.scores[strategy_id]
                print(f"\n=== {strategy_id} Details ===")
                print(f"Status: {score.status.value}")
                print(f"Success Rate: {score.success_rate:.2%}")
                print(f"Total Profit: {score.total_profit_eth:.4f} ETH")
                print(f"Avg Latency: {score.avg_latency_ms:.2f} ms")
                print(f"Edge Decay: {score.edge_decay_factor:.4f}")
                print(f"Error Rate: {score.error_rate:.2%}")
                
                # Benchmark
                benchmarks = scoreboard.benchmark_against_signals(strategy_id)
                if benchmarks:
                    print("\nSignal Benchmarks:")
                    for source, score in benchmarks.items():
                        print(f"  {source}: {score:.2%}")
            else:
                print("Strategy not found")
        
        elif choice == "3":
            print("\nChecking for pruning candidates...")
            candidates = scoreboard.get_pruning_candidates()
            if candidates:
                print(f"Found {len(candidates)} candidates: {candidates}")
                confirm = input("Create pruning proposal? (y/n): ").lower()
                if confirm == "y":
                    result = await scoreboard.prune_and_score()
                    print(f"Result: {result}")
            else:
                print("No strategies need pruning")
        
        elif choice == "4":
            metrics = scoreboard.export_metrics()
            print("\n=== Metrics Export ===")
            print(json.dumps(metrics, indent=2))
            
            # Save to file
            export_file = Path("export/scoreboard_metrics.json")
            export_file.parent.mkdir(exist_ok=True)
            with open(export_file, "w") as f:
                json.dump(metrics, f, indent=2)
            print(f"\nMetrics saved to {export_file}")
        
        elif choice == "5":
            print("\nBenchmarking all strategies...")
            for strategy_id in scoreboard.scores:
                benchmarks = scoreboard.benchmark_against_signals(strategy_id)
                print(f"\n{strategy_id}:")
                for source, score in benchmarks.items():
                    print(f"  {source}: {score:.2%}")
        
        elif choice == "0":
            break
        
        else:
            print("Invalid option")
    
    print("\nGoodbye!")


if __name__ == "__main__":
    # Run CLI
    asyncio.run(scoreboard_cli())
