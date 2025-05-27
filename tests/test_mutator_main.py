"""Tests for the mutation cycle orchestrator."""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json

from pathlib import Path


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

    monkeypatch.setattr(mut_main.AuditAgent, "run_online_audit", lambda self, prompt: "ok")

    def fake_run(cmd, check, capture_output=True, text=True):
        class R:
            stderr = ""
        return R()

    monkeypatch.setattr(mut_main.subprocess, "run", fake_run)

    promos = []

    def fake_promote(src, dst, approved, evidence=None):
        promos.append((src, dst, approved))
        return True

    monkeypatch.setattr(mut_main, "promote_strategy", fake_promote)

    runner = mut_main.MutationRunner(repo_root=str(tmp_path), logs_dir=str(logs))
    runner.run_cycle()

    assert promos
    assert (logs / "errors.log").exists()
