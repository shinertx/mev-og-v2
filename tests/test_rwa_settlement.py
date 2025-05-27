import os
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from strategies.rwa_settlement import RWASettlementMEV, VenueConfig
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
    strat = RWASettlementMEV(venues, threshold=threshold)
    return strat


def test_opportunity_detection():
    strat = setup_strat(threshold=0.01)
    feed_data = {
        ("dex", "asset"): RWAData(100, 0.1, 1),
        ("cex", "asset"): RWAData(102, 0.1, 1),
    }
    strat.feed = DummyFeed(feed_data)
    strat.tx_builder.web3 = None
    strat.nonce_manager.web3 = None
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
    strat = setup_strat()
    feed_data = {("dex", "asset"): RWAData(100, 0.1, 1), ("cex", "asset"): RWAData(100, 0.1, 1)}
    strat.feed = DummyFeed(feed_data)
    strat.tx_builder.web3 = None
    strat.nonce_manager.web3 = None
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setattr(
        "strategies.rwa_settlement.strategy.kill_switch_triggered", lambda: True
    )
    result = strat.run_once()
    assert result is None
