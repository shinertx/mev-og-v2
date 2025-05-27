import json
import tempfile
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from strategies.nft_liquidation import NFTLiquidationMEV, AuctionConfig
from agents.capital_lock import CapitalLock
from core.oracles.nft_liquidation_feed import AuctionData


class DummyFeed:
    def __init__(self, auctions):
        self.auctions = auctions
        self.web3s = {"ethereum": None}

    def fetch_auctions(self, domain):
        return self.auctions


def setup_strat(discount=0.05):
    auctions = {"proto": AuctionConfig("proto", "ethereum")}
    strat = NFTLiquidationMEV(auctions, discount=discount, capital_lock=CapitalLock(1000, 1e9, 0))
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


def test_detect_sniping(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat(discount=0.05)
    strat.feed = DummyFeed([AuctionData("nft", 90, 100, "1", 1)])
    strat.tx_builder.web3 = DummyWeb3()
    strat.nonce_manager.web3 = DummyWeb3()
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result and result["opportunity"]


def test_snapshot_restore(tmp_path):
    strat = setup_strat()
    strat.last_seen = {"nft": "1"}
    snap = tmp_path / "snap.json"
    strat.snapshot(snap)
    strat.last_seen = {}
    strat.restore(snap)
    data = json.loads(snap.read_text())
    assert strat.last_seen["nft"] == "1"
    assert data["last_seen"]["nft"] == "1"


def test_mutate_hook():
    strat = setup_strat()
    strat.mutate({"discount": 0.1})
    assert strat.discount == 0.1


def test_kill_switch(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat()
    strat.feed = DummyFeed([])
    strat.tx_builder.web3 = DummyWeb3()
    strat.nonce_manager.web3 = DummyWeb3()
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setattr(
        "strategies.nft_liquidation.strategy.kill_switch_triggered", lambda: True
    )
    result = strat.run_once()
    assert result is None
