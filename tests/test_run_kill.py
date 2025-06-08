import asyncio
import importlib
from typing import Any

import pytest

pytest.importorskip("strategies.cross_domain_arb.strategy")


def _setup_failure(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Patch strategy to raise a runtime error."""
    mod = importlib.import_module("strategies.cross_domain_arb.strategy")

    class Dummy(mod.CrossDomainArb):
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - stub
            pass

        def run_once(self) -> None:  # pragma: no cover - stub
            raise RuntimeError("fail")

    monkeypatch.setattr(mod, "CrossDomainArb", Dummy)
    monkeypatch.setenv("ARB_ERROR_LIMIT", "0")
    monkeypatch.setenv("ARB_LATENCY_THRESHOLD", "100")
    return mod


def test_run_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _setup_failure(monkeypatch)
    called: list[str] = []
    monkeypatch.setattr(mod, "record_kill_event", lambda origin: called.append(origin))

    with pytest.raises(SystemExit) as se:
        asyncio.run(mod.run(test_mode=True))

    assert se.value.code == 137
    assert called and called[0] == mod.STRATEGY_ID


def test_run_kill_error_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _setup_failure(monkeypatch)
    called: list[str] = []
    monkeypatch.setattr(mod, "record_kill_event", lambda origin: called.append(origin))

    inc_calls: list[int] = []

    class Counter:
        def inc(self) -> None:  # pragma: no cover - stub
            inc_calls.append(1)

    monkeypatch.setattr(mod, "arb_error_count", Counter())

    with pytest.raises(SystemExit):
        asyncio.run(mod.run(test_mode=True))

    assert called and called[0] == mod.STRATEGY_ID
    assert inc_calls and len(inc_calls) == 1
