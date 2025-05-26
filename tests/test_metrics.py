"""Tests for Prometheus metrics server."""

<<<<<<< HEAD
import sys
import pathlib
=======
import sys, pathlib
>>>>>>> 08463589b36fe30ca5373bfc83ad4f47056a2779
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

from core import metrics


def test_metrics_server(tmp_path):
    srv = metrics.MetricsServer(port=0)
    srv.start()

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
