import sys
import types

from ai.intent_ghost import ghost_intent
from ai.mutation_manager import MutationManager


def test_ghost_intent(monkeypatch):
    calls = {}
    class Req:
        def __init__(self):
            self.post = fake_post
    def fake_post(url, json, timeout):
        calls['url'] = url
        calls['json'] = json
        class Resp:
            def raise_for_status(self):
                pass
        return Resp()
    monkeypatch.setitem(sys.modules, 'requests', types.SimpleNamespace(post=fake_post))
    ghost_intent('http://api', {'intent_id': 'x'})
    assert calls['url'].endswith('/intents')


def test_mutation_manager(monkeypatch):
    class Dummy:
        def __init__(self, threshold=0.1):
            self.t = threshold
        def evaluate_pnl(self):
            return self.t
    mm = MutationManager({'threshold': 0.1}, num_agents=2)
    mm.spawn_agents(Dummy)
    assert len(mm.agents) == 2
    mm.score_and_prune()
    assert mm.agents


def test_hedge_risk(monkeypatch):
    called = {}

    def fake_post(url, json, timeout):
        called['url'] = url
        class Resp:
            def raise_for_status(self):
                pass
        return Resp()

    class _Session:
        def post(self, url, json, timeout):
            return fake_post(url, json, timeout)

    monkeypatch.setitem(
        sys.modules,
        'requests',
        types.SimpleNamespace(post=fake_post, Session=lambda: _Session())
    )

    from strategies.cross_domain_arb import CrossDomainArb, PoolConfig
    from agents.capital_lock import CapitalLock

    pools = {
        "eth": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "ethereum"
        ),  # test-only
        "arb": PoolConfig(
            "0xdeadbeef00000000000000000000000000000000", "arbitrum"
        ),  # test-only
    }
    strat = CrossDomainArb(pools, {}, threshold=0.0, capital_lock=CapitalLock(1000, 1e9, 0), edges_enabled={"hedge": True})
    strat.hedge_risk(1.0, "ETH")
    assert called['url'].startswith("http://")
