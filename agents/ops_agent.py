"""Operational monitoring and alert agent."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from core.logger import StructuredLogger
from .agent_registry import set_value

metrics_module: Optional[Any] = None
try:  # optional metrics; tests may stub out core
    from core import metrics as _metrics
    metrics_module = _metrics
except Exception:  # pragma: no cover - optional dependency
    pass

LOGGER = StructuredLogger("ops_agent")


class OpsAgent:
    """Monitor system health and trigger alerts."""

    def __init__(self, health_checks: Dict[str, Callable[[], bool]]) -> None:
        self.health_checks = health_checks
        self.paused = False

    # --------------------------------------------------------------
    def run_checks(self) -> None:
        failures = []
        for name, func in self.health_checks.items():
            try:
                if not func():
                    failures.append(name)
            except Exception as exc:  # pragma: no cover - runtime guard
                LOGGER.log("health_exception", strategy_id=name, risk_level="high", error=str(exc))
                failures.append(name)
        if failures:
            LOGGER.log("health_fail", strategy_id=",".join(failures), risk_level="high")
            if metrics_module:
                metrics_module.record_alert()
            self.auto_pause(reason="health_fail")
        else:
            LOGGER.log("health_ok", risk_level="low")

    # --------------------------------------------------------------
    def auto_pause(self, reason: str) -> None:
        if self.paused:
            return
        self.paused = True
        set_value("paused", True)
        LOGGER.log("auto_pause", risk_level="high", error=reason)
        if metrics_module:
            metrics_module.record_alert()

    # --------------------------------------------------------------
    def notify(self, message: str) -> None:
        webhook = os.getenv("OPS_ALERT_WEBHOOK")
        if webhook:
            try:
                import requests  # type: ignore[import-untyped]

                requests.post(webhook, json={"text": message}, timeout=5)
            except Exception as exc:  # pragma: no cover - network errors
                LOGGER.log("notify_fail", error=str(exc), risk_level="low")
        LOGGER.log("notify", risk_level="low", extra=message)

