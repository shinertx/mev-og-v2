import os
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from strategies.nft_liquidation import NFTLiquidationMEV, AuctionConfig
from core.oracles.nft_liquidation_feed import AuctionData


class DummyFeed:
    def __init__(self, auctions):
        self.auctions = auctions
        self.web3s = {"ethereum": None}

    def fetch_auctions(self, domain):
        return self.auctions


def setup_strat(discount=0.05):
    auctions = {"proto": AuctionConfig("proto", "ethereum")}
    strat = NFTLiquidationMEV(auctions, discount=discount)
    return strat


def test_detect_sniping():
    strat = setup_strat(discount=0.05)
    strat.feed = DummyFeed([AuctionData("nft", 90, 100, "1", 1)])
    strat.tx_builder.web3 = None
    strat.nonce_manager.web3 = None
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
    strat = setup_strat()
    strat.feed = DummyFeed([])
    strat.tx_builder.web3 = None
    strat.nonce_manager.web3 = None
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setattr(
        "strategies.nft_liquidation.strategy.kill_switch_triggered", lambda: True
    )
    result = strat.run_once()
    assert result is None
