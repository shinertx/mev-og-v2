"""Tests for the mutation cycle orchestrator."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

import ai.mutator.main as mut_main


def test_mutation_cycle(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "good.json").write_text(json.dumps({"opportunity": True, "spread": 1.0}) + "\n")
    (logs / "bad.json").write_text(json.dumps({"error": "fail"}) + "\n")

    strat_dir = tmp_path / "strategies" / "good"
    strat_dir.mkdir(parents=True)
    (strat_dir / "__init__.py").write_text("")
    (strat_dir / "strategy.py").write_text(
        "class Good:\n" "    def __init__(self, pools=None):\n        pass\n" "    def mutate(self, params):\n        pass\n"
    )
    sys.path.insert(0, str(tmp_path))

    monkeypatch.setenv("ERROR_LOG_FILE", str(logs / "errors.log"))
    monkeypatch.setenv("FOUNDER_APPROVED", "1")
    monkeypatch.setenv("TRACE_ID", "okid")

    monkeypatch.setattr(mut_main.AuditAgent, "run_online_audit", lambda self, prompt: "ok")

    def fake_run(cmd, check, capture_output=True, text=True):
        class R:
            stderr = ""
        return R()

    monkeypatch.setattr(mut_main.subprocess, "run", fake_run)

    promos = []

    def fake_promote(src, dst, approved, evidence=None, trace_id=None):
        promos.append((src, dst, approved, trace_id))
        return True

    monkeypatch.setattr(mut_main, "promote_strategy", fake_promote)

    runner = mut_main.MutationRunner(repo_root=str(tmp_path), logs_dir=str(logs))
    runner.run_cycle()

    assert promos
    assert (logs / "errors.log").exists()


def test_mutation_cycle_requires_founder(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "good.json").write_text("{}\n")

    strat_dir = tmp_path / "strategies" / "good"
    strat_dir.mkdir(parents=True)
    (strat_dir / "__init__.py").write_text("")
    (strat_dir / "strategy.py").write_text("class Good:\n    pass\n")
    sys.path.insert(0, str(tmp_path))

    monkeypatch.setenv("ERROR_LOG_FILE", str(logs / "errors.log"))
    monkeypatch.setenv("FOUNDER_APPROVED", "0")
    monkeypatch.setenv("TRACE_ID", "block")

    monkeypatch.setattr(mut_main.AuditAgent, "run_online_audit", lambda self, p: "ok")
    monkeypatch.setattr(mut_main.subprocess, "run", lambda *a, **k: None)

    promos = []

    def fake_promote(src, dst, approved, evidence=None, trace_id=None):
        promos.append((src, dst, approved, trace_id))
        return True

    monkeypatch.setattr(mut_main, "promote_strategy", fake_promote)

    runner = mut_main.MutationRunner(repo_root=str(tmp_path), logs_dir=str(logs))
    runner.run_cycle()

    assert not promos
    entries = [json.loads(line) for line in (logs / "errors.log").read_text().splitlines()]
    assert entries[-1]["event"] == "promote_gate"
    assert entries[-1]["trace_id"] == "block"
