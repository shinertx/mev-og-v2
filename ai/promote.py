"""Promotion and rollback utilities for strategies.

Module purpose and system role:
    - Move a tested strategy from staging into production.
    - Log every promotion, rejection, and rollback with rationale and evidence.

Integration points and dependencies:
    - Relies on :class:`core.logger.StructuredLogger` for audit logging.

Simulation/test hooks and kill conditions:
    - Pure Python file operations for unit tests and DRP snapshots.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from core.logger import StructuredLogger, log_error
from agents.capital_lock import CapitalLock
from agents.ops_agent import OpsAgent
from agents.drp_agent import DRPAgent
from agents.gatekeeper import gates_green
from agents.founder_gate import founder_approved
import os

LOGGER = StructuredLogger("promote")


def promote_strategy(
    src: Path,
    dst: Path,
    approved: bool,
    evidence: Dict[str, Any] | None = None,
    *,
    trace_id: str | None = None,
    capital_lock: CapitalLock | None = None,
    ops_agent: OpsAgent | None = None,
    drp_agent: DRPAgent | None = None,
) -> bool:
    """Promote strategy ``src`` to ``dst`` if ``approved``."""

    if trace_id is None:
        trace_id = os.getenv("TRACE_ID", "")

    if not approved or not founder_approved("promote"):
        LOGGER.log(
            "promotion_rejected",
            strategy_id=src.name,
            risk_level="low",
            info=evidence or {},
            trace_id=trace_id,
        )
        return False
    if capital_lock and ops_agent and drp_agent:
        if not gates_green(capital_lock, ops_agent, drp_agent):
            LOGGER.log(
                "promotion_blocked",
                strategy_id=src.name,
                risk_level="high",
                trace_id=trace_id,
            )
            return False
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        LOGGER.log(
            "promotion",
            strategy_id=src.name,
            risk_level="low",
            info={"src": str(src), "dst": str(dst), "evidence": evidence},
            trace_id=trace_id,
        )
        return True
    except Exception as exc:
        log_error(
            "promote",
            str(exc),
            strategy_id=src.name,
            event="promotion_fail",
            trace_id=trace_id,
        )
        return False


def rollback(dst: Path, reason: str, *, trace_id: str | None = None) -> bool:
    """Rollback an active strategy directory."""

    if trace_id is None:
        trace_id = os.getenv("TRACE_ID", "")
    try:
        if dst.exists():
            shutil.rmtree(dst)
        LOGGER.log(
            "rollback",
            strategy_id=dst.name,
            risk_level="high",
            error=reason,
            trace_id=trace_id,
        )
        return True
    except Exception as exc:
        log_error(
            "promote",
            str(exc),
            strategy_id=dst.name,
            event="rollback_fail",
            trace_id=trace_id,
        )
        return False
