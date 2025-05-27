import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from agents.ops_agent import OpsAgent
from core.logger import register_hook


def test_ops_health_fail(monkeypatch):
    checks = {"a": lambda: True, "b": lambda: False}
    agent = OpsAgent(checks)
    captured = []
    register_hook(lambda e: captured.append(e))
    agent.run_checks()
    assert any(e["event"] == "auto_pause" for e in captured)

