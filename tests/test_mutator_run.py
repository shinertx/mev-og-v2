import json

from ai.mutator.mutator import Mutator


def test_mutator_run_test_mode(tmp_path, monkeypatch):
    metrics = {"foo": {"pnl": 1.0}}
    mut = Mutator(metrics)
    monkeypatch.chdir(tmp_path)
    out = mut.run(block_number=123, chain_id=5, test_mode=True)
    assert out["scores"]
    summary = tmp_path / "telemetry" / "strategies" / "mutation_summary.json"
    data = json.loads(summary.read_text())
    assert data["block_number"] == 123
    assert data["chain_id"] == 5
