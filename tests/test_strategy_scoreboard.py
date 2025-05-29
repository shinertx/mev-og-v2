from pathlib import Path

import os
import sys

import pytest
pytest.importorskip("hexbytes")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core.strategy_scoreboard import (
    StrategyScoreboard,
    ExternalSignalFetcher,
    SignalProvider,
)
from ai.mutation_manager import MutationManager
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


class DummyProvider(SignalProvider):
    def __init__(self, value: float):
        self.value = value

    def fetch(self) -> dict:
        return {"news_sentiment": self.value}

def test_scoreboard_decay_prune(tmp_path, monkeypatch):
    signals = tmp_path / "signals.json"
    signals.write_text('{"market_pnl": 0.1, "news_sentiment": 0.1}')
    fetcher = ExternalSignalFetcher(str(signals))
    orch = DummyOrch()
    mm = MutationManager({"threshold": 0.1}, num_agents=1)
    sb = StrategyScoreboard(orch, fetcher, mutator=mm)
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


def test_fetcher_merges_providers(tmp_path):
    signals = tmp_path / "signals.json"
    signals.write_text("{}")
    provider = DummyProvider(0.5)
    fetcher = ExternalSignalFetcher(str(signals), [provider])
    data = fetcher.fetch()
    assert data["news_sentiment"] == 0.5


def test_multisig_blocks_prune(tmp_path, monkeypatch):
    signals = tmp_path / "signals.json"
    signals.write_text('{"market_pnl": 0.1}')
    fetcher = ExternalSignalFetcher(str(signals))
    orch = DummyOrch()
    sb = StrategyScoreboard(orch, fetcher)
    orch.strategies["dummy"].capital_lock.trades.extend([-1.0, -1.0])
    monkeypatch.setenv("FOUNDER_APPROVED", "0")
    res = sb.prune_and_score()
    assert "dummy" in orch.strategies  # blocked
    assert res["pruned"] == []


def test_mutation_trigger_dry_run(tmp_path, monkeypatch):
    signals = tmp_path / "signals.json"
    signals.write_text('{"market_pnl": 0.1}')
    fetcher = ExternalSignalFetcher(str(signals))

    class DummyMut(MutationManager):
        def __init__(self):
            super().__init__({"threshold": 0.1}, 1)
            self.calls = []

        def handle_pruning(self, strategies, dry_run=False):
            self.calls.append((strategies, dry_run))

    mm = DummyMut()
    orch = DummyOrch()
    orch.strategies["dummy"].capital_lock.trades.extend([-1.0, -1.0, -1.0])
    monkeypatch.setenv("FOUNDER_APPROVED", "1")
    monkeypatch.setenv("MUTATION_DRY_RUN", "1")
    sb = StrategyScoreboard(orch, fetcher, mutator=mm)
    sb.prune_and_score()
    assert mm.calls and mm.calls[0][1]

