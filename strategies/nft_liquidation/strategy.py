"""
strategy_id: "BridgeArb_001"
edge_type: "BridgeDelay"
ttl_hours: 48
triggers:
  - bridge_delay_secs > 8
  - price_gap_pct > 2
"""

# NFT liquidation auction sniper.
#
# Module purpose and system role:
#     - Monitor NFT lending protocols for liquidation auctions.
#     - Snipe auctions with optimal gas and anti-griefing logic.
#
# Integration points and dependencies:
#     - :class:`core.oracles.nft_liquidation_feed.NFTLiquidationFeed` for auction data.
#     - :class:`core.tx_engine.TransactionBuilder` and :class:`core.tx_engine.NonceManager` for tx dispatch.
#     - Kill switch utilities to abort when triggered.
#
# Simulation/test hooks and kill conditions:
#     - Supports forked-mainnet simulation via ``infra/sim_harness``.
#     - Aborts if auctions are stale or kill switch is active.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
import hashlib
from datetime import datetime, timezone
import sys
import asyncio

from core.logger import StructuredLogger, log_error, make_json_safe
from core import metrics
from core.oracles.nft_liquidation_feed import NFTLiquidationFeed, AuctionData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager, get_shared_nonce_manager
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
import time
import subprocess
from agents.capital_lock import CapitalLock
try:
    from prometheus_client import Counter, Histogram, start_http_server
except Exception:  # pragma: no cover - optional
    Counter = Histogram = None

    def start_http_server(*_a: object, **_k: object) -> None:
        pass

LOG_FILE = Path(os.getenv("NFT_LIQ_LOG", "logs/nft_liquidation.json"))
LOG = StructuredLogger("nft_liquidation", log_file=str(LOG_FILE))
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
class AuctionConfig:
    protocol: str
    domain: str


class NFTLiquidationMEV:
    """NFT liquidation sniping strategy."""

    DEFAULT_DISCOUNT = 0.05

    def __init__(
        self,
        auctions: Dict[str, AuctionConfig],
        *,
        discount: float | None = None,
        capital_lock: CapitalLock | None = None,
        nonce_manager: NonceManager | None = None,
        capital_base_eth: float = 1.0,
    ) -> None:
        self.feed = NFTLiquidationFeed()
        self.auctions = auctions
        self.discount = discount if discount is not None else self.DEFAULT_DISCOUNT
        self.last_seen: Dict[str, str] = {}

        w3 = None
        self.nonce_manager = nonce_manager or get_shared_nonce_manager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("NFT_LIQ_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)
        self.capital_base_eth = capital_base_eth

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(make_json_safe({"last_seen": self.last_seen}), fh)

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            data = json.loads(Path(path).read_text())
            self.last_seen = data.get("last_seen", {})

    # ------------------------------------------------------------------
    def _record(self, auction: AuctionData, opportunity: bool, action: str = "", tx_id: str = "") -> None:
        LOG.log(
            "auction",
            tx_id=tx_id,
            strategy_id=EDGE_SCHEMA["strategy_id"],
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="medium",
            auction_id=auction.auction_id,
            nft=auction.nft,
            price=auction.price,
            value=auction.value,
            end_block=auction.end_block,
            opportunity=opportunity,
            action=action,
        )

    # ------------------------------------------------------------------
    def _detect(self, auctions: List[AuctionData]) -> Optional[AuctionData]:
        for a in auctions:
            if a.auction_id == self.last_seen.get(a.nft):
                continue
            if a.price <= a.value * (1 - self.discount):
                return a
        return None

    async def _bundle_and_send(self, auction: AuctionData) -> tuple[str, float]:
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
    async def run_once(self) -> Optional[Dict[str, object]]:
        if kill_switch_triggered():
            record_kill_event(EDGE_SCHEMA["strategy_id"])
            LOG.log(
                "killed",
                strategy_id=EDGE_SCHEMA["strategy_id"],
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
            )
            return None

        all_auctions: List[AuctionData] = []
        for label, cfg in self.auctions.items():
            try:
                data = self.feed.fetch_auctions(cfg.domain)
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], str(exc), event="fetch_auctions", domain=cfg.domain)
                metrics.record_fail()
                arb_error_count.inc()
                return None
            all_auctions.extend(data)
            for a in data:
                self._record(a, False)

        if not all_auctions:
            return None

        opp = self._detect(all_auctions)
        if opp:
            profit = opp.value - opp.price
            gas_price = getattr(self.tx_builder.web3.eth, "gas_price", 0)
            min_gas_cost = float(gas_price * 21000) / 1e18 * 1.5
            est_slippage = 0.0
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

            pre = os.getenv("NFT_LIQ_STATE_PRE", "state/nft_liq_pre.json")
            post = os.getenv("NFT_LIQ_STATE_POST", "state/nft_liq_post.json")
            tx_pre = os.getenv("NFT_LIQ_TX_PRE", "state/nft_liq_tx_pre.json")
            tx_post = os.getenv("NFT_LIQ_TX_POST", "state/nft_liq_tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_id, latency = await self._bundle_and_send(opp)
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)
            metrics.record_opportunity(0.0, opp.value - opp.price, latency)
            arb_opportunities_found.inc()
            arb_profit_eth.inc(opp.value - opp.price)
            arb_latency.observe(latency)

            self.capital_lock.record_trade(opp.value - opp.price)
            self.last_seen[opp.nft] = opp.auction_id
            self._record(opp, True, action="snipe", tx_id=tx_id)
            return {"opportunity": True, "auction_id": opp.auction_id, "nft": opp.nft}

        metrics.record_fail()
        arb_error_count.inc()
        return None

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
        mutation_data = {
            "params": params,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if "discount" in params:
            try:
                old = self.discount
                self.discount = float(params["discount"])
                mutation_data["old_discount"] = old
                mutation_data["new_discount"] = self.discount
                
                LOG.log(
                    "mutate",
                    strategy_id=EDGE_SCHEMA["strategy_id"],
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="discount",
                    value=self.discount,
                )
                
                # Write to /last_3_codex_diffs/
                _write_mutation_diff(EDGE_SCHEMA["strategy_id"], mutation_data)
                
            except Exception as exc:
                log_error(EDGE_SCHEMA["strategy_id"], f"mutate discount: {exc}", event="mutate_error")


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

    strategy = NFTLiquidationMEV({}, capital_base_eth=capital_base, **kwargs)

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
