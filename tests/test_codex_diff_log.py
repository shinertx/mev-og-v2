import json
import sys

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


def test_codex_diff_logging(monkeypatch, tmp_path):
    diff_dir = tmp_path / "diffs"
    monkeypatch.setenv("CODEX_DIFF_DIR", str(diff_dir))

    strat_dir = tmp_path / "strategies" / "foo"
    strat_dir.mkdir(parents=True)
    (strat_dir / "strategy.py").write_text("class Foo:\n    pass\n")

    monkeypatch.setitem(sys.modules, "openai", type("O", (), {"ChatCompletion": FakeChat}))
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    metrics = {"foo": {"pnl": 1}}
    mut = Mutator(metrics, strategy_root=str(tmp_path / "strategies"), live=True)

    for _ in range(4):
        mut.mutate("foo")

    log_file = diff_dir / "foo.json"
    assert log_file.exists()
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert len(entries) == 3
    assert "patch_id" in entries[-1]
    assert "prompt_hash" in entries[-1]
    assert "votes" in entries[-1]
