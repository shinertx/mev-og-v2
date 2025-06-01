

from agents.capital_lock import CapitalLock
from agents.ops_agent import OpsAgent
from agents.drp_agent import DRPAgent
from agents.gatekeeper import gates_green
import core.tx_engine.kill_switch as ks


def _ops(paused=False):
    agent = OpsAgent({})
    agent.paused = paused
    return agent


def test_gates_all_green(monkeypatch):
    monkeypatch.setattr(ks, "kill_switch_triggered", lambda: False)
    monkeypatch.setattr("agents.gatekeeper.kill_switch_triggered", lambda: False)
    monkeypatch.delenv("OPS_CRITICAL_EVENT", raising=False)
    lock = CapitalLock(0, 0, 0)
    ops = _ops()
    drp = DRPAgent()
    assert gates_green(lock, ops, drp)


def test_gate_blocks_on_failure(monkeypatch):
    monkeypatch.setattr(ks, "kill_switch_triggered", lambda: True)
    monkeypatch.setattr("agents.gatekeeper.kill_switch_triggered", lambda: True)
    monkeypatch.delenv("OPS_CRITICAL_EVENT", raising=False)
    lock = CapitalLock(0, 0, 0)
    ops = _ops()
    drp = DRPAgent()
    assert not gates_green(lock, ops, drp)

    monkeypatch.setattr(ks, "kill_switch_triggered", lambda: False)
    monkeypatch.setattr("agents.gatekeeper.kill_switch_triggered", lambda: False)
    lock.blocked = True
    assert not gates_green(lock, ops, drp)

    lock.blocked = False
    ops.paused = True
    assert not gates_green(lock, ops, drp)

    ops.paused = False
    drp.ready = False
    assert not gates_green(lock, ops, drp)
