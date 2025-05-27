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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from statistics import mean
from pathlib import Path
from typing import Dict, Optional

try:  # webhook optional
    import requests
except Exception:  # pragma: no cover - allow missing dependency
    requests = None  # type: ignore

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager
from core.logger import log_error

from core.oracles.uniswap_feed import UniswapV3Feed, PriceData
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event

LOG_FILE = Path(os.getenv("CROSS_ARB_LOG", "logs/cross_domain_arb.json"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)

STRATEGY_ID = "cross_domain_arb"

# Metrics storage
METRICS = {
    "opportunities": 0,
    "fails": 0,
    "spreads": [],
}


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler serving in-memory metrics."""
    def do_GET(self) -> None:  # pragma: no cover - simple server
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        avg_spread = mean(METRICS["spreads"]) if METRICS["spreads"] else 0.0
        body = (
            f"opportunities_total {METRICS['opportunities']}\n"
            f"fails_total {METRICS['fails']}\n"
            f"spread_average {avg_spread}\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_metrics_server(port: int = 8000) -> HTTPServer:
    """Start background metrics server for Prometheus scraping."""
    server = HTTPServer(("0.0.0.0", port), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _log(entry: Dict[str, object]) -> None:
    with LOG_FILE.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _send_alert(payload: Dict[str, object]) -> None:
    """Send JSON payload to webhook URL if configured."""
    url = os.getenv("ARB_ALERT_WEBHOOK")
    if not url or requests is None:
        return
    try:  # pragma: no cover - network
        requests.post(url, json=payload, timeout=5)
    except Exception as exc:  # pragma: no cover - network
        logging.warning("webhook failed: %s", exc)
        log_error(STRATEGY_ID, f"webhook failed: {exc}", event="webhook_fail")


@dataclass
class PoolConfig:
    """Configuration for a Uniswap pool on a given domain."""
    pool: str
    domain: str


class CrossDomainArb:
    """Detect price spreads across domains."""

    DEFAULT_THRESHOLD = 0.003

    def __init__(self, pools: Dict[str, PoolConfig], threshold: float | None = None) -> None:
        self.feed = UniswapV3Feed()
        self.pools = pools
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.last_prices: Dict[str, float] = {}

        # transaction execution setup
        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = NonceManager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("ARB_EXECUTOR_ADDR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

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
    def _record(self, domain: str, data: PriceData, opportunity: bool, spread: float, action: str = "", tx_id: str = "") -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain": domain,
            "price": data.price,
            "opportunity": opportunity,
            "spread": spread,
            "action": action,
            "tx_id": tx_id,
            "strategy_id": STRATEGY_ID,
            "risk_level": "low",
            "mutation_id": os.getenv("MUTATION_ID", "dev"),
            "block_number": data.block,
            "block_age_sec": data.block_age,
        }
        _log(entry)

    def _detect_opportunity(self, prices: Dict[str, float]) -> Optional[Dict[str, object]]:
        domains = list(prices.keys())
        if not domains:
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
            }
        return None

    # ------------------------------------------------------------------
    def run_once(self) -> Optional[Dict[str, object]]:
        if kill_switch_triggered():
            record_kill_event(STRATEGY_ID)
            return None

        price_data: Dict[str, PriceData] = {}
        for label, cfg in self.pools.items():
            try:
                data = self.feed.fetch_price(cfg.pool, cfg.domain)
            except Exception as exc:  # pragma: no cover - dependency errors
                logging.warning("price fetch failed: %s", exc)
                log_error(STRATEGY_ID, str(exc), event="price_fetch")
                METRICS["fails"] += 1
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            self._record(cfg.domain, data, False, 0.0)

        if any(d.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")) for d in price_data.values()):
            logging.warning("stale price detected")
            log_error(STRATEGY_ID, "stale price detected", event="stale_price")
            METRICS["fails"] += 1
            return None

        prices = {k: d.price for k, d in price_data.items()}
        opp = self._detect_opportunity(prices)
        if opp:
            METRICS["opportunities"] += 1
            METRICS["spreads"].append(float(opp["spread"]))
            _send_alert({"strategy": STRATEGY_ID, **opp})

            pre = os.getenv("CROSS_ARB_STATE_PRE", "state/cross_arb_pre.json")
            post = os.getenv("CROSS_ARB_STATE_POST", "state/cross_arb_post.json")
            tx_pre = os.getenv("CROSS_ARB_TX_PRE", "state/tx_pre.json")
            tx_post = os.getenv("CROSS_ARB_TX_POST", "state/tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_hash = self.tx_builder.send_transaction(self.sample_tx, self.executor, strategy_id=STRATEGY_ID, mutation_id=os.getenv("MUTATION_ID", "dev"), risk_level="low")
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)

            for label, data in price_data.items():
                self._record(self.pools[label].domain, data, True, float(opp["spread"]), str(opp["action"]), tx_id=str(tx_hash))
        else:
            METRICS["fails"] += 1

        return opp

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, object]) -> None:
        """Apply parameter mutations for auto-tuning.

        Currently supports updating the ``threshold`` used for spread detection.
        All errors are logged to ``logs/errors.log`` for offline audit.
        """

        if "threshold" in params:
            try:
                self.threshold = float(params["threshold"])
            except Exception as exc:  # pragma: no cover - input validation
                log_error(STRATEGY_ID, f"mutate threshold: {exc}", event="mutate_error")
