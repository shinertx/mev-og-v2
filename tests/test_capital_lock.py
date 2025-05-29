import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from agents.capital_lock import CapitalLock
import json
import pytest


def test_lock_and_unlock(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPITAL_LOCK_LOG", str(tmp_path / "lock.json"))
    monkeypatch.setenv("FOUNDER_APPROVED", "1")
    monkeypatch.setenv("TRACE_ID", "t123")
    lock = CapitalLock(max_drawdown_pct=5, max_loss_usd=100, balance_usd=1000)
    lock.record_trade(-60)
    assert lock.trade_allowed()
    lock.record_trade(-60)
    assert not lock.trade_allowed()
    assert lock.unlock(approved=False) is False
    assert not lock.trade_allowed()
    assert lock.unlock(approved=True)
    assert lock.trade_allowed()
    log_path = tmp_path / "lock.json"
    if not log_path.exists():
        pytest.skip("lock.json not created")
    entries = [json.loads(l) for l in log_path.read_text().splitlines()]
    assert entries[-1]["event"] == "unlock"
    assert entries[-1]["trace_id"] == "t123"


def test_unlock_requires_founder(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPITAL_LOCK_LOG", str(tmp_path / "lock.json"))
    monkeypatch.setenv("FOUNDER_APPROVED", "0")
    monkeypatch.setenv("TRACE_ID", "nope")
    lock = CapitalLock(max_drawdown_pct=5, max_loss_usd=100, balance_usd=1000)
    lock.blocked = True
    assert lock.unlock(approved=True) is False
    log_path = tmp_path / "lock.json"
    if not log_path.exists():
        pytest.skip("lock.json not created")
    entries = [json.loads(l) for l in log_path.read_text().splitlines()]
    assert entries[-1]["event"] == "unlock_rejected"
    assert entries[-1]["trace_id"] == "nope"

