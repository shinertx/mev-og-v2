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
    class HTTPProvider:  # pragma: no cover - dummy
        def __init__(self, *_a, **_k) -> None:
            pass

    def __init__(self, *_a, **_k):
        self.eth = DummyEth()
        self.middleware_onion = types.SimpleNamespace(add=lambda *_a, **_k: None)


HARNESS = {
    "infra.sim_harness.fork_sim_cross_rollup_superbot": "CrossRollupSuperbot",
    "infra.sim_harness.fork_sim_l3_app_rollup_mev": "L3AppRollupMEV",
    "infra.sim_harness.fork_sim_l3_sequencer_mev": "L3SequencerMEV",
    "infra.sim_harness.fork_sim_nft_liquidation": "NFTLiquidationMEV",
    "infra.sim_harness.fork_sim_rwa_settlement": "RWASettlementMEV",
}


@pytest.mark.parametrize("module_path,strat_cls", HARNESS.items())
def test_harness_runs(tmp_path, monkeypatch, module_path, strat_cls):
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
    module = importlib.import_module(module_path)
    monkeypatch.setattr(module, strat_cls, DummyStrat, raising=False)
    monkeypatch.setattr(module, "Web3", DummyWeb3, raising=False)
    if hasattr(module, "geth_poa_middleware"):
        monkeypatch.setattr(module, "geth_poa_middleware", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(module.time, "sleep", lambda *_a, **_k: None)
    (tmp_path / "logs").mkdir()
    monkeypatch.chdir(tmp_path)
    module.main()
    assert (tmp_path / "logs" / "sim_complete.txt").exists()
