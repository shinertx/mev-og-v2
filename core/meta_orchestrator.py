"""Meta-orchestrator running multiple strategy variants."""

from __future__ import annotations

import random
from typing import Any, Dict, Type

from core.logger import StructuredLogger
from ai.mutation_log import log_mutation


class MetaOrchestrator:
    """Spawn, score and prune strategy variants."""

    def __init__(self, strategy_cls: Type[Any], base_params: Dict[str, Any], num_agents: int = 2) -> None:
        self.strategy_cls = strategy_cls
        self.base_params = base_params
        self.num_agents = num_agents
        self.active_agents: Dict[int, Any] = {}
        self.pruned_agents: list[int] = []
        self.logger = StructuredLogger("meta_orchestrator")
        self._spawn_agents(self.num_agents)

    # --------------------------------------------------------------
    def _spawn_agents(self, n: int) -> None:
        for _ in range(n):
            params = self.base_params.copy()
            params["threshold"] = params.get("threshold", 0.003) * (0.9 + 0.2 * random.random())
            aid = max(self.active_agents.keys(), default=-1) + 1
            agent = self.strategy_cls(**params)
            self.active_agents[aid] = agent
            log_mutation("spawn_variant", agent_id=aid, params=params)

    # --------------------------------------------------------------
    def run_cycle(self) -> None:
        for agent in self.active_agents.values():
            try:
                agent.run_once()
            except Exception:
                continue
        scores = {aid: getattr(agent, "evaluate_pnl", lambda: 0.0)() for aid, agent in self.active_agents.items()}
        keep = sorted(scores, key=lambda aid: scores[aid], reverse=True)[: max(1, self.num_agents // 2)]
        pruned = [aid for aid in list(self.active_agents) if aid not in keep]
        for aid in pruned:
            log_mutation("pruned_agent", agent_id=aid, pnl=scores.get(aid, 0.0), reason="low_performance")
            self.pruned_agents.append(aid)
            del self.active_agents[aid]
        if pruned:
            self._spawn_agents(len(pruned))
        self.logger.log("cycle", active=list(self.active_agents), pruned=pruned)

    # --------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        return {"active_agents": list(self.active_agents), "pruned_agents": self.pruned_agents}
