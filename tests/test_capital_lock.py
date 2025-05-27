import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from agents.capital_lock import CapitalLock


def test_lock_and_unlock():
    lock = CapitalLock(max_drawdown_pct=5, max_loss_usd=100, balance_usd=1000)
    lock.record_trade(-60)
    assert lock.trade_allowed()
    lock.record_trade(-60)
    assert not lock.trade_allowed()
    assert lock.unlock(approved=False) is False
    assert not lock.trade_allowed()
    assert lock.unlock(approved=True)
    assert lock.trade_allowed()

