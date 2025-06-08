from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

from core.logger import StructuredLogger

def _votes_dir() -> Path:
    path = Path(os.getenv("AI_VOTES_DIR", "telemetry/ai_votes"))
    path.mkdir(parents=True, exist_ok=True)
    return path

LOGGER = StructuredLogger("voting")

EXPECTED_AGENTS = ["Codex_v1", "Codex_v2", "ClaudeSim", "InternalDRL"]


def record_vote(
    strategy_id: str,
    patch_hash: str,
    agent: str,
    vote: bool,
    reason: str,
    timestamp: str,
) -> None:
    """Record a vote decision to ``telemetry/ai_votes``."""
    path = _votes_dir() / f"ai_vote_{timestamp.replace(':', '-')}.json"
    entry = {
        "strategy_id": strategy_id,
        "patch_hash": patch_hash,
        "agent": agent,
        "vote": vote,
        "reason": reason,
        "timestamp": timestamp,
    }
    with path.open("w") as fh:
        json.dump(entry, fh)
    LOGGER.log(
        "vote_recorded",
        strategy_id=strategy_id,
        agent=agent,
        vote=vote,
        patch_hash=patch_hash,
        trace_id=os.getenv("TRACE_ID", ""),
    )


def _collect_votes(strategy_id: str, patch_hash: str) -> Dict[str, bool]:
    votes: Dict[str, bool] = {}
    for file in _votes_dir().glob("ai_vote_*.json"):
        try:
            data = json.loads(file.read_text())
        except Exception:
            continue
        if (
            data.get("strategy_id") == strategy_id
            and data.get("patch_hash") == patch_hash
            and isinstance(data.get("agent"), str)
        ):
            votes[data["agent"]] = bool(data.get("vote"))
    return votes


def quorum_met(strategy_id: str, patch_hash: str) -> bool:
    """Return ``True`` if at least 3 expected agents approve."""
    votes = _collect_votes(strategy_id, patch_hash)
    approvals = [agent for agent, v in votes.items() if agent in EXPECTED_AGENTS and v]
    return len(set(approvals)) >= 3


def get_votes(strategy_id: str, patch_hash: str) -> Dict[str, bool]:
    """Expose recorded votes for ``strategy_id`` and ``patch_hash``."""
    return _collect_votes(strategy_id, patch_hash)
