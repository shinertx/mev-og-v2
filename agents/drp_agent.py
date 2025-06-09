"""Track DRP snapshot health for gating."""

from __future__ import annotations

from dataclasses import dataclass

from core.logger import StructuredLogger
from .agent_registry import set_value

LOGGER = StructuredLogger("drp_agent")


@dataclass
class DRPAgent:
    """Simple DRP health tracker."""

    ready: bool = True

    # --------------------------------------------------------------
    def record_export(self, success: bool) -> None:
        """Record DRP export result."""
        self.ready = success
        set_value("drp_ready", success)
        if success:
            LOGGER.log("export_ok", risk_level="low")
        else:
            LOGGER.log("export_fail", risk_level="high")
            try:
                from core import metrics as _metrics
                _metrics.record_drp_anomaly()
            except Exception:
                pass

    # --------------------------------------------------------------
    def is_ready(self) -> bool:
        """Return True if DRP is healthy."""
        return self.ready
