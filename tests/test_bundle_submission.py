import sys
import types


from strategies.cross_rollup_superbot import CrossRollupSuperbot, PoolConfig, BridgeConfig

class DummyFlashbots:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], int]] = []

    def send_bundle(self, bundle: list[str], target_block: int) -> dict[str, str]:
        self.sent.append((bundle, target_block))
        return {"bundleHash": "hash"}

class DummyEth:
    def __init__(self) -> None:
        self.block_number = 1

class DummyWeb3:
    def __init__(self) -> None:
        self.eth = DummyEth()
        self.flashbots = DummyFlashbots()


def test_bundle_send(monkeypatch) -> None:
    module = types.ModuleType("flashbots")

    def flashbot(w3, account, endpoint_uri=None):
        w3.flashbots = DummyFlashbots()

    module.flashbot = flashbot
    monkeypatch.setitem(sys.modules, "flashbots", module)
    acct = types.ModuleType("eth_account")
    class DummyAccount:
        @staticmethod
        def from_key(key):
            return "acct"
    acct.Account = DummyAccount
    monkeypatch.setitem(sys.modules, "eth_account", acct)

    pools = {
        "eth": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "ethereum"
        ),  # test-only
        "arb": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "arbitrum"
        ),  # test-only
    }
    bridges = {("ethereum", "arbitrum"): BridgeConfig(0.0)}
    strat = CrossRollupSuperbot(pools, bridges)
    w3 = DummyWeb3()
    strat.tx_builder.web3 = w3
    strat.nonce_manager.web3 = w3
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    txid, latency = strat._bundle_and_send("test")
    assert txid == "hash"
    assert latency >= 0
    assert w3.flashbots.sent

def test_bundle_fallback(monkeypatch) -> None:
    module = types.ModuleType("flashbots")

    class FB:
        def send_bundle(self, bundle, target_block):
            raise RuntimeError("fail")

    def flashbot(w3, account, endpoint_uri=None):
        w3.flashbots = FB()

    module.flashbot = flashbot
    monkeypatch.setitem(sys.modules, "flashbots", module)
    acct = types.ModuleType("eth_account")
    class DummyAccount:
        @staticmethod
        def from_key(key):
            return "acct"
    acct.Account = DummyAccount
    monkeypatch.setitem(sys.modules, "eth_account", acct)

    pools = {
        "eth": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "ethereum"
        ),
        "arb": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "arbitrum"
        ),
    }
    bridges = {("ethereum", "arbitrum"): BridgeConfig(0.0)}
    strat = CrossRollupSuperbot(pools, bridges)
    w3 = DummyWeb3()
    strat.tx_builder.web3 = w3
    strat.nonce_manager.web3 = w3
    monkeypatch.setenv("FLASHBOTS_AUTH_KEY", "0x" + "11" * 32)
    def fake_send(tx, addr, **kw):
        return b"f"
    strat.tx_builder.send_transaction = fake_send
    txid, latency = strat._bundle_and_send("test")
    assert txid == "66"
    assert latency >= 0
