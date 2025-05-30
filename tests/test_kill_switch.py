"""Tests for the kill switch environment and file triggers."""

import json
import importlib


import core.tx_engine.kill_switch as ks


def test_env_triggers_kill_switch(tmp_path, monkeypatch):
    log_file = tmp_path / "log.json"
    flag_file = tmp_path / "flag.txt"
    err_file = tmp_path / "errors.log"
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    monkeypatch.setenv("KILL_SWITCH_FLAG_FILE", str(flag_file))
    monkeypatch.setenv("KILL_SWITCH", "1")
    monkeypatch.setenv("ERROR_LOG_FILE", str(err_file))
    importlib.reload(ks)

    ks.init_kill_switch()
    assert ks.kill_switch_triggered() is True

    ks.record_kill_event("test_env")
    data = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert data[0]["triggered_by"] == "env"
    assert data[0]["origin_module"] == "test_env"
    assert data[0]["kill_event"] is True
    assert "timestamp" in data[0]
    err_lines = err_file.read_text().splitlines()
    assert err_lines


def test_file_triggers_kill_switch(tmp_path, monkeypatch):
    log_file = tmp_path / "log.json"
    flag_file = tmp_path / "flag.txt"
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    monkeypatch.setenv("KILL_SWITCH_FLAG_FILE", str(flag_file))
    monkeypatch.delenv("KILL_SWITCH", raising=False)
    importlib.reload(ks)

    flag_file.write_text("1")

    ks.init_kill_switch()
    assert ks.kill_switch_triggered() is True

    ks.record_kill_event("test_file")
    data = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert data[0]["triggered_by"] == "file"
    assert data[0]["origin_module"] == "test_file"


def test_dev_mode_cannot_bypass(tmp_path, monkeypatch):
    """Ensure DEV_MODE does not bypass kill switch."""
    log_file = tmp_path / "log.json"
    flag_file = tmp_path / "flag.txt"
    err_file = tmp_path / "errors.log"
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    monkeypatch.setenv("KILL_SWITCH_FLAG_FILE", str(flag_file))
    monkeypatch.setenv("KILL_SWITCH", "1")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("ERROR_LOG_FILE", str(err_file))
    importlib.reload(ks)

    ks.init_kill_switch()
    assert ks.kill_switch_triggered() is True

    ks.record_kill_event("test_dev")
    data = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert data[0]["origin_module"] == "test_dev"
    err_lines = err_file.read_text().splitlines()
    assert err_lines


def test_kill_event_log_contains_origin(tmp_path, monkeypatch):
    """Regression test for origin_module field presence."""
    log_file = tmp_path / "log.json"
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    importlib.reload(ks)

    ks.record_kill_event("test_regression")
    ks.record_kill_event("test_regression2")
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries
    for entry in entries:
        assert entry["origin_module"]
