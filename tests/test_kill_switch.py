"""Tests for the kill switch environment and file triggers."""


import sys
from pathlib import Path
import os
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib

import core.tx_engine.kill_switch as ks


def test_env_triggers_kill_switch(tmp_path, monkeypatch):
    log_file = tmp_path / "log.json"
    flag_file = tmp_path / "flag.txt"
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    monkeypatch.setenv("KILL_SWITCH_FLAG_FILE", str(flag_file))
    monkeypatch.setenv("KILL_SWITCH", "1")
    importlib.reload(ks)

    ks.init_kill_switch()
    assert ks.kill_switch_triggered() is True

    ks.record_kill_event("test_env")
    data = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert data[0]["triggered_by"] == "env"
    assert data[0]["origin_module"] == "test_env"
    assert data[0]["kill_event"] is True
    assert "timestamp" in data[0]


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
    data = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert data[0]["triggered_by"] == "file"
    assert data[0]["origin_module"] == "test_file"


