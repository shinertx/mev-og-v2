"""L3 Sequencer builder/sequencer MEV strategy.

Module purpose and system role:
    - Monitor L3 rollup pools for sandwich and time-band opportunities.
    - Detect reorg windows and execute reorg arbitrage when profitable.

Integration points and dependencies:
    - :class:`core.oracles.uniswap_feed.UniswapV3Feed` for pricing data.
    - :class:`core.tx_engine.TransactionBuilder` and :class:`core.tx_engine.NonceManager` for dispatch and replay defense.
    - Kill switch utilities for halting execution on demand.

Simulation/test hooks and kill conditions:
    - Designed for forked-mainnet simulation with ``infra/sim_harness``.
    - Aborts immediately if the kill switch is triggered or data is stale.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict, cast
import time

from core.logger import StructuredLogger, log_error
from core import metrics
from core.oracles.uniswap_feed import UniswapV3Feed, PriceData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager
from core.tx_engine import kill_switch as ks
from agents.capital_lock import CapitalLock

LOG_FILE = Path(os.getenv("L3_SEQ_LOG", "logs/l3_sequencer_mev.json"))
LOG = StructuredLogger("l3_sequencer_mev", log_file=str(LOG_FILE))
STRATEGY_ID = "l3_sequencer_mev"


@dataclass
class PoolConfig:
    """Configuration for monitored pools."""

    pool: str
    domain: str


class Opportunity(TypedDict):
    opportunity: bool
    spread: float
    profit: float
    action: str
    buy: str
    sell: str


class L3SequencerMEV:
    """Sandwich and reorg arbitrage on L3 sequencer blocks."""

    DEFAULT_THRESHOLD = 0.002

    def __init__(
        self,
        pools: Dict[str, PoolConfig],
        *,
        threshold: float | None = None,
        time_band_sec: int = 12,
        reorg_window: int = 1,
        capital_lock: CapitalLock | None = None,
    ) -> None:
        self.feed = UniswapV3Feed()
        self.pools = pools
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.time_band_sec = time_band_sec
        self.reorg_window = reorg_window
        self.last_prices: Dict[str, float] = {}
        self.last_block = 0

        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = NonceManager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("L3_SEQ_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"last_prices": self.last_prices, "last_block": self.last_block}, fh)

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            data = json.loads(Path(path).read_text())
            self.last_prices = data.get("last_prices", {})
            self.last_block = int(data.get("last_block", 0))

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
    def _time_band_ok(self, timestamp: int) -> bool:
        return (timestamp % self.time_band_sec) < 1

    def _compute_profit(self, buy: str, sell: str, prices: Dict[str, float]) -> float:
        price_buy = prices[buy]
        price_sell = prices[sell]
        spread = (price_sell - price_buy) / price_buy
        return spread

    def _detect_opportunity(self, prices: Dict[str, float], block: int, timestamp: int) -> Optional[Opportunity]:
        if not self._time_band_ok(timestamp):
            return None
        if block < self.last_block - self.reorg_window:
            # reorg detected, skip
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
        action = f"sequencer_sandwich:{buy}->{sell}"
        return cast(Opportunity, {"opportunity": True, "spread": spread, "profit": profit, "action": action, "buy": buy, "sell": sell})

    # ------------------------------------------------------------------
    def _bundle_and_send(self, action: str) -> str:
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

        bundle = [{"signed_transaction": self.sample_tx}]
        target_block = w3.eth.block_number + 1
        result = w3.flashbots.send_bundle(bundle, target_block)
        return str(result.get("bundleHash"))

    # ------------------------------------------------------------------
    def run_once(self) -> Optional[Opportunity]:
        env_active = os.getenv("KILL_SWITCH") == "1"
        file_active = Path(os.getenv("KILL_SWITCH_FLAG_FILE", "./flags/kill_switch.txt")).exists()
        if env_active or file_active:
            ks.record_kill_event(STRATEGY_ID)
            LOG.log(
                "killed",
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
            )
            return None

        price_data: Dict[str, PriceData] = {}
        block = 0
        timestamp = int(time.time())
        for label, cfg in self.pools.items():
            try:
                data = self.feed.fetch_price(cfg.pool, cfg.domain)
            except Exception as exc:
                log_error(STRATEGY_ID, str(exc), event="price_fetch", domain=cfg.domain)
                metrics.record_fail()
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            block = data.block
            timestamp = data.timestamp
            self._record(cfg.domain, data, False, 0.0)

        if not price_data:
            return None

        if any(d.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")) for d in price_data.values()):
            log_error(STRATEGY_ID, "stale price detected", event="stale_price")
            metrics.record_fail()
            return None

        prices = {k: d.price for k, d in price_data.items()}
        opp = self._detect_opportunity(prices, block, timestamp)
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
                self.last_block = block
                return None

            metrics.record_opportunity(float(opp["spread"]), float(opp["profit"]), 0.0)
            pre = os.getenv("L3_SEQ_STATE_PRE", "state/l3_seq_pre.json")
            post = os.getenv("L3_SEQ_STATE_POST", "state/l3_seq_post.json")
            tx_pre = os.getenv("L3_SEQ_TX_PRE", "state/l3_seq_tx_pre.json")
            tx_post = os.getenv("L3_SEQ_TX_POST", "state/l3_seq_tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_id = self._bundle_and_send(str(opp["action"]))
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            self.capital_lock.record_trade(float(opp["profit"]))
            self.last_block = block
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
            self.last_block = block

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
        if "time_band_sec" in params:
            try:
                self.time_band_sec = int(params["time_band_sec"])
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="time_band_sec",
                    value=self.time_band_sec,
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"mutate time_band_sec: {exc}", event="mutate_error")
        if "reorg_window" in params:
            try:
                self.reorg_window = int(params["reorg_window"])
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="reorg_window",
                    value=self.reorg_window,
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"mutate reorg_window: {exc}", event="mutate_error")
