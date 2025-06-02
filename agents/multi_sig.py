"""Simple multi-sig approval stub."""

from __future__ import annotations

from typing import Any, Dict

from core.logger import StructuredLogger
from .founder_gate import founder_approved

LOG = StructuredLogger("multi_sig")


class MultiSigApproval:
    """Request founder multi-sig approval for critical actions."""

    def __init__(self, provider: str = "gnosis") -> None:
        self.provider = provider

    def request(self, action: str, payload: Dict[str, Any]) -> bool:
        """Return True if approval granted."""
        try:
            if founder_approved(action):
                LOG.log("multisig_approved", action=action, risk_level="low")
                return True
            LOG.log("multisig_blocked", action=action, risk_level="high")
            return False
        except Exception as exc:  # pragma: no cover - runtime guard
            LOG.log("multisig_error", action=action, error=str(exc), risk_level="high")
            return False
