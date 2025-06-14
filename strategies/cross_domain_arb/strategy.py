"""
strategy_id: "BridgeArb_001"
edge_type: "BridgeDelay"
ttl_hours: 48
triggers:
  - bridge_delay_secs > 8
  - price_gap_pct > 2
"""

# mypy: ignore-errors
# Cross-domain ETH/USDC price arbitrage detection strategy.
#
# Module purpose and system role:
#     - Scan Ethereum, Arbitrum, and Optimism Uniswap V3 pools for price
#       discrepancies.
#     - Log actionable arbitrage signals with DRP snapshot/restore support.
#
# Integration points and dependencies:
#     - Utilizes :class:`core.oracles.uniswap_feed.UniswapV3Feed` for price data.
#     - Relies on kill switch utilities and TransactionBuilder for execution.
#
# Simulation/test hooks and kill conditions:
#     - Designed for forked-mainnet simulation via infra/sim_harness.
#     - Aborts operation if kill switch is triggered.

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
import time
import asyncio
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Tuple, TypedDict, List
import hashlib

try:  # webhook optional
    import requests
except Exception:  # pragma: no cover - allow missing dependency
    requests = None  # type: ignore

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager, get_shared_nonce_manager
from core.logger import StructuredLogger, log_error, make_json_safe
import yaml
from core import metrics
from agents.capital_lock import CapitalLock
from core.strategy_base import BaseStrategy

try:
    from prometheus_client import Counter, Histogram, start_http_server
except Exception:  # pragma: no cover - optional
    Counter = Histogram = None

    def start_http_server(*_a: object, **_k: object) -> None:
        pass

from core.oracles.uniswap_feed import UniswapV3Feed, PriceData
from core.oracles.intent_feed import IntentFeed, IntentData
from core.mempool_monitor import MempoolMonitor
from core.node_selector import NodeSelector
from ai.intent_classifier import classify_intent
from ai.intent_ghost import ghost_intent
from adapters.flashloan_adapter import FlashloanAdapter
from adapters.pool_scanner import PoolScanner
from adapters.social_alpha import scrape_social_keywords
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from ai.mutation_log import log_mutation

