from pathlib import Path

from core.strategy_base import BaseStrategy


class Dummy(BaseStrategy):
    def __init__(self, prune_epochs: int = 2) -> None:
        super().__init__("dummy", prune_epochs=prune_epochs)

    def detect_alpha(self):
        return None

    def execute_trade(self, signal):
        return None


def test_auto_prune(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    strat = Dummy(prune_epochs=2)
    strat.record_result(False, -1.0)
    assert not strat.disabled
    strat.record_result(False, -1.0)
    assert strat.disabled
    log_file = Path("logs/prune.log")
    assert log_file.exists()
