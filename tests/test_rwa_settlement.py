import json
import tempfile
import types
from pathlib import Path
import sys


from strategies.rwa_settlement import RWASettlementMEV, VenueConfig
from agents.capital_lock import CapitalLock
from core.oracles.rwa_feed import RWAData


class DummyFeed:
    def __init__(self, data):
        self.data = data
        self.web3s = {"dex": None, "cex": None}

    def fetch(self, asset, venue):
        return self.data[(venue, asset)]


def setup_strat(threshold=0.01):
    venues = {
        "dex": VenueConfig("dex", "asset"),
        "cex": VenueConfig("cex", "asset"),
    }
    strat = RWASettlementMEV(venues, threshold=threshold, capital_lock=CapitalLock(1000, 1e9, 0))
    return strat


class DummyEth:
    def __init__(self):
        self.block_number = 1


class DummyWeb3:
    def __init__(self):
        self.eth = DummyEth()


def _patch_flashbots(monkeypatch):
    module = types.ModuleType("flashbots")

    class FB:
        def send_bundle(self, bundle, target):
            return {"bundleHash": "hash"}

    def flashbot(w3, account, endpoint_uri=None):
        w3.flashbots = FB()

    module.flashbot = flashbot
    monkeypatch.setitem(sys.modules, "flashbots", module)
    account = types.ModuleType("eth_account")
    class DummyAccount:
        @staticmethod
        def from_key(key):
            return "acct"
    account.Account = DummyAccount
    monkeypatch.setitem(sys.modules, "eth_account", account)
    monkeypatch.delenv("KILL_SWITCH_FLAG_FILE", raising=False)
    monkeypatch.delenv("KILL_SWITCH", raising=False)
    monkeypatch.setattr(
        "strategies.rwa_settlement.strategy.kill_switch_triggered", lambda: False
    )
    account = types.ModuleType("eth_account")
    class DummyAccount:
        @staticmethod
        def from_key(key):
            return "acct"
    account.Account = DummyAccount
    monkeypatch.setitem(sys.modules, "eth_account", account)


def test_opportunity_detection(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat(threshold=0.01)
    feed_data = {
        ("dex", "asset"): RWAData(100, 0.1, 1),
        ("cex", "asset"): RWAData(102, 0.1, 1),
    }
    strat.feed = DummyFeed(feed_data)
    strat.tx_builder.web3 = DummyWeb3()
    strat.nonce_manager.web3 = DummyWeb3()
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result and result["opportunity"]


def test_snapshot_restore(tmp_path):
    strat = setup_strat()
    strat.last_prices = {"dex": 100}
    snap = tmp_path / "snap.json"
    strat.snapshot(snap)
    strat.last_prices = {}
    strat.restore(snap)
    data = json.loads(snap.read_text())
    assert strat.last_prices["dex"] == 100
    assert data["last_prices"]["dex"] == 100


def test_mutate_hook():
    strat = setup_strat()
    strat.mutate({"threshold": 0.02})
    assert strat.threshold == 0.02


def test_kill_switch(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat()
    feed_data = {("dex", "asset"): RWAData(100, 0.1, 1), ("cex", "asset"): RWAData(100, 0.1, 1)}
    strat.feed = DummyFeed(feed_data)
    strat.tx_builder.web3 = DummyWeb3()
    strat.nonce_manager.web3 = DummyWeb3()
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setattr(
        "strategies.rwa_settlement.strategy.kill_switch_triggered", lambda: True
    )
    result = strat.run_once()
    assert result is None
