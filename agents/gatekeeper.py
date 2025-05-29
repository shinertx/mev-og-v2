"""Aggregate agent gating logic."""

from __future__ import annotations

from core.logger import StructuredLogger
from core.tx_engine.kill_switch import kill_switch_triggered
from .capital_lock import CapitalLock
from .ops_agent import OpsAgent
from .drp_agent import DRPAgent

LOGGER = StructuredLogger("gatekeeper")


def gates_green(lock: CapitalLock, ops: OpsAgent, drp: DRPAgent) -> bool:
    """Return ``True`` if all agent gates allow execution."""
    if kill_switch_triggered():
        LOGGER.log("kill_switch", risk_level="high")
        return False
    if not lock.trade_allowed():
        LOGGER.log("capital_lock", risk_level="high")
        return False
    if ops.paused:
        LOGGER.log("ops_paused", risk_level="high")
        return False
    if not drp.is_ready():
        LOGGER.log("drp_not_ready", risk_level="high")
        return False
    LOGGER.log("all_green", risk_level="low")
    return True
