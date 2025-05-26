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

LOGGER = StructuredLogger("promote")


def promote_strategy(src: Path, dst: Path, approved: bool, evidence: Dict[str, Any] | None = None) -> bool:
    """Promote strategy ``src`` to ``dst`` if ``approved``."""

    if not approved:
        LOGGER.log("promotion_rejected", strategy_id=src.name, risk_level="low", info=evidence or {})
        return False
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        LOGGER.log(
            "promotion", strategy_id=src.name, risk_level="low", info={"src": str(src), "dst": str(dst), "evidence": evidence}
        )
        return True
    except Exception as exc:
        log_error("promote", str(exc), strategy_id=src.name, event="promotion_fail")
        return False


def rollback(dst: Path, reason: str) -> bool:
    """Rollback an active strategy directory."""

    try:
        if dst.exists():
            shutil.rmtree(dst)
        LOGGER.log("rollback", strategy_id=dst.name, risk_level="high", error=reason)
        return True
    except Exception as exc:
        log_error("promote", str(exc), strategy_id=dst.name, event="rollback_fail")
        return False
