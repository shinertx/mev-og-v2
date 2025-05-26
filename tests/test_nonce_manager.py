import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.tx_engine.nonce_manager import NonceManager


class DummyEth:
    def __init__(self, start=5):
        self.start = start
        self.calls = 0

    def get_transaction_count(self, address):
        self.calls += 1
        return self.start


class DummyWeb3:
    def __init__(self, start=5):
        self.eth = DummyEth(start)


def test_cache_update_and_reset(tmp_path):
    cache = tmp_path / "cache.json"
    log_file = tmp_path / "log.json"
    w3 = DummyWeb3()
    nm = NonceManager(w3, cache_file=str(cache), log_file=str(log_file))

    # First call fetches from RPC
    nonce1 = nm.get_nonce("0xabc")
    assert nonce1 == 5
    assert w3.eth.calls == 1

    # Subsequent call uses cache and increments
    nonce2 = nm.get_nonce("0xabc")
    assert nonce2 == 6
    assert w3.eth.calls == 1

    data = json.load(cache.open())
    assert data["0xabc"] == 6

    # manual update
    nm.update_nonce("0xabc", 10)
    assert nm.get_nonce("0xabc") == 11

    nm.reset_nonce("0xabc")
    assert "0xabc" not in json.load(cache.open())
    nonce3 = nm.get_nonce("0xabc")
    assert nonce3 == 5
    assert w3.eth.calls == 4

    logs = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert logs[-1]["source"] == "get"
    assert logs[0]["source"] == "get"
