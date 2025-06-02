import json
import time
from pathlib import Path

from agents.founder_gate import founder_approved


def test_env_token(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDER_TOKEN", "op:9999999999")
    assert founder_approved("op")
    log = Path("logs/founder_gate.json")
    if log.exists():
        entries = [json.loads(line) for line in log.read_text().splitlines()]
        assert entries[-1]["approved"] is True


def test_file_token(monkeypatch, tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("task:%d" % (time.time() + 10))
    monkeypatch.delenv("FOUNDER_TOKEN", raising=False)
    monkeypatch.setenv("FOUNDER_TOKEN_FILE", str(token_file))
    assert founder_approved("task")


def test_expired_token(monkeypatch):
    monkeypatch.setenv("FOUNDER_TOKEN", "task:1")
    assert not founder_approved("task")
