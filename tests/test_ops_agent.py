import sys


from agents.ops_agent import OpsAgent
from core.logger import register_hook


def test_ops_health_fail(monkeypatch):
    checks = {"a": lambda: True, "b": lambda: False}
    agent = OpsAgent(checks)
    captured = []
    register_hook(lambda e: captured.append(e))
    agent.run_checks()
    assert any(e["event"] == "auto_pause" for e in captured)


def test_notify_fail(monkeypatch):
    agent = OpsAgent({})
    captured = []
    register_hook(lambda e: captured.append(e))
    monkeypatch.setenv("OPS_ALERT_WEBHOOK", "http://x")

    class DummyReq:
        def post(self, *a, **k):
            raise RuntimeError("fail")

    monkeypatch.setitem(sys.modules, "requests", DummyReq())
    agent.notify("hi")
    assert any(e["event"] == "notify_fail" for e in captured)

