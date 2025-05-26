import os
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager
from core.tx_engine.kill_switch import kill_switch_triggered


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
    nm = NonceManager(web3)
    builder = TransactionBuilder(web3, nm, log_path=tmp_path / "log.json")

    tx = HexBytes(b"\x01\x02")
    result = builder.send_transaction(tx, "0xabc")
    assert result.startswith(b"hash")
    # nonce should increment
    assert nm.get_next_nonce("0xabc") == 1

    # log written
    log_lines = Path(tmp_path / "log.json").read_text().strip().split("\n")
    entry = json.loads(log_lines[0])
    assert entry["gas_estimate"] == int(21000 * 1.2)
    assert entry["status"] == "sent"


def test_kill_switch(tmp_path, monkeypatch):
    web3 = DummyWeb3()
    nm = NonceManager(web3)
    builder = TransactionBuilder(web3, nm, log_path=tmp_path / "log.json")
    monkeypatch.setenv("KILL_SWITCH_ACTIVE", "1")
    with pytest.raises(RuntimeError):
        builder.send_transaction(HexBytes(b"\x01"), "0xdef")
    monkeypatch.delenv("KILL_SWITCH_ACTIVE")
