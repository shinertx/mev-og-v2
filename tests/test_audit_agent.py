"""Unit tests for the AuditAgent logic and online audit path."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
from pathlib import Path

from ai.audit_agent import AuditAgent
from core.logger import StructuredLogger


def test_audit_summary(tmp_path):
    log_file = tmp_path / "strategy.json"
    logger = StructuredLogger("test_strategy", log_file=str(log_file))
    logger.log("run", error=None)
    logger.log("fail", error="oops")

    agent = AuditAgent(repo_root=str(Path(__file__).resolve().parents[1]))
    summary = agent.run_audit([str(log_file)])
    assert summary["failures"] == 1
    suggestions = agent.suggest_mutations(summary)
    assert suggestions


def test_run_online_audit(monkeypatch):
    responses = []

    class FakeMsg:
        def __init__(self, content):
            self.content = content

    class FakeResp:
        def __init__(self, text):
            self.choices = [type("C", (), {"message": FakeMsg(text)})]

    class FakeChat:
        @staticmethod
        def create(model, messages):
            responses.append((model, messages))
            return FakeResp("ok")

    monkeypatch.setitem(sys.modules, "openai", type("O", (), {"ChatCompletion": FakeChat}))
    monkeypatch.setenv("OPENAI_API_KEY", "x")

    agent = AuditAgent()
    out = agent.run_online_audit("hi")
    assert out == "ok"
    assert responses

