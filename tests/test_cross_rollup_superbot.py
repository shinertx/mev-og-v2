import os
import json
import tempfile
import types
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from strategies.cross_rollup_superbot import CrossRollupSuperbot, PoolConfig, BridgeConfig
from agents.capital_lock import CapitalLock
from core.oracles.uniswap_feed import PriceData


class DummyPool:
    def __init__(self, price):
        self._price = price

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
        return type("B", (), {"number": 1, "timestamp": 1})

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
    def __init__(self, prices):
        self.prices = prices
        self.web3s = {d: DummyWeb3(p) for d, p in prices.items()}

    def fetch_price(self, pool, domain):
        if isinstance(self.prices[domain], Exception):
            raise self.prices[domain]
        price = self.prices[domain]
        return PriceData(price, pool, 1, 1, 0)


def setup_strat(threshold=0.01):
    pools = {
        "eth": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "ethereum"
        ),  # test-only
        "arb": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "arbitrum"
        ),  # test-only
    }
    bridges = {("ethereum", "arbitrum"): BridgeConfig(0.0001)}
    strat = CrossRollupSuperbot(pools, bridges, threshold=threshold, capital_lock=CapitalLock(1000, 1e9, 0))
    return strat


def _patch_flashbots(monkeypatch):
    module = types.ModuleType("flashbots")

    class FB:
        def send_bundle(self, bundle, target):
            return {"bundleHash": "hash"}

    def flashbot(w3, account, endpoint_uri=None):
        w3.flashbots = FB()

    module.flashbot = flashbot
    monkeypatch.setitem(sys.modules, "flashbots", module)


def test_opportunity_detection(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat(threshold=0.01)
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 102})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result and result["opportunity"]


def test_bridge_cost_blocks_trade(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat(threshold=0.001)
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 100.05})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result is None


def test_error_blacklist(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat()
    strat.feed = DummyFeed({"ethereum": RuntimeError("rpc fail"), "arbitrum": 102})
    strat.tx_builder.web3 = DummyWeb3(100)
    strat.nonce_manager.web3 = DummyWeb3(100)
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    with tempfile.TemporaryDirectory() as td:
        os.environ["ERROR_LOG_FILE"] = str(Path(td) / "err.log")
        strat.run_once()
        assert strat.failed_pools["eth"] == 1


def test_snapshot_restore(tmp_path):
    strat = setup_strat()
    strat.last_prices = {"eth": 1.0}
    snap = tmp_path / "snap.json"
    strat.snapshot(snap)
    strat.last_prices = {}
    strat.restore(snap)
    assert strat.last_prices["eth"] == 1.0
    data = json.loads(snap.read_text())
    assert data["last_prices"]["eth"] == 1.0


def test_mutate_hook():
    strat = setup_strat(threshold=0.01)
    strat.mutate({"threshold": 0.02})
    assert strat.threshold == 0.02


def test_kill_switch(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat()
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 102})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setenv("KILL_SWITCH", "1")
    result = strat.run_once()
    assert result is None

