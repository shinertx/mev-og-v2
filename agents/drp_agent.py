"""Track DRP snapshot health for gating."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

from core.logger import StructuredLogger
from .agent_registry import set_value

LOGGER = StructuredLogger("drp_agent")


@dataclass
class DRPAgent:
    """Simple DRP health tracker."""

    ready: bool = True

    # --------------------------------------------------------------
    def _latest_export_time(self, export_dir: str = "export") -> datetime | None:
        """Return timestamp of the most recent DRP export in ``export_dir``."""
        path = Path(export_dir)
        files = sorted(path.glob("drp_export_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        return datetime.utcfromtimestamp(files[0].stat().st_mtime)

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

    # --------------------------------------------------------------
    def auto_recover(self, *, export_dir: str = "export", timeout: int = 3600) -> None:
        """Trigger rollback if DRP has been unhealthy for longer than ``timeout`` seconds."""
        ts = self._latest_export_time(export_dir)
        if ts is None or self.ready:
            return
        if datetime.utcnow() - ts > timedelta(seconds=timeout):
            try:
                subprocess.run([
                    "bash",
                    "scripts/rollback.sh",
                    f"--export-dir={export_dir}",
                ], check=True)
                LOGGER.log("auto_rollback", risk_level="high")
                self.ready = True
                set_value("drp_ready", True)
            except Exception as exc:  # pragma: no cover - runtime failures
                LOGGER.log("auto_rollback_fail", risk_level="high", error=str(exc))
