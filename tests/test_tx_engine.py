"""Tests for TransactionBuilder and associated kill switch logic."""

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
    entries = [json.loads(l) for l in kill_log.read_text().splitlines()]
    assert entries[-1]["origin_module"] == "TransactionBuilder"
    err_lines = err_log.read_text().splitlines()
    assert err_lines
    monkeypatch.delenv("KILL_SWITCH")
