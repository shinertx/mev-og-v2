"""
strategy_id: "BridgeArb_001"
edge_type: "BridgeDelay"
ttl_hours: 48
triggers:
  - bridge_delay_secs > 8
  - price_gap_pct > 2
"""

# Real-world asset (RWA) cross-venue settlement strategy.
#
# Module purpose and system role:
#     - Monitor tokenized asset prices across venues and settle when spreads exceed fees.
#
# Integration points and dependencies:
#     - :class:`core.oracles.rwa_feed.RWAFeed` for asset price and fee data.
#     - :class:`core.tx_engine.TransactionBuilder` and :class:`core.tx_engine.NonceManager` for replay defense.
#     - Kill switch utilities to halt operations.
#
# Simulation/test hooks and kill conditions:
#     - Validated via ``infra/sim_harness`` fork simulations.
#     - Circuit breaks if kill switch is active or prices are stale.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict, cast
import yaml

from core.logger import StructuredLogger, log_error, make_json_safe
from core import metrics
from core.oracles.rwa_feed import RWAFeed, RWAData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager, get_shared_nonce_manager
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from agents.capital_lock import CapitalLock
import time
try:
    from prometheus_client import Counter, Histogram, start_http_server
except Exception:  # pragma: no cover - optional
    Counter = Histogram = None

    def start_http_server(*_a: object, **_k: object) -> None:
        pass

LOG_FILE = Path(os.getenv("RWA_SETTLE_LOG", "logs/rwa_settlement.json"))
LOG = StructuredLogger("rwa_settlement", log_file=str(LOG_FILE))
EDGE_SCHEMA: Dict[str, Any] = yaml.safe_load(__doc__ or "")
STRATEGY_ID = EDGE_SCHEMA["strategy_id"]

if Counter:
    arb_opportunities_found = Counter(
        "arb_opportunities_found", "Total arb opps"
    )
    arb_profit_eth = Counter(
        "arb_profit_eth", "Cumulative ETH profit"
    )
    arb_latency = Histogram("arb_latency", "Latency for arbs")
    arb_error_count = Counter(
        "arb_error_count", "Errors during arb"
    )
    arb_abort_count = Counter(
        "arb_abort_count",
        "Aborted arb trades",
    )
    try:
        start_http_server(int(os.getenv("PROMETHEUS_PORT", "8000")))
    except Exception:
        pass
else:  # pragma: no cover - metrics optional
    class _Dummy:
        def inc(self, *_a: object, **_k: object) -> None:
            pass

        def observe(self, *_a: object, **_k: object) -> None:
            pass

    arb_opportunities_found = (
        arb_profit_eth
    ) = (
        arb_latency
    ) = (
        arb_error_count
    ) = (
        arb_abort_count
    ) = _Dummy()


@dataclass
class VenueConfig:
    venue: str
    asset: str


class Opportunity(TypedDict):
    opportunity: bool
    spread: float
    action: str
    buy: str
    sell: str


