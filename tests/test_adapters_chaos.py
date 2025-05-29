import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
import importlib.util
import json


import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
    core_stub: Any = ModuleType("core")
    setattr(core_stub, "logger", __import__("core.logger", fromlist=[""]))
    monkeypatch.setitem(sys.modules, "core", core_stub)
    hb: Any = ModuleType("hexbytes")
    setattr(hb, "HexBytes", bytes)
    monkeypatch.setitem(sys.modules, "hexbytes", hb)
    rl: Any = ModuleType("core.rate_limiter")
    class RateLimiter:
        def __init__(self, rate: int) -> None:
            return None

        def wait(self) -> None:
            return None

    setattr(rl, "RateLimiter", RateLimiter)
    monkeypatch.setitem(sys.modules, "core.rate_limiter", rl)
    ss: Any = ModuleType("core.strategy_scoreboard")
    class SignalProvider:
        pass
    setattr(ss, "SignalProvider", SignalProvider)
    monkeypatch.setitem(sys.modules, "core.strategy_scoreboard", ss)
    return tmp_path


def _setup_requests(
    monkeypatch: pytest.MonkeyPatch, success_url: str, data: Any | None = None
) -> None:
    def fake_get(url: str, *a: Any, **k: Any) -> Any:
        if success_url in url:
            return _dummy_response(data or {"ok": True})
        raise RuntimeError("fail")

    def fake_post(url: str, *a: Any, **k: Any) -> Any:
        if success_url in url:
            return _dummy_response(data or {"ok": True})
        raise RuntimeError("fail")

    monkeypatch.setitem(
        sys.modules,
        "requests",
        SimpleNamespace(get=fake_get, post=fake_post),
    )


def test_dex_adapter_fallback(
    monkeypatch: pytest.MonkeyPatch, log_env: Path
) -> None:
    _setup_requests(monkeypatch, "alt", {"ok": True})
    ops = DummyOps()
    DEXAdapter = _load("dex_adapter", "adapters/dex_adapter.py").DEXAdapter
    adapter = DEXAdapter("http://bad", alt_api_url="http://alt", ops_agent=ops)
    data = adapter.get_quote("ETH", "USDC", 1, simulate_failure="network")
    assert data.get("ok") is True
    assert adapter.failures == 0
    
def test_multi_endpoint_fallback(monkeypatch, log_env):
    calls = []

    def fake_get(url, *a, **k):
        calls.append(url)
        if "alt2" in url:
            return _dummy_response({"ok": True})
        raise RuntimeError("fail")

    monkeypatch.setitem(
        sys.modules,
        "requests",
        SimpleNamespace(get=fake_get, post=fake_get),
    )
    ops = DummyOps()
    DEXAdapter = _load("dex_adapter", "adapters/dex_adapter.py").DEXAdapter
    monkeypatch.setattr("random.sample", lambda l, k: l)
    adapter = DEXAdapter(
        "http://bad",
        alt_api_urls=["http://alt1", "http://alt2"],
        ops_agent=ops,
    )
    data = adapter.get_quote("ETH", "USDC", 1, simulate_failure="network")
    assert data.get("ok") is True
    assert any("alt1" in c for c in calls)


def test_cex_adapter_circuit(monkeypatch, log_env):

    _setup_requests(monkeypatch, "alt", {"ok": True})
    ops = DummyOps()
    CEXAdapter = _load("cex_adapter", "adapters/cex_adapter.py").CEXAdapter
    adapter = CEXAdapter(
        "http://bad",
        "k",
        alt_api_url="http://alt",
        ops_agent=ops,
        fail_threshold=1,
    )
    with pytest.raises(RuntimeError):
        adapter.get_balance(simulate_failure="network")
    assert adapter.failures == 1


def test_bridge_adapter_manual(
    monkeypatch: pytest.MonkeyPatch, log_env: Path
) -> None:
    _setup_requests(monkeypatch, "alt", {"ok": True})
    ops = DummyOps()
    BridgeAdapter = _load("bridge_adapter", "adapters/bridge_adapter.py").BridgeAdapter
    adapter = BridgeAdapter("http://bad", alt_api_url="http://alt", ops_agent=ops)
    data = adapter.bridge("eth", "arb", "ETH", 1, simulate_failure="network")
    assert data.get("ok") is True


def test_pool_scanner_downtime(
    monkeypatch: pytest.MonkeyPatch, log_env: Path
) -> None:
    _setup_requests(monkeypatch, "alt", [{"pool": "bad", "domain": "x"}])
    ops = DummyOps()
    PoolScanner = _load("pool_scanner", "adapters/pool_scanner.py").PoolScanner
    scanner = PoolScanner("http://bad", alt_api_url="http://alt", ops_agent=ops)
    pools = scanner.scan(simulate_failure="downtime")
    assert pools and pools[0].pool == "bad"


def test_mempool_monitor_rpc(
    monkeypatch: pytest.MonkeyPatch, log_env: Path
) -> None:
    ops = DummyOps()
    MempoolMonitor = _load("mempool_monitor", "core/mempool_monitor.py").MempoolMonitor
    monitor = MempoolMonitor(None, ops_agent=ops, fail_threshold=1)
    assert monitor.listen_bridge_txs(simulate_failure="rpc") == []


def test_alpha_signal(
    monkeypatch: pytest.MonkeyPatch, log_env: Path
) -> None:
    _setup_requests(monkeypatch, "alt", {"ok": True})
    ops = DummyOps()
    DuneAnalyticsAdapter = _load("alpha_signals", "adapters/alpha_signals.py").DuneAnalyticsAdapter
    WhaleAlertAdapter = _load("alpha_signals", "adapters/alpha_signals.py").WhaleAlertAdapter
    dune = DuneAnalyticsAdapter(
        "http://bad",
        "k",
        "q",
        alt_api_url="http://alt",
        ops_agent=ops,
    )
    data = dune.fetch(simulate_failure="network")
    assert data == {}
    whale = WhaleAlertAdapter(
        "http://bad",
        "k",
        alt_api_url="http://alt",
        ops_agent=ops,
    )
    data2 = whale.fetch(simulate_failure="network")
    assert data2 == {"whale_flow": 0.0}


def test_chaos_scheduler(monkeypatch, tmp_path, log_env):
    _setup_requests(monkeypatch, "alt")
    scheduler = _load("chaos_scheduler", "infra/sim_harness/chaos_scheduler.py")
    monkeypatch.setenv("CHAOS_ADAPTERS", "dex")
    monkeypatch.setenv("CHAOS_MODES", "network")
    monkeypatch.setenv("CHAOS_SCHED_LOG", str(tmp_path / "sched.json"))
    monkeypatch.setenv("CHAOS_METRICS", str(tmp_path / "metrics.json"))
    scheduler.run_once()
    metrics = json.loads(Path(tmp_path / "metrics.json").read_text())
    assert metrics["dex"]["failures"] >= 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", default="")
    args = parser.parse_args()
    if args.simulate == "bridge_downtime":
        BridgeAdapter = _load("bridge_adapter", "adapters/bridge_adapter.py").BridgeAdapter
        BridgeAdapter("http://x").bridge("e", "a", "T", 1, simulate_failure="downtime")
    elif args.simulate:
        print("unknown simulation")

