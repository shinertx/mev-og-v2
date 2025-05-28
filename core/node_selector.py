"""RPC/relay node performance tracker and selector."""

from __future__ import annotations

from statistics import mean
from typing import Dict, List, TypedDict

from core.logger import StructuredLogger

LOG = StructuredLogger("node_selector")


class NodeSelector:
    """Select the best-performing RPC or relay node."""

    def __init__(self, nodes: Dict[str, str]) -> None:
        self.nodes = nodes
        class _Stats(TypedDict):
            latencies: List[float]
            success: int
            fail: int

        self.stats: Dict[str, _Stats] = {
            n: {"latencies": [], "success": 0, "fail": 0} for n in nodes
        }

    def record(self, node: str, success: bool, latency: float) -> None:
        if node not in self.stats:
            return
        self.stats[node]["latencies"].append(latency)
        if success:
            self.stats[node]["success"] = int(self.stats[node]["success"]) + 1
        else:
            self.stats[node]["fail"] = int(self.stats[node]["fail"]) + 1
        LOG.log(
            "node_perf",
            node=node,
            success=success,
            latency=latency,
            strategy_id="cross_domain_arb",
            mutation_id="dev",
            risk_level="low",
        )

    def best(self) -> str:
        best_node = None
        best_score = float("inf")
        for node, st in self.stats.items():
            latencies = st["latencies"]
            if not latencies:
                continue
            score = mean(latencies) * (1 + st["fail"])  # penalize failures
            if score < best_score:
                best_score = score
                best_node = node
        return best_node or list(self.nodes)[0]
