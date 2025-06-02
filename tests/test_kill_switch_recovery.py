import importlib
import json

import core.tx_engine.kill_switch as ks


def test_clear_kill_switch(tmp_path, monkeypatch):
    flag_file = tmp_path / "flag.txt"
    log_file = tmp_path / "log.json"
    monkeypatch.setenv("KILL_SWITCH_FLAG_FILE", str(flag_file))
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    monkeypatch.setenv("KILL_SWITCH", "1")
    importlib.reload(ks)

    ks.init_kill_switch()
    assert ks.kill_switch_triggered() is True
    ks.clear_kill_switch()
    assert ks.kill_switch_triggered() is False


def test_record_recovery(tmp_path, monkeypatch):
    log_file = tmp_path / "log.json"
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(log_file))
    importlib.reload(ks)
    ks.record_recovery_event("test")
    data = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert data[-1]["origin_module"] == "test"
    assert data[-1]["kill_event"] is False
