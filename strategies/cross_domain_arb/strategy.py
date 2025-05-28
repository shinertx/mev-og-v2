"""Cross-domain ETH/USDC price arbitrage detection strategy.

# mypy: ignore-errors

Module purpose and system role:
    - Scan Ethereum, Arbitrum, and Optimism Uniswap V3 pools for price
      discrepancies.
    - Log actionable arbitrage signals with DRP snapshot/restore support.

Integration points and dependencies:
    - Utilizes :class:`core.oracles.uniswap_feed.UniswapV3Feed` for price data.
    - Relies on kill switch utilities and TransactionBuilder for execution.

Simulation/test hooks and kill conditions:
    - Designed for forked-mainnet simulation via infra/sim_harness.
    - Aborts operation if kill switch is triggered.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypedDict, List

try:  # webhook optional
    import requests
except Exception:  # pragma: no cover - allow missing dependency
    requests = None  # type: ignore

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager
from core.logger import StructuredLogger, log_error
from core import metrics
from agents.capital_lock import CapitalLock

from core.oracles.uniswap_feed import UniswapV3Feed, PriceData
from core.oracles.intent_feed import IntentFeed, IntentData
from core.mempool_monitor import MempoolMonitor
from core.node_selector import NodeSelector
from ai.intent_classifier import classify_intent
from ai.intent_ghost import ghost_intent
from adapters.flashloan_adapter import FlashloanAdapter
from adapters.pool_scanner import PoolScanner, PoolInfo
from adapters.social_alpha import scrape_social_keywords
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from ai.mutation_log import log_mutation

LOG_FILE = Path(os.getenv("CROSS_ARB_LOG", "logs/cross_domain_arb.json"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)

STRATEGY_ID = "cross_domain_arb"

LOG = StructuredLogger("cross_domain_arb", log_file=str(LOG_FILE))


class BridgeConfig(TypedDict, total=False):
    """Bridge cost assumptions between domains."""

    cost: float
    latency_sec: int


def start_metrics_server(port: int = 8000) -> metrics.MetricsServer:
    """Backward compatible helper to start metrics server."""
    srv = metrics.MetricsServer(port=port)
    srv.start()
    return srv


def _log(event: str, **entry: object) -> None:
    LOG.log(event, strategy_id=STRATEGY_ID, mutation_id=os.getenv("MUTATION_ID", "dev"), risk_level="low", **entry)


def _send_alert(payload: Dict[str, object]) -> None:
    """Send JSON payload to webhook URL if configured."""
    url = os.getenv("ARB_ALERT_WEBHOOK")
    if not url or requests is None:
        return
    try:  # pragma: no cover - network
        requests.post(url, json=payload, timeout=5)
        metrics.record_alert()
    except Exception as exc:  # pragma: no cover - network
        logging.warning("webhook failed: %s", exc)
        log_error(STRATEGY_ID, f"webhook failed: {exc}", event="webhook_fail")


@dataclass
class PoolConfig:
    """Configuration for a Uniswap pool on a given domain."""
    pool: str
    domain: str


class CrossDomainArb:
    """Detect price spreads across domains and execute cost-aware trades."""

    DEFAULT_THRESHOLD = 0.003

    def __init__(
        self,
        pools: Dict[str, PoolConfig],
        bridge_costs: Dict[Tuple[str, str], BridgeConfig],
        threshold: float | None = None,
        *,
        nodes: Optional[Dict[str, str]] = None,
        edges_enabled: Optional[Dict[str, bool]] = None,
        capital_lock: CapitalLock | None = None,
    ) -> None:
        self.feed = UniswapV3Feed()
        self.pools = pools
        self.bridge_costs = bridge_costs
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.last_prices: Dict[str, float] = {}

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

        # transaction execution setup
        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = NonceManager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("ARB_EXECUTOR_ADDR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

        self.intent_feed = IntentFeed()
        self.mempool_monitor = MempoolMonitor(w3)
        self.node_selector = NodeSelector(nodes or {}) if nodes else None
        self.flashloan = FlashloanAdapter(os.getenv("FLASHLOAN_API", "http://localhost:9001"))
        self.pool_scanner = PoolScanner(os.getenv("POOL_SCANNER_API", "http://localhost:9002"))
        default_edges = {
            "l1_sandwich": True,
            "intent": True,
            "flashloan": False,
            "auto_discover": True,
            "ghosting": False,
            "social_alpha": False,
            "stealth_mode": False,
            "hedge": False,
        }
        self.edges_enabled = default_edges
        if edges_enabled:
            self.edges_enabled.update(edges_enabled)

        self.metrics: Dict[str, float] = {"recent_alpha": 0.0}

    # ------------------------------------------------------------------
    def _estimate_gas_cost(self) -> float:
        try:
            gas_price = getattr(self.tx_builder.web3.eth, "gas_price", 0)
            gas_estimate = self.tx_builder.web3.eth.estimate_gas({})
            return float(gas_price * gas_estimate) / 1e18
        except Exception:
            return float(os.getenv("GAS_COST_OVERRIDE", "0"))

    def _compute_profit(self, buy: str, sell: str, prices: Dict[str, float]) -> float:
        price_buy = prices[buy]
        price_sell = prices[sell]
        spread = price_sell - price_buy
        bridge_fee = self.bridge_costs.get((buy, sell), {}).get("cost", 0.0)
        slippage_pct = float(os.getenv("SLIPPAGE_PCT", "0"))
        slippage = price_buy * slippage_pct
        gas_cost = self._estimate_gas_cost()
        return spread - gas_cost - bridge_fee - slippage

    # ------------------------------------------------------------------
    def _auto_discover(self) -> None:
        if not self.edges_enabled.get("auto_discover", True):
            return
        for info in self.pool_scanner.scan():
            if info.pool not in self.pools:
                self.pools[info.pool] = PoolConfig(info.pool, info.domain)
                LOG.log(
                    "new_pool",
                    pool=info.pool,
                    domain=info.domain,
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )
        for info in self.pool_scanner.scan_l3():
            if info.pool not in self.pools:
                self.pools[info.pool] = PoolConfig(info.pool, info.domain)
                LOG.log(
                    "new_l3_pool",
                    pool=info.pool,
                    domain=info.domain,
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )
        if self.edges_enabled.get("social_alpha", False):
            pools = scrape_social_keywords(["bridge", "swap", "launch", "L3"])
            for info in pools:
                pool = info.get("pool")
                dom = info.get("domain")
                if pool and pool not in self.pools:
                    self.pools[pool] = PoolConfig(pool, dom)
                    LOG.log(
                        "add_social_pool",
                        pool=pool,
                        domain=dom,
                        strategy_id=STRATEGY_ID,
                        mutation_id=os.getenv("MUTATION_ID", "dev"),
                        risk_level="low",
                    )

    # ------------------------------------------------------------------
    def _check_l1_sandwich(self) -> bool:
        if not self.edges_enabled.get("l1_sandwich", True):
            return True
        for tx in self.mempool_monitor.listen_bridge_txs(limit=1):
            pre = os.getenv("CROSS_ARB_STATE_PRE", "state/cross_arb_pre.json")
            post = os.getenv("CROSS_ARB_STATE_POST", "state/cross_arb_post.json")
            tx_pre = os.getenv("CROSS_ARB_TX_PRE", "state/tx_pre.json")
            tx_post = os.getenv("CROSS_ARB_TX_POST", "state/tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            try:
                front = self.tx_builder.send_transaction(
                    self.sample_tx,
                    self.executor,
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )
                back = self.tx_builder.send_transaction(
                    self.sample_tx,
                    self.executor,
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"sandwich tx fail: {exc}", event="sandwich_fail")
                metrics.record_fail()
                return False
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            LOG.log(
                "sandwich",
                tx_id=str(front),
                related=str(back),
                bridge_tx=str(tx.get("hash")),
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
            metrics.record_opportunity(0.0, 0.0, 0.0)
            return True
        return True
    # ------------------------------------------------------------------
    def _process_intents(self) -> None:
        if not self.edges_enabled.get("intent", True):
            return
        for domain in self.pools:
            try:
                intents: List[IntentData] = self.intent_feed.fetch_intents(domain)
            except Exception as exc:
                log_error(STRATEGY_ID, f"intent fetch: {exc}", event="intent_fetch", domain=domain)
                continue
            for intent in intents:
                dest = classify_intent(intent.__dict__)
                LOG.log(
                    "intent_route",
                    intent_id=intent.intent_id,
                    predicted=dest,
                    domain=domain,
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )

    # ------------------------------------------------------------------
    def _execute_flashloan(self, buy: str, sell: str) -> None:
        if not self.edges_enabled.get("flashloan", False):
            return
        token = "ETH"
        amount = float(os.getenv("FLASHLOAN_AMOUNT", "1"))
        try:
            res = self.flashloan.trigger(token, amount)
            LOG.log(
                "flashloan",
                token=token,
                amount=amount,
                result=str(res),
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
        except Exception as exc:
            log_error(STRATEGY_ID, f"flashloan: {exc}", event="flashloan_fail")

    # ------------------------------------------------------------------
    def _maybe_ghost(self) -> None:
        if not self.edges_enabled.get("ghosting", False):
            return
        fake_intent = {"intent_id": "bait", "domain": "arb", "action": "swap", "price": 0}
        ghost_intent(os.getenv("INTENT_API_URL", "http://localhost:9003"), fake_intent)

    # ------------------------------------------------------------------
    def hedge_risk(self, size: float, asset: str = "ETH") -> None:
        if not self.edges_enabled.get("hedge", False):
            return
        try:
            import requests  # type: ignore

            resp = requests.post(
                "http://insurance-api/buy",
                json={"size": size, "asset": asset},
                timeout=3,
            )
            resp.raise_for_status()
            LOG.log(
                "hedge",
                size=size,
                asset=asset,
                status="ok",
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
        except Exception as exc:  # pragma: no cover - network
            LOG.log(
                "hedge_fail",
                error=str(exc),
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )

    # ------------------------------------------------------------------
    def should_trade_now(self) -> bool:
        if not self.edges_enabled.get("stealth_mode", True):
            return True
        recent_alpha = self.metrics.get("recent_alpha", 0.0)
        gas = self._estimate_gas_cost()
        active = recent_alpha > 0.1 and gas < 0.005
        if not active:
            LOG.log(
                "stealth_mode",
                reason="low_alpha or high_gas",
                active=False,
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
        return active

    # ------------------------------------------------------------------
    def evaluate_pnl(self) -> float:
        return sum(self.capital_lock.trades)

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(self.last_prices, fh)

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            with open(path) as fh:
                self.last_prices = json.load(fh)

    # ------------------------------------------------------------------
    def _record(self, domain: str, data: PriceData, opportunity: bool, spread: float, action: str = "", tx_id: str = "", pnl: float = 0.0) -> None:
        _log(
            "price",
            domain=domain,
            price=data.price,
            opportunity=opportunity,
            spread=spread,
            action=action,
            tx_id=tx_id,
            block=data.block,
            block_age=data.block_age,
            pnl=pnl,
        )

    def _detect_opportunity(self, prices: Dict[str, float]) -> Optional[Dict[str, object]]:
        domains = list(prices.keys())
        if len(domains) < 2:
            return None
        min_domain = min(domains, key=lambda d: prices[d])
        max_domain = max(domains, key=lambda d: prices[d])
        min_price = prices[min_domain]
        max_price = prices[max_domain]
        if min_price == 0:
            return None
        spread = (max_price - min_price) / min_price
        if spread >= self.threshold:
            action = (
                f"buy:{self.pools[min_domain].domain} "
                f"sell:{self.pools[max_domain].domain}"
            )
            return {
                "opportunity": True,
                "spread": spread,
                "action": action,
                "buy": min_domain,
                "sell": max_domain,
            }
        return None

    # ------------------------------------------------------------------
    def run_once(self) -> Optional[Dict[str, object]]:
        if kill_switch_triggered():
            record_kill_event(STRATEGY_ID)
            LOG.log(
                "killed",
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
            )
            return None

        if not self.should_trade_now():
            return None

        self._maybe_ghost()
        self._auto_discover()

        if self.node_selector:
            node = self.node_selector.best()
            LOG.log(
                "node_selected",
                node=node,
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )

        price_data: Dict[str, PriceData] = {}
        for label, cfg in self.pools.items():
            try:
                data = self.feed.fetch_price(cfg.pool, cfg.domain)
            except Exception as exc:  # pragma: no cover - dependency errors
                logging.warning("price fetch failed: %s", exc)
                log_error(STRATEGY_ID, str(exc), event="price_fetch")
                metrics.record_fail()
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            self._record(cfg.domain, data, False, 0.0)

        if any(d.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")) for d in price_data.values()):
            logging.warning("stale price detected")
            log_error(STRATEGY_ID, "stale price detected", event="stale_price")
            metrics.record_fail()
            return None

        prices = {k: d.price for k, d in price_data.items()}
        opp = self._detect_opportunity(prices)
        self.metrics["recent_alpha"] = float(opp["spread"]) if opp else 0.0
        if opp:
            profit = self._compute_profit(opp["buy"], opp["sell"], prices)
            if profit <= 0:
                metrics.record_fail()
                return None
            self.hedge_risk(profit, "ETH")
            if not self.capital_lock.trade_allowed():
                msg = "capital lock: trade not allowed"
                log_error(STRATEGY_ID, msg, event="capital_lock", risk_level="high")
                LOG.log(
                    "capital_lock",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="high",
                    error=msg,
                )
                return None

            if not self._check_l1_sandwich():
                return None
            self._process_intents()
            self._execute_flashloan(str(opp["buy"]), str(opp["sell"]))

            metrics.record_opportunity(float(opp["spread"]), profit, 0.0)
            _send_alert({"strategy": STRATEGY_ID, **opp, "profit": profit})

            pre = os.getenv("CROSS_ARB_STATE_PRE", "state/cross_arb_pre.json")
            post = os.getenv("CROSS_ARB_STATE_POST", "state/cross_arb_post.json")
            tx_pre = os.getenv("CROSS_ARB_TX_PRE", "state/tx_pre.json")
            tx_post = os.getenv("CROSS_ARB_TX_POST", "state/tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            start_time = datetime.now(timezone.utc)
            tx_hash = self.tx_builder.send_transaction(
                self.sample_tx,
                self.executor,
                strategy_id=STRATEGY_ID,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
            latency = (datetime.now(timezone.utc) - start_time).total_seconds()
            if self.node_selector:
                node = self.node_selector.best()
                self.node_selector.record(node, True, latency)
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)

            self.capital_lock.record_trade(profit)

            for label, data in price_data.items():
                self._record(
                    self.pools[label].domain,
                    data,
                    True,
                    float(opp["spread"]),
                    str(opp["action"]),
                    tx_id=str(tx_hash),
                    pnl=profit,
                )
        else:
            metrics.record_fail()

        return opp

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
        """Apply parameter mutations for auto-tuning.

        Currently supports updating the ``threshold`` used for spread detection.
        All errors are logged to ``logs/errors.log`` for offline audit.
        """

        if "threshold" in params:
            try:
                old = self.threshold
                self.threshold = float(params["threshold"])
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="threshold",
                    value=self.threshold,
                )
                log_mutation(
                    "param_mutation",
                    strategy_id=STRATEGY_ID,
                    param="threshold",
                    before=old,
                    after=self.threshold,
                )
            except Exception as exc:  # pragma: no cover - input validation
                log_error(STRATEGY_ID, f"mutate threshold: {exc}", event="mutate_error")
