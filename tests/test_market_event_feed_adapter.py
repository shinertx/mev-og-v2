import json
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, List

import pytest

BASE = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "market_event_feed_adapter", BASE / "adapters" / "market_event_feed_adapter.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("spec fail")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["market_event_feed_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


def _dummy_response(data: Any) -> Any:
    class Resp:
        def __init__(self, d: Any) -> None:
            self._d = d

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Any:
            return self._d

    return Resp(data)


@pytest.fixture
def dummy_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *a: Any, **k: Any) -> Any:
        if "fail" in url:
            raise RuntimeError("fail")
        return _dummy_response([{"pair": "XYZ"}])

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))


def test_poll_and_subscribe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dummy_requests: None) -> None:
    mod = _load()
    got: List[mod.MarketEvent] = []
    adapter = mod.MarketEventFeedAdapter(dex_urls=["http://dex"], cex_urls=["http://cex"])
    adapter.subscribe(got.append)
    events = adapter.poll()
    assert events
    assert got


def test_error_triggers_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()

    def fail_get(url: str, *a: Any, **k: Any) -> Any:
        raise RuntimeError("fail")

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fail_get))
    adapter = mod.MarketEventFeedAdapter(dex_urls=["http://fail"], fail_threshold=1)
    with pytest.raises(RuntimeError):
        adapter.poll()


def test_sim_events_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    events = [
        {"source": "dex", "event_type": "dex_listing", "data": {"pair": "ABC"}}
    ]
    p = tmp_path / "events.json"
    p.write_text(json.dumps(events))
    monkeypatch.setenv("SIM_MARKET_EVENTS", str(p))
    adapter = mod.MarketEventFeedAdapter()
    evts = adapter.poll()
    assert evts and evts[0].data["pair"] == "ABC"


def test_snapshot_called(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    called = []

    def fail_get(url: str, *a: Any, **k: Any) -> Any:
        raise RuntimeError("fail")

    def snap(self: Any) -> None:
        called.append(True)

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fail_get))
    monkeypatch.setattr(mod.MarketEventFeedAdapter, "_export_snapshot", snap)
    adapter = mod.MarketEventFeedAdapter(dex_urls=["http://fail"], fail_threshold=1)
    with pytest.raises(RuntimeError):
        adapter.poll()
    assert called
