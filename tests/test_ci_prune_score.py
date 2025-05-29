import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from ai.mutation_manager import MutationManager

class Dummy:
    def __init__(self, threshold=0.1):
        self.t = threshold
    def evaluate_pnl(self):
        return self.t

def test_batch_pruning_runs():
    mm = MutationManager({'threshold': 0.1}, num_agents=3)
    mm.spawn_agents(Dummy)
    before = len(mm.agents)
    mm.score_and_prune()
    after = len(mm.agents)
    assert after <= before
