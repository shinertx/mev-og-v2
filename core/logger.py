"""Structured JSON logger for MEV-OG modules.

Module purpose and system role:
    - Provide production-grade logging with consistent schema.
    - Emits JSON lines for Prometheus and AI audit ingestion.

Integration points and dependencies:
    - Minimal dependencies (standard library only).
    - Other modules instantiate ``StructuredLogger`` to record events.

Simulation/test hooks and kill conditions:
    - Hooks allow test suites and audit agents to trace log output.
    - Designed for offline use; no network dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

try:  # optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional
    requests = None  # type: ignore


def _error_log_file() -> Path:
    """Return the configured error log file path."""

    return Path(os.getenv("ERROR_LOG_FILE", "logs/errors.log"))


def log_error(
    module: str,
    error: str,
    *,
    tx_id: str = "",
    strategy_id: str = "",
    mutation_id: str = "",
    risk_level: str = "",
    block: int | str | None = None,
    trace_id: str | None = None,
    **extra: Any,
) -> None:
    """Write structured error entry to ``logs/errors.log``."""

    if trace_id is None:
        trace_id = os.getenv("TRACE_ID", "")
    if block is None:
        block = os.getenv("BLOCK", "")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "error": error,
        "tx_id": tx_id,
        "strategy_id": strategy_id,
        "mutation_id": mutation_id,
        "risk_level": risk_level,
        "block": block,
        "trace_id": trace_id,
        **extra,
    }
    path = _error_log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


_HOOKS: List[Callable[[Dict[str, Any]], None]] = []
_ALERT_WEBHOOKS = [w for w in os.getenv("OPS_ALERT_WEBHOOK", "").split(",") if w]


def _send_alert(message: str) -> None:
    if not _ALERT_WEBHOOKS or requests is None:
        return
    for url in _ALERT_WEBHOOKS:
        try:  # pragma: no cover - network
            requests.post(url, json={"text": message}, timeout=5)
        except Exception:
            pass


def register_hook(func: Callable[[Dict[str, Any]], None]) -> None:
    """Register ``func`` to receive every log entry."""
    _HOOKS.append(func)


class StructuredLogger:
    """Write structured JSON logs to file and broadcast to hooks."""

    def __init__(self, module: str, log_file: str | None = None) -> None:
        self.module = module
        if log_file is None:
            env_var = f"{module.upper()}_LOG"
            log_file = os.getenv(env_var, f"logs/{module}.json")
        self.path = Path(log_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def log(
        self,
        event: str,
        *,
        tx_id: str = "",
        strategy_id: str = "",
        mutation_id: str = "",
        risk_level: str = "",
        block: int | str | None = None,
        error: str | None = None,
        trace_id: str | None = None,
        **extra: Any,
    ) -> None:
        """Append log entry to file and send to hooks."""

        if trace_id is None:
            trace_id = os.getenv("TRACE_ID", "")
        if block is None:
            block = os.getenv("BLOCK", "")
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "module": self.module,
            "tx_id": tx_id,
            "strategy_id": strategy_id,
            "mutation_id": mutation_id,
            "risk_level": risk_level,
            "block": block,
            "error": error,
            "trace_id": trace_id,
        }
        entry.update(extra)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
        for hook in list(_HOOKS):
            try:
                hook(entry)
            except Exception as exc:
                # log hook errors but do not interrupt logging
                log_error(
                    self.module,
                    f"hook error: {exc}",
                    event="hook_fail",
                    trace_id=trace_id,
                    block=block,
                )
        if error:
            log_error(
                self.module,
                error,
                event=event,
                tx_id=tx_id,
                strategy_id=strategy_id,
                mutation_id=mutation_id,
                risk_level=risk_level,
                trace_id=trace_id,
                block=block,
            )
        if error or risk_level == "high":
            _send_alert(f"{self.module}:{event}:{error or ''}")

    # ------------------------------------------------------------------
    def trace(self, message: str, **kw: Any) -> None:
        """Alias for :func:`log` used for verbose tracing."""

        self.log(message, **kw)

