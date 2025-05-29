import json
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

import pytest

from core.tx_engine.builder import TransactionBuilder, HexBytes
from core.tx_engine.nonce_manager import NonceManager
from core.tx_engine import kill_switch as ks


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


def test_kill_switch_bypass_attempt(tmp_path, monkeypatch):
    web3 = DummyWeb3()
    nm = NonceManager(web3, cache_file=str(tmp_path / "nonce.json"))
    builder = TransactionBuilder(web3, nm, log_path=tmp_path / "log.json")
    kill_log = tmp_path / "kill.json"
    err_log = tmp_path / "errors.log"
    monkeypatch.setenv("KILL_SWITCH", "1")
    monkeypatch.setenv("KILL_SWITCH_LOG_FILE", str(kill_log))
    monkeypatch.setenv("ERROR_LOG_FILE", str(err_log))
    monkeypatch.setattr(ks, "kill_switch_triggered", lambda: False)
    with pytest.raises(RuntimeError):
        builder.send_transaction(HexBytes(b"\x01"), "0xdef")
    entries = [json.loads(line) for line in kill_log.read_text().splitlines()]
    assert entries[-1]["origin_module"] == "TransactionBuilder"
    err_lines = err_log.read_text().splitlines()
    assert err_lines
    monkeypatch.delenv("KILL_SWITCH")
