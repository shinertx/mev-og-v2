from pathlib import Path
import os
import sys

import pytest
pytest.importorskip("hexbytes")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core.strategy_scoreboard import StrategyScoreboard, ExternalSignalFetcher
from agents.capital_lock import CapitalLock
from strategies.cross_domain_arb import PoolConfig, CrossDomainArb


class DummyOps:
    def __init__(self):
        self.notifications = []

    def notify(self, msg: str) -> None:
        self.notifications.append(msg)


class DummyOrch:
    def __init__(self):
        pools = {
            "eth": PoolConfig("0xdeadbeef00000000000000000000000000000000", "ethereum")
        }
        strat = CrossDomainArb(pools, {}, capital_lock=CapitalLock(1000, 1e9, 0))
        strat.capital_lock.trades = [1.0, -0.5, 0.2]
        self.strategies = {"dummy": strat}
        self.ops_agent = DummyOps()

    def status(self):
        return {}


def test_scoreboard_decay_prune(tmp_path, monkeypatch):
    signals = tmp_path / "signals.json"
    signals.write_text('{"market_pnl": 0.1, "news_sentiment": 0.1}')
    fetcher = ExternalSignalFetcher(str(signals))
    orch = DummyOrch()
    sb = StrategyScoreboard(orch, fetcher)
    sb.prune_and_score()  # initial run
    assert "dummy" in orch.strategies
    orch.strategies["dummy"].capital_lock.trades.extend([-1.0, -1.0, -1.0])
    monkeypatch.setenv("FOUNDER_APPROVED", "1")
    res = sb.prune_and_score()
    assert "dummy" not in orch.strategies
    assert "dummy" in res["pruned"]
    assert orch.ops_agent.notifications


def test_scoreboard_no_false_positive(tmp_path):
    signals = tmp_path / "signals.json"
    signals.write_text('{"market_pnl": 0.0}')
    fetcher = ExternalSignalFetcher(str(signals))
    orch = DummyOrch()
    sb = StrategyScoreboard(orch, fetcher)
    res = sb.prune_and_score()
    assert res["pruned"] == []
    assert Path("logs/scoreboard.json").exists()

