"""Cross-rollup MEV execution bot with DRP and mutation hooks.

This strategy scans specified Uniswap V3 pools across Ethereum and major L2s
for price discrepancies. It factors in gas and bridge costs to identify
arbitrage or sandwich opportunities and submits bundles via
:class:`~core.tx_engine.builder.TransactionBuilder`.

Module purpose and system role:
    - Monitor cross-domain prices and bridge costs.
    - Simulate bundle execution (Flashbots/SUAVE placeholder).
    - Record structured logs, metrics, and DRP snapshots.

Integration points and dependencies:
    - Uses :class:`core.oracles.uniswap_feed.UniswapV3Feed` for pricing.
    - Relies on :class:`core.tx_engine.TransactionBuilder` and
      :class:`core.tx_engine.NonceManager` for transaction dispatch.
    - Kill switch utilities abort operation when triggered.

Simulation/test hooks and kill conditions:
    - Designed for forked-mainnet simulation via ``infra/sim_harness``.
    - Automatically blacklists pools after repeated failures.
    - Aborts on kill switch activation or stale data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypedDict, cast

from core.logger import StructuredLogger, log_error, make_json_safe
from core import metrics
from core.oracles.uniswap_feed import UniswapV3Feed, PriceData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager, get_shared_nonce_manager
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from agents.capital_lock import CapitalLock
import time

LOG_FILE = Path(os.getenv("CROSS_ROLLUP_LOG", "logs/cross_rollup_superbot.json"))
LOG = StructuredLogger("cross_rollup_superbot", log_file=str(LOG_FILE))
STRATEGY_ID = "cross_rollup_superbot"


@dataclass
class PoolConfig:
    """Configuration for monitored pools."""

    pool: str
    domain: str


@dataclass
class BridgeConfig:
    """Bridge cost assumptions between two domains."""

    cost: float  # estimated fee in the traded asset
    latency_sec: int = 0


class Opportunity(TypedDict):
    opportunity: bool
    spread: float
    profit: float
    action: str
    buy: str
    sell: str


class CrossRollupSuperbot:
    """Detect cross-rollup price spreads and execute atomic trades."""

    DEFAULT_THRESHOLD = 0.005

    def __init__(
        self,
        pools: Dict[str, PoolConfig],
        bridge_costs: Dict[Tuple[str, str], BridgeConfig],
        threshold: float | None = None,
        *,
        capital_lock: CapitalLock | None = None,
        nonce_manager: NonceManager | None = None,
    ) -> None:
        self.feed = UniswapV3Feed()
        self.pools = pools
        self.bridge_costs = bridge_costs
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.last_prices: Dict[str, float] = {}
        self.failed_pools: Dict[str, int] = {}
        self.max_failures = 3

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = nonce_manager or get_shared_nonce_manager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("SUPERBOT_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(
                make_json_safe({"last_prices": self.last_prices, "failed_pools": self.failed_pools}),
                fh,
            )

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            data = json.loads(Path(path).read_text())
            self.last_prices = data.get("last_prices", {})
            self.failed_pools = data.get("failed_pools", {})

    # ------------------------------------------------------------------
    def _record(self, domain: str, data: PriceData, opportunity: bool, spread: float, action: str = "", tx_id: str = "") -> None:
        LOG.log(
            "price",
            tx_id=tx_id,
            strategy_id=STRATEGY_ID,
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="low",
            domain=domain,
            price=data.price,
            block=data.block,
            block_age=data.block_age,
            opportunity=opportunity,
            spread=spread,
            action=action,
        )

    # ------------------------------------------------------------------
    def _compute_profit(self, buy: str, sell: str, amount: float, prices: Dict[str, float]) -> float:
        price_buy = prices[buy]
        price_sell = prices[sell]
        spread = (price_sell - price_buy) / price_buy
        bridge_key = (buy, sell)
        fee = self.bridge_costs.get(bridge_key, BridgeConfig(0.0)).cost
        return (spread * amount) - fee

    def _detect_opportunity(self, prices: Dict[str, float]) -> Optional[Opportunity]:
        domains = list(prices.keys())
        if len(domains) < 2:
            return None
        buy = min(domains, key=lambda d: prices[d])
        sell = max(domains, key=lambda d: prices[d])
        spread = (prices[sell] - prices[buy]) / prices[buy]
        if spread < self.threshold:
            return None
        profit = self._compute_profit(buy, sell, 1.0, prices)
        if profit <= 0:
            return None
        action = f"bundle_buy:{buy}_sell:{sell}"
        return cast(Opportunity, {
            "opportunity": True,
            "spread": spread,
            "profit": profit,
            "action": action,
            "buy": buy,
            "sell": sell,
        })

    # ------------------------------------------------------------------
    def _bundle_and_send(self, action: str) -> tuple[str, float]:
        """Create Flashbots/SUAVE bundle and relay it with latency tracking.

        Falls back to :func:`TransactionBuilder.send_transaction` on failure.
        """
        try:
            from eth_account import Account  # type: ignore
            from flashbots import flashbot  # type: ignore
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError("flashbots package required") from exc

        w3 = self.tx_builder.web3
        auth_key = os.getenv("FLASHBOTS_AUTH_KEY")
        relay = os.getenv("FLASHBOTS_RPC_URL", "https://relay.flashbots.net")
        if not auth_key:
            raise RuntimeError("FLASHBOTS_AUTH_KEY not set")

        auth_account = Account.from_key(auth_key)
        flashbot(w3, auth_account, endpoint_uri=relay)

        priority_gwei = float(os.getenv("PRIORITY_FEE_GWEI", "2"))
        bundle = [
            {
                "signed_transaction": self.sample_tx,
                "maxPriorityFeePerGas": int(priority_gwei * 1e9),
            }
        ]
        target_block = w3.eth.block_number + 1
        start = time.time()
        try:
            result = w3.flashbots.send_bundle(bundle, target_block)
            latency = time.time() - start
            return str(result.get("bundleHash")), latency
        except Exception as exc:  # pragma: no cover - runtime
            latency = time.time() - start
            log_error(STRATEGY_ID, f"bundle send: {exc}", event="bundle_fail")
            tx_hash = self.tx_builder.send_transaction(
                self.sample_tx,
                self.executor,
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
            return (
                tx_hash.hex()
                if isinstance(tx_hash, (bytes, bytearray))
                else str(tx_hash),
                latency,
            )

    # ------------------------------------------------------------------
    def run_once(self) -> Optional[Opportunity]:
        if kill_switch_triggered():
            record_kill_event(STRATEGY_ID)
            LOG.log(
                "killed",
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
            )
            return None

        price_data: Dict[str, PriceData] = {}
        for label, cfg in self.pools.items():
            if self.failed_pools.get(label, 0) >= self.max_failures:
                continue
            try:
                data = self.feed.fetch_price(cfg.pool, cfg.domain)
            except Exception as exc:
                log_error(STRATEGY_ID, str(exc), event="price_fetch", domain=cfg.domain)
                self.failed_pools[label] = self.failed_pools.get(label, 0) + 1
                metrics.record_fail()
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            self._record(cfg.domain, data, False, 0.0)

        if not price_data:
            return None

        if any(d.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")) for d in price_data.values()):
            log_error(STRATEGY_ID, "stale price detected", event="stale_price")
            metrics.record_fail()
            return None

        prices = {k: d.price for k, d in price_data.items()}
        opp = self._detect_opportunity(prices)
        if opp:
            if not self.capital_lock.trade_allowed():
                msg = "capital lock: trade not allowed"
                LOG.log(
                    "capital_lock",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="high",
                    error=msg,
                )
                log_error(STRATEGY_ID, msg, event="capital_lock", risk_level="high")
                return None

            pre = os.getenv("SUPERBOT_STATE_PRE", "state/superbot_pre.json")
            post = os.getenv("SUPERBOT_STATE_POST", "state/superbot_post.json")
            tx_pre = os.getenv("SUPERBOT_TX_PRE", "state/superbot_tx_pre.json")
            tx_post = os.getenv("SUPERBOT_TX_POST", "state/superbot_tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_id, latency = self._bundle_and_send(str(opp["action"]))
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            metrics.record_opportunity(float(opp["spread"]), float(opp["profit"]), latency)

            self.capital_lock.record_trade(float(opp["profit"]))
            for label, data in price_data.items():
                self._record(
                    self.pools[label].domain,
                    data,
                    True,
                    float(opp["spread"]),
                    str(opp["action"]),
                    tx_id=tx_id,
                )
        else:
            metrics.record_fail()

        return opp

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
        """Update strategy parameters at runtime."""
        if "threshold" in params:
            try:
                self.threshold = float(params["threshold"])
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="threshold",
                    value=self.threshold,
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"mutate threshold: {exc}", event="mutate_error")
        if "bridge_costs" in params:
            try:
                for k, v in params["bridge_costs"].items():
                    pair = tuple(k.split("->"))
                    self.bridge_costs[pair] = BridgeConfig(**v)
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="bridge_costs",
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"mutate bridge_costs: {exc}", event="mutate_error")

