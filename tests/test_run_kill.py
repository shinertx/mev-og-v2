import importlib
import pytest

pytest.importorskip("strategies.cross_domain_arb.strategy")


@pytest.mark.asyncio
async def test_run_kill(monkeypatch):
    mod = importlib.import_module("strategies.cross_domain_arb.strategy")

    class Dummy(mod.CrossDomainArb):
        def run_once(self):
            raise RuntimeError("fail")

    monkeypatch.setattr(mod, "CrossDomainArb", Dummy)
    monkeypatch.setenv("ARB_ERROR_LIMIT", "0")
    monkeypatch.setenv("ARB_LATENCY_THRESHOLD", "100")

    called = []
    monkeypatch.setattr(mod, "record_kill_event", lambda origin: called.append(origin))

    with pytest.raises(SystemExit) as se:
        await mod.run(test_mode=True)

    assert se.value.code == 137
    assert called and called[0] == mod.STRATEGY_ID


