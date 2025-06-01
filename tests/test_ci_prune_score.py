
from ai.mutation_manager import MutationManager

class Dummy:
    def __init__(self, threshold: float = 0.1) -> None:
        self.t = threshold

    def evaluate_pnl(self) -> float:
        return self.t

def test_batch_pruning_runs() -> None:
    mm = MutationManager({'threshold': 0.1}, num_agents=3)
    mm.spawn_agents(Dummy)
    before = len(mm.agents)
    mm.score_and_prune()
    after = len(mm.agents)
    assert after <= before
