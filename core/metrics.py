"""Prometheus-style metrics endpoint for MEV-OG.

Module purpose and system role:
    - Track strategy performance and system health metrics.
    - Provide an HTTP ``/metrics`` endpoint consumable by Prometheus.

Integration points and dependencies:
    - Uses ``http.server`` from the standard library; no external deps.
    - Strategies call update functions to modify metric counters.

Simulation/test hooks and kill conditions:
    - Designed for forked and unit test environments.
    - Lightweight server can be started and stopped in tests.
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from statistics import mean
from typing import Dict, List, cast


_METRICS: Dict[str, List[float] | float | int] = {
    "opportunities": 0,
    "fails": 0,
    "pnl": 0.0,
    "spreads": [],
    "latencies": [],
    "alert_count": 0,
}
_LOCK = threading.Lock()
_METRICS_TOKEN = os.getenv("METRICS_TOKEN")


# ----------------------------------------------------------------------
# Metric update helpers
# ----------------------------------------------------------------------

def record_opportunity(spread: float, pnl: float, latency: float) -> None:
    with _LOCK:
        _METRICS["opportunities"] = cast(int, _METRICS["opportunities"]) + 1
        _METRICS["pnl"] = cast(float, _METRICS["pnl"]) + pnl
        cast(list, _METRICS["spreads"]).append(spread)  # type: ignore[arg-type]
        cast(list, _METRICS["latencies"]).append(latency)  # type: ignore[arg-type]


def record_fail() -> None:
    with _LOCK:
        _METRICS["fails"] = cast(int, _METRICS["fails"]) + 1


def record_alert() -> None:
    with _LOCK:
        _METRICS["alert_count"] = cast(int, _METRICS["alert_count"]) + 1


# ----------------------------------------------------------------------
# Metrics server
# ----------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """Serve metrics data for Prometheus scraping."""
    def do_GET(self) -> None:  # pragma: no cover - trivial
        if _METRICS_TOKEN:
            auth = self.headers.get("Authorization")
            if auth != f"Bearer {_METRICS_TOKEN}":
                self.send_response(401)
                self.end_headers()
                return
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        with _LOCK:
            avg_spread = mean(_METRICS["spreads"]) if _METRICS["spreads"] else 0.0
            avg_latency = mean(_METRICS["latencies"]) if _METRICS["latencies"] else 0.0
            body = (
                f"opportunities_total {_METRICS['opportunities']}\n"
                f"fails_total {_METRICS['fails']}\n"
                f"pnl_total {_METRICS['pnl']}\n"
                f"avg_spread {avg_spread}\n"
                f"avg_latency_seconds {avg_latency}\n"
                f"alert_count {_METRICS['alert_count']}\n"
            ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MetricsServer:
    """Background metrics HTTP server."""

    def __init__(self, host: str = "0.0.0.0", port: int | None = None) -> None:
        port = int(os.getenv("METRICS_PORT", port or 8000))
        try:
            self.server = HTTPServer((host, port), _Handler)
        except OSError as exc:  # pragma: no cover - runtime check
            if "Address already in use" in str(exc):
                raise OSError(
                    f"Port {port} already in use. Set METRICS_PORT or pass --port."
                ) from exc
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join()


if __name__ == "__main__":  # pragma: no cover - manual startup
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Start metrics HTTP server")
    parser.add_argument("--port", type=int, default=None, help="Port to bind")
    args = parser.parse_args()

    srv = MetricsServer(port=args.port)
    srv.start()
    host, port = srv.server.server_address
    print(f"Metrics server running on {host}:{port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
