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
import json
import hashlib

from core.logger import StructuredLogger, make_json_safe
from ai.mutation_log import log_mutation

LOGGER = StructuredLogger("strategy_prune")


PRUNE_THRESH = {
    "pnl": 0.0,
    "sharpe": 0.0,
    "drawdown": 0.2,
    "win_rate": 0.5,
    "failures": 0,
}


def _version_hash(sid: str, data: Dict[str, Any]) -> str:
    safe = make_json_safe({"sid": sid, "data": data})
    digest = hashlib.sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()
    return digest[:8]


def prune_strategies(metrics: Dict[str, Dict[str, Any]], audit_feedback: Dict[str, bool] | None = None) -> List[str]:
    """Return list of strategy IDs flagged for pruning."""

    flagged: List[str] = []
    for sid, data in metrics.items():
        pnl = float(data.get("realized_pnl", 0.0))
        sharpe = float(data.get("sharpe", 0.0))
        drawdown = float(data.get("drawdown", 0.0))
        win_rate = float(data.get("win_rate", 0.0))
        failures = int(data.get("failures", 0))
        audit_fail = bool(audit_feedback.get(sid, False)) if audit_feedback else False

        reasons: List[str] = []
        if pnl < PRUNE_THRESH["pnl"]:
            reasons.append("negative_pnl")
        if sharpe < PRUNE_THRESH["sharpe"]:
            reasons.append("low_sharpe")
        if drawdown > PRUNE_THRESH["drawdown"]:
            reasons.append("high_drawdown")
        if win_rate < PRUNE_THRESH["win_rate"]:
            reasons.append("low_win_rate")
        if failures > PRUNE_THRESH["failures"]:
            reasons.append("failure_modes")
        if audit_fail:
            reasons.append("audit_fail")

        if reasons:
            flagged.append(sid)
            vh = _version_hash(sid, data)
            LOGGER.log(
                "prune_flag",
                strategy_id=sid,
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                risk_level="high",
                error=None,
                info={
                    "pnl": pnl,
                    "sharpe": sharpe,
                    "drawdown": drawdown,
                    "win_rate": win_rate,
                    "failures": failures,
                    "audit_fail": audit_fail,
                    "version": vh,
                },
            )
            log_mutation(
                "prune_strategy",
                strategy_id=sid,
                before={
                    "pnl": pnl,
                    "sharpe": sharpe,
                    "drawdown": drawdown,
                    "win_rate": win_rate,
                    "failures": failures,
                },
                reason=",".join(reasons),
                version_hash=vh,
                parent_hash=data.get("parent_hash"),
            )
    return flagged
