"""Strategy pruning utilities.

Module purpose and system role:
    - Identify underperforming strategies for removal or deactivation.
    - Logging of all prune decisions for AI audit and DRP tracing.

Integration points and dependencies:
    - Works with metrics produced by :mod:`ai.mutator.score` or strategy logs.
    - Uses :class:`core.logger.StructuredLogger` for event logging.

Simulation/test hooks and kill conditions:
    - Designed for offline analysis; deterministic logic for unit tests.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from core.logger import StructuredLogger
from ai.mutation_log import log_mutation

LOGGER = StructuredLogger("strategy_prune")


PRUNE_THRESH = {
    "pnl": 0.0,
    "risk": 1.0,
}


def prune_strategies(metrics: Dict[str, Dict[str, Any]], audit_feedback: Dict[str, bool] | None = None) -> List[str]:
    """Return list of strategy IDs flagged for pruning."""

    flagged: List[str] = []
    for sid, data in metrics.items():
        pnl = float(data.get("pnl", 0.0))
        risk = float(data.get("risk", 0.0))
        chaos_fail = bool(data.get("chaos_fail", False))
        audit_fail = False
        if audit_feedback:
            audit_fail = bool(audit_feedback.get(sid, False))

        if pnl < PRUNE_THRESH["pnl"] or risk > PRUNE_THRESH["risk"] or chaos_fail or audit_fail:
            flagged.append(sid)
            LOGGER.log(
                "prune_flag",
                strategy_id=sid,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
                error=None,
                info={"pnl": pnl, "risk": risk, "chaos_fail": chaos_fail, "audit_fail": audit_fail},
            )
            log_mutation(
                "prune_strategy",
                strategy_id=sid,
                before={"pnl": pnl, "risk": risk},
                reason="decayed_alpha" if pnl <= 0 else "high_risk",
            )
    return flagged
