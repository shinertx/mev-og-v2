"""
strategy_id: "BridgeArb_001"
edge_type: "BridgeDelay"
ttl_hours: 48
triggers:
  - bridge_delay_secs > 8
  - price_gap_pct > 2
"""

# L3 Sequencer builder/sequencer MEV strategy.
#
# Module purpose and system role:
#     - Monitor L3 rollup pools for sandwich and time-band opportunities.
#     - Detect reorg windows and execute reorg arbitrage when profitable.
#
# Integration points and dependencies:
#     - :class:`core.oracles.uniswap_feed.UniswapV3Feed` for pricing data.
#     - :class:`core.tx_engine.TransactionBuilder` and :class:`core.tx_engine.NonceManager` for dispatch and replay defense.
#     - Kill switch utilities for halting execution on demand.
#
# Simulation/test hooks and kill conditions:
#     - Designed for forked-mainnet simulation with ``infra/sim_harness``.
#     - Aborts immediately if the kill switch is triggered or data is stale.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict, cast
import yaml
import time
import subprocess
import hashlib
from datetime import datetime, timezone
import sys
import asyncio
try:
    from prometheus_client import Counter, Histogram, start_http_server
except Exception:  # pragma: no cover - optional
    Counter = Histogram = None

    def start_http_server(*_a: object, **_k: object) -> None:
        pass

from core.logger import StructuredLogger, log_error, make_json_safe
from core import metrics
from core.oracles.uniswap_feed import UniswapV3Feed, PriceData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager, get_shared_nonce_manager
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from agents.capital_lock import CapitalLock

LOG_FILE = Path(os.getenv("L3_SEQ_LOG", "logs/l3_sequencer_mev.json"))
LOG = StructuredLogger("l3_sequencer_mev", log_file=str(LOG_FILE))
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
        nonce_manager: NonceManager | None = None,
        capital_base_eth: float = 1.0,
    ) -> None:
        self.feed = UniswapV3Feed()
        self.pools = pools
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self.time_band_sec = time_band_sec
        self.reorg_window = reorg_window
        self.last_prices: Dict[str, float] = {}
        self.last_block = 0

        self.capital_base_eth = capital_base_eth

        w3 = self.feed.web3s.get("ethereum") if self.feed.web3s else None
        self.nonce_manager = nonce_manager or get_shared_nonce_manager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("L3_SEQ_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(
                make_json_safe({"last_prices": self.last_prices, "last_block": self.last_block}),
                fh,
            )

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
            strategy_id=EDGE_SCHEMA["strategy_id"],
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
        return spread * self.capital_base_eth

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
    async def _bundle_and_send(self, action: str) -> tuple[str, float]:
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
            # Make it async-friendly
            await asyncio.sleep(0)  # Yield control
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
    async def run_once(self) -> Optional[Opportunity]:
        if kill_switch_triggered():
            record_kill_event(EDGE_SCHEMA["strategy_id"])
            LOG.log(
                "killed",
                strategy_id=EDGE_SCHEMA["strategy_id"],
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
                log_error(EDGE_SCHEMA["strategy_id"], str(exc), event="price_fetch", domain=cfg.domain)
                metrics.record_fail()
                arb_error_count.inc()
                return None
            price_data[label] = data
            self.last_prices[label] = data.price
            block = data.block
            timestamp = data.timestamp
            self._record(cfg.domain, data, False, 0.0)

        if not price_data:
            return None

        if any(d.block_age > int(os.getenv("PRICE_FRESHNESS_SEC", "30")) for d in price_data.values()):
            log_error(EDGE_SCHEMA["strategy_id"], "stale price detected", event="stale_price")
            metrics.record_fail()
            arb_error_count.inc()
            return None

        prices = {k: d.price for k, d in price_data.items()}
        opp = self._detect_opportunity(prices, block, timestamp)
        if opp:
            profit = float(opp["profit"])
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
                self.last_block = block
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
                self.last_block = block
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
                self.last_block = block
                return None

            pre = os.getenv("L3_SEQ_STATE_PRE", "state/l3_seq_pre.json")
            post = os.getenv("L3_SEQ_STATE_POST", "state/l3_seq_post.json")
            tx_pre = os.getenv("L3_SEQ_TX_PRE", "state/l3_seq_tx_pre.json")
            tx_post = os.getenv("L3_SEQ_TX_POST", "state/l3_seq_tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_id, latency = await self._bundle_and_send(str(opp["action"]))
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            metrics.record_opportunity(float(opp["spread"]), float(opp["profit"]), latency)
            arb_opportunities_found.inc()
            arb_profit_eth.inc(float(opp["profit"]))
            arb_latency.observe(latency)
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
            arb_error_count.inc()
            self.last_block = block

        return opp

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
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
                
                # Write to /last_3_codex_diffs/
                _write_mutation_diff(EDGE_SCHEMA["strategy_id"], mutation_data)
                
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], f"mutate threshold: {exc}", event="mutate_error")
                
        if "time_band_sec" in params:
            try:
                old = self.time_band_sec
                self.time_band_sec = int(params["time_band_sec"])
                mutation_data["old_time_band_sec"] = old
                mutation_data["new_time_band_sec"] = self.time_band_sec
                
                LOG.log(
                    "mutate",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="time_band_sec",
                    value=self.time_band_sec,
                )
                
                # Write to /last_3_codex_diffs/
                _write_mutation_diff(EDGE_SCHEMA["strategy_id"], mutation_data)
                
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], f"mutate time_band_sec: {exc}", event="mutate_error")
                
        if "reorg_window" in params:
            try:
                old = self.reorg_window
                self.reorg_window = int(params["reorg_window"])
                mutation_data["old_reorg_window"] = old
                mutation_data["new_reorg_window"] = self.reorg_window
                
                LOG.log(
                    "mutate",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="reorg_window",
                    value=self.reorg_window,
                )
                
                # Write to /last_3_codex_diffs/
                _write_mutation_diff(EDGE_SCHEMA["strategy_id"], mutation_data)
                
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], f"mutate reorg_window: {exc}", event="mutate_error")


async def run(
    block_number: int | None = None,
    chain_id: int | None = None,
    test_mode: bool = False,
    capital_base: float = 1.0,
    **kwargs: Any,
) -> None:
    """Run the strategy in a monitored loop."""

    if block_number is not None:
        os.environ["BLOCK_NUMBER"] = str(block_number)
    if chain_id is not None:
        os.environ["CHAIN_ID"] = str(chain_id)
    if test_mode:
        os.environ["TEST_MODE"] = "1"

    strategy = L3SequencerMEV({}, capital_base_eth=capital_base, **kwargs)

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
            await strategy.run_once()
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
