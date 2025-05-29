"""L3/app-rollup MEV strategy leveraging sandwich and bridge race edges.

This module scans L3 rollups for price discrepancies relative to L2/L1 pools
and monitors intent feeds for bridge transactions that can be frontrun.  It
supports runtime mutation, DRP snapshot/restore and kill switch integration.

Integration points and dependencies:
    - :class:`core.oracles.uniswap_feed.UniswapV3Feed` for pool pricing.
    - :class:`core.oracles.intent_feed.IntentFeed` for intent data.
    - :class:`core.tx_engine.TransactionBuilder` and :class:`core.tx_engine.NonceManager` for dispatch.
    - Kill switch utilities to abort on demand.

Simulation/test hooks and kill conditions:
    - Designed for forked-mainnet simulation via ``infra/sim_harness``.
    - Snapshot and restore functions persist price and bridge state.
    - Aborts immediately if the kill switch is triggered.
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
from core.oracles.intent_feed import IntentFeed, IntentData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager, get_shared_nonce_manager
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from agents.capital_lock import CapitalLock
import time

LOG_FILE = Path(os.getenv("L3_APP_ROLLUP_LOG", "logs/l3_app_rollup_mev.json"))
LOG = StructuredLogger("l3_app_rollup_mev", log_file=str(LOG_FILE))
STRATEGY_ID = "l3_app_rollup_mev"


@dataclass
class PoolConfig:
    """Configuration for monitored pools."""

    pool: str
    domain: str


@dataclass
class BridgeConfig:
    """Bridge parameters between domains."""

    cost: float
    latency_sec: int = 0


class Opportunity(TypedDict):
    opportunity: bool
    spread: float
    profit: float
    action: str
    buy: str
    sell: str


class L3AppRollupMEV:
    """Main strategy class handling sandwich and bridge-race opportunities."""

    DEFAULT_THRESHOLD = 0.003

    def __init__(
        self,
        pools: Dict[str, PoolConfig],
        bridge_costs: Dict[Tuple[str, str], BridgeConfig],
        *,
        threshold: float | None = None,
        edges_enabled: Optional[Dict[str, bool]] = None,
        capital_lock: CapitalLock | None = None,
        nonce_manager: NonceManager | None = None,
    ) -> None:
        self.feed = UniswapV3Feed()
        self.intent_feed = IntentFeed()
        self.pools = pools
        self.bridge_costs = bridge_costs
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.edges_enabled = edges_enabled or {
            "l3_sandwich": True,
            "bridge_race": True,
        }
        self.last_prices: Dict[str, float] = {}
        self.pending_bridges: Dict[str, int] = {}
        self.failed_pools: Dict[str, int] = {}
        self.max_failures = 3

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = nonce_manager or get_shared_nonce_manager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("L3_APP_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(
                make_json_safe({"last_prices": self.last_prices, "pending_bridges": self.pending_bridges}),
                fh,
            )

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            data = json.loads(Path(path).read_text())
            self.last_prices = data.get("last_prices", {})
            self.pending_bridges = data.get("pending_bridges", {})

    # ------------------------------------------------------------------
    def _record(
        self,
        domain: str,
        data: PriceData,
        opportunity: bool,
        spread: float,
        action: str = "",
        tx_id: str = "",
    ) -> None:
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
    def _compute_profit(self, buy: str, sell: str, prices: Dict[str, float]) -> float:
        price_buy = prices[buy]
        price_sell = prices[sell]
        spread = (price_sell - price_buy) / price_buy
        fee = self.bridge_costs.get((buy, sell), BridgeConfig(0.0)).cost
        return (spread - fee)

    def _detect_sandwich(self, prices: Dict[str, float]) -> Optional[Opportunity]:
        if not self.edges_enabled.get("l3_sandwich", True):
            return None
        domains = list(prices.keys())
        if len(domains) < 2:
            return None
        buy = min(domains, key=lambda d: prices[d])
        sell = max(domains, key=lambda d: prices[d])
        spread = (prices[sell] - prices[buy]) / prices[buy]
        if spread < self.threshold:
            return None
        profit = self._compute_profit(buy, sell, prices)
        if profit <= 0:
            return None
        action = f"l3_sandwich:{buy}->{sell}"
        return cast(Opportunity, {"opportunity": True, "spread": spread, "profit": profit, "action": action, "buy": buy, "sell": sell})

    def _detect_bridge_race(self, prices: Dict[str, float]) -> Optional[Opportunity]:
        if not self.edges_enabled.get("bridge_race", True):
            return None
        for (src, dst), cfg in self.bridge_costs.items():
            if src not in prices or dst not in prices:
                continue
            intents: list[IntentData]
            try:
                intents = self.intent_feed.fetch_intents(src)
            except Exception as exc:
                log_error(STRATEGY_ID, f"intent fetch: {exc}", event="intent_fetch", domain=src)
                return None
            if not intents:
                continue
            # Assume any intent implies funds bridging from src to dst
            spread = (prices[dst] - prices[src]) / prices[src]
            if spread < self.threshold:
                continue
            latency = cfg.latency_sec
            if latency > int(os.getenv("BRIDGE_LATENCY_MAX", "30")):
                continue
            profit = self._compute_profit(src, dst, prices)
            if profit <= 0:
                continue
            action = f"bridge_race:{src}->{dst}"
            return cast(Opportunity, {"opportunity": True, "spread": spread, "profit": profit, "action": action, "buy": src, "sell": dst})
        return None

    def _bundle_and_send(self, action: str) -> tuple[str, float]:
        try:
            from eth_account import Account
            from flashbots import flashbot
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
        opp = self._detect_sandwich(prices)
        if opp is None:
            opp = self._detect_bridge_race(prices)

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

            pre = os.getenv("L3_APP_STATE_PRE", "state/l3_app_pre.json")
            post = os.getenv("L3_APP_STATE_POST", "state/l3_app_post.json")
            tx_pre = os.getenv("L3_APP_TX_PRE", "state/l3_app_tx_pre.json")
            tx_post = os.getenv("L3_APP_TX_POST", "state/l3_app_tx_post.json")
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
        if "edges_enabled" in params:
            try:
                self.edges_enabled.update({str(k): bool(v) for k, v in params["edges_enabled"].items()})
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="edges_enabled",
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"mutate edges_enabled: {exc}", event="mutate_error")