LOG_FILE = Path(os.getenv("CROSS_ARB_LOG", "logs/cross_domain_arb.json"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)

EDGE_SCHEMA: Dict[str, Any] = yaml.safe_load(__doc__ or "")
STRATEGY_ID = EDGE_SCHEMA["strategy_id"]

LOG = StructuredLogger("cross_domain_arb", log_file=str(LOG_FILE))

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


class BridgeConfig(TypedDict, total=False):
    """Bridge cost assumptions between domains."""

    cost: float
    latency_sec: int


def start_metrics_server(port: int = 8000) -> None:
    """Backward compatible helper to start metrics server using Prometheus."""
    try:
        start_http_server(port)
    except Exception:
        pass


def _log(event: str, **entry: object) -> None:
    LOG.log(event, strategy_id=EDGE_SCHEMA["strategy_id"], mutation_id=os.getenv("MUTATION_ID", "dev"), risk_level="low", **entry)


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
        log_error(EDGE_SCHEMA["strategy_id"], f"webhook failed: {exc}", event="webhook_fail")


def _write_mutation_diff(strategy_id: str, mutation_data: Dict[str, Any]) -> None:
    """Write mutation diff to /last_3_codex_diffs/ directory."""
    try:
        diff_dir = Path("/last_3_codex_diffs")
        diff_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a hash for the prompt
        prompt_hash = hashlib.sha256(
            json.dumps(mutation_data, sort_keys=True).encode()
        ).hexdigest()[:8]
        
        # Create filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{strategy_id}_{timestamp}_{prompt_hash}.json"
        
        # Keep only last 3 diffs
        existing_files = sorted(
            [f for f in diff_dir.glob(f"{strategy_id}_*.json")],
            key=lambda x: x.stat().st_mtime
        )
        
        if len(existing_files) >= 3:
            for old_file in existing_files[:-2]:
                old_file.unlink()
        
        # Write the new diff
        diff_path = diff_dir / filename
        with open(diff_path, "w") as f:
            json.dump({
                "strategy_id": strategy_id,
                "timestamp": timestamp,
                "prompt_hash": prompt_hash,
                "mutation": mutation_data
            }, f, indent=2)
            
    except Exception as exc:
        log_error(strategy_id, f"Failed to write mutation diff: {exc}", event="mutation_diff_error")


@dataclass
class PoolConfig:
    """Configuration for a Uniswap pool on a given domain."""
    pool: str
    domain: str


class CrossDomainArb(BaseStrategy):
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
        nonce_manager: NonceManager | None = None,
        prune_epochs: int | None = None,
        capital_base_eth: float = 1.0,
    ) -> None:
        super().__init__(STRATEGY_ID, prune_epochs=prune_epochs, log_file=str(LOG_FILE))
        self.feed = UniswapV3Feed()
        self.pools = pools
        self.bridge_costs = bridge_costs
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.last_prices: Dict[str, float] = {}

        self.capital_base_eth = capital_base_eth

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

        # transaction execution setup
        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = nonce_manager or get_shared_nonce_manager(w3)
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
            priority_fee = int(float(os.getenv("PRIORITY_FEE_GWEI", "2")) * 1e9)
            gas_estimate = self.tx_builder.web3.eth.estimate_gas({})
            return float((gas_price + priority_fee) * gas_estimate) / 1e18
        except Exception:
            return float(os.getenv("GAS_COST_OVERRIDE", "0"))

    def _compute_profit(self, buy: str, sell: str, prices: Dict[str, float]) -> float:
        price_buy = prices[buy]
        price_sell = prices[sell]
        spread = price_sell - price_buy
        bridge_fee = self.bridge_costs.get((buy, sell), {}).get("cost", 0.0)
        slippage_pct = float(os.getenv("SLIPPAGE_PCT", "0"))
        slippage = price_buy * slippage_pct * self.capital_base_eth
        gas_cost = self._estimate_gas_cost()
        return (spread * self.capital_base_eth) - gas_cost - bridge_fee - slippage

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
                    strategy_id=EDGE_SCHEMA["strategy_id"],
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
                    strategy_id=EDGE_SCHEMA["strategy_id"],
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
                        strategy_id=EDGE_SCHEMA["strategy_id"],
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
            start_time = datetime.now(timezone.utc)
            try:
                front = self.tx_builder.send_transaction(
                    self.sample_tx,
                    self.executor,
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )
                back = self.tx_builder.send_transaction(
                    self.sample_tx,
                    self.executor,
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                )
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], f"sandwich tx fail: {exc}", event="sandwich_fail")
                metrics.record_fail()
                arb_error_count.inc()
                return False
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            latency = (datetime.now(timezone.utc) - start_time).total_seconds()
            LOG.log(
                "sandwich",
                tx_id=str(front),
                related=str(back),
                bridge_tx=str(tx.get("hash")),
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
            metrics.record_opportunity(0.0, 0.0, latency)
            arb_opportunities_found.inc()
            arb_profit_eth.inc(0.0)
            arb_latency.observe(latency)
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
                log_error(EDGE_SCHEMA["strategy_id"], f"intent fetch: {exc}", event="intent_fetch", domain=domain)
                continue
            for intent in intents:
                dest = classify_intent(intent.__dict__)
                LOG.log(
                    "intent_route",
                    intent_id=intent.intent_id,
                    predicted=dest,
                    domain=domain,
                    strategy_id=EDGE_SCHEMA["strategy_id"],
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
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
        except Exception as exc:
            log_error(EDGE_SCHEMA["strategy_id"], f"flashloan: {exc}", event="flashloan_fail")

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
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
        except Exception as exc:  # pragma: no cover - network
            LOG.log(
                "hedge_fail",
                error=str(exc),
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )

    # ------------------------------------------------------------------
    def should_trade_now(self) -> bool:
        if not self.edges_enabled.get("stealth_mode", True):
            return True

        # NEW: Block trading if GAS_COST_OVERRIDE is set and high
        gas_override = os.getenv("GAS_COST_OVERRIDE")
        if gas_override is not None:
            try:
                gas_val = float(gas_override)
                if gas_val >= 0.005:
                    LOG.log(
                        "stealth_mode",
                        reason="GAS_COST_OVERRIDE high",
                        active=False,
                        strategy_id=EDGE_SCHEMA["strategy_id"],
                        mutation_id=os.getenv("MUTATION_ID", "dev"),
                        risk_level="low",
                    )
                    return False
            except Exception:
                pass  # fallback to normal flow if conversion fails

        recent_alpha = self.metrics.get("recent_alpha", 0.0)
        gas = self._estimate_gas_cost()
        active = recent_alpha > 0.1 and gas < 0.005
        if not active:
            LOG.log(
                "stealth_mode",
                reason="low_alpha or high_gas",
                active=False,
                strategy_id=EDGE_SCHEMA["strategy_id"],
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
            json.dump(make_json_safe(self.last_prices), fh)

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

    def _validate_price_data(self, data: PriceData) -> bool:
        """Ensure price feed schema and freshness are valid."""
        if not isinstance(data.price, (int, float)):
            log_error(EDGE_SCHEMA["strategy_id"], "invalid price type", event="feed_schema")
            return False
        if data.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")):
            log_error(EDGE_SCHEMA["strategy_id"], "stale price detected", event="stale_price")
            return False
        return True

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
        if self.disabled:
            return None
        if kill_switch_triggered():
            record_kill_event(EDGE_SCHEMA["strategy_id"])
            LOG.log(
                "killed",
                strategy_id=EDGE_SCHEMA["strategy_id"],
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
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )

        price_data: Dict[str, PriceData] = {}
        for label, cfg in self.pools.items():
            try:
                data = self.feed.fetch_price(cfg.pool, cfg.domain)
            except Exception as exc:  # pragma: no cover - dependency errors
                logging.warning("price fetch failed: %s", exc)
                log_error(EDGE_SCHEMA["strategy_id"], str(exc), event="price_fetch")
                metrics.record_fail()
                arb_error_count.inc()
                return None
            if not self._validate_price_data(data):
                metrics.record_fail()
                arb_error_count.inc()
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            self._record(cfg.domain, data, False, 0.0)

        if any(d.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")) for d in price_data.values()):
            logging.warning("stale price detected")
            log_error(EDGE_SCHEMA["strategy_id"], "stale price detected", event="stale_price")
            metrics.record_fail()
            arb_error_count.inc()
            return None

        prices = {k: d.price for k, d in price_data.items()}
        opp = self._detect_opportunity(prices)
        self.metrics["recent_alpha"] = float(opp["spread"]) if opp else 0.0
        if opp:
            profit = self._compute_profit(opp["buy"], opp["sell"], prices)
            if profit <= 0 or not self.validate_costs(profit):
                self.record_result(False, profit)
                return None
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
            self.hedge_risk(profit, "ETH")
            if not self.capital_lock.trade_allowed():
                msg = "capital lock: trade not allowed"
                log_error(EDGE_SCHEMA["strategy_id"], msg, event="capital_lock", risk_level="high")
                LOG.log(
                    "capital_lock",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="high",
                    error=msg,
                )
                return None

            if not self._check_l1_sandwich():
                return None
            self._process_intents()
            self._execute_flashloan(str(opp["buy"]), str(opp["sell"]))

            start_time = datetime.now(timezone.utc)
            _send_alert({"strategy": STRATEGY_ID, **opp, "profit": profit})

            pre = os.getenv("CROSS_ARB_STATE_PRE", "state/cross_arb_pre.json")
            post = os.getenv("CROSS_ARB_STATE_POST", "state/cross_arb_post.json")
            tx_pre = os.getenv("CROSS_ARB_TX_PRE", "state/tx_pre.json")
            tx_post = os.getenv("CROSS_ARB_TX_POST", "state/tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_hash = self.tx_builder.send_transaction(
                self.sample_tx,
                self.executor,
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="low",
            )
            latency = (datetime.now(timezone.utc) - start_time).total_seconds()
            if self.node_selector:
                node = self.node_selector.best()
                self.node_selector.record(node, True, latency)
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)

            metrics.record_opportunity(float(opp["spread"]), profit, latency)
            arb_opportunities_found.inc()
            arb_profit_eth.inc(profit)
            arb_latency.observe(latency)

            self.capital_lock.record_trade(profit)

            self.performance.record(True, profit)
            self._check_prune()

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
            self.record_result(False, 0.0)

        return opp

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
        """Apply parameter mutations for auto-tuning.

        Currently supports updating the ``threshold`` used for spread detection.
        All errors are logged to ``logs/errors.log`` for offline audit.
        """

        mutation_data = {
            "params": params,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if "threshold" in params:
            try:
                old = self.threshold
                self.threshold = float(params["threshold"])
                mutation_data["old_threshold"] = old
                mutation_data["new_threshold"] = self.threshold
                
                LOG.log(
                    "mutate",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="threshold",
                    value=self.threshold,
                )
                log_mutation(
                    "param_mutation",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    param="threshold",
                    before=old,
                    after=self.threshold,
                )
                
                # Write to /last_3_codex_diffs/
                _write_mutation_diff(EDGE_SCHEMA["strategy_id"], mutation_data)
                
            except Exception as exc:  # pragma: no cover - input validation
                log_error(EDGE_SCHEMA["strategy_id"], f"mutate threshold: {exc}", event="mutate_error")


async def run(
    block_number: int | None = None,
    chain_id: int | None = None,
    test_mode: bool = False,
    capital_base: float = 1.0,
    **kwargs: Any,
) -> None:
    """Run the strategy in a monitored loop.

    The following environment variables tune kill conditions:

    - ``ARB_ERROR_LIMIT`` – consecutive error allowance (default ``3``)
    - ``ARB_LATENCY_THRESHOLD`` – allowed average latency in seconds (default ``30``)
    """

    if block_number is not None:
        os.environ["BLOCK_NUMBER"] = str(block_number)
    if chain_id is not None:
        os.environ["CHAIN_ID"] = str(chain_id)
    if test_mode:
        os.environ["TEST_MODE"] = "1"

    strategy = CrossDomainArb({}, {}, capital_base_eth=capital_base, **kwargs)

    error_limit = int(os.getenv("ARB_ERROR_LIMIT", "3"))
    latency_threshold = float(os.getenv("ARB_LATENCY_THRESHOLD", "30"))
    errors = 0
    total_latency = 0.0
    runs = 0

    def _snapshot_state() -> str | None:
        cmd = ["bash", "scripts/export_state.sh"]
        env = os.environ.copy()
        env["EXPORT_DIR"] = "/telemetry/drp"
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
            for line in result.stdout.splitlines():
                if line.startswith("Export created at "):
                    return line.split("Export created at ", 1)[1].strip()
        except FileNotFoundError:
            log_error(EDGE_SCHEMA["strategy_id"], "export_state.sh missing", event="snapshot_fail")
        except subprocess.CalledProcessError as exc:
            log_error(EDGE_SCHEMA["strategy_id"], f"snapshot fail: {exc.stderr}", event="snapshot_fail")
        return None

    while True:
        if kill_switch_triggered():
            archive = _snapshot_state()
            record_kill_event(EDGE_SCHEMA["strategy_id"], archive)
            sys.exit(137)

        start = time.monotonic()
        try:
            strategy.run_once()
            errors = 0
        except Exception as exc:  # pragma: no cover - runtime error
            log_error(EDGE_SCHEMA["strategy_id"], str(exc), event="run_error")
            arb_error_count.inc()
            errors += 1
        latency = time.monotonic() - start
        arb_latency.observe(latency)
        total_latency += latency
        runs += 1
        avg_latency = total_latency / runs

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

        if avg_latency > latency_threshold or errors > error_limit:
            archive = _snapshot_state()
            record_kill_event(EDGE_SCHEMA["strategy_id"], archive)
            sys.exit(137)
        if test_mode:
            break
        await asyncio.sleep(float(os.getenv("RUN_INTERVAL", "1")))


if __name__ == "__main__":
    asyncio.run(run())
