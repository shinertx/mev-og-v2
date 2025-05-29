"""Tests for TransactionBuilder and associated kill switch logic."""

import json
from pathlib import Path
import threading
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

import pytest

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager




class DummyEth:
    def __init__(self):
        self.sent = []

    def estimate_gas(self, tx):
        return 21000

    def get_transaction_count(self, address):
        return 0

    def send_raw_transaction(self, tx):
        self.sent.append(tx)
        return b"hash" + tx[-2:]

    class account:
        @staticmethod
        def decode_transaction(tx):
            return {}


class DummyWeb3:
    def __init__(self):
        self.eth = DummyEth()


def test_gas_estimation_and_nonce(tmp_path):
    web3 = DummyWeb3()
    nm = NonceManager(web3, cache_file=str(tmp_path / "nonce.json"))
    builder = TransactionBuilder(web3, nm, log_path=tmp_path / "log.json")

    tx = HexBytes(b"\x01\x02")
    result = builder.send_transaction(tx, "0xabc")
    assert result.startswith(b"hash")
    # nonce should increment
    assert nm.get_nonce("0xabc") == 1

    # log written
    log_lines = Path(tmp_path / "log.json").read_text().strip().split("\n")
    entry = json.loads(log_lines[0])
    assert entry["gas_estimate"] == int(21000 * 1.2)
    assert entry["status"] == "sent"


def test_kill_switch(tmp_path, monkeypatch):
    web3 = DummyWeb3()
    nm = NonceManager(web3, cache_file=str(tmp_path / "nonce.json"))
    builder = TransactionBuilder(web3, nm, log_path=tmp_path / "log.json")
    kill_log = tmp_path / "kill.json"
    err_log = tmp_path / "errors.log"
    monkeypatch.setenv("KILL_SWITCH", "1")
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(kill_log))
    monkeypatch.setenv("ERROR_LOG_FILE", str(err_log))
    with pytest.raises(RuntimeError):
        builder.send_transaction(HexBytes(b"\x01"), "0xdef")
    entries = [json.loads(line) for line in kill_log.read_text().splitlines()]
    assert entries[-1]["origin_module"] == "TransactionBuilder"
    err_lines = err_log.read_text().splitlines()
    assert err_lines
    monkeypatch.delenv("KILL_SWITCH")


def test_agent_gates_block(tmp_path):
    web3 = DummyWeb3()
    nm = NonceManager(web3, cache_file=str(tmp_path / "nonce.json"))
    builder = TransactionBuilder(web3, nm, log_path=tmp_path / "log.json")
    from agents.agent_registry import set_value
    set_value("paused", True)
    with pytest.raises(RuntimeError):
        builder.send_transaction(HexBytes(b"\x01"), "0xabc")
    set_value("paused", False)

def test_cross_agent_order_flow(tmp_path):
    web3 = DummyWeb3()
    nm = NonceManager(web3, cache_file=str(tmp_path / "nonce.json"))
    b1 = TransactionBuilder(web3, nm, log_path=tmp_path / "a.json")
    b2 = TransactionBuilder(web3, nm, log_path=tmp_path / "b.json")

    def send(builder, tx):
        builder.send_transaction(tx, "0xabc")

    t1 = threading.Thread(target=send, args=(b1, HexBytes(b"\x01")))
    t2 = threading.Thread(target=send, args=(b2, HexBytes(b"\x02")))
    t1.start(); t2.start(); t1.join(); t2.join()

    # nonces should be sequential across builders
    assert nm.get_nonce("0xabc") == 2
