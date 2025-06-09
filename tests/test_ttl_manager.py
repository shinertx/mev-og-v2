import asyncio
import os
import time
import importlib.util
import sys
from pathlib import Path

from orchestrator_ttl import StrategyTTLManager
from core.orchestrator import StrategyOrchestrator


def _make_ttl_strategy(base: Path, name: str, ttl_hours: int, age_hours: float = 0.0) -> None:
    strat_dir = base / "strategies" / name
    strat_dir.mkdir(parents=True)
    doc = f"""\nstrategy_id: '{name}'\nedge_type: test\nttl_hours: {ttl_hours}\n"""
    (strat_dir / "__init__.py").write_text(f"from .strategy import {name.capitalize()}\n__all__=['{name.capitalize()}']")
    (strat_dir / "strategy.py").write_text(
        doc + f"class {name.capitalize()}:\n    def __init__(self, **kw):\n        self.ran=False\n    def run_once(self):\n        self.ran=True\n"
    )
    ts = time.time() - age_hours * 3600
    os.utime(strat_dir / "strategy.py", (ts, ts))
    import strategies
    from pkgutil import extend_path

    strategies.__path__ = extend_path(strategies.__path__, str(base / "strategies"))
    spec = importlib.util.spec_from_file_location(f"strategies.{name}.strategy", strat_dir / "strategy.py")
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"strategies.{name}.strategy"] = mod
        spec.loader.exec_module(mod)


def _config(base: Path, names: list[str]) -> Path:
    cfg = base / "config.yaml"
    enabled = "[" + ",".join(f'\"{n}\"' for n in names) + "]"
    params = "\n  ".join(f"{n}: {{}}" for n in names)
    cfg.write_text(
        """
mode: test
wallet_address: 0x0
alpha:
  enabled: %s
  params:
    %s
risk:
  max_drawdown_pct: 5
  max_loss_usd: 100
starting_capital: 1000
capital_lock_enabled: true
kill_switch_enabled: true
""" % (enabled, params)
    )
    return cfg


def test_ttl_manager_prunes(tmp_path):
    p_old = tmp_path / "old.py"
    p_old.write_text('"""\nttl_hours: 1\n"""')
    old_ts = time.time() - 7200
    os.utime(p_old, (old_ts, old_ts))
    p_new = tmp_path / "new.py"
    p_new.write_text('"""\nttl_hours: 10\n"""')
    mgr = StrategyTTLManager()
    active = asyncio.run(mgr.enforce_all_ttls([p_old, p_new]))
    assert p_old not in active
    assert p_new in active


def test_orchestrator_filters_expired(tmp_path):
    _make_ttl_strategy(tmp_path, "old", 1, age_hours=2)
    _make_ttl_strategy(tmp_path, "fresh", 1, age_hours=0)
    cfg = _config(tmp_path, ["old", "fresh"])
    orch = StrategyOrchestrator(str(cfg))
    assert "old" not in orch.strategies
    assert "fresh" in orch.strategies