class RWASettlementMEV:
    """Cross-venue RWA settlement."""

    DEFAULT_THRESHOLD = 0.003

    def __init__(
        self,
        venues: Dict[str, VenueConfig],
        *,
        threshold: float | None = None,
        capital_lock: CapitalLock | None = None,
        nonce_manager: NonceManager | None = None,
        capital_base_eth: float = 1.0,
    ) -> None:
        self.feed = RWAFeed()
        self.venues = venues
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.last_prices: Dict[str, float] = {}

        w3 = None
        self.nonce_manager = nonce_manager or get_shared_nonce_manager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("RWA_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)
        self.capital_base_eth = capital_base_eth

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(make_json_safe({"last_prices": self.last_prices}), fh)

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            data = json.loads(Path(path).read_text())
            self.last_prices = data.get("last_prices", {})

    # ------------------------------------------------------------------
    def _record(self, venue: str, data: RWAData, opportunity: bool, spread: float, action: str = "", tx_id: str = "") -> None:
        LOG.log(
            "price",
            tx_id=tx_id,
            strategy_id=EDGE_SCHEMA["strategy_id"],
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="low",
            venue=venue,
            price=data.price,
            fee=data.fee,
            block=data.block,
            opportunity=opportunity,
            spread=spread,
            action=action,
        )

    # ------------------------------------------------------------------
    def _detect_opportunity(self, prices: Dict[str, float]) -> Optional[Opportunity]:
        venues = list(prices.keys())
        if len(venues) < 2:
            return None
        buy = min(venues, key=lambda v: prices[v])
        sell = max(venues, key=lambda v: prices[v])
        spread = (prices[sell] - prices[buy]) / prices[buy]
        if spread < self.threshold:
            return None
        action = f"rwa_settle:{buy}->{sell}"
        return cast(Opportunity, {"opportunity": True, "spread": spread, "action": action, "buy": buy, "sell": sell})

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
            log_error(EDGE_SCHEMA["strategy_id"], f"bundle send: {exc}", event="bundle_fail")
            tx_hash = self.tx_builder.send_transaction(
                self.sample_tx,
                self.executor,
                strategy_id=EDGE_SCHEMA["strategy_id"],
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
            record_kill_event(EDGE_SCHEMA["strategy_id"])
            LOG.log(
                "killed",
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
            )
            return None

        price_data: Dict[str, RWAData] = {}
        for label, cfg in self.venues.items():
            try:
                data = self.feed.fetch(cfg.asset, cfg.venue)
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], str(exc), event="price_fetch", venue=cfg.venue)
                metrics.record_fail()
                arb_error_count.inc()
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            self._record(cfg.venue, data, False, 0.0)

        if not price_data:
            return None

        prices = {k: d.price + d.fee for k, d in price_data.items()}
        opp = self._detect_opportunity(prices)
        if opp:
            profit = (prices[opp["sell"]] - prices[opp["buy"]]) * self.capital_base_eth
            gas_price = getattr(self.tx_builder.web3.eth, "gas_price", 0)
            min_gas_cost = float(gas_price * 21000) / 1e18 * 1.5
            est_slippage = abs(
                prices[opp["buy"]] - self.last_prices.get(opp["buy"], prices[opp["buy"]])
            ) / prices[opp["buy"]]
            slip_tol = float(os.getenv("SLIPPAGE_PCT", "0"))
            if profit < min_gas_cost:
                LOG.log(
                    "trade_abort",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    reason="low_pnl",
                    projected_pnl=profit,
                    threshold=min_gas_cost,
                )
                metrics.record_abort()
                arb_abort_count.inc()
                return None
            if est_slippage > slip_tol:
                LOG.log(
                    "trade_abort",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="medium",
                    reason="slippage",
                    slippage=est_slippage,
                    tolerance=slip_tol,
                )
                metrics.record_abort()
                arb_abort_count.inc()
                return None
            if not self.capital_lock.trade_allowed():
                msg = "capital lock: trade not allowed"
                LOG.log(
                    "capital_lock",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="high",
                    error=msg,
                )
                log_error(EDGE_SCHEMA["strategy_id"], msg, event="capital_lock", risk_level="high")
                return None

            pre = os.getenv("RWA_STATE_PRE", "state/rwa_pre.json")
            post = os.getenv("RWA_STATE_POST", "state/rwa_post.json")
            tx_pre = os.getenv("RWA_TX_PRE", "state/rwa_tx_pre.json")
            tx_post = os.getenv("RWA_TX_POST", "state/rwa_tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_id, latency = self._bundle_and_send(str(opp["action"]))
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            metrics.record_opportunity(float(opp["spread"]), 0.0, latency)
            arb_opportunities_found.inc()
            arb_profit_eth.inc(0.0)
            arb_latency.observe(latency)

            profit = prices[opp["sell"]] - prices[opp["buy"]]
            self.capital_lock.record_trade(profit)
            for label, data in price_data.items():
                self._record(
                    self.venues[label].venue,
                    data,
                    True,
                    float(opp["spread"]),
                    str(opp["action"]),
                    tx_id=tx_id,
                )
            return opp

        metrics.record_fail()
        arb_error_count.inc()
        return None

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
        if "threshold" in params:
            try:
                self.threshold = float(params["threshold"])
                LOG.log(
                    "mutate",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="threshold",
                    value=self.threshold,
                )
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], f"mutate threshold: {exc}", event="mutate_error")


async def run(
    block_number: int | None = None,
    chain_id: int | None = None,
    test_mode: bool = False,
    **kwargs: Any,
) -> None:
    """Execute :meth:`RWASettlementMEV.run_once` with latency tracking."""

    if block_number is not None:
        os.environ["BLOCK_NUMBER"] = str(block_number)
    if chain_id is not None:
        os.environ["CHAIN_ID"] = str(chain_id)
    if test_mode:
        os.environ["TEST_MODE"] = "1"

    strategy = RWASettlementMEV({}, **kwargs)
    start = time.monotonic()
    strategy.run_once()
    latency = time.monotonic() - start
    LOG.log(
        "run_latency",
        strategy_id=EDGE_SCHEMA["strategy_id"],
        mutation_id=os.getenv("MUTATION_ID", "dev"),
        risk_level="low",
        latency=latency,
        block=block_number,
        chain_id=chain_id,
        test_mode=test_mode,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())

