import json
import os
from pathlib import Path
from typing import Callable


from strategies.cross_rollup_superbot import CrossRollupSuperbot, PoolConfig, BridgeConfig
from agents.capital_lock import CapitalLock
from core.oracles.uniswap_feed import PriceData


class DummyPool:
    def __init__(self, price: float) -> None:
        self._price = price

    class functions:
        def __init__(self, outer: "DummyPool") -> None:
            self.outer = outer

        def slot0(self) -> Callable[[], tuple[int, int, int, int, int, int, bool]]:
            return lambda: (self.outer._price, 0, 0, 0, 0, 0, False)

        def token0(self) -> Callable[[], str]:
            return lambda: "0x0"

        def token1(self) -> Callable[[], str]:
            return lambda: "0x1"

    def __getattr__(self, item: str):
        return getattr(self.functions(self), item)


class DummyEth:
    def __init__(self, price: float) -> None:
        self.contract_obj = DummyPool(price)
        self.block_number = 1

    def contract(self, address: str, abi: object) -> DummyPool:
        return self.contract_obj

    def get_block(self, block: int) -> object:
        return type("B", (), {"number": 1, "timestamp": 1})

    def get_transaction_count(self, address: str) -> int:
        return 0

    def estimate_gas(self, tx: dict) -> int:
        return 21000

    class account:
        @staticmethod
        def decode_transaction(tx: bytes) -> dict:
            return {}


class DummyWeb3:
    def __init__(self, price: float) -> None:
        self.eth = DummyEth(price)


class DummyFeed:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices
        self.web3s = {d: DummyWeb3(p) for d, p in prices.items()}

    def fetch_price(self, pool: object, domain: str) -> PriceData:
        price = self.prices[domain]
        return PriceData(price, pool, 1, 1, 0)


def test_capital_lock_blocks_trade(tmp_path) -> None:
    pools = {
        "eth": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "ethereum"
        ),  # test-only
        "arb": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "arbitrum"
        ),  # test-only
    }
    bridges = {("ethereum", "arbitrum"): BridgeConfig(0.0001)}
    lock = CapitalLock(max_drawdown_pct=5, max_loss_usd=50, balance_usd=1000)
    lock.record_trade(-60)
    strat = CrossRollupSuperbot(pools, bridges, threshold=0.01, capital_lock=lock)
    strat.feed = DummyFeed({"ethereum": 100, "arbitrum": 102})
    strat.tx_builder.web3 = strat.feed.web3s["ethereum"]
    strat.nonce_manager.web3 = strat.feed.web3s["ethereum"]
    strat.tx_builder.send_transaction = lambda *a, **k: b"hash"

    log_file = tmp_path / "log.json"
    err_file = tmp_path / "err.log"
    os.environ["CROSS_ROLLUP_LOG"] = str(log_file)
    os.environ["ERROR_LOG_FILE"] = str(err_file)
    import strategies.cross_rollup_superbot.strategy as mod
    mod.LOG.path = Path(os.environ["CROSS_ROLLUP_LOG"])

    result = strat.run_once()
    assert result is None

    slog = json.loads(log_file.read_text().splitlines()[-1])
    elog = json.loads(err_file.read_text().splitlines()[-1])
    assert slog["error"] == "capital lock: trade not allowed"
    assert slog["risk_level"] == "high"
    assert elog["error"] == "capital lock: trade not allowed"
    assert elog["risk_level"] == "high"
