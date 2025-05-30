

from core.meta_orchestrator import MetaOrchestrator


class Dummy:
    def __init__(self, **kwargs):
        self.threshold = kwargs.get("threshold", 0.1)
        self.capital_lock = type("L", (), {"trades": [1.0]})()
        self.pools = {}
        self.edges_enabled = {"stealth_mode": False}

    def run_once(self):
        pass

    def evaluate_pnl(self):
        return self.threshold


def test_meta_cycle():
    orch = MetaOrchestrator(Dummy, {"threshold": 0.1}, num_agents=2)
    orch.run_cycle()
    st = orch.status()
    assert st["active_agents"]
