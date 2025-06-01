import importlib.util
import sys


from core.orchestrator import StrategyOrchestrator


def _make_dummy_strategy(tmp_path):
    strat_dir = tmp_path / "strategies" / "dummy"
    strat_dir.mkdir(parents=True)
    (strat_dir / "__init__.py").write_text("from .strategy import Dummy\n__all__=['Dummy']")
    (strat_dir / "strategy.py").write_text(
        "class Dummy:\n" \
        "    def __init__(self, **kw):\n        self.runs=0\n" \
        "    def run_once(self):\n        self.runs+=1\n"
    )
    import strategies
    from pkgutil import extend_path
    strategies.__path__ = extend_path(
        strategies.__path__, str(tmp_path / "strategies")
    )
    spec = importlib.util.spec_from_file_location(
        "strategies.dummy.strategy", strat_dir / "strategy.py"
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["strategies.dummy.strategy"] = mod
        spec.loader.exec_module(mod)


def _config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
mode: test
wallet_address: 0x0
alpha:
  enabled: [\"dummy\"]
  params:
    dummy: {}
risk:
  max_drawdown_pct: 5
  max_loss_usd: 100
starting_capital: 1000
capital_lock_enabled: true
kill_switch_enabled: true
"""
    )
    return cfg


def test_boot_and_parse(tmp_path):
    _make_dummy_strategy(tmp_path)
    cfg = _config(tmp_path)
    orch = StrategyOrchestrator(str(cfg))
    assert "dummy" in orch.strategies


def test_kill_switch_gating(monkeypatch, tmp_path):
    _make_dummy_strategy(tmp_path)
    cfg = _config(tmp_path)
    orch = StrategyOrchestrator(str(cfg))
    monkeypatch.setattr("core.orchestrator.kill_switch_triggered", lambda: True)
    monkeypatch.setattr("core.orchestrator.record_kill_event", lambda *a, **k: None)
    assert orch.run_once() is False


def test_ops_health_fail(monkeypatch, tmp_path):
    _make_dummy_strategy(tmp_path)
    cfg = _config(tmp_path)
    orch = StrategyOrchestrator(str(cfg))
    monkeypatch.setattr(orch.ops_agent, "run_checks", lambda: orch.ops_agent.auto_pause("x"))
    assert orch.run_once() is False


def test_dry_run_snapshot(monkeypatch, tmp_path):
    _make_dummy_strategy(tmp_path)
    cfg = _config(tmp_path)
    orch = StrategyOrchestrator(str(cfg), dry_run=True)
    calls = []

    def fake_run(cmd, check, capture_output=True, text=True):
        calls.append(cmd)
        class R:
            stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("core.tx_engine.kill_switch.kill_switch_triggered", lambda: False)
    monkeypatch.delenv("OPS_CRITICAL_EVENT", raising=False)
    assert orch.run_once()
    assert any("--dry-run" in c for c in calls[0])


def test_drp_partial_failure(monkeypatch, tmp_path):
    _make_dummy_strategy(tmp_path)
    cfg = _config(tmp_path)
    orch = StrategyOrchestrator(str(cfg))
    monkeypatch.delenv("OPS_CRITICAL_EVENT", raising=False)
    monkeypatch.setattr(
        "core.orchestrator.StrategyOrchestrator._snapshot_state", lambda self: False
    )
    assert orch.run_once()
    assert orch.drp_agent.ready is False
    monkeypatch.setattr(
        "core.orchestrator.StrategyOrchestrator._snapshot_state", lambda self: True
    )
    assert orch.run_once() is False


def test_live_loop(monkeypatch, tmp_path):
    _make_dummy_strategy(tmp_path)
    cfg = _config(tmp_path)
    orch = StrategyOrchestrator(str(cfg), dry_run=False)
    count = 0
    def fake_run_once():
        nonlocal count
        count += 1
        return count < 3
    orch.run_once = fake_run_once
    orch.run_live_loop(interval=0)
    assert count == 3
