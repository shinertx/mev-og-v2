import json
import importlib.util
import sys
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


class DummyOps:
    msgs: list[str]

    def __init__(self) -> None:
        self.msgs = []

    def notify(self, msg: str) -> None:
        self.msgs.append(msg)


BASE = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, BASE / rel)
    if spec is None or spec.loader is None:
        raise AssertionError("module spec missing")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _dummy_response(data: Any | None = None) -> Any:
    class Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Any:
            return data or {}

    return Resp()


@pytest.fixture
def log_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ERROR_LOG_FILE", str(tmp_path / "errors.log"))
    monkeypatch.setenv("FLASHLOAN_ADAPTER_LOG", str(tmp_path / "flash.json"))
    return tmp_path


def _setup_requests(monkeypatch: pytest.MonkeyPatch, success_url: str, data: Any | None = None) -> None:
    def fake_post(url: str, *a: Any, **k: Any) -> Any:
        if success_url in url:
            return _dummy_response(data or {"ok": True})
        raise RuntimeError("fail")

    monkeypatch.setitem(
        sys.modules,
        "requests",
        SimpleNamespace(post=fake_post),
    )


def test_fallback_success(monkeypatch: pytest.MonkeyPatch, log_env: Path) -> None:
    _setup_requests(monkeypatch, "alt", {"ok": True})
    FlashloanAdapter = _load("flashloan_adapter", "adapters/flashloan_adapter.py").FlashloanAdapter
    ops = DummyOps()
    adapter = FlashloanAdapter("http://bad", alt_api_url="http://alt", ops_agent=ops)
    data = adapter.trigger("ETH", 1.0, simulate_failure="network")
    assert data.get("ok") is True
    assert adapter.failures == 0
    entries = [json.loads(line) for line in (log_env / "flash.json").read_text().splitlines()]
    assert any(e["event"] == "fallback_success" for e in entries)


def test_rpc_error(monkeypatch: pytest.MonkeyPatch, log_env: Path) -> None:
    _setup_requests(monkeypatch, "alt", {"ok": True})
    FlashloanAdapter = _load("flashloan_adapter", "adapters/flashloan_adapter.py").FlashloanAdapter
    ops = DummyOps()
    adapter = FlashloanAdapter("http://bad", alt_api_url="http://alt", ops_agent=ops)
    data = adapter.trigger("ETH", 1.0, simulate_failure="rpc")
    assert data.get("ok") is True
    assert adapter.failures == 0


def test_ops_critical_and_circuit(monkeypatch: pytest.MonkeyPatch, log_env: Path) -> None:
    monkeypatch.delenv("OPS_CRITICAL_EVENT", raising=False)
    _setup_requests(monkeypatch, "none")
    FlashloanAdapter = _load("flashloan_adapter", "adapters/flashloan_adapter.py").FlashloanAdapter
    ops = DummyOps()
    adapter = FlashloanAdapter("http://bad", alt_api_url="http://alt", ops_agent=ops, fail_threshold=3)
    with pytest.raises(RuntimeError):
        adapter.trigger("ETH", 1.0, simulate_failure="network")
    assert os.getenv("OPS_CRITICAL_EVENT") == "1"
    assert adapter.failures == 2
    with pytest.raises(RuntimeError):
        adapter.trigger("ETH", 1.0, simulate_failure="network")
    assert adapter.failures >= 3


def test_kill_switch(monkeypatch: pytest.MonkeyPatch, log_env: Path) -> None:
    FlashloanAdapter = _load("flashloan_adapter", "adapters/flashloan_adapter.py").FlashloanAdapter
    called: list[str] = []
    monkeypatch.setattr("adapters.flashloan_adapter.kill_switch_triggered", lambda: True)
    monkeypatch.setattr(
        "adapters.flashloan_adapter.record_kill_event", lambda origin: called.append(origin)
    )
    adapter = FlashloanAdapter("http://bad")
    with pytest.raises(RuntimeError):
        adapter.trigger("ETH", 1.0)
    assert called and called[0] == "flashloan_adapter.trigger"

