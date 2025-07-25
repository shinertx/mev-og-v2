"""Adaptive multi-agent mutation manager."""

from __future__ import annotations

from typing import Any, Dict, List, Type

from core.logger import StructuredLogger
from .mutation_log import log_mutation

LOG = StructuredLogger("mutation_manager")


class MutationManager:
    """Spawn and score multiple strategy variants and prune losers."""

    def __init__(self, base_params: Dict[str, Any], num_agents: int = 4) -> None:
        self.base_params = base_params
        self.num_agents = num_agents
        self.agents: List[Any] = []
        self.scores: Dict[int, float] = {}
        self.chaos_counts: Dict[str, int] = {}

    # --------------------------------------------------------------
    def spawn_agents(self, agent_class: Type[Any]) -> None:
        """Instantiate agents with param mutations."""
        import random

        self.agents = []
        for i in range(self.num_agents):
            mutated = self.base_params.copy()
            mutated["threshold"] = mutated.get("threshold", 0.003) * (0.9 + 0.2 * random.random())
            agent = agent_class(**mutated)
            self.agents.append(agent)
            LOG.log("spawn_agent", agent_id=i, params=mutated)
            log_mutation("spawn_agent", agent_id=i, params=mutated)

    # --------------------------------------------------------------
    def score_and_prune(self) -> None:
        """Score each agent and keep only top performers."""
        self.scores = {i: getattr(agent, "evaluate_pnl", lambda: 0.0)() for i, agent in enumerate(self.agents)}
        keep = sorted(self.scores, key=lambda k: self.scores[k], reverse=True)[: max(1, self.num_agents // 2)]
        LOG.log("prune_agents", kept=keep, scores=self.scores)
        pruned = [i for i in range(len(self.scores)) if i not in keep]
        for pid in pruned:
            log_mutation("prune_agent", agent_id=pid, pnl=self.scores.get(pid, 0.0), reason="low_score")
        self.agents = [self.agents[i] for i in keep]

    # --------------------------------------------------------------
    def handle_pruning(self, strategies: List[str], dry_run: bool = False) -> None:
        """Trigger mutation cycle when strategies are pruned."""
        if not strategies:
            return
        if dry_run:
            LOG.log("mutation_dry_run", strategies=strategies)
            return
        log_mutation("trigger_mutation", strategies=strategies)
        LOG.log("trigger_mutation", strategies=strategies)

    # --------------------------------------------------------------
    def record_chaos_event(self, adapter: str, event: str) -> None:
        """Track adapter chaos events and emit mutation hooks."""
        count = self.chaos_counts.get(adapter, 0) + 1
        self.chaos_counts[adapter] = count
        log_mutation("adapter_chaos_event", adapter=adapter, adapter_event=event, count=count)
        LOG.log("adapter_chaos_event", adapter=adapter, adapter_event=event, count=count)
        if count >= 3:
            log_mutation("adapter_chaos_mutation", adapter=adapter)
            LOG.log("adapter_chaos_mutation", adapter=adapter)
