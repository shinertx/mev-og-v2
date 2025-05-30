import pytest
pytest.importorskip("hexbytes")

from core.alpha_dashboard import AlphaDashboard
from agents.capital_lock import CapitalLock
from strategies.cross_domain_arb import PoolConfig, CrossDomainArb


class DummyOrch:
    def __init__(self):
        pools = {
            "eth": PoolConfig(
                "0xdeadbeef00000000000000000000000000000000", "ethereum"
            )  # test-only
        }
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
