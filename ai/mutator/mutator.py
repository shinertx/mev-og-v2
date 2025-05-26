"""Simple mutation agent for strategy evolution.

Module purpose and system role:
    - Coordinate scoring and pruning of strategies for AI-led adaptation.
    - Logs mutation decisions for further analysis.

Integration points and dependencies:
    - Depends on :func:`score_strategies` and :func:`prune_strategies`.
    - Uses :class:`core.logger.StructuredLogger` for event logging.

Simulation/test hooks and kill conditions:
    - Pure Python logic; deterministic and safe for unit testing.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from core.logger import StructuredLogger
from .score import score_strategies
from .prune import prune_strategies

LOGGER = StructuredLogger("mutator")


class Mutator:
    """Run scoring and pruning to mutate strategy set."""

    def __init__(self, metrics: Dict[str, Dict[str, Any]]):
        self.metrics = metrics

    # ------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        """Return scores and list of pruned strategies."""

        scores: List[Dict[str, Any]] = score_strategies(self.metrics)
        pruned = prune_strategies(self.metrics)
        LOGGER.log(
            "mutation_run",
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            strategy_id=",".join(self.metrics.keys()),
            risk_level="low",
            scores=scores,
            pruned=pruned,
        )
        return {"scores": scores, "pruned": pruned}
