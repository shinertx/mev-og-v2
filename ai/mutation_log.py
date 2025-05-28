"""Mutation log utilities for agent evolution."""

from __future__ import annotations

from typing import Any

import os
from core.logger import StructuredLogger

LOG = StructuredLogger("mutation_log", log_file=os.getenv("MUTATION_LOG", "logs/mutation_log.json"))


def log_mutation(event: str, **data: Any) -> None:
    """Append a mutation event entry."""
    LOG.log(event, **data)
