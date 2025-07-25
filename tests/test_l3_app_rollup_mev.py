import json
import tempfile
import types
from pathlib import Path
import sys


from strategies.l3_app_rollup_mev import L3AppRollupMEV, PoolConfig, BridgeConfig
from agents.capital_lock import CapitalLock
from core.oracles.uniswap_feed import PriceData
from core.oracles.intent_feed import IntentData


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


class DummyIntentFeed:
    def __init__(self, intents):
        self.intents = intents

    def fetch_intents(self, domain):
        data = self.intents.get(domain)
        if isinstance(data, Exception):
            raise data
        return [IntentData(**i) for i in data]


def setup_strat(threshold=0.01):
    pools = {
        "arbitrum": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "arbitrum"
        ),  # test-only
        "zksync": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "zksync"
        ),  # test-only
    }
    bridges = {("zksync", "arbitrum"): BridgeConfig(0.0001, latency_sec=10)}
    strat = L3AppRollupMEV(pools, bridges, threshold=threshold, capital_lock=CapitalLock(1000, 1e9, 0))
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
        "strategies.l3_app_rollup_mev.strategy.kill_switch_triggered", lambda: False
    )
    account = types.ModuleType("eth_account")
    class DummyAccount:
        @staticmethod
        def from_key(key):
            return "acct"
    account.Account = DummyAccount
    monkeypatch.setitem(sys.modules, "eth_account", account)


def test_l3_sandwich_opportunity(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat(threshold=0.01)
    strat.feed = DummyFeed({"arbitrum": 100, "zksync": 102})
    strat.intent_feed = DummyIntentFeed({"zksync": []})
    strat.tx_builder.web3 = strat.feed.web3s["arbitrum"]
    strat.nonce_manager.web3 = strat.feed.web3s["arbitrum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result and result["opportunity"]


def test_bridge_race_opportunity(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat(threshold=0.001)
    strat.feed = DummyFeed({"arbitrum": 101, "zksync": 100})
    strat.intent_feed = DummyIntentFeed({"zksync": [{"intent_id": "1", "domain": "zksync", "action": "bridge", "price": 101}]})
    strat.edges_enabled["l3_sandwich"] = False
    strat.tx_builder.web3 = strat.feed.web3s["arbitrum"]
    strat.nonce_manager.web3 = strat.feed.web3s["arbitrum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result and result["action"].startswith("bridge_race")


def test_snapshot_restore(tmp_path):
    strat = setup_strat()
    strat.last_prices = {"arbitrum": 1.0}
    strat.pending_bridges = {"zksync": 2}
    snap = tmp_path / "snap.json"
    strat.snapshot(snap)
    strat.last_prices = {}
    strat.pending_bridges = {}
    strat.restore(snap)
    data = json.loads(snap.read_text())
    assert strat.last_prices["arbitrum"] == 1.0
    assert strat.pending_bridges["zksync"] == 2
    assert data["last_prices"]["arbitrum"] == 1.0


def test_kill_switch(monkeypatch):
    _patch_flashbots(monkeypatch)
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    strat = setup_strat()
    strat.feed = DummyFeed({"arbitrum": 100, "zksync": 102})
    strat.intent_feed = DummyIntentFeed({"zksync": []})
    strat.tx_builder.web3 = strat.feed.web3s["arbitrum"]
    strat.nonce_manager.web3 = strat.feed.web3s["arbitrum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(Path(tmp) / "kill.json"))
    monkeypatch.setattr(
        "strategies.l3_app_rollup_mev.strategy.kill_switch_triggered", lambda: True
    )
    result = strat.run_once()
    assert result is None


def test_mutate_hook():
    strat = setup_strat(threshold=0.01)
    strat.mutate({"threshold": 0.02, "edges_enabled": {"bridge_race": False}})
    assert strat.threshold == 0.02
    assert strat.edges_enabled["bridge_race"] is False
