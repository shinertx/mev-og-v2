from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, List

from core.logger import StructuredLogger, log_error
from core import metrics


@dataclass
class PerformanceTracker:
    """Track strategy profitability and failures."""

    pnl_history: List[float] = field(default_factory=list)
    fail_count: int = 0

    def record(self, success: bool, pnl: float) -> None:
        if success:
            self.pnl_history.append(pnl)
            self.fail_count = 0
        else:
            self.fail_count += 1


class BaseStrategy:
    """Base class providing cost validation and auto-pruning."""

    def __init__(self, strategy_id: str, *, prune_epochs: int | None = None, log_file: str | None = None) -> None:
        self.strategy_id = strategy_id
        self.logger = StructuredLogger(strategy_id, log_file=log_file)
        self.prune_epochs = prune_epochs or int(os.getenv("PRUNE_EPOCHS", "5"))
        self.disabled = False
        self.performance = PerformanceTracker()

    # ------------------------------------------------------------------
    def detect_alpha(self) -> Optional[Dict[str, object]]:  # pragma: no cover - interface
        return None

    def execute_trade(self, signal: Dict[str, object]) -> Optional[float]:  # pragma: no cover - interface
        return None

    # ------------------------------------------------------------------
    def validate_costs(self, expected_profit: float) -> bool:
        """Return True if expected profit exceeds all estimated costs."""
        gas = float(os.getenv("GAS_COST_OVERRIDE", "0"))
        slippage = float(os.getenv("SLIPPAGE_PCT", "0")) * expected_profit
        cex_fee = float(os.getenv("CEX_FEE_PCT", "0")) * expected_profit
        total_cost = gas + slippage + cex_fee
        ok = expected_profit - total_cost > 0
        if not ok:
            self.logger.log(
                "unprofitable",
                strategy_id=self.strategy_id,
                risk_level="low",
                profit=expected_profit,
                cost=total_cost,
            )
            log_error(self.strategy_id, "trade unprofitable", strategy_id=self.strategy_id)
        return ok

    # ------------------------------------------------------------------
    def record_result(self, success: bool, pnl: float) -> None:
        self.performance.record(success, pnl)
        if success:
            metrics.record_opportunity(0.0, pnl, 0.0)
        else:
            metrics.record_fail()
        self._check_prune()

    # ------------------------------------------------------------------
    def _check_prune(self) -> None:
        if self.disabled:
            return
        if self.performance.fail_count >= self.prune_epochs:
            self.disabled = True
            Path("logs").mkdir(exist_ok=True)
            path = Path("logs/prune.log")
            entry = {
                "strategy": self.strategy_id,
                "reason": "fail_threshold",
                "fail_count": self.performance.fail_count,
            }
            with path.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
            metrics.record_prune()
            self.logger.log("auto_prune", strategy_id=self.strategy_id, risk_level="high")
