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
try:
    from prometheus_client import (
        Counter as PCounter,
        Histogram as PHistogram,
        generate_latest,
        start_http_server,
    )
except Exception:  # pragma: no cover - optional
    PCounter = PHistogram = None  # type: ignore
    def generate_latest() -> bytes:  # type: ignore
        return b""
    def start_http_server(*_a: object, **_k: object) -> None:  # type: ignore
        pass
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from statistics import mean
from typing import Any, Dict, List, cast


_METRICS: Dict[str, Any] = {
    "opportunities": 0,
    "fails": 0,
    "pnl": 0.0,
    "spreads": [],
    "latencies": [],
    "alert_count": 0,
    "strategy_scores": {},
    "prune_total": 0,
    "decay_alerts": 0,
    "mutation_events": 0,
    "opportunities_found": 0,
    "arb_profit": 0.0,
    "arb_latency": [],
    "error_count": 0,
    "abort_total": 0,
    "kill_events": 0,
    "drp_anomalies": 0,
}
_LOCK = threading.Lock()
_METRICS_TOKEN = os.getenv("METRICS_TOKEN")

if PCounter is not None:
    PROM_ARB_FOUND = PCounter("arb_opportunities_found", "Total arb opps")
    PROM_PROFIT_ETH = PCounter("arb_profit_eth", "Cumulative ETH profit")
    PROM_LATENCY = PHistogram("arb_latency", "Latency for arbs")
    PROM_ERROR_COUNT = PCounter("arb_error_count", "Errors during arb")
    PROM_KILL = PCounter("kill_event_total", "Kill switch events")
    PROM_DRP = PCounter("drp_anomaly_total", "DRP anomalies")
else:  # pragma: no cover - metrics optional
    class _Dummy:
        def inc(self, *_a: object, **_k: object) -> None:
            pass

        def observe(self, *_a: object, **_k: object) -> None:
            pass

    PROM_ARB_FOUND = PROM_PROFIT_ETH = PROM_LATENCY = PROM_ERROR_COUNT = PROM_KILL = PROM_DRP = _Dummy()


# ----------------------------------------------------------------------
# Metric update helpers
# ----------------------------------------------------------------------

def record_opportunity(spread: float, pnl: float, latency: float) -> None:
    with _LOCK:
        _METRICS["opportunities"] = cast(int, _METRICS["opportunities"]) + 1
        _METRICS["opportunities_found"] = cast(int, _METRICS.get("opportunities_found", 0)) + 1
        _METRICS["pnl"] = cast(float, _METRICS["pnl"]) + pnl
        _METRICS["arb_profit"] = cast(float, _METRICS.get("arb_profit", 0.0)) + pnl
        cast(list, _METRICS["spreads"]).append(spread)  # type: ignore[arg-type]
        cast(list, _METRICS["latencies"]).append(latency)  # type: ignore[arg-type]
        cast(list, _METRICS["arb_latency"]).append(latency)  # type: ignore[arg-type]
    PROM_ARB_FOUND.inc()
    PROM_PROFIT_ETH.inc(pnl)
    PROM_LATENCY.observe(latency)


def record_fail() -> None:
    with _LOCK:
        _METRICS["fails"] = cast(int, _METRICS["fails"]) + 1

    record_error()


def record_error() -> None:
    with _LOCK:
        _METRICS["error_count"] = cast(int, _METRICS.get("error_count", 0)) + 1
    PROM_ERROR_COUNT.inc()

def record_alert() -> None:
    with _LOCK:
        _METRICS["alert_count"] = cast(int, _METRICS["alert_count"]) + 1



def record_strategy_score(sid: str, score: float) -> None:
    with _LOCK:
        scores = cast(Dict[str, float], _METRICS.setdefault("strategy_scores", {}))
        scores[sid] = score


def record_prune() -> None:
    with _LOCK:
        _METRICS["prune_total"] = cast(int, _METRICS.get("prune_total", 0)) + 1


def record_decay_alert() -> None:
    with _LOCK:
        _METRICS["decay_alerts"] = cast(int, _METRICS.get("decay_alerts", 0)) + 1


def record_mutation_event() -> None:
    with _LOCK:
        _METRICS["mutation_events"] = cast(int, _METRICS.get("mutation_events", 0)) + 1


def record_abort() -> None:
    """Record a trade abort decision."""
    with _LOCK:
        _METRICS["abort_total"] = cast(int, _METRICS.get("abort_total", 0)) + 1

def record_kill_event_metric() -> None:
    with _LOCK:
        _METRICS["kill_events"] = cast(int, _METRICS.get("kill_events", 0)) + 1
    PROM_KILL.inc()


def record_drp_anomaly() -> None:
    with _LOCK:
        _METRICS["drp_anomalies"] = cast(int, _METRICS.get("drp_anomalies", 0)) + 1
    PROM_DRP.inc()


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
            spreads = cast(List[float], _METRICS["spreads"])
            latencies = cast(List[float], _METRICS["latencies"])
            arb_latencies = cast(List[float], _METRICS.get("arb_latency", []))
            avg_spread = mean(spreads) if spreads else 0.0
            avg_latency = mean(latencies) if latencies else 0.0
            avg_arb_latency = mean(arb_latencies) if arb_latencies else 0.0
            custom = (
                f"opportunities_total {_METRICS['opportunities']}\n"
                f"fails_total {_METRICS['fails']}\n"
                f"pnl_total {_METRICS['pnl']}\n"
                f"avg_spread {avg_spread}\n"
                f"avg_latency_seconds {avg_latency}\n"
                f"alert_count {_METRICS['alert_count']}\n"
                f"prune_total {_METRICS['prune_total']}\n"
                f"decay_alerts {_METRICS['decay_alerts']}\n"
                f"mutation_events {_METRICS['mutation_events']}\n"
                f"abort_total {_METRICS['abort_total']}\n"
                f"opportunities_found_total {_METRICS['opportunities_found']}\n"
                f"arb_profit_total {_METRICS['arb_profit']}\n"
                f"avg_arb_latency_seconds {avg_arb_latency}\n"
                f"error_count {_METRICS['error_count']}\n"
                f"kill_events_total {_METRICS['kill_events']}\n"
                f"drp_anomalies_total {_METRICS['drp_anomalies']}\n"
            )
            body = generate_latest() + custom.encode()
            scores = cast(Dict[str, float], _METRICS.get("strategy_scores", {}))
            for sid, val in scores.items():
                body += f"strategy_score{{strategy=\"{sid}\"}} {val}\n".encode()
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
            if kill_switch_triggered():
                record_kill_event("metrics_server")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
