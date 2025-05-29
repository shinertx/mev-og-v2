from pathlib import Path
import sys

import pytest
pytest.importorskip("hexbytes")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core.strategy_scoreboard import StrategyScoreboard, ExternalSignalFetcher
from agents.capital_lock import CapitalLock
from strategies.cross_domain_arb import PoolConfig, CrossDomainArb


class DummyOrch:
    def __init__(self):
        pools = {
            "eth": PoolConfig("0xdeadbeef00000000000000000000000000000000", "ethereum")
        }
        strat = CrossDomainArb(pools, {}, capital_lock=CapitalLock(1000, 1e9, 0))
        strat.capital_lock.trades = [1.0, -0.5, 0.2]
        self.strategies = {"dummy": strat}

    def status(self):
        return {}


def test_scoreboard_collect_and_prune(tmp_path):
    signals = tmp_path / "signals.json"
    signals.write_text('{"market_pnl": 0.3}')
    fetcher = ExternalSignalFetcher(str(signals))
    sb = StrategyScoreboard(DummyOrch(), fetcher)
    metrics = sb.collect_metrics()
    assert metrics["dummy"]["realized_pnl"] != 0
    res = sb.prune_and_score()
    assert "scores" in res
    assert Path("logs/scoreboard.json").exists()

