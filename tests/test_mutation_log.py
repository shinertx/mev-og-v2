import json


from ai.mutation_manager import MutationManager


class Dummy:
    def __init__(self, threshold=0.1):
        self.threshold = threshold
    def evaluate_pnl(self):
        return self.threshold


def test_mutation_logging(tmp_path, monkeypatch):
    log = tmp_path / "mutation_log.json"
    monkeypatch.setenv("MUTATION_LOG", str(log))
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    import importlib
    import ai.mutation_log
    importlib.reload(ai.mutation_log)
    mm = MutationManager({"threshold": 0.1}, num_agents=2)
    mm.spawn_agents(Dummy)
    mm.score_and_prune()
    assert log.exists()
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(e["event"].startswith("spawn") for e in entries)
