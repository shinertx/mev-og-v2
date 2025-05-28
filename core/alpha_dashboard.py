"""Lightweight Alpha/PnL dashboard using Flask.

This server exposes a JSON endpoint with recent performance data
for live strategies. It is intended for founder/ops monitoring and
runs independently from the core orchestrator.
"""

from __future__ import annotations

import os
from threading import Thread
from typing import Any, Dict

try:
    from flask import Flask, jsonify  # type: ignore
except Exception:  # pragma: no cover - optional dep
    Flask = None  # type: ignore
    def jsonify(data: Any) -> Any:  # type: ignore
        """Fallback when Flask is unavailable."""
        return data


class AlphaDashboard:
    """Serve runtime strategy status via ``/status``."""

    def __init__(self, orchestrator: Any, port: int | None = None) -> None:
        self.orchestrator = orchestrator
        self.port = int(os.getenv("DASHBOARD_PORT", port or 8501))
        if Flask is not None:
            self.app = Flask(__name__)
            self.app.add_url_rule("/status", "status", self._status)
        else:
            self.app = None
        self.thread: Thread | None = None

    # --------------------------------------------------------------
    def status_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"strategies": {}}
        if hasattr(self.orchestrator, "status"):
            data["orchestrator"] = self.orchestrator.status()
        strategies = getattr(self.orchestrator, "strategies", {})
        for sid, strat in strategies.items():
            trades = getattr(strat.capital_lock, "trades", [])
            pnl = sum(trades)
            wins = sum(1 for t in trades if t > 0)
            losses = sum(1 for t in trades if t <= 0)
            pools = [cfg.pool for cfg in getattr(strat, "pools", {}).values()]
            stealth = strat.edges_enabled.get("stealth_mode", False)
            data["strategies"][sid] = {
                "pnl": pnl,
                "wins": wins,
                "losses": losses,
                "pools": pools,
                "stealth_mode": stealth,
            }
        return data

    # --------------------------------------------------------------
    def _status(self) -> Any:  # pragma: no cover - HTTP wrapper
        return jsonify(self.status_data())

    # --------------------------------------------------------------
    def start(self) -> None:
        if self.app is None or Flask is None:
            return
        self.thread = Thread(
            target=self.app.run,
            kwargs={"host": "0.0.0.0", "port": self.port},
            daemon=True,
        )
        self.thread.start()

    # --------------------------------------------------------------
    def stop(self) -> None:
        if self.thread:
            try:
                from werkzeug.serving import make_server

                server = make_server("0.0.0.0", self.port, self.app)
                server.shutdown()  # pragma: no cover - manual
            except Exception:
                pass
            self.thread = None
