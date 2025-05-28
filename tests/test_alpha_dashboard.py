from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core.alpha_dashboard import AlphaDashboard
from agents.capital_lock import CapitalLock
from strategies.cross_domain_arb import PoolConfig, CrossDomainArb


class DummyOrch:
    def __init__(self):
        pools = {"eth": PoolConfig("0xpool", "ethereum")}
        strat = CrossDomainArb(pools, {}, capital_lock=CapitalLock(1000, 1e9, 0))
        self.strategies = {"dummy": strat}

    def status(self):
        return {"active_agents": [0], "pruned_agents": []}


def test_status_data():
    orch = DummyOrch()
    dash = AlphaDashboard(orch)
    data = dash.status_data()
    assert "dummy" in data["strategies"]
    assert data["orchestrator"]["active_agents"] == [0]
