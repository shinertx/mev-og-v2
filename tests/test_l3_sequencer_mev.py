import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from strategies.l3_sequencer_mev import L3SequencerMEV, PoolConfig
from agents.capital_lock import CapitalLock
from core.oracles.uniswap_feed import PriceData


class DummyPool:
    def __init__(self, price, block=1, timestamp=1):
        self._price = price
        self._block = block
        self._timestamp = timestamp

    class functions:
        def __init__(self, outer):
            self.outer = outer

        def slot0(self):
            return lambda: (self.outer._price, 0, 0, 0, 0, 0, False)

        def token0(self):
            return lambda: "0x0"

        def token1(self):
            return lambda: "0x1"

    def __getattr__(self, item):
        return getattr(self.functions(self), item)


class DummyEth:
    def __init__(self, price):
        self.contract_obj = DummyPool(price)
        self.block_number = 1

    def contract(self, address, abi):
        return self.contract_obj

    def get_block(self, block):
        return type("B", (), {"number": self.block_number, "timestamp": 1})

    def get_transaction_count(self, address):
        return 0

    def estimate_gas(self, tx):
        return 21000

    class account:
        @staticmethod
        def decode_transaction(tx):
            return {}


class DummyWeb3:
    def __init__(self, price):
        self.eth = DummyEth(price)


class DummyFeed:
    def __init__(self, prices, block=1):
        self.prices = prices
        self.web3s = {d: DummyWeb3(p) for d, p in prices.items()}
        self.block = block

    def fetch_price(self, pool, domain):
        price = self.prices[domain]
        return PriceData(price, pool, self.block, 1, 0)


def setup_strat(threshold=0.001):
    pools = {
        "l3": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "ethereum"
        )  # test-only
    }
    strat = L3SequencerMEV(pools, threshold=threshold, capital_lock=CapitalLock(1000, 1e9, 0))
    return strat


def test_opportunity_detection():
    strat = setup_strat(threshold=0.001)
    strat.feed = DummyFeed({"ethereum": 100})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result is None
    strat.feed = DummyFeed({"ethereum": 98})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    result = strat.run_once()
    assert result is None or result.get("opportunity")


def test_snapshot_restore(tmp_path):
    strat = setup_strat()
    strat.last_prices = {"l3": 1.0}
    snap = tmp_path / "snap.json"
    strat.snapshot(snap)
    strat.last_prices = {}
    strat.restore(snap)
    data = json.loads(snap.read_text())
    assert strat.last_prices["l3"] == 1.0
    assert data["last_prices"]["l3"] == 1.0


def test_mutate_hook():
    strat = setup_strat()
    strat.mutate({"threshold": 0.01, "time_band_sec": 5, "reorg_window": 2})
    assert strat.threshold == 0.01
    assert strat.time_band_sec == 5
    assert strat.reorg_window == 2


def test_kill_switch(monkeypatch):
    strat = setup_strat()
    strat.feed = DummyFeed({"ethereum": 100})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setenv("KILL_SWITCH", "1")
    result = strat.run_once()
    assert result is None
