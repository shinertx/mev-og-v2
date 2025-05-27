"""Unit tests for StructuredLogger behavior."""

import json
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from core.logger import StructuredLogger, register_hook


def test_structured_logging(tmp_path, monkeypatch):
    log_file = tmp_path / "log.json"
    err_file = tmp_path / "errors.log"
    monkeypatch.setenv("ERROR_LOG_FILE", str(err_file))
    logger = StructuredLogger("test_mod", log_file=str(log_file))
    captured = []

    def hook(entry):
        captured.append(entry)

    register_hook(hook)
    logger.log(
        "event",
        tx_id="1",
        strategy_id="s",
        mutation_id="m",
        risk_level="low",
        error="boom",
    )

    data = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert data[0]["module"] == "test_mod"
    assert data[0]["event"] == "event"
    assert captured and captured[0]["tx_id"] == "1"
    ts = data[0]["timestamp"]
    dt = datetime.fromisoformat(ts)
    assert dt.tzinfo is not None

    err_lines = err_file.read_text().splitlines()
    assert err_lines
    err = json.loads(err_lines[0])
    assert err["error"] == "boom"
    assert err["module"] == "test_mod"
