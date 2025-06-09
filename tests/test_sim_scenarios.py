import importlib
import types

import pytest


class DummyStrat:
    def __init__(self, *a, **k):
        pass

    def run_once(self):
        return {"opportunity": True, "profit_eth": 1.0}


class DummyEth:
    block_number = 20000000


class DummyWeb3:
    class HTTPProvider:
        def __init__(self, *_a, **_k) -> None:
            pass

    def __init__(self, *_a, **_k):
        self.eth = DummyEth()
        self.middleware_onion = types.SimpleNamespace(add=lambda *_a, **_k: None)


SCENARIOS = {
    "sim.scenarios.replay_bridge_arb": ("fork_sim_cross_arb", "CrossDomainArb"),
    "sim.scenarios.sandwich_liquidity_shift": ("fork_sim_cross_rollup_superbot", "CrossRollupSuperbot"),
}


@pytest.mark.parametrize("module_path,harness_name,strat_cls", SCENARIOS.items())
def test_scenarios_run(tmp_path, monkeypatch, module_path, harness_name, strat_cls):
    class DummyMetric:
        def __init__(self, *a, **k):
            pass

        def inc(self, *a, **k):
            pass

        def observe(self, *a, **k):
            pass

    import prometheus_client
    monkeypatch.setattr(prometheus_client, "Counter", DummyMetric, raising=False)
    monkeypatch.setattr(prometheus_client, "Histogram", DummyMetric, raising=False)
    monkeypatch.setattr(prometheus_client, "start_http_server", lambda *_a, **_k: None, raising=False)

    harness = importlib.import_module(f"infra.sim_harness.{harness_name}")
    monkeypatch.setattr(harness, strat_cls, DummyStrat, raising=False)
    monkeypatch.setattr(harness, "Web3", DummyWeb3, raising=False)
    if hasattr(harness, "geth_poa_middleware"):
        monkeypatch.setattr(harness, "geth_poa_middleware", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(harness.time, "sleep", lambda *_a, **_k: None)

    scenario = importlib.import_module(module_path)
    (tmp_path / "logs").mkdir()
    monkeypatch.chdir(tmp_path)
    scenario.main()
    assert (tmp_path / "logs" / "sim_complete.txt").exists()

