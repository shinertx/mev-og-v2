"""Tests for the CrossDomainArb strategy."""

import json
import logging
import os
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategies.cross_domain_arb import CrossDomainArb, PoolConfig
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


def test_opportunity_detection():
    pools = {
        "eth": PoolConfig("0xpool", "ethereum"),
        "arb": PoolConfig("0xpool", "arbitrum"),
        "opt": PoolConfig("0xpool", "optimism"),
    }
    strat = CrossDomainArb(pools, threshold=0.01)
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 102, "optimism": 101})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result = strat.run_once()
    assert result["opportunity"] is True
    assert "buy:ethereum" in result["action"]


def test_price_feed_error():
    pools = {"eth": PoolConfig("0xpool", "ethereum")}
    strat = CrossDomainArb(pools)
    strat.feed = DummyFeed({"ethereum": RuntimeError("rpc fail")})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    with tempfile.TemporaryDirectory() as td:
        err = Path(td) / "errors.log"
        os.environ["ERROR_LOG_FILE"] = str(err)
        result = strat.run_once()
        assert result is None
        assert err.read_text().strip()


def test_no_false_positive_on_flip():
    pools = {
        "eth": PoolConfig("0xpool", "ethereum"),
        "arb": PoolConfig("0xpool", "arbitrum"),
    }
    strat = CrossDomainArb(pools, threshold=0.05)
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 99})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result1 = strat.run_once()
    assert result1 is None
    strat.feed = DummyFeed({"ethereum": 99, "arbitrum": 100})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result2 = strat.run_once()
    assert result2 is None


def test_stale_block_warning(caplog):
    pools = {"eth": PoolConfig("0xpool", "ethereum")}
    strat = CrossDomainArb(pools)
    stale = PriceData(100, "0xpool", 1, 1, 31)
    strat.feed = DummyFeed({"ethereum": 100})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    strat.feed.fetch_price = lambda p, d: stale
    caplog.set_level(logging.WARNING)
    with tempfile.TemporaryDirectory() as td:
        err = Path(td) / "errors.log"
        os.environ["ERROR_LOG_FILE"] = str(err)
        result = strat.run_once()
        assert result is None
        assert err.read_text().strip()
    assert any("stale" in rec.message for rec in caplog.records)


def test_snapshot_restore(tmp_path):
    pools = {"eth": PoolConfig("0xpool", "ethereum")}
    strat = CrossDomainArb(pools)
    strat.last_prices = {"eth": 1.23}
    snap = tmp_path / "snap.json"
    strat.snapshot(snap)
    strat.last_prices = {}
    strat.restore(snap)
    assert strat.last_prices["eth"] == 1.23
    data = json.loads(snap.read_text())
    assert data["eth"] == 1.23


def test_multiple_opportunities(tmp_path):
    pools = {
        "eth": PoolConfig("0xpool", "ethereum"),
        "arb": PoolConfig("0xpool", "arbitrum"),
    }
    strat = CrossDomainArb(pools, threshold=0.01)
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 103})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    os.environ["CROSS_ARB_STATE_PRE"] = str(tmp_path / "pre.json")
    os.environ["CROSS_ARB_STATE_POST"] = str(tmp_path / "post.json")
    os.environ["CROSS_ARB_TX_PRE"] = str(tmp_path / "txpre.json")
    os.environ["CROSS_ARB_TX_POST"] = str(tmp_path / "txpost.json")
    result1 = strat.run_once()
    strat.feed = DummyFeed({"ethereum": 99, "arbitrum": 102})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    result2 = strat.run_once()
    assert result1 and result2
    assert Path(os.environ["CROSS_ARB_TX_POST"]).exists()


def test_drp_snapshots(tmp_path):
    pools = {"eth": PoolConfig("0xpool", "ethereum")}
    strat = CrossDomainArb(pools, threshold=0.0)
    strat.feed = DummyFeed({"ethereum": 100})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"
    os.environ["CROSS_ARB_STATE_PRE"] = str(tmp_path / "pre.json")
    os.environ["CROSS_ARB_STATE_POST"] = str(tmp_path / "post.json")
    os.environ["CROSS_ARB_TX_PRE"] = str(tmp_path / "txpre.json")
    os.environ["CROSS_ARB_TX_POST"] = str(tmp_path / "txpost.json")
    strat.run_once()
    assert Path(os.environ["CROSS_ARB_STATE_PRE"]).exists()
    assert Path(os.environ["CROSS_ARB_STATE_POST"]).exists()
    assert Path(os.environ["CROSS_ARB_TX_PRE"]).exists()
    assert Path(os.environ["CROSS_ARB_TX_POST"]).exists()
