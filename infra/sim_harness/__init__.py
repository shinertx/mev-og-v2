"""Fork simulation harness for MEV-OG."""

from __future__ import annotations

try:
    from prometheus_client import start_http_server
except Exception:  # pragma: no cover - optional
    def start_http_server(*_a: object, **_k: object) -> None:
        pass


def start_metrics(port: int = 8000) -> None:
    """Start Prometheus metrics endpoint for simulations."""
    try:
        start_http_server(port)
    except Exception:
        pass
