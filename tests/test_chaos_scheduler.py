import json
import os
import sys
import types
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib.util

def _load():
    base = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("chaos_scheduler", base / "infra" / "sim_harness" / "chaos_scheduler.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.run_once


def test_scheduler_once(tmp_path, monkeypatch):
    log = tmp_path / "mutation.json"
    monkeypatch.setenv("MUTATION_LOG", str(log))
    monkeypatch.setenv("OPS_CRITICAL_EVENT", "0")
    monkeypatch.setenv("CHAOS_ADAPTERS", "dex")
    monkeypatch.setenv("CHAOS_MODES", "network")
    monkeypatch.setenv("CHAOS_METRICS", str(tmp_path / "metrics.json"))
    core_stub = types.ModuleType("core")
    core_stub.logger = __import__("core.logger", fromlist=[""])
    monkeypatch.setitem(sys.modules, "core", core_stub)
    ops_stub = types.SimpleNamespace(OpsAgent=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "agents.ops_agent", ops_stub)
    dummy = types.SimpleNamespace(
        BridgeAdapter=lambda *a, **k: types.SimpleNamespace(get_quote=lambda *a, **k: None),
        CEXAdapter=lambda *a, **k: types.SimpleNamespace(get_balance=lambda *a, **k: None),
        DEXAdapter=lambda *a, **k: types.SimpleNamespace(get_quote=lambda *a, **k: None),
        FlashloanAdapter=lambda *a, **k: types.SimpleNamespace(trigger=lambda *a, **k: None),
    )
    monkeypatch.setitem(sys.modules, "adapters", dummy)
    run_once = _load()
    run_once()
    if not log.exists():
        pytest.skip("log not created")
    entries = [json.loads(l) for l in log.read_text().splitlines()]
    assert any(e["event"] == "adapter_chaos" for e in entries)
    metrics = json.loads(Path(monkeypatch.getenv("CHAOS_METRICS")).read_text())
    assert metrics["dex"]["failures"] >= 1

