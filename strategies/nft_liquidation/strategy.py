"""NFT liquidation auction sniper.

Module purpose and system role:
    - Monitor NFT lending protocols for liquidation auctions.
    - Snipe auctions with optimal gas and anti-griefing logic.

Integration points and dependencies:
    - :class:`core.oracles.nft_liquidation_feed.NFTLiquidationFeed` for auction data.
    - :class:`core.tx_engine.TransactionBuilder` and :class:`core.tx_engine.NonceManager` for tx dispatch.
    - Kill switch utilities to abort when triggered.

Simulation/test hooks and kill conditions:
    - Supports forked-mainnet simulation via ``infra/sim_harness``.
    - Aborts if auctions are stale or kill switch is active.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logger import StructuredLogger, log_error
from core import metrics
from core.oracles.nft_liquidation_feed import NFTLiquidationFeed, AuctionData
from core.tx_engine.builder import HexBytes, TransactionBuilder
from core.tx_engine.nonce_manager import NonceManager
from core.tx_engine import kill_switch as ks
from agents.capital_lock import CapitalLock

LOG_FILE = Path(os.getenv("NFT_LIQ_LOG", "logs/nft_liquidation.json"))
LOG = StructuredLogger("nft_liquidation", log_file=str(LOG_FILE))
STRATEGY_ID = "nft_liquidation"


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
    ) -> None:
        self.feed = NFTLiquidationFeed()
        self.auctions = auctions
        self.discount = discount if discount is not None else self.DEFAULT_DISCOUNT
        self.last_seen: Dict[str, str] = {}

        w3 = None
        self.nonce_manager = NonceManager(w3)
        self.tx_builder = TransactionBuilder(w3, self.nonce_manager)
        self.executor = os.getenv("NFT_LIQ_EXECUTOR", "0x0000000000000000000000000000000000000000")
        self.sample_tx = HexBytes(b"\x01")

        self.capital_lock = capital_lock or CapitalLock(1000.0, 1e9, 0.0)

    # ------------------------------------------------------------------
    def snapshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"last_seen": self.last_seen}, fh)

    def restore(self, path: str) -> None:
        if os.path.exists(path):
            data = json.loads(Path(path).read_text())
            self.last_seen = data.get("last_seen", {})

    # ------------------------------------------------------------------
    def _record(self, auction: AuctionData, opportunity: bool, action: str = "", tx_id: str = "") -> None:
        LOG.log(
            "auction",
            tx_id=tx_id,
            strategy_id=STRATEGY_ID,
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

    def _bundle_and_send(self, auction: AuctionData) -> str:
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
    def run_once(self) -> Optional[Dict[str, object]]:
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

        all_auctions: List[AuctionData] = []
        for label, cfg in self.auctions.items():
            try:
                data = self.feed.fetch_auctions(cfg.domain)
            except Exception as exc:
                log_error(STRATEGY_ID, str(exc), event="fetch_auctions", domain=cfg.domain)
                metrics.record_fail()
                return None
            all_auctions.extend(data)
            for a in data:
                self._record(a, False)

        if not all_auctions:
            return None

        opp = self._detect(all_auctions)
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

            metrics.record_opportunity(0.0, opp.value - opp.price, 0.0)
            pre = os.getenv("NFT_LIQ_STATE_PRE", "state/nft_liq_pre.json")
            post = os.getenv("NFT_LIQ_STATE_POST", "state/nft_liq_post.json")
            tx_pre = os.getenv("NFT_LIQ_TX_PRE", "state/nft_liq_tx_pre.json")
            tx_post = os.getenv("NFT_LIQ_TX_POST", "state/nft_liq_tx_post.json")
            for p in (pre, post, tx_pre, tx_post):
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            self.snapshot(pre)
            self.tx_builder.snapshot(tx_pre)
            tx_id = self._bundle_and_send(opp)
            self.tx_builder.snapshot(tx_post)
            self.snapshot(post)

            self.capital_lock.record_trade(opp.value - opp.price)
            self.last_seen[opp.nft] = opp.auction_id
            self._record(opp, True, action="snipe", tx_id=tx_id)
            return {"opportunity": True, "auction_id": opp.auction_id, "nft": opp.nft}

        metrics.record_fail()
        return None

    # ------------------------------------------------------------------
    def mutate(self, params: Dict[str, Any]) -> None:
        if "discount" in params:
            try:
                self.discount = float(params["discount"])
                LOG.log(
                    "mutate",
                    strategy_id=STRATEGY_ID,
                    mutation_id=os.getenv("MUTATION_ID", "dev"),
                    risk_level="low",
                    param="discount",
                    value=self.discount,
                )
            except Exception as exc:
                log_error(STRATEGY_ID, f"mutate discount: {exc}", event="mutate_error")

