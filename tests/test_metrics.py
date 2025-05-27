"""Tests for Prometheus metrics server."""

import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core import metrics
import importlib
import os

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def test_metrics_server(tmp_path):
    srv = metrics.MetricsServer(port=0)
    srv.start()
    metrics._METRICS.update({"opportunities": 0, "fails": 0, "pnl": 0.0, "spreads": [], "latencies": [], "alert_count": 0})

    metrics.record_opportunity(0.1, 5.0, 0.5)
    metrics.record_fail()
    metrics.record_alert()

    host, port = srv.server.server_address
    url = f"http://{host}:{port}/metrics"
    data = opener.open(url).read().decode()
    srv.stop()

    assert "opportunities_total 1" in data
    assert "fails_total 1" in data
    assert "alert_count 1" in data


def _start_server_with_token(monkeypatch, token):
    monkeypatch.setenv("METRICS_TOKEN", token)
    importlib.reload(metrics)
    srv = metrics.MetricsServer(port=0)
    srv.start()
    return srv


def test_metrics_authorized(monkeypatch):
    token = "secret"
    srv = _start_server_with_token(monkeypatch, token)
    host, port = srv.server.server_address
    req = urllib.request.Request(
        f"http://{host}:{port}/metrics", headers={"Authorization": f"Bearer {token}"}
    )
    data = opener.open(req).read().decode()
    srv.stop()
    assert "opportunities_total" in data


def test_metrics_unauthorized(monkeypatch):
    token = "secret"
    srv = _start_server_with_token(monkeypatch, token)
    host, port = srv.server.server_address
    req = urllib.request.Request(f"http://{host}:{port}/metrics")
    try:
        opener.open(req)
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("expected 401")
    finally:
        srv.stop()
