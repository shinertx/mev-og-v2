import sys
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core.meta_orchestrator import MetaOrchestrator


class Dummy:
    def __init__(self, threshold=0.1):
        self.threshold = threshold
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
