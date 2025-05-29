import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from ai.mutator.mutator import Mutator


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeResp:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": FakeMsg(text)})]


class FakeChat:
    @staticmethod
    def create(model, messages):
        return FakeResp('{"params": {"threshold": 0.1}}')


def test_mutator_llm(monkeypatch, tmp_path):
    strat_dir = tmp_path / "strategies" / "foo"
    strat_dir.mkdir(parents=True)
    (strat_dir / "strategy.py").write_text("class Foo:\n    pass\n")

    monkeypatch.setitem(
        sys.modules, "openai", type("O", (), {"ChatCompletion": FakeChat})
    )
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    metrics = {"foo": {"pnl": 1}}
    mut = Mutator(metrics, live=True, strategy_root=str(tmp_path / "strategies"))
    out = mut.mutate("foo", {"threshold": 0.05})
    assert out == {"threshold": 0.1}
