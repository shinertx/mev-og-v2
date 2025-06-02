"""Risk gating via drawdown and loss limits."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.logger import StructuredLogger
from core import metrics
from .agent_registry import set_value
from .founder_gate import founder_approved
import os

LOGGER = StructuredLogger("capital_lock")


@dataclass
class CapitalLock:
    max_drawdown_pct: float
    max_loss_usd: float
    balance_usd: float
    losses: float = 0.0
    peak_balance: float = 0.0
    blocked: bool = False
    trades: list[float] = field(default_factory=list)

    # ----------------------------------------------------------
    def record_trade(self, pnl_usd: float) -> None:
        if self.blocked:
            LOGGER.log("trade_blocked", risk_level="high", error="capital_locked")
            return
        self.balance_usd += pnl_usd
        self.trades.append(pnl_usd)
        self.peak_balance = max(self.peak_balance, self.balance_usd)
        if pnl_usd < 0:
            self.losses += abs(pnl_usd)
        self._check_limits()

    # ----------------------------------------------------------
    def _check_limits(self) -> None:
        drawdown = 0.0
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - self.balance_usd) / self.peak_balance * 100
        if drawdown > self.max_drawdown_pct or self.losses > self.max_loss_usd:
            self.blocked = True
            set_value("capital_locked", True)
            LOGGER.log("risk_block", risk_level="high", error="loss_limit")
            metrics.record_alert()

    # ----------------------------------------------------------
    def trade_allowed(self) -> bool:
        return not self.blocked

    # ----------------------------------------------------------
    def unlock(self, approved: bool) -> bool:
        trace = os.getenv("TRACE_ID", "")
        if not approved or not founder_approved("capital_unlock"):
            LOGGER.log("unlock_rejected", risk_level="low", trace_id=trace)
            return False
        self.blocked = False
        set_value("capital_locked", False)
        self.losses = 0.0
        self.peak_balance = self.balance_usd
        LOGGER.log("unlock", risk_level="low", trace_id=trace)
        return True

